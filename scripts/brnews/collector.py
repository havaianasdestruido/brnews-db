"""Orquestração da coleta semanal: baixa todos os feeds e grava o JSONL."""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence
from urllib.parse import urlsplit

from .feedlist import Feed
from .fetcher import Fetcher, FetchResult
from .parsers import (
    ParsedFeed,
    dedupe_items,
    looks_blocked,
    make_id,
    parse_html,
    parse_markdown,
    parse_rss,
)

LOGGER = logging.getLogger("brnews.collector")

SCHEMA_VERSION = 1


@dataclass
class FeedReport:
    """Diagnóstico de um feed dentro de uma execução."""

    feed_name: str
    feed_slug: str
    feed_url: str
    feed_kind: str
    status: str = "pending"  # ok | empty | error
    items: int = 0
    route: str = ""
    via: str = ""
    http_status: Optional[int] = None
    strategy: str = ""
    elapsed: float = 0.0
    attempts: int = 0
    error: str = ""
    tried: List[str] = field(default_factory=list)


@dataclass
class RunResult:
    """Resultado completo de uma execução da coleta."""

    run_id: str
    started_at: str
    finished_at: str = ""
    duration_seconds: float = 0.0
    jsonl_path: Optional[Path] = None
    report_path: Optional[Path] = None
    total_items: int = 0
    feeds_total: int = 0
    feeds_ok: int = 0
    feeds_empty: int = 0
    feeds_failed: int = 0
    skipped_seen: int = 0
    routes: dict = field(default_factory=dict)
    proxies: dict = field(default_factory=dict)
    feeds: List[FeedReport] = field(default_factory=list)


# ------------------------------------------------------------------ validação
def _validate_rss(content: bytes, text: str) -> bool:
    if looks_blocked(content, text):
        return False
    head = content[:1500].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return False
    return bool(parse_rss(content, "").items)


def _validate_html(content: bytes, text: str) -> bool:
    return len(content) > 800 and not looks_blocked(content, text)


# ------------------------------------------------------------------- coletor
class Collector:
    def __init__(
        self,
        fetcher: Fetcher,
        output_dir: Path,
        limit_per_feed: int = 0,
        max_age_days: int = 0,
        summary_limit: int = 2000,
        workers: int = 8,
        include_content: bool = True,
        seen_ids: Optional[set[str]] = None,
        compress: bool = False,
    ):
        self.fetcher = fetcher
        self.output_dir = Path(output_dir)
        self.limit_per_feed = limit_per_feed
        self.max_age_days = max_age_days
        self.summary_limit = summary_limit
        self.workers = max(1, workers)
        self.include_content = include_content
        self.compress = compress
        self.seen_ids = seen_ids or set()
        self._skipped_seen = 0
        self._lock = threading.Lock()

    # -------------------------------------------------------------- um feed
    def collect_feed(self, feed: Feed, run_id: str, collected_at: str):
        report = FeedReport(
            feed_name=feed.name,
            feed_slug=feed.slug,
            feed_url=feed.url,
            feed_kind=feed.kind,
        )
        validate = _validate_html if feed.is_html else _validate_rss
        fetched: FetchResult = self.fetcher.get(
            feed.url, validate=validate, allow_markdown_mirrors=True
        )
        report.route = fetched.route
        report.via = fetched.via
        report.http_status = fetched.status
        report.elapsed = round(fetched.elapsed, 2)
        report.attempts = fetched.attempts
        report.tried = fetched.tried[-6:]

        if not fetched.ok:
            report.status = "error"
            report.error = fetched.error
            LOGGER.warning("[%s] falhou: %s", feed.name, fetched.error)
            return report, []

        parsed = self._parse(feed, fetched)
        report.strategy = parsed.strategy
        items = dedupe_items(parsed.items)
        if self.limit_per_feed:
            items = items[: self.limit_per_feed]

        records = []
        for item in items:
            record = self._build_record(feed, parsed, item, run_id, collected_at, fetched)
            if record is not None:
                records.append(record)

        report.items = len(records)
        report.status = "ok" if records else "empty"
        if not records and parsed.bozo_reason:
            report.error = parsed.bozo_reason
        LOGGER.info(
            "[%s] %s itens via %s:%s", feed.name, len(records), fetched.route, fetched.via
        )
        return report, records

    def _parse(self, feed: Feed, fetched: FetchResult) -> ParsedFeed:
        if fetched.is_markdown:
            return parse_markdown(fetched.text, feed.url)
        if feed.is_html:
            parsed = parse_html(fetched.content, feed.url, summary_limit=self.summary_limit)
            if not parsed.items:
                fallback = parse_rss(fetched.content, feed.url, self.summary_limit)
                if fallback.items:
                    fallback.strategy = "rss-fallback"
                    return fallback
            return parsed
        parsed = parse_rss(fetched.content, feed.url, self.summary_limit)
        if not parsed.items:  # feed virou página HTML
            fallback = parse_html(fetched.content, feed.url, summary_limit=self.summary_limit)
            if fallback.items:
                fallback.strategy = "html-fallback"
                return fallback
        return parsed

    def _build_record(
        self,
        feed: Feed,
        parsed: ParsedFeed,
        item: dict,
        run_id: str,
        collected_at: str,
        fetched: FetchResult,
    ) -> Optional[dict]:
        link = item.get("link", "")
        title = item.get("title", "")
        if not title and not link:
            return None

        published = item.get("published", "")
        if self.max_age_days and published:
            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if published_dt < datetime.now(timezone.utc) - timedelta(days=self.max_age_days):
                    return None
            except ValueError:
                pass

        item_id = make_id(feed.slug, link, item.get("guid", ""), title)
        if item_id in self.seen_ids:
            with self._lock:
                self._skipped_seen += 1
            return None

        record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "collected_at": collected_at,
            # --- identificação do feed (facilita categorizar depois) ---
            "feed_name": feed.name,
            "feed_slug": feed.slug,
            "feed_group": feed.group,
            "feed_section": feed.section,
            "feed_url": feed.url,
            "feed_kind": feed.kind,
            "feed_title": parsed.feed_title,
            # --- notícia ---
            "id": item_id,
            "title": title,
            "link": link,
            "guid": item.get("guid", ""),
            "published": published,
            "published_raw": item.get("published_raw", ""),
            "updated": item.get("updated", ""),
            "summary": item.get("summary", ""),
            "authors": item.get("authors", []),
            "categories": item.get("categories", []),
            "image": item.get("image", ""),
            "language": parsed.language or "pt-BR",
            "source_domain": urlsplit(link).netloc.replace("www.", "") if link else "",
            "fetch_route": fetched.route,
            "fetch_via": fetched.via,
            "parser": parsed.strategy,
        }
        if self.include_content:
            record["content_text"] = item.get("content_text", "")
        return record

    # --------------------------------------------------------------- execução
    def run(self, feeds: Sequence[Feed], dry_run: bool = False) -> RunResult:
        started = datetime.now(timezone.utc)
        run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        collected_at = started.isoformat().replace("+00:00", "Z")
        result = RunResult(
            run_id=run_id,
            started_at=collected_at,
            feeds_total=len(feeds),
        )

        records_by_feed: dict[str, List[dict]] = {}
        reports: dict[str, FeedReport] = {}

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {
                pool.submit(self.collect_feed, feed, run_id, collected_at): feed
                for feed in feeds
            }
            for future in as_completed(futures):
                feed = futures[future]
                key = f"{feed.slug}@{feed.url}"
                try:
                    report, records = future.result()
                except Exception as exc:  # noqa: BLE001 - um feed não derruba a coleta
                    LOGGER.exception("[%s] erro inesperado", feed.name)
                    report = FeedReport(
                        feed_name=feed.name,
                        feed_slug=feed.slug,
                        feed_url=feed.url,
                        feed_kind=feed.kind,
                        status="error",
                        error=f"{type(exc).__name__}: {exc}"[:300],
                    )
                    records = []
                reports[key] = report
                records_by_feed[key] = records

        # mantém a ordem original do rss.txt na saída
        ordered_records: List[dict] = []
        for feed in feeds:
            key = f"{feed.slug}@{feed.url}"
            ordered_records.extend(records_by_feed.get(key, []))
            report = reports.get(key)
            if report:
                result.feeds.append(report)

        result.total_items = len(ordered_records)
        result.feeds_ok = sum(1 for r in result.feeds if r.status == "ok")
        result.feeds_empty = sum(1 for r in result.feeds if r.status == "empty")
        result.feeds_failed = sum(1 for r in result.feeds if r.status == "error")
        result.routes = dict(self.fetcher.route_counters)
        result.proxies = self.fetcher.pool.stats()
        result.skipped_seen = self._skipped_seen

        finished = datetime.now(timezone.utc)
        result.finished_at = finished.isoformat().replace("+00:00", "Z")
        result.duration_seconds = round((finished - started).total_seconds(), 1)

        if not dry_run:
            result.jsonl_path = write_jsonl(
                self.output_dir, started, ordered_records, compress=self.compress
            )
            result.report_path = write_report(result)
            append_index(self.output_dir, result)

        return result


# --------------------------------------------------------------------- saída
def snapshot_paths(output_dir: Path, moment: datetime, compress: bool = False) -> tuple[Path, Path]:
    """``data/2026/news-2026-10-05T000000Z.jsonl`` (+ relatório ``.report.json``)."""
    stamp = moment.strftime("%Y-%m-%dT%H%M%SZ")
    extension = ".jsonl.gz" if compress else ".jsonl"
    folder = Path(output_dir) / moment.strftime("%Y")
    folder.mkdir(parents=True, exist_ok=True)
    jsonl_path = folder / f"news-{stamp}{extension}"
    suffix = 2
    while jsonl_path.exists():  # nunca sobrescreve snapshot existente
        jsonl_path = folder / f"news-{stamp}-{suffix}{extension}"
        suffix += 1
    return jsonl_path, report_path_for(jsonl_path)


def report_path_for(jsonl_path: Path) -> Path:
    name = jsonl_path.name.replace(".jsonl.gz", "").replace(".jsonl", "")
    return jsonl_path.with_name(f"{name}.report.json")


def write_jsonl(
    output_dir: Path, moment: datetime, records: Iterable[dict], compress: bool = False
) -> Path:
    jsonl_path, _ = snapshot_paths(output_dir, moment, compress)
    opener = (
        (lambda: gzip.open(jsonl_path, "wt", encoding="utf-8"))
        if compress
        else (lambda: jsonl_path.open("w", encoding="utf-8"))
    )
    with opener() as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonl_path


def write_report(result: RunResult) -> Path:
    report_path = report_path_for(Path(result.jsonl_path))
    payload = {
        "run_id": result.run_id,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_seconds": result.duration_seconds,
        "jsonl": result.jsonl_path.name if result.jsonl_path else "",
        "schema_version": SCHEMA_VERSION,
        "totals": {
            "feeds": result.feeds_total,
            "ok": result.feeds_ok,
            "empty": result.feeds_empty,
            "failed": result.feeds_failed,
            "items": result.total_items,
            "skipped_seen": result.skipped_seen,
        },
        "routes": result.routes,
        "proxies": result.proxies,
        "feeds": [asdict(feed) for feed in result.feeds],
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report_path


def append_index(output_dir: Path, result: RunResult) -> Path:
    """Histórico append-only de todas as execuções (``data/index.jsonl``)."""
    index_path = Path(output_dir) / "index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_id": result.run_id,
        "collected_at": result.started_at,
        "file": str(result.jsonl_path.relative_to(output_dir)) if result.jsonl_path else "",
        "report": str(result.report_path.relative_to(output_dir)) if result.report_path else "",
        "items": result.total_items,
        "feeds_ok": result.feeds_ok,
        "feeds_empty": result.feeds_empty,
        "feeds_failed": result.feeds_failed,
        "duration_seconds": result.duration_seconds,
        "routes": result.routes,
    }
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return index_path


def load_seen_ids(output_dir: Path, lookback: int) -> set[str]:
    """IDs já salvos nos últimos ``lookback`` snapshots (para ``--skip-seen``)."""
    if lookback <= 0:
        return set()
    files = sorted(
        path
        for path in Path(output_dir).glob("*/news-*")
        if path.name.endswith((".jsonl", ".jsonl.gz"))
    )[-lookback:]
    seen: set[str] = set()
    for path in files:
        opener = (
            (lambda p=path: gzip.open(p, "rt", encoding="utf-8"))
            if path.suffix == ".gz"
            else (lambda p=path: p.open(encoding="utf-8"))
        )
        with opener() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    seen.add(json.loads(line)["id"])
                except (ValueError, KeyError):
                    continue
    return seen


def markdown_summary(result: RunResult, top: int = 15) -> str:
    """Resumo em Markdown para o ``$GITHUB_STEP_SUMMARY``."""
    lines = [
        f"## 📰 Coleta semanal — `{result.run_id}`",
        "",
        f"- **Arquivo:** `{result.jsonl_path.name if result.jsonl_path else '(dry-run)'}`",
        f"- **Notícias:** **{result.total_items}**",
        f"- **Feeds:** {result.feeds_ok} ok · {result.feeds_empty} vazios · "
        f"{result.feeds_failed} com erro (de {result.feeds_total})",
        f"- **Rotas usadas:** {result.routes or '—'}",
        f"- **Proxies:** {result.proxies.get('configured', 0)} configurados "
        f"({result.proxies.get('disabled', 0)} desativados)",
        f"- **Duração:** {result.duration_seconds}s",
        "",
        "### Top feeds",
        "",
        "| Feed | Itens | Rota | Parser |",
        "| --- | ---: | --- | --- |",
    ]
    for report in sorted(result.feeds, key=lambda r: r.items, reverse=True)[:top]:
        lines.append(
            f"| {report.feed_name} | {report.items} | {report.route or '—'} | "
            f"{report.strategy or '—'} |"
        )

    problems = [r for r in result.feeds if r.status != "ok"]
    if problems:
        lines += ["", f"### Feeds sem notícias ({len(problems)})", "", "| Feed | Status | Motivo |", "| --- | --- | --- |"]
        for report in problems:
            reason = (report.error or "sem itens").replace("|", "/")[:120]
            lines.append(f"| {report.feed_name} | {report.status} | {reason} |")
    return "\n".join(lines) + "\n"


def write_step_summary(result: RunResult) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(markdown_summary(result))


def write_annotations(result: RunResult, max_warnings: int = 12) -> None:
    """Emite ::notice/::warning para aparecerem no resumo da execução no GitHub."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    print(
        f"::notice title=Coleta {result.run_id}::{result.total_items} notícias de "
        f"{result.feeds_ok}/{result.feeds_total} feeds "
        f"({result.feeds_empty} vazios, {result.feeds_failed} com erro) em "
        f"{result.duration_seconds}s | rotas: {result.routes}",
        flush=True,
    )
    problems = [r for r in result.feeds if r.status != "ok"]
    for report in problems[:max_warnings]:
        motivo = (report.error or "sem itens").replace("\n", " ")[:160]
        tentativas = " ; ".join(report.tried[:4])
        print(
            f"::warning title=Feed sem notícias: {report.feed_name}::"
            f"{report.status} — {motivo} ({report.feed_url}) | tentativas: {tentativas}",
            flush=True,
        )
    if len(problems) > max_warnings:
        print(
            f"::notice::mais {len(problems) - max_warnings} feeds sem notícias "
            "(lista completa no .report.json e no resumo do job)",
            flush=True,
        )


def write_github_output(result: RunResult) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    values = {
        "run_id": result.run_id,
        "items": str(result.total_items),
        "feeds_ok": str(result.feeds_ok),
        "feeds_failed": str(result.feeds_failed),
        "jsonl": str(result.jsonl_path) if result.jsonl_path else "",
        "report": str(result.report_path) if result.report_path else "",
    }
    with open(output_file, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")

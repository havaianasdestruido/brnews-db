#!/usr/bin/env python3
"""Coleta todas as notícias dos feeds de ``rss.txt`` e grava um JSONL novo.

Exemplos:

    # coleta completa (o que o GitHub Actions roda toda segunda 00:00 UTC)
    python scripts/collect_news.py

    # teste rápido, sem escrever arquivos
    python scripts/collect_news.py --max-feeds 5 --limit-per-feed 3 --dry-run -v

    # usando proxies (secret, arquivo ou CLI)
    PROXY_LIST="http://user:pass@host:3128, socks5://host:1080" \
        python scripts/collect_news.py
    python scripts/collect_news.py --proxy-file config/proxies.txt
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from brnews.collector import (  # noqa: E402
    Collector,
    load_seen_ids,
    markdown_summary,
    write_annotations,
    write_github_output,
    write_step_summary,
)
from brnews.feedlist import load_feeds  # noqa: E402
from brnews.fetcher import DEFAULT_ROUTE_ORDER, Fetcher, load_proxies  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Coletor semanal de notícias (RSS/Atom + páginas HTML).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--feeds-file", default=str(REPO_ROOT / "rss.txt"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--workers", type=int, default=8, help="downloads em paralelo")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--attempts", type=int, default=2, help="tentativas por rota")
    parser.add_argument("--limit-per-feed", type=int, default=0, help="0 = sem limite")
    parser.add_argument("--max-feeds", type=int, default=0, help="0 = todos (debug)")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=0,
        help="descarta notícias mais antigas que N dias (0 = manter tudo)",
    )
    parser.add_argument("--summary-limit", type=int, default=2000)
    parser.add_argument("--no-content", action="store_true", help="não salvar content_text")
    parser.add_argument(
        "--gzip", action="store_true", help="grava news-*.jsonl.gz (economiza espaço no repo)"
    )
    parser.add_argument(
        "--skip-seen",
        type=int,
        default=0,
        help="ignora itens já presentes nos últimos N snapshots (0 = desligado)",
    )
    parser.add_argument("--min-interval", type=float, default=1.0, help="segundos por host")

    group = parser.add_argument_group("proxies")
    group.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="proxy (repetível): http://host:3128, socks5://user:pass@host:1080, host:porta",
    )
    group.add_argument(
        "--proxy-file",
        action="append",
        default=[str(REPO_ROOT / "config" / "proxies.txt")],
        help="arquivo com um proxy por linha",
    )
    group.add_argument(
        "--route-order",
        default=",".join(DEFAULT_ROUTE_ORDER),
        help="ordem de tentativa: direct,proxy,mirror",
    )
    group.add_argument(
        "--proxies-only",
        action="store_true",
        help="atalho para --route-order proxy,mirror (nunca sai pelo IP do runner)",
    )
    group.add_argument("--no-mirrors", action="store_true", help="desliga espelhos públicos")
    group.add_argument(
        "--max-proxies-per-url", type=int, default=3, help="quantos proxies testar por URL"
    )
    group.add_argument("--insecure", action="store_true", help="não validar certificado TLS")

    parser.add_argument("--dry-run", action="store_true", help="não escreve arquivos")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose > 1 else logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    feeds = load_feeds(args.feeds_file)
    if args.max_feeds:
        feeds = feeds[: args.max_feeds]
    if not feeds:
        print(f"nenhum feed válido em {args.feeds_file}", file=sys.stderr)
        return 2

    proxies = load_proxies(explicit=args.proxy, files=args.proxy_file)
    route_order = (
        ["proxy", "mirror"]
        if args.proxies_only
        else [part.strip() for part in args.route_order.split(",") if part.strip()]
    )
    if args.no_mirrors:
        route_order = [route for route in route_order if route != "mirror"]
    if not proxies:
        route_order = [route for route in route_order if route != "proxy"]
        if not route_order:
            route_order = ["direct"]

    fetcher = Fetcher(
        proxies=proxies,
        route_order=route_order,
        timeout=args.timeout,
        attempts_per_route=args.attempts,
        max_proxies_per_url=args.max_proxies_per_url,
        min_interval_per_host=args.min_interval,
        verify_tls=not args.insecure,
        mirrors=None if not args.no_mirrors else [],
    )

    output_dir = Path(args.output_dir)
    collector = Collector(
        fetcher=fetcher,
        output_dir=output_dir,
        limit_per_feed=args.limit_per_feed,
        max_age_days=args.max_age_days,
        summary_limit=args.summary_limit,
        workers=args.workers,
        include_content=not args.no_content,
        compress=args.gzip,
        seen_ids=load_seen_ids(output_dir, args.skip_seen),
    )

    print(
        f"coletando {len(feeds)} feeds | rotas: {','.join(route_order)} | "
        f"proxies: {len(proxies)}",
        flush=True,
    )
    result = collector.run(feeds, dry_run=args.dry_run)

    print(markdown_summary(result, top=10))
    write_step_summary(result)
    write_github_output(result)
    write_annotations(result)

    if result.total_items == 0:
        print("nenhuma notícia coletada", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

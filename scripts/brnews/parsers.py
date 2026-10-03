"""Normalização do conteúdo baixado em notícias (dicts prontos p/ JSONL)."""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("brnews.parsers")

_WS_RE = re.compile(r"\s+")
_MD_LINK_RE = re.compile(r"\[([^\]\n]{15,300})\]\((https?://[^\s)]+)\)")
_TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|igshid|mc_cid|mc_eid|xtor|cmpid|ref_src|spm$)", re.IGNORECASE
)
_BAD_PATH_RE = re.compile(
    r"/(tag|tags|autor|autores|author|categoria|category|busca|search|assine|assinatura|"
    r"newsletter|login|cadastro|contato|privacidade|termos|rss|feed|podcast/?$)(/|$)",
    re.IGNORECASE,
)
_BLOCK_MARKERS = (
    "just a moment",
    "attention required",
    "cf-browser-verification",
    "verifique que você não é um robô",
    "access denied",
    "request blocked",
    "enable javascript and cookies",
    "captcha-delivery",
)


@dataclass
class ParsedFeed:
    """Saída da normalização de um feed."""

    items: List[dict] = field(default_factory=list)
    feed_title: str = ""
    language: str = ""
    bozo: bool = False
    bozo_reason: str = ""
    strategy: str = ""


# --------------------------------------------------------------------- texto
def clean_text(value: Optional[str], limit: int = 0) -> str:
    """Remove HTML/entidades e normaliza espaços."""
    if not value:
        return ""
    text = value
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = _WS_RE.sub(" ", text.replace("\xa0", " ")).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def canonical_url(url: str, base: str = "") -> str:
    """Resolve relativos e remove parâmetros de rastreamento/fragmentos."""
    if not url:
        return ""
    url = url.strip()
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return ""
    query = "&".join(
        piece
        for piece in parts.query.split("&")
        if piece and not _TRACKING_PARAMS.match(piece.split("=", 1)[0])
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))


def looks_blocked(content: bytes, text: str = "") -> bool:
    """Heurística para detectar página de bloqueio (Cloudflare, WAF, ...)."""
    sample = (text or content[:4000].decode("utf-8", "replace")).lower()
    return any(marker in sample for marker in _BLOCK_MARKERS)


def make_id(feed_slug: str, link: str, guid: str, title: str) -> str:
    base = guid or link or title
    digest = hashlib.sha1(f"{feed_slug}|{base}".encode("utf-8")).hexdigest()
    return digest[:16]


def to_iso(value) -> str:
    """struct_time/datetime/str -> ISO-8601 UTC (ou ``""``)."""
    if not value:
        return ""
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (tuple, list)) and len(value) >= 9:
            dt = datetime.fromtimestamp(calendar.timegm(tuple(value)[:9]), tz=timezone.utc)
        else:
            from email.utils import parsedate_to_datetime

            text = str(value).strip()
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:  # noqa: BLE001 - data inválida não derruba a coleta
        return ""


# ----------------------------------------------------------------- RSS/Atom
def _entry_image(entry) -> str:
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key) or []
        if media and isinstance(media, list):
            url = media[0].get("url")
            if url:
                return url
    for enclosure in entry.get("links", []) or []:
        if enclosure.get("rel") == "enclosure" and str(
            enclosure.get("type", "")
        ).startswith("image/"):
            return enclosure.get("href", "")
    for block in entry.get("content", []) or []:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)', block.get("value", "") or "")
        if match:
            return match.group(1)
    summary = entry.get("summary", "") or ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', summary)
    return match.group(1) if match else ""


def _entry_content(entry) -> str:
    blocks = entry.get("content") or []
    if blocks:
        return blocks[0].get("value", "") or ""
    return entry.get("summary", "") or ""


def parse_rss(content: bytes, feed_url: str, summary_limit: int = 2000) -> ParsedFeed:
    """Interpreta RSS/Atom/RDF com ``feedparser``."""
    parsed = feedparser.parse(content)
    result = ParsedFeed(
        feed_title=clean_text(parsed.feed.get("title", "")),
        language=(parsed.feed.get("language") or "").strip(),
        bozo=bool(parsed.get("bozo")),
        bozo_reason=str(parsed.get("bozo_exception", ""))[:200],
        strategy="rss",
    )

    for entry in parsed.entries:
        link = canonical_url(entry.get("link") or "", feed_url)
        if not link:
            for candidate in entry.get("links", []) or []:
                if candidate.get("rel") in (None, "alternate") and candidate.get("href"):
                    link = canonical_url(candidate["href"], feed_url)
                    break
        title = clean_text(entry.get("title", ""))
        if not title and not link:
            continue

        raw_content = _entry_content(entry)
        item = {
            "title": title,
            "link": link,
            "guid": (entry.get("id") or entry.get("guid") or "").strip(),
            "published": to_iso(entry.get("published_parsed") or entry.get("published")),
            "published_raw": (entry.get("published") or entry.get("updated") or "").strip(),
            "updated": to_iso(entry.get("updated_parsed") or entry.get("updated")),
            "summary": clean_text(entry.get("summary", ""), summary_limit),
            "content_text": clean_text(raw_content, summary_limit * 4),
            "authors": [
                clean_text(a.get("name", ""))
                for a in (entry.get("authors") or [])
                if a.get("name")
            ]
            or ([clean_text(entry.get("author", ""))] if entry.get("author") else []),
            "categories": [
                clean_text(tag.get("term", ""))
                for tag in (entry.get("tags") or [])
                if tag.get("term")
            ],
            "image": canonical_url(_entry_image(entry), feed_url),
        }
        result.items.append(item)

    return result


# ---------------------------------------------------------------------- HTML
def _jsonld_items(soup: BeautifulSoup, base_url: str) -> List[dict]:
    items: List[dict] = []

    def handle(node) -> None:
        if isinstance(node, list):
            for child in node:
                handle(child)
            return
        if not isinstance(node, dict):
            return
        node_type = node.get("@type") or ""
        types = {node_type} if isinstance(node_type, str) else set(node_type)
        if {"NewsArticle", "Article", "ReportageNewsArticle", "BlogPosting"} & types:
            url = node.get("url") or node.get("mainEntityOfPage")
            if isinstance(url, dict):
                url = url.get("@id", "")
            link = canonical_url(str(url or ""), base_url)
            title = clean_text(str(node.get("headline") or node.get("name") or ""))
            if link and title:
                image = node.get("image")
                if isinstance(image, dict):
                    image = image.get("url", "")
                if isinstance(image, list) and image:
                    image = image[0] if isinstance(image[0], str) else image[0].get("url", "")
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "published": to_iso(node.get("datePublished")),
                        "published_raw": str(node.get("datePublished") or ""),
                        "updated": to_iso(node.get("dateModified")),
                        "summary": clean_text(str(node.get("description") or "")),
                        "image": canonical_url(str(image or ""), base_url),
                    }
                )
        for key in ("itemListElement", "@graph", "mainEntity", "hasPart"):
            if key in node:
                handle(node[key])
        if "item" in node and isinstance(node["item"], (dict, list)):
            handle(node["item"])

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            handle(json.loads(raw))
        except (ValueError, TypeError):
            continue
    return items


def _normalize_host(host: str) -> str:
    host = (host or "").split(":")[0].strip().lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def same_site(link_host: str, base_host: str) -> bool:
    """Mesmo domínio ou subdomínio dele — comparação por rótulo, não substring.

    ``ale.com.br`` **não** é parte de ``ovale.com.br``; já
    ``g1.globo.com`` é subdomínio de ``globo.com``.
    """
    link_host = _normalize_host(link_host)
    base_host = _normalize_host(base_host)
    if not link_host or not base_host:
        return True
    return (
        link_host == base_host
        or link_host.endswith("." + base_host)
        or base_host.endswith("." + link_host)
    )


def _looks_like_article(link: str, title: str, base_host: str) -> bool:
    if not link or len(title) < 20:
        return False
    parts = urlsplit(link)
    if not same_site(parts.netloc, base_host):
        return False
    path = parts.path or "/"
    if path in ("", "/") or _BAD_PATH_RE.search(path):
        return False
    if len(title.split()) < 4:
        return False
    # artigos costumam ter slug longo ou data no caminho
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    return len(slug) >= 12 or bool(re.search(r"/20\d{2}/", path)) or bool(
        re.search(r"\d{4,}", slug)
    )


def parse_html(
    content: bytes,
    page_url: str,
    max_items: int = 60,
    summary_limit: int = 2000,
) -> ParsedFeed:
    """Extrai manchetes de uma página HTML (feeds marcados ``| HTML``)."""
    soup = BeautifulSoup(content, "lxml")
    base_host = urlsplit(page_url).netloc.replace("www.", "")
    result = ParsedFeed(
        feed_title=clean_text(soup.title.get_text() if soup.title else ""),
        language=(soup.html.get("lang") if soup.html and soup.html.has_attr("lang") else ""),
        strategy="html",
    )

    found: List[dict] = []
    seen: set[str] = set()
    strategies: List[str] = []

    for item in _jsonld_items(soup, page_url):
        if item["link"] not in seen:
            seen.add(item["link"])
            found.append(item)
    if found:
        strategies.append("jsonld")

    # <article> / cards comuns
    before_cards = len(found)
    containers = soup.find_all(["article", "li", "div"], limit=4000)
    for container in containers:
        classes = " ".join(container.get("class") or []).lower()
        if container.name != "article" and not re.search(
            r"(card|post|noticia|notícia|materia|matéria|headline|chamada|story|teaser|feed-item)",
            classes,
        ):
            continue
        anchor = container.find("a", href=True)
        if not anchor:
            continue
        heading = container.find(["h1", "h2", "h3", "h4"])
        title = clean_text(
            (heading.get_text(" ") if heading else "")
            or anchor.get("title")
            or anchor.get_text(" ")
        )
        link = canonical_url(anchor["href"], page_url)
        if not _looks_like_article(link, title, base_host) or link in seen:
            continue
        time_tag = container.find("time")
        published = ""
        if time_tag is not None:
            published = to_iso(time_tag.get("datetime") or time_tag.get_text(" ").strip())
        paragraph = container.find("p")
        seen.add(link)
        found.append(
            {
                "title": title,
                "link": link,
                "published": published,
                "published_raw": (time_tag.get("datetime") if time_tag else "") or "",
                "summary": clean_text(paragraph.get_text(" ") if paragraph else "", summary_limit),
            }
        )

    if len(found) > before_cards:
        strategies.append("cards")

    # Último recurso: qualquer <a> que pareça manchete
    if len(found) < 5:
        before_anchors = len(found)
        for anchor in soup.find_all("a", href=True, limit=4000):
            title = clean_text(anchor.get_text(" ") or anchor.get("title") or "")
            link = canonical_url(anchor["href"], page_url)
            if not _looks_like_article(link, title, base_host) or link in seen:
                continue
            seen.add(link)
            found.append({"title": title, "link": link})
        if len(found) > before_anchors:
            strategies.append("anchors")

    result.strategy = "html:" + ("+".join(strategies) if strategies else "vazio")

    result.items = [
        {
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "guid": "",
            "published": item.get("published", ""),
            "published_raw": item.get("published_raw", ""),
            "updated": item.get("updated", ""),
            "summary": item.get("summary", ""),
            "content_text": "",
            "authors": [],
            "categories": [],
            "image": item.get("image", ""),
        }
        for item in found[:max_items]
    ]
    return result


def parse_markdown(text: str, page_url: str, max_items: int = 60) -> ParsedFeed:
    """Espelhos como r.jina.ai devolvem Markdown: extrai ``[título](link)``."""
    result = ParsedFeed(strategy="markdown")
    seen: set[str] = set()
    base_host = urlsplit(page_url).netloc.replace("www.", "")
    for match in _MD_LINK_RE.finditer(text):
        title = clean_text(match.group(1))
        link = canonical_url(match.group(2), page_url)
        if not _looks_like_article(link, title, base_host) or link in seen:
            continue
        seen.add(link)
        result.items.append(
            {
                "title": title,
                "link": link,
                "guid": "",
                "published": "",
                "published_raw": "",
                "updated": "",
                "summary": "",
                "content_text": "",
                "authors": [],
                "categories": [],
                "image": "",
            }
        )
        if len(result.items) >= max_items:
            break
    return result


def dedupe_items(items: Iterable[dict]) -> List[dict]:
    """Remove repetições pelo par (link, título) dentro do mesmo feed."""
    unique: List[dict] = []
    seen: set[str] = set()
    for item in items:
        key = (item.get("link") or "").lower() or (item.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique

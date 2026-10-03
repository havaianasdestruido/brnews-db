"""Leitura e normalização do arquivo de feeds (``rss.txt``).

Formato de cada linha:

    Nome do feed|https://exemplo.com/feed
    Nome do feed|https://exemplo.com/noticias/ | HTML

* O primeiro ``|`` separa o nome da URL.
* Um sufixo opcional ``| HTML`` marca páginas que não são RSS/Atom e
  precisam de extração de links (scraping leve).
* Linhas vazias e linhas iniciadas por ``#`` são ignoradas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List

KIND_RSS = "rss"
KIND_HTML = "html"

_FLAG_RE = re.compile(r"\|\s*(html|rss|atom)\s*$", re.IGNORECASE)
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """``"Metrópoles - Coluna Juris"`` -> ``"metropoles-coluna-juris"``."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _SLUG_STRIP_RE.sub("-", ascii_only).strip("-") or "feed"


@dataclass(frozen=True)
class Feed:
    """Um feed da lista, já normalizado."""

    name: str
    url: str
    kind: str = KIND_RSS
    line_number: int = 0
    tags: List[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    @property
    def group(self) -> str:
        """Veículo/organização: ``"Metrópoles - Coluna Juris"`` -> ``"Metrópoles"``."""
        for separator in (" - ", " – ", " — "):
            if separator in self.name:
                return self.name.split(separator, 1)[0].strip()
        return self.name.strip()

    @property
    def section(self) -> str:
        """Editoria/seção: ``"Metrópoles - Coluna Juris"`` -> ``"Coluna Juris"``."""
        for separator in (" - ", " – ", " — "):
            if separator in self.name:
                return self.name.split(separator, 1)[1].strip()
        return ""

    @property
    def is_html(self) -> bool:
        return self.kind == KIND_HTML

    def as_dict(self) -> dict:
        return {
            "feed_name": self.name,
            "feed_slug": self.slug,
            "feed_group": self.group,
            "feed_section": self.section,
            "feed_url": self.url,
            "feed_kind": self.kind,
        }


def parse_line(line: str, line_number: int = 0) -> Feed | None:
    """Converte uma linha de ``rss.txt`` em :class:`Feed` (ou ``None``)."""
    raw = line.strip().lstrip("\ufeff")
    if not raw or raw.startswith("#"):
        return None

    if "|" not in raw:
        # Linha só com URL: usa o domínio como nome.
        url = raw.strip()
        if not url.lower().startswith(("http://", "https://")):
            return None
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        return Feed(name=host, url=url, kind=KIND_RSS, line_number=line_number)

    name, remainder = raw.split("|", 1)
    name = name.strip()
    remainder = remainder.strip()

    kind = KIND_RSS
    flag_match = _FLAG_RE.search(remainder)
    if flag_match:
        flag = flag_match.group(1).lower()
        kind = KIND_HTML if flag == "html" else KIND_RSS
        remainder = remainder[: flag_match.start()].strip()

    url = remainder.strip().strip("|").strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    if not name:
        name = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]

    return Feed(name=name, url=url, kind=kind, line_number=line_number)


def iter_feeds(lines: Iterable[str]) -> Iterator[Feed]:
    for number, line in enumerate(lines, start=1):
        feed = parse_line(line, number)
        if feed is not None:
            yield feed


def load_feeds(path: str | Path, drop_duplicates: bool = True) -> List[Feed]:
    """Carrega os feeds do arquivo, removendo pares (nome, url) repetidos."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    feeds: List[Feed] = []
    seen: set[tuple[str, str]] = set()
    for feed in iter_feeds(text.splitlines()):
        key = (feed.slug, feed.url.rstrip("/").lower())
        if drop_duplicates and key in seen:
            continue
        seen.add(key)
        feeds.append(feed)
    return feeds

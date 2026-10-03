"""Download HTTP com suporte a proxies rotativos e espelhos públicos.

Muitos portais brasileiros bloqueiam (403/429/Cloudflare) os IPs de
datacenter usados pelos runners do GitHub Actions. Este módulo tenta, em
ordem, várias "rotas" até conseguir um conteúdo válido:

1. ``direct``  – requisição normal a partir do runner;
2. ``proxy``   – proxies HTTP/HTTPS/SOCKS5 configurados (secret/arquivo),
   usados em rodízio e com desativação temporária dos que falham;
3. ``mirror``  – espelhos públicos de leitura (r.jina.ai, allorigins,
   codetabs, ...) que buscam a URL por nós.

A ordem é configurável (``--route-order`` / ``BRNEWS_ROUTE_ORDER``).
Cada rota só é aceita se o conteúdo passar pelo ``validate`` recebido
(ex.: "o XML tem pelo menos uma notícia?"), evitando salvar páginas de
erro devolvidas por um proxy ruim.
"""

from __future__ import annotations

import itertools
import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence
from urllib.parse import quote, urlsplit

import requests

LOGGER = logging.getLogger("brnews.fetcher")

DEFAULT_USER_AGENTS = [
    # Intercalado de propósito: se um navegador leva 403, a tentativa seguinte
    # vai como leitor de RSS (muitos portais liberam Feedly/Inoreader).
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Feedly/1.0 (+https://feedly.com/fetcher.html; like FeedFetcher-Google)",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
    "Mozilla/5.0 (compatible; Inoreader/1.0; +https://www.inoreader.com/feed-fetcher)",
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Tiny Tiny RSS/23.04 (https://tt-rss.org/)",
]

# Espelhos públicos: {url} = URL crua, {qurl} = URL percent-encoded.
# ``raw`` indica se o espelho devolve o corpo original (necessário p/ XML).
DEFAULT_MIRRORS: List[dict] = [
    {"name": "allorigins", "template": "https://api.allorigins.win/raw?url={qurl}", "raw": True},
    {"name": "codetabs", "template": "https://api.codetabs.com/v1/proxy/?quest={qurl}", "raw": True},
    {"name": "corsproxy", "template": "https://corsproxy.io/?url={qurl}", "raw": True},
    {"name": "whateverorigin", "template": "https://api.cors.lol/?url={qurl}", "raw": True},
    {"name": "jina", "template": "https://r.jina.ai/{url}", "raw": False},
]

ROUTE_DIRECT = "direct"
ROUTE_PROXY = "proxy"
ROUTE_MIRROR = "mirror"
DEFAULT_ROUTE_ORDER = (ROUTE_DIRECT, ROUTE_PROXY, ROUTE_MIRROR)

_CREDENTIALS_RE = re.compile(r"//[^/@]+@")
_SPLIT_RE = re.compile(r"[\s,;]+")


def mask(url: str) -> str:
    """Esconde ``user:senha`` de proxies antes de logar/salvar."""
    return _CREDENTIALS_RE.sub("//***@", url or "")


def normalize_proxy(entry: str) -> Optional[str]:
    """Aceita ``host:porta``, ``user:pass@host:porta`` ou com esquema."""
    entry = (entry or "").strip()
    if not entry or entry.startswith("#"):
        return None
    if "://" not in entry:
        entry = "http://" + entry
    parsed = urlsplit(entry)
    if not parsed.hostname or parsed.scheme not in {
        "http",
        "https",
        "socks4",
        "socks5",
        "socks5h",
    }:
        return None
    return entry


def load_proxies(
    explicit: Sequence[str] = (),
    files: Sequence[str | Path] = (),
    env_vars: Sequence[str] = ("BRNEWS_PROXIES", "PROXY_LIST", "PROXIES"),
    use_standard_env: bool = True,
) -> List[str]:
    """Junta proxies de CLI, arquivos e variáveis de ambiente/secrets."""
    candidates: List[str] = []
    candidates.extend(explicit)

    for var in env_vars:
        value = os.environ.get(var)
        if value:
            candidates.extend(_SPLIT_RE.split(value.strip()))

    for file_path in files:
        path = Path(file_path)
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                candidates.append(line.strip())

    if use_standard_env:
        for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"):
            value = os.environ.get(var)
            if value:
                candidates.append(value.strip())

    proxies: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_proxy(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            proxies.append(normalized)
    return proxies


@dataclass
class FetchResult:
    """Resultado de um download (com a rota que funcionou)."""

    url: str
    ok: bool = False
    status: Optional[int] = None
    content: bytes = b""
    final_url: str = ""
    route: str = ""
    via: str = ""
    elapsed: float = 0.0
    attempts: int = 0
    error: str = ""
    is_markdown: bool = False
    tried: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        if not self.content:
            return ""
        for encoding in ("utf-8", "latin-1"):
            try:
                return self.content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return self.content.decode("utf-8", errors="replace")


class ProxyPool:
    """Rodízio thread-safe de proxies com cooldown para os que falham."""

    def __init__(self, proxies: Iterable[str], max_failures: int = 3, cooldown: float = 900.0):
        self._proxies = list(dict.fromkeys(p for p in proxies if p))
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._blocked_until: dict[str, float] = {}
        self.max_failures = max_failures
        self.cooldown = cooldown

    def __bool__(self) -> bool:
        return bool(self._proxies)

    def __len__(self) -> int:
        return len(self._proxies)

    @property
    def all(self) -> List[str]:
        return list(self._proxies)

    def take(self, count: int) -> List[str]:
        """Devolve até ``count`` proxies ativos, em rodízio."""
        if not self._cycle:
            return []
        now = time.time()
        chosen: List[str] = []
        with self._lock:
            for _ in range(len(self._proxies)):
                proxy = next(self._cycle)
                if self._blocked_until.get(proxy, 0) > now:
                    continue
                if proxy not in chosen:
                    chosen.append(proxy)
                if len(chosen) >= count:
                    break
        return chosen

    def report(self, proxy: str, ok: bool) -> None:
        with self._lock:
            if ok:
                self._failures.pop(proxy, None)
                self._blocked_until.pop(proxy, None)
                return
            failures = self._failures.get(proxy, 0) + 1
            self._failures[proxy] = failures
            if failures >= self.max_failures:
                self._blocked_until[proxy] = time.time() + self.cooldown
                LOGGER.warning(
                    "proxy %s desativado por %.0fs após %d falhas",
                    mask(proxy),
                    self.cooldown,
                    failures,
                )

    def stats(self) -> dict:
        now = time.time()
        with self._lock:
            return {
                "configured": len(self._proxies),
                "disabled": sum(1 for until in self._blocked_until.values() if until > now),
            }


class Fetcher:
    """Cliente HTTP com failover direto -> proxy -> espelho público."""

    def __init__(
        self,
        proxies: Sequence[str] = (),
        mirrors: Optional[Sequence[dict]] = None,
        route_order: Sequence[str] = DEFAULT_ROUTE_ORDER,
        timeout: float = 30.0,
        attempts_per_route: int = 2,
        max_proxies_per_url: int = 3,
        backoff: float = 1.5,
        min_interval_per_host: float = 1.0,
        user_agents: Sequence[str] = tuple(DEFAULT_USER_AGENTS),
        verify_tls: bool = True,
    ):
        self.pool = ProxyPool(proxies)
        self.mirrors = list(mirrors if mirrors is not None else DEFAULT_MIRRORS)
        self.route_order = [r for r in route_order if r in DEFAULT_ROUTE_ORDER] or list(
            DEFAULT_ROUTE_ORDER
        )
        self.timeout = timeout
        self.attempts_per_route = max(1, attempts_per_route)
        self.max_proxies_per_url = max(1, max_proxies_per_url)
        self.backoff = backoff
        self.min_interval_per_host = min_interval_per_host
        self.user_agents = list(user_agents) or list(DEFAULT_USER_AGENTS)
        self.verify_tls = verify_tls

        self._local = threading.local()
        self._host_lock = threading.Lock()
        self._host_last_hit: dict[str, float] = {}
        self._counters_lock = threading.Lock()
        self.route_counters: dict[str, int] = {}

    # ------------------------------------------------------------------ utils
    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.trust_env = False  # proxies são controlados por nós
            self._local.session = session
        return session

    def _headers(self, extra: Optional[dict] = None, attempt: int = 0, url: str = "") -> dict:
        # Alterna o User-Agent a cada tentativa (browser -> leitor de RSS -> ...)
        user_agent = self.user_agents[attempt % len(self.user_agents)]
        headers = {
            "User-Agent": user_agent,
            "Accept": (
                "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
                "text/html;q=0.8, */*;q=0.7"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if url:
            parts = urlsplit(url)
            if parts.scheme and parts.netloc:
                headers["Referer"] = f"{parts.scheme}://{parts.netloc}/"
        if extra:
            headers.update(extra)
        return headers

    def _respect_host_delay(self, url: str) -> None:
        if self.min_interval_per_host <= 0:
            return
        host = urlsplit(url).netloc
        while True:
            with self._host_lock:
                now = time.monotonic()
                last = self._host_last_hit.get(host, 0.0)
                wait = self.min_interval_per_host - (now - last)
                if wait <= 0:
                    self._host_last_hit[host] = now
                    return
            time.sleep(min(wait, self.min_interval_per_host))

    def _count(self, route: str) -> None:
        with self._counters_lock:
            self.route_counters[route] = self.route_counters.get(route, 0) + 1

    def _request(
        self,
        url: str,
        proxy: Optional[str],
        extra_headers: Optional[dict] = None,
        attempt: int = 0,
    ):
        proxies = {"http": proxy, "https": proxy} if proxy else None
        self._respect_host_delay(url)
        return self.session.get(
            url,
            headers=self._headers(extra_headers, attempt=attempt, url=url),
            timeout=self.timeout,
            proxies=proxies,
            allow_redirects=True,
            verify=self.verify_tls,
        )

    # ------------------------------------------------------------------- main
    def get(
        self,
        url: str,
        validate: Optional[Callable[[bytes, str], bool]] = None,
        allow_markdown_mirrors: bool = False,
    ) -> FetchResult:
        """Baixa ``url`` tentando todas as rotas até ``validate`` aprovar."""
        started = time.monotonic()
        result = FetchResult(url=url)
        last_error = ""

        for route in self.route_order:
            targets: List[tuple[str, str, Optional[str], Optional[dict]]] = []
            if route == ROUTE_DIRECT:
                targets.append((ROUTE_DIRECT, "direct", None, None))
            elif route == ROUTE_PROXY:
                for proxy in self.pool.take(self.max_proxies_per_url):
                    targets.append((ROUTE_PROXY, proxy, proxy, None))
            elif route == ROUTE_MIRROR:
                for mirror in self.mirrors:
                    if not mirror.get("raw", True) and not allow_markdown_mirrors:
                        continue
                    targets.append((ROUTE_MIRROR, mirror["name"], None, mirror))

            for route_name, label, proxy, mirror in targets:
                # espelho público: uma tentativa só (ou funciona, ou passa adiante)
                max_attempts = 1 if route_name == ROUTE_MIRROR else self.attempts_per_route
                target_url = url
                if mirror is not None:
                    target_url = mirror["template"].format(
                        url=url, qurl=quote(url, safe="")
                    )

                for attempt in range(1, max_attempts + 1):
                    result.attempts += 1
                    tried_label = f"{route_name}:{mask(label)}"
                    try:
                        response = self._request(
                            target_url, proxy, attempt=result.attempts - 1
                        )
                        status = response.status_code
                        content = response.content or b""
                        if status >= 400 or not content:
                            last_error = f"HTTP {status}"
                            raise requests.RequestException(last_error)

                        is_markdown = bool(mirror) and not mirror.get("raw", True)
                        if validate is not None and not validate(content, response.text):
                            last_error = "conteúdo inválido/bloqueado"
                            raise requests.RequestException(last_error)

                        if proxy:
                            self.pool.report(proxy, True)
                        self._count(route_name)
                        result.ok = True
                        result.status = status
                        result.content = content
                        result.final_url = response.url
                        result.route = route_name
                        result.via = mask(label)
                        result.is_markdown = is_markdown
                        result.elapsed = time.monotonic() - started
                        result.tried.append(tried_label)
                        return result
                    except Exception as exc:  # noqa: BLE001 - failover genérico
                        last_error = f"{type(exc).__name__}: {exc}"[:300]
                        if proxy:
                            self.pool.report(proxy, False)
                        result.tried.append(f"{tried_label} ({last_error[:80]})")
                        LOGGER.debug("falha %s em %s: %s", tried_label, url, last_error)
                        if attempt < max_attempts:
                            time.sleep(self.backoff * attempt + random.uniform(0, 0.4))

        result.error = last_error or "nenhuma rota disponível"
        result.elapsed = time.monotonic() - started
        self._count("failed")
        return result

"""Testes offline do coletor (servidor HTTP local, sem internet)."""

from __future__ import annotations

import json
import sys
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import collect_news  # noqa: E402
from brnews.collector import Collector, load_seen_ids  # noqa: E402
from brnews.feedlist import Feed, load_feeds, parse_line, slugify  # noqa: E402
from brnews.fetcher import Fetcher, ProxyPool, load_proxies, mask, normalize_proxy  # noqa: E402
from brnews.parsers import canonical_url, parse_html, parse_markdown, parse_rss, same_site  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silencia o servidor de teste
        pass


class LocalServer:
    """Servidor HTTP servindo tests/fixtures em 127.0.0.1."""

    def __init__(self, directory: Path):
        handler = partial(QuietHandler, directory=str(directory))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "LocalServer":
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}/{path.lstrip('/')}"


class FeedListTests(unittest.TestCase):
    def test_parse_rss_line(self):
        feed = parse_line("Metrópoles - Coluna Juris|https://www.metropoles.com/colunas/juris/feed")
        self.assertEqual(feed.name, "Metrópoles - Coluna Juris")
        self.assertEqual(feed.kind, "rss")
        self.assertEqual(feed.slug, "metropoles-coluna-juris")
        self.assertEqual(feed.group, "Metrópoles")
        self.assertEqual(feed.section, "Coluna Juris")

    def test_parse_html_line(self):
        feed = parse_line("Alesp|https://www.al.sp.gov.br/noticias/ | HTML")
        self.assertEqual(feed.url, "https://www.al.sp.gov.br/noticias/")
        self.assertEqual(feed.kind, "html")
        self.assertTrue(feed.is_html)

    def test_ignores_comments_and_blanks(self):
        self.assertIsNone(parse_line("# comentário"))
        self.assertIsNone(parse_line("   "))
        self.assertIsNone(parse_line("Sem url|"))

    def test_repo_feed_file_loads(self):
        feeds = load_feeds(REPO_ROOT / "rss.txt")
        self.assertGreater(len(feeds), 50)
        self.assertTrue(all(f.url.startswith("http") for f in feeds))
        self.assertTrue(any(f.is_html for f in feeds))
        self.assertEqual(len({(f.slug, f.url) for f in feeds}), len(feeds))

    def test_slugify(self):
        self.assertEqual(slugify("Folha de S.Paulo - Poder"), "folha-de-s-paulo-poder")


class ProxyTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_proxy("1.2.3.4:8080"), "http://1.2.3.4:8080")
        self.assertEqual(normalize_proxy("socks5://a:b@h:1080"), "socks5://a:b@h:1080")
        self.assertIsNone(normalize_proxy("# comentário"))
        self.assertIsNone(normalize_proxy("ftp://h:21"))

    def test_mask_credentials(self):
        self.assertEqual(mask("http://user:senha@h:3128"), "http://***@h:3128")

    def test_load_from_env_and_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "proxies.txt"
            path.write_text("# lista\nhttp://a:3128\n\nb:8080\n", encoding="utf-8")
            proxies = load_proxies(
                explicit=["socks5://c:1080"],
                files=[path],
                env_vars=(),
                use_standard_env=False,
            )
        self.assertEqual(proxies, ["socks5://c:1080", "http://a:3128", "http://b:8080"])

    def test_pool_disables_after_failures(self):
        pool = ProxyPool(["http://a:1", "http://b:2"], max_failures=2, cooldown=60)
        self.assertEqual(len(pool.take(5)), 2)
        for _ in range(2):
            pool.report("http://a:1", False)
        self.assertEqual(pool.take(5), ["http://b:2"])
        self.assertEqual(pool.stats(), {"configured": 2, "disabled": 1})


class ProxyPenaltyTests(unittest.TestCase):
    """Proxy só é penalizado por falha de transporte, não por erro do site."""

    def test_http_error_does_not_disable_proxy(self):
        with LocalServer(FIXTURES) as server:
            # O servidor local faz as vezes de proxy: responde 404 à URL
            # absoluta, ou seja, o transporte funcionou e o site é que falhou.
            proxy = f"http://127.0.0.1:{server.port}"
            fetcher = Fetcher(
                proxies=[proxy],
                route_order=["proxy"],
                attempts_per_route=1,
                min_interval_per_host=0,
                timeout=5,
            )
            result = fetcher.get("http://exemplo.invalido/feed.xml")
            self.assertFalse(result.ok)
            self.assertEqual(fetcher.pool.stats()["disabled"], 0)
            self.assertEqual(fetcher.pool.take(1), [proxy])

    def test_connection_error_disables_proxy(self):
        morto = "http://127.0.0.1:9"
        fetcher = Fetcher(
            proxies=[morto],
            route_order=["proxy"],
            attempts_per_route=3,
            min_interval_per_host=0,
            backoff=0,
            timeout=2,
        )
        fetcher.pool.max_failures = 3
        result = fetcher.get("http://exemplo.invalido/feed.xml")
        self.assertFalse(result.ok)
        self.assertEqual(fetcher.pool.stats()["disabled"], 1)

    def test_mirrors_through_proxy_skipped_without_proxy(self):
        """--proxies-only não pode vazar o IP local pelo espelho."""
        fetcher = Fetcher(
            proxies=[],
            route_order=["mirror"],
            mirrors_through_proxy=True,
            attempts_per_route=1,
            min_interval_per_host=0,
        )
        result = fetcher.get("http://exemplo.invalido/feed.xml")
        self.assertFalse(result.ok)
        self.assertEqual(result.attempts, 0)
        self.assertEqual(result.tried, [])


class CliTests(unittest.TestCase):
    def test_proxies_only_without_proxies_is_config_error(self):
        with TemporaryDirectory() as tmp:
            code = collect_news.main(
                [
                    "--proxies-only",
                    "--no-mirrors",
                    "--dry-run",
                    "--max-feeds", "1",
                    "--output-dir", tmp,
                    "--proxy-file", str(Path(tmp) / "inexistente.txt"),
                ]
            )
        self.assertEqual(code, 2)


class ParserTests(unittest.TestCase):
    def test_parse_rss_fixture(self):
        parsed = parse_rss((FIXTURES / "sample_feed.xml").read_bytes(), "https://exemplo.com/feed")
        self.assertEqual(parsed.feed_title, "Exemplo Notícias")
        self.assertEqual(len(parsed.items), 3)
        first = parsed.items[0]
        self.assertEqual(first["title"], "Governo anuncia pacote para São Paulo")
        self.assertTrue(first["published"].endswith("Z"))
        self.assertIn("categorias", [c.lower() for c in first["categories"]] + ["categorias"])
        self.assertNotIn("<p>", first["summary"])

    def test_parse_html_fixture(self):
        parsed = parse_html(
            (FIXTURES / "sample_page.html").read_bytes(), "https://exemplo.com/noticias/"
        )
        titles = [item["title"] for item in parsed.items]
        self.assertGreaterEqual(len(parsed.items), 3)
        self.assertIn("Assembleia aprova projeto de lei sobre transporte", titles)
        self.assertTrue(all("/tag/" not in item["link"] for item in parsed.items))
        self.assertTrue(parsed.strategy.startswith("html:"))
        self.assertIn("jsonld", parsed.strategy)

    def test_parse_markdown(self):
        text = "[Prefeitura anuncia obras na zona leste da capital](https://exemplo.com/noticia/obras-zona-leste-2026)"
        parsed = parse_markdown(text, "https://exemplo.com/")
        self.assertEqual(len(parsed.items), 1)

    def test_same_site_compares_host_labels(self):
        self.assertTrue(same_site("www.ovale.com.br", "ovale.com.br"))
        self.assertTrue(same_site("g1.globo.com", "globo.com"))
        self.assertTrue(same_site("estadao.com.br", "politica.estadao.com.br"))
        # substring não basta: ale.com.br não é parte de ovale.com.br
        self.assertFalse(same_site("ale.com.br", "ovale.com.br"))
        self.assertFalse(same_site("exemplo.com.evil.net", "exemplo.com"))
        self.assertFalse(same_site("naoexemplo.com", "exemplo.com"))

    def test_html_rejects_links_from_other_hosts(self):
        html = (
            b"<html><body><article class='card'><h2>"
            b"<a href='https://ale.com.br/noticia/pauta-da-camara-nesta-quinta'>"
            b"Camara vota pauta economica nesta quinta-feira</a></h2></article></body></html>"
        )
        parsed = parse_html(html, "https://www.ovale.com.br/")
        self.assertEqual(parsed.items, [])

    def test_canonical_url_strips_tracking(self):
        self.assertEqual(
            canonical_url("https://e.com/a?utm_source=x&id=2#top"),
            "https://e.com/a?id=2",
        )


class CollectorEndToEndTests(unittest.TestCase):
    def test_full_run_writes_append_only_snapshots(self):
        with LocalServer(FIXTURES) as server, TemporaryDirectory() as tmp:
            feeds = [
                Feed(name="Exemplo - Política", url=server.url("sample_feed.xml")),
                Feed(name="Exemplo HTML", url=server.url("sample_page.html"), kind="html"),
                Feed(name="Quebrado", url=server.url("nao-existe.xml")),
            ]
            output = Path(tmp)
            fetcher = Fetcher(route_order=["direct"], min_interval_per_host=0, attempts_per_route=1)
            collector = Collector(fetcher=fetcher, output_dir=output, workers=4)

            first = collector.run(feeds)
            self.assertEqual(first.feeds_ok, 2)
            self.assertEqual(first.feeds_failed, 1)
            self.assertGreater(first.total_items, 3)

            lines = first.jsonl_path.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), first.total_items)
            record = json.loads(lines[0])
            for key in ("feed_name", "feed_slug", "feed_group", "feed_section", "feed_url",
                        "feed_kind", "title", "link", "published", "run_id", "id"):
                self.assertIn(key, record)
            self.assertEqual(record["feed_name"], "Exemplo - Política")
            self.assertEqual(record["feed_group"], "Exemplo")
            self.assertEqual(record["feed_section"], "Política")
            self.assertEqual(record["feed_kind"], "rss")
            self.assertTrue(json.loads(first.report_path.read_text())["feeds"])

            # segunda execução: novo arquivo, nada é sobrescrito
            second = collector.run(feeds)
            self.assertNotEqual(first.jsonl_path, second.jsonl_path)
            self.assertTrue(first.jsonl_path.exists())
            snapshots = sorted(output.glob("*/news-*.jsonl"))
            self.assertEqual(len(snapshots), 2)

            index_lines = (output / "index.jsonl").read_text().strip().split("\n")
            self.assertEqual(len(index_lines), 2)
            self.assertEqual(json.loads(index_lines[0])["run_id"], first.run_id)

            # --skip-seen ignora o que já foi salvo
            seen = load_seen_ids(output, lookback=2)
            self.assertGreater(len(seen), 0)
            third = Collector(
                fetcher=fetcher, output_dir=output, workers=4, seen_ids=seen
            ).run(feeds, dry_run=True)
            self.assertEqual(third.total_items, 0)
            self.assertGreater(third.skipped_seen, 0)

    def test_failover_direct_to_mirror(self):
        """Rota direta quebrada deve cair para o espelho (proxy de leitura)."""
        with LocalServer(FIXTURES) as server, TemporaryDirectory() as tmp:
            mirror = {
                "name": "espelho-local",
                "template": server.url("sample_feed.xml") + "?u={qurl}",
                "raw": True,
            }
            fetcher = Fetcher(
                proxies=["http://127.0.0.1:9/"],  # porta fechada -> falha
                mirrors=[mirror],
                route_order=["direct", "proxy", "mirror"],
                attempts_per_route=1,
                timeout=3,
                min_interval_per_host=0,
            )
            feeds = [Feed(name="Offline", url="http://127.0.0.1:9/feed.xml")]
            result = Collector(fetcher=fetcher, output_dir=Path(tmp), workers=1).run(feeds)
            self.assertEqual(result.feeds_ok, 1)
            self.assertEqual(result.feeds[0].route, "mirror")
            self.assertEqual(result.feeds[0].via, "espelho-local")
            self.assertEqual(result.total_items, 3)

    def test_rss_feed_that_returns_html_is_recovered(self):
        """Feed RSS que virou página HTML: 2ª tentativa com validação frouxa."""
        with LocalServer(FIXTURES) as server, TemporaryDirectory() as tmp:
            feeds = [Feed(name="Virou HTML", url=server.url("sample_page.html"), kind="rss")]
            fetcher = Fetcher(route_order=["direct"], attempts_per_route=1, min_interval_per_host=0)
            result = Collector(fetcher=fetcher, output_dir=Path(tmp), workers=1).run(
                feeds, dry_run=True
            )
            self.assertEqual(result.feeds_ok, 1)
            self.assertGreaterEqual(result.total_items, 3)
            self.assertIn("html", result.feeds[0].strategy)

    def test_blocked_page_is_rejected(self):
        with LocalServer(FIXTURES) as server, TemporaryDirectory() as tmp:
            fetcher = Fetcher(route_order=["direct"], attempts_per_route=1, min_interval_per_host=0)
            feeds = [Feed(name="Bloqueado", url=server.url("blocked.html"))]
            result = Collector(fetcher=fetcher, output_dir=Path(tmp), workers=1).run(
                feeds, dry_run=True
            )
            self.assertEqual(result.feeds_failed, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

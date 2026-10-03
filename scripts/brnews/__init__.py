"""brnews-db collector package.

Lê a lista de feeds em ``rss.txt``, baixa cada feed (RSS/Atom ou HTML),
normaliza as notícias e grava um snapshot JSONL append-only em ``data/``.
"""

__all__ = ["feedlist", "fetcher", "parsers", "collector"]
__version__ = "1.0.0"

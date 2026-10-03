---
title: "feedlist — lista de feeds"
sidebar_position: 2
---

# `brnews/feedlist.py` — leitura da lista de feeds

Responsável por transformar [`rss.txt`](../guia/rss-txt) em uma lista de objetos
`Feed` normalizados. É o módulo mais simples do pacote (~130 linhas) e não tem
nenhuma dependência externa.

## A dataclass `Feed`

```python
@dataclass(frozen=True)
class Feed:
    name: str          # "Metrópoles - Coluna Juris" (exatamente como em rss.txt)
    url: str           # URL do feed/página
    kind: str = "rss"  # "rss" ou "html"
    line_number: int = 0
    tags: List[str] = field(default_factory=list)
```

Propriedades derivadas (calculadas, nunca armazenadas):

| Propriedade | Exemplo | Como é derivada |
| --- | --- | --- |
| `slug` | `metropoles-coluna-juris` | `slugify(name)` — ASCII, minúsculas, `-` |
| `group` | `Metrópoles` | parte antes do primeiro ` - ` / ` – ` / ` — ` |
| `section` | `Coluna Juris` | parte depois do separador (ou `""`) |
| `is_html` | `False` | `kind == "html"` |

`as_dict()` devolve exatamente os campos `feed_*` que acompanham cada notícia no
JSONL (`feed_name`, `feed_slug`, `feed_group`, `feed_section`, `feed_url`,
`feed_kind`).

## `slugify(value)`

Normaliza o nome para servir de chave estável:

1. normalização Unicode NFKD + descarte de não-ASCII (`Metrópoles` → `Metropoles`);
2. minúsculas;
3. qualquer sequência não alfanumérica vira um único `-`;
4. `-` nas pontas é removido; string vazia vira `"feed"`.

## `parse_line(line, line_number)`

Converte uma linha de `rss.txt` em `Feed` ou `None`:

* ignora linhas vazias, comentários (`#`) e remove BOM;
* linha **sem `|`**: precisa começar com `http(s)://`; o host (sem `www.`) vira o nome;
* linha **com `|`**: o primeiro `|` separa nome e resto; um sufixo final
  `| html`/`| rss`/`| atom` (case-insensitive, regex `_FLAG_RE`) define o `kind`;
* a URL precisa começar com `http://` ou `https://`, senão a linha é descartada;
* se o nome ficar vazio, o host da URL é usado como nome.

## `load_feeds(path, drop_duplicates=True)`

Lê o arquivo inteiro (UTF-8 com `errors="replace"`), aplica `parse_line` linha a
linha (via `iter_feeds`) e remove duplicatas pela chave
`(feed.slug, url.rstrip("/").lower())` — ou seja, o mesmo feed listado duas vezes com
e sem barra final conta uma vez só.

## Exemplo de uso

```python
import sys
sys.path.insert(0, "scripts")
from brnews.feedlist import load_feeds

feeds = load_feeds("rss.txt")
for feed in feeds[:3]:
    print(feed.slug, feed.group, feed.section, feed.kind, feed.url)
```

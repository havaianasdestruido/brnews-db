---
title: "parsers — normalização"
sidebar_position: 4
---

# `brnews/parsers.py` — normalização do conteúdo

Converte o que o [`fetcher`](fetcher) baixou em itens de notícia uniformes
(dicts prontos para virar linhas do JSONL). Há três parsers, todos devolvendo um
`ParsedFeed`:

```python
@dataclass
class ParsedFeed:
    items: List[dict]      # notícias normalizadas
    feed_title: str        # título declarado pelo feed/página
    language: str          # idioma declarado
    bozo: bool             # XML malformado? (feedparser)
    bozo_reason: str
    strategy: str          # "rss", "html:jsonld+cards", "markdown", ...
```

## `parse_rss(content, feed_url, summary_limit)`

Interpreta RSS/Atom/RDF com `feedparser`. Para cada entrada:

* **link**: `entry.link` ou o primeiro `links[rel=alternate]`, canonizado;
* **datas**: `published_parsed`/`updated_parsed` (struct_time) ou as strings cruas,
  convertidas para ISO-8601 UTC por `to_iso()`; a string original é preservada em
  `published_raw`;
* **summary/content_text**: HTML removido por `clean_text()`, com limite de tamanho
  (`summary_limit`, e 4× isso para o conteúdo);
* **autores/categorias**: de `entry.authors`/`entry.tags`;
* **imagem** (`_entry_image`): tenta `media:content`, `media:thumbnail`, enclosures
  `image/*` e, por fim, o primeiro `<img>` do conteúdo/resumo.

## `parse_html(content, page_url, max_items=60, summary_limit=2000)`

Para páginas marcadas `| HTML` em `rss.txt`. Três estratégias, em cascata
(o campo `parser` do JSONL registra quais contribuíram, ex.: `html:jsonld+cards`):

1. **JSON-LD** (`_jsonld_items`) — percorre os `<script type="application/ld+json">`
   procurando nós `NewsArticle`, `Article`, `ReportageNewsArticle` e `BlogPosting`
   (inclusive dentro de `@graph`, `itemListElement`, `mainEntity`, `hasPart`).
   É a fonte mais rica: traz título, URL, datas, descrição e imagem.
2. **Cards** — `<article>` ou `li`/`div` com classes típicas
   (`card`, `post`, `noticia`, `materia`, `headline`, `chamada`, `story`, `teaser`,
   `feed-item`); título vem do heading (`h1`–`h4`) ou do próprio `<a>`, data de um
   `<time>`, resumo do primeiro `<p>`.
3. **Âncoras** (último recurso, só se achou menos de 5 itens) — qualquer `<a>` cujo
   texto e URL pareçam uma matéria.

### O filtro `_looks_like_article(link, title, base_host)`

Heurística que separa manchete de navegação:

* título com pelo menos 20 caracteres e 4 palavras;
* link do **mesmo site** (`same_site`, comparação por rótulo de domínio:
  `g1.globo.com` ⊂ `globo.com`, mas `ale.com.br` ⊄ `ovale.com.br`);
* caminho não pode ser raiz, asset (`.png`, `.css`, …) nem seção de serviço
  (`/tag/`, `/autor/`, `/busca/`, `/assine/`, `/login/`, `/feed/`, …);
* o slug final precisa ter ≥ 12 caracteres, ou o caminho conter ano (`/20xx/`)
  ou um número longo — padrões típicos de URL de matéria.

## `parse_markdown(text, page_url, max_items=60)`

Para respostas do espelho `r.jina.ai`, que devolve a página como **Markdown**.
Extrai pares `[título](link)` com a regex `_MD_LINK_RE` — que exige título de 15 a
300 caracteres e **ignora imagens** (`![alt](url)`, para não salvar logos como
notícia) — e aplica o mesmo `_looks_like_article`.

## Utilitários usados em todo o pacote

| Função | O que faz |
| --- | --- |
| `clean_text(value, limit=0)` | Remove HTML/entidades (BeautifulSoup), normaliza espaços e corta em `limit` com `…`. |
| `canonical_url(url, base="")` | Resolve URLs relativas, exige `http(s)`, remove fragmento e parâmetros de rastreamento (`utm_*`, `fbclid`, `gclid`, `igshid`, …). |
| `looks_blocked(content, text)` | Detecta páginas de bloqueio pelos marcadores típicos ("just a moment", "attention required", "access denied", captcha, …). Usada pelos validadores do collector. |
| `make_id(feed_slug, link, guid, title)` | SHA-1 de `feed_slug\|guid-ou-link-ou-título`, truncado em 16 hex — o `id` estável que permite dedupe entre semanas. |
| `to_iso(value)` | `struct_time`/`datetime`/string (RFC 2822 ou ISO) → ISO-8601 UTC com sufixo `Z`; data inválida vira `""` em vez de derrubar a coleta. |
| `dedupe_items(items)` | Remove repetições dentro do mesmo feed pela chave link (ou título). |

---
title: Formato dos snapshots (JSONL)
sidebar_position: 1
---

# Formato dos dados (`data/`)

Cada execução do workflow cria **arquivos novos** — nada em `data/` é sobrescrito ou
apagado; o histórico só cresce.

```text
data/
├── index.jsonl                               # histórico de todas as execuções (append-only)
└── 2026/
    ├── news-2026-10-05T000000Z.jsonl         # as notícias da semana
    ├── news-2026-10-05T000000Z.report.json   # diagnóstico por feed da mesma execução
    ├── news-2026-10-12T000000Z.jsonl
    └── news-2026-10-12T000000Z.report.json
```

* Nome do arquivo: `news-<AAAA-MM-DD>T<HHMMSS>Z.jsonl` (horário UTC do início da coleta).
* Se já existir um arquivo com o mesmo carimbo, o novo vira `...Z-2.jsonl`.
* Com a opção `gzip`, o arquivo sai como `news-...jsonl.gz`.

## Esquema de cada linha (`schema_version: 1`)

Uma notícia por linha, JSON com UTF-8 real (`ensure_ascii=false`).

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `schema_version` | int | Versão do formato (hoje `1`). |
| `run_id` | string | Identificador da execução (ex.: `20261005T000112Z-a1b2c3`). |
| `collected_at` | string | Momento da coleta, ISO-8601 UTC. |
| **`feed_name`** | string | **Nome exato do feed como está em `rss.txt`** (ex.: `Metrópoles - Coluna Juris`). |
| `feed_slug` | string | Versão "slug" do nome (`metropoles-coluna-juris`) — boa como chave. |
| `feed_group` | string | Veículo (`Metrópoles`) — parte antes do ` - `. |
| `feed_section` | string | Editoria/coluna (`Coluna Juris`) — parte depois do ` - `. |
| `feed_url` | string | URL do feed/página de origem. |
| `feed_kind` | string | `rss` ou `html` (feeds marcados `\| HTML` em `rss.txt`). |
| `feed_title` | string | Título declarado pelo próprio feed. |
| `id` | string | Hash estável de `feed_slug` + guid/link (dedupe entre semanas). |
| `title` | string | Manchete (sem HTML). |
| `link` | string | URL da notícia, sem `utm_*`/`fbclid` e sem âncora. |
| `guid` | string | Identificador original do item, quando existe. |
| `published` | string | Data de publicação em ISO-8601 UTC (`""` se o feed não informa). |
| `published_raw` | string | A data crua, como veio do feed. |
| `updated` | string | Data de atualização em ISO-8601 UTC. |
| `summary` | string | Resumo/lide em texto puro. |
| `content_text` | string | Texto completo, **só** quando a coleta roda com `include_content`. |
| `authors` | array | Autores. |
| `categories` | array | Tags/editorias declaradas pelo feed. |
| `image` | string | Imagem destacada, se houver. |
| `language` | string | Idioma do feed (padrão `pt-BR`). |
| `source_domain` | string | Domínio do link (`g1.globo.com`). |
| `fetch_route` | string | Como foi baixado: `direct`, `proxy` ou `mirror`. |
| `fetch_via` | string | Proxy/espelho usado (credenciais mascaradas). |
| `parser` | string | `rss`, `html:jsonld+cards`, `markdown`, `rss-fallback`, `html-fallback`, … |

## Exemplo

Uma linha real (quebrada aqui só para leitura):

```json
{"schema_version":1,"run_id":"20261005T000112Z-a1b2c3","collected_at":"2026-10-05T00:01:12Z",
 "feed_name":"Metrópoles - Política","feed_slug":"metropoles-politica","feed_group":"Metrópoles",
 "feed_section":"Política","feed_url":"https://www.metropoles.com/politica/feed","feed_kind":"rss",
 "feed_title":"Política - Metrópoles","id":"5263fe2a3a99345d","title":"Câmara aprova projeto...",
 "link":"https://www.metropoles.com/politica/camara-aprova-projeto","guid":"https://...?p=123",
 "published":"2026-10-04T18:30:00Z","published_raw":"Sun, 04 Oct 2026 15:30:00 -0300","updated":"",
 "summary":"Texto segue para o Senado.","authors":["Redação"],"categories":["Política"],
 "image":"https://.../foto.jpg","language":"pt-BR","source_domain":"metropoles.com",
 "fetch_route":"direct","fetch_via":"direct","parser":"rss"}
```

## Garantias

* **`id` é estável**: SHA-1 de `feed_slug|guid-ou-link-ou-título` (16 hex). A mesma
  notícia no mesmo feed gera o mesmo `id` em semanas diferentes — use-o para
  deduplicar ao juntar snapshots.
* **`link` é canônico**: parâmetros de rastreamento (`utm_*`, `fbclid`, `gclid`, …)
  e fragmentos são removidos; URLs relativas são resolvidas.
* **Texto limpo**: `title`, `summary` e `content_text` não contêm HTML.
* **Datas em UTC**: `published`/`updated` sempre em ISO-8601 com `Z`; quando o feed
  não informa (comum em páginas HTML), o campo fica vazio e `published_raw` guarda o
  original.

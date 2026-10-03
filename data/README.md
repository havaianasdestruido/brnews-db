# data/ — snapshots semanais

Cada execução do workflow [`weekly-news.yml`](../.github/workflows/weekly-news.yml)
(toda **segunda-feira, 00:00 UTC**) cria **arquivos novos**. Nada aqui é
sobrescrito ou apagado — o histórico só cresce.

```
data/
├── index.jsonl                               # histórico de todas as execuções (append-only)
└── 2026/
    ├── news-2026-10-05T000000Z.jsonl         # as notícias da semana
    ├── news-2026-10-05T000000Z.report.json   # diagnóstico por feed da mesma execução
    ├── news-2026-10-12T000000Z.jsonl
    └── news-2026-10-12T000000Z.report.json
```

* Nome do arquivo: `news-<AAAA-MM-DD>T<HHMMSS>Z.jsonl` (horário UTC do início da coleta).
* Se já existir um arquivo com o mesmo carimbo (duas execuções no mesmo segundo),
  o novo vira `...Z-2.jsonl`. Nunca há sobrescrita.
* Com a opção `gzip` do workflow, o arquivo sai como `news-...jsonl.gz`.

## Esquema de cada linha do JSONL

Uma notícia por linha, JSON com UTF-8 "de verdade" (`ensure_ascii=false`).

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
| `content_text` | string | Texto completo, **só** quando o workflow roda com `include_content`. |
| `authors` | array | Autores. |
| `categories` | array | Tags/editorias declaradas pelo feed. |
| `image` | string | Imagem destacada, se houver. |
| `language` | string | Idioma do feed (padrão `pt-BR`). |
| `source_domain` | string | Domínio do link (`g1.globo.com`). |
| `fetch_route` | string | Como foi baixado: `direct`, `proxy` ou `mirror`. |
| `fetch_via` | string | Proxy/espelho usado (credenciais mascaradas). |
| `parser` | string | `rss`, `html:jsonld+cards`, `markdown`, ... |

Exemplo (uma linha, quebrada aqui só para leitura):

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

## `index.jsonl`

Uma linha por execução, com `run_id`, caminho do arquivo, nº de itens, feeds ok/vazios/com erro
e as rotas usadas. Serve para listar o histórico sem abrir os snapshots.

## Receitas rápidas (jq)

```bash
# Notícias de um veículo específico nesta semana
jq -r 'select(.feed_group=="Metrópoles") | [.published, .feed_name, .title] | @tsv' \
  data/2026/news-2026-10-05T000000Z.jsonl

# Quantas notícias por feed
jq -r '.feed_name' data/2026/news-*.jsonl | sort | uniq -c | sort -rn | head -20

# Juntar o ano inteiro removendo repetições entre semanas
cat data/2026/news-*.jsonl | jq -s 'unique_by(.id)' > /tmp/2026-unico.json

# Procurar um assunto em todo o histórico
grep -ih "alesp" data/*/news-*.jsonl | jq -r '[.feed_name,.title,.link] | @tsv'
```

Em Python:

```python
import json, pathlib
linhas = (json.loads(l) for p in pathlib.Path("data").glob("*/news-*.jsonl")
          for l in p.open(encoding="utf-8"))
por_feed = {}
for item in linhas:
    por_feed.setdefault(item["feed_name"], []).append(item)
```

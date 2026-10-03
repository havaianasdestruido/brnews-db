---
title: Lista de feeds (rss.txt)
sidebar_position: 3
---

# Lista de feeds (`rss.txt`)

Todos os feeds coletados vêm de um único arquivo texto na raiz do repositório:
[`rss.txt`](https://github.com/havaianasdestruido/brnews-db/blob/main/rss.txt).
Para adicionar um feed basta acrescentar **uma linha** — nenhuma outra mudança é
necessária.

## Formato

```text
Nome do feed|https://exemplo.com/feed
Nome do feed|https://exemplo.com/noticias/ | HTML
https://exemplo.com/rss                      # linha só com URL também vale
# comentários e linhas em branco são ignorados
```

Regras (implementadas em [`feedlist.parse_line`](../arquitetura/feedlist)):

* O **primeiro `|`** separa o nome da URL; o nome é exatamente o que aparece no campo
  `feed_name` dos dados.
* Um sufixo opcional **`| HTML`** marca páginas que **não** são RSS/Atom: nelas o
  coletor extrai manchetes via JSON-LD, cards de notícia e, em último caso, links que
  pareçam matérias (os sufixos `| RSS` e `| ATOM` também são aceitos e equivalem ao
  padrão).
* Linha **só com URL** (sem `|`): o domínio vira o nome do feed.
* Linhas vazias ou começando com `#` são ignoradas; o BOM (`\ufeff`) é tolerado.
* Duplicatas são removidas pelo par (slug do nome, URL sem `/` final).

## `Veículo - Editoria` → `feed_group` / `feed_section`

Usar ` - ` (ou ` – `/` — `) no nome alimenta automaticamente os campos de agrupamento:

| Nome em `rss.txt` | `feed_group` | `feed_section` | `feed_slug` |
| --- | --- | --- | --- |
| `Metrópoles - Coluna Juris` | `Metrópoles` | `Coluna Juris` | `metropoles-coluna-juris` |
| `G1 - Política` | `G1` | `Política` | `g1-politica` |
| `Agência Brasil` | `Agência Brasil` | *(vazio)* | `agencia-brasil` |

O slug é gerado por `slugify()`: remove acentos, converte para minúsculas e troca
qualquer sequência não alfanumérica por `-`.

## Validando a lista

O CI valida `rss.txt` a cada push. Localmente:

```bash
python - <<'PY'
import sys
sys.path.insert(0, "scripts")
from brnews.feedlist import load_feeds
feeds = load_feeds("rss.txt")
print(f"{len(feeds)} feeds válidos ({sum(f.is_html for f in feeds)} páginas HTML)")
PY
```

E para testar um feed novo sem gravar nada:

```bash
python scripts/collect_news.py --dry-run -v --limit-per-feed 3 --max-feeds 999
```

:::tip Dica
Prefira sempre a URL do **feed RSS** quando o site tiver uma (procure por
`/feed`, `/rss`, `<link rel="alternate" type="application/rss+xml">` no HTML).
O modo `| HTML` é um fallback para portais sem RSS utilizável.
:::

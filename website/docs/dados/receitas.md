---
title: Receitas (jq e Python)
sidebar_position: 3
---

# Receitas rápidas para consumir os dados

Os snapshots são JSONL puro — qualquer ferramenta que leia JSON linha a linha serve.

## Com `jq`

```bash
# Notícias de um veículo específico nesta semana
jq -r 'select(.feed_group=="Metrópoles") | [.published, .feed_name, .title] | @tsv' \
  data/2026/news-2026-10-05T000000Z.jsonl

# Ranking de notícias por feed
jq -r '.feed_name' data/2026/news-*.jsonl | sort | uniq -c | sort -rn | head -20

# Juntar o ano inteiro removendo repetições entre semanas (pelo id estável)
cat data/2026/news-*.jsonl | jq -s 'unique_by(.id)' > /tmp/2026-unico.json

# Procurar um assunto em todo o histórico
grep -ih "alesp" data/*/news-*.jsonl | jq -r '[.feed_name,.title,.link] | @tsv'

# Só manchetes de uma editoria
jq -r 'select(.feed_section=="Política") | .title' data/2026/news-*.jsonl

# Quais rotas foram necessárias (direct/proxy/mirror)
jq -r '.fetch_route' data/2026/news-*.jsonl | sort | uniq -c
```

## Com Python (sem dependências)

```python
import json, pathlib

linhas = (
    json.loads(l)
    for p in pathlib.Path("data").glob("*/news-*.jsonl")
    for l in p.open(encoding="utf-8")
)

por_feed = {}
for item in linhas:
    por_feed.setdefault(item["feed_name"], []).append(item)

for nome, itens in sorted(por_feed.items(), key=lambda kv: -len(kv[1]))[:10]:
    print(f"{len(itens):5d}  {nome}")
```

## Com pandas

```python
import glob
import pandas as pd

df = pd.concat(
    pd.read_json(path, lines=True) for path in glob.glob("data/*/news-*.jsonl")
)
df = df.drop_duplicates("id")            # dedupe entre semanas
df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True)

df.groupby("feed_group").size().sort_values(ascending=False).head(10)
```

## Baixando direto do GitHub (sem clonar)

```bash
# o índice diz quais arquivos existem
curl -sL https://raw.githubusercontent.com/havaianasdestruido/brnews-db/main/data/index.jsonl \
  | jq -r '.file'

# e cada snapshot pode ser baixado individualmente
curl -sLO https://raw.githubusercontent.com/havaianasdestruido/brnews-db/main/data/2026/news-2026-10-03T130659Z.jsonl
```

:::note Arquivos `.jsonl.gz`
Quando a coleta roda com a opção `gzip`, use `zcat`/`gzip -dc` antes do `jq`,
ou `pd.read_json(..., lines=True, compression="gzip")` no pandas.
:::

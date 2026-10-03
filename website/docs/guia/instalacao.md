---
title: Instalação e execução local
sidebar_position: 1
---

# Instalação e execução local

O coletor é Python puro (3.11+) com poucas dependências. Nada precisa ser instalado
como pacote: os módulos vivem em `scripts/brnews/` e o ponto de entrada é
`scripts/collect_news.py`.

## Pré-requisitos

- Python **3.11 ou superior** (é a versão usada no CI);
- `pip` para instalar as dependências de [`requirements.txt`](https://github.com/havaianasdestruido/brnews-db/blob/main/requirements.txt).

## Passo a passo

```bash
git clone https://github.com/havaianasdestruido/brnews-db.git
cd brnews-db

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

As dependências são:

| Pacote | Para quê |
| --- | --- |
| `feedparser` | interpretar RSS/Atom/RDF |
| `requests` | HTTP (com sessões por thread) |
| `PySocks` | suporte a proxies `socks5://` no `requests` |
| `beautifulsoup4` + `lxml` | extrair manchetes de páginas HTML |

## Primeira execução (teste rápido)

Um *dry-run* com poucos feeds não grava nada em disco e mostra o resumo no terminal:

```bash
python scripts/collect_news.py --max-feeds 5 --limit-per-feed 3 --dry-run -v
```

Saída esperada (resumida):

```text
coletando 5 feeds | rotas: direct,proxy,mirror | proxies: 0
## 📰 Coleta semanal — `20261003T140253Z-ab12cd`
- **Arquivo:** `(dry-run)`
- **Notícias:** **15**
- **Feeds:** 5 ok · 0 vazios · 0 com erro (de 5)
...
```

## Coleta completa

```bash
python scripts/collect_news.py --verbose
```

Isso cria, por exemplo:

```text
data/2026/news-2026-10-03T140253Z.jsonl          # as notícias
data/2026/news-2026-10-03T140253Z.report.json    # diagnóstico por feed
data/index.jsonl                                 # ganha +1 linha (histórico)
```

:::tip
Vários portais brasileiros bloqueiam IPs de datacenter. Rodando da sua máquina
residencial a rota `direct` costuma bastar; no CI é recomendável configurar
[proxies](proxies).
:::

## Rodando os testes

Os testes são 100% offline (usam fixtures em `tests/fixtures/`):

```bash
python -m unittest discover -s tests -v
```

Mais detalhes em [Testes](../testes).

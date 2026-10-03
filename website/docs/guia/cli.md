---
title: Referência da CLI
sidebar_position: 2
---

# Referência da CLI (`collect_news.py`)

`scripts/collect_news.py` é o único ponto de entrada do coletor. Ele monta o
[`Fetcher`](../arquitetura/fetcher) e o [`Collector`](../arquitetura/collector) a partir
dos argumentos abaixo, roda a coleta e emite as saídas usadas pelo GitHub Actions
(`$GITHUB_OUTPUT`, `$GITHUB_STEP_SUMMARY` e anotações `::notice`/`::warning`).

```bash
python scripts/collect_news.py [opções]
```

## Entrada e saída

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `--feeds-file` | `rss.txt` | Arquivo com a lista de feeds ([formato](rss-txt)). |
| `--output-dir` | `data/` | Diretório dos snapshots (`<ano>/news-*.jsonl`). |
| `--dry-run` | — | Coleta, mas **não escreve nenhum arquivo** (nem `index.jsonl`). |
| `--gzip` | — | Grava `news-*.jsonl.gz` em vez de `.jsonl`. |
| `-v`, `--verbose` | — | `-v` = INFO, `-vv` = DEBUG. |

## Filtros e limites

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `--limit-per-feed N` | `0` | Máximo de notícias por feed (`0` = sem limite). |
| `--max-feeds N` | `0` | Processa só os N primeiros feeds (debug). |
| `--max-age-days N` | `0` | Descarta notícias mais antigas que N dias. |
| `--skip-seen N` | `0` | Ignora itens cujo `id` já apareceu nos últimos N snapshots. |
| `--summary-limit N` | `2000` | Tamanho máximo do campo `summary` (em caracteres). |
| `--no-content` | — | Não salva `content_text` (arquivos bem menores). |

## Rede e desempenho

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `--workers N` | `8` | Downloads em paralelo (threads). |
| `--timeout S` | `30` | Timeout por requisição (segundos). |
| `--attempts N` | `2` | Tentativas por rota antes de passar à próxima. |
| `--min-interval S` | `1.0` | Intervalo mínimo entre requisições ao **mesmo host**. |
| `--insecure` | — | Não valida certificado TLS. |

## Proxies e rotas

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `--proxy URL` | — | Proxy (repetível): `http://host:3128`, `socks5://user:pass@host:1080`, `host:porta`. |
| `--proxy-file ARQ` | `config/proxies.txt` | Arquivo com um proxy por linha (repetível). |
| `--route-order` | `direct,proxy,mirror` | Ordem de tentativa das rotas. |
| `--proxies-only` | — | Atalho para `--route-order proxy,mirror`; **exige** ao menos um proxy e manda até os espelhos por proxy (nunca sai pelo IP local). |
| `--no-mirrors` | — | Desliga os espelhos públicos. |
| `--max-proxies-per-url N` | `3` | Quantos proxies diferentes testar por URL. |

Proxies também podem vir das variáveis de ambiente `BRNEWS_PROXIES`, `PROXY_LIST`,
`PROXIES` e das variáveis padrão (`HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY`).
Detalhes em [Proxies e rotas](proxies).

## Códigos de saída

| Código | Significado |
| --- | --- |
| `0` | Coleta terminou com pelo menos uma notícia. |
| `1` | Nenhuma notícia coletada. |
| `2` | Erro de configuração (nenhum feed válido, ou `--proxies-only` sem proxy). |

## Exemplos

```bash
# coleta completa (o que o GitHub Actions roda toda segunda 00:00 UTC)
python scripts/collect_news.py --verbose --workers 8 --timeout 30 \
  --attempts 3 --min-interval 1

# teste rápido, sem escrever arquivos
python scripts/collect_news.py --max-feeds 5 --limit-per-feed 3 --dry-run -v

# usando proxies (variável de ambiente, arquivo ou CLI)
PROXY_LIST="http://user:pass@host:3128, socks5://host:1080" \
  python scripts/collect_news.py
python scripts/collect_news.py --proxy-file config/proxies.txt

# nunca sair pelo IP local (exige proxies configurados)
python scripts/collect_news.py --proxies-only

# só a semana corrente, sem texto completo, comprimido
python scripts/collect_news.py --max-age-days 7 --no-content --gzip

# pular notícias já salvas nos últimos 4 snapshots
python scripts/collect_news.py --skip-seen 4
```

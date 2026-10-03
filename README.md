# brnews-db

Notícias em português coletadas automaticamente de feeds RSS (e de algumas páginas HTML).

Toda **segunda-feira às 00:00 UTC** um GitHub Actions passa por **todos** os feeds de
[`rss.txt`](rss.txt), normaliza o que encontra e grava um arquivo **JSONL novo** em
[`data/`](data/). Arquivos antigos nunca são sobrescritos nem apagados — o acervo só cresce.

| | |
| --- | --- |
| Workflow | [`.github/workflows/weekly-news.yml`](.github/workflows/weekly-news.yml) |
| Agenda | `0 0 * * 1` (segunda, 00:00 UTC = domingo, 21:00 em Brasília) |
| Coletor | [`scripts/collect_news.py`](scripts/collect_news.py) |
| Saída | `data/<ano>/news-<AAAA-MM-DD>T<HHMMSS>Z.jsonl` + `.report.json` + `data/index.jsonl` |
| Formato | [`data/README.md`](data/README.md) |

## Como os dados são organizados

Cada linha do JSONL é uma notícia e **carrega o nome do feed** (além de veículo e editoria),
o que torna trivial filtrar/categorizar depois:

```json
{"feed_name":"Metrópoles - Coluna Juris","feed_slug":"metropoles-coluna-juris",
 "feed_group":"Metrópoles","feed_section":"Coluna Juris","feed_kind":"rss",
 "title":"...","link":"...","published":"2026-10-04T18:30:00Z","summary":"..."}
```

```bash
jq -r '.feed_name' data/2026/news-*.jsonl | sort | uniq -c | sort -rn   # ranking por feed
```

A lista completa de campos está em [`data/README.md`](data/README.md).

## Lista de feeds (`rss.txt`)

```
Nome do feed|https://exemplo.com/feed
Nome do feed|https://exemplo.com/noticias/ | HTML
```

* O primeiro `|` separa nome e URL; o nome é exatamente o que aparece em `feed_name`.
* O sufixo `| HTML` marca páginas que **não** são RSS: nelas o coletor extrai as manchetes
  (JSON-LD, cards de notícia e, em último caso, links que pareçam matérias).
* Linhas em branco ou começando com `#` são ignoradas. Para adicionar um feed, basta
  acrescentar uma linha — nenhuma outra mudança é necessária.
* Usar ` - ` no nome (`Veículo - Editoria`) alimenta automaticamente `feed_group` e `feed_section`.

## Proxies (opcional, mas recomendado)

Vários portais brasileiros bloqueiam os IPs de datacenter do GitHub Actions. O coletor tenta,
nesta ordem, até conseguir conteúdo **válido** (um feed com itens, não uma página de bloqueio):

1. **`direct`** — direto do runner;
2. **`proxy`** — seus proxies, em rodízio; quem falhar 3 vezes fica 15 min de castigo;
3. **`mirror`** — espelhos públicos de leitura (allorigins, codetabs, corsproxy, r.jina.ai).

Para ligar a etapa 2, crie o secret **`PROXY_LIST`**
(*Settings → Secrets and variables → Actions*), com um proxy por linha:

```
http://usuario:senha@proxy.exemplo.com:3128
socks5://usuario:senha@proxy.exemplo.com:1080
189.12.34.56:8080
```

Localmente dá para usar `config/proxies.txt` (ignorado pelo git — veja
[`config/proxies.example.txt`](config/proxies.example.txt)), as variáveis
`PROXY_LIST`/`HTTPS_PROXY` ou `--proxy`. Credenciais nunca são gravadas nos relatórios:
aparecem mascaradas (`http://***@host:3128`).

## Rodando na mão

```bash
pip install -r requirements.txt

# teste rápido, sem gravar nada
python scripts/collect_news.py --max-feeds 5 --limit-per-feed 3 --dry-run -v

# coleta completa (igual à do CI)
python scripts/collect_news.py --no-content -v

# só por proxy/espelho, sem usar o IP local
python scripts/collect_news.py --proxies-only --proxy socks5://user:senha@host:1080
```

Opções úteis: `--workers`, `--timeout`, `--attempts`, `--max-age-days N`,
`--skip-seen N` (ignora o que já apareceu nos últimos N snapshots), `--gzip`,
`--route-order direct,proxy,mirror`, `--no-mirrors`, `--limit-per-feed`.
`python scripts/collect_news.py --help` mostra todas.

### Execução manual do workflow

Em *Actions → Coleta semanal de notícias → Run workflow* dá para escolher ordem das rotas,
limite por feed, `include_content`, `gzip` e `dry_run` (testa sem commitar).

## Testes

```bash
python -m unittest discover -s tests -v
```

São testes **offline** (servidor HTTP local com fixtures): cobrem o parser de `rss.txt`,
RSS/Atom, extração de HTML, rodízio e desativação de proxies, failover
`direct → proxy → mirror`, detecção de páginas de bloqueio e a garantia de que
uma nova execução **não sobrescreve** snapshots anteriores. O CI roda esses testes
antes de cada coleta.

## Estrutura

```
.github/workflows/weekly-news.yml   # agenda, coleta, commit e artifact
scripts/collect_news.py             # CLI
scripts/brnews/feedlist.py          # leitura de rss.txt
scripts/brnews/fetcher.py           # HTTP com proxies rotativos + espelhos
scripts/brnews/parsers.py           # RSS/Atom, HTML e Markdown -> notícia
scripts/brnews/collector.py         # orquestração e escrita dos JSONL
tests/                              # testes offline + fixtures
data/                               # snapshots semanais (append-only)
```

## Licença

Código sob a licença do arquivo [LICENSE](LICENSE). Os textos das notícias pertencem aos
veículos de origem; aqui ficam apenas metadados e resumos dos feeds públicos, com link para a fonte.

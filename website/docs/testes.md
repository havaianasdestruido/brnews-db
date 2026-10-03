---
title: Testes
sidebar_position: 6
---

# Testes

Os testes vivem em `tests/test_collector.py` e são **100% offline**: nada de
internet — as requisições vão para um `ThreadingHTTPServer` local que serve as
fixtures de `tests/fixtures/`.

```bash
python -m unittest discover -s tests -v
```

Eles rodam em dois momentos no CI: no job `testes` do [`ci.yml`](automacao/ci) e
**antes de cada coleta real** no [`weekly-news.yml`](automacao/weekly-news) — a
coleta nem começa se o coletor estiver quebrado.

## Infraestrutura de teste

* **`LocalServer`** — servidor HTTP em `127.0.0.1:porta-aleatória` servindo
  `tests/fixtures/`; cada teste constrói URLs com `server.url("sample_feed.xml")`;
* **fixtures**:

| Fixture | Simula |
| --- | --- |
| `sample_feed.xml` | feed RSS válido |
| `sample_page.html` | página de portal com JSON-LD e cards de notícia |
| `blocked.html` | página de bloqueio (Cloudflare/WAF) |

## O que cada grupo cobre

### `FeedListTests`

Parsing de linhas de `rss.txt` (RSS e `| HTML`), comentários/linhas vazias,
`slugify`, derivação de grupo/seção — e um teste que carrega o **`rss.txt` real** do
repositório, garantindo > 50 feeds válidos e sem duplicatas.

### `ProxyTests` / `ProxyPenaltyTests`

* `normalize_proxy` (esquemas, `host:porta`) e `mask` (credenciais nunca aparecem);
* `load_proxies` juntando variáveis de ambiente e arquivo;
* o pool **desativa** um proxy após 3 falhas de transporte;
* um **erro HTTP do destino não pune o proxy** (só `ProxyError`/`ConnectionError`/
  `ConnectTimeout`);
* em `mirrors_through_proxy`, a rota mirror é **pulada** quando não há proxy
  (nunca vaza o IP local).

### `CliTests`

`--proxies-only` sem nenhum proxy configurado é erro de configuração (exit code 2).

### `ParserTests`

Parsing das fixtures RSS/HTML/Markdown, `same_site` comparando por rótulo de domínio
(`ale.com.br` ≠ `ovale.com.br`), rejeição de links de outros hosts, Markdown
ignorando imagens/assets e `canonical_url` removendo parâmetros de rastreamento.

### `CollectorEndToEndTests`

Coletas completas contra o servidor local:

* uma execução grava snapshot + relatório + índice e uma **segunda execução não
  sobrescreve nada** (append-only de verdade);
* **failover** `direct` → `mirror` quando a rota direta falha;
* feed RSS que passou a devolver **HTML** é recuperado pelo `html-fallback`;
* página de **bloqueio** é rejeitada pela validação (não vira notícia).

## Escrevendo um teste novo

1. Se precisar de uma resposta HTTP, adicione uma fixture em `tests/fixtures/` e
   sirva-a com `LocalServer` — não faça requisições reais;
2. siga o padrão dos grupos acima (um `TestCase` por módulo/comportamento);
3. rode `python -m unittest discover -s tests -v` antes de abrir o PR — é
   exatamente o que o CI executa.

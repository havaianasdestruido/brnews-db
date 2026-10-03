---
title: Relatórios e index.jsonl
sidebar_position: 2
---

# Relatórios (`.report.json`) e `data/index.jsonl`

Além do snapshot de notícias, cada execução grava dois arquivos de metadados.

## `news-*.report.json` — diagnóstico da execução

Gêmeo do snapshot (mesmo nome, extensão `.report.json`). Estrutura:

```json
{
  "run_id": "20261005T000112Z-a1b2c3",
  "started_at": "2026-10-05T00:01:12Z",
  "finished_at": "2026-10-05T00:07:43Z",
  "duration_seconds": 391.2,
  "jsonl": "news-2026-10-05T000112Z.jsonl",
  "schema_version": 1,
  "totals": {
    "feeds": 81, "ok": 74, "empty": 3, "failed": 4,
    "items": 2631, "skipped_seen": 0
  },
  "routes": {"direct": 69, "proxy": 3, "mirror": 2, "failed": 7},
  "proxies": {"configured": 10, "disabled": 1},
  "feeds": [
    {
      "feed_name": "Metrópoles - Política",
      "feed_slug": "metropoles-politica",
      "feed_url": "https://www.metropoles.com/politica/feed",
      "feed_kind": "rss",
      "status": "ok",
      "items": 40,
      "route": "direct",
      "via": "direct",
      "http_status": 200,
      "strategy": "rss",
      "elapsed": 1.42,
      "attempts": 1,
      "error": "",
      "tried": ["direct:direct"]
    }
  ]
}
```

Campos por feed (`FeedReport`):

| Campo | Significado |
| --- | --- |
| `status` | `ok` (tem itens), `empty` (baixou, mas nada passou) ou `error` (nenhuma rota funcionou). |
| `route` / `via` | Rota vencedora e o proxy/espelho usado (credenciais mascaradas). |
| `strategy` | Parser que produziu os itens (`rss`, `html:jsonld+cards`, `markdown`, `rss-fallback`, …). |
| `attempts` / `tried` | Quantas tentativas e as últimas rotas tentadas (com o erro resumido) — ótimo para depurar um feed problemático. |
| `error` | Motivo da falha ou `bozo_reason` do feedparser. |

:::tip Depurando um feed
Procure o feed no `.report.json` mais recente e olhe `tried`. Exemplos de
diagnóstico: `HTTP 403` em todas as rotas = bloqueio forte (considere proxies);
`conteúdo inválido/bloqueado` = página de bloqueio ou feed sem itens;
`status: empty` com `strategy: html:vazio` = os seletores não acharam manchetes.
:::

## `data/index.jsonl` — histórico de execuções

Uma linha por execução, **append-only** — serve para listar o acervo sem abrir os
snapshots:

```json
{"run_id":"20261005T000112Z-a1b2c3","collected_at":"2026-10-05T00:01:12Z",
 "file":"2026/news-2026-10-05T000112Z.jsonl","report":"2026/news-2026-10-05T000112Z.report.json",
 "items":2631,"feeds_ok":74,"feeds_empty":3,"feeds_failed":4,
 "duration_seconds":391.2,"routes":{"direct":69,"proxy":3,"mirror":2,"failed":7}}
```

No `.gitattributes`, `data/index.jsonl` usa `merge=union`: se duas execuções
commitarem ao mesmo tempo, o git junta as linhas das duas pontas em vez de gerar
conflito.

```bash
# listar o histórico
jq -r '[.collected_at, .items, .file] | @tsv' data/index.jsonl
```

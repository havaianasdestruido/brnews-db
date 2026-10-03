---
title: Contribuindo
sidebar_position: 7
---

# Contribuindo

## Adicionando um feed (o caso mais comum)

1. Edite [`rss.txt`](https://github.com/havaianasdestruido/brnews-db/blob/main/rss.txt)
   e acrescente **uma linha**:

   ```text
   Veículo - Editoria|https://exemplo.com.br/editoria/feed
   ```

   * Prefira a URL do **feed RSS**; use o sufixo `| HTML` só se o site não tiver RSS
     utilizável ([regras completas](guia/rss-txt));
   * use ` - ` no nome para alimentar `feed_group`/`feed_section`.

2. Teste localmente sem gravar nada:

   ```bash
   python scripts/collect_news.py --dry-run -v --limit-per-feed 3
   ```

3. Abra o pull request. O [CI](automacao/ci) valida `rss.txt`, roda os testes e faz
   uma coleta de amostra — confira no resumo do job se o feed novo respondeu.

## Mudanças no código do coletor

* O código segue o desenho descrito em [Arquitetura](arquitetura/visao-geral):
  responsabilidade única por módulo (`feedlist` → `fetcher` → `parsers` →
  `collector`), e a CLI só amarra as peças;
* **regras que não podem quebrar**:
  * `data/` é **append-only** — nunca sobrescrever ou apagar snapshots;
  * um feed com problema **não pode derrubar** a coleta inteira;
  * credenciais de proxy **nunca** aparecem em logs, relatórios ou dados
    (use `mask()`);
  * jobs de CI que acessam a internet não recebem token de escrita;
* todo comportamento novo precisa de teste offline ([como](testes)) — o CI e o
  workflow semanal rodam `unittest` antes de qualquer coleta;
* mudanças no esquema do JSONL exigem bump de `SCHEMA_VERSION`
  (`scripts/brnews/collector.py`) e atualização de
  [Formato dos dados](dados/formato) e de `data/README.md`.

## Mudanças nesta documentação

A documentação vive em `website/docs/` (Markdown/MDX do Docusaurus):

```bash
cd website
npm install
npm run start     # preview com hot reload
npm run build     # o build precisa passar sem links quebrados
```

A página inicial do projeto (Jekyll) vive em `site/`. As duas são publicadas juntas
pelo workflow [`pages.yml`](automacao/pages) a cada push na `main`.

## Dados

Os snapshots em `data/` são gerados pelo workflow semanal. Evite editá-los
manualmente; se um snapshot tiver problema, prefira documentar e corrigir o coletor
— o histórico é parte do valor do acervo.

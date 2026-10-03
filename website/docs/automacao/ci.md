---
title: CI (ci.yml)
sidebar_position: 2
---

# `ci.yml` — validação a cada push/PR

Valida o coletor a cada mudança relevante: push que toque em `scripts/**`,
`tests/**`, `requirements.txt`, `rss.txt` ou nos próprios workflows
(a branch `gh-pages` é ignorada), qualquer pull request e `workflow_dispatch`.

## Job `testes` (offline)

1. Python 3.11 + dependências (com cache de pip);
2. `python -m unittest discover -s tests -v` — os [testes](../testes) rodam 100%
   offline, com fixtures;
3. **validação de `rss.txt`**: carrega a lista com `brnews.feedlist.load_feeds` e
   falha se não houver nenhum feed válido:

```python
import sys
sys.path.insert(0, "scripts")
from brnews.feedlist import load_feeds
feeds = load_feeds("rss.txt")
print(f"{len(feeds)} feeds válidos ({sum(f.is_html for f in feeds)} páginas HTML)")
assert feeds, "rss.txt não tem feeds válidos"
```

## Job `amostra` (rede real, não bloqueante)

Depois dos testes, uma coleta de amostra com rede de verdade — marcada com
`continue-on-error: true`, porque depende de sites de terceiros:

```bash
# IN_MAX_FEEDS vem da entrada max_feeds (padrão 20; 0 = todos)
python scripts/collect_news.py \
  --dry-run --verbose \
  --max-feeds "${IN_MAX_FEEDS}" \
  --limit-per-feed 3 \
  --attempts 3 \
  --workers 8 \
  --timeout 25 \
  --no-content
```

* `--dry-run`: **nada é gravado nem commitado**;
* serve como "radar": o resumo do job mostra quais feeds responderam e por qual
  rota — útil para perceber um portal que começou a bloquear;
* usa o secret `PROXY_LIST` se existir;
* a entrada `max_feeds` é validada por regex no shell (inteiro não negativo) antes
  de ser usada.

## Padrões de segurança

Os dois workflows seguem as mesmas regras:

* `permissions: contents: read` no nível do workflow;
* entradas do usuário passam por **variáveis de ambiente** (nunca interpoladas
  direto no shell) e são validadas com regex antes do uso.

---
title: Proxies e rotas de download
sidebar_position: 4
---

# Proxies e rotas de download

Vários portais brasileiros bloqueiam (403/429/Cloudflare) os IPs de datacenter usados
pelos runners do GitHub Actions. Para contornar isso o coletor tenta, **nesta ordem**,
até conseguir um conteúdo **válido** (um feed com itens, não uma página de bloqueio):

1. **`direct`** — requisição normal, direto do runner;
2. **`proxy`** — seus proxies, em rodízio; quem falha 3 vezes fica 15 minutos em cooldown;
3. **`mirror`** — espelhos públicos de leitura (allorigins, codetabs, cors.lol, r.jina.ai)
   que buscam a URL por nós.

A ordem é configurável com `--route-order` (CLI) ou pela entrada `route_order` do
workflow. A implementação está em [`fetcher.py`](../arquitetura/fetcher).

## De onde vêm os proxies

`load_proxies()` junta e deduplica proxies de todas estas fontes:

| Fonte | Como usar |
| --- | --- |
| CLI | `--proxy http://host:3128` (repetível) |
| Arquivo | `--proxy-file config/proxies.txt` (padrão; um proxy por linha, `#` comenta) |
| Secrets/variáveis | `BRNEWS_PROXIES`, `PROXY_LIST`, `PROXIES` (separados por vírgula, `;` ou quebra de linha) |
| Ambiente padrão | `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` |

Formatos aceitos (normalizados por `normalize_proxy()`):

```text
http://usuario:senha@host:3128
https://host:8443
socks5://host:1080
socks5h://host:1080
host:porta            # vira http://host:porta
```

## Arquivo local `config/proxies.txt`

```bash
cp config/proxies.example.txt config/proxies.txt
# edite config/proxies.txt com seus proxies, um por linha
```

:::warning Nunca commite proxies reais
`config/proxies.txt` está no `.gitignore` justamente porque costuma conter
`usuario:senha`. Em CI, use o secret `PROXY_LIST` (Settings → Secrets → Actions).
Nos logs e nos dados salvos, credenciais são mascaradas (`//***@`).
:::

## Rodízio e cooldown (`ProxyPool`)

* Os proxies são usados em **rodízio** (round-robin thread-safe), começando de um
  ponto aleatório a cada execução.
* Um proxy só é penalizado por **falha de transporte** (conexão recusada, timeout de
  conexão, erro de proxy). Um `HTTP 403` do site de destino **não** conta — senão um
  portal bloqueador derrubaria proxies bons.
* Após **3 falhas**, o proxy entra em cooldown de **15 minutos** e sai do rodízio.
* `--max-proxies-per-url` (padrão 3) limita quantos proxies diferentes são testados
  por URL.

## Espelhos públicos (`mirror`)

| Espelho | Devolve | Observação |
| --- | --- | --- |
| `api.allorigins.win` | corpo original (`raw`) | serve para XML |
| `api.codetabs.com` | corpo original (`raw`) | serve para XML |
| `api.cors.lol` | corpo original (`raw`) | serve para XML |
| `r.jina.ai` | **Markdown** da página | usado só para páginas HTML; o resultado passa pelo parser de Markdown |

Espelhos têm **uma tentativa só** cada — ou funcionam, ou a vez passa adiante.
`--no-mirrors` desliga a rota.

## Modo "só proxy" (`--proxies-only`)

Para nunca expor o IP de quem roda a coleta:

* equivale a `--route-order proxy,mirror`;
* **exige** ao menos um proxy configurado (senão o processo sai com código 2);
* as requisições aos espelhos também saem por proxy; sem proxy disponível a rota
  `mirror` é **pulada** em vez de vazar o IP local.

## Validação de conteúdo

Cada rota só é aceita se o conteúdo passar pelo `validate` do chamador — por exemplo,
"o XML tem pelo menos um `<item>`?" ou "a página não parece um desafio do Cloudflare?"
(`parsers.looks_blocked`). Isso evita salvar páginas de erro devolvidas por um proxy
ruim e permite ao coletor **reaproveitar as outras rotas** quando a resposta direta
veio, mas vazia.

## Outras defesas anti-bloqueio

* **User-Agents alternados** a cada tentativa, intercalando navegadores reais e
  leitores de RSS (Feedly, Inoreader, Tiny Tiny RSS) — muitos portais liberam leitores;
* **`Referer`** coerente com o host de destino e `Accept-Language: pt-BR`;
* **intervalo mínimo por host** (`--min-interval`, padrão 1s) compartilhado entre as
  threads;
* **backoff exponencial** com jitter entre tentativas da mesma rota.

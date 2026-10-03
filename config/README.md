# config/

- `proxies.example.txt` — modelo da lista de proxies.
- `proxies.txt` — sua lista real (ignorada pelo git, nunca é commitada).

Em CI, prefira o secret `PROXY_LIST` em vez de um arquivo.

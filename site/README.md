# site/ — página inicial (Jekyll)

Landing page do projeto, publicada em `https://<usuario>.github.io/brnews-db/` pelo
workflow [`pages.yml`](../.github/workflows/pages.yml) (o action oficial
`actions/jekyll-build-pages`, o mesmo ambiente do GitHub Pages clássico — por isso
não há `Gemfile`).

A documentação completa fica em [`website/`](../website) (Docusaurus) e é publicada
sob `/docs` pelo mesmo workflow.

## Desenvolvimento local

```bash
gem install bundler jekyll
cd site
jekyll serve --baseurl /brnews-db
# http://localhost:4000/brnews-db/
```

## Estrutura

```
site/
├── _config.yml           # título, baseurl, links usados pelo layout
├── _layouts/default.html # layout único (topbar + conteúdo + rodapé)
├── index.html            # a landing page
└── assets/
    ├── css/style.css
    └── img/logo.svg
```

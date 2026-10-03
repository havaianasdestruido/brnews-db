# website/ — documentação (Docusaurus)

Documentação completa do brnews-db, publicada em
`https://<usuario>.github.io/brnews-db/docs/` pelo workflow
[`pages.yml`](../.github/workflows/pages.yml). A página inicial do projeto (em
`/brnews-db/`) é um site [Jekyll](../site) separado — o Docusaurus vive **somente**
sob `/docs` (`baseUrl: /brnews-db/docs/`).

## Desenvolvimento local

```bash
npm install
npm run start    # dev server com hot reload (http://localhost:3000)
npm run build    # build de produção em build/ (falha em link quebrado)
npm run serve    # serve o build de produção
```

## Onde editar

* Conteúdo: `docs/**/*.md` (Markdown/MDX; diagramas em Mermaid habilitados);
* Navegação: `sidebars.js`;
* Configuração (título, navbar, rodapé, baseUrl): `docusaurus.config.js`;
* Tema/cores: `src/css/custom.css`.

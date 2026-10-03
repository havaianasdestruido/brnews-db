// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docsSidebar: [
    'index',
    {
      type: 'category',
      label: 'Guia de uso',
      collapsed: false,
      items: [
        'guia/instalacao',
        'guia/cli',
        'guia/rss-txt',
        'guia/proxies',
      ],
    },
    {
      type: 'category',
      label: 'Arquitetura',
      collapsed: false,
      items: [
        'arquitetura/visao-geral',
        'arquitetura/feedlist',
        'arquitetura/fetcher',
        'arquitetura/parsers',
        'arquitetura/collector',
      ],
    },
    {
      type: 'category',
      label: 'Dados',
      items: [
        'dados/formato',
        'dados/relatorios',
        'dados/receitas',
      ],
    },
    {
      type: 'category',
      label: 'Automação (CI/CD)',
      items: [
        'automacao/weekly-news',
        'automacao/ci',
        'automacao/pages',
      ],
    },
    'testes',
    'contribuindo',
  ],
};

export default sidebars;

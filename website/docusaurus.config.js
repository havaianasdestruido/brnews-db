// @ts-check
// Documentação do brnews-db — servida em https://<usuario>.github.io/brnews-db/docs/
// A página inicial do projeto (em /brnews-db/) é um site Jekyll separado (pasta site/).

import { themes as prismThemes } from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'brnews-db',
  tagline: 'Notícias em português coletadas automaticamente de feeds RSS e páginas HTML',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  // URL de produção (GitHub Pages do repositório).
  url: 'https://havaianasdestruido.github.io',
  // O Docusaurus vive SOMENTE em /docs; a raiz /brnews-db/ é o site Jekyll.
  baseUrl: '/brnews-db/docs/',

  organizationName: 'havaianasdestruido',
  projectName: 'brnews-db',

  onBrokenLinks: 'throw',

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
    mermaid: true,
  },

  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    defaultLocale: 'pt-BR',
    locales: ['pt-BR'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          // Docs na raiz do site Docusaurus (que já está sob /docs).
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
          editUrl: 'https://github.com/havaianasdestruido/brnews-db/tree/main/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      image: 'img/docusaurus-social-card.jpg',
      navbar: {
        title: 'brnews-db',
        logo: {
          alt: 'brnews-db',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docsSidebar',
            position: 'left',
            label: 'Documentação',
          },
          {
            href: 'https://havaianasdestruido.github.io/brnews-db/',
            label: 'Início',
            position: 'right',
          },
          {
            href: 'https://github.com/havaianasdestruido/brnews-db',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Documentação',
            items: [
              { label: 'Visão geral', to: '/' },
              { label: 'Arquitetura', to: '/arquitetura/visao-geral' },
              { label: 'Formato dos dados', to: '/dados/formato' },
            ],
          },
          {
            title: 'Projeto',
            items: [
              {
                label: 'Página inicial (Jekyll)',
                href: 'https://havaianasdestruido.github.io/brnews-db/',
              },
              {
                label: 'Repositório no GitHub',
                href: 'https://github.com/havaianasdestruido/brnews-db',
              },
              {
                label: 'Dados (data/)',
                href: 'https://github.com/havaianasdestruido/brnews-db/tree/main/data',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} brnews-db. Documentação construída com Docusaurus; página inicial com Jekyll.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['bash', 'json', 'python', 'yaml'],
      },
    }),
};

export default config;

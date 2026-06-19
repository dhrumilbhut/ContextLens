import { defineConfig } from 'vitepress'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  title: 'ContextLens',
  description: 'Diagnose RAG hallucinations — retrieval failure vs generation failure, on every claim.',

  // Read .md files directly from the project root so no file copying or manual sync is needed.
  // README.md at the project root becomes the homepage; docs/*.md become the doc pages.
  srcDir: '../',

  srcExclude: [
    // Excluded by intent
    'docs/archive/**',
    'CLAUDE.md',
    'build-log.md',
    // Sub-projects and tooling — contain .md files we don't want to publish
    'contextlens-core/**',
    'frontend/**',
    'backend/**',
    'sdk/**',
    'sdk-validation/**',
    'landing/**',
    'mini-rag-app/**',
    'docs-site/**',
  ],

  rewrites: {
    'README.md': 'index.md',
  },

  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      {
        text: 'GitHub',
        link: 'https://github.com/dhrumilbhut/ContextLens',
      },
    ],

    sidebar: [
      {
        text: 'Getting Started',
        items: [
          { text: 'Build Order', link: '/docs/BUILD_ORDER' },
        ],
      },
      {
        text: 'Architecture & Design',
        items: [
          { text: 'Architecture', link: '/docs/ARCHITECTURE' },
          { text: 'Pipeline', link: '/docs/PIPELINE' },
          { text: 'Data Model', link: '/docs/DATA_MODEL' },
          { text: 'Key Decisions', link: '/docs/DECISIONS' },
        ],
      },
      {
        text: 'Building With ContextLens',
        items: [
          { text: 'SDK', link: '/docs/SDK' },
          { text: 'API Reference', link: '/docs/API' },
          { text: 'Dashboard', link: '/docs/DASHBOARD' },
        ],
      },
      {
        text: 'Operations',
        items: [
          { text: 'Auth', link: '/docs/AUTH' },
          { text: 'Metering', link: '/docs/METERING' },
          { text: 'Stack', link: '/docs/STACK' },
          { text: 'Cloud Future', link: '/docs/CLOUD_FUTURE' },
        ],
      },
    ],

    search: {
      provider: 'local',
    },

    socialLinks: [
      {
        icon: 'github',
        link: 'https://github.com/dhrumilbhut/ContextLens',
      },
    ],

    editLink: {
      pattern:
        'https://github.com/dhrumilbhut/ContextLens/edit/main/:path',
      text: 'Edit this page on GitHub',
    },

    footer: {
      message: 'Self-hosted. Your data never leaves your infrastructure.',
    },
  },

  vite: {
    resolve: {
      // When srcDir points outside the VitePress root, Rollup resolves imports
      // from the source file's directory (project root) rather than docs-site/node_modules.
      // Explicitly alias Vue to the local install to avoid resolution failures.
      alias: {
        vue: path.join(__dirname, '../node_modules/vue'),
        'vue/server-renderer': path.join(
          __dirname,
          '../node_modules/vue/server-renderer',
        ),
      },
    },
    server: {
      fs: {
        // Allow serving files from the project root (outside docs-site/)
        allow: ['..'],
      },
    },
  },
})

import { readdirSync } from 'node:fs';
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import pagefind from 'astro-pagefind';
import { unified } from '@astrojs/markdown-remark';
import rehypeRaw from 'rehype-raw';
import rehypeSlug from 'rehype-slug';
import { rehypeWikiLinks } from './plugins/rehype-wiki-links.mjs';
import { rehypeTables } from './plugins/rehype-tables.mjs';
import { rehypeFigures } from './plugins/rehype-figures.mjs';
import { collectAnchors } from './plugins/anchors.mjs';
import { SITE } from './src/site';

const CONTENT = './src/content/wiki';

const pages = new Set(
  readdirSync(CONTENT)
    .filter((name) => name.endsWith('.md'))
    .map((name) => name.replace(/\.md$/, '')),
);

export default defineConfig({
  // Only used to build absolute URLs for the sitemap.
  site: process.env.SITE_URL ?? 'https://example.com',
  trailingSlash: 'always',
  image: {
    // Source images run to 7728px wide, and the article column is at most
    // 46rem, so 1472 covers it at 2x.
    layout: 'constrained',
    responsiveStyles: true,
    breakpoints: [320, 640, 736, 1080, 1472, 2048],
  },
  integrations: [
    // The search page has no content of its own until a query is typed.
    sitemap({ filter: (page) => !page.endsWith('/search/') }),
    pagefind(),
  ],
  markdown: {
    processor: unified({
      rehypePlugins: [
        // The importer writes tables as HTML. Parsing that before the plugins
        // below run is what lets them see the tables and the links inside.
        rehypeRaw,
        rehypeTables(),
        rehypeFigures(),
        rehypeWikiLinks({ pages, homeId: SITE.homeId, anchors: collectAnchors(CONTENT) }),
        // Heading ids only. An anchor link inside a heading becomes part of the
        // heading's accessible name, and the contents list already links each.
        rehypeSlug,
      ],
    }),
  },
});

# Working on this repository

## What it is

A small static site — 20 pages — built from a DokuWiki export. A group wrote a fictional pandemic
scenario during a preparedness workshop, and this publishes their wiki read-only. It is a hobby
project, not production software: prefer the plain, obvious solution over the thorough one, and
don't add infrastructure it doesn't need.

## The one rule that matters

**Only publish text that is in the archive.** The wiki's pages are the content; nothing should
introduce summaries, introductions, captions or editorial framing of its own. One deliberate
exception: the fiction notice in the banner, and the `/about/` page it links to. The pages include
reports and a speech written in the register of real documents, so the site says plainly that none
of it is real and where it came from.

Images therefore carry `alt=""`. DokuWiki's image syntax holds no alt text and none was written for
them, so a screen reader passes over every picture on the site. Only one image has any text of its
own, the at-home test on `/tests_for_semvid-50/`, whose caption the wiki wrote.

## How content gets here

**`src/content/wiki/*.md` is the source now. Edit it directly.** The pages came out of the DokuWiki
export, but that import has run for the last time and `tools/import.py` is closed to further change.
Running it again would delete `src/content/wiki/` and `src/assets/` and write them afresh from an
archive, losing every edit made since.

What the importer left behind is worth knowing when reading a page:

- Tables are HTML, not Markdown, because merged cells cannot be expressed in GFM. `rehype-raw`
  therefore runs before the other rehype plugins, so they see those tables and the links inside them.
- An internal link is a bare page id — `[Timeline](timeline)` — which `plugins/rehype-wiki-links.mjs`
  turns into a route, or into red text when no page has that id.
- An image is a `<figure>` wrapping a Markdown image, carrying `data-align` and a `--figure-width`
  for where it sits and how wide it is.
- Media keeps the namespace it had in the wiki, so `src/assets/0/virus.jpg` is one of them.
  `src/images/` is where a picture that never came from the wiki goes.

`storage.zip` is not in git — it is tens of megabytes per export.

## Conventions worth keeping

- **Every page is styled identically.** There are no page types and no per-page flags. What varies
  is what the archive asked for: a figure gets the display width and the left/right float from its
  DokuWiki `{{ }}` syntax, and a table gets its merged cells. Both follow from the markup, not from
  which page it is on.
- **The main content path works without JavaScript.** Only two things use it, both enhancements that
  degrade cleanly: search, and click-to-enlarge on figures.
- **Accessibility is checked, not assumed.** `npm run test:a11y` runs axe-core over every route at
  desktop and phone widths, and should stay at zero violations. Every page has one `h1` and a
  heading outline that never skips a level. Links are underlined only on hover, so the link colours
  are pinned by contrast on both sides: 4.5:1 against every background they sit on, and 3:1 against
  the body text beside them. Changing a colour token means re-running the check.
- **One palette.** The site is light only: there is no dark mode and no theme switch, so a colour
  is written once.
- Pages are flat — no namespaces, no categories. Navigation is links, the `/all-pages/` index, and
  search.

## Practical notes

- `npm run format` runs Prettier over everything except `src/content/wiki/`, which is left alone so
  a re-import still produces exactly what is committed. Run it before committing.
- The page graph at the bottom of `/all-pages/` is derived from the pages themselves by
  `src/graph.ts`, laid out with d3-force during the build, so there is nothing to maintain when
  pages come and go. The layout is deterministic: the picture changes only when the links do.
- The site deploys at the domain root; there is no base path.
- Astro caches rendered Markdown in `node_modules/.astro`. After changing anything in `plugins/`,
  clear it (`rm -rf dist .astro node_modules/.astro`) or you will debug stale output.
- Every page is English. If one in another language appears, it needs a `lang` on `<html>`, and
  Pagefind will want `forceLanguage` so the search index stays unified.

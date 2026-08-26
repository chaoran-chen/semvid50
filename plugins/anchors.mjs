import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import GithubSlugger from 'github-slugger';

/** A section anchor as DokuWiki writes it, which is how the source links read. */
function dokuwikiAnchor(text) {
  return text
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_.-]/g, '')
    .replace(/_{2,}/g, '_')
    .replace(/^[_.-]+|[_.-]+$/g, '');
}

/** Heading text, with the inline Markdown that never reaches the id removed. */
function plainText(markdown) {
  return markdown
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`]/g, '')
    .trim();
}

/**
 * Map each page's DokuWiki section anchors onto the heading ids rehype-slug
 * will generate.
 *
 * The two schemes disagree — DokuWiki joins words with underscores, rehype-slug
 * with hyphens — so a cross-page link to a section in the source would
 * otherwise land at the top of the target page instead of at the section.
 * Deriving both forms from the same heading text keeps them in step, including
 * the counter rehype-slug appends to a repeated heading.
 */
export function collectAnchors(contentDir) {
  const anchors = new Map();

  for (const name of readdirSync(contentDir).filter((n) => n.endsWith('.md'))) {
    const body = readFileSync(join(contentDir, name), 'utf8').replace(/^---\n[\s\S]*?\n---\n/, '');
    const slugger = new GithubSlugger();
    const page = new Map();

    for (const match of body.matchAll(/^#{1,6}[ \t]+(.*)$/gm)) {
      const text = plainText(match[1]);
      page.set(dokuwikiAnchor(text), slugger.slug(text));
    }
    anchors.set(name.replace(/\.md$/, ''), page);
  }
  return anchors;
}

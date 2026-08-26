import { getCollection, type CollectionEntry } from 'astro:content';
import { SITE } from './site';

export type Page = CollectionEntry<'wiki'>;

/** All pages, ordered by title, as the all-pages index shows them. */
export async function allPages(): Promise<Page[]> {
  const pages = await getCollection('wiki');
  return pages.sort((a, b) => a.data.title.localeCompare(b.data.title, 'en'));
}

/**
 * The opening of a page's text, for the description a search engine or a chat
 * client shows. Taken from the page as rendered, so it is what the page says
 * and nothing else.
 */
export function summary(page: Page, limit = 200): string {
  const html = (page as { rendered?: { html?: string } }).rendered?.html ?? '';
  const text = html
    .replace(/<(figure|table)\b[\s\S]*?<\/\1>/g, '')
    .replace(/<span class="visually-hidden">[\s\S]*?<\/span>/g, '');
  const paragraph = /<p>([\s\S]*?)<\/p>/.exec(text)?.[1] ?? '';
  const plain = paragraph
    .replace(/<[^>]+>/g, '')
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
  if (plain.length <= limit) return plain;
  return (
    plain
      .slice(0, limit)
      .replace(/\s+\S*$/, '')
      .replace(/[,;:]$/, '') + '…'
  );
}

/** Every page except the one rendered at the site root. */
export async function articlePages(): Promise<Page[]> {
  return (await allPages()).filter((page) => page.id !== SITE.homeId);
}

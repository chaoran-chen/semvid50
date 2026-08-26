import { visit } from 'unist-util-visit';

/**
 * Turn the bare page ids the importer emits ("contact_tracing") into absolute
 * links, translating any fragment from DokuWiki's anchor scheme to the heading
 * id the build generates. A target with no matching page becomes text rather
 * than a link, since a link that goes nowhere is worse than useless with a
 * keyboard or a screen reader.
 */
export function rehypeWikiLinks({ pages, homeId, anchors }) {
  return () => (tree) => {
    visit(tree, 'element', (node) => {
      if (node.tagName !== 'a') return;
      const href = node.properties?.href;
      if (typeof href !== 'string' || href === '') return;

      if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//')) {
        const kind = /^(?:https?:)?\/\/(?:[a-z0-9-]+\.)*wikipedia\.org(?:[/:?#]|$)/i.test(href)
          ? 'external-wikipedia'
          : 'external';
        node.properties.class = [node.properties.class, kind].filter(Boolean).join(' ');
        node.properties.rel = 'noopener';
        return;
      }
      if (href.startsWith('#') || href.startsWith('/')) return;

      const [target, hash] = href.split('#');
      const resolved = hash ? (anchors.get(target)?.get(hash) ?? hash) : undefined;
      const fragment = resolved ? `#${resolved}` : '';

      if (target === homeId) {
        node.properties.href = `/${fragment}`;
        return;
      }
      if (pages.has(target)) {
        node.properties.href = `/${target}/${fragment}`;
        return;
      }

      node.tagName = 'span';
      node.properties = { class: 'wanted' };
      node.children.push({
        type: 'element',
        tagName: 'span',
        properties: { class: 'visually-hidden' },
        children: [{ type: 'text', value: ' (page does not exist)' }],
      });
    });
  };
}

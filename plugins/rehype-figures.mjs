import { visit } from 'unist-util-visit';

const isElement = (node, tagName) => node?.type === 'element' && node.tagName === tagName;

/**
 * Unwrap the paragraph Markdown puts around the image inside a figure, and tell
 * the browser how wide the image will actually be so it can pick a variant. A
 * figure spans the article column at most, and often much less, so the default
 * of `100vw` would have it fetch one twice as wide as it can show.
 */
export function rehypeFigures() {
  return () => (tree) => {
    visit(tree, 'element', (node) => {
      if (node.tagName !== 'figure') return;

      const width = /--figure-width:\s*(\d+)px/.exec(node.properties?.style ?? '')?.[1];
      const sizes = width
        ? `(min-width: ${width}px) ${width}px, 100vw`
        : '(min-width: 60rem) 46rem, 100vw';

      node.children = node.children.map((child) => {
        if (!isElement(child, 'p')) return child;
        const image = child.children.find((grandchild) => isElement(grandchild, 'img'));
        if (!image) return child;
        image.properties.sizes = sizes;
        return image;
      });
    });
  };
}

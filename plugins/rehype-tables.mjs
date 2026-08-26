import { visit } from 'unist-util-visit';

const isElement = (node, tagName) => node?.type === 'element' && node.tagName === tagName;
const rowsOf = (section) => section.children.filter((child) => isElement(child, 'tr'));

/** A table of nothing but two-cell data rows states a value for each of a set of terms. */
function keyValueRows(table) {
  if (table.children.some((child) => isElement(child, 'thead'))) return null;
  const body = table.children.find((child) => isElement(child, 'tbody'));
  const rows = body ? rowsOf(body) : [];
  const cells = rows.map((row) => row.children.filter((child) => isElement(child, 'td')));
  return rows.length && cells.every((row) => row.length === 2) ? cells : null;
}

/**
 * Give the key column of a key/value table its row headers, and let every other
 * table scroll on its own rather than pushing the page sideways.
 */
export function rehypeTables() {
  return () => (tree) => {
    visit(tree, 'element', (node, index, parent) => {
      if (node.tagName !== 'table' || !parent) return;

      const keyValue = keyValueRows(node);
      if (keyValue) {
        node.properties = { ...node.properties, class: 'key-value' };
        for (const [key] of keyValue) {
          key.tagName = 'th';
          key.properties = { ...key.properties, scope: 'row' };
        }
        return;
      }

      parent.children[index] = {
        type: 'element',
        tagName: 'div',
        properties: { class: 'scroll-box', tabIndex: 0 },
        children: [node],
      };
    });
  };
}

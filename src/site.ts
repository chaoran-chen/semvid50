export const SITE = {
  name: 'SEMViD-50 Wiki',
  /** The page rendered at the site root rather than at a route of its own. */
  homeId: 'semvid_50_pandemic',
} as const;

export function pageUrl(id: string): string {
  return id === SITE.homeId ? '/' : `/${id}/`;
}

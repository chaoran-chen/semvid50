import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationNodeDatum,
} from 'd3-force';
import { pageUrl } from './site';
import { allPages } from './wiki';

/** Node circle radius, and where the label under it starts and how it spaces. */
export const NODE_RADIUS = 7;
export const LABEL_TOP = 19;
export const LABEL_LINE = 14;

const LABEL_CHARS = 20; // where a label wraps
const LABEL_LINES = 4; // lines before the label is cut short
const CHAR_WIDTH = 5.72; // roughly, at the label's font size
const LABEL_PAD = 12; // clear space kept around a label
const ARROW = 10; // arrowhead length, in the same units

// Chosen by measuring the result: with these the 20 pages settle with no label
// overlapping another and only seven edges crossing a label, in a box narrow
// enough that the labels still render above 10px in the article column.
const LINK_DISTANCE = 220;
const CHARGE = -1400;
const TICKS = 700;

interface GraphNode {
  id: string;
  title: string;
  url: string;
  lines: string[];
  /** Ids of the pages this one links to. */
  to: string[];
  x: number;
  y: number;
}

interface GraphEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** Both pages link to the other, so the line gets an arrowhead at each end. */
  mutual: boolean;
}

interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  viewBox: string;
}

interface Placed extends SimulationNodeDatum {
  id: string;
  title: string;
  url: string;
  lines: string[];
  halfWidth: number;
  radius: number;
}

/**
 * Internal link targets in a page body.
 *
 * The importer normalises every internal link to a bare page id, so a target is
 * either one of those or something this graph ignores: an absolute URL, an
 * asset path, or a link to a page the wiki no longer has.
 */
const LINK_TARGET = /\]\(([^)\s#]+)[^)]*\)|href="([^"#]+)[^"]*"/g;

function linksFrom(body: string, ids: Set<string>, self: string): Set<string> {
  const targets = new Set<string>();
  for (const match of body.matchAll(LINK_TARGET)) {
    const target = match[1] ?? match[2];
    if (target !== self && ids.has(target)) targets.add(target);
  }
  return targets;
}

/** Break a title into label lines, greedily and on word boundaries. */
function wrapLabel(title: string): string[] {
  const lines: string[] = [];
  for (const word of title.split(/\s+/)) {
    const last = lines.at(-1);
    if (last !== undefined && `${last} ${word}`.length <= LABEL_CHARS) {
      lines[lines.length - 1] = `${last} ${word}`;
    } else {
      lines.push(word);
    }
  }
  if (lines.length <= LABEL_LINES) return lines;
  const kept = lines.slice(0, LABEL_LINES);
  kept[LABEL_LINES - 1] += '…';
  return kept;
}

/**
 * The wiki as a directed graph: a node per page, and an edge per pair of pages
 * where at least one links to the other.
 *
 * Node positions are settled here, at build time, so the page can serve the
 * graph as plain SVG with no script. d3-force is deterministic — a fixed-seed
 * generator and a phyllotaxis starting arrangement — so the same pages always
 * produce the same picture.
 */
export async function linkGraph(): Promise<Graph> {
  const pages = await allPages();
  const ids = new Set(pages.map((page) => page.id));
  const outgoing = new Map(
    pages.map((page) => [page.id, linksFrom(page.body ?? '', ids, page.id)] as const),
  );

  const placed: Placed[] = pages.map((page) => {
    const lines = wrapLabel(page.data.title);
    const halfWidth = (Math.max(...lines.map((line) => line.length)) * CHAR_WIDTH) / 2;
    return {
      id: page.id,
      title: page.data.title,
      url: pageUrl(page.id),
      lines,
      halfWidth,
      // Keep whole labels apart, not just the circles they hang from.
      radius: Math.max(halfWidth + LABEL_PAD, (LABEL_TOP + lines.length * LABEL_LINE) * 0.62),
    };
  });

  // One edge per connected pair: a mutual pair is a single line with an
  // arrowhead at each end rather than two lines on top of each other.
  const pairs: { source: string; target: string; mutual: boolean }[] = [];
  const seen = new Set<string>();
  for (const [from, targets] of outgoing) {
    for (const to of targets) {
      const key = [from, to].sort().join(' ');
      if (seen.has(key)) continue;
      seen.add(key);
      pairs.push({ source: from, target: to, mutual: outgoing.get(to)?.has(from) ?? false });
    }
  }

  const links = pairs.map((pair) => ({ ...pair }));
  const simulation = forceSimulation(placed)
    .force(
      'link',
      forceLink(links)
        .id((node) => (node as Placed).id)
        .distance(LINK_DISTANCE),
    )
    .force('charge', forceManyBody().strength(CHARGE))
    .force('collide', forceCollide<Placed>((node) => node.radius).iterations(3))
    .force('centre', forceCenter(0, 0))
    .stop();
  simulation.tick(TICKS);

  const at = new Map(placed.map((node) => [node.id, node]));
  const edges: GraphEdge[] = pairs.map(({ source, target, mutual }) => {
    const from = at.get(source)!;
    const to = at.get(target)!;
    const dx = to.x! - from.x!;
    const dy = to.y! - from.y!;
    // Stop the line short of each circle so the arrowhead meets its edge.
    const length = Math.hypot(dx, dy) || 1;
    const trim = (NODE_RADIUS + 2) / length;
    return {
      x1: round(from.x! + dx * trim),
      y1: round(from.y! + dy * trim),
      x2: round(to.x! - dx * trim),
      y2: round(to.y! - dy * trim),
      mutual,
    };
  });

  const nodes: GraphNode[] = placed.map((node) => ({
    id: node.id,
    title: node.title,
    url: node.url,
    lines: node.lines,
    to: [...(outgoing.get(node.id) ?? [])],
    x: round(node.x!),
    y: round(node.y!),
  }));

  return { nodes, edges, viewBox: boundingBox(placed).map(round).join(' ') };
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** The box the settled layout occupies, labels and arrowheads included. */
function boundingBox(placed: Placed[]): [number, number, number, number] {
  const pad = ARROW;
  const left = Math.min(...placed.map((node) => node.x! - node.halfWidth)) - pad;
  const right = Math.max(...placed.map((node) => node.x! + node.halfWidth)) + pad;
  const top = Math.min(...placed.map((node) => node.y!)) - NODE_RADIUS - pad;
  const bottom =
    Math.max(...placed.map((node) => node.y! + LABEL_TOP + node.lines.length * LABEL_LINE)) + pad;
  return [left, top, right - left, bottom - top];
}

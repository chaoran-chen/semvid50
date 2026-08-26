#!/usr/bin/env python3
"""Convert a DokuWiki storage volume into the Markdown that Astro builds from.

Markup conversion is pandoc's `dokuwiki` reader, run in a pinned container.
This script handles what pandoc cannot know: DokuWiki page-id semantics, the
titles and timestamps in `data/meta`, heading levels, and which media files a
page actually references.

Re-running rewrites the output in place. That output is tracked in git, so
`git diff` shows both what the source wiki changed and any hand edit the run
has replaced.

    python3 tools/import.py                 # storage/ -> src/content/wiki/
    python3 tools/import.py --out /tmp/new  # write elsewhere, to merge by hand
"""

import argparse
import fnmatch
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

PANDOC_IMAGE = "pandoc/core:3.5"
REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "tools/import-config.json"
ASSETS = REPO / "src/assets"
PUBLIC = REPO / "public"

# Site chrome, which no page references but the build needs: media id -> where
# the build expects the file.
CHROME = {"semvid-50_wiki-logo.png": ASSETS, "wiki/favicon.ico": PUBLIC}

WIKIPEDIA = "https://en.wikipedia.org/wiki/"

IMAGE_TOKEN = "xDOKUIMAGEx{}x"
TABLE_TOKEN = "xDOKUTABLEx{}x"
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$", re.M)
TABLE_LINE = re.compile(r"^[ \t]*[|^]")


# --------------------------------------------------------------------------- #
# DokuWiki semantics
# --------------------------------------------------------------------------- #

def clean_id(raw: str) -> str:
    """Normalise a link target the way DokuWiki's cleanID() does.

    Targets are written as free text as often as as page ids ("End of the
    SEMViD-50 public health emergency (speech)"), and only this maps them onto
    the files on disk.
    """
    text = raw.strip().strip("/:").replace("/", ":").lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_:.\-]", "", text)
    return re.sub(r"_{2,}", "_", text).strip("_-.")


def deslugify(page_id: str) -> str:
    """The title DokuWiki shows for a page with no heading and no metadata."""
    return page_id.replace("_", " ").strip().capitalize()


def meta_title(text: str) -> str | None:
    """The title DokuWiki recorded in a page's serialized PHP metadata file."""
    match = re.search(r's:5:"title";s:\d+:"(.*?)";', text, re.S)
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# Source reading
# --------------------------------------------------------------------------- #

def is_noise(name: str) -> bool:
    return any(part == "__MACOSX" or part.startswith("._") or part == ".DS_Store"
               for part in Path(name).parts)


class Source:
    """The unpacked DokuWiki storage volume."""

    def __init__(self, path: Path):
        self.path = path

    def read(self, rel: str) -> bytes | None:
        target = self.path / rel
        return target.read_bytes() if target.is_file() else None

    def read_text(self, rel: str) -> str:
        raw = self.read(rel)
        return raw.decode("utf-8", errors="replace") if raw is not None else ""

    def list(self, rel_dir: str) -> list[str]:
        """Paths of the files under `rel_dir`, relative to it."""
        base = self.path / rel_dir
        if not base.is_dir():
            return []
        return sorted(str(p.relative_to(base)) for p in base.rglob("*")
                      if p.is_file() and not is_noise(str(p.relative_to(base))))


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #

def media_id(raw: str) -> str:
    """A media reference as a path under `data/media`, namespaces included."""
    return raw.strip().strip(":").replace(":", "/")


def wikipedia_url(target: str) -> str:
    """The URL DokuWiki's `wp>` interwiki prefix expands to."""
    page, _, fragment = target.partition("#")
    encode = lambda part: urllib.parse.quote(part.strip().replace(" ", "_"), safe="")
    url = WIKIPEDIA + encode(page)
    return f"{url}#{encode(fragment)}" if fragment else url


def image_align(target: str, params: str) -> str | None:
    """Where an image sits: what the page asked for, else DokuWiki's padding.

    DokuWiki reads alignment from the padding inside the braces and ignores a
    `left`, `right` or `center` parameter, so a page that writes one gets the
    opposite of what it says. The parameter is the clearer statement of intent,
    so it wins.
    """
    for param in params.split("&"):
        if param.strip() in ("left", "right", "center"):
            return param.strip()
    left, right = target != target.lstrip(), target != target.rstrip()
    if left and right:
        return "center"
    if left:
        return "right"
    return "left" if right else None


def image_width(params: str) -> str | None:
    """The display width DokuWiki takes from a `?400` or `?400x300` parameter."""
    for param in params.split("&"):
        size = re.fullmatch(r"(\d+)(?:x\d+)?", param.strip())
        if size:
            return size.group(1)
    return None


def extract_images(body: str) -> tuple[str, list[dict]]:
    """Replace `{{image}}` syntax with tokens pandoc carries through verbatim.

    Left in place, pandoc emits raw `<img>` HTML and folds it into the
    surrounding paragraph; a token keeps each image its own block.
    """
    images: list[dict] = []

    def swap(match: re.Match) -> str:
        target, _, caption = match.group(1).partition("|")
        name, _, params = target.strip().partition("?")
        images.append({
            "name": media_id(name),
            "caption": caption.strip(),
            "align": image_align(target, params),
            "width": image_width(params),
        })
        return f"\n\n{IMAGE_TOKEN.format(len(images) - 1)}\n\n"

    return re.sub(r"\{\{([^}]*)\}\}", swap, body), images


def repair_links(body: str, log: list[str], page_id: str) -> str:
    """Undo the two ways a pasted link arrives with punctuation around it.

    "[[[url|text]]" has a bracket too many, and a URL pasted in from Markdown
    keeps the brackets it came with. Either way pandoc makes a link to nowhere,
    so both are worth naming rather than passing on. A trailing ")" is left
    alone: plenty of URLs end in one.
    """
    def brackets(match: re.Match) -> str:
        log.append(f"{page_id}: '{match.group(0)}' has a bracket too many, dropped")
        return "[["

    def wrapped(match: re.Match) -> str:
        log.append(f"{page_id}: unwrapped the pasted link to {match.group(1)[:60]}")
        return f"[[{match.group(1)}"

    body = re.sub(r"\[{3,}(?=[^\[])", brackets, body)
    return re.sub(r"\[\[[(\[]+\s*(https?://[^\]|]*?)\s*\]*(?=\s*[|\]])", wrapped, body)


def rewrite_link_targets(body: str, titles: dict[str, str], links: dict[str, str],
                         log: list[str], page_id: str) -> str:
    """Normalise link targets to page ids or URLs before pandoc sees them.

    A link written without display text gets the target page's title, as
    DokuWiki shows; the bare id would render as a slug too long to fit a narrow
    screen. `wp>` interwiki targets become encoded Wikipedia URLs, which pandoc
    does not do: it leaves the spaces in "wp>Reverse transcriptase" as they are,
    and a link destination cannot contain one.
    """

    def swap(match: re.Match) -> str:
        target, sep, text = match.group(1).partition("|")
        target = target.strip()

        if target.lower().startswith("wp>"):
            name = target[3:].strip()
            return f"[[{wikipedia_url(name)}|{text.strip() or name}]]"
        if not target:
            target = clean_id(text)
            log.append(f"{page_id}: empty link target, derived '{target}' from the link text")
        elif re.match(r"^[a-z][a-z0-9+.\-]*:", target):
            return match.group(0)  # external: pandoc handles it
        elif ">" in target:
            log.append(f"{page_id}: unsupported interwiki link '{target}'")
            return match.group(0)

        anchor = ""
        if "#" in target:
            target, _, fragment = target.partition("#")
            anchor = "#" + clean_id(fragment)

        page = clean_id(target)
        moved = links.get(page + anchor)
        if moved:
            log.append(f"{page_id}: '{page}{anchor}' has moved to '{moved}'")
            page, _, fragment = moved.partition("#")
            anchor = f"#{fragment}" if fragment else ""
        if not text.strip() and page in titles:
            sep, text = "|", titles[page]
        return f"[[{page}{anchor}{sep}{text}]]"

    return re.sub(r"\[\[([^\[\]]*?)\]\]", swap, body)


def pandoc(text: str, to: str = "gfm") -> str:
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", PANDOC_IMAGE,
         "-f", "dokuwiki", "-t", to, "--wrap=none"],
        input=text.encode("utf-8"), capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    # pandoc reads an apostrophe as an opening quote when the pairing confuses
    # it, and an opening quote can never follow a word character.
    return re.sub(r"(?<=\w)‘", "’", result.stdout.decode("utf-8"))


def normalise_headings(md: str, title: str) -> str:
    """Give the page a gap-free h2..h6 outline under the layout's h1.

    Source levels are inconsistent, and some pages reuse the top level both for
    the title and for a section further down, so they do not nest in an order
    that maps onto HTML. A stack gives each heading the next level below its
    nearest shallower ancestor, preserving the nesting without skipping a level.
    A leading heading that repeats the title is dropped, since the layout
    already renders the title as the h1.
    """
    first = HEADING.search(md)
    if first and first.group(2).strip().lower() == title.strip().lower():
        md = (md[:first.start()] + md[first.end():]).lstrip("\n")

    stack: list[tuple[int, int]] = []

    def rewrite(match: re.Match) -> str:
        source = len(match.group(1))
        while stack and stack[-1][0] >= source:
            stack.pop()
        level = min(stack[-1][1] + 1, 6) if stack else 2
        stack.append((source, level))
        return f"{'#' * level} {match.group(2)}"

    return HEADING.sub(rewrite, md)


def restore_images(md: str, images: list[dict], media: dict, log: list[str],
                   page_id: str) -> str:
    """Turn the image tokens back into figures.

    The image itself stays Markdown so that Astro resizes it; the figure around
    it carries the width and the alignment the page asked for.
    """
    for index, image in enumerate(images):
        cfg = media.get(image["name"], {})
        alt = cfg.get("alt", image["caption"])
        if not alt:
            log.append(f"{page_id}: image '{image['name']}' has no alt text")

        width = cfg.get("width", image["width"])
        attrs = f' data-align="{image["align"]}"' if image["align"] else ""
        if width:
            attrs += f' style="--figure-width: {width}px"'
        block = [f"<figure{attrs}>", "", f"![{alt}](../../assets/{image['name']})"]
        if image["caption"]:
            block += ["", f"<figcaption>{html.escape(image['caption'])}</figcaption>"]
        block += ["", "</figure>"]

        replacement = "\n".join(block)
        md = re.sub(rf"^\\?{re.escape(IMAGE_TOKEN.format(index))}$",
                    lambda _: replacement, md, flags=re.M)
    return md


# --------------------------------------------------------------------------- #
# Tables
#
# pandoc's dokuwiki reader ignores the syntax for merged cells and for header
# cells outside the first row, and GFM has no way to express either, so tables
# are parsed here and written as HTML.
# --------------------------------------------------------------------------- #

def cell_align(raw: str) -> str | None:
    """DokuWiki aligns a cell by the padding around its text."""
    left = len(raw) - len(raw.lstrip(" "))
    right = len(raw) - len(raw.rstrip(" "))
    if not raw.strip():
        return None
    if left >= 2 and right >= 2:
        return "center"
    if left >= 2:
        return "right"
    return "left" if right >= 2 else None


def cell_marks(line: str) -> list[tuple[int, str]]:
    """Where the cell delimiters are, ignoring the `|` inside a link."""
    masked = re.sub(r"\[\[.*?\]\]|\{\{.*?\}\}", lambda m: "-" * len(m.group()), line)
    return [(m.start(), m.group()) for m in re.finditer(r"[|^]", masked)]


def parse_table(lines: list[str]) -> list[list[dict]]:
    """Rows of cells, with `^^` merged into a colspan and `:::` into a rowspan."""
    rows = []
    for line in lines:
        line = line.strip()
        marks = cell_marks(line)
        cells: list[dict] = []
        for (start, mark), (end, _) in zip(marks, marks[1:]):
            raw = line[start + 1:end]
            if not raw.strip() and cells:
                cells[-1]["colspan"] += 1
                continue
            cells.append({"tag": "th" if mark == "^" else "td", "raw": raw,
                          "colspan": 1, "rowspan": 1, "align": cell_align(raw)})
        rows.append(cells)

    # A cell holding ":::" continues the cell above it, which the column it
    # starts in identifies.
    columns = []
    for row in rows:
        start = 0
        positions = {}
        for cell in row:
            positions[start] = cell
            start += cell["colspan"]
        columns.append(positions)
    for index, positions in enumerate(columns):
        for column, cell in positions.items():
            if cell["raw"].strip() != ":::":
                continue
            cell["merged"] = True
            for above in reversed(columns[:index]):
                target = above.get(column)
                if target and not target.get("merged"):
                    target["rowspan"] += 1
                    break
    return rows


def extract_tables(body: str) -> tuple[str, list[list[list[dict]]]]:
    """Replace each table with a token pandoc carries through verbatim."""
    tables: list[list[list[dict]]] = []
    out, block = [], []

    def flush():
        if block:
            tables.append(parse_table(block))
            out.append(f"\n{TABLE_TOKEN.format(len(tables) - 1)}\n")
            block.clear()

    for line in body.split("\n"):
        if TABLE_LINE.match(line):
            block.append(line)
            continue
        flush()
        out.append(line)
    flush()
    return "\n".join(out), tables


def table_cells(tables: list[list[list[dict]]]):
    for rows in tables:
        for row in rows:
            for cell in row:
                if not cell.get("merged"):
                    yield cell


def convert_cells(tables: list[list[list[dict]]]) -> None:
    """Convert every cell's inline markup in one pandoc run, split on rules."""
    cells = list(table_cells(tables))
    if not cells:
        return
    document = "\n\n----\n\n".join(cell["raw"].strip() for cell in cells)
    chunks = pandoc(document, "html").split("<hr />")
    if len(chunks) != len(cells):
        raise RuntimeError(f"converted {len(chunks)} table cells, expected {len(cells)}")
    for cell, chunk in zip(cells, chunks):
        cell["html"] = re.sub(r"</?p>", "", chunk).strip()


def head_rows(rows: list[list[dict]]) -> int:
    """How many leading rows hold nothing but header cells."""
    count = 0
    for row in rows:
        cells = [cell for cell in row if not cell.get("merged")]
        if not cells or any(cell["tag"] == "td" for cell in cells):
            break
        count += 1
    # An all-header table still needs a body to put its rows in.
    return count if count < len(rows) else 1


def table_html(rows: list[list[dict]]) -> str:
    head = head_rows(rows)
    out = ["<table>"]
    for section, group in (("thead", rows[:head]), ("tbody", rows[head:])):
        if not group:
            continue
        out.append(f"<{section}>")
        for row in group:
            out.append("<tr>")
            first = True
            for cell in row:
                if cell.get("merged"):
                    continue
                attrs = ""
                if cell["tag"] == "th":
                    if section == "thead":
                        attrs += ' scope="colgroup"' if cell["colspan"] > 1 else ' scope="col"'
                    elif first:
                        attrs += ' scope="rowgroup"' if cell["rowspan"] > 1 else ' scope="row"'
                if cell["colspan"] > 1:
                    attrs += f' colspan="{cell["colspan"]}"'
                if cell["rowspan"] > 1:
                    attrs += f' rowspan="{cell["rowspan"]}"'
                if cell["align"]:
                    attrs += f' style="text-align: {cell["align"]}"'
                out.append(f'<{cell["tag"]}{attrs}>{cell["html"]}</{cell["tag"]}>')
                first = False
            out.append("</tr>")
        out.append(f"</{section}>")
    out.append("</table>")
    return "\n".join(out)


def restore_tables(md: str, tables: list[list[list[dict]]]) -> str:
    for index, rows in enumerate(tables):
        html = table_html(rows)
        md = re.sub(rf"^\\?{re.escape(TABLE_TOKEN.format(index))}$",
                    lambda _: html, md, flags=re.M)
    return md


def front_matter(fields: dict) -> str:
    def quote(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = [f"{key}: {quote(value)}" for key, value in fields.items()]
    return "---\n" + "\n".join(lines) + "\n---\n"


# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", default=str(REPO / "storage"),
                        help="the unpacked DokuWiki storage directory")
    parser.add_argument("--out", default=str(REPO / "src/content/wiki"))
    args = parser.parse_args()

    source = Source(Path(args.source))
    config = json.loads(CONFIG.read_text())
    media_cfg = config["media"]
    links = config["links"]

    def page_id_of(name: str) -> str:
        return Path(name).with_suffix("").as_posix().replace("/", ":")

    txt_files = [n for n in source.list("data/pages") if n.endswith(".txt")]
    excluded = sorted(page_id_of(n) for n in txt_files
                      if any(fnmatch.fnmatch(page_id_of(n), p) for p in config["exclude"]))
    page_files = [n for n in txt_files if page_id_of(n) not in excluded]

    # A namespaced id would put a colon in the filename and the route. The wiki
    # is flat, so this means a new namespace needs a decision, not a guess.
    namespaced = sorted(pid for pid in map(page_id_of, page_files) if ":" in pid)
    if namespaced:
        print("pages in a namespace, which the site has no routes for:", file=sys.stderr)
        for page_id in namespaced:
            print(f"  {page_id}", file=sys.stderr)
        print('add them to "exclude" in the config, or add namespace support.', file=sys.stderr)
        return 1

    bodies = {page_id_of(n): source.read_text(f"data/pages/{n}") for n in page_files}
    meta_titles = {pid: meta_title(source.read_text(f"data/meta/{pid}.meta")) for pid in bodies}

    def title_of(page_id: str) -> str:
        heading = re.match(r"\s*=+\s*(.*?)\s*=+\s*$", bodies[page_id].split("\n")[0])
        return (meta_titles[page_id]
                or (heading.group(1).strip() if heading else None)
                or deslugify(page_id))

    # Every title has to be known before any page is converted, so that a link
    # written without display text can be given the target page's title.
    titles = {pid: title_of(pid) for pid, body in bodies.items() if body.strip()}

    out = Path(args.out)
    for directory in (out, ASSETS):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    log: list[str] = []
    dead: dict[str, list[str]] = {}
    referenced: set[str] = set()

    for page_id, body in bodies.items():
        if not body.strip():
            log.append(f"{page_id}: empty page, skipped")
            continue

        body, images = extract_images(body)
        body = rewrite_link_targets(repair_links(body, log, page_id), titles, links, log, page_id)
        body, tables = extract_tables(body)
        convert_cells(tables)
        referenced.update(image["name"] for image in images)

        md = normalise_headings(pandoc(body), titles[page_id])
        md = restore_images(md, images, media_cfg, log, page_id)
        md = restore_tables(md, tables)

        for match in re.finditer(r"\[\[([^\[\]|#]+)(#[^\[\]|]*)?", body):
            target = match.group(1)
            if not re.match(r"^[a-z][a-z0-9+.\-]*:", target) and target not in titles:
                dead.setdefault(target + (match.group(2) or ""), []).append(page_id)

        head = front_matter({"id": page_id, "title": titles[page_id]})
        (out / f"{page_id}.md").write_text(head + "\n" + md.strip() + "\n")

    media_files = source.list("data/media")
    wanted = sorted(referenced)
    for name, root in [(n, ASSETS) for n in wanted] + list(CHROME.items()):
        blob = source.read(f"data/media/{name}")
        if blob is None:
            log.append(f"media '{name}' is referenced but not in the archive")
            continue
        target = root / (Path(name).name if root is PUBLIC else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)

    unused = sorted(n for n in media_files
                    if n not in wanted and n not in CHROME and not n.startswith("wiki/")
                    and n != "_dummy")

    print(f"{len(titles)} pages -> {out}")
    if excluded:
        print(f"{len(excluded)} pages excluded by config: {', '.join(excluded)}")
    print(f"{len(wanted)} media files -> {ASSETS}")
    if unused:
        print("\nnot published (no page references them):")
        for name in unused:
            print(f"  {name}")
    if dead:
        print("\nlinks to pages the wiki no longer has:")
        for target, pages in sorted(dead.items()):
            print(f"  {target} <- {', '.join(sorted(set(pages)))}")
    stale = sorted(set(links) - {m.split(":")[1].split("'")[1] for m in log if "has moved to" in m})
    if stale:
        print("\nredirects in the config that nothing needed:")
        for target in stale:
            print(f"  {target}")
    if log:
        print("\nnotes:")
        for line in log:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

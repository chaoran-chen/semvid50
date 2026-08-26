# SEMViD-50 Wiki

A read-only static site of the fictional pandemic scenario a preparedness workshop wrote in its DokuWiki.

## Running it locally

Needs Node 22.12+ and npm.

```sh
npm install
npm run dev      # http://localhost:4321
npm run build    # static site into dist/
npm run preview  # serve the built site
npm run format   # Prettier over the repository
```

Pages live in `src/content/wiki/` as Markdown and can be edited directly.

## Running it in Docker

Builds the site and serves it with nginx, on <http://localhost:8080>:

```sh
docker build -t semvid50wiki .
docker run --rm -p 8080:80 semvid50wiki
```

Nothing but this repository is needed — the pages are committed, so the image does not import
anything. Add `--build-arg SITE_URL=https://example.org` to put the real address in the sitemap.

## Re-importing from DokuWiki

The pages are generated from a DokuWiki export. To take in a newer one, put its `storage.zip` in the
repository root and run:

```sh
unzip -q storage.zip -x '__MACOSX/*'
npm run import
git diff src/content/wiki/
```

This needs Python 3.10+ and Docker, which runs pandoc. It rewrites `src/content/wiki/`, so read the
diff before committing: it shows what the wiki changed and anything you had edited by hand.

`tools/import-config.json` holds the few things the archive cannot supply — which pages to skip, and
alt text for images.

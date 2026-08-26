/**
 * Accessibility check: runs axe-core over every built route, at a desktop and a
 * phone viewport.
 *
 * Needs a built site being served, and a Chromium to drive:
 *
 *   npm run build
 *   npm run preview &
 *   npm run test:a11y
 *
 * Set CHROME_PATH if Playwright's own browser is not installed
 * (`npx playwright install chromium` fetches it).
 */
import { readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { chromium } from 'playwright';

const require = createRequire(import.meta.url);
const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

const origin = process.env.PREVIEW_ORIGIN ?? 'http://127.0.0.1:5002';

// Every route the build produced, plus the search page with results and with
// none, which the route on its own does not exercise.
const routes = [
  '',
  '404.html',
  'search/?q=vector',
  'search/?q=zzzznomatch',
  ...readdirSync('dist', { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !['_astro', 'pagefind'].includes(entry.name))
    .map((entry) => `${entry.name}/`),
];

const viewports = [
  { name: 'desktop', viewport: { width: 1280, height: 900 } },
  { name: 'mobile', viewport: { width: 360, height: 720 } },
];

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: ['--no-sandbox'],
});

let violations = 0;
let checks = 0;

for (const { name, viewport } of viewports) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();

  for (const route of routes) {
    await page.goto(`${origin}/${route}`, { waitUntil: 'load' });
    // A query page has nothing to check until the index has loaded and the
    // outcome has been announced.
    if (route.includes('?q='))
      await page.waitForFunction(
        () =>
          /matching|No pages match/.test(
            document.getElementById('search-status')?.textContent ?? '',
          ),
        null,
        { timeout: 10000 },
      );
    await page.addScriptTag({ content: axeSource });
    const result = await page.evaluate(() =>
      window.axe.run(document, { resultTypes: ['violations'] }),
    );
    checks++;

    for (const violation of result.violations) {
      violations++;
      console.log(
        `FAIL ${name} /${route} [${violation.impact}] ${violation.id}: ${violation.help}`,
      );
      for (const node of violation.nodes.slice(0, 3))
        console.log(`       ${node.target.join(' ')}`);
    }
  }
  await context.close();
}

await browser.close();
console.log(`${checks} page-checks across ${routes.length} routes, ${violations} violations`);
process.exit(violations === 0 ? 0 : 1);

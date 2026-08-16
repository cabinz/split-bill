/**
 * Screenshots and a PDF, for looking at.
 *
 * The smoke test can tell that a figure is on the page. It cannot tell whether the
 * page is any good -- whether a column is squeezed, a chart label collides with its
 * axis, or the printed第二 page starts with an orphaned table header. That needs eyes,
 * so this produces the artefacts to use them on.
 *
 *   node e2e/shots.mjs --port 8765 --out /tmp/shots
 */
import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import fs from 'node:fs/promises'
import path from 'node:path'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const index = args.indexOf(`--${name}`)
  return index >= 0 ? args[index + 1] : fallback
}

const PORT = opt('port', '8765')
const OUT = path.resolve(opt('out', '/tmp/splitbill-shots'))
const HERE = path.dirname(fileURLToPath(import.meta.url))
const BILL = path.resolve(HERE, opt('bill', '../../tests/fixtures/bill_realistic.csv'))

await fs.mkdir(OUT, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({
  viewport: { width: 1280, height: 900 },
  deviceScaleFactor: 2,
})

await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: 'networkidle' })
await page.screenshot({ path: path.join(OUT, '00-empty.png') })

await page.locator('input[type=file]').setInputFiles(BILL)
const confirm = page.getByRole('button', { name: 'Confirm and view report' })
await confirm.waitFor({ state: 'visible', timeout: 30000 })
await page.waitForFunction(() => {
  const button = [...document.querySelectorAll('button')]
    .find((item) => item.textContent?.includes('Confirm and view report'))
  return button && !button.disabled
})
await page.locator('#import').screenshot({ path: path.join(OUT, '01-import-ready.png') })
await confirm.click()
await page.waitForSelector('#details', { timeout: 30000 })
// ECharts lays out on the next frame or two.
await page.waitForTimeout(900)

await page.screenshot({ path: path.join(OUT, '01-full.png'), fullPage: true })

for (const id of ['overview', 'members', 'settle', 'categories', 'details']) {
  const section = page.locator(`.screen-root #${id}`)
  if (await section.count()) {
    await section.scrollIntoViewIfNeeded()
    await page.waitForTimeout(250)
    await section.screenshot({ path: path.join(OUT, `section-${id}.png`) })
  }
}

// The settlement graph on its own. Its layout is a judgement about readability that no
// assertion covers -- whether a name collides with an amount, whether an arrow looks
// like it starts at the wrong dot -- so it gets its own frame to be looked at in.
// Scoped to the screen root: the print view has its own copy of this chart, mounted
// off-screen, and an unscoped selector matches both.
for (const name of ['settlement-graph', 'pool-sankey', 'category-pie',
                    'category-by-member']) {
  const chart = page.locator(`.screen-root [data-chart="${name}"]`)
  if (await chart.count()) {
    await chart.scrollIntoViewIfNeeded()
    await page.waitForTimeout(250)
    await chart.screenshot({ path: path.join(OUT, `chart-${name}.png`) })
  }
}

// An opened fold with a paged table in it: the part a suspicious member reads, and the one
// whose controls -- pager, search, column filters -- no assertion can judge the layout of.
await page.locator('#allocation > summary').click()
await page.waitForTimeout(250)
await page.locator('#allocation').screenshot({ path: path.join(OUT, 'section-allocation.png') })

// One member's records, chosen with the picker rather than by expanding a row.
await page.locator('#statements').scrollIntoViewIfNeeded()
await page.waitForTimeout(200)
await page.locator('#statements').screenshot({ path: path.join(OUT, 'section-statements.png') })

// "As me", which focuses the settlement on one person.
await page.selectOption('#as-me', '甲')
await page.waitForTimeout(200)
await page.locator('.screen-root #settle').screenshot(
  { path: path.join(OUT, 'section-as-me.png') })

// The print view needs no preparation any more -- it is mounted from the moment there is a
// report and laid out at the paper's width, so there is nothing to open and nothing to
// re-measure. What there is, is a signal saying it has finished drawing, and waiting for
// that is what this script has instead of the fixed delay it used to guess with.
await page.emulateMedia({ media: 'print' })
await page.waitForFunction(
  () => document.documentElement.dataset.printReady === 'true',
  null,
  { timeout: 30000 },
)
await page.pdf({
  path: path.join(OUT, 'report.pdf'),
  format: 'A4',
  printBackground: true,
  margin: { top: '15mm', bottom: '15mm', left: '15mm', right: '15mm' },
})
await page.screenshot({ path: path.join(OUT, '02-print-view.png'), fullPage: true })
await page.emulateMedia({ media: 'screen' })

// The preview window: the print view on a screen, and the thing a reader is most likely to
// look at before committing paper to it. Opened through the export dialog rather than by
// navigating to the URL, because it asks its opener for the report and a directly-opened
// one has no opener to ask.
await page.getByRole('button', { name: /Print \/ save as PDF|打印 \/ 另存为 PDF/ }).click()
const [previewWindow] = await Promise.all([
  page.context().waitForEvent('page'),
  page.getByRole('dialog').getByRole('button', { name: /^(Preview|预览)$/ }).click(),
])
await previewWindow.setViewportSize({ width: 1100, height: 1400 })
await previewWindow.waitForFunction(
  () => document.documentElement.dataset.printReady === 'true',
  null,
  { timeout: 30000 },
)
await previewWindow.screenshot({ path: path.join(OUT, '03-print-preview.png') })
await previewWindow.screenshot({
  path: path.join(OUT, '03-print-preview-full.png'),
  fullPage: true,
})
await previewWindow.close()

await browser.close()
console.log(`wrote ${OUT}`)

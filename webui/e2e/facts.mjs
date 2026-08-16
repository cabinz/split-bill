/**
 * The figures a report contains, read out of a rendered DOM.
 *
 * Two jobs, and they are the same job at two points in time:
 *
 *   * **Phase 0 of the decoupling plan.** Before the print view was split out of the
 *     screen view, this recorded what the one shared DOM produced. That record is what
 *     made the split provable rather than hopeful -- the question "did anything change?"
 *     has an answer other than looking at a PDF.
 *   * **Ongoing cross-assertion.** Now that there are two DOMs, both are read with the
 *     same function and the two results must be identical. Which is the plan's data
 *     consistency requirement (§9), enforced rather than intended.
 *
 * The facts are anchored on `data-fact` / `data-table` / `data-row` / `data-cell`
 * attributes rather than on positions in the markup, because the two views deliberately
 * differ in structure: the screen has interactive controls that paper has no use for,
 * and the print appendix has no "show all rows" button. Anchoring on `nth-child` would
 * make every layout change look like an arithmetic change.
 *
 * Long tables are compared by row count, endpoints and a hash of every cell. A diff
 * that says "row 341 of the ledger differs" is more use than 668 rows of output, and
 * this is checked in CI rather than read.
 *
 *   node e2e/facts.mjs --port 8765 [--out facts.json]
 */
import { chromium } from 'playwright'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import fs from 'node:fs/promises'
import path from 'node:path'

/** Runs in the browser. Kept as a string-serialisable function for `page.evaluate`. */
export function readFacts(rootSelector) {
  const root = document.querySelector(rootSelector)
  if (!root) return { error: `no ${rootSelector}` }

  const clean = (node) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim()

  const facts = {}
  for (const node of root.querySelectorAll('[data-fact]')) {
    facts[node.dataset.fact] = clean(node)
  }

  /** The cells of every marked row, as a matrix. For tables short enough to read. */
  const rows = (name) =>
    [...root.querySelectorAll(`[data-row="${name}"]`)].map((row) =>
      [...row.querySelectorAll('[data-cell]')].map((cell) => clean(cell)),
    )

  /**
   * A long table: how many rows it has, its first page, and a digest of what it rendered.
   *
   * `count` is what the table says it *contains*, not what it has drawn. The screen's
   * checking tables are paged -- 10 of 668 rows in the DOM -- so a bare row count would
   * report the page size and make "the two views agree" trivially false. They publish the
   * real total as `data-total-rows`; the print tables render everything, so for them the two
   * are the same number.
   *
   * `head` is there for the same reason. The full digests cannot match across a paged view
   * and a complete one, so the cross-check is: the same declared total, and the same first
   * page in the same order. `digest` still earns its place within one view -- printing must
   * not alter the printed appendix, whatever the screen is doing.
   *
   * Cells join on the ASCII unit separator and rows on the record separator, because
   * no cell can contain either. Joining on the empty string would give ["1", "23"] and
   * ["12", "3"] the same digest, which is the one thing a digest meant to catch a
   * shifted column must not do.
   */
  const UNIT = '\u001f'
  const RECORD = '\u001e'
  /** How many leading rows the two views are compared row for row. A screen page is 10. */
  const HEAD = 10
  const bulk = (name) => {
    const all = [...root.querySelectorAll(`[data-row="${name}"]`)]
    const text = all.map((row) =>
      [...row.children].map((cell) => clean(cell)).join(UNIT),
    )
    // What the table says it contains, read from the wrapper of a paged one. Absent on a
    // print table, whose rendered rows are all of them.
    const declared = all[0]
      ?.closest('[data-total-rows]')
      ?.getAttribute('data-total-rows')
    return {
      count: declared === undefined || declared === null ? all.length : Number(declared),
      rendered: all.length,
      first: text[0] ?? null,
      last: text.at(-1) ?? null,
      head: text.slice(0, HEAD),
      // A digest rather than the rows: 668 ledger rows is not a diff anybody reads.
      digest: text.join(RECORD),
    }
  }

  const pool = root.querySelector('[data-pool-in]')

  /** Sections of one kind, by the `data-part` they carry, print prefixes stripped. */
  const partsOf = (part) =>
    [...root.querySelectorAll(`section[id][data-part="${part}"]`)].map((section) =>
      section.id.replace(/^print-/, ''),
    )

  return {
    sections: [...root.querySelectorAll('section[id]')].map((section) =>
      section.id.replace(/^print-/, ''),
    ),
    // The body: the part the two views must agree about section for section. The checking
    // tables are deliberately not in here, being one numbered section on screen and several
    // lettered appendices on paper.
    body: partsOf('body'),
    // The screen's checking section, and the print view's appendices: the same content in
    // the two forms it legitimately takes.
    checking: partsOf('checking'),
    appendices: [...root.querySelectorAll('section[data-appendix]')].map(
      (section) => section.dataset.appendix,
    ),
    facts,
    positions: rows('position'),
    settlement: rows('transfer'),
    lendingEdges: rows('edge'),
    // Also as a bulk table: the screen pages it, so 28 pairs are 10 rows in the DOM.
    lending: bulk('edge'),
    ledger: bulk('ledger'),
    sheet: bulk('sheet'),
    memberRecords: bulk('member-record'),
    pool: pool
      ? {
          in: pool.dataset.poolIn,
          out: pool.dataset.poolOut,
          paysIn: root.querySelectorAll('[data-pool-row="in"]').length,
          drawsOut: root.querySelectorAll('[data-pool-row="out"]').length,
        }
      : null,
    charts: root.querySelectorAll('.chart svg').length,
    // Which of the named charts drew something, by `data-chart`. Section 5's two
    // graphs have their own density thresholds and paper's are stricter, so the two
    // views can legitimately differ here -- and when they do, the test needs to say
    // *which* chart is missing rather than that a count changed.
    namedCharts: [...root.querySelectorAll('[data-chart]')]
      .filter((node) => node.querySelector('svg'))
      .map((node) => node.dataset.chart)
      .sort(),
    canvases: root.querySelectorAll('canvas').length,
  }
}

/** Replace the long digests with short hashes, so a stored baseline is readable. */
export function digestFacts(facts) {
  const shorten = (bulk) =>
    bulk && {
      ...bulk,
      digest: createHash('sha256').update(bulk.digest).digest('hex').slice(0, 16),
    }
  return {
    ...facts,
    lending: shorten(facts.lending),
    ledger: shorten(facts.ledger),
    sheet: shorten(facts.sheet),
    memberRecords: shorten(facts.memberRecords),
  }
}

/** Import the fixture bill and confirm it, leaving the report on screen. */
export async function openReport(page, base, bill) {
  await page.goto(base, { waitUntil: 'networkidle' })
  await page.locator('input[type=file]').setInputFiles(bill)
  const confirm = page.getByRole('button', { name: 'Confirm and view report' })
  await confirm.waitFor({ state: 'visible', timeout: 30000 })
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.includes('Confirm and view report'))
    return button && !button.disabled
  })
  await confirm.click()
  // The last section of the report, whatever it is numbered.
  await page.waitForSelector('#details', { timeout: 30000 })
  // ECharts lays out on the next frame or two.
  await page.waitForTimeout(900)
}

export const FIXTURE_BILL = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../tests/fixtures/bill_realistic.csv',
)

// Run directly: record one view's facts, for eyeballing or for a baseline.
//
//   node e2e/facts.mjs --port 8765                        # the screen view
//   node e2e/facts.mjs --port 8765 --root '.print-root'   # the printed report
//
// The two must be identical, which `print.mjs` asserts. This is for looking at one of
// them, or for keeping a baseline across a change that should not have altered either.
if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2)
  const opt = (name, fallback) => {
    const index = args.indexOf(`--${name}`)
    return index >= 0 ? args[index + 1] : fallback
  }
  const port = opt('port', '8765')
  const out = opt('out', null)

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  await openReport(page, `http://127.0.0.1:${port}`, FIXTURE_BILL)
  const facts = digestFacts(
    await page.evaluate(
      ([source, selector]) => new Function(`return (${source})`)()(selector),
      [readFacts.toString(), opt('root', '.screen-root')],
    ),
  )
  await browser.close()

  const json = JSON.stringify(facts, null, 2)
  if (out) {
    await fs.writeFile(out, `${json}\n`)
    console.log(`wrote ${out}`)
  } else {
    console.log(json)
  }
}

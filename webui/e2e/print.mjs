/**
 * The printed report: complete, isolated from the screen, and the same figures.
 *
 * This is the suite the decoupling was for. `smoke.mjs` checks the page works; this checks
 * the three properties the split is supposed to guarantee, each of which was previously
 * either unenforced or enforced by a comment:
 *
 *   1. **The two views agree.** Both DOMs are read by the same function in `facts.mjs` and
 *      the results have to be identical -- every total, every settlement row, a digest of
 *      all 668 ledger rows. This is the check that would catch the print view drifting.
 *   2. **The print view is complete.** Every section, every appendix row, headers repeated
 *      across pages, footers not repeated, charts as SVG, no clipping.
 *   3. **The print view ignores screen state.** Filter the settlement to one member,
 *      collapse everything, scroll to the bottom -- the printed report does not change. And
 *      printing does not change the screen back, which the old implementation could not
 *      promise because it mutated the DOM and restored it afterwards.
 *
 *   node e2e/print.mjs --port 8765
 */
import { chromium } from 'playwright'
import { FIXTURE_BILL, digestFacts, openReport, readFacts } from './facts.mjs'

const args = process.argv.slice(2)
const portIndex = args.indexOf('--port')
const PORT = portIndex >= 0 ? args[portIndex + 1] : '8765'
const BASE = `http://127.0.0.1:${PORT}`

let failures = 0
const check = (label, condition, detail = '') => {
  if (condition) {
    console.log(`  ok   ${label}`)
  } else {
    console.log(`  FAIL ${label}${detail ? `  -- ${detail}` : ''}`)
    failures += 1
  }
}

/** Read the fact set out of one of the two roots. */
async function facts(page, selector) {
  return digestFacts(
    await page.evaluate(
      ([source, root]) => new Function(`return (${source})`)()(root),
      [readFacts.toString(), selector],
    ),
  )
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })

const consoleErrors = []
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('pageerror', (error) => consoleErrors.push(String(error)))

await openReport(page, BASE, FIXTURE_BILL)

console.log('\n1. the print view is mounted without anybody asking')
// Because Ctrl-P does not call our code. A print view that only existed after a click
// would make the keyboard shortcut print a blank sheet.
check('a print root exists as soon as there is a report',
      (await page.locator('.print-host .print-root').count()) === 1)
check('it is hidden from assistive technology, being a second copy of the same report',
      (await page.locator('.print-host').getAttribute('aria-hidden')) === 'true')
// Not `isVisible()`: it is deliberately laid out rather than `display: none`, because
// ECharts measures its container and a chart in a hidden box renders an empty SVG. So the
// property to check is that it is outside the viewport, not that it is unrendered.
check('it is laid out outside the viewport rather than hidden',
      await page.evaluate(() => {
        const box = document.querySelector('.print-host .print-root')?.getBoundingClientRect()
        return !!box && box.width > 100 && box.right < 0
      }))
check('and it does not make the page scroll sideways',
      await page.evaluate(() =>
        document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1))
check('it is laid out at the paper’s text width, so its charts need no resizing',
      await page.evaluate(() => {
        const width = document.querySelector('.print-host .print-root')
          ?.getBoundingClientRect().width ?? 0
        // A4's 210mm less 15mm margins each side, in CSS pixels at 96dpi.
        return Math.abs(width - (180 / 25.4) * 96) < 2
      }))
check('the ready signal was raised',
      (await page.locator('html').getAttribute('data-print-ready')) === 'true')

console.log('\n2. the two views agree on every figure')
// The default export includes the per-member statements appendix, so that the two views can
// be compared table for table. The screen always shows all four checking tables.
await page.getByRole('button', { name: 'Print / save as PDF' }).click()
await page.getByRole('dialog').locator('[data-option="statements"]').check()
await page.waitForFunction(
  () => !!document.querySelector('.print-root #print-statements'),
  null, { timeout: 10000 },
)
await page.getByRole('dialog').getByRole('button', { name: 'Close' }).click()

const screenFacts = await facts(page, '.screen-root')
const printFacts = await facts(page, '.print-root')

for (const key of Object.keys(screenFacts.facts)) {
  check(`${key}: ${screenFacts.facts[key]}`,
        printFacts.facts[key] === screenFacts.facts[key],
        `screen=${screenFacts.facts[key]} print=${printFacts.facts[key]}`)
}
// The *body*, not every section. The two views deliberately differ after it: the checking
// tables are one numbered section on screen and four lettered appendices on paper, because a
// 20-page ledger in the middle of the body would bury the settlement. What may not differ is
// the argument -- the same sections making the same claims in the same order.
check('the same body sections, in the same order',
      JSON.stringify(printFacts.body) === JSON.stringify(screenFacts.body),
      `screen=${JSON.stringify(screenFacts.body)} print=${JSON.stringify(printFacts.body)}`)
check('the screen has one checking section and the paper has none',
      JSON.stringify(screenFacts.checking) === JSON.stringify(['details'])
      && printFacts.checking.length === 0,
      `screen=${JSON.stringify(screenFacts.checking)} `
      + `print=${JSON.stringify(printFacts.checking)}`)
// Every checking table on screen has to reach paper as an appendix, or the printed report is
// missing an audit table the page offered.
const checkingIds = await page.locator('#details [id]').evaluateAll((nodes) =>
  nodes.filter((node) => node.tagName === 'DETAILS' || node.classList.contains('subsection'))
    .map((node) => node.id))
check('every screen checking table has an appendix',
      JSON.stringify([...checkingIds].sort())
        === JSON.stringify([...printFacts.appendices].sort()),
      `screen=${JSON.stringify(checkingIds)} print=${JSON.stringify(printFacts.appendices)}`)
check('the same member positions, cell for cell',
      JSON.stringify(printFacts.positions) === JSON.stringify(screenFacts.positions))
check('the same settlement, cell for cell',
      JSON.stringify(printFacts.settlement) === JSON.stringify(screenFacts.settlement))
// The long tables are paged on screen and complete on paper, so comparing the two digests
// would compare a page against a book. The properties that hold are: the same declared total,
// and the same first page in the same order -- which is what a view drifting in its ordering,
// its formatting or its column set would break.
for (const [table, rows] of [['ledger', 668], ['sheet', 153], ['lending', 28]]) {
  check(`${table}: both views declare ${screenFacts[table].count} rows`,
        printFacts[table].count === screenFacts[table].count,
        `screen=${screenFacts[table].count} print=${printFacts[table].count}`)
  check(`${table}: the same first page, row for row`,
        JSON.stringify(printFacts[table].head) === JSON.stringify(screenFacts[table].head),
        `screen=${JSON.stringify(screenFacts[table].head.slice(0, 2))} `
        + `print=${JSON.stringify(printFacts[table].head.slice(0, 2))}`)
  check(`${table}: the printed table renders every one of the ${rows}`,
        printFacts[table].rendered === rows,
        `${printFacts[table].rendered} of ${rows}`)
}
// The statements are the one table the two views deliberately hold different amounts of: one
// member on screen, because the picker can be changed, and every member on paper, because it
// cannot. So the property is containment rather than equality -- the selected member's rows
// have to be somewhere in the printed appendix, identically.
check('the printed statements contain every member’s rows',
      printFacts.memberRecords.rendered === 668,
      String(printFacts.memberRecords.rendered))
// Read in the browser rather than from the fact sets: the digests are hashed by the time they
// reach here, and what has to be checked is that the screen's rows appear among the printed
// ones -- the member the page happens to be showing, printed identically.
const statementAgreement = await page.evaluate(() => {
  const cells = (row) => [...row.children].map((cell) =>
    (cell.textContent ?? '').replace(/\s+/g, ' ').trim()).join('')
  const member = document.querySelector('#checking-member')?.value
  const onScreen = [...document.querySelectorAll('#statements [data-row="member-record"]')]
    .map(cells)
  const block = [...document.querySelectorAll('.print-root .member-detail')]
    .find((node) => node.dataset.member === member)
  const onPaper = [...(block?.querySelectorAll('[data-row="member-record"]') ?? [])].map(cells)
  return {
    member,
    screenRows: onScreen.length,
    paperRows: onPaper.length,
    missing: onScreen.filter((row) => !onPaper.includes(row)),
  }
})
check(`the member on screen (${statementAgreement.member}) is printed identically`,
      statementAgreement.missing.length === 0 && statementAgreement.screenRows > 0,
      JSON.stringify(statementAgreement.missing.slice(0, 2)))
check('and the printed block has all of that member’s rows, not just the page',
      statementAgreement.paperRows > statementAgreement.screenRows,
      `screen=${statementAgreement.screenRows} paper=${statementAgreement.paperRows}`)
check('the screen shows one member of the seven, not all of them',
      screenFacts.memberRecords.count < printFacts.memberRecords.count
      && screenFacts.memberRecords.count > 0,
      `screen=${screenFacts.memberRecords.count} print=${printFacts.memberRecords.count}`)
check('the same lending pairs, cell for cell, as far as the screen page goes',
      JSON.stringify(printFacts.lendingEdges.slice(0, screenFacts.lendingEdges.length))
        === JSON.stringify(screenFacts.lendingEdges),
      `screen=${screenFacts.lendingEdges.length} print=${printFacts.lendingEdges.length}`)
check('the same pool, in and out',
      JSON.stringify(printFacts.pool) === JSON.stringify(screenFacts.pool),
      JSON.stringify(printFacts.pool))
check('the same number of charts',
      printFacts.charts === screenFacts.charts,
      `screen=${screenFacts.charts} print=${printFacts.charts}`)
// By name, not just by count. The settlement graph has its own density thresholds and paper's
// are stricter, so if a bill ever crosses one of them this says which chart went missing
// rather than that a number changed.
check('the same named charts',
      JSON.stringify(printFacts.namedCharts) === JSON.stringify(screenFacts.namedCharts),
      `screen=${JSON.stringify(screenFacts.namedCharts)} `
      + `print=${JSON.stringify(printFacts.namedCharts)}`)
check('the settlement graph is one of them',
      screenFacts.namedCharts.includes('settlement-graph'),
      JSON.stringify(screenFacts.namedCharts))
check('and both category charts are',
      screenFacts.namedCharts.includes('category-pie')
      && screenFacts.namedCharts.includes('category-by-member'),
      JSON.stringify(screenFacts.namedCharts))

console.log('\n3. the printed report is complete')
check('the body is the overview, the members, the settlement and the categories',
      JSON.stringify(printFacts.body)
        === JSON.stringify(['overview', 'members', 'settle', 'categories']),
      JSON.stringify(printFacts.body))
check('the appendices are lettered A to D in order',
      JSON.stringify(printFacts.appendices)
        === JSON.stringify(['lending', 'statements', 'allocation', 'sheet']),
      JSON.stringify(printFacts.appendices))
check('and their headings carry those letters',
      await page.locator('.print-root [data-part="appendix"] h2').evaluateAll((nodes) =>
        nodes.map((node) => node.textContent.trim().split(/\s+/)[1]).join('')) === 'ABCD',
      await page.locator('.print-root [data-part="appendix"] h2').evaluateAll((nodes) =>
        nodes.map((node) => node.textContent.trim()).join(' | ')))
check('the allocation has all 668 rows', printFacts.ledger.rendered === 668,
      String(printFacts.ledger.rendered))
check('the source sheet has all 153 rows', printFacts.sheet.rendered === 153,
      String(printFacts.sheet.rendered))
check('every member has a statement, including any with no records',
      (await page.locator('.print-root .member-detail').count()) === 7,
      String(await page.locator('.print-root .member-detail').count()))
check('the statements are not capped the way the screen pages them',
      printFacts.memberRecords.rendered === 668,
      String(printFacts.memberRecords.rendered))
check('nothing is inside a <details>, so nothing has to be opened to print it',
      (await page.locator('.print-root details').count()) === 0)
// The first PDF told the reader to "Expand a row to see the records it is made of", beside a
// table with nothing to expand: the standfirst was shared with the screen wholesale.
// Instructions to click, expand, hover, page or search do not belong on paper.
const printProse = await page.locator('.print-root').innerText()
for (const affordance of ['Expand a row', 'Show all', 'Collapse', 'hover', 'scroll',
                          'Printing includes all of it', 'Rows per page', 'Search',
                          'Pick a member']) {
  check(`the printed report does not say "${affordance}"`,
        !printProse.includes(affordance))
}
// Every reference in the body has to land on a section of this document. A dead "#print-..."
// anchor means an appendix was excluded and the sentence citing it was printed anyway.
const danglingRefs = await page.evaluate(() => {
  const root = document.querySelector('.print-root')
  return [...root.querySelectorAll('a[href^="#"]')]
    .map((link) => link.getAttribute('href').slice(1))
    .filter((id) => !root.querySelector(`[id="${CSS.escape(id)}"]`))
})
check('no cross-reference points at a section that is not in the document',
      danglingRefs.length === 0, JSON.stringify(danglingRefs))
// And that each one *says* what it points at. A live bug: the statements reference was built
// from the allocation's label, so it linked to Appendix B under the words "Appendix C, the
// allocation" -- a reference that resolves, passes every check above, and sends the reader to
// the wrong table. Nothing but comparing the text to the target catches it.
const misdescribedRefs = await page.evaluate(() => {
  const root = document.querySelector('.print-root')
  return [...root.querySelectorAll('a[href^="#print-"]')]
    .map((link) => {
      const target = root.querySelector(`[id="${CSS.escape(link.getAttribute('href').slice(1))}"]`)
      const heading = target?.querySelector('h2')?.textContent.replace(/\s+/g, ' ').trim()
      const said = link.textContent.replace(/\s+/g, ' ').trim()
      // The link says "Appendix C, the allocation"; the heading says "Appendix C · the
      // allocation". Compare the letter and the title, which is what the reader matches on.
      const letter = said.match(/([A-Z])(?=[^A-Za-z]|$)/)?.[1]
      const title = said.replace(/^[^,，]*[,，]\s*/, '').replace(/[。.]$/, '')
      return { said, heading, ok: !!heading && heading.includes(letter) && heading.includes(title) }
    })
    .filter((entry) => !entry.ok)
})
check('every cross-reference names the appendix it points at',
      misdescribedRefs.length === 0, JSON.stringify(misdescribedRefs))
check('the body does cite its appendices, so that check proved something',
      (await page.locator('.print-root [data-part="body"] a[href^="#print-"]').count()) >= 3,
      String(await page.locator('.print-root [data-part="body"] a[href^="#print-"]').count()))
check('it has no form control of any kind',
      (await page.locator('.print-root input, .print-root select, .print-root button')
        .count()) === 0)
// Four, on a categorised bill: the pool, the transfers, and the two category charts. The two
// duplicate member charts are gone -- they plotted the net by member and consumed-versus-paid-
// versus-net, both of which the member table and the pool already state.
check('charts are SVG', (await page.locator('.print-root .chart svg').count()) === 4,
      String(await page.locator('.print-root .chart svg').count()))
check('no canvas anywhere in the print view',
      (await page.locator('.print-root canvas').count()) === 0)
check('every chart drew something rather than an empty box',
      await page.locator('.print-root .chart svg').evaluateAll((nodes) =>
        nodes.length > 0 && nodes.every((svg) => {
          const box = svg.getBoundingClientRect()
          return box.width > 100 && box.height > 40 && svg.querySelectorAll('path, rect').length > 3
        })))

console.log('\n4. tables carry their headers across pages but not their totals')
check('every print table repeats its header on a page break',
      await page.locator('.print-root table thead').evaluateAll((heads) =>
        heads.length > 0
        && heads.every((head) => getComputedStyle(head).display === 'table-header-group')))
check('and none repeats its footer, which holds a grand total',
      await page.locator('.print-root table tfoot').evaluateAll((feet) =>
        feet.length > 0
        && feet.every((foot) => getComputedStyle(foot).display === 'table-row-group')))

console.log('\n5. nothing overflows the paper')
await page.emulateMedia({ media: 'print' })
check('the screen view is not printed at all',
      !(await page.locator('.screen-root').isVisible()))
check('the print view is', await page.locator('.print-root').isVisible())
const overflow = await page.evaluate(() => {
  const root = document.querySelector('.print-root')
  if (!root) return null
  const limit = root.getBoundingClientRect().right + 1
  // Tables are the things that overflow; a wide one on paper cannot be scrolled.
  return [...root.querySelectorAll('table, .chart, .cards')]
    .filter((node) => node.getBoundingClientRect().right > limit)
    .map((node) => node.tagName + (node.className ? `.${node.className}` : ''))
})
check('no table, chart or card is wider than the page', overflow?.length === 0,
      JSON.stringify(overflow))
await page.emulateMedia({ media: 'screen' })

console.log('\n6. the printed report ignores what the screen is doing')
// Everything a reader might have done to the page before printing: focus the settlement on one
// member, check a different member's records, sort and search and page a long table, collapse
// what was open, scroll to the bottom.
await page.selectOption('#as-me', '甲')
await page.selectOption('#checking-member', '乙')
await page.locator('#allocation > summary').click()
const ledgerTable = page.locator('#allocation .data-table')
await ledgerTable.locator('thead button').last().click()          // sort by share
// A category the fixture actually has, so the table really is filtered and the pager really
// has somewhere to go. A search matching nothing would make the checks below vacuous.
await ledgerTable.locator('input[type=search]').fill('租车')
await ledgerTable.locator('select').last().selectOption('100')
await ledgerTable.getByLabel('Next page').click()
await page.evaluate(() => {
  for (const node of document.querySelectorAll('.screen-root details[open]')) {
    node.open = false
  }
  window.scrollTo(0, document.body.scrollHeight)
})
await page.waitForTimeout(200)

const afterFiddling = await facts(page, '.print-root')
check('the printed report is unchanged by filtering to one member',
      JSON.stringify(afterFiddling.settlement) === JSON.stringify(printFacts.settlement))
check('unchanged by sorting, searching and paging the allocation',
      afterFiddling.ledger.digest === printFacts.ledger.digest
      && afterFiddling.ledger.rendered === 668,
      `${afterFiddling.ledger.rendered} rows, digest ${afterFiddling.ledger.digest}`)
check('unchanged by every fold being collapsed on screen',
      afterFiddling.sheet.rendered === 153)
check('unchanged by a different member being selected for checking',
      afterFiddling.memberRecords.digest === printFacts.memberRecords.digest
      && afterFiddling.memberRecords.rendered === 668,
      String(afterFiddling.memberRecords.rendered))
check('the screen view really was filtered, so this proved something',
      (await page.locator('#settle table').first().locator('tbody tr.is-me').count()) > 0)
check('and the screen table really was searched and paged',
      (await page.locator('#allocation [data-row="ledger"]').count()) < 668
      && (await page.locator('#allocation [data-row="ledger"]').count()) > 0,
      String(await page.locator('#allocation [data-row="ledger"]').count()))

console.log('\n7. printing does not disturb the page underneath')
await page.evaluate(() => {
  window.__printed = 0
  window.print = () => { window.__printed += 1 }
})
await page.getByRole('button', { name: 'Print / save as PDF' }).click()
// Measured with the dialog already open, not before the click: Playwright scrolls an
// element into view before clicking it, and the export button is in the masthead. Reading
// the baseline earlier would attribute the test harness's own scroll to the app.
const before = await page.evaluate(() => ({
  me: document.querySelector('#as-me')?.value ?? null,
  open: document.querySelectorAll('.screen-root details[open]').length,
  scroll: Math.round(window.scrollY),
}))
await page.getByRole('dialog').getByRole('button', { name: 'Print', exact: true }).click()
await page.waitForFunction(() => window.__printed > 0, null, { timeout: 10000 })
const after = await page.evaluate(() => ({
  me: document.querySelector('#as-me')?.value ?? null,
  open: document.querySelectorAll('.screen-root details[open]').length,
  scroll: Math.round(window.scrollY),
}))
check('the print dialog was asked for exactly once',
      (await page.evaluate(() => window.__printed)) === 1)
check('the current member is still selected', after.me === before.me,
      `${before.me} -> ${after.me}`)
check('no drill-down was opened and left open', after.open === before.open,
      `${before.open} -> ${after.open}`)
check('the page did not scroll', Math.abs(after.scroll - before.scroll) <= 2,
      `${before.scroll} -> ${after.scroll}`)
check('the ready signal was raised before the dialog opened',
      (await page.locator('html').getAttribute('data-print-ready')) === 'true')

console.log('\n8. the export options change the appendices and nothing else')
await page.getByRole('button', { name: 'Print / save as PDF' }).click()
const dialog = page.getByRole('dialog')

// Dropping the statements: the appendices after it must close up, and every reference to them
// must follow. A body that still said "see Appendix C" would send the reader to the sheet.
await dialog.locator('[data-option="statements"]').uncheck()
await page.waitForFunction(
  () => !document.querySelector('.print-root #print-statements'),
  null, { timeout: 10000 },
)
const withoutStatements = await facts(page, '.print-root')
check('the statements appendix is gone',
      JSON.stringify(withoutStatements.appendices)
        === JSON.stringify(['lending', 'allocation', 'sheet']),
      JSON.stringify(withoutStatements.appendices))
check('the letters closed up, so the allocation is now B',
      await page.locator('.print-root #print-allocation h2').innerText()
        .then((text) => text.includes(' B ')),
      await page.locator('.print-root #print-allocation h2').innerText())
check('the body no longer cites a statements appendix',
      (await page.locator('.print-root a[href="#print-statements"]').count()) === 0)
check('and cites the allocation where it actually is',
      (await page.locator('.print-root [data-part="body"] a[href="#print-allocation"]')
        .count()) >= 1)
check('the body’s own numbering did not move',
      JSON.stringify(withoutStatements.body) === JSON.stringify(printFacts.body),
      JSON.stringify(withoutStatements.body))

// Dropping everything: no appendices, and no reference to one anywhere in the body.
await dialog.locator('[data-option="appendix"]').uncheck()
await page.waitForFunction(
  () => !document.querySelector('.print-root [data-part="appendix"]'),
  null, { timeout: 10000 },
)
const withoutAppendix = await facts(page, '.print-root')
check('every appendix is gone', withoutAppendix.appendices.length === 0,
      JSON.stringify(withoutAppendix.appendices))
check('and the body is untouched',
      JSON.stringify(withoutAppendix.settlement) === JSON.stringify(printFacts.settlement)
      && JSON.stringify(withoutAppendix.positions) === JSON.stringify(printFacts.positions)
      && withoutAppendix.facts['total-spend'] === printFacts.facts['total-spend'])
check('no dead reference is left behind in it',
      (await page.locator('.print-root a[href^="#print-"]').count()) === 0,
      String(await page.locator('.print-root a[href^="#print-"]').count()))
check('the statements option is unavailable without the appendices',
      await dialog.locator('[data-option="statements"]').isDisabled())

await dialog.locator('[data-option="appendix"]').check()
await dialog.locator('[data-option="statements"]').check()
await page.waitForFunction(
  () => !!document.querySelector('.print-root #print-statements'),
  null, { timeout: 10000 },
)
check('ticking them again brings all four back',
      (await page.locator('.print-root [data-part="appendix"]').count()) === 4,
      String(await page.locator('.print-root [data-part="appendix"]').count()))

console.log('\n9. the preview opens in its own window with the same report')
const [preview] = await Promise.all([
  page.context().waitForEvent('page'),
  dialog.getByRole('button', { name: 'Preview' }).click(),
])
await preview.waitForLoadState('domcontentloaded')
check('it opened at its own URL', preview.url().includes('view=print-preview'),
      preview.url())
await preview.waitForSelector('.print-root', { timeout: 15000 })
await preview.waitForFunction(
  () => document.documentElement.dataset.printReady === 'true',
  null, { timeout: 15000 },
)
const previewFacts = await facts(preview, '.print-root')
check('it shows the same figures as the window it came from',
      JSON.stringify(previewFacts.positions) === JSON.stringify(printFacts.positions)
      && previewFacts.facts['total-spend'] === printFacts.facts['total-spend'],
      JSON.stringify(previewFacts.facts))
check('with the whole allocation', previewFacts.ledger.rendered === 668,
      String(previewFacts.ledger.rendered))
check('and its charts drawn', previewFacts.charts === 4, String(previewFacts.charts))
check('it has no import panel, nav or export dialog of its own',
      (await preview.locator('#import, nav.toc, dialog').count()) === 0)
check('a PDF of the preview has pages',
      (await preview.pdf({ format: 'A4', printBackground: true })).length > 20000)
await preview.close()

console.log('\n10. a preview URL opened on its own says it has nothing to show')
const orphan = await browser.newPage()
await orphan.goto(`${BASE}/?view=print-preview`, { waitUntil: 'networkidle' })
// §5.1: a transient entry point, not a shareable link. The honest answer is to say so
// rather than to invent a way to recover a report nobody sent.
check('it explains itself instead of rendering an empty report',
      (await orphan.locator('.print-status').innerText()).includes('no report'),
      await orphan.locator('.print-status').innerText())
check('and shows no report at all', (await orphan.locator('.print-root').count()) === 0)
await orphan.close()

console.log('\n11. the PDF Chromium produces')
await page.emulateMedia({ media: 'print' })
const pdf = await page.pdf({ format: 'A4', printBackground: true,
                             margin: { top: '15mm', bottom: '15mm',
                                       left: '15mm', right: '15mm' } })
const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length
check(`the PDF has ${pages} pages, which is a whole report`, pages >= 15 && pages <= 45,
      String(pages))
check(`the PDF is ${Math.round(pdf.length / 1024)} kB`, pdf.length > 20000)
await page.emulateMedia({ media: 'screen' })

console.log('\n12. no console errors')
check('console clean', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))

await browser.close()
console.log(failures ? `\n${failures} check(s) failed\n` : '\nall print checks passed\n')
process.exit(failures ? 1 : 0)

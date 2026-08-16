/**
 * Drive the built page against the real Python service.
 *
 * A build that compiles proves the types line up and nothing else. What this checks is
 * the part that only a browser can: that the page loads its own bundle, uploads a
 * bill, renders the figures the service returned, draws the charts as SVG, and prints
 * without the interactive controls.
 *
 * Deliberately not a unit-test suite for components. The arithmetic is Python's and
 * has 6,000 tests on it; what can break here is wiring, and wiring is only visible
 * end to end.
 *
 *   node e2e/smoke.mjs            # expects `splitbill serve` on 8765
 *   node e2e/smoke.mjs --port N
 */
import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const args = process.argv.slice(2)
const portIndex = args.indexOf('--port')
const PORT = portIndex >= 0 ? args[portIndex + 1] : '8765'
const BASE = `http://127.0.0.1:${PORT}`

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BILL = path.resolve(HERE, '../../tests/fixtures/bill_realistic.csv')

let failures = 0
const check = (label, condition, detail = '') => {
  if (condition) {
    console.log(`  ok   ${label}`)
  } else {
    console.log(`  FAIL ${label}${detail ? `  -- ${detail}` : ''}`)
    failures += 1
  }
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })

const consoleErrors = []
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('pageerror', (error) => consoleErrors.push(String(error)))

console.log('\n1. the page loads')
await page.goto(BASE, { waitUntil: 'networkidle' })
check('title is SplitBill', (await page.title()) === 'SplitBill')
check('masthead rendered', (await page.locator('h1').textContent()) === 'SplitBill')
check('import panel is present', await page.locator('#import').isVisible())
check(
  'the service is reachable from the page',
  !(await page.locator('.notice.error').filter({ hasText: 'not answering' }).count()),
)

console.log('\n2. importing a bill')
// The input is `hidden` (the drop zone is the visible affordance), so
// target it directly rather than clicking through.
await page.locator('input[type=file]').setInputFiles(BILL)
const confirmImport = page.getByRole('button', { name: 'Confirm and view report' })
await confirmImport.waitFor({ state: 'visible', timeout: 20000 })
await page.waitForFunction(() => {
  const button = [...document.querySelectorAll('button')]
    .find((item) => item.textContent?.includes('Confirm and view report'))
  return button && !button.disabled
})
check('report is not shown before confirmation', (await page.locator('#overview').count()) === 0)
check('the complete source sheet is shown', await page.locator('#import tbody tr').count() === 153)
check('all seven interpreted participants are shown',
      await page.locator('#import .participant-chip').count() === 7)
const requiredColumnRoles = await page.locator(
  '#import .column-select button[role="combobox"][aria-required="true"]',
).evaluateAll((triggers) => triggers.map(
  (trigger) => trigger.closest('.column-select')?.dataset.columnRole,
))
check('only payer, participant and amount columns are marked as required',
      JSON.stringify(requiredColumnRoles) === JSON.stringify(['creditor', 'debtor', 'amount']),
      JSON.stringify(requiredColumnRoles))
check('required columns have three visible red stars',
      await page.locator('#import .required-mark').evaluateAll((marks) =>
        marks.length === 3
        && marks.every((mark) =>
          getComputedStyle(mark).color === 'rgb(168, 52, 47)'
          && !(mark.previousSibling?.textContent ?? '').endsWith(' '),
        ),
      ))
check('currency and category columns are optional',
      await page.locator(
        '#import [data-column-role="currency"] button[aria-required="false"], '
        + '#import [data-column-role="category"] button[aria-required="false"]',
      ).count() === 2)
for (const role of ['creditor', 'debtor', 'amount']) {
  const requiredSelect = page.locator(`[data-column-role="${role}"]`)
  await requiredSelect.locator('.column-select-trigger').click()
  check(`${role} has no redundant auto-detect option`,
        await requiredSelect.locator('[role="option"][data-value=""]').count() === 0)
  await requiredSelect.locator('.column-select-trigger').press('Escape')
}
for (const role of ['currency', 'category']) {
  const optionalSelect = page.locator(`[data-column-role="${role}"]`)
  await optionalSelect.locator('.column-select-trigger').click()
  check(`${role} keeps its explicit none option`,
        await optionalSelect.locator('[role="option"][data-value=""]').count() === 1)
  await optionalSelect.locator('.column-select-trigger').press('Escape')
}
const categorySelect = page.locator('[data-column-role="category"]')
check('category column was auto-detected',
      await categorySelect.getAttribute('data-selected-value') === '类型')
check('auto-detected status is inside the selected value, not its caption',
      await categorySelect.locator('.column-select-trigger .badge.auto').count() === 1
      && await page.locator('#import .field-caption .badge.auto').count() === 0)
await categorySelect.locator('.column-select-trigger').click()
check('the concrete detected option carries its status in the menu',
      await categorySelect.locator('[role="option"][data-value="类型"] .badge.auto').count() === 1)
await categorySelect.locator('[role="option"][data-value="项目"]').click()
check('category column can be changed manually',
      await categorySelect.getAttribute('data-selected-value') === '项目'
      && await categorySelect.locator('.column-select-trigger .badge.auto').count() === 0)
await categorySelect.locator('.column-select-trigger').click()
await categorySelect.locator('[role="option"][data-value="类型"]').click()
check('reselecting the detected value restores its inline status',
      await categorySelect.locator('.column-select-trigger .badge.auto').count() === 1)
await page.waitForFunction(() => {
  const button = [...document.querySelectorAll('button')]
    .find((item) => item.textContent?.includes('Confirm and view report'))
  return button && !button.disabled
})
await confirmImport.click()
await page.waitForSelector('#overview', { timeout: 20000 })
check('import settings are hidden after confirmation', (await page.locator('#import').count()) === 0)
check('overview appeared', await page.locator('#overview').isVisible())
check('members section appeared', await page.locator('#members').isVisible())
check('the settlement section appeared', await page.locator('#settle').isVisible())
check('the category section appeared', await page.locator('#categories').isVisible())
check('the checking section appeared', await page.locator('#details').isVisible())
// Numbered from what renders, so the fixture's five sections are 1..5 and the nav agrees.
check('the report is numbered from 1',
      (await page.locator('#overview h2').innerText()).trim().startsWith('1 '),
      await page.locator('#overview h2').innerText())
check('the sections are numbered consecutively',
      (await page.locator('.screen-root .section > header h2').allInnerTexts())
        .map((text) => text.trim().split(' ')[0]).join(',') === '1,2,3,4,5',
      (await page.locator('.screen-root .section > header h2').allInnerTexts()).join(' | '))
check('every section has a nav entry',
      (await page.locator('nav.toc a').count()) === 5,
      String(await page.locator('nav.toc a').count()))

console.log('\n3. the figures are the ones Python computed')
const expected = await (await fetch(`${BASE}/api/health`)).json()
check('service identifies itself', expected.service === 'splitbill')

const overview = await page.locator('#overview').innerText()
check('total spend shown', overview.includes('37,986.31'), overview.slice(0, 200))
check('member count shown', overview.includes('7'))
check('transfer count shown', overview.includes('6'))
check('currency-agnostic report omits the settlement-currency card',
      !overview.includes('Settled in') && await page.locator('#overview .card').count() === 3)

// By `data-table`, not by position: the settlement section has one table and the checking
// section has four, so a positional selector picks up whichever renders first.
const settlement = await page.locator('[data-table="settlement"]').first().innerText()
for (const amount of ['971.42', '4,522.98', '7,440.36', '2,205.42', '183.34', '614.06']) {
  check(`settlement row ${amount}`, settlement.includes(amount))
}

const members = await page.locator('[data-table="positions"]').first().innerText()
check('CJK member names rendered', members.includes('甲') && members.includes('丁'))
check('consumption figure shown', members.includes('7,131.22'))
// The net column is gone: the outstanding cell carries the direction in words and the amount
// unsigned, which is the same number in a form that does not need a minus sign decoded.
check('no separate net column', !members.includes('Net'), members.slice(0, 120))
check('outstanding states a direction and an amount',
      members.includes('to receive') && members.includes('15,323.52'),
      members.slice(0, 200))
const notes = await page.locator('#members ul.notes').innerText()
check('both routes to the outstanding figure are stated',
      notes.includes('Paid out − consumed') && notes.includes('Covered for others −'),
      notes)
check('and the allocation is cited by its resolved number',
      notes.includes('section 5.3'), notes)

console.log('\n4. charts are SVG, not canvas')
const svgCount = await page.locator('.screen-root .chart svg').count()
const canvasCount = await page.locator('.screen-root .chart canvas').count()
// Four: the pool, the transfers, and the two category charts.
check(`${svgCount} charts rendered as SVG`, svgCount === 4, `svg=${svgCount}`)
check('no canvas anywhere', canvasCount === 0, `canvas=${canvasCount}`)
check('the two duplicate member charts are gone',
      (await page.locator('#members .chart').count()) === 0)

console.log('\n5. the pool balances, inside the settlement section')
const pool = await page.locator('#pool').innerText()
check('the pool is a subsection of how-to-settle', pool.includes('3.1'), pool.slice(0, 80))
const settleText = await page.locator('#settle').innerText()
check('pool states the identity', settleText.includes('The two'), settleText.slice(0, 400))
check('pool does not report an imbalance', !settleText.includes('should be equal'))
check('and the transfers are the other subsection',
      (await page.locator('#transfers').innerText()).includes('3.2'))

console.log('\n6. the category section')
const categories = await page.locator('#categories').innerText()
check('both category subsections are there',
      categories.includes('4.1') && categories.includes('4.2'), categories.slice(0, 200))
check('the pie is said to add up to the total spend',
      categories.includes('37,986.31'), categories.slice(0, 400))

console.log('\n7. the checking tables page rather than truncate')
const allocation = page.locator('#allocation')
check('the allocation is collapsed by default',
      !(await allocation.evaluate((node) => node.open)))
check('and says how many rows it has', (await allocation.innerText()).includes('668'))
await allocation.locator('summary').click()
check('it opens', await allocation.evaluate((node) => node.open))
check('showing one page of the 668',
      (await allocation.locator('[data-row="ledger"]').count()) === 10,
      String(await allocation.locator('[data-row="ledger"]').count()))
check('and saying which page', (await allocation.innerText()).includes('1–10 of 668'),
      (await allocation.innerText()).slice(0, 200))
const lending = page.locator('#lending')
check('the lending pairs are expanded by default, being the explanation',
      await lending.evaluate((node) => node.open))
check('one member’s records are shown, not everybody’s',
      (await page.locator('#statements [data-row="member-record"]').count()) > 0
      && (await page.locator('#statements [data-row="member-record"]').count()) <= 10)

console.log('\n8. "as me" filters the settlement')
await page.selectOption('#as-me', '甲')
const highlighted = await page
  .locator('[data-table="settlement"]')
  .first()
  .locator('tbody tr.is-me')
  .count()
check(`${highlighted} of 6 transfers involve 甲`, highlighted === 5, `got ${highlighted}`)
const banner = await page.locator('#settle .notice').first().innerText()
check('per-member summary shown', banner.includes('甲'), banner)
// Two pickers, two jobs: this one focuses the transfers, the other picks whose consumption to
// check. Linking them would mean neither could be trusted to stay where it was put.
const checkingMember = await page.locator('#checking-member').inputValue()
check('the checking picker did not move with it', checkingMember !== '甲'
      || (await page.locator('#as-me').inputValue()) !== '甲',
      `as-me=甲 checking=${checkingMember}`)

console.log('\n9. export options and print view')
// The printed report itself is `print.mjs`: completeness, page count, isolation from this
// page's state. What this checks is the dialog that leads to it.
await page.getByRole('button', { name: 'Print / save as PDF' }).click()
const exportDialog = page.getByRole('dialog', { name: 'Export report' })
check('export options open before printing', await exportDialog.isVisible())
// Two checkboxes now, and they nest: the appendices are on by default, the per-member
// statements are not -- they are the allocation regrouped, at 12 extra pages on this bill.
const includeAppendix = exportDialog.locator('[data-option="appendix"]')
const includeStatements = exportDialog.locator('[data-option="statements"]')
check('the appendices are included by default', await includeAppendix.isChecked())
check('the per-member statements are not', !(await includeStatements.isChecked()))
check('and they are unavailable without the appendices',
      await (async () => {
        await includeAppendix.uncheck()
        const disabled = await includeStatements.isDisabled()
        await includeAppendix.check()
        return disabled
      })())
check(
  'the size cost is explained',
  (await exportDialog.innerText()).includes('153 transactions'),
)
check('it offers preview and print',
      await exportDialog.getByRole('button', { name: 'Preview' }).isVisible()
      && await exportDialog.getByRole('button', { name: 'Print', exact: true }).isVisible())
// §5.2: no "Cancel". Both actions are things the user might want, so neither is a default,
// and leaving is the close button's job.
check('and no cancel button',
      (await exportDialog.getByRole('button', { name: /^(Cancel|取消)$/ }).count()) === 0)
check('the close button is the way out',
      await exportDialog.getByRole('button', { name: 'Close' }).isVisible())

// Stub the browser dialog so this test can verify the wiring without blocking on
// Chromium's native print UI.
await page.evaluate(() => {
  window.__splitbillPrintCalled = false
  window.print = () => { window.__splitbillPrintCalled = true }
})
await exportDialog.getByRole('button', { name: 'Print', exact: true }).click()
await page.waitForFunction(() => window.__splitbillPrintCalled, null, { timeout: 10000 })
check('printing was invoked', await page.evaluate(() => window.__splitbillPrintCalled))
check('the dialog closes when it is', !(await exportDialog.isVisible()))

await page.emulateMedia({ media: 'print' })
// The whole screen tree, rather than control by control: the printed report is a
// different document, not a tidied-up version of this one.
check('the screen view is not printed', !(await page.locator('.screen-root').isVisible()))
check('the print view is', await page.locator('.print-root').isVisible())
const pdf = await page.pdf({ format: 'A4', printBackground: true })
check(`PDF produced (${Math.round(pdf.length / 1024)} kB)`, pdf.length > 20000)
await page.emulateMedia({ media: 'screen' })

check('the export dialog can be dismissed without printing',
      await (async () => {
        await page.getByRole('button', { name: 'Print / save as PDF' }).click()
        await exportDialog.getByRole('button', { name: 'Close' }).click()
        return !(await exportDialog.isVisible())
      })())

await page.selectOption('.language-picker select', 'zh-CN')
await page.getByRole('button', { name: '打印 / 另存为 PDF' }).click()
const chineseExportDialog = page.getByRole('dialog', { name: '导出报告' })
check('export options are translated', await chineseExportDialog.isVisible())
check(
  'the appendix option is translated',
  await chineseExportDialog.getByText('在报告末尾附带核对附录').isVisible(),
)
check(
  'and so is the per-member statements option',
  await chineseExportDialog.getByText('包含逐成员核对表').isVisible(),
)
check('both actions are translated',
      await chineseExportDialog.getByRole('button', { name: '预览' }).isVisible()
      && await chineseExportDialog.getByRole('button', { name: '打印', exact: true }).isVisible())
await chineseExportDialog.getByRole('button', { name: '关闭' }).click()

console.log('\n10. returning to import invalidates the visible report')
await page.getByRole('button', { name: '返回修改导入设置' }).click()
check('import settings return', await page.locator('#import').isVisible())
check('the old report is no longer visible', (await page.locator('#overview').count()) === 0)
const chineseConfirm = page.getByRole('button', { name: '确认并查看报告' })
check('the unchanged validated snapshot can be confirmed again', await chineseConfirm.isEnabled())
await chineseConfirm.click()
await page.waitForSelector('#overview')

console.log('\n11. no console errors')
check(
  'console clean',
  consoleErrors.length === 0,
  consoleErrors.slice(0, 3).join(' | '),
)

await browser.close()

console.log(failures ? `\n${failures} check(s) failed\n` : '\nall checks passed\n')
process.exit(failures ? 1 : 0)

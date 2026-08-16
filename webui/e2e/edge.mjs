/**
 * The awkward bills, in a browser.
 *
 * `smoke.mjs` drives one realistic bill and checks the page works. This drives the ones
 * that break pages: nothing owed, one member, a validation error, an uneven split, a
 * currency to convert, a mis-detected column, a narrow window.
 *
 * The arithmetic behind all of these is covered in Python by several thousand tests. What
 * is not covered there is what the page does with the result -- an empty settlement, a
 * net too small to transfer, a member who appears in no chart. Those only fail in a
 * browser, and they fail by looking wrong rather than by throwing.
 *
 *   node e2e/edge.mjs --port 8765
 */
import { chromium } from 'playwright'

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

const browser = await chromium.launch()

/** A fresh page with `csv` imported. Returns the page and any console errors. */
async function importBill(csv, { viewport, confirm = true } = {}) {
  const page = await browser.newPage({
    viewport: viewport ?? { width: 1280, height: 900 },
  })
  const errors = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.locator('input[type=file]').setInputFiles({
    name: 'bill.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv, 'utf-8'),
  })
  if (confirm) {
    const button = page.getByRole('button', { name: 'Confirm and view report' })
    await button.waitFor({ state: 'visible', timeout: 20000 })
    await page.waitForFunction(() => {
      const candidate = [...document.querySelectorAll('button')]
        .find((item) => item.textContent?.includes('Confirm and view report'))
      return candidate && !candidate.disabled
    })
    await button.click()
  }
  return { page, errors }
}

async function settles(page) {
  await page.waitForSelector('#settle', { timeout: 20000 })
}

// 1 ----------------------------------------------------------------------------
console.log('\n1. nobody owes anybody anything')
{
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount\nAlice,"Alice, Bob",100\nBob,"Alice, Bob",100\n')
  await settles(page)
  const text = await page.locator('#settle').innerText()
  check('says so in words', /Nobody owes anybody/i.test(text), text.slice(0, 160))
  // With nothing to settle the table is not rendered at all -- the notice replaces
  // it. (The 2 rows a naive selector finds here are the lending-edges table below,
  // which is a different thing and should be populated.)
  check('the transfer table is absent, not empty',
        (await page.locator('#settle thead:has-text("Pays")').count()) === 0)
  check('the pool says both sides are empty',
        /Nobody underpaid/i.test(text) && /Nobody overpaid/i.test(text), text.slice(0, 400))
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 2 ----------------------------------------------------------------------------
console.log('\n2. a single member')
{
  const { page, errors } = await importBill('Creditor,Debtor,Amount\nAlice,Alice,50\n')
  await settles(page)
  const overview = await page.locator('#overview').innerText()
  check('one person, one record', /\b1\b/.test(overview))
  // Nothing to draw: an empty pool, no transfers, no category column. The report does not
  // depend on a chart, so this is the right answer rather than a degraded one -- what matters
  // is that no empty frame is left behind.
  check('no chart is drawn, and none is left as an empty frame',
        (await page.locator('.screen-root .chart').count()) === 0,
        String(await page.locator('.screen-root .chart').count()))
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 3 ----------------------------------------------------------------------------
console.log('\n3. a bill the validator rejects')
{
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount\nAlice,,0\nBob,,0\n',
    { confirm: false },
  )
  await page.waitForSelector('.notice.error', { timeout: 20000 })
  const text = await page.locator('.notice.error').innerText()
  check('the error is shown', text.length > 0)
  check('it names the row', /row\s*2/i.test(text.replace(/\s+/g, ' ')), text.slice(0, 200))
  const hiddenError = page.locator('.notice.error .finding-more li').first()
  check('only the first repeated error is initially visible', !(await hiddenError.isVisible()))
  const errorMore = page.locator('.notice.error .finding-more summary')
  check('the collapsed error count is shown', /errors not shown: 1/i.test(await errorMore.innerText()))
  await errorMore.click()
  check('the remaining error can be expanded', await hiddenError.isVisible())
  const warningNotice = page.locator('.notice.warn')
  check('warnings remain visible alongside errors', await warningNotice.isVisible())
  const warningMore = warningNotice.locator('.finding-more summary')
  check('the repeated warnings are collapsed too', /warnings not shown: 1/i.test(await warningMore.innerText()))
  check('no report section appeared', (await page.locator('#settle').count()) === 0)
  check('the import panel is still there to fix it in',
        await page.locator('#import').isVisible())
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 4 ----------------------------------------------------------------------------
console.log('\n4. an uneven split (the remainder has to land somewhere)')
{
  // 100 three ways: 33.34 / 33.33 / 33.33, the extra cent to the first name sorted.
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount\nAlice,"Alice, Bob, Carol",100\n')
  await settles(page)
  const members = await page.locator('#members').innerText()
  check('the odd cent is shown', members.includes('33.34'), members.slice(0, 300))
  check('the others get 33.33', members.includes('33.33'))

  // No drill-down to open: one member's records are their own subsection, and which member
  // is shown comes from a picker rather than from expanding a row.
  const statement = await page.locator('#statements').innerText()
  check('the statement total equals that member’s consumption',
        statement.includes('33.34'), statement.slice(0, 300))
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 5 ----------------------------------------------------------------------------
console.log('\n5. a net too small to be worth transferring')
{
  // Bob's only share is one cent. The solver emits no transfer for it, and the page
  // has to say that rather than calling him square -- section 3 says he owes it.
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount\nAlice,"Alice, Bob",0.02\nCarol,"Alice, Carol",500\n')
  await settles(page)

  const settlement = await page.locator('#settle').innerText()
  check('the unsettled nets are named, not dropped',
        /not scheduled for transfer/i.test(settlement), settlement.slice(0, 200))
  // A count, not a summed magnitude: Carol +0.01 and Bob -0.01 is one cent moving,
  // and adding the absolute values would call it two.
  check('and counted rather than summed',
        /2 nets not scheduled/.test(settlement), settlement.slice(0, 260))
  check('and it names who', /Bob owes/.test(settlement))

  await page.selectOption('#as-me', 'Bob')
  await page.waitForTimeout(150)
  const banner = await page.locator('#settle .notice.info').first().innerText()
  check('"as Bob" does not claim he is square',
        !/you are square/.test(banner), banner)
  check('it explains why there is no transfer',
        /too little to be worth a transfer/.test(banner), banner)
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 6 ----------------------------------------------------------------------------
console.log('\n6. converting a currency')
{
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount,Currency\nAlice,"Alice, Bob",30000,KRW\n',
    { confirm: false },
  )
  await page.waitForSelector('#import', { timeout: 20000 })

  // Detection finds the currency column; the settlement currency and rate are ours.
  // `fill` does not fire `change`, and the rate fields only render once a settlement
  // currency is set -- so blur it the way a person would.
  const currencyField = page.locator('#import input[title*="currency to convert into"]')
  await currencyField.fill('HKD')
  await currencyField.press('Tab')
  await page.locator('#import input[placeholder="KRW"]').waitFor({ timeout: 5000 })
  await page.locator('#import input[placeholder="KRW"]').fill('KRW')
  await page.locator('#import input[placeholder="0.0057715"]').fill('0.0057715')
  await page.getByRole('button', { name: 'Add rate' }).click()
  const confirm = page.getByRole('button', { name: 'Confirm and view report' })
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.includes('Confirm and view report'))
    return button && !button.disabled
  })
  check('base-currency preview is shown before confirmation',
        (await page.locator('#import th.base-amount').innerText()).includes('HKD'))
  check('converted value is shown in the source table',
        (await page.locator('#import td.base-amount').innerText()).includes('173.14'))
  await confirm.click()
  await settles(page)
  // Wait for the *recalculated* report, not the face-value one already on screen.
  await page.locator('#overview').getByText('HKD').first().waitFor({ timeout: 10000 })

  const overview = await page.locator('#overview').innerText()
  check('amounts carry their unit', /HKD/.test(overview), overview.slice(0, 200))
  // Case-insensitively: `.card .label` is `text-transform: uppercase`, and `innerText`
  // reports text as rendered. Comparing against the source casing made this assertion
  // impossible to satisfy, so it had been failing since it was written.
  check('converted report keeps the settlement-currency card',
        /settled in/i.test(overview), overview.slice(0, 250))
  check('the converted total is right', /173\.14/.test(overview), overview.slice(0, 250))

  await page.locator('#allocation > summary').click()
  const allocation = await page.locator('#allocation').innerText()
  check('the allocation shows the original alongside',
        /30,000\.00 KRW/.test(allocation), allocation.slice(0, 400))
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 7 ----------------------------------------------------------------------------
console.log('\n7. correcting a mis-detected column')
{
  // Deliberately opaque party headers make their detection fail. The recognized
  // amount column still lets parsing finish so the manual correction UI is stable.
  const { page, errors } = await importBill(
    'ColA,ColB,Amount\nAlice,"Alice, Bob",90\nBob,Alice,30\n',
    { confirm: false },
  )

  const selects = page.locator('#import .column-select')
  await selects.first().waitFor({ state: 'visible', timeout: 20000 })
  const failedDetectionLabels = await selects.evaluateAll((items) =>
    items.slice(0, 3).map(
      (item) => item.querySelector('.column-select-value')?.textContent?.trim(),
    ),
  )
  check('failed detection asks for an explicit column instead of offering auto-detect',
        JSON.stringify(failedDetectionLabels)
          === JSON.stringify(['(select a column)', '(select a column)', 'Amount']),
        JSON.stringify(failedDetectionLabels))
  for (const [index, value] of ['ColA', 'ColB'].entries()) {
    await selects.nth(index).locator('.column-select-trigger').click()
    await selects.nth(index).locator(`[role="option"][data-value="${value}"]`).click()
  }
  const confirm = page.getByRole('button', { name: 'Confirm and view report' })
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.includes('Confirm and view report'))
    return button && !button.disabled
  })
  await confirm.click()
  await settles(page)

  const members = await page.locator('#members').innerText()
  check('the corrected mapping produced a report',
        members.includes('Alice') && members.includes('Bob'), members.slice(0, 200))
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 8 ----------------------------------------------------------------------------
console.log('\n8. a narrow window')
{
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount\nAlice,"Alice, Bob, Carol",100\nBob,Carol,50\n',
    { viewport: { width: 420, height: 900 } })
  await settles(page)

  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check(`no horizontal page overflow (${overflow}px)`, overflow <= 1, `${overflow}px`)
  check('the settlement is still reachable',
        await page.locator('#settle table').first().isVisible())
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// 9 ----------------------------------------------------------------------------
console.log('\n9. a wrong separator returns an inspectable member list')
{
  const { page, errors } = await importBill(
    'Creditor,Debtor,Amount\nAlice,"Alice, Bob",90\nBob,Carol,50\n',
    { confirm: false },
  )
  const separator = page.locator(
    '#import input[title="What separates several names in one cell."]',
  )
  await separator.fill(';')
  await separator.press('Tab')

  const separatorNotice = page.locator('.notice.warn')
  await separatorNotice.waitFor({ timeout: 10000 })
  const separatorWarning = await separatorNotice.innerText()
  check('the warning uses tentative, actionable wording',
        /may use .+ as (?:its|the) name separator/i.test(separatorWarning),
        separatorWarning)
  check('the separator mismatch is shown as a warning',
        await page.locator('.notice.warn').isVisible())
  check('validation still passes',
        (await page.locator('.validation-state').innerText()).includes('Validation passed'))
  const wrongMembers = await page.locator('.participant-chip').allTextContents()
  check('all currently interpreted participants are listed',
        wrongMembers.join('|') === 'Alice|Alice, Bob|Bob|Carol', wrongMembers.join('|'))
  check('the composite phantom member is visible', wrongMembers.includes('Alice, Bob'))
  check('confirmation remains enabled',
        await page.getByRole('button', { name: 'Confirm and view report' }).isEnabled())

  await separator.fill(',')
  await separator.press('Tab')
  await page.getByText('Validation passed').waitFor({ timeout: 10000 })
  const correctedMembers = await page.locator('.participant-chip').allTextContents()
  check('fixing the separator restores the real member list',
        correctedMembers.join('|') === 'Alice|Bob|Carol', correctedMembers.join('|'))
  check('no console errors', errors.length === 0, errors[0] ?? '')
  await page.close()
}

await browser.close()
console.log(failures ? `\n${failures} check(s) failed\n` : '\nall checks passed\n')
process.exit(failures ? 1 : 0)

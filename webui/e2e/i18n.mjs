/** Verify locale switching all the way through the printable report. */
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
function check(label, condition, detail = '') {
  if (condition) console.log(`  ok   ${label}`)
  else {
    console.log(`  FAIL ${label}${detail ? `  -- ${detail}` : ''}`)
    failures += 1
  }
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })

console.log('\n1. English is the default')
await page.goto(BASE, { waitUntil: 'networkidle' })
const picker = page.locator('.language-picker select')
check('locale starts in English', (await picker.inputValue()) === 'en')
check('document language is English', await page.locator('html').getAttribute('lang') === 'en')
check('initial interface is English', (await page.locator('#import h2').innerText()).includes('Load data'))

console.log('\n2. the whole report switches to Simplified Chinese')
await picker.selectOption('zh-CN')
check('document language follows the picker', await page.locator('html').getAttribute('lang') === 'zh-CN')
check('import interface is Chinese', (await page.locator('#import').innerText()).includes('导入'))
await page.locator('input[type=file]').setInputFiles(BILL)
const confirm = page.getByRole('button', { name: '确认并查看报告' })
await confirm.waitFor({ state: 'visible', timeout: 20000 })
check('base currency setting is Chinese',
      (await page.locator('#import').innerText()).includes('基准货币'))
check('auto-detected tags are Chinese and live inside the dropdowns',
      await page.locator('#import .column-select-trigger .badge.auto').evaluateAll(
        (tags) => tags.length > 0 && tags.every((tag) => tag.textContent?.trim() === '自动识别'),
      ))
await page.waitForFunction(() => {
  const button = [...document.querySelectorAll('button')]
    .find((item) => item.textContent?.includes('确认并查看报告'))
  return button && !button.disabled
})
await confirm.click()
await page.waitForSelector('#overview', { timeout: 20000 })
check('overview is Chinese', (await page.locator('#overview h2').innerText()).includes('概览'))
check('the settlement section is Chinese',
      (await page.locator('#settle h2').innerText()).includes('如何结清'))
check('the category section is Chinese',
      (await page.locator('#categories h2').innerText()).includes('分类支出'))
check('the checking section is Chinese',
      (await page.locator('#details h2').innerText()).includes('明细与核对'))
// The numbers are derived from what renders, so they have to be right in both languages --
// they are not part of the translated strings and cannot drift with them.
check('the report is numbered from 1 in Chinese too',
      (await page.locator('#overview h2').innerText()).trim().startsWith('1'),
      await page.locator('#overview h2').innerText())
check('and the settlement’s subsections carry their parent’s number',
      (await page.locator('#pool').innerText()).includes('3.1'),
      await page.locator('#pool').innerText())
// A cross-reference is assembled from a translated sentence and a resolved number, so this is
// the check that the assembly works in a language other than the one it was written in.
check('a cross-reference names a Chinese section and its number',
      (await page.locator('#members ul.notes').innerText()).includes('第 5.3 节'),
      await page.locator('#members ul.notes').innerText())

console.log('\n3. printing uses the selected language')
// Read out of the print view rather than the page: they are different DOMs now, and the
// one that matters here is the one that goes on paper.
await page.evaluate(() => {
  window.__splitbillPrintedText = ''
  window.print = () => {
    window.__splitbillPrintedText =
      document.querySelector('.print-root')?.textContent ?? ''
  }
})
await page.getByRole('button', { name: '打印 / 另存为 PDF' }).click()
await page.getByRole('dialog', { name: '导出报告' })
  .getByRole('button', { name: '打印', exact: true }).click()
await page.waitForFunction(() => window.__splitbillPrintedText !== '', null, { timeout: 10000 })
const printedText = await page.evaluate(() => window.__splitbillPrintedText)
for (const heading of ['概览', '每个人的收支情况', '资金池', '如何转账', '附录']) {
  check(`printable report says "${heading}"`, printedText.includes(heading))
}
check('and none of it is left in English',
      !printedText.includes('Overview') && !printedText.includes('Appendix'))

console.log('\n3b. the preview window inherits the frozen language')
await page.getByRole('button', { name: '打印 / 另存为 PDF' }).click()
const [previewWindow] = await Promise.all([
  page.context().waitForEvent('page'),
  page.getByRole('dialog', { name: '导出报告' })
    .getByRole('button', { name: '预览' }).click(),
])
await previewWindow.waitForSelector('.print-root', { timeout: 15000 })
const previewText = await previewWindow.locator('.print-root').innerText()
check('the preview is Chinese too', previewText.includes('概览'), previewText.slice(0, 80))
check('its own chrome is Chinese', (await previewWindow.locator('.print-toolbar').innerText())
  .includes('打印预览'))
check('the document language followed the frozen input',
      (await previewWindow.locator('html').getAttribute('lang')) === 'zh-CN')
await previewWindow.close()

console.log('\n4. switching back updates the existing report')
await picker.selectOption('en')
check('existing report returns to English', (await page.locator('#overview h2').innerText()).includes('Overview'))

console.log('\n5. separator findings and member preview are translated')
await picker.selectOption('zh-CN')
await page.getByRole('button', { name: '返回修改导入设置' }).click()
const separator = page.locator('#import input[title*="多个姓名"]')
await separator.fill(';')
await separator.press('Tab')
await page.getByText(/有.+项值得检查/).waitFor({ timeout: 10000 })
check('separator finding is Chinese',
      await page.getByText(/这一行可能使用了姓名分隔符“,”/).first().isVisible())
check('participant interpretation remains visible',
      await page.locator('.participant-chip').count() > 7)
check('validation no longer spins',
      (await page.locator('.validation-state').innerText()).includes('数据校验已通过'))
check('warning does not block confirmation',
      await page.getByRole('button', { name: '确认并查看报告' }).isEnabled())

await browser.close()
console.log(failures ? `\n${failures} check(s) failed\n` : '\nall i18n checks passed\n')
process.exit(failures ? 1 : 0)

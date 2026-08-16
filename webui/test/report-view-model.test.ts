/**
 * The shared presentation layer, tested where it can be tested cheaply.
 *
 * These are the functions both views call, so a mistake here appears identically on
 * screen and on paper -- which is exactly the class of bug the split cannot catch by
 * cross-checking the two DOMs against each other. Hence unit tests, which the browser
 * suites are not a substitute for.
 *
 * Two properties get asserted throughout, because they are what makes the sharing safe:
 *
 *   * **purity** -- a selector must not reorder or mutate the report it was handed. The
 *     print view sorts a table; if that sorted the caller's array, it would silently
 *     reorder the screen's.
 *   * **the cent threshold** -- display and solver have to agree about what counts as a
 *     debt, or the report contradicts itself between sections 3 and 5.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { reactive } from 'vue'

import {
  byNetDescending,
  categories,
  consumedBy,
  hasCategories,
  ledgerByMember,
  ledgerColumns,
  ledgerTotal,
  lendingEdges,
  lendingTotal,
  netScale,
  poolBalances,
  poolSides,
  recordsFor,
  settledPerMember,
  settlementTotal,
  sheetRowCount,
  transfersFor,
  unsettled,
} from '../src/presentation/report-view-model'
import {
  UNCATEGORISED,
  categoryByMember,
  categoryTotals,
  consumptionByMember,
} from '../src/presentation/report-view-model'
import { freeze, defaultExportOptions } from '../src/presentation/export-options'
import { percent, standing } from '../src/presentation/format'
import { makeReport, makeSheet } from './fixture'

describe('grouping the ledger', () => {
  it('groups every row under its member, in source order', () => {
    const groups = ledgerByMember(makeReport())
    // Keyed in the order the ledger first mentions each member, not the report's
    // net-descending member order.
    assert.deepEqual([...groups.keys()], ['amy', 'bob', 'cho', 'dee'])
    assert.deepEqual(
      groups.get('amy')?.map((entry) => entry.record_id),
      [1, 2],
    )
    assert.equal(groups.get('cho')?.length, 1)
  })

  it('loses no rows', () => {
    const report = makeReport()
    const grouped = [...ledgerByMember(report).values()].flat()
    assert.equal(grouped.length, report.ledger.length)
  })

  it('gives a member with no records an empty list rather than undefined', () => {
    assert.deepEqual(recordsFor(makeReport(), 'nobody'), [])
  })

  it('adds a member’s shares up to the consumption Python reported', () => {
    const report = makeReport()
    for (const position of report.positions) {
      assert.equal(
        Math.abs(consumedBy(report, position.member) - position.consumption) < 1e-9,
        true,
        `${position.member}: ${consumedBy(report, position.member)} vs ${position.consumption}`,
      )
    }
  })

  it('adds every share up to the total spend', () => {
    const report = makeReport()
    assert.equal(Math.abs(ledgerTotal(report) - report.summary.total_spend) < 1e-9, true)
  })
})

describe('which columns the ledger has', () => {
  it('reports the optional columns that have data', () => {
    assert.deepEqual(ledgerColumns(makeReport()), {
      dates: true,
      categories: true,
      items: true,
      converted: true,
    })
  })

  it('reports none of them for a bare ledger', () => {
    const report = makeReport()
    report.ledger = report.ledger.map((entry) => ({
      ...entry,
      date: null,
      category: null,
      item: null,
      currency_raw: null,
      amount_raw: entry.amount_std,
    }))
    assert.deepEqual(ledgerColumns(report), {
      dates: false,
      categories: false,
      items: false,
      converted: false,
    })
  })

  it('does not call an unconverted row converted just because it names a currency', () => {
    const report = makeReport()
    // Same currency throughout, so `amount_raw` equals `amount_std` everywhere: an
    // "as written" column would repeat the converted one for every row.
    report.ledger = report.ledger.map((entry) => ({
      ...entry,
      currency_raw: 'HKD',
      amount_raw: entry.amount_std,
    }))
    assert.equal(ledgerColumns(report).converted, false)
  })
})

describe('categories', () => {
  it('finds them sorted, so the stack order is stable', () => {
    assert.deepEqual(categories(makeReport()), ['food', 'transport'])
  })

  it('is true when some but not all members have one', () => {
    // 丙's equivalent in the fixture has an empty breakdown, which is the case that
    // must not hide the chart for everybody else.
    assert.equal(hasCategories(makeReport()), true)
  })

  it('is false when nobody has one', () => {
    const report = makeReport()
    report.positions = report.positions.map((position) => ({
      ...position,
      by_category: {},
    }))
    assert.equal(hasCategories(report), false)
    assert.deepEqual(categories(report), [])
  })

  it('gives every member a value for one category, zero included', () => {
    const report = makeReport()
    // cho and dee have no categories at all, which must be a zero rather than a gap -- a gap
    // shifts every later member's bar onto the wrong name.
    assert.deepEqual(categoryByMember(report, 'food'), [60, 0, 0, 60])
    assert.equal(categoryByMember(report, 'nonsense').length, report.positions.length)
  })

  it('reads each bar’s total off the member table rather than re-deriving it', () => {
    const report = makeReport()
    assert.deepEqual(
      consumptionByMember(report),
      report.positions.map((position) => position.consumption),
    )
  })
})

describe('the bill by category', () => {
  it('adds each category across every member, largest first', () => {
    const totals = categoryTotals(makeReport())
    // food is 60 + 60, transport 40 + 40.01.
    assert.equal(totals[0]!.category, 'food')
    assert.equal(totals[0]!.total, 120)
    assert.equal(totals[1]!.category, 'transport')
    assert.equal(Math.abs(totals[1]!.total - 80.01) < 1e-9, true)
  })

  it('names the part of the bill nobody categorised, and puts it last', () => {
    // Record 3 has no category, so 100.004 of the 300.014 total is unaccounted for. Leaving
    // it out would make the pie add up to less than the overview card says, with nothing on
    // the page to explain the difference.
    const totals = categoryTotals(makeReport())
    assert.equal(totals.at(-1)!.category, UNCATEGORISED)
    assert.equal(Math.abs(totals.at(-1)!.total - 100.004) < 1e-9, true)
  })

  it('adds up to the total spend, which is what the section claims', () => {
    const report = makeReport()
    const sum = categoryTotals(report).reduce((total, entry) => total + entry.total, 0)
    assert.equal(Math.abs(sum - report.summary.total_spend) < 1e-9, true, String(sum))
  })

  it('states each share of the total spend', () => {
    const totals = categoryTotals(makeReport())
    assert.equal(Math.abs(totals[0]!.share - 120 / 300.014) < 1e-9, true)
    const shares = totals.reduce((sum, entry) => sum + entry.share, 0)
    assert.equal(Math.abs(shares - 1) < 1e-9, true, String(shares))
  })

  it('leaves out a category worth less than a cent, having no slice to draw', () => {
    const report = makeReport()
    report.positions = report.positions.map((position) => ({
      ...position,
      by_category: { ...position.by_category, dust: 0.001 },
    }))
    assert.equal(
      categoryTotals(report).some((entry) => entry.category === 'dust'),
      false,
    )
  })

  it('leaves out a remainder that is only float noise', () => {
    const report = makeReport()
    // Everything categorised: the remainder is zero, and a "0.00 uncategorised" slice would
    // be an invented category.
    report.summary.total_spend = 200.01
    report.positions = report.positions.map((position) => ({
      ...position,
      by_category:
        position.member === 'amy'
          ? { food: 60, transport: 40 }
          : position.member === 'bob'
            ? { food: 60, transport: 40.01 }
            : {},
    }))
    assert.equal(
      categoryTotals(report).some((entry) => entry.category === UNCATEGORISED),
      false,
    )
  })

  it('finds nothing at all in a report with no categories', () => {
    const report = makeReport()
    report.positions = report.positions.map((position) => ({
      ...position,
      by_category: {},
    }))
    // Only the remainder is left, which is the whole bill -- and the section does not render
    // at all in this case, which is what `hasCategories` decides.
    assert.deepEqual(
      categoryTotals(report).map((entry) => entry.category),
      [UNCATEGORISED],
    )
  })
})

describe('the pool', () => {
  it('splits the members by which side of zero they are on', () => {
    const sides = poolSides(makeReport())
    assert.deepEqual(sides.creditors.map((position) => position.member), ['amy'])
    assert.deepEqual(sides.debtors.map((position) => position.member), ['bob'])
  })

  it('leaves a net under a cent out of both sides', () => {
    // cho is +0.004 and dee is -0.004: neither a creditor nor a debtor, and not an
    // error. They are the members who legitimately appear in no chart.
    const sides = poolSides(makeReport())
    const named = [...sides.creditors, ...sides.debtors].map((p) => p.member)
    assert.equal(named.includes('cho'), false)
    assert.equal(named.includes('dee'), false)
  })

  it('balances, which is the identity the report states', () => {
    const sides = poolSides(makeReport())
    assert.equal(poolBalances(sides), true)
    assert.equal(Math.abs(sides.in - sides.out) < 0.01, true)
  })

  it('orders each side by size', () => {
    const report = makeReport()
    report.positions = [
      { ...report.positions[0]!, member: 'small', net: 10 },
      { ...report.positions[0]!, member: 'large', net: 90 },
      { ...report.positions[1]!, member: 'owes-little', net: -20 },
      { ...report.positions[1]!, member: 'owes-lots', net: -80 },
    ]
    const sides = poolSides(report)
    assert.deepEqual(sides.creditors.map((p) => p.member), ['large', 'small'])
    assert.deepEqual(sides.debtors.map((p) => p.member), ['owes-lots', 'owes-little'])
  })

  it('scales bars against the largest net, and never against zero', () => {
    assert.equal(netScale(makeReport()), 100.01)
    const settled = makeReport()
    settled.positions = settled.positions.map((position) => ({ ...position, net: 0 }))
    // 1, not 0: a fully settled bill would otherwise divide by zero and put NaN in a
    // CSS width, which renders as a missing bar rather than as an error.
    assert.equal(netScale(settled), 1)
  })
})

describe('the settlement', () => {
  it('totals what it moves', () => {
    assert.equal(settlementTotal(makeReport()), 100)
  })

  it('moves less than the nets, which is what leaves a remainder to report', () => {
    const report = makeReport()
    const owed = report.positions
      .filter((position) => position.net > 0)
      .reduce((sum, position) => sum + position.net, 0)
    assert.equal(settlementTotal(report) < owed, true)
  })

  it('totals what was really lent, which is larger', () => {
    const report = makeReport()
    assert.equal(lendingTotal(report) > settlementTotal(report), true)
  })

  it('orders the real lending pairs largest first', () => {
    assert.deepEqual(
      lendingEdges(makeReport()).map((edge) => edge.amount),
      [100.01, 0.004],
    )
  })

  it('says what each member’s transfers come to, signed', () => {
    const totals = settledPerMember(makeReport())
    assert.equal(totals.get('amy'), 100)
    assert.equal(totals.get('bob'), -100)
    assert.equal(totals.get('cho'), undefined)
  })

  it('names the nets the settlement did not fully clear', () => {
    const left = unsettled(makeReport())
    // amy is still owed 0.01 and bob still owes it: a 100.01 net cleared by a 100.00
    // transfer. Above the cent, so section 3 will show it and section 5 must not claim
    // they are square.
    assert.deepEqual(left.map((entry) => entry.member), ['amy', 'bob'])
    assert.equal(Math.abs(left[0]!.remainder - 0.01) < 1e-9, true, String(left[0]!.remainder))
    assert.equal(Math.abs(left[1]!.remainder + 0.01) < 1e-9, true, String(left[1]!.remainder))
  })

  it('stays silent about a net below the cent, which the display also calls square', () => {
    // cho (+0.004) and dee (-0.004) got no transfer and need no explanation: section 3
    // shows them as settled too, so there is no contradiction to resolve.
    const named = unsettled(makeReport()).map((entry) => entry.member)
    assert.equal(named.includes('cho'), false)
    assert.equal(named.includes('dee'), false)
  })

  it('names nobody when every net is cleared exactly', () => {
    const report = makeReport()
    report.positions = [
      { ...report.positions[0]!, member: 'amy', net: 100 },
      { ...report.positions[1]!, member: 'bob', net: -100 },
    ]
    report.settlement = [{ from: 'bob', to: 'amy', amount: 100 }]
    assert.deepEqual(unsettled(report), [])
  })

  it('finds the transfers one member is in, either end', () => {
    const report = makeReport()
    assert.equal(transfersFor(report, 'amy').length, 1)
    assert.equal(transfersFor(report, 'bob').length, 1)
    assert.equal(transfersFor(report, 'cho').length, 0)
    assert.equal(transfersFor(report, 'nobody').length, 0)
  })
})

describe('percentages', () => {
  it('states a share to one decimal, so both category charts say it the same way', () => {
    assert.equal(percent(0.4), '40.0%')
    assert.equal(percent(1), '100.0%')
    assert.equal(percent(0), '0.0%')
  })

  it('leaves a rounded column adding up to something other than 100', () => {
    // Three equal thirds round to 33.3% each, which is 99.9%. Nudging one to make the column
    // reach 100 would mean printing a proportion the amounts do not give -- and these
    // percentages sit beside the amounts they came from, where the reader can check them.
    const thirds = [1 / 3, 1 / 3, 1 / 3].map(percent)
    assert.deepEqual(thirds, ['33.3%', '33.3%', '33.3%'])
  })

  it('says nothing rather than NaN for a share of nothing', () => {
    // `total > 0` guards the callers, but a chart label reading "NaN%" is the kind of thing
    // that reaches paper.
    assert.equal(percent(Number.NaN), '')
    assert.equal(percent(Number.POSITIVE_INFINITY), '')
  })
})

describe('standing agrees with the solver about what a debt is', () => {
  it('calls a net above a cent owed and below a cent owing', () => {
    assert.equal(standing(0.006), 'owed')
    assert.equal(standing(-0.006), 'owes')
  })

  it('calls anything smaller square, which is what leaves it unscheduled', () => {
    assert.equal(standing(0.004), 'square')
    assert.equal(standing(-0.004), 'square')
    assert.equal(standing(0), 'square')
  })
})

describe('selectors do not touch what they are given', () => {
  const mutating: Array<[string, (report: ReturnType<typeof makeReport>) => unknown]> = [
    ['byNetDescending', byNetDescending],
    ['lendingEdges', lendingEdges],
    ['poolSides', poolSides],
    ['unsettled', unsettled],
    ['ledgerByMember', ledgerByMember],
    ['categories', categories],
  ]

  for (const [name, selector] of mutating) {
    it(`${name} leaves the report as it found it`, () => {
      const report = makeReport()
      const before = JSON.stringify(report)
      selector(report)
      assert.equal(JSON.stringify(report), before, `${name} mutated the report`)
    })
  }

  it('byNetDescending returns a new array, not the report’s own', () => {
    const report = makeReport()
    assert.notEqual(byNetDescending(report), report.positions)
    assert.deepEqual(
      byNetDescending(report).map((position) => position.member),
      ['amy', 'cho', 'dee', 'bob'],
    )
  })
})

describe('the sheet', () => {
  it('counts its rows', () => {
    assert.equal(sheetRowCount(makeSheet()), 3)
  })

  it('counts nothing when the service sent no sheet', () => {
    assert.equal(sheetRowCount(null), 0)
  })
})

describe('freezing a print input', () => {
  it('copies deeply, so later edits to the report cannot reach it', () => {
    const report = makeReport()
    const input = freeze(report, makeSheet(), defaultExportOptions(), 'en')

    report.summary.total_spend = 999
    report.settlement.push({ from: 'cho', to: 'amy', amount: 1 })
    report.positions[0]!.net = -1
    report.ledger.length = 0

    assert.equal(input.report.summary.total_spend, 300.014)
    assert.equal(input.report.settlement.length, 1)
    assert.equal(input.report.positions[0]!.net, 100.01)
    assert.equal(input.report.ledger.length, 6)
  })

  it('copies the sheet too, so the appendix cannot be emptied under it', () => {
    const sheet = makeSheet()
    const input = freeze(makeReport(), sheet, defaultExportOptions(), 'en')
    sheet.rows.length = 0
    assert.equal(input.sheet?.rows.length, 3)
  })

  it('copies the options rather than aliasing them', () => {
    const options = defaultExportOptions()
    const input = freeze(makeReport(), null, options, 'en')
    options.appendix = false
    assert.equal(input.options.appendix, true)
  })

  it('carries the locale and a timestamp', () => {
    const input = freeze(makeReport(), null, defaultExportOptions(), 'zh-CN')
    assert.equal(input.locale, 'zh-CN')
    assert.equal(typeof input.frozenAt, 'number')
  })

  it('accepts a report with no sheet', () => {
    assert.equal(freeze(makeReport(), null, defaultExportOptions(), 'en').sheet, null)
  })

  it('freezes a reactive report, which is the only kind it is ever given', () => {
    // `structuredClone` refuses to clone a Proxy outright, and every object the screen view
    // holds is one. Without the unwrap this threw inside a watcher and the print view
    // silently never mounted -- no error the user could see, and a blank page from Ctrl-P.
    const input = freeze(
      reactive(makeReport()),
      reactive(makeSheet()),
      reactive(defaultExportOptions()),
      'en',
    )
    assert.equal(input.report.summary.total_spend, 300.014)
    assert.equal(input.sheet?.rows.length, 3)
    assert.equal(input.options.appendix, true)
  })

  it('unwraps deeply, so a nested reactive field is copied rather than aliased', () => {
    const live = reactive(makeReport())
    const input = freeze(live, null, defaultExportOptions(), 'en')
    live.positions[0]!.by_category.food = 999
    assert.equal(input.report.positions[0]!.by_category.food, 60)
  })

  it('includes the appendices by default, because a report that cannot be checked is the'
     + ' thing this tool exists to stop producing', () => {
    assert.equal(defaultExportOptions().appendix, true)
  })

  it('leaves the per-member statements out by default, being the allocation regrouped', () => {
    // On the real bill it is seven tables of a hundred-odd rows saying what the allocation
    // appendix already says, grouped another way. Worth having on request; not worth 12 pages
    // by default.
    assert.equal(defaultExportOptions().statements, false)
  })

  it('copies both options rather than aliasing them', () => {
    const options = defaultExportOptions()
    const input = freeze(makeReport(), null, options, 'en')
    options.appendix = false
    options.statements = true
    assert.equal(input.options.appendix, true)
    assert.equal(input.options.statements, false)
  })
})


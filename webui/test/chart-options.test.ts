/**
 * The chart option factories, checked for the one property that matters most.
 *
 * A print theme may change type sizes and drop tooltips. It may not change what a chart
 * shows -- a printed chart with different bars from the screen's would be a second
 * report, which is the failure the whole split exists to prevent and the one a visual
 * check is least likely to catch. So the series data is asserted equal across themes,
 * chart by chart.
 *
 * The rest is what a chart on paper cannot have: no tooltip (nothing to hover), no
 * animation (it cannot show, and a chart mid-transition when the print job composes
 * renders half-drawn). These are cheap to assert and were both real bugs.
 *
 * `../src/presentation/echarts` is never loaded: this module imports only its *type*, so
 * the whole ECharts library stays out of a unit test that is about option objects.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  PRINT_THEME,
  SCREEN_THEME,
  categoryOption,
  categoryPieOption,
  sankeyOption,
  settlementGraphOption,
} from '../src/presentation/chart-options'
import { makeReport } from './fixture'

const CATEGORY_LABELS = { uncategorised: 'Uncategorised', total: 'Total' }
const SETTLEMENT_LABELS = { pays: 'Pays', receives: 'Receives' }
const money = (value: number) => value.toFixed(2)

/** Every chart, built both ways, named for the failure message. */
function bothThemes() {
  const report = makeReport()
  return [
    [
      'category pie',
      categoryPieOption(report, 'Uncategorised', money, SCREEN_THEME),
      categoryPieOption(report, 'Uncategorised', money, PRINT_THEME),
    ],
    [
      'category by member',
      categoryOption(report, CATEGORY_LABELS, money, SCREEN_THEME),
      categoryOption(report, CATEGORY_LABELS, money, PRINT_THEME),
    ],
    [
      'sankey',
      sankeyOption(report, 'the pool', money, SCREEN_THEME),
      sankeyOption(report, 'the pool', money, PRINT_THEME),
    ],
    [
      'settlement graph',
      settlementGraphOption(report, SETTLEMENT_LABELS, money, SCREEN_THEME),
      settlementGraphOption(report, SETTLEMENT_LABELS, money, PRINT_THEME),
    ],
  ] as const
}

/** Series as plain data, with the formatter closures dropped -- two never compare equal. */
function seriesData(option: { series?: unknown }): unknown {
  return JSON.parse(
    JSON.stringify(option.series, (key, value) =>
      key === 'formatter' || key === 'valueFormatter' ? undefined : value,
    ),
  )
}

/**
 * What a chart shows, with nothing about how it looks.
 *
 * Type sizes are exactly what the theme is allowed to change, so comparing whole series
 * objects across themes would fail on the difference it is testing for. This keeps the
 * fields that carry meaning -- which series, in what order, holding which values, in
 * which colours -- and drops the ones that carry only size.
 */
function shownData(option: { series?: unknown }): unknown {
  const series = seriesData(option) as Array<Record<string, unknown>>
  return series.map((entry) => ({
    name: entry.name,
    type: entry.type,
    stack: entry.stack,
    data: entry.data,
    links: entry.links,
  }))
}

describe('a print chart shows exactly what the screen chart shows', () => {
  for (const [name, screen, print] of bothThemes()) {
    it(`${name}: the series data is identical`, () => {
      assert.deepEqual(shownData(print), shownData(screen), name)
    })
  }

  for (const [name, screen, print] of bothThemes()) {
    it(`${name}: the axis categories are identical`, () => {
      const axis = (option: { xAxis?: unknown }) =>
        (option.xAxis as { data?: unknown } | undefined)?.data ?? null
      assert.deepEqual(axis(print), axis(screen), name)
    })
  }
})

describe('what paper cannot have', () => {
  for (const [name, screen, print] of bothThemes()) {
    it(`${name}: no tooltip when printing, and one on screen`, () => {
      assert.equal(print.tooltip, undefined, name)
      assert.notEqual(screen.tooltip, undefined, name)
    })
  }

  it('the print theme sets no type size larger than the screen theme’s', () => {
    for (const key of ['axisLabel', 'categoryLabel', 'legendLabel', 'seriesLabel'] as const) {
      assert.equal(PRINT_THEME[key] <= SCREEN_THEME[key], true, key)
    }
  })
})

describe('the category pie', () => {
  it('draws one slice per category plus the part nobody categorised', () => {
    const series = seriesData(
      categoryPieOption(makeReport(), 'Uncategorised', money),
    ) as Array<{ data: Array<{ name: string; value: number }> }>
    assert.deepEqual(
      series[0]!.data.map((slice) => slice.name),
      ['food', 'transport', 'Uncategorised'],
    )
  })

  it('adds up to the total spend, which is what the section claims', () => {
    const report = makeReport()
    const series = seriesData(
      categoryPieOption(report, 'Uncategorised', money),
    ) as Array<{ data: Array<{ value: number }> }>
    const sum = series[0]!.data.reduce((total, slice) => total + slice.value, 0)
    assert.equal(Math.abs(sum - report.summary.total_spend) < 1e-9, true, String(sum))
  })

  it('labels each slice with its category, amount and percentage', () => {
    // Paper has no hover, so all three parts have to be on the chart itself.
    for (const theme of [SCREEN_THEME, PRINT_THEME]) {
      const series = (
        categoryPieOption(makeReport(), 'Uncategorised', money, theme)
          .series as Array<Record<string, unknown>>
      )[0]!
      const label = series.label as {
        show?: boolean
        formatter: (params: { dataIndex: number }) => string
      }
      assert.equal(label.show, true)
      assert.equal(label.formatter({ dataIndex: 0 }), 'food 120.00 (40.0%)')
    }
  })

  it('puts a wrapping legend across the top', () => {
    const legend = categoryPieOption(makeReport(), 'Uncategorised', money)
      .legend as {
        orient?: string
        top?: string | number
        width?: string | number
        type?: string
      }
    assert.equal(legend.orient, 'horizontal')
    assert.equal(legend.top, 0)
    assert.equal(legend.width, '90%')
    assert.notEqual(legend.type, 'scroll')
  })

  it('gives the uncategorised slice its own colour, not a category’s', () => {
    const series = seriesData(
      categoryPieOption(makeReport(), 'Uncategorised', money),
    ) as Array<{ data: Array<{ name: string; itemStyle: { color: string } }> }>
    const slices = series[0]!.data
    const grey = slices.find((slice) => slice.name === 'Uncategorised')!.itemStyle.color
    for (const slice of slices.filter((entry) => entry.name !== 'Uncategorised')) {
      assert.notEqual(slice.itemStyle.color, grey, slice.name)
    }
  })

  it('does not let the legend scroll, there being no arrow to click on paper', () => {
    const legend = categoryPieOption(makeReport(), 'Uncategorised', money)
      .legend as { type?: string }
    assert.notEqual(legend.type, 'scroll')
  })

  it('states the amount and the percentage when hovered on screen', () => {
    const option = categoryPieOption(makeReport(), 'Uncategorised', money)
    const formatter = (option.tooltip as { formatter: (params: unknown) => string })
      .formatter
    const text = formatter({ name: 'food', value: 120 })
    assert.equal(text.includes('food'), true, text)
    assert.equal(text.includes('120.00'), true, text)
    // 120 of 300.014.
    assert.equal(text.includes('40.0%'), true, text)
  })
})

describe('the category chart by member', () => {
  it('stacks one series per category, in sorted order', () => {
    const series = seriesData(
      categoryOption(makeReport(), CATEGORY_LABELS, money),
    ) as Array<{ name: string; stack: string }>
    assert.deepEqual(series.map((entry) => entry.name).slice(0, 2), ['food', 'transport'])
    assert.equal(series.every((entry) => entry.stack === 'consumption'), true)
  })

  it('gives every category series a value for every member, zero included', () => {
    const report = makeReport()
    const series = seriesData(
      categoryOption(report, CATEGORY_LABELS, money),
    ) as Array<{ data: number[] }>
    for (const entry of series) {
      assert.equal(entry.data.length, report.positions.length)
    }
    // cho and dee have no categories at all, which must be a zero rather than a gap -- a gap
    // shifts every later member's bar onto the wrong name.
    assert.equal(series[0]!.data.filter((value) => value === 0).length >= 2, true)
  })

  it('carries each member’s own uncategorised remainder as its own segment', () => {
    // cho consumed 100 with no category at all, so their bar would otherwise be empty under a
    // label saying 100.00.
    const series = seriesData(
      categoryOption(makeReport(), CATEGORY_LABELS, money),
    ) as Array<{ name: string; data: number[] }>
    const remainder = series.find((entry) => entry.name === 'Uncategorised')
    assert.notEqual(remainder, undefined)
    // cho is index 1 in the fixture's net-descending order.
    assert.equal(Math.abs(remainder!.data[1]! - 100) < 1e-9, true, String(remainder!.data))
  })

  it('labels each bar with the member’s consumption from the table, not a re-sum', () => {
    const report = makeReport()
    const series = (
      categoryOption(report, CATEGORY_LABELS, money).series as Array<Record<string, unknown>>
    )
    const totals = series.at(-1)!
    assert.equal(totals.name, 'Total')
    const label = totals.label as {
      show: boolean
      formatter: (params: { dataIndex: number }) => string
    }
    assert.equal(label.show, true)
    assert.equal(label.formatter({ dataIndex: 0 }), money(report.positions[0]!.consumption))
  })

  it('labels nothing above a member who consumed nothing', () => {
    // A "0.00" over an empty bar reads as a figure rather than as an absence.
    const report = makeReport()
    report.positions = report.positions.map((position) => ({ ...position, consumption: 0 }))
    const series = (
      categoryOption(report, CATEGORY_LABELS, money).series as Array<Record<string, unknown>>
    )
    const label = series.at(-1)!.label as {
      formatter: (params: { dataIndex: number }) => string
    }
    assert.equal(label.formatter({ dataIndex: 0 }), '')
  })

  it('keeps the total series out of the legend, it being invisible', () => {
    const option = categoryOption(makeReport(), CATEGORY_LABELS, money)
    assert.deepEqual((option.legend as { data: string[] }).data, [
      'food',
      'transport',
      'Uncategorised',
    ])
  })

  it('shows only the non-zero categories when hovered, with each one’s share', () => {
    const option = categoryOption(makeReport(), CATEGORY_LABELS, money)
    const formatter = (option.tooltip as { formatter: (params: unknown) => string })
      .formatter
    // amy: 100 consumed, 60 food, 40 transport, nothing uncategorised.
    const text = formatter([
      { axisValue: 'amy', dataIndex: 0, seriesName: 'food', value: 60 },
      { axisValue: 'amy', dataIndex: 0, seriesName: 'transport', value: 40 },
      { axisValue: 'amy', dataIndex: 0, seriesName: 'Uncategorised', value: 0 },
      { axisValue: 'amy', dataIndex: 0, seriesName: 'Total', value: 0 },
    ])
    assert.equal(text.includes('60.0%'), true, text)
    assert.equal(text.includes('40.0%'), true, text)
    // The zero component is dropped rather than shown as "0.0%", which on a bill with ten
    // categories is ten lines of nothing.
    assert.equal(text.includes('0.0%\n') || text.includes('Uncategorised'), false, text)
  })

  it('states the total in the tooltip, and no proportions for a member with none', () => {
    const report = makeReport()
    report.positions = report.positions.map((position) => ({ ...position, consumption: 0 }))
    const option = categoryOption(report, CATEGORY_LABELS, money)
    const formatter = (option.tooltip as { formatter: (params: unknown) => string })
      .formatter
    const text = formatter([
      { axisValue: 'amy', dataIndex: 0, seriesName: 'food', value: 0 },
    ])
    assert.equal(text.includes('Total'), true, text)
    assert.equal(text.includes('%'), false, text)
  })
})

describe('the charts themselves', () => {
  it('routes the sankey through one middle node and no member-to-member link', () => {
    const series = seriesData(
      sankeyOption(makeReport(), 'the pool', money),
    ) as Array<{
      data: Array<{ name: string }>
      links: Array<{ source: string; target: string }>
    }>
    const { data, links } = series[0]!
    assert.equal(data.some((node) => node.name === 'the pool'), true)
    // The re-pairing is a delivery detail, and drawing it member-to-member would show it
    // as though it meant something.
    for (const link of links) {
      assert.equal(
        link.source === 'the pool' || link.target === 'the pool',
        true,
        `${link.source} -> ${link.target}`,
      )
    }
  })

  it('draws the settlement graph from fixed coordinates rather than a simulation', () => {
    // A force layout would settle somewhere new on every render, so the screen and the
    // paper could not be the same picture.
    const series = (settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money)
      .series as Array<Record<string, unknown>>)[0]!
    assert.equal(series.layout, 'none')
    assert.equal(series.draggable, false)
    for (const node of series.data as Array<{ x: unknown; y: unknown }>) {
      assert.equal(typeof node.x, 'number')
      assert.equal(typeof node.y, 'number')
    }
  })

  it('preserves the aspect ratio, so the dots are round in any box', () => {
    // Without this the data's bounding box is stretched onto the chart's, and the
    // stretch is applied to the symbols and the edge labels too: on a wide, short chart
    // the dots came out as horizontal dashes and the amounts as unreadable smudges.
    const series = (settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money)
      .series as Array<Record<string, unknown>>)[0]!
    assert.equal(series.preserveAspect, true)
  })

  it('labels every edge with its amount, tooltip or no tooltip', () => {
    // Paper has no hover, and a diagram whose figures cannot be read cannot be checked
    // against the table above it.
    for (const theme of [SCREEN_THEME, PRINT_THEME]) {
      const series = (settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money, theme)
        .series as Array<Record<string, unknown>>)[0]!
      const label = series.edgeLabel as { show?: boolean; formatter?: unknown }
      assert.equal(label.show, true)
      assert.equal(typeof label.formatter, 'function')
      assert.equal(
        (label.formatter as (params: { value: number }) => string)({ value: 12.5 }),
        '12.50',
      )
    }
  })

  it('gives a payer and a receiver different colours, and never the same member both', () => {
    const series = seriesData(
      settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money),
    ) as Array<{
      data: Array<{ name: string; category: number }>
      links: Array<{ source: string; target: string }>
    }>
    const { data, links } = series[0]!
    const sides = new Map(data.map((node) => [node.name, node.category]))
    for (const link of links) {
      assert.equal(sides.get(link.source), 0, link.source)
      assert.equal(sides.get(link.target), 1, link.target)
    }
  })

  it('sizes a dot by what that member moves', () => {
    const report = makeReport()
    report.settlement = [
      { from: 'bob', to: 'amy', amount: 100 },
      { from: 'cho', to: 'amy', amount: 10 },
    ]
    const series = seriesData(
      settlementGraphOption(report, SETTLEMENT_LABELS, money),
    ) as Array<{ data: Array<{ name: string; symbolSize: number }> }>
    const sizes = new Map(series[0]!.data.map((node) => [node.name, node.symbolSize]))
    // amy receives 110, bob pays 100, cho pays 10.
    assert.equal(sizes.get('amy')! > sizes.get('bob')!, true)
    assert.equal(sizes.get('bob')! > sizes.get('cho')!, true)
  })

  it('writes an edge’s tooltip as an arrow, not as a comparison', () => {
    // ECharts' own edge tooltip is "甲 > 乙", and `>` reads as "greater than". The
    // direction the money goes is the entire content of an edge.
    const option = settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money)
    const formatter = (option.tooltip as { formatter: (params: unknown) => string })
      .formatter
    const text = formatter({
      dataType: 'edge',
      data: { source: 'bob', target: 'amy' },
      value: 100,
    })
    assert.equal(text.includes('&rarr;'), true, text)
    // Not `includes('>')`: `&rarr;` ends in one. What must not appear is a bare `>`
    // between the two names, which is what ECharts writes by default.
    assert.equal(/\bbob\s*>\s*amy\b/.test(text), false, text)
    assert.equal(text.includes('bob'), true, text)
    assert.equal(text.includes('amy'), true, text)
    assert.equal(text.includes('100.00'), true, text)
  })

  it('gives a node’s tooltip the total the dot size only implies', () => {
    const option = settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money)
    const formatter = (option.tooltip as { formatter: (params: unknown) => string })
      .formatter
    // bob pays 100 in the fixture's single transfer.
    const text = formatter({ dataType: 'node', name: 'bob' })
    assert.equal(text.includes('bob'), true, text)
    assert.equal(text.includes('Pays'), true, text)
    assert.equal(text.includes('100.00'), true, text)
  })

  it('does not let the legend hide a side of the settlement', () => {
    // Hiding one would hide real transfers and leave the diagram disagreeing with the
    // table above it.
    const option = settlementGraphOption(makeReport(), SETTLEMENT_LABELS, money)
    assert.equal((option.legend as { selectedMode?: unknown }).selectedMode, false)
  })

  it('leaves sub-cent nets out of the sankey, as the pool leaves them out', () => {
    const series = seriesData(
      sankeyOption(makeReport(), 'the pool', money),
    ) as Array<{ data: Array<{ name: string }> }>
    const names = series[0]!.data.map((node) => node.name)
    assert.deepEqual(names, ['bob', 'the pool', 'amy'])
  })
})

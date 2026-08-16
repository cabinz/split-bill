/**
 * Every chart in the report, as an ECharts option. One factory per chart, shared.
 *
 * The charts say the same thing in both views; only their size differs. A screen chart
 * is 320 CSS pixels tall and a printed one is 62mm, so a label that reads well on one is
 * cramped on the other -- hence `theme`, which carries type sizes and nothing else. It
 * may not change what a series contains. A chart with different *data* on paper would be
 * a second report, which is the thing the split was designed not to produce.
 *
 * Colours are stated as hex rather than as CSS variables because ECharts writes them
 * into SVG attributes, where `var(--owed)` does not resolve. They are the same values as
 * the tokens, kept beside a note saying so, and colour is never the only channel: every
 * amount is printed with its sign, so the report survives a monochrome printer.
 */
import type { Report } from './types'
import type { EChartsOption } from './echarts'
import { axisValue, chartValue, percent } from './format'
import {
  UNCATEGORISED,
  categories,
  categoryByMember,
  categoryTotals,
  consumptionByMember,
  poolSides,
  settlementGraphData,
} from './report-view-model'

/** Matches `--owed` and `--owes` in tokens.css. */
const OWED = '#1a6b45'
const OWES = '#a8342f'
/** Section 5's graph: edges belong to no side, so they take no side's colour. */
const EDGE_LINE = '#8894a0'
/** Behind an edge's amount, so it stays readable where arrows cross. */
const EDGE_LABEL_BACKING = 'rgba(255, 255, 255, 0.88)'
/** A ring around each dot, so two that touch still read as two. */
const NODE_HALO = '#ffffff'
const EDGE_CURVE = 0.12

/**
 * How large a coordinate space to give the graph. Pure workaround, and the reason is
 * worth stating because the number looks arbitrary.
 *
 * ECharts trims each edge back to its target node's circle so the arrowhead touches the
 * dot (`adjustEdge`), finding the crossing by bisection with `|dist² - r²| < 1e-2` as
 * the stopping test. That tolerance is absolute while the distances are in *data* units,
 * so on the unit circle this layer computes -- where the radius works out around 0.07
 * and its square around 0.005 -- the test is already satisfied before the search
 * starts. The loop exits having converged on nothing, and the arrows stop anywhere from
 * touching the dot to ten pixels short of it.
 *
 * Scaling the coordinates up makes the same fixed tolerance tight: at 600, r² is in the
 * thousands. Nothing else changes -- `preserveAspect` takes the aspect ratio from the
 * data's bounding box, which is square at any scale, and the view fits that box to the
 * chart either way.
 */
const GRAPH_UNITS = 600
const POOL = '#59636e'
const GRID_LINE = '#eaeef2'
const AXIS_LINE = '#59636e'

/**
 * Categorical colours, in an order chosen so adjacent stacks differ in lightness as
 * well as hue -- a stacked bar printed in greyscale still shows its divisions.
 */
const CATEGORY_PALETTE = [
  '#2f6f9f', '#c25e00', '#3f7d58', '#8d5bab', '#b03a48',
  '#1f7a8c', '#9a6a00', '#5a6b8c', '#7a4a6d', '#3d6b3a',
]

/** The part of the bill nobody labelled. Grey, so it does not read as a category
 *  competing with the named ones for attention. */
const UNCATEGORISED_FILL = '#b8c0c8'

/** Type sizes for one medium. Not a place to change what a chart shows. */
export interface ChartTheme {
  axisLabel: number
  categoryLabel: number
  legendLabel: number
  seriesLabel: number
  /** Tooltips exist on screen and not on paper, where nothing can be hovered. */
  tooltips: boolean
}

export const SCREEN_THEME: ChartTheme = {
  axisLabel: 10,
  categoryLabel: 11,
  legendLabel: 11,
  seriesLabel: 10,
  tooltips: true,
}

/**
 * Print sizes.
 *
 * A point smaller across the board: the printed chart is about a fifth the height of the
 * screen one, and ECharts sizes text in pixels against a viewBox that is then scaled to
 * the paper. Left at screen sizes the labels came out proportionally huge and collided.
 */
export const PRINT_THEME: ChartTheme = {
  axisLabel: 9,
  categoryLabel: 10,
  legendLabel: 10,
  seriesLabel: 9,
  tooltips: false,
}

/** Tooltip config, or nothing at all when the chart is going on paper. */
function tooltip(
  theme: ChartTheme,
  currency: string | null,
  trigger: 'item' | 'axis',
): EChartsOption['tooltip'] {
  if (!theme.tooltips) return undefined
  return {
    trigger,
    ...(trigger === 'axis' ? { axisPointer: { type: 'shadow' as const } } : {}),
    valueFormatter: chartValue(currency),
  }
}

/**
 * The whole bill by category, as a pie.
 *
 * Answers one question -- what did this trip mostly go on -- which is why it is a pie
 * rather than another bar chart beside the per-member one. The slices add up to
 * `summary.total_spend`, including a slice for whatever nobody categorised, so the reader
 * can check the picture against the overview card.
 *
 * Labels carry the category, its amount and its percentage on the chart itself. Not only in
 * a tooltip: paper has no hover, so every slice has to state all three figures directly.
 */
export function categoryPieOption(
  report: Report,
  uncategorisedLabel: string,
  money: (value: number) => string,
  theme: ChartTheme = SCREEN_THEME,
): EChartsOption {
  const totals = categoryTotals(report)
  const named = (category: string) =>
    category === UNCATEGORISED ? uncategorisedLabel : category
  const unit = report.meta.std_currency ? ` ${report.meta.std_currency}` : ''

  return {
    tooltip: theme.tooltips
      ? {
          trigger: 'item',
          formatter: (params) => {
            const item = (Array.isArray(params) ? params[0] : params) as {
              name?: string
              value?: unknown
            }
            const value = typeof item.value === 'number' ? item.value : 0
            const row = totals.find((entry) => named(entry.category) === item.name)
            return `${item.name ?? ''}<br/>${money(value)}${unit}`
              + ` (${percent(row?.share ?? 0)})`
          },
        }
      : undefined,
    legend: {
      // Across the top, where the legend is read before the figure. Giving a plain legend
      // a bounded width makes ECharts wrap overflowing items onto another line; `scroll`
      // is deliberately not used because it hides categories behind an arrow nobody can
      // click on paper.
      orient: 'horizontal',
      left: 'center',
      top: 0,
      width: '90%',
      itemHeight: 9,
      itemWidth: 14,
      textStyle: { fontSize: theme.legendLabel },
    },
    series: [
      {
        type: 'pie',
        // A ring rather than a disc: the slice labels sit outside it either way, and the
        // hole is where the total goes on a screen wide enough for it.
        radius: ['34%', '62%'],
        // Leave room above the ring for a legend that wraps onto a second line.
        center: ['50%', '58%'],
        avoidLabelOverlap: true,
        // Sorted by the shared selector already, and ECharts would re-sort by value
        // otherwise -- putting the uncategorised remainder somewhere other than last.
        data: totals.map((entry, index) => ({
          name: named(entry.category),
          value: entry.total,
          itemStyle: {
            color:
              entry.category === UNCATEGORISED
                ? UNCATEGORISED_FILL
                : CATEGORY_PALETTE[index % CATEGORY_PALETTE.length],
          },
        })),
        label: {
          show: true,
          fontSize: theme.seriesLabel,
          formatter: (params: { dataIndex?: number }) => {
            const entry = totals[params.dataIndex ?? -1]
            if (!entry) return ''
            return `${named(entry.category)} ${money(entry.total)} (${percent(entry.share)})`
          },
        },
        labelLine: { length: 6, length2: 6 },
        emphasis: { scale: false },
      },
    ],
  }
}

/**
 * Each member's consumption, split by category and stacked.
 *
 * Answers the other half of the question: not what the bill went on, but whether one
 * person's mix differs from another's. The total sits on top of each bar, and it is the
 * member table's "consumed" figure -- read from `positions`, not summed from the segments,
 * so the two cannot disagree.
 *
 * A member who consumed nothing gets no segments and no total, rather than a bar of zeros
 * under a "0.00" label.
 */
export function categoryOption(
  report: Report,
  labels: { uncategorised: string; total: string },
  money: (value: number) => string,
  theme: ChartTheme = SCREEN_THEME,
): EChartsOption {
  const present = categories(report)
  const consumption = consumptionByMember(report)
  const unit = report.meta.std_currency ? ` ${report.meta.std_currency}` : ''

  /** Each member's uncategorised remainder: what they consumed less what they labelled. */
  const remainders = report.positions.map((position) => {
    const labelled = present.reduce(
      (sum, category) => sum + (position.by_category[category] ?? 0),
      0,
    )
    const left = position.consumption - labelled
    return left >= 0.005 ? left : 0
  })
  const anyRemainder = remainders.some((value) => value > 0)

  const series: NonNullable<EChartsOption['series']> = present.map((category, index) => ({
    name: category,
    type: 'bar',
    stack: 'consumption',
    data: categoryByMember(report, category),
    itemStyle: { color: CATEGORY_PALETTE[index % CATEGORY_PALETTE.length] },
  }))

  if (anyRemainder) {
    series.push({
      name: labels.uncategorised,
      type: 'bar',
      stack: 'consumption',
      data: remainders,
      itemStyle: { color: UNCATEGORISED_FILL },
    })
  }

  /**
   * An invisible series, carrying the total on top of the stack.
   *
   * A zero-height bar at the top of the stack is where ECharts will put a `position: top`
   * label, and there is no other way to label a stack as a whole -- a label on the topmost
   * real segment would sit on top of *that* segment's value, and which segment is topmost
   * varies per member.
   */
  series.push({
    name: labels.total,
    type: 'bar',
    stack: 'consumption',
    data: consumption.map(() => 0),
    itemStyle: { color: 'transparent' },
    // Nothing to hover: the total is already in the tooltip below, and a zero-value entry
    // in it reads as an error.
    silent: true,
    tooltip: { show: false },
    label: {
      show: true,
      position: 'top',
      fontSize: theme.seriesLabel,
      color: AXIS_LINE,
      formatter: (params: { dataIndex?: number }) => {
        const total = consumption[params.dataIndex ?? -1] ?? 0
        // A member who consumed nothing has no proportions to show and no bar to label.
        return total >= 0.005 ? money(total) : ''
      },
    },
  })

  return {
    grid: { left: 8, right: 16, top: 34, bottom: 4, containLabel: true },
    legend: {
      top: 0,
      itemHeight: 9,
      itemWidth: 14,
      textStyle: { fontSize: theme.legendLabel },
      // The invisible total series is not a thing to switch on and off.
      data: [...present, ...(anyRemainder ? [labels.uncategorised] : [])],
    },
    tooltip: theme.tooltips
      ? {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          /**
           * The member, their total, and each non-zero category with its share of that
           * total.
           *
           * Zero components are dropped rather than shown as "0.0%", which is what the
           * default formatter does for every category a member never spent on -- ten lines
           * of nothing on a bill with ten categories. Percentages are of that member's own
           * consumption, so they answer "what does *this* person spend on" rather than
           * repeating the pie.
           */
          formatter: (params) => {
            const items = (Array.isArray(params) ? params : [params]) as Array<{
              axisValue?: string
              dataIndex?: number
              seriesName?: string
              value?: unknown
            }>
            const first = items[0]
            const total = consumption[first?.dataIndex ?? -1] ?? 0
            const head = `${first?.axisValue ?? ''} &middot; ${labels.total} `
              + `${money(total)}${unit}`
            if (total < 0.005) return head
            const lines = items
              .filter((item) => item.seriesName !== labels.total)
              .map((item) => ({
                name: item.seriesName ?? '',
                value: typeof item.value === 'number' ? item.value : 0,
              }))
              .filter((item) => item.value >= 0.005)
              .map(
                (item) =>
                  `${item.name} ${money(item.value)}${unit}`
                  + ` (${percent(item.value / total)})`,
              )
            return [head, ...lines].join('<br/>')
          },
        }
      : undefined,
    xAxis: {
      type: 'category',
      data: report.positions.map((position) => position.member),
      axisLabel: { fontSize: theme.categoryLabel },
      axisLine: { lineStyle: { color: AXIS_LINE } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: theme.axisLabel, formatter: axisValue },
      splitLine: { lineStyle: { color: GRID_LINE } },
    },
    series,
  }
}

/**
 * The settlement, as a ring of members with an arrow per transfer.
 *
 * Two things about this chart were bugs before they were decisions.
 *
 * **`preserveAspect`.** A graph series with `layout: 'none'` is fitted by stretching
 * the data's bounding box onto the chart's box, and unless the two have the same
 * proportions that stretch is non-uniform -- applied to the symbols and the edge
 * labels as well as the positions. On a wide, short chart the dots came out as
 * horizontal dashes and the amounts were squashed into unreadable smudges. Preserving
 * the aspect ratio makes the fit uniform: round dots, upright text, at the cost of
 * some unused width on a wide screen. (The other charts never hit this because an
 * automatic layout supplies no coordinates, so ECharts falls back to the view rect and
 * the scale is 1:1 by construction.)
 *
 * **The amount on every edge.** Not a tooltip: paper has no hover, and a diagram whose
 * figures can only be revealed by pointing at them cannot be checked against the table
 * it sits under.
 *
 * Returns an option with no data when the graph should not be drawn -- the caller
 * decides that with `shouldShowSettlementGraph`. Keeping the factory total means a
 * mistake at a call site draws an empty box rather than throwing mid-print.
 */
export function settlementGraphOption(
  report: Report,
  labels: { pays: string; receives: string },
  money: (value: number) => string,
  theme: ChartTheme = SCREEN_THEME,
): EChartsOption {
  const data = settlementGraphData(report)
  const nodes = [...(data?.payers ?? []), ...(data?.receivers ?? [])]

  return {
    // Its own formatter rather than the shared one: ECharts writes an edge's endpoints
    // as "甲 > 乙", and `>` reads as a comparison. An arrow says which way the money
    // goes, which is the whole content of the edge.
    tooltip: theme.tooltips
      ? {
          trigger: 'item',
          // `trigger: 'item'` never passes an array, but the callback's type admits one.
          formatter: (params) => {
            const item = (Array.isArray(params) ? params[0] : params) as {
              dataType?: string
              name?: string
              data?: unknown
              value?: unknown
            } | undefined
            if (!item) return ''
            if (item.dataType === 'edge') {
              const link = item.data as { source?: string; target?: string } | undefined
              const value = typeof item.value === 'number' ? money(item.value) : ''
              return `${link?.source ?? ''} &rarr; ${link?.target ?? ''}<br/>${value}`
            }
            // A node: the member and what the settlement moves for them in total, which
            // the diagram shows only as a dot size.
            const node = nodes.find((candidate) => candidate.member === item.name)
            if (!node) return item.name ?? ''
            const label = node.side === 'payer' ? labels.pays : labels.receives
            return `${node.member}<br/>${label} ${money(node.total)}`
          },
        }
      : undefined,
    legend: {
      top: 0,
      itemHeight: 9,
      itemWidth: 14,
      textStyle: { fontSize: theme.legendLabel },
      // A key, not a filter. Hiding a side would hide real transfers and leave the
      // diagram disagreeing with the table.
      selectedMode: false,
      data: [labels.pays, labels.receives],
    },
    series: [
      {
        type: 'graph',
        // Fixed coordinates from the shared layer, so the same bill draws the same
        // picture every time and the screen and the paper cannot differ. A force
        // layout would settle somewhere new on every render.
        layout: 'none',
        preserveAspect: true,
        categories: [
          { name: labels.pays, itemStyle: { color: OWES } },
          { name: labels.receives, itemStyle: { color: OWED } },
        ],
        data: nodes.map((node) => ({
          name: node.member,
          x: node.x * GRAPH_UNITS,
          y: node.y * GRAPH_UNITS,
          // Sized by what this member moves, so the biggest contributor is visible
          // before any figure is read.
          symbolSize: node.size,
          category: node.side === 'payer' ? 0 : 1,
          itemStyle: {
            color: node.side === 'payer' ? OWES : OWED,
            borderColor: NODE_HALO,
            borderWidth: 2,
          },
          label: { position: node.labelSide },
        })),
        links: (data?.links ?? []).map((link) => ({
          source: link.from,
          target: link.to,
          value: link.amount,
          // A slight bow, all the same way: two members on opposite sides of the ring
          // would otherwise have their arrow pass through the middle, where every
          // other arrow is.
          lineStyle: { curveness: EDGE_CURVE },
        })),
        // With the aspect preserved the drawing is a square centred in the box, so the
        // circle's size is set by the height alone and generous side padding would only
        // waste width. The vertical inset is what leaves room for the legend above and
        // for the names beside the topmost and bottommost dots.
        left: 24,
        right: 24,
        top: 32,
        // Enough for a name *below* the lowest dot: an odd number of payers always puts
        // one at the bottom of the ring, where its label needs half the symbol plus the
        // label distance plus the line height. At 22 it was clipped by four pixels.
        bottom: 36,
        roam: false,
        draggable: false,
        label: { show: true, fontSize: theme.categoryLabel, distance: 7 },
        emphasis: { focus: 'adjacency', label: { show: true } },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        lineStyle: { color: EDGE_LINE, width: 1.2, opacity: 0.8 },
        edgeLabel: {
          show: true,
          fontSize: theme.seriesLabel,
          color: '#3a444e',
          // Behind the figure, so it stays readable where arrows cross.
          backgroundColor: EDGE_LABEL_BACKING,
          padding: [1, 3],
          borderRadius: 2,
          formatter: (params: { value?: unknown }) =>
            typeof params.value === 'number' ? money(params.value) : '',
        },
      },
    ],
  }
}

/**
 * The pool, as flow.
 *
 * One middle node, deliberately. Member-to-member flows would draw the re-pairing as
 * though it meant something, and "I never borrowed from 甲" is the misreading the whole
 * report exists to remove.
 */
export function sankeyOption(
  report: Report,
  poolLabel: string,
  money: (value: number) => string,
  theme: ChartTheme = SCREEN_THEME,
): EChartsOption {
  const sides = poolSides(report)
  // Labels outside their node on both sides. The default puts every label to the right
  // of its node, which on the left-hand column prints the name on top of the flow
  // leaving it -- dark red on dark red, effectively invisible.
  const nodes = [
    ...sides.debtors.map((position) => ({
      name: position.member,
      value: Math.abs(position.net),
      itemStyle: { color: OWES },
      label: { position: 'left' as const },
    })),
    {
      name: poolLabel,
      value: sides.in,
      itemStyle: { color: POOL },
      label: { position: 'top' as const },
    },
    ...sides.creditors.map((position) => ({
      name: position.member,
      value: position.net,
      itemStyle: { color: OWED },
      label: { position: 'right' as const },
    })),
  ]
  const links = [
    ...sides.debtors.map((position) => ({
      source: position.member,
      target: poolLabel,
      value: Math.abs(position.net),
    })),
    ...sides.creditors.map((position) => ({
      source: poolLabel,
      target: position.member,
      value: position.net,
    })),
  ]

  return {
    tooltip: tooltip(theme, report.meta.std_currency, 'item'),
    series: [
      {
        type: 'sankey',
        data: nodes,
        links,
        emphasis: { focus: 'adjacency' },
        // Room for a name and an amount outside the node on each side. Without it the
        // outer labels are clipped at the chart's edge -- and on paper there is no
        // scrolling to recover them.
        left: 88,
        right: 88,
        // 22, not 10: the pool node's label sits *above* it, and 10 clipped the top off
        // the text -- visible as "tne pool" in a screenshot at 420px.
        top: 22,
        bottom: 10,
        nodeWidth: 12,
        nodeGap: 12,
        label: {
          fontSize: theme.categoryLabel,
          // The amount beside the name: the diagram's proportions show relative size,
          // but a reader who wants to check a figure should not have to hover, and on
          // paper cannot. ECharts types `value` as every shape a data item can take,
          // hence the narrowing rather than a cast.
          formatter: (params: { name?: string; value?: unknown }) => {
            const name = params.name ?? ''
            if (name === poolLabel) return name
            return typeof params.value === 'number'
              ? `${name}  ${money(params.value)}`
              : name
          },
        },
        lineStyle: { color: 'gradient', opacity: 0.45 },
      },
    ],
  }
}

/**
 * ECharts, with only the parts this report uses.
 *
 * The convenience import (`import * as echarts from 'echarts'`) pulls in every chart
 * type the library has: maps, radar, candlesticks, gauges, the geo coordinate system,
 * the WebGL bridge. That was 1.13 MB minified, against the 106 kB of everything else
 * on the page put together -- ninety percent of the download for a report that draws
 * bars and one Sankey.
 *
 * Registering by hand instead means the bundle carries what is on the page and the cost
 * of adding a chart type is visible: a new one does not render until it is named here,
 * which is a better reminder of the weight than a comment would be.
 *
 * The SVG renderer, and only the SVG renderer. Canvas rasterises at screen resolution
 * and prints as a blurred mosaic, and this report exists to be printed (plan §7.4). Not
 * importing it at all is a stronger guarantee than remembering to pass
 * `renderer: 'svg'` at each call site -- there is nothing else to fall back to.
 */

import { use } from 'echarts/core'
import { BarChart, GraphChart, PieChart, SankeyChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { LabelLayout } from 'echarts/features'
import { SVGRenderer } from 'echarts/renderers'

use([
  BarChart,      // the category stacks
  PieChart,      // the whole bill by category
  SankeyChart,   // the pool
  GraphChart,    // the transfers, drawn
  GridComponent,
  TooltipComponent,
  LegendComponent,
  // The pie's slice labels, which sit outside the ring and would otherwise collide on a
  // bill with several similar-sized categories. Not optional: on paper a collided label is
  // the proportion the chart failed to state, and there is no hover to recover it.
  LabelLayout,
  SVGRenderer,
])

export { init } from 'echarts/core'
export type { EChartsOption } from 'echarts'
export type { ECharts } from 'echarts/core'

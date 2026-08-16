<script setup lang="ts">
/**
 * A chart for paper: drawn once, measured once, and then left alone.
 *
 * The screen chart watches its container and redraws on every resize, because a screen
 * gets resized. This one has no observer and no resize path at all, and that is a
 * consequence of the split rather than an omission: the print root is laid out at exactly
 * the paper's text width in both media, so the box this measures on screen is the box it
 * will be printed into. There is nothing to react to.
 *
 * That is what removed the code this file replaces. The old flow dispatched an event on
 * `beforeprint`, told every chart to re-measure, and hoped two animation frames were
 * enough before `window.print()` blocked -- because the shared DOM was 1280px wide on
 * screen and 180mm on paper, so every chart was composed at the wrong size and clipped.
 * A fixed-width print root makes the measurement right the first time.
 *
 * What is still needed is the `viewBox`: ECharts writes the pixel width and height it
 * measured onto the root `<svg>`, and a fixed-size SVG cannot absorb the small difference
 * between a browser's millimetre and a printer's. Turning those numbers into a viewBox
 * makes the drawing scale into whatever box it is given instead of being clipped by it.
 *
 * It registers a promise with `ready.ts` and resolves it on ECharts' `finished` event, so
 * printing waits for a real signal rather than a delay.
 */
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { init } from '../presentation/echarts'
import type { ECharts, EChartsOption } from '../presentation/echarts'
import { registerChart } from './ready'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    /** `short` / `tall` / `graph` map to the millimetre heights in print.css. */
    size?: 'short' | 'default' | 'tall' | 'graph'
    /** An accessible summary, for the preview window. Every figure a chart shows is
     *  also in a table on the same page. */
    label?: string
  }>(),
  { size: 'default', label: '' },
)

/**
 * How long to wait for a chart to say it has drawn before printing without it.
 *
 * A chart that never fires `finished` is a bug, but it must not be a bug that makes the
 * print button do nothing at all -- a report missing one chart is recoverable, a frozen
 * dialog is not. Generous, because this is a ceiling and not a delay: the normal path
 * resolves in a few milliseconds and never waits on this.
 */
const DRAW_TIMEOUT_MS = 4000

const host = ref<HTMLDivElement | null>(null)
const chart = shallowRef<ECharts | null>(null)

/** Rewrite the SVG's fixed pixel size as a viewBox, so it scales to its box. */
function makeScalable() {
  const svg = host.value?.querySelector('svg')
  if (!svg || !chart.value) return
  // From the chart rather than the element's attributes, which this may already have
  // rewritten to "100%" -- a viewBox of "0 0 100% 100%" is invalid, and the browser
  // says so once per redraw.
  const width = chart.value.getWidth()
  const height = chart.value.getHeight()
  if (!width || !height) return
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`)
  svg.setAttribute('preserveAspectRatio', 'xMinYMin meet')
  svg.setAttribute('width', '100%')
  svg.setAttribute('height', '100%')
}

onMounted(() => {
  if (!host.value) return

  // The renderer is not named here: `presentation/echarts` registers the SVG one and no
  // other, so there is nothing for a mistake at this call site to fall back to. Canvas
  // rasterises at screen resolution and prints as a blurred mosaic.
  const instance = init(host.value)
  chart.value = instance

  registerChart(
    new Promise<void>((resolve) => {
      const done = () => {
        makeScalable()
        resolve()
      }
      instance.on('finished', done)
      setTimeout(done, DRAW_TIMEOUT_MS)
    }),
  )

  // No animation: it cannot show on paper, and a chart still animating when the print
  // job composes renders mid-transition.
  instance.setOption({ animation: false, ...props.option }, { notMerge: true })
  makeScalable()
})

onBeforeUnmount(() => {
  chart.value?.dispose()
  chart.value = null
})
</script>

<template>
  <div
    ref="host"
    class="chart"
    :class="{ short: size === 'short', tall: size === 'tall', graph: size === 'graph' }"
    role="img"
    :aria-label="label"
  />
</template>

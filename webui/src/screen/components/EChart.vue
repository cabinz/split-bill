<script setup lang="ts">
/**
 * An ECharts instance for the screen.
 *
 * Two rules, one of which used to be three:
 *
 *   * **`renderer: 'svg'`, always.** Not configurable here -- `presentation/echarts`
 *     registers the SVG renderer and no other, so there is nothing to fall back to. The
 *     screen has no need for canvas either, and the guarantee is stronger when it is
 *     structural.
 *   * **Redraw when the container changes width.** A window resize, a section expanding
 *     above it, a drill-down opening. That is what a screen does.
 *
 * The third rule was "re-measure before printing", and it is gone. This chart is never
 * printed: the print view has its own `PrintChart`, laid out at the paper's width from the
 * moment it mounts, so nothing has to be re-measured under a print stylesheet and there is
 * no `beforeprint` handler left in the codebase. Along with it went the animation ban --
 * animation is fine on a screen, and it was only ever disabled because a chart still
 * transitioning when the print dialog opened rendered half-drawn.
 */
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { init } from '../../presentation/echarts'
import type { ECharts, EChartsOption } from '../../presentation/echarts'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    /** `short` / `tall` map to the heights in screen.css. */
    size?: 'short' | 'default' | 'tall'
    /** An accessible summary. A chart is unreadable to a screen reader, and the figures
     *  are all in a table elsewhere on the page anyway. */
    label?: string
  }>(),
  { size: 'default', label: '' },
)

const host = ref<HTMLDivElement | null>(null)
const chart = shallowRef<ECharts | null>(null)
let observer: ResizeObserver | null = null

function render() {
  chart.value?.setOption(props.option, { notMerge: true })
}

function resize() {
  chart.value?.resize()
}

onMounted(() => {
  if (!host.value) return
  chart.value = init(host.value)
  render()
  observer = new ResizeObserver(resize)
  observer.observe(host.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
  chart.value = null
})

watch(() => props.option, render, { deep: true })
</script>

<template>
  <div
    ref="host"
    class="chart"
    :class="{ short: size === 'short', tall: size === 'tall' }"
    role="img"
    :aria-label="label"
  />
</template>

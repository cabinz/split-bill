<script setup lang="ts">
/**
 * The printed report. One component, one input, no screen.
 *
 * Its whole world is the `PrintInput` prop: a report, a sheet, the export options and a
 * locale, all frozen when the user pressed the button. It reads no store, subscribes to
 * nothing, and has no access to whether a screen table is filtered, collapsed, scrolled or
 * showing one member's view. That is the plan's §5.1 rule, and it holds structurally rather
 * than by discipline -- there is nothing here to reach for.
 *
 * The body is unconditional except for the category section, which is absent when the bill
 * has no category data -- a property of the report, not a choice. Everything else that varies
 * is an explicit export option: which appendices are included, and whether the per-member
 * statements are among them. If a printed report should ever vary in any other way, the
 * variation has to be added to `ExportOptions` and appear in the dialog, where the user can
 * see it.
 *
 * Mounted in two places -- off-screen in the report window so the browser's own Ctrl-P has
 * something to print, and as the whole document in the preview window -- with the same
 * props both times, so the two cannot disagree.
 */
import { computed, onMounted, watch } from 'vue'
import PrintOverview from './PrintOverview.vue'
import PrintMemberStanding from './PrintMemberStanding.vue'
import PrintHowToSettle from './PrintHowToSettle.vue'
import PrintCategorySpending from './PrintCategorySpending.vue'
import PrintAppendices from './PrintAppendices.vue'
import type { PrintInput } from '../presentation/export-options'
import { hasCategories } from '../presentation/report-view-model'
import { resolve } from '../presentation/sections'
import { useI18n } from '../presentation/i18n'
import { resetReady, whenPrintReady } from './ready'

const props = defineProps<{ input: PrintInput }>()

const { t } = useI18n()

/**
 * What this document contains and what everything in it is called.
 *
 * From the frozen input and nothing else: the report decides whether there is a category
 * section, the export options decide which appendices exist, and the letters and numbers
 * follow from what is left. So a reference in the body is right for *this* document rather
 * than for the one the defaults would have produced.
 */
const structure = computed(() =>
  resolve(
    'print',
    { categories: hasCategories(props.input.report) },
    props.input.options,
  ),
)

/**
 * Re-arm the ready signal whenever the input changes, then announce when it is drawn.
 *
 * The flag has to be cleared *before* the new content renders, or a caller that checks it
 * immediately after handing over a new input sees the previous report's `true` and prints
 * a half-rendered page.
 */
watch(
  () => props.input,
  () => {
    resetReady()
    void whenPrintReady()
  },
  { flush: 'pre' },
)

onMounted(() => {
  void whenPrintReady()
})
</script>

<template>
  <div class="print-root" :data-frozen-at="input.frozenAt">
    <header class="masthead">
      <div>
        <h1>SplitBill</h1>
        <div class="subtitle">
          {{ input.report.meta.source_file }} &middot;
          {{ t('app.peopleRecords', {
            people: input.report.summary.member_count,
            records: input.report.summary.record_count,
          }) }}
        </div>
      </div>
    </header>

    <PrintOverview :report="input.report" :structure="structure" />
    <PrintMemberStanding :report="input.report" :structure="structure" />
    <PrintHowToSettle :report="input.report" :structure="structure" />
    <PrintCategorySpending :report="input.report" :structure="structure" />
    <PrintAppendices
      :report="input.report"
      :structure="structure"
      :sheet="input.sheet"
    />
  </div>
</template>

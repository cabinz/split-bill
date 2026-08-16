<script setup lang="ts">
/**
 * The preview window: the print view, on a screen, framed as paper.
 *
 * It is the same `PrintReport` the report window prints, with the same input, so what is on
 * show here is what comes out of the printer -- modulo the page breaks, which only the print
 * engine knows. A separate preview implementation would defeat the point of previewing.
 *
 * It fetches nothing. The input arrives from the window that opened it, by message; there is
 * no upload token in this window and no call to the service. A preview URL opened on its own
 * -- bookmarked, refreshed after the parent closed -- has no report and says so, which is
 * honest: §5.1 makes this a transient entry point rather than a shareable link.
 *
 * The locale comes from the input rather than from storage, so a report frozen in Chinese
 * previews in Chinese even if this browser's remembered preference is English. It is applied
 * without being written back, because printing a report is not the user expressing a language
 * preference for their next session.
 */
import { onMounted, ref } from 'vue'
import PrintReport from './PrintReport.vue'
import type { PrintInput } from '../presentation/export-options'
import { applyLocale, useI18n } from '../presentation/i18n'
import { requestInput } from './channel'

const input = ref<PrintInput | null>(null)
const waiting = ref(true)
const { t } = useI18n()

/**
 * The toolbar's own print button.
 *
 * A convenience beside the browser's Ctrl-P, not a different mechanism: this window is the
 * print view and nothing else, so there is nothing to prepare and no ready signal to wait
 * for that mounting has not already waited for.
 */
function print() {
  window.print()
}

onMounted(async () => {
  const received = await requestInput()
  if (received) {
    applyLocale(received.locale)
    input.value = received
    document.title = t('print.reportFor', { file: received.report.meta.source_file })
  }
  waiting.value = false
})
</script>

<template>
  <div class="print-preview">
    <div class="print-toolbar">
      <div>
        <h1>{{ t('print.previewTitle') }}</h1>
        <p>{{ t('print.previewHint') }}</p>
      </div>
      <button v-if="input" type="button" @click="print">
        {{ t('print.previewPrint') }}
      </button>
    </div>

    <p v-if="waiting" class="print-status">{{ t('print.waiting') }}</p>
    <p v-else-if="!input" class="print-status">{{ t('print.noInput') }}</p>

    <PrintReport v-if="input" :input="input" />
  </div>
</template>

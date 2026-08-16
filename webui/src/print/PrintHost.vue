<script setup lang="ts">
/**
 * Where the print view lives inside the report window.
 *
 * A sibling of the screen view, not a child: on paper the screen tree is hidden wholesale
 * and this one is shown, which only works if neither contains the other.
 *
 * `aria-hidden`, because this is a second rendering of a report the screen view is already
 * presenting. Without it a screen reader reads the whole thing twice, and the second time
 * without the controls that make it navigable.
 *
 * It renders nothing until there is a report. The empty case is a report window where the
 * user has not confirmed an import yet, and there is no meaningful blank document to print
 * then -- `printInput` is null and the browser's own Ctrl-P produces an empty page, which is
 * the honest result for a page that is showing an upload form.
 */
import PrintReport from './PrintReport.vue'
import { printInput } from './controller'
</script>

<template>
  <div v-if="printInput" class="print-host" aria-hidden="true">
    <PrintReport :input="printInput" />
  </div>
</template>

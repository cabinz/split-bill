<script setup lang="ts">
/**
 * The screen view: the page you scroll, with the controls on it.
 *
 * Holds the only state there is -- the upload token, the options, the report -- and hands
 * it to sections that display it. No arithmetic here or anywhere below: every figure came
 * from Python, which is what makes it impossible for this page and the terminal to disagree
 * about what somebody owes.
 *
 * The sections run in the order of plan §7.2, which is deliberate: self-evident first,
 * action last. Nobody accepts a list of payments before they accept the figures the
 * payments came from.
 *
 * It owns none of the printing. `print/controller.ts` is given a frozen copy of the report
 * and the export options, and the print view renders from that -- so this component's
 * filters, expanded rows and current-member selection are invisible to the printed
 * document, and it in turn does not have to keep its DOM printable. What used to be here --
 * opening every `<details>` before printing and closing them afterwards -- is gone rather
 * than moved.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ImportPanel from './components/ImportPanel.vue'
import FindingsNotice from './components/FindingsNotice.vue'
import Overview from './components/Overview.vue'
import MemberStanding from './components/MemberStanding.vue'
import HowToSettle from './components/HowToSettle.vue'
import CategorySpending from './components/CategorySpending.vue'
import DetailsAndChecking from './components/DetailsAndChecking.vue'
import { ApiFailure, fetchPreview, fetchReport, health, parseBill } from '../api'
import PrintHost from '../print/PrintHost.vue'
import { openPreview, previewBlocked, printNow, syncLive } from '../print/controller'
import {
  defaultExportOptions,
  type ExportOptions,
} from '../presentation/export-options'
import { hasCategories } from '../presentation/report-view-model'
import { resolve } from '../presentation/sections'
import {
  SUPPORTED_LOCALES,
  locale as activeLocale,
  translateBackendMessage,
  useI18n,
  type Locale,
} from '../presentation/i18n'
import type {
  Findings,
  ParseResponse,
  PreviewResponse,
  Report,
  ReportOptions,
  Sheet,
} from '../presentation/types'

const parsed = ref<ParseResponse | null>(null)
const preview = ref<PreviewResponse | null>(null)
const previewSignature = ref<string | null>(null)
const report = ref<Report | null>(null)
const reportSheet = ref<Sheet | null>(null)
const importSheet = ref<Sheet | null>(null)
const findings = ref<Findings | null>(null)
const error = ref<string | null>(null)
const reading = ref(false)
const validating = ref(false)
const generating = ref(false)
const serviceUp = ref(true)
const me = ref<string | null>(null)
const exportDialog = ref<HTMLDialogElement | null>(null)
const step = ref<'import' | 'report'>('import')
const { locale, setLocale, t } = useI18n()

/**
 * What the printed report should contain.
 *
 * Passed to the print view as part of its frozen input, so this is the only channel by
 * which the screen can affect what is printed. Anything else the user does here -- filter
 * the settlement to one member, collapse a drill-down, scroll -- cannot reach it.
 */
const exportOptions = ref<ExportOptions>(defaultExportOptions())

const options = ref<ReportOptions>(blankOptions())
const busy = computed(() => reading.value || validating.value || generating.value)
const previewReady = computed(
  () =>
    preview.value?.ok === true &&
    previewSignature.value === optionsSignature(parsed.value?.token, options.value),
)
const previewMembers = computed(() => preview.value?.members ?? parsed.value?.members ?? [])
const previewBaseAmounts = computed(
  () => preview.value?.base_amounts ?? parsed.value?.base_amounts ?? [],
)

let validationTimer: ReturnType<typeof setTimeout> | null = null
let validationRequest = 0
let validationAbort: AbortController | null = null

function blankOptions(): ReportOptions {
  return {
    columns: {},
    separator: ',',
    all_selector: 'all',
    std_currency: null,
    exchange_rates: [],
  }
}

onMounted(async () => {
  serviceUp.value = await health()
})

/**
 * Keep the mounted print view fed with a fresh snapshot.
 *
 * The print view is mounted whenever there is a report, so that the browser's own Ctrl-P
 * has a document to print -- it never calls our code, so a print view that only existed
 * after a click would leave the keyboard shortcut printing a blank sheet. Re-freezing on
 * every change keeps that mounted copy a snapshot rather than a live view.
 *
 * The locale is in the dependency list because a printed report is in one language; the
 * frozen input has to be re-taken when the picker changes or the print view keeps rendering
 * the previous one.
 */
watch(
  [report, reportSheet, exportOptions, activeLocale],
  () => syncLive(report.value, reportSheet.value, exportOptions.value),
  { deep: true, immediate: true },
)

function reset() {
  if (validationTimer) clearTimeout(validationTimer)
  validationTimer = null
  validationAbort?.abort()
  validationAbort = null
  validationRequest += 1
  reading.value = false
  validating.value = false
  generating.value = false
  parsed.value = null
  preview.value = null
  previewSignature.value = null
  report.value = null
  reportSheet.value = null
  importSheet.value = null
  findings.value = null
  error.value = null
  me.value = null
  options.value = blankOptions()
  step.value = 'import'
}

function optionsSignature(token: string | undefined, value: ReportOptions): string {
  return JSON.stringify([token ?? null, value])
}

function describe(failure: unknown): string {
  if (failure instanceof ApiFailure) return translateBackendMessage(failure.message)
  if (failure instanceof TypeError) {
    // A fetch that never reached the service.
    return t('error.unreachable')
  }
  return translateBackendMessage(
    failure instanceof Error ? failure.message : String(failure),
  )
}

async function onFile(file: File) {
  reset()
  reading.value = true
  error.value = null
  try {
    const response = await parseBill(file)
    parsed.value = response
    preview.value = response
    importSheet.value = response.sheet
    findings.value = response.findings
    // Adopt what detection found, so the dropdowns show it and an untouched form
    // reproduces it exactly.
    const detectedOptions: ReportOptions = {
      ...blankOptions(),
      columns: Object.fromEntries(
        Object.entries(response.columns).map(([role, binding]) => [
          role,
          binding?.name ?? null,
        ]),
      ),
      std_currency: response.std_currency,
      exchange_rates: response.exchange_rates,
    }
    options.value = detectedOptions
    // Re-run through the lightweight preview endpoint so this and every later
    // option change follow the same path. No settlement analysis happens here.
    await refreshPreview(response.token, detectedOptions)
  } catch (failure) {
    parsed.value = null
    error.value = describe(failure)
  } finally {
    reading.value = false
  }
}

async function refreshPreview(
  token = parsed.value?.token,
  previewOptions = options.value,
) {
  if (!token) return
  const request = ++validationRequest
  const signature = optionsSignature(token, previewOptions)
  validationAbort?.abort()
  const controller = new AbortController()
  validationAbort = controller
  validating.value = true
  error.value = null
  try {
    const response = await fetchPreview(token, previewOptions, controller.signal)
    if (
      request !== validationRequest ||
      signature !== optionsSignature(parsed.value?.token, options.value)
    ) return
    preview.value = response
    importSheet.value = response.sheet
    previewSignature.value = signature
    findings.value = response.findings
    if (!response.ok) {
      error.value =
        response.findings.errors.length === 1
          ? t('error.notReady')
          : t('error.notReadyMany', { count: response.findings.errors.length })
    }
  } catch (failure) {
    if (
      request !== validationRequest ||
      signature !== optionsSignature(parsed.value?.token, options.value)
    ) return
    previewSignature.value = null
    error.value = describe(failure)
    if (failure instanceof ApiFailure && failure.detail.findings) {
      findings.value = failure.detail.findings
    }
    if (failure instanceof ApiFailure && failure.detail.sheet) {
      importSheet.value = failure.detail.sheet
    }
  } finally {
    if (validationAbort === controller) validationAbort = null
    if (request === validationRequest) validating.value = false
  }
}

function onOptions(next: ReportOptions) {
  options.value = next
  previewSignature.value = null
  error.value = null
  findings.value = null
  validationRequest += 1
  validationAbort?.abort()
  validationAbort = null
  if (validationTimer) clearTimeout(validationTimer)
  validationTimer = setTimeout(() => {
    validationTimer = null
    void refreshPreview()
  }, 350)
}

function validateNow() {
  if (validationTimer) {
    clearTimeout(validationTimer)
    validationTimer = null
  }
  void refreshPreview()
}

async function confirmImport() {
  if (!previewReady.value || !parsed.value) return
  const signature = optionsSignature(parsed.value.token, options.value)
  generating.value = true
  error.value = null
  try {
    const response = await fetchReport(parsed.value.token, options.value)
    if (signature !== optionsSignature(parsed.value?.token, options.value)) return
    report.value = response.report
    reportSheet.value = response.sheet
    step.value = 'report'
    current.value = 'overview'
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (failure) {
    error.value = describe(failure)
    if (failure instanceof ApiFailure && failure.detail.findings) {
      findings.value = failure.detail.findings
    }
  } finally {
    generating.value = false
  }
}

function editImport() {
  // The visible report is deliberately invalidated when its frozen input is opened
  // for editing. The current draft can be confirmed again without re-uploading.
  report.value = null
  reportSheet.value = null
  me.value = null
  step.value = 'import'
  current.value = 'import'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** Ask what the exported report should contain before printing or previewing it. */
function openExportDialog() {
  previewBlocked.value = false
  exportDialog.value?.showModal()
}

function closeExportDialog() {
  exportDialog.value?.close()
}

/** A click on the dimmed backdrop, but not the dialog card, dismisses it. */
function onExportDialogClick(event: MouseEvent) {
  if (event.target === event.currentTarget) closeExportDialog()
}

/**
 * Open the printable report in a new window.
 *
 * The window has to be opened inside this handler's own synchronous run or the browser
 * treats it as an unrequested pop-up, so `openPreview` does that first and freezes the input
 * before anything can await. The dialog stays open when the pop-up was blocked, because
 * closing it would leave the click looking as though it had simply done nothing.
 */
function previewPrintable() {
  if (!report.value) return
  if (openPreview(report.value, reportSheet.value, exportOptions.value)) {
    closeExportDialog()
  }
}

/** Freeze, wait for the print view to finish rendering, then open the print dialog. */
async function print() {
  if (!report.value) return
  closeExportDialog()
  await printNow(report.value, reportSheet.value, exportOptions.value)
}

/**
 * What this report's sections are, and what they are numbered.
 *
 * Worked out from the report rather than declared: a bill with no category column has no
 * category section, and the sections after it are numbered as though it never existed. Every
 * component reads its own number out of this, so the headings, the nav and the prose's
 * cross-references cannot disagree.
 *
 * The screen's structure ignores the export options -- they decide what is *printed*, and the
 * page shows all four checking tables regardless. `appendix: true` here means "the checking
 * subsections exist", which on screen they always do.
 */
const structure = computed(() =>
  resolve(
    'screen',
    { categories: report.value ? hasCategories(report.value) : false },
    { appendix: true, statements: true },
  ),
)

const sections = computed(() =>
  structure.value.body.map((entry) => ({ id: entry.id, label: t(entry.navKey) })),
)

const current = ref('import')

let observer: IntersectionObserver | null = null

async function observeReportSections() {
  if (!report.value) return
  await nextTick()
  for (const section of sections.value) {
    const element = document.getElementById(section.id)
    if (element) observer?.observe(element)
  }
}

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) current.value = entry.target.id
      }
    },
    { rootMargin: '-20% 0px -70% 0px' },
  )
  void observeReportSections()
})

watch(report, () => void observeReportSections())

onBeforeUnmount(() => {
  if (validationTimer) clearTimeout(validationTimer)
  validationAbort?.abort()
  observer?.disconnect()
})
</script>

<template>
  <div class="app screen-root">
    <header class="masthead">
      <div>
        <h1>SplitBill</h1>
        <div class="subtitle">
          <template v-if="report">
            {{ report.meta.source_file }} &middot;
            {{ t('app.peopleRecords', {
              people: report.summary.member_count,
              records: report.summary.record_count,
            }) }}
          </template>
          <template v-else>
            {{ t('app.tagline') }}
          </template>
        </div>
      </div>
      <div class="row masthead-actions">
        <button v-if="report" @click="editImport">{{ t('app.editImport') }}</button>
        <label class="language-picker">
          <span>{{ t('language.label') }}</span>
          <select
            :value="locale"
            @change="setLocale(($event.target as HTMLSelectElement).value as Locale)"
          >
            <option v-for="item in SUPPORTED_LOCALES" :key="item" :value="item">
              {{ t(`language.${item}`) }}
            </option>
          </select>
        </label>
        <button v-if="report" @click="openExportDialog">{{ t('app.print') }}</button>
      </div>
    </header>

    <ol class="stepper" :aria-label="t('steps.label')">
      <li :class="{ active: step === 'import', complete: step === 'report' }">
        <span class="step-number">1</span>
        <span>
          <strong>{{ t('steps.import') }}</strong>
          <small>{{ t('steps.importHint') }}</small>
        </span>
      </li>
      <li :class="{ active: step === 'report' }">
        <span class="step-number">2</span>
        <span>
          <strong>{{ t('steps.report') }}</strong>
          <small>{{ t('steps.reportHint') }}</small>
        </span>
      </li>
    </ol>

    <dialog
      ref="exportDialog"
      class="export-dialog"
      aria-labelledby="export-dialog-title"
      aria-describedby="export-dialog-hint"
      @click="onExportDialogClick"
    >
      <form method="dialog" @submit.prevent>
        <header>
          <div>
            <h2 id="export-dialog-title">{{ t('export.title') }}</h2>
            <p id="export-dialog-hint" class="hint">{{ t('export.hint') }}</p>
          </div>
          <!-- The only way out. §5.2: there is no "Cancel" button, because both actions
               are things the user might want and neither is the dialog's default. -->
          <button
            type="button"
            class="dialog-close"
            :aria-label="t('export.close')"
            @click="closeExportDialog"
          >&times;</button>
        </header>

        <label class="export-option">
          <input
            v-model="exportOptions.appendix"
            type="checkbox"
            data-option="appendix"
          />
          <span>
            <strong>{{ t('export.includeStatement') }}</strong>
            <span class="export-option-hint">
              {{ t('export.statementHint') }}
              <template v-if="report">
                {{ t('export.statementSize', {
                  records: report.summary.record_count,
                  rows: report.ledger.length,
                }) }}
              </template>
            </span>
          </span>
        </label>

        <!--
          A child of the switch above, and disabled rather than hidden when the parent is
          off: a checkbox that vanishes reads as a feature that does not exist, and the
          hint says why it is unavailable.
        -->
        <label class="export-option export-option-child" :class="{ disabled: !exportOptions.appendix }">
          <input
            v-model="exportOptions.statements"
            type="checkbox"
            data-option="statements"
            :disabled="!exportOptions.appendix"
          />
          <span>
            <strong>{{ t('export.includeStatements') }}</strong>
            <span class="export-option-hint">
              {{ t('export.statementsHint') }}
              <template v-if="report">
                {{ t('export.statementsSize', {
                  count: report.summary.member_count,
                }) }}
              </template>
              <template v-if="!exportOptions.appendix">
                {{ t('export.statementsNeedsAppendix') }}
              </template>
            </span>
          </span>
        </label>

        <p v-if="previewBlocked" class="notice error export-blocked">
          {{ t('export.blocked') }}
        </p>

        <footer>
          <p class="tiny muted export-actions-hint">{{ t('export.previewHint') }}</p>
          <div class="row">
            <button type="button" @click="previewPrintable">{{ t('export.preview') }}</button>
            <button type="button" class="primary" @click="print">
              {{ t('export.print') }}
            </button>
          </div>
        </footer>
      </form>
    </dialog>

    <nav v-if="step === 'report' && report" class="toc">
      <a
        v-for="section in sections"
        :key="section.id"
        :href="`#${section.id}`"
        :class="{ current: current === section.id }"
      >{{ section.label }}</a>
    </nav>

    <div v-if="!serviceUp" class="notice error" style="margin-bottom: 1rem">
      <strong>{{ t('service.title') }}</strong>
      {{ t('service.body') }}
    </div>

    <FindingsNotice
      v-if="step === 'import' && error && findings?.errors?.length"
      kind="error"
      :title="error"
      :findings="findings.errors"
      style="margin-bottom: 1rem"
    />

    <div
      v-else-if="step === 'import' && error"
      class="notice error"
      style="margin-bottom: 1rem"
    ><strong>{{ error }}</strong></div>

    <FindingsNotice
      v-if="step === 'import' && findings?.warnings?.length"
      kind="warn"
      :title="findings.warnings.length === 1 ? t('warning.one') : t('warning.many')"
      :findings="findings.warnings"
      style="margin-bottom: 1rem"
    />

    <ImportPanel
      v-if="step === 'import'"
      :parsed="parsed"
      :sheet="importSheet"
      :members="previewMembers"
      :base-amounts="previewBaseAmounts"
      :options="options"
      :busy="busy"
      :validating="validating"
      :generating="generating"
      :ready="previewReady"
      @file="onFile"
      @update:options="onOptions"
      @validate="validateNow"
      @confirm="confirmImport"
      @reset="reset"
    />

    <template v-if="step === 'report' && report">
      <Overview :report="report" :structure="structure" />
      <MemberStanding :report="report" :structure="structure" :me="me" />
      <HowToSettle
        :report="report"
        :structure="structure"
        :me="me"
        @update:me="me = $event"
      />
      <CategorySpending :report="report" :structure="structure" />
      <DetailsAndChecking :report="report" :structure="structure" :sheet="reportSheet" />
    </template>
  </div>

  <!-- A sibling of the screen view, never a child: on paper the screen tree is hidden
       wholesale and this one shown, which only works if neither contains the other. -->
  <PrintHost />
</template>

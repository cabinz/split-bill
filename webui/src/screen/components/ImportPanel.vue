<script setup lang="ts">
/**
 * Importing a bill, and correcting what detection guessed.
 *
 * The one part of the page that is not a view. Everything else displays a report;
 * this decides which report to ask for -- which columns mean what, which separator
 * splits a name cell, what currency to settle in.
 *
 * The column dropdowns are populated from the sheet's real headers rather than
 * being free text. A typo in a column name is a validation error two steps later,
 * and the sheet already says what its columns are called.
 */
import { computed, ref } from 'vue'
import type {
  ColumnRole,
  ExchangeRate,
  ParseResponse,
  ReportOptions,
  Sheet,
} from '../../presentation/types'
import {
  DESCRIPTIVE_ROLES,
  SELECTABLE_ROLES,
} from '../../presentation/types'
import { useI18n } from '../../presentation/i18n'
import { cell, money } from '../../presentation/format'
import ColumnSelect, { type ColumnSelectOption } from './ColumnSelect.vue'

const props = defineProps<{
  parsed: ParseResponse | null
  sheet: Sheet | null
  members: string[]
  baseAmounts: (number | null)[]
  options: ReportOptions
  busy: boolean
  validating: boolean
  generating: boolean
  /** True only when the preview belongs to the current option snapshot. */
  ready: boolean
}>()

const emit = defineEmits<{
  file: [file: File]
  'update:options': [options: ReportOptions]
  validate: []
  confirm: []
  reset: []
}>()

const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const { t } = useI18n()

/** Only the three columns needed to construct a ledger are mandatory. Currency
 * and category both have valid no-column modes. */
const requiredColumnRoles = new Set<ColumnRole>(['creditor', 'debtor', 'amount'])

const headers = computed<string[]>(() => {
  const columns = props.sheet?.columns ?? []
  // Blank and duplicate headers exist in real spreadsheets; neither can be
  // selected meaningfully, so they are left out of the dropdowns rather than
  // offered as identical options.
  return [...new Set(columns.filter((column) => column.trim() !== ''))]
})

function patch(change: Partial<ReportOptions>) {
  emit('update:options', { ...props.options, ...change })
}

function setColumn(role: ColumnRole, value: string) {
  patch({
    columns: { ...props.options.columns, [role]: value === '' ? null : value },
  })
}

/** Null is an explicit choice for optional roles, so `??` cannot be used here:
 * falling back to the detected binding would make a cleared dropdown spring back. */
function selectedColumn(role: ColumnRole): string {
  if (Object.prototype.hasOwnProperty.call(props.options.columns, role)) {
    return props.options.columns[role] ?? ''
  }
  return props.parsed?.columns?.[role]?.name ?? ''
}

function detectedColumn(role: ColumnRole): string | null {
  const binding = props.parsed?.columns?.[role]
  return binding?.auto ? binding.name : null
}

function columnOptions(role: ColumnRole): ColumnSelectOption[] {
  const choices = headers.value.map((header) => ({ value: header, label: header }))
  if (requiredColumnRoles.has(role)) return choices

  const emptyLabel = role === 'currency'
    ? t('import.noneConversion')
    : t('import.noneCategory')
  return [{ value: '', label: emptyLabel }, ...choices]
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) emit('file', file)
}

function onPick(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) emit('file', file)
  // Cleared so re-picking the same file after an edit still fires a change.
  if (fileInput.value) fileInput.value.value = ''
}

// --- exchange rates -------------------------------------------------------

const rateBase = ref('')
const rateRate = ref('')

/** The quote side is always the standard currency: converting into anything else
 *  would produce amounts the settlement cannot use. */
const quote = computed(() => props.options.std_currency ?? '')

const canAddRate = computed(
  () =>
    quote.value.trim() !== '' &&
    rateBase.value.trim() !== '' &&
    Number.isFinite(Number(rateRate.value)) &&
    Number(rateRate.value) > 0,
)

function addRate() {
  if (!canAddRate.value) return
  const base = rateBase.value.trim().toUpperCase()
  const rate: ExchangeRate = {
    base,
    quote: quote.value.trim().toUpperCase(),
    rate: Number(rateRate.value),
  }
  const kept = props.options.exchange_rates.filter(
    (existing) => !(existing.base === rate.base && existing.quote === rate.quote),
  )
  patch({ exchange_rates: [...kept, rate] })
  rateBase.value = ''
  rateRate.value = ''
}

function removeRate(index: number) {
  const rates = [...props.options.exchange_rates]
  rates.splice(index, 1)
  patch({ exchange_rates: rates })
}

const currencyColumn = computed(() => props.options.columns.currency ?? null)

const previewRows = computed(() => props.sheet?.rows ?? [])

const showBaseAmount = computed(() => props.options.std_currency !== null)

/** Date and item are useful detail when detected, but category is the optional
 * descriptive role that changes a chart and is therefore editable above. */
const detectedDetailRoles = DESCRIPTIVE_ROLES.filter((role) => role !== 'category')
</script>

<template>
  <section id="import" class="section">
    <header>
      <div>
        <h2>{{ t('import.title') }}</h2>
        <p class="hint">{{ t('import.hint') }}</p>
      </div>
      <button v-if="parsed" @click="emit('reset')">{{ t('import.startOver') }}</button>
    </header>

    <div
      v-if="!parsed"
      class="dropzone"
      :class="{ over: dragging }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <h3>{{ t('import.drop') }}</h3>
      <p class="muted small">{{ t('import.formats') }}</p>
      <p>
        <button class="primary" :disabled="busy" @click="fileInput?.click()">
          {{ busy ? t('import.reading') : t('import.choose') }}
        </button>
      </p>
      <input
        ref="fileInput"
        type="file"
        accept=".csv,.tsv,.xlsx"
        hidden
        @change="onPick"
      />
    </div>

    <div v-else class="stack">
      <div class="row">
        <strong class="grow">{{ parsed.source_file }}</strong>
        <span class="muted small">
          {{ t('import.dimensions', {
            rows: sheet?.total_rows ?? 0,
            columns: sheet?.columns.length ?? 0,
          }) }}
        </span>
      </div>

      <!-- Columns -->
      <div>
        <h3>{{ t('import.columns') }}</h3>
        <p class="muted tiny">{{ t('import.columnsHint') }}</p>
        <div class="row" style="align-items: flex-end">
          <div v-for="role in SELECTABLE_ROLES" :key="role" class="field">
            <span class="field-caption">{{ t(`role.${role}`) }}<sup
              v-if="requiredColumnRoles.has(role)"
              class="required-mark"
              aria-hidden="true"
            >*</sup></span>
            <ColumnSelect
              :data-column-role="role"
              :model-value="selectedColumn(role)"
              :options="columnOptions(role)"
              :detected-value="detectedColumn(role)"
              :detected-label="t('import.detected')"
              :label="t(`role.${role}`)"
              :placeholder="t('import.selectColumn')"
              :required="requiredColumnRoles.has(role)"
              :title="t(`roleHelp.${role}`)"
              @update:model-value="setColumn(role, $event)"
            />
          </div>
        </div>

        <p class="muted tiny" style="margin-top: .5rem">
          {{ t('import.alsoFound') }}
          <template v-for="(role, index) in detectedDetailRoles" :key="role">
            <span v-if="index > 0">, </span>
            <span v-if="parsed.columns[role]?.name">
              {{ t(`role.${role}`) }} = <code>{{ parsed.columns[role]?.name }}</code>
            </span>
            <span v-else class="faint">{{ t(`role.${role}`) }} = {{ t('import.none') }}</span>
          </template>
          <span class="faint">
            &mdash; {{ t('import.optional') }}
          </span>
        </p>
      </div>

      <!-- Splitting -->
      <div class="row" style="align-items: flex-end">
        <div class="field">
          <span>{{ t('import.separator') }}</span>
          <input
            type="text"
            size="4"
            :value="options.separator"
            :title="t('import.separatorHelp')"
            @change="patch({ separator: ($event.target as HTMLInputElement).value || ',' })"
          />
        </div>
        <div class="field">
          <span>{{ t('import.everyoneAs') }}</span>
          <input
            type="text"
            size="8"
            :value="options.all_selector"
            :title="t('import.everyoneHelp')"
            @change="patch({ all_selector: ($event.target as HTMLInputElement).value || 'all' })"
          />
        </div>
        <div class="field">
          <span>{{ t('import.settleIn') }}</span>
          <input
            type="text"
            size="6"
            :placeholder="t('import.none')"
            :value="options.std_currency ?? ''"
            :title="t('import.currencyHelp')"
            @change="patch({
              std_currency: ($event.target as HTMLInputElement).value.trim().toUpperCase() || null,
            })"
          />
        </div>
      </div>

      <!-- Rates -->
      <div v-if="options.std_currency">
        <h3>{{ t('import.exchangeRates') }}</h3>
        <p class="muted tiny">
          {{ t('import.exchangeHint', { currency: options.std_currency }) }}
          <span v-if="!currencyColumn" class="owes">
            {{ t('import.noCurrencyColumn') }}
          </span>
        </p>
        <table v-if="options.exchange_rates.length" class="compact">
          <tbody>
            <tr v-for="(rate, index) in options.exchange_rates" :key="index">
              <td><code>1 {{ rate.base }}</code></td>
              <td class="faint">=</td>
              <td class="num">{{ rate.rate }}</td>
              <td><code>{{ rate.quote }}</code></td>
              <td><button class="tiny" @click="removeRate(index)">{{ t('import.remove') }}</button></td>
            </tr>
          </tbody>
        </table>
        <div class="row" style="align-items: flex-end; margin-top: .4rem">
          <div class="field">
            <span>{{ t('import.oneUnit') }}</span>
            <input v-model="rateBase" type="text" size="5" placeholder="KRW" />
          </div>
          <span class="faint">=</span>
          <div class="field">
            <span>{{ t('import.rateAmount', { currency: options.std_currency }) }}</span>
            <input v-model="rateRate" type="text" size="10" placeholder="0.0057715" />
          </div>
          <button :disabled="!canAddRate" @click="addRate">{{ t('import.addRate') }}</button>
        </div>
      </div>

      <div class="participant-preview">
        <div class="participant-heading">
          <div>
            <h3>{{ t('import.participants') }}</h3>
            <p class="muted tiny">{{ t('import.participantsHint') }}</p>
          </div>
          <span class="participant-count">
            {{ t('import.participantCount', { count: members.length }) }}
          </span>
        </div>
        <div v-if="members.length" class="participant-list">
          <span v-for="member in members" :key="member" class="participant-chip">
            {{ member }}
          </span>
        </div>
        <p v-else class="muted tiny">{{ t('import.noParticipants') }}</p>
      </div>

      <!-- Preview -->
      <div class="import-preview">
        <div class="import-preview-heading">
          <div>
            <h3>{{ t('import.sheet') }}</h3>
            <p class="muted tiny">
              {{ t('import.previewAll', { count: sheet?.total_rows ?? 0 }) }}
            </p>
          </div>
          <span
            class="validation-state"
            :class="ready ? 'valid' : validating ? 'checking' : 'invalid'"
            role="status"
          >
            {{ ready
              ? t('import.validationReady')
              : validating
                ? t('import.validating')
                : t('import.validationNeeded') }}
          </span>
        </div>
        <div class="table-wrap import-table-wrap">
          <table class="compact">
            <thead>
              <tr>
                <th class="num">#</th>
                <th v-for="column in sheet?.columns" :key="column">{{ column }}</th>
                <th v-if="showBaseAmount" class="num base-amount">
                  {{ t('import.baseAmount', { currency: options.std_currency ?? '' }) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in previewRows" :key="index">
                <td class="num faint">{{ index + 1 }}</td>
                <td v-for="(value, column) in row" :key="column">{{ cell(value) }}</td>
                <td v-if="showBaseAmount" class="num base-amount">
                  <template v-if="baseAmounts[index] !== null && baseAmounts[index] !== undefined">
                    {{ money(baseAmounts[index] ?? 0) }}
                  </template>
                  <span v-else class="faint">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="confirm-bar">
        <div>
          <strong>{{ ready ? t('import.readyTitle') : t('import.notReadyTitle') }}</strong>
          <p class="muted tiny">
            {{ ready ? t('import.readyHint') : t('import.notReadyHint') }}
          </p>
        </div>
        <div class="row">
          <button :disabled="busy" @click="emit('validate')">
            {{ validating ? t('import.validating') : t('import.checkAgain') }}
          </button>
          <button class="primary" :disabled="busy || !ready" @click="emit('confirm')">
            {{ generating ? t('import.generating') : t('import.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

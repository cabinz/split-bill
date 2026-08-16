<script setup lang="ts">
/**
 * The summary, and the sentence the rest of the report justifies.
 *
 * Identical in substance to the screen's overview and simpler in structure: no timestamp
 * in a corner that has to survive a flex wrap, no notice that appears and disappears.
 * Everything it states comes from `summary`, which Python computed.
 */
import { computed } from 'vue'
import type { Report } from '../presentation/types'
import { amount, integer, plural, timestamp } from '../presentation/format'
import { lendingEdges } from '../presentation/report-view-model'
import {
  bodySection,
  crossRef,
  printId,
  type ResolvedStructure,
} from '../presentation/sections'
import { translateBackendMessage, useI18n } from '../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()
const meta = computed(() => bodySection(props.structure, 'overview'))

/**
 * Where the source sheet ended up, if it was included.
 *
 * The overview is where a reader checks the input, so this is where the sheet is cited. Null
 * when the appendices were excluded, and then the sentence is omitted rather than left
 * pointing at a page that is not in this document.
 */
const sheetRef = computed(() => crossRef(props.structure, 'sheet', t))

/** How many pairs really lent to each other, before simplification. The interesting
 *  comparison: the settlement is almost always far shorter, and that gap is what makes
 *  people ask why they are paying somebody they never borrowed from. */
const realPairs = computed(() => lendingEdges(props.report).length)
const savedTransfers = computed(
  () => realPairs.value - props.report.settlement.length,
)
</script>

<template>
  <section v-if="meta" :id="printId(meta.id)" class="section" data-part="body">
    <header>
      <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
      <p class="hint">
        {{ t('overview.summary', {
          transfers: plural(report.summary.transaction_count, 'transfer'),
          verb: report.summary.transaction_count === 1 ? 'settles' : 'settle',
          amount: amount(report.summary.total_spend, currency),
          people: report.summary.member_count,
        }) }}
      </p>
    </header>

    <div class="cards">
      <div class="card">
        <div class="label">{{ t('overview.totalSpend') }}</div>
        <div class="value" data-fact="total-spend">
          {{ amount(report.summary.total_spend, currency) }}
        </div>
        <div class="note">
          {{ t('overview.acrossRecords', {
            count: integer(report.summary.record_count),
          }) }}
        </div>
      </div>
      <div class="card">
        <div class="label">{{ t('overview.people') }}</div>
        <div class="value" data-fact="member-count">{{ report.summary.member_count }}</div>
        <div class="note">{{ report.members.join('、') }}</div>
      </div>
      <div class="card">
        <div class="label">{{ t('overview.transfersNeeded') }}</div>
        <div class="value" data-fact="transfer-count">
          {{ report.summary.transaction_count }}
        </div>
        <div class="note">
          <template v-if="savedTransfers > 0">
            {{ t('overview.insteadPairs', { count: realPairs }) }}
          </template>
          <template v-else-if="report.summary.transaction_count === 0">
            {{ t('overview.everybodySquare') }}
          </template>
          <template v-else>{{ t('overview.onePerPair') }}</template>
        </div>
      </div>
      <div v-if="currency" class="card">
        <div class="label">{{ t('overview.settledIn') }}</div>
        <div class="value">{{ currency }}</div>
        <div class="note">
          {{ report.meta.exchange_rates.length
            ? plural(report.meta.exchange_rates.length, 'rate')
            : t('overview.noConversion') }}
        </div>
      </div>
    </div>

    <p v-if="report.meta.exchange_rates.length" class="tiny muted" style="margin-top: 2mm">
      {{ t('overview.ratesUsed') }}
      <span
        v-for="rate in report.meta.exchange_rates"
        :key="`${rate.base}/${rate.quote}`"
        class="badge"
      >1 {{ rate.base }} = {{ rate.rate }} {{ rate.quote }}</span>
    </p>

    <div v-if="report.meta.warnings.length" class="notice info" style="margin-top: 2mm">
      <ul>
        <li v-for="warning in report.meta.warnings" :key="warning">
          {{ translateBackendMessage(warning) }}
        </li>
      </ul>
    </div>

    <p v-if="sheetRef" class="tiny muted" style="margin-top: 2mm">
      <!-- A link in the PDF and a self-sufficient sentence on paper: "see Appendix D, the
           sheet as imported" tells a reader holding a printout what to look for, which
           "click here" would not. -->
      {{ t('overview.checkInput') }}
      <a :href="`#${sheetRef.anchor}`">{{ sheetRef.label }}</a>
    </p>

    <p class="tiny faint" style="margin-top: 2mm">
      {{ report.meta.source_file }} &middot; {{ timestamp(report.meta.generated_at) }}
    </p>
  </section>
</template>

<script setup lang="ts">
/**
 * The summary, and the sentence the rest of the report justifies.
 *
 * Plan §7.2's second section. The figures are the easy part; the sentence under them
 * is what the section is for. "Six transfers settle a bill of 37,986.31 between
 * seven people" is the claim, and everything below on the page is its working.
 */
import { computed } from 'vue'
import type { Report } from '../../presentation/types'
import { amount, integer, plural, timestamp } from '../../presentation/format'
import { bodySection, type ResolvedStructure } from '../../presentation/sections'
import { translateBackendMessage, useI18n } from '../../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()
const meta = computed(() => bodySection(props.structure, 'overview'))

/** How many pairs really lent to each other, before simplification.
 *
 * The interesting comparison on this page: the settlement is almost always far
 * shorter than the list of real obligations, and that gap is exactly what makes
 * people ask why they are paying somebody they never borrowed from. */
const realPairs = computed(() => props.report.lending_edges.length)

const savedTransfers = computed(
  () => realPairs.value - props.report.settlement.length,
)
</script>

<template>
  <section v-if="meta" :id="meta.id" class="section" data-part="body">
    <header>
      <div>
        <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
        <p class="hint">{{ t('overview.summary', {
          transfers: plural(report.summary.transaction_count, 'transfer'),
          verb: report.summary.transaction_count === 1 ? 'settles' : 'settle',
          amount: amount(report.summary.total_spend, currency),
          people: report.summary.member_count,
        }) }}</p>
      </div>
      <span class="muted tiny">
        {{ report.meta.source_file }} &middot;
        {{ timestamp(report.meta.generated_at) }}
      </span>
    </header>

    <div class="cards">
      <div class="card">
        <div class="label">{{ t('overview.totalSpend') }}</div>
        <div class="value" data-fact="total-spend">
          {{ amount(report.summary.total_spend, currency) }}
        </div>
        <div class="note">
          {{ t('overview.acrossRecords', { count: integer(report.summary.record_count) }) }}
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

    <div v-if="report.meta.exchange_rates.length" class="row" style="margin-top: .8rem">
      <span class="muted small">{{ t('overview.ratesUsed') }}</span>
      <span
        v-for="rate in report.meta.exchange_rates"
        :key="`${rate.base}/${rate.quote}`"
        class="badge"
      >
        1 {{ rate.base }} = {{ rate.rate }} {{ rate.quote }}
      </span>
    </div>

    <div v-if="report.meta.warnings.length" class="notice info" style="margin-top: .8rem">
      <ul>
        <li v-for="warning in report.meta.warnings" :key="warning">
          {{ translateBackendMessage(warning) }}
        </li>
      </ul>
    </div>
  </section>
</template>

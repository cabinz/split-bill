<script setup lang="ts">
/**
 * How to settle, printed: the pool, then the transfers.
 *
 * The same two-step argument as on screen. The pool explains why the counterparty is
 * arbitrary; the transfer table is what somebody actually does. Its conservation -- in = out
 * -- is stated in words as well as drawn, and on paper that matters more than on screen,
 * since paper is where somebody sits down with a calculator.
 *
 * The lending table is not here. On the real bill it is 28 rows, which in the middle of this
 * section would separate the pool from the payments it explains; it is an appendix, cited
 * from the paragraph that needs it. That citation is resolved rather than written down: with
 * the appendices excluded there is nothing to cite and the sentence is dropped, rather than
 * printing a reference to a page that is not in the document.
 *
 * There is no "as me" and no picker of any kind. A filter needs a control to unset it, and
 * paper has none -- print scope is an export option, not a leak of whatever the screen was
 * left showing.
 *
 * The transfer diagram has a stricter density threshold than the screen's, judged from the
 * report rather than inherited from the page: a printed chart is a fifth the height of a
 * screen one and cannot be scrolled or resized to recover a collision. Above it the table
 * prints alone, which is the whole degradation path -- no empty frame and no apology for a
 * chart the reader was never promised.
 */
import { computed } from 'vue'
import PrintChart from './PrintChart.vue'
import type { Report } from '../presentation/types'
import { amount, money, plural } from '../presentation/format'
import {
  netScale,
  poolBalances,
  poolSides,
  settlementGraphData,
  settlementTotal,
  shouldShowSettlementGraph,
  unsettled,
} from '../presentation/report-view-model'
import {
  PRINT_THEME,
  sankeyOption,
  settlementGraphOption,
} from '../presentation/chart-options'
import {
  aroundRef,
  bodySection,
  crossRef,
  printId,
  sectionHint,
  subsection,
  type ResolvedStructure,
} from '../presentation/sections'
import { useI18n } from '../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'settle'))
const hint = computed(() => sectionHint(meta.value, 'print', t))
const poolPart = computed(() => subsection(props.structure, 'settle', 'pool'))
const transfersPart = computed(() => subsection(props.structure, 'settle', 'transfers'))

const membersNumber = computed(
  () => bodySection(props.structure, 'members')?.number ?? 0,
)
const lendingRef = computed(() => crossRef(props.structure, 'lending', t))
const lendingText = computed(() => aroundRef(t('settlement.pairingRef')))

const sides = computed(() => poolSides(props.report))
const balanced = computed(() => poolBalances(sides.value))
const scale = computed(() => netScale(props.report))

function width(net: number): string {
  return `${Math.max((Math.abs(net) / scale.value) * 100, 0.8)}%`
}

const total = computed(() => settlementTotal(props.report))
const remainders = computed(() => unsettled(props.report))

const showSettlementGraph = computed(() =>
  shouldShowSettlementGraph(settlementGraphData(props.report), 'print'),
)
</script>

<template>
  <section v-if="meta" :id="printId(meta.id)" class="section" data-part="body">
    <header>
      <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
      <p class="hint">{{ hint }}</p>
    </header>

    <h3 v-if="poolPart" :id="printId(poolPart.id)">
      {{ poolPart.label }} &middot; {{ t(poolPart.titleKey) }}
    </h3>
    <p class="tiny muted">{{ t('pool.hint') }}</p>

    <div class="pool" :data-pool-in="sides.in.toFixed(2)" :data-pool-out="sides.out.toFixed(2)">
      <div class="side">
        <h4>{{ t('pool.paysIn') }} &middot; {{ sides.debtors.length }}</h4>
        <div
          v-for="position in sides.debtors"
          :key="position.member"
          class="bar-row"
          data-pool-row="in"
        >
          <span class="name">{{ position.member }}</span>
          <span class="track">
            <span class="fill" :style="{ width: width(position.net), background: '#a8342f' }" />
          </span>
          <span class="value owes">{{ money(Math.abs(position.net)) }}</span>
        </div>
        <p v-if="!sides.debtors.length" class="faint small">
          {{ t('pool.nobodyUnderpaid') }}
        </p>
      </div>

      <div class="middle">
        <span class="value">{{ amount(sides.in, currency) }}</span>
        {{ t('pool.inOutAgain') }}
        <div class="tiny faint">
          {{ sides.debtors.length }} &rarr; {{ sides.creditors.length }}
        </div>
      </div>

      <div class="side">
        <h4>{{ t('pool.drawsOut') }} &middot; {{ sides.creditors.length }}</h4>
        <div
          v-for="position in sides.creditors"
          :key="position.member"
          class="bar-row"
          data-pool-row="out"
        >
          <span class="name">{{ position.member }}</span>
          <span class="track">
            <span class="fill" :style="{ width: width(position.net), background: '#1a6b45' }" />
          </span>
          <span class="value owed">{{ money(position.net) }}</span>
        </div>
        <p v-if="!sides.creditors.length" class="faint small">
          {{ t('pool.nobodyOverpaid') }}
        </p>
      </div>
    </div>

    <p class="tiny" :class="balanced ? 'muted' : 'owes'" style="margin-top: 2mm">
      {{ t(balanced ? 'pool.balanced' : 'pool.unbalanced', {
        input: amount(sides.in, currency),
        output: amount(sides.out, currency),
      }) }}
    </p>

    <div v-if="sides.debtors.length && sides.creditors.length" style="margin-top: 4mm">
      <h4>{{ t('pool.flowTitle') }}</h4>
      <PrintChart
        :option="sankeyOption(report, t('pool.node'), money, PRINT_THEME)"
        size="tall"
        data-chart="pool-sankey"
        :label="t('pool.flowAria')"
      />
    </div>

    <h3 v-if="transfersPart" :id="printId(transfersPart.id)" style="margin-top: 6mm">
      {{ transfersPart.label }} &middot; {{ t(transfersPart.titleKey) }}
      <span class="faint tiny" style="font-weight: 400">
        {{ t('settlement.simplifiedSubtitle', {
          count: plural(report.settlement.length, 'transfer'),
        }) }}
      </span>
    </h3>

    <div v-if="!report.settlement.length" class="notice info">
      {{ t('settlement.nobodyOwes') }}
    </div>

    <template v-else>
      <div v-if="remainders.length" class="notice warn" style="margin-bottom: 3mm">
        <strong>
          {{ t('settlement.unscheduledTitle', {
            count: plural(remainders.length, 'net'),
          }) }}
        </strong>
        <p class="tiny" style="margin: 1mm 0 0">
          {{ t('settlement.unscheduledHint', { section: membersNumber }) }}
        </p>
        <ul>
          <li v-for="entry in remainders" :key="entry.member">
            <strong>{{ entry.member }}</strong>
            {{ entry.remainder > 0 ? t('settlement.isOwed') : t('settlement.owes') }}
            {{ amount(Math.abs(entry.remainder), currency) }}
          </li>
        </ul>
      </div>

      <table data-table="settlement">
        <thead>
          <tr>
            <th class="num">#</th>
            <th>{{ t('settlement.pays') }}</th>
            <th></th>
            <th>{{ t('settlement.receives') }}</th>
            <th class="num">{{ t('settlement.amount') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(transfer, index) in report.settlement"
            :key="`${transfer.from}-${transfer.to}-${index}`"
            data-row="transfer"
          >
            <td class="num faint">{{ index + 1 }}</td>
            <td data-cell="from"><strong>{{ transfer.from }}</strong></td>
            <td class="faint">&rarr;</td>
            <td data-cell="to"><strong>{{ transfer.to }}</strong></td>
            <td class="num" data-cell="amount">
              <strong>{{ money(transfer.amount) }}</strong>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="4">{{ t('settlement.totalMoved') }}</td>
            <td class="num" data-fact="settlement-total">{{ money(total) }}</td>
          </tr>
        </tfoot>
      </table>

      <p class="tiny muted" style="margin-top: 2mm">
        {{ t('settlement.pairingHint', { section: membersNumber }) }}
        <template v-if="lendingRef">{{ lendingText.before
          }}<a :href="`#${lendingRef.anchor}`">{{ lendingRef.label }}</a>{{
          lendingText.after }}</template>
      </p>

      <div v-if="showSettlementGraph" style="margin-top: 3mm">
        <h4 style="margin: 0 0 1mm">{{ t('settlement.settlementGraph') }}</h4>
        <p class="tiny muted" style="margin: 0 0 1mm">
          {{ t('settlement.settlementGraphHint') }}
        </p>
        <PrintChart
          :option="settlementGraphOption(report, {
            pays: t('settlement.pays'),
            receives: t('settlement.receives'),
          }, money, PRINT_THEME)"
          size="graph"
          data-chart="settlement-graph"
          :label="t('settlement.settlementGraphAria')"
        />
      </div>
    </template>
  </section>
</template>

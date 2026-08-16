<script setup lang="ts">
/**
 * How to settle: the pool, then the transfers that realise it.
 *
 * One section with two subsections, because they are one argument in two steps and used to
 * be two sections that each half-made it. The pool answers the question the whole report
 * exists for -- "I never borrowed from 甲, why am I paying 甲?" -- and the transfer table is
 * the answer's delivery detail. Split apart, a reader could accept the transfers without
 * ever reading why the counterparty is arbitrary, which is precisely the misreading.
 *
 * The Sankey has a single middle node for that reason: member-to-member flows would draw the
 * re-pairing as though it meant something. Its conservation is a live check on the
 * arithmetic -- in = out -- and it is stated in words rather than left to the picture,
 * because a reader who adds up one column and gets the other has verified this report
 * themselves.
 *
 * What is not here any more is the lending table. It was 5.1, which made the section's first
 * table the one nobody needs to act on, and on a real bill it is 28 rows of pairs. It is now
 * a checking subsection with a reference to it from here, so this section is the two things a
 * reader has to do something about.
 *
 * "As me" is the only real interaction. It highlights table rows and deliberately leaves both
 * diagrams whole -- a filtered graph would look like a smaller bill rather than a focused
 * view of the same one -- and it cannot reach the printed report.
 */
import { computed } from 'vue'
import EChart from './EChart.vue'
import type { Report } from '../../presentation/types'
import { amount, money, plural } from '../../presentation/format'
import {
  CENT,
  netScale,
  poolBalances,
  poolSides,
  settlementGraphData,
  settlementTotal,
  shouldShowSettlementGraph,
  transfersFor,
  unsettled,
} from '../../presentation/report-view-model'
import { sankeyOption, settlementGraphOption } from '../../presentation/chart-options'
import {
  bodySection,
  crossRef,
  sectionHint,
  subsection,
  type ResolvedStructure,
} from '../../presentation/sections'
import { useI18n } from '../../presentation/i18n'

const props = defineProps<{
  report: Report
  structure: ResolvedStructure
  me: string | null
}>()

const emit = defineEmits<{ 'update:me': [member: string | null] }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'settle'))
const hint = computed(() => sectionHint(meta.value, 'screen', t))
const poolPart = computed(() => subsection(props.structure, 'settle', 'pool'))
const transfersPart = computed(() => subsection(props.structure, 'settle', 'transfers'))

/** Where the member table ended up, for the sentences that point back at it. */
const membersNumber = computed(
  () => bodySection(props.structure, 'members')?.number ?? 0,
)
/** Where the lending table ended up, or null if this export has none. */
const lendingRef = computed(() => crossRef(props.structure, 'lending', t))

const sides = computed(() => poolSides(props.report))
const scale = computed(() => netScale(props.report))
const balanced = computed(() => poolBalances(sides.value))

function width(net: number): string {
  return `${Math.max((Math.abs(net) / scale.value) * 100, 0.8)}%`
}

const sankeyChart = computed(() => sankeyOption(props.report, t('pool.node'), money))

const total = computed(() => settlementTotal(props.report))
const remainders = computed(() => unsettled(props.report))

const mine = computed(() => (props.me ? transfersFor(props.report, props.me) : []))
const owedByMe = computed(() =>
  mine.value
    .filter((transfer) => transfer.from === props.me)
    .reduce((sum, transfer) => sum + transfer.amount, 0),
)
const owedToMe = computed(() =>
  mine.value
    .filter((transfer) => transfer.to === props.me)
    .reduce((sum, transfer) => sum + transfer.amount, 0),
)
const myRemainder = computed(() => {
  if (!props.me) return 0
  return remainders.value.find((entry) => entry.member === props.me)?.remainder ?? 0
})

const showSettlementGraph = computed(() =>
  shouldShowSettlementGraph(settlementGraphData(props.report), 'screen'),
)

const settlementChart = computed(() =>
  settlementGraphOption(
    props.report,
    { pays: t('settlement.pays'), receives: t('settlement.receives') },
    money,
  ),
)
</script>

<template>
  <section v-if="meta" :id="meta.id" class="section" data-part="body">
    <header>
      <div>
        <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
        <p class="hint">{{ hint }}</p>
      </div>
      <div class="row">
        <label for="as-me">{{ t('settlement.showAs') }}</label>
        <select
          id="as-me"
          :value="me ?? ''"
          @change="emit('update:me',
                        ($event.target as HTMLSelectElement).value || null)"
        >
          <option value="">{{ t('settlement.everybody') }}</option>
          <option v-for="member in report.members" :key="member" :value="member">
            {{ member }}
          </option>
        </select>
      </div>
    </header>

    <h3 v-if="poolPart" :id="poolPart.id">
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
            <span
              class="fill"
              :style="{ width: width(position.net), background: '#a8342f' }"
            />
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
        <div class="tiny faint" style="margin-top: .3rem">
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
            <span
              class="fill"
              :style="{ width: width(position.net), background: '#1a6b45' }"
            />
          </span>
          <span class="value owed">{{ money(position.net) }}</span>
        </div>
        <p v-if="!sides.creditors.length" class="faint small">
          {{ t('pool.nobodyOverpaid') }}
        </p>
      </div>
    </div>

    <p class="tiny" :class="balanced ? 'muted' : 'owes'" style="margin-top: .7rem">
      {{ t(balanced ? 'pool.balanced' : 'pool.unbalanced', {
        input: amount(sides.in, currency),
        output: amount(sides.out, currency),
      }) }}
    </p>

    <div v-if="sides.debtors.length && sides.creditors.length" style="margin-top: 1rem">
      <h4>{{ t('pool.flowTitle') }}</h4>
      <EChart
        :option="sankeyChart"
        size="tall"
        data-chart="pool-sankey"
        :label="t('pool.flowAria')"
      />
    </div>

    <h3 v-if="transfersPart" :id="transfersPart.id" style="margin-top: 1.6rem">
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
      <div v-if="me" class="notice info" style="margin-bottom: .8rem">
        <strong>{{ me }}:</strong>
        <template v-if="owedByMe > CENT">
          {{ t('settlement.pay', { amount: amount(owedByMe, currency) }) }}
        </template>
        <template v-if="owedByMe > CENT && owedToMe > CENT">
          {{ t('settlement.and') }}
        </template>
        <template v-if="owedToMe > CENT">
          {{ t('settlement.collect', { amount: amount(owedToMe, currency) }) }}
        </template>
        <template v-if="owedByMe <= CENT && owedToMe <= CENT">
          <!-- Two different nothings, and saying the wrong one contradicts the member
               table. -->
          <template v-if="Math.abs(myRemainder) >= CENT">
            {{ t('settlement.nothingSmall', {
              section: membersNumber,
              standing: myRemainder > 0 ? t('settlement.isOwed') : t('settlement.owes'),
              amount: amount(Math.abs(myRemainder), currency),
            }) }}
          </template>
          <template v-else>{{ t('settlement.nothingSquare') }}</template>
        </template>
        <span v-else class="faint">
          {{ t('settlement.mineOfTotal', {
            mine: plural(mine.length, 'transfer'),
            total: plural(report.settlement.length, 'transfer'),
          }) }}
        </span>
      </div>

      <div v-if="remainders.length" class="notice warn" style="margin-bottom: .8rem">
        <strong>
          {{ t('settlement.unscheduledTitle', {
            count: plural(remainders.length, 'net'),
          }) }}
        </strong>
        <p class="tiny" style="margin: .3rem 0 0">
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

      <div class="table-wrap">
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
              :class="{ 'is-me': me !== null &&
                                 (transfer.from === me || transfer.to === me) }"
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
      </div>

      <p class="tiny muted" style="margin-top: .5rem">
        {{ t('settlement.pairingHint', { section: membersNumber }) }}
        <template v-if="lendingRef">
          {{ t('settlement.pairingRef', { ref: lendingRef.label }) }}
        </template>
      </p>

      <div v-if="showSettlementGraph" style="margin-top: .9rem">
        <h4 style="margin: 0 0 .2rem">{{ t('settlement.settlementGraph') }}</h4>
        <p class="tiny muted" style="margin: 0 0 .3rem">
          {{ t('settlement.settlementGraphHint') }}
        </p>
        <EChart
          :option="settlementChart"
          size="tall"
          data-chart="settlement-graph"
          :label="t('settlement.settlementGraphAria')"
        />
      </div>
    </template>
  </section>
</template>

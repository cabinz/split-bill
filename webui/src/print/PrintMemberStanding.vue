<script setup lang="ts">
/**
 * Where each member stands, printed.
 *
 * The same table and the same bullets as the screen, from the same shared list -- these are
 * the definitions the columns mean, and two copies of them would drift. What differs is what
 * follows: on screen a reader can open the records behind a figure, and here the prose names
 * the appendix they are in instead.
 *
 * No records are printed here. They used to be: this section rendered every member's records
 * in full after the charts, which put a 668-row allocation in the middle of the body and
 * pushed the settlement to page 20. They are appendices now, and the body is the part a
 * reader acts on.
 *
 * Nothing is collapsed and nothing is truncated, because there is nothing here to collapse
 * or truncate: one row per member.
 */
import { computed } from 'vue'
import type { Report } from '../presentation/types'
import { amountLabel, money, standing, standingLabel } from '../presentation/format'
import {
  MEMBER_TABLE_NOTES,
  aroundRef,
  bodySection,
  crossRef,
  printId,
  sectionHint,
  type ResolvedStructure,
} from '../presentation/sections'
import { useI18n } from '../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'members'))
const hint = computed(() => sectionHint(meta.value, 'print', t))

const allocationRef = computed(() => crossRef(props.structure, 'allocation', t))
const statementsRef = computed(() => crossRef(props.structure, 'statements', t))
const allocationText = computed(() => aroundRef(t('members.seeAllocation')))
const statementsText = computed(() => aroundRef(t('members.seeStatements')))
</script>

<template>
  <section v-if="meta" :id="printId(meta.id)" class="section" data-part="body">
    <header>
      <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
      <p class="hint">{{ hint }}</p>
    </header>

    <table data-table="positions" class="grouped-columns">
      <colgroup><col /></colgroup>
      <colgroup class="group"><col /><col /></colgroup>
      <colgroup class="group"><col /><col /></colgroup>
      <colgroup class="group"><col /></colgroup>
      <thead>
        <tr>
          <th>{{ t('members.member') }}</th>
          <th class="num">{{ amountLabel(t('members.consumed'), currency) }}</th>
          <th class="num">{{ amountLabel(t('members.paidOut'), currency) }}</th>
          <th class="num">{{ t('members.coveredFor') }}</th>
          <th class="num">{{ t('members.coveredBy') }}</th>
          <th>{{ t('members.outstanding') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="position in report.positions" :key="position.member" data-row="position">
          <td data-cell="member"><strong>{{ position.member }}</strong></td>
          <td class="num" data-cell="consumed">{{ money(position.consumption) }}</td>
          <td class="num" data-cell="paid">{{ money(position.paid) }}</td>
          <td class="num" data-cell="covered-for">{{ money(position.paid_for_others) }}</td>
          <td class="num" data-cell="covered-by">{{ money(position.covered_by_others) }}</td>
          <td
            data-cell="outstanding"
            :class="standing(position.net)"
            class="outstanding"
          >
            {{ standingLabel(standing(position.net)) }}
            <strong v-if="standing(position.net) !== 'square'">
              {{ money(Math.abs(position.net)) }}
            </strong>
          </td>
        </tr>
      </tbody>
    </table>

    <ul class="notes">
      <li v-for="note in MEMBER_TABLE_NOTES" :key="note">{{ t(note) }}</li>
      <li v-if="allocationRef">{{ allocationText.before
        }}<a :href="`#${allocationRef.anchor}`">{{ allocationRef.label }}</a>{{
        allocationText.after }}</li>
      <li v-if="statementsRef">{{ statementsText.before
        }}<a :href="`#${statementsRef.anchor}`">{{ statementsRef.label }}</a>{{
        statementsText.after }}</li>
    </ul>
  </section>
</template>

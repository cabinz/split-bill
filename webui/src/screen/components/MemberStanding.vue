<script setup lang="ts">
/**
 * Where each member stands: one row per person, and what the columns mean.
 *
 * The trust anchor. Everything else in the report follows from two numbers per person --
 * what I consumed and what I paid -- so this is the section that has to be checkable by
 * hand, and the bullets under the table are how: two independent routes to the same
 * outstanding figure, either of which a reader can check against the records.
 *
 * Three things it deliberately no longer does.
 *
 * It has no "net" column. The old table had both a signed net and a standing column
 * repeating its magnitude in words, which is the same number twice; "to receive 120.00" is
 * the net, with the sign spelled out for a reader who does not want to work out what a minus
 * sign in front of a debt means.
 *
 * It has no charts. The two that were here plotted the net by member and consumed-versus-
 * paid-versus-net, and both were a third telling of what this table and the pool already
 * say. The category chart that was also here is now its own section, since it is the one
 * chart that depends on a column the bill might not have.
 *
 * It has no per-member drill-down. Every row used to expand into that member's records
 * inside a `<details>` in a table cell, which put a hundred-odd rows per member into the
 * page and made this table hard to read for the sake of a table that is now a section of its
 * own with a member picker over it.
 */
import { computed } from 'vue'
import type { Report } from '../../presentation/types'
import { amountLabel, money, standing, standingLabel } from '../../presentation/format'
import {
  MEMBER_TABLE_NOTES,
  bodySection,
  crossRef,
  sectionHint,
  type ResolvedStructure,
} from '../../presentation/sections'
import { useI18n } from '../../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure; me: string | null }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'members'))
const hint = computed(() => sectionHint(meta.value, 'screen', t))

/**
 * Where the allocation and the statements ended up in this rendering.
 *
 * Resolved rather than written down: on screen these are numbered subsections and on paper
 * lettered appendices, and an export that leaves the statements out has to leave the
 * sentence pointing at them out too rather than print a reference to nothing.
 */
const allocationRef = computed(() => crossRef(props.structure, 'allocation', t))
const statementsRef = computed(() => crossRef(props.structure, 'statements', t))
</script>

<template>
  <section v-if="meta" :id="meta.id" class="section" data-part="body">
    <header>
      <div>
        <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
        <p class="hint">{{ hint }}</p>
      </div>
    </header>

    <div class="table-wrap">
      <!--
        Four column groups, separated by a rule: who, the two basic figures, the two that
        decompose them, and what is left to do. The rule comes from `colgroup` rather than
        from `nth-child`, so inserting a column cannot silently move the divisions.
      -->
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
          <tr
            v-for="position in report.positions"
            :key="position.member"
            data-row="position"
            :class="{ 'is-me': me === position.member }"
          >
            <td data-cell="member"><strong>{{ position.member }}</strong></td>
            <td class="num" data-cell="consumed">{{ money(position.consumption) }}</td>
            <td class="num" data-cell="paid">{{ money(position.paid) }}</td>
            <td class="num" data-cell="covered-for">
              {{ money(position.paid_for_others) }}
            </td>
            <td class="num" data-cell="covered-by">
              {{ money(position.covered_by_others) }}
            </td>
            <!--
              Direction and amount together, which is what removing the net column costs
              and why it costs nothing. Colour reinforces it; the words carry it, so a
              monochrome print and a screen reader both still say which way it goes.
            -->
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
    </div>

    <ul class="notes">
      <li v-for="note in MEMBER_TABLE_NOTES" :key="note">{{ t(note) }}</li>
      <li v-if="allocationRef">
        {{ t('members.seeAllocation', { ref: allocationRef.label }) }}
      </li>
      <li v-if="statementsRef">
        {{ t('members.seeStatements', { ref: statementsRef.label }) }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
/**
 * What the money went on. A whole section, or nothing at all.
 *
 * The one part of the report that depends on a column the bill might not have, which is why
 * it is a section rather than two charts inside another one: with no category data there is
 * no heading, no standfirst, no nav entry and no chart initialised, and the section after
 * this one takes its number. Nothing is renumbered by hand -- see `presentation/sections`.
 *
 * Two charts, answering two different questions, which is the test for whether a second
 * chart earns its place:
 *
 *   * the pie: what did this trip mostly go on? One number per category, across everybody.
 *   * the stacked bars: whose spending looks different from whose? The same categories,
 *     per member, with each member's total on top.
 *
 * Both are read from `by_category`, which Python produced. The display groups and totals;
 * it does not reinterpret a record or reallocate an amount. The pie includes a slice for
 * whatever nobody categorised, so its slices add up to the total spend on the overview card
 * rather than to some smaller figure the reader has to account for.
 */
import { computed } from 'vue'
import EChart from './EChart.vue'
import type { Report } from '../../presentation/types'
import { amount, money } from '../../presentation/format'
import { UNCATEGORISED, categoryTotals } from '../../presentation/report-view-model'
import { categoryOption, categoryPieOption } from '../../presentation/chart-options'
import {
  bodySection,
  sectionHint,
  subsection,
  type ResolvedStructure,
} from '../../presentation/sections'
import { useI18n } from '../../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'categories'))
const hint = computed(() => sectionHint(meta.value, 'screen', t))
const totalsPart = computed(() =>
  subsection(props.structure, 'categories', 'categoryTotals'),
)
const byMemberPart = computed(() =>
  subsection(props.structure, 'categories', 'categoryByMember'),
)

const totals = computed(() => categoryTotals(props.report))
/** Whether any of the bill went uncategorised, which the caption has to explain. */
const hasUncategorised = computed(() =>
  totals.value.some((entry) => entry.category === UNCATEGORISED),
)

const pieChart = computed(() =>
  categoryPieOption(props.report, t('categories.uncategorised'), money),
)

const barChart = computed(() =>
  categoryOption(
    props.report,
    { uncategorised: t('categories.uncategorised'), total: t('categories.total') },
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
    </header>

    <div v-if="totalsPart">
      <h3 :id="totalsPart.id">{{ totalsPart.label }} &middot; {{ t(totalsPart.titleKey) }}</h3>
      <p class="tiny muted">
        {{ t('categories.totalsHint', {
          amount: amount(report.summary.total_spend, currency),
        }) }}
        <template v-if="hasUncategorised">
          {{ t('categories.uncategorisedHint', { label: t('categories.uncategorised') }) }}
        </template>
      </p>
      <EChart
        :option="pieChart"
        size="tall"
        data-chart="category-pie"
        :label="t('categories.totalsAria')"
      />
    </div>

    <div v-if="byMemberPart" style="margin-top: 1.4rem">
      <h3 :id="byMemberPart.id">
        {{ byMemberPart.label }} &middot; {{ t(byMemberPart.titleKey) }}
      </h3>
      <p class="tiny muted">{{ t('categories.byMemberHint') }}</p>
      <EChart
        :option="barChart"
        data-chart="category-by-member"
        :label="t('categories.byMemberAria')"
      />
    </div>
  </section>
</template>

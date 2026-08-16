<script setup lang="ts">
/**
 * What the money went on, printed.
 *
 * The same two charts as on screen, from the same factories at print type sizes. Which is
 * what makes the requirement that they agree structural: there is one pie and one stacked
 * bar in this codebase, and the printed ones cannot fall behind a change made to the screen's.
 *
 * Both charts have to be readable with nothing to hover. The pie labels each slice with its
 * category, amount and percentage on the chart itself, and the bars carry each member's
 * total above them; the tooltips that add the per-category breakdown on screen simply do not
 * exist here, and no text on this page invites the reader to hover for anything.
 *
 * Absent entirely on a bill with no category data -- no heading, no empty frame -- and the
 * section after it takes its number.
 */
import { computed } from 'vue'
import PrintChart from './PrintChart.vue'
import type { Report } from '../presentation/types'
import { amount, money } from '../presentation/format'
import { UNCATEGORISED, categoryTotals } from '../presentation/report-view-model'
import {
  PRINT_THEME,
  categoryOption,
  categoryPieOption,
} from '../presentation/chart-options'
import {
  bodySection,
  printId,
  sectionHint,
  subsection,
  type ResolvedStructure,
} from '../presentation/sections'
import { useI18n } from '../presentation/i18n'

const props = defineProps<{ report: Report; structure: ResolvedStructure }>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'categories'))
const hint = computed(() => sectionHint(meta.value, 'print', t))
const totalsPart = computed(() =>
  subsection(props.structure, 'categories', 'categoryTotals'),
)
const byMemberPart = computed(() =>
  subsection(props.structure, 'categories', 'categoryByMember'),
)

const hasUncategorised = computed(() =>
  categoryTotals(props.report).some((entry) => entry.category === UNCATEGORISED),
)
</script>

<template>
  <section v-if="meta" :id="printId(meta.id)" class="section" data-part="body">
    <header>
      <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
      <p class="hint">{{ hint }}</p>
    </header>

    <div v-if="totalsPart">
      <h3 :id="printId(totalsPart.id)">
        {{ totalsPart.label }} &middot; {{ t(totalsPart.titleKey) }}
      </h3>
      <p class="tiny muted">
        {{ t('categories.totalsHint', {
          amount: amount(report.summary.total_spend, currency),
        }) }}
        <template v-if="hasUncategorised">
          {{ t('categories.uncategorisedHint', { label: t('categories.uncategorised') }) }}
        </template>
      </p>
      <PrintChart
        :option="categoryPieOption(report, t('categories.uncategorised'), money, PRINT_THEME)"
        size="tall"
        data-chart="category-pie"
        :label="t('categories.totalsAria')"
      />
    </div>

    <div v-if="byMemberPart" style="margin-top: 5mm">
      <h3 :id="printId(byMemberPart.id)">
        {{ byMemberPart.label }} &middot; {{ t(byMemberPart.titleKey) }}
      </h3>
      <p class="tiny muted">{{ t('categories.byMemberHint') }}</p>
      <PrintChart
        :option="categoryOption(report, {
          uncategorised: t('categories.uncategorised'),
          total: t('categories.total'),
        }, money, PRINT_THEME)"
        data-chart="category-by-member"
        :label="t('categories.byMemberAria')"
      />
    </div>
  </section>
</template>

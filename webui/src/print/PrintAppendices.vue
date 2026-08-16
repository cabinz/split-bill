<script setup lang="ts">
/**
 * The appendices: the same bill at full resolution, after the body rather than inside it.
 *
 * These are the four tables the screen puts in its checking section, lettered instead of
 * numbered and each starting a new page. Lettering is not decoration -- it keeps the body's
 * numbering intact whatever the export contains, so "section 3" means the same thing in a
 * two-page summary and in a 27-page full report.
 *
 * The letters come from `resolve()`, from the appendices actually included. Excluding the
 * per-member statements moves the allocation from C to B, and every reference to it in the
 * body follows, because those references are resolved from the same structure rather than
 * written into the prose.
 *
 * Every row is rendered. There is no cap and no class that hides the surplus, because there
 * is no screen to be brief for: the screen's tables are a different component with paging of
 * their own, and neither can affect this one. That was the specific failure the split removed
 * -- on the shared DOM the ledger was rendered in full and hidden with a class, so the
 * completeness of the printed appendix depended on a print stylesheet rule continuing to
 * un-hide it.
 *
 * Plain `<table>`, deliberately, and no `<details>` anywhere. A virtualised table prints only
 * its visible window, and a closed `<details>` prints nothing at all.
 */
import { computed } from 'vue'
import type { Report, Sheet } from '../presentation/types'
import { amount, cell, money, plural } from '../presentation/format'
import {
  consumedBy,
  ledgerByMember,
  ledgerColumns,
  ledgerTotal,
  lendingEdges,
  lendingTotal,
} from '../presentation/report-view-model'
import {
  printId,
  type ResolvedAppendix,
  type ResolvedStructure,
} from '../presentation/sections'
import { useI18n } from '../presentation/i18n'

const props = defineProps<{
  report: Report
  structure: ResolvedStructure
  sheet: Sheet | null
}>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const columns = computed(() => ledgerColumns(props.report))

const edges = computed(() => lendingEdges(props.report))
const edgeTotal = computed(() => lendingTotal(props.report))
const total = computed(() => ledgerTotal(props.report))
const byMember = computed(() => ledgerByMember(props.report))

/** Every member with all of their records. In `positions` order, and a member with none
 *  gets a block saying so -- a missing heading reads as a missing member. */
const statements = computed(() =>
  props.report.positions.map((position) => ({
    member: position.member,
    records: byMember.value.get(position.member) ?? [],
    consumed: consumedBy(props.report, position.member),
  })),
)

/** How many leading columns a per-member footer spans before "total". */
const statementSpan = computed(
  () =>
    2 +
    (columns.value.dates ? 1 : 0) +
    (columns.value.categories ? 1 : 0) +
    (columns.value.items ? 1 : 0),
)

/** Columns before the final share column, for the allocation footer's colspan. */
const ledgerSpan = computed(
  () =>
    4 +
    (columns.value.dates ? 1 : 0) +
    (columns.value.categories ? 1 : 0) +
    (columns.value.items ? 1 : 0) +
    (columns.value.converted ? 1 : 0),
)

/**
 * The heading of one appendix: "Appendix B · Each member's consumption".
 *
 * `appendix.one`, not `appendix.title`: the latter is the plural that names the group of
 * them, and "Appendices A" is not what one of them is called.
 */
function heading(entry: ResolvedAppendix): string {
  return `${t('appendix.one')} ${entry.letter} · ${t(entry.titleKey)}`
}
</script>

<template>
  <template v-for="entry in structure.appendices" :key="entry.id">
    <section
      :id="printId(entry.id)"
      class="section appendix"
      data-part="appendix"
      :data-appendix="entry.id"
    >
      <header>
        <h2>{{ heading(entry) }}</h2>
      </header>

      <!-- A · who really fronted money for whom -->
      <template v-if="entry.id === 'lending'">
        <p class="tiny muted">
          {{ t('settlement.realHint') }}
          <template v-if="edges.length > report.settlement.length">
            {{ t('settlement.directHint', {
              edges: edges.length,
              settlements: report.settlement.length,
            }) }}
          </template>
        </p>
        <!-- Three columns, matching the screen's table cell for cell. The arrow column the
             printed table used to have said what "fronted by" and "for" already say, and made
             the two views' rows differ by a cell that carries no figure. -->
        <table class="compact" data-table="lending-edges">
          <thead>
            <tr>
              <th>{{ t('settlement.frontedBy') }}</th>
              <th>{{ t('settlement.for') }}</th>
              <th class="num">{{ t('settlement.amount') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="edge in edges"
              :key="`${edge.creditor}-${edge.debtor}`"
              data-row="edge"
            >
              <td data-cell="creditor">{{ edge.creditor }}</td>
              <td data-cell="debtor">{{ edge.debtor }}</td>
              <td class="num" data-cell="amount">{{ money(edge.amount) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="2">{{ t('settlement.totalLent') }}</td>
              <td class="num" data-fact="lending-total">{{ money(edgeTotal) }}</td>
            </tr>
          </tfoot>
        </table>
        <!-- Follows the table it explains, rather than staying in the body where the reader
             cannot see the total it is about. -->
        <p class="tiny muted" style="margin-top: 2mm">{{ t('settlement.lentHint') }}</p>
      </template>

      <!-- B · one table per member -->
      <template v-else-if="entry.id === 'statements'">
        <p class="tiny muted">{{ t('appendix.statementsHint') }}</p>
        <div
          v-for="statement in statements"
          :key="statement.member"
          class="member-detail"
          :data-member="statement.member"
        >
          <h4>
            {{ t('members.records', { member: statement.member }) }}
            <span class="faint">({{ statement.records.length }})</span>
          </h4>

          <p v-if="!statement.records.length" class="tiny muted">
            {{ t('members.noRecords') }}
          </p>

          <table v-else class="compact" data-table="member-records">
            <thead>
              <tr>
                <th class="num">{{ t('appendix.record') }}</th>
                <th v-if="columns.dates">{{ t('appendix.date') }}</th>
                <th v-if="columns.categories">{{ t('appendix.category') }}</th>
                <th v-if="columns.items">{{ t('appendix.item') }}</th>
                <th>{{ t('members.paidBy') }}</th>
                <th class="num">{{ t('members.recordTotal') }}</th>
                <th class="num">{{ t('members.myShare') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="record in statement.records"
                :key="`${record.record_id}-${record.member}`"
                data-row="member-record"
              >
                <td class="num faint" data-cell="record">{{ record.record_id }}</td>
                <td v-if="columns.dates" class="small" data-cell="date">
                  {{ record.date ?? '' }}
                </td>
                <td v-if="columns.categories" class="small" data-cell="category">
                  {{ record.category ?? '' }}
                </td>
                <td v-if="columns.items" class="small" data-cell="item">
                  {{ record.item ?? '' }}
                </td>
                <td class="small" data-cell="creditor">{{ record.creditor }}</td>
                <td class="num faint" data-cell="total">{{ money(record.amount_std) }}</td>
                <td class="num" data-cell="share">{{ money(record.share) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td :colspan="statementSpan">
                  {{ t('members.sharesAdd', {
                    amount: amount(statement.consumed, currency),
                  }) }}
                </td>
                <td class="num faint">{{ t('members.total') }}</td>
                <td class="num">{{ money(statement.consumed) }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </template>

      <!-- C · every share -->
      <template v-else-if="entry.id === 'allocation'">
        <p class="tiny muted">{{ t('appendix.allocationHint') }}</p>
        <table class="compact" data-table="ledger">
          <thead>
            <tr>
              <th class="num">{{ t('appendix.record') }}</th>
              <th v-if="columns.dates">{{ t('appendix.date') }}</th>
              <th v-if="columns.categories">{{ t('appendix.category') }}</th>
              <th v-if="columns.items">{{ t('appendix.item') }}</th>
              <th>{{ t('appendix.paidBy') }}</th>
              <th>{{ t('appendix.shareOf') }}</th>
              <th v-if="columns.converted" class="num">{{ t('appendix.asWritten') }}</th>
              <th class="num">{{ t('appendix.recordTotal') }}</th>
              <th class="num">{{ t('appendix.share') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in report.ledger"
              :key="`${row.record_id}-${row.member}-${index}`"
              data-row="ledger"
            >
              <td class="num faint" data-cell="record">{{ row.record_id }}</td>
              <td v-if="columns.dates" class="small" data-cell="date">
                {{ row.date ?? '' }}
              </td>
              <td v-if="columns.categories" class="small" data-cell="category">
                {{ row.category ?? '' }}
              </td>
              <td v-if="columns.items" class="small" data-cell="item">
                {{ row.item ?? '' }}
              </td>
              <td class="small" data-cell="creditor">{{ row.creditor }}</td>
              <td class="small" data-cell="member">{{ row.member }}</td>
              <td v-if="columns.converted" class="num faint small" data-cell="as-written">
                <template v-if="row.currency_raw">
                  {{ money(row.amount_raw) }} {{ row.currency_raw }}
                </template>
              </td>
              <td class="num faint" data-cell="total">{{ money(row.amount_std) }}</td>
              <td class="num" data-cell="share">{{ money(row.share) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td :colspan="ledgerSpan">
                {{ t('appendix.sharesAcross', {
                  shares: plural(report.ledger.length, 'share'),
                  records: report.summary.record_count,
                }) }}
              </td>
              <td class="num" data-fact="ledger-total">{{ money(total) }}</td>
            </tr>
          </tfoot>
        </table>
        <p class="tiny muted">
          {{ t('appendix.sharesTotal', { amount: amount(total, currency) }) }}
        </p>
      </template>

      <!-- D · the sheet as imported, including columns this tool never reads -->
      <template v-else-if="entry.id === 'sheet'">
        <p class="tiny muted">{{ t('appendix.sheetHint') }}</p>
        <table v-if="sheet" class="compact" data-table="sheet">
          <thead>
            <tr>
              <th class="num">#</th>
              <th v-for="column in sheet.columns" :key="column">{{ column }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in sheet.rows" :key="index" data-row="sheet">
              <td class="num faint" data-cell="row">{{ index + 1 }}</td>
              <td
                v-for="(value, column) in row"
                :key="column"
                :data-cell="`column-${column}`"
              >{{ cell(value) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td :colspan="1 + sheet.columns.length">
                {{ t('appendix.records', { count: sheet.total_rows }) }}
              </td>
            </tr>
          </tfoot>
        </table>
      </template>
    </section>
  </template>

  <p class="tiny faint print-colophon">
    {{ t('appendix.generated', {
      file: report.meta.source_file,
      schema: report.schema_version,
    }) }}
  </p>
</template>

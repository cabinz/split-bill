<script setup lang="ts">
/**
 * The bill at full resolution: four tables, none of them new information.
 *
 * Everything above this section is a group-by of what is here, and the section exists so
 * that any figure can be traced to the records it came from. Which is also why the four
 * tables are progressively disclosed rather than all laid out: they run to 668 rows on the
 * real bill, and a reader who wants to check one figure should not have to scroll past all of
 * them to reach the end of the report.
 *
 * What is open by default is a judgement about what a reader needs rather than about length:
 *
 *   * **the lending pairs** are expanded, because they are the explanation for why the
 *     settlement pairs people who never lent to each other. Somebody who reads the transfer
 *     table and stops has the report's one genuinely surprising claim unexplained.
 *   * **one member's records** are not collapsed at all, but only one member is shown. The
 *     old table rendered every member's records at once, which was seven blocks of a hundred
 *     rows to see one of them.
 *   * **the allocation** and **the sheet** are collapsed. They are audit tables: complete,
 *     long, and not part of anybody's reading path.
 *
 * Each has its own switch. A single "show everything" would make the shortest table's
 * disclosure cost the same as the longest's.
 *
 * None of it reaches the printed report. The print view has its own components and its own
 * frozen input; a member selected here, a filter typed here and a page turned here are all
 * invisible to it. Which appendices get printed is asked in the export dialog instead --
 * where the answer is "all members or none", because paper has no picker to change.
 */
import { computed, ref, watch } from 'vue'
import DataTable, { type Column } from './DataTable.vue'
import type { LedgerEntry, LendingEdge, Report, Sheet } from '../../presentation/types'
import { amount, cell, money, plural } from '../../presentation/format'
import {
  consumedBy,
  ledgerColumns,
  ledgerTotal,
  lendingEdges,
  lendingTotal,
  recordsFor,
  sheetRowCount,
} from '../../presentation/report-view-model'
import {
  bodySection,
  sectionHint,
  subsection,
  type ResolvedStructure,
} from '../../presentation/sections'
import { useI18n } from '../../presentation/i18n'

const props = defineProps<{
  report: Report
  structure: ResolvedStructure
  sheet: Sheet | null
}>()

const currency = computed(() => props.report.meta.std_currency)
const { t } = useI18n()

const meta = computed(() => bodySection(props.structure, 'details'))
const hint = computed(() => sectionHint(meta.value, 'screen', t))
const lendingPart = computed(() => subsection(props.structure, 'details', 'lending'))
const statementsPart = computed(() => subsection(props.structure, 'details', 'statements'))
const allocationPart = computed(() => subsection(props.structure, 'details', 'allocation'))
const sheetPart = computed(() => subsection(props.structure, 'details', 'sheet'))

const columns = computed(() => ledgerColumns(props.report))

/* ---------------- the lending pairs ---------------- */

const edges = computed(() => lendingEdges(props.report))
const edgeTotal = computed(() => lendingTotal(props.report))

const edgeColumns = computed<Column<LendingEdge>[]>(() => [
  {
    id: 'creditor',
    header: t('settlement.frontedBy'),
    value: (edge) => edge.creditor,
    filterable: true,
  },
  {
    id: 'debtor',
    header: t('settlement.for'),
    value: (edge) => edge.debtor,
    filterable: true,
  },
  {
    id: 'amount',
    header: t('settlement.amount'),
    value: (edge) => edge.amount,
    text: (edge) => money(edge.amount),
    numeric: true,
  },
])

/* ---------------- one member's records ---------------- */

/**
 * Whose records are shown.
 *
 * Named for what it does -- pick whose consumption to check -- and deliberately separate from
 * "show as" in the settlement section, which focuses the transfers concerning one person.
 * The two are not linked: they answer different questions, and quietly moving one when the
 * other changes would mean neither could be trusted to stay where it was put.
 */
const checking = ref<string>(props.report.members[0] ?? '')

watch(
  () => props.report,
  () => {
    if (!props.report.members.includes(checking.value)) {
      checking.value = props.report.members[0] ?? ''
    }
  },
)

const myRecords = computed(() =>
  checking.value ? recordsFor(props.report, checking.value) : [],
)
const myConsumption = computed(() =>
  checking.value ? consumedBy(props.report, checking.value) : 0,
)

const recordColumns = computed<Column<LedgerEntry>[]>(() => {
  const list: Column<LedgerEntry>[] = [
    {
      id: 'record',
      header: t('appendix.record'),
      value: (entry) => entry.record_id,
      numeric: true,
      faint: true,
    },
  ]
  if (columns.value.dates) {
    list.push({ id: 'date', header: t('appendix.date'), value: (entry) => entry.date })
  }
  if (columns.value.categories) {
    list.push({
      id: 'category',
      header: t('appendix.category'),
      value: (entry) => entry.category,
      filterable: true,
    })
  }
  if (columns.value.items) {
    list.push({ id: 'item', header: t('appendix.item'), value: (entry) => entry.item })
  }
  list.push(
    {
      id: 'creditor',
      header: t('members.paidBy'),
      value: (entry) => entry.creditor,
      filterable: true,
    },
    {
      id: 'total',
      header: t('members.recordTotal'),
      value: (entry) => entry.amount_std,
      text: (entry) => money(entry.amount_std),
      numeric: true,
      faint: true,
    },
    {
      id: 'share',
      header: t('members.myShare'),
      value: (entry) => entry.share,
      text: (entry) => money(entry.share),
      numeric: true,
    },
  )
  return list
})

/* ---------------- the allocation ---------------- */

const total = computed(() => ledgerTotal(props.report))

const ledgerColumnDefs = computed<Column<LedgerEntry>[]>(() => {
  const list: Column<LedgerEntry>[] = [
    {
      id: 'record',
      header: t('appendix.record'),
      value: (entry) => entry.record_id,
      numeric: true,
      faint: true,
    },
  ]
  if (columns.value.dates) {
    list.push({ id: 'date', header: t('appendix.date'), value: (entry) => entry.date })
  }
  if (columns.value.categories) {
    list.push({
      id: 'category',
      header: t('appendix.category'),
      value: (entry) => entry.category,
      filterable: true,
    })
  }
  if (columns.value.items) {
    list.push({ id: 'item', header: t('appendix.item'), value: (entry) => entry.item })
  }
  list.push(
    {
      id: 'creditor',
      header: t('appendix.paidBy'),
      value: (entry) => entry.creditor,
      filterable: true,
    },
    {
      id: 'member',
      header: t('appendix.shareOf'),
      value: (entry) => entry.member,
      filterable: true,
    },
  )
  if (columns.value.converted) {
    list.push({
      id: 'as-written',
      header: t('appendix.asWritten'),
      value: (entry) => entry.amount_raw,
      text: (entry) =>
        entry.currency_raw ? `${money(entry.amount_raw)} ${entry.currency_raw}` : '',
      numeric: true,
      faint: true,
    })
  }
  list.push(
    {
      id: 'total',
      header: t('appendix.recordTotal'),
      value: (entry) => entry.amount_std,
      text: (entry) => money(entry.amount_std),
      numeric: true,
      faint: true,
    },
    {
      id: 'share',
      header: t('appendix.share'),
      value: (entry) => entry.share,
      text: (entry) => money(entry.share),
      numeric: true,
    },
  )
  return list
})

/* ---------------- the sheet as imported ---------------- */

/**
 * The sheet's rows are arrays, because a spreadsheet may have duplicate or blank column
 * names and keying by them would drop cells. So the columns are built by position, with the
 * source row number first.
 */
type SheetRow = { index: number; cells: (string | number | boolean | null)[] }

const sheetRows = computed<SheetRow[]>(() =>
  (props.sheet?.rows ?? []).map((cells, index) => ({ index: index + 1, cells })),
)

const sheetColumns = computed<Column<SheetRow>[]>(() => [
  { id: 'row', header: '#', value: (row) => row.index, numeric: true, faint: true },
  ...(props.sheet?.columns ?? []).map((column, position) => ({
    id: `column-${position}`,
    header: column,
    value: (row: SheetRow) => {
      const value = row.cells[position]
      return typeof value === 'number' ? value : cell(value ?? null)
    },
    text: (row: SheetRow) => cell(row.cells[position] ?? null),
  })),
])

const sheetCount = computed(() => sheetRowCount(props.sheet))
</script>

<template>
  <section v-if="meta" :id="meta.id" class="section" data-part="checking">
    <header>
      <div>
        <h2>{{ meta.number }} &middot; {{ t(meta.titleKey) }}</h2>
        <p class="hint">{{ hint }}</p>
      </div>
    </header>

    <!--
      Expanded by default: this is the report's explanation for why the settlement pairs
      people who never lent to each other, and a reader who never opens it has that claim
      unexplained.
    -->
    <details v-if="lendingPart" :id="lendingPart.id" class="fold" open>
      <summary>
        <span class="fold-title">
          {{ lendingPart.label }} &middot; {{ t(lendingPart.titleKey) }}
        </span>
        <span class="faint tiny">{{ t('details.rowCount', { count: edges.length }) }}</span>
      </summary>
      <div class="fold-body">
        <p class="tiny muted">
          {{ t('settlement.realHint') }}
          <template v-if="edges.length > report.settlement.length">
            {{ t('settlement.directHint', {
              edges: edges.length,
              settlements: report.settlement.length,
            }) }}
          </template>
        </p>
        <DataTable
          :rows="edges"
          :columns="edgeColumns"
          name="lending-edges"
          row-name="edge"
          compact
          :label="t('settlement.realTitle')"
        >
          <template #foot>
            <tr>
              <td colspan="2">{{ t('settlement.totalLent') }}</td>
              <td class="num" data-fact="lending-total">{{ money(edgeTotal) }}</td>
            </tr>
          </template>
        </DataTable>
        <p class="tiny muted">{{ t('settlement.lentHint') }}</p>
      </div>
    </details>

    <!--
      Not collapsible, and only ever one member. A fold over a picker would be two things to
      operate to see one table; the picker is already the disclosure.
    -->
    <div v-if="statementsPart" :id="statementsPart.id" class="subsection">
      <div class="subsection-head">
        <h3>{{ statementsPart.label }} &middot; {{ t(statementsPart.titleKey) }}</h3>
        <label class="row" style="gap: .4rem">
          <span>{{ t('details.whichMember') }}</span>
          <select
            id="checking-member"
            :value="checking"
            @change="checking = ($event.target as HTMLSelectElement).value"
          >
            <option v-for="member in report.members" :key="member" :value="member">
              {{ member }}
            </option>
          </select>
        </label>
      </div>
      <p class="tiny muted">{{ t('details.statementsHint') }}</p>
      <DataTable
        :rows="myRecords"
        :columns="recordColumns"
        name="member-records"
        row-name="member-record"
        compact
        :label="t('details.statementsTitle')"
      >
        <!-- Not a `data-fact`: this is the selected member's total, and which member is
             selected is screen state. The printed statements appendix has one of these per
             member, so a shared fact name would be comparing one figure against seven. -->
        <template #foot>
          <tr>
            <td :colspan="recordColumns.length - 1">{{ t('members.total') }}</td>
            <td class="num" data-cell="statement-total">{{ money(myConsumption) }}</td>
          </tr>
        </template>
      </DataTable>
      <p class="tiny muted">
        {{ t('details.statementTotal', {
          count: myRecords.length,
          amount: amount(myConsumption, currency),
          member: checking,
        }) }}
      </p>
    </div>

    <details v-if="allocationPart" :id="allocationPart.id" class="fold">
      <summary>
        <span class="fold-title">
          {{ allocationPart.label }} &middot; {{ t(allocationPart.titleKey) }}
        </span>
        <span class="faint tiny">
          {{ t('details.rowCount', { count: report.ledger.length }) }}
        </span>
      </summary>
      <div class="fold-body">
        <p class="tiny muted">{{ t('appendix.allocationHint') }}</p>
        <DataTable
          :rows="report.ledger"
          :columns="ledgerColumnDefs"
          name="ledger"
          row-name="ledger"
          compact
          :label="t('appendix.allocation')"
        >
          <template #foot>
            <tr>
              <td :colspan="ledgerColumnDefs.length - 1">
                {{ t('appendix.sharesAcross', {
                  shares: plural(report.ledger.length, 'share'),
                  records: report.summary.record_count,
                }) }}
              </td>
              <td class="num" data-fact="ledger-total">{{ money(total) }}</td>
            </tr>
          </template>
        </DataTable>
        <p class="tiny muted">
          {{ t('appendix.sharesTotal', { amount: amount(total, currency) }) }}
        </p>
      </div>
    </details>

    <details v-if="sheetPart && sheet" :id="sheetPart.id" class="fold">
      <summary>
        <span class="fold-title">
          {{ sheetPart.label }} &middot; {{ t(sheetPart.titleKey) }}
        </span>
        <span class="faint tiny">{{ t('details.rowCount', { count: sheetCount }) }}</span>
      </summary>
      <div class="fold-body">
        <p class="tiny muted">{{ t('appendix.sheetHint') }}</p>
        <DataTable
          :rows="sheetRows"
          :columns="sheetColumns"
          name="sheet"
          row-name="sheet"
          compact
          :label="t('appendix.sheet')"
        />
      </div>
    </details>

    <p class="tiny faint" style="margin-top: 1rem">
      {{ t('appendix.generated', {
        file: report.meta.source_file,
        schema: report.schema_version,
      }) }}
    </p>
  </section>
</template>

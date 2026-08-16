<script setup lang="ts" generic="Row">
/**
 * One interactive table, for every long table on the page.
 *
 * The screen has four of them -- the lending pairs, one member's records, the allocation,
 * the sheet as imported -- and they used to differ in how much of themselves they showed
 * and how you saw the rest: 12 rows with a checkbox here, 60 rows with a button there, and
 * "show all" meaning a 668-row DOM either way. Paging, sorting, searching and filtering are
 * written once here, and a business table supplies only columns and rows.
 *
 * TanStack does the row model: filtering, sorting, pagination and the state that drives
 * them. What is written here is the parts a library cannot supply -- the markup, and the
 * fact that every one of these tables is a *screen* affordance. None of it can reach the
 * printed report: the print view has its own components, renders every row of a plain
 * `<table>`, and receives a frozen copy of the report rather than this table's state. So
 * sorting the allocation on screen cannot reorder the printed appendix, and page 2 is not
 * what comes out of the printer.
 *
 * Not virtualised, and that is a rule rather than a preference for these four tables (§5.2):
 * a virtual window renders only the rows near the scroll position, and the appendix's job is
 * to contain all of them. Paging keeps the DOM small without ever making "all the rows" a
 * thing the component cannot produce.
 */
import { computed, ref, watch } from 'vue'
import {
  FlexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useVueTable,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
} from '@tanstack/vue-table'
import { useI18n } from '../../presentation/i18n'

/**
 * What a business table has to say about one column.
 *
 * Deliberately smaller than TanStack's own column definition. A caller says what the value
 * *is* -- which is what sorting, searching and filtering all work from -- and, if the
 * display differs from the value, what it should look like. Handing callers the full
 * definition would let one of them define a cell as markup whose text nothing can search.
 */
export interface Column<Row> {
  /** Stable key, used for filter state and as the `data-cell` marker. */
  id: string
  /** Column heading. */
  header: string
  /** The value: what is sorted, searched and filtered. */
  value: (row: Row) => string | number | null
  /** What to show, when it differs from the value -- a formatted amount, say. */
  text?: (row: Row) => string
  /** Right-aligned tabular figures. */
  numeric?: boolean
  /** Offer a dropdown of this column's distinct values. For a column with a small
   *  discrete domain: a member, a payer, a category. Never for an amount. */
  filterable?: boolean
  /** A quieter cell, for ids and secondary figures. */
  faint?: boolean
  /** Extra class on the cell. */
  cellClass?: string
}

const props = withDefaults(
  defineProps<{
    rows: Row[]
    columns: Column<Row>[]
    /** `data-table` on the table, for the fact-reading tests. */
    name: string
    /** `data-row` on each body row. */
    rowName?: string
    /** Rows per page, initially. */
    pageSize?: number
    /** Compact type, for the long audit tables. */
    compact?: boolean
    /** An accessible name for the table. */
    label?: string
  }>(),
  { rowName: 'row', pageSize: 10, compact: false, label: '' },
)

const { t } = useI18n()

const PAGE_SIZES = [10, 25, 50, 100]

const sorting = ref<SortingState>([])
const columnFilters = ref<ColumnFiltersState>([])
const globalFilter = ref('')
const pagination = ref({ pageIndex: 0, pageSize: props.pageSize })

/** A row's value for one column, as TanStack's accessor. */
const columnDefs = computed<ColumnDef<Row, unknown>[]>(() =>
  props.columns.map((column) => ({
    id: column.id,
    header: column.header,
    accessorFn: (row: Row) => column.value(row) ?? '',
    enableColumnFilter: column.filterable === true,
    // `includesString` lower-cases both sides and stringifies numbers, which is what a
    // search box should do to "1,108.00" and to a member's name alike.
    filterFn: 'includesString',
  })),
)

const table = useVueTable({
  get data() {
    return props.rows
  },
  get columns() {
    return columnDefs.value
  },
  state: {
    get sorting() {
      return sorting.value
    },
    get columnFilters() {
      return columnFilters.value
    },
    get globalFilter() {
      return globalFilter.value
    },
    get pagination() {
      return pagination.value
    },
  },
  onSortingChange: (updater) => {
    sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater
  },
  onColumnFiltersChange: (updater) => {
    columnFilters.value =
      typeof updater === 'function' ? updater(columnFilters.value) : updater
  },
  onGlobalFilterChange: (updater) => {
    globalFilter.value =
      typeof updater === 'function' ? updater(globalFilter.value) : updater
  },
  onPaginationChange: (updater) => {
    pagination.value = typeof updater === 'function' ? updater(pagination.value) : updater
  },
  globalFilterFn: 'includesString',
  getCoreRowModel: getCoreRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
})

/**
 * Back to page 1 whenever the rows themselves change.
 *
 * The member picker swaps 130 rows for 96, and without this a reader on page 4 of one
 * member's records lands on an empty page 4 of the next one's -- which reads as "this member
 * has no records".
 */
watch(
  () => props.rows,
  () => {
    pagination.value = { ...pagination.value, pageIndex: 0 }
    globalFilter.value = ''
    columnFilters.value = []
    sorting.value = []
  },
)

/** Filtering or searching can leave the current page past the end. */
watch(
  () => table.getFilteredRowModel().rows.length,
  () => {
    const pages = table.getPageCount()
    if (pages > 0 && pagination.value.pageIndex >= pages) {
      pagination.value = { ...pagination.value, pageIndex: pages - 1 }
    }
  },
)

const byId = computed(() => new Map(props.columns.map((column) => [column.id, column])))

/** The distinct values of one filterable column, sorted, for its dropdown. */
function choicesFor(column: Column<Row>): string[] {
  const seen = new Set<string>()
  for (const row of props.rows) {
    const value = column.value(row)
    if (value !== null && value !== '') seen.add(String(value))
  }
  return [...seen].sort((a, b) => a.localeCompare(b))
}

const filterable = computed(() => props.columns.filter((column) => column.filterable))

const shown = computed(() => table.getRowModel().rows.length)
const matched = computed(() => table.getFilteredRowModel().rows.length)
const total = computed(() => props.rows.length)

/** The 1-based range on screen, for "26–50 of 668". */
const range = computed(() => {
  if (!shown.value) return null
  const first = pagination.value.pageIndex * pagination.value.pageSize + 1
  return { first, last: first + shown.value - 1 }
})

const pageCount = computed(() => Math.max(table.getPageCount(), 1))
const filtered = computed(() => matched.value !== total.value)

function cellText(column: Column<Row>, row: Row): string {
  if (column.text) return column.text(row)
  const value = column.value(row)
  return value === null ? '' : String(value)
}

/** `aria-sort` for a header, which is how a screen reader is told the order. */
function ariaSort(direction: false | 'asc' | 'desc'): 'ascending' | 'descending' | 'none' {
  if (direction === 'asc') return 'ascending'
  if (direction === 'desc') return 'descending'
  return 'none'
}

function filterValue(id: string): string {
  const found = columnFilters.value.find((entry) => entry.id === id)
  return typeof found?.value === 'string' ? found.value : ''
}

function setFilter(id: string, value: string) {
  const rest = columnFilters.value.filter((entry) => entry.id !== id)
  columnFilters.value = value ? [...rest, { id, value }] : rest
}

const dirty = computed(
  () => Boolean(globalFilter.value) || columnFilters.value.length > 0,
)

function clearFilters() {
  globalFilter.value = ''
  columnFilters.value = []
}
</script>

<template>
  <div class="data-table" :data-table-name="name" :data-total-rows="total">
    <div class="data-table-controls">
      <label class="data-table-search">
        <span>{{ t('table.search') }}</span>
        <input
          :value="globalFilter"
          type="search"
          :placeholder="t('table.searchPlaceholder')"
          @input="globalFilter = ($event.target as HTMLInputElement).value"
        />
      </label>

      <label v-for="column in filterable" :key="column.id" class="data-table-filter">
        <span>{{ column.header }}</span>
        <select
          :value="filterValue(column.id)"
          @change="setFilter(column.id, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('table.allOf', { column: column.header }) }}</option>
          <option v-for="choice in choicesFor(column)" :key="choice" :value="choice">
            {{ choice }}
          </option>
        </select>
      </label>

      <button v-if="dirty" type="button" class="data-table-clear" @click="clearFilters">
        {{ t('table.clear') }}
      </button>

      <p class="data-table-count tiny muted">
        <template v-if="range">
          {{ t('table.range', { first: range.first, last: range.last, total }) }}
          <template v-if="filtered">
            &middot; {{ t('table.filteredFrom', { shown: matched, total }) }}
          </template>
        </template>
        <template v-else>{{ t('table.rangeEmpty', { total }) }}</template>
      </p>
    </div>

    <div class="table-wrap">
      <table
        :class="{ compact }"
        :data-table="name"
        :aria-label="label || undefined"
      >
        <thead>
          <tr>
            <th
              v-for="header in table.getHeaderGroups()[0]?.headers ?? []"
              :key="header.id"
              :class="{ num: byId.get(header.column.id)?.numeric }"
              :aria-sort="ariaSort(header.column.getIsSorted())"
            >
              <button
                type="button"
                class="data-table-sort"
                :aria-label="t('table.sortBy', { column: byId.get(header.column.id)?.header ?? '' })"
                @click="header.column.toggleSorting(undefined, false)"
              >
                <FlexRender
                  :render="header.column.columnDef.header"
                  :props="header.getContext()"
                />
                <span class="data-table-sort-mark" aria-hidden="true">{{
                  header.column.getIsSorted() === 'asc'
                    ? '▲'
                    : header.column.getIsSorted() === 'desc'
                      ? '▼'
                      : '⇅'
                }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in table.getRowModel().rows" :key="row.id" :data-row="rowName">
            <td
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-cell="cell.column.id"
              :class="[
                byId.get(cell.column.id)?.cellClass,
                {
                  num: byId.get(cell.column.id)?.numeric,
                  faint: byId.get(cell.column.id)?.faint,
                },
              ]"
            >{{ cellText(byId.get(cell.column.id)!, row.original) }}</td>
          </tr>
          <tr v-if="!shown">
            <td :colspan="columns.length" class="data-table-empty muted">
              {{ t('table.empty') }}
            </td>
          </tr>
        </tbody>
        <tfoot v-if="$slots.foot">
          <slot name="foot" />
        </tfoot>
      </table>
    </div>

    <div v-if="pageCount > 1 || total > PAGE_SIZES[0]!" class="data-table-pager">
      <div class="row">
        <button
          type="button"
          :disabled="!table.getCanPreviousPage()"
          :aria-label="t('table.first')"
          @click="table.setPageIndex(0)"
        >&laquo;</button>
        <button
          type="button"
          :disabled="!table.getCanPreviousPage()"
          :aria-label="t('table.previous')"
          @click="table.previousPage()"
        >&lsaquo;</button>
        <span class="tiny muted" aria-live="polite">
          {{ t('table.pageOf', { page: pagination.pageIndex + 1, pages: pageCount }) }}
        </span>
        <button
          type="button"
          :disabled="!table.getCanNextPage()"
          :aria-label="t('table.next')"
          @click="table.nextPage()"
        >&rsaquo;</button>
        <button
          type="button"
          :disabled="!table.getCanNextPage()"
          :aria-label="t('table.last')"
          @click="table.setPageIndex(pageCount - 1)"
        >&raquo;</button>
      </div>

      <label class="data-table-size">
        <span>{{ t('table.perPage') }}</span>
        <select
          :value="pagination.pageSize"
          @change="table.setPageSize(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="size in PAGE_SIZES" :key="size" :value="size">{{ size }}</option>
        </select>
      </label>
    </div>
  </div>
</template>

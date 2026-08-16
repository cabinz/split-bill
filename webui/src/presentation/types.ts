/**
 * The report.json contract, as TypeScript.
 *
 * Plan §5. This is a transcription of what Python produces, not a second opinion
 * about it: `splitbill/report.py` owns the shape, and the schema is versioned
 * because reports get archived. If the two ever disagree, Python is right.
 *
 * `std_currency` being nullable is the case worth keeping in mind while reading the
 * rest. A bill with no currency column and no standard currency specified -- which
 * is what the real bill in this repo looks like -- settles perfectly well, and
 * every amount in it is unitless. Every display path has to cope: no currency
 * label, no conversion column in the appendix. There is nothing to convert and
 * inventing a unit would be a lie about the data.
 */

export const SCHEMA_VERSION = '2.0'

export interface ColumnBinding {
  /** The column this role is bound to, or null when the sheet has none. */
  name: string | null
  /** True only when auto-detection found it. A guess the user may override; a
   *  column they named is not up for discussion. */
  auto: boolean
}

export type ColumnRole =
  | 'creditor'
  | 'debtor'
  | 'amount'
  | 'currency'
  | 'date'
  | 'category'
  | 'item'

export interface ExchangeRate {
  base: string
  quote: string
  rate: number
}

export interface ReportMeta {
  generated_at: string
  source_file: string
  /** null in currency-agnostic mode. See the note at the top of this file. */
  std_currency: string | null
  exchange_rates: ExchangeRate[]
  columns: Partial<Record<ColumnRole, ColumnBinding>>
  warnings: string[]
}

export interface Summary {
  total_spend: number
  record_count: number
  member_count: number
  transaction_count: number
}

/**
 * Where one member stands.
 *
 * `net` is carried twice over on purpose: `paid - consumption` and
 * `paid_for_others - covered_by_others` are the same number, and the second is the
 * one that persuades. "You covered this much for other people, they covered this
 * much for you, the difference is yours to settle" is checkable against the
 * records and points straight at the payment.
 */
export interface Position {
  member: string
  consumption: number
  paid: number
  paid_for_others: number
  covered_by_others: number
  /** Positive means owed money. */
  net: number
  /** Consumption by category. Empty when the sheet had no category column, in
   *  which case the breakdown is simply not shown. */
  by_category: Record<string, number>
}

/**
 * A payment the settlement asks for.
 *
 * `from`/`to`, never creditor/debtor. The counterparty here is a by-product of
 * re-pairing nets to minimise transfers and usually reflects no debt between these
 * two people. Lending vocabulary would assert one, and that misreading -- "I never
 * borrowed from 甲, why am I paying them?" -- is the confusion this report exists
 * to remove.
 */
export interface Transfer {
  from: string
  to: string
  amount: number
}

/** A real obligation, before simplification: `debtor` owes `creditor`. */
export interface LendingEdge {
  creditor: string
  debtor: string
  amount: number
}

/** One member's share of one record. Every summary above is a group-by of these. */
export interface LedgerEntry {
  record_id: number
  date: string | null
  category: string | null
  item: string | null
  creditor: string
  member: string
  share: number
  amount_raw: number
  currency_raw: string | null
  amount_std: number
}

export interface Report {
  schema_version: string
  meta: ReportMeta
  members: string[]
  summary: Summary
  /** Net descending, the same order as the settlement table. */
  positions: Position[]
  settlement: Transfer[]
  /** The real lending relationships, before simplification. Shown beside the
   *  settlement, the two explain each other. */
  lending_edges: LendingEdge[]
  ledger: LedgerEntry[]
}

/**
 * The sheet as read.
 *
 * Rows are arrays rather than objects because a spreadsheet may have duplicate or
 * blank column names, and keying by them would drop cells. `total_rows` is the real
 * count even when `rows` has been truncated for a preview.
 */
export interface Sheet {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  total_rows: number
  truncated: boolean
}

export interface Finding {
  row: number | null
  column: string | null
  message: string
}

export interface Findings {
  /** No report can be produced until these are fixed. */
  errors: Finding[]
  /** A report can be produced and something in it is worth a second look. */
  warnings: Finding[]
}

/** `POST /api/parse`: what was found, before anything was computed. */
export interface ParseResponse {
  ok: boolean
  token: string
  source_file: string
  std_currency: string | null
  exchange_rates: ExchangeRate[]
  columns: Partial<Record<ColumnRole, ColumnBinding>>
  sheet: Sheet
  findings: Findings
  /** Names produced by the current separator, shown before report analysis. */
  members: string[]
  /** One converted total per source row; null when that row cannot be converted. */
  base_amounts: (number | null)[]
}

/** `POST /api/preview` has the same inspectable shape as the initial parse. */
export type PreviewResponse = ParseResponse

/** `POST /api/report`: the report, with the sheet alongside for the appendix. */
export interface ReportResponse {
  token: string
  report: Report
  sheet: Sheet
}

/** A 4xx from either endpoint. `findings` is present when the bill is the problem. */
export interface ApiError {
  error: string
  findings?: Findings
  columns?: Partial<Record<ColumnRole, ColumnBinding>>
  sheet?: Sheet
  members?: string[]
  base_amounts?: (number | null)[]
}

/** What the user can change and ask for a new report with. */
export interface ReportOptions {
  columns: Partial<Record<ColumnRole, string | null>>
  separator: string
  all_selector: string
  std_currency: string | null
  exchange_rates: ExchangeRate[]
}

export const SETTLEMENT_ROLES: ColumnRole[] = [
  'creditor',
  'debtor',
  'amount',
  'currency',
]

export const DESCRIPTIVE_ROLES: ColumnRole[] = ['date', 'category', 'item']

/** Roles shown as editable mappings during import. Category is optional, but a
 * wrong guess changes the report's category chart and therefore needs the same
 * visible override as the settlement columns. */
export const SELECTABLE_ROLES: ColumnRole[] = [
  ...SETTLEMENT_ROLES,
  'category',
]

export const ROLE_LABELS: Record<ColumnRole, string> = {
  creditor: 'Who paid',
  debtor: 'Who shared',
  amount: 'Amount',
  currency: 'Currency',
  date: 'Date',
  category: 'Category',
  item: 'Item',
}

export const ROLE_HELP: Record<ColumnRole, string> = {
  creditor: 'The member who fronted the whole record.',
  debtor: 'Everyone who shared it, separated by the separator below.',
  amount: 'The record total, before any conversion.',
  currency: 'Optional. Without it every amount is taken at face value.',
  date: 'Optional. Shown in the appendix and the per-member detail.',
  category: 'Optional. Drives the spending-by-category breakdown.',
  item: 'Optional. What the record was for.',
}

/**
 * Turning figures into text.
 *
 * Every number here arrived from Python already rounded to the cent -- layer 1
 * allocates whole cents, deliberately, so that a column of shares adds up to the
 * total above it (plan §9.1). So this module formats and never rounds. If a figure
 * looks like it needs rounding on this side, something upstream is wrong and hiding
 * it here would make it unfindable.
 *
 * `std_currency` may be null, which is the currency-agnostic mode and the real
 * bill's actual state. Amounts then carry no unit at all rather than a guessed one.
 */
import { locale, t } from './i18n'

function numberLocale(): string {
  return locale.value === 'zh-CN' ? 'zh-CN' : 'en-US'
}

/** Thousand separators, two decimals, no unit. */
export function money(value: number): string {
  return value.toLocaleString(numberLocale(), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** A signed amount, for nets, where the sign is the whole point. */
export function signedMoney(value: number): string {
  // -0.00 is a real possibility out of a float sum and reads as though somebody is
  // owed a negative nothing.
  const cleaned = Object.is(value, -0) ? 0 : value
  const sign = cleaned > 0 ? '+' : cleaned < 0 ? '-' : ''
  return `${sign}${money(Math.abs(cleaned))}`
}

/** An amount with its unit, or without one when the bill has no currency. */
export function amount(value: number, currency: string | null): string {
  return currency ? `${money(value)} ${currency}` : money(value)
}

export function signedAmount(value: number, currency: string | null): string {
  return currency ? `${signedMoney(value)} ${currency}` : signedMoney(value)
}

/** "Amount (HKD)" or "Amount", matching what the CLI and the CSVs write. */
export function amountLabel(base: string, currency: string | null): string {
  return currency ? `${base} (${currency})` : base
}

export function integer(value: number): string {
  return value.toLocaleString(numberLocale())
}

/**
 * A share of something, as a percentage to one decimal.
 *
 * One decimal everywhere, so the category chart and the pie state a proportion the same
 * way. Rounded shares can add up to 99.9% or 100.1%, and they are left that way
 * deliberately: nudging one to make the column reach 100 would mean printing a figure that
 * is not the one the amounts give.
 */
export function percent(fraction: number): string {
  if (!Number.isFinite(fraction)) return ''
  return `${(fraction * 100).toLocaleString(numberLocale(), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`
}

/** A cell from the raw sheet, as text. Blank for null rather than "null". */
export function cell(value: string | number | boolean | null): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') {
    return Number.isInteger(value) ? integer(value) : money(value)
  }
  if (typeof value === 'boolean') return value ? t('cell.yes') : t('cell.no')
  return value
}

/** An ISO timestamp as something readable, falling back to the raw string. */
export function timestamp(iso: string): string {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleString(numberLocale(), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "6 transactions", "1 transaction". */
export function plural(count: number, singular: string, suffix = 's'): string {
  if (locale.value === 'zh-CN') {
    const nouns: Record<string, string> = {
      transfer: '笔转账',
      record: '条记录',
      rate: '条汇率',
      share: '份分摊',
      pair: '对关系',
      net: '个净额',
      row: '行',
    }
    return `${integer(count)} ${nouns[singular] ?? singular}`
  }
  return `${integer(count)} ${singular}${count === 1 ? '' : suffix}`
}

/**
 * A tooltip formatter for ECharts, which hands over a much wider type than a number.
 *
 * `valueFormatter` is declared as taking `OptionDataValue | OptionDataValue[]` --
 * every axis type shares one signature, so a category axis can pass a string and a
 * multi-dimensional series an array. Ours are always single numbers, but asserting
 * that at each call site would be four casts that all have to stay true. This narrows
 * once, honestly, and every chart uses it.
 */
export function chartValue(currency: string | null) {
  const unit = currency ? ` ${currency}` : ''
  return (value: unknown): string => {
    const first = Array.isArray(value) ? value[0] : value
    return typeof first === 'number' && Number.isFinite(first)
      ? money(first) + unit
      : ''
  }
}

/** An axis label formatter, which ECharts types the same loose way. */
export function axisValue(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? money(value) : ''
}

/** Owed money, owes money, or square. Drives colour and wording throughout. */
export type Standing = 'owed' | 'owes' | 'square'

/**
 * A cent, which is the resolution every figure here has.
 *
 * Below it there is nothing to say: a net of 0.004 is a net of zero as far as any
 * display is concerned, and calling somebody a creditor over it would be noise. The
 * same threshold as `report-view-model.ts`, which is where the solver's own
 * don't-bother-transferring rule is written down; stated separately here so this module
 * stays free of report-shaped imports.
 */
const CENT = 0.005

export function standing(net: number): Standing {
  if (net > CENT) return 'owed'
  if (net < -CENT) return 'owes'
  return 'square'
}

export function standingLabel(value: Standing): string {
  return t({
    owed: 'members.receive',
    owes: 'members.pay',
    square: 'members.settled',
  }[value])
}

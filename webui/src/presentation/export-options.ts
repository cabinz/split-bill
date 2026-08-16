/**
 * What the print view is given, and how it is frozen.
 *
 * A `PrintInput` is the whole of the print view's world: a report, the sheet behind it,
 * what the user asked to include, and the language to say it in. It contains no screen
 * state -- no filter, no expanded row, no current member, no scroll position -- and the
 * print view has no other input, which is how §5.1's rule is enforced rather than
 * remembered. If the printed report should differ, an option has to be added here and
 * appear in the dialog; the print view cannot reach sideways for it.
 *
 * `freeze` deep-copies. Vue's reactive objects hand out proxies onto live state, so a
 * print view holding one would re-render mid-print if the user touched a control while
 * the print dialog was open -- and on Chromium the dialog does not block the page's
 * JavaScript. A copy is a snapshot in the ordinary sense: what the report said when the
 * button was pressed.
 */
import { toRaw } from 'vue'
import type { Locale } from './i18n'
import type { Report, Sheet } from './types'

/**
 * The choices the export dialog offers.
 *
 * Two, and they nest: `appendix` is the master switch over every appendix, `statements`
 * picks one of them. The nesting is why this is an object of named flags rather than a list
 * of included ids -- the dialog has to be able to disable the child when the parent is off,
 * and a list would make "off because the parent is off" indistinguishable from "off because
 * the user said so".
 */
export interface ExportOptions {
  /**
   * Whether the appendices are printed at all.
   *
   * On by default: §2.2 asks for it, and a report that cannot be checked against its own
   * records is what V2 exists to stop producing. Optional because on the real bill it is
   * 20 of 27 pages, and somebody who wants the summary on one side of paper should not
   * have to print all of it to get it.
   *
   * It excludes the appendices and nothing else. The body is always complete.
   */
  appendix: boolean
  /**
   * Whether every member gets their own consumption statement.
   *
   * Off by default, and the reason is that it says nothing new: it is the allocation
   * appendix grouped by member instead of by record, at seven tables and a hundred-odd rows
   * each on the real bill. Worth having when the report is being handed to seven people who
   * each want their own page; not worth 12 pages by default.
   *
   * Deliberately not the screen's member picker. The screen shows one member at a time
   * because it can be changed; paper cannot, so this prints all of them or none. §5.2's
   * rule: a screen selection may not leak into a print.
   */
  statements: boolean
}

export function defaultExportOptions(): ExportOptions {
  return { appendix: true, statements: false }
}

/** Everything the print view renders from. */
export interface PrintInput {
  report: Report
  /** The sheet as imported, for the sheet appendix. Null if the service sent none. */
  sheet: Sheet | null
  options: ExportOptions
  /** The language at the moment of freezing, so a locale change mid-print cannot
   *  produce a half-translated document. */
  locale: Locale
  /** When it was frozen, in ms. Only for telling one snapshot from another. */
  frozenAt: number
}

/**
 * Take a snapshot.
 *
 * `structuredClone` rather than a JSON round trip: it copies `Map`, `Date` and `undefined`
 * correctly, and it throws on something genuinely uncopyable instead of silently dropping
 * it. The report contract is plain JSON today, so this is insurance against a later field
 * that is not -- the failure mode being guarded is a snapshot that is quietly shallow.
 *
 * `toRaw` first, and it is not optional. Vue hands out a `Proxy` for anything reactive, and
 * `structuredClone` refuses to clone a proxy outright: "could not be cloned", thrown from a
 * watcher, which is how this was found -- the print view simply never mounted. Unwrapping
 * once is enough, because a reactive proxy wraps a plain object whose own properties are
 * plain too; the proxying happens lazily as they are read.
 *
 * It also has to happen here rather than at the call sites. There are three of them and they
 * are all in the print path, so a forgotten `toRaw` would break printing and nothing else --
 * the worst place to leave a trap.
 */
export function freeze(
  report: Report,
  sheet: Sheet | null,
  options: ExportOptions,
  locale: Locale,
): PrintInput {
  return {
    report: structuredClone(toRaw(report)),
    sheet: sheet ? structuredClone(toRaw(sheet)) : null,
    options: { ...toRaw(options) },
    locale,
    frozenAt: Date.now(),
  }
}

/**
 * Driving the print view from the screen view.
 *
 * The screen holds the report; this decides what the print view is given and when the print
 * dialog opens. It is the only path between the two, and it passes a frozen `PrintInput` and
 * nothing else -- no component reference, no DOM node, no store.
 *
 * The one design decision worth explaining is why the print view is mounted all the time
 * rather than on demand.
 *
 * Ctrl-P is not ours. The browser prints whatever is in the document, and it does not call
 * our code first. If the print root only existed after somebody clicked "Print", then a
 * reader who reached for the keyboard shortcut -- which is how most people print anything --
 * would get a blank sheet, because the print stylesheet hides the screen view. So the print
 * view stays mounted, off-screen, from the moment there is a report.
 *
 * That does not weaken the freezing rule. `syncLive` re-freezes from the current report and
 * export options whenever either changes, so what is mounted is always a snapshot -- taken
 * at a defined moment, deep-copied, and never a live view of screen state. `printNow`
 * re-freezes once more so that what goes to the printer is a snapshot taken at the click,
 * and `whenPrintReady` makes sure it has actually rendered before the dialog blocks.
 */
import { ref, shallowRef } from 'vue'
import type { ExportOptions, PrintInput } from '../presentation/export-options'
import { freeze } from '../presentation/export-options'
import type { Report, Sheet } from '../presentation/types'
import { locale } from '../presentation/i18n'
import { PREVIEW_URL, serveInput } from './channel'
import { whenPrintReady } from './ready'

/** What the mounted print view is currently rendering. Null before a report exists. */
export const printInput = shallowRef<PrintInput | null>(null)

/** Set when a preview window could not be opened, so the dialog can say so. */
export const previewBlocked = ref(false)

/**
 * Keep the mounted print view in step with the report on screen.
 *
 * Called whenever the report, the sheet or the export options change. Freezes rather than
 * assigning, so the print view holds a copy and cannot observe a later mutation of the
 * report object.
 */
export function syncLive(
  report: Report | null,
  sheet: Sheet | null,
  options: ExportOptions,
): void {
  printInput.value = report ? freeze(report, sheet, options, locale.value) : null
}

/**
 * Print, having made sure what will be printed has finished rendering.
 *
 * `window.print()` is synchronous and composes the page as it stands, so everything has to
 * be settled first -- there is no adjusting anything afterwards. `whenPrintReady` waits for
 * Vue, the fonts and every chart's own `finished` event, which is a real signal rather than
 * the pair of animation frames this replaces.
 */
export async function printNow(
  report: Report,
  sheet: Sheet | null,
  options: ExportOptions,
): Promise<void> {
  printInput.value = freeze(report, sheet, options, locale.value)
  await whenPrintReady()
  window.print()
}

/**
 * Open the preview in a new window.
 *
 * `window.open` has to happen in the click handler's own synchronous run, or every browser
 * treats it as an unrequested pop-up and blocks it -- which is why this takes the report
 * rather than being async up front. The input is frozen first and served on request; see
 * `channel.ts` for the handshake and why the child asks rather than the parent pushing.
 *
 * Returns false when the window was blocked, so the dialog can say what happened instead of
 * appearing to do nothing.
 */
export function openPreview(
  report: Report,
  sheet: Sheet | null,
  options: ExportOptions,
): boolean {
  const input = freeze(report, sheet, options, locale.value)
  const child = window.open(PREVIEW_URL, '_blank')
  if (!child) {
    previewBlocked.value = true
    return false
  }
  previewBlocked.value = false

  const stop = serveInput(child, input)
  // The listener would otherwise outlive the window it was for. Long enough that a slow
  // machine still completes the handshake; the child's own timeout is shorter.
  setTimeout(stop, 60000)
  return true
}

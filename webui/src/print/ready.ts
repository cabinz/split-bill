/**
 * When the printed report is actually finished rendering.
 *
 * `window.print()` blocks and composes the page as it stands, so there is no adjusting
 * anything afterwards -- whatever is on the page at that instant is what comes out of the
 * printer. The old code waited two animation frames and hoped, which is the kind of thing
 * that works on a developer's machine and produces a chart-less first page on somebody
 * else's under load.
 *
 * So the signal is explicit. Three things have to have happened:
 *
 *   1. Vue has patched the DOM -- every table row, every section, actually present.
 *   2. The fonts are loaded. A chart laid out in a fallback font and printed in the real
 *      one has labels that no longer fit the space measured for them.
 *   3. Every chart has told ECharts' `finished` event that it has drawn.
 *
 * Charts register themselves as they mount, so nothing has to know in advance how many
 * there are -- which matters because the count depends on the bill: no category column,
 * no category chart; nobody overpaid, no Sankey.
 *
 * `document.documentElement.dataset.printReady` is set when all of it is done. Playwright
 * waits on that attribute rather than on a timeout, and so does `page.pdf()` in the
 * screenshot script, which is the same guarantee for the automated PDF that the manual
 * print gets.
 */
import { nextTick } from 'vue'

export const READY_ATTRIBUTE = 'printReady'

/** Charts that have registered but not yet finished drawing. */
let pending = new Set<Promise<void>>()

/**
 * A chart's promise to finish.
 *
 * Called during `onMounted`, which is inside the same tick as the render that created it,
 * so `whenPrintReady` sees every chart of a given render before it starts waiting.
 */
export function registerChart(drawn: Promise<void>): void {
  pending.add(drawn)
  // Removed on settle so a re-render's charts are the only ones waited on. Failures are
  // swallowed here and surfaced by the timeout in `PrintChart`, because a chart that
  // never draws must not hang printing forever.
  void drawn.catch(() => {}).finally(() => pending.delete(drawn))
}

/** Forget any outstanding registrations. Called when a fresh input is mounted. */
export function resetReady(): void {
  pending = new Set()
  if (typeof document !== 'undefined') {
    delete document.documentElement.dataset[READY_ATTRIBUTE]
  }
}

/** Fonts, if the browser will say. Resolves either way rather than blocking print. */
async function fontsReady(): Promise<void> {
  if (typeof document === 'undefined' || !document.fonts) return
  try {
    await document.fonts.ready
  } catch {
    // Safari has been known to reject this. A print in a fallback font is a worse
    // document than one in the right font, and a print that never happens is worse
    // than both.
  }
}

/**
 * Resolve once the print DOM is drawn and measured.
 *
 * Two `nextTick`s rather than one: the first flushes the render that mounted the print
 * root, and the second flushes any child that a `v-if` inside it only then evaluated --
 * the appendix sections are conditional on the export options. After that, `pending`
 * holds every chart that will exist for this input.
 */
export async function whenPrintReady(): Promise<void> {
  await nextTick()
  await nextTick()
  await fontsReady()
  // Snapshot: a chart finishing removes itself from `pending` while this awaits.
  await Promise.allSettled([...pending])
  // One more frame, so the SVG the chart just wrote is in the layout the printer sees.
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  if (typeof document !== 'undefined') {
    document.documentElement.dataset[READY_ATTRIBUTE] = 'true'
  }
}

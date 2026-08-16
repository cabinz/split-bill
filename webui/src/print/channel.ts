/**
 * Handing a frozen report to the preview window.
 *
 * The preview is a second window on the same origin, and the report has to get there
 * somehow. It is not re-fetched: the upload token would let it be, but the report the user
 * asked to preview is the one in front of them, and re-running the pipeline to obtain a
 * second copy of it introduces a way for the preview to differ from the page it was opened
 * from. So the input travels as a message.
 *
 * The protocol is a two-line handshake, and the ordering is the point:
 *
 *     child                        parent
 *       |  ---- READY ---------->    |     "I am mounted, send it"
 *       |  <--- INPUT -----------    |     the frozen PrintInput
 *
 * The child asks first. The alternative -- parent posts as soon as it has opened the window
 * -- races the child's own script loading, and a message posted before there is a listener
 * is simply lost. There is no retry loop here because there is no need for one.
 *
 * Security. This is a bill: who paid for what, with names. It is not posted to `'*'`, ever.
 *
 *   * the parent sends to its own origin explicitly, so a navigated-away child cannot
 *     receive it;
 *   * the parent checks the message came from the window it opened, so another tab on the
 *     same origin cannot ask for a copy;
 *   * the child checks the message came from its opener and from this origin;
 *   * both check the message shape before trusting any field, because `event.data` is
 *     attacker-controlled in the general case.
 *
 * A message that fails any check is dropped in silence. There is nothing useful to tell the
 * user about it and nothing safe to do with it.
 */
import type { PrintInput } from '../presentation/export-options'

/** The query that makes `main.ts` mount the preview instead of the app. */
export const PREVIEW_VIEW = 'print-preview'
export const PREVIEW_URL = `?view=${PREVIEW_VIEW}`

const READY = 'splitbill:preview-ready'
const INPUT = 'splitbill:print-input'

interface ReadyMessage {
  type: typeof READY
}

interface InputMessage {
  type: typeof INPUT
  input: PrintInput
}

/** Whether this document was opened as a print preview. */
export function isPreviewWindow(search = window.location.search): boolean {
  return new URLSearchParams(search).get('view') === PREVIEW_VIEW
}

function sameOrigin(event: MessageEvent): boolean {
  return event.origin === window.location.origin
}

/**
 * Parent side: wait for the child to ask, then send it the input once.
 *
 * Returns a function that stops listening, which the caller uses when the child never
 * arrives -- a pop-up blocker, or a user who closed it.
 */
export function serveInput(child: Window, input: PrintInput): () => void {
  const origin = window.location.origin

  function onMessage(event: MessageEvent) {
    if (!sameOrigin(event)) return
    // Only the window this call opened. Another tab on the same origin asking for a copy
    // of somebody's bill gets nothing.
    if (event.source !== child) return
    const data = event.data as Partial<ReadyMessage> | null
    if (data?.type !== READY) return
    // The explicit origin, never '*': if the child has navigated elsewhere by now, the
    // browser refuses to deliver rather than handing the bill to whatever is there.
    child.postMessage({ type: INPUT, input } satisfies InputMessage, origin)
  }

  window.addEventListener('message', onMessage)
  return () => window.removeEventListener('message', onMessage)
}

/**
 * Child side: announce readiness and resolve with the input when it arrives.
 *
 * Resolves with null when there is no opener -- a preview URL that was bookmarked,
 * refreshed after the parent closed, or opened directly. §5.1 is explicit that this URL is
 * a transient entry point rather than a shareable link, so the honest answer is to say
 * there is nothing to show rather than to invent a way to recover a report.
 */
export function requestInput(timeoutMs = 10000): Promise<PrintInput | null> {
  const opener = window.opener as Window | null
  if (!opener) return Promise.resolve(null)

  return new Promise((resolve) => {
    let settled = false

    function finish(input: PrintInput | null) {
      if (settled) return
      settled = true
      window.removeEventListener('message', onMessage)
      clearTimeout(timer)
      resolve(input)
    }

    function onMessage(event: MessageEvent) {
      if (!sameOrigin(event)) return
      if (event.source !== opener) return
      const data = event.data as Partial<InputMessage> | null
      if (data?.type !== INPUT || !data.input) return
      finish(data.input)
    }

    const timer = setTimeout(() => finish(null), timeoutMs)
    window.addEventListener('message', onMessage)
    opener.postMessage({ type: READY } satisfies ReadyMessage, window.location.origin)
  })
}

/**
 * Talking to the local Python service.
 *
 * Three calls, matching the import workflow. `parse` uploads a bill and gets back
 * what detection found; `preview` validates current options and returns the members
 * and converted row totals without running settlement; `report` performs the full
 * analysis only after confirmation. Changing one dropdown never re-uploads the file.
 *
 * No arithmetic happens on this side. Not "very little" -- none. Every figure the
 * page shows came off the wire, which is what makes it impossible for the browser
 * and the terminal to disagree about what somebody owes.
 */

import type {
  ApiError,
  ParseResponse,
  PreviewResponse,
  ReportOptions,
  ReportResponse,
} from './presentation/types'

/** A 4xx or 5xx, carrying whatever the service could say about the bill. */
export class ApiFailure extends Error {
  readonly status: number
  readonly detail: ApiError

  constructor(status: number, detail: ApiError) {
    super(detail.error || `request failed with ${status}`)
    this.name = 'ApiFailure'
    this.status = status
    this.detail = detail
  }

  /** Whether the bill is the problem, as opposed to the request or the service. */
  get isBillProblem(): boolean {
    return this.status === 422 || Boolean(this.detail.findings?.errors?.length)
  }
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  let payload: unknown
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    throw new ApiFailure(response.status, {
      error:
        response.ok
          ? 'the service sent something that is not JSON'
          : `${response.status} ${response.statusText}`,
    })
  }
  if (!response.ok) {
    throw new ApiFailure(response.status, payload as ApiError)
  }
  return payload as T
}

/**
 * Upload a bill. Returns detected columns, a preview and any findings.
 *
 * The body is the file itself with its name in a header, not multipart: the service
 * has no multipart parser (`cgi` was removed in Python 3.13) and `fetch` sends a
 * `File` as a body directly. `encodeURIComponent` because a header cannot carry the
 * non-ASCII bytes of a CJK filename.
 */
export async function parseBill(
  file: File,
  options?: Partial<Pick<ReportOptions, 'std_currency' | 'exchange_rates'>>,
): Promise<ParseResponse> {
  const query = new URLSearchParams()
  if (options?.std_currency) {
    query.set('standard_currency', options.std_currency)
  }
  for (const rate of options?.exchange_rates ?? []) {
    query.append('exchange_rate', `${rate.base}/${rate.quote}=${rate.rate}`)
  }
  const suffix = query.toString() ? `?${query}` : ''

  const response = await fetch(`/api/parse${suffix}`, {
    method: 'POST',
    headers: { 'X-Filename': encodeURIComponent(file.name) },
    body: file,
  })
  return readJson<ParseResponse>(response)
}

function optionsBody(token: string, options: ReportOptions): string {
  return JSON.stringify({
    token,
    // Nulls are meaningful. For settlement roles they retain the historical
    // "detect" behaviour; for optional descriptive roles they mean "do not use".
    columns: options.columns,
    separator: options.separator,
    all_selector: options.all_selector,
    std_currency: options.std_currency,
    exchange_rates: options.exchange_rates,
  })
}

/** Validate and interpret import settings without running settlement analysis. */
export async function fetchPreview(
  token: string,
  options: ReportOptions,
  signal?: AbortSignal,
): Promise<PreviewResponse> {
  const response = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: optionsBody(token, options),
  })
  return readJson<PreviewResponse>(response)
}

/** Ask for the report, with whatever the user has corrected. */
export async function fetchReport(
  token: string,
  options: ReportOptions,
  signal?: AbortSignal,
): Promise<ReportResponse> {
  const response = await fetch('/api/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: optionsBody(token, options),
  })
  return readJson<ReportResponse>(response)
}

/** Whether the service is up, for telling "not running" from "broken". */
export async function health(): Promise<boolean> {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) return false
    const payload = (await response.json()) as { service?: string }
    return payload.service === 'splitbill'
  } catch {
    return false
  }
}

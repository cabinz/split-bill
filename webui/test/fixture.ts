/**
 * A small report, made by hand, for testing the presentation layer.
 *
 * Not generated from Python: these tests are about what the display does with a report,
 * so the report has to be a fixed thing they can make assertions against. But it is
 * internally consistent in every way a real one is -- the nets sum to zero, each member's
 * shares sum to their consumption, the shares sum to the total spend, each member's
 * `paid` is the total of the records they fronted. A selector tested against an
 * impossible report proves nothing about a real one.
 *
 * Four members and three records, arranged so that three awkward cases are all present:
 *
 *   * **amy and bob** have nets of ±100.01 which a 100.00 transfer only mostly clears.
 *     The 0.01 left over is above the cent, so `unsettled` has to name them -- otherwise
 *     section 3 says "to pay 100.01" and section 5 says "you are square", and a reader
 *     who spots both has been handed a contradiction to resolve alone.
 *   * **cho and dee** have nets of ±0.004, below the cent. No transfer is scheduled and
 *     none should be mentioned: the display agrees with the solver that this is nothing.
 *     They are also the members who appear in no chart, having no side of the pool.
 *   * **record 2** is in another currency, so `converted` is true, and **record 3** has
 *     no category, so `hasCategories` is true without being true of everybody.
 */
import type { Report, Sheet } from '../src/presentation/types'

export function makeReport(): Report {
  return {
    schema_version: '2.0',
    meta: {
      generated_at: '2026-05-01T10:00:00+00:00',
      source_file: 'trip.csv',
      std_currency: 'HKD',
      exchange_rates: [{ base: 'KRW', quote: 'HKD', rate: 0.0057715 }],
      columns: {},
      warnings: [],
    },
    members: ['amy', 'bob', 'cho', 'dee'],
    summary: {
      total_spend: 300.014,
      record_count: 3,
      member_count: 4,
      transaction_count: 1,
    },
    // Net descending, which is the order the service sends and the report displays.
    positions: [
      {
        member: 'amy',
        consumption: 100,
        paid: 200.01,
        paid_for_others: 100.01,
        covered_by_others: 0,
        net: 100.01,
        by_category: { food: 60, transport: 40 },
      },
      {
        member: 'cho',
        consumption: 100,
        paid: 100.004,
        paid_for_others: 0.004,
        covered_by_others: 0,
        net: 0.004,
        by_category: {},
      },
      {
        member: 'dee',
        consumption: 0.004,
        paid: 0,
        paid_for_others: 0,
        covered_by_others: 0.004,
        net: -0.004,
        by_category: {},
      },
      {
        member: 'bob',
        consumption: 100.01,
        paid: 0,
        paid_for_others: 0,
        covered_by_others: 100.01,
        net: -100.01,
        by_category: { food: 60, transport: 40.01 },
      },
    ],
    // One transfer for a net of 100.01: the solver moves whole cents, so 0.01 is left on
    // both sides and has to be reported rather than quietly dropped.
    settlement: [{ from: 'bob', to: 'amy', amount: 100 }],
    lending_edges: [
      { creditor: 'amy', debtor: 'bob', amount: 100.01 },
      { creditor: 'cho', debtor: 'dee', amount: 0.004 },
    ],
    ledger: [
      {
        record_id: 1,
        date: '2026-04-01',
        category: 'food',
        item: 'dinner',
        creditor: 'amy',
        member: 'amy',
        share: 60,
        amount_raw: 120,
        currency_raw: 'HKD',
        amount_std: 120,
      },
      {
        record_id: 1,
        date: '2026-04-01',
        category: 'food',
        item: 'dinner',
        creditor: 'amy',
        member: 'bob',
        share: 60,
        amount_raw: 120,
        currency_raw: 'HKD',
        amount_std: 120,
      },
      {
        record_id: 2,
        date: '2026-04-02',
        category: 'transport',
        item: 'taxi',
        creditor: 'amy',
        member: 'amy',
        share: 40,
        amount_raw: 13868,
        currency_raw: 'KRW',
        amount_std: 80.01,
      },
      {
        record_id: 2,
        date: '2026-04-02',
        category: 'transport',
        item: 'taxi',
        creditor: 'amy',
        member: 'bob',
        share: 40.01,
        amount_raw: 13868,
        currency_raw: 'KRW',
        amount_std: 80.01,
      },
      {
        record_id: 3,
        date: null,
        category: null,
        item: null,
        creditor: 'cho',
        member: 'cho',
        share: 100,
        amount_raw: 100.004,
        currency_raw: 'HKD',
        amount_std: 100.004,
      },
      {
        record_id: 3,
        date: null,
        category: null,
        item: null,
        creditor: 'cho',
        member: 'dee',
        share: 0.004,
        amount_raw: 100.004,
        currency_raw: 'HKD',
        amount_std: 100.004,
      },
    ],
  }
}

export function makeSheet(): Sheet {
  return {
    columns: ['date', 'item', 'amount', 'payer', 'shared with'],
    rows: [
      ['2026-04-01', 'dinner', 120, 'amy', 'amy,bob'],
      ['2026-04-02', 'taxi', 13868, 'amy', 'amy,bob'],
      [null, null, 100.004, 'cho', 'cho,dee'],
    ],
    total_rows: 3,
    truncated: false,
  }
}

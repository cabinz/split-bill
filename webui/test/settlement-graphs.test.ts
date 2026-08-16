/**
 * The settlement graph, and the properties that keep it honest.
 *
 * This graph is a second reading of the settlement table, and the failure it invites is
 * subtle: a picture that looks authoritative and disagrees with the table printed above
 * it. So the assertions here are less about geometry than about correspondence -- one
 * arrow per row, the same direction, the same amount, and nobody on both sides.
 *
 * There is no graph of `lending_edges` to test. A real bill has close to one lending
 * pair per ordered pair of members -- 28 for the seven-member fixture in this
 * repository -- and no arrangement of 28 labelled arrows is readable. That stays a
 * table, and this file's job is partly to record that decision.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  GRAPH_LIMITS,
  settlementGraphData,
  shouldShowSettlementGraph,
} from '../src/presentation/report-view-model'
import type { Report, Transfer } from '../src/presentation/types'
import { makeReport } from './fixture'

/** A report with just the members and the settlement these functions read. */
function graphReport(members: string[], settlement: Transfer[]): Report {
  return { ...makeReport(), members, settlement }
}

const pay = (from: string, to: string, amount: number): Transfer =>
  ({ from, to, amount })

describe('the settlement graph', () => {
  it('draws one link per transfer, from payer to receiver', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('bob', 'amy', 30),
        pay('cho', 'amy', 20),
      ]),
    )!
    assert.deepEqual(data.links, [
      { from: 'bob', to: 'amy', amount: 30 },
      { from: 'cho', to: 'amy', amount: 20 },
    ])
  })

  it('keeps the links in the settlement’s own order, matching the table', () => {
    const transfers = [pay('cho', 'amy', 20), pay('bob', 'amy', 30)]
    const data = settlementGraphData(graphReport(['amy', 'bob', 'cho'], transfers))!
    assert.deepEqual(
      data.links.map((link) => link.from),
      transfers.map((transfer) => transfer.from),
    )
  })

  it('puts every member on exactly one side', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('bob', 'amy', 30),
        pay('cho', 'amy', 20),
      ]),
    )!
    assert.deepEqual(data.payers.map((node) => node.member), ['bob', 'cho'])
    assert.deepEqual(data.receivers.map((node) => node.member), ['amy'])
    const payers = new Set(data.payers.map((node) => node.member))
    assert.equal(data.receivers.some((node) => payers.has(node.member)), false)
  })

  it('totals a member who is in several transfers', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('bob', 'amy', 30),
        pay('bob', 'cho', 20),
      ]),
    )!
    assert.equal(data.payers[0]!.member, 'bob')
    assert.equal(data.payers[0]!.total, 50)
  })

  it('orders each side by what that member moves, largest first', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho', 'dee'], [
        pay('bob', 'amy', 10),
        pay('cho', 'amy', 90),
        pay('dee', 'amy', 50),
      ]),
    )!
    assert.deepEqual(
      data.payers.map((node) => node.member),
      ['cho', 'dee', 'bob'],
    )
  })

  it('breaks a tie on the name, so the ring is the same every time', () => {
    const report = graphReport(['amy', 'bob', 'cho', 'dee'], [
      pay('dee', 'amy', 10),
      pay('bob', 'amy', 10),
      pay('cho', 'amy', 10),
    ])
    const first = settlementGraphData(report)!
    assert.deepEqual(first.payers.map((node) => node.member), ['bob', 'cho', 'dee'])
    assert.deepEqual(settlementGraphData(report), first)
  })

  it('puts the payers on a ring and the receivers inside it', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho', 'dee'], [
        pay('bob', 'amy', 30),
        pay('cho', 'amy', 20),
        pay('dee', 'amy', 10),
      ]),
    )!
    for (const node of data.payers) {
      assert.equal(Math.abs(Math.hypot(node.x, node.y) - 1) < 1e-9, true, node.member)
    }
    for (const node of data.receivers) {
      assert.equal(Math.hypot(node.x, node.y) < 0.5, true, node.member)
    }
  })

  it('puts a lone receiver dead centre', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob'], [pay('bob', 'amy', 30)]),
    )!
    assert.deepEqual(
      [data.receivers[0]!.x, data.receivers[0]!.y],
      [0, 0],
    )
  })

  it('spreads several receivers sideways rather than stacking them', () => {
    // Stacked, an arrow to the lower receiver passes behind the upper one and looks
    // like it starts there -- a picture of somebody both receiving and paying, which
    // is the one thing a settlement never contains.
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('cho', 'amy', 30),
        pay('cho', 'bob', 20),
      ]),
    )!
    assert.equal(data.receivers.length, 2)
    assert.equal(data.receivers.every((node) => node.y === 0), true)
    assert.notEqual(data.receivers[0]!.x, data.receivers[1]!.x)
  })

  it('points a payer’s label away from the middle, so no name lies across an arrow', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho', 'dee'], [
        pay('bob', 'amy', 30),
        pay('cho', 'amy', 20),
        pay('dee', 'amy', 10),
      ]),
    )!
    for (const node of data.payers) {
      if (node.labelSide === 'left') assert.equal(node.x < 0, true, node.member)
      if (node.labelSide === 'right') assert.equal(node.x > 0, true, node.member)
    }
  })

  it('points the receivers’ labels outwards, clear of arriving amounts', () => {
    // Away from the middle is away from the arrows and their amounts, which is the same
    // rule the ring follows. Above and below were tried first and put a receiver's name
    // on top of an arriving amount.
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('cho', 'amy', 30),
        pay('cho', 'bob', 20),
      ]),
    )!
    assert.deepEqual(
      data.receivers.map((node) => node.labelSide),
      ['left', 'right'],
    )
    // And each points away from the centre rather than across it.
    for (const node of data.receivers) {
      assert.equal(node.labelSide === (node.x < 0 ? 'left' : 'right'), true, node.member)
    }
  })

  it('sizes the dots between two bounds, largest mover largest', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('bob', 'amy', 100),
        pay('cho', 'amy', 1),
      ]),
    )!
    const bob = data.payers.find((node) => node.member === 'bob')!
    const cho = data.payers.find((node) => node.member === 'cho')!
    const amy = data.receivers[0]!
    assert.equal(bob.size > cho.size, true)
    // amy receives everything, so she is the largest dot of the three.
    assert.equal(amy.size >= bob.size, true)
    for (const node of [amy, bob, cho]) {
      assert.equal(node.size >= 10 && node.size <= 26, true, node.member)
    }
  })

  it('gives equal movers equal dots', () => {
    const data = settlementGraphData(
      graphReport(['amy', 'bob', 'cho'], [
        pay('bob', 'amy', 25),
        pay('cho', 'amy', 25),
      ]),
    )!
    assert.equal(data.payers[0]!.size, data.payers[1]!.size)
  })

  it('is empty rather than wrong when the data cannot be drawn', () => {
    const members = ['amy', 'bob', 'cho']
    const cases: Array<[string, Report]> = [
      ['nothing to settle', graphReport(members, [])],
      ['a self-transfer', graphReport(members, [pay('amy', 'amy', 10)])],
      ['a stranger', graphReport(members, [pay('zed', 'amy', 10)])],
      ['a zero amount', graphReport(members, [pay('bob', 'amy', 0)])],
      ['a negative amount', graphReport(members, [pay('bob', 'amy', -5)])],
      ['an infinite amount', graphReport(members, [pay('bob', 'amy', Infinity)])],
      ['a NaN amount', graphReport(members, [pay('bob', 'amy', NaN)])],
      // A member paying and receiving would mean the graph was drawing a chain the
      // settlement does not contain.
      ['a member on both sides', graphReport(members, [
        pay('bob', 'amy', 10), pay('amy', 'cho', 10),
      ])],
    ]
    for (const [name, report] of cases) {
      assert.equal(settlementGraphData(report), null, name)
    }
  })
})

describe('when the settlement is too big to draw', () => {
  /** `count` members all paying one receiver. */
  function fanIn(count: number): Report {
    const members = Array.from({ length: count }, (_, index) => `m${index}`)
    return graphReport(
      members,
      members.slice(1).map((member) => pay(member, 'm0', 10)),
    )
  }

  it('drops the graph above the node limit and keeps it at the limit', () => {
    const atLimit = settlementGraphData(fanIn(GRAPH_LIMITS.screen.nodes))
    assert.equal(shouldShowSettlementGraph(atLimit, 'screen'), true)
    const over = settlementGraphData(fanIn(GRAPH_LIMITS.screen.nodes + 1))
    assert.equal(shouldShowSettlementGraph(over, 'screen'), false)
  })

  it('is stricter on paper than on screen', () => {
    assert.equal(GRAPH_LIMITS.print.nodes <= GRAPH_LIMITS.screen.nodes, true)
    assert.equal(GRAPH_LIMITS.print.edges <= GRAPH_LIMITS.screen.edges, true)
    // A bill between the two limits is drawn on screen and printed as a table.
    const data = settlementGraphData(fanIn(GRAPH_LIMITS.print.nodes + 2))
    assert.equal(shouldShowSettlementGraph(data, 'screen'), true)
    assert.equal(shouldShowSettlementGraph(data, 'print'), false)
  })

  it('counts the graph’s own endpoints, not the whole trip', () => {
    // Twenty members, two of whom settle anything: a two-dot graph, not a twenty-dot
    // one, and well inside every limit.
    const members = Array.from({ length: 20 }, (_, index) => `m${index}`)
    const data = settlementGraphData(graphReport(members, [pay('m1', 'm0', 10)]))!
    assert.equal(data.payers.length + data.receivers.length, 2)
    assert.equal(shouldShowSettlementGraph(data, 'print'), true)
  })

  it('says no to a graph that could not be built at all', () => {
    assert.equal(shouldShowSettlementGraph(null, 'screen'), false)
    assert.equal(shouldShowSettlementGraph(null, 'print'), false)
  })
})

describe('the builder does not touch the report it is given', () => {
  it('leaves the settlement in its original order', () => {
    const report = makeReport()
    const before = JSON.stringify(report.settlement)
    settlementGraphData(report)
    assert.equal(JSON.stringify(report.settlement), before)
  })

  it('carries every amount through unchanged', () => {
    const report = makeReport()
    const data = settlementGraphData(report)!
    assert.deepEqual(
      data.links.map((link) => link.amount),
      report.settlement.map((transfer) => transfer.amount),
    )
  })
})

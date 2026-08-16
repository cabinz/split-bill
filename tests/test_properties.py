"""What has to be true of every report, checked over generated bills.

This is what step 0i put in place of the differential suite. Through the refactor,
correctness was defined by agreement with a frozen copy of V1: the safest possible
definition while 1200 lines were being moved, and the reason the move can be trusted
(plan §4.10). But V1 is a poor judge to keep. Its figures do not add up -- that is
what step 0h fixed -- so from 0h onwards it could only referee structure, and the
comparison had to carry a budget for every figure it looked at.

These assert the properties directly instead. Each one is something a member could
check by hand and would be right to complain about:

  * the shares of a record add up to the record
  * my consumption is the sum of my shares, and nobody else's
  * what I am asked to pay is what the report says I owe
  * everybody's nets cancel
  * re-exporting the same bill does not change what I owe

Run over `tests/fuzz.py`'s generator, so they hold across random member counts,
separators, `all` spellings, currency mixes and amount formats rather than over
whatever a person thought to write down. Reproducible from the seed:

    SPLITBILL_FUZZ_CASES=3000 uv run pytest tests/test_properties.py -q
"""

from __future__ import annotations

import csv as csvmod
import io
import os
import random
from pathlib import Path

import pytest

from splitbill.settle.graph import ABS_TOL
from tests.bills import Case, analyse_case, settled_per_member
from tests.fuzz import edge_case_bills, random_bill

FUZZ_CASES = int(os.environ.get("SPLITBILL_FUZZ_CASES", "20"))
SEEDS = list(range(FUZZ_CASES))

# Figures are sums of hundreds of floats, so exact comparison is meaningless; this
# is float noise only. Anything a defect could hide in is orders of magnitude above.
NOISE = 1e-6


def reports():
    """One report per generated bill, plus the pinned edge cases."""
    return [(f"seed{seed:05d}", random_bill(seed)) for seed in SEEDS] + [
        (case.name, case) for case in edge_case_bills()
    ]


@pytest.fixture(params=reports(), ids=lambda pair: pair[0])
def case(request) -> Case:
    """The bill under test. Parametrised, so every test below runs over all of
    them."""
    return request.param[1]


@pytest.fixture
def report(case, tmp_path):
    return analyse_case(case, case.materialize(tmp_path))


class TestSharesReconcile:
    """The appendix has to survive being added up, which is the whole point of it."""

    def test_every_share_is_a_whole_number_of_cents(self, report):
        for entry in report.ledger:
            assert entry.share == round(entry.share, 2), entry

    def test_the_shares_of_a_record_add_up_to_the_record(self, report):
        totals: dict[int, float] = {}
        amounts: dict[int, float] = {}
        for entry in report.ledger:
            totals[entry.record_id] = totals.get(entry.record_id, 0.0) + entry.share
            amounts[entry.record_id] = entry.amount_std
        for record_id, total in totals.items():
            assert total == pytest.approx(amounts[record_id], abs=NOISE), record_id

    def test_consumption_is_the_sum_of_a_members_own_shares(self, report):
        summed: dict[str, float] = {}
        for entry in report.ledger:
            summed[entry.member] = summed.get(entry.member, 0.0) + entry.share
        for position in report.positions:
            assert position.consumption == pytest.approx(
                summed.get(position.member, 0.0), abs=NOISE
            ), position.member

    def test_paid_is_the_sum_of_the_records_a_member_fronted(self, report):
        fronted: dict[str, float] = {}
        for _, creditor, amount in report.ledger.records():
            fronted[creditor] = fronted.get(creditor, 0.0) + amount
        for position in report.positions:
            assert position.paid == pytest.approx(
                fronted.get(position.member, 0.0), abs=NOISE
            ), position.member

    def test_total_spend_is_the_sum_of_the_records(self, report):
        total = sum(amount for _, _, amount in report.ledger.records())
        assert report.summary.total_spend == pytest.approx(total, abs=NOISE)

    def test_the_category_breakdown_covers_all_of_consumption(self, report):
        """Or is empty. A partial breakdown would be worse than none: it invites
        adding up a chart that does not come to the total beside it."""
        for position in report.positions:
            if not position.by_category:
                continue
            assert sum(position.by_category.values()) == pytest.approx(
                position.consumption, abs=NOISE
            ), position.member


class TestNetsAgree:
    """A net is derived three ways (plan §4.7). They have to be the same number."""

    def test_paid_minus_consumption_equals_lending_minus_borrowing(self, report):
        """The two derivations the report shows side by side. `paid - consumption`
        is correct but abstract; the other says "you covered this much for other
        people and they covered this much for you", which is what a member can
        actually check."""
        for position in report.positions:
            assert position.net == pytest.approx(
                position.paid_for_others - position.covered_by_others, abs=NOISE
            ), position.member
            assert position.net == pytest.approx(
                position.paid - position.consumption, abs=NOISE
            ), position.member

    def test_the_two_layers_agree_to_float_precision(self, report):
        """Layer 1's net and layer 2's, held to float noise rather than to a cent.

        `build_report` asserts this while assembling, so a regression fails there
        first. Stated here as a property because the bound is the interesting part: it
        used to be a cent per member, sized for `add_edge` dropping near-zero edges,
        and that allowance was what let a member be shown one net while being handed
        transfers clearing another. With edges dropped only on exact cancellation there
        is nothing left for it to absorb.

        Settles the report's own ledger again rather than re-reading the sheet -- same
        allocation, and re-deriving the nets from it is exactly what layer 2 does.
        """
        from splitbill.settle import settle

        settled = settle(report.ledger.lending_triples())
        for position in report.positions:
            assert position.net == pytest.approx(
                settled.net_flows.get(position.member, 0.0), abs=NOISE
            ), position.member

    def test_nets_sum_to_zero(self, report):
        """Every amount is both somebody's spending and somebody's outlay, so the
        nets have to cancel. If they do not, the settlement below is impossible and
        the report is describing a bill that cannot be settled."""
        total = sum(position.net for position in report.positions)
        assert total == pytest.approx(0.0, abs=NOISE * len(report.members) + NOISE)

    def test_fronting_for_others_balances_being_fronted_for(self, report):
        fronted = sum(p.paid_for_others for p in report.positions)
        covered = sum(p.covered_by_others for p in report.positions)
        assert fronted == pytest.approx(covered, abs=NOISE)


class TestSettlementIsValid:
    """What a member is asked to pay must be what the report says they owe."""

    def test_the_settlement_discharges_every_net(self, report):
        """The one property that makes the scheme acceptable at all.

        A member recognises their own net and recognises nothing about the
        counterparty they are told to pay, so the transfers adding up to that net is
        the entire argument for doing as asked.

        The tolerance is one cent, and what remains inside it is a policy rather than a
        disagreement. `simplest_equiv` treats a net within `ABS_TOL` as settled, so it
        emits no transfer for a member owed a single cent -- which is defensible: a
        one-cent bank transfer is not a thing to ask a person for.

        It used to be much wider -- a cent per member -- and that was covering a real
        defect. `LendingGraph.add_edge` dropped any edge `is_zero` called zero, which
        is true *at* one cent, and dropping an edge undoes its contribution to both
        endpoints' nets while layer 1 has already counted the share. Fuzz seed 1693 is
        the case: `Carol,ALL,6,KRW` becomes 0.03 HKD across three people, two of the
        three edges are exactly 0.01, and Carol was shown a net of 10,446.82 while
        being handed transfers adding to 10,446.80.

        `add_edge` now drops an edge only when it has cancelled out exactly, so the
        nets agree to float precision and this bound is down to the last cent the
        solver declines to move. Removing that too is
        ctx/feature-integer-minor-units.md, and this is where it will show as done.
        """
        settled = settled_per_member(
            (t.receiver, t.sender, t.amount) for t in report.settlement
        )
        for position in report.positions:
            assert settled.get(position.member, 0.0) == pytest.approx(
                position.net, abs=ABS_TOL
            ), position.member

    def test_the_settlement_discharges_the_nets_it_was_built_from_exactly(
        self, report, case, tmp_path
    ):
        """Against layer 2's own nets there is no tolerance to give.

        The gap above is entirely the two layers disagreeing, not the solver being
        approximate. Asserted separately so that a real solver defect cannot hide
        inside the allowance made for the disagreement.
        """
        from splitbill.settle import settle

        settled_result = settle(report.ledger.lending_triples())
        settled = settled_per_member(
            (t.receiver, t.sender, t.amount) for t in settled_result.settlement
        )
        for member, net in settled_result.net_flows.items():
            assert settled.get(member, 0.0) == pytest.approx(net, abs=NOISE), member

    def test_no_more_transfers_than_members_minus_one(self, report):
        """n-1 always suffices: pay everything into one member and back out. A
        scheme needing more has not simplified anything."""
        assert len(report.settlement) <= max(len(report.members) - 1, 0)

    def test_transfers_are_positive(self, report):
        """A negative transfer is a transfer in the other direction, written in a
        way that guarantees somebody reads it wrong."""
        for transfer in report.settlement:
            assert transfer.amount > 0, transfer

    def test_nobody_pays_themselves(self, report):
        for transfer in report.settlement:
            assert transfer.sender != transfer.receiver, transfer

    def test_a_settled_bill_needs_no_transfers(self, report):
        """If everybody's net is zero, the scheme is empty rather than a set of
        cancelling payments."""
        if all(abs(p.net) <= ABS_TOL for p in report.positions):
            assert report.settlement == ()


class TestLendingEdgesAreReal:
    """`lending_edges` is the part of the report that can be checked against
    memory: these are the people who actually paid for each other."""

    def test_edges_only_name_members(self, report):
        for edge in report.lending_edges:
            assert edge.creditor in report.members, edge
            assert edge.debtor in report.members, edge

    def test_no_self_edges(self, report):
        """A member covering their own share is not lending, and layer 1 drops it
        while it still knows which record it came from."""
        for edge in report.lending_edges:
            assert edge.creditor != edge.debtor, edge

    def test_each_pair_appears_once(self, report):
        """Aggregated per pair, so a member reading the table sees one line per
        person rather than one per record."""
        pairs = [(e.creditor, e.debtor) for e in report.lending_edges]
        assert len(pairs) == len(set(pairs))


class TestReproducibility:
    """A report that changes when nothing changed cannot be trusted twice."""

    def test_the_same_bill_gives_the_same_report(self, case, tmp_path):
        bill = case.materialize(tmp_path)
        first, second = analyse_case(case, bill), analyse_case(case, bill)

        assert first.members == second.members
        assert [(p.member, p.net) for p in first.positions] == [
            (p.member, p.net) for p in second.positions
        ]
        assert [(t.sender, t.receiver, t.amount) for t in first.settlement] == [
            (t.sender, t.receiver, t.amount) for t in second.settlement
        ]

    def test_reordering_the_rows_does_not_change_what_anybody_owes(
        self, case, tmp_path
    ):
        """Export the same bill with its rows in a different order, and every net
        comes out identical.

        This is what the remainder rule in `loader.ledger._allocate` is for. It hands
        the leftover cents to the earliest-sorting names rather than rotating through
        the records, which costs a little fairness -- the same member gains the cent
        every time -- and buys this. Rotating by record position would spread that
        out and make two exports of one bill disagree, which is the kind of
        discrepancy nobody can explain and everybody notices.

        The *pairing* is free to change, and does on about a quarter of these bills:
        the solver walks the nets in the order the graph accumulated them, and
        reordering the rows reorders that. Which of several equally-short schemes
        comes out is not a fact about the bill. What each member owes is, and that is
        what is asserted here.
        """
        if case.csv is None:
            pytest.skip("only inline CSV cases can be reordered")

        rows = list(csvmod.reader(io.StringIO(case.csv)))
        if len(rows) < 3:
            pytest.skip("nothing to reorder")

        header, body = rows[0], rows[1:]
        random.Random(case.name).shuffle(body)
        buffer = io.StringIO()
        writer = csvmod.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(body)

        shuffled = Case(
            name=f"{case.name}_shuffled",
            csv=buffer.getvalue(),
            separator=case.separator,
            all_selector=case.all_selector,
            std_currency=case.std_currency,
            rates=case.rates,
            columns=case.columns,
        )

        original = analyse_case(case, case.materialize(tmp_path))
        reordered = analyse_case(shuffled, shuffled.materialize(tmp_path))

        assert original.members == reordered.members
        before = {p.member: p.net for p in original.positions}
        after = {p.member: p.net for p in reordered.positions}
        for member, net in before.items():
            assert after[member] == pytest.approx(net, abs=NOISE), member


class TestJsonContract:
    """The report gets archived and read by a browser, so the JSON is the product."""

    def test_it_round_trips(self, report):
        import json

        assert json.loads(report.to_json()) == report.to_dict()

    def test_every_figure_is_serialised_to_the_cent(self, report):
        payload = report.to_dict()
        for position in payload["positions"]:
            for key in ("consumption", "paid", "paid_for_others",
                        "covered_by_others", "net"):
                assert position[key] == round(position[key], 2), (position, key)
        for row in payload["ledger"]:
            assert row["share"] == round(row["share"], 2), row

    def test_the_ledger_survives_serialisation_intact(self, report):
        """Every share, not a summary of them -- the appendix is made of this."""
        assert len(report.to_dict()["ledger"]) == len(report.ledger)

    def test_members_are_listed_in_sorted_order(self, report):
        payload = report.to_dict()
        assert payload["members"] == sorted(payload["members"])

    def test_positions_are_ordered_by_net_descending(self, report):
        """Creditors first, so the table reads in the same direction as the
        settlement it exists to justify."""
        nets = [p["net"] for p in report.to_dict()["positions"]]
        assert nets == sorted(nets, reverse=True)


class TestTheGeneratorItself:
    """A generator quietly producing only trivial bills would pass everything."""

    def test_all_spellings_are_reached(self):
        from tests.fuzz import ALL_SPELLINGS

        seen = set()
        for seed in range(400):
            csv = random_bill(seed).csv
            seen |= {s for s in ALL_SPELLINGS
                     if f",{s},".replace(",,", ",") in csv or f",{s}\n" in csv
                     or f",{s}," in csv}
        assert len(seen) >= 4, f"only reached {seen}"

    def test_separators_vary(self):
        assert len({random_bill(seed).separator for seed in range(60)}) >= 3

    def test_both_currency_modes_are_reached(self):
        modes = {random_bill(seed).std_currency is None for seed in range(60)}
        assert modes == {True, False}

    def test_thousand_separated_amounts_appear(self):
        assert any('","' in random_bill(seed).csv or ',"' in random_bill(seed).csv
                   for seed in range(200))

    def test_bills_are_reproducible_from_the_seed(self):
        """A failure has to be re-runnable, or the volume is worthless."""
        assert random_bill(4242).csv == random_bill(4242).csv

    def test_descriptive_columns_appear_sometimes_and_not_always(self):
        has_meta = {"Category" in random_bill(seed).csv for seed in range(60)}
        assert has_meta == {True, False}

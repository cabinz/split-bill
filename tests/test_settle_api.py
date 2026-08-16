"""The settle layer's entry point.

`tests/test_graph_correctness.py` covers the algorithm. This covers the contract
around it: the triples-only input, the direction a Transfer runs in, and the
distinction between real obligations and the payments that clear them.

That distinction is the reason the layer returns both. A settlement will name a
counterparty a member never dealt with, and no amount of formatting makes that
self-evident -- only showing it next to the real lending does.
"""

import pytest

from splitbill.settle import Edge, SettleResult, Transfer, settle
from splitbill.settle.graph import is_zero


class TestLendingEdges:
    def test_edges_are_the_real_obligations(self):
        result = settle([("Alice", "Bob", 60.0), ("Bob", "Carol", 30.0)])
        assert result.lending_edges == (
            Edge("Alice", "Bob", 60.0),
            Edge("Bob", "Carol", 30.0),
        )

    def test_repeated_pairs_aggregate(self):
        """Two records between the same pair are one obligation."""
        result = settle([("Alice", "Bob", 40.0), ("Alice", "Bob", 25.0)])
        assert result.lending_edges == (Edge("Alice", "Bob", 65.0),)

    def test_lending_both_ways_keeps_both_edges(self):
        """Alice fronted 50 for Bob and Bob fronted 50 for Alice. Both happened,
        so both stay in the lending view; only the settlement collapses, because
        the nets cancel. The two views are not two formattings of one list."""
        result = settle([("Alice", "Bob", 50.0), ("Bob", "Alice", 50.0)])
        assert result.lending_edges == (
            Edge("Alice", "Bob", 50.0),
            Edge("Bob", "Alice", 50.0),
        )
        assert result.settlement == ()
        assert all(is_zero(net) for net in result.net_flows.values())

    def test_self_loop_is_rejected(self):
        """Layer 1 drops a member's own share while it still knows the record it
        belongs to. One arriving here means that was missed."""
        with pytest.raises(AssertionError):
            settle([("Alice", "Alice", 10.0)])


class TestTransferDirection:
    def test_sender_pays_receiver(self):
        """Alice fronted 100 for Bob, so Bob is the one who pays."""
        result = settle([("Alice", "Bob", 100.0)])
        assert result.settlement == (
            Transfer(sender="Bob", receiver="Alice", amount=100.0),
        )

    def test_net_creditor_never_pays(self):
        result = settle([("Alice", "Bob", 80.0), ("Alice", "Carol", 20.0)])
        assert "Alice" not in {t.sender for t in result.settlement}


class TestSettlementIsNotLending:
    """The headline claim of the report, in two lines of setup.

    Alice fronts for Bob; Bob fronts the same amount for Carol. Bob is square, so
    the settlement asks Carol to pay Alice -- two people with no dealings between
    them. Anyone shown only the settlement is entitled to ask why.
    """

    CHAIN = [("Alice", "Bob", 100.0), ("Bob", "Carol", 100.0)]

    def test_settlement_names_a_pair_that_never_dealt(self):
        result = settle(self.CHAIN)
        assert result.settlement == (Transfer("Carol", "Alice", 100.0),)

        lending_pairs = {(e.creditor, e.debtor) for e in result.lending_edges}
        assert ("Alice", "Carol") not in lending_pairs
        assert ("Carol", "Alice") not in lending_pairs

    def test_the_intermediary_drops_out(self):
        result = settle(self.CHAIN)
        assert is_zero(result.net_flows["Bob"])
        assert "Bob" not in {t.sender for t in result.settlement}
        assert "Bob" not in {t.receiver for t in result.settlement}

    def test_both_views_are_returned(self):
        """Losing either one is what makes the other unanswerable."""
        result = settle(self.CHAIN)
        assert result.lending_edges
        assert result.settlement
        assert result.lending_edges != result.settlement


class TestInvariants:
    BILLS = [
        [],
        [("Alice", "Bob", 10.0)],
        [("Alice", "Bob", 60.0), ("Alice", "Carol", 60.0), ("Bob", "Carol", 30.0)],
        [("Alice", "Bob", 100.0), ("Bob", "Carol", 100.0)],
        [
            ("Alice", "Bob", 148.0),
            ("Bob", "Carol", 89.0),
            ("Carol", "Dave", 17.9),
            ("Dave", "Alice", 25.86),
            ("Eve", "Alice", 31.5),
        ],
    ]
    IDS = [f"{len(b)}-lendings" for b in BILLS]

    @pytest.mark.parametrize("bill", BILLS, ids=IDS)
    def test_nets_sum_to_zero(self, bill):
        assert is_zero(sum(settle(bill).net_flows.values()))

    @pytest.mark.parametrize("bill", BILLS, ids=IDS)
    def test_settlement_discharges_every_net(self, bill):
        result = settle(bill)
        moved = dict.fromkeys(result.net_flows, 0.0)
        for transfer in result.settlement:
            moved[transfer.receiver] += transfer.amount
            moved[transfer.sender] -= transfer.amount
        for member, net in result.net_flows.items():
            assert is_zero(moved[member] - net), f"member {member}"

    @pytest.mark.parametrize("bill", BILLS, ids=IDS)
    def test_no_more_transfers_than_members_minus_one(self, bill):
        result = settle(bill)
        assert len(result.settlement) <= max(len(result.net_flows) - 1, 0)

    @pytest.mark.parametrize("bill", BILLS, ids=IDS)
    def test_settlement_is_no_longer_than_lending(self, bill):
        """Simplifying must never make the list of payments longer."""
        result = settle(bill)
        assert len(result.settlement) <= len(result.lending_edges)

    def test_empty_bill_settles_to_nothing(self):
        assert settle([]) == SettleResult(
            lending_edges=(), settlement=(), net_flows={}
        )

    def test_repeated_calls_agree(self):
        """Same input, same scheme -- a snapshot of a coin flip is no baseline."""
        bill = self.BILLS[-1]
        assert settle(bill) == settle(bill)

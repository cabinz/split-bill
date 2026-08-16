"""End-to-end baseline over a realistic bill.

Every other test in this suite builds its own three-row bill. Those pin down
behaviour; none of them would notice if the whole pipeline drifted by a cent on
a bill of real size. This one does: it runs the fixture described in
`tests/fixtures/README.md` -- 153 records, 7 members, CJK column names, no
currency column -- and pins the figures a member would actually read off the
report.

The expected values are the ones the report displays, to the cent, so the
tolerance here is half a cent. Any refactor that changes them changes what
somebody gets asked to pay.
"""

import pytest

# Half a cent: the report rounds to the cent, so this pins the displayed value
# without pinning float noise below it.
CENT = 0.005

# member -> (consumption, paid, paid_for_others, covered_by_others)
#
# These moved by a few cents at step 0h, when layer 1 started allocating the
# leftover cents of each record instead of letting them dissolve into floating
# point. The remainder goes to the earliest-sorting name, and these seven sort by
# codepoint -- 丁 first, 甲 last -- so 丁 gains and 甲 loses. `paid` is unchanged
# throughout: it sums record totals, which nobody was splitting.
EXPECTED_STATS = {
    "甲": (7131.22, 22454.74, 17974.46, 2650.94),
    "戊": (5525.51, 6139.57, 4927.45, 4313.39),
    "庚": (797.40, 0.00, 0.00, 797.40),
    "乙": (6855.92, 5884.50, 4677.00, 5648.42),
    "己": (3079.42, 874.00, 766.66, 2972.08),
    "丙": (7156.48, 2633.50, 2182.34, 6705.32),
    "丁": (7440.36, 0.00, 0.00, 7440.36),
}

# The order the statistics table renders in: net descending, ties by name.
EXPECTED_STATS_ORDER = ["甲", "戊", "庚", "乙", "己", "丙", "丁"]

# (creditor, debtor, amount) -- who ends up paying whom, and how much.
EXPECTED_SETTLEMENT = [
    ("甲", "乙", 971.42),
    ("甲", "丙", 4522.98),
    ("甲", "丁", 7440.36),
    ("甲", "己", 2205.42),
    ("甲", "庚", 183.34),
    ("戊", "庚", 614.06),
]

EXPECTED_TOTAL_SPEND = 37986.31
EXPECTED_RECORD_COUNT = 153


class TestBaselineShape:
    def test_members(self, realistic):
        assert sorted(realistic.members) == sorted(EXPECTED_STATS)

    def test_record_count(self, realistic):
        assert len(realistic.loaded.raw_frame) == EXPECTED_RECORD_COUNT

    def test_total_spend(self, realistic):
        total = realistic.loaded.raw_frame["金额"].sum()
        assert total == pytest.approx(EXPECTED_TOTAL_SPEND, abs=CENT)


class TestBaselineStats:
    def test_every_member_matches(self, realistic):
        for name, expected in EXPECTED_STATS.items():
            s = realistic.positions[name]
            actual = (s.consumption, s.paid, s.paid_for_others, s.covered_by_others)
            assert actual == pytest.approx(expected, abs=CENT), f"member {name}"

    def test_table_order(self, realistic):
        assert list(realistic.positions) == EXPECTED_STATS_ORDER

    def test_net_agrees_with_lending_view(self, realistic):
        """`paid - consumption` and `paid_for_others - covered_by_others` are the
        same number reached two ways (see plan §4.7). Both are shown in the
        report, so a member can check one against the other."""
        for name, s in realistic.positions.items():
            assert s.net == pytest.approx(
                s.paid_for_others - s.covered_by_others, abs=CENT
            ), f"member {name}"

    def test_nets_sum_to_zero(self, realistic):
        total = sum(s.net for s in realistic.positions.values())
        assert total == pytest.approx(0.0, abs=CENT)


class TestBaselineSettlement:
    def test_transfers(self, realistic):
        actual = [(t.receiver, t.sender, t.amount)
                  for t in realistic.settled.settlement]
        assert len(actual) == len(EXPECTED_SETTLEMENT)
        for got, expected in zip(actual, EXPECTED_SETTLEMENT):
            assert got[:2] == expected[:2]
            assert got[2] == pytest.approx(expected[2], abs=CENT)

    def test_transfer_count_is_at_most_members_minus_one(self, realistic):
        """A settlement never needs more transfers than members minus one."""
        assert len(realistic.settled.settlement) <= len(EXPECTED_STATS) - 1

    def test_each_member_settles_to_their_net(self, realistic):
        """The scheme has to discharge exactly the net each member was shown --
        that is the whole reason a member can accept it without recognising the
        counterparty.

        Layer 2's own net, checked against layer 1's: the two are computed from
        different data by code that does not import each other (plan §4.7).
        """
        for name, s in realistic.positions.items():
            assert realistic.nets[name] == pytest.approx(
                s.net, abs=CENT
            ), f"member {name}"

    def test_displayed_transfers_add_up_to_the_net_exactly(self, realistic):
        """Summing the transfers *as displayed* gives the net back exactly.

        Before step 0h it did not. Shares were `total / n` at full precision and each
        transfer was rounded to the cent for display, so a member appearing in n
        transfers could be off by n half-cents -- 甲, in five of them, landed 0.006
        short of a net of 15,323.236. The report was asking to be checked and then
        failing the check.

        Now every share is a whole number of cents, so the nets are too, and so are
        the transfers that discharge them. Nothing is being rounded for display any
        more; `round` below only clears the float noise that summing 1,071 shares
        leaves behind, which is why the tolerance is 1e-6 and not half a cent.

        The half-cent budget this test used to allow is gone deliberately. If it ever
        needs to come back, something has started rounding again.
        """
        settled = dict.fromkeys(EXPECTED_STATS, 0.0)
        for transfer in realistic.settled.settlement:
            shown = round(transfer.amount, 2)  # what the report displays
            settled[transfer.receiver] += shown
            settled[transfer.sender] -= shown

        for name, s in realistic.positions.items():
            assert settled[name] == pytest.approx(
                s.net, abs=1e-6
            ), f"member {name} does not settle to their net"

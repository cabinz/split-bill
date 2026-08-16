"""Test per-member spending statistics (consumption / paid / paid for others)."""

import pytest
from splitbill.loader import MemberStats
from splitbill.render.text import format_member_stats_table
from splitbill.settle.graph import is_equal
from tests.conftest import analyse, load_bill, rows_to_csv


def stats_of(rows, tmp_path, header="Creditor,Debtor,Amount,Currency", **kwargs):
    """Per-member statistics for a bill made of the given rows."""
    return load_bill(rows_to_csv(rows, header), tmp_path, **kwargs).positions


class TestMemberStats:
    """Test cases for the statistics of each member's spending."""

    def test_creditor_not_sharing_the_record(self, tmp_path):
        """A creditor outside the debtor list consumes nothing and fronts it all."""
        stats = stats_of(["Alice,Bob,100,USD"], tmp_path)

        assert is_equal(stats["Alice"].consumption, 0)
        assert is_equal(stats["Alice"].paid, 100)
        assert is_equal(stats["Alice"].paid_for_others, 100)
        assert is_equal(stats["Alice"].covered_by_others, 0)
        assert is_equal(stats["Alice"].net, 100)

        assert is_equal(stats["Bob"].consumption, 100)
        assert is_equal(stats["Bob"].paid, 0)
        assert is_equal(stats["Bob"].paid_for_others, 0)
        assert is_equal(stats["Bob"].covered_by_others, 100)
        assert is_equal(stats["Bob"].net, -100)

    def test_creditor_sharing_the_record(self, tmp_path):
        """A creditor listed as a debtor takes an even share of the record."""
        stats = stats_of(['Alice,"Alice, Bob",100,USD'], tmp_path)

        # Alice fronts 100, consumes 50 of it, and covers Bob's 50.
        assert is_equal(stats["Alice"].consumption, 50)
        assert is_equal(stats["Alice"].paid, 100)
        assert is_equal(stats["Alice"].paid_for_others, 50)
        assert is_equal(stats["Alice"].net, 50)

        assert is_equal(stats["Bob"].consumption, 50)
        assert is_equal(stats["Bob"].paid, 0)
        assert is_equal(stats["Bob"].covered_by_others, 50)
        assert is_equal(stats["Bob"].net, -50)

    def test_all_selector_splits_among_every_member(self, tmp_path):
        """The 'all' selector charges every known member an even share."""
        stats = stats_of([
            "Alice,all,90,USD",
            "Bob,Charlie,30,USD",  # brings Charlie into the member set
        ], tmp_path)

        # 3 members, so the 90 is split 30 each; Alice covers 60 for the others.
        assert is_equal(stats["Alice"].consumption, 30)
        assert is_equal(stats["Alice"].paid, 90)
        assert is_equal(stats["Alice"].paid_for_others, 60)

        assert is_equal(stats["Bob"].consumption, 30)
        assert is_equal(stats["Bob"].paid, 30)
        assert is_equal(stats["Bob"].paid_for_others, 30)

        assert is_equal(stats["Charlie"].consumption, 30 + 30)
        assert is_equal(stats["Charlie"].paid, 0)

    def test_consumption_accumulates_across_records(self, tmp_path):
        """Consumption and paid sum up over every record a member appears on."""
        stats = stats_of([
            "Alice,Bob,100,USD",
            "Alice,Bob,50,USD",
            'Bob,"Alice, Bob",80,USD',
        ], tmp_path)

        assert is_equal(stats["Alice"].consumption, 40)
        assert is_equal(stats["Alice"].paid, 150)
        assert is_equal(stats["Alice"].paid_for_others, 150)
        assert is_equal(stats["Alice"].covered_by_others, 40)

        assert is_equal(stats["Bob"].consumption, 100 + 50 + 40)
        assert is_equal(stats["Bob"].paid, 80)
        assert is_equal(stats["Bob"].paid_for_others, 40)

    def test_net_matches_graph_net_out_flow(self, tmp_path):
        """Net is exactly the net outflow the settlement is computed from."""
        bill = analyse(rows_to_csv([
            "Alice,all,120,USD",
            'Bob,"Alice, Charlie",60,USD',
            "Charlie,Alice,25,USD",
            "Alice,Bob,10,USD",
        ]), tmp_path)

        for name, s in bill.positions.items():
            assert is_equal(s.net, bill.nets[name]), f"{name} net mismatch"

    def test_totals_balance(self, tmp_path):
        """Everything paid gets consumed, and lending nets out to zero."""
        stats = stats_of([
            "Alice,all,120,USD",
            'Bob,"Alice, Charlie",60,USD',
            "Charlie,Alice,25,USD",
        ], tmp_path)

        total_consumption = sum(s.consumption for s in stats.values())
        total_paid = sum(s.paid for s in stats.values())
        assert is_equal(total_consumption, total_paid)
        assert is_equal(total_consumption, 120 + 60 + 25)

        # Fronting for others must balance being fronted for.
        assert is_equal(sum(s.paid_for_others for s in stats.values()),
                        sum(s.covered_by_others for s in stats.values()))
        assert is_equal(sum(s.net for s in stats.values()), 0)

    def test_net_equals_lending_minus_borrowing(self, tmp_path):
        """Net is what a member fronted for others less what others fronted."""
        stats = stats_of([
            'Alice,"Alice, Bob, Charlie",90,USD',
            'Bob,"Alice, Bob",40,USD',
        ], tmp_path)
        for name, s in stats.items():
            assert is_equal(s.net, s.paid_for_others - s.covered_by_others), name

    def test_settled_member_is_still_listed(self, tmp_path):
        """A member who comes out even still shows up with their spending."""
        stats = stats_of([
            'Alice,"Alice, Bob",100,USD',
            'Bob,"Alice, Bob",100,USD',
        ], tmp_path)

        assert set(stats.keys()) == {"Alice", "Bob"}
        for name in ("Alice", "Bob"):
            assert is_equal(stats[name].consumption, 100)
            assert is_equal(stats[name].paid, 100)
            assert is_equal(stats[name].net, 0)

    def test_ordered_by_net_descending(self, tmp_path):
        """Creditors come first, mirroring the settlement output."""
        stats = stats_of([
            "Alice,all,120,USD",
            "Bob,Charlie,30,USD",
        ], tmp_path)
        nets = [s.net for s in stats.values()]
        assert nets == sorted(nets, reverse=True)

    def test_custom_separator(self, tmp_path):
        """A custom name separator is honoured when splitting debtors."""
        stats = stats_of(["Alice,Bob;Charlie,100,USD"], tmp_path, separator=";")

        assert set(stats.keys()) == {"Alice", "Bob", "Charlie"}
        assert is_equal(stats["Bob"].consumption, 50)
        assert is_equal(stats["Charlie"].consumption, 50)
        assert is_equal(stats["Alice"].paid_for_others, 100)


class TestMemberStatsTable:
    """Test cases for rendering the statistics table."""

    def test_table_lists_every_member_and_amount(self, tmp_path):
        stats = stats_of(['Alice,"Alice, Bob",100,USD'], tmp_path)
        table = format_member_stats_table(stats, "USD")

        assert "Alice" in table and "Bob" in table
        assert "Consumption (USD)" in table
        assert "Paid for Others (USD)" in table
        assert "50.00" in table
        assert "+50.00" in table  # Alice's net is signed
        assert "-50.00" in table  # Bob's net is signed

    def test_table_omits_currency_when_absent(self, tmp_path):
        stats = stats_of(["Alice,Bob,100,USD"], tmp_path)
        table = format_member_stats_table(stats)

        assert "Consumption" in table
        assert "(USD)" not in table

    def test_table_rows_are_aligned(self, tmp_path):
        """Every rendered line shares the same display width."""
        from splitbill.render.text import get_display_width

        stats = stats_of([
            "Alice,all,1234567,USD",
            "Bob,Charlie,30,USD",
        ], tmp_path)
        lines = format_member_stats_table(stats, "USD").split("\n")

        widths = {get_display_width(line) for line in lines}
        assert len(widths) == 1, f"ragged table: {widths}"

    def test_empty_stats(self, tmp_path):
        assert format_member_stats_table({}) == "No members found."


class TestWideCharacterAlignment:
    """Test cases for names containing full-width (CJK) characters."""

    def test_cjk_names_stay_aligned(self, tmp_path):
        from splitbill.render.text import get_display_width

        stats = stats_of([
            "小明,all,300,USD",
            "小红,大卫,60,USD",
        ], tmp_path)
        assert set(stats.keys()) == {"小明", "小红", "大卫"}

        lines = format_member_stats_table(stats, "USD").split("\n")
        widths = {get_display_width(line) for line in lines}
        assert len(widths) == 1, f"ragged table: {widths}"

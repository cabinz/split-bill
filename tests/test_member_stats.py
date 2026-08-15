"""Test per-member spending statistics (consumption / paid / paid for others)."""

import pytest
import os
import tempfile
from splitbill.loader import Loader, DataFormat, MemberStats
from splitbill.formatter import format_member_stats_table
from splitbill.graph import is_equal


def make_loader(rows, header="Creditor,Debtor,Amount,Currency", **kwargs):
    """Build a Loader over a temporary CSV of the given rows."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False,
                                     encoding='utf-8') as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")
        temp_path = f.name
    try:
        return Loader(temp_path, DataFormat(**kwargs))
    finally:
        os.unlink(temp_path)


class TestMemberStats:
    """Test cases for the statistics of each member's spending."""

    def test_creditor_not_sharing_the_record(self):
        """A creditor outside the debtor list consumes nothing and fronts it all."""
        loader = make_loader(["Alice,Bob,100,USD"])
        stats = loader.get_member_stats()

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

    def test_creditor_sharing_the_record(self):
        """A creditor listed as a debtor takes an even share of the record."""
        loader = make_loader(['Alice,"Alice, Bob",100,USD'])
        stats = loader.get_member_stats()

        # Alice fronts 100, consumes 50 of it, and covers Bob's 50.
        assert is_equal(stats["Alice"].consumption, 50)
        assert is_equal(stats["Alice"].paid, 100)
        assert is_equal(stats["Alice"].paid_for_others, 50)
        assert is_equal(stats["Alice"].net, 50)

        assert is_equal(stats["Bob"].consumption, 50)
        assert is_equal(stats["Bob"].paid, 0)
        assert is_equal(stats["Bob"].covered_by_others, 50)
        assert is_equal(stats["Bob"].net, -50)

    def test_all_selector_splits_among_every_member(self):
        """The 'all' selector charges every known member an even share."""
        loader = make_loader([
            "Alice,all,90,USD",
            "Bob,Charlie,30,USD",  # brings Charlie into the member set
        ])
        stats = loader.get_member_stats()

        # 3 members, so the 90 is split 30 each; Alice covers 60 for the others.
        assert is_equal(stats["Alice"].consumption, 30)
        assert is_equal(stats["Alice"].paid, 90)
        assert is_equal(stats["Alice"].paid_for_others, 60)

        assert is_equal(stats["Bob"].consumption, 30)
        assert is_equal(stats["Bob"].paid, 30)
        assert is_equal(stats["Bob"].paid_for_others, 30)

        assert is_equal(stats["Charlie"].consumption, 30 + 30)
        assert is_equal(stats["Charlie"].paid, 0)

    def test_consumption_accumulates_across_records(self):
        """Consumption and paid sum up over every record a member appears on."""
        loader = make_loader([
            "Alice,Bob,100,USD",
            "Alice,Bob,50,USD",
            'Bob,"Alice, Bob",80,USD',
        ])
        stats = loader.get_member_stats()

        assert is_equal(stats["Alice"].consumption, 40)
        assert is_equal(stats["Alice"].paid, 150)
        assert is_equal(stats["Alice"].paid_for_others, 150)
        assert is_equal(stats["Alice"].covered_by_others, 40)

        assert is_equal(stats["Bob"].consumption, 100 + 50 + 40)
        assert is_equal(stats["Bob"].paid, 80)
        assert is_equal(stats["Bob"].paid_for_others, 40)

    def test_net_matches_graph_net_out_flow(self):
        """Net is exactly the net outflow the settlement is computed from."""
        loader = make_loader([
            "Alice,all,120,USD",
            'Bob,"Alice, Charlie",60,USD',
            "Charlie,Alice,25,USD",
            "Alice,Bob,10,USD",
        ])
        stats = loader.get_member_stats()
        net_out_flow = loader.get_graph().net_out_flow

        for name, s in stats.items():
            assert is_equal(s.net, net_out_flow[name]), f"{name} net mismatch"

    def test_totals_balance(self):
        """Everything paid gets consumed, and lending nets out to zero."""
        loader = make_loader([
            "Alice,all,120,USD",
            'Bob,"Alice, Charlie",60,USD',
            "Charlie,Alice,25,USD",
        ])
        stats = loader.get_member_stats()

        total_consumption = sum(s.consumption for s in stats.values())
        total_paid = sum(s.paid for s in stats.values())
        assert is_equal(total_consumption, total_paid)
        assert is_equal(total_consumption, 120 + 60 + 25)

        # Fronting for others must balance being fronted for.
        assert is_equal(sum(s.paid_for_others for s in stats.values()),
                        sum(s.covered_by_others for s in stats.values()))
        assert is_equal(sum(s.net for s in stats.values()), 0)

    def test_net_equals_lending_minus_borrowing(self):
        """Net is what a member fronted for others less what others fronted."""
        loader = make_loader([
            'Alice,"Alice, Bob, Charlie",90,USD',
            'Bob,"Alice, Bob",40,USD',
        ])
        for name, s in loader.get_member_stats().items():
            assert is_equal(s.net, s.paid_for_others - s.covered_by_others), name

    def test_settled_member_is_still_listed(self):
        """A member who comes out even still shows up with their spending."""
        loader = make_loader([
            'Alice,"Alice, Bob",100,USD',
            'Bob,"Alice, Bob",100,USD',
        ])
        stats = loader.get_member_stats()

        assert set(stats.keys()) == {"Alice", "Bob"}
        for name in ("Alice", "Bob"):
            assert is_equal(stats[name].consumption, 100)
            assert is_equal(stats[name].paid, 100)
            assert is_equal(stats[name].net, 0)

    def test_ordered_by_net_descending(self):
        """Creditors come first, mirroring the settlement output."""
        loader = make_loader([
            "Alice,all,120,USD",
            "Bob,Charlie,30,USD",
        ])
        nets = [s.net for s in loader.get_member_stats().values()]
        assert nets == sorted(nets, reverse=True)

    def test_custom_separator(self):
        """A custom name separator is honoured when splitting debtors."""
        loader = make_loader(["Alice,Bob;Charlie,100,USD"], separator=";")
        stats = loader.get_member_stats()

        assert set(stats.keys()) == {"Alice", "Bob", "Charlie"}
        assert is_equal(stats["Bob"].consumption, 50)
        assert is_equal(stats["Charlie"].consumption, 50)
        assert is_equal(stats["Alice"].paid_for_others, 100)


class TestMemberStatsTable:
    """Test cases for rendering the statistics table."""

    def test_table_lists_every_member_and_amount(self):
        loader = make_loader(['Alice,"Alice, Bob",100,USD'])
        table = format_member_stats_table(loader.get_member_stats(), "USD")

        assert "Alice" in table and "Bob" in table
        assert "Consumption (USD)" in table
        assert "Paid for Others (USD)" in table
        assert "50.00" in table
        assert "+50.00" in table  # Alice's net is signed
        assert "-50.00" in table  # Bob's net is signed

    def test_table_omits_currency_when_absent(self):
        loader = make_loader(["Alice,Bob,100,USD"])
        table = format_member_stats_table(loader.get_member_stats())

        assert "Consumption" in table
        assert "(USD)" not in table

    def test_table_rows_are_aligned(self):
        """Every rendered line shares the same display width."""
        from splitbill.formatter import get_display_width

        loader = make_loader([
            "Alice,all,1234567,USD",
            "Bob,Charlie,30,USD",
        ])
        lines = format_member_stats_table(
            loader.get_member_stats(), "USD").split("\n")

        widths = {get_display_width(line) for line in lines}
        assert len(widths) == 1, f"ragged table: {widths}"

    def test_empty_stats(self):
        assert format_member_stats_table({}) == "No members found."


class TestWideCharacterAlignment:
    """Test cases for names containing full-width (CJK) characters."""

    def test_cjk_names_stay_aligned(self):
        from splitbill.formatter import get_display_width

        loader = make_loader([
            "小明,all,300,USD",
            "小红,大卫,60,USD",
        ])
        stats = loader.get_member_stats()
        assert set(stats.keys()) == {"小明", "小红", "大卫"}

        lines = format_member_stats_table(stats, "USD").split("\n")
        widths = {get_display_width(line) for line in lines}
        assert len(widths) == 1, f"ragged table: {widths}"

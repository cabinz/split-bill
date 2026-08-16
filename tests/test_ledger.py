"""The ledger, which is the one piece of Phase 0 that is newly written.

The differential harness already proves the totals still come out the same. What
it cannot check is the thing the ledger exists for: that the shares behind those
totals survive, individually, attached to the record they came from. A report
whose figures are right but whose working is missing is exactly what V2 set out
to stop shipping.

So these tests read the table directly -- one row per person per record, adding up
to the record, with a creditor's own share marked rather than dropped.
"""

from pathlib import Path

import pandas as pd
import pytest

from splitbill.loader import DataFormat
from splitbill.loader.ledger import Ledger, build_ledger
from tests.conftest import load_bill

FIXTURE = Path(__file__).parent / "fixtures" / "bill_realistic.csv"


def ledger_of(csv: str, tmp_path: Path, **cfg_kwargs) -> Ledger:
    return load_bill(csv, tmp_path, **cfg_kwargs).ledger


SIMPLE = "Creditor,Debtor,Amount\nAlice,\"Alice, Bob, Carol\",90\nBob,Carol,50\n"


class TestShape:
    def test_one_entry_per_person_per_record(self, tmp_path):
        ledger = ledger_of(SIMPLE, tmp_path)
        assert len(ledger) == 4  # three sharers, then one
        assert [e.record_id for e in ledger] == [1, 1, 1, 2]
        assert [e.member for e in ledger] == ["Alice", "Bob", "Carol", "Carol"]

    def test_shares_add_up_to_the_record(self, tmp_path):
        ledger = ledger_of(SIMPLE, tmp_path)
        by_record = {}
        for entry in ledger:
            by_record.setdefault(entry.record_id, []).append(entry)
        for record_id, entries in by_record.items():
            total = sum(e.share for e in entries)
            assert total == pytest.approx(entries[0].amount_std), f"record {record_id}"

    def test_records_yields_each_record_once(self, tmp_path):
        ledger = ledger_of(SIMPLE, tmp_path)
        assert list(ledger.records()) == [(1, "Alice", 90.0), (2, "Bob", 50.0)]

    def test_entries_keep_source_order(self, tmp_path):
        """The appendix is read against the original sheet, so order is content."""
        ledger = ledger_of(SIMPLE, tmp_path)
        assert [e.record_id for e in ledger] == sorted(e.record_id for e in ledger)

    def test_empty_ledger(self):
        assert len(Ledger()) == 0
        assert list(Ledger().records()) == []
        assert list(Ledger().lending_triples()) == []


class TestOwnShare:
    def test_creditors_own_share_is_marked_not_dropped(self, tmp_path):
        """Alice paid 90 for three people, so 30 of it was her own.

        V1 discarded that share as soon as it had been counted. Keeping it is what
        lets a member see the whole record rather than the part they are owed.
        """
        ledger = ledger_of(SIMPLE, tmp_path)
        own = [e for e in ledger if e.is_own_share]
        assert len(own) == 1
        assert (own[0].member, own[0].share) == ("Alice", 30.0)

    def test_lending_triples_skip_the_creditors_own_share(self, tmp_path):
        ledger = ledger_of(SIMPLE, tmp_path)
        assert list(ledger.lending_triples()) == [
            ("Alice", "Bob", 30.0),
            ("Alice", "Carol", 30.0),
            ("Bob", "Carol", 50.0),
        ]

    def test_creditor_not_sharing_has_no_own_share(self, tmp_path):
        ledger = ledger_of(
            "Creditor,Debtor,Amount\nAlice,\"Bob, Carol\",80\n", tmp_path
        )
        assert not any(e.is_own_share for e in ledger)

    def test_only_the_first_occurrence_counts_as_own(self, tmp_path):
        """A name written twice in one cell gets two shares.

        V1 removed the creditor from the debtor list with `list.remove`, which
        takes out one occurrence; the second was still treated as lending. That
        behaviour is preserved rather than silently corrected -- the sheet said
        what it said, and a share quietly halved is worse than a total that looks
        odd enough to ask about.
        """
        df = pd.DataFrame({
            "Creditor": ["Alice"],
            "Debtor": ["Alice, Alice, Bob"],
            "Amount": [90.0],
        })
        cfg = DataFormat()
        df["Total Amount"] = df["Amount"]
        ledger = build_ledger(df, cfg, {"Alice", "Bob"}, "Total Amount")

        assert [(e.member, e.share, e.is_own_share) for e in ledger] == [
            ("Alice", 30.0, True),
            ("Alice", 30.0, False),
            ("Bob", 30.0, False),
        ]
        # The second Alice becomes a self-loop, which the settle layer rejects.
        assert ("Alice", "Alice", 30.0) in list(ledger.lending_triples())


class TestDescriptiveColumns:
    def test_optional_columns_are_picked_up(self, realistic):
        ledger = realistic.ledger
        first = ledger.entries[0]
        assert first.date == "2030-05-21"
        assert first.category == "交通"
        assert first.item == "交通-01"

    def test_every_entry_of_a_record_shares_its_description(self, realistic):
        ledger = realistic.ledger
        for _, entries in _grouped(ledger).items():
            assert len({(e.date, e.category, e.item) for e in entries}) == 1

    def test_categories_cover_the_whole_bill(self, realistic):
        """The category breakdown is only trustworthy if nothing falls outside it."""
        ledger = realistic.ledger
        assert all(e.category for e in ledger)

    def test_absent_columns_leave_none(self, tmp_path):
        ledger = ledger_of(SIMPLE, tmp_path)
        for entry in ledger:
            assert entry.date is None
            assert entry.category is None
            assert entry.item is None
            assert entry.currency_raw is None

    def test_currency_is_recorded_for_checking_against_receipts(self, tmp_path):
        ledger = ledger_of(
            "Creditor,Debtor,Amount,Currency\nAlice,Bob,3000,KRW\n", tmp_path
        )
        entry = ledger.entries[0]
        assert entry.currency_raw == "KRW"
        assert entry.amount_raw == 3000.0
        assert entry.amount_std == 3000.0  # no rates given: currency-agnostic


class TestFrame:
    def test_to_frame_round_trips_the_entries(self, tmp_path):
        ledger = ledger_of(SIMPLE, tmp_path)
        frame = ledger.to_frame()
        assert len(frame) == len(ledger)
        assert frame["share"].sum() == pytest.approx(140.0)
        assert set(frame["member"]) == {"Alice", "Bob", "Carol"}


class TestAgainstTheRealisticBill:
    def test_totals_reconcile_with_the_source_sheet(self, realistic):
        ledger = realistic.ledger
        assert len({e.record_id for e in ledger}) == 153
        sheet_total = realistic.loaded.raw_frame["金额"].sum()
        record_total = sum(amount for _, _, amount in ledger.records())
        assert record_total == pytest.approx(sheet_total, abs=0.005)

    def test_shares_reconcile_with_consumption(self, realistic):
        """Adding up a member's own rows must give the consumption they are shown.

        This is the check a suspicious member performs by hand, so it is the one
        that has to hold exactly.
        """
        from collections import defaultdict

        summed = defaultdict(float)
        for entry in realistic.ledger:
            summed[entry.member] += entry.share
        for name, stats in realistic.positions.items():
            assert summed[name] == pytest.approx(stats.consumption, abs=0.005), name


def _grouped(ledger):
    groups = {}
    for entry in ledger:
        groups.setdefault(entry.record_id, []).append(entry)
    return groups

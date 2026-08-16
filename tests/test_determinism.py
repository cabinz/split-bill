"""Test that identical input always produces identical output.

The settlement scheme is not unique: several schemes can share the same
(minimal) number of transactions. Which one ``simplest_equiv`` returns depends
on the order it walks creditors and debtors, which in turn used to depend on
the iteration order of the ``set`` of members -- and that follows
``PYTHONHASHSEED``, randomised per process by default. The same bill therefore
settled differently between runs.

These tests pin the ordering down. They are also what makes it meaningful to
compare outputs across versions at all: a snapshot of a non-reproducible
result cannot serve as a baseline.
"""

import os
import subprocess
import sys

import pytest

from tests.conftest import analyse, rows_to_csv


# Two net creditors and three net debtors, so the minimal scheme has several
# equally-short forms and the walk order actually decides between them.
BILL = """Creditor,Debtor,Amount,Currency
Alice,All,148,USD
Bob,All,89,USD
Carol,Dave,17.9,USD
Dave,"Alice, Bob",25.86,USD
Eve,All,31.5,USD
Alice,"Carol, Dave, Eve",40,USD
Bob,"Carol, Eve",22,USD
"""

HASH_SEEDS = ["0", "1", "2", "3", "42"]


@pytest.fixture
def bill_path(tmp_path):
    path = tmp_path / "bill.csv"
    path.write_text(BILL, encoding="utf-8")
    return str(path)


def bill(rows, tmp_path, **kwargs):
    """Load and settle a bill made of the given rows."""
    return analyse(rows_to_csv(rows), tmp_path, **kwargs)


class TestCliDeterminism:
    """End-to-end: the printed report must not vary with PYTHONHASHSEED."""

    def _run(self, bill_path, seed):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c",
             "from splitbill.__main__ import main; main()",
             "--file", bill_path, "--standard_currency", "USD"],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip(), "CLI produced no output"
        return proc.stdout

    def test_report_identical_across_hash_seeds(self, bill_path):
        outputs = {seed: self._run(bill_path, seed) for seed in HASH_SEEDS}
        first = outputs[HASH_SEEDS[0]]
        for seed, out in outputs.items():
            assert out == first, (
                f"output under PYTHONHASHSEED={seed} differs from "
                f"PYTHONHASHSEED={HASH_SEEDS[0]}"
            )

    def test_member_line_is_sorted(self, bill_path):
        out = self._run(bill_path, HASH_SEEDS[0])
        line = next(ln for ln in out.splitlines() if ln.startswith("Members:"))
        names = [n.strip() for n in line[len("Members:"):].split(",")]
        assert names == sorted(names)


class TestOrderingIsExplicit:
    """In-process: the orderings the report depends on are sorted, not incidental."""

    def test_all_selector_expands_in_sorted_order(self, tmp_path):
        """The debtor list an `all` row expands to drives edge insertion order."""
        b = bill(["Zoe,All,300,USD", "Alice,All,300,USD"], tmp_path)
        debtors = [e.debtor for e in b.settled.lending_edges if e.creditor == "Zoe"]
        assert debtors == sorted(debtors)

    def test_stats_break_net_ties_by_name(self, tmp_path):
        """Equal nets must not fall back on the aggregation's insertion order."""
        # Bob and Carol each consume 50 and pay nothing: identical net of -50.
        b = bill(["Alice,\"Bob, Carol\",100,USD"], tmp_path)
        assert list(b.positions) == ["Alice", "Bob", "Carol"]

    def test_everyone_on_an_edge_is_reported_in_sorted_order(self, tmp_path):
        b = bill(["Zoe,All,300,USD", "Alice,Bob,50,USD"], tmp_path)
        assert b.nodes() == sorted(b.nodes())

    def test_members_are_sorted(self, tmp_path):
        b = bill(["Zoe,All,300,USD", "Alice,Bob,50,USD"], tmp_path)
        assert list(b.members) == sorted(b.members)

    def test_repeated_loads_agree(self, tmp_path):
        """Same input, same process, loaded twice: identical settlement."""
        rows = BILL.strip().splitlines()[1:]

        def settled():
            return bill(rows, tmp_path).settled.settlement

        assert settled() == settled()

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
import tempfile

import pytest

from splitbill.loader import Loader, DataFormat


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


def make_loader(rows, header="Creditor,Debtor,Amount,Currency", **kwargs):
    """Build a Loader over a temporary CSV of the given rows."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                     encoding="utf-8") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")
        temp_path = f.name
    try:
        return Loader(temp_path, DataFormat(**kwargs))
    finally:
        os.unlink(temp_path)


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

    def test_all_selector_expands_in_sorted_order(self):
        """The debtor list an `all` row expands to drives edge insertion order."""
        loader = make_loader(["Zoe,All,300,USD", "Alice,All,300,USD"])
        edges = [debtor for debtor in loader.get_graph().get_edges("Zoe")]
        assert edges == sorted(edges)

    def test_stats_break_net_ties_by_name(self):
        """Equal nets must not fall back on `self._stats` insertion order."""
        # Bob and Carol each consume 50 and pay nothing: identical net of -50.
        loader = make_loader(["Alice,\"Bob, Carol\",100,USD"])
        stats = loader.get_member_stats()
        assert list(stats) == ["Alice", "Bob", "Carol"]

    def test_graph_nodes_are_sorted(self):
        loader = make_loader(["Zoe,All,300,USD", "Alice,Bob,50,USD"])
        nodes = loader.get_graph().get_nodes()
        assert nodes == sorted(nodes)

    def test_repeated_loads_agree(self):
        """Same input, same process, two Loaders: byte-identical settlement."""
        from splitbill.graph import simplest_equiv

        def settle():
            loader = make_loader([r for r in BILL.strip().splitlines()[1:]])
            return simplest_equiv(loader.get_graph()).dump().to_csv(index=False)

        assert settle() == settle()

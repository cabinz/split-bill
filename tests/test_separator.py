"""Test that a custom name separator is honoured everywhere names are split.

Reads the lending edges rather than a `LendingGraph`. Same facts -- who owes whom
how much before simplification -- but stated against layer 2's published output
instead of the data structure behind it, so splitting names stays checkable however
the graph is later implemented.
"""

from splitbill.settle.graph import is_equal
from tests.conftest import analyse, rows_to_csv


def bill(rows, tmp_path, **kwargs):
    return analyse(rows_to_csv(rows), tmp_path, **kwargs)


class TestCustomSeparator:
    """Test cases for splitting debtor names on a non-default separator."""

    def test_debtors_are_split_on_the_custom_separator(self, tmp_path):
        """Each name in the debtor cell becomes an edge of its own."""
        b = bill(["Alice,Bob;Charlie,100,USD"], tmp_path, separator=";")

        assert set(b.members) == {"Alice", "Bob", "Charlie"}
        assert len(b.settled.lending_edges) == 2
        assert is_equal(b.flow("Alice", "Bob"), 50)
        assert is_equal(b.flow("Alice", "Charlie"), 50)

    def test_no_edge_points_at_an_unsplit_name(self, tmp_path):
        """The whole debtor cell must not survive as a single phantom member."""
        b = bill(["Alice,Bob;Charlie,100,USD"], tmp_path, separator=";")

        assert "Bob;Charlie" not in b.nodes()
        assert set(b.nodes()) <= set(b.members)

    def test_net_flows_are_correct(self, tmp_path):
        """Splitting on the custom separator settles the right amounts."""
        b = bill(["Alice,Bob;Charlie,100,USD"], tmp_path, separator=";")

        assert is_equal(b.nets["Alice"], 100)
        assert is_equal(b.nets["Bob"], -50)
        assert is_equal(b.nets["Charlie"], -50)

    def test_creditor_in_debtor_list(self, tmp_path):
        """The creditor's own share is excluded, as with the default separator."""
        b = bill(["Alice,Alice;Bob,100,USD"], tmp_path, separator=";")

        assert len(b.settled.lending_edges) == 1
        assert is_equal(b.flow("Alice", "Bob"), 50)
        assert is_equal(b.nets["Alice"], 50)

    def test_all_selector_with_custom_separator(self, tmp_path):
        """The 'all' selector still expands to every member."""
        b = bill([
            "Alice,all,90,USD",
            "Bob,Charlie,30,USD",
        ], tmp_path, separator=";")

        assert set(b.members) == {"Alice", "Bob", "Charlie"}
        assert is_equal(b.flow("Alice", "Bob"), 30)
        assert is_equal(b.flow("Alice", "Charlie"), 30)

    def test_names_are_stripped(self, tmp_path):
        """Whitespace around a custom-separated name is trimmed."""
        b = bill(["Alice,Bob ; Charlie,100,USD"], tmp_path, separator=";")

        assert set(b.members) == {"Alice", "Bob", "Charlie"}
        assert is_equal(b.flow("Alice", "Bob"), 50)

    def test_default_separator_still_works(self, tmp_path):
        """The default comma path is unaffected."""
        b = bill(['Alice,"Bob, Charlie",100,USD'], tmp_path)

        assert set(b.members) == {"Alice", "Bob", "Charlie"}
        assert len(b.settled.lending_edges) == 2
        assert is_equal(b.flow("Alice", "Bob"), 50)
        assert is_equal(b.flow("Alice", "Charlie"), 50)

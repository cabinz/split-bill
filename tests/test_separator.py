"""Test that a custom name separator is honoured everywhere names are split."""

import pytest
import os
import tempfile
from splitbill.loader import Loader, DataFormat
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


class TestCustomSeparator:
    """Test cases for splitting debtor names on a non-default separator."""

    def test_debtors_are_split_on_the_custom_separator(self):
        """Each name in the debtor cell becomes an edge of its own."""
        loader = make_loader(["Alice,Bob;Charlie,100,USD"], separator=";")
        g = loader.get_graph()

        assert loader.get_members() == {"Alice", "Bob", "Charlie"}
        assert g.num_edges() == 2
        assert is_equal(g.get_flow("Alice", "Bob"), 50)
        assert is_equal(g.get_flow("Alice", "Charlie"), 50)

    def test_no_edge_points_at_an_unsplit_name(self):
        """The whole debtor cell must not survive as a single phantom member."""
        loader = make_loader(["Alice,Bob;Charlie,100,USD"], separator=";")
        g = loader.get_graph()

        assert "Bob;Charlie" not in g.get_nodes()
        assert set(g.get_nodes()) <= loader.get_members()

    def test_net_flows_are_correct(self):
        """Splitting on the custom separator settles the right amounts."""
        loader = make_loader(["Alice,Bob;Charlie,100,USD"], separator=";")
        net_out_flow = loader.get_graph().net_out_flow

        assert is_equal(net_out_flow["Alice"], 100)
        assert is_equal(net_out_flow["Bob"], -50)
        assert is_equal(net_out_flow["Charlie"], -50)

    def test_creditor_in_debtor_list(self):
        """The creditor's own share is excluded, as with the default separator."""
        loader = make_loader(["Alice,Alice;Bob,100,USD"], separator=";")
        g = loader.get_graph()

        assert g.num_edges() == 1
        assert is_equal(g.get_flow("Alice", "Bob"), 50)
        assert is_equal(g.net_out_flow["Alice"], 50)

    def test_all_selector_with_custom_separator(self):
        """The 'all' selector still expands to every member."""
        loader = make_loader([
            "Alice,all,90,USD",
            "Bob,Charlie,30,USD",
        ], separator=";")
        g = loader.get_graph()

        assert loader.get_members() == {"Alice", "Bob", "Charlie"}
        assert is_equal(g.get_flow("Alice", "Bob"), 30)
        assert is_equal(g.get_flow("Alice", "Charlie"), 30)

    def test_names_are_stripped(self):
        """Whitespace around a custom-separated name is trimmed."""
        loader = make_loader(["Alice,Bob ; Charlie,100,USD"], separator=";")

        assert loader.get_members() == {"Alice", "Bob", "Charlie"}
        assert is_equal(loader.get_graph().get_flow("Alice", "Bob"), 50)

    def test_default_separator_still_works(self):
        """The default comma path is unaffected."""
        loader = make_loader(['Alice,"Bob, Charlie",100,USD'])
        g = loader.get_graph()

        assert loader.get_members() == {"Alice", "Bob", "Charlie"}
        assert g.num_edges() == 2
        assert is_equal(g.get_flow("Alice", "Bob"), 50)
        assert is_equal(g.get_flow("Alice", "Charlie"), 50)

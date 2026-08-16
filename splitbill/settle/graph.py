"""Graph data structure for lending flows."""

from ..utils.logger import get_logger

from typing import List, Tuple
from collections import defaultdict
import math

logger = get_logger(__name__)

ABS_TOL = 1e-02


def is_equal(fp1, fp2):
    return math.isclose(fp1, fp2, abs_tol=ABS_TOL)


def is_zero(flt):
    return is_equal(flt, 0.0)


def is_exactly_zero(flt) -> bool:
    """Whether an accumulated edge has cancelled out completely.

    Distinct from `is_zero`, which is true anywhere within a cent of zero, and the
    difference is not pedantry -- see `LendingGraph.add_edge`.
    """
    return flt == 0.0


class LendingGraph:
    """A direct weighted graph, where weights are the lending flows."""

    def __init__(self, log=logger) -> None:
        self._adj_lt = defaultdict(lambda: defaultdict(float))
        self.net_out_flow = defaultdict(float)
        self.log = logger

    def vis(self) -> str:
        s = ""
        for creditor in self._adj_lt.keys():
            for debtor, amount in self._adj_lt[creditor].items():
                s += f"{creditor} --{amount:.2f}--> {debtor}\n"
        return s.strip()

    def get_nodes(self) -> List[str]:
        lt = set(self._adj_lt.keys())
        for creditor in self._adj_lt.keys():
            lt.update(list(self._adj_lt[creditor].keys()))
        return sorted(lt)

    def add_edge(self, creditor, debtor, amount) -> None:
        """Accumulate a lending amount, dropping the edge if it cancels out.

        `is_exactly_zero`, not `is_zero`, and this is the difference between a report
        that agrees with itself and one that does not.

        `remove_edge` undoes the edge's contribution to both endpoints' nets. When the
        edge really is zero -- A lent B 50, B lent A 50 -- that is exactly right and
        costs nothing: there is no obligation between them and nothing to display.

        When the edge is merely *near* zero, it is wrong. Layer 1 has already counted
        that share in somebody's consumption, so removing it from the graph's nets
        makes the two layers disagree by up to a cent per dropped edge -- and the
        report shows layer 1's figure while the settlement discharges layer 2's. A
        member is told they are owed 10,446.82 and given transfers adding to 10,446.80.

        Fuzz seed 1693 is that bill: `Carol,ALL,6,KRW` converts to 0.03 HKD and splits
        three ways, so two of the three edges are exactly one cent and `is_zero` --
        which uses `abs_tol` and is therefore true *at* one cent -- discarded both.

        The cost of keeping them is that a one-cent obligation now appears in
        `lending_edges` instead of vanishing. That is the truth about the bill, and the
        table it appears in is the one headed "who actually lent to whom".
        """
        assert (
            creditor != debtor
        ), f"creditor and debtor ({creditor}) should not be the same one!"
        self._adj_lt[creditor][debtor] += amount
        self.net_out_flow[creditor] += amount
        self.net_out_flow[debtor] -= amount
        if is_exactly_zero(self._adj_lt[creditor][debtor]):
            self.remove_edge(creditor, debtor)

    def has_edge(self, creditor, debtor) -> bool:
        return creditor in self._adj_lt and debtor in self._adj_lt[creditor]

    def get_edge(self, creditor, debtor) -> float:
        assert self.has_edge(creditor, debtor)
        return self._adj_lt[creditor][debtor]

    def get_edges(self, creditor) -> List[Tuple]:
        return self._adj_lt[creditor]

    def num_edges(self) -> int:
        return sum(len(self._adj_lt[creditor]) for creditor in self._adj_lt)

    def get_flow(self, creditor, debtor) -> float:
        return self._adj_lt[creditor][debtor] if self.has_edge(creditor, debtor) else 0.0

    def remove_edge(self, creditor, debtor) -> float:
        amount = self.get_edge(creditor, debtor)
        self._adj_lt[creditor].pop(debtor, None)
        self.net_out_flow[creditor] -= amount
        self.net_out_flow[debtor] += amount
        return amount

    def get_childs(self, node) -> List[str]:
        return list(self._adj_lt[node].keys()) if node in self._adj_lt else []

    def edges(self) -> List[Tuple[str, str, float]]:
        """Every edge as `(creditor, debtor, amount)`, in insertion order.

        Replaces the `dump()` that used to build a DataFrame here. Rendering a
        table is not a graph's job, and doing it here was the only reason this
        layer imported pandas -- which §4.5 forbids, so that the solver can be
        tested and reasoned about without a data-frame library in scope.
        `render/sheets.py` builds the frame now.
        """
        return [
            (creditor, debtor, amount)
            for creditor, children in self._adj_lt.items()
            for debtor, amount in children.items()
        ]

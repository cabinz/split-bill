"""Layer 2: turn lending relationships into the fewest transfers that clear them.

The entry point takes `(creditor, debtor, amount)` triples and nothing else. It
does not know what a spreadsheet is, what a currency is, or what a Ledger row
looks like -- which is the point. Layer 1 can be rewritten wholesale without this
layer, or the tests that pin its behaviour, noticing.

What comes back is deliberately two things at once:

    lending_edges   who actually fronted money for whom
    settlement      who should pay whom to make it all square

These differ, and not by accident. `simplest_equiv` throws away the pairings and
keeps only each member's net, then re-pairs the nets to minimise the number of
transfers. So a settlement routinely tells someone to pay a person they never
borrowed from. That is not a defect -- with n members you would otherwise need
far more than n-1 transfers -- but it is unexplainable from the settlement alone.
Returning both means the report can show them side by side, which is the whole
argument for why the settlement is legitimate.
"""

from dataclasses import dataclass

from .graph import LendingGraph
from .simplify import simplest_equiv

__all__ = ["Edge", "Transfer", "SettleResult", "settle"]


@dataclass(frozen=True)
class Edge:
    """A real obligation: `debtor` owes `creditor`, because the creditor paid.

    These are aggregated per pair across the whole bill, so one edge may stand
    for a dozen records.
    """

    creditor: str
    debtor: str
    amount: float


@dataclass(frozen=True)
class Transfer:
    """A payment the settlement asks for: `sender` pays `receiver`.

    Named for the action rather than for creditor/debtor on purpose. The
    counterparty here is a product of re-pairing nets and usually reflects no
    obligation between these two people; borrowing the lending vocabulary would
    imply one.
    """

    sender: str
    receiver: str
    amount: float


@dataclass(frozen=True)
class SettleResult:
    lending_edges: tuple[Edge, ...]
    """Aggregated real obligations, before simplification."""

    settlement: tuple[Transfer, ...]
    """The minimal set of payments that clears every net."""

    net_flows: dict[str, float]
    """Net outflow per member. Positive means the member is owed money.

    Insertion-ordered as the graph accumulated it, because that order is what the
    solver walks and therefore which of the equally-short schemes it returns.
    """


def settle(lendings) -> SettleResult:
    """Settle an iterable of `(creditor, debtor, amount)` triples.

    Self-loops are rejected rather than skipped: a member covering their own
    share is not an obligation, and dropping it is layer 1's job to do while it
    still knows the record it came from. A self-loop arriving here means the
    caller lost track of that, and silence would hide it.
    """
    graph = LendingGraph()
    for creditor, debtor, amount in lendings:
        graph.add_edge(creditor, debtor, amount)

    # `_adj_lt` rather than the sorted `get_nodes()`: insertion order decides
    # which minimal scheme comes out, so it is worth preserving. Reaching into it
    # from the package's own entry point is a good deal cheaper than widening
    # LendingGraph's API for one caller.
    lending_edges = tuple(
        Edge(creditor, debtor, amount)
        for creditor, children in graph._adj_lt.items()
        for debtor, amount in children.items()
    )

    equiv = simplest_equiv(graph)
    settlement = tuple(
        # An edge creditor -> debtor means the debtor owes; the payment runs the
        # other way.
        Transfer(sender=debtor, receiver=creditor, amount=amount)
        for creditor, children in equiv._adj_lt.items()
        for debtor, amount in children.items()
    )

    return SettleResult(
        lending_edges=lending_edges,
        settlement=settlement,
        net_flows=dict(graph.net_out_flow),
    )

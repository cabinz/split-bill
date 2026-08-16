"""Where each member stands: what they consumed, what they paid, the difference.

This is the part of the report a member can actually verify. The settlement is a
logistics problem once the nets are agreed, but the nets themselves have to be
believable, and `paid - consumption` is abstract enough that it invites doubt
rather than settling it.

So both framings are kept. `paid_for_others - covered_by_others` reaches the same
number by asking "how much of my money went on other people, and how much of
other people's money went on me" -- which is concrete, checkable against the
records, and points straight at the transfer that fixes it. That the two agree is
also a free correctness check, asserted per member in `aggregate()`.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict


@dataclass
class MemberStats:
    """Spending statistics of a single member over all the records.

    A record is fronted in full by its creditor, while its amount is shared
    evenly among the debtors listed on it (the creditor included, if listed).
    """

    consumption: float = 0.0
    """Own share of every record the member takes part in, i.e. the real cost."""

    paid: float = 0.0
    """Total amount the member actually paid out as a creditor."""

    paid_for_others: float = 0.0
    """The part of `paid` that covered other members' shares."""

    covered_by_others: float = 0.0
    """Own share that was fronted by other members."""

    @property
    def net(self) -> float:
        """Net outflow. Positive means the member is owed money by the others."""
        return self.paid - self.consumption


def aggregate(ledger, members) -> Dict[str, MemberStats]:
    """Fold a ledger into per-member positions.

    Args:
        ledger: The `Ledger` to aggregate.
        members: Everyone named in the bill. Used to seed the result, so a member
            who neither paid nor consumed anything still appears rather than
            silently vanishing from the report.

    Nothing here builds a graph or inspects one. The graph is layer 2's working
    representation; these four numbers come straight out of the ledger, and the
    fact that layer 2 independently arrives at the same nets is what makes the
    agreement worth checking (plan §4.7).
    """
    # Seeded in sorted order so the dict's key order -- which the statistics table
    # falls back on for members of equal net -- is the same on every run.
    stats: Dict[str, MemberStats] = defaultdict(
        MemberStats, {name: MemberStats() for name in sorted(members)})

    # What a creditor paid out is a fact about records, not about shares: folding
    # over entries would charge them once per participant.
    for _, creditor, amount_std in ledger.records():
        stats[creditor].paid += amount_std

    for entry in ledger:
        stats[entry.member].consumption += entry.share
        if not entry.is_own_share:
            stats[entry.creditor].paid_for_others += entry.share
            stats[entry.member].covered_by_others += entry.share

    _assert_nets_agree(stats)
    return stats


def _assert_nets_agree(stats: Dict[str, MemberStats]) -> None:
    """`paid - consumption` must equal `paid_for_others - covered_by_others`.

    Two routes to the same number, both shown in the report, so a member can
    check one against the other. If they ever disagree the report is telling a
    reader two different things and neither can be trusted, which is worth
    failing loudly over rather than rendering.

    The tolerance is a tenth of a cent: these are sums of the same floats added in
    different orders, so they agree far more closely than that, but they are not
    obliged to be bit-identical.
    """
    for name, s in stats.items():
        lending_view = s.paid_for_others - s.covered_by_others
        assert abs(s.net - lending_view) < 1e-3, (
            f"member {name}: paid - consumption = {s.net!r} but "
            f"paid_for_others - covered_by_others = {lending_view!r}"
        )

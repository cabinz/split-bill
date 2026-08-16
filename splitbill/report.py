"""The Report: what the three layers jointly produce, and the only thing layer 3
is allowed to see.

Plan §5. This is the contract between Python and anything that displays a bill --
the CLI tables, the CSV dumps, the JSON the browser reads. It carries a
`schema_version` because reports get archived, and one that cannot be opened six
months later is worse than useless.

It lives above the layers rather than inside `render/` because both `loader` and
`settle` contribute fields to it. Putting it under `render/` would have the data
layers importing the presentation layer, which is the dependency arrow §4.5 exists
to prevent.

What the structure insists on:

* `lending_edges` and `settlement` are both present, and named differently on
  purpose. The first is who really fronted money for whom; the second is who
  should pay whom, after the nets have been re-paired to minimise transfers. Shown
  side by side they explain each other, which is the one thing the V1 output could
  not do.
* `ledger` is the whole allocation, one row per person per record. Every summary
  above it is a group-by of it, so any figure in the report can be traced to the
  records it came from.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import json

import pandas as pd

from .loader import ColumnBinding, Ledger, LoadResult
from .settle import Edge, SettleResult, Transfer

SCHEMA_VERSION = "2.0"

# Reports are read by people checking arithmetic to the cent. Two decimals is what
# they see, so it is what gets serialised -- see §9.1 on why the rounding itself
# belongs in layer 1 rather than here.
MONEY_DP = 2


def _money(value: float) -> float:
    return round(float(value), MONEY_DP)


@dataclass(frozen=True)
class ReportMeta:
    """How this report was produced, in enough detail to reproduce it."""

    generated_at: str
    source_file: str
    std_currency: Optional[str]
    """None when running currency-agnostic. Everything downstream has to cope:
    amounts get no unit and the appendix shows no conversion column, because there
    was no conversion."""

    exchange_rates: Tuple[Tuple[str, str, float], ...]
    columns: Dict[str, ColumnBinding]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Summary:
    total_spend: float
    record_count: int
    member_count: int
    transaction_count: int


@dataclass(frozen=True)
class Position:
    """Where one member stands, with the two derivations of their net.

    Both are kept because they persuade differently. `paid - consumption` is
    correct but abstract; `paid_for_others - covered_by_others` says "you covered
    this much for other people, they covered this much for you, the difference is
    yours to settle", which is checkable against the records and points straight at
    the payment. They are the same number, and the report asserts as much.
    """

    member: str
    consumption: float
    paid: float
    paid_for_others: float
    covered_by_others: float
    net: float
    by_category: Dict[str, float]
    """Consumption split by category. Empty when the sheet had no category
    column, in which case the breakdown is simply not shown."""


@dataclass(frozen=True)
class Report:
    schema_version: str
    meta: ReportMeta
    members: Tuple[str, ...]
    summary: Summary
    positions: Tuple[Position, ...]
    """Net descending, the same order as the settlement table."""

    settlement: Tuple[Transfer, ...]
    lending_edges: Tuple[Edge, ...]
    ledger: Ledger

    raw_frame: Optional["pd.DataFrame"] = None
    """The sheet as read, plus the derived converted-total column.

    Not serialised -- `ledger` carries everything the JSON contract asks for. It
    travels for the appendix, which shows the bill in full including columns the
    tool never interprets, such as free-text notes. Dropping them would make the
    appendix a summary of the bill rather than the bill.
    """

    def to_dict(self) -> dict:
        """The §5 JSON structure.

        `settlement` is serialised with `from`/`to`, not `creditor`/`debtor`. The
        counterparty in a settlement is a by-product of re-pairing nets and usually
        reflects no debt between those two people; lending vocabulary would assert
        one, and that misreading is the confusion this report exists to remove.
        """
        return {
            "schema_version": self.schema_version,
            "meta": {
                "generated_at": self.meta.generated_at,
                "source_file": self.meta.source_file,
                "std_currency": self.meta.std_currency,
                "exchange_rates": [
                    {"base": base, "quote": quote, "rate": rate}
                    for base, quote, rate in self.meta.exchange_rates
                ],
                "columns": {
                    role: {"name": binding.name, "auto": binding.auto}
                    for role, binding in self.meta.columns.items()
                },
                "warnings": list(self.meta.warnings),
            },
            "members": list(self.members),
            "summary": {
                "total_spend": _money(self.summary.total_spend),
                "record_count": self.summary.record_count,
                "member_count": self.summary.member_count,
                "transaction_count": self.summary.transaction_count,
            },
            "positions": [
                {
                    "member": p.member,
                    "consumption": _money(p.consumption),
                    "paid": _money(p.paid),
                    "paid_for_others": _money(p.paid_for_others),
                    "covered_by_others": _money(p.covered_by_others),
                    "net": _money(p.net),
                    "by_category": {
                        category: _money(amount)
                        for category, amount in p.by_category.items()
                    },
                }
                for p in self.positions
            ],
            "settlement": [
                {"from": t.sender, "to": t.receiver, "amount": _money(t.amount)}
                for t in self.settlement
            ],
            "lending_edges": [
                {
                    "creditor": e.creditor,
                    "debtor": e.debtor,
                    "amount": _money(e.amount),
                }
                for e in self.lending_edges
            ],
            "ledger": [
                {
                    "record_id": entry.record_id,
                    "date": entry.date,
                    "category": entry.category,
                    "item": entry.item,
                    "creditor": entry.creditor,
                    "member": entry.member,
                    "share": _money(entry.share),
                    "amount_raw": _money(entry.amount_raw),
                    "currency_raw": entry.currency_raw,
                    "amount_std": _money(entry.amount_std),
                }
                for entry in self.ledger
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """`ensure_ascii=False`: member names and categories are routinely CJK, and
        a report full of \\uXXXX escapes is not one anybody can read."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# How far the two layers' nets may legitimately differ: float noise, and nothing else.
#
# This used to be `ABS_TOL * (member_count - 1)` -- up to a cent per member -- because
# `LendingGraph.add_edge` dropped any edge `is_zero` called zero, and `is_zero` uses
# `abs_tol`, so it was true *at* one cent. Dropping an edge also undoes its
# contribution to both endpoints' nets, while layer 1 had already counted that share.
# So the layers really did disagree by cents, and this allowance was what let the
# report be assembled anyway.
#
# It was also hiding the defect it was sized for. A member could be shown a net of
# 10,446.82 and handed transfers adding to 10,446.80, with nothing to say which was
# right. `add_edge` now drops an edge only when it has cancelled out exactly, so the
# disagreement is gone and the allowance for it went with it.
#
# Measured over 1,512 fuzzed bills after the fix: the worst gap is 4.7e-10, against
# nets of up to ~1e5. The absolute floor is 2,000x that; the relative term is there so
# a bill far larger than anything in the corpus cannot creep past it. Both are orders
# of magnitude below a cent, so §4.7's check now bites where it is supposed to -- a
# double-counted share is the size of a record and could never fit through this.
NET_FLOAT_TOL = 1e-6
NET_REL_TOL = 1e-9


def _net_tolerance(net: float = 0.0) -> float:
    """Slack for float addition, scaled to the magnitude being compared."""
    return max(NET_FLOAT_TOL, abs(net) * NET_REL_TOL)


def _by_category(ledger: Ledger) -> Dict[str, Dict[str, float]]:
    """member -> category -> consumption, from the ledger's own rows.

    Derived here rather than accumulated in layer 1 because it is just a group-by
    of the ledger, and adding a running total per category would be the same
    mistake V1 made with the shares: precompute the summary, discard the detail,
    and lose the ability to break it down any other way later.
    """
    totals: Dict[str, Dict[str, float]] = {}
    for entry in ledger:
        if entry.category is None:
            continue
        per_member = totals.setdefault(entry.member, {})
        per_member[entry.category] = per_member.get(entry.category, 0.0) + entry.share
    return totals


def build_report(
    loaded: LoadResult,
    settled: SettleResult,
    generated_at: Optional[str] = None,
) -> Report:
    """Assemble the two layers' output into one Report.

    This is the only place the layers meet, which makes it the only place the
    check in §4.7 can be made. Each member's net is computed twice over: layer 1
    subtracts consumption from what they paid, walking the ledger; layer 2 sums the
    graph's edges, and never imports `positions` or sees a ledger row. Two
    independent routes to the same number, so agreement is evidence rather than
    tautology -- and a mismatch means the report would be telling a member one
    thing and the settlement another.
    """
    for member, stats in loaded.positions.items():
        from_graph = settled.net_flows.get(member, 0.0)
        tolerance = _net_tolerance(stats.net)
        assert abs(stats.net - from_graph) <= tolerance, (
            f"member {member}: positions say net {stats.net!r}, "
            f"the lending graph says {from_graph!r} "
            f"(differ by {abs(stats.net - from_graph):.3e}, which is more than float "
            f"addition can account for -- these are two independent routes to the "
            f"same number and one of them is wrong)"
        )

    categories = _by_category(loaded.ledger)
    positions = tuple(
        Position(
            member=name,
            consumption=stats.consumption,
            paid=stats.paid,
            paid_for_others=stats.paid_for_others,
            covered_by_others=stats.covered_by_others,
            net=stats.net,
            by_category=categories.get(name, {}),
        )
        for name, stats in loaded.positions.items()
    )

    records = list(loaded.ledger.records())
    summary = Summary(
        total_spend=sum(amount for _, _, amount in records),
        record_count=len(records),
        member_count=len(loaded.members),
        transaction_count=len(settled.settlement),
    )

    meta = ReportMeta(
        generated_at=generated_at or datetime.now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds"),
        source_file=loaded.meta.source_file,
        std_currency=loaded.meta.std_currency,
        exchange_rates=loaded.meta.exchange_rates,
        columns=loaded.meta.columns,
        warnings=loaded.meta.warnings,
    )

    return Report(
        schema_version=SCHEMA_VERSION,
        meta=meta,
        members=loaded.members,
        summary=summary,
        positions=positions,
        settlement=settled.settlement,
        lending_edges=settled.lending_edges,
        ledger=loaded.ledger,
        raw_frame=loaded.raw_frame,
    )

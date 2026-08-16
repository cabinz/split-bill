"""The ledger: one row per person per record, saying what their share was.

This is the only genuinely new module in the Phase 0 refactor, and it exists
because V1 threw this table away. V1 computed each person's share inside a single
loop that also normalised names, accumulated statistics and built the graph, then
kept only the totals -- so the report could state what someone owed but never show
the records it came from.

Everything downstream is a group-by of this table: per-member drill-down, the
category breakdown, the appendix, the JSON export. Which is also why `date`,
`category` and `item` are carried along even though layer 2 never looks at them.

It is a `list` of entries rather than a DataFrame. A real bill is 153 records
across 7 people, so about a thousand rows; a Python loop over that is free, and
what it buys is entries that are typed, directly serialisable, and addressable by
attribute instead of by a column name assembled with an f-string. `to_frame()` is
there for when a group-by really is the clearest way to say something.
"""

import datetime
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

import pandas as pd

from ..utils.money import round_money, split_evenly
from .names import is_all_selector, split_names


@dataclass(frozen=True)
class LedgerEntry:
    """One member's share of one record."""

    record_id: int
    """1-based position of the record in the source sheet. With a header row
    present, the spreadsheet row is `record_id + 1`."""

    creditor: str
    """Who fronted the whole record."""

    member: str
    """Who this share belongs to."""

    share: float
    """The member's part of the record, in the standard currency."""

    amount_raw: float
    """The record's total as written in the sheet, before conversion."""

    amount_std: float
    """The record's total after conversion. Equal to `amount_raw` when running
    currency-agnostic."""

    is_own_share: bool
    """Whether this is the creditor covering their own part of what they paid.

    Not derivable from `member == creditor`, and that difference matters: V1
    dropped the creditor from the debtor list with `list.remove`, which removes
    only the first occurrence. A name written twice in one cell therefore leaves a
    second share that V1 still treated as lending. Recording the fact here keeps
    that behaviour exact instead of quietly correcting it.
    """

    currency_raw: Optional[str] = None
    date: Optional[str] = None
    category: Optional[str] = None
    item: Optional[str] = None


@dataclass(frozen=True)
class Ledger:
    """Every share of every record, in source order."""

    entries: Tuple[LedgerEntry, ...] = ()

    def __iter__(self) -> Iterator[LedgerEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def lending_triples(self) -> Iterator[Tuple[str, str, float]]:
        """`(creditor, debtor, amount)` triples for the settle layer.

        A creditor's own share is skipped: covering part of what you paid for
        yourself is not lending. Dropping it here rather than in the solver keeps
        that decision next to the record it concerns -- the solver has no way to
        tell an intentional omission from a mistake.
        """
        for entry in self.entries:
            if not entry.is_own_share:
                yield entry.creditor, entry.member, entry.share

    def records(self) -> Iterator[Tuple[int, str, float]]:
        """`(record_id, creditor, amount_std)` once per record, in source order.

        Every entry of a record carries the same creditor and total, so folding
        over entries would count a record once per participant. What a creditor
        paid out is a fact about records, not about shares.
        """
        seen = None
        for entry in self.entries:
            if entry.record_id != seen:
                seen = entry.record_id
                yield entry.record_id, entry.creditor, entry.amount_std

    def to_frame(self) -> pd.DataFrame:
        """The ledger as a DataFrame, for when a group-by says it best."""
        return pd.DataFrame([vars(entry) for entry in self.entries])


def _optional_text(row, column: Optional[str]) -> Optional[str]:
    """A cell's text, or None if the column is absent or the cell is blank."""
    if column is None or column not in row.index:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    return str(value).strip() or None


def _optional_date(row, column: Optional[str]) -> Optional[str]:
    """A cell's date as an ISO string, or None.

    Excel hands back a Timestamp where CSV hands back text, and the difference
    should not reach the report.
    """
    if column is None or column not in row.index:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime.datetime)):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value).strip() or None


def _allocate(amount: float, debtors: List[str]) -> List[float]:
    """Shares for `debtors`, in their listed order, summing exactly to `amount`.

    An amount rarely divides evenly into cents, so somebody gets the extra one. That
    is decided here rather than left to floating point, and decided the same way
    every time: the leftover cents go to the earliest-sorting names.

    Sorting by name rather than by position matters because the position is an
    accident of how a spreadsheet listed people. Two sheets with the same records in
    a different order would otherwise allocate the remainder differently and produce
    two reports that disagree by a cent -- which is exactly the kind of discrepancy
    nobody can explain and everybody notices.

    Ties keep their original position, so a name written twice is stable too.
    """
    shares = split_evenly(amount, len(debtors))
    by_name = sorted(range(len(debtors)), key=lambda i: (debtors[i], i))

    allocated = [0.0] * len(debtors)
    for rank, position in enumerate(by_name):
        allocated[position] = shares[rank]
    return allocated


def build_ledger(df: pd.DataFrame, cfg, members, std_amount_col: str) -> Ledger:
    """Allocate every record's amount across the members who shared it.

    Args:
        df: The bill, already read, amount-cleaned and carrying a converted total.
        cfg: The DataFormat naming the columns.
        members: Everyone named in the bill, used to expand a cell meaning
            "everyone".
        std_amount_col: Column holding the record total in the standard currency.

    The rules, unchanged from V1:

    * the creditor fronts the record in full, whoever ends up sharing it
    * the amount is split evenly across the debtor list, the creditor included
      when they are on it, so `len(debtors)` is taken before anyone is excluded
    * a name written twice in one cell gets two shares -- this is not filtered,
      because the sheet said what it said, and quietly halving somebody's share
      would be worse than the odd-looking total that follows from it
    """
    ordered_members = sorted(members)
    entries: List[LedgerEntry] = []

    for index, row in df.iterrows():
        creditor = row[cfg.col_creditor].strip()
        if is_all_selector(row[cfg.col_debtor]):
            # sorted(), not list(): iterating a set follows PYTHONHASHSEED, which
            # would make the share order -- and through it the settlement scheme
            # chosen among equally-minimal ones -- vary between runs.
            debtors = list(ordered_members)
        else:
            debtors = split_names(row[cfg.col_debtor], cfg.separator)

        # Snapped to the cent before splitting, so the total the appendix prints is
        # the number the shares beneath it add up to.
        amount_std = round_money(row[std_amount_col])
        shares = _allocate(amount_std, debtors)

        # Only the first occurrence, matching V1's `debtors.remove(creditor)`.
        own_share_at = debtors.index(creditor) if creditor in debtors else None

        record = dict(
            record_id=int(index) + 1,
            creditor=creditor,
            amount_raw=row[cfg.col_tot_amount],
            amount_std=amount_std,
            currency_raw=_optional_text(row, cfg.col_currency),
            date=_optional_date(row, cfg.col_date),
            category=_optional_text(row, cfg.col_category),
            item=_optional_text(row, cfg.col_item),
        )
        entries.extend(
            LedgerEntry(
                member=member,
                share=shares[position],
                is_own_share=(position == own_share_at),
                **record,
            )
            for position, member in enumerate(debtors)
        )

    return Ledger(tuple(entries))

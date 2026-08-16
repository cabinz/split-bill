"""Layer 1: read a bill and work out what each member consumed and paid.

Plan §4.2. Everything between the spreadsheet and the numbers lives here --
reading the file, detecting the columns, validating, splitting name cells,
expanding `all`, converting currencies, allocating each record's shares, and
aggregating those into per-member positions.

The layer's output has to carry the ledger itself, not just the per-member
totals. Totals are what layer 2 needs, but they are the end of a chain a member
has to be able to walk:

    each record (who fronted it, what my share was)
      -> what I consumed, what I paid
      -> my net
      -> everyone's nets sum to zero
      -> some set of transfers that clears them

Hand layer 3 only the nets and the report can state a conclusion without being
able to show any of the working. So the ledger travels intact, and category, item
and date travel with it -- layer 2 never looks at them, but the appendix and the
per-member drill-down are made of nothing else.

`load()` and `LoadResult` are the whole of this layer's public surface. The
`Loader` class that used to sit beside them was a compatibility shell, kept through
the refactor so the existing tests went on working while the module underneath them
was taken apart; it was deleted at step 0i along with the frozen V1 reference it
existed to be comparable with.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from ..config import DataColumn
from .exr import ExchangeRates
from .ledger import Ledger, build_ledger
from .names import collect_members
from .positions import MemberStats, aggregate
from .source import (ColumnBinding, DataFormat, clean_amount_column, read_sheet)
from .validator import DataValidator, ValidationResult

__all__ = [
    "ColumnBinding",
    "DataFormat",
    "order_by_net",
    "std_amount_column",
    "DataValidator",
    "ExchangeRates",
    "InvalidData",
    "Ledger",
    "LoadMeta",
    "LoadResult",
    "MemberStats",
    "ValidationResult",
    "clean_amount_column",
    "load",
    "read_sheet",
]


@dataclass(frozen=True)
class LoadMeta:
    """What layer 1 can say about how it read the bill."""

    source_file: str
    std_currency: Optional[str]
    """None when running currency-agnostic, which the report has to respect: with
    no standard currency there is nothing to label the amounts with."""

    exchange_rates: Tuple[Tuple[str, str, float], ...]
    """(base, quote, rate) as supplied, so the arithmetic can be rechecked."""

    columns: Dict[str, ColumnBinding]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadResult:
    """Layer 1's output: the ledger, the positions, and how they were arrived at.

    The ledger travels with the positions rather than being consumed into them.
    Layer 2 needs only the nets, but a net that cannot be traced back to records
    is a number a member is asked to take on trust, which is the thing V2 exists
    to stop doing.
    """

    ledger: Ledger
    positions: Dict[str, MemberStats]
    """Ordered by net descending, ties by name -- the order the report reads in."""

    members: Tuple[str, ...]
    meta: LoadMeta
    raw_frame: pd.DataFrame
    """The sheet as read. The appendix shows the bill in full, and the web view
    displays it immediately on import, so it has to survive to layer 3 intact."""

    validation: ValidationResult = field(default_factory=ValidationResult)


class InvalidData(Exception):
    """The bill cannot be interpreted. Carries the findings for reporting.

    Raised rather than returned so no caller can accidentally go on to read an
    empty ledger as though the bill were simply cheap.
    """

    def __init__(self, result: ValidationResult) -> None:
        super().__init__(f"{len(result.errors)} error(s) in the input data")
        self.result = result


def std_amount_column(exrs: Optional[ExchangeRates]) -> str:
    """Name of the derived column holding each record's converted total."""
    return "Total Amount" + (f" ({exrs.std_currency})" if exrs is not None else "")


def load(
    file_path,
    cfg: Optional[DataFormat] = None,
    exrs: Optional[ExchangeRates] = None,
    frame: Optional[pd.DataFrame] = None,
    validate: bool = True,
    source_name: Optional[str] = None,
) -> LoadResult:
    """Read a bill and work out where every member stands.

    Args:
        file_path: The bill. Only its name reaches the report.
        source_name: What to call the bill in the report, when that differs from the
            path it was read from. The web service stores an upload under a random
            token, so without this the report is headed `ioguva36Jgg….csv` instead of
            the name the user recognises.
        cfg: Which column means what. Defaults to the default names.
        exrs: Exchange rates. None runs currency-agnostic, converting nothing and
            labelling nothing -- which is the common case in practice.
        frame: An already-read sheet, so a caller that had to read it to detect
            columns need not read it twice. V1 read every bill twice for exactly
            that reason.
        validate: Whether to check the data first. Off only for callers that have
            already validated.

    Raises:
        InvalidData: if validation finds errors. Warnings do not stop a load; they
            are carried on the result for the caller to report.

    This function prints nothing. Progress belongs to whoever is driving -- the
    CLI wants it interleaved with its own output, the HTTP layer wants it as JSON,
    and a layer that decides for both makes one of them wrong.
    """
    cfg = cfg if cfg is not None else DataFormat()
    frame = read_sheet(file_path) if frame is None else frame

    # Comma thousand separators have to go before anything reads a number.
    clean_amount_column(frame, cfg.col_tot_amount)

    validation = ValidationResult()
    if validate:
        validation = DataValidator(frame, cfg, exrs).validate()
        if validation.has_errors():
            raise InvalidData(validation)

    std_col = std_amount_column(exrs)
    if exrs is not None:
        frame[std_col] = frame.apply(
            lambda row: exrs.to_std(row[cfg.col_currency], row[cfg.col_tot_amount]),
            axis=1,
        )
    else:
        frame[std_col] = frame[cfg.col_tot_amount]

    members = collect_members(frame, cfg)
    ledger = build_ledger(frame, cfg, members, std_col)
    positions = aggregate(ledger, members)

    meta = LoadMeta(
        source_file=source_name or Path(file_path).name,
        std_currency=exrs.std_currency if exrs is not None else None,
        exchange_rates=tuple(exrs.registered()) if exrs is not None else (),
        columns=dict(cfg.bindings),
        warnings=(),
    )
    return LoadResult(
        ledger=ledger,
        positions=order_by_net(positions),
        members=tuple(sorted(members)),
        meta=meta,
        raw_frame=frame,
        validation=validation,
    )


def order_by_net(positions: Dict[str, MemberStats]) -> Dict[str, MemberStats]:
    """Net descending, ties by name.

    Creditors first, then debtors, so the statistics table reads in the same
    direction as the settlement it is meant to justify. Ties break on name so the
    order never depends on how a dict happened to be filled.
    """
    return {
        name: stats
        for name, stats in sorted(positions.items(), key=lambda kv: (-kv[1].net, kv[0]))
    }

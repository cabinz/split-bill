"""Shared helpers for building a bill and reading the answer back.

Plan step 0i. The tests used to construct a `Loader` and pull results off it with
`get_ledger()` / `get_member_stats()` / `get_graph()`. That class was a compatibility
shell kept alive through the refactor so the existing tests could go on working while
the module under them was taken apart, and it is gone now: layer 1's entry point is
`load()` returning a `LoadResult`, and building the graph belongs to layer 2.

Everything here is a convenience over those two calls, nothing more. `analyse` is
what a caller actually does -- load, then settle -- and the rest are lookups that
several files wanted and would otherwise each define slightly differently.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import pytest

from splitbill.loader import DataFormat, ExchangeRates, LoadResult, load
from splitbill.settle import SettleResult, settle

FIXTURES = Path(__file__).parent / "fixtures"
REALISTIC_BILL = FIXTURES / "bill_realistic.csv"


def write_bill(csv: str, tmp_path: Path, name: str = "bill.csv") -> Path:
    """A bill on disk. `csv` is written verbatim, so it can be malformed on
    purpose."""
    bill = tmp_path / name
    bill.write_text(csv, encoding="utf-8")
    return bill


def rows_to_csv(rows, header: str = "Creditor,Debtor,Amount,Currency") -> str:
    """The row-list form several of these tests are written in."""
    return "".join([header + "\n"] + [row + "\n" for row in rows])


def cli_args(**overrides) -> Namespace:
    """The argparse namespace the CLI would build, for column auto-detection.

    Defaults to detecting everything, which is what the CLI does when given only a
    file. Override a `col_*` to pin one, as `--col_creditor` would.
    """
    args = dict(
        col_creditor=None,
        col_debtor=None,
        col_tot_amount=None,
        col_currency=None,
        separator=",",
        all_selector="all",
    )
    args.update(overrides)
    return Namespace(**args)


def load_bill(
    source,
    tmp_path: Optional[Path] = None,
    *,
    exrs: Optional[ExchangeRates] = None,
    detect: bool = False,
    validate: bool = True,
    **cfg_kwargs,
) -> LoadResult:
    """Load a bill, from a path or from CSV text.

    Args:
        source: A `Path` to an existing bill, or CSV text to write to `tmp_path`.
        tmp_path: Required when `source` is text.
        exrs: Exchange rates. None runs currency-agnostic.
        detect: Auto-detect the column names, as the CLI does. Off by default
            because most of these bills use the default names deliberately; on for
            the realistic fixture, whose columns are CJK and whose descriptive
            columns only appear when detection looks for them.
        validate: Passed through. Off for tests feeding data the validator would
            reject, which want to see what the loader makes of it anyway.
        **cfg_kwargs: Straight to `DataFormat` -- `separator`, `all_selector`, an
            explicit `col_*`. Cannot be combined with `detect`.
    """
    if isinstance(source, (str, bytes)) and not isinstance(source, Path):
        assert tmp_path is not None, "loading CSV text needs a tmp_path to write to"
        source = write_bill(source, tmp_path)

    if detect:
        assert not cfg_kwargs, "detect=True and explicit column names are exclusive"
        frame = pd.read_csv(source) if Path(source).suffix != ".xlsx" else pd.read_excel(source)
        cfg = DataFormat.from_args_with_auto_detect(cli_args(), frame)
    else:
        cfg = DataFormat(**cfg_kwargs)

    return load(source, cfg=cfg, exrs=exrs, validate=validate)


@dataclass(frozen=True)
class Bill:
    """A loaded and settled bill: layer 1's output and layer 2's, together.

    The pair a caller almost always wants, with the lookups they almost always
    want on top. Read-only -- it computes nothing that `load` and `settle` did not
    already return.
    """

    loaded: LoadResult
    settled: SettleResult

    @property
    def members(self) -> Tuple[str, ...]:
        return self.loaded.members

    @property
    def ledger(self):
        return self.loaded.ledger

    @property
    def positions(self):
        """Member -> MemberStats, net descending."""
        return self.loaded.positions

    @property
    def nets(self) -> Dict[str, float]:
        """Member -> net, from the graph. Layer 2's derivation, not layer 1's."""
        return self.settled.net_flows

    def flow(self, creditor: str, debtor: str) -> float:
        """What `debtor` owes `creditor` before simplification, 0.0 if nothing."""
        for edge in self.settled.lending_edges:
            if (edge.creditor, edge.debtor) == (creditor, debtor):
                return edge.amount
        return 0.0

    def edge_pairs(self) -> set:
        return {(e.creditor, e.debtor) for e in self.settled.lending_edges}

    def nodes(self) -> list:
        """Everyone on a lending edge, sorted. Not every member: somebody whose
        every share was their own appears nowhere in the lending graph."""
        named = {e.creditor for e in self.settled.lending_edges}
        named |= {e.debtor for e in self.settled.lending_edges}
        return sorted(named)

    def transfers(self) -> Tuple[Tuple[str, str, float], ...]:
        """The settlement as `(sender, receiver, amount)`."""
        return tuple((t.sender, t.receiver, t.amount) for t in self.settled.settlement)


def analyse(source, tmp_path: Optional[Path] = None, **kwargs) -> Bill:
    """Load and settle, which is what every caller of `load` goes on to do."""
    loaded = load_bill(source, tmp_path, **kwargs)
    return Bill(loaded=loaded, settled=settle(loaded.ledger.lending_triples()))


@pytest.fixture(scope="module")
def realistic() -> Bill:
    """The end-to-end fixture: 153 records, 7 members, CJK columns, no currency.

    Module-scoped -- it is read-only and several files use it more than once.
    """
    return analyse(REALISTIC_BILL, detect=True)

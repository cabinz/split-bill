"""Describing a bill, and running the CLI over it.

`Case` is a bill plus the options to read it with: inline CSV or a path, a
separator, an `all` spelling, a standard currency and rates. It knows how to write
itself to disk, and how to say what it would look like as CLI arguments or as an
argparse namespace, so one description drives both an in-process load and a
subprocess run.

This started life as the differential harness -- everything here was in service of
running the frozen V1 copy alongside the live package and comparing the two. That
comparison is finished (plan §4.10 for what it was for, tests/test_properties.py for
what replaced it), and what remains is the part that was always just about describing
bills and running the tool over them.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Case:
    """One bill, plus the options to read it with."""

    name: str
    csv: str | None = None
    """Inline CSV, written to a temporary file. Mutually exclusive with `path`."""
    path: str | None = None
    """An existing file, relative to the repo root (used for the .xlsx corpus)."""

    separator: str = ","
    all_selector: str = "all"
    std_currency: str | None = None
    rates: tuple[tuple[str, str, float], ...] = ()
    """(base, quote, rate) triples, as `--exchange_rate BASE/QUOTE=rate`."""

    columns: dict[str, str] = field(default_factory=dict)
    """Explicit column overrides. Anything absent is auto-detected, as the CLI does."""

    def materialize(self, tmp_dir: Path) -> Path:
        if self.path is not None:
            return REPO_ROOT / self.path
        assert self.csv is not None, f"case {self.name} has neither csv nor path"
        bill = tmp_dir / f"{self.name}.csv"
        bill.write_text(self.csv, encoding="utf-8")
        return bill

    def as_namespace(self) -> Namespace:
        """The argparse namespace the CLI would have built for this case."""
        return Namespace(
            col_creditor=self.columns.get("creditor"),
            col_debtor=self.columns.get("debtor"),
            col_tot_amount=self.columns.get("amount"),
            col_currency=self.columns.get("currency"),
            separator=self.separator,
            all_selector=self.all_selector,
        )

    def as_argv(self, bill: Path) -> list[str]:
        """The CLI arguments for this case."""
        argv = ["--file", str(bill)]
        for flag, key in (
            ("--col_creditor", "creditor"),
            ("--col_debtor", "debtor"),
            ("--col_tot_amount", "amount"),
            ("--col_currency", "currency"),
        ):
            if key in self.columns:
                argv += [flag, self.columns[key]]
        if self.separator != ",":
            argv += ["--separator", self.separator]
        if self.all_selector != "all":
            argv += ["--all_selector", self.all_selector]
        if self.std_currency:
            argv += ["--standard_currency", self.std_currency]
        for base, quote, rate in self.rates:
            argv += ["--exchange_rate", f"{base}/{quote}={rate}"]
        return argv


def read_frame(bill: Path) -> pd.DataFrame:
    """Read a bill the way the CLI reads it for column detection."""
    if bill.suffix == ".xlsx":
        return pd.read_excel(bill)
    if bill.suffix == ".tsv":
        return pd.read_csv(bill, sep="\t")
    return pd.read_csv(bill)


def analyse_case(case: Case, bill: Path):
    """Load and settle a `Case`, returning a `Report`.

    Goes through `pipeline` exactly as the CLI does, so a case description and a CLI
    run cannot drift apart in how they interpret the same options.
    """
    from splitbill import pipeline

    exrs = pipeline.exchange_rates_from_args(
        case.std_currency, [f"{b}/{q}={r}" for b, q, r in case.rates]
    )
    prepared = pipeline.prepare(bill, exrs=exrs, args=case.as_namespace())
    return pipeline.analyze(prepared)


def mask_figures(text: str) -> str:
    """Rendered output with every digit replaced by `#`.

    For comparing layout when the figures are expected to differ: the wording,
    column widths, row count and the alignment of CJK names in the box tables all
    still have to match.
    """
    return "".join("#" if character.isdigit() else character for character in text)


def settled_per_member(settlement) -> dict[str, float]:
    """member -> net amount a settlement moves to them (negative if they pay out).

    Takes `(receiver, sender, amount)` triples.
    """
    totals: dict[str, float] = {}
    for receiver, sender, amount in settlement:
        totals[receiver] = totals.get(receiver, 0.0) + amount
        totals[sender] = totals.get(sender, 0.0) - amount
    return totals


def settled_from_csv(text: str) -> dict[str, float]:
    """Per-member totals from a `--result_dump_path` CSV."""
    rows = list(csv.DictReader(io.StringIO(text)))
    return settled_per_member(
        (row["Creditor"], row["Debtor"], float(row[_amount_key(row)])) for row in rows
    )


def _amount_key(row: dict) -> str:
    """The amount column, named "Amount" or "Amount (HKD)" depending on the run."""
    return next(key for key in row if key and key.startswith("Amount"))


def render_cli(bill: Path, case: Case, *, module: str = "splitbill",
               extra_argv=()) -> str:
    """Run the CLI in a subprocess and return its stdout."""
    proc = subprocess.run(
        [sys.executable, "-c", f"from {module}.__main__ import main; main()"]
        + case.as_argv(bill)
        + list(extra_argv),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"{module} failed on {case.name}:\n{proc.stderr}"
    return proc.stdout


def dumped_csvs(bill: Path, case: Case, out_dir: Path, *,
                module: str = "splitbill") -> dict:
    """Run the CLI with both dump paths and read back what it wrote.

    The CSV files are an output nobody looks at until months later, when they are the
    only record of how a trip was settled.
    """
    result_path = out_dir / f"{module.replace('.', '_')}_result.csv"
    details_path = out_dir / f"{module.replace('.', '_')}_details.csv"
    render_cli(
        bill,
        case,
        module=module,
        extra_argv=["--result_dump_path", str(result_path),
                    "--details_dump_path", str(details_path)],
    )
    return {
        "result": result_path.read_text(encoding="utf-8"),
        "details": details_path.read_text(encoding="utf-8"),
    }

"""Wiring the three layers together, once, for everyone who needs it.

The CLI and the local web service both have to run the whole chain -- read,
detect, validate, allocate, settle, assemble. Written out at each entry point,
the two would drift, and then a bill would settle one way in the terminal and
another in the browser.

Split in two rather than offered as a single call, because the two halves are
genuinely different operations:

    prepare()  read, detect columns, validate. Computes nothing, decides nothing.
    analyze()  everything after that, ending in a Report.

Every caller wants that seam. The CLI reports which columns it detected and
whether validation passed *before* doing the work, and can stop at
`--validate-only`. §6's HTTP API splits along the same line: `POST /api/parse`
returns the detected columns and a preview so a wrong guess can be corrected in
the page, `POST /api/report` runs the rest. `analyze_file()` is there for callers
that want neither the seam nor the reporting.

Nothing here prints. Output is the caller's business, which is what lets the CLI
interleave its own lines in exactly the order it wants.
"""

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .loader import (DataFormat, DataValidator, ExchangeRates, ValidationResult,
                     load, read_sheet)
from .report import Report, build_report
from .settle import settle


@dataclass
class Prepared:
    """A bill read and checked, not yet interpreted.

    Holds the frame so the sheet is read exactly once: V1 read every bill twice,
    once to detect columns and once to work from.
    """

    file_path: Path
    frame: pd.DataFrame
    cfg: DataFormat
    exrs: Optional[ExchangeRates]
    validation: ValidationResult
    members: Tuple[str, ...] = ()
    """Names produced by the current separator, even when validation fails.

    The import UI shows this pre-analysis interpretation so a composite name such
    as ``Alice,Bob`` makes a wrong separator visible without invoking settlement.
    """

    source_name: Optional[str] = None
    """What to call the bill in the report, when the path is not it. The web service
    stores an upload under a random token, and a report headed with that token is a
    report nobody recognises."""

    @property
    def ok(self) -> bool:
        """Whether the bill can be interpreted. Warnings do not prevent it."""
        return not self.validation.has_errors()


def exchange_rates_from_args(standard_currency, rate_specs) -> Optional[ExchangeRates]:
    """Build an ExchangeRates from CLI-style `BASE/QUOTE=rate` strings.

    Returns None without a standard currency, which is the currency-agnostic mode:
    amounts are taken at face value and the report carries no unit.
    """
    if not standard_currency:
        return None
    exrs = ExchangeRates(standard_currency)
    for spec in rate_specs or []:
        base_quote, rate = spec.split("=")
        base, quote = base_quote.split("/")
        exrs.add_rate(base, quote, float(rate))
    return exrs


def prepare(
    file_path,
    cfg: Optional[DataFormat] = None,
    exrs: Optional[ExchangeRates] = None,
    args: Optional[Namespace] = None,
    source_name: Optional[str] = None,
) -> Prepared:
    """Read the bill, settle on the column names, and check the data.

    Args:
        file_path: The bill.
        cfg: An explicit column mapping. Takes precedence over `args`.
        exrs: Exchange rates, or None for currency-agnostic.
        args: CLI-style arguments to auto-detect columns from, used when `cfg` is
            not given.
        source_name: What the report should call the bill, when that is not the name
            of the file it was read from.

    Validation findings are returned rather than raised. The CLI wants to print
    them and stop; the web layer wants to hand them back with the detected columns
    so they can be corrected in the page. Deciding here would rule out one of them.
    """
    frame = read_sheet(file_path)
    if cfg is None:
        cfg = (DataFormat.from_args_with_auto_detect(args, frame)
               if args is not None else DataFormat())

    # Thousand separators go before anything reads a number, validation included.
    from .loader import clean_amount_column
    clean_amount_column(frame, cfg.col_tot_amount)

    validator = DataValidator(frame, cfg, exrs)
    validation = validator.validate()

    return Prepared(
        file_path=Path(file_path),
        frame=frame,
        cfg=cfg,
        exrs=exrs,
        validation=validation,
        members=tuple(sorted(validator.members)),
        source_name=source_name,
    )


def analyze(prepared: Prepared, generated_at: Optional[str] = None) -> Report:
    """Turn a prepared bill into a Report.

    Raises:
        ValueError: if validation found errors. Interpreting a bill that failed
            validation produces figures that look authoritative and are not.
    """
    if not prepared.ok:
        raise ValueError(
            f"cannot analyze: {len(prepared.validation.errors)} validation error(s)"
        )

    loaded = load(
        prepared.file_path,
        cfg=prepared.cfg,
        exrs=prepared.exrs,
        frame=prepared.frame,
        validate=False,  # prepare() already did, and did it on this same frame
        source_name=prepared.source_name,
    )
    settled = settle(loaded.ledger.lending_triples())
    return build_report(loaded, settled, generated_at=generated_at)


def analyze_file(
    file_path,
    cfg: Optional[DataFormat] = None,
    exrs: Optional[ExchangeRates] = None,
    args: Optional[Namespace] = None,
    generated_at: Optional[str] = None,
    source_name: Optional[str] = None,
) -> Report:
    """prepare() then analyze(), for callers with nothing to say in between."""
    return analyze(
        prepare(file_path, cfg=cfg, exrs=exrs, args=args, source_name=source_name),
        generated_at=generated_at,
    )

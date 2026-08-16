"""Shaping what the browser reads.

Two payloads, matching the two things the page does. Importing a bill has to show
what was found without committing to it -- which columns detection picked, what the
sheet actually contains, what the validator objected to -- and asking for a report
runs the arithmetic.

Everything here turns objects into plain dicts and nothing else: no HTTP, no files,
no pipeline. `serve.py` does that, and lives above the layers because it has to. This
module obeys §4.5 like the rest of `render` -- it sees a `Report` and the odds and
ends `serve` hands it, and reaches for nothing itself. Which is what makes it
testable without a socket, and what stops the browser and the terminal ending up with
two different ideas of what somebody owes.
"""

from typing import Any, Dict, List, Optional


def report_payload(report, sheet_rows: Optional[int] = None) -> Dict[str, Any]:
    """The §5 report, plus the sheet as it was read.

    The sheet travels alongside rather than inside: `Report.to_dict()` is a
    versioned contract that gets archived, and it deliberately leaves `raw_frame`
    out because `ledger` already carries every figure derived from it. But the
    appendix has to show the bill *in full* -- including columns the tool never
    looked at, like a free-text notes column -- or it is a summary of the bill
    rather than the bill. So it is a sibling key, and the contract stays untouched.

    Args:
        report: The Report to serialise.
        sheet_rows: Truncate the sheet to this many rows. None sends all of them,
            which is what the appendix needs.
    """
    return {
        "report": report.to_dict(),
        "sheet": sheet_payload(report.raw_frame, limit=sheet_rows),
    }


def parse_payload(
    *,
    source_file: str,
    columns: Dict[str, Any],
    frame,
    validation,
    std_currency: Optional[str] = None,
    exchange_rates=(),
    members=(),
    base_amounts=(),
) -> Dict[str, Any]:
    """What the page shows after an import, before anything is computed.

    Deliberately not a Report. A bill whose creditor column was guessed wrong still
    has to be displayable -- that is the whole reason `/api/parse` exists as its own
    endpoint, so a wrong guess can be corrected in the page instead of on a command
    line. `ok` says whether asking for a report would succeed.
    """
    return {
        "ok": not validation.has_errors(),
        "source_file": source_file,
        "std_currency": std_currency,
        "exchange_rates": [
            {"base": base, "quote": quote, "rate": rate}
            for base, quote, rate in exchange_rates
        ],
        "columns": columns_payload(columns),
        # Import is a confirmation step, not a sample of the data. Send the full
        # source sheet so every row can be inspected before the input is frozen.
        "sheet": sheet_payload(frame),
        "findings": findings_payload(validation),
        "members": list(members),
        "base_amounts": list(base_amounts),
    }


def columns_payload(columns: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """role -> {name, auto}, as `meta.columns` in the §5 contract.

    `auto` is the difference between a guess and an instruction, and the page needs
    it: a detected column is something to show the user and let them override, one
    they named is not up for discussion.
    """
    return {
        role: {"name": binding.name, "auto": binding.auto}
        for role, binding in columns.items()
    }


def sheet_payload(frame, limit: Optional[int] = None) -> Dict[str, Any]:
    """A DataFrame as `{columns, rows, total_rows, truncated}`.

    Rows are lists rather than dicts: a bill can have duplicate or blank column
    names, and keying by them would silently drop cells. `total_rows` is the real
    count even when `rows` is truncated, so the page can say what it is not showing.

    NaN becomes None. `json.dumps` writes bare `NaN` for a float nan, which is valid
    JavaScript and invalid JSON -- `JSON.parse` rejects it, so the page would fail to
    load a bill with one empty cell in a column the tool never uses.
    """
    if frame is None:
        return {"columns": [], "rows": [], "total_rows": 0, "truncated": False}

    import pandas as pd

    shown = frame if limit is None else frame.head(limit)
    rows: List[List[Any]] = []
    for record in shown.itertuples(index=False, name=None):
        rows.append([_jsonable(value, pd) for value in record])

    return {
        "columns": [str(column) for column in frame.columns],
        "rows": rows,
        "total_rows": int(len(frame)),
        "truncated": limit is not None and len(frame) > limit,
    }


def findings_payload(validation) -> Dict[str, List[Dict[str, Any]]]:
    """Validator output as JSON, keeping errors and warnings apart.

    The distinction is the point: an error means no report can be produced, a warning
    means one can and something in it is worth a second look. Collapsing them into
    one list would leave the page unable to say which.
    """
    return {
        "errors": [_finding(f) for f in validation.errors],
        "warnings": [_finding(f) for f in validation.warnings],
    }


def _finding(finding) -> Dict[str, Any]:
    return {
        "row": finding.row,
        "column": finding.column,
        "message": finding.message,
    }


def _jsonable(value, pd):
    """One cell, as something `json.dumps` can write and `JSON.parse` can read."""
    if value is None:
        return None
    # Timestamps first: pd.isna on some scalars returns an array.
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    # numpy scalars, Decimal, datetime.date, anything else the sheet held.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    return str(value)

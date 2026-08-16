"""CSV output, built from a Report.

These are the `--result_dump_path` and `--details_dump_path` files. They used to be
produced by reaching into whatever object happened to be at hand -- the settlement
frame came off `LendingGraph.dump()`, the details frame off the loader's internal
DataFrame -- which is why `dump()` lived on a graph in the first place and dragged
pandas into the settle layer with it.

Both are now group-bys of the Report, so the CSVs cannot disagree with what the
terminal printed.
"""

import pandas as pd


def settlement_frame(report) -> pd.DataFrame:
    """The settlement as a frame, with the same column names the CLI prints.

    The amount column carries the currency in its name when there is one, so a
    file that outlives this terminal session still says what unit it is in.
    """
    col_amount = amount_column_label(report.meta.std_currency)
    frame = pd.DataFrame(
        [
            {
                "Creditor": transfer.receiver,
                "Debtor": transfer.sender,
                col_amount: round(transfer.amount, 2),
            }
            for transfer in report.settlement
        ],
        columns=["Creditor", "Debtor", col_amount],
    )
    return frame.astype({"Creditor": "object", "Debtor": "object",
                         col_amount: "float64"})


def amount_column_label(std_currency) -> str:
    """"Amount (HKD)", or plain "Amount" when running currency-agnostic."""
    return f"Amount ({std_currency})" if std_currency is not None else "Amount"


def dump_settlement(report, path) -> None:
    settlement_frame(report).to_csv(path)


def dump_details(report, path) -> None:
    """The bill as read, plus the converted totals.

    Written from `raw_frame` rather than from the ledger: this file is for checking
    the tool's arithmetic against the original sheet, so it has to include the
    columns the tool never looked at.
    """
    report.raw_frame.to_csv(path)


def dump_ledger(report, path) -> None:
    """The per-share allocation, one row per person per record.

    The detail behind every figure in the report, in the form a spreadsheet can
    pivot. Nothing in V1 could produce this.
    """
    report.ledger.to_frame().to_csv(path, index=False)

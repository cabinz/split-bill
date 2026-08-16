"""CLI entry of the package."""

from .config import *
from .loader.source import SUPPORT_FTYPES
from .render import sheets
from .render.text import format_transaction_table, format_member_stats_table
from . import pipeline

import argparse
from pathlib import Path
import sys

SPLIT_LN = "=" * 20


def main(argv=None):
    """Run the CLI.

    `splitbill serve` is handled before argparse rather than as a subparser. Adding
    subcommands properly would make `--file` sit under one, and every invocation
    anybody has written down -- README, samples/run.sh, the Makefile, whatever is in
    somebody's shell history -- says `splitbill --file ...` with no subcommand at all.
    A new verb is not worth breaking those for.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "serve":
        return _serve(argv[1:])

    parser = argparse.ArgumentParser(
        'SplitBill',
        description="Split a group bill into the fewest transfers that settle it. "
                    "Run `splitbill serve` for the web interface.",
    )

    parser.add_argument(
        "--file",
        help="Path to the data file.", required=True
    )
    parser.add_argument(
        "--col_creditor",
        default=None,
        help=f'Column name for creditors in the sheet. Auto-detected if not specified.',
    )
    parser.add_argument(
        "--col_debtor",
        default=None,
        help=f'Column name for debtors in the sheet. Auto-detected if not specified.',
    )
    parser.add_argument(
        "--col_tot_amount",
        default=None,
        help=f"Column name for total lending amount (from the creditor) in the sheet. Auto-detected if not specified.",
    )
    parser.add_argument(
        "--col_currency",
        default=None,
        help=f"Column name for transation currency. Auto-detected if not specified.",
    )

    parser.add_argument(
        "--separator", 
        default=DEFAULT_SEP, 
        help=f"Separator for splitting names in a cell. Default as comma '{DEFAULT_SEP}'."
    )
    parser.add_argument(
        "--all_selector", 
        default=DEFAULT_ALL_SELECTOR, 
        help=f"String specifying all members memtioned in the data. Default as '{DEFAULT_ALL_SELECTOR}'."
    )
    
    parser.add_argument(
        "--standard_currency",
        type=str,
        help='The currency for settlement (ie., to be displayed in results). eg., "HKD".',
    )
    parser.add_argument(
        "--exchange_rate",
        type=str,
        action="append",
        help="Exchange rate. BASE/QUOTE=x means 1 BASE is converted to x QUOTE. eg., USD/HKD=7.8",
    )
    
    parser.add_argument(
        "--result_dump_path",
        type=str,
        help='File path to dump the output sheet. eg. "path/to/out.csv".',
    )
    parser.add_argument(
        "--details_dump_path",
        type=str,
        help='File path to dump the detailed preprocessed record sheet. eg. "path/to/details.csv".',
    )
    parser.add_argument(
        "--ledger_dump_path",
        type=str,
        help='File path to dump the per-share allocation, one row per person per '
             'record. eg. "path/to/ledger.csv".',
    )
    parser.add_argument(
        "--json_dump_path",
        type=str,
        help='File path to dump the whole report as JSON. eg. "path/to/report.json". '
             'This is the same structure the web view reads.',
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the input data without processing.",
    )

    args = parser.parse_args(argv)

    ########################################
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist")
        sys.exit(1)

    file_type = file_path.suffix
    if file_type not in SUPPORT_FTYPES:
        print(f"Error: Unsupported file format {file_type}. Supported formats: {', '.join(SUPPORT_FTYPES.keys())}")
        sys.exit(1)

    # Setup exchange rates
    exrs = pipeline.exchange_rates_from_args(
        args.standard_currency, args.exchange_rate)
    if exrs is not None:
        print(f"Standard currency for results: {args.standard_currency}")
        # Echoed from the argument as typed, not from the parsed float, so the
        # number shown back is the number the user entered.
        for spec in args.exchange_rate or []:  # spec = 'BASE/QUOTE=x'
            base_quote, rate = spec.split("=")
            base, quote = base_quote.split("/")
            print(f"Registered exchange rate {base}/{quote} = {rate}")

    # Read, detect columns, validate. Nothing is computed yet, which is what lets
    # --validate-only stop here and what the web layer's /api/parse returns.
    prepared = pipeline.prepare(args.file, exrs=exrs, args=args)

    # Reporting detection is the caller's job, not layer 1's. Only the four
    # settlement-critical roles are announced: the descriptive columns cannot stop
    # a bill from settling, so naming them would be noise about no decision.
    for role in ("creditor", "debtor", "amount", "currency"):
        binding = prepared.cfg.bindings[role]
        if binding.auto:
            print(f"✓ Auto-detected {role} column: '{binding.name}'")

    if prepared.validation.has_errors() or prepared.validation.has_warnings():
        prepared.validation.print_summary()
        if prepared.validation.has_errors():
            print("\nData validation failed. Please fix the errors above.")
            sys.exit(1)
    else:
        print("✓ Data validation passed.")

    # If validate-only flag is set, exit after validation
    if args.validate_only:
        sys.exit(0)

    print("")  # Empty line for separation

    report = pipeline.analyze(prepared)

    for warning in report.meta.warnings:
        print(warning)

    print(f"Members:", ", ".join(report.members))
    print(SPLIT_LN)

    print("Spending of each member:")
    print(format_member_stats_table(
        {p.member: p for p in report.positions}, args.standard_currency))
    print("  Consumption:     own share of the records the member takes part in")
    print("  Paid:            amount actually paid out as a creditor")
    print("  Paid for Others: the part of Paid covering other members' shares")
    print("  Net:             Paid - Consumption; positive means being owed money")
    print(SPLIT_LN)

    # Display transaction count in the title
    transaction_count = report.summary.transaction_count
    print(f"Simplest bill splitting scheme: (with {transaction_count} transaction{'s' if transaction_count != 1 else ''})")

    # Format and display the table (which says so itself when there is nothing to do)
    print(format_transaction_table(
        report.settlement, sheets.amount_column_label(report.meta.std_currency)))

    if args.result_dump_path is not None:
        sheets.dump_settlement(report, args.result_dump_path)
        print(f"Results are dumped to {args.result_dump_path}")
    if args.details_dump_path is not None:
        sheets.dump_details(report, args.details_dump_path)
        print(f"Proprocessing details are dumped to {args.details_dump_path}")
    if args.ledger_dump_path is not None:
        sheets.dump_ledger(report, args.ledger_dump_path)
        print(f"Per-share ledger is dumped to {args.ledger_dump_path}")
    if args.json_dump_path is not None:
        Path(args.json_dump_path).write_text(report.to_json(), encoding="utf-8")
        print(f"Report JSON is dumped to {args.json_dump_path}")


def _serve(argv):
    """`splitbill serve [--develop] [--port N] [--no-browser]`."""
    from . import serve as serve_module

    parser = argparse.ArgumentParser(
        "splitbill serve",
        description="Serve the web interface on localhost. Bound to loopback only, "
                    "with no authentication -- see the README.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=serve_module.DEFAULT_PORT,
        help=f"Port to listen on. Default {serve_module.DEFAULT_PORT}. "
             f"0 asks the OS for a free one.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser window.",
    )
    parser.add_argument(
        "--develop", "--dev",
        action="store_true",
        help="Run the Vite frontend with hot module replacement and restart the "
             "Python API when backend source files change.",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=serve_module.DEFAULT_FRONTEND_PORT,
        help="Vite port used with --develop. "
             f"Default {serve_module.DEFAULT_FRONTEND_PORT}.",
    )
    args = parser.parse_args(argv)

    try:
        if args.develop:
            return serve_module.serve_development(
                port=args.port,
                frontend_port=args.frontend_port,
                open_browser=not args.no_browser,
            )
        serve_module.serve(port=args.port, open_browser=not args.no_browser)
    except serve_module.DevelopmentError as exc:
        print(f"Error: {exc}")
        return 1
    except OSError as exc:
        # Almost always the port being taken, which is worth saying plainly
        # rather than as a traceback.
        print(f"Error: could not listen on port {args.port}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

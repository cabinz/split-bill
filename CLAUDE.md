# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SplitBill is a Python-based bill splitting tool designed for group trips. It processes payment records from data sheets (.xlsx, .csv, .tsv) and generates an optimized repayment scheme with the minimum number of transactions. The tool supports multiple currencies with exchange rate conversion.

## Key Commands

### Installation
```bash
# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

### Running Tests
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_auto_detect.py -v

# Run the settlement algorithm's correctness suite
uv run pytest tests/test_graph_correctness.py -v
```

### Running the CLI tool
```bash
# Basic usage with auto-detection (detects Payer/Payee or Creditor/Debtor columns)
uv run splitbill \
    --file "path/to/data.xlsx" \
    --standard_currency "HKD" \
    --exchange_rate "KRW/HKD=0.0057715"

# With custom column names (overrides auto-detection)
uv run splitbill \
    --file "path/to/data.xlsx" \
    --col_creditor "From" \
    --col_debtor "To" \
    --col_tot_amount "Value" \
    --standard_currency "CNY" \
    --exchange_rate "HKD/CNY=0.9177"

# Validate data without processing
uv run splitbill \
    --file "path/to/data.xlsx" \
    --standard_currency "USD" \
    --validate-only
```

### Development
```bash
# Install in editable mode for development
uv pip install -e .

# Run the module directly with uv
uv run python -m splitbill --file "samples/sample_data.xlsx" --standard_currency "HKD"

# Run sample script
uv run bash samples/run.sh
```

## Architecture

### Core Components

1. **CLI Entry Point** (`splitbill/__main__.py`)
   - Parses command-line arguments
   - Coordinates data loading, graph processing, and result output
   - Handles exchange rate registration

2. **Data Loading** (`splitbill/loader.py`)
   - `Loader` class: Loads and preprocesses transaction data from spreadsheets
   - `DataFormat` class: Encapsulates column naming and data format configuration
     - Auto-detects column names (Payer/Payee or Creditor/Debtor)
     - Case-insensitive column detection
     - Supports mixed column combinations (e.g., Payer + Debtor)
   - Supports CSV, TSV, and Excel formats
   - Handles member extraction and transaction normalization

3. **Graph Processing** (`splitbill/graph.py`)
   - `LendingGraph` class: Represents lending relationships as a directed weighted graph
   - Implements graph simplification algorithm to minimize transactions
   - Tracks net cash flows for each participant
   - `simplest_equiv()` function: Core algorithm for finding optimal repayment scheme

4. **Exchange Rates** (`splitbill/exr.py`)
   - `ExchangeRates` class: Manages currency conversion
   - Supports multiple exchange rate pairs
   - Converts all amounts to a standard currency for settlement

5. **Configuration** (`splitbill/config.py`)
   - Column name aliases for auto-detection
   - All selector aliases ("all", "*", "ALL", "All")
   - Default column names and separators
   - Configurable via CLI arguments

6. **Data Validation** (`splitbill/validator.py`)
   - Validates data structure and required columns
   - Checks for missing or invalid values
   - Validates currency exchange rates
   - Provides helpful error messages with column name suggestions

### Data Flow

1. User provides spreadsheet with transaction records (Creditor, Debtor, Amount, Currency)
2. Loader reads and preprocesses data, expanding "all" selector to actual members
3. Exchange rates convert all amounts to standard currency
4. Graph structure captures all lending relationships
5. Simplification algorithm reduces to minimum transactions
6. Results displayed and optionally exported to CSV

### Key Implementation Details

- **Auto-detection**: The system automatically detects column names from predefined aliases
  - Creditor columns: "Creditor", "Payer"
  - Debtor columns: "Debtor", "Payee"
  - Amount columns: "Amount", "Total"
  - Currency columns: "Currency", "Curr"
- **All selector flexibility**: Supports multiple formats ("all", "*", "ALL", "All") for indicating all members
- The graph simplification algorithm works by matching creditors and debtors to minimize the total number of transactions
- Members can be specified individually or using an "all" selector
- Multiple people can be listed in a single cell, separated by comma (customizable separator)
- The system maintains floating-point tolerance (ABS_TOL = 1e-02) for amount comparisons

## The web interface

Source in `webui/`, built output committed to `splitbill/render/webui/` (that is
deliberate — see README). Rebuild with `make webui` after any change under
`webui/src/`; `tests/test_webui_build.py` fails if the build is older than the source.

The frontend is two views over one report, and the boundary matters more than the file
layout:

```text
webui/src/presentation/   shared. Formatting, i18n, chart options, read-only selectors.
webui/src/screen/         the interactive page. Its own DOM and stylesheet.
webui/src/print/          the printed report. Its own DOM and stylesheet.
```

Rules this rests on, all of them checked by
`tests/test_webui_build.py::TestTheTwoViewsAreActuallySeparate`:

- `presentation/` imports neither view. Anything that decides *what* a figure says
  lives there, so the screen and the paper cannot disagree.
- `print/` never imports from `screen/`.
- `screen/` may import only `print/controller`, `print/PrintHost.vue` and
  `print/channel` — enough to start a print, not enough to render a print section
  inside the page.
- Neither view reads the other's DOM.
- No `<details>` in the print view and no `beforeprint` handler anywhere. A closed
  `<details>` renders none of its contents, so anything inside one is missing from the
  printed page; the old code opened them all on `beforeprint` and put them back, which
  made the printed report's completeness depend on a DOM mutation landing before a
  blocking call.

Neither view computes anything. Every amount comes from Python; the shared layer only
groups, sorts and formats. A sum in `presentation/` is only ever a sum of figures
Python already produced.

Printing does not disturb the page. The print view is mounted off-screen whenever a
report exists — so the browser's own Ctrl-P prints the report rather than a blank sheet
— and **Print** freezes a deep copy of the report plus the export options and renders
that. `structuredClone` cannot clone a Vue proxy, so `freeze()` calls `toRaw` first;
without it the print view silently never mounts.

Tests:

```bash
make webui-test    # unit tests for the shared layer, no browser
make webui-check   # build, unit tests, then four browser suites
```

`webui/e2e/print.mjs` is the one to run after touching either view: it reads both DOMs
with the same function and asserts every figure is identical, including a digest of all
668 ledger rows, then checks print completeness and that screen state cannot reach the
printed report.

## Important Notes

- The `tests/` directory contains pytest unit and integration tests
- `tests/fixtures/bill_realistic.csv` is a real trip bill run through
  `tools/anonymize_bill.py`: names, items and dates are rewritten, every amount
  and debtor grouping is untouched, so its figures are the real ones relabelled.
  It is the end-to-end baseline -- 153 records, 7 members, CJK columns, no
  currency column
- Real bills live in `fcbk/`, which is gitignored. Never commit one
- The project uses Python 3.10+ features
- All currency conversions are applied before graph simplification
- The tool is read-only on input files and only writes to specified output paths
- Column name detection is case-insensitive and prioritizes user-specified values over auto-detection
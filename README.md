# Split Bill

SplitBill turns a spreadsheet of who-paid-for-what into the fewest transfers that
settle it, and into a report each member can check for themselves.

It runs two ways: a command line that prints the settlement, and a local web page
that shows the whole derivation and prints to PDF.

## Key Features

- **A report, not just an answer**: every figure traces back to the records it came
  from, and the shares add up exactly
- **Smart Column Detection**: finds Payer/Payee or Creditor/Debtor columns itself,
  and lets you correct it in the page if it guesses wrong
- **Multi-Currency Support**: converts through the rates you supply
- **Transaction Optimization**: the minimum number of transfers
- **Flexible Input**: Excel (.xlsx), CSV, TSV
- **Data Validation**: with messages that name the row
- **Print-first web view**: charts as SVG, A4 layout, repeated table headers
- **Export**: CSV, the whole report as JSON, and the per-share ledger

## Why SplitBill?

During group trips, bills get paid by whoever is nearest the till and sorted out
later. That is easy to record and hard to settle: different people pay at different
times, in different currencies, for different subsets of the group.

Finding the minimal set of transfers is the easy half. The hard half is that the
answer is not obviously right to the people being asked to pay.

The minimum-transfer scheme works by collapsing every loan into one net figure per
person and re-pairing those, so the person you are told to pay is usually somebody
you never borrowed from. "I never borrowed from Alan, why am I paying Alan?" cannot
be answered by a tidier table; it is answered by showing the chain behind it:

```
each record (who fronted it, what my share was)
  -> what I consumed, what I paid out
  -> my net
  -> everybody's nets sum to zero
  -> any set of transfers that clears them
```

Each member only has to satisfy themselves about two numbers -- what they consumed
and what they paid. Once those are accepted, the net follows, and the transfers are
a delivery problem.

That is what the web view is for, and why the arithmetic is checkable to the cent:
every share is a whole number of cents, so a column of them adds up to the total
above it exactly. A report that fails its own arithmetic does not deserve to be
believed, and somebody always checks.

## Installation

### Requirements
- Python >= 3.10
- Dependencies: numpy, pandas, openpyxl (automatically installed)

### Quick Install

Using pip:
```bash
git clone https://github.com/cabinz/split-bill
cd split-bill
pip install .
```

Using uv (recommended for development):
```bash
git clone https://github.com/cabinz/split-bill
cd split-bill
uv pip install -e .
```

Using make:
```bash
git clone https://github.com/cabinz/split-bill
cd split-bill
make install         # For users
make install-dev     # For developers (sets up venv)
```

## Quick Start

### 1. Prepare Your Data

Create a spreadsheet with transaction records. See [sample files](samples/) for examples.

![](docs/sample_input.png)

Required columns (auto-detected):
- **Creditor/Payer**: Person who paid the bill
- **Debtor/Payee**: People who owe money (use "all" or "*" for everyone)
- **Amount/Total**: Total amount paid
- **Currency**: Transaction currency (optional if single currency)

Optional columns, used if present: **Date**, **Category**, **Item**. They do not
affect who owes what; they make the report worth reading. Anything else in the sheet
is carried through to the appendix untouched.

### 2a. The web view

```bash
splitbill serve
```

Opens a browser at `http://127.0.0.1:8765`. The web view has two explicit steps.
First, import the spreadsheet, configure its columns, separators and exchange rates,
and inspect every source row (including its base-currency amount when conversion is
enabled). Validation runs as the settings change and lists every participant produced
by the current separator, making a composite phantom name visible before analysis.
Confirming freezes that exact input snapshot and opens the second step: totals, where
each member stands, charts, the pool of over- and underpayments, transfers to make,
and the detailed appendix. Returning to the import step invalidates the visible report
until the input is confirmed again.

"Print / save as PDF" produces a multi-page A4 document -- the same report, laid out
for paper and for passing round.

**The service is bound to `127.0.0.1` and has no authentication.** That binding is
the whole security boundary: it cannot be reached from another machine, but anything
running as you on this one can reach it. It is a local tool, so that is the right
trade, but it is worth knowing rather than assuming. Uploads go to a temporary
directory that is deleted when the server stops; nothing is written into the project
and nothing is written to your spreadsheet.

### 2b. The command line

Basic usage with auto-detection:
```bash
splitbill \
    --file "samples/sample_data.xlsx" \
    --standard_currency "HKD" \
    --exchange_rate "KRW/HKD=0.0057715"
```

With custom column names:
```bash
splitbill \
    --file "data.csv" \
    --col_creditor "From" \
    --col_debtor "To" \
    --col_tot_amount "Value" \
    --standard_currency "USD" \
    --exchange_rate "EUR/USD=1.08"
```

Validate data without processing:
```bash
splitbill \
    --file "data.xlsx" \
    --standard_currency "USD" \
    --validate-only
```

### 3. Reading the output

The output shows what each member spent, followed by the optimized repayment
scheme:
```
Members: Alan, Cabin, Cathy, Vivian
====================
Spending of each member:
╔════════╦═══════════════════╦════════════╦═══════════════════════╦═══════════╗
║ Member ║ Consumption (HKD) ║ Paid (HKD) ║ Paid for Others (HKD) ║ Net (HKD) ║
╠════════╬═══════════════════╬════════════╬═══════════════════════╬═══════════╣
║ Alan   ║          1,551.87 ║   2,619.69 ║              2,137.82 ║ +1,067.82 ║
║ Cabin  ║          1,704.29 ║   1,700.10 ║              1,326.95 ║     -4.19 ║
║ Vivian ║          1,441.48 ║   1,030.22 ║                854.92 ║   -411.26 ║
║ Cathy  ║          1,545.22 ║     892.85 ║                674.56 ║   -652.37 ║
╚════════╩═══════════════════╩════════════╩═══════════════════════╩═══════════╝
  Consumption:     own share of the records the member takes part in
  Paid:            amount actually paid out as a creditor
  Paid for Others: the part of Paid covering other members' shares
  Net:             Paid - Consumption; positive means being owed money
====================
Simplest bill splitting scheme: (with 3 transactions)
╔════╦══════════╦═════╦════════╦══════════════╗
║ #  ║ Creditor ║     ║ Debtor ║ Amount (HKD) ║
╠════╬══════════╬═════╬════════╬══════════════╣
║ 1  ║   Alan   ║ <-- ║ Cabin  ║         4.19 ║
║ 2  ║   Alan   ║ <-- ║ Cathy  ║       652.37 ║
║ 3  ║   Alan   ║ <-- ║ Vivian ║       411.26 ║
╚════╩══════════╩═════╩════════╩══════════════╝
```

Every share here is a whole number of cents, so the columns add up exactly: the
three transfers sum to 1,067.82, which is Alan's net to the cent. Add up either
column and you have checked the report.

A member's `Consumption` is their real cost: the share they take on every
record they appear on, whoever fronted the money. `Paid for Others` is how much
of their own payout went to covering the rest of the group, which is the part
that gets settled. `Net` is the difference the repayment scheme resolves.

## Advanced Usage

### Command-Line Options

```bash
splitbill [OPTIONS]

Required:
  --file FILE                   Path to the data file (.xlsx, .csv, .tsv)
  --standard_currency CURRENCY  Currency for settlement (e.g., "USD", "EUR")

Optional:
  --exchange_rate RATE          Exchange rate: BASE/QUOTE=x (e.g., "EUR/USD=1.08")
                                Can specify multiple rates
  
Column Names (auto-detected if not specified):
  --col_creditor NAME           Column for payer (default: auto-detect)
  --col_debtor NAME             Column for payee (default: auto-detect)  
  --col_tot_amount NAME         Column for amount (default: auto-detect)
  --col_currency NAME           Column for currency (default: auto-detect)
  
Data Processing:
  --separator SEP               Separator for multiple names (default: ",")
  --all_selector SELECTOR       String for "all members" (default: "all")
  --validate-only              Only validate data without processing
  
Output:
  --result_dump_path PATH       Settlement as CSV
  --details_dump_path PATH      The sheet as read, plus converted totals, as CSV
  --ledger_dump_path PATH       One row per person per record, for a spreadsheet
                                to pivot -- the detail behind every figure
  --json_dump_path PATH         The whole report as JSON (the same structure the
                                web view reads; see ctx/v2_plan.md §5)
```

### The web service

```bash
splitbill serve [OPTIONS]

  --port PORT           API port (default 8765; 0 asks the OS for a free one)
  --no-browser          Do not open a browser window
  --develop, --dev      Run frontend HMR and backend auto-reload from a checkout
  --frontend-port PORT  Vite port used with --develop (default 5173)
```

Bound to `127.0.0.1` only, with no authentication -- see the note under Quick Start.
Endpoints, if you want to script it:

| Endpoint | Purpose |
|---|---|
| `POST /api/parse` | a bill (raw body, name in `X-Filename`) -> detected columns, a preview, findings, and a token |
| `POST /api/report` | `{token, columns?, separator?, std_currency?, exchange_rates?}` -> the full report |
| `GET /api/health` | liveness |

The two are separate so a wrong column guess can be corrected in the page and
recalculated without re-uploading the file.

### Examples

**Multiple exchange rates:**
```bash
splitbill \
    --file "trip_expenses.xlsx" \
    --standard_currency "USD" \
    --exchange_rate "EUR/USD=1.08" \
    --exchange_rate "GBP/USD=1.27" \
    --exchange_rate "JPY/USD=0.0067"
```

**Export results:**
```bash
splitbill \
    --file "expenses.csv" \
    --standard_currency "EUR" \
    --result_dump_path "settlement.csv" \
    --details_dump_path "all_transactions.csv"
```

**Custom separators and selectors:**
```bash
splitbill \
    --file "data.xlsx" \
    --standard_currency "USD" \
    --separator ";" \
    --all_selector "everyone"
```

**The report as JSON, and the per-share ledger:**
```bash
splitbill \
    --file "expenses.csv" \
    --json_dump_path "report.json" \
    --ledger_dump_path "ledger.csv"
```

`ledger.csv` has one row per person per record -- the working behind every figure in
the report, in a form a spreadsheet can pivot. `report.json` is the whole thing,
versioned, and is what the web view consumes.

## Data Format

### Input Spreadsheet Structure

Your spreadsheet should contain these columns (names are flexible and auto-detected):

| Date | Item | Payer | Payee | Amount | Currency |
|------|------|-------|-------|--------|----------|
| 2024-01-15 | Lunch | Alice | all | 120.50 | USD |
| 2024-01-15 | Taxi | Bob | Alice, Charlie | 45.00 | USD |
| 2024-01-16 | Hotel | Charlie | * | 580.00 | EUR |

**Column Details:**
- **Payer/Creditor**: Who paid for the expense
- **Payee/Debtor**: Who should pay (comma-separated names or "all"/"*")
- **Amount**: Total amount paid
- **Currency**: Optional if using single currency
- **Other columns**: Kept for reference but not processed

### Supported Column Aliases

The tool automatically detects these column name variations:
- Creditor: "Creditor", "Payer", "From", "Paid By"
- Debtor: "Debtor", "Payee", "To", "Split With"
- Amount: "Amount", "Total", "Value", "Cost"
- Currency: "Currency", "Curr", "CCY"

## Development

### Running Tests
```bash
# All tests
uv run pytest

# Specific test
uv run pytest tests/test_auto_detect.py -v

# With coverage
uv run pytest --cov=splitbill
```

### Project Structure

Three layers, data flowing one way, with a `Report` as the only thing the output
side ever sees. The boundaries are asserted by `tests/test_layering.py` rather than
left to good intentions.

```
split-bill/
├── splitbill/
│   ├── __main__.py        # CLI: parse argv, call pipeline, render
│   ├── serve.py           # the local HTTP service
│   ├── pipeline.py        # prepare() / analyze(): wiring the layers
│   ├── report.py          # the Report model and its JSON contract
│   ├── config.py          # column aliases, separators, tolerances
│   ├── utils/
│   │   ├── money.py       # whole-cent splitting
│   │   └── logger.py
│   ├── loader/            # (1) read -> validate -> normalise -> convert -> allocate
│   │   ├── source.py      #     reading files, detecting columns
│   │   ├── validator.py   #     structure and value checks
│   │   ├── exr.py         #     exchange rates
│   │   ├── names.py       #     splitting name cells, expanding "all"
│   │   ├── ledger.py      #     one row per person per record
│   │   └── positions.py   #     per-member consumption / paid / net
│   ├── settle/            # (2) build the graph, find the minimal equivalent
│   │   ├── graph.py       #     LendingGraph
│   │   └── simplify.py    #     simplest_equiv
│   └── render/            # (3) one Report, several outputs
│       ├── text.py        #     CLI tables, CJK width alignment
│       ├── sheets.py      #     CSV
│       ├── web.py         #     JSON payloads for the browser
│       └── webui/         #     the built frontend (committed; see below)
├── webui/                 # frontend source (Vue 3 + Vite + TypeScript + ECharts)
│   └── src/
│       ├── presentation/  #     shared by both views; no UI state
│       ├── screen/        #     the interactive page
│       └── print/         #     the printed report (see below)
├── tests/
├── samples/
├── ctx/                   # design notes; v2_plan.md is the architecture
└── Makefile
```

`settle` imports neither pandas nor `loader`: it takes
`(creditor, debtor, amount)` triples and returns transfers, which is why layer 1
could be rewritten without touching the solver or its tests. `render` sees only a
`Report`, which is why the terminal and the browser cannot disagree about what
somebody owes.

### The web interface

Source in `webui/`, built output committed to `splitbill/render/webui/`.

Two views over one report, and the split between them is the main thing to know about
this directory:

```text
webui/src/
  presentation/     shared: formatting, i18n, chart options, read-only selectors
  screen/           the page you scroll: upload, configure, filter, drill down
  print/            the printed report: A4, complete tables, SVG charts
```

`presentation/` holds everything that decides *what* a figure says. Neither view
computes anything — every amount comes from Python — and neither derives display data
of its own, so the page and the paper cannot come to disagree.

`screen/` and `print/` are separate DOMs with separate stylesheets and no imports
between them. The screen view can adopt a virtualised table, a sticky header or a
component library without any of it reaching the printed report; the printed report
renders every row of a 668-row allocation without the screen having to keep its markup
printable. Printing does not touch the page: the print view is mounted off-screen from
the moment a report exists, so the browser's own Ctrl-P works, and clicking **Print**
freezes a deep copy of the report and the export options and prints that.

The printed report is checked, not assumed. `webui/e2e/print.mjs` reads both DOMs with
one function and asserts every total, every settlement row and a digest of all 668
ledger rows are identical, then checks the printed report for completeness — sections,
row counts, repeated table headers, SVG charts, nothing wider than the paper — and
that filtering or collapsing anything on screen changes none of it.

After changing anything under `webui/src/`:

```bash
make webui          # build into splitbill/render/webui/
make webui-test     # unit-test the shared presentation layer (no browser)
make webui-check    # build, unit-test, then drive the page in a real browser
make webui-shots    # screenshots and a PDF into /tmp, for looking at
make develop        # Vite HMR + Python API auto-reload in one terminal
make webui-dev      # Vite only, if you want to manage the API separately
```

`make develop` is a convenience alias for `splitbill serve --develop`. Frontend
changes are applied by Vite without a full reload. Changes under `splitbill/`
restart the API; because uploads are intentionally temporary and live in the API
process, import the current bill again after a backend restart.

Commit the rebuilt output with the source change that caused it.
`tests/test_webui_build.py` fails if the source is newer than the build, which is
the mistake this arrangement makes easy.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

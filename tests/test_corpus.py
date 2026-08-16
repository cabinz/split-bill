"""A fixed corpus of awkward bills, run end to end through the CLI.

The corpus covers the cases listed in plan §4.10 rather than just happy paths: a
record with a single debtor, a creditor who is also on their own debtor list,
thousand separators in amounts, the various `all` spellings, a custom separator,
someone who only ever fronts money, someone whose net is zero, three currencies, and
explicitly named columns. Plus the two real bills -- the anonymised 153-record sheet
and the sample .xlsx.

What is checked here is the parts a subprocess can see and an in-process test cannot:
that the CLI exits cleanly, that its printed report matches a committed snapshot, and
that the two CSV dumps say the same thing the terminal did. The figures themselves are
`tests/test_properties.py`'s business, over a much larger set of bills.

These cases used to be run against a frozen copy of V1 as well -- see
`tests/bills.py` for what that was and why it stopped.
"""

import io
import re
from pathlib import Path

import pytest

from tests.bills import (Case, analyse_case, dumped_csvs, render_cli,
                         settled_from_csv)

FIXTURES = Path(__file__).parent / "fixtures"

# Two net creditors and three net debtors, so several schemes tie on transaction
# count and the walk order genuinely decides between them.
CONTESTED = """Creditor,Debtor,Amount,Currency
Alice,All,148,USD
Bob,All,89,USD
Carol,Dave,17.9,USD
Dave,"Alice, Bob",25.86,USD
Eve,All,31.5,USD
Alice,"Carol, Dave, Eve",40,USD
Bob,"Carol, Eve",22,USD
"""

CORPUS = [
    # The real thing: 153 records, 7 members, CJK columns, currency-agnostic.
    Case(name="realistic", path="tests/fixtures/bill_realistic.csv"),
    # Excel input, an `All` selector throughout, and a currency to convert.
    Case(
        name="sample_xlsx",
        path="samples/sample_data.xlsx",
        std_currency="HKD",
        rates=(("KRW", "HKD", 0.0057715),),
    ),
    Case(name="contested_scheme", csv=CONTESTED, std_currency="USD"),
    # One debtor only: no split at all, so the share is the whole amount.
    Case(
        name="single_debtor",
        csv="Creditor,Debtor,Amount\nAlice,Bob,100\n",
    ),
    # The creditor is on their own debtor list, which must not become a self-loop.
    Case(
        name="creditor_among_debtors",
        csv='Creditor,Debtor,Amount\nAlice,"Alice, Bob, Carol",90\n',
    ),
    # Amounts written with thousand separators, in a comma-separated file.
    Case(
        name="thousand_separators",
        csv=(
            'Creditor,Debtor,Amount\n'
            'Alice,"Bob, Carol","2,900.00"\n'
            'Bob,All,"1,050.50"\n'
        ),
    ),
    # Every spelling of "everyone" the config accepts, in one bill.
    Case(
        name="all_selector_aliases",
        csv=(
            "Creditor,Debtor,Amount\n"
            "Alice,all,70\n"
            "Bob,ALL,70\n"
            "Carol,All,70\n"
            "Alice,*,70\n"
            "Bob,所有人,70\n"
            "Carol,所有,70\n"
        ),
    ),
    # A separator that is not the comma, so the cell can contain commas safely.
    Case(
        name="custom_separator",
        csv="Creditor,Debtor,Amount\nAlice,Bob|Carol,60\nBob,Alice|Carol,30\n",
        separator="|",
    ),
    # Dave fronts everything and consumes nothing; Carol's net comes out at zero.
    Case(
        name="pure_creditor_and_zero_net",
        csv=(
            "Creditor,Debtor,Amount\n"
            "Dave,\"Alice, Bob\",100\n"
            "Carol,Alice,50\n"
            "Alice,Carol,50\n"
        ),
    ),
    # Three currencies, converted through two registered rates.
    Case(
        name="multi_currency",
        csv=(
            "Creditor,Debtor,Amount,Currency\n"
            "Alice,All,120,HKD\n"
            "Bob,All,30000,KRW\n"
            "Carol,\"Alice, Bob\",45.5,USD\n"
        ),
        std_currency="HKD",
        rates=(("KRW", "HKD", 0.0057715), ("USD", "HKD", 7.8)),
    ),
    # Explicit column names instead of auto-detection.
    Case(
        name="explicit_columns",
        csv="From,To,Value,CCY\nAlice,\"Bob, Carol\",80,USD\nBob,Alice,20,USD\n",
        columns={"creditor": "From", "debtor": "To", "amount": "Value",
                 "currency": "CCY"},
        std_currency="USD",
    ),
]

# Cases whose rendered output is also kept as a committed snapshot, so a change
# is visible in a diff and not only as a test failure.
SNAPSHOTS = {
    "realistic": "baseline_realistic.txt",
    "sample_xlsx": "baseline_sample_xlsx.txt",
}

def _ids(case: Case) -> str:
    return case.name


@pytest.mark.parametrize("case", CORPUS, ids=_ids)
def test_the_cli_handles_every_case(case: Case, tmp_path: Path):
    """It exits cleanly and prints a report naming every member.

    `render_cli` asserts the exit status, so this is mostly about the awkward
    corners reaching the terminal at all -- a CJK name, a `*` all-selector, a
    thousand separator inside a comma-separated cell.
    """
    bill = case.materialize(tmp_path)
    output = render_cli(bill, case)

    report = analyse_case(case, bill)
    for member in report.members:
        assert member in output, f"{member} missing from the printed report"


class TestAllSelectorAliasesNeedsTwoTransfers:
    """Six records of 70 shared three ways, which cannot come out even.

    70 does not divide into three whole cents, so each record leaves one over and
    every one of them goes to the earliest-sorting name. Alice is allocated 23.34 six
    times and the others 23.33, so she consumes 140.04 having paid 140.00, and two 2¢
    transfers are genuinely owed.

    V1 reported no transfers here, which looked tidier but only because its shares
    did not add up to the records they came from -- see plan §9.1. Pinned to the cent
    because it is the clearest demonstration in the suite of what the allocation
    does, and because if somebody later changes which member the remainder favours,
    this is the test that should make them say so out loud.
    """

    CASE = next(c for c in CORPUS if c.name == "all_selector_aliases")

    @pytest.fixture
    def report(self, tmp_path):
        return analyse_case(self.CASE, self.CASE.materialize(tmp_path))

    def test_the_remainder_lands_on_the_earliest_sorting_name(self, report):
        nets = {p.member: p.net for p in report.positions}
        assert nets == pytest.approx({"Alice": -0.04, "Bob": 0.02, "Carol": 0.02},
                                     abs=1e-9)

    def test_two_transfers_settle_it(self, report):
        assert [(t.sender, t.receiver, round(t.amount, 2))
                for t in report.settlement] == [
            ("Alice", "Bob", 0.02),
            ("Alice", "Carol", 0.02),
        ]

    def test_the_shares_add_up_where_v1_did_not(self, report):
        """The reason those transfers exist. Alice's six shares come to 140.04."""
        alice = sum(e.share for e in report.ledger if e.member == "Alice")
        assert alice == pytest.approx(140.04, abs=1e-9)


@pytest.mark.parametrize("case", CORPUS, ids=_ids)
def test_dumped_result_csv_agrees_with_the_report(case: Case, tmp_path: Path):
    """--result_dump_path says the same thing the report does.

    The settlement CSV used to come off `LendingGraph.dump()` and is now a group-by of
    the Report. The risk it guards against is the file and the screen disagreeing --
    somebody settling up months later from the CSV alone, on different numbers.
    """
    bill = case.materialize(tmp_path)
    dumped = dumped_csvs(bill, case, tmp_path)
    report = analyse_case(case, bill)

    from_csv = settled_from_csv(dumped["result"])
    for position in report.positions:
        assert from_csv.get(position.member, 0.0) == pytest.approx(
            position.net, abs=0.01
        ), position.member


@pytest.mark.parametrize("case", CORPUS, ids=_ids)
def test_dumped_details_csv_holds_the_whole_sheet(case: Case, tmp_path: Path):
    """--details_dump_path keeps every row and every column of the original.

    Written from `raw_frame` rather than the ledger, because this file exists for
    checking the tool's arithmetic against the source sheet -- so it has to carry the
    columns the tool never looked at, notes included.
    """
    import pandas as pd

    bill = case.materialize(tmp_path)
    dumped = dumped_csvs(bill, case, tmp_path)
    report = analyse_case(case, bill)

    written = pd.read_csv(io.StringIO(dumped["details"]), index_col=0)
    assert len(written) == len(report.raw_frame)
    for column in report.raw_frame.columns:
        assert column in written.columns, column


class TestJsonDump:
    """`--json_dump_path` writes the §5 contract, which is Phase 1's input.

    The browser reads exactly this file, so what matters is that the CLI and the web
    view cannot end up with different reports of the same bill -- one dump, one
    schema, both sides reading it.
    """

    CASE = next(c for c in CORPUS if c.name == "realistic")

    @pytest.fixture
    def dumped(self, tmp_path):
        import json

        out = tmp_path / "report.json"
        render_cli(self.CASE.materialize(tmp_path), self.CASE,
                   extra_argv=["--json_dump_path", str(out)])
        return json.loads(out.read_text(encoding="utf-8"))

    def test_it_is_the_schema_the_contract_describes(self, dumped):
        assert dumped["schema_version"] == "2.0"
        assert set(dumped) == {
            "schema_version", "meta", "members", "summary", "positions",
            "settlement", "lending_edges", "ledger",
        }

    def test_it_agrees_with_the_report_the_terminal_printed(self, dumped, tmp_path):
        report = analyse_case(self.CASE, self.CASE.materialize(tmp_path))
        expected = report.to_dict()
        # `generated_at` is a timestamp: two runs, two values, by design.
        del expected["meta"]["generated_at"], dumped["meta"]["generated_at"]
        assert dumped == expected

    def test_it_carries_every_share(self, dumped):
        """668 rows across 153 records -- the appendix in full, not a summary of it.

        Not 153x7: most records are shared by a few people rather than all seven, so
        the figure is a fact about this bill. It is pinned because a ledger that
        quietly lost rows would still look plausible.
        """
        assert len(dumped["ledger"]) == 668

    def test_cjk_is_readable_rather_than_escaped(self, tmp_path):
        out = tmp_path / "report.json"
        render_cli(self.CASE.materialize(tmp_path), self.CASE,
                   extra_argv=["--json_dump_path", str(out)])
        text = out.read_text(encoding="utf-8")
        assert "甲" in text
        assert "\\u" not in text


class TestLedgerDump:
    """`--ledger_dump_path`: the per-share table, for a spreadsheet to pivot.

    Nothing in V1 could produce this -- the shares were accumulated into totals and
    discarded -- and it is the file a member who wants to check the arithmetic
    themselves actually needs.
    """

    CASE = next(c for c in CORPUS if c.name == "realistic")

    def test_one_row_per_person_per_record(self, tmp_path):
        import pandas as pd

        out = tmp_path / "ledger.csv"
        render_cli(self.CASE.materialize(tmp_path), self.CASE,
                   extra_argv=["--ledger_dump_path", str(out)])
        frame = pd.read_csv(out)

        assert len(frame) == 668
        assert frame["record_id"].nunique() == 153
        assert set(frame.columns) >= {
            "record_id", "creditor", "member", "share", "amount_raw", "amount_std",
            "is_own_share", "date", "category", "item",
        }

    def test_the_shares_add_up_to_each_record(self, tmp_path):
        """The check the file exists to make possible, made on the file itself."""
        import pandas as pd

        out = tmp_path / "ledger.csv"
        render_cli(self.CASE.materialize(tmp_path), self.CASE,
                   extra_argv=["--ledger_dump_path", str(out)])
        frame = pd.read_csv(out)

        per_record = frame.groupby("record_id").agg(
            shares=("share", "sum"), total=("amount_std", "first"))
        assert (per_record["shares"] - per_record["total"]).abs().max() < 1e-9


def test_the_readme_shows_what_the_cli_actually_prints():
    """The sample output in README.md, against the committed snapshot of that case.

    It had gone stale: the figures there were the ones from before deterministic
    allocation, so the README advertised a settlement of 411.34 that the tool no
    longer produces. Nothing failed, because nothing was looking.

    Documentation that quietly disagrees with the tool is worse than none -- it is
    the first thing somebody checks the output against, and the mismatch reads as a
    bug in the tool. Compared against the snapshot rather than by running the CLI
    again, so this stays a text comparison and does not add a subprocess.
    """
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8")
    snapshot = (FIXTURES / SNAPSHOTS["sample_xlsx"]).read_text(encoding="utf-8")

    block = re.search(r"```\n(Members: .*?)\n```", readme, re.S)
    assert block, "the README no longer contains a sample output block"

    assert snapshot.strip().endswith(block.group(1).strip()), (
        "README.md's sample output is not what the CLI prints for "
        "samples/sample_data.xlsx. Re-run:\n"
        '  uv run splitbill --file "samples/sample_data.xlsx" '
        '--standard_currency "HKD" --exchange_rate "KRW/HKD=0.0057715"\n'
        "and paste the tables in."
    )


@pytest.mark.parametrize("case_name,snapshot_name", sorted(SNAPSHOTS.items()))
def test_rendered_output_matches_snapshot(
    case_name: str, snapshot_name: str, tmp_path: Path
):
    """The printed report against the committed baseline.

    This is what step 0f is accepted against. Regenerate deliberately, never to
    make a test go green:

        uv run python tools/refresh_baselines.py
    """
    case = next(c for c in CORPUS if c.name == case_name)
    expected = (FIXTURES / snapshot_name).read_text(encoding="utf-8")
    actual = render_cli(case.materialize(tmp_path), case)
    assert actual == expected

"""Test amount cleaning functionality for comma-formatted numbers.

Amounts arrive as "2,900.00" from every spreadsheet a human has touched, and every
one of them has to become a number before anything else reads it. These check the
frame the loader hands on -- `LoadResult.raw_frame` -- because that is what the
appendix and the details CSV are written from, so a stray string would surface there
rather than in the arithmetic.
"""

import pandas as pd
import pytest

from tests.conftest import load_bill, write_bill


def amounts(csv: str, tmp_path, column: str = "Amount", **cfg) -> pd.Series:
    """The amount column as the loader leaves it."""
    frame = load_bill(csv, tmp_path, **cfg).raw_frame
    assert pd.api.types.is_numeric_dtype(frame[column]), (
        f"{column} is {frame[column].dtype}, so something downstream will do "
        f"string arithmetic on it"
    )
    return frame[column]


class TestAmountCleaning:
    """Test cases for cleaning amount values with comma thousand separators."""

    def test_amount_with_commas(self, tmp_path):
        """Amounts with commas are cleaned. They have to be quoted in a CSV."""
        got = amounts(
            'Creditor,Debtor,Amount,Currency\n'
            'Alice,Bob,"2,900.00",USD\n'
            'Bob,Charlie,"1,500.50",USD\n',
            tmp_path,
        )
        assert list(got) == [2900.00, 1500.50]

    def test_mixed_format_amounts(self, tmp_path):
        """Some with commas, some without, in one column."""
        got = amounts(
            'Creditor,Debtor,Amount,Currency\n'
            'Alice,Bob,"2,900.00",USD\n'
            'Bob,Charlie,1500.50,USD\n'
            'Charlie,Alice,"10,000",USD\n'
            'Alice,Charlie,999.99,USD\n',
            tmp_path,
        )
        assert list(got) == [2900.00, 1500.50, 10000, 999.99]

    def test_large_numbers_with_commas(self, tmp_path):
        """More than one separator in a single amount."""
        got = amounts(
            'Creditor,Debtor,Amount,Currency\n'
            'Alice,Bob,"1,234,567.89",USD\n'
            'Bob,Charlie,"999,999.99",USD\n',
            tmp_path,
        )
        assert list(got) == [1234567.89, 999999.99]

    def test_backward_compatibility_no_commas(self, tmp_path):
        """Amounts without commas are untouched."""
        got = amounts(
            "Creditor,Debtor,Amount,Currency\n"
            "Alice,Bob,2900.00,USD\n"
            "Bob,Charlie,1500.50,USD\n",
            tmp_path,
        )
        assert list(got) == [2900.00, 1500.50]

    def test_integer_amounts_with_commas(self, tmp_path):
        got = amounts(
            'Creditor,Debtor,Amount,Currency\n'
            'Alice,Bob,"2,900",USD\n'
            'Bob,Charlie,"10,000",USD\n',
            tmp_path,
        )
        assert list(got) == [2900, 10000]

    def test_invalid_amount_raises_error(self, tmp_path):
        """A cell that is not a number at all stops the load.

        Refused rather than coerced to NaN: an amount nobody can read is a question
        for whoever wrote the sheet, and silently settling the rest of the bill
        without it would answer it wrongly.
        """
        with pytest.raises(ValueError, match="Invalid amount values found"):
            load_bill(
                "Creditor,Debtor,Amount,Currency\n"
                "Alice,Bob,2900.00,USD\n"
                "Bob,Charlie,invalid,USD\n",
                tmp_path,
            )

    def test_the_error_names_the_spreadsheet_row(self, tmp_path):
        """Row 3, counting the header as row 1 -- which is what the editor shows."""
        with pytest.raises(ValueError, match=r"row\(s\): \[3\]"):
            load_bill(
                "Creditor,Debtor,Amount,Currency\n"
                "Alice,Bob,2900.00,USD\n"
                "Bob,Charlie,invalid,USD\n",
                tmp_path,
            )

    def test_amount_cleaning_with_excel(self, tmp_path):
        """The same path for .xlsx, where a comma-formatted amount is a string."""
        bill = tmp_path / "bill.xlsx"
        pd.DataFrame({
            "Creditor": ["Alice", "Bob"],
            "Debtor": ["Bob", "Charlie"],
            "Amount": ["2,900.00", "1,500.50"],
            "Currency": ["USD", "USD"],
        }).to_excel(bill, index=False)

        frame = load_bill(bill).raw_frame
        assert pd.api.types.is_numeric_dtype(frame["Amount"])
        assert list(frame["Amount"]) == [2900.00, 1500.50]

    def test_custom_column_name_with_commas(self, tmp_path):
        """Cleaning follows the configured column, not the default name."""
        got = amounts(
            'From,To,Value,Curr\n'
            'Alice,Bob,"2,900.00",USD\n'
            'Bob,Charlie,"1,500.50",USD\n',
            tmp_path,
            column="Value",
            col_creditor="From",
            col_debtor="To",
            col_tot_amount="Value",
            col_currency="Curr",
        )
        assert list(got) == [2900.00, 1500.50]

    def test_cleaning_reaches_the_shares(self, tmp_path):
        """The point of all of the above: a cleaned amount gets split as a number.

        Without cleaning, "2,900.00" divided two ways is a TypeError at best and a
        string concatenation at worst. Checked here so the guarantee is stated in
        terms of the report and not only of a dtype.
        """
        bill = write_bill(
            'Creditor,Debtor,Amount,Currency\nAlice,"Alice, Bob","2,900.00",USD\n',
            tmp_path,
        )
        ledger = load_bill(bill).ledger
        assert [e.share for e in ledger] == [1450.00, 1450.00]

"""Reading a bill off disk, and working out which column means what.

The front of layer 1: everything here happens before a single amount is
interpreted. `read_sheet` is the one answer to "how is a bill read" -- the CLI used
to keep its own copy of the format table and read the file a second time to detect
columns before handing the path to a loader that read it again, and the two copies
were free to disagree about which formats exist. `DataFormat` is which column plays
which role, either because the user said so or because detection found it.

Nothing in here imports `settle`: this module used to build the lending graph for the
`Loader` compatibility shell, which was the one place layer 1 reached into layer 2 and
the reason `tests/test_layering.py` had a violation to report. The shell is gone and
so is the import.
"""

from ..config import *

from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd
from pathlib import Path


def clean_amount_column(df: pd.DataFrame, amount_col: str) -> None:
    """Clean amount column by removing thousand separators (commas) in-place.

    This function handles amount values that may contain comma thousand separators
    (e.g., "2,900.00") and converts them to proper numeric values.

    Args:
        df: DataFrame to clean
        amount_col: Name of the amount column to clean

    Raises:
        ValueError: If invalid amount values are detected after cleaning
    """
    # Check if column contains string/object values
    if df[amount_col].dtype == 'object':
        # Remove commas from string amounts (English format: 1,234.56)
        df[amount_col] = df[amount_col].astype(str).str.replace(',', '', regex=False)

    # Convert to numeric (float), coerce errors to NaN
    df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')

    # Check for NaN values after conversion (indicates invalid data)
    if df[amount_col].isna().any():
        invalid_rows = df[df[amount_col].isna()].index.tolist()
        # Get the actual row numbers (1-indexed for user readability)
        invalid_row_numbers = [r + 2 for r in invalid_rows]  # +2 for header and 0-indexing
        raise ValueError(
            f"Invalid amount values found in row(s): {invalid_row_numbers}. "
            f"Please check the '{amount_col}' column for non-numeric values."
        )


@dataclass(frozen=True)
class ColumnBinding:
    """Which column a role ended up bound to, and whether detection chose it.

    Reporting only: `DataFormat.col_*` stay the operative values. The difference
    shows on screen -- a detected column is a guess the user should see and be
    able to override, one they named is not up for discussion -- and it is the
    reason the web view can offer a corrected re-run instead of sending someone
    back to the command line.

    `name` is None when the sheet has no such column. That is distinct from the
    column name `DataFormat` falls back to, which is a guess that has not been
    checked against the sheet at all.
    """

    name: Optional[str]
    auto: bool
    """True only when auto-detection found this column. A fallback to the default
    name is not a detection: nothing confirmed the column exists."""


class DataFormat:
    def __init__(self,
                 col_creditor=DEFAULT_COL_CREDITOR,
                 col_debtor=DEFAULT_COL_DEBTOR,
                 col_tot_amount=DEFAULT_COL_TOT_AMOUNT,
                 col_currency=DEFAULT_COL_CURRENCY,
                 separator=DEFAULT_SEP,  # separator for multiple names
                 all_selector=DEFAULT_ALL_SELECTOR,
                 user_specified_columns: Optional[set[DataColumn]] = None,
                 col_date: Optional[str] = None,
                 col_category: Optional[str] = None,
                 col_item: Optional[str] = None,
                 bindings: Optional[Dict[str, 'ColumnBinding']] = None,
                 ) -> None:
        self.col_creditor = col_creditor
        self.col_debtor = col_debtor
        self.col_tot_amount = col_tot_amount
        self.col_currency = col_currency
        self.separator = separator
        self.all_selector = all_selector
        # Optional and descriptive: the bill settles without them. None means the
        # sheet has no such column, and the report simply omits what it cannot say.
        self.col_date = col_date
        self.col_category = col_category
        self.col_item = col_item
        # Track which columns were explicitly specified by user (not auto-detected)
        self.user_specified_columns: set[DataColumn] = user_specified_columns or set()
        # Constructed directly means every column was named on purpose.
        self.bindings: Dict[str, ColumnBinding] = bindings or {
            role: ColumnBinding(name, auto=False)
            for role, name in self.roles().items()
        }

    def roles(self) -> Dict[str, Optional[str]]:
        """Role -> operative column name. The report's `meta.columns` is keyed
        this way, and so are the detection messages."""
        return {
            "creditor": self.col_creditor,
            "debtor": self.col_debtor,
            "amount": self.col_tot_amount,
            "currency": self.col_currency,
            "date": self.col_date,
            "category": self.col_category,
            "item": self.col_item,
        }

    @classmethod
    def from_args(cls, args):
        return cls(
            args.col_creditor,
            args.col_debtor,
            args.col_tot_amount,
            args.col_currency,
            args.separator,
            args.all_selector,
        )
    
    @staticmethod
    def auto_detect_column(df_columns: List[str], aliases: List[str]) -> Optional[str]:
        """Auto-detect column name from DataFrame columns using aliases.
        
        Args:
            df_columns: List of column names from DataFrame
            aliases: List of possible aliases for this column type
        
        Returns:
            The actual column name from df_columns if found, None otherwise.
            Returns the original case from df_columns.
        """
        # Create a mapping from lowercase to original column names
        column_map = {col.lower(): col for col in df_columns}
        
        # Check each alias (case-insensitive)
        for alias in aliases:
            if alias.lower() in column_map:
                return column_map[alias.lower()]
        
        return None
    
    @classmethod
    def from_args_with_auto_detect(
        cls,
        args,
        df: pd.DataFrame,
        descriptive_overrides: Optional[Dict[str, Optional[str]]] = None,
    ):
        """Create DataFormat with auto-detection support.

        Args:
            args: Command line arguments
            df: DataFrame to detect columns from
            descriptive_overrides: Explicit choices for optional descriptive
                roles. A missing role is auto-detected; a role mapped to None is
                intentionally disabled.

        Returns:
            DataFormat instance with detected or specified column names
        """
        columns = df.columns.tolist()

        # Role -> (what the user asked for, aliases to try, fallback name).
        # Required columns fall back to a default name so the failure surfaces from
        # the validator, which can say which aliases it looked for. The descriptive
        # ones have no fallback: absent simply means the report says less.
        REQUIRED = {
            "creditor": (args.col_creditor, CREDITOR_ALIASES, DEFAULT_COL_CREDITOR,
                         DataColumn.CREDITOR),
            "debtor": (args.col_debtor, DEBTOR_ALIASES, DEFAULT_COL_DEBTOR,
                       DataColumn.DEBTOR),
            "amount": (args.col_tot_amount, AMOUNT_ALIASES, DEFAULT_COL_TOT_AMOUNT,
                       DataColumn.AMOUNT),
            "currency": (args.col_currency, CURRENCY_ALIASES, DEFAULT_COL_CURRENCY,
                         DataColumn.CURRENCY),
        }
        DESCRIPTIVE = {
            "date": DATE_ALIASES,
            "category": CATEGORY_ALIASES,
            "item": ITEM_ALIASES,
        }

        user_specified_cols: set[DataColumn] = set()
        resolved: Dict[str, Optional[str]] = {}
        bindings: Dict[str, ColumnBinding] = {}

        for role, (requested, aliases, fallback, column_enum) in REQUIRED.items():
            if requested is not None:
                user_specified_cols.add(column_enum)
                resolved[role] = requested
                # None when the named column is not there: the validator reports
                # it, and the report should not claim a column that never existed.
                bindings[role] = ColumnBinding(
                    requested if requested in columns else None, auto=False)
                continue
            detected = cls.auto_detect_column(columns, aliases)
            resolved[role] = detected if detected else fallback
            bindings[role] = ColumnBinding(detected, auto=detected is not None)

        descriptive_overrides = descriptive_overrides or {}
        for role, aliases in DESCRIPTIVE.items():
            if role in descriptive_overrides:
                requested = descriptive_overrides[role]
                resolved[role] = requested
                bindings[role] = ColumnBinding(
                    requested if requested in columns else None, auto=False)
                continue
            detected = cls.auto_detect_column(columns, aliases)
            resolved[role] = detected
            bindings[role] = ColumnBinding(detected, auto=detected is not None)

        return cls(
            col_creditor=resolved["creditor"],
            col_debtor=resolved["debtor"],
            col_tot_amount=resolved["amount"],
            col_currency=resolved["currency"],
            separator=args.separator,
            all_selector=args.all_selector,
            user_specified_columns=user_specified_cols,
            col_date=resolved["date"],
            col_category=resolved["category"],
            col_item=resolved["item"],
            bindings=bindings,
        )



SUPPORT_FTYPES = {
    ".csv": lambda x: pd.read_csv(x),
    ".tsv": lambda x: pd.read_csv(x, sep="\t"),
    ".xlsx": lambda x: pd.read_excel(x),
}


def read_sheet(file_path) -> pd.DataFrame:
    """Read a bill from disk, checking the path and the format first.

    Extracted so there is one answer to "how is a bill read". The CLI used to
    carry its own copy of this dict and read the file a second time to detect
    columns before handing the path to Loader, which then read it again -- and the
    two copies were free to disagree about which formats exist.
    """
    file_path = Path(file_path)
    assert file_path.exists(), f"The given path {file_path} does NOT exist"
    assert file_path.is_file(), f"The given path {file_path} is NOT a path"

    file_type = 'No Suffix' if file_path.suffix == '' else file_path.suffix
    if file_type not in SUPPORT_FTYPES:
        raise ValueError("Unsupported format: {}. Only support files in format: {}. "
                         "Please specify correct file path with supported format suffix.".format(
            file_type,
            ', '.join(SUPPORT_FTYPES.keys()),
        ))

    return SUPPORT_FTYPES[file_path.suffix](file_path)



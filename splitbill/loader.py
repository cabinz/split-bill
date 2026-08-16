"""Represent the loader to load records as a lending graph from the data file as required.
"""

from . import graph
from .exr import ExchangeRates
from .config import *

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd
from pathlib import Path


@dataclass
class MemberStats:
    """Spending statistics of a single member over all the records.

    A record is fronted in full by its creditor, while its amount is shared
    evenly among the debtors listed on it (the creditor included, if listed).
    """

    consumption: float = 0.0
    """Own share of every record the member takes part in, i.e. the real cost."""

    paid: float = 0.0
    """Total amount the member actually paid out as a creditor."""

    paid_for_others: float = 0.0
    """The part of `paid` that covered other members' shares."""

    covered_by_others: float = 0.0
    """Own share that was fronted by other members."""

    @property
    def net(self) -> float:
        """Net outflow. Positive means the member is owed money by the others."""
        return self.paid - self.consumption


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


class DataFormat:
    def __init__(self,
                 col_creditor=DEFAULT_COL_CREDITOR,
                 col_debtor=DEFAULT_COL_DEBTOR,
                 col_tot_amount=DEFAULT_COL_TOT_AMOUNT,
                 col_currency=DEFAULT_COL_CURRENCY,
                 separator=DEFAULT_SEP,  # separator for multiple names
                 all_selector=DEFAULT_ALL_SELECTOR,
                 user_specified_columns: Optional[set[DataColumn]] = None,
                 ) -> None:
        self.col_creditor = col_creditor
        self.col_debtor = col_debtor
        self.col_tot_amount = col_tot_amount
        self.col_currency = col_currency
        self.separator = separator
        self.all_selector = all_selector
        # Track which columns were explicitly specified by user (not auto-detected)
        self.user_specified_columns: set[DataColumn] = user_specified_columns or set()

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
    def from_args_with_auto_detect(cls, args, df: pd.DataFrame):
        """Create DataFormat with auto-detection support.

        Args:
            args: Command line arguments
            df: DataFrame to detect columns from

        Returns:
            DataFormat instance with detected or specified column names
        """
        # Track which columns are explicitly specified by user
        user_specified_cols: set[DataColumn] = set()

        # Creditor column: user specified > auto-detect > default
        col_creditor = args.col_creditor
        if col_creditor is None:  # User didn't specify
            detected = cls.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
            if detected:
                print(f"✓ Auto-detected creditor column: '{detected}'")
                col_creditor = detected
            else:
                # Keep the default, will fail later if column doesn't exist
                col_creditor = DEFAULT_COL_CREDITOR
        else:
            user_specified_cols.add(DataColumn.CREDITOR)

        # Debtor column: user specified > auto-detect > default
        col_debtor = args.col_debtor
        if col_debtor is None:  # User didn't specify
            detected = cls.auto_detect_column(df.columns.tolist(), DEBTOR_ALIASES)
            if detected:
                print(f"✓ Auto-detected debtor column: '{detected}'")
                col_debtor = detected
            else:
                col_debtor = DEFAULT_COL_DEBTOR
        else:
            user_specified_cols.add(DataColumn.DEBTOR)

        # Amount column: user specified > auto-detect > default
        col_tot_amount = args.col_tot_amount
        if col_tot_amount is None:  # User didn't specify
            detected = cls.auto_detect_column(df.columns.tolist(), AMOUNT_ALIASES)
            if detected:
                print(f"✓ Auto-detected amount column: '{detected}'")
                col_tot_amount = detected
            else:
                col_tot_amount = DEFAULT_COL_TOT_AMOUNT
        else:
            user_specified_cols.add(DataColumn.AMOUNT)

        # Currency column: user specified > auto-detect > default
        col_currency = args.col_currency
        if col_currency is None:  # User didn't specify
            detected = cls.auto_detect_column(df.columns.tolist(), CURRENCY_ALIASES)
            if detected:
                print(f"✓ Auto-detected currency column: '{detected}'")
                col_currency = detected
            else:
                col_currency = DEFAULT_COL_CURRENCY
        else:
            user_specified_cols.add(DataColumn.CURRENCY)

        return cls(
            col_creditor=col_creditor,
            col_debtor=col_debtor,
            col_tot_amount=col_tot_amount,
            col_currency=col_currency,
            separator=args.separator,
            all_selector=args.all_selector,
            user_specified_columns=user_specified_cols,
        )



SUPPORT_FTYPES = {
    ".csv": lambda x: pd.read_csv(x),
    ".tsv": lambda x: pd.read_csv(x, sep="\t"),
    ".xlsx": lambda x: pd.read_excel(x),
}


class Loader:
    def __init__(
        self,
        file_path: str,
        cfg: DataFormat = DataFormat(),
        exrs: ExchangeRates = None,
    ) -> None:
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

        self._file_path = file_path
        self._df = SUPPORT_FTYPES[self._file_path.suffix](self._file_path)
        self._cfg = cfg

        # Clean amount column to handle comma-formatted numbers
        self._clean_amount_column()

        self._metacoln_std_tot_amount = f"Total Amount"
        if exrs is not None:
            self._metacoln_std_tot_amount += f" ({exrs.std_currency})"
            self._exrs = exrs
            self._df[self._metacoln_std_tot_amount] = self._df.apply(
                lambda row: exrs.to_std(row[cfg.col_currency], row[cfg.col_tot_amount]),
                axis=1,
            )
        else:
            print("No exchange rates provided. Run in the currency-agnostic way.")
            self._df[self._metacoln_std_tot_amount] = self._df[cfg.col_tot_amount]
        
        def _split_names(s_names: str, splitter: str = DEFAULT_SEP) -> List[str]:
            names = [name.strip() for name in s_names.split(splitter)]
            return names
        
        # Helper function to check if a value is an "all" selector
        def is_all_selector(value: str) -> bool:
            return value.lower().strip() in [sel.lower() for sel in ALL_SELECTOR_ALIASES]
        
        # Collect all members
        self._members = set()
        for index, row in self._df.iterrows():
            if not is_all_selector(row[self._cfg.col_creditor]):
                creditor = _split_names(row[self._cfg.col_creditor], cfg.separator)
                if len(creditor) > 1: # Currently only support single creditor
                    raise ValueError("Currently only support single creditor. "
                                     "Please specify only one creditor in each record.")
                self._members.update(creditor)
            if not is_all_selector(row[self._cfg.col_debtor]):
                self._members.update(
                    _split_names(row[self._cfg.col_debtor], self._cfg.separator)
                )

        # Create lending graph, accumulating per-member statistics on the way
        self._g = graph.LendingGraph()
        # Seeded with every member, so that even one who neither paid nor
        # consumed anything still shows up in the statistics. Sorted, so that
        # this dict's key order -- which the statistics table falls back on for
        # members of equal net -- is the same on every run.
        self._stats: Dict[str, MemberStats] = defaultdict(
            MemberStats, {name: MemberStats() for name in sorted(self._members)})

        for index, row in self._df.iterrows():
            creditor = row[self._cfg.col_creditor].strip()
            if is_all_selector(row[self._cfg.col_debtor]):
                # sorted(), not list(): iterating a set follows PYTHONHASHSEED,
                # which would make the edge insertion order — and therefore the
                # settlement scheme picked among equally-minimal ones — vary
                # between runs.
                debtors = sorted(self._members)
            else:
                debtors = _split_names(row[self._cfg.col_debtor], self._cfg.separator)

            tot_amount = row[self._metacoln_std_tot_amount]
            pp_amount = tot_amount / len(debtors)

            # The creditor fronts the whole amount, whoever shares it.
            self._stats[creditor].paid += tot_amount
            # Everyone on the debtor list consumes an even share of it.
            for debtor in debtors:
                self._stats[debtor].consumption += pp_amount

            if creditor in debtors:  # TODO: unnecessary, self-loop and be eliminated in the graph
                debtors.remove(creditor)
            for debtor in debtors:
                self._stats[creditor].paid_for_others += pp_amount
                self._stats[debtor].covered_by_others += pp_amount
                self._g.add_edge(creditor, debtor, pp_amount)

    def _clean_amount_column(self):
        """Clean amount column by removing thousand separators (commas).

        This is a wrapper around the standalone clean_amount_column function.
        """
        clean_amount_column(self._df, self._cfg.col_tot_amount)

    def get_graph(self):
        return self._g

    def get_data(self):
        return self._df

    def get_members(self):
        return self._members

    def get_member_stats(self) -> Dict[str, MemberStats]:
        """Spending statistics of every member, ordered by net outflow descending
        (creditors first, then debtors), so that it reads the same way as the
        settlement result.

        Members with the same net are ordered by name, so that the table does
        not depend on the insertion order of ``self._stats``.
        """
        return {
            name: stats
            for name, stats in sorted(
                self._stats.items(), key=lambda kv: (-kv[1].net, kv[0])
            )
        }

    def get_preprocessed_data(self):
        return self._df

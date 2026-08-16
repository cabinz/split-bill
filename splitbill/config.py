"""Default configuration values for data format of records and the framework."""

from enum import Enum, auto


class DataColumn(Enum):
    """Enum representing the required data columns."""
    CREDITOR = auto()
    DEBTOR = auto()
    AMOUNT = auto()
    CURRENCY = auto()


DEFAULT_SEP = ","

# Column name aliases for auto-detection (in priority order)
CREDITOR_ALIASES = [
    "Creditor", "Payer", "From", "Paid By",
    "付款人",
]
DEFAULT_COL_CREDITOR = CREDITOR_ALIASES[0]

DEBTOR_ALIASES = [
    "Debtor", "Payee", "To", "Split With",
    "参与人",
]
DEFAULT_COL_DEBTOR = DEBTOR_ALIASES[0]

AMOUNT_ALIASES = [
    "Amount", "Total", "Value", "Cost",
    "金额", "总额",
]
DEFAULT_COL_TOT_AMOUNT = AMOUNT_ALIASES[0]

CURRENCY_ALIASES = [
    "Currency", "Curr", "CCY",
    "货币", "币种",
]
DEFAULT_COL_CURRENCY = CURRENCY_ALIASES[0]

# Mapping from DataColumn to aliases
COLUMN_ALIASES = {
    DataColumn.CREDITOR: CREDITOR_ALIASES,
    DataColumn.DEBTOR: DEBTOR_ALIASES,
    DataColumn.AMOUNT: AMOUNT_ALIASES,
    DataColumn.CURRENCY: CURRENCY_ALIASES,
}

# Optional descriptive columns. A bill settles fine without them, so they are
# detected silently and left as None when absent -- but they are what the report's
# per-member drill-down, category breakdown and appendix are made of, so a sheet
# that has them should not have them ignored.
DATE_ALIASES = [
    "Date", "Day",
    "日期",
]

CATEGORY_ALIASES = [
    "Category", "Type", "Kind",
    "类型", "分类", "类别",
]

# Note: deliberately not aliased to "Note"/"备注". A note is a free-text remark
# about a record; an item is what was bought. Conflating them would put arbitrary
# commentary into the report as if it were a line item.
ITEM_ALIASES = [
    "Item", "Description", "Detail",
    "项目", "名目", "事项",
]

# All selector aliases (for indicating all members)
ALL_SELECTOR_ALIASES = [
    "all", "*", "ALL", "All",
    "所有", "所有人",
]
DEFAULT_ALL_SELECTOR = ALL_SELECTOR_ALIASES[0]

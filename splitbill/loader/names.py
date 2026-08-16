"""Reading the people out of a bill's creditor and debtor cells.

A cell holds either a list of names or a word meaning "everyone", and both
spellings vary: the separator is configurable and `all` has six accepted forms.
Every part of layer 1 that looks at a name cell has to agree on how to read one,
which is the argument for these living in one module rather than as closures
inside whoever needed them first -- the validator had grown its own copy of
`is_all_selector`, character for character.
"""

from ..config import ALL_SELECTOR_ALIASES, DEFAULT_SEP

from typing import List


def split_names(s_names: str, splitter: str = DEFAULT_SEP) -> List[str]:
    """Split a cell into names, trimming the whitespace around each."""
    names = [name.strip() for name in s_names.split(splitter)]
    return names


def is_all_selector(value: str) -> bool:
    """Whether a cell means "everyone on this trip" rather than naming people."""
    return value.lower().strip() in [sel.lower() for sel in ALL_SELECTOR_ALIASES]


def collect_members(df, cfg) -> set:
    """Every member named anywhere in the bill.

    Cells meaning "everyone" are skipped: they are how a record refers to the
    member list, so they cannot contribute to building it. A member who appears
    only inside an `all` row is therefore invisible here, which is correct --
    `all` expands to whoever the explicit cells named.

    Raises:
        ValueError: if a record names more than one creditor. Splitting a record
            across several people who each fronted part of it is not supported;
            the amount a record carries is one payment by one person.
    """
    members = set()
    for index, row in df.iterrows():
        if not is_all_selector(row[cfg.col_creditor]):
            creditor = split_names(row[cfg.col_creditor], cfg.separator)
            if len(creditor) > 1:  # Currently only support single creditor
                raise ValueError("Currently only support single creditor. "
                                 "Please specify only one creditor in each record.")
            members.update(creditor)
        if not is_all_selector(row[cfg.col_debtor]):
            members.update(
                split_names(row[cfg.col_debtor], cfg.separator)
            )
    return members

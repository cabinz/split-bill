"""Splitting an amount so that the parts add back up to it.

`total / n` does not divide evenly in cents, and the leftover has to go somewhere.
V1 let it dissolve into floating point: each share was `total / n` at full
precision, rounded only when printed. Every individual figure looked right and the
column did not add up -- on a real bill, positive nets summed to 15,937.09 and
negative to 15,937.08.

For a report whose entire purpose is to be checked, that one cent is fatal. Somebody
will add up the appendix, find it short, and stop believing any of it -- and they
will be right to, because a report that cannot survive its own arithmetic has not
earned the trust it is asking for.

So the remainder is assigned, deliberately and reproducibly, rather than left to
rounding. Someone gets the extra cent, it says who, and every column adds up.
"""

from typing import List

# Everything here works in whole cents internally. Two decimal places is an
# assumption about the currency -- fine for CNY, HKD, USD; wrong for JPY (no minor
# unit) and for KWD (three). Making that configurable, and taking the tolerance out
# of the solver while at it, is ctx/feature-integer-minor-units.md.
MINOR_UNITS_PER_MAJOR = 100


def to_minor(amount: float) -> int:
    """An amount in whole cents, rounded to the nearest.

    `round`, not `int`: `1.15 * 100` is 114.99999999999999 in binary floating point,
    and truncating that gives 114¢ for an amount somebody wrote as one dollar
    fifteen.

    Exact half-cents go to even, which is `round`'s behaviour and is kept
    deliberately -- an amount lands on one only through currency conversion, and
    rounding those up every time would put a small bias in the same direction on
    every converted record. See tests/test_money.py.
    """
    return int(round(amount * MINOR_UNITS_PER_MAJOR))


def from_minor(minor: int) -> float:
    """Cents back to a major-unit amount, exact at two decimal places."""
    return minor / MINOR_UNITS_PER_MAJOR


def round_money(amount: float) -> float:
    """An amount snapped to whole cents.

    Applied to a record's total before it is split, so that the total the appendix
    prints is the same number the shares beneath it add up to.
    """
    return from_minor(to_minor(amount))


def split_evenly(total: float, n: int) -> List[float]:
    """Split `total` into `n` shares that each land on a cent and sum to it exactly.

    The first `remainder` shares are one cent larger than the rest. Which members
    those are is the caller's decision -- `loader.ledger` gives them to the
    earliest-sorting names, so the allocation is reproducible rather than dependent
    on the order a spreadsheet happened to list people in.

    Args:
        total: The amount to split.
        n: How many ways. Must be positive.

    Returns:
        `n` shares, descending by at most one cent, summing to `round_money(total)`.

    >>> split_evenly(100.0, 3)
    [33.34, 33.33, 33.33]
    >>> sum(split_evenly(100.0, 3)) == 100.0
    True
    """
    if n <= 0:
        raise ValueError(f"cannot split {total} between {n} people")

    base, remainder = divmod(to_minor(total), n)
    return [from_minor(base + (1 if i < remainder else 0)) for i in range(n)]

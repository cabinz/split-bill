"""Generate random-but-valid bills, for checking the refactor at volume.

Plan §4.10's most valuable idea: with a reference implementation on hand, "I cannot
proofread 1200 moved lines" stops being a problem to solve and becomes a problem to
delegate. A few hundred generated bills cover combinations no hand-written corpus
would think to include.

Two constraints shape the generator.

**Every bill must pass validation.** The live path validates and refuses invalid
data; the frozen V1 path never validated at all. A generated bill that trips the
validator would fail on one side for a reason that has nothing to do with the
refactor. So: no empty cells, no multi-creditor records, no `all` in a creditor
column, no name that happens to spell "everyone", and at least one record naming
members explicitly so `all` has something to expand to.

**Awkward cases have to appear on purpose.** Left to uniform chance, the
interesting ones -- a creditor on their own debtor list, a member who only ever
fronts money, a net of exactly zero -- would show up too rarely to count on. The
generator biases towards them and `edge_case_bills()` pins the ones worth having
every run.
"""

from __future__ import annotations

import csv
import io
import random
from typing import List

from tests.bills import Case

# Wide characters exercise the box tables' alignment; the ASCII names keep most
# bills quick to read when one fails. None of these can be mistaken for an
# all-selector, and none contains a separator the generator uses.
NAME_POOL = [
    "Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Heidi",
    "梅", "兰", "竹", "菊",
]

SEPARATORS = [",", "|", ";", "/"]

# Every spelling config.ALL_SELECTOR_ALIASES accepts.
ALL_SPELLINGS = ["all", "*", "ALL", "All", "所有", "所有人"]

CURRENCIES = ["HKD", "KRW", "USD", "CNY"]

RATES_TO_HKD = {"KRW": 0.0057715, "USD": 7.8, "CNY": 1.0842}


def _amount(rng: random.Random) -> str:
    """An amount, sometimes written with thousand separators.

    Group-separated amounts are the reason `clean_amount_column` exists, and they
    interact with CSV quoting whenever the separator is also a comma.
    """
    style = rng.random()
    if style < 0.12:
        return f"{rng.randrange(1000, 99999):,}.{rng.randrange(0, 100):02d}"
    if style < 0.2:
        # Odd amounts are where uneven division shows up.
        return str(rng.randrange(1, 1000) + rng.choice([0.01, 0.33, 0.07, 0.5]))
    if style < 0.25:
        return "0"  # a warning, not an error: the record simply does nothing
    return str(rng.randrange(1, 5000))


def _debtor_cell(rng: random.Random, members: List[str], creditor: str,
                 separator: str, allow_all: bool) -> str:
    """Who shared a record. Deliberately lumpy."""
    roll = rng.random()
    if allow_all and roll < 0.2:
        return rng.choice(ALL_SPELLINGS)
    if roll < 0.35:
        return rng.choice(members)  # one debtor: no split at all
    if roll < 0.55 and len(members) > 1:
        # The creditor on their own debtor list: a share that is not lending.
        others = rng.sample([m for m in members if m != creditor],
                            k=rng.randint(1, len(members) - 1))
        return separator.join([creditor] + others)
    k = rng.randint(1, len(members))
    return separator.join(rng.sample(members, k=k))


def random_bill(seed: int) -> Case:
    """One bill, reproducible from its seed alone."""
    rng = random.Random(seed)

    members = rng.sample(NAME_POOL, k=rng.randint(2, 6))
    separator = rng.choice(SEPARATORS)
    n_records = rng.randint(1, 25)

    multi_currency = rng.random() < 0.35
    std_currency = "HKD" if multi_currency else None
    currencies = rng.sample(CURRENCIES, k=rng.randint(1, 3)) if multi_currency else []
    if multi_currency and "HKD" not in currencies:
        currencies.append("HKD")

    header = ["Creditor", "Debtor", "Amount"]
    if multi_currency:
        header.append("Currency")
    # Descriptive columns some of the time, so both the with- and without-metadata
    # paths get exercised.
    with_meta = rng.random() < 0.4
    if with_meta:
        header = ["Date", "Category", "Item"] + header

    rows = []
    for index in range(n_records):
        creditor = rng.choice(members)
        # The first record must name members explicitly: `all` expands to whoever
        # the explicit cells mentioned, so a bill of nothing but `all` has no members.
        cell = _debtor_cell(rng, members, creditor, separator,
                            allow_all=index > 0)
        row = [creditor, cell, _amount(rng)]
        if multi_currency:
            row.append(rng.choice(currencies))
        if with_meta:
            row = [
                f"2030-0{rng.randint(1, 9)}-{rng.randint(10, 28)}",
                rng.choice(["Food", "Transport", "Stay", "餐费", "交通"]),
                f"item-{index:03d}",
            ] + row
        rows.append(row)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)

    rates = tuple(
        (currency, "HKD", RATES_TO_HKD[currency])
        for currency in currencies
        if currency != "HKD"
    )
    return Case(
        name=f"fuzz{seed:05d}",
        csv=buffer.getvalue(),
        separator=separator,
        std_currency=std_currency,
        rates=rates,
    )


def edge_case_bills() -> List[Case]:
    """The §4.10 list, stated outright rather than left to chance."""
    return [
        Case(name="fz_single_record",
             csv="Creditor,Debtor,Amount\nAlice,Bob,1\n"),
        Case(name="fz_creditor_only_debtor",
             csv="Creditor,Debtor,Amount\nAlice,Alice,50\n"),
        Case(name="fz_pure_creditor",
             csv="Creditor,Debtor,Amount\nAlice,\"Bob, Carol\",90\n"),
        Case(name="fz_exact_zero_net",
             csv=("Creditor,Debtor,Amount\n"
                  "Alice,Bob,40\n"
                  "Bob,Alice,40\n")),
        Case(name="fz_zero_amount",
             csv="Creditor,Debtor,Amount\nAlice,Bob,0\nAlice,Bob,10\n"),
        Case(name="fz_thousands_and_all",
             csv=("Creditor,Debtor,Amount\n"
                  "Alice,\"Bob, Carol\",\"12,345.67\"\n"
                  "Bob,all,\"1,000\"\n")),
        Case(name="fz_indivisible_by_three",
             csv="Creditor,Debtor,Amount\nAlice,\"Alice, Bob, Carol\",100\n"),
        Case(name="fz_pipe_separator",
             csv="Creditor,Debtor,Amount\nAlice,Bob|Carol|Dave,100\n",
             separator="|"),
        Case(name="fz_cjk_names",
             csv="Creditor,Debtor,Amount\n梅,\"兰, 竹, 菊\",1000\n菊,梅,250\n"),
        Case(name="fz_every_all_spelling",
             csv=("Creditor,Debtor,Amount\n"
                  "Alice,\"Bob, Carol\",30\n"
                  + "".join(f"Alice,{spelling},60\n" for spelling in ALL_SPELLINGS))),
        Case(name="fz_multi_currency",
             csv=("Creditor,Debtor,Amount,Currency\n"
                  "Alice,\"Bob, Carol\",30000,KRW\n"
                  "Bob,all,45.5,USD\n"
                  "Carol,Alice,120,HKD\n"),
             std_currency="HKD",
             rates=(("KRW", "HKD", 0.0057715), ("USD", "HKD", 7.8))),
        Case(name="fz_one_member_everywhere",
             csv=("Creditor,Debtor,Amount\n"
                  "Alice,Bob,10\nAlice,Bob,20\nAlice,Bob,30\n")),
    ]

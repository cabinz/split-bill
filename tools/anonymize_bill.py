"""Turn a real bill into a committable test fixture.

The end-to-end baseline fixture (``tests/fixtures/bill_realistic.csv``) has to
look like a real trip -- 150-odd records, seven members, CJK column names, no
currency column -- because that is the shape Phase 0 has to keep producing
byte-identically. A real bill cannot be committed as-is, so it is passed
through here first.

What is rewritten:

* member names -> positional placeholders (the Heavenly Stems, Chinese's
  A/B/C/D), so a name is still one wide character and column widths behave the
  same way
* item descriptions -> ``<category>-NN``, numbered per category
* dates -> shifted onto a synthetic month, keeping the gaps between them
* free-text notes -> emptied, column kept

What is deliberately left alone: every amount, every debtor grouping, and the
row order. Anonymisation therefore yields an *isomorphic* bill -- the graph, the
per-member figures and the settlement scheme are the real ones with the labels
swapped -- which is what makes the fixture worth having as a baseline.

The mapping is derived from the input (first appearance order), never spelled
out here, so this file leaks nothing about the bill it was run on.

Usage:
    python tools/anonymize_bill.py <real-bill.csv> <fixture.csv>
"""

from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

# Chinese's "Person A, Person B, ..." -- one wide character each, like the real
# single-character nicknames they stand in for.
NAME_PLACEHOLDERS = "甲乙丙丁戊己庚辛壬癸"

# Far enough from any real trip to be obviously synthetic.
BASE_DATE = date(2030, 5, 1)

COL_DATE = "日期"
COL_CATEGORY = "类型"
COL_ITEM = "项目"
COL_CREDITOR = "付款人"
COL_DEBTOR = "参与人"
COL_NOTE = "备注"

SEP = ","


def build_name_map(rows: list[dict]) -> dict[str, str]:
    """Map each member onto a placeholder, in order of first appearance."""
    order: list[str] = []
    for row in rows:
        for cell in (row[COL_CREDITOR], row[COL_DEBTOR]):
            for name in cell.split(SEP):
                name = name.strip()
                if name and name not in order:
                    order.append(name)
    if len(order) > len(NAME_PLACEHOLDERS):
        raise ValueError(
            f"{len(order)} members but only {len(NAME_PLACEHOLDERS)} placeholders"
        )
    return {name: NAME_PLACEHOLDERS[i] for i, name in enumerate(order)}


def build_date_map(rows: list[dict]) -> dict[str, str]:
    """Shift the dates onto BASE_DATE, preserving the intervals between them."""
    originals = sorted({row[COL_DATE].strip() for row in rows})
    first = date.fromisoformat(originals[0])
    return {
        original: (BASE_DATE + (date.fromisoformat(original) - first)).isoformat()
        for original in originals
    }


def build_item_map(rows: list[dict]) -> dict[tuple[str, str], str]:
    """Replace each item with a serial number within its category."""
    item_map: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}
    for row in rows:
        category, item = row[COL_CATEGORY].strip(), row[COL_ITEM].strip()
        key = (category, item)
        if key not in item_map:
            counters[category] = counters.get(category, 0) + 1
            item_map[key] = f"{category}-{counters[category]:02d}"
    return item_map


def anonymize(src: Path, dst: Path) -> None:
    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    names = build_name_map(rows)
    dates = build_date_map(rows)
    items = build_item_map(rows)

    def rename(cell: str) -> str:
        return SEP.join(names[n.strip()] for n in cell.split(SEP) if n.strip())

    for row in rows:
        row[COL_ITEM] = items[(row[COL_CATEGORY].strip(), row[COL_ITEM].strip())]
        row[COL_DATE] = dates[row[COL_DATE].strip()]
        row[COL_CREDITOR] = rename(row[COL_CREDITOR])
        row[COL_DEBTOR] = rename(row[COL_DEBTOR])
        if COL_NOTE in row:
            row[COL_NOTE] = ""

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} records, {len(names)} members -> {dst}")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    anonymize(Path(sys.argv[1]), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

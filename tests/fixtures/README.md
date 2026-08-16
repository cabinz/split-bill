# Test fixtures

## `bill_realistic.csv`

A real group-trip bill run through `tools/anonymize_bill.py`. It is the
end-to-end baseline for `tests/test_baseline.py`: the only fixture in the suite
at the scale the tool is actually used at.

| | |
|---|---|
| records | 153 |
| members | 7, one wide character each (`甲` … `庚`) |
| columns | `日期` `类型` `项目` `金额` `付款人` `参与人` `备注` |
| currency column | none, so the CLI runs currency-agnostic |
| total | 37,986.31 |
| settlement | 6 transfers |

### What the anonymiser changed

Member names, item descriptions, dates and free-text notes. Nothing else:
**every amount and every debtor grouping is the original**, and so is the row
order. The bill is therefore isomorphic to the real one -- the graph, the
per-member figures and the settlement scheme are the real results with the
labels swapped. That is what makes it usable as a baseline rather than merely
as sample data.

### Why this fixture earns its place

Three properties no hand-written three-row bill has:

- **CJK throughout**, in column names and member names, which is what the box
  tables' width alignment exists for
- **Currency-agnostic**, the path taken when no `--standard_currency` is given
  and there is no currency column -- the common case in practice, and the one
  least covered elsewhere
- **The rounding artefact from plan §9.1.** At full float precision the nets
  cancel; rounded to the cent for display they do not. Positive nets sum to
  15,937.09 and negative nets to 15,937.08. Anyone who adds up the column finds
  a cent missing, which is exactly what step 0h sets out to remove

### Regenerating

```bash
python tools/anonymize_bill.py <real-bill.csv> tests/fixtures/bill_realistic.csv
```

Real bills live in `fcbk/`, which is gitignored. Keep it that way.

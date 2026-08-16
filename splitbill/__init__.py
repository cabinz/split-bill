"""SplitBill: turn a spreadsheet of who-paid-for-what into the fewest transfers.

The package is three layers with a `Report` between them and the outside world; see
`ctx/v2_plan.md` §4.2, or the docstrings on `loader`, `settle` and `render`.

Re-exported here is the one call that runs all three. Everything else is reached
through its own layer, deliberately -- a top level that re-exports each layer's
internals is how the dependency rules in §4.5 stop being checkable.
"""

from .pipeline import analyze_file

__all__ = ["analyze_file"]

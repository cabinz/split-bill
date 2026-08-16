"""Regenerate the committed CLI baselines in `tests/fixtures/`.

`tests/test_differential.py::test_rendered_output_matches_snapshot` compares the
live CLI against these files. Regenerating them is how an *intended* change to
the report gets recorded -- plan step 0h, for instance, moves several figures by
a cent on purpose.

Run it deliberately, read the resulting diff, and commit it alongside the change
that caused it. Running it to make a red test green defeats the entire point of
having a baseline.

    uv run python tools/refresh_baselines.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.differential import render_cli  # noqa: E402
from tests.test_differential import CORPUS, FIXTURES, SNAPSHOTS  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for case_name, snapshot_name in sorted(SNAPSHOTS.items()):
            case = next(c for c in CORPUS if c.name == case_name)
            output = render_cli(case.materialize(tmp_dir), case, module="splitbill")
            target = FIXTURES / snapshot_name
            changed = (
                not target.exists()
                or target.read_text(encoding="utf-8") != output
            )
            target.write_text(output, encoding="utf-8")
            print(f"{'updated' if changed else 'unchanged'}: {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

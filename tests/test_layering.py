"""The dependency rules from plan §4.5, checked by reading the imports.

The three-layer split is only worth the trouble if the arrows keep pointing one way,
and that is the kind of thing no reviewer reliably catches. An `import pandas` in the
solver, or a `render` module reaching back into `loader` for a figure the Report does
not carry, both work perfectly and both quietly undo the split. Six months later the
layers are a naming convention.

So the table is machine-checked. Every `import` in every module is read out of the AST
and held against what that module is allowed to see:

    config / utils   the standard library, and nothing from this project
    loader/*         config, utils, pandas
    settle/*         config, utils          -- not pandas, not loader
    report           config, utils, loader, settle (types only)
    render/*         config, utils, report, pandas
    pipeline         anything
    __main__         anything

Two of those carry most of the weight. `settle` takes
`Iterable[tuple[str, str, float]]` and returns transfers, so layer 1 can be rewritten
entirely without the solver or its 328-line correctness suite noticing -- which is
exactly what happened during Phase 0. And `render` sees only a `Report`, so the
browser and the terminal cannot disagree about what a member owes; there is one set of
figures and both of them read it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "splitbill"

# Third-party names a module may import. The standard library is always allowed --
# enumerating it would be a maintenance chore that catches nothing.
THIRD_PARTY = {"pandas", "numpy"}

# module (as a `splitbill.`-relative dotted path) -> what it may import from the
# project, plus which third-party packages. `None` means "anything".
RULES: dict[str, dict | None] = {
    # The package root re-exports the one call that runs all three layers, so it is
    # allowed to see the assembly point and nothing else.
    "__init__": {"project": {"pipeline"}, "third_party": set()},
    "config": {"project": set(), "third_party": set()},
    "utils": {"project": set(), "third_party": set()},
    "loader": {"project": {"config", "utils"}, "third_party": {"pandas"}},
    "settle": {"project": {"config", "utils"}, "third_party": set()},
    "report": {"project": {"config", "utils", "loader", "settle"},
               "third_party": {"pandas"}},
    "render": {"project": {"config", "utils", "report"}, "third_party": {"pandas"}},
    "pipeline": None,
    "__main__": None,
    # The HTTP service. Above the layers rather than in `render/`, and for a reason
    # worth stating: `render` may not import `pipeline`, because the moment layer 3
    # can reach past the Report the browser and the terminal can disagree about what
    # somebody owes. But a server has to drive the pipeline -- that is what a server
    # is. So the payload shaping is `render/web.py`, which sees only a Report and
    # obeys the rule, and the driving is here, next to `__main__`.
    "serve": None,
}


def modules() -> list[Path]:
    """Every Python file in the package."""
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def dotted(path: Path) -> str:
    """`splitbill/loader/ledger.py` -> `loader.ledger`."""
    relative = path.relative_to(PACKAGE).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    return ".".join(parts) if parts else "__init__"


def rule_for(module: str) -> dict | None:
    """The most specific rule covering `module`.

    `loader.ledger` is governed by `loader` unless it has an entry of its own, so a
    package's rule covers everything inside it without every file being listed.
    """
    if module in RULES:
        return RULES[module]
    for prefix in sorted(RULES, key=len, reverse=True):
        if module.startswith(prefix + "."):
            return RULES[prefix]
    pytest.fail(f"{module} is not covered by the §4.5 table -- add it to RULES")


def imports_of(path: Path, package_parts: list[str] | None = None
               ) -> list[tuple[str, int]]:
    """Every imported top-level name in `path`, with its line number.

    Relative imports are resolved against the module's own package, so
    `from ..utils.money import ...` inside `loader/ledger.py` comes back as `utils`
    -- the same name an absolute import of it would give.

    Args:
        package_parts: The module's package, as path components. Derived from `path`
            when it is inside the package; passed explicitly for files that are not,
            which is how the checker gets tested on a planted violation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if package_parts is None:
        package_parts = dotted(path).split(".")
        if path.name != "__init__.py":
            package_parts = package_parts[:-1]

    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    found.append((node.module.split(".")[0], node.lineno))
                continue
            # `level` dots up from this module's package.
            base = package_parts[: len(package_parts) - (node.level - 1)]
            target = base + (node.module.split(".") if node.module else [])
            if target:
                found.append((target[0], node.lineno))
            else:
                # `from . import x` -- names within the same package.
                for alias in node.names:
                    found.append((alias.name, node.lineno))
    return found


PROJECT_TOP_LEVEL = {"config", "utils", "loader", "settle", "render", "report",
                     "pipeline", "splitbill"}


@pytest.mark.parametrize("path", modules(), ids=dotted)
def test_module_only_imports_what_its_layer_may_see(path: Path):
    module = dotted(path)
    rule = rule_for(module)
    if rule is None:
        return  # pipeline and __main__ assemble the layers; they may see everything

    own_top_level = module.split(".")[0]
    violations = []
    for name, lineno in imports_of(path):
        if name == "splitbill":
            violations.append(f"{path.name}:{lineno} imports the package by name")
            continue
        if name in PROJECT_TOP_LEVEL:
            if name != own_top_level and name not in rule["project"]:
                violations.append(
                    f"{path.name}:{lineno} imports `{name}`, which {module} may not "
                    f"see (allowed: {sorted(rule['project']) or 'nothing'})"
                )
        elif name in THIRD_PARTY and name not in rule["third_party"]:
            violations.append(
                f"{path.name}:{lineno} imports `{name}`, which {module} may not use"
            )

    assert not violations, "\n".join(violations)


class TestTheRulesThatMatterMost:
    """The two that the rest of the design rests on, stated as their own tests.

    The parametrised check above would catch these too. They are here because a
    failure should say what broke rather than which file broke it -- and because
    these two are the ones worth arguing about before changing.
    """

    def test_settle_does_not_import_pandas(self):
        """The solver takes triples and returns transfers.

        This is what let layer 1 be taken apart and rewritten without
        `test_graph_correctness.py` -- the most valuable test in the repo -- changing
        by a line.
        """
        for path in PACKAGE.joinpath("settle").rglob("*.py"):
            names = {name for name, _ in imports_of(path)}
            assert "pandas" not in names, path

    def test_settle_does_not_import_loader(self):
        for path in PACKAGE.joinpath("settle").rglob("*.py"):
            names = {name for name, _ in imports_of(path)}
            assert "loader" not in names, path

    def test_render_sees_only_the_report(self):
        """One set of figures, read by both the terminal and the browser.

        If `render` could reach into `loader` for something the Report does not carry,
        the web view and the CLI would be free to disagree -- and the bug that
        produces looks like arithmetic, not like a layering mistake.
        """
        for path in PACKAGE.joinpath("render").rglob("*.py"):
            names = {name for name, _ in imports_of(path)}
            assert "loader" not in names, path
            assert "settle" not in names, path

    def test_loader_does_not_import_settle(self):
        """Layer 1 hands over a ledger; building the graph from it is layer 2's job.

        `loader/source.py` did import `settle`, for the `Loader` compatibility shell
        that had to expose `get_graph()`. Deleting the shell at step 0i is what made
        this assertion possible.
        """
        for path in PACKAGE.joinpath("loader").rglob("*.py"):
            names = {name for name, _ in imports_of(path)}
            assert "settle" not in names, path
            assert "render" not in names, path
            assert "report" not in names, path

    def test_config_and_utils_depend_on_nothing(self):
        """They are imported by every layer, so anything they import is imported
        everywhere."""
        for path in [PACKAGE / "config.py"] + list(
            PACKAGE.joinpath("utils").rglob("*.py")
        ):
            for name, lineno in imports_of(path):
                assert name not in PROJECT_TOP_LEVEL - {"utils", "config"}, (
                    f"{path.name}:{lineno} imports {name}"
                )
                assert name not in THIRD_PARTY, f"{path.name}:{lineno} imports {name}"


class TestTheCheckerItself:
    """A checker that silently passed everything would be worse than none."""

    def test_every_module_is_covered_by_a_rule(self):
        for path in modules():
            rule_for(dotted(path))  # fails the test if uncovered

    def test_it_finds_a_planted_violation(self, tmp_path):
        """The check is only meaningful if it can fail.

        Written as though it were `splitbill/settle/planted.py`, which may see
        neither, so both of these are violations the parametrised test would report.
        """
        planted = tmp_path / "planted.py"
        planted.write_text("import pandas\nfrom ..loader import load\n",
                           encoding="utf-8")
        names = {name for name, _ in imports_of(planted, ["settle"])}
        assert names == {"pandas", "loader"}

        rule = rule_for("settle")
        assert "pandas" not in rule["third_party"]
        assert "loader" not in rule["project"]

    def test_relative_imports_resolve_to_their_top_level(self):
        """`from ..utils.money import split_evenly` inside `loader/ledger.py` has to
        read as `utils`, or every relative import would pass unexamined."""
        names = {name for name, _ in imports_of(PACKAGE / "loader" / "ledger.py")}
        assert "utils" in names

    def test_dotted_names_a_package_init(self):
        assert dotted(PACKAGE / "loader" / "__init__.py") == "loader"
        assert dotted(PACKAGE / "loader" / "ledger.py") == "loader.ledger"

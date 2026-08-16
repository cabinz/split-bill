"""The committed frontend build, and whether it still matches its source.

Built output is in the repository. That is not the usual advice, and the reason is
usability: without it, `pip install splitbill && splitbill serve` shows a placeholder
unless the user also has node and runs a build, and a tool most people cannot run is
not a tool. The cost is a class of mistake that has no other guard -- edit
`webui/src`, forget `make webui`, and the page silently keeps serving the previous
version while the tests stay green and the diff looks complete.

So the check is here instead. It cannot verify the bundle is *correct* -- that is
`webui/e2e/smoke.mjs`, which drives the real page in a real browser -- only that it
exists, that it is wired up, and that it is not older than the source it came from.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "webui"
BUILD = ROOT / "splitbill" / "render" / "webui"
INDEX = BUILD / "index.html"

built = pytest.mark.skipif(
    not INDEX.is_file(),
    reason="no frontend build in this checkout -- run `make webui`",
)


class TestTheBuildIsPresentAndWiredUp:
    @built
    def test_index_exists_and_loads_a_bundle(self):
        html = INDEX.read_text(encoding="utf-8")
        assert '<div id="app">' in html
        assert re.search(r'src="[^"]*assets/index-[^"]*\.js"', html), html

    @built
    def test_every_asset_the_index_references_is_present(self):
        """A build half-copied is worse than none: the page loads and then fails."""
        html = INDEX.read_text(encoding="utf-8")
        referenced = re.findall(r'(?:src|href)="\./([^"]+)"', html)
        assert referenced, "index.html references no assets at all"
        for asset in referenced:
            assert (BUILD / asset).is_file(), f"{asset} referenced but not built"

    @built
    def test_the_stylesheet_carries_the_print_rules(self):
        """§7.4 and §9.2: the printed artefact is the primary one. If the print
        stylesheet did not survive minification, printing is silently a screenshot."""
        css = "".join(
            path.read_text(encoding="utf-8")
            for path in (BUILD / "assets").glob("*.css")
        )
        assert "@media print" in css
        assert "@page" in css
        assert "table-header-group" in css  # repeated headers on multi-page tables
        assert "break-inside" in css
        # The print view's own root, which the screen view has no rule for and cannot
        # reach. Its absence would mean the two stylesheets had been merged back.
        assert ".print-root" in css

    @built
    def test_the_screen_view_is_not_printed(self):
        """The printed report is a different document, not this page with the controls
        hidden. If this rule is missing, printing lays the screen view on the paper
        underneath the print view -- two reports on one page."""
        css = "".join(
            path.read_text(encoding="utf-8")
            for path in (BUILD / "assets").glob("*.css")
        )
        assert re.search(r"\.screen-root\s*\{\s*display\s*:\s*none", css), (
            "no rule hiding the screen view when printing")

    @built
    def test_no_canvas_renderer_in_the_bundle(self):
        """ECharts' canvas renderer prints as a blurred mosaic, so `src/echarts.ts`
        registers only the SVG one. If the canvas renderer is in the bundle, something
        imported the convenience entry point and the guarantee is gone."""
        js = "".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (BUILD / "assets").glob("*.js")
        )
        # The canvas renderer's registered name, which appears only if it is included.
        assert "CanvasRenderer" not in js


class TestTheBuildIsNotStale:
    @built
    def test_no_source_file_is_newer_than_the_build(self):
        """Catches the mistake this file exists for: editing the source and shipping
        the previous bundle.

        Modification times, which are imperfect -- a fresh clone has arbitrary ones --
        so this is a warning that fails rather than a proof. If it fires spuriously,
        `make webui` costs two seconds and settles it.
        """
        newest_build = max(
            path.stat().st_mtime for path in BUILD.rglob("*") if path.is_file()
        )
        sources = [
            path
            for path in (SOURCE / "src").rglob("*")
            if path.is_file() and path.suffix in {".ts", ".vue", ".css"}
        ]
        assert sources, "no frontend source found"

        stale = [
            path.relative_to(ROOT)
            for path in sources
            if path.stat().st_mtime > newest_build + 1
        ]
        assert not stale, (
            "these are newer than the committed build -- run `make webui`:\n  "
            + "\n  ".join(str(path) for path in stale)
        )


class TestTheSourceIsConfiguredAsExpected:
    """Assertions about the source tree, so they hold even without a build."""

    def test_vite_builds_where_serve_looks(self):
        from splitbill.serve import STATIC_ROOT

        config = (SOURCE / "vite.config.ts").read_text(encoding="utf-8")
        assert "'../splitbill/render/webui'" in config
        assert STATIC_ROOT == BUILD

    def test_dependencies_are_pinned_exactly(self):
        """No carets. The build output is committed, so a floating dependency means
        the bundle in the repository cannot be reproduced from the source beside it."""
        manifest = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies"):
            for name, version in manifest.get(section, {}).items():
                assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
                    f"{name} is {version!r}; pin it exactly")

    def test_echarts_is_registered_piecemeal_not_wholesale(self):
        """`import * as echarts from 'echarts'` costs 1.13 MB and brings in maps,
        gauges and a WebGL bridge for a report that draws bars and one Sankey."""
        for path in (SOURCE / "src").rglob("*.vue"):
            text = path.read_text(encoding="utf-8")
            assert "from 'echarts'" not in text, (
                f"{path.name} imports the ECharts entry point; use presentation/echarts")

    def test_only_the_svg_renderer_is_registered(self):
        registry = (SOURCE / "src" / "presentation" / "echarts.ts").read_text(
            encoding="utf-8")
        assert "SVGRenderer" in registry
        assert "CanvasRenderer" not in registry


def code_of(path: Path) -> str:
    """A source file with its comments removed.

    These files explain at length why the old print path had to open every `<details>`
    on `beforeprint`, so a test that greps the raw text for `beforeprint` fails on the
    comment describing its removal. Stripping comments first is the difference between
    asserting about the code and asserting about the prose around it.

    Crude on purpose: it does not understand a `//` inside a string literal. There are
    none in these files, and a real parser would be a dependency for a grep.
    """
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)      # /* block */
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)     # <!-- html -->
    text = re.sub(r"(?m)^\s*//.*$", "", text)                   # // whole line
    return text


class TestTheTwoViewsAreActuallySeparate:
    """The dependency rules the screen/print split rests on.

    `webui/e2e/print.mjs` checks that the two views *say* the same thing, by reading
    both DOMs with one function and comparing every figure. These check the thing that
    keeps them able to: that neither view can reach into the other, and that the shared
    layer they both draw from does not reach back into either.

    Cheap, structural, and worth having in Python because they hold without a build --
    which is what makes them run on a machine with no node.
    """

    PRESENTATION = SOURCE / "src" / "presentation"
    SCREEN = SOURCE / "src" / "screen"
    PRINT = SOURCE / "src" / "print"

    def test_the_shared_layer_imports_neither_view(self):
        """A presentation module that imported a component would make the two views
        each other's dependency by transitivity, and there would be no shared layer
        left -- only a cycle."""
        for path in self.PRESENTATION.rglob("*.ts"):
            text = code_of(path)
            for forbidden in ("../screen/", "../print/", ".vue"):
                assert forbidden not in text, (
                    f"presentation/{path.name} reaches into a view: {forbidden}")

    def test_the_print_view_does_not_import_the_screen_view(self):
        """§7: the printed report may not depend on a screen component. That is the
        rule that lets the screen view adopt a virtualised table without breaking the
        appendix, and the one that would silently rot first."""
        for path in self.PRINT.rglob("*"):
            if path.suffix not in {".ts", ".vue"}:
                continue
            assert "screen/" not in code_of(path), (
                f"print/{path.name} imports from screen/")

    def test_the_screen_view_touches_only_the_print_controller(self):
        """The screen view has to be able to start a print, so it may import the
        controller and the host that mounts it. It may not import a print *section*:
        rendering one inside the page would put the two views back in one tree."""
        allowed = {"../print/controller", "../print/PrintHost.vue", "../print/channel"}
        for path in self.SCREEN.rglob("*"):
            if path.suffix not in {".ts", ".vue"}:
                continue
            for match in re.findall(r"from '([^']*print/[^']*)'", code_of(path)):
                assert match in allowed, f"{path.name} imports {match}"

    def test_neither_view_parses_the_other_s_dom(self):
        """§7's "forbidden" list: generating one view by reading the other's DOM. It
        would reintroduce every coupling the split removed, and it is exactly the
        shortcut somebody reaches for when a figure is easier to scrape than to
        plumb."""
        for root, other in ((self.PRINT, "screen-root"), (self.SCREEN, "print-root")):
            for path in root.rglob("*"):
                if path.suffix not in {".ts", ".vue"}:
                    continue
                text = code_of(path)
                assert "querySelector" not in text or other not in text, (
                    f"{path.name} looks up the other view's DOM")

    def test_the_table_library_stays_in_the_screen_view(self):
        """`@tanstack/vue-table` drives the screen's paging, sorting and filtering, and a
        paged table is the one thing the printed appendix must never be: its row model holds
        10 of 668 rows, and printing whatever page was on screen is exactly the failure the
        appendix exists to prevent.

        The screen may import it. The print view may not, and neither may the shared layer --
        a selector that returned a row model would put the paging library on the printed
        report's path without either view importing it."""
        for root in (self.PRINT, self.PRESENTATION):
            for path in root.rglob("*"):
                if path.suffix not in {".ts", ".vue"}:
                    continue
                assert "@tanstack" not in code_of(path), (
                    f"{path.name} imports the screen's table library")

    def test_no_translation_hard_codes_a_section_number(self):
        """The numbers come from what renders, so a translated sentence may not contain one.

        "Section 3 shows where it came from" was true until a section above it became
        conditional, and then it was a sentence pointing at the wrong chapter in every
        language at once -- with nothing in the report to reveal it. Numbers reach the prose
        as parameters, from the resolved structure.

        Looks for a digit next to the words for a section or an appendix, in either language,
        which is what a hard-coded reference looks like. Bare digits are everywhere in these
        strings legitimately -- "1 unit of", "{count} rows" -- so the pattern has to be the
        reference itself rather than any number."""
        text = code_of(SOURCE / "src" / "presentation" / "i18n.ts")
        offenders = [
            match.group(0)
            for match in re.finditer(
                r"(?:[Ss]ection|[Aa]ppendix|第)\s*\d+(?:\.\d+)?\s*(?:节)?"
                r"|\b\d+\.\d+\s*(?:中|节)",
                text,
            )
        ]
        assert not offenders, (
            "these translations hard-code a section number; pass it as a parameter "
            f"instead: {offenders}")

    def test_the_print_view_has_no_details_element(self):
        """A closed `<details>` renders none of its contents, so anything inside one is
        absent from the printed page unless something opens it first. That something
        used to exist -- a `beforeprint` handler that mutated the DOM and restored it
        afterwards -- and the completeness of the printed report depended on it landing
        before a blocking call. The print view now has no collapsible content at all,
        which is why that handler could be deleted rather than moved."""
        for path in self.PRINT.rglob("*.vue"):
            assert "<details" not in code_of(path), (
                f"print/{path.name} hides content in <details>")

    def test_nothing_installs_a_beforeprint_handler_any_more(self):
        """The print root is laid out at the paper's width in both media, so there is
        nothing to prepare when the print dialog opens. A new `beforeprint` handler
        would mean something had gone back to adjusting the DOM at print time."""
        for path in (SOURCE / "src").rglob("*"):
            if path.suffix not in {".ts", ".vue"}:
                continue
            assert "beforeprint" not in code_of(path), (
                f"{path.name} handles beforeprint")

    def test_the_print_input_is_the_print_view_s_only_input(self):
        """The print sections take a report and a sheet as props and read no module
        state. A print section that imported the controller could observe the live
        screen state, which is the whole thing §5.1 forbids."""
        for path in self.PRINT.glob("Print*.vue"):
            if path.name in {"PrintPreview.vue", "PrintHost.vue"}:
                continue  # the two roots, which legitimately obtain the input
            assert "./controller" not in code_of(path), (
                f"print/{path.name} imports the controller")

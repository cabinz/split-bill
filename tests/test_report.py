"""The Report and the pipeline that assembles it.

The differential harness already checks that the figures are right. What it cannot
check is the shape of the JSON contract, and that is the part a browser will be
written against -- a wrong key or a swapped direction there is a bug nobody notices
until the frontend displays it backwards.

So this covers the §5 contract itself: the keys, the `from`/`to` direction, what
happens when there is no currency and no category column, and the cross-layer net
check that makes the whole thing trustworthy.
"""

import json
from argparse import Namespace
from pathlib import Path

import pytest

from splitbill import pipeline
from splitbill.report import SCHEMA_VERSION, build_report

FIXTURE = Path(__file__).parent / "fixtures" / "bill_realistic.csv"

FIXED_TIME = "2030-06-01T12:00:00+08:00"


def args_for(**overrides) -> Namespace:
    base = dict(col_creditor=None, col_debtor=None, col_tot_amount=None,
                col_currency=None, separator=",", all_selector="all")
    base.update(overrides)
    return Namespace(**base)


def report_for(bill, csv=None, std_currency=None, rates=(), **arg_overrides):
    if csv is not None:
        Path(bill).write_text(csv, encoding="utf-8")
    exrs = pipeline.exchange_rates_from_args(
        std_currency, [f"{b}/{q}={r}" for b, q, r in rates])
    return pipeline.analyze_file(bill, exrs=exrs, args=args_for(**arg_overrides),
                                 generated_at=FIXED_TIME)


@pytest.fixture(scope="module")
def realistic():
    return report_for(FIXTURE)


class TestSummary:
    def test_counts_and_total(self, realistic):
        assert realistic.summary.record_count == 153
        assert realistic.summary.member_count == 7
        assert realistic.summary.transaction_count == 6
        assert realistic.summary.total_spend == pytest.approx(37986.31, abs=0.005)

    def test_schema_version_is_declared(self, realistic):
        assert realistic.schema_version == SCHEMA_VERSION == "2.0"

    def test_positions_are_net_descending(self, realistic):
        nets = [p.net for p in realistic.positions]
        assert nets == sorted(nets, reverse=True)

    def test_settlement_is_far_shorter_than_the_lending_it_replaces(self, realistic):
        """28 real obligations become 6 payments. That compression is the reason a
        counterparty in the settlement is often a stranger, and the reason both
        views have to be reported."""
        assert len(realistic.lending_edges) == 28
        assert len(realistic.settlement) == 6


class TestCrossLayerCheck:
    def test_nets_agree_between_the_layers(self, realistic):
        """Layer 1 reaches each net from the ledger, layer 2 from the graph.

        build_report asserts this while assembling, so reaching here at all means it
        held; the test states the invariant so it cannot be quietly dropped.
        """
        settled = {}
        for edge in realistic.lending_edges:
            settled[edge.creditor] = settled.get(edge.creditor, 0.0) + edge.amount
            settled[edge.debtor] = settled.get(edge.debtor, 0.0) - edge.amount
        for position in realistic.positions:
            assert position.net == pytest.approx(
                settled.get(position.member, 0.0), abs=1e-3), position.member

    def test_a_disagreement_would_fail_loudly(self):
        """The assertion has to bite, or it is decoration.

        A cent moved onto one member's net in the graph, leaving layer 1 untouched,
        is exactly the shape of the bug this guards against.
        """
        from splitbill.loader import load
        from splitbill.settle import settle

        prepared = pipeline.prepare(FIXTURE, args=args_for())
        loaded = load(FIXTURE, cfg=prepared.cfg, frame=prepared.frame, validate=False)
        settled = settle(loaded.ledger.lending_triples())

        tampered = dict(settled.net_flows)
        tampered[next(iter(loaded.positions))] += 1.0
        broken = type(settled)(
            lending_edges=settled.lending_edges,
            settlement=settled.settlement,
            net_flows=tampered,
        )
        with pytest.raises(AssertionError, match="the lending graph says"):
            build_report(loaded, broken)

    def test_both_derivations_of_net_agree(self, realistic):
        for p in realistic.positions:
            assert p.net == pytest.approx(
                p.paid_for_others - p.covered_by_others, abs=1e-3), p.member

    def test_every_share_lands_on_a_whole_cent(self, realistic):
        """Step 0h: no share is ever a fraction of a cent any more.

        This is what makes the appendix checkable -- a reader adding up a column of
        shares gets the total printed above it, exactly. Before 0h each share was
        `total / n` at full precision and the column came up short.
        """
        for entry in realistic.ledger:
            assert entry.share == round(entry.share, 2), entry

    def test_shares_add_up_to_their_record(self, realistic):
        """The other half of the same guarantee, per record rather than per column."""
        totals: dict = {}
        amounts: dict = {}
        for entry in realistic.ledger:
            totals[entry.record_id] = totals.get(entry.record_id, 0.0) + entry.share
            amounts[entry.record_id] = entry.amount_std
        for record_id, total in totals.items():
            assert total == pytest.approx(amounts[record_id], abs=1e-9), record_id

    def test_a_one_cent_obligation_survives_into_the_graph(self, tmp_path):
        """A share of exactly one cent reaches layer 2 intact.

        This test used to assert the opposite, and pinning that was how the defect got
        found. `LendingGraph.add_edge` dropped any edge `is_zero` called zero, and
        `is_zero` uses `abs_tol`, so it is true *at* one cent. Dropping an edge also
        undoes its contribution to both endpoints' nets -- while layer 1 had already
        counted the share in somebody's consumption. So the report showed a member one
        net and the settlement discharged another, a cent at a time.

        `add_edge` now drops an edge only when it has cancelled out exactly. Bob's one
        cent stays on the graph, the layers agree, and the settlement he is given adds
        up to the net he is shown.
        """
        report = report_for(
            tmp_path / "tiny.csv",
            csv=("Creditor,Debtor,Amount\n"
                 "Alice,\"Alice, Bob\",0.02\n"
                 "Carol,\"Alice, Carol\",500\n"),
        )
        by_member = {p.member: p for p in report.positions}

        assert by_member["Bob"].consumption == 0.01
        assert by_member["Bob"].net == pytest.approx(-0.01)

        on_an_edge = {e.creditor for e in report.lending_edges} | {
            e.debtor for e in report.lending_edges
        }
        assert "Bob" in on_an_edge

    def test_the_layers_now_agree_on_every_net(self, tmp_path):
        """The thing that was actually broken, stated directly.

        `build_report` asserts this per member, so a regression fails there first --
        but the assertion allows `_net_tolerance`, and the point of the fix is that
        nothing is using that allowance any more. Checked here at float precision.
        """
        from splitbill.loader import load
        from splitbill.settle import settle

        bill = tmp_path / "tiny.csv"
        bill.write_text(
            "Creditor,Debtor,Amount\n"
            "Alice,\"Alice, Bob\",0.02\n"
            "Carol,\"Alice, Carol\",500\n",
            encoding="utf-8",
        )
        loaded = load(bill)
        settled = settle(loaded.ledger.lending_triples())

        for member, stats in loaded.positions.items():
            assert stats.net == pytest.approx(
                settled.net_flows.get(member, 0.0), abs=1e-9
            ), member

    def test_a_sub_cent_net_is_left_unsettled_rather_than_transferred(self, tmp_path):
        """Bob is owed a cent and nobody is asked to move it.

        `simplest_equiv` treats a net within `ABS_TOL` as settled, so it emits no
        transfer for one. That is a deliberate policy and a defensible one -- a
        one-cent bank transfer is not a thing to ask a person for -- and it is
        different in kind from what was wrong before, where the two layers disagreed
        about what the net *was* and neither the report nor the settlement could be
        checked against the other.

        Written down because it is the residue: the nets are now exact, and the
        settlement still rounds off the last cent. Taking that out too is
        ctx/feature-integer-minor-units.md.
        """
        report = report_for(
            tmp_path / "tiny.csv",
            csv=("Creditor,Debtor,Amount\n"
                 "Alice,\"Alice, Bob\",0.02\n"
                 "Carol,\"Alice, Carol\",500\n"),
        )
        by_member = {p.member: p for p in report.positions}
        assert by_member["Bob"].net == pytest.approx(-0.01)

        moved = [t for t in report.settlement
                 if "Bob" in (t.sender, t.receiver)]
        assert moved == [], "a one-cent transfer is not worth asking for"


class TestJsonContract:
    def test_top_level_keys(self, realistic):
        payload = realistic.to_dict()
        assert set(payload) == {
            "schema_version", "meta", "members", "summary", "positions",
            "settlement", "lending_edges", "ledger",
        }

    def test_settlement_uses_from_and_to(self, realistic):
        """Not creditor/debtor: the counterparty is a by-product of re-pairing nets
        and naming it a creditor would assert a debt that does not exist."""
        first = realistic.to_dict()["settlement"][0]
        assert set(first) == {"from", "to", "amount"}

    def test_from_pays_to(self, realistic):
        """Direction is the one thing here that can be silently backwards."""
        payload = realistic.to_dict()
        by_member = {p["member"]: p for p in payload["positions"]}
        for transfer in payload["settlement"]:
            assert by_member[transfer["from"]]["net"] < 0, "payers owe money"
            assert by_member[transfer["to"]]["net"] > 0, "payees are owed money"

    def test_lending_edges_keep_the_lending_vocabulary(self, realistic):
        first = realistic.to_dict()["lending_edges"][0]
        assert set(first) == {"creditor", "debtor", "amount"}

    def test_ledger_rows_match_the_documented_fields(self, realistic):
        row = realistic.to_dict()["ledger"][0]
        assert set(row) == {
            "record_id", "date", "category", "item", "creditor", "member",
            "share", "amount_raw", "currency_raw", "amount_std",
        }

    def test_column_bindings_report_what_was_detected(self, realistic):
        columns = realistic.to_dict()["meta"]["columns"]
        assert columns["creditor"] == {"name": "付款人", "auto": True}
        # No currency column in this bill at all, which is different from one that
        # was named and turned out to be missing.
        assert columns["currency"] == {"name": None, "auto": False}

    def test_amounts_are_serialised_to_the_cent(self, realistic):
        payload = realistic.to_dict()
        for position in payload["positions"]:
            assert position["consumption"] == round(position["consumption"], 2)

    def test_json_round_trips(self, realistic):
        assert json.loads(realistic.to_json()) == realistic.to_dict()

    def test_cjk_is_not_escaped(self, realistic):
        """A report full of \\uXXXX escapes is not one anybody can read."""
        assert "甲" in realistic.to_json()
        assert "\\u" not in realistic.to_json()


class TestCurrencyAgnostic:
    def test_no_currency_means_null_not_a_guess(self, realistic):
        assert realistic.meta.std_currency is None
        assert realistic.to_dict()["meta"]["std_currency"] is None
        assert realistic.to_dict()["meta"]["exchange_rates"] == []

    def test_currency_agnostic_mode_needs_no_warning(self, realistic):
        assert realistic.meta.warnings == ()

    def test_rates_are_reported_as_supplied(self, tmp_path):
        report = report_for(
            tmp_path / "b.csv",
            csv="Creditor,Debtor,Amount,Currency\nAlice,All,30000,KRW\n",
            std_currency="HKD",
            rates=(("KRW", "HKD", 0.0057715),),
        )
        assert report.to_dict()["meta"]["exchange_rates"] == [
            {"base": "KRW", "quote": "HKD", "rate": 0.0057715}
        ]
        assert report.meta.std_currency == "HKD"


class TestCategories:
    def test_breakdown_sums_to_consumption(self, realistic):
        for position in realistic.positions:
            assert sum(position.by_category.values()) == pytest.approx(
                position.consumption, abs=0.005), position.member

    def test_absent_category_column_gives_empty_not_missing(self, tmp_path):
        report = report_for(
            tmp_path / "b.csv",
            csv="Creditor,Debtor,Amount\nAlice,\"Bob, Carol\",90\n",
        )
        assert all(p.by_category == {} for p in report.positions)
        assert all(p["by_category"] == {} for p in report.to_dict()["positions"])


class TestPipelineSeam:
    def test_prepare_computes_nothing(self):
        prepared = pipeline.prepare(FIXTURE, args=args_for())
        assert prepared.ok
        assert prepared.cfg.bindings["creditor"].name == "付款人"

    def test_prepare_reports_errors_instead_of_raising(self, tmp_path):
        """The CLI prints them and stops; the web layer hands them back with the
        detected columns so they can be corrected in the page. Deciding inside
        prepare() would rule out one of those."""
        bill = tmp_path / "bad.csv"
        bill.write_text("Creditor,Debtor,Amount\nAlice,,90\n", encoding="utf-8")
        prepared = pipeline.prepare(bill, args=args_for())
        assert not prepared.ok
        assert prepared.validation.has_errors()

    def test_analyze_refuses_invalid_data(self, tmp_path):
        bill = tmp_path / "bad.csv"
        bill.write_text("Creditor,Debtor,Amount\nAlice,,90\n", encoding="utf-8")
        prepared = pipeline.prepare(bill, args=args_for())
        with pytest.raises(ValueError, match="validation error"):
            pipeline.analyze(prepared)

    def test_the_sheet_is_read_once(self, tmp_path, monkeypatch):
        """V1 read every bill twice, from two copies of the format table."""
        import splitbill.loader.source as source

        calls = []
        original = source.SUPPORT_FTYPES[".csv"]
        monkeypatch.setitem(
            source.SUPPORT_FTYPES, ".csv",
            lambda path: (calls.append(path), original(path))[1],
        )
        bill = tmp_path / "b.csv"
        bill.write_text("Creditor,Debtor,Amount\nAlice,Bob,10\n", encoding="utf-8")
        pipeline.analyze_file(bill, args=args_for())
        assert len(calls) == 1

    def test_raw_frame_survives_to_the_report(self, realistic):
        """The appendix shows the bill in full, notes column included."""
        assert realistic.raw_frame is not None
        assert "备注" in realistic.raw_frame.columns

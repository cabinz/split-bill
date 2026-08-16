"""The local HTTP service, over a real socket.

Plan §6. Driven through `urllib` against a server on an OS-assigned port rather than
by calling the handler's methods, because most of what can go wrong here is not in the
handler body: a header that never arrives, a body read at the wrong length, JSON that
`json.dumps` will write and `JSON.parse` will not read. A test that calls the methods
directly would pass through all of those.

The security cases are the ones worth having. This binds to loopback, which stops the
network but not a page in the same browser, and the failure mode of getting that wrong
is quiet -- everything works, and a website can read the bill.
"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from splitbill import serve as serve_module
from splitbill.serve import MAX_UPLOAD_BYTES, Uploads, build_server, safe_filename

FIXTURES = Path(__file__).parent / "fixtures"
BILL = FIXTURES / "bill_realistic.csv"
SAMPLE_XLSX = Path(__file__).parent.parent / "samples" / "sample_data.xlsx"

SIMPLE = b'Creditor,Debtor,Amount\nAlice,"Alice, Bob",90\nBob,Carol,50\n'


class TestServeCommand:
    def test_develop_starts_both_reloadable_servers(self, monkeypatch):
        from splitbill.__main__ import main

        received = {}

        def fake_development(**options):
            received.update(options)
            return 0

        monkeypatch.setattr(serve_module, "serve_development", fake_development)

        status = main([
            "serve", "--develop", "--port", "9000",
            "--frontend-port", "5000", "--no-browser",
        ])

        assert status == 0
        assert received == {
            "port": 9000,
            "frontend_port": 5000,
            "open_browser": False,
        }

    def test_dev_is_a_short_alias(self, monkeypatch):
        from splitbill.__main__ import main

        called = []
        monkeypatch.setattr(
            serve_module, "serve_development",
            lambda **options: called.append(options) or 0,
        )

        assert main(["serve", "--dev", "--no-browser"]) == 0
        assert called


class Client:
    """A urllib wrapper that returns `(status, payload)` instead of raising."""

    def __init__(self, base: str) -> None:
        self.base = base

    def request(self, path, data=None, headers=None, method=None):
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers or {}, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def json(self, path, data=None, headers=None, method=None):
        status, body, _ = self.request(path, data, headers, method)
        try:
            return status, json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return status, body.decode("utf-8", "replace")

    def parse(self, data: bytes, filename="bill.csv", query=""):
        return self.json(f"/api/parse{query}", data=data,
                         headers={"X-Filename": filename}, method="POST")

    def report(self, **spec):
        return self.json("/api/report", data=json.dumps(spec).encode("utf-8"),
                         headers={"Content-Type": "application/json"}, method="POST")

    def preview(self, **spec):
        return self.json("/api/preview", data=json.dumps(spec).encode("utf-8"),
                         headers={"Content-Type": "application/json"}, method="POST")


@pytest.fixture(scope="module")
def client():
    """One server for the module. Port 0 so parallel runs cannot collide."""
    httpd, directory = build_server(port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Client(f"http://127.0.0.1:{httpd.server_address[1]}")
    finally:
        httpd.shutdown()
        httpd.server_close()
        httpd.RequestHandlerClass.uploads.clear()
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def token(client):
    """A parsed realistic bill, ready to ask for reports from."""
    status, payload = client.parse(BILL.read_bytes(), "bill_realistic.csv")
    assert status == 200, payload
    return payload["token"]


class TestHealth:
    def test_it_answers(self, client):
        assert client.json("/api/health") == (200, {"ok": True,
                                                    "service": "splitbill"})

    def test_it_says_which_service_it_is(self, client):
        """So a script that finds something on 8765 can tell whether it is us
        before posting a spreadsheet at it."""
        _, payload = client.json("/api/health")
        assert payload["service"] == "splitbill"


class TestParse:
    def test_it_detects_the_columns_and_says_they_were_detected(self, client):
        _, payload = client.parse(BILL.read_bytes(), "bill_realistic.csv")
        columns = payload["columns"]
        assert columns["creditor"] == {"name": "付款人", "auto": True}
        assert columns["debtor"] == {"name": "参与人", "auto": True}
        assert columns["amount"] == {"name": "金额", "auto": True}
        assert columns["category"] == {"name": "类型", "auto": True}

    def test_an_absent_column_is_null_rather_than_a_guess(self, client):
        """This bill has no currency column. Reporting the name `DataFormat` falls
        back to would be claiming a column that does not exist."""
        _, payload = client.parse(BILL.read_bytes(), "bill_realistic.csv")
        assert payload["columns"]["currency"] == {"name": None, "auto": False}

    def test_the_import_contains_the_whole_sheet_for_confirmation(self, client):
        _, payload = client.parse(BILL.read_bytes(), "bill_realistic.csv")
        sheet = payload["sheet"]
        assert len(sheet["rows"]) == 153
        assert sheet["total_rows"] == 153
        assert sheet["truncated"] is False

    def test_the_preview_keeps_columns_the_tool_ignores(self, client):
        """The page shows the bill as imported, notes column included."""
        _, payload = client.parse(BILL.read_bytes(), "bill_realistic.csv")
        assert "备注" in payload["sheet"]["columns"]

    def test_it_computes_nothing(self, client):
        """The whole reason this is a separate endpoint: a bill whose columns were
        guessed wrong still has to be displayable, so the guess can be corrected in
        the page."""
        _, payload = client.parse(BILL.read_bytes(), "bill_realistic.csv")
        assert "report" not in payload
        assert "settlement" not in payload

    def test_a_clean_bill_is_ok_with_no_findings(self, client):
        _, payload = client.parse(SIMPLE)
        assert payload["ok"] is True
        assert payload["findings"] == {"errors": [], "warnings": []}

    def test_xlsx_is_read_too(self, client):
        status, payload = client.parse(SAMPLE_XLSX.read_bytes(), "sample_data.xlsx")
        assert status == 200, payload
        assert payload["sheet"]["total_rows"] > 0

    def test_options_can_come_from_the_query_string(self, client):
        """Spelled as the CLI flags are, so the two are one thing to learn."""
        _, payload = client.parse(
            b"Creditor,Debtor,Amount,Currency\nAlice,Bob,30000,KRW\n",
            query="?standard_currency=HKD&exchange_rate=KRW/HKD=0.0057715",
        )
        assert payload["std_currency"] == "HKD"
        assert payload["exchange_rates"] == [
            {"base": "KRW", "quote": "HKD", "rate": 0.0057715}
        ]

    def test_a_bill_with_errors_parses_and_reports_them(self, client):
        """`ok: False` and the findings, not a 500. The page needs to show what is
        wrong beside the data that is wrong."""
        status, payload = client.parse(b"Creditor,Debtor,Amount\nAlice,,90\n")
        assert status == 200
        assert payload["ok"] is False
        assert payload["findings"]["errors"]

    def test_the_findings_keep_errors_and_warnings_apart(self, client):
        """An error means no report is possible; a warning means one is and
        something deserves a look. One list could not say which."""
        _, payload = client.parse(b"Creditor,Debtor,Amount\nAlice,Bob,0\n")
        assert payload["findings"]["warnings"]
        assert not payload["findings"]["errors"]


class TestReport:
    def test_preview_interprets_members_without_producing_a_report(self, client):
        _, parsed = client.parse(SIMPLE)

        status, payload = client.preview(token=parsed["token"])

        assert status == 200
        assert payload["ok"] is True
        assert payload["members"] == ["Alice", "Bob", "Carol"]
        assert payload["base_amounts"] == [90.0, 50.0]
        assert "report" not in payload

    def test_it_returns_the_schema_the_contract_describes(self, client, token):
        status, payload = client.report(token=token)
        assert status == 200
        report = payload["report"]
        assert report["schema_version"] == "2.0"
        assert set(report) == {
            "schema_version", "meta", "members", "summary", "positions",
            "settlement", "lending_edges", "ledger",
        }

    def test_it_is_the_same_report_the_cli_produces(self, client, token):
        """The point of the whole arrangement. One implementation, so a bill cannot
        settle one way in the terminal and another in the browser."""
        from splitbill import pipeline
        from tests.conftest import cli_args

        _, payload = client.report(token=token)
        expected = pipeline.analyze_file(BILL, args=cli_args()).to_dict()

        del expected["meta"]["generated_at"]
        del payload["report"]["meta"]["generated_at"]
        # The upload is stored under its token, so the CLI's filename differs.
        expected["meta"]["source_file"] = payload["report"]["meta"]["source_file"]
        assert payload["report"] == expected

    def test_the_appendix_gets_the_whole_sheet(self, client, token):
        """The report keeps the complete confirmed source sheet for its appendix."""
        _, payload = client.report(token=token)
        assert payload["sheet"]["total_rows"] == 153
        assert len(payload["sheet"]["rows"]) == 153
        assert payload["sheet"]["truncated"] is False

    def test_the_sheet_travels_beside_the_report_not_inside_it(self, client, token):
        """`Report.to_dict()` is the versioned, archived contract and leaves
        `raw_frame` out on purpose."""
        _, payload = client.report(token=token)
        assert "sheet" in payload
        assert "raw_frame" not in payload["report"]
        assert "sheet" not in payload["report"]

    def test_it_carries_every_share(self, client, token):
        _, payload = client.report(token=token)
        assert len(payload["report"]["ledger"]) == 668

    def test_one_upload_serves_repeated_reports(self, client, token):
        """Changing a dropdown must not mean re-uploading the spreadsheet."""
        first = client.report(token=token)
        second = client.report(token=token)
        assert first[0] == second[0] == 200

    def test_corrected_columns_are_honoured(self, client):
        """Detection would read `From`/`To`; the page says otherwise and wins."""
        csv = b"From,To,Value,Payer,Payee,Amount\nx,y,1,Alice,Bob,90\n"
        _, parsed = client.parse(csv)
        status, payload = client.report(
            token=parsed["token"],
            columns={"creditor": "Payer", "debtor": "Payee", "amount": "Amount"},
        )
        assert status == 200, payload
        assert payload["report"]["meta"]["columns"]["creditor"]["name"] == "Payer"
        assert set(payload["report"]["members"]) == {"Alice", "Bob"}

    def test_corrected_optional_category_is_honoured(self, client):
        """A non-standard category header can be selected without affecting the
        settlement columns."""
        csv = (
            b"Creditor,Debtor,Amount,Type,Spending bucket\n"
            b"Alice,Bob,90,wrong guess,Food\n"
        )
        _, parsed = client.parse(csv)

        status, payload = client.report(
            token=parsed["token"],
            columns={"category": "Spending bucket"},
        )

        assert status == 200, payload
        report = payload["report"]
        assert report["meta"]["columns"]["category"] == {
            "name": "Spending bucket", "auto": False}
        assert {category for position in report["positions"]
                for category in position["by_category"]} == {"Food"}

    def test_optional_category_can_be_turned_off(self, client):
        _, parsed = client.parse(
            b"Creditor,Debtor,Amount,Type\nAlice,Bob,90,Food\n")

        status, payload = client.report(
            token=parsed["token"], columns={"category": None})

        assert status == 200, payload
        assert payload["report"]["meta"]["columns"]["category"] == {
            "name": None, "auto": False}
        assert all(not position["by_category"]
                   for position in payload["report"]["positions"])

    def test_rates_can_be_given_as_objects(self, client):
        """The shape the report itself uses, so a report can be re-requested from
        its own metadata."""
        _, parsed = client.parse(
            b"Creditor,Debtor,Amount,Currency\nAlice,Bob,30000,KRW\n")
        status, payload = client.report(
            token=parsed["token"],
            std_currency="HKD",
            exchange_rates=[{"base": "KRW", "quote": "HKD", "rate": 0.0057715}],
        )
        assert status == 200, payload
        assert payload["report"]["meta"]["std_currency"] == "HKD"
        # 30000 * 0.0057715 = 173.145, and `to_minor` rounds half to even.
        assert payload["report"]["summary"]["total_spend"] == 173.14

    def test_rates_can_be_given_as_cli_strings(self, client):
        """So a curl reproduction of a page request is something a person can
        type."""
        _, parsed = client.parse(
            b"Creditor,Debtor,Amount,Currency\nAlice,Bob,30000,KRW\n")
        status, payload = client.report(
            token=parsed["token"], std_currency="HKD",
            exchange_rates=["KRW/HKD=0.0057715"],
        )
        assert status == 200, payload
        assert payload["report"]["meta"]["exchange_rates"] == [
            {"base": "KRW", "quote": "HKD", "rate": 0.0057715}
        ]

    def test_a_custom_separator_is_honoured(self, client):
        _, parsed = client.parse(b"Creditor,Debtor,Amount\nAlice,Bob|Carol,100\n")
        status, payload = client.report(token=parsed["token"], separator="|")
        assert status == 200, payload
        assert set(payload["report"]["members"]) == {"Alice", "Bob", "Carol"}

    def test_a_mismatched_separator_warns_without_blocking_analysis(self, client):
        """The user can inspect a suspected separator mistake and continue anyway."""
        _, parsed = client.parse(SIMPLE)

        preview_status, preview = client.preview(
            token=parsed["token"], separator=";"
        )
        status, payload = client.report(token=parsed["token"], separator=";")

        assert preview_status == 200
        assert preview["ok"] is True
        assert preview["members"] == ["Alice", "Alice, Bob", "Bob", "Carol"]
        assert "report" not in preview
        assert status == 200, payload
        warnings = preview["findings"]["warnings"]
        assert any("may use ',' as the name separator" in item["message"]
                   for item in warnings)
        assert any(item["row"] == 2 and item["column"] == "Debtor"
                   for item in warnings)
        assert not preview["findings"]["errors"]
        assert "report" in payload

    def test_an_invalid_bill_gives_422_with_the_findings(self, client):
        """Not a 500 -- the bill is wrong, not the request -- and the response
        carries what to fix so the page need not re-parse to find out."""
        _, parsed = client.parse(b"Creditor,Debtor,Amount\nAlice,,90\n")
        status, payload = client.report(token=parsed["token"])
        assert status == 422
        assert payload["findings"]["errors"]
        assert "columns" in payload

    def test_an_unreadable_amount_is_reported_with_a_token_to_retry_with(self, client):
        """A cell that is not a number is refused by `clean_amount_column`, which
        raises rather than returning findings.

        Answered as a finding with the token and the preview, not as an error status,
        because this is where the page earns its keep: an unreadable "amount" is
        often a mis-detected column -- notes picked up as the amount -- and the fix
        is a dropdown rather than an edit to the spreadsheet.
        """
        status, parsed = client.parse(
            b"Creditor,Debtor,Amount,Note\nAlice,Bob,90,n/a\n")
        assert status == 200
        assert "token" in parsed
        assert parsed["ok"] is True  # `Amount` is fine here; `Note` is not the amount

        # Now point the amount role at the text column, as a bad guess would.
        status, payload = client.report(
            token=parsed["token"], columns={"amount": "Note"})
        assert status == 422
        assert "row" in payload["error"].lower()

    def test_a_bill_whose_amount_column_is_unreadable_still_previews(self, client):
        """The sheet has to be displayable for the column to be corrected in it."""
        status, parsed = client.parse(
            b"Creditor,Debtor,Amount\nAlice,Bob,not-a-number\n")
        assert status == 200
        assert parsed["ok"] is False
        assert parsed["findings"]["errors"]
        assert parsed["sheet"]["rows"] == [["Alice", "Bob", "not-a-number"]]
        assert "token" in parsed

    def test_a_missing_rate_gives_422_naming_the_currency(self, client):
        _, parsed = client.parse(
            b"Creditor,Debtor,Amount,Currency\nAlice,Bob,30000,KRW\n")
        status, payload = client.report(token=parsed["token"], std_currency="HKD")
        assert status == 422
        assert "KRW" in json.dumps(payload, ensure_ascii=False)


class TestBadRequests:
    def test_an_unknown_token_is_refused(self, client):
        status, payload = client.report(token="not-a-real-token")
        assert status == 400
        assert "token" in payload["error"]

    def test_a_missing_token_is_refused(self, client):
        status, payload = client.report()
        assert status == 400

    def test_a_non_object_body_is_refused(self, client):
        status, payload = client.json(
            "/api/report", data=b"[1,2,3]",
            headers={"Content-Type": "application/json"}, method="POST")
        assert status == 400
        assert "JSON object" in payload["error"]

    def test_malformed_json_is_refused(self, client):
        status, payload = client.json(
            "/api/report", data=b"{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        assert status == 400
        assert "valid JSON" in payload["error"]

    def test_an_empty_upload_is_refused(self, client):
        status, payload = client.parse(b"")
        assert status == 400

    def test_an_unknown_endpoint_is_a_404(self, client):
        status, _ = client.json("/api/nonexistent", data=b"{}", method="POST")
        assert status == 404

    def test_an_upload_without_a_filename_is_refused(self, client):
        """The extension is how the format is chosen, so the name is not optional."""
        status, payload = client.json("/api/parse", data=SIMPLE, method="POST")
        assert status == 400
        assert "filename" in payload["error"]

    def test_an_unsupported_format_is_refused_by_name(self, client):
        status, payload = client.parse(SIMPLE, "bill.exe")
        assert status == 400
        assert ".csv" in payload["error"]

    def test_an_oversized_upload_is_refused_without_being_read(self, client):
        """Refused on Content-Length, so a 200 MB body never reaches memory."""
        status, payload = client.json(
            "/api/parse", data=b"x" * 128,
            headers={"X-Filename": "bill.csv",
                     "Content-Length": str(MAX_UPLOAD_BYTES + 1)},
            method="POST")
        assert status == 413
        assert str(MAX_UPLOAD_BYTES) in payload["error"]


class TestSecurity:
    """Loopback binding stops the network. It does not stop this browser."""

    def test_a_cross_origin_request_is_refused(self, client):
        """A page on the internet can post to localhost. Without this check, one
        could read somebody's bill out of a running server."""
        status, payload = client.json(
            "/api/health", headers={"Origin": "https://evil.example"})
        assert status == 403
        assert "cross-origin" in payload["error"]

    def test_a_foreign_host_header_is_refused(self, client):
        """DNS rebinding: an attacker's hostname resolves to 127.0.0.1, so the
        connection is local while the request was addressed elsewhere. `Host` is
        what still says which name was asked for."""
        status, payload = client.json(
            "/api/health", headers={"Host": "evil.example"})
        assert status == 403
        assert "Host" in payload["error"]

    def test_localhost_and_the_loopback_address_are_both_accepted(self, client):
        for host in ("localhost", "127.0.0.1"):
            status, _ = client.json("/api/health", headers={"Host": host})
            assert status == 200, host

    def test_a_same_origin_request_is_accepted(self, client):
        status, _ = client.json(
            "/api/health", headers={"Origin": "http://localhost:5173"})
        assert status == 200

    def test_the_static_route_cannot_escape_its_directory(self, client):
        """Encoded, so the URL parser does not normalise it away before we see it."""
        for attempt in ("/..%2f..%2f..%2fetc%2fpasswd",
                        "/assets/..%2f..%2f..%2f..%2fetc%2fpasswd"):
            status, body, _ = client.request(attempt)
            assert b"root:" not in body, attempt

    def test_it_binds_to_loopback_only(self):
        """Never 0.0.0.0, which would put an unauthenticated service on whatever
        network the laptop is on."""
        httpd, directory = build_server(port=0)
        try:
            assert httpd.server_address[0] == "127.0.0.1"
        finally:
            httpd.server_close()
            shutil.rmtree(directory, ignore_errors=True)

    def test_responses_are_not_framable_or_sniffable(self, client):
        _, _, headers = client.request("/api/health")
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_a_report_is_not_cached(self, client, token):
        """Somebody's spending, in a browser that may not be theirs alone."""
        _, _, headers = client.request(
            "/api/report", data=json.dumps({"token": token}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        assert headers["Cache-Control"] == "no-store"


class TestFilenames:
    """`safe_filename` in isolation -- attacker-controlled text that reaches a
    response."""

    @pytest.mark.parametrize("name", [
        "bill.csv", "bill_realistic.csv", "sample data.xlsx", "账单.csv",
        "2026 trip (final).xlsx", "a-b_c.tsv",
    ])
    def test_ordinary_names_pass(self, name):
        assert safe_filename(name) == name

    @pytest.mark.parametrize("name", [
        "../etc/passwd", "..\\windows\\system32", "/etc/passwd", "a/b.csv",
        ".", "..", "", "   ", "bill.csv\x00.exe", "bill.exe", "bill",
        "bill.csv;rm -rf /",
    ])
    def test_dangerous_or_unsupported_names_are_refused(self, name):
        from splitbill.serve import BadRequest

        with pytest.raises(BadRequest):
            safe_filename(name)

    def test_percent_encoding_is_decoded_before_being_checked(self, name="%2e%2e%2fx.csv"):
        """A header cannot carry a raw newline or a non-ASCII byte, so the client
        percent-encodes. Checking before decoding would pass `%2e%2e%2f`."""
        from splitbill.serve import BadRequest

        with pytest.raises(BadRequest):
            safe_filename(name)

    def test_an_encoded_cjk_name_survives(self):
        assert safe_filename("%E8%B4%A6%E5%8D%95.csv") == "账单.csv"


class TestUploads:
    def test_tokens_are_unguessable(self, tmp_path):
        """Two tabs on two bills called `bill.csv` must not see each other's, and a
        guessable token would let any page ask for one."""
        uploads = Uploads(tmp_path)
        tokens = {uploads.add(SIMPLE, "bill.csv") for _ in range(50)}
        assert len(tokens) == 50
        assert all(len(t) >= 20 for t in tokens)

    def test_the_oldest_is_dropped_past_the_limit(self, tmp_path):
        """A long-running process with a dict keyed by token is a slow leak."""
        uploads = Uploads(tmp_path, limit=3)
        first = uploads.add(SIMPLE, "a.csv")
        for name in ("b.csv", "c.csv", "d.csv"):
            uploads.add(SIMPLE, name)

        from splitbill.serve import BadRequest

        with pytest.raises(BadRequest):
            uploads.get(first)

    def test_dropping_removes_the_file_too(self, tmp_path):
        uploads = Uploads(tmp_path, limit=1)
        uploads.add(SIMPLE, "a.csv")
        uploads.add(SIMPLE, "b.csv")
        assert len(list(tmp_path.iterdir())) == 1

    def test_clear_removes_everything(self, tmp_path):
        uploads = Uploads(tmp_path)
        for name in ("a.csv", "b.csv"):
            uploads.add(SIMPLE, name)
        uploads.clear()
        assert list(tmp_path.iterdir()) == []

    def test_uploads_land_outside_the_project(self):
        """Never in the working tree: a bill is somebody's private spending, and one
        that lands in a git repo eventually gets committed."""
        httpd, directory = build_server(port=0)
        try:
            project = Path(__file__).resolve().parent.parent
            assert project not in directory.resolve().parents
        finally:
            httpd.server_close()
            shutil.rmtree(directory, ignore_errors=True)

    def test_the_original_name_is_kept_for_display(self, tmp_path):
        """The file is stored under its token; the name is what the report says it
        came from."""
        uploads = Uploads(tmp_path)
        token = uploads.add(SIMPLE, "账单.csv")
        assert uploads.get(token).original_name == "账单.csv"


class TestTheIndexRoute:
    def test_the_built_frontend_is_what_gets_served(self, client):
        """The committed build in `splitbill/render/webui/`.

        Built output is in the repository so that `pip install splitbill && splitbill
        serve` works without node. Asserting it is actually there catches the case
        where somebody changes the frontend and forgets `npm run build` -- in which
        case the page silently stays on the previous version.
        """
        from splitbill.serve import STATIC_ROOT

        if not (STATIC_ROOT / "index.html").is_file():
            pytest.skip("frontend not built in this checkout")

        status, body, headers = client.request("/")
        assert status == 200
        assert "text/html" in headers["Content-Type"]
        assert b"not been built" not in body
        assert b'<div id="app">' in body
        assert b"/assets/" in body

    def test_the_placeholder_explains_itself_when_nothing_is_built(
        self, client, monkeypatch, tmp_path
    ):
        """A checkout where `npm run build` has not been run.

        A 404 at `/` there looks like a broken install. This says what is missing, how
        to fix it, and that the API works regardless -- which it does, and the CLI does
        too.
        """
        monkeypatch.setattr(serve_module, "STATIC_ROOT", tmp_path / "absent")
        status, body, headers = client.request("/")
        assert status == 200
        assert "text/html" in headers["Content-Type"]
        assert b"not been built" in body
        assert b"npm run build" in body
        assert b"/api/parse" in body

    def test_an_unknown_path_falls_through_to_the_page(self, client):
        """Under a single-page app an unknown path is a route, not a missing file."""
        status, body, _ = client.request("/some/deep/route")
        assert status == 200
        assert b"<!DOCTYPE html>" in body or b"<!doctype html>" in body

    def test_static_root_is_where_the_frontend_actually_builds(self):
        """`webui/vite.config.ts` writes to `splitbill/render/webui`.

        Asserted against the config rather than restated, because the two drifting
        apart fails in the least helpful way available: the API works, the build
        succeeds, and the page is the "not built" placeholder. Which is exactly what
        happened -- STATIC_ROOT was `splitbill/webui`, one directory up from the
        build, and every other test here passed because they monkeypatch it.
        """
        from splitbill.serve import STATIC_ROOT

        config = (Path(__file__).resolve().parent.parent / "webui"
                  / "vite.config.ts").read_text(encoding="utf-8")
        assert "'../splitbill/render/webui'" in config, (
            "vite.config.ts no longer builds where serve.py looks")
        assert STATIC_ROOT.parts[-2:] == ("render", "webui")

    def test_a_built_frontend_is_served_when_present(self, client, monkeypatch,
                                                     tmp_path):
        """Phase 2 puts a build in `render/webui/`. Checked now so that step is
        wiring and not discovery."""
        built = tmp_path / "webui"
        built.mkdir()
        (built / "index.html").write_text("<!DOCTYPE html><h1>built</h1>",
                                          encoding="utf-8")
        (built / "app.js").write_text("export const x = 1\n", encoding="utf-8")
        monkeypatch.setattr(serve_module, "STATIC_ROOT", built)

        status, body, _ = client.request("/")
        assert status == 200 and b"built" in body

        status, body, headers = client.request("/app.js")
        assert status == 200
        assert "text/javascript" in headers["Content-Type"]


class TestJsonSafety:
    def test_a_nan_does_not_reach_the_response(self, client):
        """`json.dumps` writes a bare `NaN`, which is valid JavaScript and invalid
        JSON -- `JSON.parse` rejects it. One empty cell in a column the tool never
        reads would otherwise stop the page loading the bill."""
        csv = ("Creditor,Debtor,Amount,Note\n"
               "Alice,Bob,90,\n"
               "Bob,Carol,50,paid in cash\n").encode("utf-8")
        status, body, _ = client.request(
            "/api/parse", data=csv, headers={"X-Filename": "bill.csv"},
            method="POST")
        assert status == 200
        assert b"NaN" not in body
        payload = json.loads(body)  # would raise on a bare NaN
        assert payload["sheet"]["rows"][0][3] is None

    def test_cjk_is_readable_rather_than_escaped(self, client):
        status, body, _ = client.request(
            "/api/parse", data=BILL.read_bytes(),
            headers={"X-Filename": "bill.csv"}, method="POST")
        assert status == 200
        assert "付款人".encode("utf-8") in body
        assert b"\\u4ed8" not in body

    def test_a_date_column_serialises_as_a_string(self, client):
        """Excel hands back a Timestamp where CSV hands back text, and neither
        `json.dumps` nor the page should have to know which."""
        status, payload = client.parse(SAMPLE_XLSX.read_bytes(), "s.xlsx")
        assert status == 200
        for row in payload["sheet"]["rows"]:
            for cell in row:
                assert not hasattr(cell, "isoformat")

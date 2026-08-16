"""`splitbill serve`: the local HTTP service the browser talks to.

Plan §3 and §6. The algorithm stays in Python and the page is a view over it. One
implementation of `simplest_equiv`, one set of tests holding it down, and no
arithmetic in TypeScript that could disagree with the terminal. The cost is that this
is not a double-click app: you run a command.

    GET  /                    the page
    GET  /assets/*            its JavaScript and CSS
    POST /api/parse           a bill -> detected columns, a preview, findings
    POST /api/preview         a token + options -> validation, members, conversions
    POST /api/report          a token + options -> the full report
    GET  /api/health          for scripts and for checking the port is ours

`/api/parse` and `/api/report` are separate because a wrong column guess has to be
fixable in the page. Parse returns what it found and computes nothing; the page shows
it, the user corrects the creditor column if detection got it wrong, and report runs
with the corrected mapping. Both against the same upload, which is why parse hands
back a token: re-uploading a 5 MB spreadsheet to change one dropdown would be a
strange thing to ask.

Uploads go to a temporary directory that is removed when the server stops, never into
the project. Nothing is written to the bill.

This module lives above the three layers rather than in `render/`, and the distinction
is not bookkeeping. `render` may not import `loader`, `settle` or `pipeline` (§4.5),
because the moment layer 3 can reach past the Report there is a path by which the
browser and the CLI disagree about what somebody owes. A server, though, has to drive
the pipeline -- that is what a server is. So the shaping of the payloads is in
`render/web.py`, which sees only a Report and obeys the rule, and the driving is here,
next to `__main__.py`, which has always been allowed to see everything.

Security
--------

A local tool, which is not the same as a safe one:

* bound to 127.0.0.1 only -- never 0.0.0.0, which would put an unauthenticated
  service on the network the laptop is on
* `Host` and `Origin` are checked, because binding to loopback alone does not stop a
  page in the same browser from posting here. DNS rebinding resolves an attacker's
  hostname to 127.0.0.1 and the request arrives looking local; the `Host` header is
  what still says which name was asked for
* uploads capped, and refused before being read into memory
* the static route cannot escape its directory
* no authentication. There is no user to authenticate, and a password on a loopback
  socket is theatre. The boundary is the binding, and README says so
"""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from . import pipeline
from .loader import DataFormat, read_sheet
from .loader.source import SUPPORT_FTYPES
from .render import web
from .utils.money import round_money

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_FRONTEND_PORT = 5173

# 10 MB. A 153-record bill is about 20 KB, so this is three orders of magnitude of
# headroom -- large enough never to be hit by a real trip, small enough that a
# mistaken upload cannot exhaust memory.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Uploads are held so `/api/report` can be re-run with corrected columns without
# another upload. Bounded because this is a long-running process and an unbounded
# dict keyed by token is a slow leak; the oldest is dropped, which in practice means
# a tab left open since the morning has to re-import. Better than the alternative.
MAX_HELD_UPLOADS = 32

# The `%` is for a filename arriving percent-encoded from the header.
SAFE_FILENAME = re.compile(r"^[\w\-. %()一-鿿]+$", re.UNICODE)

# Where `webui/vite.config.ts` writes its build, and what the wheel packages. The two
# have to agree, and `tests/test_serve.py` asserts it -- the monkeypatched STATIC_ROOT
# in the other static-file tests would happily pass with this pointing anywhere.
STATIC_ROOT = Path(__file__).resolve().parent / "render" / "webui"

# What the page is served when the frontend has not been built. Phase 1 is the
# service; Phase 2 is the page. Saying so beats a 404 that looks like a bug.
PLACEHOLDER = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>SplitBill</title>
<style>
  body { font: 15px/1.6 ui-sans-serif, system-ui, sans-serif; max-width: 42rem;
         margin: 4rem auto; padding: 0 1.5rem; color: #1f2328; }
  code { background: #f0f1f3; padding: .15em .4em; border-radius: 3px; }
  .hint { color: #59636e; }
</style></head><body>
<h1>SplitBill</h1>
<p>The service is running. The web interface has not been built into this
install.</p>
<p class="hint">Build it with <code>npm install &amp;&amp; npm run build</code> in
<code>webui/</code>, or use the CLI:
<code>splitbill --file bill.csv --json_dump_path report.json</code>.</p>
<p class="hint">The API is up either way &mdash;
<code>POST /api/parse</code>, <code>POST /api/preview</code>,
<code>POST /api/report</code>.</p>
</body></html>
"""


class UploadTooLarge(Exception):
    pass


class BadRequest(Exception):
    """Something about the request is wrong in a way the client can fix."""


class DevelopmentError(Exception):
    """The source checkout cannot start its development servers."""


@dataclass
class Upload:
    """A bill on disk, and the name it arrived under."""

    path: Path
    original_name: str


class Uploads:
    """Bills held between a parse and the reports asked for from it.

    Keyed by an unguessable token rather than by filename: two browser tabs on two
    bills called `bill.csv` must not see each other's, and a token that could be
    guessed would let any page in the browser ask for the contents of one.
    """

    def __init__(self, directory: Path, limit: int = MAX_HELD_UPLOADS) -> None:
        self._directory = directory
        self._limit = limit
        self._held: Dict[str, Upload] = {}
        self._lock = threading.Lock()

    def add(self, data: bytes, original_name: str) -> str:
        token = secrets.token_urlsafe(16)
        suffix = Path(original_name).suffix.lower()
        path = self._directory / f"{token}{suffix}"
        path.write_bytes(data)

        with self._lock:
            self._held[token] = Upload(path=path, original_name=original_name)
            # dicts keep insertion order, so the first key is the oldest upload.
            while len(self._held) > self._limit:
                oldest = next(iter(self._held))
                self._held.pop(oldest).path.unlink(missing_ok=True)
        return token

    def get(self, token: str) -> Upload:
        with self._lock:
            upload = self._held.get(token)
        if upload is None:
            raise BadRequest(
                "unknown or expired upload token -- import the bill again")
        return upload

    def clear(self) -> None:
        with self._lock:
            for upload in self._held.values():
                upload.path.unlink(missing_ok=True)
            self._held.clear()


def safe_filename(raw: str) -> str:
    """A filename to keep for display, with anything path-like refused.

    The name reaches the report's `meta.source_file` and nothing else -- the file
    itself is stored under its token -- but it is attacker-controlled text that ends
    up in a JSON response, so a separator or a `..` in it is refused rather than
    stripped. Stripping invites the next question of what it stripped to.
    """
    name = unquote(raw or "").strip()
    if not name:
        raise BadRequest("the upload needs a filename, in the X-Filename header")
    if "/" in name or "\\" in name or name in (".", "..") or "\x00" in name:
        raise BadRequest(f"unacceptable filename: {name!r}")
    if not SAFE_FILENAME.match(name):
        raise BadRequest(f"unacceptable filename: {name!r}")
    if Path(name).suffix.lower() not in SUPPORT_FTYPES:
        supported = ", ".join(sorted(SUPPORT_FTYPES))
        raise BadRequest(
            f"unsupported format {Path(name).suffix!r}. Supported: {supported}")
    return name


def data_format_from(frame, spec: dict) -> DataFormat:
    """A DataFormat from a JSON body, auto-detecting whatever it leaves out.

    The page sends back the column roles as the user left them -- usually exactly
    what detection proposed, occasionally corrected. For optional descriptive
    roles, an explicit null means "do not use this role"; omitting the role leaves
    it available for auto-detection.
    """
    from argparse import Namespace

    columns = spec.get("columns") or {}
    if not isinstance(columns, dict):
        raise BadRequest("`columns` must be an object of role -> column name")

    args = Namespace(
        col_creditor=columns.get("creditor"),
        col_debtor=columns.get("debtor"),
        col_tot_amount=columns.get("amount"),
        col_currency=columns.get("currency"),
        separator=spec.get("separator") or ",",
        all_selector=spec.get("all_selector") or "all",
    )
    descriptive_overrides = {
        role: columns[role]
        for role in ("date", "category", "item")
        if role in columns
    }
    return DataFormat.from_args_with_auto_detect(
        args, frame, descriptive_overrides=descriptive_overrides)


def exchange_rates_from(spec: dict):
    """Rates from a JSON body, in either of the two shapes the page might send.

    A list of `{base, quote, rate}` objects is what the report itself uses, so a
    report can be re-requested from its own metadata. The `BASE/QUOTE=rate` strings
    are what the CLI takes, which makes a curl reproduction of a page request
    something a person can type.
    """
    currency = spec.get("std_currency") or None
    rates = spec.get("exchange_rates") or []

    specs = []
    for rate in rates:
        if isinstance(rate, str):
            specs.append(rate)
            continue
        try:
            specs.append(f"{rate['base']}/{rate['quote']}={rate['rate']}")
        except (KeyError, TypeError) as exc:
            raise BadRequest(
                "each exchange rate needs base, quote and rate") from exc

    try:
        return pipeline.exchange_rates_from_args(currency, specs)
    except (ValueError, KeyError) as exc:
        raise BadRequest(f"could not read the exchange rates: {exc}") from exc


class Handler(BaseHTTPRequestHandler):
    """The routes. One instance per request; `uploads` comes off the server."""

    server_version = "SplitBill"
    sys_version = ""

    # Set on the server by `build_server`.
    uploads: Uploads

    def do_GET(self) -> None:  # noqa: N802  (stdlib naming)
        if not self._host_is_local():
            return
        route = urlparse(self.path).path
        try:
            if route == "/api/health":
                self._json(200, {"ok": True, "service": "splitbill"})
            elif route in ("/", "/index.html"):
                self._serve_index()
            else:
                self._serve_static(route)
        except BadRequest as exc:
            self._json(400, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_is_local():
            return
        route = urlparse(self.path).path
        try:
            if route == "/api/parse":
                self._api_parse()
            elif route == "/api/preview":
                self._api_preview()
            elif route == "/api/report":
                self._api_report()
            else:
                self._json(404, {"error": f"no such endpoint: {route}"})
        except UploadTooLarge as exc:
            self._json(413, {"error": str(exc)})
        except BadRequest as exc:
            self._json(400, {"error": str(exc)})
        except ValueError as exc:
            # Unreadable amounts, unregistered currencies: the bill's problem, and
            # the message names the row or the currency.
            self._json(422, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self.log_error("unhandled error on %s: %r", route, exc)
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # --- routes ---------------------------------------------------------------

    def _api_parse(self) -> None:
        """A bill in, detected columns and a preview out. Computes nothing.

        The body is the file itself, with its name in `X-Filename`. Not multipart:
        `cgi` was removed in Python 3.13 and hand-rolling a multipart parser to
        receive one file would be a poor trade. `fetch` sends a `File` as a body
        directly, so the client side of this is one line.
        """
        name = safe_filename(self.headers.get("X-Filename", ""))
        data = self._read_body()
        if not data:
            raise BadRequest("the request body is empty")

        token = self.uploads.add(data, name)
        upload = self.uploads.get(token)

        spec = _query_options(self.path)
        frame = read_sheet(upload.path)
        cfg = data_format_from(frame, spec)
        exrs = exchange_rates_from(spec)

        try:
            prepared = pipeline.prepare(upload.path, cfg=cfg, exrs=exrs,
                                        source_name=name)
            columns, shown, validation = (prepared.cfg.bindings, prepared.frame,
                                          prepared.validation)
            members = prepared.members
            base_amounts = _base_amounts(prepared.frame, prepared.cfg, exrs)
        except ValueError as exc:
            # `clean_amount_column` refuses a cell that is not a number, and it
            # raises rather than returning findings, so it lands here instead of in
            # `prepared.validation`.
            #
            # Answered as a finding rather than as an error status, because this is
            # the case where the page is most useful: an unreadable "amount" is
            # frequently a mis-detected column -- a notes column picked up as the
            # amount -- and the fix is a dropdown, not an edit to the spreadsheet.
            # That needs the token and the preview, so both are sent. Re-read for the
            # preview because cleaning mutates the frame in place and threw partway
            # through it.
            columns, shown = cfg.bindings, read_sheet(upload.path)
            validation = _findings_from(exc, cfg.col_tot_amount)
            members = ()
            base_amounts = ()

        payload = web.parse_payload(
            source_file=name,
            columns=columns,
            frame=shown,
            validation=validation,
            std_currency=exrs.std_currency if exrs is not None else None,
            exchange_rates=tuple(exrs.registered()) if exrs is not None else (),
            members=members,
            base_amounts=base_amounts,
        )
        payload["token"] = token
        self._json(200, payload)

    def _api_preview(self) -> None:
        """Validate current import options without running settlement analysis.

        This is the live first-step endpoint. In particular, it returns the names
        produced by the selected separator even when they look wrong, so the user
        can inspect the interpretation before any exact graph search is attempted.
        """
        spec = self._read_json()
        token = spec.get("token")
        if not token or not isinstance(token, str):
            raise BadRequest("`token` is required -- POST /api/parse first")

        upload = self.uploads.get(token)
        frame = read_sheet(upload.path)
        cfg = data_format_from(frame, spec)
        exrs = exchange_rates_from(spec)

        try:
            prepared = pipeline.prepare(
                upload.path,
                cfg=cfg,
                exrs=exrs,
                source_name=upload.original_name,
            )
            shown = prepared.frame
            validation = prepared.validation
            members = prepared.members
            base_amounts = _base_amounts(shown, prepared.cfg, exrs)
            columns = prepared.cfg.bindings
        except ValueError as exc:
            shown = read_sheet(upload.path)
            validation = _findings_from(exc, cfg.col_tot_amount)
            members = ()
            base_amounts = ()
            columns = cfg.bindings

        payload = web.parse_payload(
            source_file=upload.original_name,
            columns=columns,
            frame=shown,
            validation=validation,
            std_currency=exrs.std_currency if exrs is not None else None,
            exchange_rates=(tuple(exrs.registered()) if exrs is not None else ()),
            members=members,
            base_amounts=base_amounts,
        )
        payload["token"] = token
        self._json(200, payload)

    def _api_report(self) -> None:
        """A token and options in, the whole report out.

        Re-reads the bill rather than caching the parse: reading a spreadsheet is
        milliseconds, and a cache keyed on the options would be a second place for
        the column mapping to live.
        """
        spec = self._read_json()
        token = spec.get("token")
        if not token or not isinstance(token, str):
            raise BadRequest("`token` is required -- POST /api/parse first")

        upload = self.uploads.get(token)
        frame = read_sheet(upload.path)
        cfg = data_format_from(frame, spec)
        exrs = exchange_rates_from(spec)

        prepared = pipeline.prepare(upload.path, cfg=cfg, exrs=exrs,
                                    source_name=upload.original_name)
        if not prepared.ok:
            # Not a 500: the bill is wrong, not the request. Sent with the findings
            # and the columns so the page can show what to fix without re-parsing.
            self._json(422, {
                "error": "the bill has validation errors",
                **web.parse_payload(
                    source_file=upload.original_name,
                    columns=prepared.cfg.bindings,
                    frame=prepared.frame,
                    validation=prepared.validation,
                    std_currency=exrs.std_currency if exrs is not None else None,
                    exchange_rates=(tuple(exrs.registered())
                                    if exrs is not None else ()),
                    members=prepared.members,
                    base_amounts=_base_amounts(prepared.frame, prepared.cfg, exrs),
                ),
            })
            return

        report = pipeline.analyze(prepared)
        payload = web.report_payload(report)
        payload["token"] = token
        self._json(200, payload)

    def _serve_index(self) -> None:
        index = STATIC_ROOT / "index.html"
        if index.is_file():
            self._bytes(200, index.read_bytes(), "text/html; charset=utf-8")
        else:
            self._bytes(200, PLACEHOLDER.encode("utf-8"),
                        "text/html; charset=utf-8")

    def _serve_static(self, route: str) -> None:
        """A built asset, or 404. Cannot escape `STATIC_ROOT`."""
        relative = unquote(route).lstrip("/")
        target = (STATIC_ROOT / relative).resolve()
        try:
            target.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self._json(404, {"error": "not found"})
            return
        if not target.is_file():
            # An unknown path under a single-page app is a route, not a missing
            # file -- the page's own router will make sense of it.
            self._serve_index()
            return
        self._bytes(200, target.read_bytes(), _content_type(target))

    # --- plumbing -------------------------------------------------------------

    def _host_is_local(self) -> bool:
        """Refuse anything not addressed to us by name as well as by address.

        The socket is bound to loopback, which stops the network reaching it but not
        a page in this browser. DNS rebinding points an attacker's hostname at
        127.0.0.1, so the connection is local while the request was addressed
        elsewhere -- and `Host` is what still says so. A cross-origin `Origin` is
        refused for the same reason.
        """
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        if host and host not in ("localhost", "127.0.0.1", "::1", ""):
            self._json(403, {"error": f"unexpected Host header: {host!r}"})
            return False

        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                self._json(403, {"error": f"cross-origin request from {origin!r}"})
                return False
        return True

    def _read_body(self) -> bytes:
        """The request body, refusing an oversized one before reading it."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise BadRequest("Content-Length is not a number") from exc
        if length > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(
                f"upload is {length} bytes; the limit is {MAX_UPLOAD_BYTES}"
            )
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _read_json(self) -> dict:
        body = self._read_body()
        if not body:
            return {}
        try:
            spec = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BadRequest(f"body is not valid JSON: {exc}") from exc
        if not isinstance(spec, dict):
            raise BadRequest("body must be a JSON object")
        return spec

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        self._bytes(status, body.encode("utf-8"), "application/json; charset=utf-8")

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Nothing here is meant to be framed by another page, and the report is
        # somebody's spending.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        """One line per request, on stdout with everything else.

        The default writes to stderr, which means a shell redirect of the interesting
        output gets none of it and the terminal gets both interleaved.
        """
        print(f"  {self.address_string()} - {format % args}")


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json; charset=utf-8",
}


def _content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _findings_from(exc: Exception, column: Optional[str]):
    """A raised error, as a ValidationResult the payload can carry.

    So the page has one place to look for what is wrong with a bill, whether the
    validator reported it or something upstream refused outright.
    """
    from .loader import ValidationResult

    result = ValidationResult()
    result.add_error(None, column, str(exc))
    return result


def _base_amounts(frame, cfg: DataFormat, exrs) -> list:
    """One server-computed total per source row for the import preview.

    Conversion errors are already represented by validation findings. A row whose
    amount cannot yet be converted is returned as ``None`` so the rest of the table
    and the participant interpretation remain inspectable.
    """
    if cfg.col_tot_amount not in frame.columns:
        return [None] * len(frame)

    amounts = []
    for _, row in frame.iterrows():
        try:
            value = row[cfg.col_tot_amount]
            if exrs is not None:
                value = exrs.to_std(row[cfg.col_currency], value)
            amounts.append(round_money(value))
        except (KeyError, TypeError, ValueError):
            amounts.append(None)
    return amounts


def _query_options(path: str) -> dict:
    """Options from a query string, for `/api/parse` whose body is the file.

    `?standard_currency=HKD&exchange_rate=KRW/HKD=0.0057715`, spelled as the CLI
    flags are, so the two are one thing to learn rather than two.
    """
    from urllib.parse import parse_qs

    query = parse_qs(urlparse(path).query)
    spec: dict = {}
    if "standard_currency" in query:
        spec["std_currency"] = query["standard_currency"][0]
    if "exchange_rate" in query:
        spec["exchange_rates"] = query["exchange_rate"]
    if "separator" in query:
        spec["separator"] = query["separator"][0]
    if "all_selector" in query:
        spec["all_selector"] = query["all_selector"][0]
    columns = {
        role: query[f"col_{role}"][0]
        for role in ("creditor", "debtor", "amount", "currency")
        if f"col_{role}" in query
    }
    if columns:
        spec["columns"] = columns
    return spec


def build_server(port: int = DEFAULT_PORT, upload_dir: Optional[Path] = None
                 ) -> Tuple[ThreadingHTTPServer, Path]:
    """A server bound to loopback, and the directory its uploads go in.

    Returns both so a caller -- `serve()`, or a test -- can clean up. Port 0 asks
    the OS for a free one, which is how the tests avoid fighting over 8765.
    """
    directory = Path(tempfile.mkdtemp(prefix="splitbill-")) if upload_dir is None \
        else Path(upload_dir)
    directory.mkdir(parents=True, exist_ok=True)

    handler = type("BoundHandler", (Handler,), {"uploads": Uploads(directory)})
    httpd = ThreadingHTTPServer((HOST, port), handler)
    httpd.daemon_threads = True
    return httpd, directory


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Run until interrupted, then take the uploads with it."""
    httpd, directory = build_server(port)
    actual = httpd.server_address[1]
    url = f"http://{HOST}:{actual}/"

    print(f"SplitBill is serving on {url}")
    print(f"  uploads: {directory} (removed on exit)")
    print("  bound to loopback only; no authentication -- see the README")
    if not STATIC_ROOT.joinpath("index.html").is_file():
        print("  note: the web interface is not built; the API is available")
    print("Ctrl-C to stop.")

    if open_browser:
        # After the server is listening, so the first request cannot beat it.
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        httpd.shutdown()
        httpd.server_close()
        handler_uploads = getattr(httpd.RequestHandlerClass, "uploads", None)
        if handler_uploads is not None:
            handler_uploads.clear()
        shutil.rmtree(directory, ignore_errors=True)


def _free_port() -> int:
    """Ask the OS for a currently unused loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _python_snapshot(source_root: Path) -> tuple[tuple[str, int, int], ...]:
    """A cheap, dependency-free fingerprint for backend reloads."""
    files = []
    for path in source_root.rglob("*.py"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            # An editor may replace a file between rglob() and stat(). The next
            # poll observes the completed rename.
            continue
        files.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(files))


def _stop_process(process: subprocess.Popen) -> None:
    """Stop a development child and anything it spawned."""
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:  # pragma: no cover - exercised on Windows, not in the Unix CI job
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        else:  # pragma: no cover
            process.kill()
        process.wait()


def _development_process(command: list[str], *, cwd: Path,
                         env: Optional[dict] = None) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        start_new_session=(os.name == "posix"),
    )


def _open_when_ready(port: int, url: str) -> None:
    """Open Vite after it accepts connections, without delaying the watcher."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.2):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.1)


def serve_development(port: int = DEFAULT_PORT,
                      frontend_port: int = DEFAULT_FRONTEND_PORT,
                      open_browser: bool = True) -> int:
    """Run the Vite UI and a reloadable Python API from a source checkout.

    Vite owns frontend watching and HMR. This parent watches the Python package and
    replaces the API child after a source edit. Keeping the small reloader here
    avoids adding a runtime dependency to a command intended only for contributors.
    """
    project_root = Path(__file__).resolve().parent.parent
    frontend_root = project_root / "webui"
    package_json = frontend_root / "package.json"
    source_root = project_root / "splitbill"

    if not package_json.is_file():
        raise DevelopmentError(
            "--develop must run from a SplitBill source checkout containing "
            "webui/package.json")
    npm = shutil.which("npm")
    if npm is None:
        raise DevelopmentError("--develop requires npm on PATH")
    if not (frontend_root / "node_modules" / ".bin" / "vite").exists():
        raise DevelopmentError(
            "frontend dependencies are missing; run `npm install` in webui/")

    api_port = _free_port() if port == 0 else port
    if api_port == frontend_port:
        raise DevelopmentError("the API port and frontend port must be different")

    backend_command = [
        sys.executable, "-m", "splitbill", "serve",
        "--port", str(api_port), "--no-browser",
    ]
    frontend_command = [
        npm, "run", "dev", "--", "--host", HOST,
        "--port", str(frontend_port), "--strictPort",
    ]
    frontend_env = os.environ.copy()
    frontend_env["SPLITBILL_API_PORT"] = str(api_port)
    url = f"http://{HOST}:{frontend_port}/"

    print("SplitBill development mode")
    print(f"  frontend: {url} (Vite hot updates)")
    print(f"  API:      http://{HOST}:{api_port}/ (restarts on Python changes)")
    print("  note: an API restart clears temporary uploads")
    print("Ctrl-C to stop both servers.")

    backend: Optional[subprocess.Popen] = None
    frontend: Optional[subprocess.Popen] = None
    snapshot = _python_snapshot(source_root)
    try:
        backend = _development_process(backend_command, cwd=project_root)
        # Catch an occupied API port before starting a frontend that cannot work.
        time.sleep(0.25)
        if backend.poll() is not None:
            return backend.returncode or 1

        frontend = _development_process(
            frontend_command, cwd=frontend_root, env=frontend_env)
        if open_browser:
            threading.Thread(
                target=_open_when_ready,
                args=(frontend_port, url),
                daemon=True,
            ).start()

        while True:
            time.sleep(0.25)
            if frontend.poll() is not None:
                return frontend.returncode or 1

            current = _python_snapshot(source_root)
            if current == snapshot:
                continue
            snapshot = current
            print("\nPython source changed; restarting the API...")
            _stop_process(backend)
            backend = _development_process(backend_command, cwd=project_root)
    except KeyboardInterrupt:
        print("\nstopping development servers.")
        return 0
    finally:
        if frontend is not None:
            _stop_process(frontend)
        if backend is not None:
            _stop_process(backend)

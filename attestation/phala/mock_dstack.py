#!/usr/bin/env python3
"""A stand-in dstack guest agent for the LOCAL dry run.  Never deployed.

Answers ``POST /Info`` and ``POST /GetQuote`` in the shapes the real agent
uses, so ``enclave_run.sh`` can be exercised verbatim on a development host.

The quote it returns is a REAL retained TDX quote with this run's report_data
spliced in at offset 568.  That makes the script's own offset check meaningful
(a wrong offset fails here) while remaining obviously not attestable: its
signature no longer verifies, which is exactly what we want of a mock.  Any
Lean-side or verifier-side acceptance of it would be a bug, and
``verify_run.py`` rejects it at the A1 signature check.
"""
from __future__ import annotations

import http.server
import json
import os
import pathlib
import socketserver
import sys

QUOTE_TEMPLATE = pathlib.Path(
    os.environ.get("MOCK_QUOTE_TEMPLATE", "/mock/tdx-quote.bin")
)
EVENT_LOG = pathlib.Path(os.environ.get("MOCK_EVENT_LOG", "/mock/dstack-event-log.json"))
SOCKET = os.environ.get("MOCK_SOCKET", "/var/run/dstack.sock")

APP_ID = "4b69f1ec" + "00" * 16
COMPOSE_HASH = "de" * 32
REPORT_DATA_OFFSET = 568


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the dry-run transcript readable
        pass

    def _reply(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/Info":
            self._reply({
                "app_id": APP_ID,
                "compose_hash": COMPOSE_HASH,
                "instance_id": "dryrun",
                "app_name": "attested-run-dryrun",
                "tcb_info": {
                    "mrtd": "00" * 48,
                    "rtmr0": "00" * 48, "rtmr1": "00" * 48,
                    "rtmr2": "00" * 48, "rtmr3": "00" * 48,
                    "event_log": json.loads(EVENT_LOG.read_text()),
                },
            })
        elif self.path == "/GetKey":
            # A FIXED stand-in scalar, never a real derived key.  Deterministic
            # so the dry run is reproducible, and obviously not an enclave key:
            # a receipt signed with it must never be accepted anywhere, which
            # is why the Lean-side pin for a dry run carries
            # `attestationAuthority := false`.
            self._reply({"key": "11" * 32,
                         "signature_chain": ["de" * 32, "ad" * 32]})
        elif self.path == "/GetQuote":
            report_data = request["report_data"]
            assert len(report_data) == 128, "report_data must be 64 bytes of hex"
            quote = bytearray(QUOTE_TEMPLATE.read_bytes())
            quote[REPORT_DATA_OFFSET:REPORT_DATA_OFFSET + 64] = bytes.fromhex(report_data)
            self._reply({"quote": bytes(quote).hex(), "report_data": report_data})
        else:
            self._reply({"error": f"unknown method {self.path}"})


class UnixServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True

    def get_request(self):
        request, _ = super().get_request()
        return request, ("localhost", 0)


if __name__ == "__main__":
    pathlib.Path(SOCKET).unlink(missing_ok=True)
    with UnixServer(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o666)
        print(f"mock dstack agent on {SOCKET}", file=sys.stderr, flush=True)
        server.serve_forever()

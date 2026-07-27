#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Print the CH25 A.7 Phala TDX evidence to stdout, so it can be retrieved.

Why this exists
---------------

There is no other way to get bytes out of the CVM.  Docker volumes inside a
dstack CVM are not reachable from `phala cvms` or from the host, and
`phala cvms logs` only returns the logs of containers that still exist -- a
container that has exited has had its logs dropped.  What *does* work, and was
observed to work on real hardware, is: the last container to run prints what
must be kept and then stays alive.

So this module renders each evidence file as a delimited, line-prefixed base64
block on stdout, and `tools/tg_phala_tdx_extract_evidence.py` turns the log
back into the files and verifies every digest.  The compose entry point then
holds the container open so the log can actually be fetched.

What is emitted, and what is not
--------------------------------

The file list is a hardcoded ALLOWLIST.  Nothing is emitted because it happens
to be in a directory; a file is emitted only if it is named below.  In
particular:

* the enclave signing key is not on the list and never can be -- `_self_check`
  refuses to start if any listed name looks like key material;
* `--refuse-if-contains` is additionally given the path of the derived key, and
  every blob is checked against those bytes before it is written to stdout.  A
  match aborts the whole emission without printing the offending blob, and
  without printing the secret in the error either;
* the retained A.7 artifact (1.5 MB, public, pinned by SHA-256) and the
  `dcap-qvl` binary (pinned by SHA-256) are not emitted: they are reproducible
  from their digests, which are.

The manifest block is emitted last and lists every file with its digest, so a
truncated log is detectable rather than silently short.

This module is embedded verbatim in `docker-compose.yaml`, so it is inside the
compose hash and inside RTMR3, exactly like the prelude.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys


MARKER = "SPARKINTERVAL-TDX-EVIDENCE-V1"
MANIFEST_NAME = "evidence-manifest.json"
MANIFEST_KIND = "sparkinterval.phala-tdx-evidence-manifest.v1"

# Base64 characters per DATA line.  Long enough that a big file does not
# produce an absurd number of lines, short enough to survive log viewers.
CHUNK = 512

MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024

# (root, relative name, required).  ROOTS are resolved from the command line.
# Adding anything here is a deliberate act: everything on this list is printed
# to a log that leaves the CVM.
# Ordered most load-bearing first.  `phala cvms logs` returns at most ~64 KiB,
# and the first real run lost the receipt because it was printed after
# `dstack-info.json`, whose 263,652 bytes exhausted that budget on their own.
# The signed statement and the result it commits to are therefore printed
# before anything bulky, so a truncated tail costs corroboration rather than
# the evidence itself.
#
# `dstack-info.json` is deliberately NOT on this list.  It is the guest
# agent's /Info response, dominated by the app certificate, and everything it
# attests that matters here is already carried by `tdx-quote.bin` and
# `dstack-event-log.json` -- which are on the list, and which the replay check
# ties together.  Re-adding it will silently cost you the receipt.
EVIDENCE: tuple[tuple[str, str, bool], ...] = (
    ("output", "enclave-receipt.json", True),
    ("output", "registered-result.txt", True),
    ("input", "registered-input.json", True),
    ("input", "job-scope.env", True),
    ("evidence", "prelude-summary.json", True),
    ("evidence", "rtmr-replay.json", True),
    ("input", "dcap-qvl-artifact.sha256", True),
    ("input", "tdx-quote.bin", True),
    ("input", "dcap-qvl-appraisal.json", True),
    ("evidence", "MEASUREMENTS-NOT-PINNED", False),
    ("evidence", "dcap-qvl-strict.json", True),
    ("evidence", "dcap-qvl-verify.stderr", False),
    ("input", "dcap-qvl-policy.json", True),
    ("output", "work/a7-replay.json", True),
    ("evidence", "dstack-event-log.json", True),
)

# Staged in the CVM and committed to by digest in the receipt, but NOT printed:
# `dcap-qvl-decode.json` is 18,770 bytes of the ~64 KiB budget and is the
# appraiser's rendering of a quote that is itself emitted in full, so it adds
# no fact that `tdx-quote.bin` plus `dcap-qvl-appraisal.json` do not already
# carry.  `dstack-info.json` is 263,652 bytes and cost us the receipt on the
# first end-to-end run.  Anything re-added here comes out of the same budget
# and pushes the trailing blocks off the end of the retrievable log.
WITHHELD_FROM_LOG = ("dcap-qvl-decode.json", "dstack-info.json")

# Substrings that must never appear in an emitted file name.  This is a
# belt-and-braces check on the allowlist above, evaluated at start-up.
FORBIDDEN_NAME_SUBSTRINGS = ("signing-key", "enclave-key", "private", "secret")


class EvidenceError(RuntimeError):
    """Something would have been emitted that must not be."""


def _self_check() -> None:
    names = [name for _root, name, _required in EVIDENCE] + [MANIFEST_NAME]
    if len(names) != len(set(names)):
        raise EvidenceError("the evidence allowlist has a duplicate name")
    for name in names:
        lowered = name.lower()
        for forbidden in FORBIDDEN_NAME_SUBSTRINGS:
            if forbidden in lowered:
                raise EvidenceError(
                    f"the evidence allowlist names {name!r}, which looks like "
                    "key material; refusing to emit anything"
                )
        if name.startswith("/") or ".." in Path(name).parts:
            raise EvidenceError(f"the evidence allowlist name {name!r} is unsafe")


def _canonical(document: object) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    )


def _read(path: Path) -> bytes:
    if path.is_symlink():
        raise EvidenceError(f"{path} is a symlink; refusing to follow it")
    with path.open("rb") as source:
        raw = source.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise EvidenceError(f"{path} exceeds the {MAX_FILE_BYTES}-byte emit limit")
    return raw


class Emitter:
    def __init__(self, out, secrets: tuple[bytes, ...]) -> None:
        self.out = out
        self.secrets = secrets
        self.total = 0

    def check_secret_free(self, name: str, raw: bytes) -> None:
        for secret in self.secrets:
            if secret and secret in raw:
                # The message deliberately does not contain the secret.
                raise EvidenceError(
                    f"{name} contains the derived signing key; refusing to "
                    "print any evidence at all"
                )

    def emit(self, name: str, raw: bytes) -> str:
        self.check_secret_free(name, raw)
        self.total += len(raw)
        if self.total > MAX_TOTAL_BYTES:
            raise EvidenceError("the evidence exceeds the total emit limit")
        digest = hashlib.sha256(raw).hexdigest()
        header = _canonical(
            {"bytes": len(raw), "name": name, "sha256": digest}
        ).decode("ascii")
        print(f"{MARKER} BEGIN {header}", file=self.out)
        encoded = base64.b64encode(raw).decode("ascii")
        for start in range(0, len(encoded), CHUNK):
            print(f"{MARKER} DATA {encoded[start:start + CHUNK]}", file=self.out)
        if not encoded:
            print(f"{MARKER} DATA ", file=self.out)
        trailer = _canonical({"name": name, "sha256": digest}).decode("ascii")
        print(f"{MARKER} END {trailer}", file=self.out)
        self.out.flush()
        return digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--refuse-if-contains",
        type=Path,
        action="append",
        default=[],
        help="a file whose contents must not appear in anything emitted.  The "
        "derived signing key is passed here.",
    )
    parser.add_argument(
        "--campaign-status",
        type=int,
        default=0,
        help="exit status of the campaign entry point, recorded in the "
        "manifest so a partial emission is self-describing",
    )
    return parser


def load_secrets(paths: list[Path]) -> tuple[bytes, ...]:
    secrets: list[bytes] = []
    for path in paths:
        try:
            raw = path.read_bytes()
        except OSError:
            # A key file that does not exist cannot leak.  Its absence is not
            # an error: the campaign may have failed before deriving one.
            continue
        stripped = raw.strip()
        if stripped:
            secrets.append(stripped)
            # Also guard the untrimmed bytes, in case a copy kept the newline.
            if stripped != raw:
                secrets.append(raw)
    return tuple(secrets)


def run(args: argparse.Namespace) -> int:
    _self_check()
    roots = {
        "input": args.input_root,
        "evidence": args.evidence_root,
        "output": args.output_root,
    }
    secrets = load_secrets(list(args.refuse_if_contains))
    emitter = Emitter(sys.stdout, secrets)

    print(f"{MARKER} the evidence for this run follows, base64 per line.", flush=True)
    entries: list[dict] = []
    missing_required: list[str] = []
    for root_name, name, required in EVIDENCE:
        path = roots[root_name] / name
        if not path.is_file() or path.is_symlink():
            entries.append(
                {
                    "bytes": 0,
                    "name": name,
                    "present": False,
                    "required": required,
                    "root": root_name,
                    "sha256": "",
                }
            )
            if required:
                missing_required.append(f"{root_name}/{name}")
            continue
        raw = _read(path)
        digest = emitter.emit(name, raw)
        entries.append(
            {
                "bytes": len(raw),
                "name": name,
                "present": True,
                "required": required,
                "root": root_name,
                "sha256": digest,
            }
        )

    manifest = _canonical(
        {
            "campaign_exit_status": args.campaign_status,
            "files": entries,
            "kind": MANIFEST_KIND,
            "marker": MARKER,
            "missing_required": sorted(missing_required),
        }
    )
    emitter.emit(MANIFEST_NAME, manifest)
    print(f"{MARKER} end of evidence.", flush=True)

    if missing_required:
        print(
            "evidence emission: these required files were absent: "
            + ", ".join(sorted(missing_required)),
            file=sys.stderr,
            flush=True,
        )
        return 4
    return 0


def main() -> int:
    try:
        return run(build_parser().parse_args())
    except EvidenceError as error:
        print(f"evidence emission REFUSED: {error}", file=sys.stderr, flush=True)
        return 3
    except OSError as error:
        print(f"evidence emission failed: {error}", file=sys.stderr, flush=True)
        return 5


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())

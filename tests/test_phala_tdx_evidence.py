# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Getting the evidence out of the CVM, and refusing to get the key out.

A dstack CVM has no file channel: Docker volumes are not reachable from
outside, and `phala cvms logs` returns nothing for a container that has
exited.  What works, and was observed to work on real hardware, is a container
that prints what must be kept and then stays alive.  So the campaign prints
its evidence as delimited base64 and
``tools/tg_phala_tdx_extract_evidence.py`` turns the log back into files.

These tests need no Docker, no network and no TDX.  They cover:

* the round trip -- every emitted file comes back byte for byte;
* a tampered transcript -- one altered base64 character is refused and nothing
  is written;
* the signing key -- it is not on the allowlist, and if it somehow appeared
  inside a file that *is*, the emitter refuses to print anything at all;
* completeness -- a log with no manifest, or with a block the manifest does
  not list, is refused rather than silently accepted as partial.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EMITTER = ROOT / "proof_build/ch25_a7_phala_tdx/emit_phala_tdx_evidence.py"
EXTRACTOR = ROOT / "tools/tg_phala_tdx_extract_evidence.py"
MARKER = "SPARKINTERVAL-TDX-EVIDENCE-V1"

SECRET_SCALAR = "3f1a9c4e2b8d7605af31c29e4d5b6a7089cbe1f23a4d5e6f708192a3b4c5d6e7"

# Exactly the files the emitter's allowlist names, so the fixtures below are a
# complete run rather than a convenient subset.
INPUT_FILES = {
    "job-scope.env": b"SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID=" + b"9f" * 20 + b"\n",
    "registered-input.json": b'{"campaign":"ch25-a7-boundary-v1"}',
    "tdx-quote.bin": bytes(range(256)) * 4,
    "dcap-qvl-appraisal.json": b'{"status":"UpToDate"}',
    "dcap-qvl-policy.json": b'{"kind":"policy"}',
    "dcap-qvl-artifact.sha256": b"84bd  dcap-qvl\n",
}
EVIDENCE_FILES = {
    # dstack-info.json is deliberately absent: it is staged in the CVM but not
    # emitted, because its 263 KB exhausted the ~64 KiB `phala cvms logs`
    # budget on the first real run and cost us the receipt.
    "dstack-event-log.json": b"[]",
    "dcap-qvl-decode.json": b'{"header":{}}',
    "dcap-qvl-verify.stderr": b"",
    "dcap-qvl-strict.json": b'{"passed":false}',
    "rtmr-replay.json": b'{"replayed_rtmrs":{}}',
    "prelude-summary.json": b'{"measurements_pinned":true}',
}
OUTPUT_FILES = {
    "registered-result.txt": b"true",
    "enclave-receipt.json": b'{"signature":"ab"}',
    "work/a7-replay.json": b'{"accepted":true}',
}


class EvidenceHarness:
    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phala-evidence-"))
        self.inputs = self.tmp / "shared/input"
        self.evidence = self.tmp / "shared/evidence"
        self.output = self.tmp / "out/output"
        for root, files in (
            (self.inputs, INPUT_FILES),
            (self.evidence, EVIDENCE_FILES),
            (self.output, OUTPUT_FILES),
        ):
            for name, raw in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        self.key = self.tmp / "keys/enclave-signing-key.hex"
        self.key.parent.mkdir(parents=True, exist_ok=True)
        self.key.write_text(SECRET_SCALAR + "\n", encoding="ascii")

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def emit(self, *, status: int = 0) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable, str(EMITTER),
                "--input-root", str(self.inputs),
                "--evidence-root", str(self.evidence),
                "--output-root", str(self.output),
                "--refuse-if-contains", str(self.key),
                "--campaign-status", str(status),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

    def extract(self, log: str, out_dir: Path | None) -> subprocess.CompletedProcess:
        arguments = [sys.executable, str(EXTRACTOR)]
        if out_dir is not None:
            arguments += ["--out-dir", str(out_dir)]
        return subprocess.run(
            arguments, input=log, capture_output=True, text=True, timeout=300
        )


class EvidenceRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = EvidenceHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def test_every_file_comes_back_byte_for_byte(self) -> None:
        emitted = self.harness.emit()
        self.assertEqual(emitted.returncode, 0, emitted.stderr)
        recovered = self.harness.tmp / "recovered"
        extracted = self.harness.extract(emitted.stdout, recovered)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        for root, prefix, files in (
            (self.harness.inputs, "input", INPUT_FILES),
            (self.harness.evidence, "evidence", EVIDENCE_FILES),
            (self.harness.output, "output", OUTPUT_FILES),
        ):
            for name, raw in files.items():
                self.assertEqual(
                    (recovered / prefix / name).read_bytes(),
                    raw,
                    f"{prefix}/{name} did not round-trip",
                )
                self.assertEqual((root / name).read_bytes(), raw)

    def test_a_log_with_a_timestamp_prefix_still_parses(self) -> None:
        """`phala cvms logs` prefixes every line; the marker is searched for."""

        emitted = self.harness.emit()
        decorated = "".join(
            f"2026-07-27T00:00:00Z campaign-1  | {line}\n"
            for line in emitted.stdout.splitlines()
        )
        recovered = self.harness.tmp / "recovered-decorated"
        extracted = self.harness.extract(decorated, recovered)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        self.assertEqual(
            (recovered / "output/registered-result.txt").read_bytes(), b"true"
        )

    def test_interleaved_unrelated_log_lines_are_ignored(self) -> None:
        emitted = self.harness.emit()
        noisy = []
        for index, line in enumerate(emitted.stdout.splitlines()):
            noisy.append(line)
            if index % 3 == 0:
                noisy.append("some unrelated container chatter")
        extracted = self.harness.extract("\n".join(noisy), None)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)

    def test_the_manifest_records_a_failed_campaign(self) -> None:
        emitted = self.harness.emit(status=2)
        extracted = self.harness.extract(emitted.stdout, None)
        self.assertNotEqual(extracted.returncode, 0)
        self.assertIn("exited non-zero", extracted.stderr)


class EvidenceRefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = EvidenceHarness()
        self.emitted = self.harness.emit()
        self.assertEqual(self.emitted.returncode, 0, self.emitted.stderr)

    def tearDown(self) -> None:
        self.harness.close()

    def _flip_one_base64_character(self) -> str:
        lines = self.emitted.stdout.splitlines()
        for index, line in enumerate(lines):
            if line.startswith(f"{MARKER} DATA ") and len(line) > 40:
                position = 30
                original = line[position]
                lines[index] = (
                    line[:position]
                    + ("A" if original != "A" else "B")
                    + line[position + 1:]
                )
                return "\n".join(lines)
        raise AssertionError("no DATA line to tamper with")

    def test_a_tampered_digest_is_refused_and_nothing_is_written(self) -> None:
        out_dir = self.harness.tmp / "should-not-appear"
        extracted = self.harness.extract(self._flip_one_base64_character(), out_dir)
        self.assertNotEqual(extracted.returncode, 0)
        self.assertIn("REFUSED", extracted.stderr)
        self.assertFalse(
            out_dir.exists() and list(out_dir.rglob("*")),
            "a refused extraction must write nothing",
        )

    def test_a_truncated_log_is_refused(self) -> None:
        lines = self.emitted.stdout.splitlines()
        extracted = self.harness.extract("\n".join(lines[:-4]), None)
        self.assertNotEqual(extracted.returncode, 0)
        self.assertIn("REFUSED", extracted.stderr)

    def test_a_log_without_a_manifest_is_refused(self) -> None:
        """Otherwise a partial transcript would look like a complete one."""

        lines = self.emitted.stdout.splitlines()
        start = max(
            index for index, line in enumerate(lines)
            if line.startswith(f"{MARKER} BEGIN ")
            and "evidence-manifest.json" in line
        )
        extracted = self.harness.extract("\n".join(lines[:start]), None)
        self.assertNotEqual(extracted.returncode, 0)
        self.assertIn("no evidence-manifest.json block", extracted.stderr)

    def test_an_unlisted_block_is_refused(self) -> None:
        """A block the manifest does not name means the log was doctored."""

        raw = b"not part of this run"
        digest = hashlib.sha256(raw).hexdigest()
        header = json.dumps(
            {"bytes": len(raw), "name": "smuggled.json", "sha256": digest},
            sort_keys=True,
            separators=(",", ":"),
        )
        trailer = json.dumps(
            {"name": "smuggled.json", "sha256": digest},
            sort_keys=True,
            separators=(",", ":"),
        )
        injected = "\n".join(
            [
                f"{MARKER} BEGIN {header}",
                f"{MARKER} DATA {base64.b64encode(raw).decode('ascii')}",
                f"{MARKER} END {trailer}",
            ]
        )
        extracted = self.harness.extract(
            self.emitted.stdout + injected + "\n", None
        )
        self.assertNotEqual(extracted.returncode, 0)
        self.assertIn("unlisted block", extracted.stderr)

    def test_a_block_claiming_to_be_key_material_is_refused(self) -> None:
        raw = b"whatever"
        digest = hashlib.sha256(raw).hexdigest()
        header = json.dumps(
            {
                "bytes": len(raw),
                "name": "enclave-signing-key.hex",
                "sha256": digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        extracted = self.harness.extract(
            self.emitted.stdout + f"{MARKER} BEGIN {header}\n", None
        )
        self.assertNotEqual(extracted.returncode, 0)
        self.assertIn("looks like key material", extracted.stderr)


class SigningKeyIsNeverPrintedTests(unittest.TestCase):
    """The one property this whole channel must not violate."""

    def setUp(self) -> None:
        self.harness = EvidenceHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def test_the_key_file_is_not_on_the_allowlist(self) -> None:
        emitted = self.harness.emit()
        self.assertEqual(emitted.returncode, 0, emitted.stderr)
        self.assertNotIn(SECRET_SCALAR, emitted.stdout)
        self.assertNotIn(SECRET_SCALAR, emitted.stderr)
        self.assertNotIn("enclave-signing-key", emitted.stdout)
        # Even placing it inside the emitted tree does not get it printed.
        (self.harness.inputs / "enclave-signing-key.hex").write_text(
            SECRET_SCALAR + "\n", encoding="ascii"
        )
        again = self.harness.emit()
        self.assertNotIn(SECRET_SCALAR, again.stdout)
        recovered = self.harness.tmp / "recovered"
        extracted = self.harness.extract(again.stdout, recovered)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        for path in recovered.rglob("*"):
            if path.is_file():
                self.assertNotIn(
                    SECRET_SCALAR, path.read_bytes().decode("latin-1")
                )

    def test_the_key_inside_an_allowlisted_file_aborts_the_whole_emission(
        self,
    ) -> None:
        """Nothing is printed, not even the blocks that were already fine."""

        (self.harness.evidence / "prelude-summary.json").write_text(
            json.dumps({"oops": SECRET_SCALAR}), encoding="utf-8"
        )
        emitted = self.harness.emit()
        self.assertNotEqual(emitted.returncode, 0)
        self.assertIn("REFUSED", emitted.stderr)
        self.assertNotIn(SECRET_SCALAR, emitted.stdout)
        self.assertNotIn(SECRET_SCALAR, emitted.stderr)
        # And what it did print cannot be mistaken for a complete transcript.
        extracted = self.harness.extract(emitted.stdout, None)
        self.assertNotEqual(extracted.returncode, 0)

    def test_the_allowlist_itself_refuses_key_shaped_names(self) -> None:
        source = EMITTER.read_text(encoding="utf-8")
        self.assertIn("FORBIDDEN_NAME_SUBSTRINGS", source)
        self.assertIn("_self_check", source)
        for name in ("signing-key", "enclave-key", "private", "secret"):
            self.assertIn(f'"{name}"', source)


if __name__ == "__main__":
    unittest.main()

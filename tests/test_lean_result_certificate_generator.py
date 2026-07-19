#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from reference import evaluator
from reference import format as wire


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "generate_lean_result_certificate.py"
MEMORY_RUNNER = ROOT / "tools" / "with_memory_limit.sh"
SAFE_LAKE_BUILD = ROOT / "tools" / "safe_lake_build.py"
SAFE_LEAN = ROOT / "tools" / "safe_lean.sh"
EXAMPLE_BATCH = ROOT / "examples" / "reference-certificate" / "batch.json"
TRACKED_CERTIFICATE = ROOT / "examples" / "lean-result-certificate" / "certificate.json"
TRACKED_SOURCE = (
    ROOT / "examples" / "lean-result-certificate" / "GeneratedFullCertificate.lean"
)
SCHEMA = ROOT / "schemas" / "lean-result-certificate-receipt.schema.json"
MAX_FINITE = "7fefffffffffffff"
EXAMPLE_BOUND = "4010000000000001"
GOLDEN_SOURCE_SHA256 = "c2f866f247525ec2b77c83c2ebb9f9eefaa9c9db49ea615714e892aa76f44001"


def point(bits: str) -> dict[str, str]:
    return {"lo": bits, "hi": bits}


class LeanResultCertificateGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.batch = wire.load_batch(EXAMPLE_BATCH)
        self.certificate = evaluator.issue_certificate(self.batch)
        self.certificate_path = self.directory / "certificate.json"
        self._write_certificate(self.certificate, self.certificate_path)

    @staticmethod
    def _write_certificate(certificate: dict, path: Path) -> None:
        path.write_bytes(wire.canonical_json_bytes(certificate))

    def _run(
        self,
        output: Path,
        *,
        certificate: Path | None = None,
        upper_bound: str = MAX_FINITE,
        decision_mode: str = "kernel",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--certificate",
                str(self.certificate_path if certificate is None else certificate),
                "--upper-bound",
                upper_bound,
                "--decision-mode",
                decision_mode,
                "--output",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_is_deterministic_and_receipt_binds_complete_source(self) -> None:
        first = self.directory / "First.lean"
        second = self.directory / "Second.lean"
        first_run = self._run(first)
        second_run = self._run(second)
        self.assertEqual(first_run.returncode, 0, first_run.stderr)
        self.assertEqual(second_run.returncode, 0, second_run.stderr)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_run.stdout, second_run.stdout)
        self.assertFalse(first_run.stdout.endswith("\n"))

        source = first.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), GOLDEN_SOURCE_SHA256)
        receipt = json.loads(first_run.stdout)
        self.assertEqual(
            first_run.stdout.encode("utf-8"), wire.canonical_json_bytes(receipt)
        )
        self.assertEqual(
            receipt["lean_source_sha256"], hashlib.sha256(source).hexdigest()
        )
        self.assertEqual(receipt["lean_source_size_bytes"], len(source))
        self.assertEqual(
            receipt["certificate_sha256"],
            wire.canonical_sha256(self.certificate),
        )
        self.assertEqual(
            receipt["lean_declaration"],
            "SparkInterval.GeneratedCertificate."
            f"C_{wire.canonical_sha256(self.certificate)}_B_{MAX_FINITE}_M_kernel.certificate",
        )
        self.assertEqual(
            receipt["lean_theorem"],
            "SparkInterval.GeneratedCertificate."
            f"C_{wire.canonical_sha256(self.certificate)}_B_{MAX_FINITE}_M_kernel.application_theorem",
        )
        self.assertEqual(
            receipt["lean_sum_theorem"],
            "SparkInterval.GeneratedCertificate."
            f"C_{wire.canonical_sha256(self.certificate)}_B_{MAX_FINITE}_M_kernel.application_sum_theorem",
        )
        self.assertEqual(receipt["decision_mode"], "kernel")
        self.assertNotIn(str(self.directory), source.decode("utf-8"))
        self.assertIn(
            f'def sourceBatchSha256 : String := "{self.certificate["batch_sha256"]}"',
            source.decode("utf-8"),
        )
        self.assertIn(
            b"def sourceCertificateJson : String :=\n  r#\""
            + wire.canonical_json_bytes(self.certificate)
            + b"\"#\n",
            source,
        )
        self.assertIn("theorem source_certificate_sha256_check", source.decode("utf-8"))
        self.assertIn("theorem source_certificate_parse", source.decode("utf-8"))
        self.assertIn("theorem certificate_check", source.decode("utf-8"))
        self.assertIn("set_option maxRecDepth 1000000", source.decode("utf-8"))
        self.assertIn("set_option cbv.maxSteps 10000000", source.decode("utf-8"))
        self.assertIn("set_option maxHeartbeats 2000000", source.decode("utf-8"))
        self.assertIn("set_option exponentiation.threshold 2048", source.decode("utf-8"))
        self.assertGreaterEqual(source.decode("utf-8").count("  decide_cbv"), 3)
        self.assertIn("theorem certificate_upper_bound_check", source.decode("utf-8"))
        self.assertIn("theorem certificate_upper_bound_decode", source.decode("utf-8"))
        self.assertIn("theorem application_upper_bound_decode", source.decode("utf-8"))
        self.assertIn(
            "theorem certificate_upper_bound_le_application", source.decode("utf-8")
        )
        self.assertIn("theorem application_upper_bound_sound", source.decode("utf-8"))
        self.assertIn("theorem certificate_sum_check", source.decode("utf-8"))
        self.assertIn(
            "theorem certificate_sum_upper_bound_sound", source.decode("utf-8")
        )
        self.assertIn("theorem application_theorem", source.decode("utf-8"))
        self.assertIn("theorem application_sum_theorem", source.decode("utf-8"))
        self.assertIn("#print axioms application_theorem", source.decode("utf-8"))
        self.assertIn(
            "#print axioms application_upper_bound_sound", source.decode("utf-8")
        )

    def test_emits_every_expression_constructor_and_raw_signed_zero_words(self) -> None:
        one = point("3ff0000000000000")
        two = point("4000000000000000")
        expression = {
            "op": "max",
            "left": {
                "op": "min",
                "left": {
                    "op": "abs",
                    "arg": {
                        "op": "neg",
                        "arg": {
                            "op": "sub",
                            "left": {
                                "op": "add",
                                "left": {"op": "var", "index": 0},
                                "right": {"op": "const", "value": one},
                            },
                            "right": {
                                "op": "mul",
                                "left": {"op": "var", "index": 1},
                                "right": {
                                    "op": "pow_nat",
                                    "arg": {"op": "var", "index": 2},
                                    "exponent": 2,
                                },
                            },
                        },
                    },
                },
                "right": {
                    "op": "div",
                    "left": {"op": "var", "index": 0},
                    "right": {"op": "const", "value": two},
                },
            },
            "right": {"op": "const", "value": one},
        }
        batch = {
            "schema_version": 1,
            "kind": wire.BATCH_KIND,
            "algorithm": wire.ALGORITHM_ID,
            "variable_count": 3,
            "expression": expression,
            "rows": [
                [
                    {"lo": "8000000000000000", "hi": "0000000000000000"},
                    two,
                    point("4008000000000000"),
                ]
            ],
        }
        certificate = evaluator.issue_certificate(batch)
        path = self.directory / "full-certificate.json"
        self._write_certificate(certificate, path)
        output = self.directory / "Full.lean"
        completed = self._run(output, certificate=path)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        source = output.read_text(encoding="utf-8")
        for constructor in (
            ".const",
            ".var",
            ".neg",
            ".add",
            ".sub",
            ".mul",
            ".div",
            ".abs",
            ".min",
            ".max",
            ".powNat",
        ):
            self.assertIn(constructor, source)
        self.assertIn("0x8000000000000000", source)
        self.assertIn("0x0000000000000000", source)

    def test_rejects_arithmetically_wrong_but_well_bound_certificate(self) -> None:
        tampered = copy.deepcopy(self.certificate)
        tampered["result"]["rows"][0]["hi"] = MAX_FINITE
        tampered["result_sha256"] = wire.canonical_sha256(tampered["result"])
        wire.validate_certificate(tampered)
        path = self.directory / "wrong-result.json"
        self._write_certificate(tampered, path)
        output = self.directory / "Wrong.lean"
        completed = self._run(output, certificate=path)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("exact recomputation", completed.stderr)
        self.assertFalse(output.exists())

    def test_rejects_noncanonical_input_and_hash_mismatch_without_output(self) -> None:
        noncanonical = self.directory / "noncanonical.json"
        noncanonical.write_bytes(self.certificate_path.read_bytes() + b"\n")
        output = self.directory / "Noncanonical.lean"
        completed = self._run(output, certificate=noncanonical)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not canonical JSON", completed.stderr)
        self.assertFalse(output.exists())

        bad_hash = copy.deepcopy(self.certificate)
        bad_hash["batch_sha256"] = "00" * 32
        bad_hash_path = self.directory / "bad-hash.json"
        self._write_certificate(bad_hash, bad_hash_path)
        output = self.directory / "BadHash.lean"
        completed = self._run(output, certificate=bad_hash_path)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("SHA-256 mismatch", completed.stderr)
        self.assertFalse(output.exists())

    def test_rejects_nonfinite_noncanonical_and_too_low_bounds(self) -> None:
        invalid_bounds = (
            "7ff0000000000000",
            "fff0000000000000",
            "7ff8000000000000",
            "7FEFFFFFFFFFFFFF",
            "7feffffffffffff",
            "0000000000000000",
        )
        for index, bound in enumerate(invalid_bounds):
            with self.subTest(bound=bound):
                output = self.directory / f"InvalidBound{index}.lean"
                completed = self._run(output, upper_bound=bound)
                self.assertNotEqual(completed.returncode, 0)
                self.assertFalse(output.exists())

    def test_refuses_overwrite_and_non_lean_destination(self) -> None:
        output = self.directory / "Certificate.lean"
        first = self._run(output)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()
        second = self._run(output)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("refusing to overwrite", second.stderr)
        self.assertEqual(output.read_bytes(), original)

        wrong_suffix = self.directory / "certificate.txt"
        completed = self._run(wrong_suffix)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(".lean suffix", completed.stderr)
        self.assertFalse(wrong_suffix.exists())

        sentinel = self.directory / "sentinel.txt"
        sentinel.write_bytes(b"must remain unchanged")
        symlink_output = self.directory / "Symlink.lean"
        symlink_output.symlink_to(sentinel)
        completed = self._run(symlink_output)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("refusing to overwrite", completed.stderr)
        self.assertTrue(symlink_output.is_symlink())
        self.assertEqual(sentinel.read_bytes(), b"must remain unchanged")

    def test_receipt_schema_is_closed_and_matches_cli_contract(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]), set(schema["properties"])
        )
        declaration_pattern = schema["properties"]["lean_declaration"]["pattern"]
        theorem_pattern = schema["properties"]["lean_theorem"]["pattern"]
        sum_theorem_pattern = schema["properties"]["lean_sum_theorem"]["pattern"]
        output = self.directory / "Schema.lean"
        completed = self._run(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(set(receipt), set(schema["required"]))
        self.assertIsNotNone(re.fullmatch(declaration_pattern, receipt["lean_declaration"]))
        self.assertIsNotNone(re.fullmatch(theorem_pattern, receipt["lean_theorem"]))
        self.assertIsNotNone(
            re.fullmatch(sum_theorem_pattern, receipt["lean_sum_theorem"])
        )

    def test_namespace_is_bound_to_certificate_and_bound_and_example_is_current(self) -> None:
        exact_output = self.directory / "ExactBound.lean"
        exact_run = self._run(exact_output, upper_bound=EXAMPLE_BOUND)
        self.assertEqual(exact_run.returncode, 0, exact_run.stderr)
        loose_output = self.directory / "LooseBound.lean"
        loose_run = self._run(loose_output, upper_bound=MAX_FINITE)
        self.assertEqual(loose_run.returncode, 0, loose_run.stderr)
        exact_receipt = json.loads(exact_run.stdout)
        loose_receipt = json.loads(loose_run.stdout)
        self.assertNotEqual(
            exact_receipt["lean_declaration"], loose_receipt["lean_declaration"]
        )
        self.assertNotEqual(exact_output.read_bytes(), loose_output.read_bytes())

        tracked_output = self.directory / "Tracked.lean"
        tracked_run = self._run(
            tracked_output,
            certificate=TRACKED_CERTIFICATE,
            upper_bound=EXAMPLE_BOUND,
        )
        self.assertEqual(tracked_run.returncode, 0, tracked_run.stderr)
        self.assertEqual(tracked_output.read_bytes(), TRACKED_SOURCE.read_bytes())

    def test_cli_receipt_binds_certificate_checker_and_application_bound(self) -> None:
        if shutil.which("lake") is None:
            self.skipTest("lake is required for certificate CLI integration")
        built = subprocess.run(
            [
                sys.executable,
                str(SAFE_LAKE_BUILD),
                "--target",
                "sparkinterval-check-certificate",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        receipts = []
        for bound in (EXAMPLE_BOUND, MAX_FINITE):
            checked = subprocess.run(
                [
                    str(MEMORY_RUNNER),
                    str(ROOT / ".lake/build/bin/sparkinterval-check-certificate"),
                    str(self.certificate_path),
                    "--upper-bound",
                    bound,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            receipt = json.loads(checked.stdout)
            self.assertEqual(receipt["application_upper_bound"], bound)
            self.assertEqual(
                receipt["certificate_sha256"],
                wire.canonical_sha256(self.certificate),
            )
            self.assertEqual(
                receipt["checker"],
                "sparkinterval.lean_full_certificate_checker.v1",
            )
            self.assertEqual(
                checked.stdout.rstrip("\n").encode("utf-8"),
                json.dumps(
                    receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8"),
            )
            receipts.append(receipt)
        self.assertNotEqual(receipts[0], receipts[1])

    def test_generated_source_typechecks_against_lean_core(self) -> None:
        if not (ROOT / "SparkInterval" / "Certificate.lean").is_file():
            self.skipTest("aggregate Phase-8 Lean certificate module is not ready")
        lake = shutil.which("lake")
        if lake is None:
            self.skipTest("lake is required for generated-source integration")
        output = self.directory / "GeneratedCertificate.lean"
        generated = self._run(output)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        built = subprocess.run(
            [sys.executable, str(SAFE_LAKE_BUILD), "SparkInterval.Certificate"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        checked = subprocess.run(
            [str(SAFE_LEAN), str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            checked.returncode, 0, checked.stdout + checked.stderr
        )
        self.assertIn("application_theorem", checked.stdout)
        self.assertIn("native_decide.ax", checked.stdout)

        native_output = self.directory / "GeneratedNativeCertificate.lean"
        native_generated = self._run(native_output, decision_mode="native")
        self.assertEqual(native_generated.returncode, 0, native_generated.stderr)
        native_receipt = json.loads(native_generated.stdout)
        self.assertEqual(native_receipt["decision_mode"], "native")
        native_checked = subprocess.run(
            [str(SAFE_LEAN), str(native_output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            native_checked.returncode,
            0,
            native_checked.stdout + native_checked.stderr,
        )
        self.assertIn("certificate_check._native.native_decide.ax", native_checked.stdout)


if __name__ == "__main__":
    unittest.main()

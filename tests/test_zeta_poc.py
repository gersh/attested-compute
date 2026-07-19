from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
import sys

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from reference import exact_binary64 as exact  # noqa: E402
import create_run_bundle as bundle_format  # noqa: E402
import run_expression_conformance as expression  # noqa: E402
import run_zeta_poc as zeta  # noqa: E402


FIXED_START = "2026-07-19T12:00:00Z"
FIXED_END = "2026-07-19T12:00:01Z"
FIXED_NONCE = "ab" * 32


def valid_expression_ptx() -> bytes:
    instructions: list[str] = []
    for name, count in zeta.inspect_expression_ptx.EXPECTED_DIRECTED_COUNTS.items():
        instructions.extend(f"  {name} %fd1, %fd2, %fd3;" for _ in range(count))
    return (
        ".version 9.0\n"
        ".target sm_121\n"
        ".address_size 64\n"
        ".entry expression_batch_kernel()\n"
        "{\n"
        ".local .align 16 .b8 stack[512];\n"
        + "\n".join(instructions)
        + "\n  ret;\n}\n"
    ).encode("ascii")


def write_runner_report(path: Path, *, terms: int) -> None:
    value = {
        "schema_version": 1,
        "kind": "sparkinterval_cuda_expression_batch",
        "instruction_count": 4,
        "variable_count": 1,
        "max_stack_depth": 2,
        "row_count": terms,
        "valid_row_count": terms,
        "zero_divisor_row_count": 0,
        "nonfinite_widening_row_count": 0,
        "all_rows_valid": True,
        "device_name": "NVIDIA GB10",
        "compute_capability": "12.1",
        "cuda_driver_api_version": 13000,
        "cuda_runtime_version": 13000,
        "kernel_milliseconds": 0.125,
        "kernel_rows_per_second": terms * 8000.0,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_exact_output(path: Path, *, s: int, terms: int) -> None:
    program = zeta.zeta_program(s)
    payload = bytearray(
        expression.HEADER.pack(
            expression.OUTPUT_MAGIC,
            expression.FORMAT_VERSION,
            len(program.instructions),
            program.variable_count,
            expression.validated_max_stack(program),
            terms,
        )
    )
    for row in zeta.zeta_rows(terms):
        lo, hi, status = expression.evaluate_program(program, row)
        payload += expression.OUTPUT.pack(lo, hi, status, bytes(7))
    path.write_bytes(payload)


def contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, list):
        return any(contains_float(item) for item in value)
    if isinstance(value, dict):
        return any(contains_float(item) for item in value.values())
    return False


class OfflineFixture:
    """Build a semantically complete retained run without invoking CUDA."""

    def __init__(self, root: Path, *, s: int, terms: int) -> None:
        self.root = root
        self.s = s
        self.terms = terms
        root.mkdir()
        for role, source in zeta.STAGED_SOURCES.items():
            destination = root / zeta.STAGED_PATHS[role]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        executable = root / zeta.STAGED_PATHS["host_executable"]
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"#!/bin/sh\n# synthetic expression runner\nexit 0\n")
        executable.chmod(0o755)
        cuobjdump = root / zeta.STAGED_PATHS["tool_cuobjdump"]
        cuobjdump.write_bytes(b"#!/bin/sh\n# synthetic cuobjdump\nexit 0\n")
        cuobjdump.chmod(0o755)

        ptx = root / zeta.STAGED_PATHS["gpu_ptx"]
        sass = root / zeta.STAGED_PATHS["gpu_sass"]
        ptx.write_bytes(valid_expression_ptx())
        sass.write_bytes(
            b".target sm_121\nFunction : expression_batch_kernel\n"
            b"/*0000*/ DADD.RM R2, R4, R6 ; /* encoding */\n"
            b"/*0010*/ EXIT ; /* encoding */\n"
        )
        zeta._write_canonical(
            root / zeta.STAGED_PATHS["ptx_audit"],
            zeta.inspect_expression_ptx.audit_ptx(
                ptx.read_bytes(), expected_target="sm_121"
            ),
        )
        sass_audit_path = root / zeta.STAGED_PATHS["sass_audit"]
        completed = subprocess.run(
            [
                sys.executable,
                str(zeta.STAGED_SOURCES["source_sass_audit"]),
                str(sass),
                str(sass_audit_path),
                "--allow-division-lowering",
            ],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
        zeta._write_canonical(
            sass_audit_path, zeta._load_runner_report(sass_audit_path)
        )

        zeta.write_input(root / zeta.INPUT_NAME, s, terms)
        write_exact_output(root / zeta.OUTPUT_NAME, s=s, terms=terms)
        shutil.copy2(root / zeta.OUTPUT_NAME, root / zeta.REPLAY_OUTPUT_NAME)
        write_runner_report(
            root / zeta.STAGED_PATHS["runner_report"], terms=terms
        )
        write_runner_report(
            root / zeta.STAGED_PATHS["replay_runner_report"], terms=terms
        )
        self.rebuild_report()
        self.rebuild_bundle()

    def rebuild_report(self) -> None:
        derived = zeta.derive_output(
            self.root / zeta.OUTPUT_NAME, self.s, self.terms
        )
        zeta._write_canonical(
            self.root / zeta.REPORT_NAME,
            zeta.make_report(self.root, self.s, self.terms, derived),
        )

    def rebuild_bundle(self) -> None:
        zeta.create_local_bundle(
            self.root,
            s=self.s,
            terms=self.terms,
            nonce=FIXED_NONCE,
            start_time_utc=FIXED_START,
            end_time_utc=FIXED_END,
        )


class ZetaPocTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_v1_algorithm_definition_is_immutable_and_pinned(self) -> None:
        self.assertEqual(
            zeta.ALGORITHM_DEFINITION,
            REPOSITORY_ROOT / "specifications/REAL_ZETA_POC.md",
        )
        self.assertEqual(
            hashlib.sha256(zeta.ALGORITHM_DEFINITION.read_bytes()).hexdigest(),
            "9a3bd6af5548d2c8c882f30787e4fe1170babca78143a24d40523fbf72ec6cb9",
        )

    def test_integral_tail_formula_for_zeta_two(self) -> None:
        lower, upper = zeta._tail_bounds(2, 4096)
        self.assertEqual((lower.numerator, lower.denominator), (1, 4097))
        self.assertEqual((upper.numerator, upper.denominator), (1, 4096))

    def test_exact_synthetic_zeta_two_verifies_without_gpu(self) -> None:
        fixture = OfflineFixture(self.base / "zeta2", s=2, terms=32)
        receipt = zeta.verify_work_dir(fixture.root)
        self.assertTrue(receipt["accepted"])
        self.assertEqual(receipt["integer_s"], 2)
        self.assertEqual(receipt["term_count"], 32)
        self.assertEqual(receipt["evidence_class"], "local_unattested")
        self.assertFalse(receipt["hardware_evidence"])

        report = bundle_format.load_canonical_json(fixture.root / zeta.REPORT_NAME)
        self.assertFalse(contains_float(report))
        self.assertEqual(
            report["tail"]["lower_rational"],
            {"numerator": "1", "denominator": "33"},
        )
        self.assertEqual(
            report["tail"]["upper_rational"],
            {"numerator": "1", "denominator": "32"},
        )

    def test_general_integer_s_verifies(self) -> None:
        fixture = OfflineFixture(self.base / "zeta3", s=3, terms=24)
        receipt = zeta.verify_work_dir(fixture.root)
        self.assertEqual(receipt["integer_s"], 3)
        report = bundle_format.load_canonical_json(fixture.root / zeta.REPORT_NAME)
        self.assertEqual(
            report["tail"]["lower_rational"],
            {"numerator": "1", "denominator": str(2 * 25**2)},
        )
        self.assertEqual(
            report["tail"]["upper_rational"],
            {"numerator": "1", "denominator": str(2 * 24**2)},
        )

    def test_semantic_gpu_output_tamper_rejected_after_rebinding_bundle(self) -> None:
        fixture = OfflineFixture(self.base / "output-tamper", s=2, terms=12)
        output = fixture.root / zeta.OUTPUT_NAME
        raw = bytearray(output.read_bytes())
        lo, hi, status, reserved = expression.OUTPUT.unpack_from(
            raw, expression.HEADER.size
        )
        expression.OUTPUT.pack_into(
            raw,
            expression.HEADER.size,
            exact.next_down_bits(lo),
            hi,
            status,
            reserved,
        )
        output.write_bytes(raw)
        # Rebinding the generic integrity bundle cannot bypass arithmetic
        # recomputation by the zeta verifier.
        fixture.rebuild_bundle()
        with self.assertRaisesRegex(zeta.ZetaPocError, "exact recomputation"):
            zeta.verify_work_dir(fixture.root)

    def test_report_tamper_rejected_even_with_recomputed_bundle_hash(self) -> None:
        fixture = OfflineFixture(self.base / "report-tamper", s=2, terms=12)
        report = bundle_format.load_canonical_json(fixture.root / zeta.REPORT_NAME)
        report["zeta_enclosure"]["real"]["lo"] = "0000000000000000"
        zeta._write_canonical(fixture.root / zeta.REPORT_NAME, report)
        fixture.rebuild_bundle()
        with self.assertRaisesRegex(zeta.ZetaPocError, "independent artifact recomputation"):
            zeta.verify_work_dir(fixture.root)

    def test_replay_tamper_rejected_after_rebinding_bundle(self) -> None:
        fixture = OfflineFixture(self.base / "replay-tamper", s=2, terms=12)
        replay = fixture.root / zeta.REPLAY_OUTPUT_NAME
        raw = bytearray(replay.read_bytes())
        raw[-1] = 1
        replay.write_bytes(raw)
        fixture.rebuild_bundle()
        with self.assertRaisesRegex(zeta.ZetaPocError, "reserved bytes"):
            zeta.verify_work_dir(fixture.root)

    def test_input_program_tamper_rejected_after_rebinding_bundle(self) -> None:
        fixture = OfflineFixture(self.base / "input-tamper", s=2, terms=12)
        input_path = fixture.root / zeta.INPUT_NAME
        raw = bytearray(input_path.read_bytes())
        # Change pow_nat(2) to pow_nat(3), leaving the report untouched.
        pow_argument_offset = expression.HEADER.size + 2 * expression.INSTRUCTION.size + 4
        raw[pow_argument_offset] = 3
        input_path.write_bytes(raw)
        fixture.rebuild_bundle()
        with self.assertRaisesRegex(zeta.ZetaPocError, "postfix program"):
            zeta.verify_work_dir(fixture.root)

    def test_parameter_limits_fail_closed(self) -> None:
        with self.assertRaisesRegex(zeta.ZetaPocError, "s must be"):
            zeta.validate_parameters(1, 10)
        with self.assertRaisesRegex(zeta.ZetaPocError, "terms must be"):
            zeta.validate_parameters(2, 0)
        with self.assertRaisesRegex(zeta.ZetaPocError, "nonfinite"):
            zeta.validate_parameters(64, 1_000_000)


if __name__ == "__main__":
    unittest.main()

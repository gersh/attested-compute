#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from reference import format as wire


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / ".lake/build/bin/sparkinterval-gen"
AUDIT = ROOT / "tools/inspect_generated_ptx.py"
MEMORY_RUNNER = ROOT / "tools/with_memory_limit.sh"
SAFE_LAKE_BUILD = ROOT / "tools/safe_lake_build.py"
GOLDEN_SHA256 = "2a1b3d8ebf6161521b82d352b2f2773b07e9a1b8597bc045ad038f876199f14d"


def sample_batch() -> dict:
    return {
        "schema_version": wire.SCHEMA_VERSION,
        "kind": wire.BATCH_KIND,
        "algorithm": wire.ALGORITHM_ID,
        "variable_count": 2,
        "expression": {
            "op": "add",
            "left": {
                "op": "mul",
                "left": {"op": "var", "index": 0},
                "right": {"op": "var", "index": 1},
            },
            "right": {
                "op": "const",
                "value": {
                    "lo": "3ff0000000000000",
                    "hi": "3ff0000000000000",
                },
            },
        },
        "rows": [
            [
                {"lo": "bff0000000000000", "hi": "3ff0000000000000"},
                {"lo": "4000000000000000", "hi": "4008000000000000"},
            ]
        ],
    }


class PtxGeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [str(SAFE_LAKE_BUILD), "--target", "sparkinterval-gen"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def generate(self, batch: dict, *, canonical: bool = True):
        temporary = tempfile.TemporaryDirectory()
        directory = Path(temporary.name)
        input_path = directory / "batch.json"
        output_path = directory / "kernel.ptx"
        encoded = wire.canonical_json_bytes(batch)
        input_path.write_bytes(encoded if canonical else encoded + b"\n")
        completed = subprocess.run(
            [
                str(MEMORY_RUNNER),
                str(GENERATOR),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return temporary, output_path, completed

    def test_deterministic_golden_and_ptxas(self) -> None:
        first_dir, first_path, first = self.generate(sample_batch())
        second_dir, second_path, second = self.generate(sample_batch())
        self.addCleanup(first_dir.cleanup)
        self.addCleanup(second_dir.cleanup)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_bytes = first_path.read_bytes()
        self.assertEqual(first_bytes, second_path.read_bytes())
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), GOLDEN_SHA256)
        text = first_bytes.decode("utf-8")
        self.assertIn(".target sm_121", text)
        self.assertIn("mul.rm.f64", text)
        self.assertIn("mul.rp.f64", text)
        self.assertIn("add.rm.f64", text)
        self.assertIn("add.rp.f64", text)
        self.assertNotIn(".rn.f64", text)
        self.assertNotIn(".rz.f64", text)
        self.assertNotIn("fma.", text)
        self.assertIn("st.global.u8", text)
        ptxas = shutil.which("ptxas")
        if ptxas is None:
            self.skipTest("ptxas is not installed")
        cubin = first_path.with_suffix(".cubin")
        assembled = subprocess.run(
            [ptxas, "-arch=sm_121", str(first_path), "-o", str(cubin)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(assembled.returncode, 0, assembled.stderr)
        self.assertGreater(cubin.stat().st_size, 0)

    def test_independent_allowlist_audit_and_injection_rejection(self) -> None:
        temporary, ptx_path, generated = self.generate(sample_batch())
        self.addCleanup(temporary.cleanup)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        report_path = ptx_path.with_suffix(".audit.json")
        accepted = subprocess.run(
            [str(AUDIT), str(ptx_path), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertTrue(json.loads(report_path.read_text())["passed"])
        injected = ptx_path.read_text().replace(
            "\tret;", "\tfma.rn.f64 %fd0, %fd0, %fd0, %fd0;\n\tret;"
        )
        ptx_path.write_text(injected)
        rejected = subprocess.run(
            [str(AUDIT), str(ptx_path), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["unexpected_instructions"], ["fma.rn.f64"])

    def test_audit_rejects_same_line_directives_and_extra_entry(self) -> None:
        temporary, ptx_path, generated = self.generate(sample_batch())
        self.addCleanup(temporary.cleanup)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        original = ptx_path.read_text()
        report_path = ptx_path.with_suffix(".audit.json")
        mutations = (
            original.replace("\tret;", "\tret; fma.rn.f64 %fd0, %fd0, %fd0, %fd0;"),
            original.replace(".address_size 64", ".address_size 64\n.section .evil"),
            original.replace(
                ".visible .entry sparkinterval_generated(",
                ".visible .entry evil()\n.visible .entry sparkinterval_generated(",
            ),
        )
        for mutation in mutations:
            ptx_path.write_text(mutation)
            completed = subprocess.run(
                [str(AUDIT), str(ptx_path), str(report_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(json.loads(report_path.read_text())["passed"])

    def test_audit_requires_exact_header_and_register_declarations(self) -> None:
        temporary, ptx_path, generated = self.generate(sample_batch())
        self.addCleanup(temporary.cleanup)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        original = ptx_path.read_text()
        report_path = ptx_path.with_suffix(".audit.json")
        pred = "\t.reg .pred %p<9>;"
        mutations = (
            original.replace(".version 9.0\n", ""),
            original.replace(".version 9.0\n", ".version 9.0\n.version 9.0\n"),
            original.replace(".address_size 64\n", ""),
            original.replace(".address_size 64\n", ".address_size 64\n.address_size 64\n"),
            original.replace(pred + "\n", ""),
            original.replace(pred, pred + "\n" + pred),
            original.replace(pred, "\t.reg .pred %fd<9>;"),
        )
        for mutation in mutations:
            ptx_path.write_text(mutation)
            completed = subprocess.run(
                [str(AUDIT), str(ptx_path), str(report_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(json.loads(report_path.read_text())["passed"])

    def test_rejects_operation_outside_polynomial_slice(self) -> None:
        batch = sample_batch()
        batch["expression"] = {
            "op": "div",
            "left": {"op": "var", "index": 0},
            "right": {"op": "var", "index": 1},
        }
        temporary, output_path, completed = self.generate(batch)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(completed.returncode, 3)
        self.assertIn("outside the Phase 5 polynomial allowlist", completed.stderr)
        self.assertFalse(output_path.exists())

    def test_rejects_noncanonical_json(self) -> None:
        temporary, output_path, completed = self.generate(
            sample_batch(), canonical=False
        )
        self.addCleanup(temporary.cleanup)
        self.assertEqual(completed.returncode, 3)
        self.assertIn("not canonical JSON", completed.stderr)
        self.assertFalse(output_path.exists())

    def test_rejects_oversized_sparse_file_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "oversized.json"
            output_path = root / "kernel.ptx"
            with input_path.open("wb") as output:
                output.truncate(wire.MAX_CANONICAL_JSON_BYTES + 1)
            completed = subprocess.run(
                [
                    str(MEMORY_RUNNER),
                    str(GENERATOR),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("input exceeds", completed.stderr)
            self.assertFalse(output_path.exists())

    def test_rejects_exact_field_and_phase5_limit_violations(self) -> None:
        extra = sample_batch()
        extra["unexpected"] = 0
        temporary, _, completed = self.generate(extra)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(completed.returncode, 3)
        self.assertIn("wrong fields", completed.stderr)

        too_many = sample_batch()
        too_many["variable_count"] = 65
        too_many["rows"] = [
            [
                {"lo": "0000000000000000", "hi": "0000000000000000"}
                for _ in range(65)
            ]
        ]
        temporary, _, completed = self.generate(too_many)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(completed.returncode, 3)
        self.assertIn("variable_count exceeds", completed.stderr)

    def test_demand_model_matches_ptxas_across_polynomial_shapes(self) -> None:
        ptxas = shutil.which("ptxas")
        nvdisasm = shutil.which("nvdisasm")
        if ptxas is None or nvdisasm is None:
            self.skipTest("ptxas and nvdisasm are required")

        var = lambda index: {"op": "var", "index": index}
        add = lambda left, right: {"op": "add", "left": left, "right": right}
        mul = lambda left, right: {"op": "mul", "left": left, "right": right}
        power = lambda arg, exponent: {
            "op": "pow_nat",
            "arg": arg,
            "exponent": exponent,
        }
        one = {
            "op": "const",
            "value": {"lo": "3ff0000000000000", "hi": "3ff0000000000000"},
        }
        cases = {
            "const": (
                one,
                {"LDG.E.64": 0, "LDG.E": 0, "STG.E.64": 2, "DMUL.RM": 0},
            ),
            "var": (
                var(0),
                {"LDG.E.64": 2, "LDG.E": 0, "STG.E.64": 2, "DMUL.RM": 0},
            ),
            "neg": (
                {"op": "neg", "arg": var(0)},
                {"LDG.E.64": 2, "LDG.E": 0, "STG.E.64": 2, "DMUL.RM": 0},
            ),
            "add_same": (
                add(var(0), var(0)),
                {
                    "LDG.E.64": 2,
                    "LDG.E": 0,
                    "STG.E.64": 4,
                    "DADD.RM": 1,
                },
            ),
            "add_constants": (
                add(
                    one,
                    {
                        "op": "const",
                        "value": {
                            "lo": "4000000000000000",
                            "hi": "4000000000000000",
                        },
                    },
                ),
                {
                    "LDG.E.64": 0,
                    "LDG.E": 0,
                    "STG.E.64": 2,
                    "DADD.RM": 1,
                },
            ),
            "mul_constants": (
                mul(
                    one,
                    {
                        "op": "const",
                        "value": {
                            "lo": "4000000000000000",
                            "hi": "4000000000000000",
                        },
                    },
                ),
                {
                    "LDG.E.64": 0,
                    "LDG.E": 0,
                    "STG.E.64": 2,
                    "DMUL.RM": 1,
                    "DSETP.MIN.AND": 0,
                    "FSEL": 0,
                },
            ),
            "pow_zero_var": (
                power(var(0), 0),
                {"LDG.E.64": 0, "LDG.E": 0, "STG.E.64": 2, "DMUL.RM": 0},
            ),
            "pow_zero_add": (
                power(add(var(0), var(1)), 0),
                {
                    "LDG.E.64": 0,
                    "LDG.E": 4,
                    "STG.E.64": 4,
                    "DADD.RM": 0,
                },
            ),
            "pow_one": (
                power(var(0), 1),
                {
                    "LDG.E.64": 2,
                    "DMUL.RM": 2,
                    "DSETP.MIN.AND": 1,
                    "FSEL": 2,
                },
            ),
            "two_pow_one": (
                add(power(var(0), 1), power(var(1), 1)),
                {
                    "LDG.E.64": 4,
                    "DMUL.RM": 4,
                    "DSETP.MIN.AND": 2,
                    "FSEL": 4,
                },
            ),
            "repeated_mul": (
                add(mul(var(0), var(1)), mul(var(0), var(1))),
                {
                    "LDG.E.64": 4,
                    "DMUL.RM": 4,
                    "DSETP.MIN.AND": 3,
                    "FSEL": 6,
                },
            ),
        }

        for name, (expression, expected_subset) in cases.items():
            with self.subTest(name=name):
                batch = sample_batch()
                batch["expression"] = expression
                temporary, ptx_path, generated = self.generate(batch)
                self.addCleanup(temporary.cleanup)
                self.assertEqual(generated.returncode, 0, generated.stderr)
                ptx_audit_path = ptx_path.with_suffix(".audit.json")
                audited = subprocess.run(
                    [str(AUDIT), str(ptx_path), str(ptx_audit_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(audited.returncode, 0, audited.stderr)
                ptx_report = json.loads(ptx_audit_path.read_text())
                modeled = ptx_report["lowering_model"]["expected_sass_counts"]
                for mnemonic, expected_count in expected_subset.items():
                    self.assertEqual(modeled[mnemonic], expected_count)

                cubin = ptx_path.with_suffix(".cubin")
                assembled = subprocess.run(
                    [ptxas, "-arch=sm_121", str(ptx_path), "-o", str(cubin)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(assembled.returncode, 0, assembled.stderr)
                sass_path = ptx_path.with_suffix(".sass.txt")
                disassembled = subprocess.run(
                    [nvdisasm, str(cubin)], capture_output=True, check=False
                )
                self.assertEqual(disassembled.returncode, 0, disassembled.stderr)
                sass_path.write_bytes(disassembled.stdout)
                sass_audit_path = ptx_path.with_suffix(".sass-audit.json")
                sass_audited = subprocess.run(
                    [
                        str(ROOT / "tools/inspect_generated_sass.py"),
                        str(sass_path),
                        str(ptx_audit_path),
                        str(sass_audit_path),
                        "--cubin",
                        str(cubin),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(sass_audited.returncode, 0, sass_audited.stderr)
                self.assertTrue(json.loads(sass_audit_path.read_text())["passed"])

    def test_demand_model_rejects_undefined_f64_dataflow(self) -> None:
        temporary, ptx_path, generated = self.generate(sample_batch())
        self.addCleanup(temporary.cleanup)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        original = ptx_path.read_text()
        ptx_path.write_text(
            original.replace(
                "ld.global.b64 %fd0, [%rd9+0];",
                "ld.global.b64 %fd999, [%rd9+0];",
                1,
            )
        )
        report_path = ptx_path.with_suffix(".audit.json")
        completed = subprocess.run(
            [str(AUDIT), str(ptx_path), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        report = json.loads(report_path.read_text())
        self.assertFalse(report["lowering_model"]["passed"])
        self.assertTrue(
            any("used without" in error for error in report["lowering_model"]["errors"])
        )

    def test_accepts_polynomial_boundary_shapes(self) -> None:
        zero = {"lo": "0000000000000000", "hi": "0000000000000000"}
        cases = []

        constant_only = sample_batch()
        constant_only["variable_count"] = 0
        constant_only["expression"] = {
            "op": "const",
            "value": {"lo": "3ff0000000000000", "hi": "3ff0000000000000"},
        }
        constant_only["rows"] = [[]]
        cases.append(constant_only)

        maximum_variable = sample_batch()
        maximum_variable["variable_count"] = 64
        maximum_variable["expression"] = {"op": "var", "index": 63}
        maximum_variable["rows"] = [[dict(zero) for _ in range(64)]]
        cases.append(maximum_variable)

        for exponent in (0, 1, 64):
            power = sample_batch()
            power["variable_count"] = 1
            power["expression"] = {
                "op": "pow_nat",
                "arg": {"op": "var", "index": 0},
                "exponent": exponent,
            }
            power["rows"] = [[dict(zero)]]
            cases.append(power)

        for batch in cases:
            temporary, ptx_path, completed = self.generate(batch)
            self.addCleanup(temporary.cleanup)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            audit_path = ptx_path.with_suffix(".audit.json")
            audited = subprocess.run(
                [str(AUDIT), str(ptx_path), str(audit_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(audited.returncode, 0, audited.stderr)
            self.assertTrue(json.loads(audit_path.read_text())["passed"])

    def test_rejects_expression_resource_boundaries(self) -> None:
        invalid_cases: list[tuple[dict, str]] = []

        bad_index = sample_batch()
        bad_index["expression"] = {"op": "var", "index": 2}
        invalid_cases.append((bad_index, "variable index 2 is outside variable_count 2"))

        bad_power = sample_batch()
        bad_power["expression"] = {
            "op": "pow_nat",
            "arg": {"op": "var", "index": 0},
            "exponent": 65,
        }
        invalid_cases.append((bad_power, "pow_nat exponent exceeds 64"))

        too_deep = sample_batch()
        deep_expression: dict = {"op": "var", "index": 0}
        for _ in range(65):
            deep_expression = {"op": "neg", "arg": deep_expression}
        too_deep["expression"] = deep_expression
        invalid_cases.append((too_deep, "expression exceeds the Phase 5 depth limit 64"))

        too_many_nodes = sample_batch()
        leaves: list[dict] = [
            {"op": "const", "value": {"lo": "0000000000000000", "hi": "0000000000000000"}}
            for _ in range(129)
        ]
        while len(leaves) > 1:
            next_level: list[dict] = []
            for index in range(0, len(leaves), 2):
                if index + 1 == len(leaves):
                    next_level.append(leaves[index])
                else:
                    next_level.append(
                        {"op": "add", "left": leaves[index], "right": leaves[index + 1]}
                    )
            leaves = next_level
        too_many_nodes["expression"] = leaves[0]
        invalid_cases.append((too_many_nodes, "expression exceeds the Phase 5 node limit 256"))

        for batch, message in invalid_cases:
            temporary, output_path, completed = self.generate(batch)
            self.addCleanup(temporary.cleanup)
            self.assertEqual(completed.returncode, 3)
            self.assertIn(message, completed.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()

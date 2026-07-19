#!/usr/bin/env python3

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "inspect_probe_ptx.py"


def program(extra: str = "") -> str:
    operations = "\n".join(
        f"  {op} %fd1, %fd2, %fd3;"
        for op in (
            "add.rm.f64", "add.rp.f64", "sub.rm.f64", "sub.rp.f64",
            "mul.rm.f64", "mul.rp.f64", "div.rm.f64", "div.rp.f64",
        )
    )
    return (
        ".version 9.0\n.target sm_90\n.address_size 64\n"
        ".visible .entry probe()\n{\n"
        f"{operations}\n{extra}\n  ret;\n}}\n"
    )


class PtxInspectionTest(unittest.TestCase):
    def inspect(self, source: str):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "probe.ptx"
            output_path = Path(directory) / "report.json"
            input_path.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                [str(TOOL), str(input_path), str(output_path), "--target", "sm_90"],
                capture_output=True,
                text=True,
                check=False,
            )
            return completed, json.loads(output_path.read_text(encoding="utf-8"))

    def test_accepts_exact_probe_rounding_set(self):
        completed, report = self.inspect(program())
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(report["passed"])

    def test_rejects_fused_instruction(self):
        completed, report = self.inspect(program("  fma.rn.f64 %fd1, %fd2, %fd3, %fd4;"))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["unexpected_instructions"], ["fma.rn.f64"])

    def test_rejects_missing_rounding_direction(self):
        source = program().replace("  div.rp.f64 %fd1, %fd2, %fd3;\n", "")
        completed, report = self.inspect(source)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["incorrect_required_counts"], {"div.rp.f64": 0})


if __name__ == "__main__":
    unittest.main()

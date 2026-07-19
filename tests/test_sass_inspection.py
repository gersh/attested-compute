#!/usr/bin/env python3

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "inspect_sass.py"


class SassInspectionTest(unittest.TestCase):
    def run_inspector(self, body: str, *options: str):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.sass"
            output_path = Path(directory) / "report.json"
            input_path.write_text(body, encoding="utf-8")
            completed = subprocess.run(
                [str(TOOL), str(input_path), str(output_path), *options],
                text=True,
                capture_output=True,
                check=False,
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            return completed, report

    def test_accepts_simple_f64_program(self):
        completed, report = self.run_inspector(
            ".target sm_121\nFunction : kernel\n"
            "/*0000*/ DADD.RM R2, R4, R6 ; /* encoding */\n"
            "/*0010*/ EXIT ; /* encoding */\n"
        )
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["targets"], ["sm_121"])

    def test_rejects_tensor_instruction(self):
        completed, report = self.run_inspector(
            ".target sm_121\nFunction : kernel\n"
            "/*0000*/ HMMA.1688.F32 R0, R2, R4, R6 ; /* encoding */\n"
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["findings"]["tensor_instructions"], ["HMMA.1688.F32"]
        )

    def test_division_lowering_requires_explicit_policy(self):
        body = (
            ".target sm_121\nFunction : kernel\n"
            "/*0000*/ MUFU.RCP64H R3, R9 ; /* encoding */\n"
            "/*0010*/ DFMA.RM R2, R4, R6, R8 ; /* encoding */\n"
        )
        rejected, _ = self.run_inspector(body)
        accepted, report = self.run_inspector(body, "--allow-division-lowering")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(accepted.returncode, 0)
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()

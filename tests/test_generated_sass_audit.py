#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "inspect_generated_sass.py"


def ptx_audit(
    modeled: dict[str, int] | None = None, *, target: str = "sm_121"
) -> dict:
    expected_sass_counts = {
        "DADD.RM": 2,
        "DADD.RP": 2,
        "DMUL.RM": 4,
        "DMUL.RP": 4,
        "DSETP.MIN.AND": 3,
        "DSETP.MAX.AND": 3,
        "FSEL": 6,
        "SEL": 6,
        "LDG.E.64": 2,
        "LDG.E": 0,
        "STG.E.64": 2,
        "STG.E.U8": 8,
    }
    if modeled is not None:
        expected_sass_counts.update(modeled)
    return {
        "passed": True,
        "target": target,
        "input_sha256": "0" * 64,
        "instruction_counts": {
            "add.rm.f64": 1,
            "add.rp.f64": 1,
            "sub.rm.f64": 1,
            "sub.rp.f64": 1,
            "mul.rm.f64": 4,
            "mul.rp.f64": 4,
            "min.f64": 3,
            "max.f64": 3,
            "ld.global.b64": 2,
            "st.global.b64": 2,
            "st.global.u8": 8,
        },
        "lowering_model": {
            "schema_version": 1,
            "analysis_kind": "generated_ptx_demand_and_value_numbering_v1",
            "passed": True,
            "errors": [],
            "expected_sass_counts": expected_sass_counts,
        },
    }


def sass(
    extra: str = "",
    *,
    target: str = "sm_121",
    down_mul: int = 4,
    up_mul: int = 4,
) -> str:
    lines = [f".target {target}", ".global sparkinterval_generated"]
    offset = 0
    for mnemonic, count in (
        ("DADD.RM", 2),
        ("DADD.RP", 2),
        ("DMUL.RM", down_mul),
        ("DMUL.RP", up_mul),
    ):
        for _ in range(count):
            lines.append(f"/*{offset:04x}*/ {mnemonic} R2, R4, R6 ;")
            offset += 0x10
    lines.append(f"/*{offset:04x}*/ HFMA2 R3, -RZ, RZ, 0, 0 ;")
    offset += 0x10
    bssy = "BSSY" if target == "sm_90" else "BSSY.RECONVERGENT"
    bsync = "BSYNC" if target == "sm_90" else "BSYNC.RECONVERGENT"
    lines.append(f"/*{offset:04x}*/ {bssy} B0, 0x100 ;")
    offset += 0x10
    lines.append(f"/*{offset:04x}*/ {bsync} B0 ;")
    for mnemonic in ("DSETP.MIN.AND", "DSETP.MAX.AND"):
        for _ in range(3):
            offset += 0x10
            lines.append(f"/*{offset:04x}*/ {mnemonic} P0, P1, R2, R4, PT ;")
    for mnemonic in ("FSEL", "SEL"):
        for _ in range(6):
            offset += 0x10
            lines.append(f"/*{offset:04x}*/ {mnemonic} R2, R4, R6, P0 ;")
    for mnemonic, count in (("LDG.E.64", 2), ("STG.E.64", 2), ("STG.E.U8", 8)):
        for _ in range(count):
            offset += 0x10
            lines.append(f"/*{offset:04x}*/ {mnemonic} R2, [R4] ;")
    if extra:
        offset += 0x10
        lines.append(f"/*{offset:04x}*/ {extra}")
    return "\n".join(lines) + "\n"


class GeneratedSassAuditTest(unittest.TestCase):
    def audit(
        self,
        source: str,
        *,
        modeled: dict[str, int] | None = None,
        target: str = "sm_121",
    ):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        sass_path = directory / "kernel.sass.txt"
        ptx_path = directory / "ptx-audit.json"
        report_path = directory / "report.json"
        sass_path.write_text(source)
        ptx_path.write_text(json.dumps(ptx_audit(modeled, target=target)))
        completed = subprocess.run(
            [str(TOOL), str(sass_path), str(ptx_path), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed, json.loads(report_path.read_text())

    def test_accepts_exact_binding_and_constant_forming_hfma2(self) -> None:
        completed, report = self.audit(sass())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["constant_forming_hfma2"]["unsafe"], 0)
        self.assertEqual(report["compiler_reconvergence_controls"], {
            "BSSY.RECONVERGENT": 1,
            "BSYNC.RECONVERGENT": 1,
        })
        self.assertEqual(report["mnemonic_counts"]["LDG.E.64"], 2)
        self.assertEqual(
            report["actual_corner_selection_counts"],
            {"DSETP.MAX.AND": 3, "DSETP.MIN.AND": 3},
        )

    def test_accepts_h100_target_binding_and_rejects_cross_target_sass(self) -> None:
        completed, report = self.audit(sass(target="sm_90"), target="sm_90")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(report["target"], "sm_90")
        self.assertTrue(report["target_binding_valid"])
        completed, report = self.audit(sass(target="sm_90"), target="sm_121")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["targets"], ["sm_90"])

    def test_requires_exact_value_numbered_directed_counts(self) -> None:
        completed, report = self.audit(
            sass(down_mul=2, up_mul=2),
            modeled={"DMUL.RM": 2, "DMUL.RP": 2},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            report["balanced_duplicate_dmul_sites_eliminated_by_ptxas"],
            {"DMUL.RM": 2, "DMUL.RP": 2},
        )
        completed, report = self.audit(sass(down_mul=2, up_mul=2))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_directed_counts"]["DMUL.RM"],
            {"actual": 2, "expected": 4},
        )
        completed, report = self.audit(
            sass(down_mul=2, up_mul=3),
            modeled={"DMUL.RM": 2, "DMUL.RP": 2},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_directed_counts"]["DMUL.RP"],
            {"actual": 3, "expected": 2},
        )

    def test_rejects_fused_double_arithmetic(self) -> None:
        completed, report = self.audit(
            sass("DFMA R2, R4, R6, R8 ;")
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["forbidden_instructions"], ["DFMA"])

    def test_rejects_data_dependent_hfma2(self) -> None:
        completed, report = self.audit(
            sass("HFMA2 R3, R4, R6, 0, 0 ;")
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["constant_forming_hfma2"]["unsafe"], 1)

    def test_rejects_unbalanced_reconvergence_and_changed_memory_sites(self) -> None:
        completed, report = self.audit(
            sass("BSSY.RECONVERGENT B1, 0x200 ;")
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(report["compiler_reconvergence_balanced"])
        completed, report = self.audit(sass("LDG.E.64 R8, [R10] ;"))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_global_memory_counts"]["LDG.E.64"],
            {"actual": 3, "expected": 2},
        )
        completed, report = self.audit(
            sass("DSETP.MIN.AND P2, P3, R8, R10, PT ;")
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_corner_selection"]["DSETP.MIN.AND"],
            {"actual": 4, "expected": 3},
        )

    def test_rejects_wrong_load_width_and_missing_lowering_model(self) -> None:
        changed_width = sass().replace("LDG.E.64", "LDG.E", 1)
        completed, report = self.audit(changed_width)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_global_memory_counts"]["LDG.E.64"],
            {"actual": 1, "expected": 2},
        )
        self.assertEqual(
            report["incorrect_global_memory_counts"]["LDG.E"],
            {"actual": 1, "expected": 0},
        )

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        sass_path = directory / "kernel.sass.txt"
        ptx_path = directory / "ptx-audit.json"
        report_path = directory / "report.json"
        sass_path.write_text(sass())
        audit = ptx_audit()
        del audit["lowering_model"]
        ptx_path.write_text(json.dumps(audit))
        completed = subprocess.run(
            [str(TOOL), str(sass_path), str(ptx_path), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(json.loads(report_path.read_text())["lowering_model_valid"])

    def test_rejects_changed_store_and_selector_counts(self) -> None:
        missing_store = sass().replace("STG.E.64", "NOP", 1)
        completed, report = self.audit(missing_store)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_global_memory_counts"]["STG.E.64"],
            {"actual": 1, "expected": 2},
        )

        missing_selector = sass().replace("FSEL", "MOV", 1)
        completed, report = self.audit(missing_selector)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(
            report["incorrect_corner_selection"]["corner selectors"],
            {
                "actual_sass": {"FSEL": 5, "SEL": 6},
                "expected": {"FSEL": 6, "SEL": 6},
            },
        )


if __name__ == "__main__":
    unittest.main()

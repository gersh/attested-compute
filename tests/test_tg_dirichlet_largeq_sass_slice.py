#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "audit_tg_dirichlet_largeq_sass_slice.py"
SOURCE_FILE = "gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu"


def source_text() -> str:
    lines = [f"// filler {index}" for index in range(1, 161)]
    lines[53] = (
        "  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};"
    )
    lines[87] = "  return {add(x.re, y.re), add(x.im, y.im)};"
    lines[157] = "    output[flat] = cadd(cmul(factor, zeta), recovery);"
    return "\n".join(lines) + "\n"


def function_header() -> str:
    return (
        "//--------------------- .text._example_reconstructComposeKernel "
        "--------------------------\n"
    )


def plain_sass(*, upper: str = "DADD.RP R10, R10, R20") -> str:
    return (
        "\t.target\tsm_90\n\n"
        + function_header()
        + "        /*3830*/ UIADD3 UR4, UR7, UR4, URZ ;\n"
        + "        /*3840*/ DADD.RM R12, R12, R22 ;\n"
        + f"        /*3850*/ {upper} ;\n"
        + "        /*3860*/ STG.E.64 desc[UR8][R18.64], R12 ;\n"
    )


def line_sass(*, call_line: int = 88, upper: str = "DADD.RP R10, R10, R20") -> str:
    path = f"/checkout/{SOURCE_FILE}"
    return (
        "\t.target\tsm_90\n\n"
        + function_header()
        + f'\t//## File "{path}", line 54 inlined at "{path}", line {call_line}\n'
        + f'\t//## File "{path}", line {call_line} inlined at "{path}", line 158\n'
        + f'\t//## File "{path}", line 158\n'
        + "        /*3840*/ DADD.RM R12, R12, R22 ;\n"
        + f"        /*3850*/ {upper} ;\n"
        + "        /*3860*/ STG.E.64 desc[UR8][R18.64], R12 ;\n"
    )


class LargeQSassSliceAuditTest(unittest.TestCase):
    def run_tool(
        self,
        *,
        cubin: bytes = b"\x7fELFsynthetic",
        plain: str | None = None,
        line_info: str | None = None,
        source: str | None = None,
    ):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        cubin_path = directory / "kernel.cubin"
        sass_path = directory / "kernel.sass"
        line_path = directory / "kernel.line.sass"
        source_path = directory / "kernel.cu"
        output_path = directory / "certificate.json"
        cubin_path.write_bytes(cubin)
        sass_path.write_text(plain if plain is not None else plain_sass())
        line_path.write_text(line_info if line_info is not None else line_sass())
        source_path.write_text(source if source is not None else source_text())
        completed = subprocess.run(
            [
                "python3",
                str(TOOL),
                str(cubin_path),
                str(sass_path),
                str(line_path),
                str(source_path),
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(output_path.read_text()) if output_path.exists() else None
        return completed, report

    def test_extracts_operand_level_restricted_ir(self) -> None:
        completed, report = self.run_tool()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["target"], "sm_90")
        self.assertEqual(
            report["canonical_excerpt"],
            "/*3840*/ DADD.RM R12, R12, R22 ;\n"
            "/*3850*/ DADD.RP R10, R10, R20 ;\n",
        )
        self.assertEqual(
            report["restricted_ir"]["result"], {"lo": 12, "hi": 10}
        )
        self.assertEqual(
            report["restricted_ir"]["right"], {"lo": 22, "hi": 20}
        )

    def test_rejects_changed_operand_between_disassemblies(self) -> None:
        completed, _ = self.run_tool(
            plain=plain_sass(upper="DADD.RP R10, R10, R24")
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("disagree", completed.stderr)

    def test_rejects_wrong_source_stack_or_rounding(self) -> None:
        completed, _ = self.run_tool(line_info=line_sass(call_line=89))
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("found 0", completed.stderr)

        completed, _ = self.run_tool(
            plain=plain_sass(upper="DADD.RM R10, R10, R20"),
            line_info=line_sass(upper="DADD.RM R10, R10, R20"),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("found 0", completed.stderr)

    def test_rejects_non_elf_or_non_sm90(self) -> None:
        completed, _ = self.run_tool(cubin=b"not-elf")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not an ELF", completed.stderr)

        completed, _ = self.run_tool(
            plain=plain_sass().replace("sm_90", "sm_89"),
            line_info=line_sass().replace("sm_90", "sm_89"),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("sm_90", completed.stderr)


if __name__ == "__main__":
    unittest.main()

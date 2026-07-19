from __future__ import annotations

import unittest

from tools import inspect_expression_ptx as audit


def sample_ptx(*, target: str = "sm_121", extra: tuple[str, ...] = ()) -> bytes:
    instructions: list[str] = []
    for name, count in audit.EXPECTED_DIRECTED_COUNTS.items():
        instructions.extend(f"  {name} %fd1, %fd2, %fd3;" for _ in range(count))
    instructions.extend(f"  {instruction};" for instruction in extra)
    return (
        ".version 9.0\n"
        f".target {target}\n"
        ".address_size 64\n"
        ".entry expression_batch_kernel()\n"
        "{\n"
        ".local .align 16 .b8 stack[512];\n"
        + "\n".join(instructions)
        + "\n  ret;\n}\n"
    ).encode("ascii")


class ExpressionPtxAuditTests(unittest.TestCase):
    def test_accepts_exact_directed_sites_and_sm121(self) -> None:
        report = audit.audit_ptx(sample_ptx())
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["required_directed_rounding_counts"],
            audit.EXPECTED_DIRECTED_COUNTS,
        )

    def test_rejects_wrong_target_and_changed_site_count(self) -> None:
        wrong_target = audit.audit_ptx(sample_ptx(target="sm_90"))
        self.assertFalse(wrong_target["passed"])
        missing = sample_ptx().replace(b"add.rm.f64", b"add.rn.f64", 1)
        report = audit.audit_ptx(missing)
        self.assertFalse(report["passed"])
        self.assertIn("add.rm.f64", report["incorrect_directed_rounding_counts"])
        self.assertIn("add.rn.f64", report["unexpected_floating_instructions"])

    def test_rejects_fused_approximate_and_coordination_instructions(self) -> None:
        report = audit.audit_ptx(
            sample_ptx(
                extra=(
                    "fma.rn.f64 %fd1, %fd2, %fd3, %fd4",
                    "rcp.approx.f64 %fd1, %fd2",
                    "bar.sync 0",
                )
            )
        )
        self.assertFalse(report["passed"])
        self.assertIn("fma.rn.f64", report["unexpected_floating_instructions"])
        self.assertIn("rcp.approx.f64", report["forbidden_math_instructions"])
        self.assertIn("bar.sync", report["forbidden_coordination_instructions"])

    def test_rejects_shared_memory_and_wrong_fixed_stack(self) -> None:
        shared = sample_ptx().replace(
            b".local .align 16 .b8 stack[512];",
            b".shared .align 16 .b8 stack[512];",
        )
        report = audit.audit_ptx(shared)
        self.assertFalse(report["passed"])
        self.assertEqual(report["shared_declaration_count"], 1)
        self.assertEqual(report["local_stack_bytes"], [])


if __name__ == "__main__":
    unittest.main()

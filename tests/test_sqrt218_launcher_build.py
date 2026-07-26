# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

from tg_verifier.campaign_io import canonical_json_bytes, sha256_bytes
from tg_verifier import sqrt218_launcher_build as launcher_build


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "launcher_build/sqrt218/cloud-launcher-build.v1.json"
)
SCHEMA_PATH = (
    ROOT / "schemas/sqrt218-cloud-launcher-build.schema.json"
)
TOOL_PATH = ROOT / "tools/tg_sqrt218_launcher_build.py"
RUNNER_PATH = (
    ROOT / "launcher_build/sqrt218/run_cloud_launcher_build.sh"
)
C_PATH = (
    ROOT / "launcher_build/sqrt218/sqrt218_pure_entry_launcher.c"
)
ASM_PATH = (
    ROOT / "launcher_build/sqrt218/sqrt218_pure_entry_trampoline.S"
)


def manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text())


def reseal(value: dict[str, object]) -> None:
    body = {
        key: item for key, item in value.items()
        if key != "manifest_sha256"
    }
    value["manifest_sha256"] = sha256_bytes(canonical_json_bytes(body))


class Sqrt218LauncherBuildTests(unittest.TestCase):
    def test_manifest_and_exact_source_closure_are_valid(self) -> None:
        checked = launcher_build.load_manifest(MANIFEST_PATH)
        launcher_build.validate_inputs(
            checked, ROOT, require_build_ready=True
        )
        summary = launcher_build.review_summary(checked)
        self.assertTrue(summary["build_ready"])
        self.assertFalse(summary["executes_launcher"])
        self.assertFalse(summary["opens_production_input"])
        self.assertFalse(summary["production_execution_ready"])
        self.assertFalse(summary["formal_refinement_ready"])
        self.assertFalse(summary["authorizes_lean_theorem"])
        self.assertEqual(summary["source_file_count"], 11)

    def test_authority_execution_and_source_tampering_fail_closed(self) -> None:
        cases: list[tuple[str, tuple[str, ...], object, str]] = [
            (
                "authority",
                ("authority", "authorizes_lean_theorem"),
                True,
                "authority",
            ),
            (
                "execute launcher",
                ("build", "executes_launcher"),
                True,
                "command boundary",
            ),
            (
                "open input",
                ("build", "opens_production_input"),
                True,
                "command boundary",
            ),
            (
                "production ready",
                ("status", "production_execution_ready"),
                True,
                "status",
            ),
            (
                "mutable base",
                ("container", "base_image"),
                "docker.io/rocq/rocq-prover:latest",
                "container boundary",
            ),
        ]
        for label, path, replacement, error in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(manifest())
                cursor: object = changed
                for key in path[:-1]:
                    cursor = cursor[key]  # type: ignore[index]
                cursor[path[-1]] = replacement  # type: ignore[index]
                reseal(changed)
                with self.assertRaisesRegex(
                    launcher_build.LauncherBuildError, error
                ):
                    launcher_build.validate_manifest(changed)

        changed = copy.deepcopy(manifest())
        changed["source_inputs"][0]["sha256"] = "1" * 64  # type: ignore[index]
        changed["container"]["dockerfile"]["sha256"] = "1" * 64  # type: ignore[index]
        reseal(changed)
        checked = launcher_build.validate_manifest(changed)
        with self.assertRaisesRegex(
            launcher_build.LauncherBuildError, "SHA-256"
        ):
            launcher_build.validate_inputs(checked, ROOT)

    def test_cli_is_metadata_and_source_only(self) -> None:
        shown = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "show-plan",
                str(MANIFEST_PATH),
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr.decode())
        plan = json.loads(shown.stdout)
        self.assertTrue(plan["status"]["build_ready"])
        self.assertFalse(plan["build"]["executes_launcher"])
        self.assertFalse(plan["authority"]["authorizes_lean_theorem"])
        self.assertTrue(
            plan["azure"]["repository_source_closure_baked_into_image"]
        )
        self.assertTrue(
            plan["azure"]["persistent_output_leaf_must_be_absent"]
        )
        self.assertEqual(
            plan["azure"]["persistent_output_mount"], "/workspace/export"
        )
        self.assertEqual(
            plan["azure"]["acr_pull_identity_resource_id"],
            "${ACI_IDENTITY_RESOURCE_ID}",
        )
        self.assertTrue(
            plan["azure"]["acr_pull_role_pregranted_required"]
        )
        aci_argv = plan["azure"]["aci_build_argv"]
        self.assertIn("--assign-identity", aci_argv)
        self.assertIn("--acr-identity", aci_argv)
        self.assertEqual(
            aci_argv[aci_argv.index("--assign-identity") + 1],
            "${ACI_IDENTITY_RESOURCE_ID}",
        )
        self.assertEqual(
            aci_argv[aci_argv.index("--acr-identity") + 1],
            "${ACI_IDENTITY_RESOURCE_ID}",
        )

        validated = subprocess.run(
            [
                sys.executable,
                str(TOOL_PATH),
                "validate",
                str(MANIFEST_PATH),
                "--repository-root",
                str(ROOT),
                "--require-build-ready",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(validated.returncode, 0, validated.stdout.decode())
        review = json.loads(validated.stdout)
        self.assertFalse(review["opens_production_input"])
        module = (
            ROOT / "tg_verifier/sqrt218_launcher_build.py"
        ).read_text()
        self.assertNotIn("import subprocess", module)
        self.assertNotIn("import ctypes", module)
        self.assertNotIn("import mmap", module)

    def test_launcher_source_contains_fail_closed_elf_and_snapshot_checks(
        self,
    ) -> None:
        source = C_PATH.read_text()
        for required in (
            "SYS_openat2",
            "RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS",
            "tg_stat_identity_equal",
            '"/proc/self/exe"',
            "PT_INTERP || type == PT_DYNAMIC || type == PT_TLS",
            "|| type == SHT_RELR",
            "snapshot->bytes[EI_OSABI] != ELFOSABI_SYSV",
            "snapshot->bytes[EI_ABIVERSION] != 0",
            "tg_load_le32(snapshot->bytes + 48U) != UINT32_C(0)",
            "for (ident_index = EI_PAD; ident_index < EI_NIDENT;",
            "snapshot->bytes + (size_t)section_offset",
            "(PF_W | PF_X)",
            "MAP_FIXED_NOREPLACE",
            "mapped != requested",
            "mprotect(mapped, map_bytes, protection)",
            "SHT_SYMTAB",
            '"tg_sq218_verify_snapshot_v2"',
            "value != loaded->entry",
            "return matches == 1U ? 0 : -1",
        ):
            self.assertIn(required, source)
        self.assertLess(
            source.index("tg_read_file_snapshot("),
            source.index("tg_validate_elf(&elf_snapshot"),
        )
        self.assertLess(
            source.index("tg_validate_elf(&elf_snapshot"),
            source.index("tg_map_elf(&elf_snapshot"),
        )

    def test_launcher_source_contains_isolation_observer_and_atomic_publish(
        self,
    ) -> None:
        source = C_PATH.read_text()
        assembly = ASM_PATH.read_text()
        for required in (
            "tg_require_measured_worker",
            "tg_prepare_child_signals",
            "sigprocmask(SIG_SETMASK",
            "SECCOMP_RET_KILL_PROCESS",
            "__NR_exit_group",
            "SYS_pidfd_open",
            "SIGKILL",
            "TG_RESULT_BYTES",
            "TG_STATUS_BYTES",
            "TG_CANARY",
            "post_return_rflags & TG_RFLAGS_DF",
            "tg_validate_result_record",
            "SYS_renameat2",
            "RENAME_NOREPLACE",
            '"result.bin"',
            '"transcript.txt"',
            "formal_launcher_refinement_present=false",
        ):
            self.assertIn(required, source)
        for required in (
            "leaq -8(%rsp), %rax",
            "andq $15, %rax",
            "call *%r13",
            "tg_sq218_return_sentinel:",
            "pushfq",
            "cld",
        ):
            self.assertIn(required, assembly)
        self.assertNotIn("movq $8, 32(%r10)", assembly)

    def test_cloud_runner_is_syntax_valid_and_never_executes_launcher(
        self,
    ) -> None:
        checked = subprocess.run(
            ["bash", "-n", str(RUNNER_PATH)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr.decode())
        runner = RUNNER_PATH.read_text()
        dockerfile = (
            ROOT / "launcher_build/sqrt218/Dockerfile"
        ).read_text()
        self.assertIn('TG_CLOUD_LAUNCHER_BUILD:-}" == "1"', runner)
        self.assertIn("gcc", runner)
        self.assertIn("readelf", runner)
        self.assertIn("objdump", runner)
        self.assertIn("artifact-index", runner)
        self.assertNotIn("run_step launcher", runner)
        self.assertNotIn("run_step execute", runner)
        self.assertNotIn("sqrt218-finite-certificate", runner)
        self.assertNotIn("production-certificate", runner)
        self.assertIn(
            "COPY launcher_build/sqrt218/cloud-launcher-build.v1.json",
            dockerfile,
        )
        self.assertIn(
            "/workspace/repository/launcher_build/sqrt218/"
            "sqrt218_pure_entry_launcher.c",
            dockerfile,
        )
        self.assertIn(
            "--azure-file-volume-mount-path",
            json.dumps(manifest()),
        )
        self.assertIn("--assign-identity", json.dumps(manifest()))
        self.assertIn("--acr-identity", json.dumps(manifest()))

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_json_schema_accepts_manifest_and_rejects_authority(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        value = manifest()
        validator.validate(value)

        value["authority"]["authorizes_lean_theorem"] = True  # type: ignore[index]
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(value)


if __name__ == "__main__":
    unittest.main()

# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = os.environ.get("TG_PLATT_PT21_BITREVERSE_TILE9_QUALIFICATION")
STRICT_EXECUTABLE = os.environ.get(
    "TG_PLATT_PT21_BITREVERSE_TILE9_H100_QUALIFICATION"
)
STREAM = os.environ.get("TG_PLATT_GAMMA_V2_BLOCK0_STREAM")
STREAM_SHA256 = (
    "d484eb1f0d382ffcf3683e18cd0c9570"
    "c5a215efaa595cb9bb677e3c2ebfbdbc"
)
QUALIFIER_PATH = ROOT / "tools/qualify_pt21_bitreverse_tile9.py"
QUALIFIER_SPEC = importlib.util.spec_from_file_location(
    "qualify_pt21_bitreverse_tile9", QUALIFIER_PATH
)
assert QUALIFIER_SPEC is not None and QUALIFIER_SPEC.loader is not None
QUALIFIER = importlib.util.module_from_spec(QUALIFIER_SPEC)
QUALIFIER_SPEC.loader.exec_module(QUALIFIER)
RESOURCE_INSPECTOR_PATH = (
    ROOT / "tools/inspect_pt21_bitreverse_tile9_sm90_resources.py"
)
RESOURCE_INSPECTOR_SPEC = importlib.util.spec_from_file_location(
    "inspect_pt21_bitreverse_tile9_sm90_resources",
    RESOURCE_INSPECTOR_PATH,
)
assert (
    RESOURCE_INSPECTOR_SPEC is not None
    and RESOURCE_INSPECTOR_SPEC.loader is not None
)
RESOURCE_INSPECTOR = importlib.util.module_from_spec(RESOURCE_INSPECTOR_SPEC)
RESOURCE_INSPECTOR_SPEC.loader.exec_module(RESOURCE_INSPECTOR)


def target_slice(cmake: str, target: str) -> str:
    target_position = cmake.index(target)
    begin = cmake.rfind("add_executable(", 0, target_position)
    if begin == -1:
        begin = cmake.rfind("add_library(", 0, target_position)
    if begin == -1:
        raise AssertionError(f"cannot find target declaration for {target}")
    next_executable = cmake.find("add_executable(", target_position + len(target))
    next_library = cmake.find("add_library(", target_position + len(target))
    ends = [value for value in (next_executable, next_library) if value != -1]
    return cmake[begin : min(ends) if ends else len(cmake)]


class PT21BitreverseTile9SourceTests(unittest.TestCase):
    def test_candidate_is_macro_guarded_and_fuses_exact_bitreverse_load(
        self,
    ) -> None:
        source = (
            ROOT
            / "gpu/platform/h100/"
            "h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text(encoding="utf-8")
        header = (
            ROOT / "gpu/include/sparkinterval/tg_platt_dd_transform.hpp"
        ).read_text(encoding="utf-8")
        guard = "SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION"
        self.assertGreaterEqual(source.count(guard), 3)
        self.assertGreaterEqual(header.count(guard), 2)
        kernel = (
            "dd_bit_reverse_and_radix2_stages_1_through_9_"
            "tile_sloppy_root_qualification"
        )
        self.assertIn(kernel, source)
        body = source[source.index(f"{kernel}(") :]
        body = body[: body.index("\n}\n") + 3]
        self.assertEqual(body.count("__brev("), 2)
        self.assertIn("input[line_base + first_reversed]", body)
        self.assertIn("input[line_base + second_reversed]", body)
        self.assertIn("dd_disk_input_well_formed(first_value)", body)
        self.assertIn("dd_disk_input_well_formed(second_value)", body)
        self.assertIn("atomicOr(input_failure_flags, input_failure_bit)", body)
        self.assertIn("dd_radix2_butterfly_sloppy_root_qualification(", body)
        self.assertIn("__syncthreads();", body)
        self.assertIn(
            "bitreverse_tile9_sloppy_root_kernel_resources_qualification",
            source,
        )
        self.assertIn("cudaFuncGetAttributes(", source)
        self.assertIn(kernel, source[source.index("cudaFuncGetAttributes(") :])
        self.assertIn("input == output", source)

    def test_separate_wrapper_reuses_hardened_live_differential_runner(
        self,
    ) -> None:
        wrapper = (
            ROOT
            / "reference/tg_platt_pt21_bitreverse_tile9_qualification.cu"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "#include \"tg_platt_pt21_live_transform_candidate_"
            "qualification.cu\"",
            wrapper,
        )
        self.assertIn(
            "run_source_window_bitreverse_tile9_sloppy_root_qualification",
            wrapper,
        )
        self.assertIn(
            "bitreverse_tile9_sloppy_root_kernel_resources_qualification",
            wrapper,
        )
        self.assertNotIn("write_containment_frames", wrapper)

    def test_portable_strict_and_production_targets_are_isolated(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        portable_archive_name = (
            "sparkinterval-tg-platt-dd-bitreverse-tile9-transform-"
            "qualification"
        )
        portable_archive = target_slice(cmake, portable_archive_name)
        self.assertIn(
            "SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION=1",
            portable_archive,
        )
        self.assertIn("--fmad=false", portable_archive)
        self.assertIn("--ftz=false", portable_archive)
        portable_name = (
            "sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification"
        )
        portable = target_slice(cmake, portable_name)
        self.assertIn(
            "reference/tg_platt_pt21_bitreverse_tile9_qualification.cu",
            portable,
        )
        self.assertIn(portable_archive_name, portable)

        strict_archive_name = (
            "sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-"
            "qualification"
        )
        strict_archive = target_slice(cmake, strict_archive_name)
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90=1", strict_archive)
        self.assertIn(
            f"sparkinterval_configure_h100_kernel(\n    {strict_archive_name}",
            strict_archive,
        )
        strict_name = (
            "sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification"
        )
        strict = target_slice(cmake, strict_name)
        self.assertIn("SPARKINTERVAL_REQUIRE_H100_SM90=1", strict)
        self.assertIn(strict_archive_name, strict)

        live = target_slice(
            cmake,
            "sparkinterval-tg-platt-pt21-live-transform-candidate-"
            "qualification",
        )
        production = target_slice(
            cmake, "sparkinterval-tg-platt-fused-source-worker-v2"
        )
        self.assertNotIn(
            "SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION", live
        )
        self.assertNotIn(
            "SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION",
            production,
        )

    def test_fail_closed_wrapper_checks_actual_resources_and_claims(
        self,
    ) -> None:
        wrapper = (
            ROOT / "tools/qualify_pt21_bitreverse_tile9.py"
        ).read_text(encoding="utf-8")
        for text in (
            "os.O_NOFOLLOW",
            "os.pread",
            "/proc/self/fd/",
            "pass_fds=",
            "candidate_semantic_gates_accepted",
            "tile_settled_all_sample_bytes_identical",
            "tile_settled_replay_artifact_identical",
            "exact_all_sample_containment",
            "required_sign_comparison",
            "local_bytes_per_thread",
            "static_shared_bytes",
            "active_blocks_per_multiprocessor",
            "performance_evidence_eligible",
            "runtime_instrumentation_status",
            "audited_source_snapshot",
            "binary_to_source_binding_proved",
            "build_flags_authenticated",
            "external_headers_authenticated",
            "nested_candidate_label_is_inherited_alias",
        ):
            self.assertIn(text, wrapper)

    def test_depfile_derived_repo_source_manifest_is_exact(self) -> None:
        identity = QUALIFIER.validate_repo_source_manifest()
        self.assertEqual(identity["file_count"], 17)
        self.assertTrue(identity["depfile_derived"])
        self.assertFalse(identity["external_build_dependencies_pinned"])
        self.assertFalse(identity["compiler_refinement_proved"])
        manifest = json.loads(
            (
                ROOT
                / "reference/manifests/"
                "pt21_bitreverse_tile9_repo_source_closure.v1.json"
            ).read_text()
        )
        paths = [entry["path"] for entry in manifest["files"]]
        for required in (
            "reference/tg_platt_pt21_bitreverse_tile9_qualification.cu",
            "reference/tg_platt_pt21_live_transform_candidate_qualification.cu",
            "gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu",
            "gpu/include/sparkinterval/tg_platt_dd_transform.hpp",
        ):
            self.assertIn(required, paths)

    def test_source_manifest_and_member_mutations_fail_closed(self) -> None:
        original_path = (
            ROOT
            / "reference/manifests/"
            "pt21_bitreverse_tile9_repo_source_closure.v1.json"
        )
        original = original_path.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            mutated_path = Path(directory) / "manifest.json"
            mutated_path.write_bytes(original + b"\n")
            with self.assertRaises(QUALIFIER.QualificationError):
                QUALIFIER.validate_repo_source_manifest(mutated_path)

            value = json.loads(original)
            value["files"][0]["sha256"] = "0" * 64
            member_mutation = json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode()
            mutated_path.write_bytes(member_mutation)
            with mock.patch.object(
                QUALIFIER,
                "EXPECTED_SOURCE_MANIFEST_SHA256",
                hashlib.sha256(member_mutation).hexdigest(),
            ):
                with self.assertRaises(QUALIFIER.QualificationError):
                    QUALIFIER.validate_repo_source_manifest(mutated_path)

    def test_strict_sm90_inspector_is_fail_closed(self) -> None:
        source = RESOURCE_INSPECTOR_PATH.read_text()
        for text in (
            "architectures != {\"sm_90\"}",
            "(registers, stack, shared, local) == (77, 0, 33792, 0)",
            "strict_resource_feasible",
            "registers_per_evaluated_block",
            "launch_geometry_extracted_from_binary",
            "cuobjdump_semantics_proved",
            "runtime_cuda_attributes_measured",
            "binary_to_source_binding_proved",
        ):
            self.assertIn(text, source)
        self.assertEqual(
            RESOURCE_INSPECTOR._parse_image_list(
                "ELF file    1: first.sm_90.cubin\n"
                "ELF file    2: second.sm_90.cubin\n",
                "ELF",
            ),
            ["first.sm_90.cubin", "second.sm_90.cubin"],
        )
        with self.assertRaises(RESOURCE_INSPECTOR.InspectionError):
            RESOURCE_INSPECTOR._parse_image_list(
                "PTX file    2: skipped-index.sm_90.ptx\n", "PTX"
            )


@unittest.skipUnless(
    EXECUTABLE and STREAM,
    "set the bitreverse qualifier and exact block-0 V2 stream",
)
class PT21BitreverseTile9RuntimeTests(unittest.TestCase):
    def invoke(self, *extra: str) -> subprocess.CompletedProcess[str]:
        assert EXECUTABLE is not None
        assert STREAM is not None
        executable = Path(EXECUTABLE)
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        return subprocess.run(
            [
                sys.executable,
                str(QUALIFIER_PATH),
                "--executable",
                str(executable),
                "--expected-executable-sha256",
                digest,
                "--stream",
                STREAM,
                "--repetitions",
                "3",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=ROOT,
        )

    def test_exact_live_candidate(self) -> None:
        completed = self.invoke()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertTrue(value["accepted"])
        self.assertEqual(
            value["candidate"], "pt21-bitreverse-tile9-sloppy-root"
        )
        self.assertEqual(value["nested_candidate_label"], "tile9-sloppy-root")
        self.assertTrue(value["nested_candidate_label_is_inherited_alias"])
        self.assertTrue(value["audited_source_snapshot_validated"])
        self.assertFalse(value["binary_to_source_binding_proved"])
        self.assertFalse(value["build_flags_authenticated"])
        self.assertFalse(value["external_headers_authenticated"])
        native = value["native_report"]
        self.assertTrue(native["candidate_qualified"])
        self.assertTrue(native["tile_settled_all_sample_bytes_identical"])
        self.assertTrue(native["tile_settled_replay_artifact_identical"])
        self.assertFalse(native["performance_evidence_eligible"])

    def test_forced_rejection_replays_ordinary_fallback(self) -> None:
        completed = self.invoke("--force-candidate-rejection-for-test")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        native = json.loads(completed.stdout)["native_report"]
        self.assertFalse(native["candidate_qualified"])
        self.assertTrue(native["fallback_exercised"])
        self.assertTrue(native["fallback_reproduced_ordinary"])


@unittest.skipUnless(
    STRICT_EXECUTABLE and STREAM,
    "set the strict bitreverse qualifier and exact block-0 V2 stream",
)
class PT21BitreverseTile9StrictRuntimeTests(unittest.TestCase):
    def test_strict_sm90_cubin_resource_identity(self) -> None:
        assert STRICT_EXECUTABLE is not None
        cuobjdump = shutil.which("cuobjdump")
        if cuobjdump is None:
            self.skipTest("cuobjdump is unavailable")
        executable = Path(STRICT_EXECUTABLE)
        tool = Path(cuobjdump)
        report = RESOURCE_INSPECTOR.inspect(
            executable,
            hashlib.sha256(executable.read_bytes()).hexdigest(),
            tool,
            hashlib.sha256(tool.read_bytes()).hexdigest(),
        )
        self.assertTrue(report["strict_resource_feasible"])
        self.assertEqual(report["registers_per_thread"], 77)
        self.assertEqual(report["stack_bytes"], 0)
        self.assertEqual(report["local_bytes"], 0)
        self.assertEqual(report["cuobjdump_shared_bytes"], 33792)
        self.assertEqual(report["evaluated_threads_per_block"], 256)
        self.assertEqual(report["registers_per_evaluated_block"], 19712)
        self.assertFalse(report["launch_geometry_extracted_from_binary"])
        self.assertEqual(report["resource_cubin_architecture"], "sm_90")
        self.assertEqual(
            report["embedded_cubin_images"][:2],
            RESOURCE_INSPECTOR.EXPECTED_CUBIN_IMAGES,
        )
        self.assertTrue(
            re.fullmatch(
                r"[0-9]+\.3\.sm_90\.cubin",
                report["embedded_cubin_images"][2],
            )
        )
        self.assertEqual(
            report["embedded_cubin_normalized_roster"][2],
            "<inherited-fd>.3.sm_90.cubin",
        )
        self.assertTrue(
            report["linked_archive_image_label_is_fd_basename_dependent"]
        )
        self.assertTrue(report["ptx_fallback_present"])
        self.assertEqual(
            report["ptx_fallback_images"],
            RESOURCE_INSPECTOR.EXPECTED_PTX_FALLBACK_IMAGES,
        )
        self.assertEqual(
            report["ptx_fallback_cuobjdump_target_labels"], ["sm_90"]
        )
        self.assertFalse(report["ptx_fallback_semantics_proved"])
        self.assertFalse(report["runtime_cuda_attributes_measured"])
        with self.assertRaises(RESOURCE_INSPECTOR.InspectionError):
            RESOURCE_INSPECTOR.inspect(
                executable,
                "0" * 64,
                tool,
                hashlib.sha256(tool.read_bytes()).hexdigest(),
            )

    def test_strict_sm90_binary_rejects_non_h100(self) -> None:
        assert STRICT_EXECUTABLE is not None
        assert STREAM is not None
        completed = subprocess.run(
            [
                STRICT_EXECUTABLE,
                STREAM,
                f"--expected-stream-sha256={STREAM_SHA256}",
                "--repetitions=1",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires NVIDIA H100 sm_90", completed.stderr)


if __name__ == "__main__":
    unittest.main()

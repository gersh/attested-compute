#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed cubin-resource inspection for the strict PT21 fused kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


SCHEMA = (
    "sparkinterval.tg.pt21-bitreverse-tile9-sm90-resource-inspection.v1"
)
KERNEL = (
    "dd_bit_reverse_and_radix2_stages_1_through_9_"
    "tile_sloppy_root_qualification"
)
RESOURCE_PATTERN = re.compile(
    r"^\s*REG:(\d+) STACK:(\d+) SHARED:(\d+) LOCAL:(\d+)(?:\s|$)"
)
EXPECTED_CUBIN_IMAGES = [
    "tg_platt_pt21_bitreverse_tile9_qualification.sm_90.cubin",
    "tg_platt_gamma_dd_gpu.sm_90.cubin",
]
EXPECTED_CUBIN_IMAGE_ROLES = [
    "qualification-runner",
    "gamma-synthesizer",
    "linked-archive-device-image-3",
]
EXPECTED_PTX_FALLBACK_IMAGES = [
    "tg_platt_pt21_bitreverse_tile9_qualification.sm_90.ptx",
    "tg_platt_gamma_dd_gpu.sm_90.ptx",
]


class InspectionError(RuntimeError):
    """The strict cubin did not meet the frozen resource contract."""


def _open_regular_nofollow(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink < 1:
        os.close(descriptor)
        raise InspectionError(f"{path} is not a linked regular file")
    return descriptor, metadata


def _sha256_fd(descriptor: int, byte_count: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < byte_count:
        chunk = os.pread(descriptor, min(1024 * 1024, byte_count - offset), offset)
        if not chunk:
            raise InspectionError("file changed or truncated while hashing")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _check_expected_digest(
    descriptor: int,
    metadata: os.stat_result,
    expected: str,
    label: str,
) -> str:
    digest = _sha256_fd(descriptor, metadata.st_size)
    if digest != expected:
        raise InspectionError(f"{label} SHA-256 differs")
    return digest


def _run_cuobjdump(
    tool_fd: int, executable_fd: int, operation: str
) -> str:
    completed = subprocess.run(
        [
            f"/proc/self/fd/{tool_fd}",
            operation,
            f"/proc/self/fd/{executable_fd}",
        ],
        check=False,
        capture_output=True,
        text=True,
        pass_fds=(tool_fd, executable_fd),
        timeout=60,
    )
    if completed.returncode != 0 or completed.stderr:
        raise InspectionError(
            f"cuobjdump {operation} failed: "
            f"exit={completed.returncode} stderr={completed.stderr!r}"
        )
    return completed.stdout


def _parse_image_list(output: str, kind: str) -> list[str]:
    pattern = re.compile(rf"^{kind} file\s+([0-9]+): ([^\r\n]+)$")
    rows = [
        (int(match.group(1)), match.group(2))
        for line in output.splitlines()
        if (match := pattern.fullmatch(line))
    ]
    if not rows or [index for index, _ in rows] != list(
        range(1, len(rows) + 1)
    ):
        raise InspectionError(f"cuobjdump {kind} image roster is malformed")
    return [name for _, name in rows]


def inspect(
    executable: Path,
    expected_executable_sha256: str,
    cuobjdump: Path,
    expected_cuobjdump_sha256: str,
) -> dict[str, object]:
    executable_fd, executable_metadata = _open_regular_nofollow(executable)
    tool_fd, tool_metadata = _open_regular_nofollow(cuobjdump)
    try:
        executable_sha256 = _check_expected_digest(
            executable_fd,
            executable_metadata,
            expected_executable_sha256,
            "strict executable",
        )
        tool_sha256 = _check_expected_digest(
            tool_fd, tool_metadata, expected_cuobjdump_sha256, "cuobjdump"
        )
        resource_output = _run_cuobjdump(
            tool_fd, executable_fd, "--dump-resource-usage"
        )
        cubin_images = _parse_image_list(
            _run_cuobjdump(tool_fd, executable_fd, "--list-elf"), "ELF"
        )
        ptx_images = _parse_image_list(
            _run_cuobjdump(tool_fd, executable_fd, "--list-ptx"), "PTX"
        )
        ptx_output = _run_cuobjdump(
            tool_fd, executable_fd, "--dump-ptx"
        )
        if (
            len(cubin_images) != 3
            or cubin_images[:2] != EXPECTED_CUBIN_IMAGES
            or re.fullmatch(
                r"[0-9]+\.3\.sm_90\.cubin", cubin_images[2]
            )
            is None
        ):
            raise InspectionError("strict sm90 cubin image roster differs")
        if ptx_images != EXPECTED_PTX_FALLBACK_IMAGES:
            raise InspectionError("strict PTX fallback roster differs")
        ptx_targets = set(
            re.findall(r"^\.target (sm_[0-9]+)$", ptx_output, re.MULTILINE)
        )
        if ptx_targets != {"sm_90"}:
            raise InspectionError(
                f"strict PTX target labels differ: {ptx_targets}"
            )
        architectures = set(
            re.findall(r"^arch = (sm_[0-9]+)$", resource_output, re.MULTILINE)
        )
        if architectures != {"sm_90"}:
            raise InspectionError(
                "strict resource-report image architectures differ: "
                f"{architectures}"
            )
        lines = resource_output.splitlines()
        matches = [
            index
            for index, line in enumerate(lines)
            if line.startswith(" Function ") and KERNEL in line
        ]
        if len(matches) != 1 or matches[0] + 1 >= len(lines):
            raise InspectionError("actual fused-kernel resource row is not unique")
        resource_match = RESOURCE_PATTERN.match(lines[matches[0] + 1])
        if resource_match is None:
            raise InspectionError("actual fused-kernel resource row is malformed")
        registers, stack, shared, local = (
            int(value) for value in resource_match.groups()
        )
        evaluated_threads = 256
        registers_per_block = registers * evaluated_threads
        frozen_identity = (registers, stack, shared, local) == (77, 0, 33792, 0)
        resource_feasible = (
            1 <= registers <= 255
            and evaluated_threads <= 1024
            and registers_per_block <= 65536
            and stack == 0
            and local == 0
            and 0 < shared <= 49152
        )
        if not frozen_identity or not resource_feasible:
            raise InspectionError(
                "strict fused-kernel resources fail the frozen feasibility gate"
            )
        if (
            _sha256_fd(executable_fd, executable_metadata.st_size)
            != executable_sha256
            or _sha256_fd(tool_fd, tool_metadata.st_size) != tool_sha256
        ):
            raise InspectionError("inspected executable or tool changed during run")
        return {
            "schema": SCHEMA,
            "accepted": True,
            "resource_cubin_architecture": "sm_90",
            "resource_report_image_architectures": ["sm_90"],
            "embedded_cubin_images": cubin_images,
            "embedded_cubin_normalized_roster": [
                *EXPECTED_CUBIN_IMAGES,
                "<inherited-fd>.3.sm_90.cubin",
            ],
            "embedded_cubin_image_roles": EXPECTED_CUBIN_IMAGE_ROLES,
            "linked_archive_image_label_is_fd_basename_dependent": True,
            "embedded_cubin_roster_checked": True,
            "ptx_fallback_present": True,
            "ptx_fallback_images": ptx_images,
            "ptx_fallback_roster_checked": True,
            "ptx_fallback_cuobjdump_target_labels": ["sm_90"],
            "ptx_fallback_semantics_proved": False,
            "kernel": KERNEL,
            "registers_per_thread": registers,
            "stack_bytes": stack,
            "cuobjdump_shared_bytes": shared,
            "local_bytes": local,
            "evaluated_threads_per_block": evaluated_threads,
            "registers_per_evaluated_block": registers_per_block,
            "h100_registers_per_multiprocessor_bound": 65536,
            "h100_default_static_shared_bytes_bound": 49152,
            "frozen_resource_identity": True,
            "strict_resource_feasible": True,
            "launch_geometry_extracted_from_binary": False,
            "h100_resource_limit_model_proved": False,
            "executable_sha256": executable_sha256,
            "executable_bytes": executable_metadata.st_size,
            "cuobjdump_sha256": tool_sha256,
            "cuobjdump_bytes": tool_metadata.st_size,
            "cuobjdump_tool_identity_checked": True,
            "cuobjdump_semantics_proved": False,
            "runtime_cuda_attributes_measured": False,
            "h100_execution_performed": False,
            "h100_performance_claimed": False,
            "binary_to_source_binding_proved": False,
            "compiler_refinement_proved": False,
        }
    finally:
        os.close(tool_fd)
        os.close(executable_fd)


def _lower_hex(value: str) -> bool:
    return (
        len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--expected-executable-sha256", required=True)
    parser.add_argument("--cuobjdump", type=Path, required=True)
    parser.add_argument("--expected-cuobjdump-sha256", required=True)
    arguments = parser.parse_args()
    if not _lower_hex(arguments.expected_executable_sha256):
        parser.error("--expected-executable-sha256 must be lowercase hex")
    if not _lower_hex(arguments.expected_cuobjdump_sha256):
        parser.error("--expected-cuobjdump-sha256 must be lowercase hex")
    try:
        report = inspect(
            arguments.executable,
            arguments.expected_executable_sha256,
            arguments.cuobjdump,
            arguments.expected_cuobjdump_sha256,
        )
    except (OSError, ValueError, InspectionError) as error:
        print(
            f"inspect_pt21_bitreverse_tile9_sm90_resources: {error}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

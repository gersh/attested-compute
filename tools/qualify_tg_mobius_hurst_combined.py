#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed paired qualification for the combined Möbius/Hurst candidate.

One immutable execution-image copy is used for both compared paths:

* current production p5 residue seed plus the global CUB prefix scan; and
* qualification-only p11 residue seed plus ordered affine block composition.

The tool compares every exact leaf and terminal semantic field, audits the
allocation equations, and extracts actual CUDA resource usage from a freshly
built strict-sm90 executable.  A bounded run is qualification evidence only.
The Azure mode additionally requires that the exact strict-sm90 image execute
on one H100, but it still is not attestation, compiler refinement, source
evidence, or a Lean theorem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes


SCHEMA = "sparkinterval.tg.mobius-hurst-combined-qualification.v1"
CLASSIFICATION = (
    "qualification_only_p5_global_scan_vs_p11_block_compose_"
    "not_source_evidence_attestation_compiler_refinement_or_lean_proof"
)
SOURCE_LIMIT = 10_000_000_000_000_000
MAXIMUM_LEAF_ROWS = 100_000_000
MINIMUM_CROSSOVER_ROWS = 256 * 65_536 + 1
AFFINE_ROWS_PER_THREAD = 256
AFFINE_ROWS_PER_BLOCK = 65_536
EVENTS_PER_BLOCK = 256 * 4_096
SOURCE_ROSTER_SHA256 = (
    "0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5"
)
NONROOT_DIGEST = "1" * 64
PRODUCTION_ALGORITHM = "tg_mobius_fused_affine_persistent_v1"
PRODUCTION_LEAF_DOMAIN = "sparkinterval.tg.mobius-persistent-leaf.v1"
CANDIDATE_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_235711_block_compose_"
    "rpt256_rpb65536_qualification_v1"
)
CANDIDATE_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue-235711-affine-"
    "block-compose-rpt256-rpb65536-qualification-leaf.v1"
)
STRICT_TARGET = "sparkinterval-h100-tg-mobius-persistent"
PORTABLE_TARGET = "sparkinterval-tg-mobius-persistent"

SOURCE_FILES = (
    "CMakeLists.txt",
    "SparkInterval/TernaryGoldbach/HurstAffineBlockComposition.lean",
    "SparkInterval/TernaryGoldbach/MobiusQualificationSeededRefinement.lean",
    "SparkInterval/TernaryGoldbach/MobiusResidue235711.lean",
    "gpu/include/sparkinterval/tg_mobius_affine_candidate_order.hpp",
    "gpu/include/tg_mobius_persistent_device_policy.h",
    "gpu/include/tg_mobius_segment.h",
    "gpu/platform/h100/h100_runtime_policy.h",
    "gpu/platform/h100/h100_tg_mobius_persistent_runner.cpp",
    "gpu/platform/h100/h100_tg_mobius_segment_kernel.cu",
    "gpu/src/tg_mobius_persistent_runner.cpp",
    "gpu/src/tg_mobius_segment_kernel.cu",
    "gpu/src/tg_mobius_segment_runner.cpp",
)

LEAF_SEMANTIC_FIELDS = (
    "lower",
    "upper_exclusive",
    "count",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "delta_squarefree",
    "hurst_lower",
    "hurst_upper",
    "squarefree_lower",
    "squarefree_upper",
    "poison_count",
)
TERMINAL_SEMANTIC_FIELDS = (
    "lower",
    "upper_exclusive",
    "count",
    "leaf_count",
    "incoming_mertens",
    "outgoing_mertens",
    "delta_mertens",
    "incoming_squarefree",
    "outgoing_squarefree",
    "delta_squarefree",
    "global_hurst_lower",
    "global_hurst_upper",
    "global_squarefree_lower",
    "global_squarefree_upper",
    "little_mertens_lower_delta",
    "little_mertens_upper_delta",
)

RESOURCE_ROLE_PATTERNS: Mapping[str, Mapping[str, str]] = {
    "shared": {
        "dense_distinct_divisor": (
            "mark_dense_prime_fused_distinct_divisors_multiblockILm512EEE"
        ),
        "sparse_distinct_divisor": (
            "mark_sparse_prime_fused_distinct_divisorsE"
        ),
        "dense_square_strike": "mark_dense_prime_fused_squarefulE",
        "sparse_square_strike": "mark_sparse_prime_fused_squarefulE",
        "roster_preflight": "validate_split_square_mobius_rosterE",
    },
    "current": {
        "p5_initializer": (
            "initialize_fused_mobius_support_residue_235ILb0ELb0ELb0EEE"
        ),
        "prefix_input_finalizer": "finalize_fused_mobius_prefix_inputsE",
        "cub_global_scan": "DeviceScanKernel",
        "thread_candidates": "affine_mq_thread_candidatesE",
        "block_candidates": "affine_mq_block_candidatesE",
        "device_candidate": "affine_mq_device_candidateE",
    },
    "candidate": {
        "p11_initializer": (
            "initialize_fused_mobius_support_residue_235ILb1ELb1ELb0EEE"
        ),
        "block_summaries": (
            "affine_mq_block_summaries_from_fused_supportsE"
        ),
        "ordered_block_compose": "affine_mq_compose_block_summariesE",
    },
}


class QualificationError(RuntimeError):
    """The paired qualification failed closed."""


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: Any) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _decimal(value: float) -> str:
    if not math.isfinite(value) or value < 0:
        raise QualificationError("timing is not finite and nonnegative")
    return format(value, ".17g")


def _positive_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QualificationError(f"{what} must be a positive integer")
    return value


def _nonnegative_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualificationError(f"{what} must be a nonnegative integer")
    return value


def _digest_string(value: object, what: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
    ):
        raise QualificationError(f"{what} must be a lowercase SHA-256")
    return value


def _exact_dict(
    value: object, keys: Iterable[str], what: str
) -> dict[str, Any]:
    expected = set(keys)
    if not isinstance(value, dict) or set(value) != expected:
        raise QualificationError(
            f"{what} fields differ: expected {sorted(expected)!r}"
        )
    return value


def _source_manifest() -> dict[str, Any]:
    files: list[dict[str, str]] = []
    for relative in SOURCE_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise QualificationError(f"required source file is absent: {relative}")
        files.append({"path": relative, "sha256": _sha256_file(path)})
    return {"files": files, "sha256": _digest(files)}


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 1_800,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise QualificationError(
            f"{list(command)!r} returned {result.returncode}: "
            f"{result.stderr.decode(errors='replace')!r}"
        )
    return result


def _build_target(build_dir: Path, target: str, timeout: int) -> None:
    _run(
        [
            "cmake",
            "--build",
            str(build_dir.resolve()),
            "--config",
            "Release",
            "--target",
            target,
            "--parallel",
            "2",
        ],
        cwd=ROOT,
        timeout=timeout,
    )


def _cache_values(build_dir: Path) -> dict[str, str]:
    cache = build_dir / "CMakeCache.txt"
    if not cache.is_file():
        raise QualificationError(f"CMake cache is absent: {cache}")
    values: dict[str, str] = {}
    for line in cache.read_text(encoding="utf-8", errors="strict").splitlines():
        if line.startswith(("//", "#")) or "=" not in line or ":" not in line:
            continue
        typed, value = line.split("=", 1)
        name, _kind = typed.split(":", 1)
        values[name] = value
    return values


def _build_identity(
    build_dir: Path, target: str, executable: Path
) -> dict[str, Any]:
    expected_executable = (build_dir / target).resolve()
    if executable.resolve() != expected_executable:
        raise QualificationError(
            f"{target} executable must be exactly {expected_executable}"
        )
    cache = build_dir / "CMakeCache.txt"
    values = _cache_values(build_dir)
    if values.get("CMAKE_BUILD_TYPE") != "Release":
        raise QualificationError(f"{target} was not configured as Release")
    rows = values.get(
        "SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD"
    )
    if rows != str(AFFINE_ROWS_PER_THREAD):
        raise QualificationError(
            f"{target} has unproved affine rows/thread {rows!r}"
        )
    metadata_candidates = (
        Path("CMakeCache.txt"),
        Path("build.ninja"),
        Path("Makefile"),
        Path(f"CMakeFiles/{target}.dir/flags.make"),
        Path(f"CMakeFiles/{target}.dir/link.txt"),
    )
    metadata = []
    for relative in metadata_candidates:
        path = build_dir / relative
        if path.is_file():
            metadata.append(
                {"path": relative.as_posix(), "sha256": _sha256_file(path)}
            )
    if len(metadata) < 2:
        raise QualificationError(f"{target} build metadata is incomplete")
    readelf = _run(["readelf", "-n", str(executable.resolve())])
    build_ids = re.findall(
        rb"Build ID:\s*([0-9a-f]+)", readelf.stdout
    )
    if len(build_ids) != 1:
        raise QualificationError(f"{target} has no unique ELF build id")
    architectures = values.get("CMAKE_CUDA_ARCHITECTURES", "")
    return {
        "target": target,
        "cmake_build_type": "Release",
        "cmake_cuda_architectures": architectures,
        "affine_rows_per_thread": AFFINE_ROWS_PER_THREAD,
        "cmake_cache_sha256": _sha256_file(cache),
        "metadata": metadata,
        "metadata_manifest_sha256": _digest(metadata),
        "elf_build_id": build_ids[0].decode("ascii"),
        "executable_sha256": _sha256_file(executable),
    }


def _tool_identity(path: Path, version_argument: str) -> dict[str, str]:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise QualificationError(f"required executable tool is absent: {path}")
    version = _run([str(path.resolve()), version_argument])
    raw = version.stdout + version.stderr
    if not raw.strip():
        raise QualificationError(f"{path.name} emitted no version")
    return {
        "sha256": _sha256_file(path),
        "version_sha256": _sha256_bytes(raw),
    }


def _parse_resource_usage(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="strict")
    function_pattern = re.compile(
        r"^ Function (.+):\n"
        r"^\s+REG:(\d+) STACK:(\d+) SHARED:(\d+) LOCAL:(\d+) "
        r"CONSTANT\[0\]:(\d+)",
        re.MULTILINE,
    )
    functions: list[tuple[str, dict[str, int]]] = []
    for match in function_pattern.finditer(text):
        functions.append(
            (
                match.group(1),
                {
                    "registers_per_thread": int(match.group(2)),
                    "stack_bytes_per_thread": int(match.group(3)),
                    "shared_bytes_per_block": int(match.group(4)),
                    "local_bytes_per_thread": int(match.group(5)),
                    "constant0_bytes": int(match.group(6)),
                },
            )
        )
    if not functions:
        raise QualificationError("cuobjdump emitted no function resources")

    def unique(pattern: str, role: str) -> dict[str, int]:
        matches = [resource for name, resource in functions if pattern in name]
        if len(matches) != 1:
            raise QualificationError(
                f"resource role {role!r} matched {len(matches)} functions"
            )
        return matches[0]

    roles: dict[str, dict[str, dict[str, int]]] = {}
    for family, patterns in RESOURCE_ROLE_PATTERNS.items():
        roles[family] = {
            role: unique(pattern, f"{family}.{role}")
            for role, pattern in patterns.items()
        }
    all_resources = [
        resource
        for family in roles.values()
        for resource in family.values()
    ]
    gate = all(
        resource["registers_per_thread"] <= 64
        and resource["stack_bytes_per_thread"] <= 64
        and resource["shared_bytes_per_block"] <= 227_328
        and resource["local_bytes_per_thread"] == 0
        for resource in all_resources
    )
    if not gate:
        raise QualificationError("strict-sm90 CUDA resource gate failed")
    return {
        "roles": roles,
        "gate": {
            "accepted": True,
            "maximum_registers_per_thread": 64,
            "maximum_stack_bytes_per_thread": 64,
            "maximum_shared_bytes_per_block": 227_328,
            "required_local_bytes_per_thread": 0,
        },
    }


def _strict_sm90_evidence(
    executable: Path, cuobjdump: Path
) -> dict[str, Any]:
    listed = _run(
        [str(cuobjdump.resolve()), "--list-elf", str(executable.resolve())]
    )
    listed_text = listed.stdout.decode("utf-8", errors="strict")
    cubins = re.findall(r"(\S+\.sm_([0-9]+)\.cubin)", listed_text)
    if not cubins or {arch for _name, arch in cubins} != {"90"}:
        raise QualificationError("strict executable is not sm90-cubin-only")
    usage = _run(
        [
            str(cuobjdump.resolve()),
            "--dump-resource-usage",
            str(executable.resolve()),
        ]
    )
    raw = usage.stdout + usage.stderr
    arches = set(re.findall(rb"arch = (sm_[0-9]+)", raw))
    if arches != {b"sm_90"}:
        raise QualificationError("strict resource image contains non-sm90 code")
    parsed = _parse_resource_usage(raw)
    return {
        "sm90_cubin_only": True,
        "cubin_names_sha256": _digest(sorted(name for name, _arch in cubins)),
        "resource_usage_sha256": _sha256_bytes(raw),
        "roles": parsed["roles"],
        "gate": parsed["gate"],
    }


def _runtime_device(strict_h100_runtime: bool) -> dict[str, Any]:
    selector = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,compute_cap,uuid,driver_version",
        "--format=csv,noheader,nounits",
    ]
    selector_present = bool(selector)
    if strict_h100_runtime and selector_present:
        selected_tokens = [
            token.strip() for token in selector.split(",") if token.strip()
        ]
        if len(selected_tokens) != 1:
            raise QualificationError(
                "strict H100 mode requires one CUDA_VISIBLE_DEVICES member"
            )
        command.append(f"--id={selected_tokens[0]}")
    result = _run(
        command
    )
    rows = [
        [part.strip() for part in line.split(",")]
        for line in result.stdout.decode("utf-8", errors="strict").splitlines()
        if line.strip()
    ]
    if not rows or any(len(row) != 5 for row in rows):
        raise QualificationError("nvidia-smi device query was malformed")
    if strict_h100_runtime and len(rows) != 1:
        raise QualificationError("strict H100 mode requires one visible GPU")
    selected = rows[0]
    measured_h100 = (
        strict_h100_runtime
        and selected[2] == "9.0"
        and "H100" in selected[1]
    )
    if strict_h100_runtime and not measured_h100:
        raise QualificationError("strict H100 mode did not find an H100 sm90")
    return {
        "visible_device_count": len(rows),
        "selected_index": selected[0],
        "selected_name": selected[1],
        "selected_compute_capability": selected[2],
        "selected_uuid": selected[3],
        "driver_version": selected[4],
        "cuda_visible_devices_selector_present": selector_present,
        "strict_h100_runtime": strict_h100_runtime,
        "target_h100_measured": measured_h100,
    }


def _copy_execution_image(source: Path, destination: Path) -> str:
    before = source.stat()
    if not source.is_file():
        raise QualificationError("runtime executable is not a regular file")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(destination, flags, 0o500)
    try:
        with source.open("rb") as incoming:
            while chunk := incoming.read(1 << 20):
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise QualificationError("short execution-image write")
                    view = view[written:]
        os.fsync(descriptor)
        copied = os.fstat(descriptor)
        if not os.path.isfile(destination) or copied.st_size != before.st_size:
            raise QualificationError("execution-image copy changed size")
    finally:
        os.close(descriptor)
    after = source.stat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise QualificationError("runtime executable changed during copy")
    source_digest = _sha256_file(source)
    if _sha256_file(destination) != source_digest:
        raise QualificationError("execution-image copy differs bytewise")
    return source_digest


def _parse_jsonl(raw: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        text = raw.decode("utf-8", errors="strict")
        for line in text.splitlines():
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise QualificationError("runner JSONL member is not an object")
            records.append(record)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError("runner emitted invalid JSONL") from exc
    if (
        len(records) < 3
        or records[0].get("record") != "header"
        or records[-1].get("record") != "terminal"
        or any(record.get("record") != "leaf" for record in records[1:-1])
    ):
        raise QualificationError("runner record order is not header/leaves/terminal")
    for expected, leaf in enumerate(records[1:-1]):
        if leaf.get("index") != expected:
            raise QualificationError("runner leaf indexes are not contiguous")
    if records[-1].get("leaf_count") != len(records) - 2:
        raise QualificationError("terminal leaf count differs from JSONL")
    return records


def _assert_false_claims(record: Mapping[str, Any]) -> None:
    for field in (
        "execution_attested",
        "cuda_or_cpp_compiler_refinement_proved",
        "lean_atom_discharged",
        "proves_any_external_atom",
    ):
        if record.get(field) is not False:
            raise QualificationError(f"runner did not keep {field} false")


def _validate_runner_records(
    records: list[dict[str, Any]],
    *,
    variant: str,
    executable_sha256: str,
) -> None:
    header = records[0]
    terminal = records[-1]
    if header.get("executable_sha256") != executable_sha256:
        raise QualificationError("runner executable identity differs")
    if header.get("prime_roster_sha256") != SOURCE_ROSTER_SHA256:
        raise QualificationError("runner roster identity differs")
    if header.get("cuda_allocation_epoch_count") != 1:
        raise QualificationError("runner did not use one allocation epoch")
    _assert_false_claims(header)
    _assert_false_claims(terminal)
    for leaf in records[1:-1]:
        _assert_false_claims(leaf)
        if leaf.get("poison_count") != 0:
            raise QualificationError("runner emitted a poisoned row")
    if variant == "current":
        if (
            header.get("algorithm") != PRODUCTION_ALGORITHM
            or "receipt_leaf_domain" in header
            or "qualification_only_not_production_admissible" in header
            or header.get("production_fused_prefix_input_path") is not True
            or header.get("production_split_square_support_path") is not True
            or header.get("intermediate_mobius_device_rows_materialized")
            is not False
            or terminal.get("algorithm") != PRODUCTION_ALGORITHM
        ):
            raise QualificationError("current identity/path is not production p5 scan")
    elif variant == "candidate":
        if (
            header.get("algorithm") != CANDIDATE_ALGORITHM
            or header.get("receipt_leaf_domain") != CANDIDATE_LEAF_DOMAIN
            or header.get("qualification_only_not_production_admissible")
            is not True
            or header.get("qualification_residue_235711_seed") is not True
            or header.get("residue_seed_prime_count") != 5
            or header.get("qualification_affine_block_compose") is not True
            or header.get(
                "qualification_direct_fused_support_block_compose_path"
            )
            is not True
            or header.get("production_fused_prefix_input_path") is not False
            or header.get("affine_block_summary_rows_per_thread")
            != AFFINE_ROWS_PER_THREAD
            or header.get("affine_block_summary_rows")
            != AFFINE_ROWS_PER_BLOCK
            or header.get("affine_workspace_device_bytes") != 0
        ):
            raise QualificationError("candidate identity/path is not p11 compose")
        for record in records[1:]:
            if (
                record.get("algorithm") != CANDIDATE_ALGORITHM
                or record.get("receipt_leaf_domain") != CANDIDATE_LEAF_DOMAIN
                or record.get("qualification_only_not_production_admissible")
                is not True
            ):
                raise QualificationError("candidate leaf identity is not isolated")
    else:
        raise QualificationError("unknown runner variant")


def _semantic_transcript(
    records: list[dict[str, Any]]
) -> dict[str, Any]:
    leaves = []
    for leaf in records[1:-1]:
        try:
            leaves.append({field: leaf[field] for field in LEAF_SEMANTIC_FIELDS})
        except KeyError as exc:
            raise QualificationError(
                f"runner leaf omitted semantic field {exc.args[0]}"
            ) from exc
    terminal = records[-1]
    try:
        terminal_semantics = {
            field: terminal[field] for field in TERMINAL_SEMANTIC_FIELDS
        }
    except KeyError as exc:
        raise QualificationError(
            f"runner terminal omitted semantic field {exc.args[0]}"
        ) from exc
    return {"leaves": leaves, "terminal": terminal_semantics}


def _timing(records: list[dict[str, Any]], wall_ms: float) -> dict[str, str]:
    terminal = records[-1]

    def number(name: str) -> float:
        try:
            value = float(terminal[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise QualificationError(f"runner timing {name} is invalid") from exc
        if not math.isfinite(value) or value < 0:
            raise QualificationError(f"runner timing {name} is invalid")
        return value

    kernel = number("kernel_milliseconds")
    affine = number("affine_milliseconds")
    process = number("process_milliseconds")
    return {
        "kernel_ms": _decimal(kernel),
        "affine_ms": _decimal(affine),
        "device_work_ms": _decimal(kernel + affine),
        "process_ms": _decimal(process),
        "wall_ms": _decimal(wall_ms),
    }


def _run_variant(
    executable: Path,
    roster: Path,
    *,
    variant: str,
    lower: int,
    count: int,
    strict_h100_runtime: bool,
    timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    command = [
        str(executable.resolve()),
        "--lower",
        str(lower),
        "--count",
        str(count),
        "--shard-rows",
        str(count),
        "--super-shard-rows",
        str(count),
        "--incoming-mertens",
        "0",
        "--incoming-squarefree",
        "0",
        "--previous-leaf-sha256",
        NONROOT_DIGEST,
        "--source-prime-roster",
        str(roster.resolve()),
    ]
    if strict_h100_runtime:
        command.extend(
            ["--require-device-class", "nvidia-h100-sm90"]
        )
    else:
        command.append("--allow-other-device")
    if variant == "candidate":
        command.extend(
            [
                "--qualification-residue-235711-seed",
                "--qualification-affine-block-compose",
            ]
        )
    started = time.monotonic_ns()
    result = _run(command, cwd=ROOT, timeout=timeout)
    wall_ms = (time.monotonic_ns() - started) / 1_000_000
    records = _parse_jsonl(result.stdout)
    executable_sha256 = _sha256_file(executable)
    _validate_runner_records(
        records, variant=variant, executable_sha256=executable_sha256
    )
    return records, _timing(records, wall_ms)


def _allocation_report(
    current: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    current_components = {
        "persistent_total": _positive_int(
            current.get("persistent_device_allocation_bytes"),
            "current persistent allocation",
        ),
        "fused_support": _positive_int(
            current.get("fused_support_device_bytes"),
            "current fused support",
        ),
        "prefix": _positive_int(
            current.get("affine_prefix_device_bytes"),
            "current prefix allocation",
        ),
        "workspace": _positive_int(
            current.get("affine_workspace_device_bytes"),
            "current workspace",
        ),
        "block_summaries": _nonnegative_int(
            current.get("affine_block_summary_device_bytes", 0),
            "current block summaries",
        ),
    }
    candidate_components = {
        "persistent_total": _positive_int(
            candidate.get("persistent_device_allocation_bytes"),
            "candidate persistent allocation",
        ),
        "fused_support": _positive_int(
            candidate.get("fused_support_device_bytes"),
            "candidate fused support",
        ),
        "prefix": _positive_int(
            candidate.get("affine_prefix_device_bytes"),
            "candidate prefix allocation",
        ),
        "workspace": _nonnegative_int(
            candidate.get("affine_workspace_device_bytes"),
            "candidate workspace",
        ),
        "block_summaries": _positive_int(
            candidate.get("affine_block_summary_device_bytes"),
            "candidate block summaries",
        ),
    }
    if current_components["fused_support"] != candidate_components["fused_support"]:
        raise QualificationError("paired fused-support allocation differs")
    expected_saved = (
        current_components["prefix"]
        + current_components["workspace"]
        + current_components["block_summaries"]
        - candidate_components["prefix"]
        - candidate_components["workspace"]
        - candidate_components["block_summaries"]
    )
    actual_saved = (
        current_components["persistent_total"]
        - candidate_components["persistent_total"]
    )
    if expected_saved != actual_saved:
        raise QualificationError("paired allocation equation differs")
    reference_bytes = candidate.get(
        "affine_scan_prefix_reference_device_bytes"
    )
    if (
        reference_bytes != current_components["prefix"]
        or candidate.get("affine_block_compose_scan_workspace_omitted")
        is not True
    ):
        raise QualificationError("candidate scan-memory comparison is unbound")
    return {
        "current": current_components,
        "candidate": candidate_components,
        "candidate_saved_bytes": actual_saved,
        "exact_component_equation_verified": True,
    }


def _summary_count(count: int) -> int:
    return 1 + (count - 1) // AFFINE_ROWS_PER_BLOCK


def _multiple_count(lower: int, count: int, prime: int) -> int:
    remainder = lower % prime
    first = 0 if remainder == 0 else prime - remainder
    return 0 if first >= count else 1 + (count - 1 - first) // prime


def _summaries(values: list[dict[str, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in (
        "kernel_ms",
        "affine_ms",
        "device_work_ms",
        "process_ms",
        "wall_ms",
    ):
        samples = [float(value[field]) for value in values]
        result[field] = [value[field] for value in values]
        result[f"{field[:-3]}_median_ms"] = _decimal(
            statistics.median(samples)
        )
    return result


def _validate_report_resource(
    value: object, what: str
) -> dict[str, Any]:
    resource = _exact_dict(
        value,
        {
            "constant0_bytes",
            "local_bytes_per_thread",
            "registers_per_thread",
            "shared_bytes_per_block",
            "stack_bytes_per_thread",
        },
        what,
    )
    for field in resource:
        _nonnegative_int(resource[field], f"{what}.{field}")
    if (
        resource["registers_per_thread"] > 64
        or resource["stack_bytes_per_thread"] > 64
        or resource["shared_bytes_per_block"] > 227_328
        or resource["local_bytes_per_thread"] != 0
    ):
        raise QualificationError(f"{what} exceeds the resource gate")
    return resource


def _validate_timing_summary(
    value: object, repetitions: int, what: str
) -> dict[str, Any]:
    keys = set()
    bases = ("kernel", "affine", "device_work", "process", "wall")
    for base in bases:
        keys.add(f"{base}_ms")
        keys.add(f"{base}_median_ms")
    summary = _exact_dict(value, keys, what)
    for base in bases:
        samples = summary[f"{base}_ms"]
        if not isinstance(samples, list) or len(samples) != repetitions:
            raise QualificationError(f"{what}.{base}_ms has wrong length")
        parsed = []
        for sample in samples:
            try:
                number = float(sample)
            except (TypeError, ValueError) as exc:
                raise QualificationError(
                    f"{what}.{base}_ms is not numeric"
                ) from exc
            if not math.isfinite(number) or number < 0:
                raise QualificationError(
                    f"{what}.{base}_ms is not finite and nonnegative"
                )
            parsed.append(number)
        try:
            reported_median = float(summary[f"{base}_median_ms"])
        except (TypeError, ValueError) as exc:
            raise QualificationError(
                f"{what}.{base}_median_ms is not numeric"
            ) from exc
        if (
            not math.isfinite(reported_median)
            or reported_median < 0
            or not math.isclose(
                reported_median,
                statistics.median(parsed),
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise QualificationError(f"{what}.{base} median is inconsistent")
    return summary


def validate_report(value: object) -> dict[str, Any]:
    """Validate the closed report schema and its cross-field equations."""

    report = _exact_dict(
        value,
        {
            "accepted",
            "alternating_benchmark",
            "allocation",
            "build_evidence",
            "claims",
            "classification",
            "cuda_resources",
            "identities",
            "mode",
            "runtime_device",
            "runtime_instrumentation",
            "schema",
            "semantic_equivalence",
            "workload",
        },
        "combined qualification report",
    )
    if (
        report["schema"] != SCHEMA
        or report["classification"] != CLASSIFICATION
        or report["accepted"] is not True
        or report["mode"] not in {"bounded", "azure-h100-benchmark"}
    ):
        raise QualificationError("combined report identity differs")

    claims = _exact_dict(
        report["claims"],
        {
            "candidate_selected_in_production",
            "compiler_refinement_proved",
            "cuda_to_lean_refinement_proved",
            "default_behavior_changed",
            "execution_attested",
            "performance_evidence_eligible",
            "production_identity_changed",
            "projection_used",
            "proves_any_external_atom",
            "production_receipt_identity_changed",
            "source_range_evidence",
            "production_theorem_identity_changed",
        },
        "claims",
    )
    for field in (
        "candidate_selected_in_production",
        "compiler_refinement_proved",
        "cuda_to_lean_refinement_proved",
        "default_behavior_changed",
        "execution_attested",
        "production_identity_changed",
        "projection_used",
        "proves_any_external_atom",
        "production_receipt_identity_changed",
        "source_range_evidence",
        "production_theorem_identity_changed",
    ):
        if claims[field] is not False:
            raise QualificationError(f"claim {field} must remain false")

    semantics = _exact_dict(
        report["semantic_equivalence"],
        {
            "candidate_transcript_sha256",
            "compared_leaf_fields",
            "compared_terminal_fields",
            "current_transcript_sha256",
            "exact_output_semantics_equal",
            "four_residual_projection",
            "leaf_count",
            "receipt_digests_distinct",
            "receipt_domains_distinct",
        },
        "semantic equivalence",
    )
    if (
        semantics.get("exact_output_semantics_equal") is not True
        or semantics.get("receipt_domains_distinct") is not True
        or semantics.get("receipt_digests_distinct") is not True
        or semantics.get("current_transcript_sha256")
        != semantics.get("candidate_transcript_sha256")
    ):
        raise QualificationError("semantic comparison is not exact")
    _digest_string(
        semantics.get("current_transcript_sha256"),
        "current semantic transcript",
    )
    if (
        semantics["compared_leaf_fields"] != list(LEAF_SEMANTIC_FIELDS)
        or semantics["compared_terminal_fields"]
        != list(TERMINAL_SEMANTIC_FIELDS)
        or _positive_int(semantics["leaf_count"], "semantic leaf count") != 1
    ):
        raise QualificationError("semantic comparison field set differs")
    residuals = _exact_dict(
        semantics["four_residual_projection"],
        {
            "little_mertens_lower_delta",
            "little_mertens_upper_delta",
            "mertens_hurst",
            "squarefree_cdem",
        },
        "four residual projection",
    )
    if (
        residuals["little_mertens_lower_delta"] != 0
        or residuals["little_mertens_upper_delta"] != 0
    ):
        raise QualificationError("terminal little-Mertens deltas are not zero")
    for family in ("mertens_hurst", "squarefree_cdem"):
        bounds = _exact_dict(
            residuals[family], {"lower", "upper"}, f"residual {family}"
        )
        if not isinstance(bounds["lower"], dict) or not isinstance(
            bounds["upper"], dict
        ):
            raise QualificationError(f"residual {family} bounds are absent")

    identities = _exact_dict(
        report["identities"],
        {
            "candidate_algorithm",
            "candidate_leaf_domain",
            "current_algorithm",
            "execution_image_sha256",
            "production_leaf_domain",
            "runtime_matches_strict_h100_executable",
            "runtime_original_sha256",
            "same_execution_image_both_variants",
            "source_files",
            "source_manifest_sha256",
            "strict_h100_executable_sha256",
        },
        "identities",
    )
    if (
        identities.get("same_execution_image_both_variants") is not True
        or identities.get("current_algorithm") != PRODUCTION_ALGORITHM
        or identities.get("candidate_algorithm") != CANDIDATE_ALGORITHM
        or identities.get("production_leaf_domain") != PRODUCTION_LEAF_DOMAIN
        or identities.get("candidate_leaf_domain") != CANDIDATE_LEAF_DOMAIN
    ):
        raise QualificationError("paired identities differ")
    for field in (
        "execution_image_sha256",
        "runtime_original_sha256",
        "source_manifest_sha256",
        "strict_h100_executable_sha256",
    ):
        _digest_string(identities.get(field), f"identities.{field}")
    if (
        identities["execution_image_sha256"]
        != identities["runtime_original_sha256"]
    ):
        raise QualificationError("execution copy does not match runtime image")
    source_files = identities["source_files"]
    if not isinstance(source_files, list) or len(source_files) != len(
        SOURCE_FILES
    ):
        raise QualificationError("source identity manifest has wrong length")
    for expected_path, row in zip(SOURCE_FILES, source_files, strict=True):
        checked = _exact_dict(row, {"path", "sha256"}, "source identity row")
        if checked["path"] != expected_path:
            raise QualificationError("source identity order/path differs")
        _digest_string(checked["sha256"], f"source {expected_path}")
    if _digest(source_files) != identities["source_manifest_sha256"]:
        raise QualificationError("source identity manifest digest differs")
    matches_strict = (
        identities["runtime_original_sha256"]
        == identities["strict_h100_executable_sha256"]
    )
    if identities["runtime_matches_strict_h100_executable"] is not matches_strict:
        raise QualificationError("runtime/strict image comparison differs")

    build = _exact_dict(
        report["build_evidence"],
        {
            "runtime",
            "runtime_build_invoked",
            "strict",
            "strict_build_invoked",
            "tools",
        },
        "build evidence",
    )
    if (
        build["strict_build_invoked"] is not True
        or build["runtime_build_invoked"] is not True
    ):
        raise QualificationError("required build was not invoked")
    build_keys = {
        "affine_rows_per_thread",
        "cmake_build_type",
        "cmake_cache_sha256",
        "cmake_cuda_architectures",
        "elf_build_id",
        "executable_sha256",
        "metadata",
        "metadata_manifest_sha256",
        "target",
    }
    strict_build = _exact_dict(build["strict"], build_keys, "strict build")
    runtime_build = _exact_dict(build["runtime"], build_keys, "runtime build")
    if (
        strict_build["target"] != STRICT_TARGET
        or strict_build["cmake_build_type"] != "Release"
        or strict_build["cmake_cuda_architectures"] not in {"90", "90-real"}
        or strict_build["affine_rows_per_thread"] != AFFINE_ROWS_PER_THREAD
        or strict_build["executable_sha256"]
        != identities["strict_h100_executable_sha256"]
        or runtime_build["target"] not in {PORTABLE_TARGET, STRICT_TARGET}
        or runtime_build["cmake_build_type"] != "Release"
        or runtime_build["affine_rows_per_thread"] != AFFINE_ROWS_PER_THREAD
        or runtime_build["executable_sha256"]
        != identities["runtime_original_sha256"]
    ):
        raise QualificationError("build identity is inconsistent")
    for name, member in (("strict", strict_build), ("runtime", runtime_build)):
        for field in (
            "cmake_cache_sha256",
            "executable_sha256",
            "metadata_manifest_sha256",
        ):
            _digest_string(member[field], f"{name} build {field}")
        if (
            not isinstance(member["elf_build_id"], str)
            or re.fullmatch(r"[0-9a-f]+", member["elf_build_id"]) is None
        ):
            raise QualificationError(f"{name} ELF build id is invalid")
        metadata = member["metadata"]
        if not isinstance(metadata, list) or len(metadata) < 2:
            raise QualificationError(f"{name} build metadata is incomplete")
        for row in metadata:
            checked = _exact_dict(
                row, {"path", "sha256"}, f"{name} build metadata row"
            )
            if (
                not isinstance(checked["path"], str)
                or checked["path"].startswith("/")
                or ".." in Path(checked["path"]).parts
            ):
                raise QualificationError(f"{name} build path is not relative")
            _digest_string(checked["sha256"], f"{name} metadata digest")
        if _digest(metadata) != member["metadata_manifest_sha256"]:
            raise QualificationError(f"{name} metadata manifest differs")
    tools = _exact_dict(build["tools"], {"cuobjdump", "nvcc"}, "build tools")
    for name in ("cuobjdump", "nvcc"):
        member = _exact_dict(
            tools[name], {"sha256", "version_sha256"}, f"tool {name}"
        )
        _digest_string(member["sha256"], f"tool {name}")
        _digest_string(member["version_sha256"], f"tool {name} version")

    resources = _exact_dict(
        report["cuda_resources"],
        {
            "candidate",
            "current",
            "gate",
            "resource_gate_passed",
            "shared",
            "strict_cubin_names_sha256",
            "strict_resource_usage_sha256",
            "strict_sm90_cubin_only",
        },
        "CUDA resources",
    )
    if (
        resources.get("strict_sm90_cubin_only") is not True
        or resources.get("resource_gate_passed") is not True
    ):
        raise QualificationError("strict CUDA resource evidence differs")
    _digest_string(
        resources["strict_cubin_names_sha256"], "strict cubin names"
    )
    _digest_string(
        resources["strict_resource_usage_sha256"], "strict resource usage"
    )
    for family, expected_roles in RESOURCE_ROLE_PATTERNS.items():
        role_map = _exact_dict(
            resources[family], expected_roles.keys(), f"{family} resources"
        )
        for role in expected_roles:
            _validate_report_resource(
                role_map[role], f"{family} resource {role}"
            )
    gate = _exact_dict(
        resources["gate"],
        {
            "accepted",
            "maximum_registers_per_thread",
            "maximum_shared_bytes_per_block",
            "maximum_stack_bytes_per_thread",
            "required_local_bytes_per_thread",
        },
        "resource gate",
    )
    if gate != {
        "accepted": True,
        "maximum_registers_per_thread": 64,
        "maximum_stack_bytes_per_thread": 64,
        "maximum_shared_bytes_per_block": 227_328,
        "required_local_bytes_per_thread": 0,
    }:
        raise QualificationError("resource gate constants differ")

    allocation = _exact_dict(
        report["allocation"],
        {
            "candidate",
            "candidate_saved_bytes",
            "current",
            "exact_component_equation_verified",
        },
        "allocation",
    )
    component_keys = {
        "block_summaries",
        "fused_support",
        "persistent_total",
        "prefix",
        "workspace",
    }
    current_allocation = _exact_dict(
        allocation["current"], component_keys, "current allocation"
    )
    candidate_allocation = _exact_dict(
        allocation["candidate"], component_keys, "candidate allocation"
    )
    for family, member in (
        ("current", current_allocation),
        ("candidate", candidate_allocation),
    ):
        for field in component_keys:
            _nonnegative_int(member[field], f"{family} allocation {field}")
    saved = (
        current_allocation["persistent_total"]
        - candidate_allocation["persistent_total"]
    )
    component_saved = (
        current_allocation["prefix"]
        + current_allocation["workspace"]
        + current_allocation["block_summaries"]
        - candidate_allocation["prefix"]
        - candidate_allocation["workspace"]
        - candidate_allocation["block_summaries"]
    )
    if (
        allocation.get("exact_component_equation_verified") is not True
        or allocation["candidate_saved_bytes"] != saved
        or saved <= 0
        or saved != component_saved
        or current_allocation["fused_support"]
        != candidate_allocation["fused_support"]
    ):
        raise QualificationError("allocation evidence differs")
    instrumentation = _exact_dict(
        report["runtime_instrumentation"],
        {"sanitizer_evidence_bound_to_report", "status"},
        "runtime instrumentation",
    )
    if (
        instrumentation["status"] != "not-inspected-by-paired-runner"
        or instrumentation["sanitizer_evidence_bound_to_report"] is not False
    ):
        raise QualificationError("runtime instrumentation was overstated")

    benchmark = _exact_dict(
        report["alternating_benchmark"],
        {
            "candidate",
            "current",
            "current_over_candidate_device_work_ratio",
            "measured_not_projected",
            "repetitions",
            "schedule",
        },
        "alternating benchmark",
    )
    workload = _exact_dict(
        report["workload"],
        {
            "affine_summary_count",
            "count",
            "crosses_256_summary_boundary",
            "events_per_block",
            "incoming_mertens",
            "incoming_squarefree",
            "lower",
            "p13_multiple_count",
            "p13_second_event_block_exercised",
            "previous_leaf_sha256",
            "prime_roster_sha256",
            "shard_rows",
            "super_shard_rows",
            "upper_exclusive",
        },
        "workload",
    )
    count = _positive_int(workload["count"], "workload count")
    lower = _positive_int(workload["lower"], "workload lower")
    if (
        count < MINIMUM_CROSSOVER_ROWS
        or count > MAXIMUM_LEAF_ROWS
        or workload["upper_exclusive"] != lower + count
        or lower <= 1_000_000_000_000
        or lower + count - 1 > SOURCE_LIMIT
        or workload["shard_rows"] != count
        or workload["super_shard_rows"] != count
        or workload["incoming_mertens"] != 0
        or workload["incoming_squarefree"] != 0
        or workload["previous_leaf_sha256"] != NONROOT_DIGEST
        or workload["prime_roster_sha256"] != SOURCE_ROSTER_SHA256
        or workload["affine_summary_count"] != _summary_count(count)
        or workload["affine_summary_count"] <= 256
        or workload["crosses_256_summary_boundary"] is not True
        or workload["events_per_block"] != EVENTS_PER_BLOCK
        or workload["p13_multiple_count"] != _multiple_count(lower, count, 13)
        or workload["p13_multiple_count"] <= EVENTS_PER_BLOCK
        or workload["p13_second_event_block_exercised"] is not True
    ):
        raise QualificationError("workload/crossover equation differs")
    repetitions = _positive_int(benchmark.get("repetitions"), "repetitions")
    schedule = benchmark.get("schedule")
    if (
        not isinstance(schedule, list)
        or len(schedule) != 2 * repetitions
        or any(
            value != ("current" if index % 4 in (0, 3) else "candidate")
            for index, value in enumerate(schedule)
        )
    ):
        raise QualificationError("benchmark is not pair-balanced alternating")
    current_timing = _validate_timing_summary(
        benchmark["current"], repetitions, "current timing"
    )
    candidate_timing = _validate_timing_summary(
        benchmark["candidate"], repetitions, "candidate timing"
    )
    try:
        ratio = float(benchmark["current_over_candidate_device_work_ratio"])
        expected_ratio = (
            float(current_timing["device_work_median_ms"])
            / float(candidate_timing["device_work_median_ms"])
        )
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise QualificationError("device-work timing ratio is invalid") from exc
    if (
        benchmark["measured_not_projected"] is not True
        or not math.isfinite(ratio)
        or not math.isclose(ratio, expected_ratio, rel_tol=1e-12, abs_tol=1e-12)
    ):
        raise QualificationError("device-work timing ratio is inconsistent")
    device = _exact_dict(
        report["runtime_device"],
        {
            "cuda_visible_devices_selector_present",
            "driver_version",
            "selected_compute_capability",
            "selected_index",
            "selected_name",
            "selected_uuid",
            "strict_h100_runtime",
            "target_h100_measured",
            "visible_device_count",
        },
        "runtime device",
    )
    _positive_int(device["visible_device_count"], "visible device count")
    h100 = device.get("target_h100_measured") is True
    if h100 and (
        device["strict_h100_runtime"] is not True
        or device["selected_compute_capability"] != "9.0"
        or "H100" not in str(device["selected_name"])
        or identities["runtime_matches_strict_h100_executable"] is not True
    ):
        raise QualificationError("H100 measurement identity is inconsistent")
    if report["mode"] == "bounded":
        if claims["performance_evidence_eligible"] is not False:
            raise QualificationError("bounded run claimed performance evidence")
    else:
        if (
            claims["performance_evidence_eligible"] is not True
            or not h100
            or repetitions < 5
            or workload.get("count") != MAXIMUM_LEAF_ROWS
        ):
            raise QualificationError("Azure H100 benchmark gates differ")
    return report


def qualify(arguments: argparse.Namespace) -> dict[str, Any]:
    runtime_build_dir = arguments.runtime_build_dir.resolve()
    strict_build_dir = arguments.strict_build_dir.resolve()
    runtime_runner = arguments.runner.resolve()
    strict_runner = arguments.strict_h100_runner.resolve()
    roster = arguments.prime_roster.resolve()
    if arguments.count < MINIMUM_CROSSOVER_ROWS:
        raise QualificationError(
            f"--count must be at least {MINIMUM_CROSSOVER_ROWS} "
            "to cross the 256/257 affine-summary boundary"
        )
    if arguments.count > MAXIMUM_LEAF_ROWS:
        raise QualificationError("--count exceeds the proved leaf cap")
    lower = (
        SOURCE_LIMIT - arguments.count + 1
        if arguments.lower is None
        else arguments.lower
    )
    if lower <= 1_000_000_000_000 or lower + arguments.count - 1 > SOURCE_LIMIT:
        raise QualificationError("range is not wholly in the terminal GPU domain")
    if arguments.mode == "azure-h100-benchmark":
        if arguments.count != MAXIMUM_LEAF_ROWS or arguments.repeats < 5:
            raise QualificationError(
                "Azure H100 mode requires 100000000 rows and at least 5 pairs"
            )
        arguments.strict_h100_runtime = True
    if not roster.is_file() or _sha256_file(roster) != SOURCE_ROSTER_SHA256:
        raise QualificationError("prime roster does not match the source pin")

    source_before = _source_manifest()
    _build_target(
        strict_build_dir, STRICT_TARGET, arguments.build_timeout
    )
    strict_identity = _build_identity(
        strict_build_dir, STRICT_TARGET, strict_runner
    )
    runtime_target = (
        STRICT_TARGET if arguments.strict_h100_runtime else PORTABLE_TARGET
    )
    if (
        runtime_build_dir != strict_build_dir
        or runtime_target != STRICT_TARGET
    ):
        _build_target(
            runtime_build_dir, runtime_target, arguments.build_timeout
        )
    runtime_identity = _build_identity(
        runtime_build_dir, runtime_target, runtime_runner
    )
    source_after_build = _source_manifest()
    if source_after_build != source_before:
        raise QualificationError("source manifest changed during builds")

    strict_architectures = strict_identity["cmake_cuda_architectures"]
    if strict_architectures not in {"90", "90-real"}:
        raise QualificationError("strict target cache does not select sm90")
    nvcc = arguments.nvcc.resolve()
    cuobjdump = arguments.cuobjdump.resolve()
    tools = {
        "nvcc": _tool_identity(nvcc, "--version"),
        "cuobjdump": _tool_identity(cuobjdump, "--version"),
    }
    strict_resources = _strict_sm90_evidence(strict_runner, cuobjdump)
    device = _runtime_device(arguments.strict_h100_runtime)

    with tempfile.TemporaryDirectory(
        prefix="tg-mobius-hurst-combined-"
    ) as temporary_name:
        temporary = Path(temporary_name)
        execution_image = temporary / "mobius-hurst-paired-image"
        runtime_digest = _copy_execution_image(
            runtime_runner, execution_image
        )
        if runtime_digest != runtime_identity["executable_sha256"]:
            raise QualificationError("runtime build identity changed before copy")
        strict_digest = strict_identity["executable_sha256"]
        runtime_matches_strict = runtime_digest == strict_digest
        if arguments.strict_h100_runtime and not runtime_matches_strict:
            raise QualificationError(
                "strict H100 benchmark did not execute the audited sm90 image"
            )

        schedule = [
            ("current", "candidate")
            if pair % 2 == 0
            else ("candidate", "current")
            for pair in range(arguments.repeats)
        ]
        flat_schedule = [variant for pair in schedule for variant in pair]
        timings: dict[str, list[dict[str, str]]] = {
            "current": [],
            "candidate": [],
        }
        reference_transcript: dict[str, Any] | None = None
        transcript_digest: str | None = None
        reference_headers: dict[str, dict[str, Any]] = {}
        reference_receipts: dict[str, list[str]] = {}
        all_headers_sha256: dict[str, set[str]] = {
            "current": set(),
            "candidate": set(),
        }
        for variant in flat_schedule:
            records, timing = _run_variant(
                execution_image,
                roster,
                variant=variant,
                lower=lower,
                count=arguments.count,
                strict_h100_runtime=arguments.strict_h100_runtime,
                timeout=arguments.run_timeout,
            )
            if _sha256_file(execution_image) != runtime_digest:
                raise QualificationError("execution image changed between variants")
            transcript = _semantic_transcript(records)
            digest = _digest(transcript)
            if reference_transcript is None:
                reference_transcript = transcript
                transcript_digest = digest
            elif transcript != reference_transcript or digest != transcript_digest:
                raise QualificationError(
                    "current and candidate exact output semantics differ"
                )
            header = records[0]
            header_identity = {
                key: header[key]
                for key in (
                    "algorithm",
                    "executable_sha256",
                    "prime_roster_sha256",
                    "persistent_device_allocation_bytes",
                )
            }
            all_headers_sha256[variant].add(_digest(header_identity))
            if variant not in reference_headers:
                reference_headers[variant] = header
                reference_receipts[variant] = [
                    record["leaf_sha256"] for record in records[1:-1]
                ]
            elif [
                record["leaf_sha256"] for record in records[1:-1]
            ] != reference_receipts[variant]:
                raise QualificationError(
                    f"{variant} receipt chain is nondeterministic"
                )
            timings[variant].append(timing)

        if (
            len(all_headers_sha256["current"]) != 1
            or len(all_headers_sha256["candidate"]) != 1
        ):
            raise QualificationError("paired allocation/identity header drifted")
        if reference_receipts["current"] == reference_receipts["candidate"]:
            raise QualificationError("qualification receipt domain collided")
        if reference_transcript is None or transcript_digest is None:
            raise QualificationError("paired benchmark emitted no transcript")

        allocation = _allocation_report(
            reference_headers["current"], reference_headers["candidate"]
        )
        summary_count = _summary_count(arguments.count)
        p13_events = _multiple_count(lower, arguments.count, 13)
        if summary_count <= 256 or p13_events <= EVENTS_PER_BLOCK:
            raise QualificationError(
                "bounded corpus missed a required affine/event crossover"
            )

        current_summary = _summaries(timings["current"])
        candidate_summary = _summaries(timings["candidate"])
        current_device = float(current_summary["device_work_median_ms"])
        candidate_device = float(candidate_summary["device_work_median_ms"])
        performance_eligible = (
            arguments.mode == "azure-h100-benchmark"
            and device["target_h100_measured"] is True
            and runtime_matches_strict
            and arguments.repeats >= 5
            and arguments.count == MAXIMUM_LEAF_ROWS
        )
        report: dict[str, Any] = {
            "schema": SCHEMA,
            "accepted": True,
            "classification": CLASSIFICATION,
            "mode": arguments.mode,
            "workload": {
                "lower": lower,
                "upper_exclusive": lower + arguments.count,
                "count": arguments.count,
                "shard_rows": arguments.count,
                "super_shard_rows": arguments.count,
                "incoming_mertens": 0,
                "incoming_squarefree": 0,
                "previous_leaf_sha256": NONROOT_DIGEST,
                "prime_roster_sha256": SOURCE_ROSTER_SHA256,
                "affine_summary_count": summary_count,
                "crosses_256_summary_boundary": True,
                "p13_multiple_count": p13_events,
                "p13_second_event_block_exercised": True,
                "events_per_block": EVENTS_PER_BLOCK,
            },
            "identities": {
                "source_manifest_sha256": source_before["sha256"],
                "source_files": source_before["files"],
                "runtime_original_sha256": runtime_digest,
                "execution_image_sha256": _sha256_file(execution_image),
                "strict_h100_executable_sha256": strict_digest,
                "same_execution_image_both_variants": True,
                "runtime_matches_strict_h100_executable": runtime_matches_strict,
                "current_algorithm": PRODUCTION_ALGORITHM,
                "production_leaf_domain": PRODUCTION_LEAF_DOMAIN,
                "candidate_algorithm": CANDIDATE_ALGORITHM,
                "candidate_leaf_domain": CANDIDATE_LEAF_DOMAIN,
            },
            "build_evidence": {
                "strict_build_invoked": True,
                "runtime_build_invoked": True,
                "strict": strict_identity,
                "runtime": runtime_identity,
                "tools": tools,
            },
            "cuda_resources": {
                "strict_sm90_cubin_only": strict_resources[
                    "sm90_cubin_only"
                ],
                "strict_resource_usage_sha256": strict_resources[
                    "resource_usage_sha256"
                ],
                "strict_cubin_names_sha256": strict_resources[
                    "cubin_names_sha256"
                ],
                "current": strict_resources["roles"]["current"],
                "candidate": strict_resources["roles"]["candidate"],
                "shared": strict_resources["roles"]["shared"],
                "gate": strict_resources["gate"],
                "resource_gate_passed": True,
            },
            "allocation": allocation,
            "semantic_equivalence": {
                "compared_leaf_fields": list(LEAF_SEMANTIC_FIELDS),
                "compared_terminal_fields": list(
                    TERMINAL_SEMANTIC_FIELDS
                ),
                "leaf_count": len(reference_transcript["leaves"]),
                "current_transcript_sha256": transcript_digest,
                "candidate_transcript_sha256": transcript_digest,
                "exact_output_semantics_equal": True,
                "four_residual_projection": {
                    "mertens_hurst": {
                        "lower": reference_transcript["terminal"][
                            "global_hurst_lower"
                        ],
                        "upper": reference_transcript["terminal"][
                            "global_hurst_upper"
                        ],
                    },
                    "squarefree_cdem": {
                        "lower": reference_transcript["terminal"][
                            "global_squarefree_lower"
                        ],
                        "upper": reference_transcript["terminal"][
                            "global_squarefree_upper"
                        ],
                    },
                    "little_mertens_lower_delta": reference_transcript[
                        "terminal"
                    ]["little_mertens_lower_delta"],
                    "little_mertens_upper_delta": reference_transcript[
                        "terminal"
                    ]["little_mertens_upper_delta"],
                },
                "receipt_domains_distinct": True,
                "receipt_digests_distinct": True,
            },
            "alternating_benchmark": {
                "repetitions": arguments.repeats,
                "schedule": flat_schedule,
                "current": current_summary,
                "candidate": candidate_summary,
                "current_over_candidate_device_work_ratio": _decimal(
                    current_device / candidate_device
                    if candidate_device != 0
                    else math.inf
                ),
                "measured_not_projected": True,
            },
            "runtime_device": device,
            "runtime_instrumentation": {
                "status": "not-inspected-by-paired-runner",
                "sanitizer_evidence_bound_to_report": False,
            },
            "claims": {
                "candidate_selected_in_production": False,
                "production_identity_changed": False,
                "default_behavior_changed": False,
                "production_receipt_identity_changed": False,
                "production_theorem_identity_changed": False,
                "execution_attested": False,
                "compiler_refinement_proved": False,
                "cuda_to_lean_refinement_proved": False,
                "source_range_evidence": False,
                "proves_any_external_atom": False,
                "projection_used": False,
                "performance_evidence_eligible": performance_eligible,
            },
        }
        source_final = _source_manifest()
        if source_final != source_before:
            raise QualificationError("source manifest changed during benchmark")
        if _sha256_file(roster) != SOURCE_ROSTER_SHA256:
            raise QualificationError("prime roster changed during benchmark")
        validate_report(report)
        return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    raw = canonical_json_bytes(report)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise QualificationError("short qualification-report write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if path.read_bytes() != raw:
        raise QualificationError("qualification-report readback differs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--runtime-build-dir", type=Path, required=True)
    parser.add_argument("--strict-h100-runner", type=Path, required=True)
    parser.add_argument("--strict-build-dir", type=Path, required=True)
    parser.add_argument("--prime-roster", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("bounded", "azure-h100-benchmark"),
        default="bounded",
    )
    parser.add_argument("--strict-h100-runtime", action="store_true")
    parser.add_argument("--lower", type=int)
    parser.add_argument("--count", type=int, default=MINIMUM_CROSSOVER_ROWS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run-timeout", type=int, default=900)
    parser.add_argument("--build-timeout", type=int, default=1_800)
    parser.add_argument(
        "--nvcc", type=Path, default=Path("/usr/local/cuda/bin/nvcc")
    )
    parser.add_argument(
        "--cuobjdump",
        type=Path,
        default=Path("/usr/local/cuda/bin/cuobjdump"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if arguments.repeats <= 0:
        raise QualificationError("--repeats must be positive")
    report = qualify(arguments)
    if arguments.output is not None:
        _write_report(arguments.output, report)
    if arguments.pretty:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.buffer.write(canonical_json_bytes(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QualificationError as error:
        print(f"qualification rejected: {error}", file=sys.stderr)
        raise SystemExit(1)

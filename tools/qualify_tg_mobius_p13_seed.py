#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed paired p11-versus-p13 Möbius/Hurst qualification.

Both variants use the qualification-only ordered affine block composer.  The
only changed arithmetic is whether p=13 is processed as a divisor/square
event stream or derived per row from n modulo 169.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import qualify_tg_mobius_hurst_combined as common


SCHEMA = "sparkinterval.tg.mobius-p13-seed-qualification.v1"
CLASSIFICATION = (
    "qualification_only_p11_vs_p13_residue_seed_with_affine_block_compose_"
    "not_source_evidence_attestation_compiler_refinement_or_lean_proof"
)
SOURCE_LIMIT = common.SOURCE_LIMIT
MAXIMUM_LEAF_ROWS = common.MAXIMUM_LEAF_ROWS
MINIMUM_ROWS = max(
    common.MINIMUM_CROSSOVER_ROWS,
    17 * common.EVENTS_PER_BLOCK + 1,
)
P11_ALGORITHM = common.CANDIDATE_ALGORITHM
P11_LEAF_DOMAIN = common.CANDIDATE_LEAF_DOMAIN
P13_ALGORITHM = (
    "tg_mobius_fused_affine_persistent_residue_23571113_block_compose_"
    "rpt256_rpb65536_qualification_v1"
)
P13_LEAF_DOMAIN = (
    "sparkinterval.tg.mobius-persistent-residue-23571113-affine-"
    "block-compose-rpt256-rpb65536-qualification-leaf.v1"
)
SOURCE_FILES = tuple(
    dict.fromkeys(
        common.SOURCE_FILES
        + (
            "SparkInterval/TernaryGoldbach/MobiusResidue23571113.lean",
            "SparkInterval/Tests/MobiusResidue23571113Test.lean",
            "tests/tg_mobius_residue23571113_known_answers.cpp",
            "tools/qualify_tg_mobius_p13_seed.py",
        )
    )
)
RESOURCE_PATTERNS: Mapping[str, str] = {
    "roster_preflight": "validate_split_square_mobius_rosterE",
    "dense_distinct_divisor": (
        "mark_dense_prime_fused_distinct_divisors_multiblockILm512EEE"
    ),
    "sparse_distinct_divisor": "mark_sparse_prime_fused_distinct_divisorsE",
    "dense_square_strike": "mark_dense_prime_fused_squarefulE",
    "sparse_square_strike": "mark_sparse_prime_fused_squarefulE",
    "p11_initializer": (
        "initialize_fused_mobius_support_residue_235ILb1ELb1ELb0EEE"
    ),
    "p13_initializer": (
        "initialize_fused_mobius_support_residue_235ILb1ELb1ELb1EEE"
    ),
    "block_summaries": "affine_mq_block_summaries_from_fused_supportsE",
    "ordered_block_compose": "affine_mq_compose_block_summariesE",
}


class QualificationError(common.QualificationError):
    """The p13 paired qualification failed closed."""


def _source_manifest() -> dict[str, Any]:
    files = []
    for relative in SOURCE_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise QualificationError(f"required source is absent: {relative}")
        files.append({"path": relative, "sha256": common._sha256_file(path)})
    return {"files": files, "sha256": common._digest(files)}


def _resource_evidence(executable: Path, cuobjdump: Path) -> dict[str, Any]:
    listed = common._run(
        [str(cuobjdump.resolve()), "--list-elf", str(executable.resolve())]
    )
    cubins = re.findall(
        r"(\S+\.sm_([0-9]+)\.cubin)",
        listed.stdout.decode("utf-8", errors="strict"),
    )
    if not cubins or {arch for _name, arch in cubins} != {"90"}:
        raise QualificationError("not every cubin in the target is sm90")
    listed_ptx = common._run(
        [str(cuobjdump.resolve()), "--list-ptx", str(executable.resolve())]
    )
    ptx_names = re.findall(
        r"PTX file\s+\d+:\s+(\S+\.ptx)",
        listed_ptx.stdout.decode("utf-8", errors="strict"),
    )
    usage = common._run(
        [
            str(cuobjdump.resolve()),
            "--dump-resource-usage",
            str(executable.resolve()),
        ]
    )
    raw = usage.stdout + usage.stderr
    if set(re.findall(rb"arch = (sm_[0-9]+)", raw)) != {b"sm_90"}:
        raise QualificationError("resource image contains non-sm90 code")
    pattern = re.compile(
        r"^ Function (.+):\n"
        r"^\s+REG:(\d+) STACK:(\d+) SHARED:(\d+) LOCAL:(\d+) "
        r"CONSTANT\[0\]:(\d+)",
        re.MULTILINE,
    )
    functions = [
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
        for match in pattern.finditer(raw.decode("utf-8", errors="strict"))
    ]
    roles = {}
    for role, needle in RESOURCE_PATTERNS.items():
        matches = [resource for name, resource in functions if needle in name]
        if len(matches) != 1:
            raise QualificationError(
                f"strict resource role {role!r} matched {len(matches)} kernels"
            )
        roles[role] = matches[0]
    for role, resource in roles.items():
        if (
            resource["registers_per_thread"] > 64
            or resource["stack_bytes_per_thread"] > 64
            or resource["shared_bytes_per_block"] > 227_328
            or resource["local_bytes_per_thread"] != 0
        ):
            raise QualificationError(f"resource role {role!r} exceeds gate")
    return {
        "all_cubins_sm90": True,
        "cubin_names_sha256": common._digest(
            sorted(name for name, _arch in cubins)
        ),
        "ptx_fallback_present": bool(ptx_names),
        "ptx_names_sha256": common._digest(sorted(ptx_names)),
        "ptx_absence_required": False,
        "resource_usage_sha256": common._sha256_bytes(raw),
        "roles": roles,
        "gate": {
            "accepted": True,
            "maximum_registers_per_thread": 64,
            "maximum_stack_bytes_per_thread": 64,
            "maximum_shared_bytes_per_block": 227_328,
            "required_local_bytes_per_thread": 0,
        },
    }


def _assert_false_claims(record: Mapping[str, Any]) -> None:
    for field in (
        "execution_attested",
        "cuda_or_cpp_compiler_refinement_proved",
        "lean_atom_discharged",
        "proves_any_external_atom",
    ):
        if record.get(field) is not False:
            raise QualificationError(f"runner did not keep {field} false")


def _validate_records(
    records: list[dict[str, Any]],
    *,
    variant: str,
    executable_sha256: str,
) -> None:
    header = records[0]
    terminal = records[-1]
    expected_algorithm = P11_ALGORITHM if variant == "p11" else P13_ALGORITHM
    expected_domain = P11_LEAF_DOMAIN if variant == "p11" else P13_LEAF_DOMAIN
    expected_count = 5 if variant == "p11" else 6
    if (
        header.get("algorithm") != expected_algorithm
        or terminal.get("algorithm") != expected_algorithm
        or header.get("receipt_leaf_domain") != expected_domain
        or header.get("executable_sha256") != executable_sha256
        or header.get("prime_roster_sha256")
        != common.SOURCE_ROSTER_SHA256
        or header.get("qualification_only_not_production_admissible")
        is not True
        or header.get("qualification_affine_block_compose") is not True
        or header.get(
            "qualification_direct_fused_support_block_compose_path"
        )
        is not True
        or header.get("residue_seed_prime_count") != expected_count
        or header.get("affine_workspace_device_bytes") != 0
        or header.get("cuda_allocation_epoch_count") != 1
    ):
        raise QualificationError(f"{variant} identity/path fields differ")
    if variant == "p11":
        if (
            header.get("qualification_residue_235711_seed") is not True
            or "qualification_residue_23571113_seed" in header
        ):
            raise QualificationError("p11 seed identity differs")
    elif variant == "p13":
        if (
            header.get("qualification_residue_23571113_seed") is not True
            or header.get("residue_23571113_per_row_modulus") != 169
            or header.get("residue_23571113_materialized_table_rows") != 0
            or header.get("residue_23571113_suffix_minimum_prime") != 17
            or header.get(
                "fused_multiblock_residue_23571113_minimum_safe_slots_per_prime"
            )
            != 61
            or header.get(
                "qualification_residue_23571113_split_square_support_path"
            )
            is not True
        ):
            raise QualificationError("p13 seed identity/arithmetic differs")
    else:
        raise QualificationError("unknown paired variant")
    _assert_false_claims(header)
    _assert_false_claims(terminal)
    for record in records[1:]:
        if (
            record.get("algorithm") != expected_algorithm
            or record.get("receipt_leaf_domain") != expected_domain
            or record.get("qualification_only_not_production_admissible")
            is not True
        ):
            raise QualificationError(f"{variant} receipt identity leaked")
        _assert_false_claims(record)
        if record.get("record") == "leaf" and record.get("poison_count") != 0:
            raise QualificationError(f"{variant} emitted poisoned rows")


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
    flag = (
        "--qualification-residue-235711-seed"
        if variant == "p11"
        else "--qualification-residue-23571113-seed"
    )
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
        common.NONROOT_DIGEST,
        "--source-prime-roster",
        str(roster.resolve()),
        flag,
        "--qualification-affine-block-compose",
    ]
    if strict_h100_runtime:
        command.extend(["--require-device-class", "nvidia-h100-sm90"])
    else:
        command.append("--allow-other-device")
    started = time.monotonic_ns()
    result = common._run(command, cwd=ROOT, timeout=timeout)
    wall_ms = (time.monotonic_ns() - started) / 1_000_000
    records = common._parse_jsonl(result.stdout)
    _validate_records(
        records,
        variant=variant,
        executable_sha256=common._sha256_file(executable),
    )
    return records, common._timing(records, wall_ms)


def _summary(samples: list[dict[str, str]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in (
        "kernel_ms",
        "affine_ms",
        "device_work_ms",
        "process_ms",
        "wall_ms",
    ):
        values = [float(sample[field]) for sample in samples]
        output[field] = [sample[field] for sample in samples]
        output[field.removesuffix("_ms") + "_median_ms"] = common._decimal(
            statistics.median(values)
        )
    return output


def qualify(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.count < MINIMUM_ROWS or arguments.count > MAXIMUM_LEAF_ROWS:
        raise QualificationError(
            f"--count must lie in [{MINIMUM_ROWS}, {MAXIMUM_LEAF_ROWS}]"
        )
    lower = (
        SOURCE_LIMIT - arguments.count + 1
        if arguments.lower is None
        else arguments.lower
    )
    if lower <= 1_000_000_000_000 or lower + arguments.count - 1 > SOURCE_LIMIT:
        raise QualificationError("range is outside the terminal source domain")
    strict_runtime = arguments.mode == "azure-h100-benchmark"
    if strict_runtime and (
        arguments.count != MAXIMUM_LEAF_ROWS or arguments.repeats < 5
    ):
        raise QualificationError(
            "Azure H100 mode requires 100000000 rows and at least five pairs"
        )
    roster = arguments.prime_roster.resolve()
    if (
        not roster.is_file()
        or common._sha256_file(roster) != common.SOURCE_ROSTER_SHA256
    ):
        raise QualificationError("source prime roster identity differs")

    source_before = _source_manifest()
    runtime_build = arguments.runtime_build_dir.resolve()
    strict_build = arguments.strict_build_dir.resolve()
    runtime_runner = arguments.runner.resolve()
    strict_runner = arguments.strict_h100_runner.resolve()
    common._build_target(
        strict_build, common.STRICT_TARGET, arguments.build_timeout
    )
    strict_identity = common._build_identity(
        strict_build, common.STRICT_TARGET, strict_runner
    )
    common._build_target(
        runtime_build, common.PORTABLE_TARGET, arguments.build_timeout
    )
    runtime_identity = common._build_identity(
        runtime_build, common.PORTABLE_TARGET, runtime_runner
    )
    cuobjdump = Path(arguments.cuobjdump).resolve()
    resources = _resource_evidence(strict_runner, cuobjdump)
    device = common._runtime_device(strict_runtime)
    if strict_runtime and (
        runtime_runner.resolve() != strict_runner.resolve()
        or runtime_identity["executable_sha256"]
        != strict_identity["executable_sha256"]
    ):
        raise QualificationError(
            "Azure mode must execute the exact strict-sm90 image"
        )

    p11_timings: list[dict[str, str]] = []
    p13_timings: list[dict[str, str]] = []
    transcript: dict[str, Any] | None = None
    transcript_sha256 = ""
    p11_leaf_sha256 = ""
    p13_leaf_sha256 = ""
    with tempfile.TemporaryDirectory(prefix="tg-p13-seed-") as temporary:
        execution = Path(temporary) / "mobius-p13-paired"
        execution_sha256 = common._copy_execution_image(
            runtime_runner, execution
        )
        if execution_sha256 != runtime_identity["executable_sha256"]:
            raise QualificationError("execution copy differs from build")
        for repetition in range(arguments.repeats):
            order = ("p11", "p13") if repetition % 2 == 0 else ("p13", "p11")
            for variant in order:
                records, timing = _run_variant(
                    execution,
                    roster,
                    variant=variant,
                    lower=lower,
                    count=arguments.count,
                    strict_h100_runtime=strict_runtime,
                    timeout=arguments.run_timeout,
                )
                current = common._semantic_transcript(records)
                current_digest = common._digest(current)
                if transcript is None:
                    transcript = current
                    transcript_sha256 = current_digest
                elif current != transcript or current_digest != transcript_sha256:
                    raise QualificationError(
                        "p11/p13 exact semantic transcripts differ"
                    )
                leaf = common._digest_string(
                    records[-1].get("final_leaf_sha256"),
                    f"{variant} final leaf",
                )
                if variant == "p11":
                    if p11_leaf_sha256 and leaf != p11_leaf_sha256:
                        raise QualificationError("p11 receipt is nondeterministic")
                    p11_leaf_sha256 = leaf
                    p11_timings.append(timing)
                else:
                    if p13_leaf_sha256 and leaf != p13_leaf_sha256:
                        raise QualificationError("p13 receipt is nondeterministic")
                    p13_leaf_sha256 = leaf
                    p13_timings.append(timing)
    if (
        transcript is None
        or len(p11_timings) != arguments.repeats
        or len(p13_timings) != arguments.repeats
        or p11_leaf_sha256 == p13_leaf_sha256
    ):
        raise QualificationError("paired execution was incomplete or unisolated")
    p11_summary = _summary(p11_timings)
    p13_summary = _summary(p13_timings)
    p11_device = float(p11_summary["device_work_median_ms"])
    p13_device = float(p13_summary["device_work_median_ms"])
    if not (p11_device > 0 and p13_device > 0 and p13_device < p11_device):
        raise QualificationError("p13 did not improve median device work")

    source_after = _source_manifest()
    if source_after != source_before:
        raise QualificationError("source changed during qualification")
    if common._build_identity(
        runtime_build, common.PORTABLE_TARGET, runtime_runner
    ) != runtime_identity:
        raise QualificationError("runtime build changed during qualification")
    if common._build_identity(
        strict_build, common.STRICT_TARGET, strict_runner
    ) != strict_identity:
        raise QualificationError("strict build changed during qualification")

    ratio = p11_device / p13_device
    report = {
        "schema": SCHEMA,
        "accepted": True,
        "classification": CLASSIFICATION,
        "mode": arguments.mode,
        "workload": {
            "lower": lower,
            "upper_exclusive": lower + arguments.count,
            "count": arguments.count,
            "repeats": arguments.repeats,
            "p17_multiple_count": common._multiple_count(
                lower, arguments.count, 17
            ),
            "p17_second_event_block_live": common._multiple_count(
                lower, arguments.count, 17
            )
            > common.EVENTS_PER_BLOCK,
            "partial_final_cuda_block": arguments.count % 256 != 0,
        },
        "semantic_transcript_sha256": transcript_sha256,
        "receipt_identity": {
            "p11_algorithm": P11_ALGORITHM,
            "p11_leaf_domain": P11_LEAF_DOMAIN,
            "p11_final_leaf_sha256": p11_leaf_sha256,
            "p13_algorithm": P13_ALGORITHM,
            "p13_leaf_domain": P13_LEAF_DOMAIN,
            "p13_final_leaf_sha256": p13_leaf_sha256,
            "domains_and_receipts_distinct": True,
        },
        "timing": {
            "p11": p11_summary,
            "p13": p13_summary,
            "p11_over_p13_median_device_work_ratio": common._decimal(ratio),
            "p13_median_device_work_reduction_fraction": common._decimal(
                1.0 - 1.0 / ratio
            ),
            "target_h100_measured": device["target_h100_measured"],
            "performance_evidence_eligible": (
                strict_runtime
                and device["target_h100_measured"]
                and arguments.count == MAXIMUM_LEAF_ROWS
                and arguments.repeats >= 5
            ),
        },
        "device": device,
        "source_manifest": source_before,
        "runtime_build": runtime_identity,
        "strict_sm90_build": strict_identity,
        "strict_sm90_resources": resources,
        "toolchain": {
            "nvcc": common._tool_identity(
                Path(arguments.nvcc).resolve(), "--version"
            ),
            "cuobjdump": common._tool_identity(cuobjdump, "--version"),
        },
        "production_default_changed": False,
        "production_algorithm_identity_changed": False,
        "production_receipt_domain_changed": False,
        "source_rows_replayed_independently": False,
        "full_source_range": False,
        "execution_attested": False,
        "cuda_or_cpp_compiler_refinement_proved": False,
        "cuda_to_lean_refinement_proved": False,
        "lean_atom_discharged": False,
        "proves_any_external_atom": False,
    }
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path = path.resolve()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        raw = common.canonical_json_bytes(report)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise QualificationError("short report write")
            view = view[written:]
        os.write(descriptor, b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--runtime-build-dir", type=Path, required=True)
    parser.add_argument("--strict-h100-runner", type=Path, required=True)
    parser.add_argument("--strict-build-dir", type=Path, required=True)
    parser.add_argument("--prime-roster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lower", type=int)
    parser.add_argument("--count", type=int, default=MINIMUM_ROWS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--mode",
        choices=("bounded-local", "azure-h100-benchmark"),
        default="bounded-local",
    )
    parser.add_argument("--nvcc", default="/usr/local/cuda/bin/nvcc")
    parser.add_argument("--cuobjdump", default="/usr/local/cuda/bin/cuobjdump")
    parser.add_argument("--build-timeout", type=int, default=1_800)
    parser.add_argument("--run-timeout", type=int, default=1_800)
    return parser


def main() -> int:
    parser = _parser()
    arguments = parser.parse_args()
    if arguments.repeats <= 0:
        parser.error("--repeats must be positive")
    try:
        report = qualify(arguments)
        _write_report(arguments.output, report)
    except (QualificationError, common.QualificationError, OSError) as exc:
        print(f"p13 qualification failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"accepted p13 paired qualification: "
        f"{report['semantic_transcript_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

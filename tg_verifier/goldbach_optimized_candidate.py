# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Qualification package for the unpromoted optimized GoldbachGPU source.

The package produced here is deliberately narrower than a production
registration.  It gives a reviewer reproducible source, host executable, PTX,
cubin, SASS, compiler-resource, lexical-audit, and bounded differential pins.
It does not authenticate a run, establish source-scale coverage, or discharge
a Lean atom.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence

from .campaign_io import canonical_json_bytes
from .goldbach_gpu_campaign import (
    GoldbachGPUCampaignError,
    make_bounded_sample_plan,
    parse_runner_stdout,
    runner_arguments,
    verify_hardened_source_tree,
)
from .goldbach_optimized_source import (
    ALGORITHM_CANDIDATE_ID,
    COFACTOR_FILTER_LIMIT,
    EXPECTED_GOLDBACH_SOURCE_BYTES,
    EXPECTED_GOLDBACH_SOURCE_SHA256,
    EXPECTED_SOURCE_IDENTITY_SHA256,
    WARP_PARALLEL_CUTOFF,
    prepare_optimized_source,
)
from .goldbach_shifted_coverage_optimizer import (
    rewrite_packed_count_crosscheck,
    rewrite_shifted_phase1_crosscheck,
)
from .goldbach_warp_tail_optimizer import rewrite_warp_parallel_tail
from .goldbach_wheel_filtered_tail_optimizer import (
    rewrite_wheel_filtered_sieve_crosscheck,
)


MANIFEST_KIND = "sparkinterval.goldbach-optimized-candidate-package.v1"
PTX_AUDIT_KIND = "sparkinterval.goldbach-optimized-sm90-ptx-audit.v1"
SASS_AUDIT_KIND = "sparkinterval.goldbach-optimized-sm90-sass-audit.v1"
COMPONENT_KAT_KIND = (
    "sparkinterval.goldbach-optimized-component-kat-report.v1"
)
DIFFERENTIAL_KIND = (
    "sparkinterval.goldbach-optimized-bounded-full-differential.v1"
)
QUALIFICATION_CLASSIFICATION = (
    "reproducible-bounded-candidate-qualification-not-production-evidence"
)
EXPECTED_CROSSCHECK_SOURCE_SHA256 = (
    "7baa018b8e9d2a724c7808c2c5aaca4c98024d673baa3bb0104094c66ac33c67"
)
EXPECTED_CROSSCHECK_SOURCE_BYTES = 80_762
DEFAULT_BOUNDED_EVEN_START = 31_249_998_800_000_002
DEFAULT_BOUNDED_EVEN_LIMIT = 31_250_000_000_000_000
MAX_BOUNDED_EVEN_COUNT = 600_000_000
TARGET_ARCH = "sm_90"
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
_MANIFEST_DOMAIN = b"sparkinterval/tg/goldbach-optimized-candidate/v1\x00"
_CLOSURE_DOMAIN = b"sparkinterval/tg/goldbach-optimized-closure/v1\x00"
_ROOT = Path(__file__).resolve().parents[1]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARCH_RE = re.compile(r"^(?:native|sm_[0-9]{2,3})$")
_COMPUTE_CAPABILITY_RE = re.compile(r"^[0-9]{1,2}\.[0-9]$")

# A candidate manifest is self-describing qualification evidence, not an
# authority.  Production use additionally requires the SHA-256 of the exact
# canonical manifest file to appear in this source-reviewed allowlist.  It is
# intentionally empty until an Azure x86_64 build has been independently
# reviewed.
REVIEWED_PRODUCTION_CANDIDATE_MANIFEST_FILE_SHA256S: frozenset[str] = (
    frozenset()
)

_KERNELS = {
    "byte_count": "_Z23count_unverified_kernelPKhmPj",
    "word_owner": "_Z35initialize_small_prime_words_kernelmmPm",
    "warp_sieve": "_Z35sieve_segment_warp_per_prime_kernelmmPKmmPm",
    "tail_sieve": "_Z20sieve_segment_kernelmmPKmmPm",
    "shifted_coverage": "_Z33shifted_or_phase1_coverage_kernelPKmS0_mmmPm",
    "coverage_expand": "_Z28expand_coverage_words_kernelPKmmPh",
    "packed_count": "_Z37count_uncovered_coverage_words_kernelPKmmmPj",
    "fallback_phase1": "_Z22goldbach_phase1_kernelPKmmS0_mmmmS0_mPh",
}

_COMPONENT_KATS: dict[str, dict[str, object]] = {
    "warp_tail": {
        "result_without_compute_capability": {
            "accepted": True,
            "kind": "sparkinterval.goldbach-warp-tail-kat.v1",
            "odd_count_per_window": 262_144,
            "prime_limit": 131_071,
            "tail_prime_count": 11_942,
            "warp_parallel_cutoff": 32_749,
            "warp_prime_count": 3_203,
            "window_count": 4,
            "windows": [
                {
                    "fnv1a64": "f6de1f3dc27d92d0",
                    "q_high": "4524287",
                    "q_low": "4000001",
                    "set_bits": 261_710,
                },
                {
                    "fnv1a64": "104dc6a2ad9c6f2b",
                    "q_high": "4680287",
                    "q_low": "4156001",
                    "set_bits": 261_185,
                },
                {
                    "fnv1a64": "d7047e183062e116",
                    "q_high": "31249998799524289",
                    "q_low": "31249998799000003",
                    "set_bits": 169_886,
                },
                {
                    "fnv1a64": "29c5483addcced4f",
                    "q_high": "18446744073709551615",
                    "q_low": "18446744073709027329",
                    "set_bits": 170_274,
                },
            ],
            "word_owner_cutoff": 2_039,
        },
        "source_path": (
            _ROOT
            / "gpu/platform/h100/h100_tg_goldbach_warp_tail_kat.cu"
        ),
        "source_sha256": (
            "eab8912b27de71969b35d85eedabe5b08fa93d0208ed1b12e66a516c2f827d7e"
        ),
        "source_size_bytes": 12_906,
    },
    "wheel_filter": {
        "result_without_compute_capability": {
            "accepted": True,
            "cofactor_filter_limit": 47,
            "kind": "sparkinterval.goldbach-wheel-filter-kat.v1",
            "odd_count_per_window": 262_144,
            "prime_limit": 131_071,
            "tail_prime_count": 11_942,
            "warp_parallel_cutoff": 32_749,
            "warp_prime_count": 3_203,
            "wheel_modulus": 15_015,
            "window_count": 4,
            "windows": [
                {
                    "fnv1a64": "c5a02e2b2bb2b0d0",
                    "q_high": "4524287",
                    "q_low": "4000001",
                    "set_bits": 72_597,
                },
                {
                    "fnv1a64": "869bd81a9a1827a4",
                    "q_high": "4680287",
                    "q_low": "4156001",
                    "set_bits": 72_479,
                },
                {
                    "fnv1a64": "bb99908cdab9d2e6",
                    "q_high": "31249998799524289",
                    "q_low": "31249998799000003",
                    "set_bits": 47_131,
                },
                {
                    "fnv1a64": "ac6c9b891d576bbb",
                    "q_high": "18446744073709551615",
                    "q_low": "18446744073709027329",
                    "set_bits": 47_130,
                },
            ],
            "word_owner_cutoff": 2_039,
        },
        "source_path": (
            _ROOT
            / "gpu/platform/h100/h100_tg_goldbach_wheel_filter_kat.cu"
        ),
        "source_sha256": (
            "cd9d07cf8d62fe43cac0e14050cd0a50a44f4a704301428a04df049b0330bf22"
        ),
        "source_size_bytes": 14_465,
    },
}


class GoldbachOptimizedCandidateError(RuntimeError):
    """A candidate package, compiler artifact, or bounded check failed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _pin(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise GoldbachOptimizedCandidateError(
            f"candidate artifact is linked or nonregular: {path}"
        )
    return {"sha256": _sha256(path), "size_bytes": metadata.st_size}


def _validate_host_executable(path: Path, host_architecture: str) -> None:
    """Reject scripts and an ELF whose basic architecture does not match."""

    metadata = path.lstat()
    if metadata.st_mode & 0o111 == 0:
        raise GoldbachOptimizedCandidateError(
            "candidate host executable has no executable mode bit"
        )
    try:
        with path.open("rb") as source:
            header = source.read(64)
    except OSError as error:
        raise GoldbachOptimizedCandidateError(
            "cannot read candidate host executable"
        ) from error
    expected_machine = {"x86_64": 62, "aarch64": 183}.get(
        host_architecture
    )
    if expected_machine is None:
        raise GoldbachOptimizedCandidateError(
            "candidate host architecture differs"
        )
    if (
        len(header) < 20
        or header[:4] != b"\x7fELF"
        or header[4] != 2  # ELFCLASS64
        or header[5] != 1  # ELFDATA2LSB
        or header[6] != 1  # EV_CURRENT
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate host executable is not a 64-bit little-endian ELF"
        )
    elf_type, machine = struct.unpack_from("<HH", header, 16)
    if elf_type not in {2, 3}:  # ET_EXEC or ET_DYN (PIE)
        raise GoldbachOptimizedCandidateError(
            "candidate host ELF is not an executable or PIE"
        )
    if machine != expected_machine:
        raise GoldbachOptimizedCandidateError(
            "candidate host ELF architecture differs from its manifest"
        )


def _safe_text(raw: bytes, what: str) -> str:
    if len(raw) > MAX_CAPTURE_BYTES:
        raise GoldbachOptimizedCandidateError(f"{what} exceeds capture limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GoldbachOptimizedCandidateError(
            f"{what} is not UTF-8"
        ) from error


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.SubprocessError as error:
        raise GoldbachOptimizedCandidateError(
            f"candidate command did not complete: {argv[0]}"
        ) from error
    if completed.returncode != 0:
        detail = _safe_text(
            completed.stderr or completed.stdout, "failed command output"
        ).strip()
        raise GoldbachOptimizedCandidateError(
            f"candidate command failed with status {completed.returncode}: "
            f"{detail}"
        )
    return completed


def _build_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/local/cuda/bin:/usr/bin:/bin",
        "SOURCE_DATE_EPOCH": "0",
        "TZ": "UTC",
    }


def _host_flags() -> str:
    machine = platform.machine()
    if machine == "x86_64":
        return "-O3,-march=x86-64-v2,-mtune=generic,-fopenmp"
    if machine in {"aarch64", "arm64"}:
        return "-O3,-march=armv8-a,-mtune=generic,-fopenmp"
    raise GoldbachOptimizedCandidateError(
        f"unsupported candidate host architecture: {machine}"
    )


def _tool(path: Path, version_argv: Sequence[str]) -> dict[str, object]:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GoldbachOptimizedCandidateError(
            f"candidate tool is absent: {path}"
        ) from error
    pin = _pin(resolved)
    completed = _run(
        [str(resolved), *version_argv],
        cwd=_ROOT,
        environment=_build_environment(),
        timeout=30,
    )
    version = _safe_text(
        completed.stdout + completed.stderr, f"{resolved.name} version"
    ).strip()
    if not version:
        raise GoldbachOptimizedCandidateError(
            f"{resolved.name} version is empty"
        )
    return {
        **pin,
        "resolved_path": str(resolved),
        "version": version,
    }


def crosscheck_goldbach_source(source: str) -> str:
    """Generate the independent all-live-word diagnostic source exactly."""

    transformed = rewrite_warp_parallel_tail(
        source, WARP_PARALLEL_CUTOFF
    )
    transformed = rewrite_shifted_phase1_crosscheck(transformed)
    transformed = rewrite_packed_count_crosscheck(transformed)
    transformed = rewrite_wheel_filtered_sieve_crosscheck(
        transformed, COFACTOR_FILTER_LIMIT
    )
    encoded = transformed.encode("utf-8")
    if (
        len(encoded) != EXPECTED_CROSSCHECK_SOURCE_BYTES
        or hashlib.sha256(encoded).hexdigest()
        != EXPECTED_CROSSCHECK_SOURCE_SHA256
    ):
        raise GoldbachOptimizedCandidateError(
            "generated full-differential source identity differs"
        )
    return transformed


def _write_crosscheck_tree(
    hardened_source_root: Path, destination: Path
) -> dict[str, object]:
    verify_hardened_source_tree(hardened_source_root)
    shutil.copytree(hardened_source_root, destination, symlinks=False)
    source_path = destination / "src/goldbach.cu"
    source_path.write_text(
        crosscheck_goldbach_source(
            source_path.read_text(encoding="utf-8")
        ),
        encoding="utf-8",
        newline="",
    )
    return {
        "goldbach_source_sha256": _sha256(source_path),
        "goldbach_source_size_bytes": source_path.stat().st_size,
    }


def _parse_ptx_blocks(text: str) -> dict[str, str]:
    matches = list(
        re.finditer(r"(?m)^\.visible\s+\.entry\s+(\S+)\(", text)
    )
    names = [match.group(1) for match in matches]
    if len(names) != len(set(names)):
        raise GoldbachOptimizedCandidateError(
            "candidate PTX contains a duplicate entry symbol"
        )
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[match.group(1)] = text[match.start():stop]
    return blocks


def audit_sm90_ptx(path: Path) -> dict[str, object]:
    """Perform a strict candidate-specific lexical PTX audit."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GoldbachOptimizedCandidateError(
            "cannot read retained candidate PTX"
        ) from error
    if text.count(".version 9.0") != 1 or text.count(".target sm_90") != 1:
        raise GoldbachOptimizedCandidateError(
            "candidate PTX is not uniquely PTX 9.0 for sm_90"
        )
    blocks = _parse_ptx_blocks(text)
    expected = set(_KERNELS.values())
    if set(blocks) != expected:
        raise GoldbachOptimizedCandidateError(
            "candidate PTX entry set differs from the reviewed eight kernels"
        )

    warp = blocks[_KERNELS["warp_sieve"]]
    tail = blocks[_KERNELS["tail_sieve"]]
    shifted = blocks[_KERNELS["shifted_coverage"]]
    packed = blocks[_KERNELS["packed_count"]]
    byte_count = blocks[_KERNELS["byte_count"]]
    if (
        warp.count("atom.global.and.b64") != 1
        or tail.count("atom.global.and.b64") != 1
        or shifted.count("atom.") != 0
        or packed.count("popc.b64") != 1
        or packed.count("atom.global.add.u32") != 1
        or byte_count.count("atom.global.add.u32") != 1
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate PTX atomic/popcount kernel partition differs"
        )
    if (
        text.count("atom.global.and.b64") != 2
        or text.count("atom.global.add.u32") != 2
        or "atom.global.and.b32" in text
        or "atom.global.cas" in text
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate PTX global atomic vocabulary differs"
        )
    if (
        shifted.count("ld.global.nc.u64") != 3
        or shifted.count("st.global.u64") != 1
        or shifted.count("or.b64") != 2
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate shifted-word PTX data path differs"
        )
    return {
        "accepted": True,
        "artifact": {"path": path.name, **_pin(path)},
        "classification": "strict-lexical-audit-not-ptx-operational-semantics",
        "entry_count": len(blocks),
        "entry_symbols": sorted(blocks),
        "global_atomic_counts": {
            "add_u32": text.count("atom.global.add.u32"),
            "and_b64": text.count("atom.global.and.b64"),
        },
        "kind": PTX_AUDIT_KIND,
        "packed_count_popc_b64_count": packed.count("popc.b64"),
        "shifted_coverage": {
            "atomic_count": shifted.count("atom."),
            "global_u64_load_count": shifted.count("ld.global.nc.u64"),
            "global_u64_store_count": shifted.count("st.global.u64"),
            "or_b64_count": shifted.count("or.b64"),
        },
        "target": TARGET_ARCH,
        "trust_limit": (
            "lexical shape only; no compiler, SASS, driver, hardware, or "
            "source-refinement theorem"
        ),
    }


def _sass_block(text: str, symbol: str) -> str:
    marker = f"//--------------------- .text.{symbol} "
    start = text.find(marker)
    if start < 0:
        raise GoldbachOptimizedCandidateError(
            f"candidate SASS omits kernel section {symbol}"
        )
    stop = text.find("//--------------------- .text.", start + len(marker))
    return text[start:stop if stop >= 0 else len(text)]


def audit_sm90_sass(path: Path) -> dict[str, object]:
    """Perform a strict candidate-specific lexical SASS audit."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GoldbachOptimizedCandidateError(
            "cannot read retained candidate SASS"
        ) from error
    if text.count(".target\tsm_90") != 1:
        raise GoldbachOptimizedCandidateError(
            "candidate SASS is not uniquely targeted at sm_90"
        )
    section_symbols = re.findall(
        r"(?m)^//--------------------- \.text\.(\S+) ", text
    )
    if (
        len(section_symbols) != len(set(section_symbols))
        or set(section_symbols) != set(_KERNELS.values())
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate SASS text-section set differs from the reviewed kernels"
        )
    blocks = {name: _sass_block(text, symbol) for name, symbol in _KERNELS.items()}
    if (
        blocks["warp_sieve"].count("REDG.E.AND.64.STRONG.GPU") != 1
        or blocks["tail_sieve"].count("REDG.E.AND.64.STRONG.GPU") != 1
        or blocks["packed_count"].count("REDG.E.ADD.STRONG.GPU") != 1
        or blocks["byte_count"].count("REDG.E.ADD.STRONG.GPU") != 1
        or blocks["packed_count"].count("POPC ") != 2
        or blocks["byte_count"].count("POPC ") != 1
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate SASS reduction/popcount partition differs"
        )
    if (
        text.count("REDG.E.AND.64.STRONG.GPU") != 2
        or text.count("REDG.E.ADD.STRONG.GPU") != 2
        or re.search(r"\b(?:ATOM|REDG)\S*\.AND\.32\b", text) is not None
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate SASS global reduction vocabulary differs"
        )
    return {
        "accepted": True,
        "artifact": {"path": path.name, **_pin(path)},
        "classification": "strict-lexical-audit-not-sass-operational-semantics",
        "global_reduction_counts": {
            "add_strong_gpu": text.count("REDG.E.ADD.STRONG.GPU"),
            "and64_strong_gpu": text.count(
                "REDG.E.AND.64.STRONG.GPU"
            ),
        },
        "kernel_sections": sorted(_KERNELS.values()),
        "kind": SASS_AUDIT_KIND,
        "packed_count_popc_instruction_count": blocks["packed_count"].count(
            "POPC "
        ),
        "target": TARGET_ARCH,
        "trust_limit": (
            "lexical shape only; no decoder, control-flow reachability, "
            "PTX-to-SASS, driver, hardware, or source-refinement theorem"
        ),
    }


def _parse_ptxas_resources(text: str) -> dict[str, dict[str, int]]:
    entries = list(
        re.finditer(
            r"ptxas info\s+: Compiling entry function '([^']+)' for 'sm_90'\n"
            r"ptxas info\s+: Function properties for \1\n"
            r"\s+([0-9]+) bytes stack frame, ([0-9]+) bytes spill stores, "
            r"([0-9]+) bytes spill loads\n"
            r"ptxas info\s+: Used ([0-9]+) registers, used ([0-9]+) barriers"
            r"(?:, [0-9]+ bytes cumulative stack size)?",
            text,
        )
    )
    rows = {
        match.group(1): {
            "barriers": int(match.group(6)),
            "registers": int(match.group(5)),
            "spill_load_bytes": int(match.group(4)),
            "spill_store_bytes": int(match.group(3)),
            "stack_frame_bytes": int(match.group(2)),
        }
        for match in entries
    }
    if set(rows) != set(_KERNELS.values()):
        raise GoldbachOptimizedCandidateError(
            "ptxas resource report does not cover the exact kernel set"
        )
    if any(
        row["barriers"] != 0
        or row["spill_load_bytes"] != 0
        or row["spill_store_bytes"] != 0
        for row in rows.values()
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate sm_90 build has a barrier or register spill"
        )
    if max(row["registers"] for row in rows.values()) > 52:
        raise GoldbachOptimizedCandidateError(
            "candidate sm_90 register use exceeds the reviewed ceiling"
        )
    return dict(sorted(rows.items()))


def _normalized_build_argv(
    *, arch: str, host_flags: str
) -> list[str]:
    return [
        "<nvcc>",
        "-O3",
        "-std=c++17",
        f"-arch={arch}",
        "-ccbin",
        "<host-cxx>",
        "--threads",
        "1",
        f"--frandom-seed={EXPECTED_GOLDBACH_SOURCE_SHA256}",
        "--keep",
        "--keep-dir",
        "<package-root>/build/intermediates",
        "-I",
        "<package-root>/source/include",
        (
            f"-Xcompiler={host_flags},"
            "-ffile-prefix-map=<package-root>=.,"
            "-fdebug-prefix-map=<package-root>=."
        ),
        "-Xptxas=-v",
        "-diag-suppress=177",
        "-Xlinker",
        "--build-id=none",
        "<package-root>/source/src/goldbach.cu",
        "<package-root>/source/src/prime_bitset.cpp",
        "<package-root>/source/src/segmented_sieve.cpp",
        "-lgomp",
        "-o",
        "<package-root>/artifacts/goldbach-gpu",
    ]


def _compile(
    source_root: Path,
    root: Path,
    *,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    retain: bool,
    timeout: int,
) -> dict[str, Any]:
    if _ARCH_RE.fullmatch(arch) is None:
        raise GoldbachOptimizedCandidateError(
            "candidate architecture must be native or sm_NN"
        )
    keep = root / "build/intermediates"
    artifacts = root / "artifacts"
    if source_root != root / "source":
        raise GoldbachOptimizedCandidateError(
            "candidate source must occupy the normalized build-root/source path"
        )
    keep.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    executable = artifacts / "goldbach-gpu"
    nvcc_path = nvcc.resolve(strict=True)
    host_path = host_cxx.resolve(strict=True)
    host_flags = _host_flags()
    prefix = (
        f"{host_flags},"
        f"-ffile-prefix-map={root}=.,"
        f"-fdebug-prefix-map={root}=."
    )
    argv = [
        str(nvcc_path),
        "-O3",
        "-std=c++17",
        f"-arch={arch}",
        "-ccbin",
        str(host_path),
        "--threads",
        "1",
        f"--frandom-seed={EXPECTED_GOLDBACH_SOURCE_SHA256}",
        "--keep",
        "--keep-dir",
        "build/intermediates",
        "-I",
        "source/include",
        f"-Xcompiler={prefix}",
        "-Xptxas=-v",
        "-diag-suppress=177",
        "-Xlinker",
        "--build-id=none",
        "source/src/goldbach.cu",
        "source/src/prime_bitset.cpp",
        "source/src/segmented_sieve.cpp",
        "-lgomp",
        "-o",
        "artifacts/goldbach-gpu",
    ]
    started = time.monotonic_ns()
    completed = _run(
        argv,
        cwd=root,
        environment=_build_environment(),
        timeout=timeout,
    )
    elapsed = time.monotonic_ns() - started
    if completed.stdout:
        raise GoldbachOptimizedCandidateError(
            "candidate compiler unexpectedly wrote stdout"
        )
    ptxas_text = _safe_text(completed.stderr, "ptxas resource output")
    resources = (
        _parse_ptxas_resources(ptxas_text) if arch == TARGET_ARCH else None
    )
    result: dict[str, Any] = {
        "arch": arch,
        "build_elapsed_nanoseconds": elapsed,
        "executable": _pin(executable),
        "host_flags": host_flags,
        "normalized_argv": _normalized_build_argv(
            arch=arch, host_flags=host_flags
        ),
        "ptxas_resources": resources,
    }
    if retain:
        if arch != TARGET_ARCH:
            raise GoldbachOptimizedCandidateError(
                "only the exact sm_90 build may be retained"
            )
        retained = {
            "ptx": keep / "goldbach.ptx",
            "cubin": keep / "goldbach.sm_90.cubin",
            "device_link_cubin": keep / "goldbach-gpu_dlink.sm_90.cubin",
        }
        for name, source in retained.items():
            if not source.is_file() or source.is_symlink():
                raise GoldbachOptimizedCandidateError(
                    f"nvcc did not retain exact {name}"
                )
            target = artifacts / {
                "ptx": "goldbach.sm_90.ptx",
                "cubin": "goldbach.sm_90.cubin",
                "device_link_cubin": "goldbach.dlink.sm_90.cubin",
            }[name]
            shutil.copyfile(source, target)
        sass = artifacts / "goldbach.sm_90.sass"
        nvdisasm = Path("/usr/local/cuda/bin/nvdisasm").resolve(strict=True)
        disassembled = _run(
            [str(nvdisasm), str(artifacts / "goldbach.sm_90.cubin")],
            cwd=root,
            environment=_build_environment(),
            timeout=timeout,
        )
        if disassembled.stderr:
            raise GoldbachOptimizedCandidateError(
                "nvdisasm unexpectedly wrote stderr"
            )
        sass.write_bytes(disassembled.stdout)
        result["artifacts"] = {
            name: _pin(artifacts / filename)
            for name, filename in (
                ("executable", "goldbach-gpu"),
                ("ptx", "goldbach.sm_90.ptx"),
                ("cubin", "goldbach.sm_90.cubin"),
                ("device_link_cubin", "goldbach.dlink.sm_90.cubin"),
                ("sass", "goldbach.sm_90.sass"),
            )
        }
        shutil.rmtree(root / "build")
    return result


def _validate_component_kat_result(
    name: str, value: object
) -> dict[str, object]:
    try:
        specification = _COMPONENT_KATS[name]
    except KeyError as error:
        raise GoldbachOptimizedCandidateError(
            f"unknown optimized Goldbach component KAT: {name}"
        ) from error
    if not isinstance(value, dict):
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT output is not one object"
        )
    compute_capability = value.get("compute_capability")
    if (
        not isinstance(compute_capability, str)
        or _COMPUTE_CAPABILITY_RE.fullmatch(compute_capability) is None
    ):
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT compute capability is malformed"
        )
    body = dict(value)
    del body["compute_capability"]
    if body != specification["result_without_compute_capability"]:
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT fixed answer differs"
        )
    return value


def _run_component_kat(
    name: str,
    root: Path,
    *,
    nvcc: Path,
    host_cxx: Path,
    arch: str,
    timeout: int,
) -> dict[str, object]:
    """Compile and run one exact fixed-answer CUDA component check."""

    if _ARCH_RE.fullmatch(arch) is None:
        raise GoldbachOptimizedCandidateError(
            "component KAT architecture must be native or sm_NN"
        )
    specification = _COMPONENT_KATS[name]
    source = specification["source_path"]
    if not isinstance(source, Path):
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT source specification is malformed"
        )
    expected_source = {
        "sha256": specification["source_sha256"],
        "size_bytes": specification["source_size_bytes"],
    }
    if _pin(source) != expected_source:
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT source identity differs"
        )

    build_root = root / name
    copied_source = build_root / "source/kat.cu"
    keep = build_root / "build/intermediates"
    artifacts = build_root / "artifacts"
    copied_source.parent.mkdir(parents=True)
    keep.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    shutil.copyfile(source, copied_source)
    executable = artifacts / "kat"
    host_flags = _host_flags()
    prefix = (
        f"{host_flags},"
        f"-ffile-prefix-map={build_root}=.,"
        f"-fdebug-prefix-map={build_root}=."
    )
    argv = [
        str(nvcc.resolve(strict=True)),
        "-O3",
        "-std=c++20",
        f"-arch={arch}",
        "-ccbin",
        str(host_cxx.resolve(strict=True)),
        "--threads",
        "1",
        f"--frandom-seed={specification['source_sha256']}",
        "--keep",
        "--keep-dir",
        "build/intermediates",
        f"-Xcompiler={prefix}",
        "-Xlinker",
        "--build-id=none",
        "source/kat.cu",
        "-o",
        "artifacts/kat",
    ]
    built = _run(
        argv,
        cwd=build_root,
        environment=_build_environment(),
        timeout=timeout,
    )
    if built.stdout:
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT compiler unexpectedly wrote stdout"
        )
    started = time.monotonic_ns()
    ran = _run(
        [str(executable)],
        cwd=build_root,
        environment=_build_environment(),
        timeout=timeout,
    )
    elapsed = time.monotonic_ns() - started
    if ran.stderr:
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT unexpectedly wrote stderr"
        )
    try:
        decoded = json.loads(_safe_text(ran.stdout, f"{name} KAT stdout"))
    except json.JSONDecodeError as error:
        raise GoldbachOptimizedCandidateError(
            f"{name} KAT stdout is not one JSON value"
        ) from error
    result = _validate_component_kat_result(name, decoded)
    return {
        "accepted": True,
        "arch": arch,
        "build_executable": _pin(executable),
        "classification": "bounded-fixed-answer-not-production-evidence",
        "elapsed_nanoseconds": elapsed,
        "host_architecture": platform.machine(),
        "kind": COMPONENT_KAT_KIND,
        "name": name,
        "normalized_build_argv": [
            "<nvcc>",
            "-O3",
            "-std=c++20",
            f"-arch={arch}",
            "-ccbin",
            "<host-cxx>",
            "--threads",
            "1",
            f"--frandom-seed={specification['source_sha256']}",
            "--keep",
            "--keep-dir",
            "<build-root>/build/intermediates",
            (
                f"-Xcompiler={host_flags},"
                "-ffile-prefix-map=<build-root>=.,"
                "-fdebug-prefix-map=<build-root>=."
            ),
            "-Xlinker",
            "--build-id=none",
            "<build-root>/source/kat.cu",
            "-o",
            "<build-root>/artifacts/kat",
        ],
        "result": result,
        "source": expected_source,
        "stdout_sha256": hashlib.sha256(ran.stdout).hexdigest(),
    }


def bounded_component_kats(
    *,
    nvcc: Path,
    host_cxx: Path,
    arch: str = "native",
    timeout: int = 300,
) -> dict[str, dict[str, object]]:
    """Run the two independent fixed-answer component KATs."""

    with tempfile.TemporaryDirectory(
        prefix="tg-goldbach-optimized-component-kats-"
    ) as temporary:
        root = Path(temporary)
        return {
            name: _run_component_kat(
                name,
                root,
                nvcc=nvcc,
                host_cxx=host_cxx,
                arch=arch,
                timeout=timeout,
            )
            for name in sorted(_COMPONENT_KATS)
        }


def _run_candidate(
    executable: Path,
    *,
    even_start: int,
    even_limit: int,
    timeout: int,
) -> tuple[bytes, dict[str, object], int]:
    executable_sha256 = _sha256(executable)
    plan = make_bounded_sample_plan(
        even_start=even_start,
        even_limit=even_limit,
        shard_count=1,
        executable_sha256=executable_sha256,
    )
    started = time.monotonic_ns()
    completed = _run(
        [str(executable), *runner_arguments(plan.shards[0])],
        cwd=executable.parent,
        environment=_build_environment(),
        timeout=timeout,
    )
    elapsed = time.monotonic_ns() - started
    if completed.stderr:
        raise GoldbachOptimizedCandidateError(
            "Goldbach candidate unexpectedly wrote stderr"
        )
    try:
        parsed = parse_runner_stdout(completed.stdout, plan.shards[0])
    except GoldbachGPUCampaignError as error:
        raise GoldbachOptimizedCandidateError(str(error)) from error
    if (
        parsed["phase2_fallbacks"] != 0
        or parsed["all_even_numbers_reported_satisfied"] is not True
    ):
        raise GoldbachOptimizedCandidateError(
            "bounded candidate did not close without fallback"
        )
    return completed.stdout, parsed, elapsed


def bounded_full_differential(
    hardened_source_root: Path,
    *,
    nvcc: Path,
    host_cxx: Path,
    arch: str = "native",
    even_start: int = DEFAULT_BOUNDED_EVEN_START,
    even_limit: int = DEFAULT_BOUNDED_EVEN_LIMIT,
    timeout: int = 900,
) -> dict[str, object]:
    """Run productive and all-live-word crosscheck binaries on one range."""

    if (
        even_start < 4
        or even_start % 2
        or even_limit < even_start
        or even_limit % 2
    ):
        raise GoldbachOptimizedCandidateError(
            "bounded differential range must be nonempty and even"
        )
    even_count = (even_limit - even_start) // 2 + 1
    if even_count > MAX_BOUNDED_EVEN_COUNT:
        raise GoldbachOptimizedCandidateError(
            "bounded differential exceeds the reviewed 600-million-even cap"
        )
    verify_hardened_source_tree(hardened_source_root)
    with tempfile.TemporaryDirectory(
        prefix="tg-goldbach-optimized-differential-"
    ) as temporary:
        root = Path(temporary)
        productive_source = root / "productive/source"
        productive = prepare_optimized_source(
            hardened_source_root, productive_source
        )
        crosscheck_source = root / "crosscheck/source"
        crosscheck_identity = _write_crosscheck_tree(
            hardened_source_root, crosscheck_source
        )
        productive_build = _compile(
            productive_source,
            root / "productive",
            nvcc=nvcc,
            host_cxx=host_cxx,
            arch=arch,
            retain=False,
            timeout=timeout,
        )
        crosscheck_build = _compile(
            crosscheck_source,
            root / "crosscheck",
            nvcc=nvcc,
            host_cxx=host_cxx,
            arch=arch,
            retain=False,
            timeout=timeout,
        )
        productive_raw, productive_parsed, productive_elapsed = _run_candidate(
            root / "productive/artifacts/goldbach-gpu",
            even_start=even_start,
            even_limit=even_limit,
            timeout=timeout,
        )
        crosscheck_raw, crosscheck_parsed, crosscheck_elapsed = _run_candidate(
            root / "crosscheck/artifacts/goldbach-gpu",
            even_start=even_start,
            even_limit=even_limit,
            timeout=timeout,
        )
        semantic_fields = (
            "gpu_name",
            "gpu_vram_mb",
            "small_prime_bitset_limit",
            "phase2_fallbacks",
            "all_even_numbers_reported_satisfied",
        )
        if any(
            productive_parsed[field] != crosscheck_parsed[field]
            for field in semantic_fields
        ):
            raise GoldbachOptimizedCandidateError(
                "productive and full-differential result summaries disagree"
            )
        return {
            "accepted": True,
            "arch": arch,
            "classification": (
                "bounded-all-live-sieve-coverage-count-differential-"
                "not-source-scale-evidence"
            ),
            "crosscheck": {
                "build_executable": crosscheck_build["executable"],
                "elapsed_nanoseconds": crosscheck_elapsed,
                "parsed": crosscheck_parsed,
                "stdout_sha256": hashlib.sha256(crosscheck_raw).hexdigest(),
            },
            "crosscheck_source": crosscheck_identity,
            "domain": {
                "even_count": even_count,
                "even_limit_inclusive": even_limit,
                "even_start_inclusive": even_start,
            },
            "kind": DIFFERENTIAL_KIND,
            "productive": {
                "build_executable": productive_build["executable"],
                "elapsed_nanoseconds": productive_elapsed,
                "parsed": productive_parsed,
                "stdout_sha256": hashlib.sha256(productive_raw).hexdigest(),
            },
            "productive_source_identity_sha256": productive[
                "source_identity_sha256"
            ],
            "source_scale_completion": False,
            "target_h100_measured": False,
        }


def _validate_pin_value(value: object, what: str) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or set(value) != {"sha256", "size_bytes"}
        or not isinstance(value["sha256"], str)
        or _SHA256_RE.fullmatch(value["sha256"]) is None
        or isinstance(value["size_bytes"], bool)
        or not isinstance(value["size_bytes"], int)
        or value["size_bytes"] <= 0
    ):
        raise GoldbachOptimizedCandidateError(f"{what} pin is malformed")
    return value


def _validate_component_kat_report(
    name: str, value: object
) -> dict[str, object]:
    fields = {
        "accepted",
        "arch",
        "build_executable",
        "classification",
        "elapsed_nanoseconds",
        "host_architecture",
        "kind",
        "name",
        "normalized_build_argv",
        "result",
        "source",
        "stdout_sha256",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise GoldbachOptimizedCandidateError(
            f"{name} retained KAT report has wrong fields"
        )
    arch = value["arch"]
    host_architecture = value["host_architecture"]
    if (
        value["accepted"] is not True
        or value["classification"]
        != "bounded-fixed-answer-not-production-evidence"
        or value["kind"] != COMPONENT_KAT_KIND
        or value["name"] != name
        or not isinstance(arch, str)
        or _ARCH_RE.fullmatch(arch) is None
        or host_architecture not in {"aarch64", "x86_64"}
        or isinstance(value["elapsed_nanoseconds"], bool)
        or not isinstance(value["elapsed_nanoseconds"], int)
        or value["elapsed_nanoseconds"] <= 0
        or not isinstance(value["stdout_sha256"], str)
        or _SHA256_RE.fullmatch(value["stdout_sha256"]) is None
    ):
        raise GoldbachOptimizedCandidateError(
            f"{name} retained KAT report identity differs"
        )
    _validate_pin_value(value["build_executable"], f"{name} KAT executable")
    source = _validate_pin_value(value["source"], f"{name} KAT source")
    specification = _COMPONENT_KATS[name]
    if source != {
        "sha256": specification["source_sha256"],
        "size_bytes": specification["source_size_bytes"],
    }:
        raise GoldbachOptimizedCandidateError(
            f"{name} retained KAT source identity differs"
        )
    host_flags = (
        "-O3,-march=x86-64-v2,-mtune=generic,-fopenmp"
        if host_architecture == "x86_64"
        else "-O3,-march=armv8-a,-mtune=generic,-fopenmp"
    )
    expected_argv = [
        "<nvcc>",
        "-O3",
        "-std=c++20",
        f"-arch={arch}",
        "-ccbin",
        "<host-cxx>",
        "--threads",
        "1",
        f"--frandom-seed={specification['source_sha256']}",
        "--keep",
        "--keep-dir",
        "<build-root>/build/intermediates",
        (
            f"-Xcompiler={host_flags},"
            "-ffile-prefix-map=<build-root>=.,"
            "-fdebug-prefix-map=<build-root>=."
        ),
        "-Xlinker",
        "--build-id=none",
        "<build-root>/source/kat.cu",
        "-o",
        "<build-root>/artifacts/kat",
    ]
    if value["normalized_build_argv"] != expected_argv:
        raise GoldbachOptimizedCandidateError(
            f"{name} retained KAT build recipe differs"
        )
    _validate_component_kat_result(name, value["result"])
    return value


def _validate_differential_report(value: object) -> dict[str, object]:
    fields = {
        "accepted",
        "arch",
        "classification",
        "crosscheck",
        "crosscheck_source",
        "domain",
        "kind",
        "productive",
        "productive_source_identity_sha256",
        "source_scale_completion",
        "target_h100_measured",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise GoldbachOptimizedCandidateError(
            "retained bounded differential has wrong fields"
        )
    arch = value["arch"]
    domain = value["domain"]
    if (
        value["accepted"] is not True
        or value["classification"]
        != (
            "bounded-all-live-sieve-coverage-count-differential-"
            "not-source-scale-evidence"
        )
        or value["kind"] != DIFFERENTIAL_KIND
        or value["source_scale_completion"] is not False
        or value["target_h100_measured"] is not False
        or not isinstance(arch, str)
        or _ARCH_RE.fullmatch(arch) is None
        or not isinstance(domain, dict)
        or set(domain)
        != {
            "even_count",
            "even_limit_inclusive",
            "even_start_inclusive",
        }
    ):
        raise GoldbachOptimizedCandidateError(
            "retained bounded differential identity differs"
        )
    start = domain["even_start_inclusive"]
    limit = domain["even_limit_inclusive"]
    count = domain["even_count"]
    if (
        any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in (start, limit, count)
        )
        or start < 4
        or start % 2
        or limit < start
        or limit % 2
        or count != (limit - start) // 2 + 1
        or count > MAX_BOUNDED_EVEN_COUNT
    ):
        raise GoldbachOptimizedCandidateError(
            "retained bounded differential geometry differs"
        )
    if value["crosscheck_source"] != {
        "goldbach_source_sha256": EXPECTED_CROSSCHECK_SOURCE_SHA256,
        "goldbach_source_size_bytes": EXPECTED_CROSSCHECK_SOURCE_BYTES,
    }:
        raise GoldbachOptimizedCandidateError(
            "retained crosscheck source identity differs"
        )
    productive_identity = value["productive_source_identity_sha256"]
    if (
        not isinstance(productive_identity, str)
        or _SHA256_RE.fullmatch(productive_identity) is None
    ):
        raise GoldbachOptimizedCandidateError(
            "retained productive source identity is malformed"
        )
    parsed_rows: list[dict[str, object]] = []
    for name in ("productive", "crosscheck"):
        row = value[name]
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "build_executable",
                "elapsed_nanoseconds",
                "parsed",
                "stdout_sha256",
            }
            or isinstance(row["elapsed_nanoseconds"], bool)
            or not isinstance(row["elapsed_nanoseconds"], int)
            or row["elapsed_nanoseconds"] <= 0
            or not isinstance(row["stdout_sha256"], str)
            or _SHA256_RE.fullmatch(row["stdout_sha256"]) is None
        ):
            raise GoldbachOptimizedCandidateError(
                f"retained {name} differential row is malformed"
            )
        _validate_pin_value(
            row["build_executable"], f"{name} differential executable"
        )
        parsed = row["parsed"]
        if (
            not isinstance(parsed, dict)
            or set(parsed)
            != {
                "all_even_numbers_reported_satisfied",
                "gpu_name",
                "gpu_vram_mb",
                "initialization_milliseconds",
                "phase2_fallbacks",
                "reported_computation_seconds",
                "small_prime_bitset_limit",
            }
            or parsed["all_even_numbers_reported_satisfied"] is not True
            or isinstance(parsed["phase2_fallbacks"], bool)
            or not isinstance(parsed["phase2_fallbacks"], int)
            or parsed["phase2_fallbacks"] != 0
            or not isinstance(parsed["gpu_name"], str)
            or not parsed["gpu_name"]
            or isinstance(parsed["gpu_vram_mb"], bool)
            or not isinstance(parsed["gpu_vram_mb"], int)
            or parsed["gpu_vram_mb"] <= 0
            or isinstance(parsed["small_prime_bitset_limit"], bool)
            or not isinstance(parsed["small_prime_bitset_limit"], int)
            or parsed["small_prime_bitset_limit"] <= 0
        ):
            raise GoldbachOptimizedCandidateError(
                f"retained {name} parsed differential row differs"
            )
        for timing in (
            "initialization_milliseconds",
            "reported_computation_seconds",
        ):
            if not isinstance(parsed[timing], str):
                raise GoldbachOptimizedCandidateError(
                    f"retained {name} differential timing is not text"
                )
            try:
                numeric = float(parsed[timing])
            except (TypeError, ValueError) as error:
                raise GoldbachOptimizedCandidateError(
                    f"retained {name} differential timing is malformed"
                ) from error
            if not 0 < numeric < float("inf"):
                raise GoldbachOptimizedCandidateError(
                    f"retained {name} differential timing is nonpositive"
                )
        parsed_rows.append(parsed)
    semantic_fields = (
        "gpu_name",
        "gpu_vram_mb",
        "small_prime_bitset_limit",
        "phase2_fallbacks",
        "all_even_numbers_reported_satisfied",
    )
    if any(
        parsed_rows[0][field] != parsed_rows[1][field]
        for field in semantic_fields
    ):
        raise GoldbachOptimizedCandidateError(
            "retained productive/crosscheck summaries disagree"
        )
    return value


def _closure_rows(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise GoldbachOptimizedCandidateError(
                "candidate package contains a symbolic link"
            )
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise GoldbachOptimizedCandidateError(
                "candidate package contains a special file"
            )
        relative = path.relative_to(root).as_posix()
        if relative == "candidate-manifest.json":
            continue
        rows.append({"path": relative, **_pin(path)})
    return rows


def _closure_sha256(rows: Sequence[Mapping[str, object]]) -> str:
    return hashlib.sha256(
        _CLOSURE_DOMAIN + canonical_json_bytes(list(rows))
    ).hexdigest()


def build_candidate_package(
    hardened_source_root: Path,
    destination: Path,
    *,
    nvcc: Path = Path("/usr/local/cuda/bin/nvcc"),
    host_cxx: Path = Path("/usr/bin/g++"),
    bounded_arch: str = "native",
    bounded_even_start: int = DEFAULT_BOUNDED_EVEN_START,
    bounded_even_limit: int = DEFAULT_BOUNDED_EVEN_LIMIT,
    timeout: int = 900,
) -> dict[str, object]:
    """Build one immutable, content-addressed sm_90 candidate package."""

    if destination.exists() or destination.is_symlink():
        raise GoldbachOptimizedCandidateError(
            "candidate package destination must be absent"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
    )
    succeeded = False
    try:
        source = prepare_optimized_source(
            hardened_source_root, stage / "source"
        )
        crosscheck = _write_crosscheck_tree(
            hardened_source_root, stage / "qualification/crosscheck-source"
        )
        build = _compile(
            stage / "source",
            stage,
            nvcc=nvcc,
            host_cxx=host_cxx,
            arch=TARGET_ARCH,
            retain=True,
            timeout=timeout,
        )
        audits = stage / "audits"
        audits.mkdir()
        ptx_audit = audit_sm90_ptx(stage / "artifacts/goldbach.sm_90.ptx")
        sass_audit = audit_sm90_sass(
            stage / "artifacts/goldbach.sm_90.sass"
        )
        (audits / "ptx.json").write_bytes(canonical_json_bytes(ptx_audit))
        (audits / "sass.json").write_bytes(canonical_json_bytes(sass_audit))
        differential = bounded_full_differential(
            hardened_source_root,
            nvcc=nvcc,
            host_cxx=host_cxx,
            arch=bounded_arch,
            even_start=bounded_even_start,
            even_limit=bounded_even_limit,
            timeout=timeout,
        )
        (audits / "bounded-differential.json").write_bytes(
            canonical_json_bytes(differential)
        )
        kat_sources = stage / "qualification/component-kat-source"
        kat_sources.mkdir()
        for name, specification in _COMPONENT_KATS.items():
            source_path = specification["source_path"]
            if not isinstance(source_path, Path):
                raise GoldbachOptimizedCandidateError(
                    f"{name} KAT source specification is malformed"
                )
            shutil.copyfile(source_path, kat_sources / f"{name}.cu")
        component_kats = bounded_component_kats(
            nvcc=nvcc,
            host_cxx=host_cxx,
            arch=bounded_arch,
            timeout=timeout,
        )
        for name, report in component_kats.items():
            (audits / f"{name}-kat.json").write_bytes(
                canonical_json_bytes(report)
            )
        tools = {
            "host_cxx": _tool(host_cxx, ("--version",)),
            "nvcc": _tool(nvcc, ("--version",)),
            "nvdisasm": _tool(
                Path("/usr/local/cuda/bin/nvdisasm"), ("--version",)
            ),
        }
        rows = _closure_rows(stage)
        identity = {
            "algorithm_candidate_id": ALGORITHM_CANDIDATE_ID,
            "artifacts": build["artifacts"],
            "bounded_component_kats_completed": True,
            "bounded_full_differential_completed": True,
            "build": {
                "arch": build["arch"],
                "host_architecture": platform.machine(),
                "host_flags": build["host_flags"],
                "normalized_argv": build["normalized_argv"],
                "ptxas_resources": build["ptxas_resources"],
            },
            "classification": QUALIFICATION_CLASSIFICATION,
            "closure_files": rows,
            "closure_sha256": _closure_sha256(rows),
            "crosscheck_source": crosscheck,
            "kind": MANIFEST_KIND,
            "optimized_source": {
                "goldbach_source_bytes": EXPECTED_GOLDBACH_SOURCE_BYTES,
                "goldbach_source_sha256": EXPECTED_GOLDBACH_SOURCE_SHA256,
                "source_identity_sha256": source["source_identity_sha256"],
            },
            "schema_version": 1,
            "toolchain": tools,
            "trust_status": {
                "confidential_attestation_completed": False,
                "lean_atom_discharged": False,
                "production_identity_promoted": False,
                "source_scale_completion": False,
                "target_h100_measured": False,
            },
        }
        manifest = {
            **identity,
            "manifest_sha256": hashlib.sha256(
                _MANIFEST_DOMAIN + canonical_json_bytes(identity)
            ).hexdigest(),
        }
        (stage / "candidate-manifest.json").write_bytes(
            canonical_json_bytes(manifest)
        )
        stage.rename(destination)
        succeeded = True
        return manifest
    except (
        OSError,
        UnicodeError,
        subprocess.SubprocessError,
        GoldbachGPUCampaignError,
    ) as error:
        if isinstance(error, GoldbachOptimizedCandidateError):
            raise
        raise GoldbachOptimizedCandidateError(str(error)) from error
    finally:
        if not succeeded:
            shutil.rmtree(stage, ignore_errors=True)


def validate_candidate_package(
    root: Path,
    *,
    expected_manifest_file_sha256: str | None = None,
    require_reviewed_production: bool = False,
) -> dict[str, object]:
    """Recompute every package pin and optionally require external admission.

    The manifest's domain-separated self-hash detects accidental corruption
    but cannot authorize itself.  ``expected_manifest_file_sha256`` binds the
    exact canonical manifest bytes from outside the package.  Production
    callers must also set ``require_reviewed_production``; that pin then has
    to be compiled into the source-reviewed allowlist above.
    """

    manifest_path = root / "candidate-manifest.json"
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldbachOptimizedCandidateError(
            "cannot load candidate manifest"
        ) from error
    manifest_file_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_manifest_file_sha256 is not None:
        if (
            not isinstance(expected_manifest_file_sha256, str)
            or _SHA256_RE.fullmatch(expected_manifest_file_sha256) is None
        ):
            raise GoldbachOptimizedCandidateError(
                "external candidate manifest file pin is malformed"
            )
        if manifest_file_sha256 != expected_manifest_file_sha256:
            raise GoldbachOptimizedCandidateError(
                "candidate manifest differs from its external file pin"
            )
    if require_reviewed_production:
        if expected_manifest_file_sha256 is None:
            raise GoldbachOptimizedCandidateError(
                "production candidate validation requires an external "
                "manifest file pin"
            )
        if (
            manifest_file_sha256
            not in REVIEWED_PRODUCTION_CANDIDATE_MANIFEST_FILE_SHA256S
        ):
            raise GoldbachOptimizedCandidateError(
                "optimized Goldbach production candidate is unconfigured; "
                "review the exact Azure x86_64 package before populating "
                "the allowlist"
            )
    if canonical_json_bytes(manifest) != raw:
        raise GoldbachOptimizedCandidateError(
            "candidate manifest is not canonical JSON"
        )
    if (
        not isinstance(manifest, dict)
        or manifest.get("kind") != MANIFEST_KIND
        or manifest.get("classification") != QUALIFICATION_CLASSIFICATION
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate manifest kind/classification differs"
        )
    manifest_sha256 = manifest.get("manifest_sha256")
    if (
        not isinstance(manifest_sha256, str)
        or _SHA256_RE.fullmatch(manifest_sha256) is None
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate manifest hash is malformed"
        )
    identity = dict(manifest)
    del identity["manifest_sha256"]
    if hashlib.sha256(
        _MANIFEST_DOMAIN + canonical_json_bytes(identity)
    ).hexdigest() != manifest_sha256:
        raise GoldbachOptimizedCandidateError(
            "candidate manifest self-hash differs"
        )
    rows = _closure_rows(root)
    if rows != manifest.get("closure_files"):
        raise GoldbachOptimizedCandidateError(
            "candidate package file closure differs"
        )
    if _closure_sha256(rows) != manifest.get("closure_sha256"):
        raise GoldbachOptimizedCandidateError(
            "candidate package closure hash differs"
        )
    if (
        manifest.get("schema_version") != 1
        or manifest.get("algorithm_candidate_id") != ALGORITHM_CANDIDATE_ID
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate package algorithm identity differs"
        )
    expected_artifacts = {
        name: _pin(root / f"artifacts/{filename}")
        for name, filename in (
            ("executable", "goldbach-gpu"),
            ("ptx", "goldbach.sm_90.ptx"),
            ("cubin", "goldbach.sm_90.cubin"),
            ("device_link_cubin", "goldbach.dlink.sm_90.cubin"),
            ("sass", "goldbach.sm_90.sass"),
        )
    }
    if manifest.get("artifacts") != expected_artifacts:
        raise GoldbachOptimizedCandidateError(
            "candidate manifest artifact pins differ"
        )
    optimized_source = manifest.get("optimized_source")
    source_pin = _pin(root / "source/src/goldbach.cu")
    if (
        not isinstance(optimized_source, dict)
        or set(optimized_source)
        != {
            "goldbach_source_bytes",
            "goldbach_source_sha256",
            "source_identity_sha256",
        }
        or optimized_source["goldbach_source_bytes"]
        != EXPECTED_GOLDBACH_SOURCE_BYTES
        or optimized_source["goldbach_source_sha256"]
        != EXPECTED_GOLDBACH_SOURCE_SHA256
        or source_pin
        != {
            "sha256": EXPECTED_GOLDBACH_SOURCE_SHA256,
            "size_bytes": EXPECTED_GOLDBACH_SOURCE_BYTES,
        }
        or optimized_source["source_identity_sha256"]
        != EXPECTED_SOURCE_IDENTITY_SHA256
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate optimized source identity differs"
        )
    crosscheck_source = manifest.get("crosscheck_source")
    expected_crosscheck = {
        "goldbach_source_sha256": EXPECTED_CROSSCHECK_SOURCE_SHA256,
        "goldbach_source_size_bytes": EXPECTED_CROSSCHECK_SOURCE_BYTES,
    }
    if (
        crosscheck_source != expected_crosscheck
        or _pin(
            root / "qualification/crosscheck-source/src/goldbach.cu"
        )
        != {
            "sha256": EXPECTED_CROSSCHECK_SOURCE_SHA256,
            "size_bytes": EXPECTED_CROSSCHECK_SOURCE_BYTES,
        }
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate crosscheck source identity differs"
        )
    build = manifest.get("build")
    if not isinstance(build, dict) or set(build) != {
        "arch",
        "host_architecture",
        "host_flags",
        "normalized_argv",
        "ptxas_resources",
    }:
        raise GoldbachOptimizedCandidateError(
            "candidate build identity has wrong fields"
        )
    host_architecture = build["host_architecture"]
    if host_architecture == "x86_64":
        expected_host_flags = (
            "-O3,-march=x86-64-v2,-mtune=generic,-fopenmp"
        )
    elif host_architecture == "aarch64":
        expected_host_flags = (
            "-O3,-march=armv8-a,-mtune=generic,-fopenmp"
        )
    else:
        raise GoldbachOptimizedCandidateError(
            "candidate host architecture differs"
        )
    if require_reviewed_production and host_architecture != "x86_64":
        raise GoldbachOptimizedCandidateError(
            "optimized Goldbach production admission requires an x86_64 "
            "host executable"
        )
    _validate_host_executable(
        root / "artifacts/goldbach-gpu", host_architecture
    )
    resources = build["ptxas_resources"]
    if (
        build["arch"] != TARGET_ARCH
        or build["host_flags"] != expected_host_flags
        or build["normalized_argv"]
        != _normalized_build_argv(
            arch=TARGET_ARCH, host_flags=expected_host_flags
        )
        or not isinstance(resources, dict)
        or set(resources) != set(_KERNELS.values())
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate normalized build recipe differs"
        )
    for symbol, resource in resources.items():
        if (
            not isinstance(resource, dict)
            or set(resource)
            != {
                "barriers",
                "registers",
                "spill_load_bytes",
                "spill_store_bytes",
                "stack_frame_bytes",
            }
            or any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or item < 0
                for item in resource.values()
            )
            or resource["barriers"] != 0
            or resource["spill_load_bytes"] != 0
            or resource["spill_store_bytes"] != 0
            or not 1 <= resource["registers"] <= 52
        ):
            raise GoldbachOptimizedCandidateError(
                f"candidate resource row differs for {symbol}"
            )
    toolchain = manifest.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != {
        "host_cxx",
        "nvcc",
        "nvdisasm",
    }:
        raise GoldbachOptimizedCandidateError(
            "candidate toolchain identity has wrong fields"
        )
    for name, tool in toolchain.items():
        if (
            not isinstance(tool, dict)
            or set(tool)
            != {"resolved_path", "sha256", "size_bytes", "version"}
            or not isinstance(tool["resolved_path"], str)
            or not Path(tool["resolved_path"]).is_absolute()
            or not isinstance(tool["version"], str)
            or not tool["version"]
        ):
            raise GoldbachOptimizedCandidateError(
                f"candidate toolchain pin is malformed for {name}"
            )
        _validate_pin_value(
            {
                "sha256": tool["sha256"],
                "size_bytes": tool["size_bytes"],
            },
            f"candidate toolchain {name}",
        )
    trust = manifest.get("trust_status")
    if (
        not isinstance(trust, dict)
        or set(trust)
        != {
            "confidential_attestation_completed",
            "lean_atom_discharged",
            "production_identity_promoted",
            "source_scale_completion",
            "target_h100_measured",
        }
        or any(value is not False for value in trust.values())
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate package overstates a trust/completion gate"
        )
    if (
        manifest.get("bounded_full_differential_completed") is not True
        or manifest.get("bounded_component_kats_completed") is not True
    ):
        raise GoldbachOptimizedCandidateError(
            "candidate package omits a required bounded qualification"
        )
    try:
        differential_raw = (
            root / "audits/bounded-differential.json"
        ).read_bytes()
        differential = json.loads(differential_raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldbachOptimizedCandidateError(
            "cannot load retained bounded differential"
        ) from error
    if canonical_json_bytes(differential) != differential_raw:
        raise GoldbachOptimizedCandidateError(
            "retained bounded differential is not canonical JSON"
        )
    _validate_differential_report(differential)
    if differential["productive_source_identity_sha256"] != manifest.get(
        "optimized_source", {}
    ).get("source_identity_sha256"):
        raise GoldbachOptimizedCandidateError(
            "bounded differential productive source identity differs"
        )
    for name, specification in _COMPONENT_KATS.items():
        source_path = (
            root / f"qualification/component-kat-source/{name}.cu"
        )
        expected_source = {
            "sha256": specification["source_sha256"],
            "size_bytes": specification["source_size_bytes"],
        }
        if _pin(source_path) != expected_source:
            raise GoldbachOptimizedCandidateError(
                f"retained {name} KAT source differs"
            )
        report_path = root / f"audits/{name}-kat.json"
        try:
            report_raw = report_path.read_bytes()
            report = json.loads(report_raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GoldbachOptimizedCandidateError(
                f"cannot load retained {name} KAT report"
            ) from error
        if canonical_json_bytes(report) != report_raw:
            raise GoldbachOptimizedCandidateError(
                f"retained {name} KAT report is not canonical JSON"
            )
        checked_report = _validate_component_kat_report(name, report)
        if (
            checked_report["host_architecture"]
            != manifest.get("build", {}).get("host_architecture")
        ):
            raise GoldbachOptimizedCandidateError(
                f"retained {name} KAT host architecture differs"
            )
    ptx = audit_sm90_ptx(root / "artifacts/goldbach.sm_90.ptx")
    sass = audit_sm90_sass(root / "artifacts/goldbach.sm_90.sass")
    for name, expected in (("ptx", ptx), ("sass", sass)):
        try:
            actual = json.loads((root / f"audits/{name}.json").read_bytes())
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GoldbachOptimizedCandidateError(
                f"cannot load retained {name} audit"
            ) from error
        if actual != expected:
            raise GoldbachOptimizedCandidateError(
                f"retained {name} audit differs from fresh audit"
            )
    return manifest


__all__ = [
    "DEFAULT_BOUNDED_EVEN_LIMIT",
    "DEFAULT_BOUNDED_EVEN_START",
    "COMPONENT_KAT_KIND",
    "DIFFERENTIAL_KIND",
    "EXPECTED_CROSSCHECK_SOURCE_BYTES",
    "EXPECTED_CROSSCHECK_SOURCE_SHA256",
    "GoldbachOptimizedCandidateError",
    "MANIFEST_KIND",
    "PTX_AUDIT_KIND",
    "QUALIFICATION_CLASSIFICATION",
    "REVIEWED_PRODUCTION_CANDIDATE_MANIFEST_FILE_SHA256S",
    "SASS_AUDIT_KIND",
    "audit_sm90_ptx",
    "audit_sm90_sass",
    "bounded_component_kats",
    "bounded_full_differential",
    "build_candidate_package",
    "crosscheck_goldbach_source",
    "validate_candidate_package",
]

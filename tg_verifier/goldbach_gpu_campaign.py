# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed orchestration for the hardened GoldbachGPU computation.

The production plan covers every even integer in ``[4, 4 * 10**18]`` exactly
once with 65,536 balanced, contiguous checkpoint leaves scheduled over eight
production nodes.  The runner is the reviewed
``isaac-6/goldbach-gpu`` closure with reviewed CPU-race and high-range CUDA
sieve fixes, invoked only in the deterministic twelve-base Miller--Rabin mode.
Plans bind the exact hardened source closure and an operator-supplied
executable SHA-256.

This module deliberately stops at a reproducible *external computation*.
Neither a successful local process nor the aggregate Merkle root authenticates
where the process ran, and neither establishes a Lean theorem.  Consequently
all receipts say ``execution_attested = false`` and
``lean_atom_discharged = false``.  A later signed-receipt layer must bind the
same plan, executable, source, stdout and aggregate commitments before the
trusted-compute bridge can be considered.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from math import isqrt
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    sha256_bytes,
    write_immutable_json,
)


PRODUCTION_EVEN_START = 4
PRODUCTION_EVEN_LIMIT = 4_000_000_000_000_000_000
PRODUCTION_SHARDS = 65_536
PRODUCTION_NODES = 8
PRODUCTION_GROUPS = 8_192
PRODUCTION_LEAVES_PER_GROUP = PRODUCTION_SHARDS // PRODUCTION_GROUPS
PRODUCTION_EVEN_COUNT = (
    (PRODUCTION_EVEN_LIMIT - PRODUCTION_EVEN_START) // 2 + 1
)

# A separate production profile for the finite branch below the independently
# proved analytic crossover at 10^27.  It is deliberately not called the
# historical source campaign.
ANALYTIC_10POW27_EVEN_START = 4
ANALYTIC_10POW27_EVEN_LIMIT = 31_250_000_000_000_000
ANALYTIC_10POW27_SHARDS = 65_536
ANALYTIC_10POW27_EVEN_COUNT = (
    (ANALYTIC_10POW27_EVEN_LIMIT - ANALYTIC_10POW27_EVEN_START) // 2 + 1
)

UPSTREAM_COMMIT = "b58b2dea697cdaf09208ab6d9ea2ac1b9cce1898"
HARDENING_PATCH_SHA256 = (
    "8286377f1377e9a3b7b87066b833b1e8b23c9d62af4a4089086964a7c4017452"
)
MILLER_RABIN_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
MILLER_RABIN_PROVEN_THRESHOLD_EXCLUSIVE = 318_665_857_834_031_151_167_461

PRODUCTION_ALGORITHM = "goldbach-gpu-hardened-production-65536-leaf-v2"
ANALYTIC_10POW27_ALGORITHM = (
    "goldbach-gpu-analytic-10pow27-production-65536-leaf-v1"
)
OPTIMIZED_PRODUCTION_ALGORITHM = (
    "goldbach-gpu-historical-wheel47-warp32749-shifted-packed-"
    "65536-leaf-v1"
)
ANALYTIC_10POW27_OPTIMIZED_ALGORITHM = (
    "goldbach-gpu-analytic-10pow27-wheel47-warp32749-shifted-packed-"
    "65536-leaf-v1"
)
BOUNDED_ALGORITHM = "goldbach-gpu-hardened-bounded-sample-v1"
PLAN_SCHEMA = "sparkinterval.goldbach-gpu-plan.v1"
RECEIPT_SCHEMA = "sparkinterval.goldbach-gpu-shard-receipt.v1"
AGGREGATE_SCHEMA = "sparkinterval.goldbach-gpu-aggregate.v1"

SEGMENT_SIZE = 200_000_000
P_SMALL = 1_000_000
BATCH_SIZE = 2_000_000
GPU_COUNT_PER_PROCESS = 1
PRODUCTION_GPU_NAME_RE = re.compile(r"^NVIDIA H100(?: |\Z)")
PRODUCTION_MIN_GPU_VRAM_MB = 75_000
PRODUCTION_GPU_COMPUTE_CAPABILITY = "9.0"
MAX_OUTPUT_BYTES = 64 * 1024

_ROOT = Path(__file__).resolve().parents[1]
_PATCH_PATH = _ROOT / "patches" / "goldbach-gpu" / "b58b2dea-hardening.patch"
_PIN_PATH = _ROOT / "specifications" / "GOLDBACH_GPU_UPSTREAM.json"

_PLAN_DOMAIN = b"sparkinterval/tg/goldbach-gpu/plan/v1\x00"
_SOURCE_DOMAIN = b"sparkinterval/tg/goldbach-gpu/hardened-source/v1\x00"
_RECEIPT_DOMAIN = b"sparkinterval/tg/goldbach-gpu/shard-receipt/v1\x00"
_MERKLE_LEAF_DOMAIN = b"sparkinterval/tg/goldbach-gpu/merkle-leaf/v1\x00"
_MERKLE_NODE_DOMAIN = b"sparkinterval/tg/goldbach-gpu/merkle-node/v1\x00"
_MERKLE_ODD_DOMAIN = b"sparkinterval/tg/goldbach-gpu/merkle-odd/v1\x00"
_AGGREGATE_DOMAIN = b"sparkinterval/tg/goldbach-gpu/aggregate/v1\x00"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}\Z")
_DECIMAL_INTEGER_RE = re.compile(r"^(?:0|[1-9][0-9]*)\Z")
_NONNEGATIVE_REAL_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z"
)
_RECEIPT_NAME_RE = re.compile(r"^receipt-([0-9]{8})\.json\Z")

# This is the exact deterministic output of tools/prepare_goldbach_gpu.py for
# the source pin and reviewed patch above.  CMake build products do not belong
# in this source directory and are intentionally rejected.
_EXPECTED_HARDENED_FILES: tuple[tuple[str, str, int], ...] = (
    (
        "CMakeLists.txt",
        "85d6c590bf7505510584b74e638b4c857e6554fc9ff6a176b36f55242f4f2677",
        3238,
    ),
    (
        "LICENSE",
        "90ccbf9641df6fd03427be6ac9eadc8840df8be74cb736164620a3849e72d45f",
        1078,
    ),
    (
        "include/prime_bitset.hpp",
        "0fdcd1ef6033318580d8a86a38690cb4b50755503c58c72aa70405ff1e663f7e",
        3726,
    ),
    (
        "src/goldbach.cu",
        "2b3d1f5636a2a1d21224ede5e8e7d1d4f3716ce8350c55c33d6bd9876f96142d",
        59936,
    ),
    (
        "src/prime_bitset.cpp",
        "71b1c4d0616177a71a006cdc6207f4afeb26bf6587bf7efe309e812b73e5ffbb",
        4039,
    ),
    (
        "src/segmented_sieve.cpp",
        "ae1b9c2db26c0b15dace0a44b436a3f8d65a2691c8e97dfe1ea3a0a3206f078f",
        1401,
    ),
)

# Public immutable closure description used by the deterministic optimized
# source verifier.  The tuple remains the single definition of the prepared
# hardened source file set.
HARDENED_SOURCE_FILES = _EXPECTED_HARDENED_FILES

# Kept here as a campaign-level pin to avoid an import cycle: the optimized
# source generator imports the hardened verifier above.  Its verifier
# independently recomputes this value from the transformed closure and exact
# transformer bytes.
EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256 = (
    "8c19bf2825ff8a34ef9413f35620487f2062868f723b158228a071a5cf021359"
)


class GoldbachGPUCampaignError(RuntimeError):
    """A plan, executable, runner output, receipt, or aggregate failed closed."""


def _domain_hash(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + canonical_json_bytes(value)).hexdigest()


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GoldbachGPUCampaignError(
            f"{name} must be a lowercase 64-digit SHA-256 string"
        )
    return value


def _require_int(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GoldbachGPUCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise GoldbachGPUCampaignError(f"{name} must be at least {minimum}")
    return value


def _exact_keys(name: str, value: object, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise GoldbachGPUCampaignError(f"{name} must be an object")
    actual = set(value)
    if actual != keys:
        raise GoldbachGPUCampaignError(
            f"{name} has wrong fields (missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)})"
        )
    return value


def _source_identity_core(
    files: Sequence[tuple[str, str, int]] = _EXPECTED_HARDENED_FILES,
) -> dict[str, object]:
    return {
        "upstream_commit": UPSTREAM_COMMIT,
        "hardening_patch_sha256": HARDENING_PATCH_SHA256,
        "files": [
            {"path": path, "sha256": digest, "size_bytes": size}
            for path, digest, size in files
        ],
    }


EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256 = _domain_hash(
    _SOURCE_DOMAIN, _source_identity_core()
)


def verify_hardened_source_tree(source_root: Path) -> str:
    """Verify the exact prepared source closure and return its identity hash."""

    try:
        source_metadata = source_root.lstat()
    except OSError as exc:
        raise GoldbachGPUCampaignError(
            f"cannot inspect hardened source directory {source_root}: {exc}"
        ) from exc
    if stat.S_ISLNK(source_metadata.st_mode) or not stat.S_ISDIR(source_metadata.st_mode):
        raise GoldbachGPUCampaignError(
            "hardened source root must be a nonsymlink directory"
        )
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise GoldbachGPUCampaignError(
            f"hardened source directory does not exist: {source_root}"
        )
    try:
        patch_digest, _ = hash_file_once(_PATCH_PATH, limit=1 << 20)
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc
    if patch_digest != HARDENING_PATCH_SHA256:
        raise GoldbachGPUCampaignError("reviewed GoldbachGPU hardening patch changed")

    try:
        pin = load_json(_PIN_PATH)
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc
    if not isinstance(pin, Mapping) or pin.get("commit") != UPSTREAM_COMMIT:
        raise GoldbachGPUCampaignError("GoldbachGPU upstream pin changed")

    expected_paths = {row[0] for row in _EXPECTED_HARDENED_FILES}
    actual_paths: set[str] = set()
    for directory, directories, filenames in os.walk(source_root, followlinks=False):
        base = Path(directory)
        for name in directories:
            path = base / name
            if path.is_symlink():
                raise GoldbachGPUCampaignError(
                    f"hardened source contains a symlink: {path.relative_to(source_root)}"
                )
        for name in filenames:
            path = base / name
            relative = path.relative_to(source_root).as_posix()
            if path.is_symlink():
                raise GoldbachGPUCampaignError(
                    f"hardened source contains a symlink: {relative}"
                )
            actual_paths.add(relative)
    if actual_paths != expected_paths:
        raise GoldbachGPUCampaignError(
            "hardened source file set changed "
            f"(missing={sorted(expected_paths - actual_paths)}, "
            f"extra={sorted(actual_paths - expected_paths)})"
        )

    for relative, expected_digest, expected_size in _EXPECTED_HARDENED_FILES:
        path = source_root / relative
        try:
            digest, size = hash_file_once(path, limit=1 << 20)
        except CampaignIOError as exc:
            raise GoldbachGPUCampaignError(str(exc)) from exc
        if (digest, size) != (expected_digest, expected_size):
            raise GoldbachGPUCampaignError(
                f"hardened source entry differs from the reviewed closure: {relative}"
            )
    return EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256


def source_identity_for_algorithm(algorithm: str) -> str:
    """Return the exact reviewed source identity for one plan algorithm."""

    if algorithm in {
        OPTIMIZED_PRODUCTION_ALGORITHM,
        ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
    }:
        return EXPECTED_OPTIMIZED_SOURCE_IDENTITY_SHA256
    if algorithm in {
        PRODUCTION_ALGORITHM,
        ANALYTIC_10POW27_ALGORITHM,
        BOUNDED_ALGORITHM,
    }:
        return EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256
    raise GoldbachGPUCampaignError(
        "unsupported GoldbachGPU plan algorithm"
    )


def verify_source_tree_for_algorithm(
    source_root: Path, algorithm: str,
) -> str:
    """Verify exactly the source closure selected by ``algorithm``."""

    expected = source_identity_for_algorithm(algorithm)
    if expected == EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256:
        return verify_hardened_source_tree(source_root)
    # Local import avoids a module cycle: the deterministic transformer starts
    # from ``verify_hardened_source_tree``.
    from .goldbach_optimized_source import (
        EXPECTED_SOURCE_IDENTITY_SHA256,
        GoldbachOptimizedSourceError,
        verify_optimized_source_tree,
    )

    if EXPECTED_SOURCE_IDENTITY_SHA256 != expected:
        raise GoldbachGPUCampaignError(
            "optimized source identity pins disagree"
        )
    try:
        return verify_optimized_source_tree(source_root)
    except (GoldbachOptimizedSourceError, OSError, ValueError) as error:
        raise GoldbachGPUCampaignError(str(error)) from error


def verify_executable(executable: Path, expected_sha256: str) -> str:
    """Require a nonsymlink executable regular file with the expected hash."""

    expected_sha256 = _require_sha256("expected executable SHA-256", expected_sha256)
    try:
        metadata = executable.lstat()
    except OSError as exc:
        raise GoldbachGPUCampaignError(f"cannot inspect executable {executable}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise GoldbachGPUCampaignError("GoldbachGPU executable must be a regular nonsymlink file")
    if metadata.st_mode & 0o111 == 0:
        raise GoldbachGPUCampaignError("GoldbachGPU executable is not executable")
    try:
        actual, _ = hash_file_once(executable)
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc
    if actual != expected_sha256:
        raise GoldbachGPUCampaignError(
            f"GoldbachGPU executable hash differs: expected {expected_sha256}, got {actual}"
        )
    return actual


def _hash_open_file(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1 << 20)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


@contextmanager
def _staged_executable(
    executable: Path, expected_sha256: str,
):
    """Copy, unlink, and execute one hash-checked inode through its open FD."""

    expected_sha256 = _require_sha256(
        "expected executable SHA-256", expected_sha256
    )
    proc_fd = Path("/proc/self/fd")
    if not proc_fd.is_dir():
        raise GoldbachGPUCampaignError(
            "descriptor-bound GoldbachGPU execution requires /proc/self/fd"
        )
    stage = Path(tempfile.mkdtemp(prefix=".goldbach-gpu-executable-"))
    os.chmod(stage, 0o700)
    target = stage / "goldbach-gpu"
    source_fd = -1
    destination_fd = -1
    execution_fd = -1
    try:
        source_fd = os.open(
            executable,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(source_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o111 == 0
        ):
            raise GoldbachGPUCampaignError(
                "GoldbachGPU executable must be an executable regular file"
            )
        destination_fd = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            0o500,
        )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, 1 << 20)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                count = os.write(destination_fd, view)
                if count <= 0:
                    raise GoldbachGPUCampaignError(
                        "short write while staging GoldbachGPU executable"
                    )
                view = view[count:]
        os.fchmod(destination_fd, 0o500)
        os.fsync(destination_fd)
        if digest.hexdigest() != expected_sha256:
            raise GoldbachGPUCampaignError(
                "GoldbachGPU executable changed before descriptor-bound execution"
            )
        os.close(destination_fd)
        destination_fd = -1
        execution_fd = os.open(
            target,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        if _hash_open_file(execution_fd) != expected_sha256:
            raise GoldbachGPUCampaignError(
                "staged GoldbachGPU executable hash differs"
            )
        # The process inherits this exact inode; no pathname remains to swap.
        target.unlink()
        stage.rmdir()
        yield Path(f"/proc/self/fd/{execution_fd}"), execution_fd
        if _hash_open_file(execution_fd) != expected_sha256:
            raise GoldbachGPUCampaignError(
                "descriptor-bound GoldbachGPU executable changed during execution"
            )
    except OSError as error:
        raise GoldbachGPUCampaignError(
            f"cannot stage descriptor-bound GoldbachGPU executable: {error}"
        ) from error
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if destination_fd >= 0:
            os.close(destination_fd)
        if execution_fd >= 0:
            os.close(execution_fd)
        target.unlink(missing_ok=True)
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


@dataclass(frozen=True)
class GoldbachShard:
    index: int
    rank_lower: int
    rank_upper: int
    even_start: int
    even_limit: int
    even_count: int

    def __post_init__(self) -> None:
        index = _require_int("shard index", self.index, minimum=0)
        lower = _require_int("rank_lower", self.rank_lower, minimum=0)
        upper = _require_int("rank_upper", self.rank_upper, minimum=1)
        start = _require_int("even_start", self.even_start, minimum=4)
        limit = _require_int("even_limit", self.even_limit, minimum=4)
        count = _require_int("even_count", self.even_count, minimum=2)
        if lower >= upper or upper - lower != count:
            raise GoldbachGPUCampaignError("shard rank interval/count is inconsistent")
        if start % 2 or limit % 2 or start >= limit:
            raise GoldbachGPUCampaignError("shard must contain at least two even integers")
        if (limit - start) // 2 + 1 != count:
            raise GoldbachGPUCampaignError("shard even interval/count is inconsistent")
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "rank_lower", lower)
        object.__setattr__(self, "rank_upper", upper)
        object.__setattr__(self, "even_start", start)
        object.__setattr__(self, "even_limit", limit)
        object.__setattr__(self, "even_count", count)

    def to_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "rank_lower": self.rank_lower,
            "rank_upper": self.rank_upper,
            "even_start": self.even_start,
            "even_limit": self.even_limit,
            "even_count": self.even_count,
        }

    @classmethod
    def from_dict(cls, value: object) -> "GoldbachShard":
        item = _exact_keys(
            "Goldbach shard",
            value,
            frozenset(
                {
                    "index",
                    "rank_lower",
                    "rank_upper",
                    "even_start",
                    "even_limit",
                    "even_count",
                }
            ),
        )
        return cls(**{key: item[key] for key in item})  # type: ignore[arg-type]


_PLAN_CORE_KEYS = frozenset(
    {
        "schema",
        "algorithm",
        "classification",
        "production",
        "domain",
        "rank_encoding",
        "shard_count",
        "shards",
        "upstream_commit",
        "hardening_patch_sha256",
        "hardened_source_identity_sha256",
        "executable_sha256",
        "primality",
        "runner",
        "execution_attested",
        "lean_atom_discharged",
    }
)


@dataclass(frozen=True)
class GoldbachPlan:
    algorithm: str
    classification: str
    production: bool
    even_start: int
    even_limit: int
    shards: tuple[GoldbachShard, ...]
    executable_sha256: str

    def __post_init__(self) -> None:
        if self.algorithm not in {
            PRODUCTION_ALGORITHM,
            ANALYTIC_10POW27_ALGORITHM,
            OPTIMIZED_PRODUCTION_ALGORITHM,
            ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
            BOUNDED_ALGORITHM,
        }:
            raise GoldbachGPUCampaignError("unsupported GoldbachGPU plan algorithm")
        if self.classification not in {
            "production-external-computation-unattested",
            "bounded-sample-not-production",
        }:
            raise GoldbachGPUCampaignError("unsupported GoldbachGPU plan classification")
        if not isinstance(self.production, bool):
            raise GoldbachGPUCampaignError("production must be a boolean")
        start = _require_int("plan even_start", self.even_start, minimum=4)
        limit = _require_int("plan even_limit", self.even_limit, minimum=4)
        if start % 2 or limit % 2 or start >= limit:
            raise GoldbachGPUCampaignError("plan domain must contain at least two evens")
        shards = tuple(self.shards)
        if not shards:
            raise GoldbachGPUCampaignError("plan has no shards")
        expected_rank = 0
        expected_even = start
        ranges: set[tuple[int, int]] = set()
        indices: set[int] = set()
        counts: list[int] = []
        for expected_index, shard in enumerate(shards):
            if not isinstance(shard, GoldbachShard):
                raise GoldbachGPUCampaignError("plan contains a nonshard value")
            if shard.index in indices or (shard.even_start, shard.even_limit) in ranges:
                raise GoldbachGPUCampaignError("plan contains a duplicate shard")
            if shard.index != expected_index:
                raise GoldbachGPUCampaignError("plan shard indices are reordered or missing")
            if shard.rank_lower != expected_rank:
                relation = "gap" if shard.rank_lower > expected_rank else "overlap"
                raise GoldbachGPUCampaignError(f"rank {relation} before shard {shard.index}")
            if shard.even_start != expected_even:
                relation = "gap" if shard.even_start > expected_even else "overlap"
                raise GoldbachGPUCampaignError(f"even-domain {relation} before shard {shard.index}")
            expected_rank = shard.rank_upper
            expected_even = shard.even_limit + 2
            counts.append(shard.even_count)
            indices.add(shard.index)
            ranges.add((shard.even_start, shard.even_limit))
        if expected_even != limit + 2:
            relation = "gap" if expected_even < limit + 2 else "overlap"
            raise GoldbachGPUCampaignError(f"{relation} at the plan endpoint")
        expected_count = (limit - start) // 2 + 1
        if expected_rank != expected_count:
            raise GoldbachGPUCampaignError("plan rank domain does not cover its even domain")
        if max(counts) - min(counts) > 1:
            raise GoldbachGPUCampaignError("plan shards are not balanced within one even")
        _require_sha256("executable_sha256", self.executable_sha256)
        if self.production:
            expected_production = {
                PRODUCTION_ALGORITHM: (
                    PRODUCTION_EVEN_START,
                    PRODUCTION_EVEN_LIMIT,
                    PRODUCTION_SHARDS,
                    PRODUCTION_EVEN_COUNT,
                ),
                OPTIMIZED_PRODUCTION_ALGORITHM: (
                    PRODUCTION_EVEN_START,
                    PRODUCTION_EVEN_LIMIT,
                    PRODUCTION_SHARDS,
                    PRODUCTION_EVEN_COUNT,
                ),
                ANALYTIC_10POW27_ALGORITHM: (
                    ANALYTIC_10POW27_EVEN_START,
                    ANALYTIC_10POW27_EVEN_LIMIT,
                    ANALYTIC_10POW27_SHARDS,
                    ANALYTIC_10POW27_EVEN_COUNT,
                ),
                ANALYTIC_10POW27_OPTIMIZED_ALGORITHM: (
                    ANALYTIC_10POW27_EVEN_START,
                    ANALYTIC_10POW27_EVEN_LIMIT,
                    ANALYTIC_10POW27_SHARDS,
                    ANALYTIC_10POW27_EVEN_COUNT,
                ),
            }.get(self.algorithm)
            if (
                expected_production is None
                or self.classification != "production-external-computation-unattested"
                or (start, limit, len(shards), expected_count) != expected_production
            ):
                raise GoldbachGPUCampaignError("production plan constants changed")
        elif (
            self.algorithm != BOUNDED_ALGORITHM
            or self.classification != "bounded-sample-not-production"
            or (start, limit) in {
                (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT),
                (ANALYTIC_10POW27_EVEN_START, ANALYTIC_10POW27_EVEN_LIMIT),
            }
        ):
            raise GoldbachGPUCampaignError("bounded plan is mislabeled")
        object.__setattr__(self, "even_start", start)
        object.__setattr__(self, "even_limit", limit)
        object.__setattr__(self, "shards", shards)

    def core_dict(self) -> dict[str, object]:
        return {
            "schema": PLAN_SCHEMA,
            "algorithm": self.algorithm,
            "classification": self.classification,
            "production": self.production,
            "domain": {
                "even_start_inclusive": self.even_start,
                "even_limit_inclusive": self.even_limit,
                "even_count": (self.even_limit - self.even_start) // 2 + 1,
            },
            "rank_encoding": "n=even_start+2*rank; shard ranks are half-open",
            "shard_count": len(self.shards),
            "shards": [shard.to_dict() for shard in self.shards],
            "upstream_commit": UPSTREAM_COMMIT,
            "hardening_patch_sha256": HARDENING_PATCH_SHA256,
            # The wire key is retained for v1 compatibility.  For an
            # optimized plan its value is the complete transformed source
            # identity, not the prepared base-tree identity.
            "hardened_source_identity_sha256": source_identity_for_algorithm(
                self.algorithm
            ),
            "executable_sha256": self.executable_sha256,
            "primality": {
                "command_mode": "--primetest=mr",
                "miller_rabin_bases": list(MILLER_RABIN_BASES),
                "proven_composite_threshold_exclusive": str(
                    MILLER_RABIN_PROVEN_THRESHOLD_EXCLUSIVE
                ),
            },
            "runner": {
                "gpus_per_process": GPU_COUNT_PER_PROCESS,
                "production_nodes": PRODUCTION_NODES,
                "scheduler_group_count": PRODUCTION_GROUPS,
                "checkpoint_leaves_per_group": PRODUCTION_LEAVES_PER_GROUP,
                "group_assignment": "leaf_index=group_index+k*scheduler_group_count",
                "segment_size": SEGMENT_SIZE,
                "p_small": P_SMALL,
                "batch_size": BATCH_SIZE,
                "progress_output": False,
                "production_hardware_policy": {
                    "cuda_device_name_prefix": "NVIDIA H100",
                    "minimum_total_vram_mb": PRODUCTION_MIN_GPU_VRAM_MB,
                    "required_compute_capability": PRODUCTION_GPU_COMPUTE_CAPABILITY,
                    "local_probe": "nvidia-smi-exact-device-identity-v1",
                    "authentication": "required-from-later-measured-attestation",
                },
            },
            "execution_attested": False,
            "lean_atom_discharged": False,
        }

    @property
    def plan_sha256(self) -> str:
        return _domain_hash(_PLAN_DOMAIN, self.core_dict())

    def to_dict(self) -> dict[str, object]:
        result = self.core_dict()
        result["plan_sha256"] = self.plan_sha256
        return result

    @classmethod
    def from_dict(cls, value: object) -> "GoldbachPlan":
        item = _exact_keys("Goldbach plan", value, _PLAN_CORE_KEYS | {"plan_sha256"})
        core = {key: item[key] for key in _PLAN_CORE_KEYS}
        if item["schema"] != PLAN_SCHEMA:
            raise GoldbachGPUCampaignError("unsupported GoldbachGPU plan schema")
        if item["execution_attested"] is not False or item["lean_atom_discharged"] is not False:
            raise GoldbachGPUCampaignError("plan makes an unsafe trust claim")
        domain = _exact_keys(
            "plan domain",
            item["domain"],
            frozenset(
                {"even_start_inclusive", "even_limit_inclusive", "even_count"}
            ),
        )
        raw_shards = item["shards"]
        if isinstance(raw_shards, (str, bytes)) or not isinstance(raw_shards, Sequence):
            raise GoldbachGPUCampaignError("plan shards must be an array")
        result = cls(
            algorithm=item["algorithm"],  # type: ignore[arg-type]
            classification=item["classification"],  # type: ignore[arg-type]
            production=item["production"],  # type: ignore[arg-type]
            even_start=domain["even_start_inclusive"],  # type: ignore[arg-type]
            even_limit=domain["even_limit_inclusive"],  # type: ignore[arg-type]
            shards=tuple(GoldbachShard.from_dict(row) for row in raw_shards),
            executable_sha256=item["executable_sha256"],  # type: ignore[arg-type]
        )
        if item["shard_count"] != len(result.shards):
            raise GoldbachGPUCampaignError("plan shard_count changed")
        if domain["even_count"] != (result.even_limit - result.even_start) // 2 + 1:
            raise GoldbachGPUCampaignError("plan even_count changed")
        if item["rank_encoding"] != "n=even_start+2*rank; shard ranks are half-open":
            raise GoldbachGPUCampaignError("plan rank encoding changed")
        expected_core = result.core_dict()
        if core != expected_core:
            raise GoldbachGPUCampaignError("plan constants or source policy changed")
        if item["plan_sha256"] != result.plan_sha256:
            raise GoldbachGPUCampaignError("plan SHA-256 is invalid")
        return result


def _make_plan(
    *, even_start: int, even_limit: int, shard_count: int,
    executable_sha256: str, production: bool,
    production_algorithm: str = PRODUCTION_ALGORITHM,
) -> GoldbachPlan:
    even_start = _require_int("even_start", even_start, minimum=4)
    even_limit = _require_int("even_limit", even_limit, minimum=4)
    shard_count = _require_int("shard_count", shard_count, minimum=1)
    _require_sha256("executable_sha256", executable_sha256)
    if even_start % 2 or even_limit % 2 or even_start >= even_limit:
        raise GoldbachGPUCampaignError("require an increasing inclusive even domain")
    count = (even_limit - even_start) // 2 + 1
    # Upstream rejects START == LIMIT, so each independently runnable shard
    # must contain at least two evens.
    if count < 2 * shard_count:
        raise GoldbachGPUCampaignError("each shard must contain at least two evens")
    quotient, remainder = divmod(count, shard_count)
    rank = 0
    shards: list[GoldbachShard] = []
    for index in range(shard_count):
        size = quotient + (1 if index < remainder else 0)
        following = rank + size
        shards.append(
            GoldbachShard(
                index=index,
                rank_lower=rank,
                rank_upper=following,
                even_start=even_start + 2 * rank,
                even_limit=even_start + 2 * (following - 1),
                even_count=size,
            )
        )
        rank = following
    return GoldbachPlan(
        algorithm=production_algorithm if production else BOUNDED_ALGORITHM,
        classification=(
            "production-external-computation-unattested"
            if production
            else "bounded-sample-not-production"
        ),
        production=production,
        even_start=even_start,
        even_limit=even_limit,
        shards=tuple(shards),
        executable_sha256=executable_sha256,
    )


def make_production_plan(*, executable_sha256: str) -> GoldbachPlan:
    """Return the literal balanced 65,536-leaf production plan."""

    return _make_plan(
        even_start=PRODUCTION_EVEN_START,
        even_limit=PRODUCTION_EVEN_LIMIT,
        shard_count=PRODUCTION_SHARDS,
        executable_sha256=executable_sha256,
        production=True,
    )


def make_optimized_production_plan(
    *, executable_sha256: str
) -> GoldbachPlan:
    """Return the historical domain with the reviewed optimized source."""

    return _make_plan(
        even_start=PRODUCTION_EVEN_START,
        even_limit=PRODUCTION_EVEN_LIMIT,
        shard_count=PRODUCTION_SHARDS,
        executable_sha256=executable_sha256,
        production=True,
        production_algorithm=OPTIMIZED_PRODUCTION_ALGORITHM,
    )


def make_analytic_10pow27_production_plan(
    *, executable_sha256: str
) -> GoldbachPlan:
    """Return the exact lowered binary-Goldbach production plan."""

    return _make_plan(
        even_start=ANALYTIC_10POW27_EVEN_START,
        even_limit=ANALYTIC_10POW27_EVEN_LIMIT,
        shard_count=ANALYTIC_10POW27_SHARDS,
        executable_sha256=executable_sha256,
        production=True,
        production_algorithm=ANALYTIC_10POW27_ALGORITHM,
    )


def make_optimized_analytic_10pow27_production_plan(
    *, executable_sha256: str
) -> GoldbachPlan:
    """Return the lowered domain with the reviewed optimized source."""

    return _make_plan(
        even_start=ANALYTIC_10POW27_EVEN_START,
        even_limit=ANALYTIC_10POW27_EVEN_LIMIT,
        shard_count=ANALYTIC_10POW27_SHARDS,
        executable_sha256=executable_sha256,
        production=True,
        production_algorithm=ANALYTIC_10POW27_OPTIMIZED_ALGORITHM,
    )


def make_bounded_sample_plan(
    *, even_start: int, even_limit: int, shard_count: int,
    executable_sha256: str,
) -> GoldbachPlan:
    """Return an explicitly nonproduction plan for bounded testing/benchmarking."""

    if (even_start, even_limit) in {
        (PRODUCTION_EVEN_START, PRODUCTION_EVEN_LIMIT),
        (ANALYTIC_10POW27_EVEN_START, ANALYTIC_10POW27_EVEN_LIMIT),
    }:
        raise GoldbachGPUCampaignError(
            "an exact production range must use its production plan"
        )
    return _make_plan(
        even_start=even_start,
        even_limit=even_limit,
        shard_count=shard_count,
        executable_sha256=executable_sha256,
        production=False,
    )


def runner_arguments(shard: GoldbachShard) -> tuple[str, ...]:
    """Return the only accepted upstream argv for one shard."""

    return (
        str(shard.even_limit),
        f"--start={shard.even_start}",
        f"--seg-size={SEGMENT_SIZE}",
        f"--p-small={P_SMALL}",
        f"--batch-size={BATCH_SIZE}",
        "--gpus=1",
        "--primetest=mr",
    )


def _expected_small_high(limit: int) -> int:
    effective_p_small = min(P_SMALL, limit)
    result = max(isqrt(limit) + 1, effective_p_small)
    return result if result % 2 else result + 1


def parse_runner_stdout(raw: bytes, shard: GoldbachShard) -> dict[str, object]:
    """Parse exactly one successful no-progress GoldbachGPU stdout transcript."""

    if len(raw) > MAX_OUTPUT_BYTES:
        raise GoldbachGPUCampaignError("GoldbachGPU stdout exceeds the byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GoldbachGPUCampaignError("GoldbachGPU stdout is not UTF-8") from exc
    number = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    pattern = re.compile(
        r"\A\[Hardware\] GPU 0: (?P<gpu>[^\r\n\[\]]+) "
        r"\((?P<vram>[1-9][0-9]*) MB VRAM\)\n"
        r"Building small primes bitset up to (?P<small>[1-9][0-9]*)\.\.\.\n"
        r"Pre-generating CPU primes up to 100000000\.\.\.\n"
        rf"Initialization completed in (?P<init>{number}) ms\.\n\n"
        r"--- Launching Multi-GPU Verifier ---\n"
        r"Checking range : \[(?P<start>[0-9]+), (?P<limit>[0-9]+)\]\n"
        r"Total numbers  : (?P<count>[0-9]+)\n\n\n"
        r"--- Verification Complete ---\n"
        r"All even numbers from (?P<success_start>[0-9]+) up to "
        r"(?P<success_limit>[0-9]+) satisfy Goldbach\. ✓\n"
        rf"Total computation time : (?P<seconds>{number}) seconds\n"
        r"Phase 2 fallbacks      : (?P<fallbacks>[0-9]+)\n\Z"
    )
    match = pattern.fullmatch(text)
    if match is None:
        raise GoldbachGPUCampaignError(
            "GoldbachGPU stdout does not match the reviewed successful-output grammar"
        )
    values = match.groupdict()
    expected = {
        "small": _expected_small_high(shard.even_limit),
        "start": shard.even_start,
        "limit": shard.even_limit,
        "count": shard.even_count,
        "success_start": shard.even_start,
        "success_limit": shard.even_limit,
    }
    for key, wanted in expected.items():
        if int(values[key]) != wanted:
            raise GoldbachGPUCampaignError(
                f"GoldbachGPU stdout {key} differs: expected {wanted}, got {values[key]}"
            )
    for key in ("init", "seconds"):
        if _NONNEGATIVE_REAL_RE.fullmatch(values[key]) is None:
            raise GoldbachGPUCampaignError(f"GoldbachGPU {key} is not canonical")
    return {
        "gpu_name": values["gpu"],
        "gpu_vram_mb": int(values["vram"]),
        "small_prime_bitset_limit": int(values["small"]),
        "initialization_milliseconds": values["init"],
        "reported_computation_seconds": values["seconds"],
        "phase2_fallbacks": int(values["fallbacks"]),
        "all_even_numbers_reported_satisfied": True,
    }


def _validate_production_gpu(parsed: Mapping[str, object]) -> None:
    """Enforce the hardware facts available in the pinned runner transcript.

    The upstream executable reports the CUDA device name and total VRAM.  A
    separate receipt-bound ``nvidia-smi`` probe adds compute capability, PCI
    identity and UUID.  Neither local report authenticates firmware or
    confidential-compute mode; those remain mandatory inputs to the later
    signed measured-run receipt.
    """

    name = parsed.get("gpu_name")
    vram = parsed.get("gpu_vram_mb")
    if not isinstance(name, str) or PRODUCTION_GPU_NAME_RE.match(name) is None:
        raise GoldbachGPUCampaignError(
            "production receipt was not produced by a reported NVIDIA H100"
        )
    if (
        isinstance(vram, bool)
        or not isinstance(vram, int)
        or vram < PRODUCTION_MIN_GPU_VRAM_MB
    ):
        raise GoldbachGPUCampaignError(
            "production H100 receipt reports insufficient full-device VRAM"
        )


_GPU_PROBE_KEYS = frozenset(
    {
        "schema",
        "device_selector",
        "name",
        "compute_capability",
        "memory_total_mb",
        "uuid",
        "pci_bus_id",
        "nvidia_smi_sha256",
    }
)
_GPU_UUID_RE = re.compile(r"^GPU-[0-9A-Fa-f-]{36}\Z")
_PCI_BUS_RE = re.compile(
    r"^[0-9A-Fa-f]{4,8}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]\Z"
)


def collect_production_gpu_identity(cuda_visible_device: int) -> dict[str, object]:
    """Collect exact local H100 identity facts before and after execution.

    This probe is a fail-fast hardware constraint, not authentication.  Its
    executable hash and result become receipt data so a measured-run policy
    can bind them later.
    """

    cuda_visible_device = _require_int(
        "cuda_visible_device", cuda_visible_device, minimum=0
    )
    nvidia_smi_name = shutil.which("nvidia-smi")
    if nvidia_smi_name is None:
        raise GoldbachGPUCampaignError("production execution requires nvidia-smi")
    nvidia_smi = Path(nvidia_smi_name)
    try:
        metadata = nvidia_smi.lstat()
    except OSError as exc:
        raise GoldbachGPUCampaignError(f"cannot inspect nvidia-smi: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        nvidia_smi = nvidia_smi.resolve()
    if not nvidia_smi.is_file():
        raise GoldbachGPUCampaignError("nvidia-smi is not a regular file")
    try:
        nvidia_smi_sha256, _ = hash_file_once(nvidia_smi)
        completed = subprocess.run(
            [
                str(nvidia_smi),
                f"--id={cuda_visible_device}",
                "--query-gpu=name,compute_cap,memory.total,uuid,pci.bus_id",
                "--format=csv,noheader,nounits",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (CampaignIOError, OSError, subprocess.TimeoutExpired) as exc:
        raise GoldbachGPUCampaignError(f"nvidia-smi probe failed: {exc}") from exc
    if completed.returncode != 0 or completed.stderr or len(completed.stdout) > 4096:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GoldbachGPUCampaignError(
            f"nvidia-smi probe did not return one clean record: {detail}"
        )
    try:
        text = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GoldbachGPUCampaignError("nvidia-smi output is not UTF-8") from exc
    lines = text.splitlines()
    if len(lines) != 1:
        raise GoldbachGPUCampaignError("nvidia-smi probe returned other than one GPU")
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) != 5:
        raise GoldbachGPUCampaignError("nvidia-smi probe record has the wrong fields")
    name, capability, memory_text, uuid, pci_bus_id = fields
    if _DECIMAL_INTEGER_RE.fullmatch(memory_text) is None:
        raise GoldbachGPUCampaignError("nvidia-smi GPU memory is not an integer")
    result: dict[str, object] = {
        "schema": "nvidia-smi-exact-device-identity-v1",
        "device_selector": cuda_visible_device,
        "name": name,
        "compute_capability": capability,
        "memory_total_mb": int(memory_text),
        "uuid": uuid,
        "pci_bus_id": pci_bus_id,
        "nvidia_smi_sha256": nvidia_smi_sha256,
    }
    _validate_production_gpu_probe(result)
    return result


def _validate_production_gpu_probe(value: object) -> dict[str, object]:
    item = _exact_keys("production GPU probe", value, _GPU_PROBE_KEYS)
    if item["schema"] != "nvidia-smi-exact-device-identity-v1":
        raise GoldbachGPUCampaignError("production GPU probe schema changed")
    _require_int("GPU probe device selector", item["device_selector"], minimum=0)
    _require_sha256("nvidia-smi SHA-256", item["nvidia_smi_sha256"])
    name = item["name"]
    if not isinstance(name, str) or PRODUCTION_GPU_NAME_RE.match(name) is None:
        raise GoldbachGPUCampaignError(
            "production GPU probe does not identify an NVIDIA H100"
        )
    if item["compute_capability"] != PRODUCTION_GPU_COMPUTE_CAPABILITY:
        raise GoldbachGPUCampaignError(
            "production GPU compute capability is not exactly 9.0"
        )
    memory = _require_int("GPU probe memory", item["memory_total_mb"], minimum=0)
    if memory < PRODUCTION_MIN_GPU_VRAM_MB:
        raise GoldbachGPUCampaignError("production GPU probe reports insufficient VRAM")
    if not isinstance(item["uuid"], str) or _GPU_UUID_RE.fullmatch(item["uuid"]) is None:
        raise GoldbachGPUCampaignError("production GPU UUID is malformed")
    if (
        not isinstance(item["pci_bus_id"], str)
        or _PCI_BUS_RE.fullmatch(item["pci_bus_id"]) is None
    ):
        raise GoldbachGPUCampaignError("production GPU PCI bus id is malformed")
    return dict(item)


_RECEIPT_CORE_KEYS = frozenset(
    {
        "schema",
        "algorithm",
        "classification",
        "production_campaign_shard",
        "plan_sha256",
        "hardened_source_identity_sha256",
        "executable_sha256",
        "shard",
        "runner_arguments",
        "cuda_visible_device",
        "production_gpu_probe",
        "stdout_utf8",
        "stdout_sha256",
        "parsed_output",
        "successful_process_exit",
        "execution_attested",
        "lean_atom_discharged",
    }
)


def _receipt_from_output(
    *, plan: GoldbachPlan, shard: GoldbachShard, raw_stdout: bytes,
    cuda_visible_device: int, production_gpu_probe: Mapping[str, object] | None,
) -> dict[str, object]:
    parsed = parse_runner_stdout(raw_stdout, shard)
    if plan.production:
        _validate_production_gpu(parsed)
        probe: object = _validate_production_gpu_probe(production_gpu_probe)
        if probe["device_selector"] != cuda_visible_device:
            raise GoldbachGPUCampaignError("production GPU probe selected another device")
        if probe["name"] != parsed["gpu_name"]:
            raise GoldbachGPUCampaignError("CUDA and nvidia-smi report different GPU names")
    else:
        if production_gpu_probe is not None:
            raise GoldbachGPUCampaignError("bounded receipt must not claim a production probe")
        probe = None
    core: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "algorithm": plan.algorithm,
        "classification": plan.classification,
        "production_campaign_shard": plan.production,
        "plan_sha256": plan.plan_sha256,
        "hardened_source_identity_sha256": source_identity_for_algorithm(
            plan.algorithm
        ),
        "executable_sha256": plan.executable_sha256,
        "shard": shard.to_dict(),
        "runner_arguments": list(runner_arguments(shard)),
        "cuda_visible_device": cuda_visible_device,
        "production_gpu_probe": probe,
        "stdout_utf8": raw_stdout.decode("utf-8"),
        "stdout_sha256": sha256_bytes(raw_stdout),
        "parsed_output": parsed,
        "successful_process_exit": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }
    result = dict(core)
    result["receipt_sha256"] = _domain_hash(_RECEIPT_DOMAIN, core)
    return result


def validate_receipt(value: object, *, plan: GoldbachPlan) -> dict[str, Any]:
    """Strictly validate one canonical plan-bound shard receipt."""

    item = _exact_keys(
        "GoldbachGPU receipt", value, _RECEIPT_CORE_KEYS | {"receipt_sha256"}
    )
    if item["schema"] != RECEIPT_SCHEMA:
        raise GoldbachGPUCampaignError("unsupported GoldbachGPU receipt schema")
    if item["successful_process_exit"] is not True:
        raise GoldbachGPUCampaignError("receipt does not report a successful process")
    if item["execution_attested"] is not False or item["lean_atom_discharged"] is not False:
        raise GoldbachGPUCampaignError("receipt makes an unsafe trust claim")
    index_value = item.get("shard")
    shard = GoldbachShard.from_dict(index_value)
    if shard.index >= len(plan.shards) or shard != plan.shards[shard.index]:
        raise GoldbachGPUCampaignError("receipt shard differs from the fixed plan")
    expected_scalars = {
        "algorithm": plan.algorithm,
        "classification": plan.classification,
        "production_campaign_shard": plan.production,
        "plan_sha256": plan.plan_sha256,
        "hardened_source_identity_sha256": source_identity_for_algorithm(
            plan.algorithm
        ),
        "executable_sha256": plan.executable_sha256,
    }
    for name, expected in expected_scalars.items():
        if item[name] != expected:
            raise GoldbachGPUCampaignError(f"receipt {name} differs from the plan")
    if item["runner_arguments"] != list(runner_arguments(shard)):
        raise GoldbachGPUCampaignError("receipt runner arguments changed")
    device = _require_int("cuda_visible_device", item["cuda_visible_device"], minimum=0)
    if device > 255:
        raise GoldbachGPUCampaignError("cuda_visible_device exceeds its guard")
    stdout = item["stdout_utf8"]
    if not isinstance(stdout, str):
        raise GoldbachGPUCampaignError("receipt stdout_utf8 must be a string")
    raw = stdout.encode("utf-8")
    if item["stdout_sha256"] != sha256_bytes(raw):
        raise GoldbachGPUCampaignError("receipt stdout SHA-256 is invalid")
    parsed = parse_runner_stdout(raw, shard)
    if plan.production:
        _validate_production_gpu(parsed)
        probe = _validate_production_gpu_probe(item["production_gpu_probe"])
        if probe["device_selector"] != device:
            raise GoldbachGPUCampaignError("receipt GPU probe selected another device")
        if probe["name"] != parsed["gpu_name"]:
            raise GoldbachGPUCampaignError("receipt CUDA/probe GPU names differ")
    elif item["production_gpu_probe"] is not None:
        raise GoldbachGPUCampaignError("bounded receipt contains a production GPU probe")
    if item["parsed_output"] != parsed:
        raise GoldbachGPUCampaignError("receipt parsed output differs from stdout")
    core = {key: item[key] for key in _RECEIPT_CORE_KEYS}
    if item["receipt_sha256"] != _domain_hash(_RECEIPT_DOMAIN, core):
        raise GoldbachGPUCampaignError("receipt SHA-256 is invalid")
    return dict(item)


def run_shard(
    *, plan: GoldbachPlan, shard_index: int, executable: Path,
    source_root: Path, output_directory: Path, cuda_visible_device: int = 0,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run one fixed shard and immutably retain its strictly parsed receipt."""

    shard_index = _require_int("shard_index", shard_index, minimum=0)
    cuda_visible_device = _require_int(
        "cuda_visible_device", cuda_visible_device, minimum=0
    )
    if cuda_visible_device > 255:
        raise GoldbachGPUCampaignError("cuda_visible_device exceeds its guard")
    if shard_index >= len(plan.shards):
        raise GoldbachGPUCampaignError("shard_index lies outside the fixed plan")
    if timeout_seconds is not None:
        timeout_seconds = _require_int("timeout_seconds", timeout_seconds, minimum=1)
    source_identity = verify_source_tree_for_algorithm(
        source_root, plan.algorithm
    )
    production_probe = (
        collect_production_gpu_identity(cuda_visible_device)
        if plan.production
        else None
    )
    shard = plan.shards[shard_index]
    arguments = runner_arguments(shard)
    environment = dict(os.environ)
    environment["CUDA_VISIBLE_DEVICES"] = str(cuda_visible_device)
    try:
        with _staged_executable(
            executable, plan.executable_sha256
        ) as (staged_executable, execution_fd):
            completed = subprocess.run(
                [str(staged_executable), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_seconds,
                env=environment,
                pass_fds=(execution_fd,),
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GoldbachGPUCampaignError(f"GoldbachGPU shard could not complete: {exc}") from exc
    if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise GoldbachGPUCampaignError("GoldbachGPU process output exceeds the byte limit")
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GoldbachGPUCampaignError(
            f"GoldbachGPU shard exited with {completed.returncode}: {detail}"
        )
    if completed.stderr:
        raise GoldbachGPUCampaignError("GoldbachGPU successful run emitted stderr")
    if (
        verify_source_tree_for_algorithm(source_root, plan.algorithm)
        != source_identity
    ):
        raise GoldbachGPUCampaignError(
            "GoldbachGPU source changed during execution"
        )
    if (
        plan.production
        and collect_production_gpu_identity(cuda_visible_device) != production_probe
    ):
        raise GoldbachGPUCampaignError("production GPU identity changed during execution")
    receipt = _receipt_from_output(
        plan=plan,
        shard=shard,
        raw_stdout=completed.stdout,
        cuda_visible_device=cuda_visible_device,
        production_gpu_probe=production_probe,
    )
    validate_receipt(receipt, plan=plan)
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"receipt-{shard_index:08d}.json"
    try:
        write_immutable_json(path, receipt)
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc
    return receipt


def production_group_leaf_indices(
    plan: GoldbachPlan, group_index: int,
) -> tuple[int, ...]:
    """Return the fixed strided checkpoint leaves for one scheduler group."""

    if not plan.production or len(plan.shards) != PRODUCTION_SHARDS:
        raise GoldbachGPUCampaignError(
            "scheduler groups require the literal production plan"
        )
    group_index = _require_int("group_index", group_index, minimum=0)
    if group_index >= PRODUCTION_GROUPS:
        raise GoldbachGPUCampaignError("group_index lies outside the fixed group plan")
    result = tuple(range(group_index, PRODUCTION_SHARDS, PRODUCTION_GROUPS))
    if len(result) != PRODUCTION_LEAVES_PER_GROUP:
        raise GoldbachGPUCampaignError("production group geometry changed")
    return result


def run_group(
    *, plan: GoldbachPlan, group_index: int, executable: Path,
    source_root: Path, output_directory: Path, cuda_visible_device: int = 0,
    timeout_seconds: int | None = None,
) -> dict[str, object]:
    """Run eight strided leaves, validating and skipping immutable receipts.

    One invocation is intended to sit inside one scheduler/attestation group.
    A restart never trusts mere filename presence: an existing leaf is skipped
    only after canonical parsing and full receipt validation against ``plan``.
    """

    indices = production_group_leaf_indices(plan, group_index)
    source_identity = verify_source_tree_for_algorithm(
        source_root, plan.algorithm
    )
    verify_executable(executable, plan.executable_sha256)
    rows = []
    for shard_index in indices:
        path = output_directory / f"receipt-{shard_index:08d}.json"
        if path.exists():
            receipt = load_receipt(path, plan=plan)
            status = "validated-existing-receipt"
        else:
            receipt = run_shard(
                plan=plan,
                shard_index=shard_index,
                executable=executable,
                source_root=source_root,
                output_directory=output_directory,
                cuda_visible_device=cuda_visible_device,
                timeout_seconds=timeout_seconds,
            )
            status = "completed-new-receipt"
        if receipt["shard"]["index"] != shard_index:
            raise GoldbachGPUCampaignError("group receipt has the wrong leaf index")
        rows.append(
            {
                "leaf_index": shard_index,
                "receipt_sha256": receipt["receipt_sha256"],
                "status": status,
            }
        )
    return {
        "schema": "sparkinterval.goldbach-gpu-run-group.v1",
        "group_index": group_index,
        "scheduler_group_count": PRODUCTION_GROUPS,
        "leaf_indices": list(indices),
        "receipts": rows,
        "all_group_receipts_valid": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


def load_plan(path: Path) -> GoldbachPlan:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc
    return GoldbachPlan.from_dict(value)


def load_receipt(path: Path, *, plan: GoldbachPlan) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc
    return validate_receipt(value, plan=plan)


def receipt_paths(output_directory: Path) -> tuple[Path, ...]:
    """Return exactly named receipts, rejecting malformed/duplicate indices."""

    if not output_directory.is_dir():
        raise GoldbachGPUCampaignError("receipt directory does not exist")
    indexed: dict[int, Path] = {}
    for path in output_directory.glob("receipt-*.json"):
        match = _RECEIPT_NAME_RE.fullmatch(path.name)
        if match is None:
            raise GoldbachGPUCampaignError(f"malformed receipt filename: {path.name}")
        index = int(match.group(1))
        if index in indexed:
            raise GoldbachGPUCampaignError(f"duplicate receipt index {index}")
        indexed[index] = path
    return tuple(indexed[index] for index in sorted(indexed))


def _merkle_root(receipt_sha256s: Sequence[str]) -> str:
    if not receipt_sha256s:
        raise GoldbachGPUCampaignError("cannot commit an empty receipt set")
    level = [
        hashlib.sha256(
            _MERKLE_LEAF_DOMAIN
            + bytes.fromhex(_require_sha256("receipt SHA", item))
        ).digest()
        for item in receipt_sha256s
    ]
    while len(level) > 1:
        if len(level) % 2:
            level[-1] = hashlib.sha256(_MERKLE_ODD_DOMAIN + level[-1]).digest()
        level = [
            hashlib.sha256(
                _MERKLE_NODE_DOMAIN
                + level[i]
                + (level[i + 1] if i + 1 < len(level) else level[i])
            ).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0].hex()


_AGGREGATE_CORE_KEYS = frozenset(
    {
        "schema",
        "algorithm",
        "classification",
        "production_campaign_complete",
        "plan_sha256",
        "hardened_source_identity_sha256",
        "executable_sha256",
        "domain",
        "shard_count",
        "receipt_sha256s",
        "receipt_merkle_root_sha256",
        "total_phase2_fallbacks",
        "all_processes_reported_success",
        "coverage_structurally_complete",
        "execution_attested",
        "lean_atom_discharged",
    }
)


def aggregate_receipts(
    *, plan: GoldbachPlan, receipts: Sequence[Mapping[str, Any]]
) -> dict[str, object]:
    """Validate exact coverage and return the plan-bound receipt Merkle aggregate."""

    if len(receipts) != len(plan.shards):
        raise GoldbachGPUCampaignError(
            f"receipt set is incomplete: expected {len(plan.shards)}, got {len(receipts)}"
        )
    by_index: dict[int, dict[str, Any]] = {}
    for value in receipts:
        receipt = validate_receipt(value, plan=plan)
        shard = GoldbachShard.from_dict(receipt["shard"])
        if shard.index in by_index:
            raise GoldbachGPUCampaignError(f"duplicate receipt for shard {shard.index}")
        by_index[shard.index] = receipt
    expected_indices = set(range(len(plan.shards)))
    if set(by_index) != expected_indices:
        raise GoldbachGPUCampaignError(
            f"receipt indices have a gap (missing={sorted(expected_indices - set(by_index))})"
        )
    ordered = [by_index[index] for index in range(len(plan.shards))]
    receipt_hashes = [str(receipt["receipt_sha256"]) for receipt in ordered]
    fallback_total = sum(
        int(receipt["parsed_output"]["phase2_fallbacks"]) for receipt in ordered
    )
    core: dict[str, object] = {
        "schema": AGGREGATE_SCHEMA,
        "algorithm": plan.algorithm,
        "classification": plan.classification,
        "production_campaign_complete": plan.production,
        "plan_sha256": plan.plan_sha256,
        "hardened_source_identity_sha256": source_identity_for_algorithm(
            plan.algorithm
        ),
        "executable_sha256": plan.executable_sha256,
        "domain": {
            "even_start_inclusive": plan.even_start,
            "even_limit_inclusive": plan.even_limit,
            "even_count": (plan.even_limit - plan.even_start) // 2 + 1,
        },
        "shard_count": len(plan.shards),
        "receipt_sha256s": receipt_hashes,
        "receipt_merkle_root_sha256": _merkle_root(receipt_hashes),
        "total_phase2_fallbacks": fallback_total,
        "all_processes_reported_success": True,
        "coverage_structurally_complete": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }
    result = dict(core)
    result["aggregate_sha256"] = _domain_hash(_AGGREGATE_DOMAIN, core)
    return result


def aggregate_directory(
    *, plan: GoldbachPlan, output_directory: Path,
    aggregate_path: Path | None = None,
) -> dict[str, object]:
    paths = receipt_paths(output_directory)
    receipts = [load_receipt(path, plan=plan) for path in paths]
    aggregate = aggregate_receipts(plan=plan, receipts=receipts)
    if aggregate_path is not None:
        try:
            write_immutable_json(aggregate_path, aggregate)
        except CampaignIOError as exc:
            raise GoldbachGPUCampaignError(str(exc)) from exc
    return aggregate


def validate_aggregate(
    value: object, *, plan: GoldbachPlan, receipts: Sequence[Mapping[str, Any]]
) -> dict[str, object]:
    item = _exact_keys(
        "GoldbachGPU aggregate", value, _AGGREGATE_CORE_KEYS | {"aggregate_sha256"}
    )
    expected = aggregate_receipts(plan=plan, receipts=receipts)
    if dict(item) != expected:
        raise GoldbachGPUCampaignError("aggregate differs from the receipts or fixed plan")
    return expected


def write_plan(path: Path, plan: GoldbachPlan) -> str:
    try:
        return write_immutable_json(path, plan.to_dict())
    except CampaignIOError as exc:
        raise GoldbachGPUCampaignError(str(exc)) from exc

# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministically materialize the qualified optimized Goldbach source.

This module starts from the exact prepared/hardened GoldbachGPU closure and
applies the reviewed diagnostic transforms in one fixed order.  The result is
a source-pinned Azure calibration candidate, not a production registration or
execution receipt.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import stat
import tempfile

from .campaign_io import canonical_json_bytes
from .goldbach_gpu_campaign import (
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
    HARDENED_SOURCE_FILES,
    verify_hardened_source_tree,
)
from .goldbach_shifted_coverage_optimizer import (
    rewrite_packed_shifted_unverified_count,
    rewrite_shifted_phase1,
)
from .goldbach_warp_tail_optimizer import rewrite_warp_parallel_tail
from .goldbach_wheel_filtered_tail_optimizer import (
    rewrite_wheel_filtered_sieve,
)


WARP_PARALLEL_CUTOFF = 32_749
COFACTOR_FILTER_LIMIT = 47
EXPECTED_GOLDBACH_SOURCE_SHA256 = (
    "2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c"
)
EXPECTED_GOLDBACH_SOURCE_BYTES = 71_853
EXPECTED_SOURCE_IDENTITY_SHA256 = (
    "8c19bf2825ff8a34ef9413f35620487f2062868f723b158228a071a5cf021359"
)
ALGORITHM_CANDIDATE_ID = (
    "sparkinterval.goldbach-10pow27-wheel47-warp32749-shifted-packed.v1"
)
SOURCE_SCHEMA = "sparkinterval.goldbach-optimized-source-candidate.v1"
_SOURCE_DOMAIN = b"sparkinterval/tg/goldbach-optimized-source/v1\x00"
_ROOT = Path(__file__).resolve().parents[1]
_TRANSFORM_PATHS = (
    "tg_verifier/goldbach_warp_tail_optimizer.py",
    "tg_verifier/goldbach_shifted_coverage_optimizer.py",
    "tg_verifier/goldbach_wheel_filtered_tail_optimizer.py",
)


class GoldbachOptimizedSourceError(RuntimeError):
    """The exact optimized source candidate could not be materialized."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _closure(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise GoldbachOptimizedSourceError(
                "optimized source closure contains a symbolic link"
            )
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise GoldbachOptimizedSourceError(
                "optimized source closure contains a non-regular file"
            )
        if metadata.st_nlink != 1:
            raise GoldbachOptimizedSourceError(
                "optimized source closure contains a multiply linked file"
            )
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": metadata.st_size,
            }
        )
    return rows


def _transform_rows() -> list[dict[str, object]]:
    return [
        {
            "path": path,
            "sha256": _sha256(_ROOT / path),
            "size_bytes": (_ROOT / path).stat().st_size,
        }
        for path in _TRANSFORM_PATHS
    ]


def _identity_core(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "algorithm_candidate_id": ALGORITHM_CANDIDATE_ID,
        "hardened_source_identity_sha256": (
            EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256
        ),
        "warp_parallel_cutoff": WARP_PARALLEL_CUTOFF,
        "cofactor_filter_limit": COFACTOR_FILTER_LIMIT,
        "transforms": _transform_rows(),
        "files": rows,
    }


def _expected_optimized_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path, digest, size in HARDENED_SOURCE_FILES:
        if path == "src/goldbach.cu":
            digest = EXPECTED_GOLDBACH_SOURCE_SHA256
            size = EXPECTED_GOLDBACH_SOURCE_BYTES
        rows.append({"path": path, "sha256": digest, "size_bytes": size})
    return rows


def verify_optimized_source_tree(source_root: Path) -> str:
    """Verify the complete generated source closure without regenerating it.

    This is the source-scale campaign admission check.  It binds every file in
    the transformed tree and the exact transformer bytes; it does not build an
    executable, authenticate a compiler, or claim that a campaign ran.
    """

    try:
        metadata = source_root.lstat()
    except OSError as error:
        raise GoldbachOptimizedSourceError(
            f"cannot inspect optimized source directory {source_root}: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise GoldbachOptimizedSourceError(
            "optimized source root must be a nonsymlink directory"
        )
    rows = _closure(source_root.resolve())
    if rows != _expected_optimized_rows():
        raise GoldbachOptimizedSourceError(
            "optimized source closure differs from the reviewed output"
        )
    source_identity = hashlib.sha256(
        _SOURCE_DOMAIN + canonical_json_bytes(_identity_core(rows))
    ).hexdigest()
    if source_identity != EXPECTED_SOURCE_IDENTITY_SHA256:
        raise GoldbachOptimizedSourceError(
            "optimized source identity or transformer closure differs"
        )
    return source_identity


def transform_goldbach_source(source: str) -> str:
    """Apply the exact qualified transform sequence and verify its identity."""

    transformed = rewrite_warp_parallel_tail(
        source, WARP_PARALLEL_CUTOFF
    )
    transformed = rewrite_shifted_phase1(transformed)
    transformed = rewrite_wheel_filtered_sieve(
        transformed, COFACTOR_FILTER_LIMIT
    )
    transformed = rewrite_packed_shifted_unverified_count(transformed)
    encoded = transformed.encode()
    if (
        len(encoded) != EXPECTED_GOLDBACH_SOURCE_BYTES
        or hashlib.sha256(encoded).hexdigest()
        != EXPECTED_GOLDBACH_SOURCE_SHA256
    ):
        raise GoldbachOptimizedSourceError(
            "generated optimized goldbach.cu identity differs"
        )
    return transformed


def prepare_optimized_source(
    hardened_source_root: Path, destination: Path
) -> dict[str, object]:
    """Create or exactly revalidate one immutable optimized source closure."""

    hardened_identity = verify_hardened_source_tree(hardened_source_root)
    hardened_source_root = hardened_source_root.resolve()
    if destination.is_symlink():
        raise GoldbachOptimizedSourceError(
            "optimized destination must not be a symbolic link"
        )
    if destination.exists() and not destination.is_dir():
        raise GoldbachOptimizedSourceError(
            "optimized destination exists and is not a directory"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
    )
    try:
        base_rows = _closure(hardened_source_root)
        for row in base_rows:
            relative = Path(str(row["path"]))
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hardened_source_root / relative, target)
        goldbach = temporary / "src/goldbach.cu"
        transformed = transform_goldbach_source(
            goldbach.read_text(encoding="utf-8")
        )
        goldbach.write_text(transformed, encoding="utf-8", newline="")
        rows = _closure(temporary)
        if {str(row["path"]) for row in rows} != {
            str(row["path"]) for row in base_rows
        }:
            raise GoldbachOptimizedSourceError(
                "optimized transform changed the source file set"
            )
        if destination.exists():
            if _closure(destination) != rows:
                raise GoldbachOptimizedSourceError(
                    "existing optimized source differs from deterministic output"
                )
            shutil.rmtree(temporary)
        else:
            temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    identity_core = _identity_core(rows)
    if (
        identity_core["hardened_source_identity_sha256"]
        != hardened_identity
    ):
        raise GoldbachOptimizedSourceError(
            "optimized source base identity differs"
        )
    source_identity = hashlib.sha256(
        _SOURCE_DOMAIN + canonical_json_bytes(identity_core)
    ).hexdigest()
    if source_identity != EXPECTED_SOURCE_IDENTITY_SHA256:
        raise GoldbachOptimizedSourceError(
            "optimized source closure/transform identity differs"
        )
    return {
        "accepted": True,
        "schema": SOURCE_SCHEMA,
        "classification": (
            "qualified-source-candidate-not-production-registration"
        ),
        **identity_core,
        "source_identity_sha256": source_identity,
        "destination": str(destination.resolve()),
        "production_identity_promoted": False,
        "target_h100_measured": False,
        "execution_attested": False,
        "lean_claim_discharged": False,
    }


__all__ = [
    "ALGORITHM_CANDIDATE_ID",
    "COFACTOR_FILTER_LIMIT",
    "EXPECTED_GOLDBACH_SOURCE_BYTES",
    "EXPECTED_GOLDBACH_SOURCE_SHA256",
    "EXPECTED_SOURCE_IDENTITY_SHA256",
    "GoldbachOptimizedSourceError",
    "SOURCE_SCHEMA",
    "WARP_PARALLEL_CUTOFF",
    "prepare_optimized_source",
    "transform_goldbach_source",
    "verify_optimized_source_tree",
]

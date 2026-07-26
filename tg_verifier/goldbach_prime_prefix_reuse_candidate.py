# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic source package for the unpromoted Goldbach v2 candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import stat
import tempfile

from .campaign_io import canonical_json_bytes
from .goldbach_prime_prefix_reuse_optimizer import (
    V1_OPTIMIZED_SOURCE_BYTES,
    V1_OPTIMIZED_SOURCE_SHA256,
    V2_ALGORITHM_CANDIDATE_ID,
    rewrite_prime_prefix_reuse,
    rewrite_prime_prefix_reuse_crosscheck,
)


SOURCE_SCHEMA = (
    "sparkinterval.goldbach-prime-prefix-reuse-source-candidate.v2"
)
CLASSIFICATION = (
    "bounded-source-candidate-not-production-registration-or-evidence"
)
EXPECTED_GOLDBACH_SOURCE_BYTES = 72_477
EXPECTED_GOLDBACH_SOURCE_SHA256 = (
    "51e989cc56004290922f99b12653a3cee3a6bcd3321fb35a3e890daf3912694a"
)
EXPECTED_CROSSCHECK_SOURCE_BYTES = 72_976
EXPECTED_CROSSCHECK_SOURCE_SHA256 = (
    "e2862aec57e3fc2c0c5cb32004690a7e98039133b3a480529f1e74c2d924505a"
)
# Filled from the complete v1 closure, output closure, algorithm ID, and exact
# transformer-module bytes.  This module is deliberately outside that
# self-reference.
EXPECTED_SOURCE_IDENTITY_SHA256 = (
    "3c779590babe1a9eb5e5fb21914129a6ed8edd49e4c0814c05c7f481a6dbffeb"
)
_SOURCE_DOMAIN = (
    b"sparkinterval/tg/goldbach-prime-prefix-reuse-source/v2\x00"
)
_V1_CLOSURE_DOMAIN = (
    b"sparkinterval/tg/goldbach-optimized-v1-source-closure/v1\x00"
)
EXPECTED_V1_SOURCE_CLOSURE_SHA256 = (
    "ebc51bef0b0941c99fe9d7ce994093de16bee07500d22a4e0f86dd2e44f885a0"
)
_ROOT = Path(__file__).resolve().parents[1]
_TRANSFORMER = (
    _ROOT / "tg_verifier/goldbach_prime_prefix_reuse_optimizer.py"
)


class GoldbachPrimePrefixCandidateError(RuntimeError):
    """The v2 source candidate could not be materialized exactly."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _closure(root: Path) -> list[dict[str, object]]:
    if root.is_symlink() or not root.is_dir():
        raise GoldbachPrimePrefixCandidateError(
            "candidate source root must be a real directory"
        )
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise GoldbachPrimePrefixCandidateError(
                "candidate source closure contains a symbolic link"
            )
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise GoldbachPrimePrefixCandidateError(
                "candidate source closure contains a linked/nonregular file"
            )
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": metadata.st_size,
            }
        )
    if not rows:
        raise GoldbachPrimePrefixCandidateError(
            "candidate source closure is empty"
        )
    return rows


def _validate_v1(root: Path) -> list[dict[str, object]]:
    rows = _closure(root)
    closure_sha256 = hashlib.sha256(
        _V1_CLOSURE_DOMAIN + canonical_json_bytes(rows)
    ).hexdigest()
    if closure_sha256 != EXPECTED_V1_SOURCE_CLOSURE_SHA256:
        raise GoldbachPrimePrefixCandidateError(
            "input is not the exact complete qualified v1 source closure"
        )
    source = root / "src/goldbach.cu"
    if not source.is_file() or source.is_symlink():
        raise GoldbachPrimePrefixCandidateError(
            "v1 source lacks a regular src/goldbach.cu"
        )
    pin = {
        "sha256": _sha256(source),
        "size_bytes": source.stat().st_size,
    }
    if pin != {
        "sha256": V1_OPTIMIZED_SOURCE_SHA256,
        "size_bytes": V1_OPTIMIZED_SOURCE_BYTES,
    }:
        raise GoldbachPrimePrefixCandidateError(
            "input is not the exact qualified v1 source"
        )
    return rows


def prepare_prime_prefix_reuse_source(
    v1_source_root: Path, destination: Path
) -> dict[str, object]:
    """Create or exactly revalidate one immutable v2 source closure."""

    v1_source_root = v1_source_root.resolve(strict=True)
    v1_rows = _validate_v1(v1_source_root)
    if destination.is_symlink():
        raise GoldbachPrimePrefixCandidateError(
            "destination must not be a symbolic link"
        )
    if destination.exists() and not destination.is_dir():
        raise GoldbachPrimePrefixCandidateError(
            "destination exists and is not a directory"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
    )
    try:
        for row in v1_rows:
            relative = Path(str(row["path"]))
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(v1_source_root / relative, target)
        source = temporary / "src/goldbach.cu"
        rewritten = rewrite_prime_prefix_reuse(
            source.read_text(encoding="utf-8")
        )
        source.write_text(rewritten, encoding="utf-8", newline="")
        rows = _closure(temporary)
        if {row["path"] for row in rows} != {
            row["path"] for row in v1_rows
        }:
            raise GoldbachPrimePrefixCandidateError(
                "prefix-reuse transform changed the source file set"
            )
        source_pin = {
            "sha256": _sha256(source),
            "size_bytes": source.stat().st_size,
        }
        if source_pin != {
            "sha256": EXPECTED_GOLDBACH_SOURCE_SHA256,
            "size_bytes": EXPECTED_GOLDBACH_SOURCE_BYTES,
        }:
            raise GoldbachPrimePrefixCandidateError(
                "generated v2 goldbach.cu identity differs"
            )
        if destination.exists():
            if _closure(destination) != rows:
                raise GoldbachPrimePrefixCandidateError(
                    "existing v2 destination differs"
                )
            shutil.rmtree(temporary)
        else:
            temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    transformer = {
        "path": _TRANSFORMER.relative_to(_ROOT).as_posix(),
        "sha256": _sha256(_TRANSFORMER),
        "size_bytes": _TRANSFORMER.stat().st_size,
    }
    identity_core = {
        "algorithm_candidate_id": V2_ALGORITHM_CANDIDATE_ID,
        "v1_goldbach_source_sha256": V1_OPTIMIZED_SOURCE_SHA256,
        "v1_files": v1_rows,
        "transformer": transformer,
        "files": rows,
    }
    source_identity = hashlib.sha256(
        _SOURCE_DOMAIN + canonical_json_bytes(identity_core)
    ).hexdigest()
    if source_identity != EXPECTED_SOURCE_IDENTITY_SHA256:
        raise GoldbachPrimePrefixCandidateError(
            "complete v2 source identity differs"
        )
    return {
        "accepted": True,
        "schema": SOURCE_SCHEMA,
        "classification": CLASSIFICATION,
        **identity_core,
        "source_identity_sha256": source_identity,
        "destination": str(destination.resolve()),
        "confidential_attestation_completed": False,
        "lean_atom_discharged": False,
        "production_identity_promoted": False,
        "source_scale_completion": False,
        "target_h100_measured": False,
    }


def prepare_prime_prefix_reuse_crosscheck_source(
    v1_source_root: Path, destination: Path
) -> dict[str, object]:
    """Materialize the bounded exact-vector diagnostic source closure."""

    v1_source_root = v1_source_root.resolve(strict=True)
    v1_rows = _validate_v1(v1_source_root)
    if destination.exists() or destination.is_symlink():
        raise GoldbachPrimePrefixCandidateError(
            "crosscheck destination must be absent"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
    )
    try:
        for row in v1_rows:
            relative = Path(str(row["path"]))
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(v1_source_root / relative, target)
        source = temporary / "src/goldbach.cu"
        source.write_text(
            rewrite_prime_prefix_reuse_crosscheck(
                source.read_text(encoding="utf-8")
            ),
            encoding="utf-8",
            newline="",
        )
        pin = {
            "sha256": _sha256(source),
            "size_bytes": source.stat().st_size,
        }
        if pin != {
            "sha256": EXPECTED_CROSSCHECK_SOURCE_SHA256,
            "size_bytes": EXPECTED_CROSSCHECK_SOURCE_BYTES,
        }:
            raise GoldbachPrimePrefixCandidateError(
                "generated exact-vector crosscheck identity differs"
            )
        rows = _closure(temporary)
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "accepted": True,
        "classification": "bounded-exact-vector-diagnostic-only",
        "files": rows,
        "goldbach_source": pin,
        "destination": str(destination.resolve()),
        "confidential_attestation_completed": False,
        "lean_atom_discharged": False,
        "production_identity_promoted": False,
        "source_scale_completion": False,
        "target_h100_measured": False,
    }


__all__ = [
    "CLASSIFICATION",
    "EXPECTED_CROSSCHECK_SOURCE_BYTES",
    "EXPECTED_CROSSCHECK_SOURCE_SHA256",
    "EXPECTED_GOLDBACH_SOURCE_BYTES",
    "EXPECTED_GOLDBACH_SOURCE_SHA256",
    "EXPECTED_SOURCE_IDENTITY_SHA256",
    "EXPECTED_V1_SOURCE_CLOSURE_SHA256",
    "GoldbachPrimePrefixCandidateError",
    "SOURCE_SCHEMA",
    "prepare_prime_prefix_reuse_crosscheck_source",
    "prepare_prime_prefix_reuse_source",
]

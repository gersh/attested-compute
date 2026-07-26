# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Streaming authenticated catalog for source-wide Dirichlet root artifacts.

Root numbers depend on the modulus and character, not on the ordinate.  The
t-major large-q route therefore authenticates each ``TGDRNRO1`` artifact once
and binds the exact monotone set of moduli with primitive characters.  This
catalog is NDJSON so the 292,500 source entries can be built and audited with
one root artifact and one receipt in memory.

Every catalog entry is produced only after the canonical receipt and binary
artifact pass the existing root-number parser.  The catalog is provenance and
identity evidence; it is not remote-execution attestation, zero completeness,
or Platt's Theorem 7.1.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Iterator, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_stage import canonical_component_orders
from tg_verifier.dirichlet_campaign import (
    _smallest_prime_factors,
    primitive_character_count,
)
from tg_verifier.dirichlet_lattice_stage import SOURCE_Q_START, SOURCE_Q_STOP
from tg_verifier.dirichlet_root_number_stage import (
    AUTHOR,
    ATOM_ID,
    CONVENTION_SHA256,
    ROOT_ALGORITHM_ID,
    ROOT_RECEIPT_SCHEMA,
    _validate_root_receipt,
    canonical_json_bytes,
    read_root_artifact_bytes,
    sha256_bytes,
)


ALGORITHM_ID = "platt-dirichlet-source-root-artifact-catalog-v1"
HEADER_SCHEMA = "sparkinterval.tg.dirichlet_root_catalog.header.v1"
ENTRY_SCHEMA = "sparkinterval.tg.dirichlet_root_catalog.entry.v1"
FOOTER_SCHEMA = "sparkinterval.tg.dirichlet_root_catalog.footer.v1"

MAXIMUM_HEADER_BYTES = 64 * 1024
MAXIMUM_ENTRY_BYTES = 64 * 1024
MAXIMUM_FOOTER_BYTES = 64 * 1024
MAXIMUM_RECEIPT_BYTES = 1024 * 1024
MAXIMUM_ROOT_ARTIFACT_BYTES = 32 * 1024 * 1024
MAXIMUM_CATALOG_BYTES = 512 * 1024 * 1024

ENTRY_CHAIN_DOMAIN = b"sparkinterval/tg/dirichlet-root-catalog/entries/v1\0"


class DirichletRootCatalogError(RuntimeError):
    """A root artifact, receipt, source coverage, or catalog hash failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletRootCatalogError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def root_artifact_filename(q: int) -> str:
    if type(q) is not int or not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("root artifact q is outside the large-q source range")
    return f"root-q-{q:06d}.bin"


def root_receipt_filename(q: int) -> str:
    if type(q) is not int or not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("root receipt q is outside the large-q source range")
    return f"root-q-{q:06d}.receipt.json"


@lru_cache(maxsize=1)
def _source_spf() -> tuple[int, ...]:
    return tuple(_smallest_prime_factors(SOURCE_Q_STOP))


def active_moduli(q_start: int, q_stop: int) -> Iterator[tuple[int, int]]:
    if (
        type(q_start) is not int
        or type(q_stop) is not int
        or not SOURCE_Q_START <= q_start <= q_stop <= SOURCE_Q_STOP
    ):
        _fail("root catalog modulus interval is outside the source range")
    spf = _source_spf()
    for q in range(q_start, q_stop + 1):
        count = primitive_character_count(q, spf)
        if count:
            yield q, count


def _safe_read(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletRootCatalogError(
            f"cannot open {label} without following links"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode) or not 0 < status.st_size <= maximum_bytes:
            _fail(f"{label} is not a bounded regular file")
        raw = source.read(maximum_bytes + 1)
    if len(raw) != status.st_size:
        _fail(f"{label} changed or exceeds its fixed bound")
    return raw, {
        "filename": path.name,
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }


def _safe_hash_record(
    path: Path, *, maximum_bytes: int, label: str
) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletRootCatalogError(
            f"cannot open {label} without following links"
        ) from error
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if not stat.S_ISREG(status.st_mode) or not 0 < status.st_size <= maximum_bytes:
            _fail(f"{label} is not a bounded regular file")
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    if size != status.st_size:
        _fail(f"{label} changed while hashing")
    return {
        "filename": path.name,
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletRootCatalogError(f"invalid {label} JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable root output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def split_root_stream(
    root_stream_path: Path,
    receipt_stream_path: Path,
    output_root: Path,
    *,
    q_start: int = SOURCE_Q_START,
    q_stop: int = SOURCE_Q_STOP,
    expected_root_stream_sha256: str | None = None,
    expected_receipt_stream_sha256: str | None = None,
) -> dict[str, Any]:
    """Split the persistent root stage into canonical per-q catalog inputs."""

    if output_root.exists():
        _fail("root output directory must be absent")
    expected_root_stream_sha256 = (
        None
        if expected_root_stream_sha256 is None
        else _digest(expected_root_stream_sha256, "root stream")
    )
    expected_receipt_stream_sha256 = (
        None
        if expected_receipt_stream_sha256 is None
        else _digest(expected_receipt_stream_sha256, "receipt stream")
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent)
    )
    root_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    receipt_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_descriptor = os.open(root_stream_path, root_flags)
        receipt_descriptor = os.open(receipt_stream_path, receipt_flags)
    except OSError as error:
        try:
            os.close(root_descriptor)
        except (NameError, OSError):
            pass
        raise DirichletRootCatalogError(
            "cannot open persistent root streams without following links"
        ) from error
    root_digest = hashlib.sha256()
    receipt_digest = hashlib.sha256()
    entry_count = 0
    root_bytes = 0
    receipt_bytes = 0
    try:
        with (
            os.fdopen(root_descriptor, "rb") as roots,
            os.fdopen(receipt_descriptor, "rb") as receipts,
        ):
            if (
                not stat.S_ISREG(os.fstat(roots.fileno()).st_mode)
                or not stat.S_ISREG(os.fstat(receipts.fileno()).st_mode)
            ):
                _fail("persistent root input is not a regular file")
            for q, primitive_count in active_moduli(q_start, q_stop):
                receipt_raw = _readline(
                    receipts,
                    MAXIMUM_RECEIPT_BYTES,
                    label=f"q={q} persistent root receipt",
                )
                receipt_digest.update(receipt_raw)
                receipt_bytes += len(receipt_raw)
                receipt = _canonical_object(
                    receipt_raw, label=f"q={q} persistent root receipt"
                )
                try:
                    checked = _validate_root_receipt(receipt)
                except Exception as error:
                    raise DirichletRootCatalogError(
                        f"q={q} persistent root receipt validation failed: {error}"
                    ) from error
                artifact_size = checked.get("root_artifact_bytes")
                if (
                    checked.get("q") != q
                    or checked.get("primitive_character_count") != primitive_count
                    or type(artifact_size) is not int
                    or not 0 < artifact_size <= MAXIMUM_ROOT_ARTIFACT_BYTES
                ):
                    _fail("persistent root receipt sequence or size differs")
                artifact_raw = roots.read(artifact_size)
                if len(artifact_raw) != artifact_size:
                    _fail(f"q={q} persistent root artifact is truncated")
                root_digest.update(artifact_raw)
                root_bytes += len(artifact_raw)
                try:
                    metadata, values = read_root_artifact_bytes(
                        artifact_raw, checked
                    )
                except Exception as error:
                    raise DirichletRootCatalogError(
                        f"q={q} persistent root artifact validation failed: {error}"
                    ) from error
                if (
                    metadata.get("q") != q
                    or metadata.get("primitive_character_count")
                    != primitive_count
                    or len(values) != primitive_count
                ):
                    _fail("persistent root artifact primitive inventory differs")
                artifact_path = temporary_root / root_artifact_filename(q)
                receipt_path = temporary_root / root_receipt_filename(q)
                try:
                    _atomic_bytes(artifact_path, artifact_raw)
                    _atomic_bytes(receipt_path, receipt_raw)
                except BaseException:
                    artifact_path.unlink(missing_ok=True)
                    receipt_path.unlink(missing_ok=True)
                    raise
                entry_count += 1
            if roots.read(1) or receipts.read(1):
                _fail("persistent root or receipt stream has trailing bytes")
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    actual_root_sha = root_digest.hexdigest()
    actual_receipt_sha = receipt_digest.hexdigest()
    if (
        expected_root_stream_sha256 is not None
        and expected_root_stream_sha256 != actual_root_sha
    ):
        shutil.rmtree(temporary_root, ignore_errors=True)
        _fail("persistent root stream SHA-256 differs")
    if (
        expected_receipt_stream_sha256 is not None
        and expected_receipt_stream_sha256 != actual_receipt_sha
    ):
        shutil.rmtree(temporary_root, ignore_errors=True)
        _fail("persistent root receipt stream SHA-256 differs")
    try:
        os.replace(temporary_root, output_root)
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "materialized_parsed_receipt_bound_root_stream_not_grh_evidence"
        ),
        "output_root": str(output_root.resolve()),
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "entry_count": entry_count,
        "root_stream_sha256": actual_root_sha,
        "root_stream_bytes": root_bytes,
        "receipt_stream_sha256": actual_receipt_sha,
        "receipt_stream_bytes": receipt_bytes,
        "all_artifacts_parsed_before_publish": True,
        "execution_attested": False,
        "external_atom_discharged": False,
    }


def _entry_from_files(root: Path, q: int, primitive_count: int) -> dict[str, Any]:
    artifact_path = root / root_artifact_filename(q)
    receipt_path = root / root_receipt_filename(q)
    receipt_raw, receipt_file = _safe_read(
        receipt_path,
        maximum_bytes=MAXIMUM_RECEIPT_BYTES,
        label=f"q={q} root receipt",
    )
    receipt = _canonical_object(receipt_raw, label=f"q={q} root receipt")
    try:
        checked_receipt = _validate_root_receipt(receipt)
    except Exception as error:
        raise DirichletRootCatalogError(
            f"q={q} root receipt validation failed: {error}"
        ) from error
    artifact_raw, artifact_file = _safe_read(
        artifact_path,
        maximum_bytes=MAXIMUM_ROOT_ARTIFACT_BYTES,
        label=f"q={q} root artifact",
    )
    try:
        metadata, roots = read_root_artifact_bytes(
            artifact_raw, checked_receipt
        )
    except Exception as error:
        raise DirichletRootCatalogError(
            f"q={q} root artifact validation failed: {error}"
        ) from error
    if (
        metadata.get("q") != q
        or metadata.get("primitive_character_count") != primitive_count
        or len(roots) != primitive_count
        or checked_receipt.get("q") != q
        or checked_receipt.get("primitive_character_count") != primitive_count
        or checked_receipt.get("convention_sha256") != CONVENTION_SHA256
        or checked_receipt.get("root_artifact_sha256")
        != artifact_file["sha256"]
        or checked_receipt.get("root_artifact_bytes")
        != artifact_file["size_bytes"]
    ):
        _fail(f"q={q} root artifact identity or primitive inventory differs")
    entry: dict[str, Any] = {
        "kind": ENTRY_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "q": q,
        "primitive_character_count": primitive_count,
        "component_orders": list(canonical_component_orders(q)),
        "convention_sha256": CONVENTION_SHA256,
        "artifact": artifact_file,
        "receipt": {
            **receipt_file,
            "receipt_sha256": checked_receipt["receipt_sha256"],
        },
        "additive_input_sha256": metadata["additive_input_sha256"],
        "transform_output_sha256": metadata["transform_output_sha256"],
        "external_atom_discharged": False,
    }
    entry["entry_sha256"] = sha256_bytes(canonical_json_bytes(entry))
    return entry


def _header(q_start: int, q_stop: int, entry_count: int) -> dict[str, Any]:
    full_source = (q_start, q_stop) == (SOURCE_Q_START, SOURCE_Q_STOP)
    return {
        "kind": HEADER_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "root_algorithm_id": ROOT_ALGORITHM_ID,
        "root_receipt_schema": ROOT_RECEIPT_SCHEMA,
        "convention_sha256": CONVENTION_SHA256,
        "classification": (
            "complete_large_q_root_catalog_not_execution_or_grh_evidence"
            if full_source
            else "bounded_root_catalog_kat_not_source_evidence"
        ),
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "expected_entry_count": entry_count,
        "exact_primitive_character_modulus_coverage": True,
        "external_atom_discharged": False,
    }


def _footer(
    *,
    q_start: int,
    q_stop: int,
    entry_count: int,
    entries_sha256: str,
    entry_chain_sha256: str,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "kind": FOOTER_SCHEMA,
        "schema_version": 1,
        "algorithm_id": ALGORITHM_ID,
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "entry_count": entry_count,
        "entries_sha256": entries_sha256,
        "entry_chain_sha256": entry_chain_sha256,
        "decisions": {
            "all_receipts_canonical_and_self_hashed": True,
            "all_root_artifacts_parsed_and_receipt_bound": True,
            "exact_monotone_primitive_modulus_coverage": True,
            "root_catalog_execution_attested": False,
            "zero_completeness_claimed": False,
            "external_atom_discharged": False,
        },
    }
    value["footer_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def build_root_catalog(
    catalog_path: Path,
    root: Path,
    *,
    q_start: int = SOURCE_Q_START,
    q_stop: int = SOURCE_Q_STOP,
) -> dict[str, Any]:
    """Validate every root artifact and atomically write the ordered catalog."""

    if catalog_path.exists():
        _fail(f"refusing to replace immutable root catalog: {catalog_path}")
    if root.is_symlink() or not root.is_dir():
        _fail("root artifact directory is missing, symbolic, or not a directory")
    entry_count = sum(1 for _item in active_moduli(q_start, q_stop))
    header = _header(q_start, q_stop, entry_count)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{catalog_path.name}.", dir=catalog_path.parent
    )
    temporary = Path(temporary_name)
    entries_digest = hashlib.sha256()
    entry_chain = hashlib.sha256(ENTRY_CHAIN_DOMAIN)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(header))
            for q, primitive_count in active_moduli(q_start, q_stop):
                entry = _entry_from_files(root, q, primitive_count)
                raw = canonical_json_bytes(entry)
                output.write(raw)
                entries_digest.update(raw)
                entry_chain.update(bytes.fromhex(entry["entry_sha256"]))
            footer = _footer(
                q_start=q_start,
                q_stop=q_stop,
                entry_count=entry_count,
                entries_sha256=entries_digest.hexdigest(),
                entry_chain_sha256=entry_chain.hexdigest(),
            )
            output.write(canonical_json_bytes(footer))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, catalog_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    record = _safe_hash_record(
        catalog_path,
        maximum_bytes=MAXIMUM_CATALOG_BYTES,
        label="root catalog",
    )
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": header["classification"],
        "catalog": record,
        "catalog_sha256": record["sha256"],
        "root_directory": str(root.resolve()),
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "entry_count": entry_count,
        "entries_sha256": entries_digest.hexdigest(),
        "entry_chain_sha256": entry_chain.hexdigest(),
        "bytes_written": record["size_bytes"],
        "root_artifacts_validated": True,
        "execution_attested": False,
        "external_atom_discharged": False,
    }


def _readline(source: Any, maximum: int, *, label: str) -> bytes:
    raw = source.readline(maximum + 1)
    if not raw or len(raw) > maximum or not raw.endswith(b"\n"):
        _fail(f"{label} is missing or exceeds its fixed line bound")
    return raw


def _validated_entry_shape(
    entry: dict[str, Any],
    *,
    q: int,
    primitive_count: int,
) -> None:
    body = dict(entry)
    claimed = _digest(body.pop("entry_sha256", None), "root catalog entry")
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail(f"q={q} root catalog entry self-hash differs")
    required = {
        "kind",
        "schema_version",
        "algorithm_id",
        "q",
        "primitive_character_count",
        "component_orders",
        "convention_sha256",
        "artifact",
        "receipt",
        "additive_input_sha256",
        "transform_output_sha256",
        "external_atom_discharged",
        "entry_sha256",
    }
    artifact = entry.get("artifact")
    receipt = entry.get("receipt")
    if (
        set(entry) != required
        or entry.get("kind") != ENTRY_SCHEMA
        or entry.get("schema_version") != 1
        or entry.get("algorithm_id") != ALGORITHM_ID
        or entry.get("q") != q
        or entry.get("primitive_character_count") != primitive_count
        or entry.get("component_orders") != list(canonical_component_orders(q))
        or entry.get("convention_sha256") != CONVENTION_SHA256
        or entry.get("external_atom_discharged") is not False
        or not isinstance(artifact, dict)
        or not isinstance(receipt, dict)
        or set(artifact) != {"filename", "sha256", "size_bytes"}
        or set(receipt)
        != {"filename", "sha256", "size_bytes", "receipt_sha256"}
        or artifact.get("filename") != root_artifact_filename(q)
        or receipt.get("filename") != root_receipt_filename(q)
        or type(artifact.get("size_bytes")) is not int
        or not 0 < artifact["size_bytes"] <= MAXIMUM_ROOT_ARTIFACT_BYTES
        or type(receipt.get("size_bytes")) is not int
        or not 0 < receipt["size_bytes"] <= MAXIMUM_RECEIPT_BYTES
    ):
        _fail(f"q={q} root catalog entry identity differs")
    for label, value in (
        ("artifact", artifact.get("sha256")),
        ("receipt file", receipt.get("sha256")),
        ("receipt", receipt.get("receipt_sha256")),
        ("additive input", entry.get("additive_input_sha256")),
        ("transform output", entry.get("transform_output_sha256")),
    ):
        _digest(value, f"q={q} {label} digest")


def audit_root_catalog(
    catalog_path: Path,
    *,
    root: Path | None = None,
    expected_sha256: str | None = None,
    require_full_source: bool = False,
    revalidate_artifacts: bool = False,
) -> dict[str, Any]:
    """Audit exact catalog coverage and optionally rerun every root parser."""

    if revalidate_artifacts and root is None:
        _fail("artifact revalidation requires the bound root directory")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(catalog_path, flags)
    except OSError as error:
        raise DirichletRootCatalogError(
            "cannot open root catalog without following links"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(status.st_mode)
            or not 0 < status.st_size <= MAXIMUM_CATALOG_BYTES
        ):
            _fail("root catalog is not a bounded regular file")
        if expected_sha256 is not None:
            expected_sha256 = _digest(expected_sha256, "root catalog file")
            prehash = hashlib.sha256()
            while block := source.read(1024 * 1024):
                prehash.update(block)
            if prehash.hexdigest() != expected_sha256:
                _fail("root catalog file SHA-256 differs before parsing")
            source.seek(0)
        file_digest = hashlib.sha256()
        header_raw = _readline(
            source, MAXIMUM_HEADER_BYTES, label="root catalog header"
        )
        file_digest.update(header_raw)
        header = _canonical_object(header_raw, label="root catalog header")
        if (
            header.get("kind") != HEADER_SCHEMA
            or header.get("schema_version") != 1
            or header.get("algorithm_id") != ALGORITHM_ID
            or header.get("author") != AUTHOR
            or header.get("atom_id") != ATOM_ID
            or header.get("root_algorithm_id") != ROOT_ALGORITHM_ID
            or header.get("root_receipt_schema") != ROOT_RECEIPT_SCHEMA
            or header.get("convention_sha256") != CONVENTION_SHA256
        ):
            _fail("root catalog header identity differs")
        q_start = header.get("q_start_inclusive")
        q_stop = header.get("q_stop_inclusive")
        entry_count = sum(1 for _item in active_moduli(q_start, q_stop))
        if header != _header(q_start, q_stop, entry_count):
            _fail("root catalog header geometry or classification differs")
        if require_full_source and (q_start, q_stop) != (
            SOURCE_Q_START,
            SOURCE_Q_STOP,
        ):
            _fail("root catalog does not cover the complete large-q source range")
        entries_digest = hashlib.sha256()
        entry_chain = hashlib.sha256(ENTRY_CHAIN_DOMAIN)
        for index, (q, primitive_count) in enumerate(
            active_moduli(q_start, q_stop)
        ):
            raw = _readline(
                source,
                MAXIMUM_ENTRY_BYTES,
                label=f"root catalog entry {index}",
            )
            file_digest.update(raw)
            entries_digest.update(raw)
            entry = _canonical_object(raw, label=f"root catalog entry {index}")
            _validated_entry_shape(entry, q=q, primitive_count=primitive_count)
            entry_chain.update(bytes.fromhex(entry["entry_sha256"]))
            if revalidate_artifacts:
                assert root is not None
                rebound = _entry_from_files(root, q, primitive_count)
                if rebound != entry:
                    _fail(f"q={q} root artifact files changed from the catalog")
        footer_raw = _readline(
            source, MAXIMUM_FOOTER_BYTES, label="root catalog footer"
        )
        file_digest.update(footer_raw)
        footer = _canonical_object(footer_raw, label="root catalog footer")
        body = dict(footer)
        claimed_footer = _digest(
            body.pop("footer_sha256", None), "root catalog footer"
        )
        if claimed_footer != sha256_bytes(canonical_json_bytes(body)):
            _fail("root catalog footer self-hash differs")
        expected_footer = _footer(
            q_start=q_start,
            q_stop=q_stop,
            entry_count=entry_count,
            entries_sha256=entries_digest.hexdigest(),
            entry_chain_sha256=entry_chain.hexdigest(),
        )
        if footer != expected_footer:
            _fail("root catalog footer or entry digest differs")
        trailing = source.read(1)
        file_digest.update(trailing)
        if trailing:
            _fail("root catalog has trailing bytes")
        actual_sha = file_digest.hexdigest()
        if expected_sha256 is not None and actual_sha != expected_sha256:
            _fail("root catalog changed between authentication passes")
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": header["classification"],
        "catalog": {
            "filename": catalog_path.name,
            "sha256": actual_sha,
            "size_bytes": status.st_size,
        },
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "entry_count": entry_count,
        "entries_sha256": entries_digest.hexdigest(),
        "entry_chain_sha256": entry_chain.hexdigest(),
        "complete_large_q_source_range": (
            (q_start, q_stop) == (SOURCE_Q_START, SOURCE_Q_STOP)
        ),
        "artifacts_parsed_and_receipt_bound": revalidate_artifacts,
        "execution_attested": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "streaming_root_catalog_component_not_atom_closure",
        "canonical_source_entry_count": 292_500,
        "exact_monotone_primitive_modulus_coverage": True,
        "canonical_receipt_self_hash_validation": True,
        "TGDRNRO1_parser_reused": True,
        "same_bytes_authenticated_and_parsed": True,
        "bounded_one_root_artifact_working_set": True,
        "source_catalog_generated": False,
        "source_catalog_audited": False,
        "execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "DirichletRootCatalogError",
    "ENTRY_SCHEMA",
    "FOOTER_SCHEMA",
    "HEADER_SCHEMA",
    "active_moduli",
    "audit_root_catalog",
    "build_root_catalog",
    "capability",
    "root_artifact_filename",
    "root_receipt_filename",
    "split_root_stream",
]

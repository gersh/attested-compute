# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Authenticated shared-row input for the seeded large-q CUDA frontend.

``TGDLTMB1`` is one lane-aligned block of at most 64 Hurwitz-lattice rows.
Each row occurs exactly once.  It is followed by one small factor/tail
sidecar for every active modulus; canonical CRT descriptors are reconstructed
by the CUDA executable and are not transported.  The resulting CUDA stdout is
the existing concatenated ``TGDAFFI1`` stream.

This module is a typed transport/conversion boundary.  It does not prove the
analytic meaning of a source ``TGDLQB2`` input, completed-L signs, zero
completeness, a Turing count, trusted execution, or Platt's Theorem 7.1.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
import time
from typing import Any, BinaryIO, Iterable, Iterator, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    PRIMITIVE_MODULUS_ROSTER_ID,
    PRIMITIVE_MODULUS_ROSTER_VERSION,
    canonical_component_orders,
    canonical_residue_order,
    has_primitive_character_modulus,
)
from tg_verifier.dirichlet_lattice_cache import (
    ROW_PAYLOAD_BYTES,
    canonical_json_bytes,
    validate_lattice_row,
)
from tg_verifier.dirichlet_lattice_stage import (
    LATTICE_CELL,
    LATTICE_ROWS,
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_MAX_T_INDEX,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
    maximum_t_index,
)
from tg_verifier.dirichlet_lattice_certificates import (
    derive_uniform_tail_bound,
)
from tg_verifier.dirichlet_largeq_batch import (
    FRAME_FACTOR,
    MAXIMUM_BATCH_COUNT,
    RESIDUE_DESCRIPTOR,
)
from tg_verifier.dirichlet_residue_composition import MPFRFactorProvider
from tg_verifier.dirichlet_recovery_seeds import (
    SEEDED_BATCH_HEADER,
    SEEDED_BATCH_MAGIC,
    SOURCE_M,
)
from tg_verifier.dirichlet_source_supervisor import SOURCE_CONTRACT_CLASSIFICATION
from tg_verifier.dirichlet_tmajor_spool import (
    BLOCK_ROW_BINDING_DOMAIN,
    AuthenticatedQContiguousSpool,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-tmajor-row-resident-seeded-input-v2"
ARTIFACT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda_block.artifact.v2"
)
RECEIPT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda_block.receipt.v2"
)
SIDECAR_MANIFEST_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda_block.sidecar.v1"
)
DIRECT_SIDECAR_RECIPE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda_block.direct_sidecars.v2"
)
CUDA_ALGORITHM_ID = (
    "platt-dirichlet-tmajor-row-resident-seeded-cuda-v2"
)
EXECUTION_SUMMARY_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda.execution_summary.v2"
)
EXECUTION_REPLAY_SCHEMA = (
    "sparkinterval.tg.dirichlet_tmajor_cuda.execution_replay.v2"
)

FORMAT_VERSION = 2
SIDECAR_MODE_QMAJOR_MANIFEST = 0
SIDECAR_MODE_DIRECT_MPFR = 1
DIRECT_FACTOR_PRECISION_BITS = 192
DIRECT_FACTOR_REPLAY_PRECISION_BITS = 256
BLOCK_MAGIC = b"TGDLTMB1"
ROW_MAGIC = b"TGDLTMR1"
TARGET_MAGIC = b"TGDLTMQ1"
FOOTER_MAGIC = b"TGDLTMF1"

# Keep these layouts byte-identical to
# gpu/include/sparkinterval/tg_dirichlet_tmajor_seeded.hpp.
BLOCK_HEADER = struct.Struct(
    "<8sIIIIIIIIQQQQQ32s32s32s32s32s32s"
)
ROW_HEADER = struct.Struct("<8sIIQQ32s")
TARGET_HEADER = struct.Struct("<8sIIIIIIQqQQQQQ32s")
BLOCK_FOOTER = struct.Struct("<8sIIQQQQQQ32s32s32s")

assert BLOCK_HEADER.size == 272
assert ROW_HEADER.size == 64
assert TARGET_HEADER.size == 120
assert BLOCK_FOOTER.size == 160

TARGET_SIDECAR_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-seeded/target-sidecar/v1\0"
)
SOURCE_INPUT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-seeded/source-input-chain/v1\0"
)
DIRECT_SOURCE_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tmajor-seeded/direct-source-chain/v1\0"
)

# For the clipped row r=1, the furthest source residue is a/q=1/q at the
# largest q.  Every non-clipped nearest-row displacement is at most 1/(2D),
# which is smaller because SOURCE_Q_STOP > 2D.  Thus this one exact rational
# bound is valid for every unit residue in the large-q source range and avoids
# transporting the same per-ordinate Taylor radius once per modulus.
GLOBAL_MAXIMUM_ABS_DELTA_NUMERATOR = (
    SOURCE_Q_STOP - LATTICE_ROWS
)
GLOBAL_MAXIMUM_ABS_DELTA_DENOMINATOR = (
    LATTICE_ROWS * SOURCE_Q_STOP
)

MAXIMUM_MANIFEST_LINE_BYTES = 16 * 1024
MAXIMUM_RECEIPT_BYTES = 4 * 1024 * 1024
MAXIMUM_BLOCK_BYTES = 4 * 1024 * 1024 * 1024
HEX = frozenset("0123456789abcdef")
PINNED_PRIMITIVE_SOURCE_ACTIVE_MODULI = 292_500
PINNED_PRIMITIVE_SOURCE_Q_T_ROWS = 3_637_613_167
PINNED_PRIMITIVE_SOURCE_BATCH64_TARGETS = 56_981_100


class DirichletTMajorCudaBlockError(RuntimeError):
    """A shared-row artifact, source sidecar, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTMajorCudaBlockError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in HEX for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def _integer(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = (1 << 64) - 1,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        _fail(f"{label} is outside [{minimum},{maximum}]")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("JSON object contains a duplicate key")
        value[key] = item
    return value


def _parse_json(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: _fail(
                f"{label} contains nonfinite {token}"
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletTMajorCudaBlockError(
            f"invalid {label} JSON"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not one canonical JSON record")
    return value


def _self_hash(
    value: Mapping[str, Any], field: str, *, label: str
) -> str:
    body = dict(value)
    claimed = _digest(body.pop(field, None), f"{label}.{field}")
    if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != claimed:
        _fail(f"{label} self-hash differs")
    return claimed


def _normalized_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        _fail(f"{label} is malformed")
    path = Path(value)
    if not path.is_absolute() or str(path.resolve()) != value:
        _fail(f"{label} is not absolute and normalized")
    return path


def _open_regular(path: Path, *, label: str) -> BinaryIO:
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
    except OSError as error:
        raise DirichletTMajorCudaBlockError(
            f"cannot open {label} without following a final symlink: {error}"
        ) from error
    source = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
        source.close()
        _fail(f"{label} is not a regular file")
    return source


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_exact(
    source: BinaryIO,
    count: int,
    *,
    label: str,
    digest: hashlib._Hash | None = None,
) -> bytes:
    raw = source.read(count)
    if len(raw) != count:
        _fail(f"truncated {label}")
    if digest is not None:
        digest.update(raw)
    return raw


def _hash_file(path: Path, *, label: str) -> dict[str, Any]:
    with _open_regular(path, label=label) as source:
        status = os.fstat(source.fileno())
        digest = hashlib.sha256()
        size = 0
        while raw := source.read(8 * 1024 * 1024):
            digest.update(raw)
            size += len(raw)
        if _stat_identity(os.fstat(source.fileno())) != _stat_identity(
            status
        ):
            _fail(f"{label} changed while it was hashed")
    return {
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _module_artifact(path: Path) -> dict[str, Any]:
    report = _hash_file(path.resolve(), label=f"implementation {path.name}")
    return {
        "name": path.name,
        "sha256": report["sha256"],
        "size_bytes": report["size_bytes"],
    }


def _direct_recipe(
    *,
    q_start: int,
    q_stop: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    mpfr_version: str,
) -> dict[str, Any]:
    import tg_verifier.dirichlet_lattice_certificates as lattice_certificates
    import tg_verifier.dirichlet_residue_composition as residue_composition

    body: dict[str, Any] = {
        "schema": DIRECT_SIDECAR_RECIPE_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "direct_directed_mpfr_factor_and_exact_rational_tail_recipe"
        ),
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": t_index_stop_exclusive,
        "M": SOURCE_M,
        "t_step_numerator": SOURCE_SAMPLE_NUMERATOR,
        "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
        "factor_generation": {
            "library": "MPFR",
            "version": mpfr_version,
            "precision_bits": DIRECT_FACTOR_PRECISION_BITS,
            "directed_binary64_enclosures": True,
        },
        "factor_replay": {
            "library": "MPFR",
            "version": mpfr_version,
            "precision_bits": DIRECT_FACTOR_REPLAY_PRECISION_BITS,
            "requires_containment_in_generated_enclosure": True,
        },
        "uniform_taylor_tail": {
            "maximum_abs_delta": {
                "numerator": str(GLOBAL_MAXIMUM_ABS_DELTA_NUMERATOR),
                "denominator": str(GLOBAL_MAXIMUM_ABS_DELTA_DENOMINATOR),
            },
            "exact_rational_derivation_replayed_per_ordinate": True,
        },
        "implementation_artifacts": [
            _module_artifact(Path(__file__)),
            _module_artifact(Path(lattice_certificates.__file__)),
            _module_artifact(Path(residue_composition.__file__)),
        ],
        "runtime_closure_captured": False,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    recipe = dict(body)
    recipe["recipe_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return recipe


def _validate_direct_recipe(
    value: object,
    *,
    q_start: int,
    q_stop: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
) -> tuple[dict[str, Any], MPFRFactorProvider, MPFRFactorProvider]:
    if not isinstance(value, dict):
        _fail("direct sidecar recipe is not an object")
    recipe = dict(value)
    claimed = _digest(
        recipe.pop("recipe_sha256", None), "direct sidecar recipe"
    )
    if hashlib.sha256(canonical_json_bytes(recipe)).hexdigest() != claimed:
        _fail("direct sidecar recipe self-hash differs")
    generator = MPFRFactorProvider(DIRECT_FACTOR_PRECISION_BITS)
    replayer = MPFRFactorProvider(DIRECT_FACTOR_REPLAY_PRECISION_BITS)
    expected = _direct_recipe(
        q_start=q_start,
        q_stop=q_stop,
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
        mpfr_version=generator.version,
    )
    if (
        replayer.version != generator.version
        or canonical_json_bytes(value) != canonical_json_bytes(expected)
    ):
        _fail("direct sidecar recipe, implementation, or MPFR version differs")
    return expected, generator, replayer


def _global_tail_words(
    *, first_t_index: int, t_index_stop_exclusive: int
) -> tuple[bytes, ...]:
    maximum_delta = Fraction(
        GLOBAL_MAXIMUM_ABS_DELTA_NUMERATOR,
        GLOBAL_MAXIMUM_ABS_DELTA_DENOMINATOR,
    )
    clipped_edge_witness = abs(
        Fraction(1, SOURCE_Q_STOP)
        - Fraction(
            canonical_lattice_row(SOURCE_Q_STOP, 1),
            LATTICE_ROWS,
        )
    )
    if not (
        Fraction(1, 2 * LATTICE_ROWS)
        <= maximum_delta
        < Fraction(1, LATTICE_ROWS)
        and clipped_edge_witness == maximum_delta
    ):
        _fail("global clipped-nearest-row displacement invariant failed")
    words: list[bytes] = []
    for t_index in range(first_t_index, t_index_stop_exclusive):
        derived = derive_uniform_tail_bound(
            t_index=t_index,
            m=SOURCE_M,
            maximum_abs_delta=maximum_delta,
        )
        radius = float.fromhex(derived["binary64_radius_hex"])
        if not math.isfinite(radius) or radius < 0:
            _fail("direct exact-rational Taylor tail is malformed")
        words.append(struct.pack("<d", radius))
    return tuple(words)


def _factor_contains(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] >= inner[1]
        and outer[2] <= inner[2]
        and outer[3] >= inner[3]
    )


def _direct_sidecar(
    *,
    generator: MPFRFactorProvider,
    replayer: MPFRFactorProvider,
    q: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    tail_words: tuple[bytes, ...],
) -> tuple[bytes, bytes]:
    factors = bytearray()
    for t_index in range(first_t_index, t_index_stop_exclusive):
        arguments = {
            "q": q,
            "t_numerator": t_index * SOURCE_SAMPLE_NUMERATOR,
            "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
        }
        generated = generator.factor(**arguments)
        replayed = replayer.factor(**arguments)
        if not _factor_contains(generated, replayed):
            _fail("higher-precision MPFR factor escaped generated enclosure")
        factors.extend(FRAME_FACTOR.pack(*generated))
    if len(tail_words) != t_index_stop_exclusive - first_t_index:
        _fail("direct Taylor-tail roster differs")
    return bytes(factors), b"".join(tail_words)


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable output: {path}")
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
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _expected_qs(
    *, q_start: int, q_stop: int, first_t_index: int
) -> Iterator[int]:
    for q in range(q_start, q_stop + 1):
        if (
            has_primitive_character_modulus(q)
            and first_t_index <= maximum_t_index(q)
        ):
            yield q


def _totient(q: int) -> int:
    result = q
    remaining = q
    prime = 2
    while prime * prime <= remaining:
        if remaining % prime == 0:
            result -= result // prime
            while remaining % prime == 0:
                remaining //= prime
        prime += 1 if prime == 2 else 2
    if remaining > 1:
        result -= result // remaining
    return result


def _target_sidecar_sha256(
    *,
    q: int,
    batch_count: int,
    first_t_numerator: int,
    group_order: int,
    factors: bytes,
    tails: bytes,
) -> str:
    digest = hashlib.sha256(TARGET_SIDECAR_DOMAIN)
    digest.update(
        struct.pack(
            "<IIqQ", q, batch_count, first_t_numerator, group_order
        )
    )
    digest.update(factors)
    digest.update(tails)
    return digest.hexdigest()


def _validate_factor_bytes(raw: bytes) -> None:
    for box in FRAME_FACTOR.iter_unpack(raw):
        if (
            not all(math.isfinite(value) for value in box)
            or box[0] > box[1]
            or box[2] > box[3]
        ):
            _fail("seeded input contains a malformed q^(-s) factor")


def _validate_tail_bytes(raw: bytes) -> None:
    for (radius,) in struct.iter_unpack("<d", raw):
        if not math.isfinite(radius) or radius < 0:
            _fail("seeded input contains a malformed Taylor-tail radius")


def _manifest_record(
    value: object, *, expected_q: int
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "schema_version",
        "q",
        "path",
        "sha256",
        "size_bytes",
    }:
        _fail("sidecar manifest record fields differ")
    if (
        value.get("schema") != SIDECAR_MANIFEST_SCHEMA
        or value.get("schema_version") != 1
        or value.get("q") != expected_q
    ):
        _fail("sidecar manifest record is skipped, reordered, or substituted")
    path = _normalized_path(value.get("path"), "sidecar source path")
    return {
        "schema": SIDECAR_MANIFEST_SCHEMA,
        "schema_version": 1,
        "q": expected_q,
        "path": str(path),
        "sha256": _digest(
            value.get("sha256"), "sidecar source artifact"
        ),
        "size_bytes": _integer(
            value.get("size_bytes"),
            "sidecar source artifact bytes",
            minimum=1,
            maximum=MAXIMUM_BLOCK_BYTES,
        ),
    }


def write_sidecar_manifest(
    path: Path, entries: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Write canonical source-frame pins without retaining an in-memory list."""

    if path.exists() or path.is_symlink():
        _fail(f"refusing to replace immutable manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0
    count = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            for expected_q, raw_entry in enumerate(entries):
                # enumerate() here is only a duplicate-free stream counter.
                # The builder later enforces the formulaic q roster.
                del expected_q
                if not isinstance(raw_entry, Mapping):
                    _fail("sidecar manifest input is not an object")
                source_path = Path(str(raw_entry.get("path"))).resolve()
                record = {
                    "schema": SIDECAR_MANIFEST_SCHEMA,
                    "schema_version": 1,
                    "q": _integer(
                        raw_entry.get("q"),
                        "sidecar manifest q",
                        minimum=SOURCE_Q_START,
                        maximum=SOURCE_Q_STOP,
                    ),
                    "path": str(source_path),
                    "sha256": _digest(
                        raw_entry.get("sha256"),
                        "sidecar source artifact",
                    ),
                    "size_bytes": _integer(
                        raw_entry.get("size_bytes"),
                        "sidecar source artifact bytes",
                        minimum=1,
                        maximum=MAXIMUM_BLOCK_BYTES,
                    ),
                }
                raw = canonical_json_bytes(record)
                output.write(raw)
                digest.update(raw)
                size += len(raw)
                count += 1
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "size_bytes": size,
        "record_count": count,
    }


def _seeded_sidecar(
    record: Mapping[str, Any],
    *,
    q: int,
    first_t_index: int,
    block_stop: int,
    row_payloads: tuple[bytes, ...],
) -> tuple[bytes, bytes, dict[str, int | str]]:
    path = _normalized_path(record["path"], "seeded input path")
    with _open_regular(path, label=f"q={q} seeded input") as source:
        initial = os.fstat(source.fileno())
        if initial.st_size != record["size_bytes"]:
            _fail("seeded input size differs from its manifest pin")
        source_digest = hashlib.sha256()
        raw_header = _read_exact(
            source,
            SEEDED_BATCH_HEADER.size,
            label="TGDLQB2 header",
            digest=source_digest,
        )
        (
            magic,
            version,
            frame_q,
            rows,
            degree,
            component_count,
            batch_count,
            m,
            reserved0,
            group_order,
            first_t_numerator,
            denominator,
            step_numerator,
            lattice_count,
            value_count,
            reserved1,
        ) = SEEDED_BATCH_HEADER.unpack(raw_header)
        expected_stop = min(block_stop, maximum_t_index(q) + 1)
        expected_batch = expected_stop - first_t_index
        residues = canonical_residue_order(q)
        orders = canonical_component_orders(q)
        if (
            magic != SEEDED_BATCH_MAGIC
            or version != 2
            or frame_q != q
            or rows != LATTICE_ROWS
            or degree != TAYLOR_DEGREE
            or component_count != len(orders)
            or batch_count != expected_batch
            or not 1 <= batch_count <= MAXIMUM_BATCH_COUNT
            or m != SOURCE_M
            or reserved0 != 0
            or reserved1 != 0
            or group_order != len(residues)
            or first_t_numerator
            != first_t_index * SOURCE_SAMPLE_NUMERATOR
            or denominator != SOURCE_SAMPLE_DENOMINATOR
            or step_numerator != SOURCE_SAMPLE_NUMERATOR
            or lattice_count
            != batch_count * LATTICE_ROWS * TAYLOR_COLUMNS
            or value_count != batch_count * group_order
        ):
            _fail("seeded input does not cover the exact t-major target")

        for a in residues:
            raw = _read_exact(
                source,
                RESIDUE_DESCRIPTOR.size,
                label="TGDLQB2 descriptor",
                digest=source_digest,
            )
            if RESIDUE_DESCRIPTOR.unpack(raw) != (
                a,
                canonical_lattice_row(q, a),
            ):
                _fail("seeded input descriptor table is not canonical")

        factors = _read_exact(
            source,
            batch_count * FRAME_FACTOR.size,
            label="TGDLQB2 factors",
            digest=source_digest,
        )
        _validate_factor_bytes(factors)
        for index in range(batch_count):
            raw = _read_exact(
                source,
                ROW_PAYLOAD_BYTES,
                label="TGDLQB2 lattice row",
                digest=source_digest,
            )
            if raw != row_payloads[index]:
                _fail(
                    "seeded input lattice payload differs from the "
                    "authenticated t-major spool"
                )
        tails = _read_exact(
            source,
            batch_count * 8,
            label="TGDLQB2 tail radii",
            digest=source_digest,
        )
        _validate_tail_bytes(tails)
        if source.read(1):
            _fail("seeded input has trailing bytes")
        final = os.fstat(source.fileno())
        if _stat_identity(final) != _stat_identity(initial):
            _fail("seeded input changed while it was parsed")
    observed_sha = source_digest.hexdigest()
    if observed_sha != record["sha256"]:
        _fail("seeded input digest differs from its manifest pin")
    return factors, tails, {
        "sha256": observed_sha,
        "size_bytes": initial.st_size,
        "component_count": component_count,
        "batch_count": batch_count,
        "group_order": group_order,
        "value_count": value_count,
        "first_t_numerator": first_t_numerator,
    }


def _manifest_artifact(
    path: Path, *, expected_sha256: str
) -> dict[str, Any]:
    observed = _hash_file(path, label="sidecar manifest")
    if observed["sha256"] != _digest(
        expected_sha256, "expected sidecar manifest"
    ):
        _fail("sidecar manifest differs from its external pin")
    return observed


def _manifest_chain(
    path: Path,
    *,
    q_start: int,
    q_stop: int,
    first_t_index: int,
) -> tuple[str, int, int]:
    """Recheck the canonical roster and derive its source-input chain."""

    chain = hashlib.sha256(SOURCE_INPUT_CHAIN_DOMAIN)
    source_bytes = 0
    count = 0
    with _open_regular(path, label="sidecar manifest") as source:
        initial = os.fstat(source.fileno())
        for expected_q in _expected_qs(
            q_start=q_start,
            q_stop=q_stop,
            first_t_index=first_t_index,
        ):
            raw_line = source.readline(MAXIMUM_MANIFEST_LINE_BYTES + 1)
            if (
                not raw_line
                or len(raw_line) > MAXIMUM_MANIFEST_LINE_BYTES
            ):
                _fail(
                    "sidecar manifest ended early or has an oversized line"
                )
            record = _manifest_record(
                _parse_json(
                    raw_line,
                    label=f"sidecar manifest q={expected_q}",
                ),
                expected_q=expected_q,
            )
            chain.update(
                struct.pack("<IQ", expected_q, record["size_bytes"])
            )
            chain.update(bytes.fromhex(record["sha256"]))
            source_bytes += record["size_bytes"]
            count += 1
        if source.read(1):
            _fail("sidecar manifest contains extra target records")
        if _stat_identity(os.fstat(source.fileno())) != _stat_identity(
            initial
        ):
            _fail("sidecar manifest changed while it was replayed")
    return chain.hexdigest(), source_bytes, count


def _receipt_body(
    *,
    classification: str,
    contract_sha256: str,
    spool_receipt_sha256: str,
    lane_index: int,
    q_start: int,
    q_stop: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    row_bindings_sha256: str,
    seed_artifact_sha256: str,
    seed_replay_sha256: str,
    sidecar_mode: int,
    sidecar_source: Mapping[str, Any],
    artifact: Mapping[str, Any],
    row_count: int,
    target_count: int,
    target_row_reference_count: int,
    value_count: int,
    sidecar_bytes: int,
    source_input_bytes: int,
    canonical_descriptor_bytes: int,
    source_input_chain_sha256: str,
) -> dict[str, Any]:
    q_major_lattice_bytes = target_row_reference_count * ROW_PAYLOAD_BYTES
    row_resident_lattice_bytes = row_count * ROW_PAYLOAD_BYTES
    source_headers = target_count * SEEDED_BATCH_HEADER.size
    logical_qmajor_input_bytes = (
        source_headers
        + canonical_descriptor_bytes
        + q_major_lattice_bytes
        + sidecar_bytes
    )
    if (
        sidecar_mode
        not in {SIDECAR_MODE_QMAJOR_MANIFEST, SIDECAR_MODE_DIRECT_MPFR}
        or canonical_descriptor_bytes % RESIDUE_DESCRIPTOR.size
        or (
            sidecar_mode == SIDECAR_MODE_QMAJOR_MANIFEST
            and source_input_bytes != logical_qmajor_input_bytes
        )
        or (
            sidecar_mode == SIDECAR_MODE_DIRECT_MPFR
            and source_input_bytes != 0
        )
    ):
        _fail("source sidecar mode or byte decomposition differs")
    direct = sidecar_mode == SIDECAR_MODE_DIRECT_MPFR
    return {
        "schema": RECEIPT_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "classification": classification,
        "source_contract_sha256": contract_sha256,
        "spool_receipt_sha256": spool_receipt_sha256,
        "lane_index": lane_index,
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": t_index_stop_exclusive,
        "row_bindings_sha256": row_bindings_sha256,
        "recovery_seed_artifact_sha256": seed_artifact_sha256,
        "recovery_seed_replay_sha256": seed_replay_sha256,
        "sidecar_mode": sidecar_mode,
        "sidecar_source": dict(sidecar_source),
        "artifact": dict(artifact),
        "source_seeded_input_chain_sha256": (
            source_input_chain_sha256
        ),
        "accounting": {
            "authenticated_unique_row_count": row_count,
            "active_target_count": target_count,
            "target_row_reference_count": target_row_reference_count,
            "output_value_count": value_count,
            "factor_and_tail_sidecar_bytes": sidecar_bytes,
            "source_seeded_input_bytes_consumed": source_input_bytes,
            "logical_qmajor_seeded_input_bytes": logical_qmajor_input_bytes,
            "q_major_repeated_lattice_bytes": q_major_lattice_bytes,
            "row_resident_lattice_bytes": row_resident_lattice_bytes,
            "repeated_lattice_bytes_elided": (
                q_major_lattice_bytes - row_resident_lattice_bytes
            ),
            "canonical_descriptor_bytes_elided": canonical_descriptor_bytes,
            "cuda_input_artifact_bytes": artifact["size_bytes"],
            "bounded_rows_in_memory": row_count,
        },
        "decisions": {
            "source_contract_and_spool_revalidated": True,
            "every_row_rehashed_from_the_open_spool": True,
            "every_source_TGDLQB2_hash_and_shape_validated": not direct,
            "source_lattice_payloads_equal_authenticated_spool_rows": (
                not direct
            ),
            "canonical_descriptors_validated_then_elided": not direct,
            "qmajor_seeded_inputs_consumed": not direct,
            "directed_MPFR_factors_generated": direct,
            "higher_precision_MPFR_factor_containment_replayed": direct,
            "exact_rational_uniform_Taylor_tail_replayed": direct,
            "canonical_descriptors_formulaically_elided": direct,
            "factor_and_tail_bytes_bound_in_artifact": True,
            "one_copy_per_row_cuda_input_materialized": True,
            "row_resident_cuda_execution_completed": False,
            "all_character_fft_executed": False,
            "completed_l_zero_state_validated": False,
            "zero_completeness_claimed": False,
            "turing_completeness_claimed": False,
            "source_scale_run": False,
            "trusted_execution_attested": False,
            "external_atom_discharged": False,
        },
    }


class TMajorCudaBlockBuilder:
    """Reuse one authenticated open spool across successive block builds."""

    def __init__(
        self,
        *,
        contract_path: Path,
        spool_receipt_path: Path,
        expected_spool_receipt_sha256: str,
        expected_contract_sha256: str | None = None,
        allow_structural_kat: bool = False,
    ) -> None:
        self.spool = AuthenticatedQContiguousSpool(
            spool_receipt_path,
            contract_path=contract_path,
            expected_receipt_sha256=expected_spool_receipt_sha256,
            expected_contract_sha256=expected_contract_sha256,
            allow_structural_kat=allow_structural_kat,
        )

    def close(self) -> None:
        self.spool.close()

    def __enter__(self) -> "TMajorCudaBlockBuilder":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def build(
        self,
        output_path: Path,
        receipt_path: Path,
        *,
        first_t_index: int,
        sidecar_manifest_path: Path | None = None,
        expected_sidecar_manifest_sha256: str | None = None,
        direct_sidecars: bool = False,
    ) -> dict[str, Any]:
        if (
            output_path.exists()
            or output_path.is_symlink()
            or receipt_path.exists()
            or receipt_path.is_symlink()
        ):
            _fail("refusing to replace immutable block output or receipt")
        spool = self.spool
        block_stop = min(
            spool.lane_stop, first_t_index + MAXIMUM_BATCH_COUNT
        )
        row_source = spool.block_row_source(
            first_t_index=first_t_index,
            t_index_stop_exclusive=block_stop,
        )
        row_count = row_source["row_count"]
        schedule = spool.contract["schedule"]
        q_start = schedule["q_start_inclusive"]
        q_stop = schedule["q_stop_inclusive"]
        target_count = sum(
            1
            for _q in _expected_qs(
                q_start=q_start,
                q_stop=q_stop,
                first_t_index=first_t_index,
            )
        )
        generator: MPFRFactorProvider | None = None
        replayer: MPFRFactorProvider | None = None
        tail_words: tuple[bytes, ...] | None = None
        if direct_sidecars:
            if (
                sidecar_manifest_path is not None
                or expected_sidecar_manifest_sha256 is not None
            ):
                _fail("direct sidecars do not accept a q-major manifest")
            generator = MPFRFactorProvider(DIRECT_FACTOR_PRECISION_BITS)
            replayer = MPFRFactorProvider(
                DIRECT_FACTOR_REPLAY_PRECISION_BITS
            )
            if generator.version != replayer.version:
                _fail("direct factor generation/replay MPFR versions differ")
            recipe = _direct_recipe(
                q_start=q_start,
                q_stop=q_stop,
                first_t_index=first_t_index,
                t_index_stop_exclusive=block_stop,
                mpfr_version=generator.version,
            )
            sidecar_mode = SIDECAR_MODE_DIRECT_MPFR
            sidecar_source: dict[str, Any] = {
                "mode": "direct_mpfr_uniform_tail_v1",
                "recipe": recipe,
            }
            sidecar_source_sha256 = recipe["recipe_sha256"]
            expected_source_chain = None
            expected_source_input_bytes = 0
            tail_words = _global_tail_words(
                first_t_index=first_t_index,
                t_index_stop_exclusive=block_stop,
            )
        else:
            if (
                sidecar_manifest_path is None
                or expected_sidecar_manifest_sha256 is None
            ):
                _fail("q-major conversion requires an externally pinned manifest")
            manifest = _manifest_artifact(
                sidecar_manifest_path,
                expected_sha256=expected_sidecar_manifest_sha256,
            )
            (
                expected_source_chain,
                expected_source_input_bytes,
                manifest_target_count,
            ) = _manifest_chain(
                sidecar_manifest_path,
                q_start=q_start,
                q_stop=q_stop,
                first_t_index=first_t_index,
            )
            if manifest_target_count != target_count:
                _fail("sidecar manifest target count differs")
            sidecar_mode = SIDECAR_MODE_QMAJOR_MANIFEST
            sidecar_source = {
                "mode": "qmajor_seeded_manifest_v1",
                "manifest": manifest,
            }
            sidecar_source_sha256 = manifest["sha256"]
        recovery = spool.contract["recovery"]
        seed_artifact_sha256 = _digest(
            recovery["artifact"]["sha256"], "contract recovery artifact"
        )
        seed_replay_sha256 = _digest(
            recovery["replay_sha256"], "contract recovery replay"
        )
        header = BLOCK_HEADER.pack(
            BLOCK_MAGIC,
            FORMAT_VERSION,
            spool.lane_index,
            row_count,
            target_count,
            q_start,
            q_stop,
            SOURCE_M,
            sidecar_mode,
            first_t_index,
            block_stop,
            ROW_PAYLOAD_BYTES,
            ROW_HEADER.size + ROW_PAYLOAD_BYTES,
            TARGET_HEADER.size,
            bytes.fromhex(spool.contract["contract_sha256"]),
            bytes.fromhex(spool.receipt_sha256),
            bytes.fromhex(row_source["row_bindings_sha256"]),
            bytes.fromhex(seed_artifact_sha256),
            bytes.fromhex(seed_replay_sha256),
            bytes.fromhex(sidecar_source_sha256),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", dir=output_path.parent
        )
        temporary = Path(temporary_name)
        row_stream = hashlib.sha256()
        target_stream = hashlib.sha256()
        source_chain = hashlib.sha256(
            DIRECT_SOURCE_CHAIN_DOMAIN
            if direct_sidecars
            else SOURCE_INPUT_CHAIN_DOMAIN
        )
        if direct_sidecars:
            source_chain.update(bytes.fromhex(sidecar_source_sha256))
        row_payloads: list[bytes] = []
        target_row_references = 0
        value_count = 0
        sidecar_bytes = 0
        source_input_bytes = 0
        canonical_descriptor_bytes = 0
        observed_targets = 0
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(header)
                for t_index, payload in spool.iter_block_rows(
                    first_t_index=first_t_index,
                    t_index_stop_exclusive=block_stop,
                ):
                    payload_sha = hashlib.sha256(payload).digest()
                    raw_header = ROW_HEADER.pack(
                        ROW_MAGIC,
                        FORMAT_VERSION,
                        0,
                        t_index,
                        len(payload),
                        payload_sha,
                    )
                    output.write(raw_header)
                    output.write(payload)
                    row_stream.update(raw_header)
                    row_stream.update(payload)
                    row_payloads.append(payload)
                if len(row_payloads) != row_count:
                    _fail("authenticated row stream count differs")

                def emit_target(
                    expected_q: int,
                    factors: bytes,
                    tails: bytes,
                    source: Mapping[str, int | str],
                ) -> None:
                    nonlocal target_row_references
                    nonlocal value_count
                    nonlocal sidecar_bytes
                    nonlocal source_input_bytes
                    nonlocal canonical_descriptor_bytes
                    nonlocal observed_targets
                    sidecar_sha = _target_sidecar_sha256(
                        q=expected_q,
                        batch_count=int(source["batch_count"]),
                        first_t_numerator=int(
                            source["first_t_numerator"]
                        ),
                        group_order=int(source["group_order"]),
                        factors=factors,
                        tails=tails,
                    )
                    raw_target = TARGET_HEADER.pack(
                        TARGET_MAGIC,
                        FORMAT_VERSION,
                        expected_q,
                        int(source["component_count"]),
                        int(source["batch_count"]),
                        0,
                        0,
                        int(source["group_order"]),
                        int(source["first_t_numerator"]),
                        SOURCE_SAMPLE_DENOMINATOR,
                        SOURCE_SAMPLE_NUMERATOR,
                        int(source["value_count"]),
                        len(factors),
                        len(tails),
                        bytes.fromhex(sidecar_sha),
                    )
                    output.write(raw_target)
                    output.write(factors)
                    output.write(tails)
                    target_stream.update(raw_target)
                    target_stream.update(factors)
                    target_stream.update(tails)
                    if direct_sidecars:
                        source_chain.update(
                            struct.pack(
                                "<IQ",
                                expected_q,
                                int(source["value_count"]),
                            )
                        )
                        source_chain.update(bytes.fromhex(sidecar_sha))
                    else:
                        source_chain.update(
                            struct.pack(
                                "<IQ",
                                expected_q,
                                int(source["size_bytes"]),
                            )
                        )
                        source_chain.update(
                            bytes.fromhex(str(source["sha256"]))
                        )
                        source_input_bytes += int(source["size_bytes"])
                    target_row_references += int(source["batch_count"])
                    value_count += int(source["value_count"])
                    sidecar_bytes += len(factors) + len(tails)
                    canonical_descriptor_bytes += (
                        int(source["group_order"])
                        * RESIDUE_DESCRIPTOR.size
                    )
                    observed_targets += 1

                if direct_sidecars:
                    assert generator is not None
                    assert replayer is not None
                    assert tail_words is not None
                    for expected_q in _expected_qs(
                        q_start=q_start,
                        q_stop=q_stop,
                        first_t_index=first_t_index,
                    ):
                        expected_stop = min(
                            block_stop, maximum_t_index(expected_q) + 1
                        )
                        factors, tails = _direct_sidecar(
                            generator=generator,
                            replayer=replayer,
                            q=expected_q,
                            first_t_index=first_t_index,
                            t_index_stop_exclusive=expected_stop,
                            tail_words=tail_words[
                                : expected_stop - first_t_index
                            ],
                        )
                        orders = canonical_component_orders(expected_q)
                        group_order = math.prod(orders)
                        batch_count = expected_stop - first_t_index
                        emit_target(
                            expected_q,
                            factors,
                            tails,
                            {
                                "component_count": len(orders),
                                "batch_count": batch_count,
                                "group_order": group_order,
                                "first_t_numerator": (
                                    first_t_index
                                    * SOURCE_SAMPLE_NUMERATOR
                                ),
                                "value_count": batch_count * group_order,
                            },
                        )
                else:
                    assert sidecar_manifest_path is not None
                    with _open_regular(
                        sidecar_manifest_path, label="sidecar manifest"
                    ) as manifest_source:
                        manifest_status = os.fstat(
                            manifest_source.fileno()
                        )
                        manifest_digest = hashlib.sha256()
                        manifest_size = 0
                        for expected_q in _expected_qs(
                            q_start=q_start,
                            q_stop=q_stop,
                            first_t_index=first_t_index,
                        ):
                            raw_line = manifest_source.readline(
                                MAXIMUM_MANIFEST_LINE_BYTES + 1
                            )
                            if (
                                not raw_line
                                or len(raw_line)
                                > MAXIMUM_MANIFEST_LINE_BYTES
                            ):
                                _fail(
                                    "sidecar manifest ended early or has an "
                                    "oversized line"
                                )
                            manifest_digest.update(raw_line)
                            manifest_size += len(raw_line)
                            record = _manifest_record(
                                _parse_json(
                                    raw_line,
                                    label=(
                                        f"sidecar manifest q={expected_q}"
                                    ),
                                ),
                                expected_q=expected_q,
                            )
                            factors, tails, source = _seeded_sidecar(
                                record,
                                q=expected_q,
                                first_t_index=first_t_index,
                                block_stop=block_stop,
                                row_payloads=tuple(row_payloads),
                            )
                            emit_target(
                                expected_q, factors, tails, source
                            )
                        if manifest_source.read(1):
                            _fail(
                                "sidecar manifest contains extra target records"
                            )
                        if (
                            _stat_identity(
                                os.fstat(manifest_source.fileno())
                            )
                            != _stat_identity(manifest_status)
                            or manifest_digest.hexdigest()
                            != manifest["sha256"]
                            or manifest_size != manifest["size_bytes"]
                        ):
                            _fail(
                                "sidecar manifest changed between its external "
                                "pin and block conversion"
                            )
                if observed_targets != target_count:
                    _fail("sidecar target count differs")
                if not direct_sidecars and (
                    source_chain.hexdigest() != expected_source_chain
                    or source_input_bytes != expected_source_input_bytes
                ):
                    _fail(
                        "source seeded-input chain differs from the retained "
                        "sidecar manifest"
                    )
                footer = BLOCK_FOOTER.pack(
                    FOOTER_MAGIC,
                    FORMAT_VERSION,
                    0,
                    row_count,
                    target_count,
                    target_row_references,
                    value_count,
                    sidecar_bytes,
                    source_input_bytes,
                    row_stream.digest(),
                    target_stream.digest(),
                    source_chain.digest(),
                )
                output.write(footer)
                output.flush()
                os.fsync(output.fileno())
            if temporary.stat().st_size > MAXIMUM_BLOCK_BYTES:
                _fail("t-major CUDA block exceeds its fixed byte bound")
            os.link(temporary, output_path)
            temporary.unlink()
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

        artifact_file = _hash_file(
            output_path, label="t-major CUDA block artifact"
        )
        artifact = {
            "schema": ARTIFACT_SCHEMA,
            "magic": BLOCK_MAGIC.decode("ascii"),
            **artifact_file,
        }
        classification = (
            "source_shaped_authenticated_row_resident_cuda_input_not_execution"
            if spool.contract["classification"]
            == SOURCE_CONTRACT_CLASSIFICATION
            else "bounded_structural_row_resident_cuda_input_kat"
        )
        body = _receipt_body(
            classification=classification,
            contract_sha256=spool.contract["contract_sha256"],
            spool_receipt_sha256=spool.receipt_sha256,
            lane_index=spool.lane_index,
            q_start=q_start,
            q_stop=q_stop,
            first_t_index=first_t_index,
            t_index_stop_exclusive=block_stop,
            row_bindings_sha256=row_source["row_bindings_sha256"],
            seed_artifact_sha256=seed_artifact_sha256,
            seed_replay_sha256=seed_replay_sha256,
            sidecar_mode=sidecar_mode,
            sidecar_source=sidecar_source,
            artifact=artifact,
            row_count=row_count,
            target_count=target_count,
            target_row_reference_count=target_row_references,
            value_count=value_count,
            sidecar_bytes=sidecar_bytes,
            source_input_bytes=source_input_bytes,
            canonical_descriptor_bytes=canonical_descriptor_bytes,
            source_input_chain_sha256=source_chain.hexdigest(),
        )
        receipt = dict(body)
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        try:
            _atomic_bytes(receipt_path, canonical_json_bytes(receipt))
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise
        replayed = replay_tmajor_cuda_block(
            output_path,
            receipt_path,
            expected_receipt_sha256=receipt["receipt_sha256"],
        )
        if replayed != receipt:
            _fail("fresh t-major CUDA block replay differs")
        return receipt


def _read_receipt(
    path: Path, *, expected_receipt_sha256: str
) -> dict[str, Any]:
    with _open_regular(path, label="t-major CUDA block receipt") as source:
        raw = source.read(MAXIMUM_RECEIPT_BYTES + 1)
    if not raw or len(raw) > MAXIMUM_RECEIPT_BYTES:
        _fail("t-major CUDA block receipt size is outside its bound")
    value = _parse_json(raw, label="t-major CUDA block receipt")
    claimed = _self_hash(
        value, "receipt_sha256", label="t-major CUDA block receipt"
    )
    if claimed != _digest(
        expected_receipt_sha256, "expected t-major CUDA block receipt"
    ):
        _fail("t-major CUDA block receipt differs from its external pin")
    return value


def replay_tmajor_cuda_block(
    artifact_path: Path,
    receipt_path: Path,
    *,
    expected_receipt_sha256: str,
) -> dict[str, Any]:
    """Stream and semantically recheck one immutable ``TGDLTMB1`` block."""

    receipt = _read_receipt(
        receipt_path,
        expected_receipt_sha256=expected_receipt_sha256,
    )
    sidecar_mode = receipt.get("sidecar_mode")
    sidecar_source = receipt.get("sidecar_source")
    if (
        type(sidecar_mode) is not int
        or sidecar_mode
        not in {SIDECAR_MODE_QMAJOR_MANIFEST, SIDECAR_MODE_DIRECT_MPFR}
        or not isinstance(sidecar_source, dict)
    ):
        _fail("receipt sidecar source is malformed")
    manifest_path: Path | None = None
    observed_manifest: dict[str, Any] | None = None
    direct_recipe: dict[str, Any] | None = None
    if sidecar_mode == SIDECAR_MODE_QMAJOR_MANIFEST:
        if (
            set(sidecar_source) != {"mode", "manifest"}
            or sidecar_source.get("mode")
            != "qmajor_seeded_manifest_v1"
            or not isinstance(sidecar_source.get("manifest"), dict)
        ):
            _fail("receipt q-major sidecar source is malformed")
        manifest_record = sidecar_source["manifest"]
        if set(manifest_record) != {"path", "sha256", "size_bytes"}:
            _fail("receipt sidecar manifest record is malformed")
        manifest_path = _normalized_path(
            manifest_record["path"], "receipt sidecar manifest path"
        )
        observed_manifest = _hash_file(
            manifest_path, label="receipt sidecar manifest"
        )
        if observed_manifest != manifest_record:
            _fail("retained sidecar manifest differs from its receipt")
        sidecar_source = {
            "mode": "qmajor_seeded_manifest_v1",
            "manifest": observed_manifest,
        }
    else:
        if (
            set(sidecar_source) != {"mode", "recipe"}
            or sidecar_source.get("mode")
            != "direct_mpfr_uniform_tail_v1"
            or not isinstance(sidecar_source.get("recipe"), dict)
        ):
            _fail("receipt direct sidecar source is malformed")
        direct_recipe = sidecar_source["recipe"]

    with _open_regular(
        artifact_path, label="t-major CUDA block artifact"
    ) as source:
        initial = os.fstat(source.fileno())
        if not 1 <= initial.st_size <= MAXIMUM_BLOCK_BYTES:
            _fail("t-major CUDA block artifact size is outside its bound")
        artifact_digest = hashlib.sha256()
        raw_header = _read_exact(
            source,
            BLOCK_HEADER.size,
            label="t-major CUDA block header",
            digest=artifact_digest,
        )
        (
            magic,
            version,
            lane_index,
            row_count,
            target_count,
            q_start,
            q_stop,
            m,
            block_sidecar_mode,
            first_t_index,
            block_stop,
            row_payload_bytes,
            row_record_bytes,
            target_header_bytes,
            raw_contract,
            raw_spool,
            raw_row_bindings,
            raw_seed,
            raw_seed_replay,
            raw_sidecar_source,
        ) = BLOCK_HEADER.unpack(raw_header)
        if (
            magic != BLOCK_MAGIC
            or version != FORMAT_VERSION
            or block_sidecar_mode != sidecar_mode
            or not SOURCE_Q_START <= q_start <= q_stop <= SOURCE_Q_STOP
            or m != SOURCE_M
            or not 1 <= row_count <= MAXIMUM_BATCH_COUNT
            or target_count < 1
            or first_t_index > SOURCE_MAX_T_INDEX
            or block_stop > SOURCE_MAX_T_INDEX + 1
            or block_stop != first_t_index + row_count
            or row_payload_bytes != ROW_PAYLOAD_BYTES
            or row_record_bytes != ROW_HEADER.size + ROW_PAYLOAD_BYTES
            or target_header_bytes != TARGET_HEADER.size
        ):
            _fail("t-major CUDA block header or exact geometry differs")
        expected_target_count = sum(
            1
            for _q in _expected_qs(
                q_start=q_start,
                q_stop=q_stop,
                first_t_index=first_t_index,
            )
        )
        if target_count != expected_target_count:
            _fail("t-major CUDA block target count differs from the formula")
        direct_generator: MPFRFactorProvider | None = None
        direct_replayer: MPFRFactorProvider | None = None
        direct_tail_words: tuple[bytes, ...] | None = None
        if sidecar_mode == SIDECAR_MODE_QMAJOR_MANIFEST:
            assert manifest_path is not None
            assert observed_manifest is not None
            if raw_sidecar_source.hex() != observed_manifest["sha256"]:
                _fail("t-major block sidecar manifest digest differs")
            (
                retained_source_chain,
                retained_source_bytes,
                retained_target_count,
            ) = _manifest_chain(
                manifest_path,
                q_start=q_start,
                q_stop=q_stop,
                first_t_index=first_t_index,
            )
            source_chain = hashlib.sha256(SOURCE_INPUT_CHAIN_DOMAIN)
        else:
            assert direct_recipe is not None
            (
                direct_recipe,
                direct_generator,
                direct_replayer,
            ) = _validate_direct_recipe(
                direct_recipe,
                q_start=q_start,
                q_stop=q_stop,
                first_t_index=first_t_index,
                t_index_stop_exclusive=block_stop,
            )
            if (
                raw_sidecar_source.hex()
                != direct_recipe["recipe_sha256"]
            ):
                _fail("t-major block direct sidecar recipe digest differs")
            sidecar_source = {
                "mode": "direct_mpfr_uniform_tail_v1",
                "recipe": direct_recipe,
            }
            retained_source_chain = None
            retained_source_bytes = 0
            retained_target_count = target_count
            source_chain = hashlib.sha256(DIRECT_SOURCE_CHAIN_DOMAIN)
            source_chain.update(raw_sidecar_source)
            direct_tail_words = _global_tail_words(
                first_t_index=first_t_index,
                t_index_stop_exclusive=block_stop,
            )
        if retained_target_count != target_count:
            _fail("retained sidecar source target count differs")

        row_stream = hashlib.sha256()
        row_identities: list[tuple[int, str]] = []
        for offset in range(row_count):
            raw_row = _read_exact(
                source,
                ROW_HEADER.size,
                label="t-major CUDA row header",
                digest=artifact_digest,
            )
            (
                row_magic,
                row_version,
                row_reserved,
                t_index,
                payload_bytes,
                payload_sha,
            ) = ROW_HEADER.unpack(raw_row)
            payload = _read_exact(
                source,
                ROW_PAYLOAD_BYTES,
                label="t-major CUDA row payload",
                digest=artifact_digest,
            )
            if (
                row_magic != ROW_MAGIC
                or row_version != FORMAT_VERSION
                or row_reserved != 0
                or t_index != first_t_index + offset
                or payload_bytes != ROW_PAYLOAD_BYTES
                or hashlib.sha256(payload).digest() != payload_sha
            ):
                _fail("t-major CUDA row is malformed or reordered")
            validate_lattice_row(payload)
            row_stream.update(raw_row)
            row_stream.update(payload)
            row_identities.append((t_index, payload_sha.hex()))
        row_binding = hashlib.sha256(BLOCK_ROW_BINDING_DOMAIN)
        row_binding.update(raw_spool)
        for t_index, payload_sha in row_identities:
            row_binding.update(t_index.to_bytes(8, "little"))
            row_binding.update(bytes.fromhex(payload_sha))
        if row_binding.digest() != raw_row_bindings:
            _fail("t-major CUDA row binding differs from the spool domain")

        target_stream = hashlib.sha256()
        target_rows = 0
        values = 0
        sidecar_bytes = 0
        canonical_descriptor_bytes = 0
        for expected_q in _expected_qs(
            q_start=q_start,
            q_stop=q_stop,
            first_t_index=first_t_index,
        ):
            raw_target = _read_exact(
                source,
                TARGET_HEADER.size,
                label="t-major CUDA target header",
                digest=artifact_digest,
            )
            (
                target_magic,
                target_version,
                q,
                component_count,
                batch_count,
                target_reserved0,
                target_reserved1,
                group_order,
                first_t_numerator,
                denominator,
                step,
                value_count,
                factor_bytes,
                tail_bytes,
                sidecar_sha,
            ) = TARGET_HEADER.unpack(raw_target)
            expected_batch = (
                min(block_stop, maximum_t_index(expected_q) + 1)
                - first_t_index
            )
            if (
                target_magic != TARGET_MAGIC
                or target_version != FORMAT_VERSION
                or q != expected_q
                or target_reserved0 != 0
                or target_reserved1 != 0
                or component_count
                != len(canonical_component_orders(expected_q))
                or batch_count != expected_batch
                or group_order != _totient(expected_q)
                or first_t_numerator
                != first_t_index * SOURCE_SAMPLE_NUMERATOR
                or denominator != SOURCE_SAMPLE_DENOMINATOR
                or step != SOURCE_SAMPLE_NUMERATOR
                or value_count != batch_count * group_order
                or factor_bytes != batch_count * FRAME_FACTOR.size
                or tail_bytes != batch_count * 8
            ):
                _fail("t-major CUDA target is malformed or reordered")
            factors = _read_exact(
                source,
                factor_bytes,
                label="t-major CUDA target factors",
                digest=artifact_digest,
            )
            tails = _read_exact(
                source,
                tail_bytes,
                label="t-major CUDA target tails",
                digest=artifact_digest,
            )
            _validate_factor_bytes(factors)
            _validate_tail_bytes(tails)
            if (
                _target_sidecar_sha256(
                    q=q,
                    batch_count=batch_count,
                    first_t_numerator=first_t_numerator,
                    group_order=group_order,
                    factors=factors,
                    tails=tails,
                )
                != sidecar_sha.hex()
            ):
                _fail("t-major CUDA target sidecar digest differs")
            if sidecar_mode == SIDECAR_MODE_DIRECT_MPFR:
                assert direct_generator is not None
                assert direct_replayer is not None
                assert direct_tail_words is not None
                expected_factors, expected_tails = _direct_sidecar(
                    generator=direct_generator,
                    replayer=direct_replayer,
                    q=q,
                    first_t_index=first_t_index,
                    t_index_stop_exclusive=(
                        first_t_index + batch_count
                    ),
                    tail_words=direct_tail_words[:batch_count],
                )
                if factors != expected_factors or tails != expected_tails:
                    _fail(
                        "direct MPFR factor or exact-rational tail replay differs"
                    )
                source_chain.update(
                    struct.pack("<IQ", q, value_count)
                )
                source_chain.update(sidecar_sha)
            target_stream.update(raw_target)
            target_stream.update(factors)
            target_stream.update(tails)
            target_rows += batch_count
            values += value_count
            sidecar_bytes += factor_bytes + tail_bytes
            canonical_descriptor_bytes += (
                group_order * RESIDUE_DESCRIPTOR.size
            )

        raw_footer = _read_exact(
            source,
            BLOCK_FOOTER.size,
            label="t-major CUDA block footer",
            digest=artifact_digest,
        )
        if source.read(1):
            _fail("t-major CUDA block has trailing bytes")
        (
            footer_magic,
            footer_version,
            footer_reserved,
            footer_rows,
            footer_targets,
            footer_target_rows,
            footer_values,
            footer_sidecars,
            footer_source_bytes,
            footer_row_stream,
            footer_target_stream,
            footer_source_chain,
        ) = BLOCK_FOOTER.unpack(raw_footer)
        expected_footer_chain = (
            retained_source_chain
            if sidecar_mode == SIDECAR_MODE_QMAJOR_MANIFEST
            else source_chain.hexdigest()
        )
        if (
            footer_magic != FOOTER_MAGIC
            or footer_version != FORMAT_VERSION
            or footer_reserved != 0
            or footer_rows != row_count
            or footer_targets != target_count
            or footer_target_rows != target_rows
            or footer_values != values
            or footer_sidecars != sidecar_bytes
            or footer_source_bytes != retained_source_bytes
            or footer_row_stream != row_stream.digest()
            or footer_target_stream != target_stream.digest()
            or footer_source_chain.hex() != expected_footer_chain
        ):
            _fail("t-major CUDA block footer or stream digests differ")
        final = os.fstat(source.fileno())
        if _stat_identity(final) != _stat_identity(initial):
            _fail("t-major CUDA block changed while it was replayed")

    artifact_file = {
        "path": str(artifact_path.resolve()),
        "sha256": artifact_digest.hexdigest(),
        "size_bytes": initial.st_size,
    }
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "magic": BLOCK_MAGIC.decode("ascii"),
        **artifact_file,
    }
    classification = receipt.get("classification")
    if classification not in {
        "source_shaped_authenticated_row_resident_cuda_input_not_execution",
        "bounded_structural_row_resident_cuda_input_kat",
    }:
        _fail("t-major CUDA block receipt classification differs")
    body = _receipt_body(
        classification=classification,
        contract_sha256=raw_contract.hex(),
        spool_receipt_sha256=raw_spool.hex(),
        lane_index=lane_index,
        q_start=q_start,
        q_stop=q_stop,
        first_t_index=first_t_index,
        t_index_stop_exclusive=block_stop,
        row_bindings_sha256=raw_row_bindings.hex(),
        seed_artifact_sha256=raw_seed.hex(),
        seed_replay_sha256=raw_seed_replay.hex(),
        sidecar_mode=sidecar_mode,
        sidecar_source=sidecar_source,
        artifact=artifact,
        row_count=row_count,
        target_count=target_count,
        target_row_reference_count=target_rows,
        value_count=values,
        sidecar_bytes=sidecar_bytes,
        source_input_bytes=footer_source_bytes,
        canonical_descriptor_bytes=canonical_descriptor_bytes,
        source_input_chain_sha256=footer_source_chain.hex(),
    )
    expected = dict(body)
    expected["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    if canonical_json_bytes(receipt) != canonical_json_bytes(expected):
        _fail("t-major CUDA block receipt differs from fresh replay")
    return expected


def validate_tmajor_cuda_execution_summary(
    summary_path: Path,
    artifact_path: Path,
    receipt_path: Path,
    *,
    expected_summary_sha256: str,
    expected_receipt_sha256: str,
) -> dict[str, Any]:
    """Type a CUDA terminal summary against a freshly replayed input block.

    The summary commits the exact emitted ``TGDAFFI1`` stream digest so a
    downstream transform can require byte continuity without retaining that
    stream.  This is still a statement by an unattested executable, not an
    independent arithmetic replay or trusted-execution receipt.
    """

    receipt = replay_tmajor_cuda_block(
        artifact_path,
        receipt_path,
        expected_receipt_sha256=expected_receipt_sha256,
    )
    summary_file = _hash_file(
        summary_path, label="t-major CUDA execution summary"
    )
    if summary_file["sha256"] != _digest(
        expected_summary_sha256, "expected CUDA execution summary"
    ):
        _fail("CUDA execution summary differs from its external pin")
    with _open_regular(
        summary_path, label="t-major CUDA execution summary"
    ) as source:
        raw = source.read(MAXIMUM_RECEIPT_BYTES + 1)
    if not raw or len(raw) > MAXIMUM_RECEIPT_BYTES:
        _fail("CUDA execution summary size is outside its bound")
    value = _parse_json(raw, label="t-major CUDA execution summary")
    required = {
        "algorithm_id",
        "all_character_fft_executed",
        "canonical_descriptor_input_bytes",
        "classification",
        "completed_l_zero_state_validated",
        "elapsed_kernel_nanoseconds",
        "external_atom_discharged",
        "input_artifact_sha256",
        "lane_index",
        "lattice_h2d_upload_count",
        "output_stream_sha256",
        "recovery_seed_artifact_sha256",
        "row_bindings_sha256",
        "row_count",
        "row_payload_h2d_bytes",
        "schema",
        "schema_version",
        "sidecar_source_sha256",
        "source_contract_sha256",
        "source_scale_run",
        "spool_receipt_sha256",
        "target_count",
        "transcendental_device_calls",
        "trusted_execution_attested",
        "value_count",
        "zero_completeness_claimed",
    }
    accounting = receipt["accounting"]
    _integer(
        value.get("schema_version"),
        "CUDA execution summary schema version",
        minimum=FORMAT_VERSION,
        maximum=FORMAT_VERSION,
    )
    _integer(
        value.get("elapsed_kernel_nanoseconds"),
        "CUDA elapsed kernel nanoseconds",
    )
    _integer(
        value.get("lane_index"),
        "CUDA lane index",
        maximum=(1 << 32) - 1,
    )
    _integer(
        value.get("lattice_h2d_upload_count"),
        "CUDA lattice H2D upload count",
        maximum=(1 << 32) - 1,
    )
    _integer(
        value.get("row_count"),
        "CUDA row count",
        minimum=1,
        maximum=MAXIMUM_BATCH_COUNT,
    )
    _integer(
        value.get("row_payload_h2d_bytes"),
        "CUDA row payload H2D bytes",
    )
    _integer(
        value.get("canonical_descriptor_input_bytes"),
        "CUDA canonical descriptor input bytes",
    )
    _integer(
        value.get("target_count"),
        "CUDA target count",
        minimum=1,
        maximum=SOURCE_Q_STOP - SOURCE_Q_START + 1,
    )
    _integer(
        value.get("transcendental_device_calls"),
        "CUDA transcendental device calls",
    )
    _integer(
        value.get("value_count"),
        "CUDA value count",
        minimum=1,
    )
    if (
        set(value) != required
        or value.get("schema") != EXECUTION_SUMMARY_SCHEMA
        or value.get("schema_version") != FORMAT_VERSION
        or value.get("algorithm_id") != CUDA_ALGORITHM_ID
        or value.get("classification")
        != (
            "row_resident_seeded_cuda_component_not_zero_or_"
            "turing_closure"
        )
        or value.get("input_artifact_sha256")
        != receipt["artifact"]["sha256"]
        or value.get("lane_index") != receipt["lane_index"]
        or value.get("lattice_h2d_upload_count") != 1
        or value.get("row_count")
        != accounting["authenticated_unique_row_count"]
        or value.get("row_payload_h2d_bytes")
        != accounting["row_resident_lattice_bytes"]
        or value.get("canonical_descriptor_input_bytes") != 0
        or value.get("target_count")
        != accounting["active_target_count"]
        or value.get("value_count") != accounting["output_value_count"]
        or value.get("source_contract_sha256")
        != receipt["source_contract_sha256"]
        or value.get("spool_receipt_sha256")
        != receipt["spool_receipt_sha256"]
        or value.get("row_bindings_sha256")
        != receipt["row_bindings_sha256"]
        or value.get("recovery_seed_artifact_sha256")
        != receipt["recovery_seed_artifact_sha256"]
        or value.get("sidecar_source_sha256")
        != (
            receipt["sidecar_source"]["manifest"]["sha256"]
            if receipt["sidecar_mode"]
            == SIDECAR_MODE_QMAJOR_MANIFEST
            else receipt["sidecar_source"]["recipe"]["recipe_sha256"]
        )
        or value.get("transcendental_device_calls") != 0
        or value.get("all_character_fft_executed") is not False
        or value.get("completed_l_zero_state_validated") is not False
        or value.get("source_scale_run") is not False
        or value.get("trusted_execution_attested") is not False
        or value.get("zero_completeness_claimed") is not False
        or value.get("external_atom_discharged") is not False
    ):
        _fail("CUDA execution summary identity or claim boundary differs")
    output_sha256 = _digest(
        value.get("output_stream_sha256"), "CUDA TGDAFFI1 output stream"
    )
    body = {
        "schema": EXECUTION_REPLAY_SCHEMA,
        "schema_version": FORMAT_VERSION,
        "algorithm_id": ALGORITHM_ID,
        "classification": (
            "typed_row_resident_cuda_summary_not_arithmetic_replay_or_"
            "attestation"
        ),
        "input_receipt_sha256": receipt["receipt_sha256"],
        "input_artifact_sha256": receipt["artifact"]["sha256"],
        "execution_summary": summary_file,
        "output_stream_sha256": output_sha256,
        "row_count": accounting["authenticated_unique_row_count"],
        "target_count": accounting["active_target_count"],
        "value_count": accounting["output_value_count"],
        "one_lattice_h2d_upload_reported": True,
        "summary_typed_against_fresh_input_replay": True,
        "discarded_cuda_arithmetic_independently_replayed": False,
        "all_character_fft_executed": False,
        "completed_l_zero_state_validated": False,
        "zero_completeness_claimed": False,
        "turing_completeness_claimed": False,
        "source_scale_run": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
    result = dict(body)
    result["replay_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def source_projection() -> dict[str, Any]:
    """Exact binary-input accounting for the fixed eight-lane source plan."""

    row_count = SOURCE_MAX_T_INDEX + 1
    block_count = 2_000
    active_moduli = 0
    target_count = 0
    target_row_reference_count = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        if not has_primitive_character_modulus(q):
            continue
        active_moduli += 1
        rows = maximum_t_index(q) + 1
        target_row_reference_count += rows
        target_count += (rows + MAXIMUM_BATCH_COUNT - 1) // MAXIMUM_BATCH_COUNT
    if (
        active_moduli != PINNED_PRIMITIVE_SOURCE_ACTIVE_MODULI
        or target_row_reference_count != PINNED_PRIMITIVE_SOURCE_Q_T_ROWS
        or target_count != PINNED_PRIMITIVE_SOURCE_BATCH64_TARGETS
    ):
        _fail("primitive-only t-major source roster invariant failed")
    row_bytes = row_count * (ROW_HEADER.size + ROW_PAYLOAD_BYTES)
    target_header_bytes = target_count * TARGET_HEADER.size
    factor_and_tail_bytes = target_row_reference_count * (
        FRAME_FACTOR.size + 8
    )
    block_envelope_bytes = block_count * (
        BLOCK_HEADER.size + BLOCK_FOOTER.size
    )
    total = (
        row_bytes
        + target_header_bytes
        + factor_and_tail_bytes
        + block_envelope_bytes
    )
    if total != 286_556_459_000:
        _fail("direct t-major source projection invariant failed")
    old_tmajor_model = 41_413_846_139_376
    old_seeded_qmajor_model = 5_180_404_381_680_112
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_tmajor_cuda_block."
            "source_projection.v2"
        ),
        "classification": (
            "exact_binary_input_accounting_not_runtime_or_atom_eta"
        ),
        "fixed_eight_lane_block_count": block_count,
        "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "active_modulus_count": active_moduli,
        "excluded_empty_primitive_roster_moduli": (
            SOURCE_Q_STOP - SOURCE_Q_START + 1 - active_moduli
        ),
        "authenticated_unique_row_count": row_count,
        "active_target_count": target_count,
        "target_row_reference_count": target_row_reference_count,
        "input_bytes": {
            "authenticated_rows_with_headers": row_bytes,
            "target_headers": target_header_bytes,
            "directed_mpfr_factor_and_exact_tail_sidecars": (
                factor_and_tail_bytes
            ),
            "block_headers_and_footers": block_envelope_bytes,
            "total": total,
        },
        "separate_recovery_seed_artifact_bytes": 96_008_016,
        "total_including_recovery_seeds": total + 96_008_016,
        "former_41TB_tmajor_model_reduction_ratio": (
            old_tmajor_model / total
        ),
        "former_5PB_qmajor_model_reduction_ratio": (
            old_seeded_qmajor_model / total
        ),
        "qmajor_TGDLQB2_source_files_required": False,
        "runtime_estimated": False,
        "source_scale_run": False,
        "external_atom_discharged": False,
    }


def benchmark_direct_sidecars(
    *,
    q: int = SOURCE_Q_START,
    batch_count: int = MAXIMUM_BATCH_COUNT,
    repetitions: int = 64,
) -> dict[str, Any]:
    """Bounded local factor/tail generation plus containment-replay timing."""

    if (
        not SOURCE_Q_START <= q <= SOURCE_Q_STOP
        or not has_primitive_character_modulus(q)
        or not 1 <= batch_count <= MAXIMUM_BATCH_COUNT
        or not 1 <= repetitions <= 10_000
        or batch_count - 1 > maximum_t_index(q)
    ):
        _fail("direct-sidecar benchmark geometry differs")
    generator = MPFRFactorProvider(DIRECT_FACTOR_PRECISION_BITS)
    replayer = MPFRFactorProvider(DIRECT_FACTOR_REPLAY_PRECISION_BITS)
    tails = _global_tail_words(
        first_t_index=0, t_index_stop_exclusive=batch_count
    )
    alternate_q = q + 1
    while (
        alternate_q <= SOURCE_Q_STOP
        and not has_primitive_character_modulus(alternate_q)
    ):
        alternate_q += 1
    if alternate_q > SOURCE_Q_STOP:
        alternate_q = q - 1
        while (
            alternate_q >= SOURCE_Q_START
            and not has_primitive_character_modulus(alternate_q)
        ):
            alternate_q -= 1
    if alternate_q < SOURCE_Q_START:
        _fail("direct-sidecar alternate source modulus is unavailable")
    if batch_count - 1 > maximum_t_index(alternate_q):
        _fail("direct-sidecar alternate benchmark geometry differs")
    started = time.perf_counter()
    emitted = 0
    for repetition in range(repetitions):
        factors, tail_bytes = _direct_sidecar(
            generator=generator,
            replayer=replayer,
            q=q if repetition % 2 == 0 else alternate_q,
            first_t_index=0,
            t_index_stop_exclusive=batch_count,
            tail_words=tails,
        )
        emitted += len(factors) // FRAME_FACTOR.size
        if len(tail_bytes) != batch_count * 8:
            _fail("direct-sidecar benchmark tail bytes differ")
    elapsed = time.perf_counter() - started
    rate = emitted / elapsed
    single_pass_hours = PINNED_PRIMITIVE_SOURCE_Q_T_ROWS / rate / 3600
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_tmajor_cuda_block."
            "direct_sidecar_benchmark.v2"
        ),
        "classification": (
            "bounded_local_mpfr_component_measurement_not_source_or_h100_eta"
        ),
        "q": q,
        "alternating_q": alternate_q,
        "batch_count": batch_count,
        "repetitions": repetitions,
        "factor_enclosures_generated_and_higher_precision_replayed": emitted,
        "persistent_mpfr_workspaces": 2,
        "per_workspace_q_base_cache": True,
        "q_base_cache_recomputed_per_batch": True,
        "elapsed_seconds": elapsed,
        "factor_enclosures_per_second": rate,
        "straight_line_source_factor_tail_single_process_hours": (
            single_pass_hours
        ),
        "straight_line_source_factor_tail_320_process_ideal_hours": (
            single_pass_hours / 320
        ),
        "warning": (
            "The projection covers direct factor/tail generation plus one "
            "higher-precision containment pass only. It assumes perfect "
            "scaling and excludes cache generation, CUDA composition, FFT, "
            "completed-L, zero/Turing work, I/O, replay, and attestation."
        ),
        "source_scale_run": False,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    projection = source_projection()
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": (
            "authenticated_row_resident_seeded_cuda_input_and_replay_"
            "not_zero_or_turing_closure"
        ),
        "authenticated_tmajor_spool_consumed": True,
        "one_copy_per_row_block_artifact": True,
        "qmajor_conversion_path_rechecks_every_repeated_row": True,
        "canonical_descriptors_validated_or_formulaically_elided": True,
        "factor_and_tail_sidecars_bound_exactly": True,
        "bounded_memory_maximum_rows": MAXIMUM_BATCH_COUNT,
        "formulaic_active_q_roster": True,
        "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "empty_primitive_roster_moduli_excluded": True,
        "streaming_sidecar_manifest": True,
        "direct_directed_mpfr_factor_producer": True,
        "persistent_mpfr_factor_workspace": True,
        "persistent_mpfr_q_base_cache": True,
        "higher_precision_mpfr_factor_containment_replay": True,
        "direct_exact_rational_uniform_tail_producer_and_replay": True,
        "direct_path_requires_qmajor_TGDLQB2_inputs": False,
        "direct_source_binary_input_bytes": projection["input_bytes"][
            "total"
        ],
        "direct_source_input_including_recovery_seeds": projection[
            "total_including_recovery_seeds"
        ],
        "independent_binary_replay": True,
        "parsed_seed_bytes_rehashed_against_external_pin": True,
        "cuda_consumed_block_bytes_rehashed_against_external_pin": True,
        "bounded_exact_cuda_arithmetic_sample_checker": True,
        "bounded_independent_arb_factor_checker": True,
        "source_scale_cuda_arithmetic_replay_completed": False,
        "compiler_to_sass_refinement_proved": False,
        "row_resident_cuda_mode_source": (
            "gpu/platform/h100/h100_tg_dirichlet_largeq_seeded_batch.cu"
        ),
        "source_scale_run_completed": False,
        "direct_source_sidecar_producer_implemented": True,
        "all_character_multi_q_service_integrated": False,
        "typed_bundle_output_integrated": False,
        "completed_l_zero_state_import_export_implemented": False,
        "zero_completeness_claimed": False,
        "turing_completeness_claimed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "ARTIFACT_SCHEMA",
    "BLOCK_FOOTER",
    "BLOCK_HEADER",
    "BLOCK_MAGIC",
    "DirichletTMajorCudaBlockError",
    "EXECUTION_REPLAY_SCHEMA",
    "EXECUTION_SUMMARY_SCHEMA",
    "FORMAT_VERSION",
    "PINNED_PRIMITIVE_SOURCE_ACTIVE_MODULI",
    "PINNED_PRIMITIVE_SOURCE_BATCH64_TARGETS",
    "PINNED_PRIMITIVE_SOURCE_Q_T_ROWS",
    "RECEIPT_SCHEMA",
    "ROW_HEADER",
    "ROW_MAGIC",
    "SIDECAR_MANIFEST_SCHEMA",
    "TARGET_HEADER",
    "TARGET_MAGIC",
    "TMajorCudaBlockBuilder",
    "capability",
    "benchmark_direct_sidecars",
    "replay_tmajor_cuda_block",
    "source_projection",
    "validate_tmajor_cuda_execution_summary",
    "write_sidecar_manifest",
]

# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Certified recurrence seeds for Platt's large-q finite recovery.

For the exact source grid ``t_j = 5*j/64`` and the currently selected
``M = 4``, every finite-recovery term has the identity

``(q*n+a)^(-1/2-i*t_j) = A_x * W_x^j``

where ``x=q*n+a``, ``A_x=x^(-1/2)``, and
``W_x=exp(-i*(5/64)*log(x))``.  Across ``q <= 400000`` and ``0 <= n <= 4``
only ``1 <= x <= 1999999`` occurs.  A roughly 96 MB seed table can therefore
replace the 13.084 PB logical stream of per-(q,a,t) recovery rectangles.

This module generates outward binary64 seed intervals with pinned Arb/FLINT,
authenticates each bounded chunk before exposing it, and replays every seed at
higher precision through a separately structured formula.  It does not prove
that recurrence widths are sufficient for zero isolation, run a GPU, perform
the Turing argument, or discharge Platt's Theorem 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Any, BinaryIO, Iterator, Mapping, NoReturn

from tg_verifier.dirichlet_lattice_certificates import (
    DEFAULT_REPLAY_GUARD_BITS,
    EXPECTED_FLINT,
    EXPECTED_FLINT_RELEASE,
    EXPECTED_PYTHON_FLINT,
    _binary64_box,
    _contains_arb,
    _exact_arb_endpoint,
    _downward_binary64,
    _upward_binary64,
    _validate_runtime_record,
    runtime_identity,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-finite-recovery-recurrence-seeds-v1"
CHECKER_ID = "higher-precision-arb-exp-replay-v1"
MANIFEST_SCHEMA = "sparkinterval.tg.dirichlet_recovery_seeds.manifest.v1"
REPLAY_SCHEMA = "sparkinterval.tg.dirichlet_recovery_seeds.replay.v1"

FORMAT_VERSION = 1
SOURCE_MAX_Q = 400_000
SOURCE_M = 4
SOURCE_X_START = 1
SOURCE_X_STOP = (SOURCE_M + 1) * SOURCE_MAX_Q - 1
SOURCE_STEP_NUMERATOR = 5
SOURCE_STEP_DENOMINATOR = 64
DEFAULT_PRECISION_BITS = 192
DEFAULT_REPLAY_PRECISION_BITS = 320
DEFAULT_CHUNK_RECORDS = 16_384
MAXIMUM_CHUNK_RECORDS = 1 << 20
MAXIMUM_ARTIFACT_BYTES = 256 * 1024 * 1024

HEADER_MAGIC = b"TGDRCVS1"
CHUNK_MAGIC = b"TGDRCVC1"
FOOTER_MAGIC = b"TGDRCVF1"
OUTPUT_MAGIC = b"TGDRCVO1"
SEEDED_BATCH_MAGIC = b"TGDLQB2\0"

# Header fields are format, M, maximum q, record bytes, x range, exact grid,
# record count, two generation precisions, chunk size, and two reserved words.
HEADER = struct.Struct("<8sIIIIQQQQQIIQQQ")
CHUNK_HEADER = struct.Struct("<8sIIQQ32s")
SEED_RECORD = struct.Struct("<dddddd")
FOOTER = struct.Struct("<8sIIQQ32s32s")
OUTPUT_HEADER = struct.Struct("<8sIIIIQQQQQQ")
OUTPUT_RECORD = struct.Struct("<dddd")
SEEDED_BATCH_HEADER = struct.Struct("<8sIIIIIIIIQqQQQQQ")

assert HEADER.size == 96
assert CHUNK_HEADER.size == 64
assert SEED_RECORD.size == 48
assert FOOTER.size == 96
assert OUTPUT_HEADER.size == 72
assert OUTPUT_RECORD.size == 32
assert SEEDED_BATCH_HEADER.size == 96

CHUNK_DOMAIN = b"sparkinterval/dirichlet-recovery-seed-chunk/v1\0"
ROOT_DOMAIN = b"sparkinterval/dirichlet-recovery-seed-root/v1\0"


class DirichletRecoverySeedError(RuntimeError):
    """A source parameter, artifact, interval, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletRecoverySeedError(message)


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _atomic_bytes(path: Path, raw: bytes) -> None:
    if path.exists():
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
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _load_flint() -> Any:
    try:
        import flint  # type: ignore[import-not-found]
    except ImportError as error:
        raise DirichletRecoverySeedError(
            "python-flint==0.9.0 with FLINT 3.6.0 is required"
        ) from error
    if (
        str(flint.__version__) != EXPECTED_PYTHON_FLINT
        or str(flint.__FLINT_VERSION__) != EXPECTED_FLINT
        or int(flint.__FLINT_RELEASE__) != EXPECTED_FLINT_RELEASE
    ):
        _fail("loaded python-flint / FLINT runtime differs from the pinned runtime")
    return flint


def _file_record(path: Path) -> dict[str, Any]:
    digest, size = sha256_file(path)
    return {"sha256": digest, "size_bytes": size}


def _canonical_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail("manifest is missing or is not a regular file")
    raw = path.read_bytes()
    if not raw or len(raw) > 4 * 1024 * 1024:
        _fail("manifest size is outside its fixed bound")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletRecoverySeedError("invalid seed manifest JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail("seed manifest is not canonical JSON")
    body = dict(value)
    claimed = body.pop("manifest_sha256", None)
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail("seed manifest self-hash differs")
    return value


def _join_real(first: Any, second: Any) -> Any:
    return first.union(second)


def _generated_seed(flint: Any, x: int, precision_bits: int) -> tuple[float, ...]:
    """Union independent sqrt/trig and log/complex-exp generation paths."""

    with flint.ctx.workprec(precision_bits):
        base = flint.arb(x)
        first_amplitude = 1 / base.sqrt()
        first_angle = -flint.arb(SOURCE_STEP_NUMERATOR) * base.log()
        first_angle /= SOURCE_STEP_DENOMINATOR
        first_step = flint.acb(first_angle.cos(), first_angle.sin())
    with flint.ctx.workprec(precision_bits + DEFAULT_REPLAY_GUARD_BITS):
        base = flint.arb(x)
        logarithm = base.log()
        second_amplitude = (-logarithm / 2).exp()
        second_step = flint.acb(
            0,
            -flint.arb(SOURCE_STEP_NUMERATOR) * logarithm
            / SOURCE_STEP_DENOMINATOR,
        ).exp()
        amplitude = _join_real(first_amplitude, second_amplitude)
        step = flint.acb(
            _join_real(first_step.real, second_step.real),
            _join_real(first_step.imag, second_step.imag),
        )
        amp_lo = _downward_binary64(
            _exact_arb_endpoint(amplitude, lower=True)
        )
        amp_hi = _upward_binary64(
            _exact_arb_endpoint(amplitude, lower=False)
        )
        return amp_lo, amp_hi, *_binary64_box(step)


def _replayed_seed(flint: Any, x: int, precision_bits: int) -> tuple[Any, Any]:
    """Use exp(-log(x)/2) and one complex exponential for replay."""

    with flint.ctx.workprec(precision_bits):
        logarithm = flint.arb(x).log()
        amplitude = (-logarithm / 2).exp()
        exponent = flint.acb(
            0,
            -flint.arb(SOURCE_STEP_NUMERATOR) * logarithm
            / SOURCE_STEP_DENOMINATOR,
        )
        return amplitude, exponent.exp()


def _seed_contains(record: tuple[float, ...], amplitude: Any, step: Any) -> bool:
    amp_lo, amp_hi, *step_box = record
    if not (
        math.isfinite(amp_lo)
        and math.isfinite(amp_hi)
        and 0 < amp_lo <= amp_hi <= 1
    ):
        return False
    lower = _exact_arb_endpoint(amplitude, lower=True)
    upper = _exact_arb_endpoint(amplitude, lower=False)
    return (
        Fraction.from_float(amp_lo) <= lower
        and Fraction.from_float(amp_hi) >= upper
        and _contains_arb(tuple(step_box), step)
    )


def _chunk_hash(first_x: int, count: int, payload: bytes) -> bytes:
    digest = hashlib.sha256()
    digest.update(CHUNK_DOMAIN)
    digest.update(struct.pack("<QQ", first_x, count))
    digest.update(payload)
    return digest.digest()


@dataclass(frozen=True)
class SeedHeader:
    m: int
    maximum_q: int
    x_start: int
    x_stop: int
    record_count: int
    generation_precision_bits: int
    union_precision_bits: int
    chunk_records: int

    @property
    def full_source(self) -> bool:
        return (
            self.m == SOURCE_M
            and self.maximum_q == SOURCE_MAX_Q
            and self.x_start == SOURCE_X_START
            and self.x_stop == SOURCE_X_STOP
        )


def _unpack_header(raw: bytes) -> SeedHeader:
    if len(raw) != HEADER.size:
        _fail("short recovery-seed header")
    (
        magic,
        version,
        m,
        maximum_q,
        record_size,
        x_start,
        x_stop,
        step_numerator,
        step_denominator,
        record_count,
        generation_precision,
        union_precision,
        chunk_records,
        reserved0,
        reserved1,
    ) = HEADER.unpack(raw)
    if (
        magic != HEADER_MAGIC
        or version != FORMAT_VERSION
        or m != SOURCE_M
        or maximum_q != SOURCE_MAX_Q
        or record_size != SEED_RECORD.size
        or x_start != SOURCE_X_START
        or not x_start <= x_stop <= SOURCE_X_STOP
        or step_numerator != SOURCE_STEP_NUMERATOR
        or step_denominator != SOURCE_STEP_DENOMINATOR
        or record_count != x_stop - x_start + 1
        or generation_precision < 128
        or union_precision != generation_precision + DEFAULT_REPLAY_GUARD_BITS
        or not 1 <= chunk_records <= MAXIMUM_CHUNK_RECORDS
        or reserved0
        or reserved1
    ):
        _fail("recovery-seed header or exact source geometry differs")
    return SeedHeader(
        m=m,
        maximum_q=maximum_q,
        x_start=x_start,
        x_stop=x_stop,
        record_count=record_count,
        generation_precision_bits=generation_precision,
        union_precision_bits=union_precision,
        chunk_records=chunk_records,
    )


def iter_authenticated_seed_chunks(
    path: Path,
    *,
    expected_sha256: str | None = None,
    authenticated_identity: dict[str, str] | None = None,
) -> Iterator[tuple[int, bytes]]:
    """Yield chunks after authentication and optionally return footer identity.

    ``authenticated_identity`` is populated only after the generator is fully
    exhausted and the footer has authenticated.  Callers must therefore not
    treat an empty mapping as success.
    """

    if path.is_symlink() or not path.is_file():
        _fail("seed artifact is missing or is not a regular file")
    size = path.stat().st_size
    if not HEADER.size + CHUNK_HEADER.size + SEED_RECORD.size + FOOTER.size <= size:
        _fail("seed artifact is too short")
    if size > MAXIMUM_ARTIFACT_BYTES:
        _fail("seed artifact exceeds the fixed full-source size bound")
    if expected_sha256 is not None:
        actual, _ = sha256_file(path)
        if actual != expected_sha256:
            _fail("seed artifact SHA-256 differs before parsing")

    with path.open("rb") as source:
        header_raw = source.read(HEADER.size)
        header = _unpack_header(header_raw)
        records_digest = hashlib.sha256()
        root_digest = hashlib.sha256(ROOT_DOMAIN)
        remaining = header.record_count
        expected_x = header.x_start
        chunk_count = 0
        while remaining:
            raw_chunk_header = source.read(CHUNK_HEADER.size)
            if len(raw_chunk_header) != CHUNK_HEADER.size:
                _fail("short recovery-seed chunk header")
            magic, version, reserved, first_x, count, claimed = CHUNK_HEADER.unpack(
                raw_chunk_header
            )
            expected_count = min(header.chunk_records, remaining)
            if (
                magic != CHUNK_MAGIC
                or version != FORMAT_VERSION
                or reserved
                or first_x != expected_x
                or count != expected_count
            ):
                _fail("recovery-seed chunk ordering or size differs")
            payload = source.read(count * SEED_RECORD.size)
            if len(payload) != count * SEED_RECORD.size:
                _fail("short recovery-seed chunk payload")
            actual = _chunk_hash(first_x, count, payload)
            if actual != claimed:
                _fail("recovery-seed chunk SHA-256 differs")
            records_digest.update(payload)
            root_digest.update(actual)
            yield first_x, payload
            expected_x += count
            remaining -= count
            chunk_count += 1

        raw_footer = source.read(FOOTER.size)
        if len(raw_footer) != FOOTER.size or source.read(1):
            _fail("recovery-seed footer is missing or has trailing bytes")
        (
            magic,
            version,
            reserved,
            footer_count,
            footer_chunks,
            footer_records_sha,
            footer_root_sha,
        ) = FOOTER.unpack(raw_footer)
        if (
            magic != FOOTER_MAGIC
            or version != FORMAT_VERSION
            or reserved
            or footer_count != header.record_count
            or footer_chunks != chunk_count
            or footer_records_sha != records_digest.digest()
            or footer_root_sha != root_digest.digest()
        ):
            _fail("recovery-seed footer or global digest differs")
        if authenticated_identity is not None:
            authenticated_identity.update(
                {
                    "records_sha256": records_digest.hexdigest(),
                    "chunk_root_sha256": root_digest.hexdigest(),
                }
            )


def read_seed_header(path: Path) -> SeedHeader:
    if path.is_symlink() or not path.is_file():
        _fail("seed artifact is missing or is not a regular file")
    with path.open("rb") as source:
        return read_seed_header_bytes(source.read(HEADER.size))


def read_seed_header_bytes(raw: bytes) -> SeedHeader:
    """Validate an already authenticated TGDRCVS1 header byte string."""

    return _unpack_header(raw)


def generate_seed_artifact(
    artifact_path: Path,
    manifest_path: Path,
    *,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    chunk_records: int = DEFAULT_CHUNK_RECORDS,
    sample_x_stop: int | None = None,
) -> dict[str, Any]:
    """Generate one immutable full table or explicitly classified prefix KAT."""

    if precision_bits < 128:
        _fail("generation precision must be at least 128 bits")
    if not 1 <= chunk_records <= MAXIMUM_CHUNK_RECORDS:
        _fail("chunk_records is outside the fixed bound")
    x_stop = SOURCE_X_STOP if sample_x_stop is None else sample_x_stop
    if not SOURCE_X_START <= x_stop <= SOURCE_X_STOP:
        _fail("sample_x_stop is outside the source seed range")
    if artifact_path.exists() or manifest_path.exists():
        _fail("refusing to replace an immutable seed artifact or manifest")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    record_count = x_stop - SOURCE_X_START + 1
    header_raw = HEADER.pack(
        HEADER_MAGIC,
        FORMAT_VERSION,
        SOURCE_M,
        SOURCE_MAX_Q,
        SEED_RECORD.size,
        SOURCE_X_START,
        x_stop,
        SOURCE_STEP_NUMERATOR,
        SOURCE_STEP_DENOMINATOR,
        record_count,
        precision_bits,
        precision_bits + DEFAULT_REPLAY_GUARD_BITS,
        chunk_records,
        0,
        0,
    )
    flint = _load_flint()
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{artifact_path.name}.", dir=artifact_path.parent
    )
    temporary = Path(temporary_name)
    started = time.perf_counter()
    chunk_count = 0
    records_digest = hashlib.sha256()
    root_digest = hashlib.sha256(ROOT_DOMAIN)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(header_raw)
            first_x = SOURCE_X_START
            while first_x <= x_stop:
                count = min(chunk_records, x_stop - first_x + 1)
                payload = bytearray(count * SEED_RECORD.size)
                for offset in range(count):
                    record = _generated_seed(flint, first_x + offset, precision_bits)
                    SEED_RECORD.pack_into(payload, offset * SEED_RECORD.size, *record)
                payload_bytes = bytes(payload)
                digest = _chunk_hash(first_x, count, payload_bytes)
                output.write(
                    CHUNK_HEADER.pack(
                        CHUNK_MAGIC,
                        FORMAT_VERSION,
                        0,
                        first_x,
                        count,
                        digest,
                    )
                )
                output.write(payload_bytes)
                records_digest.update(payload_bytes)
                root_digest.update(digest)
                first_x += count
                chunk_count += 1
            output.write(
                FOOTER.pack(
                    FOOTER_MAGIC,
                    FORMAT_VERSION,
                    0,
                    record_count,
                    chunk_count,
                    records_digest.digest(),
                    root_digest.digest(),
                )
            )
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, artifact_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        flint.ctx.threads = old_threads

    artifact_sha, artifact_size = sha256_file(artifact_path)
    full_source = x_stop == SOURCE_X_STOP
    manifest: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "checker_id": CHECKER_ID,
        "classification": (
            "full_source_recovery_seed_table_not_theorem_7_1"
            if full_source
            else "bounded_prefix_recovery_seed_kat_only"
        ),
        "kind": MANIFEST_SCHEMA,
        "schema_version": 1,
        "source": {
            "url": SOURCE_URL,
            "identity": "(q*n+a)^(-1/2-i*5*j/64) = (q*n+a)^(-1/2) * exp(-i*5*log(q*n+a)/64)^j",
        },
        "geometry": {
            "M": SOURCE_M,
            "maximum_q": SOURCE_MAX_Q,
            "x_start": SOURCE_X_START,
            "x_stop": x_stop,
            "record_count": record_count,
            "t_step_numerator": SOURCE_STEP_NUMERATOR,
            "t_denominator": SOURCE_STEP_DENOMINATOR,
            "full_source_seed_range": full_source,
        },
        "format": {
            "header_magic": HEADER_MAGIC.decode("ascii"),
            "chunk_magic": CHUNK_MAGIC.decode("ascii"),
            "footer_magic": FOOTER_MAGIC.decode("ascii"),
            "record_bytes": SEED_RECORD.size,
            "chunk_records": chunk_records,
            "chunk_count": chunk_count,
            "chunk_authentication_before_yield": True,
        },
        "artifact": {
            "sha256": artifact_sha,
            "size_bytes": artifact_size,
            "records_sha256": records_digest.hexdigest(),
            "chunk_root_sha256": root_digest.hexdigest(),
        },
        "generation": {
            "precision_bits": precision_bits,
            "second_precision_bits": precision_bits
            + DEFAULT_REPLAY_GUARD_BITS,
            "runtime": runtime_identity(flint),
            "producer_module": _file_record(Path(__file__).resolve()),
            "arb_threads": 1,
            "device_transcendental_calls_required": 0,
        },
        "decisions": {
            "outward_binary64_amplitude_intervals": True,
            "outward_binary64_phase_step_rectangles": True,
            "all_records_higher_precision_replayed": False,
            "gpu_recurrence_executed": False,
            "recurrence_widths_proved_sufficient_for_zero_isolation": False,
            "external_atom_discharged": False,
        },
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json_bytes(manifest))
    _atomic_bytes(manifest_path, canonical_json_bytes(manifest))
    elapsed = time.perf_counter() - started
    return {
        "manifest": manifest,
        "benchmark": {
            "elapsed_seconds": elapsed,
            "records_per_second": record_count / elapsed,
            "classification": "measured_generation_not_full_verification_eta",
        },
    }


def verify_seed_artifact(
    artifact_path: Path,
    manifest_path: Path,
    *,
    replay_precision_bits: int = DEFAULT_REPLAY_PRECISION_BITS,
) -> dict[str, Any]:
    """Authenticate and replay every amplitude/phase rectangle."""

    manifest = _canonical_manifest(manifest_path)
    if set(manifest) != {
        "algorithm_id",
        "artifact",
        "atom_id",
        "author",
        "checker_id",
        "classification",
        "decisions",
        "format",
        "generation",
        "geometry",
        "kind",
        "manifest_sha256",
        "schema_version",
        "source",
    } or (
        manifest.get("kind") != MANIFEST_SCHEMA
        or manifest.get("schema_version") != 1
        or manifest.get("algorithm_id") != ALGORITHM_ID
        or manifest.get("checker_id") != CHECKER_ID
        or manifest.get("atom_id") != ATOM_ID
        or manifest.get("author") != AUTHOR
    ):
        _fail("seed manifest identity differs")
    artifact = manifest.get("artifact")
    geometry = manifest.get("geometry")
    generation = manifest.get("generation")
    decisions = manifest.get("decisions")
    format_record = manifest.get("format")
    source_record = manifest.get("source")
    if not all(
        isinstance(item, dict)
        for item in (
            artifact,
            geometry,
            generation,
            decisions,
            format_record,
            source_record,
        )
    ):
        _fail("seed manifest records are malformed")
    assert isinstance(artifact, dict)
    assert isinstance(geometry, dict)
    assert isinstance(generation, dict)
    assert isinstance(decisions, dict)
    assert isinstance(format_record, dict)
    assert isinstance(source_record, dict)
    actual_sha, actual_size = sha256_file(artifact_path)
    if (
        artifact.get("sha256") != actual_sha
        or artifact.get("size_bytes") != actual_size
    ):
        _fail("seed artifact hash or size differs from the manifest")
    header = read_seed_header(artifact_path)
    expected_classification = (
        "full_source_recovery_seed_table_not_theorem_7_1"
        if header.full_source
        else "bounded_prefix_recovery_seed_kat_only"
    )
    chunk_count = (
        header.record_count + header.chunk_records - 1
    ) // header.chunk_records
    expected_size = (
        HEADER.size
        + chunk_count * CHUNK_HEADER.size
        + header.record_count * SEED_RECORD.size
        + FOOTER.size
    )
    if (
        manifest.get("classification") != expected_classification
        or source_record
        != {
            "url": SOURCE_URL,
            "identity": "(q*n+a)^(-1/2-i*5*j/64) = (q*n+a)^(-1/2) * exp(-i*5*log(q*n+a)/64)^j",
        }
        or geometry.get("M") != header.m
        or geometry.get("maximum_q") != header.maximum_q
        or geometry.get("x_start") != header.x_start
        or geometry.get("x_stop") != header.x_stop
        or geometry.get("record_count") != header.record_count
        or geometry.get("t_step_numerator") != SOURCE_STEP_NUMERATOR
        or geometry.get("t_denominator") != SOURCE_STEP_DENOMINATOR
        or geometry.get("full_source_seed_range") is not header.full_source
        or generation.get("precision_bits") != header.generation_precision_bits
        or generation.get("second_precision_bits") != header.union_precision_bits
        or actual_size != expected_size
    ):
        _fail("seed manifest and binary source geometry differ")
    if format_record != {
        "header_magic": HEADER_MAGIC.decode("ascii"),
        "chunk_magic": CHUNK_MAGIC.decode("ascii"),
        "footer_magic": FOOTER_MAGIC.decode("ascii"),
        "record_bytes": SEED_RECORD.size,
        "chunk_records": header.chunk_records,
        "chunk_count": chunk_count,
        "chunk_authentication_before_yield": True,
    }:
        _fail("seed manifest format record differs")
    if set(artifact) != {
        "sha256",
        "size_bytes",
        "records_sha256",
        "chunk_root_sha256",
    }:
        _fail("seed artifact manifest fields differ")
    _lower_hex_digest(artifact.get("records_sha256"), "record stream digest")
    _lower_hex_digest(artifact.get("chunk_root_sha256"), "chunk root digest")
    if set(generation) != {
        "precision_bits",
        "second_precision_bits",
        "runtime",
        "producer_module",
        "arb_threads",
        "device_transcendental_calls_required",
    } or (
        generation.get("arb_threads") != 1
        or generation.get("device_transcendental_calls_required") != 0
        or generation.get("producer_module")
        != _file_record(Path(__file__).resolve())
    ):
        _fail("seed generator identity differs")
    try:
        _validate_runtime_record(generation.get("runtime"), "generation.runtime")
    except RuntimeError as error:
        raise DirichletRecoverySeedError("seed generator runtime is invalid") from error
    if decisions != {
        "outward_binary64_amplitude_intervals": True,
        "outward_binary64_phase_step_rectangles": True,
        "all_records_higher_precision_replayed": False,
        "gpu_recurrence_executed": False,
        "recurrence_widths_proved_sufficient_for_zero_isolation": False,
        "external_atom_discharged": False,
    }:
        _fail("seed manifest decision boundary differs")
    if replay_precision_bits < header.union_precision_bits + DEFAULT_REPLAY_GUARD_BITS:
        _fail("replay precision must be at least union precision + 64 bits")

    flint = _load_flint()
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    replayed = 0
    authenticated_identity: dict[str, str] = {}
    started = time.perf_counter()
    try:
        for first_x, payload in iter_authenticated_seed_chunks(
            artifact_path,
            expected_sha256=actual_sha,
            authenticated_identity=authenticated_identity,
        ):
            count = len(payload) // SEED_RECORD.size
            for offset in range(count):
                record = SEED_RECORD.unpack_from(payload, offset * SEED_RECORD.size)
                amplitude, step = _replayed_seed(
                    flint, first_x + offset, replay_precision_bits
                )
                if not _seed_contains(record, amplitude, step):
                    _fail(f"seed replay containment failed at x={first_x + offset}")
                replayed += 1
    finally:
        flint.ctx.threads = old_threads
    if replayed != header.record_count:
        _fail("seed replay record count differs")
    if authenticated_identity != {
        "records_sha256": artifact["records_sha256"],
        "chunk_root_sha256": artifact["chunk_root_sha256"],
    }:
        _fail("seed manifest stream digests differ from the authenticated footer")
    elapsed = time.perf_counter() - started
    report: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "artifact_sha256": actual_sha,
        "atom_id": ATOM_ID,
        "checker_id": CHECKER_ID,
        "classification": "complete_seed_containment_replay_not_theorem_7_1",
        "external_atom_discharged": False,
        "full_source_seed_range": header.full_source,
        "higher_precision_arb_containment_passed": True,
        "kind": REPLAY_SCHEMA,
        "manifest_sha256": manifest["manifest_sha256"],
        "record_count": replayed,
        "replay_precision_bits": replay_precision_bits,
        "replay_runtime": runtime_identity(flint),
        "schema_version": 1,
    }
    report["replay_sha256"] = sha256_bytes(canonical_json_bytes(report))
    return {
        "replay": report,
        "benchmark": {
            "elapsed_seconds": elapsed,
            "records_per_second": replayed / elapsed,
            "classification": "measured_full_containment_replay_rate",
        },
    }


RealInterval = tuple[float, float]
ComplexInterval = tuple[RealInterval, RealInterval]


def _add(x: RealInterval, y: RealInterval) -> RealInterval:
    return (
        math.nextafter(x[0] + y[0], -math.inf),
        math.nextafter(x[1] + y[1], math.inf),
    )


def _sub(x: RealInterval, y: RealInterval) -> RealInterval:
    return (
        math.nextafter(x[0] - y[1], -math.inf),
        math.nextafter(x[1] - y[0], math.inf),
    )


def _mul(x: RealInterval, y: RealInterval) -> RealInterval:
    products = (x[0] * y[0], x[0] * y[1], x[1] * y[0], x[1] * y[1])
    return (
        math.nextafter(min(products), -math.inf),
        math.nextafter(max(products), math.inf),
    )


def _cmul(x: ComplexInterval, y: ComplexInterval) -> ComplexInterval:
    return _sub(_mul(x[0], y[0]), _mul(x[1], y[1])), _add(
        _mul(x[0], y[1]), _mul(x[1], y[0])
    )


def _cadd(x: ComplexInterval, y: ComplexInterval) -> ComplexInterval:
    return _add(x[0], y[0]), _add(x[1], y[1])


def interval_complex_power(base: ComplexInterval, exponent: int) -> ComplexInterval:
    """Directed binary64 exponentiation used by the CUDA recurrence design."""

    if exponent < 0:
        _fail("recurrence exponent must be nonnegative")
    answer: ComplexInterval = ((1.0, 1.0), (0.0, 0.0))
    current = base
    while exponent:
        if exponent & 1:
            answer = _cmul(answer, current)
        exponent >>= 1
        if exponent:
            current = _cmul(current, current)
    return answer


def recovery_term_from_seed(record: tuple[float, ...], t_index: int) -> ComplexInterval:
    if len(record) != 6 or t_index < 0:
        _fail("malformed seed record or t index")
    amplitude = (record[0], record[1])
    phase: ComplexInterval = ((record[2], record[3]), (record[4], record[5]))
    power = interval_complex_power(phase, t_index)
    return _mul(power[0], amplitude), _mul(power[1], amplitude)


def recovery_box_from_seed_lookup(
    q: int,
    a: int,
    t_index: int,
    lookup: Mapping[int, tuple[float, ...]],
) -> ComplexInterval:
    """Enclose ``sum_(n=0)^4 (q*n+a)^(-1/2-i*5*j/64)``."""

    if not 10_001 <= q <= SOURCE_MAX_Q or not 1 <= a < q or math.gcd(a, q) != 1:
        _fail("recovery request is outside the large-q unit-residue geometry")
    if t_index < 0:
        _fail("recovery t index must be nonnegative")
    result: ComplexInterval = ((0.0, 0.0), (0.0, 0.0))
    for n in range(SOURCE_M + 1):
        x = q * n + a
        try:
            record = lookup[x]
        except KeyError as error:
            raise DirichletRecoverySeedError(f"missing recurrence seed x={x}") from error
        result = _cadd(result, recovery_term_from_seed(record, t_index))
    return result


def _sample_indices(total: int, maximum_values: int | None) -> range | list[int]:
    if maximum_values is None or maximum_values >= total:
        return range(total)
    if maximum_values <= 0:
        _fail("maximum_values must be positive when supplied")
    if maximum_values == 1:
        return [0]
    # Deterministic endpoints plus evenly spaced interior values.  This is an
    # explicitly labelled KAT sample; it is never promoted to full replay.
    return sorted(
        {
            index * (total - 1) // (maximum_values - 1)
            for index in range(maximum_values)
        }
    )


def _lower_hex_digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not lowercase SHA-256")
    return value


def convert_largeq_v1_to_seeded_v2(
    source_path: Path,
    output_path: Path,
    *,
    expected_source_sha256: str,
    seed_artifact_sha256: str,
    seed_replay_sha256: str,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Remove repeated recovery boxes from one authenticated ``TGDLQBI1``.

    The resulting ``TGDLQB2`` carries one Taylor radius per ordinate.  Its
    fused CUDA consumer reconstructs the discarded finite recovery directly
    from the separately authenticated recurrence seeds.  This conversion is
    structural: the source's lattice/certificate semantics remain upstream.
    """

    from tg_verifier.dirichlet_allchars_stage import (
        canonical_component_orders,
        canonical_residue_order,
    )
    from tg_verifier.dirichlet_largeq_batch import (
        CERTIFIED_RESIDUE_BOX,
        FRAME_FACTOR,
        INPUT_HEADER,
        INPUT_MAGIC,
        RESIDUE_DESCRIPTOR,
    )
    from tg_verifier.dirichlet_lattice_stage import (
        LATTICE_CELL,
        LATTICE_ROWS,
        TAYLOR_COLUMNS,
        TAYLOR_DEGREE,
        canonical_lattice_row,
        maximum_t_index,
    )

    expected_source_sha256 = _lower_hex_digest(
        expected_source_sha256, "source input digest"
    )
    seed_artifact_sha256 = _lower_hex_digest(
        seed_artifact_sha256, "seed artifact digest"
    )
    seed_replay_sha256 = _lower_hex_digest(seed_replay_sha256, "seed replay digest")
    if source_path.is_symlink() or not source_path.is_file():
        _fail("source TGDLQBI1 is missing or is not a regular file")
    source_sha, source_size = sha256_file(source_path)
    if source_sha != expected_source_sha256:
        _fail("source TGDLQBI1 SHA-256 differs before conversion")
    if output_path.exists() or (receipt_path is not None and receipt_path.exists()):
        _fail("refusing to replace immutable seeded output or receipt")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", dir=output_path.parent
    )
    temporary = Path(temporary_name)
    output_digest = hashlib.sha256()
    output_size = 0

    def emit(destination: BinaryIO, raw: bytes) -> None:
        nonlocal output_size
        destination.write(raw)
        output_digest.update(raw)
        output_size += len(raw)

    try:
        with source_path.open("rb") as source, os.fdopen(descriptor, "wb") as output:
            raw_header = source.read(INPUT_HEADER.size)
            if len(raw_header) != INPUT_HEADER.size:
                _fail("short source TGDLQBI1 header")
            fields = list(INPUT_HEADER.unpack(raw_header))
            (
                magic,
                version,
                q,
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
            ) = fields
            orders = canonical_component_orders(q) if 10_001 <= q <= SOURCE_MAX_Q else []
            residues = canonical_residue_order(q) if orders else []
            if (
                magic != INPUT_MAGIC
                or version != 1
                or rows != LATTICE_ROWS
                or degree != TAYLOR_DEGREE
                or component_count != len(orders)
                or not 1 <= batch_count <= 64
                or m != SOURCE_M
                or reserved0
                or reserved1
                or group_order != len(residues)
                or first_t_numerator < 0
                or first_t_numerator % SOURCE_STEP_NUMERATOR
                or denominator != SOURCE_STEP_DENOMINATOR
                or step_numerator != SOURCE_STEP_NUMERATOR
                or lattice_count != batch_count * LATTICE_ROWS * TAYLOR_COLUMNS
                or value_count != batch_count * group_order
                or first_t_numerator // SOURCE_STEP_NUMERATOR + batch_count - 1
                > maximum_t_index(q)
            ):
                _fail("source TGDLQBI1 geometry differs from the seeded contract")
            expected_source_size = (
                INPUT_HEADER.size
                + group_order * RESIDUE_DESCRIPTOR.size
                + batch_count * FRAME_FACTOR.size
                + lattice_count * LATTICE_CELL.size
                + value_count * CERTIFIED_RESIDUE_BOX.size
            )
            if source_size != expected_source_size:
                _fail("source TGDLQBI1 exact length differs")
            fields[0] = SEEDED_BATCH_MAGIC
            fields[1] = 2
            emit(output, SEEDED_BATCH_HEADER.pack(*fields))

            descriptor_bytes = source.read(group_order * RESIDUE_DESCRIPTOR.size)
            if len(descriptor_bytes) != group_order * RESIDUE_DESCRIPTOR.size:
                _fail("short source descriptor table")
            for index, a in enumerate(residues):
                if RESIDUE_DESCRIPTOR.unpack_from(
                    descriptor_bytes, index * RESIDUE_DESCRIPTOR.size
                ) != (a, canonical_lattice_row(q, a)):
                    _fail("source descriptor table is not canonical CRT order")
            emit(output, descriptor_bytes)

            factor_bytes = source.read(batch_count * FRAME_FACTOR.size)
            if len(factor_bytes) != batch_count * FRAME_FACTOR.size:
                _fail("short source factor table")
            for offset in range(0, len(factor_bytes), FRAME_FACTOR.size):
                box = FRAME_FACTOR.unpack_from(factor_bytes, offset)
                if (
                    not all(math.isfinite(value) for value in box)
                    or box[0] > box[1]
                    or box[2] > box[3]
                ):
                    _fail("source q^(-s) factor is malformed")
            emit(output, factor_bytes)

            lattice_remaining = lattice_count
            while lattice_remaining:
                count = min(lattice_remaining, 4096)
                raw = source.read(count * LATTICE_CELL.size)
                if len(raw) != count * LATTICE_CELL.size:
                    _fail("short source lattice payload")
                for offset in range(0, len(raw), LATTICE_CELL.size):
                    box = LATTICE_CELL.unpack_from(raw, offset)
                    if (
                        not all(math.isfinite(value) for value in box)
                        or box[0] > box[1]
                        or box[2] > box[3]
                    ):
                        _fail("source lattice payload contains a malformed box")
                emit(output, raw)
                lattice_remaining -= count

            tail_words: list[bytes | None] = [None] * batch_count
            values_remaining = value_count
            flat = 0
            while values_remaining:
                count = min(values_remaining, 4096)
                raw = source.read(count * CERTIFIED_RESIDUE_BOX.size)
                if len(raw) != count * CERTIFIED_RESIDUE_BOX.size:
                    _fail("short source certified-box payload")
                for offset in range(0, len(raw), CERTIFIED_RESIDUE_BOX.size):
                    radius, re_lo, re_hi, im_lo, im_hi = (
                        CERTIFIED_RESIDUE_BOX.unpack_from(raw, offset)
                    )
                    if (
                        not math.isfinite(radius)
                        or radius < 0
                        or not all(
                            math.isfinite(value)
                            for value in (re_lo, re_hi, im_lo, im_hi)
                        )
                        or re_lo > re_hi
                        or im_lo > im_hi
                    ):
                        _fail("source certified recovery box is malformed")
                    frame = flat // group_order
                    radius_word = struct.pack("<d", radius)
                    if tail_words[frame] is None:
                        tail_words[frame] = radius_word
                    elif tail_words[frame] != radius_word:
                        _fail("Taylor tail radius is not uniform within one frame")
                    flat += 1
                values_remaining -= count
            if source.read(1):
                _fail("source TGDLQBI1 has trailing bytes")
            if any(word is None for word in tail_words):
                _fail("a seeded batch frame has no Taylor radius")
            for word in tail_words:
                assert word is not None
                emit(output, word)
            output.flush()
            os.fsync(output.fileno())
        post_sha, post_size = sha256_file(source_path)
        if post_sha != source_sha or post_size != source_size:
            _fail("source TGDLQBI1 changed during conversion")
        os.replace(temporary, output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    receipt: dict[str, Any] = {
        "algorithm_id": "platt-dirichlet-largeq-seeded-input-conversion-v1",
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": "compact_seeded_cuda_input_not_theorem_7_1",
        "source_input": {"sha256": source_sha, "size_bytes": source_size},
        "seed_artifact_sha256": seed_artifact_sha256,
        "seed_replay_sha256": seed_replay_sha256,
        "q": q,
        "M": m,
        "first_t_numerator": first_t_numerator,
        "t_denominator": denominator,
        "t_step_numerator": step_numerator,
        "batch_count": batch_count,
        "group_order": group_order,
        "value_count": value_count,
        "output": {
            "magic": SEEDED_BATCH_MAGIC.decode("ascii"),
            "sha256": output_digest.hexdigest(),
            "size_bytes": output_size,
        },
        "logical_recovery_rectangles_removed": value_count,
        "logical_recovery_bytes_removed": value_count * 32,
        "logical_repeated_tail_bytes_removed": value_count * 8
        - batch_count * 8,
        "decisions": {
            "source_hash_verified_before_and_after": True,
            "all_discarded_recovery_boxes_structurally_validated": True,
            "uniform_per_frame_tail_radius_verified": True,
            "finite_recovery_replaced_by_authenticated_seed_identity": True,
            "zero_isolation_or_turing_completed": False,
            "external_atom_discharged": False,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    if receipt_path is not None:
        _atomic_bytes(receipt_path, canonical_json_bytes(receipt))
    return receipt


def verify_cuda_output(
    artifact_path: Path,
    expected_artifact_sha256: str,
    output_path: Path,
    *,
    maximum_values: int | None = None,
    arb_precision_bits: int = 384,
) -> dict[str, Any]:
    """Replay a complete GPU frame or an explicitly labelled deterministic KAT.

    The CPU recurrence is a conservative binary64 replay.  A separately
    structured direct Arb power sum must also lie in every selected GPU box.
    Supplying ``maximum_values`` makes this only a KAT sample; omitting it
    checks every output in the finite frame, not the whole source campaign.
    """

    if arb_precision_bits < 320:
        _fail("CUDA output Arb replay precision must be at least 320 bits")
    if output_path.is_symlink() or not output_path.is_file():
        _fail("CUDA recovery output is missing or is not a regular file")
    output_size = output_path.stat().st_size
    if output_size < OUTPUT_HEADER.size + OUTPUT_RECORD.size:
        _fail("CUDA recovery output is too short")
    with output_path.open("rb") as output:
        raw_header = output.read(OUTPUT_HEADER.size)
        if len(raw_header) != OUTPUT_HEADER.size:
            _fail("short CUDA recovery output header")
        (
            magic,
            version,
            q,
            m,
            batch_count,
            group_order,
            first_t_index,
            step_numerator,
            denominator,
            value_count,
            reserved,
        ) = OUTPUT_HEADER.unpack(raw_header)
        units = [a for a in range(1, q) if math.gcd(a, q) == 1]
        if (
            magic != OUTPUT_MAGIC
            or version != FORMAT_VERSION
            or not 10_001 <= q <= SOURCE_MAX_Q
            or m != SOURCE_M
            or not 1 <= batch_count <= 64
            or group_order != len(units)
            or step_numerator != SOURCE_STEP_NUMERATOR
            or denominator != SOURCE_STEP_DENOMINATOR
            or value_count != batch_count * group_order
            or reserved
            or output_size != OUTPUT_HEADER.size + value_count * OUTPUT_RECORD.size
        ):
            _fail("CUDA recovery output geometry differs")
        selected = _sample_indices(value_count, maximum_values)
        raw_boxes: dict[int, tuple[float, float, float, float]] = {}
        for index in selected:
            output.seek(OUTPUT_HEADER.size + index * OUTPUT_RECORD.size)
            raw = output.read(OUTPUT_RECORD.size)
            if len(raw) != OUTPUT_RECORD.size:
                _fail("short selected CUDA recovery record")
            box = OUTPUT_RECORD.unpack(raw)
            if (
                not all(math.isfinite(value) for value in box)
                or box[0] > box[1]
                or box[2] > box[3]
            ):
                _fail("CUDA recovery output contains a malformed interval")
            raw_boxes[index] = box

    needed: set[int] = set()
    for index in selected:
        a = units[index % group_order]
        needed.update(q * n + a for n in range(SOURCE_M + 1))
    lookup: dict[int, tuple[float, ...]] = {}
    for first_x, payload in iter_authenticated_seed_chunks(
        artifact_path, expected_sha256=expected_artifact_sha256
    ):
        count = len(payload) // SEED_RECORD.size
        for offset in range(count):
            x = first_x + offset
            if x in needed:
                lookup[x] = SEED_RECORD.unpack_from(
                    payload, offset * SEED_RECORD.size
                )
    if len(lookup) != len(needed):
        _fail("authenticated seed artifact does not cover the CUDA output")

    flint = _load_flint()
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    maximum_width = 0.0
    started = time.perf_counter()
    try:
        with flint.ctx.workprec(arb_precision_bits):
            for index in selected:
                frame = index // group_order
                a = units[index % group_order]
                t_index = first_t_index + frame
                gpu = raw_boxes[index]
                cpu = recovery_box_from_seed_lookup(q, a, t_index, lookup)
                if not (
                    cpu[0][0] <= gpu[0]
                    and gpu[1] <= cpu[0][1]
                    and cpu[1][0] <= gpu[2]
                    and gpu[3] <= cpu[1][1]
                ):
                    _fail(f"CUDA directed result differs from CPU recurrence at {index}")
                s = flint.acb(
                    flint.arb(1) / 2,
                    flint.arb(SOURCE_STEP_NUMERATOR * t_index)
                    / SOURCE_STEP_DENOMINATOR,
                )
                direct = flint.acb(0)
                for n in range(SOURCE_M + 1):
                    direct += flint.acb(q * n + a) ** (-s)
                if not _contains_arb(gpu, direct):
                    _fail(f"CUDA recovery interval misses direct Arb value at {index}")
                maximum_width = max(
                    maximum_width, gpu[1] - gpu[0], gpu[3] - gpu[2]
                )
    finally:
        flint.ctx.threads = old_threads
    elapsed = time.perf_counter() - started
    complete = len(selected) == value_count
    output_sha, _ = sha256_file(output_path)
    return {
        "algorithm_id": ALGORITHM_ID,
        "artifact_sha256": expected_artifact_sha256,
        "classification": (
            "complete_finite_cuda_frame_replay_not_source_campaign"
            if complete
            else "deterministic_cuda_output_kat_sample_only"
        ),
        "cuda_output_sha256": output_sha,
        "q": q,
        "first_t_index": first_t_index,
        "batch_count": batch_count,
        "value_count": value_count,
        "values_replayed": len(selected),
        "complete_frame_replayed": complete,
        "cpu_directed_recurrence_encloses_cuda": True,
        "direct_higher_precision_arb_values_contained": True,
        "maximum_sampled_component_width": maximum_width,
        "elapsed_seconds": elapsed,
        "values_per_second": len(selected) / elapsed,
        "recurrence_widths_proved_sufficient_for_zero_isolation": False,
        "external_atom_discharged": False,
    }


def benchmark_seed_recurrence(
    artifact_path: Path,
    *,
    q: int,
    t_index: int,
    residues: int = 1_024,
) -> dict[str, Any]:
    """Measure the reviewable CPU recurrence and report its enclosure widths."""

    if residues <= 0:
        _fail("benchmark residue count must be positive")
    needed: set[int] = set()
    selected: list[int] = []
    for a in range(1, q):
        if math.gcd(a, q) != 1:
            continue
        selected.append(a)
        needed.update(q * n + a for n in range(SOURCE_M + 1))
        if len(selected) == residues:
            break
    if len(selected) != residues:
        _fail("benchmark q has fewer unit residues than requested")
    lookup: dict[int, tuple[float, ...]] = {}
    for first_x, payload in iter_authenticated_seed_chunks(artifact_path):
        count = len(payload) // SEED_RECORD.size
        for offset in range(count):
            x = first_x + offset
            if x in needed:
                lookup[x] = SEED_RECORD.unpack_from(
                    payload, offset * SEED_RECORD.size
                )
        if len(lookup) == len(needed):
            break
    if len(lookup) != len(needed):
        _fail("seed artifact does not cover the benchmark requests")
    started = time.perf_counter()
    boxes = [recovery_box_from_seed_lookup(q, a, t_index, lookup) for a in selected]
    elapsed = time.perf_counter() - started
    widths = [
        max(box[0][1] - box[0][0], box[1][1] - box[1][0]) for box in boxes
    ]
    return {
        "algorithm_id": ALGORITHM_ID,
        "classification": "cpu_recurrence_microbenchmark_not_gpu_or_theorem_eta",
        "q": q,
        "t_index": t_index,
        "residue_count": residues,
        "elapsed_seconds": elapsed,
        "residues_per_second": residues / elapsed,
        "maximum_component_width": max(widths),
        "mean_max_component_width": sum(widths) / len(widths),
        "cuda_transcendental_calls_required": 0,
        "external_atom_discharged": False,
    }


def capability() -> dict[str, Any]:
    try:
        flint = _load_flint()
        runtime = runtime_identity(flint)
        available = True
        error = None
    except DirichletRecoverySeedError as exception:
        runtime = None
        available = False
        error = str(exception)
    source_rows = 4_901_051_274
    old_box_bytes = 13_083_568_251_320_320
    compact_tail_bytes = source_rows * 8
    old_total_bytes = 18_263_933_424_590_240
    seeded_total_bytes = old_total_bytes - old_box_bytes + compact_tail_bytes
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "classification": "certified_recovery_seed_component_not_theorem_7_1",
        "pinned_arb_available": available,
        "runtime": runtime,
        "error": error,
        "source_geometry": {
            "M": SOURCE_M,
            "maximum_q": SOURCE_MAX_Q,
            "x_range": [SOURCE_X_START, SOURCE_X_STOP],
            "record_count": SOURCE_X_STOP,
            "grid_step": [SOURCE_STEP_NUMERATOR, SOURCE_STEP_DENOMINATOR],
        },
        "full_artifact_payload_bytes": SOURCE_X_STOP * SEED_RECORD.size,
        "logical_per_value_recovery_bytes_replaced": 13_083_568_251_320_320,
        "chunk_authentication_before_yield": True,
        "higher_precision_full_replay_implemented": True,
        "cuda_transcendental_calls_required": 0,
        "standalone_seeded_cuda_expansion_implemented": True,
        "gpu_expansion_integrated_with_fused_largeq_kernel": True,
        "persistent_q_framed_service_implemented": True,
        "shared_cmake_target_integrated": False,
        "source_input_traffic": {
            "old_logical_bytes": old_total_bytes,
            "seeded_logical_bytes": seeded_total_bytes,
            "logical_bytes_removed": old_total_bytes - seeded_total_bytes,
            "old_per_value_tail_plus_recovery_bytes": old_box_bytes,
            "new_per_ordinate_tail_bytes": compact_tail_bytes,
            "t_major_cache_contract_implemented_elsewhere": True,
            "t_major_unique_lattice_payload_bytes": 134_205_145_088,
            "former_t_major_descriptor_repeated_input_bytes": (
                41_413_846_139_376
            ),
            "direct_t_major_cuda_input_bytes": 286_556_459_000,
            "direct_t_major_input_including_recovery_seeds": 339_564_685_336,
            "note": (
                "the direct TGDLTMB1 path has a one-upload CUDA component, "
                "but no populated, source-scale, downstream-FFT-integrated run"
            ),
        },
        "recurrence_widths_proved_sufficient_for_zero_isolation": False,
        "external_atom_discharged": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "CHUNK_HEADER",
    "DirichletRecoverySeedError",
    "FOOTER",
    "HEADER",
    "SEED_RECORD",
    "SOURCE_M",
    "SOURCE_X_STOP",
    "benchmark_seed_recurrence",
    "capability",
    "convert_largeq_v1_to_seeded_v2",
    "generate_seed_artifact",
    "interval_complex_power",
    "iter_authenticated_seed_chunks",
    "read_seed_header",
    "read_seed_header_bytes",
    "recovery_box_from_seed_lookup",
    "recovery_term_from_seed",
    "verify_seed_artifact",
    "verify_cuda_output",
]

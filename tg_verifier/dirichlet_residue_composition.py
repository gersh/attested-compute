# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Bounded composition of large-q Taylor and finite-recovery rectangles.

The Taylor executable returns ``zeta_M(s,a/q)`` rectangles.  The unit-group
transform instead needs

    q**(-s) * zeta_M(s,a/q) + R_M(s;q,a).

This module is the deliberately narrow adapter between those two stages.  A
production job must carry the certificate manifest and replay report which
bind ``M`` and the finite recovery to ``TGDLATI1``, plus the Taylor-stage
receipt which binds that input to ``TGDLATO1``.  Merely presenting two binary
files with matching row labels is not accepted as a certified job, because a
``TGDLATO1`` header contains neither ``t`` nor ``M``.

Only one modulus is admitted per job.  Each ordinate is read in ascending
residue order, composed with outward binary64 interval arithmetic, reordered
into the transform's canonical CRT order, and written before the next
ordinate is loaded.  Thus the live binary payload is O(phi(q)), independent
of the number of batches and of the full campaign size.

This closes only the residue-composition adapter.  It does not perform the
all-character transform, completed-L phase, zero isolation, Turing count, or
the full external atom.
"""

from __future__ import annotations

from array import array
import ctypes
import ctypes.util
from dataclasses import dataclass
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
from typing import Any, BinaryIO, NoReturn, Sequence

try:
    import numpy as _np
except ImportError:  # pragma: no cover - exercised by capability fallback
    _np = None

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    FORMAT_VERSION as ALLCHARS_FORMAT_VERSION,
    INPUT_HEADER as ALLCHARS_INPUT_HEADER,
    INPUT_MAGIC as ALLCHARS_INPUT_MAGIC,
    canonical_component_orders,
    canonical_residue_order,
)
import tg_verifier.dirichlet_lattice_certificates as _lattice_certificates
from tg_verifier.dirichlet_lattice_certificates import (
    DECISIONS as LATTICE_CERTIFICATE_DECISIONS,
    MANIFEST_SCHEMA as LATTICE_MANIFEST_SCHEMA,
    RECOVERY_FORMAT_VERSION,
    RECOVERY_HEADER,
    RECOVERY_ITEM,
    RECOVERY_MAGIC,
    REPLAY_SCHEMA as LATTICE_REPLAY_SCHEMA,
    REQUEST_ENUMERATION,
    _source_record as _lattice_source_record,
    _validate_runtime_record as _validate_lattice_runtime_record,
)
from tg_verifier.dirichlet_lattice_stage import (
    FORMAT_VERSION as LATTICE_FORMAT_VERSION,
    INPUT_HEADER as LATTICE_INPUT_HEADER,
    INPUT_ITEM as LATTICE_INPUT_ITEM,
    INPUT_MAGIC as LATTICE_INPUT_MAGIC,
    LATTICE_CELL,
    LATTICE_ROWS,
    OUTPUT_HEADER as LATTICE_OUTPUT_HEADER,
    OUTPUT_ITEM as LATTICE_OUTPUT_ITEM,
    OUTPUT_MAGIC as LATTICE_OUTPUT_MAGIC,
    RECEIPT_SCHEMA as LATTICE_RECEIPT_SCHEMA,
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_Q_T_ROWS,
    SOURCE_RESIDUE_INTERPOLATIONS,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
    maximum_t_index,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-large-q-residue-composition-v1"
CHECKER_ID = "independent-mpfr-directed-residue-composition-v1"
JOB_SCHEMA = "sparkinterval.tg.dirichlet_residue_composition.job.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_residue_composition.receipt.v1"
SERVICE_REQUEST_SCHEMA = (
    "sparkinterval.tg.dirichlet_residue_composition.service_request.v1"
)
FRAMED_REQUEST_SCHEMA = (
    "sparkinterval.tg.dirichlet_residue_composition.framed_request.v1"
)

CERTIFIED_CLASSIFICATION = "certified_upstream_composition_not_atom_closure"
SYNTHETIC_CLASSIFICATION = "synthetic_composition_kat_only"
DEFAULT_FACTOR_PRECISION_BITS = 192
MINIMUM_FACTOR_PRECISION_BITS = 128
DEFAULT_MAX_BATCH_COUNT = 64
MAXIMUM_GROUP_ORDER = 399_988
NUMPY_FRAME_BYTES_PER_VALUE_BOUND = 512

_HEX_DIGITS = frozenset("0123456789abcdef")


class DirichletResidueCompositionError(RuntimeError):
    """An upstream binding, interval operation, or output contract failed."""


def _fail(message: str) -> NoReturn:
    raise DirichletResidueCompositionError(message)


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


def _load_canonical_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise DirichletResidueCompositionError(f"cannot read {label}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not canonical JSON")
    return value, raw


def _verify_self_hash(
    value: dict[str, Any], *, field: str, label: str
) -> None:
    expected = value.get(field)
    body = dict(value)
    body.pop(field, None)
    if (
        not isinstance(expected, str)
        or expected != sha256_bytes(canonical_json_bytes(body))
    ):
        _fail(f"{label} self-hash mismatch")


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


@dataclass(frozen=True)
class Artifact:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Frame:
    lattice_input: Artifact
    lattice_output: Artifact
    finite_recovery: Artifact
    lattice_certificate: Artifact | None
    lattice_replay: Artifact | None
    lattice_stage_receipt: Artifact | None


@dataclass(frozen=True)
class CompositionJob:
    path: Path
    sha256: str
    classification: str
    q: int
    first_t_numerator: int
    t_denominator: int
    t_step_numerator: int
    frames: tuple[Frame, ...]


@dataclass(frozen=True)
class ResiduePlan:
    q: int
    residues: tuple[int, ...]
    positions: array
    component_orders: tuple[int, ...]
    request_sha256: str
    first_a: int
    last_a: int

    @property
    def order(self) -> int:
        return len(self.residues)


def _artifact_from_record(
    record: object, *, base: Path, label: str
) -> Artifact:
    if not isinstance(record, dict) or set(record) != {
        "path", "sha256", "size_bytes"
    }:
        _fail(f"{label} is not a canonical artifact record")
    raw_path = record["path"]
    digest = record["sha256"]
    size_bytes = record["size_bytes"]
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        _fail(f"{label}.path is invalid")
    if not _valid_digest(digest):
        _fail(f"{label}.sha256 is invalid")
    if type(size_bytes) is not int or size_bytes <= 0:
        _fail(f"{label}.size_bytes is invalid")
    path = Path(raw_path)
    if not path.is_absolute():
        path = base / path
    return Artifact(path.resolve(), digest, size_bytes)


def _verify_artifact(artifact: Artifact, label: str) -> None:
    try:
        mode = artifact.path.stat().st_mode
    except OSError as error:
        raise DirichletResidueCompositionError(
            f"cannot stat {label}: {artifact.path}"
        ) from error
    if not stat.S_ISREG(mode):
        _fail(f"{label} is not a regular file")
    digest, size = sha256_file(artifact.path)
    if digest != artifact.sha256 or size != artifact.size_bytes:
        _fail(f"{label} hash or length mismatch")


def load_job(
    path: Path,
    *,
    allow_synthetic_kat: bool = False,
    max_batch_count: int = DEFAULT_MAX_BATCH_COUNT,
) -> CompositionJob:
    """Load a canonical job and verify every named artifact hash up front."""

    if max_batch_count <= 0:
        _fail("max_batch_count must be positive")
    value, raw = _load_canonical_json(path, "composition job")
    required = {
        "schema", "schema_version", "classification", "q",
        "first_t_numerator", "t_denominator", "t_step_numerator", "frames",
    }
    if set(value) != required:
        _fail("composition job fields changed")
    if value.get("schema") != JOB_SCHEMA or value.get("schema_version") != 1:
        _fail("composition job schema mismatch")
    classification = value.get("classification")
    if classification not in {CERTIFIED_CLASSIFICATION, SYNTHETIC_CLASSIFICATION}:
        _fail("composition job classification mismatch")
    if classification == SYNTHETIC_CLASSIFICATION and not allow_synthetic_kat:
        _fail("synthetic composition jobs require explicit KAT authorization")

    q = value.get("q")
    first = value.get("first_t_numerator")
    denominator = value.get("t_denominator")
    step = value.get("t_step_numerator")
    if type(q) is not int or not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("composition q is outside the large-q source range")
    if (
        type(first) is not int
        or first < 0
        or type(denominator) is not int
        or denominator != SOURCE_SAMPLE_DENOMINATOR
        or type(step) is not int
        or step != SOURCE_SAMPLE_NUMERATOR
        or first % SOURCE_SAMPLE_NUMERATOR != 0
    ):
        _fail("composition ordinates are not the exact 5/64 source grid")
    raw_frames = value.get("frames")
    if (
        not isinstance(raw_frames, list)
        or not raw_frames
        or len(raw_frames) > max_batch_count
    ):
        _fail("composition batch count is empty or exceeds its bound")
    first_t_index = first // SOURCE_SAMPLE_NUMERATOR
    if first_t_index + len(raw_frames) - 1 > maximum_t_index(q):
        _fail("composition batch extends beyond this modulus's source height")

    frames: list[Frame] = []
    for index, raw_frame in enumerate(raw_frames):
        label = f"frames[{index}]"
        if not isinstance(raw_frame, dict):
            _fail(f"{label} is malformed")
        basic = {"lattice_input", "lattice_output", "finite_recovery"}
        certified = basic | {
            "lattice_certificate", "lattice_replay", "lattice_stage_receipt"
        }
        expected = certified if classification == CERTIFIED_CLASSIFICATION else basic
        if set(raw_frame) != expected:
            _fail(f"{label} fields do not match its classification")
        artifacts = {
            name: _artifact_from_record(
                raw_frame[name], base=path.resolve().parent, label=f"{label}.{name}"
            )
            for name in expected
        }
        for name, artifact in artifacts.items():
            _verify_artifact(artifact, f"{label}.{name}")
        frames.append(
            Frame(
                lattice_input=artifacts["lattice_input"],
                lattice_output=artifacts["lattice_output"],
                finite_recovery=artifacts["finite_recovery"],
                lattice_certificate=artifacts.get("lattice_certificate"),
                lattice_replay=artifacts.get("lattice_replay"),
                lattice_stage_receipt=artifacts.get("lattice_stage_receipt"),
            )
        )
    return CompositionJob(
        path=path.resolve(),
        sha256=sha256_bytes(raw),
        classification=classification,
        q=q,
        first_t_numerator=first,
        t_denominator=denominator,
        t_step_numerator=step,
        frames=tuple(frames),
    )


def artifact_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    """Return a canonical hash/size/path record for a job author."""

    resolved = path.resolve()
    digest, size = sha256_file(resolved)
    displayed = resolved
    if relative_to is not None:
        try:
            displayed = resolved.relative_to(relative_to.resolve())
        except ValueError:
            displayed = resolved
    return {"path": str(displayed), "sha256": digest, "size_bytes": size}


class ResiduePlanCache:
    """A one-modulus cache; changing q releases the previous CRT plan."""

    def __init__(self) -> None:
        self._plan: ResiduePlan | None = None

    def get(self, q: int) -> ResiduePlan:
        if self._plan is not None and self._plan.q == q:
            return self._plan
        residues = canonical_residue_order(q)
        if len(residues) > MAXIMUM_GROUP_ORDER:
            _fail("unit-group order exceeds the pinned large-q maximum")
        positions = array("i", [-1]) * q
        for position, residue in enumerate(residues):
            if positions[residue] != -1:
                _fail("canonical CRT residue order contains a duplicate")
            positions[residue] = position
        digest = hashlib.sha256()
        first_a: int | None = None
        last_a: int | None = None
        count = 0
        for a in range(1, q):
            if positions[a] < 0:
                continue
            row = canonical_lattice_row(q, a)
            digest.update(struct.pack("<III", q, a, row))
            first_a = a if first_a is None else first_a
            last_a = a
            count += 1
        if count != len(residues) or first_a is None or last_a is None:
            _fail("unit-group scan does not match canonical CRT order")
        self._plan = ResiduePlan(
            q=q,
            residues=residues,
            positions=positions,
            component_orders=canonical_component_orders(q),
            request_sha256=digest.hexdigest(),
            first_a=first_a,
            last_a=last_a,
        )
        return self._plan


# ctypes view of MPFR's public __mpfr_struct layout.  We use only the public
# mpfr_* API; the fields are never inspected by Python.
class _MPFRStruct(ctypes.Structure):
    _fields_ = [
        ("_mpfr_prec", ctypes.c_long),
        ("_mpfr_sign", ctypes.c_int),
        ("_mpfr_exp", ctypes.c_long),
        ("_mpfr_d", ctypes.POINTER(ctypes.c_ulong)),
    ]


_MPFRPointer = ctypes.POINTER(_MPFRStruct)
MPFR_RNDN = 0
MPFR_RNDU = 2
MPFR_RNDD = 3


class _MPFRValue:
    def __init__(self, runtime: "MPFRFactorProvider") -> None:
        self.lib = runtime.lib
        self.value = (_MPFRStruct * 1)()
        self.lib.mpfr_init2(self.value, runtime.precision_bits)

    @property
    def pointer(self) -> _MPFRPointer:
        return self.value

    def close(self) -> None:
        if self.value is not None:
            self.lib.mpfr_clear(self.value)
            self.value = None  # type: ignore[assignment]

    def __enter__(self) -> "_MPFRValue":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Interpreter shutdown may already have released the CDLL.
            pass


class _MPFRFactorWorkspace:
    """Reusable MPFR storage for one sequential factor provider.

    Source-scale callers evaluate billions of ordinates.  Reinitializing and
    clearing 28 MPFR values for every factor is pure allocator overhead and
    does not contribute to the directed enclosure.  Keeping the same
    fixed-precision values alive preserves every per-factor arithmetic
    operation and rounding mode while making that lifetime explicit.  The
    provider also reuses the directed log and inverse-square-root base while
    consecutive calls retain the same modulus; fixed hexadecimal tests cover
    both cache hits and q changes.
    """

    def __init__(self, runtime: "MPFRFactorProvider") -> None:
        self.values = [_MPFRValue(runtime) for _ in range(20)]
        (
            self.q_value,
            self.log_lo,
            self.log_hi,
            self.angle_lo,
            self.angle_hi,
            self.width,
            self.sqrt_lo,
            self.sqrt_hi,
            self.inv_lo,
            self.inv_hi,
            self.cos_lo,
            self.cos_hi,
            self.sin_lo,
            self.sin_hi,
            self.neg_sin_lo,
            self.neg_sin_hi,
            self.factor_re_lo,
            self.factor_re_hi,
            self.factor_im_lo,
            self.factor_im_hi,
        ) = self.values
        self.lower_products = [_MPFRValue(runtime) for _ in range(4)]
        self.upper_products = [_MPFRValue(runtime) for _ in range(4)]

    def close(self) -> None:
        for value in (
            *self.values,
            *self.lower_products,
            *self.upper_products,
        ):
            value.close()


class MPFRFactorProvider:
    """Generate a rigorous binary64 rectangle for ``q**(-1/2-it)``.

    MPFR supplies directed log/sqrt/sin/cos evaluations.  The exact angle lies
    in a directed MPFR interval.  Global 1-Lipschitz bounds for sine and cosine
    inflate an endpoint evaluation by the full angle width, avoiding any
    hidden monotonicity or range-reduction assumption.
    """

    def __init__(self, precision_bits: int = DEFAULT_FACTOR_PRECISION_BITS) -> None:
        if precision_bits < MINIMUM_FACTOR_PRECISION_BITS:
            _fail(
                f"factor precision must be at least {MINIMUM_FACTOR_PRECISION_BITS} bits"
            )
        library = ctypes.util.find_library("mpfr")
        if library is None:
            _fail("libmpfr is required for rigorous q^(-s) factor generation")
        try:
            self.lib = ctypes.CDLL(library)
        except OSError as error:
            raise DirichletResidueCompositionError(
                "cannot load libmpfr for q^(-s) factor generation"
            ) from error
        self.precision_bits = precision_bits
        self._bind()
        self._workspace: _MPFRFactorWorkspace | None = (
            _MPFRFactorWorkspace(self)
        )
        self._cached_q: int | None = None

    def close(self) -> None:
        workspace = getattr(self, "_workspace", None)
        if workspace is not None:
            self._workspace = None
            self._cached_q = None
            workspace.close()

    def __enter__(self) -> "MPFRFactorProvider":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Interpreter shutdown may already have released the CDLL.
            pass

    def _bind(self) -> None:
        one = [_MPFRPointer]
        two = [_MPFRPointer, _MPFRPointer]
        self.lib.mpfr_init2.argtypes = [_MPFRPointer, ctypes.c_long]
        self.lib.mpfr_clear.argtypes = one
        self.lib.mpfr_set.argtypes = [_MPFRPointer, _MPFRPointer, ctypes.c_int]
        self.lib.mpfr_set_si.argtypes = [_MPFRPointer, ctypes.c_long, ctypes.c_int]
        self.lib.mpfr_set_ui.argtypes = [_MPFRPointer, ctypes.c_ulong, ctypes.c_int]
        self.lib.mpfr_log.argtypes = two + [ctypes.c_int]
        self.lib.mpfr_sqrt.argtypes = two + [ctypes.c_int]
        self.lib.mpfr_sin.argtypes = two + [ctypes.c_int]
        self.lib.mpfr_cos.argtypes = two + [ctypes.c_int]
        self.lib.mpfr_mul.argtypes = two + [_MPFRPointer, ctypes.c_int]
        self.lib.mpfr_mul_ui.argtypes = two + [ctypes.c_ulong, ctypes.c_int]
        self.lib.mpfr_div_ui.argtypes = two + [ctypes.c_ulong, ctypes.c_int]
        self.lib.mpfr_ui_div.argtypes = [
            _MPFRPointer, ctypes.c_ulong, _MPFRPointer, ctypes.c_int
        ]
        self.lib.mpfr_add.argtypes = two + [_MPFRPointer, ctypes.c_int]
        self.lib.mpfr_sub.argtypes = two + [_MPFRPointer, ctypes.c_int]
        self.lib.mpfr_neg.argtypes = two + [ctypes.c_int]
        self.lib.mpfr_cmp.argtypes = two
        self.lib.mpfr_cmp.restype = ctypes.c_int
        self.lib.mpfr_cmp_si.argtypes = [_MPFRPointer, ctypes.c_long]
        self.lib.mpfr_cmp_si.restype = ctypes.c_int
        self.lib.mpfr_get_d.argtypes = [_MPFRPointer, ctypes.c_int]
        self.lib.mpfr_get_d.restype = ctypes.c_double
        self.lib.mpfr_get_version.argtypes = []
        self.lib.mpfr_get_version.restype = ctypes.c_char_p

    @property
    def version(self) -> str:
        return self.lib.mpfr_get_version().decode("ascii")

    def _trig_range_into(
        self,
        function: Any,
        angle_lo: _MPFRValue,
        width: _MPFRValue,
        lo: _MPFRValue,
        hi: _MPFRValue,
    ) -> None:
        function(lo.pointer, angle_lo.pointer, MPFR_RNDD)
        function(hi.pointer, angle_lo.pointer, MPFR_RNDU)
        self.lib.mpfr_sub(lo.pointer, lo.pointer, width.pointer, MPFR_RNDD)
        self.lib.mpfr_add(hi.pointer, hi.pointer, width.pointer, MPFR_RNDU)
        if self.lib.mpfr_cmp_si(lo.pointer, -1) < 0:
            self.lib.mpfr_set_si(lo.pointer, -1, MPFR_RNDN)
        if self.lib.mpfr_cmp_si(hi.pointer, 1) > 0:
            self.lib.mpfr_set_si(hi.pointer, 1, MPFR_RNDN)

    def _mul_range_into(
        self,
        x_lo: _MPFRValue,
        x_hi: _MPFRValue,
        y_lo: _MPFRValue,
        y_hi: _MPFRValue,
        lo: _MPFRValue,
        hi: _MPFRValue,
    ) -> None:
        workspace = self._workspace
        if workspace is None:
            _fail("q^(-s) factor provider is closed")
        lower_products = workspace.lower_products
        upper_products = workspace.upper_products
        pairs = ((x_lo, y_lo), (x_lo, y_hi), (x_hi, y_lo), (x_hi, y_hi))
        for destination, (x, y) in zip(lower_products, pairs):
            self.lib.mpfr_mul(
                destination.pointer, x.pointer, y.pointer, MPFR_RNDD
            )
        for destination, (x, y) in zip(upper_products, pairs):
            self.lib.mpfr_mul(
                destination.pointer, x.pointer, y.pointer, MPFR_RNDU
            )
        minimum = lower_products[0]
        maximum = upper_products[0]
        for candidate in lower_products[1:]:
            if self.lib.mpfr_cmp(candidate.pointer, minimum.pointer) < 0:
                minimum = candidate
        for candidate in upper_products[1:]:
            if self.lib.mpfr_cmp(candidate.pointer, maximum.pointer) > 0:
                maximum = candidate
        self.lib.mpfr_set(lo.pointer, minimum.pointer, MPFR_RNDD)
        self.lib.mpfr_set(hi.pointer, maximum.pointer, MPFR_RNDU)

    def factor(
        self, *, q: int, t_numerator: int, t_denominator: int
    ) -> tuple[float, float, float, float]:
        maximum_ulong = (1 << (8 * ctypes.sizeof(ctypes.c_ulong))) - 1
        if (
            not SOURCE_Q_START <= q <= SOURCE_Q_STOP
            or t_numerator < 0
            or t_denominator <= 0
            or t_numerator > maximum_ulong
            or t_denominator > maximum_ulong
        ):
            _fail("invalid or C-ABI-overflowing q or t for q^(-s)")
        workspace = self._workspace
        if workspace is None:
            _fail("q^(-s) factor provider is closed")
        (
            q_value, log_lo, log_hi, angle_lo, angle_hi,
            width, sqrt_lo, sqrt_hi, inv_lo,
            inv_hi, cos_lo, cos_hi, sin_lo, sin_hi,
            neg_sin_lo, neg_sin_hi, factor_re_lo, factor_re_hi,
            factor_im_lo, factor_im_hi,
        ) = workspace.values
        if self._cached_q != q:
            self.lib.mpfr_set_ui(q_value.pointer, q, MPFR_RNDN)
            self.lib.mpfr_log(log_lo.pointer, q_value.pointer, MPFR_RNDD)
            self.lib.mpfr_log(log_hi.pointer, q_value.pointer, MPFR_RNDU)
            self.lib.mpfr_sqrt(
                sqrt_lo.pointer, q_value.pointer, MPFR_RNDD
            )
            self.lib.mpfr_sqrt(
                sqrt_hi.pointer, q_value.pointer, MPFR_RNDU
            )
            self.lib.mpfr_ui_div(
                inv_lo.pointer, 1, sqrt_hi.pointer, MPFR_RNDD
            )
            self.lib.mpfr_ui_div(
                inv_hi.pointer, 1, sqrt_lo.pointer, MPFR_RNDU
            )
            self._cached_q = q
        self.lib.mpfr_mul_ui(
            angle_lo.pointer, log_lo.pointer, t_numerator, MPFR_RNDD
        )
        self.lib.mpfr_div_ui(
            angle_lo.pointer, angle_lo.pointer, t_denominator, MPFR_RNDD
        )
        self.lib.mpfr_mul_ui(
            angle_hi.pointer, log_hi.pointer, t_numerator, MPFR_RNDU
        )
        self.lib.mpfr_div_ui(
            angle_hi.pointer, angle_hi.pointer, t_denominator, MPFR_RNDU
        )
        self.lib.mpfr_sub(
            width.pointer, angle_hi.pointer, angle_lo.pointer, MPFR_RNDU
        )

        self._trig_range_into(
            self.lib.mpfr_cos, angle_lo, width, cos_lo, cos_hi
        )
        self._trig_range_into(
            self.lib.mpfr_sin, angle_lo, width, sin_lo, sin_hi
        )
        self.lib.mpfr_neg(neg_sin_lo.pointer, sin_hi.pointer, MPFR_RNDD)
        self.lib.mpfr_neg(neg_sin_hi.pointer, sin_lo.pointer, MPFR_RNDU)
        self._mul_range_into(
            inv_lo, inv_hi, cos_lo, cos_hi, factor_re_lo, factor_re_hi
        )
        self._mul_range_into(
            inv_lo, inv_hi, neg_sin_lo, neg_sin_hi,
            factor_im_lo, factor_im_hi,
        )
        result = (
            self.lib.mpfr_get_d(factor_re_lo.pointer, MPFR_RNDD),
            self.lib.mpfr_get_d(factor_re_hi.pointer, MPFR_RNDU),
            self.lib.mpfr_get_d(factor_im_lo.pointer, MPFR_RNDD),
            self.lib.mpfr_get_d(factor_im_hi.pointer, MPFR_RNDU),
        )
        if not (
            all(math.isfinite(endpoint) for endpoint in result)
            and result[0] <= result[1]
            and result[2] <= result[3]
        ):
            _fail("MPFR q^(-s) factor did not fit a binary64 rectangle")
        return result


def _downward(value: float) -> float:
    if not math.isfinite(value):
        _fail("binary64 interval operation overflowed")
    return math.nextafter(value, -math.inf)


def _upward(value: float) -> float:
    if not math.isfinite(value):
        _fail("binary64 interval operation overflowed")
    return math.nextafter(value, math.inf)


def _interval_mul(
    x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> tuple[float, float]:
    lower = (
        _downward(x_lo * y_lo), _downward(x_lo * y_hi),
        _downward(x_hi * y_lo), _downward(x_hi * y_hi),
    )
    upper = (
        _upward(x_lo * y_lo), _upward(x_lo * y_hi),
        _upward(x_hi * y_lo), _upward(x_hi * y_hi),
    )
    return min(lower), max(upper)


def _interval_add(
    x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> tuple[float, float]:
    return _downward(x_lo + y_lo), _upward(x_hi + y_hi)


def _interval_sub(
    x_lo: float, x_hi: float, y_lo: float, y_hi: float
) -> tuple[float, float]:
    return _downward(x_lo - y_hi), _upward(x_hi - y_lo)


def compose_interval(
    zeta: Sequence[float], factor: Sequence[float], recovery: Sequence[float]
) -> tuple[float, float, float, float]:
    """Natural outward interval extension of ``factor*zeta + recovery``."""

    if len(zeta) != 4 or len(factor) != 4 or len(recovery) != 4:
        _fail("complex intervals must contain exactly four endpoints")
    zr_lo, zr_hi, zi_lo, zi_hi = zeta
    fr_lo, fr_hi, fi_lo, fi_hi = factor
    rr_lo, rr_hi, ri_lo, ri_hi = recovery
    endpoints = tuple(zeta) + tuple(factor) + tuple(recovery)
    if not (
        all(math.isfinite(value) for value in endpoints)
        and zr_lo <= zr_hi and zi_lo <= zi_hi
        and fr_lo <= fr_hi and fi_lo <= fi_hi
        and rr_lo <= rr_hi and ri_lo <= ri_hi
    ):
        _fail("malformed complex interval supplied to composition")
    rr_product = _interval_mul(zr_lo, zr_hi, fr_lo, fr_hi)
    ii_product = _interval_mul(zi_lo, zi_hi, fi_lo, fi_hi)
    ri_product = _interval_mul(zr_lo, zr_hi, fi_lo, fi_hi)
    ir_product = _interval_mul(zi_lo, zi_hi, fr_lo, fr_hi)
    product_re = _interval_sub(*rr_product, *ii_product)
    product_im = _interval_add(*ri_product, *ir_product)
    result_re = _interval_add(*product_re, rr_lo, rr_hi)
    result_im = _interval_add(*product_im, ri_lo, ri_hi)
    result = (*result_re, *result_im)
    if not all(math.isfinite(value) for value in result):
        _fail("composed interval is not finite")
    return result


def _read_exact(source: BinaryIO, size: int, label: str) -> bytes:
    raw = source.read(size)
    if len(raw) != size:
        _fail(f"short {label}")
    return raw


def _validate_box(values: Sequence[float], label: str) -> tuple[float, ...]:
    box = tuple(values)
    if (
        len(box) != 4
        or not all(math.isfinite(value) for value in box)
        or box[0] > box[1]
        or box[2] > box[3]
    ):
        _fail(f"{label} contains a malformed interval")
    return box


def _validate_certificate_chain(
    frame: Frame,
    *,
    plan: ResiduePlan,
    expected_t_numerator: int,
) -> int:
    if (
        frame.lattice_certificate is None
        or frame.lattice_replay is None
        or frame.lattice_stage_receipt is None
    ):
        _fail("certified frame is missing an upstream hash-chain artifact")
    certificate, _ = _load_canonical_json(
        frame.lattice_certificate.path, "lattice certificate"
    )
    if set(certificate) != {
        "schema", "schema_version", "author", "atom_id", "algorithm_id",
        "checker_id", "classification", "source", "parameters", "requests",
        "uniform_taylor_tail", "artifacts", "generator_runtime", "decisions",
        "certificate_sha256",
    }:
        _fail("lattice certificate fields changed")
    if (
        certificate.get("schema") != LATTICE_MANIFEST_SCHEMA
        or certificate.get("schema_version") != 1
        or certificate.get("author") != AUTHOR
        or certificate.get("atom_id") != ATOM_ID
        or certificate.get("algorithm_id")
        != "platt-dirichlet-certified-lattice-input-v1"
        or certificate.get("checker_id")
        != "higher-precision-flint-plus-exact-rational-tail-v1"
        or certificate.get("source") != _lattice_source_record()
    ):
        _fail("lattice certificate schema or producer identity mismatch")
    _verify_self_hash(
        certificate, field="certificate_sha256", label="lattice certificate"
    )
    parameters = certificate.get("parameters")
    requests = certificate.get("requests")
    artifacts = certificate.get("artifacts")
    decisions = certificate.get("decisions")
    if not all(isinstance(value, dict) for value in (
        parameters, requests, artifacts, decisions
    )):
        _fail("lattice certificate binding records are malformed")
    assert isinstance(parameters, dict)
    assert isinstance(requests, dict)
    assert isinstance(artifacts, dict)
    assert isinstance(decisions, dict)
    expected_t = Fraction(expected_t_numerator, SOURCE_SAMPLE_DENOMINATOR)
    t_record = parameters.get("t")
    try:
        recorded_t = Fraction(int(t_record["numerator"]), int(t_record["denominator"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise DirichletResidueCompositionError(
            "lattice certificate has a malformed exact ordinate"
        ) from error
    m = parameters.get("M")
    generation_precision = parameters.get("generation_precision_bits")
    if (
        parameters.get("q_start_inclusive") != plan.q
        or parameters.get("q_stop_inclusive") != plan.q
        or parameters.get("t_index") != expected_t_numerator // SOURCE_SAMPLE_NUMERATOR
        or recorded_t != expected_t
        or parameters.get("D") != LATTICE_ROWS
        or parameters.get("N") != TAYLOR_DEGREE
        or parameters.get("columns") != TAYLOR_COLUMNS
        or parameters.get("max_items") is not None
        or type(m) is not int
        or m <= 0
        or type(generation_precision) is not int
        or generation_precision < 128
    ):
        _fail("lattice certificate parameters do not match the full q/t frame")
    if (
        certificate.get("classification")
        != "source_shaped_certified_analytic_batch_not_theorem_7_1"
        or requests.get("count") != plan.order
        or requests.get("sha256_le_u32_q_a_row") != plan.request_sha256
        or requests.get("first")
        != {"q": plan.q, "a": plan.first_a,
            "row": canonical_lattice_row(plan.q, plan.first_a)}
        or requests.get("last")
        != {"q": plan.q, "a": plan.last_a,
            "row": canonical_lattice_row(plan.q, plan.last_a)}
        or requests.get("enumeration") != REQUEST_ENUMERATION
    ):
        _fail("lattice certificate request enumeration mismatch")
    if set(artifacts) != {
        "lattice-input.bin", "finite-recovery.bin", "producer_module"
    }:
        _fail("lattice certificate artifact closure changed")
    producer_digest, producer_size = sha256_file(
        Path(_lattice_certificates.__file__).resolve()
    )
    if artifacts.get("producer_module") != {
        "sha256": producer_digest, "size_bytes": producer_size
    }:
        _fail("lattice certificate producer-module identity mismatch")
    for artifact_name, expected in (
        ("lattice-input.bin", frame.lattice_input),
        ("finite-recovery.bin", frame.finite_recovery),
    ):
        record = artifacts.get(artifact_name)
        if (
            not isinstance(record, dict)
            or record.get("sha256") != expected.sha256
            or record.get("size_bytes") != expected.size_bytes
        ):
            _fail(f"lattice certificate does not bind {artifact_name}")
    if decisions != LATTICE_CERTIFICATE_DECISIONS:
        _fail("lattice certificate capability flags are unsafe")
    try:
        _validate_lattice_runtime_record(
            certificate.get("generator_runtime"), "generator_runtime"
        )
    except RuntimeError as error:
        raise DirichletResidueCompositionError(
            "lattice certificate generator runtime is invalid"
        ) from error

    replay, _ = _load_canonical_json(frame.lattice_replay.path, "lattice replay")
    if set(replay) != {
        "schema", "schema_version", "classification", "certificate_sha256",
        "replay_precision_bits", "lattice_cells_replayed",
        "finite_recovery_values_replayed", "uniform_tail_replayed_exactly",
        "strict_request_geometry_replayed",
        "higher_precision_arb_containment_passed", "generator_runtime",
        "replay_runtime", "same_runtime_binary", "elapsed_seconds",
        "external_atom_discharged", "replay_sha256",
    }:
        _fail("lattice replay fields changed")
    if (
        replay.get("schema") != LATTICE_REPLAY_SCHEMA
        or replay.get("schema_version") != 1
        or replay.get("classification")
        != "complete_input_bundle_replay_not_theorem_7_1"
    ):
        _fail("lattice replay schema or classification mismatch")
    _verify_self_hash(replay, field="replay_sha256", label="lattice replay")
    if (
        replay.get("certificate_sha256") != certificate.get("certificate_sha256")
        or replay.get("generator_runtime") != certificate.get("generator_runtime")
        or type(replay.get("replay_precision_bits")) is not int
        or replay.get("replay_precision_bits", 0)
        < generation_precision + 64
        or replay.get("lattice_cells_replayed") != LATTICE_ROWS * TAYLOR_COLUMNS
        or replay.get("finite_recovery_values_replayed") != plan.order
        or replay.get("uniform_tail_replayed_exactly") is not True
        or replay.get("strict_request_geometry_replayed") is not True
        or replay.get("higher_precision_arb_containment_passed") is not True
        or replay.get("external_atom_discharged") is not False
    ):
        _fail("lattice replay does not close the input bundle's stated checks")
    try:
        _validate_lattice_runtime_record(
            replay.get("generator_runtime"), "generator_runtime"
        )
        _validate_lattice_runtime_record(replay.get("replay_runtime"), "replay_runtime")
    except RuntimeError as error:
        raise DirichletResidueCompositionError(
            "lattice replay runtime identity is invalid"
        ) from error

    receipt, _ = _load_canonical_json(
        frame.lattice_stage_receipt.path, "lattice-stage receipt"
    )
    if set(receipt) != {
        "schema", "schema_version", "author", "atom_id", "algorithm_id",
        "checker_id", "source_plan_sha256", "classification", "input",
        "artifacts", "decisions", "receipt_sha256",
    }:
        _fail("lattice-stage receipt fields changed")
    if (
        receipt.get("schema") != LATTICE_RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("author") != AUTHOR
        or receipt.get("atom_id") != ATOM_ID
        or receipt.get("algorithm_id")
        != "platt-dirichlet-large-q-lattice-taylor-stage-v1"
        or receipt.get("checker_id")
        != "cpu-exact-rational-natural-interval-v1"
        or not _valid_digest(receipt.get("source_plan_sha256"))
        or receipt.get("classification")
        != "conditional_taylor_stage_with_external_lattice_certificate"
    ):
        _fail("lattice-stage receipt schema or classification mismatch")
    _verify_self_hash(receipt, field="receipt_sha256", label="lattice-stage receipt")
    input_record = receipt.get("input")
    receipt_artifacts = receipt.get("artifacts")
    receipt_decisions = receipt.get("decisions")
    if not all(isinstance(value, dict) for value in (
        input_record, receipt_artifacts, receipt_decisions
    )):
        _fail("lattice-stage receipt binding records are malformed")
    assert isinstance(input_record, dict)
    assert isinstance(receipt_artifacts, dict)
    assert isinstance(receipt_decisions, dict)
    if set(input_record) != {
        "sha256", "size_bytes", "t", "item_count", "first_request",
        "last_request",
    } or set(receipt_artifacts) != {
        "runner", "checker", "output", "lattice_certificate"
    }:
        _fail("lattice-stage receipt artifact closure changed")
    output_record = receipt_artifacts.get("output")
    certificate_record = receipt_artifacts.get("lattice_certificate")
    if (
        input_record.get("sha256") != frame.lattice_input.sha256
        or input_record.get("size_bytes") != frame.lattice_input.size_bytes
        or input_record.get("t")
        != {"numerator": expected_t_numerator,
            "denominator": SOURCE_SAMPLE_DENOMINATOR}
        or input_record.get("item_count") != plan.order
        or input_record.get("first_request")
        != {"q": plan.q, "a": plan.first_a}
        or input_record.get("last_request")
        != {"q": plan.q, "a": plan.last_a}
        or not isinstance(output_record, dict)
        or output_record.get("sha256") != frame.lattice_output.sha256
        or output_record.get("size_bytes") != frame.lattice_output.size_bytes
        or not isinstance(certificate_record, dict)
        or certificate_record.get("sha256") != frame.lattice_certificate.sha256
        or certificate_record.get("size_bytes") != frame.lattice_certificate.size_bytes
        or receipt_decisions
        != {
            "canonical_input_replayed": True,
            "exact_rational_arithmetic_replay_passed": True,
            "lattice_semantics_proved_by_this_receipt": False,
            "taylor_tail_bound_proved_by_this_receipt": False,
            "unit_group_fft_completed": False,
            "turing_completeness_completed": False,
            "external_atom_discharged": False,
        }
    ):
        _fail("lattice-stage receipt does not bind this input/output/certificate")
    return m


class _HashingWriter:
    def __init__(self, output: BinaryIO) -> None:
        self.output = output
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, raw: bytes | bytearray) -> None:
        self.output.write(raw)
        self.digest.update(raw)
        self.size += len(raw)


def _frame_into_buffer(
    frame: Frame,
    *,
    plan: ResiduePlan,
    expected_t_numerator: int,
    expected_m: int | None,
    factor: Sequence[float],
) -> tuple[bytearray, int]:
    buffer = bytearray(plan.order * COMPLEX_INTERVAL.size)
    with (
        frame.lattice_input.path.open("rb") as lattice_input,
        frame.lattice_output.path.open("rb") as lattice_output,
        frame.finite_recovery.path.open("rb") as recovery,
    ):
        input_header = LATTICE_INPUT_HEADER.unpack(
            _read_exact(lattice_input, LATTICE_INPUT_HEADER.size, "lattice input header")
        )
        (
            input_magic, input_version, rows, degree, input_reserved0,
            input_t_numerator, input_t_denominator, input_count,
            lattice_count, input_reserved1,
        ) = input_header
        expected_input_size = (
            LATTICE_INPUT_HEADER.size
            + LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
            + plan.order * LATTICE_INPUT_ITEM.size
        )
        if (
            input_magic != LATTICE_INPUT_MAGIC
            or input_version != LATTICE_FORMAT_VERSION
            or rows != LATTICE_ROWS
            or degree != TAYLOR_DEGREE
            or input_reserved0 != 0
            or input_reserved1 != 0
            or input_t_numerator != expected_t_numerator
            or input_t_denominator != SOURCE_SAMPLE_DENOMINATOR
            or input_count != plan.order
            or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
            or frame.lattice_input.size_bytes != expected_input_size
        ):
            _fail("TGDLATI1 header, t, count, or length mismatch")
        lattice_input.seek(lattice_count * LATTICE_CELL.size, os.SEEK_CUR)

        output_header = LATTICE_OUTPUT_HEADER.unpack(
            _read_exact(
                lattice_output, LATTICE_OUTPUT_HEADER.size, "lattice output header"
            )
        )
        (
            output_magic, output_version, output_rows, output_degree,
            output_reserved0, output_count, _elapsed_ns, output_reserved1,
        ) = output_header
        if (
            output_magic != LATTICE_OUTPUT_MAGIC
            or output_version != LATTICE_FORMAT_VERSION
            or output_rows != LATTICE_ROWS
            or output_degree != TAYLOR_DEGREE
            or output_reserved0 != 0
            or output_reserved1 != 0
            or output_count != plan.order
            or frame.lattice_output.size_bytes
            != LATTICE_OUTPUT_HEADER.size + plan.order * LATTICE_OUTPUT_ITEM.size
        ):
            _fail("TGDLATO1 header, count, or length mismatch")

        recovery_header = RECOVERY_HEADER.unpack(
            _read_exact(recovery, RECOVERY_HEADER.size, "finite-recovery header")
        )
        (
            recovery_magic, recovery_version, m, recovery_reserved0,
            recovery_t_numerator, recovery_t_denominator, recovery_count,
            recovery_reserved1,
        ) = recovery_header
        if (
            recovery_magic != RECOVERY_MAGIC
            or recovery_version != RECOVERY_FORMAT_VERSION
            or type(m) is not int
            or m <= 0
            or recovery_reserved0 != 0
            or recovery_reserved1 != 0
            or recovery_t_numerator != expected_t_numerator
            or recovery_t_denominator != SOURCE_SAMPLE_DENOMINATOR
            or recovery_count != plan.order
            or frame.finite_recovery.size_bytes
            != RECOVERY_HEADER.size + plan.order * RECOVERY_ITEM.size
            or (expected_m is not None and m != expected_m)
        ):
            _fail("TGDLREC1 header, M, t, count, or length mismatch")

        seen = 0
        for a in range(1, plan.q):
            position = plan.positions[a]
            if position < 0:
                continue
            row = canonical_lattice_row(plan.q, a)
            input_item = LATTICE_INPUT_ITEM.unpack(
                _read_exact(lattice_input, LATTICE_INPUT_ITEM.size, "lattice request")
            )
            input_q, input_a, input_row, request_reserved, radius = input_item
            output_item = LATTICE_OUTPUT_ITEM.unpack(
                _read_exact(lattice_output, LATTICE_OUTPUT_ITEM.size, "Taylor output")
            )
            output_q, output_a, output_row, status, *zeta_values = output_item
            recovery_item = RECOVERY_ITEM.unpack(
                _read_exact(recovery, RECOVERY_ITEM.size, "finite-recovery item")
            )
            recovery_q, recovery_a, recovery_reserved_a, recovery_reserved_b, *r_values = (
                recovery_item
            )
            if (
                (input_q, input_a, input_row) != (plan.q, a, row)
                or request_reserved != 0
                or not math.isfinite(radius)
                or radius < 0
                or (output_q, output_a, output_row) != (plan.q, a, row)
                or status != 0
                or (recovery_q, recovery_a) != (plan.q, a)
                or recovery_reserved_a != 0
                or recovery_reserved_b != 0
            ):
                _fail("q/a/row ordering differs across TGDLATI1/TGDLATO1/TGDLREC1")
            zeta = _validate_box(zeta_values, "Taylor output")
            finite = _validate_box(r_values, "finite recovery")
            composed = compose_interval(zeta, factor, finite)
            COMPLEX_INTERVAL.pack_into(
                buffer, position * COMPLEX_INTERVAL.size, *composed
            )
            seen += 1
        if seen != plan.order:
            _fail("unit-group row count changed during composition")
        if lattice_input.read(1) or lattice_output.read(1) or recovery.read(1):
            _fail("upstream artifact contains trailing bytes")
    return buffer, m


def _numpy_interval_mul(
    x_lo: Any, x_hi: Any, y_lo: Any, y_hi: Any
) -> tuple[Any, Any]:
    assert _np is not None
    negative = _np.float64(-math.inf)
    positive = _np.float64(math.inf)
    products = (
        x_lo * y_lo, x_lo * y_hi, x_hi * y_lo, x_hi * y_hi,
    )
    lower = _np.minimum.reduce(
        tuple(_np.nextafter(product, negative) for product in products)
    )
    upper = _np.maximum.reduce(
        tuple(_np.nextafter(product, positive) for product in products)
    )
    return lower, upper


def _numpy_interval_add(
    x_lo: Any, x_hi: Any, y_lo: Any, y_hi: Any
) -> tuple[Any, Any]:
    assert _np is not None
    return (
        _np.nextafter(x_lo + y_lo, _np.float64(-math.inf)),
        _np.nextafter(x_hi + y_hi, _np.float64(math.inf)),
    )


def _numpy_interval_sub(
    x_lo: Any, x_hi: Any, y_lo: Any, y_hi: Any
) -> tuple[Any, Any]:
    assert _np is not None
    return (
        _np.nextafter(x_lo - y_hi, _np.float64(-math.inf)),
        _np.nextafter(x_hi - y_lo, _np.float64(math.inf)),
    )


def _frame_into_buffer_numpy(
    frame: Frame,
    *,
    plan: ResiduePlan,
    expected_t_numerator: int,
    expected_m: int | None,
    factor: Sequence[float],
) -> tuple[bytearray, int]:
    """Vectorised version of the same directed natural interval extension."""

    if _np is None:
        _fail("NumPy backend requested but NumPy is unavailable")
    # These guards make the binary64/nextafter assumptions executable rather
    # than relying only on platform convention.
    info = _np.finfo(_np.float64)
    if info.bits != 64 or info.nmant != 52 or _np.dtype("<f8").itemsize != 8:
        _fail("NumPy does not expose IEEE-754 binary64")
    with frame.lattice_input.path.open("rb") as source:
        input_header = LATTICE_INPUT_HEADER.unpack(
            _read_exact(source, LATTICE_INPUT_HEADER.size, "lattice input header")
        )
    (
        input_magic, input_version, rows, degree, input_reserved0,
        input_t_numerator, input_t_denominator, input_count,
        lattice_count, input_reserved1,
    ) = input_header
    input_offset = LATTICE_INPUT_HEADER.size + lattice_count * LATTICE_CELL.size
    if (
        input_magic != LATTICE_INPUT_MAGIC
        or input_version != LATTICE_FORMAT_VERSION
        or rows != LATTICE_ROWS
        or degree != TAYLOR_DEGREE
        or input_reserved0 != 0
        or input_reserved1 != 0
        or input_t_numerator != expected_t_numerator
        or input_t_denominator != SOURCE_SAMPLE_DENOMINATOR
        or input_count != plan.order
        or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
        or frame.lattice_input.size_bytes
        != input_offset + plan.order * LATTICE_INPUT_ITEM.size
    ):
        _fail("TGDLATI1 header, t, count, or length mismatch")

    with frame.lattice_output.path.open("rb") as source:
        output_header = LATTICE_OUTPUT_HEADER.unpack(
            _read_exact(source, LATTICE_OUTPUT_HEADER.size, "lattice output header")
        )
    (
        output_magic, output_version, output_rows, output_degree,
        output_reserved0, output_count, _elapsed_ns, output_reserved1,
    ) = output_header
    if (
        output_magic != LATTICE_OUTPUT_MAGIC
        or output_version != LATTICE_FORMAT_VERSION
        or output_rows != LATTICE_ROWS
        or output_degree != TAYLOR_DEGREE
        or output_reserved0 != 0
        or output_reserved1 != 0
        or output_count != plan.order
        or frame.lattice_output.size_bytes
        != LATTICE_OUTPUT_HEADER.size + plan.order * LATTICE_OUTPUT_ITEM.size
    ):
        _fail("TGDLATO1 header, count, or length mismatch")

    with frame.finite_recovery.path.open("rb") as source:
        recovery_header = RECOVERY_HEADER.unpack(
            _read_exact(source, RECOVERY_HEADER.size, "finite-recovery header")
        )
    (
        recovery_magic, recovery_version, m, recovery_reserved0,
        recovery_t_numerator, recovery_t_denominator, recovery_count,
        recovery_reserved1,
    ) = recovery_header
    if (
        recovery_magic != RECOVERY_MAGIC
        or recovery_version != RECOVERY_FORMAT_VERSION
        or type(m) is not int
        or m <= 0
        or recovery_reserved0 != 0
        or recovery_reserved1 != 0
        or recovery_t_numerator != expected_t_numerator
        or recovery_t_denominator != SOURCE_SAMPLE_DENOMINATOR
        or recovery_count != plan.order
        or frame.finite_recovery.size_bytes
        != RECOVERY_HEADER.size + plan.order * RECOVERY_ITEM.size
        or (expected_m is not None and m != expected_m)
    ):
        _fail("TGDLREC1 header, M, t, count, or length mismatch")

    input_dtype = _np.dtype(
        [
            ("q", "<u4"), ("a", "<u4"), ("row", "<u4"),
            ("reserved", "<u4"), ("radius", "<f8"),
        ],
        align=False,
    )
    output_dtype = _np.dtype(
        [
            ("q", "<u4"), ("a", "<u4"), ("row", "<u4"),
            ("status", "<u4"), ("box", "<f8", (4,)),
        ],
        align=False,
    )
    recovery_dtype = _np.dtype(
        [
            ("q", "<u4"), ("a", "<u4"), ("reserved0", "<u4"),
            ("reserved1", "<u4"), ("box", "<f8", (4,)),
        ],
        align=False,
    )
    if (
        input_dtype.itemsize != LATTICE_INPUT_ITEM.size
        or output_dtype.itemsize != LATTICE_OUTPUT_ITEM.size
        or recovery_dtype.itemsize != RECOVERY_ITEM.size
    ):
        _fail("NumPy structured dtype does not match a binary protocol")
    requests = _np.memmap(
        frame.lattice_input.path,
        dtype=input_dtype,
        mode="r",
        offset=input_offset,
        shape=(plan.order,),
    )
    taylor = _np.memmap(
        frame.lattice_output.path,
        dtype=output_dtype,
        mode="r",
        offset=LATTICE_OUTPUT_HEADER.size,
        shape=(plan.order,),
    )
    finite = _np.memmap(
        frame.finite_recovery.path,
        dtype=recovery_dtype,
        mode="r",
        offset=RECOVERY_HEADER.size,
        shape=(plan.order,),
    )
    positions = _np.frombuffer(plan.positions, dtype=_np.int32)
    expected_a = _np.flatnonzero(positions >= 0).astype(_np.uint32, copy=False)
    expected_row = (
        (
            2 * _np.uint64(LATTICE_ROWS) * expected_a.astype(_np.uint64)
            + _np.uint64(plan.q - 1)
        )
        // _np.uint64(2 * plan.q)
    ).astype(_np.uint32)
    expected_row = _np.clip(expected_row, 1, LATTICE_ROWS)
    zeta = taylor["box"]
    recovery_boxes = finite["box"]
    if not (
        expected_a.size == plan.order
        and _np.all(requests["q"] == plan.q)
        and _np.array_equal(requests["a"], expected_a)
        and _np.array_equal(requests["row"], expected_row)
        and _np.all(requests["reserved"] == 0)
        and _np.all(_np.isfinite(requests["radius"]))
        and _np.all(requests["radius"] >= 0)
        and _np.all(taylor["q"] == plan.q)
        and _np.array_equal(taylor["a"], expected_a)
        and _np.array_equal(taylor["row"], expected_row)
        and _np.all(taylor["status"] == 0)
        and _np.all(finite["q"] == plan.q)
        and _np.array_equal(finite["a"], expected_a)
        and _np.all(finite["reserved0"] == 0)
        and _np.all(finite["reserved1"] == 0)
        and _np.all(_np.isfinite(zeta))
        and _np.all(_np.isfinite(recovery_boxes))
        and _np.all(zeta[:, 0] <= zeta[:, 1])
        and _np.all(zeta[:, 2] <= zeta[:, 3])
        and _np.all(recovery_boxes[:, 0] <= recovery_boxes[:, 1])
        and _np.all(recovery_boxes[:, 2] <= recovery_boxes[:, 3])
    ):
        _fail("q/a/row ordering or interval validity differs across upstream files")

    fr_lo, fr_hi, fi_lo, fi_hi = factor
    with _np.errstate(over="raise", invalid="raise"):
        rr_product = _numpy_interval_mul(zeta[:, 0], zeta[:, 1], fr_lo, fr_hi)
        ii_product = _numpy_interval_mul(zeta[:, 2], zeta[:, 3], fi_lo, fi_hi)
        ri_product = _numpy_interval_mul(zeta[:, 0], zeta[:, 1], fi_lo, fi_hi)
        ir_product = _numpy_interval_mul(zeta[:, 2], zeta[:, 3], fr_lo, fr_hi)
        product_re = _numpy_interval_sub(*rr_product, *ii_product)
        product_im = _numpy_interval_add(*ri_product, *ir_product)
        result_re = _numpy_interval_add(
            *product_re, recovery_boxes[:, 0], recovery_boxes[:, 1]
        )
        result_im = _numpy_interval_add(
            *product_im, recovery_boxes[:, 2], recovery_boxes[:, 3]
        )
    composed = _np.column_stack((*result_re, *result_im)).astype("<f8", copy=False)
    if not _np.all(_np.isfinite(composed)):
        _fail("NumPy composed interval is not finite")
    ordered = _np.empty_like(composed)
    ordered[positions[expected_a], :] = composed
    return bytearray(ordered.tobytes(order="C")), m


def _input_merkle(job: CompositionJob) -> str:
    leaves = []
    for frame in job.frames:
        artifacts = [
            frame.lattice_input, frame.lattice_output, frame.finite_recovery,
            frame.lattice_certificate, frame.lattice_replay,
            frame.lattice_stage_receipt,
        ]
        for artifact in artifacts:
            if artifact is not None:
                leaves.append(hashlib.sha256(bytes.fromhex(artifact.sha256)).digest())
    if not leaves:
        _fail("cannot commit an empty upstream artifact set")
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [
            hashlib.sha256(leaves[index] + leaves[index + 1]).digest()
            for index in range(0, len(leaves), 2)
        ]
    return leaves[0].hex()


def _write_atomic_json(path: Path, value: object) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class CompositionEngine:
    """Persistent, one-plan-at-a-time composition engine."""

    def __init__(
        self,
        *,
        factor_precision_bits: int = DEFAULT_FACTOR_PRECISION_BITS,
        max_batch_count: int = DEFAULT_MAX_BATCH_COUNT,
        backend: str = "auto",
    ) -> None:
        if max_batch_count <= 0:
            _fail("max_batch_count must be positive")
        if backend not in {"auto", "numpy", "scalar"}:
            _fail("composition backend must be auto, numpy, or scalar")
        if backend == "numpy" and _np is None:
            _fail("NumPy backend requested but NumPy is unavailable")
        self.factor_provider = MPFRFactorProvider(factor_precision_bits)
        self.plan_cache = ResiduePlanCache()
        self.max_batch_count = max_batch_count
        self.backend = "numpy" if backend == "auto" and _np is not None else backend
        if self.backend == "auto":
            self.backend = "scalar"

    def compose(
        self,
        job_path: Path,
        output_path: Path | None,
        *,
        receipt_path: Path | None = None,
        allow_synthetic_kat: bool = False,
        output_stream: BinaryIO | None = None,
        output_label: str = "<framed-stdout>",
    ) -> dict[str, Any]:
        if (output_path is None) == (output_stream is None):
            _fail("select exactly one output path or persistent output stream")
        started = time.perf_counter()
        job = load_job(
            job_path,
            allow_synthetic_kat=allow_synthetic_kat,
            max_batch_count=self.max_batch_count,
        )
        plan = self.plan_cache.get(job.q)
        if plan.order != math.prod(plan.component_orders):
            _fail("canonical component orders do not multiply to phi(q)")

        expected_m: int | None = None
        if job.classification == CERTIFIED_CLASSIFICATION:
            for index, frame in enumerate(job.frames):
                m = _validate_certificate_chain(
                    frame,
                    plan=plan,
                    expected_t_numerator=(
                        job.first_t_numerator + index * job.t_step_numerator
                    ),
                )
                expected_m = m if expected_m is None else expected_m
                if m != expected_m:
                    _fail("M changes within one composition batch")

        resolved_output: Path | None = None
        fifo = False
        persistent_stream = output_stream is not None
        owns_output = not persistent_stream
        temporary: Path | None = None
        if persistent_stream:
            assert output_stream is not None
            output_handle = output_stream
        else:
            assert output_path is not None
            resolved_output = output_path.resolve()
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            fifo = resolved_output.exists() and stat.S_ISFIFO(
                resolved_output.stat().st_mode
            )
            if resolved_output.exists() and not fifo:
                _fail(f"refusing to replace immutable output: {resolved_output}")
            if fifo:
                output_handle = resolved_output.open("wb", buffering=0)
            else:
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{resolved_output.name}.", dir=resolved_output.parent
                )
                temporary = Path(temporary_name)
                output_handle = os.fdopen(descriptor, "wb")
        writer = _HashingWriter(output_handle)
        value_count = len(job.frames) * plan.order
        try:
            writer.write(
                ALLCHARS_INPUT_HEADER.pack(
                    ALLCHARS_INPUT_MAGIC,
                    ALLCHARS_FORMAT_VERSION,
                    job.q,
                    len(plan.component_orders),
                    len(job.frames),
                    plan.order,
                    job.first_t_numerator,
                    job.t_denominator,
                    job.t_step_numerator,
                    value_count,
                    0,
                )
            )
            factor_boxes: list[dict[str, Any]] = []
            for index, frame in enumerate(job.frames):
                t_numerator = job.first_t_numerator + index * job.t_step_numerator
                factor = self.factor_provider.factor(
                    q=job.q,
                    t_numerator=t_numerator,
                    t_denominator=job.t_denominator,
                )
                frame_function = (
                    _frame_into_buffer_numpy
                    if self.backend == "numpy"
                    else _frame_into_buffer
                )
                buffer, m = frame_function(
                    frame,
                    plan=plan,
                    expected_t_numerator=t_numerator,
                    expected_m=expected_m,
                    factor=factor,
                )
                expected_m = m if expected_m is None else expected_m
                if m != expected_m:
                    _fail("M changes within one composition batch")
                # Close the path-replacement window between the initial hash
                # pass and parsing.  The composed buffer is not emitted until
                # every artifact used for this frame still has its committed
                # digest and length.
                for name, artifact in (
                    ("lattice_input", frame.lattice_input),
                    ("lattice_output", frame.lattice_output),
                    ("finite_recovery", frame.finite_recovery),
                    ("lattice_certificate", frame.lattice_certificate),
                    ("lattice_replay", frame.lattice_replay),
                    ("lattice_stage_receipt", frame.lattice_stage_receipt),
                ):
                    if artifact is not None:
                        _verify_artifact(artifact, f"post-parse {name}")
                writer.write(buffer)
                factor_boxes.append(
                    {
                        "t_numerator": t_numerator,
                        "binary64_hex": [value.hex() for value in factor],
                    }
                )
            output_handle.flush()
            if owns_output and not fifo:
                os.fsync(output_handle.fileno())
            if owns_output:
                output_handle.close()
            if temporary is not None:
                assert resolved_output is not None
                os.replace(temporary, resolved_output)
                temporary = None
        except BaseException:
            if owns_output:
                try:
                    output_handle.close()
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
            raise

        elapsed = time.perf_counter() - started
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "schema_version": 1,
            "author": AUTHOR,
            "atom_id": ATOM_ID,
            "algorithm_id": ALGORITHM_ID,
            "checker_id": CHECKER_ID,
            "classification": (
                "certified_residue_composition_adapter_only"
                if job.classification == CERTIFIED_CLASSIFICATION
                else "synthetic_residue_composition_kat_only"
            ),
            "job": {"sha256": job.sha256, "path": str(job.path)},
            "upstream_artifact_merkle_sha256": _input_merkle(job),
            "q": job.q,
            "M": expected_m,
            "first_t_numerator": job.first_t_numerator,
            "t_denominator": job.t_denominator,
            "t_step_numerator": job.t_step_numerator,
            "batch_count": len(job.frames),
            "group_order": plan.order,
            "component_orders": list(plan.component_orders),
            "value_count": value_count,
            "output": {
                "path": output_label if persistent_stream else str(resolved_output),
                "sha256": writer.digest.hexdigest(),
                "size_bytes": writer.size,
                "streamed_fifo": fifo,
                "streamed_framed_service": persistent_stream,
                "magic": ALLCHARS_INPUT_MAGIC.decode("ascii"),
            },
            "q_to_the_minus_s_factors": factor_boxes,
            "factor_backend": {
                "library": "MPFR",
                "version": self.factor_provider.version,
                "precision_bits": self.factor_provider.precision_bits,
                "angle_enclosure": "directed log/mul/div plus global trig Lipschitz bound",
            },
            "composition_backend": {
                "name": self.backend,
                "ieee_binary64_nextafter_outward": True,
                "numpy_version": None if _np is None else str(_np.__version__),
            },
            "bounded_working_set": {
                "frames_resident": 1,
                "binary_interval_payload_bytes": plan.order * COMPLEX_INTERVAL.size,
                "residue_position_bytes": job.q * array("i").itemsize,
                "conservative_backend_payload_bound_bytes": (
                    plan.order * (
                        NUMPY_FRAME_BYTES_PER_VALUE_BOUND
                        if self.backend == "numpy"
                        else COMPLEX_INTERVAL.size
                    )
                    + job.q * array("i").itemsize
                    + 2 * 1024 * 1024
                ),
                "bound_note": (
                    "one-frame binary/maps/vector temporaries; excludes fixed "
                    "Python/NumPy runtime and OS page-cache overhead"
                ),
                "batch_count_bound": self.max_batch_count,
                "campaign_outputs_retained": (
                    False if fifo or persistent_stream else None
                ),
            },
            "elapsed_seconds": elapsed,
            "values_per_second": value_count / elapsed,
            "decisions": {
                "upstream_hashes_verified_before_output": True,
                "exact_q_a_row_t_lockstep_verified": True,
                "certificate_and_replay_chain_verified": (
                    job.classification == CERTIFIED_CLASSIFICATION
                ),
                "outward_interval_composition_completed": True,
                "canonical_crt_residue_order_emitted": True,
                "all_character_fft_completed_here": False,
                "completed_l_phase_completed": False,
                "zero_isolation_completed": False,
                "turing_completeness_completed": False,
                "full_source_run_completed": False,
                "external_atom_discharged": False,
            },
        }
        receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
        if receipt_path is not None:
            _write_atomic_json(receipt_path, receipt)
        return receipt

    def compose_stream(
        self,
        job_path: Path,
        output: BinaryIO,
        *,
        receipt_path: Path | None = None,
        allow_synthetic_kat: bool = False,
        output_label: str = "<framed-stdout>",
    ) -> dict[str, Any]:
        """Append one self-delimiting TGDAFFI1 frame without closing output."""

        return self.compose(
            job_path,
            None,
            receipt_path=receipt_path,
            allow_synthetic_kat=allow_synthetic_kat,
            output_stream=output,
            output_label=output_label,
        )


def source_work(*, batch_size: int = DEFAULT_MAX_BATCH_COUNT) -> dict[str, Any]:
    """Return exact main-grid work and storage facts for this adapter."""

    if batch_size <= 0:
        _fail("batch_size must be positive")
    batch_invocations = sum(
        (maximum_t_index(q) + batch_size) // batch_size
        for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1)
    )
    materialized_bytes = SOURCE_RESIDUE_INTERPOLATIONS * COMPLEX_INTERVAL.size
    return {
        "kind": "sparkinterval.tg.dirichlet_residue_composition.work.v1",
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "main_positive_grid_only": True,
        "modulus_ordinate_factors": SOURCE_Q_T_ROWS,
        "residue_compositions": SOURCE_RESIDUE_INTERPOLATIONS,
        "complex_interval_multiplications": SOURCE_RESIDUE_INTERPOLATIONS,
        "complex_interval_additions": SOURCE_RESIDUE_INTERPOLATIONS,
        "distinct_endpoint_product_candidates": (
            16 * SOURCE_RESIDUE_INTERPOLATIONS
        ),
        "endpoint_addition_or_subtraction_candidates": (
            8 * SOURCE_RESIDUE_INTERPOLATIONS
        ),
        "batch_size": batch_size,
        "batch_invocations": batch_invocations,
        "bytes_if_all_TGDAFFI1_values_were_retained": materialized_bytes,
        "decimal_petabytes_if_retained": materialized_bytes / 1e15,
        "maximum_phi_q": MAXIMUM_GROUP_ORDER,
        "maximum_streamed_batch_bytes": (
            ALLCHARS_INPUT_HEADER.size
            + batch_size * MAXIMUM_GROUP_ORDER * COMPLEX_INTERVAL.size
        ),
        "maximum_live_interval_payload_bytes": (
            MAXIMUM_GROUP_ORDER * COMPLEX_INTERVAL.size
        ),
        "storage_policy": (
            "framed-produce pipes consecutive bounded TGDAFFI1 batches into "
            "allchars --framed-service and retains only compact hash summaries"
        ),
        "excludes": [
            "lattice generation and Taylor reconstruction",
            "all-character transform",
            "completed-L and zero scan",
            "padding, upsampling, exceptional recomputation, and Turing windows",
        ],
    }


def capability() -> dict[str, Any]:
    try:
        provider = MPFRFactorProvider()
        available = True
        version = provider.version
        error = None
    except DirichletResidueCompositionError as exception:
        available = False
        version = None
        error = str(exception)
    return {
        "kind": "sparkinterval.tg.dirichlet_residue_composition.capability.v1",
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "source": SOURCE_URL,
        "algorithm": ALGORITHM_ID,
        "checker": CHECKER_ID,
        "classification": "bounded_residue_composition_adapter_not_atom_closure",
        "component_ready": available,
        "production_ready_for_adapter_only": available,
        "production_ready_for_full_atom": False,
        "full_source_run_completed": False,
        "source_scale_storage_bounded": True,
        "persistent_adapter_service_ready": available,
        "persistent_framed_producer_ready": available,
        "persistent_allchars_framed_service_compatible": available,
        "production_supervisor_wired": False,
        "end_to_end_streaming_supervisor_ready": False,
        "source_scale_performance_validated": False,
        "libmpfr_available": available,
        "libmpfr_version": version,
        "availability_error": error,
        "numpy_vector_backend_available": _np is not None,
        "numpy_version": None if _np is None else str(_np.__version__),
        "accepted_input": [
            "hash-bound TGDLATI1/TGDLATO1/TGDLREC1",
            "lattice certificate manifest plus higher-precision Arb replay report",
            "Taylor-stage exact-checker receipt",
        ],
        "emitted_output": "one or batched TGDAFFI1 in canonical CRT residue order",
        "implemented": [
            "exact q/a/row/t and uniform M lockstep validation",
            "upstream SHA-256 and self-hash chain validation",
            "MPFR-directed q^(-1/2-it) enclosure",
            "outward binary64 complex interval multiply and add",
            "vectorised IEEE-binary64/nextafter backend with scalar fallback",
            "one-frame live payload independent of batch count",
            "named-pipe output and persistent JSONL service",
            "pure concatenated TGDAFFI1 stdout for allchars --framed-service",
            "independent higher-precision MPFR replay checker interface",
        ],
        "not_implemented": [
            "generation or replay of Hurwitz lattice/recovery inputs",
            "Taylor reconstruction itself",
            "all-character FFT execution or verification",
            "completed-L phase and production zero-scan consumer",
            "primitive/conjugate bookkeeping and exceptional recomputation",
            "small-q path, zero isolation, and Turing completeness",
            "full source run or external-atom closure",
            "campaign supervisor launch, backpressure, cancellation, and failure propagation",
            "weighted full-domain throughput validation",
        ],
        "closes_composition_adapter": available,
        "closes_external_atom": False,
    }


def benchmark_synthetic(
    *, q: int, values: int, repetitions: int = 3
) -> dict[str, Any]:
    """Benchmark the hot outward arithmetic without claiming analytic work."""

    if not SOURCE_Q_START <= q <= SOURCE_Q_STOP:
        _fail("benchmark q is outside the large-q range")
    if values <= 0 or repetitions <= 0:
        _fail("benchmark values and repetitions must be positive")
    provider = MPFRFactorProvider()
    factor = provider.factor(q=q, t_numerator=635, t_denominator=64)
    zeta = (-1.125, 0.875, -0.625, 1.375)
    recovery = (-0.25, 0.5, -0.75, 0.125)
    checksum = 0.0
    started = time.perf_counter()
    for _ in range(repetitions):
        for _index in range(values):
            result = compose_interval(zeta, factor, recovery)
            checksum += result[0] + result[3]
    elapsed = time.perf_counter() - started
    operations = values * repetitions
    return {
        "kind": "sparkinterval.tg.dirichlet_residue_composition.benchmark.v1",
        "classification": "synthetic_interval_hot_loop_not_source_runtime",
        "q": q,
        "values_per_repetition": values,
        "repetitions": repetitions,
        "compositions": operations,
        "elapsed_seconds": elapsed,
        "compositions_per_second": operations / elapsed,
        "checksum": checksum,
        "includes": "Python outward complex multiply/add hot loop",
        "excludes": [
            "artifact hashing and parsing",
            "CRT reordering and output I/O",
            "upstream analytic stages and downstream transform",
        ],
    }


__all__ = [
    "ALGORITHM_ID",
    "CERTIFIED_CLASSIFICATION",
    "CHECKER_ID",
    "CompositionEngine",
    "DEFAULT_FACTOR_PRECISION_BITS",
    "DEFAULT_MAX_BATCH_COUNT",
    "DirichletResidueCompositionError",
    "FRAMED_REQUEST_SCHEMA",
    "JOB_SCHEMA",
    "MPFRFactorProvider",
    "RECEIPT_SCHEMA",
    "SERVICE_REQUEST_SCHEMA",
    "SYNTHETIC_CLASSIFICATION",
    "artifact_record",
    "benchmark_synthetic",
    "capability",
    "canonical_json_bytes",
    "compose_interval",
    "load_job",
    "sha256_file",
    "source_work",
]

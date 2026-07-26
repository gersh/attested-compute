# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Certified inputs for Platt's conditional large-q Hurwitz lattice stage.

This module deliberately has a narrow trust claim.  Pinned Arb/FLINT computes
rectangles for the source-shaped ``zeta_M`` lattice and for the finite terms
which must be added back after the unit-group transform.  A separate exact
rational derivation supplies one Taylor-tail radius valid for every request in
the batch.  A replay invocation regenerates every analytic rectangle at higher
precision and checks containment.

The resulting bundle is useful input to the large-q arithmetic stages.  It is
not a zero-isolation certificate, a Turing count, or a proof of Platt's
Theorem 7.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import stat
import struct
import sys
import tempfile
import time
from typing import Any, Iterator, NoReturn

from tg_verifier.dirichlet_lattice_stage import (
    ATOM_ID,
    FORMAT_VERSION as LATTICE_FORMAT_VERSION,
    INPUT_HEADER,
    INPUT_ITEM,
    INPUT_MAGIC,
    LATTICE_CELL,
    LATTICE_ROWS,
    SOURCE_MAX_T_INDEX,
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    TAYLOR_COLUMNS,
    TAYLOR_DEGREE,
    canonical_lattice_row,
    maximum_t_index,
)


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "platt-dirichlet-certified-lattice-input-v1"
CHECKER_ID = "higher-precision-flint-plus-exact-rational-tail-v1"
MANIFEST_SCHEMA = "sparkinterval.tg.dirichlet_lattice_certificate.v1"
REPLAY_SCHEMA = "sparkinterval.tg.dirichlet_lattice_certificate.replay.v1"

SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
SOURCE_TEX_SHA256 = "38576ae4b275c477fb07cfd6c5e46a4dec9a4aa5268a56747f3bab8eec8f79f5"
SOURCE_PDF_SHA256 = "8fd109aa21345bc3feac4fde2faa7dfb51b4ef1fc9a430f643323612a39ef417"

EXPECTED_PYTHON_FLINT = "0.9.0"
EXPECTED_FLINT = "3.6.0"
EXPECTED_FLINT_RELEASE = 30_600
MINIMUM_PRECISION_BITS = 128
DEFAULT_PRECISION_BITS = 192
DEFAULT_REPLAY_GUARD_BITS = 64

LATTICE_FILENAME = "lattice-input.bin"
RECOVERY_FILENAME = "finite-recovery.bin"
MANIFEST_FILENAME = "certificate.json"

RECOVERY_MAGIC = b"TGDLREC1"
RECOVERY_FORMAT_VERSION = 1
RECOVERY_HEADER = struct.Struct("<8sIIIqQQQ")
RECOVERY_ITEM = struct.Struct("<IIIIdddd")

SOURCE_MAPPING = [
    {
        "paper": "Section 4, Lemma 4.1",
        "artifact": "unit-group DFT receives one value per unit residue",
    },
    {
        "paper": "Section 4.1, page 7",
        "artifact": "D=2048 rows, columns c=0,...,15 at s=1/2+it+c",
    },
    {
        "paper": "Lemma 4.2",
        "artifact": "Taylor identity and strict |delta|<alpha request guard",
    },
    {
        "paper": "paragraph immediately after Lemma 4.2",
        "artifact": "zeta_M subtracts n=0,...,M and finite-recovery adds them back",
    },
]
TAIL_SOURCE_NOTE = (
    "The analogous tail lemmas are commented out of the v1 TeX and absent "
    "from the rendered paper. The stored tail is a project-derived exact "
    "rational majorant, not a quoted Platt lemma."
)
REQUEST_ENUMERATION = (
    "ascending q, then ascending a with gcd(a,q)=1; inactive "
    "q at this source-grid ordinate are omitted"
)
RECOVERY_SEMANTICS = (
    "R_M(s;q,a)=sum_{n=0}^M (q*n+a)^(-s), so "
    "L(s,chi)=sum_a chi(a)*(q^(-s)*zeta_M(s,a/q)+R_M(s;q,a))"
)
DECISIONS = {
    "pinned_arb_flint_seed_rectangles_generated": True,
    "dual_precision_seed_union_generated": True,
    "finite_term_recovery_rectangles_generated": True,
    "strict_taylor_hypotheses_checked": True,
    "exact_rational_uniform_tail_derived": True,
    "all_character_fft_completed": False,
    "completed_L_phase_completed": False,
    "zero_isolation_completed": False,
    "turing_completeness_completed": False,
    "external_atom_discharged": False,
}


class DirichletLatticeCertificateError(RuntimeError):
    """The producer, artifact, runtime, or semantic replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletLatticeCertificateError(message)


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


def _artifact(path: Path) -> dict[str, Any]:
    digest, size = sha256_file(path)
    return {"sha256": digest, "size_bytes": size}


def _source_record() -> dict[str, Any]:
    return {
        "url": SOURCE_URL,
        "arxiv_version": "v1",
        "tex_sha256": SOURCE_TEX_SHA256,
        "pdf_sha256": SOURCE_PDF_SHA256,
        "mapping": SOURCE_MAPPING,
        "important_tail_note": TAIL_SOURCE_NOTE,
    }


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _load_flint() -> Any:
    try:
        import flint  # type: ignore[import-not-found]
    except ImportError as error:
        _fail(
            "python-flint==0.9.0 (bundling FLINT 3.6.0) is required for "
            "certified lattice generation and semantic replay"
        )
    if (
        str(flint.__version__) != EXPECTED_PYTHON_FLINT
        or str(flint.__FLINT_VERSION__) != EXPECTED_FLINT
        or int(flint.__FLINT_RELEASE__) != EXPECTED_FLINT_RELEASE
    ):
        _fail(
            "runtime mismatch: expected python-flint 0.9.0 / FLINT 3.6.0 "
            "release 30600"
        )
    return flint


def _extension_path(root: Path, relative_parent: str, stem: str) -> Path:
    candidates = sorted((root / relative_parent).glob(f"{stem}.*.so"))
    if len(candidates) != 1:
        _fail(f"cannot uniquely identify the python-flint extension {stem}")
    return candidates[0]


def runtime_identity(flint: Any | None = None) -> dict[str, Any]:
    """Return path-independent hashes for the executable and loaded Arb stack."""

    flint = _load_flint() if flint is None else flint
    root = Path(flint.__file__).resolve().parent
    extension_specs = {
        "pyflint": ("", "pyflint"),
        "flint_context": ("flint_base", "flint_context"),
        "acb": ("types", "acb"),
        "arb": ("types", "arb"),
        "arf": ("types", "arf"),
        "fmpq": ("types", "fmpq"),
        "fmpz": ("types", "fmpz"),
    }
    extensions: dict[str, Any] = {}
    for logical_name, (parent, stem) in extension_specs.items():
        path = _extension_path(root, parent, stem)
        digest, size = sha256_file(path)
        extensions[logical_name] = {
            "filename": path.name,
            "sha256": digest,
            "size_bytes": size,
        }
    executable = Path(sys.executable).resolve()
    executable_hash, executable_size = sha256_file(executable)
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_executable": {
            "filename": executable.name,
            "sha256": executable_hash,
            "size_bytes": executable_size,
        },
        "python_flint_version": str(flint.__version__),
        "flint_version": str(flint.__FLINT_VERSION__),
        "flint_release": int(flint.__FLINT_RELEASE__),
        "machine": platform.machine(),
        "extensions": extensions,
        "flint_threads": 1,
    }


def _fraction_record(value: Fraction) -> dict[str, str]:
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _fraction_from_record(value: object, label: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        _fail(f"{label} is not a canonical rational record")
    try:
        numerator = int(value["numerator"])
        denominator = int(value["denominator"])
    except (TypeError, ValueError) as error:
        raise DirichletLatticeCertificateError(
            f"{label} has a non-integer numerator or denominator"
        ) from error
    if denominator <= 0 or str(numerator) != value["numerator"] or str(denominator) != value["denominator"]:
        _fail(f"{label} is not canonically encoded")
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        _fail(f"{label} is not reduced")
    return result


def _downward_binary64(value: Fraction) -> float:
    result = float(value)
    if not math.isfinite(result):
        _fail("analytic interval endpoint overflows binary64")
    while Fraction.from_float(result) > value:
        result = math.nextafter(result, -math.inf)
    while True:
        next_value = math.nextafter(result, math.inf)
        if not math.isfinite(next_value) or Fraction.from_float(next_value) > value:
            return result
        result = next_value


def _upward_binary64(value: Fraction) -> float:
    result = float(value)
    if not math.isfinite(result):
        _fail("analytic interval endpoint overflows binary64")
    while Fraction.from_float(result) < value:
        result = math.nextafter(result, math.inf)
    while True:
        previous = math.nextafter(result, -math.inf)
        if not math.isfinite(previous) or Fraction.from_float(previous) < value:
            return result
        result = previous


def _exact_arb_endpoint(value: Any, *, lower: bool) -> Fraction:
    endpoint = value.lower() if lower else value.upper()
    if not endpoint.is_exact():
        _fail("Arb did not expose an exact finite endpoint")
    rational = endpoint.fmpq()
    return Fraction(int(rational.p), int(rational.q))


def _binary64_box(value: Any) -> tuple[float, float, float, float]:
    if not value.is_finite():
        _fail("Arb returned a non-finite complex enclosure")
    re_lo = _downward_binary64(_exact_arb_endpoint(value.real, lower=True))
    re_hi = _upward_binary64(_exact_arb_endpoint(value.real, lower=False))
    im_lo = _downward_binary64(_exact_arb_endpoint(value.imag, lower=True))
    im_hi = _upward_binary64(_exact_arb_endpoint(value.imag, lower=False))
    if not (re_lo <= re_hi and im_lo <= im_hi):
        _fail("outward binary64 conversion produced a reversed rectangle")
    return re_lo, re_hi, im_lo, im_hi


def _contains_arb(box: tuple[float, float, float, float], value: Any) -> bool:
    if not value.is_finite() or not all(math.isfinite(endpoint) for endpoint in box):
        return False
    re_lo, re_hi, im_lo, im_hi = (Fraction.from_float(endpoint) for endpoint in box)
    return (
        re_lo <= _exact_arb_endpoint(value.real, lower=True)
        and re_hi >= _exact_arb_endpoint(value.real, lower=False)
        and im_lo <= _exact_arb_endpoint(value.imag, lower=True)
        and im_hi >= _exact_arb_endpoint(value.imag, lower=False)
    )


@dataclass(frozen=True)
class Request:
    q: int
    a: int
    row: int


def _validate_batch_parameters(
    *, q_start: int, q_stop: int, t_index: int, m: int,
    precision_bits: int, max_items: int | None,
) -> None:
    if not SOURCE_Q_START <= q_start <= q_stop <= SOURCE_Q_STOP:
        _fail("q range is outside Platt's large-q source stage")
    if not 0 <= t_index <= SOURCE_MAX_T_INDEX:
        _fail("t_index is outside the fixed 5/64 source grid")
    if m < 1:
        _fail("M must be positive, matching the source's M in Z_{>0}")
    if precision_bits < MINIMUM_PRECISION_BITS:
        _fail(f"precision_bits must be at least {MINIMUM_PRECISION_BITS}")
    if max_items is not None and max_items <= 0:
        _fail("max_items must be positive")


def iter_requests(
    *, q_start: int, q_stop: int, t_index: int,
    max_items: int | None = None,
) -> Iterator[Request]:
    emitted = 0
    for q in range(q_start, q_stop + 1):
        if t_index > maximum_t_index(q):
            continue
        for a in range(1, q):
            if math.gcd(a, q) != 1:
                continue
            yield Request(q, a, canonical_lattice_row(q, a))
            emitted += 1
            if max_items is not None and emitted == max_items:
                return


def _request_scan(
    *, q_start: int, q_stop: int, t_index: int, max_items: int | None,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    maximum_delta = Fraction(0)
    first: Request | None = None
    last: Request | None = None
    for request in iter_requests(
        q_start=q_start, q_stop=q_stop, t_index=t_index, max_items=max_items
    ):
        identity = struct.pack("<III", request.q, request.a, request.row)
        digest.update(identity)
        delta = abs(
            Fraction(request.a, request.q) - Fraction(request.row, LATTICE_ROWS)
        )
        alpha = Fraction(request.row, LATTICE_ROWS)
        if not delta < alpha:
            _fail("canonical request violates Lemma 4.2's strict |delta| < alpha")
        maximum_delta = max(maximum_delta, delta)
        first = first or request
        last = request
        count += 1
    if count == 0 or first is None or last is None:
        _fail("source-shaped batch contains no active unit residues")
    return {
        "count": count,
        "sha256_le_u32_q_a_row": digest.hexdigest(),
        "maximum_abs_delta": maximum_delta,
        "first": first,
        "last": last,
    }


def derive_uniform_tail_bound(
    *, t_index: int, m: int, maximum_abs_delta: Fraction,
) -> dict[str, Any]:
    """Derive an exact rational remainder bound after columns 0 through 15.

    This is intentionally not attributed to an active lemma in the paper: the
    analogous numerical lemmas are commented out in the arXiv TeX source.  For
    K=N+1, absolute convergence of the zeta_M Dirichlet series at s+K gives an
    integral-test bound on the first omitted coefficient.  Successive absolute
    Taylor terms are then bounded by a geometric ratio.
    """

    if not 0 <= t_index <= SOURCE_MAX_T_INDEX or m < 1:
        _fail("invalid parameters for the uniform Taylor bound")
    # Interior nearest rows are within 1/(2D).  Because the paper's lattice
    # starts at r=1 rather than r=0, the clipped left edge can approach 1/D.
    if maximum_abs_delta < 0 or maximum_abs_delta >= Fraction(1, LATTICE_ROWS):
        _fail("maximum_abs_delta exceeds clipped nearest-lattice geometry")

    t = Fraction(SOURCE_SAMPLE_NUMERATOR * t_index, SOURCE_SAMPLE_DENOMINATOR)
    k = TAYLOR_DEGREE + 1
    base = m + 1

    # For p=K+1/2 and A=M+1+alpha >= B=M+1,
    #   sum_{n=M+1}^infty (n+alpha)^-p
    #     <= A^-p + A^(1-p)/(p-1)
    #     <= B^-K + 2 B^{-(K-1)}/(2K-1).
    zeta_tail_majorant = Fraction(1, base**k) + Fraction(
        2, (2 * k - 1) * base ** (k - 1)
    )

    # sqrt(t^2+(j+1/2)^2) <= t+j+1/2 for t,j >= 0.
    pochhammer_majorant = Fraction(1)
    for j in range(k):
        pochhammer_majorant *= t + Fraction(2 * j + 1, 2)

    first_omitted_majorant = (
        maximum_abs_delta**k
        * pochhammer_majorant
        * zeta_tail_majorant
        / math.factorial(k)
    )

    norm_bound = t + Fraction(1, 2)
    ratio_factor = max(Fraction(1), (norm_bound + k) / (k + 1))
    ratio_majorant = maximum_abs_delta * ratio_factor / base
    if ratio_majorant >= 1:
        _fail("derived Taylor geometric ratio is not strictly below one")
    remainder = first_omitted_majorant / (1 - ratio_majorant)
    radius = _upward_binary64(remainder)
    if Fraction.from_float(radius) < remainder:
        _fail("Taylor radius was not rounded upward")
    return {
        "classification": "project_derived_exact_rational_bound_not_active_paper_lemma",
        "taylor_columns_retained": TAYLOR_COLUMNS,
        "first_omitted_index_K": k,
        "M": m,
        "maximum_abs_delta": _fraction_record(maximum_abs_delta),
        "zeta_tail_majorant": _fraction_record(zeta_tail_majorant),
        "pochhammer_majorant": _fraction_record(pochhammer_majorant),
        "first_omitted_majorant": _fraction_record(first_omitted_majorant),
        "geometric_ratio_majorant": _fraction_record(ratio_majorant),
        "remainder_majorant": _fraction_record(remainder),
        "binary64_radius_hex": radius.hex(),
        "derivation": [
            "Write zeta_M as its absolutely convergent Dirichlet series at s+K.",
            "Apply the decreasing-function integral test to the first omitted coefficient.",
            "Use |s+j| <= t+j+1/2 and M+1+alpha >= M+1.",
            "Majorize every successive absolute Taylor term by the stored ratio < 1.",
            "Sum the resulting geometric series and round the rational result upward to binary64.",
        ],
    }


def _source_s(flint: Any, *, t_index: int, column: int = 0) -> Any:
    real = flint.arb(2 * column + 1) / 2
    imag = flint.arb(SOURCE_SAMPLE_NUMERATOR * t_index) / SOURCE_SAMPLE_DENOMINATOR
    return flint.acb(real, imag)


def _zeta_m_generate(flint: Any, *, t_index: int, row: int, column: int, m: int) -> Any:
    s = _source_s(flint, t_index=t_index, column=column)
    alpha = flint.arb(row) / LATTICE_ROWS
    result = s.zeta(alpha)
    for n in range(m + 1):
        result -= flint.acb(alpha + n) ** (-s)
    return result


def _pairwise_sum(values: list[Any], zero: Any) -> Any:
    if not values:
        return zero
    current = values
    while len(current) > 1:
        next_level: list[Any] = []
        for index in range(0, len(current), 2):
            if index + 1 == len(current):
                next_level.append(current[index])
            else:
                next_level.append(current[index] + current[index + 1])
        current = next_level
    return current[0]


def _zeta_m_replay(flint: Any, *, t_index: int, row: int, column: int, m: int) -> Any:
    # Deliberately use a separately structured pairwise subtraction path.
    s = _source_s(flint, t_index=t_index, column=column)
    alpha = flint.arb(row) / LATTICE_ROWS
    finite = _pairwise_sum(
        [flint.acb(alpha + n) ** (-s) for n in range(m, -1, -1)],
        flint.acb(0),
    )
    return s.zeta(alpha) - finite


def _finite_recovery_generate(
    flint: Any, *, t_index: int, request: Request, m: int,
) -> Any:
    s = _source_s(flint, t_index=t_index)
    result = flint.acb(0)
    for n in range(m + 1):
        # q^-s (n+a/q)^-s = (qn+a)^-s.
        result += flint.acb(request.q * n + request.a) ** (-s)
    return result


def _finite_recovery_replay(
    flint: Any, *, t_index: int, request: Request, m: int,
) -> Any:
    s = _source_s(flint, t_index=t_index)
    return _pairwise_sum(
        [
            flint.acb(request.q * n + request.a) ** (-s)
            for n in range(m, -1, -1)
        ],
        flint.acb(0),
    )


def _dual_precision_box(
    flint: Any, compute: Any, *, precision_bits: int,
) -> tuple[float, float, float, float]:
    with flint.ctx.workprec(precision_bits):
        first = compute()
    with flint.ctx.workprec(precision_bits + DEFAULT_REPLAY_GUARD_BITS):
        second = compute()
        # Unioning the independently rounded precision runs makes subsequent
        # higher-precision containment replay robust without narrowing either
        # Arb enclosure. Keep the union precision explicit rather than relying
        # on the caller's global context.
        joined = flint.acb(
            first.real.union(second.real), first.imag.union(second.imag)
        )
        return _binary64_box(joined)


def _write_lattice_input(
    path: Path,
    *,
    flint: Any,
    q_start: int,
    q_stop: int,
    t_index: int,
    m: int,
    precision_bits: int,
    max_items: int | None,
    request_scan: dict[str, Any],
    tail_radius: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    with path.open("wb") as output:
        output.write(
            INPUT_HEADER.pack(
                INPUT_MAGIC,
                LATTICE_FORMAT_VERSION,
                LATTICE_ROWS,
                TAYLOR_DEGREE,
                0,
                SOURCE_SAMPLE_NUMERATOR * t_index,
                SOURCE_SAMPLE_DENOMINATOR,
                request_scan["count"],
                LATTICE_ROWS * TAYLOR_COLUMNS,
                0,
            )
        )
        for row in range(1, LATTICE_ROWS + 1):
            for column in range(TAYLOR_COLUMNS):
                box = _dual_precision_box(
                    flint,
                    lambda row=row, column=column: _zeta_m_generate(
                        flint,
                        t_index=t_index,
                        row=row,
                        column=column,
                        m=m,
                    ),
                    precision_bits=precision_bits,
                )
                output.write(LATTICE_CELL.pack(*box))
        emitted = 0
        for request in iter_requests(
            q_start=q_start,
            q_stop=q_stop,
            t_index=t_index,
            max_items=max_items,
        ):
            output.write(
                INPUT_ITEM.pack(
                    request.q, request.a, request.row, 0, tail_radius
                )
            )
            emitted += 1
        if emitted != request_scan["count"]:
            _fail("request count changed while writing the lattice input")
        output.flush()
        os.fsync(output.fileno())
    return {
        **_artifact(path),
        "lattice_cells": LATTICE_ROWS * TAYLOR_COLUMNS,
        "request_count": emitted,
        "elapsed_seconds": time.perf_counter() - started,
    }


def _write_recovery_input(
    path: Path,
    *,
    flint: Any,
    q_start: int,
    q_stop: int,
    t_index: int,
    m: int,
    precision_bits: int,
    max_items: int | None,
    request_scan: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    digest = hashlib.sha256()
    with path.open("wb") as output:
        output.write(
            RECOVERY_HEADER.pack(
                RECOVERY_MAGIC,
                RECOVERY_FORMAT_VERSION,
                m,
                0,
                SOURCE_SAMPLE_NUMERATOR * t_index,
                SOURCE_SAMPLE_DENOMINATOR,
                request_scan["count"],
                0,
            )
        )
        emitted = 0
        for request in iter_requests(
            q_start=q_start,
            q_stop=q_stop,
            t_index=t_index,
            max_items=max_items,
        ):
            digest.update(struct.pack("<III", request.q, request.a, request.row))
            box = _dual_precision_box(
                flint,
                lambda request=request: _finite_recovery_generate(
                    flint, t_index=t_index, request=request, m=m
                ),
                precision_bits=precision_bits,
            )
            output.write(RECOVERY_ITEM.pack(request.q, request.a, 0, 0, *box))
            emitted += 1
        if emitted != request_scan["count"]:
            _fail("request count changed while writing finite recovery")
        if digest.hexdigest() != request_scan["sha256_le_u32_q_a_row"]:
            _fail("finite-recovery request identity changed")
        output.flush()
        os.fsync(output.fileno())
    return {
        **_artifact(path),
        "request_count": emitted,
        "elapsed_seconds": time.perf_counter() - started,
        "value_semantics": RECOVERY_SEMANTICS,
    }


def generate_certificate(
    root: Path,
    *,
    q_start: int,
    q_stop: int,
    t_index: int,
    m: int,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Generate one immutable source-shaped lattice/recovery input bundle."""

    _validate_batch_parameters(
        q_start=q_start,
        q_stop=q_stop,
        t_index=t_index,
        m=m,
        precision_bits=precision_bits,
        max_items=max_items,
    )
    if root.exists():
        _fail(f"refusing to replace immutable certificate root: {root}")
    flint = _load_flint()
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    temporary = root.parent / f".{root.name}.tmp.{os.getpid()}"
    if temporary.exists():
        _fail(f"temporary certificate root already exists: {temporary}")
    temporary.mkdir(parents=True)
    try:
        scan = _request_scan(
            q_start=q_start,
            q_stop=q_stop,
            t_index=t_index,
            max_items=max_items,
        )
        tail = derive_uniform_tail_bound(
            t_index=t_index,
            m=m,
            maximum_abs_delta=scan["maximum_abs_delta"],
        )
        tail_radius = float.fromhex(tail["binary64_radius_hex"])
        lattice_report = _write_lattice_input(
            temporary / LATTICE_FILENAME,
            flint=flint,
            q_start=q_start,
            q_stop=q_stop,
            t_index=t_index,
            m=m,
            precision_bits=precision_bits,
            max_items=max_items,
            request_scan=scan,
            tail_radius=tail_radius,
        )
        recovery_report = _write_recovery_input(
            temporary / RECOVERY_FILENAME,
            flint=flint,
            q_start=q_start,
            q_stop=q_stop,
            t_index=t_index,
            m=m,
            precision_bits=precision_bits,
            max_items=max_items,
            request_scan=scan,
        )
        implementation = _artifact(Path(__file__).resolve())
        first: Request = scan["first"]
        last: Request = scan["last"]
        manifest: dict[str, Any] = {
            "schema": MANIFEST_SCHEMA,
            "schema_version": 1,
            "author": AUTHOR,
            "atom_id": ATOM_ID,
            "algorithm_id": ALGORITHM_ID,
            "checker_id": CHECKER_ID,
            "classification": (
                "sample_certified_analytic_input_not_theorem_7_1"
                if max_items is not None
                else "source_shaped_certified_analytic_batch_not_theorem_7_1"
            ),
            "source": _source_record(),
            "parameters": {
                "q_start_inclusive": q_start,
                "q_stop_inclusive": q_stop,
                "t_index": t_index,
                "t": _fraction_record(
                    Fraction(
                        SOURCE_SAMPLE_NUMERATOR * t_index,
                        SOURCE_SAMPLE_DENOMINATOR,
                    )
                ),
                "D": LATTICE_ROWS,
                "N": TAYLOR_DEGREE,
                "columns": TAYLOR_COLUMNS,
                "M": m,
                "generation_precision_bits": precision_bits,
                "second_generation_precision_bits": (
                    precision_bits + DEFAULT_REPLAY_GUARD_BITS
                ),
                "max_items": max_items,
            },
            "requests": {
                "count": scan["count"],
                "sha256_le_u32_q_a_row": scan["sha256_le_u32_q_a_row"],
                "first": {"q": first.q, "a": first.a, "row": first.row},
                "last": {"q": last.q, "a": last.a, "row": last.row},
                "enumeration": REQUEST_ENUMERATION,
            },
            "uniform_taylor_tail": tail,
            "artifacts": {
                LATTICE_FILENAME: lattice_report,
                RECOVERY_FILENAME: recovery_report,
                "producer_module": implementation,
            },
            "generator_runtime": runtime_identity(flint),
            "decisions": DECISIONS,
        }
        # Elapsed timings are observations and are intentionally covered by the
        # immutable certificate hash along with the mathematical inputs.
        manifest["certificate_sha256"] = sha256_bytes(canonical_json_bytes(manifest))
        _write_atomic(temporary / MANIFEST_FILENAME, canonical_json_bytes(manifest))
        for artifact_path in temporary.iterdir():
            artifact_path.chmod(stat.S_IRUSR)
        os.replace(temporary, root)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        flint.ctx.threads = old_threads


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_FILENAME
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise DirichletLatticeCertificateError("cannot read certificate manifest") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail("certificate manifest is not canonical JSON")
    expected = value.get("certificate_sha256")
    body = dict(value)
    body.pop("certificate_sha256", None)
    if not isinstance(expected, str) or expected != sha256_bytes(canonical_json_bytes(body)):
        _fail("certificate manifest self-hash mismatch")
    if value.get("schema") != MANIFEST_SCHEMA or value.get("schema_version") != 1:
        _fail("certificate manifest schema mismatch")
    required = {
        "schema", "schema_version", "author", "atom_id", "algorithm_id",
        "checker_id", "classification", "source", "parameters", "requests",
        "uniform_taylor_tail", "artifacts", "generator_runtime", "decisions",
        "certificate_sha256",
    }
    if set(value) != required:
        _fail("certificate manifest fields changed")
    if value.get("author") != AUTHOR:
        _fail("certificate author identity mismatch")
    if value.get("algorithm_id") != ALGORITHM_ID or value.get("checker_id") != CHECKER_ID:
        _fail("certificate algorithm identity mismatch")
    if value.get("atom_id") != ATOM_ID:
        _fail("certificate atom identity mismatch")
    if value.get("source") != _source_record():
        _fail("certificate source mapping changed")
    if value.get("decisions") != DECISIONS:
        _fail("certificate trust-boundary decisions changed")
    return value


def _validate_runtime_record(value: object, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {
        "python_implementation", "python_version", "python_executable",
        "python_flint_version", "flint_version", "flint_release", "machine",
        "extensions", "flint_threads",
    }:
        _fail(f"{label} is malformed")
    if (
        value["python_flint_version"] != EXPECTED_PYTHON_FLINT
        or value["flint_version"] != EXPECTED_FLINT
        or value["flint_release"] != EXPECTED_FLINT_RELEASE
        or value["flint_threads"] != 1
    ):
        _fail(f"{label} does not bind the pinned single-threaded FLINT runtime")
    if not isinstance(value["python_implementation"], str) or not isinstance(
        value["python_version"], str
    ) or not isinstance(value["machine"], str):
        _fail(f"{label} platform identity is malformed")
    executable = value["python_executable"]
    if not isinstance(executable, dict) or set(executable) != {
        "filename", "sha256", "size_bytes"
    }:
        _fail(f"{label} executable identity is malformed")
    extensions = value["extensions"]
    expected_extensions = {
        "pyflint", "flint_context", "acb", "arb", "arf", "fmpq", "fmpz"
    }
    if not isinstance(extensions, dict) or set(extensions) != expected_extensions:
        _fail(f"{label} extension closure is malformed")
    for name, record in {"python_executable": executable, **extensions}.items():
        if not isinstance(record, dict) or set(record) != {
            "filename", "sha256", "size_bytes"
        }:
            _fail(f"{label}.{name} identity is malformed")
        digest = record["sha256"]
        if (
            not isinstance(record["filename"], str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or type(record["size_bytes"]) is not int
            or record["size_bytes"] <= 0
        ):
            _fail(f"{label}.{name} identity is invalid")


def _manifest_parameters(manifest: dict[str, Any]) -> dict[str, Any]:
    parameters = manifest.get("parameters")
    if not isinstance(parameters, dict):
        _fail("certificate parameters are missing")
    required = {
        "q_start_inclusive", "q_stop_inclusive", "t_index", "t", "D", "N",
        "columns", "M", "generation_precision_bits",
        "second_generation_precision_bits", "max_items",
    }
    if set(parameters) != required:
        _fail("certificate parameter fields changed")
    for name in (
        "q_start_inclusive", "q_stop_inclusive", "t_index", "D", "N", "columns",
        "M", "generation_precision_bits", "second_generation_precision_bits",
    ):
        if type(parameters[name]) is not int:
            _fail(f"certificate parameter {name} is not an integer")
    max_items = parameters["max_items"]
    if max_items is not None and type(max_items) is not int:
        _fail("certificate max_items is malformed")
    _validate_batch_parameters(
        q_start=parameters["q_start_inclusive"],
        q_stop=parameters["q_stop_inclusive"],
        t_index=parameters["t_index"],
        m=parameters["M"],
        precision_bits=parameters["generation_precision_bits"],
        max_items=max_items,
    )
    if (
        parameters["D"] != LATTICE_ROWS
        or parameters["N"] != TAYLOR_DEGREE
        or parameters["columns"] != TAYLOR_COLUMNS
        or parameters["second_generation_precision_bits"]
        != parameters["generation_precision_bits"] + DEFAULT_REPLAY_GUARD_BITS
    ):
        _fail("certificate lattice or precision parameters changed")
    t = _fraction_from_record(parameters["t"], "parameters.t")
    expected_t = Fraction(
        SOURCE_SAMPLE_NUMERATOR * parameters["t_index"],
        SOURCE_SAMPLE_DENOMINATOR,
    )
    if t != expected_t:
        _fail("certificate t does not match its exact source-grid index")
    return parameters


def _require_artifact(manifest: dict[str, Any], root: Path, name: str) -> Path:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or name not in artifacts:
        _fail(f"certificate does not bind {name}")
    record = artifacts[name]
    if not isinstance(record, dict):
        _fail(f"certificate artifact record for {name} is malformed")
    path = root / name
    actual_hash, actual_size = sha256_file(path)
    if record.get("sha256") != actual_hash or record.get("size_bytes") != actual_size:
        _fail(f"certificate artifact mismatch for {name}")
    return path


def _read_lattice_input(
    path: Path,
    *,
    parameters: dict[str, Any],
    expected_scan: dict[str, Any],
) -> tuple[list[tuple[float, float, float, float]], list[Request], float]:
    with path.open("rb") as source:
        raw = source.read(INPUT_HEADER.size)
        if len(raw) != INPUT_HEADER.size:
            _fail("short lattice-input header")
        (
            magic, version, rows, degree, reserved0, t_numerator,
            t_denominator, item_count, lattice_count, reserved1,
        ) = INPUT_HEADER.unpack(raw)
        if (
            magic != INPUT_MAGIC
            or version != LATTICE_FORMAT_VERSION
            or rows != LATTICE_ROWS
            or degree != TAYLOR_DEGREE
            or reserved0 != 0
            or reserved1 != 0
            or t_numerator != SOURCE_SAMPLE_NUMERATOR * parameters["t_index"]
            or t_denominator != SOURCE_SAMPLE_DENOMINATOR
            or item_count != expected_scan["count"]
            or lattice_count != LATTICE_ROWS * TAYLOR_COLUMNS
        ):
            _fail("lattice-input header does not match the certificate")
        expected_size = (
            INPUT_HEADER.size
            + lattice_count * LATTICE_CELL.size
            + item_count * INPUT_ITEM.size
        )
        if path.stat().st_size != expected_size:
            _fail("lattice-input length is not canonical")
        cells = []
        for _ in range(lattice_count):
            payload = source.read(LATTICE_CELL.size)
            if len(payload) != LATTICE_CELL.size:
                _fail("short lattice-cell payload")
            box = LATTICE_CELL.unpack(payload)
            if (
                not all(math.isfinite(value) for value in box)
                or box[0] > box[1]
                or box[2] > box[3]
            ):
                _fail("invalid lattice-cell rectangle")
            cells.append(box)
        requests = []
        radius: float | None = None
        expected_iterator = iter_requests(
            q_start=parameters["q_start_inclusive"],
            q_stop=parameters["q_stop_inclusive"],
            t_index=parameters["t_index"],
            max_items=parameters["max_items"],
        )
        for expected in expected_iterator:
            payload = source.read(INPUT_ITEM.size)
            if len(payload) != INPUT_ITEM.size:
                _fail("short lattice request payload")
            q, a, row, reserved, item_radius = INPUT_ITEM.unpack(payload)
            if (q, a, row) != (expected.q, expected.a, expected.row) or reserved != 0:
                _fail("lattice request sequence is not canonical")
            if not math.isfinite(item_radius) or item_radius < 0:
                _fail("lattice request has an invalid Taylor radius")
            radius = item_radius if radius is None else radius
            if item_radius != radius:
                _fail("lattice requests do not share the certified uniform radius")
            requests.append(expected)
        if len(requests) != item_count or source.read(1):
            _fail("lattice request count or trailing bytes mismatch")
    if radius is None:
        _fail("lattice input contains no radius")
    return cells, requests, radius


def _read_recovery_input(
    path: Path,
    *,
    parameters: dict[str, Any],
    requests: list[Request],
) -> list[tuple[float, float, float, float]]:
    with path.open("rb") as source:
        raw = source.read(RECOVERY_HEADER.size)
        if len(raw) != RECOVERY_HEADER.size:
            _fail("short finite-recovery header")
        magic, version, m, reserved0, t_numerator, t_denominator, count, reserved1 = (
            RECOVERY_HEADER.unpack(raw)
        )
        if (
            magic != RECOVERY_MAGIC
            or version != RECOVERY_FORMAT_VERSION
            or m != parameters["M"]
            or reserved0 != 0
            or reserved1 != 0
            or t_numerator != SOURCE_SAMPLE_NUMERATOR * parameters["t_index"]
            or t_denominator != SOURCE_SAMPLE_DENOMINATOR
            or count != len(requests)
            or path.stat().st_size != RECOVERY_HEADER.size + count * RECOVERY_ITEM.size
        ):
            _fail("finite-recovery header or length mismatch")
        boxes = []
        for expected in requests:
            payload = source.read(RECOVERY_ITEM.size)
            if len(payload) != RECOVERY_ITEM.size:
                _fail("short finite-recovery payload")
            q, a, reserved_a, reserved_b, *box_values = RECOVERY_ITEM.unpack(payload)
            box = tuple(box_values)
            if (
                (q, a) != (expected.q, expected.a)
                or reserved_a != 0
                or reserved_b != 0
                or not all(math.isfinite(value) for value in box)
                or box[0] > box[1]
                or box[2] > box[3]
            ):
                _fail("finite-recovery identity or rectangle mismatch")
            boxes.append(box)
        if source.read(1):
            _fail("trailing finite-recovery bytes")
    return boxes


def replay_certificate(
    root: Path,
    *,
    replay_precision_bits: int | None = None,
) -> dict[str, Any]:
    """Structurally and semantically replay every value in a bundle."""

    manifest = _load_manifest(root)
    parameters = _manifest_parameters(manifest)
    expected_classification = (
        "sample_certified_analytic_input_not_theorem_7_1"
        if parameters["max_items"] is not None
        else "source_shaped_certified_analytic_batch_not_theorem_7_1"
    )
    if manifest.get("classification") != expected_classification:
        _fail("certificate classification does not match its truncation status")
    _validate_runtime_record(manifest.get("generator_runtime"), "generator_runtime")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        LATTICE_FILENAME, RECOVERY_FILENAME, "producer_module"
    }:
        _fail("certificate artifact closure changed")
    producer_record = artifacts["producer_module"]
    if producer_record != _artifact(Path(__file__).resolve()):
        _fail("certificate was generated by a different producer module")
    generation_precision = parameters["generation_precision_bits"]
    if replay_precision_bits is None:
        replay_precision_bits = generation_precision + 2 * DEFAULT_REPLAY_GUARD_BITS
    if replay_precision_bits < generation_precision + DEFAULT_REPLAY_GUARD_BITS:
        _fail("semantic replay precision must be at least generation precision + 64 bits")

    scan = _request_scan(
        q_start=parameters["q_start_inclusive"],
        q_stop=parameters["q_stop_inclusive"],
        t_index=parameters["t_index"],
        max_items=parameters["max_items"],
    )
    requests_record = manifest.get("requests")
    if not isinstance(requests_record, dict):
        _fail("certificate request record is missing")
    if (
        requests_record.get("count") != scan["count"]
        or requests_record.get("sha256_le_u32_q_a_row")
        != scan["sha256_le_u32_q_a_row"]
    ):
        _fail("certificate request enumeration mismatch")

    lattice_path = _require_artifact(manifest, root, LATTICE_FILENAME)
    recovery_path = _require_artifact(manifest, root, RECOVERY_FILENAME)
    cells, requests, radius = _read_lattice_input(
        lattice_path, parameters=parameters, expected_scan=scan
    )
    recovery_boxes = _read_recovery_input(
        recovery_path, parameters=parameters, requests=requests
    )

    expected_tail = derive_uniform_tail_bound(
        t_index=parameters["t_index"],
        m=parameters["M"],
        maximum_abs_delta=scan["maximum_abs_delta"],
    )
    if manifest.get("uniform_taylor_tail") != expected_tail:
        _fail("stored uniform Taylor derivation does not replay exactly")
    if radius.hex() != expected_tail["binary64_radius_hex"]:
        _fail("lattice input does not use the exactly replayed uniform radius")

    flint = _load_flint()
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    started = time.perf_counter()
    try:
        with flint.ctx.workprec(replay_precision_bits):
            for row in range(1, LATTICE_ROWS + 1):
                for column in range(TAYLOR_COLUMNS):
                    index = (row - 1) * TAYLOR_COLUMNS + column
                    value = _zeta_m_replay(
                        flint,
                        t_index=parameters["t_index"],
                        row=row,
                        column=column,
                        m=parameters["M"],
                    )
                    if not _contains_arb(cells[index], value):
                        _fail(
                            "stored lattice rectangle does not contain higher-precision "
                            f"Arb replay at row={row}, column={column}"
                        )
            for index, request in enumerate(requests):
                value = _finite_recovery_replay(
                    flint,
                    t_index=parameters["t_index"],
                    request=request,
                    m=parameters["M"],
                )
                if not _contains_arb(recovery_boxes[index], value):
                    _fail(
                        "stored finite-recovery rectangle does not contain "
                        f"higher-precision Arb replay at q={request.q}, a={request.a}"
                    )
    finally:
        flint.ctx.threads = old_threads

    replay_runtime = runtime_identity(flint)
    report: dict[str, Any] = {
        "schema": REPLAY_SCHEMA,
        "schema_version": 1,
        "classification": "complete_input_bundle_replay_not_theorem_7_1",
        "certificate_sha256": manifest["certificate_sha256"],
        "replay_precision_bits": replay_precision_bits,
        "lattice_cells_replayed": len(cells),
        "finite_recovery_values_replayed": len(recovery_boxes),
        "uniform_tail_replayed_exactly": True,
        "strict_request_geometry_replayed": True,
        "higher_precision_arb_containment_passed": True,
        "generator_runtime": manifest.get("generator_runtime"),
        "replay_runtime": replay_runtime,
        "same_runtime_binary": replay_runtime == manifest.get("generator_runtime"),
        "elapsed_seconds": time.perf_counter() - started,
        "external_atom_discharged": False,
    }
    report["replay_sha256"] = sha256_bytes(canonical_json_bytes(report))
    return report


def capability() -> dict[str, Any]:
    try:
        flint = _load_flint()
        runtime = runtime_identity(flint)
        available = True
        error = None
    except DirichletLatticeCertificateError as exception:
        runtime = None
        available = False
        error = str(exception)
    return {
        "algorithm_id": ALGORITHM_ID,
        "source": SOURCE_URL,
        "source_parameters": {"D": 2048, "N": 15},
        "retained_artifact_schema": {
            "manifest": MANIFEST_SCHEMA,
            "lattice_input": {
                "magic_ascii": INPUT_MAGIC.decode("ascii"),
                "format_version": LATTICE_FORMAT_VERSION,
            },
            "finite_recovery": {
                "magic_ascii": RECOVERY_MAGIC.decode("ascii"),
                "format_version": RECOVERY_FORMAT_VERSION,
            },
            "semantic_replay": REPLAY_SCHEMA,
        },
        "pinned_flint_available": available,
        "runtime": runtime,
        "error": error,
        "component_ready": available,
        "production_ready": False,
        "full_source": False,
        "production_ready_reason": (
            "The certified lattice/recovery input component is implemented, but "
            "the all-character FFT, completed-L phase, zero isolation, and "
            "Turing completeness pipeline are not all present and no full run exists."
        ),
        "generates": [
            "rigorous zeta_M Hurwitz lattice rectangles",
            "scaled finite-term addback rectangles",
            "exact-rational uniform Taylor-tail radius",
        ],
        "external_atom_discharged": False,
    }


def benchmark_generation(
    *,
    t_index: int,
    m: int,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    lattice_rows: int = 32,
    recovery_items: int = 128,
    tail_repetitions: int = 1_000,
) -> dict[str, Any]:
    """Measure representative producer work without publishing a certificate."""

    if not 1 <= lattice_rows <= LATTICE_ROWS:
        _fail("benchmark lattice_rows is outside 1..2048")
    if recovery_items <= 0:
        _fail("benchmark recovery_items must be positive")
    if tail_repetitions <= 0:
        _fail("benchmark tail_repetitions must be positive")
    _validate_batch_parameters(
        q_start=SOURCE_Q_START,
        q_stop=SOURCE_Q_START,
        t_index=t_index,
        m=m,
        precision_bits=precision_bits,
        max_items=recovery_items,
    )
    flint = _load_flint()
    old_threads = flint.ctx.threads
    flint.ctx.threads = 1
    try:
        start = time.perf_counter()
        count = 0
        for row in range(1, lattice_rows + 1):
            for column in range(TAYLOR_COLUMNS):
                _dual_precision_box(
                    flint,
                    lambda row=row, column=column: _zeta_m_generate(
                        flint,
                        t_index=t_index,
                        row=row,
                        column=column,
                        m=m,
                    ),
                    precision_bits=precision_bits,
                )
                count += 1
        lattice_seconds = time.perf_counter() - start
        requests = list(
            iter_requests(
                q_start=SOURCE_Q_START,
                q_stop=SOURCE_Q_START,
                t_index=t_index,
                max_items=recovery_items,
            )
        )
        if len(requests) != recovery_items:
            _fail("benchmark q does not have the requested number of active residues")
        start = time.perf_counter()
        for request in requests:
            _dual_precision_box(
                flint,
                lambda request=request: _finite_recovery_generate(
                    flint, t_index=t_index, request=request, m=m
                ),
                precision_bits=precision_bits,
            )
        recovery_seconds = time.perf_counter() - start
    finally:
        flint.ctx.threads = old_threads
    # The clipped first row controls the uniform geometry. This is the first
    # residue at the largest source modulus and is close to the limiting 1/D.
    benchmark_delta = Fraction(1, LATTICE_ROWS) - Fraction(1, SOURCE_Q_STOP)
    start = time.perf_counter()
    for _ in range(tail_repetitions):
        derive_uniform_tail_bound(
            t_index=t_index, m=m, maximum_abs_delta=benchmark_delta
        )
    tail_seconds = time.perf_counter() - start
    lattice_rate = count / lattice_seconds
    recovery_rate = recovery_items / recovery_seconds
    return {
        "classification": "local_sample_not_source_runtime_and_not_theorem_7_1_eta",
        "runtime": runtime_identity(flint),
        "parameters": {
            "t_index": t_index,
            "M": m,
            "precision_bits": precision_bits,
            "second_precision_bits": precision_bits + DEFAULT_REPLAY_GUARD_BITS,
        },
        "lattice": {
            "sample_rows": lattice_rows,
            "sample_cells": count,
            "elapsed_seconds": lattice_seconds,
            "cells_per_second": lattice_rate,
            "projected_one_ordinate_seconds": (
                LATTICE_ROWS * TAYLOR_COLUMNS / lattice_rate
            ),
        },
        "finite_recovery": {
            "sample_items": recovery_items,
            "elapsed_seconds": recovery_seconds,
            "items_per_second": recovery_rate,
            "note": (
                "Per-residue Arb generation is an audit oracle. A source-scale "
                "all-character engine must compute this compact formula in its "
                "interval GPU/FFT dataflow instead of materializing every value."
            ),
        },
        "uniform_tail": {
            "sample_derivations": tail_repetitions,
            "elapsed_seconds": tail_seconds,
            "derivations_per_second": tail_repetitions / tail_seconds,
            "arithmetic": "exact rational through final upward binary64 rounding",
        },
        "external_atom_runtime_estimated": False,
    }


__all__ = [
    "ALGORITHM_ID",
    "DirichletLatticeCertificateError",
    "MANIFEST_FILENAME",
    "RECOVERY_FILENAME",
    "RECOVERY_FORMAT_VERSION",
    "RECOVERY_HEADER",
    "RECOVERY_ITEM",
    "RECOVERY_MAGIC",
    "benchmark_generation",
    "capability",
    "derive_uniform_tail_bound",
    "generate_certificate",
    "iter_requests",
    "replay_certificate",
    "runtime_identity",
]

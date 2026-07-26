# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Persistent, bounded-memory consumer for ``TGDAFFO1`` interval frames.

The all-character transform emits every character frequency, while the GRH
campaign needs only primitive characters.  This module reconstructs the
canonical frequency map from ``q``, discards nonprimitive values after
validating and hashing them, constructs Platt's completed real value with Arb,
and streams sign-change candidates to a compact event artifact.

The root number is recomputed directly from the character's Gauss sum.  That
is a rigorous reference algorithm, but it is quadratic when used for every
character of a large modulus.  Consequently this component deliberately
reports that its source-scale root-number performance path is incomplete.  It
does not claim zero completeness, Turing closure, or the external GRH atom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
from typing import Any, BinaryIO, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    FORMAT_VERSION,
    OUTPUT_HEADER,
    OUTPUT_MAGIC,
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    canonical_component_orders,
    modulus_butterflies,
    primitive_frequency_records,
)
from tg_verifier.dirichlet_root_number_stage import (
    CONVENTION_SHA256 as ROOT_ARTIFACT_CONVENTION_SHA256,
    ROOT_ALGORITHM_ID as ARTIFACT_ROOT_NUMBER_MODE,
    canonical_json_bytes as root_canonical_json_bytes,
    primitive_frequency_records_bulk,
    read_root_artifact,
)
from tg_verifier.dirichlet_allchars_q_scheduler import (
    FULL_SOURCE_CLASSIFICATION,
    SCHEDULER_ALGORITHM_ID,
    PhaseScheduleProjection,
    ParsedScheduleManifest,
    parse_schedule_manifest,
    phase_schedule_projection,
)
from tg_verifier.dirichlet_root_catalog import (
    active_moduli,
    audit_root_catalog,
    root_artifact_filename,
    root_receipt_filename,
)
from tg_verifier.dirichlet_campaign import (
    _smallest_prime_factors,
    primitive_character_count,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ACCEPTED_MANUSCRIPT_URL = (
    "https://research-information.bris.ac.uk/ws/portalfiles/portal/"
    "67056136/platt_grh3.0.pdf"
)

CONTROL_SCHEMA = "sparkinterval.tg.dirichlet_stream_consumer.control.v1"
EVENT_SCHEMA = "sparkinterval.tg.dirichlet_stream_consumer.event.v1"
EVENT_FILE_SCHEMA = "sparkinterval.tg.dirichlet_stream_consumer.events.v1"
COMPACT_EVENT_SCHEMA = (
    "sparkinterval.tg.dirichlet_stream_consumer.compact_events.v2"
)
COMPACT_STATE_SCHEMA = (
    "sparkinterval.tg.dirichlet_stream_consumer.compact_state.v2"
)
RAW_EVENT_STORAGE_MODE = "raw_ndjson"
COMPACT_EVENT_STORAGE_MODE = "compact_associative_mmr_summary"
PHASE_COMPACT_BUNDLE_STORAGE_MODE = (
    "compact_associative_per_q_phase_bundle"
)
PHASE_COMPACT_BUNDLE_SCHEMA = (
    "sparkinterval.tg.dirichlet_stream_consumer."
    "phase_compact_state_bundle.v1"
)
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_stream_consumer.receipt.v1"
ALGORITHM_ID = "platt-completed-l-stream-sign-candidates-arb-v1"
REPLAY_ID = "flint-direct-l-and-hardy-z-known-answer-replay-v1"
ROOT_NUMBER_MODE = "arb-direct-character-gauss-sum-v1"
L_VALUE_SEMANTICS = "L_chi(1/2+it)-interval-after-q^-s-and-finite-addback"
MAX_CONTROL_LINE_BYTES = 64 * 1024
MAX_BATCH_COUNT = 1_000_000
MAX_EVENT_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_EVENT_COUNT = (1 << 64) - 1
MAX_PRECISION_BITS = 4096
MAX_RECEIPT_BYTES = 1024 * 1024
MIN_PRECISION_BITS = 128
PINNED_DIRECT_ROOT_RESIDUE_VISITS = 7_884_109_109_859_397
PINNED_DIRECT_ROOT_NONZERO_TERMS = 6_584_344_411_462_564
SOURCE_SAMPLE_NUMERATOR = 5
SOURCE_SAMPLE_DENOMINATOR = 64

_EVENT_LEAF_DOMAIN = (
    b"sparkinterval/tg/dirichlet-event/leaf/v1\0"
)
_EVENT_NODE_DOMAIN = (
    b"sparkinterval/tg/dirichlet-event/node/v1\0"
)
_EVENT_ROOT_DOMAIN = (
    b"sparkinterval/tg/dirichlet-event/root/v1\0"
)
_PHASE_STATE_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-phase-state-chain/v1\0"
)
_ROLLING_MODULUS = (1 << 255) - 19
_ROLLING_BASE = (
    int.from_bytes(
        hashlib.sha256(
            b"sparkinterval/tg/dirichlet-event/rolling-base/v1"
        ).digest(),
        "big",
    )
    % (_ROLLING_MODULUS - 1)
    + 1
)
_STATE_LEAF_DOMAIN = (
    b"sparkinterval/tg/dirichlet-compact-state/leaf/v1\0"
)
_SCHEDULED_FRAME_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-stream-consumer/scheduled-frame-chain/v1\0"
)

_UPSTREAM_KEYS = {
    "all_character_transform_input_sha256",
    "finite_addback_receipt_sha256",
    "lattice_tail_receipt_sha256",
    "residue_adapter_receipt_sha256",
}


class DirichletStreamConsumerError(RuntimeError):
    """A stream, character identity, or interval obligation failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletStreamConsumerError(message)


try:
    import flint
    from flint import acb, arb, ctx, dirichlet_char
except ImportError as error:  # pragma: no cover - environment dependent
    flint = acb = arb = ctx = dirichlet_char = None
    FLINT_IMPORT_ERROR = error
else:
    FLINT_IMPORT_ERROR = None


def require_flint() -> None:
    if FLINT_IMPORT_ERROR is not None:
        _fail(f"python-flint 0.9.0 / FLINT 3.6.0 is required: {FLINT_IMPORT_ERROR}")
    versions = (flint.__version__, flint.__FLINT_VERSION__, flint.__FLINT_RELEASE__)
    if versions != ("0.9.0", "3.6.0", 30_600):
        _fail(f"pinned FLINT versions differ: {versions}")


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_float(value: str) -> NoReturn:
    _fail(f"JSON floating-point values are forbidden: {value}")


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON value is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    answer: dict[str, Any] = {}
    for key, value in pairs:
        if key in answer:
            _fail(f"duplicate JSON key: {key}")
        answer[key] = value
    return answer


def _parse_canonical_line(raw: bytes, *, label: str) -> dict[str, Any]:
    if not raw.endswith(b"\n") or len(raw) > MAX_CONTROL_LINE_BYTES:
        _fail(f"{label} is not one bounded newline-terminated record")
    try:
        value = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletStreamConsumerError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not a canonical JSON object")
    return value


def _integer(name: str, value: object, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def fraction_json(value: Fraction) -> dict[str, int]:
    return {"denominator": value.denominator, "numerator": value.numerator}


def _arb_fraction(value: Fraction):
    return arb(f"{value.numerator}/{value.denominator}")


def _dyadic(value: Any) -> Fraction:
    mantissa, exponent = value.mid().man_exp()
    mantissa = int(mantissa)
    exponent = int(exponent)
    if exponent >= 0:
        return Fraction(mantissa << exponent)
    return Fraction(mantissa, 1 << (-exponent))


def _arb_interval_json(value: Any) -> dict[str, dict[str, int]]:
    midpoint = _dyadic(value.mid())
    radius = abs(_dyadic(value.rad()))
    if radius == 0 and not value.is_exact():
        radius = Fraction(1, 1 << max(16, int(ctx.prec)))
    while True:
        enclosure = arb(
            f"{midpoint.numerator}/{midpoint.denominator}",
            f"{radius.numerator}/{radius.denominator}",
        )
        if enclosure.contains(value):
            return {
                "lower": fraction_json(midpoint - radius),
                "upper": fraction_json(midpoint + radius),
            }
        radius = max(Fraction(1, 1 << max(16, int(ctx.prec))), 2 * radius)


def _rectangle_json(value: Any) -> dict[str, Any]:
    return {"imag": _arb_interval_json(value.imag), "real": _arb_interval_json(value.real)}


def _arb_from_binary_interval(lower: float, upper: float):
    lower_q = Fraction.from_float(lower)
    upper_q = Fraction.from_float(upper)
    midpoint = (lower_q + upper_q) / 2
    radius = (upper_q - lower_q) / 2
    return arb(
        f"{midpoint.numerator}/{midpoint.denominator}",
        f"{radius.numerator}/{radius.denominator}",
    )


def _acb_from_binary_rectangle(endpoints: tuple[float, float, float, float]):
    re_lo, re_hi, im_lo, im_hi = endpoints
    return acb(
        _arb_from_binary_interval(re_lo, re_hi),
        _arb_from_binary_interval(im_lo, im_hi),
    )


def validate_control(
    value: object,
    *,
    expected_frame_index: int,
    expected_root_number_mode: str = ROOT_NUMBER_MODE,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("control record must be an object")
    required = {
        "batch_count",
        "first_t_numerator",
        "frame_index",
        "kind",
        "l_value_semantics",
        "q",
        "root_number_mode",
        "t_denominator",
        "t_step_numerator",
        "upstream_receipts",
    }
    if set(value) != required:
        _fail("control record keys differ")
    if value["kind"] != CONTROL_SCHEMA:
        _fail("unsupported control schema")
    frame_index = _integer("frame_index", value["frame_index"], minimum=0)
    if frame_index != expected_frame_index:
        _fail("control frame index is not consecutive")
    q = _integer("q", value["q"], minimum=3)
    canonical_component_orders(q)
    batch_count = _integer("batch_count", value["batch_count"], minimum=1)
    first_t_numerator = _integer(
        "first_t_numerator", value["first_t_numerator"], minimum=0
    )
    t_denominator = _integer("t_denominator", value["t_denominator"], minimum=1)
    t_step_numerator = _integer(
        "t_step_numerator", value["t_step_numerator"], minimum=1
    )
    if batch_count > MAX_BATCH_COUNT:
        _fail(f"batch_count exceeds the bounded frame limit {MAX_BATCH_COUNT}")
    if first_t_numerator > (1 << 63) - 1:
        _fail("first_t_numerator exceeds the TGDAFFI1 signed field range")
    if t_denominator > (1 << 64) - 1 or t_step_numerator > (1 << 64) - 1:
        _fail("ordinate denominator/step exceeds the TGDAFFI1 field range")
    if value["l_value_semantics"] != L_VALUE_SEMANTICS:
        _fail("control record does not assert the exact completed-L input semantics")
    if value["root_number_mode"] != expected_root_number_mode:
        _fail("unsupported or uncertified root-number mode")
    upstream = value["upstream_receipts"]
    if not isinstance(upstream, dict) or set(upstream) != _UPSTREAM_KEYS:
        _fail("upstream receipt set differs")
    for key in sorted(_UPSTREAM_KEYS):
        _digest(f"upstream_receipts.{key}", upstream[key])
    return value


def make_control(
    *,
    frame_index: int,
    q: int,
    batch_count: int,
    first_t_numerator: int,
    t_denominator: int,
    t_step_numerator: int,
    upstream_receipts: dict[str, str],
    root_number_mode: str = ROOT_NUMBER_MODE,
) -> dict[str, Any]:
    value = {
        "batch_count": batch_count,
        "first_t_numerator": first_t_numerator,
        "frame_index": frame_index,
        "kind": CONTROL_SCHEMA,
        "l_value_semantics": L_VALUE_SEMANTICS,
        "q": q,
        "root_number_mode": root_number_mode,
        "t_denominator": t_denominator,
        "t_step_numerator": t_step_numerator,
        "upstream_receipts": upstream_receipts,
    }
    return validate_control(
        value,
        expected_frame_index=frame_index,
        expected_root_number_mode=root_number_mode,
    )


def _read_exact(stream: BinaryIO, length: int, *, label: str) -> bytes:
    pieces: list[bytes] = []
    retained = 0
    while retained < length:
        piece = stream.read(length - retained)
        if not piece:
            _fail(f"truncated {label}")
        pieces.append(piece)
        retained += len(piece)
    return b"".join(pieces)


@dataclass(frozen=True)
class RootRecord:
    primitive_ordinal: int
    frequency_id: int
    conrey_number: int
    parity: int
    root_number: Any
    epsilon: Any


def _character_root_records(q: int, *, precision: int) -> tuple[RootRecord, ...]:
    """Recompute primitive root numbers directly with outward Arb arithmetic.

    ``chi_exponent`` is expressed modulo the exponent of the full Dirichlet
    group, not modulo the order of the individual character.  The distinction
    is essential (q=5, Conrey 4 is the regression KAT).
    """

    require_flint()
    if not MIN_PRECISION_BITS <= precision <= MAX_PRECISION_BITS:
        _fail(f"precision must be in {MIN_PRECISION_BITS}..{MAX_PRECISION_BITS}")
    ctx.prec = precision
    records: list[RootRecord] = []
    for identity in primitive_frequency_records(q):
        conrey = identity["conrey_number"]
        character = dirichlet_char(q, conrey)
        if (
            character.number() != conrey
            or character.modulus() != q
            or character.conductor() != q
            or not character.is_primitive()
            or character.parity() != identity["parity"]
        ):
            _fail("FLINT character identity/primitivity differs from canonical map")
        group_exponent = int(character.group().exponent())
        if group_exponent <= 0:
            _fail("Dirichlet group exponent is not positive")
        tau = acb(0)
        for residue in range(1, q + 1):
            exponent = character.chi_exponent(residue)
            if exponent is None:
                continue
            chi_value = acb(
                0, 2 * arb.pi() * int(exponent) / group_exponent
            ).exp()
            additive = acb(0, 2 * arb.pi() * residue / q).exp()
            tau += chi_value * additive
        parity = identity["parity"]
        root_number = tau / (acb(0, 1) ** parity * arb(q).sqrt())
        if not abs(root_number).contains(1):
            _fail("direct Gauss-sum root enclosure does not contain unit modulus")
        epsilon = root_number.conjugate().sqrt()
        if not (epsilon**2).overlaps(root_number.conjugate()):
            _fail("root-number square-root phase did not verify")
        records.append(
            RootRecord(
                primitive_ordinal=identity["primitive_ordinal"],
                frequency_id=identity["frequency_id"],
                conrey_number=conrey,
                parity=parity,
                root_number=root_number,
                epsilon=epsilon,
            )
        )
    return tuple(records)


def root_number_inventory(q: int, *, precision: int = 192) -> dict[str, Any]:
    records = _character_root_records(q, precision=precision)
    rows = [
        {
            "conrey_number": row.conrey_number,
            "frequency_id": row.frequency_id,
            "parity": row.parity,
            "primitive_ordinal": row.primitive_ordinal,
            "root_number": _rectangle_json(row.root_number),
        }
        for row in records
    ]
    return {
        "algorithm_id": ROOT_NUMBER_MODE,
        "character_count": len(rows),
        "q": q,
        "root_rows_sha256": sha256_bytes(canonical_json_bytes(rows)),
    }


def _root_artifact_records(
    q: int,
    *,
    artifact_path: Path,
    receipt_path: Path,
) -> tuple[tuple[RootRecord, ...], dict[str, Any]]:
    """Load one hash-bound TGDRNRO1 frame for a persistent q shard."""

    require_flint()
    try:
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
    except (OSError, json.JSONDecodeError) as error:
        raise DirichletStreamConsumerError(
            "cannot read root-number artifact receipt"
        ) from error
    if (
        not isinstance(receipt, dict)
        or len(receipt_raw) > MAX_RECEIPT_BYTES
        or root_canonical_json_bytes(receipt) != receipt_raw
    ):
        _fail("root-number artifact receipt is not bounded canonical JSON")
    try:
        metadata, multipliers = read_root_artifact(artifact_path, receipt)
    except Exception as error:
        # Preserve this consumer's fail-closed public error type while retaining
        # the root stage as the sole parser for TGDRNRO1 semantics.
        raise DirichletStreamConsumerError(
            f"root-number artifact validation failed: {error}"
        ) from error
    if metadata["q"] != q:
        _fail("root-number artifact modulus differs from the control stream")
    identities = primitive_frequency_records_bulk(q)
    if len(identities) != len(multipliers):
        _fail("root-number artifact primitive inventory differs")
    records: list[RootRecord] = []
    for identity, epsilon in zip(identities, multipliers):
        # TGDRNRO1 stores epsilon = principal_sqrt(conj(w)).  The completed-L
        # hot path needs epsilon directly.  Reconstructing w is only for the
        # existing audit-row digest and is an enclosing interval operation.
        root_number = (epsilon**2).conjugate()
        records.append(
            RootRecord(
                primitive_ordinal=identity["primitive_ordinal"],
                frequency_id=identity["frequency_id"],
                conrey_number=identity["conrey_number"],
                parity=identity["parity"],
                root_number=root_number,
                epsilon=epsilon,
            )
        )
    binding = {
        "artifact_sha256": metadata["root_artifact_sha256"],
        "convention_sha256": ROOT_ARTIFACT_CONVENTION_SHA256,
        "primitive_character_count": len(records),
        "q": q,
        "receipt_sha256": receipt.get("receipt_sha256"),
        "transform_output_sha256": metadata["transform_output_sha256"],
    }
    if not isinstance(binding["receipt_sha256"], str):
        _fail("root-number artifact receipt omits its self-hash")
    return tuple(records), binding


@lru_cache(maxsize=1)
def direct_root_source_work() -> dict[str, Any]:
    """Count the exact work of the rigorous but unscalable root path."""

    spf = _smallest_prime_factors(SOURCE_Q_STOP)
    residue_visits = 0
    nonzero_terms = 0
    maximum_modulus_terms = 0
    maximum_modulus = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        characters = primitive_character_count(q, spf)
        residue_visits += q * characters
        remaining = q
        totient = q
        while remaining > 1:
            prime = spf[remaining]
            totient -= totient // prime
            while remaining % prime == 0:
                remaining //= prime
        terms = totient * characters
        nonzero_terms += terms
        if terms > maximum_modulus_terms:
            maximum_modulus_terms = terms
            maximum_modulus = q
    if (
        residue_visits != PINNED_DIRECT_ROOT_RESIDUE_VISITS
        or nonzero_terms != PINNED_DIRECT_ROOT_NONZERO_TERMS
    ):
        _fail("direct root-number source-work invariant changed")
    return {
        "classification": "exact_work_count_not_execution_or_runtime_projection",
        "maximum_modulus": maximum_modulus,
        "maximum_modulus_nonzero_terms": maximum_modulus_terms,
        "nonzero_gauss_terms": nonzero_terms,
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "residue_visits": residue_visits,
        "root_number_mode": ROOT_NUMBER_MODE,
        "source_performance_ready": False,
    }


def _completed_interval_with_q(
    q: int, l_value: Any, root: RootRecord, ordinate: Fraction
) -> tuple[Any, int]:
    t = _arb_fraction(ordinate)
    conductor_phase = acb(0, t * (arb(q) / arb.pi()).log() / 2).exp()
    gamma_argument = acb(arb(1 + 2 * root.parity) / 4, t / 2)
    completed = (
        root.epsilon
        * conductor_phase
        * gamma_argument.gamma()
        * (arb.pi() * t / 4).exp()
        * l_value
    )
    if not completed.imag.contains(0):
        _fail("completed-L imaginary rectangle does not contain zero")
    sign = 1 if completed.real > 0 else -1 if completed.real < 0 else 0
    return completed, sign


def _event_leaf(ordinal: int, raw: bytes) -> bytes:
    digest = hashlib.sha256(_EVENT_LEAF_DOMAIN)
    digest.update(ordinal.to_bytes(8, "little"))
    digest.update(len(raw).to_bytes(8, "little"))
    digest.update(raw)
    return digest.digest()


def _event_node(height: int, left: bytes, right: bytes) -> bytes:
    digest = hashlib.sha256(_EVENT_NODE_DOMAIN)
    digest.update(height.to_bytes(4, "little"))
    digest.update(left)
    digest.update(right)
    return digest.digest()


def _event_mmr_root(
    event_count: int, peaks: list[bytes | None]
) -> str:
    digest = hashlib.sha256(_EVENT_ROOT_DOMAIN)
    digest.update(event_count.to_bytes(8, "little"))
    present = [
        (height, peak)
        for height, peak in enumerate(peaks)
        if peak is not None
    ]
    digest.update(len(present).to_bytes(4, "little"))
    for height, peak in present:
        assert peak is not None
        digest.update(height.to_bytes(4, "little"))
        digest.update(peak)
    return digest.hexdigest()


def _append_event_peak(
    peaks: list[bytes | None],
    leaf: bytes,
) -> None:
    height = 0
    node = leaf
    while height < len(peaks) and peaks[height] is not None:
        left = peaks[height]
        assert left is not None
        peaks[height] = None
        node = _event_node(height, left, node)
        height += 1
    if height == len(peaks):
        peaks.append(node)
    else:
        peaks[height] = node


def combine_associative_event_commitments(
    left_count: int,
    left_value: int,
    right_count: int,
    right_value: int,
) -> tuple[int, int]:
    """Associatively concatenate two ordered event polynomial summaries."""

    for label, count in (("left", left_count), ("right", right_count)):
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= MAX_EVENT_COUNT
        ):
            _fail(f"{label} event count is outside uint64")
    for label, value in (("left", left_value), ("right", right_value)):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value < _ROLLING_MODULUS
        ):
            _fail(f"{label} event commitment is outside its field")
    total = left_count + right_count
    if total > MAX_EVENT_COUNT:
        _fail("combined event count overflows uint64")
    combined = (
        left_value * pow(_ROLLING_BASE, right_count, _ROLLING_MODULUS)
        + right_value
    ) % _ROLLING_MODULUS
    return total, combined


@dataclass
class _CharacterChunkState:
    conrey_number: int
    primitive_ordinal: int
    parity: int
    sample_count: int = 0
    first_determinate_numerator: int | None = None
    first_sign: int = 0
    last_determinate_numerator: int | None = None
    last_sign: int = 0
    leading_ambiguity_count: int = 0
    trailing_ambiguity_count: int = 0
    ambiguity_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    bracket_count: int = 0
    ambiguity_ranges: list[dict[str, int]] = field(default_factory=list)
    bracket_records: list[dict[str, int]] = field(default_factory=list)
    _open_ambiguity_start: int | None = None
    _previous_numerator: int | None = None

    def observe(self, ordinate_numerator: int, sign: int) -> None:
        if (
            isinstance(ordinate_numerator, bool)
            or not isinstance(ordinate_numerator, int)
            or not 0 <= ordinate_numerator <= MAX_EVENT_COUNT
        ):
            _fail("character ordinate numerator is outside uint64")
        if (
            self._previous_numerator is not None
            and ordinate_numerator
            != self._previous_numerator + SOURCE_SAMPLE_NUMERATOR
        ):
            _fail("character samples are not consecutive on the exact grid")
        if self.sample_count >= MAX_EVENT_COUNT:
            _fail("character sample count overflows uint64")
        self.sample_count += 1
        if sign == 0:
            if self._open_ambiguity_start is None:
                self._open_ambiguity_start = ordinate_numerator
            self.ambiguity_count += 1
            self.trailing_ambiguity_count += 1
            if self.first_determinate_numerator is None:
                self.leading_ambiguity_count += 1
            self._previous_numerator = ordinate_numerator
            return
        if sign not in (-1, 1):
            _fail("character sign state is outside {-1,0,1}")
        if self._open_ambiguity_start is not None:
            self.ambiguity_ranges.append(
                {
                    "first_t_numerator": self._open_ambiguity_start,
                    "stop_t_numerator": ordinate_numerator,
                }
            )
            self._open_ambiguity_start = None
        if sign > 0:
            self.positive_count += 1
        else:
            self.negative_count += 1
        if self.first_determinate_numerator is None:
            self.first_determinate_numerator = ordinate_numerator
            self.first_sign = sign
        if self.last_determinate_numerator is not None and self.last_sign != sign:
            self.bracket_count += 1
            self.bracket_records.append(
                {
                    "lower_t_numerator": self.last_determinate_numerator,
                    "upper_t_numerator": ordinate_numerator,
                    "lower_sign": self.last_sign,
                    "upper_sign": sign,
                    "intervening_ambiguity_count": (
                        self.trailing_ambiguity_count
                    ),
                }
            )
        self.last_determinate_numerator = ordinate_numerator
        self.last_sign = sign
        self.trailing_ambiguity_count = 0
        self._previous_numerator = ordinate_numerator

    def record(self) -> dict[str, Any]:
        ranges = [dict(row) for row in self.ambiguity_ranges]
        if self._open_ambiguity_start is not None:
            assert self._previous_numerator is not None
            if (
                self._previous_numerator
                > MAX_EVENT_COUNT - SOURCE_SAMPLE_NUMERATOR
            ):
                _fail("character ambiguity range endpoint overflows uint64")
            ranges.append(
                {
                    "first_t_numerator": self._open_ambiguity_start,
                    "stop_t_numerator": (
                        self._previous_numerator + SOURCE_SAMPLE_NUMERATOR
                    ),
                }
            )
        result = {
            "conrey_number": self.conrey_number,
            "primitive_ordinal": self.primitive_ordinal,
            "parity": self.parity,
            "sample_count": self.sample_count,
            "first_determinate_numerator": self.first_determinate_numerator,
            "first_sign": self.first_sign,
            "last_determinate_numerator": self.last_determinate_numerator,
            "last_sign": self.last_sign,
            "leading_ambiguity_count": self.leading_ambiguity_count,
            "trailing_ambiguity_count": self.trailing_ambiguity_count,
            "ambiguity_count": self.ambiguity_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "bracket_count": self.bracket_count,
            "multiplicity_lower_bound_sum": self.bracket_count,
            "ambiguity_ranges": ranges,
            "bracket_records": [
                dict(row) for row in self.bracket_records
            ],
        }
        _validate_character_chunk_record(result)
        return result


def _character_chunk_span(
    value: Mapping[str, Any],
) -> tuple[int | None, int | None]:
    """Derive the exact half-open grid span from one nonempty record."""

    samples = value["sample_count"]
    if samples == 0:
        return None, None
    first = value["first_determinate_numerator"]
    last = value["last_determinate_numerator"]
    if first is None:
        ranges = value["ambiguity_ranges"]
        if (
            len(ranges) != 1
            or not isinstance(ranges[0], dict)
            or set(ranges[0])
            != {"first_t_numerator", "stop_t_numerator"}
        ):
            _fail("all-ambiguous character must have one maximal range")
        return ranges[0]["first_t_numerator"], ranges[0][
            "stop_t_numerator"
        ]
    assert last is not None
    leading_width = (
        value["leading_ambiguity_count"] * SOURCE_SAMPLE_NUMERATOR
    )
    trailing_width = (
        (value["trailing_ambiguity_count"] + 1)
        * SOURCE_SAMPLE_NUMERATOR
    )
    if first < leading_width or last > MAX_EVENT_COUNT - trailing_width:
        _fail("character chunk grid span overflows uint64")
    return first - leading_width, last + trailing_width


def _validate_character_chunk_record(value: Mapping[str, Any]) -> None:
    fields = {
        "conrey_number",
        "primitive_ordinal",
        "parity",
        "sample_count",
        "first_determinate_numerator",
        "first_sign",
        "last_determinate_numerator",
        "last_sign",
        "leading_ambiguity_count",
        "trailing_ambiguity_count",
        "ambiguity_count",
        "positive_count",
        "negative_count",
        "bracket_count",
        "multiplicity_lower_bound_sum",
        "ambiguity_ranges",
        "bracket_records",
    }
    if set(value) != fields:
        _fail("character chunk fields differ")
    for field in ("conrey_number", "primitive_ordinal"):
        _integer(field, value.get(field), minimum=0)
    if value.get("parity") not in (0, 1):
        _fail("character chunk parity differs")
    count_fields = (
        "sample_count",
        "leading_ambiguity_count",
        "trailing_ambiguity_count",
        "ambiguity_count",
        "positive_count",
        "negative_count",
        "bracket_count",
        "multiplicity_lower_bound_sum",
    )
    for field in count_fields:
        count = value.get(field)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= MAX_EVENT_COUNT
        ):
            _fail("character chunk counter is outside uint64")
    ambiguity = value["ambiguity_count"]
    determinate = value["positive_count"] + value["negative_count"]
    if (
        value["sample_count"] != ambiguity + determinate
        or value["multiplicity_lower_bound_sum"] != value["bracket_count"]
        or value["leading_ambiguity_count"] > ambiguity
        or value["trailing_ambiguity_count"] > ambiguity
        or value["bracket_count"] > max(0, determinate - 1)
    ):
        _fail("character chunk counter arithmetic differs")
    ranges = value.get("ambiguity_ranges")
    brackets = value.get("bracket_records")
    if not isinstance(ranges, list) or not isinstance(brackets, list):
        _fail("character sparse records are not lists")
    if len(ranges) > ambiguity or len(brackets) != value["bracket_count"]:
        _fail("character sparse record counts differ")
    first = value.get("first_determinate_numerator")
    last = value.get("last_determinate_numerator")
    if first is None:
        if (
            last is not None
            or value.get("first_sign") != 0
            or value.get("last_sign") != 0
            or determinate != 0
            or value["bracket_count"] != 0
            or value["leading_ambiguity_count"] != ambiguity
            or value["trailing_ambiguity_count"] != ambiguity
        ):
            _fail("all-ambiguous character chunk state differs")
    elif (
        isinstance(first, bool)
        or not isinstance(first, int)
        or isinstance(last, bool)
        or not isinstance(last, int)
        or first > last
        or value.get("first_sign") not in (-1, 1)
        or value.get("last_sign") not in (-1, 1)
        or determinate == 0
    ):
        _fail("determinate character chunk boundary state differs")
    span_first, span_stop = _character_chunk_span(value)
    samples = value["sample_count"]
    if samples == 0:
        if (
            first is not None
            or last is not None
            or ambiguity != 0
            or determinate != 0
            or ranges
            or brackets
        ):
            _fail("empty character chunk state differs")
        return
    assert span_first is not None and span_stop is not None
    if (
        span_stop - span_first
        != samples * SOURCE_SAMPLE_NUMERATOR
        or span_stop > MAX_EVENT_COUNT
    ):
        _fail("character chunk exact grid span differs")

    ambiguity_from_ranges = 0
    previous_stop: int | None = None
    canonical_ranges: set[tuple[int, int]] = set()
    for index, raw_range in enumerate(ranges):
        if (
            not isinstance(raw_range, dict)
            or set(raw_range)
            != {"first_t_numerator", "stop_t_numerator"}
        ):
            _fail("character ambiguity range is malformed")
        range_first = raw_range.get("first_t_numerator")
        range_stop = raw_range.get("stop_t_numerator")
        for label, numerator in (
            ("ambiguity range first", range_first),
            ("ambiguity range stop", range_stop),
        ):
            if (
                isinstance(numerator, bool)
                or not isinstance(numerator, int)
                or not 0 <= numerator <= MAX_EVENT_COUNT
                or (numerator - span_first) % SOURCE_SAMPLE_NUMERATOR
            ):
                _fail(f"character {label} is outside the exact grid")
        assert isinstance(range_first, int)
        assert isinstance(range_stop, int)
        if (
            range_first < span_first
            or range_stop > span_stop
            or range_first >= range_stop
            or (range_stop - range_first) % SOURCE_SAMPLE_NUMERATOR
            or (
                previous_stop is not None
                and range_first <= previous_stop
            )
        ):
            _fail("character ambiguity ranges are not ordered maximal ranges")
        previous_stop = range_stop
        canonical_ranges.add((range_first, range_stop))
        ambiguity_from_ranges += (
            range_stop - range_first
        ) // SOURCE_SAMPLE_NUMERATOR
        if ambiguity_from_ranges > MAX_EVENT_COUNT:
            _fail("character ambiguity ranges overflow uint64")
        if index == 0 and value["leading_ambiguity_count"]:
            if (
                range_first != span_first
                or range_stop
                != span_first
                + value["leading_ambiguity_count"]
                * SOURCE_SAMPLE_NUMERATOR
            ):
                _fail("character leading ambiguity range differs")
    if ambiguity_from_ranges != ambiguity:
        _fail("character ambiguity range sample count differs")
    if value["leading_ambiguity_count"] == 0:
        if ranges and ranges[0]["first_t_numerator"] == span_first:
            _fail("character leading ambiguity boundary count differs")
    elif not ranges:
        _fail("character leading ambiguity range is absent")
    if value["trailing_ambiguity_count"] == 0:
        if ranges and ranges[-1]["stop_t_numerator"] == span_stop:
            _fail("character trailing ambiguity boundary count differs")
    elif (
        not ranges
        or ranges[-1]["stop_t_numerator"] != span_stop
        or ranges[-1]["first_t_numerator"]
        != span_stop
        - value["trailing_ambiguity_count"]
        * SOURCE_SAMPLE_NUMERATOR
    ):
        _fail("character trailing ambiguity range differs")

    previous_upper: int | None = None
    previous_upper_sign: int | None = None
    determinate_endpoint_signs: dict[int, int] = {}
    if first is not None:
        assert last is not None
        determinate_endpoint_signs[first] = value["first_sign"]
        if (
            last in determinate_endpoint_signs
            and determinate_endpoint_signs[last] != value["last_sign"]
        ):
            _fail("character determinate boundary signs conflict")
        determinate_endpoint_signs[last] = value["last_sign"]
    for index, bracket in enumerate(brackets):
        if (
            not isinstance(bracket, dict)
            or set(bracket)
            != {
                "lower_t_numerator",
                "upper_t_numerator",
                "lower_sign",
                "upper_sign",
                "intervening_ambiguity_count",
            }
        ):
            _fail("character bracket record is malformed")
        lower = bracket.get("lower_t_numerator")
        upper = bracket.get("upper_t_numerator")
        intervening = bracket.get("intervening_ambiguity_count")
        for label, numerator in (("bracket lower", lower), ("bracket upper", upper)):
            if (
                isinstance(numerator, bool)
                or not isinstance(numerator, int)
                or not span_first <= numerator < span_stop
                or (numerator - span_first) % SOURCE_SAMPLE_NUMERATOR
            ):
                _fail(f"character {label} is outside the exact grid")
        if (
            bracket.get("lower_sign") not in (-1, 1)
            or bracket.get("upper_sign") not in (-1, 1)
            or bracket["lower_sign"] == bracket["upper_sign"]
            or isinstance(intervening, bool)
            or not isinstance(intervening, int)
            or not 0 <= intervening <= MAX_EVENT_COUNT
        ):
            _fail("character bracket sign or ambiguity count differs")
        assert isinstance(lower, int) and isinstance(upper, int)
        if (
            lower >= upper
            or (upper - lower) % SOURCE_SAMPLE_NUMERATOR
            or intervening
            != (upper - lower) // SOURCE_SAMPLE_NUMERATOR - 1
            or (previous_upper is not None and lower < previous_upper)
            or (
                previous_upper_sign is not None
                and bracket["lower_sign"] != previous_upper_sign
            )
        ):
            _fail("character brackets are reordered or not consecutive signs")
        for endpoint, sign in (
            (lower, bracket["lower_sign"]),
            (upper, bracket["upper_sign"]),
        ):
            if any(
                raw_range["first_t_numerator"]
                <= endpoint
                < raw_range["stop_t_numerator"]
                for raw_range in ranges
            ):
                _fail("character bracket endpoint is marked ambiguous")
            if (
                endpoint in determinate_endpoint_signs
                and determinate_endpoint_signs[endpoint] != sign
            ):
                _fail("character bracket endpoint signs conflict")
            determinate_endpoint_signs[endpoint] = sign
        if intervening:
            if (
                lower + SOURCE_SAMPLE_NUMERATOR,
                upper,
            ) not in canonical_ranges:
                _fail("character bracket ambiguity interval differs")
        elif upper != lower + SOURCE_SAMPLE_NUMERATOR:
            _fail("character adjacent bracket span differs")
        if index == 0 and bracket["lower_sign"] != value["first_sign"]:
            _fail("character first bracket sign differs")
        previous_upper = upper
        previous_upper_sign = bracket["upper_sign"]
    if brackets and brackets[-1]["upper_sign"] != value["last_sign"]:
        _fail("character last bracket sign differs")
    endpoint_positive = sum(
        sign > 0 for sign in determinate_endpoint_signs.values()
    )
    endpoint_negative = sum(
        sign < 0 for sign in determinate_endpoint_signs.values()
    )
    if (
        endpoint_positive > value["positive_count"]
        or endpoint_negative > value["negative_count"]
    ):
        _fail("character bracket endpoints exceed determinate sign counts")


def combine_character_chunk_states(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Associatively summarize two adjacent chunks for one character."""

    _validate_character_chunk_record(left)
    _validate_character_chunk_record(right)
    identity = ("conrey_number", "primitive_ordinal", "parity")
    if any(left.get(key) != right.get(key) for key in identity):
        _fail("character chunk identities differ")
    left_span = _character_chunk_span(left)
    right_span = _character_chunk_span(right)
    if (
        left_span[1] is not None
        and right_span[0] is not None
        and left_span[1] != right_span[0]
    ):
        _fail("character chunks are not adjacent on the exact grid")
    left_has = left.get("first_determinate_numerator") is not None
    right_has = right.get("first_determinate_numerator") is not None
    total_samples = left["sample_count"] + right["sample_count"]
    ambiguity_count = left["ambiguity_count"] + right["ambiguity_count"]
    positive_count = left["positive_count"] + right["positive_count"]
    negative_count = left["negative_count"] + right["negative_count"]
    bracket_count = left["bracket_count"] + right["bracket_count"]
    if left_has and right_has and left["last_sign"] != right["first_sign"]:
        bracket_count += 1
    for count in (
        total_samples,
        ambiguity_count,
        positive_count,
        negative_count,
        bracket_count,
    ):
        if count > MAX_EVENT_COUNT:
            _fail("combined character chunk counter overflows uint64")
    if total_samples != ambiguity_count + positive_count + negative_count:
        _fail("combined character sample partition differs")
    first_numerator = (
        left["first_determinate_numerator"]
        if left_has
        else right["first_determinate_numerator"]
    )
    first_sign = left["first_sign"] if left_has else right["first_sign"]
    last_numerator = (
        right["last_determinate_numerator"]
        if right_has
        else left["last_determinate_numerator"]
    )
    last_sign = right["last_sign"] if right_has else left["last_sign"]
    leading = left["leading_ambiguity_count"]
    if not left_has:
        leading += right["leading_ambiguity_count"]
    trailing = right["trailing_ambiguity_count"]
    if not right_has:
        trailing += left["trailing_ambiguity_count"]
    if leading > MAX_EVENT_COUNT or trailing > MAX_EVENT_COUNT:
        _fail("combined character ambiguity boundary overflows uint64")
    ranges = [
        dict(row)
        for row in left["ambiguity_ranges"] + right["ambiguity_ranges"]
    ]
    if (
        left["ambiguity_ranges"]
        and right["ambiguity_ranges"]
        and left["ambiguity_ranges"][-1]["stop_t_numerator"]
        == right["ambiguity_ranges"][0]["first_t_numerator"]
    ):
        join = len(left["ambiguity_ranges"]) - 1
        ranges[join : join + 2] = [
            {
                "first_t_numerator": ranges[join]["first_t_numerator"],
                "stop_t_numerator": ranges[join + 1][
                    "stop_t_numerator"
                ],
            }
        ]
    bracket_records = [
        dict(row) for row in left["bracket_records"]
    ]
    if left_has and right_has and left["last_sign"] != right["first_sign"]:
        intervening = (
            left["trailing_ambiguity_count"]
            + right["leading_ambiguity_count"]
        )
        if intervening > MAX_EVENT_COUNT:
            _fail("combined bracket ambiguity count overflows uint64")
        bracket_records.append(
            {
                "lower_t_numerator": left[
                    "last_determinate_numerator"
                ],
                "upper_t_numerator": right[
                    "first_determinate_numerator"
                ],
                "lower_sign": left["last_sign"],
                "upper_sign": right["first_sign"],
                "intervening_ambiguity_count": intervening,
            }
        )
    bracket_records.extend(dict(row) for row in right["bracket_records"])
    result = {
        "conrey_number": left["conrey_number"],
        "primitive_ordinal": left["primitive_ordinal"],
        "parity": left["parity"],
        "sample_count": total_samples,
        "first_determinate_numerator": first_numerator,
        "first_sign": first_sign,
        "last_determinate_numerator": last_numerator,
        "last_sign": last_sign,
        "leading_ambiguity_count": leading,
        "trailing_ambiguity_count": trailing,
        "ambiguity_count": ambiguity_count,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "bracket_count": bracket_count,
        "multiplicity_lower_bound_sum": bracket_count,
        "ambiguity_ranges": ranges,
        "bracket_records": bracket_records,
    }
    _validate_character_chunk_record(result)
    return result


class _EventWriter:
    def __init__(
        self,
        path: Path,
        *,
        maximum_bytes: int | None = None,
        storage_mode: str = RAW_EVENT_STORAGE_MODE,
        maximum_event_count: int = MAX_EVENT_COUNT,
    ):
        if (
            maximum_bytes is not None
            and (
                isinstance(maximum_bytes, bool)
                or not isinstance(maximum_bytes, int)
                or maximum_bytes <= 0
                or maximum_bytes > MAX_EVENT_OUTPUT_BYTES
            )
        ):
            _fail(
                "maximum event output bytes must be in "
                f"1..{MAX_EVENT_OUTPUT_BYTES}"
            )
        if storage_mode not in {
            RAW_EVENT_STORAGE_MODE,
            COMPACT_EVENT_STORAGE_MODE,
        }:
            _fail("unsupported event storage mode")
        if (
            isinstance(maximum_event_count, bool)
            or not isinstance(maximum_event_count, int)
            or not 0 <= maximum_event_count <= MAX_EVENT_COUNT
        ):
            _fail("maximum event count is outside uint64")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.temporary = path.with_name(path.name + ".tmp")
        self.storage_mode = storage_mode
        self.file = (
            self.temporary.open("wb")
            if storage_mode == RAW_EVENT_STORAGE_MODE
            else None
        )
        self.digest = hashlib.sha256()
        self.semantic_digest = hashlib.sha256()
        self.count = 0
        self.bytes_written = 0
        self.semantic_bytes = 0
        self.maximum_bytes = maximum_bytes
        self.maximum_event_count = maximum_event_count
        self.sign_change_count = 0
        self.indeterminate_count = 0
        self.rolling_value = 0
        self.peaks: list[bytes | None] = []
        self.header = {
            "classification": (
                "multiplicity-lower-bound-events-not-zero-completeness"
            ),
            "kind": EVENT_FILE_SCHEMA,
            "schema_version": 1,
        }
        if storage_mode == RAW_EVENT_STORAGE_MODE:
            self._write_raw(canonical_json_bytes(self.header))

    def _write_raw(self, raw: bytes) -> None:
        if (
            self.maximum_bytes is not None
            and self.bytes_written + len(raw) > self.maximum_bytes
        ):
            _fail(
                "event stream exceeds the externally supplied retained-byte "
                "budget"
            )
        assert self.file is not None
        self.file.write(raw)
        self.digest.update(raw)
        self.bytes_written += len(raw)

    def event(self, value: dict[str, Any]) -> None:
        if self.count >= self.maximum_event_count:
            _fail("event count exceeds its fixed uint64 bound")
        raw = canonical_json_bytes(value)
        if self.storage_mode == RAW_EVENT_STORAGE_MODE:
            self._write_raw(raw)
        self.semantic_digest.update(raw)
        self.semantic_bytes += len(raw)
        leaf_digest = _event_leaf(self.count, raw)
        _append_event_peak(self.peaks, leaf_digest)
        leaf_value = int.from_bytes(leaf_digest, "big") % _ROLLING_MODULUS
        self.rolling_value = (
            self.rolling_value * _ROLLING_BASE + leaf_value
        ) % _ROLLING_MODULUS
        kind = value.get("event")
        if kind == "sign_change_candidate":
            self.sign_change_count += 1
        elif kind == "indeterminate_completed_value":
            self.indeterminate_count += 1
        else:
            _fail("event writer received an unsupported semantic event")
        self.count += 1

    def publish(
        self,
        *,
        compact_context: Mapping[str, Any] | None = None,
        character_states: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[str, int, int]:
        if self.storage_mode == RAW_EVENT_STORAGE_MODE:
            assert self.file is not None
            self.file.flush()
            self.file.close()
            self.temporary.replace(self.path)
            return (
                self.digest.hexdigest(),
                self.count,
                self.path.stat().st_size,
            )
        body = self.compact_summary(
            compact_context=compact_context,
            character_states=character_states,
        )
        raw = canonical_json_bytes(body)
        if (
            self.maximum_bytes is not None
            and len(raw) > self.maximum_bytes
        ):
            _fail("compact event summary exceeds its retained-byte budget")
        self.temporary.write_bytes(raw)
        self.temporary.replace(self.path)
        return hashlib.sha256(raw).hexdigest(), self.count, len(raw)

    def compact_summary(
        self,
        *,
        compact_context: Mapping[str, Any] | None,
        character_states: Sequence[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        """Return the canonical compact value without publishing a file.

        The phase-bundle oracle uses this at each q transition.  Ordinary
        fixed-q callers continue through :meth:`publish`, which serializes
        this exact value byte-for-byte.
        """

        if self.storage_mode != COMPACT_EVENT_STORAGE_MODE:
            _fail("compact summary requested from a raw event writer")
        if compact_context is None:
            _fail("compact event summary requires its fixed-q context")
        if character_states is None:
            _fail("compact event summary requires character boundary states")
        peaks = [
            {"height": height, "sha256": peak.hex()}
            for height, peak in enumerate(self.peaks)
            if peak is not None
        ]
        body: dict[str, Any] = {
            "schema": COMPACT_EVENT_SCHEMA,
            "schema_version": 2,
            "classification": (
                "associative_ordered_event_summary_not_zero_completeness"
            ),
            "storage_mode": COMPACT_EVENT_STORAGE_MODE,
            "context": dict(compact_context),
            "character_states": [dict(state) for state in character_states],
            "event_count": self.count,
            "sign_change_count": self.sign_change_count,
            "indeterminate_count": self.indeterminate_count,
            "semantic_event_json_bytes": self.semantic_bytes,
            "semantic_event_json_sha256": self.semantic_digest.hexdigest(),
            "ordered_mmr_peaks": peaks,
            "ordered_mmr_root_sha256": _event_mmr_root(
                self.count, self.peaks
            ),
            "associative_polynomial_commitment": {
                "modulus_hex": f"{_ROLLING_MODULUS:064x}",
                "base_hex": f"{_ROLLING_BASE:064x}",
                "value_hex": f"{self.rolling_value:064x}",
                "event_count": self.count,
                "combination": (
                    "(n,h)++(m,g)=(n+m,h*base^m+g mod modulus)"
                ),
            },
            "counter_width_bits": 64,
            "raw_event_records_retained": False,
            "exact_ambiguity_ranges_retained": True,
            "ordered_bracket_records_retained": True,
            "compact_summary_is_turing_completeness": False,
            "external_atom_discharged": False,
        }
        summary = dict(body)
        summary["summary_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        return summary

    def abort(self) -> None:
        if self.file is not None and not self.file.closed:
            self.file.close()
        self.temporary.unlink(missing_ok=True)


def validate_compact_event_summary(
    value: object,
    *,
    q: int,
    primitive_characters: int,
    frame_count: int,
    first_t_numerator: int,
    stop_t_numerator: int,
) -> tuple[int, int, int]:
    """Validate the compact event monoid and its fixed-q coverage context."""

    if not isinstance(value, dict):
        _fail("compact event summary is not an object")
    required = {
        "schema",
        "schema_version",
        "classification",
        "storage_mode",
        "context",
        "character_states",
        "event_count",
        "sign_change_count",
        "indeterminate_count",
        "semantic_event_json_bytes",
        "semantic_event_json_sha256",
        "ordered_mmr_peaks",
        "ordered_mmr_root_sha256",
        "associative_polynomial_commitment",
        "counter_width_bits",
        "raw_event_records_retained",
        "exact_ambiguity_ranges_retained",
        "ordered_bracket_records_retained",
        "compact_summary_is_turing_completeness",
        "external_atom_discharged",
        "summary_sha256",
    }
    body = dict(value)
    claimed = body.pop("summary_sha256", None)
    if (
        set(value) != required
        or value.get("schema") != COMPACT_EVENT_SCHEMA
        or value.get("schema_version") != 2
        or value.get("classification")
        != "associative_ordered_event_summary_not_zero_completeness"
        or value.get("storage_mode") != COMPACT_EVENT_STORAGE_MODE
        or value.get("counter_width_bits") != 64
        or value.get("raw_event_records_retained") is not False
        or value.get("exact_ambiguity_ranges_retained") is not True
        or value.get("ordered_bracket_records_retained") is not True
        or value.get("compact_summary_is_turing_completeness") is not False
        or value.get("external_atom_discharged") is not False
        or claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    ):
        _fail("compact event summary identity or self-hash differs")
    event_count = _integer("event_count", value.get("event_count"), minimum=0)
    sign_changes = _integer(
        "sign_change_count", value.get("sign_change_count"), minimum=0
    )
    indeterminates = _integer(
        "indeterminate_count", value.get("indeterminate_count"), minimum=0
    )
    if (
        event_count > MAX_EVENT_COUNT
        or sign_changes + indeterminates != event_count
        or _integer(
            "semantic_event_json_bytes",
            value.get("semantic_event_json_bytes"),
            minimum=0,
        )
        < event_count
    ):
        _fail("compact event counters differ or overflow")
    _digest("semantic event JSON", value.get("semantic_event_json_sha256"))
    context = value.get("context")
    expected_context = {
        "q": q,
        "primitive_character_count": primitive_characters,
        "frame_count": frame_count,
        "first_t_numerator": first_t_numerator,
        "stop_t_numerator": stop_t_numerator,
        "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
        "t_step_numerator": SOURCE_SAMPLE_NUMERATOR,
    }
    if context != expected_context:
        _fail("compact event fixed-q coverage context differs")
    if (
        stop_t_numerator < first_t_numerator
        or (stop_t_numerator - first_t_numerator)
        % SOURCE_SAMPLE_NUMERATOR
    ):
        _fail("compact event source-grid span differs")
    samples_per_character = (
        stop_t_numerator - first_t_numerator
    ) // SOURCE_SAMPLE_NUMERATOR
    states = value.get("character_states")
    identities = primitive_frequency_records_bulk(q)
    if (
        not isinstance(states, list)
        or len(states) != primitive_characters
        or len(identities) != primitive_characters
    ):
        _fail("compact event character-state roster differs")
    state_brackets = 0
    state_ambiguities = 0
    for ordinal, (state, identity) in enumerate(zip(states, identities)):
        if (
            not isinstance(state, dict)
            or state.get("primitive_ordinal") != ordinal
            or state.get("primitive_ordinal")
            != identity["primitive_ordinal"]
            or state.get("conrey_number") != identity["conrey_number"]
            or state.get("parity") != identity["parity"]
        ):
            _fail("compact event character identity differs")
        _validate_character_chunk_record(state)
        span_first, span_stop = _character_chunk_span(state)
        for field in (
            "sample_count",
            "leading_ambiguity_count",
            "trailing_ambiguity_count",
            "ambiguity_count",
            "positive_count",
            "negative_count",
            "bracket_count",
            "multiplicity_lower_bound_sum",
        ):
            count = state.get(field)
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or not 0 <= count <= MAX_EVENT_COUNT
            ):
                _fail("compact event character counter differs")
        if (
            state["sample_count"] != samples_per_character
            or state["sample_count"]
            != state["ambiguity_count"]
            + state["positive_count"]
            + state["negative_count"]
            or state["multiplicity_lower_bound_sum"]
            != state["bracket_count"]
            or state["leading_ambiguity_count"]
            > state["ambiguity_count"]
            or state["trailing_ambiguity_count"]
            > state["ambiguity_count"]
        ):
            _fail("compact event character-state arithmetic differs")
        if samples_per_character and (
            span_first != first_t_numerator
            or span_stop != stop_t_numerator
        ):
            _fail("compact event character exact grid span differs")
        first = state.get("first_determinate_numerator")
        last = state.get("last_determinate_numerator")
        if first is None:
            if (
                last is not None
                or state.get("first_sign") != 0
                or state.get("last_sign") != 0
                or state["ambiguity_count"] != samples_per_character
                or state["leading_ambiguity_count"] != samples_per_character
                or state["trailing_ambiguity_count"] != samples_per_character
                or state["bracket_count"] != 0
            ):
                _fail("all-ambiguous character state differs")
        else:
            if (
                isinstance(first, bool)
                or not isinstance(first, int)
                or isinstance(last, bool)
                or not isinstance(last, int)
                or first > last
                or state.get("first_sign") not in (-1, 1)
                or state.get("last_sign") not in (-1, 1)
            ):
                _fail("determinate character boundary state differs")
            for numerator in (first, last):
                if (
                    numerator < first_t_numerator
                    or numerator >= stop_t_numerator
                    or (numerator - first_t_numerator)
                    % SOURCE_SAMPLE_NUMERATOR
                ):
                    _fail("character boundary is outside the source grid")
        state_brackets += state["bracket_count"]
        state_ambiguities += state["ambiguity_count"]
    if (
        state_brackets != sign_changes
        or state_ambiguities != indeterminates
    ):
        _fail("compact event character-state totals differ")
    raw_peaks = value.get("ordered_mmr_peaks")
    if not isinstance(raw_peaks, list) or len(raw_peaks) > 64:
        _fail("compact event MMR peak inventory differs")
    peaks: list[bytes | None] = []
    previous_height = -1
    for raw_peak in raw_peaks:
        if (
            not isinstance(raw_peak, dict)
            or set(raw_peak) != {"height", "sha256"}
        ):
            _fail("compact event MMR peak is malformed")
        height = _integer(
            "MMR peak height", raw_peak.get("height"), minimum=0
        )
        if height >= 64 or height <= previous_height:
            _fail("compact event MMR peak heights are reordered")
        previous_height = height
        while len(peaks) <= height:
            peaks.append(None)
        peaks[height] = bytes.fromhex(
            _digest("MMR peak", raw_peak.get("sha256"))
        )
    expected_heights = [
        height for height in range(64) if event_count & (1 << height)
    ]
    if [row["height"] for row in raw_peaks] != expected_heights:
        _fail("compact event MMR peaks do not match the event count")
    if value.get("ordered_mmr_root_sha256") != _event_mmr_root(
        event_count, peaks
    ):
        _fail("compact event ordered MMR root differs")
    polynomial = value.get("associative_polynomial_commitment")
    if (
        not isinstance(polynomial, dict)
        or set(polynomial)
        != {
            "modulus_hex",
            "base_hex",
            "value_hex",
            "event_count",
            "combination",
        }
        or polynomial.get("modulus_hex") != f"{_ROLLING_MODULUS:064x}"
        or polynomial.get("base_hex") != f"{_ROLLING_BASE:064x}"
        or polynomial.get("event_count") != event_count
        or polynomial.get("combination")
        != "(n,h)++(m,g)=(n+m,h*base^m+g mod modulus)"
    ):
        _fail("compact event associative commitment parameters differ")
    raw_value = polynomial.get("value_hex")
    if (
        not isinstance(raw_value, str)
        or len(raw_value) != 64
        or any(character not in "0123456789abcdef" for character in raw_value)
        or int(raw_value, 16) >= _ROLLING_MODULUS
    ):
        _fail("compact event associative commitment value differs")
    return event_count, sign_changes, indeterminates


def _compact_state_commitment(
    count: int,
    value: int,
) -> dict[str, Any]:
    return {
        "modulus_hex": f"{_ROLLING_MODULUS:064x}",
        "base_hex": f"{_ROLLING_BASE:064x}",
        "value_hex": f"{value:064x}",
        "leaf_count": count,
        "combination": (
            "(n,h)++(m,g)=(n+m,h*base^m+g mod modulus)"
        ),
    }


def _compact_state_body(
    *,
    context: Mapping[str, Any],
    character_states: Sequence[Mapping[str, Any]],
    leaf_event_summary_count: int,
    leaf_event_summary_commitment_value: int,
    internal_sign_change_count: int,
    cross_boundary_sign_change_count: int,
    ambiguity_sample_count: int,
) -> dict[str, Any]:
    sign_change_lower_bound = (
        internal_sign_change_count + cross_boundary_sign_change_count
    )
    for label, count in (
        ("leaf event summary", leaf_event_summary_count),
        ("internal sign change", internal_sign_change_count),
        ("cross-boundary sign change", cross_boundary_sign_change_count),
        ("sign-change lower bound", sign_change_lower_bound),
        ("ambiguity sample", ambiguity_sample_count),
    ):
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= MAX_EVENT_COUNT
        ):
            _fail(f"{label} count is outside uint64")
    if leaf_event_summary_count == 0:
        _fail("compact state must contain at least one event-summary leaf")
    return {
        "schema": COMPACT_STATE_SCHEMA,
        "schema_version": 2,
        "classification": (
            "associative_per_character_sign_scan_state_not_zero_completeness"
        ),
        "context": dict(context),
        "character_states": [dict(state) for state in character_states],
        "leaf_event_summary_count": leaf_event_summary_count,
        "leaf_event_summary_commitment": _compact_state_commitment(
            leaf_event_summary_count,
            leaf_event_summary_commitment_value,
        ),
        "internal_sign_change_count": internal_sign_change_count,
        "cross_boundary_sign_change_count": (
            cross_boundary_sign_change_count
        ),
        "sign_change_lower_bound": sign_change_lower_bound,
        "ambiguity_sample_count": ambiguity_sample_count,
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "refinement_artifacts_complete": False,
        "turing_completeness": False,
        "source_scale_state_encoding": False,
        "external_atom_discharged": False,
    }


def validate_compact_state_summary(
    value: object,
) -> tuple[int, int, int, int]:
    """Validate one associative state over adjacent fixed-q event shards.

    This checks arithmetic, character roster, exact grid coverage, and the
    grouping-independent leaf commitment.  It deliberately cannot establish
    that the summarized interval computations were executed; that remains a
    separately pinned replay or trusted-execution obligation.
    """

    if not isinstance(value, dict):
        _fail("compact state summary is not an object")
    required = {
        "schema",
        "schema_version",
        "classification",
        "context",
        "character_states",
        "leaf_event_summary_count",
        "leaf_event_summary_commitment",
        "internal_sign_change_count",
        "cross_boundary_sign_change_count",
        "sign_change_lower_bound",
        "ambiguity_sample_count",
        "exact_ambiguity_ranges_retained",
        "ordered_bracket_records_retained",
        "refinement_artifacts_complete",
        "turing_completeness",
        "source_scale_state_encoding",
        "external_atom_discharged",
        "state_sha256",
    }
    body = dict(value)
    claimed = body.pop("state_sha256", None)
    if (
        set(value) != required
        or value.get("schema") != COMPACT_STATE_SCHEMA
        or value.get("schema_version") != 2
        or value.get("classification")
        != (
            "associative_per_character_sign_scan_state_not_zero_"
            "completeness"
        )
        or value.get("exact_ambiguity_ranges_retained") is not True
        or value.get("ordered_bracket_records_retained") is not True
        or value.get("refinement_artifacts_complete") is not False
        or value.get("turing_completeness") is not False
        or value.get("source_scale_state_encoding") is not False
        or value.get("external_atom_discharged") is not False
        or claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    ):
        _fail("compact state summary identity or self-hash differs")
    context = value.get("context")
    context_fields = {
        "q",
        "primitive_character_count",
        "frame_count",
        "first_t_numerator",
        "stop_t_numerator",
        "t_denominator",
        "t_step_numerator",
    }
    if not isinstance(context, dict) or set(context) != context_fields:
        _fail("compact state fixed-q context differs")
    q = _integer("compact state q", context.get("q"), minimum=1)
    primitive_characters = _integer(
        "compact state primitive character count",
        context.get("primitive_character_count"),
        minimum=0,
    )
    _integer("compact state frame count", context.get("frame_count"), minimum=1)
    first_t_numerator = _integer(
        "compact state first t numerator",
        context.get("first_t_numerator"),
        minimum=0,
    )
    stop_t_numerator = _integer(
        "compact state stop t numerator",
        context.get("stop_t_numerator"),
        minimum=first_t_numerator,
    )
    if (
        context.get("t_denominator") != SOURCE_SAMPLE_DENOMINATOR
        or context.get("t_step_numerator") != SOURCE_SAMPLE_NUMERATOR
        or (stop_t_numerator - first_t_numerator)
        % SOURCE_SAMPLE_NUMERATOR
    ):
        _fail("compact state source grid differs")
    samples_per_character = (
        stop_t_numerator - first_t_numerator
    ) // SOURCE_SAMPLE_NUMERATOR
    identities = primitive_frequency_records_bulk(q)
    states = value.get("character_states")
    if (
        not isinstance(states, list)
        or len(states) != primitive_characters
        or len(identities) != primitive_characters
    ):
        _fail("compact state character-state roster differs")
    state_brackets = 0
    state_ambiguities = 0
    for ordinal, (state, identity) in enumerate(zip(states, identities)):
        if (
            not isinstance(state, dict)
            or state.get("primitive_ordinal") != ordinal
            or state.get("primitive_ordinal")
            != identity["primitive_ordinal"]
            or state.get("conrey_number") != identity["conrey_number"]
            or state.get("parity") != identity["parity"]
        ):
            _fail("compact state character identity differs")
        _validate_character_chunk_record(state)
        if state["sample_count"] != samples_per_character:
            _fail("compact state per-character sample coverage differs")
        span_first, span_stop = _character_chunk_span(state)
        if samples_per_character and (
            span_first != first_t_numerator
            or span_stop != stop_t_numerator
        ):
            _fail("compact state per-character exact grid span differs")
        first = state["first_determinate_numerator"]
        last = state["last_determinate_numerator"]
        if first is not None:
            assert last is not None
            for numerator in (first, last):
                if (
                    numerator < first_t_numerator
                    or numerator >= stop_t_numerator
                    or (numerator - first_t_numerator)
                    % SOURCE_SAMPLE_NUMERATOR
                ):
                    _fail("compact state boundary is outside the source grid")
        state_brackets += state["bracket_count"]
        state_ambiguities += state["ambiguity_count"]
        if (
            state_brackets > MAX_EVENT_COUNT
            or state_ambiguities > MAX_EVENT_COUNT
        ):
            _fail("compact state roster totals overflow uint64")
    internal = _integer(
        "compact state internal sign changes",
        value.get("internal_sign_change_count"),
        minimum=0,
    )
    cross = _integer(
        "compact state cross-boundary sign changes",
        value.get("cross_boundary_sign_change_count"),
        minimum=0,
    )
    sign_changes = _integer(
        "compact state sign-change lower bound",
        value.get("sign_change_lower_bound"),
        minimum=0,
    )
    ambiguities = _integer(
        "compact state ambiguity samples",
        value.get("ambiguity_sample_count"),
        minimum=0,
    )
    if (
        internal > MAX_EVENT_COUNT
        or cross > MAX_EVENT_COUNT
        or sign_changes > MAX_EVENT_COUNT
        or ambiguities > MAX_EVENT_COUNT
        or internal + cross != sign_changes
        or state_brackets != sign_changes
        or state_ambiguities != ambiguities
    ):
        _fail("compact state sign or ambiguity totals differ")
    leaf_count = _integer(
        "compact state leaf event-summary count",
        value.get("leaf_event_summary_count"),
        minimum=1,
    )
    commitment = value.get("leaf_event_summary_commitment")
    if (
        leaf_count > MAX_EVENT_COUNT
        or not isinstance(commitment, dict)
        or set(commitment)
        != {
            "modulus_hex",
            "base_hex",
            "value_hex",
            "leaf_count",
            "combination",
        }
        or commitment.get("modulus_hex") != f"{_ROLLING_MODULUS:064x}"
        or commitment.get("base_hex") != f"{_ROLLING_BASE:064x}"
        or commitment.get("leaf_count") != leaf_count
        or commitment.get("combination")
        != "(n,h)++(m,g)=(n+m,h*base^m+g mod modulus)"
    ):
        _fail("compact state leaf commitment parameters differ")
    raw_value = commitment.get("value_hex")
    if (
        not isinstance(raw_value, str)
        or len(raw_value) != 64
        or any(character not in "0123456789abcdef" for character in raw_value)
        or int(raw_value, 16) >= _ROLLING_MODULUS
    ):
        _fail("compact state leaf commitment value differs")
    return q, sign_changes, ambiguities, leaf_count


def compact_state_from_event_summary(value: object) -> dict[str, Any]:
    """Project one validated event summary to the associative scan state."""

    if not isinstance(value, dict) or not isinstance(value.get("context"), dict):
        _fail("compact event summary has no fixed-q context")
    context = value["context"]
    event_count, sign_changes, ambiguities = validate_compact_event_summary(
        value,
        q=_integer("compact event q", context.get("q"), minimum=1),
        primitive_characters=_integer(
            "compact event primitive character count",
            context.get("primitive_character_count"),
            minimum=0,
        ),
        frame_count=_integer(
            "compact event frame count",
            context.get("frame_count"),
            minimum=1,
        ),
        first_t_numerator=_integer(
            "compact event first t numerator",
            context.get("first_t_numerator"),
            minimum=0,
        ),
        stop_t_numerator=_integer(
            "compact event stop t numerator",
            context.get("stop_t_numerator"),
            minimum=0,
        ),
    )
    if event_count != sign_changes + ambiguities:
        _fail("compact event projection counters differ")
    summary_sha256 = _digest(
        "compact event summary", value.get("summary_sha256")
    )
    leaf_digest = hashlib.sha256(
        _STATE_LEAF_DOMAIN + bytes.fromhex(summary_sha256)
    ).digest()
    leaf_value = int.from_bytes(leaf_digest, "big") % _ROLLING_MODULUS
    body = _compact_state_body(
        context=context,
        character_states=value["character_states"],
        leaf_event_summary_count=1,
        leaf_event_summary_commitment_value=leaf_value,
        internal_sign_change_count=sign_changes,
        cross_boundary_sign_change_count=0,
        ambiguity_sample_count=ambiguities,
    )
    result = dict(body)
    result["state_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    validate_compact_state_summary(result)
    return result


def combine_compact_state_summaries(
    left: object,
    right: object,
) -> dict[str, Any]:
    """Associatively merge two exactly adjacent fixed-q scan states."""

    left_q, left_signs, left_ambiguities, left_leaves = (
        validate_compact_state_summary(left)
    )
    right_q, right_signs, right_ambiguities, right_leaves = (
        validate_compact_state_summary(right)
    )
    assert isinstance(left, dict) and isinstance(right, dict)
    left_context = left["context"]
    right_context = right["context"]
    if (
        left_q != right_q
        or left_context["primitive_character_count"]
        != right_context["primitive_character_count"]
        or left_context["t_denominator"]
        != right_context["t_denominator"]
        or left_context["t_step_numerator"]
        != right_context["t_step_numerator"]
        or left_context["stop_t_numerator"]
        != right_context["first_t_numerator"]
    ):
        _fail("compact states are not adjacent shards of one fixed-q grid")
    states: list[dict[str, Any]] = []
    inserted_crossings = 0
    for left_state, right_state in zip(
        left["character_states"], right["character_states"]
    ):
        merged = combine_character_chunk_states(left_state, right_state)
        inserted = (
            merged["bracket_count"]
            - left_state["bracket_count"]
            - right_state["bracket_count"]
        )
        if inserted not in (0, 1):
            _fail("compact state cross-boundary bracket arithmetic differs")
        inserted_crossings += inserted
        states.append(merged)
    left_commitment = int(
        left["leaf_event_summary_commitment"]["value_hex"], 16
    )
    right_commitment = int(
        right["leaf_event_summary_commitment"]["value_hex"], 16
    )
    leaf_count, commitment = combine_associative_event_commitments(
        left_leaves,
        left_commitment,
        right_leaves,
        right_commitment,
    )
    internal = (
        left["internal_sign_change_count"]
        + right["internal_sign_change_count"]
    )
    cross = (
        left["cross_boundary_sign_change_count"]
        + right["cross_boundary_sign_change_count"]
        + inserted_crossings
    )
    if (
        internal > MAX_EVENT_COUNT
        or cross > MAX_EVENT_COUNT
        or left_ambiguities + right_ambiguities > MAX_EVENT_COUNT
        or left_signs + right_signs + inserted_crossings > MAX_EVENT_COUNT
    ):
        _fail("combined compact state totals overflow uint64")
    context = {
        "q": left_q,
        "primitive_character_count": left_context[
            "primitive_character_count"
        ],
        "frame_count": (
            left_context["frame_count"] + right_context["frame_count"]
        ),
        "first_t_numerator": left_context["first_t_numerator"],
        "stop_t_numerator": right_context["stop_t_numerator"],
        "t_denominator": left_context["t_denominator"],
        "t_step_numerator": left_context["t_step_numerator"],
    }
    body = _compact_state_body(
        context=context,
        character_states=states,
        leaf_event_summary_count=leaf_count,
        leaf_event_summary_commitment_value=commitment,
        internal_sign_change_count=internal,
        cross_boundary_sign_change_count=cross,
        ambiguity_sample_count=left_ambiguities + right_ambiguities,
    )
    result = dict(body)
    result["state_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    q, signs, ambiguities, leaves = validate_compact_state_summary(result)
    if (
        q != left_q
        or signs != left_signs + right_signs + inserted_crossings
        or ambiguities != left_ambiguities + right_ambiguities
        or leaves != left_leaves + right_leaves
    ):
        _fail("combined compact state validation differs")
    return result


def validate_phase_compact_state_bundle(
    value: object,
    *,
    projection: PhaseScheduleProjection,
) -> tuple[int, int, int]:
    """Validate one bounded multi-q Arb-oracle state bundle."""

    if not isinstance(value, dict):
        _fail("phase compact state bundle is not an object")
    required = {
        "schema",
        "schema_version",
        "classification",
        "schedule_manifest_sha256",
        "schedule_execution_order_sha256",
        "phase_plan_sha256",
        "phase_schedule_sha256",
        "phase_first_t_index",
        "phase_stop_t_index_exclusive",
        "phase_execution_q_start_index",
        "phase_execution_q_stop_index",
        "active_modulus_count",
        "phase_t_index_row_count",
        "compact_states",
        "compact_state_chain_sha256",
        "event_count",
        "sign_change_lower_bound",
        "ambiguity_sample_count",
        "semantic_event_json_bytes",
        "raw_event_records_retained",
        "raw_transform_stream_retained",
        "arb_differential_qualification_oracle",
        "source_performance_ready",
        "production_accept",
        "trusted_execution_attested",
        "zero_completeness_claimed",
        "external_atom_discharged",
        "bundle_sha256",
    }
    body = dict(value)
    claimed = body.pop("bundle_sha256", None)
    if (
        set(value) != required
        or value.get("schema") != PHASE_COMPACT_BUNDLE_SCHEMA
        or value.get("schema_version") != 1
        or value.get("classification")
        != "bounded_arb_multiq_phase_oracle_not_source_production"
        or value.get("schedule_manifest_sha256")
        != projection.schedule.manifest_sha256
        or value.get("schedule_execution_order_sha256")
        != projection.schedule.execution_order_sha256
        or value.get("phase_plan_sha256")
        != projection.phase_plan_sha256
        or value.get("phase_schedule_sha256")
        != projection.phase_schedule_sha256
        or value.get("phase_first_t_index")
        != projection.first_t_index
        or value.get("phase_stop_t_index_exclusive")
        != projection.t_index_stop_exclusive
        or value.get("phase_execution_q_start_index")
        != projection.start_execution_q_index
        or value.get("phase_execution_q_stop_index")
        != projection.stop_execution_q_index
        or value.get("active_modulus_count")
        != projection.active_modulus_count
        or value.get("phase_t_index_row_count")
        != projection.t_index_row_count
        or value.get("raw_event_records_retained") is not False
        or value.get("raw_transform_stream_retained") is not False
        or value.get("arb_differential_qualification_oracle") is not True
        or value.get("source_performance_ready") is not False
        or value.get("production_accept") is not False
        or value.get("trusted_execution_attested") is not False
        or value.get("zero_completeness_claimed") is not False
        or value.get("external_atom_discharged") is not False
        or claimed
        != hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    ):
        _fail("phase compact state bundle identity or claims differ")
    states = value.get("compact_states")
    if (
        not isinstance(states, list)
        or len(states) != projection.active_modulus_count
    ):
        _fail("phase compact state bundle q roster differs")
    chain = hashlib.sha256(_PHASE_STATE_CHAIN_DOMAIN)
    signs = 0
    ambiguities = 0
    events = 0
    for state, record in zip(
        states, projection.active_records, strict=True
    ):
        q, state_signs, state_ambiguities, _leaves = (
            validate_compact_state_summary(state)
        )
        assert isinstance(state, dict)
        context = state["context"]
        if (
            q != record.q
            or context["first_t_numerator"]
            != record.first_t_index * SOURCE_SAMPLE_NUMERATOR
            or context["stop_t_numerator"]
            != record.t_index_stop_exclusive
            * SOURCE_SAMPLE_NUMERATOR
        ):
            _fail("phase compact state q or exact span differs")
        chain.update(bytes.fromhex(state["state_sha256"]))
        signs += state_signs
        ambiguities += state_ambiguities
        events += state_signs + state_ambiguities
    for label, count in (
        ("event", value.get("event_count")),
        ("sign", value.get("sign_change_lower_bound")),
        ("ambiguity", value.get("ambiguity_sample_count")),
        ("semantic bytes", value.get("semantic_event_json_bytes")),
    ):
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= MAX_EVENT_COUNT
        ):
            _fail(f"phase compact bundle {label} count differs")
    if (
        value["compact_state_chain_sha256"] != chain.hexdigest()
        or value["event_count"] != events
        or value["sign_change_lower_bound"] != signs
        or value["ambiguity_sample_count"] != ambiguities
        or value["semantic_event_json_bytes"] < events
    ):
        _fail("phase compact bundle state chain or totals differ")
    return events, signs, ambiguities


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def consume_streams(
    control_stream: BinaryIO,
    frame_stream: BinaryIO,
    events_path: Path,
    receipt_path: Path,
    *,
    precision: int = 192,
    root_artifact_path: Path | None = None,
    root_receipt_path: Path | None = None,
    schedule_manifest_path: Path | None = None,
    require_full_source_schedule: bool = False,
    root_catalog_path: Path | None = None,
    root_catalog_sha256: str | None = None,
    root_catalog_directory: Path | None = None,
    maximum_event_bytes: int | None = None,
    event_storage_mode: str = RAW_EVENT_STORAGE_MODE,
    phase_plan_sha256: str | None = None,
    phase_first_t_index: int | None = None,
    phase_stop_t_index_exclusive: int | None = None,
    phase_execution_q_start_index: int | None = None,
    phase_execution_q_stop_index: int | None = None,
) -> dict[str, Any]:
    """Consume any number of TGDAFFO1 frames in one persistent process."""

    require_flint()
    if (root_artifact_path is None) != (root_receipt_path is None):
        _fail("root artifact and receipt paths must be supplied together")
    if require_full_source_schedule and schedule_manifest_path is None:
        _fail("full-source schedule requirement needs TGDQORD1")
    try:
        schedule: ParsedScheduleManifest | None = (
            None
            if schedule_manifest_path is None
            else parse_schedule_manifest(schedule_manifest_path)
        )
    except RuntimeError as error:
        raise DirichletStreamConsumerError(
            f"TGDQORD1 validation failed: {error}"
        ) from error
    phase_arguments = (
        phase_plan_sha256,
        phase_first_t_index,
        phase_stop_t_index_exclusive,
        phase_execution_q_start_index,
        phase_execution_q_stop_index,
    )
    phase_mode = any(value is not None for value in phase_arguments)
    if phase_mode and (
        schedule_manifest_path is None
        or any(value is None for value in phase_arguments)
    ):
        _fail(
            "phase scheduled consumer requires TGDQORD1, plan digest, "
            "t bounds, and execution-q bounds"
        )
    try:
        if phase_mode:
            assert schedule_manifest_path is not None
            assert phase_plan_sha256 is not None
            assert phase_first_t_index is not None
            assert phase_stop_t_index_exclusive is not None
            assert phase_execution_q_start_index is not None
            assert phase_execution_q_stop_index is not None
        phase: PhaseScheduleProjection | None = (
            None
            if not phase_mode
            else phase_schedule_projection(
                schedule_manifest_path,
                phase_plan_sha256=phase_plan_sha256,
                first_t_index=phase_first_t_index,
                t_index_stop_exclusive=phase_stop_t_index_exclusive,
                start_execution_q_index=phase_execution_q_start_index,
                stop_execution_q_index=phase_execution_q_stop_index,
            )
        )
    except (RuntimeError, TypeError, ValueError) as error:
        raise DirichletStreamConsumerError(
            f"phase schedule validation failed: {error}"
        ) from error
    if (
        event_storage_mode == PHASE_COMPACT_BUNDLE_STORAGE_MODE
        and phase is None
    ):
        _fail("phase compact bundle requires exact phase schedule coverage")
    if (
        phase is not None
        and event_storage_mode != PHASE_COMPACT_BUNDLE_STORAGE_MODE
    ):
        _fail("partial scheduled coverage requires the phase compact bundle")
    if (
        require_full_source_schedule
        and schedule is not None
        and schedule.classification != FULL_SOURCE_CLASSIFICATION
    ):
        _fail("production consumer requires a full-source q-order manifest")
    catalog_arguments = (
        root_catalog_path,
        root_catalog_sha256,
        root_catalog_directory,
    )
    catalog_root_mode = any(value is not None for value in catalog_arguments)
    if catalog_root_mode and not all(
        value is not None for value in catalog_arguments
    ):
        _fail("root catalog path, digest, and directory must be supplied together")
    if catalog_root_mode and root_artifact_path is not None:
        _fail("single root artifact and scheduled root catalog modes conflict")
    if schedule is not None and not catalog_root_mode:
        _fail("scheduled consumer requires its source root catalog")
    root_catalog_audit: dict[str, Any] | None = None
    if catalog_root_mode:
        assert root_catalog_path is not None
        assert root_catalog_sha256 is not None
        assert root_catalog_directory is not None
        try:
            root_catalog_audit = audit_root_catalog(
                root_catalog_path,
                root=root_catalog_directory,
                expected_sha256=root_catalog_sha256,
                require_full_source=require_full_source_schedule,
                revalidate_artifacts=True,
            )
        except RuntimeError as error:
            raise DirichletStreamConsumerError(
                f"root catalog validation failed: {error}"
            ) from error
        if schedule is None:
            _fail("root catalog mode requires TGDQORD1")
        catalog_qs = tuple(
            q
            for q, _primitive_count in active_moduli(
                root_catalog_audit["q_start_inclusive"],
                root_catalog_audit["q_stop_inclusive"],
            )
        )
        if catalog_qs != tuple(record.q for record in schedule.source_records):
            _fail("root catalog q roster differs from TGDQORD1")
    artifact_root_mode = root_artifact_path is not None or catalog_root_mode
    expected_root_mode = (
        ARTIFACT_ROOT_NUMBER_MODE if artifact_root_mode else ROOT_NUMBER_MODE
    )
    if not MIN_PRECISION_BITS <= precision <= MAX_PRECISION_BITS:
        _fail(f"precision must be in {MIN_PRECISION_BITS}..{MAX_PRECISION_BITS}")
    ctx.prec = precision
    event_writer = _EventWriter(
        events_path,
        maximum_bytes=maximum_event_bytes,
        storage_mode=(
            COMPACT_EVENT_STORAGE_MODE
            if event_storage_mode == PHASE_COMPACT_BUNDLE_STORAGE_MODE
            else event_storage_mode
        ),
    )
    control_stream_digest = hashlib.sha256()
    transform_stream_digest = hashlib.sha256()
    frame_chain = (
        bytes(32)
        if schedule is None
        else hashlib.sha256(
            _SCHEDULED_FRAME_CHAIN_DOMAIN
            + bytes.fromhex(schedule.manifest_sha256)
        ).digest()
    )
    sign_chain = hashlib.sha256()
    root_chain = hashlib.sha256()
    root_artifact_chain = hashlib.sha256()
    root_artifact_bindings: list[dict[str, Any]] = []
    frames = 0
    values = 0
    primitive_samples = 0
    discarded_nonprimitive = 0
    bracket_count = 0
    indeterminate_count = 0
    root_moduli = 0
    root_characters = 0
    previous_q: int | None = None
    schedule_index = 0
    scheduled_rows = 0
    scheduled_rows_for_q = 0
    scheduled_total_rows = 0
    first_q: int | None = None
    first_ordinate: Fraction | None = None
    previous_stop: Fraction | None = None
    previous_step: Fraction | None = None
    roots_by_frequency: dict[int, RootRecord] = {}
    compact_character_states: dict[int, _CharacterChunkState] = {}
    sign_state: dict[int, tuple[Fraction, int, int]] = {}
    phase_states: list[dict[str, Any]] = []
    phase_state_chain = hashlib.sha256(_PHASE_STATE_CHAIN_DOMAIN)
    phase_q_first_ordinate: Fraction | None = None
    phase_q_frame_count = 0
    phase_event_count = 0
    phase_semantic_event_bytes = 0

    def finalize_phase_q() -> None:
        nonlocal event_writer
        nonlocal phase_q_first_ordinate
        nonlocal phase_q_frame_count
        nonlocal phase_event_count
        nonlocal phase_semantic_event_bytes
        if event_storage_mode != PHASE_COMPACT_BUNDLE_STORAGE_MODE:
            return
        if (
            previous_q is None
            or phase_q_first_ordinate is None
            or previous_stop is None
            or phase_q_frame_count == 0
        ):
            _fail("phase compact q boundary is incomplete")
        summary = event_writer.compact_summary(
            compact_context={
                "q": previous_q,
                "primitive_character_count": len(roots_by_frequency),
                "frame_count": phase_q_frame_count,
                "first_t_numerator": (
                    phase_q_first_ordinate * SOURCE_SAMPLE_DENOMINATOR
                ).numerator,
                "stop_t_numerator": (
                    previous_stop * SOURCE_SAMPLE_DENOMINATOR
                ).numerator,
                "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
                "t_step_numerator": SOURCE_SAMPLE_NUMERATOR,
            },
            character_states=[
                compact_character_states[ordinal].record()
                for ordinal in range(len(compact_character_states))
            ],
        )
        state = compact_state_from_event_summary(summary)
        phase_states.append(state)
        phase_state_chain.update(bytes.fromhex(state["state_sha256"]))
        phase_event_count += event_writer.count
        phase_semantic_event_bytes += event_writer.semantic_bytes
        event_writer = _EventWriter(
            events_path,
            maximum_bytes=maximum_event_bytes,
            storage_mode=COMPACT_EVENT_STORAGE_MODE,
        )
        phase_q_first_ordinate = None
        phase_q_frame_count = 0
    try:
        while True:
            control_raw = control_stream.readline(MAX_CONTROL_LINE_BYTES + 1)
            if control_raw == b"":
                break
            control = validate_control(
                _parse_canonical_line(control_raw, label="control record"),
                expected_frame_index=frames,
                expected_root_number_mode=expected_root_mode,
            )
            control_stream_digest.update(control_raw)
            q = control["q"]
            batch_count = control["batch_count"]
            first = Fraction(control["first_t_numerator"], control["t_denominator"])
            step = Fraction(control["t_step_numerator"], control["t_denominator"])
            if (
                event_storage_mode
                in {
                    COMPACT_EVENT_STORAGE_MODE,
                    PHASE_COMPACT_BUNDLE_STORAGE_MODE,
                }
                and (
                    control["t_denominator"] != SOURCE_SAMPLE_DENOMINATOR
                    or control["t_step_numerator"]
                    != SOURCE_SAMPLE_NUMERATOR
                )
            ):
                _fail("compact event summary requires the exact 5/64 grid")
            if previous_q is not None:
                if schedule is None and q < previous_q:
                    _fail("moduli are not monotone in the persistent stream")
                if q == previous_q:
                    if step != previous_step or first != previous_stop:
                        _fail("same-modulus frames are not a contiguous ordinate stream")
                else:
                    if event_storage_mode == COMPACT_EVENT_STORAGE_MODE:
                        _fail(
                            "compact event summary accepts one fixed-q "
                            "pipeline shard"
                        )
                    if (
                        event_storage_mode
                        == PHASE_COMPACT_BUNDLE_STORAGE_MODE
                    ):
                        finalize_phase_q()
                    sign_state.clear()
            else:
                first_q = q
                first_ordinate = first
            if q != previous_q:
                if schedule is not None:
                    if (
                        previous_q is not None
                        and scheduled_rows != scheduled_rows_for_q
                    ):
                        _fail(
                            "scheduled consumer ended a q before exact coverage"
                        )
                    expected_records = (
                        schedule.execution_records
                        if phase is None
                        else phase.active_records
                    )
                    if schedule_index >= len(expected_records):
                        _fail("consumer has a trailing scheduled modulus")
                    expected_record = expected_records[schedule_index]
                    if q != expected_record.q:
                        _fail("consumer q differs from TGDQORD1 execution order")
                    expected_first_t_index = (
                        0
                        if phase is None
                        else expected_record.first_t_index
                    )
                    if (
                        control["first_t_numerator"]
                        != expected_first_t_index
                        * SOURCE_SAMPLE_NUMERATOR
                        or control["t_denominator"]
                        != SOURCE_SAMPLE_DENOMINATOR
                        or control["t_step_numerator"]
                        != SOURCE_SAMPLE_NUMERATOR
                    ):
                        _fail(
                            "scheduled consumer requires the exact 5/64 "
                            "source progression from its bound phase start"
                        )
                    scheduled_rows = 0
                    scheduled_rows_for_q = (
                        expected_record.t_index_count
                    )
                    schedule_index += 1
                if artifact_root_mode:
                    if root_artifact_path is not None and root_moduli != 0:
                        _fail(
                            "one root artifact can serve only one modulus shard"
                        )
                    if catalog_root_mode:
                        assert root_catalog_directory is not None
                        selected_root_artifact = (
                            root_catalog_directory
                            / root_artifact_filename(q)
                        )
                        selected_root_receipt = (
                            root_catalog_directory
                            / root_receipt_filename(q)
                        )
                    else:
                        assert root_artifact_path is not None
                        assert root_receipt_path is not None
                        selected_root_artifact = root_artifact_path
                        selected_root_receipt = root_receipt_path
                    roots, root_binding = _root_artifact_records(
                        q,
                        artifact_path=selected_root_artifact,
                        receipt_path=selected_root_receipt,
                    )
                    root_artifact_chain.update(canonical_json_bytes(root_binding))
                    root_artifact_bindings.append(root_binding)
                else:
                    roots = _character_root_records(q, precision=precision)
                roots_by_frequency = {row.frequency_id: row for row in roots}
                if len(roots_by_frequency) != len(roots):
                    _fail("duplicate primitive frequency in root-number map")
                if event_storage_mode in {
                    COMPACT_EVENT_STORAGE_MODE,
                    PHASE_COMPACT_BUNDLE_STORAGE_MODE,
                }:
                    compact_character_states = {
                        row.primitive_ordinal: _CharacterChunkState(
                            conrey_number=row.conrey_number,
                            primitive_ordinal=row.primitive_ordinal,
                            parity=row.parity,
                        )
                        for row in roots
                    }
                    if len(compact_character_states) != len(roots):
                        _fail("compact character-state roster is duplicated")
                if (
                    event_storage_mode
                    == PHASE_COMPACT_BUNDLE_STORAGE_MODE
                ):
                    phase_q_first_ordinate = first
                    phase_q_frame_count = 0
                root_inventory_rows = [
                    {
                        "conrey_number": row.conrey_number,
                        "frequency_id": row.frequency_id,
                        "parity": row.parity,
                        "primitive_ordinal": row.primitive_ordinal,
                        "root_number": _rectangle_json(row.root_number),
                    }
                    for row in roots
                ]
                root_chain.update(canonical_json_bytes(root_inventory_rows))
                root_moduli += 1
                root_characters += len(roots)
            if schedule is not None:
                if (
                    scheduled_rows > scheduled_rows_for_q
                    or batch_count > scheduled_rows_for_q - scheduled_rows
                ):
                    _fail("consumer frame exceeds scheduled q row coverage")
                scheduled_rows += batch_count
                scheduled_total_rows += batch_count

            raw_header = _read_exact(
                frame_stream, OUTPUT_HEADER.size, label="TGDAFFO1 header"
            )
            transform_stream_digest.update(raw_header)
            (
                magic,
                version,
                frame_q,
                component_count,
                frame_batches,
                group_order,
                value_count,
                butterflies,
                _elapsed_nanoseconds,
            ) = OUTPUT_HEADER.unpack(raw_header)
            orders = canonical_component_orders(q)
            if (
                magic != OUTPUT_MAGIC
                or version != FORMAT_VERSION
                or frame_q != q
                or component_count != len(orders)
                or frame_batches != batch_count
                or group_order != math.prod(orders)
                or value_count != batch_count * group_order
                or butterflies != modulus_butterflies(q, batch_count=batch_count)
            ):
                _fail("TGDAFFO1 header differs from canonical control/shape")
            frame_digest = hashlib.sha256(raw_header)
            for batch_index in range(batch_count):
                ordinate = first + batch_index * step
                for frequency_id in range(group_order):
                    raw_value = _read_exact(
                        frame_stream, COMPLEX_INTERVAL.size, label="TGDAFFO1 value"
                    )
                    transform_stream_digest.update(raw_value)
                    frame_digest.update(raw_value)
                    endpoints = COMPLEX_INTERVAL.unpack(raw_value)
                    if not (
                        all(math.isfinite(endpoint) for endpoint in endpoints)
                        and endpoints[0] <= endpoints[1]
                        and endpoints[2] <= endpoints[3]
                    ):
                        _fail("TGDAFFO1 contains a malformed interval")
                    root = roots_by_frequency.get(frequency_id)
                    if root is None:
                        discarded_nonprimitive += 1
                        continue
                    l_value = _acb_from_binary_rectangle(endpoints)
                    _completed, sign = _completed_interval_with_q(
                        q, l_value, root, ordinate
                    )
                    if event_storage_mode in {
                        COMPACT_EVENT_STORAGE_MODE,
                        PHASE_COMPACT_BUNDLE_STORAGE_MODE,
                    }:
                        compact_character_states[
                            root.primitive_ordinal
                        ].observe(
                            control["first_t_numerator"]
                            + batch_index * control["t_step_numerator"],
                            sign,
                        )
                    primitive_samples += 1
                    sign_row = {
                        "conrey_number": root.conrey_number,
                        "frame_index": frames,
                        "ordinate": fraction_json(ordinate),
                        "parity": root.parity,
                        "primitive_ordinal": root.primitive_ordinal,
                        "q": q,
                        "sign": sign,
                    }
                    sign_chain.update(canonical_json_bytes(sign_row))
                    previous = sign_state.get(root.primitive_ordinal)
                    if sign == 0:
                        indeterminate_count += 1
                        event_writer.event(
                            {
                                **sign_row,
                                "completed_rectangle": _rectangle_json(_completed),
                                "kind": EVENT_SCHEMA,
                                "event": "indeterminate_completed_value",
                                "multiplicity_claimed": 0,
                            }
                        )
                        if previous is not None:
                            sign_state[root.primitive_ordinal] = (
                                previous[0],
                                previous[1],
                                previous[2] + 1,
                            )
                    else:
                        if previous is not None and previous[1] != sign:
                            event_writer.event(
                                {
                                    "conrey_number": root.conrey_number,
                                    "contains_indeterminate_samples": previous[2] > 0,
                                    "endpoint_signs": [previous[1], sign],
                                    "event": "sign_change_candidate",
                                    "kind": EVENT_SCHEMA,
                                    "lower_ordinate": fraction_json(previous[0]),
                                    "multiplicity_exact": False,
                                    "multiplicity_lower_bound": 1,
                                    "parity": root.parity,
                                    "primitive_ordinal": root.primitive_ordinal,
                                    "q": q,
                                    "upper_ordinate": fraction_json(ordinate),
                                }
                            )
                            bracket_count += 1
                        sign_state[root.primitive_ordinal] = (ordinate, sign, 0)
            frame_sha = frame_digest.digest()
            metadata_sha = hashlib.sha256(control_raw).digest()
            frame_chain = hashlib.sha256(frame_chain + metadata_sha + frame_sha).digest()
            frames += 1
            if (
                event_storage_mode
                == PHASE_COMPACT_BUNDLE_STORAGE_MODE
            ):
                phase_q_frame_count += 1
            values += value_count
            previous_q = q
            previous_step = step
            previous_stop = first + batch_count * step

        if frames == 0:
            _fail("persistent stream contains no frames")
        expected_schedule_records = (
            ()
            if schedule is None
            else (
                schedule.execution_records
                if phase is None
                else phase.active_records
            )
        )
        expected_schedule_rows = (
            0
            if schedule is None
            else (
                schedule.t_row_count
                if phase is None
                else phase.t_index_row_count
            )
        )
        if schedule is not None and (
            scheduled_rows != scheduled_rows_for_q
            or schedule_index != len(expected_schedule_records)
            or scheduled_total_rows != expected_schedule_rows
        ):
            _fail("scheduled consumer did not exactly cover TGDQORD1")
        if frame_stream.read(1):
            _fail("TGDAFFO1 stream has trailing bytes after the control stream ended")
        assert first_q is not None
        assert first_ordinate is not None
        assert previous_q is not None
        assert previous_stop is not None
        if event_storage_mode == PHASE_COMPACT_BUNDLE_STORAGE_MODE:
            finalize_phase_q()
            if (
                phase is None
                or len(phase_states) != phase.active_modulus_count
                or phase_event_count
                != bracket_count + indeterminate_count
            ):
                _fail("phase compact state bundle totals differ")
            bundle_body: dict[str, Any] = {
                "schema": PHASE_COMPACT_BUNDLE_SCHEMA,
                "schema_version": 1,
                "classification": (
                    "bounded_arb_multiq_phase_oracle_not_source_"
                    "production"
                ),
                "schedule_manifest_sha256": (
                    phase.schedule.manifest_sha256
                ),
                "schedule_execution_order_sha256": (
                    phase.schedule.execution_order_sha256
                ),
                "phase_plan_sha256": phase.phase_plan_sha256,
                "phase_schedule_sha256": phase.phase_schedule_sha256,
                "phase_first_t_index": phase.first_t_index,
                "phase_stop_t_index_exclusive": (
                    phase.t_index_stop_exclusive
                ),
                "phase_execution_q_start_index": (
                    phase.start_execution_q_index
                ),
                "phase_execution_q_stop_index": (
                    phase.stop_execution_q_index
                ),
                "active_modulus_count": phase.active_modulus_count,
                "phase_t_index_row_count": phase.t_index_row_count,
                "compact_states": phase_states,
                "compact_state_chain_sha256": (
                    phase_state_chain.hexdigest()
                ),
                "event_count": phase_event_count,
                "sign_change_lower_bound": bracket_count,
                "ambiguity_sample_count": indeterminate_count,
                "semantic_event_json_bytes": (
                    phase_semantic_event_bytes
                ),
                "raw_event_records_retained": False,
                "raw_transform_stream_retained": False,
                "arb_differential_qualification_oracle": True,
                "source_performance_ready": False,
                "production_accept": False,
                "trusted_execution_attested": False,
                "zero_completeness_claimed": False,
                "external_atom_discharged": False,
            }
            bundle = dict(bundle_body)
            bundle["bundle_sha256"] = hashlib.sha256(
                canonical_json_bytes(bundle_body)
            ).hexdigest()
            validate_phase_compact_state_bundle(
                bundle, projection=phase
            )
            bundle_raw = canonical_json_bytes(bundle)
            if (
                maximum_event_bytes is not None
                and len(bundle_raw) > maximum_event_bytes
            ):
                _fail("phase compact bundle exceeds its retained-byte budget")
            _atomic_write(events_path, bundle_raw)
            events_sha256 = hashlib.sha256(bundle_raw).hexdigest()
            event_count = phase_event_count
            event_bytes = len(bundle_raw)
        else:
            events_sha256, event_count, event_bytes = event_writer.publish(
                compact_context={
                    "q": first_q,
                    "primitive_character_count": len(roots_by_frequency),
                    "frame_count": frames,
                    "first_t_numerator": (
                        first_ordinate * SOURCE_SAMPLE_DENOMINATOR
                    ).numerator,
                    "stop_t_numerator": (
                        previous_stop * SOURCE_SAMPLE_DENOMINATOR
                    ).numerator,
                    "t_denominator": SOURCE_SAMPLE_DENOMINATOR,
                    "t_step_numerator": SOURCE_SAMPLE_NUMERATOR,
                }
                if event_storage_mode == COMPACT_EVENT_STORAGE_MODE
                else None,
                character_states=[
                    compact_character_states[ordinal].record()
                    for ordinal in range(len(compact_character_states))
                ]
                if event_storage_mode == COMPACT_EVENT_STORAGE_MODE
                else None,
            )
    except BaseException:
        event_writer.abort()
        raise

    receipt: dict[str, Any] = {
        "algorithm_id": ALGORITHM_ID,
        "all_frames_arithmetically_accepted": True,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "candidate_bracket_count": bracket_count,
        "classification": "streamed-completed-L-sign-candidates-not-zero-completeness",
        "control_stream_sha256": control_stream_digest.hexdigest(),
        "discarded_nonprimitive_value_count": discarded_nonprimitive,
        "event_count": event_count,
        "event_storage_mode": event_storage_mode,
        "events_bytes": event_bytes,
        "events_sha256": events_sha256,
        "raw_event_records_retained": (
            event_storage_mode == RAW_EVENT_STORAGE_MODE
        ),
        "external_atom_discharged": False,
        "frame_chain_sha256": frame_chain.hex(),
        "frame_count": frames,
        "full_source_campaign_run": False,
        "indeterminate_sample_count": indeterminate_count,
        "kind": RECEIPT_SCHEMA,
        "multiplicity_lower_bound_sum": bracket_count,
        "multiplicity_policy": (
            "one lower-bound event per strict endpoint sign change; never "
            "deduplicated or promoted to exact multiplicity"
        ),
        "ordinary_sign_scan_resolved": indeterminate_count == 0,
        "precision_bits": precision,
        "primitive_sample_count": primitive_samples,
        "production_accept": False,
        "root_number_artifact_chain_sha256": (
            root_artifact_chain.hexdigest() if artifact_root_mode else None
        ),
        "root_number_artifact_bindings": root_artifact_bindings,
        "root_number_artifact_supplied": artifact_root_mode,
        "root_number_character_count": root_characters,
        "root_number_mode": expected_root_mode,
        "root_number_modulus_count": root_moduli,
        "root_number_rows_sha256": root_chain.hexdigest(),
        "sign_decisions_sha256": sign_chain.hexdigest(),
        "source_performance_ready": (
            artifact_root_mode
            and event_storage_mode
            != PHASE_COMPACT_BUNDLE_STORAGE_MODE
        ),
        "source_performance_blocker": (
            (
                "qualification-only Arb phase consumer visits every "
                "transformed interval; source production must fuse "
                "completed-L classification and compact reduction on device"
            )
            if event_storage_mode
            == PHASE_COMPACT_BUNDLE_STORAGE_MODE
            else None
            if artifact_root_mode
            else (
                "direct Arb Gauss sums are quadratic across all characters of a "
                "modulus; supply a validated TGDRNRO1 artifact for source scale"
            )
        ),
        "transform_stream_sha256": transform_stream_digest.hexdigest(),
        "upstream_semantics_replayed": False,
        "upstream_semantics_status": (
            "four required receipts are identity/hash checked, but this component "
            "does not replay lattice tails, q^-s, or finite addback"
        ),
        "value_count": values,
        "zero_completeness_claimed": False,
    }
    if schedule is not None:
        assert root_catalog_audit is not None
        scheduled_moduli = (
            schedule.q_count
            if phase is None
            else phase.active_modulus_count
        )
        scheduled_t_rows = (
            schedule.t_row_count
            if phase is None
            else phase.t_index_row_count
        )
        receipt.update(
            {
                "scheduler_algorithm": SCHEDULER_ALGORITHM_ID,
                "schedule_classification": schedule.classification,
                "schedule_manifest_sha256": schedule.manifest_sha256,
                "schedule_source_roster_sha256": (
                    schedule.source_roster_sha256
                ),
                "schedule_execution_order_sha256": (
                    schedule.execution_order_sha256
                ),
                "scheduled_modulus_count": scheduled_moduli,
                "scheduled_t_index_rows": scheduled_t_rows,
                "TGDQORD1_exact_coverage": phase is None,
                "TGDQORD1_parent_manifest_bound": True,
                "phase_schedule_exact_coverage": phase is not None,
                "root_catalog_sha256": root_catalog_audit["catalog"][
                    "sha256"
                ],
                "root_catalog_entry_chain_sha256": root_catalog_audit[
                    "entry_chain_sha256"
                ],
                "root_catalog_artifacts_revalidated": root_catalog_audit[
                    "artifacts_parsed_and_receipt_bound"
                ],
            }
        )
        if phase is not None:
            receipt.update(
                {
                    "phase_plan_sha256": phase.phase_plan_sha256,
                    "phase_schedule_sha256": (
                        phase.phase_schedule_sha256
                    ),
                    "phase_first_t_index": phase.first_t_index,
                    "phase_stop_t_index_exclusive": (
                        phase.t_index_stop_exclusive
                    ),
                    "phase_execution_q_start_index": (
                        phase.start_execution_q_index
                    ),
                    "phase_execution_q_stop_index": (
                        phase.stop_execution_q_index
                    ),
                    "phase_compact_bundle_qualification_only": True,
                    "same_cuda_address_space_reduction": False,
                }
            )
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    _atomic_write(receipt_path, canonical_json_bytes(receipt))
    return receipt


def consume_paths(
    control_path: Path,
    frame_path: Path,
    events_path: Path,
    receipt_path: Path,
    *,
    precision: int = 192,
    root_artifact_path: Path | None = None,
    root_receipt_path: Path | None = None,
    schedule_manifest_path: Path | None = None,
    require_full_source_schedule: bool = False,
    root_catalog_path: Path | None = None,
    root_catalog_sha256: str | None = None,
    root_catalog_directory: Path | None = None,
    maximum_event_bytes: int | None = None,
    event_storage_mode: str = RAW_EVENT_STORAGE_MODE,
    phase_plan_sha256: str | None = None,
    phase_first_t_index: int | None = None,
    phase_stop_t_index_exclusive: int | None = None,
    phase_execution_q_start_index: int | None = None,
    phase_execution_q_stop_index: int | None = None,
) -> dict[str, Any]:
    with control_path.open("rb") as control, frame_path.open("rb") as frames:
        return consume_streams(
            control,
            frames,
            events_path,
            receipt_path,
            precision=precision,
            root_artifact_path=root_artifact_path,
            root_receipt_path=root_receipt_path,
            schedule_manifest_path=schedule_manifest_path,
            require_full_source_schedule=require_full_source_schedule,
            root_catalog_path=root_catalog_path,
            root_catalog_sha256=root_catalog_sha256,
            root_catalog_directory=root_catalog_directory,
            maximum_event_bytes=maximum_event_bytes,
            event_storage_mode=event_storage_mode,
            phase_plan_sha256=phase_plan_sha256,
            phase_first_t_index=phase_first_t_index,
            phase_stop_t_index_exclusive=(
                phase_stop_t_index_exclusive
            ),
            phase_execution_q_start_index=(
                phase_execution_q_start_index
            ),
            phase_execution_q_stop_index=(
                phase_execution_q_stop_index
            ),
        )


def verify_paths(
    control_path: Path,
    frame_path: Path,
    events_path: Path,
    receipt_path: Path,
    *,
    precision: int = 192,
    root_artifact_path: Path | None = None,
    root_receipt_path: Path | None = None,
    schedule_manifest_path: Path | None = None,
    require_full_source_schedule: bool = False,
    root_catalog_path: Path | None = None,
    root_catalog_sha256: str | None = None,
    root_catalog_directory: Path | None = None,
) -> dict[str, Any]:
    """Freshly replay both artifacts and require byte-identical decisions."""

    if receipt_path.stat().st_size > MAX_RECEIPT_BYTES:
        _fail(f"receipt exceeds the compact bound {MAX_RECEIPT_BYTES}")
    expected_receipt = receipt_path.read_bytes()

    def files_equal(left: Path, right: Path) -> bool:
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_file, right.open("rb") as right_file:
            while True:
                left_chunk = left_file.read(1024 * 1024)
                right_chunk = right_file.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True

    with tempfile.TemporaryDirectory(prefix="tg-dirichlet-stream-replay-") as temporary:
        root = Path(temporary)
        replay_events = root / "events.ndjson"
        replay_receipt = root / "receipt.json"
        produced = consume_paths(
            control_path,
            frame_path,
            replay_events,
            replay_receipt,
            precision=precision,
            root_artifact_path=root_artifact_path,
            root_receipt_path=root_receipt_path,
            schedule_manifest_path=schedule_manifest_path,
            require_full_source_schedule=require_full_source_schedule,
            root_catalog_path=root_catalog_path,
            root_catalog_sha256=root_catalog_sha256,
            root_catalog_directory=root_catalog_directory,
        )
        if not files_equal(replay_events, events_path):
            _fail("fresh Arb replay events differ")
        if replay_receipt.read_bytes() != expected_receipt:
            _fail("fresh Arb replay receipt differs")
    return {
        "accepted": True,
        "algorithm_id": REPLAY_ID,
        "events_sha256": produced["events_sha256"],
        "frame_count": produced["frame_count"],
        "kind": "sparkinterval.tg.dirichlet_stream_consumer.replay_receipt.v1",
        "precision_bits": precision,
        "receipt_sha256": produced["receipt_sha256"],
    }


def _double_enclosure(value: Any) -> tuple[float, float]:
    exact = _arb_interval_json(value)

    def endpoint(name: str) -> Fraction:
        row = exact[name]
        return Fraction(row["numerator"], row["denominator"])

    lower_q = endpoint("lower")
    upper_q = endpoint("upper")
    lower = float(lower_q)
    upper = float(upper_q)
    if Fraction.from_float(lower) > lower_q:
        lower = math.nextafter(lower, -math.inf)
    if Fraction.from_float(upper) < upper_q:
        upper = math.nextafter(upper, math.inf)
    if not (math.isfinite(lower) and math.isfinite(upper) and lower <= upper):
        _fail("KAT value cannot be represented as a finite double interval")
    return lower, upper


def _complex_double_enclosure(value: Any) -> tuple[float, float, float, float]:
    re_lo, re_hi = _double_enclosure(value.real)
    im_lo, im_hi = _double_enclosure(value.imag)
    return re_lo, re_hi, im_lo, im_hi


def write_known_answer_bundle(path: Path) -> dict[str, Any]:
    """Write a two-frame q=5 Arb KAT through height ten."""

    require_flint()
    ctx.prec = 256
    path.mkdir(parents=True, exist_ok=True)
    control_path = path / "control.ndjson"
    frame_path = path / "frames.bin"
    events_path = path / "events.ndjson"
    receipt_path = path / "receipt.json"
    records = primitive_frequency_records(5)
    by_frequency = {row["frequency_id"]: row for row in records}
    upstream = {
        "all_character_transform_input_sha256": "1" * 64,
        "finite_addback_receipt_sha256": "2" * 64,
        "lattice_tail_receipt_sha256": "3" * 64,
        "residue_adapter_receipt_sha256": "4" * 64,
    }
    frame_shapes = ((0, 65), (65, 64))
    controls = [
        make_control(
            frame_index=index,
            q=5,
            batch_count=batch_count,
            first_t_numerator=5 * first_index,
            t_denominator=64,
            t_step_numerator=5,
            upstream_receipts=upstream,
        )
        for index, (first_index, batch_count) in enumerate(frame_shapes)
    ]
    control_path.write_bytes(b"".join(canonical_json_bytes(row) for row in controls))
    with frame_path.open("wb") as output:
        for first_index, batch_count in frame_shapes:
            order = 4
            output.write(
                OUTPUT_HEADER.pack(
                    OUTPUT_MAGIC,
                    FORMAT_VERSION,
                    5,
                    1,
                    batch_count,
                    order,
                    batch_count * order,
                    modulus_butterflies(5, batch_count=batch_count),
                    0,
                )
            )
            for local_index in range(batch_count):
                t = arb(5 * (first_index + local_index)) / 64
                for frequency_id in range(order):
                    identity = by_frequency.get(frequency_id)
                    value = acb(0)
                    if identity is not None:
                        character = dirichlet_char(5, identity["conrey_number"])
                        value = character.l_function(acb(arb("1/2"), t))
                    output.write(COMPLEX_INTERVAL.pack(*_complex_double_enclosure(value)))
    receipt = consume_paths(
        control_path, frame_path, events_path, receipt_path, precision=192
    )
    audit = audit_known_answer_bundle(path, precision=256)
    return {
        "audit": audit,
        "control_path": str(control_path),
        "events_path": str(events_path),
        "frame_path": str(frame_path),
        "receipt": receipt,
        "receipt_path": str(receipt_path),
    }


def audit_known_answer_bundle(path: Path, *, precision: int = 256) -> dict[str, Any]:
    """Independently compare KAT frame values to FLINT L and Hardy Z."""

    require_flint()
    ctx.prec = precision
    control_path = path / "control.ndjson"
    frame_path = path / "frames.bin"
    controls = [
        validate_control(
            _parse_canonical_line(raw, label="KAT control record"),
            expected_frame_index=index,
        )
        for index, raw in enumerate(control_path.read_bytes().splitlines(keepends=True))
    ]
    roots = {
        row.frequency_id: row
        for row in _character_root_records(5, precision=precision)
    }
    orientations: dict[int, int] = {}
    previous_signs: dict[int, int] = {}
    direct_changes = 0
    compared = 0
    with frame_path.open("rb") as stream:
        for control in controls:
            raw_header = _read_exact(stream, OUTPUT_HEADER.size, label="KAT frame header")
            fields = OUTPUT_HEADER.unpack(raw_header)
            if fields[2] != 5 or fields[4] != control["batch_count"]:
                _fail("KAT frame/control identity differs")
            for batch_index in range(control["batch_count"]):
                ordinate = Fraction(
                    control["first_t_numerator"]
                    + batch_index * control["t_step_numerator"],
                    control["t_denominator"],
                )
                for frequency_id in range(fields[5]):
                    endpoints = COMPLEX_INTERVAL.unpack(
                        _read_exact(stream, COMPLEX_INTERVAL.size, label="KAT value")
                    )
                    root = roots.get(frequency_id)
                    if root is None:
                        continue
                    candidate = _acb_from_binary_rectangle(endpoints)
                    character = dirichlet_char(5, root.conrey_number)
                    direct_l = character.l_function(
                        acb(arb("1/2"), _arb_fraction(ordinate))
                    )
                    if not candidate.overlaps(direct_l):
                        _fail("TGDAFFO1 KAT interval does not enclose direct FLINT L")
                    _completed, stream_sign = _completed_interval_with_q(
                        5, candidate, root, ordinate
                    )
                    hardy = character.hardy_z(_arb_fraction(ordinate))
                    if not hardy.imag.contains(0):
                        _fail("direct FLINT Hardy Z is not real")
                    hardy_sign = 1 if hardy.real > 0 else -1 if hardy.real < 0 else 0
                    if stream_sign == 0 or hardy_sign == 0:
                        _fail("known-answer lattice unexpectedly has indeterminate sign")
                    orientation = orientations.setdefault(
                        root.primitive_ordinal, stream_sign * hardy_sign
                    )
                    if stream_sign != orientation * hardy_sign:
                        _fail("completed-L sign disagrees with direct FLINT Hardy Z")
                    previous = previous_signs.get(root.primitive_ordinal)
                    if previous is not None and previous != hardy_sign:
                        direct_changes += 1
                    previous_signs[root.primitive_ordinal] = hardy_sign
                    compared += 1
        if stream.read(1):
            _fail("trailing KAT frame bytes")
    events = (path / "events.ndjson").read_bytes().splitlines()
    candidate_events = [
        json.loads(raw)
        for raw in events[1:]
        if json.loads(raw).get("event") == "sign_change_candidate"
    ]
    if len(candidate_events) != direct_changes:
        _fail("streamed sign-change count differs from direct Hardy-Z replay")
    return {
        "accepted": True,
        "direct_hardy_sign_changes": direct_changes,
        "direct_l_values_compared": compared,
        "frame_count": len(controls),
        "kind": "sparkinterval.tg.dirichlet_stream_consumer.known_answer.v1",
        "q": 5,
        "root_number_regression_conrey_4_checked": True,
    }


def benchmark(*, q: int = 29, batch_count: int = 64) -> dict[str, Any]:
    """Measure the complete persistent consumer on a generated interval frame."""

    if batch_count <= 0:
        _fail("benchmark batch_count must be positive")
    require_flint()
    with tempfile.TemporaryDirectory(prefix="tg-dirichlet-consumer-bench-") as temporary:
        root = Path(temporary)
        ctx.prec = 256
        records = primitive_frequency_records(q)
        roots = {
            row.frequency_id: row
            for row in _character_root_records(q, precision=256)
        }
        control = make_control(
            frame_index=0,
            q=q,
            batch_count=batch_count,
            first_t_numerator=1,
            t_denominator=64,
            t_step_numerator=5,
            upstream_receipts={
                "all_character_transform_input_sha256": "1" * 64,
                "finite_addback_receipt_sha256": "2" * 64,
                "lattice_tail_receipt_sha256": "3" * 64,
                "residue_adapter_receipt_sha256": "4" * 64,
            },
        )
        (root / "control.ndjson").write_bytes(canonical_json_bytes(control))
        order = math.prod(canonical_component_orders(q))
        with (root / "frames.bin").open("wb") as output:
            output.write(
                OUTPUT_HEADER.pack(
                    OUTPUT_MAGIC,
                    FORMAT_VERSION,
                    q,
                    len(canonical_component_orders(q)),
                    batch_count,
                    order,
                    batch_count * order,
                    modulus_butterflies(q, batch_count=batch_count),
                    0,
                )
            )
            for batch_index in range(batch_count):
                ordinate = Fraction(1 + 5 * batch_index, 64)
                t = _arb_fraction(ordinate)
                for frequency_id in range(order):
                    root_row = roots.get(frequency_id)
                    value = acb(0)
                    if root_row is not None:
                        # Construct a nonzero, exactly real completed target;
                        # this benchmarks the consumer rather than FLINT L.
                        target = arb(
                            1
                            if (batch_index + root_row.primitive_ordinal) % 7
                            else -1
                        )
                        conductor = acb(0, t * (arb(q) / arb.pi()).log() / 2).exp()
                        gamma = acb(
                            arb(1 + 2 * root_row.parity) / 4, t / 2
                        ).gamma()
                        scale = (arb.pi() * t / 4).exp()
                        value = target / (root_row.epsilon * conductor * gamma * scale)
                    output.write(COMPLEX_INTERVAL.pack(*_complex_double_enclosure(value)))
        start = time.perf_counter()
        receipt = consume_paths(
            root / "control.ndjson",
            root / "frames.bin",
            root / "events.ndjson",
            root / "receipt.json",
            precision=192,
        )
        elapsed = time.perf_counter() - start
    return {
        "batch_count": batch_count,
        "elapsed_seconds": elapsed,
        "kind": "sparkinterval.tg.dirichlet_stream_consumer.benchmark.v1",
        "primitive_character_count": len(records),
        "primitive_samples": receipt["primitive_sample_count"],
        "primitive_samples_per_second": receipt["primitive_sample_count"] / elapsed,
        "q": q,
        "root_number_mode": ROOT_NUMBER_MODE,
        "source_projection_permitted": False,
    }


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": "bounded-memory-persistent-completed-L-sign-candidate-component",
        "completed_l_interval_arithmetic": True,
        "consumes_only_primitive_outputs_analytically": True,
        "exact_character_identity_reconstruction": True,
        "external_atom_discharged": False,
        "fresh_arb_replay": True,
        "full_source": False,
        "multiplicity_preserved": True,
        "externally_bounded_event_output_supported": True,
        "maximum_event_output_bytes": MAX_EVENT_OUTPUT_BYTES,
        "raw_event_storage_mode_supported": True,
        "compact_event_storage_mode_supported": True,
        "phase_compact_bundle_storage_mode_supported": True,
        "phase_compact_bundle_is_bounded_arb_oracle_only": True,
        "same_cuda_address_space_phase_reduction_implemented": False,
        "compact_event_summary_binds_order_and_counters": True,
        "associative_per_character_state_schema_implemented": True,
        "adjacent_cross_block_sign_merge_implemented": True,
        "compact_state_supervisor_checkpoint_integration": False,
        "exact_ambiguity_ranges_retained": True,
        "ordered_bracket_records_retained": True,
        "refinement_artifacts_complete": False,
        "source_scale_binary_state_encoding": False,
        "persistent_multi_frame_protocol": True,
        "production_accept": False,
        "root_number_reference_path": ROOT_NUMBER_MODE,
        "root_number_artifact_mode": ARTIFACT_ROOT_NUMBER_MODE,
        "root_number_artifact_integration_ready": True,
        "root_number_source_work": direct_root_source_work(),
        "source": SOURCE_URL,
        "source_performance_ready": False,
        "source_performance_ready_when_TGDRNRO1_is_supplied": True,
        "zero_completeness_claimed": False,
        "remaining": [
            (
                "replay the upstream lattice/tail, q^-s, finite-addback, and "
                "transform semantics rather than only binding their hashes"
            ),
            (
                "checkpoint and replay the associative fixed-q state across "
                "t blocks using a source-scale binary encoding"
            ),
            (
                "implement exception refinement and prove source-approved "
                "paired Turing completeness"
            ),
            "run the full source campaign and connect its accepted receipt to Lean",
        ],
    }


__all__ = [
    "ALGORITHM_ID",
    "COMPACT_EVENT_SCHEMA",
    "COMPACT_EVENT_STORAGE_MODE",
    "COMPACT_STATE_SCHEMA",
    "CONTROL_SCHEMA",
    "DirichletStreamConsumerError",
    "EVENT_FILE_SCHEMA",
    "EVENT_SCHEMA",
    "L_VALUE_SEMANTICS",
    "MAX_EVENT_OUTPUT_BYTES",
    "MAX_EVENT_COUNT",
    "PHASE_COMPACT_BUNDLE_SCHEMA",
    "PHASE_COMPACT_BUNDLE_STORAGE_MODE",
    "RAW_EVENT_STORAGE_MODE",
    "RECEIPT_SCHEMA",
    "REPLAY_ID",
    "ROOT_NUMBER_MODE",
    "audit_known_answer_bundle",
    "benchmark",
    "canonical_json_bytes",
    "capability",
    "combine_associative_event_commitments",
    "combine_character_chunk_states",
    "combine_compact_state_summaries",
    "compact_state_from_event_summary",
    "consume_paths",
    "consume_streams",
    "direct_root_source_work",
    "make_control",
    "root_number_inventory",
    "validate_control",
    "validate_compact_event_summary",
    "validate_compact_state_summary",
    "validate_phase_compact_state_bundle",
    "verify_paths",
    "write_known_answer_bundle",
]

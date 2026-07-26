# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Certified, all-character Dirichlet root-number transform stage.

For one modulus ``q``, the stage constructs the additive character

    a |-> exp(+2*pi*i*a/q)

in the canonical CRT residue order used by ``TGDAFFI1``.  One existing
all-character CRT/Bluestein transform therefore returns every Gauss sum
``tau(chi)``.  Primitive frequencies are selected by the canonical campaign
map and converted to the phase used to make the completed L-function real.

The implementation is a bounded streaming component.  It does not isolate or
count zeros and it does not discharge Platt's theorem or a Lean atom.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct
import time
from typing import Any, BinaryIO, Mapping, NoReturn

from tg_verifier.dirichlet_allchars_stage import (
    COMPLEX_INTERVAL,
    FORMAT_VERSION as ALLCHARS_FORMAT_VERSION,
    INPUT_HEADER,
    INPUT_MAGIC,
    OUTPUT_HEADER,
    OUTPUT_MAGIC,
    canonical_component_orders,
    canonical_residue_order,
    modulus_butterflies,
    primitive_frequency_records,
)
from tg_verifier.dirichlet_campaign import (
    _crt_pair,
    _smallest_prime_factors,
    _unrank_local,
    factor_prime_powers,
    local_primitive_character_count,
    primitive_character_count,
)
from tg_verifier.dirichlet_fused_stage import canonical_group_model
from tg_verifier.dirichlet_lattice_stage import SOURCE_Q_START, SOURCE_Q_STOP


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ACCEPTED_MANUSCRIPT_URL = (
    "https://research-information.bris.ac.uk/ws/portalfiles/portal/"
    "67056136/platt_grh3.0.pdf"
)

ADDITIVE_ALGORITHM_ID = "arb-one-seed-positive-additive-character-v1"
ROOT_ALGORITHM_ID = "tgdaff-all-character-gauss-root-phase-v1"
DIRECT_REPLAY_ID = "arb-direct-character-gauss-sum-v1"
ADDITIVE_RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_root.additive_input.v1"
ROOT_RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_root.receipt.v1"
STREAM_CONTROL_SCHEMA = "sparkinterval.tg.dirichlet_root.control.v1"
STREAM_SUMMARY_SCHEMA = "sparkinterval.tg.dirichlet_root.stream_summary.v1"

ROOT_MAGIC = b"TGDRNRO1"
ROOT_FORMAT_VERSION = 1
ROOT_RECORD = struct.Struct("<dddd")
ROOT_HEADER = struct.Struct("<8sIIIIQ32s32s")
MIN_PRECISION_BITS = 128
MAX_PRECISION_BITS = 4096
MAX_CONTROL_LINE_BYTES = 64 * 1024

TRANSFORM_CONVENTION = (
    "TGDAFF output k=sum_e X[e]*exp(+2*pi*i*sum_j(e_j*k_j/n_j)); "
    "X[e]=exp(+2*pi*i*canonical_residue(e)/q), hence output k=tau(chi_k)"
)
COMPLETED_PHASE_CONVENTION = (
    "parity a=(1-chi(-1))/2; w= tau(chi)/(i^a*sqrt(q)); "
    "hardy_multiplier=principal_sqrt(conj(w)); the completed critical-line "
    "value is hardy_multiplier*(q/pi)^(it/2)*Gamma((1/2+a+it)/2)*"
    "exp(pi*t/4)*L(1/2+it,chi)"
)
CONVENTION_SHA256 = hashlib.sha256(
    (TRANSFORM_CONVENTION + "\n" + COMPLETED_PHASE_CONVENTION + "\n").encode(
        "ascii"
    )
).hexdigest()

PINNED_SOURCE_WORK = {
    "active_moduli": 292_500,
    "additive_recurrence_complex_multiplications": 59_962_402_500,
    "additive_transcendental_seeds": 292_500,
    "all_character_input_values": 40_503_165_302,
    "component_dimensions_across_active_q": 816_177,
    "cross_q_cacheable_twiddle_enclosures": 12_952_682_706,
    "current_per_q_twiddle_enclosures": 71_135_060_058,
    "distinct_component_orders": 34_000,
    "distinct_q_component_plans": 219_015,
    "primitive_root_records": 29_547_446_729,
    "radix2_butterflies": 2_645_418_549_056,
    "root_stream_bytes": 945_546_375_328,
}


class DirichletRootNumberStageError(RuntimeError):
    """A convention, enclosure, identity, or artifact failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletRootNumberStageError(message)


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


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def _dyadic(value: Any) -> Fraction:
    mantissa, exponent = value.mid().man_exp()
    mantissa = int(mantissa)
    exponent = int(exponent)
    if exponent >= 0:
        return Fraction(mantissa << exponent)
    return Fraction(mantissa, 1 << (-exponent))


def _outward_binary_interval(value: Any) -> tuple[float, float]:
    """Return binary64 endpoints proven to contain one finite Arb interval."""

    midpoint = _dyadic(value)
    radius = abs(_dyadic(value.rad()))
    lower = midpoint - radius
    upper = midpoint + radius
    lower_float = float(lower)
    upper_float = float(upper)
    if Fraction.from_float(lower_float) > lower:
        lower_float = math.nextafter(lower_float, -math.inf)
    if Fraction.from_float(upper_float) < upper:
        upper_float = math.nextafter(upper_float, math.inf)
    if not (
        math.isfinite(lower_float)
        and math.isfinite(upper_float)
        and lower_float <= upper_float
    ):
        _fail("Arb interval is not representable by finite binary64 endpoints")
    return lower_float, upper_float


def _binary_interval(lower: float, upper: float):
    if not (math.isfinite(lower) and math.isfinite(upper) and lower <= upper):
        _fail("malformed binary64 interval")
    lower_q = Fraction.from_float(lower)
    upper_q = Fraction.from_float(upper)
    midpoint = (lower_q + upper_q) / 2
    radius = (upper_q - lower_q) / 2
    return arb(
        f"{midpoint.numerator}/{midpoint.denominator}",
        f"{radius.numerator}/{radius.denominator}",
    )


def _binary_rectangle(endpoints: tuple[float, float, float, float]):
    re_lo, re_hi, im_lo, im_hi = endpoints
    return acb(_binary_interval(re_lo, re_hi), _binary_interval(im_lo, im_hi))


def _pack_rectangle(value: Any) -> bytes:
    re_lo, re_hi = _outward_binary_interval(value.real)
    im_lo, im_hi = _outward_binary_interval(value.imag)
    encoded = COMPLEX_INTERVAL.pack(re_lo, re_hi, im_lo, im_hi)
    reconstructed = _binary_rectangle((re_lo, re_hi, im_lo, im_hi))
    if not reconstructed.contains(value):
        _fail("binary64 serialization did not contain the Arb rectangle")
    return encoded


def _validate_precision(precision: int) -> None:
    if not MIN_PRECISION_BITS <= precision <= MAX_PRECISION_BITS:
        _fail(f"precision must be in {MIN_PRECISION_BITS}..{MAX_PRECISION_BITS}")


def _additive_header(q: int) -> bytes:
    orders = canonical_component_orders(q)
    order = math.prod(orders)
    return INPUT_HEADER.pack(
        INPUT_MAGIC,
        ALLCHARS_FORMAT_VERSION,
        q,
        len(orders),
        1,
        order,
        0,
        1,
        1,
        order,
        0,
    )


def primitive_frequency_records_bulk(q: int) -> tuple[dict[str, int], ...]:
    """Build the canonical primitive map from one factored per-q plan.

    The legacy scalar helper deliberately accepts an optional SPF table but
    its all-character wrapper calls it without one and reconstructs both the
    sieve and primitive roots for every character.  That is useful as an
    independent KAT oracle but quadratic as a source producer.  This bulk
    implementation computes the same mapping with one factorization and one
    generator reconstruction per modulus.
    """

    spf = _smallest_prime_factors(q)
    factors = factor_prime_powers(q, spf)
    models = canonical_group_model(q)
    if len(factors) != len(models):
        _fail("bulk primitive plan factor count differs from canonical group model")
    radices = [local_primitive_character_count(prime, exponent) for prime, exponent in factors]
    total = math.prod(radices)
    if total != primitive_character_count(q, spf):
        _fail("bulk primitive plan count differs")
    orders = canonical_component_orders(q)
    records: list[dict[str, int]] = []
    for ordinal in range(total):
        local_ordinals = [0] * len(radices)
        remainder = ordinal
        for index in range(len(radices) - 1, -1, -1):
            remainder, local_ordinals[index] = divmod(remainder, radices[index])
        if remainder:
            _fail("bulk primitive ordinal unranking overflow")
        frequencies: list[int] = []
        parity = 0
        conrey_number = 0
        conrey_modulus = 1
        for (prime, exponent), model, local_ordinal in zip(
            factors, models, local_ordinals
        ):
            exponents = _unrank_local(prime, exponent, local_ordinal)
            if len(exponents) != len(model.components):
                _fail("bulk primitive exponents differ from group components")
            frequencies.extend(exponents)
            parity ^= exponents[0] & 1
            local_number = 1
            for component, frequency in zip(model.components, exponents):
                local_number = (
                    local_number
                    * pow(component.generator, frequency, model.modulus)
                ) % model.modulus
            conrey_number, conrey_modulus = _crt_pair(
                conrey_number, conrey_modulus, local_number, model.modulus
            )
        frequency_id = 0
        stride = 1
        for frequency, order in zip(frequencies, orders):
            if not 0 <= frequency < order:
                _fail("bulk primitive frequency is outside its component")
            frequency_id += frequency * stride
            stride *= order
        records.append(
            {
                "primitive_ordinal": ordinal,
                "frequency_id": frequency_id,
                "conrey_number": conrey_number,
                "parity": parity,
            }
        )
    if len({row["frequency_id"] for row in records}) != len(records):
        _fail("bulk primitive frequency map is not injective")
    return tuple(records)


def write_additive_input(
    path: Path,
    *,
    q: int,
    precision: int = 192,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Write the canonical rigorous additive-character ``TGDAFFI1`` frame.

    One Arb exponential seeds a sequential power recurrence.  The recurrence
    is evaluated through exponent ``q`` and must close around one.  Unit
    residues are placed into the transform's canonical mixed-radix order.
    """

    require_flint()
    _validate_precision(precision)
    ctx.prec = precision
    residues = canonical_residue_order(q)
    orders = canonical_component_orders(q)
    inverse = [-1] * q
    for ordinal, residue in enumerate(residues):
        if not 0 < residue < q or inverse[residue] != -1:
            _fail("canonical residue adapter is not injective on nonzero residues")
        inverse[residue] = ordinal
    values = bytearray(len(residues) * COMPLEX_INTERVAL.size)
    seed = acb(0, 2 * arb.pi() / q).exp()
    if not abs(seed).contains(1):
        _fail("additive-character seed does not enclose unit modulus")
    power = acb(1)
    for residue in range(1, q):
        power *= seed
        ordinal = inverse[residue]
        if ordinal >= 0:
            values[
                ordinal * COMPLEX_INTERVAL.size :
                (ordinal + 1) * COMPLEX_INTERVAL.size
            ] = _pack_rectangle(power)
    if not (power * seed).contains(acb(1)):
        _fail("additive-character power recurrence did not close at exponent q")
    header = _additive_header(q)
    raw = header + values
    _atomic_write(path, raw)
    receipt: dict[str, Any] = {
        "algorithm_id": ADDITIVE_ALGORITHM_ID,
        "all_intervals_outward": True,
        "author": AUTHOR,
        "batch_count": 1,
        "bytes": len(raw),
        "canonical_residue_order_reconstructed": True,
        "classification": "certified_transform_input_not_a_gauss_sum_or_grh_claim",
        "component_orders": list(orders),
        "convention_sha256": CONVENTION_SHA256,
        "format": "TGDAFFI1",
        "group_order": len(residues),
        "input_sha256": sha256_bytes(raw),
        "kind": ADDITIVE_RECEIPT_SCHEMA,
        "precision_bits": precision,
        "q": q,
        "recurrence_closure_verified": True,
        "transcendental_seed_count": 1,
        "value_count": len(residues),
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    if receipt_path is not None:
        _atomic_write(receipt_path, canonical_json_bytes(receipt))
    return receipt


def verify_additive_input(
    path: Path, receipt: Mapping[str, Any], *, replay_arithmetic: bool = False
) -> dict[str, Any]:
    """Verify identity/hash, optionally regenerating every Arb rectangle."""

    raw = path.read_bytes()
    required = {
        "algorithm_id",
        "all_intervals_outward",
        "author",
        "batch_count",
        "bytes",
        "canonical_residue_order_reconstructed",
        "classification",
        "component_orders",
        "convention_sha256",
        "format",
        "group_order",
        "input_sha256",
        "kind",
        "precision_bits",
        "q",
        "receipt_sha256",
        "recurrence_closure_verified",
        "transcendental_seed_count",
        "value_count",
    }
    if set(receipt) != required:
        _fail("additive input receipt keys differ")
    body = dict(receipt)
    claimed_receipt_sha = body.pop("receipt_sha256")
    if claimed_receipt_sha != sha256_bytes(canonical_json_bytes(body)):
        _fail("additive input receipt hash differs")
    q = receipt["q"]
    if isinstance(q, bool) or not isinstance(q, int):
        _fail("additive input q is not an integer")
    orders = canonical_component_orders(q)
    order = math.prod(orders)
    if (
        receipt["kind"] != ADDITIVE_RECEIPT_SCHEMA
        or receipt["algorithm_id"] != ADDITIVE_ALGORITHM_ID
        or receipt["format"] != "TGDAFFI1"
        or receipt["author"] != AUTHOR
        or receipt["batch_count"] != 1
        or receipt["bytes"] != len(raw)
        or receipt["component_orders"] != list(orders)
        or receipt["group_order"] != order
        or receipt["value_count"] != order
        or receipt["convention_sha256"] != CONVENTION_SHA256
        or receipt["input_sha256"] != sha256_bytes(raw)
        or raw[: INPUT_HEADER.size] != _additive_header(q)
        or len(raw) != INPUT_HEADER.size + order * COMPLEX_INTERVAL.size
    ):
        _fail("additive input identity, shape, convention, or digest differs")
    for offset in range(INPUT_HEADER.size, len(raw), COMPLEX_INTERVAL.size):
        endpoints = COMPLEX_INTERVAL.unpack_from(raw, offset)
        if not (
            all(math.isfinite(value) for value in endpoints)
            and endpoints[0] <= endpoints[1]
            and endpoints[2] <= endpoints[3]
        ):
            _fail("additive input contains a malformed interval")
    if replay_arithmetic:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            replay = Path(temporary) / "input.bin"
            regenerated = write_additive_input(
                replay, q=q, precision=receipt["precision_bits"]
            )
            if regenerated["input_sha256"] != receipt["input_sha256"]:
                _fail("fresh additive-character arithmetic replay differs")
    return {
        "accepted": True,
        "arithmetic_replayed": replay_arithmetic,
        "input_sha256": receipt["input_sha256"],
        "q": q,
    }


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
class RootFrameResult:
    receipt: dict[str, Any]
    raw: bytes


def consume_transform_frame(
    stream: BinaryIO,
    *,
    q: int,
    additive_input_sha256: str,
    additive_receipt_sha256: str,
    precision: int = 192,
) -> RootFrameResult:
    """Normalize one ``TGDAFFO1`` Gauss-sum frame into one root frame."""

    require_flint()
    _validate_precision(precision)
    ctx.prec = precision
    for label, digest in (
        ("additive_input_sha256", additive_input_sha256),
        ("additive_receipt_sha256", additive_receipt_sha256),
    ):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail(f"{label} is not a lowercase SHA-256 digest")
    raw_header = _read_exact(stream, OUTPUT_HEADER.size, label="TGDAFFO1 header")
    (
        magic,
        version,
        frame_q,
        component_count,
        batch_count,
        group_order,
        value_count,
        butterflies,
        elapsed_nanoseconds,
    ) = OUTPUT_HEADER.unpack(raw_header)
    orders = canonical_component_orders(q)
    expected_group_order = math.prod(orders)
    if (
        magic != OUTPUT_MAGIC
        or version != ALLCHARS_FORMAT_VERSION
        or frame_q != q
        or component_count != len(orders)
        or batch_count != 1
        or group_order != expected_group_order
        or value_count != expected_group_order
        or butterflies != modulus_butterflies(q)
    ):
        _fail("TGDAFFO1 identity, convention, or one-transform shape differs")

    identities = primitive_frequency_records_bulk(q)
    if len(identities) != primitive_character_count(q):
        _fail("primitive frequency inventory count differs")
    by_frequency = {row["frequency_id"]: row for row in identities}
    if len(by_frequency) != len(identities):
        _fail("primitive frequency inventory is not injective")
    records = bytearray(len(identities) * ROOT_RECORD.size)
    seen_ordinals = bytearray(len(identities))
    seen_count = 0
    transform_digest = hashlib.sha256(raw_header)
    identity_digest = hashlib.sha256()
    for identity in identities:
        identity_digest.update(canonical_json_bytes(identity))
    for frequency_id in range(group_order):
        raw_value = _read_exact(stream, COMPLEX_INTERVAL.size, label="TGDAFFO1 value")
        transform_digest.update(raw_value)
        endpoints = COMPLEX_INTERVAL.unpack(raw_value)
        if not (
            all(math.isfinite(value) for value in endpoints)
            and endpoints[0] <= endpoints[1]
            and endpoints[2] <= endpoints[3]
        ):
            _fail("TGDAFFO1 contains a malformed interval")
        identity = by_frequency.get(frequency_id)
        if identity is None:
            continue
        tau = _binary_rectangle(endpoints)
        parity = identity["parity"]
        if parity not in (0, 1):
            _fail("primitive character parity is not zero or one")
        parity_phase = acb(1) if parity == 0 else acb(0, 1)
        root_number = tau / (parity_phase * arb(q).sqrt())
        if not abs(root_number).contains(1):
            _fail("Gauss-sum root-number enclosure does not contain unit modulus")
        hardy_multiplier = root_number.conjugate().sqrt()
        if not (hardy_multiplier**2).overlaps(root_number.conjugate()):
            _fail("completed-L square-root phase convention did not verify")
        if not abs(hardy_multiplier).contains(1):
            _fail("completed-L multiplier does not contain unit modulus")
        ordinal = identity["primitive_ordinal"]
        if (
            not 0 <= ordinal < len(identities)
            or seen_ordinals[ordinal] != 0
        ):
            _fail("primitive ordinal is outside its canonical unique range")
        records[
            ordinal * ROOT_RECORD.size : (ordinal + 1) * ROOT_RECORD.size
        ] = _pack_rectangle(hardy_multiplier)
        seen_ordinals[ordinal] = 1
        seen_count += 1
    if seen_count != len(identities):
        _fail("TGDAFFO1 frame omitted a primitive character frequency")

    transform_sha = transform_digest.hexdigest()
    root_header = ROOT_HEADER.pack(
        ROOT_MAGIC,
        ROOT_FORMAT_VERSION,
        q,
        len(orders),
        ROOT_RECORD.size,
        len(identities),
        bytes.fromhex(additive_input_sha256),
        bytes.fromhex(transform_sha),
    )
    root_raw = root_header + records
    receipt: dict[str, Any] = {
        "additive_input_receipt_sha256": additive_receipt_sha256,
        "additive_input_sha256": additive_input_sha256,
        "algorithm_id": ROOT_ALGORITHM_ID,
        "all_intervals_outward": True,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": "certified_root_number_component_not_zero_or_grh_closure",
        "completed_phase_convention": COMPLETED_PHASE_CONVENTION,
        "component_orders": list(orders),
        "convention_sha256": CONVENTION_SHA256,
        "external_atom_discharged": False,
        "format": "TGDRNRO1",
        "full_source_campaign_run": False,
        "group_order": group_order,
        "kind": ROOT_RECEIPT_SCHEMA,
        "precision_bits": precision,
        "primitive_character_count": len(identities),
        "primitive_identity_rows_sha256": identity_digest.hexdigest(),
        "production_accept": False,
        "q": q,
        "radix2_butterflies": butterflies,
        "root_artifact_bytes": len(root_raw),
        "root_artifact_sha256": sha256_bytes(root_raw),
        "root_record_semantics": "principal_sqrt(conj(tau(chi)/(i^parity*sqrt(q))))",
        "source_scalable_algorithm_implemented": True,
        "source_stream_splitter_and_root_catalog_implemented": True,
        "source_root_catalog_generated": False,
        "source_performance_ready": False,
        "source_performance_blocker": "the exact-512-MiB persistent TGDAFF service now reserves and reuses all 19 convolution-root tables and independently replays its split-cache accounting, but the root-number producer is not wired into that service or source-scale measured; the remaining order-specific chirp/kernel preparation still requires receipt-preserving scheduling or cluster measurement",
        "transform_convention": TRANSFORM_CONVENTION,
        "transform_elapsed_nanoseconds_reported": elapsed_nanoseconds,
        "transform_output_sha256": transform_sha,
        "zero_completeness_claimed": False,
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(receipt))
    return RootFrameResult(receipt=receipt, raw=root_raw)


def consume_transform_path(
    transform_path: Path,
    root_path: Path,
    receipt_path: Path,
    *,
    q: int,
    additive_receipt: Mapping[str, Any],
    precision: int = 192,
) -> dict[str, Any]:
    if additive_receipt.get("q") != q:
        _fail("additive input receipt q differs from transform request")
    with transform_path.open("rb") as stream:
        result = consume_transform_frame(
            stream,
            q=q,
            additive_input_sha256=str(additive_receipt.get("input_sha256", "")),
            additive_receipt_sha256=str(additive_receipt.get("receipt_sha256", "")),
            precision=precision,
        )
        if stream.read(1):
            _fail("TGDAFFO1 has trailing bytes")
    _atomic_write(root_path, result.raw)
    _atomic_write(receipt_path, canonical_json_bytes(result.receipt))
    return result.receipt


def _validate_root_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    if claimed != sha256_bytes(canonical_json_bytes(body)):
        _fail("root receipt hash differs")
    if (
        receipt.get("kind") != ROOT_RECEIPT_SCHEMA
        or receipt.get("algorithm_id") != ROOT_ALGORITHM_ID
        or receipt.get("format") != "TGDRNRO1"
        or receipt.get("author") != AUTHOR
        or receipt.get("convention_sha256") != CONVENTION_SHA256
        or receipt.get("transform_convention") != TRANSFORM_CONVENTION
        or receipt.get("completed_phase_convention") != COMPLETED_PHASE_CONVENTION
        or receipt.get("external_atom_discharged") is not False
        or receipt.get("zero_completeness_claimed") is not False
    ):
        _fail("root receipt schema, convention, or claim boundary differs")
    return dict(receipt)


def read_root_artifact_bytes(
    raw: bytes, receipt: Mapping[str, Any] | None = None
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    """Fail-closed validate one in-memory compact primitive root artifact."""

    require_flint()
    checked_receipt: dict[str, Any] | None = None
    if receipt is not None:
        checked_receipt = _validate_root_receipt(receipt)
        if checked_receipt.get("root_artifact_bytes") != len(raw):
            _fail("root receipt root_artifact_bytes differs from TGDRNRO1")
        if checked_receipt.get("root_artifact_sha256") != sha256_bytes(raw):
            _fail("root receipt root_artifact_sha256 differs from TGDRNRO1")
    if len(raw) < ROOT_HEADER.size:
        _fail("truncated TGDRNRO1 header")
    (
        magic,
        version,
        q,
        component_count,
        record_size,
        count,
        input_digest,
        transform_digest,
    ) = ROOT_HEADER.unpack_from(raw)
    orders = canonical_component_orders(q)
    identities = primitive_frequency_records_bulk(q)
    if (
        magic != ROOT_MAGIC
        or version != ROOT_FORMAT_VERSION
        or component_count != len(orders)
        or record_size != ROOT_RECORD.size
        or count != len(identities)
        or len(raw) != ROOT_HEADER.size + count * ROOT_RECORD.size
    ):
        _fail("TGDRNRO1 identity or size differs")
    roots: list[Any] = []
    for ordinal in range(count):
        endpoints = ROOT_RECORD.unpack_from(
            raw, ROOT_HEADER.size + ordinal * ROOT_RECORD.size
        )
        value = _binary_rectangle(endpoints)
        if not abs(value).contains(1):
            _fail("stored completed-L phase does not contain unit modulus")
        roots.append(value)
    metadata = {
        "additive_input_sha256": input_digest.hex(),
        "component_orders": list(orders),
        "primitive_character_count": count,
        "q": q,
        "root_artifact_bytes": len(raw),
        "root_artifact_sha256": sha256_bytes(raw),
        "transform_output_sha256": transform_digest.hex(),
    }
    if checked_receipt is not None:
        for key in (
            "additive_input_sha256",
            "component_orders",
            "primitive_character_count",
            "q",
            "root_artifact_bytes",
            "root_artifact_sha256",
            "transform_output_sha256",
        ):
            if checked_receipt.get(key) != metadata[key]:
                _fail(f"root receipt {key} differs from TGDRNRO1")
    return metadata, tuple(roots)


def read_root_artifact(
    path: Path, receipt: Mapping[str, Any] | None = None
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    """Read and fail-closed validate a compact primitive root artifact."""

    return read_root_artifact_bytes(path.read_bytes(), receipt)


def direct_root_records(q: int, *, precision: int = 256) -> tuple[dict[str, Any], ...]:
    """Independent quadratic Arb replay intended only for small/KAT moduli."""

    require_flint()
    _validate_precision(precision)
    ctx.prec = precision
    answer: list[dict[str, Any]] = []
    for identity in primitive_frequency_records_bulk(q):
        conrey = identity["conrey_number"]
        character = dirichlet_char(q, conrey)
        if (
            character.modulus() != q
            or character.number() != conrey
            or character.conductor() != q
            or not character.is_primitive()
            or character.parity() != identity["parity"]
        ):
            _fail("FLINT direct character identity differs from canonical map")
        exponent_denominator = int(character.group().exponent())
        if exponent_denominator <= 0:
            _fail("Dirichlet group exponent is not positive")
        tau = acb(0)
        for residue in range(1, q + 1):
            exponent = character.chi_exponent(residue)
            if exponent is None:
                continue
            chi = acb(0, 2 * arb.pi() * int(exponent) / exponent_denominator).exp()
            additive = acb(0, 2 * arb.pi() * residue / q).exp()
            tau += chi * additive
        parity_phase = acb(1) if identity["parity"] == 0 else acb(0, 1)
        root_number = tau / (parity_phase * arb(q).sqrt())
        multiplier = root_number.conjugate().sqrt()
        if not abs(root_number).contains(1) or not abs(multiplier).contains(1):
            _fail("direct Arb Gauss sum did not certify a unit root number")
        answer.append({**identity, "hardy_multiplier": multiplier, "tau": tau})
    return tuple(answer)


def direct_replay_artifact(
    path: Path, receipt: Mapping[str, Any], *, precision: int = 256
) -> dict[str, Any]:
    metadata, candidates = read_root_artifact(path, receipt)
    expected = direct_root_records(metadata["q"], precision=precision)
    if len(expected) != len(candidates):
        _fail("direct root replay count differs")
    for row, candidate in zip(expected, candidates):
        if not candidate.contains(row["hardy_multiplier"]):
            _fail(
                "root artifact does not contain independent direct Arb replay "
                f"for Conrey {row['conrey_number']}"
            )
    return {
        "accepted": True,
        "algorithm_id": DIRECT_REPLAY_ID,
        "character_count": len(expected),
        "q": metadata["q"],
        "root_artifact_sha256": metadata["root_artifact_sha256"],
    }


def _reject_float(value: str) -> NoReturn:
    _fail(f"JSON floating point is forbidden in stream control: {value}")


def _reject_constant(value: str) -> NoReturn:
    _fail(f"nonfinite JSON is forbidden in stream control: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    answer: dict[str, Any] = {}
    for key, value in pairs:
        if key in answer:
            _fail(f"duplicate JSON key in stream control: {key}")
        answer[key] = value
    return answer


def _parse_control(raw: bytes, *, expected_index: int) -> dict[str, Any]:
    if not raw.endswith(b"\n") or len(raw) > MAX_CONTROL_LINE_BYTES:
        _fail("control is not one bounded newline-terminated record")
    try:
        value = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletRootNumberStageError(f"invalid control record: {error}") from error
    required = {
        "additive_input_receipt_sha256",
        "additive_input_sha256",
        "convention_sha256",
        "frame_index",
        "kind",
        "q",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or canonical_json_bytes(value) != raw
        or value["kind"] != STREAM_CONTROL_SCHEMA
        or value["frame_index"] != expected_index
        or value["convention_sha256"] != CONVENTION_SHA256
    ):
        _fail("control identity, key set, index, or convention differs")
    if isinstance(value["q"], bool) or not isinstance(value["q"], int):
        _fail("control q is not an integer")
    canonical_component_orders(value["q"])
    return value


def make_stream_control(
    *, frame_index: int, q: int, additive_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    if additive_receipt.get("q") != q:
        _fail("stream control additive receipt q differs")
    value = {
        "additive_input_receipt_sha256": additive_receipt.get("receipt_sha256"),
        "additive_input_sha256": additive_receipt.get("input_sha256"),
        "convention_sha256": CONVENTION_SHA256,
        "frame_index": frame_index,
        "kind": STREAM_CONTROL_SCHEMA,
        "q": q,
    }
    return _parse_control(canonical_json_bytes(value), expected_index=frame_index)


def consume_streams(
    control_stream: BinaryIO,
    transform_stream: BinaryIO,
    root_stream: BinaryIO,
    receipt_stream: BinaryIO,
    summary_path: Path,
    *,
    precision: int = 192,
) -> dict[str, Any]:
    """Persistently consume concatenated transforms with O(max phi(q)) RAM."""

    _validate_precision(precision)
    frame_index = 0
    previous_q = 0
    receipt_chain = bytes(32)
    root_chain = hashlib.sha256()
    root_bytes = 0
    root_records = 0
    while True:
        raw_control = control_stream.readline(MAX_CONTROL_LINE_BYTES + 1)
        if raw_control == b"":
            break
        control = _parse_control(raw_control, expected_index=frame_index)
        q = control["q"]
        if q <= previous_q:
            _fail("persistent root-number stream q values are not strictly increasing")
        result = consume_transform_frame(
            transform_stream,
            q=q,
            additive_input_sha256=control["additive_input_sha256"],
            additive_receipt_sha256=control["additive_input_receipt_sha256"],
            precision=precision,
        )
        root_stream.write(result.raw)
        root_chain.update(result.raw)
        receipt_raw = canonical_json_bytes(result.receipt)
        receipt_stream.write(receipt_raw)
        receipt_chain = hashlib.sha256(receipt_chain + hashlib.sha256(receipt_raw).digest()).digest()
        root_bytes += len(result.raw)
        root_records += result.receipt["primitive_character_count"]
        frame_index += 1
        previous_q = q
    if frame_index == 0:
        _fail("persistent root-number stream is empty")
    if transform_stream.read(1):
        _fail("transform stream has trailing bytes after controls ended")
    summary: dict[str, Any] = {
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": "bounded_root_number_stream_not_zero_or_grh_closure",
        "convention_sha256": CONVENTION_SHA256,
        "external_atom_discharged": False,
        "frame_count": frame_index,
        "full_source_campaign_run": False,
        "kind": STREAM_SUMMARY_SCHEMA,
        "maximum_retained_working_set": "one transformed modulus and one primitive root frame",
        "persistent_process": True,
        "production_accept": False,
        "receipt_chain_sha256": receipt_chain.hex(),
        "root_record_count": root_records,
        "root_stream_bytes": root_bytes,
        "root_stream_sha256": root_chain.hexdigest(),
        "zero_completeness_claimed": False,
    }
    summary["summary_sha256"] = sha256_bytes(canonical_json_bytes(summary))
    _atomic_write(summary_path, canonical_json_bytes(summary))
    return summary


@lru_cache(maxsize=1)
def source_work() -> dict[str, Any]:
    """Recompute exact source-domain work for the large-q root stage."""

    spf = _smallest_prime_factors(SOURCE_Q_STOP)
    active_moduli = 0
    recurrences = 0
    group_values = 0
    root_records = 0
    butterflies = 0
    maximum_group_order = 0
    maximum_group_q = 0
    maximum_butterflies = 0
    maximum_butterfly_q = 0
    plans: set[tuple[int, ...]] = set()
    component_orders: set[int] = set()
    convolution_lengths: set[int] = set()
    component_dimensions = 0
    current_twiddles = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        primitive_count = primitive_character_count(q, spf)
        if primitive_count == 0:
            continue
        active_moduli += 1
        recurrences += q - 1
        orders = canonical_component_orders(q)
        plans.add(orders)
        order = math.prod(orders)
        modulus_work = modulus_butterflies(q)
        for component_order in orders:
            convolution = 1 << (2 * component_order - 2).bit_length()
            component_dimensions += 1
            component_orders.add(component_order)
            convolution_lengths.add(convolution)
            current_twiddles += 2 * component_order + 2 * (convolution - 1)
        group_values += order
        root_records += primitive_count
        butterflies += modulus_work
        if order > maximum_group_order:
            maximum_group_order = order
            maximum_group_q = q
        if modulus_work > maximum_butterflies:
            maximum_butterflies = modulus_work
            maximum_butterfly_q = q
    recomputed = {
        "active_moduli": active_moduli,
        "additive_recurrence_complex_multiplications": recurrences,
        "additive_transcendental_seeds": active_moduli,
        "all_character_input_values": group_values,
        "component_dimensions_across_active_q": component_dimensions,
        "cross_q_cacheable_twiddle_enclosures": (
            2 * sum(component_orders)
            + 2 * sum(length - 1 for length in convolution_lengths)
        ),
        "current_per_q_twiddle_enclosures": current_twiddles,
        "distinct_component_orders": len(component_orders),
        "distinct_q_component_plans": len(plans),
        "primitive_root_records": root_records,
        "radix2_butterflies": butterflies,
        "root_stream_bytes": root_records * ROOT_RECORD.size + active_moduli * ROOT_HEADER.size,
    }
    if recomputed != PINNED_SOURCE_WORK:
        _fail(f"source root-number work inventory changed: {recomputed}")
    return {
        "atom_id": ATOM_ID,
        "classification": "exact_source_work_not_execution_or_grh_evidence",
        "counts": recomputed,
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "maximum_single_modulus": {
            "group_order": maximum_group_order,
            "group_order_q": maximum_group_q,
            "radix2_butterflies": maximum_butterflies,
            "radix2_butterflies_q": maximum_butterfly_q,
            "root_working_set_upper_bound_bytes": ROOT_HEADER.size + maximum_group_order * ROOT_RECORD.size,
        },
        "streaming_policy": "consume each root frame with its modulus and retain only hash chains; retaining the entire source root stream would require about 945.5 GB",
    }


def capability() -> dict[str, Any]:
    return {
        "accepted_manuscript": ACCEPTED_MANUSCRIPT_URL,
        "additive_algorithm": ADDITIVE_ALGORITHM_ID,
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "classification": "source_scalable_root_number_component_not_atom_closure",
        "closes_external_atom": False,
        "completed_phase_convention": COMPLETED_PHASE_CONVENTION,
        "convention_sha256": CONVENTION_SHA256,
        "direct_replay": DIRECT_REPLAY_ID,
        "full_source_campaign_run": False,
        "implemented": [
            "one rigorous Arb additive-character seed per modulus",
            "outward Arb power recurrence in canonical actual-residue order",
            "one existing TGDAFF all-character transform per active modulus",
            "canonical primitive frequency, Conrey number, and parity filtering",
            "tau/(i^parity*sqrt(q)) and principal sqrt(conjugate) completed-L phase",
            "compact primitive-only hash-bound binary frames",
            "persistent concatenated-frame protocol with bounded per-q memory",
            "exact-512-MiB split TGDAFF root pool and order-plan LRU with independent summary replay",
            "TGDRNRO1 artifact lookup in the completed-L stream consumer",
            "fresh quadratic direct Arb replay for independent small-modulus KATs",
        ],
        "not_implemented": [
            "source-supervisor wiring for the cross-q TGDAFF service and GPU additive recurrence kernel",
            "receipt-preserving scheduling or cluster measurement for remaining order-specific preparation",
            "zero isolation, exception upsampling, and Turing completeness",
            "full source campaign execution or Lean certificate bridge",
        ],
        "production_accept": False,
        "root_algorithm": ROOT_ALGORITHM_ID,
        "source": SOURCE_URL,
        "source_scalable_algorithm_implemented": True,
        "source_performance_ready": False,
        "transform_convention": TRANSFORM_CONVENTION,
    }


__all__ = [
    "ADDITIVE_ALGORITHM_ID",
    "ADDITIVE_RECEIPT_SCHEMA",
    "COMPLETED_PHASE_CONVENTION",
    "CONVENTION_SHA256",
    "DIRECT_REPLAY_ID",
    "DirichletRootNumberStageError",
    "ROOT_ALGORITHM_ID",
    "ROOT_FORMAT_VERSION",
    "ROOT_HEADER",
    "ROOT_MAGIC",
    "ROOT_RECEIPT_SCHEMA",
    "ROOT_RECORD",
    "STREAM_CONTROL_SCHEMA",
    "STREAM_SUMMARY_SCHEMA",
    "TRANSFORM_CONVENTION",
    "capability",
    "canonical_json_bytes",
    "consume_streams",
    "consume_transform_frame",
    "consume_transform_path",
    "direct_replay_artifact",
    "direct_root_records",
    "make_stream_control",
    "primitive_frequency_records_bulk",
    "read_root_artifact",
    "read_root_artifact_bytes",
    "source_work",
    "verify_additive_input",
    "write_additive_input",
]

# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""All-character CRT/Bluestein stage for Platt's large-q computation.

The transform consumes one interval value for every canonical unit-group
coordinate and returns every character sum in the matching mixed-radix order.
It implements the quasi-linear content of Platt's Lemma ``dc_dft``; it does not
construct the Hurwitz values, select primitive characters, isolate zeros, or
perform the Turing completeness argument.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_campaign import (
    primitive_character_count,
    primitive_character_descriptor,
)
from tg_verifier.dirichlet_fused_stage import canonical_group_model
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_Q_START,
    SOURCE_Q_STOP,
    maximum_t_index,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
SOURCE_URL = "https://arxiv.org/abs/1305.3087v1"
ALGORITHM_ID = "platt-dirichlet-allchars-bluestein-v1"
CHECKER_ID = "mpfr-directed-independent-bluestein-v1"
RESIDUE_ADAPTER_ID = "canonical-crt-residue-to-mixed-radix-v1"
PRIMITIVE_FILTER_ID = "campaign-conrey-to-positive-frequency-v1"
FORMAT_VERSION = 1
PRIMITIVE_MODULUS_ROSTER_VERSION = 2
PRIMITIVE_MODULUS_ROSTER_ID = (
    "primitive-dirichlet-moduli-q-mod-4-ne-2-v2"
)
MAXIMUM_MODULUS = 400_000
MAX_COMPONENTS = 8

INPUT_MAGIC = b"TGDAFFI1"
OUTPUT_MAGIC = b"TGDAFFO1"
INPUT_HEADER = struct.Struct("<8sIIIIQqQQQQ")
OUTPUT_HEADER = struct.Struct("<8sIIIIQQQQ")
COMPLEX_INTERVAL = struct.Struct("<dddd")


class DirichletAllCharsStageError(RuntimeError):
    """An all-character transform input or artifact failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletAllCharsStageError(message)


def canonical_component_orders(q: int) -> tuple[int, ...]:
    """Reconstruct Platt's canonical cyclic unit-group factor orders."""

    if not 3 <= q <= MAXIMUM_MODULUS:
        _fail("q is outside 3..400000")
    remaining = q
    prime = 2
    answer: list[int] = []
    while prime * prime <= remaining:
        if remaining % prime:
            prime += 1
            continue
        exponent = 0
        power = 1
        while remaining % prime == 0:
            remaining //= prime
            power *= prime
            exponent += 1
        if prime == 2:
            if exponent == 2:
                answer.append(2)
            elif exponent > 2:
                answer.extend((2, 1 << (exponent - 2)))
        else:
            answer.append(power - power // prime)
        prime += 1
    if remaining > 1:
        answer.append(remaining - 1)
    if len(answer) > MAX_COMPONENTS:
        _fail("canonical unit group exceeds the format component limit")
    return tuple(answer)


def group_order(q: int) -> int:
    return math.prod(canonical_component_orders(q))


def has_primitive_character_modulus(q: int) -> bool:
    """Exact nonempty-primitive-roster criterion in the source range.

    For ``q > 2``, primitive Dirichlet characters modulo ``q`` exist exactly
    when ``q`` is not congruent to ``2`` modulo ``4``.  The large-q source
    range starts at 10,001, so no exceptional small modulus enters here.
    """

    if not 3 <= q <= MAXIMUM_MODULUS:
        _fail("q is outside 3..400000")
    return q % 4 != 2


def canonical_residue_order(q: int) -> tuple[int, ...]:
    """Map every mixed-radix group coordinate to its actual residue mod q.

    This is the explicit adapter between the lattice/recovery stages, which
    naturally label values by ``a``, and the transform's group-coordinate
    order.  Prime-power generators and CRT inverses are reconstructed from q.
    """

    model = canonical_group_model(q)
    orders = tuple(
        component.order
        for factor in model
        for component in factor.components
    )
    if orders != canonical_component_orders(q):
        _fail("CRT model and transform component orders differ")
    residues: list[int] = []
    for ordinal in range(math.prod(orders)):
        coordinates: list[int] = []
        remainder = ordinal
        for order in orders:
            remainder, coordinate = divmod(remainder, order)
            coordinates.append(coordinate)
        if remainder:
            _fail("mixed-radix residue coordinate overflow")
        coordinate_offset = 0
        residue = 0
        for factor in model:
            local = 1
            for component in factor.components:
                local = (
                    local
                    * pow(
                        component.generator,
                        coordinates[coordinate_offset],
                        factor.modulus,
                    )
                ) % factor.modulus
                coordinate_offset += 1
            cofactor = q // factor.modulus
            residue = (
                residue
                + local * cofactor * pow(cofactor, -1, factor.modulus)
            ) % q
        if coordinate_offset != len(coordinates):
            _fail("CRT coordinate count mismatch")
        residues.append(residue)
    if sorted(residues) != [a for a in range(1, q) if math.gcd(a, q) == 1]:
        _fail("canonical CRT enumeration is not exactly U(Z/qZ)")
    return tuple(residues)


def primitive_frequency_records(q: int) -> tuple[dict[str, int], ...]:
    """Map the campaign's primitive/Conrey descriptors to transform outputs.

    Frequency coordinates are the local exponents already committed by
    :func:`primitive_character_descriptor`.  The first cyclic component varies
    fastest in the transform.  Thus output ``k`` represents the positive-
    exponent character mapping generator ``j`` to ``exp(+2*pi*i*k_j/n_j)``.
    """

    orders = canonical_component_orders(q)
    records: list[dict[str, int]] = []
    for ordinal in range(primitive_character_count(q)):
        descriptor = primitive_character_descriptor(q, ordinal)
        frequencies = tuple(
            frequency
            for local in descriptor["local_exponents"]
            for frequency in local["exponents"]
        )
        if len(frequencies) != len(orders):
            _fail("primitive descriptor component count differs from transform")
        frequency_id = 0
        stride = 1
        for frequency, order in zip(frequencies, orders):
            if not 0 <= frequency < order:
                _fail("primitive descriptor frequency is outside its component")
            frequency_id += frequency * stride
            stride *= order
        records.append(
            {
                "primitive_ordinal": ordinal,
                "frequency_id": frequency_id,
                "conrey_number": int(descriptor["conrey_number"]),
                "parity": int(descriptor["parity"]),
            }
        )
    if len({record["frequency_id"] for record in records}) != len(records):
        _fail("primitive filter produced duplicate transform frequencies")
    return tuple(records)


def write_residue_batches_input(
    path: Path,
    *,
    q: int,
    residue_batches: Sequence[Mapping[int, Sequence[float]]],
    first_t_numerator: int,
    t_denominator: int,
    t_step_numerator: int,
) -> dict[str, Any]:
    """Write production transform input from residue-labelled enclosures.

    Every batch must contain exactly one enclosure for each unit residue.  The
    enclosures are reordered with :func:`canonical_residue_order`; missing,
    extra, non-unit, or malformed rows fail closed.
    """

    if not residue_batches:
        _fail("at least one residue batch is required")
    if first_t_numerator < 0 or t_denominator <= 0 or t_step_numerator <= 0:
        _fail("invalid ordinate progression")
    residues = canonical_residue_order(q)
    residue_set = set(residues)
    orders = canonical_component_orders(q)
    value_count = len(residue_batches) * len(residues)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        output.write(
            INPUT_HEADER.pack(
                INPUT_MAGIC,
                FORMAT_VERSION,
                q,
                len(orders),
                len(residue_batches),
                len(residues),
                first_t_numerator,
                t_denominator,
                t_step_numerator,
                value_count,
                0,
            )
        )
        for batch in residue_batches:
            if set(batch) != residue_set:
                _fail("residue batch is not exactly the unit group")
            for residue in residues:
                endpoints = tuple(float(value) for value in batch[residue])
                if len(endpoints) != 4:
                    _fail("complex interval must have four endpoints")
                re_lo, re_hi, im_lo, im_hi = endpoints
                if not (
                    all(math.isfinite(x) for x in endpoints)
                    and re_lo <= re_hi
                    and im_lo <= im_hi
                ):
                    _fail("malformed residue interval")
                output.write(COMPLEX_INTERVAL.pack(*endpoints))
    return {
        "kind": "sparkinterval.tg.dirichlet_allchars.residue_adapter.v1",
        "adapter": RESIDUE_ADAPTER_ID,
        "primitive_filter": PRIMITIVE_FILTER_ID,
        "path": str(path),
        "q": q,
        "batch_count": len(residue_batches),
        "group_order": len(residues),
        "value_count": value_count,
        "component_orders": list(orders),
        "radix2_butterflies": modulus_butterflies(
            q, batch_count=len(residue_batches)
        ),
    }


def _next_power_of_two(value: int) -> int:
    if value <= 0:
        _fail("positive convolution length required")
    return 1 << (value - 1).bit_length()


def modulus_butterflies(q: int, *, batch_count: int = 1) -> int:
    """Count radix-2 butterflies for one modulus/ordinate transform.

    Each cyclic dimension pays one FFT for its reusable Bluestein kernel and
    a forward/inverse pair for every line in that dimension.
    """

    if batch_count <= 0:
        _fail("batch_count must be positive")
    orders = canonical_component_orders(q)
    total = math.prod(orders)
    answer = 0
    for order in orders:
        convolution = _next_power_of_two(2 * order - 1)
        lines = batch_count * total // order
        answer += (
            (1 + 2 * lines)
            * (convolution // 2)
            * (convolution.bit_length() - 1)
        )
    return answer


def source_work(*, batch_size: int = 64) -> dict[str, int]:
    """Recompute source-shaped large-q transform work from exact formulas."""

    transforms = 0
    group_values = 0
    butterflies_unbatched = 0
    butterflies_batched = 0
    batch_invocations = 0
    active_moduli = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        if not has_primitive_character_modulus(q):
            continue
        active_moduli += 1
        rows = maximum_t_index(q) + 1
        order = group_order(q)
        transforms += rows
        group_values += rows * order
        butterflies_unbatched += rows * modulus_butterflies(q)
        full_batches, remainder = divmod(rows, batch_size)
        batch_invocations += full_batches + int(remainder != 0)
        butterflies_batched += full_batches * modulus_butterflies(
            q, batch_count=batch_size
        )
        if remainder:
            butterflies_batched += modulus_butterflies(q, batch_count=remainder)
    return {
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
        "active_moduli": active_moduli,
        "excluded_empty_primitive_roster_moduli": (
            SOURCE_Q_STOP - SOURCE_Q_START + 1 - active_moduli
        ),
        "modulus_ordinate_transforms": transforms,
        "input_group_values": group_values,
        "unbatched_radix2_butterflies": butterflies_unbatched,
        "production_batch_size": batch_size,
        "batch_invocations": batch_invocations,
        "batched_radix2_butterflies": butterflies_batched,
    }


def preparation_inventory() -> dict[str, Any]:
    """Exact inventory of persistent-modulus MPFR twiddle preparation.

    One complex twiddle enclosure means one directed cosine rectangle and one
    directed sine rectangle.  The present runner prepares each q independently.
    The cacheable count assumes chirps are cached by component order and FFT
    roots by radix-2 convolution length across a larger q-shard supervisor.
    """

    plans: set[tuple[int, ...]] = set()
    component_orders: set[int] = set()
    convolution_lengths: set[int] = set()
    dimensions = 0
    current_enclosures = 0
    active_moduli = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        if not has_primitive_character_modulus(q):
            continue
        active_moduli += 1
        orders = canonical_component_orders(q)
        plans.add(orders)
        for order in orders:
            convolution = _next_power_of_two(2 * order - 1)
            dimensions += 1
            component_orders.add(order)
            convolution_lengths.add(convolution)
            current_enclosures += 2 * order + 2 * (convolution - 1)
    cacheable_enclosures = (
        2 * sum(component_orders)
        + 2 * sum(length - 1 for length in convolution_lengths)
    )
    return {
        "q_start": SOURCE_Q_START,
        "q_stop": SOURCE_Q_STOP,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "primitive_modulus_roster": PRIMITIVE_MODULUS_ROSTER_ID,
        "active_moduli": active_moduli,
        "distinct_q_component_plans": len(plans),
        "component_dimensions_across_q": dimensions,
        "distinct_component_orders": len(component_orders),
        "sum_distinct_component_orders": sum(component_orders),
        "distinct_radix2_convolution_lengths": len(convolution_lengths),
        "radix2_convolution_lengths": sorted(convolution_lengths),
        "current_per_q_complex_twiddle_enclosures": current_enclosures,
        "cross_q_cacheable_complex_twiddle_enclosures": cacheable_enclosures,
    }


MULTIQ_TOTAL_CACHE_BYTES = 512 * 1024 * 1024
ROOT_POOL_CONVOLUTION_LENGTHS = tuple(1 << exponent for exponent in range(2, 21))
ROOT_POOL_CATALOG_ENTRIES = len(ROOT_POOL_CONVOLUTION_LENGTHS)
ROOT_POOL_RESERVED_BYTES = (
    2
    * sum(length - 1 for length in ROOT_POOL_CONVOLUTION_LENGTHS)
    * COMPLEX_INTERVAL.size
)
ORDER_CACHE_CAPACITY_BYTES = (
    MULTIQ_TOTAL_CACHE_BYTES - ROOT_POOL_RESERVED_BYTES
)


def bounded_twiddle_cache_inventory(capacity_bytes: int) -> dict[str, int]:
    """Replay the implemented split root/order cache on the source roster.

    The total production cap is fixed at 512 MiB.  The complete immutable
    19-length root pool is reserved first, even though roots are instantiated
    lazily.  The remaining bytes form the order-specific chirp/kernel LRU.
    Entries referenced by the active mixed-radix q plan cannot be evicted.
    This is exact preparation accounting, not an H100 timing estimate.
    """

    if (
        isinstance(capacity_bytes, bool)
        or not isinstance(capacity_bytes, int)
        or capacity_bytes != MULTIQ_TOTAL_CACHE_BYTES
    ):
        _fail("split twiddle cache requires the exact 512 MiB total capacity")
    retained: dict[int, int] = {}
    lru: list[int] = []
    retained_bytes = 0
    peak_bytes = 0
    peak_total_bytes = 0
    root_lengths: set[int] = set()
    root_retained_bytes = 0
    root_accesses = 0
    root_hits = 0
    root_misses = 0
    root_prepared_enclosures = 0
    order_accesses = 0
    order_hits = 0
    order_misses = 0
    order_evictions = 0
    order_uncached_misses = 0
    order_prepared_enclosures = 0
    active_moduli = 0
    for q in range(SOURCE_Q_START, SOURCE_Q_STOP + 1):
        if not has_primitive_character_modulus(q):
            continue
        active_moduli += 1
        active: set[int] = set()
        for length in canonical_component_orders(q):
            order_accesses += 1
            convolution = _next_power_of_two(2 * length - 1)
            if length in retained:
                order_hits += 1
                lru.remove(length)
                lru.insert(0, length)
            else:
                order_misses += 1
                order_prepared_enclosures += 2 * length
                root_accesses += 1
                if convolution in root_lengths:
                    root_hits += 1
                else:
                    if convolution not in ROOT_POOL_CONVOLUTION_LENGTHS:
                        _fail("source convolution is outside root catalog")
                    root_misses += 1
                    root_lengths.add(convolution)
                    root_retained_bytes += (
                        2 * (convolution - 1) * COMPLEX_INTERVAL.size
                    )
                    root_prepared_enclosures += 2 * (convolution - 1)
                peak_total_bytes = max(
                    peak_total_bytes,
                    retained_bytes + root_retained_bytes,
                )
                entry_bytes = _order_cache_entry_bytes(length)
                retain = entry_bytes <= ORDER_CACHE_CAPACITY_BYTES
                while (
                    retain
                    and retained_bytes
                    > ORDER_CACHE_CAPACITY_BYTES - entry_bytes
                ):
                    candidate = next(
                        (
                            cached
                            for cached in reversed(lru)
                            if cached not in active
                        ),
                        None,
                    )
                    if candidate is None:
                        retain = False
                        break
                    retained_bytes -= retained.pop(candidate)
                    lru.remove(candidate)
                    order_evictions += 1
                if retain:
                    retained[length] = entry_bytes
                    retained_bytes += entry_bytes
                    lru.insert(0, length)
                    peak_bytes = max(peak_bytes, retained_bytes)
                    peak_total_bytes = max(
                        peak_total_bytes,
                        retained_bytes + root_retained_bytes,
                    )
                else:
                    order_uncached_misses += 1
            active.add(length)
    return {
        "capacity_bytes": capacity_bytes,
        "primitive_modulus_roster_version": (
            PRIMITIVE_MODULUS_ROSTER_VERSION
        ),
        "active_moduli": active_moduli,
        "root_pool_catalog_entries": ROOT_POOL_CATALOG_ENTRIES,
        "root_pool_reserved_bytes": ROOT_POOL_RESERVED_BYTES,
        "root_pool_accesses": root_accesses,
        "root_pool_hits": root_hits,
        "root_pool_misses": root_misses,
        "root_pool_retained_entries": len(root_lengths),
        "root_pool_retained_bytes": root_retained_bytes,
        "root_pool_prepared_enclosures": root_prepared_enclosures,
        "order_cache_capacity_bytes": ORDER_CACHE_CAPACITY_BYTES,
        "order_cache_accesses": order_accesses,
        "order_cache_hits": order_hits,
        "order_cache_misses": order_misses,
        "order_cache_evictions": order_evictions,
        "order_cache_uncached_misses": order_uncached_misses,
        "order_cache_retained_entries": len(retained),
        "order_cache_retained_bytes": retained_bytes,
        "order_cache_peak_retained_bytes": peak_bytes,
        "order_cache_prepared_enclosures": order_prepared_enclosures,
        "total_prepared_enclosures": (
            order_prepared_enclosures + root_prepared_enclosures
        ),
        "cache_peak_total_retained_bytes": peak_total_bytes,
    }


def _synthetic_value(index: int) -> tuple[float, float, float, float]:
    real = ((index * 37 + 11) % 211 - 105) / 128.0
    imag = ((index * 53 + 7) % 223 - 111) / 128.0
    width = math.ldexp(1.0, -42)
    return real - width, real + width, imag - width, imag + width


def write_synthetic_input(
    path: Path, *, q: int, t_index: int = 0, batch_count: int = 1
) -> dict[str, Any]:
    if t_index < 0:
        _fail("t_index must be nonnegative")
    if batch_count <= 0:
        _fail("batch_count must be positive")
    orders = canonical_component_orders(q)
    total = math.prod(orders)
    value_count = batch_count * total
    header = INPUT_HEADER.pack(
        INPUT_MAGIC,
        FORMAT_VERSION,
        q,
        len(orders),
        batch_count,
        total,
        5 * t_index,
        64,
        5,
        value_count,
        0,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        output.write(header)
        for index in range(value_count):
            output.write(COMPLEX_INTERVAL.pack(*_synthetic_value(index)))
    return {
        "kind": "sparkinterval.tg.dirichlet_allchars.synthetic_input.v1",
        "path": str(path),
        "q": q,
        "t_index": t_index,
        "batch_count": batch_count,
        "component_orders": list(orders),
        "group_order": total,
        "radix2_butterflies": modulus_butterflies(q, batch_count=batch_count),
        "bytes": path.stat().st_size,
    }


def read_input_header(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) < INPUT_HEADER.size:
        _fail("truncated input header")
    (
        magic,
        version,
        q,
        component_count,
        batch_count,
        order,
        t_numerator,
        t_denominator,
        t_step_numerator,
        value_count,
        reserved0,
    ) = INPUT_HEADER.unpack_from(raw)
    orders = canonical_component_orders(q)
    expected_order = math.prod(orders)
    if (
        magic != INPUT_MAGIC
        or version != FORMAT_VERSION
        or reserved0
        or batch_count <= 0
        or t_numerator < 0
        or t_denominator == 0
        or component_count != len(orders)
        or order != expected_order
        or t_step_numerator <= 0
        or value_count != batch_count * expected_order
        or len(raw) != INPUT_HEADER.size + value_count * COMPLEX_INTERVAL.size
    ):
        _fail("input identity or size mismatch")
    return {
        "q": q,
        "component_orders": list(orders),
        "batch_count": batch_count,
        "group_order": order,
        "value_count": value_count,
        "t_numerator": t_numerator,
        "t_denominator": t_denominator,
        "t_step_numerator": t_step_numerator,
        "radix2_butterflies": modulus_butterflies(q, batch_count=batch_count),
    }


def read_output_header(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) < OUTPUT_HEADER.size:
        _fail("truncated output header")
    (
        magic,
        version,
        q,
        component_count,
        batch_count,
        order,
        value_count,
        butterflies,
        elapsed_ns,
    ) = OUTPUT_HEADER.unpack_from(raw)
    orders = canonical_component_orders(q)
    if (
        magic != OUTPUT_MAGIC
        or version != FORMAT_VERSION
        or component_count != len(orders)
        or batch_count <= 0
        or order != math.prod(orders)
        or value_count != batch_count * order
        or butterflies != modulus_butterflies(q, batch_count=batch_count)
        or len(raw) != OUTPUT_HEADER.size + value_count * COMPLEX_INTERVAL.size
    ):
        _fail("output identity or size mismatch")
    offset = OUTPUT_HEADER.size
    for index in range(value_count):
        re_lo, re_hi, im_lo, im_hi = COMPLEX_INTERVAL.unpack_from(
            raw, offset + index * COMPLEX_INTERVAL.size
        )
        if not (
            all(math.isfinite(x) for x in (re_lo, re_hi, im_lo, im_hi))
            and re_lo <= re_hi
            and im_lo <= im_hi
        ):
            _fail("output contains malformed interval")
    return {
        "q": q,
        "component_orders": list(orders),
        "batch_count": batch_count,
        "group_order": order,
        "value_count": value_count,
        "radix2_butterflies": butterflies,
        "elapsed_nanoseconds": elapsed_ns,
    }


MULTIQ_FRAMED_SUMMARY_KIND = (
    "sparkinterval.tg.dirichlet_allchars.multiq_framed_service.v2"
)
MULTIQ_CACHE_ALGORITHM = "bounded-device-split-root-order-lru-v2"
MULTIQ_ROOT_POOL_ALGORITHM = "immutable-directed-radix2-root-pool-v1"
MULTIQ_CACHE_KEY_DOMAIN = b"TGDAFF_SPLIT_CACHE_KEY_V2"
MULTIQ_ROOT_CATALOG_DOMAIN = b"TGDAFF_ROOT_POOL_CATALOG_V1"


def _strict_nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{label} is not a nonnegative integer")
    return value


def _order_cache_entry_bytes(length: int) -> int:
    convolution = _next_power_of_two(2 * length - 1)
    return (length + convolution) * COMPLEX_INTERVAL.size


def _root_pool_catalog_sha256() -> str:
    digest = hashlib.sha256(MULTIQ_ROOT_CATALOG_DOMAIN)
    for convolution in ROOT_POOL_CONVOLUTION_LENGTHS:
        digest.update(struct.pack("<I", convolution))
    return digest.hexdigest()


def validate_multiq_framed_summary(
    summary: Mapping[str, Any],
    *,
    input_stream: bytes,
    output_stream: bytes,
) -> dict[str, Any]:
    """Independently replay one bounded cross-q cache/service summary.

    This parser does not trust the C++ cache counters.  It re-parses every
    input/output frame, reconstructs the primitive-free-independent CRT plan
    from each q, simulates the exact byte-capped LRU policy, and recomputes the
    stream and cache-key digests.  Arithmetic containment remains the job of
    the independent MPFR executable.
    """

    required = {
        "kind",
        "algorithm",
        "cache_algorithm",
        "root_pool_algorithm",
        "maximum_batch_count",
        "cache_capacity_bytes",
        "root_pool_catalog_entries",
        "root_pool_reserved_bytes",
        "order_cache_capacity_bytes",
        "first_q",
        "last_q",
        "modulus_count",
        "frame_count",
        "slice_count",
        "value_count",
        "radix2_butterflies",
        "preparation_nanoseconds",
        "elapsed_nanoseconds",
        "root_pool_accesses",
        "root_pool_hits",
        "root_pool_misses",
        "root_pool_retained_entries",
        "root_pool_retained_bytes",
        "root_pool_prepared_enclosures",
        "order_cache_accesses",
        "order_cache_hits",
        "order_cache_misses",
        "order_cache_evictions",
        "order_cache_uncached_misses",
        "order_cache_retained_entries",
        "order_cache_retained_bytes",
        "order_cache_peak_retained_bytes",
        "order_cache_prepared_enclosures",
        "total_prepared_enclosures",
        "cache_peak_total_retained_bytes",
        "order_cache_key_chain_sha256",
        "root_pool_catalog_sha256",
        "retained_input_frames",
        "retained_output_frames",
        "input_stream_sha256",
        "output_stream_sha256",
    }
    if (
        not isinstance(summary, Mapping)
        or set(summary) != required
        or summary.get("kind") != MULTIQ_FRAMED_SUMMARY_KIND
        or summary.get("algorithm") != ALGORITHM_ID
        or summary.get("cache_algorithm") != MULTIQ_CACHE_ALGORITHM
        or summary.get("root_pool_algorithm") != MULTIQ_ROOT_POOL_ALGORITHM
    ):
        _fail("multi-q summary schema or algorithm differs")
    numeric = {
        key: _strict_nonnegative_integer(summary.get(key), key)
        for key in required
        if key
        not in {
            "kind",
            "algorithm",
            "cache_algorithm",
            "root_pool_algorithm",
            "order_cache_key_chain_sha256",
            "root_pool_catalog_sha256",
            "input_stream_sha256",
            "output_stream_sha256",
        }
    }
    maximum_batch = numeric["maximum_batch_count"]
    capacity = numeric["cache_capacity_bytes"]
    if (
        maximum_batch == 0
        or capacity != MULTIQ_TOTAL_CACHE_BYTES
        or numeric["root_pool_catalog_entries"]
        != ROOT_POOL_CATALOG_ENTRIES
        or numeric["root_pool_reserved_bytes"] != ROOT_POOL_RESERVED_BYTES
        or numeric["order_cache_capacity_bytes"]
        != ORDER_CACHE_CAPACITY_BYTES
        or numeric["root_pool_reserved_bytes"]
        + numeric["order_cache_capacity_bytes"]
        != capacity
    ):
        _fail("multi-q split-cache budget or batch count differs")
    for key in (
        "order_cache_key_chain_sha256",
        "root_pool_catalog_sha256",
        "input_stream_sha256",
        "output_stream_sha256",
    ):
        value = summary.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            _fail(f"multi-q summary {key} is not lowercase SHA-256")
    if summary["root_pool_catalog_sha256"] != _root_pool_catalog_sha256():
        _fail("multi-q root-pool catalog commitment differs")
    if summary["input_stream_sha256"] != hashlib.sha256(input_stream).hexdigest():
        _fail("multi-q input stream digest differs")
    if summary["output_stream_sha256"] != hashlib.sha256(output_stream).hexdigest():
        _fail("multi-q output stream digest differs")

    cache_key_hash = hashlib.sha256(MULTIQ_CACHE_KEY_DOMAIN)
    retained: dict[int, int] = {}
    lru: list[int] = []
    active: set[int] = set()
    retained_bytes = 0
    peak_bytes = 0
    peak_total_bytes = 0
    root_lengths: set[int] = set()
    root_retained_bytes = 0
    root_accesses = 0
    root_hits = 0
    root_misses = 0
    root_prepared_enclosures = 0
    order_accesses = 0
    order_hits = 0
    order_misses = 0
    order_evictions = 0
    order_uncached = 0
    order_prepared_enclosures = 0

    input_offset = 0
    output_offset = 0
    previous_q = 0
    first_q = 0
    moduli = 0
    frames = 0
    slices = 0
    values = 0
    butterflies = 0
    elapsed = 0
    expected_first = 0
    denominator = 0
    step = 0
    while input_offset < len(input_stream):
        if len(input_stream) - input_offset < INPUT_HEADER.size:
            _fail("multi-q input stream has a partial header")
        (
            magic,
            version,
            q,
            component_count,
            batch_count,
            order,
            first_t,
            t_denominator,
            t_step,
            value_count,
            reserved,
        ) = INPUT_HEADER.unpack_from(input_stream, input_offset)
        orders = canonical_component_orders(q)
        if (
            magic != INPUT_MAGIC
            or version != FORMAT_VERSION
            or reserved != 0
            or component_count != len(orders)
            or batch_count == 0
            or batch_count > maximum_batch
            or order != math.prod(orders)
            or value_count != batch_count * order
            or first_t < 0
            or t_denominator == 0
            or t_step == 0
        ):
            _fail("multi-q input frame identity differs")
        input_size = INPUT_HEADER.size + value_count * COMPLEX_INTERVAL.size
        if input_offset + input_size > len(input_stream):
            _fail("multi-q input stream has truncated values")
        for index in range(value_count):
            endpoints = COMPLEX_INTERVAL.unpack_from(
                input_stream,
                input_offset + INPUT_HEADER.size
                + index * COMPLEX_INTERVAL.size,
            )
            if not (
                all(math.isfinite(value) for value in endpoints)
                and endpoints[0] <= endpoints[1]
                and endpoints[2] <= endpoints[3]
            ):
                _fail("multi-q input stream has a malformed interval")

        if q != previous_q:
            if previous_q != 0 and q <= previous_q:
                _fail("multi-q input roster is not strictly increasing")
            active.clear()
            previous_q = q
            if first_q == 0:
                first_q = q
            moduli += 1
            denominator = t_denominator
            step = t_step
            for length in orders:
                convolution = _next_power_of_two(2 * length - 1)
                cache_key_hash.update(struct.pack("<II", length, convolution))
                order_accesses += 1
                if length in retained:
                    order_hits += 1
                    lru.remove(length)
                    lru.insert(0, length)
                else:
                    order_misses += 1
                    order_prepared_enclosures += 2 * length
                    root_accesses += 1
                    if convolution in root_lengths:
                        root_hits += 1
                    else:
                        if convolution not in ROOT_POOL_CONVOLUTION_LENGTHS:
                            _fail(
                                "multi-q convolution is outside root catalog"
                            )
                        root_misses += 1
                        root_lengths.add(convolution)
                        root_retained_bytes += (
                            2
                            * (convolution - 1)
                            * COMPLEX_INTERVAL.size
                        )
                        root_prepared_enclosures += 2 * (convolution - 1)
                    peak_total_bytes = max(
                        peak_total_bytes,
                        retained_bytes + root_retained_bytes,
                    )
                    entry_bytes = _order_cache_entry_bytes(length)
                    retain = entry_bytes <= ORDER_CACHE_CAPACITY_BYTES
                    while (
                        retain
                        and retained_bytes
                        > ORDER_CACHE_CAPACITY_BYTES - entry_bytes
                    ):
                        candidate = next(
                            (
                                cached
                                for cached in reversed(lru)
                                if cached not in active
                            ),
                            None,
                        )
                        if candidate is None:
                            retain = False
                            break
                        retained_bytes -= retained.pop(candidate)
                        lru.remove(candidate)
                        order_evictions += 1
                    if retain:
                        retained[length] = entry_bytes
                        retained_bytes += entry_bytes
                        lru.insert(0, length)
                        peak_bytes = max(peak_bytes, retained_bytes)
                        peak_total_bytes = max(
                            peak_total_bytes,
                            retained_bytes + root_retained_bytes,
                        )
                    else:
                        order_uncached += 1
                active.add(length)
        elif (
            t_denominator != denominator
            or t_step != step
            or first_t != expected_first
        ):
            _fail("multi-q ordinate progression is discontinuous")
        expected_first = first_t + batch_count * t_step

        if len(output_stream) - output_offset < OUTPUT_HEADER.size:
            _fail("multi-q output stream has a partial header")
        output_header = OUTPUT_HEADER.unpack_from(output_stream, output_offset)
        expected_butterflies = modulus_butterflies(
            q, batch_count=batch_count
        )
        if (
            output_header[:7]
            != (
                OUTPUT_MAGIC,
                FORMAT_VERSION,
                q,
                component_count,
                batch_count,
                order,
                value_count,
            )
            or output_header[7] != expected_butterflies
        ):
            _fail("multi-q output frame identity differs")
        output_size = OUTPUT_HEADER.size + value_count * COMPLEX_INTERVAL.size
        if output_offset + output_size > len(output_stream):
            _fail("multi-q output stream has truncated values")
        for index in range(value_count):
            endpoints = COMPLEX_INTERVAL.unpack_from(
                output_stream,
                output_offset + OUTPUT_HEADER.size
                + index * COMPLEX_INTERVAL.size,
            )
            if not (
                all(math.isfinite(value) for value in endpoints)
                and endpoints[0] <= endpoints[1]
                and endpoints[2] <= endpoints[3]
            ):
                _fail("multi-q output stream has a malformed interval")
        frames += 1
        slices += batch_count
        values += value_count
        butterflies += expected_butterflies
        elapsed += output_header[8]
        input_offset += input_size
        output_offset += output_size

    if (
        frames == 0
        or input_offset != len(input_stream)
        or output_offset != len(output_stream)
    ):
        _fail("multi-q streams are empty or have trailing bytes")
    expected_numeric = {
        "first_q": first_q,
        "last_q": previous_q,
        "modulus_count": moduli,
        "frame_count": frames,
        "slice_count": slices,
        "value_count": values,
        "radix2_butterflies": butterflies,
        "elapsed_nanoseconds": elapsed,
        "root_pool_catalog_entries": ROOT_POOL_CATALOG_ENTRIES,
        "root_pool_reserved_bytes": ROOT_POOL_RESERVED_BYTES,
        "order_cache_capacity_bytes": ORDER_CACHE_CAPACITY_BYTES,
        "root_pool_accesses": root_accesses,
        "root_pool_hits": root_hits,
        "root_pool_misses": root_misses,
        "root_pool_retained_entries": len(root_lengths),
        "root_pool_retained_bytes": root_retained_bytes,
        "root_pool_prepared_enclosures": root_prepared_enclosures,
        "order_cache_accesses": order_accesses,
        "order_cache_hits": order_hits,
        "order_cache_misses": order_misses,
        "order_cache_evictions": order_evictions,
        "order_cache_uncached_misses": order_uncached,
        "order_cache_retained_entries": len(retained),
        "order_cache_retained_bytes": retained_bytes,
        "order_cache_peak_retained_bytes": peak_bytes,
        "order_cache_prepared_enclosures": order_prepared_enclosures,
        "total_prepared_enclosures": (
            order_prepared_enclosures + root_prepared_enclosures
        ),
        "cache_peak_total_retained_bytes": peak_total_bytes,
        "retained_input_frames": 0,
        "retained_output_frames": 0,
    }
    for key, expected in expected_numeric.items():
        if numeric[key] != expected:
            _fail(f"multi-q summary {key} differs from independent replay")
    if (
        numeric["preparation_nanoseconds"] < 0
        or summary["order_cache_key_chain_sha256"]
        != cache_key_hash.hexdigest()
    ):
        _fail("multi-q preparation or cache-key commitment differs")
    return dict(summary)


def capability() -> dict[str, Any]:
    return {
        "kind": "sparkinterval.tg.dirichlet_allchars.capability.v1",
        "atom_id": ATOM_ID,
        "author": AUTHOR,
        "source": SOURCE_URL,
        "accepted_manuscript": (
            "https://research-information.bris.ac.uk/ws/portalfiles/portal/"
            "67056136/platt_grh3.0.pdf"
        ),
        "algorithm": ALGORITHM_ID,
        "checker": CHECKER_ID,
        "maximum_modulus": MAXIMUM_MODULUS,
        "classification": "source_scalable_transform_component_not_atom_closure",
        "production_ready": False,
        "transform_component_production_ready": True,
        "persistent_framed_transform_service_ready": True,
        "bounded_cross_q_twiddle_cache_service_ready": True,
        "primitive_only_source_roster_ready": True,
        "streaming_supervisor_performance_ready": False,
        "full_source": False,
        "recommended_batch_size": 64,
        "frequency_convention": (
            "output k is sum_e X[e]*exp(+2*pi*i*sum_j(e_j*k_j/order_j)); "
            "equivalently generator j maps to exp(+2*pi*i*k_j/order_j)"
        ),
        "implemented": [
            "canonical CRT cyclic component reconstruction from q",
            "actual-residue to mixed-radix CRT adapter",
            "primitive-frequency and Conrey descriptor adapter",
            "multidimensional all-character transform",
            "arbitrary-length Bluestein convolution",
            "radix-2 CUDA interval FFT with directed arithmetic",
            "MPFR-generated transcendental twiddle enclosures",
            "independent MPFR-directed CPU replay",
            "persistent hash-bound binary frame service with one retained q plan",
            "versioned primitive-only source roster excluding q congruent to 2 modulo 4",
            "exact-512-MiB split immutable-root and order-plan device cache with independent summary replay",
        ],
        "not_implemented": [
            "source-shard supervisor binding composition, controls, transform, and zero scan",
            "scalable certified root-number artifact consumption downstream",
            "zero isolation and small-q algorithm",
            "Turing completeness closure",
        ],
        "closes_external_atom": False,
    }


def pretty_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


__all__ = [
    "ALGORITHM_ID",
    "CHECKER_ID",
    "COMPLEX_INTERVAL",
    "DirichletAllCharsStageError",
    "INPUT_HEADER",
    "OUTPUT_HEADER",
    "MULTIQ_CACHE_ALGORITHM",
    "MULTIQ_FRAMED_SUMMARY_KIND",
    "MULTIQ_ROOT_POOL_ALGORITHM",
    "MULTIQ_TOTAL_CACHE_BYTES",
    "ORDER_CACHE_CAPACITY_BYTES",
    "PRIMITIVE_MODULUS_ROSTER_ID",
    "PRIMITIVE_MODULUS_ROSTER_VERSION",
    "ROOT_POOL_CATALOG_ENTRIES",
    "ROOT_POOL_CONVOLUTION_LENGTHS",
    "ROOT_POOL_RESERVED_BYTES",
    "canonical_component_orders",
    "canonical_residue_order",
    "bounded_twiddle_cache_inventory",
    "capability",
    "group_order",
    "has_primitive_character_modulus",
    "modulus_butterflies",
    "primitive_frequency_records",
    "preparation_inventory",
    "read_input_header",
    "read_output_header",
    "validate_multiq_framed_summary",
    "source_work",
    "write_residue_batches_input",
    "write_synthetic_input",
]

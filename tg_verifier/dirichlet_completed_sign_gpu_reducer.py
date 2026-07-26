# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resident GPU completed-L sign reducer and bounded Arb qualification.

The production seam is an in-process CUDA call on the resident
``ComplexInterval*`` output of the scheduled all-character FFT.  It does not
serialize ``TGDAFFO1`` and does not allocate a status word per transformed
value.  Already validated allchars frames pass a null status pointer and one
zero frame-status word.

The CUDA reducer multiplies three certified enclosures:

* the resident FFT enclosure of ``L(1/2+it, chi)``;
* the ``TGDRNRO1`` Hardy/root multiplier for the same canonical primitive
  ordinal and parity; and
* a parity/sample factor enclosing
  ``(q/pi)^(it/2) Gamma((1/2+a+it)/2) exp(pi*t/4)``.

It converts rectangles to containing disks with directed arithmetic, uses the
same directed disk product as the certified Booker kernels, rejects a
completed disk that misses the real axis, and emits only dense associative
phase states plus exact sparse maximal ambiguity ranges.

This module also constructs a *bounded-only* Arb/FLINT differential fixture.
That adapter asks a diagnostic kernel for raw signs solely to measure
false-determinate and extra-ambiguity rates.  Raw signs are explicitly absent
from the production path.

None of this proves the allchars FFT refinement, the factor producer, root
artifact completeness, multiplicity preservation, Turing completeness,
source execution, attestation, GRH, or Platt's theorem.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
from typing import Any, Mapping, NoReturn, Sequence


AUTHOR = "Gershon Bialer"
ALGORITHM_ID = "tg-dirichlet-resident-completed-sign-reducer-v1"
QUALIFICATION_ID = (
    "tg-dirichlet-resident-completed-sign-arb-differential-v1"
)
QUALIFICATION_MAGIC = b"TGDCQAI1"
QUALIFICATION_VERSION = 2
QUALIFICATION_HEADER = struct.Struct("<8s6IQ")
DISK = struct.Struct("<ddd")
COMPLEX_INTERVAL = struct.Struct("<dddd")

SOURCE_STEP_NUMERATOR = 5
SOURCE_DENOMINATOR = 64
MAXIMUM_FRAME_SAMPLES = 64
MAXIMUM_QUALIFICATION_SAMPLES = 4096
MAXIMUM_QUALIFICATION_ITEMS = 4 * 1024 * 1024
SOURCE_TRANSFORM_VALUE_COUNT = 266_697_737_764_848
SOURCE_PRIMITIVE_CHARACTER_COUNT = 29_547_446_729
SOURCE_Q_COUNT = 292_500
MAXIMUM_Q_CHARACTERS = 400_000
MAXIMUM_PACKED_SAMPLES = (1 << 32) - 1
DENSE_PAGE_CHARACTERS = 4096
DENSE_PHASE_STATE_BYTES = 88
DENSE_PAGE_TOTAL_BYTES = 64


class DirichletCompletedSignReducerError(RuntimeError):
    """A reducer model, fixture, invocation, or result failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletCompletedSignReducerError(message)


def _uint(name: str, value: object, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        _fail(f"{name} is outside its fixed unsigned bound")
    return value


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def source_memory_model(
    *,
    frame_characters: int = MAXIMUM_Q_CHARACTERS,
    frame_samples: int = MAXIMUM_FRAME_SAMPLES,
    ambiguity_ranges: int = 0,
) -> dict[str, Any]:
    """Return exact byte formulas for one resident reducer frame.

    ``ambiguity_ranges`` is an explicit sensitivity, not an expected density.
    The FFT value buffer is already resident and therefore reported
    separately from incremental reducer storage.
    """

    characters = _uint(
        "frame characters", frame_characters, MAXIMUM_Q_CHARACTERS
    )
    samples = _uint(
        "frame samples", frame_samples, MAXIMUM_FRAME_SAMPLES
    )
    ranges = _uint(
        "ambiguity ranges",
        ambiguity_ranges,
        characters * ((samples + 1) // 2),
    )
    if characters == 0 or samples == 0:
        _fail("memory-model frame dimensions must be nonzero")
    resident_fft_bytes = characters * samples * COMPLEX_INTERVAL.size
    root_disk_bytes = characters * DISK.size
    parity_factor_bytes = 2 * samples * DISK.size
    parity_bytes = characters
    frequency_id_bytes = characters * 8
    dense_state_bytes = characters * 88
    range_count_bytes = characters * 8
    range_offset_bytes = (characters + 1) * 8
    sparse_range_bytes = ranges * 16
    sparse_range_primitive_ordinal_bytes = ranges * 8
    incremental = (
        root_disk_bytes
        + parity_factor_bytes
        + parity_bytes
        + frequency_id_bytes
        + dense_state_bytes
        + range_count_bytes
        + range_offset_bytes
        + sparse_range_bytes
        + sparse_range_primitive_ordinal_bytes
        + 16
    )
    raw_source_bytes = (
        SOURCE_TRANSFORM_VALUE_COUNT * COMPLEX_INTERVAL.size
    )
    raw_two_bit_code_bytes = (
        SOURCE_TRANSFORM_VALUE_COUNT + 3
    ) // 4
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "memory_model.v1"
        ),
        "classification": (
            "exact_layout_formula_not_source_measurement_or_admission"
        ),
        "frame_characters": characters,
        "frame_samples": samples,
        "ambiguity_ranges_sensitivity": ranges,
        "already_resident_fft_bytes": resident_fft_bytes,
        "root_disk_bytes": root_disk_bytes,
        "parity_factor_bytes": parity_factor_bytes,
        "parity_bytes": parity_bytes,
        "canonical_frequency_id_bytes": frequency_id_bytes,
        "dense_phase_state_bytes": dense_state_bytes,
        "range_count_bytes": range_count_bytes,
        "range_offset_bytes": range_offset_bytes,
        "sparse_range_bytes": sparse_range_bytes,
        "sparse_range_primitive_ordinal_bytes": (
            sparse_range_primitive_ordinal_bytes
        ),
        "incremental_reducer_bytes": incremental,
        "live_bytes_including_resident_fft": (
            resident_fft_bytes + incremental
        ),
        "cub_scan_temporary_bytes_included": False,
        "q_level_merge_workspace_included": False,
        "scope_note": (
            "exact named reducer buffers only; CUB implementation workspace "
            "and owning q-level accumulator are separate"
        ),
        "per_value_status_bytes": 0,
        "production_source_status_mode": (
            "nullable_per_item_pointer_plus_validated_frame_status"
        ),
        "source_raw_transform_bytes_avoided": raw_source_bytes,
        "source_raw_two_bit_code_bytes_avoided": raw_two_bit_code_bytes,
        "raw_completed_l_stream_materialized": False,
        "source_measurement": False,
        "source_admission": False,
    }


def dense_pack_model(
    *,
    character_count: int,
    sample_count: int,
) -> dict[str, Any]:
    """Return exact device-staging and canonical dense-prefix byte counts.

    The 88-byte phase states are an internal reduction representation.  They
    stay on the GPU.  TGDCSB03 retains four flags and the smallest transition
    width for the complete merged sample span.  A fixed page stride is useful
    only as temporary CUDA storage; ``canonical_dense_bytes`` is the sum of
    the used page prefixes that may cross the device boundary.
    """

    characters = _uint(
        "dense-pack characters", character_count, MAXIMUM_Q_CHARACTERS
    )
    samples = _uint(
        "dense-pack samples", sample_count, MAXIMUM_PACKED_SAMPLES
    )
    if characters == 0 or samples == 0:
        _fail("dense-pack dimensions must be nonzero")
    count_width = max(1, (samples - 1).bit_length())
    record_width = 4 + count_width
    page_count = (
        characters + DENSE_PAGE_CHARACTERS - 1
    ) // DENSE_PAGE_CHARACTERS
    page_stride = (
        DENSE_PAGE_CHARACTERS * record_width + 7
    ) // 8
    full_pages, last_page_characters = divmod(
        characters, DENSE_PAGE_CHARACTERS
    )
    canonical_dense_bytes = full_pages * page_stride
    if last_page_characters:
        canonical_dense_bytes += (
            last_page_characters * record_width + 7
        ) // 8
    internal_phase_state_bytes = characters * DENSE_PHASE_STATE_BYTES
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "dense_pack_model.v1"
        ),
        "classification": (
            "exact_layout_formula_not_source_execution_or_admission"
        ),
        "character_count": characters,
        "sample_count": samples,
        "flag_bits": 4,
        "transition_count_width_bits": count_width,
        "record_width_bits": record_width,
        "page_characters": DENSE_PAGE_CHARACTERS,
        "page_count": page_count,
        "page_stride_bytes": page_stride,
        "device_staging_bytes": page_count * page_stride,
        "canonical_dense_bytes": canonical_dense_bytes,
        "device_page_total_bytes": page_count * DENSE_PAGE_TOTAL_BYTES,
        "internal_phase_state_bytes": internal_phase_state_bytes,
        "phase_states_cross_device_boundary": False,
        "dense_padding_zeroed": True,
        "sparse_range_bytes_included": False,
        "source_execution": False,
        "source_admission": False,
    }


def source_dense_pack_projection() -> dict[str, Any]:
    """Expose the reviewed exact TGDCSB03 source projection.

    The independent formulaic recomputation lives in
    ``dirichlet_compact_state_streaming_v3.source_storage_projection_v3`` and
    takes several seconds because it enumerates every q.  These pinned values
    make routine reducer reporting cheap without pretending a source run has
    occurred.
    """

    internal = (
        SOURCE_PRIMITIVE_CHARACTER_COUNT * DENSE_PHASE_STATE_BYTES
    )
    exact_dense_floor = 62_259_950_420
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "source_dense_pack_projection.v1"
        ),
        "classification": (
            "reviewed_exact_formulaic_projection_not_source_measurement"
        ),
        "primitive_character_count": SOURCE_PRIMITIVE_CHARACTER_COUNT,
        "internal_phase_state_bytes_not_transported": internal,
        "exact_dense_byte_floor_without_q_or_page_padding": (
            exact_dense_floor
        ),
        "exact_canonical_wire_bytes_without_ambiguity_ranges": (
            62_968_524_843
        ),
        "exact_final_page_count": 7_359_448,
        "maximum_width_uniform_upper_bound_bytes": (
            (SOURCE_PRIMITIVE_CHARACTER_COUNT * 21 + 7) // 8
        ),
        "internal_to_dense_floor_ratio": internal / exact_dense_floor,
        "exact_projection_authority": (
            "dirichlet_compact_state_streaming_v3."
            "source_storage_projection_v3"
        ),
        "ambiguity_range_bytes_included": False,
        "source_execution": False,
        "source_admission": False,
    }


def factor_checkpoint_model(
    *,
    t_rows: int,
    checkpoint_span: int = 4096,
    active_moduli: int = SOURCE_Q_COUNT,
) -> dict[str, Any]:
    """Size the proposed Arb-seeded conductor recurrence.

    Gamma/``exp(pi*t/4)`` disks are shared by parity and t row.  For each q,
    Arb supplies a certified conductor-phase seed at every checkpoint and one
    certified step disk.  CUDA uses directed disk multiplication only between
    checkpoints.  Enclosure usefulness still needs a measured source-range
    qualification; this function does not assert that a chosen span is
    adequate.
    """

    rows = _uint("t rows", t_rows, 1_000_000)
    span = _uint("checkpoint span", checkpoint_span, MAXIMUM_QUALIFICATION_ITEMS)
    moduli = _uint("active moduli", active_moduli, SOURCE_Q_COUNT)
    if rows == 0 or span == 0 or moduli == 0:
        _fail("factor checkpoint dimensions must be nonzero")
    checkpoints = (rows + span - 1) // span
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "factor_checkpoint_model.v1"
        ),
        "t_rows": rows,
        "checkpoint_span": span,
        "active_moduli": moduli,
        "gamma_scaled_disk_bytes": 2 * rows * DISK.size,
        "conductor_step_disk_bytes": moduli * DISK.size,
        "conductor_checkpoint_count": moduli * checkpoints,
        "conductor_checkpoint_disk_bytes": (
            moduli * checkpoints * DISK.size
        ),
        "transcendental_evaluation_location": (
            "Arb producer; no device transcendental trusted"
        ),
        "cuda_arithmetic": "directed disk recurrence and multiplication",
        "conductor_step_t_numerator": SOURCE_STEP_NUMERATOR,
        "conductor_step_t_denominator": 2 * SOURCE_DENOMINATOR,
        "conductor_step_applications_per_sample": 1,
        "bounded_q5_initial_and_terminal_4096_step_replay": True,
        "checkpoint_enclosure_usefulness_measured": False,
        "checkpoint_enclosure_usefulness_measured_full_source_q_range": (
            False
        ),
        "source_ready": False,
    }


def capability() -> dict[str, Any]:
    return {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "capability.v1"
        ),
        "algorithm_id": ALGORITHM_ID,
        "in_process_resident_device_pointer_api": True,
        "scheduled_allchars_writeall_bypass_required": True,
        "raw_transform_stream_materialized": False,
        "raw_sign_stream_production_path": False,
        "nullable_item_status_pointer": True,
        "validated_frame_status_supported": True,
        "directed_rectangle_to_disk": True,
        "validated_rectangle_catalog_conversion": True,
        "directed_completed_l_disk_products": True,
        "completed_imaginary_must_contain_zero": True,
        "strict_sign_or_ambiguity_only": True,
        "dense_phase_state_associative": True,
        "exact_sparse_maximal_ambiguity_ranges": True,
        "exact_tgdcsb03_dense_device_pack": True,
        "dense_pack_independent_byte_reference_kat": True,
        "phase_states_cross_device_boundary": False,
        "tgdrnro1_root_binding_required": True,
        "canonical_primitive_ordinal_and_parity_binding_required": True,
        "exact_q_t_grid_binding_required": True,
        "arb_flint_bounded_differential_oracle": True,
        "factor_checkpoint_source_qualification_complete": False,
        "factor_single_step_quarter_turn_kat": True,
        "factor_initial_and_terminal_q5_arb_replay": True,
        "naive_common_q_pow_minus_s_deferral_valid": False,
        "q_pow_minus_s_deferral_obstruction": (
            "composer=q^-s*zeta_M+R_M with R_M unscaled"
        ),
        "allchars_device_integration_complete": False,
        "multiplicity_preserving_zero_lower_bound_realized": False,
        "turing_counts_realized": False,
        "source_scale_run_completed": False,
        "compiler_refinement_proved": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }


def _binary_box(value: Any) -> tuple[float, float, float, float]:
    from tg_verifier.dirichlet_root_number_stage import (
        _outward_binary_interval,
    )

    re_lo, re_hi = _outward_binary_interval(value.real)
    im_lo, im_hi = _outward_binary_interval(value.imag)
    return re_lo, re_hi, im_lo, im_hi


def _box_disk(
    box: Sequence[float],
) -> tuple[float, float, float]:
    if len(box) != 4:
        _fail("complex box must have four endpoints")
    re_lo, re_hi, im_lo, im_hi = box
    if not (
        all(math.isfinite(value) for value in box)
        and re_lo <= re_hi
        and im_lo <= im_hi
    ):
        _fail("complex box is malformed")
    # Match the CUDA center operations exactly: two binary64 multiplications
    # by 1/2 followed by one binary64 addition.
    real = 0.5 * re_lo + 0.5 * re_hi
    imaginary = 0.5 * im_lo + 0.5 * im_hi
    real_q = Fraction.from_float(real)
    imaginary_q = Fraction.from_float(imaginary)
    dx = max(
        abs(real_q - Fraction.from_float(re_lo)),
        abs(Fraction.from_float(re_hi) - real_q),
    )
    dy = max(
        abs(imaginary_q - Fraction.from_float(im_lo)),
        abs(Fraction.from_float(im_hi) - imaginary_q),
    )
    squared = dx * dx + dy * dy
    radius = math.sqrt(float(squared))
    while Fraction.from_float(radius) ** 2 < squared:
        radius = math.nextafter(radius, math.inf)
    if not math.isfinite(radius):
        _fail("box-to-disk radius is nonfinite")
    return real, imaginary, radius


def _sign(value: Any) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _write_qualification_fixture(
    path: Path,
    *,
    roots: Sequence[tuple[float, float, float]],
    gamma_scaled: Sequence[tuple[float, float, float]],
    conductor_checkpoints: Sequence[tuple[float, float, float]],
    conductor_step: tuple[float, float, float],
    checkpoint_span: int,
    parities: Sequence[int],
    values: Sequence[tuple[float, float, float, float]],
    sample_count: int,
) -> str:
    characters = len(roots)
    if (
        characters == 0
        or len(parities) != characters
        or len(gamma_scaled) != 2 * sample_count
        or not 1 <= checkpoint_span <= sample_count
        or len(conductor_checkpoints)
        != (sample_count + checkpoint_span - 1) // checkpoint_span
        or len(values) != characters * sample_count
        or characters * sample_count > MAXIMUM_QUALIFICATION_ITEMS
        or any(parity not in (0, 1) for parity in parities)
    ):
        _fail("qualification fixture dimensions differ")
    raw = bytearray(
        QUALIFICATION_HEADER.pack(
            QUALIFICATION_MAGIC,
            QUALIFICATION_VERSION,
            characters,
            sample_count,
            0,
            checkpoint_span,
            len(conductor_checkpoints),
            characters,
        )
    )
    for row in roots:
        raw.extend(DISK.pack(*row))
    for row in gamma_scaled:
        raw.extend(DISK.pack(*row))
    for row in conductor_checkpoints:
        raw.extend(DISK.pack(*row))
    raw.extend(DISK.pack(*conductor_step))
    raw.extend(bytes(parities))
    for row in values:
        raw.extend(COMPLEX_INTERVAL.pack(*row))
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _parse_runner_answer(raw: bytes, *, items: int) -> dict[str, Any]:
    try:
        answer = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletCompletedSignReducerError(
            f"CUDA qualification output is not JSON: {error}"
        ) from error
    if (
        not isinstance(answer, dict)
        or answer.get("algorithm")
        != "tg-dirichlet-completed-sign-reducer-arb-qualification-adapter-v1"
        or answer.get("source_status_or") != 0
        or answer.get("reducer_error_or") != 0
        or answer.get("gpu_factor_recurrence") is not True
        or answer.get("conductor_step_t_numerator") != 5
        or answer.get("conductor_step_t_denominator") != 128
        or answer.get("conductor_step_applications_per_sample") != 1
        or answer.get("raw_codes_production_path") is not False
        or not isinstance(answer.get("codes"), list)
        or len(answer["codes"]) != items
        or any(code not in (-1, 0, 1) for code in answer["codes"])
        or answer.get("source_scale_run_completed") is not False
        or answer.get("compiler_refinement_proved") is not False
        or answer.get("trusted_execution_attested") is not False
        or answer.get("external_atom_discharged") is not False
    ):
        _fail("CUDA qualification output identity or trust flags differ")
    return answer


def run_arb_differential_qualification(
    runner: Path,
    *,
    q: int = 5,
    first_t_index: int = 0,
    t_index_stop_exclusive: int = 512,
    precision: int = 256,
    factor_reseed_span: int = 4096,
) -> dict[str, Any]:
    """Compare bounded real-q/t CUDA decisions with direct Arb.

    The interval components are generated independently with python-flint.
    Every input is serialized outward to binary64.  The result reports both
    soundness (false determinate decisions) and enclosure quality (extra
    ambiguities relative to direct Arb and to a rectangular-component
    baseline).
    """

    if not runner.is_file():
        _fail("CUDA qualification runner is absent")
    if (
        isinstance(q, bool)
        or not isinstance(q, int)
        or not 3 <= q <= 10_000
        or isinstance(first_t_index, bool)
        or isinstance(t_index_stop_exclusive, bool)
        or not 0 <= first_t_index < t_index_stop_exclusive
        or t_index_stop_exclusive - first_t_index > 16_384
        or not 128 <= precision <= 4096
        or isinstance(factor_reseed_span, bool)
        or not isinstance(factor_reseed_span, int)
        or not 1 <= factor_reseed_span <= MAXIMUM_QUALIFICATION_SAMPLES
    ):
        _fail("bounded Arb qualification parameters differ")
    try:
        from flint import acb, arb, ctx, dirichlet_char
        from tg_verifier.dirichlet_root_number_stage import (
            _binary_rectangle,
            direct_root_records,
            primitive_frequency_records_bulk,
            require_flint,
        )
    except ImportError as error:
        raise DirichletCompletedSignReducerError(
            "pinned python-flint is required"
        ) from error
    require_flint()
    ctx.prec = precision
    roots = direct_root_records(q, precision=precision)
    identities = primitive_frequency_records_bulk(q)
    if len(roots) != len(identities) or not roots:
        _fail("direct root roster differs")
    characters = [
        dirichlet_char(q, row["conrey_number"])
        for row in identities
    ]
    for row, root, character in zip(identities, roots, characters):
        if (
            root["primitive_ordinal"] != row["primitive_ordinal"]
            or root["conrey_number"] != row["conrey_number"]
            or root["parity"] != row["parity"]
            or character.conductor() != q
            or not character.is_primitive()
        ):
            _fail("qualification primitive roster or root binding differs")

    root_boxes = [_binary_box(row["hardy_multiplier"]) for row in roots]
    root_disks = [_box_disk(box) for box in root_boxes]
    parities = [int(row["parity"]) for row in identities]
    false_determinate = 0
    opposite_determinate = 0
    extra_ambiguity = 0
    disk_extra_over_rectangle = 0
    arb_ambiguous = 0
    rectangle_ambiguous = 0
    gpu_ambiguous = 0
    compared = 0
    fixture_chain = hashlib.sha256()
    chunks = 0
    with tempfile.TemporaryDirectory() as temporary:
        root_path = Path(temporary)
        for chunk_first in range(
            first_t_index,
            t_index_stop_exclusive,
            MAXIMUM_QUALIFICATION_SAMPLES,
        ):
            chunk_stop = min(
                t_index_stop_exclusive,
                chunk_first + MAXIMUM_QUALIFICATION_SAMPLES,
            )
            samples = chunk_stop - chunk_first
            t_values = [
                arb(SOURCE_STEP_NUMERATOR * index) / SOURCE_DENOMINATOR
                for index in range(chunk_first, chunk_stop)
            ]
            conductor_values = [
                acb(
                    0, t * (arb(q) / arb.pi()).log() / 2
                ).exp()
                for t in t_values
            ]
            conductor_step = acb(
                0,
                arb(SOURCE_STEP_NUMERATOR)
                / (2 * SOURCE_DENOMINATOR)
                * (arb(q) / arb.pi()).log(),
            ).exp()
            checkpoint_span = min(factor_reseed_span, samples)
            conductor_checkpoints = [
                _box_disk(_binary_box(conductor_values[index]))
                for index in range(0, samples, checkpoint_span)
            ]
            factor_values: list[Any] = []
            factor_boxes: list[tuple[float, float, float, float]] = []
            gamma_disks: list[tuple[float, float, float]] = []
            for parity in (0, 1):
                for sample, t in enumerate(t_values):
                    gamma_argument = acb(
                        arb(1 + 2 * parity) / 4, t / 2
                    )
                    gamma_scaled = (
                        gamma_argument.gamma()
                        * (arb.pi() * t / 4).exp()
                    )
                    factor = conductor_values[sample] * gamma_scaled
                    box = _binary_box(factor)
                    factor_values.append(factor)
                    factor_boxes.append(box)
                    gamma_disks.append(
                        _box_disk(_binary_box(gamma_scaled))
                    )

            l_values: list[Any] = []
            l_boxes: list[tuple[float, float, float, float]] = []
            expected: list[int] = []
            rectangle_expected: list[int] = []
            for character_index, (character, root) in enumerate(
                zip(characters, roots)
            ):
                parity = parities[character_index]
                for sample, t in enumerate(t_values):
                    l_value = character.l_function(acb(arb("1/2"), t))
                    l_box = _binary_box(l_value)
                    factor_index = parity * samples + sample
                    completed = (
                        root["hardy_multiplier"]
                        * factor_values[factor_index]
                        * l_value
                    )
                    if not completed.imag.contains(0):
                        _fail(
                            "direct completed-L enclosure misses real axis"
                        )
                    direct_sign = _sign(completed.real)
                    rectangular = (
                        _binary_rectangle(root_boxes[character_index])
                        * _binary_rectangle(factor_boxes[factor_index])
                        * _binary_rectangle(l_box)
                    )
                    if not rectangular.imag.contains(0):
                        _fail(
                            "binary rectangular completed enclosure "
                            "misses real axis"
                        )
                    l_values.append(l_value)
                    l_boxes.append(l_box)
                    expected.append(direct_sign)
                    rectangle_expected.append(_sign(rectangular.real))

            fixture = root_path / f"chunk-{chunk_first}.bin"
            # Match allchars' resident t-major layout.  The qualification
            # kernel still reports codes in primitive-character-major order
            # for direct comparison with ``expected``.
            t_major_boxes = [
                l_boxes[character * samples + sample]
                for sample in range(samples)
                for character in range(len(characters))
            ]
            fixture_sha = _write_qualification_fixture(
                fixture,
                roots=root_disks,
                gamma_scaled=gamma_disks,
                conductor_checkpoints=conductor_checkpoints,
                conductor_step=_box_disk(_binary_box(conductor_step)),
                checkpoint_span=checkpoint_span,
                parities=parities,
                values=t_major_boxes,
                sample_count=samples,
            )
            fixture_chain.update(bytes.fromhex(fixture_sha))
            completed_process = subprocess.run(
                [str(runner), "--qualification", str(fixture)],
                check=False,
                capture_output=True,
                timeout=120,
            )
            if completed_process.returncode != 0:
                _fail(
                    "CUDA qualification runner failed: "
                    + completed_process.stderr[:4096].decode(
                        "utf-8", errors="replace"
                    )
                )
            answer = _parse_runner_answer(
                completed_process.stdout,
                items=len(expected),
            )
            for direct, rectangle, gpu in zip(
                expected, rectangle_expected, answer["codes"]
            ):
                compared += 1
                arb_ambiguous += int(direct == 0)
                rectangle_ambiguous += int(rectangle == 0)
                gpu_ambiguous += int(gpu == 0)
                if gpu != 0 and (direct == 0 or gpu != direct):
                    false_determinate += 1
                if gpu != 0 and direct != 0 and gpu != direct:
                    opposite_determinate += 1
                if gpu == 0 and direct != 0:
                    extra_ambiguity += 1
                if gpu == 0 and rectangle != 0:
                    disk_extra_over_rectangle += 1
            chunks += 1

    record: dict[str, Any] = {
        "schema": (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "arb_differential.v1"
        ),
        "algorithm_id": QUALIFICATION_ID,
        "author": AUTHOR,
        "classification": (
            "bounded_real_q_t_differential_not_source_or_atom_closure"
        ),
        "q": q,
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": t_index_stop_exclusive,
        "t_step_numerator": SOURCE_STEP_NUMERATOR,
        "t_denominator": SOURCE_DENOMINATOR,
        "primitive_character_count": len(identities),
        "chunk_count": chunks,
        "factor_reseed_span": factor_reseed_span,
        "gpu_checkpoint_factor_recurrence_used": True,
        "conductor_step_t_numerator": SOURCE_STEP_NUMERATOR,
        "conductor_step_t_denominator": 2 * SOURCE_DENOMINATOR,
        "conductor_step_applications_per_sample": 1,
        "sample_decisions_compared": compared,
        "arb_ambiguous": arb_ambiguous,
        "rectangular_component_ambiguous": rectangle_ambiguous,
        "gpu_disk_ambiguous": gpu_ambiguous,
        "false_determinate": false_determinate,
        "opposite_determinate": opposite_determinate,
        "extra_ambiguity_vs_direct_arb": extra_ambiguity,
        "extra_ambiguity_vs_rectangular_components": (
            disk_extra_over_rectangle
        ),
        "extra_ambiguity_rate": f"{extra_ambiguity}/{compared}",
        "disk_widening_rate": f"{disk_extra_over_rectangle}/{compared}",
        "completed_imaginary_real_axis_check_enforced": True,
        "qualification_fixture_chain_sha256": fixture_chain.hexdigest(),
        "raw_codes_production_path": False,
        "source_scale_run_completed": False,
        "compiler_refinement_proved": False,
        "trusted_execution_attested": False,
        "zero_completeness_claimed": False,
        "external_atom_discharged": False,
    }
    record["qualification_sha256"] = hashlib.sha256(
        _canonical_json(record)
    ).hexdigest()
    return record


def validate_qualification_result(value: Mapping[str, Any]) -> None:
    """Require the bounded soundness result without promoting source trust."""

    if (
        value.get("schema")
        != (
            "sparkinterval.tg.dirichlet_completed_sign_gpu_reducer."
            "arb_differential.v1"
        )
        or value.get("false_determinate") != 0
        or value.get("opposite_determinate") != 0
        or value.get("conductor_step_t_numerator") != 5
        or value.get("conductor_step_t_denominator") != 128
        or value.get("conductor_step_applications_per_sample") != 1
        or value.get("raw_codes_production_path") is not False
        or value.get("source_scale_run_completed") is not False
        or value.get("compiler_refinement_proved") is not False
        or value.get("trusted_execution_attested") is not False
        or value.get("zero_completeness_claimed") is not False
        or value.get("external_atom_discharged") is not False
    ):
        _fail("bounded qualification soundness or trust flags differ")
    body = dict(value)
    observed = body.pop("qualification_sha256", None)
    if (
        not isinstance(observed, str)
        or hashlib.sha256(_canonical_json(body)).hexdigest() != observed
    ):
        _fail("bounded qualification self-hash differs")


__all__ = [
    "ALGORITHM_ID",
    "DirichletCompletedSignReducerError",
    "capability",
    "factor_checkpoint_model",
    "run_arb_differential_qualification",
    "source_memory_model",
    "validate_qualification_result",
]

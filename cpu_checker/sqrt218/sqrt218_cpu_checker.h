/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#ifndef SPARKINTERVAL_SQRT218_CPU_CHECKER_H
#define SPARKINTERVAL_SQRT218_CPU_CHECKER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * This is the fixed-width V2 CPU-checker format.  It is deliberately
 * different from the registered canonical-JSON V1 archive.
 *
 * Multi-byte wire integers are unsigned big-endian.  The implementation
 * reads bytes explicitly: it does not cast untrusted input to a C struct.
 */
#define TG_SQ218_V2_HEADER_BYTES UINT64_C(160)
#define TG_SQ218_V2_PRIME_BYTES UINT64_C(80)
#define TG_SQ218_V2_FACTOR_REF_BYTES UINT64_C(8)
#define TG_SQ218_V2_FACTOR_PAIR_BYTES UINT64_C(16)
#define TG_SQ218_V2_EVENT_BYTES UINT64_C(32)
#define TG_SQ218_V2_POWER_REF_BYTES UINT64_C(8)

#define TG_SQ218_V2_VERSION UINT16_C(2)
#define TG_SQ218_LOG_SCALE UINT64_C(281474976710656)
#define TG_SQ218_RECIPROCAL_SCALE UINT64_C(1073741824)
#define TG_SQ218_LOG_SEED_AT UINT64_C(30)
#define TG_SQ218_PRODUCTION_BOUND UINT64_C(2000000)
#define TG_SQ218_PRODUCTION_REUSED_BOUND UINT64_C(1517397)

typedef struct tg_sq218_u128 {
    uint64_t hi;
    uint64_t lo;
} tg_sq218_u128;

typedef enum tg_sq218_status {
    TG_SQ218_OK = 0,
    TG_SQ218_BAD_ARGUMENT = 1,
    TG_SQ218_BAD_FORMAT = 2,
    TG_SQ218_OUT_OF_RANGE = 3,
    TG_SQ218_OVERFLOW = 4,
    TG_SQ218_PROOF_REJECTED = 5
} tg_sq218_status;

typedef struct tg_sq218_header_v2 {
    uint64_t bound;
    uint64_t reused_prime_bound;
    uint64_t log_seed_at;
    uint64_t log_scale;
    uint64_t reciprocal_scale;
    uint64_t prime_count;
    uint64_t factor_ref_count;
    uint64_t factor_pair_count;
    uint64_t event_count;
    uint64_t power_ref_count;
    uint64_t primes_offset;
    uint64_t factor_refs_offset;
    uint64_t factor_pairs_offset;
    uint64_t events_offset;
    uint64_t power_refs_offset;
    uint64_t archive_bytes;
} tg_sq218_header_v2;

typedef struct tg_sq218_prime_v2 {
    uint64_t prime;
    uint64_t witness;
    uint64_t factor_ref_index;
    uint32_t factor_ref_count;
    uint32_t gap_pair_count;
    uint64_t gap_pair_index;
    uint64_t power_ref_index;
    uint32_t power_ref_count;
    uint64_t log_lower;
    uint64_t log_upper;
} tg_sq218_prime_v2;

typedef struct tg_sq218_factor_pair_v2 {
    uint64_t left;
    uint64_t right;
} tg_sq218_factor_pair_v2;

typedef struct tg_sq218_event_v2 {
    uint64_t value;
    uint64_t prime_index;
    uint32_t exponent;
    uint64_t floor_sqrt;
} tg_sq218_event_v2;

typedef struct tg_sq218_view_v2 {
    const uint8_t *bytes;
    size_t length;
    tg_sq218_header_v2 header;
} tg_sq218_view_v2;

typedef struct tg_sq218_scan_state_v2 {
    uint64_t next_event;
    uint64_t last_event_value;
    tg_sq218_u128 weighted_upper;
    tg_sq218_u128 psi_lower;
} tg_sq218_scan_state_v2;

typedef struct tg_sq218_validation_result_v2 {
    tg_sq218_scan_state_v2 state;
    tg_sq218_u128 anchor_slack;
} tg_sq218_validation_result_v2;

/*
 * Exact two-u64 arithmetic.  The helper ABI is deliberately flat: 128-bit
 * values cross helper boundaries as scalar hi/lo limbs and results use
 * separate output pointers.  A zero return means overflow/underflow.
 */
int tg_sq218_u128_add_checked(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right_hi,
    uint64_t right_lo,
    uint64_t *out_hi,
    uint64_t *out_lo);
int tg_sq218_u128_sub_checked(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right_hi,
    uint64_t right_lo,
    uint64_t *out_hi,
    uint64_t *out_lo);
int tg_sq218_u128_mul_u64_checked(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right,
    uint64_t *out_hi,
    uint64_t *out_lo);
int tg_sq218_u128_compare(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right_hi,
    uint64_t right_lo);

/*
 * Parse and validate the fixed header and canonical, non-overlapping section
 * layout.  This performs no production replay.
 */
tg_sq218_status tg_sq218_view_open_v2(
    const uint8_t *bytes,
    size_t length,
    tg_sq218_view_v2 *out);

tg_sq218_status tg_sq218_prime_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    tg_sq218_prime_v2 *out);
tg_sq218_status tg_sq218_factor_ref_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    uint64_t *out);
tg_sq218_status tg_sq218_factor_pair_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    tg_sq218_factor_pair_v2 *out);
tg_sq218_status tg_sq218_event_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    tg_sq218_event_v2 *out);
tg_sq218_status tg_sq218_power_ref_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    uint64_t *out);

/*
 * Validate the efficient V2 prime-roster witnesses:
 *
 *   - each factor of p - 1 references an earlier prime row;
 *   - the referenced values multiply exactly to p - 1;
 *   - the Lucas/Pratt modular residues pass; and
 *   - factor-pair records cover every gap and the terminal interval.
 *
 * `CPUChecker/CRosterRefinement.lean` proves that the complete successful
 * source-shaped trace implies the exact architecture-neutral V2 roster
 * Boolean.  Compiler/ELF/ISA refinement is a separate boundary; this C
 * return value is not itself a Lean theorem.
 */
tg_sq218_status tg_sq218_validate_roster_v2(
    const tg_sq218_view_v2 *view);

/*
 * Validate the flattened per-prime inverse map.  Each prime row names the
 * event indices for exponents 1, 2, ...; the total reference count equals the
 * event count.  This is the linear-size certificate consumed by the proved
 * Operational.V2.PowerLayout checker.  The successful source-shaped loop is
 * refined in `CPUChecker/CPowerLayoutRefinement.lean`.
 */
tg_sq218_status tg_sq218_validate_power_layout_v2(
    const tg_sq218_view_v2 *view);

/*
 * Check the exact 30-seed table endpoints and then advance the integer
 * scale-2^48 recurrence once through the gaps between consecutive prime rows.
 */
tg_sq218_status tg_sq218_validate_log_ladder_v2(
    const tg_sq218_view_v2 *view);

/* Initialize and advance the checked fixed-point event arithmetic. */
void tg_sq218_scan_initial_v2(tg_sq218_scan_state_v2 *out);
tg_sq218_status tg_sq218_scan_step_v2(
    const tg_sq218_view_v2 *view,
    tg_sq218_scan_state_v2 *state);
tg_sq218_status tg_sq218_scan_all_events_v2(
    const tg_sq218_view_v2 *view,
    tg_sq218_scan_state_v2 *out);

/*
 * Check the endpoint Abel guard and return its positive slack.  This is only
 * the integer arithmetic stage: roster/layout/log-ladder validation remains
 * a separate required stage.
 */
tg_sq218_status tg_sq218_anchor_v2(
    const tg_sq218_view_v2 *view,
    const tg_sq218_scan_state_v2 *state,
    tg_sq218_u128 *slack);

/*
 * Sole production entry point: parse the exact bytes, require the production
 * profile, then validate roster, layout, logs, event fold, and anchor.  The
 * internal all-stages routine is deliberately not exposed for callers to
 * invoke with a hand-built view.
 *
 * `bytes[0..length)` must be an immutable private snapshot for the complete
 * call, and `out` must not overlap that snapshot.  The measured executable
 * must hash and retain those same snapshot bytes when constructing its
 * result/receipt binding.
 */
tg_sq218_status tg_sq218_validate_bytes_v2(
    const uint8_t *bytes,
    size_t length,
    tg_sq218_validation_result_v2 *out);

#ifdef __cplusplus
}
#endif

#endif

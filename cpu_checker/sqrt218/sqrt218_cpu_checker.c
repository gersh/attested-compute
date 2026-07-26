/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#include "sqrt218_cpu_checker.h"

#include <limits.h>

static const uint8_t tg_sq218_magic_v2[8] = {
    UINT8_C(0x53), UINT8_C(0x51), UINT8_C(0x32), UINT8_C(0x31),
    UINT8_C(0x38), UINT8_C(0x56), UINT8_C(0x32), UINT8_C(0x00)
};

static uint16_t tg_read_be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | (uint16_t)p[1]);
}

static uint32_t tg_read_be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24)
        | ((uint32_t)p[1] << 16)
        | ((uint32_t)p[2] << 8)
        | (uint32_t)p[3];
}

static uint64_t tg_read_be64(const uint8_t *p)
{
    return ((uint64_t)p[0] << 56)
        | ((uint64_t)p[1] << 48)
        | ((uint64_t)p[2] << 40)
        | ((uint64_t)p[3] << 32)
        | ((uint64_t)p[4] << 24)
        | ((uint64_t)p[5] << 16)
        | ((uint64_t)p[6] << 8)
        | (uint64_t)p[7];
}

static int tg_u64_add_checked(uint64_t a, uint64_t b, uint64_t *out)
{
    uint64_t result = a + b;
    if (result < a) {
        return 0;
    }
    *out = result;
    return 1;
}

static int tg_u64_mul_checked(uint64_t a, uint64_t b, uint64_t *out)
{
    if (a != 0 && b > UINT64_MAX / a) {
        return 0;
    }
    *out = a * b;
    return 1;
}

static void tg_mul64_wide(
    uint64_t a,
    uint64_t b,
    uint64_t *high,
    uint64_t *low)
{
    const uint64_t mask = UINT64_C(0xffffffff);
    uint64_t a0 = a & mask;
    uint64_t a1 = a >> 32;
    uint64_t b0 = b & mask;
    uint64_t b1 = b >> 32;
    uint64_t p00 = a0 * b0;
    uint64_t p01 = a0 * b1;
    uint64_t p10 = a1 * b0;
    uint64_t p11 = a1 * b1;
    uint64_t middle =
        (p00 >> 32) + (p01 & mask) + (p10 & mask);

    *low = (p00 & mask) | (middle << 32);
    *high = p11 + (p01 >> 32) + (p10 >> 32) + (middle >> 32);
}

int tg_sq218_u128_compare(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right_hi,
    uint64_t right_lo)
{
    if (left_hi < right_hi) {
        return -1;
    }
    if (left_hi > right_hi) {
        return 1;
    }
    if (left_lo < right_lo) {
        return -1;
    }
    if (left_lo > right_lo) {
        return 1;
    }
    return 0;
}

int tg_sq218_u128_add_checked(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right_hi,
    uint64_t right_lo,
    uint64_t *out_hi,
    uint64_t *out_lo)
{
    uint64_t lo;
    uint64_t hi;
    uint64_t carry;

    if (out_hi == NULL || out_lo == NULL || out_hi == out_lo) {
        return 0;
    }
    lo = left_lo + right_lo;
    carry = lo < left_lo ? UINT64_C(1) : UINT64_C(0);
    hi = left_hi + right_hi;
    if (hi < left_hi || UINT64_MAX - hi < carry) {
        return 0;
    }
    *out_hi = hi + carry;
    *out_lo = lo;
    return 1;
}

int tg_sq218_u128_sub_checked(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right_hi,
    uint64_t right_lo,
    uint64_t *out_hi,
    uint64_t *out_lo)
{
    uint64_t borrow;

    if (out_hi == NULL || out_lo == NULL || out_hi == out_lo
        || tg_sq218_u128_compare(
            left_hi, left_lo, right_hi, right_lo) < 0) {
        return 0;
    }
    borrow = left_lo < right_lo ? UINT64_C(1) : UINT64_C(0);
    *out_lo = left_lo - right_lo;
    *out_hi = left_hi - right_hi - borrow;
    return 1;
}

int tg_sq218_u128_mul_u64_checked(
    uint64_t left_hi,
    uint64_t left_lo,
    uint64_t right,
    uint64_t *out_hi,
    uint64_t *out_lo)
{
    uint64_t low_high;
    uint64_t low_low;
    uint64_t high_high;
    uint64_t high_low;
    uint64_t result_high;

    if (out_hi == NULL || out_lo == NULL || out_hi == out_lo) {
        return 0;
    }
    tg_mul64_wide(left_lo, right, &low_high, &low_low);
    tg_mul64_wide(left_hi, right, &high_high, &high_low);
    if (high_high != 0 || !tg_u64_add_checked(
            high_low, low_high, &result_high)) {
        return 0;
    }
    *out_hi = result_high;
    *out_lo = low_low;
    return 1;
}

static int tg_same_magic(const uint8_t *bytes)
{
    size_t i;
    for (i = 0; i < sizeof(tg_sq218_magic_v2); ++i) {
        if (bytes[i] != tg_sq218_magic_v2[i]) {
            return 0;
        }
    }
    return 1;
}

static int tg_section_end(
    uint64_t start,
    uint64_t count,
    uint64_t width,
    uint64_t *out)
{
    uint64_t bytes;
    return tg_u64_mul_checked(count, width, &bytes)
        && tg_u64_add_checked(start, bytes, out);
}

static int tg_range_inside(
    const tg_sq218_view_v2 *view,
    uint64_t offset,
    uint64_t width)
{
    uint64_t end;
    return view != NULL
        && tg_u64_add_checked(offset, width, &end)
        && end <= (uint64_t)view->length;
}

tg_sq218_status tg_sq218_view_open_v2(
    const uint8_t *bytes,
    size_t length,
    tg_sq218_view_v2 *out)
{
    tg_sq218_header_v2 header;
    uint64_t expected;

    if (bytes == NULL || out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    if (length < (size_t)TG_SQ218_V2_HEADER_BYTES) {
        return TG_SQ218_BAD_FORMAT;
    }
    if (!tg_same_magic(bytes)
        || tg_read_be16(bytes + 8) != TG_SQ218_V2_VERSION
        || tg_read_be16(bytes + 10) != TG_SQ218_V2_HEADER_BYTES
        || tg_read_be32(bytes + 12) != 0) {
        return TG_SQ218_BAD_FORMAT;
    }

    header.bound = tg_read_be64(bytes + 16);
    header.reused_prime_bound = tg_read_be64(bytes + 24);
    header.log_seed_at = tg_read_be64(bytes + 32);
    header.log_scale = tg_read_be64(bytes + 40);
    header.reciprocal_scale = tg_read_be64(bytes + 48);
    header.prime_count = tg_read_be64(bytes + 56);
    header.factor_ref_count = tg_read_be64(bytes + 64);
    header.factor_pair_count = tg_read_be64(bytes + 72);
    header.event_count = tg_read_be64(bytes + 80);
    header.power_ref_count = tg_read_be64(bytes + 88);
    header.primes_offset = tg_read_be64(bytes + 96);
    header.factor_refs_offset = tg_read_be64(bytes + 104);
    header.factor_pairs_offset = tg_read_be64(bytes + 112);
    header.events_offset = tg_read_be64(bytes + 120);
    header.power_refs_offset = tg_read_be64(bytes + 128);
    header.archive_bytes = tg_read_be64(bytes + 136);
    if (tg_read_be64(bytes + 144) != 0
        || tg_read_be64(bytes + 152) != 0) {
        return TG_SQ218_BAD_FORMAT;
    }

    if (header.bound < 2
        || header.reused_prime_bound > header.bound
        || header.log_seed_at != TG_SQ218_LOG_SEED_AT
        || header.log_scale != TG_SQ218_LOG_SCALE
        || header.reciprocal_scale != TG_SQ218_RECIPROCAL_SCALE
        || header.prime_count == 0
        || header.power_ref_count != header.event_count
        || header.primes_offset != TG_SQ218_V2_HEADER_BYTES) {
        return TG_SQ218_BAD_FORMAT;
    }

    expected = header.primes_offset;
    if (!tg_section_end(
            expected,
            header.prime_count,
            TG_SQ218_V2_PRIME_BYTES,
            &expected)
        || header.factor_refs_offset != expected
        || !tg_section_end(
            expected,
            header.factor_ref_count,
            TG_SQ218_V2_FACTOR_REF_BYTES,
            &expected)
        || header.factor_pairs_offset != expected
        || !tg_section_end(
            expected,
            header.factor_pair_count,
            TG_SQ218_V2_FACTOR_PAIR_BYTES,
            &expected)
        || header.events_offset != expected
        || !tg_section_end(
            expected,
            header.event_count,
            TG_SQ218_V2_EVENT_BYTES,
            &expected)
        || header.power_refs_offset != expected
        || !tg_section_end(
            expected,
            header.power_ref_count,
            TG_SQ218_V2_POWER_REF_BYTES,
            &expected)
        || header.archive_bytes != expected
        || expected > (uint64_t)SIZE_MAX
        || (size_t)expected != length) {
        return TG_SQ218_BAD_FORMAT;
    }

    out->bytes = bytes;
    out->length = length;
    out->header = header;
    return TG_SQ218_OK;
}

static tg_sq218_status tg_record_offset(
    const tg_sq218_view_v2 *view,
    uint64_t section,
    uint64_t count,
    uint64_t width,
    uint64_t index,
    uint64_t *out)
{
    uint64_t displacement;

    if (view == NULL || out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    if (index >= count
        || !tg_u64_mul_checked(index, width, &displacement)
        || !tg_u64_add_checked(section, displacement, out)
        || !tg_range_inside(view, *out, width)) {
        return TG_SQ218_OUT_OF_RANGE;
    }
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_prime_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    tg_sq218_prime_v2 *out)
{
    uint64_t offset;
    const uint8_t *p;
    tg_sq218_status status;

    if (out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    status = tg_record_offset(
        view,
        view == NULL ? 0 : view->header.primes_offset,
        view == NULL ? 0 : view->header.prime_count,
        TG_SQ218_V2_PRIME_BYTES,
        index,
        &offset);
    if (status != TG_SQ218_OK) {
        return status;
    }
    p = view->bytes + (size_t)offset;
    if (tg_read_be32(p + 52) != 0
        || tg_read_be64(p + 72) != 0) {
        return TG_SQ218_BAD_FORMAT;
    }
    out->prime = tg_read_be64(p);
    out->witness = tg_read_be64(p + 8);
    out->factor_ref_index = tg_read_be64(p + 16);
    out->factor_ref_count = tg_read_be32(p + 24);
    out->gap_pair_count = tg_read_be32(p + 28);
    out->gap_pair_index = tg_read_be64(p + 32);
    out->power_ref_index = tg_read_be64(p + 40);
    out->power_ref_count = tg_read_be32(p + 48);
    out->log_lower = tg_read_be64(p + 56);
    out->log_upper = tg_read_be64(p + 64);
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_factor_ref_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    uint64_t *out)
{
    uint64_t offset;
    tg_sq218_status status;

    if (out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    status = tg_record_offset(
        view,
        view == NULL ? 0 : view->header.factor_refs_offset,
        view == NULL ? 0 : view->header.factor_ref_count,
        TG_SQ218_V2_FACTOR_REF_BYTES,
        index,
        &offset);
    if (status != TG_SQ218_OK) {
        return status;
    }
    *out = tg_read_be64(view->bytes + (size_t)offset);
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_factor_pair_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    tg_sq218_factor_pair_v2 *out)
{
    uint64_t offset;
    const uint8_t *p;
    tg_sq218_status status;

    if (out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    status = tg_record_offset(
        view,
        view == NULL ? 0 : view->header.factor_pairs_offset,
        view == NULL ? 0 : view->header.factor_pair_count,
        TG_SQ218_V2_FACTOR_PAIR_BYTES,
        index,
        &offset);
    if (status != TG_SQ218_OK) {
        return status;
    }
    p = view->bytes + (size_t)offset;
    out->left = tg_read_be64(p);
    out->right = tg_read_be64(p + 8);
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_event_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    tg_sq218_event_v2 *out)
{
    uint64_t offset;
    const uint8_t *p;
    tg_sq218_status status;

    if (out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    status = tg_record_offset(
        view,
        view == NULL ? 0 : view->header.events_offset,
        view == NULL ? 0 : view->header.event_count,
        TG_SQ218_V2_EVENT_BYTES,
        index,
        &offset);
    if (status != TG_SQ218_OK) {
        return status;
    }
    p = view->bytes + (size_t)offset;
    if (tg_read_be32(p + 20) != 0) {
        return TG_SQ218_BAD_FORMAT;
    }
    out->value = tg_read_be64(p);
    out->prime_index = tg_read_be64(p + 8);
    out->exponent = tg_read_be32(p + 16);
    out->floor_sqrt = tg_read_be64(p + 24);
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_power_ref_at_v2(
    const tg_sq218_view_v2 *view,
    uint64_t index,
    uint64_t *out)
{
    uint64_t offset;
    tg_sq218_status status;

    if (out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    status = tg_record_offset(
        view,
        view == NULL ? 0 : view->header.power_refs_offset,
        view == NULL ? 0 : view->header.power_ref_count,
        TG_SQ218_V2_POWER_REF_BYTES,
        index,
        &offset);
    if (status != TG_SQ218_OK) {
        return status;
    }
    *out = tg_read_be64(view->bytes + (size_t)offset);
    return TG_SQ218_OK;
}

static uint64_t tg_add_mod(uint64_t a, uint64_t b, uint64_t modulus)
{
    if (a >= modulus - b) {
        return a - (modulus - b);
    }
    return a + b;
}

static uint64_t tg_mul_mod(uint64_t a, uint64_t b, uint64_t modulus)
{
    uint64_t result = 0;
    a %= modulus;
    while (b != 0) {
        if ((b & UINT64_C(1)) != 0) {
            result = tg_add_mod(result, a, modulus);
        }
        b >>= 1;
        if (b != 0) {
            a = tg_add_mod(a, a, modulus);
        }
    }
    return result;
}

static uint64_t tg_pow_mod(
    uint64_t base,
    uint64_t exponent,
    uint64_t modulus)
{
    uint64_t result = UINT64_C(1) % modulus;
    base %= modulus;
    while (exponent != 0) {
        if ((exponent & UINT64_C(1)) != 0) {
            result = tg_mul_mod(result, base, modulus);
        }
        exponent >>= 1;
        if (exponent != 0) {
            base = tg_mul_mod(base, base, modulus);
        }
    }
    return result;
}

static tg_sq218_status tg_validate_gap_pair(
    const tg_sq218_view_v2 *view,
    uint64_t pair_index,
    uint64_t value)
{
    tg_sq218_factor_pair_v2 pair;
    uint64_t product;
    tg_sq218_status status =
        tg_sq218_factor_pair_at_v2(view, pair_index, &pair);

    if (status != TG_SQ218_OK) {
        return status;
    }
    if (pair.left <= 1
        || pair.right <= 1
        || !tg_u64_mul_checked(pair.left, pair.right, &product)
        || product != value) {
        return TG_SQ218_PROOF_REJECTED;
    }
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_validate_roster_v2(
    const tg_sq218_view_v2 *view)
{
    uint64_t row_index;
    uint64_t next_factor = 0;
    uint64_t next_gap = 0;
    uint64_t terminal_local = 0;
    uint64_t previous = 1;
    tg_sq218_status status;

    if (view == NULL || view->bytes == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    for (row_index = 0;
         row_index < view->header.prime_count;
         ++row_index) {
        tg_sq218_prime_v2 row;
        uint64_t factor_offset;
        uint64_t factor_end;
        uint64_t gap_end;
        uint64_t factor_product = 1;
        uint64_t factor_local;
        uint64_t gap_local;

        status = tg_sq218_prime_at_v2(view, row_index, &row);
        if (status != TG_SQ218_OK) {
            return status;
        }
        if (row.factor_ref_index != next_factor
            || row.gap_pair_index != next_gap
            || row.prime <= previous
            || row.prime > view->header.bound
            || row.log_lower > row.log_upper
            || !tg_u64_add_checked(
                row.factor_ref_index,
                (uint64_t)row.factor_ref_count,
                &factor_end)
            || factor_end > view->header.factor_ref_count
            || !tg_u64_add_checked(
                row.gap_pair_index,
                (uint64_t)row.gap_pair_count,
                &gap_end)
            || gap_end > view->header.factor_pair_count
            || (uint64_t)row.gap_pair_count != row.prime - previous - 1) {
            return TG_SQ218_PROOF_REJECTED;
        }

        factor_offset = row.factor_ref_index;
        for (factor_local = 0;
             factor_local < (uint64_t)row.factor_ref_count;
             ++factor_local) {
            uint64_t reference;
            tg_sq218_prime_v2 factor_row;

            status = tg_sq218_factor_ref_at_v2(
                view, factor_offset + factor_local, &reference);
            if (status != TG_SQ218_OK) {
                return status;
            }
            if (reference >= row_index) {
                return TG_SQ218_PROOF_REJECTED;
            }
            status = tg_sq218_prime_at_v2(view, reference, &factor_row);
            if (status != TG_SQ218_OK) {
                return status;
            }
            if (!tg_u64_mul_checked(
                    factor_product, factor_row.prime, &factor_product)) {
                return TG_SQ218_OVERFLOW;
            }
        }
        if (factor_product != row.prime - 1) {
            return TG_SQ218_PROOF_REJECTED;
        }
        if (row.prime == 2) {
            if (row_index != 0
                || row.witness != 0
                || row.factor_ref_count != 0) {
                return TG_SQ218_PROOF_REJECTED;
            }
        } else {
            if (row.factor_ref_count == 0
                || row.witness < 2
                || row.witness >= row.prime
                || tg_pow_mod(
                    row.witness, row.prime - 1, row.prime) != 1) {
                return TG_SQ218_PROOF_REJECTED;
            }
            for (factor_local = 0;
                 factor_local < (uint64_t)row.factor_ref_count;
                 ++factor_local) {
                uint64_t reference;
                tg_sq218_prime_v2 factor_row;

                status = tg_sq218_factor_ref_at_v2(
                    view, factor_offset + factor_local, &reference);
                if (status != TG_SQ218_OK) {
                    return status;
                }
                status = tg_sq218_prime_at_v2(
                    view, reference, &factor_row);
                if (status != TG_SQ218_OK) {
                    return status;
                }
                if (tg_pow_mod(
                        row.witness,
                        (row.prime - 1) / factor_row.prime,
                        row.prime) == 1) {
                    return TG_SQ218_PROOF_REJECTED;
                }
            }
        }

        for (gap_local = 0;
             gap_local < (uint64_t)row.gap_pair_count;
             ++gap_local) {
            uint64_t value;
            if (!tg_u64_add_checked(
                    previous, gap_local + 1, &value)) {
                return TG_SQ218_OVERFLOW;
            }
            status = tg_validate_gap_pair(
                view, row.gap_pair_index + gap_local, value);
            if (status != TG_SQ218_OK) {
                return status;
            }
        }
        next_factor = factor_end;
        next_gap = gap_end;
        previous = row.prime;
    }

    if (previous > view->header.bound
        || view->header.factor_ref_count != next_factor
        || view->header.factor_pair_count - next_gap
            != view->header.bound - previous) {
        return TG_SQ218_PROOF_REJECTED;
    }
    while (next_gap < view->header.factor_pair_count) {
        uint64_t value;
        if (!tg_u64_add_checked(
                previous, terminal_local + 1,
                &value)) {
            return TG_SQ218_OVERFLOW;
        }
        status = tg_validate_gap_pair(view, next_gap, value);
        if (status != TG_SQ218_OK) {
            return status;
        }
        ++next_gap;
        ++terminal_local;
    }
    return TG_SQ218_OK;
}

void tg_sq218_scan_initial_v2(tg_sq218_scan_state_v2 *out)
{
    if (out != NULL) {
        out->next_event = 0;
        out->last_event_value = 0;
        out->weighted_upper.hi = 0;
        out->weighted_upper.lo = 0;
        out->psi_lower.hi = 0;
        out->psi_lower.lo = 0;
    }
}

static int tg_floor_sqrt_ok(uint64_t value, uint64_t root)
{
    uint64_t successor;
    if (root == 0) {
        return value == 0;
    }
    if (root > value / root || root == UINT64_MAX) {
        return 0;
    }
    successor = root + 1;
    return successor > value / successor;
}

static int tg_pow_u64_checked(
    uint64_t base,
    uint32_t exponent,
    uint64_t *out)
{
    uint64_t result = 1;
    uint64_t factor = base;
    uint32_t remaining = exponent;

    while (remaining != 0) {
        if ((remaining & UINT32_C(1)) != 0
            && !tg_u64_mul_checked(result, factor, &result)) {
            return 0;
        }
        remaining >>= 1;
        if (remaining != 0
            && !tg_u64_mul_checked(factor, factor, &factor)) {
            return 0;
        }
    }
    *out = result;
    return 1;
}

tg_sq218_status tg_sq218_validate_power_layout_v2(
    const tg_sq218_view_v2 *view)
{
    uint64_t event_index;
    uint64_t row_index;
    uint64_t next_power_ref = 0;
    uint64_t previous_value = 0;
    tg_sq218_status status;

    if (view == NULL || view->bytes == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    if (view->header.power_ref_count
        != view->header.event_count) {
        return TG_SQ218_PROOF_REJECTED;
    }

    for (event_index = 0;
         event_index < view->header.event_count;
         ++event_index) {
        tg_sq218_event_v2 event;
        tg_sq218_prime_v2 prime;
        uint64_t expected_power;

        status = tg_sq218_event_at_v2(view, event_index, &event);
        if (status != TG_SQ218_OK) {
            return status;
        }
        if (event.prime_index >= view->header.prime_count) {
            return TG_SQ218_PROOF_REJECTED;
        }
        status = tg_sq218_prime_at_v2(
            view, event.prime_index, &prime);
        if (status != TG_SQ218_OK) {
            return status;
        }
        if (event.exponent == 0
            || event.value > view->header.bound
            || !tg_floor_sqrt_ok(event.value, event.floor_sqrt)
            || !tg_pow_u64_checked(
                prime.prime, event.exponent, &expected_power)
            || expected_power != event.value
            || (event_index != 0
                && event.value <= previous_value)) {
            return TG_SQ218_PROOF_REJECTED;
        }
        previous_value = event.value;
    }

    for (row_index = 0;
         row_index < view->header.prime_count;
         ++row_index) {
        tg_sq218_prime_v2 row;
        uint64_t power_ref_end;
        uint64_t local;
        uint64_t last_power = 0;

        status = tg_sq218_prime_at_v2(view, row_index, &row);
        if (status != TG_SQ218_OK) {
            return status;
        }
        if (row.power_ref_index != next_power_ref
            || row.power_ref_count == 0
            || !tg_u64_add_checked(
                row.power_ref_index,
                (uint64_t)row.power_ref_count,
                &power_ref_end)
            || power_ref_end > view->header.power_ref_count) {
            return TG_SQ218_PROOF_REJECTED;
        }
        for (local = 0;
             local < (uint64_t)row.power_ref_count;
             ++local) {
            uint64_t reference;
            tg_sq218_event_v2 event;

            status = tg_sq218_power_ref_at_v2(
                view, row.power_ref_index + local, &reference);
            if (status != TG_SQ218_OK) {
                return status;
            }
            if (reference >= view->header.event_count) {
                return TG_SQ218_PROOF_REJECTED;
            }
            status = tg_sq218_event_at_v2(
                view, reference, &event);
            if (status != TG_SQ218_OK) {
                return status;
            }
            if (event.prime_index != row_index
                || event.exponent != (uint32_t)(local + 1)) {
                return TG_SQ218_PROOF_REJECTED;
            }
            last_power = event.value;
        }
        if (last_power > view->header.bound) {
            return TG_SQ218_PROOF_REJECTED;
        }
        {
            uint64_t next_power;
            if (tg_u64_mul_checked(
                    last_power, row.prime, &next_power)
                && next_power <= view->header.bound) {
                return TG_SQ218_PROOF_REJECTED;
            }
        }
        next_power_ref = power_ref_end;
    }
    if (next_power_ref != view->header.power_ref_count) {
        return TG_SQ218_PROOF_REJECTED;
    }
    return TG_SQ218_OK;
}

static const uint64_t tg_sq218_log_seeds[30][2] = {
    {UINT64_C(0), UINT64_C(0)},
    {UINT64_C(195103586431999), UINT64_C(195103586572737)},
    {UINT64_C(309231868028532), UINT64_C(309231868693940)},
    {UINT64_C(390207172863998), UINT64_C(390207173145474)},
    {UINT64_C(453016498773239), UINT64_C(453016499054997)},
    {UINT64_C(504335454460532), UINT64_C(504335455266677)},
    {UINT64_C(547725013666734), UINT64_C(547725014089229)},
    {UINT64_C(585310759295998), UINT64_C(585310759718211)},
    {UINT64_C(618463736514181), UINT64_C(618463736936676)},
    {UINT64_C(648120085205239), UINT64_C(648120085627734)},
    {UINT64_C(674947515845858), UINT64_C(674947516268353)},
    {UINT64_C(699439040892531), UINT64_C(699439041839414)},
    {UINT64_C(721969060362613), UINT64_C(721969060925845)},
    {UINT64_C(742828600098734), UINT64_C(742828600661966)},
    {UINT64_C(762248366993738), UINT64_C(762248367556971)},
    {UINT64_C(780414345727997), UINT64_C(780414346290948)},
    {UINT64_C(797478659741748), UINT64_C(797478660304980)},
    {UINT64_C(813567322946180), UINT64_C(813567323509412)},
    {UINT64_C(828785892793963), UINT64_C(828785893357196)},
    {UINT64_C(843223671637238), UINT64_C(843223672200471)},
    {UINT64_C(856956881960417), UINT64_C(856956882523649)},
    {UINT64_C(870051102277858), UINT64_C(870051102841090)},
    {UINT64_C(882563161108618), UINT64_C(882563161679169)},
    {UINT64_C(894542627324530), UINT64_C(894542628412151)},
    {UINT64_C(906032997473296), UINT64_C(906032998177266)},
    {UINT64_C(917072646794612), UINT64_C(917072647498582)},
    {UINT64_C(927695604734679), UINT64_C(927695605438649)},
    {UINT64_C(937932186530733), UINT64_C(937932187234703)},
    {UINT64_C(947809514957280), UINT64_C(947809515661250)},
    {UINT64_C(957351953425738), UINT64_C(957351954129708)}
};

/*
 * Restoring division of two explicit limbs by one u64.  A quotient needing
 * more than one u64 is rejected instead of truncated.
 */
static int tg_u128_div_u64(
    uint64_t numerator_hi,
    uint64_t numerator_lo,
    uint64_t denominator,
    uint64_t *quotient,
    uint64_t *remainder)
{
    uint64_t rem_hi = 0;
    uint64_t rem_lo = 0;
    uint64_t result = 0;
    unsigned position;

    if (denominator == 0 || quotient == NULL || remainder == NULL) {
        return 0;
    }
    for (position = 128; position != 0; --position) {
        unsigned bit_index = position - 1;
        uint64_t bit;

        if (rem_hi > 1 || (rem_hi & (UINT64_C(1) << 63)) != 0) {
            return 0;
        }
        if (bit_index >= 64) {
            bit = (numerator_hi >> (bit_index - 64)) & UINT64_C(1);
        } else {
            bit = (numerator_lo >> bit_index) & UINT64_C(1);
        }
        rem_hi = (rem_hi << 1) | (rem_lo >> 63);
        rem_lo = (rem_lo << 1) | bit;
        if (tg_sq218_u128_compare(
                rem_hi, rem_lo, 0, denominator) >= 0) {
            if (!tg_sq218_u128_sub_checked(
                    rem_hi,
                    rem_lo,
                    0,
                    denominator,
                    &rem_hi,
                    &rem_lo)
                || bit_index >= 64) {
                return 0;
            }
            result |= UINT64_C(1) << bit_index;
        }
    }
    if (rem_hi != 0) {
        return 0;
    }
    *quotient = result;
    *remainder = rem_lo;
    return 1;
}

static tg_sq218_status tg_log_ladder_next(
    const tg_sq218_view_v2 *view,
    uint64_t position,
    uint64_t *lower,
    uint64_t *upper)
{
    uint64_t square;
    uint64_t twice_square;
    uint64_t triple_position;
    uint64_t base_polynomial;
    uint64_t lower_polynomial;
    uint64_t upper_polynomial;
    uint64_t denominator;
    uint64_t lower_increment;
    uint64_t upper_increment;
    uint64_t remainder;
    tg_sq218_u128 numerator;

    if (view == NULL || lower == NULL || upper == NULL
        || position < TG_SQ218_LOG_SEED_AT
        || !tg_u64_mul_checked(position, position, &square)
        || !tg_u64_mul_checked(2, square, &twice_square)
        || !tg_u64_mul_checked(3, position, &triple_position)
        || twice_square <= triple_position
        || !tg_u64_mul_checked(2, square, &denominator)
        || !tg_u64_mul_checked(
            denominator, position - 1, &denominator)) {
        return TG_SQ218_OVERFLOW;
    }
    base_polynomial = twice_square - triple_position;
    lower_polynomial = base_polynomial - 1;
    if (!tg_u64_add_checked(
            base_polynomial, 3, &upper_polynomial)) {
        return TG_SQ218_OVERFLOW;
    }

    numerator.hi = 0;
    numerator.lo = view->header.log_scale;
    if (!tg_sq218_u128_mul_u64_checked(
            numerator.hi,
            numerator.lo,
            lower_polynomial,
            &numerator.hi,
            &numerator.lo)
        || !tg_u128_div_u64(
            numerator.hi,
            numerator.lo,
            denominator,
            &lower_increment,
            &remainder)
        || !tg_u64_add_checked(*lower, lower_increment, lower)) {
        return TG_SQ218_OVERFLOW;
    }

    numerator.hi = 0;
    numerator.lo = view->header.log_scale;
    if (!tg_sq218_u128_mul_u64_checked(
            numerator.hi,
            numerator.lo,
            upper_polynomial,
            &numerator.hi,
            &numerator.lo)
        || !tg_u128_div_u64(
            numerator.hi,
            numerator.lo,
            denominator,
            &upper_increment,
            &remainder)) {
        return TG_SQ218_OVERFLOW;
    }
    if (remainder != 0
        && !tg_u64_add_checked(
            upper_increment, 1, &upper_increment)) {
        return TG_SQ218_OVERFLOW;
    }
    if (!tg_u64_add_checked(*upper, upper_increment, upper)) {
        return TG_SQ218_OVERFLOW;
    }
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_validate_log_ladder_v2(
    const tg_sq218_view_v2 *view)
{
    uint64_t position = 1;
    uint64_t lower = tg_sq218_log_seeds[0][0];
    uint64_t upper = tg_sq218_log_seeds[0][1];
    uint64_t row_index;

    if (view == NULL || view->bytes == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    for (row_index = 0;
         row_index < view->header.prime_count;
         ++row_index) {
        tg_sq218_prime_v2 row;
        tg_sq218_status status =
            tg_sq218_prime_at_v2(view, row_index, &row);
        if (status != TG_SQ218_OK) {
            return status;
        }
        if (row.prime <= position
            || row.prime > view->header.bound) {
            return TG_SQ218_PROOF_REJECTED;
        }
        while (position < row.prime) {
            if (position < TG_SQ218_LOG_SEED_AT) {
                lower = tg_sq218_log_seeds[position][0];
                upper = tg_sq218_log_seeds[position][1];
            } else {
                status = tg_log_ladder_next(
                    view, position, &lower, &upper);
                if (status != TG_SQ218_OK) {
                    return status;
                }
            }
            ++position;
        }
        if (row.log_lower != lower || row.log_upper != upper) {
            return TG_SQ218_PROOF_REJECTED;
        }
    }
    return TG_SQ218_OK;
}

static tg_sq218_status tg_reciprocals(
    const tg_sq218_view_v2 *view,
    uint64_t value,
    uint64_t root,
    uint64_t *lower,
    uint64_t *upper)
{
    uint64_t square;
    uint64_t remainder;
    uint64_t twice_root;
    uint64_t twice_square;
    uint64_t lower_num;
    uint64_t lower_den;
    uint64_t four_square;
    uint64_t upper_factor;
    uint64_t upper_num;
    uint64_t three_remainder;
    uint64_t upper_den_factor;
    uint64_t upper_den;
    uint64_t quotient;
    uint64_t residue;

    if (view == NULL || lower == NULL || upper == NULL || root == 0
        || !tg_u64_mul_checked(root, root, &square)
        || square > value) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    remainder = value - square;
    if (!tg_u64_mul_checked(2, root, &twice_root)
        || !tg_u64_mul_checked(2, square, &twice_square)
        || !tg_u64_mul_checked(
            view->header.reciprocal_scale, twice_root, &lower_num)
        || !tg_u64_add_checked(twice_square, remainder, &lower_den)
        || lower_den == 0
        || !tg_u64_mul_checked(4, square, &four_square)
        || !tg_u64_add_checked(four_square, remainder, &upper_factor)
        || !tg_u64_mul_checked(
            view->header.reciprocal_scale, upper_factor, &upper_num)
        || !tg_u64_mul_checked(3, remainder, &three_remainder)
        || !tg_u64_add_checked(
            four_square, three_remainder, &upper_den_factor)
        || !tg_u64_mul_checked(root, upper_den_factor, &upper_den)
        || upper_den == 0) {
        return TG_SQ218_OVERFLOW;
    }
    *lower = lower_num / lower_den;
    quotient = upper_num / upper_den;
    residue = upper_num % upper_den;
    if (residue != 0
        && !tg_u64_add_checked(quotient, 1, &quotient)) {
        return TG_SQ218_OVERFLOW;
    }
    *upper = quotient;
    return TG_SQ218_OK;
}

static tg_sq218_status tg_head_right(
    const tg_sq218_view_v2 *view,
    uint64_t root,
    tg_sq218_u128 *out)
{
    tg_sq218_u128 result = {0, root};
    if (!tg_sq218_u128_mul_u64_checked(
            result.hi,
            result.lo,
            2501,
            &result.hi,
            &result.lo)
        || !tg_sq218_u128_mul_u64_checked(
            result.hi,
            result.lo,
            view->header.log_scale,
            &result.hi,
            &result.lo)
        || !tg_sq218_u128_mul_u64_checked(
            result.hi,
            result.lo,
            view->header.reciprocal_scale,
            &result.hi,
            &result.lo)) {
        return TG_SQ218_OVERFLOW;
    }
    *out = result;
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_scan_step_v2(
    const tg_sq218_view_v2 *view,
    tg_sq218_scan_state_v2 *state)
{
    tg_sq218_event_v2 event;
    tg_sq218_prime_v2 prime;
    tg_sq218_u128 term;
    tg_sq218_u128 weighted;
    tg_sq218_u128 psi;
    tg_sq218_u128 left;
    tg_sq218_u128 right;
    uint64_t lower_reciprocal;
    uint64_t upper_reciprocal;
    uint64_t expected_power;
    tg_sq218_status status;

    if (view == NULL || state == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    if (state->next_event >= view->header.event_count) {
        return TG_SQ218_OUT_OF_RANGE;
    }
    status = tg_sq218_event_at_v2(view, state->next_event, &event);
    if (status != TG_SQ218_OK) {
        return status;
    }
    if (event.prime_index >= view->header.prime_count) {
        return TG_SQ218_PROOF_REJECTED;
    }
    status = tg_sq218_prime_at_v2(view, event.prime_index, &prime);
    if (status != TG_SQ218_OK) {
        return status;
    }
    if (event.value > view->header.bound
        || event.exponent == 0
        || !tg_floor_sqrt_ok(event.value, event.floor_sqrt)
        || !tg_pow_u64_checked(
            prime.prime, event.exponent, &expected_power)
        || expected_power != event.value
        || (state->next_event != 0
            && event.value <= state->last_event_value)) {
        return TG_SQ218_PROOF_REJECTED;
    }
    status = tg_reciprocals(
        view,
        event.value,
        event.floor_sqrt,
        &lower_reciprocal,
        &upper_reciprocal);
    if (status != TG_SQ218_OK) {
        return status;
    }
    term.hi = 0;
    term.lo = prime.log_upper;
    if (!tg_sq218_u128_mul_u64_checked(
            term.hi,
            term.lo,
            upper_reciprocal,
            &term.hi,
            &term.lo)
        || !tg_sq218_u128_add_checked(
            state->weighted_upper.hi,
            state->weighted_upper.lo,
            term.hi,
            term.lo,
            &weighted.hi,
            &weighted.lo)) {
        return TG_SQ218_OVERFLOW;
    }
    term.hi = 0;
    term.lo = prime.log_lower;
    if (!tg_sq218_u128_add_checked(
            state->psi_lower.hi,
            state->psi_lower.lo,
            term.hi,
            term.lo,
            &psi.hi,
            &psi.lo)
        || !tg_sq218_u128_mul_u64_checked(
            weighted.hi,
            weighted.lo,
            1250,
            &left.hi,
            &left.lo)) {
        return TG_SQ218_OVERFLOW;
    }
    status = tg_head_right(view, event.floor_sqrt, &right);
    if (status != TG_SQ218_OK) {
        return status;
    }
    if (tg_sq218_u128_compare(
            left.hi, left.lo, right.hi, right.lo) >= 0) {
        return TG_SQ218_PROOF_REJECTED;
    }
    state->next_event += 1;
    state->last_event_value = event.value;
    state->weighted_upper = weighted;
    state->psi_lower = psi;
    (void)lower_reciprocal;
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_scan_all_events_v2(
    const tg_sq218_view_v2 *view,
    tg_sq218_scan_state_v2 *out)
{
    tg_sq218_scan_state_v2 state;
    tg_sq218_status status;

    if (view == NULL || out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    tg_sq218_scan_initial_v2(&state);
    while (state.next_event < view->header.event_count) {
        status = tg_sq218_scan_step_v2(view, &state);
        if (status != TG_SQ218_OK) {
            return status;
        }
    }
    *out = state;
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_anchor_v2(
    const tg_sq218_view_v2 *view,
    const tg_sq218_scan_state_v2 *state,
    tg_sq218_u128 *slack)
{
    tg_sq218_u128 correction;
    tg_sq218_u128 difference;
    tg_sq218_u128 left;
    tg_sq218_u128 right;
    tg_sq218_u128 candidate;
    uint64_t root = 1;
    uint64_t lower_reciprocal;
    uint64_t upper_reciprocal;
    tg_sq218_status status;

    if (view == NULL || state == NULL || slack == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    while (root <= view->header.bound / root
           && root * root <= view->header.bound) {
        uint64_t next = root + 1;
        if (next > view->header.bound / next) {
            break;
        }
        root = next;
    }
    status = tg_reciprocals(
        view,
        view->header.bound,
        root,
        &lower_reciprocal,
        &upper_reciprocal);
    if (status != TG_SQ218_OK) {
        return status;
    }
    correction = state->psi_lower;
    if (!tg_sq218_u128_mul_u64_checked(
            correction.hi,
            correction.lo,
            lower_reciprocal,
            &correction.hi,
            &correction.lo)) {
        return TG_SQ218_OVERFLOW;
    }
    status = tg_head_right(view, root, &right);
    if (status != TG_SQ218_OK) {
        return status;
    }

    /*
     * The Lean contract uses Int for weighted - correction.  If it is
     * negative, the strict guard is automatic and the positive slack is
     * right + 2500 * (correction - weighted).
     */
    if (tg_sq218_u128_compare(
            state->weighted_upper.hi,
            state->weighted_upper.lo,
            correction.hi,
            correction.lo) < 0) {
        if (!tg_sq218_u128_sub_checked(
                correction.hi,
                correction.lo,
                state->weighted_upper.hi,
                state->weighted_upper.lo,
                &difference.hi,
                &difference.lo)
            || !tg_sq218_u128_mul_u64_checked(
                difference.hi,
                difference.lo,
                2500,
                &left.hi,
                &left.lo)
            || !tg_sq218_u128_add_checked(
                right.hi,
                right.lo,
                left.hi,
                left.lo,
                &candidate.hi,
                &candidate.lo)) {
            return TG_SQ218_OVERFLOW;
        }
        *slack = candidate;
        return TG_SQ218_OK;
    }
    if (!tg_sq218_u128_sub_checked(
            state->weighted_upper.hi,
            state->weighted_upper.lo,
            correction.hi,
            correction.lo,
            &difference.hi,
            &difference.lo)
        || !tg_sq218_u128_mul_u64_checked(
            difference.hi,
            difference.lo,
            2500,
            &left.hi,
            &left.lo)) {
        return TG_SQ218_OVERFLOW;
    }
    if (tg_sq218_u128_compare(
            left.hi, left.lo, right.hi, right.lo) >= 0
        || !tg_sq218_u128_sub_checked(
            right.hi,
            right.lo,
            left.hi,
            left.lo,
            &candidate.hi,
            &candidate.lo)) {
        return TG_SQ218_PROOF_REJECTED;
    }
    *slack = candidate;
    (void)upper_reciprocal;
    return TG_SQ218_OK;
}

static tg_sq218_status tg_sq218_validate_all_v2(
    const tg_sq218_view_v2 *view,
    tg_sq218_validation_result_v2 *out)
{
    tg_sq218_validation_result_v2 result;
    tg_sq218_status status;

    if (view == NULL || out == NULL) {
        return TG_SQ218_BAD_ARGUMENT;
    }
    if (view->header.bound != TG_SQ218_PRODUCTION_BOUND
        || view->header.reused_prime_bound
            != TG_SQ218_PRODUCTION_REUSED_BOUND
        || view->header.log_seed_at != TG_SQ218_LOG_SEED_AT
        || view->header.log_scale != TG_SQ218_LOG_SCALE
        || view->header.reciprocal_scale
            != TG_SQ218_RECIPROCAL_SCALE) {
        return TG_SQ218_BAD_FORMAT;
    }
    status = tg_sq218_validate_roster_v2(view);
    if (status != TG_SQ218_OK) {
        return status;
    }
    status = tg_sq218_validate_power_layout_v2(view);
    if (status != TG_SQ218_OK) {
        return status;
    }
    status = tg_sq218_validate_log_ladder_v2(view);
    if (status != TG_SQ218_OK) {
        return status;
    }
    status = tg_sq218_scan_all_events_v2(view, &result.state);
    if (status != TG_SQ218_OK) {
        return status;
    }
    status = tg_sq218_anchor_v2(
        view, &result.state, &result.anchor_slack);
    if (status != TG_SQ218_OK) {
        return status;
    }
    *out = result;
    return TG_SQ218_OK;
}

tg_sq218_status tg_sq218_validate_bytes_v2(
    const uint8_t *bytes,
    size_t length,
    tg_sq218_validation_result_v2 *out)
{
    tg_sq218_view_v2 view;
    tg_sq218_status status =
        tg_sq218_view_open_v2(bytes, length, &view);
    if (status != TG_SQ218_OK) {
        return status;
    }
    return tg_sq218_validate_all_v2(&view, out);
}

/* Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * See pt21_ladder_check.h and FORMAT.md.
 */

#include "pt21_ladder_check.h"

/* ------------------------------------------------------------------ */
/* SHA-256                                                             */
/* ------------------------------------------------------------------ */

static const uint32_t pt21_sha256_round_constants[64] = {
    UINT32_C(0x428a2f98), UINT32_C(0x71374491), UINT32_C(0xb5c0fbcf),
    UINT32_C(0xe9b5dba5), UINT32_C(0x3956c25b), UINT32_C(0x59f111f1),
    UINT32_C(0x923f82a4), UINT32_C(0xab1c5ed5), UINT32_C(0xd807aa98),
    UINT32_C(0x12835b01), UINT32_C(0x243185be), UINT32_C(0x550c7dc3),
    UINT32_C(0x72be5d74), UINT32_C(0x80deb1fe), UINT32_C(0x9bdc06a7),
    UINT32_C(0xc19bf174), UINT32_C(0xe49b69c1), UINT32_C(0xefbe4786),
    UINT32_C(0x0fc19dc6), UINT32_C(0x240ca1cc), UINT32_C(0x2de92c6f),
    UINT32_C(0x4a7484aa), UINT32_C(0x5cb0a9dc), UINT32_C(0x76f988da),
    UINT32_C(0x983e5152), UINT32_C(0xa831c66d), UINT32_C(0xb00327c8),
    UINT32_C(0xbf597fc7), UINT32_C(0xc6e00bf3), UINT32_C(0xd5a79147),
    UINT32_C(0x06ca6351), UINT32_C(0x14292967), UINT32_C(0x27b70a85),
    UINT32_C(0x2e1b2138), UINT32_C(0x4d2c6dfc), UINT32_C(0x53380d13),
    UINT32_C(0x650a7354), UINT32_C(0x766a0abb), UINT32_C(0x81c2c92e),
    UINT32_C(0x92722c85), UINT32_C(0xa2bfe8a1), UINT32_C(0xa81a664b),
    UINT32_C(0xc24b8b70), UINT32_C(0xc76c51a3), UINT32_C(0xd192e819),
    UINT32_C(0xd6990624), UINT32_C(0xf40e3585), UINT32_C(0x106aa070),
    UINT32_C(0x19a4c116), UINT32_C(0x1e376c08), UINT32_C(0x2748774c),
    UINT32_C(0x34b0bcb5), UINT32_C(0x391c0cb3), UINT32_C(0x4ed8aa4a),
    UINT32_C(0x5b9cca4f), UINT32_C(0x682e6ff3), UINT32_C(0x748f82ee),
    UINT32_C(0x78a5636f), UINT32_C(0x84c87814), UINT32_C(0x8cc70208),
    UINT32_C(0x90befffa), UINT32_C(0xa4506ceb), UINT32_C(0xbef9a3f7),
    UINT32_C(0xc67178f2)
};

static uint32_t pt21_rotate_right(uint32_t value, unsigned amount)
{
    return (value >> amount) | (value << (32U - amount));
}

static uint32_t pt21_read_be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
        | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static uint64_t pt21_read_be64(const uint8_t *p)
{
    uint64_t high = (uint64_t)pt21_read_be32(p);
    uint64_t low = (uint64_t)pt21_read_be32(p + 4);
    return (high << 32) | low;
}

static int64_t pt21_read_be_i64(const uint8_t *p)
{
    uint64_t raw = pt21_read_be64(p);
    /* Two's-complement reinterpretation without implementation-defined
     * conversion: subtract 2^64 when the sign bit is set. */
    if ((raw & UINT64_C(0x8000000000000000)) != UINT64_C(0)) {
        uint64_t magnitude = ~raw; /* == (2^64 - raw) - 1, fits in int64 */
        return -(int64_t)magnitude - 1;
    }
    return (int64_t)raw;
}

static void pt21_write_be64(uint8_t *p, uint64_t value)
{
    p[0] = (uint8_t)(value >> 56);
    p[1] = (uint8_t)(value >> 48);
    p[2] = (uint8_t)(value >> 40);
    p[3] = (uint8_t)(value >> 32);
    p[4] = (uint8_t)(value >> 24);
    p[5] = (uint8_t)(value >> 16);
    p[6] = (uint8_t)(value >> 8);
    p[7] = (uint8_t)value;
}

static void pt21_sha256_compress(uint32_t state[8], const uint8_t block[64])
{
    uint32_t words[64];
    uint32_t a, b, c, d, e, f, g, h;
    unsigned index;

    for (index = 0; index < 16U; ++index) {
        words[index] = pt21_read_be32(block + (size_t)index * 4U);
    }
    for (index = 16U; index < 64U; ++index) {
        uint32_t left = words[index - 15U];
        uint32_t right = words[index - 2U];
        uint32_t sigma0 = pt21_rotate_right(left, 7U)
            ^ pt21_rotate_right(left, 18U) ^ (left >> 3);
        uint32_t sigma1 = pt21_rotate_right(right, 17U)
            ^ pt21_rotate_right(right, 19U) ^ (right >> 10);
        words[index] = words[index - 16U] + sigma0
            + words[index - 7U] + sigma1;
    }

    a = state[0]; b = state[1]; c = state[2]; d = state[3];
    e = state[4]; f = state[5]; g = state[6]; h = state[7];
    for (index = 0; index < 64U; ++index) {
        uint32_t big1 = pt21_rotate_right(e, 6U)
            ^ pt21_rotate_right(e, 11U) ^ pt21_rotate_right(e, 25U);
        uint32_t choose = (e & f) ^ ((~e) & g);
        uint32_t t1 = h + big1 + choose
            + pt21_sha256_round_constants[index] + words[index];
        uint32_t big0 = pt21_rotate_right(a, 2U)
            ^ pt21_rotate_right(a, 13U) ^ pt21_rotate_right(a, 22U);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = big0 + majority;
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

static void pt21_sha256_init(uint32_t state[8])
{
    state[0] = UINT32_C(0x6a09e667);
    state[1] = UINT32_C(0xbb67ae85);
    state[2] = UINT32_C(0x3c6ef372);
    state[3] = UINT32_C(0xa54ff53a);
    state[4] = UINT32_C(0x510e527f);
    state[5] = UINT32_C(0x9b05688c);
    state[6] = UINT32_C(0x1f83d9ab);
    state[7] = UINT32_C(0x5be0cd19);
}

/* Absorb an exact multiple of 64 bytes. */
static void pt21_sha256_absorb(
    uint32_t state[8], const uint8_t *bytes, size_t blocks)
{
    size_t index;
    for (index = 0; index < blocks; ++index) {
        pt21_sha256_compress(state, bytes + index * 64U);
    }
}

/* Absorb an arbitrary tail and finalize. */
static void pt21_sha256_finalize(
    uint32_t state[8], const uint8_t *tail, size_t tail_length,
    uint64_t total_length, uint8_t digest[32])
{
    uint8_t final_blocks[128];
    size_t padded;
    size_t index;
    uint64_t bit_length = total_length * UINT64_C(8);

    for (index = 0; index < 128U; ++index) {
        final_blocks[index] = 0U;
    }
    for (index = 0; index < tail_length; ++index) {
        final_blocks[index] = tail[index];
    }
    final_blocks[tail_length] = UINT8_C(0x80);
    padded = (tail_length < 56U) ? 64U : 128U;
    pt21_write_be64(final_blocks + padded - 8U, bit_length);
    pt21_sha256_absorb(state, final_blocks, padded / 64U);
    for (index = 0; index < 8U; ++index) {
        digest[index * 4U] = (uint8_t)(state[index] >> 24);
        digest[index * 4U + 1U] = (uint8_t)(state[index] >> 16);
        digest[index * 4U + 2U] = (uint8_t)(state[index] >> 8);
        digest[index * 4U + 3U] = (uint8_t)state[index];
    }
}

/* ------------------------------------------------------------------ */
/* Bit and lattice helpers                                             */
/* ------------------------------------------------------------------ */

static const uint8_t pt21_popcount_table[256] = {
    0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4, 1,2,2,3,2,3,3,4,2,3,3,4,3,4,4,5,
    1,2,2,3,2,3,3,4,2,3,3,4,3,4,4,5, 2,3,3,4,3,4,4,5,3,4,4,5,4,5,5,6,
    1,2,2,3,2,3,3,4,2,3,3,4,3,4,4,5, 2,3,3,4,3,4,4,5,3,4,4,5,4,5,5,6,
    2,3,3,4,3,4,4,5,3,4,4,5,4,5,5,6, 3,4,4,5,4,5,5,6,4,5,5,6,5,6,6,7,
    1,2,2,3,2,3,3,4,2,3,3,4,3,4,4,5, 2,3,3,4,3,4,4,5,3,4,4,5,4,5,5,6,
    2,3,3,4,3,4,4,5,3,4,4,5,4,5,5,6, 3,4,4,5,4,5,5,6,4,5,5,6,5,6,6,7,
    2,3,3,4,3,4,4,5,3,4,4,5,4,5,5,6, 3,4,4,5,4,5,5,6,4,5,5,6,5,6,6,7,
    3,4,4,5,4,5,5,6,4,5,5,6,5,6,6,7, 4,5,5,6,5,6,6,7,5,6,6,7,6,7,7,8
};

static unsigned pt21_bit_at(const uint8_t *bitmap, unsigned index)
{
    unsigned byte = bitmap[index >> 3];
    return (byte >> (index & 7U)) & 1U;
}

/* Number of adjacent sample pairs with opposite sign, over `samples`
 * samples.  This is exactly the number of multiplicity-one source events. */
static uint32_t pt21_transition_count(const uint8_t *bitmap, unsigned samples)
{
    uint32_t total = 0;
    unsigned full_bytes = (samples - 1U) >> 3;
    unsigned index;
    unsigned tail_start;

    /* Byte-parallel body: within a byte, transitions are popcount(x ^ x>>1)
     * over the low seven bit positions; the eighth transition (to the next
     * byte's low bit) is added explicitly. */
    for (index = 0; index < full_bytes; ++index) {
        uint8_t current = bitmap[index];
        uint8_t next = bitmap[index + 1U];
        uint8_t inner = (uint8_t)((current ^ (uint8_t)(current >> 1)) & 0x7FU);
        total += (uint32_t)pt21_popcount_table[inner];
        if ((((uint32_t)current >> 7) & 1U) != ((uint32_t)next & 1U)) {
            total += 1U;
        }
    }
    tail_start = full_bytes << 3;
    for (index = tail_start; index + 1U < samples; ++index) {
        if (pt21_bit_at(bitmap, index) != pt21_bit_at(bitmap, index + 1U)) {
            total += 1U;
        }
    }
    return total;
}

/* Signed left weight of a flank stream: -sum over events of
 * multiplicity * leftStep, matching `turingGridLeftWeight`. */
static int64_t pt21_left_weight(const uint8_t *bitmap, unsigned samples)
{
    int64_t total = 0;
    unsigned index;
    for (index = 0; index + 1U < samples; ++index) {
        if (pt21_bit_at(bitmap, index) != pt21_bit_at(bitmap, index + 1U)) {
            total += (int64_t)index;
        }
    }
    return -total;
}

/* Signed right weight of a flank stream: sum over events of
 * multiplicity * (spanSteps - rightStep), matching
 * `turingGridRightWeight`. */
static int64_t pt21_right_weight(
    const uint8_t *bitmap, unsigned samples, unsigned span_steps)
{
    int64_t total = 0;
    unsigned index;
    for (index = 0; index + 1U < samples; ++index) {
        if (pt21_bit_at(bitmap, index) != pt21_bit_at(bitmap, index + 1U)) {
            total += (int64_t)(span_steps - (index + 1U));
        }
    }
    return total;
}

/* Floor and ceiling division by a strictly positive divisor. */
static int64_t pt21_floor_div(int64_t numerator, int64_t divisor)
{
    int64_t quotient = numerator / divisor;
    if ((numerator % divisor) != 0 && numerator < 0) {
        quotient -= 1;
    }
    return quotient;
}

static int64_t pt21_ceil_div(int64_t numerator, int64_t divisor)
{
    int64_t quotient = numerator / divisor;
    if ((numerator % divisor) != 0 && numerator > 0) {
        quotient += 1;
    }
    return quotient;
}

/* ------------------------------------------------------------------ */
/* Level-0 packet check                                                */
/* ------------------------------------------------------------------ */

static const uint8_t pt21_packet_magic[8] = {
    UINT8_C(0x50), UINT8_C(0x54), UINT8_C(0x32), UINT8_C(0x31),
    UINT8_C(0x4C), UINT8_C(0x30), UINT8_C(0x01), UINT8_C(0x00)
};

void pt21_ladder_start(
    pt21_ladder_state *state,
    uint64_t first_block,
    uint64_t first_count,
    uint32_t blocks_per_group,
    int commit_packets)
{
    state->next_block = first_block;
    state->running_count = first_count;
    state->group_first_block = first_block;
    state->group_first_count = first_count;
    state->group_blocks = 0;
    state->group_slots = 0;
    pt21_sha256_init(state->group_digest_state);
    state->group_digest_length = 0;
    pt21_sha256_init(state->root_state);
    state->root_length = 0;
    state->groups_emitted = 0;
    state->blocks_per_group = blocks_per_group;
    state->commit_packets = commit_packets;
}

/* Fold a 64-byte level-1 commitment block into the group digest.  The block
 * is (block, lowerCount, slots, upperCount, packetDigestPrefix32) so the
 * group digest commits both to the emitted summary and to the packet bytes
 * that produced it. */
static void pt21_fold_window(
    pt21_ladder_state *state,
    const pt21_window_summary *summary,
    const uint8_t packet_digest[32])
{
    uint8_t record[64];
    unsigned index;
    pt21_write_be64(record + 0, summary->block);
    pt21_write_be64(record + 8, summary->lower_count);
    pt21_write_be64(record + 16, summary->slots);
    pt21_write_be64(record + 24, summary->upper_count);
    for (index = 0; index < 32U; ++index) {
        record[32U + index] = packet_digest[index];
    }
    pt21_sha256_absorb(state->group_digest_state, record, 1U);
    state->group_digest_length += 64U;
}

static void pt21_emit_group(
    pt21_ladder_state *state, uint8_t *group_record)
{
    uint8_t digest[32];
    uint8_t record_digest[32];
    uint8_t root_input[64];
    uint8_t tail[1] = { 0U };
    unsigned index;
    uint32_t digest_state[8];
    uint32_t record_state[8];

    for (index = 0; index < 8U; ++index) {
        digest_state[index] = state->group_digest_state[index];
    }
    pt21_sha256_finalize(
        digest_state, tail, 0U, state->group_digest_length, digest);

    pt21_write_be64(group_record + 0, state->group_first_block);
    pt21_write_be64(group_record + 8, state->group_blocks);
    pt21_write_be64(group_record + 16, state->group_first_count);
    pt21_write_be64(group_record + 24, state->group_slots);
    pt21_write_be64(group_record + 32, state->running_count);
    for (index = 0; index < 32U; ++index) {
        group_record[40U + index] = digest[index];
    }
    pt21_write_be64(group_record + 72, state->groups_emitted);
    pt21_write_be64(group_record + 80, UINT64_C(0));

    /* Chain each emitted group record into the campaign root through a
     * canonical 64-byte block: the record's own digest plus its index and
     * range, so the root binds order as well as content. */
    pt21_sha256_init(record_state);
    pt21_sha256_absorb(record_state, group_record, 1U);
    pt21_sha256_finalize(
        record_state, group_record + 64,
        (size_t)PT21_GROUP_RECORD_BYTES - 64U,
        (uint64_t)PT21_GROUP_RECORD_BYTES, record_digest);
    for (index = 0; index < 32U; ++index) {
        root_input[index] = record_digest[index];
    }
    pt21_write_be64(root_input + 32, state->groups_emitted);
    pt21_write_be64(root_input + 40, state->group_first_block);
    pt21_write_be64(root_input + 48, state->group_blocks);
    pt21_write_be64(root_input + 56, state->group_slots);
    pt21_sha256_absorb(state->root_state, root_input, 1U);
    state->root_length += 64U;

    state->groups_emitted += 1;
    state->group_first_block = state->next_block;
    state->group_first_count = state->running_count;
    state->group_blocks = 0;
    state->group_slots = 0;
    pt21_sha256_init(state->group_digest_state);
    state->group_digest_length = 0;
}

int pt21_ladder_step(
    pt21_ladder_state *state,
    const uint8_t *packet,
    size_t packet_length,
    pt21_window_summary *summary,
    uint8_t *group_record,
    int *group_ready)
{
    const uint8_t *main_bitmap;
    const uint8_t *left_bitmap;
    const uint8_t *right_bitmap;
    uint8_t packet_digest[32];
    uint32_t packet_state[8];
    uint64_t block;
    uint64_t lower_count;
    uint64_t upper_count;
    uint64_t slots;
    uint32_t stationary_count;
    uint32_t transitions;
    uint32_t derived_slots;
    int64_t s_bound_lower_lo, s_bound_lower_hi;
    int64_t common_lower_lo, common_lower_hi;
    int64_t s_bound_upper_lo, s_bound_upper_hi;
    int64_t common_upper_lo, common_upper_hi;
    int64_t left_weight, right_weight;
    int64_t left_integral, right_integral;
    int64_t lower_numerator_lo, lower_numerator_hi;
    int64_t upper_numerator_lo, upper_numerator_hi;
    int64_t quotient_lower_lo, quotient_lower_hi;
    int64_t quotient_upper_lo, quotient_upper_hi;
    int64_t ceil_target, floor_target;
    unsigned index;
    unsigned previous_cell;

    *group_ready = 0;
    if (packet_length != (size_t)PT21_PACKET_BYTES) {
        return PT21_ERR_LENGTH;
    }
    for (index = 0; index < 8U; ++index) {
        if (packet[index] != pt21_packet_magic[index]) {
            return PT21_ERR_MAGIC;
        }
    }

    block = pt21_read_be64(packet + 8);
    lower_count = pt21_read_be64(packet + 16);
    upper_count = pt21_read_be64(packet + 24);
    slots = (uint64_t)pt21_read_be32(packet + 32);
    stationary_count = pt21_read_be32(packet + 36);

    if (block != state->next_block) {
        return PT21_ERR_BLOCK_INDEX;
    }
    if (lower_count != state->running_count) {
        return PT21_ERR_COUNT_CURSOR;
    }
    if (lower_count == UINT64_C(0)) {
        return PT21_ERR_GEOMETRY;
    }
    if (lower_count + slots != upper_count) {
        return PT21_ERR_SLOT_CLOSURE;
    }
    if (stationary_count > PT21_MAX_STATIONARY) {
        return PT21_ERR_STATIONARY;
    }

    main_bitmap = packet + PT21_PACKET_HEADER_BYTES;
    left_bitmap = main_bitmap + PT21_MAIN_BITMAP_BYTES;
    right_bitmap = left_bitmap + PT21_FLANK_BITMAP_BYTES;

    /* (1) Slot derivation: every multiplicity-one slot is a lattice sign
     * change, and every resolved stationary cell contributes two. */
    transitions = pt21_transition_count(main_bitmap, PT21_MAIN_SAMPLES);
    derived_slots = transitions + 2U * stationary_count;
    if ((uint64_t)derived_slots != slots) {
        return PT21_ERR_SLOT_DERIVATION;
    }

    /* (2) Stationary cells must be strictly increasing, inside the main
     * lattice, and must not sit on a sign change: a resolved double zero is
     * invisible to the lattice scan. */
    previous_cell = 0U;
    for (index = 0; index < stationary_count; ++index) {
        uint32_t cell = pt21_read_be32(packet + 40 + (size_t)index * 4U);
        if (cell >= PT21_MAIN_SPAN_STEPS) {
            return PT21_ERR_STATIONARY;
        }
        if (index > 0U && cell <= previous_cell) {
            return PT21_ERR_STATIONARY;
        }
        if (pt21_bit_at(main_bitmap, cell)
                != pt21_bit_at(main_bitmap, cell + 1U)) {
            return PT21_ERR_STATIONARY;
        }
        previous_cell = cell;
    }

    /* (2b) Packets must be canonical: bits past the last lattice sample
     * are padding and must be zero, so a producer cannot hide a second
     * encoding of the same block. */
    if ((main_bitmap[PT21_MAIN_BITMAP_BYTES - 1U] & 0xFEU) != 0U) {
        return PT21_ERR_GEOMETRY;
    }
    if ((left_bitmap[PT21_FLANK_BITMAP_BYTES - 1U] & 0xFEU) != 0U) {
        return PT21_ERR_GEOMETRY;
    }
    if ((right_bitmap[PT21_FLANK_BITMAP_BYTES - 1U] & 0xFEU) != 0U) {
        return PT21_ERR_GEOMETRY;
    }

    /* (3) The source parity sanity check. */
    {
        unsigned left_sign = pt21_bit_at(main_bitmap, 0U);
        unsigned right_sign =
            pt21_bit_at(main_bitmap, PT21_MAIN_SAMPLES - 1U);
        unsigned equal_signs = (left_sign == right_sign) ? 1U : 0U;
        unsigned even_slots = ((slots & UINT64_C(1)) == UINT64_C(0)) ? 1U : 0U;
        if (equal_signs != even_slots) {
            return PT21_ERR_PARITY;
        }
    }

    /* (4) Shared endpoints of the three streams must agree. */
    if (pt21_bit_at(left_bitmap, PT21_FLANK_SAMPLES - 1U)
            != pt21_bit_at(main_bitmap, 0U)) {
        return PT21_ERR_BOUNDARY_SIGN;
    }
    if (pt21_bit_at(main_bitmap, PT21_MAIN_SAMPLES - 1U)
            != pt21_bit_at(right_bitmap, 0U)) {
        return PT21_ERR_BOUNDARY_SIGN;
    }

    /* (5) Turing arithmetic.  The two flank weights are *derived* from the
     * flank bitmaps, so the producer cannot advertise a count that does not
     * follow from the signs it published. */
    s_bound_lower_lo = pt21_read_be_i64(packet + 72);
    s_bound_lower_hi = pt21_read_be_i64(packet + 80);
    common_lower_lo = pt21_read_be_i64(packet + 88);
    common_lower_hi = pt21_read_be_i64(packet + 96);
    s_bound_upper_lo = pt21_read_be_i64(packet + 104);
    s_bound_upper_hi = pt21_read_be_i64(packet + 112);
    common_upper_lo = pt21_read_be_i64(packet + 120);
    common_upper_hi = pt21_read_be_i64(packet + 128);

    if (s_bound_lower_lo > s_bound_lower_hi
            || common_lower_lo > common_lower_hi
            || s_bound_upper_lo > s_bound_upper_hi
            || common_upper_lo > common_upper_hi
            || s_bound_lower_lo < 0
            || s_bound_upper_lo < 0) {
        return PT21_ERR_INTERVAL;
    }

    left_weight = pt21_left_weight(left_bitmap, PT21_FLANK_SAMPLES);
    right_weight = pt21_right_weight(
        right_bitmap, PT21_FLANK_SAMPLES, PT21_FLANK_SPAN_STEPS);
    if (left_weight > 0 || right_weight < 0) {
        return PT21_ERR_INTERVAL;
    }

    /* leftIntegral = leftWeight * delta, at scale 2^10.  Because
     * 2^10 / 512 = 2, this is exactly leftWeight * 21 * 2. */
    left_integral = left_weight * (int64_t)(PT21_DELTA_NUMERATOR * 2);
    right_integral = right_weight * (int64_t)(PT21_DELTA_NUMERATOR * 2);

    lower_numerator_lo = -s_bound_lower_hi - left_integral + common_lower_lo;
    lower_numerator_hi = -s_bound_lower_lo - left_integral + common_lower_hi;
    upper_numerator_lo = s_bound_upper_lo - right_integral + common_upper_lo;
    upper_numerator_hi = s_bound_upper_hi - right_integral + common_upper_hi;

    quotient_lower_lo =
        pt21_floor_div(lower_numerator_lo, (int64_t)PT21_FLANK_WIDTH);
    quotient_lower_hi =
        pt21_ceil_div(lower_numerator_hi, (int64_t)PT21_FLANK_WIDTH);
    quotient_upper_lo =
        pt21_floor_div(upper_numerator_lo, (int64_t)PT21_FLANK_WIDTH);
    quotient_upper_hi =
        pt21_ceil_div(upper_numerator_hi, (int64_t)PT21_FLANK_WIDTH);

    if (upper_count > UINT64_C(9007199254740992)) {
        return PT21_ERR_OVERFLOW;
    }
    ceil_target = (int64_t)lower_count - 1;
    floor_target = (int64_t)upper_count - 1;

    /* ceil(q) = ceilTarget iff ceilTarget - 1 < q <= ceilTarget. */
    if (!((ceil_target - 1) * (int64_t)PT21_SCALE < quotient_lower_lo)) {
        return PT21_ERR_TURING_LOWER;
    }
    if (!(quotient_lower_hi <= ceil_target * (int64_t)PT21_SCALE)) {
        return PT21_ERR_TURING_LOWER;
    }
    /* floor(q) = floorTarget iff floorTarget <= q < floorTarget + 1. */
    if (!(floor_target * (int64_t)PT21_SCALE <= quotient_upper_lo)) {
        return PT21_ERR_TURING_UPPER;
    }
    if (!(quotient_upper_hi < (floor_target + 1) * (int64_t)PT21_SCALE)) {
        return PT21_ERR_TURING_UPPER;
    }

    /* (6) Commit to the packet and fold the level-1 summary. */
    for (index = 0; index < 32U; ++index) {
        packet_digest[index] = 0U;
    }
    if (state->commit_packets != 0) {
        pt21_sha256_init(packet_state);
        pt21_sha256_absorb(
            packet_state, packet, (size_t)PT21_PACKET_BYTES / 64U);
        pt21_sha256_finalize(
            packet_state,
            packet + ((size_t)PT21_PACKET_BYTES / 64U) * 64U,
            (size_t)PT21_PACKET_BYTES % 64U,
            (uint64_t)PT21_PACKET_BYTES,
            packet_digest);
    }

    summary->block = block;
    summary->lower_count = lower_count;
    summary->slots = slots;
    summary->upper_count = upper_count;

    pt21_fold_window(state, summary, packet_digest);
    state->next_block = block + 1;
    state->running_count = upper_count;
    state->group_blocks += 1;
    state->group_slots += slots;

    if (state->group_blocks == (uint64_t)state->blocks_per_group) {
        pt21_emit_group(state, group_record);
        *group_ready = 1;
    }
    return PT21_OK;
}

int pt21_ladder_finish(
    pt21_ladder_state *state,
    uint8_t *group_record,
    int *group_ready,
    uint8_t *root_digest)
{
    uint8_t tail[1] = { 0U };
    uint32_t root_state[8];
    unsigned index;

    *group_ready = 0;
    if (state->group_blocks > 0) {
        pt21_emit_group(state, group_record);
        *group_ready = 1;
    }
    for (index = 0; index < 8U; ++index) {
        root_state[index] = state->root_state[index];
    }
    pt21_sha256_finalize(root_state, tail, 0U, state->root_length, root_digest);
    return PT21_OK;
}

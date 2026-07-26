/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#include "sqrt218_launcher_sha256.h"

#include <string.h>

static const uint32_t tg_sha256_k[64] = {
    UINT32_C(0x428a2f98), UINT32_C(0x71374491),
    UINT32_C(0xb5c0fbcf), UINT32_C(0xe9b5dba5),
    UINT32_C(0x3956c25b), UINT32_C(0x59f111f1),
    UINT32_C(0x923f82a4), UINT32_C(0xab1c5ed5),
    UINT32_C(0xd807aa98), UINT32_C(0x12835b01),
    UINT32_C(0x243185be), UINT32_C(0x550c7dc3),
    UINT32_C(0x72be5d74), UINT32_C(0x80deb1fe),
    UINT32_C(0x9bdc06a7), UINT32_C(0xc19bf174),
    UINT32_C(0xe49b69c1), UINT32_C(0xefbe4786),
    UINT32_C(0x0fc19dc6), UINT32_C(0x240ca1cc),
    UINT32_C(0x2de92c6f), UINT32_C(0x4a7484aa),
    UINT32_C(0x5cb0a9dc), UINT32_C(0x76f988da),
    UINT32_C(0x983e5152), UINT32_C(0xa831c66d),
    UINT32_C(0xb00327c8), UINT32_C(0xbf597fc7),
    UINT32_C(0xc6e00bf3), UINT32_C(0xd5a79147),
    UINT32_C(0x06ca6351), UINT32_C(0x14292967),
    UINT32_C(0x27b70a85), UINT32_C(0x2e1b2138),
    UINT32_C(0x4d2c6dfc), UINT32_C(0x53380d13),
    UINT32_C(0x650a7354), UINT32_C(0x766a0abb),
    UINT32_C(0x81c2c92e), UINT32_C(0x92722c85),
    UINT32_C(0xa2bfe8a1), UINT32_C(0xa81a664b),
    UINT32_C(0xc24b8b70), UINT32_C(0xc76c51a3),
    UINT32_C(0xd192e819), UINT32_C(0xd6990624),
    UINT32_C(0xf40e3585), UINT32_C(0x106aa070),
    UINT32_C(0x19a4c116), UINT32_C(0x1e376c08),
    UINT32_C(0x2748774c), UINT32_C(0x34b0bcb5),
    UINT32_C(0x391c0cb3), UINT32_C(0x4ed8aa4a),
    UINT32_C(0x5b9cca4f), UINT32_C(0x682e6ff3),
    UINT32_C(0x748f82ee), UINT32_C(0x78a5636f),
    UINT32_C(0x84c87814), UINT32_C(0x8cc70208),
    UINT32_C(0x90befffa), UINT32_C(0xa4506ceb),
    UINT32_C(0xbef9a3f7), UINT32_C(0xc67178f2)
};

static uint32_t tg_rotr32(uint32_t value, unsigned int distance)
{
    return (value >> distance) | (value << (32U - distance));
}

static uint32_t tg_load_be32(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0] << 24)
        | ((uint32_t)bytes[1] << 16)
        | ((uint32_t)bytes[2] << 8)
        | (uint32_t)bytes[3];
}

static void tg_store_be32(uint8_t *bytes, uint32_t value)
{
    bytes[0] = (uint8_t)(value >> 24);
    bytes[1] = (uint8_t)(value >> 16);
    bytes[2] = (uint8_t)(value >> 8);
    bytes[3] = (uint8_t)value;
}

static void tg_store_be64(uint8_t *bytes, uint64_t value)
{
    unsigned int index;

    for (index = 0; index < 8U; ++index) {
        bytes[index] =
            (uint8_t)(value >> (56U - (8U * index)));
    }
}

static void tg_sha256_compress(
    tg_sq218_sha256_context *context,
    const uint8_t block[64])
{
    uint32_t words[64];
    uint32_t a;
    uint32_t b;
    uint32_t c;
    uint32_t d;
    uint32_t e;
    uint32_t f;
    uint32_t g;
    uint32_t h;
    unsigned int index;

    for (index = 0; index < 16U; ++index) {
        words[index] = tg_load_be32(block + (4U * index));
    }
    for (index = 16U; index < 64U; ++index) {
        uint32_t left = words[index - 15U];
        uint32_t right = words[index - 2U];
        uint32_t sigma0 =
            tg_rotr32(left, 7U) ^ tg_rotr32(left, 18U) ^ (left >> 3);
        uint32_t sigma1 =
            tg_rotr32(right, 17U) ^ tg_rotr32(right, 19U) ^ (right >> 10);
        words[index] =
            words[index - 16U] + sigma0 + words[index - 7U] + sigma1;
    }

    a = context->state[0];
    b = context->state[1];
    c = context->state[2];
    d = context->state[3];
    e = context->state[4];
    f = context->state[5];
    g = context->state[6];
    h = context->state[7];
    for (index = 0; index < 64U; ++index) {
        uint32_t big_sigma1 =
            tg_rotr32(e, 6U) ^ tg_rotr32(e, 11U) ^ tg_rotr32(e, 25U);
        uint32_t choose = (e & f) ^ ((~e) & g);
        uint32_t first =
            h + big_sigma1 + choose + tg_sha256_k[index] + words[index];
        uint32_t big_sigma0 =
            tg_rotr32(a, 2U) ^ tg_rotr32(a, 13U) ^ tg_rotr32(a, 22U);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t second = big_sigma0 + majority;

        h = g;
        g = f;
        f = e;
        e = d + first;
        d = c;
        c = b;
        b = a;
        a = first + second;
    }
    context->state[0] += a;
    context->state[1] += b;
    context->state[2] += c;
    context->state[3] += d;
    context->state[4] += e;
    context->state[5] += f;
    context->state[6] += g;
    context->state[7] += h;
}

void tg_sq218_sha256_init(tg_sq218_sha256_context *context)
{
    static const uint32_t initial[8] = {
        UINT32_C(0x6a09e667), UINT32_C(0xbb67ae85),
        UINT32_C(0x3c6ef372), UINT32_C(0xa54ff53a),
        UINT32_C(0x510e527f), UINT32_C(0x9b05688c),
        UINT32_C(0x1f83d9ab), UINT32_C(0x5be0cd19)
    };

    memcpy(context->state, initial, sizeof(initial));
    context->total_bytes = 0;
    context->block_used = 0;
    memset(context->block, 0, sizeof(context->block));
}

void tg_sq218_sha256_update(
    tg_sq218_sha256_context *context,
    const uint8_t *bytes,
    size_t length)
{
    size_t consumed = 0;

    while (consumed < length) {
        size_t available = sizeof(context->block) - context->block_used;
        size_t remaining = length - consumed;
        size_t take = remaining < available ? remaining : available;

        memcpy(
            context->block + context->block_used,
            bytes + consumed,
            take);
        context->block_used += take;
        context->total_bytes += (uint64_t)take;
        consumed += take;
        if (context->block_used == sizeof(context->block)) {
            tg_sha256_compress(context, context->block);
            context->block_used = 0;
        }
    }
}

void tg_sq218_sha256_final(
    tg_sq218_sha256_context *context,
    uint8_t digest[32])
{
    uint64_t total_bits = context->total_bytes * UINT64_C(8);
    size_t index;

    context->block[context->block_used++] = UINT8_C(0x80);
    if (context->block_used > 56U) {
        memset(
            context->block + context->block_used,
            0,
            sizeof(context->block) - context->block_used);
        tg_sha256_compress(context, context->block);
        context->block_used = 0;
    }
    memset(context->block + context->block_used, 0, 56U - context->block_used);
    tg_store_be64(context->block + 56U, total_bits);
    tg_sha256_compress(context, context->block);
    for (index = 0; index < 8U; ++index) {
        tg_store_be32(digest + (4U * index), context->state[index]);
    }
    memset(context, 0, sizeof(*context));
}

void tg_sq218_sha256(
    const uint8_t *bytes,
    size_t length,
    uint8_t digest[32])
{
    tg_sq218_sha256_context context;

    tg_sq218_sha256_init(&context);
    tg_sq218_sha256_update(&context, bytes, length);
    tg_sq218_sha256_final(&context, digest);
}

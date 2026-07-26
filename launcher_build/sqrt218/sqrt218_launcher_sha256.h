/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#ifndef SPARKINTERVAL_SQRT218_LAUNCHER_SHA256_H
#define SPARKINTERVAL_SQRT218_LAUNCHER_SHA256_H

#include <stddef.h>
#include <stdint.h>

typedef struct tg_sq218_sha256_context {
    uint32_t state[8];
    uint64_t total_bytes;
    uint8_t block[64];
    size_t block_used;
} tg_sq218_sha256_context;

void tg_sq218_sha256_init(tg_sq218_sha256_context *context);
void tg_sq218_sha256_update(
    tg_sq218_sha256_context *context,
    const uint8_t *bytes,
    size_t length);
void tg_sq218_sha256_final(
    tg_sq218_sha256_context *context,
    uint8_t digest[32]);
void tg_sq218_sha256(
    const uint8_t *bytes,
    size_t length,
    uint8_t digest[32]);

#endif

/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 200809L

#include "sqrt218_cpu_command.h"

#ifndef TG_SQ218_PURE_ENTRY_ONLY
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef O_CLOEXEC
#error "sqrt218 production command requires O_CLOEXEC"
#endif

#ifndef O_NOFOLLOW
#error "sqrt218 production command requires O_NOFOLLOW"
#endif
#endif

static const uint8_t tg_sq218_result_magic_v2[8] = {
    UINT8_C(0x53), UINT8_C(0x51), UINT8_C(0x32), UINT8_C(0x31),
    UINT8_C(0x38), UINT8_C(0x52), UINT8_C(0x32), UINT8_C(0x00)
};

static const uint32_t tg_sha256_round_constants[64] = {
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

static void tg_result_put_be16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)(value >> 8);
    p[1] = (uint8_t)value;
}

static void tg_result_put_be32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

static void tg_result_put_be64(uint8_t *p, uint64_t value)
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

static uint32_t tg_sha256_read_be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24)
        | ((uint32_t)p[1] << 16)
        | ((uint32_t)p[2] << 8)
        | (uint32_t)p[3];
}

static uint32_t tg_sha256_rotate_right(uint32_t value, unsigned amount)
{
    return (value >> amount) | (value << (32U - amount));
}

static void tg_sha256_compress(uint32_t state[8], const uint8_t block[64])
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
    unsigned index;

    for (index = 0; index < 16U; ++index) {
        words[index] =
            tg_sha256_read_be32(block + (size_t)index * 4U);
    }
    for (index = 16U; index < 64U; ++index) {
        uint32_t left = words[index - 15U];
        uint32_t right = words[index - 2U];
        uint32_t small_sigma0 =
            tg_sha256_rotate_right(left, 7U)
            ^ tg_sha256_rotate_right(left, 18U)
            ^ (left >> 3);
        uint32_t small_sigma1 =
            tg_sha256_rotate_right(right, 17U)
            ^ tg_sha256_rotate_right(right, 19U)
            ^ (right >> 10);
        words[index] =
            words[index - 16U] + small_sigma0
            + words[index - 7U] + small_sigma1;
    }

    a = state[0];
    b = state[1];
    c = state[2];
    d = state[3];
    e = state[4];
    f = state[5];
    g = state[6];
    h = state[7];
    for (index = 0; index < 64U; ++index) {
        uint32_t big_sigma1 =
            tg_sha256_rotate_right(e, 6U)
            ^ tg_sha256_rotate_right(e, 11U)
            ^ tg_sha256_rotate_right(e, 25U);
        uint32_t choose = (e & f) ^ ((~e) & g);
        uint32_t temporary1 =
            h + big_sigma1 + choose
            + tg_sha256_round_constants[index] + words[index];
        uint32_t big_sigma0 =
            tg_sha256_rotate_right(a, 2U)
            ^ tg_sha256_rotate_right(a, 13U)
            ^ tg_sha256_rotate_right(a, 22U);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temporary2 = big_sigma0 + majority;

        h = g;
        g = f;
        f = e;
        e = d + temporary1;
        d = c;
        c = b;
        b = a;
        a = temporary1 + temporary2;
    }
    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

static void tg_sha256(
    const uint8_t *bytes,
    size_t length,
    uint8_t digest[32])
{
    uint32_t state[8] = {
        UINT32_C(0x6a09e667), UINT32_C(0xbb67ae85),
        UINT32_C(0x3c6ef372), UINT32_C(0xa54ff53a),
        UINT32_C(0x510e527f), UINT32_C(0x9b05688c),
        UINT32_C(0x1f83d9ab), UINT32_C(0x5be0cd19)
    };
    uint8_t final_blocks[128] = {0};
    size_t offset = 0;
    size_t remaining;
    size_t padded_length;
    uint64_t bit_length = (uint64_t)length * UINT64_C(8);
    unsigned index;

    while (length - offset >= 64U) {
        tg_sha256_compress(state, bytes + offset);
        offset += 64U;
    }
    remaining = length - offset;
    if (remaining != 0) {
        size_t copy_index;
        for (copy_index = 0; copy_index < remaining; ++copy_index) {
            final_blocks[copy_index] = bytes[offset + copy_index];
        }
    }
    final_blocks[remaining] = UINT8_C(0x80);
    padded_length = remaining < 56U ? 64U : 128U;
    tg_result_put_be64(
        final_blocks + padded_length - 8U, bit_length);
    tg_sha256_compress(state, final_blocks);
    if (padded_length == 128U) {
        tg_sha256_compress(state, final_blocks + 64);
    }
    for (index = 0; index < 8U; ++index) {
        tg_result_put_be32(digest + (size_t)index * 4U, state[index]);
    }
}

static int tg_pointer_ranges_overlap(
    const void *left,
    size_t left_length,
    const void *right,
    size_t right_length)
{
    uintptr_t left_start = (uintptr_t)left;
    uintptr_t right_start = (uintptr_t)right;
    uintptr_t left_width = (uintptr_t)left_length;
    uintptr_t right_width = (uintptr_t)right_length;
    uintptr_t left_end;
    uintptr_t right_end;

    if ((size_t)left_width != left_length
        || (size_t)right_width != right_length
        || UINTPTR_MAX - left_start < left_width
        || UINTPTR_MAX - right_start < right_width) {
        return 1;
    }
    left_end = left_start + left_width;
    right_end = right_start + right_width;
    return left_start < right_end && right_start < left_end;
}

static void tg_sq218_encode_result_v2(
    tg_sq218_status status,
    uint64_t input_bytes,
    const tg_sq218_validation_result_v2 *result,
    const uint8_t snapshot_sha256[32],
    uint8_t *record)
{
    uint64_t i;

    for (i = 0; i < TG_SQ218_RESULT_V2_BYTES; ++i) {
        record[i] = 0;
    }
    for (i = 0; i < (uint64_t)sizeof(tg_sq218_result_magic_v2); ++i) {
        record[i] = tg_sq218_result_magic_v2[i];
    }
    tg_result_put_be16(record + 8, TG_SQ218_RESULT_V2_VERSION);
    tg_result_put_be16(
        record + 10, (uint16_t)TG_SQ218_RESULT_V2_BYTES);
    tg_result_put_be32(record + 12, (uint32_t)status);
    tg_result_put_be64(record + 16, input_bytes);
    if (status == TG_SQ218_OK && result != NULL) {
        tg_result_put_be64(record + 24, result->state.next_event);
        tg_result_put_be64(record + 32, result->state.last_event_value);
        tg_result_put_be64(record + 40, result->state.weighted_upper.hi);
        tg_result_put_be64(record + 48, result->state.weighted_upper.lo);
        tg_result_put_be64(record + 56, result->state.psi_lower.hi);
        tg_result_put_be64(record + 64, result->state.psi_lower.lo);
        tg_result_put_be64(record + 72, result->anchor_slack.hi);
        tg_result_put_be64(record + 80, result->anchor_slack.lo);
    }
    for (i = 0; i < UINT64_C(32); ++i) {
        record[UINT64_C(88) + i] = snapshot_sha256[i];
    }
}

int tg_sq218_validate_snapshot_to_record_v2(
    const uint8_t *snapshot,
    size_t length,
    uint8_t *record,
    tg_sq218_status *checker_status)
{
    tg_sq218_validation_result_v2 result = {
        {0, 0, {0, 0}, {0, 0}},
        {0, 0}
    };
    tg_sq218_status status;
    uint8_t snapshot_sha256[32];
    uint64_t input_bytes;
    int status_alias;

    if (snapshot == NULL || record == NULL || checker_status == NULL) {
        return 0;
    }
    status_alias =
        tg_pointer_ranges_overlap(
            snapshot,
            length,
            checker_status,
            sizeof(*checker_status))
        || tg_pointer_ranges_overlap(
            record,
            (size_t)TG_SQ218_RESULT_V2_BYTES,
            checker_status,
            sizeof(*checker_status));
    if (tg_pointer_ranges_overlap(
            snapshot,
            length,
            record,
            (size_t)TG_SQ218_RESULT_V2_BYTES)
        || status_alias) {
        if (!status_alias) {
            *checker_status = TG_SQ218_BAD_ARGUMENT;
        }
        return 0;
    }
    input_bytes = (uint64_t)length;
    if ((size_t)input_bytes != length
        || input_bytes > UINT64_MAX / UINT64_C(8)) {
        *checker_status = TG_SQ218_BAD_ARGUMENT;
        return 0;
    }

    tg_sha256(snapshot, length, snapshot_sha256);
    status = tg_sq218_validate_bytes_v2(snapshot, length, &result);
    tg_sq218_encode_result_v2(
        status, input_bytes, &result, snapshot_sha256, record);
    *checker_status = status;
    return 1;
}

int tg_sq218_verify_snapshot_v2(
    const uint8_t *snapshot,
    uint64_t length,
    uint8_t *record,
    uint32_t *status_out)
{
    size_t native_length;
    tg_sq218_status status = TG_SQ218_BAD_ARGUMENT;
    int encoded;

    if (snapshot == NULL || record == NULL || status_out == NULL) {
        return 0;
    }
    native_length = (size_t)length;
    if ((uint64_t)native_length != length) {
        *status_out = (uint32_t)TG_SQ218_BAD_ARGUMENT;
        return 0;
    }
    if (tg_pointer_ranges_overlap(
            snapshot, native_length, status_out, sizeof(*status_out))
        || tg_pointer_ranges_overlap(
            record,
            (size_t)TG_SQ218_RESULT_V2_BYTES,
            status_out,
            sizeof(*status_out))) {
        return 0;
    }
    encoded = tg_sq218_validate_snapshot_to_record_v2(
        snapshot, native_length, record, &status);
    *status_out = (uint32_t)status;
    return encoded;
}

#ifndef TG_SQ218_PURE_ENTRY_ONLY
static int tg_read_exact_snapshot(
    const char *path,
    uint8_t **owned_bytes,
    size_t *length)
{
    struct stat metadata;
    uint8_t *bytes;
    size_t expected;
    size_t used = 0;
    uint8_t extra;
    int fd;

    if (path == NULL || owned_bytes == NULL || length == NULL) {
        return 0;
    }
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        return 0;
    }
    if (fstat(fd, &metadata) != 0
        || !S_ISREG(metadata.st_mode)
        || metadata.st_size < 0
        || (uintmax_t)metadata.st_size > (uintmax_t)SIZE_MAX) {
        (void)close(fd);
        return 0;
    }
    expected = (size_t)metadata.st_size;
    bytes = (uint8_t *)malloc(expected == 0 ? 1 : expected);
    if (bytes == NULL) {
        (void)close(fd);
        return 0;
    }

    while (used < expected) {
        size_t remaining = expected - used;
        size_t request =
            remaining > (size_t)INT_MAX ? (size_t)INT_MAX : remaining;
        ssize_t received = read(fd, bytes + used, request);
        if (received < 0) {
            if (errno == EINTR) {
                continue;
            }
            free(bytes);
            (void)close(fd);
            return 0;
        }
        if (received == 0) {
            free(bytes);
            (void)close(fd);
            return 0;
        }
        used += (size_t)received;
    }
    for (;;) {
        ssize_t received = read(fd, &extra, 1);
        if (received < 0 && errno == EINTR) {
            continue;
        }
        if (received != 0) {
            free(bytes);
            (void)close(fd);
            return 0;
        }
        break;
    }
    if (close(fd) != 0) {
        free(bytes);
        return 0;
    }
    *owned_bytes = bytes;
    *length = expected;
    return 1;
}

typedef enum tg_result_write_status {
    TG_RESULT_WRITE_OK = 0,
    TG_RESULT_WRITE_CREATE_FAILED = 1,
    TG_RESULT_WRITE_FAILED = 2
} tg_result_write_status;

static tg_result_write_status tg_write_new_result(
    const char *path,
    const uint8_t *record)
{
    size_t written = 0;
    int close_status;
    int fd;

    if (path == NULL || record == NULL) {
        return TG_RESULT_WRITE_CREATE_FAILED;
    }
    fd = open(
        path,
        O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
        S_IRUSR | S_IWUSR);
    if (fd < 0) {
        return TG_RESULT_WRITE_CREATE_FAILED;
    }
    while (written < (size_t)TG_SQ218_RESULT_V2_BYTES) {
        size_t remaining =
            (size_t)TG_SQ218_RESULT_V2_BYTES - written;
        ssize_t count = write(fd, record + written, remaining);
        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            (void)close(fd);
            (void)unlink(path);
            return TG_RESULT_WRITE_FAILED;
        }
        if (count == 0) {
            (void)close(fd);
            (void)unlink(path);
            return TG_RESULT_WRITE_FAILED;
        }
        written += (size_t)count;
    }
    if (fsync(fd) != 0) {
        (void)close(fd);
        (void)unlink(path);
        return TG_RESULT_WRITE_FAILED;
    }
    close_status = close(fd);
    if (close_status != 0) {
        (void)unlink(path);
        return TG_RESULT_WRITE_FAILED;
    }
    return TG_RESULT_WRITE_OK;
}

tg_sq218_command_exit tg_sq218_run_files_v2(
    const char *input_path,
    const char *output_path,
    tg_sq218_status *checker_status)
{
    uint8_t *owned_bytes = NULL;
    size_t length = 0;
    uint8_t record[TG_SQ218_RESULT_V2_BYTES];
    tg_sq218_status status = TG_SQ218_BAD_ARGUMENT;
    tg_result_write_status write_status;
    int encoded;

    if (input_path == NULL || output_path == NULL
        || checker_status == NULL) {
        return TG_SQ218_COMMAND_USAGE_ERROR;
    }
    if (!tg_read_exact_snapshot(input_path, &owned_bytes, &length)) {
        *checker_status = TG_SQ218_BAD_ARGUMENT;
        return TG_SQ218_COMMAND_INPUT_ERROR;
    }

    /*
     * No pointer to the owned allocation escapes.  From this point until
     * validation returns it is accessed only through this const snapshot.
     */
    {
        const uint8_t *const snapshot = owned_bytes;
        encoded = tg_sq218_validate_snapshot_to_record_v2(
            snapshot, length, record, &status);
    }
    free(owned_bytes);
    owned_bytes = NULL;
    *checker_status = status;
    if (!encoded) {
        return TG_SQ218_COMMAND_INPUT_ERROR;
    }
    write_status = tg_write_new_result(output_path, record);
    if (write_status == TG_RESULT_WRITE_CREATE_FAILED) {
        return TG_SQ218_COMMAND_OUTPUT_CREATE_ERROR;
    }
    if (write_status != TG_RESULT_WRITE_OK) {
        return TG_SQ218_COMMAND_OUTPUT_WRITE_ERROR;
    }
    if (status == TG_SQ218_OK) {
        return TG_SQ218_COMMAND_ACCEPTED;
    }
    return TG_SQ218_COMMAND_REJECTED;
}
#endif

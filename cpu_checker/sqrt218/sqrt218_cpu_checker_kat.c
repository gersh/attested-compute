/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 200809L

#include "sqrt218_cpu_checker.h"
#include "sqrt218_cpu_command.h"

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define KAT_PRIME_COUNT UINT64_C(3)
#define KAT_FACTOR_COUNT UINT64_C(3)
#define KAT_GAP_COUNT UINT64_C(1)
#define KAT_EVENT_COUNT UINT64_C(4)
#define KAT_POWER_REF_COUNT UINT64_C(4)

#define KAT_PRIMES_OFFSET TG_SQ218_V2_HEADER_BYTES
#define KAT_FACTORS_OFFSET \
    (KAT_PRIMES_OFFSET + KAT_PRIME_COUNT * TG_SQ218_V2_PRIME_BYTES)
#define KAT_GAPS_OFFSET \
    (KAT_FACTORS_OFFSET \
        + KAT_FACTOR_COUNT * TG_SQ218_V2_FACTOR_REF_BYTES)
#define KAT_EVENTS_OFFSET \
    (KAT_GAPS_OFFSET + KAT_GAP_COUNT * TG_SQ218_V2_FACTOR_PAIR_BYTES)
#define KAT_POWER_REFS_OFFSET \
    (KAT_EVENTS_OFFSET + KAT_EVENT_COUNT * TG_SQ218_V2_EVENT_BYTES)
#define KAT_BYTES \
    (KAT_POWER_REFS_OFFSET \
        + KAT_POWER_REF_COUNT * TG_SQ218_V2_POWER_REF_BYTES)

#define LOG_KAT_PRIME_COUNT UINT64_C(11)
#define LOG_KAT_PRIMES_OFFSET TG_SQ218_V2_HEADER_BYTES
#define LOG_KAT_END \
    (LOG_KAT_PRIMES_OFFSET \
        + LOG_KAT_PRIME_COUNT * TG_SQ218_V2_PRIME_BYTES)
#define LOG_KAT_BYTES LOG_KAT_END

static int failures = 0;

static void expect(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        ++failures;
    }
}

static void put_be16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)(value >> 8);
    p[1] = (uint8_t)value;
}

static void put_be32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

static void put_be64(uint8_t *p, uint64_t value)
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

static uint16_t get_be16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | (uint16_t)p[1]);
}

static uint32_t get_be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24)
        | ((uint32_t)p[1] << 16)
        | ((uint32_t)p[2] << 8)
        | (uint32_t)p[3];
}

static uint64_t get_be64(const uint8_t *p)
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

static void put_prime_record(
    uint8_t *p,
    uint64_t prime,
    uint64_t witness,
    uint64_t factor_index,
    uint32_t factor_count,
    uint64_t gap_index,
    uint32_t gap_count,
    uint64_t power_ref_index,
    uint32_t power_ref_count,
    uint64_t log_lower,
    uint64_t log_upper)
{
    put_be64(p, prime);
    put_be64(p + 8, witness);
    put_be64(p + 16, factor_index);
    put_be32(p + 24, factor_count);
    put_be32(p + 28, gap_count);
    put_be64(p + 32, gap_index);
    put_be64(p + 40, power_ref_index);
    put_be32(p + 48, power_ref_count);
    put_be32(p + 52, 0);
    put_be64(p + 56, log_lower);
    put_be64(p + 64, log_upper);
    put_be64(p + 72, 0);
}

static void put_prime(
    uint8_t *bytes,
    uint64_t index,
    uint64_t prime,
    uint64_t witness,
    uint64_t factor_index,
    uint32_t factor_count,
    uint64_t gap_index,
    uint32_t gap_count,
    uint64_t power_ref_index,
    uint32_t power_ref_count,
    uint64_t log_lower,
    uint64_t log_upper)
{
    put_prime_record(
        bytes + KAT_PRIMES_OFFSET
            + index * TG_SQ218_V2_PRIME_BYTES,
        prime,
        witness,
        factor_index,
        factor_count,
        gap_index,
        gap_count,
        power_ref_index,
        power_ref_count,
        log_lower,
        log_upper);
}

static void put_event(
    uint8_t *bytes,
    uint64_t index,
    uint64_t value,
    uint64_t prime_index,
    uint32_t exponent,
    uint64_t floor_sqrt)
{
    uint8_t *p =
        bytes + KAT_EVENTS_OFFSET
            + index * TG_SQ218_V2_EVENT_BYTES;
    put_be64(p, value);
    put_be64(p + 8, prime_index);
    put_be32(p + 16, exponent);
    put_be32(p + 20, 0);
    put_be64(p + 24, floor_sqrt);
}

static void make_kat(uint8_t *bytes)
{
    static const uint8_t magic[8] = {
        0x53, 0x51, 0x32, 0x31, 0x38, 0x56, 0x32, 0x00
    };

    memset(bytes, 0, (size_t)KAT_BYTES);
    memcpy(bytes, magic, sizeof(magic));
    put_be16(bytes + 8, TG_SQ218_V2_VERSION);
    put_be16(bytes + 10, (uint16_t)TG_SQ218_V2_HEADER_BYTES);
    put_be32(bytes + 12, 0);
    put_be64(bytes + 16, 5);
    put_be64(bytes + 24, 5);
    put_be64(bytes + 32, TG_SQ218_LOG_SEED_AT);
    put_be64(bytes + 40, TG_SQ218_LOG_SCALE);
    put_be64(bytes + 48, TG_SQ218_RECIPROCAL_SCALE);
    put_be64(bytes + 56, KAT_PRIME_COUNT);
    put_be64(bytes + 64, KAT_FACTOR_COUNT);
    put_be64(bytes + 72, KAT_GAP_COUNT);
    put_be64(bytes + 80, KAT_EVENT_COUNT);
    put_be64(bytes + 88, KAT_POWER_REF_COUNT);
    put_be64(bytes + 96, KAT_PRIMES_OFFSET);
    put_be64(bytes + 104, KAT_FACTORS_OFFSET);
    put_be64(bytes + 112, KAT_GAPS_OFFSET);
    put_be64(bytes + 120, KAT_EVENTS_OFFSET);
    put_be64(bytes + 128, KAT_POWER_REFS_OFFSET);
    put_be64(bytes + 136, KAT_BYTES);
    put_be64(bytes + 144, 0);
    put_be64(bytes + 152, 0);

    put_prime(
        bytes, 0, 2, 0, 0, 0, 0, 0, 0, 2,
        UINT64_C(195103586431999), UINT64_C(195103586572737));
    put_prime(
        bytes, 1, 3, 2, 0, 1, 0, 0, 2, 1,
        UINT64_C(309231868028532), UINT64_C(309231868693940));
    put_prime(
        bytes, 2, 5, 2, 1, 2, 0, 1, 3, 1,
        UINT64_C(453016498773239), UINT64_C(453016499054997));

    put_be64(bytes + KAT_FACTORS_OFFSET, 0);
    put_be64(bytes + KAT_FACTORS_OFFSET + 8, 0);
    put_be64(bytes + KAT_FACTORS_OFFSET + 16, 0);

    put_be64(bytes + KAT_GAPS_OFFSET, 2);
    put_be64(bytes + KAT_GAPS_OFFSET + 8, 2);

    put_event(bytes, 0, 2, 0, 1, 1);
    put_event(bytes, 1, 3, 1, 1, 1);
    put_event(bytes, 2, 4, 0, 2, 2);
    put_event(bytes, 3, 5, 2, 1, 2);

    put_be64(bytes + KAT_POWER_REFS_OFFSET, 0);
    put_be64(bytes + KAT_POWER_REFS_OFFSET + 8, 2);
    put_be64(bytes + KAT_POWER_REFS_OFFSET + 16, 1);
    put_be64(bytes + KAT_POWER_REFS_OFFSET + 24, 3);
}

static void make_log_recurrence_kat(uint8_t *bytes)
{
    static const uint8_t magic[8] = {
        0x53, 0x51, 0x32, 0x31, 0x38, 0x56, 0x32, 0x00
    };
    static const uint64_t rows[LOG_KAT_PRIME_COUNT][3] = {
        {2, UINT64_C(195103586431999), UINT64_C(195103586572737)},
        {3, UINT64_C(309231868028532), UINT64_C(309231868693940)},
        {5, UINT64_C(453016498773239), UINT64_C(453016499054997)},
        {7, UINT64_C(547725013666734), UINT64_C(547725014089229)},
        {11, UINT64_C(674947515845858), UINT64_C(674947516268353)},
        {13, UINT64_C(721969060362613), UINT64_C(721969060925845)},
        {17, UINT64_C(797478659741748), UINT64_C(797478660304980)},
        {19, UINT64_C(828785892793963), UINT64_C(828785893357196)},
        {23, UINT64_C(882563161108618), UINT64_C(882563161679169)},
        {29, UINT64_C(947809514957280), UINT64_C(947809515661250)},
        {31, UINT64_C(966567293180498), UINT64_C(966588862848202)}
    };
    uint64_t index;

    memset(bytes, 0, (size_t)LOG_KAT_BYTES);
    memcpy(bytes, magic, sizeof(magic));
    put_be16(bytes + 8, TG_SQ218_V2_VERSION);
    put_be16(bytes + 10, (uint16_t)TG_SQ218_V2_HEADER_BYTES);
    put_be64(bytes + 16, 31);
    put_be64(bytes + 24, 31);
    put_be64(bytes + 32, TG_SQ218_LOG_SEED_AT);
    put_be64(bytes + 40, TG_SQ218_LOG_SCALE);
    put_be64(bytes + 48, TG_SQ218_RECIPROCAL_SCALE);
    put_be64(bytes + 56, LOG_KAT_PRIME_COUNT);
    put_be64(bytes + 96, LOG_KAT_PRIMES_OFFSET);
    put_be64(bytes + 104, LOG_KAT_END);
    put_be64(bytes + 112, LOG_KAT_END);
    put_be64(bytes + 120, LOG_KAT_END);
    put_be64(bytes + 128, LOG_KAT_END);
    put_be64(bytes + 136, LOG_KAT_END);

    for (index = 0; index < LOG_KAT_PRIME_COUNT; ++index) {
        put_prime_record(
            bytes + LOG_KAT_PRIMES_OFFSET
                + index * TG_SQ218_V2_PRIME_BYTES,
            rows[index][0],
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            rows[index][1],
            rows[index][2]);
    }
}

static void arithmetic_kats(void)
{
    tg_sq218_u128 result;
    uint64_t aliased_output = UINT64_C(19);

    expect(
        tg_sq218_u128_add_checked(
            0, 0, 0, 1, &result.hi, &result.lo)
            && result.hi == 0 && result.lo == 1,
        "u128 zero plus one");
    expect(
        !tg_sq218_u128_add_checked(
            UINT64_MAX,
            UINT64_MAX,
            0,
            1,
            &result.hi,
            &result.lo),
        "u128 addition rejects overflow");
    expect(
        tg_sq218_u128_mul_u64_checked(
            0, UINT64_MAX, 2, &result.hi, &result.lo)
            && result.hi == 1 && result.lo == UINT64_MAX - 1,
        "u128 multiplication carries from low limb");
    expect(
        tg_sq218_u128_mul_u64_checked(
            1, 2, 3, &result.hi, &result.lo)
            && result.hi == 3 && result.lo == 6,
        "u128 multiplication preserves mixed limbs");
    expect(
        !tg_sq218_u128_mul_u64_checked(
            UINT64_MAX,
            UINT64_MAX,
            2,
            &result.hi,
            &result.lo),
        "u128 multiplication rejects overflow");
    expect(
        tg_sq218_u128_compare(1, 0, 0, UINT64_MAX) > 0,
        "u128 comparison orders high limbs first");
    expect(
        tg_sq218_u128_sub_checked(
            1, 0, 0, 1, &result.hi, &result.lo)
            && result.hi == 0 && result.lo == UINT64_MAX,
        "u128 subtraction borrows from the high limb");
    expect(
        !tg_sq218_u128_add_checked(
            0, 1, 0, 2, &aliased_output, &aliased_output)
            && aliased_output == UINT64_C(19),
        "u128 helpers reject aliased limb outputs without writing");
}

static int write_fixture_file(
    const char *path,
    const uint8_t *bytes,
    size_t length)
{
    FILE *stream = fopen(path, "wb");
    int ok;

    if (stream == NULL) {
        return 0;
    }
    ok = fwrite(bytes, 1, length, stream) == length;
    if (fclose(stream) != 0) {
        ok = 0;
    }
    return ok;
}

static int read_exact_file(
    const char *path,
    uint8_t *bytes,
    size_t length)
{
    FILE *stream = fopen(path, "rb");
    int close_status;
    int extra;
    int ok;

    if (stream == NULL) {
        return 0;
    }
    ok = fread(bytes, 1, length, stream) == length;
    extra = fgetc(stream);
    if (extra != EOF || ferror(stream) != 0) {
        ok = 0;
    }
    close_status = fclose(stream);
    if (close_status != 0) {
        ok = 0;
    }
    return ok;
}

static int rejected_record_is_canonical(
    const uint8_t *record,
    size_t input_bytes,
    tg_sq218_status status)
{
    static const uint8_t magic[8] = {
        0x53, 0x51, 0x32, 0x31, 0x38, 0x52, 0x32, 0x00
    };
    size_t index;

    if (memcmp(record, magic, sizeof(magic)) != 0
        || get_be16(record + 8) != TG_SQ218_RESULT_V2_VERSION
        || get_be16(record + 10) != TG_SQ218_RESULT_V2_BYTES
        || get_be32(record + 12) != (uint32_t)status
        || get_be64(record + 16) != (uint64_t)input_bytes) {
        return 0;
    }
    for (index = 24;
         index < 88;
         ++index) {
        if (record[index] != 0) {
            return 0;
        }
    }
    return 1;
}

static void sha256_kats(void)
{
    static const uint8_t empty_digest[32] = {
        0xe3, 0xb0, 0xc4, 0x42, 0x98, 0xfc, 0x1c, 0x14,
        0x9a, 0xfb, 0xf4, 0xc8, 0x99, 0x6f, 0xb9, 0x24,
        0x27, 0xae, 0x41, 0xe4, 0x64, 0x9b, 0x93, 0x4c,
        0xa4, 0x95, 0x99, 0x1b, 0x78, 0x52, 0xb8, 0x55
    };
    static const uint8_t abc[3] = {0x61, 0x62, 0x63};
    static const uint8_t abc_digest[32] = {
        0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea,
        0x41, 0x41, 0x40, 0xde, 0x5d, 0xae, 0x22, 0x23,
        0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17, 0x7a, 0x9c,
        0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad
    };
    static const uint8_t padding_boundary[] =
        "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    static const uint8_t padding_boundary_digest[32] = {
        0x24, 0x8d, 0x6a, 0x61, 0xd2, 0x06, 0x38, 0xb8,
        0xe5, 0xc0, 0x26, 0x93, 0x0c, 0x3e, 0x60, 0x39,
        0xa3, 0x3c, 0xe4, 0x59, 0x64, 0xff, 0x21, 0x67,
        0xf6, 0xec, 0xed, 0xd4, 0x19, 0xdb, 0x06, 0xc1
    };
    static const uint8_t full_block_digest[32] = {
        0xff, 0xe0, 0x54, 0xfe, 0x7a, 0xe0, 0xcb, 0x6d,
        0xc6, 0x5c, 0x3a, 0xf9, 0xb6, 0x1d, 0x52, 0x09,
        0xf4, 0x39, 0x85, 0x1d, 0xb4, 0x3d, 0x0b, 0xa5,
        0x99, 0x73, 0x37, 0xdf, 0x15, 0x46, 0x68, 0xeb
    };
    uint8_t empty[1] = {0};
    uint8_t full_block[64];
    uint8_t record[TG_SQ218_RESULT_V2_BYTES];
    tg_sq218_status status = TG_SQ218_OK;

    expect(
        tg_sq218_validate_snapshot_to_record_v2(
            empty, 0, record, &status)
            && status == TG_SQ218_BAD_FORMAT
            && memcmp(record + 88, empty_digest, sizeof(empty_digest)) == 0,
        "owned-snapshot SHA-256 matches the empty-message vector");
    status = TG_SQ218_OK;
    expect(
        tg_sq218_validate_snapshot_to_record_v2(
            abc, sizeof(abc), record, &status)
            && status == TG_SQ218_BAD_FORMAT
            && memcmp(record + 88, abc_digest, sizeof(abc_digest)) == 0,
        "owned-snapshot SHA-256 matches the abc vector");
    status = TG_SQ218_OK;
    expect(
        tg_sq218_validate_snapshot_to_record_v2(
            padding_boundary,
            sizeof(padding_boundary) - 1,
            record,
            &status)
            && status == TG_SQ218_BAD_FORMAT
            && memcmp(
                record + 88,
                padding_boundary_digest,
                sizeof(padding_boundary_digest)) == 0,
        "owned-snapshot SHA-256 matches the two-padding-block vector");
    memset(full_block, 'a', sizeof(full_block));
    status = TG_SQ218_OK;
    expect(
        tg_sq218_validate_snapshot_to_record_v2(
            full_block, sizeof(full_block), record, &status)
            && status == TG_SQ218_BAD_FORMAT
            && memcmp(
                record + 88,
                full_block_digest,
                sizeof(full_block_digest)) == 0,
        "owned-snapshot SHA-256 matches the full-input-block vector");
}

static void command_kats(uint8_t *bytes, size_t length)
{
    char directory[] = "/tmp/sqrt218-command-kat-XXXXXX";
    char input_path[128];
    char output_path[128];
    char tampered_input_path[128];
    char tampered_output_path[128];
    char hardlink_output_path[128];
    uint8_t record[TG_SQ218_RESULT_V2_BYTES];
    uint8_t expected_record[TG_SQ218_RESULT_V2_BYTES];
    uint8_t before[TG_SQ218_RESULT_V2_BYTES];
    uint8_t restored[KAT_BYTES];
    uint8_t tampered[KAT_BYTES];
    tg_sq218_status checker_status = TG_SQ218_OK;
    uint32_t flat_status = UINT32_MAX;
    tg_sq218_command_exit command_status;
    int path_ok;

    expect(
        tg_sq218_validate_snapshot_to_record_v2(
            bytes, length, record, &checker_status)
            && checker_status == TG_SQ218_BAD_FORMAT
            && rejected_record_is_canonical(
                record, length, TG_SQ218_BAD_FORMAT),
        "owned-snapshot wrapper rejects bound-5 as non-production");
    memcpy(expected_record, record, sizeof(expected_record));

    expect(
        tg_sq218_verify_snapshot_v2(
            bytes, (uint64_t)length, record, &flat_status)
            && flat_status == (uint32_t)TG_SQ218_BAD_FORMAT
            && memcmp(record, expected_record, sizeof(record)) == 0,
        "flat proof-facing snapshot ABI emits the same rejection record");

    memcpy(before, bytes, sizeof(before));
    checker_status = TG_SQ218_OK;
    expect(
        !tg_sq218_validate_snapshot_to_record_v2(
            bytes, length, bytes, &checker_status)
            && checker_status == TG_SQ218_BAD_ARGUMENT
            && memcmp(before, bytes, sizeof(before)) == 0,
        "owned-snapshot wrapper rejects an aliased result buffer");

    if (mkdtemp(directory) == NULL) {
        expect(0, "create private command KAT directory");
        return;
    }
    path_ok =
        snprintf(
            input_path, sizeof(input_path), "%s/input.sq218v2", directory)
            > 0
        && snprintf(
            output_path, sizeof(output_path), "%s/output.sq218r2", directory)
            > 0
        && snprintf(
            tampered_input_path,
            sizeof(tampered_input_path),
            "%s/tampered.sq218v2",
            directory) > 0
        && snprintf(
            tampered_output_path,
            sizeof(tampered_output_path),
            "%s/tampered.sq218r2",
            directory) > 0
        && snprintf(
            hardlink_output_path,
            sizeof(hardlink_output_path),
            "%s/input-hardlink.sq218r2",
            directory) > 0;
    if (!path_ok) {
        expect(0, "construct command KAT paths");
        (void)rmdir(directory);
        return;
    }

    expect(
        write_fixture_file(input_path, bytes, length),
        "write bound-5 command KAT input");
    checker_status = TG_SQ218_OK;
    command_status =
        tg_sq218_run_files_v2(input_path, output_path, &checker_status);
    expect(
        command_status == TG_SQ218_COMMAND_REJECTED
            && checker_status == TG_SQ218_BAD_FORMAT,
        "file command never reports bound-5 as production success");
    expect(
        read_exact_file(
            output_path, record, (size_t)TG_SQ218_RESULT_V2_BYTES)
            && rejected_record_is_canonical(
                record, length, TG_SQ218_BAD_FORMAT)
            && memcmp(record, expected_record, sizeof(record)) == 0,
        "file command writes the canonical bound-5 rejection record");

    memcpy(tampered, bytes, length);
    tampered[103] ^= UINT8_C(1);
    expect(
        write_fixture_file(tampered_input_path, tampered, length),
        "write tampered command KAT input");
    checker_status = TG_SQ218_OK;
    command_status =
        tg_sq218_run_files_v2(
            tampered_input_path,
            tampered_output_path,
            &checker_status);
    expect(
        command_status == TG_SQ218_COMMAND_REJECTED
            && checker_status == TG_SQ218_BAD_FORMAT
            && read_exact_file(
                tampered_output_path,
                record,
                (size_t)TG_SQ218_RESULT_V2_BYTES)
            && rejected_record_is_canonical(
                record, length, TG_SQ218_BAD_FORMAT)
            && memcmp(record, expected_record, 88) == 0
            && memcmp(record + 88, expected_record + 88, 32) != 0,
        "file command rejects and digest-distinguishes a tampered offset");

    checker_status = TG_SQ218_OK;
    command_status =
        tg_sq218_run_files_v2(input_path, input_path, &checker_status);
    expect(
        command_status == TG_SQ218_COMMAND_OUTPUT_CREATE_ERROR,
        "file command refuses an input/output path alias");
    expect(
        read_exact_file(input_path, restored, length)
            && memcmp(restored, bytes, length) == 0,
        "path-alias rejection leaves the input snapshot source unchanged");

    expect(
        link(input_path, hardlink_output_path) == 0,
        "create input hard-link alias for command KAT");
    checker_status = TG_SQ218_OK;
    command_status =
        tg_sq218_run_files_v2(
            input_path, hardlink_output_path, &checker_status);
    expect(
        command_status == TG_SQ218_COMMAND_OUTPUT_CREATE_ERROR
            && read_exact_file(input_path, restored, length)
            && memcmp(restored, bytes, length) == 0,
        "file command refuses a hard-link output alias");

    (void)unlink(hardlink_output_path);
    (void)unlink(tampered_output_path);
    (void)unlink(tampered_input_path);
    (void)unlink(output_path);
    (void)unlink(input_path);
    (void)rmdir(directory);
}

int main(void)
{
    uint8_t bytes[KAT_BYTES];
    uint8_t log_bytes[LOG_KAT_BYTES];
    tg_sq218_view_v2 view;
    tg_sq218_view_v2 log_view;
    tg_sq218_scan_state_v2 state;
    tg_sq218_u128 slack;
    tg_sq218_validation_result_v2 production_result;
    uint8_t saved;

    arithmetic_kats();
    sha256_kats();
    make_kat(bytes);
    make_log_recurrence_kat(log_bytes);
    command_kats(bytes, sizeof(bytes));
    expect(
        tg_sq218_view_open_v2(bytes, sizeof(bytes), &view)
            == TG_SQ218_OK,
        "canonical KAT header opens");
    expect(
        tg_sq218_validate_roster_v2(&view) == TG_SQ218_OK,
        "Pratt references and factor gaps validate");
    expect(
        tg_sq218_validate_power_layout_v2(&view) == TG_SQ218_OK,
        "flattened prime-power inverse map validates");
    expect(
        tg_sq218_validate_log_ladder_v2(&view) == TG_SQ218_OK,
        "seed-table log rows validate");
    expect(
        tg_sq218_scan_all_events_v2(&view, &state) == TG_SQ218_OK
            && state.next_event == KAT_EVENT_COUNT,
        "bounded arithmetic stream validates");
    expect(
        tg_sq218_anchor_v2(&view, &state, &slack) == TG_SQ218_OK
            && (slack.hi != 0 || slack.lo != 0),
        "endpoint guard has positive slack");
    expect(
        tg_sq218_validate_bytes_v2(
            bytes, sizeof(bytes), &production_result)
            == TG_SQ218_BAD_FORMAT,
        "byte-level production entry point rejects the KAT profile");
    expect(
        tg_sq218_view_open_v2(
            log_bytes, sizeof(log_bytes), &log_view) == TG_SQ218_OK
            && tg_sq218_validate_log_ladder_v2(&log_view)
                == TG_SQ218_OK,
        "log ladder advances through the first post-seed recurrence");
    log_bytes[
        LOG_KAT_PRIMES_OFFSET
            + (LOG_KAT_PRIME_COUNT - 1) * TG_SQ218_V2_PRIME_BYTES
            + 71] ^= UINT8_C(1);
    expect(
        tg_sq218_validate_log_ladder_v2(&log_view)
            == TG_SQ218_PROOF_REJECTED,
        "post-seed log endpoint tampering is rejected");

    saved = bytes[103];
    bytes[103] ^= UINT8_C(1);
    expect(
        tg_sq218_view_open_v2(bytes, sizeof(bytes), &view)
            == TG_SQ218_BAD_FORMAT,
        "noncanonical section offset is rejected");
    bytes[103] = saved;
    expect(
        tg_sq218_view_open_v2(bytes, sizeof(bytes), &view)
            == TG_SQ218_OK,
        "restored header reopens");

    saved = bytes[KAT_FACTORS_OFFSET + 7];
    bytes[KAT_FACTORS_OFFSET + 7] = 1;
    expect(
        tg_sq218_validate_roster_v2(&view)
            == TG_SQ218_PROOF_REJECTED,
        "factor reference to current row is rejected");
    bytes[KAT_FACTORS_OFFSET + 7] = saved;

    saved = bytes[KAT_GAPS_OFFSET + 15];
    bytes[KAT_GAPS_OFFSET + 15] = 3;
    expect(
        tg_sq218_validate_roster_v2(&view)
            == TG_SQ218_PROOF_REJECTED,
        "incorrect composite factor pair is rejected");
    bytes[KAT_GAPS_OFFSET + 15] = saved;

    saved = bytes[KAT_POWER_REFS_OFFSET + 15];
    bytes[KAT_POWER_REFS_OFFSET + 15] = 1;
    expect(
        tg_sq218_validate_power_layout_v2(&view)
            == TG_SQ218_PROOF_REJECTED,
        "wrong per-prime event reference is rejected");
    bytes[KAT_POWER_REFS_OFFSET + 15] = saved;

    saved = bytes[KAT_EVENTS_OFFSET + 24 + 7];
    bytes[KAT_EVENTS_OFFSET + 24 + 7] = 2;
    expect(
        tg_sq218_scan_all_events_v2(&view, &state)
            == TG_SQ218_PROOF_REJECTED,
        "incorrect floor square root is rejected");
    bytes[KAT_EVENTS_OFFSET + 24 + 7] = saved;

    if (failures != 0) {
        return 1;
    }
    puts("sqrt218 CPU checker: bounded KAT passed");
    return 0;
}

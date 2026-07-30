/* Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Benchmark and known-answer driver for the PT21 level-0 ladder checker.
 *
 * This driver is *not* part of the CompCert-compiled proof unit; it uses libc
 * for timing, allocation, and reporting.  Only `pt21_ladder_check.c` is the
 * verified-compiler target.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "pt21_ladder_check.h"

#define PT21_SOURCE_BLOCK_COUNT UINT64_C(2966443783)
#define PT21_SOURCE_LOWER_COUNT UINT64_C(32130158315)
#define PT21_SOURCE_UPPER_COUNT UINT64_C(12363153437138)

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

static void put_i64(uint8_t *p, int64_t value)
{
    uint64_t raw;
    if (value < 0) {
        raw = ~(uint64_t)(-(value + 1));
    } else {
        raw = (uint64_t)value;
    }
    put_be64(p, raw);
}

static void set_bit(uint8_t *bitmap, unsigned index, unsigned value)
{
    unsigned byte = index >> 3;
    unsigned shift = index & 7U;
    bitmap[byte] = (uint8_t)((bitmap[byte] & ~(1U << shift))
        | ((value & 1U) << shift));
}

static unsigned get_bit(const uint8_t *bitmap, unsigned index)
{
    return (unsigned)((bitmap[index >> 3] >> (index & 7U)) & 1U);
}

/* Fill `bitmap` over `samples` samples so that exactly `transitions`
 * adjacent pairs differ, starting from sign `start`. */
static void fill_bitmap(
    uint8_t *bitmap, unsigned samples, unsigned transitions, unsigned start,
    unsigned bytes)
{
    unsigned index;
    unsigned current = start & 1U;
    unsigned next_toggle = 0U;
    unsigned toggles_done = 0U;
    for (index = 0; index < bytes; ++index) {
        bitmap[index] = 0U;
    }
    for (index = 0; index < samples; ++index) {
        if (toggles_done < transitions) {
            next_toggle = (unsigned)(((uint64_t)(toggles_done + 1U)
                * (uint64_t)(samples - 1U)) / (uint64_t)transitions);
            if (index == next_toggle) {
                current ^= 1U;
                toggles_done += 1U;
            }
        }
        set_bit(bitmap, index, current);
    }
}

static int64_t left_weight_of(const uint8_t *bitmap, unsigned samples)
{
    int64_t total = 0;
    unsigned index;
    for (index = 0; index + 1U < samples; ++index) {
        if (get_bit(bitmap, index) != get_bit(bitmap, index + 1U)) {
            total += (int64_t)index;
        }
    }
    return -total;
}

static int64_t right_weight_of(
    const uint8_t *bitmap, unsigned samples, unsigned span)
{
    int64_t total = 0;
    unsigned index;
    for (index = 0; index + 1U < samples; ++index) {
        if (get_bit(bitmap, index) != get_bit(bitmap, index + 1U)) {
            total += (int64_t)(span - (index + 1U));
        }
    }
    return total;
}

/* Build one internally consistent synthetic packet. */
static void build_packet(
    uint8_t *packet, uint64_t block, uint64_t lower_count,
    unsigned main_transitions, unsigned flank_transitions)
{
    static const uint8_t magic[8] = {
        0x50, 0x54, 0x32, 0x31, 0x4C, 0x30, 0x01, 0x00
    };
    uint8_t *main_bitmap;
    uint8_t *left_bitmap;
    uint8_t *right_bitmap;
    uint64_t slots = (uint64_t)main_transitions;
    uint64_t upper_count = lower_count + slots;
    int64_t s_bound = 3789;              /* ~3.70 at scale 2^10 */
    int64_t left_weight;
    int64_t right_weight;
    int64_t left_integral;
    int64_t right_integral;
    int64_t quotient_lower;
    int64_t quotient_upper;
    int64_t numerator_lower;
    int64_t numerator_upper;
    unsigned index;
    unsigned main_start;

    for (index = 0; index < (unsigned)PT21_PACKET_BYTES; ++index) {
        packet[index] = 0U;
    }
    for (index = 0; index < 8U; ++index) {
        packet[index] = magic[index];
    }
    put_be64(packet + 8, block);
    put_be64(packet + 16, lower_count);
    put_be64(packet + 24, upper_count);
    put_be32(packet + 32, (uint32_t)slots);
    put_be32(packet + 36, 0U);

    main_bitmap = packet + PT21_PACKET_HEADER_BYTES;
    left_bitmap = main_bitmap + PT21_MAIN_BITMAP_BYTES;
    right_bitmap = left_bitmap + PT21_FLANK_BITMAP_BYTES;

    main_start = (unsigned)(block & 1U);
    fill_bitmap(main_bitmap, PT21_MAIN_SAMPLES, main_transitions, main_start,
        PT21_MAIN_BITMAP_BYTES);
    /* The left flank must end on the main stream's first sign, and the right
     * flank must start on the main stream's last sign. */
    fill_bitmap(left_bitmap, PT21_FLANK_SAMPLES, flank_transitions,
        (main_start + flank_transitions) & 1U, PT21_FLANK_BITMAP_BYTES);
    fill_bitmap(right_bitmap, PT21_FLANK_SAMPLES, flank_transitions,
        get_bit(main_bitmap, PT21_MAIN_SAMPLES - 1U), PT21_FLANK_BITMAP_BYTES);

    left_weight = left_weight_of(left_bitmap, PT21_FLANK_SAMPLES);
    right_weight = right_weight_of(
        right_bitmap, PT21_FLANK_SAMPLES, PT21_FLANK_SPAN_STEPS);
    left_integral = left_weight * (int64_t)(PT21_DELTA_NUMERATOR * 2);
    right_integral = right_weight * (int64_t)(PT21_DELTA_NUMERATOR * 2);

    /* Place the lower quotient strictly inside the ceiling cell for
     * lower_count - 1, and the upper quotient strictly inside the floor cell
     * for upper_count - 1. */
    quotient_lower = ((int64_t)lower_count - 1) * (int64_t)PT21_SCALE - 1;
    quotient_upper = ((int64_t)upper_count - 1) * (int64_t)PT21_SCALE + 1;
    numerator_lower = quotient_lower * (int64_t)PT21_FLANK_WIDTH;
    numerator_upper = quotient_upper * (int64_t)PT21_FLANK_WIDTH;

    put_i64(packet + 72, s_bound);
    put_i64(packet + 80, s_bound);
    put_i64(packet + 88, numerator_lower + s_bound + left_integral);
    put_i64(packet + 96, numerator_lower + s_bound + left_integral);
    put_i64(packet + 104, s_bound);
    put_i64(packet + 112, s_bound);
    put_i64(packet + 120, numerator_upper - s_bound + right_integral);
    put_i64(packet + 128, numerator_upper - s_bound + right_integral);
}

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int run_kat(void)
{
    static uint8_t packet[PT21_PACKET_BYTES];
    pt21_ladder_state state;
    pt21_window_summary summary;
    uint8_t group_record[PT21_GROUP_RECORD_BYTES];
    uint8_t root[32];
    int ready;
    int status;
    unsigned failures = 0U;
    unsigned mutation;
    /* Load-bearing byte offsets: magic, block index, count cursor, slot
     * count, S-bound enclosure, main bitmap head, main bitmap tail, left
     * flank, right flank interior. */
    static const unsigned mutation_offsets[9] = {
        0U, 8U, 16U, 32U, 72U, 136U, 3200U, 3280U, 3330U
    };

    build_packet(packet, 0U, PT21_SOURCE_LOWER_COUNT, 4157U, 87U);
    pt21_ladder_start(&state, 0U, PT21_SOURCE_LOWER_COUNT, 4U, 1);
    status = pt21_ladder_step(
        &state, packet, (size_t)PT21_PACKET_BYTES, &summary,
        group_record, &ready);
    if (status != PT21_OK) {
        printf("KAT FAIL: honest packet rejected with code %d\n", status);
        failures += 1U;
    } else if (summary.slots != 4157U
            || summary.upper_count != PT21_SOURCE_LOWER_COUNT + 4157U) {
        printf("KAT FAIL: wrong summary\n");
        failures += 1U;
    }

    /* Every mutated byte must be rejected. */
    for (mutation = 0U; mutation < 9U; ++mutation) {
        unsigned offset = mutation_offsets[mutation];
        build_packet(packet, 0U, PT21_SOURCE_LOWER_COUNT, 4157U, 87U);
        packet[offset] = (uint8_t)(packet[offset] ^ 0x01U);
        pt21_ladder_start(&state, 0U, PT21_SOURCE_LOWER_COUNT, 4U, 1);
        status = pt21_ladder_step(
            &state, packet, (size_t)PT21_PACKET_BYTES, &summary,
            group_record, &ready);
        if (status == PT21_OK) {
            printf("KAT FAIL: mutation at offset %u accepted\n", offset);
            failures += 1U;
        }
    }

    /* Non-canonical padding bits must be rejected. */
    build_packet(packet, 0U, PT21_SOURCE_LOWER_COUNT, 4157U, 87U);
    packet[PT21_PACKET_BYTES - 1U] =
        (uint8_t)(packet[PT21_PACKET_BYTES - 1U] ^ 0x02U);
    pt21_ladder_start(&state, 0U, PT21_SOURCE_LOWER_COUNT, 4U, 1);
    status = pt21_ladder_step(
        &state, packet, (size_t)PT21_PACKET_BYTES, &summary,
        group_record, &ready);
    if (status == PT21_OK) {
        printf("KAT FAIL: non-canonical padding accepted\n");
        failures += 1U;
    }

    /* An inflated slot count with an honest bitmap must be rejected. */
    build_packet(packet, 0U, PT21_SOURCE_LOWER_COUNT, 4157U, 87U);
    put_be32(packet + 32, 4158U);
    put_be64(packet + 24, PT21_SOURCE_LOWER_COUNT + 4158U);
    pt21_ladder_start(&state, 0U, PT21_SOURCE_LOWER_COUNT, 4U, 1);
    status = pt21_ladder_step(
        &state, packet, (size_t)PT21_PACKET_BYTES, &summary,
        group_record, &ready);
    if (status == PT21_OK) {
        printf("KAT FAIL: forged slot count accepted\n");
        failures += 1U;
    }

    /* An out-of-order block index must be rejected. */
    build_packet(packet, 7U, PT21_SOURCE_LOWER_COUNT, 4157U, 87U);
    pt21_ladder_start(&state, 0U, PT21_SOURCE_LOWER_COUNT, 4U, 1);
    status = pt21_ladder_step(
        &state, packet, (size_t)PT21_PACKET_BYTES, &summary,
        group_record, &ready);
    if (status != PT21_ERR_BLOCK_INDEX) {
        printf("KAT FAIL: block skip accepted (code %d)\n", status);
        failures += 1U;
    }

    (void)pt21_ladder_finish(&state, group_record, &ready, root);
    if (failures == 0U) {
        printf("KAT PASS\n");
        return 0;
    }
    printf("KAT FAILURES: %u\n", failures);
    return 1;
}

int main(int argc, char **argv)
{
    uint64_t blocks = 200000;
    uint32_t blocks_per_group = 512;   /* one scheduler work unit */
    uint64_t index;
    uint8_t *packets;
    pt21_ladder_state state;
    pt21_window_summary summary;
    uint8_t group_record[PT21_GROUP_RECORD_BYTES];
    uint8_t root[32];
    int ready;
    int status;
    double start;
    double elapsed;
    double blocks_per_second;
    double bytes_per_second;
    double average_slots;
    uint64_t groups = 0;
    int commit_packets = 1;
    int argument;
    const char *group_path = NULL;
    FILE *group_file = NULL;

    for (argument = 1; argument < argc; ++argument) {
        if (strcmp(argv[argument], "--kat") == 0) {
            return run_kat();
        }
        if (strcmp(argv[argument], "--no-packet-commit") == 0) {
            commit_packets = 0;
        } else if (strcmp(argv[argument], "--emit-groups") == 0
                && argument + 1 < argc) {
            group_path = argv[argument + 1];
            argument += 1;
        } else if (strcmp(argv[argument], "--blocks") == 0
                && argument + 1 < argc) {
            blocks = strtoull(argv[argument + 1], NULL, 10);
            argument += 1;
        } else if (strcmp(argv[argument], "--blocks-per-group") == 0
                && argument + 1 < argc) {
            blocks_per_group = (uint32_t)strtoul(argv[argument + 1], NULL, 10);
            argument += 1;
        }
    }

    packets = (uint8_t *)malloc((size_t)blocks * (size_t)PT21_PACKET_BYTES);
    if (packets == NULL) {
        fprintf(stderr, "allocation failed\n");
        return 2;
    }
    for (index = 0; index < blocks; ++index) {
        uint64_t lower = PT21_SOURCE_LOWER_COUNT + index * UINT64_C(4157);
        build_packet(
            packets + index * (size_t)PT21_PACKET_BYTES, index, lower,
            4157U, 87U);
    }

    if (group_path != NULL) {
        group_file = fopen(group_path, "wb");
        if (group_file == NULL) {
            fprintf(stderr, "cannot open %s\n", group_path);
            free(packets);
            return 2;
        }
    }

    pt21_ladder_start(
        &state, 0U, PT21_SOURCE_LOWER_COUNT, blocks_per_group, commit_packets);
    start = now_seconds();
    for (index = 0; index < blocks; ++index) {
        status = pt21_ladder_step(
            &state, packets + index * (size_t)PT21_PACKET_BYTES,
            (size_t)PT21_PACKET_BYTES, &summary, group_record, &ready);
        if (status != PT21_OK) {
            fprintf(stderr, "rejected block %llu with code %d\n",
                (unsigned long long)index, status);
            free(packets);
            return 3;
        }
        if (ready != 0) {
            groups += 1;
            if (group_file != NULL) {
                (void)fwrite(group_record, 1U,
                    (size_t)PT21_GROUP_RECORD_BYTES, group_file);
            }
        }
    }
    elapsed = now_seconds() - start;
    (void)pt21_ladder_finish(&state, group_record, &ready, root);
    if (ready != 0) {
        groups += 1;
        if (group_file != NULL) {
            (void)fwrite(group_record, 1U,
                (size_t)PT21_GROUP_RECORD_BYTES, group_file);
        }
    }
    if (group_file != NULL) {
        (void)fclose(group_file);
    }

    blocks_per_second = (double)blocks / elapsed;
    bytes_per_second = blocks_per_second * (double)PT21_PACKET_BYTES;
    average_slots = (double)(PT21_SOURCE_UPPER_COUNT - PT21_SOURCE_LOWER_COUNT)
        / (double)PT21_SOURCE_BLOCK_COUNT;

    printf("{\"blocks\": %llu,", (unsigned long long)blocks);
    printf(" \"packet_bytes\": %u,", (unsigned)PT21_PACKET_BYTES);
    printf(" \"blocks_per_group\": %lu,", (unsigned long)blocks_per_group);
    printf(" \"commit_packets\": %d,", commit_packets);
    printf(" \"groups_emitted\": %llu,", (unsigned long long)groups);
    printf(" \"seconds\": %.6f,", elapsed);
    printf(" \"blocks_per_second\": %.1f,", blocks_per_second);
    printf(" \"megabytes_per_second\": %.1f,", bytes_per_second / 1.0e6);
    printf(" \"slots_per_second\": %.4g,", blocks_per_second * average_slots);
    printf(" \"campaign_core_hours\": %.4g,",
        (double)PT21_SOURCE_BLOCK_COUNT / blocks_per_second / 3600.0);
    printf(" \"campaign_wire_terabytes\": %.4g,",
        (double)PT21_SOURCE_BLOCK_COUNT * (double)PT21_PACKET_BYTES / 1.0e12);
    printf(" \"final_count\": %llu,",
        (unsigned long long)state.running_count);
    printf(" \"root\": \"");
    for (index = 0; index < 32; ++index) {
        printf("%02x", (unsigned)root[index]);
    }
    printf("\"}\n");

    free(packets);
    return 0;
}

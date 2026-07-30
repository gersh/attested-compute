/* Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Fixed-width level-0 checker for the Platt--Trudgian zeta ladder.
 *
 * The checker consumes one 3339-byte packet per source block, verifies every
 * finite obligation that does not require Hardy-Z arithmetic, and emits one
 * 88-byte level-2 group summary per fixed run of blocks.  See FORMAT.md.
 *
 * The source is written for the CompCert C subset: no packed-struct casts,
 * no compiler builtins, no variadic functions, no libc dependency beyond
 * <stdint.h> and <stddef.h>, and byte-by-byte big-endian decoding.
 */

#ifndef PT21_LADDER_CHECK_H
#define PT21_LADDER_CHECK_H

#include <stddef.h>
#include <stdint.h>

/* Lattice geometry, pinned to Platt's zeta_arb source. */
#define PT21_MAIN_SAMPLES 24577U
#define PT21_MAIN_SPAN_STEPS 24576U
#define PT21_MAIN_BITMAP_BYTES 3073U
#define PT21_FLANK_SAMPLES 513U
#define PT21_FLANK_SPAN_STEPS 512U
#define PT21_FLANK_BITMAP_BYTES 65U
#define PT21_MAX_STATIONARY 8U

/* Packet layout. */
#define PT21_PACKET_HEADER_BYTES 136U
#define PT21_PACKET_BYTES 3339U

/* Group summary layout. */
#define PT21_GROUP_RECORD_BYTES 88U

/* Fixed-point scale for the Turing quotient arithmetic: 2^10. */
#define PT21_SCALE_SHIFT 10
#define PT21_SCALE 1024

/* Fixed source constants. */
#define PT21_FLANK_WIDTH 21          /* the one-sided Turing window width */
#define PT21_DELTA_NUMERATOR 21      /* lattice spacing 21/512 */
#define PT21_DELTA_DENOMINATOR 512

/* Rejection codes.  Zero means accepted. */
#define PT21_OK 0
#define PT21_ERR_MAGIC 1
#define PT21_ERR_BLOCK_INDEX 2
#define PT21_ERR_COUNT_CURSOR 3
#define PT21_ERR_SLOT_CLOSURE 4
#define PT21_ERR_SLOT_DERIVATION 5
#define PT21_ERR_PARITY 6
#define PT21_ERR_BOUNDARY_SIGN 7
#define PT21_ERR_STATIONARY 8
#define PT21_ERR_TURING_LOWER 9
#define PT21_ERR_TURING_UPPER 10
#define PT21_ERR_INTERVAL 11
#define PT21_ERR_OVERFLOW 12
#define PT21_ERR_LENGTH 13
#define PT21_ERR_GEOMETRY 14

/* Decoded level-1 window summary; four naturals, exactly the Lean
 * `SparkInterval.Zeta.PT21Ladder.WindowSummary`. */
typedef struct {
    uint64_t block;
    uint64_t lower_count;
    uint64_t slots;
    uint64_t upper_count;
} pt21_window_summary;

/* Rolling state of the streaming checker.  Constant size: the checker never
 * retains a packet, a bracket, or a window list. */
typedef struct {
    uint64_t next_block;
    uint64_t running_count;
    uint64_t group_first_block;
    uint64_t group_first_count;
    uint64_t group_blocks;
    uint64_t group_slots;
    uint32_t group_digest_state[8];
    uint64_t group_digest_length;
    uint32_t root_state[8];
    uint64_t root_length;
    uint64_t groups_emitted;
    uint32_t blocks_per_group;
    /* When zero, the group digest commits only to the level-1 summaries and
     * not to the level-0 packet bytes.  That is a real weakening: a third
     * party can then no longer re-derive the summaries from retained
     * packets, so the level-0 check becomes replayable only inside the
     * attested run.  Production must set this to one. */
    int commit_packets;
} pt21_ladder_state;

/* Start a campaign at `first_block` with left-endpoint count `first_count`. */
void pt21_ladder_start(
    pt21_ladder_state *state,
    uint64_t first_block,
    uint64_t first_count,
    uint32_t blocks_per_group,
    int commit_packets);

/* Check one packet and fold it into the state.
 *
 * On acceptance the decoded window summary is written to `summary`.  When the
 * packet closes a group, `PT21_GROUP_RECORD_BYTES` are written to
 * `group_record` and `*group_ready` is set to 1. */
int pt21_ladder_step(
    pt21_ladder_state *state,
    const uint8_t *packet,
    size_t packet_length,
    pt21_window_summary *summary,
    uint8_t *group_record,
    int *group_ready);

/* Close a partial trailing group and finalize the campaign root. */
int pt21_ladder_finish(
    pt21_ladder_state *state,
    uint8_t *group_record,
    int *group_ready,
    uint8_t *root_digest);

#endif /* PT21_LADDER_CHECK_H */

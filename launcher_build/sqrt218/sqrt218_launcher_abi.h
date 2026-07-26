/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#ifndef SPARKINTERVAL_SQRT218_LAUNCHER_ABI_H
#define SPARKINTERVAL_SQRT218_LAUNCHER_ABI_H

#include <stddef.h>
#include <stdint.h>

/*
 * This structure is shared with sqrt218_pure_entry_trampoline.S.  Keep the
 * explicit offset assertions: the assembly is deliberately small enough for
 * a human to compare with this declaration.
 */
typedef struct tg_sq218_launch_observation {
    uint64_t launcher_entry_attempt_count;
    uint64_t returned_to_sentinel;
    int32_t eax_return;
    uint32_t reserved;
    uint64_t return_sentinel;
    uint64_t entry_rsp_mod_16;
    uint64_t post_return_rflags;
} tg_sq218_launch_observation;

_Static_assert(
    offsetof(
        tg_sq218_launch_observation,
        launcher_entry_attempt_count) == 0,
    "launcher_entry_attempt_count ABI offset");
_Static_assert(
    offsetof(tg_sq218_launch_observation, returned_to_sentinel) == 8,
    "returned_to_sentinel ABI offset");
_Static_assert(
    offsetof(tg_sq218_launch_observation, eax_return) == 16,
    "eax_return ABI offset");
_Static_assert(
    offsetof(tg_sq218_launch_observation, return_sentinel) == 24,
    "return_sentinel ABI offset");
_Static_assert(
    offsetof(tg_sq218_launch_observation, entry_rsp_mod_16) == 32,
    "entry_rsp_mod_16 ABI offset");
_Static_assert(
    offsetof(tg_sq218_launch_observation, post_return_rflags) == 40,
    "post_return_rflags ABI offset");
_Static_assert(
    sizeof(tg_sq218_launch_observation) == 48,
    "launch observation ABI size");

int tg_sq218_call_pure_entry(
    const void *entry,
    const uint8_t *input,
    uint64_t input_length,
    uint8_t *result,
    uint32_t *status,
    void *stack_top,
    tg_sq218_launch_observation *observation);

extern const unsigned char tg_sq218_return_sentinel[];

#endif

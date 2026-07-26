/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#ifndef SPARKINTERVAL_SQRT218_CPU_COMMAND_H
#define SPARKINTERVAL_SQRT218_CPU_COMMAND_H

#include "sqrt218_cpu_checker.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Canonical fixed-width result record written by the V2 CPU command.
 * All multi-byte integers are unsigned big-endian.
 */
#define TG_SQ218_RESULT_V2_BYTES UINT64_C(120)
#define TG_SQ218_RESULT_V2_VERSION UINT16_C(1)

/*
 * Process exit statuses.  Zero is reserved for a production certificate that
 * the exact byte-level checker accepted and whose complete result record was
 * durably written.  A mathematical rejection still writes a canonical record
 * and returns TG_SQ218_COMMAND_REJECTED.
 */
typedef enum tg_sq218_command_exit {
    TG_SQ218_COMMAND_ACCEPTED = 0,
    TG_SQ218_COMMAND_REJECTED = 2,
    TG_SQ218_COMMAND_USAGE_ERROR = 64,
    TG_SQ218_COMMAND_INPUT_ERROR = 65,
    TG_SQ218_COMMAND_OUTPUT_CREATE_ERROR = 73,
    TG_SQ218_COMMAND_OUTPUT_WRITE_ERROR = 74
} tg_sq218_command_exit;

/*
 * Validate one already-owned immutable snapshot and encode its deterministic
 * result record.  `record` must name 120 writable bytes disjoint from the
 * complete snapshot range, and `checker_status` must be disjoint from both
 * ranges.  This function calls only
 * `tg_sq218_validate_bytes_v2`; it never invokes an internal checker stage.
 *
 * A return of one means that `record` was written.  The checker status may
 * still be nonzero, in which case all state/slack fields are canonically zero.
 * A return of zero is a wrapper argument/alias error and writes no record.
 */
int tg_sq218_validate_snapshot_to_record_v2(
    const uint8_t *snapshot,
    size_t length,
    uint8_t *record,
    tg_sq218_status *checker_status);

/*
 * Flat proof-facing ABI for the same snapshot-to-record operation.  It uses
 * fixed-width scalar length/status types and no structure arguments or
 * results.  The established production wrapper above remains unchanged.
 */
int tg_sq218_verify_snapshot_v2(
    const uint8_t *snapshot,
    uint64_t length,
    uint8_t *record,
    uint32_t *status_out);

/*
 * Production file command.
 *
 * The input is copied into a private owned allocation before validation.  The
 * output is created with exclusive-create semantics and is never allowed to
 * replace an existing path (including the input path).  On checker rejection a
 * canonical rejection record is written and the command returns 2.  The
 * record's SHA-256 field is computed from this exact owned snapshot, never by
 * reopening the input path.
 */
tg_sq218_command_exit tg_sq218_run_files_v2(
    const char *input_path,
    const char *output_path,
    tg_sq218_status *checker_status);

#ifdef __cplusplus
}
#endif

#endif

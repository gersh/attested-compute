/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

#include "sqrt218_cpu_command.h"

#include <stdio.h>

int main(int argc, char **argv)
{
    tg_sq218_status checker_status = TG_SQ218_BAD_ARGUMENT;
    tg_sq218_command_exit result;

    if (argc != 3) {
        fprintf(
            stderr,
            "usage: %s CERTIFICATE.sq218v2 RESULT.sq218r2\n",
            argc > 0 ? argv[0] : "sqrt218_cpu_checker_v2");
        return TG_SQ218_COMMAND_USAGE_ERROR;
    }
    result = tg_sq218_run_files_v2(argv[1], argv[2], &checker_status);
    if (result == TG_SQ218_COMMAND_REJECTED) {
        fprintf(
            stderr,
            "sqrt218 certificate rejected with checker status %u\n",
            (unsigned)checker_status);
    } else if (result != TG_SQ218_COMMAND_ACCEPTED) {
        fprintf(
            stderr,
            "sqrt218 command failed closed with exit status %u\n",
            (unsigned)result);
    }
    return (int)result;
}

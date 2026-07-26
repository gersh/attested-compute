/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Proof-facing single translation unit for Clight/VST/CompCert.
 *
 * TG_SQ218_PURE_ENTRY_ONLY must be supplied by the closed build command.
 * Including the implementation files here gives clightgen and VST one
 * CompCert program while preserving the two ordinary source files used by
 * the development build.
 */

#ifndef TG_SQ218_PURE_ENTRY_ONLY
#error "the proof-facing translation unit requires TG_SQ218_PURE_ENTRY_ONLY"
#endif

#include "../../cpu_checker/sqrt218/sqrt218_cpu_checker.c"
#include "../../cpu_checker/sqrt218/sqrt218_cpu_command.c"

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Isolated qualification wrapper.  It deliberately reuses the hardened live
// block-0 authentication, differential, scanner-replay, containment, and
// fail-closed fallback runner without changing that runner's source.  Only
// the tile9 entry and its resource query are redirected to the separately
// guarded fused bitreverse+tile9 implementation.

#if !defined(SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION) || \
    SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION != 1
#error "bitreverse-tile9 wrapper requires its qualification guard"
#endif

#define run_source_window_tile9_sloppy_root_qualification \
  run_source_window_bitreverse_tile9_sloppy_root_qualification
#define tile9_sloppy_root_kernel_resources_qualification \
  bitreverse_tile9_sloppy_root_kernel_resources_qualification
#include "tg_platt_pt21_live_transform_candidate_qualification.cu"

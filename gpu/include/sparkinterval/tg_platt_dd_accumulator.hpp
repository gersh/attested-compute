// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_platt_windowed.hpp"

#include <cuda_runtime.h>

#include <cstdint>

namespace sparkinterval::tg::platt_dd_accumulator {

namespace pw = sparkinterval::tg::platt_windowed;

// Persistent exact-source workspace for the 768000-term, 23-stage bucketed
// Taylor accumulator.  It owns the Q192 phase data, directed DD residual
// powers, recurrence state, and one 23*32768-cell output row.  Phase state is
// single-stream and nonconcurrent: enqueue calls must share one ordered
// producer stream.  Consumers on other streams must use explicit CUDA events,
// and all producer/consumer work must be quiescent before destruction.
struct Workspace;

struct SourceWindowView {
  const pw::ComplexDisk106* device_skn_rows = nullptr;
  std::uint64_t logical_block = 0;
  std::uint64_t window_center = 0;
  std::uint32_t stage_count = pw::kTaylorTerms;
  std::uint32_t row_stride = pw::kBucketCount;
};

// Initialize one exact, bounded source shard.  The expensive 768000-term
// constants are constructed once with directed MPFR and copied to CUDA.  The
// shard must lie wholly inside the pinned PT21 campaign.  Every output row is
// initialized to exact positive zero because the accumulator kernel writes
// only active buckets while the downstream transform reads the full row.
Workspace* create_source_workspace(std::uint64_t first_block,
                                   std::uint64_t block_count,
                                   std::uint32_t reanchor_blocks = 256U);

// Qualification-only counterpart with a bounded ring of independent output
// rows.  Immutable source tables and the ordered phase recurrence remain
// single-copy; only the 23*32768-cell output row is replicated.  This permits
// a producer stream to accumulate block b+1 while a consumer stream reads the
// completed row for block b.  It does not skip or recenter any logical block.
//
// `output_slots` is deliberately restricted to 2..4.  Production callers
// continue to use create_source_workspace, whose one-row allocation and
// behavior are unchanged.
Workspace* create_source_workspace_with_output_slots_qualification(
    std::uint64_t first_block, std::uint64_t block_count,
    std::uint32_t reanchor_blocks, std::uint32_t output_slots);

// Best-effort release of every allocation.  Passing null is a no-op; the
// first CUDA release failure is reported only after all pointers were tried.
// The caller must first synchronize every stream that can access the workspace
// or one of its borrowed output views.
void destroy_workspace(Workspace* workspace);

// Enqueue the next source window on `stream`.  The first window and every
// `reanchor_blocks` thereafter are evaluated directly from Q192 phases; other
// windows use the directed phase recurrence.  Output remains device-resident.
// A caller must consume the view before invoking this function again.
SourceWindowView run_next_source_window(Workspace* workspace,
                                        cudaStream_t stream);

// Qualification-only slot-indexed enqueue for a workspace constructed by
// create_source_workspace_with_output_slots_qualification.  Phase updates are
// still ordered by the caller's producer stream.  The caller must establish a
// CUDA happens-before edge from the previous consumer of `output_slot` before
// reusing that slot.
SourceWindowView run_next_source_window_to_slot_qualification(
    Workspace* workspace, cudaStream_t stream, std::uint32_t output_slot);

std::uint64_t first_block(const Workspace* workspace);
std::uint64_t block_count(const Workspace* workspace);
std::uint64_t windows_enqueued(const Workspace* workspace);
std::uint64_t workspace_device_bytes(const Workspace* workspace);
std::uint32_t output_slot_count(const Workspace* workspace);

// Qualification-only read access to the fixed 32769-entry source bucket
// offset table.  Bucket b is inactive exactly when offsets[b] equals
// offsets[b+1].  The returned pointer remains owned by the workspace.
const std::uint32_t* device_bucket_offsets_qualification(
    const Workspace* workspace);

// Qualification-only read access to the complete active-bucket roster used
// as the accumulator grid.  The count is bounded by kBucketCount and the
// returned pointer remains owned by the workspace.
const std::uint32_t* device_active_buckets_qualification(
    const Workspace* workspace);
std::uint32_t active_bucket_count_qualification(
    const Workspace* workspace);

#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
// Isolated accumulator-schedule experiments.  These entry points are absent
// from the default accumulator archive and must not be selected by production
// callers.
enum class QualificationSchedule : std::uint32_t {
  kBaseline8 = 0U,
  kWarp12 = 1U,
  kShared8 = 2U,
  kShared12 = 3U,
  kWarp16 = 4U,
  kWarp24 = 5U,
  kPrecomputedL1Warp8 = 6U,
  kPrecomputedL1PowerAbsWarp8 = 7U,
};

struct QualificationKernelResources {
  std::int32_t registers_per_thread = 0;
  std::uint64_t static_shared_bytes = 0U;
  std::uint64_t local_bytes_per_thread = 0U;
  std::int32_t maximum_threads_per_block = 0;
  std::int32_t active_blocks_per_multiprocessor = 0;
  std::uint32_t threads_per_block = 0U;
};

// Rerun the most recently enqueued logical window without changing phase
// state or the enqueue cursor.  The destination slot must differ from any
// still-live baseline slot owned by the caller.
SourceWindowView rerun_last_source_window_qualification(
    Workspace* workspace, cudaStream_t stream, std::uint32_t output_slot,
    QualificationSchedule schedule);

QualificationKernelResources qualification_kernel_resources(
    QualificationSchedule schedule);
#endif

}  // namespace sparkinterval::tg::platt_dd_accumulator

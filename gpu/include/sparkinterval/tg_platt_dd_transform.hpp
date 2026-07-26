// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_platt_windowed.hpp"

#include <cuda_runtime.h>

#include <cstddef>
#include <cstdint>

namespace sparkinterval::tg::platt_dd_transform {

// Opaque, persistent source-geometry workspace.  It owns all transform
// scratch buffers and the source-constant/root tables, but never owns either
// input pointer passed to run_source_window.  A workspace is single-stream
// and nonconcurrent: callers must order every run and output consumer on one
// CUDA stream (or with explicit events), and must quiesce that work before
// reuse from an unordered stream or destruction.
struct Workspace;

inline constexpr std::uint32_t kSourceSampleCount =
    4U * platt_windowed::kBucketCount;
inline constexpr std::uint32_t kSourceRequiredRadius =
    512U + 12'288U + 70U;
inline constexpr std::uint32_t kSourceRequiredBegin =
    kSourceSampleCount / 2U - kSourceRequiredRadius;
inline constexpr std::uint32_t kSourceRequiredEnd =
    kSourceSampleCount / 2U + kSourceRequiredRadius;
inline constexpr std::uint32_t kSourceRequiredCount =
    kSourceRequiredEnd - kSourceRequiredBegin + 1U;
// Adjacent PT21 logical windows are exactly 1008 ordinates apart, or 24576
// samples on the 21/512 transform lattice.  The shifted-view API below is a
// qualification boundary only: it checks array geometry, but does not claim
// that a shifted CUDA disk realizes Hardy Z at the reindexed ordinate.
inline constexpr std::int32_t kSourceBlockSampleShift = 24'576;

// Qualification-only diagnostics for the fail-closed device-input boundary.
// Production callers only need the resulting sample disks: if either bit is
// raised, every output sample is the canonical malformed disk
// {{+0,+0},+infinity}, which the event scanner rejects.
enum QualificationInputFailureFlag : std::uint32_t {
  kQualificationInputFailureNone = 0U,
  kQualificationInputFailureGamma = 1U << 0U,
  kQualificationInputFailureSkn = 1U << 1U,
  kQualificationArithmeticFailure = 1U << 2U,
};

struct QualificationRequiredSampleView {
  const platt_windowed::RealDisk106* samples = nullptr;
  std::uint32_t begin = 0U;
  std::uint32_t count = 0U;
  std::int32_t logical_block_delta = 0;
};

// Allocate and initialize a workspace for the exact PT21 source geometry:
// N1=32768, K=23, all published transform error insertions enabled.
// Throws std::runtime_error on any CUDA or initialization failure.
Workspace* create_source_workspace();

// Free every device allocation even when one cudaFree call fails, then throw
// for the first failure.  Passing null is a no-op.  The caller must first
// synchronize every stream that can access the workspace, its borrowed
// inputs, or its borrowed output views.
void destroy_workspace(Workspace* workspace);

// Execute the full two-limb source transform without a host packet boundary.
// Both arguments are device pointers with the shared wire/device layout:
//
//   gamma0:  kBucketCount ComplexDisk106 values
//   sknRows:  kTaylorTerms*kBucketCount ComplexDisk106 values, stage-major
//
// The call enqueues work on `stream` (CUDA's default stream when null).  It
// checks launch status but does not synchronize; callers can fuse a downstream
// interpolation/event kernel with device_samples before synchronizing.  Each
// input disk is checked for finite center limbs and a finite nonnegative
// radius while it is first loaded.  Invalid input fails closed by replacing
// every final sample with the canonical malformed disk described above.
void run_source_window(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream = nullptr);

// Qualification-only alternative to run_source_window.  Each radix-2
// transform executes stages 1..9 inside one 512-value shared-memory tile,
// then executes stages 10+ through the ordinary kernels.  The mathematical
// operations and root/norm table entries are unchanged, but this path is not
// part of a source or production certificate.  Qualification consumers must
// compare all kSourceSampleCount output bytes with run_source_window and fail
// closed on any difference.
void run_source_window_tile9_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream = nullptr);

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1
// Qualification-only whole-transform alternative.  This entry point is
// deliberately absent from the production transform library: it is declared
// and built only in a separate target compiled with
// SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1, --fmad=false, and
// --ftz=false.  It changes only immutable FFT-root multiplications to the
// independently bounded sloppy-DD formula; all other graph operations retain
// the ordinary implementation.  A nonfinite intermediate raises the shared
// failure word and therefore produces canonical malformed output disks.
void run_source_window_sloppy_root_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream = nullptr);

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
// Qualification-only composition of the stages-1..9 shared-memory tile with
// the bounded sloppy-root butterfly.  This is a distinct guarded entry point,
// never selected by run_source_window or exported from the production
// transform archive.  Qualification must establish byte identity with
// run_source_window_sloppy_root_qualification before relying on its existing
// containment and event-replay evidence.
void run_source_window_tile9_sloppy_root_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream = nullptr);

#if defined(SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION == 1
// Qualification-only composition that reads the bit-reversed inputs
// directly into the stages-1..9 shared tile.  It is compiled in a distinct
// archive and never selected by either run_source_window or the settled
// tile9 qualification entry.  Input and output arrays are distinct at all
// five source-transform call sites.
void run_source_window_bitreverse_tile9_sloppy_root_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream);
#endif

inline constexpr std::size_t
    kQualificationTile9SloppyRootStaticSharedBytes = 32'768U;
inline constexpr int kQualificationTile9SloppyRootThreadsPerBlock = 256;

struct QualificationTile9SloppyRootKernelResources {
  int registers_per_thread = 0;
  std::size_t static_shared_bytes = 0U;
  std::size_t local_bytes_per_thread = 0U;
  int maximum_threads_per_block = 0;
  int active_blocks_per_multiprocessor = 0;
};

// Runtime attributes for the actual joint tile kernel in the linked cubin.
// The evidence runner uses these values to reject a resource-infeasible build
// instead of inferring feasibility solely from source declarations.
QualificationTile9SloppyRootKernelResources
tile9_sloppy_root_kernel_resources_qualification();

#if defined(SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION == 1
// Runtime attributes for the actual fused bitreverse+tile9 kernel in the
// linked cubin.  A qualifier must query this entry rather than inheriting
// the settled tile9 kernel's resource report.
QualificationTile9SloppyRootKernelResources
bitreverse_tile9_sloppy_root_kernel_resources_qualification();
#endif
#endif

struct QualificationRootTableView {
  const platt_windowed::ComplexDisk106* roots = nullptr;
  const double* center_norm_upper = nullptr;
  std::uint32_t count = 0U;
};

// Borrowed device view used only by the qualification runner to audit every
// immutable root disk and its directed centre-norm bound exactly.  The view
// has the workspace lifetime and stream-ordering requirements stated above.
QualificationRootTableView device_root_table_qualification(
    const Workspace* workspace);
#endif

// Borrowed device output owned by workspace.  There are exactly
// kSourceSampleCount RealDisk106 values.  The source-required contiguous view
// starts at device_required_samples and has kSourceRequiredCount values.
const platt_windowed::RealDisk106* device_samples(const Workspace* workspace);
const platt_windowed::RealDisk106* device_required_samples(
    const Workspace* workspace);

// Borrowed pointer to the one-word input validation status.  This is exposed
// only so bounded qualification tests can distinguish Gamma from S_k
// forgeries.  It is reset and populated asynchronously on the run's stream;
// establish a CUDA happens-before edge before reading it.
const std::uint32_t* device_input_failure_flags_qualification(
    const Workspace* workspace);

// Return the zero-based beginning of a complete shifted 25,741-sample view.
// Throws std::out_of_range unless every cell lies in the 131,072-sample
// transform.  In the present geometry exactly deltas -2..2 are accepted.
std::uint32_t qualification_required_begin_for_delta(
    std::int32_t logical_block_delta);

// Bounds-checked counterpart to pointer arithmetic on device_samples().
// A null workspace is rejected.  Callers must preserve the returned count
// and delta when labeling qualification evidence.
QualificationRequiredSampleView device_qualification_required_samples(
    const Workspace* workspace, std::int32_t logical_block_delta);

// Exact persistent device allocation, useful for Azure capacity checks.
std::uint64_t workspace_device_bytes(const Workspace* workspace);

}  // namespace sparkinterval::tg::platt_dd_transform

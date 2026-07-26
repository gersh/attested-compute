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

// ---------------------------------------------------------------------------
// Batched, multi-stream execution.
//
// A BatchWorkspace holds `slots` independent transform workspaces, one
// nonblocking CUDA stream per slot, and one device staging pair per slot.  It
// exists to amortize the two fixed costs that dominate a single-window
// invocation on fast hardware:
//
//   * the immutable 32,768-entry MPFR root/constant tables, which cost far
//     more host time to build than one window costs to transform, are built
//     once by slot 0 and borrowed by every other slot;
//   * the per-window kernel sequence of one slot overlaps the sequence of the
//     others, so the low-parallelism stages (the 23-row Gamma ladder and the
//     Taylor accumulation, which occupy only a fraction of the device on
//     their own) run concurrently with another window's transform stages.
//
// Nothing that affects a value is shared.  Each slot owns every scratch
// buffer, its own input-validation word and its own sample array, and runs the
// unmodified run_source_window kernel sequence on its own stream.  A batched
// run is therefore required to be byte-identical to the same windows executed
// one at a time; a consumer that observes any difference must fail the shard.
//
// A slot is single-window at a time: after batch_run_window returns slot s,
// the caller must consume or copy that slot's samples, and establish a CUDA
// happens-before edge on the slot stream, before the round robin returns to s.
// ---------------------------------------------------------------------------

struct BatchWorkspace;

inline constexpr std::uint32_t kMaximumBatchSlots = 64U;

// Allocate `slots` window slots.  Throws std::invalid_argument unless
// 1 <= slots <= kMaximumBatchSlots, and std::runtime_error on CUDA failure.
BatchWorkspace* create_source_batch_workspace(std::uint32_t slots);

// Quiesce every slot stream, then free every device allocation.  Passing null
// is a no-op.
void destroy_batch_workspace(BatchWorkspace* batch);

std::uint32_t batch_slot_count(const BatchWorkspace* batch);
std::uint64_t batch_workspace_device_bytes(const BatchWorkspace* batch);

// Borrowed handles with the batch lifetime.  `slot` must be less than
// batch_slot_count or std::out_of_range is thrown.
cudaStream_t batch_slot_stream(const BatchWorkspace* batch,
                               std::uint32_t slot);
Workspace* batch_slot_workspace(BatchWorkspace* batch, std::uint32_t slot);
platt_windowed::ComplexDisk106* batch_slot_device_gamma(
    BatchWorkspace* batch, std::uint32_t slot);
platt_windowed::ComplexDisk106* batch_slot_device_skn(
    BatchWorkspace* batch, std::uint32_t slot);
const platt_windowed::RealDisk106* batch_slot_device_samples(
    const BatchWorkspace* batch, std::uint32_t slot);
const platt_windowed::RealDisk106* batch_slot_device_required_samples(
    const BatchWorkspace* batch, std::uint32_t slot);
const std::uint32_t* batch_slot_device_input_failure_flags_qualification(
    const BatchWorkspace* batch, std::uint32_t slot);

// Enqueue one window on the next slot in round-robin order and return that
// slot.  Both inputs are device pointers with the layout run_source_window
// documents; they are not owned or retained past the enqueued work.
std::uint32_t batch_run_window(
    BatchWorkspace* batch,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows);

// As above, but first uploads both host arrays into the slot's own device
// staging buffers on the slot stream, so the transfer of one window overlaps
// the transform of the others.  Host memory should be page-locked for the copy
// to be asynchronous.  The host arrays must remain valid until the slot
// stream reaches the copy.
std::uint32_t batch_upload_and_run_window(
    BatchWorkspace* batch,
    const platt_windowed::ComplexDisk106* hostGamma0,
    const platt_windowed::ComplexDisk106* hostSknRows);

void batch_synchronize_slot(BatchWorkspace* batch, std::uint32_t slot);
void batch_synchronize(BatchWorkspace* batch);

}  // namespace sparkinterval::tg::platt_dd_transform

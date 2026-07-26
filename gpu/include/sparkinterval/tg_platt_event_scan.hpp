// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_platt_dd_transform.hpp"

#include <cuda_runtime_api.h>

#include <array>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace sparkinterval::tg::platt_event_scan {

namespace platt_windowed = sparkinterval::tg::platt_windowed;

// The source calls zeros_st on the middle interval and makes two independent
// Turing calls on the flanks.  Keeping these as distinct streams prevents a
// main-window event from being charged to either one-sided Turing integral.
enum class StreamKind : std::uint32_t {
  kLeftFlank = 0U,
  kMain = 1U,
  kRightFlank = 2U,
};

inline constexpr std::uint32_t kStreamCount = 3U;
inline constexpr std::int32_t kRequiredLower = -12'870;
inline constexpr std::int32_t kRequiredUpper = 12'870;
inline constexpr std::int32_t kLeftFlankLower = -12'800;
inline constexpr std::int32_t kLeftFlankUpper = -12'288;
inline constexpr std::int32_t kMainLower = -12'288;
inline constexpr std::int32_t kMainUpper = 12'288;
inline constexpr std::int32_t kRightFlankLower = 12'288;
inline constexpr std::int32_t kRightFlankUpper = 12'800;
inline constexpr std::int32_t kLatticeNumerator = 21;
inline constexpr std::int32_t kLatticeDenominator = 512;

static_assert(platt_dd_transform::kSourceRequiredCount == 25'741U);
static_assert(kRequiredUpper - kRequiredLower + 1 ==
              static_cast<std::int32_t>(
                  platt_dd_transform::kSourceRequiredCount));

// A source-direct sign change.  The event certifies exactly one
// multiplicity slot.  The two weights are integer multiples of 21/512 and
// reproduce the source Nleft_int/Nright_int conservative cell choices.
struct DirectEvent {
  std::int32_t left_sample;
  std::int32_t right_sample;
  std::int32_t source_nleft_units;
  std::int32_t source_nright_units;
  std::uint32_t stream;
  std::uint32_t certified_multiplicity_slots;
};

// The exact stat_pt predicate has fired on a same-sign l/m/r triple.  This is
// only a query for the later adaptive dyadic resolve_stat_point routine.  In
// particular, certified_multiplicity_slots is always zero here.
struct StationaryCandidate {
  std::int32_t left_sample;
  std::int32_t middle_sample;
  std::int32_t right_sample;
  std::int32_t source_nleft_units_per_slot_if_resolved;
  std::int32_t source_nright_units_per_slot_if_resolved;
  std::uint32_t stream;
  std::uint8_t source_positive;
  std::uint8_t strict_stat_pt;
  std::uint8_t requires_adaptive_resolution;
  std::uint8_t certified_multiplicity_slots;
  std::uint8_t multiplicity_slots_if_resolution_succeeds;
  std::uint8_t reserved_zero[3];
};

struct EndpointRecord {
  std::int32_t sample_offset;
  std::uint32_t positive;
  platt_windowed::RealDisk106 disk;
};

struct StreamSummary {
  std::uint32_t stream;
  std::int32_t lower_sample;
  std::int32_t upper_sample;
  std::uint32_t range_sample_count;
  std::uint32_t direct_event_count;
  std::uint32_t stationary_candidate_count;
  std::uint32_t certified_direct_multiplicity_slots;
  std::uint32_t reserved_zero;
  std::int64_t direct_nleft_units;
  std::int64_t direct_nright_units;
  EndpointRecord left_endpoint;
  EndpointRecord right_endpoint;
};

enum FailureFlag : std::uint32_t {
  kFailureNone = 0U,
  kFailureMalformedDisk = 1U << 0U,
  kFailureAmbiguousDisk = 1U << 1U,
  kFailureExactArithmetic = 1U << 2U,
  kFailureDirectOverflow = 1U << 3U,
  kFailureStationaryOverflow = 1U << 4U,
  kFailureInternalGeometry = 1U << 5U,
};

struct ScanStatus {
  std::uint32_t failure_flags;
  std::uint32_t certified_sample_count;
  // Domain-separated SHA-256 Merkle root over the exact input disks/signs,
  // summaries, and compact streams.  Zero unless digest_valid is one.
  std::uint32_t digest_valid;
  std::uint32_t reserved_zero;
  unsigned char artifact_sha256[32];
};

struct Capacities {
  std::array<std::uint32_t, kStreamCount> direct;
  std::array<std::uint32_t, kStreamCount> stationary;
};

inline constexpr Capacities maximum_capacities() {
  return {{{512U, 24'576U, 512U}}, {{510U, 24'574U, 510U}}};
}

// Persistent bounded output/scratch storage.  It can be reused for every
// source block and never owns the transform's required-sample pointer.  The
// mutable workspace is single-stream and nonconcurrent: order scans, output
// reads, and replay captures on one CUDA stream (or with explicit events),
// and quiesce every such access before destruction.
struct Workspace;

Workspace* create_workspace(Capacities capacities = maximum_capacities());
// The caller must synchronize every stream that can still access the
// workspace.  Passing null is a no-op.
void destroy_workspace(Workspace* workspace);

// Enqueue a fail-closed scan on stream.  required_samples must be the device
// pointer returned by platt_dd_transform::device_required_samples or by the
// bounds-checked qualification shifted-view accessor.  Thus the transform
// and scanner can remain device-to-device with no packet boundary.
void scan_source_required_samples(
    Workspace* workspace,
    const platt_windowed::RealDisk106* required_samples,
    cudaStream_t stream = nullptr);

const DirectEvent* device_direct_events(const Workspace* workspace,
                                        StreamKind stream);
const StationaryCandidate* device_stationary_candidates(
    const Workspace* workspace, StreamKind stream);
const StreamSummary* device_stream_summaries(const Workspace* workspace);
const ScanStatus* device_scan_status(const Workspace* workspace);
std::uint64_t workspace_device_bytes(const Workspace* workspace);

struct HostArtifact {
  ScanStatus status{};
  std::array<StreamSummary, kStreamCount> summaries{};
  std::array<std::vector<DirectEvent>, kStreamCount> direct;
  std::array<std::vector<StationaryCandidate>, kStreamCount> stationary;
};

struct ReplayReport {
  bool accepted = false;
  bool device_matches_host = false;
  bool shared_endpoints_agree = false;
  std::string error;
  // Exact host copy used by the independent replay.  Keeping it in the
  // report lets the bounded FLINT junction consume the same bytes whose
  // event Merkle root was checked, instead of accepting an unbound second
  // sample array from its caller.
  std::vector<platt_windowed::RealDisk106> required_samples;
  // Linear seal of the replay-owned samples and ordered stationary arrays.
  // The full scanner Merkle tree has already been recomputed by replay; this
  // detects post-replay mutation without rebuilding that tree a second time.
  std::array<unsigned char, 32> stationary_payload_sha256{};
  HostArtifact artifact;
};

// A bounded pinned-host snapshot of one scanner invocation.  The snapshot
// owns storage for every required sample and the scanner's full configured
// event capacities.  enqueue_replay_capture records device-to-host copies on
// the caller's CUDA stream before the scanner/transform workspaces may be
// reused.  replay_captured waits only for that snapshot and then performs the
// same independent fixed-integer host replay as replay_and_check.
//
// This split is the source-scale hot-path boundary: a producer can keep
// submitting CUDA windows into a bounded ring while a CPU consumer replays
// completed captures in order.  No acceptance check is omitted.
struct ReplayCapture;

ReplayCapture* create_replay_capture(const Workspace* workspace);
void destroy_replay_capture(ReplayCapture* capture);
void enqueue_replay_capture(
    const Workspace* workspace,
    const platt_windowed::RealDisk106* required_samples,
    ReplayCapture* capture, cudaStream_t stream = nullptr);
bool replay_capture_ready(const ReplayCapture* capture);
ReplayReport replay_captured(ReplayCapture* capture);
std::uint64_t replay_capture_pinned_bytes(const ReplayCapture* capture);

// Synchronize stream, download the bounded result, and independently replay
// the exact binary64 DD-disk comparisons with fixed 2176-bit host integers.
// Acceptance requires byte-for-byte event equality, the same SHA-256 Merkle
// root, and agreement of the two explicitly duplicated shared endpoints at
// -12288 and +12288.
ReplayReport replay_and_check(
    const Workspace* workspace,
    const platt_windowed::RealDisk106* required_samples,
    cudaStream_t stream = nullptr);

// Recompute the scanner's domain-separated Merkle root from an explicit host
// sample array and compact artifact.  This is used at the CUDA/FLINT junction
// to detect mutation of samples or candidate ordering after replay.
std::array<unsigned char, 32> recompute_host_artifact_sha256(
    std::span<const platt_windowed::RealDisk106> required_samples,
    const HostArtifact& artifact);

std::array<unsigned char, 32> stationary_payload_sha256(
    std::span<const platt_windowed::RealDisk106> required_samples,
    const HostArtifact& artifact);

static_assert(sizeof(DirectEvent) == 24U);
static_assert(sizeof(StationaryCandidate) == 32U);
static_assert(sizeof(EndpointRecord) == 32U);
static_assert(sizeof(ScanStatus) == 48U);

}  // namespace sparkinterval::tg::platt_event_scan

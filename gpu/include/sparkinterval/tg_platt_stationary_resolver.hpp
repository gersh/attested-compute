// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_platt_windowed.hpp"

#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace sparkinterval::tg::platt_stationary_resolver {

namespace platt_windowed = sparkinterval::tg::platt_windowed;

inline constexpr std::int32_t kRequiredLower = -12'870;
inline constexpr std::int32_t kRequiredUpper = 12'870;
inline constexpr std::uint32_t kRequiredCount = 25'741U;
inline constexpr std::uint32_t kSourcePrecisionBits = 128U;
inline constexpr std::uint32_t kSourcePointsPerSide = 70U;
inline constexpr std::uint32_t kSourceTermsPerQuery = 140U;
inline constexpr std::uint32_t kSourceTraceResolutionLimit = 10'000U;
inline constexpr std::uint32_t kDefaultMaximumDepth = 64U;
inline constexpr std::uint32_t kSourceTraceMaximumBytes = 16U * 1024U * 1024U;
inline constexpr std::uint32_t kMaximumArfDumpBytes = 256U;
inline constexpr std::int32_t kMaximumArfExponentMagnitude = 4096;

inline constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";
inline constexpr char kInterpolationPatchSha256[] =
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3";

static_assert(kRequiredCount ==
              static_cast<std::uint32_t>(kRequiredUpper - kRequiredLower + 1));

enum class StreamKind : std::uint32_t {
  kLeftFlank = 0U,
  kMain = 1U,
  kRightFlank = 2U,
};

// Canonical scanner query.  Queries must be supplied in stream order and then
// increasing left_sample order.  The resolver independently reconstructs the
// complete source stat_pt list and rejects an omitted, duplicate, or extra
// query.
struct Candidate {
  StreamKind stream;
  std::int32_t left_sample;
  std::int32_t right_sample;
  bool source_positive;
};

// A sparse high-precision replacement for one ambiguous DD lattice disk.
// Endpoints use FLINT's canonical arf_dump_str representation.  The resolver
// requires a strict, nonempty subinterval of the original exact DD disk.  It
// never manufactures a refinement from interpolation at the same cardinal
// lattice point.
struct SparseRefinement {
  std::int32_t sample_offset;
  std::string lower_arf_dump;
  std::string upper_arf_dump;
};

struct CanonicalRational {
  std::string numerator;
  std::string denominator;
};

struct CanonicalInterval {
  CanonicalRational lower;
  CanonicalRational upper;
};

// This is field-for-field the stationaryResolution payload in
// platt-pt21-fused-source-trace.schema.json.  Two strict brackets share the
// midpoint and are later charged to one multiplicity-two conservative cell.
struct Resolution {
  StreamKind stream;
  std::int32_t outer_left_sample;
  std::int32_t outer_right_sample;
  CanonicalRational lower_offset;
  CanonicalRational midpoint_offset;
  CanonicalRational upper_offset;
  CanonicalInterval lower_value;
  CanonicalInterval midpoint_value;
  CanonicalInterval upper_value;
  std::uint32_t iterations;
  std::uint32_t interpolation_evaluations;
};

struct PrecisionEndpointAudit {
  CanonicalInterval base_interval;
  CanonicalInterval replay_interval;
  CanonicalInterval retained_hull;
};

// Qualification-only V2 evidence for the precision replay.  The retained
// resolution interval is the outward exact-rational hull of the separately
// recorded base and replay intervals; neither input is discarded.
struct PrecisionReplayAudit {
  StreamKind stream;
  std::int32_t outer_left_sample;
  std::int32_t outer_right_sample;
  std::uint32_t base_precision_bits;
  std::uint32_t replay_precision_bits;
  PrecisionEndpointAudit lower;
  PrecisionEndpointAudit midpoint;
  PrecisionEndpointAudit upper;
};

enum FailureFlag : std::uint64_t {
  kFailureNone = 0U,
  kFailureFlintIdentity = 1ULL << 0U,
  kFailureInputGeometry = 1ULL << 1U,
  kFailureMalformedDisk = 1ULL << 2U,
  kFailureUnrefinedAmbiguousDisk = 1ULL << 3U,
  kFailureRefinementEncoding = 1ULL << 4U,
  kFailureRefinementRange = 1ULL << 5U,
  kFailureRefinementNotSubset = 1ULL << 6U,
  kFailureRefinementNotStrict = 1ULL << 7U,
  kFailureCandidateList = 1ULL << 8U,
  kFailureCandidateCapacity = 1ULL << 9U,
  kFailureInterpolationStencil = 1ULL << 10U,
  kFailureInterpolationSign = 1ULL << 11U,
  kFailureDirection = 1ULL << 12U,
  kFailureDepth = 1ULL << 13U,
  kFailureReplay = 1ULL << 14U,
  kFailureInternal = 1ULL << 15U,
};

struct Options {
  std::uint32_t precision_bits = kSourcePrecisionBits;
  std::uint32_t maximum_depth = kDefaultMaximumDepth;
  std::uint32_t maximum_candidates = kSourceTraceResolutionLimit;
  std::uint32_t maximum_refinements = kSourceTraceResolutionLimit;
  std::uint32_t replay_extra_precision_bits = 64U;
  std::uint32_t maximum_trace_bytes = kSourceTraceMaximumBytes;
  bool require_flint_3_6_0 = true;
  bool retain_precision_hull_audit = false;
};

struct Report {
  bool accepted = false;
  bool replay_accepted = false;
  std::uint64_t failure_flags = kFailureNone;
  std::uint32_t ambiguous_input_disks = 0U;
  std::uint32_t refinements_applied = 0U;
  std::uint32_t candidate_count = 0U;
  std::uint64_t interpolation_evaluations = 0U;
  std::string input_sha256;
  std::string resolution_sha256;
  std::string stationary_resolutions_json;
  std::string canonical_trace_json;
  std::string error;
  std::vector<Resolution> resolutions;
  std::vector<PrecisionReplayAudit> precision_replay_audit;
};

// Resolve every source stationary query for one complete required region.
// `samples` is bounded to exactly 25,741 DD disks.  Refinements and candidates
// are bounded by Options.  The function returns an unsuccessful report on any
// ambiguity; it does not accept a partial prefix of the query list.
Report resolve_block(
    std::span<const platt_windowed::RealDisk106> samples,
    std::span<const Candidate> candidates,
    std::span<const SparseRefinement> refinements = {},
    Options options = {});

const char* stream_name(StreamKind stream);

}  // namespace sparkinterval::tg::platt_stationary_resolver

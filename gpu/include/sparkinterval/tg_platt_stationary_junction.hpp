// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// Authenticated finite junction between PT21EVT1 and the FLINT
// Gaussian--sinc stationary resolver.
//
// PT21STJ1 is deliberately nonterminal.  It proves only that the exact
// scanner payload committed by PT21EVT1 was passed to the pinned finite
// resolver and that every candidate produced one multiplicity-two resolution.
// It has no Turing fields and no Hardy-Z, FLINT-to-Mathlib, or analytic
// realization flag.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_event_record.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"
#include "sparkinterval/tg_platt_stationary_resolver.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace sparkinterval::tg::platt_stationary_junction {

namespace per = sparkinterval::tg::platt_event_record;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace psr = sparkinterval::tg::platt_stationary_resolver;

inline constexpr std::uint32_t kVersion = 1U;
inline constexpr std::size_t kRecordBytes = 400U;
inline constexpr std::size_t kRecordDigestOffset = 368U;
inline constexpr std::uint32_t kFlintRelease = 30'600U;
inline constexpr char kRecordMagic[] = "PT21STJ1";
inline constexpr char kRecordDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-junction-record/v1\0";
inline constexpr char kCandidateDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-candidates/v1\0";
inline constexpr char kRefinementDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-refinements/v1\0";
inline constexpr char kResolverInputDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-input/v1\0";

using RawRecord = std::array<unsigned char, kRecordBytes>;

class JunctionError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

enum FailureFlag : std::uint64_t {
  kFailureNone = 0U,
  kFailureEventRecord = 1ULL << 0U,
  kFailureReplay = 1ULL << 1U,
  kFailureEventRoot = 1ULL << 2U,
  kFailureCandidatePayload = 1ULL << 3U,
  kFailureResolver = 1ULL << 4U,
  kFailureResolverDigest = 1ULL << 5U,
  kFailureIdentity = 1ULL << 6U,
  kFailureInternal = 1ULL << 7U,
};

struct IdentityPins {
  Sha256Digest resolver_sha256{};
  Sha256Digest flint_sha256{};
};

struct RecordValues {
  std::uint64_t block = 0U;
  std::uint64_t failure_flags = 0U;
  std::uint32_t candidate_count = 0U;
  std::uint32_t resolution_count = 0U;
  std::uint32_t ambiguous_input_count = 0U;
  std::uint32_t refinement_count = 0U;
  std::uint32_t resolved_multiplicity_slots = 0U;
  std::uint32_t precision_bits = 0U;
  std::uint32_t maximum_depth = 0U;
  std::uint32_t replay_extra_precision_bits = 0U;
  std::uint32_t flint_release = 0U;
  std::uint32_t semantic_realization_flags = 0U;
  std::uint32_t resolver_replay_accepted = 0U;
  std::uint32_t higher_precision_containment_complete = 0U;
  Sha256Digest event_record_sha256{};
  Sha256Digest event_artifact_sha256{};
  Sha256Digest candidate_list_sha256{};
  Sha256Digest resolver_input_sha256{};
  Sha256Digest refinement_trace_sha256{};
  Sha256Digest resolution_sha256{};
  Sha256Digest stationary_trace_sha256{};
  Sha256Digest resolver_sha256{};
  Sha256Digest flint_sha256{};
};

struct Result {
  bool accepted = false;
  std::uint64_t failure_flags = kFailureNone;
  std::string error;
  RawRecord record{};
  psr::Report resolver_report;
};

void validate_record_values(const RecordValues& values);
RawRecord encode_record(const RecordValues& values);
RecordValues decode_record(const RawRecord& raw);

Sha256Digest candidate_list_sha256(
    std::span<const pes::StationaryCandidate> candidates);
Sha256Digest refinement_trace_sha256(
    std::span<const psr::SparseRefinement> refinements);
Sha256Digest resolver_input_sha256(
    std::span<const pes::platt_windowed::RealDisk106> samples,
    std::span<const psr::Candidate> candidates,
    std::span<const psr::SparseRefinement> refinements);

// Resolve one independently replayed scanner block.  The event record, replay
// root, exact candidate arrays, and replay-owned sample bytes must all agree
// before FLINT is called.  Any mismatch returns no accepted record.
Result resolve_replayed_block(
    std::uint64_t block,
    const per::RawRecord& event_record,
    const pes::ReplayReport& replay,
    std::span<const psr::SparseRefinement> refinements,
    const IdentityPins& identities,
    psr::Options options = {});

}  // namespace sparkinterval::tg::platt_stationary_junction

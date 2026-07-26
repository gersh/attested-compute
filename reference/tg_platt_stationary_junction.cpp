// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_stationary_junction.hpp"

#include <algorithm>
#include <bit>
#include <cstring>
#include <limits>
#include <string_view>
#include <utility>

namespace sparkinterval::tg::platt_stationary_junction {
namespace {

class JunctionFailure : public JunctionError {
 public:
  JunctionFailure(std::uint64_t flag, std::string message)
      : JunctionError(std::move(message)), flag_(flag) {}
  std::uint64_t flag() const { return flag_; }

 private:
  std::uint64_t flag_;
};

[[noreturn]] void reject(std::uint64_t flag, const std::string& message) {
  throw JunctionFailure(flag, message);
}

bool digest_zero(const Sha256Digest& digest) {
  return std::all_of(digest.begin(), digest.end(),
                     [](unsigned char value) { return value == 0U; });
}

void append_u32(std::vector<unsigned char>* bytes, std::uint32_t value) {
  const std::size_t offset = bytes->size();
  bytes->resize(offset + 4U);
  per::store_u32(bytes->data() + offset, value);
}

void append_i32(std::vector<unsigned char>* bytes, std::int32_t value) {
  append_u32(bytes, static_cast<std::uint32_t>(value));
}

void append_u64(std::vector<unsigned char>* bytes, std::uint64_t value) {
  const std::size_t offset = bytes->size();
  bytes->resize(offset + 8U);
  per::store_u64(bytes->data() + offset, value);
}

void append_string(std::vector<unsigned char>* bytes,
                   std::string_view value) {
  if (value.size() > std::numeric_limits<std::uint32_t>::max()) {
    reject(kFailureCandidatePayload,
           "stationary refinement string exceeds uint32");
  }
  append_u32(bytes, static_cast<std::uint32_t>(value.size()));
  bytes->insert(bytes->end(), value.begin(), value.end());
}

Sha256Digest parse_lower_hex(std::string_view text, const char* label) {
  if (text.size() != 64U) {
    reject(kFailureResolverDigest,
           std::string(label) + " is not a lowercase SHA-256");
  }
  auto nibble = [label](char value) -> unsigned char {
    if (value >= '0' && value <= '9') {
      return static_cast<unsigned char>(value - '0');
    }
    if (value >= 'a' && value <= 'f') {
      return static_cast<unsigned char>(value - 'a' + 10);
    }
    reject(kFailureResolverDigest,
           std::string(label) + " is not a lowercase SHA-256");
  };
  Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    result[index] = static_cast<unsigned char>(
        (nibble(text[2U * index]) << 4U) |
        nibble(text[2U * index + 1U]));
  }
  return result;
}

std::pair<std::int32_t, std::int32_t> stream_range(
    std::uint32_t stream) {
  if (stream >= pes::kStreamCount) {
    reject(kFailureCandidatePayload,
           "stationary candidate stream is outside 0..2");
  }
  constexpr std::int32_t lower[3] = {-12'800, -12'288, 12'288};
  constexpr std::int32_t upper[3] = {-12'288, 12'288, 12'800};
  return {lower[stream], upper[stream]};
}

void validate_candidate(const pes::StationaryCandidate& candidate,
                        std::uint32_t expected_stream) {
  const auto [lower, upper] = stream_range(expected_stream);
  if (candidate.stream != expected_stream ||
      candidate.left_sample < lower ||
      candidate.left_sample > upper - 2 ||
      candidate.middle_sample != candidate.left_sample + 1 ||
      candidate.right_sample != candidate.left_sample + 2) {
    reject(kFailureCandidatePayload,
           "stationary candidate geometry differs");
  }
  const std::int32_t edge = candidate.left_sample - lower;
  const std::int32_t edge_count = upper - lower;
  if (candidate.source_nleft_units_per_slot_if_resolved != -edge ||
      candidate.source_nright_units_per_slot_if_resolved !=
          edge_count - edge - 2 ||
      candidate.source_positive > 1U ||
      candidate.strict_stat_pt != 1U ||
      candidate.requires_adaptive_resolution != 1U ||
      candidate.certified_multiplicity_slots != 0U ||
      candidate.multiplicity_slots_if_resolution_succeeds != 2U ||
      candidate.reserved_zero[0] != 0U ||
      candidate.reserved_zero[1] != 0U ||
      candidate.reserved_zero[2] != 0U) {
    reject(kFailureCandidatePayload,
           "stationary candidate finite contract differs");
  }
}

std::vector<pes::StationaryCandidate> flatten_candidates(
    const pes::HostArtifact& artifact) {
  std::vector<pes::StationaryCandidate> result;
  std::size_t count = 0U;
  for (const auto& stream : artifact.stationary) count += stream.size();
  if (count > psr::kSourceTraceResolutionLimit) {
    reject(kFailureCandidatePayload,
           "stationary candidate payload exceeds resolver cap");
  }
  result.reserve(count);
  for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    for (const pes::StationaryCandidate& candidate :
         artifact.stationary[stream]) {
      validate_candidate(candidate, stream);
      result.push_back(candidate);
    }
  }
  return result;
}

std::vector<psr::Candidate> resolver_candidates(
    std::span<const pes::StationaryCandidate> candidates) {
  std::vector<psr::Candidate> result;
  result.reserve(candidates.size());
  for (const pes::StationaryCandidate& candidate : candidates) {
    result.push_back({
        static_cast<psr::StreamKind>(candidate.stream),
        candidate.left_sample,
        candidate.right_sample,
        candidate.source_positive != 0U,
    });
  }
  return result;
}

void validate_event_link(const per::BlockValues& event,
                         const pes::ReplayReport& replay) {
  if (!replay.accepted || !replay.device_matches_host ||
      !replay.shared_endpoints_agree ||
      replay.required_samples.size() != psr::kRequiredCount ||
      replay.artifact.status.failure_flags != 0U ||
      replay.artifact.status.certified_sample_count != psr::kRequiredCount ||
      replay.artifact.status.digest_valid != 1U) {
    reject(kFailureReplay,
           "event scanner replay is not completely accepted");
  }
  Sha256Digest replay_root{};
  std::memcpy(replay_root.data(),
              replay.artifact.status.artifact_sha256,
              replay_root.size());
  if (replay_root != event.event_artifact_sha256) {
    reject(kFailureEventRoot,
           "PT21EVT1 root differs from scanner replay root");
  }
  Sha256Digest payload_seal{};
  try {
    payload_seal = pes::stationary_payload_sha256(
        replay.required_samples, replay.artifact);
  } catch (const std::exception& error) {
    reject(kFailureEventRoot,
           "cannot recompute stationary replay seal: " +
               std::string(error.what()));
  }
  if (digest_zero(replay.stationary_payload_sha256) ||
      payload_seal != replay.stationary_payload_sha256) {
    reject(kFailureEventRoot,
           "scanner payload changed after independent replay");
  }
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    const pes::StreamSummary& summary = replay.artifact.summaries[stream];
    if (event.direct_event_count[stream] !=
            replay.artifact.direct[stream].size() ||
        event.direct_event_count[stream] != summary.direct_event_count ||
        event.stationary_candidate_count[stream] !=
            replay.artifact.stationary[stream].size() ||
        event.stationary_candidate_count[stream] !=
            summary.stationary_candidate_count ||
        event.certified_direct_slots[stream] !=
            summary.certified_direct_multiplicity_slots ||
        event.direct_nleft_units[stream] != summary.direct_nleft_units ||
        event.direct_nright_units[stream] != summary.direct_nright_units) {
      reject(kFailureCandidatePayload,
             "PT21EVT1 counts or weights differ from scanner payload");
    }
  }
}

}  // namespace

void validate_record_values(const RecordValues& values) {
  if (values.block >= per::kSourceBlockCount ||
      values.failure_flags != 0U ||
      values.candidate_count > psr::kSourceTraceResolutionLimit ||
      values.resolution_count != values.candidate_count ||
      values.ambiguous_input_count != values.refinement_count ||
      values.ambiguous_input_count != 0U ||
      values.refinement_count != 0U ||
      values.resolved_multiplicity_slots !=
          2U * values.candidate_count ||
      values.precision_bits != psr::kSourcePrecisionBits ||
      values.maximum_depth == 0U || values.maximum_depth > 96U ||
      values.replay_extra_precision_bits < 32U ||
      values.replay_extra_precision_bits > 512U ||
      values.flint_release != kFlintRelease ||
      values.semantic_realization_flags != 0U ||
      values.resolver_replay_accepted != 1U ||
      values.higher_precision_containment_complete != 1U) {
    throw JunctionError("stationary junction finite fields differ");
  }
  const std::array<const Sha256Digest*, 9> digests = {
      &values.event_record_sha256,
      &values.event_artifact_sha256,
      &values.candidate_list_sha256,
      &values.resolver_input_sha256,
      &values.refinement_trace_sha256,
      &values.resolution_sha256,
      &values.stationary_trace_sha256,
      &values.resolver_sha256,
      &values.flint_sha256,
  };
  if (std::any_of(digests.begin(), digests.end(),
                  [](const Sha256Digest* digest) {
                    return digest_zero(*digest);
                  })) {
    throw JunctionError(
        "stationary junction contains a zero identity or payload digest");
  }
}

RawRecord encode_record(const RecordValues& values) {
  validate_record_values(values);
  RawRecord raw{};
  std::memcpy(raw.data(), kRecordMagic, 8U);
  per::store_u32(raw.data() + 8U, kVersion);
  per::store_u32(raw.data() + 12U, kRecordBytes);
  per::store_u64(raw.data() + 16U, values.block);
  per::store_u64(raw.data() + 24U, values.failure_flags);
  per::store_u32(raw.data() + 32U, values.candidate_count);
  per::store_u32(raw.data() + 36U, values.resolution_count);
  per::store_u32(raw.data() + 40U, values.ambiguous_input_count);
  per::store_u32(raw.data() + 44U, values.refinement_count);
  per::store_u32(raw.data() + 48U, values.resolved_multiplicity_slots);
  per::store_u32(raw.data() + 52U, values.precision_bits);
  per::store_u32(raw.data() + 56U, values.maximum_depth);
  per::store_u32(raw.data() + 60U,
                 values.replay_extra_precision_bits);
  per::store_u32(raw.data() + 64U, values.flint_release);
  per::store_u32(raw.data() + 68U,
                 values.semantic_realization_flags);
  per::store_u32(raw.data() + 72U,
                 values.resolver_replay_accepted);
  per::store_u32(raw.data() + 76U,
                 values.higher_precision_containment_complete);
  const std::array<const Sha256Digest*, 9> digests = {
      &values.event_record_sha256,
      &values.event_artifact_sha256,
      &values.candidate_list_sha256,
      &values.resolver_input_sha256,
      &values.refinement_trace_sha256,
      &values.resolution_sha256,
      &values.stationary_trace_sha256,
      &values.resolver_sha256,
      &values.flint_sha256,
  };
  for (std::size_t index = 0U; index < digests.size(); ++index) {
    std::memcpy(raw.data() + 80U + index * 32U,
                digests[index]->data(), 32U);
  }
  const Sha256Digest digest =
      per::domain_hash(kRecordDomain, raw.data(), kRecordDigestOffset);
  std::memcpy(raw.data() + kRecordDigestOffset,
              digest.data(), digest.size());
  return raw;
}

RecordValues decode_record(const RawRecord& raw) {
  if (std::memcmp(raw.data(), kRecordMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != kRecordBytes) {
    throw JunctionError("stationary junction fixed record fields differ");
  }
  const Sha256Digest expected =
      per::domain_hash(kRecordDomain, raw.data(), kRecordDigestOffset);
  if (per::digest_at(raw.data() + kRecordDigestOffset) != expected) {
    throw JunctionError("stationary junction record digest differs");
  }
  RecordValues values;
  values.block = per::load_u64(raw.data() + 16U);
  values.failure_flags = per::load_u64(raw.data() + 24U);
  values.candidate_count = per::load_u32(raw.data() + 32U);
  values.resolution_count = per::load_u32(raw.data() + 36U);
  values.ambiguous_input_count = per::load_u32(raw.data() + 40U);
  values.refinement_count = per::load_u32(raw.data() + 44U);
  values.resolved_multiplicity_slots =
      per::load_u32(raw.data() + 48U);
  values.precision_bits = per::load_u32(raw.data() + 52U);
  values.maximum_depth = per::load_u32(raw.data() + 56U);
  values.replay_extra_precision_bits =
      per::load_u32(raw.data() + 60U);
  values.flint_release = per::load_u32(raw.data() + 64U);
  values.semantic_realization_flags =
      per::load_u32(raw.data() + 68U);
  values.resolver_replay_accepted =
      per::load_u32(raw.data() + 72U);
  values.higher_precision_containment_complete =
      per::load_u32(raw.data() + 76U);
  std::array<Sha256Digest*, 9> digests = {
      &values.event_record_sha256,
      &values.event_artifact_sha256,
      &values.candidate_list_sha256,
      &values.resolver_input_sha256,
      &values.refinement_trace_sha256,
      &values.resolution_sha256,
      &values.stationary_trace_sha256,
      &values.resolver_sha256,
      &values.flint_sha256,
  };
  for (std::size_t index = 0U; index < digests.size(); ++index) {
    *digests[index] = per::digest_at(raw.data() + 80U + index * 32U);
  }
  validate_record_values(values);
  return values;
}

Sha256Digest candidate_list_sha256(
    std::span<const pes::StationaryCandidate> candidates) {
  std::vector<unsigned char> frame;
  frame.reserve(4U + candidates.size() * 44U);
  append_u32(&frame, static_cast<std::uint32_t>(candidates.size()));
  for (const pes::StationaryCandidate& candidate : candidates) {
    append_u32(&frame, candidate.stream);
    append_i32(&frame, candidate.left_sample);
    append_i32(&frame, candidate.middle_sample);
    append_i32(&frame, candidate.right_sample);
    append_i32(
        &frame, candidate.source_nleft_units_per_slot_if_resolved);
    append_i32(
        &frame, candidate.source_nright_units_per_slot_if_resolved);
    append_u32(&frame, candidate.source_positive);
    append_u32(&frame, candidate.strict_stat_pt);
    append_u32(&frame, candidate.requires_adaptive_resolution);
    append_u32(&frame, candidate.certified_multiplicity_slots);
    append_u32(
        &frame, candidate.multiplicity_slots_if_resolution_succeeds);
  }
  return per::domain_hash(
      kCandidateDomain, frame.data(), frame.size());
}

Sha256Digest refinement_trace_sha256(
    std::span<const psr::SparseRefinement> refinements) {
  std::vector<unsigned char> frame;
  frame.reserve(4U + refinements.size() * 96U);
  append_u32(&frame, static_cast<std::uint32_t>(refinements.size()));
  for (const psr::SparseRefinement& refinement : refinements) {
    append_i32(&frame, refinement.sample_offset);
    append_string(&frame, refinement.lower_arf_dump);
    append_string(&frame, refinement.upper_arf_dump);
  }
  return per::domain_hash(
      kRefinementDomain, frame.data(), frame.size());
}

Sha256Digest resolver_input_sha256(
    std::span<const pes::platt_windowed::RealDisk106> samples,
    std::span<const psr::Candidate> candidates,
    std::span<const psr::SparseRefinement> refinements) {
  std::vector<unsigned char> frame;
  frame.reserve(samples.size() * 24U + candidates.size() * 16U +
                refinements.size() * 96U + 64U);
  append_u32(&frame, static_cast<std::uint32_t>(samples.size()));
  for (const auto& sample : samples) {
    append_u64(&frame, std::bit_cast<std::uint64_t>(sample.center.hi));
    append_u64(&frame, std::bit_cast<std::uint64_t>(sample.center.lo));
    append_u64(&frame, std::bit_cast<std::uint64_t>(sample.radius));
  }
  append_u32(&frame, static_cast<std::uint32_t>(candidates.size()));
  for (const psr::Candidate& candidate : candidates) {
    append_u32(&frame, static_cast<std::uint32_t>(candidate.stream));
    append_i32(&frame, candidate.left_sample);
    append_i32(&frame, candidate.right_sample);
    append_u32(&frame, candidate.source_positive ? 1U : 0U);
  }
  append_u32(&frame, static_cast<std::uint32_t>(refinements.size()));
  for (const psr::SparseRefinement& refinement : refinements) {
    append_i32(&frame, refinement.sample_offset);
    append_string(&frame, refinement.lower_arf_dump);
    append_string(&frame, refinement.upper_arf_dump);
  }
  return per::domain_hash(
      kResolverInputDomain, frame.data(), frame.size());
}

Result resolve_replayed_block(
    std::uint64_t block,
    const per::RawRecord& event_record,
    const pes::ReplayReport& replay,
    std::span<const psr::SparseRefinement> refinements,
    const IdentityPins& identities,
    psr::Options options) {
  Result result;
  try {
    per::BlockValues event;
    try {
      event = per::decode_record(event_record, block);
    } catch (const std::exception& error) {
      reject(kFailureEventRecord, error.what());
    }
    validate_event_link(event, replay);
    const std::vector<pes::StationaryCandidate> scanner_candidates =
        flatten_candidates(replay.artifact);
    if (scanner_candidates.size() != event.unresolved_stationary_count) {
      reject(kFailureCandidatePayload,
             "stationary candidate total differs from PT21EVT1");
    }
    const std::vector<psr::Candidate> candidates =
        resolver_candidates(scanner_candidates);
    if (!refinements.empty()) {
      reject(kFailureCandidatePayload,
             "PT21STJ1 v1 requires an event-scan rerun before accepting "
             "a sparse refinement");
    }
    if (digest_zero(identities.resolver_sha256) ||
        digest_zero(identities.flint_sha256)) {
      reject(kFailureIdentity,
             "resolver and FLINT identities must be nonzero");
    }
    result.resolver_report = psr::resolve_block(
        replay.required_samples, candidates, refinements, options);
    if (!result.resolver_report.accepted ||
        !result.resolver_report.replay_accepted ||
        result.resolver_report.failure_flags != 0U ||
        result.resolver_report.candidate_count != candidates.size() ||
        result.resolver_report.resolutions.size() != candidates.size() ||
        result.resolver_report.ambiguous_input_disks !=
            refinements.size() ||
        result.resolver_report.refinements_applied !=
            refinements.size()) {
      reject(kFailureResolver,
             "FLINT stationary resolver did not accept the complete payload");
    }
    const Sha256Digest input_digest = resolver_input_sha256(
        replay.required_samples, candidates, refinements);
    if (parse_lower_hex(result.resolver_report.input_sha256,
                        "resolver input digest") != input_digest) {
      reject(kFailureResolverDigest,
             "independent resolver input digest differs");
    }
    RecordValues values;
    values.block = block;
    values.candidate_count =
        static_cast<std::uint32_t>(candidates.size());
    values.resolution_count =
        static_cast<std::uint32_t>(
            result.resolver_report.resolutions.size());
    values.ambiguous_input_count =
        result.resolver_report.ambiguous_input_disks;
    values.refinement_count =
        static_cast<std::uint32_t>(refinements.size());
    values.resolved_multiplicity_slots =
        2U * values.resolution_count;
    values.precision_bits = options.precision_bits;
    values.maximum_depth = options.maximum_depth;
    values.replay_extra_precision_bits =
        options.replay_extra_precision_bits;
    values.flint_release = kFlintRelease;
    values.resolver_replay_accepted = 1U;
    values.higher_precision_containment_complete = 1U;
    values.event_record_sha256 =
        per::digest_at(event_record.data() + per::kRecordDigestOffset);
    values.event_artifact_sha256 = event.event_artifact_sha256;
    values.candidate_list_sha256 =
        candidate_list_sha256(scanner_candidates);
    values.resolver_input_sha256 = input_digest;
    values.refinement_trace_sha256 =
        refinement_trace_sha256(refinements);
    values.resolution_sha256 = parse_lower_hex(
        result.resolver_report.resolution_sha256,
        "stationary resolution digest");
    values.stationary_trace_sha256 = sha256(
        result.resolver_report.canonical_trace_json.data(),
        result.resolver_report.canonical_trace_json.size());
    values.resolver_sha256 = identities.resolver_sha256;
    values.flint_sha256 = identities.flint_sha256;
    result.record = encode_record(values);
    result.accepted = true;
  } catch (const JunctionFailure& failure) {
    result.failure_flags |= failure.flag();
    result.error = failure.what();
  } catch (const std::exception& error) {
    result.failure_flags |= kFailureInternal;
    result.error = error.what();
  } catch (...) {
    result.failure_flags |= kFailureInternal;
    result.error = "unknown stationary junction failure";
  }
  if (!result.accepted) result.record.fill(0U);
  return result;
}

}  // namespace sparkinterval::tg::platt_stationary_junction

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded equivalence KAT for the qualification-only inline PT21 junction.
//
// The inline side uses enqueue_replay_capture -> replay_captured -> the
// existing resolve_replayed_block API, exactly as the fused worker does.  The
// comparison side uses the pre-existing standalone replay_and_check junction
// path.  Both run on one explicitly synthetic block-zero fixture; this file
// makes no source-scale or analytic claim.

#include "sparkinterval/tg_platt_inline_stationary_stream.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace per = sparkinterval::tg::platt_event_record;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pis = sparkinterval::tg::platt_inline_stationary_stream;
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace psr = sparkinterval::tg::platt_stationary_resolver;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

void check_cuda(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

std::uint32_t parse_iterations(int argc, char** argv) {
  std::uint32_t result = 3U;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    constexpr std::string_view prefix = "--iterations=";
    if (!argument.starts_with(prefix)) {
      throw std::invalid_argument("usage: [--iterations=N]");
    }
    const std::string_view text = argument.substr(prefix.size());
    std::uint64_t value = 0U;
    const auto parsed =
        std::from_chars(text.data(), text.data() + text.size(), value);
    if (parsed.ec != std::errc{} ||
        parsed.ptr != text.data() + text.size() || value == 0U ||
        value > 100U) {
      throw std::invalid_argument("--iterations is outside 1..100");
    }
    result = static_cast<std::uint32_t>(value);
  }
  return result;
}

std::size_t at(std::int32_t offset) {
  return static_cast<std::size_t>(offset - pes::kRequiredLower);
}

std::vector<pw::RealDisk106> fixture() {
  // Exactly the standalone junction's synthetic Turing-closure fixture:
  // 3,465 direct transitions and two main-stream stationary candidates.
  std::vector<pw::RealDisk106> samples(
      sparkinterval::tg::platt_dd_transform::kSourceRequiredCount);
  const double radius = std::ldexp(1.0, -80);
  bool positive = true;
  for (std::int32_t offset = pes::kRequiredLower;
       offset <= pes::kRequiredUpper; ++offset) {
    if (offset > pes::kRequiredLower) {
      const std::int32_t boundary = offset - 1;
      if (boundary == 2 || boundary == 3 || boundary == 12 ||
          boundary == 13 ||
          (boundary >= 100 && boundary <= 3'560)) {
        positive = !positive;
      }
    }
    samples[at(offset)] = {
        {positive ? 3.0 : -3.0, 0.0}, radius};
  }
  for (const std::int32_t left : {0, 10}) {
    samples[at(left)] = {{3.0, 0.0}, radius};
    samples[at(left + 1)] = {{1.0, 0.0}, radius};
    samples[at(left + 2)] = {{3.0, 0.0}, radius};
    samples[at(left + 3)] = {{-100.0, 0.0}, radius};
  }
  return samples;
}

per::BlockValues event_values(std::uint64_t block,
                              const pes::ReplayReport& replay) {
  per::BlockValues values;
  values.block = block;
  values.failure_flags = replay.artifact.status.failure_flags;
  values.certified_sample_count =
      replay.artifact.status.certified_sample_count;
  values.digest_valid = replay.artifact.status.digest_valid;
  std::copy_n(replay.artifact.status.artifact_sha256, 32U,
              values.event_artifact_sha256.begin());
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    const pes::StreamSummary& summary = replay.artifact.summaries[stream];
    values.direct_event_count[stream] = summary.direct_event_count;
    values.stationary_candidate_count[stream] =
        summary.stationary_candidate_count;
    values.certified_direct_slots[stream] =
        summary.certified_direct_multiplicity_slots;
    values.unresolved_stationary_count +=
        summary.stationary_candidate_count;
    values.direct_nleft_units[stream] = summary.direct_nleft_units;
    values.direct_nright_units[stream] = summary.direct_nright_units;
  }
  return values;
}

sparkinterval::Sha256Digest repeated_digest(unsigned char value) {
  sparkinterval::Sha256Digest result{};
  result.fill(value);
  return result;
}

std::string hex(std::span<const unsigned char> raw) {
  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (const unsigned char byte : raw) {
    output << std::setw(2) << static_cast<unsigned int>(byte);
  }
  return output.str();
}

std::string hex(std::string_view raw) {
  return hex(std::span<const unsigned char>(
      reinterpret_cast<const unsigned char*>(raw.data()), raw.size()));
}

template <typename Operation>
bool rejects(Operation&& operation) {
  try {
    operation();
    return false;
  } catch (...) {
    return true;
  }
}

int run(int argc, char** argv) {
  const std::uint32_t iterations = parse_iterations(argc, argv);
  const std::vector<pw::RealDisk106> samples = fixture();
  pw::RealDisk106* device_samples = nullptr;
  pes::Workspace* workspace = nullptr;
  pes::ReplayCapture* capture = nullptr;
  try {
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&device_samples),
                          samples.size() * sizeof(samples[0])),
               "allocate inline fixture");
    check_cuda(cudaMemcpy(device_samples, samples.data(),
                          samples.size() * sizeof(samples[0]),
                          cudaMemcpyHostToDevice),
               "copy inline fixture");
    workspace = pes::create_workspace();
    capture = pes::create_replay_capture(workspace);

    pes::scan_source_required_samples(workspace, device_samples);
    pes::enqueue_replay_capture(
        workspace, device_samples, capture);
    const pes::ReplayReport inline_replay =
        pes::replay_captured(capture);
    if (!inline_replay.accepted) {
      throw std::runtime_error(
          "inline replay-capture fixture was rejected");
    }
    const per::RawRecord inline_event =
        per::encode_record(event_values(0U, inline_replay));

    // This is the existing standalone junction path used by
    // sparkinterval-tg-platt-stationary-junction-benchmark.
    pes::scan_source_required_samples(workspace, device_samples);
    const pes::ReplayReport standalone_replay =
        pes::replay_and_check(workspace, device_samples);
    if (!standalone_replay.accepted) {
      throw std::runtime_error(
          "standalone replay fixture was rejected");
    }
    const per::RawRecord standalone_event =
        per::encode_record(event_values(0U, standalone_replay));

    const psj::IdentityPins identities{
        .resolver_sha256 = repeated_digest(0xa5U),
        .flint_sha256 = repeated_digest(0x5aU),
    };
    psr::Options resolver_options;
    resolver_options.retain_precision_hull_audit = true;
    std::vector<pw::RealDisk106> zero_candidate_samples(
        samples.size(), {{3.0, 0.0}, std::ldexp(1.0, -80)});
    const psr::Report zero_candidate_report = psr::resolve_block(
        zero_candidate_samples, {}, {}, resolver_options);
    if (!zero_candidate_report.accepted ||
        !zero_candidate_report.precision_replay_audit.empty()) {
      throw std::runtime_error(
          "zero-candidate V2 trace sizing fixture was rejected");
    }
    const psj::Result standalone = psj::resolve_replayed_block(
        0U, standalone_event, standalone_replay, {}, identities,
        resolver_options);
    if (!standalone.accepted || standalone.failure_flags != 0U) {
      throw std::runtime_error(
          "standalone stationary junction fixture was rejected");
    }

    psj::Result inline_result;
    const auto started = std::chrono::steady_clock::now();
    for (std::uint32_t iteration = 0U; iteration < iterations;
         ++iteration) {
      inline_result = psj::resolve_replayed_block(
          0U, inline_event, inline_replay, {}, identities,
          resolver_options);
      if (!inline_result.accepted ||
          inline_result.failure_flags != 0U) {
        throw std::runtime_error(
            "inline stationary junction fixture was rejected");
      }
    }
    const double seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();

    const bool standalone_byte_identity =
        inline_event == standalone_event &&
        inline_result.record == standalone.record &&
        inline_result.resolver_report.canonical_trace_json ==
            standalone.resolver_report.canonical_trace_json;
    if (!standalone_byte_identity) {
      throw std::runtime_error(
          "inline and standalone junction bytes differ");
    }

    const pis::HeaderValues header_values{
        .first_block = 0U,
        .block_count = 1U,
        .gamma_stream_sha256 = repeated_digest(0x11U),
        .producer_sha256 = repeated_digest(0xaaU),
        .resolver_sha256 = identities.resolver_sha256,
        .flint_sha256 = identities.flint_sha256,
    };
    const pis::RawHeader header = pis::encode_header(header_values);
    pis::decode_header(header, &header_values);
    std::vector<unsigned char> frame = pis::encode_frame(
        0U, inline_event, inline_result.record,
        inline_result.resolver_report.canonical_trace_json);
    const pis::DecodedFrame decoded = pis::decode_frame(frame, 0U);
    if (decoded.event_record != inline_event ||
        decoded.junction_record != inline_result.record ||
        decoded.stationary_trace !=
            inline_result.resolver_report.canonical_trace_json) {
      throw std::runtime_error(
          "inline frame canonical roundtrip differs");
    }
    const sparkinterval::Sha256Digest frame_stream_sha256 =
        sparkinterval::sha256(frame.data(), frame.size());
    const pis::FooterValues footer_values{
        .first_block = 0U,
        .block_count = 1U,
        .total_event_records = 1U,
        .total_junction_records = 1U,
        .total_trace_bytes =
            inline_result.resolver_report.canonical_trace_json.size(),
        .frame_stream_sha256 = frame_stream_sha256,
        .header_sha256 = per::digest_at(
            header.data() + pis::kHeaderDigestOffset),
        .gamma_stream_sha256 = header_values.gamma_stream_sha256,
    };
    const pis::RawFooter footer = pis::encode_footer(footer_values);
    pis::decode_footer(footer, &footer_values);

    per::BlockValues second_event_values =
        event_values(1U, inline_replay);
    const per::RawRecord second_event =
        per::encode_record(second_event_values);
    const psj::Result second_result = psj::resolve_replayed_block(
        1U, second_event, inline_replay, {}, identities,
        resolver_options);
    if (!second_result.accepted || second_result.failure_flags != 0U) {
      throw std::runtime_error(
          "second bounded inline fixture was rejected");
    }
    const std::vector<unsigned char> second_frame = pis::encode_frame(
        1U, second_event, second_result.record,
        second_result.resolver_report.canonical_trace_json);
    const pis::HeaderValues two_header_values{
        .first_block = 0U,
        .block_count = 2U,
        .gamma_stream_sha256 = header_values.gamma_stream_sha256,
        .producer_sha256 = header_values.producer_sha256,
        .resolver_sha256 = header_values.resolver_sha256,
        .flint_sha256 = header_values.flint_sha256,
    };
    const pis::RawHeader two_header =
        pis::encode_header(two_header_values);
    sparkinterval::detail::Sha256 two_frame_hasher;
    two_frame_hasher.update(frame.data(), frame.size());
    two_frame_hasher.update(second_frame.data(), second_frame.size());
    const pis::FooterValues two_footer_values{
        .first_block = 0U,
        .block_count = 2U,
        .total_event_records = 2U,
        .total_junction_records = 2U,
        .total_trace_bytes =
            inline_result.resolver_report.canonical_trace_json.size() +
            second_result.resolver_report.canonical_trace_json.size(),
        .frame_stream_sha256 = two_frame_hasher.finish(),
        .header_sha256 = per::digest_at(
            two_header.data() + pis::kHeaderDigestOffset),
        .gamma_stream_sha256 = two_header_values.gamma_stream_sha256,
    };
    const pis::RawFooter two_footer =
        pis::encode_footer(two_footer_values);
    std::vector<unsigned char> two_frame_stream;
    two_frame_stream.reserve(
        two_header.size() + frame.size() + second_frame.size() +
        two_footer.size());
    two_frame_stream.insert(two_frame_stream.end(), two_header.begin(),
                            two_header.end());
    two_frame_stream.insert(two_frame_stream.end(), frame.begin(),
                            frame.end());
    two_frame_stream.insert(two_frame_stream.end(), second_frame.begin(),
                            second_frame.end());
    two_frame_stream.insert(two_frame_stream.end(), two_footer.begin(),
                            two_footer.end());

    std::vector<unsigned char> changed_frame = frame;
    changed_frame[pis::kFramePrefixBytes + 17U] ^= 1U;
    const bool tampered_frame_rejected = rejects([&]() {
      (void)pis::decode_frame(changed_frame, 0U);
    });

    per::BlockValues changed_event_values =
        event_values(0U, inline_replay);
    changed_event_values.event_artifact_sha256[0] ^= 0x80U;
    const per::RawRecord changed_event =
        per::encode_record(changed_event_values);
    const psj::Result tampered_event = psj::resolve_replayed_block(
        0U, changed_event, inline_replay, {}, identities);
    const bool tampered_event_rejected =
        !tampered_event.accepted &&
        (tampered_event.failure_flags & psj::kFailureEventRoot) != 0U;

    psj::IdentityPins zero_identity = identities;
    zero_identity.resolver_sha256.fill(0U);
    const psj::Result zero_identity_result =
        psj::resolve_replayed_block(
            0U, inline_event, inline_replay, {}, zero_identity);
    const bool zero_identity_rejected =
        !zero_identity_result.accepted &&
        (zero_identity_result.failure_flags & psj::kFailureIdentity) != 0U;

    pis::HeaderValues wrong_expected = header_values;
    wrong_expected.resolver_sha256[0] ^= 1U;
    const bool wrong_identity_pin_rejected = rejects([&]() {
      (void)pis::decode_header(header, &wrong_expected);
    });
    pis::HeaderValues zero_producer = header_values;
    zero_producer.producer_sha256.fill(0U);
    const bool zero_producer_rejected = rejects([&]() {
      (void)pis::encode_header(zero_producer);
    });
    pis::HeaderValues overflowing_range = header_values;
    overflowing_range.first_block = per::kSourceBlockCount - 1U;
    overflowing_range.block_count = 2U;
    const bool overflowing_range_rejected = rejects([&]() {
      (void)pis::encode_header(overflowing_range);
    });
    const bool truncated_frame_rejected = rejects([&]() {
      (void)pis::decode_frame(
          std::span<const unsigned char>(frame.data(), frame.size() - 1U),
          0U);
    });
    std::vector<unsigned char> trailing_frame = frame;
    trailing_frame.push_back(0U);
    const bool trailing_frame_rejected = rejects([&]() {
      (void)pis::decode_frame(trailing_frame, 0U);
    });
    const bool relabeled_frame_rejected = rejects([&]() {
      (void)pis::decode_frame(frame, 1U);
    });
    pis::FooterValues wrong_footer = footer_values;
    wrong_footer.gamma_stream_sha256[0] ^= 1U;
    const pis::RawFooter cross_spliced_footer =
        pis::encode_footer(wrong_footer);
    const bool cross_spliced_footer_rejected = rejects([&]() {
      (void)pis::decode_footer(cross_spliced_footer, &footer_values);
    });
    pis::FooterValues wrong_totals = footer_values;
    wrong_totals.total_event_records = 0U;
    const bool wrong_record_total_rejected = rejects([&]() {
      (void)pis::encode_footer(wrong_totals);
    });
    const std::array<psr::Candidate, 2> resolver_candidates{{
        {psr::StreamKind::kMain, 0, 2, true},
        {psr::StreamKind::kMain, 10, 12, true},
    }};
    psr::Options trace_cap_options = resolver_options;
    trace_cap_options.maximum_trace_bytes = 4096U;
    const psr::Report trace_cap_result = psr::resolve_block(
        samples, resolver_candidates, {}, trace_cap_options);
    const bool trace_cap_rejected_without_partial_output =
        !trace_cap_result.accepted &&
        (trace_cap_result.failure_flags &
         psr::kFailureCandidateCapacity) != 0U &&
        trace_cap_result.resolutions.empty() &&
        trace_cap_result.precision_replay_audit.empty() &&
        trace_cap_result.canonical_trace_json.size() <=
            trace_cap_options.maximum_trace_bytes;
    bool unpinned_replay_precision_rejected = true;
    for (const std::uint32_t extra_precision : {63U, 65U}) {
      psr::Options unpinned_precision = resolver_options;
      unpinned_precision.replay_extra_precision_bits = extra_precision;
      const psr::Report rejected = psr::resolve_block(
          zero_candidate_samples, {}, {}, unpinned_precision);
      unpinned_replay_precision_rejected &=
          !rejected.accepted &&
          (rejected.failure_flags & psr::kFailureInputGeometry) != 0U &&
          rejected.resolutions.empty() &&
          rejected.precision_replay_audit.empty();
    }
    const std::size_t two_candidate_trace_bytes =
        inline_result.resolver_report.canonical_trace_json.size();
    if (two_candidate_trace_bytes <=
        zero_candidate_report.canonical_trace_json.size()) {
      throw std::runtime_error(
          "V2 trace candidate sizing did not grow");
    }
    const std::size_t representative_bytes_per_candidate =
        (two_candidate_trace_bytes -
         zero_candidate_report.canonical_trace_json.size()) /
        2U;
    const std::size_t representative_candidates_within_16mib =
        (psr::kSourceTraceMaximumBytes -
         zero_candidate_report.canonical_trace_json.size()) /
        representative_bytes_per_candidate;

    const bool success =
        standalone_byte_identity && tampered_frame_rejected &&
        tampered_event_rejected && zero_identity_rejected &&
        wrong_identity_pin_rejected && zero_producer_rejected &&
        overflowing_range_rejected && truncated_frame_rejected &&
        trailing_frame_rejected && relabeled_frame_rejected &&
        cross_spliced_footer_rejected && wrong_record_total_rejected &&
        trace_cap_rejected_without_partial_output &&
        unpinned_replay_precision_rejected;
    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.platt-inline-stationary-kat.v1\""
              << ",\"test_success\":"
              << (success ? "true" : "false")
              << ",\"qualification_only\":true"
              << ",\"synthetic_finite_fixture\":true"
              << ",\"block\":0"
              << ",\"iterations\":" << iterations
              << ",\"elapsed_seconds\":" << seconds
              << ",\"inline_junctions_per_second\":"
              << static_cast<double>(iterations) / seconds
              << ",\"inline_replay_api\":\"replay_captured\""
              << ",\"standalone_replay_api\":\"replay_and_check\""
              << ",\"inline_matches_standalone_bytes\":"
              << (standalone_byte_identity ? "true" : "false")
              << ",\"tampered_frame_rejected\":"
              << (tampered_frame_rejected ? "true" : "false")
              << ",\"tampered_event_root_rejected\":"
              << (tampered_event_rejected ? "true" : "false")
              << ",\"zero_identity_rejected\":"
              << (zero_identity_rejected ? "true" : "false")
              << ",\"wrong_expected_identity_rejected\":"
              << (wrong_identity_pin_rejected ? "true" : "false")
              << ",\"zero_producer_rejected\":"
              << (zero_producer_rejected ? "true" : "false")
              << ",\"overflowing_range_rejected\":"
              << (overflowing_range_rejected ? "true" : "false")
              << ",\"truncated_frame_rejected\":"
              << (truncated_frame_rejected ? "true" : "false")
              << ",\"trailing_frame_rejected\":"
              << (trailing_frame_rejected ? "true" : "false")
              << ",\"relabeled_frame_rejected\":"
              << (relabeled_frame_rejected ? "true" : "false")
              << ",\"cross_spliced_footer_rejected\":"
              << (cross_spliced_footer_rejected ? "true" : "false")
              << ",\"wrong_record_total_rejected\":"
              << (wrong_record_total_rejected ? "true" : "false")
              << ",\"trace_cap_rejected_without_partial_output\":"
              << (trace_cap_rejected_without_partial_output
                      ? "true"
                      : "false")
              << ",\"unpinned_replay_precision_rejected\":"
              << (unpinned_replay_precision_rejected
                      ? "true"
                      : "false")
              << ",\"zero_candidate_v2_trace_bytes\":"
              << zero_candidate_report.canonical_trace_json.size()
              << ",\"two_candidate_v2_trace_bytes\":"
              << two_candidate_trace_bytes
              << ",\"representative_v2_bytes_per_candidate\":"
              << representative_bytes_per_candidate
              << ",\"representative_candidates_within_16mib\":"
              << representative_candidates_within_16mib
              << ",\"absolute_candidate_roster_cap\":"
              << psr::kSourceTraceResolutionLimit
              << ",\"event_record_hex\":\"" << hex(inline_event)
              << "\""
              << ",\"junction_record_hex\":\""
              << hex(inline_result.record) << "\""
              << ",\"stationary_trace_hex\":\""
              << hex(inline_result.resolver_report.canonical_trace_json)
              << "\""
              << ",\"frame_bytes\":" << frame.size()
              << ",\"frame_sha256\":\""
              << sparkinterval::lowercase_hex(
                     sparkinterval::sha256(frame.data(), frame.size()))
              << "\""
              << ",\"two_frame_stream_hex\":\""
              << hex(two_frame_stream) << "\""
              << ",\"producer_sha256_self_verified\":false"
              << ",\"producer_sha256_requires_external_manifest_pin\":true"
              << ",\"resolver_sha256_self_verified\":false"
              << ",\"flint_sha256_self_verified\":false"
              << ",\"identity_pins_require_external_manifest_or_attestation\":true"
              << ",\"resolver_inputs_retained\":false"
              << ",\"resolver_input_sha256_recomputed_from_frame\":false"
              << ",\"candidate_completeness_recomputed_from_frame\":false"
              << ",\"independent_checker_complete\":false"
              << ",\"higher_precision_containment_semantics\":"
                 "\"replay_contained_in_retained_outward_hull\""
              << ",\"hardy_z_endpoint_realization_proved\":false"
              << ",\"flint_to_mathlib_realization_proved\":false"
              << ",\"analytic_turing_realization_proved\":false"
              << ",\"sgn2_static_manifest_bound\":false"
              << ",\"multi_block_source_chain_closed\":false"
              << ",\"source_claim_ready\":false"
              << ",\"production_ready\":false"
              << ",\"pt21_atom_discharged\":false}\n";

    pes::destroy_replay_capture(capture);
    capture = nullptr;
    pes::destroy_workspace(workspace);
    workspace = nullptr;
    check_cuda(cudaFree(device_samples), "free inline fixture");
    device_samples = nullptr;
    return success ? 0 : 1;
  } catch (...) {
    if (capture != nullptr) {
      try {
        pes::destroy_replay_capture(capture);
      } catch (...) {
      }
    }
    if (workspace != nullptr) {
      try {
        pes::destroy_workspace(workspace);
      } catch (...) {
      }
    }
    if (device_samples != nullptr) cudaFree(device_samples);
    throw;
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(argc, argv);
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-inline-stationary-kat: "
              << error.what() << '\n';
    return 2;
  }
}

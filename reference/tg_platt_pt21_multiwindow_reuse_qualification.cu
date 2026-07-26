// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only experiment for exact PT21 lattice-window reuse.
//
// One genuine V2 source transform centered at logical block b is scanned at
// the five geometrically possible views b+delta, delta=-2..2.  Every eligible
// shifted view is independently replayed with the event scanner's fixed
// 2176-bit host arithmetic, then compared with a separately centered genuine
// transform for the same logical block.  This executable proves no Hardy-Z
// realization and emits no source or production certificate.

#include "sparkinterval/tg_platt_dd_accumulator.hpp"
#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"
#include "sparkinterval/tg_platt_gamma_dd_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"
#include "sparkinterval/tg_platt_stationary_junction.hpp"

#include <cuda_runtime.h>

#include <boost/multiprecision/cpp_int.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pgd = sparkinterval::tg::platt_gamma_dd_gpu;
namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;
namespace per = sparkinterval::tg::platt_event_record;
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace psr = sparkinterval::tg::platt_stationary_resolver;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

constexpr std::string_view kCmakeBuildConfig =
    SPARKINTERVAL_CMAKE_BUILD_CONFIG;
#ifdef NDEBUG
constexpr bool kNdebugDefined = true;
#else
constexpr bool kNdebugDefined = false;
#endif
constexpr bool kReleasePerformanceBuild =
    kNdebugDefined && kCmakeBuildConfig == "Release";

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +               \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

constexpr std::array<std::int32_t, 5> kDeltas = {-2, -1, 0, 1, 2};

struct Options {
  bool bounds_self_test = false;
  std::string stream_path;
  std::uint64_t center_block = 0U;
  std::uint32_t reanchor_blocks = 256U;
  std::optional<sparkinterval::Sha256Digest> expected_stream_sha256;
  std::optional<sparkinterval::Sha256Digest> resolver_sha256;
  std::optional<sparkinterval::Sha256Digest> flint_sha256;
  std::array<bool, kDeltas.size()> owned_deltas{};
  bool owned_deltas_explicit = false;
};

struct ViewResult {
  std::int32_t delta = 0;
  std::uint64_t target_block = 0U;
  std::uint32_t shifted_begin = 0U;
  bool campaign_boundary_rejected = false;
  bool roster_owned = false;
  double reuse_scan_replay_seconds = 0.0;
  double ordinary_scan_replay_seconds = 0.0;
  double reuse_junction_seconds = 0.0;
  double ordinary_junction_seconds = 0.0;
  double ordinary_source_gpu_seconds = 0.0;
  double ordinary_transform_gpu_seconds = 0.0;
  pes::ReplayReport reuse;
  pes::ReplayReport ordinary;
  psj::Result reuse_junction;
  psj::Result ordinary_junction;
  std::vector<std::int8_t> reuse_exact_signs;
  std::vector<std::int8_t> ordinary_exact_signs;
  std::array<std::int64_t, pes::kStreamCount> reuse_total_nleft_units{};
  std::array<std::int64_t, pes::kStreamCount> reuse_total_nright_units{};
  std::array<std::int64_t, pes::kStreamCount> ordinary_total_nleft_units{};
  std::array<std::int64_t, pes::kStreamCount> ordinary_total_nright_units{};
  std::uint64_t disk_byte_mismatches = 0U;
  std::uint64_t reused_certified_sign_count = 0U;
  std::uint64_t certified_overlap_sign_mismatches = 0U;
  std::uint64_t disk_interval_disjoint_count = 0U;
  bool sign_output_byte_identity = false;
  bool finite_event_semantics_identity = false;
  bool stationary_resolution_semantics_identity = false;
  bool finite_nleft_nright_semantics_identity = false;
  bool junction_record_byte_identity = false;
  bool artifact_sha256_identity = false;
};

std::uint64_t parse_unsigned(std::string_view text, const char* label) {
  if (text.empty() || text.front() == '-') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  std::uint64_t result = 0U;
  const auto parsed =
      std::from_chars(text.data(), text.data() + text.size(), result);
  if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size()) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return result;
}

unsigned char parse_hex_byte(char high, char low) {
  auto nibble = [](char value) -> unsigned int {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10U;
    throw std::runtime_error("stream SHA-256 is not hexadecimal");
  };
  return static_cast<unsigned char>((nibble(high) << 4U) | nibble(low));
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error(
        "expected stream SHA-256 must have 64 hexadecimal digits");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    result[index] = parse_hex_byte(text[2U * index], text[2U * index + 1U]);
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  Options result;
  if (argc == 2 && std::string_view(argv[1]) == "--bounds-self-test") {
    result.bounds_self_test = true;
    return result;
  }
  if (argc < 4) {
    throw std::runtime_error(
        "usage: pt21-multiwindow-reuse STREAM CENTER_BLOCK "
        "--expected-stream-sha256=HEX --resolver-sha256=HEX "
        "--flint-sha256=HEX [--reanchor-blocks=N] "
        "[--owned-deltas=-2,-1,0,1,2]\n"
        "       pt21-multiwindow-reuse --bounds-self-test");
  }
  result.stream_path = argv[1];
  result.center_block = parse_unsigned(argv[2], "center block");
  for (int index = 3; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument.starts_with("--expected-stream-sha256=")) {
      if (result.expected_stream_sha256.has_value()) {
        throw std::runtime_error("expected stream SHA-256 is duplicated");
      }
      result.expected_stream_sha256 = parse_sha256(
          argument.substr(std::string_view("--expected-stream-sha256=").size()));
    } else if (argument.starts_with("--resolver-sha256=")) {
      if (result.resolver_sha256.has_value()) {
        throw std::runtime_error("resolver SHA-256 is duplicated");
      }
      result.resolver_sha256 = parse_sha256(
          argument.substr(std::string_view("--resolver-sha256=").size()));
    } else if (argument.starts_with("--flint-sha256=")) {
      if (result.flint_sha256.has_value()) {
        throw std::runtime_error("FLINT SHA-256 is duplicated");
      }
      result.flint_sha256 = parse_sha256(
          argument.substr(std::string_view("--flint-sha256=").size()));
    } else if (argument.starts_with("--owned-deltas=")) {
      if (result.owned_deltas_explicit) {
        throw std::runtime_error("owned deltas are duplicated");
      }
      result.owned_deltas_explicit = true;
      std::string_view remaining =
          argument.substr(std::string_view("--owned-deltas=").size());
      if (remaining.empty()) {
        throw std::runtime_error("owned delta roster is empty");
      }
      while (!remaining.empty()) {
        const std::size_t comma = remaining.find(',');
        const std::string_view token = remaining.substr(0U, comma);
        std::int32_t delta = 0;
        const auto parsed =
            std::from_chars(token.data(), token.data() + token.size(), delta);
        if (token.empty() || parsed.ec != std::errc{} ||
            parsed.ptr != token.data() + token.size() ||
            delta < -2 || delta > 2) {
          throw std::runtime_error(
              "owned delta roster contains an invalid member");
        }
        const std::size_t roster_index =
            static_cast<std::size_t>(delta + 2);
        if (result.owned_deltas[roster_index]) {
          throw std::runtime_error(
              "owned delta roster contains a duplicate");
        }
        result.owned_deltas[roster_index] = true;
        if (comma == std::string_view::npos) break;
        remaining.remove_prefix(comma + 1U);
        if (remaining.empty()) {
          throw std::runtime_error(
              "owned delta roster has a trailing separator");
        }
      }
    } else if (argument.starts_with("--reanchor-blocks=")) {
      const std::uint64_t parsed = parse_unsigned(
          argument.substr(std::string_view("--reanchor-blocks=").size()),
          "reanchor blocks");
      if (parsed == 0U || parsed > (1U << 24U)) {
        throw std::runtime_error("reanchor blocks is outside range");
      }
      result.reanchor_blocks = static_cast<std::uint32_t>(parsed);
    } else {
      throw std::runtime_error("unknown option: " + std::string(argument));
    }
  }
  if (result.stream_path.empty() ||
      result.center_block >= pw::kFullBlockCount ||
      !result.expected_stream_sha256.has_value() ||
      !result.resolver_sha256.has_value() ||
      !result.flint_sha256.has_value() ||
      per::digest_is_zero(*result.resolver_sha256) ||
      per::digest_is_zero(*result.flint_sha256)) {
    throw std::runtime_error(
        "qualification requires an in-campaign center and nonzero stream, "
        "resolver, and FLINT pins");
  }
  if (result.owned_deltas_explicit &&
      !result.owned_deltas[2U]) {
    throw std::runtime_error(
        "owned delta roster must contain its center delta zero");
  }
  return result;
}

void require_target_device() {
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
  if (properties.major != 9 || properties.minor != 0 ||
      std::string_view(properties.name).find("H100") ==
          std::string_view::npos) {
    throw std::runtime_error(
        "strict H100 qualification target requires NVIDIA H100 sm_90");
  }
#endif
}

bool target_for_delta(std::uint64_t center, std::int32_t delta,
                      std::uint64_t* target) {
  if (delta < 0) {
    const std::uint64_t magnitude =
        static_cast<std::uint64_t>(-static_cast<std::int64_t>(delta));
    if (center < magnitude) return false;
    *target = center - magnitude;
    return true;
  }
  const std::uint64_t magnitude = static_cast<std::uint64_t>(delta);
  if (center >= pw::kFullBlockCount ||
      magnitude >= pw::kFullBlockCount - center) {
    return false;
  }
  *target = center + magnitude;
  return true;
}

std::size_t delta_index(std::int32_t delta) {
  if (delta < -2 || delta > 2) {
    throw std::out_of_range("qualification delta is outside -2..2");
  }
  return static_cast<std::size_t>(delta + 2);
}

bool bytes_equal(const void* first, const void* second, std::size_t bytes) {
  return bytes == 0U || std::memcmp(first, second, bytes) == 0;
}

struct ExactDyadic {
  boost::multiprecision::cpp_int numerator;
  int exponent = 0;
};

ExactDyadic exact_dyadic(double value) {
  const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
  const bool negative = (bits >> 63U) != 0U;
  const std::uint64_t exponent_bits = (bits >> 52U) & 0x7ffU;
  const std::uint64_t fraction = bits & ((std::uint64_t{1} << 52U) - 1U);
  if (exponent_bits == 0x7ffU) {
    throw std::runtime_error("non-finite value in exact dyadic conversion");
  }
  if (exponent_bits == 0U && fraction == 0U) return {};
  ExactDyadic result;
  if (exponent_bits == 0U) {
    result.numerator = fraction;
    result.exponent = -1074;
  } else {
    result.numerator =
        (std::uint64_t{1} << 52U) | fraction;
    result.exponent =
        static_cast<int>(exponent_bits) - 1023 - 52;
  }
  if (negative) result.numerator = -result.numerator;
  return result;
}

template <std::size_t Size>
int exact_sum_sign(const std::array<double, Size>& terms) {
  std::array<ExactDyadic, Size> exact{};
  int minimum_exponent = std::numeric_limits<int>::max();
  for (std::size_t index = 0U; index < Size; ++index) {
    exact[index] = exact_dyadic(terms[index]);
    if (exact[index].numerator != 0) {
      minimum_exponent =
          std::min(minimum_exponent, exact[index].exponent);
    }
  }
  if (minimum_exponent == std::numeric_limits<int>::max()) return 0;
  boost::multiprecision::cpp_int total = 0;
  for (const ExactDyadic& term : exact) {
    if (term.numerator != 0) {
      total += term.numerator << (term.exponent - minimum_exponent);
    }
  }
  return total == 0 ? 0 : total < 0 ? -1 : 1;
}

std::int8_t exact_disk_sign(const pw::RealDisk106& disk) {
  if (!std::isfinite(disk.center.hi) ||
      !std::isfinite(disk.center.lo) ||
      !std::isfinite(disk.radius) || disk.radius < 0.0) {
    return 0;
  }
  if (exact_sum_sign(
          std::array<double, 3>{
              disk.center.hi, disk.center.lo, -disk.radius}) > 0) {
    return 1;
  }
  if (exact_sum_sign(
          std::array<double, 3>{
              disk.center.hi, disk.center.lo, disk.radius}) < 0) {
    return -1;
  }
  return 0;
}

std::vector<std::int8_t> exact_sign_output(
    const pes::ReplayReport& report) {
  std::vector<std::int8_t> result;
  result.reserve(report.required_samples.size());
  for (const pw::RealDisk106& disk : report.required_samples) {
    result.push_back(exact_disk_sign(disk));
  }
  return result;
}

template <class T>
bool vector_bytes_equal(const std::vector<T>& first,
                        const std::vector<T>& second) {
  return first.size() == second.size() &&
         bytes_equal(first.data(), second.data(), first.size() * sizeof(T));
}

bool summary_finite_output_equal(const pes::StreamSummary& first,
                                 const pes::StreamSummary& second) {
  // Endpoint disks are numerical enclosures, not finite event outputs.  Their
  // sample indices and certified signs are nevertheless compared exactly.
  return first.stream == second.stream &&
         first.lower_sample == second.lower_sample &&
         first.upper_sample == second.upper_sample &&
         first.range_sample_count == second.range_sample_count &&
         first.direct_event_count == second.direct_event_count &&
         first.stationary_candidate_count ==
             second.stationary_candidate_count &&
         first.certified_direct_multiplicity_slots ==
             second.certified_direct_multiplicity_slots &&
         first.reserved_zero == second.reserved_zero &&
         first.direct_nleft_units == second.direct_nleft_units &&
         first.direct_nright_units == second.direct_nright_units &&
         first.left_endpoint.sample_offset ==
             second.left_endpoint.sample_offset &&
         first.left_endpoint.positive == second.left_endpoint.positive &&
         first.right_endpoint.sample_offset ==
             second.right_endpoint.sample_offset &&
         first.right_endpoint.positive == second.right_endpoint.positive;
}

bool finite_event_output_equal(const pes::ReplayReport& first,
                               const pes::ReplayReport& second) {
  if (!first.accepted || !second.accepted) return false;
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    if (!summary_finite_output_equal(first.artifact.summaries[stream],
                                     second.artifact.summaries[stream]) ||
        !vector_bytes_equal(first.artifact.direct[stream],
                            second.artifact.direct[stream]) ||
        !vector_bytes_equal(first.artifact.stationary[stream],
                            second.artifact.stationary[stream])) {
      return false;
    }
  }
  return true;
}

per::BlockValues event_values(std::uint64_t block,
                              const pes::ReplayReport& replay) {
  if (!replay.accepted) {
    throw std::runtime_error(
        "cannot encode an event record from a rejected replay");
  }
  per::BlockValues result{};
  result.block = block;
  result.failure_flags = replay.artifact.status.failure_flags;
  result.certified_sample_count =
      replay.artifact.status.certified_sample_count;
  result.digest_valid = replay.artifact.status.digest_valid;
  std::memcpy(result.event_artifact_sha256.data(),
              replay.artifact.status.artifact_sha256,
              result.event_artifact_sha256.size());
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    const pes::StreamSummary& summary = replay.artifact.summaries[stream];
    result.direct_event_count[stream] = summary.direct_event_count;
    result.stationary_candidate_count[stream] =
        summary.stationary_candidate_count;
    result.certified_direct_slots[stream] =
        summary.certified_direct_multiplicity_slots;
    if (summary.stationary_candidate_count >
        std::numeric_limits<std::uint32_t>::max() -
            result.unresolved_stationary_count) {
      throw std::runtime_error(
          "qualification stationary candidate total overflows");
    }
    result.unresolved_stationary_count +=
        summary.stationary_candidate_count;
    result.direct_nleft_units[stream] = summary.direct_nleft_units;
    result.direct_nright_units[stream] = summary.direct_nright_units;
  }
  per::validate_block_values(result, block);
  return result;
}

psj::Result resolve_stationary(
    std::uint64_t block, const pes::ReplayReport& replay,
    const psj::IdentityPins& identities, double* elapsed_seconds) {
  const per::RawRecord record =
      per::encode_record(event_values(block, replay));
  psr::Options resolver_options;
  resolver_options.retain_precision_hull_audit = true;
  const auto started = std::chrono::steady_clock::now();
  psj::Result result = psj::resolve_replayed_block(
      block, record, replay, {}, identities, resolver_options);
  *elapsed_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();
  if (!result.accepted || result.failure_flags != 0U ||
      !result.resolver_report.accepted ||
      !result.resolver_report.replay_accepted) {
    throw std::runtime_error(
        "stationary junction failed closed: junction_flags=" +
        std::to_string(result.failure_flags) +
        ", resolver_flags=" +
        std::to_string(result.resolver_report.failure_flags) +
        ", error=" + result.error +
        ", resolver_error=" + result.resolver_report.error);
  }
  return result;
}

bool rational_equal(const psr::CanonicalRational& first,
                    const psr::CanonicalRational& second) {
  return first.numerator == second.numerator &&
         first.denominator == second.denominator;
}

bool resolution_semantics_equal(const psr::Resolution& first,
                                const psr::Resolution& second) {
  return first.stream == second.stream &&
         first.outer_left_sample == second.outer_left_sample &&
         first.outer_right_sample == second.outer_right_sample &&
         rational_equal(first.lower_offset, second.lower_offset) &&
         rational_equal(first.midpoint_offset, second.midpoint_offset) &&
         rational_equal(first.upper_offset, second.upper_offset) &&
         first.iterations == second.iterations &&
         first.interpolation_evaluations ==
             second.interpolation_evaluations;
}

bool junction_semantics_equal(const psj::Result& first,
                              const psj::Result& second) {
  if (!first.accepted || !second.accepted) return false;
  const psj::RecordValues first_record = psj::decode_record(first.record);
  const psj::RecordValues second_record = psj::decode_record(second.record);
  const bool fixed_record_semantics =
      first_record.block == second_record.block &&
      first_record.failure_flags == second_record.failure_flags &&
      first_record.candidate_count == second_record.candidate_count &&
      first_record.resolution_count == second_record.resolution_count &&
      first_record.ambiguous_input_count ==
          second_record.ambiguous_input_count &&
      first_record.refinement_count == second_record.refinement_count &&
      first_record.resolved_multiplicity_slots ==
          second_record.resolved_multiplicity_slots &&
      first_record.precision_bits == second_record.precision_bits &&
      first_record.maximum_depth == second_record.maximum_depth &&
      first_record.replay_extra_precision_bits ==
          second_record.replay_extra_precision_bits &&
      first_record.flint_release == second_record.flint_release &&
      first_record.semantic_realization_flags ==
          second_record.semantic_realization_flags &&
      first_record.resolver_replay_accepted ==
          second_record.resolver_replay_accepted &&
      first_record.higher_precision_containment_complete ==
          second_record.higher_precision_containment_complete &&
      first_record.candidate_list_sha256 ==
          second_record.candidate_list_sha256 &&
      first_record.refinement_trace_sha256 ==
          second_record.refinement_trace_sha256 &&
      first_record.resolver_sha256 == second_record.resolver_sha256 &&
      first_record.flint_sha256 == second_record.flint_sha256;
  if (!fixed_record_semantics ||
      first.resolver_report.resolutions.size() !=
          second.resolver_report.resolutions.size()) {
    return false;
  }
  for (std::size_t index = 0U;
       index < first.resolver_report.resolutions.size(); ++index) {
    if (!resolution_semantics_equal(
            first.resolver_report.resolutions[index],
            second.resolver_report.resolutions[index])) {
      return false;
    }
  }
  return true;
}

void total_turing_units(
    const pes::ReplayReport& replay, const psj::Result& junction,
    std::array<std::int64_t, pes::kStreamCount>* nleft,
    std::array<std::int64_t, pes::kStreamCount>* nright) {
  const psj::RecordValues record = psj::decode_record(junction.record);
  std::uint64_t candidate_count = 0U;
  std::uint64_t multiplicity_slots = 0U;
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    (*nleft)[stream] = replay.artifact.summaries[stream].direct_nleft_units;
    (*nright)[stream] =
        replay.artifact.summaries[stream].direct_nright_units;
    for (const pes::StationaryCandidate& candidate :
         replay.artifact.stationary[stream]) {
      if (candidate.stream != stream ||
          candidate.certified_multiplicity_slots != 0U ||
          candidate.multiplicity_slots_if_resolution_succeeds != 2U) {
        throw std::runtime_error(
            "stationary candidate multiplicity contract differs");
      }
      const std::int64_t slots =
          candidate.multiplicity_slots_if_resolution_succeeds;
      (*nleft)[stream] +=
          slots * candidate.source_nleft_units_per_slot_if_resolved;
      (*nright)[stream] +=
          slots * candidate.source_nright_units_per_slot_if_resolved;
      multiplicity_slots += static_cast<std::uint64_t>(slots);
      ++candidate_count;
    }
  }
  if (candidate_count != record.candidate_count ||
      candidate_count != record.resolution_count ||
      multiplicity_slots != record.resolved_multiplicity_slots ||
      candidate_count != junction.resolver_report.resolutions.size()) {
    throw std::runtime_error(
        "stationary junction multiplicity/count semantics differ");
  }
}

std::uint64_t disk_byte_mismatch_count(const pes::ReplayReport& first,
                                       const pes::ReplayReport& second) {
  if (first.required_samples.size() != second.required_samples.size()) {
    return std::max(first.required_samples.size(),
                    second.required_samples.size());
  }
  std::uint64_t result = 0U;
  for (std::size_t index = 0U; index < first.required_samples.size(); ++index) {
    if (!bytes_equal(&first.required_samples[index],
                     &second.required_samples[index],
                     sizeof(pw::RealDisk106))) {
      ++result;
    }
  }
  return result;
}

bool exact_disk_intervals_overlap(const pw::RealDisk106& first,
                                  const pw::RealDisk106& second) {
  if (!std::isfinite(first.center.hi) ||
      !std::isfinite(first.center.lo) ||
      !std::isfinite(first.radius) || first.radius < 0.0 ||
      !std::isfinite(second.center.hi) ||
      !std::isfinite(second.center.lo) ||
      !std::isfinite(second.radius) || second.radius < 0.0) {
    return false;
  }
  // first.lower <= second.upper and second.lower <= first.upper,
  // evaluated as exact sums of binary64 dyadics.
  const int first_after_second = exact_sum_sign(
      std::array<double, 6>{
          first.center.hi, first.center.lo, -first.radius,
          -second.center.hi, -second.center.lo, -second.radius});
  const int second_after_first = exact_sum_sign(
      std::array<double, 6>{
          second.center.hi, second.center.lo, -second.radius,
          -first.center.hi, -first.center.lo, -first.radius});
  return first_after_second <= 0 && second_after_first <= 0;
}

void compare_disk_diagnostics(ViewResult* view) {
  if (view->reuse.required_samples.size() !=
          view->ordinary.required_samples.size() ||
      view->reuse_exact_signs.size() !=
          view->ordinary_exact_signs.size() ||
      view->reuse.required_samples.size() !=
          view->reuse_exact_signs.size()) {
    throw std::runtime_error(
        "disk diagnostic inputs have different cardinalities");
  }
  for (std::size_t index = 0U;
       index < view->reuse_exact_signs.size(); ++index) {
    const std::int8_t reuse_sign = view->reuse_exact_signs[index];
    const std::int8_t ordinary_sign =
        view->ordinary_exact_signs[index];
    if (reuse_sign != 0) ++view->reused_certified_sign_count;
    if (reuse_sign != 0 && ordinary_sign != 0 &&
        reuse_sign != ordinary_sign) {
      ++view->certified_overlap_sign_mismatches;
    }
    if (!exact_disk_intervals_overlap(
            view->reuse.required_samples[index],
            view->ordinary.required_samples[index])) {
      ++view->disk_interval_disjoint_count;
    }
  }
}

std::uint64_t malformed_count(const pes::ReplayReport& report) {
  return std::count_if(
      report.required_samples.begin(), report.required_samples.end(),
      [](const pw::RealDisk106& disk) {
        return !std::isfinite(disk.center.hi) ||
               !std::isfinite(disk.center.lo) ||
               !std::isfinite(disk.radius) || disk.radius < 0.0;
      });
}

std::uint64_t uncertified_count(const pes::ReplayReport& report) {
  const std::vector<std::int8_t> signs = exact_sign_output(report);
  return std::count(signs.begin(), signs.end(), std::int8_t{0});
}

std::uint64_t ambiguous_count(const pes::ReplayReport& report) {
  const std::uint64_t uncertified = uncertified_count(report);
  const std::uint64_t malformed = malformed_count(report);
  return uncertified >= malformed ? uncertified - malformed : uncertified;
}

double maximum_radius(const pes::ReplayReport& report) {
  double result = 0.0;
  for (const pw::RealDisk106& disk : report.required_samples) {
    if (std::isfinite(disk.radius)) result = std::max(result, disk.radius);
  }
  return result;
}

std::uint64_t direct_event_count(const pes::ReplayReport& report) {
  std::uint64_t result = 0U;
  for (const auto& events : report.artifact.direct) result += events.size();
  return result;
}

std::uint64_t stationary_candidate_count(const pes::ReplayReport& report) {
  std::uint64_t result = 0U;
  for (const auto& events : report.artifact.stationary) {
    result += events.size();
  }
  return result;
}

pes::ReplayReport scan_and_replay(
    pes::Workspace* scanner,
    const pdt::QualificationRequiredSampleView& view,
    cudaStream_t stream, double* elapsed_seconds) {
  if (view.samples == nullptr || view.count != pdt::kSourceRequiredCount) {
    throw std::runtime_error(
        "bounds-checked shifted view has invalid pointer or count");
  }
  const auto started = std::chrono::steady_clock::now();
  pes::scan_source_required_samples(scanner, view.samples, stream);
  pes::ReplayReport report =
      pes::replay_and_check(scanner, view.samples, stream);
  *elapsed_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();
  if (report.required_samples.size() != pdt::kSourceRequiredCount) {
    throw std::runtime_error(
        "shifted replay did not retain the complete sample view");
  }
  if (report.accepted && uncertified_count(report) != 0U) {
    throw std::runtime_error(
        "accepted shifted replay did not retain complete exact signs");
  }
  return report;
}

void run_bounds_self_test() {
  constexpr std::array<std::uint32_t, 5> expected = {
      3'514U, 28'090U, 52'666U, 77'242U, 101'818U};
  for (std::size_t index = 0U; index < kDeltas.size(); ++index) {
    const std::uint32_t actual =
        pdt::qualification_required_begin_for_delta(kDeltas[index]);
    if (actual != expected[index] ||
        actual > pdt::kSourceSampleCount - pdt::kSourceRequiredCount) {
      throw std::runtime_error("shifted-view valid bounds self-test failed");
    }
  }
  const std::array<std::int32_t, 4> rejected = {
      -3, 3, std::numeric_limits<std::int32_t>::min(),
      std::numeric_limits<std::int32_t>::max()};
  for (const std::int32_t delta : rejected) {
    bool threw = false;
    try {
      static_cast<void>(
          pdt::qualification_required_begin_for_delta(delta));
    } catch (const std::out_of_range&) {
      threw = true;
    }
    if (!threw) {
      throw std::runtime_error(
          "shifted-view invalid bounds self-test did not fail closed");
    }
  }
  std::cout
      << "{\"schema\":\"sparkinterval.tg.pt21-multiwindow-bounds-kat.v1\""
      << ",\"test_success\":true"
      << ",\"qualification_only\":true"
      << ",\"build_profile\":{\"cmake_build_config\":\""
      << kCmakeBuildConfig << "\",\"ndebug_defined\":"
      << (kNdebugDefined ? "true" : "false")
      << ",\"release_performance_build\":"
      << (kReleasePerformanceBuild ? "true" : "false") << '}'
      << ",\"sample_shift\":24576"
      << ",\"required_count\":25741"
      << ",\"accepted_deltas\":[-2,-1,0,1,2]"
      << ",\"accepted_begins\":[3514,28090,52666,77242,101818]"
      << ",\"rejected_deltas\":[-3,3,-2147483648,2147483647]"
      << ",\"arbitrary_pointer_api_used\":false"
      << ",\"hardy_z_realization_proved\":false"
      << ",\"source_claim_ready\":false"
      << ",\"production_ready\":false}\n";
}

struct Resources {
  pda::Workspace* accumulator = nullptr;
  pdt::Workspace* transform = nullptr;
  pes::Workspace* scanner = nullptr;
  pg2::Record* device_record = nullptr;
  pw::ComplexDisk106* device_gamma = nullptr;
  cudaStream_t stream = nullptr;
  cudaEvent_t source_started = nullptr;
  cudaEvent_t source_stopped = nullptr;
  cudaEvent_t transform_started = nullptr;
  cudaEvent_t transform_stopped = nullptr;

  ~Resources() {
    if (transform_stopped != nullptr) cudaEventDestroy(transform_stopped);
    if (transform_started != nullptr) cudaEventDestroy(transform_started);
    if (source_stopped != nullptr) cudaEventDestroy(source_stopped);
    if (source_started != nullptr) cudaEventDestroy(source_started);
    if (stream != nullptr) cudaStreamDestroy(stream);
    if (device_gamma != nullptr) cudaFree(device_gamma);
    if (device_record != nullptr) cudaFree(device_record);
    try {
      pes::destroy_workspace(scanner);
    } catch (...) {
    }
    try {
      pdt::destroy_workspace(transform);
    } catch (...) {
    }
    try {
      pda::destroy_workspace(accumulator);
    } catch (...) {
    }
  }
};

int run(const Options& options) {
  if (options.bounds_self_test) {
    run_bounds_self_test();
    return 0;
  }
  require_target_device();
  const auto wall_started = std::chrono::steady_clock::now();
  std::ifstream input(options.stream_path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor V2 stream");
  pg2::Reader reader(input, std::nullopt, std::nullopt,
                     options.expected_stream_sha256);

  std::array<ViewResult, kDeltas.size()> views{};
  std::uint64_t first_target = pw::kFullBlockCount;
  std::uint64_t last_target = 0U;
  std::uint32_t eligible_count = 0U;
  std::uint32_t owned_count = 0U;
  const std::uint64_t stream_first = reader.header().first_block;
  const std::uint64_t stream_count = reader.header().block_count;
  const std::uint64_t stream_end = stream_first + stream_count;
  for (std::size_t index = 0U; index < kDeltas.size(); ++index) {
    ViewResult& view = views[index];
    view.delta = kDeltas[index];
    // Validate transform allocation geometry even when the corresponding
    // campaign block is outside the global range.
    view.shifted_begin =
        pdt::qualification_required_begin_for_delta(view.delta);
    if (!target_for_delta(options.center_block, view.delta,
                          &view.target_block)) {
      view.campaign_boundary_rejected = true;
      if (options.owned_deltas_explicit &&
          options.owned_deltas[index]) {
        throw std::runtime_error(
            "owned delta roster leaves the PT21 campaign");
      }
      continue;
    }
    view.roster_owned =
        options.owned_deltas_explicit
            ? options.owned_deltas[index]
            : true;
    if (view.target_block < stream_first || view.target_block >= stream_end) {
      throw std::runtime_error(
          "authenticated V2 stream does not contain every eligible target");
    }
    first_target = std::min(first_target, view.target_block);
    last_target = std::max(last_target, view.target_block);
    ++eligible_count;
    if (view.roster_owned) ++owned_count;
  }
  if (eligible_count == 0U || owned_count == 0U ||
      first_target > last_target) {
    throw std::runtime_error("qualification has no eligible target blocks");
  }

  Resources resources;
  const auto setup_started = std::chrono::steady_clock::now();
  resources.accumulator = pda::create_source_workspace(
      first_target, last_target - first_target + 1U,
      options.reanchor_blocks);
  resources.transform = pdt::create_source_workspace();
  resources.scanner = pes::create_workspace();
  CUDA_CHECK(cudaMalloc(&resources.device_record,
                        sizeof(*resources.device_record)));
  CUDA_CHECK(cudaMalloc(
      &resources.device_gamma,
      pw::kBucketCount * sizeof(*resources.device_gamma)));
  CUDA_CHECK(cudaStreamCreateWithFlags(
      &resources.stream, cudaStreamNonBlocking));
  CUDA_CHECK(cudaEventCreate(&resources.source_started));
  CUDA_CHECK(cudaEventCreate(&resources.source_stopped));
  CUDA_CHECK(cudaEventCreate(&resources.transform_started));
  CUDA_CHECK(cudaEventCreate(&resources.transform_stopped));
  const double setup_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - setup_started).count();

  std::uint64_t processed = 0U;
  const psj::IdentityPins identities{
      .resolver_sha256 = *options.resolver_sha256,
      .flint_sha256 = *options.flint_sha256,
  };
  pg2::AuthenticatedChunk chunk;
  while (reader.next(chunk)) {
    for (std::size_t offset = 0U; offset < chunk.records.size(); ++offset) {
      const std::uint64_t logical_block = chunk.first_block + offset;
      if (logical_block < first_target || logical_block > last_target) {
        continue;
      }
      CUDA_CHECK(cudaEventRecord(resources.source_started, resources.stream));
      CUDA_CHECK(cudaMemcpyAsync(
          resources.device_record, &chunk.records[offset],
          sizeof(*resources.device_record), cudaMemcpyHostToDevice,
          resources.stream));
      pgd::launch_synthesize(
          resources.device_record,
          {resources.device_gamma, 1U, pw::kBucketCount, logical_block},
          resources.stream);
      const pda::SourceWindowView skn =
          pda::run_next_source_window(resources.accumulator,
                                      resources.stream);
      if (skn.logical_block != logical_block ||
          skn.stage_count != pw::kTaylorTerms ||
          skn.row_stride != pw::kBucketCount) {
        throw std::runtime_error(
            "qualification Gamma and source accumulator diverged");
      }
      CUDA_CHECK(
          cudaEventRecord(resources.transform_started, resources.stream));
      pdt::run_source_window(resources.transform, resources.device_gamma,
                             skn.device_skn_rows, resources.stream);
      CUDA_CHECK(
          cudaEventRecord(resources.transform_stopped, resources.stream));
      CUDA_CHECK(cudaEventRecord(resources.source_stopped, resources.stream));
      CUDA_CHECK(cudaEventSynchronize(resources.source_stopped));
      float source_milliseconds = 0.0F;
      CUDA_CHECK(cudaEventElapsedTime(
          &source_milliseconds, resources.source_started,
          resources.source_stopped));
      const double source_seconds = source_milliseconds / 1000.0;
      float transform_milliseconds = 0.0F;
      CUDA_CHECK(cudaEventElapsedTime(
          &transform_milliseconds, resources.transform_started,
          resources.transform_stopped));
      const double transform_seconds = transform_milliseconds / 1000.0;

      if (logical_block == options.center_block) {
        for (ViewResult& view : views) {
          if (view.campaign_boundary_rejected) continue;
          const pdt::QualificationRequiredSampleView shifted =
              pdt::device_qualification_required_samples(
                  resources.transform, view.delta);
          if (shifted.begin != view.shifted_begin ||
              shifted.logical_block_delta != view.delta) {
            throw std::runtime_error(
                "bounds-checked shifted view metadata differs");
          }
          view.reuse = scan_and_replay(
              resources.scanner, shifted, resources.stream,
              &view.reuse_scan_replay_seconds);
          if (view.reuse.accepted) {
            view.reuse_junction = resolve_stationary(
                view.target_block, view.reuse, identities,
                &view.reuse_junction_seconds);
          }
          if (view.delta == 0) {
            view.ordinary = view.reuse;
            view.ordinary_junction = view.reuse_junction;
            view.ordinary_scan_replay_seconds =
                view.reuse_scan_replay_seconds;
            view.ordinary_junction_seconds =
                view.reuse_junction_seconds;
            view.ordinary_source_gpu_seconds = source_seconds;
            view.ordinary_transform_gpu_seconds = transform_seconds;
          }
        }
      } else {
        const std::int64_t signed_delta =
            static_cast<std::int64_t>(logical_block) -
            static_cast<std::int64_t>(options.center_block);
        const std::size_t index =
            delta_index(static_cast<std::int32_t>(signed_delta));
        ViewResult& view = views[index];
        if (view.campaign_boundary_rejected ||
            view.target_block != logical_block) {
          throw std::runtime_error(
              "ordinary target does not match qualification delta");
        }
        const pdt::QualificationRequiredSampleView ordinary =
            pdt::device_qualification_required_samples(
                resources.transform, 0);
        view.ordinary = scan_and_replay(
            resources.scanner, ordinary, resources.stream,
            &view.ordinary_scan_replay_seconds);
        if (view.ordinary.accepted) {
          view.ordinary_junction = resolve_stationary(
              view.target_block, view.ordinary, identities,
              &view.ordinary_junction_seconds);
        }
        view.ordinary_source_gpu_seconds = source_seconds;
        view.ordinary_transform_gpu_seconds = transform_seconds;
      }
      ++processed;
    }
  }
  if (!reader.complete() ||
      processed != last_target - first_target + 1U ||
      pda::windows_enqueued(resources.accumulator) != processed) {
    throw std::runtime_error(
        "qualification did not authenticate and process the complete range");
  }

  double center_source_seconds = 0.0;
  double ordinary_source_seconds = 0.0;
  double ordinary_transform_seconds = 0.0;
  double center_transform_seconds = 0.0;
  double ordinary_scan_seconds = 0.0;
  double reuse_scan_seconds = 0.0;
  double ordinary_junction_seconds = 0.0;
  double reuse_junction_seconds = 0.0;
  bool all_eligible_views_accepted = true;
  bool owned_views_accepted = true;
  for (ViewResult& view : views) {
    if (view.campaign_boundary_rejected) continue;
    view.reuse_exact_signs = exact_sign_output(view.reuse);
    view.ordinary_exact_signs = exact_sign_output(view.ordinary);
    view.sign_output_byte_identity =
        vector_bytes_equal(view.reuse_exact_signs,
                           view.ordinary_exact_signs);
    compare_disk_diagnostics(&view);
    view.finite_event_semantics_identity =
        finite_event_output_equal(view.reuse, view.ordinary);
    view.stationary_resolution_semantics_identity =
        junction_semantics_equal(view.reuse_junction,
                                 view.ordinary_junction);
    if (view.reuse_junction.accepted) {
      total_turing_units(
          view.reuse, view.reuse_junction,
          &view.reuse_total_nleft_units,
          &view.reuse_total_nright_units);
    }
    if (view.ordinary_junction.accepted) {
      total_turing_units(
          view.ordinary, view.ordinary_junction,
          &view.ordinary_total_nleft_units,
          &view.ordinary_total_nright_units);
    }
    view.finite_nleft_nright_semantics_identity =
        view.reuse_junction.accepted &&
        view.ordinary_junction.accepted &&
        view.reuse_total_nleft_units ==
            view.ordinary_total_nleft_units &&
        view.reuse_total_nright_units ==
            view.ordinary_total_nright_units;
    view.junction_record_byte_identity =
        bytes_equal(view.reuse_junction.record.data(),
                    view.ordinary_junction.record.data(),
                    view.reuse_junction.record.size());
    view.disk_byte_mismatches =
        disk_byte_mismatch_count(view.reuse, view.ordinary);
    view.artifact_sha256_identity = bytes_equal(
        view.reuse.artifact.status.artifact_sha256,
        view.ordinary.artifact.status.artifact_sha256, 32U);
    const bool view_accepted =
        view.reuse.accepted && view.ordinary.accepted &&
        malformed_count(view.reuse) == 0U &&
        ambiguous_count(view.reuse) == 0U &&
        malformed_count(view.ordinary) == 0U &&
        ambiguous_count(view.ordinary) == 0U &&
        view.sign_output_byte_identity &&
        view.finite_event_semantics_identity &&
        view.stationary_resolution_semantics_identity &&
        view.finite_nleft_nright_semantics_identity;
    all_eligible_views_accepted =
        all_eligible_views_accepted && view_accepted;
    if (view.roster_owned) {
      owned_views_accepted = owned_views_accepted && view_accepted;
      ordinary_source_seconds += view.ordinary_source_gpu_seconds;
      ordinary_transform_seconds +=
          view.ordinary_transform_gpu_seconds;
      ordinary_scan_seconds += view.ordinary_scan_replay_seconds;
      reuse_scan_seconds += view.reuse_scan_replay_seconds;
      ordinary_junction_seconds += view.ordinary_junction_seconds;
      reuse_junction_seconds += view.reuse_junction_seconds;
    }
    if (view.delta == 0) {
      center_source_seconds = view.ordinary_source_gpu_seconds;
      center_transform_seconds =
          view.ordinary_transform_gpu_seconds;
    }
  }
  if (center_source_seconds <= 0.0 ||
      center_transform_seconds <= 0.0) {
    throw std::runtime_error(
        "multiwindow qualification did not measure its center transform");
  }
  const double ordinary_pretransform_seconds =
      std::max(0.0, ordinary_source_seconds -
                        ordinary_transform_seconds);
  const double center_pretransform_seconds =
      std::max(0.0, center_source_seconds -
                        center_transform_seconds);
  const double ordinary_seconds =
      ordinary_pretransform_seconds + ordinary_transform_seconds +
      ordinary_scan_seconds + ordinary_junction_seconds;
  const double reuse_seconds =
      center_pretransform_seconds + center_transform_seconds +
      reuse_scan_seconds + reuse_junction_seconds;
  const double wall_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - wall_started).count();

  std::cout << std::setprecision(17)
            << "{\"schema\":\""
               "sparkinterval.tg.platt-pt21-multiwindow-reuse-qualification.v1\""
            << ",\"accepted\":"
            << (owned_views_accepted ? "true" : "false")
            << ",\"all_geometric_eligible_views_accepted\":"
            << (all_eligible_views_accepted ? "true" : "false")
            << ",\"qualification_only\":true"
            << ",\"build_profile\":{\"cmake_build_config\":\""
            << kCmakeBuildConfig << "\",\"ndebug_defined\":"
            << (kNdebugDefined ? "true" : "false")
            << ",\"release_performance_build\":"
            << (kReleasePerformanceBuild ? "true" : "false") << '}'
            << ",\"claim_scope\":\""
               "exact_lattice_geometry_width_and_finite_event_equivalence\""
            << ",\"center_block\":" << options.center_block
            << ",\"geometric_eligible_view_count\":" << eligible_count
            << ",\"roster_owned_view_count\":" << owned_count
            << ",\"ownership_mask_explicit\":"
            << (options.owned_deltas_explicit ? "true" : "false")
            << ",\"requested_deltas\":[-2,-1,0,1,2]"
            << ",\"sample_shift_per_block\":"
            << pdt::kSourceBlockSampleShift
            << ",\"required_sample_count\":"
            << pdt::kSourceRequiredCount
            << ",\"transform_sample_count\":"
            << pdt::kSourceSampleCount
            << ",\"authenticated_stream_first_block\":"
            << stream_first
            << ",\"authenticated_stream_block_count\":"
            << stream_count
            << ",\"authenticated_stream_sha256\":\""
            << sparkinterval::lowercase_hex(reader.stream_sha256()) << "\""
            << ",\"processed_independent_block_count\":" << processed
            << ",\"setup_seconds\":" << setup_seconds
            << ",\"ordinary_gamma_accumulator_transform_gpu_seconds\":"
            << ordinary_source_seconds
            << ",\"ordinary_gamma_accumulator_pretransform_gpu_seconds\":"
            << ordinary_pretransform_seconds
            << ",\"ordinary_transform_only_gpu_seconds\":"
            << ordinary_transform_seconds
            << ",\"reuse_transform_only_gpu_seconds\":"
            << center_transform_seconds
            << ",\"transform_only_speedup\":"
            << ordinary_transform_seconds / center_transform_seconds
            << ",\"measured_transform_invocation_reduction_fraction\":"
            << 1.0 - 1.0 / owned_count
            << ",\"ordinary_fixed_integer_scan_replay_seconds\":"
            << ordinary_scan_seconds
            << ",\"ordinary_flint_junction_seconds\":"
            << ordinary_junction_seconds
            << ",\"ordinary_finite_stage_observed_seconds\":"
            << ordinary_seconds
            << ",\"ordinary_finite_stage_views_per_second\":"
            << owned_count / ordinary_seconds
            << ",\"reuse_center_gamma_accumulator_transform_gpu_seconds\":"
            << center_source_seconds
            << ",\"reuse_center_gamma_accumulator_pretransform_gpu_seconds\":"
            << center_pretransform_seconds
            << ",\"reuse_fixed_integer_scan_replay_seconds\":"
            << reuse_scan_seconds
            << ",\"reuse_flint_junction_seconds\":"
            << reuse_junction_seconds
            << ",\"reuse_finite_stage_counterfactual_seconds\":"
            << reuse_seconds
            << ",\"reuse_finite_stage_counterfactual_views_per_second\":"
            << owned_count / reuse_seconds
            << ",\"finite_stage_counterfactual_speedup\":"
            << ordinary_seconds / reuse_seconds
            << ",\"whole_pipeline_speedup_claimed\":false"
            << ",\"source_stage_timer_includes_transform\":true"
            << ",\"accumulator_stride_skip_implemented\":false"
            << ",\"accumulator_stride_skip_kat_complete\":false"
            << ",\"q192_anchor_stride_refinement_proved\":false"
            << ",\"actual_qualification_wall_seconds\":"
            << wall_seconds
            << ",\"views\":[";
  bool first = true;
  for (const ViewResult& view : views) {
    if (!first) std::cout << ',';
    first = false;
    std::cout << "{\"delta\":" << view.delta
              << ",\"shifted_begin\":" << view.shifted_begin
              << ",\"campaign_boundary_rejected\":"
              << (view.campaign_boundary_rejected ? "true" : "false");
    if (!view.campaign_boundary_rejected) {
      std::cout << ",\"target_block\":" << view.target_block
                << ",\"roster_owned\":"
                << (view.roster_owned ? "true" : "false")
                << ",\"reuse_invalid_disks\":"
                << malformed_count(view.reuse)
                << ",\"reuse_ambiguous_disks\":"
                << ambiguous_count(view.reuse)
                << ",\"ordinary_invalid_disks\":"
                << malformed_count(view.ordinary)
                << ",\"ordinary_ambiguous_disks\":"
                << ambiguous_count(view.ordinary)
                << ",\"reuse_failure_flags\":"
                << view.reuse.artifact.status.failure_flags
                << ",\"ordinary_failure_flags\":"
                << view.ordinary.artifact.status.failure_flags
                << ",\"reuse_junction_accepted\":"
                << (view.reuse_junction.accepted ? "true" : "false")
                << ",\"ordinary_junction_accepted\":"
                << (view.ordinary_junction.accepted ? "true" : "false")
                << ",\"reuse_maximum_radius\":"
                << maximum_radius(view.reuse)
                << ",\"ordinary_maximum_radius\":"
                << maximum_radius(view.ordinary)
                << ",\"sign_output_byte_identity\":"
                << (view.sign_output_byte_identity ? "true" : "false")
                << ",\"reuse_certified_sign_count\":"
                << view.reused_certified_sign_count
                << ",\"certified_overlap_sign_mismatches\":"
                << view.certified_overlap_sign_mismatches
                << ",\"disk_interval_disjoint_count\":"
                << view.disk_interval_disjoint_count
                << ",\"valid_zero_containment_failure\":"
                << (malformed_count(view.reuse) == 0U &&
                            ambiguous_count(view.reuse) != 0U
                        ? "true" : "false")
                << ",\"certified_sign_orientation_agrees\":"
                << (view.reused_certified_sign_count != 0U &&
                            view.certified_overlap_sign_mismatches == 0U
                        ? "true" : "false")
                << ",\"finite_event_semantics_identity\":"
                << (view.finite_event_semantics_identity ? "true"
                                                         : "false")
                << ",\"finite_event_comparator_omits_endpoint_disk_bytes\":true"
                << ",\"stationary_resolution_semantics_identity\":"
                << (view.stationary_resolution_semantics_identity
                        ? "true" : "false")
                << ",\"finite_nleft_nright_semantics_identity\":"
                << (view.finite_nleft_nright_semantics_identity
                        ? "true" : "false")
                << ",\"junction_record_byte_identity\":"
                << (view.junction_record_byte_identity ? "true"
                                                       : "false")
                << ",\"disk_byte_mismatches\":"
                << view.disk_byte_mismatches
                << ",\"artifact_sha256_identity\":"
                << (view.artifact_sha256_identity ? "true" : "false")
                << ",\"direct_events\":"
                << direct_event_count(view.reuse)
                << ",\"stationary_candidates\":"
                << stationary_candidate_count(view.reuse)
                << ",\"reuse_scan_replay_seconds\":"
                << view.reuse_scan_replay_seconds
                << ",\"ordinary_scan_replay_seconds\":"
                << view.ordinary_scan_replay_seconds
                << ",\"ordinary_gamma_accumulator_transform_gpu_seconds\":"
                << view.ordinary_source_gpu_seconds
                << ",\"ordinary_transform_only_gpu_seconds\":"
                << view.ordinary_transform_gpu_seconds
                << ",\"reuse_flint_junction_seconds\":"
                << view.reuse_junction_seconds
                << ",\"ordinary_flint_junction_seconds\":"
                << view.ordinary_junction_seconds
                << ",\"resolved_multiplicity_slots\":"
                << (view.reuse_junction.accepted
                        ? psj::decode_record(
                              view.reuse_junction.record)
                              .resolved_multiplicity_slots
                        : 0U)
                << ",\"total_nleft_units\":["
                << view.reuse_total_nleft_units[0] << ','
                << view.reuse_total_nleft_units[1] << ','
                << view.reuse_total_nleft_units[2] << ']'
                << ",\"total_nright_units\":["
                << view.reuse_total_nright_units[0] << ','
                << view.reuse_total_nright_units[1] << ','
                << view.reuse_total_nright_units[2] << ']';
    }
    std::cout << '}';
  }
  std::cout
      << "]"
      << ",\"bounds_checked_transform_accessor\":true"
      << ",\"arbitrary_pointer_arithmetic_used\":false"
      << ",\"event_scanner_device_replay_complete\":true"
      << ",\"fixed_2176_bit_host_replay_complete\":true"
      << ",\"independently_centered_event_comparison_complete\":true"
      << ",\"resolver_sha256\":\""
      << sparkinterval::lowercase_hex(*options.resolver_sha256) << "\""
      << ",\"flint_sha256\":\""
      << sparkinterval::lowercase_hex(*options.flint_sha256) << "\""
      << ",\"resolver_sha256_self_verified\":false"
      << ",\"flint_sha256_self_verified\":false"
      << ",\"identity_pins_require_external_manifest_or_attestation\":true"
      << ",\"disk_byte_identity_required_for_acceptance\":false"
      << ",\"disk_byte_identity_semantics\":\""
         "diagnostic_only_distinct_outward_enclosures_may_differ\""
      << ",\"center_dependent_positive_gaussian_weighting\":true"
      << ",\"raw_gaussian_weighted_interval_overlap_expected\":false"
      << ",\"gaussian_rescaling_normalization_implemented\":false"
      << ",\"normalized_disk_equivalence_checked\":false"
      << ",\"hardy_z_endpoint_realization_proved\":false"
      << ",\"flint_to_mathlib_realization_proved\":false"
      << ",\"analytic_turing_realization_proved\":false"
      << ",\"campaign_partition_implemented\":false"
      << ",\"full_campaign_qualified\":false"
      << ",\"source_claim_ready\":false"
      << ",\"production_ready\":false"
      << ",\"pt21_atom_discharged\":false}\n";
  return owned_views_accepted ? 0 : 3;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-pt21-multiwindow-reuse: "
              << error.what() << '\n';
    return 2;
  }
}

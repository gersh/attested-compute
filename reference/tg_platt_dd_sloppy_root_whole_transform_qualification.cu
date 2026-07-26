// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only whole-transform experiment for bounded sloppy-DD root
// multiplication.  This executable emits no production/source certificate.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"

#include <cuda_runtime.h>

#include <boost/multiprecision/cpp_int.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstddef>
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

#if !defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) || \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION != 1
#error "whole-transform sloppy-root runner is qualification-only"
#endif

#if !defined(SPARKINTERVAL_CUDA_FTZ_DISABLED) || \
    SPARKINTERVAL_CUDA_FTZ_DISABLED != 1
#error "whole-transform sloppy-root qualification requires --ftz=false"
#endif

namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pw = sparkinterval::tg::platt_windowed;

using boost::multiprecision::cpp_int;
using boost::multiprecision::cpp_rational;

namespace {

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

constexpr std::string_view kBuildProfile = SPARKINTERVAL_CMAKE_BUILD_CONFIG;
#ifdef NDEBUG
constexpr bool kNdebugDefined = true;
#else
constexpr bool kNdebugDefined = false;
#endif
constexpr bool kReleasePerformanceBuild =
    kNdebugDefined && kBuildProfile == "Release";
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
constexpr bool kStrictH100Target = true;
#else
constexpr bool kStrictH100Target = false;
#endif
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
constexpr bool kTile9SloppyRootCandidate = true;
#else
constexpr bool kTile9SloppyRootCandidate = false;
#endif

constexpr std::string_view kRequiredPacketSha256 =
    "caecf8faee55a1c969062bb5d85cbd50"
    "ff70b0f461778e3fcb7fd0d561a058b7";
constexpr std::uint64_t kRequiredPacketBytes = 31'457'408ULL;
constexpr std::uint64_t kRequiredPacketLegacyChecksum64 =
    0x39d3821666d7af35ULL;
constexpr std::uint64_t kOrdinaryGenuineLegacyChecksum64 =
    0xa7b7b42ab245b042ULL;
constexpr std::uint64_t kOrdinaryFiniteEdgeLegacyChecksum64 =
    0xf581990198bdc555ULL;
constexpr std::string_view kOrdinaryGenuineOutputSha256 =
    "81e54dc8806211ecc5c69b484076cd28"
    "ba1a0ab56a62a6fc8158ec84972b5a3e";
constexpr std::string_view kOrdinaryFiniteEdgeOutputSha256 =
    "72ba9bacc3a312ae18c5d423388beae5"
    "2a621f3c81e37a1a006d91acc6d6a713";
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
constexpr std::string_view kSettledSloppyGenuineOutputSha256 =
    "7d24ab69c3f2851809e13ab6d9a59434"
    "5c75f26423ca5a9fea136e7a1b861a0e";
constexpr std::string_view kSettledSloppyFiniteEdgeOutputSha256 =
    "adc7cfb2cdd84556b051d4037cc52afc"
    "93b3e44b1ce7024c8bdae8e635ea12cc";
#endif
constexpr std::uint64_t kExpectedDirectEvents = 3'539ULL;
constexpr std::uint64_t kExpectedStationaryEvents = 1ULL;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                  \
    }                                                                        \
  } while (0)

struct Options {
  std::string source_packet;
  sparkinterval::Sha256Digest expected_source_packet_sha256{};
  std::uint32_t repetitions = 9U;
};

struct DeviceProfile {
  std::string name;
  int major = 0;
  int minor = 0;
  bool is_h100_sm90 = false;
};

DeviceProfile require_and_read_device_profile() {
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
  DeviceProfile result{
      .name = properties.name,
      .major = properties.major,
      .minor = properties.minor,
      .is_h100_sm90 =
          properties.major == 9 && properties.minor == 0 &&
          std::string_view(properties.name).find("H100") !=
              std::string_view::npos,
  };
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (!result.is_h100_sm90) {
    throw std::runtime_error(
        "strict sloppy-root qualification target requires NVIDIA H100 sm_90");
  }
#endif
  return result;
}

unsigned int hex_nibble(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10U;
  throw std::runtime_error("source packet SHA-256 is not hexadecimal");
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error(
        "source packet SHA-256 must contain 64 hexadecimal digits");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    result[index] = static_cast<unsigned char>(
        (hex_nibble(text[2U * index]) << 4U) |
        hex_nibble(text[2U * index + 1U]));
  }
  return result;
}

std::uint32_t parse_repetitions(std::string_view text) {
  std::uint32_t value = 0U;
  const auto parsed =
      std::from_chars(text.data(), text.data() + text.size(), value);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != text.data() + text.size() || value == 0U ||
      value > 101U) {
    throw std::runtime_error("repetitions must be in [1,101]");
  }
  return value;
}

Options parse_options(int argc, char** argv) {
  std::optional<std::string> source_packet;
  std::optional<sparkinterval::Sha256Digest> expected_sha256;
  std::uint32_t repetitions = 9U;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    constexpr std::string_view packet_prefix = "--source-packet=";
    constexpr std::string_view sha_prefix =
        "--expected-source-packet-sha256=";
    constexpr std::string_view repetitions_prefix = "--repetitions=";
    if (argument.starts_with(packet_prefix)) {
      if (source_packet.has_value()) {
        throw std::runtime_error("source packet is duplicated");
      }
      source_packet = std::string(argument.substr(packet_prefix.size()));
      if (source_packet->empty()) {
        throw std::runtime_error("source packet path is empty");
      }
    } else if (argument.starts_with(sha_prefix)) {
      if (expected_sha256.has_value()) {
        throw std::runtime_error("expected source packet SHA-256 is duplicated");
      }
      expected_sha256 = parse_sha256(argument.substr(sha_prefix.size()));
    } else if (argument.starts_with(repetitions_prefix)) {
      repetitions =
          parse_repetitions(argument.substr(repetitions_prefix.size()));
    } else {
      throw std::runtime_error(
          "usage: tg-platt-dd-sloppy-root-whole-transform-qualification "
          "--source-packet=PT21SRC2 "
          "--expected-source-packet-sha256=HEX [--repetitions=N]");
    }
  }
  if (!source_packet.has_value() || !expected_sha256.has_value()) {
    throw std::runtime_error(
        "the exact source packet and its caller-supplied SHA-256 pin are "
        "mandatory");
  }
  const sparkinterval::Sha256Digest required =
      parse_sha256(kRequiredPacketSha256);
  if (*expected_sha256 != required) {
    throw std::runtime_error(
        "caller SHA-256 is not the qualified complete block-0 packet pin");
  }
  return {*source_packet, *expected_sha256, repetitions};
}

// Historical PT21 packets and known answers called this FNV-1a-64, but the
// project used the nonstandard offset 1,469,598,103,934,665,603.  Preserve
// those bytes and pins while naming the checksum accurately here.
std::uint64_t legacy_pt21_checksum(const void* raw, std::size_t size) {
  const auto* bytes = static_cast<const unsigned char*>(raw);
  std::uint64_t value = 1'469'598'103'934'665'603ULL;
  for (std::size_t index = 0U; index < size; ++index) {
    value ^= bytes[index];
    value *= 1'099'511'628'211ULL;
  }
  return value;
}

struct InputCase {
  std::string label;
  std::vector<pw::ComplexDisk106> gamma;
  std::vector<pw::ComplexDisk106> skn;
  bool genuine = false;
  std::uint64_t packet_bytes = 0U;
  std::uint64_t packet_legacy_checksum64 = 0U;
  std::string packet_sha256;
};

bool valid_complex_disk(const pw::ComplexDisk106& value) {
  return std::isfinite(value.real.hi) &&
         std::isfinite(value.real.lo) &&
         std::isfinite(value.imaginary.hi) &&
         std::isfinite(value.imaginary.lo) &&
         std::isfinite(value.radius) && value.radius >= 0.0;
}

InputCase load_genuine_block0(
    const std::string& path,
    const sparkinterval::Sha256Digest& expected_sha256) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "PT21 whole-transform qualification requires little endian");
  }
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open source packet");
  const std::streampos end = input.tellg();
  if (end < 0 ||
      static_cast<std::uint64_t>(end) != kRequiredPacketBytes) {
    throw std::runtime_error(
        "source packet size differs from the exact qualified fixture");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  if (!input || input.peek() != std::ifstream::traits_type::eof() ||
      bytes.size() < sizeof(pw::SourcePacketHeader)) {
    throw std::runtime_error("cannot read the complete source packet");
  }
  const sparkinterval::Sha256Digest actual_sha256 =
      sparkinterval::sha256(bytes.data(), bytes.size());
  if (actual_sha256 != expected_sha256 ||
      sparkinterval::lowercase_hex(actual_sha256) != kRequiredPacketSha256 ||
      bytes.size() != kRequiredPacketBytes ||
      legacy_pt21_checksum(bytes.data(), bytes.size()) !=
          kRequiredPacketLegacyChecksum64) {
    throw std::runtime_error(
        "source packet bytes differ from the exact qualified block-0 fixture");
  }

  pw::SourcePacketHeader header{};
  std::memcpy(&header, bytes.data(), sizeof(header));
  const std::uint64_t skn_count =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  const std::uint64_t payload_bytes =
      (pw::kBucketCount + skn_count) * sizeof(pw::ComplexDisk106);
  if (header.magic != pw::kSourcePacket106Magic ||
      header.version != pw::kSourcePacket106Version ||
      header.header_bytes != sizeof(header) ||
      header.endian_tag != pw::kSourcePacketEndianTag ||
      header.interval_encoding != pw::kSourcePacket106Encoding ||
      header.bucket_count != pw::kBucketCount ||
      header.taylor_terms != pw::kTaylorTerms ||
      header.source_terms != pw::kSourceTerms ||
      header.reserved_zero != 0U ||
      header.window_center != pw::kSourceLower + pw::kWindowStep / 2U ||
      header.gamma_count != pw::kBucketCount ||
      header.skn_count != skn_count ||
      header.payload_bytes != payload_bytes ||
      bytes.size() != sizeof(header) + payload_bytes ||
      std::memcmp(header.upstream_commit.data(), pw::kUpstreamCommit,
                  header.upstream_commit.size()) != 0) {
    throw std::runtime_error(
        "source packet is not the exact complete block-0 PT21SRC2 schema");
  }

  InputCase result;
  result.label = "genuine-complete-block0";
  result.genuine = true;
  result.packet_bytes = bytes.size();
  result.packet_legacy_checksum64 =
      legacy_pt21_checksum(bytes.data(), bytes.size());
  result.packet_sha256 = sparkinterval::lowercase_hex(actual_sha256);
  result.gamma.resize(pw::kBucketCount);
  result.skn.resize(skn_count);
  std::size_t offset = sizeof(header);
  const std::size_t gamma_bytes =
      result.gamma.size() * sizeof(pw::ComplexDisk106);
  std::memcpy(result.gamma.data(), bytes.data() + offset, gamma_bytes);
  offset += gamma_bytes;
  const std::size_t skn_bytes =
      result.skn.size() * sizeof(pw::ComplexDisk106);
  std::memcpy(result.skn.data(), bytes.data() + offset, skn_bytes);
  if (legacy_pt21_checksum(result.gamma.data(), gamma_bytes) !=
          header.gamma_fnv1a64 ||
      legacy_pt21_checksum(result.skn.data(), skn_bytes) !=
          header.skn_fnv1a64) {
    throw std::runtime_error(
        "source packet embedded Gamma/Skn FNV commitments differ");
  }
  if (!std::all_of(
          result.gamma.begin(), result.gamma.end(), valid_complex_disk) ||
      !std::all_of(
          result.skn.begin(), result.skn.end(), valid_complex_disk)) {
    throw std::runtime_error("source packet contains a malformed DD disk");
  }
  return result;
}

InputCase finite_edge_case() {
  InputCase result;
  result.label = "synthetic-finite-edge-overlap-only";
  result.gamma.resize(pw::kBucketCount);
  result.skn.resize(
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount);
  constexpr double least_subnormal =
      std::numeric_limits<double>::denorm_min();
  auto initialize = [](std::vector<pw::ComplexDisk106>* values,
                       std::uint64_t salt) {
    for (std::uint64_t index = 0U; index < values->size(); ++index) {
      pw::ComplexDisk106 value{};
      const bool negative = ((index + salt) & 1U) != 0U;
      const double sign = negative ? -1.0 : 1.0;
      if (index % 257U == salt % 257U) {
        value.real.hi =
            sign * std::ldexp(1.0 + static_cast<double>(index % 7U), -500);
        value.real.lo = sign * least_subnormal;
        value.imaginary.hi =
            -sign * std::ldexp(1.0 + static_cast<double>(index % 5U), -520);
        value.imaginary.lo = -sign * least_subnormal;
        value.radius = least_subnormal;
      } else {
        value.real.hi = negative ? -0.0 : 0.0;
        value.real.lo = negative ? 0.0 : -0.0;
        value.imaginary.hi = negative ? 0.0 : -0.0;
        value.imaginary.lo = negative ? -0.0 : 0.0;
        value.radius = 0.0;
      }
      (*values)[index] = value;
    }
  };
  initialize(&result.gamma, 17U);
  initialize(&result.skn, 89U);
  return result;
}

InputCase finite_overflow_control_case() {
  InputCase result;
  result.label = "synthetic-finite-overflow-negative-control";
  result.gamma.resize(pw::kBucketCount);
  result.skn.resize(
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount);
  pw::ComplexDisk106 provoking{};
  provoking.real.hi = std::numeric_limits<double>::max();
  provoking.real.lo = 0.0;
  provoking.imaginary.hi = std::numeric_limits<double>::max();
  provoking.imaginary.lo = 0.0;
  provoking.radius = 0.0;
  std::fill(result.gamma.begin(), result.gamma.end(), provoking);
  return result;
}

cpp_rational pow2(std::uint32_t exponent) {
  return cpp_rational(cpp_int(1) << exponent);
}

std::optional<cpp_rational> decode_finite(double value) {
  const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
  const bool negative = (bits >> 63U) != 0U;
  const std::uint32_t raw_exponent =
      static_cast<std::uint32_t>((bits >> 52U) & 0x7ffU);
  const std::uint64_t fraction = bits & ((1ULL << 52U) - 1U);
  if (raw_exponent == 0x7ffU) return std::nullopt;
  if (raw_exponent == 0U && fraction == 0U) return cpp_rational(0);
  cpp_int significand;
  std::int32_t exponent;
  if (raw_exponent == 0U) {
    significand = fraction;
    exponent = -1074;
  } else {
    significand = (cpp_int(1) << 52U) + fraction;
    exponent = static_cast<std::int32_t>(raw_exponent) - 1023 - 52;
  }
  cpp_rational result(significand);
  if (exponent >= 0) {
    result *= pow2(static_cast<std::uint32_t>(exponent));
  } else {
    result /= pow2(static_cast<std::uint32_t>(-exponent));
  }
  return negative ? -result : result;
}

cpp_rational decode_or_throw(double value) {
  const std::optional<cpp_rational> decoded = decode_finite(value);
  if (!decoded.has_value()) {
    throw std::runtime_error("exact checker received nonfinite binary64");
  }
  return *decoded;
}

cpp_rational decode_dd(pw::DoubleDouble value) {
  return decode_or_throw(value.hi) + decode_or_throw(value.lo);
}

struct ContainmentResult {
  std::uint64_t checked = 0U;
  std::uint64_t malformed = 0U;
  std::uint64_t radius_order_failures = 0U;
  std::uint64_t squared_distance_failures = 0U;
  std::uint64_t first_failure = std::numeric_limits<std::uint64_t>::max();

  bool accepted() const {
    return checked == pdt::kSourceSampleCount && malformed == 0U &&
           radius_order_failures == 0U &&
           squared_distance_failures == 0U;
  }
};

ContainmentResult exact_all_sample_containment(
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate) {
  if (ordinary.size() != pdt::kSourceSampleCount ||
      candidate.size() != pdt::kSourceSampleCount) {
    throw std::runtime_error("wrong whole-transform output size");
  }
  ContainmentResult result;
  for (std::size_t index = 0U; index < ordinary.size(); ++index) {
    ++result.checked;
    try {
      const cpp_rational ordinary_center =
          decode_dd(ordinary[index].center);
      const cpp_rational candidate_center =
          decode_dd(candidate[index].center);
      const cpp_rational ordinary_radius =
          decode_or_throw(ordinary[index].radius);
      const cpp_rational candidate_radius =
          decode_or_throw(candidate[index].radius);
      if (ordinary_radius < 0 || candidate_radius < 0) {
        ++result.malformed;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
        continue;
      }
      const cpp_rational radius_difference =
          candidate_radius - ordinary_radius;
      if (radius_difference < 0) {
        ++result.radius_order_failures;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
        continue;
      }
      const cpp_rational center_difference =
          candidate_center - ordinary_center;
      // For real Euclidean disks this is exactly the disk-containment
      // obligation requested by the qualification: r_fast >= r_full and
      // |c_fast-c_full|^2 <= (r_fast-r_full)^2.
      if (center_difference * center_difference >
          radius_difference * radius_difference) {
        ++result.squared_distance_failures;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
      }
    } catch (const std::exception&) {
      ++result.malformed;
      if (result.first_failure ==
          std::numeric_limits<std::uint64_t>::max()) {
        result.first_failure = index;
      }
    }
  }
  return result;
}

struct OverlapResult {
  std::uint64_t checked = 0U;
  std::uint64_t malformed = 0U;
  std::uint64_t squared_distance_failures = 0U;
  std::uint64_t first_failure = std::numeric_limits<std::uint64_t>::max();

  bool accepted() const {
    return checked == pdt::kSourceSampleCount && malformed == 0U &&
           squared_distance_failures == 0U;
  }
};

OverlapResult exact_all_sample_overlap(
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate) {
  if (ordinary.size() != pdt::kSourceSampleCount ||
      candidate.size() != pdt::kSourceSampleCount) {
    throw std::runtime_error("wrong whole-transform output size");
  }
  OverlapResult result;
  for (std::size_t index = 0U; index < ordinary.size(); ++index) {
    ++result.checked;
    try {
      const cpp_rational ordinary_center =
          decode_dd(ordinary[index].center);
      const cpp_rational candidate_center =
          decode_dd(candidate[index].center);
      const cpp_rational ordinary_radius =
          decode_or_throw(ordinary[index].radius);
      const cpp_rational candidate_radius =
          decode_or_throw(candidate[index].radius);
      if (ordinary_radius < 0 || candidate_radius < 0) {
        ++result.malformed;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
        continue;
      }
      const cpp_rational center_difference =
          candidate_center - ordinary_center;
      const cpp_rational radius_sum =
          candidate_radius + ordinary_radius;
      if (center_difference * center_difference >
          radius_sum * radius_sum) {
        ++result.squared_distance_failures;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
      }
    } catch (const std::exception&) {
      ++result.malformed;
      if (result.first_failure ==
          std::numeric_limits<std::uint64_t>::max()) {
        result.first_failure = index;
      }
    }
  }
  return result;
}

struct RootAudit {
  std::uint64_t count = 0U;
  std::uint64_t malformed_root_count = 0U;
  std::uint64_t malformed_norm_count = 0U;
  std::uint64_t center_norm_bound_failure_count = 0U;
  std::uint64_t first_failure = std::numeric_limits<std::uint64_t>::max();

  bool accepted() const {
    return count == pw::kBucketCount && malformed_root_count == 0U &&
           malformed_norm_count == 0U &&
           center_norm_bound_failure_count == 0U;
  }
};

RootAudit exact_root_table_audit(
    const std::vector<pw::ComplexDisk106>& roots,
    const std::vector<double>& center_norm_upper) {
  if (roots.size() != center_norm_upper.size()) {
    throw std::runtime_error("root/norm table sizes differ");
  }
  RootAudit result;
  result.count = roots.size();
  for (std::size_t index = 0U; index < roots.size(); ++index) {
    try {
      const cpp_rational real = decode_dd(roots[index].real);
      const cpp_rational imaginary = decode_dd(roots[index].imaginary);
      const cpp_rational radius = decode_or_throw(roots[index].radius);
      if (radius < 0) {
        ++result.malformed_root_count;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
      }
      const cpp_rational norm =
          decode_or_throw(center_norm_upper[index]);
      if (norm < 0) {
        ++result.malformed_norm_count;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
      } else if (real * real + imaginary * imaginary > norm * norm) {
        ++result.center_norm_bound_failure_count;
        if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max()) {
          result.first_failure = index;
        }
      }
    } catch (const std::exception&) {
      if (!valid_complex_disk(roots[index])) {
        ++result.malformed_root_count;
      }
      if (!std::isfinite(center_norm_upper[index]) ||
          center_norm_upper[index] < 0.0) {
        ++result.malformed_norm_count;
      }
      if (result.first_failure ==
          std::numeric_limits<std::uint64_t>::max()) {
        result.first_failure = index;
      }
    }
  }
  return result;
}

struct RootTableQualification {
  RootAudit ordinary;
  bool ordinary_candidate_table_byte_equal = false;
  bool candidate_settled_sloppy_table_byte_equal = false;
  bool bad_norm_mutation_rejected = false;
  std::uint64_t mutated_index =
      std::numeric_limits<std::uint64_t>::max();
  std::uint64_t mutation_failure_count = 0U;
};

struct SignCounts {
  std::uint64_t positive = 0U;
  std::uint64_t negative = 0U;
  std::uint64_t ambiguous = 0U;
  std::uint64_t malformed = 0U;
};

enum class ExactSign : std::uint8_t {
  kPositive,
  kNegative,
  kAmbiguous,
  kMalformed,
};

ExactSign exact_sign(const pw::RealDisk106& disk) {
  try {
    const cpp_rational center = decode_dd(disk.center);
    const cpp_rational radius = decode_or_throw(disk.radius);
    if (radius < 0) return ExactSign::kMalformed;
    if (center - radius > 0) return ExactSign::kPositive;
    if (center + radius < 0) return ExactSign::kNegative;
    return ExactSign::kAmbiguous;
  } catch (const std::exception&) {
    return ExactSign::kMalformed;
  }
}

SignCounts exact_sign_counts(
    const std::vector<pw::RealDisk106>& samples,
    std::size_t begin, std::size_t count) {
  if (begin > samples.size() || count > samples.size() - begin) {
    throw std::runtime_error("sign-count view is outside sample array");
  }
  SignCounts result;
  for (std::size_t index = begin; index < begin + count; ++index) {
    switch (exact_sign(samples[index])) {
      case ExactSign::kPositive:
        ++result.positive;
        break;
      case ExactSign::kNegative:
        ++result.negative;
        break;
      case ExactSign::kAmbiguous:
        ++result.ambiguous;
        break;
      case ExactSign::kMalformed:
        ++result.malformed;
        break;
    }
  }
  return result;
}

std::uint64_t exact_sign_mismatch_count(
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate,
    std::size_t begin, std::size_t count) {
  std::uint64_t result = 0U;
  for (std::size_t index = begin; index < begin + count; ++index) {
    if (exact_sign(ordinary[index]) != exact_sign(candidate[index])) {
      ++result;
    }
  }
  return result;
}

struct RadiusDistribution {
  std::uint64_t finite_ratio_count = 0U;
  std::uint64_t zero_ordinary_radius_count = 0U;
  double median = 0.0;
  double p90 = 0.0;
  double p99 = 0.0;
  double maximum = 0.0;
  double ordinary_maximum_radius = 0.0;
  double candidate_maximum_radius = 0.0;
};

double quantile(const std::vector<double>& sorted, double probability) {
  if (sorted.empty()) return 0.0;
  const std::size_t index = static_cast<std::size_t>(
      probability * static_cast<double>(sorted.size() - 1U));
  return sorted[index];
}

RadiusDistribution radius_distribution(
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate) {
  RadiusDistribution result;
  std::vector<double> ratios;
  ratios.reserve(ordinary.size());
  for (std::size_t index = 0U; index < ordinary.size(); ++index) {
    result.ordinary_maximum_radius =
        std::max(result.ordinary_maximum_radius, ordinary[index].radius);
    result.candidate_maximum_radius =
        std::max(result.candidate_maximum_radius, candidate[index].radius);
    if (ordinary[index].radius == 0.0) {
      ++result.zero_ordinary_radius_count;
    } else {
      const double ratio =
          candidate[index].radius / ordinary[index].radius;
      if (std::isfinite(ratio)) ratios.push_back(ratio);
    }
  }
  std::sort(ratios.begin(), ratios.end());
  result.finite_ratio_count = ratios.size();
  result.median = quantile(ratios, 0.50);
  result.p90 = quantile(ratios, 0.90);
  result.p99 = quantile(ratios, 0.99);
  result.maximum = ratios.empty() ? 0.0 : ratios.back();
  return result;
}

struct Resources {
  pw::ComplexDisk106* device_gamma = nullptr;
  pw::ComplexDisk106* device_skn = nullptr;
  pdt::Workspace* ordinary = nullptr;
  pdt::Workspace* candidate = nullptr;
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  pdt::Workspace* settled_sloppy = nullptr;
#endif
  pes::Workspace* ordinary_scanner = nullptr;
  pes::Workspace* candidate_scanner = nullptr;
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  pes::Workspace* settled_sloppy_scanner = nullptr;
#endif
  cudaStream_t stream = nullptr;
  cudaEvent_t started = nullptr;
  cudaEvent_t stopped = nullptr;

  ~Resources() {
    if (stream != nullptr) cudaStreamSynchronize(stream);
    if (started != nullptr) cudaEventDestroy(started);
    if (stopped != nullptr) cudaEventDestroy(stopped);
    if (ordinary_scanner != nullptr) {
      pes::destroy_workspace(ordinary_scanner);
    }
    if (candidate_scanner != nullptr) {
      pes::destroy_workspace(candidate_scanner);
    }
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
    if (settled_sloppy_scanner != nullptr) {
      pes::destroy_workspace(settled_sloppy_scanner);
    }
#endif
    if (ordinary != nullptr) pdt::destroy_workspace(ordinary);
    if (candidate != nullptr) pdt::destroy_workspace(candidate);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
    if (settled_sloppy != nullptr) {
      pdt::destroy_workspace(settled_sloppy);
    }
#endif
    if (device_gamma != nullptr) cudaFree(device_gamma);
    if (device_skn != nullptr) cudaFree(device_skn);
    if (stream != nullptr) cudaStreamDestroy(stream);
  }
};

void initialize(Resources* resources) {
  const std::uint64_t skn_count =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  CUDA_CHECK(cudaMalloc(
      &resources->device_gamma,
      pw::kBucketCount * sizeof(*resources->device_gamma)));
  CUDA_CHECK(cudaMalloc(
      &resources->device_skn,
      skn_count * sizeof(*resources->device_skn)));
  resources->ordinary = pdt::create_source_workspace();
  resources->candidate = pdt::create_source_workspace();
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  resources->settled_sloppy = pdt::create_source_workspace();
#endif
  resources->ordinary_scanner = pes::create_workspace();
  resources->candidate_scanner = pes::create_workspace();
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  resources->settled_sloppy_scanner = pes::create_workspace();
#endif
  CUDA_CHECK(cudaStreamCreateWithFlags(
      &resources->stream, cudaStreamNonBlocking));
  CUDA_CHECK(cudaEventCreate(&resources->started));
  CUDA_CHECK(cudaEventCreate(&resources->stopped));
}

void upload(const InputCase& input, Resources* resources) {
  CUDA_CHECK(cudaMemcpyAsync(
      resources->device_gamma, input.gamma.data(),
      input.gamma.size() * sizeof(pw::ComplexDisk106),
      cudaMemcpyHostToDevice, resources->stream));
  CUDA_CHECK(cudaMemcpyAsync(
      resources->device_skn, input.skn.data(),
      input.skn.size() * sizeof(pw::ComplexDisk106),
      cudaMemcpyHostToDevice, resources->stream));
  CUDA_CHECK(cudaStreamSynchronize(resources->stream));
}

void run_ordinary(Resources* resources) {
  pdt::run_source_window(
      resources->ordinary, resources->device_gamma,
      resources->device_skn, resources->stream);
}

void run_candidate(Resources* resources) {
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  pdt::run_source_window_tile9_sloppy_root_qualification(
      resources->candidate, resources->device_gamma,
      resources->device_skn, resources->stream);
#else
  pdt::run_source_window_sloppy_root_qualification(
      resources->candidate, resources->device_gamma,
      resources->device_skn, resources->stream);
#endif
}

void run_settled_sloppy(Resources* resources) {
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  pdt::run_source_window_sloppy_root_qualification(
      resources->settled_sloppy, resources->device_gamma,
      resources->device_skn, resources->stream);
#else
  run_candidate(resources);
#endif
}

enum class RunKind : std::uint8_t {
  kOrdinary,
  kCandidate,
  kSettledSloppy,
};

double timed_run(Resources* resources, RunKind kind) {
  CUDA_CHECK(cudaEventRecord(resources->started, resources->stream));
  switch (kind) {
    case RunKind::kOrdinary:
      run_ordinary(resources);
      break;
    case RunKind::kCandidate:
      run_candidate(resources);
      break;
    case RunKind::kSettledSloppy:
      run_settled_sloppy(resources);
      break;
  }
  CUDA_CHECK(cudaEventRecord(resources->stopped, resources->stream));
  CUDA_CHECK(cudaEventSynchronize(resources->stopped));
  float milliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(
      &milliseconds, resources->started, resources->stopped));
  return static_cast<double>(milliseconds);
}

std::vector<pw::RealDisk106> download(
    const pdt::Workspace* workspace, cudaStream_t stream) {
  std::vector<pw::RealDisk106> result(pdt::kSourceSampleCount);
  CUDA_CHECK(cudaMemcpyAsync(
      result.data(), pdt::device_samples(workspace),
      result.size() * sizeof(pw::RealDisk106),
      cudaMemcpyDeviceToHost, stream));
  CUDA_CHECK(cudaStreamSynchronize(stream));
  return result;
}

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
template <typename T>
bool vector_bytes_equal(
    const std::vector<T>& left, const std::vector<T>& right) {
  return left.size() == right.size() &&
         (left.empty() ||
          std::memcmp(left.data(), right.data(),
                      left.size() * sizeof(T)) == 0);
}

std::uint64_t disk_byte_mismatch_count(
    const std::vector<pw::RealDisk106>& left,
    const std::vector<pw::RealDisk106>& right,
    std::uint64_t* first_mismatch) {
  if (left.size() != right.size()) {
    throw std::runtime_error("disk arrays have different sizes");
  }
  *first_mismatch = std::numeric_limits<std::uint64_t>::max();
  std::uint64_t result = 0U;
  for (std::size_t index = 0U; index < left.size(); ++index) {
    if (std::memcmp(&left[index], &right[index], sizeof(left[index])) != 0) {
      if (result == 0U) *first_mismatch = index;
      ++result;
    }
  }
  return result;
}
#endif

std::uint32_t download_transform_failure_flags(
    const pdt::Workspace* workspace, cudaStream_t stream) {
  std::uint32_t result = 0U;
  CUDA_CHECK(cudaMemcpyAsync(
      &result, pdt::device_input_failure_flags_qualification(workspace),
      sizeof(result), cudaMemcpyDeviceToHost, stream));
  CUDA_CHECK(cudaStreamSynchronize(stream));
  return result;
}

bool canonical_malformed_disk(const pw::RealDisk106& disk) {
  return std::bit_cast<std::uint64_t>(disk.center.hi) == 0U &&
         std::bit_cast<std::uint64_t>(disk.center.lo) == 0U &&
         std::bit_cast<std::uint64_t>(disk.radius) ==
             0x7ff0000000000000ULL;
}

struct OverflowNegativeControl {
  bool finite_input = false;
  std::uint32_t candidate_transform_failure_flags = 0U;
  std::uint64_t canonical_malformed_output_count = 0U;
  std::uint64_t noncanonical_output_count = 0U;
  std::uint32_t settled_sloppy_transform_failure_flags = 0U;
  std::uint64_t settled_sloppy_canonical_malformed_output_count = 0U;
  std::uint64_t settled_sloppy_noncanonical_output_count = 0U;
  bool candidate_settled_sloppy_output_byte_equal = false;

  bool accepted() const {
    const bool candidate_accepted =
        finite_input &&
           candidate_transform_failure_flags ==
               pdt::kQualificationArithmeticFailure &&
           canonical_malformed_output_count == pdt::kSourceSampleCount &&
           noncanonical_output_count == 0U;
    const bool joint_accepted =
        !kTile9SloppyRootCandidate ||
        (settled_sloppy_transform_failure_flags ==
             candidate_transform_failure_flags &&
         settled_sloppy_canonical_malformed_output_count ==
             pdt::kSourceSampleCount &&
         settled_sloppy_noncanonical_output_count == 0U &&
         candidate_settled_sloppy_output_byte_equal);
    return candidate_accepted && joint_accepted;
  }
};

OverflowNegativeControl qualify_overflow_negative_control(
    Resources* resources) {
  const InputCase input = finite_overflow_control_case();
  const bool finite_input =
      std::all_of(
          input.gamma.begin(), input.gamma.end(), valid_complex_disk) &&
      std::all_of(
          input.skn.begin(), input.skn.end(), valid_complex_disk);
  upload(input, resources);
  run_candidate(resources);
  CUDA_CHECK(cudaStreamSynchronize(resources->stream));
  const std::uint32_t failure_flags =
      download_transform_failure_flags(
          resources->candidate, resources->stream);
  const std::vector<pw::RealDisk106> samples =
      download(resources->candidate, resources->stream);
  OverflowNegativeControl result;
  result.finite_input = finite_input;
  result.candidate_transform_failure_flags = failure_flags;
  for (const pw::RealDisk106& sample : samples) {
    if (canonical_malformed_disk(sample)) {
      ++result.canonical_malformed_output_count;
    } else {
      ++result.noncanonical_output_count;
    }
  }
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  run_settled_sloppy(resources);
  CUDA_CHECK(cudaStreamSynchronize(resources->stream));
  result.settled_sloppy_transform_failure_flags =
      download_transform_failure_flags(
          resources->settled_sloppy, resources->stream);
  const std::vector<pw::RealDisk106> settled_samples =
      download(resources->settled_sloppy, resources->stream);
  for (const pw::RealDisk106& sample : settled_samples) {
    if (canonical_malformed_disk(sample)) {
      ++result.settled_sloppy_canonical_malformed_output_count;
    } else {
      ++result.settled_sloppy_noncanonical_output_count;
    }
  }
  result.candidate_settled_sloppy_output_byte_equal =
      vector_bytes_equal(samples, settled_samples);
#endif
  return result;
}

RootTableQualification qualify_root_table(
    const Resources& resources) {
  const pdt::QualificationRootTableView ordinary_view =
      pdt::device_root_table_qualification(resources.ordinary);
  const pdt::QualificationRootTableView candidate_view =
      pdt::device_root_table_qualification(resources.candidate);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  const pdt::QualificationRootTableView settled_sloppy_view =
      pdt::device_root_table_qualification(resources.settled_sloppy);
#endif
  auto valid_view = [](const pdt::QualificationRootTableView& view) {
    return view.roots != nullptr && view.center_norm_upper != nullptr &&
           view.count == pw::kBucketCount;
  };
  if (!valid_view(ordinary_view) || !valid_view(candidate_view)
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      || !valid_view(settled_sloppy_view)
#endif
  ) {
    throw std::runtime_error(
        "qualification root-table view has wrong geometry");
  }
  std::vector<pw::ComplexDisk106> ordinary_roots(ordinary_view.count);
  std::vector<double> ordinary_norms(ordinary_view.count);
  std::vector<pw::ComplexDisk106> candidate_roots(candidate_view.count);
  std::vector<double> candidate_norms(candidate_view.count);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  std::vector<pw::ComplexDisk106> settled_sloppy_roots(
      settled_sloppy_view.count);
  std::vector<double> settled_sloppy_norms(settled_sloppy_view.count);
#endif
  CUDA_CHECK(cudaMemcpyAsync(
      ordinary_roots.data(), ordinary_view.roots,
      ordinary_roots.size() * sizeof(ordinary_roots.front()),
      cudaMemcpyDeviceToHost, resources.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      ordinary_norms.data(), ordinary_view.center_norm_upper,
      ordinary_norms.size() * sizeof(ordinary_norms.front()),
      cudaMemcpyDeviceToHost, resources.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      candidate_roots.data(), candidate_view.roots,
      candidate_roots.size() * sizeof(candidate_roots.front()),
      cudaMemcpyDeviceToHost, resources.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      candidate_norms.data(), candidate_view.center_norm_upper,
      candidate_norms.size() * sizeof(candidate_norms.front()),
      cudaMemcpyDeviceToHost, resources.stream));
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  CUDA_CHECK(cudaMemcpyAsync(
      settled_sloppy_roots.data(), settled_sloppy_view.roots,
      settled_sloppy_roots.size() * sizeof(settled_sloppy_roots.front()),
      cudaMemcpyDeviceToHost, resources.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      settled_sloppy_norms.data(), settled_sloppy_view.center_norm_upper,
      settled_sloppy_norms.size() * sizeof(settled_sloppy_norms.front()),
      cudaMemcpyDeviceToHost, resources.stream));
#endif
  CUDA_CHECK(cudaStreamSynchronize(resources.stream));

  RootTableQualification result;
  result.ordinary_candidate_table_byte_equal =
      std::memcmp(
          ordinary_roots.data(), candidate_roots.data(),
          ordinary_roots.size() * sizeof(ordinary_roots.front())) == 0 &&
      std::memcmp(
          ordinary_norms.data(), candidate_norms.data(),
          ordinary_norms.size() * sizeof(ordinary_norms.front())) == 0;
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  result.candidate_settled_sloppy_table_byte_equal =
      vector_bytes_equal(candidate_roots, settled_sloppy_roots) &&
      vector_bytes_equal(candidate_norms, settled_sloppy_norms);
#endif
  result.ordinary =
      exact_root_table_audit(ordinary_roots, ordinary_norms);
  for (std::size_t index = 0U; index < ordinary_roots.size(); ++index) {
    const cpp_rational real = decode_dd(ordinary_roots[index].real);
    const cpp_rational imaginary =
        decode_dd(ordinary_roots[index].imaginary);
    if (real * real + imaginary * imaginary > 0) {
      result.mutated_index = index;
      break;
    }
  }
  if (result.mutated_index ==
      std::numeric_limits<std::uint64_t>::max()) {
    throw std::runtime_error("root table has no nonzero center to mutate");
  }
  ordinary_norms[result.mutated_index] = 0.0;
  const RootAudit mutation =
      exact_root_table_audit(ordinary_roots, ordinary_norms);
  result.mutation_failure_count =
      mutation.center_norm_bound_failure_count;
  result.bad_norm_mutation_rejected =
      result.ordinary.accepted() &&
      result.ordinary_candidate_table_byte_equal &&
      (!kTile9SloppyRootCandidate ||
       result.candidate_settled_sloppy_table_byte_equal) &&
      mutation.malformed_root_count == 0U &&
      mutation.malformed_norm_count == 0U &&
      mutation.center_norm_bound_failure_count == 1U &&
      mutation.first_failure == result.mutated_index;
  return result;
}

struct EventResult {
  bool ordinary_accepted = false;
  bool candidate_accepted = false;
  bool settled_sloppy_accepted = false;
  bool ordinary_device_matches_host = false;
  bool candidate_device_matches_host = false;
  bool settled_sloppy_device_matches_host = false;
  bool ordinary_shared_endpoints_agree = false;
  bool candidate_shared_endpoints_agree = false;
  bool settled_sloppy_shared_endpoints_agree = false;
  bool candidate_settled_sloppy_replay_artifact_byte_equal = false;
  std::uint32_t ordinary_failure_flags = 0U;
  std::uint32_t candidate_failure_flags = 0U;
  std::uint32_t settled_sloppy_failure_flags = 0U;
  std::uint64_t ordinary_direct_count = 0U;
  std::uint64_t candidate_direct_count = 0U;
  std::uint64_t settled_sloppy_direct_count = 0U;
  std::uint64_t ordinary_stationary_count = 0U;
  std::uint64_t candidate_stationary_count = 0U;
  std::uint64_t settled_sloppy_stationary_count = 0U;

  bool accepted() const {
    const bool ordinary_candidate_accepted =
        ordinary_accepted && candidate_accepted &&
           ordinary_device_matches_host && candidate_device_matches_host &&
           ordinary_shared_endpoints_agree &&
           candidate_shared_endpoints_agree &&
           ordinary_failure_flags == 0U &&
           candidate_failure_flags == 0U &&
           ordinary_direct_count == kExpectedDirectEvents &&
           candidate_direct_count == ordinary_direct_count &&
           ordinary_stationary_count == kExpectedStationaryEvents &&
           candidate_stationary_count == ordinary_stationary_count;
    const bool joint_accepted =
        !kTile9SloppyRootCandidate ||
        (settled_sloppy_accepted &&
         settled_sloppy_device_matches_host &&
         settled_sloppy_shared_endpoints_agree &&
         candidate_settled_sloppy_replay_artifact_byte_equal &&
         settled_sloppy_failure_flags == candidate_failure_flags &&
         settled_sloppy_direct_count == candidate_direct_count &&
         settled_sloppy_stationary_count == candidate_stationary_count);
    return ordinary_candidate_accepted && joint_accepted;
  }
};

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
bool replay_reports_byte_equal(
    const pes::ReplayReport& left, const pes::ReplayReport& right) {
  if (left.accepted != right.accepted ||
      left.device_matches_host != right.device_matches_host ||
      left.shared_endpoints_agree != right.shared_endpoints_agree ||
      left.error != right.error ||
      !vector_bytes_equal(left.required_samples, right.required_samples) ||
      left.stationary_payload_sha256 !=
          right.stationary_payload_sha256 ||
      std::memcmp(&left.artifact.status, &right.artifact.status,
                  sizeof(left.artifact.status)) != 0 ||
      std::memcmp(left.artifact.summaries.data(),
                  right.artifact.summaries.data(),
                  sizeof(left.artifact.summaries)) != 0) {
    return false;
  }
  for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    if (!vector_bytes_equal(left.artifact.direct[stream],
                            right.artifact.direct[stream]) ||
        !vector_bytes_equal(left.artifact.stationary[stream],
                            right.artifact.stationary[stream])) {
      return false;
    }
  }
  return true;
}
#endif

std::uint64_t direct_count(const pes::ReplayReport& report) {
  std::uint64_t result = 0U;
  for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    result += report.artifact.direct[stream].size();
  }
  return result;
}

std::uint64_t stationary_count(const pes::ReplayReport& report) {
  std::uint64_t result = 0U;
  for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    result += report.artifact.stationary[stream].size();
  }
  return result;
}

EventResult qualify_events(Resources* resources) {
  pes::scan_source_required_samples(
      resources->ordinary_scanner,
      pdt::device_required_samples(resources->ordinary),
      resources->stream);
  const pes::ReplayReport ordinary = pes::replay_and_check(
      resources->ordinary_scanner,
      pdt::device_required_samples(resources->ordinary),
      resources->stream);
  pes::scan_source_required_samples(
      resources->candidate_scanner,
      pdt::device_required_samples(resources->candidate),
      resources->stream);
  const pes::ReplayReport candidate = pes::replay_and_check(
      resources->candidate_scanner,
      pdt::device_required_samples(resources->candidate),
      resources->stream);
  EventResult result{
      .ordinary_accepted = ordinary.accepted,
      .candidate_accepted = candidate.accepted,
      .ordinary_device_matches_host = ordinary.device_matches_host,
      .candidate_device_matches_host = candidate.device_matches_host,
      .ordinary_shared_endpoints_agree =
          ordinary.shared_endpoints_agree,
      .candidate_shared_endpoints_agree =
          candidate.shared_endpoints_agree,
      .ordinary_failure_flags =
          ordinary.artifact.status.failure_flags,
      .candidate_failure_flags =
          candidate.artifact.status.failure_flags,
      .ordinary_direct_count = direct_count(ordinary),
      .candidate_direct_count = direct_count(candidate),
      .ordinary_stationary_count = stationary_count(ordinary),
      .candidate_stationary_count = stationary_count(candidate),
  };
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  pes::scan_source_required_samples(
      resources->settled_sloppy_scanner,
      pdt::device_required_samples(resources->settled_sloppy),
      resources->stream);
  const pes::ReplayReport settled_sloppy = pes::replay_and_check(
      resources->settled_sloppy_scanner,
      pdt::device_required_samples(resources->settled_sloppy),
      resources->stream);
  result.settled_sloppy_accepted = settled_sloppy.accepted;
  result.settled_sloppy_device_matches_host =
      settled_sloppy.device_matches_host;
  result.settled_sloppy_shared_endpoints_agree =
      settled_sloppy.shared_endpoints_agree;
  result.candidate_settled_sloppy_replay_artifact_byte_equal =
      replay_reports_byte_equal(candidate, settled_sloppy);
  result.settled_sloppy_failure_flags =
      settled_sloppy.artifact.status.failure_flags;
  result.settled_sloppy_direct_count = direct_count(settled_sloppy);
  result.settled_sloppy_stationary_count =
      stationary_count(settled_sloppy);
#endif
  return result;
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  return values[values.size() / 2U];
}

struct Timing {
  double ordinary_median_ms = 0.0;
  double ordinary_minimum_ms = 0.0;
  double ordinary_maximum_ms = 0.0;
  double candidate_median_ms = 0.0;
  double candidate_minimum_ms = 0.0;
  double candidate_maximum_ms = 0.0;
  double settled_sloppy_median_ms = 0.0;
  double settled_sloppy_minimum_ms = 0.0;
  double settled_sloppy_maximum_ms = 0.0;
};

Timing benchmark_interleaved(
    Resources* resources, std::uint32_t repetitions) {
  std::vector<double> ordinary;
  std::vector<double> candidate;
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  std::vector<double> settled_sloppy;
#endif
  ordinary.reserve(repetitions);
  candidate.reserve(repetitions);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  settled_sloppy.reserve(repetitions);
#endif
  for (std::uint32_t repetition = 0U; repetition < repetitions;
       ++repetition) {
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
    switch (repetition % 3U) {
      case 0U:
        ordinary.push_back(timed_run(resources, RunKind::kOrdinary));
        settled_sloppy.push_back(
            timed_run(resources, RunKind::kSettledSloppy));
        candidate.push_back(timed_run(resources, RunKind::kCandidate));
        break;
      case 1U:
        settled_sloppy.push_back(
            timed_run(resources, RunKind::kSettledSloppy));
        candidate.push_back(timed_run(resources, RunKind::kCandidate));
        ordinary.push_back(timed_run(resources, RunKind::kOrdinary));
        break;
      default:
        candidate.push_back(timed_run(resources, RunKind::kCandidate));
        ordinary.push_back(timed_run(resources, RunKind::kOrdinary));
        settled_sloppy.push_back(
            timed_run(resources, RunKind::kSettledSloppy));
        break;
    }
#else
    if ((repetition & 1U) == 0U) {
      ordinary.push_back(timed_run(resources, RunKind::kOrdinary));
      candidate.push_back(timed_run(resources, RunKind::kCandidate));
    } else {
      candidate.push_back(timed_run(resources, RunKind::kCandidate));
      ordinary.push_back(timed_run(resources, RunKind::kOrdinary));
    }
#endif
  }
  Timing result{
      .ordinary_median_ms = median(ordinary),
      .ordinary_minimum_ms =
          *std::min_element(ordinary.begin(), ordinary.end()),
      .ordinary_maximum_ms =
          *std::max_element(ordinary.begin(), ordinary.end()),
      .candidate_median_ms = median(candidate),
      .candidate_minimum_ms =
          *std::min_element(candidate.begin(), candidate.end()),
      .candidate_maximum_ms =
          *std::max_element(candidate.begin(), candidate.end()),
  };
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  result.settled_sloppy_median_ms = median(settled_sloppy);
  result.settled_sloppy_minimum_ms =
      *std::min_element(settled_sloppy.begin(), settled_sloppy.end());
  result.settled_sloppy_maximum_ms =
      *std::max_element(settled_sloppy.begin(), settled_sloppy.end());
#endif
  return result;
}

struct CaseResult {
  std::string label;
  bool genuine = false;
  std::uint64_t packet_bytes = 0U;
  std::uint64_t packet_legacy_checksum64 = 0U;
  std::string packet_sha256;
  std::uint64_t ordinary_legacy_checksum64 = 0U;
  std::uint64_t candidate_legacy_checksum64 = 0U;
  std::string ordinary_output_sha256;
  std::string candidate_output_sha256;
  std::string settled_sloppy_output_sha256;
  bool ordinary_legacy_checksum_matches_diagnostic = false;
  bool ordinary_known_answer = false;
  bool settled_sloppy_known_answer = false;
  bool candidate_matches_settled_sloppy_sha_pin = false;
  std::uint32_t ordinary_transform_failure_flags = 0U;
  std::uint32_t candidate_transform_failure_flags = 0U;
  std::uint32_t settled_sloppy_transform_failure_flags = 0U;
  std::uint64_t candidate_settled_sloppy_disk_byte_mismatch_count = 0U;
  std::uint64_t candidate_settled_sloppy_first_disk_byte_mismatch =
      std::numeric_limits<std::uint64_t>::max();
  bool candidate_settled_sloppy_all_sample_bytes_equal = false;
  ContainmentResult containment;
  OverlapResult overlap;
  RadiusDistribution radii;
  SignCounts ordinary_all_signs;
  SignCounts candidate_all_signs;
  SignCounts ordinary_required_signs;
  SignCounts candidate_required_signs;
  std::uint64_t all_sign_mismatch_count = 0U;
  std::uint64_t required_sign_mismatch_count = 0U;
  std::optional<EventResult> events;
  std::optional<Timing> timing;

  bool accepted() const {
    const bool comparison_accepted =
        genuine ? containment.accepted() : overlap.accepted();
    const bool joint_accepted =
        !kTile9SloppyRootCandidate ||
        (settled_sloppy_known_answer &&
         candidate_matches_settled_sloppy_sha_pin &&
         settled_sloppy_transform_failure_flags ==
             candidate_transform_failure_flags &&
         candidate_settled_sloppy_disk_byte_mismatch_count == 0U &&
         candidate_settled_sloppy_all_sample_bytes_equal);
    return ordinary_known_answer && joint_accepted &&
           ordinary_transform_failure_flags == 0U &&
           candidate_transform_failure_flags == 0U &&
           comparison_accepted &&
           candidate_all_signs.malformed == 0U &&
           ordinary_all_signs.malformed == 0U &&
           (genuine
                ? (events.has_value() && events->accepted() &&
                   candidate_required_signs.ambiguous == 0U &&
                   required_sign_mismatch_count == 0U)
                : (all_sign_mismatch_count == 0U &&
                   required_sign_mismatch_count == 0U));
  }
};

CaseResult qualify_case(
    const InputCase& input, Resources* resources,
    std::uint32_t repetitions) {
  upload(input, resources);
  run_ordinary(resources);
  run_candidate(resources);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  run_settled_sloppy(resources);
#endif
  CUDA_CHECK(cudaStreamSynchronize(resources->stream));
  const std::vector<pw::RealDisk106> ordinary =
      download(resources->ordinary, resources->stream);
  const std::vector<pw::RealDisk106> candidate =
      download(resources->candidate, resources->stream);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  const std::vector<pw::RealDisk106> settled_sloppy =
      download(resources->settled_sloppy, resources->stream);
#endif

  CaseResult result;
  result.label = input.label;
  result.genuine = input.genuine;
  result.packet_bytes = input.packet_bytes;
  result.packet_legacy_checksum64 = input.packet_legacy_checksum64;
  result.packet_sha256 = input.packet_sha256;
  result.ordinary_legacy_checksum64 = legacy_pt21_checksum(
      ordinary.data(), ordinary.size() * sizeof(ordinary.front()));
  result.candidate_legacy_checksum64 = legacy_pt21_checksum(
      candidate.data(), candidate.size() * sizeof(candidate.front()));
  result.ordinary_output_sha256 = sparkinterval::lowercase_hex(
      sparkinterval::sha256(
          ordinary.data(),
          ordinary.size() * sizeof(ordinary.front())));
  result.candidate_output_sha256 = sparkinterval::lowercase_hex(
      sparkinterval::sha256(
          candidate.data(),
          candidate.size() * sizeof(candidate.front())));
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  result.settled_sloppy_output_sha256 = sparkinterval::lowercase_hex(
      sparkinterval::sha256(
          settled_sloppy.data(),
          settled_sloppy.size() * sizeof(settled_sloppy.front())));
#endif
  result.ordinary_legacy_checksum_matches_diagnostic =
      result.ordinary_legacy_checksum64 ==
      (input.genuine ? kOrdinaryGenuineLegacyChecksum64
                     : kOrdinaryFiniteEdgeLegacyChecksum64);
  result.ordinary_known_answer =
      result.ordinary_output_sha256 ==
      (input.genuine ? kOrdinaryGenuineOutputSha256
                     : kOrdinaryFiniteEdgeOutputSha256);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  const std::string_view settled_sloppy_expected =
      input.genuine ? kSettledSloppyGenuineOutputSha256
                    : kSettledSloppyFiniteEdgeOutputSha256;
  result.settled_sloppy_known_answer =
      result.settled_sloppy_output_sha256 == settled_sloppy_expected;
  result.candidate_matches_settled_sloppy_sha_pin =
      result.candidate_output_sha256 == settled_sloppy_expected;
#endif
  result.ordinary_transform_failure_flags =
      download_transform_failure_flags(
          resources->ordinary, resources->stream);
  result.candidate_transform_failure_flags =
      download_transform_failure_flags(
          resources->candidate, resources->stream);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  result.settled_sloppy_transform_failure_flags =
      download_transform_failure_flags(
          resources->settled_sloppy, resources->stream);
  result.candidate_settled_sloppy_disk_byte_mismatch_count =
      disk_byte_mismatch_count(
          candidate, settled_sloppy,
          &result.candidate_settled_sloppy_first_disk_byte_mismatch);
  result.candidate_settled_sloppy_all_sample_bytes_equal =
      vector_bytes_equal(candidate, settled_sloppy);
#endif
  result.containment =
      exact_all_sample_containment(ordinary, candidate);
  result.overlap = exact_all_sample_overlap(ordinary, candidate);
  result.radii = radius_distribution(ordinary, candidate);
  result.ordinary_all_signs =
      exact_sign_counts(ordinary, 0U, ordinary.size());
  result.candidate_all_signs =
      exact_sign_counts(candidate, 0U, candidate.size());
  result.ordinary_required_signs = exact_sign_counts(
      ordinary, pdt::kSourceRequiredBegin, pdt::kSourceRequiredCount);
  result.candidate_required_signs = exact_sign_counts(
      candidate, pdt::kSourceRequiredBegin, pdt::kSourceRequiredCount);
  result.all_sign_mismatch_count = exact_sign_mismatch_count(
      ordinary, candidate, 0U, ordinary.size());
  result.required_sign_mismatch_count = exact_sign_mismatch_count(
      ordinary, candidate, pdt::kSourceRequiredBegin,
      pdt::kSourceRequiredCount);
  if (input.genuine) {
    result.events = qualify_events(resources);
    result.timing = benchmark_interleaved(resources, repetitions);
  }
  return result;
}

void print_hex64(std::ostream& output, std::uint64_t value) {
  output << '"' << std::hex << std::setw(16) << std::setfill('0')
         << value << std::dec << std::setfill(' ') << '"';
}

std::string json_escape(std::string_view value) {
  std::string result;
  result.reserve(value.size());
  constexpr char hex[] = "0123456789abcdef";
  for (const unsigned char byte : value) {
    switch (byte) {
      case '"':
        result += "\\\"";
        break;
      case '\\':
        result += "\\\\";
        break;
      case '\n':
        result += "\\n";
        break;
      case '\r':
        result += "\\r";
        break;
      case '\t':
        result += "\\t";
        break;
      default:
        if (byte < 0x20U) {
          result += "\\u00";
          result.push_back(hex[byte >> 4U]);
          result.push_back(hex[byte & 0x0fU]);
        } else {
          result.push_back(static_cast<char>(byte));
        }
    }
  }
  return result;
}

void print_sign_counts(const SignCounts& counts) {
  std::cout << "{\"positive\":" << counts.positive
            << ",\"negative\":" << counts.negative
            << ",\"ambiguous\":" << counts.ambiguous
            << ",\"malformed\":" << counts.malformed << '}';
}

void print_case(const CaseResult& result) {
  std::cout << std::setprecision(17)
            << "{\"label\":\"" << result.label << "\""
            << ",\"genuine_complete_block0\":"
            << (result.genuine ? "true" : "false")
            << ",\"source_packet_bytes\":" << result.packet_bytes
            << ",\"source_packet_sha256\":\""
            << result.packet_sha256 << "\""
            << ",\"source_packet_legacy_checksum64\":";
  print_hex64(std::cout, result.packet_legacy_checksum64);
  std::cout << ",\"ordinary_output_legacy_checksum64\":";
  print_hex64(std::cout, result.ordinary_legacy_checksum64);
  std::cout << ",\"candidate_output_legacy_checksum64\":";
  print_hex64(std::cout, result.candidate_legacy_checksum64);
  std::cout
      << ",\"ordinary_output_sha256\":\""
      << result.ordinary_output_sha256 << "\""
      << ",\"candidate_output_sha256\":\""
      << result.candidate_output_sha256 << "\"";
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  std::cout
      << ",\"settled_sloppy_output_sha256\":\""
      << result.settled_sloppy_output_sha256 << "\""
      << ",\"settled_sloppy_output_known_answer\":"
      << (result.settled_sloppy_known_answer ? "true" : "false")
      << ",\"candidate_matches_settled_sloppy_sha_pin\":"
      << (result.candidate_matches_settled_sloppy_sha_pin
              ? "true"
              : "false");
#endif
  std::cout
      << ",\"ordinary_legacy_checksum_matches_diagnostic\":"
      << (result.ordinary_legacy_checksum_matches_diagnostic
              ? "true"
              : "false")
      << ",\"ordinary_output_known_answer\":"
      << (result.ordinary_known_answer ? "true" : "false")
      << ",\"ordinary_transform_failure_flags\":"
      << result.ordinary_transform_failure_flags
      << ",\"candidate_transform_failure_flags\":"
      << result.candidate_transform_failure_flags
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      << ",\"settled_sloppy_transform_failure_flags\":"
      << result.settled_sloppy_transform_failure_flags
      << ",\"candidate_settled_sloppy_disk_byte_mismatch_count\":"
      << result.candidate_settled_sloppy_disk_byte_mismatch_count
      << ",\"candidate_settled_sloppy_all_sample_bytes_equal\":"
      << (result.candidate_settled_sloppy_all_sample_bytes_equal
              ? "true"
              : "false")
#endif
      << ",\"containment_required_for_acceptance\":"
      << (result.genuine ? "true" : "false")
      << ",\"exact_containment\":{"
      << "\"checker\":\"independent-exact-binary64-dyadic-cpp-rational\""
      << ",\"obligation\":"
      << "\"r_fast>=r_full_and_squared_center_distance_le_squared_radius_difference\""
      << ",\"sample_count\":" << result.containment.checked
      << ",\"malformed_count\":" << result.containment.malformed
      << ",\"radius_order_failure_count\":"
      << result.containment.radius_order_failures
      << ",\"squared_distance_failure_count\":"
      << result.containment.squared_distance_failures
      << ",\"accepted\":"
      << (result.containment.accepted() ? "true" : "false");
  if (!result.containment.accepted()) {
    std::cout << ",\"first_failure\":"
              << result.containment.first_failure;
  }
  std::cout
      << "}"
      << ",\"overlap_required_for_acceptance\":"
      << (!result.genuine ? "true" : "false")
      << ",\"exact_overlap\":{"
      << "\"checker\":\"independent-exact-binary64-dyadic-cpp-rational\""
      << ",\"obligation\":"
      << "\"squared_center_distance_le_squared_radius_sum\""
      << ",\"sample_count\":" << result.overlap.checked
      << ",\"malformed_count\":" << result.overlap.malformed
      << ",\"squared_distance_failure_count\":"
      << result.overlap.squared_distance_failures
      << ",\"accepted\":"
      << (result.overlap.accepted() ? "true" : "false");
  if (!result.overlap.accepted()) {
    std::cout << ",\"first_failure\":"
              << result.overlap.first_failure;
  }
  std::cout
      << "}"
      << ",\"radius_inflation\":{\"finite_ratio_count\":"
      << result.radii.finite_ratio_count
      << ",\"zero_ordinary_radius_count\":"
      << result.radii.zero_ordinary_radius_count
      << ",\"median\":" << result.radii.median
      << ",\"p90\":" << result.radii.p90
      << ",\"p99\":" << result.radii.p99
      << ",\"maximum\":" << result.radii.maximum
      << ",\"ordinary_maximum_radius\":"
      << result.radii.ordinary_maximum_radius
      << ",\"candidate_maximum_radius\":"
      << result.radii.candidate_maximum_radius << "}"
      << ",\"ordinary_all_sample_signs\":";
  print_sign_counts(result.ordinary_all_signs);
  std::cout << ",\"candidate_all_sample_signs\":";
  print_sign_counts(result.candidate_all_signs);
  std::cout << ",\"ordinary_required_sample_signs\":";
  print_sign_counts(result.ordinary_required_signs);
  std::cout << ",\"candidate_required_sample_signs\":";
  print_sign_counts(result.candidate_required_signs);
  std::cout
      << ",\"all_sample_exact_sign_mismatch_count\":"
      << result.all_sign_mismatch_count
      << ",\"required_sample_exact_sign_mismatch_count\":"
      << result.required_sign_mismatch_count;
  if (result.events.has_value()) {
    const EventResult& events = *result.events;
    std::cout
        << ",\"event_scan\":{\"host_replay_integer_bits\":2176"
        << ",\"ordinary_accepted\":"
        << (events.ordinary_accepted ? "true" : "false")
        << ",\"candidate_accepted\":"
        << (events.candidate_accepted ? "true" : "false")
        << ",\"ordinary_device_matches_host\":"
        << (events.ordinary_device_matches_host ? "true" : "false")
        << ",\"candidate_device_matches_host\":"
        << (events.candidate_device_matches_host ? "true" : "false")
        << ",\"ordinary_shared_endpoints_agree\":"
        << (events.ordinary_shared_endpoints_agree ? "true" : "false")
        << ",\"candidate_shared_endpoints_agree\":"
        << (events.candidate_shared_endpoints_agree ? "true" : "false")
        << ",\"ordinary_failure_flags\":"
        << events.ordinary_failure_flags
        << ",\"candidate_failure_flags\":"
        << events.candidate_failure_flags
        << ",\"ordinary_direct_count\":"
        << events.ordinary_direct_count
        << ",\"candidate_direct_count\":"
        << events.candidate_direct_count
        << ",\"ordinary_stationary_count\":"
        << events.ordinary_stationary_count
        << ",\"candidate_stationary_count\":"
        << events.candidate_stationary_count
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
        << ",\"settled_sloppy_accepted\":"
        << (events.settled_sloppy_accepted ? "true" : "false")
        << ",\"settled_sloppy_device_matches_host\":"
        << (events.settled_sloppy_device_matches_host ? "true" : "false")
        << ",\"settled_sloppy_shared_endpoints_agree\":"
        << (events.settled_sloppy_shared_endpoints_agree
                ? "true"
                : "false")
        << ",\"candidate_settled_sloppy_replay_artifact_byte_equal\":"
        << (events.candidate_settled_sloppy_replay_artifact_byte_equal
                ? "true"
                : "false")
        << ",\"settled_sloppy_failure_flags\":"
        << events.settled_sloppy_failure_flags
        << ",\"settled_sloppy_direct_count\":"
        << events.settled_sloppy_direct_count
        << ",\"settled_sloppy_stationary_count\":"
        << events.settled_sloppy_stationary_count
#endif
        << ",\"accepted\":" << (events.accepted() ? "true" : "false")
        << "}";
  }
  if (result.timing.has_value()) {
    const Timing& timing = *result.timing;
    std::cout
        << ",\"interleaved_timing_ms\":{\"ordinary_median\":"
        << timing.ordinary_median_ms
        << ",\"ordinary_minimum\":" << timing.ordinary_minimum_ms
        << ",\"ordinary_maximum\":" << timing.ordinary_maximum_ms
        << ",\"candidate_median\":" << timing.candidate_median_ms
        << ",\"candidate_minimum\":" << timing.candidate_minimum_ms
        << ",\"candidate_maximum\":" << timing.candidate_maximum_ms
        << ",\"median_speedup\":"
        << timing.ordinary_median_ms / timing.candidate_median_ms
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
        << ",\"settled_sloppy_median\":"
        << timing.settled_sloppy_median_ms
        << ",\"settled_sloppy_minimum\":"
        << timing.settled_sloppy_minimum_ms
        << ",\"settled_sloppy_maximum\":"
        << timing.settled_sloppy_maximum_ms
        << ",\"candidate_speedup_over_settled_sloppy\":"
        << timing.settled_sloppy_median_ms /
               timing.candidate_median_ms
#endif
        << "}";
  }
  std::cout << ",\"accepted\":"
            << (result.accepted() ? "true" : "false") << '}';
}

int run(const Options& options) {
  const bool json_escape_control_character_kat =
      json_escape(std::string_view("\x01", 1U)) == "\\u0001";
  const DeviceProfile device_profile =
      require_and_read_device_profile();
  const bool target_h100_measured =
      kStrictH100Target && device_profile.is_h100_sm90;
  const std::array<InputCase, 2> cases{
      finite_edge_case(),
      load_genuine_block0(
          options.source_packet, options.expected_source_packet_sha256)};

  Resources resources;
  initialize(&resources);
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  const pdt::QualificationTile9SloppyRootKernelResources kernel_resources =
      pdt::tile9_sloppy_root_kernel_resources_qualification();
  const bool kernel_resources_accepted =
      kernel_resources.registers_per_thread > 0 &&
      kernel_resources.registers_per_thread <= 255 &&
      kernel_resources.static_shared_bytes ==
          pdt::kQualificationTile9SloppyRootStaticSharedBytes &&
      kernel_resources.local_bytes_per_thread == 0U &&
      kernel_resources.maximum_threads_per_block >=
          pdt::kQualificationTile9SloppyRootThreadsPerBlock &&
      kernel_resources.active_blocks_per_multiprocessor >= 1;
#endif
  const RootTableQualification roots = qualify_root_table(resources);
  const OverflowNegativeControl overflow_negative_control =
      qualify_overflow_negative_control(&resources);
  std::array<CaseResult, 2> results{
      qualify_case(cases[0], &resources, options.repetitions),
      qualify_case(cases[1], &resources, options.repetitions)};

  const bool accepted =
      json_escape_control_character_kat &&
      roots.ordinary.accepted() &&
      roots.ordinary_candidate_table_byte_equal &&
      (!kTile9SloppyRootCandidate ||
       roots.candidate_settled_sloppy_table_byte_equal) &&
      roots.bad_norm_mutation_rejected &&
      overflow_negative_control.accepted() &&
      results[0].accepted() && results[1].accepted()
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      && kernel_resources_accepted
#endif
      ;
  const bool release_build_profile_eligible =
      accepted && kReleasePerformanceBuild;

  std::cout
      << std::setprecision(17)
      << "{\"schema\":"
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      << "\"sparkinterval.tg.platt-dd-tile9-sloppy-root-whole-transform-qualification.v1\""
#else
      << "\"sparkinterval.tg.platt-dd-sloppy-root-whole-transform-qualification.v1\""
#endif
      << ",\"accepted\":" << (accepted ? "true" : "false")
      << ",\"qualification_only\":true"
      << ",\"json_escape_control_character_kat\":"
      << (json_escape_control_character_kat ? "true" : "false")
      << ",\"authenticated_fixture_required\":true"
      << ",\"fixture_is_production_source_claim\":false"
      << ",\"build_profile\":{\"cmake_build_config\":\""
      << kBuildProfile << "\""
      << ",\"ndebug_defined\":"
      << (kNdebugDefined ? "true" : "false")
      << ",\"release_performance_build\":"
      << (kReleasePerformanceBuild ? "true" : "false") << "}"
      << ",\"device_profile\":{\"name\":\""
      << json_escape(device_profile.name) << "\""
      << ",\"major\":" << device_profile.major
      << ",\"minor\":" << device_profile.minor << "}"
      << ",\"strict_h100_target\":"
      << (kStrictH100Target ? "true" : "false")
      << ",\"target_h100_measured\":"
      << (target_h100_measured ? "true" : "false")
      << ",\"h100_runtime_claimed\":"
      << (target_h100_measured ? "true" : "false")
      << ",\"repetitions\":" << options.repetitions
      << ",\"sample_disk_count\":" << pdt::kSourceSampleCount
      << ",\"required_sample_count\":" << pdt::kSourceRequiredCount
      << ",\"legacy_checksum_algorithm\":"
      << "\"historical-pt21-fnv1a64-label-nonstandard-offset\""
      << ",\"ordinary_expected_output_legacy_checksum64\":";
  print_hex64(std::cout, kOrdinaryGenuineLegacyChecksum64);
  std::cout
      << ",\"ordinary_expected_genuine_output_sha256\":\""
      << kOrdinaryGenuineOutputSha256 << "\""
      << ",\"ordinary_expected_finite_edge_output_sha256\":\""
      << kOrdinaryFiniteEdgeOutputSha256 << "\"";
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
  std::cout
      << ",\"settled_sloppy_expected_genuine_output_sha256\":\""
      << kSettledSloppyGenuineOutputSha256 << "\""
      << ",\"settled_sloppy_expected_finite_edge_output_sha256\":\""
      << kSettledSloppyFiniteEdgeOutputSha256 << "\""
      << ",\"joint_kernel_resources\":{\"registers_per_thread\":"
      << kernel_resources.registers_per_thread
      << ",\"static_shared_bytes\":"
      << kernel_resources.static_shared_bytes
      << ",\"expected_static_shared_bytes\":"
      << pdt::kQualificationTile9SloppyRootStaticSharedBytes
      << ",\"local_bytes_per_thread\":"
      << kernel_resources.local_bytes_per_thread
      << ",\"maximum_threads_per_block\":"
      << kernel_resources.maximum_threads_per_block
      << ",\"required_threads_per_block\":"
      << pdt::kQualificationTile9SloppyRootThreadsPerBlock
      << ",\"active_blocks_per_multiprocessor\":"
      << kernel_resources.active_blocks_per_multiprocessor
      << ",\"accepted\":"
      << (kernel_resources_accepted ? "true" : "false") << "}";
#endif
  std::cout
      << ",\"root_table_audit\":{\"count\":"
      << roots.ordinary.count
      << ",\"checker\":\"independent-exact-binary64-dyadic-cpp-rational\""
      << ",\"malformed_root_count\":"
      << roots.ordinary.malformed_root_count
      << ",\"malformed_norm_count\":"
      << roots.ordinary.malformed_norm_count
      << ",\"center_norm_bound_failure_count\":"
      << roots.ordinary.center_norm_bound_failure_count
      << ",\"ordinary_candidate_table_byte_equal\":"
      << (roots.ordinary_candidate_table_byte_equal ? "true" : "false")
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      << ",\"candidate_settled_sloppy_table_byte_equal\":"
      << (roots.candidate_settled_sloppy_table_byte_equal
              ? "true"
              : "false")
#endif
      << ",\"bad_norm_mutation_index\":"
      << roots.mutated_index
      << ",\"bad_norm_mutation_failure_count\":"
      << roots.mutation_failure_count
      << ",\"bad_norm_mutation_rejected\":"
      << (roots.bad_norm_mutation_rejected ? "true" : "false")
      << ",\"accepted\":"
      << (roots.ordinary.accepted() &&
                  roots.ordinary_candidate_table_byte_equal &&
                  (!kTile9SloppyRootCandidate ||
                   roots.candidate_settled_sloppy_table_byte_equal)
              ? "true"
              : "false")
      << "}"
      << ",\"candidate_overflow_negative_control\":{"
      << "\"finite_input\":"
      << (overflow_negative_control.finite_input ? "true" : "false")
      << ",\"expected_failure_flag\":"
      << pdt::kQualificationArithmeticFailure
      << ",\"candidate_transform_failure_flags\":"
      << overflow_negative_control.candidate_transform_failure_flags
      << ",\"canonical_malformed_output_count\":"
      << overflow_negative_control.canonical_malformed_output_count
      << ",\"noncanonical_output_count\":"
      << overflow_negative_control.noncanonical_output_count
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      << ",\"settled_sloppy_transform_failure_flags\":"
      << overflow_negative_control.settled_sloppy_transform_failure_flags
      << ",\"settled_sloppy_canonical_malformed_output_count\":"
      << overflow_negative_control
             .settled_sloppy_canonical_malformed_output_count
      << ",\"settled_sloppy_noncanonical_output_count\":"
      << overflow_negative_control
             .settled_sloppy_noncanonical_output_count
      << ",\"candidate_settled_sloppy_output_byte_equal\":"
      << (overflow_negative_control
                  .candidate_settled_sloppy_output_byte_equal
              ? "true"
              : "false")
#endif
      << ",\"accepted\":"
      << (overflow_negative_control.accepted() ? "true" : "false")
      << "}"
      << ",\"cases\":[";
  print_case(results[0]);
  std::cout << ',';
  print_case(results[1]);
  std::cout
      << "]"
      << ",\"release_build_profile_eligible\":"
      << (release_build_profile_eligible ? "true" : "false")
      << ",\"runtime_instrumentation_status\":\"not-inspected-by-runner\""
      << ",\"performance_evidence_eligible\":false"
      << ",\"ordinary_run_source_window_api_unchanged\":true"
      << ",\"candidate_selected_by_compile_time_guard\":true"
#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
      << ",\"settled_sloppy_entry_replayed_in_this_run\":true"
      << ",\"joint_schedule_only\":true"
      << ",\"optimization_selected_for_production\":false"
      << ",\"selection_status\":"
      << "\"qualification-only-local-gain-too-small-no-h100-measurement\""
#endif
      << ",\"arithmetic_corpus_sha256_reference\":"
      << "\"50738ee7a4b57069c074b8cbdc373ed6"
      << "feb0e90991f8ec364b68b8cef725f6c7\""
      << ",\"arithmetic_corpus_replayed_in_this_run\":false"
      << ",\"cuda_to_lean_refinement_proved\":false"
      << ",\"source_claim_ready\":false"
      << ",\"production_ready\":false"
      << ",\"pt21_atom_discharged\":false}\n";
  return accepted ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << (kTile9SloppyRootCandidate
                      ? "sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-"
                        "transform-qualification: "
                      : "sparkinterval-tg-platt-dd-sloppy-root-whole-"
                        "transform-qualification: ")
              << error.what() << '\n';
    return 2;
  }
}

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only byte-identity and performance experiment for the PT21
// shared-memory stages-1..9 DD FFT tile.  This executable emits no source or
// production certificate.

#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"
#include "sparkinterval/sha256.hpp"

#include <cuda_runtime.h>

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

namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

constexpr std::string_view kBuildProfile =
    SPARKINTERVAL_CMAKE_BUILD_CONFIG;
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

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                  \
    }                                                                        \
  } while (0)

struct Options {
  std::optional<std::string> source_packet;
  std::optional<sparkinterval::Sha256Digest> expected_source_packet_sha256;
  std::uint32_t repetitions = 9U;
  bool skip_event_artifact = false;
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
        "strict tile9 qualification target requires NVIDIA H100 sm_90");
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
  Options result;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    constexpr std::string_view packet_prefix = "--source-packet=";
    constexpr std::string_view packet_sha_prefix =
        "--expected-source-packet-sha256=";
    constexpr std::string_view repetitions_prefix = "--repetitions=";
    if (argument.starts_with(packet_prefix)) {
      if (result.source_packet.has_value()) {
        throw std::runtime_error("source packet is duplicated");
      }
      const std::string path(argument.substr(packet_prefix.size()));
      if (path.empty()) throw std::runtime_error("source packet path is empty");
      result.source_packet = path;
    } else if (argument.starts_with(packet_sha_prefix)) {
      if (result.expected_source_packet_sha256.has_value()) {
        throw std::runtime_error("expected source packet SHA-256 is duplicated");
      }
      result.expected_source_packet_sha256 =
          parse_sha256(argument.substr(packet_sha_prefix.size()));
    } else if (argument.starts_with(repetitions_prefix)) {
      result.repetitions =
          parse_repetitions(argument.substr(repetitions_prefix.size()));
    } else if (argument == "--skip-event-artifact") {
      result.skip_event_artifact = true;
    } else {
      throw std::runtime_error(
          "usage: tg-platt-dd-tile9-qualification "
          "[--source-packet=PT21SRC2 "
          "--expected-source-packet-sha256=HEX] [--repetitions=N] "
          "[--skip-event-artifact]");
    }
  }
  if (result.source_packet.has_value() !=
      result.expected_source_packet_sha256.has_value()) {
    throw std::runtime_error(
        "source packet and expected source packet SHA-256 must be supplied "
        "together");
  }
  return result;
}

std::uint64_t fnv1a(const void* raw, std::size_t size) {
  const auto* bytes = static_cast<const unsigned char*>(raw);
  std::uint64_t value = 1'469'598'103'934'665'603ULL;
  for (std::size_t index = 0U; index < size; ++index) {
    value ^= bytes[index];
    value *= 1'099'511'628'211ULL;
  }
  return value;
}

template <typename T>
bool vector_bytes_equal(const std::vector<T>& left,
                        const std::vector<T>& right) {
  return left.size() == right.size() &&
         (left.empty() ||
          std::memcmp(left.data(), right.data(),
                      left.size() * sizeof(T)) == 0);
}

struct InputCase {
  std::string label;
  std::vector<pw::ComplexDisk106> gamma;
  std::vector<pw::ComplexDisk106> skn;
  bool genuine_block0 = false;
  bool complete_source_terms = false;
  bool packet_sha256_pinned = false;
  std::uint64_t packet_bytes = 0U;
  std::uint64_t packet_fnv1a64 = 0U;
  std::string packet_sha256;
};

InputCase zero_case() {
  InputCase result;
  result.label = "synthetic-zero";
  result.gamma.resize(pw::kBucketCount);
  result.skn.resize(
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount);
  return result;
}

InputCase finite_edge_case() {
  InputCase result;
  result.label = "synthetic-finite-edge";
  result.gamma.resize(pw::kBucketCount);
  result.skn.resize(
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount);
  const double least_subnormal =
      std::numeric_limits<double>::denorm_min();
  auto initialize = [least_subnormal](
                        std::vector<pw::ComplexDisk106>* values,
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

InputCase load_genuine_block0(
    const std::string& path,
    const sparkinterval::Sha256Digest& expected_sha256) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "PT21 tile9 packet qualification requires little endian");
  }
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open source packet");
  const std::streampos end = input.tellg();
  if (end < 0 ||
      static_cast<std::uint64_t>(end) >
          std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("source packet size is invalid");
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
  if (actual_sha256 != expected_sha256) {
    throw std::runtime_error(
        "source packet SHA-256 differs from the caller pin");
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
  result.genuine_block0 = true;
  result.complete_source_terms = true;
  result.packet_sha256_pinned = true;
  result.packet_bytes = bytes.size();
  result.packet_fnv1a64 = fnv1a(bytes.data(), bytes.size());
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
  if (fnv1a(result.gamma.data(), gamma_bytes) != header.gamma_fnv1a64 ||
      fnv1a(result.skn.data(), skn_bytes) != header.skn_fnv1a64) {
    throw std::runtime_error("source packet payload FNV commitment differs");
  }
  auto valid = [](const pw::ComplexDisk106& value) {
    return std::isfinite(value.real.hi) &&
           std::isfinite(value.real.lo) &&
           std::isfinite(value.imaginary.hi) &&
           std::isfinite(value.imaginary.lo) &&
           std::isfinite(value.radius) && value.radius >= 0.0;
  };
  if (!std::all_of(result.gamma.begin(), result.gamma.end(), valid) ||
      !std::all_of(result.skn.begin(), result.skn.end(), valid)) {
    throw std::runtime_error("source packet contains a malformed DD disk");
  }
  return result;
}

struct Resources {
  pw::ComplexDisk106* device_gamma = nullptr;
  pw::ComplexDisk106* device_skn = nullptr;
  pdt::Workspace* ordinary = nullptr;
  pdt::Workspace* tile9 = nullptr;
  pes::Workspace* ordinary_scanner = nullptr;
  pes::Workspace* tile9_scanner = nullptr;
  cudaStream_t stream = nullptr;
  cudaEvent_t started = nullptr;
  cudaEvent_t stopped = nullptr;

  ~Resources() {
    if (started != nullptr) cudaEventDestroy(started);
    if (stopped != nullptr) cudaEventDestroy(stopped);
    if (ordinary_scanner != nullptr) {
      pes::destroy_workspace(ordinary_scanner);
    }
    if (tile9_scanner != nullptr) pes::destroy_workspace(tile9_scanner);
    if (ordinary != nullptr) pdt::destroy_workspace(ordinary);
    if (tile9 != nullptr) pdt::destroy_workspace(tile9);
    if (device_gamma != nullptr) cudaFree(device_gamma);
    if (device_skn != nullptr) cudaFree(device_skn);
    if (stream != nullptr) cudaStreamDestroy(stream);
  }
};

void initialize(Resources* resources, bool event_artifact) {
  const std::uint64_t skn_count =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  CUDA_CHECK(cudaMalloc(
      &resources->device_gamma,
      pw::kBucketCount * sizeof(*resources->device_gamma)));
  CUDA_CHECK(cudaMalloc(
      &resources->device_skn,
      skn_count * sizeof(*resources->device_skn)));
  resources->ordinary = pdt::create_source_workspace();
  resources->tile9 = pdt::create_source_workspace();
  if (event_artifact) {
    resources->ordinary_scanner = pes::create_workspace();
    resources->tile9_scanner = pes::create_workspace();
  }
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

void run_tile9(Resources* resources) {
  pdt::run_source_window_tile9_qualification(
      resources->tile9, resources->device_gamma,
      resources->device_skn, resources->stream);
}

double timed_run(Resources* resources, bool tile9) {
  CUDA_CHECK(cudaEventRecord(resources->started, resources->stream));
  if (tile9) {
    run_tile9(resources);
  } else {
    run_ordinary(resources);
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

std::uint64_t disk_mismatch_count(
    const std::vector<pw::RealDisk106>& left,
    const std::vector<pw::RealDisk106>& right,
    std::uint64_t* first_mismatch) {
  std::uint64_t count = 0U;
  *first_mismatch = std::numeric_limits<std::uint64_t>::max();
  for (std::size_t index = 0U; index < left.size(); ++index) {
    if (std::memcmp(&left[index], &right[index], sizeof(left[index])) != 0) {
      if (count == 0U) *first_mismatch = index;
      ++count;
    }
  }
  return count;
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  return values[values.size() / 2U];
}

struct CaseResult {
  std::string label;
  bool genuine_block0 = false;
  bool complete_source_terms = false;
  bool packet_sha256_pinned = false;
  std::uint64_t packet_bytes = 0U;
  std::uint64_t packet_fnv1a64 = 0U;
  std::string packet_sha256;
  std::uint64_t ordinary_fnv1a64 = 0U;
  std::uint64_t tile9_fnv1a64 = 0U;
  std::uint64_t disk_mismatches = 0U;
  std::uint64_t first_disk_mismatch =
      std::numeric_limits<std::uint64_t>::max();
  bool all_sample_bytes_equal = false;
  bool event_artifact_compared = false;
  bool event_artifact_byte_equal = false;
  bool ordinary_host_replay_matches = false;
  bool tile9_host_replay_matches = false;
  bool ordinary_event_scan_accepted = false;
  bool tile9_event_scan_accepted = false;
  std::uint32_t event_failure_flags = 0U;
  std::uint64_t event_direct_count = 0U;
  std::uint64_t event_stationary_count = 0U;
  double ordinary_median_ms = 0.0;
  double ordinary_minimum_ms = 0.0;
  double ordinary_maximum_ms = 0.0;
  double tile9_median_ms = 0.0;
  double tile9_minimum_ms = 0.0;
  double tile9_maximum_ms = 0.0;
  bool performance_evidence_eligible = false;
};

CaseResult qualify_case(
    const InputCase& input, Resources* resources,
    std::uint32_t repetitions, bool event_artifact) {
  upload(input, resources);
  run_ordinary(resources);
  run_tile9(resources);
  CUDA_CHECK(cudaStreamSynchronize(resources->stream));
  const std::vector<pw::RealDisk106> ordinary =
      download(resources->ordinary, resources->stream);
  const std::vector<pw::RealDisk106> tile9 =
      download(resources->tile9, resources->stream);

  CaseResult result;
  result.label = input.label;
  result.genuine_block0 = input.genuine_block0;
  result.complete_source_terms = input.complete_source_terms;
  result.packet_sha256_pinned = input.packet_sha256_pinned;
  result.packet_bytes = input.packet_bytes;
  result.packet_fnv1a64 = input.packet_fnv1a64;
  result.packet_sha256 = input.packet_sha256;
  result.ordinary_fnv1a64 =
      fnv1a(ordinary.data(), ordinary.size() * sizeof(ordinary.front()));
  result.tile9_fnv1a64 =
      fnv1a(tile9.data(), tile9.size() * sizeof(tile9.front()));
  result.disk_mismatches =
      disk_mismatch_count(
          ordinary, tile9, &result.first_disk_mismatch);
  result.all_sample_bytes_equal =
      vector_bytes_equal(ordinary, tile9);

  if (event_artifact) {
    pes::scan_source_required_samples(
        resources->ordinary_scanner,
        pdt::device_required_samples(resources->ordinary),
        resources->stream);
    const pes::ReplayReport ordinary_replay = pes::replay_and_check(
        resources->ordinary_scanner,
        pdt::device_required_samples(resources->ordinary),
        resources->stream);
    pes::scan_source_required_samples(
        resources->tile9_scanner,
        pdt::device_required_samples(resources->tile9),
        resources->stream);
    const pes::ReplayReport tile9_replay = pes::replay_and_check(
        resources->tile9_scanner,
        pdt::device_required_samples(resources->tile9),
        resources->stream);
    result.event_artifact_compared = true;
    result.event_artifact_byte_equal =
        replay_reports_byte_equal(ordinary_replay, tile9_replay);
    result.ordinary_host_replay_matches =
        ordinary_replay.device_matches_host;
    result.tile9_host_replay_matches =
        tile9_replay.device_matches_host;
    result.ordinary_event_scan_accepted = ordinary_replay.accepted;
    result.tile9_event_scan_accepted = tile9_replay.accepted;
    result.event_failure_flags =
        ordinary_replay.artifact.status.failure_flags;
    for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
      result.event_direct_count +=
          ordinary_replay.artifact.direct[stream].size();
      result.event_stationary_count +=
          ordinary_replay.artifact.stationary[stream].size();
    }
  }

  // Interleave both orders so clock/thermal drift is not assigned to one
  // implementation.  The initial identity runs above serve as warmup.
  std::vector<double> ordinary_times;
  std::vector<double> tile9_times;
  ordinary_times.reserve(repetitions);
  tile9_times.reserve(repetitions);
  for (std::uint32_t repetition = 0U; repetition < repetitions;
       ++repetition) {
    if ((repetition & 1U) == 0U) {
      ordinary_times.push_back(timed_run(resources, false));
      tile9_times.push_back(timed_run(resources, true));
    } else {
      tile9_times.push_back(timed_run(resources, true));
      ordinary_times.push_back(timed_run(resources, false));
    }
  }
  result.ordinary_median_ms = median(ordinary_times);
  result.ordinary_minimum_ms =
      *std::min_element(ordinary_times.begin(), ordinary_times.end());
  result.ordinary_maximum_ms =
      *std::max_element(ordinary_times.begin(), ordinary_times.end());
  result.tile9_median_ms = median(tile9_times);
  result.tile9_minimum_ms =
      *std::min_element(tile9_times.begin(), tile9_times.end());
  result.tile9_maximum_ms =
      *std::max_element(tile9_times.begin(), tile9_times.end());
  result.performance_evidence_eligible =
      result.genuine_block0 && result.complete_source_terms &&
      result.packet_sha256_pinned && result.all_sample_bytes_equal &&
      result.event_artifact_compared &&
      result.event_artifact_byte_equal &&
      result.ordinary_host_replay_matches &&
      result.tile9_host_replay_matches &&
      result.ordinary_event_scan_accepted &&
      result.tile9_event_scan_accepted &&
      kReleasePerformanceBuild;
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
      case '\b':
        result += "\\b";
        break;
      case '\f':
        result += "\\f";
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

int run(const Options& options) {
  const DeviceProfile device_profile =
      require_and_read_device_profile();
  const bool target_h100_measured =
      kStrictH100Target && device_profile.is_h100_sm90;
  std::vector<InputCase> inputs;
  inputs.push_back(zero_case());
  inputs.push_back(finite_edge_case());
  if (options.source_packet.has_value()) {
    inputs.push_back(load_genuine_block0(
        *options.source_packet,
        *options.expected_source_packet_sha256));
  }

  Resources resources;
  initialize(&resources, !options.skip_event_artifact);
  std::vector<CaseResult> results;
  results.reserve(inputs.size());
  bool accepted = true;
  std::uint32_t genuine_source_case_count = 0U;
  std::uint32_t accepted_genuine_source_case_count = 0U;
  std::uint32_t performance_evidence_eligible_case_count = 0U;
  for (const InputCase& input : inputs) {
    CaseResult result = qualify_case(
        input, &resources, options.repetitions,
        !options.skip_event_artifact);
    accepted =
        accepted && result.all_sample_bytes_equal &&
        (!result.event_artifact_compared ||
         (result.event_artifact_byte_equal &&
          result.ordinary_host_replay_matches &&
          result.tile9_host_replay_matches));
    if (result.genuine_block0) {
      ++genuine_source_case_count;
      if (result.ordinary_event_scan_accepted &&
          result.tile9_event_scan_accepted) {
        ++accepted_genuine_source_case_count;
      }
    }
    if (result.performance_evidence_eligible) {
      ++performance_evidence_eligible_case_count;
    }
    results.push_back(std::move(result));
  }

  std::cout << std::setprecision(17)
            << "{\"schema\":"
            << "\"sparkinterval.tg.platt-dd-tile9-qualification.v1\""
            << ",\"accepted\":" << (accepted ? "true" : "false")
            << ",\"accepted_semantics\":"
            << "\"byte_identity_qualification\""
            << ",\"genuine_source_case_count\":"
            << genuine_source_case_count
            << ",\"accepted_genuine_source_case_count\":"
            << accepted_genuine_source_case_count
            << ",\"useful_source_acceptance_observed\":"
            << (accepted_genuine_source_case_count != 0U
                    ? "true" : "false")
            << ",\"performance_evidence_eligible_case_count\":"
            << performance_evidence_eligible_case_count
            << ",\"qualification_only\":true"
            << ",\"build_profile\":{\"cmake_build_config\":\""
            << kBuildProfile << "\""
            << ",\"ndebug_defined\":"
            << (kNdebugDefined ? "true" : "false")
            << ",\"release_performance_build\":"
            << (kReleasePerformanceBuild ? "true" : "false")
            << "}"
            << ",\"device_profile\":{\"name\":\""
            << json_escape(device_profile.name) << "\""
            << ",\"major\":" << device_profile.major
            << ",\"minor\":" << device_profile.minor
            << "}"
            << ",\"strict_h100_target\":"
            << (kStrictH100Target ? "true" : "false")
            << ",\"target_h100_measured\":"
            << (target_h100_measured ? "true" : "false")
            << ",\"repetitions\":" << options.repetitions
            << ",\"early_stages_fused\":9"
            << ",\"shared_tile_values\":512"
            << ",\"shared_tile_bytes\":20480"
            << ",\"shared_root_cache_bytes\":12288"
            << ",\"declared_shared_bytes_per_block\":32768"
            << ",\"ordinary_stages_begin\":10"
            << ",\"sample_disk_count\":" << pdt::kSourceSampleCount
            << ",\"event_artifact_requested\":"
            << (!options.skip_event_artifact ? "true" : "false")
            << ",\"genuine_block0_requested\":"
            << (options.source_packet.has_value() ? "true" : "false")
            << ",\"cases\":[";
  for (std::size_t index = 0U; index < results.size(); ++index) {
    if (index != 0U) std::cout << ',';
    const CaseResult& result = results[index];
    std::cout
        << "{\"label\":\"" << result.label << "\""
        << ",\"genuine_block0\":"
        << (result.genuine_block0 ? "true" : "false")
        << ",\"complete_source_terms\":"
        << (result.complete_source_terms ? "true" : "false")
        << ",\"source_packet_sha256_pinned\":"
        << (result.packet_sha256_pinned ? "true" : "false")
        << ",\"source_packet_bytes\":" << result.packet_bytes
        << ",\"source_packet_sha256\":\""
        << result.packet_sha256 << "\""
        << ",\"source_packet_fnv1a64\":";
    print_hex64(std::cout, result.packet_fnv1a64);
    std::cout << ",\"ordinary_output_fnv1a64\":";
    print_hex64(std::cout, result.ordinary_fnv1a64);
    std::cout << ",\"tile9_output_fnv1a64\":";
    print_hex64(std::cout, result.tile9_fnv1a64);
    std::cout
        << ",\"all_131072_sample_disks_byte_equal\":"
        << (result.all_sample_bytes_equal ? "true" : "false")
        << ",\"disk_byte_mismatch_count\":"
        << result.disk_mismatches;
    if (result.disk_mismatches != 0U) {
      std::cout << ",\"first_disk_byte_mismatch\":"
                << result.first_disk_mismatch;
    }
    std::cout
        << ",\"event_artifact_compared\":"
        << (result.event_artifact_compared ? "true" : "false")
        << ",\"event_artifact_byte_equal\":"
        << (result.event_artifact_byte_equal ? "true" : "false")
        << ",\"ordinary_device_matches_host_replay\":"
        << (result.ordinary_host_replay_matches ? "true" : "false")
        << ",\"tile9_device_matches_host_replay\":"
        << (result.tile9_host_replay_matches ? "true" : "false")
        << ",\"ordinary_event_scan_accepted\":"
        << (result.ordinary_event_scan_accepted ? "true" : "false")
        << ",\"tile9_event_scan_accepted\":"
        << (result.tile9_event_scan_accepted ? "true" : "false")
        << ",\"event_failure_flags\":"
        << result.event_failure_flags
        << ",\"event_direct_count\":"
        << result.event_direct_count
        << ",\"event_stationary_count\":"
        << result.event_stationary_count
        << ",\"ordinary_transform_median_ms\":"
        << result.ordinary_median_ms
        << ",\"ordinary_transform_minimum_ms\":"
        << result.ordinary_minimum_ms
        << ",\"ordinary_transform_maximum_ms\":"
        << result.ordinary_maximum_ms
        << ",\"tile9_transform_median_ms\":"
        << result.tile9_median_ms
        << ",\"tile9_transform_minimum_ms\":"
        << result.tile9_minimum_ms
        << ",\"tile9_transform_maximum_ms\":"
        << result.tile9_maximum_ms
        << ",\"transform_speedup\":"
        << result.ordinary_median_ms / result.tile9_median_ms
        << ",\"performance_evidence_eligible\":"
        << (result.performance_evidence_eligible ? "true" : "false")
        << '}';
  }
  std::cout
      << "]"
      << ",\"default_run_source_window_modified\":false"
      << ",\"hardy_z_realization_proved\":false"
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
    std::cerr << "sparkinterval-tg-platt-dd-tile9-qualification: "
              << error.what() << '\n';
    return 2;
  }
}

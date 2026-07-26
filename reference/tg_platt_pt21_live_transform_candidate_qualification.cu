// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only live PT21 block-0 comparison:
//
// authenticated V2 Gamma record -> resident Gamma synthesis ->
// exact 768000-term/23-stage accumulator -> ordinary, settled sloppy-root,
// and tile9+sloppy-root transforms -> exact host containment and scanner
// replay.
//
// This executable deliberately reuses one accumulator, one transform
// workspace, and one event scanner.  It emits no production/source
// certificate and does not discharge PT21.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_dd_accumulator.hpp"
#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"
#include "sparkinterval/tg_platt_gamma_dd_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"

#include <cuda_runtime.h>

#include <boost/multiprecision/cpp_int.hpp>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#if !defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) || \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION != 1
#error "live transform candidate runner requires the sloppy-root guard"
#endif

#if !defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) || \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION != 1
#error "live transform candidate runner requires the tile9 sloppy-root guard"
#endif

#if !defined(SPARKINTERVAL_CUDA_FTZ_DISABLED) || \
    SPARKINTERVAL_CUDA_FTZ_DISABLED != 1
#error "live transform candidate qualification requires --ftz=false"
#endif

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pgd = sparkinterval::tg::platt_gamma_dd_gpu;
namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;
namespace pw = sparkinterval::tg::platt_windowed;

using boost::multiprecision::cpp_int;
using boost::multiprecision::cpp_rational;

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

constexpr std::string_view kExpectedLogicalStreamSha256 =
    "d484eb1f0d382ffcf3683e18cd0c9570"
    "c5a215efaa595cb9bb677e3c2ebfbdbc";
constexpr std::string_view kExpectedFileSha256 =
    "b1269afd7d15842fb15a86301627280ac"
    "ddd190de9a7e2d961510a555f14f391";
constexpr std::size_t kExpectedFileBytes =
    sizeof(pg2::Header) + sizeof(pg2::ChunkHeader) +
    sizeof(pg2::Record) + sizeof(pg2::Footer);
constexpr std::uint64_t kExpectedGammaDigest =
    0x1f06f98539bba568ULL;
constexpr std::uint64_t kExpectedGammaMaximumRadiusBits =
    0x3ae12980bb87079aULL;
constexpr std::uint64_t kExpectedRequiredDigest =
    0x55c2a006ce805986ULL;
constexpr std::uint64_t kExpectedRequiredMaximumRadiusBits =
    0x3d59e1dd5c163e26ULL;
constexpr std::string_view kExpectedOrdinaryArtifactSha256 =
    "583a257079353e8efb334f1be2d7c415"
    "14a8f9759898f1dc1b2220fbda2dae60";
constexpr std::string_view kExpectedOrdinaryAllSampleSha256 =
    "f11156870b9681147f3b48d70bd9bdc3"
    "613f015fa9a8783230fc731f49564224";
constexpr std::string_view kExpectedOrdinaryRequiredSampleSha256 =
    "3a12d63c8545aaf98ce6585994412a7e"
    "96c817a4b3d93e40da671c58883a97e4";
constexpr std::uint64_t kExpectedCandidateRequiredDigest =
    0x094f3182295e6c3fULL;
constexpr std::uint64_t kExpectedCandidateRequiredMaximumRadiusBits =
    0x3d59e1dd5cf62222ULL;
constexpr std::string_view kExpectedCandidateAllSampleSha256 =
    "06e55d44a684548c93f4ac48996fdca0"
    "6bca00e1ab4ba493d02f84d03bc16c19";
constexpr std::string_view kExpectedCandidateRequiredSampleSha256 =
    "46ceeae8f719f85bf747a9b660f26c42"
    "6016859293e22bb0e653041365f60c57";
constexpr std::string_view kExpectedCandidateArtifactSha256 =
    "65292e38a013baa83abc61bd5cdcd8c2"
    "e014032d9bceabe08d6fd5578d06ef89";
constexpr std::string_view kExpectedContainmentFrameArtifactSha256 =
    "a4379093cd52ab0b90ed73cf60f61700"
    "3490eefd2a1379115d9a3b1bdf5125d7";
constexpr std::string_view kExpectedAccumulatorGeometrySha256 =
    "67dc2eda921762f6ad1eaf046188b9500"
    "b1b19c87b46e60facf30cfb3bf28ad4";
constexpr std::string_view kExpectedRootTableSha256 =
    "0b4e51572104edf59d096d680ca010a5"
    "15157208c6cdba14be867d9c22d52040";
constexpr std::array<std::uint32_t, pes::kStreamCount>
    kExpectedDirectCount = {71U, 3'397U, 71U};
constexpr std::array<std::uint32_t, pes::kStreamCount>
    kExpectedStationaryCount = {0U, 1U, 0U};
constexpr std::array<std::int64_t, pes::kStreamCount>
    kExpectedNleft = {-18'200, -41'749'543, -18'240};
constexpr std::array<std::int64_t, pes::kStreamCount>
    kExpectedNright = {18'081, 41'731'732, 18'041};
constexpr std::uint64_t kExpectedAccumulatorBytes = 570'977'292ULL;
constexpr std::uint64_t kExpectedTransformBytes = 195'429'316ULL;
constexpr std::uint64_t kExpectedScannerBytes = 7'750'989ULL;
constexpr std::uint32_t kExpectedActiveBuckets = 6'674U;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

struct Options {
  std::string stream_path;
  sparkinterval::Sha256Digest expected_stream_sha256{};
  std::uint32_t repetitions = 3U;
  bool force_candidate_rejection_for_test = false;
  std::optional<std::string> containment_frames_out;
};

struct DeviceProfile {
  std::string name;
  int major = 0;
  int minor = 0;
  bool is_h100_sm90 = false;
};

unsigned int hex_nibble(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10U;
  throw std::runtime_error("SHA-256 is not hexadecimal");
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error("SHA-256 must have 64 hexadecimal digits");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    result[index] = static_cast<unsigned char>(
        (hex_nibble(text[2U * index]) << 4U) |
        hex_nibble(text[2U * index + 1U]));
  }
  return result;
}

bool digest_matches(
    const unsigned char* bytes, std::string_view expected_hex) {
  const sparkinterval::Sha256Digest expected =
      parse_sha256(expected_hex);
  return std::memcmp(bytes, expected.data(), expected.size()) == 0;
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
  if (argc < 3) {
    throw std::runtime_error(
        "usage: live-transform-candidate STREAM "
        "--expected-stream-sha256=HEX [--repetitions=N] "
        "[--containment-frames-out=PATH] "
        "[--force-candidate-rejection-for-test]");
  }
  Options result;
  result.stream_path = argv[1];
  bool digest_seen = false;
  for (int index = 2; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    constexpr std::string_view digest_prefix =
        "--expected-stream-sha256=";
    constexpr std::string_view repetitions_prefix = "--repetitions=";
    constexpr std::string_view containment_frames_prefix =
        "--containment-frames-out=";
    if (argument.starts_with(digest_prefix)) {
      if (digest_seen) {
        throw std::runtime_error("expected stream SHA-256 is duplicated");
      }
      result.expected_stream_sha256 =
          parse_sha256(argument.substr(digest_prefix.size()));
      digest_seen = true;
    } else if (argument.starts_with(repetitions_prefix)) {
      result.repetitions =
          parse_repetitions(argument.substr(repetitions_prefix.size()));
    } else if (argument.starts_with(containment_frames_prefix)) {
      if (result.containment_frames_out.has_value()) {
        throw std::runtime_error(
            "containment frame output is duplicated");
      }
      const std::string_view path =
          argument.substr(containment_frames_prefix.size());
      if (path.empty()) {
        throw std::runtime_error(
            "containment frame output path is empty");
      }
      if (std::filesystem::symlink_status(path).type() !=
          std::filesystem::file_type::not_found) {
        throw std::runtime_error(
            "containment artifact output already exists");
      }
      result.containment_frames_out = std::string(path);
    } else if (argument == "--force-candidate-rejection-for-test") {
      if (result.force_candidate_rejection_for_test) {
        throw std::runtime_error(
            "forced candidate rejection is duplicated");
      }
      result.force_candidate_rejection_for_test = true;
    } else {
      throw std::runtime_error("unknown live qualification argument");
    }
  }
  if (!digest_seen ||
      result.expected_stream_sha256 !=
          parse_sha256(kExpectedLogicalStreamSha256)) {
    throw std::runtime_error(
        "caller must pin the qualified block-0 V2 stream SHA-256");
  }
  return result;
}

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
        "strict live qualification target requires NVIDIA H100 sm_90");
  }
#endif
  return result;
}

struct AuthenticatedInput {
  pg2::Record record{};
  std::string file_sha256;
  std::string stream_sha256;
  std::size_t file_bytes = 0U;
};

AuthenticatedInput authenticate_input(const Options& options) {
  std::ifstream input(options.stream_path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor V2 stream");
  const std::streampos end = input.tellg();
  if (end < 0 ||
      static_cast<std::uint64_t>(end) != kExpectedFileBytes) {
    throw std::runtime_error(
        "Gamma Taylor V2 file has the wrong exact block-0 size");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  if (!input || input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("cannot read exact Gamma Taylor V2 bytes");
  }
  const sparkinterval::Sha256Digest file_sha =
      sparkinterval::sha256(bytes.data(), bytes.size());
  if (sparkinterval::lowercase_hex(file_sha) != kExpectedFileSha256) {
    throw std::runtime_error(
        "Gamma Taylor V2 file SHA-256 differs from the qualified fixture");
  }

  const std::string encoded(
      reinterpret_cast<const char*>(bytes.data()), bytes.size());
  std::istringstream decoded(
      encoded, std::ios::in | std::ios::binary);
  pg2::Reader reader(decoded, 0U, 1U, options.expected_stream_sha256);
  pg2::AuthenticatedChunk chunk;
  if (!reader.next(chunk) || chunk.first_block != 0U ||
      chunk.records.size() != 1U) {
    throw std::runtime_error(
        "Gamma Taylor V2 stream is not exactly block 0");
  }
  AuthenticatedInput result;
  result.record = chunk.records.front();
  reader.finish();
  if (!reader.complete() || reader.consumed_records() != 1U ||
      reader.chunk_count() != 1U) {
    throw std::runtime_error(
        "Gamma Taylor V2 reader did not authenticate the complete stream");
  }
  result.file_sha256 = sparkinterval::lowercase_hex(file_sha);
  result.stream_sha256 =
      sparkinterval::lowercase_hex(reader.stream_sha256());
  result.file_bytes = bytes.size();
  return result;
}

__device__ __forceinline__ std::uint64_t mix64(std::uint64_t value) {
  value ^= value >> 30U;
  value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27U;
  value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

struct RequiredAudit {
  unsigned long long invalid = 0U;
  unsigned long long ambiguous = 0U;
  unsigned long long digest = 0U;
  unsigned long long maximum_radius_bits = 0U;
};

__global__ void audit_required(
    const pw::RealDisk106* samples, RequiredAudit* audit) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < pdt::kSourceRequiredCount;
       index += blockDim.x * gridDim.x) {
    const pw::RealDisk106 value = samples[index];
    if (!isfinite(value.center.hi) || !isfinite(value.center.lo) ||
        !isfinite(value.radius) || value.radius < 0.0) {
      atomicAdd(&audit->invalid, 1ULL);
      continue;
    }
    const double center_lower =
        fmax(0.0, __dsub_rd(fabs(value.center.hi),
                            fabs(value.center.lo)));
    if (!(center_lower > value.radius) || value.center.hi == 0.0) {
      atomicAdd(&audit->ambiguous, 1ULL);
    }
    atomicMax(
        &audit->maximum_radius_bits,
        static_cast<unsigned long long>(
            __double_as_longlong(value.radius)));
    const std::uint64_t key = mix64(static_cast<std::uint64_t>(index));
    const std::uint64_t word =
        static_cast<std::uint64_t>(
            __double_as_longlong(value.center.hi)) ^
        (static_cast<std::uint64_t>(
             __double_as_longlong(value.center.lo)) << 1U) ^
        (static_cast<std::uint64_t>(
             __double_as_longlong(value.radius)) << 2U);
    atomicXor(&audit->digest, mix64(word ^ key));
  }
}

struct AccumulatorDeviceAudit {
  unsigned long long active_cells = 0U;
  unsigned long long inactive_cells = 0U;
  unsigned long long malformed_active_cells = 0U;
  unsigned long long nonzero_inactive_cells = 0U;
};

__device__ bool exact_positive_zero(double value) {
  return static_cast<std::uint64_t>(
             __double_as_longlong(value)) == 0U;
}

__global__ void audit_accumulator_row(
    const pw::ComplexDisk106* rows, const std::uint32_t* offsets,
    AccumulatorDeviceAudit* audit) {
  constexpr std::uint64_t cells =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x +
           threadIdx.x;
       index < cells;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t bucket =
        static_cast<std::uint32_t>(index % pw::kBucketCount);
    const pw::ComplexDisk106 value = rows[index];
    if (offsets[bucket] == offsets[bucket + 1U]) {
      atomicAdd(&audit->inactive_cells, 1ULL);
      if (!exact_positive_zero(value.real.hi) ||
          !exact_positive_zero(value.real.lo) ||
          !exact_positive_zero(value.imaginary.hi) ||
          !exact_positive_zero(value.imaginary.lo) ||
          !exact_positive_zero(value.radius)) {
        atomicAdd(&audit->nonzero_inactive_cells, 1ULL);
      }
    } else {
      atomicAdd(&audit->active_cells, 1ULL);
      if (!isfinite(value.real.hi) || !isfinite(value.real.lo) ||
          !isfinite(value.imaginary.hi) ||
          !isfinite(value.imaginary.lo) ||
          !isfinite(value.radius) || value.radius < 0.0) {
        atomicAdd(&audit->malformed_active_cells, 1ULL);
      }
    }
  }
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
  std::int32_t exponent = 0;
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
  const auto decoded = decode_finite(value);
  if (!decoded.has_value()) {
    throw std::runtime_error("exact checker received nonfinite binary64");
  }
  return *decoded;
}

cpp_rational decode_dd(pw::DoubleDouble value) {
  return decode_or_throw(value.hi) + decode_or_throw(value.lo);
}

enum class ExactSign : std::uint8_t {
  kPositive,
  kNegative,
  kAmbiguous,
  kMalformed,
};

ExactSign exact_sign(const pw::RealDisk106& value) {
  try {
    const cpp_rational center = decode_dd(value.center);
    const cpp_rational radius = decode_or_throw(value.radius);
    if (radius < 0) return ExactSign::kMalformed;
    if (center - radius > 0) return ExactSign::kPositive;
    if (center + radius < 0) return ExactSign::kNegative;
    return ExactSign::kAmbiguous;
  } catch (const std::exception&) {
    return ExactSign::kMalformed;
  }
}

struct Containment {
  std::uint64_t checked = 0U;
  std::uint64_t malformed = 0U;
  std::uint64_t radius_order_failures = 0U;
  std::uint64_t squared_distance_failures = 0U;
  std::uint64_t first_failure =
      std::numeric_limits<std::uint64_t>::max();

  bool accepted() const {
    return checked == pdt::kSourceSampleCount && malformed == 0U &&
           radius_order_failures == 0U &&
           squared_distance_failures == 0U;
  }
};

Containment exact_containment(
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate) {
  if (ordinary.size() != pdt::kSourceSampleCount ||
      candidate.size() != pdt::kSourceSampleCount) {
    throw std::runtime_error("whole-transform output size differs");
  }
  Containment result;
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
      } else {
        const cpp_rational radius_difference =
            candidate_radius - ordinary_radius;
        if (radius_difference < 0) {
          ++result.radius_order_failures;
        } else {
          const cpp_rational center_difference =
              candidate_center - ordinary_center;
          if (center_difference * center_difference >
              radius_difference * radius_difference) {
            ++result.squared_distance_failures;
          }
        }
      }
    } catch (const std::exception&) {
      ++result.malformed;
    }
    if (result.first_failure ==
            std::numeric_limits<std::uint64_t>::max() &&
        (result.malformed != 0U ||
         result.radius_order_failures != 0U ||
         result.squared_distance_failures != 0U)) {
      result.first_failure = index;
    }
  }
  return result;
}

struct ContainmentFrameArtifact {
  std::uint64_t frame_count = 0U;
  std::uint64_t byte_count = 0U;
  std::string sha256;
  bool written_bytes_rehashed = false;
};

class OwnedFileDescriptor {
 public:
  explicit OwnedFileDescriptor(int descriptor) : descriptor_(descriptor) {}
  ~OwnedFileDescriptor() {
    if (descriptor_ >= 0) {
      (void)::close(descriptor_);
    }
  }

  OwnedFileDescriptor(const OwnedFileDescriptor&) = delete;
  OwnedFileDescriptor& operator=(const OwnedFileDescriptor&) = delete;

  int get() const { return descriptor_; }

 private:
  int descriptor_ = -1;
};

void append_u64_le(
    std::vector<unsigned char>& bytes, std::uint64_t word) {
  for (unsigned int index = 0U; index < 8U; ++index) {
    bytes.push_back(static_cast<unsigned char>(
        word >> (8U * index)));
  }
}

void append_real_disk106_le(
    std::vector<unsigned char>& bytes,
    const pw::RealDisk106& disk) {
  append_u64_le(
      bytes, std::bit_cast<std::uint64_t>(disk.center.hi));
  append_u64_le(
      bytes, std::bit_cast<std::uint64_t>(disk.center.lo));
  append_u64_le(
      bytes, std::bit_cast<std::uint64_t>(disk.radius));
}

ContainmentFrameArtifact write_containment_frames(
    const std::string& path,
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate) {
  if (ordinary.size() != pdt::kSourceSampleCount ||
      candidate.size() != pdt::kSourceSampleCount) {
    throw std::runtime_error(
        "containment artifact transform output size differs");
  }
  if (std::filesystem::symlink_status(path).type() !=
      std::filesystem::file_type::not_found) {
    throw std::runtime_error(
        "containment artifact output already exists");
  }
  constexpr std::size_t kFrameBytes = 48U;
  std::vector<unsigned char> bytes;
  bytes.reserve(ordinary.size() * kFrameBytes);
  for (std::size_t index = 0U; index < ordinary.size(); ++index) {
    append_real_disk106_le(bytes, ordinary[index]);
    append_real_disk106_le(bytes, candidate[index]);
  }
  if (bytes.size() != ordinary.size() * kFrameBytes) {
    throw std::runtime_error(
        "containment artifact byte count differs");
  }
  const std::string expected_sha256 =
      sparkinterval::sha256_hex(bytes.data(), bytes.size());
  if (expected_sha256 !=
      kExpectedContainmentFrameArtifactSha256) {
    throw std::runtime_error(
        "containment artifact known answer differs");
  }
  const int raw_descriptor = ::open(
      path.c_str(),
      O_CREAT | O_EXCL | O_NOFOLLOW | O_RDWR | O_CLOEXEC,
      S_IRUSR | S_IWUSR);
  if (raw_descriptor < 0) {
    throw std::runtime_error(
        "cannot exclusively create containment artifact output");
  }
  OwnedFileDescriptor descriptor(raw_descriptor);
  std::size_t written = 0U;
  while (written < bytes.size()) {
    const ssize_t count = ::write(
        descriptor.get(), bytes.data() + written,
        bytes.size() - written);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) {
      throw std::runtime_error(
          "cannot write exact containment artifact bytes");
    }
    written += static_cast<std::size_t>(count);
  }
  if (::fsync(descriptor.get()) != 0) {
    throw std::runtime_error(
        "cannot synchronize containment artifact output");
  }
  struct stat status {};
  if (::fstat(descriptor.get(), &status) != 0 ||
      !S_ISREG(status.st_mode) || status.st_nlink != 1 ||
      status.st_size < 0 ||
      static_cast<std::uint64_t>(status.st_size) != bytes.size()) {
    throw std::runtime_error(
        "containment artifact output size differs");
  }
  if (::lseek(descriptor.get(), 0, SEEK_SET) != 0) {
    throw std::runtime_error(
        "cannot rewind containment artifact output");
  }
  std::vector<unsigned char> reloaded(bytes.size());
  std::size_t loaded = 0U;
  while (loaded < reloaded.size()) {
    const ssize_t count = ::read(
        descriptor.get(), reloaded.data() + loaded,
        reloaded.size() - loaded);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) {
      throw std::runtime_error(
          "cannot reread exact containment artifact bytes");
    }
    loaded += static_cast<std::size_t>(count);
  }
  unsigned char trailing = 0U;
  ssize_t trailing_count = 0;
  do {
    trailing_count = ::read(descriptor.get(), &trailing, 1U);
  } while (trailing_count < 0 && errno == EINTR);
  if (trailing_count != 0) {
    throw std::runtime_error(
        "cannot reread exact containment artifact bytes");
  }
  struct stat final_status {};
  if (::fstat(descriptor.get(), &final_status) != 0 ||
      final_status.st_dev != status.st_dev ||
      final_status.st_ino != status.st_ino ||
      final_status.st_size != status.st_size ||
      final_status.st_nlink != status.st_nlink) {
    throw std::runtime_error(
        "containment artifact identity changed during readback");
  }
  const std::string reloaded_sha256 =
      sparkinterval::sha256_hex(reloaded.data(), reloaded.size());
  if (reloaded_sha256 != expected_sha256 ||
      reloaded != bytes) {
    throw std::runtime_error(
        "containment artifact write-back differs");
  }
  return {
      .frame_count = ordinary.size(),
      .byte_count = bytes.size(),
      .sha256 = expected_sha256,
      .written_bytes_rehashed = true,
  };
}

struct SignComparison {
  std::uint64_t ordinary_ambiguous = 0U;
  std::uint64_t ordinary_malformed = 0U;
  std::uint64_t candidate_ambiguous = 0U;
  std::uint64_t candidate_malformed = 0U;
  std::uint64_t mismatch = 0U;

  bool accepted() const {
    return ordinary_ambiguous == 0U && ordinary_malformed == 0U &&
           candidate_ambiguous == 0U && candidate_malformed == 0U &&
           mismatch == 0U;
  }
};

SignComparison compare_required_signs(
    const std::vector<pw::RealDisk106>& ordinary,
    const std::vector<pw::RealDisk106>& candidate) {
  SignComparison result;
  for (std::size_t offset = 0U;
       offset < pdt::kSourceRequiredCount; ++offset) {
    const std::size_t index = pdt::kSourceRequiredBegin + offset;
    const ExactSign ordinary_sign = exact_sign(ordinary[index]);
    const ExactSign candidate_sign = exact_sign(candidate[index]);
    result.ordinary_ambiguous +=
        ordinary_sign == ExactSign::kAmbiguous;
    result.ordinary_malformed +=
        ordinary_sign == ExactSign::kMalformed;
    result.candidate_ambiguous +=
        candidate_sign == ExactSign::kAmbiguous;
    result.candidate_malformed +=
        candidate_sign == ExactSign::kMalformed;
    result.mismatch += ordinary_sign != candidate_sign;
  }
  return result;
}

template <typename Type>
bool vector_bytes_equal(
    const std::vector<Type>& left,
    const std::vector<Type>& right) {
  return left.size() == right.size() &&
         (left.empty() ||
          std::memcmp(left.data(), right.data(),
                      left.size() * sizeof(Type)) == 0);
}

bool replay_reports_byte_equal(
    const pes::ReplayReport& left,
    const pes::ReplayReport& right) {
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

bool event_topology_equal(
    const pes::ReplayReport& ordinary,
    const pes::ReplayReport& candidate) {
  for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    if (!vector_bytes_equal(ordinary.artifact.direct[stream],
                            candidate.artifact.direct[stream]) ||
        !vector_bytes_equal(ordinary.artifact.stationary[stream],
                            candidate.artifact.stationary[stream])) {
      return false;
    }
    pes::StreamSummary left = ordinary.artifact.summaries[stream];
    pes::StreamSummary right = candidate.artifact.summaries[stream];
    left.left_endpoint.disk = {};
    left.right_endpoint.disk = {};
    right.left_endpoint.disk = {};
    right.right_endpoint.disk = {};
    if (std::memcmp(&left, &right, sizeof(left)) != 0) return false;
  }
  return true;
}

bool replay_is_finite_and_reproduced(const pes::ReplayReport& report) {
  const pes::ScanStatus& status = report.artifact.status;
  return report.accepted && report.device_matches_host &&
         report.shared_endpoints_agree && report.error.empty() &&
         status.failure_flags == 0U &&
         status.certified_sample_count == pdt::kSourceRequiredCount &&
         status.digest_valid == 1U && status.reserved_zero == 0U;
}

bool ordinary_event_known_answer(const pes::ReplayReport& report) {
  if (!replay_is_finite_and_reproduced(report) ||
      !digest_matches(
          report.artifact.status.artifact_sha256,
          kExpectedOrdinaryArtifactSha256)) {
    return false;
  }
  for (std::uint32_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    const auto& summary = report.artifact.summaries[stream];
    if (summary.direct_event_count != kExpectedDirectCount[stream] ||
        summary.stationary_candidate_count !=
            kExpectedStationaryCount[stream] ||
        summary.certified_direct_multiplicity_slots !=
            kExpectedDirectCount[stream] ||
        summary.direct_nleft_units != kExpectedNleft[stream] ||
        summary.direct_nright_units != kExpectedNright[stream] ||
        report.artifact.direct[stream].size() !=
            kExpectedDirectCount[stream] ||
        report.artifact.stationary[stream].size() !=
            kExpectedStationaryCount[stream]) {
      return false;
    }
  }
  return true;
}

std::string sha256_hex(const void* data, std::size_t size) {
  return sparkinterval::lowercase_hex(
      sparkinterval::sha256(data, size));
}

std::string digest_hex(const unsigned char* bytes) {
  sparkinterval::Sha256Digest digest{};
  std::copy_n(bytes, digest.size(), digest.begin());
  return sparkinterval::lowercase_hex(digest);
}

std::string sample_sha256(
    const std::vector<pw::RealDisk106>& values) {
  return sha256_hex(
      values.data(), values.size() * sizeof(values.front()));
}

struct RootAudit {
  std::uint64_t malformed_roots = 0U;
  std::uint64_t malformed_norms = 0U;
  std::uint64_t norm_failures = 0U;
  std::string table_sha256;

  bool accepted() const {
    return malformed_roots == 0U && malformed_norms == 0U &&
           norm_failures == 0U &&
           table_sha256 == kExpectedRootTableSha256;
  }
};

struct RootSnapshot {
  std::vector<pw::ComplexDisk106> roots;
  std::vector<double> norms;
  RootAudit audit;
};

RootSnapshot snapshot_and_audit_roots(
    const pdt::Workspace* workspace, cudaStream_t stream) {
  const auto view = pdt::device_root_table_qualification(workspace);
  if (view.roots == nullptr || view.center_norm_upper == nullptr ||
      view.count != pw::kBucketCount) {
    throw std::runtime_error("root-table qualification geometry differs");
  }
  RootSnapshot result;
  result.roots.resize(view.count);
  result.norms.resize(view.count);
  CUDA_CHECK(cudaMemcpyAsync(
      result.roots.data(), view.roots,
      result.roots.size() * sizeof(result.roots.front()),
      cudaMemcpyDeviceToHost, stream));
  CUDA_CHECK(cudaMemcpyAsync(
      result.norms.data(), view.center_norm_upper,
      result.norms.size() * sizeof(result.norms.front()),
      cudaMemcpyDeviceToHost, stream));
  CUDA_CHECK(cudaStreamSynchronize(stream));
  sparkinterval::detail::Sha256 hasher;
  hasher.update(
      result.roots.data(),
      result.roots.size() * sizeof(result.roots.front()));
  hasher.update(
      result.norms.data(),
      result.norms.size() * sizeof(result.norms.front()));
  result.audit.table_sha256 =
      sparkinterval::lowercase_hex(hasher.finish());
  for (std::size_t index = 0U; index < result.roots.size(); ++index) {
    try {
      const auto& root = result.roots[index];
      const cpp_rational real = decode_dd(root.real);
      const cpp_rational imaginary = decode_dd(root.imaginary);
      const cpp_rational radius = decode_or_throw(root.radius);
      const cpp_rational norm = decode_or_throw(result.norms[index]);
      if (radius < 0) ++result.audit.malformed_roots;
      if (norm < 0) {
        ++result.audit.malformed_norms;
      } else if (real * real + imaginary * imaginary >
                 norm * norm) {
        ++result.audit.norm_failures;
      }
    } catch (const std::exception&) {
      const auto& root = result.roots[index];
      if (!std::isfinite(root.real.hi) ||
          !std::isfinite(root.real.lo) ||
          !std::isfinite(root.imaginary.hi) ||
          !std::isfinite(root.imaginary.lo) ||
          !std::isfinite(root.radius) || root.radius < 0.0) {
        ++result.audit.malformed_roots;
      }
      if (!std::isfinite(result.norms[index]) ||
          result.norms[index] < 0.0) {
        ++result.audit.malformed_norms;
      }
    }
  }
  return result;
}

struct AccumulatorAudit {
  AccumulatorDeviceAudit device{};
  bool offsets_bounded_monotone = false;
  bool active_roster_exact = false;
  std::string geometry_sha256;

  bool accepted() const {
    constexpr std::uint64_t active_cells =
        static_cast<std::uint64_t>(kExpectedActiveBuckets) *
        pw::kTaylorTerms;
    constexpr std::uint64_t all_cells =
        static_cast<std::uint64_t>(pw::kBucketCount) *
        pw::kTaylorTerms;
    return device.active_cells == active_cells &&
           device.inactive_cells == all_cells - active_cells &&
           device.malformed_active_cells == 0U &&
           device.nonzero_inactive_cells == 0U &&
           offsets_bounded_monotone && active_roster_exact &&
           geometry_sha256 == kExpectedAccumulatorGeometrySha256;
  }
};

AccumulatorAudit audit_accumulator(
    const pda::Workspace* workspace,
    const pda::SourceWindowView& view, cudaStream_t stream) {
  const std::uint32_t active_count =
      pda::active_bucket_count_qualification(workspace);
  if (active_count != kExpectedActiveBuckets) {
    throw std::runtime_error("active accumulator bucket count differs");
  }
  std::vector<std::uint32_t> offsets(pw::kBucketCount + 1U);
  std::vector<std::uint32_t> active(active_count);
  CUDA_CHECK(cudaMemcpyAsync(
      offsets.data(),
      pda::device_bucket_offsets_qualification(workspace),
      offsets.size() * sizeof(offsets.front()),
      cudaMemcpyDeviceToHost, stream));
  CUDA_CHECK(cudaMemcpyAsync(
      active.data(),
      pda::device_active_buckets_qualification(workspace),
      active.size() * sizeof(active.front()),
      cudaMemcpyDeviceToHost, stream));
  AccumulatorDeviceAudit* device_audit = nullptr;
  CUDA_CHECK(cudaMalloc(&device_audit, sizeof(*device_audit)));
  try {
    CUDA_CHECK(cudaMemsetAsync(
        device_audit, 0, sizeof(*device_audit), stream));
    audit_accumulator_row<<<256U, 256U, 0U, stream>>>(
        view.device_skn_rows,
        pda::device_bucket_offsets_qualification(workspace),
        device_audit);
    CUDA_CHECK(cudaGetLastError());
    AccumulatorAudit result;
    CUDA_CHECK(cudaMemcpyAsync(
        &result.device, device_audit, sizeof(result.device),
        cudaMemcpyDeviceToHost, stream));
    CUDA_CHECK(cudaStreamSynchronize(stream));
    CUDA_CHECK(cudaFree(device_audit));
    device_audit = nullptr;

    result.offsets_bounded_monotone =
        offsets.front() == 0U &&
        offsets.back() == pw::kSourceTerms;
    std::vector<std::uint32_t> reconstructed;
    reconstructed.reserve(active_count);
    for (std::uint32_t bucket = 0U;
         bucket < pw::kBucketCount; ++bucket) {
      if (offsets[bucket] > offsets[bucket + 1U] ||
          offsets[bucket + 1U] > pw::kSourceTerms) {
        result.offsets_bounded_monotone = false;
      }
      if (offsets[bucket] != offsets[bucket + 1U]) {
        reconstructed.push_back(bucket);
      }
    }
    result.active_roster_exact = reconstructed == active;
    sparkinterval::detail::Sha256 hasher;
    hasher.update(
        offsets.data(), offsets.size() * sizeof(offsets.front()));
    hasher.update(
        active.data(), active.size() * sizeof(active.front()));
    result.geometry_sha256 =
        sparkinterval::lowercase_hex(hasher.finish());
    return result;
  } catch (...) {
    if (device_audit != nullptr) cudaFree(device_audit);
    throw;
  }
}

struct Resources {
  pda::Workspace* accumulator = nullptr;
  pdt::Workspace* transform = nullptr;
  pes::Workspace* scanner = nullptr;
  pg2::Record* device_record = nullptr;
  pw::ComplexDisk106* device_gamma = nullptr;
  pgd::RowSummary* device_gamma_summary = nullptr;
  RequiredAudit* device_required_audit = nullptr;
  cudaStream_t stream = nullptr;
  cudaEvent_t started = nullptr;
  cudaEvent_t stopped = nullptr;

  ~Resources() {
    if (stream != nullptr) cudaStreamSynchronize(stream);
    if (started != nullptr) cudaEventDestroy(started);
    if (stopped != nullptr) cudaEventDestroy(stopped);
    if (device_required_audit != nullptr) {
      cudaFree(device_required_audit);
    }
    if (device_gamma_summary != nullptr) cudaFree(device_gamma_summary);
    if (device_gamma != nullptr) cudaFree(device_gamma);
    if (device_record != nullptr) cudaFree(device_record);
    if (scanner != nullptr) pes::destroy_workspace(scanner);
    if (transform != nullptr) pdt::destroy_workspace(transform);
    if (accumulator != nullptr) pda::destroy_workspace(accumulator);
    if (stream != nullptr) cudaStreamDestroy(stream);
  }
};

void initialize(Resources* resources) {
  resources->accumulator =
      pda::create_source_workspace(0U, 1U, 256U);
  resources->transform = pdt::create_source_workspace();
  resources->scanner = pes::create_workspace();
  CUDA_CHECK(cudaMalloc(
      &resources->device_record, sizeof(*resources->device_record)));
  CUDA_CHECK(cudaMalloc(
      &resources->device_gamma,
      pw::kBucketCount * sizeof(*resources->device_gamma)));
  CUDA_CHECK(cudaMalloc(
      &resources->device_gamma_summary,
      sizeof(*resources->device_gamma_summary)));
  CUDA_CHECK(cudaMalloc(
      &resources->device_required_audit,
      sizeof(*resources->device_required_audit)));
  CUDA_CHECK(cudaStreamCreateWithFlags(
      &resources->stream, cudaStreamNonBlocking));
  CUDA_CHECK(cudaEventCreate(&resources->started));
  CUDA_CHECK(cudaEventCreate(&resources->stopped));
}

enum class Variant : std::uint8_t {
  kOrdinary,
  kSettledSloppy,
  kTile9Sloppy,
};

void launch_variant(
    Resources* resources, const pda::SourceWindowView& skn,
    Variant variant) {
  switch (variant) {
    case Variant::kOrdinary:
      pdt::run_source_window(
          resources->transform, resources->device_gamma,
          skn.device_skn_rows, resources->stream);
      break;
    case Variant::kSettledSloppy:
      pdt::run_source_window_sloppy_root_qualification(
          resources->transform, resources->device_gamma,
          skn.device_skn_rows, resources->stream);
      break;
    case Variant::kTile9Sloppy:
      pdt::run_source_window_tile9_sloppy_root_qualification(
          resources->transform, resources->device_gamma,
          skn.device_skn_rows, resources->stream);
      break;
  }
}

struct VariantResult {
  std::vector<pw::RealDisk106> samples;
  std::uint32_t transform_failure_flags = 0U;
  RequiredAudit required_audit{};
  pes::ReplayReport replay;
  std::string all_sample_sha256;
  std::string required_sample_sha256;
};

VariantResult run_variant(
    Resources* resources, const pda::SourceWindowView& skn,
    Variant variant) {
  launch_variant(resources, skn, variant);
  CUDA_CHECK(cudaMemsetAsync(
      resources->device_required_audit, 0,
      sizeof(*resources->device_required_audit), resources->stream));
  audit_required<<<128U, 256U, 0U, resources->stream>>>(
      pdt::device_required_samples(resources->transform),
      resources->device_required_audit);
  CUDA_CHECK(cudaGetLastError());

  VariantResult result;
  result.samples.resize(pdt::kSourceSampleCount);
  CUDA_CHECK(cudaMemcpyAsync(
      result.samples.data(),
      pdt::device_samples(resources->transform),
      result.samples.size() * sizeof(result.samples.front()),
      cudaMemcpyDeviceToHost, resources->stream));
  CUDA_CHECK(cudaMemcpyAsync(
      &result.transform_failure_flags,
      pdt::device_input_failure_flags_qualification(
          resources->transform),
      sizeof(result.transform_failure_flags),
      cudaMemcpyDeviceToHost, resources->stream));
  CUDA_CHECK(cudaMemcpyAsync(
      &result.required_audit, resources->device_required_audit,
      sizeof(result.required_audit), cudaMemcpyDeviceToHost,
      resources->stream));
  CUDA_CHECK(cudaStreamSynchronize(resources->stream));

  pes::scan_source_required_samples(
      resources->scanner,
      pdt::device_required_samples(resources->transform),
      resources->stream);
  result.replay = pes::replay_and_check(
      resources->scanner,
      pdt::device_required_samples(resources->transform),
      resources->stream);
  result.all_sample_sha256 = sample_sha256(result.samples);
  result.required_sample_sha256 = sha256_hex(
      result.samples.data() + pdt::kSourceRequiredBegin,
      pdt::kSourceRequiredCount * sizeof(result.samples.front()));
  const std::vector<pw::RealDisk106> required(
      result.samples.begin() + pdt::kSourceRequiredBegin,
      result.samples.begin() + pdt::kSourceRequiredBegin +
          pdt::kSourceRequiredCount);
  if (!vector_bytes_equal(required, result.replay.required_samples)) {
    throw std::runtime_error(
        "scanner replay samples differ from the full output snapshot");
  }
  return result;
}

bool variant_finite(const VariantResult& result) {
  return result.transform_failure_flags == 0U &&
         result.required_audit.invalid == 0U &&
         result.required_audit.ambiguous == 0U &&
         replay_is_finite_and_reproduced(result.replay);
}

bool ordinary_known_answer(const VariantResult& result) {
  return variant_finite(result) &&
         result.required_audit.digest == kExpectedRequiredDigest &&
         result.required_audit.maximum_radius_bits ==
             kExpectedRequiredMaximumRadiusBits &&
         result.all_sample_sha256 ==
             kExpectedOrdinaryAllSampleSha256 &&
         result.required_sample_sha256 ==
             kExpectedOrdinaryRequiredSampleSha256 &&
         ordinary_event_known_answer(result.replay);
}

bool candidate_known_answer(const VariantResult& result) {
  return variant_finite(result) &&
         result.required_audit.digest ==
             kExpectedCandidateRequiredDigest &&
         result.required_audit.maximum_radius_bits ==
             kExpectedCandidateRequiredMaximumRadiusBits &&
         result.all_sample_sha256 ==
             kExpectedCandidateAllSampleSha256 &&
         result.required_sample_sha256 ==
             kExpectedCandidateRequiredSampleSha256 &&
         digest_matches(
             result.replay.artifact.status.artifact_sha256,
             kExpectedCandidateArtifactSha256);
}

struct Timing {
  double ordinary_median_ms = 0.0;
  double sloppy_median_ms = 0.0;
  double tile_median_ms = 0.0;
};

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  return values[values.size() / 2U];
}

double timed_variant(
    Resources* resources, const pda::SourceWindowView& skn,
    Variant variant) {
  CUDA_CHECK(cudaEventRecord(resources->started, resources->stream));
  launch_variant(resources, skn, variant);
  CUDA_CHECK(cudaEventRecord(resources->stopped, resources->stream));
  CUDA_CHECK(cudaEventSynchronize(resources->stopped));
  float milliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(
      &milliseconds, resources->started, resources->stopped));
  return milliseconds;
}

Timing benchmark(
    Resources* resources, const pda::SourceWindowView& skn,
    std::uint32_t repetitions) {
  std::vector<double> ordinary;
  std::vector<double> sloppy;
  std::vector<double> tile;
  ordinary.reserve(repetitions);
  sloppy.reserve(repetitions);
  tile.reserve(repetitions);
  for (std::uint32_t repetition = 0U;
       repetition < repetitions; ++repetition) {
    switch (repetition % 3U) {
      case 0U:
        ordinary.push_back(
            timed_variant(resources, skn, Variant::kOrdinary));
        sloppy.push_back(
            timed_variant(resources, skn, Variant::kSettledSloppy));
        tile.push_back(
            timed_variant(resources, skn, Variant::kTile9Sloppy));
        break;
      case 1U:
        tile.push_back(
            timed_variant(resources, skn, Variant::kTile9Sloppy));
        ordinary.push_back(
            timed_variant(resources, skn, Variant::kOrdinary));
        sloppy.push_back(
            timed_variant(resources, skn, Variant::kSettledSloppy));
        break;
      default:
        sloppy.push_back(
            timed_variant(resources, skn, Variant::kSettledSloppy));
        tile.push_back(
            timed_variant(resources, skn, Variant::kTile9Sloppy));
        ordinary.push_back(
            timed_variant(resources, skn, Variant::kOrdinary));
        break;
    }
  }
  return {
      .ordinary_median_ms = median(ordinary),
      .sloppy_median_ms = median(sloppy),
      .tile_median_ms = median(tile),
  };
}

std::string json_escape(std::string_view value) {
  std::string result;
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

void print_hex64(std::uint64_t value) {
  std::cout << '"' << std::hex << std::setw(16)
            << std::setfill('0') << value << std::dec
            << std::setfill(' ') << '"';
}

void print_variant(
    std::string_view name, const VariantResult& result) {
  std::cout
      << "{\"name\":\"" << name << "\""
      << ",\"transform_failure_flags\":"
      << result.transform_failure_flags
      << ",\"required_invalid\":" << result.required_audit.invalid
      << ",\"required_ambiguous\":"
      << result.required_audit.ambiguous
      << ",\"required_digest_xor\":";
  print_hex64(result.required_audit.digest);
  std::cout
      << ",\"maximum_required_radius_bits\":";
  print_hex64(result.required_audit.maximum_radius_bits);
  std::cout
      << ",\"all_sample_sha256\":\""
      << result.all_sample_sha256 << "\""
      << ",\"required_sample_sha256\":\""
      << result.required_sample_sha256 << "\""
      << ",\"scanner_accepted\":"
      << (result.replay.accepted ? "true" : "false")
      << ",\"scanner_device_matches_host\":"
      << (result.replay.device_matches_host ? "true" : "false")
      << ",\"scanner_shared_endpoints_agree\":"
      << (result.replay.shared_endpoints_agree ? "true" : "false")
      << ",\"scanner_failure_flags\":"
      << result.replay.artifact.status.failure_flags
      << ",\"scanner_artifact_sha256\":\""
      << digest_hex(result.replay.artifact.status.artifact_sha256)
      << "\",\"streams\":[";
  for (std::uint32_t stream = 0U;
       stream < pes::kStreamCount; ++stream) {
    if (stream != 0U) std::cout << ',';
    const auto& summary = result.replay.artifact.summaries[stream];
    std::cout
        << "{\"stream\":" << stream
        << ",\"direct_event_count\":"
        << summary.direct_event_count
        << ",\"stationary_candidate_count\":"
        << summary.stationary_candidate_count
        << ",\"certified_direct_multiplicity_slots\":"
        << summary.certified_direct_multiplicity_slots
        << ",\"direct_nleft_units\":"
        << summary.direct_nleft_units
        << ",\"direct_nright_units\":"
        << summary.direct_nright_units << '}';
  }
  std::cout
      << ']'
      << ",\"finite_and_reproduced\":"
      << (variant_finite(result) ? "true" : "false") << '}';
}

int run(const Options& options) {
  const AuthenticatedInput input = authenticate_input(options);
  const DeviceProfile device = require_and_read_device_profile();
  Resources resources;
  initialize(&resources);

  CUDA_CHECK(cudaMemcpyAsync(
      resources.device_record, &input.record, sizeof(input.record),
      cudaMemcpyHostToDevice, resources.stream));
  pgd::launch_synthesize(
      resources.device_record,
      {resources.device_gamma, 1U, pw::kBucketCount, 0U},
      resources.stream);
  pgd::launch_summarize(
      {resources.device_gamma, 1U, pw::kBucketCount, 0U},
      resources.device_gamma_summary, resources.stream);
  pgd::RowSummary gamma_summary{};
  CUDA_CHECK(cudaMemcpyAsync(
      &gamma_summary, resources.device_gamma_summary,
      sizeof(gamma_summary), cudaMemcpyDeviceToHost,
      resources.stream));
  const pda::SourceWindowView skn =
      pda::run_next_source_window(resources.accumulator, resources.stream);
  CUDA_CHECK(cudaStreamSynchronize(resources.stream));

  const bool gamma_known_answer =
      gamma_summary.logical_block == 0U &&
      gamma_summary.invalid_disks == 0U &&
      gamma_summary.digest == kExpectedGammaDigest &&
      std::bit_cast<std::uint64_t>(gamma_summary.maximum_radius) ==
          kExpectedGammaMaximumRadiusBits;
  const bool source_geometry =
      skn.device_skn_rows != nullptr && skn.logical_block == 0U &&
      skn.window_center == pw::kSourceLower + pw::kWindowStep / 2U &&
      skn.stage_count == pw::kTaylorTerms &&
      skn.row_stride == pw::kBucketCount &&
      pda::windows_enqueued(resources.accumulator) == 1U &&
      pda::workspace_device_bytes(resources.accumulator) ==
          kExpectedAccumulatorBytes &&
      pdt::workspace_device_bytes(resources.transform) ==
          kExpectedTransformBytes &&
      pes::workspace_device_bytes(resources.scanner) ==
          kExpectedScannerBytes;
  const AccumulatorAudit accumulator =
      audit_accumulator(resources.accumulator, skn, resources.stream);
  const RootSnapshot roots_before =
      snapshot_and_audit_roots(resources.transform, resources.stream);
  const auto kernel_resources =
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

  const VariantResult ordinary =
      run_variant(&resources, skn, Variant::kOrdinary);
  const VariantResult sloppy =
      run_variant(&resources, skn, Variant::kSettledSloppy);
  const VariantResult tile =
      run_variant(&resources, skn, Variant::kTile9Sloppy);
  const RootSnapshot roots_after =
      snapshot_and_audit_roots(resources.transform, resources.stream);

  const Containment containment =
      exact_containment(ordinary.samples, sloppy.samples);
  const SignComparison signs =
      compare_required_signs(ordinary.samples, sloppy.samples);
  const bool tile_byte_identity =
      vector_bytes_equal(sloppy.samples, tile.samples);
  const bool tile_replay_identity =
      replay_reports_byte_equal(sloppy.replay, tile.replay);
  const bool event_topology_identity =
      event_topology_equal(ordinary.replay, sloppy.replay);
  const bool root_table_immutable =
      vector_bytes_equal(roots_before.roots, roots_after.roots) &&
      vector_bytes_equal(roots_before.norms, roots_after.norms);
  const bool ordinary_accepted = ordinary_known_answer(ordinary);
  const bool sloppy_known_answer = candidate_known_answer(sloppy);
  const bool tile_known_answer = candidate_known_answer(tile);
  const bool candidate_semantic_gates_accepted =
      gamma_known_answer && source_geometry && accumulator.accepted() &&
      roots_before.audit.accepted() && roots_after.audit.accepted() &&
      root_table_immutable && kernel_resources_accepted &&
      ordinary_accepted && sloppy_known_answer &&
      tile_known_answer && containment.accepted() &&
      signs.accepted() && event_topology_identity &&
      tile_byte_identity && tile_replay_identity;
  const bool candidate_qualified =
      candidate_semantic_gates_accepted &&
      !options.force_candidate_rejection_for_test;

  bool fallback_exercised = false;
  bool fallback_reproduced_ordinary = false;
  std::optional<VariantResult> fallback;
  if (!candidate_qualified) {
    fallback_exercised = true;
    fallback = run_variant(&resources, skn, Variant::kOrdinary);
    fallback_reproduced_ordinary =
        vector_bytes_equal(fallback->samples, ordinary.samples) &&
        replay_reports_byte_equal(fallback->replay, ordinary.replay) &&
        ordinary_known_answer(*fallback);
  }
  const bool pipeline_accepted =
      ordinary_accepted &&
      (candidate_qualified || fallback_reproduced_ordinary);
  const Timing timing = candidate_qualified
                            ? benchmark(
                                  &resources, skn,
                                  options.repetitions)
                            : Timing{};
  std::optional<ContainmentFrameArtifact> containment_artifact;
  if (candidate_qualified &&
      options.containment_frames_out.has_value()) {
    containment_artifact = write_containment_frames(
        *options.containment_frames_out,
        ordinary.samples, sloppy.samples);
  }
  const bool target_h100_measured =
      kStrictH100Target && device.is_h100_sm90;

  std::cout
      << std::setprecision(17)
      << "{\"schema\":"
         "\"sparkinterval.tg.platt-pt21-live-transform-candidate-"
         "qualification.v1\""
      << ",\"accepted\":"
      << (pipeline_accepted ? "true" : "false")
      << ",\"candidate_semantic_gates_accepted\":"
      << (candidate_semantic_gates_accepted ? "true" : "false")
      << ",\"candidate_qualified\":"
      << (candidate_qualified ? "true" : "false")
      << ",\"candidate_rejection_forced_for_test\":"
      << (options.force_candidate_rejection_for_test ? "true" : "false")
      << ",\"selected_implementation\":\""
      << (candidate_qualified ? "tile9-sloppy-root"
                              : "ordinary-fallback")
      << "\""
      << ",\"qualification_only\":true"
      << ",\"first_block\":0,\"block_count\":1"
      << ",\"gamma_stream_file_bytes\":" << input.file_bytes
      << ",\"gamma_stream_file_sha256\":\""
      << input.file_sha256 << "\""
      << ",\"gamma_stream_logical_sha256\":\""
      << input.stream_sha256 << "\""
      << ",\"gamma_stream_authenticated_before_gpu_allocation\":true"
      << ",\"gamma_summary\":{\"logical_block\":"
      << gamma_summary.logical_block
      << ",\"invalid_disks\":" << gamma_summary.invalid_disks
      << ",\"digest\":";
  print_hex64(gamma_summary.digest);
  std::cout << ",\"maximum_radius_bits\":";
  print_hex64(std::bit_cast<std::uint64_t>(
      gamma_summary.maximum_radius));
  std::cout
      << ",\"known_answer\":"
      << (gamma_known_answer ? "true" : "false") << "}"
      << ",\"single_accumulator_workspace\":true"
      << ",\"single_transform_workspace\":true"
      << ",\"single_event_scanner_workspace\":true"
      << ",\"accumulator_workspace_device_bytes\":"
      << pda::workspace_device_bytes(resources.accumulator)
      << ",\"transform_workspace_device_bytes\":"
      << pdt::workspace_device_bytes(resources.transform)
      << ",\"event_scanner_workspace_device_bytes\":"
      << pes::workspace_device_bytes(resources.scanner)
      << ",\"source_geometry_accepted\":"
      << (source_geometry ? "true" : "false")
      << ",\"accumulator_audit\":{\"active_cells\":"
      << accumulator.device.active_cells
      << ",\"inactive_cells\":"
      << accumulator.device.inactive_cells
      << ",\"malformed_active_cells\":"
      << accumulator.device.malformed_active_cells
      << ",\"nonzero_inactive_cells\":"
      << accumulator.device.nonzero_inactive_cells
      << ",\"offsets_bounded_monotone\":"
      << (accumulator.offsets_bounded_monotone ? "true" : "false")
      << ",\"active_roster_exact\":"
      << (accumulator.active_roster_exact ? "true" : "false")
      << ",\"geometry_sha256\":\""
      << accumulator.geometry_sha256 << "\""
      << ",\"accepted\":"
      << (accumulator.accepted() ? "true" : "false") << "}"
      << ",\"root_table_audit\":{\"before_sha256\":\""
      << roots_before.audit.table_sha256
      << "\",\"after_sha256\":\""
      << roots_after.audit.table_sha256
      << "\",\"immutable\":"
      << (root_table_immutable ? "true" : "false")
      << ",\"accepted\":"
      << (roots_before.audit.accepted() &&
                  roots_after.audit.accepted()
              ? "true"
              : "false")
      << "}"
      << ",\"kernel_resources\":{\"registers_per_thread\":"
      << kernel_resources.registers_per_thread
      << ",\"static_shared_bytes\":"
      << kernel_resources.static_shared_bytes
      << ",\"local_bytes_per_thread\":"
      << kernel_resources.local_bytes_per_thread
      << ",\"maximum_threads_per_block\":"
      << kernel_resources.maximum_threads_per_block
      << ",\"active_blocks_per_multiprocessor\":"
      << kernel_resources.active_blocks_per_multiprocessor
      << ",\"accepted\":"
      << (kernel_resources_accepted ? "true" : "false") << "}"
      << ",\"variants\":[";
  print_variant("ordinary", ordinary);
  std::cout << ',';
  print_variant("settled-sloppy-root", sloppy);
  std::cout << ',';
  print_variant("tile9-sloppy-root", tile);
  std::cout
      << "]"
      << ",\"ordinary_known_answer\":"
      << (ordinary_accepted ? "true" : "false")
      << ",\"settled_sloppy_known_answer\":"
      << (sloppy_known_answer ? "true" : "false")
      << ",\"tile9_sloppy_known_answer\":"
      << (tile_known_answer ? "true" : "false")
      << ",\"exact_all_sample_containment\":{\"sample_count\":"
      << containment.checked
      << ",\"malformed\":" << containment.malformed
      << ",\"radius_order_failures\":"
      << containment.radius_order_failures
      << ",\"squared_distance_failures\":"
      << containment.squared_distance_failures
      << ",\"accepted\":"
      << (containment.accepted() ? "true" : "false") << "}"
      << ",\"containment_frame_artifact_emitted\":"
      << (containment_artifact.has_value() ? "true" : "false")
      << ",\"containment_frame_artifact_authenticated\":false"
      << ",\"containment_frame_artifact_written_bytes_rehashed\":"
      << (containment_artifact.has_value() &&
                  containment_artifact->written_bytes_rehashed
              ? "true"
              : "false")
      << ",\"containment_frame_artifact_frame_count\":"
      << (containment_artifact.has_value()
              ? containment_artifact->frame_count
              : 0U)
      << ",\"containment_frame_artifact_bytes\":"
      << (containment_artifact.has_value()
              ? containment_artifact->byte_count
              : 0U)
      << ",\"containment_frame_artifact_sha256\":"
      << (containment_artifact.has_value() ? "\"" : "null")
      << (containment_artifact.has_value()
              ? containment_artifact->sha256
              : std::string{})
      << (containment_artifact.has_value() ? "\"" : "")
      << ",\"containment_frame_artifact_lean_check_executed\":false"
      << ",\"prospective_containment_frame_count\":"
      << pdt::kSourceSampleCount
      << ",\"prospective_containment_frame_bytes\":48"
      << ",\"prospective_containment_artifact_bytes\":"
      << static_cast<std::uint64_t>(pdt::kSourceSampleCount) * 48U
      << ",\"required_sign_comparison\":{\"ordinary_ambiguous\":"
      << signs.ordinary_ambiguous
      << ",\"ordinary_malformed\":" << signs.ordinary_malformed
      << ",\"candidate_ambiguous\":" << signs.candidate_ambiguous
      << ",\"candidate_malformed\":" << signs.candidate_malformed
      << ",\"mismatch\":" << signs.mismatch
      << ",\"accepted\":"
      << (signs.accepted() ? "true" : "false") << "}"
      << ",\"ordinary_sloppy_event_topology_identical\":"
      << (event_topology_identity ? "true" : "false")
      << ",\"tile_settled_all_sample_bytes_identical\":"
      << (tile_byte_identity ? "true" : "false")
      << ",\"tile_settled_replay_artifact_identical\":"
      << (tile_replay_identity ? "true" : "false")
      << ",\"fallback_exercised\":"
      << (fallback_exercised ? "true" : "false")
      << ",\"fallback_reproduced_ordinary\":"
      << (fallback_reproduced_ordinary ? "true" : "false")
      << ",\"build_profile\":{\"cmake_build_config\":\""
      << kBuildProfile << "\",\"ndebug_defined\":"
      << (kNdebugDefined ? "true" : "false")
      << ",\"release_performance_build\":"
      << (kReleasePerformanceBuild ? "true" : "false") << "}"
      << ",\"device_profile\":{\"name\":\""
      << json_escape(device.name) << "\",\"major\":"
      << device.major << ",\"minor\":" << device.minor << "}"
      << ",\"strict_h100_target\":"
      << (kStrictH100Target ? "true" : "false")
      << ",\"target_h100_measured\":"
      << (target_h100_measured ? "true" : "false")
      << ",\"repetitions\":" << options.repetitions
      << ",\"timing\":{\"ordinary_median_ms\":"
      << timing.ordinary_median_ms
      << ",\"settled_sloppy_median_ms\":"
      << timing.sloppy_median_ms
      << ",\"tile9_sloppy_median_ms\":"
      << timing.tile_median_ms << "}"
      << ",\"release_build_profile_eligible\":"
      << (candidate_qualified && kReleasePerformanceBuild
                  ? "true"
                  : "false")
      << ",\"runtime_instrumentation_status\":"
         "\"not-inspected-by-runner\""
      << ",\"performance_evidence_eligible\":false"
      << ",\"candidate_selected_in_production\":false"
      << ",\"receipt_emitted\":false"
      << ",\"secure_enclave_attested\":false"
      << ",\"cuda_to_lean_refinement_proved\":false"
      << ",\"ordinary_hardy_z_realization_proved\":false"
      << ",\"flint_to_mathlib_proved\":false"
      << ",\"all_window_coverage_complete\":false"
      << ",\"stationary_turing_closure_complete\":false"
      << ",\"source_claim_ready\":false"
      << ",\"production_ready\":false"
      << ",\"pt21_atom_discharged\":false}\n";
  return pipeline_accepted ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr
        << "sparkinterval-tg-platt-pt21-live-transform-candidate-"
           "qualification: "
        << error.what() << '\n';
    return 2;
  }
}

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded authenticated consumer and full-row comparison harness for the V2
// DD Gamma Taylor stream.  This is a finite arithmetic component; it does not
// identify FLINT's acb_lgamma with Mathlib's complex Gamma and does not claim
// the PT21 theorem.

#include "sparkinterval/tg_platt_gamma_dd_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"

#include <cuda_runtime.h>
#include <mpfr.h>

#include <algorithm>
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
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace pgd = sparkinterval::tg::platt_gamma_dd_gpu;
namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +               \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

struct MpfrValue {
  mpfr_t value;
  // 2176 bits exceed the full exponent span of any sum of two finite
  // binary64 values.  Thus arbitrary (not merely normalized) DD centres are
  // reconstructed exactly before the directed containment arithmetic.
  MpfrValue() { mpfr_init2(value, 2176U); }
  ~MpfrValue() { mpfr_clear(value); }
  MpfrValue(const MpfrValue&) = delete;
  MpfrValue& operator=(const MpfrValue&) = delete;
};

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
        "strict production target requires an NVIDIA H100 sm_90 device");
  }
#endif
}

struct Options {
  std::string stream_path;
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  std::uint32_t maximum_chunk_records = 4096U;
  std::string direct_first_row;
  std::string direct_last_row;
  std::string export_first_row;
  std::string export_last_row;
  std::optional<sparkinterval::Sha256Digest> expected_stream_sha256;
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
  auto nibble = [](char value) -> unsigned {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10U;
    throw std::runtime_error("expected V2 stream SHA-256 is not hexadecimal");
  };
  return static_cast<unsigned char>((nibble(high) << 4U) | nibble(low));
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error(
        "expected V2 stream SHA-256 must have 64 hexadecimal digits");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    result[index] = parse_hex_byte(text[2U * index], text[2U * index + 1U]);
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  if (argc < 4) {
    throw std::runtime_error(
        "usage: gamma-v2-consumer STREAM FIRST_BLOCK BLOCK_COUNT "
        "[--max-chunk-records=N] [--direct-first-row=PATH] "
        "[--direct-last-row=PATH] [--export-first-row=PATH] "
        "[--export-last-row=PATH] --expected-stream-sha256=HEX");
  }
  Options result;
  result.stream_path = argv[1];
  result.first_block = parse_unsigned(argv[2], "first block");
  result.block_count = parse_unsigned(argv[3], "block count");
  for (int index = 4; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto after = [&](std::string_view prefix)
        -> std::optional<std::string_view> {
      if (!argument.starts_with(prefix)) return std::nullopt;
      return argument.substr(prefix.size());
    };
    if (const auto value = after("--max-chunk-records=")) {
      const auto parsed = parse_unsigned(*value, "maximum chunk records");
      if (parsed == 0U || parsed > (1U << 20U)) {
        throw std::runtime_error("maximum chunk records is outside range");
      }
      result.maximum_chunk_records = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = after("--direct-first-row=")) {
      result.direct_first_row = std::string(*value);
    } else if (const auto value = after("--direct-last-row=")) {
      result.direct_last_row = std::string(*value);
    } else if (const auto value = after("--export-first-row=")) {
      result.export_first_row = std::string(*value);
    } else if (const auto value = after("--export-last-row=")) {
      result.export_last_row = std::string(*value);
    } else if (const auto value = after("--expected-stream-sha256=")) {
      result.expected_stream_sha256 = parse_sha256(*value);
    } else {
      throw std::runtime_error("unknown option: " + std::string(argument));
    }
  }
  if (result.stream_path.empty() || result.block_count == 0U ||
      result.first_block >= pw::kFullBlockCount ||
      result.block_count > pw::kFullBlockCount - result.first_block) {
    throw std::runtime_error("V2 consumer range is outside PT21 geometry");
  }
  if (!result.expected_stream_sha256) {
    throw std::runtime_error(
        "V2 consumer requires --expected-stream-sha256 from a trusted "
        "manifest");
  }
  return result;
}

std::uint64_t fnv1a(const void* raw, std::size_t size) {
  std::uint64_t result = 1469598103934665603ULL;
  const auto* bytes = static_cast<const unsigned char*>(raw);
  for (std::size_t index = 0U; index < size; ++index) {
    result ^= bytes[index];
    result *= 1099511628211ULL;
  }
  return result;
}

void validate_packet_header(const pw::SourcePacketHeader& header,
                            std::uint64_t expected_height) {
  if (header.magic != pw::kGammaPacket106Magic ||
      header.version != pw::kSourcePacket106Version ||
      header.header_bytes != sizeof(header) ||
      header.endian_tag != pw::kSourcePacketEndianTag ||
      header.interval_encoding != pw::kSourcePacket106Encoding ||
      header.bucket_count != pw::kBucketCount ||
      header.taylor_terms != pg2::kDegree || header.source_terms != 0U ||
      header.reserved_zero != 0U || header.window_center != expected_height ||
      header.gamma_count != pw::kBucketCount || header.skn_count != 0U ||
      header.payload_bytes !=
          pw::kBucketCount * sizeof(pw::ComplexDisk106) ||
      header.skn_fnv1a64 != fnv1a(nullptr, 0U) ||
      std::memcmp(header.upstream_commit.data(), pw::kUpstreamCommit,
                  header.upstream_commit.size()) != 0) {
    throw std::runtime_error("direct FLINT DD Gamma packet framing differs");
  }
}

std::vector<pw::ComplexDisk106> read_direct_row(
    const std::string& path, std::uint64_t height) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open direct FLINT DD row");
  pw::SourcePacketHeader header{};
  input.read(reinterpret_cast<char*>(&header), sizeof(header));
  if (!input) throw std::runtime_error("direct FLINT DD row is truncated");
  validate_packet_header(header, height);
  std::vector<pw::ComplexDisk106> result(pw::kBucketCount);
  input.read(reinterpret_cast<char*>(result.data()),
             static_cast<std::streamsize>(header.payload_bytes));
  if (input.gcount() != static_cast<std::streamsize>(header.payload_bytes)) {
    throw std::runtime_error("direct FLINT DD row payload is truncated");
  }
  char trailing = 0;
  input.read(&trailing, 1);
  if (input.gcount() != 0 ||
      fnv1a(result.data(), header.payload_bytes) != header.gamma_fnv1a64) {
    throw std::runtime_error("direct FLINT DD row payload differs");
  }
  for (const auto& value : result) {
    if (!std::isfinite(value.real.hi) || !std::isfinite(value.real.lo) ||
        !std::isfinite(value.imaginary.hi) ||
        !std::isfinite(value.imaginary.lo) ||
        !std::isfinite(value.radius) || value.radius < 0.0) {
      throw std::runtime_error("direct FLINT DD row has an invalid disk");
    }
  }
  return result;
}

void write_row(const std::string& path,
               const std::vector<pw::ComplexDisk106>& row,
               std::uint64_t height) {
  if (path.empty()) return;
  pw::SourcePacketHeader header{};
  header.magic = pw::kGammaPacket106Magic;
  header.version = pw::kSourcePacket106Version;
  header.header_bytes = sizeof(header);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.interval_encoding = pw::kSourcePacket106Encoding;
  header.bucket_count = pw::kBucketCount;
  header.taylor_terms = pg2::kDegree;
  header.window_center = height;
  header.gamma_count = row.size();
  header.payload_bytes = row.size() * sizeof(row.front());
  header.gamma_fnv1a64 = fnv1a(row.data(), header.payload_bytes);
  header.skn_fnv1a64 = fnv1a(nullptr, 0U);
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) throw std::runtime_error("cannot open DD row export");
  output.write(reinterpret_cast<const char*>(&header), sizeof(header));
  output.write(reinterpret_cast<const char*>(row.data()),
               static_cast<std::streamsize>(header.payload_bytes));
  output.close();
  if (!output) throw std::runtime_error("cannot write complete DD row");
}

struct Comparison {
  std::uint64_t failures = 0U;
  long double maximum_required_radius = 0.0L;
  long double maximum_radius_ratio = 0.0L;
};

Comparison compare_rows(const std::vector<pw::ComplexDisk106>& outer,
                        const std::vector<pw::ComplexDisk106>& inner) {
  if (outer.size() != inner.size()) {
    throw std::runtime_error("Gamma row comparison geometry differs");
  }
  Comparison result;
  MpfrValue outer_re_mpfr;
  MpfrValue outer_im_mpfr;
  MpfrValue inner_re_mpfr;
  MpfrValue inner_im_mpfr;
  MpfrValue delta_re_mpfr;
  MpfrValue delta_im_mpfr;
  MpfrValue distance_mpfr;
  MpfrValue required_mpfr;
  for (std::size_t index = 0U; index < outer.size(); ++index) {
    const long double outer_re =
        static_cast<long double>(outer[index].real.hi) +
        static_cast<long double>(outer[index].real.lo);
    const long double outer_im =
        static_cast<long double>(outer[index].imaginary.hi) +
        static_cast<long double>(outer[index].imaginary.lo);
    const long double inner_re =
        static_cast<long double>(inner[index].real.hi) +
        static_cast<long double>(inner[index].real.lo);
    const long double inner_im =
        static_cast<long double>(inner[index].imaginary.hi) +
        static_cast<long double>(inner[index].imaginary.lo);
    const long double distance =
        hypotl(outer_re - inner_re, outer_im - inner_im);
    const long double required =
        distance + static_cast<long double>(inner[index].radius);
    result.maximum_required_radius =
        std::max(result.maximum_required_radius, required);
    if (outer[index].radius > 0.0) {
      result.maximum_radius_ratio = std::max(
          result.maximum_radius_ratio,
          required / static_cast<long double>(outer[index].radius));
    }
    // The acceptance decision is not made in long double.  Each arbitrary
    // finite binary64 pair is reconstructed exactly at 2176 bits; squared
    // distance, square root, and inner-radius addition are rounded upward by
    // MPFR.
    mpfr_set_d(outer_re_mpfr.value, outer[index].real.hi, MPFR_RNDN);
    mpfr_add_d(outer_re_mpfr.value, outer_re_mpfr.value,
               outer[index].real.lo,
               MPFR_RNDN);
    mpfr_set_d(outer_im_mpfr.value, outer[index].imaginary.hi, MPFR_RNDN);
    mpfr_add_d(outer_im_mpfr.value, outer_im_mpfr.value,
               outer[index].imaginary.lo,
               MPFR_RNDN);
    mpfr_set_d(inner_re_mpfr.value, inner[index].real.hi, MPFR_RNDN);
    mpfr_add_d(inner_re_mpfr.value, inner_re_mpfr.value,
               inner[index].real.lo,
               MPFR_RNDN);
    mpfr_set_d(inner_im_mpfr.value, inner[index].imaginary.hi, MPFR_RNDN);
    mpfr_add_d(inner_im_mpfr.value, inner_im_mpfr.value,
               inner[index].imaginary.lo,
               MPFR_RNDN);
    mpfr_sub(delta_re_mpfr.value, outer_re_mpfr.value,
             inner_re_mpfr.value, MPFR_RNDN);
    mpfr_sub(delta_im_mpfr.value, outer_im_mpfr.value,
             inner_im_mpfr.value, MPFR_RNDN);
    mpfr_mul(distance_mpfr.value, delta_re_mpfr.value,
             delta_re_mpfr.value, MPFR_RNDU);
    mpfr_fma(distance_mpfr.value, delta_im_mpfr.value,
             delta_im_mpfr.value, distance_mpfr.value,
             MPFR_RNDU);
    mpfr_sqrt(distance_mpfr.value, distance_mpfr.value, MPFR_RNDU);
    mpfr_add_d(required_mpfr.value, distance_mpfr.value,
               inner[index].radius,
               MPFR_RNDU);
    if (!std::isfinite(outer[index].radius) || outer[index].radius < 0.0 ||
        mpfr_cmp_d(required_mpfr.value, outer[index].radius) > 0) {
      ++result.failures;
    }
  }
  return result;
}

int run(const Options& options) {
  static_assert(std::endian::native == std::endian::little);
  require_target_device();
  std::ifstream input(options.stream_path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor V2 stream");
  pg2::Reader reader(input, options.first_block, options.block_count,
                     options.expected_stream_sha256);
  if (reader.header().chunk_records > options.maximum_chunk_records) {
    throw std::runtime_error("V2 chunk exceeds configured host-memory cap");
  }

  pg2::Record* device_record = nullptr;
  pw::ComplexDisk106* device_row = nullptr;
  pgd::RowSummary* device_summary = nullptr;
  cudaStream_t stream = nullptr;
  cudaEvent_t started = nullptr;
  cudaEvent_t stopped = nullptr;
  CUDA_CHECK(cudaMalloc(&device_record, sizeof(*device_record)));
  CUDA_CHECK(cudaMalloc(&device_row,
                        pw::kBucketCount * sizeof(*device_row)));
  CUDA_CHECK(cudaMalloc(&device_summary, sizeof(*device_summary)));
  CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
  CUDA_CHECK(cudaEventCreate(&started));
  CUDA_CHECK(cudaEventCreate(&stopped));

  std::uint64_t records = 0U;
  std::uint64_t invalid = 0U;
  double maximum_radius = 0.0;
  std::uint64_t digest = 0U;
  Comparison first_comparison;
  Comparison last_comparison;
  bool compared_first = false;
  bool compared_last = false;
  std::vector<pw::ComplexDisk106> host_row(pw::kBucketCount);
  std::vector<pw::ComplexDisk106> first_export_row;
  std::vector<pw::ComplexDisk106> last_export_row;
  CUDA_CHECK(cudaEventRecord(started, stream));
  pg2::AuthenticatedChunk chunk;
  while (reader.next(chunk)) {
    for (std::size_t offset = 0U; offset < chunk.records.size(); ++offset) {
      const std::uint64_t logical_block = chunk.first_block + offset;
      if (logical_block != options.first_block + records) {
        throw std::runtime_error("V2 records are not gap-free");
      }
      CUDA_CHECK(cudaMemcpyAsync(device_record, &chunk.records[offset],
                                 sizeof(*device_record),
                                 cudaMemcpyHostToDevice, stream));
      const pgd::BatchView view{device_row, 1U, pw::kBucketCount,
                                logical_block};
      pgd::launch_synthesize(device_record, view, stream);
      pgd::launch_summarize(view, device_summary, stream);
      pgd::RowSummary summary{};
      CUDA_CHECK(cudaMemcpyAsync(&summary, device_summary, sizeof(summary),
                                 cudaMemcpyDeviceToHost, stream));
      const bool is_first = records == 0U;
      const bool is_last = records + 1U == options.block_count;
      if (is_first || is_last) {
        CUDA_CHECK(cudaMemcpyAsync(
            host_row.data(), device_row,
            host_row.size() * sizeof(host_row.front()),
            cudaMemcpyDeviceToHost, stream));
      }
      CUDA_CHECK(cudaStreamSynchronize(stream));
      invalid += summary.invalid_disks;
      maximum_radius = std::max(maximum_radius, summary.maximum_radius);
      digest ^= summary.digest;
      const std::uint64_t height = pw::kSourceLower + pw::kWindowStep / 2U +
                                   logical_block * pw::kWindowStep;
      if (is_first) {
        if (!options.export_first_row.empty()) first_export_row = host_row;
        if (!options.direct_first_row.empty()) {
          first_comparison =
              compare_rows(host_row,
                           read_direct_row(options.direct_first_row, height));
          compared_first = true;
        }
      }
      if (is_last) {
        if (!options.export_last_row.empty()) last_export_row = host_row;
        if (!options.direct_last_row.empty()) {
          last_comparison =
              compare_rows(host_row,
                           read_direct_row(options.direct_last_row, height));
          compared_last = true;
        }
      }
      ++records;
    }
  }
  if (!reader.complete() || records != options.block_count || invalid != 0U) {
    throw std::runtime_error("V2 consumer did not produce a complete valid shard");
  }
  // No exported artifact becomes visible until the whole-stream footer,
  // optional externally expected digest, EOF, record count, and device
  // validity checks have all passed.
  const std::uint64_t first_height =
      pw::kSourceLower + pw::kWindowStep / 2U +
      options.first_block * pw::kWindowStep;
  const std::uint64_t last_height =
      first_height + (options.block_count - 1U) * pw::kWindowStep;
  if (!options.export_first_row.empty()) {
    write_row(options.export_first_row, first_export_row, first_height);
  }
  if (!options.export_last_row.empty()) {
    write_row(options.export_last_row, last_export_row, last_height);
  }
  CUDA_CHECK(cudaEventRecord(stopped, stream));
  CUDA_CHECK(cudaEventSynchronize(stopped));
  float milliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&milliseconds, started, stopped));

  cudaEventDestroy(stopped);
  cudaEventDestroy(started);
  cudaStreamDestroy(stream);
  cudaFree(device_summary);
  cudaFree(device_row);
  cudaFree(device_record);
  const bool comparisons_pass =
      (!compared_first || first_comparison.failures == 0U) &&
      (!compared_last || last_comparison.failures == 0U);
  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-gamma-dd-gpu.v2\""
            << ",\"accepted\":" << (comparisons_pass ? "true" : "false")
            << ",\"records\":" << records
            << ",\"gamma_values\":" << records * pw::kBucketCount
            << ",\"invalid_disks\":0"
            << ",\"maximum_radius\":" << maximum_radius
            << ",\"digest_xor\":\"" << std::hex << std::setw(16)
            << std::setfill('0') << digest << std::dec << "\""
            << ",\"gpu_seconds\":" << milliseconds / 1000.0
            << ",\"gamma_values_per_second\":"
            << (records * pw::kBucketCount) / (milliseconds / 1000.0)
            << ",\"first_full_row_compared\":"
            << (compared_first ? "true" : "false")
            << ",\"first_containment_failures\":"
            << first_comparison.failures
            << ",\"first_maximum_required_to_outer_ratio\":"
            << static_cast<double>(first_comparison.maximum_radius_ratio)
            << ",\"last_full_row_compared\":"
            << (compared_last ? "true" : "false")
            << ",\"last_containment_failures\":"
            << last_comparison.failures
            << ",\"last_maximum_required_to_outer_ratio\":"
            << static_cast<double>(last_comparison.maximum_radius_ratio)
            << ",\"stream_sha256\":\""
            << sparkinterval::lowercase_hex(reader.stream_sha256()) << "\""
            << ",\"stream_sha256_pinned\":true"
            << ",\"bounded_authenticated_input\":true"
            << ",\"flint_to_mathlib_proved\":false"
            << ",\"pt21_atom_discharged\":false}\n";
  return comparisons_pass ? 0 : 2;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 2;
  }
}

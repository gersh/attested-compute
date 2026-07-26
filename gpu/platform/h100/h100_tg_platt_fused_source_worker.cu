// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Correctness-first, source-scale finite PT21 pipeline:
//
// authenticated FLINT Gamma coefficients -> CUDA Gamma disk row -> exact
// 768000-term/23-stage DD accumulator -> persistent DD transform -> resident
// 25741-sample required region.
//
// This deliberately stops before Gaussian-sinc interpolation, stationary
// refinement, zero isolation, and Turing closure.  It proves that the formerly
// separate source-scale components have a bounded device-to-device data path;
// it does not claim the analytic PT21 theorem.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_dd_accumulator.hpp"
#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_gamma_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace pgg = sparkinterval::tg::platt_gamma_gpu;
namespace pgs = sparkinterval::tg::platt_gamma_stream;
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

struct Options {
  std::string gamma_stream;
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  std::uint32_t maximum_chunk_records = 4096U;
  std::uint32_t reanchor_blocks = 256U;
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

unsigned char hex_byte(char high, char low) {
  auto nibble = [](char value) -> unsigned {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10U;
    throw std::runtime_error("expected stream SHA-256 is not hexadecimal");
  };
  return static_cast<unsigned char>((nibble(high) << 4U) | nibble(low));
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error("expected stream SHA-256 has the wrong length");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0; index < result.size(); ++index) {
    result[index] = hex_byte(text[2U * index], text[2U * index + 1U]);
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  if (argc < 4) {
    throw std::runtime_error(
        "usage: fused-source-worker GAMMA_STREAM FIRST_BLOCK BLOCK_COUNT "
        "[--max-chunk-records=N] [--reanchor-blocks=N] "
        "[--expected-stream-sha256=HEX]");
  }
  Options options;
  options.gamma_stream = argv[1];
  options.first_block = parse_unsigned(argv[2], "first block");
  options.block_count = parse_unsigned(argv[3], "block count");
  for (int index = 4; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto value_after = [&](std::string_view prefix)
        -> std::optional<std::string_view> {
      return argument.starts_with(prefix)
                 ? std::optional(argument.substr(prefix.size()))
                 : std::nullopt;
    };
    if (const auto value = value_after("--max-chunk-records=")) {
      const std::uint64_t parsed = parse_unsigned(*value, "chunk limit");
      if (parsed == 0U || parsed > (1U << 20U)) {
        throw std::runtime_error("chunk limit is outside 1..1048576");
      }
      options.maximum_chunk_records = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = value_after("--reanchor-blocks=")) {
      const std::uint64_t parsed = parse_unsigned(*value, "reanchor interval");
      if (parsed == 0U || parsed > (1U << 24U)) {
        throw std::runtime_error(
            "reanchor interval is outside 1..16777216");
      }
      options.reanchor_blocks = static_cast<std::uint32_t>(parsed);
    } else if (const auto value =
                   value_after("--expected-stream-sha256=")) {
      options.expected_stream_sha256 = parse_sha256(*value);
    } else {
      throw std::runtime_error("unknown option: " + std::string(argument));
    }
  }
  if (options.gamma_stream.empty() || options.block_count == 0U ||
      options.first_block >= pw::kFullBlockCount ||
      options.block_count > pw::kFullBlockCount - options.first_block) {
    throw std::runtime_error("fused source shard is outside PT21 geometry");
  }
  return options;
}

__device__ __forceinline__ std::uint64_t mix64(std::uint64_t value) {
  value ^= value >> 30U;
  value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27U;
  value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

__global__ void audit_required_samples(const pw::RealDisk106* samples,
                                       unsigned long long* invalid,
                                       unsigned long long* ambiguous,
                                       unsigned long long* digest) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < pdt::kSourceRequiredCount;
       index += blockDim.x * gridDim.x) {
    const pw::RealDisk106 value = samples[index];
    if (!isfinite(value.center.hi) || !isfinite(value.center.lo) ||
        !isfinite(value.radius) || value.radius < 0.0) {
      atomicAdd(invalid, 1ULL);
      continue;
    }
    const double center_lower =
        fmax(0.0, __dsub_rd(fabs(value.center.hi),
                            fabs(value.center.lo)));
    if (!(center_lower > value.radius) || value.center.hi == 0.0) {
      atomicAdd(ambiguous, 1ULL);
    }
    const std::uint64_t key = mix64(static_cast<std::uint64_t>(index));
    const std::uint64_t word =
        static_cast<std::uint64_t>(__double_as_longlong(value.center.hi)) ^
        (static_cast<std::uint64_t>(
             __double_as_longlong(value.center.lo)) << 1U) ^
        (static_cast<std::uint64_t>(__double_as_longlong(value.radius)) <<
         2U);
    atomicXor(digest, mix64(word ^ key));
  }
}

std::string json_escape(std::string_view input) {
  std::ostringstream result;
  for (const unsigned char value : input) {
    if (value == '\\' || value == '"') result << '\\';
    if (value >= 0x20U) result << static_cast<char>(value);
  }
  return result.str();
}

int run(const Options& options) {
  std::ifstream input(options.gamma_stream, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor stream");
  const auto wall_start = std::chrono::steady_clock::now();
  pgs::GammaTaylorStreamReader reader(
      input, options.first_block, options.block_count,
      options.expected_stream_sha256);
  if (reader.header().chunk_records > options.maximum_chunk_records) {
    throw std::runtime_error("Gamma chunk exceeds configured memory cap");
  }

  pda::Workspace* accumulator = pda::create_source_workspace(
      options.first_block, options.block_count, options.reanchor_blocks);
  pdt::Workspace* transform = pdt::create_source_workspace();
  pw::GammaTaylorStreamRecord* device_record = nullptr;
  pw::ComplexInterval* device_gamma_interval = nullptr;
  pw::ComplexDisk106* device_gamma_disk = nullptr;
  unsigned long long* device_invalid = nullptr;
  unsigned long long* device_ambiguous = nullptr;
  unsigned long long* device_digest = nullptr;
  cudaStream_t stream = nullptr;
  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  try {
    CUDA_CHECK(cudaMalloc(&device_record, sizeof(*device_record)));
    CUDA_CHECK(cudaMalloc(&device_gamma_interval,
                          pw::kBucketCount *
                              sizeof(*device_gamma_interval)));
    CUDA_CHECK(cudaMalloc(&device_gamma_disk,
                          pw::kBucketCount * sizeof(*device_gamma_disk)));
    CUDA_CHECK(cudaMalloc(&device_invalid, sizeof(*device_invalid)));
    CUDA_CHECK(cudaMalloc(&device_ambiguous, sizeof(*device_ambiguous)));
    CUDA_CHECK(cudaMalloc(&device_digest, sizeof(*device_digest)));
    CUDA_CHECK(cudaMemset(device_invalid, 0, sizeof(*device_invalid)));
    CUDA_CHECK(cudaMemset(device_ambiguous, 0, sizeof(*device_ambiguous)));
    CUDA_CHECK(cudaMemset(device_digest, 0, sizeof(*device_digest)));
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start, stream));

    std::uint64_t records = 0U;
    std::uint64_t chunks = 0U;
    pgs::AuthenticatedChunk chunk;
    while (reader.next(chunk)) {
      ++chunks;
      for (std::size_t offset = 0U; offset < chunk.records.size(); ++offset) {
        const std::uint64_t logical_block = chunk.first_block + offset;
        if (logical_block != options.first_block + records) {
          throw std::runtime_error("Gamma records are not gap-free");
        }
        CUDA_CHECK(cudaMemcpyAsync(
            device_record, &chunk.records[offset], sizeof(*device_record),
            cudaMemcpyHostToDevice, stream));
        const pgg::GammaRowBatchView interval_view{
            device_gamma_interval, 1U, pw::kBucketCount, logical_block};
        const pgg::GammaDiskRowBatchView disk_view{
            device_gamma_disk, 1U, pw::kBucketCount, logical_block};
        pgg::launch_synthesize_gamma_rows(device_record, interval_view,
                                          stream);
        pgg::launch_convert_gamma_rows_to_disks(interval_view, disk_view,
                                                stream);
        const pda::SourceWindowView skn =
            pda::run_next_source_window(accumulator, stream);
        if (skn.logical_block != logical_block) {
          throw std::runtime_error("Gamma and accumulator blocks diverged");
        }
        pdt::run_source_window(transform, device_gamma_disk,
                               skn.device_skn_rows, stream);
        audit_required_samples<<<128U, 256U, 0U, stream>>>(
            pdt::device_required_samples(transform), device_invalid,
            device_ambiguous, device_digest);
        CUDA_CHECK(cudaGetLastError());
        ++records;
      }
      // The authenticated chunk owns the pageable source records used by the
      // asynchronous H2D copies.  Drain this stream before reader.next reuses
      // the vector; there is still only one synchronization per (normally
      // 4096-window) authenticated chunk, never one per source window.
      CUDA_CHECK(cudaStreamSynchronize(stream));
    }
    if (!reader.complete() || records != options.block_count ||
        pda::windows_enqueued(accumulator) != options.block_count) {
      throw std::runtime_error("fused source worker consumed a prefix only");
    }
    CUDA_CHECK(cudaEventRecord(stop, stream));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float gpu_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&gpu_ms, start, stop));
    unsigned long long invalid = 0U;
    unsigned long long ambiguous = 0U;
    unsigned long long digest = 0U;
    CUDA_CHECK(cudaMemcpy(&invalid, device_invalid, sizeof(invalid),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(&ambiguous, device_ambiguous, sizeof(ambiguous),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(&digest, device_digest, sizeof(digest),
                          cudaMemcpyDeviceToHost));
    if (invalid != 0U) {
      throw std::runtime_error("fused source worker emitted invalid disks");
    }
    const double wall_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - wall_start).count();
    const double gpu_seconds = static_cast<double>(gpu_ms) / 1000.0;
    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.platt-fused-source-worker.v1\""
              << ",\"accepted\":true"
              << ",\"claim_scope\":\"authenticated_gamma_accumulator_"
                 "dd_transform_finite_pipeline_only\""
              << ",\"first_block\":" << options.first_block
              << ",\"block_count\":" << options.block_count
              << ",\"chunks\":" << chunks
              << ",\"required_samples_audited\":"
              << records * pdt::kSourceRequiredCount
              << ",\"invalid_required_disks\":0"
              << ",\"ambiguous_required_disks\":" << ambiguous
              << ",\"required_digest_xor\":\"" << std::hex
              << std::setw(16) << std::setfill('0') << digest << std::dec
              << "\""
              << ",\"gamma_stream_sha256\":\""
              << sparkinterval::lowercase_hex(reader.stream_sha256())
              << "\""
              << ",\"gpu_seconds\":" << gpu_seconds
              << ",\"gpu_blocks_per_second\":"
              << static_cast<double>(records) / gpu_seconds
              << ",\"wall_seconds_including_source_initialization\":"
              << wall_seconds
              << ",\"accumulator_workspace_device_bytes\":"
              << pda::workspace_device_bytes(accumulator)
              << ",\"transform_workspace_device_bytes\":"
              << pdt::workspace_device_bytes(transform)
              << ",\"all_chunks_authenticated_before_gpu_use\":true"
              << ",\"footer_global_digest_and_eof_checked\":true"
              << ",\"bounded_device_memory\":true"
              << ",\"device_to_device_pipeline\":true"
              << ",\"gaussian_sinc_interpolation_implemented\":false"
              << ",\"event_stream_emitted\":false"
              << ",\"analytic_turing_realization_proved\":false"
              << ",\"flint_to_mathlib_realization_proved\":false"
              << ",\"pt21_source_claim_discharged\":false"
              << ",\"trusted_run_receipt_emitted\":false}\n";

    CUDA_CHECK(cudaEventDestroy(start));
    start = nullptr;
    CUDA_CHECK(cudaEventDestroy(stop));
    stop = nullptr;
    CUDA_CHECK(cudaStreamDestroy(stream));
    stream = nullptr;
    CUDA_CHECK(cudaFree(device_record));
    device_record = nullptr;
    CUDA_CHECK(cudaFree(device_gamma_interval));
    device_gamma_interval = nullptr;
    CUDA_CHECK(cudaFree(device_gamma_disk));
    device_gamma_disk = nullptr;
    CUDA_CHECK(cudaFree(device_invalid));
    device_invalid = nullptr;
    CUDA_CHECK(cudaFree(device_ambiguous));
    device_ambiguous = nullptr;
    CUDA_CHECK(cudaFree(device_digest));
    device_digest = nullptr;
    pdt::destroy_workspace(transform);
    transform = nullptr;
    pda::destroy_workspace(accumulator);
    accumulator = nullptr;
    return 0;
  } catch (...) {
    if (start != nullptr) cudaEventDestroy(start);
    if (stop != nullptr) cudaEventDestroy(stop);
    if (stream != nullptr) cudaStreamDestroy(stream);
    if (device_record != nullptr) cudaFree(device_record);
    if (device_gamma_interval != nullptr) cudaFree(device_gamma_interval);
    if (device_gamma_disk != nullptr) cudaFree(device_gamma_disk);
    if (device_invalid != nullptr) cudaFree(device_invalid);
    if (device_ambiguous != nullptr) cudaFree(device_ambiguous);
    if (device_digest != nullptr) cudaFree(device_digest);
    try {
      pdt::destroy_workspace(transform);
    } catch (...) {
    }
    try {
      pda::destroy_workspace(accumulator);
    } catch (...) {
    }
    throw;
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "{\"schema\":\"sparkinterval.tg.platt-fused-source-worker.v1\""
              << ",\"accepted\":false,\"error\":\""
              << json_escape(error.what())
              << "\",\"pt21_source_claim_discharged\":false,"
                 "\"trusted_run_receipt_emitted\":false}\n";
    return 2;
  }
}

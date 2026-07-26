// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded-memory CUDA consumer for the authenticated all-window Platt--
// Trudgian Gamma Taylor stream.  A chunk is SHA-256 authenticated and all of
// its interval records are validated by GammaTaylorStreamReader before any
// byte from that chunk is copied to CUDA.  Each CUDA graph launch synthesizes
// a microbatch of complete 32768-point rows; no launch is made per window.
//
// This executable deliberately does not claim that FLINT/Arb realizes the
// Mathlib analytic functions and does not discharge the PT21 source atom.  It
// is a finite producer/consumer component intended to feed a future fused
// accumulator/FFT stage inside an attested campaign.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_gamma_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
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

constexpr std::string_view kSummaryDomain =
    "sparkinterval/pt21-gamma-gpu-row-audit-summary/v1";
constexpr std::uint32_t kDefaultMicrobatchRecords = 64U;
constexpr std::uint32_t kDefaultMaximumChunkRecords = 4096U;
constexpr std::uint32_t kMaximumMicrobatchRecords = 1024U;
constexpr std::array<std::uint32_t, 5> kProbeIndices = {
    0U, 8192U, 16384U, 24576U, 32767U};

struct Options {
  std::string stream_path;
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  std::uint32_t microbatch_records = kDefaultMicrobatchRecords;
  std::uint32_t maximum_chunk_records = kDefaultMaximumChunkRecords;
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
    throw std::runtime_error("expected stream SHA-256 is not hexadecimal");
  };
  return static_cast<unsigned char>((nibble(high) << 4U) | nibble(low));
}

sparkinterval::Sha256Digest parse_sha256(std::string_view text) {
  if (text.size() != 64U) {
    throw std::runtime_error(
        "expected stream SHA-256 must contain exactly 64 hex digits");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0; index < result.size(); ++index) {
    result[index] = parse_hex_byte(text[2U * index], text[2U * index + 1U]);
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  if (argc < 4) {
    throw std::runtime_error(
        "usage: h100-tg-platt-gamma-stream-consumer STREAM FIRST_BLOCK "
        "BLOCK_COUNT [--microbatch-records=N] "
        "[--max-chunk-records=N] [--expected-stream-sha256=HEX]");
  }
  Options options;
  options.stream_path = argv[1];
  options.first_block = parse_unsigned(argv[2], "first block");
  options.block_count = parse_unsigned(argv[3], "block count");
  for (int index = 4; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto value_after = [&](std::string_view prefix)
        -> std::optional<std::string_view> {
      if (!argument.starts_with(prefix)) return std::nullopt;
      return argument.substr(prefix.size());
    };
    if (const auto value = value_after("--microbatch-records=")) {
      const std::uint64_t parsed = parse_unsigned(*value, "microbatch size");
      if (parsed == 0U || parsed > kMaximumMicrobatchRecords) {
        throw std::runtime_error("microbatch size is outside 1..1024");
      }
      options.microbatch_records = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = value_after("--max-chunk-records=")) {
      const std::uint64_t parsed =
          parse_unsigned(*value, "maximum chunk size");
      if (parsed == 0U || parsed > (1U << 20U)) {
        throw std::runtime_error(
            "maximum chunk size is outside 1..1048576");
      }
      options.maximum_chunk_records = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = value_after("--expected-stream-sha256=")) {
      options.expected_stream_sha256 = parse_sha256(*value);
    } else if (argument == "--help") {
      std::cout
          << "usage: h100-tg-platt-gamma-stream-consumer STREAM FIRST_BLOCK "
             "BLOCK_COUNT [--microbatch-records=N] "
             "[--max-chunk-records=N] [--expected-stream-sha256=HEX]\n";
      std::exit(0);
    } else {
      throw std::runtime_error("unknown option: " + std::string(argument));
    }
  }
  if (options.stream_path.empty()) {
    throw std::runtime_error("Gamma Taylor stream path is empty");
  }
  if (options.block_count == 0U ||
      options.first_block >= pw::kFullBlockCount ||
      options.block_count > pw::kFullBlockCount - options.first_block) {
    throw std::runtime_error(
        "expected shard range is outside the exact source campaign");
  }
  return options;
}

std::string json_escape(std::string_view input) {
  std::ostringstream result;
  for (const unsigned char value : input) {
    switch (value) {
      case '\\': result << "\\\\"; break;
      case '"': result << "\\\""; break;
      case '\n': result << "\\n"; break;
      case '\r': result << "\\r"; break;
      case '\t': result << "\\t"; break;
      default:
        if (value < 0x20U) {
          result << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                 << static_cast<unsigned>(value) << std::dec;
        } else {
          result << static_cast<char>(value);
        }
    }
  }
  return result.str();
}

std::string double_hex(double value) {
  std::ostringstream result;
  result << std::hexfloat << value;
  return result.str();
}

template <typename Type>
class CudaDeviceBuffer {
 public:
  explicit CudaDeviceBuffer(std::size_t count) : count_(count) {
    if (count == 0U) throw std::runtime_error("zero-sized CUDA allocation");
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&pointer_),
                          count * sizeof(Type)));
  }
  ~CudaDeviceBuffer() {
    if (pointer_ != nullptr) cudaFree(pointer_);
  }
  CudaDeviceBuffer(const CudaDeviceBuffer&) = delete;
  CudaDeviceBuffer& operator=(const CudaDeviceBuffer&) = delete;
  Type* get() const { return pointer_; }
  std::size_t count() const { return count_; }

 private:
  Type* pointer_ = nullptr;
  std::size_t count_ = 0U;
};

template <typename Type>
class CudaPinnedBuffer {
 public:
  explicit CudaPinnedBuffer(std::size_t count) : count_(count) {
    if (count == 0U) throw std::runtime_error("zero-sized pinned allocation");
    CUDA_CHECK(cudaMallocHost(reinterpret_cast<void**>(&pointer_),
                             count * sizeof(Type)));
  }
  ~CudaPinnedBuffer() {
    if (pointer_ != nullptr) cudaFreeHost(pointer_);
  }
  CudaPinnedBuffer(const CudaPinnedBuffer&) = delete;
  CudaPinnedBuffer& operator=(const CudaPinnedBuffer&) = delete;
  Type* get() const { return pointer_; }

 private:
  Type* pointer_ = nullptr;
  std::size_t count_ = 0U;
};

class CudaStream {
 public:
  CudaStream() {
    CUDA_CHECK(cudaStreamCreateWithFlags(&value_, cudaStreamNonBlocking));
  }
  ~CudaStream() {
    if (value_ != nullptr) cudaStreamDestroy(value_);
  }
  operator cudaStream_t() const { return value_; }

 private:
  cudaStream_t value_ = nullptr;
};

class CudaEvent {
 public:
  CudaEvent() { CUDA_CHECK(cudaEventCreate(&value_)); }
  ~CudaEvent() {
    if (value_ != nullptr) cudaEventDestroy(value_);
  }
  operator cudaEvent_t() const { return value_; }

 private:
  cudaEvent_t value_ = nullptr;
};

class CudaGraphBatch {
 public:
  CudaGraphBatch(
      pw::GammaTaylorStreamRecord* host_records,
      pw::GammaTaylorStreamRecord* device_records,
      pw::ComplexInterval* device_rows,
      pw::ComplexDisk106* device_disk_rows,
      pgg::GammaRowSummary* device_summaries,
      pgg::GammaDiskRowSummary* device_disk_summaries,
      pgg::GammaRowSummary* host_summaries,
      pgg::GammaDiskRowSummary* host_disk_summaries,
      std::uint32_t record_count, cudaStream_t stream)
      : record_count_(record_count) {
    CUDA_CHECK(cudaStreamBeginCapture(stream, cudaStreamCaptureModeThreadLocal));
    CUDA_CHECK(cudaMemcpyAsync(
        device_records, host_records,
        static_cast<std::size_t>(record_count) *
            sizeof(pw::GammaTaylorStreamRecord),
        cudaMemcpyHostToDevice, stream));
    const pgg::GammaRowBatchView view{
        device_rows, record_count, pw::kBucketCount, 0U};
    const pgg::GammaDiskRowBatchView disk_view{
        device_disk_rows, record_count, pw::kBucketCount, 0U};
    pgg::launch_synthesize_gamma_rows(device_records, view, stream);
    pgg::launch_summarize_gamma_rows(view, device_summaries, stream);
    pgg::launch_convert_gamma_rows_to_disks(view, disk_view, stream);
    pgg::launch_summarize_gamma_disks(disk_view, device_disk_summaries,
                                      stream);
    CUDA_CHECK(cudaMemcpyAsync(
        host_summaries, device_summaries,
        static_cast<std::size_t>(record_count) * sizeof(pgg::GammaRowSummary),
        cudaMemcpyDeviceToHost, stream));
    CUDA_CHECK(cudaMemcpyAsync(
        host_disk_summaries, device_disk_summaries,
        static_cast<std::size_t>(record_count) *
            sizeof(pgg::GammaDiskRowSummary),
        cudaMemcpyDeviceToHost, stream));
    CUDA_CHECK(cudaStreamEndCapture(stream, &graph_));
    CUDA_CHECK(cudaGraphInstantiate(&executable_, graph_, nullptr, nullptr, 0));
  }
  ~CudaGraphBatch() {
    if (executable_ != nullptr) cudaGraphExecDestroy(executable_);
    if (graph_ != nullptr) cudaGraphDestroy(graph_);
  }
  void launch(cudaStream_t stream) const {
    CUDA_CHECK(cudaGraphLaunch(executable_, stream));
  }
  std::uint32_t record_count() const { return record_count_; }

 private:
  cudaGraph_t graph_ = nullptr;
  cudaGraphExec_t executable_ = nullptr;
  std::uint32_t record_count_ = 0U;
};

struct RunResult {
  std::string device_name;
  std::uint64_t records = 0U;
  std::uint64_t chunks = 0U;
  std::uint64_t microbatches = 0U;
  std::uint64_t graph_launches = 0U;
  std::uint64_t tail_launches = 0U;
  std::uint64_t final_tail_records = 0U;
  std::uint64_t maximum_chunk_records = 0U;
  std::uint64_t invalid_intervals = 0U;
  std::uint64_t invalid_disks = 0U;
  std::uint64_t device_output_bytes = 0U;
  std::uint64_t device_disk_output_bytes = 0U;
  double maximum_real_width = 0.0;
  double maximum_imaginary_width = 0.0;
  double maximum_disk_radius = 0.0;
  double gpu_pipeline_seconds = 0.0;
  double wall_seconds = 0.0;
  sparkinterval::Sha256Digest stream_sha256{};
  sparkinterval::Sha256Digest row_summary_sha256{};
  std::array<pw::ComplexInterval, kProbeIndices.size()> probes{};
  std::array<pw::ComplexDisk106, kProbeIndices.size()> disk_probes{};
  bool probes_captured = false;
};

RunResult run_gpu(const Options& options) {
  static_assert(std::endian::native == std::endian::little);
  std::ifstream input(options.stream_path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor stream");
  const auto wall_start = std::chrono::steady_clock::now();
  pgs::GammaTaylorStreamReader reader(
      input, options.first_block, options.block_count,
      options.expected_stream_sha256);
  if (reader.header().chunk_records > options.maximum_chunk_records) {
    throw std::runtime_error(
        "Gamma Taylor chunk_records exceeds the configured host-memory cap");
  }

  const std::uint32_t batch_capacity = static_cast<std::uint32_t>(
      std::min<std::uint64_t>(options.microbatch_records,
                              options.block_count));
  const std::uint64_t output_values =
      static_cast<std::uint64_t>(batch_capacity) * pw::kBucketCount;
  if (output_values >
      std::numeric_limits<std::size_t>::max() / sizeof(pw::ComplexInterval)) {
    throw std::runtime_error("CUDA output allocation size overflows size_t");
  }
  const std::uint64_t output_bytes =
      output_values * sizeof(pw::ComplexInterval);
  const std::uint64_t disk_output_bytes =
      output_values * sizeof(pw::ComplexDisk106);
  std::size_t free_device_bytes = 0U;
  std::size_t total_device_bytes = 0U;
  CUDA_CHECK(cudaMemGetInfo(&free_device_bytes, &total_device_bytes));
  const std::uint64_t required_device_bytes =
      output_bytes + disk_output_bytes +
      static_cast<std::uint64_t>(batch_capacity) *
          (sizeof(pw::GammaTaylorStreamRecord) +
           sizeof(pgg::GammaRowSummary) +
           sizeof(pgg::GammaDiskRowSummary));
  if (required_device_bytes >
      static_cast<std::uint64_t>(free_device_bytes) * 3U / 4U) {
    throw std::runtime_error(
        "configured microbatch exceeds 75 percent of free CUDA memory");
  }

  int device = 0;
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties.major != 9 || properties.minor != 0 ||
      std::strstr(properties.name, "H100") == nullptr) {
    throw std::runtime_error(
        "strict production target requires an NVIDIA H100 sm_90 device");
  }
#endif

  CudaPinnedBuffer<pw::GammaTaylorStreamRecord> host_records(batch_capacity);
  CudaPinnedBuffer<pgg::GammaRowSummary> host_summaries(batch_capacity);
  CudaPinnedBuffer<pgg::GammaDiskRowSummary> host_disk_summaries(
      batch_capacity);
  CudaDeviceBuffer<pw::GammaTaylorStreamRecord> device_records(batch_capacity);
  CudaDeviceBuffer<pw::ComplexInterval> device_rows(
      static_cast<std::size_t>(output_values));
  CudaDeviceBuffer<pw::ComplexDisk106> device_disk_rows(
      static_cast<std::size_t>(output_values));
  CudaDeviceBuffer<pgg::GammaRowSummary> device_summaries(batch_capacity);
  CudaDeviceBuffer<pgg::GammaDiskRowSummary> device_disk_summaries(
      batch_capacity);
  CudaStream stream;
  CudaEvent start;
  CudaEvent stop;
  CudaGraphBatch graph(host_records.get(), device_records.get(),
                       device_rows.get(), device_disk_rows.get(),
                       device_summaries.get(), device_disk_summaries.get(),
                       host_summaries.get(), host_disk_summaries.get(),
                       batch_capacity, stream);

  sparkinterval::detail::Sha256 summary_hasher;
  summary_hasher.update(kSummaryDomain.data(), kSummaryDomain.size());
  summary_hasher.update(&options.first_block, sizeof(options.first_block));
  summary_hasher.update(&options.block_count, sizeof(options.block_count));

  RunResult result;
  result.device_name = properties.name;
  result.device_output_bytes = output_bytes;
  result.device_disk_output_bytes = disk_output_bytes;

  auto process_microbatch = [&](const pw::GammaTaylorStreamRecord* records,
                                std::uint32_t count,
                                std::uint64_t first_block) {
    std::memcpy(host_records.get(), records,
                static_cast<std::size_t>(count) *
                    sizeof(pw::GammaTaylorStreamRecord));
    CUDA_CHECK(cudaEventRecord(start, stream));
    if (count == graph.record_count()) {
      graph.launch(stream);
      ++result.graph_launches;
    } else {
      CUDA_CHECK(cudaMemcpyAsync(
          device_records.get(), host_records.get(),
          static_cast<std::size_t>(count) *
              sizeof(pw::GammaTaylorStreamRecord),
          cudaMemcpyHostToDevice, stream));
      const pgg::GammaRowBatchView view{
          device_rows.get(), count, pw::kBucketCount, 0U};
      const pgg::GammaDiskRowBatchView disk_view{
          device_disk_rows.get(), count, pw::kBucketCount, first_block};
      pgg::launch_synthesize_gamma_rows(device_records.get(), view, stream);
      pgg::launch_summarize_gamma_rows(view, device_summaries.get(), stream);
      pgg::launch_convert_gamma_rows_to_disks(view, disk_view, stream);
      pgg::launch_summarize_gamma_disks(
          disk_view, device_disk_summaries.get(), stream);
      CUDA_CHECK(cudaMemcpyAsync(
          host_summaries.get(), device_summaries.get(),
          static_cast<std::size_t>(count) * sizeof(pgg::GammaRowSummary),
          cudaMemcpyDeviceToHost, stream));
      CUDA_CHECK(cudaMemcpyAsync(
          host_disk_summaries.get(), device_disk_summaries.get(),
          static_cast<std::size_t>(count) *
              sizeof(pgg::GammaDiskRowSummary),
          cudaMemcpyDeviceToHost, stream));
      ++result.tail_launches;
    }
    CUDA_CHECK(cudaEventRecord(stop, stream));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
    result.gpu_pipeline_seconds +=
        static_cast<double>(elapsed_ms) / 1000.0;

    if (!result.probes_captured) {
      for (std::size_t probe = 0; probe < kProbeIndices.size(); ++probe) {
        CUDA_CHECK(cudaMemcpy(
            &result.probes[probe], device_rows.get() + kProbeIndices[probe],
            sizeof(pw::ComplexInterval), cudaMemcpyDeviceToHost));
        CUDA_CHECK(cudaMemcpy(
            &result.disk_probes[probe],
            device_disk_rows.get() + kProbeIndices[probe],
            sizeof(pw::ComplexDisk106), cudaMemcpyDeviceToHost));
      }
      result.probes_captured = true;
    }
    for (std::uint32_t index = 0U; index < count; ++index) {
      pgg::GammaRowSummary summary = host_summaries.get()[index];
      summary.logical_block = first_block + index;
      result.invalid_intervals += summary.invalid_intervals;
      result.maximum_real_width =
          std::max(result.maximum_real_width, summary.maximum_real_width);
      result.maximum_imaginary_width = std::max(
          result.maximum_imaginary_width,
          summary.maximum_imaginary_width);
      summary_hasher.update(&summary, sizeof(summary));
      pgg::GammaDiskRowSummary disk_summary =
          host_disk_summaries.get()[index];
      disk_summary.logical_block = first_block + index;
      result.invalid_disks += disk_summary.invalid_disks;
      result.maximum_disk_radius =
          std::max(result.maximum_disk_radius, disk_summary.maximum_radius);
      summary_hasher.update(&disk_summary, sizeof(disk_summary));
    }
    if (result.invalid_intervals != 0U || result.invalid_disks != 0U) {
      throw std::runtime_error(
          "CUDA Gamma synthesis produced an invalid interval or disk");
    }
    result.records += count;
    ++result.microbatches;
  };

  // Coalesce across authenticated chunk boundaries.  Thus even an input
  // deliberately framed as one record per chunk cannot force a host launch
  // per window; there is one graph launch per full microbatch and at most one
  // variable-sized tail launch for the entire shard.
  std::vector<pw::GammaTaylorStreamRecord> pending;
  pending.reserve(batch_capacity);
  std::uint64_t pending_first_block = options.first_block;
  pgs::AuthenticatedChunk chunk;
  while (reader.next(chunk)) {
    ++result.chunks;
    result.maximum_chunk_records =
        std::max<std::uint64_t>(result.maximum_chunk_records,
                                chunk.records.size());
    std::size_t offset = 0U;
    while (offset < chunk.records.size()) {
      if (pending.empty()) pending_first_block = chunk.first_block + offset;
      const std::size_t copied = std::min<std::size_t>(
          batch_capacity - pending.size(), chunk.records.size() - offset);
      pending.insert(pending.end(), chunk.records.begin() + offset,
                     chunk.records.begin() + offset + copied);
      offset += copied;
      if (pending.size() == batch_capacity) {
        process_microbatch(pending.data(), batch_capacity,
                           pending_first_block);
        pending.clear();
      }
    }
  }
  // next() has now authenticated the footer, the complete ordered stream
  // digest, and EOF.  No success JSON is emitted before this point.
  if (!pending.empty()) {
    result.final_tail_records = pending.size();
    process_microbatch(pending.data(),
                       static_cast<std::uint32_t>(pending.size()),
                       pending_first_block);
  }
  if (!reader.complete() || reader.consumed_records() != options.block_count ||
      result.records != options.block_count) {
    throw std::runtime_error("Gamma Taylor stream was only partially consumed");
  }
  result.stream_sha256 = reader.stream_sha256();
  result.row_summary_sha256 = summary_hasher.finish();
  result.wall_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - wall_start).count();
  return result;
}

void print_probe_json(const RunResult& result) {
  std::cout << "[";
  for (std::size_t index = 0; index < kProbeIndices.size(); ++index) {
    if (index != 0U) std::cout << ",";
    const pw::ComplexInterval value = result.probes[index];
    std::cout << "{\"index\":" << kProbeIndices[index]
              << ",\"re_lo_hex\":\"" << double_hex(value.re.lo)
              << "\",\"re_hi_hex\":\"" << double_hex(value.re.hi)
              << "\",\"im_lo_hex\":\"" << double_hex(value.im.lo)
              << "\",\"im_hi_hex\":\"" << double_hex(value.im.hi)
              << "\"}";
  }
  std::cout << "]";
}

void print_disk_probe_json(const RunResult& result) {
  std::cout << "[";
  for (std::size_t index = 0; index < kProbeIndices.size(); ++index) {
    if (index != 0U) std::cout << ",";
    const pw::ComplexDisk106 value = result.disk_probes[index];
    std::cout << "{\"index\":" << kProbeIndices[index]
              << ",\"re_hi_hex\":\"" << double_hex(value.real.hi)
              << "\",\"re_lo_hex\":\"" << double_hex(value.real.lo)
              << "\",\"im_hi_hex\":\""
              << double_hex(value.imaginary.hi)
              << "\",\"im_lo_hex\":\""
              << double_hex(value.imaginary.lo)
              << "\",\"radius_hex\":\"" << double_hex(value.radius)
              << "\"}";
  }
  std::cout << "]";
}

int run(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const RunResult result = run_gpu(options);
  const double gpu_rate =
      static_cast<double>(result.records) / result.gpu_pipeline_seconds;
  const double wall_rate = static_cast<double>(result.records) /
                           result.wall_seconds;
  const double projected_gpu_hours =
      static_cast<double>(pw::kFullBlockCount) / gpu_rate / 3600.0;
  const double projected_wall_hours =
      static_cast<double>(pw::kFullBlockCount) / wall_rate / 3600.0;
  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-gamma-gpu-stream.v1\""
            << ",\"accepted\":true"
            << ",\"claim_scope\":\"authenticated_gamma_stream_gpu_"
               "synthesis_only_not_pt21_or_flint_to_mathlib_realization\""
            << ",\"device\":\"" << json_escape(result.device_name) << "\""
            << ",\"first_block\":" << options.first_block
            << ",\"block_count\":" << options.block_count
            << ",\"full_source_block_count\":" << pw::kFullBlockCount
            << ",\"records_consumed\":" << result.records
            << ",\"interval_values_synthesized\":"
            << result.records * static_cast<std::uint64_t>(pw::kBucketCount)
            << ",\"chunk_count\":" << result.chunks
            << ",\"maximum_authenticated_chunk_records\":"
            << result.maximum_chunk_records
            << ",\"configured_maximum_chunk_records\":"
            << options.maximum_chunk_records
            << ",\"microbatch_records\":" << options.microbatch_records
            << ",\"microbatch_count\":" << result.microbatches
            << ",\"cuda_graph_launches\":" << result.graph_launches
            << ",\"tail_batched_launches\":" << result.tail_launches
            << ",\"final_tail_records\":" << result.final_tail_records
            << ",\"per_window_host_launches\":0"
            << ",\"maximum_device_row_buffer_bytes\":"
            << result.device_output_bytes
            << ",\"maximum_device_disk_row_buffer_bytes\":"
            << result.device_disk_output_bytes
            << ",\"invalid_intervals\":" << result.invalid_intervals
            << ",\"invalid_disks\":" << result.invalid_disks
            << ",\"maximum_real_interval_width\":"
            << result.maximum_real_width
            << ",\"maximum_imaginary_interval_width\":"
            << result.maximum_imaginary_width
            << ",\"maximum_disk_radius\":"
            << result.maximum_disk_radius
            << ",\"gpu_pipeline_seconds\":"
            << result.gpu_pipeline_seconds
            << ",\"wall_seconds\":" << result.wall_seconds
            << ",\"measured_gpu_pipeline_records_per_second\":"
            << gpu_rate
            << ",\"measured_end_to_end_records_per_second\":"
            << wall_rate
            << ",\"projected_full_source_gpu_pipeline_hours\":"
            << projected_gpu_hours
            << ",\"projected_full_source_end_to_end_hours\":"
            << projected_wall_hours
            << ",\"projection_scope\":\"single_device_gamma_synthesis_"
               "component_only_from_this_sample\""
            << ",\"stream_sha256\":\""
            << sparkinterval::lowercase_hex(result.stream_sha256) << "\""
            << ",\"expected_stream_sha256_supplied\":"
            << (options.expected_stream_sha256 ? "true" : "false")
            << ",\"row_audit_summary_sha256\":\""
            << sparkinterval::lowercase_hex(result.row_summary_sha256)
            << "\""
            << ",\"row_audit_summary_is_full_row_cryptographic_digest\":false"
            << ",\"first_record_probes\":";
  print_probe_json(result);
  std::cout << ",\"first_record_disk_probes\":";
  print_disk_probe_json(result);
  std::cout
      << ",\"exact_expected_shard_range_checked\":true"
      << ",\"all_chunks_authenticated_before_gpu_use\":true"
      << ",\"footer_and_global_digest_checked_before_acceptance\":true"
      << ",\"bounded_host_and_device_memory\":true"
      << ",\"device_rows_available_for_future_fused_consumer\":true"
      << ",\"device_disk_rows_match_transform_input_layout\":true"
      << ",\"flint_to_mathlib_realization_proved\":false"
      << ",\"pt21_source_claim_discharged\":false"
      << ",\"trusted_run_receipt_emitted\":false}\n";
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(argc, argv);
  } catch (const std::exception& error) {
    std::cerr
        << "{\"schema\":\"sparkinterval.tg.platt-gamma-gpu-stream.v1\""
        << ",\"accepted\":false"
        << ",\"error\":\"" << json_escape(error.what()) << "\""
        << ",\"flint_to_mathlib_realization_proved\":false"
        << ",\"pt21_source_claim_discharged\":false"
        << ",\"trusted_run_receipt_emitted\":false}\n";
    return 2;
  }
}

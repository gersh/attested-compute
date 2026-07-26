// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-scale V2 finite pipeline:
// authenticated FLINT DD Gamma coefficients -> direct CUDA ComplexDisk106
// row -> exact 768000-term/23-stage DD accumulator -> source DD transform ->
// resident 25741-cell required-region audit -> exact three-stream event scan
// -> compact authenticated PT21EVT1 records.
//
// PT21EVT1 is explicitly nonterminal: stationary candidates remain unresolved
// until the source Gaussian-sinc adaptive resolver runs.  This executable
// emits no PT21BLK1, performs no Turing closure, does not identify FLINT with
// Mathlib, and does not discharge PT21.

#include "sparkinterval/tg_platt_dd_accumulator.hpp"
#include "sparkinterval/tg_platt_dd_transform.hpp"
#include "sparkinterval/tg_platt_event_record.hpp"
#include "sparkinterval/tg_platt_event_scan.hpp"
#include "sparkinterval/tg_platt_gamma_dd_gpu.cuh"
#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
#include "sparkinterval/tg_platt_inline_stationary_stream.hpp"
#include "sparkinterval/tg_platt_stationary_junction.hpp"
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
#include "sparkinterval/tg_platt_pt21_block_input_stream.hpp"
#include "sparkinterval/tg_platt_pt21_required_sign_packet.hpp"
#include "sparkinterval/tg_platt_pt21_turing_inputs.hpp"
#endif

#include <cuda_runtime.h>

#include <array>
#include <bit>
#include <charconv>
#include <chrono>
#include <csignal>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <cerrno>
#include <deque>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pdt = sparkinterval::tg::platt_dd_transform;
namespace per = sparkinterval::tg::platt_event_record;
namespace pes = sparkinterval::tg::platt_event_scan;
namespace pgd = sparkinterval::tg::platt_gamma_dd_gpu;
namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;
namespace pw = sparkinterval::tg::platt_windowed;
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
namespace pis = sparkinterval::tg::platt_inline_stationary_stream;
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace psr = sparkinterval::tg::platt_stationary_resolver;
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
namespace pbi = sparkinterval::tg::platt_pt21_block_input_stream;
namespace prs = sparkinterval::tg::platt_pt21_required_sign_packet;
namespace pti = sparkinterval::tg::platt_pt21_turing_inputs;
#endif

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

struct Options {
  std::string stream_path;
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  std::uint32_t maximum_chunk_records = 4096U;
  std::uint32_t reanchor_blocks = 256U;
  std::uint32_t event_ring_blocks = 8U;
  std::uint32_t event_replay_threads = 8U;
  std::optional<sparkinterval::Sha256Digest> expected_stream_sha256;
  std::optional<std::string> event_stream_output;
  std::optional<sparkinterval::Sha256Digest> producer_sha256;
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
  std::optional<std::string> inline_stationary_output;
  std::optional<sparkinterval::Sha256Digest> resolver_sha256;
  std::optional<sparkinterval::Sha256Digest> flint_sha256;
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
  std::optional<std::string> block_input_output;
#endif
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
        "usage: fused-source-worker-v2 STREAM FIRST_BLOCK BLOCK_COUNT "
        "[--max-chunk-records=N] [--reanchor-blocks=N] "
        "[--event-ring-blocks=N] [--event-replay-threads=N] "
        "--expected-stream-sha256=HEX "
        "[--event-stream-output=PATH --producer-sha256=HEX]"
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
        " --inline-stationary-output=PATH --resolver-sha256=HEX "
        "--flint-sha256=HEX"
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
        " --block-input-output=PATH"
#endif
    );
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
    } else if (const auto value = after("--reanchor-blocks=")) {
      const auto parsed = parse_unsigned(*value, "reanchor blocks");
      if (parsed == 0U || parsed > (1U << 24U)) {
        throw std::runtime_error("reanchor blocks is outside range");
      }
      result.reanchor_blocks = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = after("--event-ring-blocks=")) {
      const auto parsed = parse_unsigned(*value, "event ring blocks");
      if (parsed == 0U || parsed > 1024U) {
        throw std::runtime_error("event ring blocks is outside range");
      }
      result.event_ring_blocks = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = after("--event-replay-threads=")) {
      const auto parsed = parse_unsigned(*value, "event replay threads");
      if (parsed == 0U || parsed > 256U) {
        throw std::runtime_error("event replay threads is outside range");
      }
      result.event_replay_threads = static_cast<std::uint32_t>(parsed);
    } else if (const auto value = after("--expected-stream-sha256=")) {
      result.expected_stream_sha256 = parse_sha256(*value);
    } else if (const auto value = after("--event-stream-output=")) {
      if (value->empty() || result.event_stream_output.has_value()) {
        throw std::runtime_error(
            "event stream output is empty or duplicated");
      }
      result.event_stream_output = std::string(*value);
    } else if (const auto value = after("--producer-sha256=")) {
      if (result.producer_sha256.has_value()) {
        throw std::runtime_error("producer SHA-256 is duplicated");
      }
      result.producer_sha256 = parse_sha256(*value);
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
    } else if (const auto value = after("--inline-stationary-output=")) {
      if (value->empty() || result.inline_stationary_output.has_value()) {
        throw std::runtime_error(
            "inline stationary output is empty or duplicated");
      }
      result.inline_stationary_output = std::string(*value);
    } else if (const auto value = after("--resolver-sha256=")) {
      if (result.resolver_sha256.has_value()) {
        throw std::runtime_error("resolver SHA-256 is duplicated");
      }
      result.resolver_sha256 = parse_sha256(*value);
    } else if (const auto value = after("--flint-sha256=")) {
      if (result.flint_sha256.has_value()) {
        throw std::runtime_error("FLINT SHA-256 is duplicated");
      }
      result.flint_sha256 = parse_sha256(*value);
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
    } else if (const auto value = after("--block-input-output=")) {
      if (value->empty() || result.block_input_output.has_value()) {
        throw std::runtime_error(
            "block input output is empty or duplicated");
      }
      result.block_input_output = std::string(*value);
#endif
    } else {
      throw std::runtime_error("unknown option: " + std::string(argument));
    }
  }
  if (result.stream_path.empty() || result.block_count == 0U ||
      result.first_block >= pw::kFullBlockCount ||
      result.block_count > pw::kFullBlockCount - result.first_block) {
    throw std::runtime_error("V2 fused range is outside PT21 geometry");
  }
  if (!result.expected_stream_sha256) {
    throw std::runtime_error(
        "V2 fused worker requires --expected-stream-sha256 from a trusted "
        "manifest");
  }
  const bool needs_producer =
      result.event_stream_output.has_value()
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
      || result.inline_stationary_output.has_value()
#endif
      ;
  if (needs_producer != result.producer_sha256.has_value()) {
    throw std::runtime_error(
        "authenticated output requires --producer-sha256 exactly when an "
        "output path is selected");
  }
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
  if (!result.inline_stationary_output.has_value() ||
      !result.resolver_sha256.has_value() ||
      !result.flint_sha256.has_value()) {
    throw std::runtime_error(
        "inline stationary qualification requires its output, resolver, "
        "and FLINT identity pins");
  }
  if (per::digest_is_zero(*result.producer_sha256) ||
      per::digest_is_zero(*result.resolver_sha256) ||
      per::digest_is_zero(*result.flint_sha256)) {
    throw std::runtime_error(
        "inline stationary qualification identities must be nonzero");
  }
  if (result.event_stream_output.has_value() &&
      *result.event_stream_output == *result.inline_stationary_output) {
    throw std::runtime_error(
        "event and inline stationary outputs must be different paths");
  }
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
  if (!result.block_input_output.has_value()) {
    throw std::runtime_error(
        "block stage qualification requires --block-input-output");
  }
  if (*result.block_input_output == *result.inline_stationary_output ||
      (result.event_stream_output.has_value() &&
       *result.event_stream_output == *result.block_input_output)) {
    throw std::runtime_error(
        "block input output must differ from every other output path");
  }
#endif
  return result;
}

__device__ __forceinline__ std::uint64_t mix64(std::uint64_t value) {
  value ^= value >> 30U;
  value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27U;
  value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

__global__ void audit_required(const pw::RealDisk106* samples,
                               unsigned long long* invalid,
                               unsigned long long* ambiguous,
                               unsigned long long* digest,
                               unsigned long long* maximum_radius_bits) {
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
        fmax(0.0, __dsub_rd(fabs(value.center.hi), fabs(value.center.lo)));
    if (!(center_lower > value.radius) || value.center.hi == 0.0) {
      atomicAdd(ambiguous, 1ULL);
    }
    atomicMax(maximum_radius_bits,
              static_cast<unsigned long long>(__double_as_longlong(
                  value.radius)));
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

class EventStreamOutput {
 public:
  EventStreamOutput(const std::string& output_path,
                    const per::HeaderValues& values)
      : output_path_(output_path), header_(per::encode_header(values)),
        values_(values) {
    if (output_path_.empty() || output_path_ == "-") {
      throw std::runtime_error(
          "event stream output must be a named regular file or FIFO");
    }
    struct stat metadata {};
    if (::lstat(output_path_.c_str(), &metadata) == 0) {
      if (!S_ISFIFO(metadata.st_mode)) {
        throw std::runtime_error(
            "event stream output already exists and is not a FIFO");
      }
      descriptor_ =
          ::open(output_path_.c_str(), O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
      if (descriptor_ < 0) {
        throw std::runtime_error(
            "cannot open event output FIFO without following links: " +
            std::string(std::strerror(errno)));
      }
      struct stat opened {};
      if (::fstat(descriptor_, &opened) != 0 || !S_ISFIFO(opened.st_mode)) {
        close_noexcept();
        throw std::runtime_error(
            "event stream output changed before FIFO open");
      }
      fifo_ = true;
    } else {
      if (errno != ENOENT) {
        throw std::runtime_error(
            "cannot inspect event stream output: " +
            std::string(std::strerror(errno)));
      }
      temporary_path_ =
          output_path_ + ".partial." + std::to_string(::getpid());
      descriptor_ =
          ::open(temporary_path_.c_str(),
                 O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                 S_IRUSR | S_IWUSR);
      if (descriptor_ < 0) {
        throw std::runtime_error(
            "cannot create exclusive event stream temporary file: " +
            std::string(std::strerror(errno)));
      }
    }
    write_raw(header_.data(), header_.size());
    whole_stream_hasher_.update(header_.data(), header_.size());
  }

  EventStreamOutput(const EventStreamOutput&) = delete;
  EventStreamOutput& operator=(const EventStreamOutput&) = delete;

  ~EventStreamOutput() {
    close_noexcept();
    if (!published_ && !temporary_path_.empty()) {
      ::unlink(temporary_path_.c_str());
    }
  }

  void write(const per::RawRecord& record,
             const per::BlockValues& values) {
    if (finished_ || records_written_ >= values_.block_count ||
        values.block != values_.first_block + records_written_) {
      throw std::runtime_error(
          "event record output order or lifecycle differs");
    }
    write_raw(record.data(), record.size());
    record_stream_hasher_.update(record.data(), record.size());
    whole_stream_hasher_.update(record.data(), record.size());
    for (std::size_t stream = 0U; stream < 3U; ++stream) {
      checked_add(&total_direct_events_,
                  values.direct_event_count[stream], "direct event");
      checked_add(&total_stationary_candidates_,
                  values.stationary_candidate_count[stream],
                  "stationary candidate");
    }
    ++records_written_;
  }

  void finish() {
    if (finished_ || records_written_ != values_.block_count) {
      throw std::runtime_error(
          "event stream cannot finalize an incomplete record range");
    }
    const per::FooterValues footer_values{
        .first_block = values_.first_block,
        .block_count = values_.block_count,
        .total_direct_events = total_direct_events_,
        .total_stationary_candidates = total_stationary_candidates_,
        .record_stream_sha256 = record_stream_hasher_.finish(),
        .header_sha256 =
            per::digest_at(header_.data() + per::kHeaderDigestOffset),
        .gamma_stream_sha256 = values_.gamma_stream_sha256,
    };
    const per::RawFooter footer = per::encode_footer(footer_values);
    write_raw(footer.data(), footer.size());
    whole_stream_hasher_.update(footer.data(), footer.size());
    stream_sha256_ = whole_stream_hasher_.finish();
    footer_sha256_ =
        per::digest_at(footer.data() + per::kFooterDigestOffset);

    if (!fifo_ && ::fsync(descriptor_) != 0) {
      throw std::runtime_error("cannot fsync event stream output");
    }
    if (::close(descriptor_) != 0) {
      descriptor_ = -1;
      throw std::runtime_error("cannot close event stream output");
    }
    descriptor_ = -1;
    if (!fifo_) {
      // link(2) gives create-only publication even when another process races
      // to create the final path.
      if (::link(temporary_path_.c_str(), output_path_.c_str()) != 0) {
        throw std::runtime_error(
            "cannot publish event stream without replacement: " +
            std::string(std::strerror(errno)));
      }
      published_ = true;
      if (::unlink(temporary_path_.c_str()) != 0) {
        throw std::runtime_error(
            "cannot remove published event stream temporary link");
      }
      temporary_path_.clear();
    } else {
      published_ = true;
    }
    finished_ = true;
  }

  const sparkinterval::Sha256Digest& stream_sha256() const {
    if (!finished_) {
      throw std::runtime_error("event stream digest requested before finish");
    }
    return stream_sha256_;
  }
  const sparkinterval::Sha256Digest& footer_sha256() const {
    if (!finished_) {
      throw std::runtime_error("event footer digest requested before finish");
    }
    return footer_sha256_;
  }
  bool is_fifo() const { return fifo_; }

 private:
  static void checked_add(std::uint64_t* accumulator, std::uint32_t value,
                          const char* label) {
    if (value >
        std::numeric_limits<std::uint64_t>::max() - *accumulator) {
      throw std::runtime_error(std::string(label) + " total overflows");
    }
    *accumulator += value;
  }

  void write_raw(const unsigned char* data, std::size_t size) {
    std::size_t offset = 0U;
    while (offset < size) {
      const ssize_t wrote =
          ::write(descriptor_, data + offset, size - offset);
      if (wrote < 0 && errno == EINTR) continue;
      if (wrote <= 0) {
        throw std::runtime_error(
            "cannot write event stream: " +
            std::string(std::strerror(errno)));
      }
      offset += static_cast<std::size_t>(wrote);
    }
  }

  void close_noexcept() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  std::string output_path_;
  std::string temporary_path_;
  int descriptor_ = -1;
  bool fifo_ = false;
  bool published_ = false;
  bool finished_ = false;
  per::RawHeader header_{};
  per::HeaderValues values_{};
  sparkinterval::detail::Sha256 record_stream_hasher_;
  sparkinterval::detail::Sha256 whole_stream_hasher_;
  sparkinterval::Sha256Digest stream_sha256_{};
  sparkinterval::Sha256Digest footer_sha256_{};
  std::uint64_t records_written_ = 0U;
  std::uint64_t total_direct_events_ = 0U;
  std::uint64_t total_stationary_candidates_ = 0U;
};

#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
class InlineStationaryStreamOutput {
 public:
  InlineStationaryStreamOutput(const std::string& output_path,
                               const pis::HeaderValues& values)
      : output_path_(output_path), header_(pis::encode_header(values)),
        values_(values) {
    if (output_path_.empty() || output_path_ == "-") {
      throw std::runtime_error(
          "inline stationary output must be a named regular file or FIFO");
    }
    struct stat metadata {};
    if (::lstat(output_path_.c_str(), &metadata) == 0) {
      if (!S_ISFIFO(metadata.st_mode)) {
        throw std::runtime_error(
            "inline stationary output already exists and is not a FIFO");
      }
      descriptor_ =
          ::open(output_path_.c_str(), O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
      if (descriptor_ < 0) {
        throw std::runtime_error(
            "cannot open inline stationary FIFO without following links: " +
            std::string(std::strerror(errno)));
      }
      struct stat opened {};
      if (::fstat(descriptor_, &opened) != 0 || !S_ISFIFO(opened.st_mode)) {
        close_noexcept();
        throw std::runtime_error(
            "inline stationary output changed before FIFO open");
      }
      fifo_ = true;
    } else {
      if (errno != ENOENT) {
        throw std::runtime_error(
            "cannot inspect inline stationary output: " +
            std::string(std::strerror(errno)));
      }
      temporary_path_ =
          output_path_ + ".partial." + std::to_string(::getpid());
      descriptor_ =
          ::open(temporary_path_.c_str(),
                 O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                 S_IRUSR | S_IWUSR);
      if (descriptor_ < 0) {
        throw std::runtime_error(
            "cannot create exclusive inline stationary temporary file: " +
            std::string(std::strerror(errno)));
      }
    }
    write_raw(header_.data(), header_.size());
    whole_stream_hasher_.update(header_.data(), header_.size());
    bytes_written_ = header_.size();
  }

  InlineStationaryStreamOutput(const InlineStationaryStreamOutput&) = delete;
  InlineStationaryStreamOutput& operator=(
      const InlineStationaryStreamOutput&) = delete;

  ~InlineStationaryStreamOutput() {
    close_noexcept();
    if (!published_ && !temporary_path_.empty()) {
      ::unlink(temporary_path_.c_str());
    }
  }

  void write(std::uint64_t block, const per::RawRecord& event_record,
             const psj::Result& junction) {
    if (finished_ || records_written_ >= values_.block_count ||
        block != values_.first_block + records_written_ ||
        !junction.accepted || junction.failure_flags != 0U ||
        junction.resolver_report.canonical_trace_json.empty()) {
      throw std::runtime_error(
          "inline stationary record order, lifecycle, or acceptance differs");
    }
    const std::string& trace =
        junction.resolver_report.canonical_trace_json;
    if (trace.size() >
        std::numeric_limits<std::uint64_t>::max() - total_trace_bytes_) {
      throw std::runtime_error(
          "inline stationary trace byte total overflows");
    }
    const std::vector<unsigned char> frame = pis::encode_frame(
        block, event_record, junction.record, trace);
    // Fail closed inside the producer too: the bytes about to be written must
    // survive the same canonical parser used by the independent KAT.
    const pis::DecodedFrame decoded = pis::decode_frame(frame, block);
    if (decoded.event_record != event_record ||
        decoded.junction_record != junction.record ||
        decoded.stationary_trace != trace) {
      throw std::runtime_error(
          "inline stationary frame changed during canonical replay");
    }
    write_raw(frame.data(), frame.size());
    frame_stream_hasher_.update(frame.data(), frame.size());
    whole_stream_hasher_.update(frame.data(), frame.size());
    total_trace_bytes_ += trace.size();
    bytes_written_ += frame.size();
    ++records_written_;
  }

  void finish() {
    if (finished_ || records_written_ != values_.block_count) {
      throw std::runtime_error(
          "inline stationary stream cannot finalize an incomplete range");
    }
    const pis::FooterValues footer_values{
        .first_block = values_.first_block,
        .block_count = values_.block_count,
        .total_event_records = records_written_,
        .total_junction_records = records_written_,
        .total_trace_bytes = total_trace_bytes_,
        .frame_stream_sha256 = frame_stream_hasher_.finish(),
        .header_sha256 =
            per::digest_at(header_.data() + pis::kHeaderDigestOffset),
        .gamma_stream_sha256 = values_.gamma_stream_sha256,
    };
    const pis::RawFooter footer = pis::encode_footer(footer_values);
    pis::decode_footer(footer, &footer_values);
    write_raw(footer.data(), footer.size());
    whole_stream_hasher_.update(footer.data(), footer.size());
    stream_sha256_ = whole_stream_hasher_.finish();
    footer_sha256_ =
        per::digest_at(footer.data() + pis::kFooterDigestOffset);
    bytes_written_ += footer.size();

    if (!fifo_ && ::fsync(descriptor_) != 0) {
      throw std::runtime_error("cannot fsync inline stationary output");
    }
    if (::close(descriptor_) != 0) {
      descriptor_ = -1;
      throw std::runtime_error("cannot close inline stationary output");
    }
    descriptor_ = -1;
    if (!fifo_) {
      if (::link(temporary_path_.c_str(), output_path_.c_str()) != 0) {
        throw std::runtime_error(
            "cannot publish inline stationary stream without replacement: " +
            std::string(std::strerror(errno)));
      }
      published_ = true;
      if (::unlink(temporary_path_.c_str()) != 0) {
        throw std::runtime_error(
            "cannot remove published inline stationary temporary link");
      }
      temporary_path_.clear();
    } else {
      published_ = true;
    }
    finished_ = true;
  }

  const sparkinterval::Sha256Digest& stream_sha256() const {
    if (!finished_) {
      throw std::runtime_error(
          "inline stationary stream digest requested before finish");
    }
    return stream_sha256_;
  }

  const sparkinterval::Sha256Digest& footer_sha256() const {
    if (!finished_) {
      throw std::runtime_error(
          "inline stationary footer digest requested before finish");
    }
    return footer_sha256_;
  }

  bool is_fifo() const { return fifo_; }
  std::uint64_t bytes_written() const { return bytes_written_; }
  std::uint64_t total_trace_bytes() const { return total_trace_bytes_; }

 private:
  void write_raw(const unsigned char* data, std::size_t size) {
    std::size_t offset = 0U;
    while (offset < size) {
      const ssize_t wrote =
          ::write(descriptor_, data + offset, size - offset);
      if (wrote < 0 && errno == EINTR) continue;
      if (wrote <= 0) {
        throw std::runtime_error(
            "cannot write inline stationary stream: " +
            std::string(std::strerror(errno)));
      }
      offset += static_cast<std::size_t>(wrote);
    }
  }

  void close_noexcept() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  std::string output_path_;
  std::string temporary_path_;
  int descriptor_ = -1;
  bool fifo_ = false;
  bool published_ = false;
  bool finished_ = false;
  pis::RawHeader header_{};
  pis::HeaderValues values_{};
  sparkinterval::detail::Sha256 frame_stream_hasher_;
  sparkinterval::detail::Sha256 whole_stream_hasher_;
  sparkinterval::Sha256Digest stream_sha256_{};
  sparkinterval::Sha256Digest footer_sha256_{};
  std::uint64_t records_written_ = 0U;
  std::uint64_t total_trace_bytes_ = 0U;
  std::uint64_t bytes_written_ = 0U;
};
#endif

#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
// Ordered, create-only publication of the complete per-block adapter inputs.
// Failure anywhere -- an invalid packet, a rejected junction, an Arb Turing
// failure, an out-of-order block, or a missing terminal footer -- leaves no
// published artifact and therefore no PT21BLK1 downstream.
class BlockInputStreamOutput {
 public:
  BlockInputStreamOutput(const std::string& output_path,
                         const pbi::HeaderValues& values)
      : output_path_(output_path), header_(pbi::encode_header(values)),
        values_(values) {
    if (output_path_.empty() || output_path_ == "-") {
      throw std::runtime_error(
          "block input output must be a named regular file or FIFO");
    }
    struct stat metadata {};
    if (::lstat(output_path_.c_str(), &metadata) == 0) {
      if (!S_ISFIFO(metadata.st_mode)) {
        throw std::runtime_error(
            "block input output already exists and is not a FIFO");
      }
      descriptor_ =
          ::open(output_path_.c_str(), O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
      if (descriptor_ < 0) {
        throw std::runtime_error(
            "cannot open block input FIFO without following links: " +
            std::string(std::strerror(errno)));
      }
      struct stat opened {};
      if (::fstat(descriptor_, &opened) != 0 || !S_ISFIFO(opened.st_mode)) {
        close_noexcept();
        throw std::runtime_error(
            "block input output changed before FIFO open");
      }
      fifo_ = true;
    } else {
      if (errno != ENOENT) {
        throw std::runtime_error(
            "cannot inspect block input output: " +
            std::string(std::strerror(errno)));
      }
      temporary_path_ =
          output_path_ + ".partial." + std::to_string(::getpid());
      descriptor_ =
          ::open(temporary_path_.c_str(),
                 O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                 S_IRUSR | S_IWUSR);
      if (descriptor_ < 0) {
        throw std::runtime_error(
            "cannot create exclusive block input temporary file: " +
            std::string(std::strerror(errno)));
      }
    }
    write_raw(header_.data(), header_.size());
    whole_stream_hasher_.update(header_.data(), header_.size());
    bytes_written_ = header_.size();
  }

  BlockInputStreamOutput(const BlockInputStreamOutput&) = delete;
  BlockInputStreamOutput& operator=(const BlockInputStreamOutput&) = delete;

  ~BlockInputStreamOutput() {
    close_noexcept();
    if (!published_ && !temporary_path_.empty()) {
      ::unlink(temporary_path_.c_str());
    }
  }

  void write(std::uint64_t block,
             std::span<const unsigned char> required_sign_packet,
             const per::RawRecord& event_record,
             const psj::Result& junction,
             const std::string& turing_inputs) {
    if (finished_ || records_written_ >= values_.block_count ||
        block != values_.first_block + records_written_ ||
        !junction.accepted || junction.failure_flags != 0U ||
        junction.resolver_report.canonical_trace_json.empty()) {
      throw std::runtime_error(
          "block input record order, lifecycle, or acceptance differs");
    }
    const std::string& trace =
        junction.resolver_report.canonical_trace_json;
    const pbi::FramePayload payload{
        .block = block,
        .required_sign_packet = required_sign_packet,
        .event_record = event_record,
        .junction_record = junction.record,
        .stationary_trace = trace,
        .turing_inputs = turing_inputs,
    };
    const std::vector<unsigned char> frame = pbi::encode_frame(payload);
    // Fail closed inside the producer too: the bytes about to be written must
    // survive the same canonical parser used by the independent decoder.
    const pbi::DecodedFrame decoded = pbi::decode_frame(frame, block);
    if (decoded.event_record != event_record ||
        decoded.junction_record != junction.record ||
        decoded.stationary_trace != trace ||
        decoded.turing_inputs != turing_inputs ||
        decoded.required_sign_packet.size() !=
            required_sign_packet.size() ||
        !std::equal(decoded.required_sign_packet.begin(),
                    decoded.required_sign_packet.end(),
                    required_sign_packet.begin())) {
      throw std::runtime_error(
          "block input frame changed during canonical replay");
    }
    if (trace.size() >
            std::numeric_limits<std::uint64_t>::max() - total_trace_bytes_ ||
        turing_inputs.size() >
            std::numeric_limits<std::uint64_t>::max() -
                total_turing_bytes_) {
      throw std::runtime_error("block input byte total overflows");
    }
    write_raw(frame.data(), frame.size());
    frame_stream_hasher_.update(frame.data(), frame.size());
    whole_stream_hasher_.update(frame.data(), frame.size());
    total_packet_bytes_ += required_sign_packet.size();
    total_trace_bytes_ += trace.size();
    total_turing_bytes_ += turing_inputs.size();
    bytes_written_ += frame.size();
    ++records_written_;
  }

  void finish() {
    if (finished_ || records_written_ != values_.block_count) {
      throw std::runtime_error(
          "block input stream cannot finalize an incomplete range");
    }
    const pbi::FooterValues footer_values{
        .first_block = values_.first_block,
        .block_count = values_.block_count,
        .total_frames = records_written_,
        .total_packet_bytes = total_packet_bytes_,
        .total_trace_bytes = total_trace_bytes_,
        .total_turing_bytes = total_turing_bytes_,
        .frame_stream_sha256 = frame_stream_hasher_.finish(),
        .header_sha256 =
            per::digest_at(header_.data() + pbi::kHeaderDigestOffset),
        .gamma_stream_sha256 = values_.gamma_stream_sha256,
    };
    const pbi::RawFooter footer = pbi::encode_footer(footer_values);
    pbi::decode_footer(footer, &footer_values);
    write_raw(footer.data(), footer.size());
    whole_stream_hasher_.update(footer.data(), footer.size());
    stream_sha256_ = whole_stream_hasher_.finish();
    footer_sha256_ =
        per::digest_at(footer.data() + pbi::kFooterDigestOffset);
    bytes_written_ += footer.size();

    if (!fifo_ && ::fsync(descriptor_) != 0) {
      throw std::runtime_error("cannot fsync block input output");
    }
    if (::close(descriptor_) != 0) {
      descriptor_ = -1;
      throw std::runtime_error("cannot close block input output");
    }
    descriptor_ = -1;
    if (!fifo_) {
      if (::link(temporary_path_.c_str(), output_path_.c_str()) != 0) {
        throw std::runtime_error(
            "cannot publish block input stream without replacement: " +
            std::string(std::strerror(errno)));
      }
      published_ = true;
      if (::unlink(temporary_path_.c_str()) != 0) {
        throw std::runtime_error(
            "cannot remove published block input temporary link");
      }
      temporary_path_.clear();
    } else {
      published_ = true;
    }
    finished_ = true;
  }

  const sparkinterval::Sha256Digest& stream_sha256() const {
    if (!finished_) {
      throw std::runtime_error(
          "block input stream digest requested before finish");
    }
    return stream_sha256_;
  }

  const sparkinterval::Sha256Digest& footer_sha256() const {
    if (!finished_) {
      throw std::runtime_error(
          "block input footer digest requested before finish");
    }
    return footer_sha256_;
  }

  bool is_fifo() const { return fifo_; }
  std::uint64_t bytes_written() const { return bytes_written_; }
  std::uint64_t total_packet_bytes() const { return total_packet_bytes_; }
  std::uint64_t total_turing_bytes() const { return total_turing_bytes_; }

 private:
  void write_raw(const unsigned char* data, std::size_t size) {
    std::size_t offset = 0U;
    while (offset < size) {
      const ssize_t wrote =
          ::write(descriptor_, data + offset, size - offset);
      if (wrote < 0 && errno == EINTR) continue;
      if (wrote <= 0) {
        throw std::runtime_error(
            "cannot write block input stream: " +
            std::string(std::strerror(errno)));
      }
      offset += static_cast<std::size_t>(wrote);
    }
  }

  void close_noexcept() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  std::string output_path_;
  std::string temporary_path_;
  int descriptor_ = -1;
  bool fifo_ = false;
  bool published_ = false;
  bool finished_ = false;
  pbi::RawHeader header_{};
  pbi::HeaderValues values_{};
  sparkinterval::detail::Sha256 frame_stream_hasher_;
  sparkinterval::detail::Sha256 whole_stream_hasher_;
  sparkinterval::Sha256Digest stream_sha256_{};
  sparkinterval::Sha256Digest footer_sha256_{};
  std::uint64_t records_written_ = 0U;
  std::uint64_t total_packet_bytes_ = 0U;
  std::uint64_t total_trace_bytes_ = 0U;
  std::uint64_t total_turing_bytes_ = 0U;
  std::uint64_t bytes_written_ = 0U;
};
#endif

bool finite_disk(const pw::RealDisk106& disk) {
  return std::isfinite(disk.center.hi) &&
         std::isfinite(disk.center.lo) &&
         std::isfinite(disk.radius) && disk.radius >= 0.0;
}

per::BlockValues event_block_values(
    std::uint64_t block, const pes::ScanStatus& status,
    const std::array<pes::StreamSummary, pes::kStreamCount>& summaries) {
  if (status.reserved_zero != 0U) {
    throw std::runtime_error("event scan status reserved field differs");
  }
  if (std::memcmp(&summaries[0].right_endpoint,
                  &summaries[1].left_endpoint,
                  sizeof(pes::EndpointRecord)) != 0 ||
      std::memcmp(&summaries[1].right_endpoint,
                  &summaries[2].left_endpoint,
                  sizeof(pes::EndpointRecord)) != 0) {
    throw std::runtime_error(
        "event scanner duplicated shared endpoints differently");
  }

  per::BlockValues result;
  result.block = block;
  result.failure_flags = status.failure_flags;
  result.certified_sample_count = status.certified_sample_count;
  result.digest_valid = status.digest_valid;
  std::memcpy(result.event_artifact_sha256.data(),
              status.artifact_sha256,
              result.event_artifact_sha256.size());
  for (std::size_t stream = 0U; stream < pes::kStreamCount; ++stream) {
    const pes::StreamSummary& summary = summaries[stream];
    const std::int32_t lower = per::kStreamLower[stream];
    const std::int32_t upper = per::kStreamUpper[stream];
    if (summary.stream != stream || summary.lower_sample != lower ||
        summary.upper_sample != upper ||
        summary.range_sample_count !=
            static_cast<std::uint32_t>(upper - lower + 1) ||
        summary.reserved_zero != 0U ||
        summary.left_endpoint.sample_offset != lower ||
        summary.right_endpoint.sample_offset != upper ||
        summary.left_endpoint.positive > 1U ||
        summary.right_endpoint.positive > 1U ||
        !finite_disk(summary.left_endpoint.disk) ||
        !finite_disk(summary.right_endpoint.disk)) {
      throw std::runtime_error("event scanner summary geometry differs");
    }
    result.direct_event_count[stream] = summary.direct_event_count;
    result.stationary_candidate_count[stream] =
        summary.stationary_candidate_count;
    result.certified_direct_slots[stream] =
        summary.certified_direct_multiplicity_slots;
    if (summary.stationary_candidate_count >
        std::numeric_limits<std::uint32_t>::max() -
            result.unresolved_stationary_count) {
      throw std::runtime_error(
          "event scanner stationary total overflows");
    }
    result.unresolved_stationary_count +=
        summary.stationary_candidate_count;
    result.direct_nleft_units[stream] = summary.direct_nleft_units;
    result.direct_nright_units[stream] = summary.direct_nright_units;
  }
  per::validate_block_values(result, block);
  return result;
}

struct ReplayRingSlot {
  pes::ReplayCapture* capture = nullptr;
  std::uint64_t logical_block = 0U;
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
  // Exact authenticated Gamma V2 input record for the same logical block.  It
  // is the honest `source_packet` identity bound by the emitted PT21SGN1.
  std::array<unsigned char, sizeof(pg2::Record)> gamma_record{};
#endif
};

int run(const Options& options) {
  require_target_device();
  const auto wall_started = std::chrono::steady_clock::now();
  std::ifstream input(options.stream_path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open Gamma Taylor V2 stream");
  pg2::Reader reader(input, options.first_block, options.block_count,
                     options.expected_stream_sha256);
  if (reader.header().chunk_records > options.maximum_chunk_records) {
    throw std::runtime_error("V2 chunk exceeds configured host-memory cap");
  }

  pda::Workspace* accumulator = nullptr;
  pdt::Workspace* transform = nullptr;
  pes::Workspace* event_scanner = nullptr;
  std::unique_ptr<EventStreamOutput> event_output;
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
  std::unique_ptr<InlineStationaryStreamOutput> inline_stationary_output;
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
  std::unique_ptr<BlockInputStreamOutput> block_input_output;
#endif
  pg2::Record* device_record = nullptr;
  pw::ComplexDisk106* device_gamma = nullptr;
  unsigned long long* device_invalid = nullptr;
  unsigned long long* device_ambiguous = nullptr;
  unsigned long long* device_digest = nullptr;
  unsigned long long* device_maximum_radius = nullptr;
  std::vector<ReplayRingSlot> replay_ring;
  std::deque<std::size_t> free_replay_slots;
  std::deque<std::size_t> pending_replay_slots;
  std::mutex replay_mutex;
  std::condition_variable replay_condition;
  bool replay_producer_done = false;
  bool replay_cancelled = false;
  std::exception_ptr replay_failure;
  std::vector<std::thread> replay_threads;
  cudaStream_t stream = nullptr;
  cudaEvent_t started = nullptr;
  cudaEvent_t stopped = nullptr;
  try {
    accumulator = pda::create_source_workspace(
        options.first_block, options.block_count, options.reanchor_blocks);
    transform = pdt::create_source_workspace();
    event_scanner = pes::create_workspace();
    CUDA_CHECK(cudaMalloc(&device_record, sizeof(*device_record)));
    CUDA_CHECK(cudaMalloc(&device_gamma,
                          pw::kBucketCount * sizeof(*device_gamma)));
    CUDA_CHECK(cudaMalloc(&device_invalid, sizeof(*device_invalid)));
    CUDA_CHECK(cudaMalloc(&device_ambiguous, sizeof(*device_ambiguous)));
    CUDA_CHECK(cudaMalloc(&device_digest, sizeof(*device_digest)));
    CUDA_CHECK(cudaMalloc(&device_maximum_radius,
                          sizeof(*device_maximum_radius)));
    replay_ring.resize(options.event_ring_blocks);
    for (std::size_t slot = 0U; slot < replay_ring.size(); ++slot) {
      replay_ring[slot].capture =
          pes::create_replay_capture(event_scanner);
      free_replay_slots.push_back(slot);
    }
    CUDA_CHECK(cudaMemset(device_invalid, 0, sizeof(*device_invalid)));
    CUDA_CHECK(cudaMemset(device_ambiguous, 0, sizeof(*device_ambiguous)));
    CUDA_CHECK(cudaMemset(device_digest, 0, sizeof(*device_digest)));
    CUDA_CHECK(cudaMemset(device_maximum_radius, 0,
                          sizeof(*device_maximum_radius)));
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    CUDA_CHECK(cudaEventCreate(&started));
    CUDA_CHECK(cudaEventCreate(&stopped));
    if (options.event_stream_output.has_value()) {
      event_output = std::make_unique<EventStreamOutput>(
          *options.event_stream_output,
          per::HeaderValues{
              .first_block = options.first_block,
              .block_count = options.block_count,
              .gamma_stream_sha256 = *options.expected_stream_sha256,
              .producer_sha256 = *options.producer_sha256,
          });
    }
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
    inline_stationary_output =
        std::make_unique<InlineStationaryStreamOutput>(
            *options.inline_stationary_output,
            pis::HeaderValues{
                .first_block = options.first_block,
                .block_count = options.block_count,
                .gamma_stream_sha256 = *options.expected_stream_sha256,
                .producer_sha256 = *options.producer_sha256,
                .resolver_sha256 = *options.resolver_sha256,
                .flint_sha256 = *options.flint_sha256,
            });
    const psj::IdentityPins inline_identities{
        .resolver_sha256 = *options.resolver_sha256,
        .flint_sha256 = *options.flint_sha256,
    };
    psr::Options inline_resolver_options;
    inline_resolver_options.retain_precision_hull_audit = true;
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
    block_input_output = std::make_unique<BlockInputStreamOutput>(
        *options.block_input_output,
        pbi::HeaderValues{
            .first_block = options.first_block,
            .block_count = options.block_count,
            .gamma_stream_sha256 = *options.expected_stream_sha256,
            .producer_sha256 = *options.producer_sha256,
            .resolver_sha256 = *options.resolver_sha256,
            .flint_sha256 = *options.flint_sha256,
        });
#endif
    const auto submission_started = std::chrono::steady_clock::now();
    CUDA_CHECK(cudaEventRecord(started, stream));

    std::uint64_t enqueued = 0U;
    std::uint64_t records = 0U;
    std::uint64_t direct_event_total = 0U;
    std::uint64_t stationary_candidate_total = 0U;
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
    std::uint64_t stationary_resolution_total = 0U;
    std::uint64_t stationary_multiplicity_slot_total = 0U;
    double inline_scanner_replay_seconds = 0.0;
    double inline_stationary_seconds = 0.0;
    double inline_serialization_seconds = 0.0;
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
    double block_packet_seconds = 0.0;
    double block_turing_seconds = 0.0;
    double block_serialization_seconds = 0.0;
#endif
    auto add_total = [](std::uint64_t* accumulator,
                        std::uint32_t value, const char* label) {
      if (value >
          std::numeric_limits<std::uint64_t>::max() - *accumulator) {
        throw std::runtime_error(std::string(label) + " total overflows");
      }
      *accumulator += value;
    };
    auto replay_worker = [&]() {
      try {
        while (true) {
          std::size_t slot_index = 0U;
          {
            std::unique_lock lock(replay_mutex);
            replay_condition.wait(lock, [&]() {
              return replay_cancelled || !pending_replay_slots.empty() ||
                     replay_producer_done;
            });
            if (replay_cancelled) return;
            if (pending_replay_slots.empty()) {
              if (replay_producer_done) return;
              continue;
            }
            slot_index = pending_replay_slots.front();
            pending_replay_slots.pop_front();
          }
          ReplayRingSlot& slot = replay_ring[slot_index];
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
          const auto inline_replay_started =
              std::chrono::steady_clock::now();
#endif
          const pes::ReplayReport replay =
              pes::replay_captured(slot.capture);
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
          const double inline_replay_seconds =
              std::chrono::duration<double>(
                  std::chrono::steady_clock::now() -
                  inline_replay_started).count();
#endif
          if (!replay.accepted) {
            throw std::runtime_error(
                "source event scan failed independent host replay: " +
                replay.error);
          }
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
          // Qualification-only fusion boundary.  The exact PT21EVT1 is
          // constructed from this replay and passed with the same replay-owned
          // sample/candidate payload directly into the pinned finite junction.
          // No second scanner replay and no process hop occurs here.
          const per::BlockValues inline_event_values = event_block_values(
              slot.logical_block, replay.artifact.status,
              replay.artifact.summaries);
          const per::RawRecord inline_event_record =
              per::encode_record(inline_event_values);
          const auto inline_started = std::chrono::steady_clock::now();
          const psj::Result inline_junction = psj::resolve_replayed_block(
              slot.logical_block, inline_event_record, replay, {},
              inline_identities, inline_resolver_options);
          const double inline_seconds = std::chrono::duration<double>(
              std::chrono::steady_clock::now() - inline_started).count();
          if (!inline_junction.accepted ||
              inline_junction.failure_flags != 0U) {
            throw std::runtime_error(
                "inline stationary junction rejected block " +
                std::to_string(slot.logical_block) + ": " +
                inline_junction.error + "; resolver_flags=" +
                std::to_string(
                    inline_junction.resolver_report.failure_flags) +
                "; resolver_error=" +
                inline_junction.resolver_report.error);
          }
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
          // Same ordered loop, same replay-owned disks: build the two
          // remaining adapter inputs here rather than in a standalone
          // assembly process.  Both stages fail closed, so an unresolved
          // finite predicate cannot reach the record adapter.
          const auto block_packet_started = std::chrono::steady_clock::now();
          const std::vector<unsigned char> block_required_packet =
              prs::encode_packet(slot.logical_block,
                                 replay.required_samples,
                                 slot.gamma_record);
          const double block_packet_elapsed =
              std::chrono::duration<double>(
                  std::chrono::steady_clock::now() -
                  block_packet_started).count();
          const auto block_turing_started =
              std::chrono::steady_clock::now();
          const std::string block_turing_inputs = pti::artifact_json(
              slot.logical_block,
              sparkinterval::lowercase_hex(
                  sparkinterval::sha256(block_required_packet.data(),
                                        block_required_packet.size())));
          const double block_turing_elapsed =
              std::chrono::duration<double>(
                  std::chrono::steady_clock::now() -
                  block_turing_started).count();
#endif
          {
            std::unique_lock lock(replay_mutex);
            replay_condition.wait(lock, [&]() {
              return replay_cancelled ||
                     slot.logical_block <= options.first_block + records;
            });
            if (replay_cancelled) return;
            if (slot.logical_block != options.first_block + records) {
              throw std::runtime_error(
                  "event replay ring is not gap-free and ordered");
            }
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
            const per::BlockValues& event_values = inline_event_values;
#else
            const per::BlockValues event_values = event_block_values(
                slot.logical_block, replay.artifact.status,
                replay.artifact.summaries);
#endif
            for (std::size_t event_stream = 0U;
                 event_stream < pes::kStreamCount; ++event_stream) {
              add_total(&direct_event_total,
                        event_values.direct_event_count[event_stream],
                        "direct event");
              add_total(
                  &stationary_candidate_total,
                  event_values.stationary_candidate_count[event_stream],
                  "stationary candidate");
            }
            if (event_output != nullptr) {
              event_output->write(
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
                  inline_event_record,
#else
                  per::encode_record(event_values),
#endif
                  event_values);
            }
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
            const auto inline_serialization_started =
                std::chrono::steady_clock::now();
            inline_stationary_output->write(
                slot.logical_block, inline_event_record, inline_junction);
            const double inline_serialization =
                std::chrono::duration<double>(
                    std::chrono::steady_clock::now() -
                    inline_serialization_started).count();
            add_total(
                &stationary_resolution_total,
                static_cast<std::uint32_t>(
                    inline_junction.resolver_report.resolutions.size()),
                "stationary resolution");
            add_total(
                &stationary_multiplicity_slot_total,
                psj::decode_record(
                    inline_junction.record).resolved_multiplicity_slots,
                "stationary multiplicity slot");
            inline_scanner_replay_seconds += inline_replay_seconds;
            inline_stationary_seconds += inline_seconds;
            inline_serialization_seconds += inline_serialization;
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
            const auto block_serialization_started =
                std::chrono::steady_clock::now();
            block_input_output->write(
                slot.logical_block, block_required_packet,
                inline_event_record, inline_junction, block_turing_inputs);
            block_serialization_seconds += std::chrono::duration<double>(
                std::chrono::steady_clock::now() -
                block_serialization_started).count();
            block_packet_seconds += block_packet_elapsed;
            block_turing_seconds += block_turing_elapsed;
#endif
            ++records;
            free_replay_slots.push_back(slot_index);
          }
          replay_condition.notify_all();
        }
      } catch (...) {
        {
          std::lock_guard lock(replay_mutex);
          if (replay_failure == nullptr) {
            replay_failure = std::current_exception();
          }
          replay_cancelled = true;
        }
        replay_condition.notify_all();
      }
    };
    const std::uint32_t replay_thread_count =
        std::min(options.event_replay_threads,
                 options.event_ring_blocks);
    replay_threads.reserve(replay_thread_count);
    for (std::uint32_t index = 0U; index < replay_thread_count; ++index) {
      replay_threads.emplace_back(replay_worker);
    }
    auto acquire_replay_slot = [&]() {
      std::unique_lock lock(replay_mutex);
      replay_condition.wait(lock, [&]() {
        return replay_cancelled || !free_replay_slots.empty();
      });
      if (replay_cancelled) {
        const std::exception_ptr failure = replay_failure;
        lock.unlock();
        if (failure != nullptr) std::rethrow_exception(failure);
        throw std::runtime_error("event replay worker was cancelled");
      }
      const std::size_t result = free_replay_slots.front();
      free_replay_slots.pop_front();
      return result;
    };
    pg2::AuthenticatedChunk chunk;
    while (reader.next(chunk)) {
      for (std::size_t offset = 0U; offset < chunk.records.size(); ++offset) {
        const std::uint64_t logical_block = chunk.first_block + offset;
        if (logical_block != options.first_block + enqueued) {
          throw std::runtime_error("V2 Gamma and source block order differs");
        }
        const std::size_t replay_slot_index = acquire_replay_slot();
        CUDA_CHECK(cudaMemcpyAsync(device_record, &chunk.records[offset],
                                   sizeof(*device_record),
                                   cudaMemcpyHostToDevice, stream));
        pgd::launch_synthesize(
            device_record,
            {device_gamma, 1U, pw::kBucketCount, logical_block}, stream);
        const pda::SourceWindowView skn =
            pda::run_next_source_window(accumulator, stream);
        if (skn.logical_block != logical_block ||
            skn.stage_count != pw::kTaylorTerms ||
            skn.row_stride != pw::kBucketCount) {
          throw std::runtime_error("V2 Gamma and DD accumulator diverged");
        }
        pdt::run_source_window(transform, device_gamma,
                               skn.device_skn_rows, stream);
        audit_required<<<128U, 256U, 0U, stream>>>(
            pdt::device_required_samples(transform), device_invalid,
            device_ambiguous, device_digest, device_maximum_radius);
        CUDA_CHECK(cudaGetLastError());
        pes::scan_source_required_samples(
            event_scanner, pdt::device_required_samples(transform), stream);
        ReplayRingSlot& replay_slot = replay_ring[replay_slot_index];
        replay_slot.logical_block = logical_block;
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
        std::memcpy(replay_slot.gamma_record.data(),
                    &chunk.records[offset],
                    replay_slot.gamma_record.size());
#endif
        try {
          pes::enqueue_replay_capture(
              event_scanner, pdt::device_required_samples(transform),
              replay_slot.capture, stream);
        } catch (...) {
          {
            std::lock_guard lock(replay_mutex);
            free_replay_slots.push_front(replay_slot_index);
          }
          replay_condition.notify_all();
          throw;
        }
        // Every sample and the scanner's full bounded arrays are copied before
        // the next same-stream workspace reuse.  The CPU thread waits on the
        // per-slot event and reruns the exact fixed-integer replay while CUDA
        // submits later windows.
        {
          std::lock_guard lock(replay_mutex);
          pending_replay_slots.push_back(replay_slot_index);
        }
        replay_condition.notify_one();
        ++enqueued;
      }
    }
    CUDA_CHECK(cudaEventRecord(stopped, stream));
    const auto replay_drain_started = std::chrono::steady_clock::now();
    {
      std::lock_guard lock(replay_mutex);
      replay_producer_done = true;
    }
    replay_condition.notify_all();
    for (std::thread& worker : replay_threads) worker.join();
    const auto replay_drained = std::chrono::steady_clock::now();
    if (replay_failure != nullptr) {
      std::rethrow_exception(replay_failure);
    }
    if (!reader.complete() || enqueued != options.block_count ||
        records != options.block_count ||
        pda::windows_enqueued(accumulator) != options.block_count) {
      throw std::runtime_error("V2 fused worker accepted only a prefix");
    }
    if (event_output != nullptr) event_output->finish();
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
    inline_stationary_output->finish();
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
    block_input_output->finish();
#endif
    CUDA_CHECK(cudaEventSynchronize(stopped));
    float milliseconds = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&milliseconds, started, stopped));
    unsigned long long invalid = 0U;
    unsigned long long ambiguous = 0U;
    unsigned long long digest = 0U;
    unsigned long long maximum_radius_bits = 0U;
    CUDA_CHECK(cudaMemcpy(&invalid, device_invalid, sizeof(invalid),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(&ambiguous, device_ambiguous, sizeof(ambiguous),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(&digest, device_digest, sizeof(digest),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(&maximum_radius_bits, device_maximum_radius,
                          sizeof(maximum_radius_bits),
                          cudaMemcpyDeviceToHost));
    if (invalid != 0U) {
      throw std::runtime_error("V2 fused worker emitted invalid disks");
    }
    if (ambiguous != 0U) {
      throw std::runtime_error(
          "V2 fused worker left ambiguous required sign disks");
    }
    const double maximum_radius =
        std::bit_cast<double>(static_cast<std::uint64_t>(maximum_radius_bits));
    const double gpu_seconds = milliseconds / 1000.0;
    const auto post_replay_finished = std::chrono::steady_clock::now();
    const double setup_seconds = std::chrono::duration<double>(
        submission_started - wall_started).count();
    const double submission_wall_seconds = std::chrono::duration<double>(
        replay_drain_started - submission_started).count();
    const double replay_drain_seconds = std::chrono::duration<double>(
        replay_drained - replay_drain_started).count();
    const double post_replay_seconds = std::chrono::duration<double>(
        post_replay_finished - replay_drained).count();
    const double wall_seconds = std::chrono::duration<double>(
        post_replay_finished - wall_started).count();
    const bool compact_event_records = event_output != nullptr;
    const std::uint64_t event_stream_bytes =
        compact_event_records
            ? per::kHeaderBytes + records * per::kRecordBytes +
                  per::kFooterBytes
            : 0U;
    std::uint64_t replay_ring_pinned_bytes = 0U;
    for (const ReplayRingSlot& slot : replay_ring) {
      replay_ring_pinned_bytes +=
          pes::replay_capture_pinned_bytes(slot.capture);
    }
    std::cout << std::setprecision(17)
              << "{\"schema\":\""
#if defined(SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION)
              << "sparkinterval.tg.platt-pt21-block-stage-qualification.v1"
#elif defined(SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION)
              << "sparkinterval.tg.platt-inline-stationary-qualification.v1"
#else
              << "sparkinterval.tg.platt-fused-source-worker.v2"
#endif
              << "\""
              << ",\"build_profile\":{\"cmake_build_config\":\""
              << kCmakeBuildConfig << "\",\"ndebug_defined\":"
              << (kNdebugDefined ? "true" : "false")
              << ",\"release_performance_build\":"
              << (kReleasePerformanceBuild ? "true" : "false") << '}'
              << ",\"accepted\":true"
              << ",\"claim_scope\":\""
#if defined(SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION)
              << "bounded_authenticated_three_adapter_inputs_streamed_from_one_ordered_worker_loop"
#elif defined(SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION)
              << "bounded_authenticated_dd_gamma_events_and_finite_stationary_junction"
#else
              << "authenticated_dd_gamma_accumulator_transform_three_stream_finite_events"
#endif
              << "\""
              << ",\"first_block\":" << options.first_block
              << ",\"block_count\":" << records
              << ",\"required_samples_audited\":"
              << records * pdt::kSourceRequiredCount
              << ",\"invalid_required_disks\":0"
              << ",\"ambiguous_required_disks\":" << ambiguous
              << ",\"maximum_required_radius\":" << maximum_radius
              << ",\"required_digest_xor\":\"" << std::hex
              << std::setw(16) << std::setfill('0') << digest << std::dec
              << "\""
              << ",\"gpu_seconds\":" << gpu_seconds
              << ",\"windows_per_second\":" << records / gpu_seconds
              << ",\"setup_seconds\":" << setup_seconds
              << ",\"submission_wall_seconds\":"
              << submission_wall_seconds
              << ",\"replay_drain_seconds\":" << replay_drain_seconds
              << ",\"post_replay_seconds\":" << post_replay_seconds
              << ",\"wall_seconds\":" << wall_seconds
              << ",\"gamma_stream_v2\":true"
              << ",\"gamma_stream_sha256_pinned\":true"
              << ",\"gamma_coefficients_complex_disk106\":true"
              << ",\"source_dd_accumulator\":true"
              << ",\"source_dd_transform\":true"
              << ",\"source_packet_retained\":false"
              << ",\"required_samples_captured_for_replay\":true"
              << ",\"three_stream_event_scan_complete\":true"
              << ",\"event_scan_artifacts_merkle_bound\":true"
              << ",\"event_scan_independent_host_replay_complete\":true"
              << ",\"event_scan_device_host_byte_identity\":true"
              << ",\"total_direct_events\":" << direct_event_total
              << ",\"total_stationary_candidates\":"
              << stationary_candidate_total
              << ",\"stationary_candidates_certified_slots\":0"
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
              << ",\"qualification_only\":true"
              << ",\"inline_stationary_algorithm\":\""
              << pis::kAlgorithmDomain << "\""
              << ",\"inline_stationary_algorithm_sha256\":\""
              << sparkinterval::lowercase_hex(pis::algorithm_sha256())
              << "\""
              << ",\"inline_stationary_records_emitted\":" << records
              << ",\"inline_stationary_resolution_count\":"
              << stationary_resolution_total
              << ",\"inline_stationary_resolved_multiplicity_slots\":"
              << stationary_multiplicity_slot_total
              << ",\"inline_stationary_resolution_seconds\":"
              << inline_stationary_seconds
              << ",\"inline_scanner_replay_thread_seconds\":"
              << inline_scanner_replay_seconds
              << ",\"inline_stationary_serialization_seconds\":"
              << inline_serialization_seconds
              << ",\"inline_stationary_resolutions_per_second\":"
              << (inline_stationary_seconds == 0.0
                      ? 0.0
                      : stationary_resolution_total /
                            inline_stationary_seconds)
              << ",\"inline_stationary_wire_magic\":\"PT21IQH1\""
              << ",\"inline_stationary_frame_magic\":\"PT21IQF1\""
              << ",\"inline_stationary_footer_magic\":\"PT21IQT1\""
              << ",\"inline_stationary_stream_bytes\":"
              << inline_stationary_output->bytes_written()
              << ",\"inline_stationary_trace_bytes\":"
              << inline_stationary_output->total_trace_bytes()
              << ",\"inline_stationary_stream_fifo\":"
              << (inline_stationary_output->is_fifo() ? "true" : "false")
              << ",\"inline_stationary_stream_sha256\":\""
              << sparkinterval::lowercase_hex(
                     inline_stationary_output->stream_sha256())
              << "\""
              << ",\"inline_stationary_footer_sha256\":\""
              << sparkinterval::lowercase_hex(
                     inline_stationary_output->footer_sha256())
              << "\""
              << ",\"resolver_sha256\":\""
              << sparkinterval::lowercase_hex(*options.resolver_sha256)
              << "\""
              << ",\"flint_sha256\":\""
              << sparkinterval::lowercase_hex(*options.flint_sha256)
              << "\""
              << ",\"producer_sha256_self_verified\":false"
              << ",\"resolver_sha256_self_verified\":false"
              << ",\"flint_sha256_self_verified\":false"
              << ",\"identity_pins_require_external_manifest_or_attestation\":true"
              << ",\"resolver_inputs_retained\":false"
              << ",\"resolver_input_sha256_recomputed_from_frame\":false"
              << ",\"candidate_completeness_recomputed_from_frame\":false"
              << ",\"independent_checker_complete\":false"
              << ",\"precision_hull_trace_v2\":true"
              << ",\"base_precision_bits\":128"
              << ",\"replay_precision_bits\":192"
              << ",\"higher_precision_containment_semantics\":"
                 "\"replay_contained_in_retained_outward_hull\""
              << ",\"stationary_junction_finite_replay_complete\":true"
              << ",\"stationary_junction_second_process_used\":false"
              << ",\"stationary_junction_second_scanner_replay_used\":false"
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
              << ",\"block_input_stream_algorithm\":\""
              << pbi::kAlgorithmDomain << "\""
              << ",\"block_input_stream_algorithm_sha256\":\""
              << sparkinterval::lowercase_hex(pbi::algorithm_sha256())
              << "\""
              << ",\"block_input_wire_magic\":\"PT21WBH1\""
              << ",\"block_input_frame_magic\":\"PT21WBF1\""
              << ",\"block_input_footer_magic\":\"PT21WBT1\""
              << ",\"block_input_frames_emitted\":" << records
              << ",\"block_input_stream_bytes\":"
              << block_input_output->bytes_written()
              << ",\"block_input_required_sign_packet_bytes\":"
              << block_input_output->total_packet_bytes()
              << ",\"block_input_turing_artifact_bytes\":"
              << block_input_output->total_turing_bytes()
              << ",\"block_input_stream_fifo\":"
              << (block_input_output->is_fifo() ? "true" : "false")
              << ",\"block_input_stream_sha256\":\""
              << sparkinterval::lowercase_hex(
                     block_input_output->stream_sha256())
              << "\""
              << ",\"block_input_footer_sha256\":\""
              << sparkinterval::lowercase_hex(
                     block_input_output->footer_sha256())
              << "\""
              << ",\"required_sign_packet_seconds\":"
              << block_packet_seconds
              << ",\"turing_input_seconds\":" << block_turing_seconds
              << ",\"block_input_serialization_seconds\":"
              << block_serialization_seconds
              << ",\"required_sign_packet_streamed_not_retained\":true"
              << ",\"turing_inputs_computed_in_worker\":true"
              << ",\"three_adapter_inputs_streamed\":true"
              << ",\"standalone_assembly_channel_used\":false"
              << ",\"record_adapter_run_in_worker_process\":false"
              << ",\"pt21blk1_emitted_by_worker\":false"
#endif
#else
              << ",\"qualification_only\":false"
#endif
              << ",\"compact_event_records_emitted\":"
              << (compact_event_records ? "true" : "false")
              << ",\"event_record_magic\":\"PT21EVT1\""
              << ",\"event_record_bytes\":" << per::kRecordBytes
              << ",\"event_stream_bytes\":" << event_stream_bytes
              << ",\"event_stream_terminal_authenticated\":"
              << (compact_event_records ? "true" : "false")
              << ",\"event_stream_fifo\":"
              << (compact_event_records && event_output->is_fifo()
                      ? "true"
                      : "false")
              << ",\"event_stream_sha256\":";
    if (compact_event_records) {
      std::cout << '"'
                << sparkinterval::lowercase_hex(
                       event_output->stream_sha256())
                << '"';
    } else {
      std::cout << "null";
    }
    std::cout << ",\"event_stream_footer_sha256\":";
    if (compact_event_records) {
      std::cout << '"'
                << sparkinterval::lowercase_hex(
                       event_output->footer_sha256())
                << '"';
    } else {
      std::cout << "null";
    }
    std::cout << ",\"event_scanner_workspace_device_bytes\":"
              << pes::workspace_device_bytes(event_scanner)
              << ",\"event_result_ring_blocks\":"
              << options.event_ring_blocks
              << ",\"event_result_ring_pinned_host_bytes\":"
              << replay_ring_pinned_bytes
              << ",\"event_replay_cpu_thread_count\":"
              << replay_threads.size()
              << ",\"python_adapter_used_for_event_stage\":false"
              << ",\"pt21_native_block_records_emitted\":false"
              << ",\"flint_to_mathlib_proved\":false"
              << ",\"gaussian_sinc_interpolation_complete\":false"
              << ",\"stationary_refinement_complete\":false"
              << ",\"zero_isolation_complete\":false"
              << ",\"turing_closure_complete\":false"
              << ",\"sgn2_static_manifest_bound\":false"
              << ",\"multi_block_source_chain_closed\":false"
              << ",\"source_claim_ready\":false"
              << ",\"production_ready\":false"
              << ",\"pt21_atom_discharged\":false}\n";

    event_output.reset();
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
    inline_stationary_output.reset();
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
    block_input_output.reset();
#endif
    cudaEventDestroy(stopped);
    stopped = nullptr;
    cudaEventDestroy(started);
    started = nullptr;
    for (ReplayRingSlot& slot : replay_ring) {
      pes::ReplayCapture* capture = slot.capture;
      slot.capture = nullptr;
      pes::destroy_replay_capture(capture);
    }
    cudaStreamDestroy(stream);
    stream = nullptr;
    cudaFree(device_maximum_radius);
    device_maximum_radius = nullptr;
    cudaFree(device_digest);
    device_digest = nullptr;
    cudaFree(device_ambiguous);
    device_ambiguous = nullptr;
    cudaFree(device_invalid);
    device_invalid = nullptr;
    cudaFree(device_gamma);
    device_gamma = nullptr;
    cudaFree(device_record);
    device_record = nullptr;
    pes::destroy_workspace(event_scanner);
    event_scanner = nullptr;
    pdt::destroy_workspace(transform);
    transform = nullptr;
    pda::destroy_workspace(accumulator);
    accumulator = nullptr;
    return 0;
  } catch (...) {
    {
      std::lock_guard lock(replay_mutex);
      replay_cancelled = true;
      replay_producer_done = true;
    }
    replay_condition.notify_all();
    for (std::thread& worker : replay_threads) {
      if (worker.joinable()) worker.join();
    }
    event_output.reset();
#ifdef SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION
    inline_stationary_output.reset();
#endif
#ifdef SPARKINTERVAL_PT21_BLOCK_STAGE_QUALIFICATION
    block_input_output.reset();
#endif
    if (stopped != nullptr) cudaEventDestroy(stopped);
    if (started != nullptr) cudaEventDestroy(started);
    for (ReplayRingSlot& slot : replay_ring) {
      pes::ReplayCapture* capture = slot.capture;
      slot.capture = nullptr;
      try {
        pes::destroy_replay_capture(capture);
      } catch (...) {
      }
    }
    if (stream != nullptr) cudaStreamDestroy(stream);
    if (device_maximum_radius != nullptr) cudaFree(device_maximum_radius);
    if (device_digest != nullptr) cudaFree(device_digest);
    if (device_ambiguous != nullptr) cudaFree(device_ambiguous);
    if (device_invalid != nullptr) cudaFree(device_invalid);
    if (device_gamma != nullptr) cudaFree(device_gamma);
    if (device_record != nullptr) cudaFree(device_record);
    try {
      pes::destroy_workspace(event_scanner);
    } catch (...) {
    }
    pdt::destroy_workspace(transform);
    pda::destroy_workspace(accumulator);
    throw;
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::signal(SIGPIPE, SIG_IGN);
    return run(parse_options(argc, argv));
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 2;
  }
}

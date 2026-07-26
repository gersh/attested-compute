// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_stationary_junction.hpp"

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
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

void check_cuda(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

struct Options {
  std::string mode = "valid";
  std::string fixture = "two-hidden-pairs";
  std::uint32_t iterations = 3U;
  std::uint32_t persistent_requests = 0U;
  std::uint64_t block = 0U;
  bool have_block = false;
  bool precision_hull_audit = false;
  std::string resolver_sha256 =
      "a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5"
      "a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5";
  std::string flint_sha256 =
      "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a"
      "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a";
};

bool is_lower_sha256(std::string_view value) {
  if (value.size() != 64U) return false;
  return std::all_of(
      value.begin(), value.end(), [](char character) {
        return (character >= '0' && character <= '9') ||
               (character >= 'a' && character <= 'f');
      });
}

std::uint64_t parse_u64(
    std::string_view value, std::string_view label) {
  if (value.empty()) {
    throw std::invalid_argument(std::string(label) + " is empty");
  }
  std::uint64_t result = 0U;
  const auto parsed =
      std::from_chars(value.data(), value.data() + value.size(), result);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != value.data() + value.size()) {
    throw std::invalid_argument(
        std::string(label) +
        " is not an unsigned decimal integer");
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--mode" && index + 1 < argc) {
      options.mode = argv[++index];
    } else if (argument == "--fixture" && index + 1 < argc) {
      options.fixture = argv[++index];
    } else if (argument == "--iterations" && index + 1 < argc) {
      const std::uint64_t value =
          parse_u64(argv[++index], "--iterations");
      if (value == 0U || value > 1'000U) {
        throw std::invalid_argument("--iterations is outside 1..1000");
      }
      options.iterations = static_cast<std::uint32_t>(value);
    } else if (argument == "--persistent-requests" &&
               index + 1 < argc) {
      if (options.persistent_requests != 0U) {
        throw std::invalid_argument(
            "--persistent-requests is duplicated");
      }
      const std::uint64_t value =
          parse_u64(argv[++index], "--persistent-requests");
      if (value == 0U || value > 1'000U) {
        throw std::invalid_argument(
            "--persistent-requests is outside 1..1000");
      }
      options.persistent_requests = static_cast<std::uint32_t>(value);
    } else if (argument == "--block" && index + 1 < argc) {
      if (options.have_block) {
        throw std::invalid_argument("--block is duplicated");
      }
      options.block = parse_u64(argv[++index], "--block");
      options.have_block = true;
    } else if (argument == "--resolver-sha256" && index + 1 < argc) {
      options.resolver_sha256 = argv[++index];
    } else if (argument == "--flint-sha256" && index + 1 < argc) {
      options.flint_sha256 = argv[++index];
    } else if (argument == "--precision-hull-audit") {
      if (options.precision_hull_audit) {
        throw std::invalid_argument(
            "--precision-hull-audit is duplicated");
      }
      options.precision_hull_audit = true;
    } else {
      throw std::invalid_argument(
          "usage: --mode valid|mutate-sample|mutate-candidate-order|"
          "mutate-root|mutate-refinement [--fixture "
          "two-hidden-pairs|turing-closure] [--iterations N] [--block N] "
          "[--persistent-requests N] "
          "[--resolver-sha256 HEX] [--flint-sha256 HEX] "
          "[--precision-hull-audit]");
    }
  }
  if (options.mode != "valid" && options.mode != "mutate-sample" &&
      options.mode != "mutate-candidate-order" &&
      options.mode != "mutate-root" &&
      options.mode != "mutate-refinement") {
    throw std::invalid_argument("unknown --mode");
  }
  if (options.fixture != "two-hidden-pairs" &&
      options.fixture != "turing-closure") {
    throw std::invalid_argument("unknown --fixture");
  }
  if (options.fixture == "two-hidden-pairs" && options.have_block) {
    throw std::invalid_argument(
        "--block is reserved for the turing-closure fixture");
  }
  if (options.block >= per::kSourceBlockCount) {
    throw std::invalid_argument("--block is outside the PT21 campaign");
  }
  if (options.fixture == "turing-closure" && options.have_block &&
      options.block != 0U) {
    throw std::invalid_argument(
        "the synthetic Turing-closure fixture is restricted to block zero");
  }
  if (options.persistent_requests != 0U &&
      (options.mode != "valid" ||
       options.fixture != "turing-closure" ||
       options.have_block)) {
    throw std::invalid_argument(
        "persistent mode requires the valid turing-closure fixture and "
        "receives blocks only from framed stdin");
  }
  if (!is_lower_sha256(options.resolver_sha256) ||
      !is_lower_sha256(options.flint_sha256) ||
      options.resolver_sha256 == std::string(64U, '0') ||
      options.flint_sha256 == std::string(64U, '0')) {
    throw std::invalid_argument(
        "resolver and FLINT identities must be nonzero lowercase SHA-256");
  }
  return options;
}

std::size_t at(std::int32_t offset) {
  return static_cast<std::size_t>(offset - pes::kRequiredLower);
}

std::vector<pw::RealDisk106> two_hidden_pairs_fixture() {
  std::vector<pw::RealDisk106> samples(
      sparkinterval::tg::platt_dd_transform::kSourceRequiredCount);
  const double radius = std::ldexp(1.0, -80);
  for (pw::RealDisk106& sample : samples) {
    sample = {{3.0, 0.0}, radius};
  }
  for (const std::int32_t left : {0, 10}) {
    samples[at(left)] = {{3.0, 0.0}, radius};
    samples[at(left + 1)] = {{1.0, 0.0}, radius};
    samples[at(left + 2)] = {{3.0, 0.0}, radius};
    samples[at(left + 3)] = {{-100.0, 0.0}, radius};
  }
  return samples;
}

std::vector<pw::RealDisk106> turing_closure_fixture() {
  // This is an explicitly synthetic finite fixture.  It has 3,465 direct
  // sign transitions and two source stationary candidates in the main
  // stream, hence 3,469 multiplicity slots.  The flank streams are constant.
  // At block zero that exact slot count closes against the genuine directed
  // Arb Turing-input computation; no count is injected or overridden.
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

sparkinterval::Sha256Digest parse_digest(std::string_view text) {
  if (!is_lower_sha256(text)) {
    throw std::invalid_argument("identity is not lowercase SHA-256");
  }
  sparkinterval::Sha256Digest result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    const auto nibble = [](char value) -> unsigned char {
      if (value >= '0' && value <= '9') {
        return static_cast<unsigned char>(value - '0');
      }
      return static_cast<unsigned char>(value - 'a' + 10);
    };
    result[index] = static_cast<unsigned char>(
        (nibble(text[2U * index]) << 4U) |
        nibble(text[2U * index + 1U]));
  }
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

constexpr std::array<unsigned char, 8> kPersistentRequestMagic{
    'P', 'T', '2', '1', 'J', 'R', 'Q', '1'};
constexpr std::array<unsigned char, 8> kPersistentResponseMagic{
    'P', 'T', '2', '1', 'J', 'R', 'S', '1'};
constexpr std::uint32_t kPersistentVersion = 1U;
constexpr std::uint32_t kPersistentRequestBytes = 24U;
constexpr std::uint32_t kPersistentResponseHeaderBytes = 40U;

std::uint32_t load_u32(const unsigned char* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t load_u64(const unsigned char* data) {
  std::uint64_t result = 0U;
  for (unsigned int index = 0U; index < 8U; ++index) {
    result |= static_cast<std::uint64_t>(data[index]) << (8U * index);
  }
  return result;
}

void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0U; index < 4U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void store_u64(unsigned char* data, std::uint64_t value) {
  for (unsigned int index = 0U; index < 8U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void read_exact(unsigned char* output, std::size_t size,
                std::string_view label) {
  std::cin.read(reinterpret_cast<char*>(output),
                static_cast<std::streamsize>(size));
  if (std::cin.gcount() != static_cast<std::streamsize>(size)) {
    throw std::runtime_error(std::string(label) + " is truncated");
  }
}

void write_exact(const unsigned char* data, std::size_t size,
                 std::string_view label) {
  std::cout.write(reinterpret_cast<const char*>(data),
                  static_cast<std::streamsize>(size));
  if (!std::cout) {
    throw std::runtime_error(std::string("cannot write ") +
                             std::string(label));
  }
}

void require_persistent_eof() {
  char trailing = '\0';
  std::cin.read(&trailing, 1);
  if (std::cin.gcount() != 0) {
    throw std::runtime_error(
        "persistent junction request stream has trailing bytes");
  }
  if (!std::cin.eof()) {
    throw std::runtime_error(
        "persistent junction request stream did not end cleanly");
  }
}

std::uint64_t read_persistent_block() {
  std::array<unsigned char, kPersistentRequestBytes> request{};
  read_exact(request.data(), request.size(), "persistent junction request");
  if (!std::equal(kPersistentRequestMagic.begin(),
                  kPersistentRequestMagic.end(), request.begin()) ||
      load_u32(request.data() + 8U) != kPersistentVersion ||
      load_u32(request.data() + 12U) != kPersistentRequestBytes) {
    throw std::runtime_error("persistent junction request header differs");
  }
  const std::uint64_t block = load_u64(request.data() + 16U);
  if (block >= per::kSourceBlockCount) {
    throw std::runtime_error(
        "persistent junction block leaves the PT21 campaign");
  }
  if (block != 0U) {
    throw std::runtime_error(
        "persistent synthetic junction is restricted to block zero");
  }
  return block;
}

void write_persistent_response(
    std::uint64_t block, const per::RawRecord& event_record,
    const psj::Result& result) {
  if (!result.accepted || result.failure_flags != 0U) {
    throw std::runtime_error(
        "persistent junction refuses a rejected finite result");
  }
  const std::string& trace = result.resolver_report.canonical_trace_json;
  if (trace.empty() ||
      trace.size() >
          std::numeric_limits<std::uint32_t>::max() -
              kPersistentResponseHeaderBytes -
              event_record.size() - result.record.size()) {
    throw std::runtime_error(
        "persistent junction trace leaves the response bound");
  }
  const std::uint32_t frame_bytes =
      kPersistentResponseHeaderBytes +
      static_cast<std::uint32_t>(event_record.size()) +
      static_cast<std::uint32_t>(result.record.size()) +
      static_cast<std::uint32_t>(trace.size());
  std::array<unsigned char, kPersistentResponseHeaderBytes> header{};
  std::copy(kPersistentResponseMagic.begin(),
            kPersistentResponseMagic.end(), header.begin());
  store_u32(header.data() + 8U, kPersistentVersion);
  store_u32(header.data() + 12U, frame_bytes);
  store_u64(header.data() + 16U, block);
  store_u32(header.data() + 24U,
            static_cast<std::uint32_t>(event_record.size()));
  store_u32(header.data() + 28U,
            static_cast<std::uint32_t>(result.record.size()));
  store_u32(header.data() + 32U,
            static_cast<std::uint32_t>(trace.size()));
  store_u32(header.data() + 36U, result.failure_flags);
  write_exact(header.data(), header.size(),
              "persistent junction response header");
  write_exact(event_record.data(), event_record.size(),
              "persistent event record");
  write_exact(result.record.data(), result.record.size(),
              "persistent stationary-junction record");
  write_exact(
      reinterpret_cast<const unsigned char*>(trace.data()), trace.size(),
      "persistent stationary trace");
  std::cout.flush();
  if (!std::cout) {
    throw std::runtime_error(
        "cannot flush persistent junction response");
  }
}

int run(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const std::vector<pw::RealDisk106> samples =
      options.fixture == "turing-closure"
          ? turing_closure_fixture()
          : two_hidden_pairs_fixture();
  pw::RealDisk106* device_samples = nullptr;
  pes::Workspace* workspace = nullptr;
  try {
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&device_samples),
                          samples.size() * sizeof(samples[0])),
               "allocate junction fixture");
    check_cuda(cudaMemcpy(device_samples, samples.data(),
                          samples.size() * sizeof(samples[0]),
                          cudaMemcpyHostToDevice),
               "copy junction fixture");
    workspace = pes::create_workspace();
    pes::scan_source_required_samples(workspace, device_samples);
    const auto cold_replay_started = std::chrono::steady_clock::now();
    const pes::ReplayReport cold_replay =
        pes::replay_and_check(workspace, device_samples);
    const double cold_scanner_replay_seconds =
        std::chrono::duration<double>(
            std::chrono::steady_clock::now() - cold_replay_started).count();
    const auto warm_replay_started = std::chrono::steady_clock::now();
    pes::ReplayReport replay =
        pes::replay_and_check(workspace, device_samples);
    const double warm_scanner_replay_seconds =
        std::chrono::duration<double>(
            std::chrono::steady_clock::now() - warm_replay_started).count();
    if (!cold_replay.accepted ||
        cold_replay.stationary_payload_sha256 !=
            replay.stationary_payload_sha256 ||
        std::memcmp(cold_replay.artifact.status.artifact_sha256,
                    replay.artifact.status.artifact_sha256, 32U) != 0) {
      throw std::runtime_error(
          "cold and warm scanner replay differ");
    }
    if (!replay.accepted) {
      throw std::runtime_error("event scanner fixture replay failed");
    }
    std::size_t candidates = 0U;
    for (const auto& stream : replay.artifact.stationary) {
      candidates += stream.size();
    }
    if (candidates != 2U) {
      throw std::runtime_error(
          "junction fixture does not have exactly two candidates");
    }
    if (options.fixture == "turing-closure") {
      if (replay.artifact.summaries[0].direct_event_count != 0U ||
          replay.artifact.summaries[1].direct_event_count != 3'465U ||
          replay.artifact.summaries[1].stationary_candidate_count != 2U ||
          replay.artifact.summaries[2].direct_event_count != 0U) {
        throw std::runtime_error(
            "synthetic Turing-closure fixture count geometry differs");
      }
    }

    const psj::IdentityPins identities{
        .resolver_sha256 = parse_digest(options.resolver_sha256),
        .flint_sha256 = parse_digest(options.flint_sha256),
    };
    sparkinterval::tg::platt_stationary_resolver::Options resolver_options;
    resolver_options.retain_precision_hull_audit =
        options.precision_hull_audit;
    if (options.persistent_requests != 0U) {
      for (std::uint32_t request = 0U;
           request < options.persistent_requests; ++request) {
        const std::uint64_t block = read_persistent_block();
        // Re-run the actual CUDA scanner for every request.  The device
        // allocation and source samples remain resident in this bounded
        // fixture, but no accepted response reuses a prior event scan.
        pes::scan_source_required_samples(workspace, device_samples);
        const pes::ReplayReport request_replay =
            pes::replay_and_check(workspace, device_samples);
        if (!request_replay.accepted ||
            request_replay.stationary_payload_sha256 !=
                replay.stationary_payload_sha256 ||
            std::memcmp(
                request_replay.artifact.status.artifact_sha256,
                replay.artifact.status.artifact_sha256, 32U) != 0) {
          throw std::runtime_error(
              "persistent CUDA scanner replay differs");
        }
        const per::RawRecord event_record =
            per::encode_record(event_values(block, request_replay));
        const psj::Result result = psj::resolve_replayed_block(
            block, event_record, request_replay, {}, identities,
            resolver_options);
        write_persistent_response(block, event_record, result);
      }
      require_persistent_eof();
      pes::destroy_workspace(workspace);
      workspace = nullptr;
      check_cuda(cudaFree(device_samples), "free junction fixture");
      device_samples = nullptr;
      return 0;
    }
    const std::vector<std::uint64_t> blocks =
        options.fixture == "turing-closure"
            ? std::vector<std::uint64_t>{options.block}
            : std::vector<std::uint64_t>{
                  0U, per::kSourceBlockCount / 2U,
                  per::kSourceBlockCount - 1U};
    psj::Result last;
    per::RawRecord last_event_record{};
    std::uint64_t accepted = 0U;
    const auto started = std::chrono::steady_clock::now();
    for (std::uint32_t iteration = 0U;
         iteration < options.iterations; ++iteration) {
      for (const std::uint64_t block : blocks) {
        pes::ReplayReport input = replay;
        per::BlockValues values = event_values(block, input);
        if (options.mode == "mutate-sample") {
          input.required_samples[0].center.hi =
              std::nextafter(input.required_samples[0].center.hi,
                             std::numeric_limits<double>::infinity());
        } else if (options.mode == "mutate-candidate-order") {
          std::swap(input.artifact.stationary[1][0],
                    input.artifact.stationary[1][1]);
        } else if (options.mode == "mutate-root") {
          values.event_artifact_sha256[0] ^= 0x80U;
        }
        const per::RawRecord event_record = per::encode_record(values);
        last_event_record = event_record;
        std::vector<
            sparkinterval::tg::platt_stationary_resolver::SparseRefinement>
            refinements;
        if (options.mode == "mutate-refinement") {
          refinements.push_back({1, "1 0", "1 0"});
        }
        last = psj::resolve_replayed_block(
            block, event_record, input, refinements, identities,
            resolver_options);
        if (last.accepted) ++accepted;
      }
    }
    const double seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    const std::uint64_t invocations =
        static_cast<std::uint64_t>(options.iterations) * blocks.size();
    const bool expected_acceptance = options.mode == "valid";
    const bool success =
        expected_acceptance ? accepted == invocations : accepted == 0U;
    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.platt-pt21-stationary-junction-benchmark.v1\""
              << ",\"test_success\":" << (success ? "true" : "false")
              << ",\"mode\":\"" << options.mode << "\""
              << ",\"fixture\":\"" << options.fixture << "\""
              << ",\"synthetic_finite_fixture\":true"
              << ",\"precision_hull_audit\":"
              << (options.precision_hull_audit ? "true" : "false")
              << ",\"accepted_records\":" << accepted
              << ",\"invocations\":" << invocations
              << ",\"first_interior_terminal_blocks\":["
              << blocks[0];
    for (std::size_t index = 1U; index < blocks.size(); ++index) {
      std::cout << ',' << blocks[index];
    }
    std::cout << ']'
              << ",\"candidate_count\":2"
              << ",\"resolved_multiplicity_slots_per_record\":4"
              << ",\"cold_scanner_replay_seconds\":"
              << cold_scanner_replay_seconds
              << ",\"warm_scanner_replay_seconds\":"
              << warm_scanner_replay_seconds
              << ",\"elapsed_seconds\":" << seconds
              << ",\"junctions_per_second\":"
              << static_cast<double>(invocations) / seconds
              << ",\"record_bytes\":" << psj::kRecordBytes
              << ",\"record_hex\":";
    if (last.accepted) {
      std::cout << '"' << hex(last.record) << '"';
    } else {
      std::cout << "null";
    }
    std::cout << ",\"event_record_hex\":";
    if (last.accepted) {
      std::cout << '"' << hex(last_event_record) << '"';
    } else {
      std::cout << "null";
    }
    std::cout << ",\"stationary_trace_hex\":";
    if (last.accepted) {
      std::cout << '"'
                << hex(last.resolver_report.canonical_trace_json) << '"';
    } else {
      std::cout << "null";
    }
    const sparkinterval::Sha256Digest sample_payload_sha256 =
        sparkinterval::sha256(samples.data(),
                              samples.size() * sizeof(samples[0]));
    std::cout << ",\"failure_flags\":" << last.failure_flags
              << ",\"required_sample_payload_sha256\":\""
              << hex(sample_payload_sha256) << "\""
              << ",\"resolver_sha256\":\""
              << options.resolver_sha256 << "\""
              << ",\"flint_sha256\":\""
              << options.flint_sha256 << "\""
              << ",\"hardy_z_endpoint_realization_proved\":false"
              << ",\"flint_to_mathlib_realization_proved\":false"
              << ",\"analytic_turing_realization_proved\":false"
              << ",\"pt21_source_claim_discharged\":false}\n";
    pes::destroy_workspace(workspace);
    check_cuda(cudaFree(device_samples), "free junction fixture");
    return success ? 0 : 1;
  } catch (...) {
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
    std::cerr << "sparkinterval-tg-platt-stationary-junction: "
              << error.what() << '\n';
    return 2;
  }
}

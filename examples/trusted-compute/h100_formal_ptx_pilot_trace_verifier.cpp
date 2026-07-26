// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Independent replay checker for h100_formal_ptx_pilot_workload.cpp.
// It never calls CUDA.  It checks the formal input, exact output bytes,
// retained strict-driver report, and the complete challenge/job-seeded trace.

#include "h100_formal_ptx_pilot_constants.hpp"
#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <fcntl.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr std::string_view kInitialDomain =
    "sparkinterval.measured-work-trace.h100-formal-ptx-pilot.initial.v1\n";
constexpr std::string_view kStepDomain =
    "sparkinterval.measured-work-trace.h100-formal-ptx-pilot.step.v1\n";

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

std::vector<unsigned char> read_file(const std::filesystem::path& path,
                                     std::size_t maximum) {
  const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (descriptor < 0) fail("cannot open " + path.string());
  struct stat metadata {};
  if (::fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_size < 0 ||
      static_cast<std::uintmax_t>(metadata.st_size) > maximum) {
    ::close(descriptor);
    fail("unbounded or non-regular verifier input: " + path.string());
  }
  std::vector<unsigned char> result(static_cast<std::size_t>(metadata.st_size));
  std::size_t offset = 0;
  while (offset < result.size()) {
    const ssize_t count =
        ::read(descriptor, result.data() + offset, result.size() - offset);
    if (count <= 0) {
      ::close(descriptor);
      fail("short read from " + path.string());
    }
    offset += static_cast<std::size_t>(count);
  }
  unsigned char extra = 0;
  if (::read(descriptor, &extra, 1) != 0 || ::close(descriptor) != 0) {
    fail("file changed while independently replayed: " + path.string());
  }
  return result;
}

std::string digest(const std::vector<unsigned char>& bytes) {
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
}

std::string digest(std::string_view bytes) {
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
}

bool lower_hex_digest(std::string_view value) {
  if (value.size() != 64U) return false;
  for (char byte : value) {
    if (!((byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f'))) {
      return false;
    }
  }
  return true;
}

std::string required_argument(int argc, char** argv, std::string_view name) {
  std::string result;
  for (int index = 1; index + 1 < argc; index += 2) {
    if (argv[index] == name) {
      if (!result.empty()) fail("duplicate argument " + std::string(name));
      result = argv[index + 1];
    }
  }
  if (result.empty()) fail("missing argument " + std::string(name));
  return result;
}

std::string_view expected_result_manifest() {
  return "{\"format\":\"sparkinterval_h100_formal_ptx_pilot_result_v1\","
         "\"hi\":\"3ff0000000000000\",\"lo\":\"3ff0000000000000\","
         "\"row_count\":1,\"schema_version\":1,\"status\":0,"
         "\"target\":\"sm_90\"}";
}

std::vector<unsigned char> expected_gpu_output() {
  std::vector<unsigned char> bytes(48, 0);
  const std::array<unsigned char, 8> magic = {'S', 'I', 'G', '6',
                                               '4', 'O', '0', '1'};
  std::copy(magic.begin(), magic.end(), bytes.begin());
  bytes[8] = 1;
  bytes[16] = 1;
  constexpr std::uint64_t one = 0x3ff0000000000000ULL;
  for (unsigned index = 0; index < 8; ++index) {
    bytes[24 + index] = static_cast<unsigned char>(one >> (8U * index));
    bytes[32 + index] = static_cast<unsigned char>(one >> (8U * index));
  }
  return bytes;
}

void require_driver_report(std::string_view report, std::string_view challenge,
                           std::string_view result_sha256) {
  if (report.empty() || report.back() != '\n' ||
      report.find('\n') != report.size() - 1) {
    fail("retained driver report is not one JSON line");
  }
  const std::array<std::string, 13> required = {
      "\"allow_other_device\":false",
      "\"compute_capability\":\"9.0\"",
      "\"device_count\":1",
      "\"device_name\":\"NVIDIA H100",
      "\"kind\":\"sparkinterval_generated_driver_run\"",
      "\"module_kind\":\"offline_cubin\"",
      "\"module_sha256\":\"" + std::string(h100_pilot::kCubinSha256) + "\"",
      "\"input_payload_sha256\":\"" +
          std::string(h100_pilot::kRowsPayloadSha256) + "\"",
      "\"output_file_sha256\":\"" + std::string(result_sha256) + "\"",
      "\"output_file_size_bytes\":48",
      "\"row_count\":1",
      "\"target\":\"sm_90\"",
      "\"challenge_nonce\":\"" + std::string(challenge) + "\"",
  };
  for (const auto& needle : required) {
    if (report.find(needle) == std::string_view::npos) {
      fail("retained driver report lacks an exact H100 execution binding");
    }
  }
}

std::string replay_chain(const std::string& challenge,
                         const std::string& job_binding,
                         const std::string& input_sha256,
                         const std::string& result_sha256,
                         const std::string& report_sha256) {
  const std::string initial =
      std::string(kInitialDomain) + "challenge_nonce=" + challenge + "\n" +
      "job_binding_sha256=" + job_binding + "\n" +
      "formal_batch_sha256=" + input_sha256 + "\n" +
      "formal_ptx_sha256=" + std::string(h100_pilot::kPtxSha256) + "\n" +
      "cubin_sha256=" + std::string(h100_pilot::kCubinSha256) + "\n" +
      "driver_sha256=" + std::string(h100_pilot::kDriverSha256) + "\n" +
      "result_sha256=" + result_sha256 + "\n" +
      "driver_report_sha256=" + report_sha256 + "\n";
  const std::string seed = digest(initial);
  return digest(std::string(kStepDomain) + "previous=" + seed + "\n" +
                "iteration=0\n" +
                "expected_interval=3ff0000000000000:3ff0000000000000\n" +
                "status=0\n");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 11) fail("expected exactly five named arguments");
    const std::string challenge = required_argument(argc, argv, "--challenge");
    const std::string job_binding =
        required_argument(argc, argv, "--job-binding");
    const std::filesystem::path input =
        required_argument(argc, argv, "--input");
    const std::filesystem::path result =
        required_argument(argc, argv, "--result");
    const std::filesystem::path trace =
        required_argument(argc, argv, "--trace");
    if (!lower_hex_digest(challenge) || !lower_hex_digest(job_binding)) {
      fail("challenge and job binding must be lowercase SHA-256 hex");
    }
    const auto input_bytes = read_file(input, 4096);
    const std::string input_sha256 = digest(input_bytes);
    if (input_bytes.size() != h100_pilot::kFormalBatchSize ||
        input_sha256 != h100_pilot::kFormalBatchSha256) {
      fail("formal ReferenceBatch differs from the pinned Lean input");
    }
    const auto result_bytes = read_file(result, 1024);
    if (std::string_view(reinterpret_cast<const char*>(result_bytes.data()),
                         result_bytes.size()) != expected_result_manifest()) {
      fail("result is not the exact UTF-8 one-row [1,1] result manifest");
    }
    const std::string result_sha256 = digest(result_bytes);
    if (result_sha256 != h100_pilot::kExpectedResultSha256) {
      fail("result digest differs from the build-time constant");
    }
    const auto raw_gpu_output = read_file(result.string() + ".gpu.raw", 1024);
    if (raw_gpu_output != expected_gpu_output() ||
        digest(raw_gpu_output) != h100_pilot::kExpectedGpuOutputSha256) {
      fail("retained raw GPU output failed independent byte-for-byte replay");
    }
    const auto stderr_bytes = read_file(result.string() + ".driver.stderr", 4096);
    if (!stderr_bytes.empty()) fail("retained generated-driver stderr is nonempty");
    const auto report_bytes =
        read_file(result.string() + ".driver.json", 16384);
    const std::string report(report_bytes.begin(), report_bytes.end());
    require_driver_report(report, challenge,
                          h100_pilot::kExpectedGpuOutputSha256);
    const std::string chain = replay_chain(challenge, job_binding, input_sha256,
                                           result_sha256, digest(report_bytes));
    const std::string expected_trace =
        "{\"algorithm_id\":\"" + std::string(h100_pilot::kAlgorithmId) +
        "\",\"challenge_nonce\":\"" + challenge +
        "\",\"input_sha256\":\"" + input_sha256 +
        "\",\"iteration_count\":1,\"job_binding_sha256\":\"" +
        job_binding +
        "\",\"kind\":\"sparkinterval_challenge_work_trace\","
        "\"result_sha256\":\"" + result_sha256 +
        "\",\"schema_version\":1,\"trace_sha256\":\"" + chain + "\"}";
    const auto trace_bytes = read_file(trace, 4096);
    if (std::string(trace_bytes.begin(), trace_bytes.end()) != expected_trace) {
      fail("challenge-bound work trace failed independent replay");
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Challenge-bound wrapper for the smallest formally modelled sm_90 program.
//
// The reviewed generated-driver binary is a separate, content-addressed
// closure member because it dynamically links the CUDA driver supplied by the
// measured Azure image.  This wrapper is a static ELF: it checks every fixed
// byte identity, invokes that exact driver without a shell, requires an H100
// success report, and emits the measured-runner result and work trace.

#include "h100_formal_ptx_pilot_constants.hpp"
#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr std::string_view kInitialDomain =
    "sparkinterval.measured-work-trace.h100-formal-ptx-pilot.initial.v1\n";
constexpr std::string_view kStepDomain =
    "sparkinterval.measured-work-trace.h100-formal-ptx-pilot.step.v1\n";
constexpr std::size_t kMaximumFileBytes = 64U * 1024U * 1024U;

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
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

std::vector<unsigned char> read_file(const std::filesystem::path& path,
                                     std::size_t maximum = kMaximumFileBytes) {
  const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (descriptor < 0) fail("cannot open " + path.string());
  struct stat metadata {};
  if (::fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_size < 0 ||
      static_cast<std::uintmax_t>(metadata.st_size) > maximum) {
    ::close(descriptor);
    fail("input is not a bounded regular file: " + path.string());
  }
  std::vector<unsigned char> result(static_cast<std::size_t>(metadata.st_size));
  std::size_t offset = 0;
  while (offset < result.size()) {
    const ssize_t count = ::read(descriptor, result.data() + offset,
                                 result.size() - offset);
    if (count <= 0) {
      ::close(descriptor);
      fail("short read from " + path.string());
    }
    offset += static_cast<std::size_t>(count);
  }
  unsigned char extra = 0;
  if (::read(descriptor, &extra, 1) != 0 || ::close(descriptor) != 0) {
    fail("file changed while read: " + path.string());
  }
  return result;
}

std::string digest(const std::vector<unsigned char>& bytes) {
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
}

std::string digest(std::string_view bytes) {
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
}

void write_exclusive(const std::filesystem::path& path,
                     const std::vector<unsigned char>& bytes) {
  const int descriptor = ::open(path.c_str(),
                                O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC |
                                    O_NOFOLLOW,
                                0600);
  if (descriptor < 0) fail("cannot exclusively create " + path.string());
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const ssize_t count = ::write(descriptor, bytes.data() + offset,
                                  bytes.size() - offset);
    if (count <= 0) {
      const int saved = errno;
      ::close(descriptor);
      errno = saved;
      fail("short write to " + path.string());
    }
    offset += static_cast<std::size_t>(count);
  }
  if (::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
    fail("cannot durably close " + path.string());
  }
}

void write_exclusive(const std::filesystem::path& path, std::string_view bytes) {
  write_exclusive(path,
                  std::vector<unsigned char>(bytes.begin(), bytes.end()));
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

void require_digest(const std::filesystem::path& path,
                    std::string_view expected, std::size_t expected_size) {
  const auto bytes = read_file(path);
  if (bytes.size() != expected_size || digest(bytes) != expected) {
    fail("content-addressed artifact mismatch: " + path.string());
  }
}

std::vector<unsigned char> expected_gpu_output() {
  std::vector<unsigned char> bytes(48, 0);
  const std::array<unsigned char, 8> magic = {'S', 'I', 'G', '6',
                                               '4', 'O', '0', '1'};
  std::copy(magic.begin(), magic.end(), bytes.begin());
  bytes[8] = 1;   // format version, little endian
  bytes[16] = 1;  // one row, little endian
  constexpr std::uint64_t one = 0x3ff0000000000000ULL;
  for (unsigned index = 0; index < 8; ++index) {
    bytes[24 + index] = static_cast<unsigned char>(one >> (8U * index));
    bytes[32 + index] = static_cast<unsigned char>(one >> (8U * index));
  }
  return bytes;
}

std::string_view expected_result_manifest() {
  return "{\"format\":\"sparkinterval_h100_formal_ptx_pilot_result_v1\","
         "\"hi\":\"3ff0000000000000\",\"lo\":\"3ff0000000000000\","
         "\"row_count\":1,\"schema_version\":1,\"status\":0,"
         "\"target\":\"sm_90\"}";
}

void require_report(std::string_view report, std::string_view challenge,
                    std::string_view output_sha256) {
  if (report.empty() || report.back() != '\n' ||
      report.find('\n') != report.size() - 1) {
    fail("generated driver did not emit exactly one JSON line");
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
      "\"output_file_sha256\":\"" + std::string(output_sha256) + "\"",
      "\"output_file_size_bytes\":48",
      "\"row_count\":1",
      "\"target\":\"sm_90\"",
      "\"challenge_nonce\":\"" + std::string(challenge) + "\"",
  };
  for (const auto& needle : required) {
    if (report.find(needle) == std::string_view::npos) {
      fail("generated driver report is missing a required H100 binding");
    }
  }
}

int invoke_driver(const std::string& challenge,
                  const std::filesystem::path& raw_output,
                  const std::filesystem::path& stdout_path,
                  const std::filesystem::path& stderr_path) {
  const std::string driver(h100_pilot::kDriverPath);
  const std::string cubin(h100_pilot::kCubinPath);
  const std::string rows(h100_pilot::kRowsPath);
  const std::string raw = raw_output.string();
  std::vector<std::string> arguments = {
      driver,
      "--cubin",
      cubin,
      "--input",
      rows,
      "--output",
      raw,
      "--expected-module-sha256",
      std::string(h100_pilot::kCubinSha256),
      "--expected-input-sha256",
      std::string(h100_pilot::kRowsPayloadSha256),
      "--target",
      "sm_90",
      "--challenge-nonce",
      challenge,
  };
  std::vector<char*> raw_arguments;
  for (std::string& item : arguments) raw_arguments.push_back(item.data());
  raw_arguments.push_back(nullptr);
  std::array<char*, 5> environment = {
      const_cast<char*>("LANG=C"), const_cast<char*>("LC_ALL=C"),
      const_cast<char*>("PATH=/usr/sbin:/usr/bin:/sbin:/bin"),
      const_cast<char*>("TZ=UTC"), nullptr};

  const pid_t child = ::fork();
  if (child < 0) fail("fork failed");
  if (child == 0) {
    const int stdout_fd = ::open(stdout_path.c_str(),
                                 O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW,
                                 0600);
    const int stderr_fd = ::open(stderr_path.c_str(),
                                 O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW,
                                 0600);
    if (stdout_fd < 0 || stderr_fd < 0 ||
        ::dup2(stdout_fd, STDOUT_FILENO) < 0 ||
        ::dup2(stderr_fd, STDERR_FILENO) < 0) {
      _exit(126);
    }
    ::close(stdout_fd);
    ::close(stderr_fd);
    ::execve(driver.c_str(), raw_arguments.data(), environment.data());
    _exit(127);
  }
  int status = 0;
  while (::waitpid(child, &status, 0) < 0) {
    if (errno != EINTR) fail("waitpid failed");
  }
  return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}

std::string trace_digest(const std::string& challenge,
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
  const std::string first = digest(initial);
  return digest(std::string(kStepDomain) + "previous=" + first + "\n" +
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
    require_digest(input, h100_pilot::kFormalBatchSha256,
                   h100_pilot::kFormalBatchSize);
    require_digest(h100_pilot::kCubinPath, h100_pilot::kCubinSha256,
                   h100_pilot::kCubinSize);
    require_digest(h100_pilot::kDriverPath, h100_pilot::kDriverSha256,
                   h100_pilot::kDriverSize);
    require_digest(h100_pilot::kRowsPath, h100_pilot::kRowsFileSha256,
                   h100_pilot::kRowsFileSize);

    const std::filesystem::path raw_output = result.string() + ".gpu.raw";
    const std::filesystem::path report_path = result.string() + ".driver.json";
    const std::filesystem::path stderr_path = result.string() + ".driver.stderr";
    if (std::filesystem::exists(raw_output) ||
        std::filesystem::exists(report_path) ||
        std::filesystem::exists(stderr_path)) {
      fail("fresh driver output paths already exist");
    }
    if (invoke_driver(challenge, raw_output, report_path, stderr_path) != 0) {
      fail("pinned generated driver rejected the H100 execution");
    }
    const auto stderr_bytes = read_file(stderr_path, 4096);
    if (!stderr_bytes.empty()) fail("generated driver emitted stderr");
    const auto expected = expected_gpu_output();
    const auto actual = read_file(raw_output, 1024);
    if (actual != expected) fail("H100 result differs from the formal pilot output");
    const std::string gpu_output_sha256 = digest(actual);
    if (gpu_output_sha256 != h100_pilot::kExpectedGpuOutputSha256) {
      fail("compiled raw GPU-result digest is inconsistent");
    }
    const auto report_bytes = read_file(report_path, 16384);
    const std::string report(report_bytes.begin(), report_bytes.end());
    require_report(report, challenge, gpu_output_sha256);
    const std::string_view result_manifest = expected_result_manifest();
    const std::string result_sha256 = digest(result_manifest);
    if (result_sha256 != h100_pilot::kExpectedResultSha256) {
      fail("compiled UTF-8 result-manifest digest is inconsistent");
    }
    write_exclusive(result, result_manifest);

    const std::string input_sha256 = digest(read_file(input));
    const std::string chain = trace_digest(
        challenge, job_binding, input_sha256, result_sha256, digest(report_bytes));
    const std::string trace_json =
        "{\"algorithm_id\":\"" + std::string(h100_pilot::kAlgorithmId) +
        "\",\"challenge_nonce\":\"" + challenge +
        "\",\"input_sha256\":\"" + input_sha256 +
        "\",\"iteration_count\":1,\"job_binding_sha256\":\"" +
        job_binding +
        "\",\"kind\":\"sparkinterval_challenge_work_trace\","
        "\"result_sha256\":\"" + result_sha256 +
        "\",\"schema_version\":1,\"trace_sha256\":\"" + chain + "\"}";
    write_exclusive(trace, trace_json);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}

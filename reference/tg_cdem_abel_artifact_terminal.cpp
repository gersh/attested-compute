// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Artifact-input terminal for the production CDEM Abel computation.
//
// The heavy producer emits one complete TG-CDEM-ABEL-ARTIFACT-V1 frame.  This
// separate, no-shell terminal parses that frame, checks its fixed production
// topology and reductions, and independently runs the reviewed chunk replayer
// for every one of its 1,000 rows.  It publishes the canonical registered
// result and a challenge/job-bound trace only after all child processes exit
// successfully with empty stderr and exact canonical stdout.
//
// This source is an operational implementation.  It is not a compiler,
// machine-code, or Lean refinement proof.

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <fcntl.h>
#include <filesystem>
#include <iostream>
#include <limits>
#include <map>
#include <mutex>
#include <spawn.h>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <utility>
#include <vector>

namespace {

using i128 = __int128;
using u128 = unsigned __int128;
namespace fs = std::filesystem;

constexpr std::string_view kAlgorithmId =
    "sparkinterval.ternary-goldbach.cdem-table-abel.artifact-terminal.v1";
constexpr std::string_view kArtifactHeader =
    "TG-CDEM-ABEL-ARTIFACT-V1\n"
    "invocation=cdem-table-abel-production-v2\n"
    "terminal=azure-sev-snp-cpu\n"
    "job={\"K\":199330,\"N\":5000000000,"
    "\"weight_scale\":1000000000000000000}\n";
constexpr std::string_view kResult =
    "2372685835387717172679029560108650251645442524";
constexpr std::string_view kResultSha256 =
    "84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c";
constexpr std::string_view kInitialDomain =
    "sparkinterval.measured-work-trace.cdem-abel-artifact-terminal.initial.v1\n";
constexpr std::string_view kStepDomain =
    "sparkinterval.measured-work-trace.cdem-abel-artifact-terminal.step.v1\n";
constexpr std::uint64_t kK = 199330;
constexpr std::uint64_t kN = 5000000000ULL;
constexpr std::uint64_t kBlockSize = 5000000ULL;
constexpr std::uint64_t kWeightScale = 1000000000000000000ULL;
constexpr std::size_t kChunkCount = 1000;
constexpr std::size_t kNaturalBytes = 32;
constexpr std::size_t kIntegerBytes = 33;
constexpr std::size_t kFixedBytes = 68;
constexpr std::size_t kChunkBytes = 195;
constexpr std::size_t kArtifactBytes =
    kArtifactHeader.size() + kFixedBytes + kChunkCount * kChunkBytes;
constexpr std::uint64_t kVariationTarget = 1678512305ULL;

constexpr std::array<unsigned char, 32> kSignedTargetBytes = {
    0xcc, 0x8f, 0x45, 0x20, 0x7a, 0x27, 0x01, 0x00};
constexpr std::array<unsigned char, 32> kAbsoluteTargetBytes = {
    0xbc, 0x98, 0x0e, 0x74, 0x5d, 0xf0, 0x23, 0x96, 0x50, 0x0a};

class TerminalError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

enum class Mode { kValidate, kRun, kVerifyTrace };

struct Options {
  Mode mode = Mode::kValidate;
  fs::path input;
  fs::path output;
  fs::path trace;
  fs::path scratch;
  fs::path replayer;
  std::string replayer_sha256;
  std::string challenge;
  std::string job_binding;
  unsigned workers = 64;
};

struct Chunk {
  std::uint64_t low = 0;
  std::uint64_t high = 0;
  std::int64_t before = 0;
  std::int64_t after = 0;
  i128 signed_upper = 0;
  u128 absolute_upper = 0;
  std::size_t wire_offset = 0;
};

struct Artifact {
  std::string bytes;
  std::string sha256;
  std::vector<Chunk> chunks;
};

struct ReplayObservation {
  std::string stdout_sha256;
  std::uint64_t variation = 0;
};

[[noreturn]] void fail(std::string message) {
  throw TerminalError(std::move(message));
}

std::string sha256(std::string_view bytes) {
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
}

bool isHex256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(value.begin(), value.end(), [](char c) {
           return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
         });
}

bool safeRelative(const fs::path& path) {
  if (path.empty() || path.is_absolute()) return false;
  for (const auto& part : path) {
    if (part.empty() || part == "." || part == "..") return false;
  }
  return path.generic_string() == path.string();
}

void requireSafeRelative(const fs::path& path, std::string_view label) {
  if (!safeRelative(path))
    fail(std::string(label) + " is not a safe relative path");
}

std::string readFile(const fs::path& path,
                     std::size_t maximum = 16 * 1024 * 1024) {
  const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (descriptor < 0) fail("cannot open regular file: " + path.string());
  struct stat before {};
  if (::fstat(descriptor, &before) != 0 || !S_ISREG(before.st_mode) ||
      before.st_nlink != 1 || before.st_size < 0 ||
      static_cast<std::uint64_t>(before.st_size) > maximum) {
    ::close(descriptor);
    fail("file is absent, linked, non-regular, or too large: " + path.string());
  }
  std::string result(static_cast<std::size_t>(before.st_size), '\0');
  std::size_t consumed = 0;
  while (consumed < result.size()) {
    const ssize_t count =
        ::read(descriptor, result.data() + consumed, result.size() - consumed);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) {
      ::close(descriptor);
      fail("short or failed read: " + path.string());
    }
    consumed += static_cast<std::size_t>(count);
  }
  char extra = 0;
  ssize_t trailing = 0;
  do {
    trailing = ::read(descriptor, &extra, 1);
  } while (trailing < 0 && errno == EINTR);
  struct stat after {};
  const bool stable =
      trailing == 0 && ::fstat(descriptor, &after) == 0 &&
      before.st_dev == after.st_dev && before.st_ino == after.st_ino &&
      before.st_mode == after.st_mode && before.st_nlink == after.st_nlink &&
      before.st_size == after.st_size &&
      before.st_mtim.tv_sec == after.st_mtim.tv_sec &&
      before.st_mtim.tv_nsec == after.st_mtim.tv_nsec &&
      before.st_ctim.tv_sec == after.st_ctim.tv_sec &&
      before.st_ctim.tv_nsec == after.st_ctim.tv_nsec;
  if (::close(descriptor) != 0 || !stable)
    fail("short or unstable read: " + path.string());
  return result;
}

void writeExclusive(const fs::path& path, std::string_view bytes,
                    mode_t mode = 0400) {
  if (!path.parent_path().empty()) {
    std::error_code error;
    fs::create_directories(path.parent_path(), error);
    if (error) fail("cannot create output parent: " + error.message());
  }
  const int descriptor =
      ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
             0600);
  if (descriptor < 0) fail("refusing non-fresh output: " + path.string());
  std::size_t written = 0;
  while (written < bytes.size()) {
    const ssize_t count =
        ::write(descriptor, bytes.data() + written, bytes.size() - written);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) {
      ::close(descriptor);
      fail("failed to write output: " + path.string());
    }
    written += static_cast<std::size_t>(count);
  }
  if (::fsync(descriptor) != 0 || ::fchmod(descriptor, mode) != 0 ||
      ::close(descriptor) != 0)
    fail("failed to seal output: " + path.string());
}

template <typename UInt>
bool parseUnsigned(std::string_view text, UInt& value) {
  if (text.empty() || (text.size() > 1 && text.front() == '0')) return false;
  UInt result = 0;
  const UInt maximum = ~static_cast<UInt>(0);
  for (char c : text) {
    if (c < '0' || c > '9') return false;
    const unsigned digit = static_cast<unsigned>(c - '0');
    if (result > (maximum - static_cast<UInt>(digit)) / 10) return false;
    result = result * 10 + digit;
  }
  value = result;
  return true;
}

std::string toString(u128 value) {
  if (value == 0) return "0";
  std::string result;
  while (value != 0) {
    result.push_back(static_cast<char>('0' + value % 10));
    value /= 10;
  }
  std::reverse(result.begin(), result.end());
  return result;
}

std::string toString(i128 value) {
  if (value >= 0) return toString(static_cast<u128>(value));
  const u128 magnitude = static_cast<u128>(-(value + 1)) + 1;
  return "-" + toString(magnitude);
}

bool checkedAdd(i128& total, i128 addend) {
  constexpr i128 maximum = static_cast<i128>((static_cast<u128>(1) << 127) - 1);
  constexpr i128 minimum = -maximum - 1;
  if ((addend > 0 && total > maximum - addend) ||
      (addend < 0 && total < minimum - addend))
    return false;
  total += addend;
  return true;
}

bool checkedAdd(u128& total, u128 addend) {
  const u128 maximum = ~static_cast<u128>(0);
  if (total > maximum - addend) return false;
  total += addend;
  return true;
}

u128 readNatural128(std::string_view bytes, std::size_t offset,
                    std::string_view label) {
  if (offset > bytes.size() || bytes.size() - offset < kNaturalBytes)
    fail(std::string(label) + " is truncated");
  for (std::size_t index = 16; index < kNaturalBytes; ++index)
    if (static_cast<unsigned char>(bytes[offset + index]) != 0)
      fail(std::string(label) + " exceeds uint128");
  u128 result = 0;
  for (std::size_t index = 0; index < 16; ++index)
    result |= static_cast<u128>(
                  static_cast<unsigned char>(bytes[offset + index]))
              << (8 * index);
  return result;
}

std::uint64_t readNatural64(std::string_view bytes, std::size_t offset,
                            std::string_view label) {
  const u128 value = readNatural128(bytes, offset, label);
  if (value > std::numeric_limits<std::uint64_t>::max())
    fail(std::string(label) + " exceeds uint64");
  return static_cast<std::uint64_t>(value);
}

i128 readInteger128(std::string_view bytes, std::size_t offset,
                    std::string_view label) {
  if (offset >= bytes.size()) fail(std::string(label) + " is truncated");
  const unsigned char sign = static_cast<unsigned char>(bytes[offset]);
  if (sign > 1) fail(std::string(label) + " has an unknown sign");
  const u128 magnitude = readNatural128(bytes, offset + 1, label);
  if (sign == 1 && magnitude == 0)
    fail(std::string(label) + " is negative zero");
  const u128 positive_max = (static_cast<u128>(1) << 127) - 1;
  const u128 negative_max = static_cast<u128>(1) << 127;
  if ((sign == 0 && magnitude > positive_max) ||
      (sign == 1 && magnitude > negative_max))
    fail(std::string(label) + " exceeds int128");
  return sign == 0 ? static_cast<i128>(magnitude)
                   : -static_cast<i128>(magnitude - 1) - 1;
}

std::int64_t readInteger64(std::string_view bytes, std::size_t offset,
                           std::string_view label) {
  const i128 value = readInteger128(bytes, offset, label);
  if (value < std::numeric_limits<std::int64_t>::min() ||
      value > std::numeric_limits<std::int64_t>::max())
    fail(std::string(label) + " exceeds int64");
  return static_cast<std::int64_t>(value);
}

std::uint32_t readU32(std::string_view bytes, std::size_t offset,
                      std::string_view label) {
  if (offset > bytes.size() || bytes.size() - offset < 4)
    fail(std::string(label) + " is truncated");
  std::uint32_t value = 0;
  for (std::size_t index = 0; index < 4; ++index)
    value |= static_cast<std::uint32_t>(
                 static_cast<unsigned char>(bytes[offset + index]))
             << (8 * index);
  return value;
}

bool targetBytesEqual(std::string_view bytes, std::size_t offset,
                      const std::array<unsigned char, 32>& expected) {
  if (offset > bytes.size() || bytes.size() - offset < expected.size())
    return false;
  for (std::size_t index = 0; index < expected.size(); ++index)
    if (static_cast<unsigned char>(bytes[offset + index]) != expected[index])
      return false;
  return true;
}

Artifact parseArtifact(std::string bytes) {
  if (bytes.size() != kArtifactBytes)
    fail("artifact byte length is not the exact production frame length");
  if (std::string_view(bytes).substr(0, kArtifactHeader.size()) !=
      kArtifactHeader)
    fail("artifact header differs");
  std::size_t offset = kArtifactHeader.size();
  if (!targetBytesEqual(bytes, offset, kSignedTargetBytes))
    fail("artifact signed target differs");
  offset += kNaturalBytes;
  if (!targetBytesEqual(bytes, offset, kAbsoluteTargetBytes))
    fail("artifact absolute target differs");
  offset += kNaturalBytes;
  if (readU32(bytes, offset, "chunk count") != kChunkCount)
    fail("artifact must contain exactly 1,000 rows");
  offset += 4;

  std::vector<Chunk> chunks;
  chunks.reserve(kChunkCount);
  std::uint64_t expected_low = 1;
  std::int64_t expected_before = 0;
  i128 signed_total = 0;
  u128 absolute_total = 0;
  for (std::size_t index = 0; index < kChunkCount; ++index) {
    const std::size_t row_offset = offset;
    Chunk chunk;
    chunk.wire_offset = row_offset;
    chunk.low = readNatural64(bytes, offset, "chunk low");
    offset += kNaturalBytes;
    chunk.high = readNatural64(bytes, offset, "chunk high");
    offset += kNaturalBytes;
    chunk.before = readInteger64(bytes, offset, "chunk before");
    offset += kIntegerBytes;
    chunk.after = readInteger64(bytes, offset, "chunk after");
    offset += kIntegerBytes;
    chunk.signed_upper =
        readInteger128(bytes, offset, "chunk signed upper");
    offset += kIntegerBytes;
    chunk.absolute_upper =
        readNatural128(bytes, offset, "chunk absolute upper");
    offset += kNaturalBytes;
    const std::uint64_t expected_high =
        std::min(kN, expected_low + kBlockSize - 1);
    if (chunk.low != expected_low || chunk.high != expected_high)
      fail("artifact row topology differs at index " + std::to_string(index));
    if (chunk.before != expected_before)
      fail("artifact incoming state is discontinuous at index " +
           std::to_string(index));
    if (!checkedAdd(signed_total, chunk.signed_upper) ||
        !checkedAdd(absolute_total, chunk.absolute_upper))
      fail("artifact row reduction overflows");
    expected_low = chunk.high + 1;
    expected_before = chunk.after;
    chunks.push_back(chunk);
  }
  u128 absolute_target = 0;
  if (!parseUnsigned(std::string_view("48710223109607260068028"),
                     absolute_target))
    fail("internal absolute target is malformed");
  if (offset != bytes.size() || expected_low != kN + 1)
    fail("artifact does not cover the complete production endpoint");
  if (expected_before != 112)
    fail("artifact final floor state differs");
  if (signed_total != static_cast<i128>(324880457633740LL))
    fail("artifact signed row reduction differs");
  if (absolute_total != absolute_target)
    fail("artifact absolute row reduction differs");
  return {bytes, sha256(bytes), std::move(chunks)};
}

std::string expectedReplay(const Chunk& chunk, std::uint64_t variation) {
  return "SCHEMA=CDEM_ABEL_CHUNK_REPLAY_V1\nK=" + std::to_string(kK) +
         "\nLOW=" + std::to_string(chunk.low) +
         "\nHIGH=" + std::to_string(chunk.high) +
         "\nBEFORE=" + std::to_string(chunk.before) +
         "\nDELTA_SUM=" +
         toString(static_cast<i128>(chunk.after) - chunk.before) +
         "\nAFTER=" + std::to_string(chunk.after) +
         "\nU_INC_UPPER_NUM=" + toString(chunk.signed_upper) +
         "\nV_INC_UPPER_NUM=" + toString(chunk.absolute_upper) +
         "\nTOTAL_VARIATION=" + std::to_string(variation) +
         "\nWEIGHT_SCALE=" + std::to_string(kWeightScale) + "\n";
}

ReplayObservation validateReplay(std::string_view stdout_bytes,
                                 std::string_view stderr_bytes,
                                 const Chunk& chunk) {
  if (!stderr_bytes.empty()) fail("chunk replayer emitted stderr");
  const std::string marker = "\nTOTAL_VARIATION=";
  const std::size_t marker_offset = stdout_bytes.find(marker);
  if (marker_offset == std::string_view::npos ||
      stdout_bytes.find(marker, marker_offset + 1) != std::string_view::npos)
    fail("chunk replayer output has a malformed variation field");
  const std::size_t value_start = marker_offset + marker.size();
  const std::size_t value_end = stdout_bytes.find('\n', value_start);
  if (value_end == std::string_view::npos)
    fail("chunk replayer variation field is unterminated");
  std::uint64_t variation = 0;
  if (!parseUnsigned(stdout_bytes.substr(value_start, value_end - value_start),
                     variation))
    fail("chunk replayer variation is not canonical uint64");
  const std::string expected = expectedReplay(chunk, variation);
  if (stdout_bytes != expected)
    fail("chunk replayer stdout differs from the exact canonical row");
  return {sha256(stdout_bytes), variation};
}

int runChild(const fs::path& executable,
             const std::vector<std::string>& arguments,
             const fs::path& stdout_path, const fs::path& stderr_path) {
  const int stdout_fd =
      ::open(stdout_path.c_str(),
             O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (stdout_fd < 0) return -1;
  const int stderr_fd =
      ::open(stderr_path.c_str(),
             O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (stderr_fd < 0) {
    ::close(stdout_fd);
    return -1;
  }
  posix_spawn_file_actions_t actions;
  if (posix_spawn_file_actions_init(&actions) != 0) {
    ::close(stdout_fd);
    ::close(stderr_fd);
    fail("posix_spawn file-action initialization failed");
  }
  const bool action_failed =
      posix_spawn_file_actions_adddup2(&actions, stdout_fd, STDOUT_FILENO) !=
          0 ||
      posix_spawn_file_actions_adddup2(&actions, stderr_fd, STDERR_FILENO) !=
          0 ||
      posix_spawn_file_actions_addclose(&actions, stdout_fd) != 0 ||
      posix_spawn_file_actions_addclose(&actions, stderr_fd) != 0;
  if (action_failed) {
    posix_spawn_file_actions_destroy(&actions);
    ::close(stdout_fd);
    ::close(stderr_fd);
    fail("posix_spawn file-action construction failed");
  }
  std::vector<std::string> storage;
  storage.reserve(arguments.size() + 1);
  storage.push_back(executable.string());
  storage.insert(storage.end(), arguments.begin(), arguments.end());
  std::vector<char*> argv;
  argv.reserve(storage.size() + 1);
  for (auto& item : storage) argv.push_back(item.data());
  argv.push_back(nullptr);
  std::array<std::string, 4> environment_storage = {
      "LANG=C", "LC_ALL=C", "PATH=/usr/bin:/bin", "TZ=UTC"};
  std::array<char*, 5> environment = {
      environment_storage[0].data(), environment_storage[1].data(),
      environment_storage[2].data(), environment_storage[3].data(), nullptr};
  pid_t pid = -1;
  const int spawned =
      posix_spawn(&pid, executable.c_str(), &actions, nullptr, argv.data(),
                  environment.data());
  posix_spawn_file_actions_destroy(&actions);
  ::close(stdout_fd);
  ::close(stderr_fd);
  if (spawned != 0) return -1;
  int status = 0;
  while (::waitpid(pid, &status, 0) < 0) {
    if (errno != EINTR) return -1;
  }
  return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

std::string computeTrace(const Options& options, const Artifact& artifact,
                         std::string_view replayer_sha256,
                         const std::vector<ReplayObservation>& observations) {
  if (observations.size() != artifact.chunks.size())
    fail("trace input does not cover every artifact row");
  std::string current =
      sha256(std::string(kInitialDomain) +
             "challenge_nonce=" + options.challenge + "\n" +
             "job_binding_sha256=" + options.job_binding + "\n" +
             "artifact_sha256=" + artifact.sha256 + "\n" +
             "replayer_executable_sha256=" + std::string(replayer_sha256) +
             "\n");
  for (std::size_t index = 0; index < artifact.chunks.size(); ++index) {
    const Chunk& chunk = artifact.chunks[index];
    const std::string row_sha =
        sha256(std::string_view(artifact.bytes).substr(chunk.wire_offset,
                                                       kChunkBytes));
    current =
        sha256(std::string(kStepDomain) + "previous=" + current + "\n" +
               "chunk_index=" + std::to_string(index) + "\n" +
               "artifact_row_sha256=" + row_sha + "\n" +
               "replay_stdout_sha256=" +
               observations[index].stdout_sha256 + "\n");
  }
  return sha256(std::string(kStepDomain) + "previous=" + current + "\n" +
                "total_variation=" + std::to_string(kVariationTarget) + "\n" +
                "result_sha256=" + std::string(kResultSha256) + "\n");
}

std::string traceJson(const Options& options, const Artifact& artifact,
                      std::string_view replayer_sha256,
                      std::string_view trace_sha256) {
  (void)replayer_sha256;
  return "{\"algorithm_id\":\"" + std::string(kAlgorithmId) +
         "\",\"challenge_nonce\":\"" + options.challenge +
         "\",\"input_sha256\":\"" + artifact.sha256 +
         "\",\"iteration_count\":1001,\"job_binding_sha256\":\"" +
         options.job_binding +
         "\",\"kind\":\"sparkinterval_challenge_work_trace\","
         "\"result_sha256\":\"" + std::string(kResultSha256) +
         "\",\"schema_version\":1,\"trace_sha256\":\"" +
         std::string(trace_sha256) + "\"}";
}

std::vector<ReplayObservation> readReplayObservations(
    const fs::path& scratch, const Artifact& artifact) {
  std::vector<ReplayObservation> observations;
  observations.reserve(kChunkCount);
  std::uint64_t variation_total = 0;
  for (std::size_t index = 0; index < kChunkCount; ++index) {
    const fs::path stdout_path =
        scratch / ("replay-" + std::to_string(index) + ".stdout");
    const fs::path stderr_path =
        scratch / ("replay-" + std::to_string(index) + ".stderr");
    ReplayObservation observation =
        validateReplay(readFile(stdout_path, 4096), readFile(stderr_path, 4096),
                       artifact.chunks[index]);
    if (observation.variation >
        std::numeric_limits<std::uint64_t>::max() - variation_total)
      fail("replay variation reduction overflows");
    variation_total += observation.variation;
    observations.push_back(std::move(observation));
  }
  if (variation_total != kVariationTarget)
    fail("replay variation reduction differs");
  return observations;
}

Options parseOptions(int argc, char** argv) {
  if (argc < 2) fail("first argument must select a terminal mode");
  Options result;
  const std::string_view mode(argv[1]);
  if (mode == "--validate-artifact")
    result.mode = Mode::kValidate;
  else if (mode == "--run")
    result.mode = Mode::kRun;
  else if (mode == "--verify-trace")
    result.mode = Mode::kVerifyTrace;
  else
    fail("first argument must be --validate-artifact, --run, or --verify-trace");
  std::map<std::string, std::string> values;
  for (int index = 2; index < argc; index += 2) {
    if (index + 1 >= argc ||
        !std::string_view(argv[index]).starts_with("--"))
      fail("arguments must be exact --name value pairs");
    if (!values.emplace(argv[index], argv[index + 1]).second)
      fail("duplicate terminal option");
  }
  if (result.mode == Mode::kValidate) {
    if (values.size() != 1 || !values.contains("--input"))
      fail("artifact validation requires only --input");
    result.input = values["--input"];
    requireSafeRelative(result.input, "input");
    return result;
  }
  const std::vector<std::string> common = {
      "--challenge",       "--input",   "--job-binding",
      "--output",          "--replayer-sha256",
      "--scratch",         "--trace"};
  for (const auto& name : common)
    if (!values.contains(name)) fail("missing terminal option: " + name);
  const std::size_t expected =
      common.size() + (result.mode == Mode::kRun ? 2 : 0);
  if (values.size() != expected) fail("unexpected terminal option");
  result.challenge = values["--challenge"];
  result.input = values["--input"];
  result.job_binding = values["--job-binding"];
  result.output = values["--output"];
  result.replayer_sha256 = values["--replayer-sha256"];
  result.scratch = values["--scratch"];
  result.trace = values["--trace"];
  if (!isHex256(result.challenge) || !isHex256(result.job_binding) ||
      !isHex256(result.replayer_sha256))
    fail("challenge, job binding, and replayer pin must be lowercase SHA-256");
  for (const auto& [path, label] :
       std::array<std::pair<fs::path, std::string_view>, 4>{
           {{result.input, "input"},
            {result.output, "output"},
            {result.scratch, "scratch"},
            {result.trace, "trace"}}})
    requireSafeRelative(path, label);
  if (result.input == result.output || result.input == result.trace ||
      result.output == result.trace)
    fail("input, output, and trace paths must be distinct");
  if (result.mode == Mode::kRun) {
    result.replayer = values["--replayer"];
    requireSafeRelative(result.replayer, "replayer");
    std::uint64_t workers = 0;
    if (!parseUnsigned(std::string_view(values["--workers"]), workers) ||
        workers != 64)
      fail("production artifact terminal requires exactly 64 workers");
    result.workers = static_cast<unsigned>(workers);
  }
  return result;
}

void runTerminal(const Options& options) {
  const Artifact artifact = parseArtifact(readFile(options.input, kArtifactBytes));
  if (fs::exists(options.output) || fs::exists(options.trace) ||
      fs::exists(options.scratch))
    fail("terminal destinations must all be fresh");
  const std::string replayer_bytes = readFile(options.replayer, 64 * 1024 * 1024);
  if (sha256(replayer_bytes) != options.replayer_sha256)
    fail("chunk replayer executable differs from its measured pin");
  if (!fs::create_directories(options.scratch))
    fail("cannot create fresh terminal scratch directory");
  const fs::path captured_replayer = options.scratch / "reviewed-replayer";
  writeExclusive(captured_replayer, replayer_bytes, 0500);

  std::atomic<std::size_t> next{0};
  std::atomic<bool> failed{false};
  std::mutex error_mutex;
  std::string error_message;
  auto worker = [&]() {
    while (!failed.load()) {
      const std::size_t index = next.fetch_add(1);
      if (index >= artifact.chunks.size()) return;
      const Chunk& chunk = artifact.chunks[index];
      const fs::path stdout_path =
          options.scratch / ("replay-" + std::to_string(index) + ".stdout");
      const fs::path stderr_path =
          options.scratch / ("replay-" + std::to_string(index) + ".stderr");
      try {
        const int status =
            runChild(captured_replayer,
                     {std::to_string(kK), std::to_string(chunk.low),
                      std::to_string(chunk.high),
                      std::to_string(chunk.before)},
                     stdout_path, stderr_path);
        if (status != 0)
          fail("chunk replayer exited unsuccessfully");
        (void)validateReplay(readFile(stdout_path, 4096),
                             readFile(stderr_path, 4096), chunk);
      } catch (const std::exception& error) {
        failed.store(true);
        std::lock_guard<std::mutex> lock(error_mutex);
        if (error_message.empty())
          error_message = "independent replay failed at row " +
                          std::to_string(index) + ": " + error.what();
        return;
      }
    }
  };
  std::vector<std::thread> threads;
  threads.reserve(options.workers);
  for (unsigned index = 0; index < options.workers; ++index)
    threads.emplace_back(worker);
  for (auto& thread : threads) thread.join();
  if (failed.load())
    fail(error_message.empty() ? "independent replay failed" : error_message);

  const auto observations = readReplayObservations(options.scratch, artifact);
  if (readFile(captured_replayer, 64 * 1024 * 1024) != replayer_bytes)
    fail("captured chunk replayer changed during terminal execution");
  const std::string trace_hash =
      computeTrace(options, artifact, options.replayer_sha256, observations);
  const std::string trace =
      traceJson(options, artifact, options.replayer_sha256, trace_hash);
  // Publish the result last: a failure while sealing the trace cannot leave
  // behind a canonical successful result.
  writeExclusive(options.trace, trace);
  writeExclusive(options.output, kResult);
}

void verifyTrace(const Options& options) {
  const Artifact artifact = parseArtifact(readFile(options.input, kArtifactBytes));
  const std::string output = readFile(options.output, 1024);
  if (output != kResult || sha256(output) != kResultSha256)
    fail("registered result differs during trace verification");
  const fs::path captured_replayer = options.scratch / "reviewed-replayer";
  if (sha256(readFile(captured_replayer, 64 * 1024 * 1024)) !=
      options.replayer_sha256)
    fail("captured chunk replayer differs during trace verification");
  const auto observations = readReplayObservations(options.scratch, artifact);
  const std::string expected =
      traceJson(options, artifact, options.replayer_sha256,
                computeTrace(options, artifact, options.replayer_sha256,
                             observations));
  if (readFile(options.trace, 4096) != expected)
    fail("challenge/job-bound artifact-terminal trace differs");
}

void validateArtifactOnly(const Options& options) {
  const Artifact artifact = parseArtifact(readFile(options.input, kArtifactBytes));
  std::cout
      << "{\"artifact_sha256\":\"" << artifact.sha256
      << "\",\"chunk_count\":1000,"
         "\"mode\":\"non_authorizing_artifact_validation\","
         "\"source_claim_ready\":false}\n";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parseOptions(argc, argv);
    if (options.mode == Mode::kValidate)
      validateArtifactOnly(options);
    else if (options.mode == Mode::kRun)
      runTerminal(options);
    else
      verifyTrace(options);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "tg_cdem_abel_artifact_terminal: " << error.what() << '\n';
    return 2;
  }
}

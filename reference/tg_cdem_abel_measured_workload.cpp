// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Closed, no-shell measured-workload supervisor for the production CDEM Abel
// computation.  This executable is built statically beside the separately
// reviewed producer and chunk replayer.  It runs the complete N=5e9 producer,
// checks every deterministic field, independently replays all 1,000 chunks,
// emits the exact registered Nat.pair result, and constructs a challenge-bound
// SHA-256 trace.  --verify-trace independently checks the retained transcript,
// replay manifest, result, and trace without re-running the expensive scan.

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <spawn.h>
#include <sstream>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

#include "sparkinterval/sha256.hpp"

extern char** environ;

namespace {

using u128 = unsigned __int128;
using i128 = __int128;

constexpr std::string_view kAlgorithmId =
    "sparkinterval.ternary-goldbach.cdem-table-abel.v2";
constexpr std::string_view kInput =
    "{\"K\":199330,\"N\":5000000000,\"weight_scale\":1000000000000000000}";
constexpr std::string_view kResult =
    "2372685835387717172679029560108650251645442524";
constexpr std::string_view kResultSha256 =
    "84e7c2b56de45b48776e4239bfc82e80ef5c80940f232b83c85eefc44648b73c";
constexpr std::string_view kInputSha256 =
    "f14d4dd60e39b2b4f655d3b82333659167d78246de8c5aab923db8a69347742a";
constexpr std::string_view kInitialDomain =
    "sparkinterval.measured-work-trace.cdem-abel.initial.v1\n";
constexpr std::string_view kStepDomain =
    "sparkinterval.measured-work-trace.cdem-abel.step.v1\n";
constexpr std::uint64_t kK = 199330;
constexpr std::uint64_t kN = 5000000000ULL;
constexpr std::uint64_t kBlockSize = 5000000ULL;
constexpr std::size_t kChunkCount = 1000;
constexpr std::uint64_t kWeightScale = 1000000000000000000ULL;
constexpr std::size_t kTraceIterations = 1002;
constexpr std::string_view kArtifactHeader =
    "TG-CDEM-ABEL-ARTIFACT-V1\n"
    "invocation=cdem-table-abel-production-v2\n"
    "terminal=azure-sev-snp-cpu\n"
    "job={\"K\":199330,\"N\":5000000000,"
    "\"weight_scale\":1000000000000000000}\n";

struct Options {
  bool verify = false;
  std::filesystem::path producer;
  std::filesystem::path replayer;
  std::string challenge;
  std::string job_binding;
  std::filesystem::path input;
  std::filesystem::path output;
  std::filesystem::path trace;
  std::filesystem::path transcript;
  std::filesystem::path replay_manifest;
  std::filesystem::path artifact;
  unsigned workers = 64;
};

struct Chunk {
  std::uint64_t low = 0;
  std::uint64_t high = 0;
  std::int64_t before = 0;
  std::int64_t after = 0;
  i128 upper_u = 0;
  u128 upper_v = 0;
  std::uint64_t variation = 0;
  std::string row;
};

[[noreturn]] void fail(const std::string& message) {
  std::cerr << message << '\n';
  std::exit(2);
}

bool isHex256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(value.begin(), value.end(), [](char c) {
           return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
         });
}

bool safeRelative(const std::filesystem::path& path) {
  if (path.empty() || path.is_absolute()) return false;
  for (const auto& part : path) {
    if (part.empty() || part == "." || part == "..") return false;
  }
  return path.generic_string() == path.string();
}

void requireSafeRelative(const std::filesystem::path& path,
                         const char* label) {
  if (!safeRelative(path)) fail(std::string(label) + " is not a safe relative path");
}

std::string readFile(const std::filesystem::path& path,
                     std::size_t maximum = 16 * 1024 * 1024) {
  const int descriptor =
      ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
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

void writeExclusive(const std::filesystem::path& path, std::string_view bytes,
                    mode_t mode = 0400) {
  if (!path.parent_path().empty()) {
    std::error_code error;
    std::filesystem::create_directories(path.parent_path(), error);
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

std::string sha256(std::string_view bytes) {
  return sparkinterval::sha256_hex(bytes.data(), bytes.size());
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

void appendNatural256(std::string& output, u128 value) {
  for (unsigned index = 0; index < 32; ++index) {
    output.push_back(static_cast<char>(value & 0xffU));
    value >>= 8;
  }
}

void appendNatural32(std::string& output, std::uint32_t value) {
  for (unsigned index = 0; index < 4; ++index) {
    output.push_back(static_cast<char>(value & 0xffU));
    value >>= 8;
  }
}

void appendInteger256(std::string& output, i128 value) {
  const bool negative = value < 0;
  const u128 magnitude =
      negative ? static_cast<u128>(-(value + 1)) + 1
               : static_cast<u128>(value);
  output.push_back(static_cast<char>(negative ? 1 : 0));
  appendNatural256(output, magnitude);
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

bool parseSigned128(std::string_view text, i128& value) {
  const bool negative = !text.empty() && text.front() == '-';
  const std::string_view magnitude = negative ? text.substr(1) : text;
  if (magnitude.empty() || (negative && magnitude == "0")) return false;
  u128 parsed = 0;
  if (!parseUnsigned(magnitude, parsed)) return false;
  const u128 positive_max = (static_cast<u128>(1) << 127) - 1;
  const u128 negative_max = static_cast<u128>(1) << 127;
  if ((!negative && parsed > positive_max) || (negative && parsed > negative_max))
    return false;
  value = negative ? -static_cast<i128>(parsed - 1) - 1
                   : static_cast<i128>(parsed);
  return true;
}

bool parseInt64(std::string_view text, std::int64_t& value) {
  i128 parsed = 0;
  if (!parseSigned128(text, parsed) ||
      parsed < std::numeric_limits<std::int64_t>::min() ||
      parsed > std::numeric_limits<std::int64_t>::max())
    return false;
  value = static_cast<std::int64_t>(parsed);
  return true;
}

std::vector<std::string_view> split(std::string_view value, char delimiter) {
  std::vector<std::string_view> result;
  std::size_t start = 0;
  for (;;) {
    const std::size_t found = value.find(delimiter, start);
    if (found == std::string_view::npos) {
      result.push_back(value.substr(start));
      return result;
    }
    result.push_back(value.substr(start, found - start));
    start = found + 1;
  }
}

std::map<std::string, std::string> parseFields(const std::string& text) {
  if (text.empty() || text.back() != '\n' || text.find('\r') != std::string::npos)
    fail("transcript is not canonical LF-terminated text");
  std::map<std::string, std::string> fields;
  std::size_t start = 0;
  while (start < text.size()) {
    const std::size_t end = text.find('\n', start);
    if (end == std::string::npos || end == start) fail("empty transcript line");
    const std::string_view line(text.data() + start, end - start);
    const std::size_t equal = line.find('=');
    if (equal == std::string_view::npos || equal == 0 || equal + 1 == line.size())
      fail("transcript line is not KEY=VALUE");
    const std::string key(line.substr(0, equal));
    const std::string value(line.substr(equal + 1));
    if (!fields.emplace(key, value).second) fail("duplicate transcript key: " + key);
    start = end + 1;
  }
  return fields;
}

void requireField(const std::map<std::string, std::string>& fields,
                  std::string_view name, std::string_view expected) {
  const auto found = fields.find(std::string(name));
  if (found == fields.end() || found->second != expected)
    fail("CDEM field differs: " + std::string(name));
}

std::vector<Chunk> validateTranscript(const std::string& transcript) {
  const auto fields = parseFields(transcript);
  const std::array<std::pair<std::string_view, std::string_view>, 20> fixed = {{
      {"K", "199330"},
      {"N", "5000000000"},
      {"A", "5000000001"},
      {"MOBIUS_M", "-6"},
      {"MOBIUS_Q", "121174"},
      {"COEFF_SCALE", "1000000000000000000000000000000"},
      {"S_LOWER_NUM", "20985957655978471021715"},
      {"S_UPPER_NUM", "20985957655978471142885"},
      {"FINAL_F", "112"},
      {"FINAL_G", "111"},
      {"TOTAL_VARIATION", "1678512305"},
      {"WEIGHT_SCALE", "1000000000000000000"},
      {"U_INC_UPPER_NUM", "324880457633740"},
      {"V_INC_UPPER_NUM", "48710223109607260068028"},
      {"ENDPOINT_RSQRT_UPPER_NUM", "14142135622317"},
      {"CHUNK_COUNT", "1000"},
      {"THREADS", "64"},
      {"BLOCK_SIZE", "5000000"},
      {"FILL_SECONDS", ""},
      {"SCAN_SECONDS", ""},
  }};
  for (const auto& [name, expected] : fixed) {
    if (expected.empty()) {
      const auto found = fields.find(std::string(name));
      if (found == fields.end() || found->second.empty() ||
          found->second.find_first_not_of("0123456789.") != std::string::npos)
        fail("invalid timing field: " + std::string(name));
    } else {
      requireField(fields, name, expected);
    }
  }
  if (fields.size() != kChunkCount + fixed.size() + 1)
    fail("CDEM transcript has missing or unexpected fields");

  std::vector<Chunk> chunks;
  chunks.reserve(kChunkCount);
  std::uint64_t expected_low = 1;
  std::int64_t expected_before = 0;
  i128 total_u = 0;
  u128 total_v = 0;
  std::uint64_t total_variation = 0;
  std::string chunk_manifest;
  for (std::size_t index = 0; index < kChunkCount; ++index) {
    const std::string key = "CHUNK_" + std::to_string(index);
    const auto found = fields.find(key);
    if (found == fields.end()) fail("missing " + key);
    const auto pieces = split(found->second, ',');
    if (pieces.size() != 7) fail("malformed " + key);
    Chunk chunk;
    u128 parsed_v = 0;
    if (!parseUnsigned(pieces[0], chunk.low) ||
        !parseUnsigned(pieces[1], chunk.high) ||
        !parseInt64(pieces[2], chunk.before) ||
        !parseInt64(pieces[3], chunk.after) ||
        !parseSigned128(pieces[4], chunk.upper_u) ||
        !parseUnsigned(pieces[5], parsed_v) ||
        !parseUnsigned(pieces[6], chunk.variation))
      fail("out-of-range or non-canonical " + key);
    chunk.upper_v = parsed_v;
    const std::uint64_t expected_high =
        std::min(kN, expected_low + kBlockSize - 1);
    if (chunk.low != expected_low || chunk.high != expected_high ||
        chunk.before != expected_before)
      fail("range or prefix discontinuity in " + key);
    expected_low = chunk.high + 1;
    expected_before = chunk.after;
    if (!checkedAdd(total_u, chunk.upper_u) ||
        !checkedAdd(total_v, chunk.upper_v))
      fail("CDEM chunk reduction overflow");
    if (std::numeric_limits<std::uint64_t>::max() - total_variation <
        chunk.variation)
      fail("variation reduction overflow");
    total_variation += chunk.variation;
    chunk.row = found->second;
    chunk_manifest += key + "=" + found->second + "\n";
    chunks.push_back(std::move(chunk));
  }
  u128 expected_total_v = 0;
  if (!parseUnsigned(std::string_view("48710223109607260068028"), expected_total_v))
    fail("internal CDEM V target is malformed");
  if (expected_low != kN + 1 || expected_before != 112 ||
      total_u != static_cast<i128>(324880457633740LL) ||
      total_v != expected_total_v ||
      total_variation != 1678512305ULL)
    fail("CDEM chunk reductions differ");
  requireField(fields, "CHUNK_MANIFEST_SHA256", sha256(chunk_manifest));
  return chunks;
}

std::string artifactBytes(const std::vector<Chunk>& chunks) {
  if (chunks.size() != kChunkCount)
    fail("CDEM artifact does not cover every production chunk");
  std::string result(kArtifactHeader);
  result.reserve(kArtifactHeader.size() + 68 + chunks.size() * 195);
  appendNatural256(result, static_cast<u128>(324880457633740ULL));
  u128 absolute_target = 0;
  if (!parseUnsigned(std::string_view("48710223109607260068028"),
                     absolute_target))
    fail("internal CDEM artifact target is malformed");
  appendNatural256(result, absolute_target);
  appendNatural32(result, static_cast<std::uint32_t>(chunks.size()));
  for (const auto& chunk : chunks) {
    appendNatural256(result, static_cast<u128>(chunk.low));
    appendNatural256(result, static_cast<u128>(chunk.high));
    appendInteger256(result, static_cast<i128>(chunk.before));
    appendInteger256(result, static_cast<i128>(chunk.after));
    appendInteger256(result, chunk.upper_u);
    appendNatural256(result, chunk.upper_v);
  }
  return result;
}

std::string expectedReplay(const Chunk& chunk) {
  const i128 delta = static_cast<i128>(chunk.after) - chunk.before;
  auto signedString = [](i128 value) {
    if (value == 0) return std::string("0");
    const bool negative = value < 0;
    u128 magnitude = negative ? static_cast<u128>(-(value + 1)) + 1
                              : static_cast<u128>(value);
    std::string result;
    while (magnitude != 0) {
      result.push_back(static_cast<char>('0' + magnitude % 10));
      magnitude /= 10;
    }
    if (negative) result.push_back('-');
    std::reverse(result.begin(), result.end());
    return result;
  };
  auto unsignedString = [](u128 value) {
    if (value == 0) return std::string("0");
    std::string result;
    while (value != 0) {
      result.push_back(static_cast<char>('0' + value % 10));
      value /= 10;
    }
    std::reverse(result.begin(), result.end());
    return result;
  };
  return "SCHEMA=CDEM_ABEL_CHUNK_REPLAY_V1\nK=199330\nLOW=" +
         std::to_string(chunk.low) + "\nHIGH=" + std::to_string(chunk.high) +
         "\nBEFORE=" + std::to_string(chunk.before) + "\nDELTA_SUM=" +
         signedString(delta) + "\nAFTER=" + std::to_string(chunk.after) +
         "\nU_INC_UPPER_NUM=" + signedString(chunk.upper_u) +
         "\nV_INC_UPPER_NUM=" + unsignedString(chunk.upper_v) +
         "\nTOTAL_VARIATION=" + std::to_string(chunk.variation) +
         "\nWEIGHT_SCALE=1000000000000000000\n";
}

int runChild(const std::filesystem::path& executable,
             const std::vector<std::string>& arguments,
             const std::filesystem::path& stdout_path,
             const std::filesystem::path& stderr_path) {
  const int stdout_fd = ::open(stdout_path.c_str(),
                               O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                               0600);
  if (stdout_fd < 0) return -1;
  const int stderr_fd = ::open(stderr_path.c_str(),
                               O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                               0600);
  if (stderr_fd < 0) {
    ::close(stdout_fd);
    return -1;
  }
  posix_spawn_file_actions_t actions;
  if (posix_spawn_file_actions_init(&actions) != 0) fail("posix_spawn init failed");
  const bool action_failed =
      posix_spawn_file_actions_adddup2(&actions, stdout_fd, STDOUT_FILENO) != 0 ||
      posix_spawn_file_actions_adddup2(&actions, stderr_fd, STDERR_FILENO) != 0 ||
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
  pid_t pid = -1;
  const int spawned = posix_spawn(&pid, executable.c_str(), &actions, nullptr,
                                  argv.data(), environ);
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

std::string computeTrace(const Options& options, const std::string& transcript,
                         const std::string& artifact,
                         const std::vector<Chunk>& chunks,
                         const std::vector<std::string>& replay_hashes) {
  if (chunks.size() != kChunkCount || replay_hashes.size() != kChunkCount)
    fail("trace inputs do not cover all chunks");
  std::string current = sha256(std::string(kInitialDomain) +
                               "challenge_nonce=" + options.challenge + "\n" +
                               "job_binding_sha256=" + options.job_binding + "\n" +
                               "input_sha256=" + std::string(kInputSha256) + "\n");
  current = sha256(std::string(kStepDomain) + "previous=" + current + "\n" +
                   "producer_sha256=" + sha256(transcript) + "\n");
  for (std::size_t index = 0; index < chunks.size(); ++index) {
    current = sha256(std::string(kStepDomain) + "previous=" + current + "\n" +
                     "chunk_index=" + std::to_string(index) + "\n" +
                     "chunk_row=" + chunks[index].row + "\n" +
                     "replay_sha256=" + replay_hashes[index] + "\n");
  }
  return sha256(std::string(kStepDomain) + "previous=" + current + "\n" +
                "artifact_sha256=" + sha256(artifact) + "\n" +
                "result_sha256=" + std::string(kResultSha256) + "\n");
}

std::string traceJson(const Options& options, const std::string& artifact_sha256,
                      const std::string& trace_sha256) {
  return "{\"algorithm_id\":\"" + std::string(kAlgorithmId) +
         "\",\"artifact_sha256\":\"" + artifact_sha256 +
         "\",\"challenge_nonce\":\"" + options.challenge +
         "\",\"input_sha256\":\"" + std::string(kInputSha256) +
         "\",\"iteration_count\":" + std::to_string(kTraceIterations) +
         ",\"job_binding_sha256\":\"" + options.job_binding +
         "\",\"kind\":\"sparkinterval_challenge_work_trace\","
         "\"result_sha256\":\"" + std::string(kResultSha256) +
         "\",\"schema_version\":1,\"trace_sha256\":\"" + trace_sha256 +
         "\"}";
}

std::vector<std::string> validateReplayManifest(
    const std::string& manifest, const std::vector<Chunk>& chunks) {
  std::vector<std::string> hashes;
  hashes.reserve(kChunkCount);
  std::size_t start = 0;
  for (std::size_t index = 0; index < kChunkCount; ++index) {
    const std::size_t end = manifest.find('\n', start);
    if (end == std::string::npos) fail("truncated replay manifest");
    const std::string expected_prefix = std::to_string(index) + ":";
    const std::string_view line(manifest.data() + start, end - start);
    if (!line.starts_with(expected_prefix)) fail("replay manifest index differs");
    const std::string digest(line.substr(expected_prefix.size()));
    if (!isHex256(digest) || digest != sha256(expectedReplay(chunks[index])))
      fail("replay manifest output digest differs");
    hashes.push_back(digest);
    start = end + 1;
  }
  if (start != manifest.size()) fail("replay manifest has extra rows");
  return hashes;
}

Options parseOptions(int argc, char** argv) {
  if (argc < 2) fail("missing --run or --verify-trace");
  Options result;
  if (std::string_view(argv[1]) == "--run") {
    result.verify = false;
  } else if (std::string_view(argv[1]) == "--verify-trace") {
    result.verify = true;
  } else {
    fail("first argument must be --run or --verify-trace");
  }
  std::map<std::string, std::string> values;
  for (int index = 2; index < argc; index += 2) {
    if (index + 1 >= argc || std::string_view(argv[index]).find("--") != 0)
      fail("arguments must be exact --name value pairs");
    if (!values.emplace(argv[index], argv[index + 1]).second)
      fail("duplicate workload option");
  }
  const std::vector<std::string> common = {
      "--artifact", "--challenge", "--input", "--job-binding", "--output",
      "--replay-manifest", "--trace", "--transcript"};
  for (const auto& name : common)
    if (!values.contains(name)) fail("missing workload option: " + name);
  if (!result.verify) {
    for (const auto& name : {"--producer", "--replayer", "--workers"})
      if (!values.contains(name)) fail("missing workload option: " + std::string(name));
  }
  const std::size_t expected = common.size() + (result.verify ? 0 : 3);
  if (values.size() != expected) fail("unexpected workload option");
  result.challenge = values["--challenge"];
  result.job_binding = values["--job-binding"];
  result.input = values["--input"];
  result.output = values["--output"];
  result.trace = values["--trace"];
  result.transcript = values["--transcript"];
  result.replay_manifest = values["--replay-manifest"];
  result.artifact = values["--artifact"];
  if (!result.verify) {
    result.producer = values["--producer"];
    result.replayer = values["--replayer"];
    std::uint64_t workers = 0;
    if (!parseUnsigned(std::string_view(values["--workers"]), workers) ||
        workers != 64)
      fail("production CDEM workload requires exactly 64 replay workers");
    result.workers = static_cast<unsigned>(workers);
  }
  if (!isHex256(result.challenge) || !isHex256(result.job_binding))
    fail("challenge and job binding must be lowercase SHA-256 hex");
  for (const auto& [path, label] :
       std::array<std::pair<std::filesystem::path, const char*>, 6>{{
           {result.input, "input"}, {result.output, "output"},
           {result.trace, "trace"}, {result.transcript, "transcript"},
           {result.replay_manifest, "replay manifest"},
           {result.artifact, "artifact"}}})
    requireSafeRelative(path, label);
  if (!result.verify) {
    requireSafeRelative(result.producer, "producer");
    requireSafeRelative(result.replayer, "replayer");
  }
  return result;
}

void runWorkload(const Options& options) {
  const std::string input = readFile(options.input, 1024);
  if (input != kInput || sha256(input) != kInputSha256) fail("registered input differs");
  if (std::filesystem::exists(options.output) || std::filesystem::exists(options.trace) ||
      std::filesystem::exists(options.transcript) ||
      std::filesystem::exists(options.replay_manifest) ||
      std::filesystem::exists(options.artifact))
    fail("one or more measured destinations are not fresh");
  const std::filesystem::path work = options.transcript.parent_path();
  if (work.empty() || std::filesystem::exists(work))
    fail("CDEM work directory must be a fresh non-root path");
  if (!std::filesystem::create_directories(work)) fail("cannot create CDEM work directory");

  const std::filesystem::path producer_stderr = work / "producer.stderr";
  const int producer_status = runChild(
      options.producer,
      {"199330", "5000000000", "5000000"},
      options.transcript,
      producer_stderr);
  if (producer_status != 0 || !readFile(producer_stderr).empty())
    fail("CDEM producer failed or emitted stderr");
  const std::string transcript = readFile(options.transcript);
  const std::vector<Chunk> chunks = validateTranscript(transcript);

  std::vector<std::string> replay_hashes(kChunkCount);
  std::atomic<std::size_t> next{0};
  std::atomic<bool> failed{false};
  std::mutex error_mutex;
  std::string error_message;
  auto worker = [&]() {
    while (!failed.load()) {
      const std::size_t index = next.fetch_add(1);
      if (index >= chunks.size()) return;
      const auto& chunk = chunks[index];
      const std::string stem = "replay-" + std::to_string(index);
      const auto stdout_path = work / (stem + ".stdout");
      const auto stderr_path = work / (stem + ".stderr");
      const int status = runChild(
          options.replayer,
          {"199330", std::to_string(chunk.low), std::to_string(chunk.high),
           std::to_string(chunk.before)},
          stdout_path,
          stderr_path);
      const std::string stderr_bytes = readFile(stderr_path);
      const std::string stdout_bytes = readFile(stdout_path);
      if (status != 0 || !stderr_bytes.empty() || stdout_bytes != expectedReplay(chunk)) {
        failed.store(true);
        std::lock_guard<std::mutex> lock(error_mutex);
        if (error_message.empty())
          error_message = "independent CDEM replay failed at chunk " +
                          std::to_string(index);
        return;
      }
      replay_hashes[index] = sha256(stdout_bytes);
    }
  };
  std::vector<std::thread> threads;
  for (unsigned index = 0; index < options.workers; ++index)
    threads.emplace_back(worker);
  for (auto& thread : threads) thread.join();
  if (failed.load() || next.load() < chunks.size())
    fail(error_message.empty() ? "incomplete independent CDEM replay" : error_message);

  std::string manifest;
  for (std::size_t index = 0; index < replay_hashes.size(); ++index)
    manifest += std::to_string(index) + ":" + replay_hashes[index] + "\n";
  writeExclusive(options.replay_manifest, manifest);
  const std::string artifact = artifactBytes(chunks);
  writeExclusive(options.artifact, artifact);
  writeExclusive(options.output, kResult);
  const std::string trace_hash =
      computeTrace(options, transcript, artifact, chunks, replay_hashes);
  writeExclusive(
      options.trace, traceJson(options, sha256(artifact), trace_hash));
}

void verifyTrace(const Options& options) {
  const std::string input = readFile(options.input, 1024);
  const std::string output = readFile(options.output, 1024);
  if (input != kInput || sha256(input) != kInputSha256 || output != kResult ||
      sha256(output) != kResultSha256)
    fail("registered input or output differs during trace verification");
  const std::string transcript = readFile(options.transcript);
  const auto chunks = validateTranscript(transcript);
  const std::string artifact = readFile(options.artifact);
  if (artifact != artifactBytes(chunks))
    fail("retained CDEM artifact differs from the checked transcript");
  const auto hashes =
      validateReplayManifest(readFile(options.replay_manifest), chunks);
  const std::string expected =
      traceJson(options, sha256(artifact),
                computeTrace(options, transcript, artifact, chunks, hashes));
  if (readFile(options.trace) != expected)
    fail("challenge-dependent CDEM work trace differs");
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parseOptions(argc, argv);
  if (options.verify)
    verifyTrace(options);
  else
    runWorkload(options);
  return 0;
}

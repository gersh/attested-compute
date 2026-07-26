// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// A deliberately small, dependency-free measured-workload example.
//
// The mathematical result is written as canonical decimal bytes with no
// trailing newline.  A separate canonical JSON trace is seeded by both the
// relying-party challenge and the measured-runner job binding, and is updated
// once per loop iteration.  The trace is freshness evidence for the measured
// executable; it is not, by itself, a proof that an unmeasured executable ran.

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>

namespace {

constexpr std::string_view kAlgorithmId =
    "sparkinterval.example.cubic-sum-div-three.v1";
constexpr std::string_view kTraceInitialDomain =
    "sparkinterval.measured-work-trace.cubic-sum-div-three.initial.v1\n";
constexpr std::string_view kTraceStepDomain =
    "sparkinterval.measured-work-trace.cubic-sum-div-three.step.v1\n";

constexpr std::array<std::uint32_t, 64> kSha256RoundConstants = {
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU,
    0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U, 0xd807aa98U, 0x12835b01U,
    0x243185beU, 0x550c7dc3U, 0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U,
    0xc19bf174U, 0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
    0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU, 0x983e5152U,
    0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U,
    0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU,
    0x53380d13U, 0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U, 0xd192e819U,
    0xd6990624U, 0xf40e3585U, 0x106aa070U, 0x19a4c116U, 0x1e376c08U,
    0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU,
    0x682e6ff3U, 0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U};

constexpr std::uint32_t rotate_right(std::uint32_t value, unsigned amount) {
  return (value >> amount) | (value << (32U - amount));
}

class Sha256 {
 public:
  Sha256()
      : state_{0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
               0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U} {}

  void update(std::string_view data) {
    for (unsigned char byte : data) {
      buffer_[buffer_size_++] = byte;
      ++byte_count_;
      if (buffer_size_ == buffer_.size()) {
        transform(buffer_.data());
        buffer_size_ = 0;
      }
    }
  }

  std::array<std::uint8_t, 32> finish() {
    const std::uint64_t bit_count = byte_count_ * 8U;
    buffer_[buffer_size_++] = 0x80U;
    if (buffer_size_ > 56U) {
      while (buffer_size_ < 64U) buffer_[buffer_size_++] = 0;
      transform(buffer_.data());
      buffer_size_ = 0;
    }
    while (buffer_size_ < 56U) buffer_[buffer_size_++] = 0;
    for (unsigned offset = 0; offset < 8U; ++offset) {
      buffer_[63U - offset] =
          static_cast<std::uint8_t>(bit_count >> (offset * 8U));
    }
    transform(buffer_.data());
    std::array<std::uint8_t, 32> digest{};
    for (unsigned word = 0; word < state_.size(); ++word) {
      for (unsigned byte = 0; byte < 4U; ++byte) {
        digest[word * 4U + byte] = static_cast<std::uint8_t>(
            state_[word] >> ((3U - byte) * 8U));
      }
    }
    return digest;
  }

 private:
  void transform(const std::uint8_t* block) {
    std::array<std::uint32_t, 64> words{};
    for (unsigned index = 0; index < 16U; ++index) {
      words[index] = (static_cast<std::uint32_t>(block[index * 4U]) << 24U) |
                     (static_cast<std::uint32_t>(block[index * 4U + 1U]) << 16U) |
                     (static_cast<std::uint32_t>(block[index * 4U + 2U]) << 8U) |
                     static_cast<std::uint32_t>(block[index * 4U + 3U]);
    }
    for (unsigned index = 16U; index < 64U; ++index) {
      const std::uint32_t s0 = rotate_right(words[index - 15U], 7U) ^
                               rotate_right(words[index - 15U], 18U) ^
                               (words[index - 15U] >> 3U);
      const std::uint32_t s1 = rotate_right(words[index - 2U], 17U) ^
                               rotate_right(words[index - 2U], 19U) ^
                               (words[index - 2U] >> 10U);
      words[index] = words[index - 16U] + s0 + words[index - 7U] + s1;
    }
    std::uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
    std::uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];
    for (unsigned index = 0; index < 64U; ++index) {
      const std::uint32_t s1 =
          rotate_right(e, 6U) ^ rotate_right(e, 11U) ^ rotate_right(e, 25U);
      const std::uint32_t choose = (e & f) ^ ((~e) & g);
      const std::uint32_t temporary1 =
          h + s1 + choose + kSha256RoundConstants[index] + words[index];
      const std::uint32_t s0 =
          rotate_right(a, 2U) ^ rotate_right(a, 13U) ^ rotate_right(a, 22U);
      const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
      const std::uint32_t temporary2 = s0 + majority;
      h = g;
      g = f;
      f = e;
      e = d + temporary1;
      d = c;
      c = b;
      b = a;
      a = temporary1 + temporary2;
    }
    state_[0] += a;
    state_[1] += b;
    state_[2] += c;
    state_[3] += d;
    state_[4] += e;
    state_[5] += f;
    state_[6] += g;
    state_[7] += h;
  }

  std::array<std::uint32_t, 8> state_;
  std::array<std::uint8_t, 64> buffer_{};
  std::size_t buffer_size_ = 0;
  std::uint64_t byte_count_ = 0;
};

std::string sha256(std::string_view value) {
  Sha256 hasher;
  hasher.update(value);
  const auto bytes = hasher.finish();
  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (std::uint8_t byte : bytes) output << std::setw(2) << unsigned(byte);
  return output.str();
}

bool is_lower_hex_digest(const std::string& value) {
  if (value.size() != 64U) return false;
  for (char character : value) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

std::string read_exact_input(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open input");
  std::ostringstream buffer;
  buffer << input.rdbuf();
  if (!input.good() && !input.eof()) throw std::runtime_error("cannot read input");
  return buffer.str();
}

void write_exclusive(const std::string& path, std::string_view bytes) {
  const int descriptor =
      ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
  if (descriptor < 0) {
    throw std::runtime_error("cannot exclusively create output: " +
                             std::string(std::strerror(errno)));
  }
  std::size_t written = 0;
  while (written < bytes.size()) {
    const ssize_t count =
        ::write(descriptor, bytes.data() + written, bytes.size() - written);
    if (count < 0) {
      const int saved = errno;
      ::close(descriptor);
      throw std::runtime_error("cannot write output: " +
                               std::string(std::strerror(saved)));
    }
    written += static_cast<std::size_t>(count);
  }
  if (::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
    throw std::runtime_error("cannot durably close output");
  }
}

std::string required_argument(int argc, char** argv, std::string_view name) {
  for (int index = 1; index + 1 < argc; index += 2) {
    if (argv[index] == name) return argv[index + 1];
  }
  throw std::runtime_error("missing argument " + std::string(name));
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 11) throw std::runtime_error("expected exactly five named arguments");
    const std::string challenge = required_argument(argc, argv, "--challenge");
    const std::string job_binding = required_argument(argc, argv, "--job-binding");
    const std::string input_path = required_argument(argc, argv, "--input");
    const std::string result_path = required_argument(argc, argv, "--result");
    const std::string trace_path = required_argument(argc, argv, "--trace");
    if (!is_lower_hex_digest(challenge) || !is_lower_hex_digest(job_binding)) {
      throw std::runtime_error("challenge and job binding must be lowercase SHA-256 hex");
    }
    const std::string input = read_exact_input(input_path);
    if (input != "20000") {
      throw std::runtime_error("this closed executable accepts only canonical input 20000");
    }
    const std::string input_sha256 = sha256(input);
    std::string trace = sha256(std::string(kTraceInitialDomain) +
                               "challenge_nonce=" + challenge + "\n" +
                               "job_binding_sha256=" + job_binding + "\n" +
                               "input_sha256=" + input_sha256 + "\n");
    std::uint64_t accumulator = 0;
    for (std::uint64_t x = 0; x <= 20000U; ++x) {
      if (x != 0 && x > std::numeric_limits<std::uint64_t>::max() / x / x) {
        throw std::runtime_error("cube overflow");
      }
      const std::uint64_t cube = x * x * x;
      if (accumulator > std::numeric_limits<std::uint64_t>::max() - cube) {
        throw std::runtime_error("accumulator overflow");
      }
      accumulator += cube;
      trace = sha256(std::string(kTraceStepDomain) + "previous=" + trace + "\n" +
                     "x=" + std::to_string(x) + "\n" +
                     "accumulator=" + std::to_string(accumulator) + "\n");
    }
    if (accumulator % 3U != 0U) throw std::runtime_error("non-integral result");
    const std::string result = std::to_string(accumulator / 3U);
    if (result != "13334666700000000") {
      throw std::runtime_error("closed computation returned the wrong value");
    }
    write_exclusive(result_path, result);
    const std::string result_sha256 = sha256(result);
    const std::string trace_json =
        "{\"algorithm_id\":\"" + std::string(kAlgorithmId) +
        "\",\"challenge_nonce\":\"" + challenge +
        "\",\"input_sha256\":\"" + input_sha256 +
        "\",\"iteration_count\":20001,\"job_binding_sha256\":\"" +
        job_binding +
        "\",\"kind\":\"sparkinterval_challenge_work_trace\","
        "\"result_sha256\":\"" + result_sha256 +
        "\",\"schema_version\":1,\"trace_sha256\":\"" + trace + "\"}";
    write_exclusive(trace_path, trace_json);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "cubic_sum_div_three_20000: " << error.what() << '\n';
    return 2;
  }
}

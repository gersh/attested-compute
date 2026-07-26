// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Produce the four rigorous Arb inputs used by each of the two one-sided
// Turing calls in the pinned PT21 windowed zeta computation.
//
// This deliberately does not consume a zero/event stream and does not claim
// the analytic Turing theorem.  It closes the smaller numerical boundary:
// for block j it evaluates the source formulas on exactly
//
//   turing_min: [10^10 + 1008j - 21, 10^10 + 1008j]
//   turing_max: [10^10 + 1008(j+1), 10^10 + 1008(j+1) + 21].
//
// The exact-rational construction now lives in
// `reference/tg_platt_pt21_turing_inputs_core.cpp` so that the fused source
// worker can call the identical code in process.  This translation unit keeps
// the one-shot and persistent request framing and remains the independent
// reference producer.

#include "sparkinterval/tg_platt_pt21_turing_inputs.hpp"

#include <flint/flint.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>

namespace pti = sparkinterval::tg::platt_pt21_turing_inputs;

namespace {

struct Options {
  std::uint64_t block = 0;
  std::string required_sign_packet_sha256;
  bool have_block = false;
  bool have_packet_sha256 = false;
  std::uint32_t persistent_requests = 0;
};

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

std::uint64_t parse_u64(std::string_view value, std::string_view label) {
  if (value.empty()) fail(std::string(label) + " is empty");
  std::uint64_t result = 0;
  const auto parsed =
      std::from_chars(value.data(), value.data() + value.size(), result);
  if (parsed.ec != std::errc() || parsed.ptr != value.data() + value.size()) {
    fail(std::string(label) + " is not an unsigned decimal integer");
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-platt-pt21-turing-inputs "
             "(--block N --required-sign-packet-sha256 HEX | "
             "--persistent-requests N)\n";
      std::exit(0);
    }
    if (argument == "--persistent-requests") {
      if (options.persistent_requests != 0 || index + 1 >= argc) {
        fail("--persistent-requests is missing or duplicated");
      }
      const std::uint64_t value =
          parse_u64(argv[++index], "--persistent-requests");
      if (value == 0 || value > 10'000) {
        fail("--persistent-requests is outside 1..10000");
      }
      options.persistent_requests = static_cast<std::uint32_t>(value);
      continue;
    }
    if (argument == "--block") {
      if (options.have_block || index + 1 >= argc) {
        fail("--block is missing or duplicated");
      }
      options.block = parse_u64(argv[++index], "--block");
      options.have_block = true;
      continue;
    }
    if (argument == "--required-sign-packet-sha256") {
      if (options.have_packet_sha256 || index + 1 >= argc) {
        fail("--required-sign-packet-sha256 is missing or duplicated");
      }
      options.required_sign_packet_sha256 = argv[++index];
      options.have_packet_sha256 = true;
      continue;
    }
    fail("unknown option: " + std::string(argument));
  }
  const bool one_shot =
      options.have_block && options.have_packet_sha256 &&
      options.persistent_requests == 0;
  const bool persistent =
      !options.have_block && !options.have_packet_sha256 &&
      options.persistent_requests != 0;
  if (!one_shot && !persistent) {
    fail("select exactly one one-shot or persistent request mode");
  }
  if (one_shot && options.block >= pti::kSourceBlockCount) {
    fail("--block is outside the PT21 source campaign");
  }
  if (one_shot &&
      !pti::is_lower_sha256(options.required_sign_packet_sha256)) {
    fail("--required-sign-packet-sha256 is not lowercase SHA-256 hex");
  }
  return options;
}

std::string artifact_json(const Options& options) {
  return pti::artifact_json(options.block,
                            options.required_sign_packet_sha256);
}

constexpr std::array<unsigned char, 8> kPersistentRequestMagic{
    'P', 'T', '2', '1', 'T', 'R', 'Q', '1'};
constexpr std::array<unsigned char, 8> kPersistentResponseMagic{
    'P', 'T', '2', '1', 'T', 'R', 'S', '1'};
constexpr std::uint32_t kPersistentVersion = 1;
constexpr std::uint32_t kPersistentRequestBytes = 56;
constexpr std::uint32_t kPersistentResponseHeaderBytes = 16;

std::uint32_t load_u32(const unsigned char* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t load_u64(const unsigned char* data) {
  std::uint64_t result = 0;
  for (unsigned int index = 0; index < 8; ++index) {
    result |= static_cast<std::uint64_t>(data[index]) << (8U * index);
  }
  return result;
}

void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0; index < 4; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void read_exact(unsigned char* output, std::size_t size,
                std::string_view label) {
  std::cin.read(reinterpret_cast<char*>(output),
                static_cast<std::streamsize>(size));
  if (std::cin.gcount() != static_cast<std::streamsize>(size)) {
    fail(std::string(label) + " is truncated");
  }
}

void write_exact(const unsigned char* data, std::size_t size,
                 std::string_view label) {
  std::cout.write(reinterpret_cast<const char*>(data),
                  static_cast<std::streamsize>(size));
  if (!std::cout) fail("cannot write " + std::string(label));
}

void require_persistent_eof() {
  char trailing = '\0';
  std::cin.read(&trailing, 1);
  if (std::cin.gcount() != 0) {
    fail("persistent Turing request stream has trailing bytes");
  }
  if (!std::cin.eof()) {
    fail("persistent Turing request stream did not end cleanly");
  }
}

std::string lower_hex(const unsigned char* data, std::size_t size) {
  constexpr char digits[] = "0123456789abcdef";
  std::string result(size * 2, '0');
  for (std::size_t index = 0; index < size; ++index) {
    result[index * 2] = digits[data[index] >> 4U];
    result[index * 2 + 1] = digits[data[index] & 15U];
  }
  return result;
}

Options read_persistent_request() {
  std::array<unsigned char, kPersistentRequestBytes> request{};
  read_exact(request.data(), request.size(), "persistent Turing request");
  if (!std::equal(kPersistentRequestMagic.begin(),
                  kPersistentRequestMagic.end(), request.begin()) ||
      load_u32(request.data() + 8) != kPersistentVersion ||
      load_u32(request.data() + 12) != kPersistentRequestBytes) {
    fail("persistent Turing request header differs");
  }
  Options result;
  result.block = load_u64(request.data() + 16);
  if (result.block >= pti::kSourceBlockCount) {
    fail("persistent Turing block leaves the PT21 campaign");
  }
  result.required_sign_packet_sha256 =
      lower_hex(request.data() + 24, 32);
  result.have_block = true;
  result.have_packet_sha256 = true;
  return result;
}

void write_persistent_response(const std::string& artifact) {
  if (artifact.empty() ||
      artifact.size() >
          std::numeric_limits<std::uint32_t>::max() -
              kPersistentResponseHeaderBytes) {
    fail("persistent Turing artifact leaves the response bound");
  }
  std::array<unsigned char, kPersistentResponseHeaderBytes> header{};
  std::copy(kPersistentResponseMagic.begin(),
            kPersistentResponseMagic.end(), header.begin());
  store_u32(header.data() + 8, kPersistentVersion);
  store_u32(
      header.data() + 12,
      kPersistentResponseHeaderBytes +
          static_cast<std::uint32_t>(artifact.size()));
  write_exact(header.data(), header.size(),
              "persistent Turing response header");
  write_exact(
      reinterpret_cast<const unsigned char*>(artifact.data()),
      artifact.size(), "persistent Turing artifact");
  std::cout.flush();
  if (!std::cout) fail("cannot flush persistent Turing response");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    if (options.persistent_requests == 0) {
      const std::string artifact = artifact_json(options);
      std::cout << artifact;
      if (!std::cout) {
        fail("failed to write the complete Turing input artifact");
      }
    } else {
      for (std::uint32_t request = 0;
           request < options.persistent_requests; ++request) {
        write_persistent_response(
            artifact_json(read_persistent_request()));
      }
      require_persistent_eof();
    }
    flint_cleanup_master();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_pt21_turing_inputs: " << error.what() << '\n';
    flint_cleanup_master();
    return 2;
  }
}

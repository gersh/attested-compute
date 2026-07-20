// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_mobius_segment.h"

#include "sparkinterval/sha256.hpp"

#include <array>
#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

constexpr std::uint64_t kSourceLimit = 10'000'000'000'000'000ULL;
constexpr std::uint64_t kDefaultCount = 65'536;
constexpr std::uint64_t kMaximumSegmentCount = 100'000'000;
constexpr std::string_view kZeroDigest =
    "0000000000000000000000000000000000000000000000000000000000000000";

// This deliberately coarse rational interval contains the tighter Machin
// enclosure used by tg_verifier.arithmetic:
//
//   607927101854026628 / 10^18
//       <= 6/pi^2 <=
//   607927101854026629 / 10^18.
//
// The Python tests establish those two comparisons with exact Fractions.
constexpr std::uint64_t kDensityDenominator = 1'000'000'000'000'000'000ULL;
constexpr std::uint64_t kDensityLowerNumerator = 607'927'101'854'026'628ULL;
constexpr std::uint64_t kDensityUpperNumerator = 607'927'101'854'026'629ULL;
constexpr std::string_view kDensityIntervalId =
    "machin_20_6_coarsened_1e18_v1";

struct Options {
  std::uint64_t lower = 1;
  std::uint64_t count = kDefaultCount;
  std::int64_t incoming_mertens = 0;
  std::uint64_t incoming_squarefree = 0;
  std::string previous_receipt_sha256{kZeroDigest};
  bool incoming_mertens_given = false;
  bool incoming_squarefree_given = false;
  bool previous_digest_given = false;
  int device = 0;
  bool allow_other_device = false;
};

struct U256 {
  std::array<std::uint64_t, 4> limb{};
};

struct EndpointProblem {
  bool present = false;
  std::uint64_t interval_n = 0;
  const char* side = "";
  std::uint64_t y = 0;
};

[[noreturn]] void fail(const std::string& message, int code = 2) {
  std::cerr << message << '\n';
  std::exit(code);
}

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  fail(std::string(operation) + " failed: " + cudaGetErrorString(status), 3);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) fail_cuda(operation, status);
}

bool parse_u64(std::string_view text, std::uint64_t* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

bool parse_i64(std::string_view text, std::int64_t* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

bool is_digest(std::string_view text) {
  if (text.size() != 64) return false;
  for (const char character : text) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--lower") {
      if (!parse_u64(require_value("--lower"), &options.lower)) {
        fail("--lower must be a nonnegative integer");
      }
    } else if (argument == "--count") {
      if (!parse_u64(require_value("--count"), &options.count)) {
        fail("--count must be a nonnegative integer");
      }
    } else if (argument == "--incoming-mertens") {
      if (!parse_i64(require_value("--incoming-mertens"),
                     &options.incoming_mertens)) {
        fail("--incoming-mertens must be a signed 64-bit integer");
      }
      options.incoming_mertens_given = true;
    } else if (argument == "--incoming-squarefree") {
      if (!parse_u64(require_value("--incoming-squarefree"),
                     &options.incoming_squarefree)) {
        fail("--incoming-squarefree must be a nonnegative integer");
      }
      options.incoming_squarefree_given = true;
    } else if (argument == "--previous-receipt-sha256") {
      options.previous_receipt_sha256 =
          std::string(require_value("--previous-receipt-sha256"));
      if (!is_digest(options.previous_receipt_sha256)) {
        fail("--previous-receipt-sha256 must be 64 lowercase hexadecimal characters");
      }
      options.previous_digest_given = true;
    } else if (argument == "--device") {
      std::uint64_t parsed = 0;
      if (!parse_u64(require_value("--device"), &parsed) ||
          parsed > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
        fail("--device must be a nonnegative integer");
      }
      options.device = static_cast<int>(parsed);
    } else if (argument == "--allow-other-device") {
      options.allow_other_device = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-mobius-segment "
             "[--lower N] [--count N] [--incoming-mertens M] "
             "[--incoming-squarefree Q] "
             "[--previous-receipt-sha256 HEX] [--device N] "
             "[--allow-other-device]\n"
             "Computes one exact bounded Moebius segment, independently "
             "checks every GPU record on the CPU, and emits a hash-linked "
             "state transition. Non-root segments require all three "
             "incoming-state arguments.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.lower < 1 || options.lower > kSourceLimit) {
    fail("--lower must lie in [1, 10000000000000000]");
  }
  if (options.count < 1 || options.count > kMaximumSegmentCount) {
    fail("--count must lie in [1, 100000000]");
  }
  if (options.count - 1 > kSourceLimit - options.lower) {
    fail("requested segment exceeds the bounded source range through 10^16");
  }
  if (options.lower == 1) {
    if (options.incoming_mertens != 0 ||
        options.incoming_squarefree != 0 ||
        options.previous_receipt_sha256 != kZeroDigest) {
      fail("a root segment must have zero incoming state and the zero previous digest");
    }
  } else if (!(options.incoming_mertens_given &&
               options.incoming_squarefree_given &&
               options.previous_digest_given)) {
    fail("a non-root segment requires incoming Mertens, squarefree, and previous-digest state");
  } else if (options.previous_receipt_sha256 == kZeroDigest) {
    fail("a non-root segment requires a nonzero previous receipt digest");
  }
  const std::uint64_t prior_rows = options.lower - 1;
  if (options.incoming_mertens < -static_cast<std::int64_t>(prior_rows) ||
      options.incoming_mertens > static_cast<std::int64_t>(prior_rows)) {
    fail("incoming Mertens state exceeds the elementary prefix range");
  }
  if (options.incoming_squarefree > prior_rows) {
    fail("incoming squarefree state exceeds the prefix length");
  }
  return options;
}

std::uint64_t integer_square_root(std::uint64_t value) {
  std::uint64_t lower = 0;
  std::uint64_t upper = 100'000'001;
  while (lower + 1 < upper) {
    const std::uint64_t middle = lower + (upper - lower) / 2;
    if (middle <= value / middle) {
      lower = middle;
    } else {
      upper = middle;
    }
  }
  return lower;
}

std::vector<std::uint32_t> exact_primes_upto(std::uint64_t limit64) {
  if (limit64 < 2) return {};
  if (limit64 > 100'000'000) fail("internal base-prime limit exceeded");
  const auto limit = static_cast<std::uint32_t>(limit64);
  std::vector<bool> composite(static_cast<std::size_t>(limit) + 1, false);
  for (std::uint32_t prime = 2; prime <= limit / prime; ++prime) {
    if (composite[prime]) continue;
    for (std::uint64_t multiple =
             static_cast<std::uint64_t>(prime) * prime;
         multiple <= limit; multiple += prime) {
      composite[static_cast<std::size_t>(multiple)] = true;
    }
  }
  std::vector<std::uint32_t> primes;
  for (std::uint32_t candidate = 2; candidate <= limit; ++candidate) {
    if (!composite[candidate]) primes.push_back(candidate);
  }
  return primes;
}

void independently_sieve(std::uint64_t lower,
                         const std::vector<std::uint32_t>& primes,
                         std::vector<TgMobiusSupport>* records) {
  for (TgMobiusSupport& record : *records) {
    record = TgMobiusSupport{1, 0, 0, 0, 0};
  }
  for (const std::uint32_t prime32 : primes) {
    const std::uint64_t prime = prime32;
    const std::uint64_t remainder = lower % prime;
    const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
    for (std::uint64_t offset = first_offset; offset < records->size();
         offset += prime) {
      TgMobiusSupport& record = (*records)[offset];
      record.base_prime_product *= prime;
      ++record.distinct_base_prime_count;
      const std::uint64_t number = lower + offset;
      if ((number / prime) % prime == 0) record.squareful = 1;
    }
  }
  for (std::size_t index = 0; index < records->size(); ++index) {
    TgMobiusSupport& record = (*records)[index];
    const std::uint64_t number = lower + index;
    if (record.squareful != 0) {
      record.mobius = 0;
    } else {
      const std::uint64_t residual = number / record.base_prime_product;
      const std::uint32_t omega = record.distinct_base_prime_count +
                                  static_cast<std::uint32_t>(residual > 1);
      record.mobius = (omega & 1U) == 0 ? 1 : -1;
    }
  }
}

bool same_record(const TgMobiusSupport& left,
                 const TgMobiusSupport& right) {
  return left.base_prime_product == right.base_prime_product &&
         left.distinct_base_prime_count == right.distinct_base_prime_count &&
         left.squareful == right.squareful && left.mobius == right.mobius &&
         left.reserved == right.reserved;
}

void hash_u32_le(sparkinterval::detail::Sha256* hasher,
                 std::uint32_t value) {
  std::array<unsigned char, 4> bytes{};
  for (unsigned int index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

void hash_u64_le(sparkinterval::detail::Sha256* hasher,
                 std::uint64_t value) {
  std::array<unsigned char, 8> bytes{};
  for (unsigned int index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

void hash_record(sparkinterval::detail::Sha256* hasher,
                 const TgMobiusSupport& record) {
  hash_u64_le(hasher, record.base_prime_product);
  hash_u32_le(hasher, record.distinct_base_prime_count);
  hash_u32_le(hasher, record.squareful);
  hash_u32_le(hasher, static_cast<std::uint32_t>(record.mobius));
  hash_u32_le(hasher, record.reserved);
}

U256 multiply_u128(unsigned __int128 left, unsigned __int128 right) {
  const std::array<std::uint64_t, 2> a = {
      static_cast<std::uint64_t>(left),
      static_cast<std::uint64_t>(left >> 64U)};
  const std::array<std::uint64_t, 2> b = {
      static_cast<std::uint64_t>(right),
      static_cast<std::uint64_t>(right >> 64U)};
  U256 result{};
  for (std::size_t i = 0; i < 2; ++i) {
    unsigned __int128 carry = 0;
    for (std::size_t j = 0; j < 2; ++j) {
      const unsigned __int128 value =
          static_cast<unsigned __int128>(a[i]) * b[j] +
          result.limb[i + j] + carry;
      result.limb[i + j] = static_cast<std::uint64_t>(value);
      carry = value >> 64U;
    }
    result.limb[i + 2] += static_cast<std::uint64_t>(carry);
  }
  return result;
}

U256 multiply_u64(U256 value, std::uint64_t factor) {
  unsigned __int128 carry = 0;
  for (std::uint64_t& limb : value.limb) {
    const unsigned __int128 product =
        static_cast<unsigned __int128>(limb) * factor + carry;
    limb = static_cast<std::uint64_t>(product);
    carry = product >> 64U;
  }
  if (carry != 0) fail("internal 256-bit comparison overflow");
  return value;
}

bool less_equal(const U256& left, const U256& right) {
  for (std::size_t index = left.limb.size(); index-- > 0;) {
    if (left.limb[index] != right.limb[index]) {
      return left.limb[index] < right.limb[index];
    }
  }
  return true;
}

bool density_endpoint_safe(std::uint64_t squarefree_count, std::uint64_t y,
                           std::uint64_t density_numerator,
                           std::uint64_t bound_numerator,
                           std::uint64_t bound_denominator) {
  const unsigned __int128 scaled_count =
      static_cast<unsigned __int128>(squarefree_count) *
      kDensityDenominator;
  const unsigned __int128 scaled_main =
      static_cast<unsigned __int128>(density_numerator) * y;
  const unsigned __int128 difference =
      scaled_count >= scaled_main ? scaled_count - scaled_main
                                  : scaled_main - scaled_count;
  const unsigned __int128 lhs_factor = difference * bound_denominator;
  const unsigned __int128 rhs_factor =
      static_cast<unsigned __int128>(kDensityDenominator) * bound_numerator;
  const U256 lhs = multiply_u128(lhs_factor, lhs_factor);
  const U256 rhs = multiply_u64(multiply_u128(rhs_factor, rhs_factor), y);
  return less_equal(lhs, rhs);
}

bool squarefree_endpoint_safe(std::uint64_t squarefree_count,
                              std::uint64_t y,
                              std::uint64_t bound_numerator,
                              std::uint64_t bound_denominator) {
  return density_endpoint_safe(squarefree_count, y,
                               kDensityLowerNumerator, bound_numerator,
                               bound_denominator) &&
         density_endpoint_safe(squarefree_count, y,
                               kDensityUpperNumerator, bound_numerator,
                               bound_denominator);
}

signed __int128 hurst_slack(std::uint64_t n, std::int64_t mertens) {
  const signed __int128 m = mertens;
  return static_cast<signed __int128>(571) * 571 * n -
         static_cast<signed __int128>(1000) * 1000 * m * m;
}

std::string render_i128(signed __int128 value) {
  if (value == 0) return "0";
  const bool negative = value < 0;
  unsigned __int128 magnitude = negative
      ? static_cast<unsigned __int128>(-(value + 1)) + 1
      : static_cast<unsigned __int128>(value);
  std::string digits;
  while (magnitude != 0) {
    digits.push_back(static_cast<char>('0' + magnitude % 10));
    magnitude /= 10;
  }
  if (negative) digits.push_back('-');
  return std::string(digits.rbegin(), digits.rend());
}

std::string hash_file(const char* path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  sparkinterval::detail::Sha256 hasher;
  std::array<char, 1 << 16> buffer{};
  while (input) {
    input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    const std::streamsize count = input.gcount();
    if (count > 0) hasher.update(buffer.data(), static_cast<std::size_t>(count));
  }
  return sparkinterval::lowercase_hex(hasher.finish());
}

std::string json_escape(std::string_view value) {
  std::string escaped;
  for (const char character : value) {
    if (character == '"' || character == '\\') escaped.push_back('\\');
    escaped.push_back(character);
  }
  return escaped;
}

void print_problem(const EndpointProblem& problem) {
  if (!problem.present) {
    std::cout << "null";
  } else {
    std::cout << "{\"interval_n\": " << problem.interval_n
              << ", \"side\": \"" << problem.side << "\", \"y\": "
              << problem.y << '}';
  }
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const std::size_t count = static_cast<std::size_t>(options.count);
  const std::uint64_t upper = options.lower + options.count - 1;
  const std::uint64_t base_prime_limit = integer_square_root(upper);
  const std::vector<std::uint32_t> primes = exact_primes_upto(base_prime_limit);
  const std::uint64_t dense_prime_limit =
      1 + (options.count - 1) / 256;
  const std::size_t dense_prime_count = static_cast<std::size_t>(
      std::upper_bound(primes.begin(), primes.end(), dense_prime_limit) -
      primes.begin());

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device; use --allow-other-device only for explicit cross-device testing", 4);
  }
  if (options.device >= device_count) fail("requested CUDA device is unavailable", 4);
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));
  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if ((std::string_view(properties.name) != "NVIDIA GB10" ||
       properties.major != 12 || properties.minor != 1) &&
      !options.allow_other_device) {
    fail("expected an NVIDIA GB10 with compute capability 12.1; use --allow-other-device only for explicit cross-device testing", 4);
  }

  const std::size_t output_bytes = count * sizeof(TgMobiusSupport);
  const std::size_t prime_bytes = primes.size() * sizeof(std::uint32_t);
  std::uint32_t* device_primes = nullptr;
  TgMobiusSupport* device_outputs = nullptr;
  if (!primes.empty()) {
    check_cuda("cudaMalloc(base_primes)",
               cudaMalloc(reinterpret_cast<void**>(&device_primes), prime_bytes));
    check_cuda("cudaMemcpy(base_primes)",
               cudaMemcpy(device_primes, primes.data(), prime_bytes,
                          cudaMemcpyHostToDevice));
  }
  check_cuda("cudaMalloc(outputs)",
             cudaMalloc(reinterpret_cast<void**>(&device_outputs), output_bytes));

  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(stop)", cudaEventCreate(&stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  check_cuda("Moebius segment launch",
             launch_tg_mobius_segment(options.lower, count, device_primes,
                                      primes.size(), dense_prime_count,
                                      device_outputs));
  check_cuda("cudaEventRecord(stop)", cudaEventRecord(stop));
  check_cuda("cudaEventSynchronize(stop)", cudaEventSynchronize(stop));
  float kernel_milliseconds = 0.0F;
  check_cuda("cudaEventElapsedTime",
             cudaEventElapsedTime(&kernel_milliseconds, start, stop));

  std::vector<TgMobiusSupport> outputs(count);
  check_cuda("cudaMemcpy(outputs)",
             cudaMemcpy(outputs.data(), device_outputs, output_bytes,
                        cudaMemcpyDeviceToHost));
  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(stop)", cudaEventDestroy(stop));
  if (device_primes != nullptr) check_cuda("cudaFree(base_primes)", cudaFree(device_primes));
  check_cuda("cudaFree(outputs)", cudaFree(device_outputs));

  const auto host_start = std::chrono::steady_clock::now();
  std::vector<TgMobiusSupport> expected(count);
  independently_sieve(options.lower, primes, &expected);
  sparkinterval::detail::Sha256 gpu_hasher;
  sparkinterval::detail::Sha256 cpu_hasher;
  std::array<std::uint64_t, 3> mobius_histogram{};
  std::uint64_t mismatch_count = 0;
  std::uint64_t first_mismatch_number = 0;
  std::int64_t mertens = options.incoming_mertens;
  std::uint64_t squarefree_count = options.incoming_squarefree;
  signed __int128 minimum_hurst_slack = 0;
  std::uint64_t minimum_hurst_slack_at = 0;
  std::uint64_t hurst_checks = 0;
  std::uint64_t first_hurst_failure = 0;
  std::uint64_t b1_checks = 0;
  std::uint64_t b2_checks = 0;
  EndpointProblem first_b1_problem{};
  EndpointProblem first_b2_problem{};

  for (std::size_t index = 0; index < count; ++index) {
    const TgMobiusSupport& actual = outputs[index];
    const TgMobiusSupport& reference = expected[index];
    hash_record(&gpu_hasher, actual);
    hash_record(&cpu_hasher, reference);
    if (!same_record(actual, reference)) {
      if (mismatch_count == 0) first_mismatch_number = options.lower + index;
      ++mismatch_count;
    }

    const std::uint64_t n = options.lower + index;
    const std::int32_t mu = reference.mobius;
    ++mobius_histogram[static_cast<std::size_t>(mu + 1)];
    mertens += mu;
    if (mu != 0) ++squarefree_count;

    if (n >= 33) {
      const signed __int128 slack = hurst_slack(n, mertens);
      if (hurst_checks == 0 || slack < minimum_hurst_slack) {
        minimum_hurst_slack = slack;
        minimum_hurst_slack_at = n;
      }
      ++hurst_checks;
      if (slack < 0 && first_hurst_failure == 0) first_hurst_failure = n;
    }

    auto check_cdem_head = [&](std::uint64_t threshold,
                               std::uint64_t bound_numerator,
                               std::uint64_t bound_denominator,
                               std::uint64_t* checks,
                               EndpointProblem* first_problem) {
      if (n < threshold) return;
      auto check_endpoint = [&](std::uint64_t y, const char* side) {
        ++*checks;
        if (!squarefree_endpoint_safe(squarefree_count, y, bound_numerator,
                                      bound_denominator) &&
            !first_problem->present) {
          *first_problem = EndpointProblem{true, n, side, y};
        }
      };
      // At n=threshold this is a limiting check from the claimed open side.
      check_endpoint(n, "at_integer_or_open_right_limit");
      if (n < kSourceLimit) check_endpoint(n + 1, "left_limit_at_next_integer");
    };
    check_cdem_head(9'243, 151, 2'000, &b1_checks, &first_b1_problem);
    check_cdem_head(438'429, 57, 2'000, &b2_checks, &first_b2_problem);
  }

  const std::string gpu_digest =
      sparkinterval::lowercase_hex(gpu_hasher.finish());
  const std::string cpu_digest =
      sparkinterval::lowercase_hex(cpu_hasher.finish());
  const bool records_passed = mismatch_count == 0 && gpu_digest == cpu_digest;
  const auto host_stop = std::chrono::steady_clock::now();
  const double host_milliseconds =
      std::chrono::duration<double, std::milli>(host_stop - host_start).count();

  const std::int64_t delta_mertens =
      static_cast<std::int64_t>(mobius_histogram[2]) -
      static_cast<std::int64_t>(mobius_histogram[0]);
  const std::uint64_t segment_squarefree =
      mobius_histogram[0] + mobius_histogram[2];
  const std::string executable_digest = hash_file("/proc/self/exe");
  if (executable_digest.empty()) {
    fail("could not hash the running executable", 5);
  }
  std::ostringstream canonical;
  canonical << "algorithm=tg_mobius_segment_v1\n"
            << "previous=" << options.previous_receipt_sha256 << '\n'
            << "lower=" << options.lower << '\n'
            << "upper=" << upper << '\n'
            << "incoming_mertens=" << options.incoming_mertens << '\n'
            << "outgoing_mertens=" << mertens << '\n'
            << "incoming_squarefree=" << options.incoming_squarefree << '\n'
            << "outgoing_squarefree=" << squarefree_count << '\n'
            << "record_sha256=" << gpu_digest << '\n'
            << "executable_sha256=" << executable_digest << '\n'
            << "density_interval=" << kDensityIntervalId << '\n'
            << "mu_negative=" << mobius_histogram[0] << '\n'
            << "mu_zero=" << mobius_histogram[1] << '\n'
            << "mu_positive=" << mobius_histogram[2] << '\n'
            << "hurst_checks=" << hurst_checks << '\n'
            << "hurst_first_failure=" << first_hurst_failure << '\n'
            << "hurst_minimum_slack="
            << (hurst_checks == 0 ? "null" : render_i128(minimum_hurst_slack))
            << '\n'
            << "hurst_minimum_at=" << minimum_hurst_slack_at << '\n'
            << "b1_checks=" << b1_checks << '\n'
            << "b1_problem_n="
            << (first_b1_problem.present ? first_b1_problem.interval_n : 0) << '\n'
            << "b1_problem_side="
            << (first_b1_problem.present ? first_b1_problem.side : "none") << '\n'
            << "b1_problem_y="
            << (first_b1_problem.present ? first_b1_problem.y : 0) << '\n'
            << "b2_checks=" << b2_checks << '\n'
            << "b2_problem_n="
            << (first_b2_problem.present ? first_b2_problem.interval_n : 0) << '\n'
            << "b2_problem_side="
            << (first_b2_problem.present ? first_b2_problem.side : "none") << '\n'
            << "b2_problem_y="
            << (first_b2_problem.present ? first_b2_problem.y : 0) << '\n';
  const std::string canonical_text = canonical.str();
  const std::string receipt_digest = sparkinterval::sha256_hex(
      canonical_text.data(), canonical_text.size());

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));
  const double rows_per_second = kernel_milliseconds > 0.0F
      ? static_cast<double>(count) * 1000.0 / kernel_milliseconds
      : 0.0;

  std::cout << std::setprecision(17)
            << "{\n"
            << "  \"schema_version\": 1,\n"
            << "  \"algorithm\": \"tg_mobius_segment_v1\",\n"
            << "  \"classification\": \"bounded_exact_transition_not_external_atom_proof\",\n"
            << "  \"lower\": " << options.lower << ",\n"
            << "  \"upper\": " << upper << ",\n"
            << "  \"record_count\": " << count << ",\n"
            << "  \"incoming_mertens\": " << options.incoming_mertens << ",\n"
            << "  \"outgoing_mertens\": " << mertens << ",\n"
            << "  \"delta_mertens\": " << delta_mertens << ",\n"
            << "  \"incoming_squarefree\": " << options.incoming_squarefree << ",\n"
            << "  \"outgoing_squarefree\": " << squarefree_count << ",\n"
            << "  \"segment_squarefree_count\": " << segment_squarefree << ",\n"
            << "  \"previous_receipt_sha256\": \""
            << options.previous_receipt_sha256 << "\",\n"
            << "  \"receipt_chain_sha256\": \"" << receipt_digest << "\",\n"
            << "  \"canonical_transition_format\": \"tg_mobius_transition_lines_v1\",\n"
            << "  \"gpu_record_sha256_le_v1\": \"" << gpu_digest << "\",\n"
            << "  \"cpu_record_sha256_le_v1\": \"" << cpu_digest << "\",\n"
            << "  \"executable_sha256\": \"" << executable_digest << "\",\n"
            << "  \"all_records_compared_with_independent_cpu_segmented_sieve\": "
            << (records_passed ? "true" : "false") << ",\n"
            << "  \"mismatch_count\": " << mismatch_count << ",\n"
            << "  \"first_mismatch_number\": "
            << (mismatch_count == 0 ? "null" : std::to_string(first_mismatch_number))
            << ",\n"
            << "  \"mobius_histogram\": {\"-1\": " << mobius_histogram[0]
            << ", \"0\": " << mobius_histogram[1] << ", \"1\": "
            << mobius_histogram[2] << "},\n"
            << "  \"hurst_integer_checks\": " << hurst_checks << ",\n"
            << "  \"hurst_minimum_squared_slack\": "
            << (hurst_checks == 0 ? "null" : render_i128(minimum_hurst_slack))
            << ",\n"
            << "  \"hurst_minimum_squared_slack_at\": "
            << (hurst_checks == 0 ? "null" : std::to_string(minimum_hurst_slack_at))
            << ",\n"
            << "  \"hurst_first_failure\": "
            << (first_hurst_failure == 0 ? "null" : std::to_string(first_hurst_failure))
            << ",\n"
            << "  \"hurst_real_slab_reduction\": \"M(x)=M(floor(x)); sqrt(x) is increasing\",\n"
            << "  \"squarefree_density_interval_id\": \"" << kDensityIntervalId
            << "\",\n"
            << "  \"squarefree_density_lower\": \"607927101854026628/1000000000000000000\",\n"
            << "  \"squarefree_density_upper\": \"607927101854026629/1000000000000000000\",\n"
            << "  \"cdem_b1_endpoint_checks\": " << b1_checks << ",\n"
            << "  \"cdem_b1_first_not_proved_safe\": ";
  print_problem(first_b1_problem);
  std::cout << ",\n  \"cdem_b2_endpoint_checks\": " << b2_checks
            << ",\n  \"cdem_b2_first_not_proved_safe\": ";
  print_problem(first_b2_problem);
  std::cout
      << ",\n  \"incoming_state_is_locally_rooted\": "
      << (options.lower == 1 ? "true" : "false") << ",\n"
      << "  \"nonroot_claims_are_conditional_on_hash_linked_incoming_state\": "
      << (options.lower == 1 ? "false" : "true") << ",\n"
      << "  \"base_prime_limit\": " << base_prime_limit << ",\n"
      << "  \"base_prime_count\": " << primes.size() << ",\n"
      << "  \"dense_prime_count\": " << dense_prime_count << ",\n"
      << "  \"base_prime_generation\": \"exact_host_eratosthenes_sieve\",\n"
      << "  \"device_name\": \"" << json_escape(properties.name) << "\",\n"
      << "  \"compute_capability\": \"" << properties.major << '.'
      << properties.minor << "\",\n"
      << "  \"cuda_driver_api_version\": " << driver_version << ",\n"
      << "  \"cuda_runtime_version\": " << runtime_version << ",\n"
      << "  \"kernel_milliseconds\": " << kernel_milliseconds << ",\n"
      << "  \"kernel_rows_per_second\": " << rows_per_second << ",\n"
      << "  \"independent_cpu_check_and_exact_bounds_milliseconds\": "
      << host_milliseconds << ",\n"
      << "  \"single_receipt_covers_full_1e16_range\": false,\n"
      << "  \"checks_hurst_source_shape_conditionally\": true,\n"
      << "  \"checks_cdem_squarefree_source_shape_conditionally\": true,\n"
      << "  \"has_complete_1e16_receipt_chain\": false,\n"
      << "  \"proves_mertens_hurst_external_atom\": false,\n"
      << "  \"proves_cdem_squarefree_external_atom\": false,\n"
      << "  \"proves_any_external_atom\": false\n"
      << "}\n";
  return records_passed ? 0 : 5;
}

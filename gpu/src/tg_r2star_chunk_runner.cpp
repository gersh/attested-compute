// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_r2star_chunk.h"
#include "tg_r2star_factor_support.h"

#include "sparkinterval/sha256.hpp"

#include <array>
#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <boost/multiprecision/cpp_int.hpp>

#include <cuda_runtime_api.h>

namespace {

constexpr std::uint64_t kSourceLimit = 21'000'000'000ULL;
constexpr std::uint64_t kDefaultCount = 10'000;
constexpr std::uint64_t kMaximumCheckedCount = 1'000'000;
constexpr std::string_view kZeroSha256 =
    "0000000000000000000000000000000000000000000000000000000000000000";
constexpr std::string_view kFactorEncoding =
    "r2star-distinct-prime-support-u64be-v1";

using boost::multiprecision::cpp_int;

[[noreturn]] void fail(const std::string& message, int code);

struct ExactFactorSupport {
  std::array<std::uint64_t, 10> factors{};
  std::uint32_t count = 0;

  void append(std::uint64_t factor) {
    if (count >= factors.size()) {
      fail("factorization exceeds the source-range support bound", 5);
    }
    factors[count++] = factor;
  }
};

// The CUDA interval almost always determines the exact scale-2^32 rounding.
// For the rare row where it straddles a rounding boundary, replay the same
// positive atanh series as tg_verifier.r2star with arbitrary-precision
// rationals.  This is a correctness fallback, not floating-point widening.
struct ExactFraction {
  cpp_int numerator = 0;
  cpp_int denominator = 1;

  ExactFraction() = default;
  ExactFraction(cpp_int n, cpp_int d = 1)
      : numerator(std::move(n)), denominator(std::move(d)) {
    if (denominator == 0) fail("exact rational has zero denominator", 5);
    if (denominator < 0) {
      numerator = -numerator;
      denominator = -denominator;
    }
    cpp_int left = numerator < 0 ? -numerator : numerator;
    cpp_int right = denominator;
    while (right != 0) {
      cpp_int remainder = left % right;
      left = right;
      right = remainder;
    }
    if (left != 0) {
      numerator /= left;
      denominator /= left;
    }
  }
};

ExactFraction operator+(const ExactFraction& left,
                        const ExactFraction& right) {
  return ExactFraction(left.numerator * right.denominator +
                           right.numerator * left.denominator,
                       left.denominator * right.denominator);
}

ExactFraction operator-(const ExactFraction& left,
                        const ExactFraction& right) {
  return ExactFraction(left.numerator * right.denominator -
                           right.numerator * left.denominator,
                       left.denominator * right.denominator);
}

ExactFraction operator*(const ExactFraction& left,
                        const ExactFraction& right) {
  return ExactFraction(left.numerator * right.numerator,
                       left.denominator * right.denominator);
}

ExactFraction operator/(const ExactFraction& left,
                        const ExactFraction& right) {
  if (right.numerator == 0) fail("exact rational division by zero", 5);
  return ExactFraction(left.numerator * right.denominator,
                       left.denominator * right.numerator);
}

ExactFraction operator*(const ExactFraction& value, std::uint64_t multiplier) {
  return ExactFraction(value.numerator * multiplier, value.denominator);
}

std::pair<ExactFraction, ExactFraction> positive_log_series_bounds_exact(
    std::uint64_t numerator, std::uint64_t denominator) {
  if (!(denominator <= numerator && numerator <= 2 * denominator)) {
    fail("exact positive-log fallback received an invalid ratio", 5);
  }
  const ExactFraction z(cpp_int(numerator - denominator),
                        cpp_int(numerator + denominator));
  if (z.numerator == 0) return {ExactFraction(), ExactFraction()};
  const ExactFraction z_squared = z * z;
  ExactFraction power = z;
  ExactFraction partial;
  for (std::uint32_t index = 0; index < kTgR2StarSeriesTerms; ++index) {
    partial = partial +
              power / ExactFraction(cpp_int(2 * index + 1));
    power = power * z_squared;
  }
  const ExactFraction lower = partial * 2;
  const ExactFraction remainder =
      (power * 2) /
      (ExactFraction(cpp_int(2 * kTgR2StarSeriesTerms + 1)) *
       (ExactFraction(1) - z_squared));
  return {lower, lower + remainder};
}

std::uint64_t exact_scaled_floor(const ExactFraction& value) {
  if (value.numerator < 0) fail("negative exact logarithm fallback", 5);
  const cpp_int quotient =
      (value.numerator << kTgR2StarScaleBits) / value.denominator;
  if (quotient > std::numeric_limits<std::uint64_t>::max()) {
    fail("exact logarithm fallback overflows uint64", 5);
  }
  return quotient.convert_to<std::uint64_t>();
}

std::uint64_t exact_scaled_ceil(const ExactFraction& value) {
  if (value.numerator < 0) fail("negative exact logarithm fallback", 5);
  const cpp_int scaled = value.numerator << kTgR2StarScaleBits;
  const cpp_int quotient =
      (scaled + value.denominator - 1) / value.denominator;
  if (quotient > std::numeric_limits<std::uint64_t>::max()) {
    fail("exact logarithm fallback overflows uint64", 5);
  }
  return quotient.convert_to<std::uint64_t>();
}

std::pair<std::uint64_t, std::uint64_t> fixed_log_bounds_exact(
    std::uint64_t integer) {
  if (integer < 2) fail("exact logarithm fallback requires n >= 2", 5);
  std::uint32_t exponent = 0;
  for (std::uint64_t copy = integer; copy > 1; copy >>= 1) ++exponent;
  const std::uint64_t power_of_two = std::uint64_t{1} << exponent;
  const auto log_two = positive_log_series_bounds_exact(2, 1);
  const auto mantissa =
      positive_log_series_bounds_exact(integer, power_of_two);
  const ExactFraction lower = log_two.first * exponent + mantissa.first;
  const ExactFraction upper = log_two.second * exponent + mantissa.second;
  const std::uint64_t result_lower = exact_scaled_floor(lower);
  const std::uint64_t result_upper = exact_scaled_ceil(upper);
  if (result_lower > result_upper) fail("exact log fallback reversed", 5);
  return {result_lower, result_upper};
}

std::uint64_t shift32_floor(const cpp_int& product) {
  if (product < 0) fail("negative exact coefficient product", 5);
  const cpp_int result = product >> 32;
  if (result > std::numeric_limits<std::uint64_t>::max()) {
    fail("exact coefficient fallback overflows uint64", 5);
  }
  return static_cast<std::uint64_t>(result);
}

std::uint64_t shift32_ceil(const cpp_int& product) {
  const std::uint64_t floor = shift32_floor(product);
  const bool remainder = (product & ((cpp_int(1) << 32) - 1)) != 0;
  if (remainder && floor == std::numeric_limits<std::uint64_t>::max()) {
    fail("exact coefficient fallback ceil overflows uint64", 5);
  }
  return floor + static_cast<std::uint64_t>(remainder);
}

TgR2StarDirectedRow exact_directed_row(
    std::uint64_t number, const ExactFactorSupport& factors) {
  TgR2StarDirectedRow row{};
  row.status = static_cast<std::uint32_t>(TgR2StarRowStatus::valid);
  if (number >= 2) {
    const auto bounds = fixed_log_bounds_exact(number);
    row.log_lower = bounds.first;
    row.log_upper = bounds.second;
  }
  std::int64_t coefficient_lower = 0;
  std::int64_t coefficient_upper = 0;
  if (factors.count == 1) {
    const auto bounds = fixed_log_bounds_exact(factors.factors[0]);
    const std::uint64_t lower_magnitude = shift32_ceil(
        cpp_int(bounds.second) * bounds.second);
    const std::uint64_t upper_magnitude = shift32_floor(
        cpp_int(bounds.first) * bounds.first);
    if (lower_magnitude > static_cast<std::uint64_t>(
                              std::numeric_limits<std::int64_t>::max()) ||
        upper_magnitude > static_cast<std::uint64_t>(
                              std::numeric_limits<std::int64_t>::max())) {
      fail("exact one-factor coefficient fallback overflows int64", 5);
    }
    coefficient_lower = -static_cast<std::int64_t>(lower_magnitude);
    coefficient_upper = -static_cast<std::int64_t>(upper_magnitude);
  } else if (factors.count == 2) {
    const auto first = fixed_log_bounds_exact(factors.factors[0]);
    const auto second = fixed_log_bounds_exact(factors.factors[1]);
    const std::uint64_t lower = shift32_floor(
        cpp_int(2) * first.first * second.first);
    const std::uint64_t upper = shift32_ceil(
        cpp_int(2) * first.second * second.second);
    if (lower > static_cast<std::uint64_t>(
                    std::numeric_limits<std::int64_t>::max()) ||
        upper > static_cast<std::uint64_t>(
                    std::numeric_limits<std::int64_t>::max())) {
      fail("exact two-factor coefficient fallback overflows int64", 5);
    }
    coefficient_lower = static_cast<std::int64_t>(lower);
    coefficient_upper = static_cast<std::int64_t>(upper);
  }
  constexpr std::int64_t twice_gamma_lower =
      static_cast<std::int64_t>(2 * kTgR2StarGammaLower);
  constexpr std::int64_t twice_gamma_upper =
      static_cast<std::int64_t>(2 * kTgR2StarGammaUpper);
  if ((coefficient_lower > 0 &&
       coefficient_lower > std::numeric_limits<std::int64_t>::max() -
                               twice_gamma_lower) ||
      (coefficient_upper > 0 &&
       coefficient_upper > std::numeric_limits<std::int64_t>::max() -
                               twice_gamma_upper)) {
    fail("exact directed-row fallback overflows int64", 5);
  }
  row.delta_lower = coefficient_lower + twice_gamma_lower;
  row.delta_upper = coefficient_upper + twice_gamma_upper;
  if (row.delta_lower > row.delta_upper) {
    fail("exact directed-row fallback reversed", 5);
  }
  return row;
}

struct Options {
  std::uint64_t lower = 1;
  std::uint64_t count = kDefaultCount;
  std::int64_t incoming_lower = 0;
  std::int64_t incoming_upper = 0;
  std::string previous_hash = std::string(kZeroSha256);
  int device = 0;
  bool allow_other_device = false;
  bool cross_check_serial = false;
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

template <typename Integer>
bool parse_integer(std::string_view text, Integer* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

bool valid_digest(std::string_view value) {
  if (value.size() != 64) return false;
  for (char character : value) {
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
      if (!parse_integer(require_value("--lower"), &options.lower)) {
        fail("--lower must be a nonnegative integer");
      }
    } else if (argument == "--count") {
      if (!parse_integer(require_value("--count"), &options.count)) {
        fail("--count must be a nonnegative integer");
      }
    } else if (argument == "--incoming-lower") {
      if (!parse_integer(require_value("--incoming-lower"),
                         &options.incoming_lower)) {
        fail("--incoming-lower must be a signed 64-bit integer");
      }
    } else if (argument == "--incoming-upper") {
      if (!parse_integer(require_value("--incoming-upper"),
                         &options.incoming_upper)) {
        fail("--incoming-upper must be a signed 64-bit integer");
      }
    } else if (argument == "--previous-hash") {
      options.previous_hash = std::string(require_value("--previous-hash"));
      if (!valid_digest(options.previous_hash)) {
        fail("--previous-hash must be a lowercase SHA-256 digest");
      }
    } else if (argument == "--device") {
      std::uint64_t parsed = 0;
      if (!parse_integer(require_value("--device"), &parsed) ||
          parsed > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
        fail("--device must be a nonnegative integer");
      }
      options.device = static_cast<int>(parsed);
    } else if (argument == "--allow-other-device") {
      options.allow_other_device = true;
    } else if (argument == "--cross-check-serial") {
      options.cross_check_serial = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-r2star-chunk [--lower N] [--count N] "
             "[--incoming-lower I] [--incoming-upper I] "
             "[--previous-hash HEX] [--device N] [--allow-other-device] "
             "[--cross-check-serial]\n"
             "Produces one bounded, hash-linked scale-2^32 R2Star chunk. "
             "Rare ambiguous GPU log roundings use an exact rational host "
             "fallback; every integer overflow rejects the chunk. Add "
             "--cross-check-serial to compare the blocked scan "
             "with the retained one-thread reference.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.lower < 1 || options.lower > kSourceLimit) {
    fail("--lower must lie in [1, 21000000000]");
  }
  if (options.count < 1 || options.count > kMaximumCheckedCount) {
    fail("--count must lie in [1, 1000000]");
  }
  if (options.count - 1 > kSourceLimit - options.lower) {
    fail("requested chunk exceeds the R2Star source range");
  }
  if (options.lower + options.count <= 3) {
    fail("chunk must contain at least one envelope endpoint n >= 3");
  }
  if (options.incoming_lower > options.incoming_upper) {
    fail("incoming directed state is reversed");
  }
  if (options.cross_check_serial && options.count > 1'000'000) {
    fail("serial cross-check exceeds its bounded range guard");
  }
  return options;
}

std::uint64_t integer_square_root(std::uint64_t value) {
  std::uint64_t lower = 0;
  std::uint64_t upper = value + 1;
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
  if (limit64 > std::numeric_limits<std::uint32_t>::max()) {
    fail("base-prime limit exceeds the exact sieve word size");
  }
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

std::vector<ExactFactorSupport> independently_factor_segment(
    std::uint64_t lower, std::size_t count,
    const std::vector<std::uint32_t>& primes) {
  std::vector<std::uint64_t> remaining(count);
  std::vector<ExactFactorSupport> result(count);
  for (std::size_t index = 0; index < count; ++index) {
    remaining[index] = lower + index;
  }
  for (std::uint32_t prime : primes) {
    const std::uint64_t first_number =
        ((lower + prime - 1) / prime) * prime;
    const std::size_t first =
        static_cast<std::size_t>(first_number - lower);
    for (std::size_t index = first; index < count; index += prime) {
      std::uint64_t& value = remaining[index];
      if (value % prime != 0) continue;
      result[index].append(prime);
      do {
        value /= prime;
      } while (value % prime == 0);
    }
  }
  for (std::size_t index = 0; index < count; ++index) {
    if (remaining[index] > 1) result[index].append(remaining[index]);
  }
  return result;
}

void hash_u64_be(sparkinterval::detail::Sha256* hasher,
                 std::uint64_t value) {
  std::array<unsigned char, 8> bytes{};
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (56U - 8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
void hash_directed_row(sparkinterval::detail::Sha256* hasher,
                       const TgR2StarDirectedRow& row) {
  // Keep the receipt format explicitly little-endian and independent of
  // struct padding. A single update also avoids compiler false positives in
  // the incremental SHA buffer analysis under aggressive inlining.
  std::array<unsigned char, 40> bytes{};
  auto put_u64 = [&](std::size_t offset, std::uint64_t value) {
    for (std::size_t index = 0; index < 8; ++index) {
      bytes[offset + index] =
          static_cast<unsigned char>(value >> (8U * index));
    }
  };
  auto put_u32 = [&](std::size_t offset, std::uint32_t value) {
    for (std::size_t index = 0; index < 4; ++index) {
      bytes[offset + index] =
          static_cast<unsigned char>(value >> (8U * index));
    }
  };
  put_u64(0, row.log_lower);
  put_u64(8, row.log_upper);
  put_u64(16, static_cast<std::uint64_t>(row.delta_lower));
  put_u64(24, static_cast<std::uint64_t>(row.delta_upper));
  put_u32(32, row.status);
  put_u32(36, row.reserved);
  hasher->update(bytes.data(), bytes.size());
}

bool capped_support_matches(const TgR2StarFactorSupport& actual,
                            const ExactFactorSupport& factors) {
  const std::uint32_t count =
      factors.count >= 3 ? 3 : factors.count;
  const std::uint64_t first = factors.count == 0 ? 0 : factors.factors[0];
  const std::uint64_t second =
      factors.count < 2 ? 0 : factors.factors[1];
  return actual.first_prime == first && actual.second_prime == second &&
         actual.distinct_prime_factor_count == count && actual.reserved == 0;
}

std::string u128_decimal(TgUnsigned128 value) {
  if (value.high == 0) return std::to_string(value.low);
  std::string reversed;
  while (value.high != 0 || value.low != 0) {
    // Divide the 128-bit value by ten one base-2^32 digit at a time.
    std::array<std::uint32_t, 4> words = {
        static_cast<std::uint32_t>(value.high >> 32),
        static_cast<std::uint32_t>(value.high),
        static_cast<std::uint32_t>(value.low >> 32),
        static_cast<std::uint32_t>(value.low),
    };
    std::uint64_t remainder = 0;
    for (std::uint32_t& word : words) {
      const std::uint64_t dividend = (remainder << 32) | word;
      word = static_cast<std::uint32_t>(dividend / 10);
      remainder = dividend % 10;
    }
    reversed.push_back(static_cast<char>('0' + remainder));
    value.high = (static_cast<std::uint64_t>(words[0]) << 32) | words[1];
    value.low = (static_cast<std::uint64_t>(words[2]) << 32) | words[3];
  }
  return std::string(reversed.rbegin(), reversed.rend());
}

std::string canonical_chunk_body(
    const Options& options, std::uint64_t upper_exclusive,
    const TgR2StarChunkSummary& summary,
    std::string_view minimum_slack,
    std::string_view factor_support_digest) {
  // This key order and punctuation exactly match Python json.dumps with
  // sort_keys=True, separators=(",", ":"), and ensure_ascii=True.
  return
      "{\"algorithm\":\"r2star_fixed_point_stream_v1\","
      "\"atom\":\"ramare-zuniga-lemma-6-2\","
      "\"bound_denominator\":100,"
      "\"bound_numerator\":193,"
      "\"factor_support_digest\":\"" + std::string(factor_support_digest) +
      "\",\"factor_support_encoding\":\"" + std::string(kFactorEncoding) +
      "\",\"gamma_lower\":" + std::to_string(kTgR2StarGammaLower) +
      ",\"gamma_upper\":" + std::to_string(kTgR2StarGammaUpper) +
      ",\"harmonic_terms\":" + std::to_string(kTgR2StarHarmonicTerms) +
      ",\"incoming_lower\":" + std::to_string(options.incoming_lower) +
      ",\"incoming_upper\":" + std::to_string(options.incoming_upper) +
      ",\"lower\":" + std::to_string(options.lower) +
      ",\"minimum_slack_index\":" +
      std::to_string(summary.minimum_slack_index) +
      ",\"minimum_squared_slack\":" + std::string(minimum_slack) +
      ",\"outgoing_lower\":" + std::to_string(summary.outgoing_lower) +
      ",\"outgoing_upper\":" + std::to_string(summary.outgoing_upper) +
      ",\"previous_hash\":\"" + options.previous_hash +
      "\",\"scale_bits\":" + std::to_string(kTgR2StarScaleBits) +
      ",\"schema_version\":1,\"series_terms\":" +
      std::to_string(kTgR2StarSeriesTerms) + ",\"upper\":" +
      std::to_string(upper_exclusive) + "}";
}

std::string json_escape(std::string_view value) {
  std::string result;
  for (char character : value) {
    if (character == '"' || character == '\\') result.push_back('\\');
    result.push_back(character);
  }
  return result;
}

bool same_summary(const TgR2StarChunkSummary& left,
                  const TgR2StarChunkSummary& right) {
  if (left.status != right.status ||
      left.first_bad_index != right.first_bad_index ||
      left.reserved != right.reserved) {
    return false;
  }
  // Rejected summaries expose only the fail-closed status and its first bad
  // row.  Partially accumulated output/minimum fields are not chunk output.
  if (left.status !=
      static_cast<std::uint32_t>(TgR2StarChunkStatus::valid)) {
    return true;
  }
  return left.outgoing_lower == right.outgoing_lower &&
         left.outgoing_upper == right.outgoing_upper &&
         left.minimum_squared_slack.low ==
             right.minimum_squared_slack.low &&
         left.minimum_squared_slack.high ==
             right.minimum_squared_slack.high &&
         left.minimum_slack_index == right.minimum_slack_index;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const std::size_t count = static_cast<std::size_t>(options.count);
  const std::uint64_t upper_inclusive = options.lower + options.count - 1;
  const std::uint64_t upper_exclusive = upper_inclusive + 1;
  const std::vector<std::uint32_t> primes =
      exact_primes_upto(integer_square_root(upper_inclusive));

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device; use --allow-other-device only for "
         "explicit cross-device testing",
         4);
  }
  if (options.device >= device_count) fail("requested CUDA device is unavailable", 4);
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));
  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if ((std::string_view(properties.name) != "NVIDIA GB10" ||
       properties.major != 12 || properties.minor != 1) &&
      !options.allow_other_device) {
    fail("expected an NVIDIA GB10 with compute capability 12.1; use "
         "--allow-other-device only for explicit cross-device testing",
         4);
  }

  const std::size_t factor_bytes = count * sizeof(TgR2StarFactorSupport);
  const std::size_t row_bytes = count * sizeof(TgR2StarDirectedRow);
  const std::size_t prime_bytes = primes.size() * sizeof(std::uint32_t);
  const std::size_t transition_block_count =
      1 + (count - 1) / kTgR2StarTransitionBlockRows;
  std::uint32_t* device_primes = nullptr;
  TgR2StarFactorSupport* device_factors = nullptr;
  TgR2StarDirectedRow* device_rows = nullptr;
  std::int64_t* device_prefix_lower = nullptr;
  std::int64_t* device_prefix_upper = nullptr;
  TgR2StarPrefixBlock* device_prefix_blocks = nullptr;
  TgR2StarEnvelopeRow* device_envelope_rows = nullptr;
  TgR2StarEnvelopeBlock* device_envelope_blocks = nullptr;
  TgR2StarChunkSummary* device_summary = nullptr;
  TgR2StarChunkSummary* device_serial_summary = nullptr;
  if (!primes.empty()) {
    check_cuda("cudaMalloc(primes)",
               cudaMalloc(reinterpret_cast<void**>(&device_primes), prime_bytes));
    check_cuda("cudaMemcpy(primes)",
               cudaMemcpy(device_primes, primes.data(), prime_bytes,
                          cudaMemcpyHostToDevice));
  }
  check_cuda("cudaMalloc(factors)",
             cudaMalloc(reinterpret_cast<void**>(&device_factors), factor_bytes));
  check_cuda("cudaMalloc(rows)",
             cudaMalloc(reinterpret_cast<void**>(&device_rows), row_bytes));
  check_cuda("cudaMalloc(prefix_lower)",
             cudaMalloc(reinterpret_cast<void**>(&device_prefix_lower),
                        count * sizeof(std::int64_t)));
  check_cuda("cudaMalloc(prefix_upper)",
             cudaMalloc(reinterpret_cast<void**>(&device_prefix_upper),
                        count * sizeof(std::int64_t)));
  check_cuda("cudaMalloc(prefix_blocks)",
             cudaMalloc(reinterpret_cast<void**>(&device_prefix_blocks),
                        transition_block_count *
                            sizeof(TgR2StarPrefixBlock)));
  check_cuda("cudaMalloc(envelope_rows)",
             cudaMalloc(reinterpret_cast<void**>(&device_envelope_rows),
                        count * sizeof(TgR2StarEnvelopeRow)));
  check_cuda("cudaMalloc(envelope_blocks)",
             cudaMalloc(reinterpret_cast<void**>(&device_envelope_blocks),
                        transition_block_count *
                            sizeof(TgR2StarEnvelopeBlock)));
  check_cuda("cudaMalloc(summary)",
             cudaMalloc(reinterpret_cast<void**>(&device_summary),
                        sizeof(TgR2StarChunkSummary)));
  if (options.cross_check_serial) {
    check_cuda("cudaMalloc(serial_summary)",
               cudaMalloc(reinterpret_cast<void**>(&device_serial_summary),
                          sizeof(TgR2StarChunkSummary)));
  }

  cudaEvent_t start = nullptr;
  cudaEvent_t after_factor = nullptr;
  cudaEvent_t after_rows = nullptr;
  cudaEvent_t before_parallel = nullptr;
  cudaEvent_t after_parallel = nullptr;
  cudaEvent_t stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(after_factor)", cudaEventCreate(&after_factor));
  check_cuda("cudaEventCreate(after_rows)", cudaEventCreate(&after_rows));
  check_cuda("cudaEventCreate(before_parallel)",
             cudaEventCreate(&before_parallel));
  check_cuda("cudaEventCreate(after_parallel)",
             cudaEventCreate(&after_parallel));
  check_cuda("cudaEventCreate(stop)", cudaEventCreate(&stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  check_cuda("factor-support launch",
             launch_tg_r2star_factor_support(
                 options.lower, count, device_primes, primes.size(),
                 device_factors));
  check_cuda("cudaEventRecord(after_factor)", cudaEventRecord(after_factor));
  check_cuda("directed-row launch",
             launch_tg_r2star_directed_rows(
                 options.lower, count, device_factors, device_rows));
  check_cuda("cudaEventRecord(after_rows)", cudaEventRecord(after_rows));

  std::vector<TgR2StarFactorSupport> factors(count);
  std::vector<TgR2StarDirectedRow> rows(count);
  check_cuda("cudaMemcpy(factors)",
             cudaMemcpy(factors.data(), device_factors, factor_bytes,
                        cudaMemcpyDeviceToHost));
  check_cuda("cudaMemcpy(rows)",
             cudaMemcpy(rows.data(), device_rows, row_bytes,
                        cudaMemcpyDeviceToHost));

  const auto host_start = std::chrono::steady_clock::now();
  const std::vector<ExactFactorSupport> exact_factor_rows =
      independently_factor_segment(options.lower, count, primes);
  sparkinterval::detail::Sha256 factor_hasher;
  factor_hasher.update(kFactorEncoding.data(), kFactorEncoding.size());
  const unsigned char zero = 0;
  factor_hasher.update(&zero, 1);
  sparkinterval::detail::Sha256 row_hasher;
  std::uint64_t factor_mismatches = 0;
  std::uint64_t first_factor_mismatch = 0;
  std::uint64_t exact_fallback_rows = 0;
  std::uint64_t integer_overflow_rows = 0;
  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t number = options.lower + index;
    const ExactFactorSupport& exact = exact_factor_rows[index];
    hash_u64_be(&factor_hasher, number);
    hash_u64_be(&factor_hasher, exact.count);
    for (std::uint32_t factor_index = 0; factor_index < exact.count;
         ++factor_index) {
      hash_u64_be(&factor_hasher, exact.factors[factor_index]);
    }
    if (!capped_support_matches(factors[index], exact)) {
      if (factor_mismatches == 0) first_factor_mismatch = number;
      ++factor_mismatches;
    }

    TgR2StarDirectedRow& row = rows[index];
    if (row.status == static_cast<std::uint32_t>(
                          TgR2StarRowStatus::log_resolution_ambiguous)) {
      row = exact_directed_row(number, exact);
      ++exact_fallback_rows;
    } else if (row.status == static_cast<std::uint32_t>(
                                 TgR2StarRowStatus::fixed_point_overflow)) {
      ++integer_overflow_rows;
    }
    if (row.status !=
        static_cast<std::uint32_t>(TgR2StarRowStatus::valid)) {
      fail("directed fixed-point row rejected at n=" +
               std::to_string(number) +
               " with status=" + std::to_string(row.status),
           5);
    }
    hash_directed_row(&row_hasher, row);
  }
  const auto host_stop = std::chrono::steady_clock::now();
  const double host_milliseconds =
      std::chrono::duration<double, std::milli>(host_stop - host_start).count();
  const std::string factor_digest =
      sparkinterval::lowercase_hex(factor_hasher.finish());
  const std::string row_digest =
      sparkinterval::lowercase_hex(row_hasher.finish());

  if (factor_mismatches != 0) {
    fail("GPU factor support disagrees with independent host factorization at n=" +
             std::to_string(first_factor_mismatch),
         5);
  }
  if (exact_fallback_rows != 0) {
    check_cuda("cudaMemcpy(exact fallback rows)",
               cudaMemcpy(device_rows, rows.data(), row_bytes,
                          cudaMemcpyHostToDevice));
  }
  check_cuda("cudaEventRecord(before_parallel)",
             cudaEventRecord(before_parallel));
  check_cuda("parallel chunk-transition launch",
             launch_tg_r2star_parallel_chunk_transition(
                 options.lower, count, device_rows, options.incoming_lower,
                 options.incoming_upper, device_prefix_lower,
                 device_prefix_upper, device_prefix_blocks,
                 device_envelope_rows, device_envelope_blocks,
                 device_summary));
  check_cuda("cudaEventRecord(after_parallel)",
             cudaEventRecord(after_parallel));
  if (options.cross_check_serial) {
    check_cuda("serial chunk-transition launch",
               launch_tg_r2star_chunk_transition(
                   options.lower, count, device_rows, options.incoming_lower,
                   options.incoming_upper, device_serial_summary));
  }
  check_cuda("cudaEventRecord(stop)", cudaEventRecord(stop));
  check_cuda("cudaEventSynchronize(stop)", cudaEventSynchronize(stop));
  float kernel_milliseconds = 0.0F;
  float factor_kernel_milliseconds = 0.0F;
  float directed_row_kernel_milliseconds = 0.0F;
  float parallel_transition_kernel_milliseconds = 0.0F;
  float serial_reference_kernel_milliseconds = 0.0F;
  check_cuda("cudaEventElapsedTime",
             cudaEventElapsedTime(&kernel_milliseconds, start, stop));
  check_cuda("cudaEventElapsedTime(factor)",
             cudaEventElapsedTime(&factor_kernel_milliseconds, start,
                                  after_factor));
  check_cuda("cudaEventElapsedTime(rows)",
             cudaEventElapsedTime(&directed_row_kernel_milliseconds,
                                  after_factor, after_rows));
  check_cuda("cudaEventElapsedTime(parallel_transition)",
             cudaEventElapsedTime(&parallel_transition_kernel_milliseconds,
                                  before_parallel, after_parallel));
  if (options.cross_check_serial) {
    check_cuda("cudaEventElapsedTime(serial_reference)",
               cudaEventElapsedTime(&serial_reference_kernel_milliseconds,
                                    after_parallel, stop));
  }

  TgR2StarChunkSummary summary{};
  TgR2StarChunkSummary serial_summary{};
  check_cuda("cudaMemcpy(summary)",
             cudaMemcpy(&summary, device_summary, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  if (options.cross_check_serial) {
    check_cuda("cudaMemcpy(serial_summary)",
               cudaMemcpy(&serial_summary, device_serial_summary,
                          sizeof(serial_summary), cudaMemcpyDeviceToHost));
  }
  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(after_factor)", cudaEventDestroy(after_factor));
  check_cuda("cudaEventDestroy(after_rows)", cudaEventDestroy(after_rows));
  check_cuda("cudaEventDestroy(before_parallel)",
             cudaEventDestroy(before_parallel));
  check_cuda("cudaEventDestroy(after_parallel)",
             cudaEventDestroy(after_parallel));
  check_cuda("cudaEventDestroy(stop)", cudaEventDestroy(stop));
  if (device_primes != nullptr) check_cuda("cudaFree(primes)", cudaFree(device_primes));
  check_cuda("cudaFree(factors)", cudaFree(device_factors));
  check_cuda("cudaFree(rows)", cudaFree(device_rows));
  check_cuda("cudaFree(prefix_lower)", cudaFree(device_prefix_lower));
  check_cuda("cudaFree(prefix_upper)", cudaFree(device_prefix_upper));
  check_cuda("cudaFree(prefix_blocks)", cudaFree(device_prefix_blocks));
  check_cuda("cudaFree(envelope_rows)", cudaFree(device_envelope_rows));
  check_cuda("cudaFree(envelope_blocks)", cudaFree(device_envelope_blocks));
  check_cuda("cudaFree(summary)", cudaFree(device_summary));
  if (device_serial_summary != nullptr) {
    check_cuda("cudaFree(serial_summary)", cudaFree(device_serial_summary));
  }

  if (options.cross_check_serial && !same_summary(summary, serial_summary)) {
    fail("blocked CUDA transition disagrees with the retained serial reference "
         "(parallel status=" + std::to_string(summary.status) +
         ", serial status=" + std::to_string(serial_summary.status) +
         ", parallel first_bad=" +
         std::to_string(summary.first_bad_index) +
         ", serial first_bad=" +
         std::to_string(serial_summary.first_bad_index) + ")",
         5);
  }

  if (summary.status !=
      static_cast<std::uint32_t>(TgR2StarChunkStatus::valid)) {
    fail("GPU chunk transition rejected at n=" +
             std::to_string(summary.first_bad_index) +
             " with status=" + std::to_string(summary.status),
         5);
  }

  const std::string minimum_slack = u128_decimal(summary.minimum_squared_slack);
  const std::string canonical_body = canonical_chunk_body(
      options, upper_exclusive, summary, minimum_slack, factor_digest);
  const std::string record_hash = sparkinterval::sha256_hex(
      canonical_body.data(), canonical_body.size());

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));
  std::cout
      << std::setprecision(17)
      << "{\n"
      << "  \"receipt_schema\": \"sparkinterval.r2star-bounded-chunk.v1\",\n"
      << "  \"classification\": "
         "\"bounded_exact_python_contract_chunk_not_full_atom_proof\",\n"
      << "  \"chunk\": {\n"
      << "    \"schema_version\": 1,\n"
      << "    \"lower\": " << options.lower << ",\n"
      << "    \"upper\": " << upper_exclusive << ",\n"
      << "    \"scale_bits\": " << kTgR2StarScaleBits << ",\n"
      << "    \"series_terms\": " << kTgR2StarSeriesTerms << ",\n"
      << "    \"harmonic_terms\": " << kTgR2StarHarmonicTerms << ",\n"
      << "    \"bound_numerator\": 193,\n"
      << "    \"bound_denominator\": 100,\n"
      << "    \"gamma_lower\": " << kTgR2StarGammaLower << ",\n"
      << "    \"gamma_upper\": " << kTgR2StarGammaUpper << ",\n"
      << "    \"incoming_lower\": " << options.incoming_lower << ",\n"
      << "    \"incoming_upper\": " << options.incoming_upper << ",\n"
      << "    \"outgoing_lower\": " << summary.outgoing_lower << ",\n"
      << "    \"outgoing_upper\": " << summary.outgoing_upper << ",\n"
      << "    \"minimum_squared_slack\": " << minimum_slack << ",\n"
      << "    \"minimum_slack_index\": " << summary.minimum_slack_index << ",\n"
      << "    \"factor_support_digest\": \"" << factor_digest << "\",\n"
      << "    \"previous_hash\": \"" << options.previous_hash << "\",\n"
      << "    \"record_hash\": \"" << record_hash << "\"\n"
      << "  },\n"
      << "  \"factor_support_encoding\": \"" << kFactorEncoding << "\",\n"
      << "  \"factor_support_digest_producer\": "
         "\"independent_host_segmented_exact_factorization_v1\",\n"
      << "  \"gpu_capped_factor_support_matches_host\": true,\n"
      << "  \"directed_rows_sha256_le_v1\": \"" << row_digest << "\",\n"
      << "  \"log_algorithm\": "
         "\"q64_directed_atanh_with_exact_rational_host_fallback_v1\",\n"
      << "  \"ambiguous_log_rows\": " << exact_fallback_rows << ",\n"
      << "  \"exact_rational_fallback_rows\": " << exact_fallback_rows
      << ",\n"
      << "  \"integer_overflow_rows\": " << integer_overflow_rows << ",\n"
      << "  \"prefix_implementation\": "
         "\"deterministic_blocked_exact_scan_v1\",\n"
      << "  \"serial_cross_check_performed\": "
      << (options.cross_check_serial ? "true" : "false") << ",\n"
      << "  \"device_name\": \"" << json_escape(properties.name) << "\",\n"
      << "  \"compute_capability\": \"" << properties.major << '.'
      << properties.minor << "\",\n"
      << "  \"cuda_driver_api_version\": " << driver_version << ",\n"
      << "  \"cuda_runtime_version\": " << runtime_version << ",\n"
      << "  \"kernel_milliseconds\": " << kernel_milliseconds << ",\n"
      << "  \"factor_kernel_milliseconds\": "
      << factor_kernel_milliseconds << ",\n"
      << "  \"directed_row_kernel_milliseconds\": "
      << directed_row_kernel_milliseconds << ",\n"
      << "  \"parallel_transition_kernel_milliseconds\": "
      << parallel_transition_kernel_milliseconds << ",\n"
      << "  \"serial_reference_kernel_milliseconds\": "
      << serial_reference_kernel_milliseconds << ",\n"
      << "  \"independent_factor_check_milliseconds\": "
      << host_milliseconds << ",\n"
      << "  \"full_source_range\": false,\n"
      << "  \"python_contract_replay_required\": true,\n"
      << "  \"hash_chain_is_integrity_not_authentication\": true,\n"
      << "  \"lean_atom_discharged\": false,\n"
      << "  \"proves_any_external_atom\": false\n"
      << "}\n";
  return 0;
}

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Independent, CPU-only arithmetic replay for the retained R2Star campaign.
//
// This executable does not include or call the CUDA producer.  It reconstructs
// each integer's complete distinct-prime-factor support, the directed Q32
// logarithm/coefficient row, the prefix interval, and the squared envelope.
// A compact, line-oriented plan supplies only the commitments already present
// in the retained runner receipts.  Every supplied value is treated as an
// expectation, never as arithmetic input other than the chunk's incoming
// prefix state.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/measured_worker_scope.hpp"
#include "sparkinterval/tg_r2star_replay_segments.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <boost/multiprecision/cpp_int.hpp>

namespace {

using boost::multiprecision::cpp_int;
__extension__ typedef unsigned __int128 u128;

constexpr std::string_view kPlanHeader =
    "sparkinterval-r2star-arithmetic-replay-plan-v1";
constexpr std::string_view kBenchmarkPlanHeader =
    "sparkinterval-r2star-arithmetic-replay-benchmark-plan-v1";
constexpr std::string_view kFactorEncoding =
    "r2star-distinct-prime-support-u64be-v1";
constexpr std::uint64_t kSourceLimit = 21'000'000'000ULL;
constexpr std::uint64_t kMaximumChunkRows = 1'000'000ULL;
constexpr std::uint32_t kSeriesTerms = 20;
constexpr std::uint64_t kGammaLower = 2'479'051'107ULL;
constexpr std::uint64_t kGammaUpper = 2'479'194'040ULL;
constexpr std::uint64_t kBoundNumerator = 193;
constexpr std::uint64_t kBoundDenominator = 100;
constexpr std::uint64_t kMaximumEnvelopeMagnitude =
    std::numeric_limits<std::uint64_t>::max() / kBoundDenominator;
constexpr std::uint64_t kMaximumPlanBytes = 64ULL << 20;

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

template <typename Integer>
Integer parse_integer(std::string_view text, const char* name) {
  if (text.empty() || text.front() == '+' ||
      text == "-0" ||
      (text.size() > 1 && text.front() == '0') ||
      (text.size() > 2 && text.front() == '-' && text[1] == '0')) {
    fail(std::string(name) + " is not a canonical decimal integer");
  }
  Integer value{};
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, value);
  if (parsed.ec != std::errc{} || parsed.ptr != end) {
    fail(std::string(name) + " is outside its integer range");
  }
  return value;
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

u128 parse_u128_decimal(std::string_view text, const char* name) {
  if (text.empty() || (text.size() > 1 && text.front() == '0')) {
    fail(std::string(name) + " is not a canonical nonnegative integer");
  }
  constexpr u128 maximum = ~static_cast<u128>(0);
  u128 value = 0;
  for (char character : text) {
    if (character < '0' || character > '9') {
      fail(std::string(name) + " is not a nonnegative decimal integer");
    }
    const unsigned int digit = static_cast<unsigned int>(character - '0');
    if (value > (maximum - digit) / 10) {
      fail(std::string(name) + " exceeds unsigned 128-bit range");
    }
    value *= 10;
    value += digit;
  }
  return value;
}

std::vector<std::string_view> split_tabs(const std::string& line) {
  std::vector<std::string_view> fields;
  std::size_t begin = 0;
  while (true) {
    const std::size_t separator = line.find('\t', begin);
    fields.emplace_back(line.data() + begin,
                        (separator == std::string::npos ? line.size()
                                                       : separator) -
                            begin);
    if (separator == std::string::npos) break;
    begin = separator + 1;
  }
  return fields;
}

struct ChunkExpectation {
  std::uint64_t lower = 0;
  std::uint64_t upper = 0;
  std::int64_t incoming_lower = 0;
  std::int64_t incoming_upper = 0;
  std::int64_t outgoing_lower = 0;
  std::int64_t outgoing_upper = 0;
  u128 minimum_squared_slack = 0;
  std::uint64_t minimum_slack_index = 0;
  std::string factor_support_digest;
  std::string directed_rows_digest;
  std::uint64_t exact_fallback_rows = 0;
};

struct ReplayPlan {
  bool benchmark_only = false;
  std::uint64_t source_lower = 1;
  std::uint64_t source_upper_exclusive = 0;
  std::uint64_t expected_limit = 0;
  std::vector<ChunkExpectation> chunks;
};

ReplayPlan load_plan(const std::string& path) {
  std::ifstream source(path, std::ios::binary | std::ios::ate);
  if (!source) fail("cannot open replay plan");
  const std::streamoff size = source.tellg();
  if (size < 0 || static_cast<std::uint64_t>(size) > kMaximumPlanBytes) {
    fail("replay plan exceeds the bounded size limit");
  }
  if (size == 0) fail("replay plan is empty");
  source.seekg(size - 1);
  char final_character = '\0';
  source.get(final_character);
  if (!source || final_character != '\n') {
    fail("replay plan must end with exactly an LF-delimited row");
  }
  source.clear();
  source.seekg(0);
  std::string line;
  if (!std::getline(source, line) ||
      (line != kPlanHeader && line != kBenchmarkPlanHeader)) {
    fail("replay plan has the wrong exact header");
  }
  ReplayPlan plan;
  plan.benchmark_only = line == kBenchmarkPlanHeader;
  if (!std::getline(source, line)) {
    fail(plan.benchmark_only ? "replay plan omits source_range"
                             : "replay plan omits expected_limit");
  }
  const auto range_fields = split_tabs(line);
  if (plan.benchmark_only) {
    if (range_fields.size() != 3 || range_fields[0] != "source_range") {
      fail("benchmark replay plan has a malformed source_range row");
    }
    plan.source_lower =
        parse_integer<std::uint64_t>(range_fields[1], "source lower");
    plan.source_upper_exclusive =
        parse_integer<std::uint64_t>(range_fields[2],
                                     "source upper exclusive");
    if (plan.source_lower < 1 ||
        plan.source_upper_exclusive <= plan.source_lower ||
        plan.source_upper_exclusive > kSourceLimit + 1) {
      fail("benchmark source range lies outside the R2Star source domain");
    }
    plan.expected_limit = plan.source_upper_exclusive - 1;
  } else {
    if (range_fields.size() != 2 ||
        range_fields[0] != "expected_limit") {
      fail("replay plan has a malformed expected_limit row");
    }
    plan.expected_limit =
        parse_integer<std::uint64_t>(range_fields[1], "expected_limit");
    if (plan.expected_limit < 3 || plan.expected_limit > kSourceLimit) {
      fail("expected_limit lies outside the R2Star source domain");
    }
    plan.source_upper_exclusive = plan.expected_limit + 1;
  }

  std::size_t line_number = 2;
  while (std::getline(source, line)) {
    ++line_number;
    if (line.empty() || line.find('\r') != std::string::npos) {
      fail("replay plan contains an empty or non-LF row at line " +
           std::to_string(line_number));
    }
    const auto fields = split_tabs(line);
    if (fields.size() != 12 || fields[0] != "chunk") {
      fail("replay plan chunk has the wrong exact field count at line " +
           std::to_string(line_number));
    }
    ChunkExpectation chunk;
    chunk.lower = parse_integer<std::uint64_t>(fields[1], "chunk lower");
    chunk.upper = parse_integer<std::uint64_t>(fields[2], "chunk upper");
    chunk.incoming_lower =
        parse_integer<std::int64_t>(fields[3], "incoming lower");
    chunk.incoming_upper =
        parse_integer<std::int64_t>(fields[4], "incoming upper");
    chunk.outgoing_lower =
        parse_integer<std::int64_t>(fields[5], "outgoing lower");
    chunk.outgoing_upper =
        parse_integer<std::int64_t>(fields[6], "outgoing upper");
    chunk.minimum_squared_slack =
        parse_u128_decimal(fields[7], "minimum squared slack");
    chunk.minimum_slack_index =
        parse_integer<std::uint64_t>(fields[8], "minimum slack index");
    if (!valid_digest(fields[9]) || !valid_digest(fields[10])) {
      fail("replay plan contains a malformed SHA-256 digest");
    }
    chunk.factor_support_digest = std::string(fields[9]);
    chunk.directed_rows_digest = std::string(fields[10]);
    chunk.exact_fallback_rows =
        parse_integer<std::uint64_t>(fields[11], "exact fallback rows");
    plan.chunks.push_back(std::move(chunk));
  }
  if (!source.eof()) fail("cannot read the complete replay plan");
  if (plan.chunks.empty()) fail("replay plan contains no chunks");

  const ChunkExpectation* previous = nullptr;
  for (std::size_t index = 0; index < plan.chunks.size(); ++index) {
    const ChunkExpectation& chunk = plan.chunks[index];
    if (chunk.lower < 1 || chunk.upper <= chunk.lower ||
        chunk.upper > plan.expected_limit + 1 ||
        chunk.upper - chunk.lower > kMaximumChunkRows ||
        chunk.upper <= 3) {
      fail("replay plan chunk range is invalid at index " +
           std::to_string(index));
    }
    if (chunk.incoming_lower > chunk.incoming_upper ||
        chunk.outgoing_lower > chunk.outgoing_upper ||
        chunk.minimum_slack_index < std::max<std::uint64_t>(3, chunk.lower) ||
        chunk.minimum_slack_index >= chunk.upper ||
        chunk.exact_fallback_rows > chunk.upper - chunk.lower) {
      fail("replay plan chunk commitment is invalid at index " +
           std::to_string(index));
    }
    if (previous == nullptr) {
      if (chunk.lower != plan.source_lower) {
        fail("replay plan does not begin at its declared source lower bound");
      }
      if (!plan.benchmark_only &&
          (chunk.incoming_lower != 0 || chunk.incoming_upper != 0)) {
        fail("replay plan is not rooted at the zero source state");
      }
    } else if (chunk.lower != previous->upper ||
               chunk.incoming_lower != previous->outgoing_lower ||
               chunk.incoming_upper != previous->outgoing_upper) {
      fail("replay plan breaks its range or directed-state chain at index " +
           std::to_string(index));
    }
    previous = &chunk;
  }
  if (previous->upper != plan.source_upper_exclusive) {
    fail(plan.benchmark_only
             ? "benchmark replay plan does not cover its declared source range"
             : "replay plan does not end immediately after expected_limit");
  }
  return plan;
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

std::vector<std::uint32_t> primes_upto(std::uint64_t limit64) {
  if (limit64 < 2) return {};
  if (limit64 > std::numeric_limits<std::uint32_t>::max()) {
    fail("base-prime limit exceeds uint32");
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
  std::vector<std::uint32_t> result;
  for (std::uint32_t candidate = 2; candidate <= limit; ++candidate) {
    if (!composite[candidate]) result.push_back(candidate);
  }
  return result;
}

struct FactorSupport {
  std::array<std::uint64_t, 10> factors{};
  std::uint32_t count = 0;

  void append(std::uint64_t factor) {
    if (count >= factors.size()) {
      fail("factor support exceeds the source-range bound");
    }
    factors[count++] = factor;
  }
};

std::vector<FactorSupport> factor_segment(
    std::uint64_t lower, std::size_t count,
    const std::vector<std::uint32_t>& primes) {
  std::vector<std::uint64_t> remaining(count);
  std::vector<FactorSupport> supports(count);
  for (std::size_t index = 0; index < count; ++index) {
    remaining[index] = lower + index;
  }
  const std::uint64_t upper_inclusive = lower + count - 1;
  const std::uint64_t root = integer_square_root(upper_inclusive);
  for (std::uint32_t prime : primes) {
    if (prime > root) break;
    const std::uint64_t remainder = lower % prime;
    const std::uint64_t first_number =
        lower + (remainder == 0 ? 0 : prime - remainder);
    if (first_number > upper_inclusive) continue;
    for (std::size_t index =
             static_cast<std::size_t>(first_number - lower);
         index < count; index += prime) {
      std::uint64_t& value = remaining[index];
      if (value % prime != 0) continue;
      supports[index].append(prime);
      do {
        value /= prime;
      } while (value % prime == 0);
    }
  }
  for (std::size_t index = 0; index < count; ++index) {
    if (remaining[index] > 1) supports[index].append(remaining[index]);
  }
  return supports;
}

std::array<unsigned char, 8> encode_u64_be(std::uint64_t value) {
  std::array<unsigned char, 8> bytes{};
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (56U - 8U * index));
  }
  return bytes;
}

void hash_u64_be(sparkinterval::detail::Sha256* hasher,
                 std::uint64_t value) {
  const auto bytes = encode_u64_be(value);
  hasher->update(bytes.data(), bytes.size());
}

struct DirectedRow {
  std::uint64_t log_lower = 0;
  std::uint64_t log_upper = 0;
  std::int64_t delta_lower = 0;
  std::int64_t delta_upper = 0;
  std::uint32_t status = 0;
  std::uint32_t reserved = 0;
};

std::array<unsigned char, 40> encode_directed_row(const DirectedRow& row) {
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
  return bytes;
}

void hash_directed_row(sparkinterval::detail::Sha256* hasher,
                       const DirectedRow& row) {
  const auto bytes = encode_directed_row(row);
  hasher->update(bytes.data(), bytes.size());
}

bool add_u64(std::uint64_t left, std::uint64_t right,
             std::uint64_t* result) {
  *result = left + right;
  return *result >= left;
}

bool add_i64(std::int64_t left, std::int64_t right, std::int64_t* result) {
  if ((right > 0 &&
       left > std::numeric_limits<std::int64_t>::max() - right) ||
      (right < 0 &&
       left < std::numeric_limits<std::int64_t>::min() - right)) {
    return false;
  }
  *result = left + right;
  return true;
}

bool multiply_u128_u64(u128 value, std::uint64_t multiplier, u128* result) {
  constexpr u128 maximum = ~static_cast<u128>(0);
  if (multiplier != 0 && value > maximum / multiplier) return false;
  *result = value * multiplier;
  return true;
}

std::uint64_t ceil_div_u64(std::uint64_t numerator,
                           std::uint64_t denominator) {
  if (denominator == 0) fail("division by zero");
  return numerator / denominator + (numerator % denominator != 0);
}

struct PositiveLogIntervals {
  std::uint64_t lower_low = 0;
  std::uint64_t lower_high = 0;
  std::uint64_t upper_low = 0;
  std::uint64_t upper_high = 0;
};

bool directed_q64_ratio(std::uint64_t numerator, std::uint64_t denominator,
                        std::uint64_t* lower, std::uint64_t* upper) {
  if (denominator == 0 || numerator >= denominator) return false;
  const u128 scaled = static_cast<u128>(numerator) << 64;
  *lower = static_cast<std::uint64_t>(scaled / denominator);
  *upper = *lower + (scaled % denominator != 0);
  return *upper >= *lower;
}

std::uint64_t q64_mul_floor(std::uint64_t left, std::uint64_t right) {
  return static_cast<std::uint64_t>(
      (static_cast<u128>(left) * right) >> 64);
}

bool q64_mul_ceil(std::uint64_t left, std::uint64_t right,
                  std::uint64_t* result) {
  const u128 product = static_cast<u128>(left) * right;
  const std::uint64_t floor = static_cast<std::uint64_t>(product >> 64);
  *result = floor + (static_cast<std::uint64_t>(product) != 0);
  return *result >= floor;
}

bool positive_log_intervals(std::uint64_t numerator,
                            std::uint64_t denominator,
                            PositiveLogIntervals* output) {
  if (denominator == 0 || numerator < denominator ||
      numerator > 2 * denominator) {
    return false;
  }
  const std::uint64_t difference = numerator - denominator;
  if (difference == 0) {
    *output = {};
    return true;
  }
  const std::uint64_t sum = numerator + denominator;
  std::uint64_t z_lower = 0;
  std::uint64_t z_upper = 0;
  if (!directed_q64_ratio(difference, sum, &z_lower, &z_upper)) return false;
  const std::uint64_t z_squared_lower = q64_mul_floor(z_lower, z_lower);
  std::uint64_t z_squared_upper = 0;
  if (!q64_mul_ceil(z_upper, z_upper, &z_squared_upper)) return false;

  std::uint64_t power_lower = z_lower;
  std::uint64_t power_upper = z_upper;
  std::uint64_t partial_lower = 0;
  std::uint64_t partial_upper = 0;
  for (std::uint32_t index = 0; index < kSeriesTerms; ++index) {
    const std::uint64_t odd = 2 * index + 1;
    if (!add_u64(partial_lower, power_lower / odd, &partial_lower) ||
        !add_u64(partial_upper, ceil_div_u64(power_upper, odd),
                 &partial_upper)) {
      return false;
    }
    power_lower = q64_mul_floor(power_lower, z_squared_lower);
    if (!q64_mul_ceil(power_upper, z_squared_upper, &power_upper)) return false;
  }
  if (partial_lower > std::numeric_limits<std::uint64_t>::max() / 2 ||
      partial_upper > std::numeric_limits<std::uint64_t>::max() / 2 ||
      power_upper > std::numeric_limits<std::uint64_t>::max() / 2) {
    return false;
  }
  const std::uint64_t lower_low = 2 * partial_lower;
  const std::uint64_t lower_high = 2 * partial_upper;
  const std::uint64_t reduced_tail =
      ceil_div_u64(2 * power_upper, 2 * kSeriesTerms + 1);
  const std::uint64_t denominator_lower = 0 - z_squared_upper;
  if (denominator_lower == 0) return false;
  const u128 scaled_tail = static_cast<u128>(reduced_tail) << 64;
  const u128 quotient =
      (scaled_tail + denominator_lower - 1) / denominator_lower;
  if (quotient > std::numeric_limits<std::uint64_t>::max()) return false;
  const std::uint64_t tail_upper =
      static_cast<std::uint64_t>(quotient);
  std::uint64_t upper_high = 0;
  if (!add_u64(lower_high, tail_upper, &upper_high)) return false;
  *output =
      PositiveLogIntervals{lower_low, lower_high, lower_low, upper_high};
  return true;
}

bool q64_to_q32_floor(u128 value, std::uint64_t* result) {
  const u128 quotient = value >> 32;
  if (quotient > std::numeric_limits<std::uint64_t>::max()) return false;
  *result = static_cast<std::uint64_t>(quotient);
  return true;
}

bool q64_to_q32_ceil(u128 value, std::uint64_t* result) {
  if (!q64_to_q32_floor(value, result)) return false;
  if ((value & ((static_cast<u128>(1) << 32) - 1)) != 0) {
    if (*result == std::numeric_limits<std::uint64_t>::max()) return false;
    ++*result;
  }
  return true;
}

struct ExactFraction {
  cpp_int numerator = 0;
  cpp_int denominator = 1;

  ExactFraction() = default;
  ExactFraction(cpp_int n, cpp_int d = 1)
      : numerator(std::move(n)), denominator(std::move(d)) {
    if (denominator == 0) fail("exact rational has zero denominator");
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
  if (right.numerator == 0) fail("exact rational division by zero");
  return ExactFraction(left.numerator * right.denominator,
                       left.denominator * right.numerator);
}

ExactFraction operator*(const ExactFraction& value, std::uint64_t multiplier) {
  return ExactFraction(value.numerator * multiplier, value.denominator);
}

std::pair<ExactFraction, ExactFraction> exact_positive_log_bounds(
    std::uint64_t numerator, std::uint64_t denominator) {
  if (!(denominator <= numerator && numerator <= 2 * denominator)) {
    fail("exact positive-log fallback received an invalid ratio");
  }
  const ExactFraction z(cpp_int(numerator - denominator),
                        cpp_int(numerator + denominator));
  if (z.numerator == 0) return {ExactFraction(), ExactFraction()};
  const ExactFraction z_squared = z * z;
  ExactFraction power = z;
  ExactFraction partial;
  for (std::uint32_t index = 0; index < kSeriesTerms; ++index) {
    partial =
        partial + power / ExactFraction(cpp_int(2 * index + 1));
    power = power * z_squared;
  }
  const ExactFraction lower = partial * 2;
  const ExactFraction remainder =
      (power * 2) /
      (ExactFraction(cpp_int(2 * kSeriesTerms + 1)) *
       (ExactFraction(1) - z_squared));
  return {lower, lower + remainder};
}

std::pair<std::uint64_t, std::uint64_t> exact_fixed_log_bounds(
    std::uint64_t integer) {
  if (integer < 2) fail("exact log fallback requires n >= 2");
  std::uint32_t exponent = 0;
  for (std::uint64_t copy = integer; copy > 1; copy >>= 1) ++exponent;
  const std::uint64_t power_of_two = std::uint64_t{1} << exponent;
  const auto log_two = exact_positive_log_bounds(2, 1);
  const auto mantissa =
      exact_positive_log_bounds(integer, power_of_two);
  const ExactFraction lower = log_two.first * exponent + mantissa.first;
  const ExactFraction upper = log_two.second * exponent + mantissa.second;
  const cpp_int lower_scaled = lower.numerator << 32;
  const cpp_int upper_scaled = upper.numerator << 32;
  const cpp_int lower_floor = lower_scaled / lower.denominator;
  const cpp_int upper_ceil =
      (upper_scaled + upper.denominator - 1) / upper.denominator;
  if (lower_floor < 0 ||
      lower_floor > std::numeric_limits<std::uint64_t>::max() ||
      upper_ceil < 0 ||
      upper_ceil > std::numeric_limits<std::uint64_t>::max()) {
    fail("exact log fallback overflows uint64");
  }
  return {lower_floor.convert_to<std::uint64_t>(),
          upper_ceil.convert_to<std::uint64_t>()};
}

struct LogBounds {
  std::uint64_t lower = 0;
  std::uint64_t upper = 0;
  bool exact_fallback = false;
};

LogBounds directed_log_bounds(std::uint64_t integer) {
  if (integer < 2) fail("directed log requires n >= 2");
  std::uint32_t exponent = 0;
  for (std::uint64_t copy = integer; copy > 1; copy >>= 1) ++exponent;
  const std::uint64_t power_of_two = std::uint64_t{1} << exponent;
  PositiveLogIntervals log_two{};
  PositiveLogIntervals mantissa{};
  if (!positive_log_intervals(2, 1, &log_two) ||
      !positive_log_intervals(integer, power_of_two, &mantissa)) {
    fail("Q64 directed-log interval overflow");
  }
  const u128 lower_low =
      static_cast<u128>(mantissa.lower_low) +
      static_cast<u128>(log_two.lower_low) * exponent;
  const u128 lower_high =
      static_cast<u128>(mantissa.lower_high) +
      static_cast<u128>(log_two.lower_high) * exponent;
  const u128 upper_low =
      static_cast<u128>(mantissa.upper_low) +
      static_cast<u128>(log_two.upper_low) * exponent;
  const u128 upper_high =
      static_cast<u128>(mantissa.upper_high) +
      static_cast<u128>(log_two.upper_high) * exponent;
  std::uint64_t lower_candidate = 0;
  std::uint64_t lower_other = 0;
  std::uint64_t upper_candidate = 0;
  std::uint64_t upper_other = 0;
  if (!q64_to_q32_floor(lower_low, &lower_candidate) ||
      !q64_to_q32_floor(lower_high, &lower_other) ||
      !q64_to_q32_ceil(upper_low, &upper_candidate) ||
      !q64_to_q32_ceil(upper_high, &upper_other)) {
    fail("Q64-to-Q32 directed-log conversion overflow");
  }
  if (lower_candidate == lower_other &&
      upper_candidate == upper_other) {
    if (lower_candidate > upper_candidate) {
      fail("directed logarithm interval reversed");
    }
    return {lower_candidate, upper_candidate, false};
  }
  const auto exact = exact_fixed_log_bounds(integer);
  return {exact.first, exact.second, true};
}

struct FactorLogCache {
  std::vector<std::uint32_t> factors;
  std::vector<LogBounds> bounds;

  explicit FactorLogCache(const std::vector<std::uint32_t>& primes)
      : factors(primes) {
    bounds.reserve(factors.size());
    for (const std::uint32_t prime : factors) {
      bounds.push_back(directed_log_bounds(prime));
    }
  }

  bool find(std::uint64_t factor, LogBounds* result) const {
    if (factors.empty() || factor > factors.back()) return false;
    const auto position =
        std::lower_bound(factors.begin(), factors.end(), factor);
    if (position == factors.end() || *position != factor) {
      fail("factor-support row contains a nonprime cached factor");
    }
    *result = bounds[static_cast<std::size_t>(position - factors.begin())];
    return true;
  }
};

std::uint64_t product_shift32_floor(std::uint64_t left,
                                    std::uint64_t right,
                                    bool doubled) {
  u128 product = static_cast<u128>(left) * right;
  if (doubled) product *= 2;
  const u128 result = product >> 32;
  if (result > std::numeric_limits<std::uint64_t>::max()) {
    fail("coefficient product floor overflows uint64");
  }
  return static_cast<std::uint64_t>(result);
}

std::uint64_t product_shift32_ceil(std::uint64_t left,
                                   std::uint64_t right,
                                   bool doubled) {
  u128 product = static_cast<u128>(left) * right;
  if (doubled) product *= 2;
  const u128 result =
      (product + ((static_cast<u128>(1) << 32) - 1)) >> 32;
  if (result > std::numeric_limits<std::uint64_t>::max()) {
    fail("coefficient product ceil overflows uint64");
  }
  return static_cast<std::uint64_t>(result);
}

DirectedRow compute_row(std::uint64_t number, const FactorSupport& support,
                        bool* used_exact_fallback,
                        const FactorLogCache* factor_log_cache = nullptr) {
  DirectedRow row;
  bool fallback = false;
  LogBounds number_bounds{};
  bool have_number_bounds = false;
  if (number >= 2) {
    number_bounds = directed_log_bounds(number);
    have_number_bounds = true;
    row.log_lower = number_bounds.lower;
    row.log_upper = number_bounds.upper;
    fallback = fallback || number_bounds.exact_fallback;
  }
  auto factor_bounds = [&](std::uint64_t factor) {
    if (factor_log_cache != nullptr && have_number_bounds &&
        factor == number) {
      return number_bounds;
    }
    LogBounds cached{};
    if (factor_log_cache != nullptr &&
        factor_log_cache->find(factor, &cached)) {
      return cached;
    }
    return directed_log_bounds(factor);
  };
  std::int64_t coefficient_lower = 0;
  std::int64_t coefficient_upper = 0;
  if (support.count == 1) {
    const LogBounds bounds = factor_bounds(support.factors[0]);
    fallback = fallback || bounds.exact_fallback;
    const std::uint64_t lower_magnitude =
        product_shift32_ceil(bounds.upper, bounds.upper, false);
    const std::uint64_t upper_magnitude =
        product_shift32_floor(bounds.lower, bounds.lower, false);
    if (lower_magnitude >
            static_cast<std::uint64_t>(
                std::numeric_limits<std::int64_t>::max()) ||
        upper_magnitude >
            static_cast<std::uint64_t>(
                std::numeric_limits<std::int64_t>::max())) {
      fail("one-factor coefficient overflows int64");
    }
    coefficient_lower = -static_cast<std::int64_t>(lower_magnitude);
    coefficient_upper = -static_cast<std::int64_t>(upper_magnitude);
  } else if (support.count == 2) {
    const LogBounds left = factor_bounds(support.factors[0]);
    const LogBounds right = factor_bounds(support.factors[1]);
    fallback =
        fallback || left.exact_fallback || right.exact_fallback;
    const std::uint64_t lower =
        product_shift32_floor(left.lower, right.lower, true);
    const std::uint64_t upper =
        product_shift32_ceil(left.upper, right.upper, true);
    if (lower >
            static_cast<std::uint64_t>(
                std::numeric_limits<std::int64_t>::max()) ||
        upper >
            static_cast<std::uint64_t>(
                std::numeric_limits<std::int64_t>::max())) {
      fail("two-factor coefficient overflows int64");
    }
    coefficient_lower = static_cast<std::int64_t>(lower);
    coefficient_upper = static_cast<std::int64_t>(upper);
  }
  constexpr std::int64_t twice_gamma_lower =
      static_cast<std::int64_t>(2 * kGammaLower);
  constexpr std::int64_t twice_gamma_upper =
      static_cast<std::int64_t>(2 * kGammaUpper);
  if (!add_i64(coefficient_lower, twice_gamma_lower, &row.delta_lower) ||
      !add_i64(coefficient_upper, twice_gamma_upper, &row.delta_upper) ||
      row.delta_lower > row.delta_upper) {
    fail("directed coefficient row overflows or reverses");
  }
  *used_exact_fallback = fallback;
  return row;
}

class ChunkReplayAccumulator {
 public:
  explicit ChunkReplayAccumulator(const ChunkExpectation& expected,
                                  bool check_factor_digest = true,
                                  bool check_row_digest = true,
                                  bool check_transition = true)
      : expected_(expected),
        check_factor_digest_(check_factor_digest),
        check_row_digest_(check_row_digest),
        check_transition_(check_transition),
        prefix_lower_(expected.incoming_lower),
        prefix_upper_(expected.incoming_upper) {
    if (check_factor_digest_) {
      factor_hasher_.update(kFactorEncoding.data(), kFactorEncoding.size());
      const unsigned char zero = 0;
      factor_hasher_.update(&zero, 1);
    }
  }

  void consume(std::uint64_t number, const FactorSupport& support,
               const DirectedRow& row, bool used_exact_fallback) {
    if (check_factor_digest_) {
      hash_u64_be(&factor_hasher_, number);
      hash_u64_be(&factor_hasher_, support.count);
      for (std::uint32_t factor_index = 0; factor_index < support.count;
           ++factor_index) {
        hash_u64_be(&factor_hasher_, support.factors[factor_index]);
      }
    }
    if (check_row_digest_) hash_directed_row(&row_hasher_, row);
    if (!check_transition_) return;
    fallback_rows_ += static_cast<std::uint64_t>(used_exact_fallback);
    if (!add_i64(prefix_lower_, row.delta_lower, &prefix_lower_) ||
        !add_i64(prefix_upper_, row.delta_upper, &prefix_upper_) ||
        prefix_lower_ > prefix_upper_) {
      fail("prefix interval overflows or reverses at n=" +
           std::to_string(number));
    }
    if (number < 3) return;
    if (prefix_lower_ == std::numeric_limits<std::int64_t>::min() ||
        prefix_upper_ == std::numeric_limits<std::int64_t>::min()) {
      fail("prefix magnitude cannot be represented at n=" +
           std::to_string(number));
    }
    const std::uint64_t lower_magnitude =
        prefix_lower_ < 0 ? static_cast<std::uint64_t>(-prefix_lower_)
                          : static_cast<std::uint64_t>(prefix_lower_);
    const std::uint64_t upper_magnitude =
        prefix_upper_ < 0 ? static_cast<std::uint64_t>(-prefix_upper_)
                          : static_cast<std::uint64_t>(prefix_upper_);
    const std::uint64_t magnitude =
        std::max(lower_magnitude, upper_magnitude);
    if (magnitude > kMaximumEnvelopeMagnitude) {
      fail("squared envelope magnitude overflows at n=" +
           std::to_string(number));
    }
    const std::uint64_t scaled_magnitude = kBoundDenominator * magnitude;
    const u128 left =
        static_cast<u128>(scaled_magnitude) * scaled_magnitude;
    u128 right = static_cast<u128>(row.log_lower) * row.log_lower;
    if (!multiply_u128_u64(right, number, &right) ||
        !multiply_u128_u64(
            right, kBoundNumerator * kBoundNumerator, &right)) {
      fail("squared envelope right side overflows at n=" +
           std::to_string(number));
    }
    if (right < left) {
      fail("squared R2Star envelope fails at n=" + std::to_string(number));
    }
    const u128 slack = right - left;
    if (!have_minimum_ || slack < minimum_slack_) {
      have_minimum_ = true;
      minimum_slack_ = slack;
      minimum_index_ = number;
    }
  }

  void finish() {
    if (check_factor_digest_) {
      const std::string factor_digest =
          sparkinterval::lowercase_hex(factor_hasher_.finish());
      if (factor_digest != expected_.factor_support_digest) {
        fail("factor-support digest mismatch for chunk starting at " +
             std::to_string(expected_.lower));
      }
    }
    if (check_row_digest_) {
      const std::string row_digest =
          sparkinterval::lowercase_hex(row_hasher_.finish());
      if (row_digest != expected_.directed_rows_digest) {
        fail("directed-row digest mismatch for chunk starting at " +
             std::to_string(expected_.lower));
      }
    }
    if (!check_transition_) return;
    if (!have_minimum_) fail("chunk contains no envelope endpoint");
    if (prefix_lower_ != expected_.outgoing_lower ||
        prefix_upper_ != expected_.outgoing_upper) {
      fail("outgoing directed state mismatch for chunk starting at " +
           std::to_string(expected_.lower));
    }
    if (minimum_slack_ != expected_.minimum_squared_slack ||
        minimum_index_ != expected_.minimum_slack_index) {
      fail("minimum squared-slack witness mismatch for chunk starting at " +
           std::to_string(expected_.lower));
    }
    if (fallback_rows_ != expected_.exact_fallback_rows) {
      fail("exact-fallback row count mismatch for chunk starting at " +
           std::to_string(expected_.lower));
    }
  }

 private:
  const ChunkExpectation& expected_;
  bool check_factor_digest_;
  bool check_row_digest_;
  bool check_transition_;
  sparkinterval::detail::Sha256 factor_hasher_;
  sparkinterval::detail::Sha256 row_hasher_;
  std::int64_t prefix_lower_;
  std::int64_t prefix_upper_;
  u128 minimum_slack_ = 0;
  std::uint64_t minimum_index_ = 0;
  bool have_minimum_ = false;
  std::uint64_t fallback_rows_ = 0;
};

void verify_chunk(const ChunkExpectation& expected,
                  const std::vector<std::uint32_t>& primes) {
  const std::size_t count =
      static_cast<std::size_t>(expected.upper - expected.lower);
  const std::vector<FactorSupport> supports =
      factor_segment(expected.lower, count, primes);
  ChunkReplayAccumulator accumulator(expected);
  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t number = expected.lower + index;
    const FactorSupport& support = supports[index];
    bool used_exact_fallback = false;
    const DirectedRow row =
        compute_row(number, support, &used_exact_fallback);
    accumulator.consume(number, support, row, used_exact_fallback);
  }
  accumulator.finish();
}

struct ComputedReplaySegment {
  sparkinterval::R2StarReplaySegmentBoundary boundary;
  std::vector<unsigned char> factor_bytes;
  std::vector<DirectedRow> rows;
  std::vector<unsigned char> row_bytes;
  std::vector<unsigned char> exact_fallback;
};

ComputedReplaySegment compute_replay_segment(
    std::size_t ordinal, std::uint64_t lower, std::uint64_t upper,
    const std::vector<std::uint32_t>& primes,
    const FactorLogCache& factor_log_cache) {
  if (upper <= lower ||
      upper - lower > std::numeric_limits<std::size_t>::max()) {
    fail("parallel replay segment has an invalid range");
  }
  ComputedReplaySegment result;
  result.boundary = {ordinal, lower, upper};
  const std::size_t count = static_cast<std::size_t>(upper - lower);
  const std::vector<FactorSupport> supports =
      factor_segment(lower, count, primes);
  result.factor_bytes.reserve(count * 40);
  result.rows.reserve(count);
  result.row_bytes.reserve(count * 40);
  result.exact_fallback.reserve(count);
  for (std::size_t index = 0; index < count; ++index) {
    const FactorSupport& support = supports[index];
    auto append_u64 = [&](std::uint64_t value) {
      const auto bytes = encode_u64_be(value);
      result.factor_bytes.insert(
          result.factor_bytes.end(), bytes.begin(), bytes.end());
    };
    append_u64(lower + index);
    append_u64(support.count);
    for (std::uint32_t factor_index = 0; factor_index < support.count;
         ++factor_index) {
      append_u64(support.factors[factor_index]);
    }
    bool used_exact_fallback = false;
    result.rows.push_back(compute_row(
        lower + index, support, &used_exact_fallback,
        &factor_log_cache));
    const auto row_bytes = encode_directed_row(result.rows.back());
    result.row_bytes.insert(
        result.row_bytes.end(), row_bytes.begin(), row_bytes.end());
    result.exact_fallback.push_back(
        static_cast<unsigned char>(used_exact_fallback));
  }
  return result;
}

void verify_chunk_segmented(
    const ChunkExpectation& expected,
    const std::vector<std::uint32_t>& primes,
    const FactorLogCache& factor_log_cache, std::size_t requested_threads,
    std::size_t segment_rows) {
  const std::uint64_t count = expected.upper - expected.lower;
  const std::size_t segment_count =
      static_cast<std::size_t>((count + segment_rows - 1) / segment_rows);
  std::vector<std::unique_ptr<ComputedReplaySegment>> segments(segment_count);
  std::atomic<std::size_t> next{0};
  std::atomic<bool> failed{false};
  std::mutex error_mutex;
  std::string error;
  auto worker = [&]() {
    while (!failed.load(std::memory_order_acquire)) {
      const std::size_t index = next.fetch_add(1);
      if (index >= segment_count) return;
      try {
        const std::uint64_t lower =
            expected.lower + static_cast<std::uint64_t>(index) * segment_rows;
        const std::uint64_t upper =
            std::min(expected.upper,
                     lower + static_cast<std::uint64_t>(segment_rows));
        segments[index] = std::make_unique<ComputedReplaySegment>(
            compute_replay_segment(index, lower, upper, primes,
                                   factor_log_cache));
      } catch (const std::exception& exception) {
        {
          std::lock_guard<std::mutex> lock(error_mutex);
          if (error.empty()) {
            error = "segment " + std::to_string(index) + ": " +
                    exception.what();
          }
        }
        failed.store(true, std::memory_order_release);
        return;
      }
    }
  };
  const std::size_t thread_count =
      std::min(requested_threads, segment_count);
  std::vector<std::thread> workers;
  workers.reserve(thread_count);
  for (std::size_t index = 0; index < thread_count; ++index) {
    workers.emplace_back(worker);
  }
  for (std::thread& thread : workers) thread.join();
  if (failed) {
    fail(error.empty() ? "parallel replay segment failed" : error);
  }

  std::vector<sparkinterval::R2StarReplaySegmentBoundary> boundaries;
  boundaries.reserve(segment_count);
  for (std::size_t index = 0; index < segment_count; ++index) {
    if (segments[index] == nullptr) {
      fail("parallel replay omitted segment " + std::to_string(index));
    }
    boundaries.push_back(segments[index]->boundary);
  }
  if (!sparkinterval::is_exact_r2star_replay_partition(
          expected.lower, expected.upper, boundaries)) {
    fail("parallel replay segment partition is reordered, gapped, or "
         "overlapping");
  }
  for (const auto& segment_pointer : segments) {
    const ComputedReplaySegment& segment = *segment_pointer;
    const std::size_t local_count = segment.rows.size();
    if (segment.row_bytes.size() != local_count * 40 ||
        segment.exact_fallback.size() != local_count ||
        segment.boundary.upper - segment.boundary.lower != local_count) {
      fail("parallel replay segment payload has inconsistent length");
    }
  }

  // SHA-256 and the directed prefix are intentionally merged only in source
  // order.  Their three independent ordered folds may run concurrently, but
  // parallel workers never supply or choose an incoming prefix state.
  auto ordered_fold = [&](bool factor_digest, bool row_digest,
                          bool transition) {
    if (factor_digest) {
      sparkinterval::detail::Sha256 hasher;
      hasher.update(kFactorEncoding.data(), kFactorEncoding.size());
      const unsigned char zero = 0;
      hasher.update(&zero, 1);
      for (const auto& segment_pointer : segments) {
        const std::vector<unsigned char>& bytes =
            segment_pointer->factor_bytes;
        hasher.update(bytes.data(), bytes.size());
      }
      if (sparkinterval::lowercase_hex(hasher.finish()) !=
          expected.factor_support_digest) {
        fail("factor-support digest mismatch for chunk starting at " +
             std::to_string(expected.lower));
      }
    }
    if (row_digest) {
      sparkinterval::detail::Sha256 hasher;
      for (const auto& segment_pointer : segments) {
        const std::vector<unsigned char>& bytes = segment_pointer->row_bytes;
        hasher.update(bytes.data(), bytes.size());
      }
      if (sparkinterval::lowercase_hex(hasher.finish()) !=
          expected.directed_rows_digest) {
        fail("directed-row digest mismatch for chunk starting at " +
             std::to_string(expected.lower));
      }
    }
    if (transition) {
      ChunkReplayAccumulator accumulator(
          expected, false, false, true);
      const FactorSupport unused_support{};
      for (const auto& segment_pointer : segments) {
        const ComputedReplaySegment& segment = *segment_pointer;
        for (std::size_t index = 0; index < segment.rows.size(); ++index) {
          accumulator.consume(
              segment.boundary.lower + index, unused_support,
              segment.rows[index], segment.exact_fallback[index] != 0);
        }
      }
      accumulator.finish();
    }
  };
  std::vector<std::array<bool, 3>> fold_duties;
  if (requested_threads >= 3) {
    fold_duties = {{
        {true, false, false},
        {false, true, false},
        {false, false, true},
    }};
  } else if (requested_threads == 2) {
    fold_duties = {{
        {true, false, false},
        {false, true, true},
    }};
  } else {
    fold_duties = {{{true, true, true}}};
  }
  std::atomic<bool> fold_failed{false};
  std::mutex fold_error_mutex;
  std::string fold_error;
  auto fold_worker = [&](std::size_t index) {
    try {
      const auto& duties = fold_duties[index];
      ordered_fold(duties[0], duties[1], duties[2]);
    } catch (const std::exception& exception) {
      std::lock_guard<std::mutex> lock(fold_error_mutex);
      if (fold_error.empty()) {
        fold_error = "ordered fold " + std::to_string(index) + ": " +
                     exception.what();
      }
      fold_failed.store(true, std::memory_order_release);
    }
  };
  std::vector<std::thread> fold_workers;
  fold_workers.reserve(fold_duties.size());
  for (std::size_t index = 0; index < fold_duties.size(); ++index) {
    fold_workers.emplace_back(fold_worker, index);
  }
  for (std::thread& thread : fold_workers) thread.join();
  if (fold_failed.load(std::memory_order_acquire)) {
    fail(fold_error.empty() ? "ordered replay fold failed" : fold_error);
  }
}

struct Options {
  std::string plan;
  std::size_t threads = 1;
  std::size_t segment_rows = 0;
};

Options parse_options(int argc, char** argv) {
  Options options;
  const unsigned int hardware = std::thread::hardware_concurrency();
  options.threads = hardware == 0 ? 1 : std::min<unsigned int>(hardware, 32);
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--plan") {
      options.plan = std::string(require_value("--plan"));
    } else if (argument == "--threads") {
      options.threads =
          parse_integer<std::size_t>(require_value("--threads"), "threads");
    } else if (argument == "--segment-rows") {
      options.segment_rows = parse_integer<std::size_t>(
          require_value("--segment-rows"), "segment rows");
      if (options.segment_rows == 0) {
        fail("--segment-rows must lie in [1,1000000]");
      }
    } else if (argument == "--help") {
      std::cout
          << "usage: tg-r2star-arithmetic-replay --plan PATH "
             "[--threads N] [--segment-rows N]\n"
             "CPU-only full row-arithmetic replay of a gap-free retained "
             "R2Star receipt plan. Threads must lie in [1,64]. The optional "
             "segment size must lie in [1,1000000] and enables the bounded "
             "parallel segment candidate.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.plan.empty()) fail("--plan is required");
  if (options.threads < 1 || options.threads > 64) {
    fail("--threads must lie in [1,64]");
  }
  if (options.segment_rows > kMaximumChunkRows) {
    fail("--segment-rows must lie in [1,1000000]");
  }
  return options;
}

void replay_serial_chunks(const ReplayPlan& plan,
                          const std::vector<std::uint32_t>& primes,
                          std::size_t requested_threads) {
  const std::size_t thread_count =
      std::min(requested_threads, plan.chunks.size());
  std::atomic<std::size_t> next{0};
  std::atomic<bool> failed{false};
  std::mutex error_mutex;
  std::string error;
  auto worker = [&]() {
    while (!failed.load(std::memory_order_acquire)) {
      const std::size_t index = next.fetch_add(1);
      if (index >= plan.chunks.size()) return;
      try {
        verify_chunk(plan.chunks[index], primes);
      } catch (const std::exception& exception) {
        {
          std::lock_guard<std::mutex> lock(error_mutex);
          if (error.empty()) {
            error = "chunk " + std::to_string(index) + ": " + exception.what();
          }
        }
        failed.store(true, std::memory_order_release);
        return;
      }
    }
  };
  std::vector<std::thread> workers;
  workers.reserve(thread_count);
  for (std::size_t index = 0; index < thread_count; ++index) {
    workers.emplace_back(worker);
  }
  for (std::thread& thread : workers) thread.join();
  if (failed) fail(error.empty() ? "row arithmetic replay failed" : error);
}

void replay_segmented_chunks(const ReplayPlan& plan,
                             const std::vector<std::uint32_t>& primes,
                             std::size_t requested_threads,
                             std::size_t segment_rows) {
  const FactorLogCache factor_log_cache(primes);
  const std::size_t outer_threads =
      std::min(requested_threads, plan.chunks.size());
  const std::size_t inner_threads =
      std::max<std::size_t>(1, requested_threads / outer_threads);
  std::atomic<std::size_t> next{0};
  std::atomic<bool> failed{false};
  std::mutex error_mutex;
  std::string error;
  auto worker = [&]() {
    while (!failed.load(std::memory_order_acquire)) {
      const std::size_t index = next.fetch_add(1);
      if (index >= plan.chunks.size()) return;
      try {
        verify_chunk_segmented(plan.chunks[index], primes, factor_log_cache,
                               inner_threads, segment_rows);
      } catch (const std::exception& exception) {
        {
          std::lock_guard<std::mutex> lock(error_mutex);
          if (error.empty()) {
            error = "chunk " + std::to_string(index) + ": " +
                    exception.what();
          }
        }
        failed.store(true, std::memory_order_release);
        return;
      }
    }
  };
  std::vector<std::thread> workers;
  workers.reserve(outer_threads);
  for (std::size_t index = 0; index < outer_threads; ++index) {
    workers.emplace_back(worker);
  }
  for (std::thread& thread : workers) thread.join();
  if (failed) {
    fail(error.empty() ? "segmented row arithmetic replay failed" : error);
  }
}

void replay(const ReplayPlan& plan, std::size_t requested_threads,
            std::size_t segment_rows) {
  const std::vector<std::uint32_t> primes =
      primes_upto(integer_square_root(plan.expected_limit));
  if (segment_rows == 0) {
    replay_serial_chunks(plan, primes, requested_threads);
  } else {
    replay_segmented_chunks(plan, primes, requested_threads, segment_rows);
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    const ReplayPlan plan = load_plan(options.plan);
    const std::uint64_t checked_rows =
        plan.source_upper_exclusive - plan.source_lower;
    if (!sparkinterval::permits_finite_work(checked_rows)) {
      fail(sparkinterval::kCloudOnlyWorkloadError);
    }
    replay(plan, options.threads, options.segment_rows);
    if (plan.benchmark_only) {
      std::cout
          << "{\"checked_chunks\":" << plan.chunks.size()
          << ",\"checked_rows\":"
          << plan.source_upper_exclusive - plan.source_lower
          << ",\"classification\":\"bounded_cpu_r2star_arithmetic_replay_benchmark_v1\","
          << "\"source_lower\":" << plan.source_lower
          << ",\"source_upper_exclusive\":" << plan.source_upper_exclusive
          << ",\"status\":\"BENCHMARK_ONLY\"}\n";
    } else {
      std::cout
          << "{\"checked_chunks\":" << plan.chunks.size()
          << ",\"checked_rows\":" << plan.expected_limit
          << ",\"classification\":\"independent_cpu_full_row_arithmetic_replay_v1\","
          << "\"expected_limit\":" << plan.expected_limit
          << ",\"status\":\"PASS\"}\n";
    }
    return 0;
  } catch (const std::exception& exception) {
    std::cerr << "R2Star arithmetic replay error: " << exception.what()
              << '\n';
    return 2;
  }
}

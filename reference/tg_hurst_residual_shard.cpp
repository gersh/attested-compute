// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-scale affine-guard shard producer for four ternary-Goldbach atoms.
//
// This adapter is compiled against the pinned MIT-licensed segmented Mobius
// sieve by Greg Hurst.  Hurst's source retains its own copyright and license;
// SPARKINTERVAL_HURST_UPSTREAM_COMMIT identifies the reviewed checkout.

#include "SegmentedMobiusSieve.h"

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

#include <boost/multiprecision/cpp_int.hpp>
#include <omp.h>

#ifndef SPARKINTERVAL_HURST_UPSTREAM_COMMIT
#error "the Hurst residual shard must bind a pinned upstream commit"
#endif

namespace {

using boost::multiprecision::cpp_int;

constexpr std::uint64_t kSourceLimit = 10'000'000'000'000'000ULL;
constexpr std::uint64_t kHurstLower = 33;
constexpr std::uint64_t kLittle211Limit = 1'000'000'000'000ULL;
constexpr std::uint64_t kLittleStrongerLower = 3;
// EXCLUSIVE upper endpoint: the stronger bound is false at 7'727'068'587.
constexpr std::uint64_t kLittleStrongerLimit = 7'727'068'587ULL;
constexpr std::uint64_t kSquarefreeB1Threshold = 9'243;
constexpr std::uint64_t kSquarefreeB2Threshold = 438'429;
constexpr std::uint64_t kDefaultSegmentSize = 110'880'000;
constexpr std::uint64_t kMaximumSegmentSize = 2'000'000'000;
constexpr std::uint64_t kReductionBlockSize = 1'048'576;
constexpr unsigned int kLittleScaleBits = 96;
constexpr unsigned __int128 kLittleScale =
    static_cast<unsigned __int128>(1) << kLittleScaleBits;
constexpr std::uint64_t kDensityDenominator = 1'000'000'000'000'000'000ULL;
constexpr std::uint64_t kDensityLower = 607'927'101'854'026'628ULL;
constexpr std::uint64_t kDensityUpper = 607'927'101'854'026'629ULL;
constexpr std::int64_t kWideLower = -4'000'000'000'000'000'000LL;
constexpr std::int64_t kWideUpper = 4'000'000'000'000'000'000LL;
constexpr signed __int128 kWideI128 =
    static_cast<signed __int128>(1) << 120U;
constexpr unsigned __int128 kSignedI128Maximum =
    (static_cast<unsigned __int128>(1) << 127U) - 1;
constexpr std::string_view kRowDomain =
    "sparkinterval.tg.hurst-residual-mobius-rows.v1";

static_assert(
    static_cast<unsigned __int128>(kDensityUpper) * kSourceLimit * 2'000 +
            static_cast<unsigned __int128>(151) * kDensityDenominator *
                100'000'000 +
            static_cast<unsigned __int128>(kDensityDenominator) * 2'000 <
        kSignedI128Maximum,
    "source-domain squarefree filter terms must fit signed 128 bits");

struct Options {
  enum class Mode { kSummary, kVerify, kAffine };
  std::uint64_t lower = 1;
  std::uint64_t upper = 1'000'000;
  std::uint64_t segment_size = kDefaultSegmentSize;
  Mode mode = Mode::kSummary;
  std::int64_t incoming_mertens = 0;
  std::uint64_t incoming_squarefree = 0;
  signed __int128 incoming_little_lower = 0;
  signed __int128 incoming_little_upper = 0;
  bool incoming_mertens_given = false;
  bool incoming_squarefree_given = false;
  bool incoming_little_lower_given = false;
  bool incoming_little_upper_given = false;
};

struct ScalarGuard {
  signed __int128 lower;
  signed __int128 upper;
  std::uint64_t lower_witness = 0;
  std::uint64_t upper_witness = 0;
  const char* lower_side = "none";
  const char* upper_side = "none";
};

struct SquarefreeGuard {
  ScalarGuard combined{-static_cast<signed __int128>(kWideUpper),
                       static_cast<signed __int128>(kWideUpper)};
};

struct PrefixDelta {
  std::int64_t mertens = 0;
  std::uint64_t squarefree = 0;
  signed __int128 little_lower = 0;
  signed __int128 little_upper = 0;
};

struct AffineGuards {
  ScalarGuard hurst{kWideLower, kWideUpper};
  ScalarGuard squarefree{kWideLower, kWideUpper};
  ScalarGuard little211_lower{-kWideI128, kWideI128};
  ScalarGuard little211_upper{-kWideI128, kWideI128};
  ScalarGuard little_stronger_lower{-kWideI128, kWideI128};
  ScalarGuard little_stronger_upper{-kWideI128, kWideI128};
};

[[noreturn]] void fail(const std::string& message) {
  std::cerr << message << '\n';
  std::exit(2);
}

bool parse_u64(std::string_view text, std::uint64_t* output) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto result = std::from_chars(begin, end, *output);
  return result.ec == std::errc{} && result.ptr == end;
}

bool parse_i64(std::string_view text, std::int64_t* output) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto result = std::from_chars(begin, end, *output);
  return result.ec == std::errc{} && result.ptr == end;
}

bool parse_i128(std::string_view text, signed __int128* output) {
  if (text.empty()) return false;
  bool negative = false;
  std::size_t index = 0;
  if (text.front() == '-') {
    negative = true;
    index = 1;
  }
  if (index == text.size()) return false;
  const unsigned __int128 signed_limit =
      static_cast<unsigned __int128>(1) << 127U;
  const unsigned __int128 limit = negative ? signed_limit : signed_limit - 1;
  unsigned __int128 magnitude = 0;
  for (; index < text.size(); ++index) {
    const char character = text[index];
    if (character < '0' || character > '9') return false;
    const unsigned int digit = static_cast<unsigned int>(character - '0');
    if (magnitude > (limit - digit) / 10) return false;
    magnitude = magnitude * 10 + digit;
  }
  if (!negative) {
    *output = static_cast<signed __int128>(magnitude);
  } else if (magnitude == signed_limit) {
    *output = -static_cast<signed __int128>(signed_limit - 1) - 1;
  } else {
    *output = -static_cast<signed __int128>(magnitude);
  }
  return true;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--lower") {
      if (!parse_u64(value("--lower"), &options.lower)) {
        fail("--lower must be an unsigned integer");
      }
    } else if (argument == "--upper") {
      if (!parse_u64(value("--upper"), &options.upper)) {
        fail("--upper must be an unsigned integer");
      }
    } else if (argument == "--segment-size") {
      if (!parse_u64(value("--segment-size"), &options.segment_size)) {
        fail("--segment-size must be an unsigned integer");
      }
    } else if (argument == "--mode") {
      const std::string_view mode = value("--mode");
      if (mode == "summary") {
        options.mode = Options::Mode::kSummary;
      } else if (mode == "verify") {
        options.mode = Options::Mode::kVerify;
      } else if (mode == "affine") {
        options.mode = Options::Mode::kAffine;
      } else {
        fail("--mode must be summary, verify, or affine");
      }
    } else if (argument == "--incoming-mertens") {
      if (!parse_i64(value("--incoming-mertens"),
                     &options.incoming_mertens)) {
        fail("--incoming-mertens must be a signed 64-bit integer");
      }
      options.incoming_mertens_given = true;
    } else if (argument == "--incoming-squarefree") {
      if (!parse_u64(value("--incoming-squarefree"),
                     &options.incoming_squarefree)) {
        fail("--incoming-squarefree must be an unsigned 64-bit integer");
      }
      options.incoming_squarefree_given = true;
    } else if (argument == "--incoming-little-lower") {
      if (!parse_i128(value("--incoming-little-lower"),
                      &options.incoming_little_lower)) {
        fail("--incoming-little-lower must be a signed 128-bit integer");
      }
      options.incoming_little_lower_given = true;
    } else if (argument == "--incoming-little-upper") {
      if (!parse_i128(value("--incoming-little-upper"),
                      &options.incoming_little_upper)) {
        fail("--incoming-little-upper must be a signed 128-bit integer");
      }
      options.incoming_little_upper_given = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-hurst-residual-shard "
             "--lower N --upper N [--segment-size N] "
             "[--mode summary|verify|affine] "
             "[--incoming-mertens M --incoming-squarefree Q "
             "--incoming-little-lower L --incoming-little-upper U]\n"
             "The inclusive shard is independently sieved and summarized as "
             "an affine guarded prefix transition.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.lower < 1 || options.upper < options.lower ||
      options.upper > kSourceLimit) {
    fail("the inclusive shard must lie in [1, 10000000000000000]");
  }
  if (options.segment_size < SegmentedMobiusSieveCore::STENCIL_PERIOD ||
      options.segment_size > kMaximumSegmentSize) {
    fail("--segment-size is outside the supported range");
  }
  if (options.mode == Options::Mode::kVerify && options.lower != 1 &&
      !(options.incoming_mertens_given && options.incoming_squarefree_given &&
        options.incoming_little_lower_given &&
        options.incoming_little_upper_given)) {
    fail("a non-root verify shard requires all four incoming prefix states");
  }
  if (options.incoming_little_lower > options.incoming_little_upper) {
    fail("the incoming little-Mertens interval is reversed");
  }
  return options;
}

std::string i128_string(signed __int128 value) {
  if (value == 0) return "0";
  const bool negative = value < 0;
  unsigned __int128 magnitude = 0;
  if (negative) {
    magnitude = static_cast<unsigned __int128>(-(value + 1));
    ++magnitude;
  } else {
    magnitude = static_cast<unsigned __int128>(value);
  }
  std::string result;
  while (magnitude != 0) {
    result.push_back(static_cast<char>('0' + magnitude % 10));
    magnitude /= 10;
  }
  if (negative) result.push_back('-');
  std::reverse(result.begin(), result.end());
  return result;
}

std::uint64_t integer_sqrt_u64(std::uint64_t value) {
  std::uint64_t estimate = static_cast<std::uint64_t>(std::sqrt(
      static_cast<long double>(value)));
  while (estimate != std::numeric_limits<std::uint64_t>::max() &&
         estimate + 1 <= value / (estimate + 1)) {
    ++estimate;
  }
  while (estimate != 0 && estimate > value / estimate) --estimate;
  return estimate;
}

void advance_floor_root(std::uint64_t value, std::uint64_t* root) {
  while (*root != std::numeric_limits<std::uint64_t>::max()) {
    const std::uint64_t next = *root + 1;
    if (static_cast<unsigned __int128>(next) * next > value) break;
    *root = next;
  }
  while (*root != 0 &&
         static_cast<unsigned __int128>(*root) * *root > value) {
    --*root;
  }
}

unsigned __int128 integer_sqrt_u128(unsigned __int128 value) {
  if (value == 0) return 0;
  unsigned __int128 low = 1;
  unsigned __int128 high = static_cast<unsigned __int128>(1) << 64U;
  while (low + 1 < high) {
    const unsigned __int128 middle = low + (high - low) / 2;
    if (middle <= value / middle) {
      low = middle;
    } else {
      high = middle;
    }
  }
  return low;
}

cpp_int integer_sqrt(cpp_int value) {
  if (value < 0) fail("internal square root received a negative integer");
  if (value < 2) return value;
  const unsigned int bits = boost::multiprecision::msb(value) + 1;
  cpp_int current = cpp_int(1) << ((bits + 1) / 2);
  for (;;) {
    cpp_int next = (current + value / current) >> 1;
    if (next >= current) return current;
    current = std::move(next);
  }
}

cpp_int ceil_div(const cpp_int& numerator, const cpp_int& denominator) {
  if (denominator <= 0) fail("internal ceil-div denominator is not positive");
  cpp_int quotient = numerator / denominator;
  cpp_int remainder = numerator % denominator;
  if (remainder > 0) ++quotient;
  return quotient;
}

signed __int128 cpp_to_i128(const cpp_int& value) {
  const cpp_int limit = cpp_int(1) << 126U;
  if (value <= -limit || value >= limit) {
    fail("exact guard value exceeds the signed-128 safety range");
  }
  return value.convert_to<signed __int128>();
}

std::uint64_t exact_hurst_limit(std::uint64_t n) {
  const unsigned __int128 numerator =
      static_cast<unsigned __int128>(571) * 571 * n;
  return static_cast<std::uint64_t>(integer_sqrt_u128(numerator / 1'000'000));
}

unsigned __int128 conservative_squarefree_radius(
    std::uint64_t bound_numerator, std::uint64_t /*bound_denominator*/,
    std::uint64_t floor_root) {
  const unsigned __int128 coefficient =
      static_cast<unsigned __int128>(bound_numerator) * kDensityDenominator;
  return coefficient * floor_root;
}

cpp_int exact_squarefree_radius(std::uint64_t n,
                                std::uint64_t bound_numerator,
                                std::uint64_t /*bound_denominator*/) {
  const cpp_int coefficient = cpp_int(bound_numerator) * kDensityDenominator;
  return integer_sqrt(coefficient * coefficient * n);
}

std::pair<signed __int128, signed __int128> exact_squarefree_q_interval(
    std::uint64_t y, std::uint64_t bound_numerator,
    std::uint64_t bound_denominator) {
  const cpp_int radius =
      exact_squarefree_radius(y, bound_numerator, bound_denominator);
  const cpp_int common = cpp_int(kDensityDenominator) * bound_denominator;
  const cpp_int lower_linear = cpp_int(kDensityUpper) * y * bound_denominator;
  const cpp_int upper_linear = cpp_int(kDensityLower) * y * bound_denominator;
  return {
      cpp_to_i128(ceil_div(lower_linear - radius, common)),
      cpp_to_i128((upper_linear + radius) / common),
  };
}

std::pair<signed __int128, signed __int128> conservative_squarefree_q_interval(
    std::uint64_t y, std::uint64_t bound_numerator,
    std::uint64_t bound_denominator, std::uint64_t floor_root) {
  const unsigned __int128 radius = conservative_squarefree_radius(
      bound_numerator, bound_denominator, floor_root);
  // All conservative terms fit signed 128 bits at the source endpoint.  This
  // path runs for every squarefree endpoint, so do not pay for arbitrary-
  // precision division merely to decide whether the exact interval can
  // tighten the current guard.
  const signed __int128 common =
      static_cast<signed __int128>(kDensityDenominator) * bound_denominator;
  const signed __int128 lower_linear =
      static_cast<signed __int128>(kDensityUpper) * y * bound_denominator;
  const signed __int128 upper_linear =
      static_cast<signed __int128>(kDensityLower) * y * bound_denominator;
  const signed __int128 scaled_radius = static_cast<signed __int128>(radius);
  const signed __int128 lower_numerator = lower_linear - scaled_radius;
  const signed __int128 upper_numerator = upper_linear + scaled_radius;
  return {
      (lower_numerator + common - 1) / common,
      upper_numerator / common,
  };
}

unsigned __int128 exact_little_limit(std::uint64_t right_endpoint,
                                     bool stronger) {
  cpp_int radicand = cpp_int(kLittleScale) * kLittleScale;
  if (stronger) {
    radicand /= cpp_int(4) * right_endpoint;
  } else {
    radicand *= 2;
    radicand /= right_endpoint;
  }
  return integer_sqrt(radicand).convert_to<unsigned __int128>();
}

void tighten(ScalarGuard* guard, signed __int128 candidate_lower,
             signed __int128 candidate_upper, std::uint64_t witness,
             const char* side) {
  if (candidate_lower > guard->lower) {
    guard->lower = candidate_lower;
    guard->lower_witness = witness;
    guard->lower_side = side;
  }
  if (candidate_upper < guard->upper) {
    guard->upper = candidate_upper;
    guard->upper_witness = witness;
    guard->upper_side = side;
  }
  if (guard->lower > guard->upper) {
    fail("a shard has an empty incoming-state guard");
  }
}

void update_hurst_guard(ScalarGuard* guard, std::uint64_t n,
                        std::int64_t local_mertens,
                        std::uint64_t floor_root) {
  const std::int64_t conservative =
      static_cast<std::int64_t>(
          (static_cast<unsigned __int128>(571) * floor_root) / 1'000);
  const signed __int128 cheap_lower = -conservative - local_mertens;
  const signed __int128 cheap_upper = conservative - local_mertens;
  if (cheap_lower <= guard->lower && cheap_upper >= guard->upper) return;
  const std::int64_t exact = static_cast<std::int64_t>(exact_hurst_limit(n));
  tighten(guard, -exact - local_mertens, exact - local_mertens, n, "integer");
}

void update_squarefree_guard(ScalarGuard* guard, std::uint64_t y,
                             std::uint64_t local_squarefree,
                             std::uint64_t bound_numerator,
                             std::uint64_t bound_denominator,
                             const char* side,
                             std::uint64_t floor_root) {
  const auto cheap = conservative_squarefree_q_interval(
      y, bound_numerator, bound_denominator, floor_root);
  const signed __int128 cheap_lower = cheap.first - local_squarefree;
  const signed __int128 cheap_upper = cheap.second - local_squarefree;
  if (cheap_lower <= guard->lower && cheap_upper >= guard->upper) return;
  const auto exact = exact_squarefree_q_interval(
      y, bound_numerator, bound_denominator);
  tighten(guard, exact.first - local_squarefree,
          exact.second - local_squarefree, y, side);
}

void update_little_guard(ScalarGuard* lower_component,
                         ScalarGuard* upper_component,
                         std::uint64_t right_endpoint,
                         signed __int128 local_lower,
                         signed __int128 local_upper, bool stronger,
                         std::uint64_t floor_root,
                         std::uint64_t half_floor_root) {
  const std::uint64_t ceil_root =
      floor_root * floor_root == right_endpoint ? floor_root : floor_root + 1;
  const std::uint64_t half = (right_endpoint + 1) / 2;
  const std::uint64_t half_ceil =
      half_floor_root * half_floor_root == half
          ? half_floor_root
          : half_floor_root + 1;
  const unsigned __int128 conservative = stronger
      ? kLittleScale /
            (static_cast<unsigned __int128>(2) * ceil_root)
      : kLittleScale / half_ceil;
  // The conservative radius is no larger than the exact radius.  Therefore
  // its incoming interval lies inside the exact interval: if this narrower
  // interval cannot tighten a side, the exact interval cannot tighten it
  // either.  Only an actual possible endpoint change pays for a 256-bit root.
  const signed __int128 conservative_signed =
      static_cast<signed __int128>(conservative);
  const bool lower_might_tighten =
      -conservative_signed - local_lower > lower_component->lower;
  const bool upper_might_tighten =
      conservative_signed - local_upper < upper_component->upper;
  if (!lower_might_tighten && !upper_might_tighten) return;
  const signed __int128 exact = static_cast<signed __int128>(
      exact_little_limit(right_endpoint, stronger));
  if (lower_might_tighten) {
    tighten(lower_component, -exact - local_lower, kWideI128,
            right_endpoint, "right_limit");
  }
  if (upper_might_tighten) {
    tighten(upper_component, -kWideI128, exact - local_upper,
            right_endpoint, "right_limit");
  }
}

struct VerificationCounters {
  std::uint64_t hurst_exact_fallbacks = 0;
  std::uint64_t squarefree_exact_fallbacks = 0;
  std::uint64_t little211_exact_fallbacks = 0;
  std::uint64_t little_stronger_exact_fallbacks = 0;
};

struct BlockVerification {
  VerificationCounters counters{};
  std::uint64_t failure_n = 0;
  const char* failure = "";
};

void update_affine_guards(AffineGuards* guards, std::uint64_t n,
                          const PrefixDelta& local,
                          std::uint64_t floor_root,
                          std::uint64_t right_floor_root,
                          std::uint64_t half_floor_root) {
  if (n >= kHurstLower) {
    update_hurst_guard(&guards->hurst, n, local.mertens, floor_root);
  }
  auto squarefree_endpoint = [&](std::uint64_t threshold,
                                 std::uint64_t numerator) {
    if (n >= threshold) {
      update_squarefree_guard(&guards->squarefree, n, local.squarefree,
                              numerator, 2'000, "integer", floor_root);
    }
    if (n >= threshold && n < kSourceLimit) {
      update_squarefree_guard(&guards->squarefree, n + 1, local.squarefree,
                              numerator, 2'000, "right_limit",
                              right_floor_root);
    }
  };
  // Above the second threshold, the 57/2000 interval is contained in the
  // 151/2000 interval, so its exact guard proves both source inequalities.
  if (n >= kSquarefreeB2Threshold) {
    squarefree_endpoint(kSquarefreeB2Threshold, 57);
  } else {
    squarefree_endpoint(kSquarefreeB1Threshold, 151);
  }
  if (n <= kLittle211Limit) {
    const std::uint64_t right = n < kLittle211Limit ? n + 1 : n;
    update_little_guard(&guards->little211_lower, &guards->little211_upper,
                        right, local.little_lower, local.little_upper, false,
                        right_floor_root, half_floor_root);
  }
  // kLittleStrongerLimit is EXCLUSIVE.  The closed statement is false there:
  // at n = 7 727 068 587 the sum exceeds its majorant by a relative 8.03e-06,
  // and that is the only violation in 3 <= n <= 7 727 068 587.  Helfgott
  // states the range with sum_{n<x}, which is exactly this half-open form, so
  // the right endpoint is unconditionally n + 1 and never collapses onto n.
  if (n >= kLittleStrongerLower && n < kLittleStrongerLimit) {
    const std::uint64_t right = n + 1;
    update_little_guard(&guards->little_stronger_lower,
                        &guards->little_stronger_upper, right,
                        local.little_lower, local.little_upper, true,
                        right_floor_root, half_floor_root);
  }
}

void translate_guard(ScalarGuard* guard, signed __int128 prefix) {
  if (std::string_view(guard->lower_side) != "none") {
    guard->lower -= prefix;
  }
  if (std::string_view(guard->upper_side) != "none") {
    guard->upper -= prefix;
  }
}

void merge_guard(ScalarGuard* destination, const ScalarGuard& source) {
  if (std::string_view(source.lower_side) != "none" &&
      source.lower > destination->lower) {
    destination->lower = source.lower;
    destination->lower_witness = source.lower_witness;
    destination->lower_side = source.lower_side;
  }
  if (std::string_view(source.upper_side) != "none" &&
      source.upper < destination->upper) {
    destination->upper = source.upper;
    destination->upper_witness = source.upper_witness;
    destination->upper_side = source.upper_side;
  }
  if (destination->lower > destination->upper) {
    fail("a shard has an empty incoming-state guard");
  }
}

void merge_translated_guards(AffineGuards* destination,
                             AffineGuards source,
                             const PrefixDelta& prefix) {
  translate_guard(&source.hurst, prefix.mertens);
  translate_guard(&source.squarefree, prefix.squarefree);
  translate_guard(&source.little211_lower, prefix.little_lower);
  translate_guard(&source.little211_upper, prefix.little_upper);
  translate_guard(&source.little_stronger_lower, prefix.little_lower);
  translate_guard(&source.little_stronger_upper, prefix.little_upper);
  merge_guard(&destination->hurst, source.hurst);
  merge_guard(&destination->squarefree, source.squarefree);
  merge_guard(&destination->little211_lower, source.little211_lower);
  merge_guard(&destination->little211_upper, source.little211_upper);
  merge_guard(&destination->little_stronger_lower,
              source.little_stronger_lower);
  merge_guard(&destination->little_stronger_upper,
              source.little_stronger_upper);
}

unsigned __int128 absolute_i128(signed __int128 value) {
  if (value >= 0) return static_cast<unsigned __int128>(value);
  unsigned __int128 result =
      static_cast<unsigned __int128>(-(value + 1));
  return result + 1;
}

bool verify_hurst_value(std::uint64_t n, std::int64_t mertens,
                        std::uint64_t floor_root,
                        VerificationCounters* counters) {
  const std::uint64_t magnitude = mertens < 0
      ? static_cast<std::uint64_t>(-(mertens + 1)) + 1
      : static_cast<std::uint64_t>(mertens);
  if (static_cast<unsigned __int128>(1'000) * magnitude <=
      static_cast<unsigned __int128>(571) * floor_root) {
    return true;
  }
  ++counters->hurst_exact_fallbacks;
  return static_cast<unsigned __int128>(1'000'000) * magnitude * magnitude <=
         static_cast<unsigned __int128>(571) * 571 * n;
}

bool verify_squarefree_side(signed __int128 deviation,
                            std::uint64_t y,
                            std::uint64_t floor_root,
                            std::uint64_t bound_numerator,
                            std::uint64_t bound_denominator,
                            VerificationCounters* counters) {
  if (deviation <= 0) return true;
  const unsigned __int128 left =
      static_cast<unsigned __int128>(deviation) * bound_denominator;
  const unsigned __int128 coefficient =
      static_cast<unsigned __int128>(bound_numerator) * kDensityDenominator;
  if (left <= coefficient * floor_root) return true;
  ++counters->squarefree_exact_fallbacks;
  const cpp_int left_big = cpp_int(left);
  const cpp_int coefficient_big = cpp_int(coefficient);
  return left_big * left_big <= coefficient_big * coefficient_big * y;
}

bool verify_squarefree_endpoint(std::uint64_t y,
                                std::uint64_t squarefree_count,
                                std::uint64_t bound_numerator,
                                std::uint64_t bound_denominator,
                                std::uint64_t floor_root,
                                VerificationCounters* counters) {
  const signed __int128 scaled_q =
      static_cast<signed __int128>(kDensityDenominator) * squarefree_count;
  const signed __int128 upper_deviation =
      scaled_q - static_cast<signed __int128>(kDensityLower) * y;
  const signed __int128 lower_deviation =
      static_cast<signed __int128>(kDensityUpper) * y - scaled_q;
  return verify_squarefree_side(upper_deviation, y, floor_root, bound_numerator,
                                bound_denominator, counters) &&
         verify_squarefree_side(lower_deviation, y, floor_root, bound_numerator,
                                bound_denominator, counters);
}

bool verify_little_value(std::uint64_t right_endpoint,
                         signed __int128 lower,
                         signed __int128 upper, bool stronger,
                         std::uint64_t floor_root,
                         std::uint64_t half_floor_root,
                         VerificationCounters* counters) {
  const std::uint64_t ceil_root =
      floor_root * floor_root == right_endpoint ? floor_root : floor_root + 1;
  bool cheap = true;
  if (upper > 0) {
    const unsigned __int128 factor =
        static_cast<unsigned __int128>(ceil_root) * (stronger ? 2 : 1);
    if (stronger) {
      cheap = static_cast<unsigned __int128>(upper) * factor <= kLittleScale;
    } else {
      const std::uint64_t half = (right_endpoint + 1) / 2;
      const std::uint64_t half_ceil =
          half_floor_root * half_floor_root == half
              ? half_floor_root
              : half_floor_root + 1;
      cheap = static_cast<unsigned __int128>(upper) * half_ceil <= kLittleScale;
    }
  }
  if (cheap && lower < 0) {
    if (stronger) {
      cheap = absolute_i128(lower) *
                  (static_cast<unsigned __int128>(2) * ceil_root) <=
              kLittleScale;
    } else {
      const std::uint64_t half = (right_endpoint + 1) / 2;
      const std::uint64_t half_ceil =
          half_floor_root * half_floor_root == half
              ? half_floor_root
              : half_floor_root + 1;
      cheap = absolute_i128(lower) * half_ceil <= kLittleScale;
    }
  }
  if (cheap) return true;
  if (stronger) {
    ++counters->little_stronger_exact_fallbacks;
  } else {
    ++counters->little211_exact_fallbacks;
  }
  const cpp_int scale = cpp_int(kLittleScale);
  const cpp_int right = right_endpoint;
  const auto endpoint_safe = [&](signed __int128 value) {
    const cpp_int magnitude = cpp_int(absolute_i128(value));
    if (stronger) {
      return cpp_int(4) * right * magnitude * magnitude <= scale * scale;
    }
    return right * magnitude * magnitude <= cpp_int(2) * scale * scale;
  };
  return endpoint_safe(lower) && endpoint_safe(upper);
}

void add_mobius_row(PrefixDelta* delta, std::uint64_t n, std::int8_t mu) {
  delta->mertens += mu;
  if (mu != 0) ++delta->squarefree;
  if (n > kLittle211Limit || mu == 0) return;
  const unsigned __int128 quotient = kLittleScale / n;
  const bool has_remainder = kLittleScale % n != 0;
  const signed __int128 floor_reciprocal =
      static_cast<signed __int128>(quotient);
  const signed __int128 ceil_reciprocal =
      floor_reciprocal + static_cast<signed __int128>(has_remainder);
  if (mu > 0) {
    delta->little_lower += floor_reciprocal;
    delta->little_upper += ceil_reciprocal;
  } else {
    delta->little_lower -= ceil_reciprocal;
    delta->little_upper -= floor_reciprocal;
  }
}

PrefixDelta operator+(const PrefixDelta& left, const PrefixDelta& right) {
  return {
      left.mertens + right.mertens,
      left.squarefree + right.squarefree,
      left.little_lower + right.little_lower,
      left.little_upper + right.little_upper,
  };
}

void add_counters(VerificationCounters* destination,
                  const VerificationCounters& source) {
  destination->hurst_exact_fallbacks += source.hurst_exact_fallbacks;
  destination->squarefree_exact_fallbacks +=
      source.squarefree_exact_fallbacks;
  destination->little211_exact_fallbacks +=
      source.little211_exact_fallbacks;
  destination->little_stronger_exact_fallbacks +=
      source.little_stronger_exact_fallbacks;
}

void hash_u64(sparkinterval::detail::Sha256* hasher, std::uint64_t value) {
  std::array<unsigned char, 8> bytes{};
  for (unsigned int index = 0; index < 8; ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (56U - 8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

void print_vector(signed __int128 m, signed __int128 q,
                  signed __int128 lm_lower, signed __int128 lm_upper) {
  std::cout << '[' << i128_string(m) << ',' << i128_string(q) << ','
            << i128_string(lm_lower) << ',' << i128_string(lm_upper) << ']';
}

void print_guard(const char* atom, const ScalarGuard& primary,
                 int component, const ScalarGuard* secondary = nullptr) {
  std::array<signed __int128, 4> lower = {
      kWideLower, kWideLower, -kWideI128, -kWideI128};
  std::array<signed __int128, 4> upper = {
      kWideUpper, kWideUpper, kWideI128, kWideI128};
  lower[component] = primary.lower;
  upper[component] = primary.upper;
  if (secondary != nullptr) {
    lower[3] = secondary->lower;
    upper[3] = secondary->upper;
  }
  std::cout << '"' << atom << "\":{\"lower\":";
  print_vector(lower[0], lower[1], lower[2], lower[3]);
  std::cout << ",\"upper\":";
  print_vector(upper[0], upper[1], upper[2], upper[3]);
  std::cout << ",\"witnesses\":[{\"component\":" << component
            << ",\"lower_n\":" << primary.lower_witness
            << ",\"lower_side\":\"" << primary.lower_side
            << "\",\"upper_n\":" << primary.upper_witness
            << ",\"upper_side\":\"" << primary.upper_side << "\"}";
  if (secondary != nullptr) {
    std::cout << ",{\"component\":3,\"lower_n\":"
              << secondary->lower_witness << ",\"lower_side\":\""
              << secondary->lower_side << "\",\"upper_n\":"
              << secondary->upper_witness << ",\"upper_side\":\""
              << secondary->upper_side << "\"}";
  }
  std::cout << "]}";
}

void print_singleton_guard(const char* atom, const Options& options) {
  std::cout << '"' << atom << "\":{\"lower\":";
  print_vector(options.incoming_mertens, options.incoming_squarefree,
               options.incoming_little_lower,
               options.incoming_little_upper);
  std::cout << ",\"upper\":";
  print_vector(options.incoming_mertens, options.incoming_squarefree,
               options.incoming_little_lower,
               options.incoming_little_upper);
  std::cout << ",\"witnesses\":[]}";
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const auto started = std::chrono::steady_clock::now();
  const std::uint64_t sqrt_upper = integer_sqrt_u64(options.upper);
  const auto primes = SegmentedMobiusSieveCore::primesUpTo(
      static_cast<std::uint32_t>(std::max<std::uint64_t>(
          SegmentedMobiusSieveCore::MIN_PRIMES_BOUND, sqrt_upper)));
  SegmentedMobiusSieveCore sieve(options.segment_size);

  std::int64_t local_mertens = 0;
  std::uint64_t local_squarefree = 0;
  signed __int128 local_little_lower = 0;
  signed __int128 local_little_upper = 0;
  AffineGuards affine_guards;
  VerificationCounters verification_counters;

  sparkinterval::detail::Sha256 row_hasher;
  row_hasher.update(kRowDomain.data(), kRowDomain.size());
  hash_u64(&row_hasher, options.lower);
  hash_u64(&row_hasher, options.upper + 1);
  std::uint64_t segments = 0;
  for (std::uint64_t lower = options.lower; lower <= options.upper;) {
    const std::uint64_t remaining = options.upper - lower + 1;
    const std::uint64_t count = std::min(options.segment_size, remaining);
    const std::uint64_t upper = lower + count - 1;
    sieve.sieve(lower, upper, primes);
    const Int8* values = sieve.data();
    const std::uint64_t block_count =
        (count + kReductionBlockSize - 1) / kReductionBlockSize;
    std::vector<PrefixDelta> block_deltas(block_count);
    std::vector<sparkinterval::Sha256Digest> block_hashes(block_count);
    std::vector<int> invalid_blocks(block_count, 0);
    std::vector<AffineGuards> block_affine_guards(block_count);

#pragma omp parallel for schedule(static)
    for (std::int64_t block_index = 0;
         block_index < static_cast<std::int64_t>(block_count);
         ++block_index) {
      const std::uint64_t block_offset =
          static_cast<std::uint64_t>(block_index) * kReductionBlockSize;
      const std::uint64_t block_size =
          std::min(kReductionBlockSize, count - block_offset);
      const std::uint64_t block_lower = lower + block_offset;
      PrefixDelta delta;
      std::vector<unsigned char> encoded(block_size);
      std::uint64_t affine_root = 0;
      std::uint64_t affine_half_root = 0;
      if (options.mode == Options::Mode::kAffine) {
        affine_root = integer_sqrt_u64(block_lower);
        if (block_lower <= kLittle211Limit) {
          affine_half_root = integer_sqrt_u64((block_lower + 2) / 2);
        }
      }
      for (std::uint64_t index = 0; index < block_size; ++index) {
        const std::int8_t mu = values[block_offset + index];
        if (mu < -1 || mu > 1) {
          invalid_blocks[block_index] = 1;
          continue;
        }
        encoded[index] = static_cast<unsigned char>(mu + 1);
        const std::uint64_t n = block_lower + index;
        add_mobius_row(&delta, n, mu);
        if (options.mode == Options::Mode::kAffine) {
          advance_floor_root(n, &affine_root);
          std::uint64_t affine_right_root = affine_root;
          advance_floor_root(
              n < kSourceLimit ? n + 1 : n, &affine_right_root);
          if (n <= kLittle211Limit) {
            const std::uint64_t little_right =
                n < kLittle211Limit ? n + 1 : n;
            advance_floor_root(
                (little_right + 1) / 2, &affine_half_root);
          }
          update_affine_guards(&block_affine_guards[block_index],
                               n, delta, affine_root, affine_right_root,
                               affine_half_root);
        }
      }
      block_deltas[block_index] = delta;
      sparkinterval::detail::Sha256 block_hasher;
      constexpr std::string_view domain =
          "sparkinterval.tg.hurst-residual-mobius-block.v1";
      block_hasher.update(domain.data(), domain.size());
      hash_u64(&block_hasher, lower + block_offset);
      hash_u64(&block_hasher, lower + block_offset + block_size);
      block_hasher.update(encoded.data(), encoded.size());
      block_hashes[block_index] = block_hasher.finish();
    }
    if (std::any_of(invalid_blocks.begin(), invalid_blocks.end(),
                    [](int value) { return value != 0; })) {
      fail("upstream sieve emitted a non-Mobius value");
    }

    std::vector<PrefixDelta> block_prefixes(block_count);
    PrefixDelta segment_delta;
    for (std::uint64_t block_index = 0; block_index < block_count;
         ++block_index) {
      block_prefixes[block_index] = segment_delta;
      segment_delta = segment_delta + block_deltas[block_index];
      hash_u64(&row_hasher, lower + block_index * kReductionBlockSize);
      row_hasher.update(block_hashes[block_index].data(),
                        block_hashes[block_index].size());
    }

    if (options.mode == Options::Mode::kVerify) {
      std::vector<BlockVerification> results(block_count);
#pragma omp parallel for schedule(static)
      for (std::int64_t block_index = 0;
           block_index < static_cast<std::int64_t>(block_count);
           ++block_index) {
        const std::uint64_t block_offset =
            static_cast<std::uint64_t>(block_index) * kReductionBlockSize;
        const std::uint64_t block_size =
            std::min(kReductionBlockSize, count - block_offset);
        PrefixDelta state = block_prefixes[block_index];
        state.mertens += options.incoming_mertens + local_mertens;
        state.squarefree += options.incoming_squarefree + local_squarefree;
        state.little_lower +=
            options.incoming_little_lower + local_little_lower;
        state.little_upper +=
            options.incoming_little_upper + local_little_upper;
        BlockVerification result;
        const std::uint64_t block_lower = lower + block_offset;
        std::uint64_t root = integer_sqrt_u64(block_lower);
        std::uint64_t half_root = integer_sqrt_u64((block_lower + 2) / 2);
        for (std::uint64_t index = 0; index < block_size; ++index) {
          const std::uint64_t n = block_lower + index;
          const std::int8_t mu = values[block_offset + index];
          advance_floor_root(n, &root);
          add_mobius_row(&state, n, mu);
          if (n >= kHurstLower &&
              !verify_hurst_value(n, state.mertens, root,
                                  &result.counters)) {
            result.failure_n = n;
            result.failure = "mertens-hurst";
            break;
          }
          std::uint64_t right_root = root;
          if (n < kSourceLimit) advance_floor_root(n + 1, &right_root);
          auto squarefree_safe = [&](std::uint64_t threshold,
                                     std::uint64_t numerator) {
            if (n >= threshold &&
                !verify_squarefree_endpoint(
                    n, state.squarefree, numerator, 2'000, root,
                    &result.counters)) {
              return false;
            }
            return n < threshold || n == kSourceLimit ||
                   verify_squarefree_endpoint(
                       n + 1, state.squarefree, numerator, 2'000,
                       right_root, &result.counters);
          };
          if (!squarefree_safe(kSquarefreeB1Threshold, 151) ||
              !squarefree_safe(kSquarefreeB2Threshold, 57)) {
            result.failure_n = n;
            result.failure = "cdem-squarefree";
            break;
          }
          if (n <= kLittle211Limit) {
            const std::uint64_t right = n < kLittle211Limit ? n + 1 : n;
            right_root = root;
            advance_floor_root(right, &right_root);
            const std::uint64_t half = (right + 1) / 2;
            advance_floor_root(half, &half_root);
            if (!verify_little_value(
                    right, state.little_lower, state.little_upper, false,
                    right_root, half_root, &result.counters)) {
              result.failure_n = n;
              result.failure = "platt-little-mertens-2-11";
              break;
            }
          }
          // Exclusive upper endpoint; see update_guards above.
          if (n >= kLittleStrongerLower && n < kLittleStrongerLimit) {
            const std::uint64_t right = n + 1;
            right_root = root;
            advance_floor_root(right, &right_root);
            const std::uint64_t half = (right + 1) / 2;
            advance_floor_root(half, &half_root);
            if (!verify_little_value(
                    right, state.little_lower, state.little_upper, true,
                    right_root, half_root, &result.counters)) {
              result.failure_n = n;
              result.failure = "platt-little-mertens-stronger";
              break;
            }
          }
        }
        results[block_index] = result;
      }
      std::uint64_t first_failure = 0;
      const char* failed_atom = "";
      for (const BlockVerification& result : results) {
        add_counters(&verification_counters, result.counters);
        if (result.failure_n != 0 &&
            (first_failure == 0 || result.failure_n < first_failure)) {
          first_failure = result.failure_n;
          failed_atom = result.failure;
        }
      }
      if (first_failure != 0) {
        fail(std::string(failed_atom) + " failed at n=" +
             std::to_string(first_failure));
      }
    }

    if (options.mode == Options::Mode::kAffine) {
      for (std::uint64_t block_index = 0; block_index < block_count;
           ++block_index) {
        PrefixDelta prefix = block_prefixes[block_index];
        prefix.mertens += local_mertens;
        prefix.squarefree += local_squarefree;
        prefix.little_lower += local_little_lower;
        prefix.little_upper += local_little_upper;
        merge_translated_guards(&affine_guards,
                                block_affine_guards[block_index], prefix);
      }
    }
    local_mertens += segment_delta.mertens;
    local_squarefree += segment_delta.squarefree;
    local_little_lower += segment_delta.little_lower;
    local_little_upper += segment_delta.little_upper;
    ++segments;
    if (upper == options.upper) break;
    lower = upper + 1;
  }

  const std::string row_sha =
      sparkinterval::lowercase_hex(row_hasher.finish());
  const double elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();

  const char* mode = options.mode == Options::Mode::kSummary
      ? "summary"
      : (options.mode == Options::Mode::kVerify ? "verify" : "affine");
  std::cout << "{\"algorithm\":\"hurst-segmented-mobius-two-pass-v2\",";
  std::cout << "\"mode\":\"" << mode << "\",";
  std::cout << "\"classification\":\"source-scale-shard-not-lean-proof\",";
  std::cout << "\"upstream_commit\":\""
            << SPARKINTERVAL_HURST_UPSTREAM_COMMIT << "\",";
  std::cout << "\"lower\":" << options.lower << ",\"upper_exclusive\":"
            << options.upper + 1 << ",\"work_count\":"
            << options.upper - options.lower + 1 << ',';
  std::cout << "\"segment_size\":" << options.segment_size
            << ",\"segments\":" << segments << ',';
  // The commitment is deliberately over fixed reduction blocks, rather than
  // one giant byte stream.  This makes independently produced shard leaves
  // composable without pretending that SHA-256 exposes an associative state.
  std::cout << "\"row_encoding\":\"mu-plus-one-block-sha256-v1\",";
  std::cout << "\"squarefree_threshold_endpoint_policy\":"
               "\"inclusive-value-and-right-limit-v2\",";
  std::cout << "\"reduction_block_rows\":" << kReductionBlockSize << ',';
  std::cout << "\"row_sha256\":\"" << row_sha << "\",";
  std::cout << "\"state_components\":[\"M\",\"Q\",\"lm_lower_q96\","
               "\"lm_upper_q96\"],\"delta\":";
  print_vector(local_mertens, local_squarefree, local_little_lower,
               local_little_upper);
  std::cout << ",\"guards\":{";
  if (options.mode == Options::Mode::kAffine) {
    print_guard("mertens-hurst", affine_guards.hurst, 0);
    std::cout << ',';
    print_guard("cdem-squarefree", affine_guards.squarefree, 1);
    std::cout << ',';
    print_guard("platt-little-mertens-2-11", affine_guards.little211_lower, 2,
                &affine_guards.little211_upper);
    std::cout << ',';
    print_guard("platt-little-mertens-stronger",
                affine_guards.little_stronger_lower, 2,
                &affine_guards.little_stronger_upper);
  } else if (options.mode == Options::Mode::kVerify) {
    print_singleton_guard("mertens-hurst", options);
    std::cout << ',';
    print_singleton_guard("cdem-squarefree", options);
    std::cout << ',';
    print_singleton_guard("platt-little-mertens-2-11", options);
    std::cout << ',';
    print_singleton_guard("platt-little-mertens-stronger", options);
  }
  std::cout << "},\"exact_fallbacks\":{";
  std::cout << "\"mertens_hurst\":"
            << verification_counters.hurst_exact_fallbacks << ',';
  std::cout << "\"squarefree\":"
            << verification_counters.squarefree_exact_fallbacks << ',';
  std::cout << "\"little_mertens_2_11\":"
            << verification_counters.little211_exact_fallbacks << ',';
  std::cout << "\"little_mertens_stronger\":"
            << verification_counters.little_stronger_exact_fallbacks;
  std::cout << "},\"accepted\":true,\"elapsed_seconds\":" << elapsed
            << ",\"execution_attested\":false,\"lean_atom_discharged\":false}\n";
  return 0;
}

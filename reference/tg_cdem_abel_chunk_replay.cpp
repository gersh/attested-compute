// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Independent, bounded-memory replayer for one CDEM Abel transcript chunk.
//
// Usage:
//   tg_cdem_abel_chunk_replay K low high incoming-F
//
// The program recomputes mu(1),...,mu(K), then the truncated divisor sum
//   delta(n) = sum_{d | n, d <= K} mu(d)
// only on [low, high].  It applies the same directed integer Abel weights as
// the production transcript and emits the outgoing F state and three local
// aggregates.  Its Eratosthenes-style Mobius sieve, integer square-root
// search, serial scan, and chunk-sized allocation are deliberately separate
// from the production program's linear sieve, floating starting estimate,
// OpenMP scan, and N-sized allocation.
//
// This is an external replay program.  Its successful execution is not a
// Lean-kernel proof and does not supply the missing realization theorem that
// identifies this recurrence with the Lean analytic definitions.

#include <algorithm>
#include <charconv>
#include <cstdint>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

namespace {

using i128 = __int128;
using u128 = unsigned __int128;

constexpr std::uint64_t WEIGHT_SCALE = 1000000000000000000ULL;  // 10^18

bool parseUint64(std::string_view text, std::uint64_t& result) {
  if (text.empty() || text.front() == '+' ||
      (text.size() > 1 && text.front() == '0')) {
    return false;
  }
  const char* const first = text.data();
  const char* const last = first + text.size();
  const auto parsed = std::from_chars(first, last, result, 10);
  return parsed.ec == std::errc{} && parsed.ptr == last;
}

bool parseInt64(std::string_view text, std::int64_t& result) {
  if (text.empty() || text.front() == '+') return false;
  const std::string_view magnitude =
      text.front() == '-' ? text.substr(1) : text;
  if (magnitude.empty() || (magnitude.size() > 1 && magnitude.front() == '0') ||
      (text.front() == '-' && magnitude == "0")) {
    return false;
  }
  const char* const first = text.data();
  const char* const last = first + text.size();
  const auto parsed = std::from_chars(first, last, result, 10);
  return parsed.ec == std::errc{} && parsed.ptr == last;
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
  // Avoid negating the least signed value in signed arithmetic.
  const u128 magnitude = static_cast<u128>(-(value + 1)) + 1;
  return "-" + toString(magnitude);
}

u128 unsignedAbs(i128 value) {
  return value >= 0 ? static_cast<u128>(value)
                    : static_cast<u128>(-(value + 1)) + 1;
}

bool checkedAdd(i128 left, i128 right, i128& result) {
  return !__builtin_add_overflow(left, right, &result);
}

bool checkedAdd(u128 left, u128 right, u128& result) {
  return !__builtin_add_overflow(left, right, &result);
}

bool checkedMultiply(i128 left, i128 right, i128& result) {
  return !__builtin_mul_overflow(left, right, &result);
}

bool checkedMultiply(u128 left, u128 right, u128& result) {
  return !__builtin_mul_overflow(left, right, &result);
}

// Exact least q such that q^2 n >= WEIGHT_SCALE^2.  Unlike the production
// source, this uses no floating-point starting estimate.
std::uint64_t ceilScaledReciprocalSqrt(std::uint64_t n) {
  const u128 target = static_cast<u128>(WEIGHT_SCALE) * WEIGHT_SCALE;
  const u128 requiredSquare = target / n + (target % n != 0);
  std::uint64_t low = 0;
  std::uint64_t high = WEIGHT_SCALE;
  while (low < high) {
    const std::uint64_t middle = low + (high - low) / 2;
    const u128 square = static_cast<u128>(middle) * middle;
    if (square >= requiredSquare) {
      high = middle;
    } else {
      low = middle + 1;
    }
  }
  return low;
}

// Compute Mobius values with the elementary prime-factor sieve.  This is
// intentionally not the production source's Euler/linear Mobius sieve.
std::vector<std::int8_t> makeMobius(std::uint32_t K) {
  std::vector<std::int8_t> mu(static_cast<std::size_t>(K) + 1, 1);
  std::vector<bool> composite(static_cast<std::size_t>(K) + 1, false);
  mu[0] = 0;
  for (std::uint32_t prime = 2; prime <= K; ++prime) {
    if (composite[prime]) continue;
    for (std::uint64_t multiple = prime; multiple <= K; multiple += prime) {
      mu[static_cast<std::size_t>(multiple)] =
          -mu[static_cast<std::size_t>(multiple)];
    }
    if (prime <= K / prime) {
      const std::uint64_t square = static_cast<std::uint64_t>(prime) * prime;
      for (std::uint64_t multiple = square; multiple <= K;
           multiple += prime) {
        composite[static_cast<std::size_t>(multiple)] = true;
      }
      for (std::uint64_t multiple = square; multiple <= K;
           multiple += square) {
        mu[static_cast<std::size_t>(multiple)] = 0;
      }
    }
  }
  return mu;
}

int fail(const char* message) {
  std::cerr << message << '\n';
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 5) {
    return fail("usage: tg_cdem_abel_chunk_replay K low high incoming-F");
  }

  std::uint64_t parsedK = 0;
  std::uint64_t low = 0;
  std::uint64_t high = 0;
  std::int64_t incoming = 0;
  if (!parseUint64(argv[1], parsedK) || !parseUint64(argv[2], low) ||
      !parseUint64(argv[3], high) || !parseInt64(argv[4], incoming)) {
    return fail("arguments must be canonical in-range decimal integers");
  }
  if (parsedK == 0 ||
      parsedK > static_cast<std::uint64_t>(
                    std::numeric_limits<std::int32_t>::max()) ||
      low == 0 || high < low) {
    return fail("require 1 <= K <= INT32_MAX and 1 <= low <= high");
  }
  const std::uint64_t span = high - low + 1;
  if (span > static_cast<std::uint64_t>(
                 std::numeric_limits<std::size_t>::max() /
                 sizeof(std::int32_t))) {
    return fail("chunk is too large for addressable exact storage");
  }
  const std::uint32_t K = static_cast<std::uint32_t>(parsedK);

  const std::vector<std::int8_t> mu = makeMobius(K);
  std::vector<std::int32_t> delta(static_cast<std::size_t>(span), 0);
  for (std::uint32_t divisor = 1; divisor <= K; ++divisor) {
    const int coefficient = mu[divisor];
    if (coefficient == 0) continue;
    const std::uint64_t remainder = low % divisor;
    std::uint64_t multiple = low;
    if (remainder != 0) {
      const std::uint64_t advance = divisor - remainder;
      if (advance > high - low) continue;
      multiple += advance;
    }
    for (;;) {
      std::int32_t& entry = delta[static_cast<std::size_t>(multiple - low)];
      if ((coefficient > 0 && entry == std::numeric_limits<std::int32_t>::max()) ||
          (coefficient < 0 && entry == std::numeric_limits<std::int32_t>::min())) {
        return fail("delta accumulator overflow");
      }
      entry += coefficient;
      if (high - multiple < divisor) break;
      multiple += divisor;
    }
  }

  i128 floorSum = incoming;
  i128 previousError = static_cast<i128>(1) - floorSum;
  previousError = static_cast<i128>(unsignedAbs(previousError));
  if (low == 1) previousError = 0;  // CDEM's explicit Gseq(0)=0 override.
  i128 uUpper = 0;
  u128 vUpper = 0;
  u128 variation = 0;

  for (std::uint64_t offset = 0; offset < span; ++offset) {
    const std::uint64_t n = low + offset;
    i128 nextFloorSum = 0;
    if (!checkedAdd(floorSum, static_cast<i128>(delta[offset]), nextFloorSum)) {
      return fail("F state overflow");
    }
    floorSum = nextFloorSum;
    const i128 signedError = static_cast<i128>(1) - floorSum;
    const u128 errorMagnitude = unsignedAbs(signedError);
    if (errorMagnitude > static_cast<u128>(
                             std::numeric_limits<i128>::max())) {
      return fail("error magnitude exceeds signed recurrence range");
    }
    const i128 error = static_cast<i128>(errorMagnitude);
    const i128 increment = error - previousError;

    if (increment != 0) {
      const std::uint64_t directedWeight =
          increment > 0
              ? WEIGHT_SCALE / n + (WEIGHT_SCALE % n != 0)
              : WEIGHT_SCALE / n;
      i128 weighted = 0;
      i128 nextU = 0;
      if (!checkedMultiply(increment, static_cast<i128>(directedWeight),
                           weighted) ||
          !checkedAdd(uUpper, weighted, nextU)) {
        return fail("signed Abel accumulator overflow");
      }
      uUpper = nextU;

      const u128 absoluteIncrement = unsignedAbs(increment);
      u128 nextVariation = 0;
      if (!checkedAdd(variation, absoluteIncrement, nextVariation)) {
        return fail("variation accumulator overflow");
      }
      variation = nextVariation;
      const std::uint64_t sqrtWeight = ceilScaledReciprocalSqrt(n);
      u128 weightedAbsolute = 0;
      u128 nextV = 0;
      if (!checkedMultiply(absoluteIncrement, static_cast<u128>(sqrtWeight),
                           weightedAbsolute) ||
          !checkedAdd(vUpper, weightedAbsolute, nextV)) {
        return fail("absolute Abel accumulator overflow");
      }
      vUpper = nextV;
    }
    previousError = error;
  }

  const i128 deltaSum = floorSum - static_cast<i128>(incoming);
  std::cout << "SCHEMA=CDEM_ABEL_CHUNK_REPLAY_V1\n";
  std::cout << "K=" << K << '\n';
  std::cout << "LOW=" << low << '\n';
  std::cout << "HIGH=" << high << '\n';
  std::cout << "BEFORE=" << incoming << '\n';
  std::cout << "DELTA_SUM=" << toString(deltaSum) << '\n';
  std::cout << "AFTER=" << toString(floorSum) << '\n';
  std::cout << "U_INC_UPPER_NUM=" << toString(uUpper) << '\n';
  std::cout << "V_INC_UPPER_NUM=" << toString(vUpper) << '\n';
  std::cout << "TOTAL_VARIATION=" << toString(variation) << '\n';
  std::cout << "WEIGHT_SCALE=" << WEIGHT_SCALE << '\n';
  return 0;
}

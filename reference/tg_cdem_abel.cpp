// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Reproducible bounded-aggregate engine for the Mobius-prefix CDEM Abel table.
//
// Build:
//   mkdir -p build/tg
//   g++ -O3 -march=native -fopenmp -std=c++20 -Igpu/include reference/tg_cdem_abel.cpp -o build/tg/tg_cdem_abel
//
// Full production parameters (also the defaults):
//   OMP_NUM_THREADS=8 build/tg/tg_cdem_abel 199330 5000000000 5000000
//
// The integer stream is exact.  The reported U_INC_UPPER and V_INC_UPPER
// are directed fixed-point upper bounds, not floating-point estimates.  This
// is a host reference producer: its stdout remains external evidence, and
// running this program does not turn that evidence into a Lean-kernel-checked
// proof or establish execution of any GPU kernel.

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#include <omp.h>

#include "sparkinterval/sha256.hpp"

namespace {

using u128 = unsigned __int128;
using i128 = __int128;

constexpr std::uint32_t DEFAULT_K = 199330;
constexpr std::uint64_t DEFAULT_N = 5000000000ULL;
constexpr std::uint64_t DEFAULT_BLOCK_SIZE = 5000000ULL;
constexpr std::uint64_t WEIGHT_SCALE = 1000000000000000000ULL;  // 10^18

bool parseUint64(std::string_view text, std::uint64_t& result) {
  if (text.empty()) return false;
  const char* first = text.data();
  const char* last = first + text.size();
  const auto parsed = std::from_chars(first, last, result, 10);
  return parsed.ec == std::errc{} && parsed.ptr == last;
}

u128 pow10(unsigned exponent) {
  u128 result = 1;
  for (unsigned i = 0; i < exponent; ++i) result *= 10;
  return result;
}

std::string toString(u128 x) {
  if (x == 0) return "0";
  std::string result;
  while (x != 0) {
    result.push_back(static_cast<char>('0' + x % 10));
    x /= 10;
  }
  std::reverse(result.begin(), result.end());
  return result;
}

std::string toString(i128 x) {
  if (x >= 0) return toString(static_cast<u128>(x));
  return "-" + toString(static_cast<u128>(-x));
}

u128 ceilDiv(u128 numerator, std::uint64_t denominator) {
  return numerator / denominator + (numerator % denominator != 0);
}

// The least q with q/s >= 1/sqrt(n), checked using exact u128 products.
// long double supplies only a starting point; the two exact loops determine
// the returned directed bound.
std::uint64_t ceilScaledReciprocalSqrt(std::uint64_t n) {
  const u128 scaleSquared = static_cast<u128>(WEIGHT_SCALE) * WEIGHT_SCALE;
  std::uint64_t q = static_cast<std::uint64_t>(
      std::ceil(static_cast<long double>(WEIGHT_SCALE) /
                std::sqrt(static_cast<long double>(n))));
  auto enough = [n, scaleSquared](std::uint64_t candidate) {
    return static_cast<u128>(candidate) * candidate * n >= scaleSquared;
  };
  while (!enough(q)) ++q;
  while (q != 0 && enough(q - 1)) --q;
  return q;
}

struct MobiusData {
  std::vector<std::int8_t> mu;
  std::vector<std::uint32_t> nonzero;
  std::int64_t mertens = 0;
  std::uint64_t squarefreeMass = 0;
  i128 reciprocalLowerNumerator = 0;
  i128 reciprocalUpperNumerator = 0;
};

MobiusData makeMobius(std::uint32_t K, u128 coefficientScale) {
  MobiusData data;
  data.mu.assign(static_cast<std::size_t>(K) + 1, 0);
  std::vector<std::uint32_t> primes;
  std::vector<bool> composite(static_cast<std::size_t>(K) + 1, false);
  data.mu[1] = 1;
  for (std::uint32_t i = 2; i <= K; ++i) {
    if (!composite[i]) {
      primes.push_back(i);
      data.mu[i] = -1;
    }
    for (std::uint32_t p : primes) {
      const std::uint64_t product = static_cast<std::uint64_t>(i) * p;
      if (product > K) break;
      composite[product] = true;
      if (i % p == 0) {
        data.mu[product] = 0;
        break;
      }
      data.mu[product] = -data.mu[i];
    }
  }

  for (std::uint32_t d = 1; d <= K; ++d) {
    const int mu = data.mu[d];
    data.mertens += mu;
    data.squarefreeMass += std::abs(mu);
    if (mu == 0) continue;
    data.nonzero.push_back(d);
    const i128 floorTerm = static_cast<i128>(coefficientScale / d);
    const i128 ceilTerm = static_cast<i128>(ceilDiv(coefficientScale, d));
    if (mu > 0) {
      data.reciprocalLowerNumerator += floorTerm;
      data.reciprocalUpperNumerator += ceilTerm;
    } else {
      data.reciprocalLowerNumerator -= ceilTerm;
      data.reciprocalUpperNumerator -= floorTerm;
    }
  }
  return data;
}

std::uint64_t blockLow(std::uint64_t block, std::uint64_t blockSize) {
  return block * blockSize + 1;
}

std::uint64_t blockHigh(std::uint64_t low, std::uint64_t N,
                        std::uint64_t blockSize) {
  const std::uint64_t remaining = N - low + 1;
  return remaining <= blockSize ? N : low + blockSize - 1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 4) {
    std::cerr << "usage: tg_cdem_abel [K [N [block-size]]]\n";
    return 2;
  }

  std::uint64_t parsedK = DEFAULT_K;
  std::uint64_t N = DEFAULT_N;
  std::uint64_t blockSize = DEFAULT_BLOCK_SIZE;
  if ((argc > 1 && !parseUint64(argv[1], parsedK)) ||
      (argc > 2 && !parseUint64(argv[2], N)) ||
      (argc > 3 && !parseUint64(argv[3], blockSize))) {
    std::cerr << "K, N, and block-size must be unsigned decimal integers\n";
    return 2;
  }
  if (parsedK >
      static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
    std::cerr << "K exceeds the exact int32 convolution bound\n";
    return 2;
  }
  const std::uint32_t K = static_cast<std::uint32_t>(parsedK);
  if (K == 0 || N < K || N == std::numeric_limits<std::uint64_t>::max() ||
      blockSize == 0 ||
      N > static_cast<std::uint64_t>(
              std::numeric_limits<std::size_t>::max() - 1)) {
    std::cerr << "require 1 <= K <= N < 2^64-1 and block-size >= 1\n";
    return 2;
  }

  const u128 coefficientScale = pow10(30);
  const MobiusData mobius = makeMobius(K, coefficientScale);
  const std::uint64_t blockCount =
      N / blockSize + (N % blockSize != 0);

  const auto start = std::chrono::steady_clock::now();
  // int32 is intentional: |sum_{d|n,d<=K} mu(d)| <= K, and the parser
  // rejects K above INT32_MAX.  The production value is K=199330.
  std::vector<std::int32_t> delta(static_cast<std::size_t>(N) + 1, 0);

#pragma omp parallel for schedule(dynamic, 1)
  for (std::uint64_t block = 0; block < blockCount; ++block) {
    const std::uint64_t low = blockLow(block, blockSize);
    const std::uint64_t high = blockHigh(low, N, blockSize);
    for (std::uint32_t d : mobius.nonzero) {
      std::uint64_t multiple = low;
      const std::uint64_t remainder = low % d;
      if (remainder != 0) {
        const std::uint64_t advance = d - remainder;
        if (advance > high - low) continue;
        multiple += advance;
      }
      const int value = mobius.mu[d];
      for (;;) {
        delta[multiple] += value;
        if (high - multiple < d) break;
        multiple += d;
      }
    }
  }
  const auto filled = std::chrono::steady_clock::now();

  std::vector<std::int64_t> blockDelta(blockCount, 0);
  std::vector<std::int64_t> blockBefore(blockCount, 0);
#pragma omp parallel for schedule(static)
  for (std::uint64_t block = 0; block < blockCount; ++block) {
    const std::uint64_t low = blockLow(block, blockSize);
    const std::uint64_t high = blockHigh(low, N, blockSize);
    std::int64_t sum = 0;
    for (std::uint64_t n = low; n <= high; ++n) sum += delta[n];
    blockDelta[block] = sum;
  }
  std::int64_t finalFloorSum = 0;
  for (std::uint64_t block = 0; block < blockCount; ++block) {
    blockBefore[block] = finalFloorSum;
    finalFloorSum += blockDelta[block];
  }

  std::vector<i128> blockUUpper(blockCount, 0);
  std::vector<u128> blockVUpper(blockCount, 0);
  std::vector<std::uint64_t> blockVariation(blockCount, 0);
#pragma omp parallel for schedule(static)
  for (std::uint64_t block = 0; block < blockCount; ++block) {
    const std::uint64_t low = blockLow(block, blockSize);
    const std::uint64_t high = blockHigh(low, N, blockSize);
    std::int64_t floorSum = blockBefore[block];
    std::int64_t previousError = std::llabs(1 - floorSum);
    if (low == 1) previousError = 0;  // CDEM's Gseq(0)=0 override.
    i128 uUpper = 0;
    u128 vUpper = 0;
    std::uint64_t variation = 0;
    for (std::uint64_t n = low; n <= high; ++n) {
      floorSum += delta[n];
      const std::int64_t error = std::llabs(1 - floorSum);
      const std::int64_t increment = error - previousError;
      if (increment > 0) {
        uUpper += static_cast<i128>(increment) *
                  ((WEIGHT_SCALE + n - 1) / n);
      } else if (increment < 0) {
        // floor(scale/n) times a negative increment is an upper bound.
        uUpper += static_cast<i128>(increment) * (WEIGHT_SCALE / n);
      }
      const std::uint64_t absoluteIncrement = std::llabs(increment);
      if (absoluteIncrement != 0) {
        variation += absoluteIncrement;
        vUpper += static_cast<u128>(absoluteIncrement) *
                  ceilScaledReciprocalSqrt(n);
      }
      previousError = error;
    }
    blockUUpper[block] = uUpper;
    blockVUpper[block] = vUpper;
    blockVariation[block] = variation;
  }

  i128 uIncrementUpper = 0;
  u128 vIncrementUpper = 0;
  u128 totalVariation = 0;
  for (std::uint64_t block = 0; block < blockCount; ++block) {
    uIncrementUpper += blockUUpper[block];
    vIncrementUpper += blockVUpper[block];
    totalVariation += blockVariation[block];
  }
  const std::int64_t finalError = std::llabs(1 - finalFloorSum);
  const std::uint64_t endpointReciprocalSqrtUpper =
      ceilScaledReciprocalSqrt(N + 1);
  const auto finished = std::chrono::steady_clock::now();

  // The compact manifest exposes exact composable block states.  It is small
  // (1,000 rows at production parameters) and lets an independent checker
  // validate coverage, prefix-state composition, and all final reductions.
  std::string chunkManifest;
  for (std::uint64_t block = 0; block < blockCount; ++block) {
    const std::uint64_t low = blockLow(block, blockSize);
    const std::uint64_t high = blockHigh(low, N, blockSize);
    const std::int64_t before = blockBefore[block];
    const std::int64_t after = before + blockDelta[block];
    chunkManifest += "CHUNK_" + std::to_string(block) + "=" +
                     std::to_string(low) + "," + std::to_string(high) + "," +
                     std::to_string(before) + "," + std::to_string(after) +
                     "," + toString(blockUUpper[block]) + "," +
                     toString(blockVUpper[block]) + "," +
                     std::to_string(blockVariation[block]) + "\n";
  }
  const std::string chunkManifestSha256 = sparkinterval::sha256_hex(
      chunkManifest.data(), chunkManifest.size());

  std::cout << "K=" << K << '\n';
  std::cout << "N=" << N << '\n';
  std::cout << "A=" << N + 1 << '\n';
  std::cout << "MOBIUS_M=" << mobius.mertens << '\n';
  std::cout << "MOBIUS_Q=" << mobius.squarefreeMass << '\n';
  std::cout << "COEFF_SCALE=" << toString(coefficientScale) << '\n';
  std::cout << "S_LOWER_NUM=" << toString(mobius.reciprocalLowerNumerator)
            << '\n';
  std::cout << "S_UPPER_NUM=" << toString(mobius.reciprocalUpperNumerator)
            << '\n';
  std::cout << "FINAL_F=" << finalFloorSum << '\n';
  std::cout << "FINAL_G=" << finalError << '\n';
  std::cout << "TOTAL_VARIATION=" << toString(totalVariation) << '\n';
  std::cout << "WEIGHT_SCALE=" << WEIGHT_SCALE << '\n';
  std::cout << "U_INC_UPPER_NUM=" << toString(uIncrementUpper) << '\n';
  std::cout << "V_INC_UPPER_NUM=" << toString(vIncrementUpper) << '\n';
  std::cout << "ENDPOINT_RSQRT_UPPER_NUM=" << endpointReciprocalSqrtUpper
            << '\n';
  std::cout << "CHUNK_COUNT=" << blockCount << '\n';
  std::cout << "CHUNK_MANIFEST_SHA256=" << chunkManifestSha256 << '\n';
  std::cout << chunkManifest;
  std::cout << "THREADS=" << omp_get_max_threads() << '\n';
  std::cout << "BLOCK_SIZE=" << blockSize << '\n';
  std::cout << "FILL_SECONDS="
            << std::chrono::duration<double>(filled - start).count() << '\n';
  std::cout << "SCAN_SECONDS="
            << std::chrono::duration<double>(finished - filled).count() << '\n';
}

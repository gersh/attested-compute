// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only whole-tail comparison for the historical GoldbachGPU
// sieve.  Production source, transforms, identities, and build defaults do
// not include this file.

#ifndef SPARKINTERVAL_ENABLE_GOLDBACH_WHEEL_GAP_QUALIFICATION
#error "the Goldbach wheel-gap tail is qualification-only and macro guarded"
#endif

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "sparkinterval/sha256.hpp"

namespace {

constexpr unsigned kThreads = 256;
constexpr std::uint64_t kWordOwnerCutoff = 2'039;
constexpr std::uint64_t kWarpParallelCutoff = 32'749;
constexpr std::uint32_t kWheelModulus = 30'030;
constexpr std::uint32_t kWheelOddEntries = kWheelModulus / 2U;
constexpr std::uint8_t kWheelSurvivesFlag = 0x80U;
constexpr std::uint8_t kWheelGapMask = 0x1fU;
constexpr std::uint8_t kExpectedMaximumGap = 22U;
constexpr std::uint32_t kExpectedWheelSurvivors = 5'760U;
constexpr std::uint64_t kBoundedPrimeLimit = 2'000'003;
constexpr std::uint64_t kBoundedOddCount = 1ULL << 20U;
constexpr unsigned kBoundedRounds = 7;
constexpr unsigned kSourceRounds = 9;
constexpr std::uint64_t kHistoricalStart =
    31'249'998'800'000'002ULL;
constexpr std::uint64_t kHistoricalLimit =
    31'250'000'000'000'000ULL;
constexpr std::uint64_t kHistoricalSegmentEvenCount = 200'000'000ULL;
constexpr std::uint64_t kHistoricalPSmall = 1'000'000ULL;

struct Counts {
  unsigned long long raw_visit_count;
  unsigned long long small_wheel_survivor_count;
  unsigned long long final_event_count;
};

struct HostCounts {
  std::uint64_t raw_visit_count = 0;
  std::uint64_t small_wheel_survivor_count = 0;
  std::uint64_t final_event_count = 0;
};

struct Geometry {
  std::string name;
  std::uint64_t q_low;
  std::uint64_t q_high;
};

struct PreparedWindow {
  Geometry geometry;
  std::vector<std::uint64_t> initial;
  std::vector<std::uint64_t> expected;
  HostCounts counts;
};

struct CaseResult {
  std::string name;
  std::uint64_t q_low;
  std::uint64_t q_high;
  std::uint64_t odd_count;
  HostCounts counts;
  std::uint64_t set_bits;
  std::string output_sha256;
};

struct TimingSet {
  std::vector<double> ordinary_raw_ms;
  std::vector<double> current_wheel47_ms;
  std::vector<double> wheel_gap_ms;
  std::vector<double> wheel_gap_remainders_ms;
  double ordinary_raw_median_ms = 0.0;
  double current_wheel47_median_ms = 0.0;
  double wheel_gap_median_ms = 0.0;
  double wheel_gap_remainders_median_ms = 0.0;
};

struct BenchmarkResult {
  std::string geometry;
  std::uint64_t window_count;
  std::uint64_t total_odd_count;
  std::uint64_t prime_limit;
  std::uint64_t tail_prime_count;
  HostCounts counts;
  unsigned rounds;
  TimingSet timings;
  std::string output_sha256;
};

void cuda_check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

std::uint64_t integer_sqrt(std::uint64_t value) {
  std::uint64_t low = 0;
  std::uint64_t high = std::min<std::uint64_t>(
      value, std::numeric_limits<std::uint32_t>::max());
  std::uint64_t answer = 0;
  while (low <= high) {
    const std::uint64_t middle = low + (high - low) / 2U;
    if (middle == 0U || middle <= value / middle) {
      answer = middle;
      low = middle + 1U;
    } else {
      high = middle - 1U;
    }
  }
  return answer;
}

std::vector<std::uint64_t> odd_primes_through(std::uint64_t limit,
                                              std::uint64_t lower_exclusive) {
  if (limit < 3U) return {};
  std::vector<unsigned char> composite(
      static_cast<std::size_t>(limit + 1U), 0U);
  for (std::uint64_t prime = 2U; prime <= limit / prime; ++prime) {
    if (composite[static_cast<std::size_t>(prime)] != 0U) continue;
    for (std::uint64_t value = prime * prime; value <= limit;
         value += prime) {
      composite[static_cast<std::size_t>(value)] = 1U;
    }
  }
  std::vector<std::uint64_t> result;
  std::uint64_t first = std::max<std::uint64_t>(3U, lower_exclusive + 1U);
  if ((first & 1U) == 0U) ++first;
  for (std::uint64_t value = first; value <= limit; value += 2U) {
    if (composite[static_cast<std::size_t>(value)] == 0U) {
      result.push_back(value);
    }
  }
  return result;
}

bool survives_small_wheel(std::uint64_t cofactor) {
  const std::uint32_t residue =
      static_cast<std::uint32_t>(cofactor % 15'015ULL);
  return residue % 3U != 0U && residue % 5U != 0U &&
         residue % 7U != 0U && residue % 11U != 0U &&
         residue % 13U != 0U;
}

__host__ __device__ bool survives_large_wheel(std::uint64_t cofactor) {
  return cofactor % 17U != 0U && cofactor % 19U != 0U &&
         cofactor % 23U != 0U && cofactor % 29U != 0U &&
         cofactor % 31U != 0U && cofactor % 37U != 0U &&
         cofactor % 41U != 0U && cofactor % 43U != 0U &&
         cofactor % 47U != 0U;
}

std::array<unsigned char, kWheelOddEntries> make_wheel_gap_table() {
  std::array<unsigned char, kWheelOddEntries> table{};
  for (std::uint32_t index = 0; index < kWheelOddEntries; ++index) {
    const std::uint32_t residue = 2U * index + 1U;
    const bool survives = survives_small_wheel(residue);
    std::uint32_t gap = 2U;
    while (!survives_small_wheel(residue + gap)) gap += 2U;
    if (gap > kWheelGapMask) {
      throw std::runtime_error("small-wheel gap does not fit encoding");
    }
    table[index] = static_cast<unsigned char>(
        (survives ? kWheelSurvivesFlag : 0U) | gap);
  }
  return table;
}

std::string wheel_table_sha256(
    const std::array<unsigned char, kWheelOddEntries>& table) {
  return sparkinterval::sha256_hex(table.data(), table.size());
}

void validate_wheel_gap_table(
    const std::array<unsigned char, kWheelOddEntries>& table) {
  std::uint32_t survivor_count = 0;
  std::uint8_t maximum_gap = 0;
  for (std::uint32_t index = 0; index < table.size(); ++index) {
    const std::uint32_t residue = 2U * index + 1U;
    const unsigned char entry = table[index];
    const bool encoded_survives =
        (entry & kWheelSurvivesFlag) != 0U;
    const std::uint8_t gap = entry & kWheelGapMask;
    if (encoded_survives != survives_small_wheel(residue) ||
        gap == 0U || (gap & 1U) != 0U ||
        !survives_small_wheel(residue + gap)) {
      throw std::runtime_error("small-wheel table entry is malformed");
    }
    for (std::uint8_t prior = 2U; prior < gap; prior += 2U) {
      if (survives_small_wheel(residue + prior)) {
        throw std::runtime_error("small-wheel gap is not least positive");
      }
    }
    survivor_count += encoded_survives ? 1U : 0U;
    maximum_gap = std::max(maximum_gap, gap);
  }
  if (survivor_count != kExpectedWheelSurvivors ||
      maximum_gap != kExpectedMaximumGap) {
    throw std::runtime_error("small-wheel table global invariants differ");
  }
}

bool first_odd_multiple(std::uint64_t q_low, std::uint64_t q_high,
                        std::uint64_t prime, std::uint64_t* first,
                        std::uint64_t* cofactor) {
  if (prime < 3U || prime > q_high / prime) return false;
  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return false;
  std::uint64_t value = quotient * prime;
  if ((value & 1U) == 0U) {
    if (value > q_high - prime) return false;
    value += prime;
    ++quotient;
  }
  const std::uint64_t square = prime * prime;
  if (value < square) {
    value = square;
    quotient = prime;
  }
  if (value > q_high) return false;
  *first = value;
  *cofactor = quotient;
  return true;
}

std::vector<std::uint64_t> word_owner_prefix(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::vector<std::uint64_t>& prefix_primes) {
  const std::uint64_t odd_count = (q_high - q_low) / 2U + 1U;
  const std::uint64_t word_count = (odd_count + 63U) / 64U;
  std::vector<std::uint64_t> words(
      static_cast<std::size_t>(word_count), ~0ULL);
  for (const std::uint64_t prime : prefix_primes) {
    std::uint64_t composite = 0;
    std::uint64_t cofactor = 0;
    if (!first_odd_multiple(
            q_low, q_high, prime, &composite, &cofactor)) {
      continue;
    }
    const std::uint64_t step = 2U * prime;
    for (;;) {
      const std::uint64_t bit = (composite - q_low) / 2U;
      words[static_cast<std::size_t>(bit / 64U)] &=
          ~(1ULL << static_cast<unsigned>(bit & 63U));
      if (step > q_high - composite) break;
      composite += step;
    }
  }
  if ((odd_count & 63U) != 0U) {
    words.back() &=
        (1ULL << static_cast<unsigned>(odd_count & 63U)) - 1ULL;
  }
  return words;
}

HostCounts cpu_raw_tail(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::vector<std::uint64_t>& tail_primes,
    std::vector<std::uint64_t>* words) {
  HostCounts counts{};
  for (const std::uint64_t prime : tail_primes) {
    std::uint64_t composite = 0;
    std::uint64_t cofactor = 0;
    if (!first_odd_multiple(
            q_low, q_high, prime, &composite, &cofactor)) {
      continue;
    }
    const std::uint64_t step = 2U * prime;
    for (;;) {
      const std::uint64_t bit = (composite - q_low) / 2U;
      (*words)[static_cast<std::size_t>(bit / 64U)] &=
          ~(1ULL << static_cast<unsigned>(bit & 63U));
      ++counts.raw_visit_count;
      if (survives_small_wheel(cofactor)) {
        ++counts.small_wheel_survivor_count;
        if (survives_large_wheel(cofactor)) {
          ++counts.final_event_count;
        }
      }
      if (step > q_high - composite) break;
      composite += step;
      cofactor += 2U;
    }
  }
  return counts;
}

HostCounts cpu_current_wheel47_tail(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::vector<std::uint64_t>& tail_primes,
    std::vector<std::uint64_t>* words) {
  HostCounts counts{};
  for (const std::uint64_t prime : tail_primes) {
    std::uint64_t composite = 0;
    std::uint64_t cofactor = 0;
    if (!first_odd_multiple(
            q_low, q_high, prime, &composite, &cofactor)) {
      continue;
    }
    const std::uint64_t step = 2U * prime;
    for (;;) {
      ++counts.raw_visit_count;
      if (survives_small_wheel(cofactor)) {
        ++counts.small_wheel_survivor_count;
        if (survives_large_wheel(cofactor)) {
          const std::uint64_t bit = (composite - q_low) / 2U;
          (*words)[static_cast<std::size_t>(bit / 64U)] &=
              ~(1ULL << static_cast<unsigned>(bit & 63U));
          ++counts.final_event_count;
        }
      }
      if (step > q_high - composite) break;
      composite += step;
      cofactor += 2U;
    }
  }
  return counts;
}

HostCounts cpu_wheel_gap_tail(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::vector<std::uint64_t>& tail_primes,
    const std::array<unsigned char, kWheelOddEntries>& table,
    std::vector<std::uint64_t>* words) {
  HostCounts counts{};
  for (const std::uint64_t prime : tail_primes) {
    std::uint64_t composite = 0;
    std::uint64_t cofactor = 0;
    if (!first_odd_multiple(
            q_low, q_high, prime, &composite, &cofactor)) {
      continue;
    }
    unsigned char entry =
        table[static_cast<std::size_t>((cofactor % kWheelModulus) / 2U)];
    if ((entry & kWheelSurvivesFlag) == 0U) {
      const std::uint64_t gap = entry & kWheelGapMask;
      if (gap > (q_high - composite) / prime) continue;
      composite += prime * gap;
      cofactor += gap;
      entry =
          table[static_cast<std::size_t>((cofactor % kWheelModulus) / 2U)];
    }
    if ((entry & kWheelSurvivesFlag) == 0U) {
      throw std::runtime_error("CPU wheel-gap alignment failed");
    }
    for (;;) {
      ++counts.small_wheel_survivor_count;
      if (survives_large_wheel(cofactor)) {
        const std::uint64_t bit = (composite - q_low) / 2U;
        (*words)[static_cast<std::size_t>(bit / 64U)] &=
            ~(1ULL << static_cast<unsigned>(bit & 63U));
        ++counts.final_event_count;
      }
      const std::uint64_t gap = entry & kWheelGapMask;
      if (gap > (q_high - composite) / prime) break;
      composite += prime * gap;
      cofactor += gap;
      entry =
          table[static_cast<std::size_t>((cofactor % kWheelModulus) / 2U)];
      if ((entry & kWheelSurvivesFlag) == 0U) {
        throw std::runtime_error("CPU wheel-gap recurrence left survivors");
      }
    }
  }
  return counts;
}

__device__ __forceinline__ bool device_survives_small_wheel(
    std::uint64_t cofactor) {
  const std::uint32_t residue =
      static_cast<std::uint32_t>(cofactor % 15'015ULL);
  return residue % 3U != 0U && residue % 5U != 0U &&
         residue % 7U != 0U && residue % 11U != 0U &&
         residue % 13U != 0U;
}

template <bool Instrument>
__global__ void ordinary_raw_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words,
    const unsigned char* __restrict__ wheel_table,
    Counts* __restrict__ counts) {
  (void)wheel_table;
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  if (prime < 3U || prime > q_high / prime) return;
  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t composite = quotient * prime;
  if ((composite & 1U) == 0U) {
    if (composite > q_high - prime) return;
    composite += prime;
    ++quotient;
  }
  const std::uint64_t square = prime * prime;
  if (composite < square) {
    composite = square;
    quotient = prime;
  }
  if (composite > q_high) return;
  const std::uint64_t step = 2U * prime;
  std::uint64_t cofactor = quotient;
  for (;;) {
    const std::uint64_t bit = (composite - q_low) / 2U;
    atomicAnd(words + bit / 64U,
              ~(1ULL << static_cast<unsigned>(bit & 63U)));
    if constexpr (Instrument) {
      atomicAdd(&counts->raw_visit_count, 1ULL);
      if (device_survives_small_wheel(cofactor)) {
        atomicAdd(&counts->small_wheel_survivor_count, 1ULL);
        if (survives_large_wheel(cofactor)) {
          atomicAdd(&counts->final_event_count, 1ULL);
        }
      }
    }
    if (step > q_high - composite) break;
    composite += step;
    cofactor += 2U;
  }
}

template <bool Instrument>
__global__ void current_wheel47_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words,
    const unsigned char* __restrict__ wheel_table,
    Counts* __restrict__ counts) {
  (void)wheel_table;
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  if (prime < 3U || prime > q_high / prime) return;
  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t composite = quotient * prime;
  if ((composite & 1U) == 0U) {
    if (composite > q_high - prime) return;
    composite += prime;
    ++quotient;
  }
  const std::uint64_t square = prime * prime;
  if (composite < square) {
    composite = square;
    quotient = prime;
  }
  if (composite > q_high) return;
  const std::uint64_t step = 2U * prime;
  std::uint64_t cofactor = quotient;
  for (;;) {
    if constexpr (Instrument) {
      atomicAdd(&counts->raw_visit_count, 1ULL);
    }
    if (device_survives_small_wheel(cofactor)) {
      if constexpr (Instrument) {
        atomicAdd(&counts->small_wheel_survivor_count, 1ULL);
      }
      if (survives_large_wheel(cofactor)) {
        const std::uint64_t bit = (composite - q_low) / 2U;
        atomicAnd(words + bit / 64U,
                  ~(1ULL << static_cast<unsigned>(bit & 63U)));
        if constexpr (Instrument) {
          atomicAdd(&counts->final_event_count, 1ULL);
        }
      }
    }
    if (step > q_high - composite) break;
    composite += step;
    cofactor += 2U;
  }
}

__device__ __forceinline__ unsigned char wheel_gap_entry(
    std::uint32_t wheel_index,
    const unsigned char* __restrict__ wheel_table) {
  return __ldg(wheel_table + wheel_index);
}

__device__ __forceinline__ std::uint32_t advance_wheel_index(
    std::uint32_t wheel_index, std::uint32_t gap) {
  wheel_index += gap / 2U;
  if (wheel_index >= kWheelOddEntries) {
    wheel_index -= kWheelOddEntries;
  }
  return wheel_index;
}

template <bool Instrument>
__global__ void wheel_gap_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words,
    const unsigned char* __restrict__ wheel_table,
    Counts* __restrict__ counts) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  if (prime < 3U || prime > q_high / prime) return;
  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t composite = quotient * prime;
  if ((composite & 1U) == 0U) {
    if (composite > q_high - prime) return;
    composite += prime;
    ++quotient;
  }
  const std::uint64_t square = prime * prime;
  if (composite < square) {
    composite = square;
    quotient = prime;
  }
  if (composite > q_high) return;
  std::uint64_t cofactor = quotient;
  std::uint32_t wheel_index = static_cast<std::uint32_t>(
      (cofactor % kWheelModulus) / 2U);
  unsigned char entry = wheel_gap_entry(wheel_index, wheel_table);
  if ((entry & kWheelSurvivesFlag) == 0U) {
    const std::uint64_t gap = entry & kWheelGapMask;
    if (gap > (q_high - composite) / prime) return;
    composite += prime * gap;
    cofactor += gap;
    wheel_index =
        advance_wheel_index(wheel_index, static_cast<std::uint32_t>(gap));
    entry = wheel_gap_entry(wheel_index, wheel_table);
  }
  if ((entry & kWheelSurvivesFlag) == 0U) return;
  for (;;) {
    if constexpr (Instrument) {
      atomicAdd(&counts->small_wheel_survivor_count, 1ULL);
    }
    if (survives_large_wheel(cofactor)) {
      const std::uint64_t bit = (composite - q_low) / 2U;
      atomicAnd(words + bit / 64U,
                ~(1ULL << static_cast<unsigned>(bit & 63U)));
      if constexpr (Instrument) {
        atomicAdd(&counts->final_event_count, 1ULL);
      }
    }
    const std::uint64_t gap = entry & kWheelGapMask;
    if (gap > (q_high - composite) / prime) break;
    composite += prime * gap;
    cofactor += gap;
    wheel_index =
        advance_wheel_index(wheel_index, static_cast<std::uint32_t>(gap));
    entry = wheel_gap_entry(wheel_index, wheel_table);
    if ((entry & kWheelSurvivesFlag) == 0U) return;
  }
}

__device__ __forceinline__ std::uint32_t advance_remainder(
    std::uint32_t remainder, std::uint32_t gap, std::uint32_t modulus) {
  remainder += gap;
  if (remainder >= modulus) remainder -= modulus;
  if (remainder >= modulus) remainder -= modulus;
  return remainder;
}

template <bool Instrument>
__global__ void wheel_gap_remainder_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words,
    const unsigned char* __restrict__ wheel_table,
    Counts* __restrict__ counts) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  if (prime < 3U || prime > q_high / prime) return;
  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t composite = quotient * prime;
  if ((composite & 1U) == 0U) {
    if (composite > q_high - prime) return;
    composite += prime;
    ++quotient;
  }
  const std::uint64_t square = prime * prime;
  if (composite < square) {
    composite = square;
    quotient = prime;
  }
  if (composite > q_high) return;
  std::uint64_t cofactor = quotient;
  std::uint32_t wheel_index = static_cast<std::uint32_t>(
      (cofactor % kWheelModulus) / 2U);
  unsigned char entry = wheel_gap_entry(wheel_index, wheel_table);
  if ((entry & kWheelSurvivesFlag) == 0U) {
    const std::uint64_t gap = entry & kWheelGapMask;
    if (gap > (q_high - composite) / prime) return;
    composite += prime * gap;
    cofactor += gap;
    wheel_index =
        advance_wheel_index(wheel_index, static_cast<std::uint32_t>(gap));
    entry = wheel_gap_entry(wheel_index, wheel_table);
  }
  if ((entry & kWheelSurvivesFlag) == 0U) return;

  std::uint32_t r17 = static_cast<std::uint32_t>(cofactor % 17U);
  std::uint32_t r19 = static_cast<std::uint32_t>(cofactor % 19U);
  std::uint32_t r23 = static_cast<std::uint32_t>(cofactor % 23U);
  std::uint32_t r29 = static_cast<std::uint32_t>(cofactor % 29U);
  std::uint32_t r31 = static_cast<std::uint32_t>(cofactor % 31U);
  std::uint32_t r37 = static_cast<std::uint32_t>(cofactor % 37U);
  std::uint32_t r41 = static_cast<std::uint32_t>(cofactor % 41U);
  std::uint32_t r43 = static_cast<std::uint32_t>(cofactor % 43U);
  std::uint32_t r47 = static_cast<std::uint32_t>(cofactor % 47U);
  for (;;) {
    if constexpr (Instrument) {
      atomicAdd(&counts->small_wheel_survivor_count, 1ULL);
    }
    if (r17 != 0U && r19 != 0U && r23 != 0U && r29 != 0U &&
        r31 != 0U && r37 != 0U && r41 != 0U && r43 != 0U &&
        r47 != 0U) {
      const std::uint64_t bit = (composite - q_low) / 2U;
      atomicAnd(words + bit / 64U,
                ~(1ULL << static_cast<unsigned>(bit & 63U)));
      if constexpr (Instrument) {
        atomicAdd(&counts->final_event_count, 1ULL);
      }
    }
    const std::uint32_t gap = entry & kWheelGapMask;
    if (gap > (q_high - composite) / prime) break;
    composite += prime * gap;
    cofactor += gap;
    r17 = advance_remainder(r17, gap, 17U);
    r19 = advance_remainder(r19, gap, 19U);
    r23 = advance_remainder(r23, gap, 23U);
    r29 = advance_remainder(r29, gap, 29U);
    r31 = advance_remainder(r31, gap, 31U);
    r37 = advance_remainder(r37, gap, 37U);
    r41 = advance_remainder(r41, gap, 41U);
    r43 = advance_remainder(r43, gap, 43U);
    r47 = advance_remainder(r47, gap, 47U);
    wheel_index = advance_wheel_index(wheel_index, gap);
    entry = wheel_gap_entry(wheel_index, wheel_table);
    if ((entry & kWheelSurvivesFlag) == 0U) return;
  }
}

HostCounts copy_counts(const Counts& counts) {
  return {
      counts.raw_visit_count,
      counts.small_wheel_survivor_count,
      counts.final_event_count,
  };
}

bool same_counts(const HostCounts& left, const HostCounts& right) {
  return left.raw_visit_count == right.raw_visit_count &&
         left.small_wheel_survivor_count ==
             right.small_wheel_survivor_count &&
         left.final_event_count == right.final_event_count;
}

void compare_words(const std::vector<std::uint64_t>& expected,
                   const std::vector<std::uint64_t>& actual,
                   std::string_view what) {
  if (expected.size() != actual.size()) {
    throw std::runtime_error(std::string(what) + " has wrong word count");
  }
  const auto mismatch =
      std::mismatch(expected.begin(), expected.end(), actual.begin());
  if (mismatch.first != expected.end()) {
    throw std::runtime_error(
        std::string(what) + " differs at word " +
        std::to_string(mismatch.first - expected.begin()));
  }
}

std::uint64_t set_bit_count(const std::vector<std::uint64_t>& words) {
  return std::accumulate(
      words.begin(), words.end(), std::uint64_t{0},
      [](std::uint64_t total, std::uint64_t word) {
        return total + std::popcount(word);
      });
}

void update_canonical_words(
    sparkinterval::detail::Sha256* hasher,
    const std::vector<std::uint64_t>& words) {
  for (const std::uint64_t word : words) {
    unsigned char bytes[8];
    for (unsigned index = 0; index < 8U; ++index) {
      bytes[index] =
          static_cast<unsigned char>(word >> (8U * index));
    }
    hasher->update(bytes, sizeof(bytes));
  }
}

std::string canonical_word_sha256(
    const std::vector<std::uint64_t>& words) {
  sparkinterval::detail::Sha256 hasher;
  update_canonical_words(&hasher, words);
  return sparkinterval::lowercase_hex(hasher.finish());
}

Geometry make_historical_geometry(std::uint64_t segment_start,
                                  std::string name) {
  const std::uint64_t segment_end = std::min(
      segment_start + 2U * kHistoricalSegmentEvenCount - 2U,
      kHistoricalLimit);
  std::uint64_t q_low =
      segment_start > kHistoricalPSmall
          ? segment_start - kHistoricalPSmall
          : 3U;
  if ((q_low & 1U) == 0U) ++q_low;
  std::uint64_t q_high =
      segment_end < std::numeric_limits<std::uint64_t>::max() - 1U
          ? segment_end + 1U
          : segment_end;
  if ((q_high & 1U) == 0U) ++q_high;
  return {std::move(name), q_low, q_high};
}

std::vector<Geometry> benchmark_geometries(std::string_view mode) {
  if (mode == "source-segment") {
    return {make_historical_geometry(
        kHistoricalStart + 4U * kHistoricalSegmentEvenCount,
        "historical-terminal-segment")};
  }
  if (mode == "terminal-600m") {
    std::vector<Geometry> result;
    for (unsigned index = 0; index < 3U; ++index) {
      result.push_back(make_historical_geometry(
          kHistoricalStart +
              2U * kHistoricalSegmentEvenCount * index,
          "historical-segment-" + std::to_string(index)));
    }
    return result;
  }
  return {{
      "bounded-source-height",
      31'249'998'799'000'003ULL,
      31'249'998'799'000'003ULL + 2U * (kBoundedOddCount - 1U),
  }};
}

PreparedWindow prepare_window(
    const Geometry& geometry,
    const std::vector<std::uint64_t>& prefix_primes,
    const std::vector<std::uint64_t>& tail_primes,
    const std::array<unsigned char, kWheelOddEntries>& table) {
  PreparedWindow result;
  result.geometry = geometry;
  result.initial = word_owner_prefix(
      geometry.q_low, geometry.q_high, prefix_primes);
  result.expected = result.initial;
  result.counts = cpu_raw_tail(
      geometry.q_low, geometry.q_high, tail_primes, &result.expected);

  std::vector<std::uint64_t> current = result.initial;
  const HostCounts current_counts = cpu_current_wheel47_tail(
      geometry.q_low, geometry.q_high, tail_primes, &current);
  std::vector<std::uint64_t> gap = result.initial;
  const HostCounts gap_counts = cpu_wheel_gap_tail(
      geometry.q_low, geometry.q_high, tail_primes, table, &gap);
  compare_words(result.expected, current, "CPU current wheel47 output");
  compare_words(result.expected, gap, "CPU wheel-gap output");
  if (!same_counts(result.counts, current_counts) ||
      current_counts.small_wheel_survivor_count !=
          gap_counts.small_wheel_survivor_count ||
      current_counts.final_event_count != gap_counts.final_event_count) {
    throw std::runtime_error("independent CPU event counts differ");
  }
  return result;
}

template <typename Kernel>
HostCounts run_instrumented(
    Kernel kernel, const PreparedWindow& window,
    std::uint64_t* device_primes, std::uint64_t prime_count,
    unsigned long long* device_words,
    const unsigned char* device_wheel_table,
    Counts* device_counts,
    bool supplies_raw_count) {
  const std::size_t bytes =
      window.initial.size() * sizeof(std::uint64_t);
  cuda_check(cudaMemcpy(device_words, window.initial.data(), bytes,
                        cudaMemcpyHostToDevice),
             "copy instrumented initial words");
  cuda_check(cudaMemset(device_counts, 0, sizeof(Counts)),
             "clear instrumented counts");
  const unsigned blocks = static_cast<unsigned>(
      (prime_count + kThreads - 1U) / kThreads);
  kernel<<<blocks, kThreads>>>(
      window.geometry.q_low, window.geometry.q_high,
      device_primes, prime_count, device_words, device_wheel_table,
      device_counts);
  cuda_check(cudaGetLastError(), "launch instrumented tail");
  cuda_check(cudaDeviceSynchronize(), "synchronize instrumented tail");
  std::vector<std::uint64_t> output(window.initial.size());
  Counts counts{};
  cuda_check(cudaMemcpy(output.data(), device_words, bytes,
                        cudaMemcpyDeviceToHost),
             "copy instrumented words");
  cuda_check(cudaMemcpy(&counts, device_counts, sizeof(Counts),
                        cudaMemcpyDeviceToHost),
             "copy instrumented counts");
  compare_words(window.expected, output, "instrumented CUDA output");
  HostCounts result = copy_counts(counts);
  if (!supplies_raw_count) {
    result.raw_visit_count = window.counts.raw_visit_count;
  }
  return result;
}

template <typename Launch>
double timed_launch(Launch launch) {
  cudaEvent_t begin = nullptr;
  cudaEvent_t end = nullptr;
  cuda_check(cudaEventCreate(&begin), "cudaEventCreate begin");
  cuda_check(cudaEventCreate(&end), "cudaEventCreate end");
  try {
    cuda_check(cudaEventRecord(begin), "cudaEventRecord begin");
    launch();
    cuda_check(cudaEventRecord(end), "cudaEventRecord end");
    cuda_check(cudaEventSynchronize(end), "cudaEventSynchronize end");
    float elapsed = 0.0F;
    cuda_check(cudaEventElapsedTime(&elapsed, begin, end),
               "cudaEventElapsedTime");
    cuda_check(cudaEventDestroy(end), "cudaEventDestroy end");
    end = nullptr;
    cuda_check(cudaEventDestroy(begin), "cudaEventDestroy begin");
    begin = nullptr;
    return static_cast<double>(elapsed);
  } catch (...) {
    if (end != nullptr) cudaEventDestroy(end);
    if (begin != nullptr) cudaEventDestroy(begin);
    throw;
  }
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  return values[values.size() / 2U];
}

template <typename Kernel>
double time_algorithm(
    Kernel kernel, const std::vector<PreparedWindow>& windows,
    std::uint64_t* device_primes, std::uint64_t prime_count,
    unsigned long long* device_words,
    const unsigned char* device_wheel_table) {
  double total = 0.0;
  const unsigned blocks = static_cast<unsigned>(
      (prime_count + kThreads - 1U) / kThreads);
  for (const PreparedWindow& window : windows) {
    const std::size_t bytes =
        window.initial.size() * sizeof(std::uint64_t);
    cuda_check(cudaMemcpy(device_words, window.initial.data(), bytes,
                          cudaMemcpyHostToDevice),
               "reset timed words");
    total += timed_launch([&]() {
      kernel<<<blocks, kThreads>>>(
          window.geometry.q_low, window.geometry.q_high,
          device_primes, prime_count, device_words, device_wheel_table,
          nullptr);
      cuda_check(cudaGetLastError(), "launch timed whole tail");
    });
  }
  return total;
}

BenchmarkResult run_benchmark(
    std::string mode, const std::vector<PreparedWindow>& windows,
    std::uint64_t prime_limit,
    const std::vector<std::uint64_t>& tail_primes,
    std::uint64_t* device_primes, unsigned rounds,
    unsigned long long* device_words,
    const unsigned char* device_wheel_table) {
  BenchmarkResult result{};
  result.geometry = std::move(mode);
  result.window_count = windows.size();
  result.prime_limit = prime_limit;
  result.tail_prime_count = tail_primes.size();
  result.rounds = rounds;
  sparkinterval::detail::Sha256 output_hasher;
  for (const PreparedWindow& window : windows) {
    result.total_odd_count +=
        (window.geometry.q_high - window.geometry.q_low) / 2U + 1U;
    result.counts.raw_visit_count += window.counts.raw_visit_count;
    result.counts.small_wheel_survivor_count +=
        window.counts.small_wheel_survivor_count;
    result.counts.final_event_count += window.counts.final_event_count;
    update_canonical_words(&output_hasher, window.expected);
  }
  result.output_sha256 =
      sparkinterval::lowercase_hex(output_hasher.finish());

  time_algorithm(
      ordinary_raw_tail_kernel<false>, windows, device_primes,
      tail_primes.size(), device_words, device_wheel_table);
  time_algorithm(
      current_wheel47_tail_kernel<false>, windows, device_primes,
      tail_primes.size(), device_words, device_wheel_table);
  time_algorithm(
      wheel_gap_tail_kernel<false>, windows, device_primes,
      tail_primes.size(), device_words, device_wheel_table);
  time_algorithm(
      wheel_gap_remainder_tail_kernel<false>, windows, device_primes,
      tail_primes.size(), device_words, device_wheel_table);

  for (unsigned round = 0; round < rounds; ++round) {
    for (unsigned offset = 0; offset < 4U; ++offset) {
      switch ((round + offset) & 3U) {
        case 0:
          result.timings.ordinary_raw_ms.push_back(time_algorithm(
              ordinary_raw_tail_kernel<false>, windows, device_primes,
              tail_primes.size(), device_words, device_wheel_table));
          break;
        case 1:
          result.timings.current_wheel47_ms.push_back(time_algorithm(
              current_wheel47_tail_kernel<false>, windows, device_primes,
              tail_primes.size(), device_words, device_wheel_table));
          break;
        case 2:
          result.timings.wheel_gap_ms.push_back(time_algorithm(
              wheel_gap_tail_kernel<false>, windows, device_primes,
              tail_primes.size(), device_words, device_wheel_table));
          break;
        default:
          result.timings.wheel_gap_remainders_ms.push_back(time_algorithm(
              wheel_gap_remainder_tail_kernel<false>, windows,
              device_primes, tail_primes.size(), device_words,
              device_wheel_table));
          break;
      }
    }
  }
  result.timings.ordinary_raw_median_ms =
      median(result.timings.ordinary_raw_ms);
  result.timings.current_wheel47_median_ms =
      median(result.timings.current_wheel47_ms);
  result.timings.wheel_gap_median_ms =
      median(result.timings.wheel_gap_ms);
  result.timings.wheel_gap_remainders_median_ms =
      median(result.timings.wheel_gap_remainders_ms);
  return result;
}

CaseResult run_case(
    std::string name, const Geometry& geometry,
    const std::vector<std::uint64_t>& prefix_primes,
    const std::vector<std::uint64_t>& tail_primes,
    const std::array<unsigned char, kWheelOddEntries>& table,
    std::uint64_t* device_primes, unsigned long long* device_words,
    const unsigned char* device_wheel_table, Counts* device_counts) {
  const PreparedWindow window =
      prepare_window(geometry, prefix_primes, tail_primes, table);
  const HostCounts raw = run_instrumented(
      ordinary_raw_tail_kernel<true>, window, device_primes,
      tail_primes.size(), device_words, device_wheel_table,
      device_counts, true);
  const HostCounts current = run_instrumented(
      current_wheel47_tail_kernel<true>, window, device_primes,
      tail_primes.size(), device_words, device_wheel_table,
      device_counts, true);
  const HostCounts gap = run_instrumented(
      wheel_gap_tail_kernel<true>, window, device_primes,
      tail_primes.size(), device_words, device_wheel_table,
      device_counts, false);
  const HostCounts remainders = run_instrumented(
      wheel_gap_remainder_tail_kernel<true>, window, device_primes,
      tail_primes.size(), device_words, device_wheel_table,
      device_counts, false);
  if (!same_counts(window.counts, raw) ||
      !same_counts(window.counts, current) ||
      !same_counts(window.counts, gap) ||
      !same_counts(window.counts, remainders)) {
    throw std::runtime_error("CUDA whole-tail event counts differ from CPU");
  }
  const std::uint64_t odd_count =
      (geometry.q_high - geometry.q_low) / 2U + 1U;
  return {
      std::move(name),
      geometry.q_low,
      geometry.q_high,
      odd_count,
      window.counts,
      set_bit_count(window.expected),
      canonical_word_sha256(window.expected),
  };
}

void print_counts(const HostCounts& counts) {
  std::cout << "{\"final_event_count\":" << counts.final_event_count
            << ",\"raw_visit_count\":" << counts.raw_visit_count
            << ",\"small_wheel_survivor_count\":"
            << counts.small_wheel_survivor_count << "}";
}

void print_case(const CaseResult& result) {
  std::cout << "{\"counts\":";
  print_counts(result.counts);
  std::cout << ",\"name\":\"" << result.name << "\""
            << ",\"odd_count\":" << result.odd_count
            << ",\"output_sha256\":\"" << result.output_sha256 << "\""
            << ",\"q_high\":\"" << result.q_high << "\""
            << ",\"q_low\":\"" << result.q_low << "\""
            << ",\"set_bits\":" << result.set_bits << "}";
}

void print_double_array(const std::vector<double>& values) {
  std::cout << "[";
  for (std::size_t index = 0; index < values.size(); ++index) {
    if (index != 0U) std::cout << ",";
    std::cout << std::fixed << std::setprecision(6) << values[index];
  }
  std::cout << "]";
}

void print_benchmark(const BenchmarkResult& result) {
  std::cout << "{\"counts\":";
  print_counts(result.counts);
  std::cout << ",\"current_over_gap_rate_ratio\":"
            << std::fixed << std::setprecision(9)
            << result.timings.current_wheel47_median_ms /
                   result.timings.wheel_gap_median_ms
            << ",\"current_over_gap_remainders_rate_ratio\":"
            << result.timings.current_wheel47_median_ms /
                   result.timings.wheel_gap_remainders_median_ms
            << ",\"geometry\":\"" << result.geometry << "\""
            << ",\"output_sha256\":\"" << result.output_sha256 << "\""
            << ",\"prime_limit\":" << result.prime_limit
            << ",\"rounds\":" << result.rounds
            << ",\"tail_prime_count\":" << result.tail_prime_count
            << ",\"timings\":{"
            << "\"current_wheel47_median_ms\":"
            << result.timings.current_wheel47_median_ms
            << ",\"current_wheel47_ms\":";
  print_double_array(result.timings.current_wheel47_ms);
  std::cout << ",\"ordinary_raw_median_ms\":"
            << result.timings.ordinary_raw_median_ms
            << ",\"ordinary_raw_ms\":";
  print_double_array(result.timings.ordinary_raw_ms);
  std::cout << ",\"wheel_gap_median_ms\":"
            << result.timings.wheel_gap_median_ms
            << ",\"wheel_gap_ms\":";
  print_double_array(result.timings.wheel_gap_ms);
  std::cout << ",\"wheel_gap_remainders_median_ms\":"
            << result.timings.wheel_gap_remainders_median_ms
            << ",\"wheel_gap_remainders_ms\":";
  print_double_array(result.timings.wheel_gap_remainders_ms);
  std::cout << "}"
            << ",\"total_odd_count\":" << result.total_odd_count
            << ",\"window_count\":" << result.window_count << "}";
}

void print_resources(const cudaFuncAttributes& attributes) {
  std::cout << "{\"local_bytes_per_thread\":"
            << attributes.localSizeBytes
            << ",\"max_threads_per_block\":"
            << attributes.maxThreadsPerBlock
            << ",\"registers_per_thread\":" << attributes.numRegs
            << ",\"static_constant_bytes\":"
            << attributes.constSizeBytes
            << ",\"static_shared_bytes\":"
            << attributes.sharedSizeBytes << "}";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::string mode = "bounded";
    if (argc == 2 &&
        (std::string_view(argv[1]) == "--source-segment" ||
         std::string_view(argv[1]) == "--terminal-600m")) {
      mode = std::string(argv[1] + 2);
    } else if (argc != 1) {
      throw std::runtime_error(
          "usage: qualifier [--source-segment|--terminal-600m]");
    }

    int device_count = 0;
    cuda_check(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount");
    if (device_count < 1) throw std::runtime_error("no CUDA device");
    cudaDeviceProp properties{};
    cuda_check(cudaGetDeviceProperties(&properties, 0),
               "cudaGetDeviceProperties");

    const auto table = make_wheel_gap_table();
    validate_wheel_gap_table(table);

    const std::vector<Geometry> geometries = benchmark_geometries(mode);
    const std::uint64_t maximum_q_high = std::max_element(
        geometries.begin(), geometries.end(),
        [](const Geometry& left, const Geometry& right) {
          return left.q_high < right.q_high;
        })->q_high;
    const std::uint64_t prime_limit =
        mode == "bounded" ? kBoundedPrimeLimit
                          : integer_sqrt(maximum_q_high);
    const std::vector<std::uint64_t> prefix_primes =
        odd_primes_through(kWordOwnerCutoff, 2U);
    const std::vector<std::uint64_t> tail_primes =
        odd_primes_through(prime_limit, kWarpParallelCutoff);
    if (prefix_primes.empty() || tail_primes.empty()) {
      throw std::runtime_error("qualification prime roster is empty");
    }

    std::uint64_t* device_primes = nullptr;
    unsigned long long* device_words = nullptr;
    unsigned char* device_wheel_table = nullptr;
    Counts* device_counts = nullptr;
    const std::size_t maximum_words =
        static_cast<std::size_t>(std::max_element(
            geometries.begin(), geometries.end(),
            [](const Geometry& left, const Geometry& right) {
              return left.q_high - left.q_low <
                     right.q_high - right.q_low;
            })->q_high -
                                 std::max_element(
                                     geometries.begin(), geometries.end(),
                                     [](const Geometry& left,
                                        const Geometry& right) {
                                       return left.q_high - left.q_low <
                                              right.q_high - right.q_low;
                                     })->q_low) /
            2U +
        1U;
    const std::size_t maximum_word_count =
        (maximum_words + 63U) / 64U;
    cuda_check(cudaMalloc(
                   &device_primes,
                   tail_primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc tail primes");
    cuda_check(cudaMemcpy(
                   device_primes, tail_primes.data(),
                   tail_primes.size() * sizeof(std::uint64_t),
                   cudaMemcpyHostToDevice),
               "copy tail primes");
    cuda_check(cudaMalloc(
                   &device_words,
                   maximum_word_count * sizeof(std::uint64_t)),
               "cudaMalloc qualification words");
    cuda_check(cudaMalloc(&device_wheel_table, table.size()),
               "cudaMalloc immutable wheel table");
    cuda_check(cudaMemcpy(
                   device_wheel_table, table.data(), table.size(),
                   cudaMemcpyHostToDevice),
               "copy immutable wheel table");
    cuda_check(cudaMalloc(&device_counts, sizeof(Counts)),
               "cudaMalloc qualification counts");

    std::vector<PreparedWindow> prepared;
    prepared.reserve(geometries.size());
    for (const Geometry& geometry : geometries) {
      prepared.push_back(
          prepare_window(geometry, prefix_primes, tail_primes, table));
    }
    const BenchmarkResult benchmark = run_benchmark(
        mode, prepared, prime_limit, tail_primes, device_primes,
        mode == "bounded" ? kBoundedRounds : kSourceRounds,
        device_words, device_wheel_table);

    const std::vector<std::uint64_t> bounded_tail_primes =
        odd_primes_through(262'147U, kWarpParallelCutoff);
    std::uint64_t* bounded_device_primes = nullptr;
    cuda_check(cudaMalloc(
                   &bounded_device_primes,
                   bounded_tail_primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc bounded case primes");
    cuda_check(cudaMemcpy(
                   bounded_device_primes, bounded_tail_primes.data(),
                   bounded_tail_primes.size() * sizeof(std::uint64_t),
                   cudaMemcpyHostToDevice),
               "copy bounded case primes");
    std::vector<CaseResult> cases;
    const std::uint64_t square = 32'771ULL * 32'771ULL;
    cases.push_back(run_case(
        "low-inactive",
        {"low-inactive", 4'000'001ULL,
         4'000'001ULL + 2U * ((1ULL << 17U) - 1U)},
        prefix_primes, bounded_tail_primes, table, bounded_device_primes,
        device_words, device_wheel_table, device_counts));
    cases.push_back(run_case(
        "prime-square-activation",
        {"prime-square-activation", square - 2U * (1ULL << 16U),
         square + 2U * ((1ULL << 17U) - (1ULL << 16U) - 1U)},
        prefix_primes, bounded_tail_primes, table, bounded_device_primes,
        device_words, device_wheel_table, device_counts));
    cases.push_back(run_case(
        "source-height",
        {"source-height", 31'249'998'799'000'003ULL,
         31'249'998'799'000'003ULL +
             2U * ((1ULL << 18U) - 1U)},
        prefix_primes, bounded_tail_primes, table, bounded_device_primes,
        device_words, device_wheel_table, device_counts));
    cases.push_back(run_case(
        "non-word-aligned-end",
        {"non-word-aligned-end", 31'249'998'799'000'003ULL,
         31'249'998'799'000'003ULL + 2U * (262'147ULL - 1U)},
        prefix_primes, bounded_tail_primes, table, bounded_device_primes,
        device_words, device_wheel_table, device_counts));
    cases.push_back(run_case(
        "uint64-overflow-edge",
        {"uint64-overflow-edge",
         std::numeric_limits<std::uint64_t>::max() -
             2U * ((1ULL << 18U) - 1U),
         std::numeric_limits<std::uint64_t>::max()},
        prefix_primes, bounded_tail_primes, table, bounded_device_primes,
        device_words, device_wheel_table, device_counts));
    cuda_check(cudaFree(bounded_device_primes),
               "cudaFree bounded case primes");

    cudaFuncAttributes raw_attributes{};
    cudaFuncAttributes current_attributes{};
    cudaFuncAttributes gap_attributes{};
    cudaFuncAttributes remainder_attributes{};
    cuda_check(cudaFuncGetAttributes(
                   &raw_attributes, ordinary_raw_tail_kernel<false>),
               "cudaFuncGetAttributes raw");
    cuda_check(cudaFuncGetAttributes(
                   &current_attributes, current_wheel47_tail_kernel<false>),
               "cudaFuncGetAttributes current");
    cuda_check(cudaFuncGetAttributes(
                   &gap_attributes, wheel_gap_tail_kernel<false>),
               "cudaFuncGetAttributes gap");
    cuda_check(cudaFuncGetAttributes(
                   &remainder_attributes,
                   wheel_gap_remainder_tail_kernel<false>),
               "cudaFuncGetAttributes remainder");
    const auto resources_ok = [](const cudaFuncAttributes& attributes,
                                 unsigned maximum_registers) {
      return attributes.localSizeBytes == 0U &&
             attributes.maxThreadsPerBlock >=
                 static_cast<int>(kThreads) &&
             attributes.numRegs > 0 &&
             attributes.numRegs <= static_cast<int>(maximum_registers) &&
             attributes.sharedSizeBytes == 0U;
    };
    if (!resources_ok(raw_attributes, 64U) ||
        !resources_ok(current_attributes, 64U) ||
        !resources_ok(gap_attributes, 64U) ||
        !resources_ok(remainder_attributes, 64U)) {
      throw std::runtime_error("qualification compiler-resource gate failed");
    }

    cuda_check(cudaFree(device_counts), "cudaFree qualification counts");
    cuda_check(cudaFree(device_wheel_table),
               "cudaFree immutable wheel table");
    cuda_check(cudaFree(device_words), "cudaFree qualification words");
    cuda_check(cudaFree(device_primes), "cudaFree tail primes");

    std::cout << "{\"accepted\":true"
              << ",\"benchmark\":";
    print_benchmark(benchmark);
    std::cout << ",\"bounded_case_count\":" << cases.size()
              << ",\"bounded_cases\":[";
    for (std::size_t index = 0; index < cases.size(); ++index) {
      if (index != 0U) std::cout << ",";
      print_case(cases[index]);
    }
    std::cout << "]"
              << ",\"compute_capability\":\"" << properties.major << "."
              << properties.minor << "\""
              << ",\"current_wheel47_resources\":";
    print_resources(current_attributes);
    std::cout << ",\"kind\":"
                 "\"sparkinterval.goldbach-wheel-gap-tail-qualification.v1\""
              << ",\"lean_bridge_complete\":false"
              << ",\"ordinary_raw_resources\":";
    print_resources(raw_attributes);
    std::cout << ",\"performance_evidence_eligible\":false"
              << ",\"production_identity_promoted\":false"
              << ",\"production_ready\":false"
              << ",\"release_build_profile_eligible\":true"
              << ",\"resource_gate_passed\":true"
              << ",\"runtime_instrumentation_status\":"
                 "\"not-inspected-by-runner\""
              << ",\"wheel_gap_remainder_resources\":";
    print_resources(remainder_attributes);
    std::cout << ",\"wheel_gap_resources\":";
    print_resources(gap_attributes);
    std::cout << ",\"wheel_table\":{"
              << "\"encoded_entry_count\":" << table.size()
              << ",\"maximum_even_gap\":"
              << static_cast<unsigned>(kExpectedMaximumGap)
              << ",\"modulus\":" << kWheelModulus
              << ",\"sha256\":\"" << wheel_table_sha256(table) << "\""
              << ",\"surviving_residue_count\":"
              << kExpectedWheelSurvivors << "}"
              << ",\"word_owner_cutoff\":" << kWordOwnerCutoff
              << ",\"warp_parallel_cutoff\":"
              << kWarpParallelCutoff << "}\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 2;
  }
  return 0;
}

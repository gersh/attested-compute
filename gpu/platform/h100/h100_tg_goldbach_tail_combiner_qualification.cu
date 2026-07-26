// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only experiment for combining Goldbach tail clears that
// target the same 64-bit word inside one CTA epoch.
//
// This file is deliberately absent from every default and production build.
// The invoking qualification runner must define the macro below explicitly.
// It compares:
//
//   * an independent CPU progression replay;
//   * the ordinary one-thread-per-prime global-atomic CUDA tail; and
//   * a CTA-local exact-key combiner with an unchanged global-atomic fallback.
//
// An eligible event takes exactly one of two routes.  A shared-table hit
// contributes its clear mask once to the exact word key; otherwise exhausting
// every active slot performs the original global atomicAnd once.  Keys remain
// immutable until a CTA barrier, each occupied slot is flushed once, and only
// then is the table reset for the next uniform epoch.

#ifndef SPARKINTERVAL_ENABLE_GOLDBACH_TAIL_COMBINER_QUALIFICATION
#error "the Goldbach tail combiner is qualification-only and macro guarded"
#endif

#include <cuda_runtime.h>

#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "sparkinterval/sha256.hpp"

namespace {

constexpr unsigned kThreads = 256;
constexpr unsigned kMaximumTableSlots = 512;
constexpr unsigned kEventsPerEpoch = 2;
constexpr std::uint64_t kWarpParallelCutoff = 32'749;
constexpr std::uint64_t kWordOwnerCutoff = 2'039;
constexpr std::uint64_t kEmptyKey =
    std::numeric_limits<std::uint64_t>::max();
constexpr std::uint64_t kBoundedPrimeLimit = 262'147;
constexpr std::uint64_t kBoundedOddCount = 1ULL << 18U;
constexpr std::uint64_t kPerformanceOddCount = 1ULL << 22U;
constexpr std::uint64_t kPerformancePrimeLimit = 2'000'003;
constexpr unsigned kBoundedRounds = 7;
constexpr unsigned kSourceRounds = 9;
constexpr std::uint64_t kSourceLimit = 31'250'000'000'000'000ULL;
constexpr std::uint64_t kSourceSegmentStart =
    31'249'999'600'000'002ULL;
constexpr std::uint64_t kSourceQLow =
    kSourceSegmentStart - 1'000'000ULL + 1ULL;
constexpr std::uint64_t kSourceQHigh = kSourceLimit + 1ULL;
constexpr std::uint64_t kSourceOddCount =
    (kSourceQHigh - kSourceQLow) / 2ULL + 1ULL;

static_assert(kSourceQLow % 2ULL == 1ULL);
static_assert(kSourceQHigh % 2ULL == 1ULL);
static_assert(kSourceOddCount == 200'500'000ULL);
static_assert(std::has_single_bit(kMaximumTableSlots));

struct DeviceCounters {
  unsigned long long eligible_event_count;
  unsigned long long combined_event_count;
  unsigned long long fallback_event_count;
  unsigned long long flushed_entry_count;
  unsigned long long collision_probe_count;
};

struct HostCounters {
  std::uint64_t eligible_event_count = 0;
  std::uint64_t combined_event_count = 0;
  std::uint64_t fallback_event_count = 0;
  std::uint64_t flushed_entry_count = 0;
  std::uint64_t collision_probe_count = 0;
};

struct CaseResult {
  std::string name;
  std::uint64_t q_low = 0;
  std::uint64_t q_high = 0;
  std::uint64_t odd_count = 0;
  unsigned table_slots = 0;
  bool force_hash_collision = false;
  bool patterned_initial_words = false;
  std::uint64_t cpu_event_count = 0;
  HostCounters counters;
  std::uint64_t set_bits = 0;
  std::string output_sha256;
};

struct BenchmarkResult {
  std::string geometry;
  std::uint64_t q_low = 0;
  std::uint64_t q_high = 0;
  std::uint64_t odd_count = 0;
  std::uint64_t prime_limit = 0;
  std::uint64_t tail_prime_count = 0;
  std::uint64_t cpu_event_count = 0;
  HostCounters routing_counters;
  unsigned rounds = 0;
  std::vector<double> ordinary_ms;
  std::vector<double> candidate_ms;
  double ordinary_median_ms = 0.0;
  double candidate_median_ms = 0.0;
  double observed_rate_ratio = 0.0;
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

std::vector<std::uint64_t> tail_primes_through(std::uint64_t limit) {
  if (limit < kWarpParallelCutoff + 2U) return {};
  if (limit > static_cast<std::uint64_t>(
                  std::numeric_limits<std::size_t>::max() - 1U)) {
    throw std::runtime_error("prime limit is not host-addressable");
  }
  std::vector<unsigned char> composite(
      static_cast<std::size_t>(limit + 1U), 0U);
  for (std::uint64_t prime = 2; prime <= limit / prime; ++prime) {
    if (composite[static_cast<std::size_t>(prime)] != 0U) continue;
    for (std::uint64_t value = prime * prime; value <= limit;
         value += prime) {
      composite[static_cast<std::size_t>(value)] = 1U;
    }
  }
  std::vector<std::uint64_t> result;
  for (std::uint64_t value = kWarpParallelCutoff + 2U; value <= limit;
       value += 2U) {
    if (composite[static_cast<std::size_t>(value)] == 0U) {
      result.push_back(value);
    }
  }
  return result;
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

__host__ __device__ bool cofactor_survives_word_owner_wheel(
    std::uint64_t cofactor) {
  const std::uint32_t residue =
      static_cast<std::uint32_t>(cofactor % 15'015ULL);
  return residue % 3U != 0U && residue % 5U != 0U &&
         residue % 7U != 0U && residue % 11U != 0U &&
         residue % 13U != 0U && cofactor % 17U != 0U &&
         cofactor % 19U != 0U && cofactor % 23U != 0U &&
         cofactor % 29U != 0U && cofactor % 31U != 0U &&
         cofactor % 37U != 0U && cofactor % 41U != 0U &&
         cofactor % 43U != 0U && cofactor % 47U != 0U;
}

std::vector<std::uint64_t> initial_words(std::uint64_t odd_count,
                                         bool patterned) {
  const std::uint64_t word_count = (odd_count + 63U) / 64U;
  std::vector<std::uint64_t> words(
      static_cast<std::size_t>(word_count),
      std::numeric_limits<std::uint64_t>::max());
  if (patterned) {
    for (std::uint64_t index = 0; index < word_count; ++index) {
      const unsigned bit =
          static_cast<unsigned>((17U * index + 3U) & 63U);
      words[static_cast<std::size_t>(index)] &= ~(1ULL << bit);
    }
  }
  if ((odd_count & 63U) != 0U) {
    words.back() &=
        (1ULL << static_cast<unsigned>(odd_count & 63U)) - 1ULL;
  }
  return words;
}

std::uint64_t cpu_mark(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::vector<std::uint64_t>& primes,
    std::vector<std::uint64_t>* words) {
  std::uint64_t events = 0;
  for (const std::uint64_t prime : primes) {
    std::uint64_t composite = 0;
    std::uint64_t cofactor = 0;
    if (!first_odd_multiple(q_low, q_high, prime, &composite, &cofactor)) {
      continue;
    }
    const std::uint64_t step = 2U * prime;
    for (;;) {
      if (cofactor_survives_word_owner_wheel(cofactor)) {
        const std::uint64_t bit = (composite - q_low) / 2U;
        (*words)[static_cast<std::size_t>(bit / 64U)] &=
            ~(1ULL << static_cast<unsigned>(bit & 63U));
        ++events;
      }
      if (step > q_high - composite) break;
      composite += step;
      cofactor += 2U;
    }
  }
  return events;
}

__global__ void ordinary_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words) {
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
    if (cofactor_survives_word_owner_wheel(cofactor)) {
      const std::uint64_t bit = (composite - q_low) / 2U;
      atomicAnd(words + bit / 64U,
                ~(1ULL << static_cast<unsigned>(bit & 63U)));
    }
    if (step > q_high - composite) break;
    composite += step;
    cofactor += 2U;
  }
}

__device__ __forceinline__ unsigned table_hash(std::uint64_t word,
                                                unsigned table_slots,
                                                bool force_collision) {
  if (force_collision) return 0U;
  return static_cast<unsigned>(
      (word * 11'400'714'819'323'198'485ULL) & (table_slots - 1U));
}

template <bool Instrument>
__global__ void combined_tail_kernel(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes,
    std::uint64_t prime_count,
    unsigned long long* __restrict__ words, unsigned table_slots,
    bool force_hash_collision, DeviceCounters* __restrict__ counters) {
  __shared__ unsigned long long keys[kMaximumTableSlots];
  __shared__ unsigned long long masks[kMaximumTableSlots];

  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  bool active = false;
  std::uint64_t prime = 0;
  std::uint64_t composite = 0;
  std::uint64_t cofactor = 0;
  std::uint64_t step = 0;
  if (index < prime_count) {
    prime = primes[index];
    if (prime >= 3U && prime <= q_high / prime) {
      std::uint64_t quotient = q_low / prime;
      if (q_low % prime != 0U) ++quotient;
      if (quotient <= q_high / prime) {
        composite = quotient * prime;
        if ((composite & 1U) == 0U) {
          if (composite <= q_high - prime) {
            composite += prime;
            ++quotient;
          } else {
            composite = q_high;
            quotient = q_high / prime;
          }
        }
        const std::uint64_t square = prime * prime;
        if (composite < square) {
          composite = square;
          quotient = prime;
        }
        if (composite <= q_high &&
            composite == quotient * prime &&
            (composite & 1U) != 0U) {
          cofactor = quotient;
          step = 2U * prime;
          active = true;
        }
      }
    }
  }

  while (__syncthreads_or(active)) {
    for (unsigned slot = threadIdx.x; slot < table_slots;
         slot += blockDim.x) {
      keys[slot] = kEmptyKey;
      masks[slot] = ~0ULL;
    }
    __syncthreads();

#pragma unroll
    for (unsigned event_index = 0; event_index < kEventsPerEpoch;
         ++event_index) {
      if (!active) continue;
      if (cofactor_survives_word_owner_wheel(cofactor)) {
        const std::uint64_t bit = (composite - q_low) / 2U;
        const std::uint64_t word = bit / 64U;
        const unsigned long long clear_mask =
            ~(1ULL << static_cast<unsigned>(bit & 63U));
        if constexpr (Instrument) {
          atomicAdd(&counters->eligible_event_count, 1ULL);
        }
        bool combined = false;
        const unsigned first_slot =
            table_hash(word, table_slots, force_hash_collision);
        for (unsigned probe = 0; probe < table_slots; ++probe) {
          const unsigned slot = (first_slot + probe) & (table_slots - 1U);
          const unsigned long long observed =
              atomicCAS(keys + slot, kEmptyKey, word);
          if (observed == kEmptyKey || observed == word) {
            atomicAnd(masks + slot, clear_mask);
            combined = true;
            if constexpr (Instrument) {
              atomicAdd(&counters->combined_event_count, 1ULL);
            }
            break;
          }
          if constexpr (Instrument) {
            atomicAdd(&counters->collision_probe_count, 1ULL);
          }
        }
        if (!combined) {
          atomicAnd(words + word, clear_mask);
          if constexpr (Instrument) {
            atomicAdd(&counters->fallback_event_count, 1ULL);
          }
        }
      }
      if (step > q_high - composite) {
        active = false;
      } else {
        composite += step;
        cofactor += 2U;
      }
    }
    __syncthreads();

    for (unsigned slot = threadIdx.x; slot < table_slots;
         slot += blockDim.x) {
      const unsigned long long key = keys[slot];
      if (key != kEmptyKey) {
        atomicAnd(words + key, masks[slot]);
        if constexpr (Instrument) {
          atomicAdd(&counters->flushed_entry_count, 1ULL);
        }
      }
    }
    __syncthreads();
  }
}

std::string canonical_word_sha256(
    const std::vector<std::uint64_t>& words) {
  sparkinterval::detail::Sha256 hasher;
  for (const std::uint64_t word : words) {
    unsigned char bytes[8];
    for (unsigned byte = 0; byte < 8U; ++byte) {
      bytes[byte] = static_cast<unsigned char>(word >> (8U * byte));
    }
    hasher.update(bytes, sizeof(bytes));
  }
  return sparkinterval::lowercase_hex(hasher.finish());
}

std::uint64_t set_bit_count(const std::vector<std::uint64_t>& words) {
  return std::accumulate(
      words.begin(), words.end(), std::uint64_t{0},
      [](std::uint64_t count, std::uint64_t word) {
        return count + std::popcount(word);
      });
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
    const std::size_t index =
        static_cast<std::size_t>(mismatch.first - expected.begin());
    throw std::runtime_error(
        std::string(what) + " differs at word " + std::to_string(index));
  }
}

HostCounters copy_counters(const DeviceCounters& value) {
  return {
      value.eligible_event_count,
      value.combined_event_count,
      value.fallback_event_count,
      value.flushed_entry_count,
      value.collision_probe_count,
  };
}

CaseResult run_case(std::string name, std::uint64_t q_low,
                    std::uint64_t odd_count,
                    const std::vector<std::uint64_t>& primes,
                    std::uint64_t* device_primes, unsigned table_slots,
                    bool force_collision, bool patterned) {
  if ((q_low & 1U) == 0U || odd_count == 0U ||
      2U * (odd_count - 1U) >
          std::numeric_limits<std::uint64_t>::max() - q_low) {
    throw std::runtime_error("invalid qualification case geometry");
  }
  if (!std::has_single_bit(table_slots) ||
      table_slots > kMaximumTableSlots) {
    throw std::runtime_error("invalid shared table slot count");
  }
  const std::uint64_t q_high = q_low + 2U * (odd_count - 1U);
  std::vector<std::uint64_t> expected =
      initial_words(odd_count, patterned);
  const std::vector<std::uint64_t> initial = expected;
  const std::uint64_t cpu_events =
      cpu_mark(q_low, q_high, primes, &expected);
  const std::size_t bytes = expected.size() * sizeof(std::uint64_t);

  unsigned long long* ordinary_device = nullptr;
  unsigned long long* candidate_device = nullptr;
  DeviceCounters* counters_device = nullptr;
  cuda_check(cudaMalloc(&ordinary_device, bytes),
             "cudaMalloc ordinary case words");
  cuda_check(cudaMalloc(&candidate_device, bytes),
             "cudaMalloc candidate case words");
  cuda_check(cudaMalloc(&counters_device, sizeof(DeviceCounters)),
             "cudaMalloc case counters");
  try {
    cuda_check(cudaMemcpy(ordinary_device, initial.data(), bytes,
                          cudaMemcpyHostToDevice),
               "copy ordinary initial words");
    cuda_check(cudaMemcpy(candidate_device, initial.data(), bytes,
                          cudaMemcpyHostToDevice),
               "copy candidate initial words");
    cuda_check(cudaMemset(counters_device, 0, sizeof(DeviceCounters)),
               "clear candidate counters");
    const unsigned blocks =
        static_cast<unsigned>((primes.size() + kThreads - 1U) / kThreads);
    ordinary_tail_kernel<<<blocks, kThreads>>>(
        q_low, q_high, device_primes, primes.size(), ordinary_device);
    cuda_check(cudaGetLastError(), "launch ordinary qualification tail");
    combined_tail_kernel<true><<<blocks, kThreads>>>(
        q_low, q_high, device_primes, primes.size(), candidate_device,
        table_slots, force_collision, counters_device);
    cuda_check(cudaGetLastError(), "launch combined qualification tail");
    cuda_check(cudaDeviceSynchronize(), "synchronize qualification case");

    std::vector<std::uint64_t> ordinary(expected.size());
    std::vector<std::uint64_t> candidate(expected.size());
    DeviceCounters device_counters{};
    cuda_check(cudaMemcpy(ordinary.data(), ordinary_device, bytes,
                          cudaMemcpyDeviceToHost),
               "copy ordinary qualification words");
    cuda_check(cudaMemcpy(candidate.data(), candidate_device, bytes,
                          cudaMemcpyDeviceToHost),
               "copy candidate qualification words");
    cuda_check(cudaMemcpy(&device_counters, counters_device,
                          sizeof(DeviceCounters), cudaMemcpyDeviceToHost),
               "copy qualification counters");
    const HostCounters counters = copy_counters(device_counters);
    compare_words(expected, ordinary, "ordinary CUDA qualification output");
    compare_words(expected, candidate, "combined CUDA qualification output");
    if (counters.eligible_event_count != cpu_events ||
        counters.combined_event_count + counters.fallback_event_count !=
            counters.eligible_event_count ||
        counters.combined_event_count < counters.flushed_entry_count) {
      throw std::runtime_error(
          "candidate event partition counters are inconsistent");
    }

    cuda_check(cudaFree(counters_device), "cudaFree case counters");
    counters_device = nullptr;
    cuda_check(cudaFree(candidate_device), "cudaFree candidate case words");
    candidate_device = nullptr;
    cuda_check(cudaFree(ordinary_device), "cudaFree ordinary case words");
    ordinary_device = nullptr;
    return {
        std::move(name),
        q_low,
        q_high,
        odd_count,
        table_slots,
        force_collision,
        patterned,
        cpu_events,
        counters,
        set_bit_count(expected),
        canonical_word_sha256(expected),
    };
  } catch (...) {
    if (counters_device != nullptr) cudaFree(counters_device);
    if (candidate_device != nullptr) cudaFree(candidate_device);
    if (ordinary_device != nullptr) cudaFree(ordinary_device);
    throw;
  }
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  const std::size_t middle = values.size() / 2U;
  if ((values.size() & 1U) != 0U) return values[middle];
  return (values[middle - 1U] + values[middle]) / 2.0;
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

BenchmarkResult run_benchmark(
    std::string geometry, std::uint64_t q_low, std::uint64_t odd_count,
    std::uint64_t prime_limit, const std::vector<std::uint64_t>& primes,
    std::uint64_t* device_primes, unsigned rounds) {
  if (rounds == 0U || (q_low & 1U) == 0U || odd_count == 0U ||
      2U * (odd_count - 1U) >
          std::numeric_limits<std::uint64_t>::max() - q_low) {
    throw std::runtime_error("invalid benchmark geometry");
  }
  const std::uint64_t q_high = q_low + 2U * (odd_count - 1U);
  std::vector<std::uint64_t> expected = initial_words(odd_count, false);
  const std::vector<std::uint64_t> initial = expected;
  const std::uint64_t cpu_events =
      cpu_mark(q_low, q_high, primes, &expected);
  const std::size_t bytes = expected.size() * sizeof(std::uint64_t);
  const unsigned blocks =
      static_cast<unsigned>((primes.size() + kThreads - 1U) / kThreads);

  unsigned long long* ordinary_device = nullptr;
  unsigned long long* candidate_device = nullptr;
  DeviceCounters* counters_device = nullptr;
  cuda_check(cudaMalloc(&ordinary_device, bytes),
             "cudaMalloc ordinary benchmark words");
  cuda_check(cudaMalloc(&candidate_device, bytes),
             "cudaMalloc candidate benchmark words");
  cuda_check(cudaMalloc(&counters_device, sizeof(DeviceCounters)),
             "cudaMalloc benchmark counters");
  try {
    auto reset_ordinary = [&]() {
      cuda_check(cudaMemcpy(ordinary_device, initial.data(), bytes,
                            cudaMemcpyHostToDevice),
                 "reset ordinary benchmark words");
    };
    auto reset_candidate = [&]() {
      cuda_check(cudaMemcpy(candidate_device, initial.data(), bytes,
                            cudaMemcpyHostToDevice),
                 "reset candidate benchmark words");
    };
    auto launch_ordinary = [&]() {
      ordinary_tail_kernel<<<blocks, kThreads>>>(
          q_low, q_high, device_primes, primes.size(), ordinary_device);
      cuda_check(cudaGetLastError(), "launch ordinary timed tail");
    };
    auto launch_candidate = [&]() {
      combined_tail_kernel<false><<<blocks, kThreads>>>(
          q_low, q_high, device_primes, primes.size(), candidate_device,
          kMaximumTableSlots, false, nullptr);
      cuda_check(cudaGetLastError(), "launch candidate timed tail");
    };

    reset_ordinary();
    timed_launch(launch_ordinary);
    reset_candidate();
    timed_launch(launch_candidate);

    std::vector<double> ordinary_times;
    std::vector<double> candidate_times;
    ordinary_times.reserve(rounds);
    candidate_times.reserve(rounds);
    for (unsigned round = 0; round < rounds; ++round) {
      if ((round & 1U) == 0U) {
        reset_ordinary();
        ordinary_times.push_back(timed_launch(launch_ordinary));
        reset_candidate();
        candidate_times.push_back(timed_launch(launch_candidate));
      } else {
        reset_candidate();
        candidate_times.push_back(timed_launch(launch_candidate));
        reset_ordinary();
        ordinary_times.push_back(timed_launch(launch_ordinary));
      }
    }

    reset_candidate();
    cuda_check(cudaMemset(counters_device, 0, sizeof(DeviceCounters)),
               "clear benchmark counters");
    combined_tail_kernel<true><<<blocks, kThreads>>>(
        q_low, q_high, device_primes, primes.size(), candidate_device,
        kMaximumTableSlots, false, counters_device);
    cuda_check(cudaGetLastError(), "launch instrumented candidate tail");
    cuda_check(cudaDeviceSynchronize(),
               "synchronize instrumented candidate tail");

    std::vector<std::uint64_t> ordinary(expected.size());
    std::vector<std::uint64_t> candidate(expected.size());
    DeviceCounters device_counters{};
    cuda_check(cudaMemcpy(ordinary.data(), ordinary_device, bytes,
                          cudaMemcpyDeviceToHost),
               "copy ordinary benchmark words");
    cuda_check(cudaMemcpy(candidate.data(), candidate_device, bytes,
                          cudaMemcpyDeviceToHost),
               "copy candidate benchmark words");
    cuda_check(cudaMemcpy(&device_counters, counters_device,
                          sizeof(DeviceCounters), cudaMemcpyDeviceToHost),
               "copy benchmark counters");
    compare_words(expected, ordinary, "ordinary CUDA benchmark output");
    compare_words(expected, candidate, "combined CUDA benchmark output");
    const HostCounters routing_counters = copy_counters(device_counters);
    if (routing_counters.eligible_event_count != cpu_events ||
        routing_counters.combined_event_count +
                routing_counters.fallback_event_count !=
            routing_counters.eligible_event_count ||
        routing_counters.combined_event_count <
            routing_counters.flushed_entry_count) {
      throw std::runtime_error(
          "benchmark event partition counters are inconsistent");
    }
    const double ordinary_median = median(ordinary_times);
    const double candidate_median = median(candidate_times);

    cuda_check(cudaFree(counters_device), "cudaFree benchmark counters");
    counters_device = nullptr;
    cuda_check(cudaFree(candidate_device),
               "cudaFree candidate benchmark words");
    candidate_device = nullptr;
    cuda_check(cudaFree(ordinary_device), "cudaFree ordinary benchmark words");
    ordinary_device = nullptr;
    return {
        std::move(geometry),
        q_low,
        q_high,
        odd_count,
        prime_limit,
        primes.size(),
        cpu_events,
        routing_counters,
        rounds,
        std::move(ordinary_times),
        std::move(candidate_times),
        ordinary_median,
        candidate_median,
        ordinary_median / candidate_median,
        canonical_word_sha256(expected),
    };
  } catch (...) {
    if (counters_device != nullptr) cudaFree(counters_device);
    if (candidate_device != nullptr) cudaFree(candidate_device);
    if (ordinary_device != nullptr) cudaFree(ordinary_device);
    throw;
  }
}

void print_counter_fields(const HostCounters& counters) {
  std::cout << "\"collision_probe_count\":"
            << counters.collision_probe_count
            << ",\"combined_event_count\":"
            << counters.combined_event_count
            << ",\"eligible_event_count\":"
            << counters.eligible_event_count
            << ",\"fallback_event_count\":"
            << counters.fallback_event_count
            << ",\"flushed_entry_count\":"
            << counters.flushed_entry_count;
}

void print_case(const CaseResult& result) {
  std::cout << "{\"counters\":{";
  print_counter_fields(result.counters);
  std::cout << "}"
            << ",\"cpu_event_count\":" << result.cpu_event_count
            << ",\"force_hash_collision\":"
            << (result.force_hash_collision ? "true" : "false")
            << ",\"name\":\"" << result.name << "\""
            << ",\"odd_count\":" << result.odd_count
            << ",\"output_sha256\":\"" << result.output_sha256 << "\""
            << ",\"patterned_initial_words\":"
            << (result.patterned_initial_words ? "true" : "false")
            << ",\"q_high\":\"" << result.q_high << "\""
            << ",\"q_low\":\"" << result.q_low << "\""
            << ",\"set_bits\":" << result.set_bits
            << ",\"table_slots\":" << result.table_slots << "}";
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
  std::cout << "{\"candidate_ms\":";
  print_double_array(result.candidate_ms);
  std::cout << ",\"candidate_median_ms\":" << std::fixed
            << std::setprecision(6) << result.candidate_median_ms
            << ",\"geometry\":\"" << result.geometry << "\""
            << ",\"observed_ordinary_over_candidate_rate_ratio\":"
            << std::fixed << std::setprecision(9)
            << result.observed_rate_ratio
            << ",\"odd_count\":" << result.odd_count
            << ",\"ordinary_ms\":";
  print_double_array(result.ordinary_ms);
  std::cout << ",\"ordinary_median_ms\":" << std::fixed
            << std::setprecision(6) << result.ordinary_median_ms
            << ",\"output_sha256\":\"" << result.output_sha256 << "\""
            << ",\"prime_limit\":" << result.prime_limit
            << ",\"q_high\":\"" << result.q_high << "\""
            << ",\"q_low\":\"" << result.q_low << "\""
            << ",\"rounds\":" << result.rounds
            << ",\"routing_counters\":{";
  print_counter_fields(result.routing_counters);
  const std::uint64_t emitted_global_atomics =
      result.routing_counters.flushed_entry_count +
      result.routing_counters.fallback_event_count;
  const std::uint64_t eliminated_global_atomics =
      result.routing_counters.eligible_event_count - emitted_global_atomics;
  std::cout << "}"
            << ",\"cpu_event_count\":" << result.cpu_event_count
            << ",\"emitted_global_atomic_count\":"
            << emitted_global_atomics
            << ",\"eliminated_global_atomic_count\":"
            << eliminated_global_atomics
            << ",\"tail_prime_count\":" << result.tail_prime_count << "}";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    bool source_segment = false;
    if (argc == 2 && std::string_view(argv[1]) == "--source-segment") {
      source_segment = true;
    } else if (argc != 1) {
      throw std::runtime_error("usage: qualifier [--source-segment]");
    }

    int device_count = 0;
    cuda_check(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount");
    if (device_count < 1) throw std::runtime_error("no CUDA device");
    cudaDeviceProp properties{};
    cuda_check(cudaGetDeviceProperties(&properties, 0),
               "cudaGetDeviceProperties");

    const std::uint64_t benchmark_q_low =
        source_segment ? kSourceQLow : 31'249'998'799'000'003ULL;
    const std::uint64_t benchmark_odd_count =
        source_segment ? kSourceOddCount : kPerformanceOddCount;
    const std::uint64_t benchmark_q_high =
        benchmark_q_low + 2U * (benchmark_odd_count - 1U);
    const std::uint64_t benchmark_prime_limit =
        source_segment ? integer_sqrt(benchmark_q_high)
                       : kPerformancePrimeLimit;
    const unsigned benchmark_rounds =
        source_segment ? kSourceRounds : kBoundedRounds;
    const std::vector<std::uint64_t> benchmark_primes =
        tail_primes_through(benchmark_prime_limit);
    if (benchmark_primes.empty()) {
      throw std::runtime_error("benchmark tail-prime roster is empty");
    }

    std::uint64_t* benchmark_device_primes = nullptr;
    cuda_check(cudaMalloc(
                   &benchmark_device_primes,
                   benchmark_primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc benchmark primes");
    cuda_check(cudaMemcpy(
                   benchmark_device_primes, benchmark_primes.data(),
                   benchmark_primes.size() * sizeof(std::uint64_t),
                   cudaMemcpyHostToDevice),
               "copy benchmark primes");
    BenchmarkResult benchmark;
    try {
      benchmark = run_benchmark(
          source_segment ? "one-historical-terminal-segment"
                         : "bounded-source-height-tail-subset",
          benchmark_q_low, benchmark_odd_count, benchmark_prime_limit,
          benchmark_primes, benchmark_device_primes, benchmark_rounds);
      cuda_check(cudaFree(benchmark_device_primes),
                 "cudaFree benchmark primes");
      benchmark_device_primes = nullptr;
    } catch (...) {
      if (benchmark_device_primes != nullptr) {
        cudaFree(benchmark_device_primes);
      }
      throw;
    }

    const std::vector<std::uint64_t> bounded_primes =
        tail_primes_through(kBoundedPrimeLimit);
    if (bounded_primes.empty()) {
      throw std::runtime_error("bounded tail-prime roster is empty");
    }
    std::uint64_t* bounded_device_primes = nullptr;
    cuda_check(cudaMalloc(
                   &bounded_device_primes,
                   bounded_primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc bounded primes");
    cuda_check(cudaMemcpy(
                   bounded_device_primes, bounded_primes.data(),
                   bounded_primes.size() * sizeof(std::uint64_t),
                   cudaMemcpyHostToDevice),
               "copy bounded primes");
    std::vector<CaseResult> cases;
    try {
      const std::uint64_t square = 32'771ULL * 32'771ULL;
      cases.push_back(run_case(
          "prime-square-activation", square - 2U * (kBoundedOddCount / 2U),
          kBoundedOddCount, bounded_primes, bounded_device_primes,
          kMaximumTableSlots, false, false));
      cases.push_back(run_case(
          "source-height-normal", 31'249'998'799'000'003ULL,
          kBoundedOddCount, bounded_primes, bounded_device_primes,
          kMaximumTableSlots, false, false));
      cases.push_back(run_case(
          "forced-collision", 31'249'998'799'000'003ULL,
          kBoundedOddCount, bounded_primes, bounded_device_primes,
          kMaximumTableSlots, true, true));
      cases.push_back(run_case(
          "forced-full-table-fallback", 31'249'998'799'000'003ULL,
          kBoundedOddCount, bounded_primes, bounded_device_primes, 8U, true,
          true));
      const std::uint64_t near_max =
          std::numeric_limits<std::uint64_t>::max() -
          2U * (kBoundedOddCount - 1U);
      cases.push_back(run_case(
          "uint64-overflow-edge", near_max, kBoundedOddCount,
          bounded_primes, bounded_device_primes, kMaximumTableSlots, false,
          false));
      cuda_check(cudaFree(bounded_device_primes),
                 "cudaFree bounded primes");
      bounded_device_primes = nullptr;
    } catch (...) {
      if (bounded_device_primes != nullptr) cudaFree(bounded_device_primes);
      throw;
    }

    const CaseResult& collision_case = cases[2];
    const CaseResult& full_case = cases[3];
    if (collision_case.counters.collision_probe_count == 0U ||
        collision_case.counters.fallback_event_count != 0U ||
        full_case.counters.collision_probe_count == 0U ||
        full_case.counters.combined_event_count == 0U ||
        full_case.counters.fallback_event_count == 0U) {
      throw std::runtime_error(
          "forced collision/full-table admission paths were not exercised");
    }

    cudaFuncAttributes ordinary_attributes{};
    cudaFuncAttributes candidate_attributes{};
    cuda_check(
        cudaFuncGetAttributes(&ordinary_attributes, ordinary_tail_kernel),
        "cudaFuncGetAttributes ordinary");
    cuda_check(cudaFuncGetAttributes(
                   &candidate_attributes, combined_tail_kernel<false>),
               "cudaFuncGetAttributes candidate");
    const bool resource_gate =
        candidate_attributes.maxThreadsPerBlock >=
            static_cast<int>(kThreads) &&
        candidate_attributes.sharedSizeBytes ==
            2U * kMaximumTableSlots * sizeof(unsigned long long) &&
        candidate_attributes.localSizeBytes == 0U &&
        candidate_attributes.numRegs > 0 &&
        candidate_attributes.numRegs <= 255;
    if (!resource_gate) {
      throw std::runtime_error("candidate compiler-resource gate failed");
    }

    std::cout
        << "{\"accepted\":true"
        << ",\"benchmark\":";
    print_benchmark(benchmark);
    std::cout
        << ",\"bounded_case_count\":" << cases.size()
        << ",\"bounded_cases\":[";
    for (std::size_t index = 0; index < cases.size(); ++index) {
      if (index != 0U) std::cout << ",";
      print_case(cases[index]);
    }
    std::cout
        << "]"
        << ",\"bounded_prime_limit\":" << kBoundedPrimeLimit
        << ",\"bounded_tail_prime_count\":" << bounded_primes.size()
        << ",\"candidate_resources\":{"
        << "\"local_bytes_per_thread\":"
        << candidate_attributes.localSizeBytes
        << ",\"max_threads_per_block\":"
        << candidate_attributes.maxThreadsPerBlock
        << ",\"registers_per_thread\":" << candidate_attributes.numRegs
        << ",\"static_shared_bytes\":"
        << candidate_attributes.sharedSizeBytes << "}"
        << ",\"compute_capability\":\"" << properties.major << "."
        << properties.minor << "\""
        << ",\"events_per_epoch\":" << kEventsPerEpoch
        << ",\"kind\":\"sparkinterval.goldbach-tail-combiner-qualification.v1\""
        << ",\"lean_bridge_complete\":false"
        << ",\"maximum_table_slots\":" << kMaximumTableSlots
        << ",\"ordinary_resources\":{"
        << "\"local_bytes_per_thread\":"
        << ordinary_attributes.localSizeBytes
        << ",\"max_threads_per_block\":"
        << ordinary_attributes.maxThreadsPerBlock
        << ",\"registers_per_thread\":" << ordinary_attributes.numRegs
        << ",\"static_shared_bytes\":"
        << ordinary_attributes.sharedSizeBytes << "}"
        << ",\"performance_evidence_eligible\":false"
        << ",\"production_identity_promoted\":false"
        << ",\"production_ready\":false"
        << ",\"release_build_profile_eligible\":true"
        << ",\"resource_gate_passed\":true"
        << ",\"runtime_instrumentation_status\":"
           "\"not-inspected-by-runner\""
        << ",\"source_segment_mode\":"
        << (source_segment ? "true" : "false")
        << ",\"threads_per_block\":" << kThreads
        << ",\"word_owner_cutoff\":" << kWordOwnerCutoff
        << ",\"warp_parallel_cutoff\":" << kWarpParallelCutoff
        << "}\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 2;
  }
  return 0;
}

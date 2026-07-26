// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded bit-for-bit KAT for the GoldbachGPU warp-per-prime sieve tier.
//
// This executable compares three implementations on four odd windows:
//
//   1. an independent CPU arithmetic-progression replay;
//   2. the reviewed one-thread-per-prime global-atomic CUDA kernel; and
//   3. the candidate word-owner/warp/tail partition above the word prefix.
//
// It deliberately tests a p^2 boundary, the production-scale magnitude, and
// a window ending at UINT64_MAX.  Passing is regression evidence, not a proof
// that CUDA or a compiled binary refines the Lean arithmetic model.

#include <cuda_runtime.h>

#include <algorithm>
#include <bit>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr unsigned kThreads = 256;
constexpr std::uint64_t kWordOwnerCutoff = 2039;
constexpr std::uint64_t kWarpParallelCutoff = 32749;
constexpr std::uint64_t kPrimeLimit = 131071;
constexpr std::uint64_t kOddCount = 1ULL << 18U;

void cuda_check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

std::vector<std::uint64_t> odd_primes_through(std::uint64_t limit) {
  std::vector<unsigned char> composite(limit + 1U, 0U);
  for (std::uint64_t prime = 2; prime <= limit / prime; ++prime) {
    if (composite[prime] != 0U) continue;
    for (std::uint64_t value = prime * prime; value <= limit;
         value += prime) {
      composite[value] = 1U;
    }
  }
  std::vector<std::uint64_t> primes;
  for (std::uint64_t value = 3; value <= limit; value += 2U) {
    if (composite[value] == 0U && value > kWordOwnerCutoff) {
      primes.push_back(value);
    }
  }
  return primes;
}

bool first_odd_multiple(std::uint64_t q_low, std::uint64_t q_high,
                        std::uint64_t prime, std::uint64_t& first) {
  if (prime < 3U || prime > q_high / prime) return false;
  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return false;
  first = quotient * prime;
  if ((first & 1U) == 0U) {
    if (first > q_high - prime) return false;
    first += prime;
  }
  const std::uint64_t square = prime * prime;
  if (first < square) first = square;
  return first <= q_high;
}

void cpu_mark(std::uint64_t q_low, std::uint64_t q_high,
              const std::vector<std::uint64_t>& primes,
              std::vector<std::uint64_t>& words) {
  for (const std::uint64_t prime : primes) {
    std::uint64_t first = 0;
    if (!first_odd_multiple(q_low, q_high, prime, first)) continue;
    const std::uint64_t step = 2U * prime;
    for (std::uint64_t composite = first;;) {
      const std::uint64_t bit = (composite - q_low) / 2U;
      words[bit / 64U] &= ~(1ULL << static_cast<unsigned>(bit & 63U));
      if (step > q_high - composite) break;
      composite += step;
    }
  }
}

__global__ void mark_one_thread_per_prime(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes, std::uint64_t prime_count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= prime_count) return;
  const std::uint64_t prime = primes[index];
  if (prime < 3U || prime > q_high / prime) return;

  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t first = quotient * prime;
  if ((first & 1U) == 0U) {
    if (first > q_high - prime) return;
    first += prime;
  }
  const std::uint64_t square = prime * prime;
  if (first < square) first = square;
  if (first > q_high) return;

  const std::uint64_t step = 2U * prime;
  for (std::uint64_t composite = first;;) {
    const std::uint64_t bit = (composite - q_low) / 2U;
    atomicAnd(words + bit / 64U,
              ~(1ULL << static_cast<unsigned>(bit & 63U)));
    if (step > q_high - composite) break;
    composite += step;
  }
}

__global__ void mark_one_warp_per_prime(
    std::uint64_t q_low, std::uint64_t q_high,
    const std::uint64_t* __restrict__ primes, std::uint64_t prime_count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t global_thread =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  const std::uint64_t warp_index = global_thread / 32U;
  const unsigned lane = threadIdx.x & 31U;
  if (warp_index >= prime_count) return;
  const std::uint64_t prime = primes[warp_index];
  if (prime < 3U || prime > q_high / prime) return;

  std::uint64_t quotient = q_low / prime;
  if (q_low % prime != 0U) ++quotient;
  if (quotient > q_high / prime) return;
  std::uint64_t first = quotient * prime;
  if ((first & 1U) == 0U) {
    if (first > q_high - prime) return;
    first += prime;
  }
  const std::uint64_t square = prime * prime;
  if (first < square) first = square;
  if (first > q_high) return;

  const std::uint64_t step = 2U * prime;
  const std::uint64_t lane_offset = step * lane;
  if (lane_offset > q_high - first) return;
  const std::uint64_t warp_step = step * 32U;
  for (std::uint64_t composite = first + lane_offset;;) {
    const std::uint64_t bit = (composite - q_low) / 2U;
    atomicAnd(words + bit / 64U,
              ~(1ULL << static_cast<unsigned>(bit & 63U)));
    if (warp_step > q_high - composite) break;
    composite += warp_step;
  }
}

std::uint64_t fnv1a_words(const std::vector<std::uint64_t>& words) {
  std::uint64_t hash = 1469598103934665603ULL;
  for (const std::uint64_t word : words) {
    for (unsigned shift = 0; shift < 64U; shift += 8U) {
      hash ^= (word >> shift) & 0xffU;
      hash *= 1099511628211ULL;
    }
  }
  return hash;
}

std::string hex_u64(std::uint64_t value) {
  std::ostringstream stream;
  stream << std::hex << std::setfill('0') << std::setw(16) << value;
  return stream.str();
}

struct WindowResult {
  std::uint64_t q_low;
  std::uint64_t q_high;
  std::uint64_t set_bits;
  std::uint64_t fnv1a;
};

WindowResult run_window(std::uint64_t q_low,
                        const std::vector<std::uint64_t>& primes,
                        std::uint64_t warp_prime_count,
                        std::uint64_t* device_primes) {
  if ((q_low & 1U) == 0U ||
      2U * (kOddCount - 1U) >
          std::numeric_limits<std::uint64_t>::max() - q_low) {
    throw std::runtime_error("invalid KAT odd window");
  }
  const std::uint64_t q_high = q_low + 2U * (kOddCount - 1U);
  const std::uint64_t word_count = (kOddCount + 63U) / 64U;
  const std::size_t bytes = word_count * sizeof(std::uint64_t);

  unsigned long long* baseline_device = nullptr;
  unsigned long long* tiered_device = nullptr;
  cuda_check(cudaMalloc(&baseline_device, bytes), "cudaMalloc baseline");
  cuda_check(cudaMalloc(&tiered_device, bytes), "cudaMalloc tiered");
  try {
    cuda_check(cudaMemset(baseline_device, 0xff, bytes),
               "cudaMemset baseline");
    cuda_check(cudaMemset(tiered_device, 0xff, bytes), "cudaMemset tiered");

    const unsigned baseline_blocks = static_cast<unsigned>(
        (primes.size() + kThreads - 1U) / kThreads);
    mark_one_thread_per_prime<<<baseline_blocks, kThreads>>>(
        q_low, q_high, device_primes, primes.size(), baseline_device);
    cuda_check(cudaGetLastError(), "launch baseline");

    const std::uint64_t warp_threads = 32U * warp_prime_count;
    const unsigned warp_blocks = static_cast<unsigned>(
        (warp_threads + kThreads - 1U) / kThreads);
    if (warp_prime_count != 0U) {
      mark_one_warp_per_prime<<<warp_blocks, kThreads>>>(
          q_low, q_high, device_primes, warp_prime_count, tiered_device);
      cuda_check(cudaGetLastError(), "launch warp tier");
    }
    const std::uint64_t tail_count = primes.size() - warp_prime_count;
    const unsigned tail_blocks = static_cast<unsigned>(
        (tail_count + kThreads - 1U) / kThreads);
    if (tail_count != 0U) {
      mark_one_thread_per_prime<<<tail_blocks, kThreads>>>(
          q_low, q_high, device_primes + warp_prime_count, tail_count,
          tiered_device);
      cuda_check(cudaGetLastError(), "launch atomic tail");
    }
    cuda_check(cudaDeviceSynchronize(), "synchronize KAT");

    std::vector<std::uint64_t> baseline(word_count);
    std::vector<std::uint64_t> tiered(word_count);
    std::vector<std::uint64_t> expected(word_count,
                                        std::numeric_limits<std::uint64_t>::max());
    cuda_check(cudaMemcpy(baseline.data(), baseline_device, bytes,
                          cudaMemcpyDeviceToHost),
               "copy baseline");
    cuda_check(cudaMemcpy(tiered.data(), tiered_device, bytes,
                          cudaMemcpyDeviceToHost),
               "copy tiered");
    cpu_mark(q_low, q_high, primes, expected);
    if (baseline != expected) {
      throw std::runtime_error("baseline CUDA sieve differs from CPU replay");
    }
    if (tiered != expected) {
      throw std::runtime_error("warp/tail CUDA sieve differs from CPU replay");
    }
    std::uint64_t set_bits = 0;
    for (const std::uint64_t word : expected) {
      set_bits += std::popcount(word);
    }
    cuda_check(cudaFree(tiered_device), "cudaFree tiered");
    tiered_device = nullptr;
    cuda_check(cudaFree(baseline_device), "cudaFree baseline");
    baseline_device = nullptr;
    return {q_low, q_high, set_bits, fnv1a_words(expected)};
  } catch (...) {
    if (tiered_device != nullptr) cudaFree(tiered_device);
    if (baseline_device != nullptr) cudaFree(baseline_device);
    throw;
  }
}

}  // namespace

int main() {
  try {
    int device_count = 0;
    cuda_check(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount");
    if (device_count < 1) throw std::runtime_error("no CUDA device");
    cudaDeviceProp properties{};
    cuda_check(cudaGetDeviceProperties(&properties, 0),
               "cudaGetDeviceProperties");

    const std::vector<std::uint64_t> primes =
        odd_primes_through(kPrimeLimit);
    const std::uint64_t warp_prime_count = std::upper_bound(
        primes.begin(), primes.end(), kWarpParallelCutoff) - primes.begin();
    if (primes.empty() || warp_prime_count == 0U ||
        warp_prime_count == primes.size()) {
      throw std::runtime_error("KAT prime partition is not three-tier");
    }
    std::uint64_t* device_primes = nullptr;
    cuda_check(cudaMalloc(&device_primes,
                          primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc primes");
    try {
      cuda_check(cudaMemcpy(device_primes, primes.data(),
                            primes.size() * sizeof(std::uint64_t),
                            cudaMemcpyHostToDevice),
                 "copy primes");

      const std::uint64_t near_max =
          std::numeric_limits<std::uint64_t>::max() -
          2U * (kOddCount - 1U);
      const std::vector<std::uint64_t> starts = {
          4'000'001ULL,
          4'156'001ULL,
          31'249'998'799'000'003ULL,
          near_max,
      };
      std::vector<WindowResult> results;
      for (const std::uint64_t start : starts) {
        results.push_back(
            run_window(start, primes, warp_prime_count, device_primes));
      }
      cuda_check(cudaFree(device_primes), "cudaFree primes");
      device_primes = nullptr;

      std::cout << "{\"accepted\":true"
                << ",\"compute_capability\":\"" << properties.major << "."
                << properties.minor << "\""
                << ",\"kind\":\"sparkinterval.goldbach-warp-tail-kat.v1\""
                << ",\"odd_count_per_window\":" << kOddCount
                << ",\"prime_limit\":" << kPrimeLimit
                << ",\"tail_prime_count\":" << primes.size()
                << ",\"warp_parallel_cutoff\":" << kWarpParallelCutoff
                << ",\"warp_prime_count\":" << warp_prime_count
                << ",\"window_count\":" << results.size()
                << ",\"windows\":[";
      for (std::size_t index = 0; index < results.size(); ++index) {
        if (index != 0U) std::cout << ",";
        const WindowResult& row = results[index];
        std::cout << "{\"fnv1a64\":\"" << hex_u64(row.fnv1a) << "\""
                  << ",\"q_high\":\"" << row.q_high << "\""
                  << ",\"q_low\":\"" << row.q_low << "\""
                  << ",\"set_bits\":" << row.set_bits << "}";
      }
      std::cout << "]"
                << ",\"word_owner_cutoff\":" << kWordOwnerCutoff
                << "}\n";
    } catch (...) {
      if (device_primes != nullptr) cudaFree(device_primes);
      throw;
    }
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 2;
  }
  return 0;
}

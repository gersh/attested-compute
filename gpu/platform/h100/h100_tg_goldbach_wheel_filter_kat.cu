// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded differential KAT for the 15015 cofactor filter.  It compares an
// independent CPU progression replay, the unfiltered CUDA sieve, and the
// wheel-filtered CUDA warp/tail partition word for word.

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

constexpr unsigned kThreads = 256U;
constexpr std::uint64_t kWordOwnerCutoff = 2039U;
constexpr std::uint64_t kWarpCutoff = 32749U;
constexpr std::uint64_t kPrimeLimit = 131071U;
constexpr std::uint64_t kOddCount = 1ULL << 18U;
constexpr std::uint64_t kWheel = 15015U;
constexpr std::uint64_t kCofactorFilterLimit = 47U;

void cuda_check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

std::vector<std::uint64_t> primes() {
  std::vector<unsigned char> composite(kPrimeLimit + 1U, 0U);
  for (std::uint64_t p = 2U; p <= kPrimeLimit / p; ++p) {
    if (composite[p] != 0U) continue;
    for (std::uint64_t n = p * p; n <= kPrimeLimit; n += p) {
      composite[n] = 1U;
    }
  }
  std::vector<std::uint64_t> result;
  for (std::uint64_t p = kWordOwnerCutoff + 2U; p <= kPrimeLimit;
       p += 2U) {
    if (composite[p] == 0U) result.push_back(p);
  }
  return result;
}

bool first_odd(std::uint64_t low, std::uint64_t high, std::uint64_t p,
               std::uint64_t& first, std::uint64_t& cofactor) {
  if (p < 3U || p > high / p) return false;
  std::uint64_t quotient = low / p;
  if (low % p != 0U) ++quotient;
  if (quotient > high / p) return false;
  first = quotient * p;
  if ((first & 1U) == 0U) {
    if (p > high - first) return false;
    first += p;
    ++quotient;
  }
  const std::uint64_t square = p * p;
  if (first < square) {
    first = square;
    quotient = p;
  }
  if (first > high) return false;
  cofactor = quotient;
  return true;
}

void cpu_mark(std::uint64_t low, std::uint64_t high,
              const std::vector<std::uint64_t>& base,
              std::vector<std::uint64_t>& words) {
  for (const std::uint64_t p : base) {
    std::uint64_t first = 0U;
    std::uint64_t unused = 0U;
    if (!first_odd(low, high, p, first, unused)) continue;
    const std::uint64_t step = 2U * p;
    for (std::uint64_t n = first;;) {
      const std::uint64_t bit = (n - low) / 2U;
      words[bit / 64U] &= ~(1ULL << static_cast<unsigned>(bit % 64U));
      if (step > high - n) break;
      n += step;
    }
  }
}

__device__ __forceinline__ bool survives(std::uint64_t cofactor) {
  const std::uint32_t r =
      static_cast<std::uint32_t>(cofactor % kWheel);
  return r % 3U != 0U && r % 5U != 0U && r % 7U != 0U &&
         r % 11U != 0U && r % 13U != 0U &&
         cofactor % 17U != 0U && cofactor % 19U != 0U &&
         cofactor % 23U != 0U && cofactor % 29U != 0U &&
         cofactor % 31U != 0U && cofactor % 37U != 0U &&
         cofactor % 41U != 0U && cofactor % 43U != 0U &&
         cofactor % 47U != 0U;
}

__device__ __forceinline__ bool device_first(
    std::uint64_t low, std::uint64_t high, std::uint64_t p,
    std::uint64_t& first, std::uint64_t& cofactor) {
  if (p < 3U || p > high / p) return false;
  std::uint64_t quotient = low / p;
  if (low % p != 0U) ++quotient;
  if (quotient > high / p) return false;
  first = quotient * p;
  if ((first & 1U) == 0U) {
    if (p > high - first) return false;
    first += p;
    ++quotient;
  }
  const std::uint64_t square = p * p;
  if (first < square) {
    first = square;
    quotient = p;
  }
  if (first > high) return false;
  cofactor = quotient;
  return true;
}

__global__ void baseline_kernel(
    std::uint64_t low, std::uint64_t high,
    const std::uint64_t* __restrict__ base, std::uint64_t count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t p = base[index];
  std::uint64_t first = 0U;
  std::uint64_t cofactor = 0U;
  if (!device_first(low, high, p, first, cofactor)) return;
  const std::uint64_t step = 2U * p;
  for (std::uint64_t n = first;;) {
    const std::uint64_t bit = (n - low) / 2U;
    atomicAnd(words + bit / 64U,
              ~(1ULL << static_cast<unsigned>(bit % 64U)));
    if (step > high - n) break;
    n += step;
  }
}

__global__ void wheel_tail_kernel(
    std::uint64_t low, std::uint64_t high,
    const std::uint64_t* __restrict__ base, std::uint64_t count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t p = base[index];
  std::uint64_t first = 0U;
  std::uint64_t cofactor = 0U;
  if (!device_first(low, high, p, first, cofactor)) return;
  const std::uint64_t step = 2U * p;
  for (std::uint64_t n = first;;) {
    if (survives(cofactor)) {
      const std::uint64_t bit = (n - low) / 2U;
      atomicAnd(words + bit / 64U,
                ~(1ULL << static_cast<unsigned>(bit % 64U)));
    }
    if (step > high - n) break;
    n += step;
    cofactor += 2U;
  }
}

__global__ void wheel_warp_kernel(
    std::uint64_t low, std::uint64_t high,
    const std::uint64_t* __restrict__ base, std::uint64_t count,
    unsigned long long* __restrict__ words) {
  const std::uint64_t thread =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  const std::uint64_t index = thread / 32U;
  const unsigned lane = threadIdx.x & 31U;
  if (index >= count) return;
  const std::uint64_t p = base[index];
  std::uint64_t first = 0U;
  std::uint64_t cofactor = 0U;
  if (!device_first(low, high, p, first, cofactor)) return;
  const std::uint64_t step = 2U * p;
  const std::uint64_t lane_offset = step * lane;
  if (lane_offset > high - first) return;
  std::uint64_t lane_cofactor = cofactor + 2U * lane;
  const std::uint64_t warp_step = step * 32U;
  for (std::uint64_t n = first + lane_offset;;) {
    if (survives(lane_cofactor)) {
      const std::uint64_t bit = (n - low) / 2U;
      atomicAnd(words + bit / 64U,
                ~(1ULL << static_cast<unsigned>(bit % 64U)));
    }
    if (warp_step > high - n) break;
    n += warp_step;
    lane_cofactor += 64U;
  }
}

std::uint64_t fnv1a(const std::vector<std::uint64_t>& words) {
  std::uint64_t result = 1469598103934665603ULL;
  for (const std::uint64_t word : words) {
    for (unsigned shift = 0U; shift < 64U; shift += 8U) {
      result ^= (word >> shift) & 0xffU;
      result *= 1099511628211ULL;
    }
  }
  return result;
}

std::string hexadecimal(std::uint64_t value) {
  std::ostringstream stream;
  stream << std::hex << std::setfill('0') << std::setw(16) << value;
  return stream.str();
}

struct Result {
  std::uint64_t low;
  std::uint64_t high;
  std::uint64_t set_bits;
  std::uint64_t digest;
};

Result run_window(std::uint64_t low, const std::vector<std::uint64_t>& base,
                  const std::vector<std::uint64_t>& wheel_primes,
                  std::uint64_t warp_count, std::uint64_t* device_base,
                  std::uint64_t* device_wheel_primes) {
  if ((low & 1U) == 0U ||
      2U * (kOddCount - 1U) >
          std::numeric_limits<std::uint64_t>::max() - low) {
    throw std::runtime_error("invalid odd KAT window");
  }
  const std::uint64_t high = low + 2U * (kOddCount - 1U);
  const std::size_t bytes = (kOddCount / 8U);
  unsigned long long* baseline = nullptr;
  unsigned long long* wheel = nullptr;
  cuda_check(cudaMalloc(&baseline, bytes), "cudaMalloc baseline");
  cuda_check(cudaMalloc(&wheel, bytes), "cudaMalloc wheel");
  try {
    cuda_check(cudaMemset(baseline, 0xff, bytes), "initialize baseline");
    cuda_check(cudaMemset(wheel, 0xff, bytes), "initialize wheel");
    const unsigned wheel_blocks = static_cast<unsigned>(
        (wheel_primes.size() + kThreads - 1U) / kThreads);
    // Model the relevant portion of the production word-owner initializer.
    // These clears are the exact premise used to omit filtered tail writes.
    baseline_kernel<<<wheel_blocks, kThreads>>>(
        low, high, device_wheel_primes, wheel_primes.size(), baseline);
    baseline_kernel<<<wheel_blocks, kThreads>>>(
        low, high, device_wheel_primes, wheel_primes.size(), wheel);
    cuda_check(cudaGetLastError(), "launch wheel-prime initializer");
    const unsigned blocks =
        static_cast<unsigned>((base.size() + kThreads - 1U) / kThreads);
    baseline_kernel<<<blocks, kThreads>>>(
        low, high, device_base, base.size(), baseline);
    cuda_check(cudaGetLastError(), "launch baseline");
    const unsigned warp_blocks = static_cast<unsigned>(
        (32U * warp_count + kThreads - 1U) / kThreads);
    wheel_warp_kernel<<<warp_blocks, kThreads>>>(
        low, high, device_base, warp_count, wheel);
    cuda_check(cudaGetLastError(), "launch wheel warp");
    const std::uint64_t tail_count = base.size() - warp_count;
    const unsigned tail_blocks = static_cast<unsigned>(
        (tail_count + kThreads - 1U) / kThreads);
    wheel_tail_kernel<<<tail_blocks, kThreads>>>(
        low, high, device_base + warp_count, tail_count, wheel);
    cuda_check(cudaGetLastError(), "launch wheel tail");
    cuda_check(cudaDeviceSynchronize(), "synchronize");

    const std::size_t word_count = kOddCount / 64U;
    std::vector<std::uint64_t> got_baseline(word_count);
    std::vector<std::uint64_t> got_wheel(word_count);
    std::vector<std::uint64_t> expected(
        word_count, std::numeric_limits<std::uint64_t>::max());
    cuda_check(cudaMemcpy(got_baseline.data(), baseline, bytes,
                          cudaMemcpyDeviceToHost),
               "copy baseline");
    cuda_check(cudaMemcpy(got_wheel.data(), wheel, bytes,
                          cudaMemcpyDeviceToHost),
               "copy wheel");
    cpu_mark(low, high, wheel_primes, expected);
    cpu_mark(low, high, base, expected);
    if (got_baseline != expected) {
      throw std::runtime_error("baseline CUDA differs from CPU replay");
    }
    if (got_wheel != expected) {
      throw std::runtime_error("wheel CUDA differs from CPU replay");
    }
    std::uint64_t set_bits = 0U;
    for (const std::uint64_t word : expected) {
      set_bits += std::popcount(word);
    }
    cuda_check(cudaFree(wheel), "cudaFree wheel");
    wheel = nullptr;
    cuda_check(cudaFree(baseline), "cudaFree baseline");
    baseline = nullptr;
    return {low, high, set_bits, fnv1a(expected)};
  } catch (...) {
    if (wheel != nullptr) cudaFree(wheel);
    if (baseline != nullptr) cudaFree(baseline);
    throw;
  }
}

}  // namespace

int main() {
  try {
    cudaDeviceProp properties{};
    cuda_check(cudaGetDeviceProperties(&properties, 0),
               "cudaGetDeviceProperties");
    const std::vector<std::uint64_t> base = primes();
    const std::vector<std::uint64_t> wheel_primes = {
        3U,  5U,  7U,  11U, 13U, 17U, 19U,
        23U, 29U, 31U, 37U, 41U, 43U, 47U};
    const std::uint64_t warp_count =
        std::upper_bound(base.begin(), base.end(), kWarpCutoff) - base.begin();
    if (warp_count == 0U || warp_count >= base.size()) {
      throw std::runtime_error("KAT prime partition is malformed");
    }
    std::uint64_t* device_base = nullptr;
    std::uint64_t* device_wheel_primes = nullptr;
    cuda_check(cudaMalloc(&device_base,
                          base.size() * sizeof(std::uint64_t)),
               "cudaMalloc primes");
    cuda_check(cudaMalloc(
                   &device_wheel_primes,
                   wheel_primes.size() * sizeof(std::uint64_t)),
               "cudaMalloc wheel primes");
    try {
      cuda_check(cudaMemcpy(device_base, base.data(),
                            base.size() * sizeof(std::uint64_t),
                            cudaMemcpyHostToDevice),
                 "copy primes");
      cuda_check(cudaMemcpy(
                     device_wheel_primes, wheel_primes.data(),
                     wheel_primes.size() * sizeof(std::uint64_t),
                     cudaMemcpyHostToDevice),
                 "copy wheel primes");
      const std::uint64_t near_max =
          std::numeric_limits<std::uint64_t>::max() -
          2U * (kOddCount - 1U);
      const std::vector<std::uint64_t> starts = {
          4'000'001ULL,
          4'156'001ULL,
          31'249'998'799'000'003ULL,
          near_max,
      };
      std::vector<Result> results;
      for (const std::uint64_t start : starts) {
        results.push_back(run_window(
            start, base, wheel_primes, warp_count, device_base,
            device_wheel_primes));
      }
      cuda_check(cudaFree(device_wheel_primes), "cudaFree wheel primes");
      device_wheel_primes = nullptr;
      cuda_check(cudaFree(device_base), "cudaFree primes");
      device_base = nullptr;

      std::cout
          << "{\"accepted\":true,\"compute_capability\":\""
          << properties.major << "." << properties.minor
          << "\",\"kind\":\"sparkinterval.goldbach-wheel-filter-kat.v1\""
          << ",\"cofactor_filter_limit\":" << kCofactorFilterLimit
          << ",\"odd_count_per_window\":" << kOddCount
          << ",\"prime_limit\":" << kPrimeLimit
          << ",\"tail_prime_count\":" << base.size()
          << ",\"warp_parallel_cutoff\":" << kWarpCutoff
          << ",\"warp_prime_count\":" << warp_count
          << ",\"wheel_modulus\":" << kWheel
          << ",\"window_count\":" << results.size() << ",\"windows\":[";
      for (std::size_t index = 0U; index < results.size(); ++index) {
        if (index != 0U) std::cout << ",";
        const Result& row = results[index];
        std::cout << "{\"fnv1a64\":\"" << hexadecimal(row.digest)
                  << "\",\"q_high\":\"" << row.high << "\",\"q_low\":\""
                  << row.low << "\",\"set_bits\":" << row.set_bits << "}";
      }
      std::cout << "],\"word_owner_cutoff\":" << kWordOwnerCutoff << "}\n";
    } catch (...) {
      if (device_wheel_primes != nullptr) cudaFree(device_wheel_primes);
      if (device_base != nullptr) cudaFree(device_base);
      throw;
    }
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 2;
  }
  return 0;
}

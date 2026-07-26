// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_mobius_segment.h"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

[[noreturn]] void fail(const char* message) {
  std::cerr << message << '\n';
  std::exit(1);
}

void check_cuda(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    std::cerr << operation << ": " << cudaGetErrorString(status) << '\n';
    std::exit(1);
  }
}

std::vector<std::uint32_t> primes_through(std::uint32_t limit) {
  std::vector<bool> composite(
      static_cast<std::size_t>(limit) + 1, false);
  std::vector<std::uint32_t> primes;
  for (std::uint32_t candidate = 2; candidate <= limit; ++candidate) {
    if (composite[candidate]) continue;
    primes.push_back(candidate);
    if (candidate <= limit / candidate) {
      for (std::uint32_t multiple = candidate * candidate;
           multiple <= limit; multiple += candidate) {
        composite[multiple] = true;
      }
    }
  }
  return primes;
}

std::uint32_t integer_square_root(std::uint64_t value) {
  std::uint32_t lower = 0;
  std::uint32_t upper = 100'000'001;
  while (lower + 1 < upper) {
    const std::uint32_t middle = lower + (upper - lower) / 2;
    if (middle <= value / middle) {
      lower = middle;
    } else {
      upper = middle;
    }
  }
  return lower;
}

struct Expected {
  std::uint64_t packed;
  std::int8_t mobius;
};

Expected expected_row(
    std::uint64_t number,
    const std::vector<std::uint32_t>& primes) {
  std::uint64_t product = 1;
  std::uint32_t count = 0;
  bool squareful = false;
  for (const std::uint64_t prime : primes) {
    if (number % prime != 0) continue;
    product *= prime;
    ++count;
    squareful = squareful || number % (prime * prime) == 0;
  }
  const std::uint64_t residual = number / product;
  const std::uint32_t omega = count + static_cast<std::uint32_t>(residual > 1);
  const std::int8_t mobius =
      squareful ? 0 : static_cast<std::int8_t>((omega & 1U) == 0 ? 1 : -1);
  const std::uint64_t packed =
      product |
      (static_cast<std::uint64_t>(count) << kTgMobiusFusedCountShift) |
      (squareful ? kTgMobiusFusedSquarefulBit : 0);
  return {packed, mobius};
}

void compare_range(
    std::uint64_t lower, std::size_t count,
    bool require_small_dense_prefix, bool require_p13_cases,
    bool require_p17_cases) {
  const std::uint64_t upper = lower + count - 1;
  const std::vector<std::uint32_t> primes =
      primes_through(integer_square_root(upper));
  if (!tg_mobius_host_roster_begins_23571113(
          primes.data(), primes.size())) {
    fail("p13 KAT roster does not begin [2,3,5,7,11,13]");
  }
  const std::uint64_t dense_prime_limit = 1 + (count - 1) / 256;
  const std::size_t dense_prime_count =
      static_cast<std::size_t>(
          std::upper_bound(
              primes.begin(), primes.end(), dense_prime_limit) -
          primes.begin());
  if (require_small_dense_prefix &&
      dense_prime_count >= kTgMobiusResidue23571113PrimeCount) {
    fail("small-count KAT did not make dense_prime_count < seed count");
  }

  std::uint32_t* device_primes = nullptr;
  TgMobiusFusedSupport* device_supports = nullptr;
  std::int8_t* device_mobius = nullptr;
  std::uint32_t* device_roster_invalid = nullptr;
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_primes),
          primes.size() * sizeof(std::uint32_t)),
      "cudaMalloc(p13 primes)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_supports),
          count * sizeof(TgMobiusFusedSupport)),
      "cudaMalloc(p13 supports)");
  check_cuda(
      cudaMalloc(reinterpret_cast<void**>(&device_mobius), count),
      "cudaMalloc(p13 mobius)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_roster_invalid),
          sizeof(std::uint32_t)),
      "cudaMalloc(p13 roster status)");
  check_cuda(
      cudaMemcpy(
          device_primes, primes.data(),
          primes.size() * sizeof(std::uint32_t),
          cudaMemcpyHostToDevice),
      "cudaMemcpy(p13 primes)");

  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense_residue_23571113_qualification(
          lower, count, device_primes, primes.size(), dense_prime_count,
          device_supports, device_mobius, device_roster_invalid),
      "p13 finalized qualification launch");
  std::vector<TgMobiusFusedSupport> p13_supports(count);
  std::vector<std::int8_t> p13_mobius(count);
  std::uint32_t roster_invalid = 1;
  check_cuda(
      cudaMemcpy(
          p13_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport), cudaMemcpyDeviceToHost),
      "cudaMemcpy(p13 supports)");
  check_cuda(
      cudaMemcpy(
          p13_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(p13 mobius)");
  check_cuda(
      cudaMemcpy(
          &roster_invalid, device_roster_invalid,
          sizeof(roster_invalid), cudaMemcpyDeviceToHost),
      "cudaMemcpy(p13 roster status)");
  if (roster_invalid != 0) {
    fail("p13 KAT rejected a valid roster");
  }

  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          lower, count, device_primes, primes.size(), dense_prime_count,
          device_supports, device_mobius, device_roster_invalid),
      "p11 differential launch");
  std::vector<TgMobiusFusedSupport> p11_supports(count);
  std::vector<std::int8_t> p11_mobius(count);
  check_cuda(
      cudaMemcpy(
          p11_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport), cudaMemcpyDeviceToHost),
      "cudaMemcpy(p11 supports)");
  check_cuda(
      cudaMemcpy(
          p11_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(p11 mobius)");

  bool saw_thirteen_not_square = false;
  bool saw_thirteen_square = false;
  bool saw_seventeen_not_square = false;
  bool saw_seventeen_square = false;
  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t number = lower + index;
    const Expected expected = expected_row(number, primes);
    if (p13_supports[index].packed != expected.packed ||
        p13_mobius[index] != expected.mobius ||
        p13_supports[index].packed != p11_supports[index].packed ||
        p13_mobius[index] != p11_mobius[index]) {
      fail("p13 all-row CPU/p11 differential KAT failed");
    }
    saw_thirteen_not_square =
        saw_thirteen_not_square ||
        (number % 13 == 0 && number % 169 != 0);
    saw_thirteen_square =
        saw_thirteen_square || number % 169 == 0;
    saw_seventeen_not_square =
        saw_seventeen_not_square ||
        (number % 17 == 0 && number % 289 != 0);
    saw_seventeen_square =
        saw_seventeen_square || number % 289 == 0;
  }
  if (require_p13_cases &&
      (!saw_thirteen_not_square || !saw_thirteen_square)) {
    fail("p13 KAT omitted a 13 versus 169 branch");
  }
  if (require_p17_cases &&
      (!saw_seventeen_not_square || !saw_seventeen_square)) {
    fail("p13 KAT omitted a p17 distinct/square strike");
  }

  check_cuda(cudaFree(device_roster_invalid), "cudaFree(p13 roster status)");
  check_cuda(cudaFree(device_mobius), "cudaFree(p13 mobius)");
  check_cuda(cudaFree(device_supports), "cudaFree(p13 supports)");
  check_cuda(cudaFree(device_primes), "cudaFree(p13 primes)");
}

void check_host_constants_and_preflight() {
  if (kTgMobiusResidue23571113Modulus != 169 ||
      kTgMobiusResidue23571113PrimeCount != 6 ||
      kTgMobiusResidue23571113SuffixMinimum != 17 ||
      kTgMobiusResidue23571113MinimumSlotsPerPrime != 61 ||
      kTgMobiusResidue23571113MultiblockSlotsPerPrime != 512) {
    fail("p13 header constants differ from the qualification contract");
  }
  const std::size_t maximum_events =
      (kTgMobiusMultiblockMaximumCount +
       kTgMobiusResidue23571113SuffixMinimum - 1) /
      kTgMobiusResidue23571113SuffixMinimum;
  if (maximum_events >
          61 * kTgMobiusMultipleEventsPerBlock ||
      maximum_events <=
          60 * kTgMobiusMultipleEventsPerBlock) {
    fail("p13 61-slot bound is not exact and minimal");
  }
  const std::uint32_t valid[] = {2, 3, 5, 7, 11, 13};
  const std::uint32_t short_roster[] = {2, 3, 5, 7, 11};
  const std::uint32_t wrong_last[] = {2, 3, 5, 7, 11, 17};
  if (!tg_mobius_host_roster_begins_23571113(valid, 6) ||
      tg_mobius_host_roster_begins_23571113(short_roster, 5) ||
      tg_mobius_host_roster_begins_23571113(wrong_last, 6) ||
      tg_mobius_host_roster_begins_23571113(nullptr, 6)) {
    fail("p13 host roster-prefix validation KAT failed");
  }
}

void require_device_roster_rejection(
    const std::vector<std::uint32_t>& roster) {
  std::uint32_t* device_primes = nullptr;
  TgMobiusFusedSupport* device_support = nullptr;
  std::uint32_t* device_roster_invalid = nullptr;
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_primes),
          roster.size() * sizeof(std::uint32_t)),
      "cudaMalloc(p13 invalid roster)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_support),
          sizeof(TgMobiusFusedSupport)),
      "cudaMalloc(p13 invalid support)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_roster_invalid),
          sizeof(std::uint32_t)),
      "cudaMalloc(p13 invalid status)");
  check_cuda(
      cudaMemcpy(
          device_primes, roster.data(),
          roster.size() * sizeof(std::uint32_t),
          cudaMemcpyHostToDevice),
      "cudaMemcpy(p13 invalid roster)");
  check_cuda(
      launch_tg_mobius_fused_support_multiblock_dense_residue_23571113_qualification(
          30'030, 1, device_primes, roster.size(), 0,
          device_support, device_roster_invalid),
      "p13 invalid-roster qualification launch");
  std::uint32_t roster_invalid = 0;
  TgMobiusFusedSupport support{};
  check_cuda(
      cudaMemcpy(
          &roster_invalid, device_roster_invalid,
          sizeof(roster_invalid), cudaMemcpyDeviceToHost),
      "cudaMemcpy(p13 invalid status)");
  check_cuda(
      cudaMemcpy(
          &support, device_support, sizeof(support),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(p13 poisoned support)");
  if (roster_invalid != 1 ||
      (support.packed & kTgMobiusFusedPoisonBit) == 0) {
    fail("p13 device roster preflight did not poison malformed input");
  }
  check_cuda(cudaFree(device_roster_invalid), "cudaFree(p13 invalid status)");
  check_cuda(cudaFree(device_support), "cudaFree(p13 invalid support)");
  check_cuda(cudaFree(device_primes), "cudaFree(p13 invalid roster)");
}

}  // namespace

int main() {
  check_host_constants_and_preflight();
  require_device_roster_rejection({2, 3, 5, 7, 11, 17});
  require_device_roster_rejection({2, 3, 5, 7, 11, 13, 13});
  require_device_roster_rejection({2, 3, 5, 7, 11, 13, 15});

  // Exact lower residues 0, 1, and 168 with tiny partial blocks.  Each span
  // includes both a 13-only row and a 169-square row while forcing
  // dense_prime_count below the six-prime seeded prefix.
  compare_range(169 * 1000, 20, true, true, false);
  compare_range(169 * 1000 + 1, 170, true, true, false);
  compare_range(169 * 1000 + 168, 20, true, true, false);

  // A 511-row partial final block crosses the 256-thread boundary.  Starting
  // at residue 168 exercises the in-block `(168 + threadIdx) % 169` wrap.
  compare_range(169 * 1000 + 168, 511, false, true, true);

  // Explicit p=17 suffix corpus: 289 is a square strike and 306 is a
  // distinct-factor event without a p17 square.
  compare_range(289, 34, true, false, true);

  std::cout
      << "p13 residue initializer lower residues 0/1/168, UInt32/block "
         "wrap, 13/169 branches, p17 distinct/square suffix, short dense "
         "prefix, partial block, exact 61-slot bound: ok\n";
  return 0;
}

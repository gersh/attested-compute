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

std::uint64_t pack(std::uint64_t product, std::uint32_t count,
                   bool squareful) {
  return product |
         (static_cast<std::uint64_t>(count)
          << kTgMobiusFusedCountShift) |
         (squareful ? kTgMobiusFusedSquarefulBit : 0);
}

void check_cuda(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    std::cerr << operation << ": " << cudaGetErrorString(status) << '\n';
    std::exit(1);
  }
}

void run_device_case(std::uint64_t number,
                     const std::vector<std::uint32_t>& primes,
                     std::uint64_t expected_product,
                     std::uint32_t expected_count,
                     bool expected_squareful,
                     std::int8_t expected_mobius,
                     bool expected_poison) {
  std::uint32_t* device_primes = nullptr;
  TgMobiusFusedSupport* device_support = nullptr;
  std::int8_t* device_mobius = nullptr;
  if (!primes.empty()) {
    check_cuda(
        cudaMalloc(reinterpret_cast<void**>(&device_primes),
                   primes.size() * sizeof(std::uint32_t)),
        "cudaMalloc(primes)");
  }
  check_cuda(
      cudaMalloc(reinterpret_cast<void**>(&device_support),
                 sizeof(TgMobiusFusedSupport)),
      "cudaMalloc(support)");
  check_cuda(
      cudaMalloc(reinterpret_cast<void**>(&device_mobius), 1),
      "cudaMalloc(mobius)");
  if (!primes.empty()) {
    check_cuda(
        cudaMemcpy(device_primes, primes.data(),
                   primes.size() * sizeof(std::uint32_t),
                   cudaMemcpyHostToDevice),
        "cudaMemcpy(primes)");
  }
  check_cuda(
      launch_tg_mobius_fused_segment(
          number, 1, device_primes, primes.size(), 0,
          device_support, device_mobius),
      "fused one-row launch");
  TgMobiusFusedSupport support{};
  std::int8_t mobius = 0;
  check_cuda(
      cudaMemcpy(&support, device_support, sizeof(support),
                 cudaMemcpyDeviceToHost),
      "cudaMemcpy(support)");
  check_cuda(
      cudaMemcpy(&mobius, device_mobius, 1, cudaMemcpyDeviceToHost),
      "cudaMemcpy(mobius)");
  const std::uint64_t packed = support.packed;
  if ((packed & kTgMobiusFusedProductMask) != expected_product ||
      ((packed & kTgMobiusFusedCountMask) >>
       kTgMobiusFusedCountShift) != expected_count ||
      ((packed & kTgMobiusFusedSquarefulBit) != 0) !=
          expected_squareful ||
      ((packed & kTgMobiusFusedPoisonBit) != 0) != expected_poison ||
      mobius != expected_mobius) {
    fail("fused one-row device CAS KAT failed");
  }

  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense(
          number, 1, device_primes, primes.size(), 0,
          device_support, device_mobius),
      "load-balanced multiblock one-row launch");
  check_cuda(
      cudaMemcpy(&support, device_support, sizeof(support),
                 cudaMemcpyDeviceToHost),
      "cudaMemcpy(multiblock support)");
  check_cuda(
      cudaMemcpy(&mobius, device_mobius, 1, cudaMemcpyDeviceToHost),
      "cudaMemcpy(multiblock mobius)");
  if (support.packed != packed || mobius != expected_mobius) {
    fail("load-balanced multiblock fused KAT failed");
  }
  check_cuda(cudaFree(device_mobius), "cudaFree(mobius)");
  check_cuda(cudaFree(device_support), "cudaFree(support)");
  if (device_primes != nullptr) {
    check_cuda(cudaFree(device_primes), "cudaFree(primes)");
  }
}

std::vector<std::uint32_t> primes_through(std::uint32_t limit) {
  std::vector<bool> composite(
      static_cast<std::size_t>(limit) + 1, false);
  std::vector<std::uint32_t> primes;
  for (std::uint32_t candidate = 2;
       candidate <= limit; ++candidate) {
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
    const std::uint32_t middle =
        lower + (upper - lower) / 2;
    if (middle <= value / middle) {
      lower = middle;
    } else {
      upper = middle;
    }
  }
  return lower;
}

void run_range_comparison(std::uint64_t lower, std::size_t count) {
  const std::uint64_t upper = lower + count - 1;
  const std::vector<std::uint32_t> primes =
      primes_through(integer_square_root(upper));
  const std::uint64_t dense_prime_limit =
      1 + (count - 1) / 256;
  const std::size_t dense_prime_count =
      static_cast<std::size_t>(
          std::upper_bound(
              primes.begin(), primes.end(), dense_prime_limit) -
          primes.begin());

  std::uint32_t* device_primes = nullptr;
  TgMobiusFusedSupport* device_supports = nullptr;
  std::int8_t* device_mobius = nullptr;
  TgMobiusPrefixMQ* device_prefix_inputs = nullptr;
  std::uint32_t* device_poison_count = nullptr;
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_primes),
          primes.size() * sizeof(std::uint32_t)),
      "cudaMalloc(range primes)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_supports),
          count * sizeof(TgMobiusFusedSupport)),
      "cudaMalloc(range supports)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_mobius), count),
      "cudaMalloc(range mobius)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_prefix_inputs),
          count * sizeof(TgMobiusPrefixMQ)),
      "cudaMalloc(range prefix inputs)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_poison_count),
          sizeof(std::uint32_t)),
      "cudaMalloc(range poison count)");
  check_cuda(
      cudaMemcpy(
          device_primes, primes.data(),
          primes.size() * sizeof(std::uint32_t),
          cudaMemcpyHostToDevice),
      "cudaMemcpy(range primes)");

  std::vector<TgMobiusFusedSupport> inline_supports(count);
  std::vector<TgMobiusFusedSupport> multiblock_supports(count);
  std::vector<TgMobiusFusedSupport> residue_supports(count);
  std::vector<TgMobiusFusedSupport> direct_prefix_supports(count);
  std::vector<TgMobiusFusedSupport> split_square_supports(count);
  std::vector<TgMobiusFusedSupport> seed7_finalized_supports(count);
  std::vector<TgMobiusFusedSupport> seed7_prefix_supports(count);
  std::vector<TgMobiusFusedSupport> seed11_finalized_supports(count);
  std::vector<TgMobiusFusedSupport> seed11_prefix_supports(count);
  std::vector<std::int8_t> inline_mobius(count);
  std::vector<std::int8_t> multiblock_mobius(count);
  std::vector<std::int8_t> residue_mobius(count);
  std::vector<std::int8_t> seed7_mobius(count);
  std::vector<std::int8_t> seed11_mobius(count);
  std::vector<TgMobiusPrefixMQ> direct_prefix_inputs(count);
  std::vector<TgMobiusPrefixMQ> split_square_prefix_inputs(count);
  std::vector<TgMobiusPrefixMQ> seed7_prefix_inputs(count);
  std::vector<TgMobiusPrefixMQ> seed11_prefix_inputs(count);
  check_cuda(
      launch_tg_mobius_fused_segment(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_mobius),
      "inline range launch");
  check_cuda(
      cudaMemcpy(
          inline_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(inline range supports)");
  check_cuda(
      cudaMemcpy(
          inline_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(inline range mobius)");

  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_mobius),
      "multiblock range launch");
  check_cuda(
      cudaMemcpy(
          multiblock_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(multiblock range supports)");
  check_cuda(
      cudaMemcpy(
          multiblock_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(multiblock range mobius)");

  if (primes.size() < 3 ||
      primes[0] != 2 || primes[1] != 3 || primes[2] != 5) {
    fail("residue-235 range KAT roster prefix is not [2,3,5]");
  }
  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_mobius),
      "residue-235 range launch");
  check_cuda(
      cudaMemcpy(
          residue_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235 range supports)");
  check_cuda(
      cudaMemcpy(
          residue_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235 range mobius)");

  check_cuda(
      cudaMemset(device_poison_count, 0, sizeof(std::uint32_t)),
      "cudaMemset(range poison count)");
  check_cuda(
      launch_tg_mobius_fused_support_multiblock_dense_residue_235(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports),
      "residue-235 support-only range launch");
  check_cuda(
      launch_tg_mobius_fused_prefix_inputs(
          lower, device_supports, count, device_prefix_inputs,
          device_poison_count),
      "direct fused prefix-input range launch");
  check_cuda(
      cudaMemcpy(
          direct_prefix_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(direct prefix range supports)");
  check_cuda(
      cudaMemcpy(
          direct_prefix_inputs.data(), device_prefix_inputs,
          count * sizeof(TgMobiusPrefixMQ),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(direct prefix range inputs)");
  std::uint32_t poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_poison_count,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(range poison count)");
  if (poison_count != 0) {
    fail("direct fused prefix-input range emitted poison");
  }

  check_cuda(
      cudaMemset(device_poison_count, 0, sizeof(std::uint32_t)),
      "cudaMemset(split-square poison count)");
  check_cuda(
      launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_poison_count),
      "residue-235 split-square support range launch");
  check_cuda(
      launch_tg_mobius_fused_prefix_inputs(
          lower, device_supports, count, device_prefix_inputs,
          device_poison_count),
      "split-square fused prefix-input range launch");
  check_cuda(
      cudaMemcpy(
          split_square_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(split-square range supports)");
  check_cuda(
      cudaMemcpy(
          split_square_prefix_inputs.data(), device_prefix_inputs,
          count * sizeof(TgMobiusPrefixMQ),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(split-square range inputs)");
  poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_poison_count,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(split-square poison count)");
  if (poison_count != 0) {
    fail("split-square fused prefix-input range emitted poison");
  }

  if (primes.size() < 4 || primes[3] != 7) {
    fail("residue-2357 range KAT roster prefix is not [2,3,5,7]");
  }
  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense_residue_2357_qualification(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_mobius,
          device_poison_count),
      "residue-2357 finalized qualification range launch");
  check_cuda(
      cudaMemcpy(
          seed7_finalized_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-2357 finalized range supports)");
  check_cuda(
      cudaMemcpy(
          seed7_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-2357 range mobius)");
  poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_poison_count,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-2357 finalized roster status)");
  if (poison_count != 0) {
    fail("residue-2357 finalized qualification rejected a valid roster");
  }

  check_cuda(
      launch_tg_mobius_fused_support_multiblock_dense_residue_2357_qualification(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_poison_count),
      "residue-2357 support qualification range launch");
  check_cuda(
      launch_tg_mobius_fused_prefix_inputs(
          lower, device_supports, count, device_prefix_inputs,
          device_poison_count),
      "residue-2357 fused prefix-input range launch");
  check_cuda(
      cudaMemcpy(
          seed7_prefix_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-2357 prefix range supports)");
  check_cuda(
      cudaMemcpy(
          seed7_prefix_inputs.data(), device_prefix_inputs,
          count * sizeof(TgMobiusPrefixMQ),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-2357 prefix range inputs)");
  poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_poison_count,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-2357 prefix poison count)");
  if (poison_count != 0) {
    fail("residue-2357 fused prefix-input range emitted poison");
  }

  if (primes.size() < 5 || primes[4] != 11) {
    fail(
        "residue-235711 range KAT roster prefix is not "
        "[2,3,5,7,11]");
  }
  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_mobius,
          device_poison_count),
      "residue-235711 finalized qualification range launch");
  check_cuda(
      cudaMemcpy(
          seed11_finalized_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235711 finalized range supports)");
  check_cuda(
      cudaMemcpy(
          seed11_mobius.data(), device_mobius, count,
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235711 range mobius)");
  poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_poison_count,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235711 finalized roster status)");
  if (poison_count != 0) {
    fail("residue-235711 finalized qualification rejected a valid roster");
  }

  check_cuda(
      launch_tg_mobius_fused_support_multiblock_dense_residue_235711_qualification(
          lower, count, device_primes, primes.size(),
          dense_prime_count, device_supports, device_poison_count),
      "residue-235711 support qualification range launch");
  check_cuda(
      launch_tg_mobius_fused_prefix_inputs(
          lower, device_supports, count, device_prefix_inputs,
          device_poison_count),
      "residue-235711 fused prefix-input range launch");
  check_cuda(
      cudaMemcpy(
          seed11_prefix_supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235711 prefix range supports)");
  check_cuda(
      cudaMemcpy(
          seed11_prefix_inputs.data(), device_prefix_inputs,
          count * sizeof(TgMobiusPrefixMQ),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235711 prefix range inputs)");
  poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_poison_count,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(residue-235711 prefix poison count)");
  if (poison_count != 0) {
    fail("residue-235711 fused prefix-input range emitted poison");
  }

  const TgMobiusResidueSeed rectangular_seeds[] = {
      TgMobiusResidueSeed::k235,
      TgMobiusResidueSeed::k2357,
      TgMobiusResidueSeed::k235711};
  const TgMobiusRectangularSlotMode rectangular_modes[] = {
      TgMobiusRectangularSlotMode::kRect2d512,
      TgMobiusRectangularSlotMode::kRect2dPower,
      TgMobiusRectangularSlotMode::kRect2dExact,
      TgMobiusRectangularSlotMode::kRect2dCountExact};
  std::vector<TgMobiusFusedSupport> rectangular_supports(count);
  std::vector<std::int8_t> rectangular_mobius(count);
  for (const TgMobiusResidueSeed seed : rectangular_seeds) {
    std::size_t seed_prime_count = 0;
    std::uint32_t suffix_minimum = 0;
    std::size_t maximum_exact_slots = 0;
    switch (seed) {
      case TgMobiusResidueSeed::k235:
        seed_prime_count = kTgMobiusResidue235PrimeCount;
        suffix_minimum = 7;
        maximum_exact_slots =
            kTgMobiusResidue235MinimumSlotsPerPrime;
        break;
      case TgMobiusResidueSeed::k2357:
        seed_prime_count = kTgMobiusResidue2357PrimeCount;
        suffix_minimum = kTgMobiusResidue2357SuffixMinimum;
        maximum_exact_slots =
            kTgMobiusResidue2357MinimumSlotsPerPrime;
        break;
      case TgMobiusResidueSeed::k235711:
        seed_prime_count = kTgMobiusResidue235711PrimeCount;
        suffix_minimum = kTgMobiusResidue235711SuffixMinimum;
        maximum_exact_slots =
            kTgMobiusResidue235711MinimumSlotsPerPrime;
        break;
    }
    const std::size_t required_slots =
        1 + ((count - 1) /
                 static_cast<std::size_t>(suffix_minimum)) /
                kTgMobiusMultipleEventsPerBlock;
    const std::size_t seeded_dense_prime_count =
        std::min(dense_prime_count, seed_prime_count);
    const std::size_t rectangular_prime_count =
        std::min(
            dense_prime_count - seeded_dense_prime_count,
            kTgMobiusMultiblockDensePrimeLimit);
    for (const TgMobiusRectangularSlotMode mode : rectangular_modes) {
      TgMobiusRectangularLaunchGeometry geometry{};
      check_cuda(
          launch_tg_mobius_fused_segment_multiblock_dense_residue_rectangular_qualification(
              lower, count, device_primes, primes.size(),
              dense_prime_count, seed, mode, device_supports,
              device_mobius, device_poison_count, &geometry),
          "rectangular qualification range launch");
      check_cuda(
          cudaMemcpy(
              rectangular_supports.data(), device_supports,
              count * sizeof(TgMobiusFusedSupport),
              cudaMemcpyDeviceToHost),
          "cudaMemcpy(rectangular range supports)");
      check_cuda(
          cudaMemcpy(
              rectangular_mobius.data(), device_mobius, count,
              cudaMemcpyDeviceToHost),
          "cudaMemcpy(rectangular range mobius)");
      poison_count = 0;
      check_cuda(
          cudaMemcpy(
              &poison_count, device_poison_count,
              sizeof(poison_count), cudaMemcpyDeviceToHost),
          "cudaMemcpy(rectangular roster status)");
      std::size_t expected_slots = required_slots;
      if (mode == TgMobiusRectangularSlotMode::kRect2d512) {
        expected_slots = 512;
      } else if (mode ==
                 TgMobiusRectangularSlotMode::kRect2dPower) {
        expected_slots = 1;
        while (expected_slots < required_slots) expected_slots *= 2;
      } else if (mode ==
                 TgMobiusRectangularSlotMode::kRect2dExact) {
        expected_slots = maximum_exact_slots;
      }
      if (poison_count != 0 || geometry.seed != seed ||
          geometry.mode != mode ||
          geometry.enclosing_lower != lower ||
          geometry.enclosing_count != count ||
          geometry.required_slots_per_prime != required_slots ||
          geometry.slots_per_prime != expected_slots ||
          geometry.events_per_block !=
              kTgMobiusMultipleEventsPerBlock ||
          geometry.grid_x != expected_slots ||
          geometry.grid_y != rectangular_prime_count ||
          geometry.grid_z != 1 ||
          geometry.threads_per_block !=
              kTgMobiusThreadsPerBlock) {
        fail("rectangular qualification geometry/status KAT failed");
      }
      for (std::size_t index = 0; index < count; ++index) {
        if (rectangular_supports[index].packed !=
                inline_supports[index].packed ||
            rectangular_mobius[index] != inline_mobius[index]) {
          fail(
              "rectangular qualification differs from the flat/CPU "
              "reference");
        }
      }
    }
  }

  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t number = lower + index;
    std::uint64_t product = 1;
    std::uint32_t distinct_count = 0;
    bool squareful = false;
    for (const std::uint64_t prime : primes) {
      if (number % prime != 0) continue;
      product *= prime;
      ++distinct_count;
      squareful =
          squareful || number % (prime * prime) == 0;
    }
    const std::uint64_t residual = number / product;
    const std::int8_t expected_mobius =
        squareful
            ? 0
            : static_cast<std::int8_t>(
                  ((distinct_count + (residual > 1)) & 1U) == 0
                      ? 1
                      : -1);
    const std::uint64_t inline_packed =
        inline_supports[index].packed;
    if (multiblock_supports[index].packed != inline_packed ||
        residue_supports[index].packed != inline_packed ||
        direct_prefix_supports[index].packed != inline_packed ||
        split_square_supports[index].packed != inline_packed ||
        seed7_finalized_supports[index].packed != inline_packed ||
        seed7_prefix_supports[index].packed != inline_packed ||
        seed11_finalized_supports[index].packed != inline_packed ||
        seed11_prefix_supports[index].packed != inline_packed ||
        inline_mobius[index] != expected_mobius ||
        multiblock_mobius[index] != expected_mobius ||
        residue_mobius[index] != expected_mobius ||
        seed7_mobius[index] != expected_mobius ||
        seed11_mobius[index] != expected_mobius ||
        direct_prefix_inputs[index].mertens != expected_mobius ||
        direct_prefix_inputs[index].squarefree !=
            static_cast<std::uint32_t>(expected_mobius != 0) ||
        split_square_prefix_inputs[index].mertens != expected_mobius ||
        split_square_prefix_inputs[index].squarefree !=
            static_cast<std::uint32_t>(expected_mobius != 0) ||
        seed7_prefix_inputs[index].mertens != expected_mobius ||
        seed7_prefix_inputs[index].squarefree !=
            static_cast<std::uint32_t>(expected_mobius != 0) ||
        seed11_prefix_inputs[index].mertens != expected_mobius ||
        seed11_prefix_inputs[index].squarefree !=
            static_cast<std::uint32_t>(expected_mobius != 0)) {
      std::cerr
          << "range mismatch n=" << number
          << " reference_packed=" << inline_packed
          << " split_packed=" << split_square_supports[index].packed
          << " seed7_packed=" << seed7_prefix_supports[index].packed
          << " seed11_packed=" << seed11_prefix_supports[index].packed
          << " expected_mu=" << static_cast<int>(expected_mobius)
          << " split_mu="
          << split_square_prefix_inputs[index].mertens
          << '\n';
      fail(
          "legacy/load-balanced/residue-235/split-square/residue-2357/"
          "residue-235711 "
          "all-row range KAT failed");
    }
  }

  check_cuda(
      cudaFree(device_poison_count), "cudaFree(range poison count)");
  check_cuda(
      cudaFree(device_prefix_inputs), "cudaFree(range prefix inputs)");
  check_cuda(cudaFree(device_mobius), "cudaFree(range mobius)");
  check_cuda(cudaFree(device_supports), "cudaFree(range supports)");
  check_cuda(cudaFree(device_primes), "cudaFree(range primes)");
}

void run_seed11_word_case(
    std::uint64_t number, std::uint64_t expected_product,
    std::uint32_t expected_count, bool expected_squareful,
    std::int8_t expected_mobius) {
  const std::vector<std::uint32_t> primes =
      primes_through(integer_square_root(number));
  if (!tg_mobius_host_roster_begins_235711(
          primes.data(), primes.size())) {
    fail("explicit residue-235711 word KAT lacks its canonical prefix");
  }
  std::uint32_t* device_primes = nullptr;
  TgMobiusFusedSupport* device_support = nullptr;
  std::int8_t* device_mobius = nullptr;
  std::uint32_t* device_roster_invalid = nullptr;
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_primes),
          primes.size() * sizeof(std::uint32_t)),
      "cudaMalloc(seed11 word primes)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_support),
          sizeof(TgMobiusFusedSupport)),
      "cudaMalloc(seed11 word support)");
  check_cuda(
      cudaMalloc(reinterpret_cast<void**>(&device_mobius), 1),
      "cudaMalloc(seed11 word mobius)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_roster_invalid),
          sizeof(std::uint32_t)),
      "cudaMalloc(seed11 word roster status)");
  check_cuda(
      cudaMemcpy(
          device_primes, primes.data(),
          primes.size() * sizeof(std::uint32_t),
          cudaMemcpyHostToDevice),
      "cudaMemcpy(seed11 word primes)");
  check_cuda(
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          number, 1, device_primes, primes.size(), primes.size(),
          device_support, device_mobius, device_roster_invalid),
      "residue-235711 explicit word launch");
  TgMobiusFusedSupport support{};
  std::int8_t mobius = 0;
  std::uint32_t roster_invalid = 0;
  check_cuda(
      cudaMemcpy(
          &support, device_support, sizeof(support),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(seed11 word support)");
  check_cuda(
      cudaMemcpy(
          &mobius, device_mobius, sizeof(mobius),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(seed11 word mobius)");
  check_cuda(
      cudaMemcpy(
          &roster_invalid, device_roster_invalid,
          sizeof(roster_invalid), cudaMemcpyDeviceToHost),
      "cudaMemcpy(seed11 word roster status)");
  if (roster_invalid != 0 ||
      support.packed !=
          pack(expected_product, expected_count, expected_squareful) ||
      mobius != expected_mobius) {
    fail("explicit residue-235711 packed product/count/squareful KAT failed");
  }
  check_cuda(
      cudaFree(device_roster_invalid),
      "cudaFree(seed11 word roster status)");
  check_cuda(cudaFree(device_mobius), "cudaFree(seed11 word mobius)");
  check_cuda(cudaFree(device_support), "cudaFree(seed11 word support)");
  check_cuda(cudaFree(device_primes), "cudaFree(seed11 word primes)");
}

enum class SplitSquareSeedMode {
  kResidue235,
  kResidue2357,
  kResidue235711,
};

void run_split_square_malformed_roster_case(
    const std::vector<std::uint32_t>& primes,
    SplitSquareSeedMode seed_mode =
        SplitSquareSeedMode::kResidue235) {
  constexpr std::uint64_t lower = 1'000;
  constexpr std::size_t count = 513;
  std::uint32_t* device_primes = nullptr;
  TgMobiusFusedSupport* device_supports = nullptr;
  TgMobiusPrefixMQ* device_prefix_inputs = nullptr;
  std::uint32_t* device_roster_invalid = nullptr;
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_primes),
          primes.size() * sizeof(std::uint32_t)),
      "cudaMalloc(malformed roster primes)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_supports),
          count * sizeof(TgMobiusFusedSupport)),
      "cudaMalloc(malformed roster supports)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_prefix_inputs),
          count * sizeof(TgMobiusPrefixMQ)),
      "cudaMalloc(malformed roster prefix inputs)");
  check_cuda(
      cudaMalloc(
          reinterpret_cast<void**>(&device_roster_invalid),
          sizeof(std::uint32_t)),
      "cudaMalloc(malformed roster status)");
  check_cuda(
      cudaMemcpy(
          device_primes, primes.data(),
          primes.size() * sizeof(std::uint32_t),
          cudaMemcpyHostToDevice),
      "cudaMemcpy(malformed roster primes)");
  cudaError_t launch_status = cudaErrorInvalidValue;
  if (seed_mode == SplitSquareSeedMode::kResidue235711) {
    launch_status =
        launch_tg_mobius_fused_support_multiblock_dense_residue_235711_qualification(
            lower, count, device_primes, primes.size(),
            primes.size(), device_supports,
            device_roster_invalid);
  } else if (seed_mode == SplitSquareSeedMode::kResidue2357) {
    launch_status =
        launch_tg_mobius_fused_support_multiblock_dense_residue_2357_qualification(
            lower, count, device_primes, primes.size(),
            primes.size(), device_supports,
            device_roster_invalid);
  } else {
    launch_status =
        launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
            lower, count, device_primes, primes.size(),
            primes.size(), device_supports,
            device_roster_invalid);
  }
  check_cuda(launch_status, "malformed split-square support launch");

  std::uint32_t roster_invalid = 0;
  std::vector<TgMobiusFusedSupport> supports(count);
  check_cuda(
      cudaMemcpy(
          &roster_invalid, device_roster_invalid,
          sizeof(roster_invalid), cudaMemcpyDeviceToHost),
      "cudaMemcpy(malformed roster status)");
  check_cuda(
      cudaMemcpy(
          supports.data(), device_supports,
          count * sizeof(TgMobiusFusedSupport),
          cudaMemcpyDeviceToHost),
      "cudaMemcpy(malformed roster supports)");
  if (roster_invalid != 1 ||
      !std::all_of(
          supports.begin(), supports.end(),
          [](const TgMobiusFusedSupport& support) {
            return (support.packed & kTgMobiusFusedPoisonBit) != 0;
          })) {
    fail("malformed split-square roster did not poison every support row");
  }

  check_cuda(
      cudaMemset(
          device_roster_invalid, 0, sizeof(std::uint32_t)),
      "cudaMemset(malformed roster poison count)");
  check_cuda(
      launch_tg_mobius_fused_prefix_inputs(
          lower, device_supports, count, device_prefix_inputs,
          device_roster_invalid),
      "malformed roster prefix-input launch");
  std::uint32_t poison_count = 0;
  check_cuda(
      cudaMemcpy(
          &poison_count, device_roster_invalid,
          sizeof(poison_count), cudaMemcpyDeviceToHost),
      "cudaMemcpy(malformed roster poison count)");
  if (poison_count != count) {
    fail("malformed split-square roster poison count did not cover every row");
  }

  check_cuda(
      cudaFree(device_roster_invalid),
      "cudaFree(malformed roster status)");
  check_cuda(
      cudaFree(device_prefix_inputs),
      "cudaFree(malformed roster prefix inputs)");
  check_cuda(
      cudaFree(device_supports),
      "cudaFree(malformed roster supports)");
  check_cuda(
      cudaFree(device_primes),
      "cudaFree(malformed roster primes)");
}

}  // namespace

int main() {
  const std::uint32_t valid_seed_prefix[] = {2, 3, 5};
  const std::uint32_t invalid_seed_prefix[] = {2, 3, 7};
  const std::uint32_t valid_seed7_prefix[] = {2, 3, 5, 7};
  const std::uint32_t invalid_seed7_prefix[] = {2, 3, 5, 11};
  const std::uint32_t valid_seed11_prefix[] = {2, 3, 5, 7, 11};
  const std::uint32_t invalid_seed11_prefix[] = {2, 3, 5, 7, 13};
  if (!tg_mobius_host_roster_begins_235(valid_seed_prefix, 3) ||
      tg_mobius_host_roster_begins_235(invalid_seed_prefix, 3) ||
      tg_mobius_host_roster_begins_235(valid_seed_prefix, 2) ||
      tg_mobius_host_roster_begins_235(nullptr, 3)) {
    fail("host residue-235 roster-prefix validator KAT failed");
  }
  if (!tg_mobius_host_roster_begins_2357(valid_seed7_prefix, 4) ||
      tg_mobius_host_roster_begins_2357(invalid_seed7_prefix, 4) ||
      tg_mobius_host_roster_begins_2357(valid_seed7_prefix, 3) ||
      tg_mobius_host_roster_begins_2357(nullptr, 4)) {
    fail("host residue-2357 roster-prefix validator KAT failed");
  }
  if (!tg_mobius_host_roster_begins_235711(valid_seed11_prefix, 5) ||
      tg_mobius_host_roster_begins_235711(
          invalid_seed11_prefix, 5) ||
      tg_mobius_host_roster_begins_235711(valid_seed11_prefix, 4) ||
      tg_mobius_host_roster_begins_235711(nullptr, 5)) {
    fail("host residue-235711 roster-prefix validator KAT failed");
  }
  const std::size_t maximum_p7_events =
      (kTgMobiusMultiblockMaximumCount + 7 - 1) / 7;
  if (kTgMobiusResidue235MinimumSlotsPerPrime != 147 ||
      maximum_p7_events >
          kTgMobiusResidue235MinimumSlotsPerPrime *
              kTgMobiusMultipleEventsPerBlock ||
      maximum_p7_events <=
          (kTgMobiusResidue235MinimumSlotsPerPrime - 1) *
              kTgMobiusMultipleEventsPerBlock) {
    fail("residue-235 exact minimum block-slot bound KAT failed");
  }
  const std::size_t maximum_p11_events =
      (kTgMobiusMultiblockMaximumCount +
           kTgMobiusResidue2357SuffixMinimum - 1) /
      kTgMobiusResidue2357SuffixMinimum;
  if (kTgMobiusResidue2357SuffixMinimum != 11 ||
      kTgMobiusResidue2357MinimumSlotsPerPrime != 94 ||
      kTgMobiusResidue2357MultiblockSlotsPerPrime <
          kTgMobiusResidue2357MinimumSlotsPerPrime ||
      maximum_p11_events >
          kTgMobiusResidue2357MultiblockSlotsPerPrime *
              kTgMobiusMultipleEventsPerBlock ||
      maximum_p11_events <=
          (kTgMobiusResidue2357MinimumSlotsPerPrime - 1) *
              kTgMobiusMultipleEventsPerBlock) {
    fail("residue-2357 exact minimum block-slot bound KAT failed");
  }
  const std::size_t maximum_p13_events =
      (kTgMobiusMultiblockMaximumCount +
           kTgMobiusResidue235711SuffixMinimum - 1) /
      kTgMobiusResidue235711SuffixMinimum;
  if (kTgMobiusResidue235711SuffixMinimum != 13 ||
      kTgMobiusResidue235711MinimumSlotsPerPrime != 79 ||
      kTgMobiusResidue235711MultiblockSlotsPerPrime !=
          kTgMobiusResidue2357MultiblockSlotsPerPrime ||
      maximum_p13_events >
          kTgMobiusResidue235711MultiblockSlotsPerPrime *
              kTgMobiusMultipleEventsPerBlock ||
      maximum_p13_events <=
          (kTgMobiusResidue235711MinimumSlotsPerPrime - 1) *
              kTgMobiusMultipleEventsPerBlock) {
    fail("residue-235711 exact minimum block-slot bound KAT failed");
  }
  TgMobiusRectangularLaunchGeometry rectangular_geometry{};
  struct MaximumGeometryCase {
    TgMobiusResidueSeed seed;
    std::size_t expected_exact_slots;
  };
  const MaximumGeometryCase maximum_geometry_cases[] = {
      {TgMobiusResidueSeed::k235, 147},
      {TgMobiusResidueSeed::k2357, 94},
      {TgMobiusResidueSeed::k235711, 79}};
  for (const MaximumGeometryCase& geometry_case :
       maximum_geometry_cases) {
    if (tg_mobius_rectangular_launch_geometry_qualification(
            1, kTgMobiusMultiblockMaximumCount,
            kTgMobiusMultiblockDensePrimeLimit,
            geometry_case.seed,
            TgMobiusRectangularSlotMode::kRect2dExact,
            &rectangular_geometry) != cudaSuccess ||
        rectangular_geometry.slots_per_prime !=
            geometry_case.expected_exact_slots ||
        rectangular_geometry.required_slots_per_prime !=
            geometry_case.expected_exact_slots ||
        rectangular_geometry.grid_y !=
            kTgMobiusMultiblockDensePrimeLimit) {
      fail("rectangular maximum-count exact-geometry KAT failed");
    }
  }
  const MaximumGeometryCase count_100m_geometry_cases[] = {
      {TgMobiusResidueSeed::k235, 14},
      {TgMobiusResidueSeed::k2357, 9},
      {TgMobiusResidueSeed::k235711, 8}};
  for (const MaximumGeometryCase& geometry_case :
       count_100m_geometry_cases) {
    if (tg_mobius_rectangular_launch_geometry_qualification(
            1, 100'000'000, 1, geometry_case.seed,
            TgMobiusRectangularSlotMode::kRect2dCountExact,
            &rectangular_geometry) != cudaSuccess ||
        rectangular_geometry.slots_per_prime !=
            geometry_case.expected_exact_slots ||
        rectangular_geometry.required_slots_per_prime !=
            geometry_case.expected_exact_slots) {
      fail("rectangular 100M count-exact geometry KAT failed");
    }
  }
  if (tg_mobius_rectangular_launch_geometry_qualification(
          1, 13 * kTgMobiusMultipleEventsPerBlock + 1, 0,
          TgMobiusResidueSeed::k235711,
          TgMobiusRectangularSlotMode::kRect2dCountExact,
          &rectangular_geometry) != cudaSuccess ||
      rectangular_geometry.required_slots_per_prime != 2 ||
      rectangular_geometry.slots_per_prime != 2 ||
      rectangular_geometry.grid_x != 2 ||
      rectangular_geometry.grid_y != 0) {
    fail("rectangular p13 two-slot/zero-prime geometry KAT failed");
  }
  if (tg_mobius_rectangular_launch_geometry_qualification(
          1, 0, 1, TgMobiusResidueSeed::k235,
          TgMobiusRectangularSlotMode::kRect2d512,
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          0, 1, 1, TgMobiusResidueSeed::k235,
          TgMobiusRectangularSlotMode::kRect2d512,
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          kTgMobiusSourceLimit, 2, 1,
          TgMobiusResidueSeed::k235,
          TgMobiusRectangularSlotMode::kRect2d512,
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          1, kTgMobiusMultiblockMaximumCount + 1, 1,
          TgMobiusResidueSeed::k235,
          TgMobiusRectangularSlotMode::kRect2d512,
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          1, 1, kTgMobiusMultiblockDensePrimeLimit + 1,
          TgMobiusResidueSeed::k235,
          TgMobiusRectangularSlotMode::kRect2d512,
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          1, 1, 1, static_cast<TgMobiusResidueSeed>(0),
          TgMobiusRectangularSlotMode::kRect2d512,
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          1, 1, 1, TgMobiusResidueSeed::k235,
          static_cast<TgMobiusRectangularSlotMode>(0),
          &rectangular_geometry) != cudaErrorInvalidValue ||
      tg_mobius_rectangular_launch_geometry_qualification(
          1, 1, 1, TgMobiusResidueSeed::k235,
          TgMobiusRectangularSlotMode::kRect2d512,
          nullptr) != cudaErrorInvalidValue) {
    fail("rectangular geometry fail-closed guard KAT failed");
  }
  const std::uint64_t encoded =
      pack(kTgMobiusPrimorial13, 13, true);
  if ((encoded & kTgMobiusFusedProductMask) !=
          kTgMobiusPrimorial13 ||
      ((encoded & kTgMobiusFusedCountMask) >>
       kTgMobiusFusedCountShift) != 13 ||
      (encoded & kTgMobiusFusedSquarefulBit) == 0 ||
      (encoded &
       (kTgMobiusFusedReservedMask |
        kTgMobiusFusedPoisonBit)) != 0) {
    fail("fused support host packing KAT failed");
  }
  if (!(kTgMobiusPrimorial13 <= kTgMobiusSourceLimit &&
        kTgMobiusSourceLimit < kTgMobiusPrimorial14 &&
        kTgMobiusSourceLimit <
            (std::uint64_t{1} << kTgMobiusFusedProductBits))) {
    fail("fused support source bounds changed");
  }

  // These calls must reject before dereferencing the nonnull sentinels or
  // attempting a CUDA launch.  They exercise the public launch API rather
  // than the runner's independent command-line range validation.
  auto* support = reinterpret_cast<TgMobiusFusedSupport*>(
      static_cast<std::uintptr_t>(0x1'000));
  auto* device_prime_sentinel = reinterpret_cast<std::uint32_t*>(
      static_cast<std::uintptr_t>(0x2'000));
  auto* mobius = reinterpret_cast<std::int8_t*>(
      static_cast<std::uintptr_t>(0x3'000));
  auto* prefix = reinterpret_cast<TgMobiusPrefixMQ*>(
      static_cast<std::uintptr_t>(0x4'000));
  auto* poison = reinterpret_cast<std::uint32_t*>(
      static_cast<std::uintptr_t>(0x5'000));
  if (launch_tg_mobius_fused_segment(
          kTgMobiusSourceLimit + 1, 1, nullptr, 0, 0,
          support, mobius) != cudaErrorInvalidValue) {
    fail("fused launch accepted lower above the source limit");
  }
  if (launch_tg_mobius_fused_segment(
          kTgMobiusSourceLimit, 2, nullptr, 0, 0,
          support, mobius) != cudaErrorInvalidValue) {
    fail("fused launch accepted a segment crossing the source limit");
  }
  if (launch_tg_mobius_fused_segment_multiblock_dense(
          kTgMobiusSourceLimit, 2, nullptr, 0, 0,
          support, mobius) != cudaErrorInvalidValue) {
    fail(
        "multiblock fused launch accepted a segment "
        "crossing the source limit");
  }
  if (launch_tg_mobius_fused_segment_multiblock_dense(
          1, kTgMobiusMultiblockMaximumCount + 1,
          nullptr, 0, 0, support, mobius) !=
      cudaErrorInvalidValue) {
    fail("multiblock fused launch accepted a count above its schedule bound");
  }
  if (launch_tg_mobius_fused_segment_multiblock_dense_residue_235(
          1, 1, nullptr, 0, 0, support, mobius) !=
      cudaErrorInvalidValue) {
    fail("residue-235 fused launch accepted a roster shorter than [2,3,5]");
  }
  if (launch_tg_mobius_fused_support_multiblock_dense_residue_235(
          1, 1, nullptr, 0, 0, support) !=
      cudaErrorInvalidValue) {
    fail(
        "residue-235 support-only launch accepted a roster "
        "shorter than [2,3,5]");
  }
  if (
      launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
          1, 1, nullptr, 0, 0, support, poison) !=
      cudaErrorInvalidValue) {
    fail(
        "residue-235 split-square launch accepted a roster "
        "shorter than [2,3,5]");
  }
  if (
      launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
          1, 1, device_prime_sentinel, 3, 0, support, nullptr) !=
      cudaErrorInvalidValue) {
    fail(
        "residue-235 split-square launch accepted null "
        "roster-invalid storage");
  }
  if (
      launch_tg_mobius_fused_support_multiblock_dense_residue_2357_qualification(
          1, 1, device_prime_sentinel, 3, 0, support, poison) !=
      cudaErrorInvalidValue) {
    fail(
        "residue-2357 qualification launch accepted a roster "
        "shorter than [2,3,5,7]");
  }
  if (
      launch_tg_mobius_fused_segment_multiblock_dense_residue_2357_qualification(
          1, 1, device_prime_sentinel, 4, 0, support, mobius,
          nullptr) != cudaErrorInvalidValue) {
    fail(
        "residue-2357 finalized qualification launch accepted null "
        "roster-invalid storage");
  }
  if (
      launch_tg_mobius_fused_support_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 4, 0, support, poison) !=
      cudaErrorInvalidValue) {
    fail(
        "residue-235711 qualification launch accepted a roster "
        "shorter than [2,3,5,7,11]");
  }
  if (
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 5, 0, support, mobius,
          nullptr) != cudaErrorInvalidValue) {
    fail(
        "residue-235711 finalized qualification launch accepted null "
        "roster-invalid storage");
  }
  if (
      launch_tg_mobius_fused_support_multiblock_dense_residue_rectangular_qualification(
          1, 1, device_prime_sentinel, 4, 0,
          TgMobiusResidueSeed::k235711,
          TgMobiusRectangularSlotMode::kRect2d512,
          support, poison, &rectangular_geometry) !=
      cudaErrorInvalidValue) {
    fail(
        "rectangular residue-235711 launch accepted a short seed roster");
  }
  if (
      launch_tg_mobius_fused_support_multiblock_dense_residue_rectangular_qualification(
          1, 1, device_prime_sentinel, 5, 0,
          TgMobiusResidueSeed::k235711,
          TgMobiusRectangularSlotMode::kRect2d512,
          support, poison, nullptr) != cudaErrorInvalidValue) {
    fail("rectangular launch accepted null geometry storage");
  }
  auto* support_as_primes =
      reinterpret_cast<std::uint32_t*>(support);
  auto* support_as_mobius =
      reinterpret_cast<std::int8_t*>(support);
  auto* support_as_roster_status =
      reinterpret_cast<std::uint32_t*>(support);
  auto* mobius_as_roster_status =
      reinterpret_cast<std::uint32_t*>(mobius);
  if (
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, support_as_primes, 5, 0, support, mobius,
          poison) != cudaErrorInvalidValue ||
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 5, 0, support,
          reinterpret_cast<std::int8_t*>(device_prime_sentinel),
          poison) != cudaErrorInvalidValue ||
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 5, 0, support, mobius,
          device_prime_sentinel) != cudaErrorInvalidValue ||
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 5, 0, support,
          support_as_mobius, poison) != cudaErrorInvalidValue ||
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 5, 0, support, mobius,
          support_as_roster_status) != cudaErrorInvalidValue ||
      launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
          1, 1, device_prime_sentinel, 5, 0, support, mobius,
          mobius_as_roster_status) != cudaErrorInvalidValue) {
    fail("fused qualification API accepted overlapping device buffers");
  }
  if (launch_tg_mobius_fused_prefix_inputs(
          kTgMobiusSourceLimit, support, 2, prefix, poison) !=
      cudaErrorInvalidValue) {
    fail("direct fused prefix finalizer crossed the source limit");
  }

  const std::vector<std::uint32_t> first_thirteen_primes{
      2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41};
  run_device_case(1, {}, 1, 0, false, 1, false);
  run_device_case(202, {2}, 2, 1, false, 1, false);
  run_device_case(8, {2}, 2, 1, true, 0, false);
  run_device_case(49, {7}, 7, 1, true, 0, false);
  run_device_case(
      kTgMobiusPrimorial13, first_thirteen_primes,
      kTgMobiusPrimorial13, 13, false, -1, false);
  run_device_case(
      2 * kTgMobiusPrimorial13, first_thirteen_primes,
      kTgMobiusPrimorial13, 13, true, 0, false);
  // Deliberately violate the distinct-prime roster contract.  The fourteenth
  // duplicate divisor must poison the word and emit the non-Möbius sentinel.
  run_device_case(
      2, std::vector<std::uint32_t>(14, 2),
      std::uint64_t{1} << 13, 13, false, 2, true);
  // Direct word cases expose the exact mod-121 branch:
  // 121 and 1210 require the 11^2 squareful bit, while 2310 exercises the
  // maximum five-prime seed product/count without that bit.
  run_seed11_word_case(121, 11, 1, true, 0);
  run_seed11_word_case(1'210, 110, 3, true, 0);
  run_seed11_word_case(2'310, 2'310, 5, false, -1);
  run_range_comparison(1, 8'192);
  run_range_comparison(438'420, 4'097);
  // The suffix has more than 200 primes here and the interval contains
  // square multiples from both sides of the split-square schedule boundary.
  // sqrt(1,585,535)=1259 and pi(1259)=205.  After the four-prime
  // residue-2357 seed this leaves 201 suffix primes, so the candidate's
  // square schedule necessarily executes both its 200-prime dense side and
  // its sparse side.  The interval contains 1253^2 and 1259^2.
  run_range_comparison(1'520'000, 65'536);
  run_split_square_malformed_roster_case({2, 3, 7});
  run_split_square_malformed_roster_case({2, 3, 5, 0});
  run_split_square_malformed_roster_case({2, 3, 5, 11, 7});
  run_split_square_malformed_roster_case(
      {2, 3, 5, kTgMobiusMaximumPrime + 1});
  run_split_square_malformed_roster_case(
      {2, 3, 5, 11}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 0}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 8}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 9}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 10}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 13, 11}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 7}, SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, kTgMobiusMaximumPrime + 1},
      SplitSquareSeedMode::kResidue2357);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 13}, SplitSquareSeedMode::kResidue235711);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 0}, SplitSquareSeedMode::kResidue235711);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 11, 0}, SplitSquareSeedMode::kResidue235711);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 11, 12}, SplitSquareSeedMode::kResidue235711);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 11, 17, 13},
      SplitSquareSeedMode::kResidue235711);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 11, 11}, SplitSquareSeedMode::kResidue235711);
  run_split_square_malformed_roster_case(
      {2, 3, 5, 7, 11, kTgMobiusMaximumPrime + 1},
      SplitSquareSeedMode::kResidue235711);

  std::cout
      << "fused support residue-235/2357/235711 packing, preflight, "
         "and API-bound KAT passed\n";
  return 0;
}

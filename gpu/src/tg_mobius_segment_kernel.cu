// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_mobius_segment.h"
#include "sparkinterval/tg_mobius_affine_candidate_order.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>

#include <cub/block/block_scan.cuh>
#include <cub/device/device_scan.cuh>
#include <cuda_runtime.h>

namespace {

constexpr unsigned int kThreadsPerBlock =
    static_cast<unsigned int>(kTgMobiusThreadsPerBlock);
constexpr std::size_t kMaximumGridX = 0x7fffffffULL;
constexpr std::size_t kAffineRowsPerThread =
    kTgMobiusAffineRowsPerThread;
constexpr std::size_t kAffineRowsPerBlock =
    kTgMobiusAffineRowsPerBlock;
constexpr std::uint64_t kAffineSquarefreeThreshold = 438'429;
constexpr std::uint64_t kAffineSourceLimit = 10'000'000'000'000'000ULL;
constexpr std::uint64_t kAffineDensityDenominator =
    1'000'000'000'000'000'000ULL;
constexpr std::uint64_t kAffineDensityLower =
    607'927'101'854'026'628ULL;
constexpr std::uint64_t kAffineDensityUpper =
    607'927'101'854'026'629ULL;
constexpr std::uint64_t kAffineSquarefreeNumerator = 57;
constexpr std::uint64_t kAffineSquarefreeDenominator = 2'000;
constexpr std::uint64_t kUnsigned64Maximum =
    18'446'744'073'709'551'615ULL;
constexpr std::size_t kMaximumAffineSourceCount = 100'000'000;

constexpr std::uint64_t residue_235_support(std::size_t residue) {
  std::uint64_t product = 1;
  std::uint32_t distinct_count = 0;
  bool squareful = false;
  for (const std::uint64_t prime : {2ULL, 3ULL, 5ULL}) {
    if (residue % prime != 0) continue;
    product *= prime;
    ++distinct_count;
    squareful = squareful || residue % (prime * prime) == 0;
  }
  return product |
         (static_cast<std::uint64_t>(distinct_count)
          << kTgMobiusFusedCountShift) |
         (squareful ? kTgMobiusFusedSquarefulBit : 0);
}

struct Residue235Table {
  std::uint64_t values[kTgMobiusResidue235Modulus]{};

  __host__ __device__ constexpr std::uint64_t
  operator[](std::size_t index) const {
    return values[index];
  }
};

constexpr Residue235Table make_residue_235_table() {
  Residue235Table table{};
  for (std::size_t residue = 0;
       residue < kTgMobiusResidue235Modulus; ++residue) {
    table.values[residue] = residue_235_support(residue);
  }
  return table;
}

constexpr auto kResidue235Table = make_residue_235_table();
static_assert(kResidue235Table[1] == 1);
static_assert(
    (kResidue235Table[0] & kTgMobiusFusedProductMask) == 30);
static_assert(
    ((kResidue235Table[0] & kTgMobiusFusedCountMask) >>
     kTgMobiusFusedCountShift) == 3);
static_assert(
    (kResidue235Table[0] & kTgMobiusFusedSquarefulBit) != 0);
static_assert(
    (kResidue235Table[30] & kTgMobiusFusedSquarefulBit) == 0);

// The same constexpr generator initializes both the host-audited object and
// a read-only device-global image in the fat binary.  CUDA module loading
// materializes this 7,200-byte image once per context; there is no per-segment
// host-to-device table copy.
__device__ const Residue235Table g_tg_mobius_residue_235_table =
    make_residue_235_table();
std::size_t bounded_multiblock_prime_count(
    std::size_t dense_prime_count) {
  return dense_prime_count < kTgMobiusMultiblockDensePrimeLimit
             ? dense_prime_count
             : kTgMobiusMultiblockDensePrimeLimit;
}

bool residue_seed_parameters(
    TgMobiusResidueSeed seed, std::size_t* seed_prime_count,
    std::uint32_t* suffix_minimum,
    std::size_t* maximum_count_exact_slots) {
  if (seed_prime_count == nullptr || suffix_minimum == nullptr ||
      maximum_count_exact_slots == nullptr) {
    return false;
  }
  switch (seed) {
    case TgMobiusResidueSeed::k235:
      *seed_prime_count = kTgMobiusResidue235PrimeCount;
      *suffix_minimum = 7;
      *maximum_count_exact_slots =
          kTgMobiusResidue235MinimumSlotsPerPrime;
      return true;
    case TgMobiusResidueSeed::k2357:
      *seed_prime_count = kTgMobiusResidue2357PrimeCount;
      *suffix_minimum = kTgMobiusResidue2357SuffixMinimum;
      *maximum_count_exact_slots =
          kTgMobiusResidue2357MinimumSlotsPerPrime;
      return true;
    case TgMobiusResidueSeed::k235711:
      *seed_prime_count = kTgMobiusResidue235711PrimeCount;
      *suffix_minimum = kTgMobiusResidue235711SuffixMinimum;
      *maximum_count_exact_slots =
          kTgMobiusResidue235711MinimumSlotsPerPrime;
      return true;
    case TgMobiusResidueSeed::k23571113:
      *seed_prime_count = kTgMobiusResidue23571113PrimeCount;
      *suffix_minimum = kTgMobiusResidue23571113SuffixMinimum;
      *maximum_count_exact_slots =
          kTgMobiusResidue23571113MinimumSlotsPerPrime;
      return true;
  }
  return false;
}

bool rectangular_slot_count(
    TgMobiusRectangularSlotMode mode, std::size_t required_slots,
    std::size_t maximum_count_exact_slots, std::size_t* slots) {
  if (required_slots == 0 || maximum_count_exact_slots == 0 ||
      slots == nullptr) {
    return false;
  }
  switch (mode) {
    case TgMobiusRectangularSlotMode::kRect2d512:
      *slots = kTgMobiusMultiblockSlotsPerPrime;
      return true;
    case TgMobiusRectangularSlotMode::kRect2dPower: {
      std::size_t power = 1;
      while (power < required_slots &&
             power < kTgMobiusMultiblockSlotsPerPrime) {
        power *= 2;
      }
      *slots = power;
      return true;
    }
    case TgMobiusRectangularSlotMode::kRect2dExact:
      *slots = maximum_count_exact_slots;
      return true;
    case TgMobiusRectangularSlotMode::kRect2dCountExact:
      *slots = required_slots;
      return true;
  }
  return false;
}

__device__ __forceinline__ bool tg_mobius_prime_is_machine_safe(
    std::uint64_t prime) {
  return prime >= 2 && prime <= kTgMobiusMaximumPrime;
}

// This preflight is deliberately structural rather than a second primality
// proof.  Production authenticates the exact canonical roster on the host and
// round-trip checks its device copy.  The device pass closes the asynchronous
// raw-API safety gap: no malformed prefix, below-bound suffix, zero divisor,
// out-of-order entry, or value above the proved p <= 10^8 machine domain can
// reach native arithmetic without first making every initialized support row
// poisonous.
__global__ void validate_split_square_mobius_roster(
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t seeded_prime_count,
    std::uint32_t* roster_invalid) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[index];
  bool malformed = !tg_mobius_prime_is_machine_safe(prime);
  if (index == 0) {
    malformed = malformed || prime != 2;
  } else {
    const std::uint64_t previous = base_primes[index - 1];
    malformed = malformed || prime <= previous;
    if (index == 1) malformed = malformed || prime != 3;
    if (index == 2) malformed = malformed || prime != 5;
    if (seeded_prime_count >= kTgMobiusResidue2357PrimeCount &&
        index == 3) {
      malformed = malformed || prime != 7;
    }
    if (seeded_prime_count >= kTgMobiusResidue235711PrimeCount &&
        index == 4) {
      malformed = malformed || prime != 11;
    }
    if (seeded_prime_count >= kTgMobiusResidue23571113PrimeCount &&
        index == 5) {
      malformed = malformed || prime != 13;
    }
    if (index >= seeded_prime_count) {
      const std::uint32_t suffix_minimum =
          seeded_prime_count >= kTgMobiusResidue23571113PrimeCount
              ? kTgMobiusResidue23571113SuffixMinimum
              : seeded_prime_count >= kTgMobiusResidue235711PrimeCount
              ? kTgMobiusResidue235711SuffixMinimum
              : seeded_prime_count >= kTgMobiusResidue2357PrimeCount
                    ? kTgMobiusResidue2357SuffixMinimum
                    : 7U;
      malformed = malformed || prime < suffix_minimum;
    }
  }
  if (malformed) atomicExch(roster_invalid, 1U);
}

__device__ __forceinline__ void atomic_multiply_exact_divisor(
    std::uint64_t* destination, std::uint32_t prime) {
  auto* target = reinterpret_cast<unsigned long long*>(destination);
  unsigned long long observed = atomicCAS(target, 0ULL, 0ULL);
  for (;;) {
    const unsigned long long assumed = observed;
    // Every intermediate product is a product of distinct divisors of n, so
    // it divides n and cannot overflow the supported source range.
    const unsigned long long desired =
        assumed * static_cast<unsigned long long>(prime);
    observed = atomicCAS(target, assumed, desired);
    if (observed == assumed) return;
  }
}

__global__ void initialize_mobius_support(TgMobiusSupport* outputs,
                                           std::size_t count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  outputs[index].base_prime_product = 1;
  outputs[index].distinct_base_prime_count = 0;
  outputs[index].squareful = 0;
  outputs[index].mobius = 0;
  outputs[index].reserved = 0;
}

__device__ __forceinline__ void mark_one_multiple(
    std::uint64_t lower, std::uint64_t offset, std::uint64_t prime,
    std::uint64_t prime_square,
    TgMobiusSupport* outputs) {
  TgMobiusSupport* record = &outputs[offset];
  atomicAdd(&record->distinct_base_prime_count, 1U);
  atomic_multiply_exact_divisor(&record->base_prime_product,
                                static_cast<std::uint32_t>(prime));
  const std::uint64_t number = lower + offset;
  if (number % prime_square == 0) atomicExch(&record->squareful, 1U);
}

// Small primes have many multiples.  One block owns each such prime and its
// threads partition the multiples, avoiding a serial p=2 bottleneck.
__global__ void mark_dense_prime_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, TgMobiusSupport* outputs) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_prime_square;
  __shared__ std::uint64_t shared_first_offset;
  if (threadIdx.x == 0) {
    shared_prime = base_primes[blockIdx.x];
    shared_prime_square = shared_prime * shared_prime;
    const std::uint64_t remainder = lower % shared_prime;
    shared_first_offset =
        remainder == 0 ? 0 : shared_prime - remainder;
  }
  __syncthreads();
  const std::uint64_t prime = shared_prime;
  const std::uint64_t prime_square = shared_prime_square;
  const std::uint64_t first_offset = shared_first_offset;
  const std::uint64_t thread_offset =
      first_offset + static_cast<std::uint64_t>(threadIdx.x) * prime;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime;
  for (std::uint64_t offset = thread_offset; offset < count; offset += stride) {
    mark_one_multiple(lower, offset, prime, prime_square, outputs);
  }
}

// Large primes have fewer than one block's worth of multiples.  One thread
// per prime avoids launching hundreds of idle threads for each sparse row.
__global__ void mark_sparse_prime_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t first_prime_index,
    std::size_t base_prime_count, TgMobiusSupport* outputs) {
  const std::size_t prime_index =
      first_prime_index +
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (prime_index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[prime_index];
  const std::uint64_t prime_square = prime * prime;
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
  for (std::uint64_t offset = first_offset; offset < count; offset += prime) {
    mark_one_multiple(lower, offset, prime, prime_square, outputs);
  }
}

__global__ void finalize_mobius_support(std::uint64_t lower,
                                        std::size_t count,
                                        TgMobiusSupport* outputs) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t number = lower + index;
  TgMobiusSupport* record = &outputs[index];
  if (record->squareful != 0) {
    record->mobius = 0;
    record->reserved = 0;
    return;
  }
  const std::uint64_t residual = number / record->base_prime_product;
  const std::uint32_t omega = record->distinct_base_prime_count +
                              static_cast<std::uint32_t>(residual > 1);
  record->mobius = (omega & 1U) == 0 ? 1 : -1;
  record->reserved = 0;
}

__global__ void pack_mobius_values(const TgMobiusSupport* inputs,
                                   std::size_t count,
                                   std::int8_t* outputs) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  outputs[index] = static_cast<std::int8_t>(inputs[index].mobius);
}

__global__ void initialize_compact_mobius_support(
    TgMobiusCompactSupport* supports, std::size_t count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  supports[index].base_prime_product = 1;
  supports[index].packed_count_squareful = 0;
  supports[index].reserved = 0;
}

__device__ __forceinline__ void mark_one_compact_multiple(
    std::uint64_t lower, std::uint64_t offset, std::uint64_t prime,
    std::uint64_t prime_square,
    TgMobiusCompactSupport* supports) {
  TgMobiusCompactSupport* record = &supports[offset];
  atomicAdd(&record->packed_count_squareful, 1U);
  atomic_multiply_exact_divisor(&record->base_prime_product,
                                static_cast<std::uint32_t>(prime));
  const std::uint64_t number = lower + offset;
  if (number % prime_square == 0) {
    atomicOr(&record->packed_count_squareful, 0x80000000U);
  }
}

__global__ void mark_dense_prime_compact_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusCompactSupport* supports) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_prime_square;
  __shared__ std::uint64_t shared_first_offset;
  if (threadIdx.x == 0) {
    shared_prime = base_primes[blockIdx.x];
    shared_prime_square = shared_prime * shared_prime;
    const std::uint64_t remainder = lower % shared_prime;
    shared_first_offset =
        remainder == 0 ? 0 : shared_prime - remainder;
  }
  __syncthreads();
  const std::uint64_t prime = shared_prime;
  const std::uint64_t prime_square = shared_prime_square;
  const std::uint64_t first_offset = shared_first_offset;
  const std::uint64_t thread_offset =
      first_offset + static_cast<std::uint64_t>(threadIdx.x) * prime;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime;
  for (std::uint64_t offset = thread_offset; offset < count;
       offset += stride) {
    mark_one_compact_multiple(
        lower, offset, prime, prime_square, supports);
  }
}

__global__ void mark_sparse_prime_compact_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t first_prime_index,
    std::size_t base_prime_count,
    TgMobiusCompactSupport* supports) {
  const std::size_t prime_index =
      first_prime_index +
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (prime_index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[prime_index];
  const std::uint64_t prime_square = prime * prime;
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
  for (std::uint64_t offset = first_offset; offset < count;
       offset += prime) {
    mark_one_compact_multiple(
        lower, offset, prime, prime_square, supports);
  }
}

__global__ void finalize_compact_mobius_support(
    std::uint64_t lower, std::size_t count,
    TgMobiusCompactSupport* supports, std::int8_t* mobius) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t number = lower + index;
  TgMobiusCompactSupport* record = &supports[index];
  const std::uint32_t packed = record->packed_count_squareful;
  if ((packed & 0x80000000U) != 0) {
    mobius[index] = 0;
    record->reserved = 0;
    return;
  }
  const std::uint64_t residual = number / record->base_prime_product;
  const std::uint32_t omega =
      (packed & 0x7fffffffU) +
      static_cast<std::uint32_t>(residual > 1);
  mobius[index] = static_cast<std::int8_t>(
      (omega & 1U) == 0 ? 1 : -1);
  record->reserved = 0;
}

__global__ void initialize_fused_mobius_support(
    TgMobiusFusedSupport* supports, std::size_t count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  supports[index].packed = 1;
}

template <bool IncludeSeven, bool IncludeEleven, bool IncludeThirteen>
__global__ void initialize_fused_mobius_support_residue_235(
    std::uint64_t lower, TgMobiusFusedSupport* supports,
    std::size_t count, const std::uint32_t* roster_invalid) {
  static_assert(!IncludeEleven || IncludeSeven);
  static_assert(!IncludeThirteen || IncludeEleven);
  __shared__ std::uint32_t block_first_residue;
  __shared__ std::uint32_t block_first_residue_49;
  __shared__ std::uint32_t block_first_residue_121;
  __shared__ std::uint32_t block_first_residue_169;
  __shared__ std::uint32_t block_roster_invalid;
  if (threadIdx.x == 0) {
    const std::uint64_t block_first_number =
        lower + static_cast<std::uint64_t>(blockIdx.x) * blockDim.x;
    block_first_residue = static_cast<std::uint32_t>(
        block_first_number % kTgMobiusResidue235Modulus);
    if constexpr (IncludeSeven) {
      block_first_residue_49 = static_cast<std::uint32_t>(
          block_first_number % kTgMobiusResidue2357Modulus);
    }
    if constexpr (IncludeEleven) {
      block_first_residue_121 = static_cast<std::uint32_t>(
          block_first_number % kTgMobiusResidue235711Modulus);
    }
    if constexpr (IncludeThirteen) {
      block_first_residue_169 = static_cast<std::uint32_t>(
          block_first_number % kTgMobiusResidue23571113Modulus);
    }
    block_roster_invalid =
        roster_invalid == nullptr ? 0U : *roster_invalid;
  }
  __syncthreads();
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  std::uint32_t residue = block_first_residue + threadIdx.x;
  if (residue >= kTgMobiusResidue235Modulus) {
    residue -= kTgMobiusResidue235Modulus;
  }
  std::uint64_t packed = g_tg_mobius_residue_235_table[residue];
  if constexpr (IncludeSeven) {
    // The row-local residue identity and exact p=7 update are formalized in
    // SparkInterval/TernaryGoldbach/MobiusResidue2357.lean.
    const std::uint32_t residue_49 =
        (block_first_residue_49 + threadIdx.x) %
        kTgMobiusResidue2357Modulus;
    if (residue_49 % 7 == 0) {
      const std::uint64_t product =
          (packed & kTgMobiusFusedProductMask) * 7;
      const std::uint64_t distinct_count =
          ((packed & kTgMobiusFusedCountMask) >>
           kTgMobiusFusedCountShift) + 1;
      packed =
          product |
          (distinct_count << kTgMobiusFusedCountShift) |
          (packed & kTgMobiusFusedSquarefulBit);
      if (residue_49 == 0) {
        packed |= kTgMobiusFusedSquarefulBit;
      }
    }
  }
  if constexpr (IncludeEleven) {
    // Lean cross-check:
    //   blockLocalResidue121_eq_sourceNumber_mod,
    //   blockLocalResidue121_mod_eleven_eq_zero_iff,
    //   blockLocalResidue121_eq_zero_iff, and
    //   applyEleven_mod121_eq
    // in SparkInterval/TernaryGoldbach/MobiusResidue235711.lean.
    // In particular, residue==0 (not merely residue%11==0) is exactly the
    // 11^2 test.  No divisibility inference is made from a reduced mod-11
    // value.
    const std::uint32_t residue_121 =
        (block_first_residue_121 + threadIdx.x) %
        kTgMobiusResidue235711Modulus;
    if (residue_121 % 11 == 0) {
      const std::uint64_t product =
          (packed & kTgMobiusFusedProductMask) * 11;
      const std::uint64_t distinct_count =
          ((packed & kTgMobiusFusedCountMask) >>
           kTgMobiusFusedCountShift) + 1;
      packed =
          product |
          (distinct_count << kTgMobiusFusedCountShift) |
          (packed & kTgMobiusFusedSquarefulBit);
      if (residue_121 == 0) {
        packed |= kTgMobiusFusedSquarefulBit;
      }
    }
  }
  if constexpr (IncludeThirteen) {
    const std::uint32_t residue_169 =
        (block_first_residue_169 + threadIdx.x) %
        kTgMobiusResidue23571113Modulus;
    if (residue_169 % 13 == 0) {
      const std::uint64_t product =
          (packed & kTgMobiusFusedProductMask) * 13;
      const std::uint64_t distinct_count =
          ((packed & kTgMobiusFusedCountMask) >>
           kTgMobiusFusedCountShift) + 1;
      packed =
          product |
          (distinct_count << kTgMobiusFusedCountShift) |
          (packed & kTgMobiusFusedSquarefulBit);
      if (residue_169 == 0) {
        packed |= kTgMobiusFusedSquarefulBit;
      }
    }
  }
  supports[index].packed =
      packed |
      (block_roster_invalid != 0 ? kTgMobiusFusedPoisonBit : 0);
}

__device__ __forceinline__ void mark_one_fused_multiple(
    std::uint64_t lower, std::uint64_t offset, std::uint64_t prime,
    std::uint64_t prime_square, std::uint64_t maximum_product,
    TgMobiusFusedSupport* supports) {
  auto* target = reinterpret_cast<unsigned long long*>(
      &supports[offset].packed);
  const std::uint64_t number = lower + offset;
  const bool squareful = number % prime_square == 0;
  unsigned long long observed = atomicCAS(target, 0ULL, 0ULL);
  for (;;) {
    const std::uint64_t assumed = observed;
    if ((assumed & kTgMobiusFusedPoisonBit) != 0) return;
    const std::uint64_t product =
        assumed & kTgMobiusFusedProductMask;
    const std::uint32_t distinct_count = static_cast<std::uint32_t>(
        (assumed & kTgMobiusFusedCountMask) >>
        kTgMobiusFusedCountShift);
    const bool malformed =
        (assumed & kTgMobiusFusedReservedMask) != 0 ||
        product == 0 ||
        distinct_count >= kTgMobiusFusedMaximumDistinctPrimes ||
        prime < 2 ||
        product > maximum_product;
    std::uint64_t desired = assumed | kTgMobiusFusedPoisonBit;
    if (!malformed) {
      const std::uint64_t next_product = product * prime;
      const std::uint64_t next_count =
          static_cast<std::uint64_t>(distinct_count + 1);
      desired =
          next_product |
          (next_count << kTgMobiusFusedCountShift) |
          (assumed & kTgMobiusFusedSquarefulBit) |
          (squareful ? kTgMobiusFusedSquarefulBit : 0);
    }
    observed = atomicCAS(target, assumed, desired);
    if (observed == assumed) return;
  }
}

__global__ void mark_dense_prime_fused_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusFusedSupport* supports) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_prime_square;
  __shared__ std::uint64_t shared_maximum_product;
  __shared__ std::uint64_t shared_first_offset;
  __shared__ bool shared_prime_valid;
  if (threadIdx.x == 0) {
    shared_prime = base_primes[blockIdx.x];
    shared_prime_valid =
        tg_mobius_prime_is_machine_safe(shared_prime);
    if (shared_prime_valid) {
      shared_prime_square = shared_prime * shared_prime;
      shared_maximum_product =
          kTgMobiusFusedProductMask / shared_prime;
      const std::uint64_t remainder = lower % shared_prime;
      shared_first_offset =
          remainder == 0 ? 0 : shared_prime - remainder;
    }
  }
  __syncthreads();
  if (!shared_prime_valid) return;
  const std::uint64_t prime = shared_prime;
  const std::uint64_t prime_square = shared_prime_square;
  const std::uint64_t maximum_product = shared_maximum_product;
  const std::uint64_t first_offset = shared_first_offset;
  const std::uint64_t thread_offset =
      first_offset + static_cast<std::uint64_t>(threadIdx.x) * prime;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime;
  for (std::uint64_t offset = thread_offset; offset < count;
       offset += stride) {
    mark_one_fused_multiple(
        lower, offset, prime, prime_square, maximum_product, supports);
  }
}

template <std::size_t BlockSlotsPerDensePrime>
__global__ void mark_dense_prime_fused_support_multiblock(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusFusedSupport* supports) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_prime_square;
  __shared__ std::uint64_t shared_maximum_product;
  __shared__ std::uint64_t shared_first_offset;
  __shared__ std::uint64_t shared_event_begin;
  __shared__ std::uint64_t shared_event_end;
  __shared__ bool shared_prime_valid;
  const std::size_t prime_index =
      static_cast<std::size_t>(blockIdx.x) /
      BlockSlotsPerDensePrime;
  const std::size_t block_ordinal =
      static_cast<std::size_t>(blockIdx.x) %
      BlockSlotsPerDensePrime;
  if (threadIdx.x == 0) {
    shared_prime = base_primes[prime_index];
    shared_prime_valid =
        tg_mobius_prime_is_machine_safe(shared_prime);
    if (shared_prime_valid) {
      shared_prime_square = shared_prime * shared_prime;
      shared_maximum_product =
          kTgMobiusFusedProductMask / shared_prime;
      const std::uint64_t remainder = lower % shared_prime;
      shared_first_offset =
          remainder == 0 ? 0 : shared_prime - remainder;
      const std::uint64_t multiple_count =
          shared_first_offset >= count
              ? 0
              : 1 + (count - 1 - shared_first_offset) / shared_prime;
      shared_event_begin =
          static_cast<std::uint64_t>(block_ordinal) *
          kTgMobiusMultipleEventsPerBlock;
      const std::uint64_t proposed_end =
          shared_event_begin + kTgMobiusMultipleEventsPerBlock;
      shared_event_end =
          proposed_end < multiple_count
              ? proposed_end
              : multiple_count;
    }
  }
  __syncthreads();
  if (!shared_prime_valid) return;
  if (shared_event_begin >= shared_event_end) return;
  const std::uint64_t prime = shared_prime;
  const std::uint64_t prime_square = shared_prime_square;
  const std::uint64_t maximum_product = shared_maximum_product;
  const std::uint64_t first_offset = shared_first_offset;
  for (std::uint64_t event =
           shared_event_begin + threadIdx.x;
       event < shared_event_end; event += blockDim.x) {
    const std::uint64_t offset = first_offset + event * prime;
    mark_one_fused_multiple(
        lower, offset, prime, prime_square, maximum_product, supports);
  }
}

__global__ void mark_sparse_prime_fused_support(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t first_prime_index,
    std::size_t base_prime_count,
    TgMobiusFusedSupport* supports) {
  const std::size_t prime_index =
      first_prime_index +
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (prime_index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[prime_index];
  if (!tg_mobius_prime_is_machine_safe(prime)) return;
  const std::uint64_t prime_square = prime * prime;
  const std::uint64_t maximum_product =
      kTgMobiusFusedProductMask / prime;
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
  for (std::uint64_t offset = first_offset; offset < count;
       offset += prime) {
    mark_one_fused_multiple(
        lower, offset, prime, prime_square, maximum_product, supports);
  }
}

// Production divisor update for the split-square schedule.  One event exists
// for each selected suffix prime p and each row n divisible by p.  The update
// deliberately does not evaluate n mod p^2.  All squareful bits are installed
// by the later square-strike kernels after these CAS kernels complete.
__device__ __forceinline__ void mark_one_fused_distinct_divisor(
    std::uint64_t offset, std::uint64_t prime,
    std::uint64_t maximum_product,
    TgMobiusFusedSupport* supports) {
  auto* target = reinterpret_cast<unsigned long long*>(
      &supports[offset].packed);
  unsigned long long observed = atomicCAS(target, 0ULL, 0ULL);
  for (;;) {
    const std::uint64_t assumed = observed;
    if ((assumed & kTgMobiusFusedPoisonBit) != 0) return;
    const std::uint64_t product =
        assumed & kTgMobiusFusedProductMask;
    const std::uint32_t distinct_count = static_cast<std::uint32_t>(
        (assumed & kTgMobiusFusedCountMask) >>
        kTgMobiusFusedCountShift);
    const bool malformed =
        (assumed & kTgMobiusFusedReservedMask) != 0 ||
        product == 0 ||
        distinct_count >= kTgMobiusFusedMaximumDistinctPrimes ||
        prime < 2 ||
        product > maximum_product;
    std::uint64_t desired = assumed | kTgMobiusFusedPoisonBit;
    if (!malformed) {
      const std::uint64_t next_product = product * prime;
      const std::uint64_t next_count =
          static_cast<std::uint64_t>(distinct_count + 1);
      desired =
          next_product |
          (next_count << kTgMobiusFusedCountShift) |
          (assumed & kTgMobiusFusedSquarefulBit);
    }
    observed = atomicCAS(target, assumed, desired);
    if (observed == assumed) return;
  }
}

__global__ void mark_dense_prime_fused_distinct_divisors(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusFusedSupport* supports) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_maximum_product;
  __shared__ std::uint64_t shared_first_offset;
  __shared__ bool shared_prime_valid;
  if (threadIdx.x == 0) {
    shared_prime = base_primes[blockIdx.x];
    shared_prime_valid =
        tg_mobius_prime_is_machine_safe(shared_prime);
    if (shared_prime_valid) {
      shared_maximum_product =
          kTgMobiusFusedProductMask / shared_prime;
      const std::uint64_t remainder = lower % shared_prime;
      shared_first_offset =
          remainder == 0 ? 0 : shared_prime - remainder;
    }
  }
  __syncthreads();
  if (!shared_prime_valid) return;
  const std::uint64_t prime = shared_prime;
  const std::uint64_t maximum_product = shared_maximum_product;
  const std::uint64_t first_offset = shared_first_offset;
  const std::uint64_t thread_offset =
      first_offset + static_cast<std::uint64_t>(threadIdx.x) * prime;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime;
  for (std::uint64_t offset = thread_offset; offset < count;
       offset += stride) {
    mark_one_fused_distinct_divisor(
        offset, prime, maximum_product, supports);
  }
}

template <std::size_t BlockSlotsPerDensePrime>
__global__ void mark_dense_prime_fused_distinct_divisors_multiblock(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusFusedSupport* supports) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_maximum_product;
  __shared__ std::uint64_t shared_first_offset;
  __shared__ std::uint64_t shared_event_begin;
  __shared__ std::uint64_t shared_event_end;
  __shared__ bool shared_prime_valid;
  const std::size_t prime_index =
      static_cast<std::size_t>(blockIdx.x) /
      BlockSlotsPerDensePrime;
  const std::size_t block_ordinal =
      static_cast<std::size_t>(blockIdx.x) %
      BlockSlotsPerDensePrime;
  if (threadIdx.x == 0) {
    shared_prime = base_primes[prime_index];
    shared_prime_valid =
        tg_mobius_prime_is_machine_safe(shared_prime);
    if (shared_prime_valid) {
      shared_maximum_product =
          kTgMobiusFusedProductMask / shared_prime;
      const std::uint64_t remainder = lower % shared_prime;
      shared_first_offset =
          remainder == 0 ? 0 : shared_prime - remainder;
      const std::uint64_t multiple_count =
          shared_first_offset >= count
              ? 0
              : 1 + (count - 1 - shared_first_offset) / shared_prime;
      shared_event_begin =
          static_cast<std::uint64_t>(block_ordinal) *
          kTgMobiusMultipleEventsPerBlock;
      const std::uint64_t proposed_end =
          shared_event_begin + kTgMobiusMultipleEventsPerBlock;
      shared_event_end =
          proposed_end < multiple_count
              ? proposed_end
              : multiple_count;
    }
  }
  __syncthreads();
  if (!shared_prime_valid) return;
  if (shared_event_begin >= shared_event_end) return;
  const std::uint64_t prime = shared_prime;
  const std::uint64_t maximum_product = shared_maximum_product;
  const std::uint64_t first_offset = shared_first_offset;
  for (std::uint64_t event =
           shared_event_begin + threadIdx.x;
       event < shared_event_end; event += blockDim.x) {
    const std::uint64_t offset = first_offset + event * prime;
    mark_one_fused_distinct_divisor(
        offset, prime, maximum_product, supports);
  }
}

// Qualification-only rectangular realization of the same event partition.
// SparkInterval/TernaryGoldbach/MobiusRectangularCUDASchedule.lean proves
// ownership for arbitrary positive slot width:
//   prime_index = blockIdx.y, block_ordinal = blockIdx.x.
// The host witness records and guards both dimensions before this kernel is
// launched.  No production entry point selects this mapping.
__global__ void
mark_dense_prime_fused_distinct_divisors_multiblock_rectangular(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusFusedSupport* supports) {
  __shared__ std::uint64_t shared_prime;
  __shared__ std::uint64_t shared_maximum_product;
  __shared__ std::uint64_t shared_first_offset;
  __shared__ std::uint64_t shared_event_begin;
  __shared__ std::uint64_t shared_event_end;
  __shared__ bool shared_prime_valid;
  const std::size_t prime_index =
      static_cast<std::size_t>(blockIdx.y);
  const std::size_t block_ordinal =
      static_cast<std::size_t>(blockIdx.x);
  if (threadIdx.x == 0) {
    shared_prime = base_primes[prime_index];
    shared_prime_valid =
        tg_mobius_prime_is_machine_safe(shared_prime);
    if (shared_prime_valid) {
      shared_maximum_product =
          kTgMobiusFusedProductMask / shared_prime;
      const std::uint64_t remainder = lower % shared_prime;
      shared_first_offset =
          remainder == 0 ? 0 : shared_prime - remainder;
      const std::uint64_t multiple_count =
          shared_first_offset >= count
              ? 0
              : 1 + (count - 1 - shared_first_offset) / shared_prime;
      shared_event_begin =
          static_cast<std::uint64_t>(block_ordinal) *
          kTgMobiusMultipleEventsPerBlock;
      const std::uint64_t proposed_end =
          shared_event_begin + kTgMobiusMultipleEventsPerBlock;
      shared_event_end =
          proposed_end < multiple_count
              ? proposed_end
              : multiple_count;
    }
  }
  __syncthreads();
  if (!shared_prime_valid ||
      shared_event_begin >= shared_event_end) {
    return;
  }
  const std::uint64_t prime = shared_prime;
  const std::uint64_t maximum_product = shared_maximum_product;
  const std::uint64_t first_offset = shared_first_offset;
  for (std::uint64_t event =
           shared_event_begin + threadIdx.x;
       event < shared_event_end; event += blockDim.x) {
    const std::uint64_t offset = first_offset + event * prime;
    mark_one_fused_distinct_divisor(
        offset, prime, maximum_product, supports);
  }
}

__global__ void mark_sparse_prime_fused_distinct_divisors(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t first_prime_index,
    std::size_t base_prime_count,
    TgMobiusFusedSupport* supports) {
  const std::size_t prime_index =
      first_prime_index +
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (prime_index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[prime_index];
  if (!tg_mobius_prime_is_machine_safe(prime)) return;
  const std::uint64_t maximum_product =
      kTgMobiusFusedProductMask / prime;
  const std::uint64_t remainder = lower % prime;
  const std::uint64_t first_offset =
      remainder == 0 ? 0 : prime - remainder;
  for (std::uint64_t offset = first_offset; offset < count;
       offset += prime) {
    mark_one_fused_distinct_divisor(
        offset, prime, maximum_product, supports);
  }
}

__device__ __forceinline__ void mark_one_fused_squareful(
    std::uint64_t offset, TgMobiusFusedSupport* supports) {
  // The square pass is enqueued only after all distinct-factor CAS kernels in
  // the same stream.  atomicOr is retained both for multiple square divisors
  // of one row and to make the one-way state transition explicit: no product,
  // count, reserved, or poison bit can be cleared.
  auto* target = reinterpret_cast<unsigned long long*>(
      &supports[offset].packed);
  atomicOr(
      target,
      static_cast<unsigned long long>(kTgMobiusFusedSquarefulBit));
}

__device__ __forceinline__ bool first_square_offset(
    std::uint64_t lower, std::size_t count,
    std::uint64_t prime_square, std::uint64_t* offset) {
  if (prime_square == 0) return false;
  const std::uint64_t remainder = lower % prime_square;
  const std::uint64_t first =
      remainder == 0 ? 0 : prime_square - remainder;
  if (first >= count) return false;
  *offset = first;
  return true;
}

// One block per early suffix prime.  Threads enumerate disjoint square
// multiple ordinals, so every (p^2,n) event is visited exactly once.
__global__ void mark_dense_prime_fused_squareful(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes,
    TgMobiusFusedSupport* supports) {
  __shared__ std::uint64_t shared_prime_square;
  __shared__ std::uint64_t shared_first_offset;
  __shared__ bool shared_has_event;
  __shared__ bool shared_prime_valid;
  if (threadIdx.x == 0) {
    const std::uint64_t prime = base_primes[blockIdx.x];
    shared_prime_valid = tg_mobius_prime_is_machine_safe(prime);
    shared_has_event = false;
    if (shared_prime_valid) {
      shared_prime_square = prime * prime;
      shared_has_event = first_square_offset(
          lower, count, shared_prime_square, &shared_first_offset);
    }
  }
  __syncthreads();
  if (!shared_prime_valid) return;
  if (!shared_has_event) return;
  const std::uint64_t prime_square = shared_prime_square;
  const std::uint64_t thread_offset =
      shared_first_offset +
      static_cast<std::uint64_t>(threadIdx.x) * prime_square;
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * prime_square;
  for (std::uint64_t offset = thread_offset; offset < count;
       offset += stride) {
    mark_one_fused_squareful(offset, supports);
  }
}

// One thread per later suffix prime.  The dense/sparse prime-index ranges are
// disjoint, and this thread's ordinal loop has step p^2, so the whole square
// schedule contains neither omissions nor duplicate (p^2,n) events.
__global__ void mark_sparse_prime_fused_squareful(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t first_prime_index,
    std::size_t base_prime_count,
    TgMobiusFusedSupport* supports) {
  const std::size_t prime_index =
      first_prime_index +
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (prime_index >= base_prime_count) return;
  const std::uint64_t prime = base_primes[prime_index];
  if (!tg_mobius_prime_is_machine_safe(prime)) return;
  const std::uint64_t prime_square = prime * prime;
  std::uint64_t first_offset = 0;
  if (!first_square_offset(
          lower, count, prime_square, &first_offset)) {
    return;
  }
  for (std::uint64_t offset = first_offset; offset < count;
       offset += prime_square) {
    mark_one_fused_squareful(offset, supports);
  }
}

__global__ void finalize_fused_mobius_support(
    std::uint64_t lower, std::size_t count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t packed = supports[index].packed;
  const std::uint64_t product =
      packed & kTgMobiusFusedProductMask;
  const std::uint32_t distinct_count = static_cast<std::uint32_t>(
      (packed & kTgMobiusFusedCountMask) >>
      kTgMobiusFusedCountShift);
  const std::uint64_t number = lower + index;
  if ((packed &
       (kTgMobiusFusedReservedMask | kTgMobiusFusedPoisonBit)) != 0 ||
      product == 0 ||
      distinct_count > kTgMobiusFusedMaximumDistinctPrimes ||
      product > number || number % product != 0) {
    // Two is outside the mathematical Möbius codomain.  The runner's
    // independent CPU comparison therefore rejects any poisoned row.
    mobius[index] = 2;
    return;
  }
  if ((packed & kTgMobiusFusedSquarefulBit) != 0) {
    mobius[index] = 0;
    return;
  }
  const std::uint64_t residual = number / product;
  const std::uint32_t omega =
      distinct_count + static_cast<std::uint32_t>(residual > 1);
  mobius[index] = static_cast<std::int8_t>(
      (omega & 1U) == 0 ? 1 : -1);
}

__device__ __forceinline__ TgMobiusPrefixMQ
decode_fused_mobius_prefix_input(
    std::uint64_t lower, std::size_t index,
    const TgMobiusFusedSupport* supports, bool* poisoned) {
  const std::uint64_t packed = supports[index].packed;
  const std::uint64_t product =
      packed & kTgMobiusFusedProductMask;
  const std::uint32_t distinct_count = static_cast<std::uint32_t>(
      (packed & kTgMobiusFusedCountMask) >>
      kTgMobiusFusedCountShift);
  const std::uint64_t number = lower + index;
  *poisoned =
      (packed &
       (kTgMobiusFusedReservedMask | kTgMobiusFusedPoisonBit)) != 0 ||
      product == 0 ||
      distinct_count > kTgMobiusFusedMaximumDistinctPrimes ||
      product > number || number % product != 0;
  if (*poisoned ||
      (packed & kTgMobiusFusedSquarefulBit) != 0) {
    return {0, 0};
  }
  const std::uint64_t residual = number / product;
  const std::uint32_t omega =
      distinct_count + static_cast<std::uint32_t>(residual > 1);
  const std::int32_t mobius = (omega & 1U) == 0 ? 1 : -1;
  return {mobius, 1};
}

__global__ void finalize_fused_mobius_prefix_inputs(
    std::uint64_t lower, std::size_t count,
    const TgMobiusFusedSupport* supports,
    TgMobiusPrefixMQ* prefix_inputs,
    std::uint32_t* poison_count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  bool poisoned = false;
  prefix_inputs[index] = decode_fused_mobius_prefix_input(
      lower, index, supports, &poisoned);
  if (poisoned) atomicAdd(poison_count, 1U);
}

__global__ void count_poisoned_mobius(
    const std::int8_t* mobius, std::size_t count,
    std::uint32_t* poison_count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::int8_t value = mobius[index];
  if (value < -1 || value > 1) atomicAdd(poison_count, 1U);
}

struct AddPrefixMq {
  __host__ __device__ __forceinline__ TgMobiusPrefixMQ operator()(
      const TgMobiusPrefixMQ& left,
      const TgMobiusPrefixMQ& right) const {
    const std::int64_t mertens =
        static_cast<std::int64_t>(left.mertens) + right.mertens;
    const std::uint64_t squarefree =
        static_cast<std::uint64_t>(left.squarefree) + right.squarefree;
    // CUB combines disjoint portions of a source shard containing at most
    // 10^8 rows, so these exact mathematical partial sums fit their fields.
    return {static_cast<std::int32_t>(mertens),
            static_cast<std::uint32_t>(squarefree)};
  }
};

__global__ void initialize_prefix_mq(const std::int8_t* mobius,
                                     std::size_t count,
                                     TgMobiusPrefixMQ* prefixes,
                                     std::uint32_t* poison_count) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::int8_t value = mobius[index];
  if (poison_count != nullptr && (value < -1 || value > 1)) {
    atomicAdd(poison_count, 1U);
  }
  prefixes[index] = {static_cast<std::int32_t>(value),
                     static_cast<std::uint32_t>(value != 0)};
}

__device__ __forceinline__ std::uint64_t floor_sqrt_u64(
    std::uint64_t value) {
  std::uint64_t estimate =
      static_cast<std::uint64_t>(sqrt(static_cast<double>(value)));
  while (estimate != kUnsigned64Maximum &&
         estimate + 1 <= value / (estimate + 1)) {
    ++estimate;
  }
  while (estimate != 0 && estimate > value / estimate) --estimate;
  return estimate;
}

__device__ __forceinline__ std::uint64_t exact_hurst_limit_device(
    std::uint64_t n) {
  const unsigned __int128 radicand =
      static_cast<unsigned __int128>(571) * 571 * n / 1'000'000;
  return floor_sqrt_u64(static_cast<std::uint64_t>(radicand));
}

struct DeviceU256 {
  std::uint64_t limb[4];
};

__device__ __forceinline__ DeviceU256 multiply_u128_device(
    unsigned __int128 left, unsigned __int128 right) {
  const std::uint64_t a[2] = {
      static_cast<std::uint64_t>(left),
      static_cast<std::uint64_t>(left >> 64U)};
  const std::uint64_t b[2] = {
      static_cast<std::uint64_t>(right),
      static_cast<std::uint64_t>(right >> 64U)};
  DeviceU256 result{{0, 0, 0, 0}};
  for (unsigned int i = 0; i < 2; ++i) {
    unsigned __int128 carry = 0;
    for (unsigned int j = 0; j < 2; ++j) {
      const unsigned __int128 value =
          static_cast<unsigned __int128>(a[i]) * b[j] +
          result.limb[i + j] + carry;
      result.limb[i + j] = static_cast<std::uint64_t>(value);
      carry = value >> 64U;
    }
    result.limb[i + 2] += static_cast<std::uint64_t>(carry);
  }
  return result;
}

__device__ __forceinline__ DeviceU256 multiply_u64_device(
    DeviceU256 value, std::uint64_t factor) {
  unsigned __int128 carry = 0;
  for (unsigned int index = 0; index < 4; ++index) {
    const unsigned __int128 product =
        static_cast<unsigned __int128>(value.limb[index]) * factor +
        carry;
    value.limb[index] = static_cast<std::uint64_t>(product);
    carry = product >> 64U;
  }
  return value;
}

__device__ __forceinline__ bool less_equal_device(
    const DeviceU256& left, const DeviceU256& right) {
  for (unsigned int reverse = 4; reverse != 0; --reverse) {
    const unsigned int index = reverse - 1;
    if (left.limb[index] != right.limb[index]) {
      return left.limb[index] < right.limb[index];
    }
  }
  return true;
}

__device__ __forceinline__ bool density_endpoint_safe_device(
    std::uint64_t squarefree_count, std::uint64_t y,
    std::uint64_t floor_root, std::uint64_t density_numerator) {
  const unsigned __int128 scaled_count =
      static_cast<unsigned __int128>(squarefree_count) *
      kAffineDensityDenominator;
  const unsigned __int128 scaled_main =
      static_cast<unsigned __int128>(density_numerator) * y;
  const unsigned __int128 difference =
      scaled_count >= scaled_main ? scaled_count - scaled_main
                                  : scaled_main - scaled_count;
  const unsigned __int128 lhs_factor =
      difference * kAffineSquarefreeDenominator;
  const unsigned __int128 rhs_factor =
      static_cast<unsigned __int128>(kAffineDensityDenominator) *
      kAffineSquarefreeNumerator;
  // With r=floor(sqrt(y)), L <= C*r proves L^2 <= C^2*y and
  // L >= C*(r+1) disproves it.  Only the one-C-wide boundary strip needs
  // the exact 256-bit square comparison.  All threshold products fit u128
  // over y <= 10^16.
  const unsigned __int128 accepted_threshold =
      rhs_factor * floor_root;
  if (lhs_factor <= accepted_threshold) return true;
  const unsigned __int128 rejected_threshold =
      rhs_factor * (floor_root + 1);
  if (lhs_factor >= rejected_threshold) return false;
  const DeviceU256 lhs =
      multiply_u128_device(lhs_factor, lhs_factor);
  const DeviceU256 rhs = multiply_u64_device(
      multiply_u128_device(rhs_factor, rhs_factor), y);
  return less_equal_device(lhs, rhs);
}

__device__ __forceinline__ bool squarefree_endpoint_safe_device(
    std::uint64_t squarefree_count, std::uint64_t y,
    std::uint64_t floor_root) {
  return density_endpoint_safe_device(
             squarefree_count, y, floor_root, kAffineDensityLower) &&
         density_endpoint_safe_device(
             squarefree_count, y, floor_root, kAffineDensityUpper);
}

__device__ __forceinline__ void insert_affine_mq_row_candidates(
    std::uint64_t lower, std::size_t index,
    const TgMobiusPrefixMQ& prefix,
    TgMobiusAffineMqThreadCandidates* result) {
  const std::uint64_t n = lower + index;
  if (n >= 33) {
    const std::int64_t limit =
        static_cast<std::int64_t>(exact_hurst_limit_device(n));
    const std::uint32_t integer_order =
        static_cast<std::uint32_t>(2 * index);
    const TgMobiusAffineMqBoundCandidate lower_candidate{
        -limit - prefix.mertens, 0, integer_order};
    const TgMobiusAffineMqBoundCandidate upper_candidate{
        limit - prefix.mertens, 0, integer_order};
    sparkinterval::tg::detail::insert_max_candidate(
        lower_candidate, &result->hurst_lower, nullptr);
    sparkinterval::tg::detail::insert_min_candidate(
        upper_candidate, &result->hurst_upper, nullptr);
  }
  if (n < kAffineSquarefreeThreshold) return;
  for (unsigned int endpoint = 0; endpoint < 2; ++endpoint) {
    if (endpoint == 1 && n == kAffineSourceLimit) continue;
    const std::uint64_t y = n + endpoint;
    const std::uint64_t root = floor_sqrt_u64(y);
    const unsigned __int128 denominator =
        static_cast<unsigned __int128>(kAffineDensityDenominator) *
        kAffineSquarefreeDenominator;
    const unsigned __int128 radius =
        static_cast<unsigned __int128>(kAffineSquarefreeNumerator) *
        kAffineDensityDenominator * root;
    const unsigned __int128 lower_numerator =
        static_cast<unsigned __int128>(kAffineDensityUpper) * y *
            kAffineSquarefreeDenominator -
        radius;
    const unsigned __int128 upper_numerator =
        static_cast<unsigned __int128>(kAffineDensityLower) * y *
            kAffineSquarefreeDenominator +
        radius;
    std::uint64_t interval_lower = static_cast<std::uint64_t>(
        (lower_numerator + denominator - 1) / denominator);
    std::uint64_t interval_upper =
        static_cast<std::uint64_t>(upper_numerator / denominator);
    if (interval_lower != 0 &&
        squarefree_endpoint_safe_device(interval_lower - 1, y, root)) {
      --interval_lower;
    }
    if (interval_upper != kUnsigned64Maximum &&
        squarefree_endpoint_safe_device(interval_upper + 1, y, root)) {
      ++interval_upper;
    }
    const std::int64_t adjusted_lower =
        static_cast<std::int64_t>(interval_lower) -
        static_cast<std::int64_t>(prefix.squarefree);
    const std::int64_t adjusted_upper =
        static_cast<std::int64_t>(interval_upper) -
        static_cast<std::int64_t>(prefix.squarefree);
    const std::uint32_t order =
        static_cast<std::uint32_t>(2 * index + endpoint);
    sparkinterval::tg::detail::insert_max_candidate(
        {adjusted_lower, prefix.squarefree, order},
        &result->squarefree_lower, nullptr);
    sparkinterval::tg::detail::insert_min_candidate(
        {adjusted_upper, prefix.squarefree, order},
        &result->squarefree_upper, nullptr);
  }
}

__device__ __forceinline__ TgMobiusAffineMqThreadCandidates
compute_affine_mq_thread_candidates(
    std::uint64_t lower, std::size_t count,
    const TgMobiusPrefixMQ* prefixes) {
  const std::size_t block_offset =
      static_cast<std::size_t>(blockIdx.x) * kAffineRowsPerBlock;
  TgMobiusAffineMqThreadCandidates result =
      sparkinterval::tg::detail::empty_affine_candidates();
  for (std::size_t lane_offset = threadIdx.x;
       lane_offset < kAffineRowsPerBlock; lane_offset += blockDim.x) {
    const std::size_t index = block_offset + lane_offset;
    if (index >= count) break;
    const TgMobiusPrefixMQ prefix = prefixes[index];
    insert_affine_mq_row_candidates(lower, index, prefix, &result);
  }
  return result;
}

__global__ void affine_mq_thread_candidates(
    std::uint64_t lower, std::size_t count,
    const TgMobiusPrefixMQ* prefixes,
    TgMobiusAffineMqThreadCandidates* outputs) {
  const std::size_t output_index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  outputs[output_index] =
      compute_affine_mq_thread_candidates(lower, count, prefixes);
}

__global__ void affine_mq_block_candidates(
    std::uint64_t lower, std::size_t count,
    const TgMobiusPrefixMQ* prefixes,
    TgMobiusAffineMqThreadCandidates* outputs) {
  __shared__ TgMobiusAffineMqThreadCandidates
      shared_candidates[kThreadsPerBlock];
  shared_candidates[threadIdx.x] =
      compute_affine_mq_thread_candidates(lower, count, prefixes);
  __syncthreads();
  for (unsigned int stride = kThreadsPerBlock / 2;
       stride != 0; stride >>= 1U) {
    if (threadIdx.x < stride) {
      shared_candidates[threadIdx.x] =
          sparkinterval::tg::detail::combine_affine_candidates(
              shared_candidates[threadIdx.x],
              shared_candidates[threadIdx.x + stride]);
    }
    __syncthreads();
  }
  if (threadIdx.x == 0) outputs[blockIdx.x] = shared_candidates[0];
}

__global__ void affine_mq_device_candidate(
    const TgMobiusAffineMqThreadCandidates* inputs,
    std::size_t input_count,
    TgMobiusAffineMqThreadCandidates* output) {
  __shared__ TgMobiusAffineMqThreadCandidates
      shared_candidates[kThreadsPerBlock];
  TgMobiusAffineMqThreadCandidates local =
      sparkinterval::tg::detail::empty_affine_candidates();
  for (std::size_t index = threadIdx.x;
       index < input_count; index += blockDim.x) {
    local = sparkinterval::tg::detail::combine_affine_candidates(
        local, inputs[index]);
  }
  shared_candidates[threadIdx.x] = local;
  __syncthreads();
  for (unsigned int stride = kThreadsPerBlock / 2;
       stride != 0; stride >>= 1U) {
    if (threadIdx.x < stride) {
      shared_candidates[threadIdx.x] =
          sparkinterval::tg::detail::combine_affine_candidates(
              shared_candidates[threadIdx.x],
              shared_candidates[threadIdx.x + stride]);
    }
    __syncthreads();
  }
  if (threadIdx.x == 0) *output = shared_candidates[0];
}

__device__ __forceinline__ TgMobiusAffineMqBoundCandidate
translate_affine_candidate(
    TgMobiusAffineMqBoundCandidate candidate,
    std::int64_t value_shift, std::uint32_t squarefree_shift,
    bool carries_squarefree_prefix) {
  if (candidate.order ==
      sparkinterval::tg::detail::kCandidateUnsigned32Maximum) {
    return candidate;
  }
  candidate.value += value_shift;
  if (carries_squarefree_prefix) {
    candidate.local_squarefree += squarefree_shift;
  }
  return candidate;
}

__device__ __forceinline__ TgMobiusAffineMqBlockSummary
empty_affine_block_summary() {
  return {{0, 0},
          sparkinterval::tg::detail::empty_affine_candidates()};
}

// Ordered affine composition for two consecutive row tiles.  Right-hand
// candidates were evaluated with a zero incoming state.  Prefixing that tile
// by `left.delta` subtracts the corresponding coordinate from every affine
// value and adds it to the retained squarefree prefix witness.
__device__ __forceinline__ TgMobiusAffineMqBlockSummary
compose_affine_block_summaries(
    const TgMobiusAffineMqBlockSummary& left,
    const TgMobiusAffineMqBlockSummary& right) {
  TgMobiusAffineMqThreadCandidates translated = right.candidates;
  const std::int64_t mertens_shift =
      -static_cast<std::int64_t>(left.delta.mertens);
  const std::int64_t squarefree_shift =
      -static_cast<std::int64_t>(left.delta.squarefree);
  translated.hurst_lower = translate_affine_candidate(
      translated.hurst_lower, mertens_shift, 0, false);
  translated.hurst_upper = translate_affine_candidate(
      translated.hurst_upper, mertens_shift, 0, false);
  translated.squarefree_lower = translate_affine_candidate(
      translated.squarefree_lower, squarefree_shift,
      left.delta.squarefree, true);
  translated.squarefree_upper = translate_affine_candidate(
      translated.squarefree_upper, squarefree_shift,
      left.delta.squarefree, true);
  const std::int64_t mertens =
      static_cast<std::int64_t>(left.delta.mertens) +
      right.delta.mertens;
  const std::uint64_t squarefree =
      static_cast<std::uint64_t>(left.delta.squarefree) +
      right.delta.squarefree;
  return {
      {static_cast<std::int32_t>(mertens),
       static_cast<std::uint32_t>(squarefree)},
      sparkinterval::tg::detail::combine_affine_candidates(
          left.candidates, translated)};
}

// Qualification-only replacement for the count-row global prefix array.
// Each block owns one consecutive kAffineRowsPerBlock-row tile.  Its 256
// threads scan kAffineRowsPerThread coalesced stripes, retain candidates
// relative to a zero tile prefix, and emit one 72-byte associative summary.
__global__ void affine_mq_block_summaries_from_fused_supports(
    std::uint64_t lower, std::size_t count,
    const TgMobiusFusedSupport* supports,
    TgMobiusAffineMqBlockSummary* summaries,
    std::uint32_t* poison_count) {
  using BlockScan =
      cub::BlockScan<TgMobiusPrefixMQ, kThreadsPerBlock>;
  __shared__ typename BlockScan::TempStorage scan_storage;
  __shared__ TgMobiusAffineMqThreadCandidates
      shared_candidates[kThreadsPerBlock];
  const std::size_t block_offset =
      static_cast<std::size_t>(blockIdx.x) * kAffineRowsPerBlock;
  TgMobiusPrefixMQ running{0, 0};
  TgMobiusAffineMqThreadCandidates local_candidates =
      sparkinterval::tg::detail::empty_affine_candidates();
  for (std::size_t stripe = 0;
       stripe < kAffineRowsPerThread; ++stripe) {
    const std::size_t index =
        block_offset + stripe * kThreadsPerBlock + threadIdx.x;
    TgMobiusPrefixMQ input{0, 0};
    if (index < count) {
      bool poisoned = false;
      input = decode_fused_mobius_prefix_input(
          lower, index, supports, &poisoned);
      if (poisoned) atomicAdd(poison_count, 1U);
    }
    TgMobiusPrefixMQ stripe_prefix{};
    TgMobiusPrefixMQ stripe_total{};
    BlockScan(scan_storage).InclusiveScan(
        input, stripe_prefix, AddPrefixMq{}, stripe_total);
    const TgMobiusPrefixMQ tile_prefix =
        AddPrefixMq{}(running, stripe_prefix);
    if (index < count) {
      insert_affine_mq_row_candidates(
          lower, index, tile_prefix, &local_candidates);
    }
    running = AddPrefixMq{}(running, stripe_total);
    __syncthreads();
  }
  shared_candidates[threadIdx.x] = local_candidates;
  __syncthreads();
  for (unsigned int stride = kThreadsPerBlock / 2;
       stride != 0; stride >>= 1U) {
    if (threadIdx.x < stride) {
      shared_candidates[threadIdx.x] =
          sparkinterval::tg::detail::combine_affine_candidates(
              shared_candidates[threadIdx.x],
              shared_candidates[threadIdx.x + stride]);
    }
    __syncthreads();
  }
  if (threadIdx.x == 0) {
    summaries[blockIdx.x] = {running, shared_candidates[0]};
  }
}

// Under the default 256-row/thread geometry, the block count is at most
// ceil(10^8/65,536)=1,526.  Qualification sweeps derive the corresponding
// count from kAffineRowsPerBlock.  Each thread composes one contiguous chunk
// in source order, then the adjacent-pair tree preserves that order while
// reducing the 256 chunks.
__global__ void affine_mq_compose_block_summaries(
    const TgMobiusAffineMqBlockSummary* summaries,
    std::size_t summary_count, TgMobiusPrefixMQ* delta,
    TgMobiusAffineMqThreadCandidates* candidate) {
  __shared__ TgMobiusAffineMqBlockSummary
      shared_summaries[kThreadsPerBlock];
  const std::size_t summaries_per_thread =
      1 + (summary_count - 1) / kThreadsPerBlock;
  const std::size_t begin =
      static_cast<std::size_t>(threadIdx.x) * summaries_per_thread;
  const std::size_t proposed_end = begin + summaries_per_thread;
  const std::size_t end =
      proposed_end < summary_count ? proposed_end : summary_count;
  TgMobiusAffineMqBlockSummary local = empty_affine_block_summary();
  for (std::size_t index = begin; index < end; ++index) {
    local = compose_affine_block_summaries(local, summaries[index]);
  }
  shared_summaries[threadIdx.x] = local;
  __syncthreads();
  for (unsigned int span = 1; span < kThreadsPerBlock; span <<= 1U) {
    const unsigned int left = threadIdx.x * (span << 1U);
    if (left < kThreadsPerBlock) {
      shared_summaries[left] = compose_affine_block_summaries(
          shared_summaries[left], shared_summaries[left + span]);
    }
    __syncthreads();
  }
  if (threadIdx.x == 0) {
    *delta = shared_summaries[0].delta;
    *candidate = shared_summaries[0].candidates;
  }
}

cudaError_t check_launch() { return cudaGetLastError(); }

bool device_ranges_overlap(
    const void* first, std::size_t first_bytes,
    const void* second, std::size_t second_bytes) {
  const auto first_address =
      reinterpret_cast<std::uintptr_t>(first);
  const auto second_address =
      reinterpret_cast<std::uintptr_t>(second);
  if (first_address <= second_address) {
    return second_address - first_address < first_bytes;
  }
  return first_address - second_address < second_bytes;
}

}  // namespace

cudaError_t tg_mobius_rectangular_launch_geometry_qualification(
    std::uint64_t lower, std::size_t count,
    std::size_t multiblock_prime_count,
    TgMobiusResidueSeed seed,
    TgMobiusRectangularSlotMode mode,
    TgMobiusRectangularLaunchGeometry* geometry) {
  if (geometry == nullptr || lower == 0 ||
      lower > kTgMobiusSourceLimit || count == 0 ||
      count > kTgMobiusMultiblockMaximumCount ||
      count - 1 > kTgMobiusSourceLimit - lower ||
      multiblock_prime_count >
          kTgMobiusMultiblockDensePrimeLimit ||
      kTgMobiusMultipleEventsPerBlock == 0 ||
      kTgMobiusThreadsPerBlock == 0) {
    return cudaErrorInvalidValue;
  }
  std::size_t seed_prime_count = 0;
  std::uint32_t suffix_minimum = 0;
  std::size_t maximum_count_exact_slots = 0;
  if (!residue_seed_parameters(
          seed, &seed_prime_count, &suffix_minimum,
          &maximum_count_exact_slots) ||
      suffix_minimum == 0) {
    return cudaErrorInvalidValue;
  }
  // Match MobiusRectangularCUDASchedule.requiredSlotsPerPrime literally:
  //   1 + (((count - 1) / suffixMinimum) / eventsPerBlock).
  // The sequential quotient is also the theorem-facing form used in the
  // receipt audit, even though positive integer floor division permits a
  // product-denominator simplification.
  const std::size_t required_slots =
      1 + ((count - 1) /
               static_cast<std::size_t>(suffix_minimum)) /
              kTgMobiusMultipleEventsPerBlock;
  std::size_t slots = 0;
  if (!rectangular_slot_count(
          mode, required_slots, maximum_count_exact_slots, &slots) ||
      slots == 0 || slots < required_slots ||
      slots > kTgMobiusMultiblockSlotsPerPrime ||
      slots > std::numeric_limits<unsigned int>::max() ||
      multiblock_prime_count >
          std::numeric_limits<unsigned int>::max()) {
    return cudaErrorInvalidValue;
  }

  int current_device = 0;
  cudaError_t status = cudaGetDevice(&current_device);
  if (status != cudaSuccess) return status;
  int maximum_grid_x = 0;
  int maximum_grid_y = 0;
  int maximum_grid_z = 0;
  int maximum_threads_per_block = 0;
  int maximum_block_dim_x = 0;
  status = cudaDeviceGetAttribute(
      &maximum_grid_x, cudaDevAttrMaxGridDimX, current_device);
  if (status != cudaSuccess) return status;
  status = cudaDeviceGetAttribute(
      &maximum_grid_y, cudaDevAttrMaxGridDimY, current_device);
  if (status != cudaSuccess) return status;
  status = cudaDeviceGetAttribute(
      &maximum_grid_z, cudaDevAttrMaxGridDimZ, current_device);
  if (status != cudaSuccess) return status;
  status = cudaDeviceGetAttribute(
      &maximum_threads_per_block,
      cudaDevAttrMaxThreadsPerBlock, current_device);
  if (status != cudaSuccess) return status;
  status = cudaDeviceGetAttribute(
      &maximum_block_dim_x, cudaDevAttrMaxBlockDimX, current_device);
  if (status != cudaSuccess) return status;
  if (maximum_grid_x < 1 || maximum_grid_y < 1 ||
      maximum_grid_z < 1 || maximum_threads_per_block < 1 ||
      maximum_block_dim_x < 1 ||
      slots > static_cast<std::size_t>(maximum_grid_x) ||
      (multiblock_prime_count != 0 &&
       multiblock_prime_count >
           static_cast<std::size_t>(maximum_grid_y)) ||
      1U > static_cast<unsigned int>(maximum_grid_z) ||
      kTgMobiusThreadsPerBlock >
          static_cast<std::size_t>(maximum_threads_per_block) ||
      kTgMobiusThreadsPerBlock >
          static_cast<std::size_t>(maximum_block_dim_x)) {
    return cudaErrorInvalidConfiguration;
  }

  *geometry = TgMobiusRectangularLaunchGeometry{
      seed,
      mode,
      lower,
      count,
      seed_prime_count,
      suffix_minimum,
      required_slots,
      slots,
      kTgMobiusMultipleEventsPerBlock,
      static_cast<unsigned int>(slots),
      static_cast<unsigned int>(multiblock_prime_count),
      1U,
      kThreadsPerBlock};
  return cudaSuccess;
}

cudaError_t launch_tg_mobius_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusSupport* outputs, cudaStream_t stream) {
  if (lower == 0 || count == 0 || outputs == nullptr ||
      (base_prime_count != 0 && base_primes == nullptr) ||
      dense_prime_count > base_prime_count) {
    return cudaErrorInvalidValue;
  }
  if (count - 1 > std::numeric_limits<std::uint64_t>::max() - lower) {
    return cudaErrorInvalidValue;
  }
  const std::size_t output_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  const std::size_t sparse_prime_count = base_prime_count - dense_prime_count;
  const std::size_t sparse_blocks =
      sparse_prime_count == 0
          ? 0
          : 1 + (sparse_prime_count - 1) / kThreadsPerBlock;
  if (output_blocks > kMaximumGridX || dense_prime_count > kMaximumGridX ||
      sparse_blocks > kMaximumGridX) {
    return cudaErrorInvalidConfiguration;
  }

  initialize_mobius_support<<<static_cast<unsigned int>(output_blocks),
                              kThreadsPerBlock, 0, stream>>>(outputs, count);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;
  if (dense_prime_count != 0) {
    mark_dense_prime_support<<<static_cast<unsigned int>(dense_prime_count),
                               kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, outputs);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (sparse_prime_count != 0) {
    mark_sparse_prime_support<<<static_cast<unsigned int>(sparse_blocks),
                                kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, dense_prime_count, base_prime_count,
        outputs);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  finalize_mobius_support<<<static_cast<unsigned int>(output_blocks),
                            kThreadsPerBlock, 0, stream>>>(lower, count,
                                                           outputs);
  return check_launch();
}

cudaError_t launch_tg_mobius_pack(
    const TgMobiusSupport* inputs, std::size_t count,
    std::int8_t* outputs, cudaStream_t stream) {
  if (inputs == nullptr || count == 0 || outputs == nullptr) {
    return cudaErrorInvalidValue;
  }
  const std::size_t blocks = 1 + (count - 1) / kThreadsPerBlock;
  if (blocks > kMaximumGridX) return cudaErrorInvalidConfiguration;
  pack_mobius_values<<<static_cast<unsigned int>(blocks),
                       kThreadsPerBlock, 0, stream>>>(inputs, count, outputs);
  return check_launch();
}

cudaError_t launch_tg_mobius_compact_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusCompactSupport* supports, std::int8_t* mobius,
    cudaStream_t stream) {
  if (lower == 0 || count == 0 || supports == nullptr ||
      mobius == nullptr ||
      (base_prime_count != 0 && base_primes == nullptr) ||
      dense_prime_count > base_prime_count ||
      count - 1 > std::numeric_limits<std::uint64_t>::max() - lower) {
    return cudaErrorInvalidValue;
  }
  const std::size_t output_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  const std::size_t sparse_prime_count =
      base_prime_count - dense_prime_count;
  const std::size_t sparse_blocks =
      sparse_prime_count == 0
          ? 0
          : 1 + (sparse_prime_count - 1) / kThreadsPerBlock;
  if (output_blocks > kMaximumGridX ||
      dense_prime_count > kMaximumGridX ||
      sparse_blocks > kMaximumGridX) {
    return cudaErrorInvalidConfiguration;
  }
  initialize_compact_mobius_support<<<
      static_cast<unsigned int>(output_blocks),
      kThreadsPerBlock, 0, stream>>>(supports, count);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;
  if (dense_prime_count != 0) {
    mark_dense_prime_compact_support<<<
        static_cast<unsigned int>(dense_prime_count),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, supports);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (sparse_prime_count != 0) {
    mark_sparse_prime_compact_support<<<
        static_cast<unsigned int>(sparse_blocks),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, dense_prime_count,
        base_prime_count, supports);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  finalize_compact_mobius_support<<<
      static_cast<unsigned int>(output_blocks),
      kThreadsPerBlock, 0, stream>>>(
      lower, count, supports, mobius);
  return check_launch();
}

cudaError_t launch_tg_mobius_fused_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    cudaStream_t stream) {
  if (lower == 0 || lower > kTgMobiusSourceLimit ||
      count == 0 || supports == nullptr ||
      mobius == nullptr ||
      (base_prime_count != 0 && base_primes == nullptr) ||
      dense_prime_count > base_prime_count ||
      count - 1 > kTgMobiusSourceLimit - lower) {
    return cudaErrorInvalidValue;
  }
  const std::size_t output_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  const std::size_t sparse_prime_count =
      base_prime_count - dense_prime_count;
  const std::size_t sparse_blocks =
      sparse_prime_count == 0
          ? 0
          : 1 + (sparse_prime_count - 1) / kThreadsPerBlock;
  if (output_blocks > kMaximumGridX ||
      dense_prime_count > kMaximumGridX ||
      sparse_blocks > kMaximumGridX) {
    return cudaErrorInvalidConfiguration;
  }
  initialize_fused_mobius_support<<<
      static_cast<unsigned int>(output_blocks),
      kThreadsPerBlock, 0, stream>>>(supports, count);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;
  if (dense_prime_count != 0) {
    mark_dense_prime_fused_support<<<
        static_cast<unsigned int>(dense_prime_count),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, supports);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (sparse_prime_count != 0) {
    mark_sparse_prime_fused_support<<<
        static_cast<unsigned int>(sparse_blocks),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, base_primes, dense_prime_count,
        base_prime_count, supports);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  finalize_fused_mobius_support<<<
      static_cast<unsigned int>(output_blocks),
      kThreadsPerBlock, 0, stream>>>(
      lower, count, supports, mobius);
  return check_launch();
}

namespace {

cudaError_t launch_tg_mobius_fused_segment_multiblock_dense_impl(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    bool initialize_from_residue_235, bool finalize_mobius,
    bool split_squareful, bool qualification_seed_seven,
    bool qualification_seed_eleven, bool qualification_seed_thirteen,
    const TgMobiusRectangularLaunchGeometry* rectangular_geometry,
    std::uint32_t* roster_invalid,
    cudaStream_t stream) {
  const std::size_t seeded_prime_count =
      qualification_seed_thirteen
          ? kTgMobiusResidue23571113PrimeCount
          : qualification_seed_eleven
          ? kTgMobiusResidue235711PrimeCount
          : qualification_seed_seven
          ? kTgMobiusResidue2357PrimeCount
          : (initialize_from_residue_235
                 ? kTgMobiusResidue235PrimeCount
                 : 0);
  if (lower == 0 || lower > kTgMobiusSourceLimit ||
      count == 0 ||
      count > kTgMobiusMultiblockMaximumCount ||
      supports == nullptr || (finalize_mobius && mobius == nullptr) ||
      (base_prime_count != 0 && base_primes == nullptr) ||
      (split_squareful && roster_invalid == nullptr) ||
      ((qualification_seed_seven || qualification_seed_eleven ||
        qualification_seed_thirteen) &&
       (!initialize_from_residue_235 || !split_squareful)) ||
      (rectangular_geometry != nullptr &&
       (!initialize_from_residue_235 || !split_squareful)) ||
      (qualification_seed_seven && qualification_seed_eleven) ||
      (qualification_seed_seven && qualification_seed_thirteen) ||
      (qualification_seed_eleven && qualification_seed_thirteen) ||
      base_prime_count < seeded_prime_count ||
      dense_prime_count > base_prime_count ||
      count - 1 > kTgMobiusSourceLimit - lower) {
    return cudaErrorInvalidValue;
  }
  if (base_prime_count >
          std::numeric_limits<std::size_t>::max() /
              sizeof(std::uint32_t) ||
      count >
          std::numeric_limits<std::size_t>::max() /
              sizeof(TgMobiusFusedSupport)) {
    return cudaErrorInvalidValue;
  }
  const std::size_t prime_bytes =
      base_prime_count * sizeof(std::uint32_t);
  const std::size_t support_bytes =
      count * sizeof(TgMobiusFusedSupport);
  const bool primes_overlap_supports =
      base_prime_count != 0 &&
      device_ranges_overlap(
          base_primes, prime_bytes, supports, support_bytes);
  const bool primes_overlap_mobius =
      finalize_mobius && base_prime_count != 0 &&
      device_ranges_overlap(
          base_primes, prime_bytes, mobius, count);
  const bool primes_overlap_roster_status =
      split_squareful && base_prime_count != 0 &&
      device_ranges_overlap(
          base_primes, prime_bytes, roster_invalid,
          sizeof(std::uint32_t));
  const bool supports_overlap_mobius =
      finalize_mobius &&
      device_ranges_overlap(
          supports, support_bytes, mobius, count);
  const bool supports_overlap_roster_status =
      split_squareful &&
      device_ranges_overlap(
          supports, support_bytes, roster_invalid,
          sizeof(std::uint32_t));
  const bool mobius_overlaps_roster_status =
      finalize_mobius && split_squareful &&
      device_ranges_overlap(
          mobius, count, roster_invalid, sizeof(std::uint32_t));
  if (primes_overlap_supports || primes_overlap_mobius ||
      primes_overlap_roster_status || supports_overlap_mobius ||
      supports_overlap_roster_status ||
      mobius_overlaps_roster_status) {
    return cudaErrorInvalidValue;
  }
  const std::uint32_t* unseeded_base_primes =
      seeded_prime_count == 0
          ? base_primes
          : base_primes + seeded_prime_count;
  const std::size_t unseeded_base_prime_count =
      base_prime_count - seeded_prime_count;
  const std::size_t seeded_dense_prime_count =
      dense_prime_count < seeded_prime_count
          ? dense_prime_count
          : seeded_prime_count;
  const std::size_t unseeded_dense_prime_count =
      dense_prime_count - seeded_dense_prime_count;
  const std::size_t output_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  const std::size_t sparse_prime_count =
      unseeded_base_prime_count - unseeded_dense_prime_count;
  const std::size_t sparse_blocks =
      sparse_prime_count == 0
          ? 0
          : 1 + (sparse_prime_count - 1) / kThreadsPerBlock;
  const std::size_t multiblock_prime_count =
      bounded_multiblock_prime_count(
          unseeded_dense_prime_count);
  const std::size_t block_slots_per_dense_prime =
      rectangular_geometry != nullptr
          ? rectangular_geometry->slots_per_prime
          : qualification_seed_thirteen
          ? kTgMobiusResidue23571113MultiblockSlotsPerPrime
          : qualification_seed_eleven
          ? kTgMobiusResidue235711MultiblockSlotsPerPrime
          : qualification_seed_seven
          ? kTgMobiusResidue2357MultiblockSlotsPerPrime
          : initialize_from_residue_235
          ? kTgMobiusResidue235MultiblockSlotsPerPrime
          : kTgMobiusMultiblockSlotsPerPrime;
  const std::size_t multiblock_grid =
      multiblock_prime_count *
      block_slots_per_dense_prime;
  const std::size_t remaining_dense_prime_count =
      unseeded_dense_prime_count - multiblock_prime_count;
  const std::size_t square_dense_prime_count =
      unseeded_base_prime_count <
              kTgMobiusSplitSquareDensePrimeLimit
          ? unseeded_base_prime_count
          : kTgMobiusSplitSquareDensePrimeLimit;
  const std::size_t square_sparse_prime_count =
      unseeded_base_prime_count - square_dense_prime_count;
  const std::size_t square_sparse_blocks =
      square_sparse_prime_count == 0
          ? 0
          : 1 + (square_sparse_prime_count - 1) /
                    kThreadsPerBlock;
  const std::size_t roster_validation_blocks =
      split_squareful
          ? 1 + (base_prime_count - 1) / kThreadsPerBlock
          : 0;
  if (rectangular_geometry != nullptr) {
    const TgMobiusResidueSeed expected_seed =
        qualification_seed_thirteen
            ? TgMobiusResidueSeed::k23571113
            : qualification_seed_eleven
            ? TgMobiusResidueSeed::k235711
            : qualification_seed_seven
                  ? TgMobiusResidueSeed::k2357
                  : TgMobiusResidueSeed::k235;
    if (rectangular_geometry->seed != expected_seed ||
        rectangular_geometry->enclosing_lower != lower ||
        rectangular_geometry->enclosing_count != count ||
        rectangular_geometry->seed_prime_count != seeded_prime_count ||
        rectangular_geometry->required_slots_per_prime == 0 ||
        rectangular_geometry->slots_per_prime == 0 ||
        rectangular_geometry->slots_per_prime <
            rectangular_geometry->required_slots_per_prime ||
        rectangular_geometry->slots_per_prime >
            kTgMobiusMultiblockSlotsPerPrime ||
        rectangular_geometry->events_per_block !=
            kTgMobiusMultipleEventsPerBlock ||
        rectangular_geometry->grid_x !=
            rectangular_geometry->slots_per_prime ||
        rectangular_geometry->grid_y !=
            multiblock_prime_count ||
        rectangular_geometry->grid_z != 1 ||
        rectangular_geometry->threads_per_block !=
            kThreadsPerBlock) {
      return cudaErrorInvalidValue;
    }
  }
  if (output_blocks > kMaximumGridX ||
      (rectangular_geometry == nullptr &&
       multiblock_grid > kMaximumGridX) ||
      remaining_dense_prime_count > kMaximumGridX ||
      sparse_blocks > kMaximumGridX ||
      square_dense_prime_count > kMaximumGridX ||
      square_sparse_blocks > kMaximumGridX ||
      roster_validation_blocks > kMaximumGridX) {
    return cudaErrorInvalidConfiguration;
  }
  cudaError_t status = cudaSuccess;
  if (split_squareful) {
    status = cudaMemsetAsync(
        roster_invalid, 0, sizeof(std::uint32_t), stream);
    if (status != cudaSuccess) return status;
    validate_split_square_mobius_roster<<<
        static_cast<unsigned int>(roster_validation_blocks),
        kThreadsPerBlock, 0, stream>>>(
        base_primes, base_prime_count, seeded_prime_count,
        roster_invalid);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (initialize_from_residue_235) {
    if (qualification_seed_thirteen) {
      initialize_fused_mobius_support_residue_235<true, true, true><<<
          static_cast<unsigned int>(output_blocks),
          kThreadsPerBlock, 0, stream>>>(
          lower, supports, count, roster_invalid);
    } else if (qualification_seed_eleven) {
      initialize_fused_mobius_support_residue_235<true, true, false><<<
          static_cast<unsigned int>(output_blocks),
          kThreadsPerBlock, 0, stream>>>(
          lower, supports, count, roster_invalid);
    } else if (qualification_seed_seven) {
      initialize_fused_mobius_support_residue_235<true, false, false><<<
          static_cast<unsigned int>(output_blocks),
          kThreadsPerBlock, 0, stream>>>(
          lower, supports, count, roster_invalid);
    } else {
      initialize_fused_mobius_support_residue_235<false, false, false><<<
          static_cast<unsigned int>(output_blocks),
          kThreadsPerBlock, 0, stream>>>(
          lower, supports, count, roster_invalid);
    }
  } else {
    initialize_fused_mobius_support<<<
        static_cast<unsigned int>(output_blocks),
        kThreadsPerBlock, 0, stream>>>(supports, count);
  }
  status = check_launch();
  if (status != cudaSuccess) return status;
  if (multiblock_prime_count != 0) {
    if (split_squareful) {
      if (rectangular_geometry != nullptr) {
        const dim3 rectangular_grid(
            rectangular_geometry->grid_x,
            rectangular_geometry->grid_y,
            rectangular_geometry->grid_z);
        mark_dense_prime_fused_distinct_divisors_multiblock_rectangular<<<
            rectangular_grid, kThreadsPerBlock, 0, stream>>>(
            lower, count, unseeded_base_primes, supports);
      } else if (initialize_from_residue_235) {
        if (qualification_seed_thirteen) {
          mark_dense_prime_fused_distinct_divisors_multiblock<
              kTgMobiusResidue23571113MultiblockSlotsPerPrime><<<
              static_cast<unsigned int>(multiblock_grid),
              kThreadsPerBlock, 0, stream>>>(
              lower, count, unseeded_base_primes, supports);
        } else if (qualification_seed_eleven) {
          mark_dense_prime_fused_distinct_divisors_multiblock<
              kTgMobiusResidue235711MultiblockSlotsPerPrime><<<
              static_cast<unsigned int>(multiblock_grid),
              kThreadsPerBlock, 0, stream>>>(
              lower, count, unseeded_base_primes, supports);
        } else if (qualification_seed_seven) {
          mark_dense_prime_fused_distinct_divisors_multiblock<
              kTgMobiusResidue2357MultiblockSlotsPerPrime><<<
              static_cast<unsigned int>(multiblock_grid),
              kThreadsPerBlock, 0, stream>>>(
              lower, count, unseeded_base_primes, supports);
        } else {
          mark_dense_prime_fused_distinct_divisors_multiblock<
              kTgMobiusResidue235MultiblockSlotsPerPrime><<<
              static_cast<unsigned int>(multiblock_grid),
              kThreadsPerBlock, 0, stream>>>(
              lower, count, unseeded_base_primes, supports);
        }
      } else {
        mark_dense_prime_fused_distinct_divisors_multiblock<
            kTgMobiusMultiblockSlotsPerPrime><<<
            static_cast<unsigned int>(multiblock_grid),
            kThreadsPerBlock, 0, stream>>>(
            lower, count, unseeded_base_primes, supports);
      }
    } else {
      if (initialize_from_residue_235) {
        mark_dense_prime_fused_support_multiblock<
            kTgMobiusResidue235MultiblockSlotsPerPrime><<<
            static_cast<unsigned int>(multiblock_grid),
            kThreadsPerBlock, 0, stream>>>(
            lower, count, unseeded_base_primes, supports);
      } else {
        mark_dense_prime_fused_support_multiblock<
            kTgMobiusMultiblockSlotsPerPrime><<<
            static_cast<unsigned int>(multiblock_grid),
            kThreadsPerBlock, 0, stream>>>(
            lower, count, unseeded_base_primes, supports);
      }
    }
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (remaining_dense_prime_count != 0) {
    if (split_squareful) {
      mark_dense_prime_fused_distinct_divisors<<<
          static_cast<unsigned int>(remaining_dense_prime_count),
          kThreadsPerBlock, 0, stream>>>(
          lower, count,
          unseeded_base_primes + multiblock_prime_count,
          supports);
    } else {
      mark_dense_prime_fused_support<<<
          static_cast<unsigned int>(remaining_dense_prime_count),
          kThreadsPerBlock, 0, stream>>>(
          lower, count,
          unseeded_base_primes + multiblock_prime_count,
          supports);
    }
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (sparse_prime_count != 0) {
    if (split_squareful) {
      mark_sparse_prime_fused_distinct_divisors<<<
          static_cast<unsigned int>(sparse_blocks),
          kThreadsPerBlock, 0, stream>>>(
          lower, count, unseeded_base_primes,
          unseeded_dense_prime_count,
          unseeded_base_prime_count, supports);
    } else {
      mark_sparse_prime_fused_support<<<
          static_cast<unsigned int>(sparse_blocks),
          kThreadsPerBlock, 0, stream>>>(
          lower, count, unseeded_base_primes,
          unseeded_dense_prime_count,
          unseeded_base_prime_count, supports);
    }
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  // CUDA launches in one stream execute in issue order.  Therefore no
  // product/count CAS can overlap either square-strike kernel, and no
  // finalizer can observe a support row before every square strike finishes.
  if (split_squareful && square_dense_prime_count != 0) {
    mark_dense_prime_fused_squareful<<<
        static_cast<unsigned int>(square_dense_prime_count),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, unseeded_base_primes, supports);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (split_squareful && square_sparse_prime_count != 0) {
    mark_sparse_prime_fused_squareful<<<
        static_cast<unsigned int>(square_sparse_blocks),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, unseeded_base_primes,
        square_dense_prime_count,
        unseeded_base_prime_count, supports);
    status = check_launch();
    if (status != cudaSuccess) return status;
  }
  if (finalize_mobius) {
    finalize_fused_mobius_support<<<
        static_cast<unsigned int>(output_blocks),
        kThreadsPerBlock, 0, stream>>>(
        lower, count, supports, mobius);
    return check_launch();
  }
  return cudaSuccess;
}

}  // namespace

cudaError_t launch_tg_mobius_fused_segment_multiblock_dense(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, mobius, false, true, false, false,
      false, false, nullptr, nullptr, stream);
}

cudaError_t launch_tg_mobius_fused_segment_multiblock_dense_residue_235(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, mobius, true, true, false, false,
      false, false, nullptr, nullptr, stream);
}

cudaError_t launch_tg_mobius_fused_support_multiblock_dense_residue_235(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, nullptr, true, false, false, false,
      false, false, nullptr, nullptr, stream);
}

cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, nullptr, true, false, true, false,
      false, false, nullptr, roster_invalid, stream);
}

cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_2357_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, nullptr, true, false, true, true,
      false, false, nullptr, roster_invalid, stream);
}

cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_2357_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid, cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, mobius, true, true, true, true,
      false, false, nullptr, roster_invalid, stream);
}

cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_235711_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, nullptr, true, false, true, false,
      true, false, nullptr, roster_invalid, stream);
}

cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid, cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, mobius, true, true, true, false,
      true, false, nullptr, roster_invalid, stream);
}

cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_23571113_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, nullptr, true, false, true, false,
      false, true, nullptr, roster_invalid, stream);
}

cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_23571113_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid, cudaStream_t stream) {
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, mobius, true, true, true, false,
      false, true, nullptr, roster_invalid, stream);
}

namespace {

cudaError_t launch_tg_mobius_fused_rectangular_qualification_impl(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusResidueSeed seed,
    TgMobiusRectangularSlotMode mode,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    bool finalize_mobius, std::uint32_t* roster_invalid,
    TgMobiusRectangularLaunchGeometry* geometry,
    cudaStream_t stream) {
  std::size_t seed_prime_count = 0;
  std::uint32_t suffix_minimum = 0;
  std::size_t maximum_count_exact_slots = 0;
  if (!residue_seed_parameters(
          seed, &seed_prime_count, &suffix_minimum,
          &maximum_count_exact_slots) ||
      base_prime_count < seed_prime_count ||
      base_primes == nullptr || dense_prime_count > base_prime_count ||
      supports == nullptr || (finalize_mobius && mobius == nullptr) ||
      roster_invalid == nullptr || geometry == nullptr) {
    return cudaErrorInvalidValue;
  }
  const std::size_t seeded_dense_prime_count =
      dense_prime_count < seed_prime_count
          ? dense_prime_count
          : seed_prime_count;
  const std::size_t unseeded_dense_prime_count =
      dense_prime_count - seeded_dense_prime_count;
  const std::size_t multiblock_prime_count =
      bounded_multiblock_prime_count(unseeded_dense_prime_count);
  cudaError_t status =
      tg_mobius_rectangular_launch_geometry_qualification(
          lower, count, multiblock_prime_count, seed, mode, geometry);
  if (status != cudaSuccess) return status;
  const bool seed_seven = seed == TgMobiusResidueSeed::k2357;
  const bool seed_eleven = seed == TgMobiusResidueSeed::k235711;
  const bool seed_thirteen =
      seed == TgMobiusResidueSeed::k23571113;
  return launch_tg_mobius_fused_segment_multiblock_dense_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, supports, mobius, true, finalize_mobius,
      true, seed_seven, seed_eleven, seed_thirteen,
      geometry, roster_invalid, stream);
}

}  // namespace

cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_rectangular_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusResidueSeed seed,
    TgMobiusRectangularSlotMode mode,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    TgMobiusRectangularLaunchGeometry* geometry,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_rectangular_qualification_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, seed, mode, supports, nullptr, false,
      roster_invalid, geometry, stream);
}

cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_rectangular_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusResidueSeed seed,
    TgMobiusRectangularSlotMode mode,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid,
    TgMobiusRectangularLaunchGeometry* geometry,
    cudaStream_t stream) {
  return launch_tg_mobius_fused_rectangular_qualification_impl(
      lower, count, base_primes, base_prime_count,
      dense_prime_count, seed, mode, supports, mobius, true,
      roster_invalid, geometry, stream);
}

cudaError_t launch_tg_mobius_fused_prefix_inputs(
    std::uint64_t lower, const TgMobiusFusedSupport* supports,
    std::size_t count, TgMobiusPrefixMQ* prefix_inputs,
    std::uint32_t* poison_count, cudaStream_t stream) {
  if (lower == 0 || lower > kAffineSourceLimit ||
      supports == nullptr || count == 0 ||
      count > kMaximumAffineSourceCount ||
      count - 1 > kAffineSourceLimit - lower ||
      prefix_inputs == nullptr || poison_count == nullptr) {
    return cudaErrorInvalidValue;
  }
  const std::size_t blocks =
      1 + (count - 1) / kThreadsPerBlock;
  finalize_fused_mobius_prefix_inputs<<<
      static_cast<unsigned int>(blocks),
      kThreadsPerBlock, 0, stream>>>(
      lower, count, supports, prefix_inputs, poison_count);
  return check_launch();
}

cudaError_t launch_tg_mobius_poison_count(
    const std::int8_t* mobius, std::size_t count,
    std::uint32_t* poison_count, cudaStream_t stream) {
  if (mobius == nullptr || count == 0 ||
      count > kMaximumAffineSourceCount ||
      poison_count == nullptr) {
    return cudaErrorInvalidValue;
  }
  const std::size_t blocks =
      1 + (count - 1) / kThreadsPerBlock;
  count_poisoned_mobius<<<
      static_cast<unsigned int>(blocks),
      kThreadsPerBlock, 0, stream>>>(
      mobius, count, poison_count);
  return check_launch();
}

std::size_t tg_mobius_affine_mq_candidate_count(std::size_t count) {
  if (count == 0 || count > kMaximumAffineSourceCount) return 0;
  const std::size_t blocks = 1 + (count - 1) / kAffineRowsPerBlock;
  if (blocks > kMaximumGridX) return 0;
  return blocks * kThreadsPerBlock;
}

std::size_t tg_mobius_affine_mq_reduced_candidate_count(
    std::size_t count) {
  return tg_mobius_affine_mq_candidate_count(count) == 0 ? 0 : 1;
}

cudaError_t tg_mobius_affine_mq_workspace_size(
    std::size_t count, std::size_t* workspace_bytes) {
  if (count == 0 || count > kMaximumAffineSourceCount ||
      workspace_bytes == nullptr) {
    return cudaErrorInvalidValue;
  }
  return cub::DeviceScan::InclusiveScan(
      nullptr, *workspace_bytes,
      static_cast<TgMobiusPrefixMQ*>(nullptr),
      static_cast<TgMobiusPrefixMQ*>(nullptr), AddPrefixMq{}, count);
}

cudaError_t tg_mobius_affine_mq_reduced_workspace_size(
    std::size_t count, std::size_t* workspace_bytes) {
  if (workspace_bytes == nullptr) return cudaErrorInvalidValue;
  std::size_t cub_bytes = 0;
  cudaError_t status =
      tg_mobius_affine_mq_workspace_size(count, &cub_bytes);
  if (status != cudaSuccess) return status;
  const std::size_t thread_candidate_count =
      tg_mobius_affine_mq_candidate_count(count);
  const std::size_t block_candidate_count =
      thread_candidate_count / kThreadsPerBlock;
  const std::size_t block_bytes =
      block_candidate_count * sizeof(TgMobiusAffineMqThreadCandidates);
  *workspace_bytes = cub_bytes > block_bytes ? cub_bytes : block_bytes;
  return cudaSuccess;
}

cudaError_t launch_tg_mobius_affine_mq(
    std::uint64_t lower, const std::int8_t* mobius, std::size_t count,
    TgMobiusPrefixMQ* prefixes,
    TgMobiusAffineMqThreadCandidates* candidates,
    void* workspace, std::size_t workspace_bytes,
    cudaStream_t stream) {
  const std::size_t candidate_count =
      tg_mobius_affine_mq_candidate_count(count);
  if (lower == 0 || lower > kAffineSourceLimit ||
      mobius == nullptr || count == 0 ||
      count > kMaximumAffineSourceCount ||
      count - 1 > kAffineSourceLimit - lower ||
      prefixes == nullptr || candidates == nullptr ||
      workspace == nullptr || workspace_bytes == 0 ||
      candidate_count == 0) {
    return cudaErrorInvalidValue;
  }
  const std::size_t prefix_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  initialize_prefix_mq<<<static_cast<unsigned int>(prefix_blocks),
                         kThreadsPerBlock, 0, stream>>>(
      mobius, count, prefixes, nullptr);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;
  status = cub::DeviceScan::InclusiveScan(
      workspace, workspace_bytes, prefixes, prefixes, AddPrefixMq{}, count,
      stream);
  if (status != cudaSuccess) return status;
  const std::size_t blocks = candidate_count / kThreadsPerBlock;
  affine_mq_thread_candidates<<<static_cast<unsigned int>(blocks),
                                kThreadsPerBlock, 0, stream>>>(
      lower, count, prefixes, candidates);
  return check_launch();
}

cudaError_t launch_tg_mobius_affine_mq_reduced(
    std::uint64_t lower, const std::int8_t* mobius, std::size_t count,
    TgMobiusPrefixMQ* prefixes,
    TgMobiusAffineMqThreadCandidates* candidate,
    void* workspace, std::size_t workspace_bytes,
    std::uint32_t* poison_count,
    cudaStream_t stream) {
  const std::size_t thread_candidate_count =
      tg_mobius_affine_mq_candidate_count(count);
  const std::size_t block_candidate_count =
      thread_candidate_count / kThreadsPerBlock;
  std::size_t required_workspace_bytes = 0;
  cudaError_t status = tg_mobius_affine_mq_reduced_workspace_size(
      count, &required_workspace_bytes);
  if (status != cudaSuccess) return status;
  if (lower == 0 || lower > kAffineSourceLimit ||
      mobius == nullptr || count == 0 ||
      count > kMaximumAffineSourceCount ||
      count - 1 > kAffineSourceLimit - lower ||
      prefixes == nullptr || candidate == nullptr ||
      workspace == nullptr ||
      workspace_bytes < required_workspace_bytes ||
      block_candidate_count == 0) {
    return cudaErrorInvalidValue;
  }
  const std::size_t prefix_blocks =
      1 + (count - 1) / kThreadsPerBlock;
  initialize_prefix_mq<<<static_cast<unsigned int>(prefix_blocks),
                         kThreadsPerBlock, 0, stream>>>(
      mobius, count, prefixes, poison_count);
  status = check_launch();
  if (status != cudaSuccess) return status;
  return launch_tg_mobius_affine_mq_reduced_from_prefix_inputs(
      lower, count, prefixes, candidate, workspace,
      workspace_bytes, stream);
}

cudaError_t launch_tg_mobius_affine_mq_reduced_from_prefix_inputs(
    std::uint64_t lower, std::size_t count,
    TgMobiusPrefixMQ* prefix_inputs,
    TgMobiusAffineMqThreadCandidates* candidate,
    void* workspace, std::size_t workspace_bytes,
    cudaStream_t stream) {
  const std::size_t thread_candidate_count =
      tg_mobius_affine_mq_candidate_count(count);
  const std::size_t block_candidate_count =
      thread_candidate_count / kThreadsPerBlock;
  std::size_t required_workspace_bytes = 0;
  cudaError_t status = tg_mobius_affine_mq_reduced_workspace_size(
      count, &required_workspace_bytes);
  if (status != cudaSuccess) return status;
  if (lower == 0 || lower > kAffineSourceLimit ||
      count == 0 || count > kMaximumAffineSourceCount ||
      count - 1 > kAffineSourceLimit - lower ||
      prefix_inputs == nullptr || candidate == nullptr ||
      workspace == nullptr ||
      workspace_bytes < required_workspace_bytes ||
      block_candidate_count == 0) {
    return cudaErrorInvalidValue;
  }
  std::size_t cub_bytes = 0;
  status = tg_mobius_affine_mq_workspace_size(count, &cub_bytes);
  if (status != cudaSuccess) return status;
  status = cub::DeviceScan::InclusiveScan(
      workspace, cub_bytes, prefix_inputs, prefix_inputs,
      AddPrefixMq{}, count,
      stream);
  if (status != cudaSuccess) return status;
  auto* block_candidates =
      static_cast<TgMobiusAffineMqThreadCandidates*>(workspace);
  affine_mq_block_candidates<<<
      static_cast<unsigned int>(block_candidate_count),
      kThreadsPerBlock, 0, stream>>>(
      lower, count, prefix_inputs, block_candidates);
  status = check_launch();
  if (status != cudaSuccess) return status;
  affine_mq_device_candidate<<<1, kThreadsPerBlock, 0, stream>>>(
      block_candidates, block_candidate_count, candidate);
  return check_launch();
}

std::size_t tg_mobius_affine_mq_block_summary_count(
    std::size_t count) {
  if (count == 0 || count > kMaximumAffineSourceCount) return 0;
  return 1 + (count - 1) / kAffineRowsPerBlock;
}

std::size_t tg_mobius_affine_mq_rows_per_thread() {
  return kAffineRowsPerThread;
}

std::size_t tg_mobius_affine_mq_rows_per_block() {
  return kAffineRowsPerBlock;
}

cudaError_t
launch_tg_mobius_affine_mq_compose_block_summaries_qualification(
    const TgMobiusAffineMqBlockSummary* block_summaries,
    std::size_t summary_count,
    TgMobiusPrefixMQ* delta,
    TgMobiusAffineMqThreadCandidates* candidate,
    cudaStream_t stream) {
  const std::size_t maximum_summary_count =
      tg_mobius_affine_mq_block_summary_count(
          kMaximumAffineSourceCount);
  if (block_summaries == nullptr || summary_count == 0 ||
      summary_count > maximum_summary_count ||
      delta == nullptr || candidate == nullptr ||
      device_ranges_overlap(
          block_summaries,
          summary_count * sizeof(TgMobiusAffineMqBlockSummary),
          delta, sizeof(TgMobiusPrefixMQ)) ||
      device_ranges_overlap(
          block_summaries,
          summary_count * sizeof(TgMobiusAffineMqBlockSummary),
          candidate, sizeof(TgMobiusAffineMqThreadCandidates)) ||
      device_ranges_overlap(
          delta, sizeof(TgMobiusPrefixMQ),
          candidate, sizeof(TgMobiusAffineMqThreadCandidates))) {
    return cudaErrorInvalidValue;
  }
  affine_mq_compose_block_summaries<<<
      1, kThreadsPerBlock, 0, stream>>>(
      block_summaries, summary_count, delta, candidate);
  return check_launch();
}

cudaError_t
launch_tg_mobius_affine_mq_block_compose_from_fused_supports_qualification(
    std::uint64_t lower, std::size_t count,
    const TgMobiusFusedSupport* supports,
    TgMobiusAffineMqBlockSummary* block_summaries,
    std::size_t block_summary_capacity,
    TgMobiusPrefixMQ* delta,
    TgMobiusAffineMqThreadCandidates* candidate,
    std::uint32_t* poison_count,
    cudaStream_t stream) {
  const std::size_t summary_count =
      tg_mobius_affine_mq_block_summary_count(count);
  if (lower == 0 || lower > kAffineSourceLimit ||
      count == 0 || count > kMaximumAffineSourceCount ||
      count - 1 > kAffineSourceLimit - lower ||
      supports == nullptr || block_summaries == nullptr ||
      block_summary_capacity < summary_count ||
      delta == nullptr || candidate == nullptr ||
      poison_count == nullptr || summary_count == 0 ||
      summary_count > kMaximumGridX ||
      device_ranges_overlap(
          supports, count * sizeof(TgMobiusFusedSupport),
          block_summaries,
          summary_count *
              sizeof(TgMobiusAffineMqBlockSummary)) ||
      device_ranges_overlap(
          supports, count * sizeof(TgMobiusFusedSupport),
          delta, sizeof(TgMobiusPrefixMQ)) ||
      device_ranges_overlap(
          supports, count * sizeof(TgMobiusFusedSupport),
          candidate, sizeof(TgMobiusAffineMqThreadCandidates)) ||
      device_ranges_overlap(
          supports, count * sizeof(TgMobiusFusedSupport),
          poison_count, sizeof(std::uint32_t)) ||
      device_ranges_overlap(
          block_summaries,
          summary_count *
              sizeof(TgMobiusAffineMqBlockSummary),
          delta, sizeof(TgMobiusPrefixMQ)) ||
      device_ranges_overlap(
          block_summaries,
          summary_count *
              sizeof(TgMobiusAffineMqBlockSummary),
          candidate, sizeof(TgMobiusAffineMqThreadCandidates)) ||
      device_ranges_overlap(
          block_summaries,
          summary_count *
              sizeof(TgMobiusAffineMqBlockSummary),
          poison_count, sizeof(std::uint32_t)) ||
      device_ranges_overlap(
          delta, sizeof(TgMobiusPrefixMQ),
          candidate, sizeof(TgMobiusAffineMqThreadCandidates)) ||
      device_ranges_overlap(
          delta, sizeof(TgMobiusPrefixMQ),
          poison_count, sizeof(std::uint32_t)) ||
      device_ranges_overlap(
          candidate, sizeof(TgMobiusAffineMqThreadCandidates),
          poison_count, sizeof(std::uint32_t))) {
    return cudaErrorInvalidValue;
  }
  affine_mq_block_summaries_from_fused_supports<<<
      static_cast<unsigned int>(summary_count),
      kThreadsPerBlock, 0, stream>>>(
      lower, count, supports, block_summaries, poison_count);
  cudaError_t status = check_launch();
  if (status != cudaSuccess) return status;
  return launch_tg_mobius_affine_mq_compose_block_summaries_qualification(
      block_summaries, summary_count, delta, candidate, stream);
}

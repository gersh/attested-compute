// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>

#include <cuda_runtime_api.h>

// Exact integer support for a segmented Moebius computation.  The product
// and count refer to the distinct supplied base primes which divide n.
// squareful is one exactly when some supplied p has p^2 | n.  When the caller
// supplies every prime through sqrt(segment upper), mobius is the mathematical
// Moebius value of n.
struct alignas(8) TgMobiusSupport {
  std::uint64_t base_prime_product;
  std::uint32_t distinct_base_prime_count;
  std::uint32_t squareful;
  std::int32_t mobius;
  std::uint32_t reserved;
};

static_assert(sizeof(TgMobiusSupport) == 24);

struct alignas(8) TgMobiusCompactSupport {
  std::uint64_t base_prime_product;
  // Bits 0..30 are the distinct-base-prime count; bit 31 is squareful.
  std::uint32_t packed_count_squareful;
  std::uint32_t reserved;
};

static_assert(sizeof(TgMobiusCompactSupport) == 16);

// Guarded production one-word support encoding for n <= 10^16.
//
//   bits  0..53: product of distinct supplied prime divisors
//   bits 54..58: number of those divisors
//   bit      59: some supplied p satisfies p^2 | n
//   bits 60..62: reserved zero
//   bit      63: fail-closed arithmetic poison
//
// The product divides n and 10^16 < 2^54.  Fourteen distinct primes cannot
// divide n: the product of the first fourteen primes is
// 13082761331670030 > 10^16, whereas the first thirteen product is
// 304250263527210.  Five count bits are therefore more than sufficient.
inline constexpr unsigned int kTgMobiusFusedProductBits = 54;
inline constexpr unsigned int kTgMobiusFusedCountBits = 5;
inline constexpr unsigned int kTgMobiusFusedCountShift = 54;
inline constexpr std::uint64_t kTgMobiusFusedProductMask =
    (std::uint64_t{1} << kTgMobiusFusedProductBits) - 1;
inline constexpr std::uint64_t kTgMobiusFusedCountMask =
    ((std::uint64_t{1} << kTgMobiusFusedCountBits) - 1)
    << kTgMobiusFusedCountShift;
inline constexpr std::uint64_t kTgMobiusFusedSquarefulBit =
    std::uint64_t{1} << 59;
inline constexpr std::uint64_t kTgMobiusFusedReservedMask =
    std::uint64_t{7} << 60;
inline constexpr std::uint64_t kTgMobiusFusedPoisonBit =
    std::uint64_t{1} << 63;
inline constexpr std::uint32_t kTgMobiusFusedMaximumDistinctPrimes = 13;
inline constexpr std::uint64_t kTgMobiusPrimorial13 =
    304'250'263'527'210ULL;
inline constexpr std::uint64_t kTgMobiusPrimorial14 =
    13'082'761'331'670'030ULL;
inline constexpr std::uint64_t kTgMobiusSourceLimit =
    10'000'000'000'000'000ULL;
inline constexpr std::uint32_t kTgMobiusMaximumPrime = 100'000'000U;
inline constexpr std::size_t kTgMobiusMultiblockDensePrimeLimit = 200;
// The unseeded qualification path starts at p=2.
inline constexpr std::size_t kTgMobiusMultiblockSlotsPerPrime = 512;
// The production residue-235 path starts its event suffix at p=7.  The first
// constant is the exact minimum for the unchanged public maximum row count;
// the selected launch value remains a separately benchmarked performance
// choice and must never be smaller than that minimum.
inline constexpr std::size_t
    kTgMobiusResidue235MinimumSlotsPerPrime = 147;
inline constexpr std::size_t
    kTgMobiusResidue235MultiblockSlotsPerPrime = 512;
inline constexpr std::size_t kTgMobiusThreadsPerBlock = 256;
#ifndef SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD
#define SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD 256
#endif
inline constexpr std::size_t kTgMobiusAffineRowsPerThread =
    SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD;
inline constexpr std::size_t kTgMobiusAffineRowsPerBlock =
    kTgMobiusThreadsPerBlock * kTgMobiusAffineRowsPerThread;
inline constexpr std::size_t
    kTgMobiusMultiblockIterationsPerThread = 4'096;
inline constexpr std::size_t kTgMobiusMultipleEventsPerBlock =
    kTgMobiusThreadsPerBlock *
    kTgMobiusMultiblockIterationsPerThread;
inline constexpr std::size_t kTgMobiusMultiblockMaximumCount =
    2 * kTgMobiusMultiblockSlotsPerPrime *
    kTgMobiusMultipleEventsPerBlock;
inline constexpr std::size_t kTgMobiusResidue235Modulus =
    2 * 2 * 3 * 3 * 5 * 5;
inline constexpr std::size_t kTgMobiusResidue235PrimeCount = 3;
// Qualification-only extension of the exact residue-235 seed, whose pure
// arithmetic specification and refinement theorem are
// SparkInterval/TernaryGoldbach/MobiusResidue2357.lean.  The existing
// 900-word table is still used; the p=7 contribution is derived per row from
// n modulo 49, so this candidate does not materialize a 44,100-word CRT table.
inline constexpr std::size_t kTgMobiusResidue2357Modulus = 7 * 7;
inline constexpr std::size_t kTgMobiusResidue2357PrimeCount = 4;
inline constexpr std::uint32_t
    kTgMobiusResidue2357SuffixMinimum = 11;
inline constexpr std::size_t
    kTgMobiusResidue2357MinimumSlotsPerPrime = 94;
// Qualification geometry, intentionally independent of the production
// residue-235 launch.  It may be changed only by an explicit bounded
// differential/performance qualification; production remains pinned above.
inline constexpr std::size_t
    kTgMobiusResidue2357MultiblockSlotsPerPrime = 512;
// Qualification-only extension through p=11.  Its pure arithmetic seed,
// packed-word bounds, exact mod-121 update, and suffix-capacity proof live in
// SparkInterval/TernaryGoldbach/MobiusResidue235711.lean.  Keep the launch
// geometry equal to the p=7 candidate while measuring the seed change; this
// isolates arithmetic work removal from any future geometry experiment.
inline constexpr std::size_t kTgMobiusResidue235711Modulus = 11 * 11;
inline constexpr std::size_t kTgMobiusResidue235711PrimeCount = 5;
inline constexpr std::uint32_t
    kTgMobiusResidue235711SuffixMinimum = 13;
inline constexpr std::size_t
    kTgMobiusResidue235711MinimumSlotsPerPrime = 79;
inline constexpr std::size_t
    kTgMobiusResidue235711MultiblockSlotsPerPrime = 512;
// Qualification-only extension through p=13.  It preserves the p=11
// candidate and derives the p=13 contribution from n modulo 169.  The
// suffix therefore starts at 17.  Its launch identity remains separate from
// both production and the p=11 qualification.
inline constexpr std::size_t kTgMobiusResidue23571113Modulus = 13 * 13;
inline constexpr std::size_t kTgMobiusResidue23571113PrimeCount = 6;
inline constexpr std::uint32_t
    kTgMobiusResidue23571113SuffixMinimum = 17;
inline constexpr std::size_t
    kTgMobiusResidue23571113MinimumSlotsPerPrime = 61;
inline constexpr std::size_t
    kTgMobiusResidue23571113MultiblockSlotsPerPrime = 512;
// The split-square production path gives one whole block to each of the
// first suffix primes' p^2 strike streams.  Later primes have at most a small
// number of square multiples per public shard and use one thread per prime.
// This is a performance partition only; the two schedules cover disjoint
// prime-index ranges.
inline constexpr std::size_t kTgMobiusSplitSquareDensePrimeLimit = 200;

static_assert(kTgMobiusSourceLimit < (std::uint64_t{1} << 54));
static_assert(
    static_cast<std::uint64_t>(kTgMobiusMaximumPrime) *
        kTgMobiusMaximumPrime ==
    kTgMobiusSourceLimit);
static_assert(kTgMobiusPrimorial13 <= kTgMobiusSourceLimit);
static_assert(kTgMobiusPrimorial14 > kTgMobiusSourceLimit);
static_assert(
    kTgMobiusFusedMaximumDistinctPrimes <
    (std::uint32_t{1} << kTgMobiusFusedCountBits));
static_assert(kTgMobiusMultipleEventsPerBlock == 1'048'576);
static_assert(kTgMobiusAffineRowsPerThread > 0);
static_assert(kTgMobiusAffineRowsPerThread <= 512);
static_assert(
    (kTgMobiusAffineRowsPerThread &
     (kTgMobiusAffineRowsPerThread - 1)) == 0);
static_assert(kTgMobiusAffineRowsPerBlock <= 131'072);
static_assert(kTgMobiusMultiblockMaximumCount == 1'073'741'824);
static_assert(kTgMobiusResidue235Modulus == 900);
static_assert(kTgMobiusResidue2357Modulus == 49);
static_assert(kTgMobiusResidue2357SuffixMinimum == 11);
static_assert(kTgMobiusResidue235711Modulus == 121);
static_assert(kTgMobiusResidue235711SuffixMinimum == 13);
static_assert(kTgMobiusResidue23571113Modulus == 169);
static_assert(kTgMobiusResidue23571113SuffixMinimum == 17);
static_assert(
    (kTgMobiusMultiblockMaximumCount + 7 - 1) / 7 <=
    kTgMobiusResidue235MinimumSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    kTgMobiusResidue235MinimumSlotsPerPrime <=
    kTgMobiusResidue235MultiblockSlotsPerPrime);
static_assert(
    (kTgMobiusMultiblockMaximumCount + 7 - 1) / 7 <=
    kTgMobiusResidue235MultiblockSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount + 7 - 1) / 7 >
    (kTgMobiusResidue235MinimumSlotsPerPrime - 1) *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue2357SuffixMinimum - 1) /
            kTgMobiusResidue2357SuffixMinimum <=
    kTgMobiusResidue2357MinimumSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    kTgMobiusResidue2357MinimumSlotsPerPrime <=
    kTgMobiusResidue2357MultiblockSlotsPerPrime);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue2357SuffixMinimum - 1) /
            kTgMobiusResidue2357SuffixMinimum <=
    kTgMobiusResidue2357MultiblockSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue2357SuffixMinimum - 1) /
            kTgMobiusResidue2357SuffixMinimum >
    (kTgMobiusResidue2357MinimumSlotsPerPrime - 1) *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue235711SuffixMinimum - 1) /
            kTgMobiusResidue235711SuffixMinimum <=
    kTgMobiusResidue235711MinimumSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    kTgMobiusResidue235711MinimumSlotsPerPrime <=
    kTgMobiusResidue235711MultiblockSlotsPerPrime);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue235711SuffixMinimum - 1) /
            kTgMobiusResidue235711SuffixMinimum <=
    kTgMobiusResidue235711MultiblockSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue235711SuffixMinimum - 1) /
            kTgMobiusResidue235711SuffixMinimum >
    (kTgMobiusResidue235711MinimumSlotsPerPrime - 1) *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue23571113SuffixMinimum - 1) /
            kTgMobiusResidue23571113SuffixMinimum <=
    kTgMobiusResidue23571113MinimumSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    kTgMobiusResidue23571113MinimumSlotsPerPrime <=
    kTgMobiusResidue23571113MultiblockSlotsPerPrime);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue23571113SuffixMinimum - 1) /
            kTgMobiusResidue23571113SuffixMinimum <=
    kTgMobiusResidue23571113MultiblockSlotsPerPrime *
        kTgMobiusMultipleEventsPerBlock);
static_assert(
    (kTgMobiusMultiblockMaximumCount +
         kTgMobiusResidue23571113SuffixMinimum - 1) /
            kTgMobiusResidue23571113SuffixMinimum >
    (kTgMobiusResidue23571113MinimumSlotsPerPrime - 1) *
        kTgMobiusMultipleEventsPerBlock);

inline bool tg_mobius_host_roster_begins_235(
    const std::uint32_t* primes, std::size_t count) {
  return count >= kTgMobiusResidue235PrimeCount &&
         primes != nullptr &&
         primes[0] == 2 && primes[1] == 3 && primes[2] == 5;
}

inline bool tg_mobius_host_roster_begins_2357(
    const std::uint32_t* primes, std::size_t count) {
  return count >= kTgMobiusResidue2357PrimeCount &&
         primes != nullptr &&
         primes[0] == 2 && primes[1] == 3 &&
         primes[2] == 5 && primes[3] == 7;
}

inline bool tg_mobius_host_roster_begins_235711(
    const std::uint32_t* primes, std::size_t count) {
  return count >= kTgMobiusResidue235711PrimeCount &&
         primes != nullptr &&
         primes[0] == 2 && primes[1] == 3 &&
         primes[2] == 5 && primes[3] == 7 &&
         primes[4] == 11;
}

inline bool tg_mobius_host_roster_begins_23571113(
    const std::uint32_t* primes, std::size_t count) {
  return count >= kTgMobiusResidue23571113PrimeCount &&
         primes != nullptr &&
         primes[0] == 2 && primes[1] == 3 &&
         primes[2] == 5 && primes[3] == 7 &&
         primes[4] == 11 && primes[5] == 13;
}

struct alignas(8) TgMobiusFusedSupport {
  std::uint64_t packed;
};

static_assert(sizeof(TgMobiusFusedSupport) == 8);

// Explicit qualification-only seed and rectangular launch selectors.  The
// enumerator values are stable receipt/API identities, not prime counts.
enum class TgMobiusResidueSeed : std::uint32_t {
  k235 = 235,
  k2357 = 2'357,
  k235711 = 235'711,
  k23571113 = 23'571'113,
};

enum class TgMobiusRectangularSlotMode : std::uint32_t {
  kRect2d512 = 1,
  kRect2dPower = 2,
  kRect2dExact = 3,
  kRect2dCountExact = 4,
};

// Host-computed launch witness for a qualification-only 2D divisor-event
// grid.  grid=(slots_per_prime,multiblock_prime_count,1), with
// prime_index=blockIdx.y and block_ordinal=blockIdx.x.  The arbitrary-width
// ownership theorem and the exact 147/94/79 maximum-count instantiations are
// in SparkInterval/TernaryGoldbach/MobiusRectangularCUDASchedule.lean.
struct TgMobiusRectangularLaunchGeometry {
  TgMobiusResidueSeed seed;
  TgMobiusRectangularSlotMode mode;
  std::uint64_t enclosing_lower;
  std::size_t enclosing_count;
  std::size_t seed_prime_count;
  std::uint32_t suffix_minimum_prime;
  std::size_t required_slots_per_prime;
  std::size_t slots_per_prime;
  std::size_t events_per_block;
  unsigned int grid_x;
  unsigned int grid_y;
  unsigned int grid_z;
  unsigned int threads_per_block;
};

// A shard contains at most 10^8 rows.  Every inclusive local Mertens prefix
// lies in [-10^8,10^8], and every local squarefree prefix lies in [0,10^8],
// so the device scan needs only one signed and one unsigned 32-bit word.
struct alignas(8) TgMobiusPrefixMQ {
  std::int32_t mertens;
  std::uint32_t squarefree;
};

static_assert(sizeof(TgMobiusPrefixMQ) == 8);
static_assert(100'000'000 < 2'147'483'647);

// One deterministic thread-local candidate set for the terminal-range affine
// Mertens/squarefree prototype.  ``order`` is twice the row offset plus zero
// for an integer endpoint and one for its right limit.
struct alignas(8) TgMobiusAffineMqBoundCandidate {
  std::int64_t value;
  std::uint32_t local_squarefree;
  std::uint32_t order;
};

static_assert(sizeof(TgMobiusAffineMqBoundCandidate) == 16);
static_assert(2 * 100'000'000 - 1 <
              std::numeric_limits<std::uint32_t>::max());

struct alignas(8) TgMobiusAffineMqThreadCandidates {
  TgMobiusAffineMqBoundCandidate hurst_lower;
  TgMobiusAffineMqBoundCandidate hurst_upper;
  TgMobiusAffineMqBoundCandidate squarefree_lower;
  TgMobiusAffineMqBoundCandidate squarefree_upper;
};

static_assert(sizeof(TgMobiusAffineMqThreadCandidates) == 64);

// Qualification-only associative summary for one consecutive tile.  The
// default candidate geometry is 256 threads x 256 rows = 65,536 rows; bounded
// qualification builds may select another rows-per-thread value.  `candidates`
// is expressed relative to the tile's zero incoming {M,Q} state; `delta`
// translates the following tile during ordered composition.
struct alignas(8) TgMobiusAffineMqBlockSummary {
  TgMobiusPrefixMQ delta;
  TgMobiusAffineMqThreadCandidates candidates;
};

static_assert(sizeof(TgMobiusAffineMqBlockSummary) == 72);

// Produce exact support records for n in [lower, lower + count).  base_primes
// must contain, exactly once and in increasing order, every prime not greater
// than floor(sqrt(lower + count - 1)) which divides at least one integer in the
// segment.  Supplying additional primes through that square-root bound is
// allowed.  The public runner constructs the complete prime list with an exact
// host sieve, filters only the device copy, and independently recomputes every
// output record from the complete list.
cudaError_t launch_tg_mobius_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusSupport* outputs, cudaStream_t stream = nullptr);

// Pack the finalized mathematical Möbius values into one signed byte per row.
// This is a transfer optimization only: the full support records remain the
// independently qualified device realization used to produce these bytes.
cudaError_t launch_tg_mobius_pack(
    const TgMobiusSupport* inputs, std::size_t count,
    std::int8_t* outputs, cudaStream_t stream = nullptr);

// Memory-compact realization of the same support algorithm.  It writes the
// final Möbius byte directly and retains product/count/squareful support in 16
// bytes per row for differential qualification.
cudaError_t launch_tg_mobius_compact_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusCompactSupport* supports, std::int8_t* mobius,
    cudaStream_t stream = nullptr);

// Guarded 8-byte realization of the same support algorithm.  Each
// divisor update is one serializable 64-bit CAS over the product, count, and
// squareful flag.  Bounds are checked in the CAS loop; a violation sets the
// poison bit and finalizes to a non-Möbius sentinel so qualification fails.
cudaError_t launch_tg_mobius_fused_segment(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    cudaStream_t stream = nullptr);

// Load-balanced realization of the same inline-squareful support equation.
// Up to the first kTgMobiusMultiblockDensePrimeLimit dense primes use
// kTgMobiusMultiblockSlotsPerPrime disjoint block slots per prime.  Each block
// owns a contiguous range of kTgMobiusMultipleEventsPerBlock multiple
// ordinals, so no (prime, multiple) event is omitted or processed twice.
// kTgMobiusMultiblockMaximumCount is the declared schedule bound.
cudaError_t launch_tg_mobius_fused_segment_multiblock_dense(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    cudaStream_t stream = nullptr);

// Residue-seeded inline-square reference realization.  The caller
// must validate that base_primes begins exactly [2,3,5].  Initialization
// loads the exact product/count/squareful contribution of those primes from
// the residue class modulo 2^2*3^2*5^2, and the event kernels start at 7.
// Because base_primes is device memory, this asynchronous raw API validates
// the prefix length but cannot inspect its values without adding a device
// synchronization; exact prefix values are a caller precondition.  Both
// public runners validate their authenticated host roster before this call.
cudaError_t launch_tg_mobius_fused_segment_multiblock_dense_residue_235(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    cudaStream_t stream = nullptr);

// Support-only qualification/reference phase of the same inline-square
// residue-235 launch. It initializes and marks the packed support rows but
// deliberately does not materialize an intermediate one-byte Möbius array.
// It is retained for direct word-for-word comparison with the split-square
// production API below.
cudaError_t launch_tg_mobius_fused_support_multiblock_dense_residue_235(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports,
    cudaStream_t stream = nullptr);

// Production split-square realization.  Unlike the qualification API above,
// each (p,n) divisor event updates only product/count and performs no n mod
// p^2 operation.  After every such CAS kernel has completed in `stream`, a
// disjoint two-part p^2 schedule atomically ORs the squareful bit for exactly
// the rows divisible by p^2.  The first kTgMobiusSplitSquareDensePrimeLimit
// suffix primes use one block per prime; every remaining suffix prime uses
// one thread.  The stream order is part of this API: initialization, all
// distinct-factor updates, all square strikes, then caller finalization.
// `roster_invalid` is asynchronous device storage for one uint32.  The launch
// clears it, structurally validates the device roster before any prime
// arithmetic, and sets it to one on a malformed prefix, unsafe value, or
// non-increasing entry.  Invalid input initializes every support row with the
// poison bit; callers may reuse the scalar after the support phase.  This is
// a machine-safety check, not a replacement for authenticating roster
// primality and completeness.  The production runner performs an exact
// host-hash check followed by byte-for-byte device round-trip equality.
// Every fused multiblock entry point rejects overlap among its roster,
// support, optional Möbius-byte output, and roster-status device ranges
// before launch.
//
// The old inline-square API remains available immediately above as a
// differential qualification/reference realization.
cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_235_split_square(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

// Qualification-only p=7 seed candidate.  It preserves the production
// residue-235 table, derives the exact p=7 product/count/squareful update from
// each row's residue modulo 49, and starts both event schedules after the
// exact [2,3,5,7] prefix.  The device preflight requires that complete prefix,
// strictly increasing suffix entries at least 11, and the same machine
// bounds as the production split-square path.  These APIs are intentionally
// separate from the production entry point above until differential,
// sanitizer, and target-H100 performance qualification are complete.
cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_2357_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

// Byte-finalizing form of the same qualification candidate, retained for
// all-row old/new Möbius differential tests and one-shot runner experiments.
cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_2357_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

// Qualification-only p=11 seed candidate.  It extends the p=7 seed with the
// exact contribution determined by n modulo 121 and starts both event
// schedules after [2,3,5,7,11].  Device preflight rejects any other prefix,
// any suffix entry below 13, and every malformed/non-increasing machine
// roster before arithmetic.  The selected 512-slot geometry is deliberately
// identical to the p=7 candidate so qualification isolates only the seed.
cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_235711_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

// Qualification-only p=13 seed candidate.  It extends the p=11 seed with the
// exact contribution determined by n modulo 169 and starts both event
// schedules after [2,3,5,7,11,13].  The explicit APIs and receipt identity
// prevent accidental selection by the production/default path.
cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_23571113_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

cudaError_t
launch_tg_mobius_fused_segment_multiblock_dense_residue_23571113_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusFusedSupport* supports, std::int8_t* mobius,
    std::uint32_t* roster_invalid,
    cudaStream_t stream = nullptr);

// Qualification-only rectangular schedule.  The seed is explicit and the
// caller must retain the returned geometry in its qualification receipt.
// Host validation rejects unknown enum values, empty/out-of-range segments,
// more than 200 rectangular prime rows, insufficient/oversized slot counts,
// and device grid/thread limits before any launch.  A zero rectangular-prime
// suffix is valid and skips the 2D kernel rather than launching grid.y=0.
cudaError_t tg_mobius_rectangular_launch_geometry_qualification(
    std::uint64_t lower, std::size_t count,
    std::size_t multiblock_prime_count,
    TgMobiusResidueSeed seed,
    TgMobiusRectangularSlotMode mode,
    TgMobiusRectangularLaunchGeometry* geometry);

cudaError_t
launch_tg_mobius_fused_support_multiblock_dense_residue_rectangular_qualification(
    std::uint64_t lower, std::size_t count,
    const std::uint32_t* base_primes, std::size_t base_prime_count,
    std::size_t dense_prime_count,
    TgMobiusResidueSeed seed,
    TgMobiusRectangularSlotMode mode,
    TgMobiusFusedSupport* supports, std::uint32_t* roster_invalid,
    TgMobiusRectangularLaunchGeometry* geometry,
    cudaStream_t stream = nullptr);

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
    cudaStream_t stream = nullptr);

// Decode one packed support slice directly to the unscanned exact affine
// input rows {mu, mu != 0}.  Malformed/poison rows, including a zero product,
// a product larger than the represented number, or a product that does not
// divide that number, increment poison_count and contribute a neutral scan
// row; an accepted receipt requires the final count to be zero.  This removes
// the production-only write/read of an intermediate Möbius byte without
// changing the mathematical row equation.
cudaError_t launch_tg_mobius_fused_prefix_inputs(
    std::uint64_t lower, const TgMobiusFusedSupport* supports,
    std::size_t count, TgMobiusPrefixMQ* prefix_inputs,
    std::uint32_t* poison_count,
    cudaStream_t stream = nullptr);

// Count fail-closed values outside {-1,0,1} without transferring the row
// stream.  Production leaf summaries require this count to be zero.
cudaError_t launch_tg_mobius_poison_count(
    const std::int8_t* mobius, std::size_t count,
    std::uint32_t* poison_count, cudaStream_t stream = nullptr);

// Terminal-range affine MQ prototype.  It performs an exact ordered inclusive
// scan of compact Möbius bytes, exact-corrects every squarefree endpoint in
// checked 256-bit arithmetic, and emits deterministic thread-local extrema.
// The caller independently exact-rechecks every transferred thread-local
// squarefree extremum before accepting the final squarefree guard.  This
// prototype deliberately does not cover either little-Mertens component.
std::size_t tg_mobius_affine_mq_candidate_count(std::size_t count);
cudaError_t tg_mobius_affine_mq_workspace_size(
    std::size_t count, std::size_t* workspace_bytes);
cudaError_t launch_tg_mobius_affine_mq(
    std::uint64_t lower, const std::int8_t* mobius, std::size_t count,
    TgMobiusPrefixMQ* prefixes,
    TgMobiusAffineMqThreadCandidates* candidates,
    void* workspace, std::size_t workspace_bytes,
    cudaStream_t stream = nullptr);

// Production-shaped variant of the same exact affine scan.  It applies the
// lexicographic candidate selector hierarchically (thread -> block -> device)
// and emits exactly one 64-byte four-extrema record.  The supplied workspace
// is reused first by CUB and then as the block-candidate array.
std::size_t tg_mobius_affine_mq_reduced_candidate_count(std::size_t count);
cudaError_t tg_mobius_affine_mq_reduced_workspace_size(
    std::size_t count, std::size_t* workspace_bytes);
cudaError_t launch_tg_mobius_affine_mq_reduced(
    std::uint64_t lower, const std::int8_t* mobius, std::size_t count,
    TgMobiusPrefixMQ* prefixes,
    TgMobiusAffineMqThreadCandidates* candidate,
    void* workspace, std::size_t workspace_bytes,
    std::uint32_t* poison_count = nullptr,
    cudaStream_t stream = nullptr);

// Reduced affine scan starting from exact, unscanned {mu, mu != 0} rows
// already written by launch_tg_mobius_fused_prefix_inputs.  CUB overwrites
// the input rows with their inclusive prefixes.  Poison handling belongs to
// the packed-word finalizer and remains an explicit zero-count receipt field.
cudaError_t launch_tg_mobius_affine_mq_reduced_from_prefix_inputs(
    std::uint64_t lower, std::size_t count,
    TgMobiusPrefixMQ* prefix_inputs,
    TgMobiusAffineMqThreadCandidates* candidate,
    void* workspace, std::size_t workspace_bytes,
    cudaStream_t stream = nullptr);

// Qualification-only fused block-composition path.  It decodes packed
// supports, scans each consecutive tile locally (65,536 rows in the default
// 256-by-256 candidate geometry), emits one relative affine summary per tile,
// and composes those summaries in source order.  It never materializes or
// globally scans the count-row prefix array.
// All five device ranges (`supports`, `block_summaries`, `delta`, `candidate`,
// and `poison_count`) must be pairwise disjoint.
std::size_t tg_mobius_affine_mq_block_summary_count(std::size_t count);
std::size_t tg_mobius_affine_mq_rows_per_thread();
std::size_t tg_mobius_affine_mq_rows_per_block();

// Qualification-only ordered finalizer exposed separately so the
// summary-count crossover at 256 CUDA threads can be checked without
// synthesizing millions of input rows.  `summary_count` is bounded by the
// maximum 10^8-row leaf geometry.  Inputs must be consecutive, disjoint tile
// summaries emitted by the block-summary kernel for one valid leaf of at most
// 10^8 rows; that precondition makes all exact delta, candidate-translation,
// and witness sums fit their fixed-width fields.  The two outputs must be
// mutually disjoint and disjoint from the entire input summary range.
cudaError_t
launch_tg_mobius_affine_mq_compose_block_summaries_qualification(
    const TgMobiusAffineMqBlockSummary* block_summaries,
    std::size_t summary_count,
    TgMobiusPrefixMQ* delta,
    TgMobiusAffineMqThreadCandidates* candidate,
    cudaStream_t stream = nullptr);

cudaError_t
launch_tg_mobius_affine_mq_block_compose_from_fused_supports_qualification(
    std::uint64_t lower, std::size_t count,
    const TgMobiusFusedSupport* supports,
    TgMobiusAffineMqBlockSummary* block_summaries,
    std::size_t block_summary_capacity,
    TgMobiusPrefixMQ* delta,
    TgMobiusAffineMqThreadCandidates* candidate,
    std::uint32_t* poison_count,
    cudaStream_t stream = nullptr);

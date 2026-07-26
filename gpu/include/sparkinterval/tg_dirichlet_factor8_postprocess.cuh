// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <cuda_runtime.h>

#include <cstdint>

namespace sparkinterval::tg::dirichlet_factor8_postprocess {

constexpr std::uint32_t kUpsampleFactor = 8U;
constexpr std::uint32_t kTruncation = 20U;
constexpr std::int32_t kFirstTapOffset = -19;
constexpr std::int32_t kLastTapOffset = 20;
constexpr std::uint32_t kTapCount = 40U;
constexpr std::uint32_t kInterpolatedPhaseCount = 7U;
constexpr std::uint32_t kConvolutionThreads = 256U;
constexpr std::uint32_t kMaximumSharedSourceIntervals = 72U;
constexpr double kMinimumInterpolationErrorUpper = 8.6e-8;

enum SignCode : unsigned char {
  kNegative = 0U,
  kAmbiguous = 1U,
  kPositive = 2U,
  kReserved = 3U,
};

enum DeviceError : std::uint32_t {
  kSuccess = 0U,
  kInvalidInputInterval = 1U << 0U,
  kInvalidCoefficientInterval = 1U << 1U,
  kInvalidInterpolationError = 1U << 2U,
  kInputWindowOutsideShard = 1U << 3U,
  kNonFiniteArithmetic = 1U << 4U,
};

struct Interval {
  double lower;
  double upper;
};

struct DeviceSummary {
  unsigned long long negative_count;
  unsigned long long ambiguous_count;
  unsigned long long positive_count;
  unsigned long long adjacent_opposite_sign_count;
  std::uint32_t error_or;
  std::uint32_t reserved;
};

static_assert(sizeof(Interval) == 16U);
static_assert(sizeof(DeviceSummary) == 40U);

__device__ __forceinline__ bool validInterval(Interval value) {
  return isfinite(value.lower) && isfinite(value.upper) &&
         value.lower <= value.upper;
}

__device__ __forceinline__ Interval directedProductFourCorner(
    Interval left, Interval right) {
  const double ll_down = __dmul_rd(left.lower, right.lower);
  const double lu_down = __dmul_rd(left.lower, right.upper);
  const double ul_down = __dmul_rd(left.upper, right.lower);
  const double uu_down = __dmul_rd(left.upper, right.upper);
  const double ll_up = __dmul_ru(left.lower, right.lower);
  const double lu_up = __dmul_ru(left.lower, right.upper);
  const double ul_up = __dmul_ru(left.upper, right.lower);
  const double uu_up = __dmul_ru(left.upper, right.upper);
  return {
      fmin(fmin(ll_down, lu_down), fmin(ul_down, uu_down)),
      fmax(fmax(ll_up, lu_up), fmax(ul_up, uu_up)),
  };
}

// Every source coefficient interval is certified not to cross zero.  Once
// that invariant has been checked, monotonicity reduces the general
// eight-multiply four-corner hull to exactly two directed multiplications.
__device__ __forceinline__ Interval directedProductSignedCoefficient(
    Interval value, Interval coefficient) {
  if (coefficient.lower > 0.0) {
    if (value.lower >= 0.0) {
      return {__dmul_rd(value.lower, coefficient.lower),
              __dmul_ru(value.upper, coefficient.upper)};
    }
    if (value.upper <= 0.0) {
      return {__dmul_rd(value.lower, coefficient.upper),
              __dmul_ru(value.upper, coefficient.lower)};
    }
    return {__dmul_rd(value.lower, coefficient.upper),
            __dmul_ru(value.upper, coefficient.upper)};
  }
  // coefficient.upper < 0
  if (value.lower >= 0.0) {
    return {__dmul_rd(value.upper, coefficient.lower),
            __dmul_ru(value.lower, coefficient.upper)};
  }
  if (value.upper <= 0.0) {
    return {__dmul_rd(value.upper, coefficient.upper),
            __dmul_ru(value.lower, coefficient.lower)};
  }
  return {__dmul_rd(value.upper, coefficient.lower),
          __dmul_ru(value.lower, coefficient.lower)};
}

// The optimized path fuses the selected endpoint product with the running
// endpoint sum.  Explicit directed FMA has one rounding instead of the
// multiply-then-add reference path and therefore remains an enclosure while
// reducing both instruction count and radius growth.
__device__ __forceinline__ Interval directedAccumulateSignedCoefficient(
    Interval accumulator, Interval value, Interval coefficient) {
  if (coefficient.lower > 0.0) {
    if (value.lower >= 0.0) {
      return {__fma_rd(value.lower, coefficient.lower, accumulator.lower),
              __fma_ru(value.upper, coefficient.upper, accumulator.upper)};
    }
    if (value.upper <= 0.0) {
      return {__fma_rd(value.lower, coefficient.upper, accumulator.lower),
              __fma_ru(value.upper, coefficient.lower, accumulator.upper)};
    }
    return {__fma_rd(value.lower, coefficient.upper, accumulator.lower),
            __fma_ru(value.upper, coefficient.upper, accumulator.upper)};
  }
  if (value.lower >= 0.0) {
    return {__fma_rd(value.upper, coefficient.lower, accumulator.lower),
            __fma_ru(value.lower, coefficient.upper, accumulator.upper)};
  }
  if (value.upper <= 0.0) {
    return {__fma_rd(value.upper, coefficient.upper, accumulator.lower),
            __fma_ru(value.lower, coefficient.lower, accumulator.upper)};
  }
  return {__fma_rd(value.upper, coefficient.lower, accumulator.lower),
          __fma_ru(value.lower, coefficient.lower, accumulator.upper)};
}

__device__ __forceinline__ unsigned char classify(Interval value) {
  if (value.upper < 0.0) return kNegative;
  if (value.lower > 0.0) return kPositive;
  return kAmbiguous;
}

// One thread owns one target sample.  The source samples are the real
// completed-L enclosures on Platt's 5/64 lattice.  Nonaligned target samples
// use the forty source terms at offsets -19,...,20; aligned targets reuse the
// source enclosure exactly.  Only source-checked coefficient intervals and
// an explicit nonnegative interpolation-error upper bound enter the kernel.
template <bool UseSignedCoefficientMonotonicity>
static __global__ void interpolateAndClassify(
    const Interval* source, std::int64_t firstSourceIndex,
    std::uint64_t sourceCount, const Interval* coefficients,
    std::int64_t firstFineIndex, std::uint64_t outputCount,
    double interpolationErrorUpper, unsigned char* codes,
    DeviceSummary* summary) {
  __shared__ Interval sourceTile[kMaximumSharedSourceIntervals];
  const std::uint64_t outputBase =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x;
  if (outputBase >= outputCount) return;
  if (blockDim.x != kConvolutionThreads) {
    if (threadIdx.x == 0U) {
      atomicOr(&summary->error_or, kInputWindowOutsideShard);
    }
    return;
  }
  const std::uint64_t blockOutputCount =
      min(static_cast<std::uint64_t>(blockDim.x), outputCount - outputBase);
  const std::int64_t blockFirstFine =
      firstFineIndex + static_cast<std::int64_t>(outputBase);
  const std::int64_t blockLastFine =
      blockFirstFine + static_cast<std::int64_t>(blockOutputCount - 1U);
  const std::int64_t tileFirstSource =
      blockFirstFine / kUpsampleFactor + kFirstTapOffset;
  const std::int64_t tileLastSource =
      blockLastFine / kUpsampleFactor + kLastTapOffset;
  const std::uint32_t tileCount = static_cast<std::uint32_t>(
      tileLastSource - tileFirstSource + 1);
  if (tileCount > kMaximumSharedSourceIntervals) {
    if (threadIdx.x == 0U) {
      atomicOr(&summary->error_or, kInputWindowOutsideShard);
    }
    return;
  }
  for (std::uint32_t tile = threadIdx.x; tile < tileCount;
       tile += blockDim.x) {
    const std::int64_t sourceIndex =
        tileFirstSource + static_cast<std::int64_t>(tile);
    const std::int64_t local = sourceIndex - firstSourceIndex;
    if (local < 0 || static_cast<std::uint64_t>(local) >= sourceCount) {
      const double invalid = __longlong_as_double(
          static_cast<long long>(0x7ff8000000000000ULL));
      sourceTile[tile] = {invalid, invalid};
      atomicOr(&summary->error_or, kInputWindowOutsideShard);
    } else {
      sourceTile[tile] = source[local];
    }
  }
  __syncthreads();
  const std::uint64_t output = outputBase + threadIdx.x;
  if (output < outputCount) {
    const std::int64_t fine =
        firstFineIndex + static_cast<std::int64_t>(output);
    if (fine < 0 || !isfinite(interpolationErrorUpper) ||
        interpolationErrorUpper < kMinimumInterpolationErrorUpper) {
      atomicOr(&summary->error_or, kInvalidInterpolationError);
      codes[output] = kReserved;
      return;
    }
    const std::int64_t center = fine / kUpsampleFactor;
    const std::uint32_t phase =
        static_cast<std::uint32_t>(fine % kUpsampleFactor);
    Interval enclosure{};
    std::uint32_t error = kSuccess;
    if (phase == 0U) {
      const std::int64_t local = center - tileFirstSource;
      if (local < 0 || static_cast<std::uint64_t>(local) >= tileCount) {
        error |= kInputWindowOutsideShard;
      } else {
        enclosure = sourceTile[local];
        if (!validInterval(enclosure)) error |= kInvalidInputInterval;
      }
    } else {
      enclosure = {0.0, 0.0};
      const std::uint64_t coefficientBase =
          static_cast<std::uint64_t>(phase - 1U) * kTapCount;
      for (std::uint32_t tap = 0U; tap < kTapCount; ++tap) {
        const std::int64_t sourceIndex =
            center + kFirstTapOffset + static_cast<std::int64_t>(tap);
        const std::int64_t local = sourceIndex - tileFirstSource;
        if (local < 0 || static_cast<std::uint64_t>(local) >= tileCount) {
          error |= kInputWindowOutsideShard;
          continue;
        }
        const Interval input = sourceTile[local];
        const Interval weight = coefficients[coefficientBase + tap];
        if (!validInterval(input)) error |= kInvalidInputInterval;
        if (!validInterval(weight) ||
            !(weight.lower > 0.0 || weight.upper < 0.0)) {
          error |= kInvalidCoefficientInterval;
        }
        if (error != kSuccess) continue;
        if constexpr (UseSignedCoefficientMonotonicity) {
          enclosure =
              directedAccumulateSignedCoefficient(enclosure, input, weight);
        } else {
          const Interval product = directedProductFourCorner(input, weight);
          enclosure.lower = __dadd_rd(enclosure.lower, product.lower);
          enclosure.upper = __dadd_ru(enclosure.upper, product.upper);
        }
      }
      if (error == kSuccess) {
        enclosure.lower =
            __dsub_rd(enclosure.lower, interpolationErrorUpper);
        enclosure.upper =
            __dadd_ru(enclosure.upper, interpolationErrorUpper);
      }
    }
    if (error == kSuccess &&
        (!validInterval(enclosure) || !isfinite(enclosure.lower) ||
         !isfinite(enclosure.upper))) {
      error |= kNonFiniteArithmetic;
    }
    if (error != kSuccess) {
      atomicOr(&summary->error_or, error);
      codes[output] = kReserved;
      return;
    }
    const unsigned char code = classify(enclosure);
    codes[output] = code;
    if (code == kNegative) {
      atomicAdd(&summary->negative_count, 1ULL);
    } else if (code == kPositive) {
      atomicAdd(&summary->positive_count, 1ULL);
    } else {
      atomicAdd(&summary->ambiguous_count, 1ULL);
    }
  }
}

static __global__ void countAdjacentOppositeSigns(
    const unsigned char* codes, std::uint64_t count,
    DeviceSummary* summary) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index + 1U < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const unsigned char left = codes[index];
    const unsigned char right = codes[index + 1U];
    if ((left == kNegative && right == kPositive) ||
        (left == kPositive && right == kNegative)) {
      atomicAdd(&summary->adjacent_opposite_sign_count, 1ULL);
    }
  }
}

// Four outputs per byte and one byte owner avoids atomics and makes unused
// high lanes canonical zeroes.
static __global__ void packCodes(const unsigned char* codes,
                                 std::uint64_t count,
                                 unsigned char* packed) {
  const std::uint64_t byteCount = (count + 3U) / 4U;
  for (std::uint64_t byte =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       byte < byteCount;
       byte += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    unsigned char value = 0U;
    for (unsigned lane = 0U; lane < 4U; ++lane) {
      const std::uint64_t index = byte * 4U + lane;
      if (index < count) {
        value |= static_cast<unsigned char>(codes[index] << (2U * lane));
      }
    }
    packed[byte] = value;
  }
}

}  // namespace sparkinterval::tg::dirichlet_factor8_postprocess

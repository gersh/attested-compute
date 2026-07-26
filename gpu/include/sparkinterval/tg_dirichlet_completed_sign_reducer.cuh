// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_booker_smallq_certified.hpp"
#include "sparkinterval/tg_dirichlet_lattice.hpp"
#include "sparkinterval/tg_dirichlet_strict_sign_pack.cuh"

#include <cuda_runtime.h>

#include <cstdint>
#include <limits>

namespace sparkinterval::tg::dirichlet_completed_sign_reducer {

namespace dl = dirichlet_lattice;
namespace sc = dirichlet_booker_smallq_certified;
namespace sign_pack = dirichlet_strict_sign_pack;

inline constexpr std::uint32_t kFormatVersion = 1U;
inline constexpr std::uint64_t kSourceStepNumerator = 5U;
inline constexpr std::uint64_t kSourceDenominator = 64U;
inline constexpr std::uint32_t kSourceSampleCount = 127988U;
inline constexpr std::uint32_t kMaximumModulus = 400000U;
inline constexpr std::uint32_t kMaximumFrameSamples = 64U;
inline constexpr std::uint32_t kDensePageCharacters = 4096U;
inline constexpr std::uint64_t kMaximumPackedSamples =
    ~std::uint32_t{0};

// The dense state is intentionally independent of the number of ambiguity
// ranges.  A first pass produces one state and one range count per character;
// a device exclusive scan allocates exactly the sparse range payload; a
// second pass writes only those ranges.  No completed-L sample or two-bit
// sign stream has to cross the device boundary.
struct PhaseState {
  std::uint64_t sample_count;
  std::uint64_t first_t_numerator;
  std::uint64_t stop_t_numerator;
  std::uint64_t first_determinate_numerator;
  std::uint64_t last_determinate_numerator;
  std::uint64_t transition_count;
  std::uint64_t ambiguity_count;
  std::uint64_t ambiguity_range_count;
  std::uint64_t t_step_numerator;
  std::uint32_t leading_ambiguity_count;
  std::uint32_t trailing_ambiguity_count;
  std::int8_t first_sign;
  std::int8_t last_sign;
  std::uint8_t has_determinate;
  std::uint8_t reserved0;
  std::uint32_t status_or;
};

struct AmbiguityRange {
  std::uint64_t first_t_numerator;
  std::uint64_t stop_t_numerator;
};

struct DeviceSummary {
  std::uint32_t source_status_or;
  std::uint32_t reducer_error_or;
  std::uint64_t ambiguity_range_count;
};

// Exact TGDCSB03 dense-page totals.  Dense bytes live in a fixed-stride
// device staging array; dense_bytes is the canonical used prefix copied into
// the variable-length page payload before its sparse rows.
struct DensePageTotals {
  std::uint64_t ordinal_start;
  std::uint64_t character_count;
  std::uint64_t dense_bytes;
  std::uint64_t transition_count;
  std::uint64_t ambiguity_sample_count;
  std::uint64_t ambiguity_range_count;
  std::uint32_t sparse_character_count;
  std::uint32_t count_width;
  std::uint32_t record_width;
  std::uint32_t status_or;
};

struct DenseDecodedRecord {
  std::uint64_t transition_count;
  std::int8_t first_sign;
  std::int8_t last_sign;
  std::uint8_t has_determinate;
  std::uint8_t has_sparse;
};

enum ReducerError : std::uint32_t {
  kReducerSuccess = 0U,
  kInvalidLValue = 1U << 0U,
  kInvalidRootDisk = 1U << 1U,
  kInvalidFactorDisk = 1U << 2U,
  kInvalidParity = 1U << 3U,
  kCompletedDiskMissesRealAxis = 1U << 4U,
  kNonFiniteCompletedDisk = 1U << 5U,
  kCoordinateOverflow = 1U << 6U,
  kRangeLayoutMismatch = 1U << 7U,
  kRangeCapacityExceeded = 1U << 8U,
  kNonAdjacentState = 1U << 9U,
  kStateCounterOverflow = 1U << 10U,
  kMalformedState = 1U << 11U,
  kInvalidFrequencyId = 1U << 12U,
  kDensePackLayoutMismatch = 1U << 13U,
  kDensePackCounterOverflow = 1U << 14U,
};

static_assert(sizeof(PhaseState) == 88U);
static_assert(sizeof(AmbiguityRange) == 16U);
static_assert(sizeof(DeviceSummary) == 16U);
static_assert(sizeof(DensePageTotals) == 64U);
static_assert(sizeof(DenseDecodedRecord) == 16U);

__host__ __device__ __forceinline__ bool checkedAdd(
    std::uint64_t left, std::uint64_t right, std::uint64_t* result) {
  constexpr std::uint64_t maximum = ~std::uint64_t{0};
  if (left > maximum - right) return false;
  *result = left + right;
  return true;
}

__host__ __device__ __forceinline__ bool checkedMul(
    std::uint64_t left, std::uint64_t right, std::uint64_t* result) {
  constexpr std::uint64_t maximum = ~std::uint64_t{0};
  if (left != 0U &&
      right > maximum / left) {
    return false;
  }
  *result = left * right;
  return true;
}

__host__ __device__ __forceinline__ std::uint32_t denseCountWidth(
    std::uint64_t sample_count) {
  if (sample_count <= 1U) return 1U;
  std::uint64_t maximum_transition = sample_count - 1U;
  std::uint32_t width = 0U;
  while (maximum_transition != 0U) {
    ++width;
    maximum_transition >>= 1U;
  }
  return width;
}

__host__ __device__ __forceinline__ std::uint32_t denseRecordWidth(
    std::uint64_t sample_count) {
  return 4U + denseCountWidth(sample_count);
}

__host__ __device__ __forceinline__ std::uint64_t densePageCount(
    std::uint64_t character_count) {
  return character_count == 0U
             ? 0U
             : 1U + (character_count - 1U) / kDensePageCharacters;
}

__host__ __device__ __forceinline__ std::uint64_t densePackedBytes(
    std::uint64_t character_count, std::uint32_t record_width) {
  std::uint64_t bits = 0U;
  if (!checkedMul(character_count, record_width, &bits)) {
    return ~std::uint64_t{0};
  }
  return bits / 8U + static_cast<std::uint64_t>(bits % 8U != 0U);
}

__host__ __device__ __forceinline__ std::uint64_t densePageStrideBytes(
    std::uint64_t sample_count) {
  return densePackedBytes(
      kDensePageCharacters, denseRecordWidth(sample_count));
}

__device__ __forceinline__ double normUpper(double real, double imaginary) {
  return __dsqrt_ru(
      __dadd_ru(__dmul_ru(real, real), __dmul_ru(imaginary, imaginary)));
}

__device__ __forceinline__ double coordinateError(
    double center, double lower, double upper) {
  return fmax(__dsub_ru(center, lower), __dsub_ru(upper, center));
}

__device__ __forceinline__ bool validRectangle(dl::ComplexInterval value) {
  return isfinite(value.re.lo) && isfinite(value.re.hi) &&
         isfinite(value.im.lo) && isfinite(value.im.hi) &&
         value.re.lo <= value.re.hi && value.im.lo <= value.im.hi;
}

// Convert a directed rectangle to a containing Euclidean disk.  Scaling each
// endpoint by 1/2 avoids overflow in (lo + hi)/2.  The endpoint-to-center
// distances and Euclidean radius are rounded upward.
__device__ __forceinline__ sc::Disk rectangleToDisk(
    dl::ComplexInterval value) {
  const double real = __dadd_rn(__dmul_rn(0.5, value.re.lo),
                                __dmul_rn(0.5, value.re.hi));
  const double imaginary = __dadd_rn(__dmul_rn(0.5, value.im.lo),
                                     __dmul_rn(0.5, value.im.hi));
  const double real_error = coordinateError(
      real, value.re.lo, value.re.hi);
  const double imaginary_error = coordinateError(
      imaginary, value.im.lo, value.im.hi);
  return {real, imaginary, normUpper(real_error, imaginary_error)};
}

// This is the same directed disk product used by the certified Booker
// kernels.  The center is ordinary binary64 arithmetic; a separately
// directed rectangle encloses the exact center product, and its distance
// from the rounded center is added to the analytic disk-product radius.
__device__ __forceinline__ sc::Disk diskMul(sc::Disk left, sc::Disk right) {
  const double rr_lo = __dmul_rd(left.real, right.real);
  const double rr_hi = __dmul_ru(left.real, right.real);
  const double ii_lo = __dmul_rd(left.imaginary, right.imaginary);
  const double ii_hi = __dmul_ru(left.imaginary, right.imaginary);
  const double ri_lo = __dmul_rd(left.real, right.imaginary);
  const double ri_hi = __dmul_ru(left.real, right.imaginary);
  const double ir_lo = __dmul_rd(left.imaginary, right.real);
  const double ir_hi = __dmul_ru(left.imaginary, right.real);
  const double real_lo = __dsub_rd(rr_lo, ii_hi);
  const double real_hi = __dsub_ru(rr_hi, ii_lo);
  const double imaginary_lo = __dadd_rd(ri_lo, ir_lo);
  const double imaginary_hi = __dadd_ru(ri_hi, ir_hi);
  const double real =
      fma(left.real, right.real,
          -left.imaginary * right.imaginary);
  const double imaginary =
      fma(left.real, right.imaginary,
          left.imaginary * right.real);
  const double rounding =
      normUpper(coordinateError(real, real_lo, real_hi),
                coordinateError(imaginary, imaginary_lo, imaginary_hi));
  const double left_norm = normUpper(left.real, left.imaginary);
  const double right_norm = normUpper(right.real, right.imaginary);
  double radius =
      __dadd_ru(rounding, __dmul_ru(left_norm, right.radius));
  radius = __dadd_ru(radius, __dmul_ru(right_norm, left.radius));
  radius = __dadd_ru(radius,
                     __dmul_ru(left.radius, right.radius));
  return {real, imaginary, radius};
}

// Convert a bounded catalog (not the resident FFT values) once.  In
// particular, TGDRNRO1 rectangles are converted once per q before all
// character/sample products; there is no repeated host/device wire stream.
static __global__ void convertRectanglesToDisks(
    const dl::ComplexInterval* rectangles, std::uint64_t count,
    sc::Disk* disks, std::uint32_t error_bit, DeviceSummary* summary) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    std::uint32_t error = kReducerSuccess;
    sc::Disk result{};
    if (!validRectangle(rectangles[index])) {
      error |= error_bit;
    } else {
      result = rectangleToDisk(rectangles[index]);
      if (!sign_pack::validStrictSignDisk(result)) error |= error_bit;
    }
    disks[index] = result;
    if (error != 0U) atomicOr(&summary->reducer_error_or, error);
  }
}

// Source-oriented common-factor builder.  Arb supplies:
//   * two gamma(t)*exp(pi*t/4) disk rows, one for each parity;
//   * a certified conductor-phase disk at every checkpoint; and
//   * a certified exp(i*(5/128)*log(q/pi)) step disk.
// One block owns each checkpoint span.  Threads first build contiguous
// per-thread step powers, then an inclusive block prefix gives every thread
// the phase at the start of its chunk.  Each thread advances its short chunk
// in exact sample order.  This retains one unique checkpoint/sample owner and
// uses only directed disk multiplication, without serializing all 4096 rows
// through one CUDA thread.
static __global__ void buildParityFactorsFromCheckpoints(
    const sc::Disk* gamma_scaled,
    const sc::Disk* conductor_checkpoints,
    sc::Disk conductor_step,
    std::uint32_t sample_count,
    std::uint32_t checkpoint_span,
    std::uint32_t checkpoint_count,
    sc::Disk* parity_factors,
    DeviceSummary* summary) {
  __shared__ sc::Disk chunk_prefix[256];
  __shared__ std::uint32_t block_error;
  const sc::Disk identity{1.0, 0.0, 0.0};
  for (std::uint32_t checkpoint = blockIdx.x;
       checkpoint < checkpoint_count;
       checkpoint += gridDim.x) {
    if (threadIdx.x == 0U) block_error = kReducerSuccess;
    __syncthreads();
    const std::uint64_t start64 =
        static_cast<std::uint64_t>(checkpoint) * checkpoint_span;
    const std::uint32_t start =
        start64 > sample_count ? sample_count
                               : static_cast<std::uint32_t>(start64);
    const std::uint64_t candidate_stop = start64 + checkpoint_span;
    const std::uint64_t stop64 =
        candidate_stop < static_cast<std::uint64_t>(sample_count)
            ? candidate_stop
            : static_cast<std::uint64_t>(sample_count);
    const std::uint32_t stop = static_cast<std::uint32_t>(stop64);
    const sc::Disk checkpoint_phase =
        conductor_checkpoints[checkpoint];
    if (checkpoint_span == 0U || start >= sample_count ||
        !sign_pack::validStrictSignDisk(checkpoint_phase) ||
        !sign_pack::validStrictSignDisk(conductor_step)) {
      atomicOr(&block_error, kInvalidFactorDisk);
    }
    const std::uint32_t span = stop >= start ? stop - start : 0U;
    const std::uint32_t chunk =
        (span + blockDim.x - 1U) / blockDim.x;
    const std::uint64_t local_start64 =
        static_cast<std::uint64_t>(start) +
        static_cast<std::uint64_t>(threadIdx.x) * chunk;
    const std::uint32_t local_start =
        local_start64 < stop ? static_cast<std::uint32_t>(local_start64)
                             : stop;
    const std::uint64_t local_stop64 =
        local_start64 + static_cast<std::uint64_t>(chunk);
    const std::uint32_t local_stop =
        local_stop64 < stop ? static_cast<std::uint32_t>(local_stop64)
                            : stop;
    sc::Disk chunk_power = identity;
    for (std::uint32_t sample = local_start; sample < local_stop;
         ++sample) {
      chunk_power = diskMul(chunk_power, conductor_step);
      if (!sign_pack::validStrictSignDisk(chunk_power)) {
        atomicOr(&block_error, kInvalidFactorDisk);
      }
    }
    chunk_prefix[threadIdx.x] = chunk_power;
    __syncthreads();
    for (std::uint32_t offset = 1U; offset < blockDim.x;
         offset <<= 1U) {
      const sc::Disk current = chunk_prefix[threadIdx.x];
      const sc::Disk left =
          threadIdx.x >= offset
              ? chunk_prefix[threadIdx.x - offset]
              : identity;
      __syncthreads();
      sc::Disk combined = current;
      if (threadIdx.x >= offset) {
        combined = diskMul(left, current);
        if (!sign_pack::validStrictSignDisk(combined)) {
          atomicOr(&block_error, kInvalidFactorDisk);
        }
      }
      __syncthreads();
      chunk_prefix[threadIdx.x] = combined;
      __syncthreads();
    }
    const sc::Disk preceding_power =
        threadIdx.x == 0U ? identity
                          : chunk_prefix[threadIdx.x - 1U];
    sc::Disk phase = checkpoint_phase;
    if (local_start < local_stop && threadIdx.x != 0U) {
      phase = diskMul(checkpoint_phase, preceding_power);
      if (!sign_pack::validStrictSignDisk(phase)) {
        atomicOr(&block_error, kInvalidFactorDisk);
      }
    }
    __syncthreads();
    std::uint32_t error = block_error;
    for (std::uint32_t sample = local_start;
         sample < local_stop && error == kReducerSuccess; ++sample) {
      for (std::uint32_t parity = 0U; parity < 2U; ++parity) {
        const sc::Disk gamma =
            gamma_scaled[
                static_cast<std::uint64_t>(parity) * sample_count +
                sample];
        if (!sign_pack::validStrictSignDisk(gamma)) {
          error |= kInvalidFactorDisk;
          break;
        }
        const sc::Disk factor = diskMul(phase, gamma);
        if (!sign_pack::validStrictSignDisk(factor)) {
          error |= kInvalidFactorDisk;
          break;
        }
        parity_factors[
            static_cast<std::uint64_t>(parity) * sample_count +
            sample] = factor;
      }
      if (sample + 1U < local_stop && error == kReducerSuccess) {
        phase = diskMul(phase, conductor_step);
        if (!sign_pack::validStrictSignDisk(phase)) {
          error |= kInvalidFactorDisk;
        }
      }
    }
    if (error != 0U) atomicOr(&summary->reducer_error_or, error);
    __syncthreads();
  }
}

__device__ __forceinline__ std::int8_t classifyCompletedDisk(
    sc::Disk value, std::uint32_t* error) {
  if (!sign_pack::validStrictSignDisk(value)) {
    *error |= kNonFiniteCompletedDisk;
    return 0;
  }
  // The Hardy multiplier/root convention says the completed critical-line
  // value is real.  A computed disk that does not even meet the real axis is
  // inconsistent with that convention and fails closed instead of being
  // silently projected to its real coordinate.
  if (fabs(value.imaginary) > value.radius) {
    *error |= kCompletedDiskMissesRealAxis;
    return 0;
  }
  const double boundary =
      nextafter(value.radius,
                __longlong_as_double(0x7ff0000000000000LL));
  if (!isfinite(boundary)) {
    *error |= kNonFiniteCompletedDisk;
    return 0;
  }
  if (value.real < -boundary) return -1;
  if (value.real > boundary) return 1;
  return 0;
}

__device__ __forceinline__ std::int8_t classifyItem(
    dl::ComplexInterval l_value, std::uint32_t source_status,
    sc::Disk root, sc::Disk factor, std::uint32_t parity,
    std::uint32_t* source_status_or, std::uint32_t* error) {
  *source_status_or |= source_status;
  if (source_status != 0U) return 0;
  if (!validRectangle(l_value)) {
    *error |= kInvalidLValue;
    return 0;
  }
  if (!sign_pack::validStrictSignDisk(root)) {
    *error |= kInvalidRootDisk;
    return 0;
  }
  if (!sign_pack::validStrictSignDisk(factor)) {
    *error |= kInvalidFactorDisk;
    return 0;
  }
  if (parity > 1U) {
    *error |= kInvalidParity;
    return 0;
  }
  const sc::Disk l_disk = rectangleToDisk(l_value);
  if (!sign_pack::validStrictSignDisk(l_disk)) {
    *error |= kInvalidLValue;
    return 0;
  }
  return classifyCompletedDisk(
      diskMul(diskMul(root, factor), l_disk), error);
}

__host__ __device__ __forceinline__ bool sampleNumerator(
    std::uint64_t first_t_numerator, std::uint64_t step,
    std::uint64_t sample, std::uint64_t* result) {
  std::uint64_t offset = 0U;
  return checkedMul(step, sample, &offset) &&
         checkedAdd(first_t_numerator, offset, result);
}

__host__ __device__ __forceinline__ bool validPhaseState(
    const PhaseState& state);

// One thread owns a complete character.  Scheduled FFT frames are bounded by
// 64 ordinates, so the serial scan is short and preserves exact sample order
// without atomics.  The expensive completed-L values never leave the GPU.
static __global__ void reduceCompletedSigns(
    const dl::ComplexInterval* l_values,
    // Nullable.  The in-process allchars path has one already validated
    // frame-level status and passes nullptr here; per-item words exist only
    // for bounded differential adapters that already own such an array.
    const std::uint32_t* source_statuses,
    std::uint32_t frame_source_status,
    const sc::Disk* roots,
    const sc::Disk* parity_factors,
    const std::uint8_t* parities,
    // Canonical primitive ordinal -> allchars frequency id.  allchars keeps
    // each t row contiguous, so the reducer reads
    // l_values[sample * frequency_stride + frequency_ids[ordinal]] directly
    // from TransformPlan::DeviceTransformResult without a transpose.
    const std::uint64_t* frequency_ids,
    std::uint64_t frequency_stride,
    std::uint32_t character_count,
    std::uint32_t sample_count,
    std::uint64_t first_t_numerator,
    std::uint64_t t_step_numerator,
    PhaseState* states,
    std::uint64_t* range_counts,
    DeviceSummary* summary) {
  for (std::uint32_t character = blockIdx.x * blockDim.x + threadIdx.x;
       character < character_count;
       character += blockDim.x * gridDim.x) {
    PhaseState state{};
    state.sample_count = sample_count;
    state.first_t_numerator = first_t_numerator;
    state.t_step_numerator = t_step_numerator;
    std::uint32_t error = kReducerSuccess;
    std::uint32_t source_or = 0U;
    if (sample_count == 0U || sample_count > kMaximumFrameSamples ||
        t_step_numerator != kSourceStepNumerator ||
        frequency_stride == 0U) {
      error |= kMalformedState;
    }
    if (!sampleNumerator(first_t_numerator, t_step_numerator,
                         sample_count, &state.stop_t_numerator)) {
      error |= kCoordinateOverflow;
    }
    const std::uint32_t parity = parities[character];
    const std::uint64_t frequency = frequency_ids[character];
    if (frequency >= frequency_stride) error |= kInvalidFrequencyId;
    const std::uint64_t safe_frequency =
        frequency < frequency_stride ? frequency : 0U;
    bool open_ambiguity = false;
    bool seen_determinate = false;
    for (std::uint32_t sample = 0U;
         sample < sample_count && (error & kMalformedState) == 0U;
         ++sample) {
      std::uint64_t numerator = 0U;
      if (!sampleNumerator(first_t_numerator, t_step_numerator,
                           sample, &numerator)) {
        error |= kCoordinateOverflow;
        break;
      }
      const std::uint64_t flat =
          static_cast<std::uint64_t>(sample) * frequency_stride +
          safe_frequency;
      const std::uint32_t item_status =
          source_statuses == nullptr ? frame_source_status
                                     : source_statuses[flat];
      const std::uint32_t factor_parity = parity <= 1U ? parity : 0U;
      const std::int8_t sign = classifyItem(
          l_values[flat], item_status, roots[character],
          parity_factors[
              static_cast<std::uint64_t>(factor_parity) * sample_count +
              sample],
          parity, &source_or, &error);
      if (sign == 0) {
        ++state.ambiguity_count;
        if (!open_ambiguity) {
          open_ambiguity = true;
          ++state.ambiguity_range_count;
        }
        if (!seen_determinate) ++state.leading_ambiguity_count;
        ++state.trailing_ambiguity_count;
        continue;
      }
      open_ambiguity = false;
      if (!seen_determinate) {
        state.has_determinate = 1U;
        state.first_determinate_numerator = numerator;
        state.first_sign = sign;
        seen_determinate = true;
      } else if (state.last_sign != sign) {
        ++state.transition_count;
      }
      state.last_determinate_numerator = numerator;
      state.last_sign = sign;
      state.trailing_ambiguity_count = 0U;
    }
    state.status_or = source_or | error;
    states[character] = state;
    range_counts[character] = state.ambiguity_range_count;
    if (source_or != 0U) atomicOr(&summary->source_status_or, source_or);
    if (error != 0U) atomicOr(&summary->reducer_error_or, error);
    if (state.ambiguity_range_count != 0U) {
      atomicAdd(
          reinterpret_cast<unsigned long long*>(
              &summary->ambiguity_range_count),
          static_cast<unsigned long long>(state.ambiguity_range_count));
    }
  }
}

// Recompute only the three-way sign decision and write the exact maximal
// ambiguity ranges into offsets obtained from the device prefix scan.
static __global__ void writeAmbiguityRanges(
    const dl::ComplexInterval* l_values,
    const std::uint32_t* source_statuses,
    std::uint32_t frame_source_status,
    const sc::Disk* roots,
    const sc::Disk* parity_factors,
    const std::uint8_t* parities,
    const std::uint64_t* frequency_ids,
    std::uint64_t frequency_stride,
    std::uint32_t character_count,
    std::uint32_t sample_count,
    std::uint64_t first_t_numerator,
    std::uint64_t t_step_numerator,
    const PhaseState* states,
    const std::uint64_t* range_offsets,
    std::uint64_t range_capacity,
    AmbiguityRange* ranges,
    // Optional sparse tag.  Production supplies this and copies only
    // (ordinal, range) rows after a device scan/reduction; the 16-byte KAT
    // path leaves it null.
    std::uint64_t* range_primitive_ordinals,
    DeviceSummary* summary) {
  for (std::uint32_t character = blockIdx.x * blockDim.x + threadIdx.x;
       character < character_count;
       character += blockDim.x * gridDim.x) {
    const std::uint64_t begin = range_offsets[character];
    const std::uint64_t end = range_offsets[character + 1U];
    const PhaseState expected = states[character];
    std::uint32_t error = kReducerSuccess;
    std::uint64_t frame_stop = 0U;
    if (!validPhaseState(expected) ||
        expected.sample_count != sample_count ||
        expected.first_t_numerator != first_t_numerator ||
        expected.t_step_numerator != t_step_numerator ||
        !sampleNumerator(first_t_numerator, t_step_numerator,
                         sample_count, &frame_stop) ||
        expected.stop_t_numerator != frame_stop) {
      atomicOr(&summary->reducer_error_or, kMalformedState);
      continue;
    }
    if (end < begin || end - begin != expected.ambiguity_range_count) {
      atomicOr(&summary->reducer_error_or, kRangeLayoutMismatch);
      continue;
    }
    if (end > range_capacity) {
      atomicOr(&summary->reducer_error_or, kRangeCapacityExceeded);
      continue;
    }
    const std::uint32_t parity = parities[character];
    const std::uint64_t frequency = frequency_ids[character];
    if (frequency >= frequency_stride) error |= kInvalidFrequencyId;
    const std::uint64_t safe_frequency =
        frequency < frequency_stride ? frequency : 0U;
    bool open = false;
    std::uint64_t open_first = 0U;
    std::uint64_t output = begin;
    std::uint32_t source_or = 0U;
    for (std::uint32_t sample = 0U; sample < sample_count; ++sample) {
      std::uint64_t numerator = 0U;
      if (!sampleNumerator(first_t_numerator, t_step_numerator,
                           sample, &numerator)) {
        error |= kCoordinateOverflow;
        break;
      }
      const std::uint64_t flat =
          static_cast<std::uint64_t>(sample) * frequency_stride +
          safe_frequency;
      const std::uint32_t item_status =
          source_statuses == nullptr ? frame_source_status
                                     : source_statuses[flat];
      const std::uint32_t factor_parity = parity <= 1U ? parity : 0U;
      const std::int8_t sign = classifyItem(
          l_values[flat], item_status, roots[character],
          parity_factors[
              static_cast<std::uint64_t>(factor_parity) * sample_count +
              sample],
          parity, &source_or, &error);
      if (sign == 0 && !open) {
        open = true;
        open_first = numerator;
      } else if (sign != 0 && open) {
        if (output >= end) {
          error |= kRangeLayoutMismatch;
          break;
        }
        ranges[output] = {open_first, numerator};
        if (range_primitive_ordinals != nullptr) {
          range_primitive_ordinals[output] = character;
        }
        ++output;
        open = false;
      }
    }
    if (open && error == kReducerSuccess) {
      if (output >= end) {
        error |= kRangeLayoutMismatch;
      } else {
        ranges[output] = {open_first, expected.stop_t_numerator};
        if (range_primitive_ordinals != nullptr) {
          range_primitive_ordinals[output] = character;
        }
        ++output;
      }
    }
    if (output != end) error |= kRangeLayoutMismatch;
    if (source_or != 0U) atomicOr(&summary->source_status_or, source_or);
    if (error != 0U) atomicOr(&summary->reducer_error_or, error);
  }
}

// Qualification-only raw-code projection.  This deliberately is not part of
// the production call graph: it exists so a bounded Arb/FLINT oracle can
// measure false-determinate and extra-ambiguity rates item by item.
static __global__ void classifyCompletedSignsForQualification(
    const dl::ComplexInterval* l_values,
    const std::uint32_t* source_statuses,
    std::uint32_t frame_source_status,
    const sc::Disk* roots,
    const sc::Disk* parity_factors,
    const std::uint8_t* parities,
    const std::uint64_t* frequency_ids,
    std::uint64_t frequency_stride,
    std::uint32_t character_count,
    std::uint32_t sample_count,
    std::int8_t* codes,
    DeviceSummary* summary) {
  const std::uint64_t total =
      static_cast<std::uint64_t>(character_count) * sample_count;
  for (std::uint64_t item =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       item < total;
       item += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t character =
        static_cast<std::uint32_t>(item / sample_count);
    const std::uint32_t sample =
        static_cast<std::uint32_t>(item % sample_count);
    std::uint32_t error = kReducerSuccess;
    const std::uint64_t frequency = frequency_ids[character];
    if (frequency >= frequency_stride) error |= kInvalidFrequencyId;
    const std::uint64_t safe_frequency =
        frequency < frequency_stride ? frequency : 0U;
    const std::uint64_t flat =
        static_cast<std::uint64_t>(sample) * frequency_stride +
        safe_frequency;
    const std::uint32_t parity = parities[character];
    const std::uint32_t factor_parity = parity <= 1U ? parity : 0U;
    const std::uint32_t item_status =
        source_statuses == nullptr ? frame_source_status
                                   : source_statuses[flat];
    std::uint32_t source_or = 0U;
    codes[item] = classifyItem(
        l_values[flat], item_status, roots[character],
        parity_factors[
            static_cast<std::uint64_t>(factor_parity) * sample_count +
            sample],
        parity, &source_or, &error);
    if (source_or != 0U) atomicOr(&summary->source_status_or, source_or);
    if (error != 0U) atomicOr(&summary->reducer_error_or, error);
  }
}

__host__ __device__ __forceinline__ bool validPhaseState(
    const PhaseState& state) {
  std::uint64_t expected_stop = 0U;
  if (state.sample_count == 0U ||
      state.t_step_numerator != kSourceStepNumerator ||
      !sampleNumerator(state.first_t_numerator, state.t_step_numerator,
                       state.sample_count, &expected_stop) ||
      expected_stop != state.stop_t_numerator ||
      state.ambiguity_count > state.sample_count ||
      state.leading_ambiguity_count > state.ambiguity_count ||
      state.trailing_ambiguity_count > state.ambiguity_count ||
      state.ambiguity_range_count > state.ambiguity_count ||
      ((state.ambiguity_count == 0U) !=
       (state.ambiguity_range_count == 0U)) ||
      state.status_or != 0U) {
    return false;
  }
  const std::uint64_t determinate =
      state.sample_count - state.ambiguity_count;
  if (state.has_determinate == 0U) {
    return determinate == 0U && state.first_sign == 0 &&
           state.last_sign == 0 && state.transition_count == 0U &&
           state.leading_ambiguity_count == state.sample_count &&
           state.trailing_ambiguity_count == state.sample_count &&
           state.ambiguity_range_count == 1U;
  }
  std::uint64_t expected_first = 0U;
  std::uint64_t trailing_plus_endpoint = 0U;
  std::uint64_t trailing_width = 0U;
  if (!sampleNumerator(
          state.first_t_numerator, state.t_step_numerator,
          state.leading_ambiguity_count, &expected_first) ||
      !checkedAdd(state.trailing_ambiguity_count, 1U,
                  &trailing_plus_endpoint) ||
      !checkedMul(state.t_step_numerator, trailing_plus_endpoint,
                  &trailing_width) ||
      trailing_width > state.stop_t_numerator) {
    return false;
  }
  const std::uint64_t expected_last =
      state.stop_t_numerator - trailing_width;
  return state.has_determinate == 1U && determinate != 0U &&
         (state.first_sign == -1 || state.first_sign == 1) &&
         (state.last_sign == -1 || state.last_sign == 1) &&
         state.first_determinate_numerator == expected_first &&
         state.last_determinate_numerator == expected_last &&
         state.first_determinate_numerator <=
             state.last_determinate_numerator &&
         state.transition_count <= determinate - 1U &&
         (state.transition_count & 1U) ==
             static_cast<std::uint64_t>(
             state.first_sign != state.last_sign);
}

__host__ __device__ __forceinline__ bool denseRecordValue(
    const PhaseState& state, std::uint64_t expected_sample_count,
    std::uint64_t expected_first_t_numerator,
    std::uint64_t expected_stop_t_numerator,
    std::uint64_t expected_t_step_numerator, std::uint64_t* value) {
  if (!validPhaseState(state) ||
      state.sample_count != expected_sample_count ||
      state.first_t_numerator != expected_first_t_numerator ||
      state.stop_t_numerator != expected_stop_t_numerator ||
      state.t_step_numerator != expected_t_step_numerator ||
      expected_sample_count == 0U ||
      expected_sample_count > kMaximumPackedSamples) {
    return false;
  }
  const std::uint32_t count_width =
      denseCountWidth(expected_sample_count);
  if (state.transition_count >= (std::uint64_t{1} << count_width)) {
    return false;
  }
  std::uint64_t flags = state.has_determinate != 0U ? 1U : 0U;
  if (state.has_determinate != 0U && state.first_sign > 0) flags |= 2U;
  if (state.has_determinate != 0U && state.last_sign > 0) flags |= 4U;
  if (state.ambiguity_range_count != 0U) flags |= 8U;
  *value = flags | (state.transition_count << 4U);
  return true;
}

__host__ __device__ __forceinline__ bool decodeDenseRecord(
    const unsigned char* page, std::uint64_t local_ordinal,
    std::uint64_t sample_count, DenseDecodedRecord* decoded) {
  if (page == nullptr || decoded == nullptr || sample_count == 0U ||
      sample_count > kMaximumPackedSamples ||
      local_ordinal >= kDensePageCharacters) {
    return false;
  }
  const std::uint32_t record_width = denseRecordWidth(sample_count);
  const std::uint64_t bit_start = local_ordinal * record_width;
  std::uint64_t value = 0U;
  for (std::uint32_t bit = 0U; bit < record_width; ++bit) {
    const std::uint64_t absolute = bit_start + bit;
    value |=
        static_cast<std::uint64_t>(
            (page[absolute / 8U] >> (absolute % 8U)) & 1U)
        << bit;
  }
  DenseDecodedRecord result{};
  result.has_determinate = static_cast<std::uint8_t>(value & 1U);
  result.first_sign =
      result.has_determinate == 0U ? 0 : (value & 2U) != 0U ? 1 : -1;
  result.last_sign =
      result.has_determinate == 0U ? 0 : (value & 4U) != 0U ? 1 : -1;
  result.has_sparse = static_cast<std::uint8_t>((value >> 3U) & 1U);
  result.transition_count = value >> 4U;
  if ((result.has_determinate == 0U &&
       ((value & 6U) != 0U || result.transition_count != 0U)) ||
      result.transition_count > sample_count - 1U) {
    return false;
  }
  *decoded = result;
  return true;
}

static __global__ void buildDensePageTotals(
    const PhaseState* states, std::uint64_t character_count,
    std::uint64_t sample_count, std::uint64_t first_t_numerator,
    std::uint64_t stop_t_numerator, std::uint64_t t_step_numerator,
    DensePageTotals* page_totals, DeviceSummary* summary) {
  const std::uint64_t page_count = densePageCount(character_count);
  const std::uint64_t page = blockIdx.x;
  if (page >= page_count) return;
  __shared__ unsigned long long transition_count;
  __shared__ unsigned long long ambiguity_sample_count;
  __shared__ unsigned long long ambiguity_range_count;
  __shared__ unsigned int sparse_character_count;
  __shared__ unsigned int page_error;
  if (threadIdx.x == 0U) {
    transition_count = 0U;
    ambiguity_sample_count = 0U;
    ambiguity_range_count = 0U;
    sparse_character_count = 0U;
    page_error = kReducerSuccess;
  }
  __syncthreads();
  const std::uint64_t ordinal_start =
      page * kDensePageCharacters;
  const std::uint64_t remaining =
      character_count - ordinal_start;
  const std::uint64_t page_characters =
      remaining < kDensePageCharacters
          ? remaining
          : static_cast<std::uint64_t>(kDensePageCharacters);
  std::uint64_t local_transitions = 0U;
  std::uint64_t local_ambiguities = 0U;
  std::uint64_t local_ranges = 0U;
  std::uint32_t local_sparse = 0U;
  std::uint32_t local_error = kReducerSuccess;
  for (std::uint64_t local = threadIdx.x; local < page_characters;
       local += blockDim.x) {
    const PhaseState state = states[ordinal_start + local];
    std::uint64_t packed = 0U;
    if (!denseRecordValue(
            state, sample_count, first_t_numerator, stop_t_numerator,
            t_step_numerator, &packed)) {
      local_error |= kDensePackLayoutMismatch;
      continue;
    }
    if (!checkedAdd(local_transitions, state.transition_count,
                    &local_transitions) ||
        !checkedAdd(local_ambiguities, state.ambiguity_count,
                    &local_ambiguities) ||
        !checkedAdd(local_ranges, state.ambiguity_range_count,
                    &local_ranges)) {
      local_error |= kDensePackCounterOverflow;
    }
    local_sparse += static_cast<std::uint32_t>(
        state.ambiguity_range_count != 0U);
  }
  atomicAdd(&transition_count,
            static_cast<unsigned long long>(local_transitions));
  atomicAdd(&ambiguity_sample_count,
            static_cast<unsigned long long>(local_ambiguities));
  atomicAdd(&ambiguity_range_count,
            static_cast<unsigned long long>(local_ranges));
  atomicAdd(&sparse_character_count, local_sparse);
  if (local_error != 0U) atomicOr(&page_error, local_error);
  __syncthreads();
  if (threadIdx.x == 0U) {
    DensePageTotals totals{};
    totals.ordinal_start = ordinal_start;
    totals.character_count = page_characters;
    totals.count_width = denseCountWidth(sample_count);
    totals.record_width = 4U + totals.count_width;
    totals.dense_bytes =
        densePackedBytes(totals.character_count, totals.record_width);
    totals.transition_count = transition_count;
    totals.ambiguity_sample_count = ambiguity_sample_count;
    totals.ambiguity_range_count = ambiguity_range_count;
    totals.sparse_character_count = sparse_character_count;
    totals.status_or = page_error;
    page_totals[page] = totals;
    if (page_error != 0U) {
      atomicOr(&summary->reducer_error_or, page_error);
    }
  }
}

// Fixed-stride device staging. Every thread owns one complete 32-bit output
// word and visits only the records overlapping that word, so records crossing
// byte/word boundaries need no atomics and each PhaseState is loaded only a
// few times. Unused words and high padding bits are written as zero;
// page_totals.dense_bytes selects the canonical prefix for TGDCSB03.
static __global__ void packDensePages(
    const PhaseState* states, std::uint64_t character_count,
    std::uint64_t sample_count, std::uint64_t page_stride_bytes,
    unsigned char* packed_pages) {
  const std::uint64_t page = blockIdx.x;
  const std::uint64_t ordinal_start = page * kDensePageCharacters;
  if (ordinal_start >= character_count) return;
  const std::uint64_t remaining = character_count - ordinal_start;
  const std::uint64_t page_characters =
      remaining < kDensePageCharacters
          ? remaining
          : static_cast<std::uint64_t>(kDensePageCharacters);
  const std::uint32_t record_width = denseRecordWidth(sample_count);
  const std::uint64_t words = page_stride_bytes / 4U;
  for (std::uint64_t word = threadIdx.x; word < words;
       word += blockDim.x) {
    const std::uint64_t word_bit_start = word * 32U;
    const std::uint64_t word_bit_stop = word_bit_start + 32U;
    const std::uint64_t first_local =
        word_bit_start / record_width;
    std::uint64_t last_local =
        (word_bit_stop - 1U) / record_width;
    if (last_local >= page_characters && page_characters != 0U) {
      last_local = page_characters - 1U;
    }
    std::uint32_t output = 0U;
    for (std::uint64_t local = first_local;
         local <= last_local && local < page_characters; ++local) {
      // buildDensePageTotals validated this exact state and geometry in the
      // preceding kernel on the same stream.
      const PhaseState state = states[ordinal_start + local];
      std::uint64_t flags = state.has_determinate != 0U ? 1U : 0U;
      if (state.has_determinate != 0U && state.first_sign > 0) flags |= 2U;
      if (state.has_determinate != 0U && state.last_sign > 0) flags |= 4U;
      if (state.ambiguity_range_count != 0U) flags |= 8U;
      const std::uint64_t value =
          flags | (state.transition_count << 4U);
      const std::uint64_t record_bit_start = local * record_width;
      const std::uint64_t record_bit_stop =
          record_bit_start + record_width;
      const std::uint64_t overlap_start =
          record_bit_start > word_bit_start
              ? record_bit_start
              : word_bit_start;
      const std::uint64_t overlap_stop =
          record_bit_stop < word_bit_stop
              ? record_bit_stop
              : word_bit_stop;
      const std::uint32_t overlap_width =
          static_cast<std::uint32_t>(overlap_stop - overlap_start);
      const std::uint32_t record_shift =
          static_cast<std::uint32_t>(
              overlap_start - record_bit_start);
      const std::uint32_t word_shift =
          static_cast<std::uint32_t>(
              overlap_start - word_bit_start);
      const std::uint64_t mask =
          overlap_width == 32U
              ? 0xffffffffULL
              : (std::uint64_t{1} << overlap_width) - 1U;
      output |= static_cast<std::uint32_t>(
                    (value >> record_shift) & mask)
                << word_shift;
    }
    unsigned char* bytes =
        packed_pages + page * page_stride_bytes + word * 4U;
    bytes[0] = static_cast<unsigned char>(output);
    bytes[1] = static_cast<unsigned char>(output >> 8U);
    bytes[2] = static_cast<unsigned char>(output >> 16U);
    bytes[3] = static_cast<unsigned char>(output >> 24U);
  }
}

// Associative ordered merge of dense phase state.  Sparse ambiguity ranges
// use the same ordered concatenation, coalescing the single boundary pair
// exactly when both sides have boundary ambiguity.
__host__ __device__ __forceinline__ bool combineAdjacentStates(
    const PhaseState& left, const PhaseState& right, PhaseState* output,
    std::uint32_t* error) {
  if (!validPhaseState(left) || !validPhaseState(right)) {
    *error |= kMalformedState;
    return false;
  }
  if (left.stop_t_numerator != right.first_t_numerator ||
      left.t_step_numerator != right.t_step_numerator) {
    *error |= kNonAdjacentState;
    return false;
  }
  PhaseState result{};
  result.first_t_numerator = left.first_t_numerator;
  result.stop_t_numerator = right.stop_t_numerator;
  result.t_step_numerator = left.t_step_numerator;
  if (!checkedAdd(left.sample_count, right.sample_count,
                  &result.sample_count) ||
      !checkedAdd(left.ambiguity_count, right.ambiguity_count,
                  &result.ambiguity_count) ||
      !checkedAdd(left.transition_count, right.transition_count,
                  &result.transition_count) ||
      !checkedAdd(left.ambiguity_range_count,
                  right.ambiguity_range_count,
                  &result.ambiguity_range_count)) {
    *error |= kStateCounterOverflow;
    return false;
  }
  if (left.has_determinate != 0U && right.has_determinate != 0U &&
      left.last_sign != right.first_sign) {
    if (!checkedAdd(result.transition_count, 1U,
                    &result.transition_count)) {
      *error |= kStateCounterOverflow;
      return false;
    }
  }
  if (left.trailing_ambiguity_count != 0U &&
      right.leading_ambiguity_count != 0U) {
    --result.ambiguity_range_count;
  }
  if (left.has_determinate != 0U) {
    result.has_determinate = 1U;
    result.first_determinate_numerator =
        left.first_determinate_numerator;
    result.first_sign = left.first_sign;
    result.leading_ambiguity_count =
        left.leading_ambiguity_count;
  } else {
    result.has_determinate = right.has_determinate;
    result.first_determinate_numerator =
        right.first_determinate_numerator;
    result.first_sign = right.first_sign;
    std::uint64_t leading = 0U;
    if (!checkedAdd(left.sample_count, right.leading_ambiguity_count,
                    &leading) ||
        leading > ~std::uint32_t{0}) {
      *error |= kStateCounterOverflow;
      return false;
    }
    result.leading_ambiguity_count =
        static_cast<std::uint32_t>(leading);
  }
  if (right.has_determinate != 0U) {
    result.has_determinate = 1U;
    result.last_determinate_numerator =
        right.last_determinate_numerator;
    result.last_sign = right.last_sign;
    result.trailing_ambiguity_count =
        right.trailing_ambiguity_count;
  } else {
    result.last_determinate_numerator =
        left.last_determinate_numerator;
    result.last_sign = left.last_sign;
    std::uint64_t trailing = 0U;
    if (!checkedAdd(right.sample_count, left.trailing_ambiguity_count,
                    &trailing) ||
        trailing > ~std::uint32_t{0}) {
      *error |= kStateCounterOverflow;
      return false;
    }
    result.trailing_ambiguity_count =
        static_cast<std::uint32_t>(trailing);
  }
  result.status_or = left.status_or | right.status_or;
  if (!validPhaseState(result)) {
    *error |= kMalformedState;
    return false;
  }
  *output = result;
  return true;
}

static __global__ void combineAdjacentStateArrays(
    const PhaseState* left, const PhaseState* right,
    std::uint32_t character_count, PhaseState* output,
    DeviceSummary* summary) {
  for (std::uint32_t character = blockIdx.x * blockDim.x + threadIdx.x;
       character < character_count;
       character += blockDim.x * gridDim.x) {
    std::uint32_t error = kReducerSuccess;
    PhaseState combined{};
    if (combineAdjacentStates(
            left[character], right[character], &combined, &error)) {
      output[character] = combined;
    } else {
      // Keep rejected output deterministic even if a later queued stage is
      // launched before the host observes the fail-closed summary.
      output[character] = PhaseState{};
      atomicOr(&summary->reducer_error_or, error);
    }
  }
}

// Non-owning same-process view of one resident allchars frame.  The caller
// must bind q, canonical primitive frequency ids/parities, TGDRNRO1 roots,
// factor-convention digest, exact 5/64 coordinates, and the upstream frame
// commitment in its receipt.  This struct intentionally carries no host
// vector and owns no raw-output path.
struct ResidentFrameView {
  std::uint32_t q;
  std::uint32_t character_count;
  std::uint32_t sample_count;
  std::uint32_t frame_source_status;
  std::uint64_t frequency_stride;
  std::uint64_t value_count;
  std::uint64_t first_t_numerator;
  std::uint64_t t_step_numerator;
  const dl::ComplexInterval* l_values;
  const std::uint32_t* optional_item_statuses;
  const sc::Disk* roots;
  const sc::Disk* parity_factors;
  const std::uint8_t* parities;
  const std::uint64_t* frequency_ids;
};

struct ReductionWorkspace {
  PhaseState* states;
  std::uint64_t* range_counts;
  DeviceSummary* summary;
};

struct FactorRecurrenceView {
  const sc::Disk* gamma_scaled;
  const sc::Disk* conductor_checkpoints;
  sc::Disk conductor_step;
  std::uint32_t sample_count;
  std::uint32_t checkpoint_span;
  std::uint32_t checkpoint_count;
};

struct DensePackView {
  const PhaseState* states;
  std::uint64_t character_count;
  std::uint64_t sample_count;
  std::uint64_t first_t_numerator;
  std::uint64_t stop_t_numerator;
  std::uint64_t t_step_numerator;
  unsigned char* packed_pages;
  std::uint64_t packed_capacity_bytes;
  DensePageTotals* page_totals;
  std::uint64_t page_totals_count;
  DeviceSummary* summary;
};

inline bool validResidentFrameView(const ResidentFrameView& frame) {
  std::uint64_t expected_values = 0U;
  std::uint64_t expected_stop = 0U;
  return frame.q != 0U && frame.q <= kMaximumModulus &&
         frame.character_count != 0U && frame.sample_count != 0U &&
         frame.sample_count <= kMaximumFrameSamples &&
         frame.frequency_stride != 0U &&
         frame.t_step_numerator == kSourceStepNumerator &&
         checkedMul(frame.sample_count, frame.frequency_stride,
                    &expected_values) &&
         expected_values == frame.value_count &&
         sampleNumerator(frame.first_t_numerator,
                         frame.t_step_numerator, frame.sample_count,
                         &expected_stop) &&
         frame.l_values != nullptr && frame.roots != nullptr &&
         frame.parity_factors != nullptr && frame.parities != nullptr &&
         frame.frequency_ids != nullptr;
}

// Convert a bounded root/factor catalog into the directed disk convention
// without clearing an owning pipeline summary. Invalid rows are
// deterministically written as zero disks and set the requested stage bit.
inline cudaError_t launchRectangleCatalogToDisksIntoSummary(
    const dl::ComplexInterval* rectangles, std::uint64_t count,
    sc::Disk* disks, std::uint32_t error_bit, DeviceSummary* summary,
    cudaStream_t stream = nullptr) {
  if (rectangles == nullptr || disks == nullptr || summary == nullptr ||
      count == 0U ||
      count > 2ULL * kMaximumModulus ||
      (error_bit != kInvalidRootDisk &&
       error_bit != kInvalidFactorDisk)) {
    return cudaErrorInvalidValue;
  }
  const std::uint32_t requested_blocks =
      static_cast<std::uint32_t>((count + 255U) / 256U);
  const std::uint32_t blocks =
      requested_blocks < 4096U ? requested_blocks : 4096U;
  convertRectanglesToDisks<<<blocks, 256, 0, stream>>>(
      rectangles, count, disks, error_bit, summary);
  return cudaGetLastError();
}

// Production callers use this validated wrapper, never the raw kernel.  In
// particular, an undersized checkpoint roster cannot leave any factor row
// unwritten, and an oversized roster cannot read a nonexistent checkpoint.
inline cudaError_t launchParityFactorsFromCheckpoints(
    const FactorRecurrenceView& factors, sc::Disk* parity_factors,
    DeviceSummary* summary, cudaStream_t stream = nullptr) {
  if (factors.gamma_scaled == nullptr ||
      factors.conductor_checkpoints == nullptr ||
      parity_factors == nullptr || summary == nullptr ||
      factors.sample_count == 0U ||
      factors.sample_count > kSourceSampleCount ||
      factors.checkpoint_span == 0U) {
    return cudaErrorInvalidValue;
  }
  const std::uint32_t expected_checkpoints =
      1U + (factors.sample_count - 1U) / factors.checkpoint_span;
  if (factors.checkpoint_count != expected_checkpoints) {
    return cudaErrorInvalidValue;
  }
  cudaError_t status =
      cudaMemsetAsync(summary, 0, sizeof(DeviceSummary), stream);
  if (status != cudaSuccess) return status;
  std::uint64_t factor_bytes = 0U;
  if (!checkedMul(
          static_cast<std::uint64_t>(factors.sample_count) * 2U,
          sizeof(sc::Disk), &factor_bytes) ||
      factor_bytes > std::numeric_limits<std::size_t>::max()) {
    return cudaErrorInvalidValue;
  }
  status = cudaMemsetAsync(
      parity_factors, 0, static_cast<std::size_t>(factor_bytes), stream);
  if (status != cudaSuccess) return status;
  const std::uint32_t requested_blocks = factors.checkpoint_count;
  const std::uint32_t blocks =
      requested_blocks < 4096U ? requested_blocks : 4096U;
  buildParityFactorsFromCheckpoints<<<blocks, 256, 0, stream>>>(
      factors.gamma_scaled, factors.conductor_checkpoints,
      factors.conductor_step, factors.sample_count,
      factors.checkpoint_span, factors.checkpoint_count, parity_factors,
      summary);
  return cudaGetLastError();
}

// Launch only the dense/count pass.  A CUB exclusive scan of range_counts
// followed by writeAmbiguityRanges is the sparse second pass.  Keeping the
// scan outside this header lets allchars reuse its persistent workspace.
inline cudaError_t launchResidentPhaseReduction(
    const ResidentFrameView& frame, const ReductionWorkspace& workspace,
    cudaStream_t stream = nullptr) {
  if (!validResidentFrameView(frame) || workspace.states == nullptr ||
      workspace.range_counts == nullptr || workspace.summary == nullptr) {
    return cudaErrorInvalidValue;
  }
  cudaError_t status =
      cudaMemsetAsync(workspace.summary, 0, sizeof(DeviceSummary), stream);
  if (status != cudaSuccess) return status;
  const std::uint32_t blocks =
      min(4096U, (frame.character_count + 255U) / 256U);
  reduceCompletedSigns<<<blocks, 256, 0, stream>>>(
      frame.l_values, frame.optional_item_statuses,
      frame.frame_source_status, frame.roots, frame.parity_factors,
      frame.parities, frame.frequency_ids, frame.frequency_stride,
      frame.character_count, frame.sample_count,
      frame.first_t_numerator, frame.t_step_numerator, workspace.states,
      workspace.range_counts, workspace.summary);
  return cudaGetLastError();
}

inline cudaError_t launchResidentAmbiguityRangeWrite(
    const ResidentFrameView& frame, const PhaseState* states,
    const std::uint64_t* range_offsets, std::uint64_t range_capacity,
    AmbiguityRange* ranges, DeviceSummary* summary,
    cudaStream_t stream = nullptr) {
  if (!validResidentFrameView(frame) || states == nullptr ||
      range_offsets == nullptr || summary == nullptr ||
      (range_capacity != 0U && ranges == nullptr)) {
    return cudaErrorInvalidValue;
  }
  if (range_capacity != 0U) {
    std::uint64_t range_bytes = 0U;
    if (!checkedMul(range_capacity, sizeof(AmbiguityRange),
                    &range_bytes) ||
        range_bytes > std::numeric_limits<std::size_t>::max()) {
      return cudaErrorInvalidValue;
    }
    cudaError_t status = cudaMemsetAsync(
        ranges, 0, static_cast<std::size_t>(range_bytes), stream);
    if (status != cudaSuccess) return status;
  }
  const std::uint32_t blocks =
      min(4096U, (frame.character_count + 255U) / 256U);
  writeAmbiguityRanges<<<blocks, 256, 0, stream>>>(
      frame.l_values, frame.optional_item_statuses,
      frame.frame_source_status, frame.roots, frame.parity_factors,
      frame.parities, frame.frequency_ids, frame.frequency_stride,
      frame.character_count, frame.sample_count,
      frame.first_t_numerator, frame.t_step_numerator, states,
      range_offsets, range_capacity, ranges, nullptr, summary);
  return cudaGetLastError();
}

inline cudaError_t launchResidentTaggedAmbiguityRangeWrite(
    const ResidentFrameView& frame, const PhaseState* states,
    const std::uint64_t* range_offsets, std::uint64_t range_capacity,
    AmbiguityRange* ranges, std::uint64_t* range_primitive_ordinals,
    DeviceSummary* summary, cudaStream_t stream = nullptr) {
  if (!validResidentFrameView(frame) || states == nullptr ||
      range_offsets == nullptr || summary == nullptr ||
      (range_capacity != 0U &&
       (ranges == nullptr || range_primitive_ordinals == nullptr))) {
    return cudaErrorInvalidValue;
  }
  if (range_capacity != 0U) {
    std::uint64_t range_bytes = 0U;
    std::uint64_t ordinal_bytes = 0U;
    if (!checkedMul(range_capacity, sizeof(AmbiguityRange),
                    &range_bytes) ||
        !checkedMul(range_capacity, sizeof(std::uint64_t),
                    &ordinal_bytes) ||
        range_bytes > std::numeric_limits<std::size_t>::max() ||
        ordinal_bytes > std::numeric_limits<std::size_t>::max()) {
      return cudaErrorInvalidValue;
    }
    cudaError_t status = cudaMemsetAsync(
        ranges, 0, static_cast<std::size_t>(range_bytes), stream);
    if (status != cudaSuccess) return status;
    status = cudaMemsetAsync(
        range_primitive_ordinals, 0xff,
        static_cast<std::size_t>(ordinal_bytes), stream);
    if (status != cudaSuccess) return status;
  }
  const std::uint32_t blocks =
      min(4096U, (frame.character_count + 255U) / 256U);
  writeAmbiguityRanges<<<blocks, 256, 0, stream>>>(
      frame.l_values, frame.optional_item_statuses,
      frame.frame_source_status, frame.roots, frame.parity_factors,
      frame.parities, frame.frequency_ids, frame.frequency_stride,
      frame.character_count, frame.sample_count,
      frame.first_t_numerator, frame.t_step_numerator, states,
      range_offsets, range_capacity, ranges, range_primitive_ordinals,
      summary);
  return cudaGetLastError();
}

// Append into storage initialized once by the owning q-level pipeline.
// range_offsets are absolute offsets into [0, range_capacity); unlike the
// standalone wrapper above, this function intentionally performs no memset
// and therefore cannot erase sparse rows written by earlier frames.
inline cudaError_t
launchResidentTaggedAmbiguityRangeWriteIntoInitializedStorage(
    const ResidentFrameView& frame, const PhaseState* states,
    const std::uint64_t* absolute_range_offsets,
    std::uint64_t range_capacity, AmbiguityRange* ranges,
    std::uint64_t* range_primitive_ordinals, DeviceSummary* summary,
    cudaStream_t stream = nullptr) {
  if (!validResidentFrameView(frame) || states == nullptr ||
      absolute_range_offsets == nullptr || summary == nullptr ||
      (range_capacity != 0U &&
       (ranges == nullptr || range_primitive_ordinals == nullptr))) {
    return cudaErrorInvalidValue;
  }
  std::uint64_t range_bytes = 0U;
  std::uint64_t ordinal_bytes = 0U;
  if (!checkedMul(range_capacity, sizeof(AmbiguityRange),
                  &range_bytes) ||
      !checkedMul(range_capacity, sizeof(std::uint64_t),
                  &ordinal_bytes) ||
      range_bytes > std::numeric_limits<std::size_t>::max() ||
      ordinal_bytes > std::numeric_limits<std::size_t>::max()) {
    return cudaErrorInvalidValue;
  }
  const std::uint32_t blocks =
      min(4096U, (frame.character_count + 255U) / 256U);
  writeAmbiguityRanges<<<blocks, 256, 0, stream>>>(
      frame.l_values, frame.optional_item_statuses,
      frame.frame_source_status, frame.roots, frame.parity_factors,
      frame.parities, frame.frequency_ids, frame.frequency_stride,
      frame.character_count, frame.sample_count,
      frame.first_t_numerator, frame.t_step_numerator, states,
      absolute_range_offsets, range_capacity, ranges,
      range_primitive_ordinals, summary);
  return cudaGetLastError();
}

// Validate and emit the exact dense prefix used by TGDCSB03. The output is
// fixed-stride only while resident on the GPU: page_totals[page].dense_bytes
// gives the canonical variable-length prefix for transport. Callers must
// check this stage summary and the separately retained upstream reducer
// summary before accepting or signing any output.
inline cudaError_t launchDenseTGDCSB03Pack(
    const DensePackView& view, cudaStream_t stream = nullptr) {
  std::uint64_t expected_stop = 0U;
  if (view.states == nullptr || view.packed_pages == nullptr ||
      view.page_totals == nullptr || view.summary == nullptr ||
      view.character_count == 0U ||
      view.character_count > kMaximumModulus ||
      view.sample_count == 0U ||
      view.sample_count > kMaximumPackedSamples ||
      view.t_step_numerator != kSourceStepNumerator ||
      !sampleNumerator(
          view.first_t_numerator, view.t_step_numerator,
          view.sample_count, &expected_stop) ||
      expected_stop != view.stop_t_numerator) {
    return cudaErrorInvalidValue;
  }
  const std::uint64_t pages = densePageCount(view.character_count);
  const std::uint64_t stride = densePageStrideBytes(view.sample_count);
  std::uint64_t required_bytes = 0U;
  if (pages == 0U || stride == ~std::uint64_t{0} ||
      !checkedMul(pages, stride, &required_bytes) ||
      required_bytes > std::numeric_limits<std::size_t>::max() ||
      view.page_totals_count != pages ||
      view.packed_capacity_bytes != required_bytes) {
    return cudaErrorInvalidValue;
  }
  cudaError_t status =
      cudaMemsetAsync(view.summary, 0, sizeof(DeviceSummary), stream);
  if (status != cudaSuccess) return status;
  status = cudaMemsetAsync(
      view.page_totals, 0,
      static_cast<std::size_t>(pages * sizeof(DensePageTotals)), stream);
  if (status != cudaSuccess) return status;
  const std::uint32_t total_blocks =
      static_cast<std::uint32_t>(pages < 4096U ? pages : 4096U);
  buildDensePageTotals<<<total_blocks, 256, 0, stream>>>(
      view.states, view.character_count, view.sample_count,
      view.first_t_numerator, view.stop_t_numerator,
      view.t_step_numerator, view.page_totals, view.summary);
  status = cudaGetLastError();
  if (status != cudaSuccess) return status;
  packDensePages<<<static_cast<std::uint32_t>(pages), 256, 0, stream>>>(
      view.states, view.character_count, view.sample_count, stride,
      view.packed_pages);
  return cudaGetLastError();
}

}  // namespace sparkinterval::tg::dirichlet_completed_sign_reducer

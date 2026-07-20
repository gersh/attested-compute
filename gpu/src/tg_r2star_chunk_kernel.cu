// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_r2star_chunk.h"

#include <cstddef>
#include <cstdint>
#include <limits>

#include <cuda_runtime.h>

namespace {

constexpr unsigned int kThreadsPerBlock = 256;
constexpr std::size_t kMaximumGridX = 0x7fffffffULL;
constexpr std::uint64_t kLow32Mask = 0xffffffffULL;
constexpr std::uint64_t kU64Max = 0xffffffffffffffffULL;
constexpr std::int64_t kI64Max = 9'223'372'036'854'775'807LL;
constexpr std::int64_t kI64Min = -kI64Max - 1;
constexpr std::uint64_t kMaximumEnvelopeMagnitude =
    184'467'440'737'095'516ULL;  // floor((2^64-1)/100)

struct PositiveLogIntervals {
  std::uint64_t lower_low;
  std::uint64_t lower_high;
  std::uint64_t upper_low;
  std::uint64_t upper_high;
};

__device__ __forceinline__ bool add_u64(std::uint64_t left,
                                        std::uint64_t right,
                                        std::uint64_t* result) {
  *result = left + right;
  return *result >= left;
}

__device__ __forceinline__ bool add_i64(std::int64_t left,
                                        std::int64_t right,
                                        std::int64_t* result) {
  if ((right > 0 && left > kI64Max - right) ||
      (right < 0 && left < kI64Min - right)) {
    return false;
  }
  *result = left + right;
  return true;
}

__device__ __forceinline__ std::uint64_t ceil_div_u64(
    std::uint64_t numerator, std::uint64_t denominator) {
  return numerator / denominator + (numerator % denominator != 0);
}

// Exact floor/ceil of numerator * 2^64 / denominator for numerator <
// denominator < 2^48.  Four base-2^16 digits keep every partial dividend
// below 2^64, avoiding an implicit floating or 128-bit division.
__device__ __forceinline__ bool directed_q64_ratio(
    std::uint64_t numerator, std::uint64_t denominator,
    std::uint64_t* lower, std::uint64_t* upper) {
  if (denominator == 0 || numerator >= denominator ||
      denominator >= (1ULL << 48)) {
    return false;
  }
  std::uint64_t quotient = 0;
  std::uint64_t remainder = numerator;
#pragma unroll
  for (unsigned int digit = 0; digit < 4; ++digit) {
    const std::uint64_t partial = remainder << 16;
    quotient = (quotient << 16) | (partial / denominator);
    remainder = partial % denominator;
  }
  *lower = quotient;
  *upper = quotient + (remainder != 0);
  return *upper >= *lower;
}

__device__ __forceinline__ std::uint64_t q64_mul_floor(
    std::uint64_t left, std::uint64_t right) {
  return __umul64hi(left, right);
}

__device__ __forceinline__ bool q64_mul_ceil(
    std::uint64_t left, std::uint64_t right, std::uint64_t* result) {
  const std::uint64_t low = left * right;
  const std::uint64_t high = __umul64hi(left, right);
  *result = high + (low != 0);
  return *result >= high;
}

__device__ __forceinline__ int compare_u128(TgUnsigned128 left,
                                             TgUnsigned128 right) {
  if (left.high != right.high) return left.high < right.high ? -1 : 1;
  if (left.low != right.low) return left.low < right.low ? -1 : 1;
  return 0;
}

__device__ __forceinline__ TgUnsigned128 multiply_u64(std::uint64_t left,
                                                       std::uint64_t right) {
  return TgUnsigned128{left * right, __umul64hi(left, right)};
}

// Return ceil(numerator_units * 2^64 / denominator_units) when the
// denominator is at least 8/9 of 2^64.  The exact result lies between n and
// ceil(9n/8); the bounded correction loop compares full 128-bit products.
__device__ __forceinline__ bool divide_by_near_one_q64_ceil(
    std::uint64_t numerator_units, std::uint64_t denominator_units,
    std::uint64_t* result) {
  if (denominator_units == 0) return false;
  std::uint64_t candidate = numerator_units;
  const std::uint64_t maximum =
      numerator_units + ceil_div_u64(numerator_units, 8) + 1;
  const TgUnsigned128 target{0, numerator_units};
  while (candidate <= maximum) {
    if (compare_u128(multiply_u64(candidate, denominator_units), target) >= 0) {
      *result = candidate;
      return true;
    }
    ++candidate;
  }
  return false;
}

__device__ bool positive_log_intervals(std::uint64_t numerator,
                                       std::uint64_t denominator,
                                       PositiveLogIntervals* output) {
  if (denominator == 0 || numerator < denominator ||
      numerator > 2 * denominator) {
    return false;
  }
  const std::uint64_t difference = numerator - denominator;
  if (difference == 0) {
    *output = PositiveLogIntervals{0, 0, 0, 0};
    return true;
  }
  const std::uint64_t sum = numerator + denominator;
  std::uint64_t z_lower = 0;
  std::uint64_t z_upper = 0;
  if (!directed_q64_ratio(difference, sum, &z_lower, &z_upper)) return false;
  const std::uint64_t z_squared_lower = q64_mul_floor(z_lower, z_lower);
  std::uint64_t z_squared_upper = 0;
  if (!q64_mul_ceil(z_upper, z_upper, &z_squared_upper)) return false;

  std::uint64_t power_lower = z_lower;
  std::uint64_t power_upper = z_upper;
  std::uint64_t partial_lower = 0;
  std::uint64_t partial_upper = 0;
#pragma unroll
  for (std::uint32_t index = 0; index < kTgR2StarSeriesTerms; ++index) {
    const std::uint64_t odd = 2 * index + 1;
    if (!add_u64(partial_lower, power_lower / odd, &partial_lower) ||
        !add_u64(partial_upper, ceil_div_u64(power_upper, odd),
                 &partial_upper)) {
      return false;
    }
    power_lower = q64_mul_floor(power_lower, z_squared_lower);
    if (!q64_mul_ceil(power_upper, z_squared_upper, &power_upper)) return false;
  }
  if (partial_lower > kU64Max / 2 || partial_upper > kU64Max / 2 ||
      power_upper > kU64Max / 2) {
    return false;
  }
  const std::uint64_t lower_low = 2 * partial_lower;
  const std::uint64_t lower_high = 2 * partial_upper;

  // The Python contract's remainder is
  // 2*power/((2*T+1)*(1-z^2)).  First round division by the odd integer up,
  // then divide by the rigorous lower Q64 bound for 1-z^2.  This can only
  // enlarge the upper endpoint.
  const std::uint64_t reduced_tail = ceil_div_u64(
      2 * power_upper, 2 * kTgR2StarSeriesTerms + 1);
  const std::uint64_t denominator_lower = 0 - z_squared_upper;
  std::uint64_t tail_upper = 0;
  if (!divide_by_near_one_q64_ceil(reduced_tail, denominator_lower,
                                   &tail_upper)) {
    return false;
  }
  std::uint64_t upper_high = 0;
  if (!add_u64(lower_high, tail_upper, &upper_high)) return false;
  *output = PositiveLogIntervals{
      lower_low, lower_high, lower_low, upper_high};
  return true;
}

__device__ __forceinline__ bool add_scaled_component(
    TgUnsigned128* accumulator, std::uint64_t value,
    std::uint32_t multiplier) {
  const TgUnsigned128 product = multiply_u64(value, multiplier);
  const std::uint64_t old_low = accumulator->low;
  accumulator->low += product.low;
  const std::uint64_t carry = accumulator->low < old_low;
  const std::uint64_t old_high = accumulator->high;
  accumulator->high += product.high;
  if (accumulator->high < old_high) return false;
  const std::uint64_t before_carry = accumulator->high;
  accumulator->high += carry;
  return accumulator->high >= before_carry;
}

__device__ __forceinline__ bool q64_to_q32_floor(TgUnsigned128 value,
                                                  std::uint64_t* result) {
  if (value.high >> 32 != 0) return false;
  *result = (value.high << 32) | (value.low >> 32);
  return true;
}

__device__ __forceinline__ bool q64_to_q32_ceil(TgUnsigned128 value,
                                                 std::uint64_t* result) {
  if (!q64_to_q32_floor(value, result)) return false;
  if ((value.low & kLow32Mask) != 0) {
    if (*result == kU64Max) return false;
    ++*result;
  }
  return true;
}

__device__ bool fixed_log_bounds(std::uint64_t integer,
                                 std::uint64_t* lower,
                                 std::uint64_t* upper,
                                 bool* ambiguous) {
  if (integer < 2) return false;
  const std::uint32_t exponent = 63U - __clzll(integer);
  const std::uint64_t power_of_two = 1ULL << exponent;
  PositiveLogIntervals log_two{};
  PositiveLogIntervals mantissa{};
  if (!positive_log_intervals(2, 1, &log_two) ||
      !positive_log_intervals(integer, power_of_two, &mantissa)) {
    return false;
  }

  TgUnsigned128 lower_low{mantissa.lower_low, 0};
  TgUnsigned128 lower_high{mantissa.lower_high, 0};
  TgUnsigned128 upper_low{mantissa.upper_low, 0};
  TgUnsigned128 upper_high{mantissa.upper_high, 0};
  if (!add_scaled_component(&lower_low, log_two.lower_low, exponent) ||
      !add_scaled_component(&lower_high, log_two.lower_high, exponent) ||
      !add_scaled_component(&upper_low, log_two.upper_low, exponent) ||
      !add_scaled_component(&upper_high, log_two.upper_high, exponent)) {
    return false;
  }
  std::uint64_t lower_candidate = 0;
  std::uint64_t lower_other = 0;
  std::uint64_t upper_candidate = 0;
  std::uint64_t upper_other = 0;
  if (!q64_to_q32_floor(lower_low, &lower_candidate) ||
      !q64_to_q32_floor(lower_high, &lower_other) ||
      !q64_to_q32_ceil(upper_low, &upper_candidate) ||
      !q64_to_q32_ceil(upper_high, &upper_other)) {
    return false;
  }
  *ambiguous = lower_candidate != lower_other ||
               upper_candidate != upper_other;
  if (*ambiguous) return true;
  *lower = lower_candidate;
  *upper = upper_candidate;
  return *lower <= *upper;
}

__device__ bool product_shift32(std::uint64_t left, std::uint64_t right,
                                bool double_product,
                                std::uint64_t* floor,
                                std::uint64_t* ceil) {
  std::uint64_t low = left * right;
  std::uint64_t high = __umul64hi(left, right);
  if (double_product) {
    if ((high >> 63) != 0) return false;
    high = (high << 1) | (low >> 63);
    low <<= 1;
  }
  if ((high >> 32) != 0) return false;
  *floor = (high << 32) | (low >> 32);
  *ceil = *floor + ((low & kLow32Mask) != 0);
  return *ceil >= *floor;
}

__global__ void compute_directed_rows(
    std::uint64_t lower, std::size_t count,
    const TgR2StarFactorSupport* factor_support,
    TgR2StarDirectedRow* rows) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t number = lower + index;
  const TgR2StarFactorSupport support = factor_support[index];
  TgR2StarDirectedRow result{};
  result.status = static_cast<std::uint32_t>(TgR2StarRowStatus::valid);

  if (support.reserved != 0 || support.distinct_prime_factor_count > 3 ||
      (number == 1 && support.distinct_prime_factor_count != 0) ||
      (number > 1 && support.distinct_prime_factor_count == 0) ||
      (support.distinct_prime_factor_count >= 1 &&
       (support.first_prime < 2 || number % support.first_prime != 0)) ||
      (support.distinct_prime_factor_count >= 2 &&
       (support.second_prime <= support.first_prime ||
        number % support.second_prime != 0))) {
    result.status = static_cast<std::uint32_t>(
        TgR2StarRowStatus::invalid_factor_support);
    rows[index] = result;
    return;
  }

  bool ambiguous = false;
  if (number >= 2 &&
      !fixed_log_bounds(number, &result.log_lower, &result.log_upper,
                        &ambiguous)) {
    result.status =
        static_cast<std::uint32_t>(TgR2StarRowStatus::fixed_point_overflow);
    rows[index] = result;
    return;
  }
  if (ambiguous) {
    result.status = static_cast<std::uint32_t>(
        TgR2StarRowStatus::log_resolution_ambiguous);
    rows[index] = result;
    return;
  }

  std::int64_t coefficient_lower = 0;
  std::int64_t coefficient_upper = 0;
  if (support.distinct_prime_factor_count == 1) {
    std::uint64_t factor_lower = 0;
    std::uint64_t factor_upper = 0;
    if (!fixed_log_bounds(support.first_prime, &factor_lower, &factor_upper,
                          &ambiguous) || ambiguous) {
      result.status = static_cast<std::uint32_t>(
          ambiguous ? TgR2StarRowStatus::log_resolution_ambiguous
                    : TgR2StarRowStatus::fixed_point_overflow);
      rows[index] = result;
      return;
    }
    std::uint64_t upper_floor = 0;
    std::uint64_t upper_ceil = 0;
    std::uint64_t lower_floor = 0;
    std::uint64_t lower_ceil = 0;
    if (!product_shift32(factor_upper, factor_upper, false, &upper_floor,
                         &upper_ceil) ||
        !product_shift32(factor_lower, factor_lower, false, &lower_floor,
                         &lower_ceil) ||
        upper_ceil > static_cast<std::uint64_t>(
                         kI64Max) ||
        lower_floor > static_cast<std::uint64_t>(
                          kI64Max)) {
      result.status =
          static_cast<std::uint32_t>(TgR2StarRowStatus::fixed_point_overflow);
      rows[index] = result;
      return;
    }
    coefficient_lower = -static_cast<std::int64_t>(upper_ceil);
    coefficient_upper = -static_cast<std::int64_t>(lower_floor);
  } else if (support.distinct_prime_factor_count == 2) {
    std::uint64_t first_lower = 0;
    std::uint64_t first_upper = 0;
    std::uint64_t second_lower = 0;
    std::uint64_t second_upper = 0;
    if (!fixed_log_bounds(support.first_prime, &first_lower, &first_upper,
                          &ambiguous) || ambiguous ||
        !fixed_log_bounds(support.second_prime, &second_lower, &second_upper,
                          &ambiguous) || ambiguous) {
      result.status = static_cast<std::uint32_t>(
          ambiguous ? TgR2StarRowStatus::log_resolution_ambiguous
                    : TgR2StarRowStatus::fixed_point_overflow);
      rows[index] = result;
      return;
    }
    std::uint64_t lower_floor = 0;
    std::uint64_t lower_ceil = 0;
    std::uint64_t upper_floor = 0;
    std::uint64_t upper_ceil = 0;
    if (!product_shift32(first_lower, second_lower, true, &lower_floor,
                         &lower_ceil) ||
        !product_shift32(first_upper, second_upper, true, &upper_floor,
                         &upper_ceil) ||
        lower_floor > static_cast<std::uint64_t>(
                          kI64Max) ||
        upper_ceil > static_cast<std::uint64_t>(
                         kI64Max)) {
      result.status =
          static_cast<std::uint32_t>(TgR2StarRowStatus::fixed_point_overflow);
      rows[index] = result;
      return;
    }
    coefficient_lower = static_cast<std::int64_t>(lower_floor);
    coefficient_upper = static_cast<std::int64_t>(upper_ceil);
  }

  constexpr std::int64_t twice_gamma_lower =
      static_cast<std::int64_t>(2 * kTgR2StarGammaLower);
  constexpr std::int64_t twice_gamma_upper =
      static_cast<std::int64_t>(2 * kTgR2StarGammaUpper);
  if (!add_i64(coefficient_lower, twice_gamma_lower, &result.delta_lower) ||
      !add_i64(coefficient_upper, twice_gamma_upper, &result.delta_upper) ||
      result.delta_lower > result.delta_upper) {
    result.status =
        static_cast<std::uint32_t>(TgR2StarRowStatus::fixed_point_overflow);
  }
  rows[index] = result;
}

__device__ __forceinline__ bool multiply_u128_u64(
    TgUnsigned128 value, std::uint64_t multiplier, TgUnsigned128* result) {
  const TgUnsigned128 low_product = multiply_u64(value.low, multiplier);
  const TgUnsigned128 high_product = multiply_u64(value.high, multiplier);
  if (high_product.high != 0) return false;
  result->low = low_product.low;
  result->high = low_product.high + high_product.low;
  return result->high >= low_product.high;
}

__device__ __forceinline__ TgUnsigned128 subtract_u128(
    TgUnsigned128 left, TgUnsigned128 right) {
  const std::uint64_t borrow = left.low < right.low;
  return TgUnsigned128{left.low - right.low, left.high - right.high - borrow};
}

__global__ void apply_chunk_transition(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t incoming_lower, std::int64_t incoming_upper,
    TgR2StarChunkSummary* summary) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  TgR2StarChunkSummary result{};
  result.outgoing_lower = incoming_lower;
  result.outgoing_upper = incoming_upper;
  result.minimum_squared_slack =
      TgUnsigned128{kU64Max, kU64Max};
  result.status = static_cast<std::uint32_t>(TgR2StarChunkStatus::valid);
  if (incoming_lower > incoming_upper) {
    result.status = static_cast<std::uint32_t>(
        TgR2StarChunkStatus::prefix_overflow);
    *summary = result;
    return;
  }

  bool have_endpoint = false;
  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t number = lower + index;
    const TgR2StarDirectedRow row = rows[index];
    if (row.status != static_cast<std::uint32_t>(TgR2StarRowStatus::valid) ||
        row.reserved != 0 || row.delta_lower > row.delta_upper) {
      result.status =
          static_cast<std::uint32_t>(TgR2StarChunkStatus::invalid_row);
      result.first_bad_index = number;
      *summary = result;
      return;
    }
    if (!add_i64(result.outgoing_lower, row.delta_lower,
                 &result.outgoing_lower) ||
        !add_i64(result.outgoing_upper, row.delta_upper,
                 &result.outgoing_upper) ||
        result.outgoing_lower > result.outgoing_upper) {
      result.status =
          static_cast<std::uint32_t>(TgR2StarChunkStatus::prefix_overflow);
      result.first_bad_index = number;
      *summary = result;
      return;
    }
    if (number < 3) continue;
    have_endpoint = true;

    if (result.outgoing_lower == kI64Min ||
        result.outgoing_upper == kI64Min) {
      result.status = static_cast<std::uint32_t>(
          TgR2StarChunkStatus::squared_comparison_overflow);
      result.first_bad_index = number;
      *summary = result;
      return;
    }
    const std::uint64_t lower_magnitude = result.outgoing_lower < 0
        ? static_cast<std::uint64_t>(-result.outgoing_lower)
        : static_cast<std::uint64_t>(result.outgoing_lower);
    const std::uint64_t upper_magnitude = result.outgoing_upper < 0
        ? static_cast<std::uint64_t>(-result.outgoing_upper)
        : static_cast<std::uint64_t>(result.outgoing_upper);
    const std::uint64_t magnitude =
        lower_magnitude > upper_magnitude ? lower_magnitude : upper_magnitude;
    if (magnitude > kMaximumEnvelopeMagnitude) {
      result.status = static_cast<std::uint32_t>(
          TgR2StarChunkStatus::squared_comparison_overflow);
      result.first_bad_index = number;
      *summary = result;
      return;
    }
    const TgUnsigned128 left = multiply_u64(100 * magnitude, 100 * magnitude);
    TgUnsigned128 right = multiply_u64(row.log_lower, row.log_lower);
    if (!multiply_u128_u64(right, number, &right) ||
        !multiply_u128_u64(right, 193ULL * 193ULL, &right)) {
      result.status = static_cast<std::uint32_t>(
          TgR2StarChunkStatus::squared_comparison_overflow);
      result.first_bad_index = number;
      *summary = result;
      return;
    }
    if (compare_u128(right, left) < 0) {
      result.status =
          static_cast<std::uint32_t>(TgR2StarChunkStatus::inequality_failed);
      result.first_bad_index = number;
      *summary = result;
      return;
    }
    const TgUnsigned128 slack = subtract_u128(right, left);
    if (compare_u128(slack, result.minimum_squared_slack) < 0) {
      result.minimum_squared_slack = slack;
      result.minimum_slack_index = number;
    }
  }
  if (!have_endpoint) {
    result.status = static_cast<std::uint32_t>(
        TgR2StarChunkStatus::no_envelope_endpoint);
  }
  *summary = result;
}

__device__ __forceinline__ std::uint32_t compute_envelope_slack(
    std::uint64_t number, std::uint64_t log_lower,
    std::int64_t prefix_lower, std::int64_t prefix_upper,
    TgUnsigned128* slack) {
  if (prefix_lower == kI64Min || prefix_upper == kI64Min) {
    return static_cast<std::uint32_t>(
        TgR2StarChunkStatus::squared_comparison_overflow);
  }
  const std::uint64_t lower_magnitude = prefix_lower < 0
      ? static_cast<std::uint64_t>(-prefix_lower)
      : static_cast<std::uint64_t>(prefix_lower);
  const std::uint64_t upper_magnitude = prefix_upper < 0
      ? static_cast<std::uint64_t>(-prefix_upper)
      : static_cast<std::uint64_t>(prefix_upper);
  const std::uint64_t magnitude =
      lower_magnitude > upper_magnitude ? lower_magnitude : upper_magnitude;
  if (magnitude > kMaximumEnvelopeMagnitude) {
    return static_cast<std::uint32_t>(
        TgR2StarChunkStatus::squared_comparison_overflow);
  }
  const TgUnsigned128 left = multiply_u64(100 * magnitude, 100 * magnitude);
  TgUnsigned128 right = multiply_u64(log_lower, log_lower);
  if (!multiply_u128_u64(right, number, &right) ||
      !multiply_u128_u64(right, 193ULL * 193ULL, &right)) {
    return static_cast<std::uint32_t>(
        TgR2StarChunkStatus::squared_comparison_overflow);
  }
  if (compare_u128(right, left) < 0) {
    return static_cast<std::uint32_t>(
        TgR2StarChunkStatus::inequality_failed);
  }
  *slack = subtract_u128(right, left);
  return static_cast<std::uint32_t>(TgR2StarChunkStatus::valid);
}

__global__ void scan_prefix_blocks(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t* prefix_lower, std::int64_t* prefix_upper,
    TgR2StarPrefixBlock* prefix_blocks) {
  if (threadIdx.x != 0) return;
  const std::size_t start =
      static_cast<std::size_t>(blockIdx.x) * kTgR2StarTransitionBlockRows;
  const std::size_t stop =
      start + kTgR2StarTransitionBlockRows < count
          ? start + kTgR2StarTransitionBlockRows
          : count;
  TgR2StarPrefixBlock state{};
  state.status = static_cast<std::uint32_t>(TgR2StarChunkStatus::valid);
  for (std::size_t index = start; index < stop; ++index) {
    const TgR2StarDirectedRow row = rows[index];
    if (row.status != static_cast<std::uint32_t>(TgR2StarRowStatus::valid) ||
        row.reserved != 0 || row.delta_lower > row.delta_upper) {
      state.status =
          static_cast<std::uint32_t>(TgR2StarChunkStatus::invalid_row);
      state.first_bad_index = lower + index;
      break;
    }
    if (!add_i64(state.lower, row.delta_lower, &state.lower) ||
        !add_i64(state.upper, row.delta_upper, &state.upper) ||
        state.lower > state.upper) {
      state.status =
          static_cast<std::uint32_t>(TgR2StarChunkStatus::prefix_overflow);
      state.first_bad_index = lower + index;
      break;
    }
    prefix_lower[index] = state.lower;
    prefix_upper[index] = state.upper;
  }
  prefix_blocks[blockIdx.x] = state;
}

__global__ void compose_prefix_block_offsets(
    std::uint64_t lower, std::size_t count,
    std::int64_t incoming_lower, std::int64_t incoming_upper,
    TgR2StarPrefixBlock* prefix_blocks) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  const std::size_t block_count =
      1 + (count - 1) / kTgR2StarTransitionBlockRows;
  std::int64_t running_lower = incoming_lower;
  std::int64_t running_upper = incoming_upper;
  std::uint32_t failure =
      incoming_lower <= incoming_upper
          ? static_cast<std::uint32_t>(TgR2StarChunkStatus::valid)
          : static_cast<std::uint32_t>(TgR2StarChunkStatus::prefix_overflow);
  std::uint64_t first_bad = failure == 0 ? 0 : lower;
  for (std::size_t block = 0; block < block_count; ++block) {
    TgR2StarPrefixBlock state = prefix_blocks[block];
    if (failure == 0 && state.status != 0) {
      failure = state.status;
      first_bad = state.first_bad_index;
    }
    if (failure != 0) {
      state.status = failure;
      state.first_bad_index = first_bad;
      prefix_blocks[block] = state;
      continue;
    }
    const std::int64_t total_lower = state.lower;
    const std::int64_t total_upper = state.upper;
    state.lower = running_lower;
    state.upper = running_upper;
    if (!add_i64(running_lower, total_lower, &running_lower) ||
        !add_i64(running_upper, total_upper, &running_upper) ||
        running_lower > running_upper) {
      failure =
          static_cast<std::uint32_t>(TgR2StarChunkStatus::prefix_overflow);
      first_bad = lower + block * kTgR2StarTransitionBlockRows;
      state.status = failure;
      state.first_bad_index = first_bad;
    }
    prefix_blocks[block] = state;
  }
}

__global__ void apply_prefix_offsets_and_envelopes(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t* prefix_lower, std::int64_t* prefix_upper,
    const TgR2StarPrefixBlock* prefix_blocks,
    TgR2StarEnvelopeRow* envelope_rows) {
  const std::size_t index =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= count) return;
  const std::uint64_t number = lower + index;
  const std::size_t prefix_block = index / kTgR2StarTransitionBlockRows;
  const TgR2StarPrefixBlock block = prefix_blocks[prefix_block];
  TgR2StarEnvelopeRow result{};
  result.squared_slack = TgUnsigned128{kU64Max, kU64Max};
  if (block.status != 0) {
    result.status = block.status;
    result.index = block.first_bad_index;
    envelope_rows[index] = result;
    return;
  }
  std::int64_t actual_lower = 0;
  std::int64_t actual_upper = 0;
  if (!add_i64(block.lower, prefix_lower[index], &actual_lower) ||
      !add_i64(block.upper, prefix_upper[index], &actual_upper) ||
      actual_lower > actual_upper) {
    result.status =
        static_cast<std::uint32_t>(TgR2StarChunkStatus::prefix_overflow);
    result.index = number;
    envelope_rows[index] = result;
    return;
  }
  prefix_lower[index] = actual_lower;
  prefix_upper[index] = actual_upper;
  result.index = number;
  result.status = static_cast<std::uint32_t>(TgR2StarChunkStatus::valid);
  if (number >= 3) {
    result.status = compute_envelope_slack(
        number, rows[index].log_lower, actual_lower, actual_upper,
        &result.squared_slack);
  } else {
    result.index = 0;
  }
  envelope_rows[index] = result;
}

__global__ void reduce_envelope_blocks(
    std::size_t count, const TgR2StarEnvelopeRow* envelope_rows,
    TgR2StarEnvelopeBlock* envelope_blocks) {
  if (threadIdx.x != 0) return;
  const std::size_t start =
      static_cast<std::size_t>(blockIdx.x) * kTgR2StarTransitionBlockRows;
  const std::size_t stop =
      start + kTgR2StarTransitionBlockRows < count
          ? start + kTgR2StarTransitionBlockRows
          : count;
  TgR2StarEnvelopeBlock result{};
  result.minimum_squared_slack = TgUnsigned128{kU64Max, kU64Max};
  result.status = static_cast<std::uint32_t>(TgR2StarChunkStatus::valid);
  for (std::size_t index = start; index < stop; ++index) {
    const TgR2StarEnvelopeRow row = envelope_rows[index];
    if (row.status != 0) {
      result.status = row.status;
      result.first_bad_index = row.index;
      break;
    }
    if (row.index != 0 &&
        compare_u128(row.squared_slack, result.minimum_squared_slack) < 0) {
      result.minimum_squared_slack = row.squared_slack;
      result.minimum_slack_index = row.index;
    }
  }
  envelope_blocks[blockIdx.x] = result;
}

__global__ void finalize_parallel_summary(
    std::size_t count, const std::int64_t* prefix_lower,
    const std::int64_t* prefix_upper,
    const TgR2StarEnvelopeBlock* envelope_blocks,
    TgR2StarChunkSummary* summary) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  const std::size_t block_count =
      1 + (count - 1) / kTgR2StarTransitionBlockRows;
  TgR2StarChunkSummary result{};
  result.minimum_squared_slack = TgUnsigned128{kU64Max, kU64Max};
  result.status = static_cast<std::uint32_t>(TgR2StarChunkStatus::valid);
  for (std::size_t block = 0; block < block_count; ++block) {
    const TgR2StarEnvelopeBlock state = envelope_blocks[block];
    if (state.status != 0) {
      result.status = state.status;
      result.first_bad_index = state.first_bad_index;
      *summary = result;
      return;
    }
    if (state.minimum_slack_index != 0 &&
        compare_u128(state.minimum_squared_slack,
                     result.minimum_squared_slack) < 0) {
      result.minimum_squared_slack = state.minimum_squared_slack;
      result.minimum_slack_index = state.minimum_slack_index;
    }
  }
  if (result.minimum_slack_index == 0) {
    result.status = static_cast<std::uint32_t>(
        TgR2StarChunkStatus::no_envelope_endpoint);
  } else {
    result.outgoing_lower = prefix_lower[count - 1];
    result.outgoing_upper = prefix_upper[count - 1];
  }
  *summary = result;
}

}  // namespace

cudaError_t launch_tg_r2star_directed_rows(
    std::uint64_t lower, std::size_t count,
    const TgR2StarFactorSupport* factor_support,
    TgR2StarDirectedRow* rows, cudaStream_t stream) {
  if (lower == 0 || count == 0 || factor_support == nullptr || rows == nullptr ||
      count - 1 > std::numeric_limits<std::uint64_t>::max() - lower) {
    return cudaErrorInvalidValue;
  }
  const std::size_t blocks = (count + kThreadsPerBlock - 1) / kThreadsPerBlock;
  if (blocks > kMaximumGridX) return cudaErrorInvalidConfiguration;
  compute_directed_rows<<<static_cast<unsigned int>(blocks), kThreadsPerBlock,
                          0, stream>>>(lower, count, factor_support, rows);
  return cudaGetLastError();
}

cudaError_t launch_tg_r2star_chunk_transition(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t incoming_lower, std::int64_t incoming_upper,
    TgR2StarChunkSummary* summary, cudaStream_t stream) {
  if (lower == 0 || count == 0 || rows == nullptr || summary == nullptr ||
      count - 1 > std::numeric_limits<std::uint64_t>::max() - lower) {
    return cudaErrorInvalidValue;
  }
  apply_chunk_transition<<<1, 1, 0, stream>>>(
      lower, count, rows, incoming_lower, incoming_upper, summary);
  return cudaGetLastError();
}

cudaError_t launch_tg_r2star_parallel_chunk_transition(
    std::uint64_t lower, std::size_t count,
    const TgR2StarDirectedRow* rows,
    std::int64_t incoming_lower, std::int64_t incoming_upper,
    std::int64_t* prefix_lower, std::int64_t* prefix_upper,
    TgR2StarPrefixBlock* prefix_blocks,
    TgR2StarEnvelopeRow* envelope_rows,
    TgR2StarEnvelopeBlock* envelope_blocks,
    TgR2StarChunkSummary* summary, cudaStream_t stream) {
  if (lower == 0 || count == 0 || rows == nullptr || prefix_lower == nullptr ||
      prefix_upper == nullptr || prefix_blocks == nullptr ||
      envelope_rows == nullptr || envelope_blocks == nullptr ||
      summary == nullptr ||
      count - 1 > std::numeric_limits<std::uint64_t>::max() - lower) {
    return cudaErrorInvalidValue;
  }
  const std::size_t transition_blocks =
      1 + (count - 1) / kTgR2StarTransitionBlockRows;
  const std::size_t row_blocks = 1 + (count - 1) / kThreadsPerBlock;
  if (transition_blocks > kMaximumGridX || row_blocks > kMaximumGridX) {
    return cudaErrorInvalidConfiguration;
  }
  scan_prefix_blocks<<<static_cast<unsigned int>(transition_blocks), 1, 0,
                       stream>>>(lower, count, rows, prefix_lower,
                                 prefix_upper, prefix_blocks);
  cudaError_t status = cudaGetLastError();
  if (status != cudaSuccess) return status;
  compose_prefix_block_offsets<<<1, 1, 0, stream>>>(
      lower, count, incoming_lower, incoming_upper, prefix_blocks);
  status = cudaGetLastError();
  if (status != cudaSuccess) return status;
  apply_prefix_offsets_and_envelopes<<<static_cast<unsigned int>(row_blocks),
                                       kThreadsPerBlock, 0, stream>>>(
      lower, count, rows, prefix_lower, prefix_upper, prefix_blocks,
      envelope_rows);
  status = cudaGetLastError();
  if (status != cudaSuccess) return status;
  reduce_envelope_blocks<<<static_cast<unsigned int>(transition_blocks), 1, 0,
                           stream>>>(count, envelope_rows, envelope_blocks);
  status = cudaGetLastError();
  if (status != cudaSuccess) return status;
  finalize_parallel_summary<<<1, 1, 0, stream>>>(
      count, prefix_lower, prefix_upper, envelope_blocks, summary);
  return cudaGetLastError();
}

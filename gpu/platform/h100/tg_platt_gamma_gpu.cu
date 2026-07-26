// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_gamma_gpu.cuh"

#include <cuda_runtime.h>

#include <cmath>
#include <cstdint>

namespace sparkinterval::tg::platt_gamma_gpu {
namespace {

using pw::ComplexInterval;
using pw::RealInterval;

__device__ __forceinline__ RealInterval add(RealInterval x, RealInterval y) {
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
}

__device__ __forceinline__ RealInterval sub(RealInterval x, RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval mul(RealInterval x, RealInterval y) {
  if (x.lo >= 0.0 && y.lo >= 0.0) {
    return {__dmul_rd(x.lo, y.lo), __dmul_ru(x.hi, y.hi)};
  }
  if (x.hi <= 0.0 && y.hi <= 0.0) {
    return {__dmul_rd(x.hi, y.hi), __dmul_ru(x.lo, y.lo)};
  }
  if (x.lo >= 0.0 && y.hi <= 0.0) {
    return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.lo, y.hi)};
  }
  if (x.hi <= 0.0 && y.lo >= 0.0) {
    return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.hi, y.lo)};
  }
  const double down[] = {__dmul_rd(x.lo, y.lo), __dmul_rd(x.lo, y.hi),
                         __dmul_rd(x.hi, y.lo), __dmul_rd(x.hi, y.hi)};
  const double up[] = {__dmul_ru(x.lo, y.lo), __dmul_ru(x.lo, y.hi),
                       __dmul_ru(x.hi, y.lo), __dmul_ru(x.hi, y.hi)};
  return {fmin(fmin(down[0], down[1]), fmin(down[2], down[3])),
          fmax(fmax(up[0], up[1]), fmax(up[2], up[3]))};
}

__device__ __forceinline__ ComplexInterval cscale(ComplexInterval x,
                                                   RealInterval y) {
  return {mul(x.re, y), mul(x.im, y)};
}

__device__ __forceinline__ ComplexInterval cmul(ComplexInterval x,
                                                 ComplexInterval y) {
  return {sub(mul(x.re, y.re), mul(x.im, y.im)),
          add(mul(x.re, y.im), mul(x.im, y.re))};
}

__device__ __forceinline__ RealInterval negate(RealInterval x) {
  return {-x.hi, -x.lo};
}

__device__ __forceinline__ double factorial_as_double(unsigned degree) {
  double result = 1.0;
  for (unsigned value = 2U; value <= degree; ++value) {
    result *= static_cast<double>(value);
  }
  return result;
}

__device__ __forceinline__ RealInterval signed_reciprocal_factorial(
    unsigned degree, bool negative) {
  const double denominator = factorial_as_double(degree);
  const RealInterval positive{__ddiv_rd(1.0, denominator),
                              __ddiv_ru(1.0, denominator)};
  return negative ? negate(positive) : positive;
}

__device__ __forceinline__ RealInterval widen_symmetric(RealInterval value,
                                                         double radius) {
  return {__dsub_rd(value.lo, radius), __dadd_ru(value.hi, radius)};
}

__device__ __forceinline__ RealInterval positive_power(RealInterval x,
                                                        unsigned exponent) {
  RealInterval result{1.0, 1.0};
  for (unsigned index = 0U; index < exponent; ++index) result = mul(result, x);
  return result;
}

// Directed Maclaurin enclosures on 0 <= x <= pi/4.  The deliberately loose
// denominators dominate the first omitted terms over this range.
__device__ __forceinline__ ComplexInterval sin_cos_pi_over_four(
    RealInterval x) {
  const RealInterval square = mul(x, x);
  RealInterval sine_polynomial = signed_reciprocal_factorial(17U, false);
  for (int degree = 15; degree >= 1; degree -= 2) {
    const bool negative = ((degree - 1) / 2) % 2 != 0;
    sine_polynomial = add(
        mul(sine_polynomial, square),
        signed_reciprocal_factorial(static_cast<unsigned>(degree), negative));
  }
  RealInterval sine = mul(x, sine_polynomial);
  sine = widen_symmetric(
      sine, __ddiv_ru(positive_power(x, 19U).hi, 1.0e17));

  RealInterval cosine = signed_reciprocal_factorial(18U, true);
  for (int degree = 16; degree >= 0; degree -= 2) {
    const bool negative = (degree / 2) % 2 != 0;
    cosine = add(
        mul(cosine, square),
        signed_reciprocal_factorial(static_cast<unsigned>(degree), negative));
  }
  cosine = widen_symmetric(
      cosine, __ddiv_ru(positive_power(x, 20U).hi, 2.0e18));
  return {cosine, sine};
}

__device__ __forceinline__ ComplexInterval sin_cos_small_signed(
    RealInterval x) {
  const RealInterval square = mul(x, x);
  RealInterval sine_polynomial = signed_reciprocal_factorial(17U, false);
  for (int degree = 15; degree >= 1; degree -= 2) {
    const bool negative = ((degree - 1) / 2) % 2 != 0;
    sine_polynomial = add(
        mul(sine_polynomial, square),
        signed_reciprocal_factorial(static_cast<unsigned>(degree), negative));
  }
  RealInterval sine = mul(x, sine_polynomial);
  RealInterval cosine = signed_reciprocal_factorial(18U, true);
  for (int degree = 16; degree >= 0; degree -= 2) {
    const bool negative = (degree / 2) % 2 != 0;
    cosine = add(
        mul(cosine, square),
        signed_reciprocal_factorial(static_cast<unsigned>(degree), negative));
  }
  const double magnitude = fmax(-x.lo, x.hi);
  double sine_tail = 1.0;
  for (unsigned index = 0; index < 19U; ++index) {
    sine_tail = __dmul_ru(sine_tail, magnitude);
  }
  sine_tail = __ddiv_ru(sine_tail, 1.0e17);
  double cosine_tail = 1.0;
  for (unsigned index = 0; index < 20U; ++index) {
    cosine_tail = __dmul_ru(cosine_tail, magnitude);
  }
  cosine_tail = __ddiv_ru(cosine_tail, 2.0e18);
  return {widen_symmetric(cosine, cosine_tail),
          widen_symmetric(sine, sine_tail)};
}

__device__ __forceinline__ RealInterval exp_interval(RealInterval x) {
  constexpr double ln2_lo = 0x1.62e42fefa39eep-1;
  constexpr double ln2_hi = 0x1.62e42fefa39f0p-1;
  constexpr double ln2_mid = 0x1.62e42fefa39efp-1;
  // The midpoint only chooses an integral binary shift; it is not part of an
  // enclosure endpoint calculation.
  const double midpoint = x.lo / 2.0 + x.hi / 2.0;
  const int exponent = static_cast<int>(floor(midpoint / ln2_mid));
  const RealInterval exponent_interval{static_cast<double>(exponent),
                                       static_cast<double>(exponent)};
  const RealInterval residual =
      sub(x, mul(exponent_interval, {ln2_lo, ln2_hi}));
  if (residual.lo < -0.7 || residual.hi > 0.7) {
    return {-INFINITY, INFINITY};
  }
  RealInterval polynomial = signed_reciprocal_factorial(18U, false);
  for (int degree = 17; degree >= 0; --degree) {
    polynomial = add(
        mul(polynomial, residual),
        signed_reciprocal_factorial(static_cast<unsigned>(degree), false));
  }
  polynomial = widen_symmetric(polynomial, 1.0e-18);
  const double lower = ldexp(polynomial.lo, exponent);
  const double upper = ldexp(polynomial.hi, exponent);
  return {__longlong_as_double(__double_as_longlong(lower) - 1ULL),
          __longlong_as_double(__double_as_longlong(upper) + 1ULL)};
}

struct UInt192 {
  std::uint64_t limb0;
  std::uint64_t limb1;
  std::uint64_t limb2;
};

__device__ __forceinline__ UInt192 multiply_low_192(
    pw::FixedTurn192 value, std::uint64_t multiplier) {
  UInt192 result{};
  result.limb0 = value.limb0 * multiplier;
  std::uint64_t carry = __umul64hi(value.limb0, multiplier);
  const std::uint64_t middle_product = value.limb1 * multiplier;
  result.limb1 = middle_product + carry;
  const std::uint64_t middle_overflow = result.limb1 < middle_product ? 1U : 0U;
  carry = __umul64hi(value.limb1, multiplier) + middle_overflow;
  result.limb2 = value.limb2 * multiplier + carry;
  return result;
}

__device__ __forceinline__ UInt192 subtract_192(UInt192 x, UInt192 y) {
  UInt192 result{};
  result.limb0 = x.limb0 - y.limb0;
  const std::uint64_t borrow0 = x.limb0 < y.limb0 ? 1U : 0U;
  const std::uint64_t adjusted1 = y.limb1 + borrow0;
  const std::uint64_t carry1 = adjusted1 < y.limb1 ? 1U : 0U;
  result.limb1 = x.limb1 - adjusted1;
  const std::uint64_t borrow1 =
      (x.limb1 < adjusted1 || carry1 != 0U) ? 1U : 0U;
  result.limb2 = x.limb2 - y.limb2 - borrow1;
  return result;
}

__device__ __forceinline__ UInt192 add_192(UInt192 x, UInt192 y) {
  UInt192 result{};
  result.limb0 = x.limb0 + y.limb0;
  const std::uint64_t carry0 = result.limb0 < x.limb0 ? 1U : 0U;
  const std::uint64_t middle = x.limb1 + y.limb1;
  const std::uint64_t carry_middle = middle < x.limb1 ? 1U : 0U;
  result.limb1 = middle + carry0;
  const std::uint64_t carry1 =
      (result.limb1 < middle || carry_middle != 0U) ? 1U : 0U;
  result.limb2 = x.limb2 + y.limb2 + carry1;
  return result;
}

__device__ __forceinline__ UInt192 negate_192(UInt192 value) {
  return subtract_192(UInt192{}, value);
}

__device__ __forceinline__ ComplexInterval fixed_product_phase(
    UInt192 product, double phase_error) {
  const unsigned octant = static_cast<unsigned>(product.limb2 >> 61U);
  product.limb2 &= (1ULL << 61U) - 1ULL;
  if ((octant & 1U) != 0U) {
    const UInt192 one_eighth{0U, 0U, 1ULL << 61U};
    product = subtract_192(one_eighth, product);
  }
  const bool has_low_bits = product.limb0 != 0U || product.limb1 != 0U;
  const double turn_lo = ldexp(__ull2double_rd(product.limb2), -64);
  const std::uint64_t upper_limb =
      product.limb2 + (has_low_bits ? 1ULL : 0ULL);
  const double turn_hi = ldexp(__ull2double_ru(upper_limb), -64);
  constexpr double pi_lo = 0x1.921fb54442d17p+1;
  constexpr double pi_hi = 0x1.921fb54442d19p+1;
  const RealInterval reduced{__dmul_rd(turn_lo, 2.0 * pi_lo),
                             __dmul_ru(turn_hi, 2.0 * pi_hi)};
  const ComplexInterval base = sin_cos_pi_over_four(reduced);
  RealInterval cosine{};
  RealInterval sine{};
  switch (octant) {
    case 0U: cosine = base.re; sine = base.im; break;
    case 1U: cosine = base.im; sine = base.re; break;
    case 2U: cosine = negate(base.im); sine = base.re; break;
    case 3U: cosine = negate(base.re); sine = base.im; break;
    case 4U: cosine = negate(base.re); sine = negate(base.im); break;
    case 5U: cosine = negate(base.im); sine = negate(base.re); break;
    case 6U: cosine = base.im; sine = negate(base.re); break;
    default: cosine = base.re; sine = negate(base.im); break;
  }
  return {widen_symmetric(cosine, phase_error),
          widen_symmetric(sine, phase_error)};
}

__device__ __forceinline__ ComplexInterval fixed_anchor_step_phase(
    pw::FixedTurn192 anchor, pw::FixedTurn192 step, int grid_offset,
    double anchor_error, double step_error) {
  const std::uint64_t magnitude = static_cast<std::uint64_t>(
      grid_offset < 0 ? -static_cast<std::int64_t>(grid_offset)
                      : static_cast<std::int64_t>(grid_offset));
  UInt192 displacement = multiply_low_192(step, magnitude);
  if (grid_offset < 0) displacement = negate_192(displacement);
  const UInt192 product =
      add_192({anchor.limb0, anchor.limb1, anchor.limb2}, displacement);
  const double phase_error = __dadd_ru(
      anchor_error, __dmul_ru(static_cast<double>(magnitude), step_error));
  return fixed_product_phase(product, phase_error);
}

__global__ void synthesize_gamma_rows(
    const pw::GammaTaylorStreamRecord* records, GammaRowBatchView output) {
  const std::uint32_t record_index = blockIdx.y;
  if (record_index >= output.record_count) return;

  __shared__ pw::GammaTaylorStreamRecord projection;
  static_assert(sizeof(projection) % sizeof(std::uint64_t) == 0U);
  auto* projection_words = reinterpret_cast<std::uint64_t*>(&projection);
  const auto* source_words = reinterpret_cast<const std::uint64_t*>(
      records + record_index);
  for (std::uint32_t word = threadIdx.x;
       word < sizeof(projection) / sizeof(std::uint64_t);
       word += blockDim.x) {
    projection_words[word] = source_words[word];
  }
  __syncthreads();

  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= pw::kBucketCount) return;
  const int grid_offset = static_cast<int>(index) -
                          static_cast<int>(pw::kBucketCount / 2U);
  // The multiplication is exact: 21/128 and every relevant integral offset
  // have exact binary64 representations.
  const double u_value = static_cast<double>(grid_offset) * (21.0 / 128.0);
  const RealInterval u{u_value, u_value};

  RealInterval real_log = projection.real_coefficients[5];
  for (int degree = 4; degree >= 0; --degree) {
    real_log = add(mul(real_log, u), projection.real_coefficients[degree]);
  }
  const RealInterval u_squared = mul(u, u);
  const RealInterval inverse_gaussian_denominator{
      __ddiv_rd(1.0, 26912.0), __ddiv_ru(1.0, 26912.0)};
  real_log = sub(real_log, mul(u_squared, inverse_gaussian_denominator));
  real_log = widen_symmetric(real_log, projection.logarithm_remainder);
  const RealInterval amplitude = exp_interval(real_log);

  RealInterval residual_phase = projection.imaginary_coefficients[5];
  for (int degree = 4; degree >= 2; --degree) {
    residual_phase =
        add(mul(residual_phase, u), projection.imaginary_coefficients[degree]);
  }
  residual_phase = mul(mul(residual_phase, u), u);
  residual_phase =
      widen_symmetric(residual_phase, projection.logarithm_remainder);
  const ComplexInterval anchor = fixed_anchor_step_phase(
      projection.phase_anchor, projection.phase_grid_step, grid_offset,
      projection.phase_anchor_error, projection.phase_grid_step_error);
  const ComplexInterval residual = sin_cos_small_signed(residual_phase);
  output.rows[static_cast<std::uint64_t>(record_index) * output.row_stride +
              index] = cscale(cmul(anchor, residual), amplitude);
}

__device__ __forceinline__ std::uint64_t mix64(std::uint64_t value) {
  value ^= value >> 30U;
  value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27U;
  value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

__global__ void summarize_gamma_rows(GammaRowBatchView input,
                                     GammaRowSummary* summaries) {
  const std::uint32_t record_index = blockIdx.x;
  if (record_index >= input.record_count) return;
  const std::uint32_t lane = threadIdx.x;
  std::uint64_t hashes[4] = {};
  std::uint64_t invalid = 0U;
  double max_real_width = 0.0;
  double max_imaginary_width = 0.0;
  const std::uint64_t logical_block = input.first_block + record_index;
  for (std::uint32_t index = lane; index < pw::kBucketCount;
       index += blockDim.x) {
    const ComplexInterval value =
        input.rows[static_cast<std::uint64_t>(record_index) *
                       input.row_stride +
                   index];
    const bool valid = isfinite(value.re.lo) && isfinite(value.re.hi) &&
                       isfinite(value.im.lo) && isfinite(value.im.hi) &&
                       value.re.lo <= value.re.hi &&
                       value.im.lo <= value.im.hi;
    invalid += valid ? 0U : 1U;
    if (valid) {
      max_real_width =
          fmax(max_real_width, __dsub_ru(value.re.hi, value.re.lo));
      max_imaginary_width =
          fmax(max_imaginary_width, __dsub_ru(value.im.hi, value.im.lo));
    }
    // The row's absolute logical block is committed by the ordered host
    // summary.  Keeping the cell reduction independent of it lets one fixed
    // CUDA graph serve every microbatch without mutable kernel parameters.
    const std::uint64_t key =
        mix64(static_cast<std::uint64_t>(index) << 32U);
    const std::uint64_t words[4] = {
        static_cast<std::uint64_t>(__double_as_longlong(value.re.lo)),
        static_cast<std::uint64_t>(__double_as_longlong(value.re.hi)),
        static_cast<std::uint64_t>(__double_as_longlong(value.im.lo)),
        static_cast<std::uint64_t>(__double_as_longlong(value.im.hi))};
#pragma unroll
    for (unsigned component = 0; component < 4U; ++component) {
      hashes[component] ^=
          mix64(words[component] ^ key ^
                (0x9e3779b97f4a7c15ULL * (component + 1U)));
    }
  }

  __shared__ std::uint64_t shared_hashes[4][256];
  __shared__ std::uint64_t shared_invalid[256];
  __shared__ double shared_real_width[256];
  __shared__ double shared_imaginary_width[256];
#pragma unroll
  for (unsigned component = 0; component < 4U; ++component) {
    shared_hashes[component][lane] = hashes[component];
  }
  shared_invalid[lane] = invalid;
  shared_real_width[lane] = max_real_width;
  shared_imaginary_width[lane] = max_imaginary_width;
  __syncthreads();
  for (unsigned stride = blockDim.x / 2U; stride != 0U; stride >>= 1U) {
    if (lane < stride) {
#pragma unroll
      for (unsigned component = 0; component < 4U; ++component) {
        shared_hashes[component][lane] ^=
            shared_hashes[component][lane + stride];
      }
      shared_invalid[lane] += shared_invalid[lane + stride];
      shared_real_width[lane] =
          fmax(shared_real_width[lane], shared_real_width[lane + stride]);
      shared_imaginary_width[lane] = fmax(
          shared_imaginary_width[lane],
          shared_imaginary_width[lane + stride]);
    }
    __syncthreads();
  }
  if (lane == 0U) {
    summaries[record_index] =
        {logical_block,
         shared_hashes[0][0],
         shared_hashes[1][0],
         shared_hashes[2][0],
         shared_hashes[3][0],
         shared_invalid[0],
         shared_real_width[0],
         shared_imaginary_width[0]};
  }
}

__device__ __forceinline__ double disk_norm_upper(double x, double y) {
  const double large = fmax(x, y);
  const double small = fmin(x, y);
  if (large == 0.0) return 0.0;
  const double ratio = __ddiv_ru(small, large);
  return __dmul_ru(
      large, __dsqrt_ru(__dadd_ru(1.0, __dmul_ru(ratio, ratio))));
}

__global__ void convert_gamma_rows_to_disks(GammaRowBatchView input,
                                             GammaDiskRowBatchView output) {
  const std::uint32_t record = blockIdx.y;
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < pw::kBucketCount; index += blockDim.x * gridDim.x) {
    const std::uint64_t input_offset =
        static_cast<std::uint64_t>(record) * input.row_stride + index;
    const std::uint64_t output_offset =
        static_cast<std::uint64_t>(record) * output.row_stride + index;
    const pw::ComplexInterval value = input.rows[input_offset];
    const double real_center =
        __dadd_rn(__dmul_rn(value.re.lo, 0.5),
                  __dmul_rn(value.re.hi, 0.5));
    const double imaginary_center =
        __dadd_rn(__dmul_rn(value.im.lo, 0.5),
                  __dmul_rn(value.im.hi, 0.5));
    if (!isfinite(real_center) || !isfinite(imaginary_center) ||
        real_center < value.re.lo || real_center > value.re.hi ||
        imaginary_center < value.im.lo ||
        imaginary_center > value.im.hi) {
      output.rows[output_offset] =
          {{0.0, 0.0}, {0.0, 0.0}, INFINITY};
      continue;
    }
    const double real_radius =
        fmax(__dsub_ru(real_center, value.re.lo),
             __dsub_ru(value.re.hi, real_center));
    const double imaginary_radius =
        fmax(__dsub_ru(imaginary_center, value.im.lo),
             __dsub_ru(value.im.hi, imaginary_center));
    output.rows[output_offset] = {
        {real_center, 0.0}, {imaginary_center, 0.0},
        disk_norm_upper(real_radius, imaginary_radius)};
  }
}

__global__ void summarize_gamma_disks(GammaDiskRowBatchView input,
                                      GammaDiskRowSummary* summaries) {
  const std::uint32_t record = blockIdx.x;
  const std::uint32_t lane = threadIdx.x;
  std::uint64_t digest = 0U;
  std::uint64_t invalid = 0U;
  double maximum_radius = 0.0;
  for (std::uint32_t index = lane; index < pw::kBucketCount;
       index += blockDim.x) {
    const pw::ComplexDisk106 value =
        input.rows[static_cast<std::uint64_t>(record) * input.row_stride +
                   index];
    if (!isfinite(value.real.hi) || !isfinite(value.real.lo) ||
        !isfinite(value.imaginary.hi) ||
        !isfinite(value.imaginary.lo) || !isfinite(value.radius) ||
        value.radius < 0.0) {
      ++invalid;
    }
    maximum_radius = fmax(maximum_radius, value.radius);
    const std::uint64_t key =
        mix64(static_cast<std::uint64_t>(index) << 32U);
    digest ^= mix64(
        static_cast<std::uint64_t>(__double_as_longlong(value.real.hi)) ^
        key);
    digest ^= mix64(
        static_cast<std::uint64_t>(__double_as_longlong(value.imaginary.hi)) ^
        (key + 0x9e3779b97f4a7c15ULL));
    digest ^= mix64(
        static_cast<std::uint64_t>(__double_as_longlong(value.radius)) ^
        (key + 0x3c6ef372fe94f82aULL));
  }
  __shared__ std::uint64_t shared_digest[256];
  __shared__ std::uint64_t shared_invalid[256];
  __shared__ double shared_radius[256];
  shared_digest[lane] = digest;
  shared_invalid[lane] = invalid;
  shared_radius[lane] = maximum_radius;
  __syncthreads();
  for (unsigned stride = blockDim.x / 2U; stride != 0U; stride >>= 1U) {
    if (lane < stride) {
      shared_digest[lane] ^= shared_digest[lane + stride];
      shared_invalid[lane] += shared_invalid[lane + stride];
      shared_radius[lane] =
          fmax(shared_radius[lane], shared_radius[lane + stride]);
    }
    __syncthreads();
  }
  if (lane == 0U) {
    summaries[record] = {input.first_block + record, shared_digest[0],
                         shared_invalid[0], shared_radius[0]};
  }
}

}  // namespace

void launch_synthesize_gamma_rows(
    const pw::GammaTaylorStreamRecord* authenticated_records,
    GammaRowBatchView output, cudaStream_t stream) {
  constexpr std::uint32_t threads = 256U;
  const dim3 blocks((pw::kBucketCount + threads - 1U) / threads,
                    output.record_count);
  synthesize_gamma_rows<<<blocks, threads, 0U, stream>>>(authenticated_records,
                                                         output);
}

void launch_summarize_gamma_rows(GammaRowBatchView input,
                                 GammaRowSummary* summaries,
                                 cudaStream_t stream) {
  summarize_gamma_rows<<<input.record_count, 256U, 0U, stream>>>(input,
                                                                 summaries);
}

void launch_convert_gamma_rows_to_disks(GammaRowBatchView input,
                                        GammaDiskRowBatchView output,
                                        cudaStream_t stream) {
  if (input.record_count != output.record_count) return;
  constexpr std::uint32_t threads = 256U;
  const dim3 blocks((pw::kBucketCount + threads - 1U) / threads,
                    input.record_count);
  convert_gamma_rows_to_disks<<<blocks, threads, 0U, stream>>>(input,
                                                               output);
}

void launch_summarize_gamma_disks(GammaDiskRowBatchView input,
                                  GammaDiskRowSummary* summaries,
                                  cudaStream_t stream) {
  summarize_gamma_disks<<<input.record_count, 256U, 0U, stream>>>(input,
                                                                  summaries);
}

}  // namespace sparkinterval::tg::platt_gamma_gpu

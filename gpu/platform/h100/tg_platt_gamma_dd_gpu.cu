// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_gamma_dd_gpu.cuh"

#include <cuda_runtime.h>

#include <cmath>
#include <cstdint>

namespace sparkinterval::tg::platt_gamma_dd_gpu {
namespace {

using pw::ComplexDisk106;
using pw::DoubleDouble;
using pw::RealDisk106;

constexpr double kDDFloor = 0x0.0000000000001p-1022;

struct TwoSum {
  double sum;
  double residual;
};

struct DDResult {
  DoubleDouble value;
  double error;
};

__device__ __forceinline__ TwoSum two_sum(double a, double b) {
  const double sum = __dadd_rn(a, b);
  const double virtual_b = __dsub_rn(sum, a);
  const double residual = __dadd_rn(
      __dsub_rn(a, __dsub_rn(sum, virtual_b)),
      __dsub_rn(b, virtual_b));
  return {sum, residual};
}

__device__ __forceinline__ TwoSum two_product(double a, double b) {
  const double product = __dmul_rn(a, b);
  return {product, fma(a, b, -product)};
}

__device__ __forceinline__ DDResult add_center(DoubleDouble a,
                                                DoubleDouble b) {
  const TwoSum high = two_sum(a.hi, b.hi);
  double low = 0.0;
  double error = kDDFloor;
  const double terms[] = {high.residual, a.lo, b.lo};
#pragma unroll
  for (int index = 0; index < 3; ++index) {
    const TwoSum next = two_sum(low, terms[index]);
    low = next.sum;
    error = __dadd_ru(error, fabs(next.residual));
    error = __dadd_ru(error, kDDFloor);
  }
  const TwoSum normalized = two_sum(high.sum, low);
  error = __dadd_ru(error, kDDFloor);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ DDResult mul_center(DoubleDouble a,
                                                DoubleDouble b) {
  const TwoSum products[] = {
      two_product(a.hi, b.hi), two_product(a.hi, b.lo),
      two_product(a.lo, b.hi), two_product(a.lo, b.lo)};
  double low = 0.0;
  double error = __dmul_ru(4.0, kDDFloor);
  const double terms[] = {
      products[0].residual, products[1].sum, products[1].residual,
      products[2].sum,      products[2].residual, products[3].sum,
      products[3].residual};
#pragma unroll
  for (int index = 0; index < 7; ++index) {
    const TwoSum next = two_sum(low, terms[index]);
    low = next.sum;
    error = __dadd_ru(error, fabs(next.residual));
    error = __dadd_ru(error, kDDFloor);
  }
  const TwoSum normalized = two_sum(products[0].sum, low);
  error = __dadd_ru(error, kDDFloor);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ double abs_upper(DoubleDouble value) {
  return __dadd_ru(fabs(value.hi), fabs(value.lo));
}

__device__ __forceinline__ double norm_upper(DoubleDouble re,
                                              DoubleDouble im) {
  const double x = abs_upper(re);
  const double y = abs_upper(im);
  const double large = fmax(x, y);
  const double small = fmin(x, y);
  if (large == 0.0) return 0.0;
  const double ratio = __ddiv_ru(small, large);
  return __dmul_ru(
      large, __dsqrt_ru(__dadd_ru(1.0, __dmul_ru(ratio, ratio))));
}

__device__ __forceinline__ RealDisk106 real_add(RealDisk106 x,
                                                 RealDisk106 y) {
  const DDResult center = add_center(x.center, y.center);
  return {center.value,
          __dadd_ru(__dadd_ru(x.radius, y.radius), center.error)};
}

__device__ __forceinline__ RealDisk106 real_mul(RealDisk106 x,
                                                 RealDisk106 y) {
  const DDResult center = mul_center(x.center, y.center);
  const double nx = abs_upper(x.center);
  const double ny = abs_upper(y.center);
  double radius = __dadd_ru(center.error, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {center.value, radius};
}

__device__ __forceinline__ DoubleDouble negate(DoubleDouble x) {
  return {-x.hi, -x.lo};
}

__device__ __forceinline__ RealDisk106 real_negate(RealDisk106 x) {
  return {negate(x.center), x.radius};
}

__device__ __forceinline__ ComplexDisk106 complex_mul(ComplexDisk106 x,
                                                       ComplexDisk106 y) {
  const DDResult rr = mul_center(x.real, y.real);
  const DDResult ii = mul_center(x.imaginary, y.imaginary);
  const DDResult ri = mul_center(x.real, y.imaginary);
  const DDResult ir = mul_center(x.imaginary, y.real);
  const DDResult re = add_center(rr.value, negate(ii.value));
  const DDResult im = add_center(ri.value, ir.value);
  const double re_error = __dadd_ru(__dadd_ru(rr.error, ii.error), re.error);
  const double im_error = __dadd_ru(__dadd_ru(ri.error, ir.error), im.error);
  const double local = norm_upper({re_error, 0.0}, {im_error, 0.0});
  const double nx = norm_upper(x.real, x.imaginary);
  const double ny = norm_upper(y.real, y.imaginary);
  double radius = __dadd_ru(local, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

__device__ __forceinline__ ComplexDisk106 complex_scale(ComplexDisk106 x,
                                                         RealDisk106 y) {
  const DDResult re = mul_center(x.real, y.center);
  const DDResult im = mul_center(x.imaginary, y.center);
  const double local = norm_upper({re.error, 0.0}, {im.error, 0.0});
  const double nx = norm_upper(x.real, x.imaginary);
  const double ny = abs_upper(y.center);
  double radius = __dadd_ru(local, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

// All table entries are exact rational coefficients projected as a two-limb
// centre plus the exact residual rounded upward.  These are data, not results
// of a device transcendental implementation.
__device__ __constant__ RealDisk106 kExpCoefficients[25] = {
    {{0x1p+0, 0x0p+0}, 0x0p+0},
    {{0x1p+0, 0x0p+0}, 0x0p+0},
    {{0x1p-1, 0x0p+0}, 0x0p+0},
    {{0x1.5555555555555p-3, 0x1.5555555555555p-57}, 0x1.5555555555556p-111},
    {{0x1.5555555555555p-5, 0x1.5555555555555p-59}, 0x1.5555555555556p-113},
    {{0x1.1111111111111p-7, 0x1.1111111111111p-63}, 0x1.1111111111112p-119},
    {{0x1.6c16c16c16c17p-10, -0x1.f49f49f49f49fp-65}, 0x1.27d27d27d27d3p-119},
    {{0x1.a01a01a01a01ap-13, 0x1.a01a01a01a01ap-73}, 0x1.a01a01a01a01bp-133},
    {{0x1.a01a01a01a01ap-16, 0x1.a01a01a01a01ap-76}, 0x1.a01a01a01a01bp-136},
    {{0x1.71de3a556c734p-19, -0x1.c154f8ddc6c00p-73}, 0x1.71de3a556c734p-127},
    {{0x1.27e4fb7789f5cp-22, 0x1.cbbc05b4fa99ap-76}, 0x1.c6d278883e8f5p-132},
    {{0x1.ae64567f544e4p-26, -0x1.c062e06d1f209p-80}, 0x1.c7880adcbc46ep-136},
    {{0x1.1eed8eff8d898p-29, -0x1.2aec959e14c06p-83}, 0x1.2fb0073dd2d9fp-139},
    {{0x1.6124613a86d09p-33, 0x1.f28e0cc748ebep-87}, 0x1.7b2c4c8a840bcp-141},
    {{0x1.93974a8c07c9dp-37, 0x1.05d6f8a2efd1fp-92}, 0x1.3aa3346236a5ep-147},
    {{0x1.ae7f3e733b81fp-41, 0x1.1d8656b0ee8cbp-97}, 0x1.6e142a138f825p-157},
    {{0x1.ae7f3e733b81fp-45, 0x1.1d8656b0ee8cbp-101}, 0x1.6e142a138f825p-161},
    {{0x1.952c77030ad4ap-49, 0x1.ac981465ddc6cp-103}, 0x1.588b72e53bc5fp-165},
    {{0x1.6827863b97d97p-53, 0x1.eec01221a8b0bp-107}, 0x1.568798662118bp-161},
    {{0x1.2f49b46814157p-57, 0x1.2650f61dbdcb4p-112}, 0x1.69502917cbf3bp-166},
    {{0x1.e542ba4020225p-62, 0x1.ea72b4afe3c2fp-120}, 0x1.44020dfd65c8dp-174},
    {{0x1.71b8ef6dcf572p-66, -0x1.d043ae40c4647p-120}, 0x1.486121e81d5fep-176},
    {{0x1.0ce396db7f853p-70, -0x1.aebcdbd20331cp-124}, 0x1.38a88578b4d75p-178},
    {{0x1.761b41316381ap-75, -0x1.3423c7d91404fp-130}, 0x1.e6135bfc1194ap-185},
    {{0x1.f2cf01972f578p-80, -0x1.9ada5fcc1ab14p-135}, 0x1.440ce7fd610dcp-189}};

__device__ __constant__ RealDisk106 kSineCoefficients[20] = {
    {{0x1p+0, 0x0p+0}, 0x0p+0},
    {{-0x1.5555555555555p-3, -0x1.5555555555555p-57}, 0x1.5555555555556p-111},
    {{0x1.1111111111111p-7, 0x1.1111111111111p-63}, 0x1.1111111111112p-119},
    {{-0x1.a01a01a01a01ap-13, -0x1.a01a01a01a01ap-73}, 0x1.a01a01a01a01bp-133},
    {{0x1.71de3a556c734p-19, -0x1.c154f8ddc6c00p-73}, 0x1.71de3a556c734p-127},
    {{-0x1.ae64567f544e4p-26, 0x1.c062e06d1f209p-80}, 0x1.c7880adcbc46ep-136},
    {{0x1.6124613a86d09p-33, 0x1.f28e0cc748ebep-87}, 0x1.7b2c4c8a840bcp-141},
    {{-0x1.ae7f3e733b81fp-41, -0x1.1d8656b0ee8cbp-97}, 0x1.6e142a138f825p-157},
    {{0x1.952c77030ad4ap-49, 0x1.ac981465ddc6cp-103}, 0x1.588b72e53bc5fp-165},
    {{-0x1.2f49b46814157p-57, -0x1.2650f61dbdcb4p-112}, 0x1.69502917cbf3bp-166},
    {{0x1.71b8ef6dcf572p-66, -0x1.d043ae40c4647p-120}, 0x1.486121e81d5fep-176},
    {{-0x1.761b41316381ap-75, 0x1.3423c7d91404fp-130}, 0x1.e6135bfc1194ap-185},
    {{0x1.3f3ccdd165fa9p-84, -0x1.58ddadf344487p-139}, 0x1.e8ed8001ad67ep-193},
    {{-0x1.d1ab1c2dccea3p-94, -0x1.054d0c78aea14p-149}, 0x1.196bf16c33a56p-203},
    {{0x1.259f98b4358adp-103, 0x1.eaf8c39dd9bc5p-157}, 0x1.6e29990a26fb7p-211},
    {{-0x1.434d2e783f5bcp-113, -0x1.0b87b91be9affp-167}, 0x1.c89db1796db75p-224},
    {{0x1.3981254dd0d52p-123, -0x1.2b1f4c8015a2fp-177}, 0x1.d82af23edb6dbp-231},
    {{-0x1.0dc59c716d91fp-133, -0x1.419e3fad3f031p-188}, 0x1.d9d7ed1981ffcp-244},
    {{0x1.9ec8d1c94e85bp-144, -0x1.670e9d4784ec6p-201}, 0x1.79fe5954939a3p-255},
    {{-0x1.1e99449a4bacep-154, 0x1.fefbb89514b3cp-210}, 0x1.53433f743a2d9p-264}};

__device__ __constant__ RealDisk106 kCosineCoefficients[20] = {
    {{0x1p+0, 0x0p+0}, 0x0p+0},
    {{-0x1p-1, 0x0p+0}, 0x0p+0},
    {{0x1.5555555555555p-5, 0x1.5555555555555p-59}, 0x1.5555555555556p-113},
    {{-0x1.6c16c16c16c17p-10, 0x1.f49f49f49f49fp-65}, 0x1.27d27d27d27d3p-119},
    {{0x1.a01a01a01a01ap-16, 0x1.a01a01a01a01ap-76}, 0x1.a01a01a01a01bp-136},
    {{-0x1.27e4fb7789f5cp-22, -0x1.cbbc05b4fa99ap-76}, 0x1.c6d278883e8f5p-132},
    {{0x1.1eed8eff8d898p-29, -0x1.2aec959e14c06p-83}, 0x1.2fb0073dd2d9fp-139},
    {{-0x1.93974a8c07c9dp-37, -0x1.05d6f8a2efd1fp-92}, 0x1.3aa3346236a5ep-147},
    {{0x1.ae7f3e733b81fp-45, 0x1.1d8656b0ee8cbp-101}, 0x1.6e142a138f825p-161},
    {{-0x1.6827863b97d97p-53, -0x1.eec01221a8b0bp-107}, 0x1.568798662118bp-161},
    {{0x1.e542ba4020225p-62, 0x1.ea72b4afe3c2fp-120}, 0x1.44020dfd65c8dp-174},
    {{-0x1.0ce396db7f853p-70, 0x1.aebcdbd20331cp-124}, 0x1.38a88578b4d75p-178},
    {{0x1.f2cf01972f578p-80, -0x1.9ada5fcc1ab14p-135}, 0x1.440ce7fd610dcp-189},
    {{-0x1.88e85fc6a4e5ap-89, 0x1.71c37ebd16540p-143}, 0x1.494676265a364p-197},
    {{0x1.0a18a2635085dp-98, 0x1.b9e2e28e1aa54p-153}, 0x1.a8549a9d99586p-207},
    {{-0x1.3932c5047d60ep-108, -0x1.832b7b530a627p-162}, 0x1.5d2c61f6d124dp-218},
    {{0x1.434d2e783f5bcp-118, 0x1.0b87b91be9affp-172}, 0x1.c89db1796db75p-229},
    {{-0x1.2710231c0fd7ap-128, -0x1.3f8a2b4af9d6bp-184}, 0x1.c32215a9f317ep-238},
    {{0x1.df983290c2ca9p-139, 0x1.5835c6895393bp-194}, 0x1.0578f45b1aaafp-249},
    {{-0x1.5d4acb9c0c3abp-149, 0x1.6ec2c8f5b13b2p-205}, 0x1.e2860aaa59188p-259}};

__device__ __forceinline__ ComplexDisk106 sin_cos_reduced(RealDisk106 x) {
  const double magnitude = __dadd_ru(abs_upper(x.center), x.radius);
  if (!isfinite(magnitude) || magnitude > 0.786) {
    return {{0.0, 0.0}, {0.0, 0.0}, INFINITY};
  }
  const RealDisk106 square = real_mul(x, x);
  RealDisk106 sine = kSineCoefficients[19];
  RealDisk106 cosine = kCosineCoefficients[19];
#pragma unroll
  for (int index = 18; index >= 0; --index) {
    sine = real_add(real_mul(sine, square), kSineCoefficients[index]);
    cosine = real_add(real_mul(cosine, square), kCosineCoefficients[index]);
  }
  sine = real_mul(x, sine);
  // At |x| <= 0.786 the first omitted terms are below this common bound.
  sine.radius = __dadd_ru(sine.radius, 1.0e-50);
  cosine.radius = __dadd_ru(cosine.radius, 1.0e-50);
  return {cosine.center, sine.center,
          norm_upper({cosine.radius, 0.0}, {sine.radius, 0.0})};
}

__device__ __forceinline__ RealDisk106 exp_disk(RealDisk106 x) {
  constexpr RealDisk106 ln2 = {
      {0x1.62e42fefa39efp-1, 0x1.abc9e3b39803fp-56},
      0x1.7b57a079a1934p-111};
  const double approximate = __dadd_rn(x.center.hi, x.center.lo);
  const int exponent = __double2int_rn(approximate * 0x1.71547652b82fep+0);
  const RealDisk106 multiple = real_mul(
      ln2, {{static_cast<double>(exponent), 0.0}, 0.0});
  const RealDisk106 residual = real_add(x, real_negate(multiple));
  const double magnitude =
      __dadd_ru(abs_upper(residual.center), residual.radius);
  if (!isfinite(magnitude) || magnitude > 0.36) {
    return {{0.0, 0.0}, INFINITY};
  }
  RealDisk106 value = kExpCoefficients[24];
#pragma unroll
  for (int degree = 23; degree >= 0; --degree) {
    value = real_add(real_mul(value, residual), kExpCoefficients[degree]);
  }
  // exp(.36)*.36^25/25! < 7.47e-37.
  value.radius = __dadd_ru(value.radius, 8.0e-37);
  value.center.hi = ldexp(value.center.hi, exponent);
  value.center.lo = ldexp(value.center.lo, exponent);
  value.radius = ldexp(value.radius, exponent);
  value.radius = __dadd_ru(value.radius, kDDFloor);
  return value;
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
  const std::uint64_t overflow = result.limb1 < middle_product ? 1U : 0U;
  carry = __umul64hi(value.limb1, multiplier) + overflow;
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

__device__ __forceinline__ UInt192 negate_192(UInt192 x) {
  return subtract_192(UInt192{}, x);
}

__device__ __forceinline__ RealDisk106 fraction_from_192(UInt192 value) {
  RealDisk106 result{{0.0, 0.0}, 0.0};
  const double terms[] = {
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb2 >> 32U)), -32),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb2)), -64),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb1 >> 32U)), -96),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb1)), -128),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb0 >> 32U)), -160),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb0)), -192)};
#pragma unroll
  for (int index = 0; index < 6; ++index) {
    result = real_add(result, {{terms[index], 0.0}, 0.0});
  }
  return result;
}

__device__ __forceinline__ ComplexDisk106 fixed_phase(UInt192 product,
                                                       double phase_error) {
  constexpr RealDisk106 two_pi = {
      {0x1.921fb54442d18p+2, 0x1.1a62633145c07p-52},
      0x1.f1976b7ed8fbcp-108};
  const unsigned octant = static_cast<unsigned>(product.limb2 >> 61U);
  product.limb2 &= (1ULL << 61U) - 1ULL;
  if ((octant & 1U) != 0U) {
    product = subtract_192({0U, 0U, 1ULL << 61U}, product);
  }
  const RealDisk106 angle = real_mul(fraction_from_192(product), two_pi);
  const ComplexDisk106 base = sin_cos_reduced(angle);
  DoubleDouble cosine{};
  DoubleDouble sine{};
  switch (octant) {
    case 0U: cosine = base.real; sine = base.imaginary; break;
    case 1U: cosine = base.imaginary; sine = base.real; break;
    case 2U: cosine = negate(base.imaginary); sine = base.real; break;
    case 3U: cosine = negate(base.real); sine = base.imaginary; break;
    case 4U: cosine = negate(base.real); sine = negate(base.imaginary); break;
    case 5U: cosine = negate(base.imaginary); sine = negate(base.real); break;
    case 6U: cosine = base.imaginary; sine = negate(base.real); break;
    default: cosine = base.real; sine = negate(base.imaginary); break;
  }
  return {cosine, sine, __dadd_ru(base.radius, phase_error)};
}

__device__ __forceinline__ ComplexDisk106 anchor_step_phase(
    pw::FixedTurn192 anchor, pw::FixedTurn192 step, int grid_offset,
    double anchor_error, double step_error) {
  const std::uint64_t magnitude = static_cast<std::uint64_t>(
      grid_offset < 0 ? -static_cast<std::int64_t>(grid_offset)
                      : static_cast<std::int64_t>(grid_offset));
  UInt192 displacement = multiply_low_192(step, magnitude);
  if (grid_offset < 0) displacement = negate_192(displacement);
  const UInt192 product = add_192(
      {anchor.limb0, anchor.limb1, anchor.limb2}, displacement);
  const double error = __dadd_ru(
      anchor_error, __dmul_ru(static_cast<double>(magnitude), step_error));
  return fixed_phase(product, error);
}

__device__ __forceinline__ RealDisk106 coefficient_coordinate(
    const ComplexDisk106& coefficient, bool imaginary) {
  return {imaginary ? coefficient.imaginary : coefficient.real,
          coefficient.radius};
}

__global__ void synthesize(const pg2::Record* records, BatchView output) {
  const std::uint32_t record_index = blockIdx.y;
  if (record_index >= output.record_count) return;
  __shared__ pg2::Record record;
  static_assert(sizeof(record) % sizeof(std::uint64_t) == 0U);
  auto* target = reinterpret_cast<std::uint64_t*>(&record);
  const auto* source = reinterpret_cast<const std::uint64_t*>(
      records + record_index);
  for (std::uint32_t word = threadIdx.x;
       word < sizeof(record) / sizeof(std::uint64_t); word += blockDim.x) {
    target[word] = source[word];
  }
  __syncthreads();

  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= pw::kBucketCount) return;
  const int grid_offset = static_cast<int>(index) -
                          static_cast<int>(pw::kBucketCount / 2U);
  // Exactly representable dyadic source coordinate.
  const RealDisk106 u{{static_cast<double>(grid_offset) * (21.0 / 128.0),
                       0.0},
                      0.0};

  RealDisk106 real_log = coefficient_coordinate(record.coefficients[5], false);
#pragma unroll
  for (int degree = 4; degree >= 0; --degree) {
    real_log = real_add(
        real_mul(real_log, u),
        coefficient_coordinate(record.coefficients[degree], false));
  }
  // u is exact. DD multiplication retains its product residual, and the
  // fixed disk is an outward enclosure of the exact rational 1/26912.
  const RealDisk106 gaussian = real_mul(
      real_mul(u, u), pg2::kInverseGaussianDenominator);
  real_log = real_add(real_log, real_negate(gaussian));
  real_log.radius =
      __dadd_ru(real_log.radius, record.logarithm_remainder);
  const RealDisk106 amplitude = exp_disk(real_log);

  RealDisk106 residual_phase =
      coefficient_coordinate(record.coefficients[5], true);
#pragma unroll
  for (int degree = 4; degree >= 2; --degree) {
    residual_phase = real_add(
        real_mul(residual_phase, u),
        coefficient_coordinate(record.coefficients[degree], true));
  }
  residual_phase = real_mul(real_mul(residual_phase, u), u);
  residual_phase.radius =
      __dadd_ru(residual_phase.radius, record.logarithm_remainder);
  const ComplexDisk106 phase = anchor_step_phase(
      record.phase_anchor, record.phase_grid_step, grid_offset,
      record.phase_anchor_error, record.phase_grid_step_error);
  const ComplexDisk106 residual = sin_cos_reduced(residual_phase);
  output.rows[static_cast<std::uint64_t>(record_index) * output.row_stride +
              index] = complex_scale(complex_mul(phase, residual), amplitude);
}

__device__ __forceinline__ std::uint64_t mix64(std::uint64_t value) {
  value ^= value >> 30U;
  value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27U;
  value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

__global__ void summarize(BatchView input, RowSummary* summaries) {
  const std::uint32_t record = blockIdx.x;
  const std::uint32_t lane = threadIdx.x;
  std::uint64_t digest = 0U;
  std::uint64_t invalid = 0U;
  double maximum_radius = 0.0;
  for (std::uint32_t index = lane; index < pw::kBucketCount;
       index += blockDim.x) {
    const ComplexDisk106 value =
        input.rows[static_cast<std::uint64_t>(record) * input.row_stride +
                   index];
    if (!isfinite(value.real.hi) || !isfinite(value.real.lo) ||
        !isfinite(value.imaginary.hi) ||
        !isfinite(value.imaginary.lo) || !isfinite(value.radius) ||
        value.radius < 0.0) {
      ++invalid;
    }
    maximum_radius = fmax(maximum_radius, value.radius);
    const std::uint64_t key = mix64(static_cast<std::uint64_t>(index) << 32U);
    digest ^= mix64(static_cast<std::uint64_t>(
                        __double_as_longlong(value.real.hi)) ^ key);
    digest ^= mix64(static_cast<std::uint64_t>(
                        __double_as_longlong(value.real.lo)) ^
                    (key + 0x9e3779b97f4a7c15ULL));
    digest ^= mix64(static_cast<std::uint64_t>(
                        __double_as_longlong(value.imaginary.hi)) ^
                    (key + 0x3c6ef372fe94f82aULL));
    digest ^= mix64(static_cast<std::uint64_t>(
                        __double_as_longlong(value.imaginary.lo)) ^
                    (key + 0xdaa66d2c7ddef73fULL));
    digest ^= mix64(static_cast<std::uint64_t>(
                        __double_as_longlong(value.radius)) ^
                    (key + 0x78dde6e5fd29f054ULL));
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

void launch_synthesize(const pg2::Record* authenticated_records,
                       BatchView output, cudaStream_t stream) {
  constexpr std::uint32_t threads = 256U;
  const dim3 blocks((pw::kBucketCount + threads - 1U) / threads,
                    output.record_count);
  synthesize<<<blocks, threads, 0U, stream>>>(authenticated_records, output);
}

void launch_summarize(BatchView input, RowSummary* summaries,
                      cudaStream_t stream) {
  summarize<<<input.record_count, 256U, 0U, stream>>>(input, summaries);
}

}  // namespace sparkinterval::tg::platt_gamma_dd_gpu

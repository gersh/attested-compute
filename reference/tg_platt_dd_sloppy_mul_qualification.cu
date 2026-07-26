// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only comparison of the full-expansion PT21 complex-disk
// root multiplication with a bounded "sloppy DD" alternative.  This
// executable emits no source, production, or refinement certificate.

#include <boost/multiprecision/cpp_int.hpp>

#include "sparkinterval/sha256.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

namespace {

using boost::multiprecision::cpp_int;
using boost::multiprecision::cpp_rational;

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

#if !defined(SPARKINTERVAL_CUDA_FTZ_DISABLED) || \
    SPARKINTERVAL_CUDA_FTZ_DISABLED != 1
#error "qualification must be compiled with --ftz=false and SPARKINTERVAL_CUDA_FTZ_DISABLED=1"
#endif

constexpr std::string_view kBuildProfile =
    SPARKINTERVAL_CMAKE_BUILD_CONFIG;
#ifdef NDEBUG
constexpr bool kNdebugDefined = true;
#else
constexpr bool kNdebugDefined = false;
#endif
constexpr bool kReleasePerformanceBuild =
    kNdebugDefined && kBuildProfile == "Release";

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                 \
                               cudaGetErrorString(status_));                  \
    }                                                                        \
  } while (0)

struct DD {
  double hi;
  double lo;
};

struct DDDisk {
  DD real;
  DD imaginary;
  double radius;
};

struct CenterResult {
  DD value;
  double error;
  std::uint32_t status;
  std::uint32_t reserved_zero;
};

struct TwoSumResult {
  double sum;
  double residual;
};

struct CaseInput {
  DDDisk left;
  DDDisk right;
  double right_center_norm_bound;
  std::uint32_t expected_status_mask;
  std::uint32_t expectation;
};

struct ScalarMulCase {
  DD left;
  DD right;
};

struct DiskMulResult {
  DDDisk output;
  double center_error_bound;
  double left_center_norm_bound;
  double right_center_norm_bound;
  std::uint32_t status;
  std::uint32_t reserved_zero;
};

static_assert(sizeof(DD) == 16U);
static_assert(sizeof(DDDisk) == 40U);
static_assert(sizeof(CaseInput) == 96U);
static_assert(sizeof(ScalarMulCase) == 32U);
static_assert(sizeof(DiskMulResult) == 72U);
static_assert(sizeof(CenterResult) == 32U);
static_assert(sizeof(double) == sizeof(std::uint64_t));
static_assert(std::numeric_limits<double>::is_iec559);
static_assert(std::is_standard_layout_v<DD>);
static_assert(std::is_standard_layout_v<DDDisk>);
static_assert(std::is_standard_layout_v<CaseInput>);
static_assert(std::is_standard_layout_v<ScalarMulCase>);
static_assert(std::is_trivially_copyable_v<DD>);
static_assert(std::is_trivially_copyable_v<DDDisk>);
static_assert(std::is_trivially_copyable_v<CaseInput>);
static_assert(std::is_trivially_copyable_v<ScalarMulCase>);
static_assert(offsetof(CaseInput, left) == 0U);
static_assert(offsetof(CaseInput, right) == 40U);
static_assert(offsetof(CaseInput, right_center_norm_bound) == 80U);
static_assert(offsetof(CaseInput, expected_status_mask) == 88U);
static_assert(offsetof(CaseInput, expectation) == 92U);

constexpr std::uint32_t kStatusOk = 0U;
constexpr std::uint32_t kStatusInvalidInput = 1U << 0U;
constexpr std::uint32_t kStatusNonfiniteOutput = 1U << 1U;
constexpr std::uint32_t kStatusNegativeBound = 1U << 2U;
constexpr std::uint32_t kStatusNonfiniteIntermediate = 1U << 3U;
constexpr std::uint32_t kExpectationOrdinary = 0U;
constexpr std::uint32_t kExpectationKernelReject = 1U;
constexpr std::uint32_t kExpectationExactCheckerReject = 2U;
constexpr double kDDFloor = 0x0.0000000000001p-1022;
constexpr double kFastTwoSumFloors = 6.0 * kDDFloor;
constexpr double kRnRelativeError = 0x1.0000000000001p-53;
constexpr DD kNearTightAddA{-0x1p+214, -0x1p+214};
constexpr DD kNearTightAddB{0x1.8p+563, -0x1p+267};

__device__ __forceinline__ TwoSumResult two_sum(double a, double b) {
  const double sum = __dadd_rn(a, b);
  const double virtual_b = __dsub_rn(sum, a);
  const double residual = __dadd_rn(
      __dsub_rn(a, __dsub_rn(sum, virtual_b)),
      __dsub_rn(b, virtual_b));
  return {sum, residual};
}

__device__ __forceinline__ TwoSumResult two_product(double a, double b) {
  const double product = __dmul_rn(a, b);
  return {product, fma(a, b, -product)};
}

__device__ __forceinline__ double error_add(double bound, double value) {
  return __dadd_ru(bound, fabs(value));
}

__device__ __forceinline__ std::uint32_t finite_status(double value) {
  return isfinite(value) ? kStatusOk : kStatusNonfiniteIntermediate;
}

__device__ __forceinline__ std::uint32_t finite_status(
    TwoSumResult value) {
  return finite_status(value.sum) | finite_status(value.residual);
}

// Full expansion helper copied semantically from the qualification target's
// current PT21 transform.  It is deliberately local to this executable.
__device__ __forceinline__ CenterResult full_add_center(DD a, DD b) {
  const TwoSumResult high = two_sum(a.hi, b.hi);
  std::uint32_t status = finite_status(high);
  double low = 0.0;
  double error = kDDFloor;
  const double terms[] = {high.residual, a.lo, b.lo};
#pragma unroll
  for (int index = 0; index < 3; ++index) {
    const TwoSumResult next = two_sum(low, terms[index]);
    status |= finite_status(next);
    low = next.sum;
    error = error_add(error, next.residual);
    status |= finite_status(error);
    error = __dadd_ru(error, kDDFloor);
    status |= finite_status(error);
  }
  const TwoSumResult normalized = two_sum(high.sum, low);
  status |= finite_status(normalized);
  error = __dadd_ru(error, kDDFloor);
  status |= finite_status(error);
  return {{normalized.sum, normalized.residual}, error, status, 0U};
}

__device__ __forceinline__ CenterResult full_mul_center(DD a, DD b) {
  const TwoSumResult products[] = {
      two_product(a.hi, b.hi), two_product(a.hi, b.lo),
      two_product(a.lo, b.hi), two_product(a.lo, b.lo)};
  std::uint32_t status = kStatusOk;
#pragma unroll
  for (int index = 0; index < 4; ++index) {
    status |= finite_status(products[index]);
  }
  double low = 0.0;
  double error = __dmul_ru(4.0, kDDFloor);
  status |= finite_status(error);
  const double terms[] = {
      products[0].residual,
      products[1].sum,
      products[1].residual,
      products[2].sum,
      products[2].residual,
      products[3].sum,
      products[3].residual,
  };
#pragma unroll
  for (int index = 0; index < 7; ++index) {
    const TwoSumResult next = two_sum(low, terms[index]);
    status |= finite_status(next);
    low = next.sum;
    error = error_add(error, next.residual);
    status |= finite_status(error);
    error = __dadd_ru(error, kDDFloor);
    status |= finite_status(error);
  }
  const TwoSumResult normalized = two_sum(products[0].sum, low);
  status |= finite_status(normalized);
  error = __dadd_ru(error, kDDFloor);
  status |= finite_status(error);
  return {{normalized.sum, normalized.residual}, error, status, 0U};
}

__device__ __forceinline__ double rn_error(double result) {
  return __dadd_ru(
      __dmul_ru(fabs(result), kRnRelativeError), kDDFloor);
}

// This is the already-qualified accumulator formula, copied into an isolated
// benchmark.  No non-overlap property of either DD input is assumed.
__device__ __noinline__ CenterResult fast_add_center(DD a, DD b) {
  const TwoSumResult high = two_sum(a.hi, b.hi);
  std::uint32_t status = finite_status(high);
  const double low_parts = __dadd_rn(a.lo, b.lo);
  status |= finite_status(low_parts);
  const double low = __dadd_rn(high.residual, low_parts);
  status |= finite_status(low);
  const TwoSumResult normalized = two_sum(high.sum, low);
  status |= finite_status(normalized);
  double error = rn_error(low_parts);
  status |= finite_status(error);
  error = __dadd_ru(error, rn_error(low));
  status |= finite_status(error);
  error = __dadd_ru(error, 2.0 * kFastTwoSumFloors);
  status |= finite_status(error);
  return {{normalized.sum, normalized.residual}, error, status, 0U};
}

__device__ __noinline__ CenterResult fast_mul_center(DD a, DD b) {
  const TwoSumResult leading = two_product(a.hi, b.hi);
  std::uint32_t status = finite_status(leading);
  const double cross0 = __dmul_rn(a.hi, b.lo);
  status |= finite_status(cross0);
  const double cross1 = __dmul_rn(a.lo, b.hi);
  status |= finite_status(cross1);
  const double cross = __dadd_rn(cross0, cross1);
  status |= finite_status(cross);
  const double low = __dadd_rn(leading.residual, cross);
  status |= finite_status(low);
  const TwoSumResult normalized = two_sum(leading.sum, low);
  status |= finite_status(normalized);
  double error = kDDFloor;
  error = __dadd_ru(error, rn_error(cross0));
  status |= finite_status(error);
  error = __dadd_ru(error, rn_error(cross1));
  status |= finite_status(error);
  error = __dadd_ru(error, rn_error(cross));
  status |= finite_status(error);
  error = __dadd_ru(error, rn_error(low));
  status |= finite_status(error);
  error = __dadd_ru(error, __dmul_ru(fabs(a.lo), fabs(b.lo)));
  status |= finite_status(error);
  error = __dadd_ru(error, kFastTwoSumFloors);
  status |= finite_status(error);
  return {{normalized.sum, normalized.residual}, error, status, 0U};
}

__device__ __forceinline__ double dd_abs_upper(DD value) {
  return __dadd_ru(fabs(value.hi), fabs(value.lo));
}

__device__ __forceinline__ double center_l1_upper(DD real, DD imaginary) {
  return __dadd_ru(dd_abs_upper(real), dd_abs_upper(imaginary));
}

__device__ __forceinline__ bool finite_dd(DD value) {
  return isfinite(value.hi) && isfinite(value.lo);
}

__device__ __forceinline__ bool valid_input(const CaseInput& input) {
  return finite_dd(input.left.real) &&
         finite_dd(input.left.imaginary) &&
         finite_dd(input.right.real) &&
         finite_dd(input.right.imaginary) &&
         isfinite(input.left.radius) && input.left.radius >= 0.0 &&
         isfinite(input.right.radius) && input.right.radius >= 0.0 &&
         isfinite(input.right_center_norm_bound) &&
         input.right_center_norm_bound >= 0.0;
}

__device__ __forceinline__ bool finite_result(
    const DiskMulResult& result) {
  return finite_dd(result.output.real) &&
         finite_dd(result.output.imaginary) &&
         isfinite(result.output.radius) &&
         isfinite(result.center_error_bound) &&
         isfinite(result.left_center_norm_bound) &&
         isfinite(result.right_center_norm_bound);
}

template <bool Fast>
__device__ __forceinline__ DiskMulResult disk_root_mul(
    const CaseInput& input) {
  if (!valid_input(input)) {
    return {{{0.0, 0.0}, {0.0, 0.0}, 0.0},
            0.0, 0.0, 0.0, kStatusInvalidInput, 0U};
  }

  const CenterResult rr =
      Fast ? fast_mul_center(input.left.real, input.right.real)
           : full_mul_center(input.left.real, input.right.real);
  const CenterResult ii =
      Fast ? fast_mul_center(input.left.imaginary, input.right.imaginary)
           : full_mul_center(input.left.imaginary, input.right.imaginary);
  const DD negative_ii{-ii.value.hi, -ii.value.lo};
  const CenterResult real =
      Fast ? fast_add_center(rr.value, negative_ii)
           : full_add_center(rr.value, negative_ii);
  const double real_error =
      __dadd_ru(__dadd_ru(rr.error, ii.error), real.error);
  std::uint32_t status = rr.status | ii.status | real.status;
  status |= finite_status(real_error);

  const CenterResult ri =
      Fast ? fast_mul_center(input.left.real, input.right.imaginary)
           : full_mul_center(input.left.real, input.right.imaginary);
  const CenterResult ir =
      Fast ? fast_mul_center(input.left.imaginary, input.right.real)
           : full_mul_center(input.left.imaginary, input.right.real);
  const CenterResult imaginary =
      Fast ? fast_add_center(ri.value, ir.value)
           : full_add_center(ri.value, ir.value);
  status |= ri.status | ir.status | imaginary.status;
  const double imaginary_error =
      __dadd_ru(__dadd_ru(ri.error, ir.error), imaginary.error);
  status |= finite_status(imaginary_error);
  const double local_error =
      __dadd_ru(real_error, imaginary_error);
  status |= finite_status(local_error);
  const double left_norm =
      center_l1_upper(input.left.real, input.left.imaginary);
  status |= finite_status(left_norm);
  double radius = __dadd_ru(
      local_error, __dmul_ru(left_norm, input.right.radius));
  status |= finite_status(radius);
  radius = __dadd_ru(
      radius,
      __dmul_ru(input.right_center_norm_bound, input.left.radius));
  status |= finite_status(radius);
  radius = __dadd_ru(
      radius, __dmul_ru(input.left.radius, input.right.radius));
  status |= finite_status(radius);

  DiskMulResult result{
      {real.value, imaginary.value, radius},
      local_error,
      left_norm,
      input.right_center_norm_bound,
      status,
      0U,
  };
  if (!finite_result(result)) {
    result.status |= kStatusNonfiniteOutput;
  }
  if (result.output.radius < 0.0 ||
      result.center_error_bound < 0.0 ||
      result.left_center_norm_bound < 0.0 ||
      result.right_center_norm_bound < 0.0) {
    result.status |= kStatusNegativeBound;
  }
  return result;
}

__global__ void qualify_kernel(const CaseInput* inputs,
                               DiskMulResult* full,
                               DiskMulResult* fast,
                               std::uint32_t count) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < count; index += blockDim.x * gridDim.x) {
    full[index] = disk_root_mul<false>(inputs[index]);
    fast[index] = disk_root_mul<true>(inputs[index]);
  }
}

template <bool Fast>
__global__ void benchmark_kernel(const CaseInput* inputs,
                                 DDDisk* outputs,
                                 std::uint32_t* statuses,
                                 std::uint32_t count,
                                 std::uint32_t corpus_mask) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < count; index += blockDim.x * gridDim.x) {
    const DiskMulResult result =
        disk_root_mul<Fast>(inputs[index & corpus_mask]);
    outputs[index] = result.output;
    statuses[index] = result.status;
  }
}

__global__ void near_tight_fast_add_kernel(CenterResult* output) {
  *output = fast_add_center(kNearTightAddA, kNearTightAddB);
}

__global__ void direct_fast_mul_kernel(const ScalarMulCase* inputs,
                                       CenterResult* outputs,
                                       std::uint32_t count) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < count; index += blockDim.x * gridDim.x) {
    outputs[index] =
        fast_mul_center(inputs[index].left, inputs[index].right);
  }
}

struct ExactDisk {
  cpp_rational re;
  cpp_rational im;
  cpp_rational radius;
};

cpp_rational pow2(std::uint32_t exponent) {
  return cpp_rational(cpp_int(1) << exponent);
}

std::optional<cpp_rational> decode_finite(double value) {
  const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
  const bool negative = (bits >> 63U) != 0U;
  const std::uint32_t raw_exponent =
      static_cast<std::uint32_t>((bits >> 52U) & 0x7ffU);
  const std::uint64_t fraction = bits & ((1ULL << 52U) - 1U);
  if (raw_exponent == 0x7ffU) return std::nullopt;
  if (raw_exponent == 0U && fraction == 0U) return cpp_rational(0);
  cpp_int significand;
  std::int32_t exponent;
  if (raw_exponent == 0U) {
    significand = fraction;
    exponent = -1074;
  } else {
    significand = (cpp_int(1) << 52U) + fraction;
    exponent = static_cast<std::int32_t>(raw_exponent) - 1023 - 52;
  }
  cpp_rational result(significand);
  if (exponent >= 0) {
    result *= pow2(static_cast<std::uint32_t>(exponent));
  } else {
    result /= pow2(static_cast<std::uint32_t>(-exponent));
  }
  return negative ? -result : result;
}

cpp_rational decode_or_throw(double value) {
  const std::optional<cpp_rational> decoded = decode_finite(value);
  if (!decoded.has_value()) {
    throw std::runtime_error("exact checker received nonfinite binary64");
  }
  return *decoded;
}

cpp_rational decode_dd(DD value) {
  return decode_or_throw(value.hi) + decode_or_throw(value.lo);
}

ExactDisk decode_disk(DDDisk disk) {
  return {
      decode_dd(disk.real),
      decode_dd(disk.imaginary),
      decode_or_throw(disk.radius),
  };
}

bool norm_bound_valid(const ExactDisk& disk,
                      const cpp_rational& bound) {
  return bound >= 0 &&
         disk.re * disk.re + disk.im * disk.im <= bound * bound;
}

struct ExactCheck {
  bool decoded = false;
  bool center_bound = false;
  bool left_norm_bound = false;
  bool right_norm_bound = false;
  bool radius_bound = false;

  bool accepted() const {
    return decoded && center_bound && left_norm_bound &&
           right_norm_bound && radius_bound;
  }
};

ExactCheck exact_check(const CaseInput& raw_input,
                       const DiskMulResult& raw_result) {
  ExactCheck check;
  if (raw_result.status != kStatusOk) return check;
  try {
    const ExactDisk left = decode_disk(raw_input.left);
    const ExactDisk right = decode_disk(raw_input.right);
    const ExactDisk output = decode_disk(raw_result.output);
    const cpp_rational center_error =
        decode_or_throw(raw_result.center_error_bound);
    const cpp_rational left_norm =
        decode_or_throw(raw_result.left_center_norm_bound);
    const cpp_rational right_norm =
        decode_or_throw(raw_result.right_center_norm_bound);
    check.decoded =
        left.radius >= 0 && right.radius >= 0 &&
        output.radius >= 0 && center_error >= 0;
    if (!check.decoded) return check;
    const cpp_rational exact_re =
        left.re * right.re - left.im * right.im;
    const cpp_rational exact_im =
        left.re * right.im + left.im * right.re;
    const cpp_rational error_re = exact_re - output.re;
    const cpp_rational error_im = exact_im - output.im;
    check.center_bound =
        error_re * error_re + error_im * error_im <=
        center_error * center_error;
    check.left_norm_bound = norm_bound_valid(left, left_norm);
    check.right_norm_bound = norm_bound_valid(right, right_norm);
    const cpp_rational required =
        center_error + left_norm * right.radius +
        right_norm * left.radius + left.radius * right.radius;
    check.radius_bound = required <= output.radius;
    return check;
  } catch (const std::exception&) {
    return check;
  }
}

struct NearTightAddCheck {
  bool status_ok = false;
  bool reserved_zero = false;
  bool exact_bound = false;
  bool expected_result_bits = false;
  bool expected_error_bits = false;
  bool expected_exact_error = false;

  bool accepted() const {
    return status_ok && reserved_zero && exact_bound && expected_result_bits &&
           expected_error_bits && expected_exact_error;
  }
};

NearTightAddCheck check_near_tight_add(const CenterResult& result) {
  NearTightAddCheck check;
  check.status_ok = result.status == kStatusOk;
  check.reserved_zero = result.reserved_zero == 0U;
  if (!check.status_ok) return check;
  try {
    const cpp_rational exact =
        decode_dd(kNearTightAddA) + decode_dd(kNearTightAddB);
    const cpp_rational approximate = decode_dd(result.value);
    const cpp_rational signed_error = exact - approximate;
    const cpp_rational absolute_error =
        signed_error < 0 ? -signed_error : signed_error;
    const cpp_rational error_bound = decode_or_throw(result.error);
    check.exact_bound =
        error_bound >= 0 && absolute_error <= error_bound;
    check.expected_result_bits =
        std::bit_cast<std::uint64_t>(result.value.hi) ==
            std::bit_cast<std::uint64_t>(0x1.8p+563) &&
        std::bit_cast<std::uint64_t>(result.value.lo) ==
            std::bit_cast<std::uint64_t>(-0x1p+267);
    check.expected_error_bits =
        std::bit_cast<std::uint64_t>(result.error) ==
        std::bit_cast<std::uint64_t>(0x1.0000000000003p+215);
    check.expected_exact_error =
        absolute_error == decode_or_throw(0x1p+215);
    return check;
  } catch (const std::exception&) {
    return check;
  }
}

bool check_direct_fast_mul(const ScalarMulCase& input,
                           const CenterResult& result) {
  if (result.status != kStatusOk || result.reserved_zero != 0U) {
    return false;
  }
  try {
    const cpp_rational exact =
        decode_dd(input.left) * decode_dd(input.right);
    const cpp_rational approximate = decode_dd(result.value);
    const cpp_rational signed_error = exact - approximate;
    const cpp_rational absolute_error =
        signed_error < 0 ? -signed_error : signed_error;
    const cpp_rational error_bound = decode_or_throw(result.error);
    return error_bound >= 0 && absolute_error <= error_bound;
  } catch (const std::exception&) {
    return false;
  }
}

double host_l1_upper(DD real, DD imaginary) {
  const std::array<double, 4> terms{
      std::fabs(real.hi), std::fabs(real.lo),
      std::fabs(imaginary.hi), std::fabs(imaginary.lo)};
  double result = 0.0;
  for (double term : terms) {
    result += term;
    if (std::isfinite(result)) {
      result = std::nextafter(
          result, std::numeric_limits<double>::infinity());
    }
  }
  return result;
}

struct Corpus {
  std::vector<CaseInput> inputs;
  std::vector<std::string> labels;
  std::uint32_t pt21_like_begin = 0U;
};

void add_case(Corpus* corpus, std::string label,
              DDDisk left, DDDisk right,
              std::uint32_t expected_status_mask = kStatusOk,
              std::uint32_t expectation = kExpectationOrdinary,
              std::optional<double> norm_override = std::nullopt) {
  const double norm = host_l1_upper(right.real, right.imaginary);
  corpus->inputs.push_back(
      {left, right, norm_override.value_or(norm),
       expected_status_mask, expectation});
  corpus->labels.push_back(std::move(label));
}

Corpus build_corpus() {
  Corpus corpus;
  constexpr double denorm = std::numeric_limits<double>::denorm_min();
  constexpr double min_normal = std::numeric_limits<double>::min();
  constexpr double max_finite = std::numeric_limits<double>::max();
  const std::array<double, 8> edge{
      0.0, -0.0, denorm, -denorm,
      std::nextafter(min_normal, 0.0), min_normal,
      1.0, -1.0};
  for (std::size_t index = 0U; index < edge.size(); ++index) {
    const double a = edge[index];
    const double b = edge[(3U * index + 1U) % edge.size()];
    add_case(
        &corpus, "edge-" + std::to_string(index),
        {{a, -b}, {b, a}, std::fabs(a) * 0x1p-80 + denorm},
        {{b, a}, {-a, b}, std::fabs(b) * 0x1p-80 + denorm});
  }
  add_case(
      &corpus, "overlapping-limbs",
      {{1.0, 1.0}, {-1.0, -0.75}, 0x1p-80},
      {{0.5, -0.75}, {1.0, 1.0}, 0x1p-90});
  add_case(
      &corpus, "severe-cancellation",
      {{0x1.0000000000001p+400, -0x1p+348},
       {0x1.0000000000000p+400, 0x1p+347}, 0x1p+250},
      {{0x1.0000000000000p-400, 0x1p-452},
       {0x1.0000000000001p-400, -0x1p-452}, 0x1p-550});
  add_case(
      &corpus, "subnormal-products",
      {{0x1p-800, denorm}, {-0x1p-700, -denorm}, denorm},
      {{0x1p-400, -denorm}, {0x1p-375, denorm}, denorm});
  // Exact-fuzzing found this fast-add shape within three ulps of its outward
  // budget.  Multiplication by (1+i) makes the real-center combine exercise
  // precisely a+b while the independent disk checker remains the oracle.
  add_case(
      &corpus, "near-tight-fast-add-budget",
      {{-0x1p+214, -0x1p+214},
       {-0x1.8p+563, 0x1p+267}, 0x1p+100},
      {{1.0, 0.0}, {1.0, 0.0}, 0x1p-100});
  add_case(
      &corpus, "large-finite",
      {{0x1p+500, -0x1p+446}, {0x1p+480, 0x1p+425}, 0x1p+300},
      {{0x1p+400, 0x1p+346}, {-0x1p+380, 0x1p+325}, 0x1p+200});
  add_case(
      &corpus, "intentional-overflow",
      {{max_finite, 0.0}, {max_finite, 0.0}, 0.0},
      {{2.0, 0.0}, {2.0, 0.0}, 0.0},
      kStatusNonfiniteIntermediate | kStatusNonfiniteOutput,
      kExpectationKernelReject);
  add_case(
      &corpus, "negative-radius",
      {{1.0, 0.0}, {0.0, 0.0}, -denorm},
      {{1.0, 0.0}, {0.0, 0.0}, 0.0},
      kStatusInvalidInput, kExpectationKernelReject);
  add_case(
      &corpus, "nonfinite-input",
      {{std::numeric_limits<double>::infinity(), 0.0},
       {0.0, 0.0}, 0.0},
      {{1.0, 0.0}, {0.0, 0.0}, 0.0},
      kStatusInvalidInput, kExpectationKernelReject);
  add_case(
      &corpus, "undersized-root-norm-contract",
      {{0.75, 0x1p-55}, {-0.5, -0x1p-56}, 0x1p-90},
      {{0.75, -0x1p-55}, {0.5, 0x1p-56}, 0x1p-90},
      kStatusOk, kExpectationExactCheckerReject, 0.0);

  corpus.pt21_like_begin =
      static_cast<std::uint32_t>(corpus.inputs.size());
  constexpr std::array<std::array<double, 2>, 16> root_centers{{
      {{1.0, 0.0}},
      {{0x1.d906bcf328d46p-1, 0x1.87de2a6aea963p-2}},
      {{0x1.6a09e667f3bcdp-1, 0x1.6a09e667f3bcdp-1}},
      {{0x1.87de2a6aea963p-2, 0x1.d906bcf328d46p-1}},
      {{0.0, 1.0}},
      {{-0x1.87de2a6aea963p-2, 0x1.d906bcf328d46p-1}},
      {{-0x1.6a09e667f3bcdp-1, 0x1.6a09e667f3bcdp-1}},
      {{-0x1.d906bcf328d46p-1, 0x1.87de2a6aea963p-2}},
      {{-1.0, 0.0}},
      {{-0x1.d906bcf328d46p-1, -0x1.87de2a6aea963p-2}},
      {{-0x1.6a09e667f3bcdp-1, -0x1.6a09e667f3bcdp-1}},
      {{-0x1.87de2a6aea963p-2, -0x1.d906bcf328d46p-1}},
      {{0.0, -1.0}},
      {{0x1.87de2a6aea963p-2, -0x1.d906bcf328d46p-1}},
      {{0x1.6a09e667f3bcdp-1, -0x1.6a09e667f3bcdp-1}},
      {{0x1.d906bcf328d46p-1, -0x1.87de2a6aea963p-2}},
  }};
  auto splitmix64 = [](std::uint64_t value) {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
  };
  auto deterministic_center = [splitmix64](
                                  std::uint64_t seed, int exponent) {
    const std::uint64_t random = splitmix64(seed);
    const std::uint64_t fraction =
        random & ((1ULL << 52U) - 1U);
    const std::uint64_t biased =
        static_cast<std::uint64_t>(exponent + 1023);
    const std::uint64_t sign = random >> 63U;
    return std::bit_cast<double>(
        (sign << 63U) | (biased << 52U) | fraction);
  };
  constexpr std::uint32_t pt21_cases = 4096U;
  for (std::uint32_t index = 0U; index < pt21_cases; ++index) {
    const std::array<double, 2> root =
        root_centers[index % root_centers.size()];
    const double root_re_hi = root[0];
    const double root_im_hi = root[1];
    const double root_re_lo = std::ldexp(
        root_re_hi, (index & 1U) != 0U ? -55 : -56);
    const double root_im_lo = std::ldexp(
        root_im_hi, (index & 2U) != 0U ? -56 : -55);
    const int exponent =
        static_cast<int>(index % 81U) - 40;
    const double real_hi = deterministic_center(
        0x6a09e667f3bcc909ULL + index, exponent);
    const double imaginary_hi = deterministic_center(
        0xbb67ae8584caa73bULL + index, exponent);
    const double real_lo = std::ldexp(
        (index & 1U) != 0U ? real_hi : -real_hi, -54);
    const double imaginary_lo = std::ldexp(
        (index & 2U) != 0U ? -imaginary_hi : imaginary_hi, -55);
    const double scale =
        std::max(std::fabs(real_hi), std::fabs(imaginary_hi));
    add_case(
        &corpus, "pt21-like-" + std::to_string(index),
        {{real_hi, real_lo}, {imaginary_hi, imaginary_lo},
         std::max(denorm, std::ldexp(scale, -95))},
        {{root_re_hi, root_re_lo}, {root_im_hi, root_im_lo},
         0x1p-106});
  }
  return corpus;
}

std::vector<ScalarMulCase> build_direct_fast_mul_cases() {
  constexpr double denorm = std::numeric_limits<double>::denorm_min();
  constexpr double min_normal = std::numeric_limits<double>::min();
  return {
      {{1.0, 1.0}, {-0.75, 1.0}},
      {kNearTightAddA, kNearTightAddB},
      {{0x1p-800, denorm}, {0x1p-400, -denorm}},
      {{0x1.0000000000001p+400, -0x1p+348},
       {0x1.0000000000000p-400, 0x1p-452}},
      {{0x1p+500, -0x1p+446}, {0x1p+400, 0x1p+346}},
      {{-0.0, denorm}, {min_normal, -denorm}},
      {{0x1.fffffffffffffp-1, -0x1p-54},
       {0x1.6a09e667f3bcdp-1, -0x1p-55}},
      {{-0x1.0000000000001p-500, 0x1p-554},
       {0x1.d906bcf328d46p-1, 0x1p-55}},
  };
}

std::uint32_t parse_u32(std::string_view text, std::uint32_t lower,
                        std::uint32_t upper, const char* name) {
  std::uint32_t value = 0U;
  const auto parsed =
      std::from_chars(text.data(), text.data() + text.size(), value);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != text.data() + text.size() ||
      value < lower || value > upper) {
    throw std::runtime_error(
        std::string(name) + " is outside its accepted range");
  }
  return value;
}

struct Options {
  std::uint32_t repetitions = 11U;
  std::uint32_t benchmark_log2 = 20U;
};

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    constexpr std::string_view repetitions_prefix = "--repetitions=";
    constexpr std::string_view count_prefix = "--benchmark-log2=";
    if (argument.starts_with(repetitions_prefix)) {
      options.repetitions = parse_u32(
          argument.substr(repetitions_prefix.size()), 1U, 101U,
          "repetitions");
    } else if (argument.starts_with(count_prefix)) {
      options.benchmark_log2 = parse_u32(
          argument.substr(count_prefix.size()), 12U, 24U,
          "benchmark-log2");
    } else {
      throw std::runtime_error(
          "usage: tg-platt-dd-sloppy-mul-qualification "
          "[--repetitions=N] [--benchmark-log2=N]");
    }
  }
  return options;
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  return values[values.size() / 2U];
}

double quantile(std::vector<double> values, std::uint32_t numerator,
                std::uint32_t denominator) {
  if (values.empty() || denominator == 0U || numerator > denominator) {
    throw std::runtime_error("invalid quantile request");
  }
  std::sort(values.begin(), values.end());
  const std::uint64_t scaled =
      static_cast<std::uint64_t>(values.size() - 1U) * numerator;
  const std::size_t index = static_cast<std::size_t>(
      (scaled + denominator - 1U) / denominator);
  return values[index];
}

std::uint64_t fnv1a64(const void* raw, std::size_t size) {
  const auto* bytes = static_cast<const unsigned char*>(raw);
  std::uint64_t hash = 14'695'981'039'346'656'037ULL;
  for (std::size_t index = 0U; index < size; ++index) {
    hash ^= bytes[index];
    hash *= 1'099'511'628'211ULL;
  }
  return hash;
}

void append_u32_le(std::vector<std::uint8_t>* bytes,
                   std::uint32_t value) {
  for (std::uint32_t shift = 0U; shift < 32U; shift += 8U) {
    bytes->push_back(static_cast<std::uint8_t>(value >> shift));
  }
}

void append_u64_le(std::vector<std::uint8_t>* bytes,
                   std::uint64_t value) {
  for (std::uint32_t shift = 0U; shift < 64U; shift += 8U) {
    bytes->push_back(static_cast<std::uint8_t>(value >> shift));
  }
}

void append_double_le(std::vector<std::uint8_t>* bytes, double value) {
  append_u64_le(bytes, std::bit_cast<std::uint64_t>(value));
}

void append_dd(std::vector<std::uint8_t>* bytes, DD value) {
  append_double_le(bytes, value.hi);
  append_double_le(bytes, value.lo);
}

void append_disk(std::vector<std::uint8_t>* bytes, DDDisk value) {
  append_dd(bytes, value.real);
  append_dd(bytes, value.imaginary);
  append_double_le(bytes, value.radius);
}

std::vector<std::uint8_t> canonical_corpus_bytes(
    const std::vector<CaseInput>& inputs) {
  constexpr std::size_t kEncodedCaseBytes = 96U;
  std::vector<std::uint8_t> bytes;
  bytes.reserve(inputs.size() * kEncodedCaseBytes);
  for (const CaseInput& input : inputs) {
    append_disk(&bytes, input.left);
    append_disk(&bytes, input.right);
    append_double_le(&bytes, input.right_center_norm_bound);
    append_u32_le(&bytes, input.expected_status_mask);
    append_u32_le(&bytes, input.expectation);
  }
  if (bytes.size() != inputs.size() * kEncodedCaseBytes) {
    throw std::runtime_error("canonical corpus encoding length mismatch");
  }
  return bytes;
}

std::string json_escape(std::string_view input) {
  constexpr char kHex[] = "0123456789abcdef";
  std::string escaped;
  escaped.reserve(input.size());
  for (unsigned char byte : input) {
    switch (byte) {
      case '"':
        escaped += "\\\"";
        break;
      case '\\':
        escaped += "\\\\";
        break;
      case '\b':
        escaped += "\\b";
        break;
      case '\f':
        escaped += "\\f";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        if (byte < 0x20U) {
          escaped += "\\u00";
          escaped.push_back(kHex[byte >> 4U]);
          escaped.push_back(kHex[byte & 0x0fU]);
        } else {
          escaped.push_back(static_cast<char>(byte));
        }
    }
  }
  return escaped;
}

void print_hex64(std::ostream& output, std::uint64_t value) {
  output << '"' << std::hex << std::setw(16) << std::setfill('0')
         << value << std::dec << std::setfill(' ') << '"';
}

struct Timings {
  double full_median_ms = 0.0;
  double fast_median_ms = 0.0;
  double full_minimum_ms = 0.0;
  double fast_minimum_ms = 0.0;
};

template <bool Fast>
double timed_launch(const CaseInput* inputs, DDDisk* outputs,
                    std::uint32_t* statuses, std::uint32_t count,
                    std::uint32_t corpus_mask, cudaEvent_t started,
                    cudaEvent_t stopped, cudaStream_t stream) {
  constexpr std::uint32_t threads = 256U;
  const std::uint32_t blocks =
      std::min<std::uint32_t>((count + threads - 1U) / threads, 65'535U);
  CUDA_CHECK(cudaEventRecord(started, stream));
  benchmark_kernel<Fast><<<blocks, threads, 0U, stream>>>(
      inputs, outputs, statuses, count, corpus_mask);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaEventRecord(stopped, stream));
  CUDA_CHECK(cudaEventSynchronize(stopped));
  float milliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&milliseconds, started, stopped));
  return static_cast<double>(milliseconds);
}

Timings benchmark(const Options& options, const CaseInput* device_inputs,
                  DDDisk* device_outputs, std::uint32_t* device_statuses,
                  std::uint32_t corpus_mask, cudaStream_t stream) {
  const std::uint32_t count = 1U << options.benchmark_log2;
  cudaEvent_t started = nullptr;
  cudaEvent_t stopped = nullptr;
  CUDA_CHECK(cudaEventCreate(&started));
  CUDA_CHECK(cudaEventCreate(&stopped));
  std::vector<double> full;
  std::vector<double> fast;
  full.reserve(options.repetitions);
  fast.reserve(options.repetitions);
  // Untimed warmup.
  (void)timed_launch<false>(
      device_inputs, device_outputs, device_statuses, count, corpus_mask,
      started, stopped, stream);
  (void)timed_launch<true>(
      device_inputs, device_outputs, device_statuses, count, corpus_mask,
      started, stopped, stream);
  for (std::uint32_t repetition = 0U;
       repetition < options.repetitions; ++repetition) {
    if ((repetition & 1U) == 0U) {
      full.push_back(timed_launch<false>(
          device_inputs, device_outputs, device_statuses, count, corpus_mask,
          started, stopped, stream));
      fast.push_back(timed_launch<true>(
          device_inputs, device_outputs, device_statuses, count, corpus_mask,
          started, stopped, stream));
    } else {
      fast.push_back(timed_launch<true>(
          device_inputs, device_outputs, device_statuses, count, corpus_mask,
          started, stopped, stream));
      full.push_back(timed_launch<false>(
          device_inputs, device_outputs, device_statuses, count, corpus_mask,
          started, stopped, stream));
    }
  }
  CUDA_CHECK(cudaEventDestroy(started));
  CUDA_CHECK(cudaEventDestroy(stopped));
  return {
      median(full),
      median(fast),
      *std::min_element(full.begin(), full.end()),
      *std::min_element(fast.begin(), fast.end()),
  };
}

struct DeviceStorage {
  CaseInput* inputs = nullptr;
  DiskMulResult* full = nullptr;
  DiskMulResult* fast = nullptr;
  DDDisk* benchmark_outputs = nullptr;
  std::uint32_t* benchmark_statuses = nullptr;
  CenterResult* near_tight_add = nullptr;
  ScalarMulCase* direct_mul_inputs = nullptr;
  CenterResult* direct_mul_outputs = nullptr;
  cudaStream_t stream = nullptr;

  ~DeviceStorage() {
    if (inputs != nullptr) cudaFree(inputs);
    if (full != nullptr) cudaFree(full);
    if (fast != nullptr) cudaFree(fast);
    if (benchmark_outputs != nullptr) cudaFree(benchmark_outputs);
    if (benchmark_statuses != nullptr) cudaFree(benchmark_statuses);
    if (near_tight_add != nullptr) cudaFree(near_tight_add);
    if (direct_mul_inputs != nullptr) cudaFree(direct_mul_inputs);
    if (direct_mul_outputs != nullptr) cudaFree(direct_mul_outputs);
    if (stream != nullptr) cudaStreamDestroy(stream);
  }
};

void print_kernel_resources(const char* prefix,
                            const cudaFuncAttributes& attributes) {
  std::cout
      << ",\"" << prefix << "_registers_per_thread\":"
      << attributes.numRegs
      << ",\"" << prefix << "_local_bytes\":"
      << attributes.localSizeBytes
      << ",\"" << prefix << "_static_shared_bytes\":"
      << attributes.sharedSizeBytes
      << ",\"" << prefix << "_maximum_threads_per_block\":"
      << attributes.maxThreadsPerBlock;
}

int run(const Options& options) {
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp required_properties{};
  int required_device = 0;
  CUDA_CHECK(cudaGetDevice(&required_device));
  CUDA_CHECK(cudaGetDeviceProperties(
      &required_properties, required_device));
  if (required_properties.major != 9 ||
      required_properties.minor != 0 ||
      std::strstr(required_properties.name, "H100") == nullptr) {
    throw std::runtime_error(
        "strict qualification target requires an NVIDIA H100 sm_90 device");
  }
#endif
  Corpus corpus = build_corpus();
  const std::vector<ScalarMulCase> direct_mul_cases =
      build_direct_fast_mul_cases();
  const std::size_t nonpadding_count = corpus.inputs.size();
  // A power-of-two corpus lets the timed kernel use a mask rather than an
  // integer remainder.  Pad only with a safe PT21-like cell.
  std::size_t padded_count = 1U;
  while (padded_count < corpus.inputs.size()) padded_count <<= 1U;
  while (corpus.inputs.size() < padded_count) {
    corpus.inputs.push_back(corpus.inputs[corpus.pt21_like_begin]);
    corpus.labels.push_back("padding");
  }
  const std::uint32_t corpus_count =
      static_cast<std::uint32_t>(corpus.inputs.size());
  constexpr std::uint32_t pt21_benchmark_mask = 4096U - 1U;
  const std::uint32_t benchmark_count = 1U << options.benchmark_log2;

  DeviceStorage device;
  CUDA_CHECK(cudaStreamCreateWithFlags(
      &device.stream, cudaStreamNonBlocking));
  CUDA_CHECK(cudaMalloc(
      &device.inputs, corpus_count * sizeof(*device.inputs)));
  CUDA_CHECK(cudaMalloc(
      &device.full, corpus_count * sizeof(*device.full)));
  CUDA_CHECK(cudaMalloc(
      &device.fast, corpus_count * sizeof(*device.fast)));
  CUDA_CHECK(cudaMalloc(
      &device.benchmark_outputs,
      static_cast<std::uint64_t>(benchmark_count) *
          sizeof(*device.benchmark_outputs)));
  CUDA_CHECK(cudaMalloc(
      &device.benchmark_statuses,
      static_cast<std::uint64_t>(benchmark_count) *
          sizeof(*device.benchmark_statuses)));
  CUDA_CHECK(cudaMalloc(
      &device.near_tight_add, sizeof(*device.near_tight_add)));
  CUDA_CHECK(cudaMalloc(
      &device.direct_mul_inputs,
      direct_mul_cases.size() * sizeof(*device.direct_mul_inputs)));
  CUDA_CHECK(cudaMalloc(
      &device.direct_mul_outputs,
      direct_mul_cases.size() * sizeof(*device.direct_mul_outputs)));
  CUDA_CHECK(cudaMemcpyAsync(
      device.inputs, corpus.inputs.data(),
      corpus_count * sizeof(*device.inputs),
      cudaMemcpyHostToDevice, device.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      device.direct_mul_inputs, direct_mul_cases.data(),
      direct_mul_cases.size() * sizeof(*device.direct_mul_inputs),
      cudaMemcpyHostToDevice, device.stream));
  constexpr std::uint32_t threads = 256U;
  qualify_kernel<<<(corpus_count + threads - 1U) / threads,
                   threads, 0U, device.stream>>>(
      device.inputs, device.full, device.fast, corpus_count);
  CUDA_CHECK(cudaGetLastError());
  near_tight_fast_add_kernel<<<1U, 1U, 0U, device.stream>>>(
      device.near_tight_add);
  CUDA_CHECK(cudaGetLastError());
  direct_fast_mul_kernel<<<1U, 32U, 0U, device.stream>>>(
      device.direct_mul_inputs, device.direct_mul_outputs,
      static_cast<std::uint32_t>(direct_mul_cases.size()));
  CUDA_CHECK(cudaGetLastError());
  std::vector<DiskMulResult> full(corpus_count);
  std::vector<DiskMulResult> fast(corpus_count);
  CenterResult near_tight_add{};
  std::vector<CenterResult> direct_mul_results(direct_mul_cases.size());
  CUDA_CHECK(cudaMemcpyAsync(
      full.data(), device.full, corpus_count * sizeof(*device.full),
      cudaMemcpyDeviceToHost, device.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      fast.data(), device.fast, corpus_count * sizeof(*device.fast),
      cudaMemcpyDeviceToHost, device.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      &near_tight_add, device.near_tight_add, sizeof(near_tight_add),
      cudaMemcpyDeviceToHost, device.stream));
  CUDA_CHECK(cudaMemcpyAsync(
      direct_mul_results.data(), device.direct_mul_outputs,
      direct_mul_results.size() * sizeof(*device.direct_mul_outputs),
      cudaMemcpyDeviceToHost, device.stream));
  CUDA_CHECK(cudaStreamSynchronize(device.stream));
  const NearTightAddCheck near_tight_add_check =
      check_near_tight_add(near_tight_add);
  std::uint64_t direct_fast_mul_failure_count = 0U;
  for (std::size_t index = 0U; index < direct_mul_cases.size(); ++index) {
    if (!check_direct_fast_mul(
            direct_mul_cases[index], direct_mul_results[index])) {
      ++direct_fast_mul_failure_count;
    }
  }

  std::uint64_t expected_kernel_rejects = 0U;
  std::uint64_t expected_exact_checker_rejects = 0U;
  std::uint64_t expected_invalid_input_reasons = 0U;
  std::uint64_t expected_nonfinite_intermediate_reasons = 0U;
  struct OutcomeCounts {
    std::uint64_t expected_status_reason_matches = 0U;
    std::uint64_t expected_invalid_input_reason_matches = 0U;
    std::uint64_t expected_nonfinite_intermediate_reason_matches = 0U;
    std::uint64_t expected_exact_checker_catches = 0U;
    std::uint64_t expected_right_norm_checker_catches = 0U;
    std::uint64_t expected_behavior_mismatches = 0U;
    std::uint64_t unexpected_kernel_rejects = 0U;
    std::uint64_t unexpected_exact_failures = 0U;
  };
  OutcomeCounts full_counts;
  OutcomeCounts fast_counts;
  std::uint64_t first_full_failure =
      std::numeric_limits<std::uint64_t>::max();
  std::uint64_t first_fast_failure =
      std::numeric_limits<std::uint64_t>::max();
  std::vector<double> radius_ratios;
  radius_ratios.reserve(corpus_count - corpus.pt21_like_begin);
  double maximum_radius_ratio = 0.0;
  std::uint64_t maximum_radius_ratio_index = 0U;
  for (std::uint32_t index = 0U; index < corpus_count; ++index) {
    const CaseInput& input = corpus.inputs[index];
    if (input.expectation == kExpectationKernelReject) {
      ++expected_kernel_rejects;
      if ((input.expected_status_mask & kStatusInvalidInput) != 0U) {
        ++expected_invalid_input_reasons;
      }
      if ((input.expected_status_mask &
           kStatusNonfiniteIntermediate) != 0U) {
        ++expected_nonfinite_intermediate_reasons;
      }
    } else if (input.expectation ==
               kExpectationExactCheckerReject) {
      ++expected_exact_checker_rejects;
    }
    auto evaluate = [&](const DiskMulResult& result,
                        OutcomeCounts* counts,
                        std::uint64_t* first_failure) {
      if (input.expectation == kExpectationKernelReject) {
        const bool reason_matches =
            result.status == input.expected_status_mask;
        if (reason_matches) {
          ++counts->expected_status_reason_matches;
          if ((input.expected_status_mask &
               kStatusInvalidInput) != 0U) {
            ++counts->expected_invalid_input_reason_matches;
          }
          if ((input.expected_status_mask &
               kStatusNonfiniteIntermediate) != 0U) {
            ++counts->expected_nonfinite_intermediate_reason_matches;
          }
        } else {
          ++counts->expected_behavior_mismatches;
        }
        return;
      }
      if (result.status != kStatusOk) {
        if (input.expectation == kExpectationExactCheckerReject) {
          ++counts->expected_behavior_mismatches;
        } else {
          ++counts->unexpected_kernel_rejects;
        }
        return;
      }
      const ExactCheck exact = exact_check(input, result);
      const bool exact_accepted = exact.accepted();
      if (input.expectation == kExpectationExactCheckerReject) {
        const bool caught_only_by_right_norm =
            exact.decoded && exact.center_bound &&
            exact.left_norm_bound && !exact.right_norm_bound &&
            exact.radius_bound;
        if (exact_accepted || !caught_only_by_right_norm) {
          ++counts->expected_behavior_mismatches;
        } else {
          ++counts->expected_exact_checker_catches;
          ++counts->expected_right_norm_checker_catches;
        }
      } else if (!exact_accepted) {
        if (counts->unexpected_exact_failures == 0U) {
          *first_failure = index;
        }
        ++counts->unexpected_exact_failures;
      }
    };
    evaluate(full[index], &full_counts, &first_full_failure);
    evaluate(fast[index], &fast_counts, &first_fast_failure);
    if (index >= corpus.pt21_like_begin &&
        index < corpus.labels.size() &&
        corpus.labels[index] != "padding" &&
        full[index].status == kStatusOk &&
        fast[index].status == kStatusOk &&
        full[index].output.radius > 0.0) {
      const double ratio =
          fast[index].output.radius / full[index].output.radius;
      radius_ratios.push_back(ratio);
      if (ratio > maximum_radius_ratio) {
        maximum_radius_ratio = ratio;
        maximum_radius_ratio_index = index;
      }
    }
  }
  const double median_radius_ratio =
      radius_ratios.empty() ? 0.0 : median(radius_ratios);
  const double p90_radius_ratio =
      radius_ratios.empty() ? 0.0 : quantile(radius_ratios, 9U, 10U);
  const double p99_radius_ratio =
      radius_ratios.empty() ? 0.0 : quantile(radius_ratios, 99U, 100U);
  const std::vector<std::uint8_t> corpus_bytes =
      canonical_corpus_bytes(corpus.inputs);
  const std::uint64_t corpus_fnv1a64 = fnv1a64(
      corpus_bytes.data(), corpus_bytes.size());
  const std::string corpus_sha256 = sparkinterval::sha256_hex(
      corpus_bytes.data(), corpus_bytes.size());

  const Timings timings = benchmark(
      options, device.inputs + corpus.pt21_like_begin,
      device.benchmark_outputs, device.benchmark_statuses,
      pt21_benchmark_mask, device.stream);
  cudaFuncAttributes full_attributes{};
  cudaFuncAttributes fast_attributes{};
  CUDA_CHECK(cudaFuncGetAttributes(
      &full_attributes, benchmark_kernel<false>));
  CUDA_CHECK(cudaFuncGetAttributes(
      &fast_attributes, benchmark_kernel<true>));
  cudaDeviceProp properties{};
  int device_index = 0;
  CUDA_CHECK(cudaGetDevice(&device_index));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device_index));
  int cuda_runtime_version = 0;
  CUDA_CHECK(cudaRuntimeGetVersion(&cuda_runtime_version));

  const bool accepted =
      full_counts.expected_status_reason_matches ==
          expected_kernel_rejects &&
      fast_counts.expected_status_reason_matches ==
          expected_kernel_rejects &&
      full_counts.expected_exact_checker_catches ==
          expected_exact_checker_rejects &&
      fast_counts.expected_exact_checker_catches ==
          expected_exact_checker_rejects &&
      full_counts.expected_right_norm_checker_catches ==
          expected_exact_checker_rejects &&
      fast_counts.expected_right_norm_checker_catches ==
          expected_exact_checker_rejects &&
      full_counts.expected_behavior_mismatches == 0U &&
      fast_counts.expected_behavior_mismatches == 0U &&
      full_counts.unexpected_kernel_rejects == 0U &&
      fast_counts.unexpected_kernel_rejects == 0U &&
      full_counts.unexpected_exact_failures == 0U &&
      fast_counts.unexpected_exact_failures == 0U &&
      near_tight_add_check.accepted() &&
      direct_fast_mul_failure_count == 0U &&
      !radius_ratios.empty();
  std::cout << std::setprecision(17)
            << "{\"schema\":"
            << "\"sparkinterval.tg.platt-dd-sloppy-mul-qualification.v1\""
            << ",\"accepted\":" << (accepted ? "true" : "false")
            << ",\"qualification_only\":true"
            << ",\"production_transform_modified\":false"
            << ",\"cuda_to_lean_refinement_claimed\":false"
            << ",\"build_profile\":{\"cmake_build_config\":\""
            << kBuildProfile << "\",\"ndebug_defined\":"
            << (kNdebugDefined ? "true" : "false")
            << ",\"release_performance_build\":"
            << (kReleasePerformanceBuild ? "true" : "false") << '}'
            << ",\"device_profile\":{\"name\":\""
            << json_escape(properties.name)
            << "\",\"compute_capability\":\""
            << properties.major << '.' << properties.minor << "\""
            << ",\"multiprocessor_count\":"
            << properties.multiProcessorCount
            << ",\"maximum_threads_per_block\":"
            << properties.maxThreadsPerBlock
            << ",\"shared_memory_per_multiprocessor\":"
            << properties.sharedMemPerMultiprocessor
            << ",\"cuda_runtime_version\":"
            << cuda_runtime_version << '}'
            << ",\"corpus_count\":" << corpus_count
            << ",\"nonpadding_case_count\":" << nonpadding_count
            << ",\"corpus_encoding\":"
            << "\"caseinput-v1-little-endian-iec559-binary64\""
            << ",\"corpus_sha256\":\"" << corpus_sha256 << "\""
            << ",\"corpus_fnv1a64\":";
  print_hex64(std::cout, corpus_fnv1a64);
  std::cout
            << ",\"pt21_like_case_count\":4096"
            << ",\"expected_kernel_reject_count\":"
            << expected_kernel_rejects
            << ",\"expected_exact_checker_reject_count\":"
            << expected_exact_checker_rejects
            << ",\"expected_invalid_input_reason_count\":"
            << expected_invalid_input_reasons
            << ",\"expected_nonfinite_intermediate_reason_count\":"
            << expected_nonfinite_intermediate_reasons
            << ",\"full_expected_status_reason_match_count\":"
            << full_counts.expected_status_reason_matches
            << ",\"fast_expected_status_reason_match_count\":"
            << fast_counts.expected_status_reason_matches
            << ",\"full_expected_invalid_input_reason_match_count\":"
            << full_counts.expected_invalid_input_reason_matches
            << ",\"fast_expected_invalid_input_reason_match_count\":"
            << fast_counts.expected_invalid_input_reason_matches
            << ",\"full_expected_nonfinite_intermediate_reason_match_count\":"
            << full_counts.expected_nonfinite_intermediate_reason_matches
            << ",\"fast_expected_nonfinite_intermediate_reason_match_count\":"
            << fast_counts.expected_nonfinite_intermediate_reason_matches
            << ",\"full_expected_exact_checker_catch_count\":"
            << full_counts.expected_exact_checker_catches
            << ",\"fast_expected_exact_checker_catch_count\":"
            << fast_counts.expected_exact_checker_catches
            << ",\"full_expected_right_norm_checker_catch_count\":"
            << full_counts.expected_right_norm_checker_catches
            << ",\"fast_expected_right_norm_checker_catch_count\":"
            << fast_counts.expected_right_norm_checker_catches
            << ",\"full_expected_behavior_mismatch_count\":"
            << full_counts.expected_behavior_mismatches
            << ",\"fast_expected_behavior_mismatch_count\":"
            << fast_counts.expected_behavior_mismatches
            << ",\"unexpected_full_kernel_reject_count\":"
            << full_counts.unexpected_kernel_rejects
            << ",\"unexpected_fast_kernel_reject_count\":"
            << fast_counts.unexpected_kernel_rejects
            << ",\"full_exact_dyadic_failure_count\":"
            << full_counts.unexpected_exact_failures
            << ",\"fast_exact_dyadic_failure_count\":"
            << fast_counts.unexpected_exact_failures;
  if (full_counts.unexpected_exact_failures != 0U) {
    std::cout << ",\"first_full_exact_failure\":"
              << first_full_failure;
  }
  if (fast_counts.unexpected_exact_failures != 0U) {
    std::cout << ",\"first_fast_exact_failure\":"
              << first_fast_failure;
  }
  std::cout
      << ",\"near_tight_fast_add_exact_bound\":"
      << (near_tight_add_check.exact_bound ? "true" : "false")
      << ",\"near_tight_fast_add_reserved_zero\":"
      << (near_tight_add_check.reserved_zero ? "true" : "false")
      << ",\"near_tight_fast_add_expected_result_bits\":"
      << (near_tight_add_check.expected_result_bits ? "true" : "false")
      << ",\"near_tight_fast_add_expected_error_bits\":"
      << (near_tight_add_check.expected_error_bits ? "true" : "false")
      << ",\"near_tight_fast_add_expected_exact_error\":"
      << (near_tight_add_check.expected_exact_error ? "true" : "false")
      << ",\"direct_fast_mul_case_count\":"
      << direct_mul_cases.size()
      << ",\"direct_fast_mul_exact_failure_count\":"
      << direct_fast_mul_failure_count
      << ",\"median_pt21_like_radius_inflation\":"
      << median_radius_ratio
      << ",\"p90_pt21_like_radius_inflation\":"
      << p90_radius_ratio
      << ",\"p99_pt21_like_radius_inflation\":"
      << p99_radius_ratio
      << ",\"maximum_pt21_like_radius_inflation\":"
      << maximum_radius_ratio
      << ",\"maximum_radius_inflation_case\":"
      << maximum_radius_ratio_index
      << ",\"benchmark_log2\":" << options.benchmark_log2
      << ",\"benchmark_operations\":" << benchmark_count
      << ",\"benchmark_input_profile\":\"pt21-like-only\""
      << ",\"repetitions\":" << options.repetitions
      << ",\"full_median_ms\":" << timings.full_median_ms
      << ",\"fast_median_ms\":" << timings.fast_median_ms
      << ",\"full_minimum_ms\":" << timings.full_minimum_ms
      << ",\"fast_minimum_ms\":" << timings.fast_minimum_ms
      << ",\"median_speedup\":"
      << timings.full_median_ms / timings.fast_median_ms;
  print_kernel_resources("full", full_attributes);
  print_kernel_resources("fast", fast_attributes);
  std::cout
      << ",\"arithmetic_checker\":"
      << "\"independent-exact-binary64-dyadic-cpp-rational\""
      << ",\"semantic_decomposition\":"
      << "\"SparkInterval.Certified.ComplexDisk.MulCertificate\""
      << ",\"ftz_disabled_compile_contract\":true"
      << ",\"underflow_policy\":"
      << "\"explicit-minimum-subnormal-error-budget-ftz-disabled\""
      << ",\"overflow_policy\":\"fail-closed-nonfinite\"}\n";
  return accepted ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-dd-sloppy-mul-qualification: "
              << error.what() << '\n';
    return 2;
  }
}

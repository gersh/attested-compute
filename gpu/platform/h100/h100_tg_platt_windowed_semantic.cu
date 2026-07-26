// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-semantic directed-binary64 implementation of the transform portion
// of djplatt/code zeta_arb/arb_zeta.cpp at
// 42b21426718e542daa2b006dc05ea2d7f26426e6.
//
// This program deliberately starts from certified boxes for gamma(t) and the
// bucketed Taylor sums.  It implements G_k, my_convolve/do_conv, the published
// error insertions, zero padding, and arb_fft.h::hermidft in their source
// order.  Gamma construction, Dirichlet-term bucketing, interpolation, zero
// isolation, and Turing completeness are outside this executable.  Therefore
// its output is never, by itself, a zeta-zero certificate.

#include "sparkinterval/tg_platt_windowed.hpp"

#include <cuda_runtime.h>
#include <mpfr.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace pw = sparkinterval::tg::platt_windowed;

namespace {

using pw::ComplexInterval;
using pw::RealInterval;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +               \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

constexpr double kGTruncationError = 1.83e-44;
constexpr double kGTransformError = 1.0e-307;
constexpr double kFHatSumError = 3.26e-33;
constexpr double kTaylorError = 6.73e-33;
constexpr double kFHatTransformError = 1.0e-307;
constexpr double kFMaxError = 3.93e-245;

struct Options {
  std::uint32_t convolution_length = 8U;
  std::uint32_t taylor_terms = 3U;
  std::uint32_t repetitions = 1U;
  bool source_shape = false;
  bool source_errors = false;
};

std::uint64_t parse_unsigned(const char* text, const char* label) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  errno = 0;
  char* end = nullptr;
  const unsigned long long value = std::strtoull(text, &end, 10);
  if (errno != 0 || end == nullptr || *end != '\0') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<std::uint64_t>(value);
}

bool is_power_of_two(std::uint32_t value) {
  return value != 0U && (value & (value - 1U)) == 0U;
}

std::uint32_t exact_log2(std::uint32_t value) {
  if (!is_power_of_two(value)) throw std::runtime_error("length is not radix 2");
  std::uint32_t result = 0U;
  while ((1U << result) != value) ++result;
  return result;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    auto value_after = [&](const char* prefix) -> const char* {
      const std::string key(prefix);
      return argument.rfind(key, 0) == 0 ? argv[index] + key.size() : nullptr;
    };
    if (argument == "--source-shape") {
      options.source_shape = true;
      options.source_errors = true;
      options.convolution_length = pw::kBucketCount;
      options.taylor_terms = pw::kTaylorTerms;
    } else if (argument == "--source-errors") {
      options.source_errors = true;
    } else if (argument == "--no-source-errors") {
      options.source_errors = false;
    } else if (const char* value = value_after("--length=")) {
      const auto parsed = parse_unsigned(value, "convolution length");
      if (parsed < 2U || parsed > pw::kBucketCount ||
          !is_power_of_two(static_cast<std::uint32_t>(parsed))) {
        throw std::runtime_error(
            "convolution length must be a power of two in 2..32768");
      }
      options.convolution_length = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--stages=")) {
      const auto parsed = parse_unsigned(value, "Taylor stage count");
      if (parsed == 0U || parsed > pw::kTaylorTerms) {
        throw std::runtime_error("Taylor stages must be in 1..23");
      }
      options.taylor_terms = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--repetitions=")) {
      const auto parsed = parse_unsigned(value, "repetition count");
      if (parsed == 0U || parsed > 1000U) {
        throw std::runtime_error("repetitions must be in 1..1000");
      }
      options.repetitions = static_cast<std::uint32_t>(parsed);
    } else {
      throw std::runtime_error("unknown option: " + argument);
    }
  }
  if (!is_power_of_two(options.convolution_length)) {
    throw std::runtime_error("convolution length is not radix 2");
  }
  return options;
}

struct MpfrValue {
  mpfr_t value;
  explicit MpfrValue(mpfr_prec_t precision = 320) { mpfr_init2(value, precision); }
  ~MpfrValue() { mpfr_clear(value); }
  MpfrValue(const MpfrValue&) = delete;
  MpfrValue& operator=(const MpfrValue&) = delete;
};

double mpfr_down(mpfr_srcptr value) { return mpfr_get_d(value, MPFR_RNDD); }
double mpfr_up(mpfr_srcptr value) { return mpfr_get_d(value, MPFR_RNDU); }

// Every angle passed to sinpi/cospi is an exact dyadic.  MPFR therefore sees
// the exact rational 2*j/max_length, not a rounded approximation to pi.
std::vector<ComplexInterval> initialize_positive_roots(
    std::uint32_t max_length) {
  std::vector<ComplexInterval> roots(max_length / 2U);
  const std::uint32_t log_length = exact_log2(max_length);
  MpfrValue turn, sine_lo, sine_hi, cosine_lo, cosine_hi;
  for (std::uint32_t index = 0; index < max_length / 2U; ++index) {
    mpfr_set_ui(turn.value, index, MPFR_RNDN);
    mpfr_div_2ui(turn.value, turn.value, log_length - 1U, MPFR_RNDN);
    mpfr_sinpi(sine_lo.value, turn.value, MPFR_RNDD);
    mpfr_sinpi(sine_hi.value, turn.value, MPFR_RNDU);
    mpfr_cospi(cosine_lo.value, turn.value, MPFR_RNDD);
    mpfr_cospi(cosine_hi.value, turn.value, MPFR_RNDU);
    roots[index] = {{mpfr_down(cosine_lo.value), mpfr_up(cosine_hi.value)},
                    {mpfr_down(sine_lo.value), mpfr_up(sine_hi.value)}};
  }
  return roots;
}

std::vector<RealInterval> initialize_stage_reciprocals(
    std::uint32_t stages) {
  std::vector<RealInterval> reciprocals(stages);
  MpfrValue numerator, denominator, lower, upper;
  mpfr_set_ui(numerator.value, 1U, MPFR_RNDN);
  for (std::uint32_t stage = 0; stage < stages; ++stage) {
    mpfr_set_ui(denominator.value, stage + 1U, MPFR_RNDN);
    mpfr_div(lower.value, numerator.value, denominator.value, MPFR_RNDD);
    mpfr_div(upper.value, numerator.value, denominator.value, MPFR_RNDU);
    reciprocals[stage] = {mpfr_down(lower.value), mpfr_up(upper.value)};
  }
  return reciprocals;
}

ComplexInterval initialize_omega(std::uint32_t full_sample_length) {
  const std::uint32_t log_length = exact_log2(full_sample_length);
  MpfrValue turn, sine_lo, sine_hi, cosine_lo, cosine_hi;
  mpfr_set_ui(turn.value, 1U, MPFR_RNDN);
  // sinpi/cospi argument is 2/full_sample_length.
  mpfr_div_2ui(turn.value, turn.value, log_length - 1U, MPFR_RNDN);
  mpfr_sinpi(sine_lo.value, turn.value, MPFR_RNDD);
  mpfr_sinpi(sine_hi.value, turn.value, MPFR_RNDU);
  mpfr_cospi(cosine_lo.value, turn.value, MPFR_RNDD);
  mpfr_cospi(cosine_hi.value, turn.value, MPFR_RNDU);
  return {{mpfr_down(cosine_lo.value), mpfr_up(cosine_hi.value)},
          {mpfr_down(sine_lo.value), mpfr_up(sine_hi.value)}};
}

RealInterval source_two_pi_t(std::uint32_t index, std::uint32_t length) {
  // Upstream: t=(index-N1/2)*(21/128), two_pi_t=-2*pi*t.
  const std::int64_t signed_index = static_cast<std::int64_t>(index) -
                                    static_cast<std::int64_t>(length / 2U);
  MpfrValue pi_lo, pi_hi, t, product_lo, product_hi;
  mpfr_const_pi(pi_lo.value, MPFR_RNDD);
  mpfr_const_pi(pi_hi.value, MPFR_RNDU);
  mpfr_set_si(t.value, -signed_index, MPFR_RNDN);
  mpfr_mul_ui(t.value, t.value, 21U, MPFR_RNDN);
  mpfr_div_2ui(t.value, t.value, 6U, MPFR_RNDN);  // -2*(21/128)
  if (mpfr_sgn(t.value) >= 0) {
    mpfr_mul(product_lo.value, t.value, pi_lo.value, MPFR_RNDD);
    mpfr_mul(product_hi.value, t.value, pi_hi.value, MPFR_RNDU);
  } else {
    mpfr_mul(product_lo.value, t.value, pi_hi.value, MPFR_RNDD);
    mpfr_mul(product_hi.value, t.value, pi_lo.value, MPFR_RNDU);
  }
  return {mpfr_down(product_lo.value), mpfr_up(product_hi.value)};
}

struct HostInputs {
  std::vector<ComplexInterval> gamma0;
  std::vector<RealInterval> two_pi_t;
  std::vector<ComplexInterval> skn_rows;
};

HostInputs initialize_inputs(const Options& options) {
  const std::uint32_t length = options.convolution_length;
  HostInputs inputs;
  inputs.gamma0.resize(length);
  inputs.two_pi_t.resize(length);
  inputs.skn_rows.resize(static_cast<std::size_t>(options.taylor_terms) * length);
  for (std::uint32_t index = 0; index < length; ++index) {
    // Exact dyadic KAT/source-shape placeholders.  The semantic production
    // boundary replaces gamma0 and skn_rows with the certified upstream boxes.
    const std::int32_t re_numerator = static_cast<std::int32_t>(index % 17U) - 8;
    const std::int32_t im_numerator = static_cast<std::int32_t>(index % 11U) - 5;
    const double re = std::ldexp(static_cast<double>(re_numerator), -8);
    const double im = std::ldexp(static_cast<double>(im_numerator), -9);
    inputs.gamma0[index] = {{re, re}, {im, im}};
    if (options.source_shape) {
      inputs.two_pi_t[index] = source_two_pi_t(index, length);
    } else {
      const std::int32_t t_numerator = static_cast<std::int32_t>(index) -
                                       static_cast<std::int32_t>(length / 2U);
      const double value = std::ldexp(static_cast<double>(t_numerator), -4);
      inputs.two_pi_t[index] = {value, value};
    }
  }
  for (std::uint32_t stage = 0; stage < options.taylor_terms; ++stage) {
    for (std::uint32_t index = 0; index < length; ++index) {
      const std::int32_t re_numerator = static_cast<std::int32_t>(
          ((stage + 3U) * (index + 5U)) % 29U) - 14;
      const std::int32_t im_numerator = static_cast<std::int32_t>(
          ((stage + 7U) * (index + 2U)) % 31U) - 15;
      // Source residuals satisfy |s_n-u_m| <= 1/(2B) < 2^-13.  Scaling the
      // synthetic stage by 2^(-13k) gives the work-shape input the same
      // essential cancellation as make_skn's residual power.  These remain
      // synthetic exact dyadics; they are not claimed to be actual sums.
      const int stage_scale = options.source_shape
                                  ? -10 - 13 * static_cast<int>(stage)
                                  : -10;
      const double re =
          std::ldexp(static_cast<double>(re_numerator), stage_scale);
      const double im =
          std::ldexp(static_cast<double>(im_numerator), stage_scale);
      inputs.skn_rows[static_cast<std::size_t>(stage) * length + index] =
          {{re, re}, {im, im}};
    }
  }
  return inputs;
}

__device__ __forceinline__ RealInterval add(RealInterval x, RealInterval y) {
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
}

__device__ __forceinline__ RealInterval sub(RealInterval x, RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval negate(RealInterval x) {
  return {-x.hi, -x.lo};
}

__device__ __forceinline__ RealInterval mul(RealInterval x, RealInterval y) {
  const double down[] = {__dmul_rd(x.lo, y.lo), __dmul_rd(x.lo, y.hi),
                         __dmul_rd(x.hi, y.lo), __dmul_rd(x.hi, y.hi)};
  const double up[] = {__dmul_ru(x.lo, y.lo), __dmul_ru(x.lo, y.hi),
                       __dmul_ru(x.hi, y.lo), __dmul_ru(x.hi, y.hi)};
  return {fmin(fmin(down[0], down[1]), fmin(down[2], down[3])),
          fmax(fmax(up[0], up[1]), fmax(up[2], up[3]))};
}

__device__ __forceinline__ ComplexInterval cadd(ComplexInterval x,
                                                 ComplexInterval y) {
  return {add(x.re, y.re), add(x.im, y.im)};
}

__device__ __forceinline__ ComplexInterval csub(ComplexInterval x,
                                                 ComplexInterval y) {
  return {sub(x.re, y.re), sub(x.im, y.im)};
}

__device__ __forceinline__ ComplexInterval cnegate(ComplexInterval x) {
  return {negate(x.re), negate(x.im)};
}

__device__ __forceinline__ ComplexInterval cconjugate(ComplexInterval x) {
  return {x.re, negate(x.im)};
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

__device__ __forceinline__ ComplexInterval times_i(ComplexInterval x) {
  return {negate(x.im), x.re};
}

__device__ __forceinline__ ComplexInterval add_square_error(
    ComplexInterval x, double radius) {
  const RealInterval error{-radius, radius};
  return {add(x.re, error), add(x.im, error)};
}

__global__ void build_gamma_rows(const ComplexInterval* gamma0,
                                 const RealInterval* two_pi_t,
                                 const RealInterval* stage_reciprocals,
                                 std::uint32_t length,
                                 std::uint32_t stages,
                                 ComplexInterval* rows) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < length; index += blockDim.x * gridDim.x) {
    ComplexInterval value = gamma0[index];
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      rows[static_cast<std::uint64_t>(stage) * length + index] = value;
      if (stage + 1U != stages) {
        value = cscale(times_i(value), two_pi_t[index]);
        value = cscale(value, stage_reciprocals[stage]);
      }
    }
  }
}

__global__ void copy_add_g_error(const ComplexInterval* input,
                                 ComplexInterval* output,
                                 std::uint64_t count,
                                 double error) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    output[index] = add_square_error(input[index], error);
  }
}

__global__ void bit_reverse_lines(const ComplexInterval* input,
                                  ComplexInterval* output,
                                  std::uint32_t lines,
                                  std::uint32_t transform_length,
                                  std::uint32_t log_length) {
  const std::uint64_t count =
      static_cast<std::uint64_t>(lines) * transform_length;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t position =
        static_cast<std::uint32_t>(flat % transform_length);
    const std::uint32_t reversed = __brev(position) >> (32U - log_length);
    const std::uint64_t line = flat / transform_length;
    output[line * transform_length + reversed] = input[flat];
  }
}

__global__ void radix2_stage(ComplexInterval* values,
                             const ComplexInterval* positive_roots,
                             std::uint32_t lines,
                             std::uint32_t transform_length,
                             std::uint32_t maximum_length,
                             std::uint32_t stage_length,
                             bool negative_sign) {
  const std::uint64_t butterflies =
      static_cast<std::uint64_t>(lines) * transform_length / 2U;
  const std::uint32_t half = stage_length / 2U;
  const std::uint32_t root_stride = maximum_length / stage_length;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < butterflies;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / (transform_length / 2U);
    const std::uint64_t local = flat % (transform_length / 2U);
    const std::uint64_t group = local / half;
    const std::uint32_t offset = static_cast<std::uint32_t>(local % half);
    const std::uint64_t left = line * transform_length +
                               group * stage_length + offset;
    const std::uint64_t right = left + half;
    ComplexInterval root = positive_roots[offset * root_stride];
    if (negative_sign) root = cconjugate(root);
    const ComplexInterval first = values[left];
    const ComplexInterval second = cmul(values[right], root);
    values[left] = cadd(first, second);
    values[right] = csub(first, second);
  }
}

__global__ void postprocess_G(ComplexInterval* rows,
                              std::uint32_t length,
                              std::uint32_t stages,
                              double transform_error) {
  const std::uint64_t count = static_cast<std::uint64_t>(stages) * length;
  // acb_div_arb(..., A1) with A1=128/21 is multiplication by exact 21/128.
  constexpr RealInterval inverse_A1{21.0 / 128.0, 21.0 / 128.0};
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t index = static_cast<std::uint32_t>(flat % length);
    if (index > length / 2U) {
      rows[flat] = {{0.0, 0.0}, {0.0, 0.0}};
      continue;
    }
    ComplexInterval value = cscale(rows[flat], inverse_A1);
    value = add_square_error(value, transform_error);
    rows[flat] = (index & 1U) != 0U ? cnegate(value) : value;
  }
}

__global__ void pointwise_products(const ComplexInterval* left,
                                   const ComplexInterval* right,
                                   ComplexInterval* output,
                                   std::uint64_t count) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    output[index] = cmul(left[index], right[index]);
  }
}

__global__ void normalize_and_taylor_sum(const ComplexInterval* rows,
                                         ComplexInterval* retained,
                                         std::uint32_t length,
                                         std::uint32_t stages,
                                         RealInterval reciprocal_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < length / 2U; index += blockDim.x * gridDim.x) {
    ComplexInterval sum{{0.0, 0.0}, {0.0, 0.0}};
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      sum = cadd(sum, cscale(
          rows[static_cast<std::uint64_t>(stage) * length + index],
          reciprocal_length));
    }
    retained[index] = sum;
  }
}

__global__ void initialize_half_spectrum(
    const ComplexInterval* retained, ComplexInterval* half_spectrum,
    std::uint32_t convolution_length, double fmax_error,
    double fhatsum_error, double taylor_error, double transform_error) {
  const std::uint32_t reduced_length = 2U * convolution_length;
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index <= reduced_length; index += blockDim.x * gridDim.x) {
    ComplexInterval value =
        index < convolution_length / 2U
            ? retained[index]
            : ComplexInterval{{-fmax_error, fmax_error},
                              {-fmax_error, fmax_error}};
    value = add_square_error(value, fhatsum_error);
    value = add_square_error(value, taylor_error);
    value = add_square_error(value, transform_error);
    // arb_zeta.cpp negates every odd Fourier coefficient immediately before
    // calling hermidft.
    half_spectrum[index] = (index & 1U) != 0U ? cnegate(value) : value;
  }
}

__global__ void hermidft_preprocess(const ComplexInterval* half_spectrum,
                                    ComplexInterval* reduced,
                                    const ComplexInterval* roots,
                                    ComplexInterval omega,
                                    std::uint32_t reduced_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    if (index == 0U) {
      // This is exactly arb_fft.h::hermidft's special endpoint assignment;
      // the source uses only the real parts of x[0] and x[NN].
      reduced[0] = {
          add(half_spectrum[0].re, half_spectrum[reduced_length].re),
          sub(half_spectrum[0].re, half_spectrum[reduced_length].re)};
      continue;
    }
    const ComplexInterval mirror =
        cconjugate(half_spectrum[reduced_length - index]);
    const ComplexInterval pair_sum = cadd(mirror, half_spectrum[index]);
    ComplexInterval pair_difference =
        times_i(csub(half_spectrum[index], mirror));
    pair_difference = cmul(pair_difference, roots[index / 2U]);
    if ((index & 1U) != 0U) pair_difference = cmul(pair_difference, omega);
    reduced[index] = cadd(pair_difference, pair_sum);
  }
}

__global__ void interleave_hermidft_output(const ComplexInterval* reduced,
                                           RealInterval* samples,
                                           std::uint32_t reduced_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    samples[2U * index] = reduced[index].re;
    samples[2U * index + 1U] = reduced[index].im;
  }
}

std::uint32_t blocks_for(std::uint64_t count) {
  constexpr std::uint32_t threads = 256U;
  return static_cast<std::uint32_t>(
      std::min<std::uint64_t>((count + threads - 1U) / threads, 4096U));
}

void transform(const ComplexInterval* input, ComplexInterval* output,
               const ComplexInterval* roots, std::uint32_t lines,
               std::uint32_t length, std::uint32_t maximum_length,
               bool negative_sign) {
  constexpr std::uint32_t threads = 256U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  bit_reverse_lines<<<blocks_for(cells), threads>>>(
      input, output, lines, length, exact_log2(length));
  for (std::uint32_t stage_length = 2U; stage_length <= length;
       stage_length <<= 1U) {
    radix2_stage<<<blocks_for(cells / 2U), threads>>>(
        output, roots, lines, length, maximum_length, stage_length,
        negative_sign);
  }
}

using LongComplex = std::complex<long double>;

std::vector<LongComplex> direct_dft(const std::vector<LongComplex>& input,
                                    bool negative_sign) {
  const std::size_t length = input.size();
  const long double pi = acosl(-1.0L);
  const long double sign = negative_sign ? -1.0L : 1.0L;
  std::vector<LongComplex> output(length);
  for (std::size_t frequency = 0; frequency < length; ++frequency) {
    LongComplex sum{};
    for (std::size_t index = 0; index < length; ++index) {
      const long double angle = sign * 2.0L * pi *
          static_cast<long double>(index * frequency) /
          static_cast<long double>(length);
      sum += input[index] * LongComplex(cosl(angle), sinl(angle));
    }
    output[frequency] = sum;
  }
  return output;
}

std::vector<long double> reference_samples(const Options& options,
                                           const HostInputs& inputs) {
  const std::uint32_t length = options.convolution_length;
  const std::uint32_t stages = options.taylor_terms;
  std::vector<std::vector<LongComplex>> gamma_rows(
      stages, std::vector<LongComplex>(length));
  for (std::uint32_t index = 0; index < length; ++index) {
    LongComplex value(inputs.gamma0[index].re.lo, inputs.gamma0[index].im.lo);
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      gamma_rows[stage][index] = value;
      if (stage + 1U != stages) {
        value *= LongComplex(0.0L, 1.0L);
        value *= static_cast<long double>(inputs.two_pi_t[index].lo);
        value /= static_cast<long double>(stage + 1U);
      }
    }
  }
  std::vector<LongComplex> retained(length / 2U);
  for (std::uint32_t stage = 0; stage < stages; ++stage) {
    std::vector<LongComplex> G = direct_dft(gamma_rows[stage], true);
    for (std::uint32_t index = 0; index < length; ++index) {
      if (index > length / 2U) {
        G[index] = {};
      } else {
        G[index] *= 21.0L / 128.0L;
        if ((index & 1U) != 0U) G[index] = -G[index];
      }
    }
    std::vector<LongComplex> S(length);
    for (std::uint32_t index = 0; index < length; ++index) {
      const ComplexInterval box =
          inputs.skn_rows[static_cast<std::size_t>(stage) * length + index];
      S[index] = LongComplex(box.re.lo, box.im.lo);
    }
    G = direct_dft(G, false);
    S = direct_dft(S, false);
    for (std::uint32_t index = 0; index < length; ++index) G[index] *= S[index];
    G = direct_dft(G, true);
    for (std::uint32_t index = 0; index < length / 2U; ++index) {
      retained[index] += G[index] / static_cast<long double>(length);
    }
  }

  const std::uint32_t reduced_length = 2U * length;
  std::vector<LongComplex> x(reduced_length + 1U);
  for (std::uint32_t index = 0; index < length / 2U; ++index) {
    x[index] = retained[index];
  }
  for (std::uint32_t index = 1; index <= reduced_length; index += 2U) {
    x[index] = -x[index];
  }
  std::vector<LongComplex> reduced(reduced_length);
  reduced[0] = LongComplex(x[0].real() + x[reduced_length].real(),
                           x[0].real() - x[reduced_length].real());
  const long double pi = acosl(-1.0L);
  const LongComplex omega(cosl(2.0L * pi / (2.0L * reduced_length)),
                          sinl(2.0L * pi / (2.0L * reduced_length)));
  for (std::uint32_t index = 1; index < reduced_length; ++index) {
    const LongComplex mirror = std::conj(x[reduced_length - index]);
    LongComplex difference = (x[index] - mirror) * LongComplex(0.0L, 1.0L);
    const long double angle = 2.0L * pi * (index / 2U) /
                              static_cast<long double>(reduced_length);
    difference *= LongComplex(cosl(angle), sinl(angle));
    if ((index & 1U) != 0U) difference *= omega;
    reduced[index] = difference + mirror + x[index];
  }
  reduced = direct_dft(reduced, false);
  std::vector<long double> samples(2U * reduced_length);
  for (std::uint32_t index = 0; index < reduced_length; ++index) {
    samples[2U * index] = reduced[index].real();
    samples[2U * index + 1U] = reduced[index].imag();
  }
  return samples;
}

std::uint64_t fnv1a(const std::vector<RealInterval>& values) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = reinterpret_cast<const unsigned char*>(values.data());
  for (std::size_t index = 0; index < values.size() * sizeof(RealInterval);
       ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

int run(const Options& options) {
  constexpr std::uint32_t threads = 256U;
  const std::uint32_t length = options.convolution_length;
  const std::uint32_t stages = options.taylor_terms;
  const std::uint32_t reduced_length = 2U * length;
  const std::uint32_t sample_count = 2U * reduced_length;
  const std::uint64_t row_cells = static_cast<std::uint64_t>(stages) * length;
  const HostInputs host = initialize_inputs(options);
  const std::vector<ComplexInterval> roots =
      initialize_positive_roots(reduced_length);
  const std::vector<RealInterval> stage_reciprocals =
      initialize_stage_reciprocals(stages);
  const double reciprocal_length_value =
      std::ldexp(1.0, -static_cast<int>(exact_log2(length)));
  const RealInterval reciprocal_length{reciprocal_length_value,
                                       reciprocal_length_value};
  const ComplexInterval omega = initialize_omega(sample_count);

  cudaDeviceProp properties{};
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties.major != 9 || properties.minor != 0 ||
      std::strstr(properties.name, "H100") == nullptr) {
    throw std::runtime_error(
        "strict production target requires an NVIDIA H100 sm_90 device");
  }
#endif

  ComplexInterval *d_gamma0 = nullptr, *d_gamma_rows = nullptr;
  ComplexInterval *d_G_negative = nullptr, *d_G_positive = nullptr;
  ComplexInterval *d_S_positive = nullptr, *d_products = nullptr;
  ComplexInterval *d_convolutions = nullptr, *d_retained = nullptr;
  ComplexInterval *d_half_spectrum = nullptr, *d_hermi_pre = nullptr;
  ComplexInterval *d_hermi_fft = nullptr, *d_roots = nullptr;
  RealInterval *d_two_pi_t = nullptr, *d_stage_reciprocals = nullptr;
  RealInterval* d_samples = nullptr;
  ComplexInterval* d_skn = nullptr;
  CUDA_CHECK(cudaMalloc(&d_gamma0, length * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_two_pi_t, length * sizeof(RealInterval)));
  CUDA_CHECK(cudaMalloc(&d_stage_reciprocals,
                        stages * sizeof(RealInterval)));
  CUDA_CHECK(cudaMalloc(&d_skn, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_gamma_rows, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_G_negative, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_G_positive, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_S_positive, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_products, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_convolutions, row_cells * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_retained, (length / 2U) * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_half_spectrum,
                        (reduced_length + 1U) * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_hermi_pre,
                        reduced_length * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_hermi_fft,
                        reduced_length * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_roots, roots.size() * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&d_samples, sample_count * sizeof(RealInterval)));
  CUDA_CHECK(cudaMemcpy(d_gamma0, host.gamma0.data(),
                        length * sizeof(ComplexInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_two_pi_t, host.two_pi_t.data(),
                        length * sizeof(RealInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_stage_reciprocals, stage_reciprocals.data(),
                        stages * sizeof(RealInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_skn, host.skn_rows.data(),
                        row_cells * sizeof(ComplexInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots, roots.data(),
                        roots.size() * sizeof(ComplexInterval),
                        cudaMemcpyHostToDevice));

  const double g_error = options.source_errors ? kGTruncationError : 0.0;
  const double G_error = options.source_errors ? kGTransformError : 0.0;
  const double fmax_error = options.source_errors ? kFMaxError : 0.0;
  const double fhatsum_error = options.source_errors ? kFHatSumError : 0.0;
  const double taylor_error = options.source_errors ? kTaylorError : 0.0;
  const double fhat_transform_error =
      options.source_errors ? kFHatTransformError : 0.0;

  cudaEvent_t start{}, stop{};
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t repetition = 0; repetition < options.repetitions;
       ++repetition) {
    build_gamma_rows<<<blocks_for(length), threads>>>(
        d_gamma0, d_two_pi_t, d_stage_reciprocals, length, stages,
        d_gamma_rows);
    copy_add_g_error<<<blocks_for(row_cells), threads>>>(
        d_gamma_rows, d_G_positive, row_cells, g_error);

    // arb_zeta.cpp::G_k: negative transform, scale, error, alternating sign,
    // and removal of coefficients above N1/2.
    transform(d_G_positive, d_G_negative, d_roots, stages, length,
              reduced_length, true);
    postprocess_G<<<blocks_for(row_cells), threads>>>(
        d_G_negative, length, stages, G_error);

    // arb_zeta.cpp::my_convolve: two positive transforms, pointwise product,
    // one negative transform, and normalization by N1.
    transform(d_G_negative, d_G_positive, d_roots, stages, length,
              reduced_length, false);
    transform(d_skn, d_S_positive, d_roots, stages, length,
              reduced_length, false);
    pointwise_products<<<blocks_for(row_cells), threads>>>(
        d_G_positive, d_S_positive, d_products, row_cells);
    transform(d_products, d_convolutions, d_roots, stages, length,
              reduced_length, true);
    normalize_and_taylor_sum<<<blocks_for(length / 2U), threads>>>(
        d_convolutions, d_retained, length, stages, reciprocal_length);

    initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads>>>(
        d_retained, d_half_spectrum, length, fmax_error, fhatsum_error,
        taylor_error, fhat_transform_error);
    hermidft_preprocess<<<blocks_for(reduced_length), threads>>>(
        d_half_spectrum, d_hermi_pre, d_roots, omega, reduced_length);
    transform(d_hermi_pre, d_hermi_fft, d_roots, 1U, reduced_length,
              reduced_length, false);
    interleave_hermidft_output<<<blocks_for(reduced_length), threads>>>(
        d_hermi_fft, d_samples, reduced_length);
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  CUDA_CHECK(cudaGetLastError());
  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));

  std::vector<RealInterval> samples(sample_count);
  CUDA_CHECK(cudaMemcpy(samples.data(), d_samples,
                        samples.size() * sizeof(RealInterval),
                        cudaMemcpyDeviceToHost));
  bool finite = true;
  std::uint64_t sign_ambiguous = 0U;
  double maximum_width = 0.0;
  for (const RealInterval sample : samples) {
    finite = finite && std::isfinite(sample.lo) && std::isfinite(sample.hi) &&
             sample.lo <= sample.hi;
    if (sample.lo <= 0.0 && sample.hi >= 0.0) ++sign_ambiguous;
    maximum_width = std::max(maximum_width, sample.hi - sample.lo);
  }

  bool kat_contained = true;
  double maximum_kat_distance = 0.0;
  if (!options.source_shape && !options.source_errors && length <= 32U) {
    const std::vector<long double> reference = reference_samples(options, host);
    for (std::size_t index = 0; index < samples.size(); ++index) {
      const long double value = reference[index];
      kat_contained = kat_contained &&
          static_cast<long double>(samples[index].lo) <= value &&
          value <= static_cast<long double>(samples[index].hi);
      const long double midpoint =
          (static_cast<long double>(samples[index].lo) +
           static_cast<long double>(samples[index].hi)) / 2.0L;
      maximum_kat_distance = std::max(
          maximum_kat_distance,
          static_cast<double>(fabsl(midpoint - value)));
    }
  }

  const std::uint64_t batched_butterflies =
      4ULL * stages * (length / 2ULL) * exact_log2(length);
  const std::uint64_t final_butterflies =
      static_cast<std::uint64_t>(reduced_length / 2U) *
      exact_log2(reduced_length);
  const std::uint64_t butterflies_per_run =
      batched_butterflies + final_butterflies;
  const double elapsed_seconds = static_cast<double>(elapsed_ms) / 1000.0;
  const double runs_per_second = options.repetitions / elapsed_seconds;
  const double butterflies_per_second =
      static_cast<double>(butterflies_per_run) * options.repetitions /
      elapsed_seconds;

  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-windowed-semantic.v1\""
            << ",\"claim_scope\":\"source_semantic_transform_from_certified_input_boxes_not_a_zeta_certificate\""
            << ",\"upstream_commit\":\"42b21426718e542daa2b006dc05ea2d7f26426e6\""
            << ",\"actual_zeta_inputs\":false"
            << ",\"source_shape\":" << (options.source_shape ? "true" : "false")
            << ",\"source_error_disks\":" << (options.source_errors ? "true" : "false")
            << ",\"device\":\"" << properties.name << "\""
            << ",\"compute_capability\":\"" << properties.major << "."
            << properties.minor << "\""
            << ",\"convolution_length\":" << length
            << ",\"taylor_terms\":" << stages
            << ",\"repetitions\":" << options.repetitions
            << ",\"negative_G_transforms\":" << stages
            << ",\"positive_convolution_transforms\":" << 2U * stages
            << ",\"negative_inverse_transforms\":" << stages
            << ",\"positive_hermidft_transforms\":1"
            << ",\"butterflies_per_run\":" << butterflies_per_run
            << ",\"pointwise_products_per_run\":" << row_cells
            << ",\"elapsed_seconds\":" << elapsed_seconds
            << ",\"semantic_runs_per_second\":" << runs_per_second
            << ",\"butterflies_per_second\":" << butterflies_per_second
            << ",\"all_output_intervals_finite\":" << (finite ? "true" : "false")
            << ",\"synthetic_sign_ambiguous_samples\":" << sign_ambiguous
            << ",\"maximum_output_width\":" << maximum_width
            << ",\"small_kat_contained\":" << (kat_contained ? "true" : "false")
            << ",\"maximum_kat_midpoint_distance\":" << maximum_kat_distance
            << ",\"output_fnv1a64\":\"" << std::hex << std::setw(16)
            << std::setfill('0') << fnv1a(samples) << "\"}\n";

  CUDA_CHECK(cudaEventDestroy(start));
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaFree(d_gamma0));
  CUDA_CHECK(cudaFree(d_two_pi_t));
  CUDA_CHECK(cudaFree(d_stage_reciprocals));
  CUDA_CHECK(cudaFree(d_skn));
  CUDA_CHECK(cudaFree(d_gamma_rows));
  CUDA_CHECK(cudaFree(d_G_negative));
  CUDA_CHECK(cudaFree(d_G_positive));
  CUDA_CHECK(cudaFree(d_S_positive));
  CUDA_CHECK(cudaFree(d_products));
  CUDA_CHECK(cudaFree(d_convolutions));
  CUDA_CHECK(cudaFree(d_retained));
  CUDA_CHECK(cudaFree(d_half_spectrum));
  CUDA_CHECK(cudaFree(d_hermi_pre));
  CUDA_CHECK(cudaFree(d_hermi_fft));
  CUDA_CHECK(cudaFree(d_roots));
  CUDA_CHECK(cudaFree(d_samples));
  return finite && kat_contained ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-windowed-semantic: " << error.what()
              << '\n';
    return 2;
  }
}

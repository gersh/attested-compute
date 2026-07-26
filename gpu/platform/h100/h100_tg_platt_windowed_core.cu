// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Production-shape benchmark for the compact Gamma-row synthesis and bucketed
// Taylor accumulator in the Platt--Trudgian windowed zeta computation.  It
// implements the exact M=768000, K=23, N1=32768 geometry with directed
// binary64 intervals and benchmarks the source's exact four batched N1 FFT
// passes plus final length-65536 pass.  The source-compatible end-to-end runner
// still needs the convolution dependencies, interpolation, zero isolation,
// and Turing stages; this executable is deliberately fail-honest about that
// boundary in its JSON report.

#include "sparkinterval/tg_platt_windowed.hpp"
#include "sparkinterval/tg_platt_dd_accumulator.hpp"
#include "sparkinterval/sha256.hpp"

#include <cuda_runtime.h>
#include <mpfr.h>

#include <algorithm>
#include <bit>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
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

struct MpfrValue {
  mpfr_t value;
  explicit MpfrValue(mpfr_prec_t precision = 320) {
    mpfr_init2(value, precision);
  }
  ~MpfrValue() { mpfr_clear(value); }
  MpfrValue(const MpfrValue&) = delete;
  MpfrValue& operator=(const MpfrValue&) = delete;
};

struct Options {
  std::uint32_t terms = pw::kSourceTerms;
  std::uint32_t stages = pw::kTaylorTerms;
  std::uint32_t blocks = 2U;
  std::uint32_t repetitions = 3U;
  std::uint32_t reanchor_blocks = 256U;
  std::uint32_t fft_passes = 4U;
  std::uint32_t dd_source_blocks = 0U;
  std::uint64_t dd_source_start_block = 0U;
  bool source_geometry = false;
  bool gamma_synthesis = false;
  std::string export_source_packet;
  std::string export_source_dd_packet;
  std::string dd_gamma_row;
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

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    auto value_after = [&](const char* prefix) -> const char* {
      const std::string key(prefix);
      if (argument.rfind(key, 0) != 0) return nullptr;
      return argv[index] + key.size();
    };
    if (const char* value = value_after("--terms=")) {
      const auto parsed = parse_unsigned(value, "term count");
      if (parsed == 0U || parsed > pw::kSourceTerms) {
        throw std::runtime_error("term count is outside 1..768000");
      }
      options.terms = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--stages=")) {
      const auto parsed = parse_unsigned(value, "Taylor stage count");
      if (parsed == 0U || parsed > pw::kTaylorTerms) {
        throw std::runtime_error("Taylor stage count is outside 1..23");
      }
      options.stages = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--blocks=")) {
      const auto parsed = parse_unsigned(value, "block count");
      if (parsed == 0U || parsed > 4096U) {
        throw std::runtime_error("block count is outside 1..4096");
      }
      options.blocks = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--repetitions=")) {
      const auto parsed = parse_unsigned(value, "repetition count");
      if (parsed == 0U || parsed > 1000U) {
        throw std::runtime_error("repetition count is outside 1..1000");
      }
      options.repetitions = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--reanchor-blocks=")) {
      const auto parsed = parse_unsigned(value, "phase re-anchor interval");
      if (parsed == 0U || parsed > 4096U) {
        throw std::runtime_error(
            "phase re-anchor interval is outside 1..4096");
      }
      options.reanchor_blocks = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--fft-passes=")) {
      const auto parsed = parse_unsigned(value, "batched FFT pass count");
      if (parsed > 4U) {
        throw std::runtime_error("batched FFT pass count is outside 0..4");
      }
      options.fft_passes = static_cast<std::uint32_t>(parsed);
    } else if (const char* value = value_after("--dd-source-blocks=")) {
      const auto parsed = parse_unsigned(value, "two-limb source block count");
      if (parsed == 0U || parsed > (1U << 24U)) {
        throw std::runtime_error(
            "two-limb source block count is outside 1..16777216");
      }
      options.dd_source_blocks = static_cast<std::uint32_t>(parsed);
    } else if (const char* value =
                   value_after("--dd-source-start-block=")) {
      const auto parsed = parse_unsigned(value, "two-limb source start block");
      if (parsed >= pw::kFullBlockCount) {
        throw std::runtime_error(
            "two-limb source start block is outside the full campaign");
      }
      options.dd_source_start_block = parsed;
    } else if (argument == "--source-geometry") {
      options.source_geometry = true;
    } else if (argument == "--gamma-synthesis") {
      options.gamma_synthesis = true;
    } else if (const char* value = value_after("--export-source-packet=")) {
      if (*value == '\0') {
        throw std::runtime_error("source packet path is empty");
      }
      options.export_source_packet = value;
    } else if (const char* value =
                   value_after("--export-source-dd-packet=")) {
      if (*value == '\0') {
        throw std::runtime_error("two-limb source packet path is empty");
      }
      options.export_source_dd_packet = value;
    } else if (const char* value = value_after("--dd-gamma-row=")) {
      if (*value == '\0') {
        throw std::runtime_error("two-limb Gamma row path is empty");
      }
      options.dd_gamma_row = value;
    } else {
      throw std::runtime_error("unknown option: " + argument);
    }
  }
  if (options.gamma_synthesis && !options.source_geometry) {
    throw std::runtime_error(
        "--gamma-synthesis requires --source-geometry");
  }
  if (!options.export_source_packet.empty() &&
      (!options.source_geometry || !options.gamma_synthesis ||
       options.blocks != 1U || options.repetitions != 1U ||
       options.stages != pw::kTaylorTerms)) {
    throw std::runtime_error(
        "source packet export requires --source-geometry, "
        "--gamma-synthesis, --blocks=1, --repetitions=1, and --stages=23");
  }
  if (!options.export_source_dd_packet.empty() &&
      (!options.source_geometry || options.blocks != 1U ||
       options.repetitions != 1U || options.stages != pw::kTaylorTerms ||
       options.dd_gamma_row.empty())) {
    throw std::runtime_error(
        "two-limb source packet export requires --source-geometry, "
        "--blocks=1, --repetitions=1, --stages=23, and --dd-gamma-row");
  }
  if (!options.dd_gamma_row.empty() &&
      options.export_source_dd_packet.empty()) {
    throw std::runtime_error(
        "--dd-gamma-row requires --export-source-dd-packet");
  }
  if (options.dd_source_blocks != 0U && !options.source_geometry) {
    throw std::runtime_error(
        "--dd-source-blocks requires --source-geometry");
  }
  if (options.dd_source_blocks == 0U &&
      options.dd_source_start_block != 0U) {
    throw std::runtime_error(
        "--dd-source-start-block requires --dd-source-blocks");
  }
  if (options.dd_source_blocks != 0U &&
      options.dd_source_start_block + options.dd_source_blocks >
          pw::kFullBlockCount) {
    throw std::runtime_error(
        "two-limb source block shard exceeds the full campaign");
  }
  if (options.dd_source_blocks != 0U &&
      !options.export_source_dd_packet.empty()) {
    throw std::runtime_error(
        "--dd-source-blocks and --export-source-dd-packet are separate "
        "streaming and first-window packet modes");
  }
  return options;
}

struct HostTerms {
  std::vector<std::uint32_t> one_based_ns;
  std::vector<std::uint32_t> offsets;
  std::vector<std::uint32_t> active_buckets;
  std::vector<RealInterval> residuals;
  std::vector<RealInterval> amplitudes;
  std::vector<pw::FixedTurn192> fixed_turns;
  std::vector<ComplexInterval> values;
  std::vector<ComplexInterval> phase_steps;
  std::vector<pw::RealDisk106> narrow_residuals;
  std::vector<pw::ComplexDisk106> narrow_values;
  std::vector<pw::RealDisk106> narrow_amplitudes;
};

// The benchmark KAT and the production all-window stream use the same
// naturally aligned, statically sized record.  Keeping one shared type avoids
// a second unchecked byte-to-kernel interpretation at the GPU boundary.
using GammaTaylorProjection = pw::GammaTaylorStreamRecord;
static_assert(sizeof(GammaTaylorProjection) == 264U);

// KAT projection emitted by sparkinterval-tg-platt-gamma-taylor at the first
// source window centre, FLINT 3.6.0, 256 bits, degree 6.  Production streams a
// separately hash-bound packet for every window; this fixed packet lets the
// GPU benchmark and known-answer test exercise the exact synthesis dataflow.
GammaTaylorProjection source_lower_gamma_projection() {
  return {
      {{-0x1.2a82dda76b818p+2, -0x1.2a82dda76b817p+2},
       {-0x1.b7cdfc2998f46p-36, -0x1.b7cdfc2998f45p-36},
       {0x1.79ca0e4a3ecb8p-70, 0x1.79ca0e4a3ecb9p-70},
       {-0x1.b0b0fb9f5d863p-104, -0x1.b0b0fb9f5d862p-104},
       {0x1.16c25ec89d755p-137, 0x1.16c25ec89d756p-137},
       {-0x1.7f1fb09d3e1edp-171, -0x1.7f1fb09d3e1ecp-171}},
      {{0x1.8d5a4381659e8p+36, 0x1.8d5a4381659e9p+36},
       {0x1.6552c13834fedp+3, 0x1.6552c13834feep+3},
       {0x1.b7cdfc2998f45p-36, 0x1.b7cdfc2998f46p-36},
       {-0x1.f7b8130da90f6p-71, -0x1.f7b8130da90f5p-71},
       {0x1.b0b0fb9f5d862p-105, 0x1.b0b0fb9f5d863p-105},
       {-0x1.be03cada95889p-139, -0x1.be03cada95888p-139}},
      {0x32e78fa208d9282fULL, 0x31fea3aef4924eb6ULL,
       0xc7e64ca1720e02e1ULL},
      {0xbe0f1ad116ce6d63ULL, 0x4847b631c746ec93ULL,
       0x4aa43d8dfc8a1c3aULL},
      0x1.6c56d7ec36824p-194,
      0x1.48cbe6daaf2abp-191,
      0x1.466e52bf5ef32p-104};
}

double outward_down(mpfr_srcptr value) {
  double result = mpfr_get_d(value, MPFR_RNDD);
  // The source initializer is a benchmark/audit aid, not the production
  // phase certificate.  Four extra ulps dominate the 320-bit construction
  // error after multiplication by heights through 3.01e12.
  for (unsigned i = 0; i < 4U; ++i) {
    result = std::nextafter(result, -std::numeric_limits<double>::infinity());
  }
  return result;
}

double outward_up(mpfr_srcptr value) {
  double result = mpfr_get_d(value, MPFR_RNDU);
  for (unsigned i = 0; i < 4U; ++i) {
    result = std::nextafter(result, std::numeric_limits<double>::infinity());
  }
  return result;
}

struct DDRealProjection {
  pw::DoubleDouble center;
  double radius;
};

DDRealProjection project_mpfr_interval_dd(mpfr_srcptr lower,
                                          mpfr_srcptr upper) {
  MpfrValue midpoint, high, low, center, left_error, right_error, radius;
  mpfr_add(midpoint.value, lower, upper, MPFR_RNDN);
  mpfr_div_2ui(midpoint.value, midpoint.value, 1U, MPFR_RNDN);
  const double hi = mpfr_get_d(midpoint.value, MPFR_RNDN);
  mpfr_set_d(high.value, hi, MPFR_RNDN);
  mpfr_sub(low.value, midpoint.value, high.value, MPFR_RNDN);
  const double lo = mpfr_get_d(low.value, MPFR_RNDN);
  mpfr_set_d(center.value, hi, MPFR_RNDN);
  mpfr_add_d(center.value, center.value, lo, MPFR_RNDN);
  mpfr_sub(left_error.value, center.value, lower, MPFR_RNDU);
  mpfr_abs(left_error.value, left_error.value, MPFR_RNDU);
  mpfr_sub(right_error.value, upper, center.value, MPFR_RNDU);
  mpfr_abs(right_error.value, right_error.value, MPFR_RNDU);
  mpfr_max(radius.value, left_error.value, right_error.value, MPFR_RNDU);
  return {{hi, lo}, mpfr_get_d(radius.value, MPFR_RNDU)};
}

void multiply_by_positive_interval(mpfr_ptr output_lower,
                                   mpfr_ptr output_upper,
                                   mpfr_srcptr value_lower,
                                   mpfr_srcptr value_upper,
                                   mpfr_srcptr scale_lower,
                                   mpfr_srcptr scale_upper) {
  if (mpfr_sgn(value_lower) >= 0) {
    mpfr_mul(output_lower, value_lower, scale_lower, MPFR_RNDD);
    mpfr_mul(output_upper, value_upper, scale_upper, MPFR_RNDU);
  } else if (mpfr_sgn(value_upper) <= 0) {
    mpfr_mul(output_lower, value_lower, scale_upper, MPFR_RNDD);
    mpfr_mul(output_upper, value_upper, scale_lower, MPFR_RNDU);
  } else {
    mpfr_mul(output_lower, value_lower, scale_upper, MPFR_RNDD);
    mpfr_mul(output_upper, value_upper, scale_upper, MPFR_RNDU);
  }
}

// Rigorous first-window term disk.  The exact logarithm interval is scaled
// before trig evaluation; sin/cos are widened by the argument half-width via
// their global 1-Lipschitz bound, then multiplied by the positive amplitude
// interval.  No binary64 source-cell uncertainty is discarded.
pw::ComplexDisk106 narrow_source_value(
    mpfr_srcptr logarithm_lo, mpfr_srcptr logarithm_hi,
    mpfr_srcptr amplitude_lo, mpfr_srcptr amplitude_hi,
    std::uint64_t height) {
  MpfrValue argument_lo, argument_hi, midpoint, phase_error;
  MpfrValue first_error, second_error;
  mpfr_mul_ui(argument_lo.value, logarithm_hi, height, MPFR_RNDU);
  mpfr_neg(argument_lo.value, argument_lo.value, MPFR_RNDD);
  mpfr_mul_ui(argument_hi.value, logarithm_lo, height, MPFR_RNDD);
  mpfr_neg(argument_hi.value, argument_hi.value, MPFR_RNDU);
  mpfr_add(midpoint.value, argument_lo.value, argument_hi.value, MPFR_RNDN);
  mpfr_div_2ui(midpoint.value, midpoint.value, 1U, MPFR_RNDN);
  mpfr_sub(first_error.value, midpoint.value, argument_lo.value, MPFR_RNDU);
  mpfr_sub(second_error.value, argument_hi.value, midpoint.value, MPFR_RNDU);
  mpfr_max(phase_error.value, first_error.value, second_error.value,
           MPFR_RNDU);

  MpfrValue sine_lo, sine_hi, cosine_lo, cosine_hi;
  mpfr_sin(sine_lo.value, midpoint.value, MPFR_RNDD);
  mpfr_sin(sine_hi.value, midpoint.value, MPFR_RNDU);
  mpfr_cos(cosine_lo.value, midpoint.value, MPFR_RNDD);
  mpfr_cos(cosine_hi.value, midpoint.value, MPFR_RNDU);
  mpfr_sub(sine_lo.value, sine_lo.value, phase_error.value, MPFR_RNDD);
  mpfr_add(sine_hi.value, sine_hi.value, phase_error.value, MPFR_RNDU);
  mpfr_sub(cosine_lo.value, cosine_lo.value, phase_error.value, MPFR_RNDD);
  mpfr_add(cosine_hi.value, cosine_hi.value, phase_error.value, MPFR_RNDU);

  MpfrValue re_lo, re_hi, im_lo, im_hi;
  multiply_by_positive_interval(re_lo.value, re_hi.value,
                                cosine_lo.value, cosine_hi.value,
                                amplitude_lo, amplitude_hi);
  multiply_by_positive_interval(im_lo.value, im_hi.value,
                                sine_lo.value, sine_hi.value,
                                amplitude_lo, amplitude_hi);
  const DDRealProjection re =
      project_mpfr_interval_dd(re_lo.value, re_hi.value);
  const DDRealProjection im =
      project_mpfr_interval_dd(im_lo.value, im_hi.value);
  MpfrValue re_radius, im_radius, radius;
  mpfr_set_d(re_radius.value, re.radius, MPFR_RNDN);
  mpfr_set_d(im_radius.value, im.radius, MPFR_RNDN);
  mpfr_mul(radius.value, re_radius.value, re_radius.value, MPFR_RNDU);
  mpfr_fma(radius.value, im_radius.value, im_radius.value, radius.value,
           MPFR_RNDU);
  mpfr_sqrt(radius.value, radius.value, MPFR_RNDU);
  return {re.center, im.center, mpfr_get_d(radius.value, MPFR_RNDU)};
}

struct SourceDDTrigData {
  std::vector<pw::RealDisk106> sine_coefficients;
  std::vector<pw::RealDisk106> cosine_coefficients;
  pw::RealDisk106 two_pi;
};

SourceDDTrigData initialize_source_dd_trig_data() {
  constexpr unsigned kCoefficientCount = 20U;
  SourceDDTrigData result;
  result.sine_coefficients.reserve(kCoefficientCount);
  result.cosine_coefficients.reserve(kCoefficientCount);
  MpfrValue factorial, lower, upper;
  auto coefficient = [&](unsigned degree, bool negative) {
    mpfr_fac_ui(factorial.value, degree, MPFR_RNDN);
    mpfr_ui_div(lower.value, 1U, factorial.value, MPFR_RNDD);
    mpfr_ui_div(upper.value, 1U, factorial.value, MPFR_RNDU);
    if (negative) {
      MpfrValue neg_lower, neg_upper;
      mpfr_neg(neg_lower.value, upper.value, MPFR_RNDD);
      mpfr_neg(neg_upper.value, lower.value, MPFR_RNDU);
      const DDRealProjection projected =
          project_mpfr_interval_dd(neg_lower.value, neg_upper.value);
      return pw::RealDisk106{projected.center, projected.radius};
    }
    const DDRealProjection projected =
        project_mpfr_interval_dd(lower.value, upper.value);
    return pw::RealDisk106{projected.center, projected.radius};
  };
  for (unsigned index = 0U; index < kCoefficientCount; ++index) {
    result.sine_coefficients.push_back(
        coefficient(2U * index + 1U, (index & 1U) != 0U));
    result.cosine_coefficients.push_back(
        coefficient(2U * index, (index & 1U) != 0U));
  }
  MpfrValue pi_lo, pi_hi, two_pi_lo, two_pi_hi;
  mpfr_const_pi(pi_lo.value, MPFR_RNDD);
  mpfr_const_pi(pi_hi.value, MPFR_RNDU);
  mpfr_mul_2ui(two_pi_lo.value, pi_lo.value, 1U, MPFR_RNDD);
  mpfr_mul_2ui(two_pi_hi.value, pi_hi.value, 1U, MPFR_RNDU);
  const DDRealProjection two_pi =
      project_mpfr_interval_dd(two_pi_lo.value, two_pi_hi.value);
  result.two_pi = {two_pi.center, two_pi.radius};
  return result;
}

// Recomputes the exact source term independently with directed MPFR bounds
// and returns the radius about the CUDA center needed to contain it.  The
// analytic estimate
//
//   |a exp(i theta) - a0 exp(i theta0)|
//     <= |a-a0| + a_max |theta-theta0|
//
// avoids demanding containment of impossible corners from a Cartesian box.
// Passing this gate checks the CUDA Q192 disk against the source expression;
// it is still a KAT, not a formal proof of the CUDA instruction sequence.
double source_dd_required_truth_radius(
    const pw::ComplexDisk106& outer, std::uint32_t one_based_n,
    std::uint64_t height) {
  MpfrValue pi_lo, pi_hi, log_pi_lo, log_pi_hi, log_n_lo, log_n_hi;
  MpfrValue log_lo, log_hi, angle_lo, angle_hi, angle_mid, phase_error;
  MpfrValue amplitude_lo, amplitude_hi, amplitude_mid, amplitude_error;
  MpfrValue sine_lo, sine_hi, cosine_lo, cosine_hi;
  MpfrValue reference_re_lo, reference_re_hi;
  MpfrValue reference_im_lo, reference_im_hi;
  MpfrValue outer_re, outer_im, temporary, first, second;
  MpfrValue delta_re, delta_im, distance, analytic_error;
  mpfr_const_pi(pi_lo.value, MPFR_RNDD);
  mpfr_const_pi(pi_hi.value, MPFR_RNDU);
  mpfr_log(log_pi_lo.value, pi_lo.value, MPFR_RNDD);
  mpfr_log(log_pi_hi.value, pi_hi.value, MPFR_RNDU);
  mpfr_div_2ui(log_pi_lo.value, log_pi_lo.value, 1U, MPFR_RNDD);
  mpfr_div_2ui(log_pi_hi.value, log_pi_hi.value, 1U, MPFR_RNDU);
  mpfr_log_ui(log_n_lo.value, one_based_n, MPFR_RNDD);
  mpfr_log_ui(log_n_hi.value, one_based_n, MPFR_RNDU);
  mpfr_add(log_lo.value, log_n_lo.value, log_pi_lo.value, MPFR_RNDD);
  mpfr_add(log_hi.value, log_n_hi.value, log_pi_hi.value, MPFR_RNDU);
  mpfr_mul_ui(angle_lo.value, log_hi.value, height, MPFR_RNDU);
  mpfr_neg(angle_lo.value, angle_lo.value, MPFR_RNDD);
  mpfr_mul_ui(angle_hi.value, log_lo.value, height, MPFR_RNDD);
  mpfr_neg(angle_hi.value, angle_hi.value, MPFR_RNDU);
  mpfr_add(angle_mid.value, angle_lo.value, angle_hi.value, MPFR_RNDN);
  mpfr_div_2ui(angle_mid.value, angle_mid.value, 1U, MPFR_RNDN);
  mpfr_sub(first.value, angle_mid.value, angle_lo.value, MPFR_RNDU);
  mpfr_sub(second.value, angle_hi.value, angle_mid.value, MPFR_RNDU);
  mpfr_max(phase_error.value, first.value, second.value, MPFR_RNDU);

  mpfr_set_ui(amplitude_lo.value, one_based_n, MPFR_RNDN);
  mpfr_sqrt(amplitude_lo.value, amplitude_lo.value, MPFR_RNDU);
  mpfr_ui_div(amplitude_lo.value, 1U, amplitude_lo.value, MPFR_RNDD);
  mpfr_set_ui(amplitude_hi.value, one_based_n, MPFR_RNDN);
  mpfr_sqrt(amplitude_hi.value, amplitude_hi.value, MPFR_RNDD);
  mpfr_ui_div(amplitude_hi.value, 1U, amplitude_hi.value, MPFR_RNDU);
  mpfr_add(amplitude_mid.value, amplitude_lo.value, amplitude_hi.value,
           MPFR_RNDN);
  mpfr_div_2ui(amplitude_mid.value, amplitude_mid.value, 1U, MPFR_RNDN);
  mpfr_sub(first.value, amplitude_mid.value, amplitude_lo.value,
           MPFR_RNDU);
  mpfr_sub(second.value, amplitude_hi.value, amplitude_mid.value,
           MPFR_RNDU);
  mpfr_max(amplitude_error.value, first.value, second.value, MPFR_RNDU);

  mpfr_sin(sine_lo.value, angle_mid.value, MPFR_RNDD);
  mpfr_sin(sine_hi.value, angle_mid.value, MPFR_RNDU);
  mpfr_cos(cosine_lo.value, angle_mid.value, MPFR_RNDD);
  mpfr_cos(cosine_hi.value, angle_mid.value, MPFR_RNDU);
  multiply_by_positive_interval(reference_re_lo.value,
                                reference_re_hi.value, cosine_lo.value,
                                cosine_hi.value, amplitude_mid.value,
                                amplitude_mid.value);
  multiply_by_positive_interval(reference_im_lo.value,
                                reference_im_hi.value, sine_lo.value,
                                sine_hi.value, amplitude_mid.value,
                                amplitude_mid.value);

  mpfr_set_d(outer_re.value, outer.real.hi, MPFR_RNDN);
  mpfr_set_d(temporary.value, outer.real.lo, MPFR_RNDN);
  mpfr_add(outer_re.value, outer_re.value, temporary.value, MPFR_RNDN);
  mpfr_set_d(outer_im.value, outer.imaginary.hi, MPFR_RNDN);
  mpfr_set_d(temporary.value, outer.imaginary.lo, MPFR_RNDN);
  mpfr_add(outer_im.value, outer_im.value, temporary.value, MPFR_RNDN);
  mpfr_sub(first.value, outer_re.value, reference_re_lo.value, MPFR_RNDU);
  mpfr_abs(first.value, first.value, MPFR_RNDU);
  mpfr_sub(second.value, outer_re.value, reference_re_hi.value, MPFR_RNDU);
  mpfr_abs(second.value, second.value, MPFR_RNDU);
  mpfr_max(delta_re.value, first.value, second.value, MPFR_RNDU);
  mpfr_sub(first.value, outer_im.value, reference_im_lo.value, MPFR_RNDU);
  mpfr_abs(first.value, first.value, MPFR_RNDU);
  mpfr_sub(second.value, outer_im.value, reference_im_hi.value, MPFR_RNDU);
  mpfr_abs(second.value, second.value, MPFR_RNDU);
  mpfr_max(delta_im.value, first.value, second.value, MPFR_RNDU);
  mpfr_mul(distance.value, delta_re.value, delta_re.value, MPFR_RNDU);
  mpfr_fma(distance.value, delta_im.value, delta_im.value, distance.value,
           MPFR_RNDU);
  mpfr_sqrt(distance.value, distance.value, MPFR_RNDU);
  mpfr_mul(analytic_error.value, amplitude_hi.value, phase_error.value,
           MPFR_RNDU);
  mpfr_add(analytic_error.value, analytic_error.value,
           amplitude_error.value, MPFR_RNDU);
  mpfr_add(distance.value, distance.value, analytic_error.value,
           MPFR_RNDU);
  return mpfr_get_d(distance.value, MPFR_RNDU);
}

void set_dd_interval(mpfr_ptr lower, mpfr_ptr upper,
                     pw::DoubleDouble value) {
  mpfr_set_d(lower, value.hi, MPFR_RNDN);
  mpfr_add_d(lower, lower, value.lo, MPFR_RNDD);
  mpfr_set_d(upper, value.hi, MPFR_RNDN);
  mpfr_add_d(upper, upper, value.lo, MPFR_RNDU);
}

void multiply_intervals(mpfr_ptr output_lower, mpfr_ptr output_upper,
                        mpfr_srcptr x_lower, mpfr_srcptr x_upper,
                        mpfr_srcptr y_lower, mpfr_srcptr y_upper) {
  MpfrValue p0, p1, p2, p3;
  mpfr_mul(p0.value, x_lower, y_lower, MPFR_RNDD);
  mpfr_mul(p1.value, x_lower, y_upper, MPFR_RNDD);
  mpfr_mul(p2.value, x_upper, y_lower, MPFR_RNDD);
  mpfr_mul(p3.value, x_upper, y_upper, MPFR_RNDD);
  mpfr_min(output_lower, p0.value, p1.value, MPFR_RNDD);
  mpfr_min(output_lower, output_lower, p2.value, MPFR_RNDD);
  mpfr_min(output_lower, output_lower, p3.value, MPFR_RNDD);
  mpfr_mul(p0.value, x_lower, y_lower, MPFR_RNDU);
  mpfr_mul(p1.value, x_lower, y_upper, MPFR_RNDU);
  mpfr_mul(p2.value, x_upper, y_lower, MPFR_RNDU);
  mpfr_mul(p3.value, x_upper, y_upper, MPFR_RNDU);
  mpfr_max(output_upper, p0.value, p1.value, MPFR_RNDU);
  mpfr_max(output_upper, output_upper, p2.value, MPFR_RNDU);
  mpfr_max(output_upper, output_upper, p3.value, MPFR_RNDU);
}

void absolute_interval_upper(mpfr_ptr output, mpfr_srcptr lower,
                             mpfr_srcptr upper) {
  MpfrValue left, right;
  mpfr_abs(left.value, lower, MPFR_RNDU);
  mpfr_abs(right.value, upper, MPFR_RNDU);
  mpfr_max(output, left.value, right.value, MPFR_RNDU);
}

// Independent directed-MPFR replay of one bucket/stage accumulator input.
// It computes an interval for the exact DD-centre sum and a Euclidean input
// uncertainty radius, then returns the radius required about `output`.
// Passing this check for both kernels is a differential KAT, not a proof of
// the CUDA instruction sequence.
double source_dd_accumulator_required_radius(
    const std::vector<pw::ComplexDisk106>& values,
    const std::vector<pw::RealDisk106>& powers,
    const pw::ComplexDisk106& output) {
  if (!powers.empty() && powers.size() != values.size()) {
    throw std::runtime_error("MPFR accumulator KAT input-size mismatch");
  }
  MpfrValue sum_re_lo, sum_re_hi, sum_im_lo, sum_im_hi, sum_radius;
  mpfr_set_zero(sum_re_lo.value, 1);
  mpfr_set_zero(sum_re_hi.value, 1);
  mpfr_set_zero(sum_im_lo.value, 1);
  mpfr_set_zero(sum_im_hi.value, 1);
  mpfr_set_zero(sum_radius.value, 1);
  MpfrValue re_lo, re_hi, im_lo, im_hi, power_lo, power_hi;
  MpfrValue contribution_re_lo, contribution_re_hi;
  MpfrValue contribution_im_lo, contribution_im_hi;
  MpfrValue re_abs, im_abs, value_norm, power_abs;
  MpfrValue value_radius, power_radius, contribution_radius;
  MpfrValue first, second;
  for (std::size_t index = 0; index < values.size(); ++index) {
    const pw::ComplexDisk106& value = values[index];
    set_dd_interval(re_lo.value, re_hi.value, value.real);
    set_dd_interval(im_lo.value, im_hi.value, value.imaginary);
    mpfr_set_d(value_radius.value, value.radius, MPFR_RNDU);
    if (powers.empty()) {
      mpfr_set(contribution_re_lo.value, re_lo.value, MPFR_RNDD);
      mpfr_set(contribution_re_hi.value, re_hi.value, MPFR_RNDU);
      mpfr_set(contribution_im_lo.value, im_lo.value, MPFR_RNDD);
      mpfr_set(contribution_im_hi.value, im_hi.value, MPFR_RNDU);
      mpfr_set(contribution_radius.value, value_radius.value, MPFR_RNDU);
    } else {
      const pw::RealDisk106& power = powers[index];
      set_dd_interval(power_lo.value, power_hi.value, power.center);
      multiply_intervals(contribution_re_lo.value,
                         contribution_re_hi.value, re_lo.value,
                         re_hi.value, power_lo.value, power_hi.value);
      multiply_intervals(contribution_im_lo.value,
                         contribution_im_hi.value, im_lo.value,
                         im_hi.value, power_lo.value, power_hi.value);
      absolute_interval_upper(re_abs.value, re_lo.value, re_hi.value);
      absolute_interval_upper(im_abs.value, im_lo.value, im_hi.value);
      mpfr_mul(value_norm.value, re_abs.value, re_abs.value, MPFR_RNDU);
      mpfr_fma(value_norm.value, im_abs.value, im_abs.value,
               value_norm.value, MPFR_RNDU);
      mpfr_sqrt(value_norm.value, value_norm.value, MPFR_RNDU);
      absolute_interval_upper(power_abs.value, power_lo.value,
                              power_hi.value);
      mpfr_set_d(power_radius.value, power.radius, MPFR_RNDU);
      mpfr_mul(contribution_radius.value, value_norm.value,
               power_radius.value, MPFR_RNDU);
      mpfr_fma(contribution_radius.value, power_abs.value,
               value_radius.value, contribution_radius.value,
               MPFR_RNDU);
      mpfr_fma(contribution_radius.value, value_radius.value,
               power_radius.value, contribution_radius.value,
               MPFR_RNDU);
    }
    mpfr_add(sum_re_lo.value, sum_re_lo.value,
             contribution_re_lo.value, MPFR_RNDD);
    mpfr_add(sum_re_hi.value, sum_re_hi.value,
             contribution_re_hi.value, MPFR_RNDU);
    mpfr_add(sum_im_lo.value, sum_im_lo.value,
             contribution_im_lo.value, MPFR_RNDD);
    mpfr_add(sum_im_hi.value, sum_im_hi.value,
             contribution_im_hi.value, MPFR_RNDU);
    mpfr_add(sum_radius.value, sum_radius.value,
             contribution_radius.value, MPFR_RNDU);
  }

  MpfrValue output_re_lo, output_re_hi, output_im_lo, output_im_hi;
  MpfrValue delta_re, delta_im, distance;
  set_dd_interval(output_re_lo.value, output_re_hi.value, output.real);
  set_dd_interval(output_im_lo.value, output_im_hi.value, output.imaginary);
  mpfr_sub(first.value, output_re_lo.value, sum_re_hi.value, MPFR_RNDD);
  mpfr_abs(first.value, first.value, MPFR_RNDU);
  mpfr_sub(second.value, output_re_hi.value, sum_re_lo.value, MPFR_RNDU);
  mpfr_abs(second.value, second.value, MPFR_RNDU);
  mpfr_max(delta_re.value, first.value, second.value, MPFR_RNDU);
  mpfr_sub(first.value, output_im_lo.value, sum_im_hi.value, MPFR_RNDD);
  mpfr_abs(first.value, first.value, MPFR_RNDU);
  mpfr_sub(second.value, output_im_hi.value, sum_im_lo.value, MPFR_RNDU);
  mpfr_abs(second.value, second.value, MPFR_RNDU);
  mpfr_max(delta_im.value, first.value, second.value, MPFR_RNDU);
  mpfr_mul(distance.value, delta_re.value, delta_re.value, MPFR_RNDU);
  mpfr_fma(distance.value, delta_im.value, delta_im.value,
           distance.value, MPFR_RNDU);
  mpfr_sqrt(distance.value, distance.value, MPFR_RNDU);
  mpfr_add(distance.value, distance.value, sum_radius.value, MPFR_RNDU);
  return mpfr_get_d(distance.value, MPFR_RNDU);
}

ComplexInterval phase_interval(mpfr_srcptr logarithm,
                               std::uint64_t multiplier) {
  MpfrValue argument, sine_lo, sine_hi, cosine_lo, cosine_hi;
  mpfr_mul_ui(argument.value, logarithm, multiplier, MPFR_RNDN);
  mpfr_neg(argument.value, argument.value, MPFR_RNDN);
  mpfr_sin(sine_lo.value, argument.value, MPFR_RNDD);
  mpfr_sin(sine_hi.value, argument.value, MPFR_RNDU);
  mpfr_cos(cosine_lo.value, argument.value, MPFR_RNDD);
  mpfr_cos(cosine_hi.value, argument.value, MPFR_RNDU);
  return {{outward_down(cosine_lo.value), outward_up(cosine_hi.value)},
          {outward_down(sine_lo.value), outward_up(sine_hi.value)}};
}

struct UnsortedTerm {
  std::uint32_t one_based_n;
  std::uint32_t bucket;
  RealInterval residual;
  RealInterval amplitude;
  pw::FixedTurn192 fixed_turn;
  ComplexInterval value;
  ComplexInterval phase_step;
  pw::RealDisk106 narrow_residual;
  pw::ComplexDisk106 narrow_value;
  pw::RealDisk106 narrow_amplitude;
};

pw::FixedTurn192 export_fixed_turn(mpz_srcptr integer) {
  mpz_t residue;
  mpz_init(residue);
  mpz_fdiv_r_2exp(residue, integer, 192U);
  std::uint64_t limbs[3] = {0U, 0U, 0U};
  std::size_t count = 0U;
  mpz_export(limbs, &count, -1, sizeof(std::uint64_t), 0, 0, residue);
  mpz_clear(residue);
  if (count > 3U) throw std::runtime_error("fixed-turn export overflow");
  return {limbs[0], limbs[1], limbs[2]};
}

pw::FixedTurn192 fixed_turn_from_bounds(mpfr_srcptr quotient_lo,
                                        mpfr_srcptr quotient_hi) {
  MpfrValue scaled_lo, scaled_hi;
  mpfr_mul_2ui(scaled_lo.value, quotient_lo, 192U, MPFR_RNDD);
  mpfr_mul_2ui(scaled_hi.value, quotient_hi, 192U, MPFR_RNDU);
  mpz_t integer_lo;
  mpz_t integer_hi;
  mpz_init(integer_lo);
  mpz_init(integer_hi);
  mpfr_get_z(integer_lo, scaled_lo.value, MPFR_RNDN);
  mpfr_get_z(integer_hi, scaled_hi.value, MPFR_RNDN);
  if (mpz_cmp(integer_lo, integer_hi) != 0) {
    mpz_clear(integer_hi);
    mpz_clear(integer_lo);
    throw std::runtime_error(
        "320-bit enclosure does not certify a unique nearest Q192 turn");
  }
  const pw::FixedTurn192 result = export_fixed_turn(integer_lo);
  mpz_clear(integer_hi);
  mpz_clear(integer_lo);
  return result;
}

UnsortedTerm source_term(std::uint32_t one_based_n) {
  MpfrValue pi, pi_lo, pi_hi, log_pi, log_pi_lo, log_pi_hi;
  MpfrValue log_n, log_n_lo, log_n_hi, logarithm, logarithm_lo;
  MpfrValue logarithm_hi, two_pi_lo, two_pi_hi;
  MpfrValue quotient_lo, quotient_hi, scaled_lo, scaled_hi, half;
  MpfrValue bucket_fraction_lo, bucket_fraction_hi, residual_lo, residual_hi;
  MpfrValue amplitude_lo, amplitude_hi;
  mpfr_const_pi(pi.value, MPFR_RNDN);
  mpfr_const_pi(pi_lo.value, MPFR_RNDD);
  mpfr_const_pi(pi_hi.value, MPFR_RNDU);
  mpfr_log(log_pi.value, pi.value, MPFR_RNDN);
  mpfr_log(log_pi_lo.value, pi_lo.value, MPFR_RNDD);
  mpfr_log(log_pi_hi.value, pi_hi.value, MPFR_RNDU);
  mpfr_log_ui(log_n.value, one_based_n, MPFR_RNDN);
  mpfr_log_ui(log_n_lo.value, one_based_n, MPFR_RNDD);
  mpfr_log_ui(log_n_hi.value, one_based_n, MPFR_RNDU);
  mpfr_div_ui(log_pi.value, log_pi.value, 2U, MPFR_RNDN);
  mpfr_div_ui(log_pi_lo.value, log_pi_lo.value, 2U, MPFR_RNDD);
  mpfr_div_ui(log_pi_hi.value, log_pi_hi.value, 2U, MPFR_RNDU);
  mpfr_add(logarithm.value, log_n.value, log_pi.value, MPFR_RNDN);
  mpfr_add(logarithm_lo.value, log_n_lo.value, log_pi_lo.value, MPFR_RNDD);
  mpfr_add(logarithm_hi.value, log_n_hi.value, log_pi_hi.value, MPFR_RNDU);
  mpfr_mul_ui(two_pi_lo.value, pi_lo.value, 2U, MPFR_RNDD);
  mpfr_mul_ui(two_pi_hi.value, pi_hi.value, 2U, MPFR_RNDU);
  mpfr_div(quotient_lo.value, logarithm_lo.value, two_pi_hi.value,
           MPFR_RNDD);
  mpfr_div(quotient_hi.value, logarithm_hi.value, two_pi_lo.value,
           MPFR_RNDU);

  mpfr_set_d(half.value, 0.5, MPFR_RNDN);
  mpfr_mul_ui(scaled_lo.value, quotient_lo.value, pw::kBucketScale,
              MPFR_RNDD);
  mpfr_mul_ui(scaled_hi.value, quotient_hi.value, pw::kBucketScale,
              MPFR_RNDU);
  mpfr_add(scaled_lo.value, scaled_lo.value, half.value, MPFR_RNDD);
  mpfr_add(scaled_hi.value, scaled_hi.value, half.value, MPFR_RNDU);
  mpz_t bucket_lo;
  mpz_t bucket_hi;
  mpz_init(bucket_lo);
  mpz_init(bucket_hi);
  mpfr_get_z(bucket_lo, scaled_lo.value, MPFR_RNDD);
  mpfr_get_z(bucket_hi, scaled_hi.value, MPFR_RNDD);
  if (mpz_cmp(bucket_lo, bucket_hi) != 0 || !mpz_fits_ulong_p(bucket_lo)) {
    mpz_clear(bucket_hi);
    mpz_clear(bucket_lo);
    throw std::runtime_error(
        "320-bit enclosure does not certify a unique source bucket");
  }
  const unsigned long natural_bucket = mpz_get_ui(bucket_lo);
  mpz_clear(bucket_hi);
  mpz_clear(bucket_lo);
  if (natural_bucket == 0U || natural_bucket >= pw::kBucketCount / 2U) {
    throw std::runtime_error("source term has an inadmissible natural bucket");
  }
  mpfr_set_ui(bucket_fraction_lo.value, natural_bucket, MPFR_RNDN);
  mpfr_set_ui(bucket_fraction_hi.value, natural_bucket, MPFR_RNDN);
  mpfr_div_ui(bucket_fraction_lo.value, bucket_fraction_lo.value,
              pw::kBucketScale, MPFR_RNDD);
  mpfr_div_ui(bucket_fraction_hi.value, bucket_fraction_hi.value,
              pw::kBucketScale, MPFR_RNDU);
  mpfr_sub(residual_lo.value, quotient_lo.value, bucket_fraction_hi.value,
           MPFR_RNDD);
  mpfr_sub(residual_hi.value, quotient_hi.value, bucket_fraction_lo.value,
           MPFR_RNDU);

  mpfr_set_ui(amplitude_lo.value, one_based_n, MPFR_RNDN);
  mpfr_sqrt(amplitude_lo.value, amplitude_lo.value, MPFR_RNDU);
  mpfr_ui_div(amplitude_lo.value, 1U, amplitude_lo.value, MPFR_RNDD);
  mpfr_set_ui(amplitude_hi.value, one_based_n, MPFR_RNDN);
  mpfr_sqrt(amplitude_hi.value, amplitude_hi.value, MPFR_RNDD);
  mpfr_ui_div(amplitude_hi.value, 1U, amplitude_hi.value, MPFR_RNDU);

  const std::uint64_t initial_center = pw::kSourceLower + pw::kWindowStep / 2U;
  ComplexInterval value = phase_interval(logarithm.value, initial_center);
  const RealInterval amplitude{outward_down(amplitude_lo.value),
                               outward_up(amplitude_hi.value)};
  auto scale_component = [&](RealInterval component) {
    const double products[] = {component.lo * amplitude.lo,
                               component.lo * amplitude.hi,
                               component.hi * amplitude.lo,
                               component.hi * amplitude.hi};
    const auto [minimum, maximum] = std::minmax_element(
        std::begin(products), std::end(products));
    return RealInterval{
        std::nextafter(*minimum, -std::numeric_limits<double>::infinity()),
        std::nextafter(*maximum, std::numeric_limits<double>::infinity())};
  };
  value = {scale_component(value.re), scale_component(value.im)};
  const DDRealProjection narrow_residual =
      project_mpfr_interval_dd(residual_lo.value, residual_hi.value);
  const DDRealProjection narrow_amplitude =
      project_mpfr_interval_dd(amplitude_lo.value, amplitude_hi.value);
  const pw::ComplexDisk106 narrow_value = narrow_source_value(
      logarithm_lo.value, logarithm_hi.value, amplitude_lo.value,
      amplitude_hi.value, initial_center);
  return {one_based_n,
          pw::conjugate_bucket(static_cast<std::uint32_t>(natural_bucket)),
          {outward_down(residual_lo.value), outward_up(residual_hi.value)},
          amplitude,
          fixed_turn_from_bounds(quotient_lo.value, quotient_hi.value), value,
          phase_interval(logarithm.value, pw::kWindowStep),
          {narrow_residual.center, narrow_residual.radius}, narrow_value,
          {narrow_amplitude.center, narrow_amplitude.radius}};
}

UnsortedTerm synthetic_term(std::uint32_t one_based_n) {
  constexpr double pi = 3.141592653589793238462643383279502884;
  const double logarithm = std::log(static_cast<double>(one_based_n)) +
                           0.5 * std::log(pi);
  const double quotient = logarithm / (2.0 * pi);
  const auto natural_bucket = static_cast<std::uint32_t>(
      std::floor(quotient * static_cast<double>(pw::kBucketScale) + 0.5));
  const double residual =
      quotient - static_cast<double>(natural_bucket) / pw::kBucketScale;
  const double amplitude = 1.0 / std::sqrt(static_cast<double>(one_based_n));
  const double initial_angle =
      -static_cast<double>(pw::kSourceLower + pw::kWindowStep / 2U) * logarithm;
  const double step_angle = -static_cast<double>(pw::kWindowStep) * logarithm;
  const double value_re = amplitude * std::cos(initial_angle);
  const double value_im = amplitude * std::sin(initial_angle);
  return {one_based_n, pw::conjugate_bucket(natural_bucket),
          {residual, residual}, {amplitude, amplitude}, {0U, 0U, 0U},
          {{value_re, value_re}, {value_im, value_im}},
          {{std::cos(step_angle), std::cos(step_angle)},
           {std::sin(step_angle), std::sin(step_angle)}},
          {{residual, 0.0}, 0.0},
          {{value_re, 0.0}, {value_im, 0.0}, 0.0},
          {{amplitude, 0.0}, 0.0}};
}

HostTerms initialize_terms(const Options& options) {
  std::vector<UnsortedTerm> terms;
  terms.reserve(options.terms);
  for (std::uint32_t index = 0; index < options.terms; ++index) {
    terms.push_back(options.source_geometry ? source_term(index + 1U)
                                            : synthetic_term(index + 1U));
  }
  std::stable_sort(terms.begin(), terms.end(),
                   [](const UnsortedTerm& left, const UnsortedTerm& right) {
                     return left.bucket < right.bucket;
                   });

  HostTerms result;
  result.one_based_ns.reserve(terms.size());
  result.offsets.assign(pw::kBucketCount + 1U, 0U);
  result.residuals.reserve(terms.size());
  result.amplitudes.reserve(terms.size());
  result.fixed_turns.reserve(terms.size());
  result.values.reserve(terms.size());
  result.phase_steps.reserve(terms.size());
  result.narrow_residuals.reserve(terms.size());
  result.narrow_values.reserve(terms.size());
  result.narrow_amplitudes.reserve(terms.size());
  for (const auto& term : terms) {
    if (term.bucket >= pw::kBucketCount) {
      throw std::runtime_error("term bucket exceeds N1");
    }
    ++result.offsets[term.bucket + 1U];
    result.one_based_ns.push_back(term.one_based_n);
    result.residuals.push_back(term.residual);
    result.amplitudes.push_back(term.amplitude);
    result.fixed_turns.push_back(term.fixed_turn);
    result.values.push_back(term.value);
    result.phase_steps.push_back(term.phase_step);
    result.narrow_residuals.push_back(term.narrow_residual);
    result.narrow_values.push_back(term.narrow_value);
    result.narrow_amplitudes.push_back(term.narrow_amplitude);
  }
  std::partial_sum(result.offsets.begin(), result.offsets.end(),
                   result.offsets.begin());
  for (std::uint32_t bucket = 0; bucket < pw::kBucketCount; ++bucket) {
    if (result.offsets[bucket] != result.offsets[bucket + 1U]) {
      result.active_buckets.push_back(bucket);
    }
  }
  if (result.active_buckets.empty()) {
    throw std::runtime_error("term initialization produced no active bucket");
  }
  return result;
}

std::vector<ComplexInterval> initialize_fft_roots() {
  std::vector<ComplexInterval> roots(pw::kFinalFftLength / 2U);
  MpfrValue pi, angle;
  mpfr_const_pi(pi.value, MPFR_RNDN);
  for (std::uint32_t index = 0;
       index < static_cast<std::uint32_t>(roots.size()); ++index) {
    mpfr_mul_ui(angle.value, pi.value, 2ULL * index, MPFR_RNDN);
    mpfr_div_ui(angle.value, angle.value, pw::kFinalFftLength, MPFR_RNDN);
    roots[index] = phase_interval(angle.value, 1U);
  }
  return roots;
}

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

__device__ __forceinline__ ComplexInterval cadd(ComplexInterval x,
                                                 ComplexInterval y) {
  return {add(x.re, y.re), add(x.im, y.im)};
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

struct SourceDDTwoSum {
  double sum;
  double residual;
};

struct SourceDDResult {
  pw::DoubleDouble value;
  double error;
};

constexpr double kSourceDDFloor = 0x0.0000000000001p-1022;

__device__ __forceinline__ SourceDDTwoSum source_dd_two_sum(double a,
                                                            double b) {
  const double sum = __dadd_rn(a, b);
  const double virtual_b = __dsub_rn(sum, a);
  const double residual = __dadd_rn(
      __dsub_rn(a, __dsub_rn(sum, virtual_b)),
      __dsub_rn(b, virtual_b));
  return {sum, residual};
}

__device__ __forceinline__ SourceDDTwoSum source_dd_two_product(double a,
                                                                double b) {
  const double product = __dmul_rn(a, b);
  return {product, fma(a, b, -product)};
}

__device__ __forceinline__ SourceDDResult source_dd_add_center(
    pw::DoubleDouble a, pw::DoubleDouble b) {
  const SourceDDTwoSum high = source_dd_two_sum(a.hi, b.hi);
  double low = 0.0;
  double error = kSourceDDFloor;
  const double terms[] = {high.residual, a.lo, b.lo};
#pragma unroll
  for (int index = 0; index < 3; ++index) {
    const SourceDDTwoSum next = source_dd_two_sum(low, terms[index]);
    low = next.sum;
    error = __dadd_ru(error, fabs(next.residual));
    error = __dadd_ru(error, kSourceDDFloor);
  }
  const SourceDDTwoSum normalized = source_dd_two_sum(high.sum, low);
  error = __dadd_ru(error, kSourceDDFloor);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ SourceDDResult source_dd_mul_center(
    pw::DoubleDouble a, pw::DoubleDouble b) {
  const SourceDDTwoSum products[] = {
      source_dd_two_product(a.hi, b.hi),
      source_dd_two_product(a.hi, b.lo),
      source_dd_two_product(a.lo, b.hi),
      source_dd_two_product(a.lo, b.lo)};
  double low = 0.0;
  double error = __dmul_ru(4.0, kSourceDDFloor);
  const double terms[] = {
      products[0].residual, products[1].sum, products[1].residual,
      products[2].sum,      products[2].residual, products[3].sum,
      products[3].residual};
#pragma unroll
  for (int index = 0; index < 7; ++index) {
    const SourceDDTwoSum next = source_dd_two_sum(low, terms[index]);
    low = next.sum;
    error = __dadd_ru(error, fabs(next.residual));
    error = __dadd_ru(error, kSourceDDFloor);
  }
  const SourceDDTwoSum normalized = source_dd_two_sum(products[0].sum, low);
  error = __dadd_ru(error, kSourceDDFloor);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ double source_dd_abs_upper(
    pw::DoubleDouble value) {
  return __dadd_ru(fabs(value.hi), fabs(value.lo));
}

__device__ __forceinline__ double source_dd_norm_upper(
    pw::DoubleDouble re, pw::DoubleDouble im) {
  const double x = source_dd_abs_upper(re);
  const double y = source_dd_abs_upper(im);
  const double large = fmax(x, y);
  const double small = fmin(x, y);
  if (large == 0.0) return 0.0;
  const double ratio = __ddiv_ru(small, large);
  return __dmul_ru(
      large, __dsqrt_ru(__dadd_ru(1.0, __dmul_ru(ratio, ratio))));
}

__device__ __forceinline__ pw::RealDisk106 source_dd_real_mul(
    pw::RealDisk106 x, pw::RealDisk106 y) {
  const SourceDDResult center = source_dd_mul_center(x.center, y.center);
  const double nx = source_dd_abs_upper(x.center);
  const double ny = source_dd_abs_upper(y.center);
  double radius = __dadd_ru(center.error, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {center.value, radius};
}

__device__ __forceinline__ pw::RealDisk106 source_dd_real_add(
    pw::RealDisk106 x, pw::RealDisk106 y) {
  const SourceDDResult center = source_dd_add_center(x.center, y.center);
  return {center.value,
          __dadd_ru(__dadd_ru(x.radius, y.radius), center.error)};
}

__device__ __forceinline__ pw::ComplexDisk106 source_dd_complex_add(
    pw::ComplexDisk106 x, pw::ComplexDisk106 y) {
  const SourceDDResult re = source_dd_add_center(x.real, y.real);
  const SourceDDResult im = source_dd_add_center(x.imaginary, y.imaginary);
  const double local = source_dd_norm_upper({re.error, 0.0},
                                            {im.error, 0.0});
  return {re.value, im.value,
          __dadd_ru(__dadd_ru(x.radius, y.radius), local)};
}

__device__ __forceinline__ pw::ComplexDisk106 source_dd_complex_scale(
    pw::ComplexDisk106 x, pw::RealDisk106 y) {
  const SourceDDResult re = source_dd_mul_center(x.real, y.center);
  const SourceDDResult im = source_dd_mul_center(x.imaginary, y.center);
  const double local = source_dd_norm_upper({re.error, 0.0},
                                            {im.error, 0.0});
  const double nx = source_dd_norm_upper(x.real, x.imaginary);
  const double ny = source_dd_abs_upper(y.center);
  double radius = __dadd_ru(local, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

// Euclidean-disk multiplication with an unevaluated two-limb Cartesian
// centre.  Every discarded TwoSum/FMA residual is charged to `local`; the
// remaining three terms are the standard
//
//   |cx| ry + |cy| rx + rx ry
//
// disk-product radius.  This is used by the source-height phase recurrence;
// it must therefore remain directed even though both mathematical factors
// have modulus close to one.
__device__ __forceinline__ pw::ComplexDisk106 source_dd_complex_mul(
    pw::ComplexDisk106 x, pw::ComplexDisk106 y) {
  const SourceDDResult rr = source_dd_mul_center(x.real, y.real);
  const SourceDDResult ii = source_dd_mul_center(x.imaginary, y.imaginary);
  const SourceDDResult ri = source_dd_mul_center(x.real, y.imaginary);
  const SourceDDResult ir = source_dd_mul_center(x.imaginary, y.real);
  const SourceDDResult re = source_dd_add_center(
      rr.value, {-ii.value.hi, -ii.value.lo});
  const SourceDDResult im = source_dd_add_center(ri.value, ir.value);
  const double re_error =
      __dadd_ru(__dadd_ru(rr.error, ii.error), re.error);
  const double im_error =
      __dadd_ru(__dadd_ru(ri.error, ir.error), im.error);
  const double local = source_dd_norm_upper(
      {re_error, 0.0}, {im_error, 0.0});
  const double nx = source_dd_norm_upper(x.real, x.imaginary);
  const double ny = source_dd_norm_upper(y.real, y.imaginary);
  double radius = __dadd_ru(local, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

__global__ void source_dd_build_power_table(
    const pw::RealDisk106* residuals, pw::RealDisk106* powers,
    std::uint32_t terms, std::uint32_t stages) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    pw::RealDisk106 power{{1.0, 0.0}, 0.0};
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      powers[static_cast<std::uint64_t>(stage) * terms + index] = power;
      power = source_dd_real_mul(power, residuals[index]);
    }
  }
}

// Reference implementation retained for the differential KAT below.  It
// keeps a two-limb centre after every operation and is intentionally not used
// by the production-shaped stream once the compressed accumulator has passed
// the MPFR comparison.
__global__ void source_dd_accumulate_all_stages_legacy(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const pw::ComplexDisk106* values, const pw::RealDisk106* powers,
    std::uint32_t terms, std::uint32_t active_count,
    std::uint32_t stage_count, pw::ComplexDisk106* output) {
  const std::uint32_t flat_block = blockIdx.x;
  const std::uint32_t stage = flat_block / active_count;
  const std::uint32_t active_index = flat_block % active_count;
  if (stage >= stage_count) return;
  const std::uint32_t lane = threadIdx.x;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  pw::ComplexDisk106 sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
  for (std::uint32_t term = begin + lane; term < end; term += 32U) {
    const pw::ComplexDisk106 contribution =
        stage == 0U
            ? values[term]
            : source_dd_complex_scale(
                  values[term],
                  powers[static_cast<std::uint64_t>(stage) * terms + term]);
    sum = source_dd_complex_add(sum, contribution);
  }
  for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
    const pw::ComplexDisk106 other{
        {__shfl_down_sync(0xffffffffU, sum.real.hi, delta),
         __shfl_down_sync(0xffffffffU, sum.real.lo, delta)},
        {__shfl_down_sync(0xffffffffU, sum.imaginary.hi, delta),
         __shfl_down_sync(0xffffffffU, sum.imaginary.lo, delta)},
        __shfl_down_sync(0xffffffffU, sum.radius, delta)};
    if (lane < delta) sum = source_dd_complex_add(sum, other);
  }
  if (lane == 0U) {
    output[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] =
        sum;
  }
}

// A two-limb centre plus an L1 error budget.  `radius` is still a Euclidean
// disk radius: every componentwise centre error is charged by its L1 norm,
// which is an upper bound for the Euclidean norm.  Unlike a binary64-only
// compression, this keeps the accuracy needed by the downstream sign test.
struct SourceDDFastAccum {
  pw::DoubleDouble real;
  pw::DoubleDouble imaginary;
  double radius;
};

constexpr std::uint32_t kSourceDDAccumulatorWarps = 8U;
constexpr double kSourceDDFastTwoSumFloors = 6.0 * kSourceDDFloor;
constexpr double kSourceDDRnRelativeError = 0x1.0000000000001p-53;

__device__ __forceinline__ double source_dd_l1_upper(
    pw::DoubleDouble re, pw::DoubleDouble im) {
  double result = __dadd_ru(fabs(re.hi), fabs(re.lo));
  result = __dadd_ru(result, fabs(im.hi));
  return __dadd_ru(result, fabs(im.lo));
}

// For a finite round-to-nearest result r, u/(1-u)|r| plus one minimum
// subnormal bounds the operation's rounding error.  This form remains valid
// under cancellation and does not assume a normal exact result.
__device__ __forceinline__ double source_dd_rn_error(double result) {
  return __dadd_ru(
      __dmul_ru(fabs(result), kSourceDDRnRelativeError), kSourceDDFloor);
}

// Fast bounded DD addition for the accumulator only.  Two rounded low-part
// additions replace three general expansion insertions.  Their errors and
// both TwoSum underflow budgets are retained explicitly.
__device__ __forceinline__ SourceDDResult source_dd_fast_add_center(
    pw::DoubleDouble a, pw::DoubleDouble b) {
  const SourceDDTwoSum high = source_dd_two_sum(a.hi, b.hi);
  const double low_parts = __dadd_rn(a.lo, b.lo);
  const double low = __dadd_rn(high.residual, low_parts);
  const SourceDDTwoSum normalized = source_dd_two_sum(high.sum, low);
  double error = source_dd_rn_error(low_parts);
  error = __dadd_ru(error, source_dd_rn_error(low));
  error = __dadd_ru(error, 2.0 * kSourceDDFastTwoSumFloors);
  return {{normalized.sum, normalized.residual}, error};
}

// Fast bounded DD multiplication for the accumulator only.  The leading FMA
// retains the product residual, two rounded cross-products form the low limb,
// and every omitted/rounded term (including a.lo*b.lo) is charged outwards.
// No non-overlap property of the input expansions is assumed.
__device__ __forceinline__ SourceDDResult source_dd_fast_mul_center(
    pw::DoubleDouble a, pw::DoubleDouble b) {
  const SourceDDTwoSum leading = source_dd_two_product(a.hi, b.hi);
  const double cross0 = __dmul_rn(a.hi, b.lo);
  const double cross1 = __dmul_rn(a.lo, b.hi);
  const double cross = __dadd_rn(cross0, cross1);
  const double low = __dadd_rn(leading.residual, cross);
  const SourceDDTwoSum normalized = source_dd_two_sum(leading.sum, low);
  double error = kSourceDDFloor;
  error = __dadd_ru(error, source_dd_rn_error(cross0));
  error = __dadd_ru(error, source_dd_rn_error(cross1));
  error = __dadd_ru(error, source_dd_rn_error(cross));
  error = __dadd_ru(error, source_dd_rn_error(low));
  error = __dadd_ru(error, __dmul_ru(fabs(a.lo), fabs(b.lo)));
  error = __dadd_ru(error, kSourceDDFastTwoSumFloors);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ SourceDDFastAccum source_dd_fast_scale(
    pw::ComplexDisk106 x, pw::RealDisk106 y) {
  const double y_abs = __dadd_ru(fabs(y.center.hi), fabs(y.center.lo));
  const SourceDDResult re = source_dd_fast_mul_center(x.real, y.center);
  const SourceDDResult im =
      source_dd_fast_mul_center(x.imaginary, y.center);
  const double x_abs = source_dd_l1_upper(x.real, x.imaginary);
  double radius = __dadd_ru(re.error, im.error);
  radius = __dadd_ru(radius, __dmul_ru(x_abs, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(y_abs, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

__device__ __forceinline__ SourceDDFastAccum source_dd_fast_add(
    SourceDDFastAccum x, SourceDDFastAccum y) {
  const SourceDDResult re = source_dd_fast_add_center(x.real, y.real);
  const SourceDDResult im =
      source_dd_fast_add_center(x.imaginary, y.imaginary);
  double radius = __dadd_ru(x.radius, y.radius);
  radius = __dadd_ru(radius, re.error);
  radius = __dadd_ru(radius, im.error);
  return {re.value, im.value, radius};
}

// One block owns one bucket.  Its eight warps consume the 23 Taylor stages in
// three short rounds.  This removes roughly 23x as many one-warp block
// schedules while retaining the exact per-(bucket,stage) lane partition and
// fixed shuffle tree of the reference kernel.
__global__ void source_dd_accumulate_all_stages(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const pw::ComplexDisk106* values, const pw::RealDisk106* powers,
    std::uint32_t terms, std::uint32_t active_count,
    std::uint32_t stage_count, pw::ComplexDisk106* output) {
  const std::uint32_t active_index = blockIdx.x;
  if (active_index >= active_count) return;
  const std::uint32_t warp = threadIdx.x >> 5U;
  const std::uint32_t lane = threadIdx.x & 31U;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  for (std::uint32_t stage = warp; stage < stage_count;
       stage += kSourceDDAccumulatorWarps) {
    SourceDDFastAccum sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
    for (std::uint32_t term = begin + lane; term < end; term += 32U) {
      const SourceDDFastAccum contribution =
          stage == 0U
              ? SourceDDFastAccum{values[term].real,
                                  values[term].imaginary,
                                  values[term].radius}
              : source_dd_fast_scale(
                    values[term],
                    powers[static_cast<std::uint64_t>(stage) * terms +
                           term]);
      sum = source_dd_fast_add(sum, contribution);
    }
    for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
      const SourceDDFastAccum other{
          {__shfl_down_sync(0xffffffffU, sum.real.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.real.lo, delta)},
          {__shfl_down_sync(0xffffffffU, sum.imaginary.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.imaginary.lo, delta)},
          __shfl_down_sync(0xffffffffU, sum.radius, delta)};
      if (lane < delta) sum = source_dd_fast_add(sum, other);
    }
    if (lane == 0U) {
      output[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] =
          {sum.real, sum.imaginary, sum.radius};
    }
  }
}

#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
// Qualification-only schedule variants.  The non-shared variant changes only
// the number of independently assigned stage warps.  The shared variant keeps
// each lane's term order and the existing warp shuffle tree, but loads each
// 32-term ComplexDisk106 chunk once per stage round instead of once per stage.
// Every thread participates in both barriers, including the one inactive warp
// in the final 12-warp round.
template <std::uint32_t Warps>
__global__ void source_dd_accumulate_all_stages_warp_qualification(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const pw::ComplexDisk106* values, const pw::RealDisk106* powers,
    std::uint32_t terms, std::uint32_t active_count,
    std::uint32_t stage_count, pw::ComplexDisk106* output) {
  const std::uint32_t active_index = blockIdx.x;
  if (active_index >= active_count) return;
  const std::uint32_t warp = threadIdx.x >> 5U;
  const std::uint32_t lane = threadIdx.x & 31U;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  for (std::uint32_t stage = warp; stage < stage_count; stage += Warps) {
    SourceDDFastAccum sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
    for (std::uint32_t term = begin + lane; term < end; term += 32U) {
      const SourceDDFastAccum contribution =
          stage == 0U
              ? SourceDDFastAccum{values[term].real,
                                  values[term].imaginary,
                                  values[term].radius}
              : source_dd_fast_scale(
                    values[term],
                    powers[static_cast<std::uint64_t>(stage) * terms +
                           term]);
      sum = source_dd_fast_add(sum, contribution);
    }
    for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
      const SourceDDFastAccum other{
          {__shfl_down_sync(0xffffffffU, sum.real.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.real.lo, delta)},
          {__shfl_down_sync(0xffffffffU, sum.imaginary.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.imaginary.lo, delta)},
          __shfl_down_sync(0xffffffffU, sum.radius, delta)};
      if (lane < delta) sum = source_dd_fast_add(sum, other);
    }
    if (lane == 0U) {
      output[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] =
          {sum.real, sum.imaginary, sum.radius};
    }
  }
}

template <std::uint32_t Warps>
__global__ void source_dd_accumulate_all_stages_shared_qualification(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const pw::ComplexDisk106* values, const pw::RealDisk106* powers,
    std::uint32_t terms, std::uint32_t active_count,
    std::uint32_t stage_count, pw::ComplexDisk106* output) {
  __shared__ pw::ComplexDisk106 shared_values[32];
  const std::uint32_t active_index = blockIdx.x;
  if (active_index >= active_count) return;
  const std::uint32_t warp = threadIdx.x >> 5U;
  const std::uint32_t lane = threadIdx.x & 31U;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  const std::uint32_t rounds =
      (stage_count + Warps - 1U) / Warps;
  for (std::uint32_t round = 0U; round < rounds; ++round) {
    const std::uint32_t stage = round * Warps + warp;
    SourceDDFastAccum sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
    for (std::uint32_t chunk = begin; chunk < end; chunk += 32U) {
      const std::uint32_t term = chunk + lane;
      if (warp == 0U && term < end) {
        shared_values[lane] = values[term];
      }
      __syncthreads();
      if (stage < stage_count && term < end) {
        const pw::ComplexDisk106 value = shared_values[lane];
        const SourceDDFastAccum contribution =
            stage == 0U
                ? SourceDDFastAccum{value.real, value.imaginary,
                                    value.radius}
                : source_dd_fast_scale(
                      value,
                      powers[static_cast<std::uint64_t>(stage) * terms +
                             term]);
        sum = source_dd_fast_add(sum, contribution);
      }
      __syncthreads();
    }
    if (stage < stage_count) {
      for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
        const SourceDDFastAccum other{
            {__shfl_down_sync(0xffffffffU, sum.real.hi, delta),
             __shfl_down_sync(0xffffffffU, sum.real.lo, delta)},
            {__shfl_down_sync(0xffffffffU, sum.imaginary.hi, delta),
             __shfl_down_sync(0xffffffffU, sum.imaginary.lo, delta)},
            __shfl_down_sync(0xffffffffU, sum.radius, delta)};
        if (lane < delta) sum = source_dd_fast_add(sum, other);
      }
      if (lane == 0U) {
        output[static_cast<std::uint64_t>(stage) * pw::kBucketCount +
               bucket] = {sum.real, sum.imaginary, sum.radius};
      }
    }
  }
}

__global__ void source_dd_precompute_value_l1_qualification(
    const pw::ComplexDisk106* values, double* value_l1,
    std::uint32_t terms) {
  for (std::uint32_t term = blockIdx.x * blockDim.x + threadIdx.x;
       term < terms; term += blockDim.x * gridDim.x) {
    value_l1[term] =
        source_dd_l1_upper(values[term].real, values[term].imaginary);
  }
}

__global__ void source_dd_precompute_power_abs_qualification(
    const pw::RealDisk106* powers, double* power_abs,
    std::uint64_t cells) {
  for (std::uint64_t cell =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x +
           threadIdx.x;
       cell < cells;
       cell += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    power_abs[cell] =
        __dadd_ru(fabs(powers[cell].center.hi),
                  fabs(powers[cell].center.lo));
  }
}

__device__ __forceinline__ SourceDDFastAccum
source_dd_fast_scale_precomputed_l1_qualification(
    pw::ComplexDisk106 x, pw::RealDisk106 y, double x_abs) {
  const double y_abs = __dadd_ru(fabs(y.center.hi), fabs(y.center.lo));
  const SourceDDResult re = source_dd_fast_mul_center(x.real, y.center);
  const SourceDDResult im =
      source_dd_fast_mul_center(x.imaginary, y.center);
  double radius = __dadd_ru(re.error, im.error);
  radius = __dadd_ru(radius, __dmul_ru(x_abs, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(y_abs, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

__device__ __forceinline__ SourceDDFastAccum
source_dd_fast_scale_precomputed_l1_power_abs_qualification(
    pw::ComplexDisk106 x, pw::RealDisk106 y, double x_abs,
    double y_abs) {
  const SourceDDResult re = source_dd_fast_mul_center(x.real, y.center);
  const SourceDDResult im =
      source_dd_fast_mul_center(x.imaginary, y.center);
  double radius = __dadd_ru(re.error, im.error);
  radius = __dadd_ru(radius, __dmul_ru(x_abs, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(y_abs, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

__global__ void source_dd_accumulate_all_stages_precomputed_l1_qualification(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const pw::ComplexDisk106* values, const pw::RealDisk106* powers,
    const double* value_l1, std::uint32_t terms,
    std::uint32_t active_count, std::uint32_t stage_count,
    pw::ComplexDisk106* output) {
  const std::uint32_t active_index = blockIdx.x;
  if (active_index >= active_count) return;
  const std::uint32_t warp = threadIdx.x >> 5U;
  const std::uint32_t lane = threadIdx.x & 31U;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  for (std::uint32_t stage = warp; stage < stage_count;
       stage += kSourceDDAccumulatorWarps) {
    SourceDDFastAccum sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
    for (std::uint32_t term = begin + lane; term < end; term += 32U) {
      const SourceDDFastAccum contribution =
          stage == 0U
              ? SourceDDFastAccum{values[term].real,
                                  values[term].imaginary,
                                  values[term].radius}
              : source_dd_fast_scale_precomputed_l1_qualification(
                    values[term],
                    powers[static_cast<std::uint64_t>(stage) * terms +
                           term],
                    value_l1[term]);
      sum = source_dd_fast_add(sum, contribution);
    }
    for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
      const SourceDDFastAccum other{
          {__shfl_down_sync(0xffffffffU, sum.real.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.real.lo, delta)},
          {__shfl_down_sync(0xffffffffU, sum.imaginary.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.imaginary.lo, delta)},
          __shfl_down_sync(0xffffffffU, sum.radius, delta)};
      if (lane < delta) sum = source_dd_fast_add(sum, other);
    }
    if (lane == 0U) {
      output[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] =
          {sum.real, sum.imaginary, sum.radius};
    }
  }
}

__global__ void
source_dd_accumulate_all_stages_precomputed_l1_power_abs_qualification(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const pw::ComplexDisk106* values, const pw::RealDisk106* powers,
    const double* value_l1, const double* power_abs,
    std::uint32_t terms, std::uint32_t active_count,
    std::uint32_t stage_count, pw::ComplexDisk106* output) {
  const std::uint32_t active_index = blockIdx.x;
  if (active_index >= active_count) return;
  const std::uint32_t warp = threadIdx.x >> 5U;
  const std::uint32_t lane = threadIdx.x & 31U;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  for (std::uint32_t stage = warp; stage < stage_count;
       stage += kSourceDDAccumulatorWarps) {
    SourceDDFastAccum sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
    for (std::uint32_t term = begin + lane; term < end; term += 32U) {
      const std::uint64_t power_cell =
          static_cast<std::uint64_t>(stage) * terms + term;
      const SourceDDFastAccum contribution =
          stage == 0U
              ? SourceDDFastAccum{values[term].real,
                                  values[term].imaginary,
                                  values[term].radius}
              : source_dd_fast_scale_precomputed_l1_power_abs_qualification(
                    values[term], powers[power_cell], value_l1[term],
                    power_abs[power_cell]);
      sum = source_dd_fast_add(sum, contribution);
    }
    for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
      const SourceDDFastAccum other{
          {__shfl_down_sync(0xffffffffU, sum.real.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.real.lo, delta)},
          {__shfl_down_sync(0xffffffffU, sum.imaginary.hi, delta),
           __shfl_down_sync(0xffffffffU, sum.imaginary.lo, delta)},
          __shfl_down_sync(0xffffffffU, sum.radius, delta)};
      if (lane < delta) sum = source_dd_fast_add(sum, other);
    }
    if (lane == 0U) {
      output[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] =
          {sum.real, sum.imaginary, sum.radius};
    }
  }
}
#endif

struct DeviceUInt192 {
  std::uint64_t limb0;
  std::uint64_t limb1;
  std::uint64_t limb2;
};

__device__ __forceinline__ DeviceUInt192 multiply_low_192(
    pw::FixedTurn192 value, std::uint64_t multiplier) {
  DeviceUInt192 result{};
  result.limb0 = value.limb0 * multiplier;
  std::uint64_t carry = __umul64hi(value.limb0, multiplier);
  const std::uint64_t middle_product = value.limb1 * multiplier;
  result.limb1 = middle_product + carry;
  const std::uint64_t middle_overflow = result.limb1 < middle_product ? 1U : 0U;
  carry = __umul64hi(value.limb1, multiplier) + middle_overflow;
  result.limb2 = value.limb2 * multiplier + carry;
  return result;
}

__device__ __forceinline__ DeviceUInt192 subtract_192(DeviceUInt192 x,
                                                       DeviceUInt192 y) {
  DeviceUInt192 result{};
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

__device__ __forceinline__ DeviceUInt192 add_192(DeviceUInt192 x,
                                                  DeviceUInt192 y) {
  DeviceUInt192 result{};
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

__device__ __forceinline__ DeviceUInt192 negate_192(DeviceUInt192 value) {
  return subtract_192(DeviceUInt192{}, value);
}

__device__ __forceinline__ pw::RealDisk106 source_dd_fraction_from_192(
    DeviceUInt192 value) {
  pw::RealDisk106 result{{0.0, 0.0}, 0.0};
  const double terms[] = {
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb2 >> 32U)),
            -32),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb2)), -64),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb1 >> 32U)),
            -96),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb1)),
            -128),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb0 >> 32U)),
            -160),
      ldexp(static_cast<double>(static_cast<std::uint32_t>(value.limb0)),
            -192)};
#pragma unroll
  for (int index = 0; index < 6; ++index) {
    result = source_dd_real_add(result, {{terms[index], 0.0}, 0.0});
  }
  return result;
}

__device__ __forceinline__ pw::ComplexDisk106 source_dd_sin_cos_reduced(
    pw::RealDisk106 x, const pw::RealDisk106* sine_coefficients,
    const pw::RealDisk106* cosine_coefficients) {
  constexpr int kCoefficientCount = 20;
  const pw::RealDisk106 square = source_dd_real_mul(x, x);
  pw::RealDisk106 sine = sine_coefficients[kCoefficientCount - 1];
  pw::RealDisk106 cosine = cosine_coefficients[kCoefficientCount - 1];
#pragma unroll
  for (int index = kCoefficientCount - 2; index >= 0; --index) {
    sine = source_dd_real_add(source_dd_real_mul(sine, square),
                              sine_coefficients[index]);
    cosine = source_dd_real_add(source_dd_real_mul(cosine, square),
                                cosine_coefficients[index]);
  }
  sine = source_dd_real_mul(x, sine);
  // At |x| <= pi/4 plus the recorded disk error, the first omitted sine and
  // cosine terms are below 1.5e-54 and 7.8e-53 respectively.  1e-50 is a
  // deliberately loose common analytic tail.
  sine.radius = __dadd_ru(sine.radius, 1.0e-50);
  cosine.radius = __dadd_ru(cosine.radius, 1.0e-50);
  const double radius = source_dd_norm_upper(
      {cosine.radius, 0.0}, {sine.radius, 0.0});
  return {cosine.center, sine.center, radius};
}

__device__ __forceinline__ pw::DoubleDouble source_dd_negate_center(
    pw::DoubleDouble value) {
  return {-value.hi, -value.lo};
}

__device__ __forceinline__ pw::ComplexDisk106 source_dd_fixed_product_phase(
    DeviceUInt192 product, std::uint64_t height,
    pw::RealDisk106 two_pi,
    const pw::RealDisk106* sine_coefficients,
    const pw::RealDisk106* cosine_coefficients) {
  const unsigned octant = static_cast<unsigned>(product.limb2 >> 61U);
  product.limb2 &= (1ULL << 61U) - 1ULL;
  if ((octant & 1U) != 0U) {
    const DeviceUInt192 one_eighth{0U, 0U, 1ULL << 61U};
    product = subtract_192(one_eighth, product);
  }
  pw::RealDisk106 angle = source_dd_real_mul(
      source_dd_fraction_from_192(product), two_pi);
  pw::ComplexDisk106 base = source_dd_sin_cos_reduced(
      angle, sine_coefficients, cosine_coefficients);
  pw::DoubleDouble cosine{};
  pw::DoubleDouble sine{};
  switch (octant) {
    case 0U: cosine = base.real; sine = base.imaginary; break;
    case 1U: cosine = base.imaginary; sine = base.real; break;
    case 2U: cosine = source_dd_negate_center(base.imaginary); sine = base.real; break;
    case 3U: cosine = source_dd_negate_center(base.real); sine = base.imaginary; break;
    case 4U:
      cosine = source_dd_negate_center(base.real);
      sine = source_dd_negate_center(base.imaginary);
      break;
    case 5U:
      cosine = source_dd_negate_center(base.imaginary);
      sine = source_dd_negate_center(base.real);
      break;
    case 6U: cosine = base.imaginary; sine = source_dd_negate_center(base.real); break;
    default: cosine = base.real; sine = source_dd_negate_center(base.imaginary); break;
  }
  // The stored turn is nearest Q192.  Multiplication by height changes the
  // phase by at most pi*height/2^192, and exp(i x) is 1-Lipschitz.
  constexpr double pi_upper = 0x1.921fb54442d19p+1;
  const double q192_error =
      ldexp(__dmul_ru(pi_upper, static_cast<double>(height)), -192);
  return {cosine, source_dd_negate_center(sine),
          __dadd_ru(base.radius, q192_error)};
}

__global__ void source_dd_anchor_fixed_phases(
    const pw::FixedTurn192* fixed_turns,
    const pw::RealDisk106* amplitudes, std::uint64_t height,
    pw::RealDisk106 two_pi,
    const pw::RealDisk106* sine_coefficients,
    const pw::RealDisk106* cosine_coefficients,
    pw::ComplexDisk106* values, std::uint32_t terms) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    const DeviceUInt192 product = multiply_low_192(fixed_turns[index], height);
    values[index] = source_dd_complex_scale(
        source_dd_fixed_product_phase(product, height, two_pi,
                                      sine_coefficients,
                                      cosine_coefficients),
        amplitudes[index]);
  }
}

// Build the exact source-window phase multiplier exp(-i*1008*log(n sqrt pi))
// from the same nearest-Q192 turn used by a direct anchor.  The disk radius
// includes the Q192 storage error multiplied by exactly one source step.
__global__ void source_dd_construct_phase_steps(
    const pw::FixedTurn192* fixed_turns, pw::RealDisk106 two_pi,
    const pw::RealDisk106* sine_coefficients,
    const pw::RealDisk106* cosine_coefficients,
    pw::ComplexDisk106* phase_steps, std::uint32_t terms) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    const DeviceUInt192 product =
        multiply_low_192(fixed_turns[index], pw::kWindowStep);
    phase_steps[index] = source_dd_fixed_product_phase(
        product, pw::kWindowStep, two_pi, sine_coefficients,
        cosine_coefficients);
  }
}

__global__ void source_dd_advance_phase(
    pw::ComplexDisk106* values,
    const pw::ComplexDisk106* phase_steps, std::uint32_t terms) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    values[index] = source_dd_complex_mul(values[index], phase_steps[index]);
  }
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

// Directed Maclaurin enclosures on 0 <= x <= pi/4.  The retained sine term
// is x^17/17!, with remainder <= x^19/1e17.  The retained cosine term is
// x^18/18!, with remainder <= x^20/2e18.  Both denominators are deliberately
// below the corresponding exact factorial.
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
  const RealInterval sine_power = positive_power(x, 19U);
  sine = widen_symmetric(sine, __ddiv_ru(sine_power.hi, 1.0e17));

  RealInterval cosine_polynomial = signed_reciprocal_factorial(18U, true);
  for (int degree = 16; degree >= 0; degree -= 2) {
    const bool negative = (degree / 2) % 2 != 0;
    cosine_polynomial = add(
        mul(cosine_polynomial, square),
        signed_reciprocal_factorial(static_cast<unsigned>(degree), negative));
  }
  RealInterval cosine = cosine_polynomial;
  const RealInterval cosine_power = positive_power(x, 20U);
  cosine = widen_symmetric(cosine, __ddiv_ru(cosine_power.hi, 2.0e18));
  return {cosine, sine};
}

// The same directed degree-18/17 evaluation for a signed interval.  The
// polynomial algebra is valid on [-pi/4,pi/4]; only the remainder calculation
// differs from the nonnegative octant helper above.
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

// Certified range-reduced exponential for the Gamma synthesis benchmark.
// Any integral binary shift is legal; the midpoint only selects one that
// keeps the residual in [-0.7,0.7].  The degree-18 Taylor tail on that interval
// is widened by 1e-18, conservatively above 2*0.7^19/19!.
__device__ __forceinline__ RealInterval exp_interval(RealInterval x) {
  constexpr double ln2_lo = 0x1.62e42fefa39eep-1;
  constexpr double ln2_hi = 0x1.62e42fefa39f0p-1;
  constexpr double ln2_mid = 0x1.62e42fefa39efp-1;
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
  // exp(real_log) is strictly positive and normal on the source range, so
  // adjacent positive binary64 encodings are the directed neighbours.
  return {__longlong_as_double(__double_as_longlong(lower) - 1ULL),
          __longlong_as_double(__double_as_longlong(upper) + 1ULL)};
}

__device__ __forceinline__ ComplexInterval fixed_product_phase(
    DeviceUInt192 product, double phase_error, bool negative_phase) {
  const unsigned octant = static_cast<unsigned>(product.limb2 >> 61U);
  product.limb2 &= (1ULL << 61U) - 1ULL;
  if ((octant & 1U) != 0U) {
    const DeviceUInt192 one_eighth{0U, 0U, 1ULL << 61U};
    product = subtract_192(one_eighth, product);
  }

  const bool has_low_bits = product.limb0 != 0U || product.limb1 != 0U;
  const double turn_lo = ldexp(__ull2double_rd(product.limb2), -64);
  const std::uint64_t upper_limb =
      product.limb2 + (has_low_bits ? 1ULL : 0ULL);
  const double turn_hi = ldexp(__ull2double_ru(upper_limb), -64);
  constexpr double pi_lo = 0x1.921fb54442d17p+1;
  constexpr double pi_hi = 0x1.921fb54442d19p+1;
  const RealInterval reduced{
      __dmul_rd(turn_lo, 2.0 * pi_lo),
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
  if (negative_phase) sine = negate(sine);
  return {widen_symmetric(cosine, phase_error),
          widen_symmetric(sine, phase_error)};
}

__device__ __forceinline__ ComplexInterval fixed_turn_phase(
    pw::FixedTurn192 turn, std::uint64_t height) {
  const DeviceUInt192 product = multiply_low_192(turn, height);
  // Nearest Q192 storage changes the turn by at most 2^-193.  Multiplication
  // by height and conversion to radians therefore changes either trig value
  // by at most pi*height/2^192 (the derivatives have absolute value <= 1).
  constexpr double pi_hi = 0x1.921fb54442d19p+1;
  const double phase_error = ldexp(
      __dmul_ru(pi_hi, static_cast<double>(height)), -192);
  return fixed_product_phase(product, phase_error, true);
}

__device__ __forceinline__ ComplexInterval fixed_anchor_step_phase(
    pw::FixedTurn192 anchor, pw::FixedTurn192 step, int grid_offset,
    double anchor_error, double step_error) {
  const std::uint64_t magnitude = static_cast<std::uint64_t>(
      grid_offset < 0 ? -static_cast<std::int64_t>(grid_offset)
                      : static_cast<std::int64_t>(grid_offset));
  DeviceUInt192 displacement = multiply_low_192(step, magnitude);
  if (grid_offset < 0) displacement = negate_192(displacement);
  const DeviceUInt192 product =
      add_192({anchor.limb0, anchor.limb1, anchor.limb2}, displacement);
  const double phase_error = __dadd_ru(
      anchor_error, __dmul_ru(static_cast<double>(magnitude), step_error));
  return fixed_product_phase(product, phase_error, false);
}

__global__ void anchor_fixed_phases(const pw::FixedTurn192* fixed_turns,
                                    const RealInterval* amplitudes,
                                    std::uint64_t height,
                                    ComplexInterval* values,
                                    std::uint32_t terms) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    values[index] = cscale(fixed_turn_phase(fixed_turns[index], height),
                           amplitudes[index]);
  }
}

__global__ void construct_fixed_phase_steps(
    const pw::FixedTurn192* fixed_turns, ComplexInterval* phase_steps,
    std::uint32_t terms) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    phase_steps[index] =
        fixed_turn_phase(fixed_turns[index], pw::kWindowStep);
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

__global__ void initialize_final_fft_input(const ComplexInterval* input,
                                           ComplexInterval* final_input) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < pw::kFinalFftLength;
       index += blockDim.x * gridDim.x) {
    final_input[index] =
        index < pw::kBucketCount
            ? input[index]
            : ComplexInterval{{0.0, 0.0}, {0.0, 0.0}};
  }
}

__global__ void radix2_stage(ComplexInterval* values,
                             const ComplexInterval* roots,
                             std::uint32_t lines,
                             std::uint32_t transform_length,
                             std::uint32_t stage_length) {
  const std::uint64_t butterflies =
      static_cast<std::uint64_t>(lines) * transform_length / 2U;
  const std::uint32_t half = stage_length / 2U;
  const std::uint32_t root_stride = pw::kFinalFftLength / stage_length;
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
    const ComplexInterval first = values[left];
    const ComplexInterval second =
        cmul(values[right], roots[offset * root_stride]);
    values[left] = cadd(first, second);
    values[right] = {sub(first.re, second.re), sub(first.im, second.im)};
  }
}

__global__ void build_power_table(const RealInterval* residuals,
                                  RealInterval* powers,
                                  std::uint32_t terms,
                                  std::uint32_t stages) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    RealInterval power{1.0, 1.0};
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      powers[static_cast<std::uint64_t>(stage) * terms + index] = power;
      power = mul(power, residuals[index]);
    }
  }
}

__global__ void accumulate_all_stages(
    const std::uint32_t* offsets, const std::uint32_t* active_buckets,
    const ComplexInterval* values, const RealInterval* powers,
    std::uint32_t terms, std::uint32_t active_count,
    std::uint32_t stage_count, ComplexInterval* output) {
  const std::uint32_t flat_block = blockIdx.x;
  const std::uint32_t stage = flat_block / active_count;
  const std::uint32_t active_index = flat_block % active_count;
  if (stage >= stage_count) return;
  const std::uint32_t lane = threadIdx.x;
  const std::uint32_t bucket = active_buckets[active_index];
  const std::uint32_t begin = offsets[bucket];
  const std::uint32_t end = offsets[bucket + 1U];
  ComplexInterval sum{{0.0, 0.0}, {0.0, 0.0}};
  for (std::uint32_t term = begin + lane; term < end; term += 32U) {
    const ComplexInterval contribution =
        stage == 0U
            ? values[term]
            : cscale(values[term],
                     powers[static_cast<std::uint64_t>(stage) * terms + term]);
    sum = cadd(sum, contribution);
  }
  for (std::uint32_t delta = 16U; delta != 0U; delta >>= 1U) {
    const ComplexInterval other{
        {__shfl_down_sync(0xffffffffU, sum.re.lo, delta),
         __shfl_down_sync(0xffffffffU, sum.re.hi, delta)},
        {__shfl_down_sync(0xffffffffU, sum.im.lo, delta),
         __shfl_down_sync(0xffffffffU, sum.im.hi, delta)}};
    if (lane < delta) sum = cadd(sum, other);
  }
  if (lane == 0U) {
    output[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] = sum;
  }
}

__global__ void advance_phase(ComplexInterval* values,
                              const ComplexInterval* phase_steps,
                              std::uint32_t terms) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < terms; index += blockDim.x * gridDim.x) {
    values[index] = cmul(values[index], phase_steps[index]);
  }
}

__global__ void synthesize_gamma_row(GammaTaylorProjection projection,
                                     ComplexInterval* gamma_values) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < pw::kBucketCount; index += blockDim.x * gridDim.x) {
    const int grid_offset = static_cast<int>(index) -
                            static_cast<int>(pw::kBucketCount / 2U);
    // The source grid spacing 21/128 is exactly representable in binary64.
    const double u_value =
        static_cast<double>(grid_offset) * (21.0 / 128.0);
    const RealInterval u{u_value, u_value};

    RealInterval real_log = projection.real_coefficients[5];
    for (int degree = 4; degree >= 0; --degree) {
      real_log = add(mul(real_log, u),
                     projection.real_coefficients[degree]);
    }
    const RealInterval u_squared = mul(u, u);
    const RealInterval inverse_gaussian_denominator{
        __ddiv_rd(1.0, 26912.0), __ddiv_ru(1.0, 26912.0)};
    const RealInterval gaussian =
        mul(u_squared, inverse_gaussian_denominator);
    real_log = sub(real_log, gaussian);
    real_log = widen_symmetric(real_log, projection.logarithm_remainder);
    const RealInterval amplitude = exp_interval(real_log);

    RealInterval residual_phase = projection.imaginary_coefficients[5];
    for (int degree = 4; degree >= 2; --degree) {
      residual_phase = add(mul(residual_phase, u),
                           projection.imaginary_coefficients[degree]);
    }
    residual_phase = mul(mul(residual_phase, u), u);
    residual_phase = widen_symmetric(
        residual_phase, projection.logarithm_remainder);
    const ComplexInterval anchor = fixed_anchor_step_phase(
        projection.phase_anchor, projection.phase_grid_step, grid_offset,
        projection.phase_anchor_error, projection.phase_grid_step_error);
    const ComplexInterval residual = sin_cos_small_signed(residual_phase);
    gamma_values[index] = cscale(cmul(anchor, residual), amplitude);
  }
}

std::uint64_t checksum_output(const std::vector<ComplexInterval>& values) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = reinterpret_cast<const unsigned char*>(values.data());
  const std::size_t size = values.size() * sizeof(ComplexInterval);
  for (std::size_t index = 0; index < size; ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

std::uint64_t checksum_bytes(const void* raw, std::size_t size) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = static_cast<const unsigned char*>(raw);
  for (std::size_t index = 0; index < size; ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

struct LoadedDDGammaRow {
  std::vector<pw::ComplexDisk106> values;
  std::string sha256;
};

LoadedDDGammaRow load_dd_gamma_row(const std::string& path,
                                   std::uint64_t expected_height) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "two-limb Gamma row requires a little-endian host");
  }
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open two-limb Gamma row");
  const std::streampos end = input.tellg();
  if (end < 0 || static_cast<std::uint64_t>(end) >
                     std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("two-limb Gamma row has invalid size");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  if (!input || input.peek() != std::ifstream::traits_type::eof() ||
      bytes.size() < sizeof(pw::SourcePacketHeader)) {
    throw std::runtime_error("cannot read complete two-limb Gamma row");
  }
  pw::SourcePacketHeader header{};
  std::memcpy(&header, bytes.data(), sizeof(header));
  const std::uint64_t payload_bytes =
      static_cast<std::uint64_t>(pw::kBucketCount) *
      sizeof(pw::ComplexDisk106);
  if (header.magic != pw::kGammaPacket106Magic ||
      header.version != pw::kSourcePacket106Version ||
      header.header_bytes != sizeof(header) ||
      header.endian_tag != pw::kSourcePacketEndianTag ||
      header.interval_encoding != pw::kSourcePacket106Encoding ||
      header.bucket_count != pw::kBucketCount ||
      header.taylor_terms < 6U || header.taylor_terms > 16U ||
      header.source_terms != 0U ||
      header.reserved_zero != 0U ||
      header.window_center != expected_height ||
      header.gamma_count != pw::kBucketCount || header.skn_count != 0U ||
      header.payload_bytes != payload_bytes ||
      bytes.size() != sizeof(header) + payload_bytes ||
      std::memcmp(header.upstream_commit.data(), pw::kUpstreamCommit,
                  header.upstream_commit.size()) != 0) {
    throw std::runtime_error(
        "two-limb Gamma row differs from the fixed source schema");
  }
  const void* payload = bytes.data() + sizeof(header);
  if (checksum_bytes(payload, payload_bytes) != header.gamma_fnv1a64 ||
      header.skn_fnv1a64 != checksum_bytes(nullptr, 0U)) {
    throw std::runtime_error("two-limb Gamma row checksum mismatch");
  }
  LoadedDDGammaRow result;
  result.values.resize(pw::kBucketCount);
  std::memcpy(result.values.data(), payload, payload_bytes);
  for (const pw::ComplexDisk106 value : result.values) {
    if (!std::isfinite(value.real.hi) || !std::isfinite(value.real.lo) ||
        !std::isfinite(value.imaginary.hi) ||
        !std::isfinite(value.imaginary.lo) ||
        !std::isfinite(value.radius) || value.radius < 0.0) {
      throw std::runtime_error(
          "two-limb Gamma row contains an invalid disk");
    }
  }
  result.sha256 = sparkinterval::sha256_hex(bytes.data(), bytes.size());
  return result;
}

struct SourcePacketExport {
  std::string sha256;
  std::uint64_t bytes;
  std::uint64_t gamma_fnv1a64;
  std::uint64_t skn_fnv1a64;
};

SourcePacketExport write_source_packet(
    const std::string& path, const Options& options,
    const std::vector<ComplexInterval>& gamma,
    const std::vector<ComplexInterval>& skn) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "PT21 source packet export requires a little-endian host");
  }
  const std::uint64_t expected_gamma = pw::kBucketCount;
  const std::uint64_t expected_skn =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  if (gamma.size() != expected_gamma || skn.size() != expected_skn) {
    throw std::runtime_error(
        "PT21 source packet payload has the wrong fixed geometry");
  }

  pw::SourcePacketHeader header{};
  header.magic = pw::kSourcePacketMagic;
  header.version = pw::kSourcePacketVersion;
  header.header_bytes = sizeof(pw::SourcePacketHeader);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.interval_encoding = pw::kSourcePacketIntervalEncoding;
  header.bucket_count = pw::kBucketCount;
  header.taylor_terms = pw::kTaylorTerms;
  header.source_terms = options.terms;
  header.reserved_zero = 0U;
  header.window_center = pw::kSourceLower + pw::kWindowStep / 2U;
  header.gamma_count = gamma.size();
  header.skn_count = skn.size();
  header.payload_bytes =
      (gamma.size() + skn.size()) * sizeof(ComplexInterval);
  header.gamma_fnv1a64 = checksum_output(gamma);
  header.skn_fnv1a64 = checksum_output(skn);
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());

  const std::uint64_t total_bytes = sizeof(header) + header.payload_bytes;
  if (total_bytes > std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("PT21 source packet exceeds host address space");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(total_bytes));
  std::size_t offset = 0U;
  std::memcpy(bytes.data() + offset, &header, sizeof(header));
  offset += sizeof(header);
  const std::size_t gamma_bytes = gamma.size() * sizeof(ComplexInterval);
  std::memcpy(bytes.data() + offset, gamma.data(), gamma_bytes);
  offset += gamma_bytes;
  const std::size_t skn_bytes = skn.size() * sizeof(ComplexInterval);
  std::memcpy(bytes.data() + offset, skn.data(), skn_bytes);
  offset += skn_bytes;
  if (offset != bytes.size()) {
    throw std::runtime_error("PT21 source packet byte accounting failed");
  }

  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) throw std::runtime_error("cannot open source packet output");
  output.write(reinterpret_cast<const char*>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  output.close();
  if (!output) throw std::runtime_error("cannot write complete source packet");
  return {sparkinterval::sha256_hex(bytes.data(), bytes.size()), total_bytes,
          header.gamma_fnv1a64, header.skn_fnv1a64};
}

SourcePacketExport write_source_dd_packet(
    const std::string& path, const Options& options,
    const std::vector<pw::ComplexDisk106>& gamma,
    const std::vector<pw::ComplexDisk106>& skn) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "two-limb source packet export requires a little-endian host");
  }
  const std::uint64_t expected_skn =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  if (gamma.size() != pw::kBucketCount || skn.size() != expected_skn) {
    throw std::runtime_error(
        "two-limb source packet payload has the wrong fixed geometry");
  }
  pw::SourcePacketHeader header{};
  header.magic = pw::kSourcePacket106Magic;
  header.version = pw::kSourcePacket106Version;
  header.header_bytes = sizeof(header);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.interval_encoding = pw::kSourcePacket106Encoding;
  header.bucket_count = pw::kBucketCount;
  header.taylor_terms = pw::kTaylorTerms;
  header.source_terms = options.terms;
  header.reserved_zero = 0U;
  header.window_center = pw::kSourceLower + pw::kWindowStep / 2U;
  header.gamma_count = gamma.size();
  header.skn_count = skn.size();
  header.payload_bytes =
      (gamma.size() + skn.size()) * sizeof(pw::ComplexDisk106);
  const std::size_t gamma_bytes = gamma.size() * sizeof(pw::ComplexDisk106);
  const std::size_t skn_bytes = skn.size() * sizeof(pw::ComplexDisk106);
  header.gamma_fnv1a64 = checksum_bytes(gamma.data(), gamma_bytes);
  header.skn_fnv1a64 = checksum_bytes(skn.data(), skn_bytes);
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());
  std::vector<unsigned char> bytes(sizeof(header) + header.payload_bytes);
  std::size_t offset = 0U;
  std::memcpy(bytes.data(), &header, sizeof(header));
  offset += sizeof(header);
  std::memcpy(bytes.data() + offset, gamma.data(), gamma_bytes);
  offset += gamma_bytes;
  std::memcpy(bytes.data() + offset, skn.data(), skn_bytes);
  offset += skn_bytes;
  if (offset != bytes.size()) {
    throw std::runtime_error("two-limb source packet byte accounting failed");
  }
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) throw std::runtime_error("cannot open two-limb source packet");
  output.write(reinterpret_cast<const char*>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  output.close();
  if (!output) {
    throw std::runtime_error("cannot write complete two-limb source packet");
  }
  return {sparkinterval::sha256_hex(bytes.data(), bytes.size()), bytes.size(),
          header.gamma_fnv1a64, header.skn_fnv1a64};
}

void require_device(cudaDeviceProp* properties) {
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties->major != 9 || properties->minor != 0 ||
      std::strstr(properties->name, "H100") == nullptr) {
    throw std::runtime_error(
        "strict production target requires an NVIDIA H100 sm_90 device");
  }
#endif
}

int run(const Options& options) {
  cudaDeviceProp properties{};
  require_device(&properties);
  const HostTerms host = initialize_terms(options);
  LoadedDDGammaRow loaded_dd_gamma;
  const bool source_dd_packet_exported =
      !options.export_source_dd_packet.empty();
  const bool source_dd_enabled =
      source_dd_packet_exported || options.dd_source_blocks != 0U;
  SourceDDTrigData source_dd_trig;
  if (source_dd_enabled) source_dd_trig = initialize_source_dd_trig_data();
  if (source_dd_packet_exported) {
    loaded_dd_gamma = load_dd_gamma_row(
        options.dd_gamma_row,
        pw::kSourceLower + pw::kWindowStep / 2U);
  }
  const std::vector<ComplexInterval> fft_roots =
      options.fft_passes == 0U ? std::vector<ComplexInterval>{}
                               : initialize_fft_roots();
  const std::uint64_t power_cells =
      static_cast<std::uint64_t>(options.terms) * options.stages;
  if (power_cells > std::numeric_limits<std::size_t>::max() /
                        sizeof(RealInterval)) {
    throw std::runtime_error("power table exceeds host address space");
  }

  std::uint32_t* device_offsets = nullptr;
  std::uint32_t* device_active = nullptr;
  RealInterval* device_residuals = nullptr;
  RealInterval* device_amplitudes = nullptr;
  RealInterval* device_powers = nullptr;
  pw::FixedTurn192* device_fixed_turns = nullptr;
  ComplexInterval* device_initial_values = nullptr;
  ComplexInterval* device_values = nullptr;
  ComplexInterval* device_phase_steps = nullptr;
  ComplexInterval* device_output = nullptr;
  ComplexInterval* device_fft_roots = nullptr;
  ComplexInterval* device_fft_workspace = nullptr;
  ComplexInterval* device_final_fft_input = nullptr;
  ComplexInterval* device_final_fft_workspace = nullptr;
  ComplexInterval* device_gamma_values = nullptr;
  pw::RealDisk106* device_narrow_residuals = nullptr;
  pw::RealDisk106* device_narrow_amplitudes = nullptr;
  pw::RealDisk106* device_narrow_powers = nullptr;
  pw::RealDisk106* device_dd_sine_coefficients = nullptr;
  pw::RealDisk106* device_dd_cosine_coefficients = nullptr;
  pw::ComplexDisk106* device_narrow_values = nullptr;
  pw::ComplexDisk106* device_narrow_phase_steps = nullptr;
  pw::ComplexDisk106* device_narrow_output = nullptr;
  pw::ComplexDisk106* device_narrow_output_legacy = nullptr;

  CUDA_CHECK(cudaMalloc(&device_offsets,
                        host.offsets.size() * sizeof(std::uint32_t)));
  CUDA_CHECK(cudaMalloc(&device_active,
                        host.active_buckets.size() * sizeof(std::uint32_t)));
  CUDA_CHECK(cudaMalloc(&device_residuals,
                        host.residuals.size() * sizeof(RealInterval)));
  CUDA_CHECK(cudaMalloc(&device_amplitudes,
                        host.amplitudes.size() * sizeof(RealInterval)));
  CUDA_CHECK(cudaMalloc(&device_powers,
                        static_cast<std::size_t>(power_cells) *
                            sizeof(RealInterval)));
  CUDA_CHECK(cudaMalloc(&device_fixed_turns,
                        host.fixed_turns.size() * sizeof(pw::FixedTurn192)));
  CUDA_CHECK(cudaMalloc(&device_initial_values,
                        host.values.size() * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&device_values,
                        host.values.size() * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&device_phase_steps,
                        host.phase_steps.size() * sizeof(ComplexInterval)));
  CUDA_CHECK(cudaMalloc(&device_output,
                        static_cast<std::size_t>(options.stages) *
                            pw::kBucketCount * sizeof(ComplexInterval)));
  if (options.fft_passes != 0U) {
    CUDA_CHECK(cudaMalloc(&device_fft_roots,
                          fft_roots.size() * sizeof(ComplexInterval)));
    CUDA_CHECK(cudaMalloc(&device_fft_workspace,
                          static_cast<std::size_t>(options.stages) *
                              pw::kBucketCount * sizeof(ComplexInterval)));
    CUDA_CHECK(cudaMalloc(&device_final_fft_input,
                          pw::kFinalFftLength * sizeof(ComplexInterval)));
    CUDA_CHECK(cudaMalloc(&device_final_fft_workspace,
                          pw::kFinalFftLength * sizeof(ComplexInterval)));
  }
  if (options.gamma_synthesis) {
    CUDA_CHECK(cudaMalloc(&device_gamma_values,
                          pw::kBucketCount * sizeof(ComplexInterval)));
  }
  if (source_dd_enabled) {
    CUDA_CHECK(cudaMalloc(&device_narrow_residuals,
                          host.narrow_residuals.size() *
                              sizeof(pw::RealDisk106)));
    CUDA_CHECK(cudaMalloc(&device_narrow_amplitudes,
                          host.narrow_amplitudes.size() *
                              sizeof(pw::RealDisk106)));
    CUDA_CHECK(cudaMalloc(&device_narrow_powers,
                          static_cast<std::size_t>(power_cells) *
                              sizeof(pw::RealDisk106)));
    CUDA_CHECK(cudaMalloc(&device_dd_sine_coefficients,
                          source_dd_trig.sine_coefficients.size() *
                              sizeof(pw::RealDisk106)));
    CUDA_CHECK(cudaMalloc(&device_dd_cosine_coefficients,
                          source_dd_trig.cosine_coefficients.size() *
                              sizeof(pw::RealDisk106)));
    CUDA_CHECK(cudaMalloc(&device_narrow_values,
                          host.narrow_values.size() *
                              sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMalloc(&device_narrow_phase_steps,
                          host.narrow_values.size() *
                              sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMalloc(&device_narrow_output,
                          static_cast<std::size_t>(options.stages) *
                              pw::kBucketCount *
                              sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMalloc(&device_narrow_output_legacy,
                          static_cast<std::size_t>(options.stages) *
                              pw::kBucketCount *
                              sizeof(pw::ComplexDisk106)));
  }

  CUDA_CHECK(cudaMemcpy(device_offsets, host.offsets.data(),
                        host.offsets.size() * sizeof(std::uint32_t),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device_active, host.active_buckets.data(),
                        host.active_buckets.size() * sizeof(std::uint32_t),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device_residuals, host.residuals.data(),
                        host.residuals.size() * sizeof(RealInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device_amplitudes, host.amplitudes.data(),
                        host.amplitudes.size() * sizeof(RealInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device_fixed_turns, host.fixed_turns.data(),
                        host.fixed_turns.size() * sizeof(pw::FixedTurn192),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device_initial_values, host.values.data(),
                        host.values.size() * sizeof(ComplexInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device_phase_steps, host.phase_steps.data(),
                        host.phase_steps.size() * sizeof(ComplexInterval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(device_output, 0,
                        static_cast<std::size_t>(options.stages) *
                            pw::kBucketCount * sizeof(ComplexInterval)));
  if (options.fft_passes != 0U) {
    CUDA_CHECK(cudaMemcpy(device_fft_roots, fft_roots.data(),
                          fft_roots.size() * sizeof(ComplexInterval),
                          cudaMemcpyHostToDevice));
  }
  if (source_dd_enabled) {
    CUDA_CHECK(cudaMemcpy(device_narrow_residuals,
                          host.narrow_residuals.data(),
                          host.narrow_residuals.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_narrow_amplitudes,
                          host.narrow_amplitudes.data(),
                          host.narrow_amplitudes.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_dd_sine_coefficients,
                          source_dd_trig.sine_coefficients.data(),
                          source_dd_trig.sine_coefficients.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_dd_cosine_coefficients,
                          source_dd_trig.cosine_coefficients.data(),
                          source_dd_trig.cosine_coefficients.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemset(device_narrow_output, 0,
                          static_cast<std::size_t>(options.stages) *
                              pw::kBucketCount *
                              sizeof(pw::ComplexDisk106)));
    CUDA_CHECK(cudaMemset(device_narrow_output_legacy, 0,
                          static_cast<std::size_t>(options.stages) *
                              pw::kBucketCount *
                              sizeof(pw::ComplexDisk106)));
  }

  constexpr std::uint32_t threads = 256U;
  const std::uint32_t term_blocks =
      std::min<std::uint32_t>((options.terms + threads - 1U) / threads, 4096U);
  std::uint64_t source_dd_anchor_kat_failures = 0U;
  const std::uint64_t source_dd_anchor_kat_height =
      pw::kSourceLower + pw::kWindowStep / 2U +
      options.dd_source_start_block * pw::kWindowStep;
  std::uint32_t source_dd_anchor_kat_first_failure = 0U;
  double source_dd_anchor_kat_first_required = 0.0;
  double source_dd_anchor_kat_first_output = 0.0;
  double source_dd_anchor_kat_max_required_radius = 0.0;
  double source_dd_anchor_kat_max_output_radius = 0.0;
  if (options.source_geometry) {
    anchor_fixed_phases<<<term_blocks, threads>>>(
        device_fixed_turns, device_amplitudes,
        pw::kSourceLower + pw::kWindowStep / 2U, device_initial_values,
        options.terms);
    construct_fixed_phase_steps<<<term_blocks, threads>>>(
        device_fixed_turns, device_phase_steps, options.terms);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    std::vector<ComplexInterval> fixed_initial(options.terms);
    std::vector<ComplexInterval> fixed_steps(options.terms);
    CUDA_CHECK(cudaMemcpy(fixed_initial.data(), device_initial_values,
                          fixed_initial.size() * sizeof(ComplexInterval),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(fixed_steps.data(), device_phase_steps,
                          fixed_steps.size() * sizeof(ComplexInterval),
                          cudaMemcpyDeviceToHost));
    auto contains_midpoint = [](RealInterval enclosure,
                                RealInterval reference) {
      const double midpoint = reference.lo / 2.0 + reference.hi / 2.0;
      return std::isfinite(enclosure.lo) && std::isfinite(enclosure.hi) &&
             enclosure.lo <= midpoint && midpoint <= enclosure.hi;
    };
    for (std::uint32_t index = 0; index < options.terms; ++index) {
      if (!contains_midpoint(fixed_initial[index].re, host.values[index].re) ||
          !contains_midpoint(fixed_initial[index].im, host.values[index].im) ||
          !contains_midpoint(fixed_steps[index].re,
                             host.phase_steps[index].re) ||
          !contains_midpoint(fixed_steps[index].im,
                             host.phase_steps[index].im)) {
        throw std::runtime_error(
            "fixed-turn phase enclosure missed the MPFR audit midpoint at term " +
            std::to_string(index));
      }
    }
  }
  if (source_dd_enabled) {
    source_dd_anchor_fixed_phases<<<term_blocks, threads>>>(
        device_fixed_turns, device_narrow_amplitudes,
        source_dd_anchor_kat_height, source_dd_trig.two_pi,
        device_dd_sine_coefficients, device_dd_cosine_coefficients,
        device_narrow_values, options.terms);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
    std::vector<pw::ComplexDisk106> anchored_values(options.terms);
    CUDA_CHECK(cudaMemcpy(anchored_values.data(), device_narrow_values,
                          anchored_values.size() *
                              sizeof(pw::ComplexDisk106),
                          cudaMemcpyDeviceToHost));
    for (std::uint32_t index = 0; index < options.terms; ++index) {
      const pw::ComplexDisk106& anchored = anchored_values[index];
      if (!std::isfinite(anchored.real.hi) ||
          !std::isfinite(anchored.real.lo) ||
          !std::isfinite(anchored.imaginary.hi) ||
          !std::isfinite(anchored.imaginary.lo) ||
          !std::isfinite(anchored.radius) || anchored.radius < 0.0) {
        throw std::runtime_error(
            "Q192 two-limb re-anchor produced an invalid disk at term " +
            std::to_string(index));
      }
      const double required = source_dd_required_truth_radius(
          anchored, host.one_based_ns[index], source_dd_anchor_kat_height);
      source_dd_anchor_kat_max_required_radius =
          std::max(source_dd_anchor_kat_max_required_radius, required);
      source_dd_anchor_kat_max_output_radius =
          std::max(source_dd_anchor_kat_max_output_radius, anchored.radius);
      if (!(required <= anchored.radius)) {
        if (source_dd_anchor_kat_failures == 0U) {
          source_dd_anchor_kat_first_failure = index;
          source_dd_anchor_kat_first_required = required;
          source_dd_anchor_kat_first_output = anchored.radius;
        }
        ++source_dd_anchor_kat_failures;
      }
    }
    if (source_dd_anchor_kat_failures != 0U) {
      std::cerr << std::setprecision(17) << std::scientific
                << "first Q192 KAT failure term="
                << source_dd_anchor_kat_first_failure
                << " required_radius="
                << source_dd_anchor_kat_first_required
                << " output_radius="
                << source_dd_anchor_kat_first_output << '\n'
                << std::defaultfloat;
      throw std::runtime_error(
          "Q192 two-limb re-anchor failed the independent first-window "
          "MPFR containment KAT for " +
          std::to_string(source_dd_anchor_kat_failures) +
          " terms; first term=" +
          std::to_string(source_dd_anchor_kat_first_failure) +
          " required=" +
          std::to_string(source_dd_anchor_kat_first_required) +
          " output=" + std::to_string(source_dd_anchor_kat_first_output));
    }
  }
  build_power_table<<<term_blocks, threads>>>(
      device_residuals, device_powers, options.terms, options.stages);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  if (source_dd_enabled) {
    source_dd_build_power_table<<<term_blocks, threads>>>(
        device_narrow_residuals, device_narrow_powers, options.terms,
        options.stages);
    source_dd_construct_phase_steps<<<term_blocks, threads>>>(
        device_fixed_turns, source_dd_trig.two_pi,
        device_dd_sine_coefficients, device_dd_cosine_coefficients,
        device_narrow_phase_steps, options.terms);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
  }

  cudaEvent_t start{};
  cudaEvent_t stop{};
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  double dd_source_elapsed_seconds = 0.0;
  double dd_source_term_visits_per_second = 0.0;
  double dd_source_stream_elapsed_seconds = 0.0;
  double dd_source_stream_blocks_per_second = 0.0;
  double dd_source_stream_term_visits_per_second = 0.0;
  std::uint64_t dd_source_stream_output_fnv1a64 = 0U;
  std::uint64_t dd_source_recurrence_kat_samples = 0U;
  std::uint64_t dd_source_recurrence_kat_failures = 0U;
  double dd_source_recurrence_kat_max_required_radius = 0.0;
  double dd_source_recurrence_kat_max_output_radius = 0.0;
  std::uint64_t dd_accumulator_mpfr_kat_samples = 0U;
  std::uint64_t dd_accumulator_legacy_kat_failures = 0U;
  std::uint64_t dd_accumulator_compressed_kat_failures = 0U;
  double dd_accumulator_legacy_elapsed_seconds = 0.0;
  double dd_accumulator_compressed_elapsed_seconds = 0.0;
  double dd_accumulator_kat_max_required_radius = 0.0;
  double dd_accumulator_kat_max_legacy_radius = 0.0;
  double dd_accumulator_kat_max_compressed_radius = 0.0;
  double dd_accumulator_kat_max_radius_ratio = 0.0;
  std::vector<pw::ComplexDisk106> narrow_output;
  SourcePacketExport source_dd_packet{};
  if (source_dd_enabled) {
    const auto active_count =
        static_cast<std::uint32_t>(host.active_buckets.size());
    const auto legacy_blocks =
        static_cast<unsigned>(active_count * options.stages);
    const auto compressed_blocks = static_cast<unsigned>(active_count);

    // Warm both paths before the one-window differential timing.  The legacy
    // result remains available solely as an independent implementation KAT.
    source_dd_accumulate_all_stages_legacy<<<legacy_blocks, 32U>>>(
        device_offsets, device_active, device_narrow_values,
        device_narrow_powers, options.terms, active_count, options.stages,
        device_narrow_output_legacy);
    source_dd_accumulate_all_stages<<<
        compressed_blocks, kSourceDDAccumulatorWarps * 32U>>>(
        device_offsets, device_active, device_narrow_values,
        device_narrow_powers, options.terms, active_count, options.stages,
        device_narrow_output);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    CUDA_CHECK(cudaEventRecord(start));
    source_dd_accumulate_all_stages_legacy<<<legacy_blocks, 32U>>>(
        device_offsets, device_active, device_narrow_values,
        device_narrow_powers, options.terms, active_count, options.stages,
        device_narrow_output_legacy);
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float legacy_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&legacy_ms, start, stop));
    dd_accumulator_legacy_elapsed_seconds =
        static_cast<double>(legacy_ms) / 1000.0;

    CUDA_CHECK(cudaEventRecord(start));
    source_dd_accumulate_all_stages<<<
        compressed_blocks, kSourceDDAccumulatorWarps * 32U>>>(
        device_offsets, device_active, device_narrow_values,
        device_narrow_powers, options.terms, active_count, options.stages,
        device_narrow_output);
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float compressed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&compressed_ms, start, stop));
    dd_accumulator_compressed_elapsed_seconds =
        static_cast<double>(compressed_ms) / 1000.0;

    const std::size_t output_cells =
        static_cast<std::size_t>(options.stages) * pw::kBucketCount;
    std::vector<pw::ComplexDisk106> legacy_output(output_cells);
    std::vector<pw::ComplexDisk106> compressed_output(output_cells);
    CUDA_CHECK(cudaMemcpy(legacy_output.data(), device_narrow_output_legacy,
                          output_cells * sizeof(pw::ComplexDisk106),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(compressed_output.data(), device_narrow_output,
                          output_cells * sizeof(pw::ComplexDisk106),
                          cudaMemcpyDeviceToHost));

    std::vector<std::uint32_t> selected_active;
    auto select_active = [&](std::uint32_t active_index) {
      if (active_index >= active_count) return;
      if (std::find(selected_active.begin(), selected_active.end(),
                    active_index) == selected_active.end()) {
        selected_active.push_back(active_index);
      }
    };
    select_active(0U);
    select_active(active_count / 4U);
    select_active(active_count / 2U);
    select_active((3U * active_count) / 4U);
    select_active(active_count - 1U);
    std::uint32_t largest_active = 0U;
    std::uint32_t largest_terms = 0U;
    for (std::uint32_t active = 0U; active < active_count; ++active) {
      const std::uint32_t bucket = host.active_buckets[active];
      const std::uint32_t count =
          host.offsets[bucket + 1U] - host.offsets[bucket];
      if (count > largest_terms) {
        largest_terms = count;
        largest_active = active;
      }
    }
    select_active(largest_active);

    std::vector<std::uint32_t> selected_stages;
    auto select_stage = [&](std::uint32_t stage) {
      if (stage >= options.stages) return;
      if (std::find(selected_stages.begin(), selected_stages.end(), stage) ==
          selected_stages.end()) {
        selected_stages.push_back(stage);
      }
    };
    select_stage(0U);
    select_stage(1U);
    select_stage(options.stages / 2U);
    select_stage(options.stages - 1U);

    for (const std::uint32_t active : selected_active) {
      const std::uint32_t bucket = host.active_buckets[active];
      const std::uint32_t begin = host.offsets[bucket];
      const std::uint32_t end = host.offsets[bucket + 1U];
      const std::size_t count = end - begin;
      std::vector<pw::ComplexDisk106> values(count);
      CUDA_CHECK(cudaMemcpy(values.data(), device_narrow_values + begin,
                            count * sizeof(pw::ComplexDisk106),
                            cudaMemcpyDeviceToHost));
      for (const std::uint32_t stage : selected_stages) {
        std::vector<pw::RealDisk106> powers;
        if (stage != 0U) {
          powers.resize(count);
          const std::uint64_t power_begin =
              static_cast<std::uint64_t>(stage) * options.terms + begin;
          CUDA_CHECK(cudaMemcpy(powers.data(),
                                device_narrow_powers + power_begin,
                                count * sizeof(pw::RealDisk106),
                                cudaMemcpyDeviceToHost));
        }
        const std::size_t cell =
            static_cast<std::size_t>(stage) * pw::kBucketCount + bucket;
        const double legacy_required =
            source_dd_accumulator_required_radius(
                values, powers, legacy_output[cell]);
        const double compressed_required =
            source_dd_accumulator_required_radius(
                values, powers, compressed_output[cell]);
        ++dd_accumulator_mpfr_kat_samples;
        dd_accumulator_kat_max_required_radius = std::max(
            dd_accumulator_kat_max_required_radius,
            std::max(legacy_required, compressed_required));
        dd_accumulator_kat_max_legacy_radius = std::max(
            dd_accumulator_kat_max_legacy_radius,
            legacy_output[cell].radius);
        dd_accumulator_kat_max_compressed_radius = std::max(
            dd_accumulator_kat_max_compressed_radius,
            compressed_output[cell].radius);
        if (legacy_output[cell].radius > 0.0) {
          dd_accumulator_kat_max_radius_ratio = std::max(
              dd_accumulator_kat_max_radius_ratio,
              compressed_output[cell].radius / legacy_output[cell].radius);
        }
        if (!(legacy_required <= legacy_output[cell].radius)) {
          ++dd_accumulator_legacy_kat_failures;
        }
        if (!(compressed_required <= compressed_output[cell].radius)) {
          ++dd_accumulator_compressed_kat_failures;
        }
      }
    }
    if (dd_accumulator_legacy_kat_failures != 0U ||
        dd_accumulator_compressed_kat_failures != 0U) {
      throw std::runtime_error(
          "legacy/compressed accumulator failed directed MPFR differential KAT");
    }
  }
  if (source_dd_packet_exported) {
    const std::uint64_t accumulator_blocks =
        static_cast<std::uint64_t>(host.active_buckets.size());
    CUDA_CHECK(cudaEventRecord(start));
    source_dd_accumulate_all_stages<<<
        static_cast<unsigned>(accumulator_blocks),
        kSourceDDAccumulatorWarps * 32U>>>(
        device_offsets, device_active, device_narrow_values,
        device_narrow_powers, options.terms,
        static_cast<std::uint32_t>(host.active_buckets.size()),
        options.stages, device_narrow_output);
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float dd_source_elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&dd_source_elapsed_ms, start, stop));
    dd_source_elapsed_seconds =
        static_cast<double>(dd_source_elapsed_ms) / 1000.0;
    dd_source_term_visits_per_second =
        static_cast<double>(options.terms) * options.stages /
        dd_source_elapsed_seconds;
    narrow_output.resize(static_cast<std::size_t>(options.stages) *
                         pw::kBucketCount);
    CUDA_CHECK(cudaMemcpy(narrow_output.data(), device_narrow_output,
                          narrow_output.size() *
                              sizeof(pw::ComplexDisk106),
                          cudaMemcpyDeviceToHost));
    for (const pw::ComplexDisk106 value : narrow_output) {
      if (!std::isfinite(value.real.hi) ||
          !std::isfinite(value.real.lo) ||
          !std::isfinite(value.imaginary.hi) ||
          !std::isfinite(value.imaginary.lo) ||
          !std::isfinite(value.radius) || value.radius < 0.0) {
        throw std::runtime_error(
            "two-limb Taylor accumulator produced an invalid disk");
      }
    }
    source_dd_packet = write_source_dd_packet(
        options.export_source_dd_packet, options, loaded_dd_gamma.values,
        narrow_output);
  }
  if (options.dd_source_blocks != 0U) {
    const std::uint64_t accumulator_blocks =
        static_cast<std::uint64_t>(host.active_buckets.size());
    CUDA_CHECK(cudaEventRecord(start));
    for (std::uint32_t block = 0U; block < options.dd_source_blocks;
         ++block) {
      const std::uint64_t logical_block =
          options.dd_source_start_block + block;
      const std::uint64_t height =
          pw::kSourceLower + pw::kWindowStep / 2U +
          logical_block * pw::kWindowStep;
      if (block != 0U) {
        if (block % options.reanchor_blocks == 0U) {
          source_dd_anchor_fixed_phases<<<term_blocks, threads>>>(
              device_fixed_turns, device_narrow_amplitudes, height,
              source_dd_trig.two_pi, device_dd_sine_coefficients,
              device_dd_cosine_coefficients, device_narrow_values,
              options.terms);
        } else {
          source_dd_advance_phase<<<term_blocks, threads>>>(
              device_narrow_values, device_narrow_phase_steps,
              options.terms);
        }
      }
      source_dd_accumulate_all_stages<<<
          static_cast<unsigned>(accumulator_blocks),
          kSourceDDAccumulatorWarps * 32U>>>(
          device_offsets, device_active, device_narrow_values,
          device_narrow_powers, options.terms,
          static_cast<std::uint32_t>(host.active_buckets.size()),
          options.stages, device_narrow_output);
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float dd_source_stream_elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&dd_source_stream_elapsed_ms, start,
                                    stop));
    dd_source_stream_elapsed_seconds =
        static_cast<double>(dd_source_stream_elapsed_ms) / 1000.0;
    dd_source_stream_blocks_per_second =
        options.dd_source_blocks / dd_source_stream_elapsed_seconds;
    dd_source_stream_term_visits_per_second =
        static_cast<double>(options.dd_source_blocks) * options.terms *
        options.stages / dd_source_stream_elapsed_seconds;
    narrow_output.resize(static_cast<std::size_t>(options.stages) *
                         pw::kBucketCount);
    CUDA_CHECK(cudaMemcpy(narrow_output.data(), device_narrow_output,
                          narrow_output.size() *
                              sizeof(pw::ComplexDisk106),
                          cudaMemcpyDeviceToHost));
    // Independent MPFR spot audit at the final streamed height.  This is a
    // KAT, not the physical-refinement proof: the device disk arithmetic and
    // periodic re-anchor remain visible as the single trusted-run boundary.
    std::vector<pw::ComplexDisk106> final_phase_values(options.terms);
    CUDA_CHECK(cudaMemcpy(final_phase_values.data(), device_narrow_values,
                          final_phase_values.size() *
                              sizeof(pw::ComplexDisk106),
                          cudaMemcpyDeviceToHost));
    const std::uint64_t final_height =
        pw::kSourceLower + pw::kWindowStep / 2U +
        (options.dd_source_start_block + options.dd_source_blocks - 1U) *
            pw::kWindowStep;
    const std::uint32_t audit_stride =
        std::max<std::uint32_t>(1U, options.terms / 1024U);
    for (std::uint32_t index = 0U; index < options.terms;
         index += audit_stride) {
      const pw::ComplexDisk106& value = final_phase_values[index];
      const double required = source_dd_required_truth_radius(
          value, host.one_based_ns[index], final_height);
      ++dd_source_recurrence_kat_samples;
      dd_source_recurrence_kat_max_required_radius =
          std::max(dd_source_recurrence_kat_max_required_radius, required);
      dd_source_recurrence_kat_max_output_radius =
          std::max(dd_source_recurrence_kat_max_output_radius,
                   value.radius);
      if (!(required <= value.radius)) {
        ++dd_source_recurrence_kat_failures;
      }
    }
    if (dd_source_recurrence_kat_failures != 0U) {
      throw std::runtime_error(
          "periodic Q192 phase recurrence failed its final-height MPFR KAT");
    }
    for (const pw::ComplexDisk106 value : narrow_output) {
      if (!std::isfinite(value.real.hi) ||
          !std::isfinite(value.real.lo) ||
          !std::isfinite(value.imaginary.hi) ||
          !std::isfinite(value.imaginary.lo) ||
          !std::isfinite(value.radius) || value.radius < 0.0) {
        throw std::runtime_error(
            "streaming two-limb Taylor accumulator produced an invalid "
            "disk");
      }
    }
    dd_source_stream_output_fnv1a64 = checksum_bytes(
        narrow_output.data(),
        narrow_output.size() * sizeof(pw::ComplexDisk106));
  }
  double gamma_elapsed_seconds = 0.0;
  double gamma_values_per_second = 0.0;
  std::uint64_t gamma_checksum = 0U;
  std::vector<ComplexInterval> gamma_values_host;
  if (options.gamma_synthesis) {
    const GammaTaylorProjection gamma_projection =
        source_lower_gamma_projection();
    const std::uint32_t gamma_blocks =
        (pw::kBucketCount + threads - 1U) / threads;
    CUDA_CHECK(cudaEventRecord(start));
    for (std::uint32_t repetition = 0; repetition < options.repetitions;
         ++repetition) {
      for (std::uint32_t block = 0; block < options.blocks; ++block) {
        synthesize_gamma_row<<<gamma_blocks, threads>>>(
            gamma_projection, device_gamma_values);
      }
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float gamma_elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&gamma_elapsed_ms, start, stop));
    gamma_elapsed_seconds = static_cast<double>(gamma_elapsed_ms) / 1000.0;
    gamma_values_per_second =
        static_cast<double>(options.repetitions) * options.blocks *
        pw::kBucketCount / gamma_elapsed_seconds;
    gamma_values_host.resize(pw::kBucketCount);
    CUDA_CHECK(cudaMemcpy(gamma_values_host.data(), device_gamma_values,
                          gamma_values_host.size() * sizeof(ComplexInterval),
                          cudaMemcpyDeviceToHost));
    for (const ComplexInterval& value : gamma_values_host) {
      if (!std::isfinite(value.re.lo) || !std::isfinite(value.re.hi) ||
          !std::isfinite(value.im.lo) || !std::isfinite(value.im.hi) ||
          value.re.lo > value.re.hi || value.im.lo > value.im.hi) {
        throw std::runtime_error(
            "Gamma Taylor synthesis produced an invalid interval");
      }
    }
    gamma_checksum = checksum_output(gamma_values_host);
  }
  double fixed_anchor_terms_per_second = 0.0;
  if (options.source_geometry) {
    constexpr std::uint32_t anchor_repetitions = 8U;
    CUDA_CHECK(cudaEventRecord(start));
    for (std::uint32_t iteration = 0; iteration < anchor_repetitions;
         ++iteration) {
      anchor_fixed_phases<<<term_blocks, threads>>>(
          device_fixed_turns, device_amplitudes,
          pw::kSourceLower + pw::kWindowStep / 2U +
              static_cast<std::uint64_t>(iteration) * pw::kWindowStep,
          device_initial_values, options.terms);
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float anchor_elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&anchor_elapsed_ms, start, stop));
    fixed_anchor_terms_per_second =
        static_cast<double>(anchor_repetitions) * options.terms /
        (static_cast<double>(anchor_elapsed_ms) / 1000.0);
    anchor_fixed_phases<<<term_blocks, threads>>>(
        device_fixed_turns, device_amplitudes,
        pw::kSourceLower + pw::kWindowStep / 2U, device_initial_values,
        options.terms);
    CUDA_CHECK(cudaGetLastError());
  }
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t repetition = 0; repetition < options.repetitions;
       ++repetition) {
    CUDA_CHECK(cudaMemcpyAsync(device_values, device_initial_values,
                               host.values.size() * sizeof(ComplexInterval),
                               cudaMemcpyDeviceToDevice));
    for (std::uint32_t block = 0; block < options.blocks; ++block) {
      if (options.source_geometry && block != 0U &&
          block % options.reanchor_blocks == 0U) {
        anchor_fixed_phases<<<term_blocks, threads>>>(
            device_fixed_turns, device_amplitudes,
            pw::kSourceLower + pw::kWindowStep / 2U +
                static_cast<std::uint64_t>(block) * pw::kWindowStep,
            device_values, options.terms);
      }
      const std::uint64_t accumulator_blocks =
          static_cast<std::uint64_t>(host.active_buckets.size()) *
          options.stages;
      accumulate_all_stages<<<static_cast<unsigned>(accumulator_blocks), 32U>>>(
          device_offsets, device_active, device_values, device_powers,
          options.terms,
          static_cast<std::uint32_t>(host.active_buckets.size()),
          options.stages, device_output);
      if (block + 1U != options.blocks &&
          (!options.source_geometry ||
           (block + 1U) % options.reanchor_blocks != 0U)) {
        advance_phase<<<term_blocks, threads>>>(
            device_values, device_phase_steps, options.terms);
      }
    }
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  CUDA_CHECK(cudaGetLastError());
  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));

  std::vector<ComplexInterval> output(
      static_cast<std::size_t>(options.stages) * pw::kBucketCount);
  CUDA_CHECK(cudaMemcpy(output.data(), device_output,
                        output.size() * sizeof(ComplexInterval),
                        cudaMemcpyDeviceToHost));
  for (const ComplexInterval& value : output) {
    if (!std::isfinite(value.re.lo) || !std::isfinite(value.re.hi) ||
        !std::isfinite(value.im.lo) || !std::isfinite(value.im.hi) ||
        value.re.lo > value.re.hi || value.im.lo > value.im.hi) {
      throw std::runtime_error(
          "Taylor accumulator produced a non-finite or reversed interval");
    }
  }
  const std::uint64_t checksum = checksum_output(output);
  SourcePacketExport source_packet{};
  const bool source_packet_exported = !options.export_source_packet.empty();
  if (source_packet_exported) {
    source_packet = write_source_packet(options.export_source_packet, options,
                                        gamma_values_host, output);
  }
  double fft_elapsed_seconds = 0.0;
  std::uint64_t fft_butterflies = 0U;
  double fft_butterflies_per_second = 0.0;
  if (options.fft_passes != 0U) {
    const std::uint64_t logical_runs =
        static_cast<std::uint64_t>(options.repetitions) * options.blocks;
    const std::uint64_t batched_items =
        static_cast<std::uint64_t>(options.stages) * pw::kBucketCount;
    const std::uint32_t batched_blocks = static_cast<std::uint32_t>(
        std::min<std::uint64_t>((batched_items + threads - 1U) / threads,
                                4096U));
    const std::uint32_t final_blocks =
        (pw::kFinalFftLength + threads - 1U) / threads;
    CUDA_CHECK(cudaEventRecord(start));
    for (std::uint64_t logical = 0; logical < logical_runs; ++logical) {
      for (std::uint32_t pass = 0; pass < options.fft_passes; ++pass) {
        bit_reverse_lines<<<batched_blocks, threads>>>(
            device_output, device_fft_workspace, options.stages,
            pw::kBucketCount, 15U);
        for (std::uint32_t stage_length = 2U;
             stage_length <= pw::kBucketCount; stage_length <<= 1U) {
          radix2_stage<<<batched_blocks, threads>>>(
              device_fft_workspace, device_fft_roots, options.stages,
              pw::kBucketCount, stage_length);
        }
      }
      initialize_final_fft_input<<<final_blocks, threads>>>(
          device_output, device_final_fft_input);
      bit_reverse_lines<<<final_blocks, threads>>>(
          device_final_fft_input, device_final_fft_workspace, 1U,
          pw::kFinalFftLength, 16U);
      for (std::uint32_t stage_length = 2U;
           stage_length <= pw::kFinalFftLength; stage_length <<= 1U) {
        radix2_stage<<<final_blocks, threads>>>(
            device_final_fft_workspace, device_fft_roots, 1U,
            pw::kFinalFftLength, stage_length);
      }
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float fft_elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&fft_elapsed_ms, start, stop));
    fft_elapsed_seconds = static_cast<double>(fft_elapsed_ms) / 1000.0;
    const std::uint64_t batched_per_run =
        static_cast<std::uint64_t>(options.fft_passes) * options.stages *
        (pw::kBucketCount / 2U) * 15U;
    const std::uint64_t final_per_run =
        static_cast<std::uint64_t>(pw::kFinalFftLength / 2U) * 16U;
    fft_butterflies = logical_runs * (batched_per_run + final_per_run);
    fft_butterflies_per_second =
        static_cast<double>(fft_butterflies) / fft_elapsed_seconds;
    std::vector<ComplexInterval> final_fft(pw::kFinalFftLength);
    CUDA_CHECK(cudaMemcpy(final_fft.data(), device_final_fft_workspace,
                          final_fft.size() * sizeof(ComplexInterval),
                          cudaMemcpyDeviceToHost));
    for (const ComplexInterval& value : final_fft) {
      if (!std::isfinite(value.re.lo) || !std::isfinite(value.re.hi) ||
          !std::isfinite(value.im.lo) || !std::isfinite(value.im.hi) ||
          value.re.lo > value.re.hi || value.im.lo > value.im.hi) {
        throw std::runtime_error(
            "batched FFT produced a non-finite or reversed interval");
      }
    }
  }
  const std::uint64_t term_visits =
      static_cast<std::uint64_t>(options.repetitions) * options.blocks *
      options.stages * options.terms;
  const double elapsed_seconds = static_cast<double>(elapsed_ms) / 1000.0;
  const double visits_per_second =
      static_cast<double>(term_visits) / elapsed_seconds;
  const double blocks_per_second =
      static_cast<double>(options.repetitions) * options.blocks /
      elapsed_seconds;
  const double single_h100_days =
      static_cast<double>(pw::kFullBlockCount) / blocks_per_second / 86400.0;
  const double eight_h100_days = single_h100_days / 8.0;
  const double logical_runs =
      static_cast<double>(options.repetitions) * options.blocks;
  const double combined_seconds_per_block =
      elapsed_seconds / logical_runs + fft_elapsed_seconds / logical_runs +
      gamma_elapsed_seconds / logical_runs;
  const double combined_blocks_per_second = 1.0 / combined_seconds_per_block;
  const double combined_eight_device_days =
      static_cast<double>(pw::kFullBlockCount) /
      combined_blocks_per_second / 86400.0 / 8.0;

  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-windowed-core-benchmark.v1\""
            << ",\"claim_scope\":\"gamma_taylor_synthesis_and_exact_fft_work_shape_not_a_source_certificate\""
            << ",\"device\":\"" << properties.name << "\""
            << ",\"compute_capability\":\"" << properties.major << "."
            << properties.minor << "\""
            << ",\"source_geometry_initializer\":"
            << (options.source_geometry ? "true" : "false")
            << ",\"fixed_q192_phase\":"
            << (options.source_geometry ? "true" : "false")
            << ",\"gamma_taylor_synthesis\":"
            << (options.gamma_synthesis ? "true" : "false")
            << ",\"gamma_packet_scope\":\""
            << (options.gamma_synthesis
                    ? (source_packet_exported
                           ? "first_source_window_packet_analytic_realization_open"
                           : "first_source_window_kat_reused_for_work_shape")
                    : "disabled")
            << "\""
            << ",\"terms\":" << options.terms
            << ",\"buckets\":" << pw::kBucketCount
            << ",\"active_buckets\":" << host.active_buckets.size()
            << ",\"taylor_stages\":" << options.stages
            << ",\"logical_blocks\":" << options.blocks
            << ",\"phase_reanchor_blocks\":"
            << (options.source_geometry ? options.reanchor_blocks : 0U)
            << ",\"repetitions\":" << options.repetitions
            << ",\"batched_fft_passes\":" << options.fft_passes
            << ",\"power_table_bytes\":"
            << power_cells * sizeof(RealInterval)
            << ",\"elapsed_seconds\":" << elapsed_seconds
            << ",\"term_visits\":" << term_visits
            << ",\"term_visits_per_second\":" << visits_per_second
            << ",\"fixed_phase_anchor_terms_per_second\":"
            << fixed_anchor_terms_per_second
            << ",\"gamma_elapsed_seconds\":" << gamma_elapsed_seconds
            << ",\"gamma_values_per_second\":"
            << gamma_values_per_second
            << ",\"fft_elapsed_seconds\":" << fft_elapsed_seconds
            << ",\"fft_butterflies\":" << fft_butterflies
            << ",\"fft_butterflies_per_second\":"
            << fft_butterflies_per_second
            << ",\"logical_blocks_per_second\":" << blocks_per_second
            << ",\"projected_single_device_days_core_only\":"
            << single_h100_days
            << ",\"projected_eight_device_days_core_only\":"
            << eight_h100_days
            << ",\"combined_gamma_taylor_fft_blocks_per_second\":"
            << combined_blocks_per_second
            << ",\"projected_eight_device_days_gamma_taylor_fft\":"
            << combined_eight_device_days
            << ",\"gamma_probes\":[";
  if (options.gamma_synthesis) {
    constexpr std::uint32_t probe_indices[] = {0U, 8192U, 16384U, 24576U,
                                                32767U};
    for (std::size_t probe = 0;
         probe < sizeof(probe_indices) / sizeof(probe_indices[0]); ++probe) {
      if (probe != 0U) std::cout << ',';
      const std::uint32_t index = probe_indices[probe];
      const ComplexInterval value = gamma_values_host[index];
      std::cout << "{\"index\":" << std::dec << index
                << ",\"re_lo_hex\":\"" << std::hexfloat << value.re.lo
                << "\",\"re_hi_hex\":\"" << value.re.hi
                << "\",\"im_lo_hex\":\"" << value.im.lo
                << "\",\"im_hi_hex\":\"" << value.im.hi << "\"}";
    }
  }
  std::cout << std::defaultfloat
            << "]"
            << ",\"gamma_output_fnv1a64\":\"" << std::hex
            << std::setw(16) << std::setfill('0') << gamma_checksum << "\""
            << ",\"output_fnv1a64\":\"" << std::hex
            << std::setw(16) << std::setfill('0') << checksum << "\""
            << std::dec << std::defaultfloat
            << ",\"source_packet_exported\":"
            << (source_packet_exported ? "true" : "false")
            << ",\"source_packet_complete_terms\":"
            << (source_packet_exported && options.terms == pw::kSourceTerms
                    ? "true" : "false")
            << ",\"source_packet_bytes\":" << source_packet.bytes
            << ",\"source_packet_sha256\":\"" << source_packet.sha256
            << "\""
            << ",\"source_dd_packet_exported\":"
            << (source_dd_packet_exported ? "true" : "false")
            << ",\"source_dd_packet_complete_terms\":"
            << (source_dd_packet_exported &&
                        options.terms == pw::kSourceTerms
                    ? "true"
                    : "false")
            << ",\"source_dd_packet_bytes\":" << source_dd_packet.bytes
            << ",\"source_dd_packet_sha256\":\""
            << source_dd_packet.sha256 << "\""
            << ",\"source_dd_gamma_row_sha256\":\""
            << loaded_dd_gamma.sha256 << "\""
            << ",\"source_dd_accumulator_elapsed_seconds\":"
            << dd_source_elapsed_seconds
            << ",\"source_dd_term_visits_per_second\":"
            << dd_source_term_visits_per_second
            << ",\"source_dd_accumulator_algorithm\":\"bounded-fast-dd-center-l1-radius-v1\""
            << ",\"source_dd_accumulator_warps_per_bucket\":"
            << kSourceDDAccumulatorWarps
            << ",\"source_dd_accumulator_legacy_elapsed_seconds\":"
            << dd_accumulator_legacy_elapsed_seconds
            << ",\"source_dd_accumulator_compressed_elapsed_seconds\":"
            << dd_accumulator_compressed_elapsed_seconds
            << ",\"source_dd_accumulator_local_speedup\":"
            << (dd_accumulator_compressed_elapsed_seconds > 0.0
                    ? dd_accumulator_legacy_elapsed_seconds /
                          dd_accumulator_compressed_elapsed_seconds
                    : 0.0)
            << ",\"source_dd_accumulator_mpfr_kat_samples\":"
            << dd_accumulator_mpfr_kat_samples
            << ",\"source_dd_accumulator_legacy_kat_failures\":"
            << dd_accumulator_legacy_kat_failures
            << ",\"source_dd_accumulator_compressed_kat_failures\":"
            << dd_accumulator_compressed_kat_failures
            << ",\"source_dd_accumulator_physical_refinement_proved\":false"
            << ",\"source_dd_accumulator_kat_max_required_radius\":"
            << dd_accumulator_kat_max_required_radius
            << ",\"source_dd_accumulator_kat_max_legacy_radius\":"
            << dd_accumulator_kat_max_legacy_radius
            << ",\"source_dd_accumulator_kat_max_compressed_radius\":"
            << dd_accumulator_kat_max_compressed_radius
            << ",\"source_dd_accumulator_kat_max_radius_ratio\":"
            << dd_accumulator_kat_max_radius_ratio
            << ",\"source_dd_q192_reanchor_every_block\":"
            << (options.dd_source_blocks != 0U &&
                        options.reanchor_blocks == 1U
                    ? "true"
                    : "false")
            << ",\"source_dd_phase_recurrence_enabled\":"
            << (options.dd_source_blocks != 0U &&
                        options.reanchor_blocks > 1U
                    ? "true"
                    : "false")
            << ",\"source_dd_phase_reanchor_blocks\":"
            << (options.dd_source_blocks != 0U
                    ? options.reanchor_blocks
                    : 0U)
            << ",\"source_dd_stream_start_block\":"
            << options.dd_source_start_block
            << ",\"source_dd_stream_blocks\":"
            << options.dd_source_blocks
            << ",\"source_dd_stream_elapsed_seconds\":"
            << dd_source_stream_elapsed_seconds
            << ",\"source_dd_stream_blocks_per_second\":"
            << dd_source_stream_blocks_per_second
            << ",\"source_dd_stream_term_visits_per_second\":"
            << dd_source_stream_term_visits_per_second
            << ",\"source_dd_stream_final_output_fnv1a64\":\""
            << std::hex << std::setw(16) << std::setfill('0')
            << dd_source_stream_output_fnv1a64 << std::dec
            << "\""
            << ",\"source_dd_anchor_kat_contained\":"
            << (source_dd_enabled && source_dd_anchor_kat_failures == 0U
                    ? "true"
                    : "false")
            << ",\"source_dd_anchor_kat_height\":"
            << source_dd_anchor_kat_height
            << ",\"source_dd_anchor_kat_failures\":"
            << source_dd_anchor_kat_failures
            << ",\"source_dd_anchor_kat_max_required_radius\":"
            << source_dd_anchor_kat_max_required_radius
            << ",\"source_dd_anchor_kat_max_output_radius\":"
            << source_dd_anchor_kat_max_output_radius
            << ",\"source_dd_recurrence_kat_samples\":"
            << dd_source_recurrence_kat_samples
            << ",\"source_dd_recurrence_kat_failures\":"
            << dd_source_recurrence_kat_failures
            << ",\"source_dd_recurrence_kat_max_required_radius\":"
            << dd_source_recurrence_kat_max_required_radius
            << ",\"source_dd_recurrence_kat_max_output_radius\":"
            << dd_source_recurrence_kat_max_output_radius
            << ",\"source_dd_phase_physical_refinement_proved\":false"
            << ",\"zero_isolation_events_constructed\":false"
            << ",\"turing_event_stream_constructed\":false"
            << ",\"global_zero_count_constructed\":false"
            << "}\n";

  CUDA_CHECK(cudaEventDestroy(start));
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaFree(device_offsets));
  CUDA_CHECK(cudaFree(device_active));
  CUDA_CHECK(cudaFree(device_residuals));
  CUDA_CHECK(cudaFree(device_amplitudes));
  CUDA_CHECK(cudaFree(device_powers));
  CUDA_CHECK(cudaFree(device_fixed_turns));
  CUDA_CHECK(cudaFree(device_initial_values));
  CUDA_CHECK(cudaFree(device_values));
  CUDA_CHECK(cudaFree(device_phase_steps));
  CUDA_CHECK(cudaFree(device_output));
  if (options.fft_passes != 0U) {
    CUDA_CHECK(cudaFree(device_fft_roots));
    CUDA_CHECK(cudaFree(device_fft_workspace));
    CUDA_CHECK(cudaFree(device_final_fft_input));
    CUDA_CHECK(cudaFree(device_final_fft_workspace));
  }
  if (options.gamma_synthesis) CUDA_CHECK(cudaFree(device_gamma_values));
  if (source_dd_enabled) {
    CUDA_CHECK(cudaFree(device_narrow_residuals));
    CUDA_CHECK(cudaFree(device_narrow_amplitudes));
    CUDA_CHECK(cudaFree(device_narrow_powers));
    CUDA_CHECK(cudaFree(device_dd_sine_coefficients));
    CUDA_CHECK(cudaFree(device_dd_cosine_coefficients));
    CUDA_CHECK(cudaFree(device_narrow_values));
    CUDA_CHECK(cudaFree(device_narrow_phase_steps));
    CUDA_CHECK(cudaFree(device_narrow_output));
    CUDA_CHECK(cudaFree(device_narrow_output_legacy));
  }
  return 0;
}

}  // namespace

#ifndef SPARKINTERVAL_PLATT_DD_ACCUMULATOR_NO_API
namespace sparkinterval::tg::platt_dd_accumulator {

struct Workspace {
  std::uint64_t first = 0U;
  std::uint64_t count = 0U;
  std::uint64_t enqueued = 0U;
  std::uint64_t device_bytes = 0U;
  std::uint32_t reanchor = 0U;
  std::uint32_t output_slots = 1U;
  std::uint32_t active_count = 0U;
  pw::RealDisk106 two_pi{};
  std::uint32_t* offsets = nullptr;
  std::uint32_t* active = nullptr;
  pw::FixedTurn192* fixed_turns = nullptr;
  pw::RealDisk106* residuals = nullptr;
  pw::RealDisk106* amplitudes = nullptr;
  pw::RealDisk106* powers = nullptr;
  pw::RealDisk106* sine_coefficients = nullptr;
  pw::RealDisk106* cosine_coefficients = nullptr;
  pw::ComplexDisk106* values = nullptr;
  pw::ComplexDisk106* phase_steps = nullptr;
  pw::ComplexDisk106* output = nullptr;
#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
  double* value_l1 = nullptr;
  double* power_abs = nullptr;
#endif
};

namespace {

void release_pointer(void* pointer, cudaError_t& first_error) {
  if (pointer == nullptr) return;
  const cudaError_t status = cudaFree(pointer);
  if (first_error == cudaSuccess && status != cudaSuccess) {
    first_error = status;
  }
}

void release_workspace(Workspace* workspace, bool report_error) {
  if (workspace == nullptr) return;
  cudaError_t first_error = cudaSuccess;
  release_pointer(workspace->offsets, first_error);
  release_pointer(workspace->active, first_error);
  release_pointer(workspace->fixed_turns, first_error);
  release_pointer(workspace->residuals, first_error);
  release_pointer(workspace->amplitudes, first_error);
  release_pointer(workspace->powers, first_error);
  release_pointer(workspace->sine_coefficients, first_error);
  release_pointer(workspace->cosine_coefficients, first_error);
  release_pointer(workspace->values, first_error);
  release_pointer(workspace->phase_steps, first_error);
  release_pointer(workspace->output, first_error);
#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
  release_pointer(workspace->value_l1, first_error);
  release_pointer(workspace->power_abs, first_error);
#endif
  delete workspace;
  if (report_error && first_error != cudaSuccess) {
    throw std::runtime_error(std::string("CUDA workspace release failed: ") +
                             cudaGetErrorString(first_error));
  }
}

template <typename Type>
void allocate(Type** output, std::uint64_t count, std::uint64_t& total_bytes) {
  if (count == 0U ||
      count > std::numeric_limits<std::size_t>::max() / sizeof(Type)) {
    throw std::runtime_error("DD accumulator allocation size is invalid");
  }
  const std::size_t bytes =
      static_cast<std::size_t>(count) * sizeof(Type);
  CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(output), bytes));
  total_bytes += bytes;
}

}  // namespace

namespace {

Workspace* create_source_workspace_impl(std::uint64_t first,
                                        std::uint64_t count,
                                        std::uint32_t reanchor_blocks,
                                        std::uint32_t output_slots,
                                        bool qualification_slots) {
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
  if (properties.major != 9 || properties.minor != 0 ||
      std::strstr(properties.name, "H100") == nullptr) {
    throw std::runtime_error(
        "strict production target requires an NVIDIA H100 sm_90 device");
  }
#endif
  if (count == 0U || first >= pw::kFullBlockCount ||
      count > pw::kFullBlockCount - first) {
    throw std::runtime_error(
        "DD accumulator shard is outside the exact PT21 campaign");
  }
  if (reanchor_blocks == 0U || reanchor_blocks > (1U << 24U)) {
    throw std::runtime_error(
        "DD accumulator re-anchor interval is outside 1..16777216");
  }
  if ((!qualification_slots && output_slots != 1U) ||
      (qualification_slots && (output_slots < 2U || output_slots > 4U))) {
    throw std::runtime_error(
        "DD accumulator output-slot count is outside its API contract");
  }

  Options options;
  options.terms = pw::kSourceTerms;
  options.stages = pw::kTaylorTerms;
  options.source_geometry = true;
  options.fft_passes = 0U;
  const HostTerms host = initialize_terms(options);
  const SourceDDTrigData trig = initialize_source_dd_trig_data();

  auto* workspace = new Workspace{};
  workspace->first = first;
  workspace->count = count;
  workspace->reanchor = reanchor_blocks;
  workspace->output_slots = output_slots;
  workspace->active_count =
      static_cast<std::uint32_t>(host.active_buckets.size());
  workspace->two_pi = trig.two_pi;
  try {
    const std::uint64_t power_cells =
        static_cast<std::uint64_t>(pw::kSourceTerms) * pw::kTaylorTerms;
    const std::uint64_t output_cells =
        static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
    allocate(&workspace->offsets, host.offsets.size(),
             workspace->device_bytes);
    allocate(&workspace->active, host.active_buckets.size(),
             workspace->device_bytes);
    allocate(&workspace->fixed_turns, host.fixed_turns.size(),
             workspace->device_bytes);
    allocate(&workspace->residuals, host.narrow_residuals.size(),
             workspace->device_bytes);
    allocate(&workspace->amplitudes, host.narrow_amplitudes.size(),
             workspace->device_bytes);
    allocate(&workspace->powers, power_cells, workspace->device_bytes);
    allocate(&workspace->sine_coefficients, trig.sine_coefficients.size(),
             workspace->device_bytes);
    allocate(&workspace->cosine_coefficients, trig.cosine_coefficients.size(),
             workspace->device_bytes);
    allocate(&workspace->values, host.narrow_values.size(),
             workspace->device_bytes);
    allocate(&workspace->phase_steps, host.narrow_values.size(),
             workspace->device_bytes);
    allocate(&workspace->output, output_cells * output_slots,
             workspace->device_bytes);
#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
    allocate(&workspace->value_l1, pw::kSourceTerms,
             workspace->device_bytes);
    allocate(&workspace->power_abs, power_cells,
             workspace->device_bytes);
#endif

    // Only active buckets are written by source_dd_accumulate_all_stages, but
    // the downstream transform reads every bucket in every Taylor row.  Make
    // the mathematically required zero value for every inactive cell explicit
    // for all output slots.  The checked default-stream memset is covered by
    // the initialization cudaDeviceSynchronize below before publication.
    CUDA_CHECK(cudaMemset(workspace->output, 0,
                          output_cells * output_slots *
                              sizeof(*workspace->output)));

    CUDA_CHECK(cudaMemcpy(workspace->offsets, host.offsets.data(),
                          host.offsets.size() * sizeof(std::uint32_t),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->active, host.active_buckets.data(),
                          host.active_buckets.size() * sizeof(std::uint32_t),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->fixed_turns, host.fixed_turns.data(),
                          host.fixed_turns.size() * sizeof(pw::FixedTurn192),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->residuals,
                          host.narrow_residuals.data(),
                          host.narrow_residuals.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->amplitudes,
                          host.narrow_amplitudes.data(),
                          host.narrow_amplitudes.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->sine_coefficients,
                          trig.sine_coefficients.data(),
                          trig.sine_coefficients.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->cosine_coefficients,
                          trig.cosine_coefficients.data(),
                          trig.cosine_coefficients.size() *
                              sizeof(pw::RealDisk106),
                          cudaMemcpyHostToDevice));

    constexpr std::uint32_t threads = 256U;
    const std::uint32_t term_blocks = std::min<std::uint32_t>(
        (pw::kSourceTerms + threads - 1U) / threads, 4096U);
    source_dd_build_power_table<<<term_blocks, threads>>>(
        workspace->residuals, workspace->powers, pw::kSourceTerms,
        pw::kTaylorTerms);
#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
    source_dd_precompute_power_abs_qualification<<<4096U, threads>>>(
        workspace->powers, workspace->power_abs, power_cells);
#endif
    source_dd_construct_phase_steps<<<term_blocks, threads>>>(
        workspace->fixed_turns, workspace->two_pi,
        workspace->sine_coefficients, workspace->cosine_coefficients,
        workspace->phase_steps, pw::kSourceTerms);
    const std::uint64_t height =
        pw::kSourceLower + pw::kWindowStep / 2U + first * pw::kWindowStep;
    source_dd_anchor_fixed_phases<<<term_blocks, threads>>>(
        workspace->fixed_turns, workspace->amplitudes, height,
        workspace->two_pi, workspace->sine_coefficients,
        workspace->cosine_coefficients, workspace->values,
        pw::kSourceTerms);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
  } catch (...) {
    release_workspace(workspace, false);
    throw;
  }
  return workspace;
}

SourceWindowView run_next_source_window_impl(Workspace* workspace,
                                             cudaStream_t stream,
                                             std::uint32_t output_slot) {
  if (workspace == nullptr) {
    throw std::runtime_error("DD accumulator workspace is null");
  }
  if (output_slot >= workspace->output_slots) {
    throw std::runtime_error("DD accumulator output slot is outside range");
  }
  if (workspace->enqueued >= workspace->count) {
    throw std::runtime_error("DD accumulator shard is exhausted");
  }
  constexpr std::uint64_t output_cells =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  pw::ComplexDisk106* const output =
      workspace->output + output_slot * output_cells;
  constexpr std::uint32_t threads = 256U;
  const std::uint32_t term_blocks = std::min<std::uint32_t>(
      (pw::kSourceTerms + threads - 1U) / threads, 4096U);
  const std::uint64_t relative = workspace->enqueued;
  const std::uint64_t logical_block = workspace->first + relative;
  const std::uint64_t height = pw::kSourceLower + pw::kWindowStep / 2U +
                               logical_block * pw::kWindowStep;
  if (relative != 0U) {
    if (relative % workspace->reanchor == 0U) {
      source_dd_anchor_fixed_phases<<<term_blocks, threads, 0U, stream>>>(
          workspace->fixed_turns, workspace->amplitudes, height,
          workspace->two_pi, workspace->sine_coefficients,
          workspace->cosine_coefficients, workspace->values,
          pw::kSourceTerms);
    } else {
      source_dd_advance_phase<<<term_blocks, threads, 0U, stream>>>(
          workspace->values, workspace->phase_steps, pw::kSourceTerms);
    }
  }
  source_dd_accumulate_all_stages<<<
      workspace->active_count, kSourceDDAccumulatorWarps * 32U, 0U,
      stream>>>(workspace->offsets, workspace->active, workspace->values,
                workspace->powers, pw::kSourceTerms,
                workspace->active_count, pw::kTaylorTerms, output);
  CUDA_CHECK(cudaGetLastError());
  ++workspace->enqueued;
  return {output, logical_block, height, pw::kTaylorTerms,
          pw::kBucketCount};
}

#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
template <typename Kernel>
QualificationKernelResources read_qualification_kernel_resources(
    Kernel kernel, std::uint32_t threads) {
  cudaFuncAttributes attributes{};
  CUDA_CHECK(cudaFuncGetAttributes(&attributes, kernel));
  int active_blocks = 0;
  CUDA_CHECK(cudaOccupancyMaxActiveBlocksPerMultiprocessor(
      &active_blocks, kernel, static_cast<int>(threads), 0U));
  return {
      attributes.numRegs,
      static_cast<std::uint64_t>(attributes.sharedSizeBytes),
      static_cast<std::uint64_t>(attributes.localSizeBytes),
      attributes.maxThreadsPerBlock,
      active_blocks,
      threads,
  };
}
#endif

}  // namespace

Workspace* create_source_workspace(std::uint64_t first,
                                   std::uint64_t count,
                                   std::uint32_t reanchor_blocks) {
  return create_source_workspace_impl(first, count, reanchor_blocks, 1U,
                                      false);
}

Workspace* create_source_workspace_with_output_slots_qualification(
    std::uint64_t first, std::uint64_t count,
    std::uint32_t reanchor_blocks, std::uint32_t output_slots) {
  return create_source_workspace_impl(first, count, reanchor_blocks,
                                      output_slots, true);
}

void destroy_workspace(Workspace* workspace) {
  release_workspace(workspace, true);
}

SourceWindowView run_next_source_window(Workspace* workspace,
                                        cudaStream_t stream) {
  return run_next_source_window_impl(workspace, stream, 0U);
}

SourceWindowView run_next_source_window_to_slot_qualification(
    Workspace* workspace, cudaStream_t stream,
    std::uint32_t output_slot) {
  if (workspace == nullptr || workspace->output_slots < 2U) {
    throw std::runtime_error(
        "slot-indexed enqueue requires a qualification workspace");
  }
  return run_next_source_window_impl(workspace, stream, output_slot);
}

std::uint64_t first_block(const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->first;
}

std::uint64_t block_count(const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->count;
}

std::uint64_t windows_enqueued(const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->enqueued;
}

std::uint64_t workspace_device_bytes(const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->device_bytes;
}

std::uint32_t output_slot_count(const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->output_slots;
}

const std::uint32_t* device_bucket_offsets_qualification(
    const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->offsets;
}

const std::uint32_t* device_active_buckets_qualification(
    const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->active;
}

std::uint32_t active_bucket_count_qualification(
    const Workspace* workspace) {
  if (workspace == nullptr) throw std::runtime_error("workspace is null");
  return workspace->active_count;
}

#ifdef SPARKINTERVAL_ENABLE_PT21_ACCUMULATOR_QUALIFICATION
SourceWindowView rerun_last_source_window_qualification(
    Workspace* workspace, cudaStream_t stream, std::uint32_t output_slot,
    QualificationSchedule schedule) {
  if (workspace == nullptr) {
    throw std::runtime_error("DD accumulator workspace is null");
  }
  if (workspace->output_slots < 2U ||
      output_slot >= workspace->output_slots) {
    throw std::runtime_error(
        "accumulator rerun requires a qualification output slot");
  }
  if (workspace->enqueued == 0U) {
    throw std::runtime_error(
        "accumulator rerun requires an already enqueued window");
  }
  constexpr std::uint64_t output_cells =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  pw::ComplexDisk106* const output =
      workspace->output + output_slot * output_cells;
  switch (schedule) {
    case QualificationSchedule::kBaseline8:
      source_dd_accumulate_all_stages<<<
          workspace->active_count, kSourceDDAccumulatorWarps * 32U, 0U,
          stream>>>(workspace->offsets, workspace->active, workspace->values,
                    workspace->powers, pw::kSourceTerms,
                    workspace->active_count, pw::kTaylorTerms, output);
      break;
    case QualificationSchedule::kWarp12:
      source_dd_accumulate_all_stages_warp_qualification<12U>
          <<<workspace->active_count, 12U * 32U, 0U, stream>>>(
              workspace->offsets, workspace->active, workspace->values,
              workspace->powers, pw::kSourceTerms,
              workspace->active_count, pw::kTaylorTerms, output);
      break;
    case QualificationSchedule::kShared8:
      source_dd_accumulate_all_stages_shared_qualification<8U>
          <<<workspace->active_count, 8U * 32U, 0U, stream>>>(
              workspace->offsets, workspace->active, workspace->values,
              workspace->powers, pw::kSourceTerms,
              workspace->active_count, pw::kTaylorTerms, output);
      break;
    case QualificationSchedule::kShared12:
      source_dd_accumulate_all_stages_shared_qualification<12U>
          <<<workspace->active_count, 12U * 32U, 0U, stream>>>(
              workspace->offsets, workspace->active, workspace->values,
              workspace->powers, pw::kSourceTerms,
              workspace->active_count, pw::kTaylorTerms, output);
      break;
    case QualificationSchedule::kWarp16:
      source_dd_accumulate_all_stages_warp_qualification<16U>
          <<<workspace->active_count, 16U * 32U, 0U, stream>>>(
              workspace->offsets, workspace->active, workspace->values,
              workspace->powers, pw::kSourceTerms,
              workspace->active_count, pw::kTaylorTerms, output);
      break;
    case QualificationSchedule::kWarp24:
      source_dd_accumulate_all_stages_warp_qualification<24U>
          <<<workspace->active_count, 24U * 32U, 0U, stream>>>(
              workspace->offsets, workspace->active, workspace->values,
              workspace->powers, pw::kSourceTerms,
              workspace->active_count, pw::kTaylorTerms, output);
      break;
    case QualificationSchedule::kPrecomputedL1Warp8: {
      constexpr std::uint32_t threads = 256U;
      const std::uint32_t blocks = std::min<std::uint32_t>(
          (pw::kSourceTerms + threads - 1U) / threads, 4096U);
      source_dd_precompute_value_l1_qualification<<<
          blocks, threads, 0U, stream>>>(
          workspace->values, workspace->value_l1, pw::kSourceTerms);
      source_dd_accumulate_all_stages_precomputed_l1_qualification<<<
          workspace->active_count, kSourceDDAccumulatorWarps * 32U, 0U,
          stream>>>(workspace->offsets, workspace->active, workspace->values,
                    workspace->powers, workspace->value_l1,
                    pw::kSourceTerms, workspace->active_count,
                    pw::kTaylorTerms, output);
      break;
    }
    case QualificationSchedule::kPrecomputedL1PowerAbsWarp8: {
      constexpr std::uint32_t threads = 256U;
      const std::uint32_t blocks = std::min<std::uint32_t>(
          (pw::kSourceTerms + threads - 1U) / threads, 4096U);
      source_dd_precompute_value_l1_qualification<<<
          blocks, threads, 0U, stream>>>(
          workspace->values, workspace->value_l1, pw::kSourceTerms);
      source_dd_accumulate_all_stages_precomputed_l1_power_abs_qualification
          <<<workspace->active_count,
             kSourceDDAccumulatorWarps * 32U, 0U, stream>>>(
              workspace->offsets, workspace->active, workspace->values,
              workspace->powers, workspace->value_l1,
              workspace->power_abs, pw::kSourceTerms,
              workspace->active_count, pw::kTaylorTerms, output);
      break;
    }
    default:
      throw std::runtime_error(
          "unknown accumulator qualification schedule");
  }
  CUDA_CHECK(cudaGetLastError());
  const std::uint64_t logical_block =
      workspace->first + workspace->enqueued - 1U;
  const std::uint64_t height =
      pw::kSourceLower + pw::kWindowStep / 2U +
      logical_block * pw::kWindowStep;
  return {output, logical_block, height, pw::kTaylorTerms,
          pw::kBucketCount};
}

QualificationKernelResources qualification_kernel_resources(
    QualificationSchedule schedule) {
  switch (schedule) {
    case QualificationSchedule::kBaseline8:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages,
          kSourceDDAccumulatorWarps * 32U);
    case QualificationSchedule::kWarp12:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_warp_qualification<12U>,
          12U * 32U);
    case QualificationSchedule::kShared8:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_shared_qualification<8U>,
          8U * 32U);
    case QualificationSchedule::kShared12:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_shared_qualification<12U>,
          12U * 32U);
    case QualificationSchedule::kWarp16:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_warp_qualification<16U>,
          16U * 32U);
    case QualificationSchedule::kWarp24:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_warp_qualification<24U>,
          24U * 32U);
    case QualificationSchedule::kPrecomputedL1Warp8:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_precomputed_l1_qualification,
          kSourceDDAccumulatorWarps * 32U);
    case QualificationSchedule::kPrecomputedL1PowerAbsWarp8:
      return read_qualification_kernel_resources(
          source_dd_accumulate_all_stages_precomputed_l1_power_abs_qualification,
          kSourceDDAccumulatorWarps * 32U);
    default:
      throw std::runtime_error(
          "unknown accumulator qualification schedule");
  }
}
#endif

}  // namespace sparkinterval::tg::platt_dd_accumulator
#endif

#ifndef SPARKINTERVAL_PLATT_WINDOWED_CORE_NO_MAIN
int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-windowed-core: " << error.what()
              << '\n';
    return 2;
  }
}
#endif

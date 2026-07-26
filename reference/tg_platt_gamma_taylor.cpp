// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Compact source-semantic Gamma data for the Platt--Trudgian windowed zeta
// computation.  Instead of sending N1=32768 independent Gamma values to the
// GPU for every window, this program encloses the Taylor coefficients of
//
//   L_T(u) = log Gamma(1/4 + i (T+u)/2) + pi (T+u)/4
//
// at u=0.  It also computes a uniform integral-remainder bound over the exact
// source window |u| <= 2688.  The Gaussian -u^2/(2h^2) is an exact quadratic
// added by the GPU and is intentionally not folded into these coefficients.
//
// The coefficient and remainder endpoints are emitted as canonical FLINT
// arf_dump_str dyadics.  An optional audit evaluates the polynomial enclosure
// at a deterministic sample grid and checks inclusion of fresh acb_lgamma
// evaluations.  FLINT/Arb remains an explicit external analytic realization;
// the enclosing Taylor reduction itself is finite and independently replayable.

#include <flint/acb.h>
#include <flint/acb_poly.h>
#include <flint/arb.h>
#include <flint/arf.h>
#include <flint/flint.h>
#include <flint/fmpz.h>
#include <flint/mag.h>

#include <gmp.h>

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_windowed.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#ifndef SPARKINTERVAL_FLINT_PLATT_COMMIT
#error "the Gamma Taylor producer must bind the reviewed FLINT commit"
#endif

namespace {

namespace pw = sparkinterval::tg::platt_windowed;

constexpr std::uint64_t kSourceLower = 10'000'000'000ULL;
constexpr std::uint64_t kSourceUpper = 3'000'175'332'800ULL;
constexpr std::uint64_t kWindowStep = 1008ULL;
constexpr std::int64_t kRadiusNumerator = 2688;
constexpr std::int64_t kRadiusDenominator = 1;
constexpr long kDefaultPrecision = 256;
constexpr long kDefaultDegree = 6;
constexpr char kReviewedPlattSourceSha256[] =
    "9a748490b327b102d53506e390a42afac796a5b42b42060fe82aa8f5744bb152";
constexpr char kGammaTaylorContractId[] =
    "sparkinterval/pt21-gamma-taylor-stream/v1";
constexpr char kGammaTaylorStreamHashDomain[] =
    "sparkinterval/pt21-gamma-taylor-stream/v1";

struct Options {
  std::uint64_t height = kSourceLower + kWindowStep / 2ULL;
  long precision = kDefaultPrecision;
  long degree = kDefaultDegree;
  std::uint64_t repeat = 1;
  std::uint64_t audit_samples = 9;
  std::string export_dd_gamma_row;
  std::uint64_t stream_first_block = 0;
  std::uint64_t stream_blocks = 0;
  std::uint32_t stream_chunk_records = 4096U;
  std::uint64_t stream_audit_stride = 1ULL << 20U;
  std::string stream_output;
  bool stream_hash_only = false;
};

[[noreturn]] void fail(const std::string& message) {
  std::cerr << message << '\n';
  std::exit(2);
}

template <typename Integer>
bool parse_integer(std::string_view text, Integer* output) {
  if (text.empty()) return false;
  const char* first = text.data();
  const char* last = first + text.size();
  const auto result = std::from_chars(first, last, *output);
  return result.ec == std::errc{} && result.ptr == last;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--height") {
      if (!parse_integer(value("--height"), &options.height)) {
        fail("--height must be an unsigned integer");
      }
    } else if (argument == "--precision") {
      if (!parse_integer(value("--precision"), &options.precision)) {
        fail("--precision must be an integer");
      }
    } else if (argument == "--degree") {
      if (!parse_integer(value("--degree"), &options.degree)) {
        fail("--degree must be an integer");
      }
    } else if (argument == "--repeat") {
      if (!parse_integer(value("--repeat"), &options.repeat)) {
        fail("--repeat must be an unsigned integer");
      }
    } else if (argument == "--audit-samples") {
      if (!parse_integer(value("--audit-samples"),
                         &options.audit_samples)) {
        fail("--audit-samples must be an unsigned integer");
      }
    } else if (argument == "--export-dd-gamma-row") {
      options.export_dd_gamma_row =
          std::string(value("--export-dd-gamma-row"));
      if (options.export_dd_gamma_row.empty()) {
        fail("--export-dd-gamma-row path is empty");
      }
    } else if (argument == "--stream-first-block") {
      if (!parse_integer(value("--stream-first-block"),
                         &options.stream_first_block)) {
        fail("--stream-first-block must be an unsigned integer");
      }
    } else if (argument == "--stream-blocks") {
      if (!parse_integer(value("--stream-blocks"), &options.stream_blocks)) {
        fail("--stream-blocks must be an unsigned integer");
      }
    } else if (argument == "--stream-chunk-records") {
      if (!parse_integer(value("--stream-chunk-records"),
                         &options.stream_chunk_records)) {
        fail("--stream-chunk-records must be an unsigned integer");
      }
    } else if (argument == "--stream-audit-stride") {
      if (!parse_integer(value("--stream-audit-stride"),
                         &options.stream_audit_stride)) {
        fail("--stream-audit-stride must be an unsigned integer");
      }
    } else if (argument == "--stream-output") {
      options.stream_output = std::string(value("--stream-output"));
      if (options.stream_output.empty()) {
        fail("--stream-output path is empty");
      }
    } else if (argument == "--stream-hash-only") {
      options.stream_hash_only = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-platt-gamma-taylor "
             "[--height T] [--precision BITS] [--degree D] "
             "[--repeat N] [--audit-samples N] "
             "[--export-dd-gamma-row PATH]\n"
             "  all-window stream mode:\n"
             "    --stream-blocks N [--stream-first-block N] "
             "[--stream-chunk-records N]\n"
             "    [--stream-audit-stride N] "
             "(--stream-output PATH | --stream-hash-only)\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.height < kSourceLower || options.height > kSourceUpper) {
    fail("height is outside the source interval");
  }
  if (options.precision < 96 || options.precision > 4096) {
    fail("precision is outside 96..4096 bits");
  }
  if (options.degree < 3 || options.degree > 16) {
    fail("degree is outside 3..16");
  }
  if (options.repeat == 0 || options.repeat > 10'000'000ULL) {
    fail("repeat is outside 1..10000000");
  }
  if (options.audit_samples > 4097) {
    fail("audit sample count exceeds 4097");
  }
  const bool stream_requested = options.stream_blocks != 0U ||
                                options.stream_first_block != 0U ||
                                !options.stream_output.empty() ||
                                options.stream_hash_only;
  if (stream_requested) {
    if (options.stream_blocks == 0U) {
      fail("stream mode requires a positive --stream-blocks");
    }
    if (options.stream_first_block >= pw::kFullBlockCount ||
        options.stream_blocks >
            pw::kFullBlockCount - options.stream_first_block) {
      fail("stream block range exceeds the exact source campaign");
    }
    if (options.stream_chunk_records == 0U ||
        options.stream_chunk_records > (1U << 20U)) {
      fail("stream chunk size is outside 1..1048576 records");
    }
    if (options.stream_hash_only == !options.stream_output.empty()) {
      fail("choose exactly one of --stream-output and --stream-hash-only");
    }
    if (options.precision != pw::kGammaTaylorPrecision ||
        options.degree != pw::kGammaTaylorDegree || options.repeat != 1U) {
      fail("stream v1 fixes precision=256, degree=6, and repeat=1");
    }
    if (!options.export_dd_gamma_row.empty()) {
      fail("stream mode cannot export a per-window Gamma row");
    }
  }
  return options;
}

void require_flint_identity() {
  if (std::strcmp(FLINT_VERSION, "3.6.0") != 0 ||
      std::strcmp(flint_version, "3.6.0") != 0 ||
      __FLINT_RELEASE != 30600) {
    fail("compile-time or runtime FLINT is not 3.6.0");
  }
}

struct AcbPolynomial {
  acb_poly_t value;
  AcbPolynomial() { acb_poly_init(value); }
  ~AcbPolynomial() { acb_poly_clear(value); }
  AcbPolynomial(const AcbPolynomial&) = delete;
  AcbPolynomial& operator=(const AcbPolynomial&) = delete;
};

struct AcbValue {
  acb_t value;
  AcbValue() { acb_init(value); }
  ~AcbValue() { acb_clear(value); }
  AcbValue(const AcbValue&) = delete;
  AcbValue& operator=(const AcbValue&) = delete;
};

struct ArbValue {
  arb_t value;
  ArbValue() { arb_init(value); }
  ~ArbValue() { arb_clear(value); }
  ArbValue(const ArbValue&) = delete;
  ArbValue& operator=(const ArbValue&) = delete;
};

struct ArfValue {
  arf_t value;
  ArfValue() { arf_init(value); }
  ~ArfValue() { arf_clear(value); }
  ArfValue(const ArfValue&) = delete;
  ArfValue& operator=(const ArfValue&) = delete;
};

std::string dump_arf(const arf_t value) {
  char* raw = arf_dump_str(value);
  if (raw == nullptr) fail("arf_dump_str returned null");
  const std::string result(raw);
  flint_free(raw);
  return result;
}

struct DyadicInterval {
  std::string lower;
  std::string upper;
};

DyadicInterval dump_interval(const arb_t value, long precision);

struct Binary64Interval {
  double lower;
  double upper;
};

Binary64Interval project_binary64(const arb_t value, long precision) {
  ArfValue lower;
  ArfValue upper;
  arb_get_interval_arf(lower.value, upper.value, value, precision);
  return {arf_get_d(lower.value, ARF_RND_FLOOR),
          arf_get_d(upper.value, ARF_RND_CEIL)};
}

std::string hex_double(double value) {
  std::ostringstream output;
  output << std::hexfloat << value;
  return output.str();
}

std::string json_binary64_interval(const Binary64Interval& interval) {
  return "{\"lo_hex\":\"" + hex_double(interval.lower) +
         "\",\"hi_hex\":\"" + hex_double(interval.upper) + "\"}";
}

std::string hex_u64(std::uint64_t value) {
  constexpr char digits[] = "0123456789abcdef";
  std::string result(16, '0');
  for (int index = 15; index >= 0; --index) {
    result[static_cast<std::size_t>(index)] = digits[value & 0xfU];
    value >>= 4U;
  }
  return result;
}

struct FixedTurnProjection {
  std::array<std::uint64_t, 3> limbs{};
  DyadicInterval angular_error;
  double angular_error_upper = 0.0;
};

FixedTurnProjection project_fixed_turn(const arb_t angle, long precision) {
  ArbValue pi;
  ArbValue turns;
  ArbValue scaled;
  ArbValue shifted;
  ArbValue rounded_ball;
  arb_const_pi(pi.value, precision);
  arb_mul_2exp_si(turns.value, pi.value, 1);
  arb_div(turns.value, angle, turns.value, precision);
  arb_mul_2exp_si(scaled.value, turns.value, 192);
  ArbValue half;
  ArbValue scaled_midpoint;
  arb_set_ui(half.value, 1);
  arb_mul_2exp_si(half.value, half.value, -1);
  // Select the nearest Q192 value to the deterministic Arb midpoint.  It is
  // incorrect to require the *whole* enclosing interval to have one nearest
  // integer: over billions of windows a sound interval will occasionally
  // straddle a half-integer even when it is extremely narrow.  The complete
  // input interval is retained below when bounding angular_error, so this
  // midpoint choice loses no uncertainty.
  arb_get_mid_arb(scaled_midpoint.value, scaled.value);
  arb_add(shifted.value, scaled_midpoint.value, half.value, precision);
  arb_floor(rounded_ball.value, shifted.value, precision);

  fmpz_t rounded;
  fmpz_t residue;
  fmpz_init(rounded);
  fmpz_init(residue);
  if (!arb_get_unique_fmpz(rounded, rounded_ball.value)) {
    fmpz_clear(residue);
    fmpz_clear(rounded);
    fail("phase midpoint does not determine a Q192 projection");
  }
  fmpz_fdiv_r_2exp(residue, rounded, 192);
  mpz_t residue_mpz;
  mpz_init(residue_mpz);
  fmpz_get_mpz(residue_mpz, residue);
  FixedTurnProjection result;
  std::size_t exported = 0;
  mpz_export(result.limbs.data(), &exported, -1, sizeof(std::uint64_t), 0, 0,
             residue_mpz);
  mpz_clear(residue_mpz);
  if (exported > result.limbs.size()) {
    fmpz_clear(residue);
    fmpz_clear(rounded);
    fail("Q192 residue export overflow");
  }

  ArbValue rounded_turn;
  ArbValue turn_error;
  ArbValue angular_error;
  arb_set_fmpz(rounded_turn.value, rounded);
  arb_mul_2exp_si(rounded_turn.value, rounded_turn.value, -192);
  arb_sub(turn_error.value, turns.value, rounded_turn.value, precision);
  arb_abs(turn_error.value, turn_error.value);
  arb_mul_2exp_si(pi.value, pi.value, 1);
  arb_mul(angular_error.value, turn_error.value, pi.value, precision);
  result.angular_error = dump_interval(angular_error.value, precision);
  ArfValue upper;
  arb_get_ubound_arf(upper.value, angular_error.value, precision);
  result.angular_error_upper = arf_get_d(upper.value, ARF_RND_UP);
  fmpz_clear(residue);
  fmpz_clear(rounded);
  return result;
}

DyadicInterval dump_interval(const arb_t value, long precision) {
  ArfValue lower;
  ArfValue upper;
  arb_get_interval_arf(lower.value, upper.value, value, precision);
  return {dump_arf(lower.value), dump_arf(upper.value)};
}

void set_exact_height_half(arb_t output, std::uint64_t height) {
  arb_set_ui(output, height);
  arb_mul_2exp_si(output, output, -1);
}

void initialize_argument(acb_poly_t argument, std::uint64_t height,
                         bool uncertain_center, long precision) {
  AcbValue constant;
  AcbValue linear;
  arb_set_ui(acb_realref(constant.value), 1);
  arb_mul_2exp_si(acb_realref(constant.value), acb_realref(constant.value),
                  -2);
  set_exact_height_half(acb_imagref(constant.value), height);
  if (uncertain_center) {
    // The imaginary part is (T+u)/2 and |u| <= 2688 exactly.
    ArbValue radius;
    arb_set_si(radius.value, kRadiusNumerator);
    arb_div_si(radius.value, radius.value, kRadiusDenominator, precision);
    arb_mul_2exp_si(radius.value, radius.value, -1);
    arb_add_error(acb_imagref(constant.value), radius.value);
  }
  arb_set_ui(acb_imagref(linear.value), 1);
  arb_mul_2exp_si(acb_imagref(linear.value), acb_imagref(linear.value), -1);
  acb_poly_set_coeff_acb(argument, 0, constant.value);
  acb_poly_set_coeff_acb(argument, 1, linear.value);
}

void add_source_exponential_scale(acb_poly_t logarithm,
                                  std::uint64_t height, long precision) {
  ArbValue pi;
  ArbValue scaled;
  arb_const_pi(pi.value, precision);

  arb_mul_ui(scaled.value, pi.value, height, precision);
  arb_mul_2exp_si(scaled.value, scaled.value, -2);
  arb_add(acb_realref(acb_poly_get_coeff_ptr(logarithm, 0)),
          acb_realref(acb_poly_get_coeff_ptr(logarithm, 0)), scaled.value,
          precision);

  arb_mul_2exp_si(scaled.value, pi.value, -2);
  arb_add(acb_realref(acb_poly_get_coeff_ptr(logarithm, 1)),
          acb_realref(acb_poly_get_coeff_ptr(logarithm, 1)), scaled.value,
          precision);
}

struct TaylorCertificate {
  AcbPolynomial coefficients;
  ArbValue remainder;
};

void compute_certificate(TaylorCertificate* certificate,
                         const Options& options) {
  AcbPolynomial argument;
  initialize_argument(argument.value, options.height, false,
                      options.precision);
  acb_poly_lgamma_series(certificate->coefficients.value, argument.value,
                         options.degree, options.precision);
  add_source_exponential_scale(certificate->coefficients.value,
                               options.height, options.precision);

  // A coefficient of the series at an uncertain centre encloses
  // L_T^(degree)(v)/degree! for every |v| <= radius.  The complex integral
  // Taylor remainder is therefore bounded by sup |coefficient|*radius^degree.
  AcbPolynomial uncertain_argument;
  AcbPolynomial uncertain_series;
  initialize_argument(uncertain_argument.value, options.height, true,
                      options.precision);
  acb_poly_lgamma_series(uncertain_series.value, uncertain_argument.value,
                         options.degree + 1, options.precision);
  AcbValue derivative_coefficient;
  acb_poly_get_coeff_acb(derivative_coefficient.value,
                         uncertain_series.value, options.degree);
  arb_abs(certificate->remainder.value,
          acb_realref(derivative_coefficient.value));
  ArbValue imaginary_abs;
  arb_abs(imaginary_abs.value,
          acb_imagref(derivative_coefficient.value));
  arb_hypot(certificate->remainder.value, certificate->remainder.value,
            imaginary_abs.value, options.precision);
  ArbValue radius;
  ArbValue radius_power;
  arb_set_si(radius.value, kRadiusNumerator);
  arb_div_si(radius.value, radius.value, kRadiusDenominator,
             options.precision);
  arb_pow_ui(radius_power.value, radius.value,
             static_cast<ulong>(options.degree), options.precision);
  arb_mul(certificate->remainder.value, certificate->remainder.value,
          radius_power.value, options.precision);
}

void evaluate_polynomial(acb_t output, const acb_poly_t coefficients,
                         const arb_t u, long degree, long precision) {
  acb_zero(output);
  for (long index = degree - 1; index >= 0; --index) {
    acb_mul_arb(output, output, u, precision);
    acb_add(output, output, acb_poly_get_coeff_ptr(coefficients, index),
            precision);
  }
}

bool audit_certificate(const TaylorCertificate& certificate,
                       const Options& options) {
  if (options.audit_samples == 0) return true;
  const std::uint64_t denominator =
      std::max<std::uint64_t>(1, options.audit_samples - 1);
  for (std::uint64_t sample = 0; sample < options.audit_samples; ++sample) {
    ArbValue u;
    // Deterministic exact grid from -R to R, including both endpoints when
    // more than one sample is requested.
    const std::int64_t numerator =
        options.audit_samples == 1
            ? 0
            : -kRadiusNumerator * static_cast<std::int64_t>(denominator) +
                  2 * kRadiusNumerator * static_cast<std::int64_t>(sample);
    arb_set_si(u.value, numerator);
    arb_div_ui(u.value, u.value, denominator, options.precision);

    AcbValue polynomial;
    evaluate_polynomial(polynomial.value, certificate.coefficients.value,
                        u.value, options.degree, options.precision);
    acb_add_error_arb(polynomial.value, certificate.remainder.value);

    AcbValue argument;
    arb_set_ui(acb_realref(argument.value), 1);
    arb_mul_2exp_si(acb_realref(argument.value),
                    acb_realref(argument.value), -2);
    set_exact_height_half(acb_imagref(argument.value), options.height);
    ArbValue half_u;
    arb_mul_2exp_si(half_u.value, u.value, -1);
    arb_add(acb_imagref(argument.value), acb_imagref(argument.value),
            half_u.value, options.precision);

    AcbValue direct;
    acb_lgamma(direct.value, argument.value, options.precision);
    ArbValue pi;
    ArbValue absolute_height;
    arb_const_pi(pi.value, options.precision);
    arb_set_ui(absolute_height.value, options.height);
    arb_add(absolute_height.value, absolute_height.value, u.value,
            options.precision);
    arb_mul(absolute_height.value, absolute_height.value, pi.value,
            options.precision);
    arb_mul_2exp_si(absolute_height.value, absolute_height.value, -2);
    arb_add(acb_realref(direct.value), acb_realref(direct.value),
            absolute_height.value, options.precision);
    if (!acb_contains(polynomial.value, direct.value)) return false;
  }
  return true;
}

unsigned char hex_nibble(char value) {
  if (value >= '0' && value <= '9') {
    return static_cast<unsigned char>(value - '0');
  }
  if (value >= 'a' && value <= 'f') {
    return static_cast<unsigned char>(10 + value - 'a');
  }
  if (value >= 'A' && value <= 'F') {
    return static_cast<unsigned char>(10 + value - 'A');
  }
  fail("invalid pinned SHA-256 hex digit");
}

std::array<unsigned char, 32> decode_sha256(const char* hexadecimal) {
  if (std::strlen(hexadecimal) != 64U) {
    fail("pinned SHA-256 has the wrong length");
  }
  std::array<unsigned char, 32> result{};
  for (std::size_t index = 0; index < result.size(); ++index) {
    result[index] = static_cast<unsigned char>(
        (hex_nibble(hexadecimal[index * 2U]) << 4U) |
        hex_nibble(hexadecimal[index * 2U + 1U]));
  }
  return result;
}

pw::GammaTaylorStreamRecord project_stream_record(
    const TaylorCertificate& certificate, const Options& options) {
  pw::GammaTaylorStreamRecord result{};
  for (long index = 0; index < options.degree; ++index) {
    const acb_srcptr coefficient =
        acb_poly_get_coeff_ptr(certificate.coefficients.value, index);
    const Binary64Interval real =
        project_binary64(acb_realref(coefficient), options.precision);
    const Binary64Interval imaginary =
        project_binary64(acb_imagref(coefficient), options.precision);
    result.real_coefficients[index] = {real.lower, real.upper};
    result.imaginary_coefficients[index] = {imaginary.lower,
                                             imaginary.upper};
  }

  const acb_srcptr constant =
      acb_poly_get_coeff_ptr(certificate.coefficients.value, 0);
  const acb_srcptr linear =
      acb_poly_get_coeff_ptr(certificate.coefficients.value, 1);
  const FixedTurnProjection phase_anchor =
      project_fixed_turn(acb_imagref(constant), options.precision);
  ArbValue phase_step_angle;
  arb_mul_si(phase_step_angle.value, acb_imagref(linear), 21,
             options.precision);
  arb_mul_2exp_si(phase_step_angle.value, phase_step_angle.value, -7);
  const FixedTurnProjection phase_step =
      project_fixed_turn(phase_step_angle.value, options.precision);
  result.phase_anchor = {phase_anchor.limbs[0], phase_anchor.limbs[1],
                         phase_anchor.limbs[2]};
  result.phase_grid_step = {phase_step.limbs[0], phase_step.limbs[1],
                            phase_step.limbs[2]};
  result.phase_anchor_error = phase_anchor.angular_error_upper;
  result.phase_grid_step_error = phase_step.angular_error_upper;
  const Binary64Interval remainder =
      project_binary64(certificate.remainder.value, options.precision);
  result.logarithm_remainder = remainder.upper;

  auto valid_interval = [](const pw::RealInterval& interval) {
    return std::isfinite(interval.lo) && std::isfinite(interval.hi) &&
           interval.lo <= interval.hi;
  };
  for (std::uint32_t index = 0; index < pw::kGammaTaylorDegree; ++index) {
    if (!valid_interval(result.real_coefficients[index]) ||
        !valid_interval(result.imaginary_coefficients[index])) {
      fail("Gamma Taylor projection contains an invalid coefficient");
    }
  }
  if (!std::isfinite(result.phase_anchor_error) ||
      !std::isfinite(result.phase_grid_step_error) ||
      !std::isfinite(result.logarithm_remainder) ||
      result.phase_anchor_error < 0.0 ||
      result.phase_grid_step_error < 0.0 ||
      result.logarithm_remainder < 0.0) {
    fail("Gamma Taylor projection contains an invalid error bound");
  }
  return result;
}

pw::GammaTaylorStreamHeader make_stream_header(const Options& options) {
  pw::GammaTaylorStreamHeader header{};
  header.magic = pw::kGammaTaylorStreamMagic;
  header.version = pw::kGammaTaylorStreamVersion;
  header.header_bytes = sizeof(header);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.record_encoding = pw::kGammaTaylorStreamEncoding;
  header.record_bytes = sizeof(pw::GammaTaylorStreamRecord);
  header.chunk_records = options.stream_chunk_records;
  header.degree = pw::kGammaTaylorDegree;
  header.precision_bits = pw::kGammaTaylorPrecision;
  header.source_lower = pw::kSourceLower;
  header.source_step = pw::kWindowStep;
  header.full_block_count = pw::kFullBlockCount;
  header.first_block = options.stream_first_block;
  header.block_count = options.stream_blocks;
  header.radius_numerator = kRadiusNumerator;
  header.radius_denominator = kRadiusDenominator;
  header.grid_step_numerator = 21;
  header.grid_step_denominator = 128;
  header.gaussian_h = 116;
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());
  constexpr char flint_commit[] = SPARKINTERVAL_FLINT_PLATT_COMMIT;
  static_assert(sizeof(flint_commit) == 41U);
  std::memcpy(header.flint_commit.data(), flint_commit,
              header.flint_commit.size());
  header.reviewed_source_sha256 =
      decode_sha256(kReviewedPlattSourceSha256);
  static_assert(sizeof(kGammaTaylorContractId) <=
                sizeof(header.contract_id));
  std::memcpy(header.contract_id.data(), kGammaTaylorContractId,
              sizeof(kGammaTaylorContractId) - 1U);
  return header;
}

struct GammaTaylorStreamResult {
  std::uint64_t chunks = 0U;
  std::uint64_t audits = 0U;
  std::uint64_t record_payload_bytes = 0U;
  std::uint64_t authenticated_stream_bytes = 0U;
  std::uint64_t artifact_bytes = 0U;
  double elapsed_seconds = 0.0;
  std::string header_sha256;
  std::string stream_sha256;
  std::string first_record_sha256;
  std::string last_record_sha256;
};

GammaTaylorStreamResult produce_stream(const Options& options) {
  if constexpr (std::endian::native != std::endian::little) {
    fail("Gamma Taylor stream v1 requires a little-endian host");
  }
  static_assert(std::numeric_limits<double>::is_iec559);
  const pw::GammaTaylorStreamHeader header = make_stream_header(options);
  const auto header_digest = sparkinterval::sha256(&header, sizeof(header));

  std::ofstream output;
  if (!options.stream_hash_only) {
    output.open(options.stream_output, std::ios::binary | std::ios::trunc);
    if (!output) fail("cannot open Gamma Taylor stream output");
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    if (!output) fail("cannot write Gamma Taylor stream header");
  }

  sparkinterval::detail::Sha256 stream_hasher;
  stream_hasher.update(kGammaTaylorStreamHashDomain,
                       sizeof(kGammaTaylorStreamHashDomain) - 1U);
  stream_hasher.update(&header, sizeof(header));
  GammaTaylorStreamResult result;
  result.header_sha256 = sparkinterval::lowercase_hex(header_digest);
  result.authenticated_stream_bytes = sizeof(header);

  TaylorCertificate certificate;
  std::vector<pw::GammaTaylorStreamRecord> records;
  records.reserve(options.stream_chunk_records);
  const auto started = std::chrono::steady_clock::now();
  std::uint64_t produced = 0U;
  while (produced < options.stream_blocks) {
    const std::uint64_t remaining = options.stream_blocks - produced;
    const std::uint32_t chunk_count = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(remaining, options.stream_chunk_records));
    records.clear();
    for (std::uint32_t local = 0; local < chunk_count; ++local) {
      const std::uint64_t relative = produced + local;
      const std::uint64_t block = options.stream_first_block + relative;
      const std::uint64_t height =
          pw::kSourceLower + pw::kWindowStep / 2U +
          block * pw::kWindowStep;
      Options at_height = options;
      at_height.height = height;
      acb_poly_zero(certificate.coefficients.value);
      arb_zero(certificate.remainder.value);
      compute_certificate(&certificate, at_height);
      const bool endpoint = relative == 0U ||
                            relative + 1U == options.stream_blocks;
      const bool stride_audit = options.stream_audit_stride != 0U &&
                                block % options.stream_audit_stride == 0U;
      if (endpoint || stride_audit) {
        if (!audit_certificate(certificate, at_height)) {
          fail("stream Taylor enclosure missed a direct FLINT audit sample");
        }
        ++result.audits;
      }
      records.push_back(project_stream_record(certificate, at_height));
    }

    const std::size_t payload_bytes =
        records.size() * sizeof(pw::GammaTaylorStreamRecord);
    pw::GammaTaylorChunkHeader chunk{};
    chunk.magic = pw::kGammaTaylorChunkMagic;
    chunk.version = pw::kGammaTaylorStreamVersion;
    chunk.header_bytes = sizeof(chunk);
    chunk.first_block = options.stream_first_block + produced;
    chunk.record_count = chunk_count;
    chunk.payload_bytes = payload_bytes;
    chunk.payload_sha256 =
        sparkinterval::sha256(records.data(), payload_bytes);
    stream_hasher.update(&chunk, sizeof(chunk));
    stream_hasher.update(records.data(), payload_bytes);
    if (!options.stream_hash_only) {
      output.write(reinterpret_cast<const char*>(&chunk), sizeof(chunk));
      output.write(reinterpret_cast<const char*>(records.data()),
                   static_cast<std::streamsize>(payload_bytes));
      if (!output) fail("cannot write complete Gamma Taylor stream chunk");
    }
    if (produced == 0U) {
      result.first_record_sha256 = sparkinterval::sha256_hex(
          records.data(), sizeof(pw::GammaTaylorStreamRecord));
    }
    result.last_record_sha256 = sparkinterval::sha256_hex(
        &records.back(), sizeof(pw::GammaTaylorStreamRecord));
    result.record_payload_bytes += payload_bytes;
    result.authenticated_stream_bytes += sizeof(chunk) + payload_bytes;
    produced += chunk_count;
    ++result.chunks;
  }

  const auto stream_digest = stream_hasher.finish();
  result.stream_sha256 = sparkinterval::lowercase_hex(stream_digest);
  pw::GammaTaylorStreamFooter footer{};
  footer.magic = pw::kGammaTaylorFooterMagic;
  footer.version = pw::kGammaTaylorStreamVersion;
  footer.footer_bytes = sizeof(footer);
  footer.first_block = options.stream_first_block;
  footer.block_count = options.stream_blocks;
  footer.chunk_count = result.chunks;
  footer.record_payload_bytes = result.record_payload_bytes;
  footer.authenticated_stream_bytes = result.authenticated_stream_bytes;
  footer.header_sha256 = header_digest;
  footer.stream_sha256 = stream_digest;
  if (!options.stream_hash_only) {
    output.write(reinterpret_cast<const char*>(&footer), sizeof(footer));
    output.close();
    if (!output) fail("cannot write complete Gamma Taylor stream footer");
  }
  result.artifact_bytes =
      result.authenticated_stream_bytes + sizeof(footer);
  const auto stopped = std::chrono::steady_clock::now();
  result.elapsed_seconds =
      std::chrono::duration<double>(stopped - started).count();
  return result;
}

int run_stream(const Options& options) {
  const GammaTaylorStreamResult result = produce_stream(options);
  const double records_per_second =
      static_cast<double>(options.stream_blocks) / result.elapsed_seconds;
  const double projected_full_single_core_hours =
      static_cast<double>(pw::kFullBlockCount) / records_per_second / 3600.0;
  const double seven_day_aggregate_bytes_per_second =
      static_cast<double>(pw::kFullBlockCount) *
      sizeof(pw::GammaTaylorStreamRecord) / (7.0 * 86400.0);
  const std::uint64_t first_height =
      pw::kSourceLower + pw::kWindowStep / 2U +
      options.stream_first_block * pw::kWindowStep;
  const std::uint64_t last_height =
      first_height + (options.stream_blocks - 1U) * pw::kWindowStep;
  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-gamma-taylor-stream.v1\""
            << ",\"claim_scope\":\"all_window_outward_flint_projection_stream\""
            << ",\"first_block\":" << options.stream_first_block
            << ",\"block_count\":" << options.stream_blocks
            << ",\"full_block_count\":" << pw::kFullBlockCount
            << ",\"first_window_center\":" << first_height
            << ",\"last_window_center\":" << last_height
            << ",\"record_bytes\":" << sizeof(pw::GammaTaylorStreamRecord)
            << ",\"chunk_records\":" << options.stream_chunk_records
            << ",\"chunk_count\":" << result.chunks
            << ",\"record_payload_bytes\":"
            << result.record_payload_bytes
            << ",\"artifact_bytes\":" << result.artifact_bytes
            << ",\"hash_only\":"
            << (options.stream_hash_only ? "true" : "false")
            << ",\"header_sha256\":\"" << result.header_sha256 << "\""
            << ",\"stream_sha256\":\"" << result.stream_sha256 << "\""
            << ",\"first_record_sha256\":\""
            << result.first_record_sha256 << "\""
            << ",\"last_record_sha256\":\""
            << result.last_record_sha256 << "\""
            << ",\"audit_stride\":" << options.stream_audit_stride
            << ",\"audit_samples_per_record\":" << options.audit_samples
            << ",\"audited_records\":" << result.audits
            << ",\"audit_passed\":true"
            << ",\"elapsed_seconds\":" << result.elapsed_seconds
            << ",\"records_per_second\":" << records_per_second
            << ",\"projected_full_single_core_hours\":"
            << projected_full_single_core_hours
            << ",\"seven_day_aggregate_feed_bytes_per_second\":"
            << seven_day_aggregate_bytes_per_second
            << ",\"upstream_commit\":\"" << pw::kUpstreamCommit << "\""
            << ",\"reviewed_source_sha256\":\""
            << kReviewedPlattSourceSha256 << "\""
            << ",\"flint_version\":\"3.6.0\""
            << ",\"flint_commit\":\""
            << SPARKINTERVAL_FLINT_PLATT_COMMIT << "\""
            << ",\"binary64_projection_outward\":true"
            << ",\"chunk_authentication\":\"sha256\""
            << ",\"complete_stream_authentication\":\"sha256\""
            << ",\"execution_attested\":false"
            << ",\"flint_to_mathlib_realization_proved\":false"
            << ",\"pt21_source_claim_discharged\":false}\n";
  flint_cleanup_master();
  return 0;
}

std::string json_interval(const DyadicInterval& interval) {
  return "{\"lo\":\"" + interval.lower + "\",\"hi\":\"" +
         interval.upper + "\"}";
}

std::string source_value_probe(std::uint32_t index, const Options& options) {
  constexpr std::uint32_t kGridCount = 32768;
  if (index >= kGridCount) fail("Gamma probe index is outside the source grid");
  ArbValue u;
  const std::int64_t offset =
      static_cast<std::int64_t>(index) - kGridCount / 2;
  arb_set_si(u.value, offset * 21);
  arb_mul_2exp_si(u.value, u.value, -7);

  AcbValue argument;
  arb_set_ui(acb_realref(argument.value), 1);
  arb_mul_2exp_si(acb_realref(argument.value),
                  acb_realref(argument.value), -2);
  set_exact_height_half(acb_imagref(argument.value), options.height);
  ArbValue half_u;
  arb_mul_2exp_si(half_u.value, u.value, -1);
  arb_add(acb_imagref(argument.value), acb_imagref(argument.value),
          half_u.value, options.precision);

  AcbValue value;
  acb_lgamma(value.value, argument.value, options.precision);
  ArbValue pi;
  ArbValue absolute_height;
  ArbValue gaussian;
  arb_const_pi(pi.value, options.precision);
  arb_set_ui(absolute_height.value, options.height);
  arb_add(absolute_height.value, absolute_height.value, u.value,
          options.precision);
  arb_mul(absolute_height.value, absolute_height.value, pi.value,
          options.precision);
  arb_mul_2exp_si(absolute_height.value, absolute_height.value, -2);
  arb_add(acb_realref(value.value), acb_realref(value.value),
          absolute_height.value, options.precision);
  arb_mul(gaussian.value, u.value, u.value, options.precision);
  arb_div_ui(gaussian.value, gaussian.value, 26912, options.precision);
  arb_sub(acb_realref(value.value), acb_realref(value.value), gaussian.value,
          options.precision);
  acb_exp(value.value, value.value, options.precision);
  const Binary64Interval real =
      project_binary64(acb_realref(value.value), options.precision);
  const Binary64Interval imaginary =
      project_binary64(acb_imagref(value.value), options.precision);
  return "{\"index\":" + std::to_string(index) +
         ",\"re\":" + json_binary64_interval(real) +
         ",\"im\":" + json_binary64_interval(imaginary) + "}";
}

struct DDProjection {
  pw::DoubleDouble center;
  double radius;
};

DDProjection project_arb_dd(const arb_t value, long precision) {
  ArfValue lower;
  ArfValue upper;
  ArfValue midpoint;
  ArfValue high;
  ArfValue low;
  ArfValue center;
  ArfValue left_error;
  ArfValue right_error;
  arb_get_interval_arf(lower.value, upper.value, value, precision);
  arf_add(midpoint.value, lower.value, upper.value, ARF_PREC_EXACT,
          ARF_RND_NEAR);
  arf_mul_2exp_si(midpoint.value, midpoint.value, -1);
  const double hi = arf_get_d(midpoint.value, ARF_RND_NEAR);
  arf_set_d(high.value, hi);
  arf_sub(low.value, midpoint.value, high.value, ARF_PREC_EXACT,
          ARF_RND_NEAR);
  const double lo = arf_get_d(low.value, ARF_RND_NEAR);
  arf_set_d(center.value, hi);
  arf_set_d(low.value, lo);
  arf_add(center.value, center.value, low.value, ARF_PREC_EXACT,
          ARF_RND_NEAR);
  arf_sub(left_error.value, center.value, lower.value, ARF_PREC_EXACT,
          ARF_RND_NEAR);
  arf_abs(left_error.value, left_error.value);
  arf_sub(right_error.value, upper.value, center.value, ARF_PREC_EXACT,
          ARF_RND_NEAR);
  arf_abs(right_error.value, right_error.value);
  const arf_srcptr larger =
      arf_cmp(left_error.value, right_error.value) >= 0
          ? left_error.value
          : right_error.value;
  return {{hi, lo}, arf_get_d(larger, ARF_RND_CEIL)};
}

pw::ComplexDisk106 project_acb_dd(const acb_t value, long precision) {
  const DDProjection re = project_arb_dd(acb_realref(value), precision);
  const DDProjection im = project_arb_dd(acb_imagref(value), precision);
  // L1 dominates the Euclidean coordinate error.  One successor makes the
  // binary64 addition outward without relying on the host rounding mode.
  const double radius = std::nextafter(
      re.radius + im.radius, std::numeric_limits<double>::infinity());
  return {re.center, im.center, radius};
}

std::uint64_t fnv1a_bytes(const void* raw, std::size_t size) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = static_cast<const unsigned char*>(raw);
  for (std::size_t index = 0; index < size; ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

std::vector<pw::ComplexDisk106> build_dd_gamma_row(
    const TaylorCertificate& certificate, const Options& options) {
  std::vector<pw::ComplexDisk106> result(pw::kBucketCount);
  for (std::uint32_t index = 0; index < pw::kBucketCount; ++index) {
    ArbValue u;
    const std::int64_t offset = static_cast<std::int64_t>(index) -
                                pw::kBucketCount / 2;
    arb_set_si(u.value, offset * 21);
    arb_mul_2exp_si(u.value, u.value, -7);
    AcbValue logarithm;
    evaluate_polynomial(logarithm.value, certificate.coefficients.value,
                        u.value, options.degree, options.precision);
    acb_add_error_arb(logarithm.value, certificate.remainder.value);
    ArbValue gaussian;
    arb_mul(gaussian.value, u.value, u.value, options.precision);
    arb_div_ui(gaussian.value, gaussian.value, 26912, options.precision);
    arb_sub(acb_realref(logarithm.value), acb_realref(logarithm.value),
            gaussian.value, options.precision);
    acb_exp(logarithm.value, logarithm.value, options.precision);
    result[index] = project_acb_dd(logarithm.value, options.precision);
  }
  return result;
}

struct GammaRowExport {
  std::string sha256;
  std::uint64_t bytes = 0U;
  std::uint64_t fnv1a64 = 0U;
};

GammaRowExport write_dd_gamma_row(
    const std::string& path, const std::vector<pw::ComplexDisk106>& row,
    const Options& options) {
  if (row.size() != pw::kBucketCount) {
    fail("two-limb Gamma row has the wrong fixed geometry");
  }
  pw::SourcePacketHeader header{};
  header.magic = pw::kGammaPacket106Magic;
  header.version = pw::kSourcePacket106Version;
  header.header_bytes = sizeof(header);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.interval_encoding = pw::kSourcePacket106Encoding;
  header.bucket_count = pw::kBucketCount;
  header.taylor_terms = static_cast<std::uint32_t>(options.degree);
  header.source_terms = 0U;
  header.reserved_zero = 0U;
  header.window_center = options.height;
  header.gamma_count = row.size();
  header.skn_count = 0U;
  header.payload_bytes = row.size() * sizeof(pw::ComplexDisk106);
  header.gamma_fnv1a64 = fnv1a_bytes(row.data(), header.payload_bytes);
  header.skn_fnv1a64 = fnv1a_bytes(nullptr, 0U);
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());
  std::vector<unsigned char> bytes(sizeof(header) + header.payload_bytes);
  std::memcpy(bytes.data(), &header, sizeof(header));
  std::memcpy(bytes.data() + sizeof(header), row.data(),
              header.payload_bytes);
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) fail("cannot open two-limb Gamma row output");
  output.write(reinterpret_cast<const char*>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  output.close();
  if (!output) fail("cannot write complete two-limb Gamma row");
  return {sparkinterval::sha256_hex(bytes.data(), bytes.size()), bytes.size(),
          header.gamma_fnv1a64};
}

int run(const Options& options) {
  require_flint_identity();
  if (options.stream_blocks != 0U) return run_stream(options);
  const auto started = std::chrono::steady_clock::now();
  TaylorCertificate last;
  for (std::uint64_t iteration = 0; iteration < options.repeat; ++iteration) {
    acb_poly_zero(last.coefficients.value);
    arb_zero(last.remainder.value);
    compute_certificate(&last, options);
  }
  const auto stopped = std::chrono::steady_clock::now();
  const bool audit_ok = audit_certificate(last, options);
  if (!audit_ok) fail("Taylor enclosure missed a direct FLINT audit sample");
  std::vector<pw::ComplexDisk106> dd_gamma_row;
  GammaRowExport dd_gamma_export;
  double dd_gamma_seconds = 0.0;
  if (!options.export_dd_gamma_row.empty()) {
    const auto gamma_started = std::chrono::steady_clock::now();
    dd_gamma_row = build_dd_gamma_row(last, options);
    const auto gamma_stopped = std::chrono::steady_clock::now();
    dd_gamma_seconds =
        std::chrono::duration<double>(gamma_stopped - gamma_started).count();
    dd_gamma_export = write_dd_gamma_row(options.export_dd_gamma_row,
                                         dd_gamma_row, options);
  }

  std::vector<std::string> coefficient_rows;
  std::vector<std::string> binary64_rows;
  coefficient_rows.reserve(static_cast<std::size_t>(options.degree));
  binary64_rows.reserve(static_cast<std::size_t>(options.degree));
  sparkinterval::detail::Sha256 transcript_hash;
  sparkinterval::detail::Sha256 projection_hash;
  for (long index = 0; index < options.degree; ++index) {
    const acb_srcptr coefficient =
        acb_poly_get_coeff_ptr(last.coefficients.value, index);
    const DyadicInterval real =
        dump_interval(acb_realref(coefficient), options.precision);
    const DyadicInterval imaginary =
        dump_interval(acb_imagref(coefficient), options.precision);
    std::ostringstream row;
    row << index << '\t' << real.lower << '\t' << real.upper << '\t'
        << imaginary.lower << '\t' << imaginary.upper << '\n';
    const std::string canonical = row.str();
    transcript_hash.update(canonical.data(), canonical.size());
    coefficient_rows.push_back("{\"degree\":" + std::to_string(index) +
                               ",\"re\":" + json_interval(real) +
                               ",\"im\":" + json_interval(imaginary) +
                               "}");
    const Binary64Interval real64 =
        project_binary64(acb_realref(coefficient), options.precision);
    const Binary64Interval imaginary64 =
        project_binary64(acb_imagref(coefficient), options.precision);
    const std::string projection_row =
        std::to_string(index) + "\t" + hex_double(real64.lower) + "\t" +
        hex_double(real64.upper) + "\t" + hex_double(imaginary64.lower) +
        "\t" + hex_double(imaginary64.upper) + "\n";
    projection_hash.update(projection_row.data(), projection_row.size());
    binary64_rows.push_back(
        "{\"degree\":" + std::to_string(index) + ",\"re\":" +
        json_binary64_interval(real64) + ",\"im\":" +
        json_binary64_interval(imaginary64) + "}");
  }
  const DyadicInterval remainder =
      dump_interval(last.remainder.value, options.precision);
  const std::string remainder_row =
      "remainder\t" + remainder.lower + "\t" + remainder.upper + "\n";
  transcript_hash.update(remainder_row.data(), remainder_row.size());
  const std::string digest =
      sparkinterval::lowercase_hex(transcript_hash.finish());
  const acb_srcptr constant =
      acb_poly_get_coeff_ptr(last.coefficients.value, 0);
  const acb_srcptr linear =
      acb_poly_get_coeff_ptr(last.coefficients.value, 1);
  const FixedTurnProjection phase_anchor =
      project_fixed_turn(acb_imagref(constant), options.precision);
  ArbValue phase_step_angle;
  arb_mul_si(phase_step_angle.value, acb_imagref(linear), 21,
             options.precision);
  arb_mul_2exp_si(phase_step_angle.value, phase_step_angle.value, -7);
  const FixedTurnProjection phase_step =
      project_fixed_turn(phase_step_angle.value, options.precision);
  const Binary64Interval remainder64 =
      project_binary64(last.remainder.value, options.precision);
  std::ostringstream fixed_projection;
  fixed_projection << "anchor\t" << hex_u64(phase_anchor.limbs[0]) << '\t'
                   << hex_u64(phase_anchor.limbs[1]) << '\t'
                   << hex_u64(phase_anchor.limbs[2]) << '\t'
                   << hex_double(phase_anchor.angular_error_upper) << '\n'
                   << "step\t" << hex_u64(phase_step.limbs[0]) << '\t'
                   << hex_u64(phase_step.limbs[1]) << '\t'
                   << hex_u64(phase_step.limbs[2]) << '\t'
                   << hex_double(phase_step.angular_error_upper) << '\n'
                   << "remainder\t" << hex_double(remainder64.lower) << '\t'
                   << hex_double(remainder64.upper) << '\n';
  const std::string fixed_projection_rows = fixed_projection.str();
  projection_hash.update(fixed_projection_rows.data(),
                         fixed_projection_rows.size());
  const std::string projected_digest =
      sparkinterval::lowercase_hex(projection_hash.finish());
  const double elapsed_seconds =
      std::chrono::duration<double>(stopped - started).count();

  std::cout
      << "{\"schema\":\"sparkinterval.tg.platt-gamma-taylor.v1\""
      << ",\"claim_scope\":\"compact_flint_gamma_taylor_certificate\""
      << ",\"height\":" << options.height
      << ",\"source_radius\":\"2688\""
      << ",\"source_grid_step\":\"21/128\""
      << ",\"gaussian_h\":\"116\""
      << ",\"degree\":" << options.degree
      << ",\"precision_bits\":" << options.precision
      << ",\"coefficients\":[";
  for (std::size_t index = 0; index < coefficient_rows.size(); ++index) {
    if (index != 0) std::cout << ',';
    std::cout << coefficient_rows[index];
  }
  std::cout << "]"
            << ",\"remainder_abs\":" << json_interval(remainder)
            << ",\"binary64_coefficients\":[";
  for (std::size_t index = 0; index < binary64_rows.size(); ++index) {
    if (index != 0) std::cout << ',';
    std::cout << binary64_rows[index];
  }
  auto print_fixed_turn = [](const FixedTurnProjection& projection) {
    std::cout << "{\"limbs_le\":[\"" << hex_u64(projection.limbs[0])
              << "\",\"" << hex_u64(projection.limbs[1]) << "\",\""
              << hex_u64(projection.limbs[2]) << "\"]"
              << ",\"angular_error\":"
              << json_interval(projection.angular_error)
              << ",\"angular_error_upper_hex\":\""
              << hex_double(projection.angular_error_upper) << "\"}";
  };
  std::cout << "]"
            << ",\"phase_anchor_q192\":";
  print_fixed_turn(phase_anchor);
  std::cout << ",\"phase_grid_step_q192\":";
  print_fixed_turn(phase_step);
  std::cout << ",\"remainder_binary64\":"
            << json_binary64_interval(remainder64)
            << ",\"source_value_probes\":[";
  constexpr std::uint32_t probe_indices[] = {0U, 8192U, 16384U, 24576U,
                                              32767U};
  for (std::size_t probe = 0;
       probe < sizeof(probe_indices) / sizeof(probe_indices[0]); ++probe) {
    if (probe != 0U) std::cout << ',';
    std::cout << source_value_probe(probe_indices[probe], options);
  }
  std::cout << "]"
            << ",\"audit_samples\":" << options.audit_samples
            << ",\"audit_passed\":" << (audit_ok ? "true" : "false")
            << ",\"repeat\":" << options.repeat
            << ",\"elapsed_seconds\":" << elapsed_seconds
            << ",\"certificates_per_second\":"
            << static_cast<double>(options.repeat) / elapsed_seconds
            << ",\"coefficient_digest\":\"" << digest << "\""
            << ",\"projection_digest\":\"" << projected_digest << "\""
            << ",\"flint_version\":\"3.6.0\""
            << ",\"flint_commit\":\""
            << SPARKINTERVAL_FLINT_PLATT_COMMIT << "\""
            << ",\"dd_gamma_row_exported\":"
            << (!options.export_dd_gamma_row.empty() ? "true" : "false")
            << ",\"dd_gamma_row_schema\":\"sparkinterval.tg.platt-gamma-dd-row.v2\""
            << ",\"dd_gamma_row_cells\":" << dd_gamma_row.size()
            << ",\"dd_gamma_row_seconds\":" << dd_gamma_seconds
            << ",\"dd_gamma_row_bytes\":" << dd_gamma_export.bytes
            << ",\"dd_gamma_row_fnv1a64\":\""
            << hex_u64(dd_gamma_export.fnv1a64) << "\""
            << ",\"dd_gamma_row_sha256\":\"" << dd_gamma_export.sha256
            << "\""
            << ",\"execution_attested\":false"
            << ",\"lean_atom_discharged\":false}\n";
  flint_cleanup_master();
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    return run(parse_options(argc, argv));
  } catch (const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 2;
  }
}

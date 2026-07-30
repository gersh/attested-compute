// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Exact-rational one-sided Turing input construction shared by the standalone
// producer executable and the fused source worker.
//
// This file is a verbatim relocation of the arithmetic that previously lived
// inside `reference/tg_platt_pt21_turing_inputs.cpp`.  Both consumers now call
// the same function, so their canonical artifacts are byte-identical by
// construction rather than by convention.

#include "sparkinterval/tg_platt_pt21_turing_inputs.hpp"

#include <flint/arb.h>
#include <flint/arf.h>
#include <flint/flint.h>
#include <flint/fmpq.h>
#include <flint/fmpz.h>

#include <limits>
#include <sstream>
#include <string>
#include <string_view>

namespace sparkinterval::tg::platt_pt21_turing_inputs {

namespace {

constexpr slong kRetainedPrecision = kRetainedPrecisionBits;
constexpr slong kReplayPrecision = kReplayPrecisionBits;

class ArbValue {
 public:
  ArbValue() { arb_init(value_); }
  ~ArbValue() { arb_clear(value_); }
  ArbValue(const ArbValue&) = delete;
  ArbValue& operator=(const ArbValue&) = delete;
  arb_ptr get() { return value_; }
  arb_srcptr get() const { return value_; }

 private:
  arb_t value_;
};

class ArfValue {
 public:
  ArfValue() { arf_init(value_); }
  ~ArfValue() { arf_clear(value_); }
  ArfValue(const ArfValue&) = delete;
  ArfValue& operator=(const ArfValue&) = delete;
  arf_ptr get() { return value_; }
  arf_srcptr get() const { return value_; }

 private:
  arf_t value_;
};

class FmpqValue {
 public:
  FmpqValue() { fmpq_init(value_); }
  ~FmpqValue() { fmpq_clear(value_); }
  FmpqValue(const FmpqValue&) = delete;
  FmpqValue& operator=(const FmpqValue&) = delete;
  fmpq* get() { return value_; }

 private:
  fmpq_t value_;
};

struct SideValues {
  ArbValue s_bound;
  ArbValue log_pi;
  ArbValue im_gamma_integral;
  ArbValue pi;
};

[[noreturn]] void fail(const std::string& message) {
  throw TuringInputsError(message);
}

std::string dump_fmpz(const fmpz* value) {
  char* raw = fmpz_get_str(nullptr, 10, value);
  if (raw == nullptr) fail("fmpz_get_str returned null");
  std::string result(raw);
  flint_free(raw);
  return result;
}

std::string rational_json(arf_srcptr value) {
  if (!arf_is_finite(value)) fail("an extracted endpoint is not finite");
  FmpqValue rational;
  arf_get_fmpq(rational.get(), value);
  fmpq_canonicalise(rational.get());
  return "{\"denominator\":" + dump_fmpz(fmpq_denref(rational.get())) +
         ",\"numerator\":" + dump_fmpz(fmpq_numref(rational.get())) + "}";
}

std::string interval_json(arb_srcptr value) {
  if (!arb_is_finite(value)) fail("an Arb result is not finite");
  ArfValue lower;
  ArfValue upper;
  arb_get_interval_arf(lower.get(), upper.get(), value, kRetainedPrecision);
  if (arf_cmp(lower.get(), upper.get()) > 0) {
    fail("an extracted interval has reversed endpoints");
  }
  return "{\"hi\":" + rational_json(upper.get()) +
         ",\"lo\":" + rational_json(lower.get()) + "}";
}

void set_u64(arb_t value, std::uint64_t input) {
  // The campaign heights fit in an unsigned long on every supported
  // production target, but using an fmpz keeps this source correct on a
  // platform whose unsigned long is narrower.
  fmpz_t integer;
  fmpz_init(integer);
  fmpz_set_ui(integer, static_cast<ulong>(input));
  if constexpr (std::numeric_limits<ulong>::max() <
                std::numeric_limits<std::uint64_t>::max()) {
    if (input > std::numeric_limits<ulong>::max()) {
      fmpz_clear(integer);
      fail("campaign height does not fit the platform unsigned long");
    }
  }
  arb_set_fmpz(value, integer);
  fmpz_clear(integer);
}

void set_fraction(arb_t value, ulong numerator, ulong denominator, slong prec) {
  arb_set_ui(value, numerator);
  arb_div_ui(value, value, denominator, prec);
}

// Literal transcription of zeta_arb/turing.c::St_int, with its decimal
// constants represented by the exact source rationals 59/1000 and 2067/1000.
void st_int(arb_t result, arb_srcptr t, slong prec) {
  ArbValue c1;
  ArbValue c2;
  set_fraction(c1.get(), 59, 1000, prec);
  set_fraction(c2.get(), 2067, 1000, prec);
  arb_log(result, t, prec);
  arb_mul(result, result, c1.get(), prec);
  arb_add(result, result, c2.get(), prec);
}

// Literal exact-rational version of zeta_arb/turing.c::im_int1.
void im_int1(arb_t result, arb_srcptr t, slong prec) {
  ArbValue temporary;
  ArbValue work;

  arb_mul_2exp_si(temporary.get(), t, 2);
  arb_atan(result, temporary.get(), prec);
  arb_mul(result, result, t, prec);
  arb_div_ui(result, result, 4, prec);
  arb_neg(result, result);

  arb_mul(temporary.get(), t, t, prec);
  arb_mul_ui(work.get(), temporary.get(), 3, prec);
  arb_div_ui(work.get(), work.get(), 4, prec);
  arb_neg(work.get(), work.get());
  arb_add(result, result, work.get(), prec);

  arb_mul_ui(work.get(), temporary.get(), 16, prec);
  arb_add_ui(work.get(), work.get(), 1, prec);
  arb_log(work.get(), work.get(), prec);
  arb_div_ui(work.get(), work.get(), 32, prec);
  arb_add(result, result, work.get(), prec);

  arb_set_si(work.get(), -1);
  arb_div_ui(work.get(), work.get(), 64, prec);
  arb_add(result, result, work.get(), prec);

  arb_set_ui(work.get(), 1);
  arb_div_ui(work.get(), work.get(), 16, prec);
  arb_add(temporary.get(), temporary.get(), work.get(), prec);
  arb_log(work.get(), temporary.get(), prec);
  arb_mul(temporary.get(), temporary.get(), work.get(), prec);
  arb_div_ui(temporary.get(), temporary.get(), 4, prec);
  arb_add(result, result, temporary.get(), prec);
}

// Literal exact-rational version of zeta_arb/turing.c::im_int.  The explicit
// error radius (t1-t0)/(3*t0) encloses the omitted log-gamma remainder.
void im_int(arb_t result, arb_srcptr t0, arb_srcptr t1, slong prec) {
  ArbValue error;
  ArbValue at_t0;
  ArbValue at_t1;
  ArbValue temporary;

  arb_sub(temporary.get(), t1, t0, prec);
  arb_div_ui(error.get(), temporary.get(), 3, prec);
  arb_div(error.get(), error.get(), t0, prec);

  arb_mul_2exp_si(at_t0.get(), t0, -1);
  arb_mul_2exp_si(at_t1.get(), t1, -1);
  im_int1(result, at_t1.get(), prec);
  im_int1(temporary.get(), at_t0.get(), prec);
  arb_sub(result, result, temporary.get(), prec);
  arb_mul_ui(result, result, 2, prec);
  arb_add_error(result, error.get());
}

void compute_side(SideValues* result, std::uint64_t t0_integer,
                  std::uint64_t t1_integer, slong prec) {
  if (result == nullptr || t0_integer == 0 || t0_integer >= t1_integer ||
      t1_integer - t0_integer != kTuringWidth) {
    fail("one-sided Turing interval geometry is invalid");
  }
  ArbValue t0;
  ArbValue t1;
  set_u64(t0.get(), t0_integer);
  set_u64(t1.get(), t1_integer);

  arb_const_pi(result->pi.get(), prec);
  arb_log(result->log_pi.get(), result->pi.get(), prec);
  st_int(result->s_bound.get(), t1.get(), prec);
  im_int(result->im_gamma_integral.get(), t0.get(), t1.get(), prec);
}

void require_replay_contains(arb_srcptr retained, arb_srcptr replay,
                             std::string_view label) {
  if (!arb_is_finite(retained) || !arb_is_finite(replay) ||
      !arb_contains(retained, replay)) {
    fail(std::string(label) + " failed 256-bit containment replay");
  }
}

void validate_side(const SideValues& retained, const SideValues& replay,
                   std::string_view label) {
  require_replay_contains(retained.s_bound.get(), replay.s_bound.get(),
                          std::string(label) + ".s_bound");
  require_replay_contains(retained.log_pi.get(), replay.log_pi.get(),
                          std::string(label) + ".log_pi");
  require_replay_contains(retained.im_gamma_integral.get(),
                          replay.im_gamma_integral.get(),
                          std::string(label) + ".im_gamma_integral");
  require_replay_contains(retained.pi.get(), replay.pi.get(),
                          std::string(label) + ".pi");
  if (!arb_is_positive(retained.s_bound.get()) ||
      !arb_is_positive(retained.log_pi.get()) ||
      !arb_is_positive(retained.pi.get())) {
    fail(std::string(label) +
         " contains an ambiguous sign in a required positive input");
  }
}

std::string values_json(const SideValues& values) {
  return "{\"im_gamma_integral\":" +
         interval_json(values.im_gamma_integral.get()) +
         ",\"log_pi\":" + interval_json(values.log_pi.get()) +
         ",\"pi\":" + interval_json(values.pi.get()) +
         ",\"s_bound\":" + interval_json(values.s_bound.get()) + "}";
}

std::string side_json(std::string_view function_name, std::uint64_t t0,
                      std::uint64_t t1, const SideValues& values) {
  std::ostringstream output;
  output << "{\"function\":\"" << function_name << "\",\"interval\":{\"a\":"
         << t0 << ",\"b\":" << t1 << "},\"values\":" << values_json(values)
         << '}';
  return output.str();
}

}  // namespace

bool is_lower_sha256(std::string_view value) {
  if (value.size() != 64) return false;
  for (char character : value) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

std::string artifact_json(std::uint64_t block,
                          std::string_view required_sign_packet_sha256) {
  if (block >= kSourceBlockCount) {
    fail("Turing block is outside the PT21 source campaign");
  }
  if (!is_lower_sha256(required_sign_packet_sha256)) {
    fail("required-sign packet SHA-256 is not lowercase hexadecimal");
  }
  const std::uint64_t height_lower = kSourceLower + block * kSourceStep;
  const std::uint64_t height_upper = height_lower + kSourceStep;
  if (height_lower < kTuringWidth ||
      height_upper > std::numeric_limits<std::uint64_t>::max() -
                         kTuringWidth) {
    fail("derived PT21 source geometry overflows");
  }
  const std::uint64_t lower_a = height_lower - kTuringWidth;
  const std::uint64_t lower_b = height_lower;
  const std::uint64_t upper_a = height_upper;
  const std::uint64_t upper_b = height_upper + kTuringWidth;

  SideValues lower;
  SideValues upper;
  SideValues lower_replay;
  SideValues upper_replay;
  compute_side(&lower, lower_a, lower_b, kRetainedPrecision);
  compute_side(&upper, upper_a, upper_b, kRetainedPrecision);
  compute_side(&lower_replay, lower_a, lower_b, kReplayPrecision);
  compute_side(&upper_replay, upper_a, upper_b, kReplayPrecision);
  validate_side(lower, lower_replay, "lower");
  validate_side(upper, upper_replay, "upper");

  // Field order is lexicographic so the output is byte-for-byte canonical
  // under json.dumps(sort_keys=True, separators=(",", ":")).
  std::ostringstream output;
  output
      << "{\"algorithm\":\"" << kAlgorithm << "\",\"block\":" << block
      << ",\"flint_commit\":\"" << kFlintCommit << "\",\"inputs\":{\"lower\":"
      << side_json("turing_min", lower_a, lower_b, lower)
      << ",\"upper\":" << side_json("turing_max", upper_a, upper_b, upper)
      << "},\"precision_bits\":" << kRetainedPrecision
      << ",\"replay_precision_bits\":" << kReplayPrecision
      << ",\"required_sign_packet_sha256\":\""
      << required_sign_packet_sha256 << "\",\"schema\":\"" << kSchema
      << "\",\"semantic_status\":{\"analytic_turing_realization_proved\":false,"
         "\"arb_interval_arithmetic_executed\":true,"
         "\"hardy_z_endpoint_realization_proved\":false},"
         "\"source_identity\":{\"height_lower\":"
      << height_lower
      << ",\"height_upper\":" << height_upper
      << ",\"interpolation_patch_sha256\":\"" << kInterpolationPatchSha256
      << "\",\"source_turing_c_sha256\":\"" << kTuringSourceSha256
      << "\",\"upstream_commit\":\"" << kUpstreamCommit
      << "\"}}\n";
  std::string result = output.str();
  if (result.empty() || result.size() > kMaximumArtifactBytes) {
    fail("canonical Turing artifact leaves its byte bound");
  }
  return result;
}

}  // namespace sparkinterval::tg::platt_pt21_turing_inputs

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_stationary_resolver.hpp"

#include "sparkinterval/sha256.hpp"

#include <flint/arb.h>
#include <flint/arf.h>
#include <flint/flint.h>
#include <flint/fmpq.h>
#include <flint/fmpz.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace sparkinterval::tg::platt_stationary_resolver {
namespace {

constexpr std::int32_t kLeftFlankLower = -12'800;
constexpr std::int32_t kLeftFlankUpper = -12'288;
constexpr std::int32_t kMainLower = -12'288;
constexpr std::int32_t kMainUpper = 12'288;
constexpr std::int32_t kRightFlankLower = 12'288;
constexpr std::int32_t kRightFlankUpper = 12'800;
constexpr char kInputHashDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-input/v1\0";
constexpr char kResolutionHashDomain[] =
    "sparkinterval/tg/platt-pt21-stationary-resolutions/v1\0";

class ArbValue {
 public:
  ArbValue() { arb_init(value_); }
  ~ArbValue() { arb_clear(value_); }
  ArbValue(const ArbValue&) = delete;
  ArbValue& operator=(const ArbValue&) = delete;
  ArbValue(ArbValue&& other) noexcept {
    arb_init(value_);
    arb_swap(value_, other.value_);
  }
  ArbValue& operator=(ArbValue&& other) noexcept {
    arb_swap(value_, other.value_);
    return *this;
  }
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
  ArfValue(ArfValue&& other) noexcept {
    arf_init(value_);
    arf_swap(value_, other.value_);
  }
  ArfValue& operator=(ArfValue&& other) noexcept {
    arf_swap(value_, other.value_);
    return *this;
  }
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
  FmpqValue(FmpqValue&& other) noexcept {
    fmpq_init(value_);
    fmpq_swap(value_, other.value_);
  }
  FmpqValue& operator=(FmpqValue&& other) noexcept {
    fmpq_swap(value_, other.value_);
    return *this;
  }
  fmpq* get() { return value_; }
  const fmpq* get() const { return value_; }

 private:
  fmpq_t value_;
};

class ArbVector {
 public:
  explicit ArbVector(std::size_t count)
      : count_(count), values_(_arb_vec_init(static_cast<slong>(count))) {}
  ~ArbVector() { _arb_vec_clear(values_, static_cast<slong>(count_)); }
  ArbVector(const ArbVector&) = delete;
  ArbVector& operator=(const ArbVector&) = delete;
  arb_ptr operator[](std::size_t index) { return values_ + index; }
  arb_srcptr operator[](std::size_t index) const { return values_ + index; }

 private:
  std::size_t count_;
  arb_ptr values_;
};

class ArfVector {
 public:
  explicit ArfVector(std::size_t count)
      : count_(count), values_(_arf_vec_init(static_cast<slong>(count))) {}
  ~ArfVector() { _arf_vec_clear(values_, static_cast<slong>(count_)); }
  ArfVector(const ArfVector&) = delete;
  ArfVector& operator=(const ArfVector&) = delete;
  arf_ptr operator[](std::size_t index) { return values_ + index; }
  arf_srcptr operator[](std::size_t index) const { return values_ + index; }

 private:
  std::size_t count_;
  arf_ptr values_;
};

class ResolveFailure : public std::runtime_error {
 public:
  ResolveFailure(std::uint64_t flag, std::string message)
      : std::runtime_error(std::move(message)), flag_(flag) {}
  std::uint64_t flag() const { return flag_; }

 private:
  std::uint64_t flag_;
};

[[noreturn]] void reject(std::uint64_t flag, const std::string& message) {
  throw ResolveFailure(flag, message);
}

std::size_t sample_index(std::int32_t offset) {
  if (offset < kRequiredLower || offset > kRequiredUpper) {
    reject(kFailureInterpolationStencil,
           "interpolation stencil leaves the required sample region");
  }
  return static_cast<std::size_t>(offset - kRequiredLower);
}

std::pair<std::int32_t, std::int32_t> stream_range(StreamKind stream) {
  switch (stream) {
    case StreamKind::kLeftFlank:
      return {kLeftFlankLower, kLeftFlankUpper};
    case StreamKind::kMain:
      return {kMainLower, kMainUpper};
    case StreamKind::kRightFlank:
      return {kRightFlankLower, kRightFlankUpper};
  }
  reject(kFailureCandidateList, "candidate stream is outside 0..2");
}

std::string dump_arf(arf_srcptr value) {
  char* raw = arf_dump_str(value);
  if (raw == nullptr) reject(kFailureInternal, "arf_dump_str returned null");
  const std::string result(raw);
  flint_free(raw);
  return result;
}

std::string dump_fmpz(const fmpz* value) {
  char* raw = fmpz_get_str(nullptr, 10, value);
  if (raw == nullptr) reject(kFailureInternal, "fmpz_get_str returned null");
  const std::string result(raw);
  flint_free(raw);
  return result;
}

CanonicalRational canonical_rational(const fmpq* value) {
  return {dump_fmpz(fmpq_numref(value)), dump_fmpz(fmpq_denref(value))};
}

CanonicalRational canonical_rational(arf_srcptr value) {
  FmpqValue rational;
  arf_get_fmpq(rational.get(), value);
  fmpq_canonicalise(rational.get());
  return canonical_rational(rational.get());
}

CanonicalInterval canonical_interval(arb_srcptr value, slong precision) {
  ArfValue lower;
  ArfValue upper;
  arb_get_interval_arf(lower.get(), upper.get(), value, precision);
  return {canonical_rational(lower.get()), canonical_rational(upper.get())};
}

void load_rational(fmpq_t destination, const CanonicalRational& value) {
  const std::string text = value.numerator + "/" + value.denominator;
  if (fmpq_set_str(destination, text.c_str(), 10) != 0) {
    reject(kFailureReplay, "resolution contains a malformed rational");
  }
  fmpq_canonicalise(destination);
  if (canonical_rational(destination).numerator != value.numerator ||
      canonical_rational(destination).denominator != value.denominator) {
    reject(kFailureReplay, "resolution rational is not canonical");
  }
}

void exact_disk_bounds(const platt_windowed::RealDisk106& disk,
                       arf_t lower, arf_t upper) {
  if (!std::isfinite(disk.center.hi) ||
      !std::isfinite(disk.center.lo) || !std::isfinite(disk.radius) ||
      disk.radius < 0.0) {
    reject(kFailureMalformedDisk, "required DD disk is malformed");
  }
  ArfValue high;
  ArfValue low;
  ArfValue radius;
  ArfValue center;
  arf_set_d(high.get(), disk.center.hi);
  arf_set_d(low.get(), disk.center.lo);
  arf_set_d(radius.get(), disk.radius);
  arf_add(center.get(), high.get(), low.get(), ARF_PREC_EXACT, ARF_RND_NEAR);
  arf_sub(lower, center.get(), radius.get(), ARF_PREC_EXACT, ARF_RND_NEAR);
  arf_add(upper, center.get(), radius.get(), ARF_PREC_EXACT, ARF_RND_NEAR);
}

int exact_sign(arf_srcptr lower, arf_srcptr upper) {
  if (arf_cmp_si(lower, 0) > 0) return 1;
  if (arf_cmp_si(upper, 0) < 0) return -1;
  return 0;
}

bool exact_strict_gt(arf_srcptr left_lower, arf_srcptr right_upper) {
  return arf_cmp(left_lower, right_upper) > 0;
}

void append_u32(std::string* bytes, std::uint32_t value) {
  for (unsigned int index = 0; index < 4U; ++index) {
    bytes->push_back(static_cast<char>(value >> (8U * index)));
  }
}

void append_u64(std::string* bytes, std::uint64_t value) {
  for (unsigned int index = 0; index < 8U; ++index) {
    bytes->push_back(static_cast<char>(value >> (8U * index)));
  }
}

void append_i32(std::string* bytes, std::int32_t value) {
  append_u32(bytes, static_cast<std::uint32_t>(value));
}

void append_string(std::string* bytes, std::string_view value) {
  if (value.size() > std::numeric_limits<std::uint32_t>::max()) {
    reject(kFailureInputGeometry, "hashed string is too long");
  }
  append_u32(bytes, static_cast<std::uint32_t>(value.size()));
  bytes->append(value);
}

std::string input_digest(
    std::span<const platt_windowed::RealDisk106> samples,
    std::span<const Candidate> candidates,
    std::span<const SparseRefinement> refinements) {
  sparkinterval::detail::Sha256 digest;
  digest.update(kInputHashDomain, sizeof(kInputHashDomain) - 1U);
  std::string frame;
  frame.reserve(samples.size() * 24U + candidates.size() * 16U +
                refinements.size() * 96U + 64U);
  append_u32(&frame, static_cast<std::uint32_t>(samples.size()));
  for (const auto& sample : samples) {
    append_u64(&frame, std::bit_cast<std::uint64_t>(sample.center.hi));
    append_u64(&frame, std::bit_cast<std::uint64_t>(sample.center.lo));
    append_u64(&frame, std::bit_cast<std::uint64_t>(sample.radius));
  }
  append_u32(&frame, static_cast<std::uint32_t>(candidates.size()));
  for (const Candidate& candidate : candidates) {
    append_u32(&frame, static_cast<std::uint32_t>(candidate.stream));
    append_i32(&frame, candidate.left_sample);
    append_i32(&frame, candidate.right_sample);
    append_u32(&frame, candidate.source_positive ? 1U : 0U);
  }
  append_u32(&frame, static_cast<std::uint32_t>(refinements.size()));
  for (const SparseRefinement& refinement : refinements) {
    append_i32(&frame, refinement.sample_offset);
    append_string(&frame, refinement.lower_arf_dump);
    append_string(&frame, refinement.upper_arf_dump);
  }
  digest.update(frame.data(), frame.size());
  return sparkinterval::lowercase_hex(digest.finish());
}

std::string json_escape(std::string_view value) {
  std::ostringstream output;
  for (const unsigned char character : value) {
    switch (character) {
      case '"':
        output << "\\\"";
        break;
      case '\\':
        output << "\\\\";
        break;
      case '\b':
        output << "\\b";
        break;
      case '\f':
        output << "\\f";
        break;
      case '\n':
        output << "\\n";
        break;
      case '\r':
        output << "\\r";
        break;
      case '\t':
        output << "\\t";
        break;
      default:
        if (character < 0x20U) {
          constexpr char hex[] = "0123456789abcdef";
          output << "\\u00" << hex[character >> 4U]
                 << hex[character & 0xfU];
        } else {
          output << static_cast<char>(character);
        }
    }
  }
  return output.str();
}

std::string rational_json(const CanonicalRational& value) {
  return "{\"denominator\":" + value.denominator +
         ",\"numerator\":" + value.numerator + "}";
}

std::string interval_json(const CanonicalInterval& value) {
  return "{\"hi\":" + rational_json(value.upper) +
         ",\"lo\":" + rational_json(value.lower) + "}";
}

std::string one_resolution_json(const Resolution& value) {
  std::ostringstream output;
  output << "{\"lower_offset\":" << rational_json(value.lower_offset)
         << ",\"lower_value\":" << interval_json(value.lower_value)
         << ",\"midpoint_offset\":"
         << rational_json(value.midpoint_offset)
         << ",\"midpoint_value\":" << interval_json(value.midpoint_value)
         << ",\"outer_left_sample\":" << value.outer_left_sample
         << ",\"outer_right_sample\":" << value.outer_right_sample
         << ",\"stream\":\"" << stream_name(value.stream) << "\""
         << ",\"upper_offset\":" << rational_json(value.upper_offset)
         << ",\"upper_value\":" << interval_json(value.upper_value) << '}';
  return output.str();
}

std::string resolutions_json(const std::vector<Resolution>& resolutions) {
  std::ostringstream output;
  output << '[';
  for (std::size_t index = 0; index < resolutions.size(); ++index) {
    if (index != 0U) output << ',';
    output << one_resolution_json(resolutions[index]);
  }
  output << ']';
  return output.str();
}

std::string endpoint_audit_json(const PrecisionEndpointAudit& value) {
  return "{\"base_interval\":" + interval_json(value.base_interval) +
         ",\"replay_interval\":" + interval_json(value.replay_interval) +
         ",\"retained_hull\":" + interval_json(value.retained_hull) + "}";
}

std::string one_precision_audit_json(const PrecisionReplayAudit& value) {
  std::ostringstream output;
  output << "{\"base_precision_bits\":" << value.base_precision_bits
         << ",\"lower\":" << endpoint_audit_json(value.lower)
         << ",\"midpoint\":" << endpoint_audit_json(value.midpoint)
         << ",\"outer_left_sample\":" << value.outer_left_sample
         << ",\"outer_right_sample\":" << value.outer_right_sample
         << ",\"replay_precision_bits\":" << value.replay_precision_bits
         << ",\"stream\":\"" << stream_name(value.stream) << "\""
         << ",\"upper\":" << endpoint_audit_json(value.upper) << '}';
  return output.str();
}

std::string precision_audit_json(
    const std::vector<PrecisionReplayAudit>& audits) {
  std::ostringstream output;
  output << '[';
  for (std::size_t index = 0U; index < audits.size(); ++index) {
    if (index != 0U) output << ',';
    output << one_precision_audit_json(audits[index]);
  }
  output << ']';
  return output.str();
}

std::string trace_json(const Report& report, const Options& options) {
  // Keys at every object level are emitted in lexicographic order, matching
  // Python json.dumps(..., sort_keys=True, separators=(",", ":")).
  std::ostringstream output;
  output << "{\"accepted\":" << (report.accepted ? "true" : "false")
         << ",\"ambiguous_input_disks\":"
         << report.ambiguous_input_disks
         << ",\"candidate_count\":" << report.candidate_count
         << ",\"error\":\"" << json_escape(report.error) << "\""
         << ",\"failure_flags\":" << report.failure_flags
         << ",\"input_sha256\":\"" << report.input_sha256 << "\""
         << ",\"interpolation_evaluations\":"
         << report.interpolation_evaluations
         << ",\"interpolation_patch_sha256\":\""
         << kInterpolationPatchSha256 << "\""
         << ",\"maximum_depth\":" << options.maximum_depth
         << ",\"precision_bits\":" << options.precision_bits
         << (options.retain_precision_hull_audit
                 ? ",\"precision_replay_audit\":" +
                       precision_audit_json(
                           report.precision_replay_audit)
                 : "")
         << ",\"refinements_applied\":" << report.refinements_applied
         << ",\"replay_accepted\":"
         << (report.replay_accepted ? "true" : "false")
         << ",\"required_sample_count\":" << kRequiredCount
         << ",\"resolution_sha256\":\"" << report.resolution_sha256
         << "\",\"schema\":\"sparkinterval.tg.platt-pt21-stationary-trace."
         << (options.retain_precision_hull_audit ? "v2\"" : "v1\"")
         << ",\"semantic_status\":{"
            "\"analytic_turing_realization_proved\":false,"
            "\"flint_to_mathlib_realization_proved\":false,"
            "\"hardy_z_endpoint_realization_proved\":false}"
         << ",\"stationary_resolutions\":"
         << report.stationary_resolutions_json
         << ",\"upstream_commit\":\"" << kUpstreamCommit << "\"}";
  return output.str();
}

struct ExactSamples {
  explicit ExactSamples(std::size_t count)
      : lower(count), upper(count), arb(count) {}
  ArfVector lower;
  ArfVector upper;
  ArbVector arb;
};

bool arf_dump_load_canonical(std::string_view encoded, arf_t output) {
  if (encoded.empty() || encoded.size() > kMaximumArfDumpBytes ||
      encoded.find('\0') != std::string_view::npos) {
    return false;
  }
  const std::string owned(encoded);
  if (arf_load_str(output, owned.c_str()) != 0 || !arf_is_finite(output)) {
    return false;
  }
  if (dump_arf(output) != owned ||
      (!arf_is_zero(output) &&
       (!fmpz_fits_si(ARF_EXPREF(output)) ||
        fmpz_cmp_si(ARF_EXPREF(output),
                    kMaximumArfExponentMagnitude) > 0 ||
        fmpz_cmp_si(ARF_EXPREF(output),
                    -kMaximumArfExponentMagnitude) < 0 ||
        arf_bits(output) > static_cast<slong>(kMaximumArfDumpBytes * 4U)))) {
    return false;
  }
  return true;
}

void prepare_samples(
    std::span<const platt_windowed::RealDisk106> samples,
    std::span<const SparseRefinement> refinements,
    const Options& options, ExactSamples* exact,
    std::uint32_t* ambiguous_output) {
  std::uint32_t ambiguous = 0U;
  for (std::size_t index = 0; index < samples.size(); ++index) {
    exact_disk_bounds(samples[index], exact->lower[index], exact->upper[index]);
    if (exact_sign(exact->lower[index], exact->upper[index]) == 0) {
      ++ambiguous;
    }
  }
  *ambiguous_output = ambiguous;

  std::int32_t previous_offset = std::numeric_limits<std::int32_t>::min();
  for (const SparseRefinement& refinement : refinements) {
    if (refinement.sample_offset <= previous_offset) {
      reject(kFailureRefinementRange,
             "sparse refinements are duplicate or not increasing");
    }
    previous_offset = refinement.sample_offset;
    if (refinement.sample_offset < kRequiredLower ||
        refinement.sample_offset > kRequiredUpper) {
      reject(kFailureRefinementRange,
             "sparse refinement offset leaves the required region");
    }
    const std::size_t index = sample_index(refinement.sample_offset);
    if (exact_sign(exact->lower[index], exact->upper[index]) != 0) {
      reject(kFailureRefinementRange,
             "sparse refinement targets an already strict DD disk");
    }
    ArfValue refined_lower;
    ArfValue refined_upper;
    if (!arf_dump_load_canonical(refinement.lower_arf_dump,
                                 refined_lower.get()) ||
        !arf_dump_load_canonical(refinement.upper_arf_dump,
                                 refined_upper.get()) ||
        arf_cmp(refined_lower.get(), refined_upper.get()) > 0) {
      reject(kFailureRefinementEncoding,
             "sparse refinement is not one canonical finite interval");
    }
    if (arf_cmp(refined_lower.get(), exact->lower[index]) < 0 ||
        arf_cmp(refined_upper.get(), exact->upper[index]) > 0) {
      reject(kFailureRefinementNotSubset,
             "sparse refinement is not a subset of its DD disk");
    }
    if (exact_sign(refined_lower.get(), refined_upper.get()) == 0) {
      reject(kFailureRefinementNotStrict,
             "sparse refinement does not establish a strict sign");
    }
    arf_set(exact->lower[index], refined_lower.get());
    arf_set(exact->upper[index], refined_upper.get());
  }

  for (std::size_t index = 0; index < samples.size(); ++index) {
    if (exact_sign(exact->lower[index], exact->upper[index]) == 0) {
      reject(kFailureUnrefinedAmbiguousDisk,
             "at least one DD lattice disk lacks a strict refinement");
    }
    arb_set_interval_arf(exact->arb[index], exact->lower[index],
                         exact->upper[index],
                         static_cast<slong>(options.precision_bits));
  }
}

std::vector<Candidate> generate_candidates(const ExactSamples& samples,
                                           const Options& options) {
  std::vector<Candidate> result;
  result.reserve(256U);
  for (std::uint32_t stream_value = 0U; stream_value < 3U; ++stream_value) {
    const StreamKind stream = static_cast<StreamKind>(stream_value);
    const auto [lower, upper] = stream_range(stream);
    for (std::int32_t left = lower; left <= upper - 2; ++left) {
      const std::size_t left_index = sample_index(left);
      const std::size_t middle_index = sample_index(left + 1);
      const std::size_t right_index = sample_index(left + 2);
      const int sign = exact_sign(samples.lower[middle_index],
                                  samples.upper[middle_index]);
      bool stationary = false;
      if (sign > 0) {
        stationary = exact_strict_gt(samples.lower[left_index],
                                     samples.upper[middle_index]) &&
                     exact_strict_gt(samples.lower[right_index],
                                     samples.upper[middle_index]);
      } else if (sign < 0) {
        stationary = exact_strict_gt(samples.lower[middle_index],
                                     samples.upper[left_index]) &&
                     exact_strict_gt(samples.lower[middle_index],
                                     samples.upper[right_index]);
      }
      if (stationary) {
        if (result.size() >= options.maximum_candidates) {
          reject(kFailureCandidateCapacity,
                 "source stationary candidate count exceeds capacity");
        }
        result.push_back({stream, left, left + 2, sign > 0});
      }
    }
  }
  return result;
}

bool same_candidate(const Candidate& left, const Candidate& right) {
  return left.stream == right.stream &&
         left.left_sample == right.left_sample &&
         left.right_sample == right.right_sample &&
         left.source_positive == right.source_positive;
}

void check_candidates(std::span<const Candidate> supplied,
                      const std::vector<Candidate>& generated) {
  if (supplied.size() != generated.size()) {
    reject(kFailureCandidateList,
           "supplied stationary candidate list is incomplete or has extras");
  }
  for (std::size_t index = 0; index < supplied.size(); ++index) {
    if (!same_candidate(supplied[index], generated[index])) {
      reject(kFailureCandidateList,
             "supplied stationary candidate list differs from source stat_pt");
    }
  }
}

enum class Direction { kUp, kDown, kUnknown };

Direction direction(arb_srcptr left, arb_srcptr right) {
  if (arb_gt(left, right)) return Direction::kDown;
  if (arb_lt(left, right)) return Direction::kUp;
  return Direction::kUnknown;
}

int strict_sign(arb_srcptr value) {
  if (arb_is_positive(value)) return 1;
  if (arb_is_negative(value)) return -1;
  return 0;
}

void set_fmpq_si(fmpq_t value, std::int32_t integer) {
  fmpq_set_si(value, static_cast<slong>(integer), 1U);
}

void midpoint(fmpq_t output, const fmpq* left, const fmpq* right) {
  fmpq_add(output, left, right);
  fmpq_div_2exp(output, output, 1U);
}

bool is_integer(const fmpq* value) {
  return fmpz_is_one(fmpq_denref(value));
}

std::int32_t floor_i32(const fmpq* value) {
  fmpz_t quotient;
  fmpz_init(quotient);
  fmpz_fdiv_q(quotient, fmpq_numref(value), fmpq_denref(value));
  if (!fmpz_fits_si(quotient)) {
    fmpz_clear(quotient);
    reject(kFailureInterpolationStencil, "query floor does not fit slong");
  }
  const slong result = fmpz_get_si(quotient);
  fmpz_clear(quotient);
  if (result < std::numeric_limits<std::int32_t>::min() ||
      result > std::numeric_limits<std::int32_t>::max()) {
    reject(kFailureInterpolationStencil, "query floor does not fit int32");
  }
  return static_cast<std::int32_t>(result);
}

class SourceInterpolator {
 public:
  SourceInterpolator(const ExactSamples& samples, slong precision)
      : samples_(samples), precision_(precision) {
    arb_set_si(spacing_.get(), 21);
    arb_div_ui(spacing_.get(), spacing_.get(), 512U, precision_);
    arb_neg(negative_spacing_.get(), spacing_.get());
    arb_set_si(gaussian_h_.get(), 13);
    arb_div_ui(gaussian_h_.get(), gaussian_h_.get(), 64U, precision_);
    arb_const_pi(pi_.get(), precision_);
    arb_div(two_pi_b_.get(), pi_.get(), spacing_.get(), precision_);

    fmpq_t error;
    fmpq_init(error);
    fmpz_set_ui(fmpq_numref(error), 245U);
    fmpz_ui_pow_ui(fmpq_denref(error), 10U, 42U);
    fmpq_canonicalise(error);
    arb_set_fmpq(interpolation_error_.get(), error, precision_);
    fmpq_clear(error);
  }

  void evaluate(arb_t output, const fmpq* query) const {
    if (is_integer(query)) {
      reject(kFailureInterpolationStencil,
             "adaptive interpolation queried a cardinal lattice point");
    }
    const std::int32_t floor = floor_i32(query);
    const std::int32_t nearest_right = floor + 1;
    if (nearest_right + static_cast<std::int32_t>(kSourcePointsPerSide) - 1 >
            kRequiredUpper ||
        floor - static_cast<std::int32_t>(kSourcePointsPerSide) + 1 <
            kRequiredLower) {
      reject(kFailureInterpolationStencil,
             "140-row interpolation stencil is incomplete");
    }

    ArbValue query_arb;
    arb_set_fmpq(query_arb.get(), query, precision_);
    arb_zero(output);
    accumulate_side(output, query_arb.get(), nearest_right, 1);
    accumulate_side(output, query_arb.get(), floor, -1);
    // The exact rational 245/10^42 jointly budgets Appendix C.1 and corrected
    // C.3.  arb_add_error uses a magnitude enclosing that positive rational.
    arb_add_error(output, interpolation_error_.get());
  }

 private:
  void accumulate_side(arb_t output, arb_srcptr query,
                       std::int32_t first, std::int32_t step) const {
    ArbValue distance;
    ArbValue gaussian;
    ArbValue argument;
    ArbValue sine;
    ArbValue cosine;
    ArbValue sinc;
    ArbValue product;
    for (std::uint32_t slot = 0; slot < kSourcePointsPerSide; ++slot) {
      const std::int32_t index =
          first + step * static_cast<std::int32_t>(slot);
      arb_sub_si(distance.get(), query, static_cast<slong>(index), precision_);
      arb_mul(distance.get(), distance.get(), negative_spacing_.get(),
              precision_);

      // inter_gaussian: exp(-distance^2/(2H^2)).
      arb_div(gaussian.get(), distance.get(), gaussian_h_.get(), precision_);
      arb_mul(gaussian.get(), gaussian.get(), gaussian.get(), precision_);
      arb_mul_2exp_si(gaussian.get(), gaussian.get(), -1);
      arb_neg(gaussian.get(), gaussian.get());
      arb_exp(gaussian.get(), gaussian.get(), precision_);

      arb_mul(argument.get(), distance.get(), two_pi_b_.get(), precision_);
      if (slot == 0U) {
        arb_sin_cos(sine.get(), cosine.get(), argument.get(), precision_);
      } else {
        // Pinned inter_sinc_cos reuses sin/cos after an integral lattice step.
        arb_neg(sine.get(), sine.get());
        arb_neg(cosine.get(), cosine.get());
      }
      arb_div(sinc.get(), sine.get(), argument.get(), precision_);

      arb_mul(product.get(), samples_.arb[sample_index(index)],
              gaussian.get(), precision_);
      arb_mul(product.get(), product.get(), sinc.get(), precision_);
      arb_add(output, output, product.get(), precision_);
    }
  }

  const ExactSamples& samples_;
  slong precision_;
  ArbValue spacing_;
  ArbValue negative_spacing_;
  ArbValue gaussian_h_;
  ArbValue pi_;
  ArbValue two_pi_b_;
  ArbValue interpolation_error_;
};

struct InternalResolution {
  FmpqValue lower;
  FmpqValue middle;
  FmpqValue upper;
  ArbValue lower_value;
  ArbValue middle_value;
  ArbValue upper_value;
  std::uint32_t iterations = 0U;
  std::uint32_t evaluations = 0U;
};

void set_point(fmpq_t target_coordinate, arb_t target_value,
               const fmpq* source_coordinate, arb_srcptr source_value) {
  fmpq_set(target_coordinate, source_coordinate);
  arb_set(target_value, source_value);
}

InternalResolution resolve_one(const Candidate& candidate,
                               const ExactSamples& samples,
                               const SourceInterpolator& interpolator,
                               const Options& options,
                               std::uint64_t* evaluation_counter = nullptr) {
  InternalResolution result;
  FmpqValue tl;
  FmpqValue tm;
  FmpqValue tr;
  ArbValue ftl;
  ArbValue ftm;
  ArbValue ftr;
  FmpqValue qleft;
  FmpqValue qright;
  ArbValue fqleft;
  ArbValue fqright;

  set_fmpq_si(tl.get(), candidate.left_sample);
  set_fmpq_si(tm.get(), candidate.left_sample + 1);
  set_fmpq_si(tr.get(), candidate.left_sample + 2);
  arb_set(ftl.get(), samples.arb[sample_index(candidate.left_sample)]);
  arb_set(ftm.get(), samples.arb[sample_index(candidate.left_sample + 1)]);
  arb_set(ftr.get(), samples.arb[sample_index(candidate.left_sample + 2)]);
  const int source_sign = candidate.source_positive ? 1 : -1;

  for (std::uint32_t iteration = 1U; iteration <= options.maximum_depth;
       ++iteration) {
    midpoint(qleft.get(), tl.get(), tm.get());
    interpolator.evaluate(fqleft.get(), qleft.get());
    ++result.evaluations;
    if (evaluation_counter != nullptr) ++*evaluation_counter;
    const int left_sign = strict_sign(fqleft.get());
    if (left_sign == 0) {
      reject(kFailureInterpolationSign,
             "left dyadic interpolation interval contains zero");
    }
    if (left_sign != source_sign) {
      set_point(result.lower.get(), result.lower_value.get(), tl.get(),
                ftl.get());
      set_point(result.middle.get(), result.middle_value.get(), qleft.get(),
                fqleft.get());
      set_point(result.upper.get(), result.upper_value.get(), tm.get(),
                ftm.get());
      result.iterations = iteration;
      return result;
    }

    const Direction dir1 = direction(ftl.get(), fqleft.get());
    const Direction dir2 = direction(fqleft.get(), ftm.get());
    if (dir1 == Direction::kUnknown || dir2 == Direction::kUnknown) {
      reject(kFailureDirection,
             "left dyadic source direction is not strict");
    }
    const bool left_extremum =
        (source_sign > 0 && dir1 == Direction::kDown &&
         dir2 == Direction::kUp) ||
        (source_sign < 0 && dir1 == Direction::kUp &&
         dir2 == Direction::kDown);
    if (left_extremum) {
      set_point(tr.get(), ftr.get(), tm.get(), ftm.get());
      set_point(tm.get(), ftm.get(), qleft.get(), fqleft.get());
      continue;
    }

    midpoint(qright.get(), tm.get(), tr.get());
    interpolator.evaluate(fqright.get(), qright.get());
    ++result.evaluations;
    if (evaluation_counter != nullptr) ++*evaluation_counter;
    const int right_sign = strict_sign(fqright.get());
    if (right_sign == 0) {
      reject(kFailureInterpolationSign,
             "right dyadic interpolation interval contains zero");
    }
    if (right_sign != source_sign) {
      set_point(result.lower.get(), result.lower_value.get(), tm.get(),
                ftm.get());
      set_point(result.middle.get(), result.middle_value.get(), qright.get(),
                fqright.get());
      set_point(result.upper.get(), result.upper_value.get(), tr.get(),
                ftr.get());
      result.iterations = iteration;
      return result;
    }

    const Direction dir3 = direction(ftm.get(), fqright.get());
    const Direction dir4 = direction(fqright.get(), ftr.get());
    if (dir3 == Direction::kUnknown || dir4 == Direction::kUnknown) {
      reject(kFailureDirection,
             "right dyadic source direction is not strict");
    }
    const bool middle_extremum =
        (source_sign > 0 && dir2 == Direction::kDown &&
         dir3 == Direction::kUp) ||
        (source_sign < 0 && dir2 == Direction::kUp &&
         dir3 == Direction::kDown);
    if (middle_extremum) {
      set_point(tl.get(), ftl.get(), qleft.get(), fqleft.get());
      set_point(tr.get(), ftr.get(), qright.get(), fqright.get());
      continue;
    }
    const bool right_extremum =
        (source_sign > 0 && dir3 == Direction::kDown &&
         dir4 == Direction::kUp) ||
        (source_sign < 0 && dir3 == Direction::kUp &&
         dir4 == Direction::kDown);
    if (right_extremum) {
      set_point(tl.get(), ftl.get(), tm.get(), ftm.get());
      set_point(tm.get(), ftm.get(), qright.get(), fqright.get());
      continue;
    }
    reject(kFailureDirection,
           "pinned stationary resolver has no strict refinement branch");
  }
  reject(kFailureDepth, "adaptive dyadic resolver exhausted its depth cap");
}

Resolution external_resolution(const Candidate& candidate,
                               const InternalResolution& internal,
                               slong precision) {
  return {
      candidate.stream,
      candidate.left_sample,
      candidate.right_sample,
      canonical_rational(internal.lower.get()),
      canonical_rational(internal.middle.get()),
      canonical_rational(internal.upper.get()),
      canonical_interval(internal.lower_value.get(), precision),
      canonical_interval(internal.middle_value.get(), precision),
      canonical_interval(internal.upper_value.get(), precision),
      internal.iterations,
      internal.evaluations,
  };
}

bool same_rational(const CanonicalRational& left,
                   const CanonicalRational& right) {
  return left.numerator == right.numerator &&
         left.denominator == right.denominator;
}

bool same_interval(const CanonicalInterval& left,
                   const CanonicalInterval& right) {
  return same_rational(left.lower, right.lower) &&
         same_rational(left.upper, right.upper);
}

bool same_resolution(const Resolution& left, const Resolution& right) {
  return left.stream == right.stream &&
         left.outer_left_sample == right.outer_left_sample &&
         left.outer_right_sample == right.outer_right_sample &&
         same_rational(left.lower_offset, right.lower_offset) &&
         same_rational(left.midpoint_offset, right.midpoint_offset) &&
         same_rational(left.upper_offset, right.upper_offset) &&
         same_interval(left.lower_value, right.lower_value) &&
         same_interval(left.midpoint_value, right.midpoint_value) &&
         same_interval(left.upper_value, right.upper_value) &&
         left.iterations == right.iterations &&
         left.interpolation_evaluations == right.interpolation_evaluations;
}

void value_at(arb_t output, const fmpq* coordinate,
              const ExactSamples& samples,
              const SourceInterpolator& interpolator) {
  if (is_integer(coordinate)) {
    const slong index = fmpz_get_si(fmpq_numref(coordinate));
    if (index < kRequiredLower || index > kRequiredUpper) {
      reject(kFailureReplay, "replay lattice coordinate is out of range");
    }
    arb_set(output, samples.arb[sample_index(static_cast<std::int32_t>(index))]);
  } else {
    interpolator.evaluate(output, coordinate);
  }
}

void require_recorded_contains(const CanonicalInterval& recorded,
                               arb_srcptr fresh, slong precision) {
  FmpqValue recorded_lower;
  FmpqValue recorded_upper;
  load_rational(recorded_lower.get(), recorded.lower);
  load_rational(recorded_upper.get(), recorded.upper);
  ArfValue fresh_lower;
  ArfValue fresh_upper;
  arb_get_interval_arf(fresh_lower.get(), fresh_upper.get(), fresh, precision);
  FmpqValue fresh_lower_q;
  FmpqValue fresh_upper_q;
  arf_get_fmpq(fresh_lower_q.get(), fresh_lower.get());
  arf_get_fmpq(fresh_upper_q.get(), fresh_upper.get());
  if (fmpq_cmp(recorded_lower.get(), fresh_lower_q.get()) > 0 ||
      fmpq_cmp(fresh_upper_q.get(), recorded_upper.get()) > 0) {
    reject(kFailureReplay,
           "higher-precision replay is not contained by recorded interval");
  }
}

PrecisionEndpointAudit widen_recorded_to_include(
    CanonicalInterval* recorded, arb_srcptr fresh, slong precision) {
  const CanonicalInterval base_interval = *recorded;
  FmpqValue recorded_lower;
  FmpqValue recorded_upper;
  load_rational(recorded_lower.get(), recorded->lower);
  load_rational(recorded_upper.get(), recorded->upper);
  const int original_sign =
      fmpq_sgn(recorded_lower.get()) > 0
          ? 1
          : (fmpq_sgn(recorded_upper.get()) < 0 ? -1 : 0);
  if (original_sign == 0) {
    reject(kFailureReplay,
           "recorded stationary interval is not strict before replay");
  }

  ArfValue fresh_lower;
  ArfValue fresh_upper;
  arb_get_interval_arf(fresh_lower.get(), fresh_upper.get(), fresh, precision);
  const CanonicalInterval replay_interval{
      canonical_rational(fresh_lower.get()),
      canonical_rational(fresh_upper.get())};
  FmpqValue fresh_lower_q;
  FmpqValue fresh_upper_q;
  arf_get_fmpq(fresh_lower_q.get(), fresh_lower.get());
  arf_get_fmpq(fresh_upper_q.get(), fresh_upper.get());
  if (fmpq_cmp(fresh_lower_q.get(), recorded_lower.get()) < 0) {
    fmpq_set(recorded_lower.get(), fresh_lower_q.get());
  }
  if (fmpq_cmp(fresh_upper_q.get(), recorded_upper.get()) > 0) {
    fmpq_set(recorded_upper.get(), fresh_upper_q.get());
  }
  const int widened_sign =
      fmpq_sgn(recorded_lower.get()) > 0
          ? 1
          : (fmpq_sgn(recorded_upper.get()) < 0 ? -1 : 0);
  if (widened_sign != original_sign) {
    reject(kFailureReplay,
           "higher-precision replay destroys a retained strict sign");
  }
  recorded->lower = canonical_rational(recorded_lower.get());
  recorded->upper = canonical_rational(recorded_upper.get());
  return {
      .base_interval = base_interval,
      .replay_interval = replay_interval,
      .retained_hull = *recorded,
  };
}

PrecisionReplayAudit widen_with_higher_precision_replay(
    Resolution* resolution, const ExactSamples& samples,
    const SourceInterpolator& interpolator, slong replay_precision,
    const Options& options) {
  const std::array<const CanonicalRational*, 3> coordinate_records = {
      &resolution->lower_offset, &resolution->midpoint_offset,
      &resolution->upper_offset};
  const std::array<CanonicalInterval*, 3> interval_records = {
      &resolution->lower_value, &resolution->midpoint_value,
      &resolution->upper_value};
  std::array<PrecisionEndpointAudit, 3> endpoint_audits;
  for (std::size_t index = 0; index < coordinate_records.size(); ++index) {
    FmpqValue coordinate;
    load_rational(coordinate.get(), *coordinate_records[index]);
    ArbValue fresh;
    value_at(fresh.get(), coordinate.get(), samples, interpolator);
    // Arb computations at different precisions are each rigorous, but
    // interval dependency does not imply that the higher-precision result is
    // nested inside the lower-precision result.  Retain their exact rational
    // hull, then independently recompute the higher-precision result below.
    endpoint_audits[index] = widen_recorded_to_include(
        interval_records[index], fresh.get(), replay_precision);
  }
  return {
      .stream = resolution->stream,
      .outer_left_sample = resolution->outer_left_sample,
      .outer_right_sample = resolution->outer_right_sample,
      .base_precision_bits = options.precision_bits,
      .replay_precision_bits =
          options.precision_bits + options.replay_extra_precision_bits,
      .lower = endpoint_audits[0],
      .midpoint = endpoint_audits[1],
      .upper = endpoint_audits[2],
  };
}

void higher_precision_replay(const Resolution& resolution,
                             const ExactSamples& samples,
                             const SourceInterpolator& interpolator,
                             slong replay_precision) {
  const std::array<const CanonicalRational*, 3> coordinate_records = {
      &resolution.lower_offset, &resolution.midpoint_offset,
      &resolution.upper_offset};
  const std::array<const CanonicalInterval*, 3> interval_records = {
      &resolution.lower_value, &resolution.midpoint_value,
      &resolution.upper_value};
  for (std::size_t index = 0; index < coordinate_records.size(); ++index) {
    FmpqValue coordinate;
    load_rational(coordinate.get(), *coordinate_records[index]);
    ArbValue fresh;
    value_at(fresh.get(), coordinate.get(), samples, interpolator);
    require_recorded_contains(*interval_records[index], fresh.get(),
                              replay_precision);
  }
}

void validate_options(const Options& options,
                      std::span<const Candidate> candidates,
                      std::span<const SparseRefinement> refinements) {
  if (options.precision_bits != kSourcePrecisionBits ||
      options.maximum_depth == 0U || options.maximum_depth > 96U ||
      options.maximum_candidates == 0U ||
      options.maximum_candidates > kSourceTraceResolutionLimit ||
      options.maximum_refinements > kSourceTraceResolutionLimit ||
      options.replay_extra_precision_bits < 32U ||
      options.replay_extra_precision_bits > 512U ||
      options.maximum_trace_bytes < 4096U ||
      options.maximum_trace_bytes > kSourceTraceMaximumBytes ||
      (options.retain_precision_hull_audit &&
       options.replay_extra_precision_bits != 64U) ||
      candidates.size() > options.maximum_candidates ||
      refinements.size() > options.maximum_refinements) {
    reject(kFailureInputGeometry, "stationary resolver options exceed bounds");
  }
  for (const SparseRefinement& refinement : refinements) {
    if (refinement.lower_arf_dump.empty() ||
        refinement.upper_arf_dump.empty() ||
        refinement.lower_arf_dump.size() > kMaximumArfDumpBytes ||
        refinement.upper_arf_dump.size() > kMaximumArfDumpBytes) {
      reject(kFailureRefinementEncoding,
             "sparse refinement encoding exceeds its byte cap");
    }
  }
}

void finish_report_json(Report* report, const Options& options) {
  report->stationary_resolutions_json = resolutions_json(report->resolutions);
  sparkinterval::detail::Sha256 digest;
  digest.update(kResolutionHashDomain, sizeof(kResolutionHashDomain) - 1U);
  digest.update(report->stationary_resolutions_json.data(),
                report->stationary_resolutions_json.size());
  report->resolution_sha256 =
      sparkinterval::lowercase_hex(digest.finish());
  report->canonical_trace_json = trace_json(*report, options);
  if (report->canonical_trace_json.size() + 1U > options.maximum_trace_bytes) {
    report->accepted = false;
    report->replay_accepted = false;
    report->failure_flags |= kFailureCandidateCapacity;
    report->error = "canonical stationary trace exceeds its byte cap";
    report->resolutions.clear();
    report->precision_replay_audit.clear();
    report->stationary_resolutions_json = "[]";
    sparkinterval::detail::Sha256 empty_digest;
    empty_digest.update(kResolutionHashDomain,
                        sizeof(kResolutionHashDomain) - 1U);
    empty_digest.update("[]", 2U);
    report->resolution_sha256 =
        sparkinterval::lowercase_hex(empty_digest.finish());
    report->canonical_trace_json = trace_json(*report, options);
  }
  report->canonical_trace_json.push_back('\n');
}

}  // namespace

const char* stream_name(StreamKind stream) {
  switch (stream) {
    case StreamKind::kLeftFlank:
      return "left_flank";
    case StreamKind::kMain:
      return "main";
    case StreamKind::kRightFlank:
      return "right_flank";
  }
  return "invalid";
}

Report resolve_block(
    std::span<const platt_windowed::RealDisk106> samples,
    std::span<const Candidate> candidates,
    std::span<const SparseRefinement> refinements,
    Options options) {
  Report report;
  report.input_sha256.assign(64U, '0');
  report.resolution_sha256.assign(64U, '0');
  try {
    if (samples.size() != kRequiredCount) {
      reject(kFailureInputGeometry,
             "stationary resolver requires exactly 25,741 samples");
    }
    validate_options(options, candidates, refinements);
    report.input_sha256 = input_digest(samples, candidates, refinements);
    if (options.require_flint_3_6_0 &&
        (std::strcmp(FLINT_VERSION, "3.6.0") != 0 ||
         std::strcmp(flint_version, "3.6.0") != 0 ||
         __FLINT_RELEASE != 30600)) {
      reject(kFailureFlintIdentity,
             "stationary resolver requires reviewed FLINT 3.6.0");
    }

    ExactSamples exact(samples.size());
    prepare_samples(samples, refinements, options, &exact,
                    &report.ambiguous_input_disks);
    report.refinements_applied = static_cast<std::uint32_t>(refinements.size());
    const std::vector<Candidate> generated =
        generate_candidates(exact, options);
    report.candidate_count = static_cast<std::uint32_t>(generated.size());
    check_candidates(candidates, generated);

    SourceInterpolator interpolator(exact,
                                    static_cast<slong>(options.precision_bits));
    const slong replay_precision =
        static_cast<slong>(options.precision_bits) +
        options.replay_extra_precision_bits;
    // Construct the 192-bit constants and interpolation budget only once for
    // a block that has stationary candidates.  The hull evaluation and the
    // containment replay below still invoke evaluate independently.
    std::unique_ptr<SourceInterpolator> replay_interpolator;
    if (!generated.empty()) {
      replay_interpolator =
          std::make_unique<SourceInterpolator>(exact, replay_precision);
    }
    report.resolutions.reserve(generated.size());
    for (const Candidate& candidate : generated) {
      const InternalResolution internal =
          resolve_one(candidate, exact, interpolator, options,
                      &report.interpolation_evaluations);
      report.resolutions.push_back(external_resolution(
          candidate, internal, static_cast<slong>(options.precision_bits)));
    }

    // Deterministic replay first reruns the complete source control path, then
    // independently evaluates every retained endpoint with extra precision.
    for (std::size_t index = 0; index < generated.size(); ++index) {
      const InternalResolution replay_internal =
          resolve_one(generated[index], exact, interpolator, options);
      const Resolution replay = external_resolution(
          generated[index], replay_internal,
          static_cast<slong>(options.precision_bits));
      if (!same_resolution(report.resolutions[index], replay)) {
        reject(kFailureReplay,
               "deterministic stationary control replay differs");
      }
      if (options.retain_precision_hull_audit) {
        report.precision_replay_audit.push_back(
            widen_with_higher_precision_replay(
                &report.resolutions[index], exact, *replay_interpolator,
                replay_precision, options));
      }
      higher_precision_replay(report.resolutions[index], exact,
                              *replay_interpolator, replay_precision);
    }
    report.replay_accepted = true;
    report.accepted = true;
  } catch (const ResolveFailure& failure) {
    report.failure_flags |= failure.flag();
    report.error = failure.what();
    report.accepted = false;
    report.replay_accepted = false;
    report.resolutions.clear();
    report.precision_replay_audit.clear();
  } catch (const std::exception& error) {
    report.failure_flags |= kFailureInternal;
    report.error = error.what();
    report.accepted = false;
    report.replay_accepted = false;
    report.resolutions.clear();
    report.precision_replay_audit.clear();
  } catch (...) {
    report.failure_flags |= kFailureInternal;
    report.error = "unknown stationary resolver failure";
    report.accepted = false;
    report.replay_accepted = false;
    report.resolutions.clear();
    report.precision_replay_audit.clear();
  }
  try {
    finish_report_json(&report, options);
  } catch (const std::exception& error) {
    report.accepted = false;
    report.replay_accepted = false;
    report.failure_flags |= kFailureInternal;
    report.error = error.what();
    report.resolutions.clear();
    report.precision_replay_audit.clear();
    report.stationary_resolutions_json = "[]";
    report.resolution_sha256.assign(64U, '0');
    report.canonical_trace_json = trace_json(report, options) + "\n";
  }
  return report;
}

}  // namespace sparkinterval::tg::platt_stationary_resolver

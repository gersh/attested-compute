// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Produce the four rigorous Arb inputs used by each of the two one-sided
// Turing calls in the pinned PT21 windowed zeta computation.
//
// This deliberately does not consume a zero/event stream and does not claim
// the analytic Turing theorem.  It closes the smaller numerical boundary:
// for block j it evaluates the source formulas on exactly
//
//   turing_min: [10^10 + 1008j - 21, 10^10 + 1008j]
//   turing_max: [10^10 + 1008(j+1), 10^10 + 1008(j+1) + 21].
//
// Every emitted endpoint is an exact reduced dyadic rational obtained from an
// outward Arb interval.  A second 256-bit evaluation must be contained in the
// retained 128-bit interval before any output is released.

#include <flint/arb.h>
#include <flint/arf.h>
#include <flint/flint.h>
#include <flint/fmpq.h>
#include <flint/fmpz.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {

constexpr std::uint64_t kSourceLower = 10'000'000'000ULL;
constexpr std::uint64_t kSourceStep = 1'008ULL;
constexpr std::uint64_t kSourceBlockCount = 2'966'443'783ULL;
constexpr std::uint64_t kTuringWidth = 21ULL;
constexpr slong kRetainedPrecision = 128;
constexpr slong kReplayPrecision = 256;

constexpr std::string_view kSchema =
    "sparkinterval.tg.platt-pt21-turing-inputs.v1";
constexpr std::string_view kAlgorithm =
    "pinned-platt-pt21-one-sided-turing-inputs-flint-3.6-v1";
constexpr std::string_view kUpstreamCommit =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";
constexpr std::string_view kTuringSourceSha256 =
    "07305e04e85477749ced09325c9e78388dd55d6107aa526d3becde345a430c27";
constexpr std::string_view kFlintCommit =
    "8d5454b96761fafe4d5a9da76a369a602f500f49";
constexpr std::string_view kInterpolationPatchSha256 =
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3";

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

struct Options {
  std::uint64_t block = 0;
  std::string required_sign_packet_sha256;
  bool have_block = false;
  bool have_packet_sha256 = false;
  std::uint32_t persistent_requests = 0;
};

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
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

std::uint64_t parse_u64(std::string_view value, std::string_view label) {
  if (value.empty()) fail(std::string(label) + " is empty");
  std::uint64_t result = 0;
  const auto parsed =
      std::from_chars(value.data(), value.data() + value.size(), result);
  if (parsed.ec != std::errc() || parsed.ptr != value.data() + value.size()) {
    fail(std::string(label) + " is not an unsigned decimal integer");
  }
  return result;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-platt-pt21-turing-inputs "
             "(--block N --required-sign-packet-sha256 HEX | "
             "--persistent-requests N)\n";
      std::exit(0);
    }
    if (argument == "--persistent-requests") {
      if (options.persistent_requests != 0 || index + 1 >= argc) {
        fail("--persistent-requests is missing or duplicated");
      }
      const std::uint64_t value =
          parse_u64(argv[++index], "--persistent-requests");
      if (value == 0 || value > 10'000) {
        fail("--persistent-requests is outside 1..10000");
      }
      options.persistent_requests = static_cast<std::uint32_t>(value);
      continue;
    }
    if (argument == "--block") {
      if (options.have_block || index + 1 >= argc) {
        fail("--block is missing or duplicated");
      }
      options.block = parse_u64(argv[++index], "--block");
      options.have_block = true;
      continue;
    }
    if (argument == "--required-sign-packet-sha256") {
      if (options.have_packet_sha256 || index + 1 >= argc) {
        fail("--required-sign-packet-sha256 is missing or duplicated");
      }
      options.required_sign_packet_sha256 = argv[++index];
      options.have_packet_sha256 = true;
      continue;
    }
    fail("unknown option: " + std::string(argument));
  }
  const bool one_shot =
      options.have_block && options.have_packet_sha256 &&
      options.persistent_requests == 0;
  const bool persistent =
      !options.have_block && !options.have_packet_sha256 &&
      options.persistent_requests != 0;
  if (!one_shot && !persistent) {
    fail("select exactly one one-shot or persistent request mode");
  }
  if (one_shot && options.block >= kSourceBlockCount) {
    fail("--block is outside the PT21 source campaign");
  }
  if (one_shot &&
      !is_lower_sha256(options.required_sign_packet_sha256)) {
    fail("--required-sign-packet-sha256 is not lowercase SHA-256 hex");
  }
  return options;
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

std::string artifact_json(const Options& options) {
  const std::uint64_t height_lower =
      kSourceLower + options.block * kSourceStep;
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
      << "{\"algorithm\":\"" << kAlgorithm << "\",\"block\":" << options.block
      << ",\"flint_commit\":\"" << kFlintCommit << "\",\"inputs\":{\"lower\":"
      << side_json("turing_min", lower_a, lower_b, lower)
      << ",\"upper\":" << side_json("turing_max", upper_a, upper_b, upper)
      << "},\"precision_bits\":" << kRetainedPrecision
      << ",\"replay_precision_bits\":" << kReplayPrecision
      << ",\"required_sign_packet_sha256\":\""
      << options.required_sign_packet_sha256 << "\",\"schema\":\"" << kSchema
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
  return output.str();
}

constexpr std::array<unsigned char, 8> kPersistentRequestMagic{
    'P', 'T', '2', '1', 'T', 'R', 'Q', '1'};
constexpr std::array<unsigned char, 8> kPersistentResponseMagic{
    'P', 'T', '2', '1', 'T', 'R', 'S', '1'};
constexpr std::uint32_t kPersistentVersion = 1;
constexpr std::uint32_t kPersistentRequestBytes = 56;
constexpr std::uint32_t kPersistentResponseHeaderBytes = 16;

std::uint32_t load_u32(const unsigned char* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t load_u64(const unsigned char* data) {
  std::uint64_t result = 0;
  for (unsigned int index = 0; index < 8; ++index) {
    result |= static_cast<std::uint64_t>(data[index]) << (8U * index);
  }
  return result;
}

void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0; index < 4; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void read_exact(unsigned char* output, std::size_t size,
                std::string_view label) {
  std::cin.read(reinterpret_cast<char*>(output),
                static_cast<std::streamsize>(size));
  if (std::cin.gcount() != static_cast<std::streamsize>(size)) {
    fail(std::string(label) + " is truncated");
  }
}

void write_exact(const unsigned char* data, std::size_t size,
                 std::string_view label) {
  std::cout.write(reinterpret_cast<const char*>(data),
                  static_cast<std::streamsize>(size));
  if (!std::cout) fail("cannot write " + std::string(label));
}

void require_persistent_eof() {
  char trailing = '\0';
  std::cin.read(&trailing, 1);
  if (std::cin.gcount() != 0) {
    fail("persistent Turing request stream has trailing bytes");
  }
  if (!std::cin.eof()) {
    fail("persistent Turing request stream did not end cleanly");
  }
}

std::string lower_hex(const unsigned char* data, std::size_t size) {
  constexpr char digits[] = "0123456789abcdef";
  std::string result(size * 2, '0');
  for (std::size_t index = 0; index < size; ++index) {
    result[index * 2] = digits[data[index] >> 4U];
    result[index * 2 + 1] = digits[data[index] & 15U];
  }
  return result;
}

Options read_persistent_request() {
  std::array<unsigned char, kPersistentRequestBytes> request{};
  read_exact(request.data(), request.size(), "persistent Turing request");
  if (!std::equal(kPersistentRequestMagic.begin(),
                  kPersistentRequestMagic.end(), request.begin()) ||
      load_u32(request.data() + 8) != kPersistentVersion ||
      load_u32(request.data() + 12) != kPersistentRequestBytes) {
    fail("persistent Turing request header differs");
  }
  Options result;
  result.block = load_u64(request.data() + 16);
  if (result.block >= kSourceBlockCount) {
    fail("persistent Turing block leaves the PT21 campaign");
  }
  result.required_sign_packet_sha256 =
      lower_hex(request.data() + 24, 32);
  result.have_block = true;
  result.have_packet_sha256 = true;
  return result;
}

void write_persistent_response(const std::string& artifact) {
  if (artifact.empty() ||
      artifact.size() >
          std::numeric_limits<std::uint32_t>::max() -
              kPersistentResponseHeaderBytes) {
    fail("persistent Turing artifact leaves the response bound");
  }
  std::array<unsigned char, kPersistentResponseHeaderBytes> header{};
  std::copy(kPersistentResponseMagic.begin(),
            kPersistentResponseMagic.end(), header.begin());
  store_u32(header.data() + 8, kPersistentVersion);
  store_u32(
      header.data() + 12,
      kPersistentResponseHeaderBytes +
          static_cast<std::uint32_t>(artifact.size()));
  write_exact(header.data(), header.size(),
              "persistent Turing response header");
  write_exact(
      reinterpret_cast<const unsigned char*>(artifact.data()),
      artifact.size(), "persistent Turing artifact");
  std::cout.flush();
  if (!std::cout) fail("cannot flush persistent Turing response");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    if (options.persistent_requests == 0) {
      const std::string artifact = artifact_json(options);
      std::cout << artifact;
      if (!std::cout) {
        fail("failed to write the complete Turing input artifact");
      }
    } else {
      for (std::uint32_t request = 0;
           request < options.persistent_requests; ++request) {
        write_persistent_response(
            artifact_json(read_persistent_request()));
      }
      require_persistent_eof();
    }
    flint_cleanup_master();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_pt21_turing_inputs: " << error.what() << '\n';
    flint_cleanup_master();
    return 2;
  }
}

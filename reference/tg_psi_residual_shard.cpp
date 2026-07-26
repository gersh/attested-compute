// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-scale two-pass verifier for the CH25 Chebyshev-psi computation.
//
// The prime stream comes from a pinned primesieve checkout.  Every logarithm
// is enclosed by CRlibm's correctly rounded log_rd/log_ru, then converted
// exactly from binary64 to Q64 integers.  Summary mode returns the additive
// interval transition and a commitment to every prime-power row.  Verify mode
// independently regenerates the same rows from a root-derived incoming state
// and checks the exact integer endpoint inequalities used by
// tg_verifier/finite_campaigns.py.

#include <primesieve.hpp>

extern "C" {
#include "crlibm.h"
}

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cfenv>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <boost/multiprecision/cpp_int.hpp>

#ifndef SPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT
#error "the psi residual shard must bind a pinned primesieve commit"
#endif

#ifndef SPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT
#error "the psi residual shard must bind a pinned CRlibm commit"
#endif

namespace {

using boost::multiprecision::cpp_int;
using u128 = unsigned __int128;

constexpr std::uint64_t kSourceLimit = 10'000'000'000'000ULL;
constexpr std::uint64_t kSourceEventCount = 346'065'767'406ULL;
constexpr unsigned int kScaleBits = 64;
constexpr u128 kScale = static_cast<u128>(1) << kScaleBits;
constexpr std::uint64_t kUpperNumerator = 19'764'819;
constexpr std::uint64_t kUpperDenominator = 25'000'000;
constexpr int kDefaultSieveSizeKiB = 384;
constexpr std::string_view kRowDomain =
    "sparkinterval.tg.psi-prime-power-rows.v1";
constexpr std::string_view kEventDomain =
    "sparkinterval.tg.psi-prime-power-events.v1";

struct Options {
  enum class Mode { kSummary, kVerify };
  std::uint64_t lower = 2;
  std::uint64_t upper = 1'000'000;
  Mode mode = Mode::kSummary;
  u128 incoming_lower = 0;
  u128 incoming_upper = 0;
  bool incoming_lower_given = false;
  bool incoming_upper_given = false;
  int sieve_size_kib = kDefaultSieveSizeKiB;
};

struct LogBounds {
  u128 lower;
  u128 upper;
};

struct PrimePower {
  std::uint64_t value;
  std::uint64_t prime;
  std::uint32_t exponent;
};

struct ExactFallbacks {
  std::uint64_t lower_left_limit = 0;
  std::uint64_t upper_post_jump = 0;
  std::uint64_t terminal_lower = 0;
};

struct StreamResult {
  u128 delta_lower = 0;
  u128 delta_upper = 0;
  u128 outgoing_lower = 0;
  u128 outgoing_upper = 0;
  std::uint64_t events = 0;
  std::uint64_t prime_events = 0;
  std::uint64_t higher_power_events = 0;
  std::string event_sha256;
  std::string row_sha256;
  ExactFallbacks exact_fallbacks;
  bool terminal_strict_lower_checked = false;
};

[[noreturn]] void fail(const std::string& message) {
  std::cerr << message << '\n';
  std::exit(2);
}

bool parse_u64(std::string_view text, std::uint64_t* output) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto result = std::from_chars(begin, end, *output);
  return result.ec == std::errc{} && result.ptr == end;
}

bool parse_u128(std::string_view text, u128* output) {
  if (text.empty()) return false;
  u128 value = 0;
  constexpr u128 maximum = ~static_cast<u128>(0);
  for (char character : text) {
    if (character < '0' || character > '9') return false;
    const unsigned int digit = static_cast<unsigned int>(character - '0');
    if (value > (maximum - digit) / 10) return false;
    value = value * 10 + digit;
  }
  *output = value;
  return true;
}

std::string u128_string(u128 value) {
  if (value == 0) return "0";
  std::string result;
  while (value != 0) {
    result.push_back(static_cast<char>('0' + value % 10));
    value /= 10;
  }
  std::reverse(result.begin(), result.end());
  return result;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--lower") {
      if (!parse_u64(value("--lower"), &options.lower)) {
        fail("--lower must be an unsigned integer");
      }
    } else if (argument == "--upper") {
      if (!parse_u64(value("--upper"), &options.upper)) {
        fail("--upper must be an unsigned integer");
      }
    } else if (argument == "--mode") {
      const std::string_view mode = value("--mode");
      if (mode == "summary") {
        options.mode = Options::Mode::kSummary;
      } else if (mode == "verify") {
        options.mode = Options::Mode::kVerify;
      } else {
        fail("--mode must be summary or verify");
      }
    } else if (argument == "--incoming-lower") {
      if (!parse_u128(value("--incoming-lower"), &options.incoming_lower)) {
        fail("--incoming-lower must be an unsigned 128-bit integer");
      }
      options.incoming_lower_given = true;
    } else if (argument == "--incoming-upper") {
      if (!parse_u128(value("--incoming-upper"), &options.incoming_upper)) {
        fail("--incoming-upper must be an unsigned 128-bit integer");
      }
      options.incoming_upper_given = true;
    } else if (argument == "--sieve-size-kib") {
      std::uint64_t parsed = 0;
      if (!parse_u64(value("--sieve-size-kib"), &parsed) || parsed > 8192) {
        fail("--sieve-size-kib must lie in [16, 8192]");
      }
      options.sieve_size_kib = static_cast<int>(parsed);
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-psi-residual-shard "
             "--lower N --upper N --mode summary|verify "
             "[--incoming-lower L --incoming-upper U] "
             "[--sieve-size-kib N]\n"
             "The shard range is inclusive.  A non-root verify shard "
             "requires both root-derived Q64 incoming states.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.lower < 2 || options.upper < options.lower ||
      options.upper > kSourceLimit) {
    fail("the inclusive shard must lie in [2, 10000000000000]");
  }
  if (options.sieve_size_kib < 16 || options.sieve_size_kib > 8192) {
    fail("--sieve-size-kib must lie in [16, 8192]");
  }
  if (options.incoming_lower_given != options.incoming_upper_given) {
    fail("both incoming interval endpoints must be supplied together");
  }
  if (options.mode == Options::Mode::kSummary &&
      options.incoming_lower_given) {
    fail("summary mode does not accept an incoming state");
  }
  if (options.mode == Options::Mode::kVerify && options.lower != 2 &&
      !options.incoming_lower_given) {
    fail("a non-root verify shard requires both incoming interval endpoints");
  }
  if (options.incoming_lower > options.incoming_upper) {
    fail("the incoming psi interval is reversed");
  }
  return options;
}

std::uint64_t integer_sqrt_u64(std::uint64_t value) {
  std::uint64_t estimate = static_cast<std::uint64_t>(
      std::sqrt(static_cast<long double>(value)));
  while (estimate != std::numeric_limits<std::uint64_t>::max() &&
         (estimate + 1) <= value / (estimate + 1)) {
    ++estimate;
  }
  while (estimate != 0 && estimate > value / estimate) --estimate;
  return estimate;
}

cpp_int to_cpp_int(u128 value) {
  cpp_int result = static_cast<std::uint64_t>(value >> 64U);
  result <<= 64U;
  result += static_cast<std::uint64_t>(value);
  return result;
}

// Return floor/ceil(value * 2^64) by decoding binary64 exactly.  No
// floating-point multiplication or integer conversion is used here.
u128 scale_binary64(double value, bool round_up) {
  if (!(value > 0.0) || !std::isfinite(value)) {
    fail("CRlibm returned a non-positive or non-finite logarithm endpoint");
  }
  const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
  if ((bits >> 63U) != 0) fail("CRlibm returned a negative log endpoint");
  const unsigned int biased = static_cast<unsigned int>((bits >> 52U) & 0x7ffU);
  if (biased == 0 || biased == 0x7ffU) {
    fail("CRlibm returned a non-normal log endpoint");
  }
  const std::uint64_t significand =
      (std::uint64_t{1} << 52U) | (bits & ((std::uint64_t{1} << 52U) - 1));
  const int exponent = static_cast<int>(biased) - 1023;
  const int shift = exponent - 52 + static_cast<int>(kScaleBits);
  if (shift >= 0) {
    if (shift >= 128 || static_cast<u128>(significand) >
                            (~static_cast<u128>(0) >> shift)) {
      fail("scaled CRlibm logarithm exceeds unsigned 128-bit range");
    }
    return static_cast<u128>(significand) << shift;
  }
  const unsigned int right = static_cast<unsigned int>(-shift);
  if (right >= 64) return round_up ? 1 : 0;
  const std::uint64_t quotient = significand >> right;
  const std::uint64_t remainder =
      significand & ((std::uint64_t{1} << right) - 1);
  return static_cast<u128>(quotient) + (round_up && remainder != 0 ? 1 : 0);
}

LogBounds fixed_log_bounds(std::uint64_t prime) {
  // Every source-range prime is below 2^53, hence this conversion is exact.
  const double input = static_cast<double>(prime);
  if (static_cast<std::uint64_t>(input) != prime) {
    fail("prime is not exactly representable as binary64");
  }
  const double lower = log_rd(input);
  const double upper = log_ru(input);
  LogBounds result{scale_binary64(lower, false),
                   scale_binary64(upper, true)};
  if (result.lower > result.upper) {
    fail("CRlibm produced a reversed logarithm interval");
  }
  return result;
}

void put_u32_be(unsigned char* output, std::uint32_t value) {
  for (unsigned int index = 0; index < 4; ++index) {
    output[index] = static_cast<unsigned char>(value >> (24U - 8U * index));
  }
}

void put_u64_be(unsigned char* output, std::uint64_t value) {
  for (unsigned int index = 0; index < 8; ++index) {
    output[index] = static_cast<unsigned char>(value >> (56U - 8U * index));
  }
}

void put_u128_be(unsigned char* output, u128 value) {
  for (unsigned int index = 0; index < 16; ++index) {
    output[index] =
        static_cast<unsigned char>(value >> (120U - 8U * index));
  }
}

void hash_event(sparkinterval::detail::Sha256* hasher,
                const PrimePower& event, const LogBounds& log) {
  std::array<unsigned char, 52> row{};
  put_u64_be(row.data(), event.value);
  put_u64_be(row.data() + 8, event.prime);
  put_u32_be(row.data() + 16, event.exponent);
  put_u128_be(row.data() + 20, log.lower);
  put_u128_be(row.data() + 36, log.upper);
  hasher->update(row.data(), row.size());
}

void hash_event_structure(sparkinterval::detail::Sha256* hasher,
                          const PrimePower& event) {
  std::array<unsigned char, 20> row{};
  put_u64_be(row.data(), event.value);
  put_u64_be(row.data() + 8, event.prime);
  put_u32_be(row.data() + 16, event.exponent);
  hasher->update(row.data(), row.size());
}

std::vector<PrimePower> higher_prime_powers(std::uint64_t lower,
                                            std::uint64_t upper) {
  const std::uint64_t base_limit = integer_sqrt_u64(upper);
  primesieve::iterator iterator(2, base_limit);
  std::vector<PrimePower> powers;
  for (std::uint64_t prime = iterator.next_prime(); prime <= base_limit;
       prime = iterator.next_prime()) {
    std::uint64_t power = prime * prime;
    std::uint32_t exponent = 2;
    while (power <= upper) {
      if (power >= lower) powers.push_back({power, prime, exponent});
      if (power > upper / prime) break;
      power *= prime;
      ++exponent;
    }
  }
  std::sort(powers.begin(), powers.end(),
            [](const PrimePower& left, const PrimePower& right) {
              if (left.value != right.value) return left.value < right.value;
              if (left.prime != right.prime) return left.prime < right.prime;
              return left.exponent < right.exponent;
            });
  for (std::size_t index = 1; index < powers.size(); ++index) {
    if (powers[index - 1].value >= powers[index].value) {
      fail("higher-prime-power construction is not strictly value ordered");
    }
  }
  return powers;
}

bool exact_lower_endpoint(std::uint64_t value, u128 psi_lower,
                          bool strict, std::uint64_t* fallback_count) {
  const u128 x_scaled = static_cast<u128>(value) << kScaleBits;
  if (psi_lower >= x_scaled) return true;
  const u128 difference = x_scaled - psi_lower;
  const std::uint64_t quotient =
      static_cast<std::uint64_t>(difference >> kScaleBits);
  const bool has_remainder = static_cast<std::uint64_t>(difference) != 0;
  if (has_remainder && quotient == std::numeric_limits<std::uint64_t>::max()) {
    return false;
  }
  const std::uint64_t ceiling = quotient + (has_remainder ? 1 : 0);
#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
  const std::uint64_t root = integer_sqrt_u64(2 * value);
  if (ceiling <= root &&
      (!strict || ceiling < root || has_remainder ||
       root * root < 2 * value)) {
    return true;
  }
  if (quotient > root) return false;
#else
  // Compare the floor/ceiling squares directly instead of computing
  // floor(sqrt(2*value)) for every prime-power event.  Both quotient values
  // are uint64, so their products fit exactly in u128.  If the ceiling square
  // is inside the bound, the true fixed-point difference is also inside.  In
  // the strict case equality is safe only when a nonzero Q64 remainder makes
  // the true difference strictly smaller than ceiling * 2^64.  Conversely,
  // a floor square outside the bound proves failure.  Only the one-cell
  // boundary between those tests needs the existing arbitrary-precision
  // fallback.
  const u128 bound = static_cast<u128>(2) * value;
  const u128 ceiling_squared = static_cast<u128>(ceiling) * ceiling;
  if ((!strict && ceiling_squared <= bound) ||
      (strict && (ceiling_squared < bound ||
                  (has_remainder && ceiling_squared <= bound)))) {
    return true;
  }
  const u128 quotient_squared = static_cast<u128>(quotient) * quotient;
  if (quotient_squared > bound) return false;
#endif
  ++*fallback_count;
  const cpp_int difference_exact = to_cpp_int(difference);
  const cpp_int left = difference_exact * difference_exact;
  const cpp_int right = cpp_int(2) * value << (2 * kScaleBits);
  return strict ? left < right : left <= right;
}

bool exact_upper_endpoint(std::uint64_t value, u128 psi_upper,
                          std::uint64_t* fallback_count) {
  const u128 x_scaled = static_cast<u128>(value) << kScaleBits;
  if (psi_upper <= x_scaled) return true;
  const u128 difference = psi_upper - x_scaled;
  const std::uint64_t quotient =
      static_cast<std::uint64_t>(difference >> kScaleBits);
  const bool has_remainder = static_cast<std::uint64_t>(difference) != 0;
  auto exact_fallback = [&]() {
    ++*fallback_count;
    const cpp_int difference_exact = to_cpp_int(difference);
    const cpp_int left = difference_exact * difference_exact *
                         kUpperDenominator * kUpperDenominator;
    const cpp_int right = cpp_int(kUpperNumerator) * kUpperNumerator * value
                          << (2 * kScaleBits);
    return left <= right;
  };
  // Keep all fixed-width products comfortably below 2^128.  This branch is
  // not a mathematical cutoff: unusual supplied states take the exact path.
  if (quotient > 3'000'000) return exact_fallback();
  const std::uint64_t ceiling = quotient + (has_remainder ? 1 : 0);
  const u128 denominator_squared =
      static_cast<u128>(kUpperDenominator) * kUpperDenominator;
  const u128 numerator_squared =
      static_cast<u128>(kUpperNumerator) * kUpperNumerator;
  const u128 right_small = numerator_squared * value;
  const u128 ceiling_left =
      static_cast<u128>(ceiling) * ceiling * denominator_squared;
  if (ceiling_left <= right_small) return true;
  const u128 floor_left =
      static_cast<u128>(quotient) * quotient * denominator_squared;
  if (floor_left > right_small) return false;
  return exact_fallback();
}

#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
class EventProcessor {
#else
template <bool Verify>
class EventProcessor {
#endif
 public:
  EventProcessor(const Options& options,
                 sparkinterval::detail::Sha256* event_hasher,
                 sparkinterval::detail::Sha256* row_hasher)
      : options_(options), event_hasher_(event_hasher), row_hasher_(row_hasher),
        current_lower_(options.incoming_lower),
        current_upper_(options.incoming_upper) {}

  void process(const PrimePower& event) {
    if (event.value < options_.lower || event.value > options_.upper) {
      fail("prime-power event escaped the requested shard");
    }
    if (has_previous_ && event.value <= previous_value_) {
      fail("merged prime-power stream is not strictly value ordered");
    }
    const LogBounds log = fixed_log_bounds(event.prime);
    hash_event_structure(event_hasher_, event);
    hash_event(row_hasher_, event, log);

#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
    if (options_.mode == Options::Mode::kVerify) {
#else
    if constexpr (Verify) {
#endif
      if (!exact_lower_endpoint(event.value, current_lower_, false,
                                &fallbacks_.lower_left_limit)) {
        fail("lower psi envelope fails at the left limit of " +
             std::to_string(event.value));
      }
    }
    constexpr u128 maximum = ~static_cast<u128>(0);
    if (delta_lower_ > maximum - log.lower ||
        delta_upper_ > maximum - log.upper ||
        current_lower_ > maximum - log.lower ||
        current_upper_ > maximum - log.upper) {
      fail("Q64 psi interval accumulator overflow");
    }
    delta_lower_ += log.lower;
    delta_upper_ += log.upper;
    current_lower_ += log.lower;
    current_upper_ += log.upper;
#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
    if (options_.mode == Options::Mode::kVerify) {
#else
    if constexpr (Verify) {
#endif
      if (!exact_upper_endpoint(event.value, current_upper_,
                                &fallbacks_.upper_post_jump)) {
        fail("upper psi envelope fails after the jump at " +
             std::to_string(event.value));
      }
    }
    if (event.exponent == 1) {
      ++prime_events_;
    } else {
      ++higher_power_events_;
    }
    ++events_;
    previous_value_ = event.value;
    has_previous_ = true;
  }

  StreamResult finish() {
    bool terminal_checked = false;
#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
    if (options_.mode == Options::Mode::kVerify) {
#else
    if constexpr (Verify) {
#endif
      if (options_.upper == kSourceLimit) {
        terminal_checked = true;
        if (!exact_lower_endpoint(kSourceLimit, current_lower_, true,
                                  &fallbacks_.terminal_lower)) {
          fail("strict lower psi envelope fails at the source endpoint");
        }
      }
    }
    return {
        .delta_lower = delta_lower_,
        .delta_upper = delta_upper_,
        .outgoing_lower = current_lower_,
        .outgoing_upper = current_upper_,
        .events = events_,
        .prime_events = prime_events_,
        .higher_power_events = higher_power_events_,
        .event_sha256 = "",
        .row_sha256 = "",
        .exact_fallbacks = fallbacks_,
        .terminal_strict_lower_checked = terminal_checked,
    };
  }

 private:
  const Options& options_;
  sparkinterval::detail::Sha256* event_hasher_;
  sparkinterval::detail::Sha256* row_hasher_;
  u128 delta_lower_ = 0;
  u128 delta_upper_ = 0;
  u128 current_lower_;
  u128 current_upper_;
  std::uint64_t events_ = 0;
  std::uint64_t prime_events_ = 0;
  std::uint64_t higher_power_events_ = 0;
  std::uint64_t previous_value_ = 0;
  bool has_previous_ = false;
  ExactFallbacks fallbacks_;
};

#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
StreamResult run_stream(const Options& options) {
#else
template <bool Verify>
StreamResult run_stream(const Options& options) {
#endif
  const std::vector<PrimePower> powers =
      higher_prime_powers(options.lower, options.upper);
  primesieve::iterator primes(options.lower, options.upper);
  std::uint64_t prime = primes.next_prime();
  std::size_t power_index = 0;

  sparkinterval::detail::Sha256 event_hasher;
  event_hasher.update(kEventDomain.data(), kEventDomain.size());
  sparkinterval::detail::Sha256 row_hasher;
  row_hasher.update(kRowDomain.data(), kRowDomain.size());
  const unsigned char zero = 0;
  event_hasher.update(&zero, 1);
  row_hasher.update(&zero, 1);
#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
  EventProcessor processor(options, &event_hasher, &row_hasher);
#else
  EventProcessor<Verify> processor(options, &event_hasher, &row_hasher);
#endif

  while (prime <= options.upper || power_index < powers.size()) {
    const bool take_prime =
        prime <= options.upper &&
        (power_index == powers.size() || prime < powers[power_index].value);
    if (take_prime) {
      processor.process({prime, prime, 1});
      prime = primes.next_prime();
    } else {
      if (prime <= options.upper && prime == powers[power_index].value) {
        fail("a prime collided with a higher prime power");
      }
      processor.process(powers[power_index++]);
    }
  }
  StreamResult result = processor.finish();
  result.event_sha256 =
      sparkinterval::lowercase_hex(event_hasher.finish());
  result.row_sha256 =
      sparkinterval::lowercase_hex(row_hasher.finish());
  if (result.events != result.prime_events + result.higher_power_events) {
    fail("prime-power event counters do not add up");
  }
  if (options.lower == 2 && options.upper == kSourceLimit &&
      result.events != kSourceEventCount) {
    fail("full-source prime-power event count differs from the pinned value");
  }
  return result;
}

void print_u128_array(u128 first, u128 second) {
  std::cout << '[' << u128_string(first) << ',' << u128_string(second) << ']';
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  if (!std::numeric_limits<double>::is_iec559 || sizeof(double) != 8) {
    fail("the CRlibm adapter requires IEEE-754 binary64 double");
  }
  if (std::fesetround(FE_TONEAREST) != 0 ||
      std::fegetround() != FE_TONEAREST) {
    fail("cannot establish round-to-nearest for CRlibm");
  }
  const unsigned long long crlibm_state = crlibm_init();
  primesieve::set_sieve_size(options.sieve_size_kib);
  const auto started = std::chrono::steady_clock::now();

  StreamResult result;
  try {
#ifdef SPARKINTERVAL_PSI_LITERAL_REFERENCE
    result = run_stream(options);
#else
    result = options.mode == Options::Mode::kSummary
                 ? run_stream<false>(options)
                 : run_stream<true>(options);
#endif
  } catch (const std::exception& error) {
    crlibm_exit(crlibm_state);
    fail(std::string("prime stream failed: ") + error.what());
  }
  crlibm_exit(crlibm_state);
  const double elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();

  const char* mode =
      options.mode == Options::Mode::kSummary ? "summary" : "verify";
  std::cout << "{\"algorithm\":\"ch25-psi-prime-power-two-pass-v1\",";
  std::cout << "\"mode\":\"" << mode << "\",";
  std::cout << "\"classification\":\"source-scale-shard-not-lean-proof\",";
  std::cout << "\"atom\":\"ch25-psi-1e13\",";
  std::cout << "\"primesieve_commit\":\""
            << SPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT << "\",";
  std::cout << "\"crlibm_commit\":\""
            << SPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT << "\",";
  std::cout << "\"lower\":" << options.lower << ",\"upper_exclusive\":"
            << options.upper + 1 << ",\"work_count\":"
            << options.upper - options.lower + 1 << ',';
  std::cout << "\"scale_bits\":" << kScaleBits
            << ",\"sieve_size_kib\":" << options.sieve_size_kib << ',';
  std::cout << "\"log_interval_encoding\":"
               "\"crlibm-binary64-directed-to-q64-v1\",";
  std::cout << "\"event_encoding\":"
               "\"u64be-value-u64be-prime-u32be-exponent-v1\",";
  std::cout << "\"event_sha256\":\"" << result.event_sha256 << "\",";
  std::cout << "\"row_encoding\":"
               "\"u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1\",";
  std::cout << "\"row_sha256\":\"" << result.row_sha256 << "\",";
  std::cout << "\"prime_power_events\":" << result.events
            << ",\"prime_events\":" << result.prime_events
            << ",\"higher_power_events\":" << result.higher_power_events
            << ',';
  std::cout << "\"state_components\":[\"psi_lower_q64\","
               "\"psi_upper_q64\"],\"delta\":";
  print_u128_array(result.delta_lower, result.delta_upper);
  std::cout << ",\"guards\":";
  if (options.mode == Options::Mode::kSummary) {
    std::cout << "{}";
  } else {
    std::cout << "{\"ch25-psi-1e13\":{\"lower_guard\":";
    print_u128_array(options.incoming_lower, options.incoming_upper);
    std::cout << ",\"upper_guard\":";
    print_u128_array(options.incoming_lower, options.incoming_upper);
    std::cout << ",\"witnesses\":[]}}";
  }
  std::cout << ",\"incoming_state\":";
  if (options.mode == Options::Mode::kSummary) {
    std::cout << "null,\"outgoing_state\":null";
  } else {
    print_u128_array(options.incoming_lower, options.incoming_upper);
    std::cout << ",\"outgoing_state\":";
    print_u128_array(result.outgoing_lower, result.outgoing_upper);
  }
  std::cout << ",\"exact_fallbacks\":{";
  std::cout << "\"lower_left_limit\":"
            << result.exact_fallbacks.lower_left_limit << ',';
  std::cout << "\"upper_post_jump\":"
            << result.exact_fallbacks.upper_post_jump << ',';
  std::cout << "\"terminal_lower\":"
            << result.exact_fallbacks.terminal_lower << "},";
  std::cout << "\"terminal_strict_lower_checked\":"
            << (result.terminal_strict_lower_checked ? "true" : "false")
            << ",\"accepted\":true,\"elapsed_seconds\":"
            << std::setprecision(9) << elapsed
            << ",\"execution_attested\":false,"
               "\"lean_atom_discharged\":false}\n";
  return 0;
}

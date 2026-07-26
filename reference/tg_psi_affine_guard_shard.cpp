// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// One-pass affine-guard producer for the CH25 Chebyshev-psi computation.
//
// This translation unit deliberately includes the reviewed two-pass worker so
// prime-power enumeration, CRlibm conversion, row encodings, and commitments
// have one implementation.  Its own entry point emits the additive transition
// together with a conservative rectangle of incoming Q64 states for which all
// lower-left-limit and upper-post-jump inequalities hold.  A supervisor can
// therefore run every shard in parallel, exclusive-scan the deltas, and check
// each derived incoming state against the retained rectangle without replaying
// the prime-power stream.

#define main sparkinterval_tg_psi_two_pass_embedded_main
#include "tg_psi_residual_shard.cpp"
#undef main

namespace {

constexpr unsigned int kGuardFractionBits = 16;
constexpr unsigned int kGuardToQ64Shift =
    kScaleBits - kGuardFractionBits;
constexpr std::uint64_t kGuardScale =
    std::uint64_t{1} << kGuardFractionBits;

struct AffineGuard {
  u128 lower_min = 0;
  u128 upper_max = ~static_cast<u128>(0);
  std::uint64_t lower_witness_index = 0;
  std::uint64_t lower_witness_value = 0;
  u128 lower_witness_delta = 0;
  u128 lower_witness_radius = 0;
  bool lower_witness_strict = false;
  std::string lower_witness_kind;
  std::uint64_t upper_witness_index = 0;
  std::uint64_t upper_witness_value = 0;
  u128 upper_witness_delta = 0;
  u128 upper_witness_radius = 0;
  std::string upper_witness_kind;
  bool terminal_strict_lower_constrained = false;
};

struct AffineResult {
  StreamResult stream;
  AffineGuard guard;
};

Options parse_affine_options(int argc, char** argv) {
  Options options;
  bool saw_mode = false;
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
    } else if (argument == "--sieve-size-kib") {
      std::uint64_t parsed = 0;
      if (!parse_u64(value("--sieve-size-kib"), &parsed) || parsed > 8192) {
        fail("--sieve-size-kib must lie in [16, 8192]");
      }
      options.sieve_size_kib = static_cast<int>(parsed);
    } else if (argument == "--mode") {
      if (value("--mode") != "affine") fail("--mode must be affine");
      saw_mode = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-psi-affine-guard-shard "
             "--mode affine --lower N --upper N "
             "[--sieve-size-kib N]\n"
             "The shard range is inclusive.  No incoming state is accepted; "
             "the output contains its allowed incoming rectangle.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (!saw_mode) fail("--mode affine is required");
  if (options.lower < 2 || options.upper < options.lower ||
      options.upper > kSourceLimit) {
    fail("the inclusive shard must lie in [2, 10000000000000]");
  }
  if (options.sieve_size_kib < 16 || options.sieve_size_kib > 8192) {
    fail("--sieve-size-kib must lie in [16, 8192]");
  }
  return options;
}

// Return floor(sqrt(value) * 2^16).  Binary64 supplies only a starting
// estimate.  The two exact u128 square loops establish the returned integer,
// so the guard does not rely on the direction or last bit of libm sqrt.
std::uint64_t scaled_sqrt_floor(std::uint64_t value) {
  const double approximate =
      std::sqrt(static_cast<double>(value)) *
      static_cast<double>(kGuardScale);
  if (!(approximate >= 0.0) || !std::isfinite(approximate) ||
      approximate >
          static_cast<double>(std::numeric_limits<std::uint64_t>::max())) {
    fail("cannot seed the affine-guard integer square root");
  }
  std::uint64_t estimate = static_cast<std::uint64_t>(approximate);
  const u128 radicand =
      static_cast<u128>(value) << (2 * kGuardFractionBits);
  while (estimate != std::numeric_limits<std::uint64_t>::max()) {
    const u128 following = static_cast<u128>(estimate + 1);
    if (following * following > radicand) break;
    ++estimate;
  }
  while (static_cast<u128>(estimate) * estimate > radicand) --estimate;
  return estimate;
}

u128 lower_radius_q64(std::uint64_t value, bool strict) {
  const std::uint64_t scaled_root = scaled_sqrt_floor(2 * value);
  u128 radius =
      static_cast<u128>(scaled_root) << kGuardToQ64Shift;
  if (strict) {
    const u128 radicand =
        static_cast<u128>(2 * value) << (2 * kGuardFractionBits);
    if (static_cast<u128>(scaled_root) * scaled_root == radicand) {
      if (radius == 0) fail("strict affine lower radius underflow");
      --radius;
    }
  }
  return radius;
}

u128 upper_radius_q64(std::uint64_t value) {
  const std::uint64_t scaled_root = scaled_sqrt_floor(value);
  const u128 numerator =
      (static_cast<u128>(kUpperNumerator) * scaled_root)
      << kGuardToQ64Shift;
  return numerator / kUpperDenominator;
}

class AffineEventProcessor {
 public:
  AffineEventProcessor(const Options& options,
                       sparkinterval::detail::Sha256* event_hasher,
                       sparkinterval::detail::Sha256* row_hasher)
      : options_(options), event_hasher_(event_hasher),
        row_hasher_(row_hasher) {}

  void constrain_lower(std::uint64_t value, bool strict,
                       std::uint64_t event_index) {
    const u128 x_scaled = static_cast<u128>(value) << kScaleBits;
    const u128 radius = lower_radius_q64(value, strict);
    const u128 boundary = x_scaled > radius ? x_scaled - radius : 0;
    const u128 required =
        boundary > delta_lower_ ? boundary - delta_lower_ : 0;
    if (guard_.lower_witness_kind.empty() || required > guard_.lower_min) {
      guard_.lower_min = required;
      guard_.lower_witness_index = event_index;
      guard_.lower_witness_value = value;
      guard_.lower_witness_delta = delta_lower_;
      guard_.lower_witness_radius = radius;
      guard_.lower_witness_strict = strict;
      guard_.lower_witness_kind =
          strict ? "terminal_strict_lower" : "lower_left_limit";
    }
  }

  void constrain_upper(std::uint64_t value, std::uint64_t event_index) {
    const u128 x_scaled = static_cast<u128>(value) << kScaleBits;
    const u128 radius = upper_radius_q64(value);
    constexpr u128 maximum = ~static_cast<u128>(0);
    if (x_scaled > maximum - radius) {
      fail("affine upper boundary overflows u128");
    }
    const u128 boundary = x_scaled + radius;
    if (boundary < delta_upper_) {
      fail("affine upper guard has no nonnegative incoming state");
    }
    const u128 allowed = boundary - delta_upper_;
    if (guard_.upper_witness_kind.empty() || allowed < guard_.upper_max) {
      guard_.upper_max = allowed;
      guard_.upper_witness_index = event_index;
      guard_.upper_witness_value = value;
      guard_.upper_witness_delta = delta_upper_;
      guard_.upper_witness_radius = radius;
      guard_.upper_witness_kind = "upper_post_jump";
    }
  }

  void process(const PrimePower& event) {
    if (event.value < options_.lower || event.value > options_.upper) {
      fail("prime-power event escaped the requested affine shard");
    }
    if (has_previous_ && event.value <= previous_value_) {
      fail("affine prime-power stream is not strictly value ordered");
    }
    const LogBounds log = fixed_log_bounds(event.prime);
    hash_event_structure(event_hasher_, event);
    hash_event(row_hasher_, event, log);
    constrain_lower(event.value, false, events_);

    constexpr u128 maximum = ~static_cast<u128>(0);
    if (delta_lower_ > maximum - log.lower ||
        delta_upper_ > maximum - log.upper) {
      fail("affine Q64 psi transition overflow");
    }
    delta_lower_ += log.lower;
    delta_upper_ += log.upper;
    constrain_upper(event.value, events_);

    if (event.exponent == 1) {
      ++prime_events_;
    } else {
      ++higher_power_events_;
    }
    ++events_;
    previous_value_ = event.value;
    has_previous_ = true;
  }

  AffineResult finish() {
    if (options_.upper == kSourceLimit) {
      constrain_lower(kSourceLimit, true, events_);
      guard_.terminal_strict_lower_constrained = true;
    }
    constexpr u128 maximum = ~static_cast<u128>(0);
    if (guard_.lower_witness_kind.empty() ||
        guard_.upper_witness_kind.empty()) {
      fail("affine incoming rectangle has no event witnesses");
    }
    // Because accepted inputs also require lower <= upper, the event-derived
    // upper cap bounds both endpoints.  Check it makes both transition
    // additions safe instead of silently replacing an event witness with an
    // unreported overflow constraint.
    if (guard_.upper_max > maximum - delta_lower_ ||
        guard_.upper_max > maximum - delta_upper_) {
      fail("affine event guard does not imply accumulator safety");
    }
    if (guard_.lower_min > guard_.upper_max) {
      fail("affine incoming rectangle is empty");
    }
    StreamResult stream{
        .delta_lower = delta_lower_,
        .delta_upper = delta_upper_,
        .outgoing_lower = 0,
        .outgoing_upper = 0,
        .events = events_,
        .prime_events = prime_events_,
        .higher_power_events = higher_power_events_,
        .event_sha256 = "",
        .row_sha256 = "",
        .exact_fallbacks = {},
        .terminal_strict_lower_checked = false,
    };
    return {.stream = std::move(stream), .guard = guard_};
  }

 private:
  const Options& options_;
  sparkinterval::detail::Sha256* event_hasher_;
  sparkinterval::detail::Sha256* row_hasher_;
  u128 delta_lower_ = 0;
  u128 delta_upper_ = 0;
  std::uint64_t events_ = 0;
  std::uint64_t prime_events_ = 0;
  std::uint64_t higher_power_events_ = 0;
  std::uint64_t previous_value_ = 0;
  bool has_previous_ = false;
  AffineGuard guard_;
};

AffineResult run_affine_stream(const Options& options) {
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
  AffineEventProcessor processor(options, &event_hasher, &row_hasher);

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
  AffineResult result = processor.finish();
  result.stream.event_sha256 =
      sparkinterval::lowercase_hex(event_hasher.finish());
  result.stream.row_sha256 =
      sparkinterval::lowercase_hex(row_hasher.finish());
  if (result.stream.events !=
      result.stream.prime_events + result.stream.higher_power_events) {
    fail("affine prime-power event counters do not add up");
  }
  if (options.lower == 2 && options.upper == kSourceLimit &&
      result.stream.events != kSourceEventCount) {
    fail("full-source affine event count differs from the pinned value");
  }
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_affine_options(argc, argv);
  if (!std::numeric_limits<double>::is_iec559 || sizeof(double) != 8) {
    fail("the affine CRlibm adapter requires IEEE-754 binary64 double");
  }
  if (std::fesetround(FE_TONEAREST) != 0 ||
      std::fegetround() != FE_TONEAREST) {
    fail("cannot establish round-to-nearest for the affine worker");
  }
  const unsigned long long crlibm_state = crlibm_init();
  primesieve::set_sieve_size(options.sieve_size_kib);
  const auto started = std::chrono::steady_clock::now();
  AffineResult result;
  try {
    result = run_affine_stream(options);
  } catch (const std::exception& error) {
    crlibm_exit(crlibm_state);
    fail(std::string("affine prime stream failed: ") + error.what());
  }
  crlibm_exit(crlibm_state);
  const double elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started).count();

  std::cout
      << "{\"algorithm\":\"ch25-psi-prime-power-affine-guard-v1\","
      << "\"mode\":\"affine\","
      << "\"classification\":\"source-scale-shard-not-lean-proof\","
      << "\"atom\":\"ch25-psi-1e13\","
      << "\"primesieve_commit\":\""
      << SPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT << "\","
      << "\"crlibm_commit\":\""
      << SPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT << "\","
      << "\"lower\":" << options.lower
      << ",\"upper_exclusive\":" << options.upper + 1
      << ",\"work_count\":" << options.upper - options.lower + 1
      << ",\"scale_bits\":" << kScaleBits
      << ",\"sieve_size_kib\":" << options.sieve_size_kib << ','
      << "\"log_interval_encoding\":"
         "\"crlibm-binary64-directed-to-q64-v1\","
      << "\"event_encoding\":"
         "\"u64be-value-u64be-prime-u32be-exponent-v1\","
      << "\"event_sha256\":\"" << result.stream.event_sha256 << "\","
      << "\"row_encoding\":"
         "\"u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1\","
      << "\"row_sha256\":\"" << result.stream.row_sha256 << "\","
      << "\"prime_power_events\":" << result.stream.events
      << ",\"prime_events\":" << result.stream.prime_events
      << ",\"higher_power_events\":"
      << result.stream.higher_power_events
      << ",\"state_components\":[\"psi_lower_q64\",\"psi_upper_q64\"],"
      << "\"delta\":";
  print_u128_array(result.stream.delta_lower, result.stream.delta_upper);
  std::cout
      << ",\"guard_encoding\":"
         "\"independent-q64-rectangle-with-lower-le-upper-v1\","
      << "\"allowed_incoming_q64\":{\"lower_min\":"
      << u128_string(result.guard.lower_min)
      << ",\"upper_max\":" << u128_string(result.guard.upper_max)
      << ",\"predicate\":\"lower_min<=lower<=upper<=upper_max\"},"
      << "\"guard_witnesses\":{\"lower_min\":{\"event_index\":"
      << result.guard.lower_witness_index << ",\"value\":"
      << result.guard.lower_witness_value << ",\"prefix_delta_q64\":"
      << u128_string(result.guard.lower_witness_delta)
      << ",\"radius_q64\":"
      << u128_string(result.guard.lower_witness_radius)
      << ",\"strict\":"
      << (result.guard.lower_witness_strict ? "true" : "false")
      << ",\"kind\":\""
      << result.guard.lower_witness_kind
      << "\"},\"upper_max\":{\"event_index\":"
      << result.guard.upper_witness_index << ",\"value\":"
      << result.guard.upper_witness_value << ",\"prefix_delta_q64\":"
      << u128_string(result.guard.upper_witness_delta)
      << ",\"radius_q64\":"
      << u128_string(result.guard.upper_witness_radius)
      << ",\"kind\":\""
      << result.guard.upper_witness_kind << "\"}},"
      << "\"guard_derivation\":{"
      << "\"sqrt_fraction_bits\":" << kGuardFractionBits << ','
      << "\"lower_radius\":"
         "\"floor(sqrt(2*x)*2^16)*2^48\","
      << "\"upper_radius\":"
         "\"floor(19764819*floor(sqrt(x)*2^16)*2^48/25000000)\"},"
      << "\"terminal_strict_lower_constrained\":"
      << (result.guard.terminal_strict_lower_constrained ? "true" : "false")
      << ",\"incoming_state\":null,\"outgoing_state\":null,"
      << "\"accepted\":true,\"elapsed_seconds\":"
      << std::setprecision(17) << elapsed
      << ",\"execution_attested\":false,\"lean_atom_discharged\":false}\n";
  return 0;
}

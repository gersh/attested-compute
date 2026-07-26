// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded-memory FLINT 3.6.0 verifier for the Platt--Trudgian zeta residual.
//
// The source-scale engine uses FLINT's public Platt local-isolation API.  It
// performs the same rigorous grid evaluation and Turing-complete sign-change
// isolation as acb_dirichlet_platt_zeta_zeros, but deliberately retains the
// isolating endpoints instead of paying to refine every zero.  The audit
// engine calls acb_dirichlet_platt_zeta_zeros itself for spot replay.  Neither
// engine assumes simplicity: the FLINT call must return every requested
// multiplicity-counted index, or the shard fails closed.

#include <flint/acb.h>
#include <flint/acb_dirichlet.h>
#include <flint/arb.h>
#include <flint/arb_calc.h>
#include <flint/arf.h>
#include <flint/flint.h>
#include <flint/fmpz.h>

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>

#ifndef SPARKINTERVAL_FLINT_PLATT_COMMIT
#error "the zeta shard must bind the reviewed FLINT commit"
#endif

namespace {

constexpr std::uint64_t kPlattFirstIndex = 10'000ULL;
constexpr std::uint64_t kSourceCount = 12'363'153'437'138ULL;
constexpr std::uint64_t kSourceSentinel = kSourceCount + 1ULL;
constexpr std::uint64_t kSourceHeight = 3'000'175'332'800ULL;
constexpr std::uint64_t kDefaultMicroBatch = 4096ULL;
constexpr std::uint64_t kMaxMicroBatch = 10'000'000ULL;
constexpr long kDefaultPrecision = 96;
constexpr long kMinPrecision = 32;
constexpr long kMaxPrecision = 16'384;

enum class Engine { kPlattIsolate, kPlattZetaReplay, kOrdinaryPrefix, kCount };

struct Options {
  Engine engine = Engine::kPlattIsolate;
  std::uint64_t first_index = kPlattFirstIndex;
  std::uint64_t count = 1;
  std::uint64_t micro_batch = kDefaultMicroBatch;
  std::uint64_t height = kSourceHeight;
  std::uint64_t expected_count = kSourceCount;
  long precision = kDefaultPrecision;
  long threads = 1;
};

[[noreturn]] void fail(const std::string& message) {
  std::cerr << message << '\n';
  std::exit(2);
}

bool parse_u64(std::string_view text, std::uint64_t* output) {
  if (text.empty() || text.front() == '-') return false;
  const char* first = text.data();
  const char* last = first + text.size();
  const auto result = std::from_chars(first, last, *output);
  return result.ec == std::errc{} && result.ptr == last;
}

bool parse_long(std::string_view text, long* output) {
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
    if (argument == "--engine") {
      const auto engine = value("--engine");
      if (engine == "platt-isolate") {
        options.engine = Engine::kPlattIsolate;
      } else if (engine == "platt-zeta-replay") {
        options.engine = Engine::kPlattZetaReplay;
      } else if (engine == "ordinary-prefix") {
        options.engine = Engine::kOrdinaryPrefix;
      } else if (engine == "count") {
        options.engine = Engine::kCount;
      } else {
        fail("unknown engine");
      }
    } else if (argument == "--first-index") {
      if (!parse_u64(value("--first-index"), &options.first_index)) {
        fail("--first-index must be an unsigned integer");
      }
    } else if (argument == "--count") {
      if (!parse_u64(value("--count"), &options.count)) {
        fail("--count must be an unsigned integer");
      }
    } else if (argument == "--micro-batch") {
      if (!parse_u64(value("--micro-batch"), &options.micro_batch)) {
        fail("--micro-batch must be an unsigned integer");
      }
    } else if (argument == "--height") {
      if (!parse_u64(value("--height"), &options.height)) {
        fail("--height must be an unsigned integer");
      }
    } else if (argument == "--expected-count") {
      if (!parse_u64(value("--expected-count"), &options.expected_count)) {
        fail("--expected-count must be an unsigned integer");
      }
    } else if (argument == "--precision") {
      if (!parse_long(value("--precision"), &options.precision)) {
        fail("--precision must be an integer");
      }
    } else if (argument == "--threads") {
      if (!parse_long(value("--threads"), &options.threads)) {
        fail("--threads must be an integer");
      }
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-platt-zeta-shard --engine "
             "platt-isolate|platt-zeta-replay|ordinary-prefix|count "
             "[--first-index N --count N --micro-batch N] "
             "[--height N --expected-count N] [--precision N] "
             "[--threads N]\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.precision < kMinPrecision || options.precision > kMaxPrecision) {
    fail("precision is outside the reviewed range");
  }
  if (options.threads < 1 || options.threads > 1024) {
    fail("threads is outside the reviewed range");
  }
  if (options.micro_batch < 1 || options.micro_batch > kMaxMicroBatch) {
    fail("micro-batch is outside the reviewed range");
  }
  if (options.engine == Engine::kCount) {
    if (options.height < 1) fail("count height must be positive");
    return options;
  }
  if (options.first_index < 1 || options.count < 1 ||
      options.first_index > std::numeric_limits<std::uint64_t>::max() -
                                (options.count - 1)) {
    fail("invalid index interval");
  }
  const std::uint64_t last = options.first_index + options.count - 1;
  if (options.engine == Engine::kOrdinaryPrefix) {
    if (last >= kPlattFirstIndex) {
      fail("ordinary-prefix is restricted to indices 1 through 9999");
    }
  } else if (options.first_index < kPlattFirstIndex || last > kSourceSentinel) {
    fail("Platt shard must lie in [10000, source-count+1]");
  }
  return options;
}

std::string json_escape(std::string_view text) {
  std::ostringstream output;
  for (const unsigned char character : text) {
    switch (character) {
      case '\\': output << "\\\\"; break;
      case '"': output << "\\\""; break;
      case '\b': output << "\\b"; break;
      case '\f': output << "\\f"; break;
      case '\n': output << "\\n"; break;
      case '\r': output << "\\r"; break;
      case '\t': output << "\\t"; break;
      default:
        if (character < 0x20) fail("unexpected control byte in FLINT dump");
        output << static_cast<char>(character);
    }
  }
  return output.str();
}

std::string dump_arf(const arf_t value) {
  char* raw = arf_dump_str(value);
  if (raw == nullptr) fail("arf_dump_str returned null");
  const std::string result(raw);
  flint_free(raw);
  return result;
}

std::string dump_arb(const arb_t value) {
  char* raw = arb_dump_str(value);
  if (raw == nullptr) fail("arb_dump_str returned null");
  const std::string result(raw);
  flint_free(raw);
  return result;
}

void hash_row(sparkinterval::detail::Sha256* hash, std::uint64_t index,
              std::string_view lower, std::string_view upper) {
  const std::string row = std::to_string(index) + "\t" + std::string(lower) +
                          "\t" + std::string(upper) + "\n";
  hash->update(row.data(), row.size());
}

std::string engine_name(Engine engine) {
  switch (engine) {
    case Engine::kPlattIsolate: return "flint-platt-local-isolation-v1";
    case Engine::kPlattZetaReplay: return "flint-platt-zeta-zeros-replay-v1";
    case Engine::kOrdinaryPrefix: return "flint-ordinary-prefix-v1";
    case Engine::kCount: return "flint-exact-zeta-nzeros-v1";
  }
  fail("unreachable engine");
}

void require_flint_identity() {
  if (std::strcmp(FLINT_VERSION, "3.6.0") != 0 ||
      std::strcmp(flint_version, "3.6.0") != 0 || __FLINT_RELEASE != 30600) {
    fail("compile-time or runtime FLINT is not 3.6.0");
  }
}

void print_common_tail(std::uint64_t elapsed_ms) {
  std::cout << ",\"flint_version\":\"3.6.0\""
            << ",\"flint_commit\":\"" SPARKINTERVAL_FLINT_PLATT_COMMIT "\""
            << ",\"elapsed_milliseconds\":" << elapsed_ms
            << ",\"execution_attested\":false"
            << ",\"lean_atom_discharged\":false"
            << ",\"accepted\":true}\n";
}

int run_count(const Options& options) {
  arb_t height_ball, result;
  fmpz_t actual;
  arb_init(height_ball);
  arb_init(result);
  fmpz_init(actual);
  arb_set_ui(height_ball, options.height);
  const auto begin = std::chrono::steady_clock::now();
  acb_dirichlet_zeta_nzeros(result, height_ball, options.precision);
  const auto end = std::chrono::steady_clock::now();
  if (!arb_is_finite(result) || !arb_get_unique_fmpz(actual, result) ||
      fmpz_sgn(actual) < 0) {
    fail("zeta_nzeros did not return a unique finite integer");
  }
  const char* actual_raw = fmpz_get_str(nullptr, 10, actual);
  if (actual_raw == nullptr) fail("cannot serialize zeta_nzeros result");
  const std::string actual_text(actual_raw);
  flint_free(const_cast<char*>(actual_raw));
  if (actual_text != std::to_string(options.expected_count)) {
    fail("zeta_nzeros differs from --expected-count");
  }
  const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(
      end - begin).count();
  std::cout << "{\"schema\":\"sparkinterval.tg.platt-zeta-shard.v1\""
            << ",\"engine\":\"" << engine_name(options.engine) << "\""
            << ",\"height\":" << options.height
            << ",\"multiplicity_count\":" << actual_text
            << ",\"counted_with_multiplicity\":true";
  print_common_tail(static_cast<std::uint64_t>(milliseconds));
  fmpz_clear(actual);
  arb_clear(result);
  arb_clear(height_ball);
  return 0;
}

struct StreamResult {
  std::uint64_t records = 0;
  std::uint64_t calls = 0;
  std::string first_lower;
  std::string first_upper;
  std::string last_lower;
  std::string last_upper;
  bool included_cutoff_checked = false;
  bool sentinel_cutoff_checked = false;
  std::string digest;
};

StreamResult run_platt_isolate(const Options& options) {
  StreamResult result;
  sparkinterval::detail::Sha256 hash;
  std::uint64_t current = options.first_index;
  const std::uint64_t end = current + options.count;
  arf_t previous_upper, height;
  arf_init(previous_upper);
  arf_init(height);
  arf_set_ui(height, kSourceHeight);
  bool have_previous = false;
  while (current < end) {
    const std::uint64_t requested64 =
        std::min<std::uint64_t>(options.micro_batch, end - current);
    const slong requested = static_cast<slong>(requested64);
    fmpz_t n;
    fmpz_init(n);
    fmpz_set_ui(n, current);
    arf_interval_ptr intervals = _arf_interval_vec_init(requested);
    const slong found = acb_dirichlet_platt_isolate_local_hardy_z_zeros(
        intervals, n, requested, options.precision);
    if (found < 1 || found > requested) {
      _arf_interval_vec_clear(intervals, requested);
      fmpz_clear(n);
      fail("FLINT Platt local isolation returned no usable consecutive block");
    }
    for (slong offset = 0; offset < found; ++offset) {
      const std::uint64_t index = current + static_cast<std::uint64_t>(offset);
      const arf_t lower = {intervals[offset].a};
      const arf_t upper = {intervals[offset].b};
      if (!arf_is_finite(lower) || !arf_is_finite(upper) ||
          arf_sgn(lower) <= 0 || arf_cmp(lower, upper) >= 0) {
        fail("FLINT returned a malformed Platt isolating interval");
      }
      // FLINT documents these as open intervals (a,b).  Adjacent isolations
      // may share a certified nonzero endpoint, so b == a is disjoint; only
      // b > a would overlap.
      if (have_previous && arf_cmp(previous_upper, lower) > 0) {
        fail("consecutive Platt open isolating intervals overlap");
      }
      if (index <= kSourceCount && arf_cmp(upper, height) > 0) {
        fail("an included source zero is not certified below the cutoff");
      }
      if (index == kSourceCount) result.included_cutoff_checked = true;
      if (index == kSourceSentinel) {
        if (arf_cmp(lower, height) <= 0) {
          fail("the source sentinel is not certified above the cutoff");
        }
        result.sentinel_cutoff_checked = true;
      }
      const std::string lower_dump = dump_arf(lower);
      const std::string upper_dump = dump_arf(upper);
      hash_row(&hash, index, lower_dump, upper_dump);
      if (result.records == 0) {
        result.first_lower = lower_dump;
        result.first_upper = upper_dump;
      }
      result.last_lower = lower_dump;
      result.last_upper = upper_dump;
      arf_set(previous_upper, upper);
      have_previous = true;
      ++result.records;
    }
    ++result.calls;
    current += static_cast<std::uint64_t>(found);
    _arf_interval_vec_clear(intervals, requested);
    fmpz_clear(n);
  }
  result.digest = sparkinterval::lowercase_hex(hash.finish());
  arf_clear(height);
  arf_clear(previous_upper);
  return result;
}

StreamResult run_acb_stream(const Options& options) {
  StreamResult result;
  sparkinterval::detail::Sha256 hash;
  std::uint64_t current = options.first_index;
  const std::uint64_t end = current + options.count;
  arb_t previous, half, height;
  arb_init(previous);
  arb_init(half);
  arb_init(height);
  arb_one(half);
  arb_mul_2exp_si(half, half, -1);
  arb_set_ui(height, kSourceHeight);
  bool have_previous = false;
  while (current < end) {
    const std::uint64_t requested64 =
        std::min<std::uint64_t>(options.micro_batch, end - current);
    const slong requested = static_cast<slong>(requested64);
    fmpz_t n;
    fmpz_init(n);
    fmpz_set_ui(n, current);
    acb_ptr zeros = _acb_vec_init(requested);
    slong found = requested;
    if (options.engine == Engine::kPlattZetaReplay) {
      found = acb_dirichlet_platt_zeta_zeros(
          zeros, n, requested, options.precision);
    } else {
      acb_dirichlet_zeta_zeros(zeros, n, requested, options.precision);
    }
    if (found < 1 || found > requested) {
      _acb_vec_clear(zeros, requested);
      fmpz_clear(n);
      fail("FLINT returned no usable consecutive zeta-zero block");
    }
    for (slong offset = 0; offset < found; ++offset) {
      const std::uint64_t index = current + static_cast<std::uint64_t>(offset);
      const acb_t zero = {zeros[offset]};
      const arb_t real = {zeros[offset].real};
      const arb_t imag = {zeros[offset].imag};
      if (!acb_is_finite(zero) || !arb_equal(real, half) ||
          !arb_is_positive(imag)) {
        fail("FLINT zeta zero is not a positive finite critical-line ball");
      }
      if (have_previous && !arb_lt(previous, imag)) {
        fail("consecutive zeta-zero balls are not strictly disjoint");
      }
      if (index <= kSourceCount && !arb_le(imag, height)) {
        fail("an included source zero is not certified below the cutoff");
      }
      if (index == kSourceCount) result.included_cutoff_checked = true;
      if (index == kSourceSentinel) {
        if (!arb_gt(imag, height)) {
          fail("the source sentinel is not certified above the cutoff");
        }
        result.sentinel_cutoff_checked = true;
      }
      const std::string ball = dump_arb(imag);
      hash_row(&hash, index, ball, ball);
      if (result.records == 0) {
        result.first_lower = ball;
        result.first_upper = ball;
      }
      result.last_lower = ball;
      result.last_upper = ball;
      arb_set(previous, imag);
      have_previous = true;
      ++result.records;
    }
    ++result.calls;
    current += static_cast<std::uint64_t>(found);
    _acb_vec_clear(zeros, requested);
    fmpz_clear(n);
  }
  result.digest = sparkinterval::lowercase_hex(hash.finish());
  arb_clear(height);
  arb_clear(half);
  arb_clear(previous);
  return result;
}

int run_stream(const Options& options) {
  const auto begin = std::chrono::steady_clock::now();
  StreamResult result = options.engine == Engine::kPlattIsolate
                            ? run_platt_isolate(options)
                            : run_acb_stream(options);
  const auto end = std::chrono::steady_clock::now();
  if (result.records != options.count) fail("record-count invariant failed");
  const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(
      end - begin).count();
  const std::uint64_t last = options.first_index + options.count - 1;
  std::cout << "{\"schema\":\"sparkinterval.tg.platt-zeta-shard.v1\""
            << ",\"engine\":\"" << engine_name(options.engine) << "\""
            << ",\"first_index\":" << options.first_index
            << ",\"last_index\":" << last
            << ",\"record_count\":" << result.records
            << ",\"micro_batch\":" << options.micro_batch
            << ",\"flint_calls\":" << result.calls
            << ",\"precision_bits\":" << options.precision
            << ",\"flint_threads\":" << options.threads
            << ",\"interval_encoding\":\"flint-3.6-dump-str\""
            << ",\"interval_rows_sha256\":\"" << result.digest << "\""
            << ",\"first_lower\":\"" << json_escape(result.first_lower) << "\""
            << ",\"first_upper\":\"" << json_escape(result.first_upper) << "\""
            << ",\"last_lower\":\"" << json_escape(result.last_lower) << "\""
            << ",\"last_upper\":\"" << json_escape(result.last_upper) << "\""
            << ",\"positive_finite_disjoint_open_intervals\":true"
            << ",\"critical_line_certified\":true"
            << ",\"counted_with_multiplicity\":true"
            << ",\"simplicity_assumed\":false"
            << ",\"included_cutoff_checked\":"
            << (result.included_cutoff_checked ? "true" : "false")
            << ",\"sentinel_cutoff_checked\":"
            << (result.sentinel_cutoff_checked ? "true" : "false");
  print_common_tail(static_cast<std::uint64_t>(milliseconds));
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  require_flint_identity();
  flint_set_num_threads(options.threads);
  const int status = options.engine == Engine::kCount ? run_count(options)
                                                       : run_stream(options);
  flint_cleanup_master();
  return status;
}

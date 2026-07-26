// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_mobius_segment.h"

#include "sparkinterval/sha256.hpp"

#include <array>
#include <algorithm>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

constexpr std::uint64_t kSourceLimit = 10'000'000'000'000'000ULL;
constexpr std::uint64_t kDefaultCount = 65'536;
constexpr std::uint64_t kMaximumSegmentCount = 100'000'000;
constexpr std::size_t kSourcePrimeRosterCount = 5'761'455;
constexpr std::size_t kSourcePrimeRosterBytes =
    kSourcePrimeRosterCount * sizeof(std::uint32_t);
constexpr std::uint32_t kSourcePrimeRosterLast = 99'999'989;
constexpr std::string_view kSourcePrimeRosterSha256 =
    "0feea6e7805b8bae663ecadd180f8ea94061ff0b16d6f9da2472fbe2e6d5cbb5";
constexpr std::uint64_t kLittleMertens211Limit = 1'000'000'000'000ULL;
constexpr std::uint64_t kLittleMertensStrongerLower = 3;
constexpr std::uint64_t kLittleMertensStrongerLimit = 7'727'068'587ULL;
constexpr unsigned int kLittleMertensScaleBits = 96;
constexpr unsigned __int128 kLittleMertensScale =
    static_cast<unsigned __int128>(1) << kLittleMertensScaleBits;
constexpr std::string_view kZeroDigest =
    "0000000000000000000000000000000000000000000000000000000000000000";

// This deliberately coarse rational interval contains the tighter Machin
// enclosure used by tg_verifier.arithmetic:
//
//   607927101854026628 / 10^18
//       <= 6/pi^2 <=
//   607927101854026629 / 10^18.
//
// The Python tests establish those two comparisons with exact Fractions.
constexpr std::uint64_t kDensityDenominator = 1'000'000'000'000'000'000ULL;
constexpr std::uint64_t kDensityLowerNumerator = 607'927'101'854'026'628ULL;
constexpr std::uint64_t kDensityUpperNumerator = 607'927'101'854'026'629ULL;
constexpr std::string_view kDensityIntervalId =
    "machin_20_6_coarsened_1e18_v1";
constexpr std::string_view kResidue235711QualificationAlgorithm =
    "tg_mobius_compact_mu_residue_235711_qualification_v1";
constexpr std::string_view kResidue235711QualificationClassification =
    "qualification_only_residue_235711_not_full_support_receipt_or_proof";

std::string_view rectangular_mode_name(
    TgMobiusRectangularSlotMode mode) {
  switch (mode) {
    case TgMobiusRectangularSlotMode::kRect2d512:
      return "rect2d512";
    case TgMobiusRectangularSlotMode::kRect2dPower:
      return "rect2dPower";
    case TgMobiusRectangularSlotMode::kRect2dExact:
      return "rect2dExact";
    case TgMobiusRectangularSlotMode::kRect2dCountExact:
      return "rect2dCountExact";
  }
  return "invalid";
}

std::string_view residue_seed_name(TgMobiusResidueSeed seed) {
  switch (seed) {
    case TgMobiusResidueSeed::k235:
      return "235";
    case TgMobiusResidueSeed::k2357:
      return "2357";
    case TgMobiusResidueSeed::k235711:
      return "235711";
    case TgMobiusResidueSeed::k23571113:
      return "23571113";
  }
  return "invalid";
}

struct Options {
  std::uint64_t lower = 1;
  std::uint64_t count = kDefaultCount;
  std::int64_t incoming_mertens = 0;
  std::uint64_t incoming_squarefree = 0;
  signed __int128 incoming_little_mertens_lower = 0;
  signed __int128 incoming_little_mertens_upper = 0;
  std::string previous_receipt_sha256{kZeroDigest};
  bool incoming_mertens_given = false;
  bool incoming_squarefree_given = false;
  bool incoming_little_mertens_lower_given = false;
  bool incoming_little_mertens_upper_given = false;
  bool previous_digest_given = false;
  int device = 0;
  bool allow_other_device = false;
  bool qualification_use_all_device_primes = false;
  std::uint32_t qualification_omit_device_prime = 0;
  std::string source_prime_roster;
  bool compact_mu_output = false;
  bool affine_mq_gpu_prototype = false;
  bool compact_support_kernel = false;
  bool qualification_transfer_compact_support = false;
  bool fused_support_kernel = false;
  bool qualification_legacy_one_block_dense = false;
  bool qualification_unseeded_fused_initializer = false;
  bool qualification_residue_2357_seed = false;
  bool qualification_residue_235711_seed = false;
  bool qualification_residue_rectangular = false;
  TgMobiusRectangularSlotMode qualification_rectangular_mode =
      TgMobiusRectangularSlotMode::kRect2d512;
  bool qualification_transfer_fused_support = false;
  std::string qualification_write_mu;
};

struct U256 {
  std::array<std::uint64_t, 4> limb{};
};

struct EndpointProblem {
  bool present = false;
  std::uint64_t interval_n = 0;
  const char* side = "";
  std::uint64_t y = 0;
};

struct LittleMertensProblem {
  bool present = false;
  std::uint64_t interval_floor = 0;
  std::uint64_t right_endpoint = 0;
};

[[noreturn]] void fail(const std::string& message, int code = 2) {
  std::cerr << message << '\n';
  std::exit(code);
}

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  fail(std::string(operation) + " failed: " + cudaGetErrorString(status), 3);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) fail_cuda(operation, status);
}

bool parse_u64(std::string_view text, std::uint64_t* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

bool parse_i64(std::string_view text, std::int64_t* result) {
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *result);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

bool parse_i128(std::string_view text, signed __int128* result) {
  if (text.empty()) return false;
  bool negative = false;
  std::size_t offset = 0;
  if (text.front() == '-') {
    negative = true;
    offset = 1;
  }
  if (offset == text.size()) return false;
  const unsigned __int128 negative_limit =
      static_cast<unsigned __int128>(1) << 127U;
  const unsigned __int128 positive_limit = negative_limit - 1;
  const unsigned __int128 limit = negative ? negative_limit : positive_limit;
  unsigned __int128 magnitude = 0;
  for (; offset < text.size(); ++offset) {
    const char digit_character = text[offset];
    if (digit_character < '0' || digit_character > '9') return false;
    const unsigned int digit =
        static_cast<unsigned int>(digit_character - '0');
    if (magnitude > (limit - digit) / 10U) return false;
    magnitude = magnitude * 10U + digit;
  }
  if (!negative) {
    *result = static_cast<signed __int128>(magnitude);
  } else if (magnitude == negative_limit) {
    *result = -static_cast<signed __int128>(negative_limit - 1) - 1;
  } else {
    *result = -static_cast<signed __int128>(magnitude);
  }
  return true;
}

bool is_digest(std::string_view text) {
  if (text.size() != 64) return false;
  for (const char character : text) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--lower") {
      if (!parse_u64(require_value("--lower"), &options.lower)) {
        fail("--lower must be a nonnegative integer");
      }
    } else if (argument == "--count") {
      if (!parse_u64(require_value("--count"), &options.count)) {
        fail("--count must be a nonnegative integer");
      }
    } else if (argument == "--incoming-mertens") {
      if (!parse_i64(require_value("--incoming-mertens"),
                     &options.incoming_mertens)) {
        fail("--incoming-mertens must be a signed 64-bit integer");
      }
      options.incoming_mertens_given = true;
    } else if (argument == "--incoming-squarefree") {
      if (!parse_u64(require_value("--incoming-squarefree"),
                     &options.incoming_squarefree)) {
        fail("--incoming-squarefree must be a nonnegative integer");
      }
      options.incoming_squarefree_given = true;
    } else if (argument == "--incoming-little-mertens-lower") {
      if (!parse_i128(require_value("--incoming-little-mertens-lower"),
                      &options.incoming_little_mertens_lower)) {
        fail("--incoming-little-mertens-lower must be a signed 128-bit integer");
      }
      options.incoming_little_mertens_lower_given = true;
    } else if (argument == "--incoming-little-mertens-upper") {
      if (!parse_i128(require_value("--incoming-little-mertens-upper"),
                      &options.incoming_little_mertens_upper)) {
        fail("--incoming-little-mertens-upper must be a signed 128-bit integer");
      }
      options.incoming_little_mertens_upper_given = true;
    } else if (argument == "--previous-receipt-sha256") {
      options.previous_receipt_sha256 =
          std::string(require_value("--previous-receipt-sha256"));
      if (!is_digest(options.previous_receipt_sha256)) {
        fail("--previous-receipt-sha256 must be 64 lowercase hexadecimal characters");
      }
      options.previous_digest_given = true;
    } else if (argument == "--device") {
      std::uint64_t parsed = 0;
      if (!parse_u64(require_value("--device"), &parsed) ||
          parsed > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
        fail("--device must be a nonnegative integer");
      }
      options.device = static_cast<int>(parsed);
    } else if (argument == "--allow-other-device") {
      options.allow_other_device = true;
    } else if (argument == "--qualification-use-all-device-primes") {
      options.qualification_use_all_device_primes = true;
    } else if (argument == "--qualification-omit-device-prime") {
      std::uint64_t parsed = 0;
      if (!parse_u64(require_value("--qualification-omit-device-prime"),
                     &parsed) ||
          parsed < 2 ||
          parsed > std::numeric_limits<std::uint32_t>::max()) {
        fail("--qualification-omit-device-prime must be a 32-bit prime");
      }
      options.qualification_omit_device_prime =
          static_cast<std::uint32_t>(parsed);
    } else if (argument == "--source-prime-roster") {
      options.source_prime_roster =
          std::string(require_value("--source-prime-roster"));
      if (options.source_prime_roster.empty()) {
        fail("--source-prime-roster must not be empty");
      }
    } else if (argument == "--compact-mu-output") {
      options.compact_mu_output = true;
    } else if (argument == "--affine-mq-gpu-prototype") {
      options.affine_mq_gpu_prototype = true;
    } else if (argument == "--compact-support-kernel") {
      options.compact_support_kernel = true;
    } else if (argument == "--qualification-transfer-compact-support") {
      options.qualification_transfer_compact_support = true;
    } else if (argument == "--fused-support-kernel") {
      options.fused_support_kernel = true;
    } else if (argument == "--qualification-legacy-one-block-dense") {
      options.qualification_legacy_one_block_dense = true;
    } else if (argument ==
               "--qualification-unseeded-fused-initializer") {
      options.qualification_unseeded_fused_initializer = true;
    } else if (argument == "--qualification-residue-2357-seed") {
      options.qualification_residue_2357_seed = true;
    } else if (argument == "--qualification-residue-235711-seed") {
      options.qualification_residue_235711_seed = true;
    } else if (argument == "--qualification-residue-rectangular") {
      const std::string_view mode =
          require_value("--qualification-residue-rectangular");
      if (mode == "rect2d512") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2d512;
      } else if (mode == "rect2dPower") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2dPower;
      } else if (mode == "rect2dExact") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2dExact;
      } else if (mode == "rect2dCountExact") {
        options.qualification_rectangular_mode =
            TgMobiusRectangularSlotMode::kRect2dCountExact;
      } else {
        fail("--qualification-residue-rectangular must be rect2d512, "
             "rect2dPower, rect2dExact, or rect2dCountExact");
      }
      options.qualification_residue_rectangular = true;
    } else if (argument == "--qualification-transfer-fused-support") {
      options.qualification_transfer_fused_support = true;
    } else if (argument == "--qualification-write-mu") {
      options.qualification_write_mu =
          std::string(require_value("--qualification-write-mu"));
      if (options.qualification_write_mu.empty()) {
        fail("--qualification-write-mu must not be empty");
      }
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-mobius-segment "
             "[--lower N] [--count N] [--incoming-mertens M] "
             "[--incoming-squarefree Q] "
             "[--incoming-little-mertens-lower L] "
             "[--incoming-little-mertens-upper U] "
             "[--previous-receipt-sha256 HEX] [--device N] "
             "[--allow-other-device] "
             "[--qualification-use-all-device-primes] "
             "[--qualification-omit-device-prime P] "
             "[--source-prime-roster FILE] [--compact-mu-output] "
             "[--affine-mq-gpu-prototype] [--compact-support-kernel] "
             "[--qualification-transfer-compact-support] "
             "[--fused-support-kernel] "
             "[--qualification-legacy-one-block-dense] "
             "[--qualification-unseeded-fused-initializer] "
             "[--qualification-residue-2357-seed] "
             "[--qualification-residue-235711-seed] "
             "[--qualification-residue-rectangular "
             "rect2d512|rect2dPower|rect2dExact|rect2dCountExact] "
             "[--qualification-transfer-fused-support] "
             "[--qualification-write-mu FILE]\n"
             "Computes one exact bounded Moebius segment, independently "
             "checks every GPU record on the CPU, and emits a hash-linked "
             "state transition. The qualification-only all-primes switch "
             "disables the semantics-preserving active-prime device filter; "
             "the qualification-only omission switch deliberately corrupts "
             "the device input and must make the independent oracle fail. "
             "The optional source roster is the canonical authenticated "
             "little-endian prime table through 10^8. Compact output copies "
             "one mathematical Moebius byte per row and is deliberately not "
             "a full-support receipt. The terminal affine MQ prototype "
             "requires compact output and covers neither little-Mertens "
             "component. The compact-support kernel uses 16 bytes per device "
             "row and writes mu directly; its qualification switch transfers "
             "those fields for exact differential checking. "
             "The fused-support kernel uses one guarded 64-bit "
             "CAS word per row; its qualification switch transfers and "
             "decodes every field against the independent oracle. "
             "Its default load-balanced schedule partitions multiple "
             "ordinals for the first 200 dense primes across disjoint "
             "blocks. The qualification-only legacy switch restores the "
             "one-block-per-dense-prime schedule. "
             "The default fused initializer seeds exact 2/3/5 support from "
             "n modulo 900 and skips those three event passes after "
             "validating the device roster prefix. The qualification-only "
             "unseeded switch restores the plain-one initializer. The "
             "qualification-only residue-2357 switch derives the exact p=7 "
             "seed contribution from n modulo 49, requires [2,3,5,7], and "
             "uses the separate split-square candidate API. The distinct "
             "qualification-only residue-235711 switch additionally derives "
             "p=11 from n modulo 121, requires [2,3,5,7,11], and preserves "
             "the p=7 candidate's 512-slot launch geometry. The rectangular "
             "switch selects a separately identified 2D qualification grid "
             "for the chosen seed (default 235), and binds its realized "
             "geometry in the receipt. "
             "The qualification-only mu writer emits the exact signed-byte "
             "GPU row stream for cross-run metamorphic tests. "
             "Non-root segments require all four prefix state arguments plus "
             "the previous receipt digest.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.lower < 1 || options.lower > kSourceLimit) {
    fail("--lower must lie in [1, 10000000000000000]");
  }
  if (options.count < 1 || options.count > kMaximumSegmentCount) {
    fail("--count must lie in [1, 100000000]");
  }
  if (options.count - 1 > kSourceLimit - options.lower) {
    fail("requested segment exceeds the bounded source range through 10^16");
  }
  if (options.lower == 1) {
    if (options.incoming_mertens != 0 ||
        options.incoming_squarefree != 0 ||
        options.incoming_little_mertens_lower != 0 ||
        options.incoming_little_mertens_upper != 0 ||
        options.previous_receipt_sha256 != kZeroDigest) {
      fail("a root segment must have zero incoming state and the zero previous digest");
    }
  } else if (!(options.incoming_mertens_given &&
               options.incoming_squarefree_given &&
               options.incoming_little_mertens_lower_given &&
               options.incoming_little_mertens_upper_given &&
               options.previous_digest_given)) {
    fail("a non-root segment requires incoming Mertens, squarefree, little-Mertens interval, and previous-digest state");
  } else if (options.previous_receipt_sha256 == kZeroDigest) {
    fail("a non-root segment requires a nonzero previous receipt digest");
  }
  const std::uint64_t prior_rows = options.lower - 1;
  if (options.incoming_mertens < -static_cast<std::int64_t>(prior_rows) ||
      options.incoming_mertens > static_cast<std::int64_t>(prior_rows)) {
    fail("incoming Mertens state exceeds the elementary prefix range");
  }
  if (options.incoming_squarefree > prior_rows) {
    fail("incoming squarefree state exceeds the prefix length");
  }
  if (options.incoming_little_mertens_lower >
      options.incoming_little_mertens_upper) {
    fail("incoming little-Mertens interval is reversed");
  }
  if (options.affine_mq_gpu_prototype &&
      (!options.compact_mu_output ||
       options.lower <= kLittleMertens211Limit)) {
    fail("--affine-mq-gpu-prototype requires compact output wholly above 10^12");
  }
  if (options.compact_support_kernel && !options.compact_mu_output) {
    fail("--compact-support-kernel requires --compact-mu-output");
  }
  if (options.qualification_transfer_compact_support &&
      !options.compact_support_kernel) {
    fail("--qualification-transfer-compact-support requires the compact-support kernel");
  }
  if (options.fused_support_kernel && !options.compact_mu_output) {
    fail("--fused-support-kernel requires --compact-mu-output");
  }
  if (options.qualification_legacy_one_block_dense &&
      !options.fused_support_kernel) {
    fail("--qualification-legacy-one-block-dense requires "
         "--fused-support-kernel");
  }
  if (options.qualification_unseeded_fused_initializer &&
      !options.fused_support_kernel) {
    fail("--qualification-unseeded-fused-initializer requires "
         "--fused-support-kernel");
  }
  if (options.qualification_unseeded_fused_initializer &&
      options.qualification_legacy_one_block_dense) {
    fail("--qualification-unseeded-fused-initializer and "
         "--qualification-legacy-one-block-dense are mutually exclusive");
  }
  if (options.qualification_residue_2357_seed &&
      !options.fused_support_kernel) {
    fail("--qualification-residue-2357-seed requires "
         "--fused-support-kernel");
  }
  if (options.qualification_residue_2357_seed &&
      (options.qualification_unseeded_fused_initializer ||
       options.qualification_legacy_one_block_dense ||
       options.qualification_residue_235711_seed)) {
    fail("--qualification-residue-2357-seed is mutually exclusive with "
         "the residue-235711, unseeded, and legacy fused qualification paths");
  }
  if (options.qualification_residue_235711_seed &&
      !options.fused_support_kernel) {
    fail("--qualification-residue-235711-seed requires "
         "--fused-support-kernel");
  }
  if (options.qualification_residue_235711_seed &&
      (options.qualification_unseeded_fused_initializer ||
       options.qualification_legacy_one_block_dense)) {
    fail("--qualification-residue-235711-seed is mutually exclusive with "
         "the unseeded and legacy fused qualification paths");
  }
  if (options.qualification_residue_rectangular &&
      !options.fused_support_kernel) {
    fail("--qualification-residue-rectangular requires "
         "--fused-support-kernel");
  }
  if (options.qualification_residue_rectangular &&
      (options.qualification_unseeded_fused_initializer ||
       options.qualification_legacy_one_block_dense)) {
    fail("--qualification-residue-rectangular is mutually exclusive with "
         "the unseeded and legacy fused qualification paths");
  }
  if (options.compact_support_kernel && options.fused_support_kernel) {
    fail("compact-support and fused-support kernels are mutually exclusive");
  }
  if (options.qualification_transfer_fused_support &&
      !options.fused_support_kernel) {
    fail("--qualification-transfer-fused-support requires the fused-support kernel");
  }
  if (!options.qualification_write_mu.empty() &&
      !options.compact_mu_output) {
    fail("--qualification-write-mu requires --compact-mu-output");
  }
  if (options.qualification_transfer_compact_support &&
      options.qualification_transfer_fused_support) {
    fail("compact-support and fused-support qualification transfers are mutually exclusive");
  }
  return options;
}

std::uint64_t integer_square_root(std::uint64_t value) {
  std::uint64_t lower = 0;
  std::uint64_t upper = 100'000'001;
  while (lower + 1 < upper) {
    const std::uint64_t middle = lower + (upper - lower) / 2;
    if (middle <= value / middle) {
      lower = middle;
    } else {
      upper = middle;
    }
  }
  return lower;
}

std::vector<std::uint32_t> exact_primes_upto(std::uint64_t limit64) {
  if (limit64 < 2) return {};
  if (limit64 > 100'000'000) fail("internal base-prime limit exceeded");
  const auto limit = static_cast<std::uint32_t>(limit64);
  std::vector<bool> composite(static_cast<std::size_t>(limit) + 1, false);
  for (std::uint32_t prime = 2; prime <= limit / prime; ++prime) {
    if (composite[prime]) continue;
    for (std::uint64_t multiple =
             static_cast<std::uint64_t>(prime) * prime;
         multiple <= limit; multiple += prime) {
      composite[static_cast<std::size_t>(multiple)] = true;
    }
  }
  std::vector<std::uint32_t> primes;
  for (std::uint32_t candidate = 2; candidate <= limit; ++candidate) {
    if (!composite[candidate]) primes.push_back(candidate);
  }
  return primes;
}

std::vector<std::uint32_t> load_source_prime_roster(const std::string& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) fail("could not open the source prime roster");
  const std::streampos end = input.tellg();
  if (end < 0 ||
      static_cast<std::uint64_t>(end) != kSourcePrimeRosterBytes) {
    fail("source prime roster has the wrong byte length");
  }
  input.seekg(0);
  std::vector<unsigned char> bytes(kSourcePrimeRosterBytes);
  input.read(reinterpret_cast<char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  if (!input || input.peek() != std::ifstream::traits_type::eof()) {
    fail("source prime roster could not be read exactly");
  }
  if (sparkinterval::sha256_hex(bytes.data(), bytes.size()) !=
      kSourcePrimeRosterSha256) {
    fail("source prime roster SHA-256 does not match the compiled pin");
  }
  std::vector<std::uint32_t> primes(kSourcePrimeRosterCount);
  for (std::size_t index = 0; index < primes.size(); ++index) {
    const unsigned char* encoded = bytes.data() + 4 * index;
    primes[index] = static_cast<std::uint32_t>(encoded[0]) |
                    (static_cast<std::uint32_t>(encoded[1]) << 8U) |
                    (static_cast<std::uint32_t>(encoded[2]) << 16U) |
                    (static_cast<std::uint32_t>(encoded[3]) << 24U);
    if ((index == 0 && primes[index] != 2) ||
        (index != 0 && primes[index - 1] >= primes[index])) {
      fail("source prime roster ordering is malformed");
    }
  }
  if (primes.back() != kSourcePrimeRosterLast) {
    fail("source prime roster endpoint is malformed");
  }
  return primes;
}

std::vector<std::uint32_t> primes_hitting_segment(
    std::uint64_t lower, std::size_t count,
    const std::vector<std::uint32_t>& primes,
    std::size_t retained_seed_prime_count = 0) {
  std::vector<std::uint32_t> active;
  active.reserve(std::min(primes.size(), count));
  for (std::size_t index = 0; index < primes.size(); ++index) {
    const std::uint32_t prime32 = primes[index];
    const std::uint64_t prime = prime32;
    const std::uint64_t remainder = lower % prime;
    const std::uint64_t first_offset =
        remainder == 0 ? 0 : prime - remainder;
    if (index < retained_seed_prime_count ||
        first_offset < count) {
      active.push_back(prime32);
    }
  }
  return active;
}

void independently_sieve(std::uint64_t lower,
                         const std::vector<std::uint32_t>& primes,
                         std::vector<TgMobiusSupport>* records) {
  for (TgMobiusSupport& record : *records) {
    record = TgMobiusSupport{1, 0, 0, 0, 0};
  }
  for (const std::uint32_t prime32 : primes) {
    const std::uint64_t prime = prime32;
    const std::uint64_t remainder = lower % prime;
    const std::uint64_t first_offset = remainder == 0 ? 0 : prime - remainder;
    for (std::uint64_t offset = first_offset; offset < records->size();
         offset += prime) {
      TgMobiusSupport& record = (*records)[offset];
      record.base_prime_product *= prime;
      ++record.distinct_base_prime_count;
      const std::uint64_t number = lower + offset;
      if ((number / prime) % prime == 0) record.squareful = 1;
    }
  }
  for (std::size_t index = 0; index < records->size(); ++index) {
    TgMobiusSupport& record = (*records)[index];
    const std::uint64_t number = lower + index;
    if (record.squareful != 0) {
      record.mobius = 0;
    } else {
      const std::uint64_t residual = number / record.base_prime_product;
      const std::uint32_t omega = record.distinct_base_prime_count +
                                  static_cast<std::uint32_t>(residual > 1);
      record.mobius = (omega & 1U) == 0 ? 1 : -1;
    }
  }
}

bool same_record(const TgMobiusSupport& left,
                 const TgMobiusSupport& right) {
  return left.base_prime_product == right.base_prime_product &&
         left.distinct_base_prime_count == right.distinct_base_prime_count &&
         left.squareful == right.squareful && left.mobius == right.mobius &&
         left.reserved == right.reserved;
}

void store_u32_le(unsigned char* destination, std::uint32_t value) {
  for (unsigned int index = 0; index < 4; ++index) {
    destination[index] =
        static_cast<unsigned char>(value >> (8U * index));
  }
}

void store_u64_le(unsigned char* destination, std::uint64_t value) {
  for (unsigned int index = 0; index < 8; ++index) {
    destination[index] =
        static_cast<unsigned char>(value >> (8U * index));
  }
}

void hash_u64_be(sparkinterval::detail::Sha256* hasher,
                 std::uint64_t value) {
  std::array<unsigned char, 8> bytes{};
  for (unsigned int index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<unsigned char>(value >> (56U - 8U * index));
  }
  hasher->update(bytes.data(), bytes.size());
}

std::string hash_records_le(const std::vector<TgMobiusSupport>& records) {
  constexpr std::size_t kRecordBytes = 24;
  constexpr std::size_t kRecordsPerBuffer = 4096;
  std::array<unsigned char, kRecordBytes * kRecordsPerBuffer> bytes{};
  sparkinterval::detail::Sha256 hasher;
  for (std::size_t offset = 0; offset < records.size();
       offset += kRecordsPerBuffer) {
    const std::size_t block_size =
        std::min(kRecordsPerBuffer, records.size() - offset);
    for (std::size_t index = 0; index < block_size; ++index) {
      const TgMobiusSupport& record = records[offset + index];
      unsigned char* destination = bytes.data() + kRecordBytes * index;
      store_u64_le(destination, record.base_prime_product);
      store_u32_le(destination + 8, record.distinct_base_prime_count);
      store_u32_le(destination + 12, record.squareful);
      store_u32_le(destination + 16,
                   static_cast<std::uint32_t>(record.mobius));
      store_u32_le(destination + 20, record.reserved);
    }
    hasher.update(bytes.data(), block_size * kRecordBytes);
  }
  return sparkinterval::lowercase_hex(hasher.finish());
}

U256 multiply_u128(unsigned __int128 left, unsigned __int128 right) {
  const std::array<std::uint64_t, 2> a = {
      static_cast<std::uint64_t>(left),
      static_cast<std::uint64_t>(left >> 64U)};
  const std::array<std::uint64_t, 2> b = {
      static_cast<std::uint64_t>(right),
      static_cast<std::uint64_t>(right >> 64U)};
  U256 result{};
  for (std::size_t i = 0; i < 2; ++i) {
    unsigned __int128 carry = 0;
    for (std::size_t j = 0; j < 2; ++j) {
      const unsigned __int128 value =
          static_cast<unsigned __int128>(a[i]) * b[j] +
          result.limb[i + j] + carry;
      result.limb[i + j] = static_cast<std::uint64_t>(value);
      carry = value >> 64U;
    }
    result.limb[i + 2] += static_cast<std::uint64_t>(carry);
  }
  return result;
}

U256 multiply_u64(U256 value, std::uint64_t factor) {
  unsigned __int128 carry = 0;
  for (std::uint64_t& limb : value.limb) {
    const unsigned __int128 product =
        static_cast<unsigned __int128>(limb) * factor + carry;
    limb = static_cast<std::uint64_t>(product);
    carry = product >> 64U;
  }
  if (carry != 0) fail("internal 256-bit comparison overflow");
  return value;
}

bool less_equal(const U256& left, const U256& right) {
  for (std::size_t index = left.limb.size(); index-- > 0;) {
    if (left.limb[index] != right.limb[index]) {
      return left.limb[index] < right.limb[index];
    }
  }
  return true;
}

signed __int128 i128_maximum() {
  return static_cast<signed __int128>(
      (static_cast<unsigned __int128>(1) << 127U) - 1);
}

signed __int128 i128_minimum() {
  return -i128_maximum() - 1;
}

signed __int128 checked_add_i128(signed __int128 left,
                                 signed __int128 right,
                                 const char* label) {
  if ((right > 0 && left > i128_maximum() - right) ||
      (right < 0 && left < i128_minimum() - right)) {
    fail(std::string(label) + " overflowed signed 128-bit state", 6);
  }
  return left + right;
}

unsigned __int128 absolute_i128(signed __int128 value) {
  return value < 0
      ? static_cast<unsigned __int128>(-(value + 1)) + 1
      : static_cast<unsigned __int128>(value);
}

void add_directed_reciprocal(std::uint64_t n, std::int32_t mu,
                             signed __int128* lower,
                             signed __int128* upper,
                             signed __int128* lower_delta,
                             signed __int128* upper_delta) {
  if (mu == 0) return;
  const unsigned __int128 quotient = kLittleMertensScale / n;
  const bool has_remainder = kLittleMertensScale % n != 0;
  const signed __int128 rounded_down =
      static_cast<signed __int128>(quotient);
  const signed __int128 rounded_up = static_cast<signed __int128>(
      quotient + static_cast<unsigned int>(has_remainder));
  const signed __int128 lower_increment = mu > 0 ? rounded_down : -rounded_up;
  const signed __int128 upper_increment = mu > 0 ? rounded_up : -rounded_down;
  *lower = checked_add_i128(*lower, lower_increment,
                            "little-Mertens lower endpoint");
  *upper = checked_add_i128(*upper, upper_increment,
                            "little-Mertens upper endpoint");
  *lower_delta = checked_add_i128(*lower_delta, lower_increment,
                                  "little-Mertens lower delta");
  *upper_delta = checked_add_i128(*upper_delta, upper_increment,
                                  "little-Mertens upper delta");
  if (*lower > *upper) fail("little-Mertens interval invariant failed", 6);
}

unsigned __int128 little_mertens_absolute_numerator(
    signed __int128 lower, signed __int128 upper) {
  const unsigned __int128 lower_absolute = absolute_i128(lower);
  const unsigned __int128 upper_absolute = absolute_i128(upper);
  return std::max(lower_absolute, upper_absolute);
}

bool little_mertens_endpoint_safe(signed __int128 lower,
                                  signed __int128 upper,
                                  std::uint64_t right_endpoint,
                                  bool stronger_bound) {
  // [lower/S, upper/S] encloses sum mu(n)/n.  Squaring the larger absolute
  // endpoint proves either r*s^2 <= 2 or 4*r*s^2 <= 1, with no floating
  // square root in the decision path.
  const unsigned __int128 absolute =
      little_mertens_absolute_numerator(lower, upper);
  U256 lhs = multiply_u64(multiply_u128(absolute, absolute), right_endpoint);
  U256 rhs = multiply_u128(kLittleMertensScale, kLittleMertensScale);
  if (stronger_bound) {
    lhs = multiply_u64(lhs, 4);
  } else {
    rhs = multiply_u64(rhs, 2);
  }
  return less_equal(lhs, rhs);
}

bool density_endpoint_safe(std::uint64_t squarefree_count, std::uint64_t y,
                           std::uint64_t density_numerator,
                           std::uint64_t bound_numerator,
                           std::uint64_t bound_denominator) {
  const unsigned __int128 scaled_count =
      static_cast<unsigned __int128>(squarefree_count) *
      kDensityDenominator;
  const unsigned __int128 scaled_main =
      static_cast<unsigned __int128>(density_numerator) * y;
  const unsigned __int128 difference =
      scaled_count >= scaled_main ? scaled_count - scaled_main
                                  : scaled_main - scaled_count;
  const unsigned __int128 lhs_factor = difference * bound_denominator;
  const unsigned __int128 rhs_factor =
      static_cast<unsigned __int128>(kDensityDenominator) * bound_numerator;
  const U256 lhs = multiply_u128(lhs_factor, lhs_factor);
  const U256 rhs = multiply_u64(multiply_u128(rhs_factor, rhs_factor), y);
  return less_equal(lhs, rhs);
}

bool squarefree_endpoint_safe(std::uint64_t squarefree_count,
                              std::uint64_t y,
                              std::uint64_t bound_numerator,
                              std::uint64_t bound_denominator) {
  return density_endpoint_safe(squarefree_count, y,
                               kDensityLowerNumerator, bound_numerator,
                               bound_denominator) &&
         density_endpoint_safe(squarefree_count, y,
                               kDensityUpperNumerator, bound_numerator,
                               bound_denominator);
}

struct AffineMqHostBound {
  std::int64_t value = 0;
  std::uint64_t witness_y = 0;
  std::uint64_t order = 0;
};

struct AffineMqHostSummary {
  bool present = false;
  TgMobiusPrefixMQ delta{};
  AffineMqHostBound hurst_lower{};
  AffineMqHostBound hurst_upper{};
  AffineMqHostBound squarefree_lower{};
  AffineMqHostBound squarefree_upper{};
};

std::uint64_t affine_candidate_witness_y(
    std::uint64_t lower,
    std::size_t leaf_count,
    const TgMobiusAffineMqBoundCandidate& candidate) {
  const std::uint64_t row_offset = candidate.order >> 1U;
  const std::uint64_t endpoint = candidate.order & 1U;
  if (row_offset >= leaf_count ||
      row_offset + endpoint > kSourceLimit - lower) {
    fail("affine MQ candidate order is outside the source shard");
  }
  return lower + row_offset + endpoint;
}

bool is_empty_affine_max_candidate(
    const TgMobiusAffineMqBoundCandidate& candidate) {
  return candidate.value == std::numeric_limits<std::int64_t>::min() &&
         candidate.local_squarefree == 0 &&
         candidate.order == std::numeric_limits<std::uint32_t>::max();
}

bool is_empty_affine_min_candidate(
    const TgMobiusAffineMqBoundCandidate& candidate) {
  return candidate.value == std::numeric_limits<std::int64_t>::max() &&
         candidate.local_squarefree == 0 &&
         candidate.order == std::numeric_limits<std::uint32_t>::max();
}

void validate_affine_candidate(
    const TgMobiusAffineMqBoundCandidate& candidate,
    std::size_t leaf_count,
    const TgMobiusPrefixMQ& delta,
    bool require_integer_endpoint,
    bool carries_squarefree_prefix) {
  const std::uint64_t order = candidate.order;
  const std::uint64_t row_offset = order >> 1U;
  if (order >= 2 * static_cast<std::uint64_t>(leaf_count)) {
    fail("affine MQ candidate order exceeds the actual leaf");
  }
  if (require_integer_endpoint && (order & 1U) != 0) {
    fail("affine MQ Hurst candidate used a right-limit endpoint");
  }
  if (carries_squarefree_prefix) {
    if (candidate.local_squarefree > delta.squarefree ||
        candidate.local_squarefree > row_offset + 1) {
      fail("affine MQ candidate squarefree witness exceeds its prefix");
    }
  } else if (candidate.local_squarefree != 0) {
    fail("affine MQ Hurst candidate carried a squarefree witness");
  }
}

std::int64_t exact_squarefree_candidate(
    const TgMobiusAffineMqBoundCandidate& candidate,
    std::uint64_t witness_y, bool lower) {
  const signed __int128 unadjusted =
      static_cast<signed __int128>(candidate.value) +
      candidate.local_squarefree;
  if (unadjusted < 0 ||
      unadjusted > std::numeric_limits<std::uint64_t>::max()) {
    fail("affine MQ candidate left the unsigned squarefree range");
  }
  std::uint64_t q = static_cast<std::uint64_t>(unadjusted);
  if (!squarefree_endpoint_safe(
          q, witness_y, 57, 2'000)) {
    fail("conservative affine MQ squarefree candidate is not exact-safe");
  }
  if (lower) {
    if (q != 0 &&
        squarefree_endpoint_safe(
            q - 1, witness_y, 57, 2'000)) {
      --q;
    }
  } else if (q != std::numeric_limits<std::uint64_t>::max() &&
             squarefree_endpoint_safe(
                 q + 1, witness_y, 57, 2'000)) {
    ++q;
  }
  const signed __int128 adjusted =
      static_cast<signed __int128>(q) - candidate.local_squarefree;
  if (adjusted < std::numeric_limits<std::int64_t>::min() ||
      adjusted > std::numeric_limits<std::int64_t>::max()) {
    fail("exact affine MQ squarefree guard left signed 64 bits");
  }
  return static_cast<std::int64_t>(adjusted);
}

AffineMqHostSummary finalize_affine_mq_candidates(
    std::uint64_t shard_lower,
    std::size_t leaf_count,
    const TgMobiusPrefixMQ& delta,
    const std::vector<TgMobiusAffineMqThreadCandidates>& records) {
  if (leaf_count == 0 || leaf_count > kMaximumSegmentCount) {
    fail("affine MQ finalizer received an invalid leaf count");
  }
  if (records.empty()) fail("affine MQ prototype emitted no candidates");
  const std::int64_t delta_mertens = delta.mertens;
  const std::int64_t delta_squarefree = delta.squarefree;
  if (delta.squarefree > leaf_count ||
      delta_mertens < -delta_squarefree ||
      delta_mertens > delta_squarefree ||
      (delta_mertens + delta_squarefree) % 2 != 0) {
    fail("affine MQ terminal delta violates exact Möbius row invariants");
  }
  const auto i64_min = std::numeric_limits<std::int64_t>::min();
  const auto i64_max = std::numeric_limits<std::int64_t>::max();
  AffineMqHostSummary summary{};
  summary.present = true;
  summary.delta = delta;
  summary.hurst_lower = {i64_min, 0,
                         std::numeric_limits<std::uint64_t>::max()};
  summary.hurst_upper = {i64_max, 0,
                         std::numeric_limits<std::uint64_t>::max()};
  for (const TgMobiusAffineMqThreadCandidates& record : records) {
    const auto& lower = record.hurst_lower;
    if (!is_empty_affine_max_candidate(lower)) {
      validate_affine_candidate(
          lower, leaf_count, delta, true, false);
    }
    if (lower.value > summary.hurst_lower.value ||
        (lower.value == summary.hurst_lower.value &&
         lower.order < summary.hurst_lower.order)) {
      summary.hurst_lower =
          {lower.value,
           affine_candidate_witness_y(
               shard_lower, leaf_count, lower),
           lower.order};
    }
    const auto& upper = record.hurst_upper;
    if (!is_empty_affine_min_candidate(upper)) {
      validate_affine_candidate(
          upper, leaf_count, delta, true, false);
    }
    if (upper.value < summary.hurst_upper.value ||
        (upper.value == summary.hurst_upper.value &&
         upper.order < summary.hurst_upper.order)) {
      summary.hurst_upper =
          {upper.value,
           affine_candidate_witness_y(
               shard_lower, leaf_count, upper),
           upper.order};
    }
  }
  summary.squarefree_lower = {
      i64_min, 0, std::numeric_limits<std::uint64_t>::max()};
  summary.squarefree_upper = {
      i64_max, 0, std::numeric_limits<std::uint64_t>::max()};
  auto consider_lower =
      [&](const TgMobiusAffineMqBoundCandidate& candidate) {
        if (is_empty_affine_max_candidate(candidate)) return;
        validate_affine_candidate(
            candidate, leaf_count, delta, false, true);
        const std::uint64_t witness_y =
            affine_candidate_witness_y(
                shard_lower, leaf_count, candidate);
        const std::int64_t exact =
            exact_squarefree_candidate(candidate, witness_y, true);
        if (exact != candidate.value) {
          fail("device affine MQ lower boundary was not exact");
        }
        if (exact > summary.squarefree_lower.value ||
            (exact == summary.squarefree_lower.value &&
             candidate.order < summary.squarefree_lower.order)) {
          summary.squarefree_lower =
              {exact, witness_y, candidate.order};
        }
      };
  auto consider_upper =
      [&](const TgMobiusAffineMqBoundCandidate& candidate) {
        if (is_empty_affine_min_candidate(candidate)) return;
        validate_affine_candidate(
            candidate, leaf_count, delta, false, true);
        const std::uint64_t witness_y =
            affine_candidate_witness_y(
                shard_lower, leaf_count, candidate);
        const std::int64_t exact =
            exact_squarefree_candidate(candidate, witness_y, false);
        if (exact != candidate.value) {
          fail("device affine MQ upper boundary was not exact");
        }
        if (exact < summary.squarefree_upper.value ||
            (exact == summary.squarefree_upper.value &&
             candidate.order < summary.squarefree_upper.order)) {
          summary.squarefree_upper =
              {exact, witness_y, candidate.order};
        }
      };
  for (const TgMobiusAffineMqThreadCandidates& record : records) {
    consider_lower(record.squarefree_lower);
    consider_upper(record.squarefree_upper);
  }
  if (summary.hurst_lower.value == i64_min ||
      summary.hurst_upper.value == i64_max ||
      summary.squarefree_lower.value == i64_min ||
      summary.squarefree_upper.value == i64_max) {
    fail("affine MQ prototype did not cover every terminal guard");
  }
  return summary;
}

signed __int128 hurst_slack(std::uint64_t n, std::int64_t mertens) {
  const signed __int128 m = mertens;
  return static_cast<signed __int128>(571) * 571 * n -
         static_cast<signed __int128>(1000) * 1000 * m * m;
}

std::string render_i128(signed __int128 value) {
  if (value == 0) return "0";
  const bool negative = value < 0;
  unsigned __int128 magnitude = negative
      ? static_cast<unsigned __int128>(-(value + 1)) + 1
      : static_cast<unsigned __int128>(value);
  std::string digits;
  while (magnitude != 0) {
    digits.push_back(static_cast<char>('0' + magnitude % 10));
    magnitude /= 10;
  }
  if (negative) digits.push_back('-');
  return std::string(digits.rbegin(), digits.rend());
}

std::string render_u128(unsigned __int128 value) {
  if (value == 0) return "0";
  std::string digits;
  while (value != 0) {
    digits.push_back(static_cast<char>('0' + value % 10));
    value /= 10;
  }
  return std::string(digits.rbegin(), digits.rend());
}

std::string hash_file(const char* path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  sparkinterval::detail::Sha256 hasher;
  std::array<char, 1 << 16> buffer{};
  while (input) {
    input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    const std::streamsize count = input.gcount();
    if (count > 0) hasher.update(buffer.data(), static_cast<std::size_t>(count));
  }
  return sparkinterval::lowercase_hex(hasher.finish());
}

std::string json_escape(std::string_view value) {
  std::string escaped;
  for (const char character : value) {
    if (character == '"' || character == '\\') escaped.push_back('\\');
    escaped.push_back(character);
  }
  return escaped;
}

void print_problem(const EndpointProblem& problem) {
  if (!problem.present) {
    std::cout << "null";
  } else {
    std::cout << "{\"interval_n\": " << problem.interval_n
              << ", \"side\": \"" << problem.side << "\", \"y\": "
              << problem.y << '}';
  }
}

void print_little_mertens_problem(const LittleMertensProblem& problem) {
  if (!problem.present) {
    std::cout << "null";
  } else {
    std::cout << "{\"interval_floor\": " << problem.interval_floor
              << ", \"right_endpoint\": " << problem.right_endpoint << '}';
  }
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const TgMobiusResidueSeed selected_residue_seed =
      options.qualification_residue_235711_seed
          ? TgMobiusResidueSeed::k235711
          : options.qualification_residue_2357_seed
                ? TgMobiusResidueSeed::k2357
                : TgMobiusResidueSeed::k235;
  const auto process_start = std::chrono::steady_clock::now();
  const std::size_t count = static_cast<std::size_t>(options.count);
  const std::uint64_t upper = options.lower + options.count - 1;
  const std::uint64_t base_prime_limit = integer_square_root(upper);
  std::vector<std::uint32_t> primes;
  double prime_generation_milliseconds = 0.0;
  double prime_roster_load_and_authenticate_milliseconds = 0.0;
  if (options.source_prime_roster.empty()) {
    const auto prime_generation_start = std::chrono::steady_clock::now();
    primes = exact_primes_upto(base_prime_limit);
    const auto prime_generation_stop = std::chrono::steady_clock::now();
    prime_generation_milliseconds =
        std::chrono::duration<double, std::milli>(
            prime_generation_stop - prime_generation_start).count();
  } else {
    const auto roster_start = std::chrono::steady_clock::now();
    primes = load_source_prime_roster(options.source_prime_roster);
    primes.erase(
        std::upper_bound(primes.begin(), primes.end(), base_prime_limit),
        primes.end());
    const auto roster_stop = std::chrono::steady_clock::now();
    prime_roster_load_and_authenticate_milliseconds =
        std::chrono::duration<double, std::milli>(
            roster_stop - roster_start).count();
  }
  const auto active_filter_start = std::chrono::steady_clock::now();
  const bool all_primes_hit_by_interval_length =
      options.count >= base_prime_limit;
  std::vector<std::uint32_t> filtered_active_primes;
  if (!all_primes_hit_by_interval_length) {
    const std::size_t retained_seed_prime_count =
        options.fused_support_kernel &&
                !options.qualification_legacy_one_block_dense &&
                !options.qualification_unseeded_fused_initializer
            ? (options.qualification_residue_2357_seed
                   ? kTgMobiusResidue2357PrimeCount
                   : options.qualification_residue_235711_seed
                   ? kTgMobiusResidue235711PrimeCount
                   : kTgMobiusResidue235PrimeCount)
            : 0;
    filtered_active_primes =
        primes_hitting_segment(
            options.lower, count, primes,
            retained_seed_prime_count);
  }
  const std::vector<std::uint32_t>& active_primes =
      all_primes_hit_by_interval_length
          ? primes
          : filtered_active_primes;
  const auto active_filter_stop = std::chrono::steady_clock::now();
  const std::vector<std::uint32_t>& selected_device_primes =
      options.qualification_use_all_device_primes ? primes : active_primes;
  std::vector<std::uint32_t> attacked_device_primes;
  const std::vector<std::uint32_t>* device_prime_list_pointer =
      &selected_device_primes;
  if (options.qualification_omit_device_prime != 0) {
    attacked_device_primes = selected_device_primes;
    const auto found = std::lower_bound(
        attacked_device_primes.begin(), attacked_device_primes.end(),
        options.qualification_omit_device_prime);
    if (found == attacked_device_primes.end() ||
        *found != options.qualification_omit_device_prime) {
      fail("qualification omission prime is absent from the device list");
    }
    attacked_device_primes.erase(found);
    device_prime_list_pointer = &attacked_device_primes;
  }
  const std::vector<std::uint32_t>& device_prime_list =
      *device_prime_list_pointer;
  if (options.fused_support_kernel &&
      !options.qualification_legacy_one_block_dense &&
      !options.qualification_unseeded_fused_initializer &&
      !(options.qualification_residue_235711_seed
            ? tg_mobius_host_roster_begins_235711(
                  device_prime_list.data(), device_prime_list.size())
            : options.qualification_residue_2357_seed
                  ? tg_mobius_host_roster_begins_2357(
                        device_prime_list.data(),
                        device_prime_list.size())
                  : tg_mobius_host_roster_begins_235(
                        device_prime_list.data(),
                        device_prime_list.size()))) {
    if (options.qualification_residue_235711_seed) {
      fail(
          "residue-235711 qualification requires the selected device "
          "prime roster to begin exactly [2,3,5,7,11]");
    }
    fail(options.qualification_residue_2357_seed
             ? "residue-2357 qualification requires the selected device "
               "prime roster to begin exactly [2,3,5,7]"
             : "residue-235 initialization requires the selected device "
               "prime roster to begin exactly [2,3,5]");
  }
  const std::uint64_t dense_prime_limit =
      1 + (options.count - 1) / 256;
  const std::size_t dense_prime_count = static_cast<std::size_t>(
      std::upper_bound(device_prime_list.begin(), device_prime_list.end(),
                       dense_prime_limit) -
      device_prime_list.begin());
  const double active_filter_milliseconds =
      std::chrono::duration<double, std::milli>(
          active_filter_stop - active_filter_start).count();

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device; use --allow-other-device only for explicit cross-device testing", 4);
  }
  if (options.device >= device_count) fail("requested CUDA device is unavailable", 4);
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));
  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if ((std::string_view(properties.name) != "NVIDIA GB10" ||
       properties.major != 12 || properties.minor != 1) &&
      !options.allow_other_device) {
    fail("expected an NVIDIA GB10 with compute capability 12.1; use --allow-other-device only for explicit cross-device testing", 4);
  }

  const std::size_t output_bytes = count * sizeof(TgMobiusSupport);
  const std::size_t prime_bytes =
      device_prime_list.size() * sizeof(std::uint32_t);
  std::uint32_t* device_primes = nullptr;
  TgMobiusSupport* device_outputs = nullptr;
  TgMobiusCompactSupport* device_compact_supports = nullptr;
  TgMobiusFusedSupport* device_fused_supports = nullptr;
  std::int8_t* device_mobius = nullptr;
  TgMobiusPrefixMQ* device_affine_prefixes = nullptr;
  TgMobiusAffineMqThreadCandidates* device_affine_candidates = nullptr;
  std::uint32_t* device_roster_invalid = nullptr;
  TgMobiusRectangularLaunchGeometry rectangular_geometry{};
  void* device_affine_workspace = nullptr;
  std::size_t affine_workspace_bytes = 0;
  const std::size_t affine_candidate_count =
      options.affine_mq_gpu_prototype
          ? tg_mobius_affine_mq_candidate_count(count)
          : 0;
  const auto allocation_start = std::chrono::steady_clock::now();
  if (!device_prime_list.empty()) {
    check_cuda("cudaMalloc(base_primes)",
               cudaMalloc(reinterpret_cast<void**>(&device_primes), prime_bytes));
  }
  if (options.compact_support_kernel) {
    check_cuda(
        "cudaMalloc(compact_supports)",
        cudaMalloc(reinterpret_cast<void**>(&device_compact_supports),
                   count * sizeof(TgMobiusCompactSupport)));
  } else if (options.fused_support_kernel) {
    check_cuda(
        "cudaMalloc(fused_supports)",
        cudaMalloc(reinterpret_cast<void**>(&device_fused_supports),
                   count * sizeof(TgMobiusFusedSupport)));
  } else {
    check_cuda(
        "cudaMalloc(outputs)",
        cudaMalloc(reinterpret_cast<void**>(&device_outputs), output_bytes));
  }
  if (options.compact_mu_output) {
    check_cuda("cudaMalloc(compact_mobius)",
               cudaMalloc(reinterpret_cast<void**>(&device_mobius), count));
  }
  if (options.qualification_residue_2357_seed ||
      options.qualification_residue_235711_seed ||
      options.qualification_residue_rectangular) {
    check_cuda(
        "cudaMalloc(qualification_roster_invalid)",
        cudaMalloc(
            reinterpret_cast<void**>(&device_roster_invalid),
            sizeof(std::uint32_t)));
  }
  if (options.affine_mq_gpu_prototype) {
    if (affine_candidate_count == 0) {
      fail("affine MQ candidate count is invalid");
    }
    check_cuda(
        "affine MQ workspace query",
        tg_mobius_affine_mq_workspace_size(
            count, &affine_workspace_bytes));
    if (affine_workspace_bytes == 0) {
      fail("affine MQ workspace query returned zero bytes");
    }
    check_cuda(
        "cudaMalloc(affine_mq_prefixes)",
        cudaMalloc(reinterpret_cast<void**>(&device_affine_prefixes),
                   count * sizeof(TgMobiusPrefixMQ)));
    check_cuda(
        "cudaMalloc(affine_mq_candidates)",
        cudaMalloc(reinterpret_cast<void**>(&device_affine_candidates),
                   affine_candidate_count *
                       sizeof(TgMobiusAffineMqThreadCandidates)));
    check_cuda(
        "cudaMalloc(affine_mq_workspace)",
        cudaMalloc(&device_affine_workspace, affine_workspace_bytes));
  }
  const auto allocation_stop = std::chrono::steady_clock::now();
  const auto host_to_device_start = std::chrono::steady_clock::now();
  if (!device_prime_list.empty()) {
    check_cuda("cudaMemcpy(base_primes)",
               cudaMemcpy(device_primes, device_prime_list.data(), prime_bytes,
                          cudaMemcpyHostToDevice));
  }
  const auto host_to_device_stop = std::chrono::steady_clock::now();
  const double allocation_milliseconds =
      std::chrono::duration<double, std::milli>(
          allocation_stop - allocation_start).count();
  const double host_to_device_milliseconds =
      std::chrono::duration<double, std::milli>(
          host_to_device_stop - host_to_device_start).count();

  cudaEvent_t start = nullptr;
  cudaEvent_t segment_stop = nullptr;
  cudaEvent_t pack_stop = nullptr;
  cudaEvent_t affine_stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(segment_stop)",
             cudaEventCreate(&segment_stop));
  check_cuda("cudaEventCreate(pack_stop)", cudaEventCreate(&pack_stop));
  check_cuda("cudaEventCreate(affine_stop)", cudaEventCreate(&affine_stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  if (options.compact_support_kernel) {
    check_cuda(
        "compact-support Moebius segment launch",
        launch_tg_mobius_compact_segment(
            options.lower, count, device_primes,
            device_prime_list.size(), dense_prime_count,
            device_compact_supports, device_mobius));
  } else if (options.fused_support_kernel) {
    check_cuda(
        "fused-support Moebius segment launch",
        options.qualification_residue_rectangular
            ? launch_tg_mobius_fused_segment_multiblock_dense_residue_rectangular_qualification(
                  options.lower, count, device_primes,
                  device_prime_list.size(), dense_prime_count,
                  selected_residue_seed,
                  options.qualification_rectangular_mode,
                  device_fused_supports, device_mobius,
                  device_roster_invalid, &rectangular_geometry)
            : options.qualification_residue_235711_seed
            ? launch_tg_mobius_fused_segment_multiblock_dense_residue_235711_qualification(
                  options.lower, count, device_primes,
                  device_prime_list.size(), dense_prime_count,
                  device_fused_supports, device_mobius,
                  device_roster_invalid)
            : options.qualification_residue_2357_seed
            ? launch_tg_mobius_fused_segment_multiblock_dense_residue_2357_qualification(
                  options.lower, count, device_primes,
                  device_prime_list.size(), dense_prime_count,
                  device_fused_supports, device_mobius,
                  device_roster_invalid)
            : options.qualification_legacy_one_block_dense
            ? launch_tg_mobius_fused_segment(
                  options.lower, count, device_primes,
                  device_prime_list.size(), dense_prime_count,
                  device_fused_supports, device_mobius)
            : (options.qualification_unseeded_fused_initializer
                   ? launch_tg_mobius_fused_segment_multiblock_dense(
                         options.lower, count, device_primes,
                         device_prime_list.size(), dense_prime_count,
                         device_fused_supports, device_mobius)
                   : launch_tg_mobius_fused_segment_multiblock_dense_residue_235(
                         options.lower, count, device_primes,
                         device_prime_list.size(), dense_prime_count,
                         device_fused_supports, device_mobius)));
  } else {
    check_cuda(
        "Moebius segment launch",
        launch_tg_mobius_segment(
            options.lower, count, device_primes,
            device_prime_list.size(), dense_prime_count,
            device_outputs));
  }
  check_cuda("cudaEventRecord(segment_stop)",
             cudaEventRecord(segment_stop));
  if (options.compact_mu_output &&
      !options.compact_support_kernel &&
      !options.fused_support_kernel) {
    check_cuda("Moebius compact pack launch",
               launch_tg_mobius_pack(device_outputs, count, device_mobius));
  }
  check_cuda("cudaEventRecord(pack_stop)", cudaEventRecord(pack_stop));
  if (options.affine_mq_gpu_prototype) {
    check_cuda(
        "Moebius affine MQ scan/reduction launch",
        launch_tg_mobius_affine_mq(
            options.lower, device_mobius, count, device_affine_prefixes,
            device_affine_candidates, device_affine_workspace,
            affine_workspace_bytes));
  }
  check_cuda("cudaEventRecord(affine_stop)", cudaEventRecord(affine_stop));
  check_cuda("cudaEventSynchronize(affine_stop)",
             cudaEventSynchronize(affine_stop));
  float kernel_milliseconds = 0.0F;
  float compact_pack_milliseconds = 0.0F;
  float affine_mq_device_milliseconds = 0.0F;
  check_cuda(
      "cudaEventElapsedTime(segment)",
      cudaEventElapsedTime(&kernel_milliseconds, start, segment_stop));
  check_cuda(
      "cudaEventElapsedTime(pack)",
      cudaEventElapsedTime(
          &compact_pack_milliseconds, segment_stop, pack_stop));
  check_cuda(
      "cudaEventElapsedTime(affine MQ)",
      cudaEventElapsedTime(
          &affine_mq_device_milliseconds, pack_stop, affine_stop));
  // Adjacent CUDA events around an intentionally empty phase can report a
  // small nonzero timestamp gap.  Report zero for phases which were not
  // launched so the timing decomposition does not invent device work.
  if (!options.compact_mu_output || options.compact_support_kernel ||
      options.fused_support_kernel) {
    compact_pack_milliseconds = 0.0F;
  }
  if (!options.affine_mq_gpu_prototype) {
    affine_mq_device_milliseconds = 0.0F;
  }

  std::vector<TgMobiusSupport> outputs;
  std::vector<std::int8_t> compact_mobius;
  std::vector<TgMobiusCompactSupport> compact_supports;
  std::vector<TgMobiusFusedSupport> fused_supports;
  if (options.compact_mu_output) {
    compact_mobius.resize(count);
  } else {
    outputs.resize(count);
  }
  if (options.qualification_transfer_compact_support) {
    compact_supports.resize(count);
  }
  if (options.qualification_transfer_fused_support) {
    fused_supports.resize(count);
  }
  std::uint32_t roster_invalid = 0;
  if (options.qualification_residue_2357_seed ||
      options.qualification_residue_235711_seed ||
      options.qualification_residue_rectangular) {
    check_cuda(
        "cudaMemcpy(qualification_roster_invalid)",
        cudaMemcpy(
            &roster_invalid, device_roster_invalid,
            sizeof(roster_invalid), cudaMemcpyDeviceToHost));
    if (roster_invalid != 0) {
      fail(
          options.qualification_residue_rectangular
              ? "rectangular residue qualification device preflight "
                "rejected the host-validated roster"
              : options.qualification_residue_235711_seed
              ? "residue-235711 qualification device preflight rejected "
                "the host-validated roster"
              : "residue-2357 qualification device preflight rejected the "
                "host-validated roster");
    }
  }
  const auto device_to_host_start = std::chrono::steady_clock::now();
  if (options.compact_mu_output) {
    check_cuda("cudaMemcpy(compact_mobius)",
               cudaMemcpy(compact_mobius.data(), device_mobius, count,
                          cudaMemcpyDeviceToHost));
  } else {
    check_cuda("cudaMemcpy(outputs)",
               cudaMemcpy(outputs.data(), device_outputs, output_bytes,
                          cudaMemcpyDeviceToHost));
  }
  if (options.qualification_transfer_compact_support) {
    check_cuda(
        "cudaMemcpy(compact_supports)",
        cudaMemcpy(
            compact_supports.data(), device_compact_supports,
            compact_supports.size() *
                sizeof(TgMobiusCompactSupport),
            cudaMemcpyDeviceToHost));
  }
  if (options.qualification_transfer_fused_support) {
    check_cuda(
        "cudaMemcpy(fused_supports)",
        cudaMemcpy(
            fused_supports.data(), device_fused_supports,
            fused_supports.size() * sizeof(TgMobiusFusedSupport),
            cudaMemcpyDeviceToHost));
  }
  if (!options.qualification_write_mu.empty()) {
    std::ofstream output(options.qualification_write_mu,
                         std::ios::binary | std::ios::trunc);
    if (!output) fail("could not open qualification mu output");
    output.write(
        reinterpret_cast<const char*>(compact_mobius.data()),
        static_cast<std::streamsize>(compact_mobius.size()));
    if (!output) fail("could not write qualification mu output");
  }
  const auto device_to_host_stop = std::chrono::steady_clock::now();
  const double device_to_host_milliseconds =
      std::chrono::duration<double, std::milli>(
          device_to_host_stop - device_to_host_start).count();
  const std::size_t device_to_host_bytes =
      (options.compact_mu_output ? count : output_bytes) +
      (options.qualification_transfer_compact_support
           ? count * sizeof(TgMobiusCompactSupport)
           : 0) +
      (options.qualification_transfer_fused_support
           ? count * sizeof(TgMobiusFusedSupport)
           : 0) +
      (options.qualification_residue_2357_seed ||
               options.qualification_residue_235711_seed ||
               options.qualification_residue_rectangular
           ? sizeof(std::uint32_t)
           : 0);
  std::vector<TgMobiusAffineMqThreadCandidates> affine_candidates;
  TgMobiusPrefixMQ affine_delta{};
  double affine_summary_transfer_milliseconds = 0.0;
  if (options.affine_mq_gpu_prototype) {
    affine_candidates.resize(affine_candidate_count);
    const auto affine_transfer_start = std::chrono::steady_clock::now();
    check_cuda(
        "cudaMemcpy(affine_mq_candidates)",
        cudaMemcpy(
            affine_candidates.data(), device_affine_candidates,
            affine_candidates.size() *
                sizeof(TgMobiusAffineMqThreadCandidates),
            cudaMemcpyDeviceToHost));
    check_cuda(
        "cudaMemcpy(affine_mq_delta)",
        cudaMemcpy(
            &affine_delta, device_affine_prefixes + count - 1,
            sizeof(affine_delta), cudaMemcpyDeviceToHost));
    const auto affine_transfer_stop = std::chrono::steady_clock::now();
    affine_summary_transfer_milliseconds =
        std::chrono::duration<double, std::milli>(
            affine_transfer_stop - affine_transfer_start).count();
  }
  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(segment_stop)",
             cudaEventDestroy(segment_stop));
  check_cuda("cudaEventDestroy(pack_stop)", cudaEventDestroy(pack_stop));
  check_cuda("cudaEventDestroy(affine_stop)",
             cudaEventDestroy(affine_stop));
  if (device_primes != nullptr) check_cuda("cudaFree(base_primes)", cudaFree(device_primes));
  if (device_mobius != nullptr) {
    check_cuda("cudaFree(compact_mobius)", cudaFree(device_mobius));
  }
  if (device_compact_supports != nullptr) {
    check_cuda("cudaFree(compact_supports)",
               cudaFree(device_compact_supports));
  }
  if (device_fused_supports != nullptr) {
    check_cuda("cudaFree(fused_supports)",
               cudaFree(device_fused_supports));
  }
  if (device_roster_invalid != nullptr) {
    check_cuda(
        "cudaFree(qualification_roster_invalid)",
        cudaFree(device_roster_invalid));
  }
  if (device_affine_prefixes != nullptr) {
    check_cuda("cudaFree(affine_mq_prefixes)",
               cudaFree(device_affine_prefixes));
  }
  if (device_affine_candidates != nullptr) {
    check_cuda("cudaFree(affine_mq_candidates)",
               cudaFree(device_affine_candidates));
  }
  if (device_affine_workspace != nullptr) {
    check_cuda("cudaFree(affine_mq_workspace)",
               cudaFree(device_affine_workspace));
  }
  if (device_outputs != nullptr) {
    check_cuda("cudaFree(outputs)", cudaFree(device_outputs));
  }

  const auto affine_finalize_start = std::chrono::steady_clock::now();
  AffineMqHostSummary affine_summary{};
  if (options.affine_mq_gpu_prototype) {
    affine_summary =
        finalize_affine_mq_candidates(
            options.lower, count, affine_delta, affine_candidates);
  }
  const auto affine_finalize_stop = std::chrono::steady_clock::now();
  const double affine_finalize_milliseconds =
      std::chrono::duration<double, std::milli>(
          affine_finalize_stop - affine_finalize_start).count();

  const auto host_start = std::chrono::steady_clock::now();
  const auto independent_sieve_start = host_start;
  std::vector<TgMobiusSupport> expected(count);
  independently_sieve(options.lower, primes, &expected);
  const auto independent_sieve_stop = std::chrono::steady_clock::now();
  std::uint64_t mismatch_count = 0;
  std::uint64_t first_mismatch_number = 0;
  std::uint64_t fused_support_poison_count = 0;
  const auto comparison_start = independent_sieve_stop;
  for (std::size_t index = 0; index < count; ++index) {
    const TgMobiusSupport& reference = expected[index];
    bool same = options.compact_mu_output
        ? compact_mobius[index] == reference.mobius
        : same_record(outputs[index], reference);
    if (same && options.qualification_transfer_compact_support) {
      const TgMobiusCompactSupport& compact = compact_supports[index];
      same =
          compact.base_prime_product == reference.base_prime_product &&
          (compact.packed_count_squareful & 0x7fffffffU) ==
              reference.distinct_base_prime_count &&
          (compact.packed_count_squareful >> 31U) ==
              reference.squareful &&
          compact.reserved == reference.reserved;
    }
    if (options.qualification_transfer_fused_support) {
      const std::uint64_t packed = fused_supports[index].packed;
      const bool poisoned =
          (packed & kTgMobiusFusedPoisonBit) != 0;
      if (poisoned) ++fused_support_poison_count;
      const bool fused_same =
          (packed & kTgMobiusFusedProductMask) ==
              reference.base_prime_product &&
          ((packed & kTgMobiusFusedCountMask) >>
           kTgMobiusFusedCountShift) ==
              reference.distinct_base_prime_count &&
          ((packed & kTgMobiusFusedSquarefulBit) != 0) ==
              (reference.squareful != 0) &&
          (packed &
           (kTgMobiusFusedReservedMask |
            kTgMobiusFusedPoisonBit)) == 0;
      same = same && fused_same;
    }
    if (!same) {
      if (mismatch_count == 0) first_mismatch_number = options.lower + index;
      ++mismatch_count;
    }
  }
  const bool full_support_compared =
      !options.compact_mu_output ||
      options.qualification_transfer_compact_support ||
      options.qualification_transfer_fused_support;
  const std::string cpu_full_support_digest = full_support_compared
      ? hash_records_le(expected)
      : std::string(kZeroDigest);
  const std::string gpu_digest = !full_support_compared
      ? std::string(kZeroDigest)
      : (mismatch_count == 0
             ? cpu_full_support_digest
             : (!outputs.empty() ? hash_records_le(outputs)
                                 : std::string(kZeroDigest)));
  // Exact fieldwise equality makes the independently generated record byte
  // stream identical.  Avoid a redundant SHA-256 compression pass on valid
  // shards; retain the second pass on a mismatch for useful diagnostics.
  const std::string cpu_digest = cpu_full_support_digest;
  const bool records_passed =
      full_support_compared && mismatch_count == 0 &&
      gpu_digest == cpu_digest;
  const bool compared_output_passed =
      mismatch_count == 0 &&
      (options.compact_mu_output || gpu_digest == cpu_digest);

  // Reproduce the pinned Hurst adapter's single-segment row commitment from
  // the GPU-produced values.  This binds exact ordered mu bytes, while the
  // full-output mode's support digest continues to bind every GPU field.
  constexpr std::uint64_t kHurstReductionBlockSize = 1'048'576;
  constexpr std::string_view kHurstRowDomain =
      "sparkinterval.tg.hurst-residual-mobius-rows.v1";
  constexpr std::string_view kHurstBlockDomain =
      "sparkinterval.tg.hurst-residual-mobius-block.v1";
  sparkinterval::detail::Sha256 hurst_row_hasher;
  hurst_row_hasher.update(kHurstRowDomain.data(), kHurstRowDomain.size());
  hash_u64_be(&hurst_row_hasher, options.lower);
  hash_u64_be(&hurst_row_hasher, upper + 1);
  const std::size_t hurst_block_count =
      1 + (count - 1) / kHurstReductionBlockSize;
  std::vector<sparkinterval::Sha256Digest> hurst_block_digests(
      hurst_block_count);
  const unsigned int available_threads =
      std::max(1U, std::thread::hardware_concurrency());
  const std::size_t hurst_hash_threads =
      std::min<std::size_t>(hurst_block_count, available_threads);
  std::atomic<std::size_t> next_hurst_block{0};
  auto hash_hurst_blocks = [&]() {
    for (;;) {
      const std::size_t block_index =
          next_hurst_block.fetch_add(1, std::memory_order_relaxed);
      if (block_index >= hurst_block_count) return;
      const std::size_t block_offset =
          block_index * kHurstReductionBlockSize;
      const std::size_t block_size = std::min<std::size_t>(
          kHurstReductionBlockSize, count - block_offset);
      std::vector<unsigned char> encoded(block_size);
      for (std::size_t index = 0; index < block_size; ++index) {
        const std::int32_t mu = options.compact_mu_output
            ? compact_mobius[block_offset + index]
            : outputs[block_offset + index].mobius;
        encoded[index] = static_cast<unsigned char>(mu + 1);
      }
      sparkinterval::detail::Sha256 block_hasher;
      block_hasher.update(kHurstBlockDomain.data(),
                          kHurstBlockDomain.size());
      hash_u64_be(&block_hasher, options.lower + block_offset);
      hash_u64_be(&block_hasher,
                  options.lower + block_offset + block_size);
      block_hasher.update(encoded.data(), encoded.size());
      hurst_block_digests[block_index] = block_hasher.finish();
    }
  };
  std::vector<std::thread> hurst_hash_workers;
  hurst_hash_workers.reserve(hurst_hash_threads);
  for (std::size_t index = 0; index < hurst_hash_threads; ++index) {
    hurst_hash_workers.emplace_back(hash_hurst_blocks);
  }
  for (std::thread& worker : hurst_hash_workers) worker.join();
  for (std::size_t block_index = 0; block_index < hurst_block_count;
       ++block_index) {
    const std::size_t block_offset =
        block_index * kHurstReductionBlockSize;
    hash_u64_be(&hurst_row_hasher, options.lower + block_offset);
    hurst_row_hasher.update(hurst_block_digests[block_index].data(),
                            hurst_block_digests[block_index].size());
  }
  const std::string hurst_row_digest =
      sparkinterval::lowercase_hex(hurst_row_hasher.finish());
  const auto comparison_stop = std::chrono::steady_clock::now();

  const auto guard_fold_start = comparison_stop;
  std::array<std::uint64_t, 3> mobius_histogram{};
  std::int64_t mertens = options.incoming_mertens;
  std::uint64_t squarefree_count = options.incoming_squarefree;
  signed __int128 little_mertens_lower =
      options.incoming_little_mertens_lower;
  signed __int128 little_mertens_upper =
      options.incoming_little_mertens_upper;
  signed __int128 little_mertens_lower_delta = 0;
  signed __int128 little_mertens_upper_delta = 0;
  signed __int128 minimum_hurst_slack = 0;
  std::uint64_t minimum_hurst_slack_at = 0;
  std::uint64_t hurst_checks = 0;
  std::uint64_t first_hurst_failure = 0;
  std::uint64_t b1_checks = 0;
  std::uint64_t b2_checks = 0;
  EndpointProblem first_b1_problem{};
  EndpointProblem first_b2_problem{};
  std::uint64_t little_mertens_211_checks = 0;
  std::uint64_t little_mertens_stronger_checks = 0;
  LittleMertensProblem first_little_mertens_211_problem{};
  LittleMertensProblem first_little_mertens_stronger_problem{};
  unsigned __int128 little_mertens_211_maximum_absolute = 0;
  unsigned __int128 little_mertens_stronger_maximum_absolute = 0;
  std::uint64_t little_mertens_211_maximum_at = 0;
  std::uint64_t little_mertens_211_maximum_right_endpoint = 0;
  std::uint64_t little_mertens_stronger_maximum_at = 0;
  std::uint64_t little_mertens_stronger_maximum_right_endpoint = 0;

  for (std::size_t index = 0; index < count; ++index) {
    const TgMobiusSupport& reference = expected[index];
    const std::uint64_t n = options.lower + index;
    const std::int32_t mu = reference.mobius;
    ++mobius_histogram[static_cast<std::size_t>(mu + 1)];
    mertens += mu;
    if (mu != 0) ++squarefree_count;
    if (n <= kLittleMertens211Limit) {
      add_directed_reciprocal(n, mu, &little_mertens_lower,
                              &little_mertens_upper,
                              &little_mertens_lower_delta,
                              &little_mertens_upper_delta);
    }

    if (n >= 33) {
      const signed __int128 slack = hurst_slack(n, mertens);
      if (hurst_checks == 0 || slack < minimum_hurst_slack) {
        minimum_hurst_slack = slack;
        minimum_hurst_slack_at = n;
      }
      ++hurst_checks;
      if (slack < 0 && first_hurst_failure == 0) first_hurst_failure = n;
    }

    auto check_cdem_head = [&](std::uint64_t threshold,
                               std::uint64_t bound_numerator,
                               std::uint64_t bound_denominator,
                               std::uint64_t* checks,
                               EndpointProblem* first_problem) {
      if (n < threshold) return;
      auto check_endpoint = [&](std::uint64_t y, const char* side) {
        ++*checks;
        if (!squarefree_endpoint_safe(squarefree_count, y, bound_numerator,
                                      bound_denominator) &&
            !first_problem->present) {
          *first_problem = EndpointProblem{true, n, side, y};
        }
      };
      // At n=threshold this is a limiting check from the claimed open side.
      check_endpoint(n, "at_integer_or_open_right_limit");
      if (n < kSourceLimit) check_endpoint(n + 1, "left_limit_at_next_integer");
    };
    check_cdem_head(9'243, 151, 2'000, &b1_checks, &first_b1_problem);
    check_cdem_head(438'429, 57, 2'000, &b2_checks, &first_b2_problem);

    auto check_little_mertens =
        [&](std::uint64_t source_lower, std::uint64_t source_upper,
            bool stronger_bound, std::uint64_t* checks,
            LittleMertensProblem* first_problem,
            unsigned __int128* maximum_absolute,
            std::uint64_t* maximum_at,
            std::uint64_t* maximum_right_endpoint) {
          if (n < source_lower || n > source_upper) return;
          const std::uint64_t right_endpoint =
              n == source_upper ? n : n + 1;
          const unsigned __int128 absolute =
              little_mertens_absolute_numerator(little_mertens_lower,
                                                 little_mertens_upper);
          if (*checks == 0 || absolute > *maximum_absolute) {
            *maximum_absolute = absolute;
            *maximum_at = n;
            *maximum_right_endpoint = right_endpoint;
          }
          ++*checks;
          if (!little_mertens_endpoint_safe(
                  little_mertens_lower, little_mertens_upper,
                  right_endpoint, stronger_bound) &&
              !first_problem->present) {
            *first_problem = LittleMertensProblem{true, n, right_endpoint};
          }
        };
    check_little_mertens(1, kLittleMertens211Limit, false,
                         &little_mertens_211_checks,
                         &first_little_mertens_211_problem,
                         &little_mertens_211_maximum_absolute,
                         &little_mertens_211_maximum_at,
                         &little_mertens_211_maximum_right_endpoint);
    check_little_mertens(kLittleMertensStrongerLower,
                         kLittleMertensStrongerLimit, true,
                         &little_mertens_stronger_checks,
                         &first_little_mertens_stronger_problem,
                         &little_mertens_stronger_maximum_absolute,
                         &little_mertens_stronger_maximum_at,
                         &little_mertens_stronger_maximum_right_endpoint);
  }

  const auto guard_fold_stop = std::chrono::steady_clock::now();
  const auto host_stop = guard_fold_stop;
  const double independent_sieve_milliseconds =
      std::chrono::duration<double, std::milli>(
          independent_sieve_stop - independent_sieve_start).count();
  const double comparison_and_hash_milliseconds =
      std::chrono::duration<double, std::milli>(
          comparison_stop - comparison_start).count();
  const double guard_fold_milliseconds =
      std::chrono::duration<double, std::milli>(
          guard_fold_stop - guard_fold_start).count();
  const double host_milliseconds =
      std::chrono::duration<double, std::milli>(host_stop - host_start).count();

  const std::int64_t delta_mertens =
      static_cast<std::int64_t>(mobius_histogram[2]) -
      static_cast<std::int64_t>(mobius_histogram[0]);
  const std::uint64_t segment_squarefree =
      mobius_histogram[0] + mobius_histogram[2];
  const std::string executable_digest = hash_file("/proc/self/exe");
  if (executable_digest.empty()) {
    fail("could not hash the running executable", 5);
  }
  const std::string rectangular_algorithm_id =
      "tg_mobius_compact_mu_residue_" +
      std::string(residue_seed_name(selected_residue_seed)) + "_" +
      std::string(rectangular_mode_name(
          options.qualification_rectangular_mode)) +
      "_qualification_v1";
  const std::string rectangular_receipt_domain =
      "sparkinterval.tg.mobius-one-shot-residue-" +
      std::string(residue_seed_name(selected_residue_seed)) + "-" +
      std::string(rectangular_mode_name(
          options.qualification_rectangular_mode)) +
      "-qualification.v1";
  const std::string_view algorithm_id =
      options.qualification_residue_rectangular
          ? std::string_view(rectangular_algorithm_id)
          : options.qualification_residue_235711_seed
          ? kResidue235711QualificationAlgorithm
          : options.compact_mu_output
                ? std::string_view(
                      "tg_mobius_compact_mu_qualification_v1")
                : std::string_view("tg_mobius_segment_v2");
  const std::string_view classification_id =
      options.qualification_residue_rectangular
          ? std::string_view(
                "qualification_only_rectangular_residue_schedule_not_"
                "full_support_receipt_or_proof")
          : options.qualification_residue_235711_seed
          ? kResidue235711QualificationClassification
          : options.compact_mu_output
                ? std::string_view(
                      "bounded_compact_mu_transition_not_full_support_"
                      "receipt_or_proof")
                : std::string_view(
                      "bounded_exact_transition_not_external_atom_proof");
  std::ostringstream canonical;
  canonical << "algorithm=" << algorithm_id << '\n';
  if (options.qualification_residue_rectangular) {
    canonical
        << "qualification_domain=" << rectangular_receipt_domain << '\n'
        << "residue_seed="
        << residue_seed_name(rectangular_geometry.seed) << '\n'
        << "rectangular_mode="
        << rectangular_mode_name(rectangular_geometry.mode) << '\n'
        << "rectangular_slots_per_prime="
        << rectangular_geometry.slots_per_prime << '\n'
        << "rectangular_required_slots_per_prime="
        << rectangular_geometry.required_slots_per_prime << '\n'
        << "rectangular_events_per_block="
        << rectangular_geometry.events_per_block << '\n'
        << "rectangular_grid_x=" << rectangular_geometry.grid_x << '\n'
        << "rectangular_grid_y=" << rectangular_geometry.grid_y << '\n'
        << "rectangular_grid_z=" << rectangular_geometry.grid_z << '\n'
        << "rectangular_threads_per_block="
        << rectangular_geometry.threads_per_block << '\n'
        << "enclosing_super_shard_lower="
        << rectangular_geometry.enclosing_lower << '\n'
        << "enclosing_super_shard_count="
        << rectangular_geometry.enclosing_count << '\n';
  }
  canonical << "previous=" << options.previous_receipt_sha256 << '\n'
            << "lower=" << options.lower << '\n'
            << "upper=" << upper << '\n'
            << "incoming_mertens=" << options.incoming_mertens << '\n'
            << "outgoing_mertens=" << mertens << '\n'
            << "incoming_squarefree=" << options.incoming_squarefree << '\n'
            << "outgoing_squarefree=" << squarefree_count << '\n'
            << "little_mertens_scale_bits=" << kLittleMertensScaleBits << '\n'
            << "incoming_little_mertens_lower="
            << render_i128(options.incoming_little_mertens_lower) << '\n'
            << "incoming_little_mertens_upper="
            << render_i128(options.incoming_little_mertens_upper) << '\n'
            << "outgoing_little_mertens_lower="
            << render_i128(little_mertens_lower) << '\n'
            << "outgoing_little_mertens_upper="
            << render_i128(little_mertens_upper) << '\n'
            << "little_mertens_lower_delta="
            << render_i128(little_mertens_lower_delta) << '\n'
            << "little_mertens_upper_delta="
            << render_i128(little_mertens_upper_delta) << '\n'
            << "record_sha256="
            << (options.compact_mu_output ? hurst_row_digest : gpu_digest)
            << '\n'
            << "executable_sha256=" << executable_digest << '\n'
            << "density_interval=" << kDensityIntervalId << '\n'
            << "mu_negative=" << mobius_histogram[0] << '\n'
            << "mu_zero=" << mobius_histogram[1] << '\n'
            << "mu_positive=" << mobius_histogram[2] << '\n'
            << "hurst_checks=" << hurst_checks << '\n'
            << "hurst_first_failure=" << first_hurst_failure << '\n'
            << "hurst_minimum_slack="
            << (hurst_checks == 0 ? "null" : render_i128(minimum_hurst_slack))
            << '\n'
            << "hurst_minimum_at=" << minimum_hurst_slack_at << '\n'
            << "b1_checks=" << b1_checks << '\n'
            << "b1_problem_n="
            << (first_b1_problem.present ? first_b1_problem.interval_n : 0) << '\n'
            << "b1_problem_side="
            << (first_b1_problem.present ? first_b1_problem.side : "none") << '\n'
            << "b1_problem_y="
            << (first_b1_problem.present ? first_b1_problem.y : 0) << '\n'
            << "b2_checks=" << b2_checks << '\n'
            << "b2_problem_n="
            << (first_b2_problem.present ? first_b2_problem.interval_n : 0) << '\n'
            << "b2_problem_side="
            << (first_b2_problem.present ? first_b2_problem.side : "none") << '\n'
            << "b2_problem_y="
            << (first_b2_problem.present ? first_b2_problem.y : 0) << '\n'
            << "little_mertens_211_checks=" << little_mertens_211_checks << '\n'
            << "little_mertens_211_problem_n="
            << (first_little_mertens_211_problem.present
                    ? first_little_mertens_211_problem.interval_floor
                    : 0)
            << '\n'
            << "little_mertens_211_problem_right="
            << (first_little_mertens_211_problem.present
                    ? first_little_mertens_211_problem.right_endpoint
                    : 0)
            << '\n'
            << "little_mertens_211_maximum_absolute="
            << (little_mertens_211_checks == 0
                    ? "null"
                    : render_u128(little_mertens_211_maximum_absolute))
            << '\n'
            << "little_mertens_211_maximum_at="
            << little_mertens_211_maximum_at << '\n'
            << "little_mertens_211_maximum_right="
            << little_mertens_211_maximum_right_endpoint << '\n'
            << "little_mertens_stronger_checks="
            << little_mertens_stronger_checks << '\n'
            << "little_mertens_stronger_problem_n="
            << (first_little_mertens_stronger_problem.present
                    ? first_little_mertens_stronger_problem.interval_floor
                    : 0)
            << '\n'
            << "little_mertens_stronger_problem_right="
            << (first_little_mertens_stronger_problem.present
                    ? first_little_mertens_stronger_problem.right_endpoint
                    : 0)
            << '\n'
            << "little_mertens_stronger_maximum_absolute="
            << (little_mertens_stronger_checks == 0
                    ? "null"
                    : render_u128(little_mertens_stronger_maximum_absolute))
            << '\n'
            << "little_mertens_stronger_maximum_at="
            << little_mertens_stronger_maximum_at << '\n'
            << "little_mertens_stronger_maximum_right="
            << little_mertens_stronger_maximum_right_endpoint << '\n';
  const std::string canonical_text = canonical.str();
  const std::string receipt_digest = sparkinterval::sha256_hex(
      canonical_text.data(), canonical_text.size());

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));
  const double rows_per_second = kernel_milliseconds > 0.0F
      ? static_cast<double>(count) * 1000.0 / kernel_milliseconds
      : 0.0;
  const std::size_t device_support_bytes_per_row =
      options.fused_support_kernel
          ? sizeof(TgMobiusFusedSupport)
          : (options.compact_support_kernel
                 ? sizeof(TgMobiusCompactSupport)
                 : sizeof(TgMobiusSupport));
  const std::string_view device_support_layout =
      options.fused_support_kernel
          ? "fused_product54_count5_squareful1_reserved3_poison1_u64"
          : (options.compact_support_kernel
                 ? "product_u64_plus_count31_squareful1_plus_reserved_u32"
                 : "full_tg_mobius_support_v1");

  std::cout << std::setprecision(17)
            << "{\n"
            << "  \"schema_version\": "
            << (options.compact_mu_output ? 0 : 2) << ",\n"
            << "  \"algorithm\": \"" << algorithm_id << "\",\n"
            << "  \"classification\": \"" << classification_id
            << "\",\n"
            << "  \"lower\": " << options.lower << ",\n"
            << "  \"upper\": " << upper << ",\n"
            << "  \"record_count\": " << count << ",\n"
            << "  \"incoming_mertens\": " << options.incoming_mertens << ",\n"
            << "  \"outgoing_mertens\": " << mertens << ",\n"
            << "  \"delta_mertens\": " << delta_mertens << ",\n"
            << "  \"incoming_squarefree\": " << options.incoming_squarefree << ",\n"
            << "  \"outgoing_squarefree\": " << squarefree_count << ",\n"
            << "  \"segment_squarefree_count\": " << segment_squarefree << ",\n"
            << "  \"little_mertens_fixed_point_scale_bits\": "
            << kLittleMertensScaleBits << ",\n"
            << "  \"little_mertens_fixed_point_scale\": "
            << render_u128(kLittleMertensScale) << ",\n"
            << "  \"incoming_little_mertens_lower\": "
            << render_i128(options.incoming_little_mertens_lower) << ",\n"
            << "  \"incoming_little_mertens_upper\": "
            << render_i128(options.incoming_little_mertens_upper) << ",\n"
            << "  \"outgoing_little_mertens_lower\": "
            << render_i128(little_mertens_lower) << ",\n"
            << "  \"outgoing_little_mertens_upper\": "
            << render_i128(little_mertens_upper) << ",\n"
            << "  \"little_mertens_lower_delta\": "
            << render_i128(little_mertens_lower_delta) << ",\n"
            << "  \"little_mertens_upper_delta\": "
            << render_i128(little_mertens_upper_delta) << ",\n"
            << "  \"previous_receipt_sha256\": \""
            << options.previous_receipt_sha256 << "\",\n"
            << "  \"receipt_chain_sha256\": \"" << receipt_digest << "\",\n"
            << "  \"canonical_transition_format\": \"tg_mobius_transition_lines_v2\",\n"
            << "  \"gpu_record_sha256_le_v1\": \"" << gpu_digest << "\",\n"
            << "  \"cpu_record_sha256_le_v1\": \"" << cpu_digest << "\",\n"
            << "  \"full_support_commitment_present\": "
            << (full_support_compared ? "true" : "false") << ",\n"
            << "  \"gpu_mu_hurst_block_sha256_v1\": \""
            << hurst_row_digest << "\",\n"
            << "  \"executable_sha256\": \"" << executable_digest << "\",\n"
            << "  \"all_records_compared_with_independent_cpu_segmented_sieve\": "
            << (records_passed ? "true" : "false") << ",\n"
            << "  \"all_gpu_mu_values_compared_with_independent_cpu_segmented_sieve\": "
            << (compared_output_passed ? "true" : "false") << ",\n"
            << "  \"mismatch_count\": " << mismatch_count << ",\n"
            << "  \"first_mismatch_number\": "
            << (mismatch_count == 0 ? "null" : std::to_string(first_mismatch_number))
            << ",\n"
            << "  \"mobius_histogram\": {\"-1\": " << mobius_histogram[0]
            << ", \"0\": " << mobius_histogram[1] << ", \"1\": "
            << mobius_histogram[2] << "},\n"
            << "  \"hurst_integer_checks\": " << hurst_checks << ",\n"
            << "  \"hurst_minimum_squared_slack\": "
            << (hurst_checks == 0 ? "null" : render_i128(minimum_hurst_slack))
            << ",\n"
            << "  \"hurst_minimum_squared_slack_at\": "
            << (hurst_checks == 0 ? "null" : std::to_string(minimum_hurst_slack_at))
            << ",\n"
            << "  \"hurst_first_failure\": "
            << (first_hurst_failure == 0 ? "null" : std::to_string(first_hurst_failure))
            << ",\n"
            << "  \"hurst_real_slab_reduction\": \"M(x)=M(floor(x)); sqrt(x) is increasing\",\n"
            << "  \"squarefree_density_interval_id\": \"" << kDensityIntervalId
            << "\",\n"
            << "  \"squarefree_density_lower\": \"607927101854026628/1000000000000000000\",\n"
            << "  \"squarefree_density_upper\": \"607927101854026629/1000000000000000000\",\n"
            << "  \"cdem_b1_endpoint_checks\": " << b1_checks << ",\n"
            << "  \"cdem_b1_first_not_proved_safe\": ";
  print_problem(first_b1_problem);
  std::cout << ",\n  \"cdem_b2_endpoint_checks\": " << b2_checks
            << ",\n  \"cdem_b2_first_not_proved_safe\": ";
  print_problem(first_b2_problem);
  std::cout << ",\n  \"little_mertens_2_11_real_slab_checks\": "
            << little_mertens_211_checks
            << ",\n  \"little_mertens_2_11_first_not_proved_safe\": ";
  print_little_mertens_problem(first_little_mertens_211_problem);
  std::cout << ",\n  \"little_mertens_2_11_maximum_interval_absolute_numerator\": "
            << (little_mertens_211_checks == 0
                    ? "null"
                    : render_u128(little_mertens_211_maximum_absolute))
            << ",\n  \"little_mertens_2_11_maximum_interval_absolute_at\": "
            << (little_mertens_211_checks == 0
                    ? "null"
                    : std::to_string(little_mertens_211_maximum_at))
            << ",\n  \"little_mertens_2_11_maximum_interval_absolute_right_endpoint\": "
            << (little_mertens_211_checks == 0
                    ? "null"
                    : std::to_string(
                          little_mertens_211_maximum_right_endpoint))
            << ",\n  \"little_mertens_stronger_real_slab_checks\": "
            << little_mertens_stronger_checks
            << ",\n  \"little_mertens_stronger_first_not_proved_safe\": ";
  print_little_mertens_problem(first_little_mertens_stronger_problem);
  std::cout << ",\n  \"little_mertens_stronger_maximum_interval_absolute_numerator\": "
            << (little_mertens_stronger_checks == 0
                    ? "null"
                    : render_u128(little_mertens_stronger_maximum_absolute))
            << ",\n  \"little_mertens_stronger_maximum_interval_absolute_at\": "
            << (little_mertens_stronger_checks == 0
                    ? "null"
                    : std::to_string(little_mertens_stronger_maximum_at))
            << ",\n  \"little_mertens_stronger_maximum_interval_absolute_right_endpoint\": "
            << (little_mertens_stronger_checks == 0
                    ? "null"
                    : std::to_string(
                          little_mertens_stronger_maximum_right_endpoint))
            << ",\n  \"little_mertens_interval_update\": "
               "\"floor/ceil(mu(n)*2^96/n), accumulated in checked signed __int128\",\n"
            << "  \"little_mertens_real_slab_reduction\": "
               "\"sum is constant on [n,n+1); compare its enclosing interval at n+1, except the closed source endpoint is compared at itself\",\n"
            << "  \"little_mertens_squared_comparisons\": "
               "\"r*A^2 <= 2*S^2 and 4*r*A^2 <= S^2 in checked unsigned 256-bit arithmetic\",\n"
            << "  \"fixed_point_overflow_guard_triggered\": false";
  std::cout
      << ",\n  \"incoming_state_is_locally_rooted\": "
      << (options.lower == 1 ? "true" : "false") << ",\n"
      << "  \"nonroot_claims_are_conditional_on_hash_linked_incoming_state\": "
      << (options.lower == 1 ? "false" : "true") << ",\n"
      << "  \"base_prime_limit\": " << base_prime_limit << ",\n"
      << "  \"base_prime_count\": " << primes.size() << ",\n"
      << "  \"active_base_prime_count\": " << active_primes.size() << ",\n"
      << "  \"device_base_prime_count\": " << device_prime_list.size() << ",\n"
      << "  \"device_base_prime_selection\": \""
      << (options.qualification_use_all_device_primes
              ? "qualification_all_primes"
              : "active_primes_hitting_segment")
      << "\",\n"
      << "  \"inactive_base_primes_omitted_from_device\": "
      << (primes.size() - active_primes.size()) << ",\n"
      << "  \"dense_prime_count\": " << dense_prime_count << ",\n"
      << "  \"base_prime_generation\": \""
      << (options.source_prime_roster.empty()
              ? "exact_host_eratosthenes_sieve"
              : "authenticated_canonical_u32le_roster")
      << "\",\n"
      << "  \"base_prime_source\": \""
      << (options.source_prime_roster.empty()
              ? "per_process_exact_eratosthenes"
              : "compiled_sha256_pinned_source_roster")
      << "\",\n"
      << "  \"source_prime_roster_sha256\": \""
      << (options.source_prime_roster.empty()
              ? std::string(kZeroDigest)
              : std::string(kSourcePrimeRosterSha256))
      << "\",\n"
      << "  \"device_prime_filter\": "
      << (all_primes_hit_by_interval_length
              ? "\"all_primes_hit_by_interval_length\""
              : "\"exact_first-multiple-in-half-open-segment\"")
      << ",\n"
      << "  \"active_prime_filter_skipped_by_interval_length\": "
      << (all_primes_hit_by_interval_length ? "true" : "false")
      << ",\n"
      << "  \"independent_cpu_oracle_uses_complete_base_prime_list\": true,\n"
      << "  \"hurst_single_segment_mu_row_sha256_v1\": \""
      << hurst_row_digest << "\",\n"
      << "  \"hurst_mu_commitment_block_count\": "
      << hurst_block_count << ",\n"
      << "  \"hurst_mu_commitment_worker_threads\": "
      << hurst_hash_threads << ",\n"
      << "  \"device_name\": \"" << json_escape(properties.name) << "\",\n"
      << "  \"compute_capability\": \"" << properties.major << '.'
      << properties.minor << "\",\n"
      << "  \"cuda_driver_api_version\": " << driver_version << ",\n"
      << "  \"cuda_runtime_version\": " << runtime_version << ",\n"
      << "  \"prime_generation_milliseconds\": "
      << prime_generation_milliseconds << ",\n"
      << "  \"prime_roster_load_and_authenticate_milliseconds\": "
      << prime_roster_load_and_authenticate_milliseconds << ",\n"
      << "  \"active_prime_filter_milliseconds\": "
      << active_filter_milliseconds << ",\n"
      << "  \"device_allocation_milliseconds\": "
      << allocation_milliseconds << ",\n"
      << "  \"host_to_device_transfer_milliseconds\": "
      << host_to_device_milliseconds << ",\n"
      << "  \"kernel_milliseconds\": " << kernel_milliseconds << ",\n"
      << "  \"kernel_rows_per_second\": " << rows_per_second << ",\n"
      << "  \"compact_pack_milliseconds\": "
      << compact_pack_milliseconds << ",\n"
      << "  \"affine_mq_scan_reduction_milliseconds\": "
      << affine_mq_device_milliseconds << ",\n"
      << "  \"device_to_host_transfer_milliseconds\": "
      << device_to_host_milliseconds << ",\n"
      << "  \"device_to_host_bytes\": "
      << device_to_host_bytes << ",\n"
      << "  \"device_to_host_bytes_per_row\": "
      << device_to_host_bytes / count << ",\n"
      << "  \"full_support_device_to_host_transfer\": "
      << (full_support_compared ? "true" : "false") << ",\n"
      << "  \"device_support_bytes_per_row\": "
      << device_support_bytes_per_row
      << ",\n"
      << "  \"device_support_layout\": \""
      << device_support_layout
      << "\",\n"
      << "  \"compact_support_kernel\": "
      << (options.compact_support_kernel ? "true" : "false") << ",\n"
      << "  \"compact_support_fieldwise_qualification_transfer\": "
      << (options.qualification_transfer_compact_support
              ? "true"
              : "false")
      << ",\n"
      << "  \"fused_support_kernel\": "
      << (options.fused_support_kernel ? "true" : "false") << ",\n"
      << "  \"fused_support_load_balanced_dense_schedule\": "
      << (options.fused_support_kernel &&
                  !options.qualification_legacy_one_block_dense
              ? "true"
              : "false")
      << ",\n"
      << "  \"qualification_legacy_one_block_dense\": "
      << (options.qualification_legacy_one_block_dense
              ? "true"
              : "false")
      << ",\n"
      << "  \"fused_support_residue_235_initializer\": "
      << (options.fused_support_kernel &&
                  !options.qualification_legacy_one_block_dense &&
                  !options.qualification_unseeded_fused_initializer &&
                  !options.qualification_residue_2357_seed &&
                  !options.qualification_residue_235711_seed &&
                  !options.qualification_residue_rectangular
              ? "true"
              : "false")
      << ",\n"
      << "  \"qualification_residue_2357_seed\": "
      << (options.qualification_residue_2357_seed
              ? "true"
              : "false")
      << ",\n"
      << "  \"residue_2357_initializer_uses_residue_235_table\": "
      << (options.qualification_residue_2357_seed
              ? "true"
              : "false")
      << ",\n"
      << "  \"residue_2357_per_row_modulus\": "
      << kTgMobiusResidue2357Modulus << ",\n"
      << "  \"residue_2357_materialized_table_rows\": 0,\n";
  if (options.qualification_residue_235711_seed) {
    std::cout
        << "  \"qualification_residue_235711_seed\": true,\n"
        << "  \"residue_seed_prime_count\": "
        << kTgMobiusResidue235711PrimeCount << ",\n"
        << "  \"residue_235711_initializer_uses_residue_235_table\": "
           "true,\n"
        << "  \"residue_235711_per_row_modulus\": "
        << kTgMobiusResidue235711Modulus << ",\n"
        << "  \"residue_235711_materialized_table_rows\": 0,\n"
        << "  \"residue_235711_suffix_minimum_prime\": "
        << kTgMobiusResidue235711SuffixMinimum << ",\n"
        << "  \"fused_multiblock_residue_235711_minimum_safe_slots_per_"
           "prime\": "
        << kTgMobiusResidue235711MinimumSlotsPerPrime << ",\n"
        << "  \"fused_multiblock_residue_235711_slots_per_prime\": "
        << kTgMobiusResidue235711MultiblockSlotsPerPrime << ",\n"
        << "  \"residue_235711_lean_arithmetic_contract\": "
           "\"SparkInterval.TernaryGoldbach.MobiusResidue235711\",\n";
  }
  if (options.qualification_residue_rectangular) {
    std::cout
        << "  \"qualification_receipt_domain\": \""
        << rectangular_receipt_domain << "\",\n"
        << "  \"qualification_residue_rectangular\": true,\n"
        << "  \"qualification_rectangular_seed\": \""
        << residue_seed_name(rectangular_geometry.seed) << "\",\n"
        << "  \"qualification_rectangular_mode\": \""
        << rectangular_mode_name(rectangular_geometry.mode) << "\",\n"
        << "  \"qualification_rectangular_required_slots_per_prime\": "
        << rectangular_geometry.required_slots_per_prime << ",\n"
        << "  \"qualification_rectangular_slots_per_prime\": "
        << rectangular_geometry.slots_per_prime << ",\n"
        << "  \"qualification_rectangular_events_per_block\": "
        << rectangular_geometry.events_per_block << ",\n"
        << "  \"qualification_rectangular_multiblock_prime_count\": "
        << rectangular_geometry.grid_y << ",\n"
        << "  \"qualification_rectangular_grid\": {\"x\": "
        << rectangular_geometry.grid_x << ", \"y\": "
        << rectangular_geometry.grid_y << ", \"z\": "
        << rectangular_geometry.grid_z << "},\n"
        << "  \"qualification_rectangular_threads_per_block\": "
        << rectangular_geometry.threads_per_block << ",\n"
        << "  \"qualification_rectangular_enclosing_super_shard_lower\": "
        << rectangular_geometry.enclosing_lower << ",\n"
        << "  \"qualification_rectangular_enclosing_super_shard_count\": "
        << rectangular_geometry.enclosing_count << ",\n"
        << "  \"qualification_rectangular_lean_schedule_contract\": "
           "\"SparkInterval.TernaryGoldbach."
           "MobiusRectangularCUDASchedule\",\n";
  }
  std::cout
      << "  \"qualification_unseeded_fused_initializer\": "
      << (options.qualification_unseeded_fused_initializer
              ? "true"
              : "false")
      << ",\n"
      << "  \"residue_235_initializer_table_rows\": "
      << kTgMobiusResidue235Modulus << ",\n"
      << "  \"residue_235_initializer_table_bytes\": "
      << kTgMobiusResidue235Modulus * sizeof(std::uint64_t)
      << ",\n"
      << "  \"residue_235_table_storage\": "
         "\"fatbinary_device_global_init\",\n"
      << "  \"residue_235_table_materialization_scope\": "
         "\"cuda_module_context_load\",\n"
      << "  \"residue_235_explicit_h2d_upload_bytes_per_sieve\": 0,\n"
      << "  \"fused_multiblock_dense_prime_limit\": "
      << kTgMobiusMultiblockDensePrimeLimit << ",\n"
      << "  \"fused_multiblock_slots_per_prime\": "
      << (options.fused_support_kernel &&
                  !options.qualification_legacy_one_block_dense &&
                  !options.qualification_unseeded_fused_initializer
              ? (options.qualification_residue_rectangular
                     ? rectangular_geometry.slots_per_prime
                     : options.qualification_residue_2357_seed
                     ? kTgMobiusResidue2357MultiblockSlotsPerPrime
                     : options.qualification_residue_235711_seed
                     ? kTgMobiusResidue235711MultiblockSlotsPerPrime
                     : kTgMobiusResidue235MultiblockSlotsPerPrime)
              : kTgMobiusMultiblockSlotsPerPrime)
      << ",\n"
      << "  \"fused_multiblock_unseeded_slots_per_prime\": "
      << kTgMobiusMultiblockSlotsPerPrime << ",\n"
      << "  \"fused_multiblock_residue_235_slots_per_prime\": "
      << kTgMobiusResidue235MultiblockSlotsPerPrime << ",\n"
      << "  \"fused_multiblock_residue_235_minimum_safe_slots_per_prime\": "
      << kTgMobiusResidue235MinimumSlotsPerPrime << ",\n"
      << "  \"fused_multiblock_residue_2357_minimum_safe_slots_per_prime\": "
      << kTgMobiusResidue2357MinimumSlotsPerPrime << ",\n"
      << "  \"fused_multiblock_residue_2357_slots_per_prime\": "
      << kTgMobiusResidue2357MultiblockSlotsPerPrime << ",\n"
      << "  \"fused_multiblock_iterations_per_thread\": "
      << kTgMobiusMultiblockIterationsPerThread << ",\n"
      << "  \"fused_support_fieldwise_qualification_transfer\": "
      << (options.qualification_transfer_fused_support
              ? "true"
              : "false")
      << ",\n"
      << "  \"qualification_mu_bytes_written\": "
      << (options.qualification_write_mu.empty() ? 0 : count)
      << ",\n"
      << "  \"fused_support_product_bits\": "
      << kTgMobiusFusedProductBits << ",\n"
      << "  \"fused_support_count_bits\": "
      << kTgMobiusFusedCountBits << ",\n"
      << "  \"fused_support_maximum_distinct_primes\": "
      << kTgMobiusFusedMaximumDistinctPrimes << ",\n"
      << "  \"fused_support_primorial_14\": "
      << kTgMobiusPrimorial14 << ",\n"
      << "  \"fused_support_source_limit\": "
      << kTgMobiusSourceLimit << ",\n"
      << "  \"fused_support_runtime_product_count_reserved_guards\": true,\n"
      << "  \"fused_support_poison_count\": "
      << fused_support_poison_count << ",\n"
      << "  \"fused_support_lean_arithmetic_contract\": "
         "\"SparkInterval.TernaryGoldbach.MobiusFusedSupport\",\n"
      << "  \"affine_mq_summary_transfer_milliseconds\": "
      << affine_summary_transfer_milliseconds << ",\n"
      << "  \"affine_mq_host_exact_finalize_milliseconds\": "
      << affine_finalize_milliseconds << ",\n"
      << "  \"affine_mq_prefix_device_bytes\": "
      << (options.affine_mq_gpu_prototype
              ? count * sizeof(TgMobiusPrefixMQ)
              : 0)
      << ",\n"
      << "  \"affine_mq_prefix_mertens_bits\": 32,\n"
      << "  \"affine_mq_prefix_squarefree_bits\": 32,\n"
      << "  \"affine_mq_prefix_maximum_rows\": 100000000,\n"
      << "  \"affine_mq_thread_extrema_per_record\": 4,\n"
      << "  \"affine_mq_candidate_local_squarefree_bits\": 32,\n"
      << "  \"affine_mq_candidate_order_bits\": 32,\n"
      << "  \"affine_mq_candidate_witness_derived_from_lower_and_order\": true,\n"
      << "  \"affine_mq_candidate_device_bytes\": "
      << (options.affine_mq_gpu_prototype
              ? affine_candidate_count *
                    sizeof(TgMobiusAffineMqThreadCandidates)
              : 0)
      << ",\n"
      << "  \"affine_mq_workspace_device_bytes\": "
      << (options.affine_mq_gpu_prototype
              ? affine_workspace_bytes
              : 0)
      << ",\n"
      << "  \"affine_mq_delta_mertens\": ";
  if (affine_summary.present) {
    std::cout << affine_summary.delta.mertens;
  } else {
    std::cout << "null";
  }
  std::cout << ",\n  \"affine_mq_delta_squarefree\": ";
  if (affine_summary.present) {
    std::cout << affine_summary.delta.squarefree;
  } else {
    std::cout << "null";
  }
  std::cout << ",\n  \"affine_mq_hurst_guard\": ";
  if (affine_summary.present) {
    std::cout
        << "{\"lower\":" << affine_summary.hurst_lower.value
        << ",\"lower_witness\":"
        << affine_summary.hurst_lower.witness_y
        << ",\"upper\":" << affine_summary.hurst_upper.value
        << ",\"upper_witness\":"
        << affine_summary.hurst_upper.witness_y << '}';
  } else {
    std::cout << "null";
  }
  std::cout << ",\n  \"affine_mq_squarefree_guard\": ";
  if (affine_summary.present) {
    std::cout
        << "{\"lower\":" << affine_summary.squarefree_lower.value
        << ",\"lower_witness\":"
        << affine_summary.squarefree_lower.witness_y
        << ",\"lower_side\":\""
        << ((affine_summary.squarefree_lower.order & 1U) == 0
                ? "integer"
                : "right_limit")
        << "\",\"upper\":" << affine_summary.squarefree_upper.value
        << ",\"upper_witness\":"
        << affine_summary.squarefree_upper.witness_y
        << ",\"upper_side\":\""
        << ((affine_summary.squarefree_upper.order & 1U) == 0
                ? "integer"
                : "right_limit")
        << "\"}";
  } else {
    std::cout << "null";
  }
  std::cout
      << ",\n  \"affine_mq_squarefree_endpoint_arithmetic\": "
         "\"exact_u128_sqrt_bracket_then_u256_boundary_q_minus_1_q_plus_1_before_reduction\",\n"
      << "  \"affine_mq_conservative_interval_arithmetic\": "
         "\"exact_source_shaped_u128_numerators_two_divisions_per_endpoint\",\n"
      << "  \"affine_mq_exact_corrects_every_squarefree_endpoint\": "
      << (options.affine_mq_gpu_prototype ? "true" : "false") << ",\n"
      << "  \"affine_mq_u256_used_only_in_exact_boundary_strip\": "
      << (options.affine_mq_gpu_prototype ? "true" : "false") << ",\n"
      << "  \"affine_mq_host_rechecks_all_thread_squarefree_extrema\": "
      << (options.affine_mq_gpu_prototype ? "true" : "false") << ",\n"
      << "  \"affine_mq_fixed_top_k_used_for_acceptance\": false,\n"
      << "  \"affine_mq_prototype_covers_little_mertens\": false,\n"
      << "  \"affine_mq_prototype_full_source_range\": false,\n"
      << "  \"affine_mq_prototype_execution_attested\": false,\n"
      << "  \"affine_mq_prototype_lean_atom_discharged\": false,\n"
      << "  \"independent_cpu_sieve_milliseconds\": "
      << independent_sieve_milliseconds << ",\n"
      << "  \"record_comparison_and_hash_milliseconds\": "
      << comparison_and_hash_milliseconds << ",\n"
      << "  \"guard_fold_milliseconds\": "
      << guard_fold_milliseconds << ",\n"
      << "  \"independent_cpu_check_and_exact_bounds_milliseconds\": "
      << host_milliseconds << ",\n"
      << "  \"process_milliseconds_before_json_render\": "
      << std::chrono::duration<double, std::milli>(
             std::chrono::steady_clock::now() - process_start).count()
      << ",\n"
      << "  \"single_receipt_covers_full_1e16_range\": false,\n"
      << "  \"single_receipt_covers_full_little_mertens_2_11_range\": false,\n"
      << "  \"single_receipt_covers_full_little_mertens_stronger_range\": false,\n"
      << "  \"checks_hurst_source_shape_conditionally\": true,\n"
      << "  \"checks_cdem_squarefree_source_shape_conditionally\": true,\n"
      << "  \"checks_little_mertens_source_shape_conditionally\": true,\n"
      << "  \"has_complete_1e16_receipt_chain\": false,\n"
      << "  \"has_complete_little_mertens_2_11_receipt_chain\": false,\n"
      << "  \"has_complete_little_mertens_stronger_receipt_chain\": false,\n"
      << "  \"proves_mertens_hurst_external_atom\": false,\n"
      << "  \"proves_cdem_squarefree_external_atom\": false,\n"
      << "  \"proves_little_mertens_2_11_external_atom\": false,\n"
      << "  \"proves_little_mertens_stronger_external_atom\": false,\n"
      << "  \"proves_any_external_atom\": false\n"
      << "}\n";
  return compared_output_passed ? 0 : 5;
}

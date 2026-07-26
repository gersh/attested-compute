// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Native producer stage for the Helfgott--Platt prime ladder
// (arXiv:1305.3062v2, Sections 2--4).
//
// This program is deliberately only a producer.  It sieves the arithmetic
// progression k*2^n+1 by every prime below 16000 and applies the paper's
// ordered small-witness Proth test using GMP.  The historical default is
// n=52; a reviewed campaign may bind another explicit exponent.  It writes a compact deterministic
// stream which is replayed independently with Python's integer arithmetic
// before any rung enters a campaign range.  If a ladder step contains no
// accepted Proth prime, the stream ends with an explicit open general-prime
// obligation.  It never labels a probable prime as prime.

#include <gmp.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#ifndef SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE_SHA256
#error "native Goldbach ladder producer must bind its reviewed source digest"
#endif

namespace {

using u128 = unsigned __int128;

constexpr std::uint64_t kDefaultProthExponent = 52;
constexpr std::uint32_t kSieveBound = 16'000;
constexpr u128 kSourceMaximumGap = static_cast<u128>(4'000'000'000'000'000'000ULL);
// Intervals certified by a rung p are [p+4,p+4e18].  This two-smaller step
// is the repository's stronger condition which makes adjacent odd intervals
// overlap or touch without a parity off-by-two gap.
constexpr u128 kSourceCoverageStep =
    kSourceMaximumGap - static_cast<u128>(2);
constexpr std::uint64_t kDefaultBlockCandidates = UINT64_C(1) << 24;
constexpr std::array<unsigned long, 10> kWitnesses = {
    2UL, 3UL, 5UL, 7UL, 11UL, 13UL, 17UL, 19UL, 23UL, 29UL};
constexpr std::array<char, 8> kMagic = {'T', 'G', 'N', 'P', 'L', 'D', '1', '\n'};

struct Options {
  u128 anchor = 0;
  u128 target = 0;
  u128 coverageStep = kSourceCoverageStep;
  std::uint64_t prothExponent = kDefaultProthExponent;
  std::uint64_t blockCandidates = kDefaultBlockCandidates;
  std::filesystem::path output;
};

struct Rung {
  std::uint64_t k = 0;
  std::uint8_t witness = 0;
};

struct SearchStatistics {
  std::uint64_t blocksSieved = 0;
  std::uint64_t candidatesSieved = 0;
  std::uint64_t candidatesExamined = 0;
  std::uint64_t sieveSurvivorsTested = 0;
};

struct SegmentResult {
  std::vector<Rung> rungs;
  bool complete = false;
  u128 lastNumber = 0;
  u128 holeLowerExclusive = 0;
  u128 holeUpperInclusive = 0;
  SearchStatistics statistics;
};

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error(message);
}

bool parseU64(std::string_view text, std::uint64_t* output) {
  if (text.empty()) return false;
  const char* begin = text.data();
  const char* end = begin + text.size();
  const auto parsed = std::from_chars(begin, end, *output, 10);
  return parsed.ec == std::errc{} && parsed.ptr == end;
}

bool parseU128(std::string_view text, u128* output) {
  if (text.empty()) return false;
  constexpr u128 maximum = ~static_cast<u128>(0);
  u128 value = 0;
  for (const char character : text) {
    if (character < '0' || character > '9') return false;
    const unsigned int digit = static_cast<unsigned int>(character - '0');
    if (value > (maximum - digit) / 10) return false;
    value = value * 10 + digit;
  }
  *output = value;
  return true;
}

std::string toString(u128 value) {
  if (value == 0) return "0";
  std::string result;
  while (value != 0) {
    result.push_back(static_cast<char>('0' + value % 10));
    value /= 10;
  }
  std::reverse(result.begin(), result.end());
  return result;
}

Options parseOptions(int argc, char** argv) {
  Options options;
  bool haveAnchor = false;
  bool haveTarget = false;
  bool haveOutput = false;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    auto value = [&](const char* name) -> std::string_view {
      if (++index >= argc) fail(std::string(name) + " requires a value");
      return argv[index];
    };
    if (argument == "--anchor-number") {
      if (!parseU128(value("--anchor-number"), &options.anchor)) {
        fail("--anchor-number must be an unsigned decimal integer");
      }
      haveAnchor = true;
    } else if (argument == "--target-number") {
      if (!parseU128(value("--target-number"), &options.target)) {
        fail("--target-number must be an unsigned decimal integer");
      }
      haveTarget = true;
    } else if (argument == "--coverage-step") {
      if (!parseU128(value("--coverage-step"), &options.coverageStep)) {
        fail("--coverage-step must be an unsigned decimal integer");
      }
    } else if (argument == "--proth-exponent") {
      if (!parseU64(value("--proth-exponent"), &options.prothExponent)) {
        fail("--proth-exponent must be an unsigned decimal integer");
      }
    } else if (argument == "--sieve-block-candidates") {
      if (!parseU64(value("--sieve-block-candidates"),
                    &options.blockCandidates)) {
        fail("--sieve-block-candidates must be an unsigned decimal integer");
      }
    } else if (argument == "--output") {
      options.output = std::string(value("--output"));
      haveOutput = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-tg-goldbach-ladder-native "
             "--anchor-number N --target-number N --output PATH "
             "[--coverage-step N] [--proth-exponent N] "
             "[--sieve-block-candidates N]\n"
             "The output is a deterministic Proth-rung stream.  A complete=false "
             "stream is a fail-closed request for a certified general prime.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (!haveAnchor || !haveTarget || !haveOutput) {
    fail("--anchor-number, --target-number, and --output are required");
  }
  if (options.anchor < 3 || options.target <= options.anchor ||
      options.coverageStep == 0) {
    fail("require 3 <= anchor-number < target-number and a positive coverage-step");
  }
  if (options.prothExponent == 0 || options.prothExponent > 63) {
    fail("--proth-exponent must lie in [1,63]");
  }
  // k < 2^n is the defining Proth guard committed by the campaign.
  const std::uint64_t prothPower =
      UINT64_C(1) << options.prothExponent;
  const u128 largestProth =
      (static_cast<u128>(prothPower) - 1) * prothPower + 1;
  if (options.target > largestProth) {
    fail("target exceeds the fixed-exponent Proth domain");
  }
  if (options.blockCandidates < 1024 ||
      options.blockCandidates > UINT64_C(1) << 30) {
    fail("--sieve-block-candidates must lie in [1024,1073741824]");
  }
  if (options.output.empty() || std::filesystem::exists(options.output)) {
    fail("output path must be nonempty and must not already exist");
  }
  return options;
}

std::vector<std::uint32_t> primesBelow(std::uint32_t bound) {
  std::vector<bool> composite(bound, false);
  std::vector<std::uint32_t> primes;
  for (std::uint32_t candidate = 2; candidate < bound; ++candidate) {
    if (composite[candidate]) continue;
    primes.push_back(candidate);
    if (candidate > (bound - 1) / candidate) continue;
    for (std::uint32_t multiple = candidate * candidate; multiple < bound;
         multiple += candidate) {
      composite[multiple] = true;
    }
  }
  return primes;
}

std::uint32_t inverseMod(std::uint32_t value, std::uint32_t modulus) {
  std::int64_t oldR = value;
  std::int64_t r = modulus;
  std::int64_t oldS = 1;
  std::int64_t s = 0;
  while (r != 0) {
    const std::int64_t quotient = oldR / r;
    const std::int64_t nextR = oldR - quotient * r;
    oldR = r;
    r = nextR;
    const std::int64_t nextS = oldS - quotient * s;
    oldS = s;
    s = nextS;
  }
  if (oldR != 1) fail("noninvertible sieve residue");
  oldS %= modulus;
  if (oldS < 0) oldS += modulus;
  return static_cast<std::uint32_t>(oldS);
}

struct SievePrime {
  std::uint32_t prime = 0;
  std::uint32_t forbiddenResidue = 0;
};

std::vector<SievePrime> sourceSievePrimes(std::uint64_t prothExponent) {
  std::vector<SievePrime> result;
  for (const std::uint32_t prime : primesBelow(kSieveBound)) {
    if (prime == 2) continue;  // k*2^n+1 is always odd.
    std::uint32_t power = 1;
    for (std::uint64_t bit = 0; bit < prothExponent; ++bit) {
      power = static_cast<std::uint32_t>(
          (static_cast<std::uint64_t>(power) * 2) % prime);
    }
    const std::uint32_t inverse = inverseMod(power, prime);
    result.push_back(SievePrime{prime, static_cast<std::uint32_t>(prime - inverse)});
  }
  return result;
}

struct SieveBlock {
  std::uint64_t begin = 0;
  std::uint64_t end = 0;
  std::vector<std::uint8_t> survivor;
};

class ProgressionSieve {
 public:
  ProgressionSieve(std::uint64_t blockCandidates, std::uint64_t prothPower,
                   std::uint64_t prothExponent,
                   SearchStatistics* statistics)
      : blockCandidates_(blockCandidates),
        prothPower_(prothPower),
        primes_(sourceSievePrimes(prothExponent)),
        statistics_(statistics) {}

  bool survives(std::uint64_t k) {
    const std::uint64_t begin = (k / blockCandidates_) * blockCandidates_;
    for (const SieveBlock& block : cache_) {
      if (block.begin == begin) {
        return block.survivor[static_cast<std::size_t>(k - begin)] != 0;
      }
    }
    makeBlock(begin);
    return cache_.back().survivor[static_cast<std::size_t>(k - begin)] != 0;
  }

 private:
  void makeBlock(std::uint64_t begin) {
    const std::uint64_t prothKLimit = prothPower_;
    const std::uint64_t count =
        std::min(blockCandidates_, prothKLimit - begin);
    SieveBlock block;
    block.begin = begin;
    block.end = begin + count;
    block.survivor.assign(static_cast<std::size_t>(count), 1);
    if (begin == 0 && count != 0) block.survivor[0] = 0;  // q=1.
    for (const SievePrime entry : primes_) {
      const std::uint64_t prime = entry.prime;
      const std::uint64_t residue = begin % prime;
      const std::uint64_t offset =
          (entry.forbiddenResidue + prime - residue) % prime;
      for (std::uint64_t position = offset; position < count; position += prime) {
        block.survivor[static_cast<std::size_t>(position)] = 0;
      }
    }
    ++statistics_->blocksSieved;
    statistics_->candidatesSieved += count;
    if (cache_.size() == 2) cache_.erase(cache_.begin());
    cache_.push_back(std::move(block));
  }

  std::uint64_t blockCandidates_;
  std::uint64_t prothPower_;
  std::vector<SievePrime> primes_;
  SearchStatistics* statistics_;
  std::vector<SieveBlock> cache_;
};

class ProthTester {
 public:
  ProthTester(std::uint64_t prothExponent, std::uint64_t prothPower)
      : prothExponent_(prothExponent), prothPower_(prothPower) {
    mpz_inits(k_, number_, exponent_, base_, residue_, minusOne_, nullptr);
  }

  ~ProthTester() {
    mpz_clears(k_, number_, exponent_, base_, residue_, minusOne_, nullptr);
  }

  ProthTester(const ProthTester&) = delete;
  ProthTester& operator=(const ProthTester&) = delete;

  bool test(std::uint64_t k, std::uint8_t* acceptedWitness) {
    if (k == 0 || k >= prothPower_) return false;
    mpz_set_ui(k_, k);
    mpz_mul_2exp(number_, k_, prothExponent_);
    mpz_add_ui(number_, number_, 1);
    mpz_sub_ui(exponent_, number_, 1);
    mpz_fdiv_q_2exp(exponent_, exponent_, 1);
    mpz_sub_ui(minusOne_, number_, 1);
    for (const unsigned long witness : kWitnesses) {
      mpz_set_ui(base_, witness);
      if (mpz_jacobi(base_, number_) != -1) continue;
      mpz_powm(residue_, base_, exponent_, number_);
      if (mpz_cmp(residue_, minusOne_) == 0) {
        *acceptedWitness = static_cast<std::uint8_t>(witness);
        return true;
      }
      // Match Algorithm 2 exactly: only the first bounded quadratic
      // non-residue is used for the modular-power test.
      return false;
    }
    return false;
  }

 private:
  std::uint64_t prothExponent_;
  std::uint64_t prothPower_;
  mpz_t k_;
  mpz_t number_;
  mpz_t exponent_;
  mpz_t base_;
  mpz_t residue_;
  mpz_t minusOne_;
};

u128 prothNumber(std::uint64_t k, std::uint64_t prothPower) {
  return static_cast<u128>(k) * prothPower + 1;
}

bool findLargestProth(u128 lowerExclusive, u128 upperInclusive,
                      std::uint64_t prothPower,
                      ProgressionSieve* sieve, ProthTester* tester,
                      SearchStatistics* statistics, Rung* output) {
  if (upperInclusive <= lowerExclusive) return false;
  const u128 maximumK128 = (upperInclusive - 1) / prothPower;
  const u128 excludedK128 = (lowerExclusive - 1) / prothPower;
  if (maximumK128 >= prothPower) fail("candidate violates k < 2^n");
  if (maximumK128 <= excludedK128) return false;
  const std::uint64_t maximumK = static_cast<std::uint64_t>(maximumK128);
  const std::uint64_t excludedK = static_cast<std::uint64_t>(excludedK128);
  for (std::uint64_t k = maximumK; k > excludedK; --k) {
    ++statistics->candidatesExamined;
    if (!sieve->survives(k)) continue;
    ++statistics->sieveSurvivorsTested;
    std::uint8_t witness = 0;
    if (tester->test(k, &witness)) {
      *output = Rung{k, witness};
      return true;
    }
  }
  return false;
}

SegmentResult produce(const Options& options) {
  SegmentResult result;
  result.lastNumber = options.anchor;
  const std::uint64_t prothPower = UINT64_C(1) << options.prothExponent;
  ProgressionSieve sieve(options.blockCandidates, prothPower,
                         options.prothExponent, &result.statistics);
  ProthTester tester(options.prothExponent, prothPower);
  while (options.target - result.lastNumber > options.coverageStep) {
    const u128 upper = result.lastNumber + options.coverageStep;
    Rung rung;
    if (!findLargestProth(result.lastNumber, upper, prothPower, &sieve, &tester,
                          &result.statistics, &rung)) {
      result.complete = false;
      result.holeLowerExclusive = result.lastNumber;
      result.holeUpperInclusive = upper;
      return result;
    }
    const u128 number = prothNumber(rung.k, prothPower);
    if (!(result.lastNumber < number && number <= upper)) {
      fail("internal ladder-step range violation");
    }
    result.rungs.push_back(rung);
    result.lastNumber = number;
  }
  result.complete = true;
  return result;
}

std::string boolString(bool value) { return value ? "true" : "false"; }

std::string protocolHeader(const Options& options, const SegmentResult& result) {
  const std::string holeLower = result.complete
                                    ? "null"
                                    : "\"" + toString(result.holeLowerExclusive) + "\"";
  const std::string holeUpper = result.complete
                                    ? "null"
                                    : "\"" + toString(result.holeUpperInclusive) + "\"";
  return
      "{\"anchor_number\":\"" + toString(options.anchor) +
      "\",\"complete\":" + boolString(result.complete) +
      ",\"coverage_step\":\"" + toString(options.coverageStep) +
      "\",\"gmp_version\":\"" + std::string(gmp_version) +
      "\",\"hole_lower_exclusive\":" + holeLower +
      ",\"hole_upper_inclusive\":" + holeUpper +
      ",\"kind\":\"tg_goldbach_native_proth_segment_v1\""
      ",\"last_number\":\"" + toString(result.lastNumber) +
      "\",\"proth_exponent\":" + std::to_string(options.prothExponent) +
      ",\"record_count\":" + std::to_string(result.rungs.size()) +
      ",\"sieve_bound\":16000"
      ",\"source_sha256\":\"" +
      std::string(SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE_SHA256) +
      "\",\"target_number\":\"" + toString(options.target) +
      "\",\"witnesses\":[2,3,5,7,11,13,17,19,23,29]}\n";
}

void writeU64LittleEndian(std::ostream& stream, std::uint64_t value) {
  for (unsigned int byte = 0; byte < 8; ++byte) {
    stream.put(static_cast<char>((value >> (8 * byte)) & 0xff));
  }
}

void writeVarint(std::ostream& stream, std::uint64_t value) {
  while (value >= 0x80) {
    stream.put(static_cast<char>((value & 0x7f) | 0x80));
    value >>= 7;
  }
  stream.put(static_cast<char>(value));
}

void writeProtocol(const Options& options, const SegmentResult& result) {
  const std::string header = protocolHeader(options, result);
  if (header.size() > std::numeric_limits<std::uint64_t>::max()) {
    fail("protocol header is too large");
  }
  const std::filesystem::path temporary =
      options.output.string() + ".temporary";
  if (std::filesystem::exists(temporary)) {
    fail("temporary output path already exists");
  }
  try {
    std::ofstream stream(temporary, std::ios::binary | std::ios::out);
    if (!stream) fail("cannot create protocol output");
    stream.write(kMagic.data(), static_cast<std::streamsize>(kMagic.size()));
    writeU64LittleEndian(stream, static_cast<std::uint64_t>(header.size()));
    stream.write(header.data(), static_cast<std::streamsize>(header.size()));
    std::uint64_t previousK = 0;
    for (const Rung rung : result.rungs) {
      if (rung.k <= previousK) fail("rung k values are not strictly increasing");
      writeVarint(stream, rung.k - previousK);
      stream.put(static_cast<char>(rung.witness));
      previousK = rung.k;
    }
    stream.flush();
    if (!stream) fail("failed while writing protocol output");
    stream.close();
    std::filesystem::rename(temporary, options.output);
  } catch (...) {
    std::error_code ignored;
    std::filesystem::remove(temporary, ignored);
    throw;
  }
}

std::string secondsString(double seconds) {
  std::string result = std::to_string(seconds);
  while (result.size() > 1 && result.back() == '0') result.pop_back();
  if (!result.empty() && result.back() == '.') result.push_back('0');
  return result;
}

void printReport(const SegmentResult& result, double elapsedSeconds) {
  // This report is benchmark metadata, not part of the deterministic stream.
  std::cout
      << "{\"blocks_sieved\":" << result.statistics.blocksSieved
      << ",\"candidates_examined\":" << result.statistics.candidatesExamined
      << ",\"candidates_sieved\":" << result.statistics.candidatesSieved
      << ",\"complete\":" << boolString(result.complete)
      << ",\"elapsed_seconds\":\"" << secondsString(elapsedSeconds)
      << "\",\"kind\":\"tg_goldbach_native_proth_report_v1\""
      << ",\"record_count\":" << result.rungs.size()
      << ",\"sieve_survivors_tested\":"
      << result.statistics.sieveSurvivorsTested << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parseOptions(argc, argv);
    const auto start = std::chrono::steady_clock::now();
    const SegmentResult result = produce(options);
    writeProtocol(options, result);
    const double elapsed = std::chrono::duration<double>(
                               std::chrono::steady_clock::now() - start)
                               .count();
    printReport(result, elapsed);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "goldbach-ladder-native: " << error.what() << '\n';
    return 2;
  }
}

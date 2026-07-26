// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Exact, source-range scheduler and segmented factorization stage for the
// finite computation in Helfgott Proposition 12.2.4.
//
// This stage does not claim the analytic inequality.  It removes the
// unscalable per-q trial division from the directed verifier and emits a
// deterministic commitment to complete prime factorizations and phi(q).
// Every factor is drawn from an Eratosthenes prime table and the residual is
// divided to completion, so accepting a row never depends on a probable-prime
// test or on floating-point arithmetic.

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#include "sparkinterval/sha256.hpp"

namespace {

using u128 = unsigned __int128;

constexpr std::uint64_t kDenseQUpperExclusive = 3'300'000'000ULL;
constexpr std::uint64_t kExtensionQUpperExclusive = 22'000'000'000ULL;
constexpr std::uint64_t kExtensionDivisor = 210ULL;
constexpr std::uint64_t kDenseRows = kDenseQUpperExclusive - 1ULL;
constexpr std::uint64_t kFirstExtensionQ = 3'300'000'060ULL;
constexpr std::uint64_t kSourceRows = 3'389'047'618ULL;
constexpr std::uint64_t kDefaultBlockRows = 1ULL << 18;
constexpr std::size_t kMaxDistinctFactors = 16;
constexpr char kDigestDomain[] =
    "sparkinterval/tg/prop1224/factor-rows/v1\0";

struct Options {
  std::uint64_t rankLower = 0;
  std::uint64_t rankUpper = 0;
  std::uint64_t blockRows = kDefaultBlockRows;
};

struct FactorRow {
  std::uint64_t q = 0;
  std::uint64_t phi = 0;
  std::array<std::uint64_t, kMaxDistinctFactors> factors{};
  std::uint8_t factorCount = 0;
};

bool parseUint64(std::string_view text, std::uint64_t& result) {
  if (text.empty()) return false;
  const char* first = text.data();
  const char* last = first + text.size();
  const auto parsed = std::from_chars(first, last, result, 10);
  return parsed.ec == std::errc{} && parsed.ptr == last;
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

std::uint64_t floorSqrt(std::uint64_t value) {
  std::uint64_t root = static_cast<std::uint64_t>(
      std::sqrt(static_cast<long double>(value)));
  while (static_cast<u128>(root + 1) * (root + 1) <= value) ++root;
  while (static_cast<u128>(root) * root > value) --root;
  return root;
}

std::vector<std::uint32_t> primesThrough(std::uint64_t upper) {
  if (upper > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error("prime-table endpoint exceeds uint32");
  }
  std::vector<bool> composite(static_cast<std::size_t>(upper) + 1, false);
  std::vector<std::uint32_t> primes;
  for (std::uint64_t n = 2; n <= upper; ++n) {
    if (composite[n]) continue;
    primes.push_back(static_cast<std::uint32_t>(n));
    if (n > upper / n) continue;
    for (std::uint64_t multiple = n * n; multiple <= upper; multiple += n) {
      composite[multiple] = true;
    }
  }
  return primes;
}

void appendFactor(FactorRow& row, std::uint64_t prime) {
  if (row.factorCount != 0 &&
      row.factors[static_cast<std::size_t>(row.factorCount) - 1] == prime) {
    return;
  }
  if (row.factorCount >= row.factors.size()) {
    throw std::runtime_error("distinct-factor capacity exceeded");
  }
  row.factors[row.factorCount++] = prime;
}

// Factor the consecutive integers base, ..., base+count-1.  qScale is one
// for the dense source portion and 210 for the extension.  In the latter
// case we factor m=q/210 and merge the four fixed prime divisors of 210.
std::vector<FactorRow> factorConsecutive(std::uint64_t base,
                                         std::uint64_t count,
                                         std::uint64_t qScale,
                                         const std::vector<std::uint32_t>& primes) {
  if (count == 0 || base == 0 || qScale == 0 ||
      count > std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("invalid segmented-factor range");
  }
  std::vector<std::uint64_t> remainder(static_cast<std::size_t>(count));
  std::vector<FactorRow> rows(static_cast<std::size_t>(count));
  for (std::uint64_t index = 0; index < count; ++index) {
    const std::uint64_t source = base + index;
    if (source > std::numeric_limits<std::uint64_t>::max() / qScale) {
      throw std::runtime_error("q scheduler overflow");
    }
    remainder[index] = source;
    rows[index].q = source * qScale;
  }

  for (const std::uint64_t prime : primes) {
    std::uint64_t first = base;
    const std::uint64_t residue = base % prime;
    if (residue != 0) {
      const std::uint64_t advance = prime - residue;
      if (advance >= count) continue;
      first += advance;
    }
    const std::uint64_t last = base + count - 1;
    for (std::uint64_t value = first;; value += prime) {
      const std::size_t index = static_cast<std::size_t>(value - base);
      appendFactor(rows[index], prime);
      while (remainder[index] % prime == 0) remainder[index] /= prime;
      if (prime > last - value) break;
    }
  }

  for (std::size_t index = 0; index < rows.size(); ++index) {
    if (remainder[index] > 1) appendFactor(rows[index], remainder[index]);
    if (qScale == kExtensionDivisor) {
      std::array<std::uint64_t, kMaxDistinctFactors> merged{};
      std::size_t mergedCount = 0;
      constexpr std::array<std::uint64_t, 4> fixed = {2, 3, 5, 7};
      std::size_t left = 0;
      std::size_t right = 0;
      while (left < fixed.size() || right < rows[index].factorCount) {
        const std::uint64_t a = left < fixed.size()
                                    ? fixed[left]
                                    : std::numeric_limits<std::uint64_t>::max();
        const std::uint64_t b = right < rows[index].factorCount
                                    ? rows[index].factors[right]
                                    : std::numeric_limits<std::uint64_t>::max();
        const std::uint64_t next = std::min(a, b);
        if (mergedCount == 0 || merged[mergedCount - 1] != next) {
          if (mergedCount == merged.size()) {
            throw std::runtime_error("merged distinct-factor capacity exceeded");
          }
          merged[mergedCount++] = next;
        }
        if (a == next) ++left;
        if (b == next) ++right;
      }
      rows[index].factors = merged;
      rows[index].factorCount = static_cast<std::uint8_t>(mergedCount);
    }

    std::uint64_t phi = rows[index].q;
    for (std::size_t position = 0; position < rows[index].factorCount;
         ++position) {
      const std::uint64_t prime = rows[index].factors[position];
      if (prime < 2 || rows[index].q % prime != 0) {
        throw std::runtime_error("factor row failed exact divisibility replay");
      }
      if (position != 0 && rows[index].factors[position - 1] >= prime) {
        throw std::runtime_error("factor row is not strictly increasing");
      }
      phi -= phi / prime;
    }
    rows[index].phi = phi;
  }
  return rows;
}

std::uint64_t qAtRank(std::uint64_t rank) {
  if (rank > kSourceRows) throw std::runtime_error("q rank exceeds source rows");
  if (rank == kSourceRows) return kExtensionQUpperExclusive;
  if (rank < kDenseRows) return rank + 1;
  return kFirstExtensionQ + (rank - kDenseRows) * kExtensionDivisor;
}

Options parseOptions(int argc, char** argv) {
  Options options;
  bool haveLower = false;
  bool haveUpper = false;
  for (int index = 1; index < argc; ++index) {
    const std::string_view name(argv[index]);
    if (index + 1 >= argc) throw std::runtime_error("missing option value");
    std::uint64_t value = 0;
    if (!parseUint64(argv[++index], value)) {
      throw std::runtime_error("option value is not an unsigned decimal integer");
    }
    if (name == "--rank-lower") {
      options.rankLower = value;
      haveLower = true;
    } else if (name == "--rank-upper") {
      options.rankUpper = value;
      haveUpper = true;
    } else if (name == "--block-rows") {
      options.blockRows = value;
    } else {
      throw std::runtime_error("unknown option: " + std::string(name));
    }
  }
  if (!haveLower || !haveUpper) {
    throw std::runtime_error("--rank-lower and --rank-upper are required");
  }
  if (options.rankLower >= options.rankUpper ||
      options.rankUpper > kSourceRows || options.blockRows == 0 ||
      options.blockRows > 100'000'000ULL) {
    throw std::runtime_error(
        "require 0 <= rank-lower < rank-upper <= 3389047618 and "
        "1 <= block-rows <= 100000000");
  }
  return options;
}

void hashRow(sparkinterval::detail::Sha256& digest, std::uint64_t rank,
             const FactorRow& row) {
  std::ostringstream line;
  line << "Q:" << rank << ':' << row.q << ':' << row.phi << ':';
  for (std::size_t position = 0; position < row.factorCount; ++position) {
    if (position != 0) line << ',';
    line << row.factors[position];
  }
  line << '\n';
  const std::string encoded = line.str();
  digest.update(encoded.data(), encoded.size());
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parseOptions(argc, argv);
    const auto started = std::chrono::steady_clock::now();
    const std::uint64_t maxDenseQ =
        options.rankLower < kDenseRows
            ? std::min(options.rankUpper, kDenseRows)
            : 0;
    const std::uint64_t maxExtensionM =
        options.rankUpper > kDenseRows
            ? qAtRank(options.rankUpper - 1) / kExtensionDivisor
            : 0;
    const std::uint64_t primeLimit = floorSqrt(
        std::max(maxDenseQ, maxExtensionM));
    const std::vector<std::uint32_t> primes = primesThrough(primeLimit);

    sparkinterval::detail::Sha256 digest;
    digest.update(kDigestDomain, sizeof(kDigestDomain) - 1);
    std::uint64_t rank = options.rankLower;
    std::uint64_t maxFactorCount = 0;
    u128 phiSum = 0;
    while (rank < options.rankUpper) {
      const bool dense = rank < kDenseRows;
      const std::uint64_t regimeEnd = dense ? kDenseRows : options.rankUpper;
      const std::uint64_t count = std::min(
          options.blockRows, std::min(options.rankUpper, regimeEnd) - rank);
      const std::uint64_t firstQ = qAtRank(rank);
      const std::uint64_t scale = dense ? 1 : kExtensionDivisor;
      const std::uint64_t base = firstQ / scale;
      const std::vector<FactorRow> rows =
          factorConsecutive(base, count, scale, primes);
      for (std::size_t index = 0; index < rows.size(); ++index) {
        const std::uint64_t expectedQ = qAtRank(rank + index);
        if (rows[index].q != expectedQ) {
          throw std::runtime_error("segmented rows disagree with exact q scheduler");
        }
        hashRow(digest, rank + index, rows[index]);
        phiSum += rows[index].phi;
        maxFactorCount = std::max<std::uint64_t>(maxFactorCount,
                                                rows[index].factorCount);
      }
      rank += count;
    }

    const std::string rowRoot =
        sparkinterval::lowercase_hex(digest.finish());
    const double seconds = std::chrono::duration<double>(
                               std::chrono::steady_clock::now() - started)
                               .count();
    const std::uint64_t rows = options.rankUpper - options.rankLower;
    std::cout << "{\n"
              << "  \"algorithm\": \"prop1224-exact-segmented-factor-shard-v1\",\n"
              << "  \"classification\": \"exact-structural-prefilter-not-final-inequality\",\n"
              << "  \"rank_lower\": " << options.rankLower << ",\n"
              << "  \"rank_upper\": " << options.rankUpper << ",\n"
              << "  \"work_count\": " << rows << ",\n"
              << "  \"first_q\": " << qAtRank(options.rankLower) << ",\n"
              << "  \"next_q\": " << qAtRank(options.rankUpper) << ",\n"
              << "  \"row_encoding\": \"Q:rank:q:phi:sorted-distinct-primes\\n\",\n"
              << "  \"row_root_sha256\": \"" << rowRoot << "\",\n"
              << "  \"phi_sum\": \"" << toString(phiSum) << "\",\n"
              << "  \"max_distinct_factor_count\": " << maxFactorCount << ",\n"
              << "  \"prime_table_limit\": " << primeLimit << ",\n"
              << "  \"block_rows\": " << options.blockRows << ",\n"
              << "  \"elapsed_seconds\": " << seconds << ",\n"
              << "  \"rows_per_second\": "
              << (seconds == 0.0 ? 0.0 : static_cast<double>(rows) / seconds)
              << "\n}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "Proposition 12.2.4 factor shard error: " << error.what()
              << '\n';
    return 2;
  }
}

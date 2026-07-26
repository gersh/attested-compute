// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Qualification-only differential harness for replacing the first eight
// literal word-owner clears (primes 3 through 23) with one packed odd-residue
// wheel.  This file is not included by any production source.

#if !defined(SPARKINTERVAL_ENABLE_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION) || \
    SPARKINTERVAL_ENABLE_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION != 1
#error "the Goldbach through-23 word-owner wheel is qualification-only"
#endif

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "sparkinterval/sha256.hpp"

namespace {

#ifndef SPARKINTERVAL_CMAKE_BUILD_CONFIG
#define SPARKINTERVAL_CMAKE_BUILD_CONFIG "unreported"
#endif

constexpr std::string_view kBuildProfile =
    SPARKINTERVAL_CMAKE_BUILD_CONFIG;
#ifdef NDEBUG
constexpr bool kNdebugDefined = true;
#else
constexpr bool kNdebugDefined = false;
#endif
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
constexpr bool kStrictH100Target = true;
#else
constexpr bool kStrictH100Target = false;
#endif

constexpr unsigned kThreads = 256U;
constexpr std::uint32_t kWordOwnerCutoff = 2'039U;
constexpr std::array<std::uint32_t, 8> kWheelPrimes = {
    3U, 5U, 7U, 11U, 13U, 17U, 19U, 23U};
constexpr std::uint32_t kWheelOddModulus =
    3U * 5U * 7U * 11U * 13U * 17U * 19U * 23U;
constexpr std::uint32_t kWheelCarryBits = 64U;
constexpr std::uint32_t kWheelLogicalBits =
    kWheelOddModulus + kWheelCarryBits;
constexpr std::uint32_t kWheelWords =
    (kWheelLogicalBits + 63U) / 64U;
constexpr std::uint64_t kWheelBytes =
    static_cast<std::uint64_t>(kWheelWords) * sizeof(std::uint64_t);
constexpr std::uint32_t kExpectedWheelSurvivors = 36'495'360U;
constexpr std::uint64_t kSourceQlow =
    31'249'999'599'000'003ULL;
constexpr std::uint64_t kSourceOddCount = 200'500'000ULL;
constexpr std::uint64_t kMaximumQualifiedWordCount =
    (kSourceOddCount + 63U) / 64U;
constexpr unsigned kBoundedRounds = 9U;
constexpr unsigned kSourceRounds = 101U;
constexpr unsigned kIntegratedEquivalentSegments = 100U;
constexpr std::string_view kCurrentGoldbachSourceSha256 =
    "2e4eedcf9d301c454c3e0174cccbe0f7"
    "a7a11350475ec8d681515d2a7ded333c";

static_assert(kWheelOddModulus == 111'546'435U);
static_assert(kWheelWords == 1'742'915U);
static_assert(kWheelBytes == 13'943'320ULL);
static_assert(kMaximumQualifiedWordCount == 3'132'813ULL);
static_assert(kMaximumQualifiedWordCount < kWheelOddModulus);
static_assert(
    64ULL * (kMaximumQualifiedWordCount - 1ULL) <
    2ULL * kWheelOddModulus);
static_assert(
    (kWheelOddModulus - 1ULL) +
        64ULL * (kMaximumQualifiedWordCount - 1ULL) <
    3ULL * kWheelOddModulus);
static_assert(
    (kWheelOddModulus - 1ULL) +
        64ULL * (kMaximumQualifiedWordCount - 1ULL) <=
    std::numeric_limits<std::uint32_t>::max());

// The exact production prime roster after the wheel.  Both CUDA paths expand
// this same list, making "unchanged 29..2039 clears" a source-level fact.
#define SPARKINTERVAL_GOLDBACH_WORD_OWNER_PRIMES_29_TO_2039(X) \
  X(29) X(31) X(37) X(41) X(43) X(47) X(53) X(59) \
  X(61) X(67) X(71) X(73) X(79) X(83) X(89) X(97) \
  X(101) X(103) X(107) X(109) X(113) X(127) X(131) X(137) \
  X(139) X(149) X(151) X(157) X(163) X(167) X(173) X(179) \
  X(181) X(191) X(193) X(197) X(199) X(211) X(223) X(227) \
  X(229) X(233) X(239) X(241) X(251) X(257) X(263) X(269) \
  X(271) X(277) X(281) X(283) X(293) X(307) X(311) X(313) \
  X(317) X(331) X(337) X(347) X(349) X(353) X(359) X(367) \
  X(373) X(379) X(383) X(389) X(397) X(401) X(409) X(419) \
  X(421) X(431) X(433) X(439) X(443) X(449) X(457) X(461) \
  X(463) X(467) X(479) X(487) X(491) X(499) X(503) X(509) \
  X(521) X(523) X(541) X(547) X(557) X(563) X(569) X(571) \
  X(577) X(587) X(593) X(599) X(601) X(607) X(613) X(617) \
  X(619) X(631) X(641) X(643) X(647) X(653) X(659) X(661) \
  X(673) X(677) X(683) X(691) X(701) X(709) X(719) X(727) \
  X(733) X(739) X(743) X(751) X(757) X(761) X(769) X(773) \
  X(787) X(797) X(809) X(811) X(821) X(823) X(827) X(829) \
  X(839) X(853) X(857) X(859) X(863) X(877) X(881) X(883) \
  X(887) X(907) X(911) X(919) X(929) X(937) X(941) X(947) \
  X(953) X(967) X(971) X(977) X(983) X(991) X(997) X(1009) \
  X(1013) X(1019) X(1021) X(1031) X(1033) X(1039) X(1049) X(1051) \
  X(1061) X(1063) X(1069) X(1087) X(1091) X(1093) X(1097) X(1103) \
  X(1109) X(1117) X(1123) X(1129) X(1151) X(1153) X(1163) X(1171) \
  X(1181) X(1187) X(1193) X(1201) X(1213) X(1217) X(1223) X(1229) \
  X(1231) X(1237) X(1249) X(1259) X(1277) X(1279) X(1283) X(1289) \
  X(1291) X(1297) X(1301) X(1303) X(1307) X(1319) X(1321) X(1327) \
  X(1361) X(1367) X(1373) X(1381) X(1399) X(1409) X(1423) X(1427) \
  X(1429) X(1433) X(1439) X(1447) X(1451) X(1453) X(1459) X(1471) \
  X(1481) X(1483) X(1487) X(1489) X(1493) X(1499) X(1511) X(1523) \
  X(1531) X(1543) X(1549) X(1553) X(1559) X(1567) X(1571) X(1579) \
  X(1583) X(1597) X(1601) X(1607) X(1609) X(1613) X(1619) X(1621) \
  X(1627) X(1637) X(1657) X(1663) X(1667) X(1669) X(1693) X(1697) \
  X(1699) X(1709) X(1721) X(1723) X(1733) X(1741) X(1747) X(1753) \
  X(1759) X(1777) X(1783) X(1787) X(1789) X(1801) X(1811) X(1823) \
  X(1831) X(1847) X(1861) X(1867) X(1871) X(1873) X(1877) X(1879) \
  X(1889) X(1901) X(1907) X(1913) X(1931) X(1933) X(1949) X(1951) \
  X(1973) X(1979) X(1987) X(1993) X(1997) X(1999) X(2003) X(2011) \
  X(2017) X(2027) X(2029) X(2039)

void cuda_check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(
        std::string(operation) + ": " + cudaGetErrorString(status));
  }
}

void require_device(cudaDeviceProp* properties) {
  int count = 0;
  cuda_check(cudaGetDeviceCount(&count), "cudaGetDeviceCount");
  if (count < 1) throw std::runtime_error("no CUDA device");
  cuda_check(
      cudaGetDeviceProperties(properties, 0),
      "cudaGetDeviceProperties");
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties->major != 9 || properties->minor != 0 ||
      std::string_view(properties->name).find("H100") ==
          std::string_view::npos) {
    throw std::runtime_error(
        "strict word-owner wheel qualification requires NVIDIA H100 sm_90");
  }
#endif
}

template <std::uint32_t Prime>
__device__ __forceinline__ void clear_small_prime_from_word(
    std::uint64_t word_low, std::uint64_t& word) {
  constexpr std::uint32_t inverse_two = (Prime + 1U) / 2U;
  const std::uint32_t residue =
      static_cast<std::uint32_t>(word_low % Prime);
  const std::uint32_t first = static_cast<std::uint32_t>(
      (static_cast<std::uint64_t>((Prime - residue) % Prime) *
       inverse_two) %
      Prime);
  constexpr std::uint64_t square =
      static_cast<std::uint64_t>(Prime) * Prime;
  for (std::uint32_t bit = first; bit < 64U; bit += Prime) {
    const std::uint64_t candidate =
        word_low + 2U * static_cast<std::uint64_t>(bit);
    if (candidate >= square) word &= ~(1ULL << bit);
  }
}

#define SPARKINTERVAL_CLEAR_WORD_OWNER_PRIME(Prime) \
  clear_small_prime_from_word<Prime>(word_low, word);

__global__ void current_literal_word_owner_kernel(
    std::uint64_t q_low, std::uint64_t word_count,
    std::uint64_t* __restrict__ words) {
  const std::uint64_t word_index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x +
      threadIdx.x;
  if (word_index >= word_count) return;
  const std::uint64_t word_low = q_low + 128U * word_index;
  std::uint64_t word = ~0ULL;
  clear_small_prime_from_word<3>(word_low, word);
  clear_small_prime_from_word<5>(word_low, word);
  clear_small_prime_from_word<7>(word_low, word);
  clear_small_prime_from_word<11>(word_low, word);
  clear_small_prime_from_word<13>(word_low, word);
  clear_small_prime_from_word<17>(word_low, word);
  clear_small_prime_from_word<19>(word_low, word);
  clear_small_prime_from_word<23>(word_low, word);
  SPARKINTERVAL_GOLDBACH_WORD_OWNER_PRIMES_29_TO_2039(
      SPARKINTERVAL_CLEAR_WORD_OWNER_PRIME)
  words[word_index] = word;
}

__device__ std::uint64_t g_word_owner_wheel23[kWheelWords];

__global__ void initialize_word_owner_wheel23_kernel() {
  const std::uint32_t word_index =
      blockIdx.x * blockDim.x + threadIdx.x;
  if (word_index >= kWheelWords) return;
  std::uint64_t word = 0U;
  for (std::uint32_t bit = 0U; bit < 64U; ++bit) {
    const std::uint32_t logical = word_index * 64U + bit;
    if (logical >= kWheelLogicalBits) break;
    const std::uint32_t phase = logical % kWheelOddModulus;
    const std::uint32_t odd = 2U * phase + 1U;
    const bool survives =
        odd % 3U != 0U && odd % 5U != 0U &&
        odd % 7U != 0U && odd % 11U != 0U &&
        odd % 13U != 0U && odd % 17U != 0U &&
        odd % 19U != 0U && odd % 23U != 0U;
    if (survives) word |= 1ULL << bit;
  }
  g_word_owner_wheel23[word_index] = word;
}

template <std::uint32_t Prime>
__device__ __forceinline__ void restore_wheel_prime(
    std::uint64_t word_low, std::uint64_t& word) {
  if (word_low <= Prime && Prime - word_low < 128U) {
    word |= 1ULL << ((Prime - word_low) / 2U);
  }
}

__device__ __forceinline__ std::uint64_t load_wheel23_word(
    std::uint32_t q_half_mod, std::uint64_t word_index) {
  // The launch guard gives word_index < 3,132,813 < M.  Therefore
  // q_half_mod + 64 * word_index < 3M < 2^32.  These two conditional
  // subtractions are the exact residue and use no per-thread division.
  std::uint32_t phase =
      q_half_mod + 64U * static_cast<std::uint32_t>(word_index);
  if (phase >= kWheelOddModulus) phase -= kWheelOddModulus;
  if (phase >= kWheelOddModulus) phase -= kWheelOddModulus;
  const std::uint32_t base = phase >> 6U;
  const std::uint32_t shift = phase & 63U;
  std::uint64_t word = g_word_owner_wheel23[base] >> shift;
  if (shift != 0U) {
    word |=
        g_word_owner_wheel23[base + 1U] << (64U - shift);
  }
  return word;
}

__global__ void candidate_wheel23_word_owner_kernel(
    std::uint64_t q_low, std::uint32_t q_half_mod,
    std::uint64_t word_count,
    std::uint64_t* __restrict__ words) {
  const std::uint64_t word_index =
      static_cast<std::uint64_t>(blockIdx.x) * blockDim.x +
      threadIdx.x;
  if (word_index >= word_count) return;
  const std::uint64_t word_low = q_low + 128U * word_index;
  std::uint64_t word = load_wheel23_word(q_half_mod, word_index);
  restore_wheel_prime<3>(word_low, word);
  restore_wheel_prime<5>(word_low, word);
  restore_wheel_prime<7>(word_low, word);
  restore_wheel_prime<11>(word_low, word);
  restore_wheel_prime<13>(word_low, word);
  restore_wheel_prime<17>(word_low, word);
  restore_wheel_prime<19>(word_low, word);
  restore_wheel_prime<23>(word_low, word);
  SPARKINTERVAL_GOLDBACH_WORD_OWNER_PRIMES_29_TO_2039(
      SPARKINTERVAL_CLEAR_WORD_OWNER_PRIME)
  words[word_index] = word;
}

#undef SPARKINTERVAL_CLEAR_WORD_OWNER_PRIME

std::vector<std::uint32_t> odd_primes_through_2039() {
  std::array<bool, kWordOwnerCutoff + 1U> composite{};
  for (std::uint32_t p = 2U; p <= kWordOwnerCutoff / p; ++p) {
    if (composite[p]) continue;
    for (std::uint32_t n = p * p; n <= kWordOwnerCutoff; n += p) {
      composite[n] = true;
    }
  }
  std::vector<std::uint32_t> result;
  for (std::uint32_t p = 3U; p <= kWordOwnerCutoff; p += 2U) {
    if (!composite[p]) result.push_back(p);
  }
  if (result.size() != 308U || result.front() != 3U ||
      result.back() != kWordOwnerCutoff) {
    throw std::runtime_error("independent CPU prime roster differs");
  }
  return result;
}

bool first_odd_multiple(
    std::uint64_t low, std::uint64_t high, std::uint64_t prime,
    std::uint64_t* first) {
  std::uint64_t quotient = low / prime;
  if (low % prime != 0U) ++quotient;
  if (quotient > high / prime) return false;
  std::uint64_t value = quotient * prime;
  if ((value & 1U) == 0U) {
    if (prime > high - value) return false;
    value += prime;
  }
  const std::uint64_t square = prime * prime;
  if (value < square) value = square;
  if (value > high) return false;
  *first = value;
  return true;
}

std::vector<std::uint64_t> cpu_word_owner(
    std::uint64_t q_low, std::uint64_t odd_count,
    const std::vector<std::uint32_t>& primes) {
  if ((q_low & 1U) == 0U || odd_count == 0U) {
    throw std::runtime_error("CPU word-owner geometry is not odd");
  }
  const std::uint64_t word_count = (odd_count + 63U) / 64U;
  const std::uint64_t full_count = word_count * 64U;
  if (full_count - 1U >
      (std::numeric_limits<std::uint64_t>::max() - q_low) / 2U) {
    throw std::runtime_error("CPU word-owner full-word span overflows");
  }
  const std::uint64_t full_high =
      q_low + 2U * (full_count - 1U);
  std::vector<std::uint64_t> words(
      static_cast<std::size_t>(word_count), ~0ULL);
  for (const std::uint64_t prime : primes) {
    std::uint64_t first = 0U;
    if (!first_odd_multiple(q_low, full_high, prime, &first)) continue;
    const std::uint64_t step = 2U * prime;
    for (std::uint64_t value = first;;) {
      const std::uint64_t bit = (value - q_low) / 2U;
      words[static_cast<std::size_t>(bit / 64U)] &=
          ~(1ULL << static_cast<unsigned>(bit & 63U));
      if (step > full_high - value) break;
      value += step;
    }
  }
  return words;
}

std::vector<std::uint64_t> independent_wheel_table() {
  std::vector<std::uint64_t> words(kWheelWords, ~0ULL);
  const unsigned final_bits = kWheelLogicalBits & 63U;
  if (final_bits != 0U) {
    words.back() = (1ULL << final_bits) - 1ULL;
  }
  for (const std::uint32_t prime : kWheelPrimes) {
    for (std::uint64_t logical = (prime - 1U) / 2U;
         logical < kWheelLogicalBits; logical += prime) {
      words[static_cast<std::size_t>(logical / 64U)] &=
          ~(1ULL << static_cast<unsigned>(logical & 63U));
    }
  }
  return words;
}

std::string canonical_sha256(
    const std::vector<std::uint64_t>& words) {
  sparkinterval::detail::Sha256 hasher;
  for (const std::uint64_t word : words) {
    unsigned char bytes[8];
    for (unsigned index = 0U; index < 8U; ++index) {
      bytes[index] =
          static_cast<unsigned char>(word >> (8U * index));
    }
    hasher.update(bytes, sizeof(bytes));
  }
  return sparkinterval::lowercase_hex(hasher.finish());
}

void update_u64(
    sparkinterval::detail::Sha256* hasher, std::uint64_t value) {
  unsigned char bytes[8];
  for (unsigned index = 0U; index < 8U; ++index) {
    bytes[index] =
        static_cast<unsigned char>(value >> (8U * index));
  }
  hasher->update(bytes, sizeof(bytes));
}

struct TableAudit {
  std::string sha256;
  std::uint64_t mismatched_words = 0U;
  std::uint64_t carry_mismatches = 0U;
  std::uint64_t padding_nonzero_bits = 0U;
  std::uint64_t surviving_residues = 0U;
  double initialization_ms = 0.0;

  bool accepted() const {
    return mismatched_words == 0U && carry_mismatches == 0U &&
           padding_nonzero_bits == 0U &&
           surviving_residues == kExpectedWheelSurvivors;
  }
};

double elapsed(cudaEvent_t begin, cudaEvent_t end) {
  float milliseconds = 0.0F;
  cuda_check(
      cudaEventElapsedTime(&milliseconds, begin, end),
      "cudaEventElapsedTime");
  return milliseconds;
}

TableAudit initialize_and_audit_table() {
  cudaEvent_t begin = nullptr;
  cudaEvent_t end = nullptr;
  cuda_check(cudaEventCreate(&begin), "cudaEventCreate table begin");
  cuda_check(cudaEventCreate(&end), "cudaEventCreate table end");
  cuda_check(cudaEventRecord(begin), "cudaEventRecord table begin");
  initialize_word_owner_wheel23_kernel<<<
      (kWheelWords + kThreads - 1U) / kThreads, kThreads>>>();
  cuda_check(cudaGetLastError(), "launch wheel table initializer");
  cuda_check(cudaEventRecord(end), "cudaEventRecord table end");
  cuda_check(cudaEventSynchronize(end), "synchronize wheel table");
  TableAudit result;
  result.initialization_ms = elapsed(begin, end);
  cuda_check(cudaEventDestroy(end), "cudaEventDestroy table end");
  cuda_check(cudaEventDestroy(begin), "cudaEventDestroy table begin");

  std::vector<std::uint64_t> actual(kWheelWords);
  cuda_check(
      cudaMemcpyFromSymbol(
          actual.data(), g_word_owner_wheel23,
          actual.size() * sizeof(actual.front())),
      "copy wheel table");
  const std::vector<std::uint64_t> expected =
      independent_wheel_table();
  for (std::size_t index = 0U; index < actual.size(); ++index) {
    result.mismatched_words += actual[index] != expected[index];
  }
  for (std::uint32_t bit = 0U; bit < kWheelCarryBits; ++bit) {
    const std::uint64_t head =
        (actual[bit / 64U] >> (bit & 63U)) & 1U;
    const std::uint64_t carry_index =
        static_cast<std::uint64_t>(kWheelOddModulus) + bit;
    const std::uint64_t carry =
        (actual[carry_index / 64U] >> (carry_index & 63U)) & 1U;
    result.carry_mismatches += head != carry;
  }
  for (std::uint64_t bit = kWheelLogicalBits;
       bit < static_cast<std::uint64_t>(kWheelWords) * 64U; ++bit) {
    result.padding_nonzero_bits +=
        (actual[bit / 64U] >> (bit & 63U)) & 1U;
  }
  for (std::uint64_t bit = 0U; bit < kWheelOddModulus; ++bit) {
    result.surviving_residues +=
        (actual[bit / 64U] >> (bit & 63U)) & 1U;
  }
  result.sha256 = canonical_sha256(actual);
  return result;
}

struct CaseSpec {
  std::string name;
  std::uint64_t q_low;
  std::uint64_t odd_count;
};

struct CaseResult {
  CaseSpec spec;
  std::uint64_t word_count = 0U;
  std::uint64_t padding_bits = 0U;
  std::uint64_t set_bits = 0U;
  std::string output_sha256;
};

void compare_words(
    const std::vector<std::uint64_t>& expected,
    const std::vector<std::uint64_t>& actual,
    std::string_view label) {
  if (expected.size() != actual.size()) {
    throw std::runtime_error(std::string(label) + " size differs");
  }
  const auto mismatch = std::mismatch(
      expected.begin(), expected.end(), actual.begin());
  if (mismatch.first != expected.end()) {
    throw std::runtime_error(
        std::string(label) + " differs at word " +
        std::to_string(mismatch.first - expected.begin()));
  }
}

void launch_current(
    std::uint64_t q_low, std::uint64_t word_count,
    std::uint64_t* words) {
  current_literal_word_owner_kernel<<<
      static_cast<unsigned>((word_count + kThreads - 1U) / kThreads),
      kThreads>>>(q_low, word_count, words);
  cuda_check(cudaGetLastError(), "launch current word owner");
}

void launch_candidate(
    std::uint64_t q_low, std::uint64_t word_count,
    std::uint64_t* words) {
  if (word_count > kMaximumQualifiedWordCount) {
    throw std::runtime_error(
        "phase-hoisted wheel23 word count exceeds qualified bound");
  }
  const std::uint32_t q_half_mod = static_cast<std::uint32_t>(
      (q_low >> 1U) % kWheelOddModulus);
  candidate_wheel23_word_owner_kernel<<<
      static_cast<unsigned>((word_count + kThreads - 1U) / kThreads),
      kThreads>>>(q_low, q_half_mod, word_count, words);
  cuda_check(cudaGetLastError(), "launch candidate word owner");
}

CaseResult run_case(
    const CaseSpec& spec, const std::vector<std::uint32_t>& primes,
    std::uint64_t* current_words, std::uint64_t* candidate_words) {
  const std::vector<std::uint64_t> expected =
      cpu_word_owner(spec.q_low, spec.odd_count, primes);
  const std::uint64_t word_count = expected.size();
  const std::size_t bytes =
      expected.size() * sizeof(expected.front());
  launch_current(spec.q_low, word_count, current_words);
  launch_candidate(spec.q_low, word_count, candidate_words);
  cuda_check(cudaDeviceSynchronize(), "synchronize word-owner case");
  std::vector<std::uint64_t> current(expected.size());
  std::vector<std::uint64_t> candidate(expected.size());
  cuda_check(
      cudaMemcpy(
          current.data(), current_words, bytes,
          cudaMemcpyDeviceToHost),
      "copy current words");
  cuda_check(
      cudaMemcpy(
          candidate.data(), candidate_words, bytes,
          cudaMemcpyDeviceToHost),
      "copy candidate words");
  compare_words(expected, current, "current CUDA/CPU");
  compare_words(expected, candidate, "candidate CUDA/CPU");
  compare_words(current, candidate, "current/candidate CUDA");
  return {
      spec,
      word_count,
      word_count * 64U - spec.odd_count,
      std::accumulate(
          expected.begin(), expected.end(), std::uint64_t{0},
          [](std::uint64_t total, std::uint64_t word) {
            return total + std::popcount(word);
          }),
      canonical_sha256(expected),
  };
}

struct PrimeSquareAudit {
  std::uint64_t prime_count = 0U;
  std::string sha256;
};

PrimeSquareAudit run_prime_square_audit(
    const std::vector<std::uint32_t>& primes,
    std::uint64_t* current_words, std::uint64_t* candidate_words) {
  sparkinterval::detail::Sha256 hasher;
  for (const std::uint64_t prime : primes) {
    const std::uint64_t square = prime * prime;
    const CaseSpec spec{
        "p2-" + std::to_string(prime),
        square > 254U ? square - 254U : 3U,
        256U,
    };
    const CaseResult result =
        run_case(spec, primes, current_words, candidate_words);
    update_u64(&hasher, prime);
    update_u64(&hasher, spec.q_low);
    update_u64(&hasher, result.set_bits);
    const std::vector<std::uint64_t> expected =
        cpu_word_owner(spec.q_low, spec.odd_count, primes);
    for (const std::uint64_t word : expected) update_u64(&hasher, word);
  }
  return {
      primes.size(),
      sparkinterval::lowercase_hex(hasher.finish()),
  };
}

template <typename Launch>
double timed_launch(Launch launch) {
  cudaEvent_t begin = nullptr;
  cudaEvent_t end = nullptr;
  cuda_check(cudaEventCreate(&begin), "cudaEventCreate begin");
  cuda_check(cudaEventCreate(&end), "cudaEventCreate end");
  cuda_check(cudaEventRecord(begin), "cudaEventRecord begin");
  launch();
  cuda_check(cudaEventRecord(end), "cudaEventRecord end");
  cuda_check(cudaEventSynchronize(end), "cudaEventSynchronize end");
  const double result = elapsed(begin, end);
  cuda_check(cudaEventDestroy(end), "cudaEventDestroy end");
  cuda_check(cudaEventDestroy(begin), "cudaEventDestroy begin");
  return result;
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  return values[values.size() / 2U];
}

struct Benchmark {
  unsigned rounds = 0U;
  std::vector<double> current_ms;
  std::vector<double> candidate_ms;
  double current_median_ms = 0.0;
  double candidate_median_ms = 0.0;
  double current_over_candidate_rate_ratio = 0.0;
  double integrated_current_20b_ms = 0.0;
  double integrated_candidate_20b_ms = 0.0;
  bool integrated_equivalent_measured = false;
};

Benchmark benchmark(
    const CaseSpec& source, unsigned rounds, double table_ms,
    std::uint64_t* current_words, std::uint64_t* candidate_words) {
  Benchmark result;
  result.rounds = rounds;
  const std::uint64_t word_count =
      (source.odd_count + 63U) / 64U;
  launch_current(source.q_low, word_count, current_words);
  launch_candidate(source.q_low, word_count, candidate_words);
  cuda_check(cudaDeviceSynchronize(), "synchronize benchmark warmup");
  for (unsigned round = 0U; round < rounds; ++round) {
    if ((round & 1U) == 0U) {
      result.current_ms.push_back(timed_launch([&]() {
        launch_current(source.q_low, word_count, current_words);
      }));
      result.candidate_ms.push_back(timed_launch([&]() {
        launch_candidate(source.q_low, word_count, candidate_words);
      }));
    } else {
      result.candidate_ms.push_back(timed_launch([&]() {
        launch_candidate(source.q_low, word_count, candidate_words);
      }));
      result.current_ms.push_back(timed_launch([&]() {
        launch_current(source.q_low, word_count, current_words);
      }));
    }
  }
  result.current_median_ms = median(result.current_ms);
  result.candidate_median_ms = median(result.candidate_ms);
  result.current_over_candidate_rate_ratio =
      result.current_median_ms / result.candidate_median_ms;
  if (rounds >= kIntegratedEquivalentSegments) {
    result.integrated_current_20b_ms = std::accumulate(
        result.current_ms.begin(),
        result.current_ms.begin() + kIntegratedEquivalentSegments, 0.0);
    result.integrated_candidate_20b_ms =
        table_ms + std::accumulate(
            result.candidate_ms.begin(),
            result.candidate_ms.begin() +
                kIntegratedEquivalentSegments,
            0.0);
    result.integrated_equivalent_measured = true;
  }
  return result;
}

bool resource_ok(
    const cudaFuncAttributes& attributes,
    unsigned maximum_registers) {
  return attributes.localSizeBytes == 0U &&
         attributes.maxThreadsPerBlock >=
             static_cast<int>(kThreads) &&
         attributes.numRegs > 0 &&
         attributes.numRegs <= static_cast<int>(maximum_registers) &&
         attributes.sharedSizeBytes == 0U;
}

void print_resources(const cudaFuncAttributes& value) {
  std::cout
      << "{\"local_bytes_per_thread\":" << value.localSizeBytes
      << ",\"max_threads_per_block\":"
      << value.maxThreadsPerBlock
      << ",\"registers_per_thread\":" << value.numRegs
      << ",\"static_constant_bytes\":" << value.constSizeBytes
      << ",\"static_shared_bytes\":" << value.sharedSizeBytes << '}';
}

void print_array(const std::vector<double>& values) {
  std::cout << '[';
  for (std::size_t index = 0U; index < values.size(); ++index) {
    if (index != 0U) std::cout << ',';
    std::cout << std::fixed << std::setprecision(6) << values[index];
  }
  std::cout << ']';
}

void print_case(const CaseResult& result) {
  const std::uint64_t full_high =
      result.spec.q_low + 2U * (result.word_count * 64U - 1U);
  std::cout
      << "{\"name\":\"" << result.spec.name << "\""
      << ",\"odd_count\":" << result.spec.odd_count
      << ",\"output_sha256\":\"" << result.output_sha256 << "\""
      << ",\"padding_bits\":" << result.padding_bits
      << ",\"q_low\":\"" << result.spec.q_low << "\""
      << ",\"full_word_q_high\":\"" << full_high << "\""
      << ",\"set_bits\":" << result.set_bits
      << ",\"word_count\":" << result.word_count << '}';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::string mode = "bounded";
    if (argc == 2 && std::string_view(argv[1]) == "--source-segment") {
      mode = "source-segment";
    } else if (argc != 1) {
      throw std::runtime_error("usage: qualifier [--source-segment]");
    }

    cudaDeviceProp properties{};
    require_device(&properties);
    const TableAudit table = initialize_and_audit_table();
    if (!table.accepted()) {
      throw std::runtime_error("through-23 wheel table audit failed");
    }
    const std::vector<std::uint32_t> primes =
        odd_primes_through_2039();

    const std::vector<CaseSpec> specs = {
        {"low-prime-restoration", 3U, 256U},
        {"wheel-period-carry",
         2ULL * (kWheelOddModulus - 32ULL) + 1ULL, 256U},
        {"source-height", 31'249'998'799'000'003ULL, 262'147U},
        {"uint64-max-edge",
         std::numeric_limits<std::uint64_t>::max() -
             2ULL * ((1ULL << 18U) - 1ULL),
         1ULL << 18U},
    };
    const CaseSpec source{
        "historical-terminal-segment", kSourceQlow, kSourceOddCount};
    std::uint64_t maximum_words =
        (source.odd_count + 63U) / 64U;
    std::uint64_t* current_words = nullptr;
    std::uint64_t* candidate_words = nullptr;
    cuda_check(
        cudaMalloc(
            &current_words,
            maximum_words * sizeof(std::uint64_t)),
        "cudaMalloc current words");
    cuda_check(
        cudaMalloc(
            &candidate_words,
            maximum_words * sizeof(std::uint64_t)),
        "cudaMalloc candidate words");

    bool oversized_launch_rejected = false;
    try {
      launch_candidate(
          source.q_low, kMaximumQualifiedWordCount + 1ULL,
          candidate_words);
    } catch (const std::runtime_error& error) {
      oversized_launch_rejected =
          std::string_view(error.what()) ==
          "phase-hoisted wheel23 word count exceeds qualified bound";
    }
    if (!oversized_launch_rejected) {
      throw std::runtime_error(
          "phase-hoisted wheel23 oversized launch was not rejected");
    }

    std::vector<CaseResult> cases;
    for (const CaseSpec& spec : specs) {
      cases.push_back(
          run_case(spec, primes, current_words, candidate_words));
    }
    const PrimeSquareAudit p2 = run_prime_square_audit(
        primes, current_words, candidate_words);
    std::optional<CaseResult> terminal;
    if (mode == "source-segment") {
      terminal =
          run_case(source, primes, current_words, candidate_words);
    }
    const unsigned rounds =
        mode == "source-segment" ? kSourceRounds : kBoundedRounds;
    const CaseSpec benchmark_spec =
        mode == "source-segment"
            ? source
            : CaseSpec{
                  "bounded-source-equivalent",
                  31'249'998'799'000'003ULL, 1ULL << 20U};
    const Benchmark timing = benchmark(
        benchmark_spec, rounds, table.initialization_ms,
        current_words, candidate_words);

    cudaFuncAttributes table_attributes{};
    cudaFuncAttributes current_attributes{};
    cudaFuncAttributes candidate_attributes{};
    cuda_check(
        cudaFuncGetAttributes(
            &table_attributes,
            initialize_word_owner_wheel23_kernel),
        "cudaFuncGetAttributes table");
    cuda_check(
        cudaFuncGetAttributes(
            &current_attributes,
            current_literal_word_owner_kernel),
        "cudaFuncGetAttributes current");
    cuda_check(
        cudaFuncGetAttributes(
            &candidate_attributes,
            candidate_wheel23_word_owner_kernel),
        "cudaFuncGetAttributes candidate");
    const bool resources_accepted =
        resource_ok(table_attributes, 64U) &&
        resource_ok(current_attributes, 64U) &&
        resource_ok(candidate_attributes, 64U);
    if (!resources_accepted) {
      throw std::runtime_error("word-owner compiler resource gate failed");
    }
    cuda_check(cudaFree(candidate_words), "cudaFree candidate words");
    cuda_check(cudaFree(current_words), "cudaFree current words");

    std::cout
        << std::setprecision(17)
        << "{\"accepted\":true"
        << ",\"algorithm_equivalence_scope\":"
           "\"cpu-vs-current-vs-phase-hoisted-wheel23-all-output-words\""
        << ",\"benchmark\":{\"candidate_median_ms\":"
        << timing.candidate_median_ms
        << ",\"candidate_ms\":";
    print_array(timing.candidate_ms);
    std::cout
        << ",\"current_median_ms\":" << timing.current_median_ms
        << ",\"current_ms\":";
    print_array(timing.current_ms);
    std::cout
        << ",\"current_over_candidate_rate_ratio\":"
        << timing.current_over_candidate_rate_ratio
        << ",\"integrated_equivalent_even_count\":\"20000000000\""
        << ",\"integrated_equivalent_odd_word_inputs\":\""
        << kSourceOddCount * kIntegratedEquivalentSegments << "\""
        << ",\"integrated_equivalent_segment_count\":"
        << kIntegratedEquivalentSegments
        << ",\"integrated_equivalent_measured\":"
        << (timing.integrated_equivalent_measured ? "true" : "false")
        << ",\"integrated_current_initializer_ms\":"
        << timing.integrated_current_20b_ms
        << ",\"integrated_candidate_initializer_plus_table_ms\":"
        << timing.integrated_candidate_20b_ms
        << ",\"rounds\":" << timing.rounds << "}"
        << ",\"bounded_cases\":[";
    for (std::size_t index = 0U; index < cases.size(); ++index) {
      if (index != 0U) std::cout << ',';
      print_case(cases[index]);
    }
    std::cout
        << "]"
        << ",\"build_profile\":{\"cmake_build_config\":\""
        << kBuildProfile << "\",\"ndebug_defined\":"
        << (kNdebugDefined ? "true" : "false") << "}"
        << ",\"candidate_resources\":";
    print_resources(candidate_attributes);
    std::cout
        << ",\"classification\":"
           "\"qualification-only-unpromoted-candidate\""
        << ",\"compute_capability\":\"" << properties.major << '.'
        << properties.minor << "\""
        << ",\"current_resources\":";
    print_resources(current_attributes);
    std::cout
        << ",\"kind\":"
           "\"sparkinterval.goldbach-word-owner-wheel23-qualification.v1\""
        << ",\"mode\":\"" << mode << "\""
        << ",\"phase_reduction\":{"
        << "\"conditional_subtractions\":2"
        << ",\"launch_guard_passed\":true"
        << ",\"maximum_phase_numerator\":"
        << (kWheelOddModulus - 1ULL) +
               64ULL * (kMaximumQualifiedWordCount - 1ULL)
        << ",\"maximum_qualified_word_count\":"
        << kMaximumQualifiedWordCount
        << ",\"maximum_scaled_word_index\":"
        << 64ULL * (kMaximumQualifiedWordCount - 1ULL)
        << ",\"maximum_word_index\":"
        << kMaximumQualifiedWordCount - 1ULL
        << ",\"oversized_launch_rejected\":"
        << (oversized_launch_rejected ? "true" : "false")
        << ",\"q_half_mod_hoisted\":true"
        << ",\"three_moduli\":"
        << 3ULL * kWheelOddModulus
        << ",\"uint32_max\":"
        << std::numeric_limits<std::uint32_t>::max()
        << ",\"word_index_modulus_elided\":true}"
        << ",\"prime_square_audit\":{\"prime_count\":"
        << p2.prime_count << ",\"sha256\":\"" << p2.sha256 << "\"}"
        << ",\"resource_gate_passed\":true"
        << ",\"source_pins\":{\"current_goldbach_source_sha256\":\""
        << kCurrentGoldbachSourceSha256 << "\"}"
        << ",\"strict_h100_target\":"
        << (kStrictH100Target ? "true" : "false")
        << ",\"table_initializer_resources\":";
    print_resources(table_attributes);
    std::cout
        << ",\"terminal_case\":";
    if (terminal.has_value()) {
      print_case(*terminal);
    } else {
      std::cout << "null";
    }
    std::cout
        << ",\"wheel_table\":{\"carry_bits\":"
        << kWheelCarryBits
        << ",\"carry_mismatches\":" << table.carry_mismatches
        << ",\"device_bytes\":" << kWheelBytes
        << ",\"initialization_ms\":" << table.initialization_ms
        << ",\"logical_bits\":" << kWheelLogicalBits
        << ",\"mismatched_words\":" << table.mismatched_words
        << ",\"odd_modulus\":" << kWheelOddModulus
        << ",\"padding_nonzero_bits\":"
        << table.padding_nonzero_bits
        << ",\"sha256\":\"" << table.sha256
        << "\",\"surviving_residues\":"
        << table.surviving_residues
        << ",\"word_count\":" << kWheelWords << "}"
        << ",\"all_word_equality\":true"
        << ",\"candidate_selected_in_production\":false"
        << ",\"cuda_to_lean_refinement_proved\":false"
        << ",\"h100_measured\":false"
        << ",\"lean_bridge_complete\":false"
        << ",\"performance_evidence_eligible\":false"
        << ",\"production_identity_changed\":false"
        << ",\"production_ready\":false"
        << ",\"release_build_profile_eligible\":"
        << ((kNdebugDefined && kBuildProfile == "Release")
                ? "true"
                : "false")
        << ",\"receipt_emitted\":false"
        << ",\"runtime_instrumentation_status\":"
           "\"not-inspected-by-runner\""
        << ",\"theorem_claimed\":false"
        << ",\"word_owner_cutoff\":" << kWordOwnerCutoff << "}\n";
  } catch (const std::exception& error) {
    std::cerr
        << "goldbach-word-owner-wheel23-qualification: "
        << error.what() << '\n';
    return 2;
  }
  return 0;
}

#undef SPARKINTERVAL_GOLDBACH_WORD_OWNER_PRIMES_29_TO_2039

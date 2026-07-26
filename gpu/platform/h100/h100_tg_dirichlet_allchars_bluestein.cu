// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-scalable all-character transform for Platt's large-q algorithm.
// Each cyclic factor is transformed with Bluestein's chirp convolution and a
// radix-2 interval FFT.  MPFR constructs rigorous binary64 enclosures of every
// transcendental twiddle; CUDA arithmetic then uses directed rounding.

#include "sparkinterval/tg_dirichlet_allchars.hpp"
#include "sparkinterval/tg_dirichlet_completed_factor_artifacts.hpp"
#include "sparkinterval/tg_dirichlet_completed_sign_reducer.cuh"
#include "sparkinterval/tg_dirichlet_resident_phase_accumulator.cuh"
#include "sparkinterval/sha256.hpp"

#include <cuda_runtime.h>
#include <mpfr.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <csignal>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <list>
#include <limits>
#include <memory>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <system_error>
#include <sys/wait.h>
#include <type_traits>
#include <unordered_map>
#include <unistd.h>
#include <utility>
#include <vector>

namespace da = sparkinterval::tg::dirichlet_allchars;
namespace dl = sparkinterval::tg::dirichlet_lattice;
namespace dr =
    sparkinterval::tg::dirichlet_completed_sign_reducer;
namespace dfa =
    sparkinterval::tg::dirichlet_completed_factor_artifacts;
namespace dpa =
    sparkinterval::tg::dirichlet_resident_phase_accumulator;
namespace sc =
    sparkinterval::tg::dirichlet_booker_smallq_certified;

namespace {

using dl::ComplexInterval;
using dl::RealInterval;

static_assert(
    std::endian::native == std::endian::little,
    "the raw interval/root/chirp wire formats require a little-endian host");
static_assert(
    sizeof(double) == 8U && std::numeric_limits<double>::is_iec559 &&
        std::numeric_limits<double>::radix == 2 &&
        std::numeric_limits<double>::digits == 53 &&
        std::numeric_limits<double>::max_exponent == 1024,
    "the raw interval/root/chirp wire formats require IEEE binary64");
static_assert(std::is_standard_layout_v<RealInterval>);
static_assert(std::is_trivially_copyable_v<RealInterval>);
static_assert(std::is_standard_layout_v<ComplexInterval>);
static_assert(std::is_trivially_copyable_v<ComplexInterval>);
static_assert(sizeof(RealInterval) == 16U);
static_assert(sizeof(ComplexInterval) == 32U);

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +               \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

struct MpfrValue {
  mpfr_t value;
  explicit MpfrValue(mpfr_prec_t precision = 320) { mpfr_init2(value, precision); }
  ~MpfrValue() { mpfr_clear(value); }
  MpfrValue(const MpfrValue&) = delete;
  MpfrValue& operator=(const MpfrValue&) = delete;
};

// A 256-bit recurrence is already much narrower than one binary64 ulp over a
// 256-entry block.  The direct root builder deliberately retains MpfrValue's
// 320-bit default as an independently configured diagnostic path.
constexpr mpfr_prec_t kChirpPrecision = 256;
constexpr std::uint32_t kChirpAnchorCadence = 256U;
constexpr double kMaximumChirpComponentWidth = 0x1p-48;
constexpr mpfr_prec_t kFftRootPrecision = 256;
constexpr std::uint32_t kFftRootAnchorCadence = 256U;
constexpr double kMaximumFftRootComponentWidth = 0x1p-48;
constexpr std::uint32_t kMaximumOrderImpulseQ = 399989U;
constexpr std::uint32_t kMaximumOrderImpulseLength = 399988U;
constexpr std::uint32_t kMaximumOrderImpulseConvolution = 1U << 20U;
constexpr std::uint32_t kMaximumOrderImpulseLogConvolution = 20U;
constexpr std::uint64_t kMaximumOrderImpulseButterflies =
    3ULL * (kMaximumOrderImpulseConvolution / 2ULL) *
    kMaximumOrderImpulseLogConvolution;
// This deliberately overestimates the peak live CUDA interval arrays:
// two transform buffers, two work buffers, two root arrays, the chirp, the
// transformed kernel, and one temporary kernel array.  The temporary and work
// arrays are not actually live together, but retaining both in the estimate
// makes the preflight independent of allocator-release behavior.
constexpr std::uint64_t kMaximumOrderImpulseRequiredDeviceBytes =
    (6ULL * kMaximumOrderImpulseConvolution +
     3ULL * kMaximumOrderImpulseLength) *
    sizeof(ComplexInterval);
constexpr std::uint64_t kMaximumOrderImpulseDeviceHeadroomBytes =
    256ULL * 1024ULL * 1024ULL;
constexpr double kMaximumOrderImpulseWidth = 0x1p-16;

struct MpfrRealInterval {
  MpfrValue lo;
  MpfrValue hi;

  explicit MpfrRealInterval(mpfr_prec_t precision = kChirpPrecision)
      : lo(precision), hi(precision) {}
};

struct MpfrComplexInterval {
  MpfrRealInterval re;
  MpfrRealInterval im;

  explicit MpfrComplexInterval(mpfr_prec_t precision = kChirpPrecision)
      : re(precision), im(precision) {}
};

// All recurrence temporaries have the same precision as the state.  Keeping
// them alive across the complete chirp avoids an MPFR allocation for every
// real product and for every anchor trigonometric evaluation.
struct MpfrChirpScratch {
  mpq_t rational;
  MpfrValue xLo;
  MpfrValue xHi;
  MpfrValue candidateLo;
  MpfrValue candidateHi;
  MpfrValue point;
  MpfrValue productLo;
  MpfrValue productHi;
  MpfrRealInterval ac;
  MpfrRealInterval bd;
  MpfrRealInterval ad;
  MpfrRealInterval bc;

  explicit MpfrChirpScratch(mpfr_prec_t precision = kChirpPrecision)
      : xLo(precision),
        xHi(precision),
        candidateLo(precision),
        candidateHi(precision),
        point(precision),
        productLo(precision),
        productHi(precision),
        ac(precision),
        bd(precision),
        ad(precision),
        bc(precision) {
    mpq_init(rational);
  }

  ~MpfrChirpScratch() { mpq_clear(rational); }
  MpfrChirpScratch(const MpfrChirpScratch&) = delete;
  MpfrChirpScratch& operator=(const MpfrChirpScratch&) = delete;
};

std::uint64_t parseUnsigned(const char* text, const char* label) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  errno = 0;
  char* end = nullptr;
  const unsigned long long value = std::strtoull(text, &end, 10);
  if (errno != 0 || end == nullptr || *end != '\0') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<std::uint64_t>(value);
}

sparkinterval::Sha256Digest parseLowercaseSha256(const char* text,
                                                 const char* label) {
  if (text == nullptr || std::strlen(text) != 64U) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  sparkinterval::Sha256Digest digest{};
  for (std::size_t index = 0U; index < digest.size(); ++index) {
    const auto nibble = [&](char character) -> unsigned char {
      if (character >= '0' && character <= '9') {
        return static_cast<unsigned char>(character - '0');
      }
      if (character >= 'a' && character <= 'f') {
        return static_cast<unsigned char>(character - 'a' + 10);
      }
      throw std::runtime_error(std::string("invalid ") + label);
    };
    digest[index] = static_cast<unsigned char>(
        (nibble(text[2U * index]) << 4U) |
        nibble(text[2U * index + 1U]));
  }
  return digest;
}

void hashUint32LE(sparkinterval::detail::Sha256* hasher,
                  std::uint32_t value) {
  const unsigned char bytes[4] = {
      static_cast<unsigned char>(value),
      static_cast<unsigned char>(value >> 8U),
      static_cast<unsigned char>(value >> 16U),
      static_cast<unsigned char>(value >> 24U),
  };
  hasher->update(bytes, sizeof(bytes));
}

std::vector<std::uint32_t> canonicalOrders(std::uint32_t q) {
  if (q < 3U || q > da::kMaximumModulus) {
    throw std::runtime_error("q is outside 3..400000");
  }
  std::vector<std::uint32_t> orders;
  std::uint32_t remaining = q;
  for (std::uint32_t p = 2U;
       static_cast<std::uint64_t>(p) * p <= remaining; ++p) {
    if (remaining % p != 0U) continue;
    std::uint32_t exponent = 0U;
    std::uint32_t modulus = 1U;
    while (remaining % p == 0U) {
      remaining /= p;
      modulus *= p;
      ++exponent;
    }
    if (p == 2U) {
      if (exponent == 2U) orders.push_back(2U);
      if (exponent > 2U) {
        orders.push_back(2U);
        orders.push_back(1U << (exponent - 2U));
      }
    } else {
      orders.push_back(modulus - modulus / p);
    }
  }
  if (remaining > 1U) orders.push_back(remaining - 1U);
  if (orders.size() > da::kMaxComponents) {
    throw std::runtime_error("canonical group exceeds component limit");
  }
  return orders;
}

std::uint64_t orderProduct(const std::vector<std::uint32_t>& orders) {
  std::uint64_t product = 1U;
  for (const auto order : orders) product *= order;
  return product;
}

std::uint32_t nextPowerOfTwo(std::uint64_t value) {
  std::uint64_t answer = 1U;
  while (answer < value) answer <<= 1U;
  if (answer > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error("Bluestein convolution length overflow");
  }
  return static_cast<std::uint32_t>(answer);
}

std::uint32_t integerLog2(std::uint32_t value) {
  std::uint32_t answer = 0U;
  while ((1U << answer) != value) ++answer;
  return answer;
}

constexpr std::uint32_t kSourceRootFirstConvolution = 4U;
constexpr std::uint32_t kSourceRootLastConvolution = 1U << 20U;
constexpr std::uint64_t kMultiQTotalCacheBytes = 512ULL * 1024ULL * 1024ULL;

constexpr std::uint32_t sourceRootCatalogEntries() {
  std::uint32_t entries = 0U;
  for (std::uint64_t convolution = kSourceRootFirstConvolution;
       convolution <= kSourceRootLastConvolution; convolution <<= 1U) {
    ++entries;
  }
  return entries;
}

constexpr std::uint64_t sourceRootPoolReservedBytes() {
  std::uint64_t intervals = 0U;
  for (std::uint64_t convolution = kSourceRootFirstConvolution;
       convolution <= kSourceRootLastConvolution; convolution <<= 1U) {
    intervals += 2U * (convolution - 1U);
  }
  return intervals * sizeof(ComplexInterval);
}

constexpr std::uint32_t kSourceRootCatalogEntries =
    sourceRootCatalogEntries();
constexpr std::uint64_t kSourceRootPoolReservedBytes =
    sourceRootPoolReservedBytes();
constexpr std::uint64_t kMultiQOrderCacheBytes =
    kMultiQTotalCacheBytes - kSourceRootPoolReservedBytes;
static_assert(kSourceRootPoolReservedBytes == 134216256ULL);
static_assert(kMultiQOrderCacheBytes == 402654656ULL);
static_assert(kSourceRootCatalogEntries == 19U);

bool sourceRootConvolution(std::uint32_t convolution) {
  return convolution >= kSourceRootFirstConvolution &&
         convolution <= kSourceRootLastConvolution &&
         (convolution & (convolution - 1U)) == 0U;
}

constexpr char kQOrderManifestMagic[8] =
    {'T', 'G', 'D', 'Q', 'O', 'R', 'D', '1'};
constexpr std::uint32_t kQOrderManifestVersion = 1U;
constexpr std::uint32_t kQOrderBounded = 0U;
constexpr std::uint32_t kQOrderFullSource = 1U;
constexpr std::uint32_t kPrimitiveRosterVersion = 2U;
constexpr std::uint32_t kSourceQStart = 10001U;
constexpr std::uint32_t kSourceQStop = 400000U;
constexpr std::uint64_t kSourcePrimitiveModuli = 292500ULL;
constexpr std::uint64_t kSourcePrimitiveTRows = 3637613167ULL;
constexpr char kQOrderSchedulerAlgorithm[] =
    "primitive-v2-component-signature-lexicographic-q-v1";
constexpr char kQOrderSourceDomain[] = "TGDQ_SOURCE_ROSTER_V1";
constexpr char kQOrderExecutionDomain[] = "TGDQ_EXECUTION_ORDER_V1";
constexpr char kPhaseScheduleDomain[] = "TGDQ_PHASE_SCHEDULE_V1";
constexpr char kPinnedSourceRosterDigest[] =
    "d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c";
constexpr char kPinnedExecutionOrderDigest[] =
    "34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd";

struct QOrderManifestHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t classification;
  std::uint32_t primitive_roster_version;
  std::uint32_t q_start;
  std::uint32_t q_stop;
  std::uint32_t record_size;
  std::uint64_t q_count;
  std::uint64_t t_row_count;
  unsigned char source_roster_sha256[32];
  unsigned char execution_order_sha256[32];
};

struct QOrderManifestRecord {
  std::uint32_t q;
  std::uint32_t t_index_count;
};

static_assert(sizeof(QOrderManifestHeader) == 112U);
static_assert(sizeof(QOrderManifestRecord) == 8U);

struct LoadedQOrderManifest {
  QOrderManifestHeader header{};
  std::vector<QOrderManifestRecord> execution;
  sparkinterval::Sha256Digest file_digest{};
  sparkinterval::Sha256Digest source_digest{};
  sparkinterval::Sha256Digest execution_digest{};

  const char* classificationName() const {
    return header.classification == kQOrderFullSource
               ? "full-primitive-v2-source-permutation"
               : "bounded-primitive-v2-conformance-permutation";
  }
};

struct PhaseScheduleRecord {
  std::uint32_t execution_q_index = 0U;
  std::uint32_t q = 0U;
  std::uint32_t first_t_index = 0U;
  std::uint32_t t_index_stop_exclusive = 0U;

  std::uint32_t tIndexCount() const {
    return t_index_stop_exclusive - first_t_index;
  }
};

struct PhaseScheduleCoverage {
  std::uint32_t first_t_index = 0U;
  std::uint32_t t_index_stop_exclusive = 0U;
  std::uint32_t start_execution_q_index = 0U;
  std::uint32_t stop_execution_q_index = 0U;
  sparkinterval::Sha256Digest phase_plan_digest{};
  sparkinterval::Sha256Digest phase_schedule_digest{};
  std::vector<PhaseScheduleRecord> active;
  std::uint64_t t_row_count = 0U;
};

bool hasPrimitiveRoster(std::uint32_t q) {
  return q >= kSourceQStart && q <= kSourceQStop && q % 4U != 2U;
}

std::uint32_t maximumSourceTRows(std::uint32_t q) {
  if (q < kSourceQStart || q > kSourceQStop) {
    throw std::runtime_error("scheduled q is outside the source range");
  }
  const std::uint64_t additive =
      q % 2U == 0U ? 75000000ULL : 37500000ULL;
  const std::uint64_t height_numerator =
      std::max(100000000ULL, 200ULL * q + additive);
  return static_cast<std::uint32_t>(
      height_numerator * 64ULL / (5ULL * q) + 1ULL);
}

std::array<std::uint32_t, da::kMaxComponents + 1U> qOrderKey(
    std::uint32_t q) {
  auto orders = canonicalOrders(q);
  std::sort(orders.begin(), orders.end(), std::greater<std::uint32_t>());
  std::array<std::uint32_t, da::kMaxComponents + 1U> key{};
  std::copy(orders.begin(), orders.end(), key.begin());
  key.back() = q;
  return key;
}

bool qOrderLess(const QOrderManifestRecord& left,
                const QOrderManifestRecord& right) {
  return qOrderKey(left.q) < qOrderKey(right.q);
}

sparkinterval::Sha256Digest qRecordDigest(
    const char* domain, std::size_t domain_size,
    const std::vector<QOrderManifestRecord>& records) {
  sparkinterval::detail::Sha256 hasher;
  hasher.update(domain, domain_size);
  for (const auto& record : records) {
    hasher.update(&record, sizeof(record));
  }
  return hasher.finish();
}

LoadedQOrderManifest loadQOrderManifest(const std::string& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("could not open q-order manifest");
  const std::streamoff end = input.tellg();
  if (end < static_cast<std::streamoff>(sizeof(QOrderManifestHeader)) ||
      end > static_cast<std::streamoff>(
                sizeof(QOrderManifestHeader) +
                (kSourceQStop - kSourceQStart + 1ULL) *
                    sizeof(QOrderManifestRecord))) {
    throw std::runtime_error("q-order manifest size is outside its bound");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(raw.data()),
             static_cast<std::streamsize>(raw.size()));
  if (!input) throw std::runtime_error("could not read q-order manifest");

  LoadedQOrderManifest loaded;
  std::memcpy(&loaded.header, raw.data(), sizeof(loaded.header));
  const auto& header = loaded.header;
  if (std::memcmp(header.magic, kQOrderManifestMagic, 8U) != 0 ||
      header.version != kQOrderManifestVersion ||
      (header.classification != kQOrderBounded &&
       header.classification != kQOrderFullSource) ||
      header.primitive_roster_version != kPrimitiveRosterVersion ||
      header.record_size != sizeof(QOrderManifestRecord) ||
      header.q_count == 0U ||
      header.q_count >
          static_cast<std::uint64_t>(kSourceQStop - kSourceQStart + 1U) ||
      raw.size() != sizeof(QOrderManifestHeader) +
                        header.q_count * sizeof(QOrderManifestRecord)) {
    throw std::runtime_error("q-order manifest header or size differs");
  }
  loaded.execution.resize(static_cast<std::size_t>(header.q_count));
  std::memcpy(loaded.execution.data(),
              raw.data() + sizeof(QOrderManifestHeader),
              loaded.execution.size() * sizeof(QOrderManifestRecord));
  loaded.file_digest = sparkinterval::sha256(raw.data(), raw.size());

  std::vector<bool> seen(kSourceQStop + 1U, false);
  std::uint64_t rows = 0U;
  std::uint32_t q_min = kSourceQStop;
  std::uint32_t q_max = kSourceQStart;
  for (const auto& record : loaded.execution) {
    if (!hasPrimitiveRoster(record.q) || seen[record.q] ||
        record.t_index_count == 0U ||
        record.t_index_count > maximumSourceTRows(record.q)) {
      throw std::runtime_error(
          "q-order record is duplicate or outside primitive V2");
    }
    seen[record.q] = true;
    rows += record.t_index_count;
    q_min = std::min(q_min, record.q);
    q_max = std::max(q_max, record.q);
  }
  if (rows != header.t_row_count || q_min != header.q_start ||
      q_max != header.q_stop) {
    throw std::runtime_error("q-order range or row coverage differs");
  }

  for (std::size_t index = 1U; index < loaded.execution.size(); ++index) {
    if (!qOrderLess(loaded.execution[index - 1U],
                    loaded.execution[index])) {
      throw std::runtime_error(
          "q-order records are not the canonical execution permutation");
    }
  }
  auto source = loaded.execution;
  std::sort(source.begin(), source.end(),
            [](const auto& left, const auto& right) {
              return left.q < right.q;
            });
  loaded.source_digest =
      qRecordDigest(kQOrderSourceDomain, sizeof(kQOrderSourceDomain) - 1U,
                    source);
  loaded.execution_digest =
      qRecordDigest(kQOrderExecutionDomain,
                    sizeof(kQOrderExecutionDomain) - 1U, loaded.execution);
  if (!std::equal(loaded.source_digest.begin(), loaded.source_digest.end(),
                  header.source_roster_sha256) ||
      !std::equal(loaded.execution_digest.begin(),
                  loaded.execution_digest.end(),
                  header.execution_order_sha256)) {
    throw std::runtime_error("q-order manifest digest differs");
  }

  if (header.classification == kQOrderFullSource) {
    if (header.q_start != kSourceQStart || header.q_stop != kSourceQStop ||
        header.q_count != kSourcePrimitiveModuli ||
        header.t_row_count != kSourcePrimitiveTRows ||
        sparkinterval::lowercase_hex(loaded.source_digest) !=
            kPinnedSourceRosterDigest ||
        sparkinterval::lowercase_hex(loaded.execution_digest) !=
            kPinnedExecutionOrderDigest) {
      throw std::runtime_error("full-source q-order identity differs");
    }
    std::size_t index = 0U;
    for (std::uint32_t q = kSourceQStart; q <= kSourceQStop; ++q) {
      if (!hasPrimitiveRoster(q)) continue;
      if (index >= source.size() || source[index].q != q ||
          source[index].t_index_count != maximumSourceTRows(q)) {
        throw std::runtime_error(
            "full-source q-order roster or height differs");
      }
      ++index;
    }
    if (index != source.size()) {
      throw std::runtime_error("full-source q-order roster has trailing q");
    }
  }
  return loaded;
}

PhaseScheduleCoverage makePhaseScheduleCoverage(
    const LoadedQOrderManifest& schedule,
    const sparkinterval::Sha256Digest& phasePlanDigest,
    std::uint32_t firstTIndex, std::uint32_t stopTIndex,
    std::uint32_t startExecutionQIndex,
    std::uint32_t stopExecutionQIndex) {
  if (firstTIndex >= stopTIndex ||
      startExecutionQIndex >= stopExecutionQIndex ||
      stopExecutionQIndex > schedule.execution.size()) {
    throw std::runtime_error("phase scheduled geometry is empty or out of range");
  }
  std::uint32_t maximumRows = 0U;
  for (std::uint32_t index = startExecutionQIndex;
       index < stopExecutionQIndex; ++index) {
    maximumRows =
        std::max(maximumRows, schedule.execution[index].t_index_count);
  }
  if (maximumRows < stopTIndex) {
    throw std::runtime_error(
        "phase scheduled stop is unused by every selected modulus");
  }

  PhaseScheduleCoverage phase;
  phase.first_t_index = firstTIndex;
  phase.t_index_stop_exclusive = stopTIndex;
  phase.start_execution_q_index = startExecutionQIndex;
  phase.stop_execution_q_index = stopExecutionQIndex;
  phase.phase_plan_digest = phasePlanDigest;
  for (std::uint32_t index = startExecutionQIndex;
       index < stopExecutionQIndex; ++index) {
    const auto& parent = schedule.execution[index];
    if (parent.t_index_count <= firstTIndex) continue;
    const std::uint32_t activeStop =
        std::min(parent.t_index_count, stopTIndex);
    phase.active.push_back(
        {index, parent.q, firstTIndex, activeStop});
    phase.t_row_count +=
        static_cast<std::uint64_t>(activeStop - firstTIndex);
  }
  if (phase.active.empty()) {
    throw std::runtime_error("phase scheduled projection has no active modulus");
  }

  sparkinterval::detail::Sha256 commitment;
  commitment.update(kPhaseScheduleDomain,
                    sizeof(kPhaseScheduleDomain) - 1U);
  commitment.update(schedule.file_digest.data(),
                    schedule.file_digest.size());
  commitment.update(schedule.execution_digest.data(),
                    schedule.execution_digest.size());
  commitment.update(phase.phase_plan_digest.data(),
                    phase.phase_plan_digest.size());
  hashUint32LE(&commitment, firstTIndex);
  hashUint32LE(&commitment, stopTIndex);
  hashUint32LE(&commitment, startExecutionQIndex);
  hashUint32LE(&commitment, stopExecutionQIndex);
  for (const auto& record : phase.active) {
    hashUint32LE(&commitment, record.execution_q_index);
    hashUint32LE(&commitment, record.q);
    hashUint32LE(&commitment, record.first_t_index);
    hashUint32LE(&commitment, record.t_index_stop_exclusive);
  }
  phase.phase_schedule_digest = commitment.finish();
  return phase;
}

void includeCandidate(mpfr_t lo, mpfr_t hi, mpfr_srcptr candidateLo,
                      mpfr_srcptr candidateHi) {
  if (mpfr_less_p(candidateLo, lo)) mpfr_set(lo, candidateLo, MPFR_RNDD);
  if (mpfr_greater_p(candidateHi, hi)) mpfr_set(hi, candidateHi, MPFR_RNDU);
}

RealInterval trigInterval(std::uint64_t numerator, std::uint64_t denominator,
                          bool sine) {
  if (denominator == 0U) throw std::runtime_error("zero twiddle denominator");
  numerator %= 2U * denominator;
  mpq_t rational;
  mpq_init(rational);
  mpq_set_ui(rational, numerator, denominator);
  mpq_canonicalize(rational);
  MpfrValue xLo, xHi, lo, hi, down, up, point;
  mpfr_set_q(xLo.value, rational, MPFR_RNDD);
  mpfr_set_q(xHi.value, rational, MPFR_RNDU);
  if (sine) {
    mpfr_sinpi(lo.value, xLo.value, MPFR_RNDD);
    mpfr_sinpi(hi.value, xLo.value, MPFR_RNDU);
    mpfr_sinpi(down.value, xHi.value, MPFR_RNDD);
    mpfr_sinpi(up.value, xHi.value, MPFR_RNDU);
  } else {
    mpfr_cospi(lo.value, xLo.value, MPFR_RNDD);
    mpfr_cospi(hi.value, xLo.value, MPFR_RNDU);
    mpfr_cospi(down.value, xHi.value, MPFR_RNDD);
    mpfr_cospi(up.value, xHi.value, MPFR_RNDU);
  }
  includeCandidate(lo.value, hi.value, down.value, up.value);

  // Include every possible interior extremum.  The MPFR argument is a tiny
  // enclosure of an exact rational, but this explicit test avoids relying on
  // it remaining in one monotonicity interval.
  const double critical[] = {0.0, 0.5, 1.0, 1.5, 2.0};
  for (const double c : critical) {
    mpfr_set_d(point.value, c, MPFR_RNDN);
    if (mpfr_lessequal_p(xLo.value, point.value) &&
        mpfr_greaterequal_p(xHi.value, point.value)) {
      // Values at half-integers/integers are exactly -1, 0, or 1.  Encode
      // those values combinatorially rather than importing libm here.
      const int twice = static_cast<int>(std::llround(2.0 * c));
      int encoded = 0;
      if (sine) {
        if (twice == 1) encoded = 1;
        if (twice == 3) encoded = -1;
      } else {
        if (twice == 0 || twice == 4) encoded = 1;
        if (twice == 2) encoded = -1;
      }
      mpfr_set_si(down.value, encoded, MPFR_RNDD);
      mpfr_set_si(up.value, encoded, MPFR_RNDU);
      includeCandidate(lo.value, hi.value, down.value, up.value);
    }
  }
  const double resultLo = mpfr_get_d(lo.value, MPFR_RNDD);
  const double resultHi = mpfr_get_d(hi.value, MPFR_RNDU);
  mpq_clear(rational);
  return {resultLo, resultHi};
}

ComplexInterval unitRoot(std::uint64_t numerator, std::uint64_t denominator,
                         int sign) {
  if (sign < 0 && numerator != 0U) {
    numerator = (2U * denominator - numerator % (2U * denominator)) %
                (2U * denominator);
  }
  return {trigInterval(numerator, denominator, false),
          trigInterval(numerator, denominator, true)};
}

std::uint64_t doubledDenominator(std::uint32_t length) {
  if (length == 0U ||
      static_cast<std::uint64_t>(length) >
          std::numeric_limits<std::uint64_t>::max() / 2U) {
    throw std::runtime_error("chirp denominator is zero or overflows");
  }
  return 2U * static_cast<std::uint64_t>(length);
}

std::uint64_t squarePhaseNumerator(std::uint64_t index,
                                   std::uint32_t length) {
  const std::uint64_t period = doubledDenominator(length);
  if (index != 0U &&
      index > std::numeric_limits<std::uint64_t>::max() / index) {
    throw std::runtime_error("chirp square phase numerator overflows");
  }
  return (index * index) % period;
}

std::uint64_t oddStepPhaseNumerator(std::uint64_t index,
                                    std::uint32_t length) {
  const std::uint64_t period = doubledDenominator(length);
  if (index >
      (std::numeric_limits<std::uint64_t>::max() - 1U) / 2U) {
    throw std::runtime_error("chirp odd-step phase numerator overflows");
  }
  return (2U * index + 1U) % period;
}

void mpfrIncludeCandidate(MpfrRealInterval* output, mpfr_srcptr candidateLo,
                          mpfr_srcptr candidateHi) {
  if (mpfr_less_p(candidateLo, output->lo.value)) {
    mpfr_set(output->lo.value, candidateLo, MPFR_RNDD);
  }
  if (mpfr_greater_p(candidateHi, output->hi.value)) {
    mpfr_set(output->hi.value, candidateHi, MPFR_RNDU);
  }
}

void mpfrTrigInterval(MpfrRealInterval* output, std::uint64_t numerator,
                      std::uint32_t denominator, bool sine,
                      MpfrChirpScratch* scratch) {
  const std::uint64_t period = doubledDenominator(denominator);
  numerator %= period;
  mpq_set_ui(scratch->rational, numerator, denominator);
  mpq_canonicalize(scratch->rational);
  mpfr_set_q(scratch->xLo.value, scratch->rational, MPFR_RNDD);
  mpfr_set_q(scratch->xHi.value, scratch->rational, MPFR_RNDU);
  if (sine) {
    mpfr_sinpi(output->lo.value, scratch->xLo.value, MPFR_RNDD);
    mpfr_sinpi(output->hi.value, scratch->xLo.value, MPFR_RNDU);
    mpfr_sinpi(scratch->candidateLo.value, scratch->xHi.value, MPFR_RNDD);
    mpfr_sinpi(scratch->candidateHi.value, scratch->xHi.value, MPFR_RNDU);
  } else {
    mpfr_cospi(output->lo.value, scratch->xLo.value, MPFR_RNDD);
    mpfr_cospi(output->hi.value, scratch->xLo.value, MPFR_RNDU);
    mpfr_cospi(scratch->candidateLo.value, scratch->xHi.value, MPFR_RNDD);
    mpfr_cospi(scratch->candidateHi.value, scratch->xHi.value, MPFR_RNDU);
  }
  mpfrIncludeCandidate(output, scratch->candidateLo.value,
                       scratch->candidateHi.value);

  // The exact rational lies in [0,2).  Include any half-integer or integer
  // extremum crossed by its directed MPFR argument enclosure.
  for (int twice = 0; twice <= 4; ++twice) {
    mpfr_set_si(scratch->point.value, twice, MPFR_RNDN);
    mpfr_div_2ui(scratch->point.value, scratch->point.value, 1U,
                 MPFR_RNDN);
    if (mpfr_lessequal_p(scratch->xLo.value, scratch->point.value) &&
        mpfr_greaterequal_p(scratch->xHi.value, scratch->point.value)) {
      int encoded = 0;
      if (sine) {
        if (twice == 1) encoded = 1;
        if (twice == 3) encoded = -1;
      } else {
        if (twice == 0 || twice == 4) encoded = 1;
        if (twice == 2) encoded = -1;
      }
      mpfr_set_si(scratch->candidateLo.value, encoded, MPFR_RNDD);
      mpfr_set_si(scratch->candidateHi.value, encoded, MPFR_RNDU);
      mpfrIncludeCandidate(output, scratch->candidateLo.value,
                           scratch->candidateHi.value);
    }
  }
}

void mpfrUnitRoot(MpfrComplexInterval* output, std::uint64_t numerator,
                  std::uint32_t denominator, int sign,
                  MpfrChirpScratch* scratch) {
  const std::uint64_t period = doubledDenominator(denominator);
  numerator %= period;
  if (sign < 0 && numerator != 0U) {
    numerator = period - numerator;
  }
  mpfrTrigInterval(&output->re, numerator, denominator, false, scratch);
  mpfrTrigInterval(&output->im, numerator, denominator, true, scratch);
}

void mpfrRealMul(MpfrRealInterval* output, const MpfrRealInterval& left,
                 const MpfrRealInterval& right,
                 MpfrChirpScratch* scratch) {
  const auto endpoints = [&](mpfr_srcptr lowerLeft,
                             mpfr_srcptr lowerRight,
                             mpfr_srcptr upperLeft,
                             mpfr_srcptr upperRight) {
    mpfr_mul(output->lo.value, lowerLeft, lowerRight, MPFR_RNDD);
    mpfr_mul(output->hi.value, upperLeft, upperRight, MPFR_RNDU);
  };
  const bool leftNonnegative = mpfr_sgn(left.lo.value) >= 0;
  const bool leftNonpositive = mpfr_sgn(left.hi.value) <= 0;
  const bool rightNonnegative = mpfr_sgn(right.lo.value) >= 0;
  const bool rightNonpositive = mpfr_sgn(right.hi.value) <= 0;
  if (leftNonnegative) {
    if (rightNonnegative) {
      endpoints(left.lo.value, right.lo.value,
                left.hi.value, right.hi.value);
    } else if (rightNonpositive) {
      endpoints(left.hi.value, right.lo.value,
                left.lo.value, right.hi.value);
    } else {
      endpoints(left.hi.value, right.lo.value,
                left.hi.value, right.hi.value);
    }
  } else if (leftNonpositive) {
    if (rightNonnegative) {
      endpoints(left.lo.value, right.hi.value,
                left.hi.value, right.lo.value);
    } else if (rightNonpositive) {
      endpoints(left.hi.value, right.hi.value,
                left.lo.value, right.lo.value);
    } else {
      endpoints(left.lo.value, right.hi.value,
                left.lo.value, right.lo.value);
    }
  } else if (rightNonnegative) {
    endpoints(left.lo.value, right.hi.value,
              left.hi.value, right.hi.value);
  } else if (rightNonpositive) {
    endpoints(left.hi.value, right.lo.value,
              left.lo.value, right.lo.value);
  } else {
    mpfr_mul(output->lo.value, left.lo.value, right.hi.value, MPFR_RNDD);
    mpfr_mul(scratch->productLo.value, left.hi.value, right.lo.value,
             MPFR_RNDD);
    if (mpfr_less_p(scratch->productLo.value, output->lo.value)) {
      mpfr_set(output->lo.value, scratch->productLo.value, MPFR_RNDD);
    }
    mpfr_mul(output->hi.value, left.lo.value, right.lo.value, MPFR_RNDU);
    mpfr_mul(scratch->productHi.value, left.hi.value, right.hi.value,
             MPFR_RNDU);
    if (mpfr_greater_p(scratch->productHi.value, output->hi.value)) {
      mpfr_set(output->hi.value, scratch->productHi.value, MPFR_RNDU);
    }
  }
}

void mpfrRealAdd(MpfrRealInterval* output, const MpfrRealInterval& left,
                 const MpfrRealInterval& right) {
  mpfr_add(output->lo.value, left.lo.value, right.lo.value, MPFR_RNDD);
  mpfr_add(output->hi.value, left.hi.value, right.hi.value, MPFR_RNDU);
}

void mpfrRealSub(MpfrRealInterval* output, const MpfrRealInterval& left,
                 const MpfrRealInterval& right) {
  mpfr_sub(output->lo.value, left.lo.value, right.hi.value, MPFR_RNDD);
  mpfr_sub(output->hi.value, left.hi.value, right.lo.value, MPFR_RNDU);
}

void mpfrComplexMul(MpfrComplexInterval* output,
                    const MpfrComplexInterval& left,
                    const MpfrComplexInterval& right,
                    MpfrChirpScratch* scratch) {
  mpfrRealMul(&scratch->ac, left.re, right.re, scratch);
  mpfrRealMul(&scratch->bd, left.im, right.im, scratch);
  mpfrRealMul(&scratch->ad, left.re, right.im, scratch);
  mpfrRealMul(&scratch->bc, left.im, right.re, scratch);
  mpfrRealSub(&output->re, scratch->ac, scratch->bd);
  mpfrRealAdd(&output->im, scratch->ad, scratch->bc);
}

ComplexInterval outwardBinary64(const MpfrComplexInterval& value) {
  return {{mpfr_get_d(value.re.lo.value, MPFR_RNDD),
           mpfr_get_d(value.re.hi.value, MPFR_RNDU)},
          {mpfr_get_d(value.im.lo.value, MPFR_RNDD),
           mpfr_get_d(value.im.hi.value, MPFR_RNDU)}};
}

ComplexInterval conjugateEnclosure(const ComplexInterval& value) {
  return {value.re, {-value.im.hi, -value.im.lo}};
}

std::vector<ComplexInterval> conjugateEnclosures(
    const std::vector<ComplexInterval>& values) {
  std::vector<ComplexInterval> result;
  result.reserve(values.size());
  for (const auto& value : values) {
    result.push_back(conjugateEnclosure(value));
  }
  return result;
}

bool finiteOrdered(const ComplexInterval& value) {
  return std::isfinite(value.re.lo) && std::isfinite(value.re.hi) &&
         std::isfinite(value.im.lo) && std::isfinite(value.im.hi) &&
         value.re.lo <= value.re.hi && value.im.lo <= value.im.hi;
}

void selectCudaDevice(std::uint32_t device) {
  if (device > static_cast<std::uint32_t>(
                   std::numeric_limits<int>::max())) {
    throw std::runtime_error("CUDA device index exceeds int");
  }
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error("strict target requires compute capability 9.0");
  }
#endif
}

__device__ __forceinline__ RealInterval add(RealInterval x, RealInterval y) {
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
}

__device__ __forceinline__ RealInterval sub(RealInterval x, RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval mul(RealInterval x, RealInterval y) {
  // Directed products are monotone on each sign quadrant.  The transform's
  // MPFR-built roots and ordinary data boxes are overwhelmingly
  // sign-definite, so select the extremal endpoint pair instead of evaluating
  // all four pairs in both rounding modes.  Crossing intervals retain the
  // exact four-candidate hull required by natural interval multiplication.
  if (x.lo >= 0.0) {
    if (y.lo >= 0.0) {
      return {__dmul_rd(x.lo, y.lo), __dmul_ru(x.hi, y.hi)};
    }
    if (y.hi <= 0.0) {
      return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.lo, y.hi)};
    }
    return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.hi, y.hi)};
  }
  if (x.hi <= 0.0) {
    if (y.lo >= 0.0) {
      return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.hi, y.lo)};
    }
    if (y.hi <= 0.0) {
      return {__dmul_rd(x.hi, y.hi), __dmul_ru(x.lo, y.lo)};
    }
    return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.lo, y.lo)};
  }
  if (y.lo >= 0.0) {
    return {__dmul_rd(x.lo, y.hi), __dmul_ru(x.hi, y.hi)};
  }
  if (y.hi <= 0.0) {
    return {__dmul_rd(x.hi, y.lo), __dmul_ru(x.lo, y.lo)};
  }
  return {
      fmin(__dmul_rd(x.lo, y.hi), __dmul_rd(x.hi, y.lo)),
      fmax(__dmul_ru(x.lo, y.lo), __dmul_ru(x.hi, y.hi)),
  };
}

__device__ __forceinline__ ComplexInterval cadd(ComplexInterval x,
                                                 ComplexInterval y) {
  return {add(x.re, y.re), add(x.im, y.im)};
}

__device__ __forceinline__ ComplexInterval csub(ComplexInterval x,
                                                 ComplexInterval y) {
  return {sub(x.re, y.re), sub(x.im, y.im)};
}

__device__ __forceinline__ ComplexInterval cmul(ComplexInterval x,
                                                 ComplexInterval y) {
  return {sub(mul(x.re, y.re), mul(x.im, y.im)),
          add(mul(x.re, y.im), mul(x.im, y.re))};
}

__global__ void initializeA(const ComplexInterval* input,
                            ComplexInterval* workspace,
                            const ComplexInterval* chirp, std::uint64_t total,
                            std::uint32_t length, std::uint32_t convolution,
                            std::uint64_t stride, std::uint32_t logConvolution) {
  const std::uint64_t lines = total / length;
  const std::uint64_t count = lines * convolution;
  for (std::uint64_t flat = blockIdx.x * blockDim.x + threadIdx.x;
       flat < count; flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / convolution;
    const std::uint32_t position = static_cast<std::uint32_t>(flat % convolution);
    std::uint32_t reversed = __brev(position) >> (32U - logConvolution);
    ComplexInterval value{{0.0, 0.0}, {0.0, 0.0}};
    if (position < length) {
      const std::uint64_t outer = line / stride;
      const std::uint64_t inner = line % stride;
      const std::uint64_t source = outer * length * stride +
                                   static_cast<std::uint64_t>(position) * stride +
                                   inner;
      value = cmul(input[source], chirp[position]);
    }
    workspace[line * convolution + reversed] = value;
  }
}

__global__ void bitReverseCopy(const ComplexInterval* input,
                               ComplexInterval* output, std::uint64_t lines,
                               std::uint32_t length, std::uint32_t logLength) {
  const std::uint64_t count = lines * length;
  for (std::uint64_t flat = blockIdx.x * blockDim.x + threadIdx.x;
       flat < count; flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / length;
    const std::uint32_t position = static_cast<std::uint32_t>(flat % length);
    const std::uint32_t reversed = __brev(position) >> (32U - logLength);
    output[line * length + reversed] = input[flat];
  }
}

__global__ void fftStage(ComplexInterval* data, const ComplexInterval* roots,
                         std::uint64_t lines, std::uint32_t transformLength,
                         std::uint32_t stageLength) {
  const std::uint64_t butterflies = lines * transformLength / 2U;
  const std::uint32_t half = stageLength / 2U;
  const std::uint32_t rootOffset = half - 1U;
  for (std::uint64_t flat = blockIdx.x * blockDim.x + threadIdx.x;
       flat < butterflies;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / (transformLength / 2U);
    const std::uint64_t local = flat % (transformLength / 2U);
    const std::uint64_t block = local / half;
    const std::uint32_t j = static_cast<std::uint32_t>(local % half);
    const std::uint64_t left = line * transformLength + block * stageLength + j;
    const std::uint64_t right = left + half;
    const ComplexInterval u = data[left];
    const ComplexInterval v = cmul(data[right], roots[rootOffset + j]);
    data[left] = cadd(u, v);
    data[right] = csub(u, v);
  }
}

// The initial radix-2 stages never communicate across one fixed-size tile.
// Keeping that tile in shared memory preserves the exact DIT butterfly graph
// and directed operation order while replacing several full-array global
// read/write passes with one.  A grid-stride loop covers source-sized line
// counts without relying on a one-dimensional grid larger than 65535 blocks.
__global__ void fftInitialStages(ComplexInterval* data,
                                 const ComplexInterval* roots,
                                 std::uint64_t lines,
                                 std::uint32_t transformLength,
                                 std::uint32_t tileLength) {
  extern __shared__ ComplexInterval tile[];
  const std::uint64_t tilesPerLine = transformLength / tileLength;
  const std::uint64_t tileCount = lines * tilesPerLine;
  for (std::uint64_t tileIndex = blockIdx.x; tileIndex < tileCount;
       tileIndex += gridDim.x) {
    const std::uint64_t line = tileIndex / tilesPerLine;
    const std::uint64_t tileInLine = tileIndex % tilesPerLine;
    const std::uint64_t base =
        line * transformLength + tileInLine * tileLength;
    for (std::uint32_t position = threadIdx.x; position < tileLength;
         position += blockDim.x) {
      tile[position] = data[base + position];
    }
    __syncthreads();
    for (std::uint32_t stageLength = 2U; stageLength <= tileLength;
         stageLength <<= 1U) {
      const std::uint32_t half = stageLength / 2U;
      const std::uint32_t rootOffset = half - 1U;
      for (std::uint32_t local = threadIdx.x; local < tileLength / 2U;
           local += blockDim.x) {
        const std::uint32_t stageBlock = local / half;
        const std::uint32_t j = local % half;
        const std::uint32_t left = stageBlock * stageLength + j;
        const std::uint32_t right = left + half;
        const ComplexInterval u = tile[left];
        const ComplexInterval v =
            cmul(tile[right], roots[rootOffset + j]);
        tile[left] = cadd(u, v);
        tile[right] = csub(u, v);
      }
      __syncthreads();
    }
    for (std::uint32_t position = threadIdx.x; position < tileLength;
         position += blockDim.x) {
      data[base + position] = tile[position];
    }
    __syncthreads();
  }
}

// The inverse radix-2 transform consumes bit-reversed input.  Multiplication
// by the transformed Bluestein kernel is pointwise, so write that rounded
// product directly to its bit-reversed destination and avoid one complete
// global-memory pass and one launch.
__global__ void pointwiseBitReverseCopy(
    const ComplexInterval* values, ComplexInterval* output,
    const ComplexInterval* multiplier, std::uint64_t lines,
    std::uint32_t length, std::uint32_t logLength) {
  const std::uint64_t count = lines * length;
  for (std::uint64_t flat = blockIdx.x * blockDim.x + threadIdx.x;
       flat < count; flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / length;
    const std::uint32_t position = static_cast<std::uint32_t>(flat % length);
    const std::uint32_t reversed =
        __brev(position) >> (32U - logLength);
    output[line * length + reversed] =
        cmul(values[flat], multiplier[position]);
  }
}

__global__ void gatherOutput(const ComplexInterval* workspace,
                             ComplexInterval* output,
                             const ComplexInterval* chirp, std::uint64_t total,
                             std::uint32_t length, std::uint32_t convolution,
                             std::uint64_t stride,
                             double inverseConvolution) {
  for (std::uint64_t flat = blockIdx.x * blockDim.x + threadIdx.x;
       flat < total; flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / length;
    const std::uint32_t k = static_cast<std::uint32_t>(flat % length);
    ComplexInterval value = cmul(workspace[line * convolution + k], chirp[k]);
    // convolution is exactly 2^logConvolution, so multiplication by its
    // exactly representable reciprocal has the same real result and directed
    // binary64 rounding as division.  --ftz=false preserves subnormal
    // behavior, while the positive scale also preserves signed zero and
    // infinity.  This removes two directed divisions per complex output.
    value.re = {__dmul_rd(value.re.lo, inverseConvolution),
                __dmul_ru(value.re.hi, inverseConvolution)};
    value.im = {__dmul_rd(value.im.lo, inverseConvolution),
                __dmul_ru(value.im.hi, inverseConvolution)};
    const std::uint64_t outer = line / stride;
    const std::uint64_t inner = line % stride;
    const std::uint64_t target = outer * length * stride +
                                 static_cast<std::uint64_t>(k) * stride + inner;
    output[target] = value;
  }
}

std::uint32_t blocksFor(std::uint64_t count) {
  constexpr std::uint32_t kThreads = 256U;
  return static_cast<std::uint32_t>(std::min<std::uint64_t>(
      65535U, std::max<std::uint64_t>(1U, (count + kThreads - 1U) / kThreads)));
}

void launchFft(ComplexInterval* data, const ComplexInterval* roots,
               std::uint64_t lines, std::uint32_t length) {
  constexpr std::uint32_t kThreads = 256U;
  constexpr std::uint32_t kTileLength = 1024U;
  const std::uint32_t tileLength = std::min(length, kTileLength);
  const std::uint64_t tileCount =
      lines * (static_cast<std::uint64_t>(length) / tileLength);
  const std::uint32_t tileBlocks = static_cast<std::uint32_t>(
      std::min<std::uint64_t>(65535U, std::max<std::uint64_t>(1U, tileCount)));
  const std::uint32_t tileThreads =
      std::max(32U, std::min(256U, tileLength / 2U));
  fftInitialStages<<<tileBlocks, tileThreads,
                     tileLength * sizeof(ComplexInterval)>>>(
      data, roots, lines, length, tileLength);
  CUDA_CHECK(cudaGetLastError());
  for (std::uint32_t stage = tileLength << 1U; stage <= length;
       stage <<= 1U) {
    const std::uint64_t count = lines * length / 2U;
    fftStage<<<blocksFor(count), kThreads>>>(data, roots, lines, length, stage);
    CUDA_CHECK(cudaGetLastError());
  }
}

// Independent direct-root builder retained for qualification. Production uses
// the periodic-anchor recurrence below.
std::vector<ComplexInterval> directFftRoots(
    std::uint32_t length, int sign) {
  if (!sourceRootConvolution(length)) {
    throw std::runtime_error(
        "direct FFT-root length is outside the source catalog");
  }
  if (sign != -1 && sign != 1) {
    throw std::runtime_error("direct FFT-root sign must be -1 or +1");
  }
  std::vector<ComplexInterval> roots(length - 1U);
  for (std::uint32_t stage = 2U; stage <= length; stage <<= 1U) {
    const std::uint32_t half = stage / 2U;
    const std::uint32_t offset = half - 1U;
    for (std::uint32_t j = 0; j < half; ++j) {
      roots[offset + j] = unitRoot(2ULL * j, stage, sign);
    }
  }
  return roots;
}

// Independent direct-root builder retained for diagnostic comparison.  The
// production plan below uses the periodic-anchor recurrence.
std::vector<ComplexInterval> directChirp(std::uint32_t length, int sign) {
  if (sign != -1 && sign != 1) {
    throw std::runtime_error("direct chirp sign must be -1 or +1");
  }
  if (length > da::kMaximumModulus) {
    throw std::runtime_error("direct chirp length exceeds source range");
  }
  doubledDenominator(length);
  std::vector<ComplexInterval> result(length);
  for (std::uint64_t n = 0; n < length; ++n) {
    result[n] = unitRoot(squarePhaseNumerator(n, length), length, sign);
  }
  return result;
}

struct ChirpStateRecord {
  ComplexInterval chirp;
  ComplexInterval oddStep;
};

static_assert(sizeof(ChirpStateRecord) == 64U);
static_assert(std::is_standard_layout_v<ChirpStateRecord>);
static_assert(std::is_trivially_copyable_v<ChirpStateRecord>);

struct ChirpGenerationStats {
  std::uint64_t anchors = 0U;
  std::uint64_t recurrenceUpdates = 0U;
  double maximumMpfrComponentWidth = 0.0;
  double maximumBinary64ComponentWidth = 0.0;
};

double componentWidth(const RealInterval& value) {
  return value.hi - value.lo;
}

double mpfrComponentWidth(const MpfrRealInterval& value,
                          MpfrValue* temporary) {
  mpfr_sub(temporary->value, value.hi.value, value.lo.value, MPFR_RNDU);
  return mpfr_get_d(temporary->value, MPFR_RNDU);
}

struct FftRootGenerationStats {
  std::uint64_t stages = 0U;
  std::uint64_t anchors = 0U;
  std::uint64_t recurrenceUpdates = 0U;
  double maximumMpfrComponentWidth = 0.0;
  double maximumBinary64ComponentWidth = 0.0;
};

std::vector<ComplexInterval> recurrenceFftRoots(
    std::uint32_t length, int sign,
    FftRootGenerationStats* generationStats = nullptr) {
  if (!sourceRootConvolution(length)) {
    throw std::runtime_error(
        "recurrence FFT-root length is outside the source catalog");
  }
  if (sign != -1 && sign != 1) {
    throw std::runtime_error("recurrence FFT-root sign must be -1 or +1");
  }

  std::vector<ComplexInterval> roots(length - 1U);
  MpfrChirpScratch scratch(kFftRootPrecision);
  MpfrComplexInterval state[2] = {
      MpfrComplexInterval(kFftRootPrecision),
      MpfrComplexInterval(kFftRootPrecision),
  };
  MpfrComplexInterval unitStep(kFftRootPrecision);
  std::size_t active = 0U;
  FftRootGenerationStats stats;

  for (std::uint32_t stage = 2U; stage <= length; stage <<= 1U) {
    const std::uint32_t half = stage / 2U;
    const std::uint32_t offset = half - 1U;
    // In the stage-s table, state[j] is the positive/negative unit root with
    // exponent j and this fixed root is exponent one.
    mpfrUnitRoot(&unitStep, 2U, stage, sign, &scratch);
    ++stats.stages;
    for (std::uint32_t j = 0U; j < half; ++j) {
      if (j % kFftRootAnchorCadence == 0U) {
        mpfrUnitRoot(
            &state[active], 2ULL * j, stage, sign, &scratch);
        ++stats.anchors;
      } else {
        const std::size_t next = 1U - active;
        mpfrComplexMul(
            &state[next], state[active], unitStep, &scratch);
        active = next;
        ++stats.recurrenceUpdates;
      }

      const std::size_t index =
          static_cast<std::size_t>(offset) + j;
      roots[index] = outwardBinary64(state[active]);
      if (!finiteOrdered(roots[index])) {
        throw std::runtime_error(
            "FFT-root recurrence produced a malformed interval");
      }
      const double width = std::max(
          componentWidth(roots[index].re),
          componentWidth(roots[index].im));
      if (!(width <= kMaximumFftRootComponentWidth)) {
        throw std::runtime_error(
            "FFT-root recurrence exceeded its binary64 width ceiling");
      }
      const double mpfrWidth = std::max(
          mpfrComponentWidth(state[active].re, &scratch.productLo),
          mpfrComponentWidth(state[active].im, &scratch.productLo));
      stats.maximumMpfrComponentWidth =
          std::max(stats.maximumMpfrComponentWidth, mpfrWidth);
      stats.maximumBinary64ComponentWidth =
          std::max(stats.maximumBinary64ComponentWidth, width);
    }
  }
  if (generationStats != nullptr) *generationStats = stats;
  return roots;
}

std::vector<ComplexInterval> recurrenceChirp(
    std::uint32_t length, int sign,
    std::vector<ChirpStateRecord>* trace = nullptr,
    ChirpGenerationStats* generationStats = nullptr) {
  if (sign != -1 && sign != 1) {
    throw std::runtime_error("chirp sign must be -1 or +1");
  }
  if (length > da::kMaximumModulus) {
    throw std::runtime_error("recurrence chirp length exceeds source range");
  }
  doubledDenominator(length);
  std::vector<ComplexInterval> result(length);
  if (trace != nullptr) trace->resize(length);

  MpfrChirpScratch scratch(kChirpPrecision);
  MpfrComplexInterval chirpState[2] = {
      MpfrComplexInterval(kChirpPrecision),
      MpfrComplexInterval(kChirpPrecision),
  };
  MpfrComplexInterval oddStepState[2] = {
      MpfrComplexInterval(kChirpPrecision),
      MpfrComplexInterval(kChirpPrecision),
  };
  MpfrComplexInterval unitStep(kChirpPrecision);
  mpfrUnitRoot(&unitStep, 2U, length, sign, &scratch);
  std::size_t active = 0U;

  ChirpGenerationStats stats;
  for (std::uint64_t n = 0U; n < length; ++n) {
    if (n % kChirpAnchorCadence == 0U) {
      mpfrUnitRoot(&chirpState[active],
                   squarePhaseNumerator(n, length), length, sign, &scratch);
      mpfrUnitRoot(&oddStepState[active],
                   oddStepPhaseNumerator(n, length), length, sign, &scratch);
      ++stats.anchors;
    } else {
      const std::size_t next = 1U - active;
      // These are exactly the two complex interval multiplications in the
      // proved c_(n+1)=c_n*d_n, d_(n+1)=d_n*u recurrence.
      mpfrComplexMul(&chirpState[next], chirpState[active],
                     oddStepState[active], &scratch);
      mpfrComplexMul(&oddStepState[next], oddStepState[active], unitStep,
                     &scratch);
      active = next;
      ++stats.recurrenceUpdates;
    }

    result[n] = outwardBinary64(chirpState[active]);
    const ComplexInterval oddStep = outwardBinary64(oddStepState[active]);
    if (!finiteOrdered(result[n]) || !finiteOrdered(oddStep)) {
      throw std::runtime_error("chirp recurrence produced a malformed interval");
    }
    const double width = std::max(
        {componentWidth(result[n].re), componentWidth(result[n].im),
         componentWidth(oddStep.re), componentWidth(oddStep.im)});
    if (!(width <= kMaximumChirpComponentWidth)) {
      throw std::runtime_error(
          "chirp recurrence exceeded its binary64 width ceiling");
    }
    const double mpfrWidth = std::max(
        {mpfrComponentWidth(chirpState[active].re, &scratch.productLo),
         mpfrComponentWidth(chirpState[active].im, &scratch.productLo),
         mpfrComponentWidth(oddStepState[active].re, &scratch.productLo),
         mpfrComponentWidth(oddStepState[active].im, &scratch.productLo)});
    stats.maximumMpfrComponentWidth =
        std::max(stats.maximumMpfrComponentWidth, mpfrWidth);
    stats.maximumBinary64ComponentWidth =
        std::max(stats.maximumBinary64ComponentWidth, width);
    if (trace != nullptr) {
      (*trace)[n] = {result[n], oddStep};
    }
  }
  if (generationStats != nullptr) *generationStats = stats;
  return result;
}

std::vector<ComplexInterval> chirp(std::uint32_t length, int sign) {
  return recurrenceChirp(length, sign);
}

int parseChirpSign(const char* text) {
  if (text != nullptr &&
      (std::strcmp(text, "1") == 0 || std::strcmp(text, "+1") == 0)) {
    return 1;
  }
  if (text != nullptr && std::strcmp(text, "-1") == 0) return -1;
  throw std::runtime_error("chirp sign must be -1 or +1");
}

void publishChirpStateDump(const std::string& path,
                           const std::vector<ChirpStateRecord>& states) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    output.write(
        reinterpret_cast<const char*>(states.data()),
        static_cast<std::streamsize>(
            states.size() * sizeof(ChirpStateRecord)));
    if (!output) {
      throw std::runtime_error("could not write chirp state dump");
    }
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish chirp state dump");
  }
}

int runChirpDump(const char* modeText, std::uint32_t length, int sign,
                 const char* outputPath) {
  const bool recurrence = std::strcmp(modeText, "recurrence") == 0;
  const bool conjugate = std::strcmp(modeText, "conjugate") == 0;
  const bool direct = std::strcmp(modeText, "direct") == 0;
  if (!recurrence && !conjugate && !direct) {
    throw std::runtime_error(
        "chirp dump mode must be recurrence, conjugate, or direct");
  }
  if (conjugate && sign != -1) {
    throw std::runtime_error(
        "conjugate chirp diagnostic constructs only sign -1");
  }
  if (length == 0U || length > da::kMaximumModulus) {
    throw std::runtime_error("chirp dump length is outside 1..400000");
  }

  std::vector<ComplexInterval> timed;
  ChirpGenerationStats timedStats;
  const auto start = std::chrono::steady_clock::now();
  if (recurrence) {
    timed = recurrenceChirp(length, sign, nullptr, &timedStats);
  } else if (conjugate) {
    timed = conjugateEnclosures(
        recurrenceChirp(length, +1, nullptr, &timedStats));
  } else {
    timed = directChirp(length, sign);
  }
  const auto stop = std::chrono::steady_clock::now();

  std::vector<ChirpStateRecord> states(length);
  ChirpGenerationStats traceStats;
  if (recurrence || conjugate) {
    std::vector<ChirpStateRecord> positiveStates;
    const auto traced = recurrenceChirp(
        length, conjugate ? +1 : sign,
        conjugate ? &positiveStates : &states, &traceStats);
    if (conjugate) {
      for (std::size_t index = 0U; index < positiveStates.size(); ++index) {
        states[index] = {
            conjugateEnclosure(positiveStates[index].chirp),
            conjugateEnclosure(positiveStates[index].oddStep),
        };
      }
    }
    const auto tracedOutput =
        conjugate ? conjugateEnclosures(traced) : traced;
    if (tracedOutput.size() != timed.size() ||
        std::memcmp(tracedOutput.data(), timed.data(),
                    timed.size() * sizeof(ComplexInterval)) != 0) {
      throw std::runtime_error(
          "repeated chirp construction was not byte deterministic");
    }
  } else {
    for (std::uint64_t n = 0U; n < length; ++n) {
      states[n] = {
          timed[n],
          unitRoot(oddStepPhaseNumerator(n, length), length, sign),
      };
    }
    traceStats.anchors = length;
    for (const auto& state : states) {
      const double width = std::max(
          {componentWidth(state.chirp.re), componentWidth(state.chirp.im),
           componentWidth(state.oddStep.re),
           componentWidth(state.oddStep.im)});
      traceStats.maximumBinary64ComponentWidth =
          std::max(traceStats.maximumBinary64ComponentWidth, width);
    }
  }
  publishChirpStateDump(outputPath, states);
  const auto digest = sparkinterval::sha256(
      states.data(), states.size() * sizeof(ChirpStateRecord));
  const auto elapsed = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start)
          .count());
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-chirp-periodic-anchor-v1\","
      "\"mode\":\"%s\",\"length\":%u,\"sign\":%d,"
      "\"precision_bits\":%ld,\"anchor_cadence\":%u,"
      "\"anchors\":%llu,\"recurrence_updates\":%llu,"
      "\"generation_nanoseconds\":%llu,"
      "\"maximum_internal_mpfr_component_width\":%.17g,"
      "\"maximum_binary64_component_width\":%.17g,"
      "\"maximum_binary64_component_width_ceiling\":%.17g,"
      "\"state_count\":%u,\"state_record_bytes\":%zu,"
      "\"state_sha256\":\"%s\"}\n",
      recurrence ? "recurrence" : (conjugate ? "conjugate" : "direct"),
      length, sign,
      static_cast<long>((recurrence || conjugate) ? kChirpPrecision : 320),
      kChirpAnchorCadence,
      static_cast<unsigned long long>(traceStats.anchors),
      static_cast<unsigned long long>(traceStats.recurrenceUpdates),
      static_cast<unsigned long long>(elapsed),
      traceStats.maximumMpfrComponentWidth,
      traceStats.maximumBinary64ComponentWidth,
      kMaximumChirpComponentWidth, length, sizeof(ChirpStateRecord),
      sparkinterval::lowercase_hex(digest).c_str());
  return 0;
}

void publishFftRootDump(
    const std::string& path,
    const std::vector<ComplexInterval>& roots) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    output.write(
        reinterpret_cast<const char*>(roots.data()),
        static_cast<std::streamsize>(
            roots.size() * sizeof(ComplexInterval)));
    if (!output) {
      throw std::runtime_error("could not write FFT-root dump");
    }
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish FFT-root dump");
  }
}

int runFftRootDump(
    const char* modeText, std::uint32_t length, int sign,
    const char* outputPath) {
  const bool recurrence = std::strcmp(modeText, "recurrence") == 0;
  const bool conjugate = std::strcmp(modeText, "conjugate") == 0;
  const bool direct = std::strcmp(modeText, "direct") == 0;
  if (!recurrence && !conjugate && !direct) {
    throw std::runtime_error(
        "FFT-root dump mode must be recurrence, conjugate, or direct");
  }
  if (conjugate && sign != -1) {
    throw std::runtime_error(
        "conjugate FFT-root diagnostic constructs only sign -1");
  }
  if (!sourceRootConvolution(length)) {
    throw std::runtime_error(
        "FFT-root dump length is outside the 19-entry source catalog");
  }

  FftRootGenerationStats stats;
  const auto start = std::chrono::steady_clock::now();
  std::vector<ComplexInterval> roots;
  if (recurrence) {
    roots = recurrenceFftRoots(length, sign, &stats);
  } else if (conjugate) {
    roots = conjugateEnclosures(
        recurrenceFftRoots(length, +1, &stats));
  } else {
    roots = directFftRoots(length, sign);
    stats.stages = integerLog2(length);
    stats.anchors = roots.size();
    for (const auto& root : roots) {
      stats.maximumBinary64ComponentWidth = std::max(
          stats.maximumBinary64ComponentWidth,
          std::max(
              componentWidth(root.re), componentWidth(root.im)));
    }
  }
  const auto stop = std::chrono::steady_clock::now();
  publishFftRootDump(outputPath, roots);
  const auto digest = sparkinterval::sha256(
      roots.data(), roots.size() * sizeof(ComplexInterval));
  const std::uint64_t elapsed = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          stop - start)
          .count());
  std::printf(
      "{\"algorithm\":"
      "\"platt-dirichlet-fft-root-periodic-anchor-v1\","
      "\"mode\":\"%s\",\"length\":%u,\"sign\":%d,"
      "\"precision_bits\":%ld,\"anchor_cadence\":%u,"
      "\"stages\":%llu,\"anchors\":%llu,"
      "\"recurrence_updates\":%llu,"
      "\"generation_nanoseconds\":%llu,"
      "\"maximum_internal_mpfr_component_width\":%.17g,"
      "\"maximum_binary64_component_width\":%.17g,"
      "\"maximum_binary64_component_width_ceiling\":%.17g,"
      "\"root_count\":%zu,\"root_record_bytes\":%zu,"
      "\"root_sha256\":\"%s\"}\n",
      recurrence ? "recurrence" : (conjugate ? "conjugate" : "direct"),
      length, sign,
      static_cast<long>((recurrence || conjugate) ? kFftRootPrecision : 320),
      kFftRootAnchorCadence,
      static_cast<unsigned long long>(stats.stages),
      static_cast<unsigned long long>(stats.anchors),
      static_cast<unsigned long long>(stats.recurrenceUpdates),
      static_cast<unsigned long long>(elapsed),
      stats.maximumMpfrComponentWidth,
      stats.maximumBinary64ComponentWidth,
      kMaximumFftRootComponentWidth, roots.size(),
      sizeof(ComplexInterval),
      sparkinterval::lowercase_hex(digest).c_str());
  return 0;
}

// The two radix-2 root arrays depend only on the convolution length.  There
// are exactly 19 possible lengths (4 through 2^20) in q <= 400000.  They are
// split from the order-specific chirp/kernel object below so an eviction of an
// order does not regenerate the same expensive roots.
class SharedRadix2Roots {
 public:
  explicit SharedRadix2Roots(std::uint32_t convolution)
      : convolution_(convolution) {
    if (!sourceRootConvolution(convolution_)) {
      throw std::runtime_error(
          "convolution is outside the fixed source root catalog");
    }
    try {
      const auto rootsInverse = recurrenceFftRoots(convolution_, +1);
      // The exact negative root is the complex conjugate of the positive
      // root.  Endpoint negation is exact in binary64, so derive the forward
      // boxes definitionally instead of invoking MPFR a second time.
      const auto rootsForward = conjugateEnclosures(rootsInverse);
      CUDA_CHECK(cudaMalloc(&dRootsForward_,
                            rootsForward.size() * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMalloc(&dRootsInverse_,
                            rootsInverse.size() * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMemcpy(dRootsForward_, rootsForward.data(),
                            rootsForward.size() * sizeof(ComplexInterval),
                            cudaMemcpyHostToDevice));
      CUDA_CHECK(cudaMemcpy(dRootsInverse_, rootsInverse.data(),
                            rootsInverse.size() * sizeof(ComplexInterval),
                            cudaMemcpyHostToDevice));
    } catch (...) {
      release();
      throw;
    }
  }

  SharedRadix2Roots(const SharedRadix2Roots&) = delete;
  SharedRadix2Roots& operator=(const SharedRadix2Roots&) = delete;

  ~SharedRadix2Roots() { release(); }

  static std::uint64_t retainedBytes(std::uint32_t convolution) {
    return 2ULL * (static_cast<std::uint64_t>(convolution) - 1ULL) *
           sizeof(ComplexInterval);
  }

  static std::uint64_t preparedEnclosures(std::uint32_t convolution) {
    return 2ULL * (static_cast<std::uint64_t>(convolution) - 1ULL);
  }

  std::uint32_t convolution() const { return convolution_; }
  ComplexInterval* forwardData() const { return dRootsForward_; }
  ComplexInterval* inverseData() const { return dRootsInverse_; }

 private:
  void release() noexcept {
    cudaFree(dRootsInverse_);
    dRootsInverse_ = nullptr;
    cudaFree(dRootsForward_);
    dRootsForward_ = nullptr;
  }

  std::uint32_t convolution_;
  ComplexInterval* dRootsForward_ = nullptr;
  ComplexInterval* dRootsInverse_ = nullptr;
};

struct RootPoolStats {
  std::uint64_t accesses = 0U;
  std::uint64_t hits = 0U;
  std::uint64_t misses = 0U;
  std::uint64_t retainedBytes = 0U;
  std::uint64_t preparedEnclosures = 0U;
};

class ImmutableRootPool {
 public:
  std::shared_ptr<SharedRadix2Roots> acquire(std::uint32_t convolution) {
    ++stats_.accesses;
    const auto found = entries_.find(convolution);
    if (found != entries_.end()) {
      ++stats_.hits;
      return found->second;
    }
    ++stats_.misses;
    auto roots = std::make_shared<SharedRadix2Roots>(convolution);
    stats_.retainedBytes += SharedRadix2Roots::retainedBytes(convolution);
    stats_.preparedEnclosures +=
        SharedRadix2Roots::preparedEnclosures(convolution);
    if (stats_.retainedBytes > kSourceRootPoolReservedBytes) {
      throw std::runtime_error("immutable root pool exceeded its reservation");
    }
    entries_.emplace(convolution, roots);
    return roots;
  }

  const RootPoolStats& stats() const { return stats_; }
  std::uint64_t retainedEntries() const { return entries_.size(); }

  static sparkinterval::Sha256Digest catalogDigest() {
    static constexpr char kDomain[] = "TGDAFF_ROOT_POOL_CATALOG_V1";
    sparkinterval::detail::Sha256 hasher;
    hasher.update(kDomain, sizeof(kDomain) - 1U);
    for (std::uint32_t convolution = kSourceRootFirstConvolution;
         convolution <= kSourceRootLastConvolution; convolution <<= 1U) {
      unsigned char encoded[4];
      for (unsigned int index = 0; index < 4U; ++index) {
        encoded[index] =
            static_cast<unsigned char>(convolution >> (8U * index));
      }
      hasher.update(encoded, sizeof(encoded));
    }
    return hasher.finish();
  }

 private:
  std::unordered_map<std::uint32_t, std::shared_ptr<SharedRadix2Roots>>
      entries_;
  RootPoolStats stats_;
};

// The chirp and transformed Bluestein kernel depend on the cyclic component
// order.  The radix-2 roots are shared by every order with the same
// convolution length.
class SharedDimensionData {
 public:
  explicit SharedDimensionData(std::uint32_t length)
      : SharedDimensionData(
            length, std::make_shared<SharedRadix2Roots>(
                        nextPowerOfTwo(2ULL * length - 1ULL))) {}

  SharedDimensionData(
      std::uint32_t length,
      std::shared_ptr<SharedRadix2Roots> roots)
      : length_(length),
        convolution_(nextPowerOfTwo(2ULL * length - 1ULL)),
        logConvolution_(integerLog2(convolution_)),
        roots_(std::move(roots)) {
    if (roots_ == nullptr || roots_->convolution() != convolution_) {
      throw std::runtime_error("shared radix-2 root identity differs");
    }
    ComplexInterval* dKernelNatural = nullptr;
    try {
      constexpr std::uint32_t kThreads = 256U;
      const auto chirpPlus = chirp(length_, +1);
      // Keep production aligned with the exact conjugation theorem: the
      // negative chirp is derived from the positive recurrence boxes.  The
      // independently generated negative recurrence remains a diagnostic.
      const auto chirpMinus = conjugateEnclosures(chirpPlus);
      std::vector<ComplexInterval> kernel(
          convolution_, ComplexInterval{{0.0, 0.0}, {0.0, 0.0}});
      kernel[0] = chirpMinus[0];
      for (std::uint32_t n = 1U; n < length_; ++n) {
        kernel[n] = chirpMinus[n];
        kernel[convolution_ - n] = chirpMinus[n];
      }
      CUDA_CHECK(
          cudaMalloc(&dChirp_, chirpPlus.size() * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMalloc(&dKernel_,
                            kernel.size() * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMalloc(&dKernelNatural,
                            kernel.size() * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMemcpy(dChirp_, chirpPlus.data(),
                            chirpPlus.size() * sizeof(ComplexInterval),
                            cudaMemcpyHostToDevice));
      CUDA_CHECK(cudaMemcpy(dKernelNatural, kernel.data(),
                            kernel.size() * sizeof(ComplexInterval),
                            cudaMemcpyHostToDevice));
      bitReverseCopy<<<blocksFor(convolution_), kThreads>>>(
          dKernelNatural, dKernel_, 1U, convolution_, logConvolution_);
      CUDA_CHECK(cudaGetLastError());
      launchFft(dKernel_, roots_->forwardData(), 1U, convolution_);
      CUDA_CHECK(cudaDeviceSynchronize());
      CUDA_CHECK(cudaFree(dKernelNatural));
      dKernelNatural = nullptr;
    } catch (...) {
      cudaFree(dKernelNatural);
      release();
      throw;
    }
  }

  SharedDimensionData(const SharedDimensionData&) = delete;
  SharedDimensionData& operator=(const SharedDimensionData&) = delete;

  ~SharedDimensionData() { release(); }

  static std::uint64_t retainedBytes(std::uint32_t length) {
    const std::uint64_t convolution =
        nextPowerOfTwo(2ULL * length - 1ULL);
    return (static_cast<std::uint64_t>(length) + convolution) *
           sizeof(ComplexInterval);
  }

  static std::uint64_t preparedEnclosures(std::uint32_t length) {
    return 2ULL * static_cast<std::uint64_t>(length);
  }

  std::uint32_t length() const { return length_; }
  std::uint32_t convolution() const { return convolution_; }
  std::uint32_t logConvolution() const { return logConvolution_; }
  ComplexInterval* chirpData() const { return dChirp_; }
  ComplexInterval* kernelData() const { return dKernel_; }
  ComplexInterval* rootsForwardData() const { return roots_->forwardData(); }
  ComplexInterval* rootsInverseData() const { return roots_->inverseData(); }

 private:
  void release() noexcept {
    cudaFree(dKernel_);
    dKernel_ = nullptr;
    cudaFree(dChirp_);
    dChirp_ = nullptr;
  }

  std::uint32_t length_;
  std::uint32_t convolution_;
  std::uint32_t logConvolution_;
  std::shared_ptr<SharedRadix2Roots> roots_;
  ComplexInterval* dChirp_ = nullptr;
  ComplexInterval* dKernel_ = nullptr;
};

struct OrderCacheStats {
  std::uint64_t accesses = 0U;
  std::uint64_t hits = 0U;
  std::uint64_t misses = 0U;
  std::uint64_t evictions = 0U;
  std::uint64_t uncachedMisses = 0U;
  std::uint64_t retainedBytes = 0U;
  std::uint64_t peakRetainedBytes = 0U;
  std::uint64_t preparedEnclosures = 0U;
  std::uint64_t peakTotalRetainedBytes = 0U;
};

// The total multi-q cache budget is exactly 512 MiB.  The complete immutable
// 19-length root catalog is reserved first (134,216,256 bytes), leaving
// 402,654,656 bytes for this order-specific LRU.  Roots are instantiated
// lazily but never evicted; reserving their full source-domain size up front
// prevents early order entries from borrowing memory needed by a later root.
class TwiddlePlanCache {
 public:
  TwiddlePlanCache() {
    static constexpr char kKeyDomain[] = "TGDAFF_SPLIT_CACHE_KEY_V2";
    keyHasher_.update(kKeyDomain, sizeof(kKeyDomain) - 1U);
  }

  std::shared_ptr<SharedDimensionData> acquire(std::uint32_t length) {
    ++stats_.accesses;
    const std::uint32_t convolution =
        nextPowerOfTwo(2ULL * length - 1ULL);
    unsigned char key[8];
    for (unsigned int index = 0; index < 4U; ++index) {
      key[index] = static_cast<unsigned char>(length >> (8U * index));
      key[4U + index] =
          static_cast<unsigned char>(convolution >> (8U * index));
    }
    keyHasher_.update(key, sizeof(key));

    const auto found = entries_.find(length);
    if (found != entries_.end()) {
      ++stats_.hits;
      lru_.splice(lru_.begin(), lru_, found->second.position);
      updateTotalPeak();
      return found->second.data;
    }
    ++stats_.misses;
    stats_.preparedEnclosures +=
        SharedDimensionData::preparedEnclosures(length);
    const std::uint64_t bytes = SharedDimensionData::retainedBytes(length);
    const auto roots = roots_.acquire(convolution);
    updateTotalPeak();
    const bool retain = bytes <= kMultiQOrderCacheBytes && makeRoom(bytes);
    auto data = std::make_shared<SharedDimensionData>(length, roots);
    if (!retain) {
      ++stats_.uncachedMisses;
      updateTotalPeak();
      return data;
    }
    lru_.push_front(length);
    entries_.emplace(length, Entry{data, lru_.begin(), bytes});
    stats_.retainedBytes += bytes;
    stats_.peakRetainedBytes =
        std::max(stats_.peakRetainedBytes, stats_.retainedBytes);
    updateTotalPeak();
    return data;
  }

  const OrderCacheStats& stats() const { return stats_; }
  std::uint64_t retainedEntries() const { return entries_.size(); }
  const RootPoolStats& rootStats() const { return roots_.stats(); }
  std::uint64_t retainedRootEntries() const {
    return roots_.retainedEntries();
  }
  sparkinterval::Sha256Digest finishKeyDigest() { return keyHasher_.finish(); }
  sparkinterval::Sha256Digest rootCatalogDigest() const {
    return ImmutableRootPool::catalogDigest();
  }

 private:
  struct Entry {
    std::shared_ptr<SharedDimensionData> data;
    std::list<std::uint32_t>::iterator position;
    std::uint64_t bytes;
  };

  bool makeRoom(std::uint64_t bytes) {
    while (stats_.retainedBytes > kMultiQOrderCacheBytes - bytes) {
      auto candidate = lru_.end();
      bool found = false;
      while (candidate != lru_.begin()) {
        --candidate;
        const auto entry = entries_.find(*candidate);
        if (entry == entries_.end()) {
          throw std::runtime_error("twiddle cache LRU identity changed");
        }
        if (entry->second.data.use_count() == 1) {
          found = true;
          break;
        }
      }
      if (!found) return false;
      const auto entry = entries_.find(*candidate);
      stats_.retainedBytes -= entry->second.bytes;
      entries_.erase(entry);
      lru_.erase(candidate);
      ++stats_.evictions;
    }
    return true;
  }

  void updateTotalPeak() {
    const std::uint64_t total =
        stats_.retainedBytes + roots_.stats().retainedBytes;
    if (total > kMultiQTotalCacheBytes) {
      throw std::runtime_error("split cache exceeded the total reservation");
    }
    stats_.peakTotalRetainedBytes =
        std::max(stats_.peakTotalRetainedBytes, total);
  }

  ImmutableRootPool roots_;
  OrderCacheStats stats_;
  std::list<std::uint32_t> lru_;
  std::unordered_map<std::uint32_t, Entry> entries_;
  sparkinterval::detail::Sha256 keyHasher_;
};

class DimensionPlan {
 public:
  DimensionPlan(std::uint32_t length, std::uint64_t stride,
                std::uint64_t maximumTotal, TwiddlePlanCache* cache)
      : shared_(cache == nullptr
                    ? std::make_shared<SharedDimensionData>(length)
                    : cache->acquire(length)),
        stride_(stride),
        maximumWorkspace_(maximumTotal / length *
                          shared_->convolution()) {
    try {
      CUDA_CHECK(cudaMalloc(&dWorkspace_,
                            maximumWorkspace_ * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMalloc(&dScratch_,
                            maximumWorkspace_ * sizeof(ComplexInterval)));
    } catch (...) {
      release();
      throw;
    }
  }

  DimensionPlan(const DimensionPlan&) = delete;
  DimensionPlan& operator=(const DimensionPlan&) = delete;

  ~DimensionPlan() { release(); }

  void execute(ComplexInterval* input, ComplexInterval* output,
               std::uint64_t total) const {
    constexpr std::uint32_t kThreads = 256U;
    const std::uint32_t length = shared_->length();
    const std::uint32_t convolution = shared_->convolution();
    const std::uint64_t lines = total / length;
    const std::uint64_t workspaceCount = lines * convolution;
    if (workspaceCount > maximumWorkspace_) {
      throw std::runtime_error("batch exceeds prepared transform capacity");
    }
    initializeA<<<blocksFor(workspaceCount), kThreads>>>(
        input, dWorkspace_, shared_->chirpData(), total, length, convolution,
        stride_, shared_->logConvolution());
    CUDA_CHECK(cudaGetLastError());
    launchFft(dWorkspace_, shared_->rootsForwardData(), lines, convolution);
    pointwiseBitReverseCopy<<<blocksFor(workspaceCount), kThreads>>>(
        dWorkspace_, dScratch_, shared_->kernelData(), lines, convolution,
        shared_->logConvolution());
    CUDA_CHECK(cudaGetLastError());
    launchFft(dScratch_, shared_->rootsInverseData(), lines, convolution);
    gatherOutput<<<blocksFor(total), kThreads>>>(
        dScratch_, output, shared_->chirpData(), total, length, convolution,
        stride_, std::ldexp(1.0, -static_cast<int>(
            shared_->logConvolution())));
    CUDA_CHECK(cudaGetLastError());
  }

 private:
  void release() noexcept {
    cudaFree(dScratch_);
    dScratch_ = nullptr;
    cudaFree(dWorkspace_);
    dWorkspace_ = nullptr;
  }

  std::shared_ptr<SharedDimensionData> shared_;
  std::uint64_t stride_;
  std::uint64_t maximumWorkspace_;
  ComplexInterval* dWorkspace_ = nullptr;
  ComplexInterval* dScratch_ = nullptr;
};

struct DeviceTransformResult {
  ComplexInterval* values = nullptr;
  std::uint64_t value_count = 0U;
  std::uint64_t elapsed_nanoseconds = 0U;
};

class TransformPlan {
 public:
  TransformPlan(const std::vector<std::uint32_t>& orders,
                std::uint64_t maximumTotal,
                TwiddlePlanCache* cache = nullptr)
      : maximumTotal_(maximumTotal) {
    try {
      CUDA_CHECK(cudaMalloc(&dA_, maximumTotal * sizeof(ComplexInterval)));
      CUDA_CHECK(cudaMalloc(&dB_, maximumTotal * sizeof(ComplexInterval)));
      std::uint64_t stride = 1U;
      for (const auto length : orders) {
        dimensions_.emplace_back(std::make_unique<DimensionPlan>(
            length, stride, maximumTotal, cache));
        stride *= length;
      }
      CUDA_CHECK(cudaEventCreate(&startEvent_));
      CUDA_CHECK(cudaEventCreate(&stopEvent_));
    } catch (...) {
      release();
      throw;
    }
  }

  ~TransformPlan() { release(); }

  ComplexInterval* deviceInputData() const { return dA_; }
  std::uint64_t maximumValueCount() const { return maximumTotal_; }

  // Queue every transform dimension in the current CUDA stream and return
  // the still-resident output pointer without a device/host synchronization.
  // The source composer writes directly to deviceInputData(), calls this
  // method, and queues the completed-L reducer on the returned pointer.  A
  // later compact-state/checkpoint transfer is the synchronization boundary.
  DeviceTransformResult enqueueLoadedDevice(std::uint64_t total) const {
    if (total == 0U || total > maximumTotal_) {
      throw std::runtime_error("batch exceeds prepared value capacity");
    }
    ComplexInterval* current = dA_;
    ComplexInterval* spare = dB_;
    for (const auto& dimension : dimensions_) {
      dimension->execute(current, spare, total);
      std::swap(current, spare);
    }
    return {current, total, 0U};
  }

  // KAT/diagnostic wrapper.  Production does not synchronize one event pair
  // for every <=64-row frame merely to obtain a timing number.
  DeviceTransformResult executeLoadedDevice(std::uint64_t total) const {
    CUDA_CHECK(cudaEventRecord(startEvent_));
    DeviceTransformResult result = enqueueLoadedDevice(total);
    CUDA_CHECK(cudaEventRecord(stopEvent_));
    CUDA_CHECK(cudaEventSynchronize(stopEvent_));
    float elapsedMilliseconds = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(
        &elapsedMilliseconds, startEvent_, stopEvent_));
    result.elapsed_nanoseconds = static_cast<std::uint64_t>(
        static_cast<double>(elapsedMilliseconds) * 1.0e6);
    return result;
  }

  DeviceTransformResult executeDevice(
      const std::vector<ComplexInterval>& values) const {
    if (values.empty() || values.size() > maximumTotal_) {
      throw std::runtime_error("batch exceeds prepared value capacity");
    }
    CUDA_CHECK(cudaMemcpy(
        dA_, values.data(), values.size() * sizeof(ComplexInterval),
        cudaMemcpyHostToDevice));
    return executeLoadedDevice(values.size());
  }

  DeviceTransformResult executeDeviceToDevice(
      const ComplexInterval* values, std::uint64_t total) const {
    if (values == nullptr || total == 0U || total > maximumTotal_) {
      throw std::runtime_error(
          "device transform input is empty or exceeds capacity");
    }
    if (values != dA_) {
      CUDA_CHECK(cudaMemcpy(
          dA_, values, total * sizeof(ComplexInterval),
          cudaMemcpyDeviceToDevice));
    }
    return executeLoadedDevice(total);
  }

  DeviceTransformResult enqueueDeviceToDevice(
      const ComplexInterval* values, std::uint64_t total) const {
    if (values == nullptr || total == 0U || total > maximumTotal_) {
      throw std::runtime_error(
          "device transform input is empty or exceeds capacity");
    }
    if (values != dA_) {
      CUDA_CHECK(cudaMemcpyAsync(
          dA_, values, total * sizeof(ComplexInterval),
          cudaMemcpyDeviceToDevice));
    }
    return enqueueLoadedDevice(total);
  }

  std::uint64_t execute(std::vector<ComplexInterval>* values) const {
    if (values == nullptr) {
      throw std::runtime_error("host-download transform target is null");
    }
    const auto result = executeDevice(*values);
    CUDA_CHECK(cudaMemcpy(
        values->data(), result.values,
        result.value_count * sizeof(ComplexInterval),
        cudaMemcpyDeviceToHost));
    return result.elapsed_nanoseconds;
  }

 private:
  void release() noexcept {
    dimensions_.clear();
    if (stopEvent_ != nullptr) cudaEventDestroy(stopEvent_);
    stopEvent_ = nullptr;
    if (startEvent_ != nullptr) cudaEventDestroy(startEvent_);
    startEvent_ = nullptr;
    cudaFree(dB_);
    dB_ = nullptr;
    cudaFree(dA_);
    dA_ = nullptr;
  }

  std::uint64_t maximumTotal_;
  mutable ComplexInterval* dA_ = nullptr;
  mutable ComplexInterval* dB_ = nullptr;
  mutable cudaEvent_t startEvent_ = nullptr;
  mutable cudaEvent_t stopEvent_ = nullptr;
  std::vector<std::unique_ptr<DimensionPlan>> dimensions_;
};

template <typename T>
T readObject(std::istream& input, const char* label) {
  T object{};
  input.read(reinterpret_cast<char*>(&object), sizeof(object));
  if (!input) throw std::runtime_error(std::string("truncated ") + label);
  return object;
}

struct LoadedInput {
  da::InputHeader header{};
  std::vector<std::uint32_t> orders;
  std::vector<ComplexInterval> values;
  std::uint64_t butterflies = 0U;
};

void validateInputHeader(LoadedInput* loaded, const std::string& label) {
  const auto& header = loaded->header;
  if (std::memcmp(header.magic, da::kInputMagic, 8) != 0 ||
      header.version != da::kFormatVersion || header.reserved0 != 0U ||
      header.batch_count == 0U || header.t_denominator == 0U ||
      header.first_t_numerator < 0 || header.t_step_numerator == 0U) {
    throw std::runtime_error("invalid input header in " + label);
  }
  loaded->orders = canonicalOrders(header.q);
  const std::uint64_t groupOrder = orderProduct(loaded->orders);
  const std::uint64_t valueCount = groupOrder * header.batch_count;
  if (header.component_count != loaded->orders.size() ||
      header.group_order != groupOrder || header.value_count != valueCount) {
    throw std::runtime_error("input group identity does not match q in " +
                             label);
  }
  for (const auto length : loaded->orders) {
    const std::uint64_t lines = valueCount / length;
    const std::uint32_t convolution = nextPowerOfTwo(2ULL * length - 1ULL);
    loaded->butterflies += (1ULL + 2ULL * lines) * (convolution / 2ULL) *
                           integerLog2(convolution);
  }
}

// Read one self-delimiting TGDAFFI1 frame.  A clean EOF before the first
// header byte terminates a persistent stream; any partial header/value is a
// hard failure.  No frame boundary is inferred from EOF.
bool readInputFrame(std::istream& input, const std::string& label,
                    LoadedInput* loaded) {
  input.read(reinterpret_cast<char*>(&loaded->header),
             sizeof(loaded->header));
  if (!input) {
    if (input.eof() && input.gcount() == 0) return false;
    throw std::runtime_error("truncated input header in " + label);
  }
  validateInputHeader(loaded, label);
  loaded->values.resize(loaded->header.value_count);
  input.read(reinterpret_cast<char*>(loaded->values.data()),
             static_cast<std::streamsize>(loaded->values.size() *
                                          sizeof(loaded->values[0])));
  if (!input) throw std::runtime_error("truncated input values in " + label);
  if (!std::all_of(loaded->values.begin(), loaded->values.end(), finiteOrdered)) {
    throw std::runtime_error("input contains malformed interval in " + label);
  }
  return true;
}

LoadedInput loadInput(const std::string& path, bool valuesRequired = true) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("could not open input " + path);
  LoadedInput loaded;
  if (!valuesRequired) {
    loaded.header = readObject<da::InputHeader>(input, "header");
    validateInputHeader(&loaded, path);
    return loaded;
  }
  if (!readInputFrame(input, path, &loaded)) {
    throw std::runtime_error("empty input " + path);
  }
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing input bytes in " + path);
  }
  return loaded;
}

da::OutputHeader makeOutputHeader(const LoadedInput& input,
                                  std::uint64_t elapsed) {
  da::OutputHeader output{};
  std::memcpy(output.magic, da::kOutputMagic, 8);
  output.version = da::kFormatVersion;
  output.q = input.header.q;
  output.component_count = input.header.component_count;
  output.batch_count = input.header.batch_count;
  output.group_order = input.header.group_order;
  output.value_count = input.header.value_count;
  output.radix2_butterflies = input.butterflies;
  output.elapsed_nanoseconds = elapsed;
  return output;
}

void writeAtomically(const std::string& path, const da::OutputHeader& header,
                     const std::vector<ComplexInterval>& values) {
  if (header.value_count != values.size()) {
    throw std::runtime_error(
        "output header value count differs from payload");
  }
  if (!std::all_of(values.begin(), values.end(), finiteOrdered)) {
    throw std::runtime_error(
        "refusing to publish malformed transform interval");
  }
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("could not create output");
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    output.write(reinterpret_cast<const char*>(values.data()),
                 static_cast<std::streamsize>(values.size() * sizeof(values[0])));
    if (!output) throw std::runtime_error("could not write output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish output: " + error.message());
  }
}

int runMaximumOrderImpulseQualification(
    const char* outputPath, std::uint32_t device,
    std::uint32_t maximumSeconds) {
  if (outputPath == nullptr || *outputPath == '\0') {
    throw std::runtime_error("maximum-order qualification output is empty");
  }
  if (maximumSeconds == 0U || maximumSeconds > 3600U) {
    throw std::runtime_error(
        "maximum-order qualification timeout is outside 1..3600 seconds");
  }
  const std::vector<std::uint32_t> orders =
      canonicalOrders(kMaximumOrderImpulseQ);
  if (orders.size() != 1U ||
      orders[0] != kMaximumOrderImpulseLength ||
      nextPowerOfTwo(2ULL * orders[0] - 1ULL) !=
          kMaximumOrderImpulseConvolution ||
      integerLog2(kMaximumOrderImpulseConvolution) !=
          kMaximumOrderImpulseLogConvolution) {
    throw std::runtime_error(
        "maximum-order qualification identity changed");
  }

  const auto wallStart = std::chrono::steady_clock::now();
  selectCudaDevice(device);
  CUDA_CHECK(cudaFree(nullptr));
  std::size_t freeDeviceBytes = 0U;
  std::size_t totalDeviceBytes = 0U;
  CUDA_CHECK(cudaMemGetInfo(&freeDeviceBytes, &totalDeviceBytes));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(
      &properties, static_cast<int>(device)));
  if (kMaximumOrderImpulseRequiredDeviceBytes > freeDeviceBytes ||
      kMaximumOrderImpulseDeviceHeadroomBytes >
          freeDeviceBytes - kMaximumOrderImpulseRequiredDeviceBytes) {
    throw std::runtime_error(
        "maximum-order qualification lacks guarded CUDA memory");
  }

  std::vector<ComplexInterval> values(
      kMaximumOrderImpulseLength,
      ComplexInterval{{0.0, 0.0}, {0.0, 0.0}});
  values[0] = {{1.0, 1.0}, {0.0, 0.0}};
  const auto preparationStart = std::chrono::steady_clock::now();
  const TransformPlan plan(orders, kMaximumOrderImpulseLength);
  const auto preparationStop = std::chrono::steady_clock::now();
  const std::uint64_t preparationNanoseconds =
      static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              preparationStop - preparationStart)
              .count());
  const std::uint64_t transformNanoseconds = plan.execute(&values);

  const auto validationStart = std::chrono::steady_clock::now();
  double maximumComponentWidth = 0.0;
  for (std::size_t index = 0U; index < values.size(); ++index) {
    const auto& value = values[index];
    if (!finiteOrdered(value)) {
      throw std::runtime_error(
          "maximum-order impulse produced malformed interval at " +
          std::to_string(index));
    }
    if (!(value.re.lo <= 1.0 && 1.0 <= value.re.hi &&
          value.im.lo <= 0.0 && 0.0 <= value.im.hi)) {
      throw std::runtime_error(
          "maximum-order impulse identity missed at output " +
          std::to_string(index));
    }
    const double width = std::max(
        componentWidth(value.re), componentWidth(value.im));
    if (!std::isfinite(width) || width > kMaximumOrderImpulseWidth) {
      throw std::runtime_error(
          "maximum-order impulse exceeded its usefulness width at output " +
          std::to_string(index));
    }
    maximumComponentWidth = std::max(maximumComponentWidth, width);
  }
  const auto validationStop = std::chrono::steady_clock::now();
  const std::uint64_t validationNanoseconds =
      static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              validationStop - validationStart)
              .count());
  const std::uint64_t computeValidationNanoseconds =
      static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              validationStop - wallStart)
              .count());
  if (computeValidationNanoseconds >
      static_cast<std::uint64_t>(maximumSeconds) * 1000000000ULL) {
    throw std::runtime_error(
        "maximum-order qualification exceeded its runtime guard");
  }

  da::OutputHeader header{};
  std::memcpy(header.magic, da::kOutputMagic, 8);
  header.version = da::kFormatVersion;
  header.q = kMaximumOrderImpulseQ;
  header.component_count = 1U;
  header.batch_count = 1U;
  header.group_order = kMaximumOrderImpulseLength;
  header.value_count = kMaximumOrderImpulseLength;
  header.radix2_butterflies = kMaximumOrderImpulseButterflies;
  header.elapsed_nanoseconds = transformNanoseconds;
  writeAtomically(outputPath, header, values);
  const auto digest = sparkinterval::sha256(
      values.data(), values.size() * sizeof(ComplexInterval));

  std::printf(
      "{\"algorithm\":"
      "\"platt-dirichlet-allchars-max-order-impulse-qualification-v1\","
      "\"q\":%u,\"order\":%u,\"convolution\":%u,"
      "\"log_convolution\":%u,\"value_count\":%u,"
      "\"checked_output_count\":%u,\"radix2_butterflies\":%llu,"
      "\"device\":%u,\"device_compute_major\":%d,"
      "\"device_compute_minor\":%d,"
      "\"required_device_bytes\":%llu,"
      "\"free_device_bytes_before\":%zu,"
      "\"total_device_bytes\":%zu,\"device_headroom_bytes\":%llu,"
      "\"maximum_seconds\":%u,\"preparation_nanoseconds\":%llu,"
      "\"transform_nanoseconds\":%llu,"
      "\"validation_nanoseconds\":%llu,"
      "\"compute_validation_nanoseconds\":%llu,"
      "\"maximum_component_width\":%.17g,"
      "\"maximum_component_width_ceiling\":%.17g,"
      "\"output_payload_sha256\":\"%s\"}\n",
      kMaximumOrderImpulseQ, kMaximumOrderImpulseLength,
      kMaximumOrderImpulseConvolution,
      kMaximumOrderImpulseLogConvolution,
      kMaximumOrderImpulseLength, kMaximumOrderImpulseLength,
      static_cast<unsigned long long>(
          kMaximumOrderImpulseButterflies),
      device, properties.major, properties.minor,
      static_cast<unsigned long long>(
          kMaximumOrderImpulseRequiredDeviceBytes),
      freeDeviceBytes, totalDeviceBytes,
      static_cast<unsigned long long>(
          kMaximumOrderImpulseDeviceHeadroomBytes),
      maximumSeconds,
      static_cast<unsigned long long>(preparationNanoseconds),
      static_cast<unsigned long long>(transformNanoseconds),
      static_cast<unsigned long long>(validationNanoseconds),
      static_cast<unsigned long long>(computeValidationNanoseconds),
      maximumComponentWidth, kMaximumOrderImpulseWidth,
      sparkinterval::lowercase_hex(digest).c_str());
  return 0;
}

// The delta-at-zero KAT above reaches every allocation and FFT stage, but a
// coherent root-table/indexing error can cancel because the DFT of delta_0 is
// constant.  Delta_1 has the nonconstant exact transform
//
//   X[k] = exp(2*pi*i*k/N),
//
// so this separate opt-in qualification detects high-stage sign, index, and
// layout mistakes.  The producer validates against its retained 320-bit direct
// root path; reference/tg_dirichlet_allchars_mpfr.cpp independently repeats
// the semantic check with separately implemented MPFR arithmetic.
int runMaximumOrderDeltaOneQualification(
    const char* outputPath, std::uint32_t device,
    std::uint32_t maximumSeconds) {
  if (outputPath == nullptr || *outputPath == '\0') {
    throw std::runtime_error(
        "maximum-order delta-one qualification output is empty");
  }
  if (maximumSeconds == 0U || maximumSeconds > 3600U) {
    throw std::runtime_error(
        "maximum-order delta-one qualification timeout is outside "
        "1..3600 seconds");
  }
  const std::vector<std::uint32_t> orders =
      canonicalOrders(kMaximumOrderImpulseQ);
  if (orders.size() != 1U ||
      orders[0] != kMaximumOrderImpulseLength ||
      nextPowerOfTwo(2ULL * orders[0] - 1ULL) !=
          kMaximumOrderImpulseConvolution ||
      integerLog2(kMaximumOrderImpulseConvolution) !=
          kMaximumOrderImpulseLogConvolution) {
    throw std::runtime_error(
        "maximum-order delta-one qualification identity changed");
  }

  const auto wallStart = std::chrono::steady_clock::now();
  selectCudaDevice(device);
  CUDA_CHECK(cudaFree(nullptr));
  std::size_t freeDeviceBytes = 0U;
  std::size_t totalDeviceBytes = 0U;
  CUDA_CHECK(cudaMemGetInfo(&freeDeviceBytes, &totalDeviceBytes));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(
      &properties, static_cast<int>(device)));
  if (kMaximumOrderImpulseRequiredDeviceBytes > freeDeviceBytes ||
      kMaximumOrderImpulseDeviceHeadroomBytes >
          freeDeviceBytes - kMaximumOrderImpulseRequiredDeviceBytes) {
    throw std::runtime_error(
        "maximum-order delta-one qualification lacks guarded CUDA memory");
  }

  std::vector<ComplexInterval> values(
      kMaximumOrderImpulseLength,
      ComplexInterval{{0.0, 0.0}, {0.0, 0.0}});
  values[1] = {{1.0, 1.0}, {0.0, 0.0}};
  const auto preparationStart = std::chrono::steady_clock::now();
  const TransformPlan plan(orders, kMaximumOrderImpulseLength);
  const auto preparationStop = std::chrono::steady_clock::now();
  const std::uint64_t preparationNanoseconds =
      static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              preparationStop - preparationStart)
              .count());
  const std::uint64_t transformNanoseconds = plan.execute(&values);

  const auto validationStart = std::chrono::steady_clock::now();
  double maximumComponentWidth = 0.0;
  for (std::size_t index = 0U; index < values.size(); ++index) {
    const auto& value = values[index];
    if (!finiteOrdered(value)) {
      throw std::runtime_error(
          "maximum-order delta-one produced malformed interval at " +
          std::to_string(index));
    }
    const ComplexInterval expected =
        unitRoot(2ULL * index, kMaximumOrderImpulseLength, +1);
    if (!(value.re.lo <= expected.re.lo &&
          expected.re.hi <= value.re.hi &&
          value.im.lo <= expected.im.lo &&
          expected.im.hi <= value.im.hi)) {
      throw std::runtime_error(
          "maximum-order delta-one missed its direct root at output " +
          std::to_string(index));
    }
    const double width = std::max(
        componentWidth(value.re), componentWidth(value.im));
    if (!std::isfinite(width) || width > kMaximumOrderImpulseWidth) {
      throw std::runtime_error(
          "maximum-order delta-one exceeded its usefulness width at output " +
          std::to_string(index));
    }
    maximumComponentWidth = std::max(maximumComponentWidth, width);
  }
  const auto validationStop = std::chrono::steady_clock::now();
  const std::uint64_t validationNanoseconds =
      static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              validationStop - validationStart)
              .count());
  const std::uint64_t computeValidationNanoseconds =
      static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              validationStop - wallStart)
              .count());
  if (computeValidationNanoseconds >
      static_cast<std::uint64_t>(maximumSeconds) * 1000000000ULL) {
    throw std::runtime_error(
        "maximum-order delta-one qualification exceeded its runtime guard");
  }

  da::OutputHeader header{};
  std::memcpy(header.magic, da::kOutputMagic, 8);
  header.version = da::kFormatVersion;
  header.q = kMaximumOrderImpulseQ;
  header.component_count = 1U;
  header.batch_count = 1U;
  header.group_order = kMaximumOrderImpulseLength;
  header.value_count = kMaximumOrderImpulseLength;
  header.radix2_butterflies = kMaximumOrderImpulseButterflies;
  header.elapsed_nanoseconds = transformNanoseconds;
  writeAtomically(outputPath, header, values);
  const auto payloadDigest = sparkinterval::sha256(
      values.data(), values.size() * sizeof(ComplexInterval));
  sparkinterval::detail::Sha256 artifactHasher;
  artifactHasher.update(&header, sizeof(header));
  artifactHasher.update(
      values.data(), values.size() * sizeof(ComplexInterval));
  const auto artifactDigest = artifactHasher.finish();

  std::printf(
      "{\"algorithm\":"
      "\"platt-dirichlet-allchars-max-order-delta-one-qualification-v1\","
      "\"semantic\":\"positive_dft_delta_one\","
      "\"q\":%u,\"order\":%u,\"convolution\":%u,"
      "\"log_convolution\":%u,\"input_nonzero_index\":1,"
      "\"value_count\":%u,\"checked_output_count\":%u,"
      "\"semantic_reference_precision_bits\":320,"
      "\"radix2_butterflies\":%llu,"
      "\"device\":%u,\"device_compute_major\":%d,"
      "\"device_compute_minor\":%d,"
      "\"required_device_bytes\":%llu,"
      "\"free_device_bytes_before\":%zu,"
      "\"total_device_bytes\":%zu,\"device_headroom_bytes\":%llu,"
      "\"maximum_seconds\":%u,\"preparation_nanoseconds\":%llu,"
      "\"transform_nanoseconds\":%llu,"
      "\"validation_nanoseconds\":%llu,"
      "\"compute_validation_nanoseconds\":%llu,"
      "\"maximum_component_width\":%.17g,"
      "\"maximum_component_width_ceiling\":%.17g,"
      "\"output_payload_sha256\":\"%s\","
      "\"output_artifact_sha256\":\"%s\"}\n",
      kMaximumOrderImpulseQ, kMaximumOrderImpulseLength,
      kMaximumOrderImpulseConvolution,
      kMaximumOrderImpulseLogConvolution,
      kMaximumOrderImpulseLength, kMaximumOrderImpulseLength,
      static_cast<unsigned long long>(
          kMaximumOrderImpulseButterflies),
      device, properties.major, properties.minor,
      static_cast<unsigned long long>(
          kMaximumOrderImpulseRequiredDeviceBytes),
      freeDeviceBytes, totalDeviceBytes,
      static_cast<unsigned long long>(
          kMaximumOrderImpulseDeviceHeadroomBytes),
      maximumSeconds,
      static_cast<unsigned long long>(preparationNanoseconds),
      static_cast<unsigned long long>(transformNanoseconds),
      static_cast<unsigned long long>(validationNanoseconds),
      static_cast<unsigned long long>(computeValidationNanoseconds),
      maximumComponentWidth, kMaximumOrderImpulseWidth,
      sparkinterval::lowercase_hex(payloadDigest).c_str(),
      sparkinterval::lowercase_hex(artifactDigest).c_str());
  return 0;
}

struct StreamEntry {
  std::string input;
  std::string receipt;
};

std::vector<StreamEntry> readStreamManifest(const std::string& path) {
  std::ifstream manifest(path);
  if (!manifest) throw std::runtime_error("could not open stream manifest");
  std::string line;
  if (!std::getline(manifest, line) || line != "TGDAFF_STREAM_V1") {
    throw std::runtime_error("invalid stream manifest header");
  }
  const std::filesystem::path base =
      std::filesystem::absolute(std::filesystem::path(path)).parent_path();
  std::vector<StreamEntry> entries;
  while (std::getline(manifest, line)) {
    if (line.empty()) continue;
    const std::size_t separator = line.find('\t');
    if (separator == std::string::npos || line.find('\t', separator + 1U) !=
                                              std::string::npos) {
      throw std::runtime_error("stream manifest line must have two TSV fields");
    }
    std::filesystem::path input = line.substr(0, separator);
    std::filesystem::path receipt = line.substr(separator + 1U);
    if (input.empty() || receipt.empty()) {
      throw std::runtime_error("empty stream manifest path");
    }
    if (input.is_relative()) input = base / input;
    if (receipt.is_relative()) receipt = base / receipt;
    entries.push_back({input.lexically_normal().string(),
                       receipt.lexically_normal().string()});
  }
  if (entries.empty()) throw std::runtime_error("empty stream manifest");
  return entries;
}

sparkinterval::Sha256Digest hashFile(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("consumer did not create receipt");
  sparkinterval::detail::Sha256 hasher;
  std::array<char, 1U << 16U> buffer{};
  std::uint64_t size = 0U;
  while (input) {
    input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    const std::streamsize count = input.gcount();
    if (count > 0) {
      hasher.update(buffer.data(), static_cast<std::size_t>(count));
      size += static_cast<std::uint64_t>(count);
    }
  }
  if (size == 0U) throw std::runtime_error("consumer receipt is empty");
  return hasher.finish();
}

constexpr char kRootArtifactMagic[8] =
    {'T', 'G', 'D', 'R', 'N', 'R', 'O', '1'};
constexpr char kFactorFixtureMagic[8] =
    {'T', 'G', 'D', 'C', 'F', 'C', 'T', '1'};

struct RootArtifactHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t component_count;
  std::uint32_t record_size;
  std::uint64_t record_count;
  sparkinterval::Sha256Digest additive_input_sha256;
  sparkinterval::Sha256Digest transform_output_sha256;
};

// Qualification-only direct factor fixture.  Source production replaces this
// per-frame table with the shared parity-gamma table and certified
// conductor-phase checkpoint recurrence.
struct FactorFixtureHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t sample_count;
  std::uint32_t reserved;
  std::uint64_t first_t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t t_step_numerator;
  std::uint64_t factor_count;
};

// Bounded handoff KAT output.  It uses the production-shaped CUB accumulator:
// internal 88-byte states and per-frame range counts never cross to the host.
// Dense page bytes are the exact TGDCSB03 bit layout, though this fixture does
// not supply the source roster/header commitments needed for an atom closure.
struct CompactReductionKatHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t q;
  std::uint32_t character_count;
  std::uint32_t page_count;
  std::uint64_t sample_count;
  std::uint64_t first_t_numerator;
  std::uint64_t stop_t_numerator;
  std::uint64_t t_step_numerator;
  std::uint64_t raw_sparse_range_count;
  std::uint64_t coalesced_sparse_range_count;
  std::uint64_t device_to_host_bytes;
  std::uint32_t reduction_source_status_or;
  std::uint32_t reduction_error_or;
  std::uint32_t pack_source_status_or;
  std::uint32_t pack_error_or;
  std::uint32_t page_totals_size;
  std::uint32_t tagged_range_size;
  std::uint64_t phase_state_device_to_host_bytes;
  std::uint64_t per_frame_count_device_to_host_bytes;
  std::uint64_t payload_bytes;
};

static_assert(sizeof(RootArtifactHeader) == 96U);
static_assert(sizeof(FactorFixtureHeader) == 56U);
static_assert(sizeof(CompactReductionKatHeader) == 128U);
static_assert(sizeof(dpa::TaggedAmbiguityRange) == 24U);

std::vector<unsigned char> readBoundedArtifact(
    const std::string& path, std::uint64_t maximumBytes,
    const sparkinterval::Sha256Digest& expectedDigest,
    const char* label) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) {
    throw std::runtime_error(std::string("could not open ") + label);
  }
  const std::streamoff size = input.tellg();
  if (size <= 0 ||
      static_cast<std::uint64_t>(size) > maximumBytes) {
    throw std::runtime_error(std::string(label) +
                             " size is outside its bounded format");
  }
  input.seekg(0);
  std::vector<unsigned char> raw(static_cast<std::size_t>(size));
  input.read(reinterpret_cast<char*>(raw.data()), size);
  if (!input || input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error(std::string(label) +
                             " changed or has trailing bytes");
  }
  sparkinterval::detail::Sha256 hasher;
  hasher.update(raw.data(), raw.size());
  if (hasher.finish() != expectedDigest) {
    throw std::runtime_error(std::string(label) +
                             " differs from its expected SHA-256");
  }
  return raw;
}

struct PrimitiveDeviceMap {
  std::vector<std::uint64_t> frequency_ids;
  std::vector<std::uint8_t> parities;
};

struct PrimePower {
  std::uint32_t prime;
  std::uint32_t exponent;
};

std::vector<PrimePower> factorPrimePowers(std::uint32_t q) {
  std::vector<PrimePower> result;
  std::uint32_t remaining = q;
  for (std::uint32_t prime = 2U;
       static_cast<std::uint64_t>(prime) * prime <= remaining;
       ++prime) {
    if (remaining % prime != 0U) continue;
    std::uint32_t exponent = 0U;
    do {
      remaining /= prime;
      ++exponent;
    } while (remaining % prime == 0U);
    result.push_back({prime, exponent});
  }
  if (remaining > 1U) result.push_back({remaining, 1U});
  return result;
}

std::uint64_t localPrimitiveCount(const PrimePower& factor) {
  const std::uint32_t p = factor.prime;
  const std::uint32_t exponent = factor.exponent;
  if (p == 2U) {
    if (exponent == 1U) return 0U;
    if (exponent == 2U) return 1U;
    return std::uint64_t{1} << (exponent - 2U);
  }
  if (exponent == 1U) return p - 2U;
  std::uint64_t power = 1U;
  for (std::uint32_t index = 0U; index + 2U < exponent; ++index) {
    power *= p;
  }
  return power * (p - 1ULL) * (p - 1ULL);
}

std::vector<std::uint32_t> unrankLocalPrimitive(
    const PrimePower& factor, std::uint64_t ordinal) {
  const std::uint64_t count = localPrimitiveCount(factor);
  if (ordinal >= count) {
    throw std::runtime_error("local primitive ordinal is out of range");
  }
  if (factor.prime != 2U) {
    if (factor.exponent == 1U) {
      return {static_cast<std::uint32_t>(ordinal + 1U)};
    }
    const std::uint64_t block = ordinal / (factor.prime - 1U);
    const std::uint64_t offset = ordinal % (factor.prime - 1U);
    return {static_cast<std::uint32_t>(
        block * factor.prime + offset + 1U)};
  }
  if (factor.exponent == 2U) return {1U};
  const std::uint64_t perSign =
      std::uint64_t{1} << (factor.exponent - 3U);
  return {
      static_cast<std::uint32_t>(ordinal / perSign),
      static_cast<std::uint32_t>(2U * (ordinal % perSign) + 1U),
  };
}

PrimitiveDeviceMap canonicalPrimitiveDeviceMap(std::uint32_t q) {
  const auto factors = factorPrimePowers(q);
  const auto orders = canonicalOrders(q);
  std::vector<std::uint64_t> radices;
  std::uint64_t characterCount = 1U;
  for (const auto& factor : factors) {
    const std::uint64_t count = localPrimitiveCount(factor);
    if (count == 0U ||
        characterCount >
            std::numeric_limits<std::uint64_t>::max() / count) {
      throw std::runtime_error(
          "modulus has no bounded primitive-character roster");
    }
    radices.push_back(count);
    characterCount *= count;
  }
  if (characterCount == 0U ||
      characterCount > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error("primitive-character count is outside uint32");
  }
  PrimitiveDeviceMap result;
  result.frequency_ids.reserve(static_cast<std::size_t>(characterCount));
  result.parities.reserve(static_cast<std::size_t>(characterCount));
  std::vector<std::uint64_t> localOrdinals(radices.size());
  for (std::uint64_t ordinal = 0U; ordinal < characterCount; ++ordinal) {
    std::uint64_t remaining = ordinal;
    for (std::size_t reverse = radices.size(); reverse != 0U; --reverse) {
      const std::size_t index = reverse - 1U;
      localOrdinals[index] = remaining % radices[index];
      remaining /= radices[index];
    }
    if (remaining != 0U) {
      throw std::runtime_error("primitive mixed-radix unranking overflow");
    }
    std::vector<std::uint32_t> frequencies;
    std::uint8_t parity = 0U;
    for (std::size_t index = 0U; index < factors.size(); ++index) {
      const auto exponents =
          unrankLocalPrimitive(factors[index], localOrdinals[index]);
      parity ^= static_cast<std::uint8_t>(exponents.front() & 1U);
      frequencies.insert(
          frequencies.end(), exponents.begin(), exponents.end());
    }
    if (frequencies.size() != orders.size()) {
      throw std::runtime_error(
          "primitive frequency components differ from allchars");
    }
    std::uint64_t frequencyId = 0U;
    std::uint64_t stride = 1U;
    for (std::size_t index = 0U; index < orders.size(); ++index) {
      if (frequencies[index] >= orders[index]) {
        throw std::runtime_error(
            "primitive frequency is outside its component order");
      }
      frequencyId += stride * frequencies[index];
      stride *= orders[index];
    }
    result.frequency_ids.push_back(frequencyId);
    result.parities.push_back(parity);
  }
  std::vector<std::uint64_t> unique = result.frequency_ids;
  std::sort(unique.begin(), unique.end());
  if (std::adjacent_find(unique.begin(), unique.end()) != unique.end()) {
    throw std::runtime_error("primitive frequency map is not injective");
  }
  return result;
}

struct LoadedRootFixture {
  std::vector<ComplexInterval> rectangles;
  sparkinterval::Sha256Digest sha256;
};

LoadedRootFixture loadRootFixture(
    const std::string& path,
    const sparkinterval::Sha256Digest& expectedDigest,
    std::uint32_t q, std::size_t characterCount) {
  const std::uint64_t maximum =
      sizeof(RootArtifactHeader) +
      32ULL * static_cast<std::uint64_t>(characterCount);
  const auto raw =
      readBoundedArtifact(path, maximum, expectedDigest, "TGDRNRO1");
  RootArtifactHeader header{};
  if (raw.size() < sizeof(header)) {
    throw std::runtime_error("TGDRNRO1 header is truncated");
  }
  std::memcpy(&header, raw.data(), sizeof(header));
  const auto orders = canonicalOrders(q);
  if (std::memcmp(header.magic, kRootArtifactMagic, 8U) != 0 ||
      header.version != 1U || header.q != q ||
      header.component_count != orders.size() ||
      header.record_size != sizeof(ComplexInterval) ||
      header.record_count != characterCount ||
      raw.size() !=
          sizeof(header) +
              characterCount * sizeof(ComplexInterval)) {
    throw std::runtime_error("TGDRNRO1 identity or size differs");
  }
  LoadedRootFixture result;
  result.rectangles.resize(characterCount);
  std::memcpy(
      result.rectangles.data(), raw.data() + sizeof(header),
      characterCount * sizeof(ComplexInterval));
  if (!std::all_of(
          result.rectangles.begin(), result.rectangles.end(),
          finiteOrdered)) {
    throw std::runtime_error("TGDRNRO1 contains malformed rectangle");
  }
  result.sha256 = expectedDigest;
  return result;
}

struct LoadedFactorFixture {
  std::vector<sc::Disk> factors;
  sparkinterval::Sha256Digest sha256;
};

LoadedFactorFixture loadFactorFixture(
    const std::string& path,
    const sparkinterval::Sha256Digest& expectedDigest,
    const LoadedInput& input) {
  constexpr std::uint64_t maximum =
      sizeof(FactorFixtureHeader) +
      2ULL * dr::kMaximumFrameSamples * sizeof(sc::Disk);
  const auto raw = readBoundedArtifact(
      path, maximum, expectedDigest, "TGDCFCT1 factor fixture");
  FactorFixtureHeader header{};
  if (raw.size() < sizeof(header)) {
    throw std::runtime_error("TGDCFCT1 header is truncated");
  }
  std::memcpy(&header, raw.data(), sizeof(header));
  const std::uint64_t factorCount =
      2ULL * input.header.batch_count;
  if (std::memcmp(header.magic, kFactorFixtureMagic, 8U) != 0 ||
      header.version != 1U || header.q != input.header.q ||
      header.sample_count != input.header.batch_count ||
      header.reserved != 0U ||
      header.first_t_numerator !=
          static_cast<std::uint64_t>(
              input.header.first_t_numerator) ||
      header.t_denominator != input.header.t_denominator ||
      header.t_step_numerator != input.header.t_step_numerator ||
      header.factor_count != factorCount ||
      raw.size() !=
          sizeof(header) + factorCount * sizeof(sc::Disk)) {
    throw std::runtime_error("TGDCFCT1 identity or size differs");
  }
  LoadedFactorFixture result;
  result.factors.resize(static_cast<std::size_t>(factorCount));
  std::memcpy(
      result.factors.data(), raw.data() + sizeof(header),
      result.factors.size() * sizeof(sc::Disk));
  if (!std::all_of(
          result.factors.begin(), result.factors.end(),
          [](const sc::Disk& value) {
            return std::isfinite(value.real) &&
                   std::isfinite(value.imaginary) &&
                   std::isfinite(value.radius) &&
                   value.radius >= 0.0;
          })) {
    throw std::runtime_error("TGDCFCT1 contains malformed disk");
  }
  result.sha256 = expectedDigest;
  return result;
}

bool finiteDisk(const sc::Disk& value) {
  return std::isfinite(value.real) &&
         std::isfinite(value.imaginary) &&
         std::isfinite(value.radius) && value.radius >= 0.0;
}

struct RecurrenceArtifactPaths {
  const char* gamma_path;
  sparkinterval::Sha256Digest gamma_sha256;
  const char* step_path;
  sparkinterval::Sha256Digest step_sha256;
  const char* checkpoint_path;
  sparkinterval::Sha256Digest checkpoint_sha256;
};

struct LoadedFactorRecurrence {
  std::vector<sc::Disk> gamma;
  std::vector<sc::Disk> checkpoints;
  sc::Disk step{};
  std::uint32_t checkpoint_span = 0U;
  sparkinterval::Sha256Digest gamma_sha256{};
  sparkinterval::Sha256Digest step_sha256{};
  sparkinterval::Sha256Digest checkpoint_sha256{};
};

LoadedFactorRecurrence loadBoundedFactorRecurrence(
    const RecurrenceArtifactPaths& paths,
    const LoadedInput& input,
    const sparkinterval::Sha256Digest& expectedProducerDigest) {
  if (input.header.first_t_numerator < 0 ||
      static_cast<std::uint64_t>(
          input.header.first_t_numerator) %
              dr::kSourceStepNumerator !=
          0U) {
    throw std::runtime_error(
        "factor recurrence first ordinate is not a source t index");
  }
  const std::uint64_t firstTIndex =
      static_cast<std::uint64_t>(
          input.header.first_t_numerator) /
      dr::kSourceStepNumerator;
  const std::uint64_t stopTIndex =
      firstTIndex + input.header.batch_count;
  sparkinterval::detail::Sha256 scheduleHasher;
  hashUint32LE(&scheduleHasher, input.header.q);
  hashUint32LE(&scheduleHasher, input.header.batch_count);
  const auto expectedScheduleDigest = scheduleHasher.finish();
  sparkinterval::detail::Sha256 phaseScheduleHasher;
  hashUint32LE(&phaseScheduleHasher, input.header.q);
  hashUint32LE(
      &phaseScheduleHasher,
      static_cast<std::uint32_t>(firstTIndex));
  hashUint32LE(
      &phaseScheduleHasher, input.header.batch_count);
  const auto expectedPhaseScheduleDigest =
      phaseScheduleHasher.finish();

  constexpr std::uint64_t gammaMaximum =
      sizeof(dfa::GammaHeader) +
      2ULL * dr::kMaximumFrameSamples * sizeof(sc::Disk);
  const auto gammaRaw = readBoundedArtifact(
      paths.gamma_path, gammaMaximum, paths.gamma_sha256,
      "TGDCGAM1 gamma fixture");
  dfa::GammaHeader gammaHeader{};
  if (gammaRaw.size() < sizeof(gammaHeader)) {
    throw std::runtime_error("TGDCGAM1 header is truncated");
  }
  std::memcpy(&gammaHeader, gammaRaw.data(), sizeof(gammaHeader));
  const std::uint64_t gammaCount =
      2ULL * input.header.batch_count;
  if (std::memcmp(
          gammaHeader.magic, dfa::kGammaMagic,
          sizeof(gammaHeader.magic)) != 0 ||
      gammaHeader.version != dfa::kFormatVersion ||
      gammaHeader.classification != dfa::kBoundedClassification ||
      gammaHeader.disk_size != sizeof(sc::Disk) ||
      gammaHeader.reserved != 0U ||
      gammaHeader.first_t_index != firstTIndex ||
      gammaHeader.t_index_stop_exclusive != stopTIndex ||
      gammaHeader.t_denominator != input.header.t_denominator ||
      gammaHeader.t_step_numerator !=
          input.header.t_step_numerator ||
      gammaHeader.disk_count != gammaCount ||
      gammaHeader.factor_convention_sha256 !=
          dfa::kFactorConventionSha256 ||
      gammaHeader.producer_identity_sha256 !=
          expectedProducerDigest ||
      gammaRaw.size() !=
          sizeof(gammaHeader) + gammaCount * sizeof(sc::Disk)) {
    throw std::runtime_error("TGDCGAM1 identity or size differs");
  }

  constexpr std::uint64_t stepMaximum =
      sizeof(dfa::StepHeader) + sizeof(sc::Disk);
  const auto stepRaw = readBoundedArtifact(
      paths.step_path, stepMaximum, paths.step_sha256,
      "TGDCSTP1 step fixture");
  dfa::StepHeader stepHeader{};
  if (stepRaw.size() < sizeof(stepHeader)) {
    throw std::runtime_error("TGDCSTP1 header is truncated");
  }
  std::memcpy(&stepHeader, stepRaw.data(), sizeof(stepHeader));
  if (std::memcmp(
          stepHeader.magic, dfa::kStepMagic,
          sizeof(stepHeader.magic)) != 0 ||
      stepHeader.version != dfa::kFormatVersion ||
      stepHeader.classification != dfa::kBoundedClassification ||
      stepHeader.disk_size != sizeof(sc::Disk) ||
      stepHeader.reserved != 0U ||
      stepHeader.primitive_roster_version != 2U ||
      stepHeader.q_count != 1U ||
      stepHeader.q_start != input.header.q ||
      stepHeader.q_stop != input.header.q ||
      stepHeader.schedule_manifest_sha256 !=
          expectedScheduleDigest ||
      stepHeader.execution_order_sha256 !=
          expectedScheduleDigest ||
      stepHeader.factor_convention_sha256 !=
          dfa::kFactorConventionSha256 ||
      stepRaw.size() != sizeof(stepHeader) + sizeof(sc::Disk)) {
    throw std::runtime_error("TGDCSTP1 identity or size differs");
  }

  constexpr std::uint64_t checkpointMaximum =
      sizeof(dfa::CheckpointHeader) +
      sizeof(dfa::CheckpointRecordHeader) +
      dr::kMaximumFrameSamples * sizeof(sc::Disk);
  const auto checkpointRaw = readBoundedArtifact(
      paths.checkpoint_path, checkpointMaximum,
      paths.checkpoint_sha256, "TGDCCPB1 checkpoint fixture");
  dfa::CheckpointHeader checkpointHeader{};
  if (checkpointRaw.size() < sizeof(checkpointHeader)) {
    throw std::runtime_error("TGDCCPB1 header is truncated");
  }
  std::memcpy(
      &checkpointHeader, checkpointRaw.data(),
      sizeof(checkpointHeader));
  if (std::memcmp(
          checkpointHeader.magic, dfa::kCheckpointMagic,
          sizeof(checkpointHeader.magic)) != 0 ||
      checkpointHeader.version != dfa::kFormatVersion ||
      checkpointHeader.classification !=
          dfa::kBoundedClassification ||
      checkpointHeader.disk_size != sizeof(sc::Disk) ||
      checkpointHeader.record_header_size !=
          sizeof(dfa::CheckpointRecordHeader) ||
      checkpointHeader.phase_index != 0U ||
      checkpointHeader.first_t_index != firstTIndex ||
      checkpointHeader.t_index_stop_exclusive != stopTIndex ||
      checkpointHeader.t_denominator != input.header.t_denominator ||
      checkpointHeader.t_step_numerator !=
          input.header.t_step_numerator ||
      checkpointHeader.checkpoint_span == 0U ||
      checkpointHeader.q_count != 1U ||
      checkpointHeader.schedule_manifest_sha256 !=
          expectedScheduleDigest ||
      checkpointHeader.phase_schedule_sha256 !=
          expectedPhaseScheduleDigest ||
      checkpointHeader.gamma_artifact_sha256 !=
          paths.gamma_sha256 ||
      checkpointHeader.step_artifact_sha256 !=
          paths.step_sha256 ||
      checkpointHeader.schedule_manifest_sha256 !=
          stepHeader.schedule_manifest_sha256) {
    throw std::runtime_error("TGDCCPB1 identity differs");
  }
  const std::size_t recordOffset = sizeof(checkpointHeader);
  if (checkpointRaw.size() <
      recordOffset + sizeof(dfa::CheckpointRecordHeader)) {
    throw std::runtime_error(
        "TGDCCPB1 record header is truncated");
  }
  dfa::CheckpointRecordHeader record{};
  std::memcpy(
      &record, checkpointRaw.data() + recordOffset,
      sizeof(record));
  const std::uint32_t expectedCheckpoints =
      1U + (input.header.batch_count - 1U) /
               checkpointHeader.checkpoint_span;
  if (record.q != input.header.q ||
      record.sample_count != input.header.batch_count ||
      record.checkpoint_count != expectedCheckpoints ||
      record.reserved != 0U ||
      checkpointHeader.checkpoint_count != expectedCheckpoints ||
      checkpointRaw.size() !=
          recordOffset + sizeof(record) +
              static_cast<std::uint64_t>(expectedCheckpoints) *
                  sizeof(sc::Disk)) {
    throw std::runtime_error(
        "TGDCCPB1 record identity or size differs");
  }

  LoadedFactorRecurrence result;
  result.gamma.resize(static_cast<std::size_t>(gammaCount));
  std::memcpy(
      result.gamma.data(), gammaRaw.data() + sizeof(gammaHeader),
      result.gamma.size() * sizeof(sc::Disk));
  std::memcpy(
      &result.step, stepRaw.data() + sizeof(stepHeader),
      sizeof(result.step));
  result.checkpoints.resize(expectedCheckpoints);
  std::memcpy(
      result.checkpoints.data(),
      checkpointRaw.data() + recordOffset + sizeof(record),
      result.checkpoints.size() * sizeof(sc::Disk));
  if (!std::all_of(
          result.gamma.begin(), result.gamma.end(), finiteDisk) ||
      !finiteDisk(result.step) ||
      !std::all_of(
          result.checkpoints.begin(),
          result.checkpoints.end(), finiteDisk)) {
    throw std::runtime_error(
        "completed factor recurrence contains malformed disk");
  }
  result.checkpoint_span = checkpointHeader.checkpoint_span;
  result.gamma_sha256 = paths.gamma_sha256;
  result.step_sha256 = paths.step_sha256;
  result.checkpoint_sha256 = paths.checkpoint_sha256;
  return result;
}

template <typename T>
struct DeviceArray {
  T* data = nullptr;
  std::size_t count = 0U;

  DeviceArray() = default;
  explicit DeviceArray(std::size_t requested) : count(requested) {
    CUDA_CHECK(cudaMalloc(
        &data, std::max<std::size_t>(1U, count) * sizeof(T)));
  }
  DeviceArray(const DeviceArray&) = delete;
  DeviceArray& operator=(const DeviceArray&) = delete;
  ~DeviceArray() { cudaFree(data); }
};

sparkinterval::Sha256Digest merkleRoot(
    std::vector<sparkinterval::Sha256Digest> level) {
  if (level.empty()) throw std::runtime_error("cannot Merkle-hash no receipts");
  while (level.size() > 1U) {
    if ((level.size() & 1U) != 0U) level.push_back(level.back());
    std::vector<sparkinterval::Sha256Digest> next;
    next.reserve(level.size() / 2U);
    for (std::size_t index = 0; index < level.size(); index += 2U) {
      sparkinterval::detail::Sha256 hasher;
      hasher.update(level[index].data(), level[index].size());
      hasher.update(level[index + 1U].data(), level[index + 1U].size());
      next.push_back(hasher.finish());
    }
    level = std::move(next);
  }
  return level.front();
}

void writeAll(int descriptor, const void* raw, std::size_t size) {
  const char* data = static_cast<const char*>(raw);
  while (size != 0U) {
    const ssize_t written = ::write(descriptor, data, size);
    if (written < 0 && errno == EINTR) continue;
    if (written <= 0) throw std::runtime_error("stream pipe write failed");
    data += written;
    size -= static_cast<std::size_t>(written);
  }
}

int runBoundedResidentCompletedSignHandoff(
    const char* inputPath, const char* rootPath,
    const sparkinterval::Sha256Digest& rootSha256,
    const char* factorPath,
    const sparkinterval::Sha256Digest& factorSha256,
    const char* statePath, const char* summaryPath,
    std::uint32_t device,
    const RecurrenceArtifactPaths* recurrencePaths = nullptr,
    const sparkinterval::Sha256Digest* expectedRecurrenceProducer =
        nullptr,
    bool realArbQualification = false) {
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(
      &properties, static_cast<int>(device)));
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error(
        "strict target requires compute capability 9.0");
  }
#endif
  LoadedInput input = loadInput(inputPath);
  if (input.header.batch_count > dr::kMaximumFrameSamples ||
      input.header.t_denominator != dr::kSourceDenominator ||
      input.header.t_step_numerator != dr::kSourceStepNumerator) {
    throw std::runtime_error(
        "bounded resident reducer requires one <=64-row 5/64 frame");
  }
  const PrimitiveDeviceMap primitive =
      canonicalPrimitiveDeviceMap(input.header.q);
  if (primitive.frequency_ids.empty()) {
    throw std::runtime_error(
        "bounded resident reducer has no primitive characters");
  }
  const LoadedRootFixture roots = loadRootFixture(
      rootPath, rootSha256, input.header.q,
      primitive.frequency_ids.size());
  std::optional<LoadedFactorFixture> directFactors;
  std::optional<LoadedFactorRecurrence> recurrence;
  if (recurrencePaths == nullptr) {
    if (factorPath == nullptr) {
      throw std::runtime_error(
          "bounded direct factor fixture path is null");
    }
    directFactors = loadFactorFixture(
        factorPath, factorSha256, input);
  } else {
    if (expectedRecurrenceProducer == nullptr) {
      throw std::runtime_error(
          "bounded recurrence producer identity is absent");
    }
    recurrence = loadBoundedFactorRecurrence(
        *recurrencePaths, input, *expectedRecurrenceProducer);
  }

  const auto orders = canonicalOrders(input.header.q);
  TransformPlan transform(orders, input.header.value_count);
  // This copies only producer input H2D.  Crucially, executeDevice returns the
  // transformed device pointer; no TGDAFFO1 payload is copied back or written.
  const DeviceTransformResult transformed =
      transform.executeDevice(input.values);

  const std::size_t characters = primitive.frequency_ids.size();
  DeviceArray<ComplexInterval> dRootRectangles(characters);
  DeviceArray<sc::Disk> dRoots(characters);
  const std::size_t factorCount =
      2U * static_cast<std::size_t>(input.header.batch_count);
  DeviceArray<sc::Disk> dFactors(factorCount);
  DeviceArray<sc::Disk> dGamma(
      recurrence.has_value() ? recurrence->gamma.size() : 0U);
  DeviceArray<sc::Disk> dCheckpoints(
      recurrence.has_value() ? recurrence->checkpoints.size() : 0U);
  DeviceArray<std::uint8_t> dParities(characters);
  DeviceArray<std::uint64_t> dFrequencies(characters);
  DeviceArray<dr::DeviceSummary> dConversionSummary(1U);
  DeviceArray<dr::DeviceSummary> dFactorSummary(1U);
  CUDA_CHECK(cudaMemcpy(
      dRootRectangles.data, roots.rectangles.data(),
      characters * sizeof(ComplexInterval), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(
      dFactorSummary.data, 0, sizeof(dr::DeviceSummary)));
  if (directFactors.has_value()) {
    CUDA_CHECK(cudaMemcpy(
        dFactors.data, directFactors->factors.data(),
        directFactors->factors.size() * sizeof(sc::Disk),
        cudaMemcpyHostToDevice));
  } else {
    CUDA_CHECK(cudaMemcpy(
        dGamma.data, recurrence->gamma.data(),
        recurrence->gamma.size() * sizeof(sc::Disk),
        cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(
        dCheckpoints.data, recurrence->checkpoints.data(),
        recurrence->checkpoints.size() * sizeof(sc::Disk),
        cudaMemcpyHostToDevice));
    const dr::FactorRecurrenceView factorRecurrence{
        dGamma.data,
        dCheckpoints.data,
        recurrence->step,
        input.header.batch_count,
        recurrence->checkpoint_span,
        static_cast<std::uint32_t>(
            recurrence->checkpoints.size()),
    };
    CUDA_CHECK(dr::launchParityFactorsFromCheckpoints(
        factorRecurrence, dFactors.data, dFactorSummary.data));
  }
  CUDA_CHECK(cudaMemcpy(
      dParities.data, primitive.parities.data(),
      characters * sizeof(std::uint8_t), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(
      dFrequencies.data, primitive.frequency_ids.data(),
      characters * sizeof(std::uint64_t), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(
      dConversionSummary.data, 0, sizeof(dr::DeviceSummary)));
  const std::uint32_t conversionBlocks = std::min<std::uint32_t>(
      4096U,
      (static_cast<std::uint32_t>(characters) + 255U) / 256U);
  dr::convertRectanglesToDisks<<<conversionBlocks, 256>>>(
      dRootRectangles.data, characters, dRoots.data,
      dr::kInvalidRootDisk, dConversionSummary.data);
  CUDA_CHECK(cudaGetLastError());
  dr::DeviceSummary conversionSummary{};
  CUDA_CHECK(cudaMemcpy(
      &conversionSummary, dConversionSummary.data,
      sizeof(conversionSummary), cudaMemcpyDeviceToHost));
  if (conversionSummary.source_status_or != 0U ||
      conversionSummary.reducer_error_or != 0U ||
      conversionSummary.ambiguity_range_count != 0U) {
    throw std::runtime_error(
        "bounded resident reducer root conversion failed");
  }

  const dr::ResidentFrameView frame{
      input.header.q,
      static_cast<std::uint32_t>(characters),
      input.header.batch_count,
      0U,
      input.header.group_order,
      transformed.value_count,
      static_cast<std::uint64_t>(input.header.first_t_numerator),
      input.header.t_step_numerator,
      transformed.values,
      nullptr,
      dRoots.data,
      dFactors.data,
      dParities.data,
      dFrequencies.data,
  };

  std::uint64_t stopNumerator = 0U;
  if (!dr::sampleNumerator(
          frame.first_t_numerator, frame.t_step_numerator,
          frame.sample_count, &stopNumerator)) {
    throw std::runtime_error(
        "bounded resident output coordinate overflow");
  }
  const std::uint64_t maximumRangesPerCharacter =
      (static_cast<std::uint64_t>(frame.sample_count) + 1U) / 2U;
  std::uint64_t sparseCapacity = 0U;
  if (!dr::checkedMul(
          frame.character_count, maximumRangesPerCharacter,
          &sparseCapacity) ||
      sparseCapacity == 0U) {
    throw std::runtime_error(
        "bounded resident sparse capacity overflows");
  }
  const dpa::PhaseAccumulatorConfig accumulatorConfig{
      frame.q,
      frame.character_count,
      frame.sample_count,
      frame.first_t_numerator,
      stopNumerator,
      frame.t_step_numerator,
      sparseCapacity,
  };
  dpa::ResidentPhaseAccumulator accumulator(accumulatorConfig);
  CUDA_CHECK(accumulator.enqueueFrame(frame));
  const dpa::PhaseCheckpoint checkpoint = accumulator.checkpoint();
  dr::DeviceSummary factorSummary{};
  CUDA_CHECK(cudaMemcpy(
      &factorSummary, dFactorSummary.data, sizeof(factorSummary),
      cudaMemcpyDeviceToHost));
  if (factorSummary.source_status_or != 0U ||
      factorSummary.reducer_error_or != 0U ||
      factorSummary.ambiguity_range_count != 0U) {
    throw std::runtime_error(
        "bounded resident factor recurrence failed closed");
  }
  std::uint64_t payloadBytes = 0U;
  for (const auto& page : checkpoint.pages) {
    std::uint64_t pageBytes = 0U;
    if (!dr::checkedAdd(
            sizeof(dr::DensePageTotals), page.dense.size(),
            &pageBytes) ||
        !dr::checkedAdd(payloadBytes, pageBytes, &payloadBytes)) {
      throw std::runtime_error(
          "bounded resident compact page size overflows");
    }
  }
  std::uint64_t taggedBytes = 0U;
  if (!dr::checkedMul(
          checkpoint.ambiguity_ranges.size(),
          sizeof(dpa::TaggedAmbiguityRange), &taggedBytes) ||
      !dr::checkedAdd(payloadBytes, taggedBytes, &payloadBytes)) {
    throw std::runtime_error(
        "bounded resident sparse payload size overflows");
  }
  const CompactReductionKatHeader header{
      {'T', 'G', 'D', 'C', 'P', 'C', 'K', '1'},
      1U,
      frame.q,
      frame.character_count,
      static_cast<std::uint32_t>(checkpoint.pages.size()),
      frame.sample_count,
      frame.first_t_numerator,
      stopNumerator,
      frame.t_step_numerator,
      checkpoint.raw_sparse_range_count,
      checkpoint.coalesced_sparse_range_count,
      checkpoint.device_to_host_bytes,
      checkpoint.reduction_summary.source_status_or,
      checkpoint.reduction_summary.reducer_error_or,
      checkpoint.pack_summary.source_status_or,
      checkpoint.pack_summary.reducer_error_or,
      static_cast<std::uint32_t>(sizeof(dr::DensePageTotals)),
      static_cast<std::uint32_t>(sizeof(dpa::TaggedAmbiguityRange)),
      checkpoint.phase_state_device_to_host_bytes,
      checkpoint.per_frame_count_device_to_host_bytes,
      payloadBytes,
  };
  if (std::filesystem::exists(statePath)) {
    throw std::runtime_error(
        "refusing to replace bounded resident reduction state");
  }
  const std::string stateTemporary =
      std::string(statePath) + ".tmp." + std::to_string(getpid());
  {
    std::ofstream output(
        stateTemporary, std::ios::binary | std::ios::trunc);
    if (!output) {
      throw std::runtime_error(
          "could not create bounded resident reduction state");
    }
    output.write(
        reinterpret_cast<const char*>(&header), sizeof(header));
    for (const auto& page : checkpoint.pages) {
      output.write(
          reinterpret_cast<const char*>(&page.totals),
          sizeof(page.totals));
      output.write(
          reinterpret_cast<const char*>(page.dense.data()),
          static_cast<std::streamsize>(page.dense.size()));
    }
    output.write(
        reinterpret_cast<const char*>(
            checkpoint.ambiguity_ranges.data()),
        static_cast<std::streamsize>(
            checkpoint.ambiguity_ranges.size() *
            sizeof(checkpoint.ambiguity_ranges[0])));
    if (!output) {
      throw std::runtime_error(
          "could not write bounded resident reduction state");
    }
  }
  std::error_code stateError;
  std::filesystem::rename(stateTemporary, statePath, stateError);
  if (stateError) {
    std::filesystem::remove(stateTemporary);
    throw std::runtime_error(
        "could not publish bounded resident reduction state");
  }
  const auto inputDigest = hashFile(inputPath);
  const auto stateDigest = hashFile(statePath);
  const std::string summaryTemporary =
      std::string(summaryPath) + ".tmp." + std::to_string(getpid());
  std::ofstream output(summaryTemporary, std::ios::trunc);
  if (!output) {
    throw std::runtime_error(
        "could not create bounded resident reduction summary");
  }
  output
      << "{\"algorithm\":"
         "\"tg-dirichlet-allchars-resident-completed-sign-handoff-kat-v1\","
      << "\"classification\":"
      << (realArbQualification
              ? "\"bounded_real_arb_recurrence_qualification_not_source_or_atom_closure\","
              : "\"bounded_synthetic_handoff_not_source_or_atom_closure\",")
      << "\"q\":" << frame.q
      << ",\"character_count\":" << frame.character_count
      << ",\"sample_count\":" << frame.sample_count
      << ",\"first_t_numerator\":" << frame.first_t_numerator
      << ",\"stop_t_numerator\":" << stopNumerator
      << ",\"t_denominator\":" << input.header.t_denominator
      << ",\"t_step_numerator\":" << frame.t_step_numerator
      << ",\"input_sha256\":\""
      << sparkinterval::lowercase_hex(inputDigest)
      << "\",\"root_artifact_sha256\":\""
      << sparkinterval::lowercase_hex(rootSha256);
  if (recurrence.has_value()) {
    output
        << "\",\"expected_factor_producer_sha256\":\""
        << sparkinterval::lowercase_hex(
               *expectedRecurrenceProducer)
        << "\",\"gamma_artifact_sha256\":\""
        << sparkinterval::lowercase_hex(
               recurrence->gamma_sha256)
        << "\",\"step_artifact_sha256\":\""
        << sparkinterval::lowercase_hex(
               recurrence->step_sha256)
        << "\",\"checkpoint_artifact_sha256\":\""
        << sparkinterval::lowercase_hex(
               recurrence->checkpoint_sha256);
  } else {
    output
        << "\",\"factor_fixture_sha256\":\""
        << sparkinterval::lowercase_hex(factorSha256);
  }
  output
      << "\",\"state_sha256\":\""
      << sparkinterval::lowercase_hex(stateDigest)
      << "\",\"state_bytes\":"
      << std::filesystem::file_size(statePath)
      << ",\"transform_elapsed_nanoseconds\":"
      << transformed.elapsed_nanoseconds
      << ",\"TGDAFFO1_device_to_host_bytes\":0"
      << ",\"raw_transform_stream_materialized\":false"
      << ",\"same_cuda_address_space_reduction\":true"
      << ",\"device_cub_range_scan\":true"
      << ",\"device_adjacent_state_merge\":true"
      << ",\"device_tgdcsb03_dense_pack\":true"
      << ",\"bounded_host_range_count_copy\":false"
      << ",\"phase_state_device_to_host_bytes\":"
      << checkpoint.phase_state_device_to_host_bytes
      << ",\"per_frame_count_device_to_host_bytes\":"
      << checkpoint.per_frame_count_device_to_host_bytes
      << ",\"compact_checkpoint_device_to_host_bytes\":"
      << checkpoint.device_to_host_bytes
      << ",\"dense_staging_device_to_host_bytes\":"
      << checkpoint.dense_staging_device_to_host_bytes
      << ",\"canonical_dense_bytes\":"
      << checkpoint.canonical_dense_bytes
      << ",\"dense_device_to_host_copy_count\":"
      << checkpoint.dense_device_to_host_copy_count
      << ",\"raw_sparse_range_count\":"
      << checkpoint.raw_sparse_range_count
      << ",\"coalesced_sparse_range_count\":"
      << checkpoint.coalesced_sparse_range_count
      << ",\"factor_checkpoint_recurrence_path\":"
      << (recurrence.has_value() ? "true" : "false")
      << ",\"conductor_step_t_numerator\":5"
      << ",\"conductor_step_t_denominator\":128"
      << ",\"conductor_step_applications_per_sample\":1"
      << ",\"factor_summary_source_status_or\":"
      << factorSummary.source_status_or
      << ",\"factor_summary_reducer_error_or\":"
      << factorSummary.reducer_error_or
      << ",\"source_packed_state_path\":false"
      << ",\"source_factor_recurrence_path\":false"
      << ",\"source_performance_ready\":false"
      << ",\"production_run_completed\":false"
      << ",\"trusted_execution_attested\":false"
      << ",\"zero_completeness_claimed\":false"
      << ",\"external_atom_discharged\":false}\n";
  output.close();
  if (!output) {
    throw std::runtime_error(
        "could not write bounded resident reduction summary");
  }
  std::error_code summaryError;
  std::filesystem::rename(
      summaryTemporary, summaryPath, summaryError);
  if (summaryError) {
    std::filesystem::remove(summaryTemporary);
    throw std::runtime_error(
        "could not publish bounded resident reduction summary");
  }
  return 0;
}

void writeFramedSummary(
    const std::string& path, std::uint32_t q, std::uint32_t maximumBatch,
    std::uint64_t frames, std::uint64_t slices, std::uint64_t values,
    std::uint64_t butterflies, std::uint64_t preparation,
    std::uint64_t elapsed, const sparkinterval::Sha256Digest& inputDigest,
    const sparkinterval::Sha256Digest& outputDigest) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  std::ofstream output(temporary, std::ios::trunc);
  if (!output) throw std::runtime_error("could not create framed summary");
  output
      << "{\"kind\":\"sparkinterval.tg.dirichlet_allchars.framed_service.v1\","
      << "\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
      << "\"q\":" << q << ",\"maximum_batch_count\":" << maximumBatch
      << ",\"frame_count\":" << frames << ",\"slice_count\":" << slices
      << ",\"value_count\":" << values
      << ",\"radix2_butterflies\":" << butterflies
      << ",\"preparation_nanoseconds\":" << preparation
      << ",\"elapsed_nanoseconds\":" << elapsed
      << ",\"retained_input_frames\":0,\"retained_output_frames\":0,"
      << "\"input_stream_sha256\":\""
      << sparkinterval::lowercase_hex(inputDigest)
      << "\",\"output_stream_sha256\":\""
      << sparkinterval::lowercase_hex(outputDigest) << "\"}\n";
  output.close();
  if (!output) throw std::runtime_error("could not write framed summary");
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish framed summary");
  }
}

// Persistent binary service used by the source-scale pipeline:
//
//   concatenated TGDAFFI1 frames -> one retained CUDA plan -> TGDAFFO1 frames.
//
// It deliberately writes no status text to stdout.  The downstream completed-L
// consumer therefore sees a pure self-delimiting binary stream.  The summary
// binds both streams and is published only after a clean EOF and successful
// completion of every frame.
int runFramedService(std::uint32_t q, std::uint32_t maximumBatch,
                     const char* summaryPath, std::uint32_t device) {
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error("strict target requires compute capability 9.0");
  }
#endif
  if (maximumBatch == 0U) {
    throw std::runtime_error("maximum batch count must be positive");
  }
  const auto orders = canonicalOrders(q);
  const std::uint64_t groupOrder = orderProduct(orders);
  if (groupOrder > std::numeric_limits<std::uint64_t>::max() / maximumBatch) {
    throw std::runtime_error("framed service capacity overflow");
  }
  const std::uint64_t maximumValues = groupOrder * maximumBatch;
  const auto preparationStart = std::chrono::steady_clock::now();
  const TransformPlan transform(orders, maximumValues);
  const auto preparationStop = std::chrono::steady_clock::now();
  const auto preparation = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          preparationStop - preparationStart).count());

  std::signal(SIGPIPE, SIG_IGN);
  sparkinterval::detail::Sha256 inputHasher;
  sparkinterval::detail::Sha256 outputHasher;
  std::uint64_t frames = 0U;
  std::uint64_t slices = 0U;
  std::uint64_t values = 0U;
  std::uint64_t butterflies = 0U;
  std::uint64_t elapsedTotal = 0U;
  std::uint64_t expectedFirst = 0U;
  std::uint64_t denominator = 0U;
  std::uint64_t step = 0U;
  bool haveProgression = false;

  while (true) {
    LoadedInput input;
    if (!readInputFrame(std::cin, "persistent stdin", &input)) break;
    if (input.header.q != q || input.orders != orders ||
        input.header.batch_count > maximumBatch) {
      throw std::runtime_error("framed input exceeds or changes service plan");
    }
    const std::uint64_t first =
        static_cast<std::uint64_t>(input.header.first_t_numerator);
    if (!haveProgression) {
      denominator = input.header.t_denominator;
      step = input.header.t_step_numerator;
      haveProgression = true;
    } else if (input.header.t_denominator != denominator ||
               input.header.t_step_numerator != step ||
               first != expectedFirst) {
      throw std::runtime_error(
          "framed inputs are not one contiguous ordinate progression");
    }
    const std::uint64_t batch = input.header.batch_count;
    if (batch > (std::numeric_limits<std::uint64_t>::max() - first) / step) {
      throw std::runtime_error("framed ordinate progression overflow");
    }
    expectedFirst = first + batch * step;

    inputHasher.update(&input.header, sizeof(input.header));
    inputHasher.update(input.values.data(),
                       input.values.size() * sizeof(input.values[0]));
    const std::uint64_t elapsed = transform.execute(&input.values);
    if (!std::all_of(input.values.begin(), input.values.end(), finiteOrdered)) {
      throw std::runtime_error("framed transform produced malformed interval");
    }
    const auto output = makeOutputHeader(input, elapsed);
    outputHasher.update(&output, sizeof(output));
    outputHasher.update(input.values.data(),
                        input.values.size() * sizeof(input.values[0]));
    writeAll(STDOUT_FILENO, &output, sizeof(output));
    writeAll(STDOUT_FILENO, input.values.data(),
             input.values.size() * sizeof(input.values[0]));

    ++frames;
    slices += batch;
    values += input.values.size();
    butterflies += input.butterflies;
    elapsedTotal += elapsed;
  }
  if (frames == 0U) {
    throw std::runtime_error("framed service received no input frames");
  }
  writeFramedSummary(summaryPath, q, maximumBatch, frames, slices, values,
                     butterflies, preparation, elapsedTotal,
                     inputHasher.finish(), outputHasher.finish());
  return 0;
}

void writeMultiQFramedSummary(
    const std::string& path, std::uint32_t maximumBatch,
    std::uint32_t firstQ, std::uint32_t lastQ, std::uint64_t moduli,
    std::uint64_t frames,
    std::uint64_t slices, std::uint64_t values, std::uint64_t butterflies,
    std::uint64_t preparation, std::uint64_t elapsed,
    const OrderCacheStats& orderStats, std::uint64_t retainedOrderEntries,
    const RootPoolStats& rootStats, std::uint64_t retainedRootEntries,
    const sparkinterval::Sha256Digest& orderKeyDigest,
    const sparkinterval::Sha256Digest& rootCatalogDigest,
    const sparkinterval::Sha256Digest& inputDigest,
    const sparkinterval::Sha256Digest& outputDigest) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  std::ofstream output(temporary, std::ios::trunc);
  if (!output) throw std::runtime_error("could not create multi-q summary");
  output
      << "{\"kind\":"
         "\"sparkinterval.tg.dirichlet_allchars.multiq_framed_service.v2\","
      << "\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
      << "\"cache_algorithm\":"
         "\"bounded-device-split-root-order-lru-v2\","
      << "\"root_pool_algorithm\":"
         "\"immutable-directed-radix2-root-pool-v1\","
      << "\"maximum_batch_count\":" << maximumBatch
      << ",\"cache_capacity_bytes\":" << kMultiQTotalCacheBytes
      << ",\"root_pool_catalog_entries\":" << kSourceRootCatalogEntries
      << ",\"root_pool_reserved_bytes\":"
      << kSourceRootPoolReservedBytes
      << ",\"order_cache_capacity_bytes\":" << kMultiQOrderCacheBytes
      << ",\"first_q\":" << firstQ << ",\"last_q\":" << lastQ
      << ",\"modulus_count\":" << moduli << ",\"frame_count\":" << frames
      << ",\"slice_count\":" << slices << ",\"value_count\":" << values
      << ",\"radix2_butterflies\":" << butterflies
      << ",\"preparation_nanoseconds\":" << preparation
      << ",\"elapsed_nanoseconds\":" << elapsed
      << ",\"root_pool_accesses\":" << rootStats.accesses
      << ",\"root_pool_hits\":" << rootStats.hits
      << ",\"root_pool_misses\":" << rootStats.misses
      << ",\"root_pool_retained_entries\":" << retainedRootEntries
      << ",\"root_pool_retained_bytes\":" << rootStats.retainedBytes
      << ",\"root_pool_prepared_enclosures\":"
      << rootStats.preparedEnclosures
      << ",\"order_cache_accesses\":" << orderStats.accesses
      << ",\"order_cache_hits\":" << orderStats.hits
      << ",\"order_cache_misses\":" << orderStats.misses
      << ",\"order_cache_evictions\":" << orderStats.evictions
      << ",\"order_cache_uncached_misses\":"
      << orderStats.uncachedMisses
      << ",\"order_cache_retained_entries\":" << retainedOrderEntries
      << ",\"order_cache_retained_bytes\":" << orderStats.retainedBytes
      << ",\"order_cache_peak_retained_bytes\":"
      << orderStats.peakRetainedBytes
      << ",\"order_cache_prepared_enclosures\":"
      << orderStats.preparedEnclosures
      << ",\"total_prepared_enclosures\":"
      << orderStats.preparedEnclosures + rootStats.preparedEnclosures
      << ",\"cache_peak_total_retained_bytes\":"
      << orderStats.peakTotalRetainedBytes
      << ",\"order_cache_key_chain_sha256\":\""
      << sparkinterval::lowercase_hex(orderKeyDigest)
      << "\",\"root_pool_catalog_sha256\":\""
      << sparkinterval::lowercase_hex(rootCatalogDigest)
      << "\",\"retained_input_frames\":0,\"retained_output_frames\":0,"
      << "\"input_stream_sha256\":\""
      << sparkinterval::lowercase_hex(inputDigest)
      << "\",\"output_stream_sha256\":\""
      << sparkinterval::lowercase_hex(outputDigest) << "\"}\n";
  output.close();
  if (!output) throw std::runtime_error("could not write multi-q summary");
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish multi-q summary");
  }
}

void writeScheduledMultiQFramedSummary(
    const std::string& path, std::uint32_t maximumBatch,
    const LoadedQOrderManifest& schedule, std::uint32_t firstQ,
    std::uint32_t lastQ, std::uint64_t moduli, std::uint64_t frames,
    std::uint64_t slices, std::uint64_t values, std::uint64_t butterflies,
    std::uint64_t preparation, std::uint64_t elapsed,
    const OrderCacheStats& orderStats, std::uint64_t retainedOrderEntries,
    const RootPoolStats& rootStats, std::uint64_t retainedRootEntries,
    const sparkinterval::Sha256Digest& orderKeyDigest,
    const sparkinterval::Sha256Digest& rootCatalogDigest,
    const sparkinterval::Sha256Digest& inputDigest,
    const sparkinterval::Sha256Digest& outputDigest) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  std::ofstream output(temporary, std::ios::trunc);
  if (!output) {
    throw std::runtime_error("could not create scheduled multi-q summary");
  }
  output
      << "{\"kind\":"
         "\"sparkinterval.tg.dirichlet_allchars."
         "scheduled_multiq_framed_service.v1\","
      << "\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
      << "\"scheduler_algorithm\":\"" << kQOrderSchedulerAlgorithm << "\","
      << "\"schedule_classification\":\""
      << schedule.classificationName() << "\","
      << "\"schedule_manifest_sha256\":\""
      << sparkinterval::lowercase_hex(schedule.file_digest)
      << "\",\"schedule_source_roster_sha256\":\""
      << sparkinterval::lowercase_hex(schedule.source_digest)
      << "\",\"schedule_execution_order_sha256\":\""
      << sparkinterval::lowercase_hex(schedule.execution_digest) << "\","
      << "\"cache_algorithm\":"
         "\"bounded-device-split-root-order-lru-v2\","
      << "\"root_pool_algorithm\":"
         "\"immutable-directed-radix2-root-pool-v1\","
      << "\"maximum_batch_count\":" << maximumBatch
      << ",\"cache_capacity_bytes\":" << kMultiQTotalCacheBytes
      << ",\"root_pool_catalog_entries\":" << kSourceRootCatalogEntries
      << ",\"root_pool_reserved_bytes\":"
      << kSourceRootPoolReservedBytes
      << ",\"order_cache_capacity_bytes\":" << kMultiQOrderCacheBytes
      << ",\"first_q\":" << firstQ << ",\"last_q\":" << lastQ
      << ",\"modulus_count\":" << moduli
      << ",\"scheduled_t_index_rows\":" << schedule.header.t_row_count
      << ",\"frame_count\":" << frames
      << ",\"slice_count\":" << slices << ",\"value_count\":" << values
      << ",\"radix2_butterflies\":" << butterflies
      << ",\"preparation_nanoseconds\":" << preparation
      << ",\"elapsed_nanoseconds\":" << elapsed
      << ",\"root_pool_accesses\":" << rootStats.accesses
      << ",\"root_pool_hits\":" << rootStats.hits
      << ",\"root_pool_misses\":" << rootStats.misses
      << ",\"root_pool_retained_entries\":" << retainedRootEntries
      << ",\"root_pool_retained_bytes\":" << rootStats.retainedBytes
      << ",\"root_pool_prepared_enclosures\":"
      << rootStats.preparedEnclosures
      << ",\"order_cache_accesses\":" << orderStats.accesses
      << ",\"order_cache_hits\":" << orderStats.hits
      << ",\"order_cache_misses\":" << orderStats.misses
      << ",\"order_cache_evictions\":" << orderStats.evictions
      << ",\"order_cache_uncached_misses\":"
      << orderStats.uncachedMisses
      << ",\"order_cache_retained_entries\":" << retainedOrderEntries
      << ",\"order_cache_retained_bytes\":" << orderStats.retainedBytes
      << ",\"order_cache_peak_retained_bytes\":"
      << orderStats.peakRetainedBytes
      << ",\"order_cache_prepared_enclosures\":"
      << orderStats.preparedEnclosures
      << ",\"total_prepared_enclosures\":"
      << orderStats.preparedEnclosures + rootStats.preparedEnclosures
      << ",\"cache_peak_total_retained_bytes\":"
      << orderStats.peakTotalRetainedBytes
      << ",\"order_cache_key_chain_sha256\":\""
      << sparkinterval::lowercase_hex(orderKeyDigest)
      << "\",\"root_pool_catalog_sha256\":\""
      << sparkinterval::lowercase_hex(rootCatalogDigest)
      << "\",\"retained_input_frames\":0,\"retained_output_frames\":0,"
      << "\"input_stream_sha256\":\""
      << sparkinterval::lowercase_hex(inputDigest)
      << "\",\"output_stream_sha256\":\""
      << sparkinterval::lowercase_hex(outputDigest) << "\"}\n";
  output.close();
  if (!output) {
    throw std::runtime_error("could not write scheduled multi-q summary");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error(
        "could not publish scheduled multi-q summary");
  }
}

void writePhaseScheduledMultiQFramedSummary(
    const std::string& path, std::uint32_t maximumBatch,
    const LoadedQOrderManifest& schedule,
    const PhaseScheduleCoverage& phase, std::uint32_t firstQ,
    std::uint32_t lastQ, std::uint64_t moduli, std::uint64_t frames,
    std::uint64_t slices, std::uint64_t values,
    std::uint64_t butterflies, std::uint64_t preparation,
    std::uint64_t elapsed, const OrderCacheStats& orderStats,
    std::uint64_t retainedOrderEntries, const RootPoolStats& rootStats,
    std::uint64_t retainedRootEntries,
    const sparkinterval::Sha256Digest& orderKeyDigest,
    const sparkinterval::Sha256Digest& rootCatalogDigest,
    const sparkinterval::Sha256Digest& inputDigest,
    const sparkinterval::Sha256Digest& outputDigest) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  std::ofstream output(temporary, std::ios::trunc);
  if (!output) {
    throw std::runtime_error(
        "could not create phase scheduled multi-q summary");
  }
  output
      << "{\"kind\":"
         "\"sparkinterval.tg.dirichlet_allchars."
         "phase_scheduled_multiq_framed_service.v1\","
      << "\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
      << "\"scheduler_algorithm\":\"" << kQOrderSchedulerAlgorithm << "\","
      << "\"schedule_classification\":\""
      << schedule.classificationName() << "\","
      << "\"schedule_manifest_sha256\":\""
      << sparkinterval::lowercase_hex(schedule.file_digest)
      << "\",\"schedule_source_roster_sha256\":\""
      << sparkinterval::lowercase_hex(schedule.source_digest)
      << "\",\"schedule_execution_order_sha256\":\""
      << sparkinterval::lowercase_hex(schedule.execution_digest)
      << "\",\"phase_plan_sha256\":\""
      << sparkinterval::lowercase_hex(phase.phase_plan_digest)
      << "\",\"phase_schedule_sha256\":\""
      << sparkinterval::lowercase_hex(phase.phase_schedule_digest) << "\","
      << "\"cache_algorithm\":"
         "\"bounded-device-split-root-order-lru-v2\","
      << "\"root_pool_algorithm\":"
         "\"immutable-directed-radix2-root-pool-v1\","
      << "\"maximum_batch_count\":" << maximumBatch
      << ",\"cache_capacity_bytes\":" << kMultiQTotalCacheBytes
      << ",\"root_pool_catalog_entries\":" << kSourceRootCatalogEntries
      << ",\"root_pool_reserved_bytes\":"
      << kSourceRootPoolReservedBytes
      << ",\"order_cache_capacity_bytes\":" << kMultiQOrderCacheBytes
      << ",\"phase_first_t_index\":" << phase.first_t_index
      << ",\"phase_stop_t_index_exclusive\":"
      << phase.t_index_stop_exclusive
      << ",\"phase_execution_q_start_index\":"
      << phase.start_execution_q_index
      << ",\"phase_execution_q_stop_index\":"
      << phase.stop_execution_q_index
      << ",\"phase_active_modulus_count\":" << phase.active.size()
      << ",\"parent_scheduled_t_index_rows\":"
      << schedule.header.t_row_count
      << ",\"phase_t_index_rows\":" << phase.t_row_count
      << ",\"first_q\":" << firstQ << ",\"last_q\":" << lastQ
      << ",\"modulus_count\":" << moduli << ",\"frame_count\":" << frames
      << ",\"slice_count\":" << slices << ",\"value_count\":" << values
      << ",\"radix2_butterflies\":" << butterflies
      << ",\"preparation_nanoseconds\":" << preparation
      << ",\"elapsed_nanoseconds\":" << elapsed
      << ",\"root_pool_accesses\":" << rootStats.accesses
      << ",\"root_pool_hits\":" << rootStats.hits
      << ",\"root_pool_misses\":" << rootStats.misses
      << ",\"root_pool_retained_entries\":" << retainedRootEntries
      << ",\"root_pool_retained_bytes\":" << rootStats.retainedBytes
      << ",\"root_pool_prepared_enclosures\":"
      << rootStats.preparedEnclosures
      << ",\"order_cache_accesses\":" << orderStats.accesses
      << ",\"order_cache_hits\":" << orderStats.hits
      << ",\"order_cache_misses\":" << orderStats.misses
      << ",\"order_cache_evictions\":" << orderStats.evictions
      << ",\"order_cache_uncached_misses\":"
      << orderStats.uncachedMisses
      << ",\"order_cache_retained_entries\":" << retainedOrderEntries
      << ",\"order_cache_retained_bytes\":" << orderStats.retainedBytes
      << ",\"order_cache_peak_retained_bytes\":"
      << orderStats.peakRetainedBytes
      << ",\"order_cache_prepared_enclosures\":"
      << orderStats.preparedEnclosures
      << ",\"total_prepared_enclosures\":"
      << orderStats.preparedEnclosures + rootStats.preparedEnclosures
      << ",\"cache_peak_total_retained_bytes\":"
      << orderStats.peakTotalRetainedBytes
      << ",\"order_cache_key_chain_sha256\":\""
      << sparkinterval::lowercase_hex(orderKeyDigest)
      << "\",\"root_pool_catalog_sha256\":\""
      << sparkinterval::lowercase_hex(rootCatalogDigest)
      << "\",\"retained_input_frames\":0,\"retained_output_frames\":0,"
      << "\"input_stream_sha256\":\""
      << sparkinterval::lowercase_hex(inputDigest)
      << "\",\"output_stream_sha256\":\""
      << sparkinterval::lowercase_hex(outputDigest) << "\"}\n";
  output.close();
  if (!output) {
    throw std::runtime_error(
        "could not write phase scheduled multi-q summary");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error(
        "could not publish phase scheduled multi-q summary");
  }
}

// Persistent source-shard service.  Unlike --framed-service, q may increase
// between frame groups.  The current q's work buffers are released at each
// transition.  Immutable radix-2 roots remain in their reserved pool, while
// order-specific directed chirps and transformed Bluestein kernels remain in
// the separate byte-bounded LRU above.  Thus a hit reuses the exact device
// bytes generated earlier; it does not approximate a transcendental.
int runMultiQFramedService(std::uint32_t maximumBatch,
                           std::uint64_t cacheCapacityBytes,
                           const char* summaryPath, std::uint32_t device,
                           const LoadedQOrderManifest* schedule = nullptr,
                           const PhaseScheduleCoverage* phase = nullptr) {
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error("strict target requires compute capability 9.0");
  }
#endif
  if (maximumBatch == 0U) {
    throw std::runtime_error("maximum batch count must be positive");
  }
  if (cacheCapacityBytes != kMultiQTotalCacheBytes) {
    throw std::runtime_error(
        "multi-q split cache requires the exact 512 MiB total budget");
  }
  if (phase != nullptr && schedule == nullptr) {
    throw std::runtime_error(
        "phase scheduled service requires its parent q-order manifest");
  }

  TwiddlePlanCache cache;
  std::unique_ptr<TransformPlan> transform;
  std::vector<std::uint32_t> orders;
  std::uint32_t currentQ = 0U;
  std::uint32_t firstQ = 0U;
  std::uint64_t moduli = 0U;
  std::uint64_t frames = 0U;
  std::uint64_t slices = 0U;
  std::uint64_t values = 0U;
  std::uint64_t butterflies = 0U;
  std::uint64_t preparation = 0U;
  std::uint64_t elapsedTotal = 0U;
  std::uint64_t expectedFirst = 0U;
  std::uint64_t denominator = 0U;
  std::uint64_t step = 0U;
  std::size_t scheduleIndex = 0U;
  std::uint64_t scheduledRowsForQ = 0U;
  std::uint64_t consumedScheduledRows = 0U;
  std::uint32_t scheduledFirstTIndex = 0U;
  bool haveProgression = false;
  sparkinterval::detail::Sha256 inputHasher;
  sparkinterval::detail::Sha256 outputHasher;
  std::signal(SIGPIPE, SIG_IGN);

  while (true) {
    LoadedInput input;
    if (!readInputFrame(std::cin, "multi-q persistent stdin", &input)) break;
    if (input.header.batch_count > maximumBatch) {
      throw std::runtime_error("multi-q frame exceeds batch capacity");
    }
    if (input.header.q != currentQ) {
      if (schedule != nullptr) {
        if (currentQ != 0U &&
            consumedScheduledRows != scheduledRowsForQ) {
          throw std::runtime_error(
              "scheduled multi-q stream ended a q before exact coverage");
        }
        const std::size_t expectedQCount =
            phase == nullptr ? schedule->execution.size()
                             : phase->active.size();
        if (scheduleIndex >= expectedQCount) {
          throw std::runtime_error(
              "scheduled multi-q stream has a trailing modulus");
        }
        const std::uint32_t expectedQ =
            phase == nullptr ? schedule->execution[scheduleIndex].q
                             : phase->active[scheduleIndex].q;
        if (input.header.q != expectedQ) {
          throw std::runtime_error(
              "scheduled multi-q q does not match its manifest");
        }
        if (phase == nullptr) {
          scheduledRowsForQ =
              schedule->execution[scheduleIndex].t_index_count;
          scheduledFirstTIndex = 0U;
        } else {
          scheduledRowsForQ =
              phase->active[scheduleIndex].tIndexCount();
          scheduledFirstTIndex =
              phase->active[scheduleIndex].first_t_index;
        }
        consumedScheduledRows = 0U;
        ++scheduleIndex;
      } else if (currentQ != 0U && input.header.q <= currentQ) {
          throw std::runtime_error(
              "multi-q frames are not grouped in strictly increasing q");
      }
      // Make the old q's cache references evictable before acquiring the new
      // plan.  The retained immutable entries themselves stay resident.
      transform.reset();
      orders = input.orders;
      const std::uint64_t groupOrder = orderProduct(orders);
      if (groupOrder >
          std::numeric_limits<std::uint64_t>::max() / maximumBatch) {
        throw std::runtime_error("multi-q service capacity overflow");
      }
      const auto start = std::chrono::steady_clock::now();
      transform = std::make_unique<TransformPlan>(
          orders, groupOrder * maximumBatch, &cache);
      const auto stop = std::chrono::steady_clock::now();
      preparation += static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start)
              .count());
      currentQ = input.header.q;
      if (firstQ == 0U) firstQ = currentQ;
      ++moduli;
      haveProgression = false;
    } else if (input.orders != orders) {
      throw std::runtime_error("multi-q component plan changed within q");
    }

    const std::uint64_t first =
        static_cast<std::uint64_t>(input.header.first_t_numerator);
    if (!haveProgression) {
      denominator = input.header.t_denominator;
      step = input.header.t_step_numerator;
      if (schedule != nullptr &&
          (first !=
               static_cast<std::uint64_t>(scheduledFirstTIndex) * 5ULL ||
           denominator != 64U || step != 5U)) {
        throw std::runtime_error(
            "scheduled multi-q source progression differs");
      }
      haveProgression = true;
    } else if (input.header.t_denominator != denominator ||
               input.header.t_step_numerator != step ||
               first != expectedFirst) {
      throw std::runtime_error(
          "multi-q frames are not one contiguous progression within q");
    }
    const std::uint64_t batch = input.header.batch_count;
    if (batch > (std::numeric_limits<std::uint64_t>::max() - first) / step) {
      throw std::runtime_error("multi-q ordinate progression overflow");
    }
    expectedFirst = first + batch * step;
    if (schedule != nullptr) {
      if (consumedScheduledRows > scheduledRowsForQ ||
          batch > scheduledRowsForQ - consumedScheduledRows) {
        throw std::runtime_error(
            "scheduled multi-q frame exceeds q row coverage");
      }
      consumedScheduledRows += batch;
    }

    inputHasher.update(&input.header, sizeof(input.header));
    inputHasher.update(input.values.data(),
                       input.values.size() * sizeof(input.values[0]));
    const std::uint64_t elapsed = transform->execute(&input.values);
    if (!std::all_of(input.values.begin(), input.values.end(), finiteOrdered)) {
      throw std::runtime_error("multi-q transform produced malformed interval");
    }
    const auto output = makeOutputHeader(input, elapsed);
    outputHasher.update(&output, sizeof(output));
    outputHasher.update(input.values.data(),
                        input.values.size() * sizeof(input.values[0]));
    writeAll(STDOUT_FILENO, &output, sizeof(output));
    writeAll(STDOUT_FILENO, input.values.data(),
             input.values.size() * sizeof(input.values[0]));
    ++frames;
    slices += batch;
    values += input.values.size();
    butterflies += input.butterflies;
    elapsedTotal += elapsed;
  }
  if (frames == 0U) {
    throw std::runtime_error("multi-q service received no input frames");
  }
  if (schedule != nullptr &&
      (consumedScheduledRows != scheduledRowsForQ ||
       scheduleIndex !=
           (phase == nullptr ? schedule->execution.size()
                             : phase->active.size()) ||
       moduli !=
           (phase == nullptr ? schedule->header.q_count
                             : phase->active.size()) ||
       slices !=
           (phase == nullptr ? schedule->header.t_row_count
                             : phase->t_row_count))) {
    throw std::runtime_error(
        "scheduled multi-q stream did not exactly cover its manifest");
  }
  // Drop the active q before reporting retained cache state.  This does not
  // evict anything; it only makes every retained entry independently owned by
  // the cache.
  transform.reset();
  const auto cacheKeyDigest = cache.finishKeyDigest();
  const auto inputDigest = inputHasher.finish();
  const auto outputDigest = outputHasher.finish();
  if (schedule == nullptr) {
    writeMultiQFramedSummary(
        summaryPath, maximumBatch, firstQ, currentQ, moduli, frames, slices,
        values, butterflies, preparation, elapsedTotal, cache.stats(),
        cache.retainedEntries(), cache.rootStats(),
        cache.retainedRootEntries(), cacheKeyDigest,
        cache.rootCatalogDigest(), inputDigest, outputDigest);
  } else if (phase == nullptr) {
    writeScheduledMultiQFramedSummary(
        summaryPath, maximumBatch, *schedule, firstQ, currentQ, moduli,
        frames, slices, values, butterflies, preparation, elapsedTotal,
        cache.stats(), cache.retainedEntries(), cache.rootStats(),
        cache.retainedRootEntries(), cacheKeyDigest,
        cache.rootCatalogDigest(), inputDigest, outputDigest);
  } else {
    writePhaseScheduledMultiQFramedSummary(
        summaryPath, maximumBatch, *schedule, *phase, firstQ, currentQ,
        moduli, frames, slices, values, butterflies, preparation,
        elapsedTotal, cache.stats(), cache.retainedEntries(),
        cache.rootStats(), cache.retainedRootEntries(), cacheKeyDigest,
        cache.rootCatalogDigest(), inputDigest, outputDigest);
  }
  return 0;
}

void consumeWithoutMaterializing(const std::string& consumer,
                                 const std::string& receipt,
                                 const da::OutputHeader& header,
                                 const std::vector<ComplexInterval>& values) {
  int descriptors[2];
  if (pipe(descriptors) != 0) throw std::runtime_error("could not create pipe");
  const pid_t child = fork();
  if (child < 0) {
    close(descriptors[0]);
    close(descriptors[1]);
    throw std::runtime_error("could not fork stream consumer");
  }
  if (child == 0) {
    if (dup2(descriptors[0], STDIN_FILENO) < 0) _exit(126);
    close(descriptors[0]);
    close(descriptors[1]);
    execl(consumer.c_str(), consumer.c_str(), receipt.c_str(),
          static_cast<char*>(nullptr));
    _exit(127);
  }
  close(descriptors[0]);
  try {
    writeAll(descriptors[1], &header, sizeof(header));
    writeAll(descriptors[1], values.data(), values.size() * sizeof(values[0]));
    close(descriptors[1]);
  } catch (...) {
    close(descriptors[1]);
    int ignored = 0;
    waitpid(child, &ignored, 0);
    throw;
  }
  int status = 0;
  if (waitpid(child, &status, 0) != child || !WIFEXITED(status) ||
      WEXITSTATUS(status) != 0) {
    throw std::runtime_error("stream consumer failed");
  }
}

void writeStreamSummary(const std::string& path, std::uint32_t q,
                        std::uint64_t batches, std::uint64_t values,
                        std::uint64_t butterflies, std::uint64_t preparation,
                        std::uint64_t elapsed,
                        const sparkinterval::Sha256Digest& root) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  std::ofstream output(temporary, std::ios::trunc);
  if (!output) throw std::runtime_error("could not create stream summary");
  output << "{\"kind\":\"sparkinterval.tg.dirichlet_allchars.stream.v1\","
         << "\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
         << "\"q\":" << q << ",\"batch_files\":" << batches
         << ",\"value_count\":" << values
         << ",\"radix2_butterflies\":" << butterflies
         << ",\"preparation_nanoseconds\":" << preparation
         << ",\"elapsed_nanoseconds\":" << elapsed
         << ",\"receipt_merkle_sha256\":\""
         << sparkinterval::lowercase_hex(root) << "\"}\n";
  output.close();
  if (!output) throw std::runtime_error("could not write stream summary");
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish stream summary");
  }
}

int runStream(const char* manifestPath, const char* consumerPath,
              const char* summaryPath, std::uint32_t device) {
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error("strict target requires compute capability 9.0");
  }
#endif
  const auto entries = readStreamManifest(manifestPath);
  std::uint32_t q = 0U;
  std::vector<std::uint32_t> orders;
  std::uint64_t maximumValues = 0U;
  for (const auto& entry : entries) {
    const auto header = loadInput(entry.input, false);
    if (q == 0U) {
      q = header.header.q;
      orders = header.orders;
    } else if (q != header.header.q || orders != header.orders) {
      throw std::runtime_error("one stream manifest must contain exactly one q");
    }
    maximumValues = std::max(maximumValues, header.header.value_count);
  }
  const auto preparationStart = std::chrono::steady_clock::now();
  const TransformPlan plan(orders, maximumValues);
  const auto preparationStop = std::chrono::steady_clock::now();
  const auto preparation = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          preparationStop - preparationStart).count());
  std::uint64_t totalValues = 0U;
  std::uint64_t totalButterflies = 0U;
  std::uint64_t totalElapsed = 0U;
  std::vector<sparkinterval::Sha256Digest> receiptDigests;
  std::signal(SIGPIPE, SIG_IGN);
  for (const auto& entry : entries) {
    auto input = loadInput(entry.input);
    const std::uint64_t elapsed = plan.execute(&input.values);
    const auto output = makeOutputHeader(input, elapsed);
    consumeWithoutMaterializing(consumerPath, entry.receipt, output,
                                input.values);
    receiptDigests.push_back(hashFile(entry.receipt));
    totalValues += input.values.size();
    totalButterflies += input.butterflies;
    totalElapsed += elapsed;
  }
  const auto root = merkleRoot(std::move(receiptDigests));
  writeStreamSummary(summaryPath, q, entries.size(), totalValues,
                     totalButterflies, preparation, totalElapsed, root);
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-allchars-bluestein-stream-v1\","
      "\"q\":%u,\"batch_files\":%zu,\"value_count\":%llu,"
      "\"radix2_butterflies\":%llu,\"preparation_nanoseconds\":%llu,"
      "\"elapsed_nanoseconds\":%llu,\"receipt_merkle_sha256\":\"%s\"}\n",
      q, entries.size(), static_cast<unsigned long long>(totalValues),
      static_cast<unsigned long long>(totalButterflies),
      static_cast<unsigned long long>(preparation),
      static_cast<unsigned long long>(totalElapsed),
      sparkinterval::lowercase_hex(root).c_str());
  return 0;
}

struct RollingPlan {
  std::uint32_t q = 0U;
  std::uint64_t firstNumerator = 0U;
  std::uint64_t denominator = 0U;
  std::uint64_t stepNumerator = 0U;
  std::uint64_t totalSlices = 0U;
  std::uint32_t batchSize = 0U;
};

RollingPlan readRollingPlan(const std::string& path) {
  std::ifstream input(path);
  std::string header;
  std::string row;
  if (!std::getline(input, header) || header != "TGDAFF_ROLLING_V1" ||
      !std::getline(input, row)) {
    throw std::runtime_error("invalid rolling plan header");
  }
  if (std::getline(input, header) && !header.empty()) {
    throw std::runtime_error("rolling plan must contain one parameter row");
  }
  std::vector<std::string> fields;
  std::size_t start = 0U;
  while (true) {
    const std::size_t separator = row.find('\t', start);
    fields.push_back(row.substr(start, separator - start));
    if (separator == std::string::npos) break;
    start = separator + 1U;
  }
  if (fields.size() != 6U) {
    throw std::runtime_error("rolling plan row must have six TSV fields");
  }
  RollingPlan plan;
  plan.q = static_cast<std::uint32_t>(parseUnsigned(fields[0].c_str(), "q"));
  plan.firstNumerator = parseUnsigned(fields[1].c_str(), "first numerator");
  plan.denominator = parseUnsigned(fields[2].c_str(), "denominator");
  plan.stepNumerator = parseUnsigned(fields[3].c_str(), "step numerator");
  plan.totalSlices = parseUnsigned(fields[4].c_str(), "total slices");
  plan.batchSize = static_cast<std::uint32_t>(
      parseUnsigned(fields[5].c_str(), "batch size"));
  if (plan.q < 3U || plan.q > da::kMaximumModulus || plan.denominator == 0U ||
      plan.stepNumerator == 0U || plan.totalSlices == 0U ||
      plan.batchSize == 0U ||
      plan.firstNumerator >
          static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    throw std::runtime_error("rolling plan parameter out of range");
  }
  return plan;
}

void runRollingProducer(const std::string& producer, const RollingPlan& plan,
                        std::uint64_t firstNumerator,
                        std::uint32_t batchCount,
                        const std::string& outputPath) {
  const std::string q = std::to_string(plan.q);
  const std::string first = std::to_string(firstNumerator);
  const std::string denominator = std::to_string(plan.denominator);
  const std::string step = std::to_string(plan.stepNumerator);
  const std::string count = std::to_string(batchCount);
  const pid_t child = fork();
  if (child < 0) throw std::runtime_error("could not fork rolling producer");
  if (child == 0) {
    execl(producer.c_str(), producer.c_str(), q.c_str(), first.c_str(),
          denominator.c_str(), step.c_str(), count.c_str(), outputPath.c_str(),
          static_cast<char*>(nullptr));
    _exit(127);
  }
  int status = 0;
  if (waitpid(child, &status, 0) != child || !WIFEXITED(status) ||
      WEXITSTATUS(status) != 0) {
    throw std::runtime_error("rolling producer failed");
  }
}

void writeRollingSummary(const std::string& path, const RollingPlan& plan,
                         std::uint64_t batches, std::uint64_t values,
                         std::uint64_t butterflies, std::uint64_t preparation,
                         std::uint64_t elapsed,
                         const sparkinterval::Sha256Digest& root) {
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  std::ofstream output(temporary, std::ios::trunc);
  if (!output) throw std::runtime_error("could not create rolling summary");
  output << "{\"kind\":\"sparkinterval.tg.dirichlet_allchars.rolling.v1\","
         << "\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
         << "\"q\":" << plan.q << ",\"batches\":" << batches
         << ",\"slices\":" << plan.totalSlices
         << ",\"value_count\":" << values
         << ",\"radix2_butterflies\":" << butterflies
         << ",\"preparation_nanoseconds\":" << preparation
         << ",\"elapsed_nanoseconds\":" << elapsed
         << ",\"retained_input_batches\":0,\"retained_output_batches\":0,"
         << "\"retained_consumer_receipts\":0,"
         << "\"receipt_merkle_sha256\":\""
         << sparkinterval::lowercase_hex(root) << "\"}\n";
  output.close();
  if (!output) throw std::runtime_error("could not write rolling summary");
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish rolling summary");
  }
}

int runRolling(const char* planPath, const char* producerPath,
               const char* consumerPath, const char* workDirectory,
               const char* summaryPath, std::uint32_t device) {
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error("strict target requires compute capability 9.0");
  }
#endif
  const RollingPlan rolling = readRollingPlan(planPath);
  const auto orders = canonicalOrders(rolling.q);
  const std::uint64_t groupOrder = orderProduct(orders);
  const std::uint64_t maximumValues = groupOrder * rolling.batchSize;
  std::filesystem::create_directories(workDirectory);
  const std::filesystem::path work =
      std::filesystem::absolute(std::filesystem::path(workDirectory));
  const std::string inputPath = (work / "rolling-input.bin").string();
  const std::string receiptPath = (work / "rolling-consumer-receipt.json").string();
  std::error_code ignored;
  std::filesystem::remove(inputPath, ignored);
  std::filesystem::remove(receiptPath, ignored);

  const auto preparationStart = std::chrono::steady_clock::now();
  const TransformPlan transform(orders, maximumValues);
  const auto preparationStop = std::chrono::steady_clock::now();
  const auto preparation = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          preparationStop - preparationStart).count());
  std::vector<sparkinterval::Sha256Digest> receipts;
  const std::uint64_t batchTotal =
      (rolling.totalSlices + rolling.batchSize - 1U) / rolling.batchSize;
  receipts.reserve(static_cast<std::size_t>(batchTotal));
  std::uint64_t slicesDone = 0U;
  std::uint64_t totalValues = 0U;
  std::uint64_t totalButterflies = 0U;
  std::uint64_t totalElapsed = 0U;
  std::signal(SIGPIPE, SIG_IGN);
  while (slicesDone < rolling.totalSlices) {
    const std::uint32_t count = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(rolling.batchSize,
                                rolling.totalSlices - slicesDone));
    const std::uint64_t first =
        rolling.firstNumerator + slicesDone * rolling.stepNumerator;
    if (first >
        static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
      throw std::runtime_error("rolling ordinate numerator overflow");
    }
    runRollingProducer(producerPath, rolling, first, count, inputPath);
    auto input = loadInput(inputPath);
    std::filesystem::remove(inputPath, ignored);
    if (input.header.q != rolling.q || input.header.batch_count != count ||
        input.header.first_t_numerator != static_cast<std::int64_t>(first) ||
        input.header.t_denominator != rolling.denominator ||
        input.header.t_step_numerator != rolling.stepNumerator) {
      throw std::runtime_error("rolling producer emitted the wrong batch identity");
    }
    const std::uint64_t elapsed = transform.execute(&input.values);
    const auto output = makeOutputHeader(input, elapsed);
    consumeWithoutMaterializing(consumerPath, receiptPath, output, input.values);
    receipts.push_back(hashFile(receiptPath));
    std::filesystem::remove(receiptPath, ignored);
    slicesDone += count;
    totalValues += input.values.size();
    totalButterflies += input.butterflies;
    totalElapsed += elapsed;
  }
  const auto root = merkleRoot(std::move(receipts));
  writeRollingSummary(summaryPath, rolling, batchTotal, totalValues,
                      totalButterflies, preparation, totalElapsed, root);
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-allchars-bluestein-rolling-v1\","
      "\"q\":%u,\"batches\":%llu,\"slices\":%llu,"
      "\"value_count\":%llu,\"radix2_butterflies\":%llu,"
      "\"preparation_nanoseconds\":%llu,\"elapsed_nanoseconds\":%llu,"
      "\"receipt_merkle_sha256\":\"%s\"}\n",
      rolling.q, static_cast<unsigned long long>(batchTotal),
      static_cast<unsigned long long>(rolling.totalSlices),
      static_cast<unsigned long long>(totalValues),
      static_cast<unsigned long long>(totalButterflies),
      static_cast<unsigned long long>(preparation),
      static_cast<unsigned long long>(totalElapsed),
      sparkinterval::lowercase_hex(root).c_str());
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 5 &&
        std::strcmp(
            argv[1], "--qualification-max-order-impulse") == 0) {
      const std::uint64_t device =
          parseUnsigned(argv[3], "qualification device");
      const std::uint64_t maximumSeconds =
          parseUnsigned(argv[4], "qualification maximum seconds");
      if (device > std::numeric_limits<std::uint32_t>::max() ||
          maximumSeconds > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "maximum-order qualification argument exceeds uint32");
      }
      return runMaximumOrderImpulseQualification(
          argv[2], static_cast<std::uint32_t>(device),
          static_cast<std::uint32_t>(maximumSeconds));
    }
    if (argc == 5 &&
        std::strcmp(
            argv[1], "--qualification-max-order-delta-one") == 0) {
      const std::uint64_t device =
          parseUnsigned(argv[3], "delta-one qualification device");
      const std::uint64_t maximumSeconds =
          parseUnsigned(argv[4], "delta-one qualification maximum seconds");
      if (device > std::numeric_limits<std::uint32_t>::max() ||
          maximumSeconds > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "maximum-order delta-one qualification argument exceeds uint32");
      }
      return runMaximumOrderDeltaOneQualification(
          argv[2], static_cast<std::uint32_t>(device),
          static_cast<std::uint32_t>(maximumSeconds));
    }
    if (argc == 6 &&
        std::strcmp(argv[1], "--dump-fft-roots") == 0) {
      const std::uint64_t length =
          parseUnsigned(argv[3], "FFT-root length");
      if (length > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("FFT-root length exceeds uint32");
      }
      return runFftRootDump(
          argv[2], static_cast<std::uint32_t>(length),
          parseChirpSign(argv[4]), argv[5]);
    }
    if (argc == 6 && std::strcmp(argv[1], "--dump-chirp") == 0) {
      const std::uint64_t length = parseUnsigned(argv[3], "chirp length");
      if (length > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("chirp length exceeds uint32");
      }
      return runChirpDump(
          argv[2], static_cast<std::uint32_t>(length),
          parseChirpSign(argv[4]), argv[5]);
    }
    if (argc == 15 &&
        std::strcmp(
            argv[1],
            "--bounded-resident-completed-sign-arb-recurrence-handoff") ==
            0) {
      const auto rootSha256 =
          parseLowercaseSha256(argv[4], "root artifact SHA-256");
      const auto expectedProducer = parseLowercaseSha256(
          argv[5], "expected factor producer SHA-256");
      const RecurrenceArtifactPaths recurrence{
          argv[6],
          parseLowercaseSha256(
              argv[7], "gamma artifact SHA-256"),
          argv[8],
          parseLowercaseSha256(
              argv[9], "step artifact SHA-256"),
          argv[10],
          parseLowercaseSha256(
              argv[11], "checkpoint artifact SHA-256"),
      };
      const std::uint64_t device = parseUnsigned(argv[14], "device");
      if (device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("device is outside uint32");
      }
      return runBoundedResidentCompletedSignHandoff(
          argv[2], argv[3], rootSha256, nullptr,
          sparkinterval::Sha256Digest{}, argv[12], argv[13],
          static_cast<std::uint32_t>(device), &recurrence,
          &expectedProducer, true);
    }
    if (argc == 14 &&
        std::strcmp(
            argv[1],
            "--bounded-resident-completed-sign-recurrence-handoff") ==
            0) {
      const auto rootSha256 =
          parseLowercaseSha256(argv[4], "root artifact SHA-256");
      const RecurrenceArtifactPaths recurrence{
          argv[5],
          parseLowercaseSha256(
              argv[6], "gamma artifact SHA-256"),
          argv[7],
          parseLowercaseSha256(
              argv[8], "step artifact SHA-256"),
          argv[9],
          parseLowercaseSha256(
              argv[10], "checkpoint artifact SHA-256"),
      };
      const std::uint64_t device = parseUnsigned(argv[13], "device");
      if (device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("device is outside uint32");
      }
      const auto expectedProducer = parseLowercaseSha256(
          "781293f8d433537a7d3b9bc10ef7c9f757c4fab984cd46e98"
          "fde5dfcdd2c8d84",
          "bounded synthetic factor producer SHA-256");
      return runBoundedResidentCompletedSignHandoff(
          argv[2], argv[3], rootSha256, nullptr,
          sparkinterval::Sha256Digest{}, argv[11], argv[12],
          static_cast<std::uint32_t>(device), &recurrence,
          &expectedProducer);
    }
    if (argc == 10 &&
        std::strcmp(
            argv[1],
            "--bounded-resident-completed-sign-handoff") == 0) {
      const auto rootSha256 =
          parseLowercaseSha256(argv[4], "root artifact SHA-256");
      const auto factorSha256 =
          parseLowercaseSha256(argv[6], "factor fixture SHA-256");
      const std::uint64_t device = parseUnsigned(argv[9], "device");
      if (device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("device is outside uint32");
      }
      return runBoundedResidentCompletedSignHandoff(
          argv[2], argv[3], rootSha256, argv[5], factorSha256,
          argv[7], argv[8], static_cast<std::uint32_t>(device));
    }
    if (argc == 12 &&
        (std::strcmp(
             argv[1], "--phase-scheduled-multiq-framed-service") == 0 ||
         std::strcmp(
             argv[1],
             "--bounded-phase-scheduled-multiq-framed-service") == 0)) {
      const bool bounded =
          std::strcmp(
              argv[1],
              "--bounded-phase-scheduled-multiq-framed-service") == 0;
      const std::uint64_t maximumBatch =
          parseUnsigned(argv[2], "maximum batch count");
      const std::uint64_t cacheMiB =
          parseUnsigned(argv[3], "total split-cache MiB");
      const auto phasePlan =
          parseLowercaseSha256(argv[5], "phase plan SHA-256");
      const std::uint64_t firstT =
          parseUnsigned(argv[6], "phase first t index");
      const std::uint64_t stopT =
          parseUnsigned(argv[7], "phase stop t index");
      const std::uint64_t startQ =
          parseUnsigned(argv[8], "phase execution q start index");
      const std::uint64_t stopQ =
          parseUnsigned(argv[9], "phase execution q stop index");
      const std::uint64_t device = parseUnsigned(argv[11], "device");
      if (maximumBatch > std::numeric_limits<std::uint32_t>::max() ||
          cacheMiB > std::numeric_limits<std::uint64_t>::max() /
                         (1024ULL * 1024ULL) ||
          firstT > std::numeric_limits<std::uint32_t>::max() ||
          stopT > std::numeric_limits<std::uint32_t>::max() ||
          startQ > std::numeric_limits<std::uint32_t>::max() ||
          stopQ > std::numeric_limits<std::uint32_t>::max() ||
          device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "phase scheduled multi-q argument is outside its fixed width");
      }
      if (cacheMiB != 512ULL) {
        throw std::runtime_error(
            "phase scheduled multi-q split cache requires "
            "TOTAL_CACHE_MIB=512");
      }
      const auto schedule = loadQOrderManifest(argv[4]);
      if ((!bounded &&
           schedule.header.classification != kQOrderFullSource) ||
          (bounded &&
           schedule.header.classification != kQOrderBounded)) {
        throw std::runtime_error(
            "phase scheduled multi-q mode and manifest classification "
            "differ");
      }
      const auto phase = makePhaseScheduleCoverage(
          schedule, phasePlan, static_cast<std::uint32_t>(firstT),
          static_cast<std::uint32_t>(stopT),
          static_cast<std::uint32_t>(startQ),
          static_cast<std::uint32_t>(stopQ));
      return runMultiQFramedService(
          static_cast<std::uint32_t>(maximumBatch),
          cacheMiB * 1024ULL * 1024ULL, argv[10],
          static_cast<std::uint32_t>(device), &schedule, &phase);
    }
    if (argc == 7 &&
        (std::strcmp(argv[1], "--scheduled-multiq-framed-service") == 0 ||
         std::strcmp(argv[1],
                     "--bounded-scheduled-multiq-framed-service") == 0)) {
      const bool bounded =
          std::strcmp(
              argv[1], "--bounded-scheduled-multiq-framed-service") == 0;
      const std::uint64_t maximumBatch =
          parseUnsigned(argv[2], "maximum batch count");
      const std::uint64_t cacheMiB =
          parseUnsigned(argv[3], "total split-cache MiB");
      const std::uint64_t device = parseUnsigned(argv[6], "device");
      if (maximumBatch > std::numeric_limits<std::uint32_t>::max() ||
          cacheMiB > std::numeric_limits<std::uint64_t>::max() /
                         (1024ULL * 1024ULL) ||
          device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "scheduled multi-q service argument is outside its fixed width");
      }
      if (cacheMiB != 512ULL) {
        throw std::runtime_error(
            "scheduled multi-q split cache requires TOTAL_CACHE_MIB=512");
      }
      const auto schedule = loadQOrderManifest(argv[4]);
      if ((!bounded &&
           schedule.header.classification != kQOrderFullSource) ||
          (bounded &&
           schedule.header.classification != kQOrderBounded)) {
        throw std::runtime_error(
            "scheduled multi-q mode and manifest classification differ");
      }
      return runMultiQFramedService(
          static_cast<std::uint32_t>(maximumBatch),
          cacheMiB * 1024ULL * 1024ULL, argv[5],
          static_cast<std::uint32_t>(device), &schedule);
    }
    if (argc == 6 &&
        std::strcmp(argv[1], "--multiq-framed-service") == 0) {
      const std::uint64_t maximumBatch =
          parseUnsigned(argv[2], "maximum batch count");
      const std::uint64_t cacheMiB =
          parseUnsigned(argv[3], "total split-cache MiB");
      const std::uint64_t device = parseUnsigned(argv[5], "device");
      if (maximumBatch > std::numeric_limits<std::uint32_t>::max() ||
          cacheMiB > std::numeric_limits<std::uint64_t>::max() /
                         (1024ULL * 1024ULL) ||
          device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error(
            "multi-q framed service argument is outside its fixed width");
      }
      if (cacheMiB != 512ULL) {
        throw std::runtime_error(
            "multi-q split cache requires TOTAL_CACHE_MIB=512");
      }
      return runMultiQFramedService(
          static_cast<std::uint32_t>(maximumBatch),
          cacheMiB * 1024ULL * 1024ULL, argv[4],
          static_cast<std::uint32_t>(device));
    }
    if (argc == 6 && std::strcmp(argv[1], "--framed-service") == 0) {
      const std::uint64_t q = parseUnsigned(argv[2], "q");
      const std::uint64_t maximumBatch =
          parseUnsigned(argv[3], "maximum batch count");
      const std::uint64_t device = parseUnsigned(argv[5], "device");
      if (q > std::numeric_limits<std::uint32_t>::max() ||
          maximumBatch > std::numeric_limits<std::uint32_t>::max() ||
          device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("framed service argument exceeds uint32");
      }
      return runFramedService(static_cast<std::uint32_t>(q),
                              static_cast<std::uint32_t>(maximumBatch),
                              argv[4], static_cast<std::uint32_t>(device));
    }
    if (argc == 8 && std::strcmp(argv[1], "--rolling") == 0) {
      return runRolling(argv[2], argv[3], argv[4], argv[5], argv[6],
                        static_cast<std::uint32_t>(
                            parseUnsigned(argv[7], "device")));
    }
    if (argc == 6 && std::strcmp(argv[1], "--stream") == 0) {
      return runStream(argv[2], argv[3], argv[4],
                       static_cast<std::uint32_t>(
                           parseUnsigned(argv[5], "device")));
    }
    if (argc < 3 || argc > 5) {
      throw std::runtime_error(
          "usage: runner INPUT OUTPUT [DEVICE=0] [ITERATIONS=1]\n"
          "   or: runner --bounded-resident-completed-sign-handoff"
          " INPUT ROOT ROOT_SHA FACTOR FACTOR_SHA STATE SUMMARY DEVICE\n"
          "   or: runner --bounded-resident-completed-sign-recurrence-handoff"
          " INPUT ROOT ROOT_SHA GAMMA GAMMA_SHA STEPS STEP_SHA"
          " CHECKPOINTS CHECKPOINT_SHA STATE SUMMARY DEVICE\n"
          "   or: runner --bounded-resident-completed-sign-arb-recurrence-handoff"
          " INPUT ROOT ROOT_SHA PRODUCER_SHA GAMMA GAMMA_SHA STEPS STEP_SHA"
          " CHECKPOINTS CHECKPOINT_SHA STATE SUMMARY DEVICE\n"
          "   or: runner --scheduled-multiq-framed-service MAX_BATCH 512"
          " SCHEDULE SUMMARY DEVICE\n"
          "   or: runner --bounded-scheduled-multiq-framed-service"
          " MAX_BATCH 512 SCHEDULE SUMMARY DEVICE\n"
          "   or: runner --multiq-framed-service MAX_BATCH 512 SUMMARY DEVICE\n"
          "   or: runner --framed-service Q MAX_BATCH SUMMARY DEVICE\n"
          "   or: runner --qualification-max-order-impulse"
          " OUTPUT DEVICE MAX_SECONDS\n"
          "   or: runner --qualification-max-order-delta-one"
          " OUTPUT DEVICE MAX_SECONDS\n"
          "   or: runner --dump-fft-roots"
          " (recurrence|conjugate|direct) LENGTH SIGN OUTPUT\n"
          "   or: runner --dump-chirp (recurrence|conjugate|direct)"
          " LENGTH SIGN OUTPUT\n"
          "   or: runner --stream MANIFEST CONSUMER SUMMARY DEVICE\n"
          "   or: runner --rolling PLAN PRODUCER CONSUMER WORKDIR SUMMARY DEVICE");
    }
    const std::uint64_t rawDevice =
        argc >= 4 ? parseUnsigned(argv[3], "device") : 0U;
    if (rawDevice > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("device exceeds uint32");
    }
    const std::uint32_t device = static_cast<std::uint32_t>(rawDevice);
    const std::uint64_t rawIterations =
        argc >= 5 ? parseUnsigned(argv[4], "iterations") : 1U;
    if (rawIterations > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("iterations exceeds uint32");
    }
    const std::uint32_t iterations =
        static_cast<std::uint32_t>(rawIterations);
    if (iterations == 0U) throw std::runtime_error("iterations must be positive");
    selectCudaDevice(device);

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) throw std::runtime_error("could not open input");
    const da::InputHeader header = readObject<da::InputHeader>(input, "header");
    if (std::memcmp(header.magic, da::kInputMagic, 8) != 0 ||
        header.version != da::kFormatVersion || header.reserved0 != 0U ||
        header.batch_count == 0U || header.t_denominator == 0U ||
        header.first_t_numerator < 0 || header.t_step_numerator == 0U) {
      throw std::runtime_error("invalid input header");
    }
    const auto orders = canonicalOrders(header.q);
    const std::uint64_t total = orderProduct(orders);
    const std::uint64_t valueCount = total * header.batch_count;
    if (header.component_count != orders.size() || header.group_order != total ||
        header.value_count != valueCount) {
      throw std::runtime_error("input group identity does not match q");
    }
    std::vector<ComplexInterval> values(valueCount);
    input.read(reinterpret_cast<char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(values[0])));
    if (!input) throw std::runtime_error("truncated input values");
    if (input.peek() != std::ifstream::traits_type::eof()) {
      throw std::runtime_error("trailing input bytes");
    }
    if (!std::all_of(values.begin(), values.end(), finiteOrdered)) {
      throw std::runtime_error("input contains malformed interval");
    }

    std::uint64_t butterflies = 0U;
    std::uint64_t stride = 1U;
    for (const auto length : orders) {
      const std::uint64_t lines = valueCount / length;
      const std::uint32_t convolution = nextPowerOfTwo(2ULL * length - 1ULL);
      butterflies += (1ULL + 2ULL * lines) * (convolution / 2ULL) *
                     integerLog2(convolution);
      stride *= length;
    }

    const auto preparationStart = std::chrono::steady_clock::now();
    const TransformPlan plan(orders, valueCount);
    const auto preparationStop = std::chrono::steady_clock::now();
    const auto preparationNanoseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            preparationStop - preparationStart).count());
    std::uint64_t elapsed = 0U;
    const std::vector<ComplexInterval> originalValues = values;
    for (std::uint32_t iteration = 0; iteration < iterations; ++iteration) {
      values = originalValues;
      elapsed += plan.execute(&values);
    }
    if (!std::all_of(values.begin(), values.end(), finiteOrdered)) {
      throw std::runtime_error("transform produced malformed interval");
    }

    da::OutputHeader output{};
    std::memcpy(output.magic, da::kOutputMagic, 8);
    output.version = da::kFormatVersion;
    output.q = header.q;
    output.component_count = header.component_count;
    output.batch_count = header.batch_count;
    output.group_order = total;
    output.value_count = valueCount;
    output.radix2_butterflies = butterflies;
    output.elapsed_nanoseconds = elapsed / iterations;
    writeAtomically(argv[2], output, values);
    std::printf(
        "{\"algorithm\":\"platt-dirichlet-allchars-bluestein-v1\","
        "\"q\":%u,\"group_order\":%llu,\"batch_count\":%u,"
        "\"value_count\":%llu,\"components\":%zu,"
        "\"radix2_butterflies\":%llu,\"preparation_nanoseconds\":%llu,"
        "\"elapsed_nanoseconds\":%llu}\n",
        header.q, static_cast<unsigned long long>(total), header.batch_count,
        static_cast<unsigned long long>(valueCount), orders.size(),
        static_cast<unsigned long long>(butterflies),
        static_cast<unsigned long long>(preparationNanoseconds),
        static_cast<unsigned long long>(output.elapsed_nanoseconds));
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "Dirichlet all-character transform error: %s\n",
                 error.what());
    return 2;
  }
}

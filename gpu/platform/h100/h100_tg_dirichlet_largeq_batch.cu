// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-scalable, q-persistent large-modulus residue batch.  This program
// deliberately contains no device transcendental operation.  It consumes
// externally certified boxes and performs only directed binary64 interval
// Taylor reconstruction, q^(-s) multiplication, and finite-recovery addback.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_dirichlet_largeq_batch.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <system_error>
#include <tuple>
#include <unistd.h>
#include <utility>
#include <vector>

namespace lb = sparkinterval::tg::dirichlet_largeq_batch;
namespace da = sparkinterval::tg::dirichlet_allchars;
namespace dl = sparkinterval::tg::dirichlet_lattice;

namespace {

using dl::ComplexInterval;
using dl::RealInterval;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

__device__ __forceinline__ RealInterval add(RealInterval x, RealInterval y) {
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
}

__device__ __forceinline__ RealInterval sub(RealInterval x, RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval mul(RealInterval x, RealInterval y) {
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

__device__ __forceinline__ RealInterval dividePositive(RealInterval x,
                                                        double denominator) {
  return {__ddiv_rd(x.lo, denominator), __ddiv_ru(x.hi, denominator)};
}

__device__ __forceinline__ RealInterval rationalNonnegative(
    std::uint64_t numerator, std::uint64_t denominator) {
  const double n = static_cast<double>(numerator);
  const double d = static_cast<double>(denominator);
  return {__ddiv_rd(n, d), __ddiv_ru(n, d)};
}

__device__ __forceinline__ ComplexInterval cadd(ComplexInterval x,
                                                 ComplexInterval y) {
  return {add(x.re, y.re), add(x.im, y.im)};
}

__device__ __forceinline__ ComplexInterval cmul(ComplexInterval x,
                                                 ComplexInterval y) {
  return {sub(mul(x.re, y.re), mul(x.im, y.im)),
          add(mul(x.re, y.im), mul(x.im, y.re))};
}

__device__ __forceinline__ ComplexInterval cscale(ComplexInterval x,
                                                   RealInterval y) {
  return {mul(x.re, y), mul(x.im, y)};
}

__device__ __forceinline__ ComplexInterval cdividePositive(
    ComplexInterval x, double denominator) {
  return {dividePositive(x.re, denominator),
          dividePositive(x.im, denominator)};
}

__global__ void reconstructComposeKernel(
    lb::InputHeader header, const lb::ResidueDescriptor* descriptors,
    const lb::FrameFactor* factors, const ComplexInterval* lattices,
    const lb::CertifiedResidueBox* certified, ComplexInterval* output) {
  const std::uint64_t stride =
      static_cast<std::uint64_t>(blockDim.x) * gridDim.x;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < header.value_count; flat += stride) {
    const std::uint32_t frame =
        static_cast<std::uint32_t>(flat / header.group_order);
    const std::uint64_t position = flat % header.group_order;
    const lb::ResidueDescriptor descriptor = descriptors[position];
    const std::uint64_t tNumerator =
        static_cast<std::uint64_t>(header.first_t_numerator) +
        static_cast<std::uint64_t>(frame) * header.t_step_numerator;

    const RealInterval aOverQ =
        rationalNonnegative(descriptor.a, header.q);
    const RealInterval rowOverD =
        rationalNonnegative(descriptor.lattice_row, dl::kLatticeRows);
    const RealInterval minusDelta = sub(rowOverD, aOverQ);
    // validateHeader fixes the source denominator to 64 and bounds the
    // numerator by 2^53.  Scaling that exactly represented integer by the
    // binary power 2^-6 is exact, so both directed division endpoints from
    // rationalNonnegative(tNumerator, 64) are this same binary64 value.
    const double tPoint =
        static_cast<double>(tNumerator) * 0x1p-6;
    const RealInterval t{tPoint, tPoint};
    ComplexInterval power{{1.0, 1.0}, {0.0, 0.0}};
    ComplexInterval zeta{{0.0, 0.0}, {0.0, 0.0}};
    const std::uint64_t latticeBase =
        static_cast<std::uint64_t>(frame) * dl::kLatticeCellCount;
    for (std::uint32_t column = 0; column <= dl::kTaylorDegree; ++column) {
      const std::uint64_t latticeIndex =
          latticeBase +
          (static_cast<std::uint64_t>(descriptor.lattice_row) - 1U) *
              dl::kTaylorColumns +
          column;
      zeta = cadd(zeta, cmul(power, lattices[latticeIndex]));
      if (column != dl::kTaylorDegree) {
        const ComplexInterval sPlusColumn{
            {static_cast<double>(column) + 0.5,
             static_cast<double>(column) + 0.5},
            t};
        power = cdividePositive(
            cscale(cmul(power, sPlusColumn), minusDelta),
            static_cast<double>(column + 1U));
      }
    }
    const lb::CertifiedResidueBox box = certified[flat];
    zeta.re.lo = __dsub_rd(zeta.re.lo, box.taylor_tail_radius_hi);
    zeta.re.hi = __dadd_ru(zeta.re.hi, box.taylor_tail_radius_hi);
    zeta.im.lo = __dsub_rd(zeta.im.lo, box.taylor_tail_radius_hi);
    zeta.im.hi = __dadd_ru(zeta.im.hi, box.taylor_tail_radius_hi);
    output[flat] = cadd(cmul(factors[frame].q_to_the_minus_s, zeta),
                        box.finite_recovery);
  }
}

bool finiteOrdered(const RealInterval& value) {
  return std::isfinite(value.lo) && std::isfinite(value.hi) &&
         value.lo <= value.hi;
}

bool finiteOrdered(const ComplexInterval& value) {
  return finiteOrdered(value.re) && finiteOrdered(value.im);
}

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

std::uint64_t powMod(std::uint64_t base, std::uint64_t exponent,
                     std::uint64_t modulus) {
  std::uint64_t answer = 1U;
  base %= modulus;
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) answer = (answer * base) % modulus;
    exponent >>= 1U;
    if (exponent != 0U) base = (base * base) % modulus;
  }
  return answer;
}

std::uint64_t inverseMod(std::uint64_t value, std::uint64_t modulus) {
  std::int64_t oldR = static_cast<std::int64_t>(value);
  std::int64_t r = static_cast<std::int64_t>(modulus);
  std::int64_t oldS = 1;
  std::int64_t s = 0;
  while (r != 0) {
    const std::int64_t quotient = oldR / r;
    std::tie(oldR, r) = std::pair{r, oldR - quotient * r};
    std::tie(oldS, s) = std::pair{s, oldS - quotient * s};
  }
  if (oldR != 1) throw std::runtime_error("noninvertible CRT cofactor");
  oldS %= static_cast<std::int64_t>(modulus);
  if (oldS < 0) oldS += static_cast<std::int64_t>(modulus);
  return static_cast<std::uint64_t>(oldS);
}

std::vector<std::uint32_t> distinctPrimeDivisors(std::uint32_t value) {
  std::vector<std::uint32_t> answer;
  for (std::uint32_t p = 2U;
       static_cast<std::uint64_t>(p) * p <= value; ++p) {
    if (value % p != 0U) continue;
    answer.push_back(p);
    while (value % p == 0U) value /= p;
  }
  if (value > 1U) answer.push_back(value);
  return answer;
}

std::uint32_t leastPrimitiveRoot(std::uint32_t modulus,
                                 std::uint32_t prime) {
  const std::uint32_t order = modulus - modulus / prime;
  const auto divisors = distinctPrimeDivisors(order);
  for (std::uint32_t candidate = 2U; candidate < modulus; ++candidate) {
    if (std::gcd(candidate, modulus) != 1U) continue;
    bool primitive = true;
    for (const auto divisor : divisors) {
      if (powMod(candidate, order / divisor, modulus) == 1U) {
        primitive = false;
        break;
      }
    }
    if (primitive) return candidate;
  }
  throw std::runtime_error("cannot reconstruct canonical primitive root");
}

struct Component {
  std::uint32_t generator;
  std::uint32_t order;
};

struct Factor {
  std::uint32_t modulus;
  std::vector<Component> components;
};

std::vector<Factor> canonicalFactors(std::uint32_t q) {
  std::vector<Factor> answer;
  std::uint32_t remaining = q;
  for (std::uint32_t prime = 2U;
       static_cast<std::uint64_t>(prime) * prime <= remaining; ++prime) {
    if (remaining % prime != 0U) continue;
    std::uint32_t exponent = 0U;
    std::uint32_t modulus = 1U;
    do {
      remaining /= prime;
      modulus *= prime;
      ++exponent;
    } while (remaining % prime == 0U);
    Factor factor{modulus, {}};
    if (prime == 2U) {
      if (exponent == 2U) factor.components.push_back({3U, 2U});
      if (exponent > 2U) {
        factor.components.push_back({modulus - 1U, 2U});
        factor.components.push_back({5U, 1U << (exponent - 2U)});
      }
    } else {
      factor.components.push_back(
          {leastPrimitiveRoot(modulus, prime), modulus - modulus / prime});
    }
    answer.push_back(std::move(factor));
  }
  if (remaining > 1U) {
    answer.push_back(Factor{
        remaining, {{leastPrimitiveRoot(remaining, remaining), remaining - 1U}}});
  }
  return answer;
}

std::vector<lb::ResidueDescriptor> canonicalDescriptors(std::uint32_t q) {
  const auto factors = canonicalFactors(q);
  std::vector<std::uint32_t> orders;
  for (const auto& factor : factors) {
    for (const auto& component : factor.components) {
      orders.push_back(component.order);
    }
  }
  std::uint64_t groupOrder = 1U;
  for (const auto order : orders) groupOrder *= order;
  std::vector<lb::ResidueDescriptor> answer;
  answer.reserve(static_cast<std::size_t>(groupOrder));
  for (std::uint64_t ordinal = 0; ordinal < groupOrder; ++ordinal) {
    std::vector<std::uint32_t> coordinates;
    coordinates.reserve(orders.size());
    std::uint64_t remaining = ordinal;
    for (const auto order : orders) {
      coordinates.push_back(static_cast<std::uint32_t>(remaining % order));
      remaining /= order;
    }
    if (remaining != 0U) throw std::runtime_error("CRT ordinal overflow");
    std::uint64_t residue = 0U;
    std::size_t coordinate = 0U;
    for (const auto& factor : factors) {
      std::uint64_t local = 1U;
      for (const auto& component : factor.components) {
        local = (local * powMod(component.generator, coordinates[coordinate],
                                factor.modulus)) % factor.modulus;
        ++coordinate;
      }
      const std::uint64_t cofactor = q / factor.modulus;
      residue = (residue + local * cofactor *
                             inverseMod(cofactor % factor.modulus,
                                        factor.modulus)) % q;
    }
    if (coordinate != coordinates.size() || residue == 0U || residue >= q) {
      throw std::runtime_error("canonical CRT reconstruction failed");
    }
    answer.push_back({static_cast<std::uint32_t>(residue),
                      dl::canonical_lattice_row(
                          q, static_cast<std::uint32_t>(residue))});
  }
  std::vector<std::uint32_t> residues;
  residues.reserve(answer.size());
  for (const auto descriptor : answer) residues.push_back(descriptor.a);
  std::sort(residues.begin(), residues.end());
  std::vector<std::uint32_t> expected;
  for (std::uint32_t a = 1U; a < q; ++a) {
    if (std::gcd(a, q) == 1U) expected.push_back(a);
  }
  if (residues != expected) {
    throw std::runtime_error("CRT order is not exactly the unit group");
  }
  return answer;
}

std::vector<std::uint32_t> canonicalOrders(std::uint32_t q) {
  std::vector<std::uint32_t> orders;
  for (const auto& factor : canonicalFactors(q)) {
    for (const auto& component : factor.components) {
      orders.push_back(component.order);
    }
  }
  return orders;
}

std::uint64_t maximumTIndex(std::uint32_t q) {
  const std::uint64_t additive =
      (q % 2U == 0U) ? 75000000ULL : 37500000ULL;
  const std::uint64_t heightNumerator =
      std::max<std::uint64_t>(100000000ULL, 200ULL * q + additive);
  return heightNumerator * lb::kSourceTDenominator /
         (static_cast<std::uint64_t>(q) * lb::kSourceTStepNumerator);
}

template <typename T>
void readVector(std::istream& input, std::vector<T>* values,
                std::uint64_t count, const char* label,
                sparkinterval::detail::Sha256* digest = nullptr) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T) ||
      count * sizeof(T) >
          static_cast<std::uint64_t>(std::numeric_limits<std::streamsize>::max())) {
    throw std::runtime_error(std::string(label) + " array is too large");
  }
  values->resize(static_cast<std::size_t>(count));
  const auto bytes = static_cast<std::streamsize>(values->size() * sizeof(T));
  input.read(reinterpret_cast<char*>(values->data()), bytes);
  if (!input) throw std::runtime_error(std::string("truncated ") + label);
  if (digest != nullptr) digest->update(values->data(), static_cast<std::size_t>(bytes));
}

struct LoadedFrame {
  lb::InputHeader header{};
  std::vector<lb::ResidueDescriptor> descriptors;
  std::vector<lb::FrameFactor> factors;
  std::vector<ComplexInterval> lattices;
  std::vector<lb::CertifiedResidueBox> certified;
  std::string inputSha256;
};

void validateHeader(const lb::InputHeader& header,
                    const std::vector<lb::ResidueDescriptor>& expected,
                    std::uint32_t maximumBatch) {
  const auto orders = canonicalOrders(header.q);
  const std::uint64_t groupOrder = expected.size();
  if (std::memcmp(header.magic, lb::kInputMagic, 8) != 0 ||
      header.version != lb::kFormatVersion ||
      header.q < lb::kMinimumModulus || header.q > lb::kMaximumModulus ||
      header.lattice_rows != dl::kLatticeRows ||
      header.taylor_degree != dl::kTaylorDegree ||
      header.component_count != orders.size() || header.batch_count == 0U ||
      header.batch_count > maximumBatch ||
      header.batch_count > lb::kMaximumBatchCount || header.m == 0U ||
      header.reserved0 != 0U || header.reserved1 != 0U ||
      header.group_order != groupOrder || header.first_t_numerator < 0 ||
      static_cast<std::uint64_t>(header.first_t_numerator) %
              lb::kSourceTStepNumerator !=
          0U ||
      header.t_denominator != lb::kSourceTDenominator ||
      header.t_step_numerator != lb::kSourceTStepNumerator ||
      header.lattice_cell_count !=
          static_cast<std::uint64_t>(header.batch_count) *
              dl::kLatticeCellCount ||
      header.value_count !=
          static_cast<std::uint64_t>(header.batch_count) * groupOrder) {
    throw std::runtime_error("invalid large-q batch input header");
  }
  const std::uint64_t lastT =
      static_cast<std::uint64_t>(header.first_t_numerator) +
      static_cast<std::uint64_t>(header.batch_count - 1U) *
          header.t_step_numerator;
  if (lastT > (1ULL << 53U) ||
      lastT > maximumTIndex(header.q) * lb::kSourceTStepNumerator) {
    throw std::runtime_error("batch extends beyond the exact source grid");
  }
}

bool readFrame(std::istream& input, LoadedFrame* loaded,
               std::uint32_t maximumBatch,
               const std::vector<lb::ResidueDescriptor>* cachedExpected = nullptr) {
  input.read(reinterpret_cast<char*>(&loaded->header),
             sizeof(loaded->header));
  if (!input) {
    if (input.eof() && input.gcount() == 0) return false;
    throw std::runtime_error("truncated large-q batch header");
  }
  sparkinterval::detail::Sha256 digest;
  digest.update(&loaded->header, sizeof(loaded->header));
  std::vector<lb::ResidueDescriptor> reconstructed;
  if (cachedExpected == nullptr) {
    reconstructed = canonicalDescriptors(loaded->header.q);
    cachedExpected = &reconstructed;
  }
  const auto& expected = *cachedExpected;
  validateHeader(loaded->header, expected, maximumBatch);
  readVector(input, &loaded->descriptors, loaded->header.group_order,
             "residue descriptors", &digest);
  readVector(input, &loaded->factors, loaded->header.batch_count,
             "frame factors", &digest);
  readVector(input, &loaded->lattices, loaded->header.lattice_cell_count,
             "lattice cells", &digest);
  readVector(input, &loaded->certified, loaded->header.value_count,
             "certified residue boxes", &digest);
  if (loaded->descriptors != expected) {
    throw std::runtime_error("residue descriptors are not canonical CRT order");
  }
  for (const auto& factor : loaded->factors) {
    if (!finiteOrdered(factor.q_to_the_minus_s)) {
      throw std::runtime_error("malformed q^(-s) factor interval");
    }
  }
  for (const auto& lattice : loaded->lattices) {
    if (!finiteOrdered(lattice)) {
      throw std::runtime_error("malformed lattice interval");
    }
  }
  for (const auto& box : loaded->certified) {
    if (!std::isfinite(box.taylor_tail_radius_hi) ||
        box.taylor_tail_radius_hi < 0.0 ||
        !finiteOrdered(box.finite_recovery)) {
      throw std::runtime_error("malformed certified residue box");
    }
  }
  loaded->inputSha256 = sparkinterval::lowercase_hex(digest.finish());
  return true;
}

std::uint32_t blocksFor(std::uint64_t count) {
  constexpr std::uint32_t kThreads = 256U;
  return static_cast<std::uint32_t>(std::min<std::uint64_t>(
      65535U, std::max<std::uint64_t>(1U, (count + kThreads - 1U) / kThreads)));
}

class BatchPlan {
 public:
  BatchPlan() = default;
  BatchPlan(const BatchPlan&) = delete;
  BatchPlan& operator=(const BatchPlan&) = delete;
  ~BatchPlan() {
    cudaFree(dOutput_);
    cudaFree(dCertified_);
    cudaFree(dLattices_);
    cudaFree(dFactors_);
    cudaFree(dDescriptors_);
  }

  std::pair<std::vector<ComplexInterval>, std::uint64_t> execute(
      const LoadedFrame& frame, std::uint32_t repetitions) {
    if (repetitions == 0U) throw std::runtime_error("repetitions must be positive");
    reserve(&dDescriptors_, &descriptorCapacity_, frame.descriptors.size());
    reserve(&dFactors_, &factorCapacity_, frame.factors.size());
    reserve(&dLattices_, &latticeCapacity_, frame.lattices.size());
    reserve(&dCertified_, &certifiedCapacity_, frame.certified.size());
    reserve(&dOutput_, &outputCapacity_, frame.header.value_count);
    CUDA_CHECK(cudaMemcpy(dDescriptors_, frame.descriptors.data(),
                          frame.descriptors.size() * sizeof(frame.descriptors[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dFactors_, frame.factors.data(),
                          frame.factors.size() * sizeof(frame.factors[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dLattices_, frame.lattices.data(),
                          frame.lattices.size() * sizeof(frame.lattices[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dCertified_, frame.certified.data(),
                          frame.certified.size() * sizeof(frame.certified[0]),
                          cudaMemcpyHostToDevice));
    cudaEvent_t start = nullptr;
    cudaEvent_t stop = nullptr;
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    constexpr std::uint32_t kThreads = 256U;
    for (std::uint32_t repetition = 0; repetition < repetitions; ++repetition) {
      reconstructComposeKernel<<<blocksFor(frame.header.value_count), kThreads>>>(
          frame.header, dDescriptors_, dFactors_, dLattices_, dCertified_,
          dOutput_);
      CUDA_CHECK(cudaGetLastError());
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsedMilliseconds = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsedMilliseconds, start, stop));
    CUDA_CHECK(cudaEventDestroy(stop));
    CUDA_CHECK(cudaEventDestroy(start));
    std::vector<ComplexInterval> output(frame.header.value_count);
    CUDA_CHECK(cudaMemcpy(output.data(), dOutput_,
                          output.size() * sizeof(output[0]),
                          cudaMemcpyDeviceToHost));
    if (!std::all_of(output.begin(), output.end(),
                     [](const auto& value) { return finiteOrdered(value); })) {
      throw std::runtime_error("CUDA output contains malformed interval");
    }
    const auto elapsedNanoseconds = static_cast<std::uint64_t>(
        static_cast<double>(elapsedMilliseconds) * 1000000.0);
    return {std::move(output), elapsedNanoseconds};
  }

 private:
  template <typename T>
  static void reserve(T** pointer, std::size_t* capacity, std::size_t count) {
    if (count <= *capacity) return;
    CUDA_CHECK(cudaFree(*pointer));
    *pointer = nullptr;
    CUDA_CHECK(cudaMalloc(pointer, count * sizeof(T)));
    *capacity = count;
  }

  lb::ResidueDescriptor* dDescriptors_ = nullptr;
  lb::FrameFactor* dFactors_ = nullptr;
  ComplexInterval* dLattices_ = nullptr;
  lb::CertifiedResidueBox* dCertified_ = nullptr;
  ComplexInterval* dOutput_ = nullptr;
  std::size_t descriptorCapacity_ = 0U;
  std::size_t factorCapacity_ = 0U;
  std::size_t latticeCapacity_ = 0U;
  std::size_t certifiedCapacity_ = 0U;
  std::size_t outputCapacity_ = 0U;
};

da::InputHeader outputHeader(const LoadedFrame& frame) {
  da::InputHeader header{};
  std::memcpy(header.magic, da::kInputMagic, 8);
  header.version = da::kFormatVersion;
  header.q = frame.header.q;
  header.component_count = frame.header.component_count;
  header.batch_count = frame.header.batch_count;
  header.group_order = frame.header.group_order;
  header.first_t_numerator = frame.header.first_t_numerator;
  header.t_denominator = frame.header.t_denominator;
  header.t_step_numerator = frame.header.t_step_numerator;
  header.value_count = frame.header.value_count;
  header.reserved0 = 0U;
  return header;
}

template <typename Stream>
void writeOutput(Stream& output, const LoadedFrame& frame,
                 const std::vector<ComplexInterval>& values,
                 sparkinterval::detail::Sha256* digest = nullptr) {
  const da::InputHeader header = outputHeader(frame);
  output.write(reinterpret_cast<const char*>(&header), sizeof(header));
  output.write(reinterpret_cast<const char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(values[0])));
  if (!output) throw std::runtime_error("cannot write TGDAFFI1 output");
  if (digest != nullptr) {
    digest->update(&header, sizeof(header));
    digest->update(values.data(), values.size() * sizeof(values[0]));
  }
}

void writeAtomically(const std::filesystem::path& path,
                     const LoadedFrame& frame,
                     const std::vector<ComplexInterval>& values) {
  if (std::filesystem::exists(path)) {
    throw std::runtime_error("refusing to replace immutable TGDAFFI1 output");
  }
  const auto temporary =
      path.string() + ".tmp." + std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create temporary output");
    writeOutput(output, frame, values);
    output.flush();
    if (!output) throw std::runtime_error("cannot flush output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish output: " + error.message());
  }
}

void selectDevice(std::uint32_t device) {
  int deviceCount = 0;
  CUDA_CHECK(cudaGetDeviceCount(&deviceCount));
  if (device >= static_cast<std::uint32_t>(deviceCount)) {
    throw std::runtime_error("CUDA device is out of range");
  }
  CUDA_CHECK(cudaSetDevice(static_cast<int>(device)));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, static_cast<int>(device)));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  if (properties.major != 9 || properties.minor != 0) {
    throw std::runtime_error(
        "strict production runner requires an H100 with compute capability 9.0");
  }
#endif
  if (properties.major < 6) {
    throw std::runtime_error("directed binary64 CUDA arithmetic is unavailable");
  }
}

void runSingle(const char* inputPath, const char* outputPath,
               std::uint32_t device, std::uint32_t repetitions) {
  selectDevice(device);
  std::ifstream input(inputPath, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open input");
  LoadedFrame frame;
  if (!readFrame(input, &frame, lb::kMaximumBatchCount)) {
    throw std::runtime_error("empty input");
  }
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes after one input frame");
  }
  BatchPlan plan;
  auto [values, elapsed] = plan.execute(frame, repetitions);
  writeAtomically(outputPath, frame, values);
  const double seconds = static_cast<double>(elapsed) / 1.0e9;
  const double valueRate =
      static_cast<double>(frame.header.value_count) * repetitions / seconds;
  std::cout << "{\"batch_count\":" << frame.header.batch_count
            << ",\"classification\":\"directed_cuda_box_composition_only\""
            << ",\"device\":" << device
            << ",\"input_sha256\":\"" << frame.inputSha256 << "\""
            << ",\"kernel_launches\":" << repetitions
            << ",\"q\":" << frame.header.q
            << ",\"repetitions\":" << repetitions
            << ",\"transcendental_device_calls\":0"
            << ",\"value_count\":" << frame.header.value_count
            << ",\"values_per_second\":" << std::setprecision(17)
            << valueRate << "}\n";
}

void runService(std::uint32_t q, std::uint32_t maximumBatch,
                const std::filesystem::path& summaryPath,
                std::uint32_t device) {
  if (q < lb::kMinimumModulus || q > lb::kMaximumModulus ||
      maximumBatch == 0U || maximumBatch > lb::kMaximumBatchCount) {
    throw std::runtime_error("invalid framed-service q or batch bound");
  }
  if (std::filesystem::exists(summaryPath)) {
    throw std::runtime_error("refusing to replace immutable service summary");
  }
  selectDevice(device);
  BatchPlan plan;
  const auto expectedDescriptors = canonicalDescriptors(q);
  std::uint64_t frames = 0U;
  std::uint64_t launches = 0U;
  std::uint64_t values = 0U;
  std::uint64_t elapsed = 0U;
  std::uint64_t expectedNextT = 0U;
  std::uint32_t expectedM = 0U;
  sparkinterval::detail::Sha256 inputDigests;
  sparkinterval::detail::Sha256 outputDigest;
  while (true) {
    LoadedFrame frame;
    if (!readFrame(std::cin, &frame, maximumBatch, &expectedDescriptors)) break;
    if (frame.header.q != q) {
      throw std::runtime_error("framed-service q changed");
    }
    if (frames != 0U && frame.header.m != expectedM) {
      throw std::runtime_error("framed-service M changed");
    }
    expectedM = frame.header.m;
    if (frames != 0U &&
        static_cast<std::uint64_t>(frame.header.first_t_numerator) !=
            expectedNextT) {
      throw std::runtime_error("framed-service ordinates are not contiguous");
    }
    expectedNextT =
        static_cast<std::uint64_t>(frame.header.first_t_numerator) +
        static_cast<std::uint64_t>(frame.header.batch_count) *
            frame.header.t_step_numerator;
    inputDigests.update(frame.inputSha256.data(), frame.inputSha256.size());
    auto [result, frameElapsed] = plan.execute(frame, 1U);
    writeOutput(std::cout, frame, result, &outputDigest);
    std::cout.flush();
    if (!std::cout) throw std::runtime_error("cannot flush TGDAFFI1 stream");
    ++frames;
    ++launches;
    values += frame.header.value_count;
    elapsed += frameElapsed;
  }
  if (frames == 0U) throw std::runtime_error("framed-service received no frames");
  const auto temporary = summaryPath.string() + ".tmp." +
                         std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream summary(temporary, std::ios::trunc);
    if (!summary) throw std::runtime_error("cannot create service summary");
    summary << "{\"classification\":\"persistent_directed_cuda_box_composition_only\""
            << ",\"device\":" << device
            << ",\"frame_count\":" << frames
            << ",\"input_frame_digest_chain_sha256\":\""
            << sparkinterval::lowercase_hex(inputDigests.finish()) << "\""
            << ",\"kernel_launches\":" << launches
            << ",\"output_stream_sha256\":\""
            << sparkinterval::lowercase_hex(outputDigest.finish()) << "\""
            << ",\"q\":" << q
            << ",\"transcendental_device_calls\":0"
            << ",\"value_count\":" << values
            << ",\"elapsed_kernel_nanoseconds\":" << elapsed << "}\n";
    if (!summary) throw std::runtime_error("cannot write service summary");
  }
  std::error_code error;
  std::filesystem::rename(temporary, summaryPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish service summary: " + error.message());
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 6 && std::string(argv[1]) == "--framed-service") {
      const auto q = parseUnsigned(argv[2], "q");
      const auto maximumBatch = parseUnsigned(argv[3], "maximum batch");
      const auto device = parseUnsigned(argv[5], "device");
      if (q > std::numeric_limits<std::uint32_t>::max() ||
          maximumBatch > std::numeric_limits<std::uint32_t>::max() ||
          device > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("framed-service argument overflow");
      }
      runService(static_cast<std::uint32_t>(q),
                 static_cast<std::uint32_t>(maximumBatch), argv[4],
                 static_cast<std::uint32_t>(device));
      return 0;
    }
    if (argc != 5) {
      throw std::runtime_error(
          "usage: runner INPUT.bin OUTPUT.bin DEVICE REPETITIONS\n"
          "   or: runner --framed-service Q MAX_BATCH SUMMARY.json DEVICE");
    }
    const auto device = parseUnsigned(argv[3], "device");
    const auto repetitions = parseUnsigned(argv[4], "repetitions");
    if (device > std::numeric_limits<std::uint32_t>::max() ||
        repetitions == 0U ||
        repetitions > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error("device or repetition count is invalid");
    }
    runSingle(argv[1], argv[2], static_cast<std::uint32_t>(device),
              static_cast<std::uint32_t>(repetitions));
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_largeq_batch: %s\n", error.what());
    return 1;
  }
}

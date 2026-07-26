// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Compact selected-character oracle for Platt's large-q algorithm.  For one
// ordinate, the input contains the shared Hurwitz lattice and compact CRT
// descriptions of one or more unit groups.  The GPU generates every unit
// residue, performs Lemma 4.2's Taylor reconstruction, multiplies by the
// selected character, and reduces directly to the requested DFT coefficient.
// It intentionally does not claim to be the absent all-character Bluestein
// interval FFT or any of the zero-isolation/Turing pipeline.

#include "sparkinterval/tg_dirichlet_fused.hpp"

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
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <system_error>
#include <tuple>
#include <unistd.h>
#include <utility>
#include <vector>

namespace df = sparkinterval::tg::dirichlet_fused;
namespace dl = sparkinterval::tg::dirichlet_lattice;

namespace {

using dl::ComplexInterval;
using dl::RealInterval;

#define CUDA_CHECK(call)                                                    \
  do {                                                                      \
    const cudaError_t status_ = (call);                                     \
    if (status_ != cudaSuccess) {                                           \
      std::fprintf(stderr, "cuda error %s at %s:%d\n",                    \
                   cudaGetErrorString(status_), __FILE__, __LINE__);        \
      std::exit(2);                                                         \
    }                                                                       \
  } while (0)

__host__ __device__ inline RealInterval add(RealInterval x, RealInterval y) {
#ifdef __CUDA_ARCH__
  return {__dadd_rd(x.lo, y.lo), __dadd_ru(x.hi, y.hi)};
#else
  return {x.lo + y.lo, x.hi + y.hi};
#endif
}

__device__ __forceinline__ RealInterval sub(RealInterval x, RealInterval y) {
  return {__dsub_rd(x.lo, y.hi), __dsub_ru(x.hi, y.lo)};
}

__device__ __forceinline__ RealInterval mul(RealInterval x, RealInterval y) {
  const double dlo0 = __dmul_rd(x.lo, y.lo);
  const double dlo1 = __dmul_rd(x.lo, y.hi);
  const double dlo2 = __dmul_rd(x.hi, y.lo);
  const double dlo3 = __dmul_rd(x.hi, y.hi);
  const double dhi0 = __dmul_ru(x.lo, y.lo);
  const double dhi1 = __dmul_ru(x.lo, y.hi);
  const double dhi2 = __dmul_ru(x.hi, y.lo);
  const double dhi3 = __dmul_ru(x.hi, y.hi);
  return {fmin(fmin(dlo0, dlo1), fmin(dlo2, dlo3)),
          fmax(fmax(dhi0, dhi1), fmax(dhi2, dhi3))};
}

__device__ __forceinline__ RealInterval div_positive(RealInterval x,
                                                      double denominator) {
  return {__ddiv_rd(x.lo, denominator), __ddiv_ru(x.hi, denominator)};
}

__device__ __forceinline__ RealInterval rational_nonnegative(
    std::uint64_t numerator, std::uint64_t denominator) {
  const double n = static_cast<double>(numerator);
  const double d = static_cast<double>(denominator);
  return {__ddiv_rd(n, d), __ddiv_ru(n, d)};
}

__host__ __device__ inline ComplexInterval cadd(ComplexInterval x,
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

__device__ __forceinline__ ComplexInterval cdiv_positive(
    ComplexInterval x, double denominator) {
  return {div_positive(x.re, denominator),
          div_positive(x.im, denominator)};
}

__device__ __forceinline__ ComplexInterval cpow_nonnegative(
    ComplexInterval base, std::uint32_t exponent) {
  ComplexInterval result{{1.0, 1.0}, {0.0, 0.0}};
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) result = cmul(result, base);
    exponent >>= 1U;
    if (exponent != 0U) base = cmul(base, base);
  }
  return result;
}

__device__ __forceinline__ std::uint64_t pow_mod(
    std::uint64_t base, std::uint32_t exponent, std::uint32_t modulus) {
  std::uint64_t result = 1U;
  base %= modulus;
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) result = (result * base) % modulus;
    exponent >>= 1U;
    if (exponent != 0U) base = (base * base) % modulus;
  }
  return result;
}

__device__ __forceinline__ std::uint32_t canonical_row(std::uint32_t q,
                                                        std::uint32_t a) {
  const std::uint64_t twice_numerator =
      2ULL * dl::kLatticeRows * static_cast<std::uint64_t>(a);
  const std::uint64_t twice_q = 2ULL * q;
  std::uint64_t row = (twice_numerator + q - 1ULL) / twice_q;
  if (row < 1ULL) row = 1ULL;
  if (row > dl::kLatticeRows) row = dl::kLatticeRows;
  return static_cast<std::uint32_t>(row);
}

__device__ __forceinline__ std::uint32_t residue_from_group_index(
    const df::ModulusTask& task, const df::LocalFactor* factors,
    const df::CyclicComponent* components, std::uint64_t group_index,
    std::uint32_t* coordinates) {
  std::uint64_t remaining = group_index;
  for (std::uint32_t local = 0; local < task.component_count; ++local) {
    const auto& component = components[task.component_offset + local];
    coordinates[local] =
        static_cast<std::uint32_t>(remaining % component.order);
    remaining /= component.order;
  }
  if (remaining != 0U) return 0U;

  std::uint64_t answer = 0U;
  for (std::uint32_t local_factor = 0;
       local_factor < task.local_factor_count; ++local_factor) {
    const std::uint32_t factor_index =
        task.local_factor_offset + local_factor;
    const auto& factor = factors[factor_index];
    std::uint64_t local_residue = 1U;
    for (std::uint32_t offset = 0; offset < factor.component_count; ++offset) {
      const std::uint32_t component_index = factor.component_offset + offset;
      const auto& component = components[component_index];
      const std::uint32_t coordinate =
          coordinates[component_index - task.component_offset];
      local_residue =
          (local_residue * pow_mod(component.generator, coordinate,
                                   factor.modulus)) %
          factor.modulus;
    }
    const std::uint64_t term =
        (((local_residue * factor.crt_cofactor) % task.q) *
         factor.crt_inverse) %
        task.q;
    answer = (answer + term) % task.q;
  }
  return static_cast<std::uint32_t>(answer);
}

__device__ __forceinline__ ComplexInterval reconstruct(
    const df::InputHeader& header, const df::ModulusTask& task,
    const ComplexInterval* lattice, std::uint32_t a) {
  const std::uint32_t row = canonical_row(task.q, a);
  const RealInterval a_over_q = rational_nonnegative(a, task.q);
  const RealInterval r_over_d =
      rational_nonnegative(row, dl::kLatticeRows);
  const RealInterval minus_delta = sub(r_over_d, a_over_q);
  const RealInterval t = rational_nonnegative(
      static_cast<std::uint64_t>(header.t_numerator), header.t_denominator);
  ComplexInterval power{{1.0, 1.0}, {0.0, 0.0}};
  ComplexInterval sum{{0.0, 0.0}, {0.0, 0.0}};
  for (std::uint32_t column = 0; column <= dl::kTaylorDegree; ++column) {
    const std::size_t lattice_offset =
        (static_cast<std::size_t>(row) - 1U) * dl::kTaylorColumns + column;
    sum = cadd(sum, cmul(power, lattice[lattice_offset]));
    if (column != dl::kTaylorDegree) {
      const ComplexInterval s_plus_column{
          {static_cast<double>(column) + 0.5,
           static_cast<double>(column) + 0.5},
          t};
      power = cdiv_positive(
          cscale(cmul(power, s_plus_column), minus_delta),
          static_cast<double>(column + 1U));
    }
  }
  sum.re.lo = __dsub_rd(sum.re.lo, task.tail_radius_hi);
  sum.re.hi = __dadd_ru(sum.re.hi, task.tail_radius_hi);
  sum.im.lo = __dsub_rd(sum.im.lo, task.tail_radius_hi);
  sum.im.hi = __dadd_ru(sum.im.hi, task.tail_radius_hi);
  return sum;
}

__global__ void fused_character_kernel(
    df::InputHeader header, df::ModulusTask task,
    const df::LocalFactor* factors, const df::CyclicComponent* components,
    const df::CharacterRequest* characters, const ComplexInterval* lattice,
    df::OutputItem* output) {
  constexpr std::uint32_t kThreads = 256;
  __shared__ ComplexInterval partial[kThreads];
  __shared__ std::uint32_t partial_status[kThreads];
  const std::uint32_t local_character = blockIdx.x;
  if (local_character >= task.character_count) return;
  const auto& character =
      characters[task.character_offset + local_character];
  ComplexInterval subtotal{{0.0, 0.0}, {0.0, 0.0}};
  std::uint32_t local_status = 0U;
  for (std::uint64_t group_index = threadIdx.x;
       group_index < task.group_order; group_index += blockDim.x) {
    std::uint32_t coordinates[df::kMaxComponents] = {};
    const std::uint32_t a = residue_from_group_index(
        task, factors, components, group_index, coordinates);
    if (a == 0U || a >= task.q) {
      local_status = 1U;
      continue;
    }
    ComplexInterval weight{{1.0, 1.0}, {0.0, 0.0}};
    for (std::uint32_t local = 0; local < task.component_count; ++local) {
      const auto& component = components[task.component_offset + local];
      const std::uint32_t exponent = static_cast<std::uint32_t>(
          (static_cast<std::uint64_t>(character.frequency[local]) *
           coordinates[local]) %
          component.order);
      weight = cmul(weight, cpow_nonnegative(component.root, exponent));
    }
    subtotal = cadd(subtotal,
                    cmul(weight, reconstruct(header, task, lattice, a)));
  }
  partial[threadIdx.x] = subtotal;
  partial_status[threadIdx.x] = local_status;
  __syncthreads();
  for (std::uint32_t offset = kThreads / 2U; offset != 0U; offset >>= 1U) {
    if (threadIdx.x < offset) {
      partial[threadIdx.x] =
          cadd(partial[threadIdx.x], partial[threadIdx.x + offset]);
      partial_status[threadIdx.x] |= partial_status[threadIdx.x + offset];
    }
    __syncthreads();
  }
  if (threadIdx.x == 0U) {
    const ComplexInterval value = partial[0];
    const bool finite = isfinite(value.re.lo) && isfinite(value.re.hi) &&
                        isfinite(value.im.lo) && isfinite(value.im.hi) &&
                        value.re.lo <= value.re.hi &&
                        value.im.lo <= value.im.hi;
    output[task.character_offset + local_character] = {
        task.q, character.id,
        (finite && partial_status[0] == 0U) ? 0U : 1U, 0U,
        value};
  }
}

template <typename T>
std::vector<T> read_array(std::ifstream& input, std::uint64_t count,
                          const char* label) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(std::string(label) + " array is too large");
  }
  std::vector<T> values(static_cast<std::size_t>(count));
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!input) throw std::runtime_error(std::string("short read of ") + label);
  return values;
}

std::uint64_t pow_mod_host(std::uint64_t base, std::uint64_t exponent,
                           std::uint64_t modulus) {
  std::uint64_t result = 1U;
  base %= modulus;
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) result = (result * base) % modulus;
    exponent >>= 1U;
    if (exponent != 0U) base = (base * base) % modulus;
  }
  return result;
}

std::uint64_t inverse_mod(std::uint64_t value, std::uint64_t modulus) {
  std::int64_t old_r = static_cast<std::int64_t>(value);
  std::int64_t r = static_cast<std::int64_t>(modulus);
  std::int64_t old_s = 1;
  std::int64_t s = 0;
  while (r != 0) {
    const std::int64_t quotient = old_r / r;
    std::tie(old_r, r) = std::pair{r, old_r - quotient * r};
    std::tie(old_s, s) = std::pair{s, old_s - quotient * s};
  }
  if (old_r != 1) throw std::runtime_error("noninvertible CRT cofactor");
  old_s %= static_cast<std::int64_t>(modulus);
  if (old_s < 0) old_s += static_cast<std::int64_t>(modulus);
  return static_cast<std::uint64_t>(old_s);
}

std::vector<std::uint32_t> distinct_prime_divisors(std::uint32_t value) {
  std::vector<std::uint32_t> result;
  for (std::uint32_t p = 2; static_cast<std::uint64_t>(p) * p <= value; ++p) {
    if (value % p != 0U) continue;
    result.push_back(p);
    while (value % p == 0U) value /= p;
  }
  if (value > 1U) result.push_back(value);
  return result;
}

std::uint32_t least_primitive_root(std::uint32_t modulus,
                                   std::uint32_t prime) {
  const std::uint32_t order = modulus - modulus / prime;
  const auto divisors = distinct_prime_divisors(order);
  for (std::uint32_t candidate = 2; candidate < modulus; ++candidate) {
    if (std::gcd(candidate, modulus) != 1U) continue;
    bool primitive = true;
    for (const std::uint32_t divisor : divisors) {
      if (pow_mod_host(candidate, order / divisor, modulus) == 1U) {
        primitive = false;
        break;
      }
    }
    if (primitive) return candidate;
  }
  throw std::runtime_error("cannot reconstruct canonical primitive root");
}

struct ExpectedFactor {
  std::uint32_t modulus;
  std::vector<std::pair<std::uint32_t, std::uint32_t>> components;
};

std::vector<ExpectedFactor> expected_factors(std::uint32_t q) {
  std::vector<ExpectedFactor> result;
  std::uint32_t remainder = q;
  for (std::uint32_t prime = 2;
       static_cast<std::uint64_t>(prime) * prime <= remainder; ++prime) {
    if (remainder % prime != 0U) continue;
    std::uint32_t modulus = 1U;
    std::uint32_t exponent = 0U;
    do {
      remainder /= prime;
      modulus *= prime;
      ++exponent;
    } while (remainder % prime == 0U);
    ExpectedFactor factor{modulus, {}};
    if (prime == 2U) {
      if (exponent == 2U) factor.components.emplace_back(3U, 2U);
      if (exponent > 2U) {
        factor.components.emplace_back(modulus - 1U, 2U);
        factor.components.emplace_back(5U, 1U << (exponent - 2U));
      }
    } else {
      factor.components.emplace_back(
          least_primitive_root(modulus, prime), modulus - modulus / prime);
    }
    result.push_back(std::move(factor));
  }
  if (remainder > 1U) {
    const std::uint32_t prime = remainder;
    result.push_back(ExpectedFactor{
        prime, {{least_primitive_root(prime, prime), prime - 1U}}});
  }
  return result;
}

bool finite_interval(const RealInterval& interval) {
  return std::isfinite(interval.lo) && std::isfinite(interval.hi) &&
         interval.lo <= interval.hi;
}

void validate_input(
    const df::InputHeader& header, const std::vector<df::ModulusTask>& tasks,
    const std::vector<df::LocalFactor>& factors,
    const std::vector<df::CyclicComponent>& components,
    const std::vector<df::CharacterRequest>& characters,
    const std::vector<ComplexInterval>& lattice) {
  if (std::memcmp(header.magic, df::kInputMagic, sizeof(header.magic)) != 0 ||
      header.version != df::kFormatVersion ||
      header.lattice_rows != dl::kLatticeRows ||
      header.taylor_degree != dl::kTaylorDegree || header.task_count == 0U ||
      header.task_count != tasks.size() ||
      header.total_local_factors != factors.size() ||
      header.total_components != components.size() ||
      header.total_characters == 0U ||
      header.total_characters != characters.size() || header.reserved0 != 0U ||
      header.reserved1 != 0U || header.reserved2 != 0U ||
      header.t_numerator < 0 || header.t_denominator == 0U ||
      static_cast<std::uint64_t>(header.t_numerator) > (1ULL << 53U) ||
      header.t_denominator > (1ULL << 53U) ||
      header.lattice_cell_count != dl::kLatticeCellCount ||
      lattice.size() != dl::kLatticeCellCount) {
    throw std::runtime_error("invalid fused Dirichlet input header");
  }
  for (const auto& cell : lattice) {
    if (!finite_interval(cell.re) || !finite_interval(cell.im)) {
      throw std::runtime_error("non-finite or reversed lattice interval");
    }
  }

  std::uint32_t next_factor = 0U;
  std::uint32_t next_component = 0U;
  std::uint32_t next_character = 0U;
  std::uint32_t previous_q = 0U;
  for (const auto& task : tasks) {
    if (task.q < 3U || task.q > df::kMaximumModulus || task.q <= previous_q ||
        task.local_factor_offset != next_factor ||
        task.component_offset != next_component ||
        task.character_offset != next_character ||
        task.local_factor_count == 0U ||
        task.local_factor_count > df::kMaxLocalFactors ||
        task.component_count > df::kMaxComponents ||
        task.character_count == 0U || task.reserved0 != 0U ||
        task.reserved1 != 0U || !std::isfinite(task.tail_radius_hi) ||
        task.tail_radius_hi < 0.0 ||
        static_cast<std::uint64_t>(task.local_factor_offset) +
                task.local_factor_count >
            factors.size() ||
        static_cast<std::uint64_t>(task.component_offset) +
                task.component_count >
            components.size() ||
        static_cast<std::uint64_t>(task.character_offset) +
                task.character_count >
            characters.size()) {
      throw std::runtime_error("invalid or noncanonical modulus task");
    }
    const auto expected = expected_factors(task.q);
    if (expected.size() != task.local_factor_count) {
      throw std::runtime_error("local factor count disagrees with q");
    }
    std::uint64_t group_order = 1U;
    std::uint32_t expected_component_offset = task.component_offset;
    for (std::uint32_t local = 0; local < task.local_factor_count; ++local) {
      const std::uint32_t factor_index = task.local_factor_offset + local;
      const auto& actual_factor = factors[factor_index];
      const auto& expected_factor = expected[local];
      const std::uint64_t cofactor = task.q / expected_factor.modulus;
      const std::uint64_t inverse =
          inverse_mod(cofactor % expected_factor.modulus,
                      expected_factor.modulus);
      if (actual_factor.modulus != expected_factor.modulus ||
          actual_factor.component_offset != expected_component_offset ||
          actual_factor.component_count != expected_factor.components.size() ||
          actual_factor.reserved0 != 0U ||
          actual_factor.crt_cofactor != cofactor ||
          actual_factor.crt_inverse != inverse) {
        throw std::runtime_error("noncanonical CRT local factor descriptor");
      }
      for (std::uint32_t local_component = 0;
           local_component < actual_factor.component_count;
           ++local_component) {
        const std::uint32_t component_index =
            actual_factor.component_offset + local_component;
        const auto& actual_component = components[component_index];
        const auto& expected_component =
            expected_factor.components[local_component];
        if (actual_component.local_factor_index != factor_index ||
            actual_component.generator != expected_component.first ||
            actual_component.order != expected_component.second ||
            actual_component.reserved0 != 0U ||
            !finite_interval(actual_component.root.re) ||
            !finite_interval(actual_component.root.im) ||
            actual_component.root.re.lo < -1.0 ||
            actual_component.root.re.hi > 1.0 ||
            actual_component.root.im.lo < -1.0 ||
            actual_component.root.im.hi > 1.0) {
          throw std::runtime_error("noncanonical cyclic component descriptor");
        }
        group_order *= actual_component.order;
      }
      expected_component_offset += actual_factor.component_count;
    }
    if (expected_component_offset !=
            task.component_offset + task.component_count ||
        group_order != task.group_order) {
      throw std::runtime_error("unit-group order invariant failed");
    }
    std::uint32_t previous_id = 0U;
    for (std::uint32_t local = 0; local < task.character_count; ++local) {
      const auto& character = characters[task.character_offset + local];
      std::uint64_t ordinal = 0U;
      std::uint64_t radix = 1U;
      if (character.reserved0 != 0U ||
          (local != 0U && character.id <= previous_id)) {
        throw std::runtime_error("noncanonical character request ordering");
      }
      for (std::uint32_t component = 0; component < df::kMaxComponents;
           ++component) {
        if (component < task.component_count) {
          const std::uint32_t order =
              components[task.component_offset + component].order;
          if (character.frequency[component] >= order) {
            throw std::runtime_error("character frequency is out of range");
          }
          ordinal += radix * character.frequency[component];
          radix *= order;
        } else if (character.frequency[component] != 0U) {
          throw std::runtime_error("unused character frequency is nonzero");
        }
      }
      if (ordinal != character.id) {
        throw std::runtime_error("character ID is not its mixed-radix ordinal");
      }
      previous_id = character.id;
    }
    next_factor += task.local_factor_count;
    next_component += task.component_count;
    next_character += task.character_count;
    previous_q = task.q;
  }
  if (next_factor != factors.size() || next_component != components.size() ||
      next_character != characters.size()) {
    throw std::runtime_error("task ranges do not cover compact payload");
  }
}

void write_output_atomic(const std::filesystem::path& path,
                         const df::OutputHeader& header,
                         const std::vector<df::OutputItem>& results) {
  const std::filesystem::path temporary =
      path.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create temporary output");
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    output.write(reinterpret_cast<const char*>(results.data()),
                 static_cast<std::streamsize>(results.size() *
                                              sizeof(df::OutputItem)));
    output.flush();
    if (!output) throw std::runtime_error("cannot write output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish output: " + error.message());
  }
}

int parse_nonnegative(const char* text, const char* label) {
  char* end = nullptr;
  errno = 0;
  const long value = std::strtol(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' || value < 0 ||
      value > std::numeric_limits<int>::max()) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<int>(value);
}

int parse_positive(const char* text, const char* label) {
  const int value = parse_nonnegative(text, label);
  if (value == 0) throw std::runtime_error(std::string(label) + " must be positive");
  return value;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 3 || argc > 5) {
      std::fprintf(stderr,
                   "usage: %s INPUT.bin OUTPUT.bin [device] [iterations]\n",
                   argv[0]);
      return 1;
    }
    const int device = argc >= 4 ? parse_nonnegative(argv[3], "device") : 0;
    const int iterations = argc >= 5 ? parse_positive(argv[4], "iterations") : 1;
    CUDA_CHECK(cudaSetDevice(device));
    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
    if (properties.major != 9 || properties.minor != 0 ||
        std::strstr(properties.name, "H100") == nullptr) {
      throw std::runtime_error(
          "strict production runner requires an H100 with compute capability 9.0");
    }
#endif

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    df::InputHeader header{};
    input.read(reinterpret_cast<char*>(&header), sizeof(header));
    if (!input) throw std::runtime_error("short input header");
    if (std::memcmp(header.magic, df::kInputMagic, sizeof(header.magic)) != 0 ||
        header.version != df::kFormatVersion || header.task_count == 0U ||
        header.total_characters == 0U ||
        header.lattice_cell_count != dl::kLatticeCellCount) {
      throw std::runtime_error("invalid fused Dirichlet input header");
    }
    const std::uintmax_t expected_size =
        sizeof(header) +
        static_cast<std::uintmax_t>(header.task_count) * sizeof(df::ModulusTask) +
        static_cast<std::uintmax_t>(header.total_local_factors) *
            sizeof(df::LocalFactor) +
        static_cast<std::uintmax_t>(header.total_components) *
            sizeof(df::CyclicComponent) +
        static_cast<std::uintmax_t>(header.total_characters) *
            sizeof(df::CharacterRequest) +
        static_cast<std::uintmax_t>(header.lattice_cell_count) *
            sizeof(ComplexInterval);
    if (std::filesystem::file_size(argv[1]) != expected_size) {
      throw std::runtime_error("noncanonical compact input file length");
    }
    const auto tasks =
        read_array<df::ModulusTask>(input, header.task_count, "modulus tasks");
    const auto factors = read_array<df::LocalFactor>(
        input, header.total_local_factors, "local factors");
    const auto components = read_array<df::CyclicComponent>(
        input, header.total_components, "cyclic components");
    const auto characters = read_array<df::CharacterRequest>(
        input, header.total_characters, "character requests");
    const auto lattice = read_array<ComplexInterval>(
        input, header.lattice_cell_count, "lattice cells");
    char trailing = 0;
    if (input.read(&trailing, 1)) throw std::runtime_error("trailing input bytes");
    validate_input(header, tasks, factors, components, characters, lattice);

    df::LocalFactor* device_factors = nullptr;
    df::CyclicComponent* device_components = nullptr;
    df::CharacterRequest* device_characters = nullptr;
    ComplexInterval* device_lattice = nullptr;
    df::OutputItem* device_output = nullptr;
    CUDA_CHECK(cudaMalloc(&device_factors, factors.size() * sizeof(*device_factors)));
    CUDA_CHECK(cudaMalloc(&device_components,
                          components.size() * sizeof(*device_components)));
    CUDA_CHECK(cudaMalloc(&device_characters,
                          characters.size() * sizeof(*device_characters)));
    CUDA_CHECK(cudaMalloc(&device_lattice, lattice.size() * sizeof(*device_lattice)));
    CUDA_CHECK(cudaMalloc(&device_output,
                          characters.size() * sizeof(*device_output)));
    CUDA_CHECK(cudaMemcpy(device_factors, factors.data(),
                          factors.size() * sizeof(*device_factors),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_components, components.data(),
                          components.size() * sizeof(*device_components),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_characters, characters.data(),
                          characters.size() * sizeof(*device_characters),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(device_lattice, lattice.data(),
                          lattice.size() * sizeof(*device_lattice),
                          cudaMemcpyHostToDevice));

    cudaEvent_t start{};
    cudaEvent_t stop{};
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    for (int iteration = 0; iteration < iterations; ++iteration) {
      for (const auto& task : tasks) {
        fused_character_kernel<<<task.character_count, 256>>>(
            header, task, device_factors, device_components,
            device_characters, device_lattice, device_output);
        CUDA_CHECK(cudaGetLastError());
      }
    }
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));

    std::vector<df::OutputItem> output(characters.size());
    CUDA_CHECK(cudaMemcpy(output.data(), device_output,
                          output.size() * sizeof(df::OutputItem),
                          cudaMemcpyDeviceToHost));
    std::uint32_t status_or = 0U;
    for (const auto& value : output) status_or |= value.status;
    if (status_or != 0U) {
      throw std::runtime_error("fused kernel emitted invalid output");
    }

    std::uint64_t group_points = 0U;
    for (const auto& task : tasks) {
      if (task.group_order >
          (std::numeric_limits<std::uint64_t>::max() - group_points) /
              task.character_count) {
        throw std::runtime_error("group-point count overflow");
      }
      group_points += task.group_order * task.character_count;
    }
    df::OutputHeader output_header{};
    std::memcpy(output_header.magic, df::kOutputMagic,
                sizeof(output_header.magic));
    output_header.version = df::kFormatVersion;
    output_header.task_count = header.task_count;
    output_header.total_characters = header.total_characters;
    output_header.total_group_points_per_iteration = group_points;
    output_header.elapsed_nanoseconds = static_cast<std::uint64_t>(
        std::ceil(static_cast<double>(elapsed_ms) * 1000000.0));
    write_output_atomic(argv[2], output_header, output);

    const long double seconds = static_cast<long double>(elapsed_ms) / 1000.0L;
    const long double evaluated =
        static_cast<long double>(group_points) * iterations;
    std::printf(
        "{\"algorithm\":\"platt-dirichlet-fused-character-block-v1\","
        "\"conditional_stage_only\":true,\"all_character_fft\":false,"
        "\"device\":\"%s\",\"task_count\":%u,"
        "\"character_count\":%u,\"iterations\":%d,"
        "\"group_points_per_iteration\":%llu,\"kernel_ms\":%.6f,"
        "\"group_points_per_second\":%.6Le,\"status_or\":%u}\n",
        properties.name, header.task_count, header.total_characters, iterations,
        static_cast<unsigned long long>(group_points), elapsed_ms,
        seconds > 0.0L ? evaluated / seconds : 0.0L, status_or);

    cudaEventDestroy(start);
    cudaEventDestroy(stop);
    cudaFree(device_factors);
    cudaFree(device_components);
    cudaFree(device_characters);
    cudaFree(device_lattice);
    cudaFree(device_output);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "Dirichlet fused runner: %s\n", error.what());
    return 1;
  }
}

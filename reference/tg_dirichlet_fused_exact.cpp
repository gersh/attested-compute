// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Exact-dyadic reference for the compact selected-character stage.  All
// binary64 input endpoints are decoded as rationals and the natural interval
// expression is evaluated with unbounded integers.  This checks the finite
// arithmetic and the independently reconstructed CRT enumeration.  It does
// not prove that input rectangles enclose Hurwitz values or roots of unity.

#include "sparkinterval/tg_dirichlet_fused.hpp"

#include <boost/multiprecision/cpp_int.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
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

using Integer = boost::multiprecision::cpp_int;
using Rational = boost::multiprecision::cpp_rational;

struct ExactInterval {
  Rational lo;
  Rational hi;
};

struct ExactComplex {
  ExactInterval re;
  ExactInterval im;
};

struct Input {
  df::InputHeader header;
  std::vector<df::ModulusTask> tasks;
  std::vector<df::LocalFactor> factors;
  std::vector<df::CyclicComponent> components;
  std::vector<df::CharacterRequest> characters;
  std::vector<dl::ComplexInterval> lattice;
};

struct Output {
  df::OutputHeader header;
  std::vector<df::OutputItem> values;
};

Rational from_double(double value) {
  if (!std::isfinite(value)) throw std::runtime_error("non-finite binary64");
  const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
  const bool negative = (bits >> 63U) != 0U;
  const std::uint64_t exponent_bits = (bits >> 52U) & 0x7ffU;
  const std::uint64_t fraction_bits = bits & ((1ULL << 52U) - 1ULL);
  if (exponent_bits == 0U && fraction_bits == 0U) return Rational(0);
  Integer significand;
  int exponent = 0;
  if (exponent_bits == 0U) {
    significand = fraction_bits;
    exponent = -1074;
  } else {
    significand = (1ULL << 52U) | fraction_bits;
    exponent = static_cast<int>(exponent_bits) - 1023 - 52;
  }
  Rational result(significand);
  if (exponent >= 0) {
    result *= Integer(1) << exponent;
  } else {
    result /= Integer(1) << (-exponent);
  }
  return negative ? -result : result;
}

ExactInterval point(const Rational& value) { return {value, value}; }

ExactInterval add(const ExactInterval& x, const ExactInterval& y) {
  return {x.lo + y.lo, x.hi + y.hi};
}

ExactInterval sub(const ExactInterval& x, const ExactInterval& y) {
  return {x.lo - y.hi, x.hi - y.lo};
}

ExactInterval mul(const ExactInterval& x, const ExactInterval& y) {
  const std::array<Rational, 4> products = {
      x.lo * y.lo, x.lo * y.hi, x.hi * y.lo, x.hi * y.hi};
  return {*std::min_element(products.begin(), products.end()),
          *std::max_element(products.begin(), products.end())};
}

ExactInterval divide_positive(const ExactInterval& x,
                              std::uint32_t denominator) {
  const Rational d(denominator);
  return {x.lo / d, x.hi / d};
}

ExactComplex cadd(const ExactComplex& x, const ExactComplex& y) {
  return {add(x.re, y.re), add(x.im, y.im)};
}

ExactComplex cmul(const ExactComplex& x, const ExactComplex& y) {
  return {sub(mul(x.re, y.re), mul(x.im, y.im)),
          add(mul(x.re, y.im), mul(x.im, y.re))};
}

ExactComplex cscale(const ExactComplex& x, const ExactInterval& y) {
  return {mul(x.re, y), mul(x.im, y)};
}

ExactComplex cdivide_positive(const ExactComplex& x,
                              std::uint32_t denominator) {
  return {divide_positive(x.re, denominator),
          divide_positive(x.im, denominator)};
}

ExactComplex cpow_nonnegative(ExactComplex base, std::uint32_t exponent) {
  ExactComplex result{point(Rational(1)), point(Rational(0))};
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) result = cmul(result, base);
    exponent >>= 1U;
    if (exponent != 0U) base = cmul(base, base);
  }
  return result;
}

ExactInterval exact(const dl::RealInterval& value) {
  const ExactInterval result{from_double(value.lo), from_double(value.hi)};
  if (result.lo > result.hi) throw std::runtime_error("reversed interval");
  return result;
}

ExactComplex exact(const dl::ComplexInterval& value) {
  return {exact(value.re), exact(value.im)};
}

std::uint64_t pow_mod(std::uint64_t base, std::uint64_t exponent,
                      std::uint64_t modulus) {
  std::uint64_t result = 1U;
  base %= modulus;
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) result = (result * base) % modulus;
    base = (base * base) % modulus;
    exponent >>= 1U;
  }
  return result;
}

std::uint64_t inverse_mod(std::uint64_t value, std::uint64_t modulus) {
  std::int64_t t = 0;
  std::int64_t new_t = 1;
  std::int64_t r = static_cast<std::int64_t>(modulus);
  std::int64_t new_r = static_cast<std::int64_t>(value);
  while (new_r != 0) {
    const std::int64_t quotient = r / new_r;
    std::tie(t, new_t) = std::pair{new_t, t - quotient * new_t};
    std::tie(r, new_r) = std::pair{new_r, r - quotient * new_r};
  }
  if (r != 1) throw std::runtime_error("CRT inverse does not exist");
  t %= static_cast<std::int64_t>(modulus);
  if (t < 0) t += static_cast<std::int64_t>(modulus);
  return static_cast<std::uint64_t>(t);
}

std::vector<std::uint32_t> prime_divisors(std::uint32_t n) {
  std::vector<std::uint32_t> values;
  std::uint32_t p = 2U;
  while (static_cast<std::uint64_t>(p) * p <= n) {
    if (n % p == 0U) {
      values.push_back(p);
      do {
        n /= p;
      } while (n % p == 0U);
    }
    ++p;
  }
  if (n > 1U) values.push_back(n);
  return values;
}

std::uint32_t primitive_root(std::uint32_t modulus, std::uint32_t prime) {
  const std::uint32_t order = modulus - modulus / prime;
  const auto divisors = prime_divisors(order);
  for (std::uint32_t candidate = 2U; candidate < modulus; ++candidate) {
    if (std::gcd(candidate, modulus) != 1U) continue;
    bool works = true;
    for (const auto divisor : divisors) {
      if (pow_mod(candidate, order / divisor, modulus) == 1U) {
        works = false;
        break;
      }
    }
    if (works) return candidate;
  }
  throw std::runtime_error("primitive-root reconstruction failed");
}

struct FactorModel {
  std::uint32_t modulus;
  std::vector<std::pair<std::uint32_t, std::uint32_t>> cyclic;
};

std::vector<FactorModel> canonical_model(std::uint32_t q) {
  std::vector<FactorModel> model;
  std::uint32_t rest = q;
  for (std::uint32_t p = 2U;
       static_cast<std::uint64_t>(p) * p <= rest; ++p) {
    if (rest % p != 0U) continue;
    std::uint32_t exponent = 0U;
    std::uint32_t pk = 1U;
    while (rest % p == 0U) {
      rest /= p;
      pk *= p;
      ++exponent;
    }
    FactorModel factor{pk, {}};
    if (p == 2U) {
      if (exponent == 2U) factor.cyclic.emplace_back(3U, 2U);
      if (exponent > 2U) {
        factor.cyclic.emplace_back(pk - 1U, 2U);
        factor.cyclic.emplace_back(5U, 1U << (exponent - 2U));
      }
    } else {
      factor.cyclic.emplace_back(primitive_root(pk, p), pk - pk / p);
    }
    model.push_back(std::move(factor));
  }
  if (rest != 1U) {
    model.push_back(FactorModel{
        rest, {{primitive_root(rest, rest), rest - 1U}}});
  }
  return model;
}

void validate(const Input& input) {
  const auto& h = input.header;
  if (std::memcmp(h.magic, df::kInputMagic, sizeof(h.magic)) != 0 ||
      h.version != df::kFormatVersion ||
      h.lattice_rows != dl::kLatticeRows ||
      h.taylor_degree != dl::kTaylorDegree || h.task_count == 0U ||
      h.task_count != input.tasks.size() ||
      h.total_local_factors != input.factors.size() ||
      h.total_components != input.components.size() ||
      h.total_characters == 0U ||
      h.total_characters != input.characters.size() || h.reserved0 != 0U ||
      h.t_numerator < 0 || h.t_denominator == 0U ||
      static_cast<std::uint64_t>(h.t_numerator) > (1ULL << 53U) ||
      h.t_denominator > (1ULL << 53U) ||
      h.lattice_cell_count != dl::kLatticeCellCount ||
      input.lattice.size() != dl::kLatticeCellCount || h.reserved1 != 0U ||
      h.reserved2 != 0U) {
    throw std::runtime_error("invalid compact input header");
  }
  for (const auto& cell : input.lattice) (void)exact(cell);

  std::uint32_t factor_cursor = 0U;
  std::uint32_t component_cursor = 0U;
  std::uint32_t character_cursor = 0U;
  std::uint32_t last_q = 0U;
  for (const auto& task : input.tasks) {
    if (task.q < 3U || task.q > df::kMaximumModulus || task.q <= last_q ||
        task.local_factor_offset != factor_cursor ||
        task.component_offset != component_cursor ||
        task.character_offset != character_cursor ||
        task.local_factor_count == 0U ||
        task.local_factor_count > df::kMaxLocalFactors ||
        task.component_count > df::kMaxComponents ||
        task.character_count == 0U || task.reserved0 != 0U ||
        task.reserved1 != 0U || !std::isfinite(task.tail_radius_hi) ||
        task.tail_radius_hi < 0.0) {
      throw std::runtime_error("invalid modulus task");
    }
    const auto expected = canonical_model(task.q);
    if (expected.size() != task.local_factor_count) {
      throw std::runtime_error("factor count differs from independent model");
    }
    std::uint64_t phi = 1U;
    std::uint32_t component_expected = task.component_offset;
    for (std::uint32_t j = 0; j < task.local_factor_count; ++j) {
      const auto factor_index = task.local_factor_offset + j;
      if (factor_index >= input.factors.size()) {
        throw std::runtime_error("factor range exceeds payload");
      }
      const auto& actual = input.factors[factor_index];
      const auto& wanted = expected[j];
      const std::uint64_t cofactor = task.q / wanted.modulus;
      if (actual.modulus != wanted.modulus ||
          actual.component_offset != component_expected ||
          actual.component_count != wanted.cyclic.size() ||
          actual.reserved0 != 0U || actual.crt_cofactor != cofactor ||
          actual.crt_inverse != inverse_mod(cofactor % wanted.modulus,
                                            wanted.modulus)) {
        throw std::runtime_error("CRT descriptor differs from canonical model");
      }
      for (std::uint32_t k = 0; k < actual.component_count; ++k) {
        const std::uint32_t component_index = actual.component_offset + k;
        if (component_index >= input.components.size()) {
          throw std::runtime_error("component range exceeds payload");
        }
        const auto& component = input.components[component_index];
        if (component.local_factor_index != factor_index ||
            component.generator != wanted.cyclic[k].first ||
            component.order != wanted.cyclic[k].second ||
            component.reserved0 != 0U) {
          throw std::runtime_error("cyclic descriptor differs from canonical model");
        }
        const ExactComplex root = exact(component.root);
        if (root.re.lo < -1 || root.re.hi > 1 || root.im.lo < -1 ||
            root.im.hi > 1) {
          throw std::runtime_error("root interval lies outside the unit square");
        }
        phi *= component.order;
      }
      component_expected += actual.component_count;
    }
    if (component_expected != task.component_offset + task.component_count ||
        phi != task.group_order) {
      throw std::runtime_error("unit-group order mismatch");
    }
    std::uint32_t prior_id = 0U;
    for (std::uint32_t j = 0; j < task.character_count; ++j) {
      const std::uint32_t index = task.character_offset + j;
      if (index >= input.characters.size()) {
        throw std::runtime_error("character range exceeds payload");
      }
      const auto& character = input.characters[index];
      std::uint64_t ordinal = 0U;
      std::uint64_t radix = 1U;
      if (character.reserved0 != 0U ||
          (j != 0U && character.id <= prior_id)) {
        throw std::runtime_error("invalid character request ordering");
      }
      for (std::uint32_t k = 0; k < df::kMaxComponents; ++k) {
        if (k < task.component_count) {
          const std::uint32_t order =
              input.components[task.component_offset + k].order;
          if (character.frequency[k] >= order) {
            throw std::runtime_error("character frequency is outside its radix");
          }
          ordinal += radix * character.frequency[k];
          radix *= order;
        } else if (character.frequency[k] != 0U) {
          throw std::runtime_error("unused character frequency is nonzero");
        }
      }
      if (ordinal != character.id) {
        throw std::runtime_error("character ID differs from mixed-radix ordinal");
      }
      prior_id = character.id;
    }
    factor_cursor += task.local_factor_count;
    component_cursor += task.component_count;
    character_cursor += task.character_count;
    last_q = task.q;
  }
  if (factor_cursor != input.factors.size() ||
      component_cursor != input.components.size() ||
      character_cursor != input.characters.size()) {
    throw std::runtime_error("task ranges do not exactly cover payload arrays");
  }
}

template <typename T>
std::vector<T> read_array(std::ifstream& stream, std::uint64_t count,
                          const char* label) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(std::string(label) + " count is too large");
  }
  std::vector<T> values(static_cast<std::size_t>(count));
  stream.read(reinterpret_cast<char*>(values.data()),
              static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!stream) throw std::runtime_error(std::string("short ") + label);
  return values;
}

Input read_input(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open input");
  Input input{};
  stream.read(reinterpret_cast<char*>(&input.header), sizeof(input.header));
  if (!stream) throw std::runtime_error("short input header");
  if (std::memcmp(input.header.magic, df::kInputMagic,
                  sizeof(input.header.magic)) != 0 ||
      input.header.version != df::kFormatVersion ||
      input.header.task_count == 0U || input.header.total_characters == 0U ||
      input.header.lattice_cell_count != dl::kLatticeCellCount) {
    throw std::runtime_error("invalid compact input header");
  }
  const std::uintmax_t expected_size =
      sizeof(df::InputHeader) +
      static_cast<std::uintmax_t>(input.header.task_count) *
          sizeof(df::ModulusTask) +
      static_cast<std::uintmax_t>(input.header.total_local_factors) *
          sizeof(df::LocalFactor) +
      static_cast<std::uintmax_t>(input.header.total_components) *
          sizeof(df::CyclicComponent) +
      static_cast<std::uintmax_t>(input.header.total_characters) *
          sizeof(df::CharacterRequest) +
      static_cast<std::uintmax_t>(input.header.lattice_cell_count) *
          sizeof(dl::ComplexInterval);
  if (std::filesystem::file_size(path) != expected_size) {
    throw std::runtime_error("noncanonical input length");
  }
  input.tasks = read_array<df::ModulusTask>(
      stream, input.header.task_count, "modulus tasks");
  input.factors = read_array<df::LocalFactor>(
      stream, input.header.total_local_factors, "local factors");
  input.components = read_array<df::CyclicComponent>(
      stream, input.header.total_components, "cyclic components");
  input.characters = read_array<df::CharacterRequest>(
      stream, input.header.total_characters, "characters");
  input.lattice = read_array<dl::ComplexInterval>(
      stream, input.header.lattice_cell_count, "lattice");
  char trailing = 0;
  if (stream.read(&trailing, 1)) throw std::runtime_error("trailing input bytes");
  validate(input);
  return input;
}

Output read_output(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open output");
  Output output{};
  stream.read(reinterpret_cast<char*>(&output.header), sizeof(output.header));
  if (!stream ||
      std::memcmp(output.header.magic, df::kOutputMagic,
                  sizeof(output.header.magic)) != 0 ||
      output.header.version != df::kFormatVersion ||
      output.header.total_characters == 0U || output.header.reserved0 != 0U ||
      output.header.reserved1 != 0U) {
    throw std::runtime_error("invalid output header");
  }
  const std::uintmax_t expected =
      sizeof(df::OutputHeader) +
      static_cast<std::uintmax_t>(output.header.total_characters) *
          sizeof(df::OutputItem);
  if (std::filesystem::file_size(path) != expected) {
    throw std::runtime_error("noncanonical output length");
  }
  output.values = read_array<df::OutputItem>(
      stream, output.header.total_characters, "output values");
  char trailing = 0;
  if (stream.read(&trailing, 1)) throw std::runtime_error("trailing output bytes");
  return output;
}

std::uint32_t residue(const Input& input, const df::ModulusTask& task,
                      std::uint64_t index,
                      std::array<std::uint32_t, df::kMaxComponents>& coordinates) {
  std::uint64_t remaining = index;
  for (std::uint32_t j = 0; j < task.component_count; ++j) {
    const auto& component = input.components[task.component_offset + j];
    coordinates[j] = static_cast<std::uint32_t>(remaining % component.order);
    remaining /= component.order;
  }
  if (remaining != 0U) throw std::runtime_error("mixed-radix decoding failed");
  std::uint64_t answer = 0U;
  for (std::uint32_t j = 0; j < task.local_factor_count; ++j) {
    const auto& factor = input.factors[task.local_factor_offset + j];
    std::uint64_t local = 1U;
    for (std::uint32_t k = 0; k < factor.component_count; ++k) {
      const std::uint32_t component_index = factor.component_offset + k;
      const auto& component = input.components[component_index];
      local = (local * pow_mod(
                           component.generator,
                           coordinates[component_index - task.component_offset],
                           factor.modulus)) %
              factor.modulus;
    }
    answer = (answer +
              ((local * factor.crt_cofactor) % task.q) *
                  factor.crt_inverse) %
             task.q;
  }
  if (answer == 0U || std::gcd(answer, static_cast<std::uint64_t>(task.q)) != 1U) {
    throw std::runtime_error("CRT enumeration produced a nonunit");
  }
  return static_cast<std::uint32_t>(answer);
}

ExactComplex reconstruct(const Input& input, const df::ModulusTask& task,
                         std::uint32_t a) {
  const std::uint32_t row = dl::canonical_lattice_row(task.q, a);
  const Rational t(Integer(input.header.t_numerator),
                   Integer(input.header.t_denominator));
  const Rational minus_delta =
      Rational(row) / Rational(dl::kLatticeRows) -
      Rational(a) / Rational(task.q);
  ExactComplex power{point(Rational(1)), point(Rational(0))};
  ExactComplex sum{point(Rational(0)), point(Rational(0))};
  for (std::uint32_t column = 0; column <= dl::kTaylorDegree; ++column) {
    sum = cadd(sum, cmul(power,
                         exact(input.lattice[dl::lattice_index(row, column)])));
    if (column != dl::kTaylorDegree) {
      const ExactComplex s_plus_column{
          point(Rational(2U * column + 1U) / Rational(2)), point(t)};
      power = cdivide_positive(
          cscale(cmul(power, s_plus_column), point(minus_delta)), column + 1U);
    }
  }
  const Rational tail = from_double(task.tail_radius_hi);
  sum.re.lo -= tail;
  sum.re.hi += tail;
  sum.im.lo -= tail;
  sum.im.hi += tail;
  return sum;
}

ExactComplex evaluate_character(const Input& input,
                                const df::ModulusTask& task,
                                const df::CharacterRequest& character) {
  ExactComplex sum{point(Rational(0)), point(Rational(0))};
  for (std::uint64_t index = 0; index < task.group_order; ++index) {
    std::array<std::uint32_t, df::kMaxComponents> coordinates{};
    const std::uint32_t a = residue(input, task, index, coordinates);
    ExactComplex weight{point(Rational(1)), point(Rational(0))};
    for (std::uint32_t j = 0; j < task.component_count; ++j) {
      const auto& component = input.components[task.component_offset + j];
      const std::uint32_t exponent = static_cast<std::uint32_t>(
          (static_cast<std::uint64_t>(character.frequency[j]) * coordinates[j]) %
          component.order);
      weight = cmul(weight,
                    cpow_nonnegative(exact(component.root), exponent));
    }
    sum = cadd(sum, cmul(weight, reconstruct(input, task, a)));
  }
  return sum;
}

double downward(const Rational& value) {
  double result = value.convert_to<double>();
  if (!std::isfinite(result)) throw std::runtime_error("binary64 overflow");
  while (from_double(result) > value) {
    result = std::nextafter(result, -std::numeric_limits<double>::infinity());
  }
  for (;;) {
    const double next =
        std::nextafter(result, std::numeric_limits<double>::infinity());
    if (!std::isfinite(next) || from_double(next) > value) break;
    result = next;
  }
  return result;
}

double upward(const Rational& value) {
  double result = value.convert_to<double>();
  if (!std::isfinite(result)) throw std::runtime_error("binary64 overflow");
  while (from_double(result) < value) {
    result = std::nextafter(result, std::numeric_limits<double>::infinity());
  }
  for (;;) {
    const double previous =
        std::nextafter(result, -std::numeric_limits<double>::infinity());
    if (!std::isfinite(previous) || from_double(previous) < value) break;
    result = previous;
  }
  return result;
}

dl::ComplexInterval rounded(const ExactComplex& value) {
  return {{downward(value.re.lo), upward(value.re.hi)},
          {downward(value.im.lo), upward(value.im.hi)}};
}

std::uint64_t group_point_count(const Input& input) {
  std::uint64_t total = 0U;
  for (const auto& task : input.tasks) {
    if (task.group_order >
        (std::numeric_limits<std::uint64_t>::max() - total) /
            task.character_count) {
      throw std::runtime_error("group-point count overflow");
    }
    total += task.group_order * task.character_count;
  }
  return total;
}

void write_output_atomic(const std::filesystem::path& path,
                         const Output& output) {
  const auto temporary =
      path.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
  {
    std::ofstream stream(temporary, std::ios::binary | std::ios::trunc);
    if (!stream) throw std::runtime_error("cannot create temporary output");
    stream.write(reinterpret_cast<const char*>(&output.header),
                 sizeof(output.header));
    stream.write(reinterpret_cast<const char*>(output.values.data()),
                 static_cast<std::streamsize>(output.values.size() *
                                              sizeof(df::OutputItem)));
    stream.flush();
    if (!stream) throw std::runtime_error("cannot write output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("cannot publish output: " + error.message());
  }
}

void compute(const Input& input, const std::filesystem::path& path) {
  const auto started = std::chrono::steady_clock::now();
  Output output{};
  std::memcpy(output.header.magic, df::kOutputMagic,
              sizeof(output.header.magic));
  output.header.version = df::kFormatVersion;
  output.header.task_count = input.header.task_count;
  output.header.total_characters = input.header.total_characters;
  output.header.total_group_points_per_iteration = group_point_count(input);
  output.values.reserve(input.characters.size());
  for (const auto& task : input.tasks) {
    for (std::uint32_t local = 0; local < task.character_count; ++local) {
      const auto& character = input.characters[task.character_offset + local];
      output.values.push_back(
          {task.q, character.id, 0U, 0U,
           rounded(evaluate_character(input, task, character))});
    }
  }
  output.header.elapsed_nanoseconds = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now() - started)
          .count());
  write_output_atomic(path, output);
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-fused-character-block-v1\","
      "\"backend\":\"cpu-exact-rational\","
      "\"conditional_stage_only\":true,\"all_character_fft\":false,"
      "\"task_count\":%u,\"character_count\":%u,"
      "\"group_points\":%llu,\"elapsed_nanoseconds\":%llu}\n",
      input.header.task_count, input.header.total_characters,
      static_cast<unsigned long long>(output.header.total_group_points_per_iteration),
      static_cast<unsigned long long>(output.header.elapsed_nanoseconds));
}

void verify(const Input& input, const Output& output) {
  if (output.header.task_count != input.header.task_count ||
      output.header.total_characters != input.header.total_characters ||
      output.header.total_group_points_per_iteration != group_point_count(input) ||
      output.values.size() != input.characters.size()) {
    throw std::runtime_error("input/output header mismatch");
  }
  std::size_t output_index = 0U;
  for (const auto& task : input.tasks) {
    for (std::uint32_t local = 0; local < task.character_count; ++local) {
      const auto& character = input.characters[task.character_offset + local];
      const auto& got_row = output.values[output_index++];
      if (got_row.q != task.q || got_row.character_id != character.id ||
          got_row.status != 0U || got_row.reserved0 != 0U) {
        throw std::runtime_error("output identity/status mismatch");
      }
      const ExactComplex wanted = evaluate_character(input, task, character);
      const ExactComplex got = exact(got_row.value);
      if (got.re.lo > wanted.re.lo || got.re.hi < wanted.re.hi ||
          got.im.lo > wanted.im.lo || got.im.hi < wanted.im.hi) {
        throw std::runtime_error("GPU rectangle misses exact fused coefficient");
      }
    }
  }
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-fused-character-block-v1\","
      "\"checker\":\"cpu-exact-rational-fused-character-v1\","
      "\"conditional_stage_only\":true,\"verified\":true,"
      "\"task_count\":%u,\"character_count\":%u,"
      "\"group_points\":%llu}\n",
      input.header.task_count, input.header.total_characters,
      static_cast<unsigned long long>(group_point_count(input)));
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 4 || (std::strcmp(argv[1], "compute") != 0 &&
                      std::strcmp(argv[1], "verify") != 0)) {
      std::fprintf(stderr, "usage: %s compute|verify INPUT.bin OUTPUT.bin\n",
                   argv[0]);
      return 1;
    }
    const Input input = read_input(argv[2]);
    if (std::strcmp(argv[1], "compute") == 0) {
      compute(input, argv[3]);
    } else {
      verify(input, read_output(argv[3]));
    }
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "Dirichlet fused exact checker: %s\n", error.what());
    return 1;
  }
}

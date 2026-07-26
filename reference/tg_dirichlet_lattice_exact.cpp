// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Exact-rational CPU reference for the conditional large-q Taylor stage.
// Every binary64 endpoint is decoded as an exact dyadic rational.  The checker
// then evaluates the natural interval extension of Platt's Lemma 4.2 with
// unbounded integers and verifies that each GPU rectangle contains it.

#include "sparkinterval/tg_dirichlet_lattice.hpp"

#include <boost/multiprecision/cpp_int.hpp>

#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <iterator>
#include <numeric>
#include <stdexcept>
#include <string>
#include <system_error>
#include <unistd.h>
#include <vector>

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
  dl::InputHeader header;
  std::vector<dl::ComplexInterval> lattice;
  std::vector<dl::InputItem> requests;
};

struct Output {
  dl::OutputHeader header;
  std::vector<dl::OutputItem> results;
};

Rational from_double(double value) {
  if (!std::isfinite(value)) throw std::runtime_error("non-finite binary64");
  const std::uint64_t bits = std::bit_cast<std::uint64_t>(value);
  const bool negative = (bits >> 63U) != 0;
  const std::uint64_t exponent_bits = (bits >> 52U) & 0x7ffU;
  const std::uint64_t fraction_bits = bits & ((1ULL << 52U) - 1ULL);
  if (exponent_bits == 0 && fraction_bits == 0) return Rational(0);

  Integer significand;
  int exponent;
  if (exponent_bits == 0) {
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

Rational rational(std::int64_t numerator, std::uint64_t denominator) {
  if (denominator == 0) throw std::runtime_error("zero rational denominator");
  return Rational(Integer(numerator)) / Rational(Integer(denominator));
}

ExactInterval point(const Rational& value) { return {value, value}; }

ExactInterval add(const ExactInterval& x, const ExactInterval& y) {
  return {x.lo + y.lo, x.hi + y.hi};
}

ExactInterval sub(const ExactInterval& x, const ExactInterval& y) {
  return {x.lo - y.hi, x.hi - y.lo};
}

ExactInterval mul(const ExactInterval& x, const ExactInterval& y) {
  const Rational products[4] = {x.lo * y.lo, x.lo * y.hi,
                                x.hi * y.lo, x.hi * y.hi};
  return {*std::min_element(std::begin(products), std::end(products)),
          *std::max_element(std::begin(products), std::end(products))};
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

ExactInterval exact(const dl::RealInterval& value) {
  const ExactInterval result{from_double(value.lo), from_double(value.hi)};
  if (result.lo > result.hi) throw std::runtime_error("reversed interval");
  return result;
}

ExactComplex exact(const dl::ComplexInterval& value) {
  return {exact(value.re), exact(value.im)};
}

void validate(const Input& input) {
  const auto& header = input.header;
  if (std::memcmp(header.magic, dl::kInputMagic, sizeof(header.magic)) != 0 ||
      header.version != dl::kFormatVersion ||
      header.lattice_rows != dl::kLatticeRows ||
      header.taylor_degree != dl::kTaylorDegree || header.reserved0 != 0 ||
      header.reserved1 != 0 || header.t_numerator < 0 ||
      header.t_denominator == 0 || header.item_count == 0 ||
      header.item_count != input.requests.size() ||
      header.lattice_cell_count != dl::kLatticeCellCount ||
      input.lattice.size() != dl::kLatticeCellCount) {
    throw std::runtime_error("invalid input header");
  }
  for (const auto& cell : input.lattice) (void)exact(cell);
  for (const auto& request : input.requests) {
    if (request.q < 3 || request.q > 400000 || request.a == 0 ||
        request.a >= request.q || std::gcd(request.a, request.q) != 1 ||
        request.reserved != 0 || !std::isfinite(request.tail_radius_hi) ||
        request.tail_radius_hi < 0.0 ||
        request.lattice_row !=
            dl::canonical_lattice_row(request.q, request.a)) {
      throw std::runtime_error("invalid residue request");
    }
    const std::int64_t delta_numerator =
        static_cast<std::int64_t>(dl::kLatticeRows) * request.a -
        static_cast<std::int64_t>(request.lattice_row) * request.q;
    const std::uint64_t absolute_delta = static_cast<std::uint64_t>(
        delta_numerator < 0 ? -delta_numerator : delta_numerator);
    if (absolute_delta >=
        static_cast<std::uint64_t>(request.lattice_row) * request.q) {
      throw std::runtime_error("Taylor request violates |delta| < alpha");
    }
  }
}

Input read_input(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open input");
  Input input{};
  stream.read(reinterpret_cast<char*>(&input.header), sizeof(input.header));
  if (!stream) throw std::runtime_error("short input header");
  if (std::memcmp(input.header.magic, dl::kInputMagic,
                  sizeof(input.header.magic)) != 0 ||
      input.header.version != dl::kFormatVersion ||
      input.header.lattice_rows != dl::kLatticeRows ||
      input.header.taylor_degree != dl::kTaylorDegree ||
      input.header.reserved0 != 0 || input.header.reserved1 != 0 ||
      input.header.t_numerator < 0 || input.header.t_denominator == 0 ||
      input.header.item_count == 0 ||
      input.header.lattice_cell_count != dl::kLatticeCellCount ||
      input.header.item_count >
          std::numeric_limits<std::size_t>::max() / sizeof(dl::InputItem)) {
    throw std::runtime_error("invalid input header");
  }
  const std::uintmax_t file_size = std::filesystem::file_size(path);
  const std::uintmax_t fixed_size =
      sizeof(dl::InputHeader) +
      dl::kLatticeCellCount * sizeof(dl::ComplexInterval);
  if (file_size < fixed_size ||
      input.header.item_count >
          (file_size - fixed_size) / sizeof(dl::InputItem) ||
      fixed_size + input.header.item_count * sizeof(dl::InputItem) != file_size) {
    throw std::runtime_error("noncanonical input file length");
  }
  input.lattice.resize(
      static_cast<std::size_t>(input.header.lattice_cell_count));
  input.requests.resize(static_cast<std::size_t>(input.header.item_count));
  stream.read(reinterpret_cast<char*>(input.lattice.data()),
              static_cast<std::streamsize>(input.lattice.size() *
                                           sizeof(dl::ComplexInterval)));
  stream.read(reinterpret_cast<char*>(input.requests.data()),
              static_cast<std::streamsize>(input.requests.size() *
                                           sizeof(dl::InputItem)));
  if (!stream) throw std::runtime_error("short input payload");
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
      std::memcmp(output.header.magic, dl::kOutputMagic,
                  sizeof(output.header.magic)) != 0 ||
      output.header.version != dl::kFormatVersion ||
      output.header.lattice_rows != dl::kLatticeRows ||
      output.header.taylor_degree != dl::kTaylorDegree ||
      output.header.reserved0 != 0 || output.header.reserved1 != 0 ||
      output.header.item_count >
          std::numeric_limits<std::size_t>::max() / sizeof(dl::OutputItem)) {
    throw std::runtime_error("invalid output header");
  }
  const std::uintmax_t file_size = std::filesystem::file_size(path);
  const std::uintmax_t fixed_size = sizeof(dl::OutputHeader);
  if (file_size < fixed_size ||
      output.header.item_count >
          (file_size - fixed_size) / sizeof(dl::OutputItem) ||
      fixed_size + output.header.item_count * sizeof(dl::OutputItem) != file_size) {
    throw std::runtime_error("noncanonical output file length");
  }
  output.results.resize(static_cast<std::size_t>(output.header.item_count));
  stream.read(reinterpret_cast<char*>(output.results.data()),
              static_cast<std::streamsize>(output.results.size() *
                                           sizeof(dl::OutputItem)));
  if (!stream) throw std::runtime_error("short output payload");
  char trailing = 0;
  if (stream.read(&trailing, 1)) throw std::runtime_error("trailing output bytes");
  return output;
}

ExactComplex evaluate(const Input& input, const dl::InputItem& request) {
  const Rational t =
      rational(input.header.t_numerator, input.header.t_denominator);
  const Rational minus_delta =
      Rational(request.lattice_row) / Rational(dl::kLatticeRows) -
      Rational(request.a) / Rational(request.q);
  ExactComplex power{point(Rational(1)), point(Rational(0))};
  ExactComplex sum{point(Rational(0)), point(Rational(0))};
  for (std::uint32_t column = 0; column <= dl::kTaylorDegree; ++column) {
    sum = cadd(sum,
               cmul(power,
                    exact(input.lattice[dl::lattice_index(
                        request.lattice_row, column)])));
    if (column != dl::kTaylorDegree) {
      const ExactComplex s_plus_column{
          point(Rational(2U * column + 1U) / Rational(2)), point(t)};
      power = cdivide_positive(
          cscale(cmul(power, s_plus_column), point(minus_delta)),
          column + 1U);
    }
  }
  const Rational radius = from_double(request.tail_radius_hi);
  sum.re.lo -= radius;
  sum.re.hi += radius;
  sum.im.lo -= radius;
  sum.im.hi += radius;
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

void write_output_atomic(const std::filesystem::path& path,
                         const Output& output) {
  const std::filesystem::path temporary =
      path.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
  {
    std::ofstream stream(temporary, std::ios::binary | std::ios::trunc);
    if (!stream) throw std::runtime_error("cannot create temporary output");
    stream.write(reinterpret_cast<const char*>(&output.header),
                 sizeof(output.header));
    stream.write(reinterpret_cast<const char*>(output.results.data()),
                 static_cast<std::streamsize>(output.results.size() *
                                              sizeof(dl::OutputItem)));
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
  const auto start = std::chrono::steady_clock::now();
  Output output{};
  std::memcpy(output.header.magic, dl::kOutputMagic,
              sizeof(output.header.magic));
  output.header.version = dl::kFormatVersion;
  output.header.lattice_rows = dl::kLatticeRows;
  output.header.taylor_degree = dl::kTaylorDegree;
  output.header.item_count = input.header.item_count;
  output.results.reserve(input.requests.size());
  for (const auto& request : input.requests) {
    output.results.push_back({request.q, request.a, request.lattice_row, 0,
                              rounded(evaluate(input, request))});
  }
  output.header.elapsed_nanoseconds = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now() - start)
          .count());
  write_output_atomic(path, output);
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-large-q-lattice-taylor-stage-v1\","
      "\"backend\":\"cpu-exact-rational\",\"conditional_stage_only\":true,"
      "\"item_count\":%llu,\"elapsed_nanoseconds\":%llu}\n",
      static_cast<unsigned long long>(output.header.item_count),
      static_cast<unsigned long long>(output.header.elapsed_nanoseconds));
}

void verify(const Input& input, const Output& output) {
  if (output.header.item_count != input.header.item_count ||
      output.results.size() != input.requests.size()) {
    throw std::runtime_error("input/output item count mismatch");
  }
  for (std::size_t index = 0; index < input.requests.size(); ++index) {
    const auto& request = input.requests[index];
    const auto& result = output.results[index];
    if (result.q != request.q || result.a != request.a ||
        result.lattice_row != request.lattice_row || result.status != 0) {
      throw std::runtime_error("output identity or status mismatch at row " +
                               std::to_string(index));
    }
    const ExactComplex wanted = evaluate(input, request);
    const ExactComplex got = exact(result.value);
    if (got.re.lo > wanted.re.lo || got.re.hi < wanted.re.hi ||
        got.im.lo > wanted.im.lo || got.im.hi < wanted.im.hi) {
      throw std::runtime_error("output does not enclose exact result at row " +
                               std::to_string(index));
    }
  }
  std::printf(
      "{\"algorithm\":\"platt-dirichlet-large-q-lattice-taylor-stage-v1\","
      "\"checker\":\"cpu-exact-rational-natural-interval-v1\","
      "\"conditional_stage_only\":true,\"verified\":true,"
      "\"item_count\":%llu}\n",
      static_cast<unsigned long long>(input.header.item_count));
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
    std::fprintf(stderr, "Dirichlet exact lattice checker: %s\n", error.what());
    return 1;
  }
}

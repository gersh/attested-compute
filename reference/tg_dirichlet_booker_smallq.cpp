// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Independent MPFR arithmetic audit for the untrusted small-q CUDA proposal.
// The retained rigorous certificate is produced/replayed with Arb.  This
// program deliberately makes no interval claim: it recomputes every finite
// Gaussian sum at 256-bit precision and rejects a CUDA midpoint differing by
// more than 5e-12*(1+|value|).  It is a cross-implementation KAT and benchmark,
// not the analytic-tail or Theorem-7.1 trust boundary.

#include "sparkinterval/tg_dirichlet_booker_smallq.hpp"

#include <mpfr.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace sq = sparkinterval::tg::dirichlet_booker_smallq;

namespace {

constexpr mpfr_prec_t kPrecision = 256;

class Real {
 public:
  Real() { mpfr_init2(value_, kPrecision); mpfr_set_zero(value_, 0); }
  explicit Real(double value) : Real() { mpfr_set_d(value_, value, MPFR_RNDN); }
  explicit Real(std::uint64_t value) : Real() { mpfr_set_uj(value_, value, MPFR_RNDN); }
  Real(const Real& other) : Real() { mpfr_set(value_, other.value_, MPFR_RNDN); }
  Real(Real&& other) noexcept : Real() { mpfr_swap(value_, other.value_); }
  Real& operator=(const Real& other) {
    if (this != &other) mpfr_set(value_, other.value_, MPFR_RNDN);
    return *this;
  }
  Real& operator=(Real&& other) noexcept {
    if (this != &other) mpfr_swap(value_, other.value_);
    return *this;
  }
  ~Real() { mpfr_clear(value_); }
  mpfr_ptr get() { return value_; }
  mpfr_srcptr get() const { return value_; }
  double as_double() const { return mpfr_get_d(value_, MPFR_RNDN); }
  static Real pi() { Real answer; mpfr_const_pi(answer.get(), MPFR_RNDN); return answer; }
 private:
  mpfr_t value_;
};

Real add(const Real& x, const Real& y) {
  Real z; mpfr_add(z.get(), x.get(), y.get(), MPFR_RNDN); return z;
}
Real sub(const Real& x, const Real& y) {
  Real z; mpfr_sub(z.get(), x.get(), y.get(), MPFR_RNDN); return z;
}
Real mul(const Real& x, const Real& y) {
  Real z; mpfr_mul(z.get(), x.get(), y.get(), MPFR_RNDN); return z;
}
Real div(const Real& x, const Real& y) {
  Real z; mpfr_div(z.get(), x.get(), y.get(), MPFR_RNDN); return z;
}
Real exp(const Real& x) { Real z; mpfr_exp(z.get(), x.get(), MPFR_RNDN); return z; }
Real pow(const Real& x, const Real& y) {
  Real z; mpfr_pow(z.get(), x.get(), y.get(), MPFR_RNDN); return z;
}
Real sin(const Real& x) { Real z; mpfr_sin(z.get(), x.get(), MPFR_RNDN); return z; }
Real cos(const Real& x) { Real z; mpfr_cos(z.get(), x.get(), MPFR_RNDN); return z; }

struct Complex {
  Real re;
  Real im;
};

Complex multiply(const Complex& x, const Complex& y) {
  return {sub(mul(x.re, y.re), mul(x.im, y.im)),
          add(mul(x.re, y.im), mul(x.im, y.re))};
}

Complex add(const Complex& x, const Complex& y) {
  return {add(x.re, y.re), add(x.im, y.im)};
}

template <typename T>
std::vector<T> read_array(std::ifstream& input, std::uint64_t count,
                          const char* label) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T))
    throw std::runtime_error(std::string(label) + " count overflow");
  std::vector<T> result(static_cast<std::size_t>(count));
  input.read(reinterpret_cast<char*>(result.data()),
             static_cast<std::streamsize>(result.size() * sizeof(T)));
  if (!input) throw std::runtime_error(std::string("short ") + label);
  return result;
}

struct Input {
  sq::InputHeader header;
  std::vector<std::uint32_t> exponents;
  std::vector<sq::FrequencyRequest> requests;
};

Input read_input(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open input");
  Input input{};
  stream.read(reinterpret_cast<char*>(&input.header), sizeof(input.header));
  if (!stream || std::memcmp(input.header.magic, sq::kInputMagic, 8) != 0 ||
      input.header.version != sq::kFormatVersion || input.header.q < 3 ||
      input.header.q > sq::kMaximumModulus || input.header.group_exponent == 0 ||
      input.header.parity > 1 || input.header.frequency_count == 0 ||
      input.header.reserved0 != 0)
    throw std::runtime_error("invalid input header");
  const std::uintmax_t expected = sizeof(sq::InputHeader) +
      static_cast<std::uintmax_t>(input.header.q) * sizeof(std::uint32_t) +
      static_cast<std::uintmax_t>(input.header.frequency_count) *
          sizeof(sq::FrequencyRequest);
  if (std::filesystem::file_size(path) != expected)
    throw std::runtime_error("noncanonical input size");
  input.exponents = read_array<std::uint32_t>(stream, input.header.q, "exponents");
  input.requests = read_array<sq::FrequencyRequest>(
      stream, input.header.frequency_count, "requests");
  return input;
}

struct Output {
  sq::OutputHeader header;
  std::vector<sq::OutputItem> values;
};

Output read_output(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open output");
  Output output{};
  stream.read(reinterpret_cast<char*>(&output.header), sizeof(output.header));
  if (!stream || std::memcmp(output.header.magic, sq::kOutputMagic, 8) != 0 ||
      output.header.version != sq::kFormatVersion || output.header.reserved0 != 0)
    throw std::runtime_error("invalid output header");
  const std::uintmax_t expected = sizeof(sq::OutputHeader) +
      static_cast<std::uintmax_t>(output.header.frequency_count) *
          sizeof(sq::OutputItem);
  if (std::filesystem::file_size(path) != expected)
    throw std::runtime_error("noncanonical output size");
  output.values = read_array<sq::OutputItem>(stream, output.header.frequency_count,
                                             "output values");
  return output;
}

Complex evaluate(const Input& input, const sq::FrequencyRequest& request) {
  const Real pi = Real::pi();
  const std::uint64_t absolute_index = request.signed_index < 0
      ? static_cast<std::uint64_t>(-request.signed_index)
      : static_cast<std::uint64_t>(request.signed_index);
  const Real x = div(mul(mul(Real(2.0), pi), Real(absolute_index)),
                     Real(input.header.b));
  const Real u_imag = div(mul(pi, Real(input.header.eta)), Real(4.0));
  const Real exp_2x = exp(mul(Real(2.0), x));
  const Real cosine_2u = cos(mul(Real(2.0), u_imag));
  const Real sine_2u = sin(mul(Real(2.0), u_imag));
  const Real coefficient = div(
      mul(pi, exp_2x), Real(static_cast<std::uint64_t>(input.header.q)));
  Real gaussian_real = mul(Real(-1.0), mul(coefficient, cosine_2u));
  Real gaussian_imag = mul(Real(-1.0), mul(coefficient, sine_2u));
  Complex sum{Real(0.0), Real(0.0)};
  for (std::uint32_t n = 1; n <= request.truncation; ++n) {
    const std::uint32_t exponent_value = input.exponents[n % input.header.q];
    if (exponent_value == sq::kNonUnitExponent) continue;
    const Real n_squared = mul(Real(static_cast<std::uint64_t>(n)),
                               Real(static_cast<std::uint64_t>(n)));
    Real magnitude = exp(mul(gaussian_real, n_squared));
    if (input.header.parity != 0)
      magnitude = mul(magnitude, Real(static_cast<std::uint64_t>(n)));
    const Real character_phase = div(
        mul(mul(Real(2.0), pi),
            Real(static_cast<std::uint64_t>(exponent_value))),
        Real(static_cast<std::uint64_t>(input.header.group_exponent)));
    const Real phase = add(mul(gaussian_imag, n_squared), character_phase);
    sum = add(sum, {mul(magnitude, cos(phase)), mul(magnitude, sin(phase))});
  }
  const Real p(input.header.parity == 0 ? 0.5 : 1.5);
  const Real prefactor_magnitude = div(
      mul(Real(2.0), exp(mul(p, x))),
      pow(Real(static_cast<std::uint64_t>(input.header.q)),
          div(p, Real(2.0))));
  const Real phase = mul(p, u_imag);
  const Complex tilt{mul(prefactor_magnitude, cos(phase)),
                     mul(prefactor_magnitude, sin(phase))};
  const Complex epsilon{Real(input.header.epsilon_real),
                        Real(input.header.epsilon_imag)};
  Complex answer = multiply(multiply(epsilon, tilt), sum);
  if (request.signed_index < 0) answer.im = mul(Real(-1.0), answer.im);
  return answer;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3) {
      std::fprintf(stderr, "usage: %s INPUT GPU_OUTPUT\n", argv[0]);
      return 2;
    }
    const Input input = read_input(argv[1]);
    const Output output = read_output(argv[2]);
    if (output.header.q != input.header.q ||
        output.header.frequency_start != input.header.frequency_start ||
        output.header.frequency_count != input.header.frequency_count)
      throw std::runtime_error("input/output identity mismatch");
    double maximum_absolute = 0.0;
    double maximum_relative = 0.0;
    std::uint64_t total_terms = 0;
    for (std::size_t i = 0; i < input.requests.size(); ++i) {
      const auto& request = input.requests[i];
      const auto& proposal = output.values[i];
      if (request.index != input.header.frequency_start + i ||
          proposal.index != request.index || request.reserved0 != 0 ||
          proposal.status != 0 || proposal.reserved0 != 0)
        throw std::runtime_error("request/output sequence mismatch");
      const Complex reference = evaluate(input, request);
      const double re = reference.re.as_double();
      const double im = reference.im.as_double();
      const double error = std::hypot(proposal.real - re, proposal.imag - im);
      const double magnitude = std::hypot(re, im);
      maximum_absolute = std::max(maximum_absolute, error);
      maximum_relative = std::max(maximum_relative,
                                  error / std::max(magnitude, 1e-300));
      if (error > 5e-12 * (1.0 + magnitude))
        throw std::runtime_error("CUDA proposal differs from MPFR reference");
      total_terms += request.truncation;
    }
    std::printf(
        "{\"algorithm\":\"mpfr256-smallq-finite-sum-audit-v1\","
        "\"frequencies\":%llu,\"finite_gaussian_terms\":%llu,"
        "\"maximum_absolute_error\":%.17g,"
        "\"maximum_relative_error\":%.17g,"
        "\"passed\":true,\"trusted_certificate\":false}\n",
        static_cast<unsigned long long>(input.header.frequency_count),
        static_cast<unsigned long long>(total_terms), maximum_absolute,
        maximum_relative);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_booker_smallq: %s\n", error.what());
    return 2;
  }
}

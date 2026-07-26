// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Independent MPFR-directed reference for the multidimensional Bluestein
// transform used in Platt's large-q all-character stage.  This implementation
// deliberately shares only the binary format with the CUDA producer.

#include "sparkinterval/tg_dirichlet_allchars.hpp"

#include <mpfr.h>

#include <algorithm>
#include <bit>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <system_error>
#include <type_traits>
#include <unistd.h>
#include <utility>
#include <vector>

namespace da = sparkinterval::tg::dirichlet_allchars;
namespace dl = sparkinterval::tg::dirichlet_lattice;

namespace {

mpfr_prec_t gPrecision = 192;

static_assert(
    std::endian::native == std::endian::little,
    "the raw all-character interval wire formats require little endian");
static_assert(
    sizeof(double) == 8U && std::numeric_limits<double>::is_iec559 &&
        std::numeric_limits<double>::radix == 2 &&
        std::numeric_limits<double>::digits == 53 &&
        std::numeric_limits<double>::max_exponent == 1024,
    "the raw all-character interval wire formats require IEEE binary64");
static_assert(std::is_standard_layout_v<dl::RealInterval>);
static_assert(std::is_trivially_copyable_v<dl::RealInterval>);
static_assert(std::is_standard_layout_v<dl::ComplexInterval>);
static_assert(std::is_trivially_copyable_v<dl::ComplexInterval>);
static_assert(sizeof(dl::RealInterval) == 16U);
static_assert(sizeof(dl::ComplexInterval) == 32U);

class Interval {
 public:
  Interval() {
    mpfr_init2(lo_, gPrecision);
    mpfr_init2(hi_, gPrecision);
    mpfr_set_zero(lo_, 0);
    mpfr_set_zero(hi_, 0);
  }
  Interval(const Interval& other) : Interval() {
    mpfr_set(lo_, other.lo_, MPFR_RNDD);
    mpfr_set(hi_, other.hi_, MPFR_RNDU);
  }
  Interval(Interval&& other) noexcept : Interval() {
    mpfr_swap(lo_, other.lo_);
    mpfr_swap(hi_, other.hi_);
  }
  Interval& operator=(const Interval& other) {
    if (this != &other) {
      mpfr_set(lo_, other.lo_, MPFR_RNDD);
      mpfr_set(hi_, other.hi_, MPFR_RNDU);
    }
    return *this;
  }
  Interval& operator=(Interval&& other) noexcept {
    if (this != &other) {
      mpfr_swap(lo_, other.lo_);
      mpfr_swap(hi_, other.hi_);
    }
    return *this;
  }
  ~Interval() {
    mpfr_clear(lo_);
    mpfr_clear(hi_);
  }
  mpfr_ptr lo() { return lo_; }
  mpfr_ptr hi() { return hi_; }
  mpfr_srcptr lo() const { return lo_; }
  mpfr_srcptr hi() const { return hi_; }

  static Interval fromDouble(double lo, double hi) {
    Interval answer;
    mpfr_set_d(answer.lo_, lo, MPFR_RNDD);
    mpfr_set_d(answer.hi_, hi, MPFR_RNDU);
    return answer;
  }

  static Interval exact(long value) {
    Interval answer;
    mpfr_set_si(answer.lo_, value, MPFR_RNDD);
    mpfr_set_si(answer.hi_, value, MPFR_RNDU);
    return answer;
  }

 private:
  mpfr_t lo_;
  mpfr_t hi_;
};

struct Complex {
  Interval re;
  Interval im;
};

Interval add(const Interval& a, const Interval& b) {
  Interval answer;
  mpfr_add(answer.lo(), a.lo(), b.lo(), MPFR_RNDD);
  mpfr_add(answer.hi(), a.hi(), b.hi(), MPFR_RNDU);
  return answer;
}

Interval sub(const Interval& a, const Interval& b) {
  Interval answer;
  mpfr_sub(answer.lo(), a.lo(), b.hi(), MPFR_RNDD);
  mpfr_sub(answer.hi(), a.hi(), b.lo(), MPFR_RNDU);
  return answer;
}

Interval mul(const Interval& a, const Interval& b) {
  Interval answer;
  mpfr_t down, up;
  mpfr_init2(down, gPrecision);
  mpfr_init2(up, gPrecision);
  bool first = true;
  for (mpfr_srcptr x : {a.lo(), a.hi()}) {
    for (mpfr_srcptr y : {b.lo(), b.hi()}) {
      mpfr_mul(down, x, y, MPFR_RNDD);
      mpfr_mul(up, x, y, MPFR_RNDU);
      if (first || mpfr_less_p(down, answer.lo())) {
        mpfr_set(answer.lo(), down, MPFR_RNDD);
      }
      if (first || mpfr_greater_p(up, answer.hi())) {
        mpfr_set(answer.hi(), up, MPFR_RNDU);
      }
      first = false;
    }
  }
  mpfr_clear(up);
  mpfr_clear(down);
  return answer;
}

Interval divPositiveInteger(const Interval& a, std::uint32_t denominator) {
  Interval answer;
  mpfr_div_ui(answer.lo(), a.lo(), denominator, MPFR_RNDD);
  mpfr_div_ui(answer.hi(), a.hi(), denominator, MPFR_RNDU);
  return answer;
}

Complex cadd(const Complex& a, const Complex& b) {
  return {add(a.re, b.re), add(a.im, b.im)};
}

Complex csub(const Complex& a, const Complex& b) {
  return {sub(a.re, b.re), sub(a.im, b.im)};
}

Complex cmul(const Complex& a, const Complex& b) {
  return {sub(mul(a.re, b.re), mul(a.im, b.im)),
          add(mul(a.re, b.im), mul(a.im, b.re))};
}

Complex cdiv(const Complex& a, std::uint32_t denominator) {
  return {divPositiveInteger(a.re, denominator),
          divPositiveInteger(a.im, denominator)};
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

std::vector<std::uint32_t> reconstructOrders(std::uint32_t q) {
  if (q < 3U || q > 400000U) throw std::runtime_error("q out of range");
  std::vector<std::uint32_t> result;
  std::uint32_t n = q;
  std::uint32_t p = 2U;
  while (static_cast<std::uint64_t>(p) * p <= n) {
    if (n % p != 0U) {
      ++p;
      continue;
    }
    std::uint32_t e = 0U;
    std::uint32_t power = 1U;
    do {
      n /= p;
      power *= p;
      ++e;
    } while (n % p == 0U);
    if (p == 2U) {
      if (e == 2U) result.push_back(2U);
      if (e > 2U) {
        result.push_back(2U);
        result.push_back(1U << (e - 2U));
      }
    } else {
      result.push_back(power - power / p);
    }
    ++p;
  }
  if (n > 1U) result.push_back(n - 1U);
  if (result.size() > 8U) throw std::runtime_error("too many components");
  return result;
}

std::uint64_t product(const std::vector<std::uint32_t>& values) {
  std::uint64_t answer = 1U;
  for (const auto value : values) answer *= value;
  return answer;
}

std::uint32_t nextPow2(std::uint64_t target) {
  std::uint64_t answer = 1U;
  while (answer < target) answer *= 2U;
  if (answer > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error("convolution overflow");
  }
  return static_cast<std::uint32_t>(answer);
}

std::uint32_t log2Exact(std::uint32_t value) {
  std::uint32_t answer = 0U;
  while ((1U << answer) != value) ++answer;
  return answer;
}

void include(Interval& range, mpfr_srcptr lower, mpfr_srcptr upper) {
  if (mpfr_less_p(lower, range.lo())) mpfr_set(range.lo(), lower, MPFR_RNDD);
  if (mpfr_greater_p(upper, range.hi())) mpfr_set(range.hi(), upper, MPFR_RNDU);
}

Interval trig(std::uint64_t numerator, std::uint64_t denominator, bool sine) {
  numerator %= 2U * denominator;
  mpq_t exact;
  mpq_init(exact);
  mpq_set_ui(exact, numerator, denominator);
  mpq_canonicalize(exact);
  mpfr_t xLo, xHi, aLo, aHi, bLo, bHi, point;
  for (mpfr_ptr value : {xLo, xHi, aLo, aHi, bLo, bHi, point}) {
    mpfr_init2(value, gPrecision);
  }
  mpfr_set_q(xLo, exact, MPFR_RNDD);
  mpfr_set_q(xHi, exact, MPFR_RNDU);
  if (sine) {
    mpfr_sinpi(aLo, xLo, MPFR_RNDD);
    mpfr_sinpi(aHi, xLo, MPFR_RNDU);
    mpfr_sinpi(bLo, xHi, MPFR_RNDD);
    mpfr_sinpi(bHi, xHi, MPFR_RNDU);
  } else {
    mpfr_cospi(aLo, xLo, MPFR_RNDD);
    mpfr_cospi(aHi, xLo, MPFR_RNDU);
    mpfr_cospi(bLo, xHi, MPFR_RNDD);
    mpfr_cospi(bHi, xHi, MPFR_RNDU);
  }
  Interval answer;
  mpfr_set(answer.lo(), aLo, MPFR_RNDD);
  mpfr_set(answer.hi(), aHi, MPFR_RNDU);
  include(answer, bLo, bHi);
  const int twiceCritical[] = {0, 1, 2, 3, 4};
  for (const int twice : twiceCritical) {
    mpfr_set_si(point, twice, MPFR_RNDN);
    mpfr_div_2ui(point, point, 1U, MPFR_RNDN);
    if (mpfr_lessequal_p(xLo, point) && mpfr_greaterequal_p(xHi, point)) {
      int value = 0;
      if (sine) {
        if (twice == 1) value = 1;
        if (twice == 3) value = -1;
      } else {
        if (twice == 0 || twice == 4) value = 1;
        if (twice == 2) value = -1;
      }
      mpfr_set_si(aLo, value, MPFR_RNDD);
      mpfr_set_si(aHi, value, MPFR_RNDU);
      include(answer, aLo, aHi);
    }
  }
  for (mpfr_ptr value : {point, bHi, bLo, aHi, aLo, xHi, xLo}) {
    mpfr_clear(value);
  }
  mpq_clear(exact);
  return answer;
}

Complex root(std::uint64_t numerator, std::uint64_t denominator, int sign) {
  if (sign < 0 && numerator != 0U) {
    numerator = (2U * denominator - numerator % (2U * denominator)) %
                (2U * denominator);
  }
  return {trig(numerator, denominator, false),
          trig(numerator, denominator, true)};
}

std::vector<Complex> roots(std::uint32_t length, int sign) {
  std::vector<Complex> answer(length - 1U);
  for (std::uint32_t stage = 2U; stage <= length; stage *= 2U) {
    const std::uint32_t half = stage / 2U;
    for (std::uint32_t j = 0; j < half; ++j) {
      answer[half - 1U + j] = root(2ULL * j, stage, sign);
    }
  }
  return answer;
}

void fft(std::vector<Complex>& values, const std::vector<Complex>& twiddles) {
  const std::uint32_t n = static_cast<std::uint32_t>(values.size());
  for (std::uint32_t i = 1U, j = 0U; i < n; ++i) {
    std::uint32_t bit = n >> 1U;
    while ((j & bit) != 0U) {
      j ^= bit;
      bit >>= 1U;
    }
    j ^= bit;
    if (i < j) std::swap(values[i], values[j]);
  }
  for (std::uint32_t stage = 2U; stage <= n; stage *= 2U) {
    const std::uint32_t half = stage / 2U;
    for (std::uint32_t base = 0U; base < n; base += stage) {
      for (std::uint32_t j = 0U; j < half; ++j) {
        const Complex u = values[base + j];
        const Complex v = cmul(values[base + j + half],
                               twiddles[half - 1U + j]);
        values[base + j] = cadd(u, v);
        values[base + j + half] = csub(u, v);
      }
    }
  }
}

std::vector<Complex> chirps(std::uint32_t length, int sign) {
  std::vector<Complex> answer(length);
  for (std::uint64_t n = 0; n < length; ++n) {
    answer[n] = root(n * n, length, sign);
  }
  return answer;
}

std::vector<Complex> transformDimension(const std::vector<Complex>& input,
                                        std::uint32_t length,
                                        std::uint64_t stride) {
  const std::uint64_t total = input.size();
  const std::uint64_t lines = total / length;
  const std::uint32_t m = nextPow2(2ULL * length - 1ULL);
  const auto plus = chirps(length, +1);
  const auto minus = chirps(length, -1);
  const auto forward = roots(m, -1);
  const auto inverse = roots(m, +1);
  std::vector<Complex> kernel(m);
  kernel[0] = minus[0];
  for (std::uint32_t n = 1U; n < length; ++n) {
    kernel[n] = minus[n];
    kernel[m - n] = minus[n];
  }
  fft(kernel, forward);

  std::vector<Complex> output(total);
  std::vector<Complex> work(m);
  for (std::uint64_t line = 0; line < lines; ++line) {
    std::fill(work.begin(), work.end(), Complex{});
    const std::uint64_t outer = line / stride;
    const std::uint64_t inner = line % stride;
    for (std::uint32_t n = 0U; n < length; ++n) {
      const std::uint64_t source = outer * length * stride +
                                   static_cast<std::uint64_t>(n) * stride + inner;
      work[n] = cmul(input[source], plus[n]);
    }
    fft(work, forward);
    for (std::uint32_t k = 0U; k < m; ++k) work[k] = cmul(work[k], kernel[k]);
    fft(work, inverse);
    for (std::uint32_t k = 0U; k < length; ++k) {
      const std::uint64_t target = outer * length * stride +
                                   static_cast<std::uint64_t>(k) * stride + inner;
      output[target] = cdiv(cmul(work[k], plus[k]), m);
    }
  }
  return output;
}

struct Input {
  da::InputHeader header{};
  std::vector<dl::ComplexInterval> raw;
  std::vector<std::uint32_t> orders;
};

Input readInput(const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) throw std::runtime_error("could not open input");
  Input input;
  file.read(reinterpret_cast<char*>(&input.header), sizeof(input.header));
  if (!file) throw std::runtime_error("truncated input header");
  if (std::memcmp(input.header.magic, da::kInputMagic, 8) != 0 ||
      input.header.version != 1U || input.header.reserved0 != 0U ||
      input.header.batch_count == 0U || input.header.t_denominator == 0U ||
      input.header.first_t_numerator < 0 || input.header.t_step_numerator == 0U) {
    throw std::runtime_error("invalid input header");
  }
  input.orders = reconstructOrders(input.header.q);
  const std::uint64_t expected = product(input.orders);
  if (input.header.component_count != input.orders.size() ||
      input.header.group_order != expected ||
      input.header.value_count != expected * input.header.batch_count) {
    throw std::runtime_error("input group identity mismatch");
  }
  input.raw.resize(input.header.value_count);
  file.read(reinterpret_cast<char*>(input.raw.data()),
            static_cast<std::streamsize>(input.raw.size() * sizeof(input.raw[0])));
  if (!file) throw std::runtime_error("truncated values");
  if (file.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing input bytes");
  }
  for (const auto& z : input.raw) {
    if (!std::isfinite(z.re.lo) || !std::isfinite(z.re.hi) ||
        !std::isfinite(z.im.lo) || !std::isfinite(z.im.hi) ||
        z.re.lo > z.re.hi || z.im.lo > z.im.hi) {
      throw std::runtime_error("malformed input interval");
    }
  }
  return input;
}

std::vector<Complex> compute(const Input& input) {
  std::vector<Complex> values(input.raw.size());
  for (std::size_t i = 0; i < values.size(); ++i) {
    values[i].re = Interval::fromDouble(input.raw[i].re.lo, input.raw[i].re.hi);
    values[i].im = Interval::fromDouble(input.raw[i].im.lo, input.raw[i].im.hi);
  }
  std::uint64_t stride = 1U;
  for (const auto length : input.orders) {
    values = transformDimension(values, length, stride);
    stride *= length;
  }
  return values;
}

std::uint64_t butterflyCount(const Input& input) {
  std::uint64_t answer = 0U;
  for (const auto n : input.orders) {
    const std::uint64_t lines = input.raw.size() / n;
    const std::uint32_t m = nextPow2(2ULL * n - 1ULL);
    answer += (1ULL + 2ULL * lines) * (m / 2ULL) * log2Exact(m);
  }
  return answer;
}

void writeOutput(const std::string& path, const Input& input,
                 const std::vector<Complex>& values, std::uint64_t elapsed) {
  da::OutputHeader header{};
  std::memcpy(header.magic, da::kOutputMagic, 8);
  header.version = 1U;
  header.q = input.header.q;
  header.component_count = input.header.component_count;
  header.batch_count = input.header.batch_count;
  header.group_order = input.header.group_order;
  header.value_count = input.raw.size();
  header.radix2_butterflies = butterflyCount(input);
  header.elapsed_nanoseconds = elapsed;
  std::vector<dl::ComplexInterval> raw(values.size());
  for (std::size_t i = 0; i < values.size(); ++i) {
    raw[i] = {{mpfr_get_d(values[i].re.lo(), MPFR_RNDD),
               mpfr_get_d(values[i].re.hi(), MPFR_RNDU)},
              {mpfr_get_d(values[i].im.lo(), MPFR_RNDD),
               mpfr_get_d(values[i].im.hi(), MPFR_RNDU)}};
  }
  const std::string temporary = path + ".tmp." + std::to_string(getpid());
  {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    output.write(reinterpret_cast<const char*>(raw.data()),
                 static_cast<std::streamsize>(raw.size() * sizeof(raw[0])));
    if (!output) throw std::runtime_error("could not write output");
  }
  std::error_code error;
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error("could not publish output");
  }
}

void verifyOutput(const std::string& path, const Input& input,
                  const std::vector<Complex>& expected) {
  std::ifstream file(path, std::ios::binary);
  da::OutputHeader header{};
  file.read(reinterpret_cast<char*>(&header), sizeof(header));
  if (!file || std::memcmp(header.magic, da::kOutputMagic, 8) != 0 ||
      header.version != 1U || header.q != input.header.q ||
      header.component_count != input.header.component_count ||
      header.batch_count != input.header.batch_count ||
      header.group_order != input.header.group_order ||
      header.value_count != input.raw.size() ||
      header.radix2_butterflies != butterflyCount(input)) {
    throw std::runtime_error("output identity mismatch");
  }
  for (std::size_t i = 0; i < expected.size(); ++i) {
    dl::ComplexInterval candidate{};
    file.read(reinterpret_cast<char*>(&candidate), sizeof(candidate));
    if (!file || !std::isfinite(candidate.re.lo) ||
        !std::isfinite(candidate.re.hi) || !std::isfinite(candidate.im.lo) ||
        !std::isfinite(candidate.im.hi) || candidate.re.lo > candidate.re.hi ||
        candidate.im.lo > candidate.im.hi) {
      throw std::runtime_error("malformed output interval");
    }
    if (mpfr_cmp_d(expected[i].re.lo(), candidate.re.lo) < 0 ||
        mpfr_cmp_d(expected[i].re.hi(), candidate.re.hi) > 0 ||
        mpfr_cmp_d(expected[i].im.lo(), candidate.im.lo) < 0 ||
        mpfr_cmp_d(expected[i].im.hi(), candidate.im.hi) > 0) {
      throw std::runtime_error("output does not enclose MPFR reference");
    }
  }
  if (file.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing output bytes");
  }
}

struct ChirpStateRecord {
  dl::ComplexInterval chirp;
  dl::ComplexInterval oddStep;
};

static_assert(sizeof(ChirpStateRecord) == 64U);
static_assert(std::is_standard_layout_v<ChirpStateRecord>);
static_assert(std::is_trivially_copyable_v<ChirpStateRecord>);

int parseChirpSign(const char* text) {
  if (text != nullptr &&
      (std::strcmp(text, "1") == 0 || std::strcmp(text, "+1") == 0)) {
    return 1;
  }
  if (text != nullptr && std::strcmp(text, "-1") == 0) return -1;
  throw std::runtime_error("chirp sign must be -1 or +1");
}

std::uint64_t checkedSquarePhase(std::uint64_t index,
                                 std::uint32_t length) {
  if (length == 0U ||
      static_cast<std::uint64_t>(length) >
          std::numeric_limits<std::uint64_t>::max() / 2U) {
    throw std::runtime_error("chirp denominator is zero or overflows");
  }
  if (index != 0U &&
      index > std::numeric_limits<std::uint64_t>::max() / index) {
    throw std::runtime_error("chirp square phase overflows");
  }
  return (index * index) % (2U * static_cast<std::uint64_t>(length));
}

std::uint64_t checkedOddStepPhase(std::uint64_t index,
                                  std::uint32_t length) {
  if (length == 0U ||
      static_cast<std::uint64_t>(length) >
          std::numeric_limits<std::uint64_t>::max() / 2U ||
      index > (std::numeric_limits<std::uint64_t>::max() - 1U) / 2U) {
    throw std::runtime_error("chirp odd-step phase overflows");
  }
  return (2U * index + 1U) %
         (2U * static_cast<std::uint64_t>(length));
}

void verifyRootRectangle(const dl::ComplexInterval& candidate,
                         const Complex& expected) {
  if (!std::isfinite(candidate.re.lo) ||
      !std::isfinite(candidate.re.hi) ||
      !std::isfinite(candidate.im.lo) ||
      !std::isfinite(candidate.im.hi) ||
      candidate.re.lo > candidate.re.hi ||
      candidate.im.lo > candidate.im.hi) {
    throw std::runtime_error("malformed root interval");
  }
  if (mpfr_cmp_d(expected.re.lo(), candidate.re.lo) < 0 ||
      mpfr_cmp_d(expected.re.hi(), candidate.re.hi) > 0 ||
      mpfr_cmp_d(expected.im.lo(), candidate.im.lo) < 0 ||
      mpfr_cmp_d(expected.im.hi(), candidate.im.hi) > 0) {
    throw std::runtime_error(
        "root interval does not enclose the direct MPFR root");
  }
}

void verifyChirpStateDump(const std::string& path, std::uint32_t length,
                          int sign) {
  if (length == 0U || length > da::kMaximumModulus) {
    throw std::runtime_error("chirp length is outside 1..400000");
  }
  std::ifstream file(path, std::ios::binary);
  if (!file) throw std::runtime_error("could not open chirp state dump");
  for (std::uint64_t n = 0U; n < length; ++n) {
    ChirpStateRecord candidate{};
    file.read(reinterpret_cast<char*>(&candidate), sizeof(candidate));
    if (!file) throw std::runtime_error("truncated chirp state dump");
    const Complex expectedChirp =
        root(checkedSquarePhase(n, length), length, sign);
    const Complex expectedOddStep =
        root(checkedOddStepPhase(n, length), length, sign);
    verifyRootRectangle(candidate.chirp, expectedChirp);
    verifyRootRectangle(candidate.oddStep, expectedOddStep);
  }
  if (file.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing chirp state dump bytes");
  }
}

bool sourceFftRootLength(std::uint32_t length) {
  return length >= 4U && length <= (1U << 20U) &&
         (length & (length - 1U)) == 0U;
}

void verifyFftRootDump(const std::string& path, std::uint32_t length,
                       int sign) {
  if (!sourceFftRootLength(length)) {
    throw std::runtime_error(
        "FFT-root length is outside the 19-entry source catalog");
  }
  std::ifstream file(path, std::ios::binary);
  if (!file) throw std::runtime_error("could not open FFT-root dump");
  for (std::uint32_t stage = 2U; stage <= length; stage <<= 1U) {
    const std::uint32_t half = stage / 2U;
    for (std::uint32_t j = 0U; j < half; ++j) {
      dl::ComplexInterval candidate{};
      file.read(reinterpret_cast<char*>(&candidate), sizeof(candidate));
      if (!file) throw std::runtime_error("truncated FFT-root dump");
      verifyRootRectangle(candidate, root(2ULL * j, stage, sign));
    }
  }
  if (file.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing FFT-root dump bytes");
  }
}

constexpr std::uint32_t kMaximumOrderDeltaOneQ = 399989U;
constexpr std::uint32_t kMaximumOrderDeltaOneLength = 399988U;
constexpr std::uint32_t kMaximumOrderDeltaOneConvolution = 1U << 20U;
constexpr std::uint32_t kMaximumOrderDeltaOneLogConvolution = 20U;
constexpr std::uint64_t kMaximumOrderDeltaOneButterflies =
    3ULL * (kMaximumOrderDeltaOneConvolution / 2ULL) *
    kMaximumOrderDeltaOneLogConvolution;

struct DeltaOneVerification {
  std::uint64_t checkedOutputCount = 0U;
  double maximumComponentWidth = 0.0;
};

DeltaOneVerification verifyMaximumOrderDeltaOne(
    const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) {
    throw std::runtime_error(
        "could not open maximum-order delta-one output");
  }
  da::OutputHeader header{};
  file.read(reinterpret_cast<char*>(&header), sizeof(header));
  if (!file || std::memcmp(header.magic, da::kOutputMagic, 8) != 0 ||
      header.version != da::kFormatVersion ||
      header.q != kMaximumOrderDeltaOneQ ||
      header.component_count != 1U || header.batch_count != 1U ||
      header.group_order != kMaximumOrderDeltaOneLength ||
      header.value_count != kMaximumOrderDeltaOneLength ||
      header.radix2_butterflies != kMaximumOrderDeltaOneButterflies) {
    throw std::runtime_error(
        "maximum-order delta-one output identity mismatch");
  }

  DeltaOneVerification result;
  for (std::uint64_t index = 0U;
       index < kMaximumOrderDeltaOneLength; ++index) {
    dl::ComplexInterval candidate{};
    file.read(reinterpret_cast<char*>(&candidate), sizeof(candidate));
    if (!file) {
      throw std::runtime_error(
          "truncated maximum-order delta-one output");
    }
    // For the positive-character convention, the DFT of delta_1 is the
    // exact root exp(2*pi*i*index/N).  This direct MPFR path is independent
    // of the CUDA producer's recurrence table and FFT indexing.
    verifyRootRectangle(
        candidate, root(2ULL * index, kMaximumOrderDeltaOneLength, +1));
    const double width = std::max(
        candidate.re.hi - candidate.re.lo,
        candidate.im.hi - candidate.im.lo);
    if (!std::isfinite(width)) {
      throw std::runtime_error(
          "non-finite maximum-order delta-one output width");
    }
    result.maximumComponentWidth =
        std::max(result.maximumComponentWidth, width);
    ++result.checkedOutputCount;
  }
  if (file.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error(
        "trailing maximum-order delta-one output bytes");
  }
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 4 &&
        std::strcmp(argv[1], "verify-max-order-delta-one") == 0) {
      const auto precision = parseUnsigned(argv[3], "precision");
      if (precision < 96U || precision > 4096U) {
        throw std::runtime_error("precision outside 96..4096");
      }
      gPrecision = static_cast<mpfr_prec_t>(precision);
      const auto start = std::chrono::steady_clock::now();
      const DeltaOneVerification result =
          verifyMaximumOrderDeltaOne(argv[2]);
      const auto stop = std::chrono::steady_clock::now();
      const auto elapsed = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              stop - start)
              .count());
      std::printf(
          "{\"algorithm\":"
          "\"platt-dirichlet-allchars-mpfr-max-order-delta-one-reference-v1\","
          "\"mode\":\"verify-max-order-delta-one\","
          "\"semantic\":\"positive_dft_delta_one\","
          "\"q\":%u,\"order\":%u,\"checked_output_count\":%llu,"
          "\"precision_bits\":%ld,\"elapsed_nanoseconds\":%llu,"
          "\"maximum_component_width\":%.17g}\n",
          kMaximumOrderDeltaOneQ, kMaximumOrderDeltaOneLength,
          static_cast<unsigned long long>(result.checkedOutputCount),
          static_cast<long>(gPrecision),
          static_cast<unsigned long long>(elapsed),
          result.maximumComponentWidth);
      return 0;
    }
    if (argc == 6 && std::strcmp(argv[1], "verify-fft-roots") == 0) {
      const auto length = parseUnsigned(argv[2], "FFT-root length");
      if (length > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("FFT-root length exceeds uint32");
      }
      const auto precision = parseUnsigned(argv[5], "precision");
      if (precision < 96U || precision > 4096U) {
        throw std::runtime_error("precision outside 96..4096");
      }
      gPrecision = static_cast<mpfr_prec_t>(precision);
      const int sign = parseChirpSign(argv[3]);
      const auto start = std::chrono::steady_clock::now();
      verifyFftRootDump(
          argv[4], static_cast<std::uint32_t>(length), sign);
      const auto stop = std::chrono::steady_clock::now();
      const auto elapsed = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              stop - start)
              .count());
      std::printf(
          "{\"algorithm\":"
          "\"platt-dirichlet-allchars-mpfr-fft-root-reference-v1\","
          "\"mode\":\"verify-fft-roots\",\"length\":%llu,"
          "\"sign\":%d,\"root_count\":%llu,"
          "\"precision_bits\":%ld,\"elapsed_nanoseconds\":%llu}\n",
          static_cast<unsigned long long>(length), sign,
          static_cast<unsigned long long>(length - 1U),
          static_cast<long>(gPrecision),
          static_cast<unsigned long long>(elapsed));
      return 0;
    }
    if (argc == 6 && std::strcmp(argv[1], "verify-chirp") == 0) {
      const auto length = parseUnsigned(argv[2], "chirp length");
      if (length > std::numeric_limits<std::uint32_t>::max()) {
        throw std::runtime_error("chirp length exceeds uint32");
      }
      const auto precision = parseUnsigned(argv[5], "precision");
      if (precision < 96U || precision > 4096U) {
        throw std::runtime_error("precision outside 96..4096");
      }
      gPrecision = static_cast<mpfr_prec_t>(precision);
      const int sign = parseChirpSign(argv[3]);
      const auto start = std::chrono::steady_clock::now();
      verifyChirpStateDump(
          argv[4], static_cast<std::uint32_t>(length), sign);
      const auto stop = std::chrono::steady_clock::now();
      const auto elapsed = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              stop - start).count());
      std::printf(
          "{\"algorithm\":"
          "\"platt-dirichlet-allchars-mpfr-chirp-reference-v1\","
          "\"mode\":\"verify-chirp\",\"length\":%llu,\"sign\":%d,"
          "\"state_count\":%llu,\"rectangle_count\":%llu,"
          "\"precision_bits\":%ld,\"elapsed_nanoseconds\":%llu}\n",
          static_cast<unsigned long long>(length), sign,
          static_cast<unsigned long long>(length),
          static_cast<unsigned long long>(2U * length),
          static_cast<long>(gPrecision),
          static_cast<unsigned long long>(elapsed));
      return 0;
    }
    if (argc < 4 || argc > 5) {
      throw std::runtime_error(
          "usage: checker (compute|verify) INPUT OUTPUT [PRECISION=192]\n"
          "   or: checker verify-max-order-delta-one OUTPUT PRECISION\n"
          "   or: checker verify-chirp LENGTH SIGN STATE_DUMP PRECISION\n"
          "   or: checker verify-fft-roots"
          " LENGTH SIGN ROOT_DUMP PRECISION");
    }
    if (argc == 5) {
      const auto precision = parseUnsigned(argv[4], "precision");
      if (precision < 96U || precision > 4096U) {
        throw std::runtime_error("precision outside 96..4096");
      }
      gPrecision = static_cast<mpfr_prec_t>(precision);
    }
    const Input input = readInput(argv[2]);
    const auto start = std::chrono::steady_clock::now();
    const auto expected = compute(input);
    const auto stop = std::chrono::steady_clock::now();
    const auto elapsed = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count());
    if (std::strcmp(argv[1], "compute") == 0) {
      writeOutput(argv[3], input, expected, elapsed);
    } else if (std::strcmp(argv[1], "verify") == 0) {
      verifyOutput(argv[3], input, expected);
    } else {
      throw std::runtime_error("mode must be compute or verify");
    }
    std::printf(
        "{\"algorithm\":\"platt-dirichlet-allchars-mpfr-reference-v1\","
        "\"q\":%u,\"group_order\":%llu,\"batch_count\":%u,"
        "\"value_count\":%zu,\"precision_bits\":%ld,"
        "\"elapsed_nanoseconds\":%llu,\"mode\":\"%s\"}\n",
        input.header.q,
        static_cast<unsigned long long>(input.header.group_order),
        input.header.batch_count, input.raw.size(), static_cast<long>(gPrecision),
        static_cast<unsigned long long>(elapsed), argv[1]);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "Dirichlet all-character MPFR error: %s\n",
                 error.what());
    return 2;
  }
}

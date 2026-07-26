// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Bounded qualification tool for the proved Bluestein chirp recurrence.
//
// This is not itself a trusted proof artifact.  It measures a source-shaped
// MPFR interval implementation of the recurrence formalized in
// SparkInterval/Dirichlet/BluesteinChirpRecurrence.lean and independently
// checks periodic entries against fresh directed sinpi/cospi evaluations.

#include <mpfr.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {

constexpr mpfr_prec_t kPrecision = 256;

struct Value {
  mpfr_t value;

  Value() { mpfr_init2(value, kPrecision); }
  ~Value() { mpfr_clear(value); }
  Value(const Value&) = delete;
  Value& operator=(const Value&) = delete;
};

struct RealInterval {
  Value lo;
  Value hi;
};

struct ComplexInterval {
  RealInterval re;
  RealInterval im;
};

struct Scratch {
  RealInterval ac;
  RealInterval bd;
  RealInterval ad;
  RealInterval bc;
  Value productLo;
  Value productHi;
  Value rationalLo;
  Value rationalHi;
  Value candidateLo;
  Value candidateHi;
};

std::uint64_t parseUnsigned(const char* text, const char* label) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  char* stop = nullptr;
  const unsigned long long value = std::strtoull(text, &stop, 10);
  if (stop == nullptr || *stop != '\0') {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<std::uint64_t>(value);
}

void point(RealInterval& output, long value) {
  mpfr_set_si(output.lo.value, value, MPFR_RNDD);
  mpfr_set_si(output.hi.value, value, MPFR_RNDU);
}

void includeCandidate(RealInterval& output, mpfr_srcptr lower,
                      mpfr_srcptr upper) {
  if (mpfr_less_p(lower, output.lo.value)) {
    mpfr_set(output.lo.value, lower, MPFR_RNDD);
  }
  if (mpfr_greater_p(upper, output.hi.value)) {
    mpfr_set(output.hi.value, upper, MPFR_RNDU);
  }
}

void trigInterval(RealInterval& output, std::uint64_t numerator,
                  std::uint64_t denominator, bool sine, Scratch& scratch) {
  if (denominator == 0) throw std::runtime_error("zero denominator");
  numerator %= 2 * denominator;
  mpq_t rational;
  mpq_init(rational);
  mpq_set_ui(rational, numerator, denominator);
  mpq_canonicalize(rational);
  mpfr_set_q(scratch.rationalLo.value, rational, MPFR_RNDD);
  mpfr_set_q(scratch.rationalHi.value, rational, MPFR_RNDU);
  if (sine) {
    mpfr_sinpi(output.lo.value, scratch.rationalLo.value, MPFR_RNDD);
    mpfr_sinpi(output.hi.value, scratch.rationalLo.value, MPFR_RNDU);
    mpfr_sinpi(scratch.candidateLo.value, scratch.rationalHi.value,
               MPFR_RNDD);
    mpfr_sinpi(scratch.candidateHi.value, scratch.rationalHi.value,
               MPFR_RNDU);
  } else {
    mpfr_cospi(output.lo.value, scratch.rationalLo.value, MPFR_RNDD);
    mpfr_cospi(output.hi.value, scratch.rationalLo.value, MPFR_RNDU);
    mpfr_cospi(scratch.candidateLo.value, scratch.rationalHi.value,
               MPFR_RNDD);
    mpfr_cospi(scratch.candidateHi.value, scratch.rationalHi.value,
               MPFR_RNDU);
  }
  includeCandidate(output, scratch.candidateLo.value,
                   scratch.candidateHi.value);
  mpq_clear(rational);
}

void unitRoot(ComplexInterval& output, std::uint64_t numerator,
              std::uint64_t denominator, Scratch& scratch) {
  trigInterval(output.re, numerator, denominator, false, scratch);
  trigInterval(output.im, numerator, denominator, true, scratch);
}

void realMul(RealInterval& output, const RealInterval& left,
             const RealInterval& right, Scratch& scratch) {
  mpfr_set_inf(output.lo.value, 1);
  mpfr_set_inf(output.hi.value, -1);
  mpfr_srcptr leftValues[2] = {left.lo.value, left.hi.value};
  mpfr_srcptr rightValues[2] = {right.lo.value, right.hi.value};
  for (mpfr_srcptr x : leftValues) {
    for (mpfr_srcptr y : rightValues) {
      mpfr_mul(scratch.productLo.value, x, y, MPFR_RNDD);
      mpfr_mul(scratch.productHi.value, x, y, MPFR_RNDU);
      includeCandidate(output, scratch.productLo.value,
                       scratch.productHi.value);
    }
  }
}

void realAdd(RealInterval& output, const RealInterval& left,
             const RealInterval& right) {
  mpfr_add(output.lo.value, left.lo.value, right.lo.value, MPFR_RNDD);
  mpfr_add(output.hi.value, left.hi.value, right.hi.value, MPFR_RNDU);
}

void realSub(RealInterval& output, const RealInterval& left,
             const RealInterval& right) {
  mpfr_sub(output.lo.value, left.lo.value, right.hi.value, MPFR_RNDD);
  mpfr_sub(output.hi.value, left.hi.value, right.lo.value, MPFR_RNDU);
}

void complexMul(ComplexInterval& output, const ComplexInterval& left,
                const ComplexInterval& right, Scratch& scratch) {
  realMul(scratch.ac, left.re, right.re, scratch);
  realMul(scratch.bd, left.im, right.im, scratch);
  realMul(scratch.ad, left.re, right.im, scratch);
  realMul(scratch.bc, left.im, right.re, scratch);
  realSub(output.re, scratch.ac, scratch.bd);
  realAdd(output.im, scratch.ad, scratch.bc);
}

bool containsMidpoint(const RealInterval& outer, const RealInterval& inner,
                      Value& midpoint) {
  mpfr_add(midpoint.value, inner.lo.value, inner.hi.value, MPFR_RNDN);
  mpfr_div_2ui(midpoint.value, midpoint.value, 1, MPFR_RNDN);
  return mpfr_lessequal_p(outer.lo.value, midpoint.value) &&
         mpfr_greaterequal_p(outer.hi.value, midpoint.value);
}

bool containsMidpoint(const ComplexInterval& outer,
                      const ComplexInterval& inner, Scratch& scratch) {
  return containsMidpoint(outer.re, inner.re, scratch.candidateLo) &&
         containsMidpoint(outer.im, inner.im, scratch.candidateHi);
}

double width(const RealInterval& interval, Value& temporary) {
  mpfr_sub(temporary.value, interval.hi.value, interval.lo.value, MPFR_RNDU);
  return mpfr_get_d(temporary.value, MPFR_RNDU);
}

struct Result {
  double seconds;
  double maximumWidth;
  std::uint64_t audited;
};

Result recurrenceBenchmark(std::uint64_t order, std::uint64_t count,
                           std::uint64_t auditStride,
                           std::uint64_t resetStride) {
  Scratch scratch;
  ComplexInterval chirp[2];
  ComplexInterval oddStep[2];
  ComplexInterval unit;
  ComplexInterval direct;
  Value widthTemporary;
  point(chirp[0].re, 1);
  point(chirp[0].im, 0);
  unitRoot(oddStep[0], 1, order, scratch);
  unitRoot(unit, 2, order, scratch);
  std::size_t active = 0;
  double maximumWidth = 0;
  std::uint64_t audited = 0;
  const auto start = std::chrono::steady_clock::now();
  for (std::uint64_t index = 0; index < count; ++index) {
    if (index != 0 && index % resetStride == 0) {
      const std::uint64_t square = index * index;
      unitRoot(chirp[active], square % (2 * order), order, scratch);
      unitRoot(oddStep[active], (2 * index + 1) % (2 * order), order,
               scratch);
    }
    maximumWidth =
        std::max({maximumWidth, width(chirp[active].re, widthTemporary),
                  width(chirp[active].im, widthTemporary)});
    if (index % auditStride == 0 || index + 1 == count) {
      const std::uint64_t square = index * index;
      const std::uint64_t reduced = square % (2 * order);
      unitRoot(direct, reduced, order, scratch);
      if (!containsMidpoint(chirp[active], direct, scratch)) {
        throw std::runtime_error(
            "recurrence interval missed independent direct midpoint");
      }
      ++audited;
    }
    const std::size_t next = 1 - active;
    complexMul(chirp[next], chirp[active], oddStep[active], scratch);
    complexMul(oddStep[next], oddStep[active], unit, scratch);
    active = next;
  }
  const auto stop = std::chrono::steady_clock::now();
  return {
      std::chrono::duration<double>(stop - start).count(),
      maximumWidth,
      audited,
  };
}

double directBenchmark(std::uint64_t order, std::uint64_t count) {
  Scratch scratch;
  ComplexInterval direct;
  const auto start = std::chrono::steady_clock::now();
  for (std::uint64_t index = 0; index < count; ++index) {
    const std::uint64_t square = index * index;
    const std::uint64_t reduced = square % (2 * order);
    unitRoot(direct, reduced, order, scratch);
  }
  const auto stop = std::chrono::steady_clock::now();
  return std::chrono::duration<double>(stop - start).count();
}

}  // namespace

int main(int argc, char** argv) try {
  if (argc != 6) {
    std::cerr << "usage: " << argv[0]
              << " ORDER RECURRENCE_COUNT DIRECT_COUNT AUDIT_STRIDE"
                 " RESET_STRIDE\n";
    return 2;
  }
  const std::uint64_t order = parseUnsigned(argv[1], "order");
  const std::uint64_t recurrenceCount =
      parseUnsigned(argv[2], "recurrence count");
  const std::uint64_t directCount = parseUnsigned(argv[3], "direct count");
  const std::uint64_t auditStride = parseUnsigned(argv[4], "audit stride");
  const std::uint64_t resetStride = parseUnsigned(argv[5], "reset stride");
  if (order == 0 || recurrenceCount == 0 || directCount == 0 ||
      auditStride == 0 || resetStride == 0 ||
      order > std::numeric_limits<std::uint64_t>::max() / 2) {
    throw std::runtime_error("arguments must be positive and 2*order must fit");
  }
  constexpr std::uint64_t kMaximumSquareCount =
      std::uint64_t{1} << 32;
  if (recurrenceCount > kMaximumSquareCount ||
      directCount > kMaximumSquareCount) {
    throw std::runtime_error("counts exceed the checked uint64 square range");
  }
  const Result recurrence =
      recurrenceBenchmark(order, recurrenceCount, auditStride, resetStride);
  const double directSeconds = directBenchmark(order, directCount);
  const double directRate = static_cast<double>(directCount) / directSeconds;
  const double recurrenceRate =
      static_cast<double>(recurrenceCount) / recurrence.seconds;
  std::cout << std::setprecision(17)
            << "{\"order\":" << order
            << ",\"precision_bits\":" << kPrecision
            << ",\"recurrence_count\":" << recurrenceCount
            << ",\"recurrence_seconds\":" << recurrence.seconds
            << ",\"recurrence_entries_per_second\":" << recurrenceRate
            << ",\"direct_count\":" << directCount
            << ",\"direct_seconds\":" << directSeconds
            << ",\"direct_entries_per_second\":" << directRate
            << ",\"speedup\":" << recurrenceRate / directRate
            << ",\"maximum_interval_width\":" << recurrence.maximumWidth
            << ",\"independent_direct_midpoint_audits\":"
            << recurrence.audited
            << ",\"reset_stride\":" << resetStride
            << ",\"transcendental_roots_per_reset\":2"
            << "}\n";
  return 0;
} catch (const std::exception& error) {
  std::cerr << "error: " << error.what() << '\n';
  return 1;
}

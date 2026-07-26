// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Rigorous MPFR CPU verifier for independent complete-q shards of Helfgott
// Proposition 12.2.4.  All transcendental operations and algebraic endpoints
// use outward MPFR rounding.  The finite G_q prefix uses exact GMP integers at
// scale 2^precision.  This is an external computation, not a Lean proof.

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#include <gmpxx.h>
#include <mpfr.h>

#include "sparkinterval/sha256.hpp"

namespace {

using u128 = unsigned __int128;

constexpr std::uint64_t kDenseRows = 3'299'999'999ULL;
constexpr std::uint64_t kFirstExtensionQ = 3'300'000'060ULL;
constexpr std::uint64_t kExtensionDivisor = 210ULL;
constexpr std::uint64_t kTerminalQ = 22'000'000'000ULL;
constexpr std::uint64_t kSourceRows = 3'389'047'618ULL;
constexpr char kDigestDomain[] =
    "sparkinterval/tg/prop1224/mpfr-directed-rows/v1\0";

struct Options {
  std::uint64_t lower = 0;
  std::uint64_t upper = 0;
  std::uint64_t segment = 250'000;
  mpfr_prec_t precision = 192;
};

mpfr_prec_t gPrecision = 192;

bool parseUint64(std::string_view text, std::uint64_t& result) {
  if (text.empty()) return false;
  const char* first = text.data();
  const char* last = first + text.size();
  const auto parsed = std::from_chars(first, last, result, 10);
  return parsed.ec == std::errc{} && parsed.ptr == last;
}

std::uint64_t qAtRank(std::uint64_t rank) {
  if (rank > kSourceRows) throw std::runtime_error("rank exceeds source domain");
  if (rank == kSourceRows) return kTerminalQ;
  if (rank < kDenseRows) return rank + 1;
  return kFirstExtensionQ + (rank - kDenseRows) * kExtensionDivisor;
}

std::uint64_t floorSqrt(std::uint64_t value) {
  std::uint64_t root = static_cast<std::uint64_t>(
      std::sqrt(static_cast<long double>(value)));
  while (static_cast<u128>(root + 1) * (root + 1) <= value) ++root;
  while (static_cast<u128>(root) * root > value) --root;
  return root;
}

std::vector<std::uint32_t> primesThrough(std::uint64_t upper) {
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

std::vector<std::uint64_t> distinctFactors(std::uint64_t value) {
  std::vector<std::uint64_t> factors;
  std::uint64_t remainder = value;
  for (std::uint64_t divisor = 2; divisor <= remainder / divisor;
       divisor = divisor == 2 ? 3 : divisor + 2) {
    if (remainder % divisor != 0) continue;
    factors.push_back(divisor);
    do {
      remainder /= divisor;
    } while (remainder % divisor == 0);
  }
  if (remainder > 1) factors.push_back(remainder);
  return factors;
}

std::uint64_t totient(std::uint64_t q,
                      const std::vector<std::uint64_t>& factors) {
  std::uint64_t result = q;
  for (const std::uint64_t prime : factors) result -= result / prime;
  return result;
}

class Interval {
 public:
  Interval() {
    mpfr_init2(lo_, gPrecision);
    mpfr_init2(hi_, gPrecision);
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

  static Interval zero() { return rational(0, 1); }
  static Interval integer(std::uint64_t value) {
    Interval result;
    mpfr_set_ui(result.lo_, value, MPFR_RNDD);
    mpfr_set_ui(result.hi_, value, MPFR_RNDU);
    return result;
  }
  static Interval rational(std::int64_t numerator,
                           std::uint64_t denominator) {
    if (denominator == 0) throw std::runtime_error("zero interval denominator");
    Interval result;
    mpfr_set_si(result.lo_, numerator, MPFR_RNDD);
    mpfr_div_ui(result.lo_, result.lo_, denominator, MPFR_RNDD);
    mpfr_set_si(result.hi_, numerator, MPFR_RNDU);
    mpfr_div_ui(result.hi_, result.hi_, denominator, MPFR_RNDU);
    return result;
  }
  static Interval endpoints(std::int64_t lowerNumerator,
                            std::uint64_t lowerDenominator,
                            std::int64_t upperNumerator,
                            std::uint64_t upperDenominator) {
    Interval result;
    mpfr_set_si(result.lo_, lowerNumerator, MPFR_RNDD);
    mpfr_div_ui(result.lo_, result.lo_, lowerDenominator, MPFR_RNDD);
    mpfr_set_si(result.hi_, upperNumerator, MPFR_RNDU);
    mpfr_div_ui(result.hi_, result.hi_, upperDenominator, MPFR_RNDU);
    return result;
  }

 private:
  mpfr_t lo_;
  mpfr_t hi_;
};

Interval add(const Interval& a, const Interval& b) {
  Interval r;
  mpfr_add(r.lo(), a.lo(), b.lo(), MPFR_RNDD);
  mpfr_add(r.hi(), a.hi(), b.hi(), MPFR_RNDU);
  return r;
}

Interval sub(const Interval& a, const Interval& b) {
  Interval r;
  mpfr_sub(r.lo(), a.lo(), b.hi(), MPFR_RNDD);
  mpfr_sub(r.hi(), a.hi(), b.lo(), MPFR_RNDU);
  return r;
}

Interval neg(const Interval& a) {
  Interval r;
  mpfr_neg(r.lo(), a.hi(), MPFR_RNDD);
  mpfr_neg(r.hi(), a.lo(), MPFR_RNDU);
  return r;
}

Interval mul(const Interval& a, const Interval& b) {
  Interval r;
  mpfr_t down;
  mpfr_t up;
  mpfr_init2(down, gPrecision);
  mpfr_init2(up, gPrecision);
  bool first = true;
  for (mpfr_srcptr x : {a.lo(), a.hi()}) {
    for (mpfr_srcptr y : {b.lo(), b.hi()}) {
      mpfr_mul(down, x, y, MPFR_RNDD);
      mpfr_mul(up, x, y, MPFR_RNDU);
      if (first || mpfr_less_p(down, r.lo())) mpfr_set(r.lo(), down, MPFR_RNDD);
      if (first || mpfr_greater_p(up, r.hi())) mpfr_set(r.hi(), up, MPFR_RNDU);
      first = false;
    }
  }
  mpfr_clear(down);
  mpfr_clear(up);
  return r;
}

Interval reciprocal(const Interval& a) {
  if (mpfr_sgn(a.lo()) <= 0) throw std::runtime_error("nonpositive denominator");
  Interval r;
  mpfr_ui_div(r.lo(), 1, a.hi(), MPFR_RNDD);
  mpfr_ui_div(r.hi(), 1, a.lo(), MPFR_RNDU);
  return r;
}

Interval divi(const Interval& a, const Interval& b) {
  return mul(a, reciprocal(b));
}

Interval expi(const Interval& a) {
  Interval r;
  mpfr_exp(r.lo(), a.lo(), MPFR_RNDD);
  mpfr_exp(r.hi(), a.hi(), MPFR_RNDU);
  return r;
}

Interval logi(const Interval& a) {
  if (mpfr_sgn(a.lo()) <= 0) throw std::runtime_error("log of nonpositive interval");
  Interval r;
  mpfr_log(r.lo(), a.lo(), MPFR_RNDD);
  mpfr_log(r.hi(), a.hi(), MPFR_RNDU);
  return r;
}

Interval powNat(Interval base, unsigned exponent) {
  Interval result = Interval::integer(1);
  while (exponent != 0) {
    if ((exponent & 1U) != 0) result = mul(result, base);
    exponent >>= 1U;
    if (exponent != 0) base = mul(base, base);
  }
  return result;
}

Interval rpow(const Interval& base, const Interval& exponent) {
  return expi(mul(logi(base), exponent));
}

Interval cubeRoot(std::uint64_t value) {
  Interval r;
  mpfr_set_ui(r.lo(), value, MPFR_RNDD);
  mpfr_rootn_ui(r.lo(), r.lo(), 3, MPFR_RNDD);
  mpfr_set_ui(r.hi(), value, MPFR_RNDU);
  mpfr_rootn_ui(r.hi(), r.hi(), 3, MPFR_RNDU);
  return r;
}

Interval maximum(const Interval& a, const Interval& b, const Interval& c) {
  Interval r;
  mpfr_max(r.lo(), a.lo(), b.lo(), MPFR_RNDD);
  mpfr_max(r.lo(), r.lo(), c.lo(), MPFR_RNDD);
  mpfr_max(r.hi(), a.hi(), b.hi(), MPFR_RNDU);
  mpfr_max(r.hi(), r.hi(), c.hi(), MPFR_RNDU);
  return r;
}

std::uint64_t ceilToUint(mpfr_srcptr value) {
  if (mpfr_sgn(value) < 0) throw std::runtime_error("negative endpoint ceiling");
  mpfr_t rounded;
  mpfr_init2(rounded, gPrecision);
  mpfr_ceil(rounded, value);
  if (!mpfr_fits_ulong_p(rounded, MPFR_RNDN)) {
    mpfr_clear(rounded);
    throw std::runtime_error("endpoint ceiling exceeds unsigned long");
  }
  const std::uint64_t result = mpfr_get_ui(rounded, MPFR_RNDN);
  mpfr_clear(rounded);
  return result;
}

std::string hexFloat(mpfr_srcptr value) {
  char* text = nullptr;
  if (mpfr_asprintf(&text, "%Ra", value) < 0 || text == nullptr) {
    throw std::runtime_error("could not encode MPFR endpoint");
  }
  std::string result(text);
  mpfr_free_str(text);
  return result;
}

struct Parameters {
  std::uint64_t q = 0;
  std::uint64_t phi = 0;
  std::vector<std::uint64_t> factors;
  Interval logQ;
  Interval logPrimeSum;
  Interval f1;
  Interval varpi;
  Interval lambda;
};

Parameters makeParameters(std::uint64_t q) {
  const Interval one = Interval::integer(1);
  const Interval omega = Interval::rational(627'312ULL, 1'000'000ULL);
  const Interval gamma = Interval::endpoints(
      577'215'657, 1'000'000'000ULL, 5'772'162, 10'000'000ULL);
  const Interval ce = Interval::endpoints(
      13'325'822, 10'000'000ULL, 13'339, 10'000ULL);
  Parameters p;
  p.q = q;
  p.factors = distinctFactors(q);
  p.phi = totient(q, p.factors);
  p.logQ = logi(Interval::integer(q));
  p.logPrimeSum = Interval::zero();
  for (const std::uint64_t prime : p.factors) {
    p.logPrimeSum = add(
        p.logPrimeSum,
        mul(logi(Interval::integer(prime)), Interval::rational(1ULL, prime)));
  }
  const Interval expMinusGamma = expi(neg(gamma));
  const Interval tau = mul(Interval::rational(2ULL, 5ULL), expMinusGamma);
  const Interval cSigma = expi(mul(
      expMinusGamma, Interval::rational(-3'371, 20'500ULL)));
  const Interval c2 = expi(add(
      Interval::rational(1'109ULL, 10'000ULL),
      mul(omega, sub(ce, Interval::rational(164ULL, 125ULL)))));
  const Interval kappa = add(
      mul(sub(one, omega), sub(p.logQ, p.logPrimeSum)),
      sub(Interval::rational(34ULL, 25ULL), ce));
  if (mpfr_sgn(kappa.lo()) <= 0) throw std::runtime_error("kappa is not positive");

  p.f1 = one;
  for (const std::uint64_t prime : p.factors) {
    const Interval root = cubeRoot(prime);
    const Interval twoThirds = mul(root, root);
    const Interval numerator = add(one, reciprocal(twoThirds));
    const Interval denominator = add(
        one,
        mul(add(root, twoThirds),
            Interval::rational(1ULL, prime * (prime - 1ULL))));
    p.f1 = mul(p.f1, divi(numerator, denominator));
  }
  const Interval lambdaBase = divi(
      mul(mul(Interval::rational(q, p.phi),
              Interval::rational(1'863'085'131ULL, 250'000'000ULL)),
          p.f1),
      kappa);
  p.lambda = powNat(lambdaBase, 3);

  const Interval a = mul(cSigma, rpow(Interval::integer(q), tau));
  const Interval gate = add(one, p.logQ);
  Interval varpiZero;
  if (mpfr_less_p(gate.hi(), a.lo())) {
    const Interval difference = sub(a, p.logQ);
    if (mpfr_sgn(difference.lo()) <= 0) {
      throw std::runtime_error("varpiZero inner difference is not positive");
    }
    const Interval exponent = neg(divi(tau, sub(one, tau)));
    const Interval correction = rpow(difference, exponent);
    const Interval inner = sub(a, mul(p.logQ, correction));
    if (mpfr_sgn(inner.lo()) <= 0) {
      throw std::runtime_error("varpiZero outer base is not positive");
    }
    varpiZero = rpow(inner, reciprocal(sub(one, tau)));
  } else if (mpfr_greaterequal_p(gate.lo(), a.hi())) {
    varpiZero = Interval::zero();
  } else {
    throw std::runtime_error("precision does not decide varpiZero branch");
  }
  const Interval varpiMiddle = sub(
      mul(cSigma, rpow(Interval::integer(100'000), tau)), p.logQ);
  const Interval omegaExponent = reciprocal(sub(one, omega));
  const Interval varpiLast = divi(
      Interval::integer(100'000),
      rpow(mul(c2, Interval::integer(q)), omegaExponent));
  p.varpi = maximum(varpiZero, varpiMiddle, varpiLast);
  return p;
}

Interval gUpperInterval(const mpz_class& units, mpfr_prec_t bits) {
  Interval result;
  mpfr_set_z(result.lo(), units.get_mpz_t(), MPFR_RNDD);
  mpfr_div_2ui(result.lo(), result.lo(), bits, MPFR_RNDD);
  mpfr_set_z(result.hi(), units.get_mpz_t(), MPFR_RNDU);
  mpfr_div_2ui(result.hi(), result.hi(), bits, MPFR_RNDU);
  return result;
}

Interval margin(const Parameters& p, std::uint64_t k,
                const mpz_class& gUpper, mpfr_prec_t bits) {
  const Interval one = Interval::integer(1);
  const Interval omega = Interval::rational(627'312ULL, 1'000'000ULL);
  const Interval inner = add(
      add(mul(sub(one, omega), p.logQ), mul(omega, p.logPrimeSum)),
      add(Interval::rational(34ULL, 25ULL), logi(Interval::integer(k))));
  const Interval rightMinusError = sub(
      mul(Interval::rational(p.phi, p.q), inner),
      gUpperInterval(gUpper, bits));
  const Interval remote = mul(
      mul(Interval::rational(1'142'335'152ULL, 250'000'000ULL),
          reciprocal(cubeRoot(20'000ULL * k))),
      p.f1);
  return sub(rightMinusError, remote);
}

template <typename Callback>
void forTotientSquarefree(std::uint64_t lower, std::uint64_t upper,
                          std::uint64_t segmentSize, Callback callback) {
  for (std::uint64_t lo = lower; lo < upper;) {
    const std::uint64_t hi = std::min(upper, lo + segmentSize);
    const std::size_t size = static_cast<std::size_t>(hi - lo);
    std::vector<std::uint64_t> phi(size);
    std::vector<std::uint64_t> remainder(size);
    std::vector<std::uint8_t> squarefree(size, 1);
    for (std::size_t index = 0; index < size; ++index) {
      phi[index] = lo + index;
      remainder[index] = lo + index;
    }
    const auto primes = primesThrough(floorSqrt(hi - 1));
    for (const std::uint64_t prime : primes) {
      std::uint64_t first = lo + ((prime - lo % prime) % prime);
      for (std::uint64_t multiple = first; multiple < hi; multiple += prime) {
        const std::size_t index = static_cast<std::size_t>(multiple - lo);
        phi[index] -= phi[index] / prime;
        unsigned exponent = 0;
        while (remainder[index] % prime == 0) {
          remainder[index] /= prime;
          ++exponent;
        }
        if (exponent > 1) squarefree[index] = 0;
      }
    }
    for (std::size_t index = 0; index < size; ++index) {
      if (remainder[index] > 1) phi[index] -= phi[index] / remainder[index];
      callback(lo + index, phi[index], squarefree[index] != 0);
    }
    lo = hi;
  }
}

Options parseOptions(int argc, char** argv) {
  Options o;
  bool haveLower = false;
  bool haveUpper = false;
  for (int i = 1; i < argc; ++i) {
    const std::string_view name(argv[i]);
    if (i + 1 >= argc) throw std::runtime_error("missing option value");
    std::uint64_t value = 0;
    if (!parseUint64(argv[++i], value)) throw std::runtime_error("invalid integer option");
    if (name == "--rank-lower") {
      o.lower = value;
      haveLower = true;
    } else if (name == "--rank-upper") {
      o.upper = value;
      haveUpper = true;
    } else if (name == "--segment-size") {
      o.segment = value;
    } else if (name == "--precision-bits") {
      if (value > static_cast<std::uint64_t>(std::numeric_limits<mpfr_prec_t>::max())) {
        throw std::runtime_error("precision exceeds mpfr_prec_t");
      }
      o.precision = static_cast<mpfr_prec_t>(value);
    } else {
      throw std::runtime_error("unknown option: " + std::string(name));
    }
  }
  if (!haveLower || !haveUpper || o.lower >= o.upper || o.upper > kSourceRows ||
      o.segment == 0 || o.segment > 100'000'000 || o.precision < 128 ||
      o.precision > 4096) {
    throw std::runtime_error(
        "require a nonempty source rank range, 1<=segment<=1e8, and "
        "128<=precision<=4096");
  }
  return o;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parseOptions(argc, argv);
    gPrecision = options.precision;
    const mpz_class scale = mpz_class(1) << options.precision;
    sparkinterval::detail::Sha256 digest;
    digest.update(kDigestDomain, sizeof(kDigestDomain) - 1);
    std::uint64_t emptyRows = 0;
    std::uint64_t nonemptyRows = 0;
    std::uint64_t rSteps = 0;
    std::uint64_t kRows = 0;
    bool haveMinimum = false;
    Interval minimum;
    const auto started = std::chrono::steady_clock::now();
    for (std::uint64_t rank = options.lower; rank < options.upper; ++rank) {
      const Parameters p = makeParameters(qAtRank(rank));
      const std::uint64_t first = std::max<std::uint64_t>(1, ceilToUint(p.varpi.lo()));
      const std::uint64_t lambdaCeil = ceilToUint(p.lambda.hi());
      const std::uint64_t last = lambdaCeil == 0 ? 0 : lambdaCeil - 1;
      std::ostringstream header;
      header << "Q:" << rank << ':' << p.q << ':' << p.phi << ':';
      for (std::size_t i = 0; i < p.factors.size(); ++i) {
        if (i != 0) header << ',';
        header << p.factors[i];
      }
      header << ':' << first << ':' << last << '\n';
      const std::string headerLine = header.str();
      digest.update(headerLine.data(), headerLine.size());
      if (last < first) {
        ++emptyRows;
        continue;
      }
      ++nonemptyRows;
      mpz_class gLower = 0;
      mpz_class gUpper = 0;
      forTotientSquarefree(
          1, last + 1, options.segment,
          [&](std::uint64_t r, std::uint64_t phiR, bool squarefree) {
            const bool coprime = std::gcd(r, p.q) == 1;
            if (squarefree && coprime) {
              const mpz_class divisor(phiR);
              gLower += scale / divisor;
              gUpper += (scale + divisor - 1) / divisor;
            }
            ++rSteps;
            if (r < first) return;
            const Interval current = margin(p, r, gUpper, options.precision);
            if (mpfr_sgn(current.lo()) < 0) {
              throw std::runtime_error(
                  "negative directed margin at rank=" + std::to_string(rank) +
                  ", q=" + std::to_string(p.q) + ", k=" + std::to_string(r));
            }
            if (!haveMinimum || mpfr_less_p(current.lo(), minimum.lo())) {
              minimum = current;
              haveMinimum = true;
            }
            ++kRows;
            const std::string row =
                "K:" + std::to_string(rank) + ':' + std::to_string(p.q) + ':' +
                std::to_string(r) + ':' + gUpper.get_str() + ':' +
                hexFloat(current.lo()) + '\n';
            digest.update(row.data(), row.size());
          });
    }
    const double elapsed = std::chrono::duration<double>(
                               std::chrono::steady_clock::now() - started)
                               .count();
    const std::uint64_t rows = options.upper - options.lower;
    std::cout << "{\n"
              << "  \"algorithm\": \"prop1224-mpfr-directed-independent-q-shard-v1\",\n"
              << "  \"classification\": \"directed-external-computation-not-lean-proof\",\n"
              << "  \"rank_lower\": " << options.lower << ",\n"
              << "  \"rank_upper\": " << options.upper << ",\n"
              << "  \"work_count\": " << rows << ",\n"
              << "  \"first_q\": " << qAtRank(options.lower) << ",\n"
              << "  \"next_q\": " << qAtRank(options.upper) << ",\n"
              << "  \"precision_bits\": " << options.precision << ",\n"
              << "  \"segment_size\": " << options.segment << ",\n"
              << "  \"empty_q_rows\": " << emptyRows << ",\n"
              << "  \"nonempty_q_rows\": " << nonemptyRows << ",\n"
              << "  \"r_steps\": " << rSteps << ",\n"
              << "  \"conservative_k_rows_checked\": " << kRows << ",\n"
              << "  \"minimum_margin_lower_hex\": "
              << (haveMinimum ? "\"" + hexFloat(minimum.lo()) + "\"" : "null")
              << ",\n"
              << "  \"row_root_sha256\": \""
              << sparkinterval::lowercase_hex(digest.finish()) << "\",\n"
              << "  \"mpfr_version\": \"" << mpfr_get_version() << "\",\n"
              << "  \"elapsed_seconds\": " << elapsed << ",\n"
              << "  \"rows_per_second\": "
              << (elapsed == 0.0 ? 0.0 : static_cast<double>(rows) / elapsed)
              << ",\n"
              << "  \"execution_attested\": false,\n"
              << "  \"lean_realization_proved\": false,\n"
              << "  \"lean_atom_discharged\": false\n"
              << "}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "Proposition 12.2.4 MPFR shard error: " << error.what() << '\n';
    return 2;
  }
}

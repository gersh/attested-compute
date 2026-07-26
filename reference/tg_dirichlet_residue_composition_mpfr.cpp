// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Independent higher-precision replay for the large-q residue-composition
// adapter.  This program shares binary formats, but no interval operators or
// q^(-s) implementation, with the Python producer.  It does not replay the
// Hurwitz Taylor stage and it does not close Platt's theorem.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_dirichlet_allchars.hpp"
#include "sparkinterval/tg_dirichlet_lattice.hpp"

#include <mpfr.h>

#include <algorithm>
#include <bit>
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
#include <tuple>
#include <utility>
#include <vector>

namespace da = sparkinterval::tg::dirichlet_allchars;
namespace dl = sparkinterval::tg::dirichlet_lattice;

namespace {

constexpr char kRecoveryMagic[8] = {'T', 'G', 'D', 'L', 'R', 'E', 'C', '1'};
constexpr std::uint32_t kRecoveryVersion = 1U;
constexpr std::uint32_t kLargeQStart = 10001U;
constexpr std::uint32_t kLargeQStop = 400000U;
constexpr std::uint64_t kSourceDenominator = 64U;
constexpr std::uint64_t kSourceStep = 5U;

std::uint64_t maximumTIndex(std::uint32_t q) {
  const std::uint64_t additive =
      (q % 2U == 0U) ? 75000000ULL : 37500000ULL;
  const std::uint64_t heightNumerator =
      std::max<std::uint64_t>(100000000ULL, 200ULL * q + additive);
  return heightNumerator * kSourceDenominator /
         (static_cast<std::uint64_t>(q) * kSourceStep);
}

#pragma pack(push, 1)
struct RecoveryHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t m;
  std::uint32_t reserved0;
  std::int64_t tNumerator;
  std::uint64_t tDenominator;
  std::uint64_t count;
  std::uint64_t reserved1;
};
#pragma pack(pop)

struct RecoveryItem {
  std::uint32_t q;
  std::uint32_t a;
  std::uint32_t reserved0;
  std::uint32_t reserved1;
  dl::ComplexInterval value;
};

static_assert(sizeof(RecoveryHeader) == 52U);
static_assert(sizeof(RecoveryItem) == 48U);

mpfr_prec_t gPrecision = 384;

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
    if (!std::isfinite(lo) || !std::isfinite(hi) || lo > hi) {
      throw std::runtime_error("malformed binary64 interval");
    }
    Interval result;
    mpfr_set_d(result.lo_, lo, MPFR_RNDD);
    mpfr_set_d(result.hi_, hi, MPFR_RNDU);
    return result;
  }

  static Interval exactUnsigned(std::uint64_t value) {
    Interval result;
    mpfr_set_uj(result.lo_, value, MPFR_RNDN);
    mpfr_set_uj(result.hi_, value, MPFR_RNDN);
    return result;
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
  Interval result;
  mpfr_add(result.lo(), a.lo(), b.lo(), MPFR_RNDD);
  mpfr_add(result.hi(), a.hi(), b.hi(), MPFR_RNDU);
  return result;
}

Interval sub(const Interval& a, const Interval& b) {
  Interval result;
  mpfr_sub(result.lo(), a.lo(), b.hi(), MPFR_RNDD);
  mpfr_sub(result.hi(), a.hi(), b.lo(), MPFR_RNDU);
  return result;
}

Interval mul(const Interval& a, const Interval& b) {
  Interval result;
  mpfr_t down, up;
  mpfr_init2(down, gPrecision);
  mpfr_init2(up, gPrecision);
  bool first = true;
  for (mpfr_srcptr x : {a.lo(), a.hi()}) {
    for (mpfr_srcptr y : {b.lo(), b.hi()}) {
      mpfr_mul(down, x, y, MPFR_RNDD);
      mpfr_mul(up, x, y, MPFR_RNDU);
      if (first || mpfr_less_p(down, result.lo())) {
        mpfr_set(result.lo(), down, MPFR_RNDD);
      }
      if (first || mpfr_greater_p(up, result.hi())) {
        mpfr_set(result.hi(), up, MPFR_RNDU);
      }
      first = false;
    }
  }
  mpfr_clear(up);
  mpfr_clear(down);
  return result;
}

Complex add(const Complex& a, const Complex& b) {
  return {add(a.re, b.re), add(a.im, b.im)};
}

Complex mul(const Complex& a, const Complex& b) {
  return {sub(mul(a.re, b.re), mul(a.im, b.im)),
          add(mul(a.re, b.im), mul(a.im, b.re))};
}

Complex exact(const dl::ComplexInterval& value) {
  return {Interval::fromDouble(value.re.lo, value.re.hi),
          Interval::fromDouble(value.im.lo, value.im.hi)};
}

Interval trigLipschitz(mpfr_srcptr angleLo, mpfr_srcptr angleHi, bool sine) {
  mpfr_t width;
  mpfr_init2(width, gPrecision);
  mpfr_sub(width, angleHi, angleLo, MPFR_RNDU);
  Interval result;
  if (sine) {
    mpfr_sin(result.lo(), angleLo, MPFR_RNDD);
    mpfr_sin(result.hi(), angleLo, MPFR_RNDU);
  } else {
    mpfr_cos(result.lo(), angleLo, MPFR_RNDD);
    mpfr_cos(result.hi(), angleLo, MPFR_RNDU);
  }
  mpfr_sub(result.lo(), result.lo(), width, MPFR_RNDD);
  mpfr_add(result.hi(), result.hi(), width, MPFR_RNDU);
  if (mpfr_cmp_si(result.lo(), -1) < 0) mpfr_set_si(result.lo(), -1, MPFR_RNDN);
  if (mpfr_cmp_si(result.hi(), 1) > 0) mpfr_set_si(result.hi(), 1, MPFR_RNDN);
  mpfr_clear(width);
  return result;
}

Complex qMinusS(std::uint32_t q, std::uint64_t tNumerator,
                std::uint64_t tDenominator) {
  mpfr_t qExact, logLo, logHi, angleLo, angleHi, sqrtLo, sqrtHi;
  for (mpfr_ptr value :
       {qExact, logLo, logHi, angleLo, angleHi, sqrtLo, sqrtHi}) {
    mpfr_init2(value, gPrecision);
  }
  mpfr_set_ui(qExact, q, MPFR_RNDN);
  mpfr_log(logLo, qExact, MPFR_RNDD);
  mpfr_log(logHi, qExact, MPFR_RNDU);
  if (tNumerator > std::numeric_limits<unsigned long>::max() ||
      tDenominator > std::numeric_limits<unsigned long>::max()) {
    throw std::runtime_error("ordinate does not fit MPFR integer operation");
  }
  mpfr_mul_ui(angleLo, logLo, static_cast<unsigned long>(tNumerator),
              MPFR_RNDD);
  mpfr_div_ui(angleLo, angleLo, static_cast<unsigned long>(tDenominator),
              MPFR_RNDD);
  mpfr_mul_ui(angleHi, logHi, static_cast<unsigned long>(tNumerator),
              MPFR_RNDU);
  mpfr_div_ui(angleHi, angleHi, static_cast<unsigned long>(tDenominator),
              MPFR_RNDU);
  mpfr_sqrt(sqrtLo, qExact, MPFR_RNDD);
  mpfr_sqrt(sqrtHi, qExact, MPFR_RNDU);
  Interval inverse;
  mpfr_ui_div(inverse.lo(), 1U, sqrtHi, MPFR_RNDD);
  mpfr_ui_div(inverse.hi(), 1U, sqrtLo, MPFR_RNDU);
  Interval cosine = trigLipschitz(angleLo, angleHi, false);
  Interval sine = trigLipschitz(angleLo, angleHi, true);
  Interval negativeSine;
  mpfr_neg(negativeSine.lo(), sine.hi(), MPFR_RNDD);
  mpfr_neg(negativeSine.hi(), sine.lo(), MPFR_RNDU);
  Complex result{mul(inverse, cosine), mul(inverse, negativeSine)};
  for (mpfr_ptr value :
       {sqrtHi, sqrtLo, angleHi, angleLo, logHi, logLo, qExact}) {
    mpfr_clear(value);
  }
  return result;
}

bool contains(const dl::ComplexInterval& outer, const Complex& inner) {
  if (!std::isfinite(outer.re.lo) || !std::isfinite(outer.re.hi) ||
      !std::isfinite(outer.im.lo) || !std::isfinite(outer.im.hi) ||
      outer.re.lo > outer.re.hi || outer.im.lo > outer.im.hi) {
    return false;
  }
  mpfr_t endpoint;
  mpfr_init2(endpoint, gPrecision);
  mpfr_set_d(endpoint, outer.re.lo, MPFR_RNDN);
  bool answer = mpfr_lessequal_p(endpoint, inner.re.lo()) != 0;
  mpfr_set_d(endpoint, outer.re.hi, MPFR_RNDN);
  answer = answer && mpfr_greaterequal_p(endpoint, inner.re.hi()) != 0;
  mpfr_set_d(endpoint, outer.im.lo, MPFR_RNDN);
  answer = answer && mpfr_lessequal_p(endpoint, inner.im.lo()) != 0;
  mpfr_set_d(endpoint, outer.im.hi, MPFR_RNDN);
  answer = answer && mpfr_greaterequal_p(endpoint, inner.im.hi()) != 0;
  mpfr_clear(endpoint);
  return answer;
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
  std::uint64_t result = 1U;
  base %= modulus;
  while (exponent != 0U) {
    if ((exponent & 1U) != 0U) result = (result * base) % modulus;
    base = (base * base) % modulus;
    exponent >>= 1U;
  }
  return result;
}

std::uint64_t inverseMod(std::uint64_t value, std::uint64_t modulus) {
  std::int64_t t = 0;
  std::int64_t nextT = 1;
  std::int64_t r = static_cast<std::int64_t>(modulus);
  std::int64_t nextR = static_cast<std::int64_t>(value);
  while (nextR != 0) {
    const std::int64_t quotient = r / nextR;
    std::tie(t, nextT) = std::pair{nextT, t - quotient * nextT};
    std::tie(r, nextR) = std::pair{nextR, r - quotient * nextR};
  }
  if (r != 1) throw std::runtime_error("CRT inverse does not exist");
  t %= static_cast<std::int64_t>(modulus);
  if (t < 0) t += static_cast<std::int64_t>(modulus);
  return static_cast<std::uint64_t>(t);
}

std::vector<std::uint32_t> primeDivisors(std::uint32_t n) {
  std::vector<std::uint32_t> values;
  for (std::uint32_t p = 2U;
       static_cast<std::uint64_t>(p) * p <= n; ++p) {
    if (n % p != 0U) continue;
    values.push_back(p);
    do {
      n /= p;
    } while (n % p == 0U);
  }
  if (n > 1U) values.push_back(n);
  return values;
}

std::uint32_t primitiveRoot(std::uint32_t modulus, std::uint32_t prime) {
  const std::uint32_t order = modulus - modulus / prime;
  const auto divisors = primeDivisors(order);
  for (std::uint32_t candidate = 2U; candidate < modulus; ++candidate) {
    if (std::gcd(candidate, modulus) != 1U) continue;
    bool works = true;
    for (const auto divisor : divisors) {
      if (powMod(candidate, order / divisor, modulus) == 1U) {
        works = false;
        break;
      }
    }
    if (works) return candidate;
  }
  throw std::runtime_error("primitive-root reconstruction failed");
}

struct Component {
  std::uint32_t generator;
  std::uint32_t order;
};

struct Factor {
  std::uint32_t modulus;
  std::vector<Component> components;
};

std::vector<Factor> canonicalModel(std::uint32_t q) {
  std::vector<Factor> result;
  std::uint32_t rest = q;
  for (std::uint32_t p = 2U;
       static_cast<std::uint64_t>(p) * p <= rest; ++p) {
    if (rest % p != 0U) continue;
    std::uint32_t exponent = 0U;
    std::uint32_t power = 1U;
    while (rest % p == 0U) {
      rest /= p;
      power *= p;
      ++exponent;
    }
    Factor factor{power, {}};
    if (p == 2U) {
      if (exponent == 2U) factor.components.push_back({3U, 2U});
      if (exponent > 2U) {
        factor.components.push_back({power - 1U, 2U});
        factor.components.push_back({5U, 1U << (exponent - 2U)});
      }
    } else {
      factor.components.push_back(
          {primitiveRoot(power, p), power - power / p});
    }
    result.push_back(std::move(factor));
  }
  if (rest > 1U) {
    result.push_back(Factor{rest, {{primitiveRoot(rest, rest), rest - 1U}}});
  }
  return result;
}

std::vector<std::uint32_t> canonicalResidues(std::uint32_t q) {
  const auto model = canonicalModel(q);
  std::vector<std::uint32_t> orders;
  for (const auto& factor : model) {
    for (const auto& component : factor.components) {
      orders.push_back(component.order);
    }
  }
  std::uint64_t order = 1U;
  for (const auto value : orders) order *= value;
  std::vector<std::uint32_t> result;
  result.reserve(static_cast<std::size_t>(order));
  for (std::uint64_t ordinal = 0; ordinal < order; ++ordinal) {
    std::vector<std::uint32_t> coordinates;
    std::uint64_t remaining = ordinal;
    for (const auto radix : orders) {
      coordinates.push_back(static_cast<std::uint32_t>(remaining % radix));
      remaining /= radix;
    }
    if (remaining != 0U) throw std::runtime_error("coordinate overflow");
    std::uint64_t residue = 0U;
    std::size_t coordinate = 0U;
    for (const auto& factor : model) {
      std::uint64_t local = 1U;
      for (const auto& component : factor.components) {
        local = (local * powMod(component.generator, coordinates[coordinate],
                                factor.modulus)) %
                factor.modulus;
        ++coordinate;
      }
      const std::uint64_t cofactor = q / factor.modulus;
      residue =
          (residue + local * cofactor *
                         inverseMod(cofactor % factor.modulus, factor.modulus)) %
          q;
    }
    result.push_back(static_cast<std::uint32_t>(residue));
  }
  auto sorted = result;
  std::sort(sorted.begin(), sorted.end());
  std::vector<std::uint32_t> expected;
  for (std::uint32_t a = 1U; a < q; ++a) {
    if (std::gcd(a, q) == 1U) expected.push_back(a);
  }
  if (sorted != expected) {
    throw std::runtime_error("canonical CRT order is not the unit group");
  }
  return result;
}

template <typename T>
T readObject(std::ifstream& input, const char* label) {
  T result{};
  input.read(reinterpret_cast<char*>(&result), sizeof(result));
  if (!input) throw std::runtime_error(std::string("short ") + label);
  return result;
}

template <typename T>
std::vector<T> readVector(std::ifstream& input, std::uint64_t count,
                          const char* label) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(std::string(label) + " count overflows memory");
  }
  std::vector<T> result(static_cast<std::size_t>(count));
  input.read(reinterpret_cast<char*>(result.data()),
             static_cast<std::streamsize>(result.size() * sizeof(T)));
  if (!input) throw std::runtime_error(std::string("short ") + label);
  return result;
}

std::string sha256File(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot hash input file");
  sparkinterval::detail::Sha256 digest;
  std::vector<char> buffer(1U << 20U);
  while (input) {
    input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    const auto count = input.gcount();
    if (count > 0) digest.update(buffer.data(), static_cast<std::size_t>(count));
  }
  if (!input.eof()) throw std::runtime_error("file hash read failed");
  return sparkinterval::lowercase_hex(digest.finish());
}

void verifyFrame(const std::filesystem::path& taylorPath,
                 const std::filesystem::path& recoveryPath,
                 const da::InputHeader& composedHeader,
                 const std::vector<std::uint32_t>& residues,
                 const std::vector<dl::ComplexInterval>& composed,
                 std::uint32_t frameIndex, std::uint32_t& commonM) {
  std::ifstream taylor(taylorPath, std::ios::binary);
  std::ifstream recovery(recoveryPath, std::ios::binary);
  if (!taylor || !recovery) throw std::runtime_error("cannot open upstream frame");
  const auto th = readObject<dl::OutputHeader>(taylor, "TGDLATO1 header");
  const auto rh = readObject<RecoveryHeader>(recovery, "TGDLREC1 header");
  const std::uint64_t order = residues.size();
  const std::int64_t expectedT =
      composedHeader.first_t_numerator +
      static_cast<std::int64_t>(frameIndex * composedHeader.t_step_numerator);
  if (std::memcmp(th.magic, dl::kOutputMagic, 8U) != 0 ||
      th.version != dl::kFormatVersion || th.lattice_rows != dl::kLatticeRows ||
      th.taylor_degree != dl::kTaylorDegree || th.reserved0 != 0U ||
      th.reserved1 != 0U || th.item_count != order ||
      std::filesystem::file_size(taylorPath) !=
          sizeof(dl::OutputHeader) + order * sizeof(dl::OutputItem)) {
    throw std::runtime_error("invalid TGDLATO1 identity or length");
  }
  if (std::memcmp(rh.magic, kRecoveryMagic, 8U) != 0 ||
      rh.version != kRecoveryVersion || rh.m == 0U || rh.reserved0 != 0U ||
      rh.reserved1 != 0U || rh.tNumerator != expectedT ||
      rh.tDenominator != composedHeader.t_denominator || rh.count != order ||
      std::filesystem::file_size(recoveryPath) !=
          sizeof(RecoveryHeader) + order * sizeof(RecoveryItem)) {
    throw std::runtime_error("invalid TGDLREC1 identity, t, or length");
  }
  if (frameIndex == 0U) commonM = rh.m;
  if (rh.m != commonM) throw std::runtime_error("M changes between frames");

  std::vector<std::uint32_t> positions(composedHeader.q,
                                       std::numeric_limits<std::uint32_t>::max());
  for (std::uint32_t index = 0U; index < residues.size(); ++index) {
    positions[residues[index]] = index;
  }
  const Complex factor = qMinusS(
      composedHeader.q, static_cast<std::uint64_t>(expectedT),
      composedHeader.t_denominator);
  std::uint64_t seen = 0U;
  for (std::uint32_t a = 1U; a < composedHeader.q; ++a) {
    if (positions[a] == std::numeric_limits<std::uint32_t>::max()) continue;
    const auto zeta = readObject<dl::OutputItem>(taylor, "Taylor item");
    const auto finite = readObject<RecoveryItem>(recovery, "recovery item");
    const std::uint32_t row = dl::canonical_lattice_row(composedHeader.q, a);
    if (zeta.q != composedHeader.q || zeta.a != a || zeta.lattice_row != row ||
        zeta.status != 0U || finite.q != composedHeader.q || finite.a != a ||
        finite.reserved0 != 0U || finite.reserved1 != 0U) {
      throw std::runtime_error("q/a/row ordering mismatch in replay frame");
    }
    const Complex expected = add(mul(exact(zeta.value), factor),
                                 exact(finite.value));
    const auto& actual = composed[positions[a]];
    if (!contains(actual, expected)) {
      throw std::runtime_error("TGDAFFI1 does not contain MPFR replay at a=" +
                               std::to_string(a));
    }
    ++seen;
  }
  if (seen != order) throw std::runtime_error("replay unit-group count mismatch");
  char trailing = 0;
  if (taylor.read(&trailing, 1) || recovery.read(&trailing, 1)) {
    throw std::runtime_error("trailing upstream frame bytes");
  }
}

void verify(const std::filesystem::path& composedPath,
            const std::vector<std::pair<std::filesystem::path,
                                        std::filesystem::path>>& frames) {
  static_assert(std::endian::native == std::endian::little,
                "binary protocols require little endian");
  std::ifstream input(composedPath, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open TGDAFFI1");
  const auto header = readObject<da::InputHeader>(input, "TGDAFFI1 header");
  if (std::memcmp(header.magic, da::kInputMagic, 8U) != 0 ||
      header.version != da::kFormatVersion || header.q < kLargeQStart ||
      header.q > kLargeQStop || header.batch_count == 0U ||
      header.batch_count != frames.size() || header.first_t_numerator < 0 ||
      header.first_t_numerator % static_cast<std::int64_t>(kSourceStep) != 0 ||
      header.t_denominator != kSourceDenominator ||
      header.t_step_numerator != kSourceStep || header.reserved0 != 0U) {
    throw std::runtime_error("invalid TGDAFFI1 source-grid header");
  }
  const std::uint64_t firstIndex =
      static_cast<std::uint64_t>(header.first_t_numerator) / kSourceStep;
  if (firstIndex + header.batch_count - 1U > maximumTIndex(header.q)) {
    throw std::runtime_error("TGDAFFI1 extends beyond this q's source height");
  }
  const auto residues = canonicalResidues(header.q);
  if (header.group_order != residues.size() ||
      header.value_count != header.batch_count * header.group_order ||
      std::filesystem::file_size(composedPath) !=
          sizeof(da::InputHeader) +
              header.value_count * sizeof(dl::ComplexInterval)) {
    throw std::runtime_error("TGDAFFI1 group order, count, or length mismatch");
  }
  const auto model = canonicalModel(header.q);
  std::uint32_t componentCount = 0U;
  for (const auto& factor : model) componentCount += factor.components.size();
  if (header.component_count != componentCount) {
    throw std::runtime_error("TGDAFFI1 component count mismatch");
  }

  std::uint32_t commonM = 0U;
  for (std::uint32_t frame = 0U; frame < header.batch_count; ++frame) {
    const auto values = readVector<dl::ComplexInterval>(
        input, header.group_order, "TGDAFFI1 frame");
    verifyFrame(frames[frame].first, frames[frame].second, header, residues,
                values, frame, commonM);
  }
  char trailing = 0;
  if (input.read(&trailing, 1)) throw std::runtime_error("trailing TGDAFFI1 bytes");
  std::printf(
      "{\"backend\":\"MPFR %s\",\"batch_count\":%u,"
      "\"classification\":\"higher_precision_composition_replay_not_atom_closure\","
      "\"external_atom_discharged\":false,\"group_order\":%llu,"
      "\"M\":%u,\"precision_bits\":%ld,\"q\":%u,\"t_order_replayed\":true,"
      "\"upstream_frame_hashes\":[",
      mpfr_get_version(), header.batch_count,
      static_cast<unsigned long long>(header.group_order),
      commonM, static_cast<long>(gPrecision), header.q);
  for (std::size_t index = 0U; index < frames.size(); ++index) {
    if (index != 0U) std::printf(",");
    const auto taylorHash = sha256File(frames[index].first);
    const auto recoveryHash = sha256File(frames[index].second);
    std::printf("{\"finite_recovery_sha256\":\"%s\","
                "\"taylor_output_sha256\":\"%s\"}",
                recoveryHash.c_str(), taylorHash.c_str());
  }
  const auto outputHash = sha256File(composedPath);
  std::printf(
      "],\"value_count\":%llu,\"TGDAFFI1_sha256\":\"%s\"}\n",
      static_cast<unsigned long long>(header.value_count), outputHash.c_str());
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 6 || std::string(argv[1]) != "verify" ||
        ((argc - 4) % 2) != 0) {
      throw std::runtime_error(
          "usage: checker verify TGDAFFI1 PRECISION_BITS "
          "TGDLATO1 TGDLREC1 [TGDLATO1 TGDLREC1 ...]");
    }
    const auto precision = parseUnsigned(argv[3], "precision");
    if (precision < 256U || precision > 16384U) {
      throw std::runtime_error("replay precision must be in 256..16384 bits");
    }
    gPrecision = static_cast<mpfr_prec_t>(precision);
    std::vector<std::pair<std::filesystem::path, std::filesystem::path>> frames;
    for (int index = 4; index < argc; index += 2) {
      frames.emplace_back(argv[index], argv[index + 1]);
    }
    verify(argv[2], frames);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_residue_composition_mpfr: %s\n",
                 error.what());
    return 1;
  }
}

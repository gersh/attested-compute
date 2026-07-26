// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Rigorous finite-Gaussian and positive-sign radix-2 DFT engine for Platt's
// small-q path.  Device code evaluates no transcendental function.  Its only
// non-basic operation is CUDA's upward-rounded __dsqrt_ru.  MPFR constructs
// the character-root and FFT-root disks; the input's w, prefactor, and
// analytic-tail disks are a fail-closed certificate boundary intended for an
// independent Arb checker.

#include "sparkinterval/tg_dirichlet_booker_smallq_certified.hpp"
#include "sparkinterval/tg_dirichlet_strict_sign_pack.cuh"
#include "sparkinterval/sha256.hpp"

#include <cuda_runtime.h>
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
#include <map>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <system_error>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace sc = sparkinterval::tg::dirichlet_booker_smallq_certified;
namespace strict_pack = sparkinterval::tg::dirichlet_strict_sign_pack;

namespace {

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

constexpr std::uint32_t kThreads = 256U;
constexpr std::uint32_t kRootAnchorSpan = 256U;
constexpr mpfr_prec_t kMpfrPrecision = 320;
constexpr std::uint64_t kSourceSampleNumerator = 5U;
constexpr char kPackedFrameDomain[] =
    "SparkInterval/DirichletBookerSmallQ/packed-sign-frame/v1";

static_assert(std::endian::native == std::endian::little,
              "small-q binary protocols require a little-endian host");

struct MpfrValue {
  mpfr_t value;
  MpfrValue() { mpfr_init2(value, kMpfrPrecision); }
  ~MpfrValue() { mpfr_clear(value); }
  MpfrValue(const MpfrValue&) = delete;
  MpfrValue& operator=(const MpfrValue&) = delete;
};

struct RealRectangle {
  double lo;
  double hi;
};

void includeCandidate(mpfr_t lo, mpfr_t hi, mpfr_srcptr candidateLo,
                      mpfr_srcptr candidateHi) {
  if (mpfr_less_p(candidateLo, lo)) mpfr_set(lo, candidateLo, MPFR_RNDD);
  if (mpfr_greater_p(candidateHi, hi)) mpfr_set(hi, candidateHi, MPFR_RNDU);
}

RealRectangle trigRectangle(std::uint64_t numerator,
                            std::uint64_t denominator, bool sine) {
  if (denominator == 0U || denominator > (1ULL << 62U)) {
    throw std::runtime_error("invalid root denominator");
  }
  const std::uint64_t period = 2U * denominator;
  numerator %= period;
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
  // The exact rational interval is far narrower than one ulp at this
  // precision, but include the five extrema in one sinpi/cospi period
  // explicitly rather than assuming monotonicity.
  for (unsigned twice = 0; twice <= 4U; ++twice) {
    mpfr_set_ui(point.value, twice, MPFR_RNDN);
    mpfr_div_2ui(point.value, point.value, 1U, MPFR_RNDN);
    if (mpfr_lessequal_p(xLo.value, point.value) &&
        mpfr_greaterequal_p(xHi.value, point.value)) {
      int exact = 0;
      if (sine) {
        if (twice == 1U) exact = 1;
        if (twice == 3U) exact = -1;
      } else {
        if (twice == 0U || twice == 4U) exact = 1;
        if (twice == 2U) exact = -1;
      }
      mpfr_set_si(down.value, exact, MPFR_RNDD);
      mpfr_set_si(up.value, exact, MPFR_RNDU);
      includeCandidate(lo.value, hi.value, down.value, up.value);
    }
  }
  RealRectangle result{mpfr_get_d(lo.value, MPFR_RNDD),
                       mpfr_get_d(hi.value, MPFR_RNDU)};
  mpq_clear(rational);
  return result;
}

sc::Disk rectangleDisk(RealRectangle re, RealRectangle im) {
  const double centerRe = std::midpoint(re.lo, re.hi);
  const double centerIm = std::midpoint(im.lo, im.hi);
  MpfrValue dx0, dx1, dy0, dy1, dx, dy, radius;
  mpfr_set_d(dx0.value, centerRe, MPFR_RNDN);
  mpfr_sub_d(dx0.value, dx0.value, re.lo, MPFR_RNDU);
  mpfr_abs(dx0.value, dx0.value, MPFR_RNDU);
  mpfr_set_d(dx1.value, re.hi, MPFR_RNDN);
  mpfr_sub_d(dx1.value, dx1.value, centerRe, MPFR_RNDU);
  mpfr_abs(dx1.value, dx1.value, MPFR_RNDU);
  mpfr_max(dx.value, dx0.value, dx1.value, MPFR_RNDU);
  mpfr_set_d(dy0.value, centerIm, MPFR_RNDN);
  mpfr_sub_d(dy0.value, dy0.value, im.lo, MPFR_RNDU);
  mpfr_abs(dy0.value, dy0.value, MPFR_RNDU);
  mpfr_set_d(dy1.value, im.hi, MPFR_RNDN);
  mpfr_sub_d(dy1.value, dy1.value, centerIm, MPFR_RNDU);
  mpfr_abs(dy1.value, dy1.value, MPFR_RNDU);
  mpfr_max(dy.value, dy0.value, dy1.value, MPFR_RNDU);
  mpfr_mul(radius.value, dx.value, dx.value, MPFR_RNDU);
  mpfr_fma(radius.value, dy.value, dy.value, radius.value, MPFR_RNDU);
  mpfr_sqrt(radius.value, radius.value, MPFR_RNDU);
  return {centerRe, centerIm, mpfr_get_d(radius.value, MPFR_RNDU)};
}

sc::Disk unitRoot(std::uint64_t exponent, std::uint64_t order) {
  if (order == 0U || exponent > std::numeric_limits<std::uint64_t>::max() / 2U) {
    throw std::runtime_error("invalid unit-root arguments");
  }
  return rectangleDisk(trigRectangle(2U * exponent, order, false),
                       trigRectangle(2U * exponent, order, true));
}

__device__ __forceinline__ bool validDisk(sc::Disk value) {
  return isfinite(value.real) && isfinite(value.imaginary) &&
         isfinite(value.radius) && value.radius >= 0.0;
}

__device__ __forceinline__ double normUpper(double re, double im) {
  const double square = __dadd_ru(__dmul_ru(re, re), __dmul_ru(im, im));
  return __dsqrt_ru(square);
}

__device__ __forceinline__ double coordinateError(double center, double lo,
                                                   double hi) {
  return fmax(__dsub_ru(center, lo), __dsub_ru(hi, center));
}

__device__ __forceinline__ sc::Disk diskAdd(sc::Disk x, sc::Disk y) {
  const double loRe = __dadd_rd(x.real, y.real);
  const double hiRe = __dadd_ru(x.real, y.real);
  const double loIm = __dadd_rd(x.imaginary, y.imaginary);
  const double hiIm = __dadd_ru(x.imaginary, y.imaginary);
  const double re = __dadd_rn(x.real, y.real);
  const double im = __dadd_rn(x.imaginary, y.imaginary);
  const double er = coordinateError(re, loRe, hiRe);
  const double ei = coordinateError(im, loIm, hiIm);
  const double rounding = normUpper(er, ei);
  return {re, im, __dadd_ru(__dadd_ru(x.radius, y.radius), rounding)};
}

__device__ __forceinline__ sc::Disk diskSub(sc::Disk x, sc::Disk y) {
  y.real = -y.real;
  y.imaginary = -y.imaginary;
  return diskAdd(x, y);
}

__device__ __forceinline__ sc::Disk diskMul(sc::Disk x, sc::Disk y) {
  const double xryrLo = __dmul_rd(x.real, y.real);
  const double xryrHi = __dmul_ru(x.real, y.real);
  const double xiyIlo = __dmul_rd(x.imaginary, y.imaginary);
  const double xiyIhi = __dmul_ru(x.imaginary, y.imaginary);
  const double xrYiLo = __dmul_rd(x.real, y.imaginary);
  const double xrYiHi = __dmul_ru(x.real, y.imaginary);
  const double xiYrLo = __dmul_rd(x.imaginary, y.real);
  const double xiYrHi = __dmul_ru(x.imaginary, y.real);
  const double loRe = __dsub_rd(xryrLo, xiyIhi);
  const double hiRe = __dsub_ru(xryrHi, xiyIlo);
  const double loIm = __dadd_rd(xrYiLo, xiYrLo);
  const double hiIm = __dadd_ru(xrYiHi, xiYrHi);
  const double re = fma(x.real, y.real, -x.imaginary * y.imaginary);
  const double im = fma(x.real, y.imaginary, x.imaginary * y.real);
  const double er = coordinateError(re, loRe, hiRe);
  const double ei = coordinateError(im, loIm, hiIm);
  const double rounding = normUpper(er, ei);
  const double nx = normUpper(x.real, x.imaginary);
  const double ny = normUpper(y.real, y.imaginary);
  double radius = __dadd_ru(rounding, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re, im, radius};
}

__device__ __forceinline__ sc::Disk diskScaleUnsigned(sc::Disk x,
                                                       std::uint32_t n) {
  return diskMul(x, {static_cast<double>(n), 0.0, 0.0});
}

__global__ void finiteGaussianKernel(
    sc::InputHeader header, const sc::CharacterHeader* characters,
    const sc::Disk* characterRoots, const sc::FrequencySeed* seeds,
    const sc::SharedFrequencySeed* sharedSeeds,
    const sc::Disk* characterEpsilons, std::uint64_t sharedSeedStart,
    std::uint64_t sharedSeedCount, sc::Disk* output,
    std::uint32_t* statuses) {
  const std::uint64_t total =
      static_cast<std::uint64_t>(header.batch_count) * sharedSeedCount;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < total;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t batch =
        static_cast<std::uint32_t>(flat / sharedSeedCount);
    const std::uint64_t local = flat % sharedSeedCount;
    const std::uint64_t outputFlat =
        static_cast<std::uint64_t>(batch) * header.frequency_count +
        sharedSeedStart + local;
    sc::FrequencySeed seed{};
    if (header.version == sc::kFactoredFormatVersion) {
      const sc::SharedFrequencySeed shared = sharedSeeds[local];
      const sc::ParitySeed parity =
          characters[batch].parity == 0U ? shared.even : shared.odd;
      seed.index = shared.index;
      seed.signed_index = shared.signed_index;
      seed.truncation = parity.truncation;
      seed.w = shared.w;
      seed.prefactor = diskMul(parity.prefactor, characterEpsilons[batch]);
      seed.analytic_radius_hi = parity.analytic_radius_hi;
    } else {
      seed = seeds[outputFlat];
    }
    std::uint32_t status = sc::kSuccess;
    if (!validDisk(seed.w) || !validDisk(seed.prefactor) ||
        !isfinite(seed.analytic_radius_hi) || seed.analytic_radius_hi < 0.0 ||
        characters[batch].parity > 1U) {
      status |= sc::kMalformedSeed;
    }
    sc::Disk sum{0.0, 0.0, 0.0};
    if (status == sc::kSuccess && seed.truncation != 0U) {
      sc::Disk z = seed.w;
      const sc::Disk w2 = diskMul(seed.w, seed.w);
      sc::Disk ratio = diskMul(w2, seed.w);
      for (std::uint32_t n = 1U; n <= seed.truncation; ++n) {
        const sc::Disk chi = characterRoots[
            static_cast<std::uint64_t>(batch) * header.q + n % header.q];
        if (!(chi.real == 0.0 && chi.imaginary == 0.0 && chi.radius == 0.0)) {
          sc::Disk term = diskMul(chi, z);
          if (characters[batch].parity != 0U) {
            term = diskScaleUnsigned(term, n);
          }
          sum = diskAdd(sum, term);
        }
        if (n != seed.truncation) {
          z = diskMul(z, ratio);
          ratio = diskMul(ratio, w2);
        }
      }
    }
    sc::Disk answer = diskMul(seed.prefactor, sum);
    if (seed.signed_index < 0) answer.imaginary = -answer.imaginary;
    answer.radius = __dadd_ru(answer.radius, seed.analytic_radius_hi);
    if (!validDisk(answer)) {
      status |= sc::kNonFiniteArithmetic;
      if (isinf(answer.radius)) status |= sc::kRadiusOverflow;
    }
    output[outputFlat] = answer;
    statuses[outputFlat] = status;
  }
}

__global__ void fillRootStage(sc::Disk* roots, std::uint32_t rootOffset,
                              std::uint32_t half,
                              const sc::Disk* anchors,
                              std::uint32_t anchorCount, sc::Disk step) {
  for (std::uint32_t anchorIndex = blockIdx.x * blockDim.x + threadIdx.x;
       anchorIndex < anchorCount;
       anchorIndex += blockDim.x * gridDim.x) {
    const std::uint32_t start = anchorIndex * kRootAnchorSpan;
    const std::uint32_t stop = min(half, start + kRootAnchorSpan);
    sc::Disk value = anchors[anchorIndex];
    for (std::uint32_t j = start; j < stop; ++j) {
      roots[rootOffset + j] = value;
      value = diskMul(value, step);
    }
  }
}

__global__ void bitReverseCopy(const sc::Disk* input, sc::Disk* output,
                               std::uint64_t lines, std::uint32_t length,
                               std::uint32_t logLength) {
  const std::uint64_t total = lines * length;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < total;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / length;
    const std::uint32_t local = static_cast<std::uint32_t>(flat % length);
    const std::uint32_t reversed = __brev(local) >> (32U - logLength);
    output[line * length + reversed] = input[flat];
  }
}

__global__ void fftStage(sc::Disk* values, const sc::Disk* roots,
                         std::uint64_t lines, std::uint32_t length,
                         std::uint32_t stageLength) {
  const std::uint64_t butterflies = lines * length / 2U;
  const std::uint32_t half = stageLength / 2U;
  const std::uint32_t rootOffset = half - 1U;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < butterflies;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / (length / 2U);
    const std::uint64_t local = flat % (length / 2U);
    const std::uint64_t group = local / half;
    const std::uint32_t j = static_cast<std::uint32_t>(local % half);
    const std::uint64_t left =
        line * length + group * stageLength + j;
    const std::uint64_t right = left + half;
    const sc::Disk u = values[left];
    const sc::Disk v = diskMul(values[right], roots[rootOffset + j]);
    values[left] = diskAdd(u, v);
    values[right] = diskSub(u, v);
  }
}

__global__ void validateDisks(const sc::Disk* values, std::uint32_t* statuses,
                              std::uint64_t count) {
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    if (!validDisk(values[flat])) {
      statuses[flat] |= sc::kNonFiniteArithmetic;
      if (isinf(values[flat].radius)) statuses[flat] |= sc::kRadiusOverflow;
    }
  }
}

std::uint32_t blocksFor(std::uint64_t count) {
  return static_cast<std::uint32_t>(std::min<std::uint64_t>(
      65535U, std::max<std::uint64_t>(1U, (count + kThreads - 1U) / kThreads)));
}

std::uint32_t integerLog2(std::uint64_t value) {
  if (value == 0U || (value & (value - 1U)) != 0U || value > (1ULL << 31U)) {
    throw std::runtime_error("transform length is not a supported power of two");
  }
  std::uint32_t result = 0U;
  while ((1ULL << result) != value) ++result;
  return result;
}

class Radix2Plan {
 public:
  Radix2Plan(std::uint32_t length, std::uint32_t maximumBatch)
      : length_(length),
        logLength_(integerLog2(length)),
        maximumBatch_(maximumBatch) {
    if (length_ > sc::kMaximumTransformLength || maximumBatch_ == 0U) {
      throw std::runtime_error("invalid radix-2 plan dimensions");
    }
    const std::uint64_t capacity =
        static_cast<std::uint64_t>(length_) * maximumBatch_;
    CUDA_CHECK(cudaMalloc(&roots_, (length_ - 1ULL) * sizeof(sc::Disk)));
    CUDA_CHECK(cudaMalloc(&scratch_, capacity * sizeof(sc::Disk)));
    const std::uint32_t maximumAnchors =
        (length_ / 2U + kRootAnchorSpan - 1U) / kRootAnchorSpan;
    CUDA_CHECK(cudaMalloc(&anchors_, maximumAnchors * sizeof(sc::Disk)));
    prepareRoots();
  }

  ~Radix2Plan() {
    cudaFree(anchors_);
    cudaFree(scratch_);
    cudaFree(roots_);
  }

  Radix2Plan(const Radix2Plan&) = delete;
  Radix2Plan& operator=(const Radix2Plan&) = delete;

  sc::Disk* execute(const sc::Disk* input, std::uint32_t batch) {
    if (batch == 0U || batch > maximumBatch_) {
      throw std::runtime_error("FFT batch exceeds resident plan capacity");
    }
    const std::uint64_t count = static_cast<std::uint64_t>(batch) * length_;
    bitReverseCopy<<<blocksFor(count), kThreads>>>(
        input, scratch_, batch, length_, logLength_);
    CUDA_CHECK(cudaGetLastError());
    for (std::uint32_t stage = 2U; stage <= length_; stage <<= 1U) {
      fftStage<<<blocksFor(count / 2U), kThreads>>>(
          scratch_, roots_, batch, length_, stage);
      CUDA_CHECK(cudaGetLastError());
    }
    return scratch_;
  }

  std::uint32_t length() const { return length_; }
  std::uint32_t maximumBatch() const { return maximumBatch_; }

 private:
  void prepareRoots() {
    for (std::uint32_t stage = 2U; stage <= length_; stage <<= 1U) {
      const std::uint32_t half = stage / 2U;
      const std::uint32_t rootOffset = half - 1U;
      const std::uint32_t anchorCount =
          (half + kRootAnchorSpan - 1U) / kRootAnchorSpan;
      std::vector<sc::Disk> hostAnchors(anchorCount);
      for (std::uint32_t block = 0; block < anchorCount; ++block) {
        hostAnchors[block] = unitRoot(
            static_cast<std::uint64_t>(block) * kRootAnchorSpan, stage);
      }
      const sc::Disk step = unitRoot(1U, stage);
      CUDA_CHECK(cudaMemcpy(anchors_, hostAnchors.data(),
                            hostAnchors.size() * sizeof(sc::Disk),
                            cudaMemcpyHostToDevice));
      fillRootStage<<<blocksFor(anchorCount), kThreads>>>(
          roots_, rootOffset, half, anchors_, anchorCount, step);
      CUDA_CHECK(cudaGetLastError());
    }
    CUDA_CHECK(cudaDeviceSynchronize());
  }

  std::uint32_t length_;
  std::uint32_t logLength_;
  std::uint32_t maximumBatch_;
  sc::Disk* roots_ = nullptr;
  sc::Disk* scratch_ = nullptr;
  sc::Disk* anchors_ = nullptr;
};

template <typename T>
T readObject(std::ifstream& input, const char* label,
             sparkinterval::detail::Sha256* digest = nullptr) {
  T result{};
  input.read(reinterpret_cast<char*>(&result), sizeof(result));
  if (!input) throw std::runtime_error(std::string("truncated ") + label);
  if (digest != nullptr) digest->update(&result, sizeof(result));
  return result;
}

template <typename T>
std::vector<T> readArray(std::ifstream& input, std::uint64_t count,
                         const char* label,
                         sparkinterval::detail::Sha256* digest = nullptr) {
  if (count > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
    throw std::runtime_error(std::string(label) + " count overflow");
  }
  std::vector<T> result(static_cast<std::size_t>(count));
  input.read(reinterpret_cast<char*>(result.data()),
             static_cast<std::streamsize>(result.size() * sizeof(T)));
  if (!input) throw std::runtime_error(std::string("truncated ") + label);
  if (digest != nullptr && !result.empty()) {
    digest->update(result.data(), result.size() * sizeof(T));
  }
  return result;
}

struct LoadedInput {
  sc::InputHeader header{};
  sc::ParameterHeader parameters{};
  std::vector<sc::CharacterHeader> characters;
  std::vector<sc::Disk> characterEpsilons;
  std::vector<std::uint32_t> exponents;
  std::vector<sc::FrequencySeed> seeds;
  std::vector<sc::SharedFrequencySeed> sharedSeeds;
  std::uint64_t finiteTerms = 0U;
};

bool validHostDisk(const sc::Disk& value) {
  return std::isfinite(value.real) && std::isfinite(value.imaginary) &&
         std::isfinite(value.radius) && value.radius >= 0.0;
}

LoadedInput loadInput(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open input " + path.string());
  LoadedInput loaded;
  loaded.header = readObject<sc::InputHeader>(input, "input header");
  const auto& h = loaded.header;
  const bool legacy = std::memcmp(h.magic, sc::kInputMagic, 8) == 0 &&
                      h.version == sc::kFormatVersion;
  const bool factored =
      std::memcmp(h.magic, sc::kFactoredInputMagic, 8) == 0 &&
      h.version == sc::kFactoredFormatVersion;
  if ((!legacy && !factored) || h.q < 3U ||
      h.q > sc::kMaximumModulus || h.group_exponent == 0U ||
      h.batch_count == 0U || h.transform_length == 0U ||
      h.transform_length > sc::kMaximumTransformLength ||
      (h.transform_length & (h.transform_length - 1U)) != 0U ||
      h.frequency_count == 0U ||
      h.frequency_start + h.frequency_count < h.frequency_start ||
      h.frequency_start + h.frequency_count > h.transform_length ||
      (h.run_dft != 0U && h.run_dft != 1U) ||
      (h.run_dft != 0U &&
       (h.transform_length < 2U || h.frequency_start != 0U ||
        h.frequency_count != h.transform_length)) ||
      h.target_bits < 32U || h.target_bits > 1024U || h.reserved1 != 0U) {
    throw std::runtime_error("invalid certified small-q input header");
  }
  loaded.parameters = readObject<sc::ParameterHeader>(input, "parameter header");
  const auto& p = loaded.parameters;
  const auto absoluteEta = p.eta_numerator < 0
      ? static_cast<std::uint64_t>(-(p.eta_numerator + 1)) + 1U
      : static_cast<std::uint64_t>(p.eta_numerator);
  if (p.eta_denominator == 0U || absoluteEta >= p.eta_denominator ||
      p.a_numerator == 0U || p.a_denominator == 0U || p.b_numerator == 0U ||
      p.b_denominator == 0U ||
      std::gcd(absoluteEta, p.eta_denominator) != 1U ||
      std::gcd(p.a_numerator, p.a_denominator) != 1U ||
      std::gcd(p.b_numerator, p.b_denominator) != 1U) {
    throw std::runtime_error("invalid exact transform parameters");
  }
  const std::uint64_t total =
      static_cast<std::uint64_t>(h.batch_count) * h.frequency_count;
  loaded.characters.reserve(h.batch_count);
  loaded.characterEpsilons.reserve(h.batch_count);
  loaded.exponents.reserve(static_cast<std::size_t>(h.batch_count) * h.q);
  if (legacy) loaded.seeds.reserve(static_cast<std::size_t>(total));
  std::uint64_t parityCounts[2] = {0U, 0U};
  for (std::uint32_t batch = 0; batch < h.batch_count; ++batch) {
    sc::CharacterHeader character{};
    if (factored) {
      const auto encoded = readObject<sc::FactoredCharacterHeader>(
          input, "factored character header");
      character = {encoded.character_id, encoded.parity, encoded.reserved0,
                   encoded.reserved1};
      if (!validHostDisk(encoded.epsilon)) {
        throw std::runtime_error("invalid character epsilon disk");
      }
      loaded.characterEpsilons.push_back(encoded.epsilon);
    } else {
      character = readObject<sc::CharacterHeader>(input, "character header");
      loaded.characterEpsilons.push_back({1.0, 0.0, 0.0});
    }
    if (character.parity > 1U || character.reserved0 != 0U ||
        character.reserved1 != 0U) {
      throw std::runtime_error("invalid character header");
    }
    ++parityCounts[character.parity];
    loaded.characters.push_back(character);
    auto exponents = readArray<std::uint32_t>(input, h.q, "character exponents");
    for (const auto exponent : exponents) {
      if (exponent != sc::kNonUnitExponent && exponent >= h.group_exponent) {
        throw std::runtime_error("character exponent outside group exponent");
      }
    }
    loaded.exponents.insert(loaded.exponents.end(), exponents.begin(),
                            exponents.end());
    if (legacy) {
      auto seeds = readArray<sc::FrequencySeed>(input, h.frequency_count,
                                                "frequency seeds");
      for (std::uint64_t local = 0; local < h.frequency_count; ++local) {
        const auto& seed = seeds[local];
        const std::uint64_t expected = h.frequency_start + local;
        const std::int64_t signedExpected =
            expected <= h.transform_length / 2U
                ? static_cast<std::int64_t>(expected)
                : static_cast<std::int64_t>(expected - h.transform_length);
        if (seed.index != expected || seed.signed_index != signedExpected ||
            seed.truncation > 100000000U || seed.reserved0 != 0U ||
            seed.reserved1 != 0U || !validHostDisk(seed.w) ||
            !validHostDisk(seed.prefactor) ||
            !std::isfinite(seed.analytic_radius_hi) ||
            seed.analytic_radius_hi < 0.0) {
          throw std::runtime_error("invalid frequency seed");
        }
        if (loaded.finiteTerms >
            std::numeric_limits<std::uint64_t>::max() - seed.truncation) {
          throw std::runtime_error("finite-term count overflow");
        }
        loaded.finiteTerms += seed.truncation;
      }
      loaded.seeds.insert(loaded.seeds.end(), seeds.begin(), seeds.end());
    }
  }
  if (factored) {
    loaded.sharedSeeds = readArray<sc::SharedFrequencySeed>(
        input, h.frequency_count, "shared frequency seeds");
    for (std::uint64_t local = 0; local < h.frequency_count; ++local) {
      const auto& shared = loaded.sharedSeeds[local];
      const std::uint64_t expected = h.frequency_start + local;
      const std::int64_t signedExpected =
          expected <= h.transform_length / 2U
              ? static_cast<std::int64_t>(expected)
              : static_cast<std::int64_t>(expected - h.transform_length);
      if (shared.index != expected || shared.signed_index != signedExpected ||
          !validHostDisk(shared.w)) {
        throw std::runtime_error("invalid shared frequency seed");
      }
      const sc::ParitySeed paritySeeds[2] = {shared.even, shared.odd};
      for (std::uint32_t parity = 0; parity < 2U; ++parity) {
        const auto& seed = paritySeeds[parity];
        if (seed.truncation > 100000000U || seed.reserved0 != 0U ||
            !validHostDisk(seed.prefactor) ||
            !std::isfinite(seed.analytic_radius_hi) ||
            seed.analytic_radius_hi < 0.0) {
          throw std::runtime_error("invalid factored parity seed");
        }
        if (seed.truncation != 0U &&
            parityCounts[parity] >
                std::numeric_limits<std::uint64_t>::max() / seed.truncation) {
          throw std::runtime_error("finite-term product overflow");
        }
        const std::uint64_t terms = parityCounts[parity] * seed.truncation;
        if (loaded.finiteTerms >
            std::numeric_limits<std::uint64_t>::max() - terms) {
          throw std::runtime_error("finite-term count overflow");
        }
        loaded.finiteTerms += terms;
      }
    }
  }
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes in certified small-q input");
  }
  return loaded;
}

bool validExactParameters(const sc::ParameterHeader& p) {
  const auto absoluteEta = p.eta_numerator < 0
      ? static_cast<std::uint64_t>(-(p.eta_numerator + 1)) + 1U
      : static_cast<std::uint64_t>(p.eta_numerator);
  return p.eta_denominator != 0U && absoluteEta < p.eta_denominator &&
         p.a_numerator != 0U && p.a_denominator != 0U &&
         p.b_numerator != 0U && p.b_denominator != 0U &&
         std::gcd(absoluteEta, p.eta_denominator) == 1U &&
         std::gcd(p.a_numerator, p.a_denominator) == 1U &&
         std::gcd(p.b_numerator, p.b_denominator) == 1U;
}

void validateSplitHeader(const sc::InputHeader& h, const char magic[8],
                         const char* label) {
  if (std::memcmp(h.magic, magic, 8) != 0 ||
      h.version != sc::kFactoredFormatVersion || h.q < 3U ||
      h.q > sc::kMaximumModulus || h.group_exponent == 0U ||
      h.batch_count == 0U || h.transform_length == 0U ||
      h.transform_length > sc::kMaximumTransformLength ||
      (h.transform_length & (h.transform_length - 1U)) != 0U ||
      h.frequency_count == 0U ||
      h.frequency_start + h.frequency_count < h.frequency_start ||
      h.frequency_start + h.frequency_count > h.transform_length ||
      (h.run_dft != 0U && h.run_dft != 1U) ||
      (h.run_dft != 0U &&
       (h.transform_length < 2U || h.frequency_start != 0U ||
        h.frequency_count != h.transform_length)) ||
      h.target_bits < 32U || h.target_bits > 1024U || h.reserved1 != 0U) {
    throw std::runtime_error(std::string("invalid ") + label + " header");
  }
}

struct LoadedSharedPlan {
  sc::InputHeader header{};
  sc::FactoredPlanCommitment commitment{};
  sc::ParameterHeader parameters{};
  sparkinterval::Sha256Digest digest{};
  std::filesystem::path path;
  std::uint64_t sharedOffset = 0U;
  std::uint64_t parityTruncationSums[2] = {0U, 0U};
};

struct ReducedFraction {
  std::uint64_t numerator;
  std::uint64_t denominator;
};

ReducedFraction reducedFraction(std::uint64_t numerator,
                                std::uint64_t denominator) {
  if (denominator == 0U) {
    throw std::runtime_error("cannot reduce a zero-denominator fraction");
  }
  const std::uint64_t divisor = std::gcd(numerator, denominator);
  return ReducedFraction{numerator / divisor, denominator / divisor};
}

std::uint64_t sourceSampleCount(const LoadedSharedPlan& plan) {
  // Match dirichlet_booker_smallq.transform_parameters exactly.  Reduced
  // output is unsafe for a merely shape-compatible project parameter set:
  // only the published 5/64 source grid may use TGDBSQR3.
  const std::uint64_t q = plan.header.q;
  const std::uint64_t additive = (q & 1U) == 0U ? 75000000U : 37500000U;
  const std::uint64_t heightNumerator =
      std::max<std::uint64_t>(100000000U, additive + 200U * q);
  const std::uint64_t minimumNumerator =
      64U * (heightNumerator + 64U * q);
  const std::uint64_t minimumDenominator = 5U * q;
  const std::uint64_t minimumLength =
      (minimumNumerator + minimumDenominator - 1U) / minimumDenominator;
  std::uint64_t canonicalLength = 1U;
  while (canonicalLength < minimumLength) canonicalLength <<= 1U;
  const ReducedFraction eta =
      reducedFraction(heightNumerator, heightNumerator + 64U * q);
  const ReducedFraction b =
      reducedFraction(5U * plan.header.transform_length, 64U);
  const auto& p = plan.parameters;
  if (p.eta_numerator < 0 ||
      static_cast<std::uint64_t>(p.eta_numerator) != eta.numerator ||
      p.eta_denominator != eta.denominator || p.a_numerator != 64U ||
      p.a_denominator != 5U || p.b_numerator != b.numerator ||
      p.b_denominator != b.denominator || plan.header.frequency_start != 0U ||
      plan.header.frequency_count != plan.header.transform_length ||
      plan.header.transform_length != canonicalLength ||
      plan.header.run_dft == 0U) {
    throw std::runtime_error(
        "source-sample-only output requires the exact canonical source plan");
  }
  return (64U * heightNumerator) / (5U * q) + 1U;
}

LoadedSharedPlan loadSharedPlan(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open shared plan " + path.string());
  sparkinterval::detail::Sha256 digest;
  LoadedSharedPlan plan;
  plan.path = path;
  plan.header = readObject<sc::InputHeader>(input, "shared plan header", &digest);
  validateSplitHeader(plan.header, sc::kFactoredPlanMagic, "shared plan");
  plan.commitment = readObject<sc::FactoredPlanCommitment>(
      input, "shared plan commitment", &digest);
  plan.parameters = readObject<sc::ParameterHeader>(
      input, "shared plan parameters", &digest);
  if (!validExactParameters(plan.parameters)) {
    throw std::runtime_error("invalid shared plan exact parameters");
  }
  plan.sharedOffset = sizeof(sc::InputHeader) +
                      sizeof(sc::FactoredPlanCommitment) +
                      sizeof(sc::ParameterHeader);
  constexpr std::uint64_t kReadRecords = 1U << 16U;
  for (std::uint64_t start = 0; start < plan.header.frequency_count;) {
    const std::uint64_t count =
        std::min<std::uint64_t>(kReadRecords, plan.header.frequency_count - start);
    const auto seeds = readArray<sc::SharedFrequencySeed>(
        input, count, "shared plan seeds", &digest);
    for (std::uint64_t local = 0; local < count; ++local) {
      const auto& shared = seeds[local];
      const std::uint64_t expected = plan.header.frequency_start + start + local;
      const std::int64_t signedExpected =
          expected <= plan.header.transform_length / 2U
              ? static_cast<std::int64_t>(expected)
              : static_cast<std::int64_t>(expected - plan.header.transform_length);
      if (shared.index != expected || shared.signed_index != signedExpected ||
          !validHostDisk(shared.w)) {
        throw std::runtime_error("invalid shared plan frequency seed");
      }
      const sc::ParitySeed paritySeeds[2] = {shared.even, shared.odd};
      for (std::uint32_t parity = 0; parity < 2U; ++parity) {
        const auto& seed = paritySeeds[parity];
        if (seed.truncation > 100000000U || seed.reserved0 != 0U ||
            !validHostDisk(seed.prefactor) ||
            !std::isfinite(seed.analytic_radius_hi) ||
            seed.analytic_radius_hi < 0.0 ||
            plan.parityTruncationSums[parity] >
                std::numeric_limits<std::uint64_t>::max() - seed.truncation) {
          throw std::runtime_error("invalid shared plan parity seed");
        }
        plan.parityTruncationSums[parity] += seed.truncation;
      }
    }
    start += count;
  }
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes in shared plan");
  }
  plan.digest = digest.finish();
  return plan;
}

bool samePlanShape(const sc::InputHeader& batch,
                   const sc::InputHeader& plan) {
  return batch.q == plan.q &&
         batch.group_exponent == plan.group_exponent &&
         batch.transform_length == plan.transform_length &&
         batch.frequency_start == plan.frequency_start &&
         batch.frequency_count == plan.frequency_count &&
         batch.run_dft == plan.run_dft &&
         batch.target_bits == plan.target_bits;
}

struct BatchPreview {
  sc::InputHeader header{};
  sc::FactoredBatchBinding binding{};
  std::vector<std::uint64_t> characterIds;
  std::vector<std::uint32_t> characterParities;
  sparkinterval::Sha256Digest digest{};
};

BatchPreview preflightServiceBatch(
    const std::filesystem::path& path, const LoadedSharedPlan& plan,
    sparkinterval::detail::Sha256* rosterDigest) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open character batch " + path.string());
  BatchPreview preview;
  sparkinterval::detail::Sha256 batchDigest;
  preview.header = readObject<sc::InputHeader>(
      input, "character batch header", &batchDigest);
  validateSplitHeader(preview.header, sc::kFactoredBatchMagic,
                      "character batch");
  preview.binding = readObject<sc::FactoredBatchBinding>(
      input, "character batch binding", &batchDigest);
  if (!samePlanShape(preview.header, plan.header) ||
      std::memcmp(preview.binding.plan_sha256, plan.digest.data(),
                  plan.digest.size()) != 0 ||
      preview.binding.campaign_character_count != plan.header.batch_count ||
      preview.binding.character_start + preview.header.batch_count <
          preview.binding.character_start ||
      preview.binding.character_start + preview.header.batch_count >
          plan.header.batch_count ||
      preview.binding.campaign_batch_count == 0U ||
      preview.binding.batch_ordinal >= preview.binding.campaign_batch_count) {
    throw std::runtime_error("character batch does not match shared plan");
  }
  preview.characterIds.reserve(preview.header.batch_count);
  preview.characterParities.reserve(preview.header.batch_count);
  for (std::uint32_t batch = 0; batch < preview.header.batch_count; ++batch) {
    const auto character = readObject<sc::FactoredCharacterHeader>(
        input, "factored service character header", &batchDigest);
    if (character.parity > 1U || character.reserved0 != 0U ||
        character.reserved1 != 0U || !validHostDisk(character.epsilon)) {
      throw std::runtime_error("invalid factored service character header");
    }
    preview.characterIds.push_back(character.character_id);
    preview.characterParities.push_back(character.parity);
    rosterDigest->update(&character.character_id, sizeof(character.character_id));
    (void)readArray<std::uint32_t>(input, preview.header.q,
                                   "factored service exponents", &batchDigest);
  }
  if (input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("trailing bytes in character batch");
  }
  preview.digest = batchDigest.finish();
  return preview;
}

sparkinterval::Sha256Digest parseSha256Hex(const char* text,
                                           const char* label) {
  if (text == nullptr || std::strlen(text) != 64U) {
    throw std::runtime_error(std::string(label) +
                             " must have 64 lowercase hexadecimal digits");
  }
  sparkinterval::Sha256Digest result{};
  auto nibble = [label](char value) -> unsigned char {
    if (value >= '0' && value <= '9') {
      return static_cast<unsigned char>(value - '0');
    }
    if (value >= 'a' && value <= 'f') {
      return static_cast<unsigned char>(value - 'a' + 10);
    }
    throw std::runtime_error(std::string(label) +
                             " must be lowercase hexadecimal");
  };
  for (std::size_t index = 0; index < result.size(); ++index) {
    result[index] = static_cast<unsigned char>(
        (nibble(text[2U * index]) << 4U) | nibble(text[2U * index + 1U]));
  }
  return result;
}

sparkinterval::Sha256Digest batchPartitionDigest(
    const std::vector<BatchPreview>& previews) {
  constexpr char kDomain[] =
      "SparkInterval/DirichletBookerSmallQ/"
      "semantic-control-batch-partition/v1";
  sparkinterval::detail::Sha256 digest;
  digest.update(kDomain, sizeof(kDomain));
  const std::uint64_t batchCount = previews.size();
  digest.update(&batchCount, sizeof(batchCount));
  for (const auto& preview : previews) {
    if (preview.characterIds.size() != preview.header.batch_count ||
        preview.characterParities.size() != preview.header.batch_count) {
      throw std::runtime_error("incomplete service batch preview");
    }
    digest.update(preview.digest.data(), preview.digest.size());
    digest.update(&preview.binding.character_start,
                  sizeof(preview.binding.character_start));
    digest.update(&preview.binding.campaign_character_count,
                  sizeof(preview.binding.campaign_character_count));
    digest.update(&preview.binding.batch_ordinal,
                  sizeof(preview.binding.batch_ordinal));
    digest.update(&preview.binding.campaign_batch_count,
                  sizeof(preview.binding.campaign_batch_count));
    const std::uint64_t characterCount = preview.characterIds.size();
    digest.update(&characterCount, sizeof(characterCount));
    for (std::size_t index = 0; index < preview.characterIds.size(); ++index) {
      digest.update(&preview.characterIds[index],
                    sizeof(preview.characterIds[index]));
      digest.update(&preview.characterParities[index],
                    sizeof(preview.characterParities[index]));
    }
  }
  return digest.finish();
}

struct FileIdentity {
  dev_t device{};
  ino_t inode{};
  mode_t mode{};
  off_t size{};
  timespec modified{};
  timespec changed{};
};

FileIdentity fileIdentity(const struct stat& status) {
  return {status.st_dev, status.st_ino, status.st_mode, status.st_size,
          status.st_mtim, status.st_ctim};
}

bool operator==(const FileIdentity& left, const FileIdentity& right) {
  return left.device == right.device && left.inode == right.inode &&
         left.mode == right.mode && left.size == right.size &&
         left.modified.tv_sec == right.modified.tv_sec &&
         left.modified.tv_nsec == right.modified.tv_nsec &&
         left.changed.tv_sec == right.changed.tv_sec &&
         left.changed.tv_nsec == right.changed.tv_nsec;
}

class MappedTimeTailControl {
 public:
  MappedTimeTailControl(
      const std::filesystem::path& path, const LoadedSharedPlan& plan,
      const std::vector<BatchPreview>& previews,
      const sparkinterval::Sha256Digest& expectedPartition)
      : path_(path) {
    try {
      descriptor_ =
          open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
      if (descriptor_ < 0) {
        throw std::runtime_error("cannot open strict-sign control " +
                                 path.string());
      }
      struct stat status {};
      if (fstat(descriptor_, &status) != 0 || !S_ISREG(status.st_mode) ||
          status.st_size < 0) {
        throw std::runtime_error(
            "strict-sign control is not a regular file");
      }
      identity_ = fileIdentity(status);
      size_ = static_cast<std::uint64_t>(status.st_size);
      if (size_ < sizeof(sc::TimeTailControlHeader) ||
          size_ > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("strict-sign control size is unsupported");
      }
      mapped_ = static_cast<const unsigned char*>(
          mmap(nullptr, static_cast<std::size_t>(size_), PROT_READ,
               MAP_PRIVATE, descriptor_, 0));
      if (mapped_ == MAP_FAILED) {
        mapped_ = nullptr;
        throw std::runtime_error("cannot map strict-sign control");
      }
      std::memcpy(&header_, mapped_, sizeof(header_));
      std::uint64_t parityCounts[2] = {0U, 0U};
      for (const auto& preview : previews) {
        for (const auto parity : preview.characterParities) {
          if (parity > 1U) {
            throw std::runtime_error(
                "strict-sign preview parity is outside 0..1");
          }
          ++parityCounts[parity];
        }
      }
      const std::uint64_t samples = sourceSampleCount(plan);
      if (samples >
          (std::numeric_limits<std::uint64_t>::max() -
           sizeof(sc::TimeTailControlHeader)) /
              sizeof(sc::TimeTailControlItem)) {
        throw std::runtime_error("strict-sign control length overflows");
      }
      const std::uint64_t expectedSize =
          sizeof(sc::TimeTailControlHeader) +
          samples * sizeof(sc::TimeTailControlItem);
      if (std::memcmp(header_.magic, sc::kTimeTailControlMagic, 8) != 0 ||
          header_.version != sc::kTimeTailControlVersion ||
          header_.q != plan.header.q ||
          header_.even_character_count != parityCounts[0] ||
          header_.odd_character_count != parityCounts[1] ||
          header_.transform_length != plan.header.transform_length ||
          header_.sample_count != samples ||
          header_.precision_bits < 128U || header_.precision_bits > 4096U ||
          header_.reserved0 != 0U ||
          std::memcmp(header_.plan_sha256, plan.digest.data(),
                      plan.digest.size()) != 0 ||
          std::memcmp(header_.batch_partition_sha256,
                      expectedPartition.data(), expectedPartition.size()) !=
              0 ||
          size_ != expectedSize) {
        throw std::runtime_error(
            "strict-sign control identity, roster, or grid differs");
      }
      items_ = reinterpret_cast<const sc::TimeTailControlItem*>(
          mapped_ + sizeof(header_));
      for (std::uint64_t sample = 0; sample < samples; ++sample) {
        if (!std::isfinite(items_[sample].even) ||
            items_[sample].even < 0.0 ||
            !std::isfinite(items_[sample].odd) ||
            items_[sample].odd < 0.0) {
          throw std::runtime_error(
              "strict-sign control contains a nonfinite or negative word");
        }
      }
      sparkinterval::detail::Sha256 digest;
      constexpr std::size_t kHashChunk = 8U << 20U;
      for (std::uint64_t offset = 0U; offset < size_;) {
        const std::size_t count = static_cast<std::size_t>(
            std::min<std::uint64_t>(kHashChunk, size_ - offset));
        digest.update(mapped_ + offset, count);
        offset += count;
      }
      digest_ = digest.finish();
      verifyStable();
    } catch (...) {
      closeResources();
      throw;
    }
  }

  ~MappedTimeTailControl() { closeResources(); }
  MappedTimeTailControl(const MappedTimeTailControl&) = delete;
  MappedTimeTailControl& operator=(const MappedTimeTailControl&) = delete;

  const sc::TimeTailControlHeader& header() const { return header_; }
  const sparkinterval::Sha256Digest& digest() const { return digest_; }
  const sc::TimeTailControlItem* items() const { return items_; }

  double threshold(std::uint64_t sample, std::uint32_t parity) const {
    if (sample >= header_.sample_count || parity > 1U) {
      throw std::runtime_error("strict-sign control index is out of range");
    }
    return parity == 0U ? items_[sample].even : items_[sample].odd;
  }

  void verifyStable() const {
    struct stat status {};
    if (descriptor_ < 0 || fstat(descriptor_, &status) != 0 ||
        !(fileIdentity(status) == identity_)) {
      throw std::runtime_error(
          "strict-sign control changed while it was consumed");
    }
  }

 private:
  void closeResources() noexcept {
    if (mapped_ != nullptr) {
      munmap(const_cast<unsigned char*>(mapped_),
             static_cast<std::size_t>(size_));
      mapped_ = nullptr;
    }
    if (descriptor_ >= 0) {
      close(descriptor_);
      descriptor_ = -1;
    }
  }

  std::filesystem::path path_;
  int descriptor_ = -1;
  std::uint64_t size_ = 0U;
  const unsigned char* mapped_ = nullptr;
  const sc::TimeTailControlItem* items_ = nullptr;
  FileIdentity identity_{};
  sc::TimeTailControlHeader header_{};
  sparkinterval::Sha256Digest digest_{};
};

struct LoadedServiceBatch {
  LoadedInput input;
  sc::FactoredBatchBinding binding{};
  sparkinterval::Sha256Digest digest{};
};

LoadedServiceBatch loadServiceBatch(const std::filesystem::path& path,
                                    const LoadedSharedPlan& plan) {
  std::ifstream source(path, std::ios::binary);
  if (!source) throw std::runtime_error("cannot open character batch " + path.string());
  LoadedServiceBatch result;
  sparkinterval::detail::Sha256 batchDigest;
  auto& loaded = result.input;
  loaded.header = readObject<sc::InputHeader>(
      source, "character batch header", &batchDigest);
  validateSplitHeader(loaded.header, sc::kFactoredBatchMagic,
                      "character batch");
  result.binding = readObject<sc::FactoredBatchBinding>(
      source, "character batch binding", &batchDigest);
  if (!samePlanShape(loaded.header, plan.header) ||
      std::memcmp(result.binding.plan_sha256, plan.digest.data(),
                  plan.digest.size()) != 0 ||
      result.binding.campaign_character_count != plan.header.batch_count) {
    throw std::runtime_error("character batch changed after service preflight");
  }
  loaded.parameters = plan.parameters;
  loaded.characters.reserve(loaded.header.batch_count);
  loaded.characterEpsilons.reserve(loaded.header.batch_count);
  loaded.exponents.reserve(
      static_cast<std::size_t>(loaded.header.batch_count) * loaded.header.q);
  std::uint64_t parityCounts[2] = {0U, 0U};
  for (std::uint32_t batch = 0; batch < loaded.header.batch_count; ++batch) {
    const auto encoded = readObject<sc::FactoredCharacterHeader>(
        source, "factored service character header", &batchDigest);
    if (encoded.parity > 1U || encoded.reserved0 != 0U ||
        encoded.reserved1 != 0U || !validHostDisk(encoded.epsilon)) {
      throw std::runtime_error("invalid factored service character header");
    }
    loaded.characters.push_back(
        {encoded.character_id, encoded.parity, encoded.reserved0,
         encoded.reserved1});
    loaded.characterEpsilons.push_back(encoded.epsilon);
    ++parityCounts[encoded.parity];
    const auto exponents = readArray<std::uint32_t>(
        source, loaded.header.q, "factored service character exponents",
        &batchDigest);
    for (const auto exponent : exponents) {
      if (exponent != sc::kNonUnitExponent &&
          exponent >= loaded.header.group_exponent) {
        throw std::runtime_error("service exponent outside group exponent");
      }
    }
    loaded.exponents.insert(loaded.exponents.end(), exponents.begin(),
                            exponents.end());
  }
  if (source.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("character batch changed size after preflight");
  }
  result.digest = batchDigest.finish();
  for (std::uint32_t parity = 0; parity < 2U; ++parity) {
    if (plan.parityTruncationSums[parity] != 0U &&
        parityCounts[parity] > std::numeric_limits<std::uint64_t>::max() /
                                   plan.parityTruncationSums[parity]) {
      throw std::runtime_error("service finite-term count overflow");
    }
    const std::uint64_t terms =
        parityCounts[parity] * plan.parityTruncationSums[parity];
    if (loaded.finiteTerms >
        std::numeric_limits<std::uint64_t>::max() - terms) {
      throw std::runtime_error("service finite-term sum overflow");
    }
    loaded.finiteTerms += terms;
  }
  return result;
}

std::vector<sc::Disk> characterRootDisks(const LoadedInput& input) {
  // The exact exponent table changes with chi, but exp(2*pi*i*e/E) depends
  // only on E.  Keep this O(E) MPFR table resident across every frame in the
  // process instead of paying O(batch*q) transcendental calls per frame.
  static std::map<std::uint32_t, std::vector<sc::Disk>> cache;
  const auto groupExponent = input.header.group_exponent;
  auto found = cache.find(groupExponent);
  if (found == cache.end()) {
    std::vector<sc::Disk> table(groupExponent);
    for (std::uint32_t e = 0; e < groupExponent; ++e) {
      table[e] = unitRoot(e, groupExponent);
    }
    found = cache.emplace(groupExponent, std::move(table)).first;
  }
  std::vector<sc::Disk> result(input.exponents.size());
  for (std::size_t i = 0; i < input.exponents.size(); ++i) {
    const std::uint32_t exponent = input.exponents[i];
    result[i] = exponent == sc::kNonUnitExponent
                    ? sc::Disk{0.0, 0.0, 0.0}
                    : found->second[exponent];
  }
  return result;
}

void writeOutput(const std::filesystem::path& path, const LoadedInput& input,
                 const std::vector<sc::Disk>& values,
                 const std::vector<std::uint32_t>& statuses,
                 std::uint64_t elapsedNanoseconds,
                 const sc::FactoredServiceOutputBinding* serviceBinding =
                     nullptr,
                 std::uint64_t publishedFrequencyCount = 0U) {
  if (values.size() != statuses.size()) {
    throw std::runtime_error("internal output/status size mismatch");
  }
  std::uint32_t statusOr = 0U;
  for (const auto status : statuses) statusOr |= status;
  sc::OutputHeader header{};
  const bool factored =
      input.header.version == sc::kFactoredFormatVersion;
  if (publishedFrequencyCount == 0U) {
    publishedFrequencyCount = input.header.frequency_count;
  }
  if (publishedFrequencyCount > input.header.frequency_count ||
      (publishedFrequencyCount != input.header.frequency_count &&
       serviceBinding == nullptr)) {
    throw std::runtime_error("invalid reduced output frequency count");
  }
  std::memcpy(
      header.magic,
      serviceBinding != nullptr
          ? (publishedFrequencyCount == input.header.frequency_count
                 ? sc::kFactoredServiceOutputMagic
                 : sc::kFactoredReducedServiceOutputMagic)
          : (factored ? sc::kFactoredOutputMagic : sc::kOutputMagic),
      8);
  header.version = input.header.version;
  header.q = input.header.q;
  header.batch_count = input.header.batch_count;
  header.run_dft = input.header.run_dft;
  header.frequency_start = input.header.frequency_start;
  header.frequency_count = publishedFrequencyCount;
  header.finite_gaussian_terms = input.finiteTerms;
  header.radix2_butterflies = input.header.run_dft
      ? static_cast<std::uint64_t>(input.header.batch_count) *
            (input.header.transform_length / 2U) *
            integerLog2(input.header.transform_length)
      : 0U;
  header.elapsed_nanoseconds = elapsedNanoseconds;
  header.status_or = statusOr;
  auto writePayload = [&](auto&& writeBytes) {
    writeBytes(&header, sizeof(header));
    if (serviceBinding != nullptr) {
      writeBytes(serviceBinding, sizeof(*serviceBinding));
    }
    // Multi-megabyte writes avoid one ostream/stdio call per 48-byte item.
    // The byte order remains exactly the historical character-major format.
    constexpr std::size_t kOutputChunkItems = 1U << 16U;
    std::vector<sc::OutputItem> chunk;
    chunk.reserve(kOutputChunkItems);
    const std::uint64_t publishedTotal =
        static_cast<std::uint64_t>(input.header.batch_count) *
        publishedFrequencyCount;
    for (std::uint64_t flatStart = 0U; flatStart < publishedTotal;
         flatStart += kOutputChunkItems) {
      const std::uint64_t count =
          std::min<std::uint64_t>(kOutputChunkItems, publishedTotal - flatStart);
      chunk.clear();
      for (std::uint64_t relative = 0U; relative < count; ++relative) {
        const std::uint64_t outputFlat = flatStart + relative;
        const std::uint32_t batch = static_cast<std::uint32_t>(
            outputFlat / publishedFrequencyCount);
        const std::uint64_t local = outputFlat % publishedFrequencyCount;
        const std::uint64_t flat =
            static_cast<std::uint64_t>(batch) * input.header.frequency_count +
            local;
        chunk.push_back(sc::OutputItem{
            input.characters[batch].character_id,
            input.header.frequency_start + local,
            values[flat], statuses[flat], 0U});
      }
      writeBytes(chunk.data(), chunk.size() * sizeof(sc::OutputItem));
    }
  };

  if (path == std::filesystem::path("-")) {
    // A sequence of service batches is self-framing: every header states its
    // character and frequency counts.  Sending each frame to stdout lets a
    // FIFO consumer validate and reduce it without a 339.8-TB file boundary.
    writePayload([](const void* data, std::size_t size) {
      if (size != 0U && std::fwrite(data, 1U, size, stdout) != size) {
        throw std::runtime_error("cannot stream output to stdout");
      }
    });
    if (std::fflush(stdout) != 0) {
      throw std::runtime_error("cannot flush streamed output");
    }
  } else {
    const auto parent = path.parent_path().empty() ? std::filesystem::path(".")
                                                    : path.parent_path();
    std::filesystem::create_directories(parent);
    const auto temporary = parent /
        ("." + path.filename().string() + "." + std::to_string(getpid()) + ".tmp");
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create output");
    writePayload([&](const void* data, std::size_t size) {
      output.write(reinterpret_cast<const char*>(data),
                   static_cast<std::streamsize>(size));
      if (!output) throw std::runtime_error("cannot write output");
    });
    output.flush();
    if (!output) throw std::runtime_error("cannot write output");
    output.close();
    std::error_code error;
    std::filesystem::rename(temporary, path, error);
    if (error) {
      std::filesystem::remove(temporary);
      throw std::runtime_error("cannot publish output: " + error.message());
    }
  }
  if (statusOr != 0U) {
    throw std::runtime_error("certified CUDA stage failed closed with status " +
                             std::to_string(statusOr));
  }
}

class PackedSignStreamWriter {
 public:
  PackedSignStreamWriter(
      const LoadedSharedPlan& plan, const MappedTimeTailControl& control,
      const sparkinterval::Sha256Digest& controlReceiptSha256,
      const sparkinterval::Sha256Digest& batchPartitionSha256,
      const sparkinterval::Sha256Digest& compactRosterSha256,
      const sparkinterval::Sha256Digest& pinsetSha256,
      const sparkinterval::Sha256Digest& sourceBindingSha256,
      std::uint64_t expectedFrames, std::uint32_t packingMode)
      : plan_(plan),
        control_(control),
        controlReceiptSha256_(controlReceiptSha256),
        batchPartitionSha256_(batchPartitionSha256),
        compactRosterSha256_(compactRosterSha256),
        pinsetSha256_(pinsetSha256),
        sourceBindingSha256_(sourceBindingSha256),
        expectedFrames_(expectedFrames),
        packingMode_(packingMode) {
    if (expectedFrames_ == 0U ||
        (packingMode_ != sc::kPackedSignHostProductionMode &&
         packingMode_ != sc::kPackedSignDeviceProductionMode)) {
      throw std::runtime_error(
          "strict-sign packed stream requires frames and a pinned packing "
          "location");
    }
  }

  void writeFrame(
      const LoadedInput& input,
      const sc::FactoredServiceOutputBinding& serviceBinding,
      const sparkinterval::Sha256Digest& batchSha256,
      const std::vector<sc::Disk>& values,
      const std::vector<std::uint32_t>& statuses,
      std::uint64_t elapsedNanoseconds) {
    const std::uint64_t expectedDeviceItems =
        static_cast<std::uint64_t>(input.header.batch_count) *
        input.header.frequency_count;
    if (packingMode_ != sc::kPackedSignHostProductionMode ||
        finished_ || frameCount_ >= expectedFrames_ ||
        values.size() != statuses.size() ||
        expectedDeviceItems > std::numeric_limits<std::size_t>::max() ||
        values.size() != static_cast<std::size_t>(expectedDeviceItems) ||
        input.header.q != plan_.header.q ||
        input.header.transform_length != plan_.header.transform_length ||
        input.header.frequency_start != 0U ||
        input.header.frequency_count != plan_.header.frequency_count ||
        input.header.run_dft != 1U ||
        std::memcmp(serviceBinding.plan_sha256, plan_.digest.data(),
                    plan_.digest.size()) != 0 ||
        std::memcmp(serviceBinding.batch_sha256, batchSha256.data(),
                    batchSha256.size()) != 0 ||
        serviceBinding.batch_ordinal != frameCount_ ||
        serviceBinding.campaign_batch_count != expectedFrames_ ||
        serviceBinding.campaign_character_count != plan_.header.batch_count ||
        serviceBinding.character_start + input.header.batch_count <
            serviceBinding.character_start ||
        serviceBinding.character_start + input.header.batch_count >
            serviceBinding.campaign_character_count) {
      throw std::runtime_error(
          "strict-sign packed frame input or batch binding differs");
    }
    const std::uint64_t sourceSamples = control_.header().sample_count;
    if (sourceSamples == 0U ||
        sourceSamples > input.header.frequency_count ||
        input.header.batch_count >
            std::numeric_limits<std::uint64_t>::max() / sourceSamples) {
      throw std::runtime_error("strict-sign packed frame size overflows");
    }
    const std::uint64_t itemCount =
        static_cast<std::uint64_t>(input.header.batch_count) * sourceSamples;
    const std::uint64_t payloadBytes = (itemCount + 3U) / 4U;
    const std::uint64_t butterflies =
        static_cast<std::uint64_t>(input.header.batch_count) *
        (input.header.transform_length / 2U) *
        integerLog2(input.header.transform_length);
    std::uint32_t statusOr = 0U;
    for (const auto status : statuses) statusOr |= status;
    if (statusOr != 0U) {
      throw std::runtime_error(
          "strict-sign packer refuses nonzero CUDA status");
    }

    sc::PackedSignFramePrefix prefix{};
    std::memcpy(prefix.magic, sc::kPackedSignFrameMagic, 8);
    prefix.version = sc::kPackedSignFormatVersion;
    prefix.mode = packingMode_;
    prefix.q = input.header.q;
    prefix.bits_per_code = sc::kPackedSignBitsPerCode;
    prefix.batch_character_count = input.header.batch_count;
    prefix.frequency_start = 0U;
    prefix.frequency_count = sourceSamples;
    prefix.first_t_numerator = 0U;
    if (sourceSamples >
        std::numeric_limits<std::uint64_t>::max() /
            kSourceSampleNumerator) {
      throw std::runtime_error("strict-sign packed source span overflows");
    }
    prefix.stop_t_numerator = sourceSamples * kSourceSampleNumerator;
    prefix.payload_bytes = payloadBytes;
    prefix.finite_gaussian_terms = input.finiteTerms;
    prefix.radix2_butterflies = butterflies;
    prefix.elapsed_nanoseconds = elapsedNanoseconds;
    prefix.status_or = 0U;
    prefix.reserved0 = 0U;

    sc::PackedSignBatchBinding binding{};
    binding.character_start = serviceBinding.character_start;
    binding.campaign_character_count =
        serviceBinding.campaign_character_count;
    binding.batch_ordinal = serviceBinding.batch_ordinal;
    binding.campaign_batch_count = serviceBinding.campaign_batch_count;

    sc::PackedSignDigestBindings digests{};
    std::memcpy(digests.plan_sha256, plan_.digest.data(),
                plan_.digest.size());
    std::memcpy(digests.batch_sha256, batchSha256.data(),
                batchSha256.size());
    std::memcpy(digests.control_sha256, control_.digest().data(),
                control_.digest().size());
    std::memcpy(digests.control_receipt_sha256,
                controlReceiptSha256_.data(),
                controlReceiptSha256_.size());
    std::memcpy(digests.batch_partition_sha256,
                batchPartitionSha256_.data(),
                batchPartitionSha256_.size());
    std::memcpy(digests.plan_roster_sha256,
                plan_.commitment.character_roster_sha256,
                sizeof(digests.plan_roster_sha256));
    std::memcpy(digests.compact_roster_sha256,
                compactRosterSha256_.data(), compactRosterSha256_.size());
    std::memcpy(digests.pinset_sha256, pinsetSha256_.data(),
                pinsetSha256_.size());
    std::memcpy(digests.source_binding_sha256,
                sourceBindingSha256_.data(), sourceBindingSha256_.size());
    std::memcpy(digests.previous_frame_sha256, previousFrameSha256_.data(),
                previousFrameSha256_.size());

    sparkinterval::detail::Sha256 frameDigest;
    frameDigest.update(kPackedFrameDomain, sizeof(kPackedFrameDomain));
    writeFrameBytes(&prefix, sizeof(prefix), &frameDigest);
    writeFrameBytes(&binding, sizeof(binding), &frameDigest);
    writeFrameBytes(&digests, sizeof(digests), &frameDigest);

    sparkinterval::detail::Sha256 payloadDigest;
    constexpr std::size_t kPayloadChunkBytes = 1U << 20U;
    std::vector<unsigned char> payload;
    payload.reserve(kPayloadChunkBytes);
    std::uint64_t emittedItems = 0U;
    std::uint64_t emittedPayloadBytes = 0U;
    auto flushPayload = [&]() {
      if (payload.empty()) return;
      writeFrameBytes(payload.data(), payload.size(), &frameDigest);
      payloadDigest.update(payload.data(), payload.size());
      checkedAdd(&emittedPayloadBytes, payload.size(),
                 "strict-sign payload byte count");
      payload.clear();
    };
    unsigned char packed = 0U;
    unsigned packedCodes = 0U;
    for (std::uint32_t character = 0U;
         character < input.header.batch_count; ++character) {
      const std::uint32_t parity = input.characters[character].parity;
      for (std::uint64_t sample = 0U; sample < sourceSamples; ++sample) {
        const std::uint64_t flat =
            static_cast<std::uint64_t>(character) *
                input.header.frequency_count +
            sample;
        if (flat >= values.size() || flat >= statuses.size() ||
            statuses[flat] != sc::kSuccess ||
            !validHostDisk(values[flat])) {
          throw std::runtime_error(
              "strict-sign packer encountered an invalid source disk");
        }
        const double threshold = control_.threshold(sample, parity);
        volatile double roundedSum = values[flat].radius + threshold;
        const double boundary =
            std::nextafter(roundedSum,
                           std::numeric_limits<double>::infinity());
        if (!std::isfinite(boundary)) {
          throw std::runtime_error(
              "strict-sign boundary overflows binary64");
        }
        unsigned char code = sc::kPackedSignAmbiguous;
        if (values[flat].real < -boundary) {
          code = sc::kPackedSignNegative;
          ++negativeCount_;
        } else if (values[flat].real > boundary) {
          code = sc::kPackedSignPositive;
          ++positiveCount_;
        } else {
          ++ambiguousCount_;
        }
        packed |= static_cast<unsigned char>(code << (2U * packedCodes));
        ++packedCodes;
        ++emittedItems;
        if (packedCodes == 4U) {
          payload.push_back(packed);
          packed = 0U;
          packedCodes = 0U;
          if (payload.size() == kPayloadChunkBytes) flushPayload();
        }
      }
    }
    if (packedCodes != 0U) payload.push_back(packed);
    flushPayload();
    if (emittedItems != itemCount || emittedPayloadBytes != payloadBytes) {
      throw std::runtime_error(
          "strict-sign packed payload item or byte count differs");
    }
    const auto payloadSha256 = payloadDigest.finish();
    const auto frameSha256 = frameDigest.finish();

    sc::PackedSignFrameTrailer trailer{};
    std::memcpy(trailer.magic, sc::kPackedSignTrailerMagic, 8);
    trailer.version = sc::kPackedSignFormatVersion;
    trailer.reserved0 = 0U;
    trailer.frame_ordinal = frameCount_;
    trailer.payload_bytes = payloadBytes;
    std::memcpy(trailer.payload_sha256, payloadSha256.data(),
                payloadSha256.size());
    std::memcpy(trailer.frame_sha256, frameSha256.data(),
                frameSha256.size());
    writeBodyBytes(&trailer, sizeof(trailer));

    previousFrameSha256_ = frameSha256;
    ++frameCount_;
    checkedAdd(&itemCount_, itemCount, "strict-sign item count");
    checkedAdd(&finiteTerms_, input.finiteTerms,
               "strict-sign finite-term count");
    checkedAdd(&butterflies_, butterflies,
               "strict-sign butterfly count");
    checkedAdd(&cudaElapsed_, elapsedNanoseconds,
               "strict-sign elapsed count");
    control_.verifyStable();
  }

  void writeDeviceFrame(
      const LoadedInput& input,
      const sc::FactoredServiceOutputBinding& serviceBinding,
      const sparkinterval::Sha256Digest& batchSha256,
      const std::vector<unsigned char>& payload,
      const strict_pack::DevicePackSummary& deviceSummary,
      std::uint64_t elapsedNanoseconds) {
    if (packingMode_ != sc::kPackedSignDeviceProductionMode ||
        finished_ || frameCount_ >= expectedFrames_ ||
        input.header.q != plan_.header.q ||
        input.header.transform_length != plan_.header.transform_length ||
        input.header.frequency_start != 0U ||
        input.header.frequency_count != plan_.header.frequency_count ||
        input.header.run_dft != 1U ||
        std::memcmp(serviceBinding.plan_sha256, plan_.digest.data(),
                    plan_.digest.size()) != 0 ||
        std::memcmp(serviceBinding.batch_sha256, batchSha256.data(),
                    batchSha256.size()) != 0 ||
        serviceBinding.batch_ordinal != frameCount_ ||
        serviceBinding.campaign_batch_count != expectedFrames_ ||
        serviceBinding.campaign_character_count != plan_.header.batch_count ||
        serviceBinding.character_start + input.header.batch_count <
            serviceBinding.character_start ||
        serviceBinding.character_start + input.header.batch_count >
            serviceBinding.campaign_character_count) {
      throw std::runtime_error(
          "device strict-sign packed frame input or batch binding differs");
    }
    if (deviceSummary.cuda_status_or != 0U ||
        deviceSummary.classifier_error_or != 0U) {
      throw std::runtime_error(
          "device strict-sign packer refuses nonzero CUDA/classifier status");
    }
    const std::uint64_t sourceSamples = control_.header().sample_count;
    if (sourceSamples == 0U ||
        sourceSamples > input.header.frequency_count ||
        input.header.batch_count >
            std::numeric_limits<std::uint64_t>::max() / sourceSamples) {
      throw std::runtime_error(
          "device strict-sign packed frame size overflows");
    }
    const std::uint64_t itemCount =
        static_cast<std::uint64_t>(input.header.batch_count) * sourceSamples;
    const std::uint64_t payloadBytes = (itemCount + 3U) / 4U;
    if (payloadBytes > std::numeric_limits<std::size_t>::max() ||
        payload.size() != static_cast<std::size_t>(payloadBytes)) {
      throw std::runtime_error(
          "device strict-sign packed payload length differs");
    }
    std::uint64_t localCounts[3] = {0U, 0U, 0U};
    for (std::uint64_t item = 0U; item < itemCount; ++item) {
      const unsigned char code = static_cast<unsigned char>(
          (payload[static_cast<std::size_t>(item / 4U)] >>
           (2U * static_cast<unsigned>(item & 3U))) &
          3U);
      if (code > sc::kPackedSignPositive) {
        throw std::runtime_error(
            "device strict-sign payload contains reserved code 3");
      }
      ++localCounts[code];
    }
    const unsigned usedCodes = static_cast<unsigned>(itemCount & 3U);
    if (usedCodes != 0U) {
      const unsigned usedBits = 2U * usedCodes;
      const unsigned char unusedMask =
          static_cast<unsigned char>(0xffU << usedBits);
      if ((payload.back() & unusedMask) != 0U) {
        throw std::runtime_error(
            "device strict-sign payload has nonzero padding");
      }
    }

    const std::uint64_t butterflies =
        static_cast<std::uint64_t>(input.header.batch_count) *
        (input.header.transform_length / 2U) *
        integerLog2(input.header.transform_length);
    sc::PackedSignFramePrefix prefix{};
    std::memcpy(prefix.magic, sc::kPackedSignFrameMagic, 8);
    prefix.version = sc::kPackedSignFormatVersion;
    prefix.mode = packingMode_;
    prefix.q = input.header.q;
    prefix.bits_per_code = sc::kPackedSignBitsPerCode;
    prefix.batch_character_count = input.header.batch_count;
    prefix.frequency_start = 0U;
    prefix.frequency_count = sourceSamples;
    prefix.first_t_numerator = 0U;
    if (sourceSamples >
        std::numeric_limits<std::uint64_t>::max() /
            kSourceSampleNumerator) {
      throw std::runtime_error(
          "device strict-sign packed source span overflows");
    }
    prefix.stop_t_numerator = sourceSamples * kSourceSampleNumerator;
    prefix.payload_bytes = payloadBytes;
    prefix.finite_gaussian_terms = input.finiteTerms;
    prefix.radix2_butterflies = butterflies;
    prefix.elapsed_nanoseconds = elapsedNanoseconds;
    prefix.status_or = 0U;
    prefix.reserved0 = 0U;

    sc::PackedSignBatchBinding binding{};
    binding.character_start = serviceBinding.character_start;
    binding.campaign_character_count =
        serviceBinding.campaign_character_count;
    binding.batch_ordinal = serviceBinding.batch_ordinal;
    binding.campaign_batch_count = serviceBinding.campaign_batch_count;

    sc::PackedSignDigestBindings digests{};
    std::memcpy(digests.plan_sha256, plan_.digest.data(),
                plan_.digest.size());
    std::memcpy(digests.batch_sha256, batchSha256.data(),
                batchSha256.size());
    std::memcpy(digests.control_sha256, control_.digest().data(),
                control_.digest().size());
    std::memcpy(digests.control_receipt_sha256,
                controlReceiptSha256_.data(),
                controlReceiptSha256_.size());
    std::memcpy(digests.batch_partition_sha256,
                batchPartitionSha256_.data(),
                batchPartitionSha256_.size());
    std::memcpy(digests.plan_roster_sha256,
                plan_.commitment.character_roster_sha256,
                sizeof(digests.plan_roster_sha256));
    std::memcpy(digests.compact_roster_sha256,
                compactRosterSha256_.data(), compactRosterSha256_.size());
    std::memcpy(digests.pinset_sha256, pinsetSha256_.data(),
                pinsetSha256_.size());
    std::memcpy(digests.source_binding_sha256,
                sourceBindingSha256_.data(), sourceBindingSha256_.size());
    std::memcpy(digests.previous_frame_sha256,
                previousFrameSha256_.data(),
                previousFrameSha256_.size());

    sparkinterval::detail::Sha256 frameDigest;
    frameDigest.update(kPackedFrameDomain, sizeof(kPackedFrameDomain));
    writeFrameBytes(&prefix, sizeof(prefix), &frameDigest);
    writeFrameBytes(&binding, sizeof(binding), &frameDigest);
    writeFrameBytes(&digests, sizeof(digests), &frameDigest);
    writeFrameBytes(payload.data(), payload.size(), &frameDigest);
    const auto payloadSha256 =
        sparkinterval::sha256(payload.data(), payload.size());
    const auto frameSha256 = frameDigest.finish();

    sc::PackedSignFrameTrailer trailer{};
    std::memcpy(trailer.magic, sc::kPackedSignTrailerMagic, 8);
    trailer.version = sc::kPackedSignFormatVersion;
    trailer.reserved0 = 0U;
    trailer.frame_ordinal = frameCount_;
    trailer.payload_bytes = payloadBytes;
    std::memcpy(trailer.payload_sha256, payloadSha256.data(),
                payloadSha256.size());
    std::memcpy(trailer.frame_sha256, frameSha256.data(),
                frameSha256.size());
    writeBodyBytes(&trailer, sizeof(trailer));

    previousFrameSha256_ = frameSha256;
    ++frameCount_;
    checkedAdd(&itemCount_, itemCount, "strict-sign item count");
    checkedAdd(&ambiguousCount_, localCounts[sc::kPackedSignAmbiguous],
               "strict-sign ambiguous count");
    checkedAdd(&negativeCount_, localCounts[sc::kPackedSignNegative],
               "strict-sign negative count");
    checkedAdd(&positiveCount_, localCounts[sc::kPackedSignPositive],
               "strict-sign positive count");
    checkedAdd(&finiteTerms_, input.finiteTerms,
               "strict-sign finite-term count");
    checkedAdd(&butterflies_, butterflies,
               "strict-sign butterfly count");
    checkedAdd(&cudaElapsed_, elapsedNanoseconds,
               "strict-sign elapsed count");
    control_.verifyStable();
  }

  void finish() {
    if (finished_ || frameCount_ != expectedFrames_ ||
        itemCount_ != static_cast<std::uint64_t>(plan_.header.batch_count) *
                          control_.header().sample_count ||
        itemCount_ != ambiguousCount_ + negativeCount_ + positiveCount_) {
      throw std::runtime_error(
          "strict-sign packed stream coverage differs");
    }
    control_.verifyStable();
    const auto bodySha256 = bodyDigest_.finish();
    sc::PackedSignStreamEnd end{};
    std::memcpy(end.magic, sc::kPackedSignEndMagic, 8);
    end.version = sc::kPackedSignFormatVersion;
    end.reserved0 = 0U;
    end.frame_count = frameCount_;
    end.item_count = itemCount_;
    std::memcpy(end.last_frame_sha256, previousFrameSha256_.data(),
                previousFrameSha256_.size());
    std::memcpy(end.body_sha256, bodySha256.data(), bodySha256.size());
    writeRaw(&end, sizeof(end));
    streamDigest_.update(&end, sizeof(end));
    streamSha256_ = streamDigest_.finish();
    if (std::fflush(stdout) != 0) {
      throw std::runtime_error(
          "cannot flush strict-sign packed stream");
    }
    finished_ = true;
  }

  const sparkinterval::Sha256Digest& streamSha256() const {
    if (!finished_) {
      throw std::runtime_error(
          "strict-sign stream digest requested before terminal record");
    }
    return streamSha256_;
  }
  std::uint64_t frameCount() const { return frameCount_; }
  std::uint64_t itemCount() const { return itemCount_; }
  std::uint64_t ambiguousCount() const { return ambiguousCount_; }
  std::uint64_t negativeCount() const { return negativeCount_; }
  std::uint64_t positiveCount() const { return positiveCount_; }
  std::uint64_t bytesWritten() const { return bytesWritten_; }

 private:
  static void checkedAdd(std::uint64_t* target, std::uint64_t value,
                         const char* label) {
    if (*target > std::numeric_limits<std::uint64_t>::max() - value) {
      throw std::runtime_error(std::string(label) + " overflows");
    }
    *target += value;
  }

  void writeRaw(const void* data, std::size_t size) {
    if (size != 0U && std::fwrite(data, 1U, size, stdout) != size) {
      throw std::runtime_error(
          "cannot stream strict-sign packed output");
    }
    checkedAdd(&bytesWritten_, size, "strict-sign output byte count");
  }

  void writeBodyBytes(const void* data, std::size_t size) {
    writeRaw(data, size);
    bodyDigest_.update(data, size);
    streamDigest_.update(data, size);
  }

  void writeFrameBytes(const void* data, std::size_t size,
                       sparkinterval::detail::Sha256* frameDigest) {
    writeBodyBytes(data, size);
    frameDigest->update(data, size);
  }

  const LoadedSharedPlan& plan_;
  const MappedTimeTailControl& control_;
  sparkinterval::Sha256Digest controlReceiptSha256_{};
  sparkinterval::Sha256Digest batchPartitionSha256_{};
  sparkinterval::Sha256Digest compactRosterSha256_{};
  sparkinterval::Sha256Digest pinsetSha256_{};
  sparkinterval::Sha256Digest sourceBindingSha256_{};
  std::uint64_t expectedFrames_ = 0U;
  std::uint32_t packingMode_ = 0U;
  sparkinterval::detail::Sha256 bodyDigest_;
  sparkinterval::detail::Sha256 streamDigest_;
  sparkinterval::Sha256Digest previousFrameSha256_{};
  sparkinterval::Sha256Digest streamSha256_{};
  std::uint64_t frameCount_ = 0U;
  std::uint64_t itemCount_ = 0U;
  std::uint64_t ambiguousCount_ = 0U;
  std::uint64_t negativeCount_ = 0U;
  std::uint64_t positiveCount_ = 0U;
  std::uint64_t finiteTerms_ = 0U;
  std::uint64_t butterflies_ = 0U;
  std::uint64_t cudaElapsed_ = 0U;
  std::uint64_t bytesWritten_ = 0U;
  bool finished_ = false;
};

unsigned parseIterations(const char* text) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error("invalid iteration count");
  }
  errno = 0;
  char* end = nullptr;
  const unsigned long value = std::strtoul(text, &end, 10);
  if (errno != 0 || end == nullptr || *end != '\0' || value == 0U ||
      value > 10000U) {
    throw std::runtime_error("iterations must lie in 1..10000");
  }
  return static_cast<unsigned>(value);
}

std::uint64_t parseSeedChunkRecords(const char* text) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    throw std::runtime_error("invalid shared-seed chunk count");
  }
  errno = 0;
  char* end = nullptr;
  const unsigned long long value = std::strtoull(text, &end, 10);
  if (errno != 0 || end == nullptr || *end != '\0' || value == 0U ||
      value > sc::kMaximumTransformLength) {
    throw std::runtime_error("shared-seed chunk count is outside 1..2^29");
  }
  return static_cast<std::uint64_t>(value);
}

struct ResidentBuffers {
  sc::CharacterHeader* characters = nullptr;
  sc::Disk* characterEpsilons = nullptr;
  sc::Disk* characterRoots = nullptr;
  sc::FrequencySeed* seeds = nullptr;
  sc::SharedFrequencySeed* sharedSeeds = nullptr;
  sc::Disk* values = nullptr;
  std::uint32_t* statuses = nullptr;
  std::uint64_t totalCapacity = 0U;
  std::uint64_t seedCapacity = 0U;
  std::uint64_t sharedSeedCapacity = 0U;
  std::uint64_t rootCapacity = 0U;
  std::uint32_t characterCapacity = 0U;

  ~ResidentBuffers() {
    cudaFree(statuses);
    cudaFree(values);
    cudaFree(sharedSeeds);
    cudaFree(seeds);
    cudaFree(characterRoots);
    cudaFree(characterEpsilons);
    cudaFree(characters);
  }

  void ensure(const LoadedInput& input,
              std::uint64_t factoredSharedSeedCapacity = 0U) {
    const std::uint64_t total = static_cast<std::uint64_t>(input.header.batch_count) *
                                input.header.frequency_count;
    const std::uint64_t roots = static_cast<std::uint64_t>(input.header.batch_count) *
                                input.header.q;
    if (input.header.batch_count > characterCapacity) {
      cudaFree(characters);
      cudaFree(characterEpsilons);
      CUDA_CHECK(cudaMalloc(&characters,
                            input.header.batch_count * sizeof(sc::CharacterHeader)));
      CUDA_CHECK(cudaMalloc(&characterEpsilons,
                            input.header.batch_count * sizeof(sc::Disk)));
      characterCapacity = input.header.batch_count;
    }
    if (roots > rootCapacity) {
      cudaFree(characterRoots);
      CUDA_CHECK(cudaMalloc(&characterRoots, roots * sizeof(sc::Disk)));
      rootCapacity = roots;
    }
    if (total > totalCapacity) {
      cudaFree(statuses);
      cudaFree(values);
      CUDA_CHECK(cudaMalloc(&values, total * sizeof(sc::Disk)));
      CUDA_CHECK(cudaMalloc(&statuses, total * sizeof(std::uint32_t)));
      totalCapacity = total;
    }
    if (input.header.version == sc::kFormatVersion && total > seedCapacity) {
      cudaFree(seeds);
      CUDA_CHECK(cudaMalloc(&seeds, total * sizeof(sc::FrequencySeed)));
      seedCapacity = total;
    }
    const std::uint64_t requestedSharedSeedCapacity =
        factoredSharedSeedCapacity == 0U ? input.header.frequency_count
                                        : factoredSharedSeedCapacity;
    if (input.header.version == sc::kFactoredFormatVersion &&
        requestedSharedSeedCapacity > sharedSeedCapacity) {
      cudaFree(sharedSeeds);
      CUDA_CHECK(cudaMalloc(&sharedSeeds, requestedSharedSeedCapacity *
                                             sizeof(sc::SharedFrequencySeed)));
      sharedSeedCapacity = requestedSharedSeedCapacity;
    }
  }
};

struct DevicePackedFrame {
  std::vector<unsigned char> payload;
  strict_pack::DevicePackSummary summary{};
  std::uint64_t classificationNanoseconds = 0U;
  std::uint64_t transferNanoseconds = 0U;
};

class DeviceStrictSignPacker {
 public:
  DeviceStrictSignPacker(const MappedTimeTailControl& control,
                         std::uint32_t maximumBatch,
                         std::uint64_t frequencyStride)
      : control_(control),
        maximumBatch_(maximumBatch),
        frequencyStride_(frequencyStride),
        sourceSamples_(control.header().sample_count) {
    if (maximumBatch_ == 0U || sourceSamples_ == 0U ||
        sourceSamples_ > frequencyStride_ ||
        maximumBatch_ >
            std::numeric_limits<std::uint64_t>::max() / sourceSamples_) {
      throw std::runtime_error(
          "device strict-sign packer dimensions overflow");
    }
    const std::uint64_t maximumItems =
        static_cast<std::uint64_t>(maximumBatch_) * sourceSamples_;
    payloadCapacity_ = (maximumItems + 3U) / 4U;
    if (sourceSamples_ >
            std::numeric_limits<std::size_t>::max() /
                sizeof(sc::TimeTailControlItem) ||
        payloadCapacity_ > std::numeric_limits<std::size_t>::max()) {
      throw std::runtime_error(
          "device strict-sign packer allocation is unsupported");
    }
    try {
      CUDA_CHECK(cudaMalloc(
          &deviceControls_,
          static_cast<std::size_t>(sourceSamples_) *
              sizeof(sc::TimeTailControlItem)));
      CUDA_CHECK(cudaMalloc(&devicePayload_,
                            static_cast<std::size_t>(payloadCapacity_)));
      CUDA_CHECK(cudaMalloc(&deviceSummary_,
                            sizeof(strict_pack::DevicePackSummary)));
      control_.verifyStable();
      const auto uploadStarted = std::chrono::steady_clock::now();
      CUDA_CHECK(cudaMemcpy(
          deviceControls_, control_.items(),
          static_cast<std::size_t>(sourceSamples_) *
              sizeof(sc::TimeTailControlItem),
          cudaMemcpyHostToDevice));
      const auto uploadStopped = std::chrono::steady_clock::now();
      controlUploadNanoseconds_ = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              uploadStopped - uploadStarted)
              .count());
      control_.verifyStable();
    } catch (...) {
      cudaFree(deviceSummary_);
      cudaFree(devicePayload_);
      cudaFree(deviceControls_);
      deviceSummary_ = nullptr;
      devicePayload_ = nullptr;
      deviceControls_ = nullptr;
      throw;
    }
  }

  ~DeviceStrictSignPacker() {
    cudaFree(deviceSummary_);
    cudaFree(devicePayload_);
    cudaFree(deviceControls_);
  }

  DeviceStrictSignPacker(const DeviceStrictSignPacker&) = delete;
  DeviceStrictSignPacker& operator=(const DeviceStrictSignPacker&) = delete;

  DevicePackedFrame pack(
      const LoadedInput& input, const sc::Disk* deviceValues,
      const std::uint32_t* deviceStatuses,
      const sc::CharacterHeader* deviceCharacters) {
    if (deviceValues == nullptr || deviceStatuses == nullptr ||
        deviceCharacters == nullptr ||
        input.header.run_dft != 1U ||
        input.header.frequency_start != 0U ||
        input.header.frequency_count != frequencyStride_ ||
        input.header.transform_length != frequencyStride_ ||
        input.header.batch_count == 0U ||
        input.header.batch_count > maximumBatch_ ||
        sourceSamples_ > input.header.frequency_count ||
        input.header.batch_count >
            std::numeric_limits<std::uint64_t>::max() / sourceSamples_) {
      throw std::runtime_error(
          "device strict-sign packer refuses a partial/non-production span");
    }
    const std::uint64_t itemCount =
        static_cast<std::uint64_t>(input.header.batch_count) * sourceSamples_;
    const std::uint64_t payloadBytes = (itemCount + 3U) / 4U;
    const std::uint64_t totalStatuses =
        static_cast<std::uint64_t>(input.header.batch_count) *
        input.header.frequency_count;
    if (payloadBytes == 0U || payloadBytes > payloadCapacity_ ||
        payloadBytes > std::numeric_limits<std::size_t>::max()) {
      throw std::runtime_error(
          "device strict-sign packed payload size overflows");
    }

    CUDA_CHECK(cudaMemset(deviceSummary_, 0,
                          sizeof(strict_pack::DevicePackSummary)));
    cudaEvent_t startEvent = nullptr;
    cudaEvent_t stopEvent = nullptr;
    CUDA_CHECK(cudaEventCreate(&startEvent));
    CUDA_CHECK(cudaEventCreate(&stopEvent));
    CUDA_CHECK(cudaEventRecord(startEvent));
    strict_pack::reduceStatuses<<<blocksFor(totalStatuses), kThreads>>>(
        deviceStatuses, totalStatuses, deviceSummary_);
    CUDA_CHECK(cudaGetLastError());
    strict_pack::packStrictSigns<<<blocksFor(payloadBytes), kThreads>>>(
        deviceValues, deviceStatuses, deviceCharacters, deviceControls_,
        frequencyStride_, sourceSamples_, input.header.batch_count,
        devicePayload_, payloadBytes, deviceSummary_);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stopEvent));
    CUDA_CHECK(cudaEventSynchronize(stopEvent));
    float elapsedMilliseconds = 0.0F;
    CUDA_CHECK(
        cudaEventElapsedTime(&elapsedMilliseconds, startEvent, stopEvent));
    CUDA_CHECK(cudaEventDestroy(stopEvent));
    CUDA_CHECK(cudaEventDestroy(startEvent));

    DevicePackedFrame result;
    result.classificationNanoseconds = static_cast<std::uint64_t>(
        static_cast<double>(elapsedMilliseconds) * 1000000.0);
    CUDA_CHECK(cudaMemcpy(&result.summary, deviceSummary_,
                          sizeof(result.summary), cudaMemcpyDeviceToHost));
    checkedAdd(&boundedStatusBytesCopied_, sizeof(result.summary),
               "device strict-sign bounded-status transfer");
    if (result.summary.cuda_status_or != 0U ||
        result.summary.classifier_error_or != 0U) {
      throw std::runtime_error(
          "device strict-sign classification failed closed with status " +
          std::to_string(result.summary.cuda_status_or) + "/" +
          std::to_string(result.summary.classifier_error_or));
    }
    result.payload.resize(static_cast<std::size_t>(payloadBytes));
    const auto transferStarted = std::chrono::steady_clock::now();
    CUDA_CHECK(cudaMemcpy(result.payload.data(), devicePayload_,
                          result.payload.size(), cudaMemcpyDeviceToHost));
    const auto transferStopped = std::chrono::steady_clock::now();
    result.transferNanoseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            transferStopped - transferStarted)
            .count());
    checkedAdd(&payloadBytesCopied_, payloadBytes,
               "device strict-sign payload transfer");
    const std::uint64_t avoidedPerItem =
        sizeof(sc::Disk) + sizeof(std::uint32_t);
    if (totalStatuses >
        std::numeric_limits<std::uint64_t>::max() / avoidedPerItem) {
      throw std::runtime_error(
          "device strict-sign avoided transfer count overflows");
    }
    checkedAdd(&fullArrayBytesAvoided_, totalStatuses * avoidedPerItem,
               "device strict-sign avoided transfer");
    checkedAdd(&classificationNanoseconds_, result.classificationNanoseconds,
               "device strict-sign classifier time");
    checkedAdd(&transferNanoseconds_, result.transferNanoseconds,
               "device strict-sign transfer time");
    control_.verifyStable();
    return result;
  }

  std::uint64_t controlUploadNanoseconds() const {
    return controlUploadNanoseconds_;
  }
  std::uint64_t classificationNanoseconds() const {
    return classificationNanoseconds_;
  }
  std::uint64_t transferNanoseconds() const {
    return transferNanoseconds_;
  }
  std::uint64_t payloadBytesCopied() const { return payloadBytesCopied_; }
  std::uint64_t boundedStatusBytesCopied() const {
    return boundedStatusBytesCopied_;
  }
  std::uint64_t fullArrayBytesAvoided() const {
    return fullArrayBytesAvoided_;
  }

 private:
  static void checkedAdd(std::uint64_t* target, std::uint64_t value,
                         const char* label) {
    if (*target > std::numeric_limits<std::uint64_t>::max() - value) {
      throw std::runtime_error(std::string(label) + " overflows");
    }
    *target += value;
  }

  const MappedTimeTailControl& control_;
  std::uint32_t maximumBatch_ = 0U;
  std::uint64_t frequencyStride_ = 0U;
  std::uint64_t sourceSamples_ = 0U;
  std::uint64_t payloadCapacity_ = 0U;
  sc::TimeTailControlItem* deviceControls_ = nullptr;
  unsigned char* devicePayload_ = nullptr;
  strict_pack::DevicePackSummary* deviceSummary_ = nullptr;
  std::uint64_t controlUploadNanoseconds_ = 0U;
  std::uint64_t classificationNanoseconds_ = 0U;
  std::uint64_t transferNanoseconds_ = 0U;
  std::uint64_t payloadBytesCopied_ = 0U;
  std::uint64_t boundedStatusBytesCopied_ = 0U;
  std::uint64_t fullArrayBytesAvoided_ = 0U;
};

std::uint64_t execute(const LoadedInput& input, ResidentBuffers* buffers,
                      Radix2Plan* plan, unsigned iterations,
                      std::vector<sc::Disk>* hostValues,
                      std::vector<std::uint32_t>* hostStatuses) {
  const std::uint64_t total = static_cast<std::uint64_t>(input.header.batch_count) *
                              input.header.frequency_count;
  const auto roots = characterRootDisks(input);
  buffers->ensure(input);
  CUDA_CHECK(cudaMemcpy(buffers->characters, input.characters.data(),
                        input.characters.size() * sizeof(input.characters[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(buffers->characterEpsilons,
                        input.characterEpsilons.data(),
                        input.characterEpsilons.size() *
                            sizeof(input.characterEpsilons[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(buffers->characterRoots, roots.data(),
                        roots.size() * sizeof(roots[0]), cudaMemcpyHostToDevice));
  if (input.header.version == sc::kFactoredFormatVersion) {
    CUDA_CHECK(cudaMemcpy(buffers->sharedSeeds, input.sharedSeeds.data(),
                          input.sharedSeeds.size() *
                              sizeof(input.sharedSeeds[0]),
                          cudaMemcpyHostToDevice));
  } else {
    CUDA_CHECK(cudaMemcpy(buffers->seeds, input.seeds.data(),
                          input.seeds.size() * sizeof(input.seeds[0]),
                          cudaMemcpyHostToDevice));
  }
  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  sc::Disk* finalValues = buffers->values;
  CUDA_CHECK(cudaEventRecord(start));
  for (unsigned iteration = 0; iteration < iterations; ++iteration) {
    finiteGaussianKernel<<<blocksFor(total), kThreads>>>(
        input.header, buffers->characters, buffers->characterRoots,
        buffers->seeds, buffers->sharedSeeds, buffers->characterEpsilons,
        0U, input.header.frequency_count, buffers->values, buffers->statuses);
    CUDA_CHECK(cudaGetLastError());
    if (input.header.run_dft != 0U) {
      if (plan == nullptr || plan->length() != input.header.transform_length ||
          plan->maximumBatch() < input.header.batch_count) {
        throw std::runtime_error("resident FFT plan mismatch");
      }
      finalValues = plan->execute(buffers->values, input.header.batch_count);
      validateDisks<<<blocksFor(total), kThreads>>>(
          finalValues, buffers->statuses, total);
      CUDA_CHECK(cudaGetLastError());
    }
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float elapsedMilliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsedMilliseconds, start, stop));
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaEventDestroy(start));
  hostValues->resize(total);
  hostStatuses->resize(total);
  CUDA_CHECK(cudaMemcpy(hostValues->data(), finalValues,
                        total * sizeof(sc::Disk), cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(hostStatuses->data(), buffers->statuses,
                        total * sizeof(std::uint32_t), cudaMemcpyDeviceToHost));
  return static_cast<std::uint64_t>(
      static_cast<double>(elapsedMilliseconds) * 1000000.0 / iterations);
}

void uploadServiceCharacters(const LoadedInput& input, ResidentBuffers* buffers,
                             std::uint64_t sharedSeedCapacity) {
  const auto roots = characterRootDisks(input);
  buffers->ensure(input, sharedSeedCapacity);
  CUDA_CHECK(cudaMemcpy(buffers->characters, input.characters.data(),
                        input.characters.size() * sizeof(input.characters[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(buffers->characterEpsilons,
                        input.characterEpsilons.data(),
                        input.characterEpsilons.size() *
                            sizeof(input.characterEpsilons[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(buffers->characterRoots, roots.data(),
                        roots.size() * sizeof(roots[0]),
                        cudaMemcpyHostToDevice));
}

void validateSharedChunk(const LoadedSharedPlan& plan,
                         const std::vector<sc::SharedFrequencySeed>& seeds,
                         std::uint64_t start) {
  for (std::uint64_t local = 0; local < seeds.size(); ++local) {
    const auto& shared = seeds[local];
    const std::uint64_t expected = plan.header.frequency_start + start + local;
    const std::int64_t signedExpected =
        expected <= plan.header.transform_length / 2U
            ? static_cast<std::int64_t>(expected)
            : static_cast<std::int64_t>(expected - plan.header.transform_length);
    if (shared.index != expected || shared.signed_index != signedExpected ||
        !validHostDisk(shared.w)) {
      throw std::runtime_error("shared plan changed after preflight");
    }
    const sc::ParitySeed paritySeeds[2] = {shared.even, shared.odd};
    for (const auto& seed : paritySeeds) {
      if (seed.truncation > 100000000U || seed.reserved0 != 0U ||
          !validHostDisk(seed.prefactor) ||
          !std::isfinite(seed.analytic_radius_hi) ||
          seed.analytic_radius_hi < 0.0) {
        throw std::runtime_error("shared plan parity changed after preflight");
      }
    }
  }
}

struct OpenSharedPlan {
  std::ifstream input;
  sparkinterval::detail::Sha256 digest;
};

OpenSharedPlan reopenSharedPlan(const LoadedSharedPlan& plan) {
  OpenSharedPlan result{std::ifstream(plan.path, std::ios::binary), {}};
  if (!result.input) {
    throw std::runtime_error("cannot reopen shared plan " + plan.path.string());
  }
  const auto header = readObject<sc::InputHeader>(
      result.input, "reopened shared plan header", &result.digest);
  const auto commitment = readObject<sc::FactoredPlanCommitment>(
      result.input, "reopened shared plan commitment", &result.digest);
  const auto parameters = readObject<sc::ParameterHeader>(
      result.input, "reopened shared plan parameters", &result.digest);
  if (std::memcmp(&header, &plan.header, sizeof(header)) != 0 ||
      std::memcmp(&commitment, &plan.commitment, sizeof(commitment)) != 0 ||
      std::memcmp(&parameters, &plan.parameters, sizeof(parameters)) != 0) {
    throw std::runtime_error("shared plan header changed after preflight");
  }
  return result;
}

void finishSharedPlanReplay(OpenSharedPlan* replay,
                            const LoadedSharedPlan& plan) {
  if (replay->input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("shared plan grew after preflight");
  }
  if (replay->digest.finish() != plan.digest) {
    throw std::runtime_error("shared plan digest changed after preflight");
  }
}

void uploadResidentSharedPlan(const LoadedSharedPlan& plan,
                              ResidentBuffers* buffers) {
  constexpr std::uint64_t kTransferRecords = 1U << 20U;
  OpenSharedPlan replay = reopenSharedPlan(plan);
  for (std::uint64_t start = 0; start < plan.header.frequency_count;) {
    const std::uint64_t count = std::min<std::uint64_t>(
        kTransferRecords, plan.header.frequency_count - start);
    const auto seeds = readArray<sc::SharedFrequencySeed>(
        replay.input, count, "resident shared seeds", &replay.digest);
    validateSharedChunk(plan, seeds, start);
    CUDA_CHECK(cudaMemcpy(buffers->sharedSeeds + start, seeds.data(),
                          seeds.size() * sizeof(seeds[0]),
                          cudaMemcpyHostToDevice));
    start += count;
  }
  finishSharedPlanReplay(&replay, plan);
}

void executeStreamingSharedPlan(const LoadedSharedPlan& plan,
                                const LoadedInput& input,
                                ResidentBuffers* buffers,
                                std::uint64_t chunkRecords) {
  OpenSharedPlan replay = reopenSharedPlan(plan);
  for (std::uint64_t start = 0; start < plan.header.frequency_count;) {
    const std::uint64_t count =
        std::min(chunkRecords, plan.header.frequency_count - start);
    const auto seeds = readArray<sc::SharedFrequencySeed>(
        replay.input, count, "streamed shared seeds", &replay.digest);
    validateSharedChunk(plan, seeds, start);
    CUDA_CHECK(cudaMemcpy(buffers->sharedSeeds, seeds.data(),
                          seeds.size() * sizeof(seeds[0]),
                          cudaMemcpyHostToDevice));
    const std::uint64_t chunkWork =
        static_cast<std::uint64_t>(input.header.batch_count) * count;
    finiteGaussianKernel<<<blocksFor(chunkWork), kThreads>>>(
        input.header, buffers->characters, buffers->characterRoots,
        buffers->seeds, buffers->sharedSeeds, buffers->characterEpsilons,
        start, count, buffers->values, buffers->statuses);
    CUDA_CHECK(cudaGetLastError());
    start += count;
  }
  finishSharedPlanReplay(&replay, plan);
}

struct ServiceBatchExecution {
  std::uint64_t elapsedNanoseconds = 0U;
  sc::Disk* deviceValues = nullptr;
};

ServiceBatchExecution executeServiceBatch(
    const LoadedSharedPlan& sharedPlan, const LoadedInput& input,
    ResidentBuffers* buffers, Radix2Plan* fftPlan, unsigned iterations,
    bool sharedSeedsResident, std::uint64_t sharedSeedCapacity,
    bool* residentSeedsUploaded, std::vector<sc::Disk>* hostValues,
    std::vector<std::uint32_t>* hostStatuses) {
  if ((hostValues == nullptr) != (hostStatuses == nullptr)) {
    throw std::runtime_error(
        "service host value/status copies must be requested together");
  }
  const std::uint64_t total =
      static_cast<std::uint64_t>(input.header.batch_count) *
      input.header.frequency_count;
  uploadServiceCharacters(input, buffers, sharedSeedCapacity);
  if (sharedSeedsResident && !*residentSeedsUploaded) {
    uploadResidentSharedPlan(sharedPlan, buffers);
    *residentSeedsUploaded = true;
  }
  cudaEvent_t startEvent = nullptr;
  cudaEvent_t stopEvent = nullptr;
  CUDA_CHECK(cudaEventCreate(&startEvent));
  CUDA_CHECK(cudaEventCreate(&stopEvent));
  sc::Disk* finalValues = buffers->values;
  CUDA_CHECK(cudaEventRecord(startEvent));
  for (unsigned iteration = 0; iteration < iterations; ++iteration) {
    if (sharedSeedsResident) {
      finiteGaussianKernel<<<blocksFor(total), kThreads>>>(
          input.header, buffers->characters, buffers->characterRoots,
          buffers->seeds, buffers->sharedSeeds, buffers->characterEpsilons,
          0U, input.header.frequency_count, buffers->values,
          buffers->statuses);
      CUDA_CHECK(cudaGetLastError());
    } else {
      executeStreamingSharedPlan(sharedPlan, input, buffers,
                                 sharedSeedCapacity);
    }
    if (input.header.run_dft != 0U) {
      if (fftPlan == nullptr ||
          fftPlan->length() != input.header.transform_length ||
          fftPlan->maximumBatch() < input.header.batch_count) {
        throw std::runtime_error("service FFT plan mismatch");
      }
      finalValues = fftPlan->execute(buffers->values,
                                     input.header.batch_count);
      validateDisks<<<blocksFor(total), kThreads>>>(
          finalValues, buffers->statuses, total);
      CUDA_CHECK(cudaGetLastError());
    }
  }
  CUDA_CHECK(cudaEventRecord(stopEvent));
  CUDA_CHECK(cudaEventSynchronize(stopEvent));
  float elapsedMilliseconds = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsedMilliseconds, startEvent, stopEvent));
  CUDA_CHECK(cudaEventDestroy(stopEvent));
  CUDA_CHECK(cudaEventDestroy(startEvent));
  if (hostValues != nullptr) {
    hostValues->resize(total);
    hostStatuses->resize(total);
    CUDA_CHECK(cudaMemcpy(hostValues->data(), finalValues,
                          total * sizeof(sc::Disk), cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(hostStatuses->data(), buffers->statuses,
                          total * sizeof(std::uint32_t),
                          cudaMemcpyDeviceToHost));
  }
  return {
      static_cast<std::uint64_t>(
          static_cast<double>(elapsedMilliseconds) * 1000000.0 / iterations),
      finalValues,
  };
}

unsigned __int128 explicitServiceBytes(const sc::InputHeader& plan,
                                       std::uint32_t maximumBatch,
                                       std::uint64_t sharedSeedCapacity,
                                       unsigned __int128 additionalDeviceBytes) {
  using Wide = unsigned __int128;
  const Wide n = plan.frequency_count;
  const Wide batch = maximumBatch;
  Wide total = static_cast<Wide>(sharedSeedCapacity) *
               sizeof(sc::SharedFrequencySeed);
  total += batch * n * (sizeof(sc::Disk) + sizeof(std::uint32_t));
  total += batch * plan.q * sizeof(sc::Disk);
  total += batch * (sizeof(sc::CharacterHeader) + sizeof(sc::Disk));
  if (plan.run_dft != 0U) {
    total += batch * n * sizeof(sc::Disk);
    total += (n - 1U) * sizeof(sc::Disk);
    total += ((n / 2U + kRootAnchorSpan - 1U) / kRootAnchorSpan) *
             sizeof(sc::Disk);
  }
  total += additionalDeviceBytes;
  return total;
}

std::uint64_t chooseSharedSeedCapacity(const LoadedSharedPlan& plan,
                                       std::uint32_t maximumBatch,
                                       std::uint64_t campaignBatchCount,
                                       std::uint64_t requestedChunkRecords,
                                       unsigned __int128
                                           additionalDeviceBytes) {
  std::size_t freeBytes = 0U;
  std::size_t totalBytes = 0U;
  CUDA_CHECK(cudaMemGetInfo(&freeBytes, &totalBytes));
  constexpr std::uint64_t kMaximumReserve = 8ULL << 30U;
  const std::uint64_t reserve = std::min<std::uint64_t>(
      kMaximumReserve, static_cast<std::uint64_t>(freeBytes) / 10U);
  const unsigned __int128 usable = freeBytes - reserve;
  if (requestedChunkRecords != 0U) {
    const std::uint64_t requested = std::min(
        requestedChunkRecords, plan.header.frequency_count);
    if (requested != plan.header.frequency_count && campaignBatchCount != 1U) {
      throw std::runtime_error(
          "forced streaming is allowed only for a one-batch campaign");
    }
    if (explicitServiceBytes(plan.header, maximumBatch, requested,
                             additionalDeviceBytes) > usable) {
      throw std::runtime_error(
          "requested shared-seed chunk exceeds safe device memory");
    }
    return requested;
  }
  if (explicitServiceBytes(plan.header, maximumBatch,
                           plan.header.frequency_count,
                           additionalDeviceBytes) <= usable) {
    return plan.header.frequency_count;
  }
  const std::uint64_t chunk =
      std::min<std::uint64_t>(1U << 20U, plan.header.frequency_count);
  if (campaignBatchCount != 1U) {
    throw std::runtime_error(
        "shared seeds do not fit resident and streaming would reread them "
        "across character batches; regenerate smaller batches or use a "
        "larger-memory device");
  }
  if (explicitServiceBytes(plan.header, maximumBatch, chunk,
                           additionalDeviceBytes) > usable) {
    throw std::runtime_error(
        "bounded service batch exceeds device memory after safety reserve");
  }
  return chunk;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    unsigned iterations = 1U;
    std::uint64_t requestedSharedSeedChunkRecords = 0U;
    bool strictSignPacked = false;
    bool strictSignPackedDevice = false;
    std::filesystem::path strictSignControlPath;
    sparkinterval::Sha256Digest strictSignControlReceiptSha256{};
    sparkinterval::Sha256Digest strictSignCompactRosterSha256{};
    sparkinterval::Sha256Digest strictSignPinsetSha256{};
    sparkinterval::Sha256Digest strictSignSourceBindingSha256{};
    int firstPair = 1;
    if (argc >= 4 && std::strcmp(argv[1], "--iterations") == 0) {
      iterations = parseIterations(argv[2]);
      firstPair = 3;
    }
    bool sourceSamplesOnly = false;
    bool sawSharedSeedChunkOption = false;
    while (firstPair < argc) {
      if (std::strcmp(argv[firstPair], "--source-samples-only") == 0) {
        if (sourceSamplesOnly) {
          throw std::runtime_error("duplicate --source-samples-only option");
        }
        sourceSamplesOnly = true;
        ++firstPair;
        continue;
      }
      if (firstPair + 1 < argc &&
          std::strcmp(argv[firstPair], "--shared-seed-chunk-records") == 0) {
        if (sawSharedSeedChunkOption) {
          throw std::runtime_error(
              "duplicate --shared-seed-chunk-records option");
        }
        requestedSharedSeedChunkRecords =
            parseSeedChunkRecords(argv[firstPair + 1]);
        sawSharedSeedChunkOption = true;
        firstPair += 2;
        continue;
      }
      const bool requestedHostPacking =
          std::strcmp(argv[firstPair], "--strict-sign-packed") == 0;
      const bool requestedDevicePacking =
          std::strcmp(argv[firstPair], "--strict-sign-packed-device") == 0;
      if (requestedHostPacking || requestedDevicePacking) {
        if (strictSignPacked || firstPair + 5 >= argc) {
          throw std::runtime_error(
              "a strict-sign packing mode requires CONTROL "
              "CONTROL_RECEIPT_SHA256 COMPACT_ROSTER_SHA256 "
              "PINSET_SHA256 SOURCE_BINDING_SHA256 exactly once");
        }
        strictSignPacked = true;
        strictSignPackedDevice = requestedDevicePacking;
        strictSignControlPath = argv[firstPair + 1];
        strictSignControlReceiptSha256 = parseSha256Hex(
            argv[firstPair + 2], "control receipt SHA-256");
        strictSignCompactRosterSha256 = parseSha256Hex(
            argv[firstPair + 3], "compact roster SHA-256");
        strictSignPinsetSha256 =
            parseSha256Hex(argv[firstPair + 4], "pinset SHA-256");
        strictSignSourceBindingSha256 = parseSha256Hex(
            argv[firstPair + 5], "source binding SHA-256");
        firstPair += 6;
        continue;
      }
      break;
    }
    bool factoredService = false;
    std::filesystem::path sharedPlanPath;
    if (firstPair < argc &&
        std::strcmp(argv[firstPair], "--factored-service") == 0) {
      factoredService = true;
      ++firstPair;
      if (firstPair >= argc) {
        throw std::runtime_error("--factored-service requires a shared plan");
      }
      sharedPlanPath = argv[firstPair++];
    }
    if (argc - firstPair < 2 || ((argc - firstPair) & 1) != 0) {
      std::fprintf(stderr,
                   "usage: %s [--iterations N] "
                   "[--shared-seed-chunk-records N] "
                   "[--source-samples-only] "
                   "[--strict-sign-packed CONTROL "
                   "CONTROL_RECEIPT_SHA256 COMPACT_ROSTER_SHA256 "
                   "PINSET_SHA256 SOURCE_BINDING_SHA256 | "
                   "--strict-sign-packed-device CONTROL "
                   "CONTROL_RECEIPT_SHA256 COMPACT_ROSTER_SHA256 "
                   "PINSET_SHA256 SOURCE_BINDING_SHA256] "
                   "[--factored-service SHARED_PLAN] "
                   "INPUT OUTPUT [INPUT OUTPUT ...]\n",
                   argv[0]);
      return 2;
    }
    int device = 0;
    CUDA_CHECK(cudaGetDevice(&device));
    cudaDeviceProp properties{};
    CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
    if (properties.major != 9 || properties.minor != 0) {
      throw std::runtime_error("strict build requires a physical sm_90 H100");
    }
#endif
    if (factoredService) {
      if (strictSignPacked && !sourceSamplesOnly) {
        throw std::runtime_error(
            "strict-sign packing requires --source-samples-only");
      }
      const LoadedSharedPlan sharedPlan = loadSharedPlan(sharedPlanPath);
      const std::uint64_t publishedFrequencyCount = sourceSamplesOnly
          ? sourceSampleCount(sharedPlan)
          : sharedPlan.header.frequency_count;
      bool binaryOutputOnStdout = false;
      for (int argument = firstPair; argument < argc; argument += 2) {
        binaryOutputOnStdout |= std::strcmp(argv[argument + 1], "-") == 0;
        if (strictSignPacked &&
            std::strcmp(argv[argument + 1], "-") != 0) {
          throw std::runtime_error(
              "strict-sign packed frames form one terminally sealed stdout "
              "stream; every service output must be '-'");
        }
      }
      FILE* const reportStream = binaryOutputOnStdout ? stderr : stdout;
      constexpr char kRosterDomain[] =
          "SparkInterval/DirichletBookerSmallQ/roster/v3";
      sparkinterval::detail::Sha256 rosterDigest;
      // sizeof includes the one NUL byte used by the Python domain separator.
      rosterDigest.update(kRosterDomain, sizeof(kRosterDomain));
      std::vector<BatchPreview> previews;
      const std::uint64_t suppliedBatchCount =
          static_cast<std::uint64_t>((argc - firstPair) / 2);
      previews.reserve(static_cast<std::size_t>(suppliedBatchCount));
      std::uint64_t nextCharacter = 0U;
      std::uint32_t maximumBatch = 0U;
      for (int argument = firstPair; argument < argc; argument += 2) {
        BatchPreview preview = preflightServiceBatch(
            argv[argument], sharedPlan, &rosterDigest);
        if (preview.binding.batch_ordinal != previews.size() ||
            preview.binding.campaign_batch_count != suppliedBatchCount ||
            preview.binding.character_start != nextCharacter) {
          throw std::runtime_error(
              "service batches are not one complete contiguous partition");
        }
        nextCharacter += preview.header.batch_count;
        maximumBatch = std::max(maximumBatch, preview.header.batch_count);
        previews.push_back(std::move(preview));
      }
      const auto observedRosterDigest = rosterDigest.finish();
      if (nextCharacter != sharedPlan.header.batch_count ||
          std::memcmp(observedRosterDigest.data(),
                      sharedPlan.commitment.character_roster_sha256,
                      observedRosterDigest.size()) != 0) {
        throw std::runtime_error(
            "service character roster commitment or coverage mismatch");
      }
      const auto partitionSha256 = batchPartitionDigest(previews);
      std::unique_ptr<MappedTimeTailControl> strictControl;
      std::unique_ptr<PackedSignStreamWriter> strictWriter;
      if (strictSignPacked) {
        strictControl = std::make_unique<MappedTimeTailControl>(
            strictSignControlPath, sharedPlan, previews, partitionSha256);
        strictWriter = std::make_unique<PackedSignStreamWriter>(
            sharedPlan, *strictControl, strictSignControlReceiptSha256,
            partitionSha256, strictSignCompactRosterSha256,
            strictSignPinsetSha256, strictSignSourceBindingSha256,
            suppliedBatchCount,
            strictSignPackedDevice
                ? sc::kPackedSignDeviceProductionMode
                : sc::kPackedSignHostProductionMode);
      }
      unsigned __int128 devicePackingBytes = 0U;
      if (strictSignPackedDevice) {
        using Wide = unsigned __int128;
        const Wide samples = strictControl->header().sample_count;
        const Wide items = static_cast<Wide>(maximumBatch) * samples;
        devicePackingBytes =
            samples * sizeof(sc::TimeTailControlItem) +
            (items + 3U) / 4U + sizeof(strict_pack::DevicePackSummary);
      }
      const std::uint64_t sharedSeedCapacity = chooseSharedSeedCapacity(
          sharedPlan, maximumBatch, suppliedBatchCount,
          requestedSharedSeedChunkRecords, devicePackingBytes);
      const bool sharedSeedsResident =
          sharedSeedCapacity == sharedPlan.header.frequency_count;
      ResidentBuffers buffers;
      std::unique_ptr<Radix2Plan> plan;
      if (sharedPlan.header.run_dft != 0U) {
        plan = std::make_unique<Radix2Plan>(
            static_cast<std::uint32_t>(sharedPlan.header.transform_length),
            maximumBatch);
      }
      std::unique_ptr<DeviceStrictSignPacker> devicePacker;
      if (strictSignPackedDevice) {
        devicePacker = std::make_unique<DeviceStrictSignPacker>(
            *strictControl, maximumBatch,
            sharedPlan.header.frequency_count);
      }
      bool residentSeedsUploaded = false;
      std::uint64_t allTerms = 0U;
      std::uint64_t allButterflies = 0U;
      std::uint64_t allElapsed = 0U;
      std::uint64_t allFrequencies = 0U;
      for (std::size_t ordinal = 0; ordinal < previews.size(); ++ordinal) {
        const int argument = firstPair + static_cast<int>(2U * ordinal);
        LoadedServiceBatch loaded = loadServiceBatch(argv[argument], sharedPlan);
        const auto& preview = previews[ordinal];
        if (std::memcmp(&loaded.binding, &preview.binding,
                        sizeof(loaded.binding)) != 0 ||
            loaded.digest != preview.digest ||
            loaded.input.characters.size() != preview.characterIds.size()) {
          throw std::runtime_error("character batch changed after preflight");
        }
        for (std::size_t index = 0; index < preview.characterIds.size(); ++index) {
          if (loaded.input.characters[index].character_id !=
              preview.characterIds[index]) {
            throw std::runtime_error(
                "character roster changed after service preflight");
          }
        }
        std::vector<sc::Disk> values;
        std::vector<std::uint32_t> statuses;
        const ServiceBatchExecution execution = executeServiceBatch(
            sharedPlan, loaded.input, &buffers, plan.get(), iterations,
            sharedSeedsResident, sharedSeedCapacity, &residentSeedsUploaded,
            strictSignPackedDevice ? nullptr : &values,
            strictSignPackedDevice ? nullptr : &statuses);
        const std::uint64_t elapsed = execution.elapsedNanoseconds;
        sc::FactoredServiceOutputBinding outputBinding{};
        std::memcpy(outputBinding.plan_sha256, loaded.binding.plan_sha256,
                    sizeof(outputBinding.plan_sha256));
        std::memcpy(outputBinding.batch_sha256, loaded.digest.data(),
                    loaded.digest.size());
        outputBinding.character_start = loaded.binding.character_start;
        outputBinding.campaign_character_count =
            loaded.binding.campaign_character_count;
        outputBinding.batch_ordinal = loaded.binding.batch_ordinal;
        outputBinding.campaign_batch_count =
            loaded.binding.campaign_batch_count;
        if (devicePacker != nullptr) {
          DevicePackedFrame packed = devicePacker->pack(
              loaded.input, execution.deviceValues, buffers.statuses,
              buffers.characters);
          strictWriter->writeDeviceFrame(
              loaded.input, outputBinding, loaded.digest, packed.payload,
              packed.summary, elapsed);
        } else if (strictWriter != nullptr) {
          strictWriter->writeFrame(loaded.input, outputBinding, loaded.digest,
                                   values, statuses, elapsed);
        } else {
          writeOutput(argv[argument + 1], loaded.input, values, statuses,
                      elapsed, &outputBinding, publishedFrequencyCount);
        }
        const std::uint64_t butterflies = loaded.input.header.run_dft
            ? static_cast<std::uint64_t>(loaded.input.header.batch_count) *
                  (loaded.input.header.transform_length / 2U) *
                  integerLog2(loaded.input.header.transform_length)
            : 0U;
        allTerms += loaded.input.finiteTerms;
        allButterflies += butterflies;
        allElapsed += elapsed;
        allFrequencies +=
            static_cast<std::uint64_t>(loaded.input.header.batch_count) *
            publishedFrequencyCount;
        std::fprintf(
            reportStream,
            "{\"algorithm\":\"platt-booker-smallq-factored-service-v3\","
            "\"batch_ordinal\":%llu,\"batch_count\":%u,"
            "\"frequencies\":%llu,\"finite_gaussian_terms\":%llu,"
            "\"radix2_butterflies\":%llu,\"elapsed_nanoseconds\":%llu,"
            "\"shared_seeds_resident\":%s,"
            "\"shared_seed_capacity\":%llu}\n",
            static_cast<unsigned long long>(ordinal),
            loaded.input.header.batch_count,
            static_cast<unsigned long long>(
                static_cast<std::uint64_t>(loaded.input.header.batch_count) *
                publishedFrequencyCount),
            static_cast<unsigned long long>(loaded.input.finiteTerms),
            static_cast<unsigned long long>(butterflies),
            static_cast<unsigned long long>(elapsed),
            sharedSeedsResident ? "true" : "false",
            static_cast<unsigned long long>(sharedSeedCapacity));
      }
      if (strictWriter != nullptr) {
        strictWriter->finish();
        const char* const packingLocation =
            strictSignPackedDevice ? "device" : "host";
        const char* const packingAlgorithm = strictSignPackedDevice
            ? "platt-booker-smallq-runner-strict-sign-pack-device-v1"
            : "platt-booker-smallq-runner-strict-sign-pack-v1";
        std::fprintf(
            reportStream,
            "{\"algorithm\":\"%s\","
            "\"classification\":\"transport_not_source_or_dft_replay\","
            "\"packing_location\":\"%s\",\"packing_mode\":%u,"
            "\"frames\":%llu,\"items\":%llu,"
            "\"ambiguous\":%llu,\"negative\":%llu,\"positive\":%llu,"
            "\"bytes\":%llu,\"stream_sha256\":\"%s\","
            "\"control_upload_nanoseconds\":%llu,"
            "\"device_classification_nanoseconds\":%llu,"
            "\"device_to_host_transfer_nanoseconds\":%llu,"
            "\"device_to_host_payload_bytes\":%llu,"
            "\"device_to_host_bounded_status_bytes\":%llu,"
            "\"full_disk_status_array_bytes_not_copied\":%llu,"
            "\"source_admission_enabled\":false,"
            "\"dft_arithmetic_containment_replayed\":false,"
            "\"zero_multiplicity_realized\":false,"
            "\"turing_closure_realized\":false,"
            "\"production_ready\":false}\n",
            packingAlgorithm, packingLocation,
            strictSignPackedDevice
                ? sc::kPackedSignDeviceProductionMode
                : sc::kPackedSignHostProductionMode,
            static_cast<unsigned long long>(strictWriter->frameCount()),
            static_cast<unsigned long long>(strictWriter->itemCount()),
            static_cast<unsigned long long>(strictWriter->ambiguousCount()),
            static_cast<unsigned long long>(strictWriter->negativeCount()),
            static_cast<unsigned long long>(strictWriter->positiveCount()),
            static_cast<unsigned long long>(strictWriter->bytesWritten()),
            sparkinterval::lowercase_hex(strictWriter->streamSha256()).c_str(),
            static_cast<unsigned long long>(
                devicePacker == nullptr
                    ? 0U
                    : devicePacker->controlUploadNanoseconds()),
            static_cast<unsigned long long>(
                devicePacker == nullptr
                    ? 0U
                    : devicePacker->classificationNanoseconds()),
            static_cast<unsigned long long>(
                devicePacker == nullptr
                    ? 0U
                    : devicePacker->transferNanoseconds()),
            static_cast<unsigned long long>(
                devicePacker == nullptr
                    ? 0U
                    : devicePacker->payloadBytesCopied()),
            static_cast<unsigned long long>(
                devicePacker == nullptr
                    ? 0U
                    : devicePacker->boundedStatusBytesCopied()),
            static_cast<unsigned long long>(
                devicePacker == nullptr
                    ? 0U
                    : devicePacker->fullArrayBytesAvoided()));
      }
      std::fprintf(
          reportStream,
          "{\"algorithm\":\"platt-booker-smallq-factored-service-v3-summary\","
          "\"plan_sha256\":\"%s\",\"batches\":%llu,"
          "\"characters\":%u,\"frequencies\":%llu,"
          "\"finite_gaussian_terms\":%llu,\"radix2_butterflies\":%llu,"
          "\"elapsed_nanoseconds\":%llu,\"shared_plan_artifact_copies\":1,"
          "\"shared_plan_device_resident\":%s,"
          "\"shared_plan_execution_read_passes\":%u,"
          "\"preflight_complete_before_execution\":true}\n",
          sparkinterval::lowercase_hex(sharedPlan.digest).c_str(),
          static_cast<unsigned long long>(previews.size()),
          sharedPlan.header.batch_count,
          static_cast<unsigned long long>(allFrequencies),
          static_cast<unsigned long long>(allTerms),
          static_cast<unsigned long long>(allButterflies),
          static_cast<unsigned long long>(allElapsed),
          sharedSeedsResident ? "true" : "false",
          sharedSeedsResident ? 1U : iterations);
      return 0;
    }
    if (strictSignPacked) {
      throw std::runtime_error(
          "--strict-sign-packed requires --factored-service");
    }
    if (requestedSharedSeedChunkRecords != 0U) {
      throw std::runtime_error(
          "--shared-seed-chunk-records requires --factored-service");
    }
    if (sourceSamplesOnly) {
      throw std::runtime_error(
          "--source-samples-only requires --factored-service");
    }
    ResidentBuffers buffers;
    std::unique_ptr<Radix2Plan> plan;
    std::uint64_t allTerms = 0U;
    std::uint64_t allButterflies = 0U;
    std::uint64_t allElapsed = 0U;
    std::uint64_t allFrequencies = 0U;
    std::uint64_t frames = 0U;
    std::uint32_t observedVersion = 0U;
    for (int argument = firstPair; argument < argc; argument += 2) {
      const LoadedInput input = loadInput(argv[argument]);
      if (observedVersion == 0U) {
        observedVersion = input.header.version;
      } else if (observedVersion != input.header.version) {
        throw std::runtime_error("one process may not mix v2 and v3 frames");
      }
      if (input.header.run_dft != 0U &&
          (!plan || plan->length() != input.header.transform_length ||
           plan->maximumBatch() < input.header.batch_count)) {
        plan = std::make_unique<Radix2Plan>(
            static_cast<std::uint32_t>(input.header.transform_length),
            input.header.batch_count);
      }
      std::vector<sc::Disk> values;
      std::vector<std::uint32_t> statuses;
      const std::uint64_t elapsed = execute(
          input, &buffers, plan.get(), iterations, &values, &statuses);
      writeOutput(argv[argument + 1], input, values, statuses, elapsed);
      const std::uint64_t butterflies = input.header.run_dft
          ? static_cast<std::uint64_t>(input.header.batch_count) *
                (input.header.transform_length / 2U) *
                integerLog2(input.header.transform_length)
          : 0U;
      allTerms += input.finiteTerms;
      allButterflies += butterflies;
      allElapsed += elapsed;
      allFrequencies += static_cast<std::uint64_t>(input.header.batch_count) *
                        input.header.frequency_count;
      ++frames;
      const char* algorithm = input.header.version == sc::kFactoredFormatVersion
          ? "platt-booker-smallq-factored-disk-dft-v3"
          : "platt-booker-smallq-certified-disk-dft-v2";
      std::printf(
          "{\"algorithm\":\"%s\","
          "\"frame\":%llu,\"batch_count\":%u,\"frequencies\":%llu,"
          "\"finite_gaussian_terms\":%llu,\"radix2_butterflies\":%llu,"
          "\"elapsed_nanoseconds\":%llu,\"device_transcendentals\":false,"
          "\"certified_disk_arithmetic\":true}\n",
          algorithm, static_cast<unsigned long long>(frames),
          input.header.batch_count,
          static_cast<unsigned long long>(
              static_cast<std::uint64_t>(input.header.batch_count) *
              input.header.frequency_count),
          static_cast<unsigned long long>(input.finiteTerms),
          static_cast<unsigned long long>(butterflies),
          static_cast<unsigned long long>(elapsed));
    }
    const char* summaryAlgorithm =
        observedVersion == sc::kFactoredFormatVersion
            ? "platt-booker-smallq-factored-disk-dft-v3-summary"
            : "platt-booker-smallq-certified-disk-dft-v2-summary";
    std::printf(
        "{\"algorithm\":\"%s\","
        "\"frames\":%llu,\"frequencies\":%llu,"
        "\"finite_gaussian_terms\":%llu,\"radix2_butterflies\":%llu,"
        "\"elapsed_nanoseconds\":%llu,\"persistent_process\":true,"
        "\"fft_plan_reused_for_equal_lengths\":true,"
        "\"trusted_transcendental_boundary\":\"mpfr-arb-seed-disks\"}\n",
        summaryAlgorithm, static_cast<unsigned long long>(frames),
        static_cast<unsigned long long>(allFrequencies),
        static_cast<unsigned long long>(allTerms),
        static_cast<unsigned long long>(allButterflies),
        static_cast<unsigned long long>(allElapsed));
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr,
                 "h100_tg_dirichlet_booker_smallq_certified: %s\n",
                 error.what());
    return 2;
  }
}

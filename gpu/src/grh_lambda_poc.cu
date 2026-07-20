// SparkInterval GRH POC: rigorous double-interval enclosures of Platt's
// completed Dirichlet function
//
//   Lambda_chi(t) = eps_chi (q/pi)^{it/2} Gamma((1/2 + a_chi + it)/2)
//                   exp(pi t / 4) L_chi(1/2 + it)
//
// for every character chi of one modulus q at a batch of ordinates t
// (arXiv:1305.3087, abstract and section 3).  L_chi is assembled from
// per-residue Dirichlet partial sums plus an Euler-Maclaurin Hurwitz tail:
//
//   q^{-s} zeta(s, a/q) = sum_{n<M} (nq+a)^{-s} + q^{-s} T_M(s, a/q),
//   L_chi(s) = sum_{(a,q)=1} chi(a) [ ... ],
//
// with T_M the standard Euler-Maclaurin tail through J Bernoulli terms and
// the periodized-Bernoulli remainder bound
//   |R_J| <= 4 |(s)_{2J+1}| (2pi)^{-(2J+1)} (M+alpha)^{-(sigma+2J)} / (sigma+2J).
//
// All arithmetic is directed-rounded IEEE binary64 interval arithmetic in
// the style of gpu/src/expression_batch_kernel.cu.  Transcendental device
// functions (log, exp, sin, cos, atan) are enclosed by widening the CUDA
// math library result by DOC_ULPS + 2 ulps; the CUDA Math API documents
// maximum errors of at most 2 ulps for these functions over the full
// double range.  That vendor error bound is a stated trust assumption of
// this numeric layer (Platt relied on crlibm's correct rounding in the
// same role); enclosures are additionally cross-checked against
// high-precision CPU recomputation by tools/run_grh_poc.py.
//
// This evaluator is a proof-of-concept for moderate ordinates (|t| up to a
// few thousand): interval blow-up of t*log(m) argument reduction makes the
// direct sum unusable near Platt's full heights, where his lattice/Taylor
// and FFT algorithms with high-precision seeds are required.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <cuda_runtime.h>

namespace {

constexpr char kInputMagic[8] = {'S', 'G', 'R', 'H', 'I', 'N', '0', '1'};
constexpr char kOutputMagic[8] = {'S', 'G', 'R', 'H', 'O', 'T', '0', '1'};

struct JobHeader {
  char magic[8];
  std::uint32_t q;
  std::uint32_t phi;
  std::uint32_t char_count;
  std::uint32_t t_count;
  std::uint32_t terms_m;
  std::uint32_t bern_j;
  std::uint32_t gamma_jg;
  std::uint32_t gamma_shift;
  double lnq_pi_lo;
  double lnq_pi_hi;
  double em_rconst_hi;
  double g_rconst_hi;
};

struct DeviceJob {
  std::uint32_t q;
  std::uint32_t phi;
  std::uint32_t char_count;
  std::uint32_t t_count;
  std::uint32_t terms_m;
  std::uint32_t bern_j;
  std::uint32_t gamma_jg;
  std::uint32_t gamma_shift;
  double lnq_pi_lo;
  double lnq_pi_hi;
  double em_rconst_hi;
  double g_rconst_hi;
};

// ---------------------------------------------------------------------------
// Directed-rounded interval arithmetic (lower/upper endpoints, no negation).
// ---------------------------------------------------------------------------

struct ival {
  double lo;
  double hi;
};

struct cval {
  ival re;
  ival im;
};

__device__ __forceinline__ ival ipoint(double x) { return {x, x}; }

__device__ __forceinline__ ival iadd(ival a, ival b) {
  return {__dadd_rd(a.lo, b.lo), __dadd_ru(a.hi, b.hi)};
}

__device__ __forceinline__ ival isub(ival a, ival b) {
  return {__dsub_rd(a.lo, b.hi), __dsub_ru(a.hi, b.lo)};
}

__device__ __forceinline__ ival ineg(ival a) { return {-a.hi, -a.lo}; }

__device__ __forceinline__ ival imul(ival a, ival b) {
  const double p1 = __dmul_rd(a.lo, b.lo);
  const double p2 = __dmul_rd(a.lo, b.hi);
  const double p3 = __dmul_rd(a.hi, b.lo);
  const double p4 = __dmul_rd(a.hi, b.hi);
  const double q1 = __dmul_ru(a.lo, b.lo);
  const double q2 = __dmul_ru(a.lo, b.hi);
  const double q3 = __dmul_ru(a.hi, b.lo);
  const double q4 = __dmul_ru(a.hi, b.hi);
  return {fmin(fmin(p1, p2), fmin(p3, p4)),
          fmax(fmax(q1, q2), fmax(q3, q4))};
}

// Division requiring 0 not in b; caller guarantees the precondition.
__device__ __forceinline__ ival idiv(ival a, ival b) {
  const double p1 = __ddiv_rd(a.lo, b.lo);
  const double p2 = __ddiv_rd(a.lo, b.hi);
  const double p3 = __ddiv_rd(a.hi, b.lo);
  const double p4 = __ddiv_rd(a.hi, b.hi);
  const double q1 = __ddiv_ru(a.lo, b.lo);
  const double q2 = __ddiv_ru(a.lo, b.hi);
  const double q3 = __ddiv_ru(a.hi, b.lo);
  const double q4 = __ddiv_ru(a.hi, b.hi);
  return {fmin(fmin(p1, p2), fmin(p3, p4)),
          fmax(fmax(q1, q2), fmax(q3, q4))};
}

// Square of an interval possibly containing zero.
__device__ __forceinline__ ival isqr(ival a) {
  if (a.lo >= 0.0) {
    return {__dmul_rd(a.lo, a.lo), __dmul_ru(a.hi, a.hi)};
  }
  if (a.hi <= 0.0) {
    return {__dmul_rd(a.hi, a.hi), __dmul_ru(a.lo, a.lo)};
  }
  const double m = fmax(-a.lo, a.hi);
  return {0.0, __dmul_ru(m, m)};
}

// Requires a.lo >= 0.  __dsqrt_rd/__dsqrt_ru are correctly rounded.
__device__ __forceinline__ ival isqrt(ival a) {
  return {__dsqrt_rd(a.lo), __dsqrt_ru(a.hi)};
}

// Widen the endpoints outward by `ulps` representable steps.
__device__ __forceinline__ double step_down(double x, int ulps) {
  for (int i = 0; i < ulps; ++i) {
    x = nextafter(x, -HUGE_VAL);
  }
  return x;
}

__device__ __forceinline__ double step_up(double x, int ulps) {
  for (int i = 0; i < ulps; ++i) {
    x = nextafter(x, HUGE_VAL);
  }
  return x;
}

// Monotone enclosures of CUDA math functions.  The CUDA Math API documents
// maximum errors of 1 ulp (log, exp) and 2 ulp (sin, cos, atan) over the
// full binary64 range; each endpoint is widened outward by two extra steps.
constexpr int kLogUlps = 3;
constexpr int kExpUlps = 3;
constexpr int kAtanUlps = 4;

// Requires a.lo > 0.
__device__ __forceinline__ ival ilog(ival a) {
  return {step_down(log(a.lo), kLogUlps), step_up(log(a.hi), kLogUlps)};
}

__device__ __forceinline__ ival iexp(ival a) {
  return {fmax(0.0, step_down(exp(a.lo), kExpUlps)),
          step_up(exp(a.hi), kExpUlps)};
}

__device__ __forceinline__ ival iatan(ival a) {
  return {step_down(atan(a.lo), kAtanUlps), step_up(atan(a.hi), kAtanUlps)};
}

// sin/cos on an interval via midpoint evaluation plus the Lipschitz bound
// |sin'| <= 1, |cos'| <= 1.  CUDA sin/cos use full Payne-Hanek argument
// reduction; 2 documented ulps of a result bounded by 1 are covered by the
// absolute slack 2^-50 together with the interval-radius term.
constexpr double kSinCosAbsErr = 8.8817841970012523e-16;  // 2^-50

__device__ __forceinline__ void isincos(ival a, ival* s, ival* c) {
  const double mid = 0.5 * (a.lo + a.hi);
  const double rad = fmax(__dsub_ru(a.hi, mid), __dsub_ru(mid, a.lo));
  double sm;
  double cm;
  sincos(mid, &sm, &cm);
  const double slack = __dadd_ru(rad, kSinCosAbsErr);
  s->lo = fmax(-1.0, __dsub_rd(sm, slack));
  s->hi = fmin(1.0, __dadd_ru(sm, slack));
  c->lo = fmax(-1.0, __dsub_rd(cm, slack));
  c->hi = fmin(1.0, __dadd_ru(cm, slack));
}

__device__ __forceinline__ ival iwiden(ival a, double err) {
  return {__dsub_rd(a.lo, err), __dadd_ru(a.hi, err)};
}

// Upper bound of |a| over the interval.
__device__ __forceinline__ double iabs_hi(ival a) {
  return fmax(-a.lo, a.hi);
}

// ---------------------------------------------------------------------------
// Complex rectangles.
// ---------------------------------------------------------------------------

__device__ __forceinline__ cval cadd(cval a, cval b) {
  return {iadd(a.re, b.re), iadd(a.im, b.im)};
}

__device__ __forceinline__ cval csub(cval a, cval b) {
  return {isub(a.re, b.re), isub(a.im, b.im)};
}

__device__ __forceinline__ cval cmul(cval a, cval b) {
  return {isub(imul(a.re, b.re), imul(a.im, b.im)),
          iadd(imul(a.re, b.im), imul(a.im, b.re))};
}

__device__ __forceinline__ cval cscale(cval a, ival r) {
  return {imul(a.re, r), imul(a.im, r)};
}

// |b|^2 with a positive lower bound is the caller's precondition.
__device__ __forceinline__ cval cdiv(cval a, cval b) {
  const ival norm = iadd(isqr(b.re), isqr(b.im));
  const cval conj_num = {iadd(imul(a.re, b.re), imul(a.im, b.im)),
                         isub(imul(a.im, b.re), imul(a.re, b.im))};
  return {idiv(conj_num.re, norm), idiv(conj_num.im, norm)};
}

__device__ __forceinline__ cval cinv(cval b) {
  const ival norm = iadd(isqr(b.re), isqr(b.im));
  return {idiv(b.re, norm), idiv(ineg(b.im), norm)};
}

// Principal logarithm of a rectangle with re > 0.
__device__ __forceinline__ cval clog(cval z) {
  const ival norm = iadd(isqr(z.re), isqr(z.im));
  const ival lre = imul(ilog(norm), ipoint(0.5));
  const ival lim = iatan(idiv(z.im, z.re));
  return {lre, lim};
}

__device__ __forceinline__ cval cexp(cval z) {
  const ival mag = iexp(z.re);
  ival s;
  ival c;
  isincos(z.im, &s, &c);
  return {imul(mag, c), imul(mag, s)};
}

__device__ __forceinline__ cval cwiden(cval z, double err) {
  return {iwiden(z.re, err), iwiden(z.im, err)};
}

// e^{-i theta} = (cos theta, -sin theta).
__device__ __forceinline__ cval cexp_neg_i(ival theta) {
  ival s;
  ival c;
  isincos(theta, &s, &c);
  return {c, ineg(s)};
}

// ---------------------------------------------------------------------------
// log Gamma via Stirling with a fixed integer shift.
//
// For w with Re w >= 6 and |arg w| < pi/2:
//   log Gamma(w) = (w - 1/2) Log w - w + (1/2) log(2 pi)
//                  + sum_{j=1..JG} B_{2j} / (2j (2j-1)) w^{1-2j} + R,
//   |R| <= |B_{2JG+2}| / ((2JG+2)(2JG+1)) sec(arg(w)/2)^{2JG+2} |w|^{-(2JG+1)}
// and sec(arg(w)/2)^2 <= 2 for |arg w| < pi/2, giving the host-computed
// g_rconst_hi = |B_{2JG+2}| / ((2JG+2)(2JG+1)) * 2^{JG+1}.
// ---------------------------------------------------------------------------

// log(2 pi)/2 rounded outward.
__device__ __forceinline__ ival half_log_two_pi() {
  return {0.9189385332046726, 0.9189385332046728};
}

__device__ cval clgamma_shifted(cval z, const DeviceJob job,
                                const ival* gbern) {
  cval w = z;
  cval log_accum = {ipoint(0.0), ipoint(0.0)};
  for (std::uint32_t k = 0; k < job.gamma_shift; ++k) {
    log_accum = cadd(log_accum, clog(w));
    w = cadd(w, {ipoint(1.0), ipoint(0.0)});
  }
  const cval logw = clog(w);
  const cval whalf = {isub(w.re, ipoint(0.5)), w.im};
  cval result = csub(cmul(whalf, logw), w);
  result = cadd(result, {half_log_two_pi(), ipoint(0.0)});
  const cval winv = cinv(w);
  const cval winv2 = cmul(winv, winv);
  cval wpow = winv;
  for (std::uint32_t j = 0; j < job.gamma_jg; ++j) {
    result = cadd(result, cscale(wpow, gbern[j]));
    wpow = cmul(wpow, winv2);
  }
  // Remainder bound: g_rconst_hi * |w|^{-(2 JG + 1)}.
  const double norm_lo = iadd(isqr(w.re), isqr(w.im)).lo;
  const double wabs_lo = __dsqrt_rd(norm_lo);
  double inv_hi = __ddiv_ru(1.0, wabs_lo);
  double pow_hi = inv_hi;
  for (std::uint32_t k = 0; k < 2 * job.gamma_jg; ++k) {
    pow_hi = __dmul_ru(pow_hi, inv_hi);
  }
  const double rem = __dmul_ru(job.g_rconst_hi, pow_hi);
  result = cwiden(result, rem);
  return csub(result, log_accum);
}

// ---------------------------------------------------------------------------
// Kernel 1: per-(t, residue) Dirichlet partial sum plus Euler-Maclaurin tail.
//
//   D_a(t) = sum_{n=0}^{M-1} (n q + a)^{-1/2 - i t}
//            + q^{-s} [ x^{1-s}/(s-1) + x^{-s}/2
//                       + sum_{j=1..J} (B_{2j}/(2j)!) (s)_{2j-1} x^{-s-2j+1}
//                       +- R_J ],   x = M + a/q.
// ---------------------------------------------------------------------------

__global__ void hurwitz_kernel(const DeviceJob job,
                               const std::uint32_t* residues,
                               const double* t_values,
                               const ival* bern,
                               cval* d_out,
                               std::uint8_t* status_out) {
  const std::size_t idx =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  const std::size_t total =
      static_cast<std::size_t>(job.t_count) * job.phi;
  if (idx >= total) {
    return;
  }
  const std::uint32_t res_idx = static_cast<std::uint32_t>(idx % job.phi);
  const std::uint32_t t_idx = static_cast<std::uint32_t>(idx / job.phi);
  const std::uint32_t a = residues[res_idx];
  const double t = t_values[t_idx];
  const ival t_iv = ipoint(t);

  cval acc = {ipoint(0.0), ipoint(0.0)};
  for (std::uint32_t n = 0; n < job.terms_m; ++n) {
    const double m = static_cast<double>(n) * job.q + a;
    const ival lm = ilog(ipoint(m));
    const ival arg = imul(lm, t_iv);
    const ival scale = idiv(ipoint(1.0), isqrt(ipoint(m)));
    const cval phase = cexp_neg_i(arg);
    acc = cadd(acc, cscale(phase, scale));
  }

  // x = M + a/q and the shared powers x^{-s}, x^{1-s}.
  const ival alpha = idiv(ipoint(static_cast<double>(a)),
                          ipoint(static_cast<double>(job.q)));
  const ival x = iadd(ipoint(static_cast<double>(job.terms_m)), alpha);
  const ival lx = ilog(x);
  const cval ephase = cexp_neg_i(imul(lx, t_iv));
  const ival sqx = isqrt(x);
  const cval x_pow_ms = cscale(ephase, idiv(ipoint(1.0), sqx));   // x^{-s}
  const cval x_pow_1ms = cscale(ephase, sqx);                      // x^{1-s}

  const cval s = {ipoint(0.5), t_iv};
  const cval s_minus_1 = {ipoint(-0.5), t_iv};
  cval tail = cdiv(x_pow_1ms, s_minus_1);
  tail = cadd(tail, cscale(x_pow_ms, ipoint(0.5)));

  // Bernoulli terms with running Pochhammer (s)_{2j-1} and power x^{-s-2j+1}.
  const ival xinv = idiv(ipoint(1.0), x);
  const ival xinv2 = imul(xinv, xinv);
  cval poch = s;                          // (s)_1
  cval xpow = cscale(x_pow_ms, xinv);     // x^{-s-1}
  double poch_abs_hi = 0.0;
  for (std::uint32_t j = 1; j <= job.bern_j; ++j) {
    tail = cadd(tail, cscale(cmul(poch, xpow), bern[j - 1]));
    if (j < job.bern_j) {
      const std::uint32_t k1 = 2 * j - 1;
      const cval f1 = {iadd(s.re, ipoint(static_cast<double>(k1))), s.im};
      const cval f2 = {iadd(s.re, ipoint(static_cast<double>(k1 + 1))), s.im};
      poch = cmul(cmul(poch, f1), f2);
      xpow = cscale(xpow, xinv2);
    } else {
      // Extend (s)_{2J-1} to |(s)_{2J+1}| upper bound for the remainder.
      const std::uint32_t k1 = 2 * j - 1;
      const ival n1 = iadd(isqr(iadd(s.re, ipoint(static_cast<double>(k1)))),
                           isqr(s.im));
      const ival n2 =
          iadd(isqr(iadd(s.re, ipoint(static_cast<double>(k1 + 1)))),
               isqr(s.im));
      const double pnorm =
          __dsqrt_ru(iadd(isqr(poch.re), isqr(poch.im)).hi);
      poch_abs_hi = __dmul_ru(
          pnorm, __dmul_ru(__dsqrt_ru(n1.hi), __dsqrt_ru(n2.hi)));
    }
  }

  // |R_J| <= em_rconst_hi * |(s)_{2J+1}| * x^{-(1/2 + 2J)} with
  // em_rconst_hi = 4 (2 pi)^{-(2J+1)} / (1/2 + 2J) from the host.
  double x_pow_hi = __ddiv_ru(1.0, __dsqrt_rd(x.lo));
  const double xinv_hi = __ddiv_ru(1.0, x.lo);
  for (std::uint32_t k = 0; k < 2 * job.bern_j; ++k) {
    x_pow_hi = __dmul_ru(x_pow_hi, xinv_hi);
  }
  const double rem =
      __dmul_ru(job.em_rconst_hi, __dmul_ru(poch_abs_hi, x_pow_hi));
  tail = cwiden(tail, rem);

  // q^{-s} = q^{-1/2} e^{-i t log q}.
  const ival lq = ilog(ipoint(static_cast<double>(job.q)));
  const cval q_pow_ms = cscale(cexp_neg_i(imul(lq, t_iv)),
                               idiv(ipoint(1.0), isqrt(ipoint(
                                   static_cast<double>(job.q)))));
  const cval result = cadd(acc, cmul(q_pow_ms, tail));

  const bool finite = isfinite(result.re.lo) && isfinite(result.re.hi) &&
                      isfinite(result.im.lo) && isfinite(result.im.hi);
  d_out[idx] = result;
  status_out[idx] = finite ? 0 : 1;
}

// ---------------------------------------------------------------------------
// Kernel 2: character combination and completed-function factor.
//
//   L_chi(1/2 + i t) = sum_j chi(a_j) D_{a_j}(t)
//   Lambda_chi(t) = eps_chi exp(logGamma(z) + pi t / 4 + i (t/2) log(q/pi))
//                   L_chi(1/2 + i t),   z = (1/2 + a_chi + i t)/2.
// ---------------------------------------------------------------------------

// pi rounded outward.
__device__ __forceinline__ ival pi_interval() {
  return {3.1415926535897931, 3.1415926535897936};
}

__global__ void lambda_kernel(const DeviceJob job,
                              const cval* chi_table,
                              const cval* eps_table,
                              const std::uint8_t* parity,
                              const double* t_values,
                              const ival* gbern,
                              const cval* d_in,
                              const std::uint8_t* d_status,
                              cval* lambda_out,
                              std::uint8_t* status_out) {
  const std::size_t idx =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  const std::size_t total =
      static_cast<std::size_t>(job.t_count) * job.char_count;
  if (idx >= total) {
    return;
  }
  const std::uint32_t char_idx =
      static_cast<std::uint32_t>(idx % job.char_count);
  const std::uint32_t t_idx = static_cast<std::uint32_t>(idx / job.char_count);
  const double t = t_values[t_idx];
  const ival t_iv = ipoint(t);

  cval l_value = {ipoint(0.0), ipoint(0.0)};
  std::uint8_t status = 0;
  const cval* chi_row =
      chi_table + static_cast<std::size_t>(char_idx) * job.phi;
  const cval* d_row = d_in + static_cast<std::size_t>(t_idx) * job.phi;
  const std::uint8_t* d_status_row =
      d_status + static_cast<std::size_t>(t_idx) * job.phi;
  for (std::uint32_t j = 0; j < job.phi; ++j) {
    status |= d_status_row[j];
    l_value = cadd(l_value, cmul(chi_row[j], d_row[j]));
  }

  const double a_par = static_cast<double>(parity[char_idx]);
  const cval z = {ipoint(0.25 + 0.5 * a_par), imul(t_iv, ipoint(0.5))};
  const cval lgamma_z = clgamma_shifted(z, job, gbern);

  const ival pi_iv = pi_interval();
  const ival exp_re = imul(imul(pi_iv, t_iv), ipoint(0.25));
  const ival lnq_pi = {job.lnq_pi_lo, job.lnq_pi_hi};
  const ival exp_im = imul(imul(t_iv, ipoint(0.5)), lnq_pi);
  const cval exponent = cadd(lgamma_z, {exp_re, exp_im});
  const cval phase = cexp(exponent);
  const cval lambda = cmul(cmul(eps_table[char_idx], phase), l_value);

  const bool finite = isfinite(lambda.re.lo) && isfinite(lambda.re.hi) &&
                      isfinite(lambda.im.lo) && isfinite(lambda.im.hi);
  if (!finite) {
    status |= 2;
  }
  lambda_out[idx] = lambda;
  status_out[idx] = status;
}

// ---------------------------------------------------------------------------
// Host driver.
// ---------------------------------------------------------------------------

#define CUDA_CHECK(call)                                                   \
  do {                                                                     \
    const cudaError_t cuda_status = (call);                                \
    if (cuda_status != cudaSuccess) {                                      \
      std::fprintf(stderr, "cuda error %s at %s:%d\n",                     \
                   cudaGetErrorString(cuda_status), __FILE__, __LINE__);   \
      std::exit(2);                                                        \
    }                                                                      \
  } while (0)

template <typename T>
std::vector<T> read_array(std::FILE* file, std::size_t count,
                          const char* what) {
  std::vector<T> data(count);
  if (std::fread(data.data(), sizeof(T), count, file) != count) {
    std::fprintf(stderr, "short read: %s\n", what);
    std::exit(1);
  }
  return data;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3) {
    std::fprintf(stderr,
                 "usage: %s <input.bin> <output.bin> [device]\n", argv[0]);
    return 1;
  }
  const int device = argc > 3 ? std::atoi(argv[3]) : 0;
  CUDA_CHECK(cudaSetDevice(device));
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
  if (properties.major != 9 || properties.minor != 0 ||
      std::strstr(properties.name, "H100") == nullptr) {
    std::fprintf(
        stderr,
        "strict H100 GRH runner requires device name containing H100 and "
        "compute capability 9.0; found %s (%d.%d)\n",
        properties.name, properties.major, properties.minor);
    return 4;
  }
#endif

  std::FILE* in = std::fopen(argv[1], "rb");
  if (in == nullptr) {
    std::fprintf(stderr, "cannot open %s\n", argv[1]);
    return 1;
  }
  JobHeader header{};
  if (std::fread(&header, sizeof(header), 1, in) != 1 ||
      std::memcmp(header.magic, kInputMagic, 8) != 0) {
    std::fprintf(stderr, "bad input header\n");
    return 1;
  }
  const std::size_t phi = header.phi;
  const std::size_t char_count = header.char_count;
  const std::size_t t_count = header.t_count;

  const auto residues =
      read_array<std::uint32_t>(in, phi, "residues");
  const auto parity =
      read_array<std::uint8_t>(in, char_count, "parity");
  const auto bern =
      read_array<double>(in, 2 * header.bern_j, "bernoulli");
  const auto gbern =
      read_array<double>(in, 2 * header.gamma_jg, "gamma bernoulli");
  const auto chi =
      read_array<double>(in, 4 * char_count * phi, "character table");
  const auto eps = read_array<double>(in, 4 * char_count, "epsilon");
  const auto t_values = read_array<double>(in, t_count, "ordinates");
  std::fclose(in);

  DeviceJob job{};
  job.q = header.q;
  job.phi = header.phi;
  job.char_count = header.char_count;
  job.t_count = header.t_count;
  job.terms_m = header.terms_m;
  job.bern_j = header.bern_j;
  job.gamma_jg = header.gamma_jg;
  job.gamma_shift = header.gamma_shift;
  job.lnq_pi_lo = header.lnq_pi_lo;
  job.lnq_pi_hi = header.lnq_pi_hi;
  job.em_rconst_hi = header.em_rconst_hi;
  job.g_rconst_hi = header.g_rconst_hi;

  std::uint32_t* d_residues = nullptr;
  double* d_t = nullptr;
  ival* d_bern = nullptr;
  ival* d_gbern = nullptr;
  cval* d_chi = nullptr;
  cval* d_eps = nullptr;
  std::uint8_t* d_parity = nullptr;
  cval* d_hurwitz = nullptr;
  std::uint8_t* d_hstatus = nullptr;
  cval* d_lambda = nullptr;
  std::uint8_t* d_lstatus = nullptr;

  CUDA_CHECK(cudaMalloc(&d_residues, phi * sizeof(std::uint32_t)));
  CUDA_CHECK(cudaMalloc(&d_t, t_count * sizeof(double)));
  CUDA_CHECK(cudaMalloc(&d_bern, header.bern_j * sizeof(ival)));
  CUDA_CHECK(cudaMalloc(&d_gbern, header.gamma_jg * sizeof(ival)));
  CUDA_CHECK(cudaMalloc(&d_chi, char_count * phi * sizeof(cval)));
  CUDA_CHECK(cudaMalloc(&d_eps, char_count * sizeof(cval)));
  CUDA_CHECK(cudaMalloc(&d_parity, char_count * sizeof(std::uint8_t)));
  CUDA_CHECK(cudaMalloc(&d_hurwitz, t_count * phi * sizeof(cval)));
  CUDA_CHECK(cudaMalloc(&d_hstatus, t_count * phi * sizeof(std::uint8_t)));
  CUDA_CHECK(cudaMalloc(&d_lambda, t_count * char_count * sizeof(cval)));
  CUDA_CHECK(
      cudaMalloc(&d_lstatus, t_count * char_count * sizeof(std::uint8_t)));

  CUDA_CHECK(cudaMemcpy(d_residues, residues.data(),
                        phi * sizeof(std::uint32_t), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_t, t_values.data(), t_count * sizeof(double),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_bern, bern.data(), header.bern_j * sizeof(ival),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_gbern, gbern.data(), header.gamma_jg * sizeof(ival),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_chi, chi.data(), char_count * phi * sizeof(cval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_eps, eps.data(), char_count * sizeof(cval),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_parity, parity.data(),
                        char_count * sizeof(std::uint8_t),
                        cudaMemcpyHostToDevice));

  cudaEvent_t ev_start;
  cudaEvent_t ev_mid;
  cudaEvent_t ev_end;
  CUDA_CHECK(cudaEventCreate(&ev_start));
  CUDA_CHECK(cudaEventCreate(&ev_mid));
  CUDA_CHECK(cudaEventCreate(&ev_end));

  constexpr unsigned int kThreads = 128;
  const std::size_t hurwitz_total = t_count * phi;
  const std::size_t lambda_total = t_count * char_count;
  const unsigned int hurwitz_blocks = static_cast<unsigned int>(
      (hurwitz_total + kThreads - 1) / kThreads);
  const unsigned int lambda_blocks = static_cast<unsigned int>(
      (lambda_total + kThreads - 1) / kThreads);

  CUDA_CHECK(cudaEventRecord(ev_start));
  hurwitz_kernel<<<hurwitz_blocks, kThreads>>>(
      job, d_residues, d_t, d_bern, d_hurwitz, d_hstatus);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaEventRecord(ev_mid));
  lambda_kernel<<<lambda_blocks, kThreads>>>(
      job, d_chi, d_eps, d_parity, d_t, d_gbern, d_hurwitz, d_hstatus,
      d_lambda, d_lstatus);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaEventRecord(ev_end));
  CUDA_CHECK(cudaDeviceSynchronize());

  float hurwitz_ms = 0.0f;
  float lambda_ms = 0.0f;
  CUDA_CHECK(cudaEventElapsedTime(&hurwitz_ms, ev_start, ev_mid));
  CUDA_CHECK(cudaEventElapsedTime(&lambda_ms, ev_mid, ev_end));

  std::vector<double> lambda_host(4 * lambda_total);
  std::vector<std::uint8_t> status_host(lambda_total);
  CUDA_CHECK(cudaMemcpy(lambda_host.data(), d_lambda,
                        lambda_total * sizeof(cval), cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(status_host.data(), d_lstatus,
                        lambda_total * sizeof(std::uint8_t),
                        cudaMemcpyDeviceToHost));

  std::FILE* out = std::fopen(argv[2], "wb");
  if (out == nullptr) {
    std::fprintf(stderr, "cannot open %s\n", argv[2]);
    return 1;
  }
  std::uint32_t summary = 0;
  for (const std::uint8_t s : status_host) {
    summary |= s;
  }
  std::fwrite(kOutputMagic, 1, 8, out);
  const std::uint32_t out_header[4] = {header.char_count, header.t_count,
                                       summary, 0};
  std::fwrite(out_header, sizeof(std::uint32_t), 4, out);
  std::fwrite(lambda_host.data(), sizeof(double), lambda_host.size(), out);
  std::fwrite(status_host.data(), 1, status_host.size(), out);
  std::fclose(out);

  cudaDeviceProp props{};
  CUDA_CHECK(cudaGetDeviceProperties(&props, device));
  const double term_evals =
      static_cast<double>(hurwitz_total) * job.terms_m;
  std::printf(
      "{\"device\": \"%s\", \"q\": %u, \"phi\": %u, \"characters\": %u, "
      "\"t_count\": %u, \"terms_m\": %u, \"hurwitz_ms\": %.3f, "
      "\"lambda_ms\": %.3f, \"term_evals\": %.0f, "
      "\"terms_per_second\": %.3e, \"status_summary\": %u}\n",
      props.name, job.q, job.phi, job.char_count, job.t_count, job.terms_m,
      hurwitz_ms, lambda_ms, term_evals,
      term_evals / (hurwitz_ms * 1e-3), summary);
  return 0;
}

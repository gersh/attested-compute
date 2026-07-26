// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Two-limb-center complex-disk diagnostic for the Platt PT21 windowed
// transform.  It consumes the same fixed source packet as the binary64 disk
// producer, but keeps each Cartesian center as an unevaluated sum of two
// binary64 values.  Error-free TwoSum/FMA decompositions supply a conservative
// local residual disk.  This is a precision/width experiment, not yet a
// proved CUDA-to-Lean refinement.

#include <cstdio>
#include <memory>

#include "sparkinterval/tg_platt_dd_transform.hpp"

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1 && \
    (!defined(SPARKINTERVAL_CUDA_FTZ_DISABLED) || \
     SPARKINTERVAL_CUDA_FTZ_DISABLED != 1)
#error "sloppy-root whole-transform qualification requires --ftz=false"
#endif

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1 && \
    (!defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) || \
     SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION != 1)
#error "tile9 sloppy-root qualification requires the sloppy-root guard"
#endif

#define SPARKINTERVAL_PLATT_DISK_NO_MAIN
#include "h100_tg_platt_windowed_disk_semantic.cu"
#undef SPARKINTERVAL_PLATT_DISK_NO_MAIN

namespace {

struct DD {
  double hi;
  double lo;
};

struct DDDisk {
  DD real;
  DD imaginary;
  double radius;
};

struct DDRealDisk {
  DD center;
  double radius;
};

struct DDDiskOptions : DiskOptions {
  bool discard_source_packet_radii_for_diagnostic = false;
  bool require_source_region_unambiguous = false;
  std::string export_required_sign_packet;
};

DDDiskOptions parse_dd_disk_options(int argc, char** argv) {
  std::vector<char*> base_argv;
  base_argv.reserve(static_cast<std::size_t>(argc));
  base_argv.push_back(argv[0]);
  DDDiskOptions result;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    if (argument == "--discard-source-packet-radii-for-diagnostic") {
      result.discard_source_packet_radii_for_diagnostic = true;
    } else if (argument == "--require-source-region-unambiguous") {
      result.require_source_region_unambiguous = true;
    } else if (argument.rfind("--export-required-sign-packet=", 0) == 0) {
      result.export_required_sign_packet =
          argument.substr(std::string("--export-required-sign-packet=").size());
      if (result.export_required_sign_packet.empty()) {
        throw std::runtime_error("required-sign packet path is empty");
      }
    } else {
      base_argv.push_back(argv[index]);
    }
  }
  static_cast<DiskOptions&>(result) =
      parse_disk_options(static_cast<int>(base_argv.size()), base_argv.data());
  if (result.discard_source_packet_radii_for_diagnostic &&
      result.source_packet.empty()) {
    throw std::runtime_error(
        "--discard-source-packet-radii-for-diagnostic requires --source-packet");
  }
  if (!result.export_required_sign_packet.empty() &&
      result.source_packet.empty()) {
    throw std::runtime_error(
        "--export-required-sign-packet requires --source-packet");
  }
  return result;
}

struct TwoSumResult {
  double sum;
  double residual;
};

struct DDResult {
  DD value;
  double error;
};

static_assert(sizeof(DD) == 16U);
static_assert(sizeof(DDDisk) == 40U);
static_assert(sizeof(DDRealDisk) == 24U);
static_assert(sizeof(DDDisk) == sizeof(pw::ComplexDisk106));

struct LoadedSourcePacket106 {
  std::vector<DDDisk> gamma0;
  std::vector<DDDisk> skn_rows;
  std::string sha256;
  std::uint32_t source_terms = 0U;
  std::uint64_t bytes = 0U;
  std::uint64_t window_center = 0U;
  bool complete_terms = false;
};

bool source_packet_is_106(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open PT21 source packet");
  pw::SourcePacketHeader header{};
  input.read(reinterpret_cast<char*>(&header), sizeof(header));
  if (!input) throw std::runtime_error("PT21 source packet header is truncated");
  return header.magic == pw::kSourcePacket106Magic;
}

LoadedSourcePacket106 load_source_packet106(const std::string& path) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "PT21 two-limb packet import requires a little-endian host");
  }
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open PT21 two-limb packet");
  const std::streampos end = input.tellg();
  if (end < 0 || static_cast<std::uint64_t>(end) >
                     std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("PT21 two-limb packet has invalid size");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  if (!input || input.peek() != std::ifstream::traits_type::eof() ||
      bytes.size() < sizeof(pw::SourcePacketHeader)) {
    throw std::runtime_error("cannot read complete PT21 two-limb packet");
  }
  pw::SourcePacketHeader header{};
  std::memcpy(&header, bytes.data(), sizeof(header));
  const std::uint64_t expected_skn =
      static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
  const std::uint64_t expected_payload =
      (pw::kBucketCount + expected_skn) * sizeof(DDDisk);
  if (header.magic != pw::kSourcePacket106Magic ||
      header.version != pw::kSourcePacket106Version ||
      header.header_bytes != sizeof(header) ||
      header.endian_tag != pw::kSourcePacketEndianTag ||
      header.interval_encoding != pw::kSourcePacket106Encoding ||
      header.bucket_count != pw::kBucketCount ||
      header.taylor_terms != pw::kTaylorTerms ||
      header.source_terms == 0U || header.source_terms > pw::kSourceTerms ||
      header.reserved_zero != 0U ||
      header.window_center != pw::kSourceLower + pw::kWindowStep / 2U ||
      header.gamma_count != pw::kBucketCount ||
      header.skn_count != expected_skn ||
      header.payload_bytes != expected_payload ||
      bytes.size() != sizeof(header) + expected_payload ||
      std::memcmp(header.upstream_commit.data(), pw::kUpstreamCommit,
                  header.upstream_commit.size()) != 0) {
    throw std::runtime_error(
        "PT21 two-limb packet header is not the fixed v2 schema");
  }
  LoadedSourcePacket106 result;
  result.gamma0.resize(pw::kBucketCount);
  result.skn_rows.resize(expected_skn);
  std::size_t offset = sizeof(header);
  const std::size_t gamma_bytes = result.gamma0.size() * sizeof(DDDisk);
  std::memcpy(result.gamma0.data(), bytes.data() + offset, gamma_bytes);
  offset += gamma_bytes;
  const std::size_t skn_bytes = result.skn_rows.size() * sizeof(DDDisk);
  std::memcpy(result.skn_rows.data(), bytes.data() + offset, skn_bytes);
  if (fnv1a_bytes(result.gamma0.data(), gamma_bytes) !=
          header.gamma_fnv1a64 ||
      fnv1a_bytes(result.skn_rows.data(), skn_bytes) != header.skn_fnv1a64) {
    throw std::runtime_error("PT21 two-limb packet checksum mismatch");
  }
  auto valid = [](DDDisk value) {
    return std::isfinite(value.real.hi) && std::isfinite(value.real.lo) &&
           std::isfinite(value.imaginary.hi) &&
           std::isfinite(value.imaginary.lo) &&
           std::isfinite(value.radius) && value.radius >= 0.0;
  };
  for (const DDDisk value : result.gamma0) {
    if (!valid(value)) {
      throw std::runtime_error("PT21 two-limb Gamma cell is invalid");
    }
  }
  for (const DDDisk value : result.skn_rows) {
    if (!valid(value)) {
      throw std::runtime_error("PT21 two-limb Taylor cell is invalid");
    }
  }
  result.sha256 = sparkinterval::sha256_hex(bytes.data(), bytes.size());
  result.source_terms = header.source_terms;
  result.bytes = bytes.size();
  result.window_center = header.window_center;
  result.complete_terms = header.source_terms == pw::kSourceTerms;
  return result;
}

// One least positive subnormal is charged for every error-free transform.
// Away from underflow TwoSum and FMA TwoProd are exact decompositions; this
// floor keeps the experimental enclosure fail-closed at the underflow edge.
constexpr double kDDFloor = 0x0.0000000000001p-1022;

__device__ __forceinline__ TwoSumResult dd_two_sum(double a, double b) {
  const double sum = __dadd_rn(a, b);
  const double virtual_b = __dsub_rn(sum, a);
  const double residual = __dadd_rn(
      __dsub_rn(a, __dsub_rn(sum, virtual_b)),
      __dsub_rn(b, virtual_b));
  return {sum, residual};
}

__device__ __forceinline__ TwoSumResult dd_two_product(double a, double b) {
  const double product = __dmul_rn(a, b);
  return {product, fma(a, b, -product)};
}

__device__ __forceinline__ double dd_error_add(double bound, double value) {
  return __dadd_ru(bound, fabs(value));
}

// Compress four exact binary64 summands into two limbs.  The returned error
// bounds the exact signed residual discarded by the compression.
__device__ __forceinline__ DDResult dd_add_center(DD a, DD b) {
  const TwoSumResult high = dd_two_sum(a.hi, b.hi);
  double low = 0.0;
  double error = kDDFloor;
  const double terms[] = {high.residual, a.lo, b.lo};
#pragma unroll
  for (int index = 0; index < 3; ++index) {
    const TwoSumResult next = dd_two_sum(low, terms[index]);
    low = next.sum;
    error = dd_error_add(error, next.residual);
    error = __dadd_ru(error, kDDFloor);
  }
  const TwoSumResult normalized = dd_two_sum(high.sum, low);
  error = __dadd_ru(error, kDDFloor);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ DD dd_negate_center(DD value) {
  return {-value.hi, -value.lo};
}

// Expand all four limb products with FMA, then compress their eight exact
// binary64 summands.  Rounding residuals from the low accumulator are carried
// into `error`, rather than silently dropped as in an ordinary double-double
// implementation.
__device__ __forceinline__ DDResult dd_mul_center(DD a, DD b) {
  const TwoSumResult products[] = {
      dd_two_product(a.hi, b.hi), dd_two_product(a.hi, b.lo),
      dd_two_product(a.lo, b.hi), dd_two_product(a.lo, b.lo)};
  double low = 0.0;
  double error = __dmul_ru(4.0, kDDFloor);
  const double terms[] = {
      products[0].residual,
      products[1].sum,
      products[1].residual,
      products[2].sum,
      products[2].residual,
      products[3].sum,
      products[3].residual,
  };
#pragma unroll
  for (int index = 0; index < 7; ++index) {
    const TwoSumResult next = dd_two_sum(low, terms[index]);
    low = next.sum;
    error = dd_error_add(error, next.residual);
    error = __dadd_ru(error, kDDFloor);
  }
  const TwoSumResult normalized = dd_two_sum(products[0].sum, low);
  error = __dadd_ru(error, kDDFloor);
  return {{normalized.sum, normalized.residual}, error};
}

__device__ __forceinline__ double dd_abs_upper(DD value) {
  return __dadd_ru(fabs(value.hi), fabs(value.lo));
}

__device__ __forceinline__ double dd_norm_upper(DD re, DD im) {
  return disk_norm_upper(dd_abs_upper(re), dd_abs_upper(im));
}

__device__ __forceinline__ double dd_l1_norm_upper(DD re, DD im) {
  return __dadd_ru(dd_abs_upper(re), dd_abs_upper(im));
}

__device__ __forceinline__ DDDisk dd_disk_add(DDDisk x, DDDisk y) {
  const DDResult re = dd_add_center(x.real, y.real);
  const DDResult im = dd_add_center(x.imaginary, y.imaginary);
  const double local_error = disk_norm_upper(re.error, im.error);
  return {re.value, im.value,
          __dadd_ru(__dadd_ru(x.radius, y.radius), local_error)};
}

__device__ __forceinline__ DDDisk dd_disk_negate(DDDisk x) {
  return {dd_negate_center(x.real), dd_negate_center(x.imaginary), x.radius};
}

__device__ __forceinline__ DDDisk dd_disk_sub(DDDisk x, DDDisk y) {
  return dd_disk_add(x, dd_disk_negate(y));
}

// The FFT hot path uses the elementary |x + i y| <= |x| + |y| bound
// for newly introduced centre-compression residuals.  It is looser than the
// Euclidean helper above but avoids a directed divide and square root at
// every add/subtract while remaining a direct norm certificate.
__device__ __forceinline__ DDDisk dd_disk_add_l1(DDDisk x, DDDisk y) {
  const DDResult re = dd_add_center(x.real, y.real);
  const DDResult im = dd_add_center(x.imaginary, y.imaginary);
  const double local_error = __dadd_ru(re.error, im.error);
  return {re.value, im.value,
          __dadd_ru(__dadd_ru(x.radius, y.radius), local_error)};
}

__device__ __forceinline__ DDDisk dd_disk_sub_l1(DDDisk x, DDDisk y) {
  return dd_disk_add_l1(x, dd_disk_negate(y));
}

__device__ __forceinline__ DDDisk dd_disk_conjugate(DDDisk x) {
  return {x.real, dd_negate_center(x.imaginary), x.radius};
}

__device__ __forceinline__ DDDisk dd_disk_times_i(DDDisk x) {
  return {dd_negate_center(x.imaginary), x.real, x.radius};
}

__device__ __forceinline__ DDDisk dd_disk_mul(DDDisk x, DDDisk y) {
  const DDResult rr = dd_mul_center(x.real, y.real);
  const DDResult ii = dd_mul_center(x.imaginary, y.imaginary);
  const DDResult ri = dd_mul_center(x.real, y.imaginary);
  const DDResult ir = dd_mul_center(x.imaginary, y.real);
  const DDResult re = dd_add_center(rr.value, dd_negate_center(ii.value));
  const DDResult im = dd_add_center(ri.value, ir.value);
  const double re_error = __dadd_ru(__dadd_ru(rr.error, ii.error), re.error);
  const double im_error = __dadd_ru(__dadd_ru(ri.error, ir.error), im.error);
  const double local_error = disk_norm_upper(re_error, im_error);
  const double nx = dd_norm_upper(x.real, x.imaginary);
  const double ny = dd_norm_upper(y.real, y.imaginary);
  double radius = __dadd_ru(local_error, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

// FFT roots are immutable.  Their directed centre norms are computed once
// when the workspace is initialized and reused at every butterfly.  The
// remaining two local norm terms use the elementary L1 upper bound, which is
// a looser but division/square-root-free certificate.
__device__ __forceinline__ DDDisk dd_disk_mul_known_y_norm(
    DDDisk x, DDDisk y, double y_center_norm_upper) {
  const DDResult rr = dd_mul_center(x.real, y.real);
  const DDResult ii = dd_mul_center(x.imaginary, y.imaginary);
  const DDResult ri = dd_mul_center(x.real, y.imaginary);
  const DDResult ir = dd_mul_center(x.imaginary, y.real);
  const DDResult re = dd_add_center(rr.value, dd_negate_center(ii.value));
  const DDResult im = dd_add_center(ri.value, ir.value);
  const double re_error = __dadd_ru(__dadd_ru(rr.error, ii.error), re.error);
  const double im_error = __dadd_ru(__dadd_ru(ri.error, ir.error), im.error);
  const double local_error = __dadd_ru(re_error, im_error);
  const double nx = dd_l1_norm_upper(x.real, x.imaginary);
  double radius = __dadd_ru(local_error, __dmul_ru(nx, y.radius));
  radius =
      __dadd_ru(radius, __dmul_ru(y_center_norm_upper, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re.value, im.value, radius};
}

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1
// These helpers are intentionally compiled only into the isolated
// qualification library.  They are the settled formulas exercised by
// tg_platt_dd_sloppy_mul_qualification.cu.  No normalized/nonoverlapping-limb
// or normal-result premise is used: every discarded RN operation receives an
// absolute directed-rounding charge and every underflow edge receives eta.
constexpr double kQualificationRnRelativeError =
    0x1.0000000000001p-53;
constexpr double kQualificationFastMulFloors = 6.0 * kDDFloor;
constexpr double kQualificationFastAddFloors = 12.0 * kDDFloor;

enum DDQualificationStatus : std::uint32_t {
  kDDQualificationOk = 0U,
  kDDQualificationInvalidInput = 1U << 0U,
  kDDQualificationNonfiniteIntermediate = 1U << 1U,
  kDDQualificationInvalidOutput = 1U << 2U,
};

struct DDQualificationCenterResult {
  DD value;
  double error;
  std::uint32_t status;
};

struct DDQualificationDiskResult {
  DDDisk value;
  std::uint32_t status;
};

__device__ __forceinline__ std::uint32_t
dd_qualification_finite_status(double value) {
  return isfinite(value) ? kDDQualificationOk
                         : kDDQualificationNonfiniteIntermediate;
}

__device__ __forceinline__ std::uint32_t
dd_qualification_finite_status(TwoSumResult value) {
  return dd_qualification_finite_status(value.sum) |
         dd_qualification_finite_status(value.residual);
}

__device__ __forceinline__ double dd_qualification_rn_error(double value) {
  return __dadd_ru(
      __dmul_ru(fabs(value), kQualificationRnRelativeError), kDDFloor);
}

__device__ __noinline__ DDQualificationCenterResult
dd_qualification_fast_add_center(DD a, DD b) {
  const TwoSumResult high = dd_two_sum(a.hi, b.hi);
  std::uint32_t status = dd_qualification_finite_status(high);
  const double low_parts = __dadd_rn(a.lo, b.lo);
  status |= dd_qualification_finite_status(low_parts);
  const double low = __dadd_rn(high.residual, low_parts);
  status |= dd_qualification_finite_status(low);
  const TwoSumResult normalized = dd_two_sum(high.sum, low);
  status |= dd_qualification_finite_status(normalized);
  double error = dd_qualification_rn_error(low_parts);
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, dd_qualification_rn_error(low));
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, kQualificationFastAddFloors);
  status |= dd_qualification_finite_status(error);
  return {{normalized.sum, normalized.residual}, error, status};
}

__device__ __noinline__ DDQualificationCenterResult
dd_qualification_fast_mul_center(DD a, DD b) {
  const TwoSumResult leading = dd_two_product(a.hi, b.hi);
  std::uint32_t status = dd_qualification_finite_status(leading);
  const double cross0 = __dmul_rn(a.hi, b.lo);
  status |= dd_qualification_finite_status(cross0);
  const double cross1 = __dmul_rn(a.lo, b.hi);
  status |= dd_qualification_finite_status(cross1);
  const double cross = __dadd_rn(cross0, cross1);
  status |= dd_qualification_finite_status(cross);
  const double low = __dadd_rn(leading.residual, cross);
  status |= dd_qualification_finite_status(low);
  const TwoSumResult normalized = dd_two_sum(leading.sum, low);
  status |= dd_qualification_finite_status(normalized);
  double error = kDDFloor;
  error = __dadd_ru(error, dd_qualification_rn_error(cross0));
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, dd_qualification_rn_error(cross1));
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, dd_qualification_rn_error(cross));
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, dd_qualification_rn_error(low));
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, __dmul_ru(fabs(a.lo), fabs(b.lo)));
  status |= dd_qualification_finite_status(error);
  error = __dadd_ru(error, kQualificationFastMulFloors);
  status |= dd_qualification_finite_status(error);
  return {{normalized.sum, normalized.residual}, error, status};
}

__device__ __forceinline__ bool dd_qualification_finite_center(DD value) {
  return isfinite(value.hi) && isfinite(value.lo);
}

__device__ __forceinline__ bool dd_qualification_valid_disk(DDDisk value) {
  return dd_qualification_finite_center(value.real) &&
         dd_qualification_finite_center(value.imaginary) &&
         isfinite(value.radius) && value.radius >= 0.0;
}

__device__ __forceinline__ DDQualificationDiskResult
dd_disk_mul_known_y_norm_sloppy_qualification(
    DDDisk x, DDDisk y, double y_center_norm_upper) {
  std::uint32_t status =
      dd_qualification_valid_disk(x) &&
              dd_qualification_valid_disk(y) &&
              isfinite(y_center_norm_upper) &&
              y_center_norm_upper >= 0.0
          ? kDDQualificationOk
          : kDDQualificationInvalidInput;

  const DDQualificationCenterResult rr =
      dd_qualification_fast_mul_center(x.real, y.real);
  const DDQualificationCenterResult ii =
      dd_qualification_fast_mul_center(x.imaginary, y.imaginary);
  const DDQualificationCenterResult re =
      dd_qualification_fast_add_center(
          rr.value, {-ii.value.hi, -ii.value.lo});
  status |= rr.status | ii.status | re.status;
  const double re_error =
      __dadd_ru(__dadd_ru(rr.error, ii.error), re.error);
  status |= dd_qualification_finite_status(re_error);

  const DDQualificationCenterResult ri =
      dd_qualification_fast_mul_center(x.real, y.imaginary);
  const DDQualificationCenterResult ir =
      dd_qualification_fast_mul_center(x.imaginary, y.real);
  const DDQualificationCenterResult im =
      dd_qualification_fast_add_center(ri.value, ir.value);
  status |= ri.status | ir.status | im.status;
  const double im_error =
      __dadd_ru(__dadd_ru(ri.error, ir.error), im.error);
  status |= dd_qualification_finite_status(im_error);

  const double local_error = __dadd_ru(re_error, im_error);
  status |= dd_qualification_finite_status(local_error);
  const double x_center_l1 =
      dd_l1_norm_upper(x.real, x.imaginary);
  status |= dd_qualification_finite_status(x_center_l1);
  double radius =
      __dadd_ru(local_error, __dmul_ru(x_center_l1, y.radius));
  status |= dd_qualification_finite_status(radius);
  radius = __dadd_ru(
      radius, __dmul_ru(y_center_norm_upper, x.radius));
  status |= dd_qualification_finite_status(radius);
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  status |= dd_qualification_finite_status(radius);

  const DDDisk result{re.value, im.value, radius};
  if (!dd_qualification_valid_disk(result) ||
      !isfinite(local_error) || local_error < 0.0 ||
      !isfinite(x_center_l1) || x_center_l1 < 0.0) {
    status |= kDDQualificationInvalidOutput;
  }
  return {result, status};
}
#endif

__device__ __forceinline__ DDDisk dd_disk_add_square_error(DDDisk value,
                                                            double error) {
  value.radius =
      __dadd_ru(value.radius, disk_norm_upper(error, error));
  return value;
}

__device__ __forceinline__ DDDisk dd_disk_real_projection(DDDisk value) {
  return {value.real, {0.0, 0.0}, value.radius};
}

DDDisk disk_to_dd(Disk value) {
  return {{value.real, 0.0}, {value.imaginary, 0.0}, value.radius};
}

std::vector<DDDisk> boxes_to_dd_disks(
    const std::vector<ComplexInterval>& boxes) {
  std::vector<DDDisk> result;
  result.reserve(boxes.size());
  for (const ComplexInterval box : boxes) {
    result.push_back(disk_to_dd(box_to_disk(box)));
  }
  return result;
}

std::vector<DDDisk> real_boxes_to_dd_disks(
    const std::vector<RealInterval>& boxes) {
  std::vector<DDDisk> result;
  result.reserve(boxes.size());
  for (const RealInterval box : boxes) {
    result.push_back(disk_to_dd(real_box_to_disk(box)));
  }
  return result;
}

struct DDRealEnclosure {
  DD center;
  double radius;
};

// Preserve roughly 106 bits from a 320-bit MPFR interval instead of first
// widening it to adjacent binary64 endpoints.  This is essential for FFT
// roots: an ordinary one-ulp root disk is amplified by the long transform
// graph even when all source packet cells are treated as points.
DDRealEnclosure mpfr_interval_to_dd(mpfr_srcptr lower, mpfr_srcptr upper) {
  MpfrValue midpoint, high, low, center, left_error, right_error, radius;
  mpfr_add(midpoint.value, lower, upper, MPFR_RNDN);
  mpfr_div_2ui(midpoint.value, midpoint.value, 1U, MPFR_RNDN);
  const double hi = mpfr_get_d(midpoint.value, MPFR_RNDN);
  mpfr_set_d(high.value, hi, MPFR_RNDN);
  mpfr_sub(low.value, midpoint.value, high.value, MPFR_RNDN);
  const double lo = mpfr_get_d(low.value, MPFR_RNDN);
  mpfr_set_d(center.value, hi, MPFR_RNDN);
  mpfr_add_d(center.value, center.value, lo, MPFR_RNDN);
  mpfr_sub(left_error.value, center.value, lower, MPFR_RNDU);
  mpfr_abs(left_error.value, left_error.value, MPFR_RNDU);
  mpfr_sub(right_error.value, upper, center.value, MPFR_RNDU);
  mpfr_abs(right_error.value, right_error.value, MPFR_RNDU);
  mpfr_max(radius.value, left_error.value, right_error.value, MPFR_RNDU);
  return {{hi, lo}, mpfr_get_d(radius.value, MPFR_RNDU)};
}

DDDisk combine_dd_enclosures(DDRealEnclosure re, DDRealEnclosure im) {
  MpfrValue re_radius, im_radius, radius;
  mpfr_set_d(re_radius.value, re.radius, MPFR_RNDU);
  mpfr_set_d(im_radius.value, im.radius, MPFR_RNDU);
  mpfr_mul(radius.value, re_radius.value, re_radius.value, MPFR_RNDU);
  mpfr_fma(radius.value, im_radius.value, im_radius.value, radius.value,
           MPFR_RNDU);
  mpfr_sqrt(radius.value, radius.value, MPFR_RNDU);
  return {re.center, im.center, mpfr_get_d(radius.value, MPFR_RNDU)};
}

std::vector<DDDisk> initialize_dd_positive_roots(std::uint32_t max_length) {
  std::vector<DDDisk> roots(max_length / 2U);
  const std::uint32_t log_length = exact_log2(max_length);
  MpfrValue turn, sine_lo, sine_hi, cosine_lo, cosine_hi;
  for (std::uint32_t index = 0; index < max_length / 2U; ++index) {
    mpfr_set_ui(turn.value, index, MPFR_RNDN);
    mpfr_div_2ui(turn.value, turn.value, log_length - 1U, MPFR_RNDN);
    mpfr_sinpi(sine_lo.value, turn.value, MPFR_RNDD);
    mpfr_sinpi(sine_hi.value, turn.value, MPFR_RNDU);
    mpfr_cospi(cosine_lo.value, turn.value, MPFR_RNDD);
    mpfr_cospi(cosine_hi.value, turn.value, MPFR_RNDU);
    roots[index] = combine_dd_enclosures(
        mpfr_interval_to_dd(cosine_lo.value, cosine_hi.value),
        mpfr_interval_to_dd(sine_lo.value, sine_hi.value));
  }
  return roots;
}

std::vector<DDDisk> initialize_dd_stage_reciprocals(std::uint32_t stages) {
  std::vector<DDDisk> result(stages);
  MpfrValue numerator, denominator, lower, upper;
  mpfr_set_ui(numerator.value, 1U, MPFR_RNDN);
  for (std::uint32_t stage = 0; stage < stages; ++stage) {
    mpfr_set_ui(denominator.value, stage + 1U, MPFR_RNDN);
    mpfr_div(lower.value, numerator.value, denominator.value, MPFR_RNDD);
    mpfr_div(upper.value, numerator.value, denominator.value, MPFR_RNDU);
    const DDRealEnclosure value =
        mpfr_interval_to_dd(lower.value, upper.value);
    result[stage] = {value.center, {0.0, 0.0}, value.radius};
  }
  return result;
}

std::vector<DDDisk> initialize_dd_two_pi_t(std::uint32_t length) {
  std::vector<DDDisk> result(length);
  MpfrValue pi_lo, pi_hi, t, lower, upper;
  mpfr_const_pi(pi_lo.value, MPFR_RNDD);
  mpfr_const_pi(pi_hi.value, MPFR_RNDU);
  for (std::uint32_t index = 0; index < length; ++index) {
    const std::int64_t signed_index = static_cast<std::int64_t>(index) -
                                      static_cast<std::int64_t>(length / 2U);
    mpfr_set_si(t.value, -signed_index, MPFR_RNDN);
    mpfr_mul_ui(t.value, t.value, 21U, MPFR_RNDN);
    mpfr_div_2ui(t.value, t.value, 6U, MPFR_RNDN);
    if (mpfr_sgn(t.value) >= 0) {
      mpfr_mul(lower.value, t.value, pi_lo.value, MPFR_RNDD);
      mpfr_mul(upper.value, t.value, pi_hi.value, MPFR_RNDU);
    } else {
      mpfr_mul(lower.value, t.value, pi_hi.value, MPFR_RNDD);
      mpfr_mul(upper.value, t.value, pi_lo.value, MPFR_RNDU);
    }
    const DDRealEnclosure value =
        mpfr_interval_to_dd(lower.value, upper.value);
    result[index] = {value.center, {0.0, 0.0}, value.radius};
  }
  return result;
}

DDDisk initialize_dd_omega(std::uint32_t full_sample_length) {
  const std::uint32_t log_length = exact_log2(full_sample_length);
  MpfrValue turn, sine_lo, sine_hi, cosine_lo, cosine_hi;
  mpfr_set_ui(turn.value, 1U, MPFR_RNDN);
  mpfr_div_2ui(turn.value, turn.value, log_length - 1U, MPFR_RNDN);
  mpfr_sinpi(sine_lo.value, turn.value, MPFR_RNDD);
  mpfr_sinpi(sine_hi.value, turn.value, MPFR_RNDU);
  mpfr_cospi(cosine_lo.value, turn.value, MPFR_RNDD);
  mpfr_cospi(cosine_hi.value, turn.value, MPFR_RNDU);
  return combine_dd_enclosures(
      mpfr_interval_to_dd(cosine_lo.value, cosine_hi.value),
      mpfr_interval_to_dd(sine_lo.value, sine_hi.value));
}

__device__ __forceinline__ bool dd_input_finite_binary64(double value) {
  const std::uint64_t bits =
      static_cast<std::uint64_t>(__double_as_longlong(value));
  return ((bits >> 52U) & 0x7ffU) != 0x7ffU;
}

__device__ __forceinline__ bool dd_disk_input_well_formed(DDDisk value) {
  return dd_input_finite_binary64(value.real.hi) &&
         dd_input_finite_binary64(value.real.lo) &&
         dd_input_finite_binary64(value.imaginary.hi) &&
         dd_input_finite_binary64(value.imaginary.lo) &&
         dd_input_finite_binary64(value.radius) && value.radius >= 0.0;
}

__global__ void dd_build_gamma_rows(
    const DDDisk* gamma0, const DDDisk* two_pi_t,
    const DDDisk* stage_reciprocals, std::uint32_t length,
    std::uint32_t stages, DDDisk* rows,
    std::uint32_t* input_failure_flags,
    std::uint32_t input_failure_bit) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < length; index += blockDim.x * gridDim.x) {
    DDDisk value = gamma0[index];
    if (input_failure_flags != nullptr &&
        !dd_disk_input_well_formed(value)) {
      atomicOr(input_failure_flags, input_failure_bit);
    }
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      rows[static_cast<std::uint64_t>(stage) * length + index] = value;
      if (stage + 1U != stages) {
        value = dd_disk_mul(dd_disk_times_i(value), two_pi_t[index]);
        value = dd_disk_mul(value, stage_reciprocals[stage]);
      }
    }
  }
}

__global__ void dd_copy_add_g_error(const DDDisk* input, DDDisk* output,
                                    std::uint64_t count, double error) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    output[index] = dd_disk_add_square_error(input[index], error);
  }
}

template <bool ValidateInput>
__global__ void dd_bit_reverse_lines(
    const DDDisk* input, DDDisk* output, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t log_length,
    std::uint32_t* input_failure_flags,
    std::uint32_t input_failure_bit) {
  const std::uint64_t count =
      static_cast<std::uint64_t>(lines) * transform_length;
  const std::uint64_t position_mask =
      static_cast<std::uint64_t>(transform_length) - 1U;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t position =
        static_cast<std::uint32_t>(flat & position_mask);
    const std::uint32_t reversed = __brev(position) >> (32U - log_length);
    const std::uint64_t line = flat >> log_length;
    const DDDisk value = input[flat];
    if constexpr (ValidateInput) {
      if (!dd_disk_input_well_formed(value)) {
        atomicOr(input_failure_flags, input_failure_bit);
      }
    }
    output[line * transform_length + reversed] = value;
  }
}

__global__ void dd_initialize_root_center_norms(
    const DDDisk* roots, double* root_center_norms, std::uint32_t count) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < count; index += blockDim.x * gridDim.x) {
    root_center_norms[index] =
        dd_norm_upper(roots[index].real, roots[index].imaginary);
  }
}

__device__ __forceinline__ void dd_radix2_butterfly(
    DDDisk first, DDDisk second, DDDisk root,
    double root_center_norm_upper, DDDisk* left, DDDisk* right) {
  const DDDisk weighted = dd_disk_mul_known_y_norm(
      second, root, root_center_norm_upper);
  *left = dd_disk_add_l1(first, weighted);
  *right = dd_disk_sub_l1(first, weighted);
}

__global__ void dd_radix2_stage(
    DDDisk* values, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t transform_log,
    std::uint32_t maximum_log,
    std::uint32_t stage_log, bool negative_sign) {
  const std::uint64_t butterflies =
      static_cast<std::uint64_t>(lines) * transform_length / 2U;
  const std::uint32_t stage_length = 1U << stage_log;
  const std::uint32_t half = 1U << (stage_log - 1U);
  const std::uint32_t root_stride = 1U << (maximum_log - stage_log);
  const std::uint64_t line_mask =
      (static_cast<std::uint64_t>(transform_length) >> 1U) - 1U;
  const std::uint64_t offset_mask = static_cast<std::uint64_t>(half) - 1U;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < butterflies;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat >> (transform_log - 1U);
    const std::uint64_t local = flat & line_mask;
    const std::uint64_t group = local >> (stage_log - 1U);
    const std::uint32_t offset =
        static_cast<std::uint32_t>(local & offset_mask);
    const std::uint64_t left =
        line * transform_length + group * stage_length + offset;
    const std::uint64_t right = left + half;
    DDDisk root = positive_roots[offset * root_stride];
    if (negative_sign) root = dd_disk_conjugate(root);
    const DDDisk first = values[left];
    dd_radix2_butterfly(
        first, values[right], root,
        positive_root_center_norms[offset * root_stride],
        &values[left], &values[right]);
  }
}

// Fuse two consecutive iterative radix-2 stages while their combined groups
// fit in a 512-value shared-memory tile.  The first half of the kernel writes
// exactly the ordinary first-stage outputs to shared memory; after the block
// barrier the second half performs the ordinary second-stage butterflies and
// publishes only those final values.  This removes the intervening global
// write/read and one kernel launch; it is not a different radix-4 rounding
// formula.
__global__ void dd_radix2_stage_pair(
    DDDisk* values, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t transform_log,
    std::uint32_t maximum_log,
    std::uint32_t first_stage_log, std::uint32_t block_values,
    std::uint32_t blocks_per_line, bool negative_sign) {
  __shared__ DDDisk stage_values[512];
  const std::uint32_t first_half = 1U << (first_stage_log - 1U);
  const std::uint32_t second_half = 1U << first_stage_log;
  const std::uint32_t pair_length = 1U << (first_stage_log + 1U);
  const std::uint32_t first_root_stride =
      1U << (maximum_log - first_stage_log);
  const std::uint32_t second_root_stride =
      1U << (maximum_log - first_stage_log - 1U);
  const std::uint32_t line = blockIdx.x / blocks_per_line;
  if (line >= lines) return;
  const std::uint32_t chunk = blockIdx.x % blocks_per_line;
  const std::uint64_t global_base =
      static_cast<std::uint64_t>(line) * transform_length +
      static_cast<std::uint64_t>(chunk) * block_values;
  const std::uint32_t local_butterfly = threadIdx.x;

  const std::uint32_t first_group =
      local_butterfly >> (first_stage_log - 1U);
  const std::uint32_t first_offset =
      local_butterfly & (first_half - 1U);
  const std::uint32_t first_left =
      first_group * (2U * first_half) + first_offset;
  const std::uint32_t first_right = first_left + first_half;
  const std::uint32_t first_root_index =
      first_offset * first_root_stride;
  DDDisk first_root = positive_roots[first_root_index];
  if (negative_sign) first_root = dd_disk_conjugate(first_root);
  dd_radix2_butterfly(
      values[global_base + first_left],
      values[global_base + first_right], first_root,
      positive_root_center_norms[first_root_index],
      &stage_values[first_left], &stage_values[first_right]);
  __syncthreads();

  const std::uint32_t second_group =
      local_butterfly >> first_stage_log;
  const std::uint32_t second_offset =
      local_butterfly & (second_half - 1U);
  const std::uint32_t second_left =
      second_group * pair_length + second_offset;
  const std::uint32_t second_right = second_left + second_half;
  const std::uint32_t second_root_index =
      second_offset * second_root_stride;
  DDDisk second_root = positive_roots[second_root_index];
  if (negative_sign) second_root = dd_disk_conjugate(second_root);
  dd_radix2_butterfly(
      stage_values[second_left], stage_values[second_right], second_root,
      positive_root_center_norms[second_root_index],
      &values[global_base + second_left],
      &values[global_base + second_right]);
}

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1
__device__ __forceinline__ void
dd_radix2_butterfly_sloppy_root_qualification(
    DDDisk first, DDDisk second, DDDisk root,
    double root_center_norm_upper, DDDisk* left, DDDisk* right,
    std::uint32_t* arithmetic_failure_flags) {
  const DDQualificationDiskResult weighted =
      dd_disk_mul_known_y_norm_sloppy_qualification(
          second, root, root_center_norm_upper);
  *left = dd_disk_add_l1(first, weighted.value);
  *right = dd_disk_sub_l1(first, weighted.value);
  std::uint32_t status = weighted.status;
  if (!dd_qualification_valid_disk(first) ||
      !dd_qualification_valid_disk(*left) ||
      !dd_qualification_valid_disk(*right)) {
    status |= kDDQualificationInvalidOutput;
  }
  if (status != kDDQualificationOk) {
    atomicOr(arithmetic_failure_flags,
             sparkinterval::tg::platt_dd_transform::
                 kQualificationArithmeticFailure);
  }
}

__global__ void dd_radix2_stage_sloppy_root_qualification(
    DDDisk* values, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t transform_log,
    std::uint32_t maximum_log, std::uint32_t stage_log, bool negative_sign,
    std::uint32_t* arithmetic_failure_flags) {
  const std::uint64_t butterflies =
      static_cast<std::uint64_t>(lines) * transform_length / 2U;
  const std::uint32_t stage_length = 1U << stage_log;
  const std::uint32_t half = 1U << (stage_log - 1U);
  const std::uint32_t root_stride = 1U << (maximum_log - stage_log);
  const std::uint64_t line_mask =
      (static_cast<std::uint64_t>(transform_length) >> 1U) - 1U;
  const std::uint64_t offset_mask = static_cast<std::uint64_t>(half) - 1U;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < butterflies;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat >> (transform_log - 1U);
    const std::uint64_t local = flat & line_mask;
    const std::uint64_t group = local >> (stage_log - 1U);
    const std::uint32_t offset =
        static_cast<std::uint32_t>(local & offset_mask);
    const std::uint64_t left =
        line * transform_length + group * stage_length + offset;
    const std::uint64_t right = left + half;
    DDDisk root = positive_roots[offset * root_stride];
    if (negative_sign) root = dd_disk_conjugate(root);
    const DDDisk first = values[left];
    dd_radix2_butterfly_sloppy_root_qualification(
        first, values[right], root,
        positive_root_center_norms[offset * root_stride],
        &values[left], &values[right], arithmetic_failure_flags);
  }
}

__global__ void dd_radix2_stage_pair_sloppy_root_qualification(
    DDDisk* values, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t transform_log,
    std::uint32_t maximum_log, std::uint32_t first_stage_log,
    std::uint32_t block_values, std::uint32_t blocks_per_line,
    bool negative_sign, std::uint32_t* arithmetic_failure_flags) {
  __shared__ DDDisk stage_values[512];
  const std::uint32_t first_half = 1U << (first_stage_log - 1U);
  const std::uint32_t second_half = 1U << first_stage_log;
  const std::uint32_t pair_length = 1U << (first_stage_log + 1U);
  const std::uint32_t first_root_stride =
      1U << (maximum_log - first_stage_log);
  const std::uint32_t second_root_stride =
      1U << (maximum_log - first_stage_log - 1U);
  const std::uint32_t line = blockIdx.x / blocks_per_line;
  if (line >= lines) return;
  const std::uint32_t chunk = blockIdx.x % blocks_per_line;
  const std::uint64_t global_base =
      static_cast<std::uint64_t>(line) * transform_length +
      static_cast<std::uint64_t>(chunk) * block_values;
  const std::uint32_t local_butterfly = threadIdx.x;

  const std::uint32_t first_group =
      local_butterfly >> (first_stage_log - 1U);
  const std::uint32_t first_offset =
      local_butterfly & (first_half - 1U);
  const std::uint32_t first_left =
      first_group * (2U * first_half) + first_offset;
  const std::uint32_t first_right = first_left + first_half;
  const std::uint32_t first_root_index =
      first_offset * first_root_stride;
  DDDisk first_root = positive_roots[first_root_index];
  if (negative_sign) first_root = dd_disk_conjugate(first_root);
  dd_radix2_butterfly_sloppy_root_qualification(
      values[global_base + first_left],
      values[global_base + first_right], first_root,
      positive_root_center_norms[first_root_index],
      &stage_values[first_left], &stage_values[first_right],
      arithmetic_failure_flags);
  __syncthreads();

  const std::uint32_t second_group =
      local_butterfly >> first_stage_log;
  const std::uint32_t second_offset =
      local_butterfly & (second_half - 1U);
  const std::uint32_t second_left =
      second_group * pair_length + second_offset;
  const std::uint32_t second_right = second_left + second_half;
  const std::uint32_t second_root_index =
      second_offset * second_root_stride;
  DDDisk second_root = positive_roots[second_root_index];
  if (negative_sign) second_root = dd_disk_conjugate(second_root);
  dd_radix2_butterfly_sloppy_root_qualification(
      stage_values[second_left], stage_values[second_right], second_root,
      positive_root_center_norms[second_root_index],
      &values[global_base + second_left],
      &values[global_base + second_right], arithmetic_failure_flags);
}
#endif

// Qualification-only early-stage fusion.  A 512-value tile is closed under
// iterative radix-2 stages 1..9.  Every thread performs the same butterfly
// and root/norm lookup as dd_radix2_stage; barriers merely replace the global
// stores/loads between stages.  The final store publishes the exact stage-9
// cells expected by the ordinary stage-10 kernel.
__global__ void dd_radix2_stages_1_through_9_tile_qualification(
    DDDisk* values, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t maximum_log,
    std::uint32_t blocks_per_line, bool negative_sign) {
  __shared__ DDDisk stage_values[512];
  __shared__ DDDisk stage9_roots[256];
  __shared__ double stage9_root_center_norms[256];
  const std::uint32_t line = blockIdx.x / blocks_per_line;
  if (line >= lines) return;
  const std::uint32_t chunk = blockIdx.x % blocks_per_line;
  const std::uint64_t global_base =
      static_cast<std::uint64_t>(line) * transform_length +
      static_cast<std::uint64_t>(chunk) * 512U;
  const std::uint32_t local_butterfly = threadIdx.x;
  const std::uint32_t stage9_root_stride =
      1U << (maximum_log - 9U);

  stage_values[local_butterfly] =
      values[global_base + local_butterfly];
  stage_values[local_butterfly + 256U] =
      values[global_base + local_butterfly + 256U];
  stage9_roots[local_butterfly] =
      positive_roots[local_butterfly * stage9_root_stride];
  stage9_root_center_norms[local_butterfly] =
      positive_root_center_norms[
          local_butterfly * stage9_root_stride];
  __syncthreads();

#pragma unroll
  for (std::uint32_t stage_log = 1U; stage_log <= 9U; ++stage_log) {
    const std::uint32_t half = 1U << (stage_log - 1U);
    const std::uint32_t stage_length = 1U << stage_log;
    const std::uint32_t group =
        local_butterfly >> (stage_log - 1U);
    const std::uint32_t offset =
        local_butterfly & (half - 1U);
    const std::uint32_t left = group * stage_length + offset;
    const std::uint32_t right = left + half;
    const std::uint32_t root_slot = offset << (9U - stage_log);
    DDDisk root = stage9_roots[root_slot];
    if (negative_sign) root = dd_disk_conjugate(root);
    DDDisk left_result{};
    DDDisk right_result{};
    dd_radix2_butterfly(
        stage_values[left], stage_values[right], root,
        stage9_root_center_norms[root_slot],
        &left_result, &right_result);
    stage_values[left] = left_result;
    stage_values[right] = right_result;
    __syncthreads();
  }

  values[global_base + local_butterfly] =
      stage_values[local_butterfly];
  values[global_base + local_butterfly + 256U] =
      stage_values[local_butterfly + 256U];
}

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
static_assert(
    512U * sizeof(DDDisk) + 256U * sizeof(DDDisk) +
            256U * sizeof(double) ==
        sparkinterval::tg::platt_dd_transform::
            kQualificationTile9SloppyRootStaticSharedBytes);
// Joint qualification candidate: preserve the settled sloppy-root operation
// order at every butterfly while retaining stages 1..9 in one closed
// shared-memory tile.  The root slot identity
//
//   (offset << (9-stage_log)) * 2^(maximum_log-9)
//     = offset * 2^(maximum_log-stage_log)
//
// is exactly the ordinary/sloppy stage-kernel root index.  The runner requires
// all 131072 resulting sample disks to be byte-identical to the settled
// sloppy-root entry before accepting this scheduling optimization.
__global__ void
dd_radix2_stages_1_through_9_tile_sloppy_root_qualification(
    DDDisk* values, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t maximum_log,
    std::uint32_t blocks_per_line, bool negative_sign,
    std::uint32_t* arithmetic_failure_flags) {
  __shared__ DDDisk stage_values[512];
  __shared__ DDDisk stage9_roots[256];
  __shared__ double stage9_root_center_norms[256];
  const std::uint32_t line = blockIdx.x / blocks_per_line;
  if (line >= lines) return;
  const std::uint32_t chunk = blockIdx.x % blocks_per_line;
  const std::uint64_t global_base =
      static_cast<std::uint64_t>(line) * transform_length +
      static_cast<std::uint64_t>(chunk) * 512U;
  const std::uint32_t local_butterfly = threadIdx.x;
  const std::uint32_t stage9_root_stride =
      1U << (maximum_log - 9U);

  stage_values[local_butterfly] =
      values[global_base + local_butterfly];
  stage_values[local_butterfly + 256U] =
      values[global_base + local_butterfly + 256U];
  stage9_roots[local_butterfly] =
      positive_roots[local_butterfly * stage9_root_stride];
  stage9_root_center_norms[local_butterfly] =
      positive_root_center_norms[
          local_butterfly * stage9_root_stride];
  __syncthreads();

#pragma unroll
  for (std::uint32_t stage_log = 1U; stage_log <= 9U; ++stage_log) {
    const std::uint32_t half = 1U << (stage_log - 1U);
    const std::uint32_t stage_length = 1U << stage_log;
    const std::uint32_t group =
        local_butterfly >> (stage_log - 1U);
    const std::uint32_t offset =
        local_butterfly & (half - 1U);
    const std::uint32_t left = group * stage_length + offset;
    const std::uint32_t right = left + half;
    const std::uint32_t root_slot = offset << (9U - stage_log);
    DDDisk root = stage9_roots[root_slot];
    if (negative_sign) root = dd_disk_conjugate(root);
    DDDisk left_result{};
    DDDisk right_result{};
    dd_radix2_butterfly_sloppy_root_qualification(
        stage_values[left], stage_values[right], root,
        stage9_root_center_norms[root_slot],
        &left_result, &right_result, arithmetic_failure_flags);
    stage_values[left] = left_result;
    stage_values[right] = right_result;
    __syncthreads();
  }

  values[global_base + local_butterfly] =
      stage_values[local_butterfly];
  values[global_base + local_butterfly + 256U] =
      stage_values[local_butterfly + 256U];
}

#if defined(SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION == 1
// Qualification-only composition of bit reversal with the settled tile9
// kernel.  Since fixed-width bit reversal is an involution, output position
// p receives input position reverse(p), exactly as dd_bit_reverse_lines
// followed by the existing tile.  The intermediate full-array global
// write/read and one launch are removed; every butterfly and root lookup
// remains byte-for-byte the settled tile9 operation.
__global__ void
dd_bit_reverse_and_radix2_stages_1_through_9_tile_sloppy_root_qualification(
    const DDDisk* input, DDDisk* output, const DDDisk* positive_roots,
    const double* positive_root_center_norms, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t transform_log,
    std::uint32_t maximum_log, std::uint32_t blocks_per_line,
    bool negative_sign, std::uint32_t* arithmetic_failure_flags,
    std::uint32_t* input_failure_flags,
    std::uint32_t input_failure_bit) {
  __shared__ DDDisk stage_values[512];
  __shared__ DDDisk stage9_roots[256];
  __shared__ double stage9_root_center_norms[256];
  const std::uint32_t line = blockIdx.x / blocks_per_line;
  if (line >= lines) return;
  const std::uint32_t chunk = blockIdx.x % blocks_per_line;
  const std::uint32_t first_position =
      chunk * 512U + threadIdx.x;
  const std::uint32_t second_position = first_position + 256U;
  const std::uint32_t first_reversed =
      __brev(first_position) >> (32U - transform_log);
  const std::uint32_t second_reversed =
      __brev(second_position) >> (32U - transform_log);
  const std::uint64_t line_base =
      static_cast<std::uint64_t>(line) * transform_length;
  const DDDisk first_value = input[line_base + first_reversed];
  const DDDisk second_value = input[line_base + second_reversed];
  if (input_failure_flags != nullptr &&
      (!dd_disk_input_well_formed(first_value) ||
       !dd_disk_input_well_formed(second_value))) {
    atomicOr(input_failure_flags, input_failure_bit);
  }
  stage_values[threadIdx.x] = first_value;
  stage_values[threadIdx.x + 256U] = second_value;

  const std::uint32_t stage9_root_stride =
      1U << (maximum_log - 9U);
  stage9_roots[threadIdx.x] =
      positive_roots[threadIdx.x * stage9_root_stride];
  stage9_root_center_norms[threadIdx.x] =
      positive_root_center_norms[
          threadIdx.x * stage9_root_stride];
  __syncthreads();

#pragma unroll
  for (std::uint32_t stage_log = 1U; stage_log <= 9U; ++stage_log) {
    const std::uint32_t half = 1U << (stage_log - 1U);
    const std::uint32_t stage_length = 1U << stage_log;
    const std::uint32_t group =
        threadIdx.x >> (stage_log - 1U);
    const std::uint32_t offset = threadIdx.x & (half - 1U);
    const std::uint32_t left = group * stage_length + offset;
    const std::uint32_t right = left + half;
    const std::uint32_t root_slot = offset << (9U - stage_log);
    DDDisk root = stage9_roots[root_slot];
    if (negative_sign) root = dd_disk_conjugate(root);
    DDDisk left_result{};
    DDDisk right_result{};
    dd_radix2_butterfly_sloppy_root_qualification(
        stage_values[left], stage_values[right], root,
        stage9_root_center_norms[root_slot],
        &left_result, &right_result, arithmetic_failure_flags);
    stage_values[left] = left_result;
    stage_values[right] = right_result;
    __syncthreads();
  }

  const std::uint64_t output_base =
      line_base + static_cast<std::uint64_t>(chunk) * 512U;
  output[output_base + threadIdx.x] = stage_values[threadIdx.x];
  output[output_base + threadIdx.x + 256U] =
      stage_values[threadIdx.x + 256U];
}
#endif
#endif

__global__ void dd_postprocess_G(DDDisk* rows, std::uint32_t length,
                                 std::uint32_t stages,
                                 double transform_error) {
  const std::uint64_t count = static_cast<std::uint64_t>(stages) * length;
  const DDDisk inverse_A1{{21.0 / 128.0, 0.0}, {0.0, 0.0}, 0.0};
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t index = static_cast<std::uint32_t>(flat % length);
    if (index > length / 2U) {
      rows[flat] = {{0.0, 0.0}, {0.0, 0.0}, 0.0};
      continue;
    }
    DDDisk value = dd_disk_mul(rows[flat], inverse_A1);
    value = dd_disk_add_square_error(value, transform_error);
    rows[flat] = (index & 1U) != 0U ? dd_disk_negate(value) : value;
  }
}

__global__ void dd_pointwise_products(const DDDisk* left,
                                      const DDDisk* right, DDDisk* output,
                                      std::uint64_t count) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    output[index] = dd_disk_mul(left[index], right[index]);
  }
}

__global__ void dd_normalize_and_taylor_sum(
    const DDDisk* rows, DDDisk* retained, std::uint32_t length,
    std::uint32_t stages, DDDisk reciprocal_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < length / 2U; index += blockDim.x * gridDim.x) {
    DDDisk sum{{0.0, 0.0}, {0.0, 0.0}, 0.0};
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      sum = dd_disk_add(
          sum, dd_disk_mul(
                   rows[static_cast<std::uint64_t>(stage) * length + index],
                   reciprocal_length));
    }
    retained[index] = sum;
  }
}

__global__ void dd_initialize_half_spectrum(
    const DDDisk* retained, DDDisk* half_spectrum,
    std::uint32_t convolution_length, double fmax_error,
    double fhatsum_error, double taylor_error, double transform_error) {
  const std::uint32_t reduced_length = 2U * convolution_length;
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index <= reduced_length; index += blockDim.x * gridDim.x) {
    DDDisk value = index < convolution_length / 2U
        ? retained[index]
        : DDDisk{{0.0, 0.0}, {0.0, 0.0},
                 disk_norm_upper(fmax_error, fmax_error)};
    value = dd_disk_add_square_error(value, fhatsum_error);
    value = dd_disk_add_square_error(value, taylor_error);
    value = dd_disk_add_square_error(value, transform_error);
    half_spectrum[index] =
        (index & 1U) != 0U ? dd_disk_negate(value) : value;
  }
}

__global__ void dd_hermidft_preprocess(
    const DDDisk* half_spectrum, DDDisk* reduced, const DDDisk* roots,
    const double* root_center_norms, DDDisk omega,
    std::uint32_t reduced_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    if (index == 0U) {
      const DDDisk left = dd_disk_mul(
          dd_disk_real_projection(half_spectrum[0]),
          DDDisk{{1.0, 0.0}, {1.0, 0.0}, 0.0});
      const DDDisk right = dd_disk_mul(
          dd_disk_real_projection(half_spectrum[reduced_length]),
          DDDisk{{1.0, 0.0}, {-1.0, 0.0}, 0.0});
      reduced[0] = dd_disk_add(left, right);
      continue;
    }
    const DDDisk mirror =
        dd_disk_conjugate(half_spectrum[reduced_length - index]);
    const DDDisk pair_sum = dd_disk_add(mirror, half_spectrum[index]);
    DDDisk pair_difference =
        dd_disk_times_i(dd_disk_sub(half_spectrum[index], mirror));
    pair_difference = dd_disk_mul_known_y_norm(
        pair_difference, roots[index / 2U],
        root_center_norms[index / 2U]);
    if ((index & 1U) != 0U) {
      pair_difference = dd_disk_mul(pair_difference, omega);
    }
    reduced[index] = dd_disk_add(pair_difference, pair_sum);
  }
}

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1
__global__ void dd_hermidft_preprocess_sloppy_root_qualification(
    const DDDisk* half_spectrum, DDDisk* reduced, const DDDisk* roots,
    const double* root_center_norms, DDDisk omega,
    std::uint32_t reduced_length,
    std::uint32_t* arithmetic_failure_flags) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    if (index == 0U) {
      const DDDisk left = dd_disk_mul(
          dd_disk_real_projection(half_spectrum[0]),
          DDDisk{{1.0, 0.0}, {1.0, 0.0}, 0.0});
      const DDDisk right = dd_disk_mul(
          dd_disk_real_projection(half_spectrum[reduced_length]),
          DDDisk{{1.0, 0.0}, {-1.0, 0.0}, 0.0});
      reduced[0] = dd_disk_add(left, right);
      if (!dd_qualification_valid_disk(reduced[0])) {
        atomicOr(arithmetic_failure_flags,
                 sparkinterval::tg::platt_dd_transform::
                     kQualificationArithmeticFailure);
      }
      continue;
    }
    const DDDisk mirror =
        dd_disk_conjugate(half_spectrum[reduced_length - index]);
    const DDDisk pair_sum = dd_disk_add(mirror, half_spectrum[index]);
    const DDDisk unweighted_difference =
        dd_disk_times_i(dd_disk_sub(half_spectrum[index], mirror));
    const DDQualificationDiskResult weighted =
        dd_disk_mul_known_y_norm_sloppy_qualification(
            unweighted_difference, roots[index / 2U],
            root_center_norms[index / 2U]);
    DDDisk pair_difference = weighted.value;
    if ((index & 1U) != 0U) {
      pair_difference = dd_disk_mul(pair_difference, omega);
    }
    reduced[index] = dd_disk_add(pair_difference, pair_sum);
    if (weighted.status != kDDQualificationOk ||
        !dd_qualification_valid_disk(reduced[index])) {
      atomicOr(arithmetic_failure_flags,
               sparkinterval::tg::platt_dd_transform::
                   kQualificationArithmeticFailure);
    }
  }
}
#endif

__global__ void dd_extract_samples(const DDDisk* reduced,
                                   DDRealDisk* samples,
                                   std::uint32_t reduced_length,
                                   const std::uint32_t* input_failure_flags) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    if (input_failure_flags != nullptr && *input_failure_flags != 0U) {
      const double infinity =
          __longlong_as_double(0x7ff0000000000000LL);
      const DDRealDisk malformed{{0.0, 0.0}, infinity};
      samples[2U * index] = malformed;
      samples[2U * index + 1U] = malformed;
      continue;
    }
    samples[2U * index] = {reduced[index].real, reduced[index].radius};
    samples[2U * index + 1U] =
        {reduced[index].imaginary, reduced[index].radius};
  }
}

void dd_transform(const DDDisk* input, DDDisk* output, const DDDisk* roots,
                  const double* root_center_norms, std::uint32_t lines,
                  std::uint32_t length,
                  std::uint32_t maximum_length, bool negative_sign,
                  cudaStream_t stream = nullptr,
                  std::uint32_t* input_failure_flags = nullptr,
                  std::uint32_t input_failure_bit = 0U) {
  constexpr std::uint32_t threads = 256U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  const std::uint32_t transform_log = exact_log2(length);
  const std::uint32_t maximum_log = exact_log2(maximum_length);
  if (input_failure_flags == nullptr) {
    dd_bit_reverse_lines<false><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, nullptr, 0U);
  } else {
    dd_bit_reverse_lines<true><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, input_failure_flags,
        input_failure_bit);
  }
  std::uint32_t stage_log = 1U;
  constexpr std::uint32_t paired_tile_values = 512U;
  const std::uint32_t block_values =
      std::min(length, paired_tile_values);
  const std::uint32_t blocks_per_line = length / block_values;
  for (; stage_log + 1U <= transform_log &&
         (1U << (stage_log + 1U)) <= block_values;
       stage_log += 2U) {
    dd_radix2_stage_pair<<<lines * blocks_per_line, block_values / 2U, 0U,
                           stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, block_values, blocks_per_line,
        negative_sign);
  }
  for (; stage_log <= transform_log; ++stage_log) {
    dd_radix2_stage<<<blocks_for(cells / 2U), threads, 0U, stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, negative_sign);
  }
}

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1
void dd_transform_sloppy_root_qualification(
    const DDDisk* input, DDDisk* output, const DDDisk* roots,
    const double* root_center_norms, std::uint32_t lines,
    std::uint32_t length, std::uint32_t maximum_length, bool negative_sign,
    cudaStream_t stream, std::uint32_t* arithmetic_failure_flags,
    std::uint32_t* input_failure_flags = nullptr,
    std::uint32_t input_failure_bit = 0U) {
  if (arithmetic_failure_flags == nullptr) {
    throw std::runtime_error(
        "sloppy-root qualification requires a failure word");
  }
  constexpr std::uint32_t threads = 256U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  const std::uint32_t transform_log = exact_log2(length);
  const std::uint32_t maximum_log = exact_log2(maximum_length);
  if (input_failure_flags == nullptr) {
    dd_bit_reverse_lines<false><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, nullptr, 0U);
  } else {
    dd_bit_reverse_lines<true><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, input_failure_flags,
        input_failure_bit);
  }
  std::uint32_t stage_log = 1U;
  constexpr std::uint32_t paired_tile_values = 512U;
  const std::uint32_t block_values =
      std::min(length, paired_tile_values);
  const std::uint32_t blocks_per_line = length / block_values;
  for (; stage_log + 1U <= transform_log &&
         (1U << (stage_log + 1U)) <= block_values;
       stage_log += 2U) {
    dd_radix2_stage_pair_sloppy_root_qualification<<<
        lines * blocks_per_line, block_values / 2U, 0U, stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, block_values, blocks_per_line,
        negative_sign, arithmetic_failure_flags);
  }
  for (; stage_log <= transform_log; ++stage_log) {
    dd_radix2_stage_sloppy_root_qualification<<<
        blocks_for(cells / 2U), threads, 0U, stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, negative_sign, arithmetic_failure_flags);
  }
}
#endif

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
void dd_transform_tile9_sloppy_root_qualification(
    const DDDisk* input, DDDisk* output, const DDDisk* roots,
    const double* root_center_norms, std::uint32_t lines,
    std::uint32_t length, std::uint32_t maximum_length,
    bool negative_sign, cudaStream_t stream,
    std::uint32_t* arithmetic_failure_flags,
    std::uint32_t* input_failure_flags = nullptr,
    std::uint32_t input_failure_bit = 0U) {
  if (arithmetic_failure_flags == nullptr) {
    throw std::runtime_error(
        "tile9 sloppy-root qualification requires a failure word");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t tile_values = 512U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  const std::uint32_t transform_log = exact_log2(length);
  const std::uint32_t maximum_log = exact_log2(maximum_length);
  if (transform_log < 9U || maximum_log < transform_log ||
      length % tile_values != 0U) {
    throw std::runtime_error(
        "tile9 sloppy-root qualification requires a power-of-two length "
        "divisible by 512 and a covering root table");
  }
  if (input_failure_flags == nullptr) {
    dd_bit_reverse_lines<false><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, nullptr, 0U);
  } else {
    dd_bit_reverse_lines<true><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, input_failure_flags,
        input_failure_bit);
  }
  const std::uint32_t blocks_per_line = length / tile_values;
  dd_radix2_stages_1_through_9_tile_sloppy_root_qualification<<<
      lines * blocks_per_line, threads, 0U, stream>>>(
      output, roots, root_center_norms, lines, length, maximum_log,
      blocks_per_line, negative_sign, arithmetic_failure_flags);
  for (std::uint32_t stage_log = 10U; stage_log <= transform_log;
       ++stage_log) {
    dd_radix2_stage_sloppy_root_qualification<<<
        blocks_for(cells / 2U), threads, 0U, stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, negative_sign, arithmetic_failure_flags);
  }
}

#if defined(SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION == 1
void dd_transform_bitreverse_tile9_sloppy_root_qualification(
    const DDDisk* input, DDDisk* output, const DDDisk* roots,
    const double* root_center_norms, std::uint32_t lines,
    std::uint32_t length, std::uint32_t maximum_length,
    bool negative_sign, cudaStream_t stream,
    std::uint32_t* arithmetic_failure_flags,
    std::uint32_t* input_failure_flags = nullptr,
    std::uint32_t input_failure_bit = 0U) {
  if (arithmetic_failure_flags == nullptr) {
    throw std::runtime_error(
        "bitreverse-tile9 qualification requires a failure word");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t tile_values = 512U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  const std::uint32_t transform_log = exact_log2(length);
  const std::uint32_t maximum_log = exact_log2(maximum_length);
  if (transform_log < 9U || maximum_log < transform_log ||
      length % tile_values != 0U || input == output) {
    throw std::runtime_error(
        "bitreverse-tile9 qualification requires distinct input/output, "
        "a power-of-two length divisible by 512, and a covering root table");
  }
  const std::uint32_t blocks_per_line = length / tile_values;
  dd_bit_reverse_and_radix2_stages_1_through_9_tile_sloppy_root_qualification<<<
      lines * blocks_per_line, threads, 0U, stream>>>(
      input, output, roots, root_center_norms, lines, length, transform_log,
      maximum_log, blocks_per_line, negative_sign, arithmetic_failure_flags,
      input_failure_flags, input_failure_bit);
  for (std::uint32_t stage_log = 10U; stage_log <= transform_log;
       ++stage_log) {
    dd_radix2_stage_sloppy_root_qualification<<<
        blocks_for(cells / 2U), threads, 0U, stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, negative_sign, arithmetic_failure_flags);
  }
}
#endif
#endif

void dd_transform_tile9_qualification(
    const DDDisk* input, DDDisk* output, const DDDisk* roots,
    const double* root_center_norms, std::uint32_t lines,
    std::uint32_t length, std::uint32_t maximum_length,
    bool negative_sign, cudaStream_t stream = nullptr,
    std::uint32_t* input_failure_flags = nullptr,
    std::uint32_t input_failure_bit = 0U) {
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t tile_values = 512U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  const std::uint32_t transform_log = exact_log2(length);
  const std::uint32_t maximum_log = exact_log2(maximum_length);
  if (transform_log < 9U || maximum_log < transform_log ||
      length % tile_values != 0U) {
    throw std::runtime_error(
        "qualification tile9 transform requires a power-of-two length "
        "divisible by 512 and a covering root table");
  }
  if (input_failure_flags == nullptr) {
    dd_bit_reverse_lines<false><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, nullptr, 0U);
  } else {
    dd_bit_reverse_lines<true><<<blocks_for(cells), threads, 0U, stream>>>(
        input, output, lines, length, transform_log, input_failure_flags,
        input_failure_bit);
  }
  const std::uint32_t blocks_per_line = length / tile_values;
  dd_radix2_stages_1_through_9_tile_qualification<<<
      lines * blocks_per_line, threads, 0U, stream>>>(
      output, roots, root_center_norms, lines, length, maximum_log,
      blocks_per_line, negative_sign);
  for (std::uint32_t stage_log = 10U; stage_log <= transform_log;
       ++stage_log) {
    dd_radix2_stage<<<blocks_for(cells / 2U), threads, 0U, stream>>>(
        output, roots, root_center_norms, lines, length, transform_log,
        maximum_log, stage_log, negative_sign);
  }
}

std::uint64_t dd_disk_fnv1a(const std::vector<DDRealDisk>& values) {
  return fnv1a_bytes(values.data(), values.size() * sizeof(DDRealDisk));
}

struct RequiredSignPacketExport {
  std::string sha256;
  std::uint64_t bytes = 0U;
  std::uint64_t sample_fnv1a64 = 0U;
  std::uint64_t sign_fnv1a64 = 0U;
};

RequiredSignPacketExport write_required_sign_packet(
    const std::string& path, const std::vector<DDRealDisk>& all_samples,
    std::size_t begin, std::size_t end,
    const LoadedSourcePacket106& source) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "required-sign packet export requires a little-endian host");
  }
  if (begin > end || end >= all_samples.size()) {
    throw std::runtime_error("required-sign packet range is invalid");
  }
  const std::size_t count = end - begin + 1U;
  std::vector<DDRealDisk> samples(all_samples.begin() + begin,
                                  all_samples.begin() + end + 1U);
  std::vector<unsigned char> signs((count + 7U) / 8U, 0U);
  for (std::size_t index = 0; index < count; ++index) {
    const DDRealDisk value = samples[index];
    if (!std::isfinite(value.center.hi) ||
        !std::isfinite(value.center.lo) ||
        !std::isfinite(value.radius) || value.radius < 0.0) {
      throw std::runtime_error(
          "required-sign packet contains an invalid disk");
    }
    const double center_lower =
        std::max(0.0, std::fabs(value.center.hi) -
                          std::fabs(value.center.lo));
    if (!(center_lower > value.radius) || value.center.hi == 0.0) {
      throw std::runtime_error(
          "required-sign packet refuses an ambiguous sample");
    }
    if (value.center.hi > 0.0) {
      signs[index / 8U] |= static_cast<unsigned char>(1U << (index % 8U));
    }
  }
  if ((count & 7U) != 0U) {
    const unsigned used = static_cast<unsigned>(count & 7U);
    const unsigned char unused_mask =
        static_cast<unsigned char>(0xffU << used);
    if ((signs.back() & unused_mask) != 0U) {
      throw std::runtime_error(
          "required-sign packet has nonzero unused sign bits");
    }
  }

  pw::RequiredSignPacketHeader header{};
  header.magic = pw::kRequiredSignPacketMagic;
  header.version = pw::kRequiredSignPacketVersion;
  header.header_bytes = sizeof(header);
  header.endian_tag = pw::kSourcePacketEndianTag;
  header.sample_encoding = pw::kRequiredSignSampleEncoding;
  header.sign_encoding = pw::kRequiredSignBitEncoding;
  header.source_terms = source.source_terms;
  header.required_begin = static_cast<std::uint32_t>(begin);
  header.required_end = static_cast<std::uint32_t>(end);
  header.required_count = static_cast<std::uint32_t>(count);
  header.reserved_zero = 0U;
  header.window_center = source.window_center;
  header.sample_bytes = samples.size() * sizeof(DDRealDisk);
  header.sign_bytes = signs.size();
  header.sample_fnv1a64 = fnv1a_bytes(samples.data(), header.sample_bytes);
  header.sign_fnv1a64 = fnv1a_bytes(signs.data(), signs.size());
  header.source_packet_bytes = source.bytes;
  if (source.sha256.size() != header.source_packet_sha256.size()) {
    throw std::runtime_error("source packet SHA-256 length is invalid");
  }
  std::memcpy(header.source_packet_sha256.data(), source.sha256.data(),
              header.source_packet_sha256.size());
  std::memcpy(header.upstream_commit.data(), pw::kUpstreamCommit,
              header.upstream_commit.size());

  std::vector<unsigned char> bytes(sizeof(header) + header.sample_bytes +
                                   header.sign_bytes);
  std::size_t offset = 0U;
  std::memcpy(bytes.data() + offset, &header, sizeof(header));
  offset += sizeof(header);
  std::memcpy(bytes.data() + offset, samples.data(), header.sample_bytes);
  offset += header.sample_bytes;
  std::memcpy(bytes.data() + offset, signs.data(), signs.size());
  offset += signs.size();
  if (offset != bytes.size()) {
    throw std::runtime_error("required-sign packet byte accounting failed");
  }
  const std::string temporary = path + ".partial";
  {
    std::ifstream existing(path, std::ios::binary);
    std::ifstream partial(temporary, std::ios::binary);
    if (existing.good() || partial.good()) {
      throw std::runtime_error(
          "required-sign packet output or partial already exists");
    }
  }
  std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
  if (!output) throw std::runtime_error("cannot open required-sign packet");
  output.write(reinterpret_cast<const char*>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  output.close();
  if (!output || std::rename(temporary.c_str(), path.c_str()) != 0) {
    std::remove(temporary.c_str());
    throw std::runtime_error("cannot publish complete required-sign packet");
  }
  return {sparkinterval::sha256_hex(bytes.data(), bytes.size()), bytes.size(),
          header.sample_fnv1a64, header.sign_fnv1a64};
}

int run_dd_disk_semantic(const DDDiskOptions& options) {
  constexpr std::uint32_t threads = 256U;
  const std::uint32_t length = options.convolution_length;
  const std::uint32_t stages = options.taylor_terms;
  const std::uint32_t reduced_length = 2U * length;
  const std::uint32_t sample_count = 2U * reduced_length;
  const std::uint64_t row_cells = static_cast<std::uint64_t>(stages) * length;
  if (!options.endpoint_certificate.empty()) {
    throw std::runtime_error(
        "two-limb diagnostic does not implement the single-limb endpoint wire format");
  }

  const bool packet_supplied = !options.source_packet.empty();
  LoadedSourcePacket loaded_packet{};
  LoadedSourcePacket106 loaded_packet106{};
  bool packet_is_106 = false;
  HostInputs box_host;
  std::vector<DDDisk> gamma0;
  std::vector<DDDisk> skn_rows;
  if (packet_supplied) {
    packet_is_106 = source_packet_is_106(options.source_packet);
    if (packet_is_106) {
      loaded_packet106 = load_source_packet106(options.source_packet);
      gamma0 = std::move(loaded_packet106.gamma0);
      skn_rows = std::move(loaded_packet106.skn_rows);
    } else {
      loaded_packet = load_source_packet(options.source_packet);
      box_host = std::move(loaded_packet.inputs);
      gamma0 = boxes_to_dd_disks(box_host.gamma0);
      skn_rows = boxes_to_dd_disks(box_host.skn_rows);
    }
    const bool complete = packet_is_106 ? loaded_packet106.complete_terms
                                        : loaded_packet.complete_terms;
    if (options.require_full_source_packet && !complete) {
      throw std::runtime_error(
          "source packet is partial but complete source terms were required");
    }
  } else {
    box_host = initialize_inputs(options);
    gamma0 = boxes_to_dd_disks(box_host.gamma0);
    skn_rows = boxes_to_dd_disks(box_host.skn_rows);
  }

  const std::vector<DDDisk> two_pi_t =
      options.source_shape ? initialize_dd_two_pi_t(length)
                           : real_boxes_to_dd_disks(box_host.two_pi_t);
  if (options.discard_source_packet_radii_for_diagnostic) {
    for (DDDisk& value : gamma0) value.radius = 0.0;
    for (DDDisk& value : skn_rows) value.radius = 0.0;
  }
  const std::vector<DDDisk> roots =
      initialize_dd_positive_roots(reduced_length);
  const std::vector<DDDisk> stage_reciprocals =
      initialize_dd_stage_reciprocals(stages);
  const DDDisk reciprocal_length{
      {std::ldexp(1.0, -static_cast<int>(exact_log2(length))), 0.0},
      {0.0, 0.0}, 0.0};
  const DDDisk omega = initialize_dd_omega(sample_count);

  cudaDeviceProp properties{};
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));

  DDDisk *d_gamma0 = nullptr, *d_two_pi_t = nullptr;
  DDDisk *d_stage_reciprocals = nullptr, *d_skn = nullptr;
  DDDisk *d_gamma_rows = nullptr, *d_G_negative = nullptr;
  DDDisk *d_G_positive = nullptr, *d_S_positive = nullptr;
  DDDisk *d_products = nullptr, *d_convolutions = nullptr;
  DDDisk *d_retained = nullptr, *d_half_spectrum = nullptr;
  DDDisk *d_hermi_pre = nullptr, *d_hermi_fft = nullptr, *d_roots = nullptr;
  double* d_root_center_norms = nullptr;
  DDRealDisk* d_samples = nullptr;

  auto allocate = [](auto** pointer, std::uint64_t count) {
    CUDA_CHECK(cudaMalloc(pointer, count * sizeof(**pointer)));
  };
  allocate(&d_gamma0, length);
  allocate(&d_two_pi_t, length);
  allocate(&d_stage_reciprocals, stages);
  allocate(&d_skn, row_cells);
  allocate(&d_gamma_rows, row_cells);
  allocate(&d_G_negative, row_cells);
  allocate(&d_G_positive, row_cells);
  allocate(&d_S_positive, row_cells);
  allocate(&d_products, row_cells);
  allocate(&d_convolutions, row_cells);
  allocate(&d_retained, length / 2U);
  allocate(&d_half_spectrum, reduced_length + 1U);
  allocate(&d_hermi_pre, reduced_length);
  allocate(&d_hermi_fft, reduced_length);
  allocate(&d_roots, roots.size());
  allocate(&d_root_center_norms, roots.size());
  allocate(&d_samples, sample_count);

  CUDA_CHECK(cudaMemcpy(d_gamma0, gamma0.data(), length * sizeof(DDDisk),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_two_pi_t, two_pi_t.data(), length * sizeof(DDDisk),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_stage_reciprocals, stage_reciprocals.data(),
                        stages * sizeof(DDDisk), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_skn, skn_rows.data(), row_cells * sizeof(DDDisk),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots, roots.data(), roots.size() * sizeof(DDDisk),
                        cudaMemcpyHostToDevice));
  dd_initialize_root_center_norms<<<blocks_for(roots.size()), threads>>>(
      d_roots, d_root_center_norms,
      static_cast<std::uint32_t>(roots.size()));
  CUDA_CHECK(cudaGetLastError());

  const double g_error = options.source_errors ? kGTruncationError : 0.0;
  const double G_error = options.source_errors ? kGTransformError : 0.0;
  const double fmax_error = options.source_errors ? kFMaxError : 0.0;
  const double fhatsum_error = options.source_errors ? kFHatSumError : 0.0;
  const double taylor_error = options.source_errors ? kTaylorError : 0.0;
  const double fhat_transform_error =
      options.source_errors ? kFHatTransformError : 0.0;

  cudaEvent_t start{}, stop{};
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t repetition = 0; repetition < options.repetitions;
       ++repetition) {
    dd_build_gamma_rows<<<blocks_for(length), threads>>>(
        d_gamma0, d_two_pi_t, d_stage_reciprocals, length, stages,
        d_gamma_rows, nullptr, 0U);
    dd_copy_add_g_error<<<blocks_for(row_cells), threads>>>(
        d_gamma_rows, d_G_positive, row_cells, g_error);
    dd_transform(d_G_positive, d_G_negative, d_roots, d_root_center_norms,
                 stages, length, reduced_length, true);
    dd_postprocess_G<<<blocks_for(row_cells), threads>>>(
        d_G_negative, length, stages, G_error);
    dd_transform(d_G_negative, d_G_positive, d_roots, d_root_center_norms,
                 stages, length, reduced_length, false);
    dd_transform(d_skn, d_S_positive, d_roots, d_root_center_norms, stages,
                 length, reduced_length, false);
    dd_pointwise_products<<<blocks_for(row_cells), threads>>>(
        d_G_positive, d_S_positive, d_products, row_cells);
    dd_transform(d_products, d_convolutions, d_roots, d_root_center_norms,
                 stages, length, reduced_length, true);
    dd_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads>>>(
        d_convolutions, d_retained, length, stages, reciprocal_length);
    dd_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads>>>(
        d_retained, d_half_spectrum, length, fmax_error, fhatsum_error,
        taylor_error, fhat_transform_error);
    dd_hermidft_preprocess<<<blocks_for(reduced_length), threads>>>(
        d_half_spectrum, d_hermi_pre, d_roots, d_root_center_norms, omega,
        reduced_length);
    dd_transform(d_hermi_pre, d_hermi_fft, d_roots, d_root_center_norms, 1U,
                 reduced_length, reduced_length, false);
    dd_extract_samples<<<blocks_for(reduced_length), threads>>>(
        d_hermi_fft, d_samples, reduced_length, nullptr);
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  CUDA_CHECK(cudaGetLastError());

  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
  std::vector<DDRealDisk> samples(sample_count);
  CUDA_CHECK(cudaMemcpy(samples.data(), d_samples,
                        samples.size() * sizeof(DDRealDisk),
                        cudaMemcpyDeviceToHost));

  bool finite = true;
  std::uint64_t sign_ambiguous = 0U;
  std::uint64_t source_region_sign_ambiguous = 0U;
  double maximum_radius = 0.0;
  double maximum_center_upper = 0.0;
  double minimum_sign_margin = std::numeric_limits<double>::infinity();
  std::size_t maximum_radius_index = 0U;
  std::size_t first_ambiguous_index = samples.size();
  std::size_t first_source_region_ambiguous_index = samples.size();
  // Upstream consumes exactly the centre, plus TURING_LEN=512,
  // int_step/2=12288, and Ns*INTER_SPACING=70 samples on each side.
  constexpr std::size_t kSourceRegionRadius = 512U + 12288U + 70U;
  const std::size_t source_region_center = sample_count / 2U;
  const std::size_t source_region_begin =
      source_region_center - kSourceRegionRadius;
  const std::size_t source_region_end =
      source_region_center + kSourceRegionRadius;
  std::uint64_t center_abs_le_1e30 = 0U;
  std::uint64_t center_abs_le_1e24 = 0U;
  std::uint64_t center_abs_le_1e21 = 0U;
  std::uint64_t center_abs_le_1e18 = 0U;
  for (std::size_t index = 0; index < samples.size(); ++index) {
    const DDRealDisk sample = samples[index];
    finite = finite && std::isfinite(sample.center.hi) &&
             std::isfinite(sample.center.lo) &&
             std::isfinite(sample.radius) && sample.radius >= 0.0;
    // |hi+lo| >= |hi|-|lo|, so this deliberately fails closed if the low
    // limb could affect either the sign or its distance from the disk radius.
    const double center_lower =
        std::max(0.0, std::fabs(sample.center.hi) -
                          std::fabs(sample.center.lo));
    const double center_upper =
        std::fabs(sample.center.hi) + std::fabs(sample.center.lo);
    if (center_upper <= 1.0e-30) ++center_abs_le_1e30;
    if (center_upper <= 1.0e-24) ++center_abs_le_1e24;
    if (center_upper <= 1.0e-21) ++center_abs_le_1e21;
    if (center_upper <= 1.0e-18) ++center_abs_le_1e18;
    const double sign_margin = center_lower - sample.radius;
    if (sign_margin <= 0.0) {
      if (first_ambiguous_index == samples.size()) first_ambiguous_index = index;
      ++sign_ambiguous;
      if (index >= source_region_begin && index <= source_region_end) {
        if (first_source_region_ambiguous_index == samples.size()) {
          first_source_region_ambiguous_index = index;
        }
        ++source_region_sign_ambiguous;
      }
    }
    if (sample.radius > maximum_radius) {
      maximum_radius = sample.radius;
      maximum_radius_index = index;
    }
    maximum_center_upper = std::max(maximum_center_upper, center_upper);
    minimum_sign_margin = std::min(minimum_sign_margin, sign_margin);
  }
  const DDRealDisk first_ambiguous =
      first_ambiguous_index < samples.size()
          ? samples[first_ambiguous_index]
          : DDRealDisk{{0.0, 0.0}, 0.0};

  RequiredSignPacketExport required_sign_packet{};
  const bool required_sign_packet_exported =
      !options.export_required_sign_packet.empty();
  if (required_sign_packet_exported) {
    if (!packet_is_106 || !loaded_packet106.complete_terms ||
        options.discard_source_packet_radii_for_diagnostic ||
        !options.source_shape || !options.source_errors || !finite ||
        source_region_sign_ambiguous != 0U) {
      throw std::runtime_error(
          "required-sign packet export requires a complete v2 source "
          "packet, all source errors, and zero required-region ambiguities");
    }
    required_sign_packet = write_required_sign_packet(
        options.export_required_sign_packet, samples, source_region_begin,
        source_region_end, loaded_packet106);
  }

  bool kat_contained = true;
  double maximum_kat_distance = 0.0;
  if (!options.source_shape && !options.source_errors && length <= 32U) {
    const std::vector<long double> reference =
        reference_samples(options, box_host);
    for (std::size_t index = 0; index < samples.size(); ++index) {
      const long double center =
          static_cast<long double>(samples[index].center.hi) +
          static_cast<long double>(samples[index].center.lo);
      const long double distance = fabsl(reference[index] - center);
      kat_contained = kat_contained &&
          distance <= static_cast<long double>(samples[index].radius);
      maximum_kat_distance =
          std::max(maximum_kat_distance, static_cast<double>(distance));
    }
  }

  const std::uint64_t batched_butterflies =
      4ULL * stages * (length / 2ULL) * exact_log2(length);
  const std::uint64_t final_butterflies =
      static_cast<std::uint64_t>(reduced_length / 2U) *
      exact_log2(reduced_length);
  const std::uint64_t butterflies_per_run =
      batched_butterflies + final_butterflies;
  const double elapsed_seconds = static_cast<double>(elapsed_ms) / 1000.0;
  const double runs_per_second = options.repetitions / elapsed_seconds;

  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-windowed-dd-disk-semantic.v1\""
            << ",\"claim_scope\":\"source_core_packet_to_two_limb_disk_transform_diagnostic_not_a_zeta_certificate\""
            << ",\"formal_arithmetic_model\":\"two_limb_centers_with_TwoSum_FMA_residual_disks_candidate\""
            << ",\"physical_trace_refinement_proved\":false"
            << ",\"actual_zeta_inputs\":false"
            << ",\"source_core_packet_consumed\":"
            << (packet_supplied ? "true" : "false")
            << ",\"source_packet_interval_encoding\":"
            << (packet_supplied ? (packet_is_106 ? 2U : 1U) : 0U)
            << ",\"source_packet_complete_terms\":"
            << (packet_supplied &&
                        (packet_is_106 ? loaded_packet106.complete_terms
                                       : loaded_packet.complete_terms)
                    ? "true"
                    : "false")
            << ",\"source_packet_term_count\":"
            << (packet_supplied
                    ? (packet_is_106 ? loaded_packet106.source_terms
                                     : loaded_packet.source_terms)
                    : 0U)
            << ",\"source_packet_bytes\":"
            << (packet_supplied
                    ? (packet_is_106 ? loaded_packet106.bytes
                                     : loaded_packet.bytes)
                    : 0U)
            << ",\"source_packet_sha256\":\""
            << (packet_supplied
                    ? (packet_is_106 ? loaded_packet106.sha256
                                     : loaded_packet.sha256)
                    : "")
            << "\""
            << ",\"source_packet_radii_discarded_for_diagnostic\":"
            << (options.discard_source_packet_radii_for_diagnostic ? "true"
                                                                   : "false")
            << ",\"device\":\"" << properties.name << "\""
            << ",\"compute_capability\":\"" << properties.major << "."
            << properties.minor << "\""
            << ",\"convolution_length\":" << length
            << ",\"taylor_terms\":" << stages
            << ",\"repetitions\":" << options.repetitions
            << ",\"butterflies_per_run\":" << butterflies_per_run
            << ",\"elapsed_seconds\":" << elapsed_seconds
            << ",\"semantic_runs_per_second\":" << runs_per_second
            << ",\"butterflies_per_second\":"
            << static_cast<double>(butterflies_per_run) * options.repetitions /
                   elapsed_seconds
            << ",\"all_output_disks_finite\":" << (finite ? "true" : "false")
            << ",\"sign_ambiguous_samples\":" << sign_ambiguous
            << ",\"all_sample_signs_certified\":"
            << (sign_ambiguous == 0U ? "true" : "false")
            << ",\"source_required_sample_begin\":" << source_region_begin
            << ",\"source_required_sample_end\":" << source_region_end
            << ",\"source_required_sample_count\":"
            << source_region_end - source_region_begin + 1U
            << ",\"source_required_sign_ambiguous_samples\":"
            << source_region_sign_ambiguous
            << ",\"source_required_sample_signs_certified\":"
            << (source_region_sign_ambiguous == 0U ? "true" : "false")
            << ",\"source_required_sign_stream_constructible\":"
            << (source_region_sign_ambiguous == 0U ? "true" : "false")
            << ",\"required_sign_packet_exported\":"
            << (required_sign_packet_exported ? "true" : "false")
            << ",\"required_sign_packet_bytes\":"
            << required_sign_packet.bytes
            << ",\"required_sign_packet_sha256\":\""
            << required_sign_packet.sha256 << "\""
            << ",\"required_sign_packet_sample_fnv1a64\":\""
            << std::hex << std::setw(16) << std::setfill('0')
            << required_sign_packet.sample_fnv1a64
            << "\""
            << ",\"required_sign_packet_sign_fnv1a64\":\""
            << std::setw(16) << required_sign_packet.sign_fnv1a64
            << "\"" << std::dec
            << ",\"zero_isolation_events_constructed\":false"
            << ",\"turing_event_stream_constructed\":false"
            << ",\"global_zero_count_constructed\":false"
            << ",\"first_source_required_ambiguous_index\":"
            << (first_source_region_ambiguous_index < samples.size()
                    ? static_cast<std::int64_t>(
                          first_source_region_ambiguous_index)
                    : -1)
            << ",\"ambiguity_policy\":\"two_limb_triangle_lower_bound_fails_closed\""
            << ",\"maximum_output_radius\":" << maximum_radius
            << ",\"maximum_output_diameter\":" << 2.0 * maximum_radius
            << ",\"maximum_output_radius_index\":" << maximum_radius_index
            << ",\"maximum_output_center_abs_upper\":"
            << maximum_center_upper
            << ",\"minimum_sign_margin\":" << minimum_sign_margin
            << ",\"center_abs_le_1e-30\":" << center_abs_le_1e30
            << ",\"center_abs_le_1e-24\":" << center_abs_le_1e24
            << ",\"center_abs_le_1e-21\":" << center_abs_le_1e21
            << ",\"center_abs_le_1e-18\":" << center_abs_le_1e18
            << ",\"first_ambiguous_index\":"
            << (first_ambiguous_index < samples.size()
                    ? static_cast<std::int64_t>(first_ambiguous_index)
                    : -1)
            << ",\"first_ambiguous_center_hi\":" << first_ambiguous.center.hi
            << ",\"first_ambiguous_center_lo\":" << first_ambiguous.center.lo
            << ",\"first_ambiguous_radius\":" << first_ambiguous.radius
            << ",\"small_long_double_kat_contained\":"
            << (kat_contained ? "true" : "false")
            << ",\"maximum_kat_center_distance\":" << maximum_kat_distance
            << ",\"whole_transform_trace_exported\":false"
            << ",\"output_fnv1a64\":\"" << std::hex << std::setw(16)
            << std::setfill('0') << dd_disk_fnv1a(samples) << "\"}\n";

  CUDA_CHECK(cudaEventDestroy(start));
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaFree(d_gamma0));
  CUDA_CHECK(cudaFree(d_two_pi_t));
  CUDA_CHECK(cudaFree(d_stage_reciprocals));
  CUDA_CHECK(cudaFree(d_skn));
  CUDA_CHECK(cudaFree(d_gamma_rows));
  CUDA_CHECK(cudaFree(d_G_negative));
  CUDA_CHECK(cudaFree(d_G_positive));
  CUDA_CHECK(cudaFree(d_S_positive));
  CUDA_CHECK(cudaFree(d_products));
  CUDA_CHECK(cudaFree(d_convolutions));
  CUDA_CHECK(cudaFree(d_retained));
  CUDA_CHECK(cudaFree(d_half_spectrum));
  CUDA_CHECK(cudaFree(d_hermi_pre));
  CUDA_CHECK(cudaFree(d_hermi_fft));
  CUDA_CHECK(cudaFree(d_root_center_norms));
  CUDA_CHECK(cudaFree(d_roots));
  CUDA_CHECK(cudaFree(d_samples));
  return finite && kat_contained &&
                 (!options.require_unambiguous || sign_ambiguous == 0U)
                 && (!options.require_source_region_unambiguous ||
                     source_region_sign_ambiguous == 0U)
             ? 0
             : 1;
}

}  // namespace

namespace sparkinterval::tg::platt_dd_transform {

struct Workspace {
  DDDisk* two_pi_t = nullptr;
  DDDisk* stage_reciprocals = nullptr;
  DDDisk* gamma_rows = nullptr;
  DDDisk* G_negative = nullptr;
  DDDisk* G_positive = nullptr;
  DDDisk* S_positive = nullptr;
  DDDisk* products = nullptr;
  DDDisk* convolutions = nullptr;
  DDDisk* retained = nullptr;
  DDDisk* half_spectrum = nullptr;
  DDDisk* hermi_pre = nullptr;
  DDDisk* hermi_fft = nullptr;
  DDDisk* roots = nullptr;
  double* root_center_norms = nullptr;
  DDRealDisk* samples = nullptr;
  std::uint32_t* input_failure_flags = nullptr;
  DDDisk reciprocal_length{};
  DDDisk omega{};
  std::uint64_t allocated_bytes = 0U;
};

static_assert(sizeof(DDDisk) == sizeof(platt_windowed::ComplexDisk106));
static_assert(alignof(DDDisk) == alignof(platt_windowed::ComplexDisk106));
static_assert(sizeof(DDRealDisk) == sizeof(platt_windowed::RealDisk106));
static_assert(alignof(DDRealDisk) == alignof(platt_windowed::RealDisk106));
static_assert(kSourceSampleCount == 131'072U);
static_assert(kSourceRequiredBegin == 52'666U);
static_assert(kSourceRequiredEnd == 78'406U);
static_assert(kSourceRequiredCount == 25'741U);

namespace {

void release_storage(Workspace* workspace, cudaError_t* first_error) {
  if (workspace == nullptr) return;
  auto release = [&](void* pointer) {
    if (pointer == nullptr) return;
    const cudaError_t status = cudaFree(pointer);
    if (*first_error == cudaSuccess && status != cudaSuccess) {
      *first_error = status;
    }
  };
  release(workspace->two_pi_t);
  release(workspace->stage_reciprocals);
  release(workspace->gamma_rows);
  release(workspace->G_negative);
  release(workspace->G_positive);
  release(workspace->S_positive);
  release(workspace->products);
  release(workspace->convolutions);
  release(workspace->retained);
  release(workspace->half_spectrum);
  release(workspace->hermi_pre);
  release(workspace->hermi_fft);
  release(workspace->root_center_norms);
  release(workspace->roots);
  release(workspace->samples);
  release(workspace->input_failure_flags);
}

template <typename T>
void allocate(Workspace* workspace, T** pointer, std::uint64_t count) {
  if (count == 0U || count >
                         std::numeric_limits<std::uint64_t>::max() /
                             sizeof(T)) {
    throw std::runtime_error("PT21 DD transform allocation size is invalid");
  }
  CUDA_CHECK(cudaMalloc(pointer, count * sizeof(T)));
  workspace->allocated_bytes += count * sizeof(T);
}

}  // namespace

Workspace* create_source_workspace() {
#ifdef SPARKINTERVAL_REQUIRE_H100_SM90
  cudaDeviceProp properties{};
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
  if (properties.major != 9 || properties.minor != 0 ||
      std::strstr(properties.name, "H100") == nullptr) {
    throw std::runtime_error(
        "strict production target requires an NVIDIA H100 sm_90 device");
  }
#endif
  constexpr std::uint32_t length = platt_windowed::kBucketCount;
  constexpr std::uint32_t stages = platt_windowed::kTaylorTerms;
  constexpr std::uint32_t reduced_length = 2U * length;
  constexpr std::uint64_t row_cells =
      static_cast<std::uint64_t>(stages) * length;

  std::unique_ptr<Workspace> workspace(new Workspace{});
  try {
    const std::vector<DDDisk> two_pi_t = initialize_dd_two_pi_t(length);
    const std::vector<DDDisk> roots =
        initialize_dd_positive_roots(reduced_length);
    const std::vector<DDDisk> reciprocals =
        initialize_dd_stage_reciprocals(stages);
    workspace->reciprocal_length = {
        {std::ldexp(1.0, -static_cast<int>(exact_log2(length))), 0.0},
        {0.0, 0.0},
        0.0};
    workspace->omega = initialize_dd_omega(kSourceSampleCount);

    allocate(workspace.get(), &workspace->two_pi_t, length);
    allocate(workspace.get(), &workspace->stage_reciprocals, stages);
    allocate(workspace.get(), &workspace->gamma_rows, row_cells);
    allocate(workspace.get(), &workspace->G_negative, row_cells);
    allocate(workspace.get(), &workspace->G_positive, row_cells);
    allocate(workspace.get(), &workspace->S_positive, row_cells);
    allocate(workspace.get(), &workspace->products, row_cells);
    allocate(workspace.get(), &workspace->convolutions, row_cells);
    allocate(workspace.get(), &workspace->retained, length / 2U);
    allocate(workspace.get(), &workspace->half_spectrum,
             reduced_length + 1U);
    allocate(workspace.get(), &workspace->hermi_pre, reduced_length);
    allocate(workspace.get(), &workspace->hermi_fft, reduced_length);
    allocate(workspace.get(), &workspace->roots, roots.size());
    allocate(workspace.get(), &workspace->root_center_norms, roots.size());
    allocate(workspace.get(), &workspace->samples, kSourceSampleCount);
    allocate(workspace.get(), &workspace->input_failure_flags, 1U);

    CUDA_CHECK(cudaMemcpy(workspace->two_pi_t, two_pi_t.data(),
                          two_pi_t.size() * sizeof(DDDisk),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->stage_reciprocals, reciprocals.data(),
                          reciprocals.size() * sizeof(DDDisk),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(workspace->roots, roots.data(),
                          roots.size() * sizeof(DDDisk),
                          cudaMemcpyHostToDevice));
    dd_initialize_root_center_norms<<<blocks_for(roots.size()), 256U>>>(
        workspace->roots, workspace->root_center_norms,
        static_cast<std::uint32_t>(roots.size()));
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaMemset(workspace->input_failure_flags, 0,
                          sizeof(*workspace->input_failure_flags)));
    // Callers intentionally use nonblocking streams, which do not inherit
    // legacy-default-stream ordering.  Publish the immutable norm table only
    // after its one-time initialization is complete.
    CUDA_CHECK(cudaDeviceSynchronize());
  } catch (...) {
    cudaError_t ignored = cudaSuccess;
    release_storage(workspace.get(), &ignored);
    throw;
  }
  return workspace.release();
}

void destroy_workspace(Workspace* workspace) {
  if (workspace == nullptr) return;
  cudaError_t first_error = cudaSuccess;
  release_storage(workspace, &first_error);
  delete workspace;
  if (first_error != cudaSuccess) {
    throw std::runtime_error(
        std::string("CUDA error while freeing PT21 DD transform: ") +
        cudaGetErrorString(first_error));
  }
}

void run_source_window(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream) {
  if (workspace == nullptr || deviceGamma0 == nullptr ||
      deviceSknRows == nullptr) {
    throw std::runtime_error("PT21 DD transform received a null device input");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t length = platt_windowed::kBucketCount;
  constexpr std::uint32_t stages = platt_windowed::kTaylorTerms;
  constexpr std::uint32_t reduced_length = 2U * length;
  constexpr std::uint64_t row_cells =
      static_cast<std::uint64_t>(stages) * length;
  const auto* gamma0 = reinterpret_cast<const DDDisk*>(deviceGamma0);
  const auto* skn = reinterpret_cast<const DDDisk*>(deviceSknRows);

  CUDA_CHECK(cudaMemsetAsync(workspace->input_failure_flags, 0,
                             sizeof(*workspace->input_failure_flags), stream));
  dd_build_gamma_rows<<<blocks_for(length), threads, 0U, stream>>>(
      gamma0, workspace->two_pi_t, workspace->stage_reciprocals, length,
      stages, workspace->gamma_rows, workspace->input_failure_flags,
      kQualificationInputFailureGamma);
  dd_copy_add_g_error<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->gamma_rows, workspace->G_positive, row_cells,
      kGTruncationError);
  dd_transform(workspace->G_positive, workspace->G_negative, workspace->roots,
               workspace->root_center_norms, stages, length, reduced_length,
               true, stream);
  dd_postprocess_G<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_negative, length, stages, kGTransformError);
  dd_transform(workspace->G_negative, workspace->G_positive, workspace->roots,
               workspace->root_center_norms, stages, length, reduced_length,
               false, stream);
  dd_transform(skn, workspace->S_positive, workspace->roots,
               workspace->root_center_norms, stages, length, reduced_length,
               false, stream, workspace->input_failure_flags,
               kQualificationInputFailureSkn);
  dd_pointwise_products<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_positive, workspace->S_positive, workspace->products,
      row_cells);
  dd_transform(workspace->products, workspace->convolutions, workspace->roots,
               workspace->root_center_norms, stages, length, reduced_length,
               true, stream);
  dd_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads, 0U,
                                stream>>>(
      workspace->convolutions, workspace->retained, length, stages,
      workspace->reciprocal_length);
  dd_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads, 0U,
                                stream>>>(
      workspace->retained, workspace->half_spectrum, length, kFMaxError,
      kFHatSumError, kTaylorError, kFHatTransformError);
  dd_hermidft_preprocess<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->half_spectrum, workspace->hermi_pre, workspace->roots,
      workspace->root_center_norms, workspace->omega, reduced_length);
  dd_transform(workspace->hermi_pre, workspace->hermi_fft, workspace->roots,
               workspace->root_center_norms, 1U, reduced_length,
               reduced_length, false, stream);
  dd_extract_samples<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->hermi_fft, workspace->samples, reduced_length,
      workspace->input_failure_flags);
  CUDA_CHECK(cudaGetLastError());
}

void run_source_window_tile9_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream) {
  if (workspace == nullptr || deviceGamma0 == nullptr ||
      deviceSknRows == nullptr) {
    throw std::runtime_error(
        "PT21 tile9 qualification received a null device input");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t length = platt_windowed::kBucketCount;
  constexpr std::uint32_t stages = platt_windowed::kTaylorTerms;
  constexpr std::uint32_t reduced_length = 2U * length;
  constexpr std::uint64_t row_cells =
      static_cast<std::uint64_t>(stages) * length;
  const auto* gamma0 = reinterpret_cast<const DDDisk*>(deviceGamma0);
  const auto* skn = reinterpret_cast<const DDDisk*>(deviceSknRows);

  CUDA_CHECK(cudaMemsetAsync(workspace->input_failure_flags, 0,
                             sizeof(*workspace->input_failure_flags), stream));
  dd_build_gamma_rows<<<blocks_for(length), threads, 0U, stream>>>(
      gamma0, workspace->two_pi_t, workspace->stage_reciprocals, length,
      stages, workspace->gamma_rows, workspace->input_failure_flags,
      kQualificationInputFailureGamma);
  dd_copy_add_g_error<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->gamma_rows, workspace->G_positive, row_cells,
      kGTruncationError);
  dd_transform_tile9_qualification(
      workspace->G_positive, workspace->G_negative, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream);
  dd_postprocess_G<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_negative, length, stages, kGTransformError);
  dd_transform_tile9_qualification(
      workspace->G_negative, workspace->G_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream);
  dd_transform_tile9_qualification(
      skn, workspace->S_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags,
      kQualificationInputFailureSkn);
  dd_pointwise_products<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_positive, workspace->S_positive, workspace->products,
      row_cells);
  dd_transform_tile9_qualification(
      workspace->products, workspace->convolutions, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream);
  dd_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads, 0U,
                                stream>>>(
      workspace->convolutions, workspace->retained, length, stages,
      workspace->reciprocal_length);
  dd_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads, 0U,
                                stream>>>(
      workspace->retained, workspace->half_spectrum, length, kFMaxError,
      kFHatSumError, kTaylorError, kFHatTransformError);
  dd_hermidft_preprocess<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->half_spectrum, workspace->hermi_pre, workspace->roots,
      workspace->root_center_norms, workspace->omega, reduced_length);
  dd_transform_tile9_qualification(
      workspace->hermi_pre, workspace->hermi_fft, workspace->roots,
      workspace->root_center_norms, 1U, reduced_length, reduced_length, false,
      stream);
  dd_extract_samples<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->hermi_fft, workspace->samples, reduced_length,
      workspace->input_failure_flags);
  CUDA_CHECK(cudaGetLastError());
}

#if defined(SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION == 1
void run_source_window_sloppy_root_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream) {
  if (workspace == nullptr || deviceGamma0 == nullptr ||
      deviceSknRows == nullptr) {
    throw std::runtime_error(
        "PT21 sloppy-root qualification received a null device input");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t length = platt_windowed::kBucketCount;
  constexpr std::uint32_t stages = platt_windowed::kTaylorTerms;
  constexpr std::uint32_t reduced_length = 2U * length;
  constexpr std::uint64_t row_cells =
      static_cast<std::uint64_t>(stages) * length;
  const auto* gamma0 = reinterpret_cast<const DDDisk*>(deviceGamma0);
  const auto* skn = reinterpret_cast<const DDDisk*>(deviceSknRows);

  CUDA_CHECK(cudaMemsetAsync(workspace->input_failure_flags, 0,
                             sizeof(*workspace->input_failure_flags), stream));
  dd_build_gamma_rows<<<blocks_for(length), threads, 0U, stream>>>(
      gamma0, workspace->two_pi_t, workspace->stage_reciprocals, length,
      stages, workspace->gamma_rows, workspace->input_failure_flags,
      kQualificationInputFailureGamma);
  dd_copy_add_g_error<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->gamma_rows, workspace->G_positive, row_cells,
      kGTruncationError);
  dd_transform_sloppy_root_qualification(
      workspace->G_positive, workspace->G_negative, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream, workspace->input_failure_flags);
  dd_postprocess_G<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_negative, length, stages, kGTransformError);
  dd_transform_sloppy_root_qualification(
      workspace->G_negative, workspace->G_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags);
  dd_transform_sloppy_root_qualification(
      skn, workspace->S_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags,
      workspace->input_failure_flags, kQualificationInputFailureSkn);
  dd_pointwise_products<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_positive, workspace->S_positive, workspace->products,
      row_cells);
  dd_transform_sloppy_root_qualification(
      workspace->products, workspace->convolutions, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream, workspace->input_failure_flags);
  dd_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads, 0U,
                                stream>>>(
      workspace->convolutions, workspace->retained, length, stages,
      workspace->reciprocal_length);
  dd_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads, 0U,
                                stream>>>(
      workspace->retained, workspace->half_spectrum, length, kFMaxError,
      kFHatSumError, kTaylorError, kFHatTransformError);
  dd_hermidft_preprocess_sloppy_root_qualification<<<
      blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->half_spectrum, workspace->hermi_pre, workspace->roots,
      workspace->root_center_norms, workspace->omega, reduced_length,
      workspace->input_failure_flags);
  dd_transform_sloppy_root_qualification(
      workspace->hermi_pre, workspace->hermi_fft, workspace->roots,
      workspace->root_center_norms, 1U, reduced_length, reduced_length,
      false, stream, workspace->input_failure_flags);
  dd_extract_samples<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->hermi_fft, workspace->samples, reduced_length,
      workspace->input_failure_flags);
  CUDA_CHECK(cudaGetLastError());
}

#if defined(SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION == 1
void run_source_window_tile9_sloppy_root_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream) {
  if (workspace == nullptr || deviceGamma0 == nullptr ||
      deviceSknRows == nullptr) {
    throw std::runtime_error(
        "PT21 tile9 sloppy-root qualification received a null device input");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t length = platt_windowed::kBucketCount;
  constexpr std::uint32_t stages = platt_windowed::kTaylorTerms;
  constexpr std::uint32_t reduced_length = 2U * length;
  constexpr std::uint64_t row_cells =
      static_cast<std::uint64_t>(stages) * length;
  const auto* gamma0 = reinterpret_cast<const DDDisk*>(deviceGamma0);
  const auto* skn = reinterpret_cast<const DDDisk*>(deviceSknRows);

  CUDA_CHECK(cudaMemsetAsync(workspace->input_failure_flags, 0,
                             sizeof(*workspace->input_failure_flags), stream));
  dd_build_gamma_rows<<<blocks_for(length), threads, 0U, stream>>>(
      gamma0, workspace->two_pi_t, workspace->stage_reciprocals, length,
      stages, workspace->gamma_rows, workspace->input_failure_flags,
      kQualificationInputFailureGamma);
  dd_copy_add_g_error<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->gamma_rows, workspace->G_positive, row_cells,
      kGTruncationError);
  dd_transform_tile9_sloppy_root_qualification(
      workspace->G_positive, workspace->G_negative, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream, workspace->input_failure_flags);
  dd_postprocess_G<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_negative, length, stages, kGTransformError);
  dd_transform_tile9_sloppy_root_qualification(
      workspace->G_negative, workspace->G_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags);
  dd_transform_tile9_sloppy_root_qualification(
      skn, workspace->S_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags,
      workspace->input_failure_flags, kQualificationInputFailureSkn);
  dd_pointwise_products<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_positive, workspace->S_positive, workspace->products,
      row_cells);
  dd_transform_tile9_sloppy_root_qualification(
      workspace->products, workspace->convolutions, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream, workspace->input_failure_flags);
  dd_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads, 0U,
                                stream>>>(
      workspace->convolutions, workspace->retained, length, stages,
      workspace->reciprocal_length);
  dd_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads, 0U,
                                stream>>>(
      workspace->retained, workspace->half_spectrum, length, kFMaxError,
      kFHatSumError, kTaylorError, kFHatTransformError);
  dd_hermidft_preprocess_sloppy_root_qualification<<<
      blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->half_spectrum, workspace->hermi_pre, workspace->roots,
      workspace->root_center_norms, workspace->omega, reduced_length,
      workspace->input_failure_flags);
  dd_transform_tile9_sloppy_root_qualification(
      workspace->hermi_pre, workspace->hermi_fft, workspace->roots,
      workspace->root_center_norms, 1U, reduced_length, reduced_length,
      false, stream, workspace->input_failure_flags);
  dd_extract_samples<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->hermi_fft, workspace->samples, reduced_length,
      workspace->input_failure_flags);
  CUDA_CHECK(cudaGetLastError());
}

#if defined(SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION) && \
    SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION == 1
void run_source_window_bitreverse_tile9_sloppy_root_qualification(
    Workspace* workspace,
    const platt_windowed::ComplexDisk106* deviceGamma0,
    const platt_windowed::ComplexDisk106* deviceSknRows,
    cudaStream_t stream) {
  if (workspace == nullptr || deviceGamma0 == nullptr ||
      deviceSknRows == nullptr) {
    throw std::runtime_error(
        "PT21 bitreverse-tile9 qualification received a null device input");
  }
  constexpr std::uint32_t threads = 256U;
  constexpr std::uint32_t length = platt_windowed::kBucketCount;
  constexpr std::uint32_t stages = platt_windowed::kTaylorTerms;
  constexpr std::uint32_t reduced_length = 2U * length;
  constexpr std::uint64_t row_cells =
      static_cast<std::uint64_t>(stages) * length;
  const auto* gamma0 = reinterpret_cast<const DDDisk*>(deviceGamma0);
  const auto* skn = reinterpret_cast<const DDDisk*>(deviceSknRows);

  CUDA_CHECK(cudaMemsetAsync(workspace->input_failure_flags, 0,
                             sizeof(*workspace->input_failure_flags), stream));
  dd_build_gamma_rows<<<blocks_for(length), threads, 0U, stream>>>(
      gamma0, workspace->two_pi_t, workspace->stage_reciprocals, length,
      stages, workspace->gamma_rows, workspace->input_failure_flags,
      kQualificationInputFailureGamma);
  dd_copy_add_g_error<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->gamma_rows, workspace->G_positive, row_cells,
      kGTruncationError);
  dd_transform_bitreverse_tile9_sloppy_root_qualification(
      workspace->G_positive, workspace->G_negative, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream, workspace->input_failure_flags);
  dd_postprocess_G<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_negative, length, stages, kGTransformError);
  dd_transform_bitreverse_tile9_sloppy_root_qualification(
      workspace->G_negative, workspace->G_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags);
  dd_transform_bitreverse_tile9_sloppy_root_qualification(
      skn, workspace->S_positive, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, false,
      stream, workspace->input_failure_flags,
      workspace->input_failure_flags, kQualificationInputFailureSkn);
  dd_pointwise_products<<<blocks_for(row_cells), threads, 0U, stream>>>(
      workspace->G_positive, workspace->S_positive, workspace->products,
      row_cells);
  dd_transform_bitreverse_tile9_sloppy_root_qualification(
      workspace->products, workspace->convolutions, workspace->roots,
      workspace->root_center_norms, stages, length, reduced_length, true,
      stream, workspace->input_failure_flags);
  dd_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads, 0U,
                                stream>>>(
      workspace->convolutions, workspace->retained, length, stages,
      workspace->reciprocal_length);
  dd_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads, 0U,
                                stream>>>(
      workspace->retained, workspace->half_spectrum, length, kFMaxError,
      kFHatSumError, kTaylorError, kFHatTransformError);
  dd_hermidft_preprocess_sloppy_root_qualification<<<
      blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->half_spectrum, workspace->hermi_pre, workspace->roots,
      workspace->root_center_norms, workspace->omega, reduced_length,
      workspace->input_failure_flags);
  dd_transform_bitreverse_tile9_sloppy_root_qualification(
      workspace->hermi_pre, workspace->hermi_fft, workspace->roots,
      workspace->root_center_norms, 1U, reduced_length, reduced_length,
      false, stream, workspace->input_failure_flags);
  dd_extract_samples<<<blocks_for(reduced_length), threads, 0U, stream>>>(
      workspace->hermi_fft, workspace->samples, reduced_length,
      workspace->input_failure_flags);
  CUDA_CHECK(cudaGetLastError());
}

QualificationTile9SloppyRootKernelResources
bitreverse_tile9_sloppy_root_kernel_resources_qualification() {
  cudaFuncAttributes attributes{};
  CUDA_CHECK(cudaFuncGetAttributes(
      &attributes,
      dd_bit_reverse_and_radix2_stages_1_through_9_tile_sloppy_root_qualification));
  int active_blocks = 0;
  CUDA_CHECK(cudaOccupancyMaxActiveBlocksPerMultiprocessor(
      &active_blocks,
      dd_bit_reverse_and_radix2_stages_1_through_9_tile_sloppy_root_qualification,
      kQualificationTile9SloppyRootThreadsPerBlock, 0U));
  return {
      .registers_per_thread = attributes.numRegs,
      .static_shared_bytes = attributes.sharedSizeBytes,
      .local_bytes_per_thread = attributes.localSizeBytes,
      .maximum_threads_per_block = attributes.maxThreadsPerBlock,
      .active_blocks_per_multiprocessor = active_blocks,
  };
}
#endif

QualificationTile9SloppyRootKernelResources
tile9_sloppy_root_kernel_resources_qualification() {
  cudaFuncAttributes attributes{};
  CUDA_CHECK(cudaFuncGetAttributes(
      &attributes,
      dd_radix2_stages_1_through_9_tile_sloppy_root_qualification));
  int active_blocks = 0;
  CUDA_CHECK(cudaOccupancyMaxActiveBlocksPerMultiprocessor(
      &active_blocks,
      dd_radix2_stages_1_through_9_tile_sloppy_root_qualification,
      kQualificationTile9SloppyRootThreadsPerBlock, 0U));
  return {
      .registers_per_thread = attributes.numRegs,
      .static_shared_bytes = attributes.sharedSizeBytes,
      .local_bytes_per_thread = attributes.localSizeBytes,
      .maximum_threads_per_block = attributes.maxThreadsPerBlock,
      .active_blocks_per_multiprocessor = active_blocks,
  };
}
#endif

QualificationRootTableView device_root_table_qualification(
    const Workspace* workspace) {
  if (workspace == nullptr) return {};
  constexpr std::uint32_t count = platt_windowed::kBucketCount;
  return {
      .roots =
          reinterpret_cast<const platt_windowed::ComplexDisk106*>(
              workspace->roots),
      .center_norm_upper = workspace->root_center_norms,
      .count = count,
  };
}
#endif

const platt_windowed::RealDisk106* device_samples(
    const Workspace* workspace) {
  if (workspace == nullptr) return nullptr;
  return reinterpret_cast<const platt_windowed::RealDisk106*>(
      workspace->samples);
}

const platt_windowed::RealDisk106* device_required_samples(
    const Workspace* workspace) {
  const platt_windowed::RealDisk106* samples = device_samples(workspace);
  return samples == nullptr ? nullptr : samples + kSourceRequiredBegin;
}

const std::uint32_t* device_input_failure_flags_qualification(
    const Workspace* workspace) {
  return workspace == nullptr ? nullptr : workspace->input_failure_flags;
}

std::uint32_t qualification_required_begin_for_delta(
    std::int32_t logical_block_delta) {
  const std::int64_t begin =
      static_cast<std::int64_t>(kSourceRequiredBegin) +
      static_cast<std::int64_t>(logical_block_delta) *
          static_cast<std::int64_t>(kSourceBlockSampleShift);
  const std::int64_t end =
      begin + static_cast<std::int64_t>(kSourceRequiredCount);
  if (begin < 0 ||
      end > static_cast<std::int64_t>(kSourceSampleCount)) {
    throw std::out_of_range(
        "qualification shifted required view leaves transform allocation");
  }
  return static_cast<std::uint32_t>(begin);
}

QualificationRequiredSampleView device_qualification_required_samples(
    const Workspace* workspace, std::int32_t logical_block_delta) {
  const platt_windowed::RealDisk106* samples = device_samples(workspace);
  if (samples == nullptr) {
    throw std::invalid_argument(
        "null transform workspace for qualification shifted view");
  }
  const std::uint32_t begin =
      qualification_required_begin_for_delta(logical_block_delta);
  return {
      .samples = samples + begin,
      .begin = begin,
      .count = kSourceRequiredCount,
      .logical_block_delta = logical_block_delta,
  };
}

std::uint64_t workspace_device_bytes(const Workspace* workspace) {
  return workspace == nullptr ? 0U : workspace->allocated_bytes;
}

}  // namespace sparkinterval::tg::platt_dd_transform

#ifndef SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN
int main(int argc, char** argv) {
  try {
    return run_dd_disk_semantic(parse_dd_disk_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-windowed-dd-disk-semantic: "
              << error.what() << '\n';
    return 2;
  }
}
#endif

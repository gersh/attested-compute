// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Binary64 complex-disk prototype for the source-semantic transform in
// h100_tg_platt_windowed_semantic.cu.  This file includes that implementation
// under a renamed main solely to reuse its exact source parameters, MPFR root
// construction, synthetic inputs, and independent long-double KAT.  The GPU
// dataflow below is separate and uses center+radius disks throughout.

#include "sparkinterval/tg_dirichlet_booker_smallq_certified.hpp"
#include "sparkinterval/sha256.hpp"

#include <bit>
#include <fstream>
#include <numeric>

#define main sparkinterval_platt_box_reference_main
#include "h100_tg_platt_windowed_semantic.cu"
#undef main

namespace {

namespace sc = sparkinterval::tg::dirichlet_booker_smallq_certified;

using Disk = sc::Disk;

struct DiskOptions : Options {
  std::string source_packet;
  std::string endpoint_certificate;
  bool require_unambiguous = false;
  bool require_full_source_packet = false;
};

DiskOptions parse_disk_options(int argc, char** argv) {
  std::vector<char*> base_argv;
  base_argv.reserve(static_cast<std::size_t>(argc));
  base_argv.push_back(argv[0]);
  DiskOptions result;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    constexpr std::string_view packet_prefix = "--source-packet=";
    constexpr std::string_view certificate_prefix =
        "--endpoint-certificate=";
    if (argument.rfind(packet_prefix, 0) == 0) {
      result.source_packet = argument.substr(packet_prefix.size());
      if (result.source_packet.empty()) {
        throw std::runtime_error("source packet path is empty");
      }
    } else if (argument.rfind(certificate_prefix, 0) == 0) {
      result.endpoint_certificate =
          argument.substr(certificate_prefix.size());
      if (result.endpoint_certificate.empty()) {
        throw std::runtime_error("endpoint certificate path is empty");
      }
    } else if (argument == "--require-unambiguous") {
      result.require_unambiguous = true;
    } else if (argument == "--require-full-source-packet") {
      result.require_full_source_packet = true;
    } else {
      base_argv.push_back(argv[index]);
    }
  }
  static_cast<Options&>(result) =
      parse_options(static_cast<int>(base_argv.size()), base_argv.data());
  if (!result.source_packet.empty()) {
    result.source_shape = true;
    result.source_errors = true;
    result.convolution_length = pw::kBucketCount;
    result.taylor_terms = pw::kTaylorTerms;
  }
  if (result.require_full_source_packet && result.source_packet.empty()) {
    throw std::runtime_error(
        "--require-full-source-packet requires --source-packet");
  }
  return result;
}

struct RealDisk {
  double center;
  double radius;
};

struct HermidftEndpointTrace {
  Disk left_input;
  Disk right_input;
  Disk left_projection;
  Disk right_projection;
  Disk left_product;
  Disk right_product;
  Disk output;
};

static_assert(sizeof(Disk) == 24U);
static_assert(sizeof(RealDisk) == 16U);

std::uint64_t fnv1a_bytes(const void* raw, std::size_t size) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = static_cast<const unsigned char*>(raw);
  for (std::size_t index = 0; index < size; ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

struct LoadedSourcePacket {
  HostInputs inputs;
  std::string sha256;
  std::uint32_t source_terms;
  std::uint64_t bytes;
  bool complete_terms;
};

LoadedSourcePacket load_source_packet(const std::string& path) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "PT21 source packet import requires a little-endian host");
  }
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open PT21 source packet");
  const std::streampos end = input.tellg();
  if (end < 0 || static_cast<std::uint64_t>(end) >
                     std::numeric_limits<std::size_t>::max()) {
    throw std::runtime_error("PT21 source packet has invalid file size");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  if (!input || input.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("cannot read complete PT21 source packet");
  }
  if (bytes.size() < sizeof(pw::SourcePacketHeader)) {
    throw std::runtime_error("PT21 source packet is truncated before header");
  }
  pw::SourcePacketHeader header{};
  std::memcpy(&header, bytes.data(), sizeof(header));
  if (header.magic != pw::kSourcePacketMagic ||
      header.version != pw::kSourcePacketVersion ||
      header.header_bytes != sizeof(header) ||
      header.endian_tag != pw::kSourcePacketEndianTag ||
      header.interval_encoding != pw::kSourcePacketIntervalEncoding ||
      header.bucket_count != pw::kBucketCount ||
      header.taylor_terms != pw::kTaylorTerms ||
      header.reserved_zero != 0U ||
      header.window_center != pw::kSourceLower + pw::kWindowStep / 2U ||
      header.gamma_count != pw::kBucketCount ||
      header.skn_count !=
          static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount ||
      header.source_terms == 0U || header.source_terms > pw::kSourceTerms ||
      std::memcmp(header.upstream_commit.data(), pw::kUpstreamCommit,
                  header.upstream_commit.size()) != 0) {
    throw std::runtime_error("PT21 source packet header is not the fixed schema");
  }
  const std::uint64_t expected_payload =
      (header.gamma_count + header.skn_count) * sizeof(ComplexInterval);
  if (header.payload_bytes != expected_payload ||
      bytes.size() != sizeof(header) + expected_payload) {
    throw std::runtime_error("PT21 source packet payload size is not exact");
  }

  LoadedSourcePacket result{};
  result.inputs.gamma0.resize(header.gamma_count);
  result.inputs.two_pi_t.resize(pw::kBucketCount);
  result.inputs.skn_rows.resize(header.skn_count);
  std::size_t offset = sizeof(header);
  const std::size_t gamma_bytes =
      result.inputs.gamma0.size() * sizeof(ComplexInterval);
  std::memcpy(result.inputs.gamma0.data(), bytes.data() + offset, gamma_bytes);
  offset += gamma_bytes;
  const std::size_t skn_bytes =
      result.inputs.skn_rows.size() * sizeof(ComplexInterval);
  std::memcpy(result.inputs.skn_rows.data(), bytes.data() + offset, skn_bytes);
  if (fnv1a_bytes(result.inputs.gamma0.data(), gamma_bytes) !=
          header.gamma_fnv1a64 ||
      fnv1a_bytes(result.inputs.skn_rows.data(), skn_bytes) !=
          header.skn_fnv1a64) {
    throw std::runtime_error("PT21 source packet payload checksum mismatch");
  }
  auto require_interval = [](RealInterval interval) {
    return std::isfinite(interval.lo) && std::isfinite(interval.hi) &&
           interval.lo <= interval.hi;
  };
  for (const ComplexInterval value : result.inputs.gamma0) {
    if (!require_interval(value.re) || !require_interval(value.im)) {
      throw std::runtime_error("PT21 Gamma packet contains an invalid interval");
    }
  }
  for (const ComplexInterval value : result.inputs.skn_rows) {
    if (!require_interval(value.re) || !require_interval(value.im)) {
      throw std::runtime_error("PT21 skn packet contains an invalid interval");
    }
  }
  for (std::uint32_t index = 0; index < pw::kBucketCount; ++index) {
    result.inputs.two_pi_t[index] = source_two_pi_t(index, pw::kBucketCount);
  }
  result.sha256 = sparkinterval::sha256_hex(bytes.data(), bytes.size());
  result.source_terms = header.source_terms;
  result.bytes = bytes.size();
  result.complete_terms = header.source_terms == pw::kSourceTerms;
  return result;
}

// Convert a host MPFR rectangle to one Euclidean disk.  The center is an
// ordinary binary64 midpoint; MPFR bounds every endpoint-to-center distance
// and the final hypotenuse upward.
Disk box_to_disk(ComplexInterval box) {
  const double center_re = std::midpoint(box.re.lo, box.re.hi);
  const double center_im = std::midpoint(box.im.lo, box.im.hi);
  MpfrValue dx0, dx1, dy0, dy1, dx, dy, radius;
  mpfr_set_d(dx0.value, center_re, MPFR_RNDN);
  mpfr_sub_d(dx0.value, dx0.value, box.re.lo, MPFR_RNDU);
  mpfr_abs(dx0.value, dx0.value, MPFR_RNDU);
  mpfr_set_d(dx1.value, box.re.hi, MPFR_RNDN);
  mpfr_sub_d(dx1.value, dx1.value, center_re, MPFR_RNDU);
  mpfr_abs(dx1.value, dx1.value, MPFR_RNDU);
  mpfr_max(dx.value, dx0.value, dx1.value, MPFR_RNDU);
  mpfr_set_d(dy0.value, center_im, MPFR_RNDN);
  mpfr_sub_d(dy0.value, dy0.value, box.im.lo, MPFR_RNDU);
  mpfr_abs(dy0.value, dy0.value, MPFR_RNDU);
  mpfr_set_d(dy1.value, box.im.hi, MPFR_RNDN);
  mpfr_sub_d(dy1.value, dy1.value, center_im, MPFR_RNDU);
  mpfr_abs(dy1.value, dy1.value, MPFR_RNDU);
  mpfr_max(dy.value, dy0.value, dy1.value, MPFR_RNDU);
  mpfr_mul(radius.value, dx.value, dx.value, MPFR_RNDU);
  mpfr_fma(radius.value, dy.value, dy.value, radius.value, MPFR_RNDU);
  mpfr_sqrt(radius.value, radius.value, MPFR_RNDU);
  return {center_re, center_im, mpfr_get_d(radius.value, MPFR_RNDU)};
}

Disk real_box_to_disk(RealInterval box) {
  return box_to_disk({box, {0.0, 0.0}});
}

std::vector<Disk> boxes_to_disks(const std::vector<ComplexInterval>& boxes) {
  std::vector<Disk> result;
  result.reserve(boxes.size());
  for (const ComplexInterval box : boxes) result.push_back(box_to_disk(box));
  return result;
}

std::vector<Disk> real_boxes_to_disks(const std::vector<RealInterval>& boxes) {
  std::vector<Disk> result;
  result.reserve(boxes.size());
  for (const RealInterval box : boxes) result.push_back(real_box_to_disk(box));
  return result;
}

// Stable upward Euclidean norm.  Scaling avoids the catastrophic underflow
// of sqrt(x*x+y*y) for the source's 1e-307 error disks and avoids overflow for
// large intermediate centers.
__device__ __forceinline__ double disk_norm_upper(double re, double im) {
  double large = fmax(fabs(re), fabs(im));
  double small = fmin(fabs(re), fabs(im));
  if (large == 0.0) return 0.0;
  const double ratio = __ddiv_ru(small, large);
  const double square = __dadd_ru(1.0, __dmul_ru(ratio, ratio));
  return __dmul_ru(large, __dsqrt_ru(square));
}

__device__ __forceinline__ double disk_coordinate_error(
    double center, double lo, double hi) {
  return fmax(__dsub_ru(center, lo), __dsub_ru(hi, center));
}

// These are the CUDA refinements of ComplexDisk.AddCertificate and
// ComplexDisk.MulCertificate.  A production trace exporter must emit the
// decoded operands/results plus the four norm/error witnesses so Lean can
// replay their exact rational inequalities; this prototype benchmarks the
// physical producer but does not treat a CUDA execution as a Lean proof.
__device__ __forceinline__ Disk disk_add(Disk x, Disk y) {
  const double lo_re = __dadd_rd(x.real, y.real);
  const double hi_re = __dadd_ru(x.real, y.real);
  const double lo_im = __dadd_rd(x.imaginary, y.imaginary);
  const double hi_im = __dadd_ru(x.imaginary, y.imaginary);
  const double re = __dadd_rn(x.real, y.real);
  const double im = __dadd_rn(x.imaginary, y.imaginary);
  const double er = disk_coordinate_error(re, lo_re, hi_re);
  const double ei = disk_coordinate_error(im, lo_im, hi_im);
  const double rounding = disk_norm_upper(er, ei);
  return {re, im, __dadd_ru(__dadd_ru(x.radius, y.radius), rounding)};
}

__device__ __forceinline__ Disk disk_negate(Disk x) {
  return {-x.real, -x.imaginary, x.radius};
}

__device__ __forceinline__ Disk disk_sub(Disk x, Disk y) {
  return disk_add(x, disk_negate(y));
}

__device__ __forceinline__ Disk disk_conjugate(Disk x) {
  return {x.real, -x.imaginary, x.radius};
}

__device__ __forceinline__ Disk disk_times_i(Disk x) {
  return {-x.imaginary, x.real, x.radius};
}

__device__ __forceinline__ Disk disk_mul(Disk x, Disk y) {
  const double xryr_lo = __dmul_rd(x.real, y.real);
  const double xryr_hi = __dmul_ru(x.real, y.real);
  const double xiyi_lo = __dmul_rd(x.imaginary, y.imaginary);
  const double xiyi_hi = __dmul_ru(x.imaginary, y.imaginary);
  const double xryi_lo = __dmul_rd(x.real, y.imaginary);
  const double xryi_hi = __dmul_ru(x.real, y.imaginary);
  const double xiyr_lo = __dmul_rd(x.imaginary, y.real);
  const double xiyr_hi = __dmul_ru(x.imaginary, y.real);
  const double lo_re = __dsub_rd(xryr_lo, xiyi_hi);
  const double hi_re = __dsub_ru(xryr_hi, xiyi_lo);
  const double lo_im = __dadd_rd(xryi_lo, xiyr_lo);
  const double hi_im = __dadd_ru(xryi_hi, xiyr_hi);
  const double re = fma(x.real, y.real, -x.imaginary * y.imaginary);
  const double im = fma(x.real, y.imaginary, x.imaginary * y.real);
  const double er = disk_coordinate_error(re, lo_re, hi_re);
  const double ei = disk_coordinate_error(im, lo_im, hi_im);
  const double rounding = disk_norm_upper(er, ei);
  const double nx = disk_norm_upper(x.real, x.imaginary);
  const double ny = disk_norm_upper(y.real, y.imaginary);
  double radius = __dadd_ru(rounding, __dmul_ru(nx, y.radius));
  radius = __dadd_ru(radius, __dmul_ru(ny, x.radius));
  radius = __dadd_ru(radius, __dmul_ru(x.radius, y.radius));
  return {re, im, radius};
}

__device__ __forceinline__ Disk disk_add_square_error(Disk value,
                                                       double error) {
  // The source widens both Cartesian coordinates by error, so the enclosing
  // Euclidean disk grows by sqrt(error^2+error^2).
  return {value.real, value.imaginary,
          __dadd_ru(value.radius, disk_norm_upper(error, error))};
}

__device__ __forceinline__ Disk disk_real_projection(Disk value) {
  return {value.real, 0.0, value.radius};
}

__global__ void disk_build_gamma_rows(
    const Disk* gamma0, const Disk* two_pi_t,
    const Disk* stage_reciprocals, std::uint32_t length,
    std::uint32_t stages, Disk* rows) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < length; index += blockDim.x * gridDim.x) {
    Disk value = gamma0[index];
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      rows[static_cast<std::uint64_t>(stage) * length + index] = value;
      if (stage + 1U != stages) {
        value = disk_mul(disk_times_i(value), two_pi_t[index]);
        value = disk_mul(value, stage_reciprocals[stage]);
      }
    }
  }
}

__global__ void disk_copy_add_g_error(const Disk* input, Disk* output,
                                      std::uint64_t count, double error) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    output[index] = disk_add_square_error(input[index], error);
  }
}

__global__ void disk_bit_reverse_lines(
    const Disk* input, Disk* output, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t log_length) {
  const std::uint64_t count =
      static_cast<std::uint64_t>(lines) * transform_length;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t position =
        static_cast<std::uint32_t>(flat % transform_length);
    const std::uint32_t reversed = __brev(position) >> (32U - log_length);
    const std::uint64_t line = flat / transform_length;
    output[line * transform_length + reversed] = input[flat];
  }
}

__global__ void disk_radix2_stage(
    Disk* values, const Disk* positive_roots, std::uint32_t lines,
    std::uint32_t transform_length, std::uint32_t maximum_length,
    std::uint32_t stage_length, bool negative_sign) {
  const std::uint64_t butterflies =
      static_cast<std::uint64_t>(lines) * transform_length / 2U;
  const std::uint32_t half = stage_length / 2U;
  const std::uint32_t root_stride = maximum_length / stage_length;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < butterflies;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint64_t line = flat / (transform_length / 2U);
    const std::uint64_t local = flat % (transform_length / 2U);
    const std::uint64_t group = local / half;
    const std::uint32_t offset = static_cast<std::uint32_t>(local % half);
    const std::uint64_t left =
        line * transform_length + group * stage_length + offset;
    const std::uint64_t right = left + half;
    Disk root = positive_roots[offset * root_stride];
    if (negative_sign) root = disk_conjugate(root);
    const Disk first = values[left];
    const Disk second = disk_mul(values[right], root);
    values[left] = disk_add(first, second);
    values[right] = disk_sub(first, second);
  }
}

__global__ void disk_postprocess_G(Disk* rows, std::uint32_t length,
                                   std::uint32_t stages,
                                   double transform_error) {
  const std::uint64_t count = static_cast<std::uint64_t>(stages) * length;
  const Disk inverse_A1{21.0 / 128.0, 0.0, 0.0};
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t index = static_cast<std::uint32_t>(flat % length);
    if (index > length / 2U) {
      rows[flat] = {0.0, 0.0, 0.0};
      continue;
    }
    Disk value = disk_mul(rows[flat], inverse_A1);
    value = disk_add_square_error(value, transform_error);
    rows[flat] = (index & 1U) != 0U ? disk_negate(value) : value;
  }
}

__global__ void disk_pointwise_products(const Disk* left, const Disk* right,
                                        Disk* output, std::uint64_t count) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    output[index] = disk_mul(left[index], right[index]);
  }
}

__global__ void disk_normalize_and_taylor_sum(
    const Disk* rows, Disk* retained, std::uint32_t length,
    std::uint32_t stages, Disk reciprocal_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < length / 2U; index += blockDim.x * gridDim.x) {
    Disk sum{0.0, 0.0, 0.0};
    for (std::uint32_t stage = 0; stage < stages; ++stage) {
      sum = disk_add(sum, disk_mul(
          rows[static_cast<std::uint64_t>(stage) * length + index],
          reciprocal_length));
    }
    retained[index] = sum;
  }
}

__global__ void disk_initialize_half_spectrum(
    const Disk* retained, Disk* half_spectrum,
    std::uint32_t convolution_length, double fmax_error,
    double fhatsum_error, double taylor_error, double transform_error) {
  const std::uint32_t reduced_length = 2U * convolution_length;
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index <= reduced_length; index += blockDim.x * gridDim.x) {
    Disk value = index < convolution_length / 2U
        ? retained[index]
        : Disk{0.0, 0.0, disk_norm_upper(fmax_error, fmax_error)};
    value = disk_add_square_error(value, fhatsum_error);
    value = disk_add_square_error(value, taylor_error);
    value = disk_add_square_error(value, transform_error);
    half_spectrum[index] =
        (index & 1U) != 0U ? disk_negate(value) : value;
  }
}

__global__ void disk_hermidft_preprocess(
    const Disk* half_spectrum, Disk* reduced, const Disk* roots,
    Disk omega, std::uint32_t reduced_length,
    HermidftEndpointTrace* endpoint_trace) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    if (index == 0U) {
      // (Re x0 + Re xN) + i (Re x0 - Re xN), expressed through ordinary
      // disk multiplication/addition so the same Lean Mul/Add certificates
      // cover the exceptional endpoint.
      const Disk left_input = half_spectrum[0];
      const Disk right_input = half_spectrum[reduced_length];
      const Disk left_projection = disk_real_projection(left_input);
      const Disk right_projection = disk_real_projection(right_input);
      const Disk left = disk_mul(left_projection, {1.0, 1.0, 0.0});
      const Disk right = disk_mul(right_projection, {1.0, -1.0, 0.0});
      const Disk output = disk_add(left, right);
      reduced[0] = output;
      if (endpoint_trace != nullptr) {
        *endpoint_trace = {left_input, right_input, left_projection,
                           right_projection, left, right, output};
      }
      continue;
    }
    const Disk mirror =
        disk_conjugate(half_spectrum[reduced_length - index]);
    const Disk pair_sum = disk_add(mirror, half_spectrum[index]);
    Disk pair_difference =
        disk_times_i(disk_sub(half_spectrum[index], mirror));
    pair_difference = disk_mul(pair_difference, roots[index / 2U]);
    if ((index & 1U) != 0U) {
      pair_difference = disk_mul(pair_difference, omega);
    }
    reduced[index] = disk_add(pair_difference, pair_sum);
  }
}

__global__ void disk_extract_samples(const Disk* reduced, RealDisk* samples,
                                     std::uint32_t reduced_length) {
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index < reduced_length; index += blockDim.x * gridDim.x) {
    samples[2U * index] = {reduced[index].real, reduced[index].radius};
    samples[2U * index + 1U] =
        {reduced[index].imaginary, reduced[index].radius};
  }
}

void disk_transform(const Disk* input, Disk* output, const Disk* roots,
                    std::uint32_t lines, std::uint32_t length,
                    std::uint32_t maximum_length, bool negative_sign) {
  constexpr std::uint32_t threads = 256U;
  const std::uint64_t cells = static_cast<std::uint64_t>(lines) * length;
  disk_bit_reverse_lines<<<blocks_for(cells), threads>>>(
      input, output, lines, length, exact_log2(length));
  for (std::uint32_t stage_length = 2U; stage_length <= length;
       stage_length <<= 1U) {
    disk_radix2_stage<<<blocks_for(cells / 2U), threads>>>(
        output, roots, lines, length, maximum_length, stage_length,
        negative_sign);
  }
}

std::uint64_t disk_fnv1a(const std::vector<RealDisk>& values) {
  std::uint64_t hash = 1469598103934665603ULL;
  const auto* bytes = reinterpret_cast<const unsigned char*>(values.data());
  for (std::size_t index = 0; index < values.size() * sizeof(RealDisk);
       ++index) {
    hash ^= bytes[index];
    hash *= 1099511628211ULL;
  }
  return hash;
}

double canonical_binary64(double value) {
  return value == 0.0 ? 0.0 : value;
}

double mpfr_hypot_upper(double re, double im) {
  MpfrValue x, y, square;
  mpfr_set_d(x.value, re, MPFR_RNDN);
  mpfr_set_d(y.value, im, MPFR_RNDN);
  mpfr_mul(square.value, x.value, x.value, MPFR_RNDU);
  mpfr_fma(square.value, y.value, y.value, square.value, MPFR_RNDU);
  mpfr_sqrt(square.value, square.value, MPFR_RNDU);
  return canonical_binary64(mpfr_get_d(square.value, MPFR_RNDU));
}

double mpfr_mul_center_error_upper(Disk left, Disk right, Disk output) {
  MpfrValue lr, li, rr, ri, out_re, out_im;
  MpfrValue first, second, delta_re, delta_im, square;
  mpfr_set_d(lr.value, left.real, MPFR_RNDN);
  mpfr_set_d(li.value, left.imaginary, MPFR_RNDN);
  mpfr_set_d(rr.value, right.real, MPFR_RNDN);
  mpfr_set_d(ri.value, right.imaginary, MPFR_RNDN);
  mpfr_set_d(out_re.value, output.real, MPFR_RNDN);
  mpfr_set_d(out_im.value, output.imaginary, MPFR_RNDN);
  mpfr_mul(first.value, lr.value, rr.value, MPFR_RNDN);
  mpfr_mul(second.value, li.value, ri.value, MPFR_RNDN);
  mpfr_sub(delta_re.value, first.value, second.value, MPFR_RNDN);
  mpfr_sub(delta_re.value, delta_re.value, out_re.value, MPFR_RNDN);
  mpfr_mul(first.value, lr.value, ri.value, MPFR_RNDN);
  mpfr_mul(second.value, li.value, rr.value, MPFR_RNDN);
  mpfr_add(delta_im.value, first.value, second.value, MPFR_RNDN);
  mpfr_sub(delta_im.value, delta_im.value, out_im.value, MPFR_RNDN);
  mpfr_mul(square.value, delta_re.value, delta_re.value, MPFR_RNDU);
  mpfr_fma(square.value, delta_im.value, delta_im.value, square.value,
           MPFR_RNDU);
  mpfr_sqrt(square.value, square.value, MPFR_RNDU);
  return canonical_binary64(mpfr_get_d(square.value, MPFR_RNDU));
}

double mpfr_add_center_error_upper(Disk left, Disk right, Disk output) {
  MpfrValue lr, li, rr, ri, out_re, out_im;
  MpfrValue delta_re, delta_im, square;
  mpfr_set_d(lr.value, left.real, MPFR_RNDN);
  mpfr_set_d(li.value, left.imaginary, MPFR_RNDN);
  mpfr_set_d(rr.value, right.real, MPFR_RNDN);
  mpfr_set_d(ri.value, right.imaginary, MPFR_RNDN);
  mpfr_set_d(out_re.value, output.real, MPFR_RNDN);
  mpfr_set_d(out_im.value, output.imaginary, MPFR_RNDN);
  mpfr_add(delta_re.value, lr.value, rr.value, MPFR_RNDN);
  mpfr_sub(delta_re.value, delta_re.value, out_re.value, MPFR_RNDN);
  mpfr_add(delta_im.value, li.value, ri.value, MPFR_RNDN);
  mpfr_sub(delta_im.value, delta_im.value, out_im.value, MPFR_RNDN);
  mpfr_mul(square.value, delta_re.value, delta_re.value, MPFR_RNDU);
  mpfr_fma(square.value, delta_im.value, delta_im.value, square.value,
           MPFR_RNDU);
  mpfr_sqrt(square.value, square.value, MPFR_RNDU);
  return canonical_binary64(mpfr_get_d(square.value, MPFR_RNDU));
}

void append_binary64_le(std::vector<unsigned char>* output, double value) {
  const std::uint64_t word =
      std::bit_cast<std::uint64_t>(canonical_binary64(value));
  for (unsigned shift = 0U; shift < 64U; shift += 8U) {
    output->push_back(static_cast<unsigned char>(word >> shift));
  }
}

void append_disk(std::vector<unsigned char>* output, Disk disk) {
  append_binary64_le(output, disk.real);
  append_binary64_le(output, disk.imaginary);
  append_binary64_le(output, disk.radius);
}

void append_mul_certificate(std::vector<unsigned char>* output, Disk left,
                            Disk right, Disk product) {
  append_disk(output, left);
  append_disk(output, right);
  append_disk(output, product);
  append_binary64_le(output,
                     mpfr_mul_center_error_upper(left, right, product));
  append_binary64_le(output,
                     mpfr_hypot_upper(left.real, left.imaginary));
  append_binary64_le(output,
                     mpfr_hypot_upper(right.real, right.imaginary));
}

void append_add_certificate(std::vector<unsigned char>* output, Disk left,
                            Disk right, Disk sum) {
  append_disk(output, left);
  append_disk(output, right);
  append_disk(output, sum);
  append_binary64_le(output,
                     mpfr_add_center_error_upper(left, right, sum));
}

struct EndpointCertificateExport {
  std::string sha256;
  std::uint64_t bytes;
};

EndpointCertificateExport write_endpoint_certificate(
    const std::string& path, const HermidftEndpointTrace& trace) {
  if constexpr (std::endian::native != std::endian::little) {
    throw std::runtime_error(
        "endpoint certificate export requires a little-endian host");
  }
  constexpr std::size_t kEndpointCertificateBytes = 320U;
  const Disk one_plus_i{1.0, 1.0, 0.0};
  const Disk one_minus_i{1.0, -1.0, 0.0};
  std::vector<unsigned char> bytes;
  bytes.reserve(kEndpointCertificateBytes);
  append_disk(&bytes, trace.left_input);
  append_disk(&bytes, trace.right_input);
  append_mul_certificate(&bytes, trace.left_projection, one_plus_i,
                         trace.left_product);
  append_mul_certificate(&bytes, trace.right_projection, one_minus_i,
                         trace.right_product);
  append_add_certificate(&bytes, trace.left_product, trace.right_product,
                         trace.output);
  if (bytes.size() != kEndpointCertificateBytes) {
    throw std::runtime_error(
        "endpoint certificate byte accounting is not the Lean wire schema");
  }
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) throw std::runtime_error("cannot open endpoint certificate");
  output.write(reinterpret_cast<const char*>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  output.close();
  if (!output) throw std::runtime_error("cannot write endpoint certificate");
  return {sparkinterval::sha256_hex(bytes.data(), bytes.size()), bytes.size()};
}

int run_disk_semantic(const DiskOptions& options) {
  constexpr std::uint32_t threads = 256U;
  const std::uint32_t length = options.convolution_length;
  const std::uint32_t stages = options.taylor_terms;
  const std::uint32_t reduced_length = 2U * length;
  const std::uint32_t sample_count = 2U * reduced_length;
  const std::uint64_t row_cells = static_cast<std::uint64_t>(stages) * length;

  const bool packet_supplied = !options.source_packet.empty();
  LoadedSourcePacket loaded_packet{};
  HostInputs box_host;
  if (packet_supplied) {
    loaded_packet = load_source_packet(options.source_packet);
    if (options.require_full_source_packet && !loaded_packet.complete_terms) {
      throw std::runtime_error(
          "source packet is partial but complete source terms were required");
    }
    box_host = std::move(loaded_packet.inputs);
  } else {
    box_host = initialize_inputs(options);
  }
  const std::vector<Disk> gamma0 = boxes_to_disks(box_host.gamma0);
  const std::vector<Disk> two_pi_t = real_boxes_to_disks(box_host.two_pi_t);
  const std::vector<Disk> skn_rows = boxes_to_disks(box_host.skn_rows);
  const std::vector<Disk> roots = boxes_to_disks(
      initialize_positive_roots(reduced_length));
  const std::vector<Disk> stage_reciprocals = real_boxes_to_disks(
      initialize_stage_reciprocals(stages));
  const Disk reciprocal_length{
      std::ldexp(1.0, -static_cast<int>(exact_log2(length))), 0.0, 0.0};
  const Disk omega = box_to_disk(initialize_omega(sample_count));

  cudaDeviceProp properties{};
  int device = 0;
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&properties, device));

  Disk *d_gamma0 = nullptr, *d_two_pi_t = nullptr;
  Disk *d_stage_reciprocals = nullptr, *d_skn = nullptr;
  Disk *d_gamma_rows = nullptr, *d_G_negative = nullptr;
  Disk *d_G_positive = nullptr, *d_S_positive = nullptr;
  Disk *d_products = nullptr, *d_convolutions = nullptr;
  Disk *d_retained = nullptr, *d_half_spectrum = nullptr;
  Disk *d_hermi_pre = nullptr, *d_hermi_fft = nullptr, *d_roots = nullptr;
  RealDisk* d_samples = nullptr;
  HermidftEndpointTrace* d_endpoint_trace = nullptr;

  CUDA_CHECK(cudaMalloc(&d_gamma0, length * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_two_pi_t, length * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_stage_reciprocals, stages * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_skn, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_gamma_rows, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_G_negative, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_G_positive, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_S_positive, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_products, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_convolutions, row_cells * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_retained, (length / 2U) * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_half_spectrum,
                        (reduced_length + 1U) * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_hermi_pre, reduced_length * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_hermi_fft, reduced_length * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_roots, roots.size() * sizeof(Disk)));
  CUDA_CHECK(cudaMalloc(&d_samples, sample_count * sizeof(RealDisk)));
  CUDA_CHECK(cudaMalloc(&d_endpoint_trace, sizeof(HermidftEndpointTrace)));

  CUDA_CHECK(cudaMemcpy(d_gamma0, gamma0.data(), length * sizeof(Disk),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_two_pi_t, two_pi_t.data(), length * sizeof(Disk),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_stage_reciprocals, stage_reciprocals.data(),
                        stages * sizeof(Disk), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_skn, skn_rows.data(), row_cells * sizeof(Disk),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots, roots.data(), roots.size() * sizeof(Disk),
                        cudaMemcpyHostToDevice));

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
    // Exact source dataflow: G_k recurrence, negative transform and
    // postprocess; two positive convolution transforms, pointwise product,
    // negative inverse and Taylor sum; source half-spectrum errors;
    // literal hermidft preprocessing; final positive transform.
    disk_build_gamma_rows<<<blocks_for(length), threads>>>(
        d_gamma0, d_two_pi_t, d_stage_reciprocals, length, stages,
        d_gamma_rows);
    disk_copy_add_g_error<<<blocks_for(row_cells), threads>>>(
        d_gamma_rows, d_G_positive, row_cells, g_error);
    disk_transform(d_G_positive, d_G_negative, d_roots, stages, length,
                   reduced_length, true);
    disk_postprocess_G<<<blocks_for(row_cells), threads>>>(
        d_G_negative, length, stages, G_error);

    disk_transform(d_G_negative, d_G_positive, d_roots, stages, length,
                   reduced_length, false);
    disk_transform(d_skn, d_S_positive, d_roots, stages, length,
                   reduced_length, false);
    disk_pointwise_products<<<blocks_for(row_cells), threads>>>(
        d_G_positive, d_S_positive, d_products, row_cells);
    disk_transform(d_products, d_convolutions, d_roots, stages, length,
                   reduced_length, true);
    disk_normalize_and_taylor_sum<<<blocks_for(length / 2U), threads>>>(
        d_convolutions, d_retained, length, stages, reciprocal_length);

    disk_initialize_half_spectrum<<<blocks_for(reduced_length + 1U), threads>>>(
        d_retained, d_half_spectrum, length, fmax_error, fhatsum_error,
        taylor_error, fhat_transform_error);
    disk_hermidft_preprocess<<<blocks_for(reduced_length), threads>>>(
        d_half_spectrum, d_hermi_pre, d_roots, omega, reduced_length,
        d_endpoint_trace);
    disk_transform(d_hermi_pre, d_hermi_fft, d_roots, 1U, reduced_length,
                   reduced_length, false);
    disk_extract_samples<<<blocks_for(reduced_length), threads>>>(
        d_hermi_fft, d_samples, reduced_length);
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  CUDA_CHECK(cudaGetLastError());

  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
  std::vector<RealDisk> samples(sample_count);
  CUDA_CHECK(cudaMemcpy(samples.data(), d_samples,
                        samples.size() * sizeof(RealDisk),
                        cudaMemcpyDeviceToHost));
  HermidftEndpointTrace endpoint_trace{};
  CUDA_CHECK(cudaMemcpy(&endpoint_trace, d_endpoint_trace,
                        sizeof(endpoint_trace), cudaMemcpyDeviceToHost));

  bool finite = true;
  std::uint64_t sign_ambiguous = 0U;
  double maximum_radius = 0.0;
  double maximum_center = 0.0;
  double minimum_sign_margin = std::numeric_limits<double>::infinity();
  std::size_t maximum_radius_index = 0U;
  std::size_t first_ambiguous_index = samples.size();
  for (std::size_t index = 0; index < samples.size(); ++index) {
    const RealDisk sample = samples[index];
    finite = finite && std::isfinite(sample.center) &&
             std::isfinite(sample.radius) && sample.radius >= 0.0;
    if (fabs(sample.center) <= sample.radius) {
      if (first_ambiguous_index == samples.size()) first_ambiguous_index = index;
      ++sign_ambiguous;
    }
    if (sample.radius > maximum_radius) {
      maximum_radius = sample.radius;
      maximum_radius_index = index;
    }
    maximum_center = std::max(maximum_center, fabs(sample.center));
    minimum_sign_margin =
        std::min(minimum_sign_margin, fabs(sample.center) - sample.radius);
  }
  const RealDisk first_ambiguous =
      first_ambiguous_index < samples.size()
          ? samples[first_ambiguous_index]
          : RealDisk{0.0, 0.0};

  bool kat_contained = true;
  double maximum_kat_distance = 0.0;
  if (!options.source_shape && !options.source_errors && length <= 32U) {
    const std::vector<long double> reference =
        reference_samples(options, box_host);
    for (std::size_t index = 0; index < samples.size(); ++index) {
      const long double distance =
          fabsl(reference[index] - static_cast<long double>(samples[index].center));
      kat_contained = kat_contained &&
          distance <= static_cast<long double>(samples[index].radius);
      maximum_kat_distance = std::max(
          maximum_kat_distance, static_cast<double>(distance));
    }
  }

  EndpointCertificateExport endpoint_certificate{};
  const bool endpoint_certificate_exported =
      !options.endpoint_certificate.empty();
  if (endpoint_certificate_exported) {
    endpoint_certificate = write_endpoint_certificate(
        options.endpoint_certificate, endpoint_trace);
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
  const double butterflies_per_second =
      static_cast<double>(butterflies_per_run) * options.repetitions /
      elapsed_seconds;

  std::cout << std::setprecision(17)
            << "{\"schema\":\"sparkinterval.tg.platt-windowed-disk-semantic.v2\""
            << ",\"claim_scope\":\"source_core_packet_to_disk_transform_candidate_not_a_zeta_certificate\""
            << ",\"formal_arithmetic_model\":\"SparkInterval.Certified.ComplexDisk.AddCertificate+MulCertificate\""
            << ",\"physical_trace_refinement_proved\":false"
            << ",\"upstream_commit\":\"42b21426718e542daa2b006dc05ea2d7f26426e6\""
            << ",\"actual_zeta_inputs\":false"
            << ",\"source_core_packet_consumed\":"
            << (packet_supplied ? "true" : "false")
            << ",\"source_packet_complete_terms\":"
            << (packet_supplied && loaded_packet.complete_terms ? "true"
                                                               : "false")
            << ",\"source_packet_term_count\":"
            << (packet_supplied ? loaded_packet.source_terms : 0U)
            << ",\"source_packet_bytes\":"
            << (packet_supplied ? loaded_packet.bytes : 0U)
            << ",\"source_packet_sha256\":\""
            << (packet_supplied ? loaded_packet.sha256 : "") << "\""
            << ",\"source_shape\":" << (options.source_shape ? "true" : "false")
            << ",\"source_error_disks\":"
            << (options.source_errors ? "true" : "false")
            << ",\"device\":\"" << properties.name << "\""
            << ",\"compute_capability\":\"" << properties.major << "."
            << properties.minor << "\""
            << ",\"convolution_length\":" << length
            << ",\"taylor_terms\":" << stages
            << ",\"repetitions\":" << options.repetitions
            << ",\"negative_G_transforms\":" << stages
            << ",\"positive_convolution_transforms\":" << 2U * stages
            << ",\"negative_inverse_transforms\":" << stages
            << ",\"positive_hermidft_transforms\":1"
            << ",\"butterflies_per_run\":" << butterflies_per_run
            << ",\"pointwise_products_per_run\":" << row_cells
            << ",\"elapsed_seconds\":" << elapsed_seconds
            << ",\"semantic_runs_per_second\":" << runs_per_second
            << ",\"butterflies_per_second\":" << butterflies_per_second
            << ",\"all_output_disks_finite\":" << (finite ? "true" : "false")
            << ",\"sign_ambiguous_samples\":" << sign_ambiguous
            << ",\"all_sample_signs_certified\":"
            << (sign_ambiguous == 0U ? "true" : "false")
            << ",\"ambiguity_policy\":\"ambiguous_samples_have_no_sign_and_require_refinement\""
            << ",\"maximum_output_radius\":" << maximum_radius
            << ",\"maximum_output_diameter\":" << 2.0 * maximum_radius
            << ",\"maximum_output_radius_index\":" << maximum_radius_index
            << ",\"maximum_output_center_abs\":" << maximum_center
            << ",\"minimum_sign_margin\":" << minimum_sign_margin
            << ",\"first_ambiguous_index\":"
            << (first_ambiguous_index < samples.size()
                    ? static_cast<std::int64_t>(first_ambiguous_index)
                    : -1)
            << ",\"first_ambiguous_center\":" << first_ambiguous.center
            << ",\"first_ambiguous_radius\":" << first_ambiguous.radius
            << ",\"small_long_double_kat_contained\":"
            << (kat_contained ? "true" : "false")
            << ",\"maximum_kat_center_distance\":" << maximum_kat_distance
            << ",\"endpoint_certificate_exported\":"
            << (endpoint_certificate_exported ? "true" : "false")
            << ",\"endpoint_certificate_schema\":\"sparkinterval.platt-hermidft-endpoint-wire.v1\""
            << ",\"endpoint_certificate_bytes\":"
            << endpoint_certificate.bytes
            << ",\"endpoint_certificate_sha256\":\""
            << endpoint_certificate.sha256 << "\""
            << ",\"endpoint_certificate_lean_checker\":\"SparkInterval.Zeta.PlattDiskPipeline.Wire.checkBytes\""
            << ",\"whole_transform_trace_exported\":false"
            << ",\"endpoint_device_copy_to_wire_refinement_proved\":false"
            << ",\"output_fnv1a64\":\"" << std::hex << std::setw(16)
            << std::setfill('0') << disk_fnv1a(samples) << "\"}\n";

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
  CUDA_CHECK(cudaFree(d_roots));
  CUDA_CHECK(cudaFree(d_samples));
  CUDA_CHECK(cudaFree(d_endpoint_trace));
  return finite && kat_contained &&
                 (!options.require_unambiguous || sign_ambiguous == 0U)
             ? 0
             : 1;
}

}  // namespace

#ifndef SPARKINTERVAL_PLATT_DISK_NO_MAIN
int main(int argc, char** argv) {
  try {
    return run_disk_semantic(parse_disk_options(argc, argv));
  } catch (const std::exception& error) {
    std::cerr << "sparkinterval-tg-platt-windowed-disk-semantic: "
              << error.what() << '\n';
    return 2;
  }
}
#endif

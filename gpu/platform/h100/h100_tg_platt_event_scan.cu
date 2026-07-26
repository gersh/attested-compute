// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_event_scan.hpp"

#include "sparkinterval/sha256.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace sparkinterval::tg::platt_event_scan {
namespace {

namespace pw = sparkinterval::tg::platt_windowed;

constexpr unsigned int kThreads = 256U;
constexpr unsigned int kWarps = kThreads / 32U;
constexpr char kMerkleLeafDomain[] =
    "sparkinterval/tg/platt-pt21-event-scan/leaf/v1";
constexpr char kMerkleNodeDomain[] =
    "sparkinterval/tg/platt-pt21-event-scan/node/v1";
constexpr char kStationaryPayloadDomain[] =
    "sparkinterval/tg/platt-stationary-junction-payload/v1\0";
__device__ __constant__ char kDeviceMerkleLeafDomain[] =
    "sparkinterval/tg/platt-pt21-event-scan/leaf/v1";
__device__ __constant__ char kDeviceMerkleNodeDomain[] =
    "sparkinterval/tg/platt-pt21-event-scan/node/v1";

inline constexpr std::uint32_t kGeometryLeaf = 0U;
inline constexpr std::uint32_t kSampleLeafBegin = 1U;
inline constexpr std::uint32_t kSummaryLeafBegin =
    kSampleLeafBegin + platt_dd_transform::kSourceRequiredCount;
inline constexpr std::uint32_t kDirectLeafBegin =
    kSummaryLeafBegin + kStreamCount;
inline constexpr std::uint32_t kMaximumDirectLeaves =
    512U + 24'576U + 512U;
inline constexpr std::uint32_t kStationaryLeafBegin =
    kDirectLeafBegin + kMaximumDirectLeaves;
inline constexpr std::uint32_t kMaximumStationaryLeaves =
    510U + 24'574U + 510U;
inline constexpr std::uint32_t kUsedMerkleLeaves =
    kStationaryLeafBegin + kMaximumStationaryLeaves;
inline constexpr std::uint32_t kMerkleLeafCount = 131'072U;
inline constexpr std::uint32_t kMerkleSecondCount = kMerkleLeafCount / 2U;
static_assert(kUsedMerkleLeaves < kMerkleLeafCount);

#define SPARK_HD __host__ __device__ __forceinline__

SPARK_HD std::uint64_t double_bits(double value) {
#if defined(__CUDA_ARCH__)
  return static_cast<std::uint64_t>(__double_as_longlong(value));
#else
  std::uint64_t result;
  std::memcpy(&result, &value, sizeof(result));
  return result;
#endif
}

SPARK_HD bool finite_binary64(double value) {
  return ((double_bits(value) >> 52U) & 0x7ffU) != 0x7ffU;
}

struct ExactExpansion {
  double values[8];
  int length;
  bool valid;
};

// Shewchuk grow-expansion addition.  With round-to-nearest IEEE binary64,
// every returned component together represents the exact real sum.  We use
// no fast-math build flags and fail closed if an intermediate overflows.
SPARK_HD void expansion_add(ExactExpansion* expansion, double value) {
  if (!expansion->valid || value == 0.0) return;
  if (expansion->length == 0) {
    expansion->values[0] = value;
    expansion->length = 1;
    return;
  }
  double q = value;
  double output[8];
  int output_length = 0;
  for (int index = 0; index < expansion->length; ++index) {
    const double a = expansion->values[index];
    const double sum = a + q;
    if (!finite_binary64(sum)) {
      expansion->valid = false;
      return;
    }
    const double q_virtual = sum - a;
    const double a_virtual = sum - q_virtual;
    const double q_roundoff = q - q_virtual;
    const double a_roundoff = a - a_virtual;
    const double residual = a_roundoff + q_roundoff;
    if (residual != 0.0) output[output_length++] = residual;
    q = sum;
  }
  if (q != 0.0 || output_length == 0) output[output_length++] = q;
  if (output_length > 8) {
    expansion->valid = false;
    return;
  }
  expansion->length = output_length;
  for (int index = 0; index < output_length; ++index) {
    expansion->values[index] = output[index];
  }
}

SPARK_HD int exact_sum_sign(const double* values, int count, bool* valid) {
  ExactExpansion expansion{{0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0},
                           0, true};
  for (int index = 0; index < count; ++index) {
    expansion_add(&expansion, values[index]);
  }
  *valid = expansion.valid;
  if (!expansion.valid || expansion.length == 0) return 0;
  for (int index = expansion.length - 1; index >= 0; --index) {
    if (expansion.values[index] > 0.0) return 1;
    if (expansion.values[index] < 0.0) return -1;
  }
  return 0;
}

struct CertifiedSign {
  std::int8_t sign;
  std::uint32_t failure;
};

SPARK_HD CertifiedSign certify_disk(const pw::RealDisk106& disk) {
  if (!finite_binary64(disk.center.hi) ||
      !finite_binary64(disk.center.lo) || !finite_binary64(disk.radius) ||
      disk.radius < 0.0) {
    return {0, kFailureMalformedDisk};
  }
  bool valid = true;
  const double lower_terms[3] = {
      disk.center.hi, disk.center.lo, -disk.radius};
  const int lower_sign = exact_sum_sign(lower_terms, 3, &valid);
  if (!valid) return {0, kFailureExactArithmetic};
  if (lower_sign > 0) return {1, kFailureNone};

  const double upper_terms[3] = {
      disk.center.hi, disk.center.lo, disk.radius};
  const int upper_sign = exact_sum_sign(upper_terms, 3, &valid);
  if (!valid) return {0, kFailureExactArithmetic};
  if (upper_sign < 0) return {-1, kFailureNone};
  return {0, kFailureAmbiguousDisk};
}

// Exact strict interval comparison used by Arb's arb_gt:
// left.lower > right.upper.  Together with exact_stat_pt, this reproduces
// zeta_arb/turing.c at djplatt/code commit 42b21426718e542daa2b006dc05ea2d7f26426e6.
SPARK_HD bool disk_strict_gt(const pw::RealDisk106& left,
                             const pw::RealDisk106& right,
                             bool* valid) {
  const double terms[6] = {
      left.center.hi, left.center.lo, -left.radius,
      -right.center.hi, -right.center.lo, -right.radius};
  return exact_sum_sign(terms, 6, valid) > 0;
}

SPARK_HD bool exact_stat_pt(const pw::RealDisk106& left,
                            const pw::RealDisk106& middle,
                            const pw::RealDisk106& right,
                            std::int8_t sign, bool* valid) {
  *valid = true;
  if (sign > 0) {
    const bool left_gt = disk_strict_gt(left, middle, valid);
    if (!*valid || !left_gt) return false;
    return disk_strict_gt(right, middle, valid);
  }
  const bool middle_gt_left = disk_strict_gt(middle, left, valid);
  if (!*valid || !middle_gt_left) return false;
  return disk_strict_gt(middle, right, valid);
}

SPARK_HD int stream_lower(std::uint32_t stream) {
  return stream == 0U ? kLeftFlankLower
       : stream == 1U ? kMainLower
                      : kRightFlankLower;
}

SPARK_HD int stream_upper(std::uint32_t stream) {
  return stream == 0U ? kLeftFlankUpper
       : stream == 1U ? kMainUpper
                      : kRightFlankUpper;
}

SPARK_HD std::uint32_t required_index(int offset) {
  return static_cast<std::uint32_t>(offset - kRequiredLower);
}

struct DeviceOutputs {
  DirectEvent* direct[kStreamCount];
  StationaryCandidate* stationary[kStreamCount];
  std::uint32_t direct_capacities[kStreamCount];
  std::uint32_t stationary_capacities[kStreamCount];
  StreamSummary* summaries;
  ScanStatus* status;
  unsigned char* merkle_a;
  unsigned char* merkle_b;
};

__global__ void certify_samples_kernel(const pw::RealDisk106* samples,
                                       std::int8_t* signs,
                                       ScanStatus* status) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= platt_dd_transform::kSourceRequiredCount) return;
  const CertifiedSign result = certify_disk(samples[index]);
  signs[index] = result.sign;
  if (result.failure != kFailureNone) {
    atomicOr(&status->failure_flags, result.failure);
  } else {
    atomicAdd(&status->certified_sample_count, 1U);
  }
}

__device__ unsigned int compact_rank(bool selected,
                                     unsigned int* warp_counts,
                                     unsigned int* warp_bases,
                                     unsigned int* chunk_count) {
  const unsigned int lane = threadIdx.x & 31U;
  const unsigned int warp = threadIdx.x >> 5U;
  const unsigned int mask = __ballot_sync(0xffffffffU, selected);
  if (lane == 0U) warp_counts[warp] = __popc(mask);
  __syncthreads();
  if (threadIdx.x == 0U) {
    unsigned int total = 0U;
    for (unsigned int index = 0; index < kWarps; ++index) {
      warp_bases[index] = total;
      total += warp_counts[index];
    }
    *chunk_count = total;
  }
  __syncthreads();
  const unsigned int lower_lanes =
      lane == 0U ? 0U : ((1U << lane) - 1U);
  return warp_bases[warp] + __popc(mask & lower_lanes);
}

__global__ void scan_streams_kernel(const pw::RealDisk106* samples,
                                    const std::int8_t* signs,
                                    DeviceOutputs outputs) {
  const std::uint32_t stream = blockIdx.x;
  if (stream >= kStreamCount || outputs.status->failure_flags != 0U) return;

  const int lower = stream_lower(stream);
  const int upper = stream_upper(stream);
  const unsigned int edge_count = static_cast<unsigned int>(upper - lower);
  const unsigned int triple_count = edge_count - 1U;
  __shared__ unsigned int warp_counts[kWarps];
  __shared__ unsigned int warp_bases[kWarps];
  __shared__ unsigned int chunk_count;
  __shared__ unsigned int direct_total;
  __shared__ unsigned int stationary_total;
  if (threadIdx.x == 0U) {
    direct_total = 0U;
    stationary_total = 0U;
  }
  __syncthreads();

  for (unsigned int base = 0U; base < edge_count; base += blockDim.x) {
    const unsigned int edge = base + threadIdx.x;
    bool direct_selected = false;
    DirectEvent direct{};
    if (edge < edge_count) {
      const int left_offset = lower + static_cast<int>(edge);
      const std::int8_t left_sign = signs[required_index(left_offset)];
      const std::int8_t right_sign = signs[required_index(left_offset + 1)];
      direct_selected = left_sign != right_sign;
      if (direct_selected) {
        direct.left_sample = left_offset;
        direct.right_sample = left_offset + 1;
        // With every sign certified, upstream last_ptr is this edge's left
        // sample.  These are exactly Nleft_int and Nright_int before the
        // common 21/512 lattice factor.
        direct.source_nleft_units = -static_cast<int>(edge);
        direct.source_nright_units =
            static_cast<int>(edge_count - edge - 1U);
        direct.stream = stream;
        direct.certified_multiplicity_slots = 1U;
      }
    }
    const unsigned int direct_rank = compact_rank(
        direct_selected, warp_counts, warp_bases, &chunk_count);
    const unsigned int direct_chunk_count = chunk_count;
    if (direct_selected) {
      const unsigned int output_index = direct_total + direct_rank;
      if (output_index < outputs.direct_capacities[stream]) {
        outputs.direct[stream][output_index] = direct;
      } else {
        atomicOr(&outputs.status->failure_flags, kFailureDirectOverflow);
      }
    }
    __syncthreads();
    if (threadIdx.x == 0U) direct_total += direct_chunk_count;
    __syncthreads();

    bool stationary_selected = false;
    StationaryCandidate stationary{};
    if (edge < triple_count) {
      const int left_offset = lower + static_cast<int>(edge);
      const std::int8_t left_sign = signs[required_index(left_offset)];
      const std::int8_t middle_sign = signs[required_index(left_offset + 1)];
      const std::int8_t right_sign = signs[required_index(left_offset + 2)];
      if (left_sign == middle_sign && middle_sign == right_sign) {
        bool exact_valid = true;
        stationary_selected = exact_stat_pt(
            samples[required_index(left_offset)],
            samples[required_index(left_offset + 1)],
            samples[required_index(left_offset + 2)], middle_sign,
            &exact_valid);
        if (!exact_valid) {
          atomicOr(&outputs.status->failure_flags,
                   kFailureExactArithmetic);
          stationary_selected = false;
        }
      }
      if (stationary_selected) {
        stationary.left_sample = left_offset;
        stationary.middle_sample = left_offset + 1;
        stationary.right_sample = left_offset + 2;
        stationary.source_nleft_units_per_slot_if_resolved =
            -static_cast<int>(edge);
        stationary.source_nright_units_per_slot_if_resolved =
            static_cast<int>(edge_count - edge - 2U);
        stationary.stream = stream;
        stationary.source_positive = middle_sign > 0 ? 1U : 0U;
        stationary.strict_stat_pt = 1U;
        stationary.requires_adaptive_resolution = 1U;
        stationary.certified_multiplicity_slots = 0U;
        stationary.multiplicity_slots_if_resolution_succeeds = 2U;
        stationary.reserved_zero[0] = 0U;
        stationary.reserved_zero[1] = 0U;
        stationary.reserved_zero[2] = 0U;
      }
    }
    const unsigned int stationary_rank = compact_rank(
        stationary_selected, warp_counts, warp_bases, &chunk_count);
    const unsigned int stationary_chunk_count = chunk_count;
    if (stationary_selected) {
      const unsigned int output_index = stationary_total + stationary_rank;
      if (output_index < outputs.stationary_capacities[stream]) {
        outputs.stationary[stream][output_index] = stationary;
      } else {
        atomicOr(&outputs.status->failure_flags,
                 kFailureStationaryOverflow);
      }
    }
    __syncthreads();
    if (threadIdx.x == 0U) stationary_total += stationary_chunk_count;
    __syncthreads();
  }

  if (threadIdx.x == 0U) {
    StreamSummary summary{};
    summary.stream = stream;
    summary.lower_sample = lower;
    summary.upper_sample = upper;
    summary.range_sample_count = static_cast<std::uint32_t>(upper - lower + 1);
    summary.direct_event_count = direct_total;
    summary.stationary_candidate_count = stationary_total;
    summary.certified_direct_multiplicity_slots = direct_total;
    summary.reserved_zero = 0U;
    summary.direct_nleft_units = 0;
    summary.direct_nright_units = 0;
    const unsigned int retained_direct =
        direct_total < outputs.direct_capacities[stream]
            ? direct_total
            : outputs.direct_capacities[stream];
    for (unsigned int index = 0; index < retained_direct; ++index) {
      summary.direct_nleft_units +=
          outputs.direct[stream][index].source_nleft_units;
      summary.direct_nright_units +=
          outputs.direct[stream][index].source_nright_units;
    }
    summary.left_endpoint.sample_offset = lower;
    summary.left_endpoint.positive =
        signs[required_index(lower)] > 0 ? 1U : 0U;
    summary.left_endpoint.disk = samples[required_index(lower)];
    summary.right_endpoint.sample_offset = upper;
    summary.right_endpoint.positive =
        signs[required_index(upper)] > 0 ? 1U : 0U;
    summary.right_endpoint.disk = samples[required_index(upper)];
    outputs.summaries[stream] = summary;
  }
}

struct DeviceSha256 {
  std::uint32_t state[8];
  unsigned char buffer[64];
  std::uint32_t buffer_size;
  std::uint64_t total_bytes;
};

__device__ __forceinline__ std::uint32_t rotr(std::uint32_t value,
                                              unsigned int distance) {
  return (value >> distance) | (value << (32U - distance));
}

__device__ void sha_transform(DeviceSha256* sha,
                              const unsigned char* block) {
  constexpr std::uint32_t constants[64] = {
      0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
      0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
      0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
      0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
      0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
      0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
      0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
      0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
      0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
      0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
      0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
      0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
      0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
      0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
      0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
      0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U};
  std::uint32_t words[64];
  for (int index = 0; index < 16; ++index) {
    words[index] =
        (static_cast<std::uint32_t>(block[index * 4]) << 24U) |
        (static_cast<std::uint32_t>(block[index * 4 + 1]) << 16U) |
        (static_cast<std::uint32_t>(block[index * 4 + 2]) << 8U) |
        static_cast<std::uint32_t>(block[index * 4 + 3]);
  }
  for (int index = 16; index < 64; ++index) {
    const std::uint32_t x = words[index - 15];
    const std::uint32_t y = words[index - 2];
    const std::uint32_t sigma0 = rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3U);
    const std::uint32_t sigma1 = rotr(y, 17) ^ rotr(y, 19) ^ (y >> 10U);
    words[index] =
        words[index - 16] + sigma0 + words[index - 7] + sigma1;
  }
  std::uint32_t a = sha->state[0];
  std::uint32_t b = sha->state[1];
  std::uint32_t c = sha->state[2];
  std::uint32_t d = sha->state[3];
  std::uint32_t e = sha->state[4];
  std::uint32_t f = sha->state[5];
  std::uint32_t g = sha->state[6];
  std::uint32_t h = sha->state[7];
  for (int index = 0; index < 64; ++index) {
    const std::uint32_t choice = (e & f) ^ (~e & g);
    const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    const std::uint32_t sum0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    const std::uint32_t sum1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    const std::uint32_t temporary1 =
        h + sum1 + choice + constants[index] + words[index];
    const std::uint32_t temporary2 = sum0 + majority;
    h = g;
    g = f;
    f = e;
    e = d + temporary1;
    d = c;
    c = b;
    b = a;
    a = temporary1 + temporary2;
  }
  sha->state[0] += a;
  sha->state[1] += b;
  sha->state[2] += c;
  sha->state[3] += d;
  sha->state[4] += e;
  sha->state[5] += f;
  sha->state[6] += g;
  sha->state[7] += h;
}

__device__ void sha_init(DeviceSha256* sha) {
  const std::uint32_t initial[8] = {
      0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
      0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U};
  for (int index = 0; index < 8; ++index) sha->state[index] = initial[index];
  sha->buffer_size = 0U;
  sha->total_bytes = 0U;
}

__device__ void sha_byte(DeviceSha256* sha, unsigned char value) {
  sha->buffer[sha->buffer_size++] = value;
  ++sha->total_bytes;
  if (sha->buffer_size == 64U) {
    sha_transform(sha, sha->buffer);
    sha->buffer_size = 0U;
  }
}

__device__ void sha_u32(DeviceSha256* sha, std::uint32_t value) {
  for (unsigned int byte = 0; byte < 4U; ++byte) {
    sha_byte(sha, static_cast<unsigned char>(value >> (8U * byte)));
  }
}

__device__ void sha_u64(DeviceSha256* sha, std::uint64_t value) {
  for (unsigned int byte = 0; byte < 8U; ++byte) {
    sha_byte(sha, static_cast<unsigned char>(value >> (8U * byte)));
  }
}

__device__ void sha_disk(DeviceSha256* sha, const pw::RealDisk106& disk) {
  sha_u64(sha, double_bits(disk.center.hi));
  sha_u64(sha, double_bits(disk.center.lo));
  sha_u64(sha, double_bits(disk.radius));
}

__device__ void sha_finish(DeviceSha256* sha, unsigned char* digest) {
  const std::uint64_t bit_length = sha->total_bytes * 8U;
  sha->buffer[sha->buffer_size++] = 0x80U;
  if (sha->buffer_size > 56U) {
    while (sha->buffer_size < 64U) sha->buffer[sha->buffer_size++] = 0U;
    sha_transform(sha, sha->buffer);
    sha->buffer_size = 0U;
  }
  while (sha->buffer_size < 56U) sha->buffer[sha->buffer_size++] = 0U;
  for (unsigned int byte = 0; byte < 8U; ++byte) {
    sha->buffer[56U + byte] =
        static_cast<unsigned char>(bit_length >> (56U - 8U * byte));
  }
  sha_transform(sha, sha->buffer);
  for (int word = 0; word < 8; ++word) {
    for (int byte = 0; byte < 4; ++byte) {
      digest[word * 4 + byte] = static_cast<unsigned char>(
          sha->state[word] >> (24U - 8U * byte));
    }
  }
}

__device__ void sha_direct(DeviceSha256* sha, const DirectEvent& event) {
  sha_u32(sha, static_cast<std::uint32_t>(event.left_sample));
  sha_u32(sha, static_cast<std::uint32_t>(event.right_sample));
  sha_u32(sha, static_cast<std::uint32_t>(event.source_nleft_units));
  sha_u32(sha, static_cast<std::uint32_t>(event.source_nright_units));
  sha_u32(sha, event.stream);
  sha_u32(sha, event.certified_multiplicity_slots);
}

__device__ void sha_stationary(DeviceSha256* sha,
                               const StationaryCandidate& candidate) {
  sha_u32(sha, static_cast<std::uint32_t>(candidate.left_sample));
  sha_u32(sha, static_cast<std::uint32_t>(candidate.middle_sample));
  sha_u32(sha, static_cast<std::uint32_t>(candidate.right_sample));
  sha_u32(sha, static_cast<std::uint32_t>(
                   candidate.source_nleft_units_per_slot_if_resolved));
  sha_u32(sha, static_cast<std::uint32_t>(
                   candidate.source_nright_units_per_slot_if_resolved));
  sha_u32(sha, candidate.stream);
  sha_byte(sha, candidate.source_positive);
  sha_byte(sha, candidate.strict_stat_pt);
  sha_byte(sha, candidate.requires_adaptive_resolution);
  sha_byte(sha, candidate.certified_multiplicity_slots);
  sha_byte(sha, candidate.multiplicity_slots_if_resolution_succeeds);
  sha_byte(sha, 0U);
  sha_byte(sha, 0U);
  sha_byte(sha, 0U);
}

__device__ void sha_summary(DeviceSha256* sha, const StreamSummary& summary) {
  sha_u32(sha, summary.stream);
  sha_u32(sha, static_cast<std::uint32_t>(summary.lower_sample));
  sha_u32(sha, static_cast<std::uint32_t>(summary.upper_sample));
  sha_u32(sha, summary.range_sample_count);
  sha_u32(sha, summary.direct_event_count);
  sha_u32(sha, summary.stationary_candidate_count);
  sha_u32(sha, summary.certified_direct_multiplicity_slots);
  sha_u32(sha, 0U);
  sha_u64(sha, static_cast<std::uint64_t>(summary.direct_nleft_units));
  sha_u64(sha, static_cast<std::uint64_t>(summary.direct_nright_units));
  sha_u32(sha,
          static_cast<std::uint32_t>(summary.left_endpoint.sample_offset));
  sha_u32(sha, summary.left_endpoint.positive);
  sha_disk(sha, summary.left_endpoint.disk);
  sha_u32(sha,
          static_cast<std::uint32_t>(summary.right_endpoint.sample_offset));
  sha_u32(sha, summary.right_endpoint.positive);
  sha_disk(sha, summary.right_endpoint.disk);
}

__device__ void sha_device_domain(DeviceSha256* sha, const char* domain,
                                  std::size_t size) {
  for (std::size_t index = 0; index < size; ++index) {
    sha_byte(sha, static_cast<unsigned char>(domain[index]));
  }
}

__device__ bool decode_fixed_slot(std::uint32_t local,
                                  const std::uint32_t sizes[kStreamCount],
                                  std::uint32_t* stream,
                                  std::uint32_t* slot) {
  std::uint32_t base = 0U;
  for (std::uint32_t index = 0U; index < kStreamCount; ++index) {
    if (local < base + sizes[index]) {
      *stream = index;
      *slot = local - base;
      return true;
    }
    base += sizes[index];
  }
  return false;
}

__global__ void merkle_leaf_kernel(const pw::RealDisk106* samples,
                                   const std::int8_t* signs,
                                   DeviceOutputs outputs) {
  const std::uint32_t leaf = blockIdx.x * blockDim.x + threadIdx.x;
  if (leaf >= kMerkleLeafCount) return;
  unsigned char* destination = outputs.merkle_a + leaf * 32U;
  if (outputs.status->failure_flags != 0U || leaf >= kUsedMerkleLeaves) {
    for (unsigned int byte = 0; byte < 32U; ++byte) destination[byte] = 0U;
    return;
  }

  DeviceSha256 sha;
  sha_init(&sha);
  sha_device_domain(&sha, kDeviceMerkleLeafDomain,
                    sizeof(kDeviceMerkleLeafDomain));
  sha_u32(&sha, leaf);
  bool active = true;
  if (leaf == kGeometryLeaf) {
    sha_u32(&sha, 0U);
    sha_u32(&sha, platt_dd_transform::kSourceRequiredCount);
    sha_u32(&sha, static_cast<std::uint32_t>(kRequiredLower));
    sha_u32(&sha, static_cast<std::uint32_t>(kRequiredUpper));
    sha_u32(&sha, static_cast<std::uint32_t>(kLatticeNumerator));
    sha_u32(&sha, static_cast<std::uint32_t>(kLatticeDenominator));
  } else if (leaf < kSummaryLeafBegin) {
    const std::uint32_t sample = leaf - kSampleLeafBegin;
    sha_u32(&sha, 1U);
    sha_u32(&sha, sample);
    sha_disk(&sha, samples[sample]);
    sha_byte(&sha, signs[sample] > 0 ? 1U : 0U);
  } else if (leaf < kDirectLeafBegin) {
    const std::uint32_t stream = leaf - kSummaryLeafBegin;
    sha_u32(&sha, 2U);
    sha_u32(&sha, stream);
    sha_summary(&sha, outputs.summaries[stream]);
  } else if (leaf < kStationaryLeafBegin) {
    constexpr std::uint32_t sizes[kStreamCount] = {512U, 24'576U, 512U};
    std::uint32_t stream = 0U;
    std::uint32_t slot = 0U;
    decode_fixed_slot(leaf - kDirectLeafBegin, sizes, &stream, &slot);
    active = slot < outputs.summaries[stream].direct_event_count;
    if (active) {
      sha_u32(&sha, 3U);
      sha_u32(&sha, stream);
      sha_u32(&sha, slot);
      sha_direct(&sha, outputs.direct[stream][slot]);
    }
  } else {
    constexpr std::uint32_t sizes[kStreamCount] = {510U, 24'574U, 510U};
    std::uint32_t stream = 0U;
    std::uint32_t slot = 0U;
    decode_fixed_slot(leaf - kStationaryLeafBegin, sizes, &stream, &slot);
    active = slot < outputs.summaries[stream].stationary_candidate_count;
    if (active) {
      sha_u32(&sha, 4U);
      sha_u32(&sha, stream);
      sha_u32(&sha, slot);
      sha_stationary(&sha, outputs.stationary[stream][slot]);
    }
  }
  if (!active) {
    for (unsigned int byte = 0; byte < 32U; ++byte) destination[byte] = 0U;
    return;
  }
  sha_finish(&sha, destination);
}

__global__ void merkle_node_kernel(const unsigned char* source,
                                   unsigned char* destination,
                                   std::uint32_t node_count,
                                   std::uint32_t level,
                                   const ScanStatus* status) {
  const std::uint32_t node = blockIdx.x * blockDim.x + threadIdx.x;
  if (node >= node_count || status->failure_flags != 0U) return;
  DeviceSha256 sha;
  sha_init(&sha);
  sha_device_domain(&sha, kDeviceMerkleNodeDomain,
                    sizeof(kDeviceMerkleNodeDomain));
  sha_u32(&sha, level);
  sha_u32(&sha, node);
  const unsigned char* children = source + node * 64U;
  for (unsigned int byte = 0; byte < 64U; ++byte) {
    sha_byte(&sha, children[byte]);
  }
  sha_finish(&sha, destination + node * 32U);
}

__global__ void merkle_finish_kernel(const unsigned char* root,
                                     ScanStatus* status) {
  if (blockIdx.x != 0U || threadIdx.x != 0U ||
      status->failure_flags != 0U) {
    return;
  }
  for (unsigned int byte = 0; byte < 32U; ++byte) {
    status->artifact_sha256[byte] = root[byte];
  }
  status->digest_valid = 1U;
}

void check_cuda(cudaError_t status, const char* operation) {
  if (status != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " +
                             cudaGetErrorString(status));
  }
}

std::size_t stream_index(StreamKind stream) {
  const std::size_t result = static_cast<std::size_t>(stream);
  if (result >= kStreamCount) throw std::invalid_argument("invalid stream");
  return result;
}

void append_u32(std::vector<unsigned char>* bytes, std::uint32_t value) {
  for (unsigned int byte = 0; byte < 4U; ++byte) {
    bytes->push_back(static_cast<unsigned char>(value >> (8U * byte)));
  }
}

void append_u64(std::vector<unsigned char>* bytes, std::uint64_t value) {
  for (unsigned int byte = 0; byte < 8U; ++byte) {
    bytes->push_back(static_cast<unsigned char>(value >> (8U * byte)));
  }
}

void append_disk(std::vector<unsigned char>* bytes,
                 const pw::RealDisk106& disk) {
  append_u64(bytes, double_bits(disk.center.hi));
  append_u64(bytes, double_bits(disk.center.lo));
  append_u64(bytes, double_bits(disk.radius));
}

void append_direct(std::vector<unsigned char>* bytes,
                   const DirectEvent& event) {
  append_u32(bytes, static_cast<std::uint32_t>(event.left_sample));
  append_u32(bytes, static_cast<std::uint32_t>(event.right_sample));
  append_u32(bytes, static_cast<std::uint32_t>(event.source_nleft_units));
  append_u32(bytes, static_cast<std::uint32_t>(event.source_nright_units));
  append_u32(bytes, event.stream);
  append_u32(bytes, event.certified_multiplicity_slots);
}

void append_stationary(std::vector<unsigned char>* bytes,
                       const StationaryCandidate& candidate) {
  append_u32(bytes, static_cast<std::uint32_t>(candidate.left_sample));
  append_u32(bytes, static_cast<std::uint32_t>(candidate.middle_sample));
  append_u32(bytes, static_cast<std::uint32_t>(candidate.right_sample));
  append_u32(bytes, static_cast<std::uint32_t>(
                        candidate.source_nleft_units_per_slot_if_resolved));
  append_u32(bytes, static_cast<std::uint32_t>(
                        candidate.source_nright_units_per_slot_if_resolved));
  append_u32(bytes, candidate.stream);
  bytes->push_back(candidate.source_positive);
  bytes->push_back(candidate.strict_stat_pt);
  bytes->push_back(candidate.requires_adaptive_resolution);
  bytes->push_back(candidate.certified_multiplicity_slots);
  bytes->push_back(candidate.multiplicity_slots_if_resolution_succeeds);
  bytes->insert(bytes->end(), 3U, 0U);
}

void append_summary(std::vector<unsigned char>* bytes,
                    const StreamSummary& summary) {
  append_u32(bytes, summary.stream);
  append_u32(bytes, static_cast<std::uint32_t>(summary.lower_sample));
  append_u32(bytes, static_cast<std::uint32_t>(summary.upper_sample));
  append_u32(bytes, summary.range_sample_count);
  append_u32(bytes, summary.direct_event_count);
  append_u32(bytes, summary.stationary_candidate_count);
  append_u32(bytes, summary.certified_direct_multiplicity_slots);
  append_u32(bytes, 0U);
  append_u64(bytes, static_cast<std::uint64_t>(summary.direct_nleft_units));
  append_u64(bytes, static_cast<std::uint64_t>(summary.direct_nright_units));
  append_u32(bytes,
             static_cast<std::uint32_t>(summary.left_endpoint.sample_offset));
  append_u32(bytes, summary.left_endpoint.positive);
  append_disk(bytes, summary.left_endpoint.disk);
  append_u32(bytes,
             static_cast<std::uint32_t>(summary.right_endpoint.sample_offset));
  append_u32(bytes, summary.right_endpoint.positive);
  append_disk(bytes, summary.right_endpoint.disk);
}

Sha256Digest host_merkle_node(
    std::uint32_t level, std::uint32_t node,
    const Sha256Digest& left, const Sha256Digest& right) {
  std::vector<unsigned char> bytes;
  bytes.reserve(sizeof(kMerkleNodeDomain) + 72U);
  bytes.insert(bytes.end(), kMerkleNodeDomain,
               kMerkleNodeDomain + sizeof(kMerkleNodeDomain));
  append_u32(&bytes, level);
  append_u32(&bytes, node);
  bytes.insert(bytes.end(), left.begin(), left.end());
  bytes.insert(bytes.end(), right.begin(), right.end());
  return sparkinterval::sha256(bytes.data(), bytes.size());
}

const std::vector<std::vector<Sha256Digest>>& zero_merkle_levels() {
  // Inactive scanner leaves are literal zero digests.  Their parent hashes
  // depend only on level and node and are therefore constant across every
  // PT21 block.  Construct this table once; replay then hashes only ancestors
  // of active samples/events instead of rehashing the large zero suffix.
  static const std::vector<std::vector<Sha256Digest>> levels = [] {
    std::vector<std::vector<Sha256Digest>> result;
    result.emplace_back(kMerkleLeafCount);
    std::uint32_t level = 0U;
    while (result.back().size() > 1U) {
      const auto& source = result.back();
      std::vector<Sha256Digest> next(source.size() / 2U);
      for (std::size_t node = 0U; node < next.size(); ++node) {
        next[node] = host_merkle_node(
            level, static_cast<std::uint32_t>(node),
            source[node * 2U], source[node * 2U + 1U]);
      }
      result.push_back(std::move(next));
      ++level;
    }
    return result;
  }();
  return levels;
}

Sha256Digest artifact_digest(const std::vector<pw::RealDisk106>& samples,
                             const std::vector<std::int8_t>& signs,
                             const HostArtifact& artifact) {
  std::vector<Sha256Digest> tree(kMerkleLeafCount);
  std::vector<std::uint8_t> active(kMerkleLeafCount, 0U);
  std::vector<unsigned char> bytes;
  bytes.reserve(160U);
  const auto begin_leaf = [&bytes](std::uint32_t leaf) {
    bytes.clear();
    bytes.insert(bytes.end(), kMerkleLeafDomain,
                 kMerkleLeafDomain + sizeof(kMerkleLeafDomain));
    append_u32(&bytes, leaf);
  };

  begin_leaf(kGeometryLeaf);
  append_u32(&bytes, 0U);
  append_u32(&bytes, platt_dd_transform::kSourceRequiredCount);
  append_u32(&bytes, static_cast<std::uint32_t>(kRequiredLower));
  append_u32(&bytes, static_cast<std::uint32_t>(kRequiredUpper));
  append_u32(&bytes, static_cast<std::uint32_t>(kLatticeNumerator));
  append_u32(&bytes, static_cast<std::uint32_t>(kLatticeDenominator));
  tree[kGeometryLeaf] = sparkinterval::sha256(bytes.data(), bytes.size());
  active[kGeometryLeaf] = 1U;
  for (std::size_t index = 0; index < samples.size(); ++index) {
    const std::uint32_t leaf =
        kSampleLeafBegin + static_cast<std::uint32_t>(index);
    begin_leaf(leaf);
    append_u32(&bytes, 1U);
    append_u32(&bytes, static_cast<std::uint32_t>(index));
    append_disk(&bytes, samples[index]);
    bytes.push_back(signs[index] > 0 ? 1U : 0U);
    tree[leaf] = sparkinterval::sha256(bytes.data(), bytes.size());
    active[leaf] = 1U;
  }
  for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
    const std::uint32_t leaf =
        kSummaryLeafBegin + static_cast<std::uint32_t>(stream);
    begin_leaf(leaf);
    append_u32(&bytes, 2U);
    append_u32(&bytes, static_cast<std::uint32_t>(stream));
    append_summary(&bytes, artifact.summaries[stream]);
    tree[leaf] = sparkinterval::sha256(bytes.data(), bytes.size());
    active[leaf] = 1U;
  }
  constexpr std::uint32_t direct_sizes[kStreamCount] = {
      512U, 24'576U, 512U};
  std::uint32_t direct_base = kDirectLeafBegin;
  for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
    for (std::size_t slot = 0; slot < artifact.direct[stream].size(); ++slot) {
      const std::uint32_t leaf =
          direct_base + static_cast<std::uint32_t>(slot);
      begin_leaf(leaf);
      append_u32(&bytes, 3U);
      append_u32(&bytes, static_cast<std::uint32_t>(stream));
      append_u32(&bytes, static_cast<std::uint32_t>(slot));
      append_direct(&bytes, artifact.direct[stream][slot]);
      tree[leaf] = sparkinterval::sha256(bytes.data(), bytes.size());
      active[leaf] = 1U;
    }
    direct_base += direct_sizes[stream];
  }
  constexpr std::uint32_t stationary_sizes[kStreamCount] = {
      510U, 24'574U, 510U};
  std::uint32_t stationary_base = kStationaryLeafBegin;
  for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
    for (std::size_t slot = 0; slot < artifact.stationary[stream].size();
         ++slot) {
      const std::uint32_t leaf =
          stationary_base + static_cast<std::uint32_t>(slot);
      begin_leaf(leaf);
      append_u32(&bytes, 4U);
      append_u32(&bytes, static_cast<std::uint32_t>(stream));
      append_u32(&bytes, static_cast<std::uint32_t>(slot));
      append_stationary(&bytes, artifact.stationary[stream][slot]);
      tree[leaf] = sparkinterval::sha256(bytes.data(), bytes.size());
      active[leaf] = 1U;
    }
    stationary_base += stationary_sizes[stream];
  }

  std::uint32_t level = 0U;
  const auto& zero_levels = zero_merkle_levels();
  while (tree.size() > 1U) {
    std::vector<Sha256Digest> next = zero_levels[level + 1U];
    std::vector<std::uint8_t> next_active(next.size(), 0U);
    for (std::size_t node = 0; node < next.size(); ++node) {
      if (active[node * 2U] != 0U ||
          active[node * 2U + 1U] != 0U) {
        next[node] = host_merkle_node(
            level, static_cast<std::uint32_t>(node),
            tree[node * 2U], tree[node * 2U + 1U]);
        next_active[node] = 1U;
      }
    }
    tree = std::move(next);
    active = std::move(next_active);
    ++level;
  }
  return tree.front();
}

bool equal_bytes(const void* left, const void* right, std::size_t size) {
  return std::memcmp(left, right, size) == 0;
}

bool shared_endpoints_agree(
    const std::array<StreamSummary, kStreamCount>& summaries) {
  return equal_bytes(&summaries[0].right_endpoint,
                     &summaries[1].left_endpoint,
                     sizeof(EndpointRecord)) &&
         equal_bytes(&summaries[1].right_endpoint,
                     &summaries[2].left_endpoint,
                     sizeof(EndpointRecord));
}

// Independent host replay has a fixed 2176-bit signed-magnitude dyadic
// fallback.  Cheap outward binary64 boxes decide only strictly separated
// signs/comparisons; equality and inconclusive boxes use this exact fallback.
// It intentionally does not share the CUDA expansion-adder implementation.
// Six binary64 terms need at most 2101 bits including carry.
inline constexpr std::size_t kHostExactLimbs = 34U;

struct ExactDyadic {
  std::uint64_t significand;
  int exponent;
  bool negative;
};

ExactDyadic exact_dyadic(double value) {
  const std::uint64_t bits = double_bits(value);
  const bool negative = (bits >> 63U) != 0U;
  const std::uint64_t encoded_exponent = (bits >> 52U) & 0x7ffU;
  const std::uint64_t fraction = bits & ((1ULL << 52U) - 1ULL);
  if (encoded_exponent == 0U) {
    return {fraction, -1074, negative};
  }
  return {(1ULL << 52U) | fraction,
          static_cast<int>(encoded_exponent) - 1023 - 52, negative};
}

struct SignedMagnitude {
  std::array<std::uint64_t, kHostExactLimbs> limbs{};
  bool negative = false;
};

int compare_magnitude(const SignedMagnitude& left,
                      const SignedMagnitude& right) {
  for (std::size_t index = kHostExactLimbs; index-- != 0U;) {
    if (left.limbs[index] < right.limbs[index]) return -1;
    if (left.limbs[index] > right.limbs[index]) return 1;
  }
  return 0;
}

void add_magnitude(SignedMagnitude* left, const SignedMagnitude& right) {
  std::uint64_t carry = 0U;
  for (std::size_t index = 0; index < kHostExactLimbs; ++index) {
    const unsigned __int128 sum =
        static_cast<unsigned __int128>(left->limbs[index]) +
        right.limbs[index] + carry;
    left->limbs[index] = static_cast<std::uint64_t>(sum);
    carry = static_cast<std::uint64_t>(sum >> 64U);
  }
  if (carry != 0U) throw std::overflow_error("host exact dyadic overflow");
}

void subtract_magnitude(SignedMagnitude* left,
                        const SignedMagnitude& right) {
  std::uint64_t borrow = 0U;
  for (std::size_t index = 0; index < kHostExactLimbs; ++index) {
    const unsigned __int128 subtrahend =
        static_cast<unsigned __int128>(right.limbs[index]) + borrow;
    const unsigned __int128 minuend = left->limbs[index];
    left->limbs[index] =
        static_cast<std::uint64_t>(minuend - subtrahend);
    borrow = minuend < subtrahend ? 1U : 0U;
  }
  if (borrow != 0U) throw std::logic_error("negative magnitude subtraction");
}

bool magnitude_is_zero(const SignedMagnitude& value) {
  for (const std::uint64_t limb : value.limbs) {
    if (limb != 0U) return false;
  }
  return true;
}

SignedMagnitude shifted_term(const ExactDyadic& term,
                             int minimum_exponent) {
  SignedMagnitude result;
  result.negative = term.negative;
  if (term.significand == 0U) return result;
  const unsigned int shift =
      static_cast<unsigned int>(term.exponent - minimum_exponent);
  const std::size_t word = shift / 64U;
  const unsigned int bits = shift % 64U;
  if (word >= kHostExactLimbs) {
    throw std::overflow_error("host exact dyadic shift overflow");
  }
  result.limbs[word] = term.significand << bits;
  if (bits != 0U) {
    if (word + 1U >= kHostExactLimbs) {
      throw std::overflow_error("host exact dyadic carry overflow");
    }
    result.limbs[word + 1U] = term.significand >> (64U - bits);
  }
  return result;
}

void add_signed(SignedMagnitude* total, const SignedMagnitude& term) {
  if (magnitude_is_zero(term)) return;
  if (magnitude_is_zero(*total)) {
    *total = term;
    return;
  }
  if (total->negative == term.negative) {
    add_magnitude(total, term);
    return;
  }
  const int comparison = compare_magnitude(*total, term);
  if (comparison == 0) {
    *total = SignedMagnitude{};
  } else if (comparison > 0) {
    subtract_magnitude(total, term);
  } else {
    SignedMagnitude difference = term;
    subtract_magnitude(&difference, *total);
    *total = difference;
  }
}

int host_exact_sum_sign(const double* values, int count) {
  std::array<ExactDyadic, 8> terms{};
  int minimum_exponent = std::numeric_limits<int>::max();
  for (int index = 0; index < count; ++index) {
    terms[index] = exact_dyadic(values[index]);
    if (terms[index].significand != 0U) {
      minimum_exponent = std::min(minimum_exponent, terms[index].exponent);
    }
  }
  if (minimum_exponent == std::numeric_limits<int>::max()) return 0;
  SignedMagnitude total;
  for (int index = 0; index < count; ++index) {
    add_signed(&total, shifted_term(terms[index], minimum_exponent));
  }
  return magnitude_is_zero(total) ? 0 : total.negative ? -1 : 1;
}

CertifiedSign host_certify_disk(const pw::RealDisk106& disk) {
  if (!finite_binary64(disk.center.hi) ||
      !finite_binary64(disk.center.lo) || !finite_binary64(disk.radius) ||
      disk.radius < 0.0) {
    return {0, kFailureMalformedDisk};
  }
  const double lower_terms[3] = {disk.center.hi, disk.center.lo,
                                 -disk.radius};
  if (host_exact_sum_sign(lower_terms, 3) > 0) {
    return {1, kFailureNone};
  }
  const double upper_terms[3] = {disk.center.hi, disk.center.lo,
                                 disk.radius};
  if (host_exact_sum_sign(upper_terms, 3) < 0) {
    return {-1, kFailureNone};
  }
  return {0, kFailureAmbiguousDisk};
}

bool host_disk_strict_gt(const pw::RealDisk106& left,
                         const pw::RealDisk106& right) {
  const double terms[6] = {
      left.center.hi,   left.center.lo,   -left.radius,
      -right.center.hi, -right.center.lo, -right.radius};
  return host_exact_sum_sign(terms, 6) > 0;
}

struct DirectedHostInterval {
  double lo;
  double hi;
};

DirectedHostInterval host_outward_interval(
    const pw::RealDisk106& disk) {
  const double infinity = std::numeric_limits<double>::infinity();
  const double center = disk.center.hi + disk.center.lo;
  if (!std::isfinite(center)) return {-infinity, infinity};
  const double center_lo = std::nextafter(center, -infinity);
  const double center_hi = std::nextafter(center, infinity);
  const double lower = center_lo - disk.radius;
  const double upper = center_hi + disk.radius;
  if (!std::isfinite(lower) || !std::isfinite(upper)) {
    return {-infinity, infinity};
  }
  return {
      std::nextafter(lower, -infinity),
      std::nextafter(upper, infinity)};
}

CertifiedSign host_certify_disk(
    const pw::RealDisk106& disk,
    const DirectedHostInterval& outer) {
  if (!finite_binary64(disk.center.hi) ||
      !finite_binary64(disk.center.lo) || !finite_binary64(disk.radius) ||
      disk.radius < 0.0) {
    return {0, kFailureMalformedDisk};
  }
  // These branches are only filters.  Each arithmetic operation in `outer`
  // was widened by one binary64 successor/predecessor; an inconclusive box
  // always falls through to the independent fixed-integer computation.
  if (outer.lo > 0.0) return {1, kFailureNone};
  if (outer.hi < 0.0) return {-1, kFailureNone};
  const double lower_terms[3] = {disk.center.hi, disk.center.lo,
                                 -disk.radius};
  if (host_exact_sum_sign(lower_terms, 3) > 0) {
    return {1, kFailureNone};
  }
  const double upper_terms[3] = {disk.center.hi, disk.center.lo,
                                 disk.radius};
  if (host_exact_sum_sign(upper_terms, 3) < 0) {
    return {-1, kFailureNone};
  }
  return {0, kFailureAmbiguousDisk};
}

bool host_exact_stat_pt(const pw::RealDisk106& left,
                        const pw::RealDisk106& middle,
                        const pw::RealDisk106& right,
                        std::int8_t sign);

bool host_filtered_stat_pt(
    const pw::RealDisk106& left,
    const pw::RealDisk106& middle,
    const pw::RealDisk106& right,
    const DirectedHostInterval& left_outer,
    const DirectedHostInterval& middle_outer,
    const DirectedHostInterval& right_outer,
    std::int8_t sign) {
  const auto same_disk = [](const pw::RealDisk106& first,
                            const pw::RealDisk106& second) {
    return first.center.hi == second.center.hi &&
           first.center.lo == second.center.lo &&
           first.radius == second.radius;
  };
  // An interval cannot be strictly above or below itself.  This catches
  // constant source runs without invoking the fixed-integer fallback.
  if (same_disk(left, middle) || same_disk(right, middle)) return false;
  bool certified = false;
  bool rejected = false;
  if (sign > 0) {
    certified = left_outer.lo > middle_outer.hi &&
                right_outer.lo > middle_outer.hi;
    rejected = left_outer.hi <= middle_outer.lo ||
               right_outer.hi <= middle_outer.lo;
  } else {
    certified = middle_outer.lo > left_outer.hi &&
                middle_outer.lo > right_outer.hi;
    rejected = middle_outer.hi <= left_outer.lo ||
               middle_outer.hi <= right_outer.lo;
  }
  if (certified) return true;
  if (rejected) return false;
  return host_exact_stat_pt(left, middle, right, sign);
}

bool host_exact_stat_pt(const pw::RealDisk106& left,
                        const pw::RealDisk106& middle,
                        const pw::RealDisk106& right, std::int8_t sign) {
  return sign > 0
             ? host_disk_strict_gt(left, middle) &&
                   host_disk_strict_gt(right, middle)
             : host_disk_strict_gt(middle, left) &&
                   host_disk_strict_gt(middle, right);
}

}  // namespace

struct Workspace {
  Capacities capacities{};
  std::int8_t* signs = nullptr;
  std::array<DirectEvent*, kStreamCount> direct{};
  std::array<StationaryCandidate*, kStreamCount> stationary{};
  StreamSummary* summaries = nullptr;
  ScanStatus* status = nullptr;
  unsigned char* merkle_a = nullptr;
  unsigned char* merkle_b = nullptr;
  std::uint64_t device_bytes = 0U;
};

struct ReplayCapture {
  Capacities capacities{};
  pw::RealDisk106* required_samples = nullptr;
  ScanStatus* status = nullptr;
  StreamSummary* summaries = nullptr;
  std::array<DirectEvent*, kStreamCount> direct{};
  std::array<StationaryCandidate*, kStreamCount> stationary{};
  cudaEvent_t ready = nullptr;
  std::atomic<bool> enqueued{false};
  std::atomic<bool> event_recorded{false};
  cudaStream_t stream = nullptr;
  std::uint64_t pinned_bytes = 0U;
};

Workspace* create_workspace(Capacities capacities) {
  const Capacities maxima = maximum_capacities();
  for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
    if (capacities.direct[stream] > maxima.direct[stream] ||
        capacities.stationary[stream] > maxima.stationary[stream]) {
      throw std::invalid_argument("event scanner capacity exceeds geometry");
    }
  }
  Workspace* workspace = new Workspace;
  workspace->capacities = capacities;
  try {
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&workspace->signs),
                          platt_dd_transform::kSourceRequiredCount *
                              sizeof(std::int8_t)),
               "cudaMalloc signs");
    workspace->device_bytes +=
        platt_dd_transform::kSourceRequiredCount * sizeof(std::int8_t);
    for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
      if (capacities.direct[stream] != 0U) {
        check_cuda(cudaMalloc(reinterpret_cast<void**>(
                                  &workspace->direct[stream]),
                              capacities.direct[stream] *
                                  sizeof(DirectEvent)),
                   "cudaMalloc direct events");
        workspace->device_bytes +=
            capacities.direct[stream] * sizeof(DirectEvent);
      }
      if (capacities.stationary[stream] != 0U) {
        check_cuda(cudaMalloc(reinterpret_cast<void**>(
                                  &workspace->stationary[stream]),
                              capacities.stationary[stream] *
                                  sizeof(StationaryCandidate)),
                   "cudaMalloc stationary candidates");
        workspace->device_bytes +=
            capacities.stationary[stream] * sizeof(StationaryCandidate);
      }
    }
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&workspace->summaries),
                          kStreamCount * sizeof(StreamSummary)),
               "cudaMalloc summaries");
    workspace->device_bytes += kStreamCount * sizeof(StreamSummary);
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&workspace->status),
                          sizeof(ScanStatus)),
               "cudaMalloc status");
    workspace->device_bytes += sizeof(ScanStatus);
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&workspace->merkle_a),
                          static_cast<std::size_t>(kMerkleLeafCount) * 32U),
               "cudaMalloc Merkle leaves");
    workspace->device_bytes +=
        static_cast<std::uint64_t>(kMerkleLeafCount) * 32U;
    check_cuda(cudaMalloc(reinterpret_cast<void**>(&workspace->merkle_b),
                          static_cast<std::size_t>(kMerkleSecondCount) * 32U),
               "cudaMalloc Merkle nodes");
    workspace->device_bytes +=
        static_cast<std::uint64_t>(kMerkleSecondCount) * 32U;
    return workspace;
  } catch (...) {
    try {
      destroy_workspace(workspace);
    } catch (...) {
    }
    throw;
  }
}

void destroy_workspace(Workspace* workspace) {
  if (workspace == nullptr) return;
  cudaError_t first_error = cudaSuccess;
  auto release = [&first_error](void* pointer) {
    if (pointer == nullptr) return;
    const cudaError_t result = cudaFree(pointer);
    if (first_error == cudaSuccess && result != cudaSuccess) {
      first_error = result;
    }
  };
  release(workspace->signs);
  for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
    release(workspace->direct[stream]);
    release(workspace->stationary[stream]);
  }
  release(workspace->summaries);
  release(workspace->status);
  release(workspace->merkle_a);
  release(workspace->merkle_b);
  delete workspace;
  if (first_error != cudaSuccess) {
    throw std::runtime_error(std::string("cudaFree event workspace: ") +
                             cudaGetErrorString(first_error));
  }
}

DeviceOutputs device_outputs(Workspace* workspace) {
  DeviceOutputs outputs{};
  for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
    outputs.direct[stream] = workspace->direct[stream];
    outputs.stationary[stream] = workspace->stationary[stream];
    outputs.direct_capacities[stream] = workspace->capacities.direct[stream];
    outputs.stationary_capacities[stream] =
        workspace->capacities.stationary[stream];
  }
  outputs.summaries = workspace->summaries;
  outputs.status = workspace->status;
  outputs.merkle_a = workspace->merkle_a;
  outputs.merkle_b = workspace->merkle_b;
  return outputs;
}

void scan_source_required_samples(Workspace* workspace,
                                  const pw::RealDisk106* required_samples,
                                  cudaStream_t stream) {
  if (workspace == nullptr || required_samples == nullptr) {
    throw std::invalid_argument("null event scanner workspace/input");
  }
  check_cuda(cudaMemsetAsync(workspace->status, 0, sizeof(ScanStatus), stream),
             "cudaMemsetAsync scan status");
  check_cuda(cudaMemsetAsync(workspace->summaries, 0,
                             kStreamCount * sizeof(StreamSummary), stream),
             "cudaMemsetAsync stream summaries");
  // ReplayCapture intentionally transfers each fixed-capacity array so the
  // producer never synchronizes on a data-dependent count.  Initialize the
  // unused suffixes as well as the rows written by scan_streams_kernel:
  // copying indeterminate device bytes is nondeterministic and is rejected
  // by compute-sanitizer initcheck even though replay consumes only the
  // authenticated summary counts.
  for (std::size_t event_stream = 0U; event_stream < kStreamCount;
       ++event_stream) {
    if (workspace->capacities.direct[event_stream] != 0U) {
      check_cuda(cudaMemsetAsync(
                     workspace->direct[event_stream], 0,
                     workspace->capacities.direct[event_stream] *
                         sizeof(DirectEvent),
                     stream),
                 "cudaMemsetAsync direct events");
    }
    if (workspace->capacities.stationary[event_stream] != 0U) {
      check_cuda(cudaMemsetAsync(
                     workspace->stationary[event_stream], 0,
                     workspace->capacities.stationary[event_stream] *
                         sizeof(StationaryCandidate),
                     stream),
                 "cudaMemsetAsync stationary candidates");
    }
  }
  const unsigned int blocks =
      (platt_dd_transform::kSourceRequiredCount + kThreads - 1U) / kThreads;
  certify_samples_kernel<<<blocks, kThreads, 0, stream>>>(
      required_samples, workspace->signs, workspace->status);
  check_cuda(cudaPeekAtLastError(), "launch certify_samples_kernel");
  const DeviceOutputs outputs = device_outputs(workspace);
  scan_streams_kernel<<<kStreamCount, kThreads, 0, stream>>>(
      required_samples, workspace->signs, outputs);
  check_cuda(cudaPeekAtLastError(), "launch scan_streams_kernel");
  merkle_leaf_kernel<<<kMerkleLeafCount / kThreads, kThreads, 0, stream>>>(
      required_samples, workspace->signs, outputs);
  check_cuda(cudaPeekAtLastError(), "launch merkle_leaf_kernel");
  const unsigned char* source = workspace->merkle_a;
  unsigned char* destination = workspace->merkle_b;
  std::uint32_t node_count = kMerkleSecondCount;
  std::uint32_t level = 0U;
  while (node_count != 0U) {
    const unsigned int grid = (node_count + kThreads - 1U) / kThreads;
    merkle_node_kernel<<<grid, kThreads, 0, stream>>>(
        source, destination, node_count, level, workspace->status);
    check_cuda(cudaPeekAtLastError(), "launch merkle_node_kernel");
    if (node_count == 1U) break;
    source = destination;
    destination = destination == workspace->merkle_b
                      ? workspace->merkle_a
                      : workspace->merkle_b;
    node_count /= 2U;
    ++level;
  }
  merkle_finish_kernel<<<1U, 1U, 0, stream>>>(destination,
                                               workspace->status);
  check_cuda(cudaPeekAtLastError(), "launch merkle_finish_kernel");
}

const DirectEvent* device_direct_events(const Workspace* workspace,
                                        StreamKind stream) {
  if (workspace == nullptr) return nullptr;
  return workspace->direct[stream_index(stream)];
}

const StationaryCandidate* device_stationary_candidates(
    const Workspace* workspace, StreamKind stream) {
  if (workspace == nullptr) return nullptr;
  return workspace->stationary[stream_index(stream)];
}

const StreamSummary* device_stream_summaries(const Workspace* workspace) {
  return workspace == nullptr ? nullptr : workspace->summaries;
}

const ScanStatus* device_scan_status(const Workspace* workspace) {
  return workspace == nullptr ? nullptr : workspace->status;
}

std::uint64_t workspace_device_bytes(const Workspace* workspace) {
  return workspace == nullptr ? 0U : workspace->device_bytes;
}

static ReplayReport replay_host_artifact(
    const Capacities& capacities,
    std::vector<pw::RealDisk106> required_samples,
    HostArtifact artifact) {
  ReplayReport report;
  report.required_samples = std::move(required_samples);
  report.artifact = std::move(artifact);
  const std::vector<pw::RealDisk106>& samples = report.required_samples;
  if (samples.size() != platt_dd_transform::kSourceRequiredCount) {
    throw std::invalid_argument(
        "host event replay requires exactly 25,741 samples");
  }

  std::vector<std::int8_t> signs(samples.size(), 0);
  std::vector<DirectedHostInterval> outer(samples.size());
  std::uint32_t expected_flags = 0U;
  std::uint32_t certified_count = 0U;
  for (std::size_t index = 0; index < samples.size(); ++index) {
    outer[index] = host_outward_interval(samples[index]);
    const CertifiedSign result =
        host_certify_disk(samples[index], outer[index]);
    signs[index] = result.sign;
    expected_flags |= result.failure;
    if (result.failure == kFailureNone) ++certified_count;
  }

  HostArtifact expected;
  expected.status.failure_flags = expected_flags;
  expected.status.certified_sample_count = certified_count;
  if (expected_flags == 0U) {
    for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
      const int lower = stream_lower(static_cast<std::uint32_t>(stream));
      const int upper = stream_upper(static_cast<std::uint32_t>(stream));
      const int edge_count = upper - lower;
      for (int edge = 0; edge < edge_count; ++edge) {
        const int left_offset = lower + edge;
        if (signs[required_index(left_offset)] !=
            signs[required_index(left_offset + 1)]) {
          DirectEvent event{};
          event.left_sample = left_offset;
          event.right_sample = left_offset + 1;
          event.source_nleft_units = -edge;
          event.source_nright_units = edge_count - edge - 1;
          event.stream = static_cast<std::uint32_t>(stream);
          event.certified_multiplicity_slots = 1U;
          expected.direct[stream].push_back(event);
        }
        if (edge + 1 < edge_count) {
          const std::int8_t left_sign = signs[required_index(left_offset)];
          const std::int8_t middle_sign =
              signs[required_index(left_offset + 1)];
          const std::int8_t right_sign =
              signs[required_index(left_offset + 2)];
          bool selected = false;
          if (left_sign == middle_sign && middle_sign == right_sign) {
            const std::size_t left_index = required_index(left_offset);
            const std::size_t middle_index =
                required_index(left_offset + 1);
            const std::size_t right_index =
                required_index(left_offset + 2);
            selected = host_filtered_stat_pt(
                samples[left_index], samples[middle_index],
                samples[right_index], outer[left_index],
                outer[middle_index], outer[right_index], middle_sign);
          }
          if (selected) {
            StationaryCandidate candidate{};
            candidate.left_sample = left_offset;
            candidate.middle_sample = left_offset + 1;
            candidate.right_sample = left_offset + 2;
            candidate.source_nleft_units_per_slot_if_resolved = -edge;
            candidate.source_nright_units_per_slot_if_resolved =
                edge_count - edge - 2;
            candidate.stream = static_cast<std::uint32_t>(stream);
            candidate.source_positive = middle_sign > 0 ? 1U : 0U;
            candidate.strict_stat_pt = 1U;
            candidate.requires_adaptive_resolution = 1U;
            candidate.certified_multiplicity_slots = 0U;
            candidate.multiplicity_slots_if_resolution_succeeds = 2U;
            expected.stationary[stream].push_back(candidate);
          }
        }
      }
      if (expected.direct[stream].size() >
          capacities.direct[stream]) {
        expected_flags |= kFailureDirectOverflow;
      }
      if (expected.stationary[stream].size() >
          capacities.stationary[stream]) {
        expected_flags |= kFailureStationaryOverflow;
      }
      StreamSummary summary{};
      summary.stream = static_cast<std::uint32_t>(stream);
      summary.lower_sample = lower;
      summary.upper_sample = upper;
      summary.range_sample_count = upper - lower + 1;
      summary.direct_event_count = expected.direct[stream].size();
      summary.stationary_candidate_count = expected.stationary[stream].size();
      summary.certified_direct_multiplicity_slots =
          expected.direct[stream].size();
      for (const DirectEvent& event : expected.direct[stream]) {
        summary.direct_nleft_units += event.source_nleft_units;
        summary.direct_nright_units += event.source_nright_units;
      }
      summary.left_endpoint = {
          lower,
          signs[required_index(lower)] > 0 ? 1U : 0U,
          samples[required_index(lower)]};
      summary.right_endpoint = {
          upper,
          signs[required_index(upper)] > 0 ? 1U : 0U,
          samples[required_index(upper)]};
      expected.summaries[stream] = summary;
    }
  }
  expected.status.failure_flags = expected_flags;

  bool matches =
      report.artifact.status.failure_flags == expected_flags &&
      report.artifact.status.certified_sample_count == certified_count;
  if (expected_flags == 0U) {
    matches = matches &&
              equal_bytes(report.artifact.summaries.data(),
                          expected.summaries.data(),
                          kStreamCount * sizeof(StreamSummary));
    for (std::size_t stream = 0; stream < kStreamCount; ++stream) {
      matches = matches &&
                report.artifact.direct[stream].size() ==
                    expected.direct[stream].size() &&
                report.artifact.stationary[stream].size() ==
                    expected.stationary[stream].size();
      if (!report.artifact.direct[stream].empty()) {
        matches = matches && equal_bytes(
            report.artifact.direct[stream].data(),
            expected.direct[stream].data(),
            expected.direct[stream].size() * sizeof(DirectEvent));
      }
      if (!report.artifact.stationary[stream].empty()) {
        matches = matches && equal_bytes(
            report.artifact.stationary[stream].data(),
            expected.stationary[stream].data(),
            expected.stationary[stream].size() *
                sizeof(StationaryCandidate));
      }
    }
    const Sha256Digest digest = artifact_digest(samples, signs, expected);
    matches = matches && report.artifact.status.digest_valid == 1U &&
              equal_bytes(report.artifact.status.artifact_sha256,
                          digest.data(), digest.size());
  } else {
    matches = matches && report.artifact.status.digest_valid == 0U;
  }
  report.device_matches_host = matches;
  report.shared_endpoints_agree =
      expected_flags == 0U && shared_endpoints_agree(report.artifact.summaries);
  report.accepted = expected_flags == 0U && matches &&
                    report.shared_endpoints_agree;
  if (report.accepted) {
    report.stationary_payload_sha256 =
        stationary_payload_sha256(report.required_samples, report.artifact);
  }
  if (!report.accepted) {
    if (expected_flags != 0U) {
      report.error = "scan failed closed with flags " +
                     std::to_string(expected_flags);
    } else if (!matches) {
      report.error = "device event artifact differs from host replay";
    } else {
      report.error = "shared stream endpoints differ";
    }
  }
  return report;
}

ReplayCapture* create_replay_capture(const Workspace* workspace) {
  if (workspace == nullptr) {
    throw std::invalid_argument("null event scanner replay workspace");
  }
  ReplayCapture* capture = new ReplayCapture;
  capture->capacities = workspace->capacities;
  auto allocate = [capture](auto** pointer, std::size_t count,
                            const char* label) {
    using Element = std::remove_pointer_t<
        std::remove_reference_t<decltype(*pointer)>>;
    if (count == 0U) return;
    check_cuda(cudaHostAlloc(reinterpret_cast<void**>(pointer),
                             count * sizeof(Element),
                             cudaHostAllocPortable),
               label);
    capture->pinned_bytes += count * sizeof(Element);
  };
  try {
    allocate(&capture->required_samples,
             platt_dd_transform::kSourceRequiredCount,
             "cudaHostAlloc replay samples");
    allocate(&capture->status, 1U, "cudaHostAlloc replay status");
    allocate(&capture->summaries, kStreamCount,
             "cudaHostAlloc replay summaries");
    for (std::size_t stream = 0U; stream < kStreamCount; ++stream) {
      allocate(&capture->direct[stream],
               capture->capacities.direct[stream],
               "cudaHostAlloc replay direct events");
      allocate(&capture->stationary[stream],
               capture->capacities.stationary[stream],
               "cudaHostAlloc replay stationary candidates");
    }
    check_cuda(cudaEventCreateWithFlags(
                   &capture->ready,
                   cudaEventDisableTiming | cudaEventBlockingSync),
               "cudaEventCreate replay capture");
    return capture;
  } catch (...) {
    try {
      destroy_replay_capture(capture);
    } catch (...) {
    }
    throw;
  }
}

void destroy_replay_capture(ReplayCapture* capture) {
  if (capture == nullptr) return;
  cudaError_t first_error = cudaSuccess;
  auto remember = [&first_error](cudaError_t status) {
    if (first_error == cudaSuccess && status != cudaSuccess) {
      first_error = status;
    }
  };
  if (capture->enqueued.load(std::memory_order_acquire)) {
    if (capture->event_recorded.load(std::memory_order_acquire) &&
        capture->ready != nullptr) {
      remember(cudaEventSynchronize(capture->ready));
    } else {
      remember(cudaStreamSynchronize(capture->stream));
    }
  }
  if (capture->ready != nullptr) remember(cudaEventDestroy(capture->ready));
  auto release = [&remember](void* pointer) {
    if (pointer != nullptr) remember(cudaFreeHost(pointer));
  };
  release(capture->required_samples);
  release(capture->status);
  release(capture->summaries);
  for (std::size_t stream = 0U; stream < kStreamCount; ++stream) {
    release(capture->direct[stream]);
    release(capture->stationary[stream]);
  }
  delete capture;
  if (first_error != cudaSuccess) {
    throw std::runtime_error(std::string("destroy replay capture: ") +
                             cudaGetErrorString(first_error));
  }
}

void enqueue_replay_capture(
    const Workspace* workspace,
    const pw::RealDisk106* required_samples,
    ReplayCapture* capture, cudaStream_t stream) {
  if (workspace == nullptr || required_samples == nullptr ||
      capture == nullptr) {
    throw std::invalid_argument("null asynchronous event replay input");
  }
  if (capture->capacities.direct != workspace->capacities.direct ||
      capture->capacities.stationary != workspace->capacities.stationary) {
    throw std::invalid_argument(
        "event replay capture capacities differ from workspace");
  }
  bool expected = false;
  if (!capture->enqueued.compare_exchange_strong(
          expected, true, std::memory_order_acq_rel)) {
    throw std::logic_error(
        "event replay capture reused before replay completed");
  }
  capture->stream = stream;
  capture->event_recorded.store(false, std::memory_order_release);
  try {
    check_cuda(cudaMemcpyAsync(
                   capture->required_samples, required_samples,
                   platt_dd_transform::kSourceRequiredCount *
                       sizeof(pw::RealDisk106),
                   cudaMemcpyDeviceToHost, stream),
               "enqueue replay sample copy");
    check_cuda(cudaMemcpyAsync(capture->status, workspace->status,
                               sizeof(ScanStatus), cudaMemcpyDeviceToHost,
                               stream),
               "enqueue replay status copy");
    check_cuda(cudaMemcpyAsync(
                   capture->summaries, workspace->summaries,
                   kStreamCount * sizeof(StreamSummary),
                   cudaMemcpyDeviceToHost, stream),
               "enqueue replay summary copy");
    for (std::size_t event_stream = 0U; event_stream < kStreamCount;
         ++event_stream) {
      const std::uint32_t direct_count =
          capture->capacities.direct[event_stream];
      if (direct_count != 0U) {
        check_cuda(cudaMemcpyAsync(
                       capture->direct[event_stream],
                       workspace->direct[event_stream],
                       direct_count * sizeof(DirectEvent),
                       cudaMemcpyDeviceToHost, stream),
                   "enqueue replay direct-event copy");
      }
      const std::uint32_t stationary_count =
          capture->capacities.stationary[event_stream];
      if (stationary_count != 0U) {
        check_cuda(cudaMemcpyAsync(
                       capture->stationary[event_stream],
                       workspace->stationary[event_stream],
                       stationary_count * sizeof(StationaryCandidate),
                       cudaMemcpyDeviceToHost, stream),
                   "enqueue replay stationary-candidate copy");
      }
    }
    check_cuda(cudaEventRecord(capture->ready, stream),
               "record replay capture readiness");
    capture->event_recorded.store(true, std::memory_order_release);
  } catch (...) {
    // A failed enqueue may have placed a strict prefix of the copies on the
    // stream.  Quiesce that prefix before making the bounded slot reusable.
    if (cudaStreamSynchronize(stream) == cudaSuccess) {
      capture->enqueued.store(false, std::memory_order_release);
    }
    throw;
  }
}

bool replay_capture_ready(const ReplayCapture* capture) {
  if (capture == nullptr) {
    throw std::invalid_argument("null asynchronous event replay capture");
  }
  if (!capture->enqueued.load(std::memory_order_acquire)) return false;
  if (!capture->event_recorded.load(std::memory_order_acquire)) return false;
  const cudaError_t status = cudaEventQuery(capture->ready);
  if (status == cudaSuccess) return true;
  if (status == cudaErrorNotReady) return false;
  throw std::runtime_error(std::string("query replay capture: ") +
                           cudaGetErrorString(status));
}

ReplayReport replay_captured(ReplayCapture* capture) {
  if (capture == nullptr ||
      !capture->enqueued.load(std::memory_order_acquire) ||
      !capture->event_recorded.load(std::memory_order_acquire)) {
    throw std::invalid_argument(
        "asynchronous event replay capture is not enqueued");
  }
  try {
    const cudaError_t synchronized = cudaEventSynchronize(capture->ready);
    if (synchronized != cudaSuccess) {
      throw std::runtime_error(
          std::string("synchronize replay capture: ") +
          cudaGetErrorString(synchronized));
    }
    // From here on the pinned bytes are quiescent.  Even if allocation or
    // semantic replay throws, the slot may safely be destroyed or reused.
    capture->event_recorded.store(false, std::memory_order_release);
    std::vector<pw::RealDisk106> required_samples(
        capture->required_samples,
        capture->required_samples +
            platt_dd_transform::kSourceRequiredCount);
    HostArtifact artifact;
    artifact.status = *capture->status;
    std::memcpy(artifact.summaries.data(), capture->summaries,
                kStreamCount * sizeof(StreamSummary));
    for (std::size_t stream = 0U; stream < kStreamCount; ++stream) {
      const std::size_t direct_count = std::min<std::size_t>(
          artifact.summaries[stream].direct_event_count,
          capture->capacities.direct[stream]);
      if (direct_count != 0U) {
        artifact.direct[stream].assign(
            capture->direct[stream],
            capture->direct[stream] + direct_count);
      }
      const std::size_t stationary_count = std::min<std::size_t>(
          artifact.summaries[stream].stationary_candidate_count,
          capture->capacities.stationary[stream]);
      if (stationary_count != 0U) {
        artifact.stationary[stream].assign(
            capture->stationary[stream],
            capture->stationary[stream] + stationary_count);
      }
    }
    ReplayReport report = replay_host_artifact(
        capture->capacities, std::move(required_samples),
        std::move(artifact));
    capture->enqueued.store(false, std::memory_order_release);
    return report;
  } catch (...) {
    if (!capture->event_recorded.load(std::memory_order_acquire)) {
      capture->enqueued.store(false, std::memory_order_release);
    }
    throw;
  }
}

std::uint64_t replay_capture_pinned_bytes(const ReplayCapture* capture) {
  return capture == nullptr ? 0U : capture->pinned_bytes;
}

ReplayReport replay_and_check(const Workspace* workspace,
                              const pw::RealDisk106* required_samples,
                              cudaStream_t stream) {
  if (workspace == nullptr || required_samples == nullptr) {
    throw std::invalid_argument("null event scanner replay workspace/input");
  }
  check_cuda(cudaStreamSynchronize(stream), "synchronize event scan");
  std::vector<pw::RealDisk106> samples(
      platt_dd_transform::kSourceRequiredCount);
  check_cuda(cudaMemcpy(samples.data(), required_samples,
                        samples.size() * sizeof(pw::RealDisk106),
                        cudaMemcpyDeviceToHost),
             "copy required samples for replay");
  HostArtifact artifact;
  check_cuda(cudaMemcpy(&artifact.status, workspace->status,
                        sizeof(ScanStatus), cudaMemcpyDeviceToHost),
             "copy event scan status");
  check_cuda(cudaMemcpy(artifact.summaries.data(), workspace->summaries,
                        kStreamCount * sizeof(StreamSummary),
                        cudaMemcpyDeviceToHost),
             "copy event stream summaries");
  for (std::size_t event_stream = 0U; event_stream < kStreamCount;
       ++event_stream) {
    const std::size_t direct_count = std::min<std::size_t>(
        artifact.summaries[event_stream].direct_event_count,
        workspace->capacities.direct[event_stream]);
    artifact.direct[event_stream].resize(direct_count);
    if (direct_count != 0U) {
      check_cuda(cudaMemcpy(
                     artifact.direct[event_stream].data(),
                     workspace->direct[event_stream],
                     direct_count * sizeof(DirectEvent),
                     cudaMemcpyDeviceToHost),
                 "copy direct events");
    }
    const std::size_t stationary_count = std::min<std::size_t>(
        artifact.summaries[event_stream].stationary_candidate_count,
        workspace->capacities.stationary[event_stream]);
    artifact.stationary[event_stream].resize(stationary_count);
    if (stationary_count != 0U) {
      check_cuda(cudaMemcpy(
                     artifact.stationary[event_stream].data(),
                     workspace->stationary[event_stream],
                     stationary_count * sizeof(StationaryCandidate),
                     cudaMemcpyDeviceToHost),
                 "copy stationary candidates");
    }
  }
  return replay_host_artifact(workspace->capacities, std::move(samples),
                              std::move(artifact));
}

std::array<unsigned char, 32> recompute_host_artifact_sha256(
    std::span<const pw::RealDisk106> required_samples,
    const HostArtifact& artifact) {
  if (required_samples.size() !=
      platt_dd_transform::kSourceRequiredCount) {
    throw std::invalid_argument(
        "host event artifact requires exactly 25,741 samples");
  }
  std::vector<std::int8_t> signs(required_samples.size(), 0);
  for (std::size_t index = 0; index < required_samples.size(); ++index) {
    const CertifiedSign certified = host_certify_disk(required_samples[index]);
    if (certified.failure != kFailureNone) {
      throw std::invalid_argument(
          "host event artifact contains an uncertified sample");
    }
    signs[index] = certified.sign;
  }
  const std::vector<pw::RealDisk106> owned(
      required_samples.begin(), required_samples.end());
  return artifact_digest(owned, signs, artifact);
}

std::array<unsigned char, 32> stationary_payload_sha256(
    std::span<const pw::RealDisk106> required_samples,
    const HostArtifact& artifact) {
  if (required_samples.size() !=
      platt_dd_transform::kSourceRequiredCount) {
    throw std::invalid_argument(
        "stationary payload requires exactly 25,741 samples");
  }
  std::size_t candidate_count = 0U;
  for (const auto& stream : artifact.stationary) {
    candidate_count += stream.size();
  }
  const Capacities capacities = maximum_capacities();
  const std::size_t maximum_candidates =
      static_cast<std::size_t>(capacities.stationary[0]) +
      capacities.stationary[1] + capacities.stationary[2];
  if (candidate_count > maximum_candidates) {
    throw std::invalid_argument(
        "stationary payload candidate count exceeds scanner capacity");
  }
  std::vector<unsigned char> frame;
  frame.reserve(
      8U + required_samples.size() * sizeof(pw::RealDisk106) +
      candidate_count * sizeof(StationaryCandidate));
  append_u32(&frame, static_cast<std::uint32_t>(required_samples.size()));
  for (const pw::RealDisk106& sample : required_samples) {
    append_disk(&frame, sample);
  }
  append_u32(&frame, static_cast<std::uint32_t>(candidate_count));
  for (std::size_t stream = 0U; stream < kStreamCount; ++stream) {
    for (const StationaryCandidate& candidate :
         artifact.stationary[stream]) {
      append_stationary(&frame, candidate);
    }
  }
  sparkinterval::detail::Sha256 digest;
  digest.update(kStationaryPayloadDomain,
                sizeof(kStationaryPayloadDomain) - 1U);
  digest.update(frame.data(), frame.size());
  return digest.finish();
}

}  // namespace sparkinterval::tg::platt_event_scan

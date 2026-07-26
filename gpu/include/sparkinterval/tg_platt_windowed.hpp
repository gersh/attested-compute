// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include <array>
#include <cstdint>
#include <type_traits>

#include "sparkinterval/tg_dirichlet_lattice.hpp"

namespace sparkinterval::tg::platt_windowed {

// Exact production geometry from djplatt/code, zeta_arb/parameters.h, at
// commit 42b21426718e542daa2b006dc05ea2d7f26426e6.
inline constexpr std::uint32_t kTransformLength = 131072;
inline constexpr std::uint32_t kUpsampling = 4;
inline constexpr std::uint32_t kBucketCount =
    kTransformLength / kUpsampling;
inline constexpr std::uint32_t kFinalFftLength = kTransformLength / 2U;
inline constexpr std::uint32_t kSourceTerms = 768000;
inline constexpr std::uint32_t kTaylorTerms = 23;
inline constexpr std::uint32_t kBucketScale = 5376;
inline constexpr std::uint64_t kWindowStep = 1008;
inline constexpr std::uint64_t kSourceLower = 10000000000ULL;
inline constexpr std::uint64_t kSourceUpper = 3000175332800ULL;
inline constexpr std::uint64_t kFullBlockCount = 2966443783ULL;
inline constexpr std::uint64_t kFullCoverageUpper = 3000175333264ULL;

using RealInterval = dirichlet_lattice::RealInterval;
using ComplexInterval = dirichlet_lattice::ComplexInterval;

// A complex Euclidean disk whose Cartesian center is the exact mathematical
// sum of two binary64 limbs.  `radius` encloses every uncertainty not retained
// in those limbs.  The packed source-v2 payload stores five little-endian
// binary64 words per cell in this field order.
struct DoubleDouble {
  double hi;
  double lo;
};

struct RealDisk106 {
  DoubleDouble center;
  double radius;
};

struct ComplexDisk106 {
  DoubleDouble real;
  DoubleDouble imaginary;
  double radius;
};

// The natural bucket is round(B log(n sqrt(pi))/(2 pi)).  The upstream
// program stores the coefficient at the conjugate-order index N1-bucket.
inline constexpr std::uint32_t conjugate_bucket(
    std::uint32_t natural_bucket) {
  return natural_bucket == 0U ? 0U : kBucketCount - natural_bucket;
}

struct CoreDimensions {
  std::uint32_t terms;
  std::uint32_t buckets;
  std::uint32_t taylor_terms;
  std::uint32_t active_buckets;
};

// The fractional turn round(log(n sqrt(pi))/(2 pi) * 2^192), in
// little-endian limbs.  Multiplication by an integral height is performed
// modulo 2^192.  The rounding contributes at most
// pi*height/2^192 radians of phase error.
struct FixedTurn192 {
  std::uint64_t limb0;
  std::uint64_t limb1;
  std::uint64_t limb2;
};

/*
The first-window source packet is deliberately a small fixed binary format,
not a serialization of a C++ container.  All integers and IEEE-754 binary64
words are little endian.  The 128-byte header is followed by

  gamma_count ComplexInterval values, then
  skn_count ComplexInterval values.

`source_terms` records whether the bucket rows came from the complete
768,000-term source sum or a deliberately partial integration fixture.  A
consumer must not promote a partial packet to source evidence.
*/
inline constexpr std::array<char, 8> kSourcePacketMagic = {
    'P', 'T', '2', '1', 'S', 'R', 'C', '1'};
inline constexpr std::uint32_t kSourcePacketVersion = 1U;
inline constexpr std::uint32_t kSourcePacketEndianTag = 0x01020304U;
inline constexpr std::uint32_t kSourcePacketIntervalEncoding = 1U;
inline constexpr std::array<char, 8> kSourcePacket106Magic = {
    'P', 'T', '2', '1', 'S', 'R', 'C', '2'};
inline constexpr std::array<char, 8> kGammaPacket106Magic = {
    'P', 'T', '2', '1', 'G', 'A', 'M', '2'};
// Canonical all-window log-Gamma Taylor stream.  A producer emits one
// GammaTaylorStreamRecord for each logical source block, in increasing block
// order.  Chunk framing permits a GPU consumer to authenticate bounded input
// before using it; the footer authenticates the complete ordered stream.
inline constexpr std::array<char, 8> kGammaTaylorStreamMagic = {
    'P', 'T', '2', '1', 'G', 'T', 'S', '1'};
inline constexpr std::array<char, 8> kGammaTaylorChunkMagic = {
    'P', 'T', '2', '1', 'G', 'T', 'C', '1'};
inline constexpr std::array<char, 8> kGammaTaylorFooterMagic = {
    'P', 'T', '2', '1', 'G', 'T', 'F', '1'};
inline constexpr std::uint32_t kSourcePacket106Version = 2U;
inline constexpr std::uint32_t kSourcePacket106Encoding = 2U;
inline constexpr std::uint32_t kGammaTaylorStreamVersion = 1U;
inline constexpr std::uint32_t kGammaTaylorStreamEncoding = 1U;
inline constexpr std::uint32_t kGammaTaylorDegree = 6U;
inline constexpr std::uint32_t kGammaTaylorPrecision = 256U;
inline constexpr std::array<char, 8> kRequiredSignPacketMagic = {
    'P', 'T', '2', '1', 'S', 'G', 'N', '1'};
inline constexpr std::uint32_t kRequiredSignPacketVersion = 1U;
inline constexpr std::uint32_t kRequiredSignSampleEncoding = 1U;
inline constexpr std::uint32_t kRequiredSignBitEncoding = 1U;
inline constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";

#pragma pack(push, 1)
struct SourcePacketHeader {
  std::array<char, 8> magic;
  std::uint32_t version;
  std::uint32_t header_bytes;
  std::uint32_t endian_tag;
  std::uint32_t interval_encoding;
  std::uint32_t bucket_count;
  std::uint32_t taylor_terms;
  std::uint32_t source_terms;
  std::uint32_t reserved_zero;
  std::uint64_t window_center;
  std::uint64_t gamma_count;
  std::uint64_t skn_count;
  std::uint64_t payload_bytes;
  std::uint64_t gamma_fnv1a64;
  std::uint64_t skn_fnv1a64;
  std::array<char, 40> upstream_commit;
};

// A bounded, replayable handoff from the source transform to interpolation
// and zero isolation.  The payload is `sample_bytes` packed triples
// `(center_hi, center_lo, radius)`, followed by `sign_bytes` LSB-first bits
// (one means positive).  A producer must refuse to emit the packet if any
// retained disk contains zero.  The full campaign streams this payload
// ephemerally and retains only domain-separated hashes and event artifacts.
struct RequiredSignPacketHeader {
  std::array<char, 8> magic;
  std::uint32_t version;
  std::uint32_t header_bytes;
  std::uint32_t endian_tag;
  std::uint32_t sample_encoding;
  std::uint32_t sign_encoding;
  std::uint32_t source_terms;
  std::uint32_t required_begin;
  std::uint32_t required_end;
  std::uint32_t required_count;
  std::uint32_t reserved_zero;
  std::uint64_t window_center;
  std::uint64_t sample_bytes;
  std::uint64_t sign_bytes;
  std::uint64_t sample_fnv1a64;
  std::uint64_t sign_fnv1a64;
  std::uint64_t source_packet_bytes;
  std::array<char, 64> source_packet_sha256;
  std::array<char, 40> upstream_commit;
};
#pragma pack(pop)

// Fixed binary64 projection of a rigorous FLINT/Arb Taylor enclosure for
//
//   log Gamma(1/4 + i (T+u)/2) + pi (T+u)/4,  |u| <= 2688.
//
// Every RealInterval endpoint is rounded outwards.  The two fixed-turn values
// retain the constant and source-grid-linear imaginary phase at Q192; their
// errors are absolute angular errors in radians.  `logarithm_remainder` is a
// nonnegative upper bound for the complex degree-six Taylor remainder.  The
// Gaussian term is deliberately absent and is evaluated exactly from u by
// the GPU consumer.
struct GammaTaylorStreamRecord {
  RealInterval real_coefficients[kGammaTaylorDegree];
  RealInterval imaginary_coefficients[kGammaTaylorDegree];
  FixedTurn192 phase_anchor;
  FixedTurn192 phase_grid_step;
  double phase_anchor_error;
  double phase_grid_step_error;
  double logarithm_remainder;
};

// All fields and records are stored as little-endian bytes.  The header binds
// the source geometry, both source revisions, and the reviewed Platt source
// set.  The SHA-256 fields in the chunk/footer are raw 32-byte digests.
#pragma pack(push, 1)
struct GammaTaylorStreamHeader {
  std::array<char, 8> magic;
  std::uint32_t version;
  std::uint32_t header_bytes;
  std::uint32_t endian_tag;
  std::uint32_t record_encoding;
  std::uint32_t record_bytes;
  std::uint32_t chunk_records;
  std::uint32_t degree;
  std::uint32_t precision_bits;
  std::uint64_t source_lower;
  std::uint64_t source_step;
  std::uint64_t full_block_count;
  std::uint64_t first_block;
  std::uint64_t block_count;
  std::int64_t radius_numerator;
  std::uint64_t radius_denominator;
  std::int64_t grid_step_numerator;
  std::uint64_t grid_step_denominator;
  std::uint64_t gaussian_h;
  std::array<char, 40> upstream_commit;
  std::array<char, 40> flint_commit;
  std::array<unsigned char, 32> reviewed_source_sha256;
  std::array<char, 48> contract_id;
  std::array<unsigned char, 40> reserved_zero;
};

struct GammaTaylorChunkHeader {
  std::array<char, 8> magic;
  std::uint32_t version;
  std::uint32_t header_bytes;
  std::uint64_t first_block;
  std::uint32_t record_count;
  std::uint32_t reserved_zero;
  std::uint64_t payload_bytes;
  std::array<unsigned char, 32> payload_sha256;
};

struct GammaTaylorStreamFooter {
  std::array<char, 8> magic;
  std::uint32_t version;
  std::uint32_t footer_bytes;
  std::uint64_t first_block;
  std::uint64_t block_count;
  std::uint64_t chunk_count;
  std::uint64_t record_payload_bytes;
  std::uint64_t authenticated_stream_bytes;
  std::array<unsigned char, 32> header_sha256;
  std::array<unsigned char, 32> stream_sha256;
  std::array<unsigned char, 8> reserved_zero;
};
#pragma pack(pop)

static_assert(kBucketCount == 32768U);
static_assert(kSourceLower + kWindowStep * kFullBlockCount ==
              kFullCoverageUpper);
static_assert(sizeof(RealInterval) == 16U);
static_assert(sizeof(ComplexInterval) == 32U);
static_assert(sizeof(DoubleDouble) == 16U);
static_assert(sizeof(RealDisk106) == 24U);
static_assert(sizeof(ComplexDisk106) == 40U);
static_assert(sizeof(FixedTurn192) == 24U);
static_assert(sizeof(SourcePacketHeader) == 128U);
static_assert(sizeof(RequiredSignPacketHeader) == 200U);
static_assert(sizeof(GammaTaylorStreamRecord) == 264U);
static_assert(alignof(GammaTaylorStreamRecord) == alignof(double));
static_assert(sizeof(GammaTaylorStreamHeader) == 320U);
static_assert(sizeof(GammaTaylorChunkHeader) == 72U);
static_assert(sizeof(GammaTaylorStreamFooter) == 128U);
static_assert(std::is_trivially_copyable_v<SourcePacketHeader>);
static_assert(std::is_trivially_copyable_v<RequiredSignPacketHeader>);
static_assert(std::is_trivially_copyable_v<GammaTaylorStreamRecord>);
static_assert(std::is_trivially_copyable_v<GammaTaylorStreamHeader>);
static_assert(std::is_trivially_copyable_v<GammaTaylorChunkHeader>);
static_assert(std::is_trivially_copyable_v<GammaTaylorStreamFooter>);
static_assert(sizeof(kUpstreamCommit) == 41U);

}  // namespace sparkinterval::tg::platt_windowed

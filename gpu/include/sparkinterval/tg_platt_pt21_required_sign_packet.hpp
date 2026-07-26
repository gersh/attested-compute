// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// In-worker encoder for the `PT21SGN1` required-region DD/sign packet.
//
// The V2 fused worker never retains this packet as an artifact: it is built
// from the replay-owned 25,741 disks, hashed, streamed into the block-input
// frame, and dropped.  Retaining one packet per window would need 1.8428 PB.
//
// Fail-closed by construction: an invalid or sign-ambiguous disk throws, so a
// completed transform with an unresolved finite predicate can never produce a
// packet, a Turing artifact bound to a packet digest, or a `PT21BLK1`.
//
// Field honesty note.  `source_packet_bytes`/`source_packet_sha256` name the
// upstream *input* bytes that produced this window.  V1 bound its 31 MB source
// packet there.  V2 has no such packet, so this encoder binds the exact
// 312-byte authenticated Gamma V2 stream record for the same logical block --
// the actual input the accumulator and transform consumed.  It never places an
// event digest, scanner Merkle root, or any output commitment in that field.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_windowed.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace sparkinterval::tg::platt_pt21_required_sign_packet {

namespace pw = sparkinterval::tg::platt_windowed;

inline constexpr char kMagic[] = "PT21SGN1";
inline constexpr std::uint32_t kVersion = 1U;
inline constexpr std::size_t kHeaderBytes = 200U;
inline constexpr std::uint32_t kEndianTag = 0x01020304U;
inline constexpr std::uint32_t kSampleEncoding = 1U;
inline constexpr std::uint32_t kSignEncoding = 1U;
inline constexpr std::uint32_t kSourceTerms = 768'000U;
inline constexpr std::uint32_t kRequiredBegin = 52'666U;
inline constexpr std::uint32_t kRequiredEnd = 78'406U;
inline constexpr std::uint32_t kRequiredCount = 25'741U;
inline constexpr std::uint64_t kSourceLowerCenter = 10'000'000'504ULL;
inline constexpr std::uint64_t kSourceStep = 1'008ULL;
inline constexpr std::uint64_t kFullBlockCount = 2'966'443'783ULL;
inline constexpr std::size_t kSampleBytes = 24U;
inline constexpr std::size_t kSampleTotalBytes =
    kRequiredCount * kSampleBytes;
inline constexpr std::size_t kSignTotalBytes = (kRequiredCount + 7U) / 8U;
inline constexpr std::size_t kPacketBytes =
    kHeaderBytes + kSampleTotalBytes + kSignTotalBytes;
inline constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";

// Historical PT21SGN1 v1 wire checksum.  The offset basis is not the standard
// FNV-1a-64 basis; SHA-256 remains the cryptographic integrity boundary.
inline constexpr std::uint64_t kChecksumOffset = 1'469'598'103'934'665'603ULL;
inline constexpr std::uint64_t kChecksumPrime = 1'099'511'628'211ULL;

static_assert(kRequiredEnd - kRequiredBegin + 1U == kRequiredCount);
static_assert(sizeof(pw::RealDisk106) == kSampleBytes);
static_assert(kPacketBytes == 621'202U);

class RequiredSignPacketError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

inline std::uint64_t wire_checksum(const unsigned char* data,
                                   std::size_t size) {
  std::uint64_t value = kChecksumOffset;
  for (std::size_t index = 0U; index < size; ++index) {
    value ^= static_cast<std::uint64_t>(data[index]);
    value *= kChecksumPrime;
  }
  return value;
}

inline void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0U; index < 4U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

inline void store_u64(unsigned char* data, std::uint64_t value) {
  for (unsigned int index = 0U; index < 8U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

inline std::uint64_t window_center(std::uint64_t block) {
  if (block >= kFullBlockCount) {
    throw RequiredSignPacketError(
        "required-sign packet block leaves the PT21 campaign");
  }
  return kSourceLowerCenter + block * kSourceStep;
}

// Recompute the sign of one exact DD disk under the same fail-closed rule the
// Python decoder applies.  Returns true for a certified positive centre.
inline bool certified_positive(const pw::RealDisk106& disk,
                               std::size_t index) {
  const double hi = disk.center.hi;
  const double lo = disk.center.lo;
  const double radius = disk.radius;
  const bool finite =
      std::isfinite(hi) && std::isfinite(lo) && std::isfinite(radius);
  if (!finite || radius < 0.0) {
    throw RequiredSignPacketError(
        "invalid DD disk at retained index " + std::to_string(index));
  }
  const double magnitude_hi = hi < 0.0 ? -hi : hi;
  const double magnitude_lo = lo < 0.0 ? -lo : lo;
  const double center_lower_raw = magnitude_hi - magnitude_lo;
  const double center_lower =
      center_lower_raw > 0.0 ? center_lower_raw : 0.0;
  if (!(center_lower > radius) || hi == 0.0) {
    throw RequiredSignPacketError(
        "ambiguous DD disk at retained index " + std::to_string(index));
  }
  return hi > 0.0;
}

// Build the exact 621,202-byte packet wire for one block.
//
// `gamma_record` must be the exact authenticated Gamma V2 stream record bytes
// for the same logical block.  `samples` must be the replay-owned required
// view, in retained order.
inline std::vector<unsigned char> encode_packet(
    std::uint64_t block, std::span<const pw::RealDisk106> samples,
    std::span<const unsigned char> gamma_record) {
  if (samples.size() != kRequiredCount) {
    throw RequiredSignPacketError(
        "required-sign packet needs exactly 25741 retained disks");
  }
  if (gamma_record.empty()) {
    throw RequiredSignPacketError(
        "required-sign packet needs the nonempty source input record");
  }
  const std::uint64_t center = window_center(block);

  std::vector<unsigned char> raw(kPacketBytes, 0U);
  unsigned char* const sample_region = raw.data() + kHeaderBytes;
  unsigned char* const sign_region = sample_region + kSampleTotalBytes;
  for (std::size_t index = 0U; index < kRequiredCount; ++index) {
    const pw::RealDisk106& disk = samples[index];
    // The wire is little-endian binary64 (hi, lo, radius); the host layout is
    // identical on every supported target, and the static_asserts above pin
    // the size.  Copying the struct preserves the exact bit patterns the
    // scanner and the independent host replay both certified.
    std::memcpy(sample_region + index * kSampleBytes, &disk, kSampleBytes);
    if (certified_positive(disk, index)) {
      sign_region[index / 8U] |=
          static_cast<unsigned char>(1U << (index % 8U));
    }
  }

  const Sha256Digest gamma_digest =
      sha256(gamma_record.data(), gamma_record.size());
  const std::string gamma_hex = lowercase_hex(gamma_digest);
  if (gamma_hex.size() != 64U) {
    throw RequiredSignPacketError("source input digest is not 64 hex digits");
  }

  unsigned char* const header = raw.data();
  std::memcpy(header, kMagic, 8U);
  store_u32(header + 8U, kVersion);
  store_u32(header + 12U, static_cast<std::uint32_t>(kHeaderBytes));
  store_u32(header + 16U, kEndianTag);
  store_u32(header + 20U, kSampleEncoding);
  store_u32(header + 24U, kSignEncoding);
  store_u32(header + 28U, kSourceTerms);
  store_u32(header + 32U, kRequiredBegin);
  store_u32(header + 36U, kRequiredEnd);
  store_u32(header + 40U, kRequiredCount);
  store_u32(header + 44U, 0U);
  store_u64(header + 48U, center);
  store_u64(header + 56U, static_cast<std::uint64_t>(kSampleTotalBytes));
  store_u64(header + 64U, static_cast<std::uint64_t>(kSignTotalBytes));
  store_u64(header + 72U,
            wire_checksum(sample_region, kSampleTotalBytes));
  store_u64(header + 80U, wire_checksum(sign_region, kSignTotalBytes));
  store_u64(header + 88U, static_cast<std::uint64_t>(gamma_record.size()));
  std::memcpy(header + 96U, gamma_hex.data(), 64U);
  std::memcpy(header + 160U, kUpstreamCommit, 40U);
  return raw;
}

}  // namespace sparkinterval::tg::platt_pt21_required_sign_packet

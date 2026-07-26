// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// Source-authenticated, two-limb replacement for the original binary64-box
// Gamma Taylor stream.  V1 remains a supported diagnostic format; it must not
// be silently interpreted as this format.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_windowed.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <istream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace sparkinterval::tg::platt_gamma_stream_v2 {

namespace pw = sparkinterval::tg::platt_windowed;

inline constexpr std::array<char, 8> kStreamMagic = {
    'P', 'T', '2', '1', 'G', 'T', 'S', '2'};
inline constexpr std::array<char, 8> kChunkMagic = {
    'P', 'T', '2', '1', 'G', 'T', 'C', '2'};
inline constexpr std::array<char, 8> kFooterMagic = {
    'P', 'T', '2', '1', 'G', 'T', 'F', '2'};
inline constexpr std::uint32_t kVersion = 2U;
inline constexpr std::uint32_t kEncoding = 2U;
inline constexpr std::uint32_t kDegree = 6U;
inline constexpr std::uint32_t kPrecisionBits = 256U;
inline constexpr std::string_view kHashDomain =
    "sparkinterval/pt21-gamma-taylor-stream/v2";
inline constexpr std::string_view kContractId =
    "sparkinterval/pt21-gamma-taylor-stream/v2";
inline constexpr std::string_view kFlintCommit =
    "8d5454b96761fafe4d5a9da76a369a602f500f49";
inline constexpr std::array<unsigned char, 32> kReviewedSourceSha256 = {
    0x9a, 0x74, 0x84, 0x90, 0xb3, 0x27, 0xb1, 0x02,
    0xd5, 0x35, 0x06, 0xe3, 0x90, 0xa4, 0x2a, 0xfa,
    0xc7, 0x96, 0xa5, 0xb4, 0x2b, 0x42, 0x06, 0x0f,
    0xe8, 0x2a, 0xa8, 0xf5, 0x74, 0x4b, 0xb1, 0x52,
};

// A disk for each complex Taylor coefficient.  Its centre is the exact sum
// of the two binary64 limbs and its radius includes both Arb coordinate
// projection errors.  Keeping the phase anchor and one-grid-step phase at
// Q192 avoids evaluating the enormous constant/linear imaginary terms in
// floating point.  logarithm_remainder is the source's order-six complex
// integral-Taylor remainder.
struct Record {
  pw::ComplexDisk106 coefficients[kDegree];
  pw::FixedTurn192 phase_anchor;
  pw::FixedTurn192 phase_grid_step;
  double phase_anchor_error;
  double phase_grid_step_error;
  double logarithm_remainder;
};

#pragma pack(push, 1)
struct Header {
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
  // Exact rational 1/(2 H^2) = 1/26912, projected to a DD disk.  These bits
  // are fixed by the contract and independently checked by every reader.
  pw::RealDisk106 inverse_gaussian_denominator;
  std::array<char, 40> upstream_commit;
  std::array<char, 40> flint_commit;
  std::array<unsigned char, 32> reviewed_source_sha256;
  std::array<char, 48> contract_id;
  std::array<unsigned char, 32> reserved_zero;
};

struct ChunkHeader {
  std::array<char, 8> magic;
  std::uint32_t version;
  std::uint32_t header_bytes;
  std::uint64_t first_block;
  std::uint32_t record_count;
  std::uint32_t reserved_zero;
  std::uint64_t payload_bytes;
  std::array<unsigned char, 32> payload_sha256;
};

struct Footer {
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

static_assert(sizeof(Record) == 312U);
static_assert(alignof(Record) == alignof(double));
static_assert(sizeof(Header) == 336U);
static_assert(sizeof(ChunkHeader) == 72U);
static_assert(sizeof(Footer) == 128U);

// Canonical outward DD enclosure of the exact rational 1/26912.  The radius
// is the exact remaining rational rounded toward +infinity.
inline constexpr pw::RealDisk106 kInverseGaussianDenominator = {
    {0x1.37b4824872744p-15, 0x1.f5a681ac98332p-69},
    0x1.ceaff16389e4ap-124};

class Error : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct AuthenticatedChunk {
  std::uint64_t first_block = 0U;
  std::vector<Record> records;
  Sha256Digest payload_sha256{};
};

inline bool all_zero(const void* raw, std::size_t size) {
  const auto* bytes = static_cast<const unsigned char*>(raw);
  return std::all_of(bytes, bytes + size,
                     [](unsigned char value) { return value == 0U; });
}

inline bool padded_ascii_equal(const char* raw, std::size_t size,
                               std::string_view expected) {
  return expected.size() <= size &&
         std::memcmp(raw, expected.data(), expected.size()) == 0 &&
         all_zero(raw + expected.size(), size - expected.size());
}

inline bool same_bits(double x, double y) {
  return std::bit_cast<std::uint64_t>(x) == std::bit_cast<std::uint64_t>(y);
}

inline void validate_real_disk(const pw::RealDisk106& value,
                               const char* label) {
  if (!std::isfinite(value.center.hi) ||
      !std::isfinite(value.center.lo) || !std::isfinite(value.radius) ||
      value.radius < 0.0) {
    throw Error(std::string("Gamma Taylor V2 has invalid ") + label);
  }
}

inline void validate_record(const Record& record) {
  for (std::uint32_t degree = 0U; degree < kDegree; ++degree) {
    const auto& value = record.coefficients[degree];
    if (!std::isfinite(value.real.hi) ||
        !std::isfinite(value.real.lo) ||
        !std::isfinite(value.imaginary.hi) ||
        !std::isfinite(value.imaginary.lo) ||
        !std::isfinite(value.radius) || value.radius < 0.0) {
      throw Error("Gamma Taylor V2 has an invalid coefficient disk");
    }
  }
  if (!std::isfinite(record.phase_anchor_error) ||
      record.phase_anchor_error < 0.0 ||
      !std::isfinite(record.phase_grid_step_error) ||
      record.phase_grid_step_error < 0.0 ||
      !std::isfinite(record.logarithm_remainder) ||
      record.logarithm_remainder < 0.0) {
    throw Error("Gamma Taylor V2 has an invalid projection error");
  }
}

// Authentication is deliberately host-side and fail-before-yield.  A caller
// must consume to false or call finish(); accepting an authenticated prefix
// without checking the footer is an error at the campaign layer.
class Reader {
 public:
  Reader(std::istream& input,
         std::optional<std::uint64_t> expected_first_block = std::nullopt,
         std::optional<std::uint64_t> expected_block_count = std::nullopt,
         std::optional<Sha256Digest> expected_stream_sha256 = std::nullopt)
      : input_(input), expected_stream_sha256_(expected_stream_sha256) {
    if constexpr (std::endian::native != std::endian::little) {
      throw Error("Gamma Taylor V2 requires a little-endian host");
    }
    static_assert(std::numeric_limits<double>::is_iec559);
    read_exact(&header_, sizeof(header_), "Gamma Taylor V2 header");
    validate_header(expected_first_block, expected_block_count);
    header_sha256_ = sha256(&header_, sizeof(header_));
    stream_hasher_.update(kHashDomain.data(), kHashDomain.size());
    stream_hasher_.update(&header_, sizeof(header_));
    authenticated_stream_bytes_ = sizeof(header_);
  }

  const Header& header() const { return header_; }
  bool complete() const { return complete_; }
  std::uint64_t consumed_records() const { return consumed_; }
  std::uint64_t chunk_count() const { return chunks_; }
  const Sha256Digest& stream_sha256() const {
    if (!complete_) throw Error("V2 stream digest requested before footer");
    return stream_sha256_;
  }

  bool next(AuthenticatedChunk& output) {
    if (complete_) return false;
    if (consumed_ == header_.block_count) {
      verify_footer();
      return false;
    }
    ChunkHeader chunk{};
    read_exact(&chunk, sizeof(chunk), "Gamma Taylor V2 chunk header");
    const std::uint64_t remaining = header_.block_count - consumed_;
    const std::uint32_t expected_count = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(header_.chunk_records, remaining));
    const std::uint64_t expected_bytes =
        static_cast<std::uint64_t>(expected_count) * sizeof(Record);
    if (chunk.magic != kChunkMagic || chunk.version != kVersion ||
        chunk.header_bytes != sizeof(chunk) ||
        chunk.first_block != header_.first_block + consumed_ ||
        chunk.record_count != expected_count || chunk.reserved_zero != 0U ||
        chunk.payload_bytes != expected_bytes) {
      throw Error("Gamma Taylor V2 chunk framing differs");
    }
    std::vector<Record> records(expected_count);
    read_exact(records.data(), static_cast<std::size_t>(expected_bytes),
               "Gamma Taylor V2 chunk payload");
    const Sha256Digest payload_sha =
        sha256(records.data(), static_cast<std::size_t>(expected_bytes));
    if (payload_sha != chunk.payload_sha256) {
      throw Error("Gamma Taylor V2 chunk payload digest differs");
    }
    for (const auto& record : records) validate_record(record);
    stream_hasher_.update(&chunk, sizeof(chunk));
    stream_hasher_.update(records.data(),
                          static_cast<std::size_t>(expected_bytes));
    output = {chunk.first_block, std::move(records), payload_sha};
    consumed_ += expected_count;
    record_payload_bytes_ += expected_bytes;
    authenticated_stream_bytes_ += sizeof(chunk) + expected_bytes;
    ++chunks_;
    return true;
  }

  void finish() {
    AuthenticatedChunk ignored;
    while (next(ignored)) {
    }
  }

 private:
  void read_exact(void* output, std::size_t size, const char* label) {
    input_.read(static_cast<char*>(output), static_cast<std::streamsize>(size));
    if (input_.gcount() != static_cast<std::streamsize>(size)) {
      throw Error(std::string(label) + " is truncated");
    }
  }

  void validate_header(
      std::optional<std::uint64_t> expected_first_block,
      std::optional<std::uint64_t> expected_block_count) {
    auto require = [](bool condition, const char* field) {
      if (!condition) {
        throw Error(std::string("Gamma Taylor V2 fixed header differs at ") +
                    field);
      }
    };
    require(header_.magic == kStreamMagic, "magic");
    require(header_.version == kVersion, "version");
    require(header_.header_bytes == sizeof(header_), "header_bytes");
    require(header_.endian_tag == pw::kSourcePacketEndianTag, "endian_tag");
    require(header_.record_encoding == kEncoding, "record_encoding");
    require(header_.record_bytes == sizeof(Record), "record_bytes");
    require(header_.chunk_records >= 1U &&
                header_.chunk_records <= (1U << 20U),
            "chunk_records");
    require(header_.degree == kDegree, "degree");
    require(header_.precision_bits == kPrecisionBits, "precision_bits");
    require(header_.source_lower == pw::kSourceLower, "source_lower");
    require(header_.source_step == pw::kWindowStep, "source_step");
    require(header_.full_block_count == pw::kFullBlockCount,
            "full_block_count");
    require(header_.radius_numerator == 2688, "radius_numerator");
    require(header_.radius_denominator == 1U, "radius_denominator");
    require(header_.grid_step_numerator == 21, "grid_step_numerator");
    require(header_.grid_step_denominator == 128U,
            "grid_step_denominator");
    require(header_.gaussian_h == 116U, "gaussian_h");
    require(same_bits(header_.inverse_gaussian_denominator.center.hi,
                      kInverseGaussianDenominator.center.hi) &&
                same_bits(header_.inverse_gaussian_denominator.center.lo,
                          kInverseGaussianDenominator.center.lo) &&
                same_bits(header_.inverse_gaussian_denominator.radius,
                          kInverseGaussianDenominator.radius),
            "inverse_gaussian_denominator");
    require(std::memcmp(header_.upstream_commit.data(), pw::kUpstreamCommit,
                        header_.upstream_commit.size()) == 0,
            "upstream_commit");
    require(std::memcmp(header_.flint_commit.data(), kFlintCommit.data(),
                        header_.flint_commit.size()) == 0,
            "flint_commit");
    require(header_.reviewed_source_sha256 == kReviewedSourceSha256,
            "reviewed_source_sha256");
    require(padded_ascii_equal(header_.contract_id.data(),
                               header_.contract_id.size(), kContractId),
            "contract_id");
    require(all_zero(header_.reserved_zero.data(),
                     header_.reserved_zero.size()),
            "reserved_zero");
    if (header_.block_count == 0U ||
        header_.first_block >= pw::kFullBlockCount ||
        header_.block_count > pw::kFullBlockCount - header_.first_block) {
      throw Error("Gamma Taylor V2 stream range is invalid");
    }
    if (expected_first_block &&
        header_.first_block != *expected_first_block) {
      throw Error("Gamma Taylor V2 first block differs");
    }
    if (expected_block_count &&
        header_.block_count != *expected_block_count) {
      throw Error("Gamma Taylor V2 block count differs");
    }
  }

  void verify_footer() {
    Footer footer{};
    read_exact(&footer, sizeof(footer), "Gamma Taylor V2 footer");
    stream_sha256_ = stream_hasher_.finish();
    if (footer.magic != kFooterMagic || footer.version != kVersion ||
        footer.footer_bytes != sizeof(footer) ||
        footer.first_block != header_.first_block ||
        footer.block_count != header_.block_count ||
        footer.chunk_count != chunks_ ||
        footer.record_payload_bytes != record_payload_bytes_ ||
        footer.authenticated_stream_bytes != authenticated_stream_bytes_ ||
        footer.header_sha256 != header_sha256_ ||
        footer.stream_sha256 != stream_sha256_ ||
        !all_zero(footer.reserved_zero.data(), footer.reserved_zero.size())) {
      throw Error("Gamma Taylor V2 footer differs");
    }
    if (expected_stream_sha256_ &&
        stream_sha256_ != *expected_stream_sha256_) {
      throw Error("Gamma Taylor V2 stream digest differs");
    }
    char trailing = 0;
    input_.read(&trailing, 1);
    if (input_.gcount() != 0) {
      throw Error("trailing bytes follow the Gamma Taylor V2 footer");
    }
    complete_ = true;
  }

  std::istream& input_;
  Header header_{};
  std::optional<Sha256Digest> expected_stream_sha256_;
  detail::Sha256 stream_hasher_;
  Sha256Digest header_sha256_{};
  Sha256Digest stream_sha256_{};
  std::uint64_t consumed_ = 0U;
  std::uint64_t chunks_ = 0U;
  std::uint64_t record_payload_bytes_ = 0U;
  std::uint64_t authenticated_stream_bytes_ = 0U;
  bool complete_ = false;
};

}  // namespace sparkinterval::tg::platt_gamma_stream_v2

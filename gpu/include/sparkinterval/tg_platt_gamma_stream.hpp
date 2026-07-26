// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

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

namespace sparkinterval::tg::platt_gamma_stream {

namespace pw = sparkinterval::tg::platt_windowed;

inline constexpr std::string_view kStreamHashDomain =
    "sparkinterval/pt21-gamma-taylor-stream/v1";
inline constexpr std::string_view kFlintCommit =
    "8d5454b96761fafe4d5a9da76a369a602f500f49";
inline constexpr std::string_view kContractId =
    "sparkinterval/pt21-gamma-taylor-stream/v1";
inline constexpr std::array<unsigned char, 32> kReviewedSourceSha256 = {
    0x9a, 0x74, 0x84, 0x90, 0xb3, 0x27, 0xb1, 0x02,
    0xd5, 0x35, 0x06, 0xe3, 0x90, 0xa4, 0x2a, 0xfa,
    0xc7, 0x96, 0xa5, 0xb4, 0x2b, 0x42, 0x06, 0x0f,
    0xe8, 0x2a, 0xa8, 0xf5, 0x74, 0x4b, 0xb1, 0x52,
};

class GammaTaylorStreamError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct AuthenticatedChunk {
  std::uint64_t first_block = 0;
  std::vector<pw::GammaTaylorStreamRecord> records;
  Sha256Digest payload_sha256{};
};

inline bool all_zero(const void* raw, std::size_t size) {
  const auto* bytes = static_cast<const unsigned char*>(raw);
  return std::all_of(bytes, bytes + size,
                     [](unsigned char value) { return value == 0U; });
}

inline bool padded_ascii_equal(const char* raw, std::size_t size,
                               std::string_view expected) {
  if (expected.size() > size ||
      std::memcmp(raw, expected.data(), expected.size()) != 0) {
    return false;
  }
  return all_zero(raw + expected.size(), size - expected.size());
}

inline void validate_record(const pw::GammaTaylorStreamRecord& record) {
  auto interval = [](pw::RealInterval value) {
    return std::isfinite(value.lo) && std::isfinite(value.hi) &&
           value.lo <= value.hi;
  };
  for (std::uint32_t degree = 0; degree < pw::kGammaTaylorDegree; ++degree) {
    if (!interval(record.real_coefficients[degree]) ||
        !interval(record.imaginary_coefficients[degree])) {
      throw GammaTaylorStreamError(
          "Gamma Taylor record has an invalid coefficient interval");
    }
  }
  if (!std::isfinite(record.phase_anchor_error) ||
      record.phase_anchor_error < 0.0 ||
      !std::isfinite(record.phase_grid_step_error) ||
      record.phase_grid_step_error < 0.0 ||
      !std::isfinite(record.logarithm_remainder) ||
      record.logarithm_remainder < 0.0) {
    throw GammaTaylorStreamError(
        "Gamma Taylor record has an invalid projection error");
  }
}

// Bounded-memory, fail-before-yield decoder for the production Gamma stream.
// `next` authenticates the entire chunk and validates every record before it
// moves any bytes into `output`.  The caller must consume through the final
// false result (or call `finish`) so the footer and whole-stream digest are
// checked; accepting a prefix is deliberately an error.
class GammaTaylorStreamReader {
 public:
  GammaTaylorStreamReader(
      std::istream& input,
      std::optional<std::uint64_t> expected_first_block = std::nullopt,
      std::optional<std::uint64_t> expected_block_count = std::nullopt,
      std::optional<Sha256Digest> expected_stream_sha256 = std::nullopt)
      : input_(input), expected_stream_sha256_(expected_stream_sha256) {
    if constexpr (std::endian::native != std::endian::little) {
      throw GammaTaylorStreamError(
          "Gamma Taylor stream requires a little-endian host");
    }
    static_assert(std::numeric_limits<double>::is_iec559);
    read_exact(&header_, sizeof(header_), "Gamma Taylor header");
    validate_header(expected_first_block, expected_block_count);
    header_sha256_ = sha256(&header_, sizeof(header_));
    stream_hasher_.update(kStreamHashDomain.data(), kStreamHashDomain.size());
    stream_hasher_.update(&header_, sizeof(header_));
  }

  const pw::GammaTaylorStreamHeader& header() const { return header_; }
  std::uint64_t consumed_records() const { return consumed_; }
  std::uint64_t chunk_count() const { return chunks_; }
  bool complete() const { return complete_; }
  const Sha256Digest& stream_sha256() const {
    if (!complete_) {
      throw GammaTaylorStreamError(
          "Gamma Taylor stream digest requested before footer verification");
    }
    return stream_sha256_;
  }

  bool next(AuthenticatedChunk& output) {
    if (complete_) return false;
    if (consumed_ == header_.block_count) {
      verify_footer();
      return false;
    }
    pw::GammaTaylorChunkHeader chunk{};
    read_exact(&chunk, sizeof(chunk), "Gamma Taylor chunk header");
    const std::uint64_t remaining = header_.block_count - consumed_;
    const std::uint32_t expected_count = static_cast<std::uint32_t>(
        std::min<std::uint64_t>(header_.chunk_records, remaining));
    const std::uint64_t expected_bytes =
        static_cast<std::uint64_t>(expected_count) *
        sizeof(pw::GammaTaylorStreamRecord);
    if (chunk.magic != pw::kGammaTaylorChunkMagic ||
        chunk.version != pw::kGammaTaylorStreamVersion ||
        chunk.header_bytes != sizeof(chunk) ||
        chunk.first_block != header_.first_block + consumed_ ||
        chunk.record_count != expected_count || chunk.reserved_zero != 0U ||
        chunk.payload_bytes != expected_bytes) {
      throw GammaTaylorStreamError("Gamma Taylor chunk framing differs");
    }
    std::vector<pw::GammaTaylorStreamRecord> records(expected_count);
    read_exact(records.data(), static_cast<std::size_t>(expected_bytes),
               "Gamma Taylor chunk payload");
    const Sha256Digest payload_sha =
        sha256(records.data(), static_cast<std::size_t>(expected_bytes));
    if (payload_sha != chunk.payload_sha256) {
      throw GammaTaylorStreamError("Gamma Taylor chunk payload digest differs");
    }
    for (const auto& record : records) validate_record(record);

    // Only authenticated, structurally valid records become observable.
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
    input_.read(static_cast<char*>(output),
                static_cast<std::streamsize>(size));
    if (input_.gcount() != static_cast<std::streamsize>(size)) {
      throw GammaTaylorStreamError(std::string(label) + " is truncated");
    }
  }

  void validate_header(
      std::optional<std::uint64_t> expected_first_block,
      std::optional<std::uint64_t> expected_block_count) {
    auto require = [](bool condition, const char* field) {
      if (!condition) {
        throw GammaTaylorStreamError(
            std::string("Gamma Taylor fixed header differs at ") + field);
      }
    };
    require(header_.magic == pw::kGammaTaylorStreamMagic, "magic");
    require(header_.version == pw::kGammaTaylorStreamVersion, "version");
    require(header_.header_bytes == sizeof(header_), "header_bytes");
    require(header_.endian_tag == pw::kSourcePacketEndianTag, "endian_tag");
    require(header_.record_encoding == pw::kGammaTaylorStreamEncoding,
            "record_encoding");
    require(header_.record_bytes == sizeof(pw::GammaTaylorStreamRecord),
            "record_bytes");
    require(header_.chunk_records >= 1U &&
                header_.chunk_records <= (1U << 20U),
            "chunk_records");
    require(header_.degree == pw::kGammaTaylorDegree, "degree");
    require(header_.precision_bits == pw::kGammaTaylorPrecision,
            "precision_bits");
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
      throw GammaTaylorStreamError("Gamma Taylor stream range is invalid");
    }
    if (expected_first_block &&
        header_.first_block != *expected_first_block) {
      throw GammaTaylorStreamError("Gamma Taylor first block differs");
    }
    if (expected_block_count &&
        header_.block_count != *expected_block_count) {
      throw GammaTaylorStreamError("Gamma Taylor block count differs");
    }
    authenticated_stream_bytes_ = sizeof(header_);
  }

  void verify_footer() {
    pw::GammaTaylorStreamFooter footer{};
    read_exact(&footer, sizeof(footer), "Gamma Taylor footer");
    stream_sha256_ = stream_hasher_.finish();
    if (footer.magic != pw::kGammaTaylorFooterMagic ||
        footer.version != pw::kGammaTaylorStreamVersion ||
        footer.footer_bytes != sizeof(footer) ||
        footer.first_block != header_.first_block ||
        footer.block_count != header_.block_count ||
        footer.chunk_count != chunks_ ||
        footer.record_payload_bytes != record_payload_bytes_ ||
        footer.authenticated_stream_bytes != authenticated_stream_bytes_ ||
        footer.header_sha256 != header_sha256_ ||
        footer.stream_sha256 != stream_sha256_ ||
        !all_zero(footer.reserved_zero.data(), footer.reserved_zero.size())) {
      throw GammaTaylorStreamError("Gamma Taylor footer differs");
    }
    if (expected_stream_sha256_ &&
        stream_sha256_ != *expected_stream_sha256_) {
      throw GammaTaylorStreamError("Gamma Taylor stream digest differs");
    }
    char trailing = 0;
    input_.read(&trailing, 1);
    if (input_.gcount() != 0) {
      throw GammaTaylorStreamError(
          "trailing bytes follow the Gamma Taylor footer");
    }
    complete_ = true;
  }

  std::istream& input_;
  pw::GammaTaylorStreamHeader header_{};
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

}  // namespace sparkinterval::tg::platt_gamma_stream

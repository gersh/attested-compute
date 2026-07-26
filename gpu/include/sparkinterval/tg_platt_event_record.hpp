// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// Compact, nonterminal wire for the fused PT21 transform/event stage.
//
// PT21EVT1 deliberately is not PT21BLK1.  It commits the exact required DD
// disks and the three finite scanner streams, while retaining the number of
// stationary candidates that still require Gaussian--sinc resolution.  It
// contains no Turing count and makes no Hardy-Z or multiplicity claim.

#include "sparkinterval/sha256.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace sparkinterval::tg::platt_event_record {

inline constexpr std::uint32_t kVersion = 1U;
inline constexpr std::uint32_t kFiniteEventStageFlag = 1U;
inline constexpr std::uint64_t kSourceBlockCount = 2'966'443'783ULL;
inline constexpr std::uint32_t kRequiredSampleCount = 25'741U;
inline constexpr std::int32_t kRequiredLower = -12'870;
inline constexpr std::int32_t kRequiredUpper = 12'870;
inline constexpr std::int32_t kLatticeNumerator = 21;
inline constexpr std::int32_t kLatticeDenominator = 512;
inline constexpr std::array<std::int32_t, 3> kStreamLower = {
    -12'800, -12'288, 12'288};
inline constexpr std::array<std::int32_t, 3> kStreamUpper = {
    -12'288, 12'288, 12'800};
inline constexpr std::array<std::uint32_t, 3> kDirectCapacities = {
    512U, 24'576U, 512U};
inline constexpr std::array<std::uint32_t, 3> kStationaryCapacities = {
    510U, 24'574U, 510U};
inline constexpr std::array<std::uint32_t, 3> kEdgeCounts = {
    512U, 24'576U, 512U};
inline constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";

inline constexpr std::size_t kHeaderBytes = 192U;
inline constexpr std::size_t kRecordBytes = 192U;
inline constexpr std::size_t kFooterBytes = 192U;
inline constexpr std::size_t kHeaderDigestOffset = 160U;
inline constexpr std::size_t kRecordDigestOffset = 160U;
inline constexpr std::size_t kFooterDigestOffset = 160U;

inline constexpr char kHeaderMagic[] = "PT21EVH1";
inline constexpr char kRecordMagic[] = "PT21EVT1";
inline constexpr char kFooterMagic[] = "PT21EVF1";
inline constexpr char kContractDomain[] =
    "sparkinterval/tg/platt-pt21-event-contract/v1\0";
inline constexpr char kHeaderDomain[] =
    "sparkinterval/tg/platt-pt21-event-stream-header/v1\0";
inline constexpr char kRecordDomain[] =
    "sparkinterval/tg/platt-pt21-event-record/v1\0";
inline constexpr char kFooterDomain[] =
    "sparkinterval/tg/platt-pt21-event-stream-footer/v1\0";

using RawHeader = std::array<unsigned char, kHeaderBytes>;
using RawRecord = std::array<unsigned char, kRecordBytes>;
using RawFooter = std::array<unsigned char, kFooterBytes>;

class EventRecordError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct HeaderValues {
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  Sha256Digest gamma_stream_sha256{};
  Sha256Digest producer_sha256{};
};

struct BlockValues {
  std::uint64_t block = 0U;
  std::uint32_t failure_flags = 0U;
  std::uint32_t certified_sample_count = 0U;
  std::uint32_t digest_valid = 0U;
  std::array<std::uint32_t, 3> direct_event_count{};
  std::array<std::uint32_t, 3> stationary_candidate_count{};
  std::array<std::uint32_t, 3> certified_direct_slots{};
  std::uint32_t unresolved_stationary_count = 0U;
  std::array<std::int64_t, 3> direct_nleft_units{};
  std::array<std::int64_t, 3> direct_nright_units{};
  Sha256Digest event_artifact_sha256{};
};

struct FooterValues {
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  std::uint64_t total_direct_events = 0U;
  std::uint64_t total_stationary_candidates = 0U;
  Sha256Digest record_stream_sha256{};
  Sha256Digest header_sha256{};
  Sha256Digest gamma_stream_sha256{};
};

inline bool digest_is_zero(const Sha256Digest& digest) {
  for (const unsigned char byte : digest) {
    if (byte != 0U) return false;
  }
  return true;
}

inline void store_u32(unsigned char* destination, std::uint32_t value) {
  for (unsigned int byte = 0U; byte < 4U; ++byte) {
    destination[byte] =
        static_cast<unsigned char>(value >> (8U * byte));
  }
}

inline void store_u64(unsigned char* destination, std::uint64_t value) {
  for (unsigned int byte = 0U; byte < 8U; ++byte) {
    destination[byte] =
        static_cast<unsigned char>(value >> (8U * byte));
  }
}

inline std::uint32_t load_u32(const unsigned char* source) {
  std::uint32_t result = 0U;
  for (unsigned int byte = 0U; byte < 4U; ++byte) {
    result |= static_cast<std::uint32_t>(source[byte]) << (8U * byte);
  }
  return result;
}

inline std::uint64_t load_u64(const unsigned char* source) {
  std::uint64_t result = 0U;
  for (unsigned int byte = 0U; byte < 8U; ++byte) {
    result |= static_cast<std::uint64_t>(source[byte]) << (8U * byte);
  }
  return result;
}

inline void append_u32(std::vector<unsigned char>* destination,
                       std::uint32_t value) {
  const std::size_t offset = destination->size();
  destination->resize(offset + 4U);
  store_u32(destination->data() + offset, value);
}

inline void append_i32(std::vector<unsigned char>* destination,
                       std::int32_t value) {
  append_u32(destination, static_cast<std::uint32_t>(value));
}

template <std::size_t N>
inline Sha256Digest domain_hash(const char (&domain)[N],
                                const unsigned char* data,
                                std::size_t size) {
  detail::Sha256 hasher;
  // N includes the compiler terminator. N - 1 retains the explicit NUL in
  // each domain literal.
  hasher.update(domain, N - 1U);
  hasher.update(data, size);
  return hasher.finish();
}

inline Sha256Digest event_contract_sha256() {
  std::vector<unsigned char> encoded;
  encoded.reserve(128U);
  append_u32(&encoded, kRequiredSampleCount);
  append_i32(&encoded, kRequiredLower);
  append_i32(&encoded, kRequiredUpper);
  append_i32(&encoded, kLatticeNumerator);
  append_i32(&encoded, kLatticeDenominator);
  for (std::size_t stream = 0U; stream < 3U; ++stream) {
    append_i32(&encoded, kStreamLower[stream]);
    append_i32(&encoded, kStreamUpper[stream]);
  }
  for (const std::uint32_t capacity : kDirectCapacities) {
    append_u32(&encoded, capacity);
  }
  for (const std::uint32_t capacity : kStationaryCapacities) {
    append_u32(&encoded, capacity);
  }
  encoded.insert(encoded.end(), kUpstreamCommit,
                 kUpstreamCommit + sizeof(kUpstreamCommit) - 1U);
  return domain_hash(kContractDomain, encoded.data(), encoded.size());
}

inline void require_geometry(std::uint64_t first_block,
                             std::uint64_t block_count) {
  if (block_count == 0U || first_block >= kSourceBlockCount ||
      block_count > kSourceBlockCount - first_block) {
    throw EventRecordError("event stream geometry is outside PT21");
  }
}

inline RawHeader encode_header(const HeaderValues& values) {
  require_geometry(values.first_block, values.block_count);
  if (digest_is_zero(values.gamma_stream_sha256) ||
      digest_is_zero(values.producer_sha256)) {
    throw EventRecordError("event stream identities must be nonzero");
  }
  RawHeader raw{};
  std::memcpy(raw.data(), kHeaderMagic, 8U);
  store_u32(raw.data() + 8U, kVersion);
  store_u32(raw.data() + 12U, kHeaderBytes);
  store_u32(raw.data() + 16U, kRecordBytes);
  store_u32(raw.data() + 20U, kFiniteEventStageFlag);
  store_u64(raw.data() + 24U, values.first_block);
  store_u64(raw.data() + 32U, values.block_count);
  std::memcpy(raw.data() + 40U, values.gamma_stream_sha256.data(), 32U);
  std::memcpy(raw.data() + 72U, values.producer_sha256.data(), 32U);
  const Sha256Digest contract = event_contract_sha256();
  std::memcpy(raw.data() + 104U, contract.data(), 32U);
  const Sha256Digest digest =
      domain_hash(kHeaderDomain, raw.data(), kHeaderDigestOffset);
  std::memcpy(raw.data() + kHeaderDigestOffset, digest.data(), 32U);
  return raw;
}

inline Sha256Digest digest_at(const unsigned char* source) {
  Sha256Digest result{};
  std::memcpy(result.data(), source, result.size());
  return result;
}

inline void validate_header(const RawHeader& raw,
                            const HeaderValues* expected = nullptr) {
  if (std::memcmp(raw.data(), kHeaderMagic, 8U) != 0 ||
      load_u32(raw.data() + 8U) != kVersion ||
      load_u32(raw.data() + 12U) != kHeaderBytes ||
      load_u32(raw.data() + 16U) != kRecordBytes ||
      load_u32(raw.data() + 20U) != kFiniteEventStageFlag) {
    throw EventRecordError("event stream fixed header differs");
  }
  const std::uint64_t first_block = load_u64(raw.data() + 24U);
  const std::uint64_t block_count = load_u64(raw.data() + 32U);
  require_geometry(first_block, block_count);
  const Sha256Digest gamma = digest_at(raw.data() + 40U);
  const Sha256Digest producer = digest_at(raw.data() + 72U);
  if (digest_is_zero(gamma) || digest_is_zero(producer) ||
      digest_at(raw.data() + 104U) != event_contract_sha256()) {
    throw EventRecordError("event stream identity or contract differs");
  }
  for (std::size_t index = 136U; index < kHeaderDigestOffset; ++index) {
    if (raw[index] != 0U) {
      throw EventRecordError("event stream header reserved bytes differ");
    }
  }
  const Sha256Digest digest =
      domain_hash(kHeaderDomain, raw.data(), kHeaderDigestOffset);
  if (digest_at(raw.data() + kHeaderDigestOffset) != digest) {
    throw EventRecordError("event stream header digest differs");
  }
  if (expected != nullptr &&
      (first_block != expected->first_block ||
       block_count != expected->block_count ||
       gamma != expected->gamma_stream_sha256 ||
       producer != expected->producer_sha256)) {
    throw EventRecordError("event stream header differs from its pin");
  }
}

inline void checked_add(std::uint32_t* accumulator, std::uint32_t value,
                        std::string_view label) {
  if (value > std::numeric_limits<std::uint32_t>::max() - *accumulator) {
    throw EventRecordError(std::string(label) + " count overflows uint32");
  }
  *accumulator += value;
}

inline void validate_block_values(const BlockValues& values,
                                  std::uint64_t expected_block) {
  if (values.block != expected_block || values.block >= kSourceBlockCount) {
    throw EventRecordError("event record block is not gap-free");
  }
  if (values.failure_flags != 0U ||
      values.certified_sample_count != kRequiredSampleCount ||
      values.digest_valid != 1U ||
      digest_is_zero(values.event_artifact_sha256)) {
    throw EventRecordError("event record has an unresolved finite failure");
  }
  std::uint32_t stationary_total = 0U;
  for (std::size_t stream = 0U; stream < 3U; ++stream) {
    if (values.direct_event_count[stream] >
            kDirectCapacities[stream] ||
        values.stationary_candidate_count[stream] >
            kStationaryCapacities[stream] ||
        values.certified_direct_slots[stream] !=
            values.direct_event_count[stream]) {
      throw EventRecordError("event record stream counts differ");
    }
    checked_add(&stationary_total,
                values.stationary_candidate_count[stream], "stationary");
    const std::int64_t maximum =
        static_cast<std::int64_t>(values.direct_event_count[stream]) *
        static_cast<std::int64_t>(kEdgeCounts[stream] - 1U);
    if (values.direct_nleft_units[stream] > 0 ||
        values.direct_nleft_units[stream] < -maximum ||
        values.direct_nright_units[stream] < 0 ||
        values.direct_nright_units[stream] > maximum) {
      throw EventRecordError("event record direct weights leave source bounds");
    }
  }
  if (values.unresolved_stationary_count != stationary_total) {
    throw EventRecordError(
        "event record unresolved stationary count differs");
  }
}

inline RawRecord encode_record(const BlockValues& values) {
  validate_block_values(values, values.block);
  RawRecord raw{};
  std::memcpy(raw.data(), kRecordMagic, 8U);
  store_u32(raw.data() + 8U, kVersion);
  store_u32(raw.data() + 12U, kRecordBytes);
  store_u64(raw.data() + 16U, values.block);
  store_u32(raw.data() + 24U, values.failure_flags);
  store_u32(raw.data() + 28U, values.certified_sample_count);
  store_u32(raw.data() + 32U, values.digest_valid);
  for (std::size_t stream = 0U; stream < 3U; ++stream) {
    store_u32(raw.data() + 40U + stream * 4U,
              values.direct_event_count[stream]);
    store_u32(raw.data() + 52U + stream * 4U,
              values.stationary_candidate_count[stream]);
    store_u32(raw.data() + 64U + stream * 4U,
              values.certified_direct_slots[stream]);
  }
  store_u32(raw.data() + 76U, values.unresolved_stationary_count);
  for (std::size_t stream = 0U; stream < 3U; ++stream) {
    store_u64(raw.data() + 80U + stream * 8U,
              static_cast<std::uint64_t>(
                  values.direct_nleft_units[stream]));
    store_u64(raw.data() + 104U + stream * 8U,
              static_cast<std::uint64_t>(
                  values.direct_nright_units[stream]));
  }
  std::memcpy(raw.data() + 128U, values.event_artifact_sha256.data(), 32U);
  const Sha256Digest digest =
      domain_hash(kRecordDomain, raw.data(), kRecordDigestOffset);
  std::memcpy(raw.data() + kRecordDigestOffset, digest.data(), 32U);
  return raw;
}

inline std::int64_t load_i64(const unsigned char* source) {
  const std::uint64_t bits = load_u64(source);
  std::int64_t result = 0;
  std::memcpy(&result, &bits, sizeof(result));
  return result;
}

inline BlockValues decode_record(const RawRecord& raw,
                                 std::uint64_t expected_block) {
  if (std::memcmp(raw.data(), kRecordMagic, 8U) != 0 ||
      load_u32(raw.data() + 8U) != kVersion ||
      load_u32(raw.data() + 12U) != kRecordBytes ||
      load_u32(raw.data() + 36U) != 0U) {
    throw EventRecordError("event record fixed fields differ");
  }
  const Sha256Digest digest =
      domain_hash(kRecordDomain, raw.data(), kRecordDigestOffset);
  if (digest_at(raw.data() + kRecordDigestOffset) != digest) {
    throw EventRecordError("event record digest differs");
  }
  BlockValues values;
  values.block = load_u64(raw.data() + 16U);
  values.failure_flags = load_u32(raw.data() + 24U);
  values.certified_sample_count = load_u32(raw.data() + 28U);
  values.digest_valid = load_u32(raw.data() + 32U);
  for (std::size_t stream = 0U; stream < 3U; ++stream) {
    values.direct_event_count[stream] =
        load_u32(raw.data() + 40U + stream * 4U);
    values.stationary_candidate_count[stream] =
        load_u32(raw.data() + 52U + stream * 4U);
    values.certified_direct_slots[stream] =
        load_u32(raw.data() + 64U + stream * 4U);
    values.direct_nleft_units[stream] =
        load_i64(raw.data() + 80U + stream * 8U);
    values.direct_nright_units[stream] =
        load_i64(raw.data() + 104U + stream * 8U);
  }
  values.unresolved_stationary_count = load_u32(raw.data() + 76U);
  values.event_artifact_sha256 = digest_at(raw.data() + 128U);
  validate_block_values(values, expected_block);
  return values;
}

inline RawFooter encode_footer(const FooterValues& values) {
  require_geometry(values.first_block, values.block_count);
  if (digest_is_zero(values.record_stream_sha256) ||
      digest_is_zero(values.header_sha256) ||
      digest_is_zero(values.gamma_stream_sha256)) {
    throw EventRecordError("event stream footer identities must be nonzero");
  }
  RawFooter raw{};
  std::memcpy(raw.data(), kFooterMagic, 8U);
  store_u32(raw.data() + 8U, kVersion);
  store_u32(raw.data() + 12U, kFooterBytes);
  store_u64(raw.data() + 16U, values.first_block);
  store_u64(raw.data() + 24U, values.block_count);
  store_u64(raw.data() + 32U, values.total_direct_events);
  store_u64(raw.data() + 40U, values.total_stationary_candidates);
  std::memcpy(raw.data() + 48U, values.record_stream_sha256.data(), 32U);
  std::memcpy(raw.data() + 80U, values.header_sha256.data(), 32U);
  std::memcpy(raw.data() + 112U, values.gamma_stream_sha256.data(), 32U);
  const Sha256Digest digest =
      domain_hash(kFooterDomain, raw.data(), kFooterDigestOffset);
  std::memcpy(raw.data() + kFooterDigestOffset, digest.data(), 32U);
  return raw;
}

inline void validate_footer(const RawFooter& raw,
                            const FooterValues& expected) {
  if (std::memcmp(raw.data(), kFooterMagic, 8U) != 0 ||
      load_u32(raw.data() + 8U) != kVersion ||
      load_u32(raw.data() + 12U) != kFooterBytes ||
      load_u64(raw.data() + 16U) != expected.first_block ||
      load_u64(raw.data() + 24U) != expected.block_count ||
      load_u64(raw.data() + 32U) != expected.total_direct_events ||
      load_u64(raw.data() + 40U) !=
          expected.total_stationary_candidates ||
      digest_at(raw.data() + 48U) != expected.record_stream_sha256 ||
      digest_at(raw.data() + 80U) != expected.header_sha256 ||
      digest_at(raw.data() + 112U) != expected.gamma_stream_sha256) {
    throw EventRecordError("event stream footer fields differ");
  }
  for (std::size_t index = 144U; index < kFooterDigestOffset; ++index) {
    if (raw[index] != 0U) {
      throw EventRecordError("event stream footer reserved bytes differ");
    }
  }
  const Sha256Digest digest =
      domain_hash(kFooterDomain, raw.data(), kFooterDigestOffset);
  if (digest_at(raw.data() + kFooterDigestOffset) != digest) {
    throw EventRecordError("event stream footer digest differs");
  }
}

static_assert(sizeof(kUpstreamCommit) - 1U == 40U);
static_assert(kRequiredUpper - kRequiredLower + 1 ==
              static_cast<std::int32_t>(kRequiredSampleCount));
static_assert(kHeaderDigestOffset + 32U == kHeaderBytes);
static_assert(kRecordDigestOffset + 32U == kRecordBytes);
static_assert(kFooterDigestOffset + 32U == kFooterBytes);

}  // namespace sparkinterval::tg::platt_event_record

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// Qualification-only authenticated framing for the inline PT21 finite
// event/stationary junction.
//
// Every variable-length PT21IQF1 frame contains, in order, one exact
// PT21EVT1 record, its exact PT21STJ1 result, and the canonical stationary
// trace whose digest is pinned by PT21STJ1.  This wire is deliberately
// nonterminal: it contains no PT21BLK1 record, no Turing closure, and no
// analytic or FLINT-to-Mathlib realization flag.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_event_record.hpp"
#include "sparkinterval/tg_platt_stationary_junction.hpp"
#include "sparkinterval/tg_platt_stationary_resolver.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace sparkinterval::tg::platt_inline_stationary_stream {

namespace per = sparkinterval::tg::platt_event_record;
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace psr = sparkinterval::tg::platt_stationary_resolver;

inline constexpr std::uint32_t kVersion = 1U;
inline constexpr std::uint32_t kFiniteQualificationOnlyFlag = 1U;
inline constexpr std::size_t kHeaderBytes = 256U;
inline constexpr std::size_t kHeaderDigestOffset = 224U;
inline constexpr std::size_t kFramePrefixBytes = 144U;
inline constexpr std::size_t kFrameDigestBytes = 32U;
inline constexpr std::size_t kFooterBytes = 192U;
inline constexpr std::size_t kFooterDigestOffset = 160U;
inline constexpr std::uint32_t kMaximumTraceBytes =
    psr::kSourceTraceMaximumBytes;

inline constexpr char kHeaderMagic[] = "PT21IQH1";
inline constexpr char kFrameMagic[] = "PT21IQF1";
inline constexpr char kFooterMagic[] = "PT21IQT1";
inline constexpr char kAlgorithmDomain[] =
    "sparkinterval/tg/platt-pt21-inline-stationary-qualification/v1\0";
inline constexpr char kHeaderDomain[] =
    "sparkinterval/tg/platt-pt21-inline-stationary-header/v1\0";
inline constexpr char kFrameDomain[] =
    "sparkinterval/tg/platt-pt21-inline-stationary-frame/v1\0";
inline constexpr char kFooterDomain[] =
    "sparkinterval/tg/platt-pt21-inline-stationary-footer/v1\0";

using RawHeader = std::array<unsigned char, kHeaderBytes>;
using RawFooter = std::array<unsigned char, kFooterBytes>;

class InlineStationaryStreamError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct HeaderValues {
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  Sha256Digest gamma_stream_sha256{};
  Sha256Digest producer_sha256{};
  Sha256Digest resolver_sha256{};
  Sha256Digest flint_sha256{};
};

struct FooterValues {
  std::uint64_t first_block = 0U;
  std::uint64_t block_count = 0U;
  std::uint64_t total_event_records = 0U;
  std::uint64_t total_junction_records = 0U;
  std::uint64_t total_trace_bytes = 0U;
  Sha256Digest frame_stream_sha256{};
  Sha256Digest header_sha256{};
  Sha256Digest gamma_stream_sha256{};
};

struct DecodedFrame {
  std::uint64_t block = 0U;
  per::RawRecord event_record{};
  psj::RawRecord junction_record{};
  std::string stationary_trace;
  Sha256Digest frame_sha256{};
};

inline Sha256Digest algorithm_sha256() {
  static constexpr unsigned char empty = 0U;
  return per::domain_hash(kAlgorithmDomain, &empty, 0U);
}

inline void require_nonzero(const Sha256Digest& digest,
                            std::string_view label) {
  if (per::digest_is_zero(digest)) {
    throw InlineStationaryStreamError(
        std::string(label) + " identity must be nonzero");
  }
}

inline RawHeader encode_header(const HeaderValues& values) {
  per::require_geometry(values.first_block, values.block_count);
  require_nonzero(values.gamma_stream_sha256, "Gamma stream");
  require_nonzero(values.producer_sha256, "producer");
  require_nonzero(values.resolver_sha256, "resolver");
  require_nonzero(values.flint_sha256, "FLINT");
  RawHeader raw{};
  std::memcpy(raw.data(), kHeaderMagic, 8U);
  per::store_u32(raw.data() + 8U, kVersion);
  per::store_u32(raw.data() + 12U, kHeaderBytes);
  per::store_u32(raw.data() + 16U, kFramePrefixBytes);
  per::store_u32(raw.data() + 20U, kFooterBytes);
  per::store_u64(raw.data() + 24U, values.first_block);
  per::store_u64(raw.data() + 32U, values.block_count);
  std::memcpy(raw.data() + 40U, values.gamma_stream_sha256.data(), 32U);
  std::memcpy(raw.data() + 72U, values.producer_sha256.data(), 32U);
  std::memcpy(raw.data() + 104U, values.resolver_sha256.data(), 32U);
  std::memcpy(raw.data() + 136U, values.flint_sha256.data(), 32U);
  const Sha256Digest algorithm = algorithm_sha256();
  std::memcpy(raw.data() + 168U, algorithm.data(), 32U);
  per::store_u32(raw.data() + 200U, kFiniteQualificationOnlyFlag);
  const Sha256Digest digest =
      per::domain_hash(kHeaderDomain, raw.data(), kHeaderDigestOffset);
  std::memcpy(raw.data() + kHeaderDigestOffset, digest.data(), digest.size());
  return raw;
}

inline HeaderValues decode_header(
    const RawHeader& raw, const HeaderValues* expected = nullptr) {
  if (std::memcmp(raw.data(), kHeaderMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != kHeaderBytes ||
      per::load_u32(raw.data() + 16U) != kFramePrefixBytes ||
      per::load_u32(raw.data() + 20U) != kFooterBytes ||
      per::load_u32(raw.data() + 200U) !=
          kFiniteQualificationOnlyFlag) {
    throw InlineStationaryStreamError(
        "inline stationary stream fixed header differs");
  }
  for (std::size_t index = 204U; index < kHeaderDigestOffset; ++index) {
    if (raw[index] != 0U) {
      throw InlineStationaryStreamError(
          "inline stationary stream header reserved bytes differ");
    }
  }
  const Sha256Digest digest =
      per::domain_hash(kHeaderDomain, raw.data(), kHeaderDigestOffset);
  if (per::digest_at(raw.data() + kHeaderDigestOffset) != digest ||
      per::digest_at(raw.data() + 168U) != algorithm_sha256()) {
    throw InlineStationaryStreamError(
        "inline stationary stream header digest or algorithm differs");
  }
  HeaderValues values{
      .first_block = per::load_u64(raw.data() + 24U),
      .block_count = per::load_u64(raw.data() + 32U),
      .gamma_stream_sha256 = per::digest_at(raw.data() + 40U),
      .producer_sha256 = per::digest_at(raw.data() + 72U),
      .resolver_sha256 = per::digest_at(raw.data() + 104U),
      .flint_sha256 = per::digest_at(raw.data() + 136U),
  };
  per::require_geometry(values.first_block, values.block_count);
  require_nonzero(values.gamma_stream_sha256, "Gamma stream");
  require_nonzero(values.producer_sha256, "producer");
  require_nonzero(values.resolver_sha256, "resolver");
  require_nonzero(values.flint_sha256, "FLINT");
  if (expected != nullptr &&
      (values.first_block != expected->first_block ||
       values.block_count != expected->block_count ||
       values.gamma_stream_sha256 != expected->gamma_stream_sha256 ||
       values.producer_sha256 != expected->producer_sha256 ||
       values.resolver_sha256 != expected->resolver_sha256 ||
       values.flint_sha256 != expected->flint_sha256)) {
    throw InlineStationaryStreamError(
        "inline stationary stream header differs from its identity pin");
  }
  return values;
}

inline std::vector<unsigned char> encode_frame(
    std::uint64_t block, const per::RawRecord& event_record,
    const psj::RawRecord& junction_record,
    std::string_view stationary_trace) {
  const per::BlockValues event = per::decode_record(event_record, block);
  const psj::RecordValues junction = psj::decode_record(junction_record);
  if (junction.block != block ||
      junction.event_record_sha256 !=
          per::digest_at(event_record.data() + per::kRecordDigestOffset) ||
      junction.event_artifact_sha256 != event.event_artifact_sha256) {
    throw InlineStationaryStreamError(
        "inline stationary frame event/junction link differs");
  }
  if (stationary_trace.empty() ||
      stationary_trace.size() > kMaximumTraceBytes ||
      sha256(stationary_trace.data(), stationary_trace.size()) !=
          junction.stationary_trace_sha256) {
    throw InlineStationaryStreamError(
        "inline stationary frame trace differs from PT21STJ1");
  }
  const std::uint64_t wide_size =
      kFramePrefixBytes + event_record.size() + junction_record.size() +
      stationary_trace.size() + kFrameDigestBytes;
  if (wide_size > std::numeric_limits<std::uint32_t>::max()) {
    throw InlineStationaryStreamError(
        "inline stationary frame exceeds uint32");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(wide_size), 0U);
  std::memcpy(raw.data(), kFrameMagic, 8U);
  per::store_u32(raw.data() + 8U, kVersion);
  per::store_u32(raw.data() + 12U,
                 static_cast<std::uint32_t>(raw.size()));
  per::store_u64(raw.data() + 16U, block);
  per::store_u32(raw.data() + 24U,
                 static_cast<std::uint32_t>(event_record.size()));
  per::store_u32(raw.data() + 28U,
                 static_cast<std::uint32_t>(junction_record.size()));
  per::store_u32(raw.data() + 32U,
                 static_cast<std::uint32_t>(stationary_trace.size()));
  per::store_u64(raw.data() + 40U, 0U);
  const Sha256Digest event_digest =
      sha256(event_record.data(), event_record.size());
  const Sha256Digest junction_digest =
      sha256(junction_record.data(), junction_record.size());
  const Sha256Digest trace_digest =
      sha256(stationary_trace.data(), stationary_trace.size());
  std::memcpy(raw.data() + 48U, event_digest.data(), 32U);
  std::memcpy(raw.data() + 80U, junction_digest.data(), 32U);
  std::memcpy(raw.data() + 112U, trace_digest.data(), 32U);
  std::size_t payload = kFramePrefixBytes;
  std::memcpy(raw.data() + payload, event_record.data(), event_record.size());
  payload += event_record.size();
  std::memcpy(raw.data() + payload, junction_record.data(),
              junction_record.size());
  payload += junction_record.size();
  std::memcpy(raw.data() + payload, stationary_trace.data(),
              stationary_trace.size());
  const Sha256Digest frame_digest =
      per::domain_hash(kFrameDomain, raw.data(),
                       raw.size() - kFrameDigestBytes);
  std::memcpy(raw.data() + raw.size() - kFrameDigestBytes,
              frame_digest.data(), frame_digest.size());
  return raw;
}

inline DecodedFrame decode_frame(std::span<const unsigned char> raw,
                                 std::uint64_t expected_block) {
  if (raw.size() < kFramePrefixBytes + per::kRecordBytes +
                       psj::kRecordBytes + 1U + kFrameDigestBytes ||
      std::memcmp(raw.data(), kFrameMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != raw.size() ||
      per::load_u64(raw.data() + 16U) != expected_block ||
      per::load_u32(raw.data() + 24U) != per::kRecordBytes ||
      per::load_u32(raw.data() + 28U) != psj::kRecordBytes ||
      per::load_u64(raw.data() + 40U) != 0U) {
    throw InlineStationaryStreamError(
        "inline stationary frame fixed fields differ");
  }
  const std::uint32_t trace_bytes = per::load_u32(raw.data() + 32U);
  if (per::load_u32(raw.data() + 36U) != 0U ||
      trace_bytes == 0U || trace_bytes > kMaximumTraceBytes ||
      raw.size() != kFramePrefixBytes + per::kRecordBytes +
                        psj::kRecordBytes + trace_bytes +
                        kFrameDigestBytes) {
    throw InlineStationaryStreamError(
        "inline stationary frame lengths differ");
  }
  const Sha256Digest frame_digest =
      per::domain_hash(kFrameDomain, raw.data(),
                       raw.size() - kFrameDigestBytes);
  if (per::digest_at(raw.data() + raw.size() - kFrameDigestBytes) !=
      frame_digest) {
    throw InlineStationaryStreamError(
        "inline stationary frame digest differs");
  }
  DecodedFrame result;
  result.block = expected_block;
  std::size_t payload = kFramePrefixBytes;
  std::copy_n(raw.data() + payload, result.event_record.size(),
              result.event_record.begin());
  payload += result.event_record.size();
  std::copy_n(raw.data() + payload, result.junction_record.size(),
              result.junction_record.begin());
  payload += result.junction_record.size();
  result.stationary_trace.assign(
      reinterpret_cast<const char*>(raw.data() + payload), trace_bytes);
  result.frame_sha256 = frame_digest;
  if (sha256(result.event_record.data(), result.event_record.size()) !=
          per::digest_at(raw.data() + 48U) ||
      sha256(result.junction_record.data(),
             result.junction_record.size()) !=
          per::digest_at(raw.data() + 80U) ||
      sha256(result.stationary_trace.data(),
             result.stationary_trace.size()) !=
          per::digest_at(raw.data() + 112U)) {
    throw InlineStationaryStreamError(
        "inline stationary frame payload digest differs");
  }
  // Reuse the encoder's nested PT21EVT1/PT21STJ1/trace checks.
  const std::vector<unsigned char> canonical = encode_frame(
      expected_block, result.event_record, result.junction_record,
      result.stationary_trace);
  if (!std::equal(canonical.begin(), canonical.end(), raw.begin(),
                  raw.end())) {
    throw InlineStationaryStreamError(
        "inline stationary frame is not canonical");
  }
  return result;
}

inline RawFooter encode_footer(const FooterValues& values) {
  per::require_geometry(values.first_block, values.block_count);
  if (values.total_event_records != values.block_count ||
      values.total_junction_records != values.block_count) {
    throw InlineStationaryStreamError(
        "inline stationary footer record totals differ");
  }
  require_nonzero(values.frame_stream_sha256, "frame stream");
  require_nonzero(values.header_sha256, "header");
  require_nonzero(values.gamma_stream_sha256, "Gamma stream");
  RawFooter raw{};
  std::memcpy(raw.data(), kFooterMagic, 8U);
  per::store_u32(raw.data() + 8U, kVersion);
  per::store_u32(raw.data() + 12U, kFooterBytes);
  per::store_u64(raw.data() + 16U, values.first_block);
  per::store_u64(raw.data() + 24U, values.block_count);
  per::store_u64(raw.data() + 32U, values.total_event_records);
  per::store_u64(raw.data() + 40U, values.total_junction_records);
  per::store_u64(raw.data() + 48U, values.total_trace_bytes);
  std::memcpy(raw.data() + 56U, values.frame_stream_sha256.data(), 32U);
  std::memcpy(raw.data() + 88U, values.header_sha256.data(), 32U);
  std::memcpy(raw.data() + 120U, values.gamma_stream_sha256.data(), 32U);
  const Sha256Digest digest =
      per::domain_hash(kFooterDomain, raw.data(), kFooterDigestOffset);
  std::memcpy(raw.data() + kFooterDigestOffset, digest.data(), digest.size());
  return raw;
}

inline FooterValues decode_footer(
    const RawFooter& raw, const FooterValues* expected = nullptr) {
  if (std::memcmp(raw.data(), kFooterMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != kFooterBytes) {
    throw InlineStationaryStreamError(
        "inline stationary footer fixed fields differ");
  }
  for (std::size_t index = 152U; index < kFooterDigestOffset; ++index) {
    if (raw[index] != 0U) {
      throw InlineStationaryStreamError(
          "inline stationary footer reserved bytes differ");
    }
  }
  const Sha256Digest digest =
      per::domain_hash(kFooterDomain, raw.data(), kFooterDigestOffset);
  if (per::digest_at(raw.data() + kFooterDigestOffset) != digest) {
    throw InlineStationaryStreamError(
        "inline stationary footer digest differs");
  }
  FooterValues values{
      .first_block = per::load_u64(raw.data() + 16U),
      .block_count = per::load_u64(raw.data() + 24U),
      .total_event_records = per::load_u64(raw.data() + 32U),
      .total_junction_records = per::load_u64(raw.data() + 40U),
      .total_trace_bytes = per::load_u64(raw.data() + 48U),
      .frame_stream_sha256 = per::digest_at(raw.data() + 56U),
      .header_sha256 = per::digest_at(raw.data() + 88U),
      .gamma_stream_sha256 = per::digest_at(raw.data() + 120U),
  };
  per::require_geometry(values.first_block, values.block_count);
  if (values.total_event_records != values.block_count ||
      values.total_junction_records != values.block_count) {
    throw InlineStationaryStreamError(
        "inline stationary footer record totals differ");
  }
  require_nonzero(values.frame_stream_sha256, "frame stream");
  require_nonzero(values.header_sha256, "header");
  require_nonzero(values.gamma_stream_sha256, "Gamma stream");
  if (expected != nullptr &&
      (values.first_block != expected->first_block ||
       values.block_count != expected->block_count ||
       values.total_event_records != expected->total_event_records ||
       values.total_junction_records != expected->total_junction_records ||
       values.total_trace_bytes != expected->total_trace_bytes ||
       values.frame_stream_sha256 != expected->frame_stream_sha256 ||
       values.header_sha256 != expected->header_sha256 ||
       values.gamma_stream_sha256 != expected->gamma_stream_sha256)) {
    throw InlineStationaryStreamError(
        "inline stationary footer differs from its pin");
  }
  return values;
}

static_assert(kHeaderDigestOffset + 32U == kHeaderBytes);
static_assert(kFooterDigestOffset + 32U == kFooterBytes);

}  // namespace sparkinterval::tg::platt_inline_stationary_stream

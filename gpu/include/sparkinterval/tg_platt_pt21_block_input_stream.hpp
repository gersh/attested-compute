// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

// Authenticated per-block wire carrying the *complete* set of finite inputs
// that `tg_verifier/platt_pt21_native_record_adapter.py` needs to emit one
// canonical `PT21BLK1`:
//
//   1. the required-sign packet (`PT21SGN1`) rebuilt from the replay-owned
//      25,741 DD disks;
//   2. the independently replayed stationary trace, bound by `PT21STJ1`; and
//   3. the block-bound directed-Arb Turing inputs.
//
// The `PT21EVT1` record and the `PT21STJ1` record travel with them so the
// scanner Merkle root, the resolver identity, and the packet stay linked in
// one ordered stream.  This replaces the standalone assembly channel in which
// a separate process wrote three files per block and a manifest named them.
//
// This wire is deliberately *not* terminal.  It contains no `PT21BLK1`, no
// count telescoping, and no analytic realization flag.  A consumer must still
// run the exact-rational adapter and the native shard finalizer, and every
// Hardy-Z / multiplicity / analytic-Turing status stays false.

#include "sparkinterval/sha256.hpp"
#include "sparkinterval/tg_platt_event_record.hpp"
#include "sparkinterval/tg_platt_pt21_required_sign_packet.hpp"
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

namespace sparkinterval::tg::platt_pt21_block_input_stream {

namespace per = sparkinterval::tg::platt_event_record;
namespace psj = sparkinterval::tg::platt_stationary_junction;
namespace psr = sparkinterval::tg::platt_stationary_resolver;
namespace prs = sparkinterval::tg::platt_pt21_required_sign_packet;

inline constexpr std::uint32_t kVersion = 1U;
inline constexpr std::uint32_t kFiniteQualificationOnlyFlag = 1U;
inline constexpr std::size_t kHeaderBytes = 256U;
inline constexpr std::size_t kHeaderDigestOffset = 224U;
inline constexpr std::size_t kFramePrefixBytes = 208U;
inline constexpr std::size_t kFrameDigestBytes = 32U;
inline constexpr std::size_t kFooterBytes = 192U;
inline constexpr std::size_t kFooterDigestOffset = 160U;
inline constexpr std::uint32_t kMaximumTraceBytes =
    psr::kSourceTraceMaximumBytes;
inline constexpr std::uint32_t kMaximumTuringBytes = 16U * 1024U;

inline constexpr char kHeaderMagic[] = "PT21WBH1";
inline constexpr char kFrameMagic[] = "PT21WBF1";
inline constexpr char kFooterMagic[] = "PT21WBT1";
inline constexpr char kAlgorithmDomain[] =
    "sparkinterval/tg/platt-pt21-worker-block-input-stream/v1\0";
inline constexpr char kHeaderDomain[] =
    "sparkinterval/tg/platt-pt21-worker-block-input-header/v1\0";
inline constexpr char kFrameDomain[] =
    "sparkinterval/tg/platt-pt21-worker-block-input-frame/v1\0";
inline constexpr char kFooterDomain[] =
    "sparkinterval/tg/platt-pt21-worker-block-input-footer/v1\0";

using RawHeader = std::array<unsigned char, kHeaderBytes>;
using RawFooter = std::array<unsigned char, kFooterBytes>;

class BlockInputStreamError : public std::runtime_error {
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
  std::uint64_t total_frames = 0U;
  std::uint64_t total_packet_bytes = 0U;
  std::uint64_t total_trace_bytes = 0U;
  std::uint64_t total_turing_bytes = 0U;
  Sha256Digest frame_stream_sha256{};
  Sha256Digest header_sha256{};
  Sha256Digest gamma_stream_sha256{};
};

struct FramePayload {
  std::uint64_t block = 0U;
  std::span<const unsigned char> required_sign_packet;
  per::RawRecord event_record{};
  psj::RawRecord junction_record{};
  std::string_view stationary_trace;
  std::string_view turing_inputs;
};

struct DecodedFrame {
  std::uint64_t block = 0U;
  std::vector<unsigned char> required_sign_packet;
  per::RawRecord event_record{};
  psj::RawRecord junction_record{};
  std::string stationary_trace;
  std::string turing_inputs;
  Sha256Digest frame_sha256{};
};

inline Sha256Digest algorithm_sha256() {
  static constexpr unsigned char empty = 0U;
  return per::domain_hash(kAlgorithmDomain, &empty, 0U);
}

inline void require_nonzero(const Sha256Digest& digest,
                            std::string_view label) {
  if (per::digest_is_zero(digest)) {
    throw BlockInputStreamError(
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
  per::store_u32(raw.data() + 204U,
                 static_cast<std::uint32_t>(prs::kPacketBytes));
  const Sha256Digest digest =
      per::domain_hash(kHeaderDomain, raw.data(), kHeaderDigestOffset);
  std::memcpy(raw.data() + kHeaderDigestOffset, digest.data(), digest.size());
  return raw;
}

inline HeaderValues decode_header(const RawHeader& raw,
                                  const HeaderValues* expected = nullptr) {
  if (std::memcmp(raw.data(), kHeaderMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != kHeaderBytes ||
      per::load_u32(raw.data() + 16U) != kFramePrefixBytes ||
      per::load_u32(raw.data() + 20U) != kFooterBytes ||
      per::load_u32(raw.data() + 200U) != kFiniteQualificationOnlyFlag ||
      per::load_u32(raw.data() + 204U) !=
          static_cast<std::uint32_t>(prs::kPacketBytes)) {
    throw BlockInputStreamError("block-input stream fixed header differs");
  }
  for (std::size_t index = 208U; index < kHeaderDigestOffset; ++index) {
    if (raw[index] != 0U) {
      throw BlockInputStreamError(
          "block-input stream header reserved bytes differ");
    }
  }
  const Sha256Digest digest =
      per::domain_hash(kHeaderDomain, raw.data(), kHeaderDigestOffset);
  if (per::digest_at(raw.data() + kHeaderDigestOffset) != digest ||
      per::digest_at(raw.data() + 168U) != algorithm_sha256()) {
    throw BlockInputStreamError(
        "block-input stream header digest or algorithm differs");
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
    throw BlockInputStreamError(
        "block-input stream header differs from its identity pin");
  }
  return values;
}

// The Turing artifact must be one canonical JSON object terminated by exactly
// one newline.  The encoder does not reparse JSON; it enforces the shape the
// independent Python decoder requires and binds the digest.
inline void require_canonical_json_line(std::string_view value,
                                        std::uint32_t maximum,
                                        std::string_view label) {
  if (value.size() < 3U || value.size() > maximum ||
      value.front() != '{' || value.back() != '\n' ||
      value[value.size() - 2U] != '}' ||
      value.find('\n') != value.size() - 1U) {
    throw BlockInputStreamError(
        std::string(label) + " is not one canonical JSON line");
  }
}

inline std::vector<unsigned char> encode_frame(const FramePayload& payload) {
  const per::BlockValues event =
      per::decode_record(payload.event_record, payload.block);
  const psj::RecordValues junction = psj::decode_record(
      payload.junction_record);
  if (junction.block != payload.block ||
      junction.event_record_sha256 !=
          per::digest_at(payload.event_record.data() +
                         per::kRecordDigestOffset) ||
      junction.event_artifact_sha256 != event.event_artifact_sha256) {
    throw BlockInputStreamError(
        "block-input frame event/junction link differs");
  }
  if (payload.required_sign_packet.size() != prs::kPacketBytes ||
      std::memcmp(payload.required_sign_packet.data(), prs::kMagic, 8U) !=
          0) {
    throw BlockInputStreamError(
        "block-input frame required-sign packet is not the exact wire");
  }
  if (per::load_u64(payload.required_sign_packet.data() + 48U) !=
      prs::window_center(payload.block)) {
    throw BlockInputStreamError(
        "block-input frame packet centre is off the block's source grid");
  }
  if (payload.stationary_trace.empty() ||
      payload.stationary_trace.size() > kMaximumTraceBytes ||
      sha256(payload.stationary_trace.data(),
             payload.stationary_trace.size()) !=
          junction.stationary_trace_sha256) {
    throw BlockInputStreamError(
        "block-input frame trace differs from PT21STJ1");
  }
  require_canonical_json_line(payload.turing_inputs, kMaximumTuringBytes,
                              "Turing input artifact");

  const std::uint64_t wide_size =
      kFramePrefixBytes + payload.required_sign_packet.size() +
      payload.event_record.size() + payload.junction_record.size() +
      payload.stationary_trace.size() + payload.turing_inputs.size() +
      kFrameDigestBytes;
  if (wide_size > std::numeric_limits<std::uint32_t>::max()) {
    throw BlockInputStreamError("block-input frame exceeds uint32");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(wide_size), 0U);
  std::memcpy(raw.data(), kFrameMagic, 8U);
  per::store_u32(raw.data() + 8U, kVersion);
  per::store_u32(raw.data() + 12U, static_cast<std::uint32_t>(raw.size()));
  per::store_u64(raw.data() + 16U, payload.block);
  per::store_u32(raw.data() + 24U,
                 static_cast<std::uint32_t>(
                     payload.required_sign_packet.size()));
  per::store_u32(raw.data() + 28U,
                 static_cast<std::uint32_t>(payload.event_record.size()));
  per::store_u32(raw.data() + 32U,
                 static_cast<std::uint32_t>(payload.junction_record.size()));
  per::store_u32(raw.data() + 36U,
                 static_cast<std::uint32_t>(
                     payload.stationary_trace.size()));
  per::store_u32(raw.data() + 40U,
                 static_cast<std::uint32_t>(payload.turing_inputs.size()));
  per::store_u32(raw.data() + 44U, 0U);
  const Sha256Digest packet_digest = sha256(
      payload.required_sign_packet.data(),
      payload.required_sign_packet.size());
  const Sha256Digest event_digest =
      sha256(payload.event_record.data(), payload.event_record.size());
  const Sha256Digest junction_digest =
      sha256(payload.junction_record.data(), payload.junction_record.size());
  const Sha256Digest trace_digest = sha256(
      payload.stationary_trace.data(), payload.stationary_trace.size());
  const Sha256Digest turing_digest =
      sha256(payload.turing_inputs.data(), payload.turing_inputs.size());
  std::memcpy(raw.data() + 48U, packet_digest.data(), 32U);
  std::memcpy(raw.data() + 80U, event_digest.data(), 32U);
  std::memcpy(raw.data() + 112U, junction_digest.data(), 32U);
  std::memcpy(raw.data() + 144U, trace_digest.data(), 32U);
  std::memcpy(raw.data() + 176U, turing_digest.data(), 32U);

  std::size_t offset = kFramePrefixBytes;
  auto append = [&raw, &offset](const void* data, std::size_t size) {
    std::memcpy(raw.data() + offset, data, size);
    offset += size;
  };
  append(payload.required_sign_packet.data(),
         payload.required_sign_packet.size());
  append(payload.event_record.data(), payload.event_record.size());
  append(payload.junction_record.data(), payload.junction_record.size());
  append(payload.stationary_trace.data(), payload.stationary_trace.size());
  append(payload.turing_inputs.data(), payload.turing_inputs.size());

  const Sha256Digest frame_digest = per::domain_hash(
      kFrameDomain, raw.data(), raw.size() - kFrameDigestBytes);
  std::memcpy(raw.data() + raw.size() - kFrameDigestBytes,
              frame_digest.data(), frame_digest.size());
  return raw;
}

inline DecodedFrame decode_frame(std::span<const unsigned char> raw,
                                 std::uint64_t expected_block) {
  if (raw.size() < kFramePrefixBytes + prs::kPacketBytes +
                       per::kRecordBytes + psj::kRecordBytes + 2U +
                       kFrameDigestBytes ||
      std::memcmp(raw.data(), kFrameMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != raw.size() ||
      per::load_u64(raw.data() + 16U) != expected_block ||
      per::load_u32(raw.data() + 24U) !=
          static_cast<std::uint32_t>(prs::kPacketBytes) ||
      per::load_u32(raw.data() + 28U) != per::kRecordBytes ||
      per::load_u32(raw.data() + 32U) != psj::kRecordBytes ||
      per::load_u32(raw.data() + 44U) != 0U) {
    throw BlockInputStreamError("block-input frame fixed fields differ");
  }
  const std::uint32_t trace_bytes = per::load_u32(raw.data() + 36U);
  const std::uint32_t turing_bytes = per::load_u32(raw.data() + 40U);
  if (trace_bytes == 0U || trace_bytes > kMaximumTraceBytes ||
      turing_bytes == 0U || turing_bytes > kMaximumTuringBytes ||
      raw.size() != kFramePrefixBytes + prs::kPacketBytes +
                        per::kRecordBytes + psj::kRecordBytes +
                        trace_bytes + turing_bytes + kFrameDigestBytes) {
    throw BlockInputStreamError("block-input frame lengths differ");
  }
  const Sha256Digest frame_digest = per::domain_hash(
      kFrameDomain, raw.data(), raw.size() - kFrameDigestBytes);
  if (per::digest_at(raw.data() + raw.size() - kFrameDigestBytes) !=
      frame_digest) {
    throw BlockInputStreamError("block-input frame digest differs");
  }

  DecodedFrame result;
  result.block = expected_block;
  std::size_t offset = kFramePrefixBytes;
  result.required_sign_packet.assign(raw.data() + offset,
                                     raw.data() + offset + prs::kPacketBytes);
  offset += prs::kPacketBytes;
  std::copy_n(raw.data() + offset, result.event_record.size(),
              result.event_record.begin());
  offset += result.event_record.size();
  std::copy_n(raw.data() + offset, result.junction_record.size(),
              result.junction_record.begin());
  offset += result.junction_record.size();
  result.stationary_trace.assign(
      reinterpret_cast<const char*>(raw.data() + offset), trace_bytes);
  offset += trace_bytes;
  result.turing_inputs.assign(
      reinterpret_cast<const char*>(raw.data() + offset), turing_bytes);
  result.frame_sha256 = frame_digest;

  if (sha256(result.required_sign_packet.data(),
             result.required_sign_packet.size()) !=
          per::digest_at(raw.data() + 48U) ||
      sha256(result.event_record.data(), result.event_record.size()) !=
          per::digest_at(raw.data() + 80U) ||
      sha256(result.junction_record.data(),
             result.junction_record.size()) !=
          per::digest_at(raw.data() + 112U) ||
      sha256(result.stationary_trace.data(),
             result.stationary_trace.size()) !=
          per::digest_at(raw.data() + 144U) ||
      sha256(result.turing_inputs.data(), result.turing_inputs.size()) !=
          per::digest_at(raw.data() + 176U)) {
    throw BlockInputStreamError("block-input frame payload digest differs");
  }

  // Reuse the encoder's nested packet/event/junction/trace/Turing checks.
  const FramePayload payload{
      .block = expected_block,
      .required_sign_packet = result.required_sign_packet,
      .event_record = result.event_record,
      .junction_record = result.junction_record,
      .stationary_trace = result.stationary_trace,
      .turing_inputs = result.turing_inputs,
  };
  const std::vector<unsigned char> canonical = encode_frame(payload);
  if (!std::equal(canonical.begin(), canonical.end(), raw.begin(),
                  raw.end())) {
    throw BlockInputStreamError("block-input frame is not canonical");
  }
  return result;
}

inline RawFooter encode_footer(const FooterValues& values) {
  per::require_geometry(values.first_block, values.block_count);
  if (values.total_frames != values.block_count ||
      values.total_packet_bytes !=
          values.block_count * prs::kPacketBytes) {
    throw BlockInputStreamError("block-input footer totals differ");
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
  per::store_u64(raw.data() + 32U, values.total_frames);
  per::store_u64(raw.data() + 40U, values.total_packet_bytes);
  per::store_u64(raw.data() + 48U, values.total_trace_bytes);
  per::store_u64(raw.data() + 56U, values.total_turing_bytes);
  std::memcpy(raw.data() + 64U, values.frame_stream_sha256.data(), 32U);
  std::memcpy(raw.data() + 96U, values.header_sha256.data(), 32U);
  std::memcpy(raw.data() + 128U, values.gamma_stream_sha256.data(), 32U);
  const Sha256Digest digest =
      per::domain_hash(kFooterDomain, raw.data(), kFooterDigestOffset);
  std::memcpy(raw.data() + kFooterDigestOffset, digest.data(), digest.size());
  return raw;
}

inline FooterValues decode_footer(const RawFooter& raw,
                                  const FooterValues* expected = nullptr) {
  if (std::memcmp(raw.data(), kFooterMagic, 8U) != 0 ||
      per::load_u32(raw.data() + 8U) != kVersion ||
      per::load_u32(raw.data() + 12U) != kFooterBytes) {
    throw BlockInputStreamError("block-input footer fixed fields differ");
  }
  const Sha256Digest digest =
      per::domain_hash(kFooterDomain, raw.data(), kFooterDigestOffset);
  if (per::digest_at(raw.data() + kFooterDigestOffset) != digest) {
    throw BlockInputStreamError("block-input footer digest differs");
  }
  FooterValues values{
      .first_block = per::load_u64(raw.data() + 16U),
      .block_count = per::load_u64(raw.data() + 24U),
      .total_frames = per::load_u64(raw.data() + 32U),
      .total_packet_bytes = per::load_u64(raw.data() + 40U),
      .total_trace_bytes = per::load_u64(raw.data() + 48U),
      .total_turing_bytes = per::load_u64(raw.data() + 56U),
      .frame_stream_sha256 = per::digest_at(raw.data() + 64U),
      .header_sha256 = per::digest_at(raw.data() + 96U),
      .gamma_stream_sha256 = per::digest_at(raw.data() + 128U),
  };
  per::require_geometry(values.first_block, values.block_count);
  if (values.total_frames != values.block_count ||
      values.total_packet_bytes !=
          values.block_count * prs::kPacketBytes) {
    throw BlockInputStreamError("block-input footer totals differ");
  }
  require_nonzero(values.frame_stream_sha256, "frame stream");
  require_nonzero(values.header_sha256, "header");
  require_nonzero(values.gamma_stream_sha256, "Gamma stream");
  if (expected != nullptr &&
      (values.first_block != expected->first_block ||
       values.block_count != expected->block_count ||
       values.total_frames != expected->total_frames ||
       values.total_packet_bytes != expected->total_packet_bytes ||
       values.total_trace_bytes != expected->total_trace_bytes ||
       values.total_turing_bytes != expected->total_turing_bytes ||
       values.frame_stream_sha256 != expected->frame_stream_sha256 ||
       values.header_sha256 != expected->header_sha256 ||
       values.gamma_stream_sha256 != expected->gamma_stream_sha256)) {
    throw BlockInputStreamError(
        "block-input footer differs from its pin");
  }
  return values;
}

static_assert(kHeaderDigestOffset + 32U == kHeaderBytes);
static_assert(kFooterDigestOffset + 32U == kFooterBytes);

}  // namespace sparkinterval::tg::platt_pt21_block_input_stream

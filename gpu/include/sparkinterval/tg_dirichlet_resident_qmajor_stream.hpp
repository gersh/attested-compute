// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_formulaic_qmajor.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <utility>

namespace sparkinterval::tg::dirichlet_resident_qmajor_stream {

namespace fq = sparkinterval::tg::dirichlet_formulaic_qmajor;

inline constexpr std::uint32_t kFormatVersion = 1U;
inline constexpr std::uint32_t kBoundedSchedule = 0U;
inline constexpr std::uint32_t kFullSourceSchedule = 1U;
inline constexpr std::uint32_t kBoundedProjectionCoverage = 0U;
inline constexpr std::uint32_t kExactCandidatePhaseCoverage = 1U;
inline constexpr std::uint32_t kPhaseCount = 10U;
inline constexpr std::uint32_t kMaximumRows = 39488U;
inline constexpr std::uint32_t kMaximumQPerLane = 64U;
inline constexpr std::uint32_t kMaximumTargetsPerLane = 39488U;
inline constexpr std::uint32_t kMaximumLaneCount = 8192U;
inline constexpr std::uint32_t kMaximumBatchCount = 64U;
inline constexpr std::uint64_t kMaximumGroupOrder = 400000U;
inline constexpr std::uint64_t kMaximumTargetValues =
    kMaximumBatchCount * kMaximumGroupOrder;
inline constexpr std::uint64_t kMaximumPhaseTargets = 56981100U;
inline constexpr std::uint64_t kMaximumPhaseRowReferences = 1270668873U;
inline constexpr std::uint64_t kMaximumPhaseValues = 34172695117846U;
inline constexpr std::uint64_t kMaximumOutputPhaseTargets = 5380665U;
inline constexpr std::uint64_t kTgdaffiHeaderBytes = 72U;
inline constexpr std::uint64_t kComplexIntervalBytes = 32U;
inline constexpr std::uint64_t kMaximumProjectedPhaseOutputBytes =
    kMaximumOutputPhaseTargets * kTgdaffiHeaderBytes +
    kMaximumPhaseValues * kComplexIntervalBytes;
inline constexpr std::uint64_t kMaximumLaneInputBytes = 128U << 20U;
inline constexpr std::uint64_t kMaximumSidecarInputBytes = 64ULL << 30U;
inline constexpr std::uint64_t kDeviceMemorySafetyReserveBytes =
    512U << 20U;
inline constexpr std::array<std::uint32_t, kPhaseCount + 1U> kPhaseCuts = {
    0U,     768U,   1600U,  2368U,  3200U,  4032U,
    5568U,  9600U,  49088U, 88512U, 127988U};
inline constexpr std::array<unsigned char, 32U> kCandidateReportSha256 = {
    0xeaU, 0xe0U, 0x86U, 0x77U, 0x13U, 0x56U, 0xccU, 0x3eU,
    0x2cU, 0xc2U, 0x67U, 0x80U, 0x01U, 0x26U, 0x86U, 0xfdU,
    0xbcU, 0x3aU, 0x80U, 0x97U, 0xaaU, 0x76U, 0xa3U, 0x41U,
    0x70U, 0x56U, 0xfeU, 0x74U, 0xf5U, 0xa3U, 0x2eU, 0xb6U};

inline constexpr char kPlanDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_PLAN_V1";
inline constexpr char kLanePartitionDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANES_V1";
inline constexpr char kTargetDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_TARGET_V1";
inline constexpr char kTargetChainDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_TARGET_CHAIN_V1";
inline constexpr char kLaneTargetChainDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANE_TARGET_CHAIN_V1";
inline constexpr char kLanePlanDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANE_PLAN_V1";
inline constexpr char kLaneChainDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_LANE_CHAIN_V1";
inline constexpr char kRowChainDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_ROW_CHAIN_V1";
inline constexpr char kSidecarDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_STREAM_SIDECAR_V1";

inline constexpr char kRowHeaderMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'R', 'H', '1'};
inline constexpr char kRowFooterMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'R', 'F', '1'};
inline constexpr char kStreamHeaderMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'S', 'H', '1'};
inline constexpr char kLaneHeaderMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'L', 'H', '1'};
inline constexpr char kTargetMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'T', 'G', '1'};
inline constexpr char kLaneFooterMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'L', 'F', '1'};
inline constexpr char kStreamFooterMagic[8] = {
    'T', 'G', 'D', 'Q', 'S', 'S', 'F', '1'};

struct RowArtifactHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t schedule_classification;
  std::uint32_t coverage_mode;
  std::uint32_t phase_index;
  std::uint32_t row_count;
  std::uint32_t reserved;
  std::uint64_t start_execution_q_index;
  std::uint64_t stop_execution_q_index;
  std::uint64_t canonical_first_t_index;
  std::uint64_t canonical_t_index_stop_exclusive;
  std::uint64_t loaded_first_t_index;
  std::uint64_t loaded_t_index_stop_exclusive;
  std::uint64_t row_header_bytes;
  std::uint64_t row_payload_bytes;
  std::uint64_t input_size_bytes;
  unsigned char schedule_manifest_sha256[32];
  unsigned char schedule_execution_order_sha256[32];
  unsigned char phase_plan_sha256[32];
  unsigned char candidate_report_sha256[32];
  unsigned char source_contract_sha256[32];
  unsigned char lattice_source_sha256[32];
  unsigned char recovery_seed_sha256[32];
  unsigned char lane_partition_sha256[32];
};

struct RowArtifactFooter {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t row_count;
  std::uint64_t input_bytes_before_footer;
  std::uint64_t row_payload_bytes;
  unsigned char row_chain_sha256[32];
  unsigned char row_stream_sha256[32];
  unsigned char reserved_sha256[32];
};

struct StreamHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t schedule_classification;
  std::uint32_t coverage_mode;
  std::uint32_t phase_index;
  std::uint32_t lane_count;
  std::uint32_t maximum_q_per_lane;
  std::uint32_t maximum_targets_per_lane;
  std::uint32_t maximum_batch_count;
  std::uint32_t reserved0;
  std::uint32_t reserved1;
  std::uint64_t start_execution_q_index;
  std::uint64_t stop_execution_q_index;
  std::uint64_t canonical_first_t_index;
  std::uint64_t canonical_t_index_stop_exclusive;
  std::uint64_t loaded_first_t_index;
  std::uint64_t loaded_t_index_stop_exclusive;
  std::uint64_t active_q_count;
  std::uint64_t target_count;
  std::uint64_t target_row_reference_count;
  std::uint64_t value_count;
  std::uint64_t input_size_bytes;
  std::uint64_t maximum_group_order;
  unsigned char schedule_manifest_sha256[32];
  unsigned char schedule_execution_order_sha256[32];
  unsigned char phase_plan_sha256[32];
  unsigned char candidate_report_sha256[32];
  unsigned char source_contract_sha256[32];
  unsigned char row_artifact_sha256[32];
  unsigned char recovery_seed_sha256[32];
  unsigned char sidecar_source_sha256[32];
  unsigned char lane_partition_sha256[32];
};

struct LaneHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint32_t lane_index;
  std::uint32_t q_count;
  std::uint64_t start_execution_q_index;
  std::uint64_t stop_execution_q_index;
  std::uint64_t target_count;
  std::uint64_t target_row_reference_count;
  std::uint64_t value_count;
  std::uint64_t sidecar_bytes;
  std::uint64_t lane_input_bytes;
  std::uint64_t maximum_group_order;
  unsigned char previous_lane_chain_sha256[32];
  unsigned char lane_plan_sha256[32];
};

struct TargetHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t execution_q_index;
  std::uint32_t q;
  std::uint32_t phase_index;
  std::uint32_t lane_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;
  std::uint32_t batch_count;
  std::uint32_t component_count;
  std::uint32_t reserved2;
  std::uint64_t group_order;
  std::uint64_t value_count;
  std::uint64_t factor_bytes;
  std::uint64_t tail_bytes;
  unsigned char target_sha256[32];
  unsigned char sidecar_sha256[32];
};

struct LaneFooter {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint32_t lane_index;
  std::uint32_t reserved2;
  std::uint64_t q_count;
  std::uint64_t target_count;
  std::uint64_t target_row_reference_count;
  std::uint64_t value_count;
  std::uint64_t sidecar_bytes;
  std::uint64_t input_bytes_before_footer;
  unsigned char target_chain_sha256[32];
  unsigned char lane_stream_sha256[32];
  unsigned char lane_chain_sha256[32];
  unsigned char reserved_sha256[32];
};

struct StreamFooter {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t lane_count;
  std::uint64_t active_q_count;
  std::uint64_t target_count;
  std::uint64_t target_row_reference_count;
  std::uint64_t value_count;
  std::uint64_t sidecar_bytes;
  std::uint64_t input_bytes_before_footer;
  unsigned char lane_chain_sha256[32];
  unsigned char target_chain_sha256[32];
  unsigned char body_stream_sha256[32];
  unsigned char reserved_sha256[32];
};

struct Target {
  std::uint64_t execution_q_index;
  std::uint32_t q;
  std::uint32_t phase_index;
  std::uint32_t lane_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;
  std::uint32_t batch_count;

  friend constexpr bool operator==(const Target&, const Target&) = default;
};

static_assert(sizeof(RowArtifactHeader) == 360U);
static_assert(sizeof(RowArtifactFooter) == 136U);
static_assert(sizeof(StreamHeader) == 432U);
static_assert(sizeof(LaneHeader) == 152U);
static_assert(sizeof(TargetHeader) == 152U);
static_assert(sizeof(LaneFooter) == 200U);
static_assert(sizeof(StreamFooter) == 200U);

inline constexpr std::uint64_t kMaximumRowArtifactBytes =
    sizeof(RowArtifactHeader) +
    static_cast<std::uint64_t>(kMaximumRows) * (64U + (1U << 20U)) +
    sizeof(RowArtifactFooter);

inline std::pair<std::uint32_t, std::uint32_t> phaseBounds(
    std::uint32_t phase_index) {
  if (phase_index >= kPhaseCount) {
    throw std::runtime_error("resident stream phase index is outside ten phases");
  }
  return {kPhaseCuts[phase_index], kPhaseCuts[phase_index + 1U]};
}

inline void appendTarget(detail::Sha256* digest, const Target& target) {
  fq::appendLe64(digest, target.execution_q_index);
  fq::appendLe32(digest, target.q);
  fq::appendLe32(digest, target.phase_index);
  fq::appendLe32(digest, target.lane_index);
  fq::appendLe32(digest, target.first_t_index);
  fq::appendLe32(digest, target.t_index_stop_exclusive);
  fq::appendLe32(digest, target.batch_count);
}

inline Sha256Digest targetDigest(const Target& target) {
  detail::Sha256 digest;
  digest.update(kTargetDomain, sizeof(kTargetDomain) - 1U);
  appendTarget(&digest, target);
  return digest.finish();
}

inline Sha256Digest planDigest(
    const Sha256Digest& schedule_manifest_sha256,
    const Sha256Digest& schedule_execution_order_sha256,
    const Sha256Digest& lane_partition_sha256,
    std::uint32_t schedule_classification, std::uint32_t coverage_mode,
    std::uint32_t phase_index, std::uint32_t canonical_first_t_index,
    std::uint32_t canonical_t_index_stop_exclusive,
    std::uint32_t loaded_first_t_index,
    std::uint32_t loaded_t_index_stop_exclusive,
    std::uint64_t start_execution_q_index,
    std::uint64_t stop_execution_q_index) {
  const auto [expected_first, expected_stop] = phaseBounds(phase_index);
  if ((schedule_classification != kBoundedSchedule &&
       schedule_classification != kFullSourceSchedule) ||
      (coverage_mode != kBoundedProjectionCoverage &&
       coverage_mode != kExactCandidatePhaseCoverage) ||
      canonical_first_t_index != expected_first ||
      canonical_t_index_stop_exclusive != expected_stop ||
      loaded_first_t_index < canonical_first_t_index ||
      loaded_t_index_stop_exclusive > canonical_t_index_stop_exclusive ||
      loaded_first_t_index >= loaded_t_index_stop_exclusive ||
      loaded_t_index_stop_exclusive - loaded_first_t_index > kMaximumRows ||
      start_execution_q_index >= stop_execution_q_index ||
      (coverage_mode == kBoundedProjectionCoverage &&
       schedule_classification != kBoundedSchedule) ||
      (coverage_mode == kExactCandidatePhaseCoverage &&
       (schedule_classification != kFullSourceSchedule ||
        loaded_first_t_index != canonical_first_t_index ||
        loaded_t_index_stop_exclusive !=
            canonical_t_index_stop_exclusive))) {
    throw std::runtime_error("resident stream plan geometry is malformed");
  }
  detail::Sha256 digest;
  digest.update(kPlanDomain, sizeof(kPlanDomain) - 1U);
  digest.update(
      schedule_manifest_sha256.data(), schedule_manifest_sha256.size());
  digest.update(
      schedule_execution_order_sha256.data(),
      schedule_execution_order_sha256.size());
  digest.update(
      lane_partition_sha256.data(), lane_partition_sha256.size());
  digest.update(
      kCandidateReportSha256.data(), kCandidateReportSha256.size());
  fq::appendLe32(&digest, schedule_classification);
  fq::appendLe32(&digest, coverage_mode);
  fq::appendLe32(&digest, phase_index);
  fq::appendLe32(&digest, canonical_first_t_index);
  fq::appendLe32(&digest, canonical_t_index_stop_exclusive);
  fq::appendLe32(&digest, loaded_first_t_index);
  fq::appendLe32(&digest, loaded_t_index_stop_exclusive);
  fq::appendLe64(&digest, start_execution_q_index);
  fq::appendLe64(&digest, stop_execution_q_index);
  fq::appendLe32(&digest, kMaximumRows);
  fq::appendLe32(&digest, kMaximumQPerLane);
  fq::appendLe32(&digest, kMaximumTargetsPerLane);
  fq::appendLe32(&digest, kMaximumBatchCount);
  return digest.finish();
}

inline Sha256Digest initialRowChain(const Sha256Digest& phase_plan_sha256) {
  detail::Sha256 digest;
  digest.update(kRowChainDomain, sizeof(kRowChainDomain) - 1U);
  digest.update(phase_plan_sha256.data(), phase_plan_sha256.size());
  return digest.finish();
}

inline Sha256Digest advanceRowChain(
    const Sha256Digest& previous, std::uint64_t t_index,
    const Sha256Digest& payload_sha256) {
  detail::Sha256 digest;
  digest.update(kRowChainDomain, sizeof(kRowChainDomain) - 1U);
  digest.update(previous.data(), previous.size());
  fq::appendLe64(&digest, t_index);
  digest.update(payload_sha256.data(), payload_sha256.size());
  return digest.finish();
}

inline Sha256Digest initialTargetChain(
    const Sha256Digest& phase_plan_sha256) {
  detail::Sha256 digest;
  digest.update(kTargetChainDomain, sizeof(kTargetChainDomain) - 1U);
  digest.update(phase_plan_sha256.data(), phase_plan_sha256.size());
  return digest.finish();
}

inline Sha256Digest initialLaneTargetChain(
    const Sha256Digest& phase_plan_sha256, std::uint32_t lane_index) {
  detail::Sha256 digest;
  digest.update(
      kLaneTargetChainDomain, sizeof(kLaneTargetChainDomain) - 1U);
  digest.update(phase_plan_sha256.data(), phase_plan_sha256.size());
  fq::appendLe32(&digest, lane_index);
  return digest.finish();
}

inline Sha256Digest advanceTargetChain(
    const Sha256Digest& previous, const Target& target, bool lane_chain) {
  detail::Sha256 digest;
  if (lane_chain) {
    digest.update(
        kLaneTargetChainDomain, sizeof(kLaneTargetChainDomain) - 1U);
  } else {
    digest.update(kTargetChainDomain, sizeof(kTargetChainDomain) - 1U);
  }
  digest.update(previous.data(), previous.size());
  appendTarget(&digest, target);
  return digest.finish();
}

inline Sha256Digest lanePlanDigest(
    const Sha256Digest& phase_plan_sha256, const LaneHeader& lane) {
  detail::Sha256 digest;
  digest.update(kLanePlanDomain, sizeof(kLanePlanDomain) - 1U);
  digest.update(phase_plan_sha256.data(), phase_plan_sha256.size());
  fq::appendLe32(&digest, lane.lane_index);
  fq::appendLe32(&digest, lane.q_count);
  fq::appendLe64(&digest, lane.start_execution_q_index);
  fq::appendLe64(&digest, lane.stop_execution_q_index);
  fq::appendLe64(&digest, lane.target_count);
  fq::appendLe64(&digest, lane.target_row_reference_count);
  fq::appendLe64(&digest, lane.value_count);
  fq::appendLe64(&digest, lane.sidecar_bytes);
  fq::appendLe64(&digest, lane.lane_input_bytes);
  fq::appendLe64(&digest, lane.maximum_group_order);
  return digest.finish();
}

inline Sha256Digest initialLaneChain(
    const Sha256Digest& phase_plan_sha256,
    const Sha256Digest& lane_partition_sha256) {
  detail::Sha256 digest;
  digest.update(kLaneChainDomain, sizeof(kLaneChainDomain) - 1U);
  digest.update(phase_plan_sha256.data(), phase_plan_sha256.size());
  digest.update(
      lane_partition_sha256.data(), lane_partition_sha256.size());
  return digest.finish();
}

inline Sha256Digest advanceLaneChain(
    const Sha256Digest& previous, const Sha256Digest& lane_plan_sha256,
    const Sha256Digest& target_chain_sha256,
    const Sha256Digest& lane_stream_sha256) {
  detail::Sha256 digest;
  digest.update(kLaneChainDomain, sizeof(kLaneChainDomain) - 1U);
  digest.update(previous.data(), previous.size());
  digest.update(lane_plan_sha256.data(), lane_plan_sha256.size());
  digest.update(target_chain_sha256.data(), target_chain_sha256.size());
  digest.update(lane_stream_sha256.data(), lane_stream_sha256.size());
  return digest.finish();
}

}  // namespace sparkinterval::tg::dirichlet_resident_qmajor_stream

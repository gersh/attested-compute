// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_formulaic_qmajor.hpp"

#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace sparkinterval::tg::dirichlet_resident_qmajor_phase {

namespace fq = sparkinterval::tg::dirichlet_formulaic_qmajor;

inline constexpr std::uint32_t kFormatVersion = 1U;
inline constexpr std::uint32_t kMaximumRows = 64U;
inline constexpr std::uint32_t kMaximumTargets = 64U;
inline constexpr std::uint64_t kMaximumValues = 1U << 24U;
inline constexpr std::uint64_t kMaximumInputBytes = 80U << 20U;
inline constexpr std::uint64_t kMaximumScheduleRecords = 256U;
inline constexpr std::uint64_t kDeviceMemorySafetyReserveBytes =
    512U << 20U;
inline constexpr char kPlanDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_PHASE_PLAN_V1";
inline constexpr char kChainDomain[] =
    "TG_DIRICHLET_RESIDENT_QMAJOR_PHASE_CHAIN_V1";
inline constexpr char kRowBindingDomain[] =
    "sparkinterval/tg/dirichlet-resident-qmajor-phase/rows/v1";
inline constexpr char kSidecarDomain[] =
    "sparkinterval/tg/dirichlet-resident-qmajor-phase/sidecar/v1";
inline constexpr char kHeaderMagic[8] = {
    'T', 'G', 'D', 'Q', 'R', 'P', 'H', '1'};
inline constexpr char kTargetMagic[8] = {
    'T', 'G', 'D', 'Q', 'R', 'P', 'Q', '1'};
inline constexpr char kFooterMagic[8] = {
    'T', 'G', 'D', 'Q', 'R', 'P', 'F', '1'};

struct Header {
  char magic[8];
  std::uint32_t version;
  std::uint32_t schedule_classification;
  std::uint32_t maximum_rows;
  std::uint32_t maximum_targets;
  std::uint32_t phase_index;
  std::uint32_t row_count;
  std::uint32_t target_count;
  std::uint32_t reserved;
  std::uint64_t start_execution_q_index;
  std::uint64_t stop_execution_q_index;
  std::uint64_t first_t_index;
  std::uint64_t t_index_stop_exclusive;
  std::uint64_t value_count;
  std::uint64_t row_header_bytes;
  std::uint64_t row_payload_bytes;
  std::uint64_t target_header_bytes;
  std::uint64_t factor_record_bytes;
  std::uint64_t tail_record_bytes;
  std::uint64_t input_size_bytes;
  unsigned char schedule_manifest_sha256[32];
  unsigned char schedule_execution_order_sha256[32];
  unsigned char phase_plan_sha256[32];
  unsigned char source_contract_sha256[32];
  unsigned char lattice_source_sha256[32];
  unsigned char recovery_seed_sha256[32];
  unsigned char sidecar_source_sha256[32];
  unsigned char row_bindings_sha256[32];
};

struct TargetHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t execution_q_index;
  std::uint32_t q;
  std::uint32_t phase_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;
  std::uint32_t batch_count;
  std::uint32_t component_count;
  std::uint64_t group_order;
  std::uint64_t value_count;
  std::uint64_t factor_bytes;
  std::uint64_t tail_bytes;
  unsigned char target_sha256[32];
  unsigned char sidecar_sha256[32];
};

struct Footer {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t row_count;
  std::uint64_t target_count;
  std::uint64_t target_row_reference_count;
  std::uint64_t value_count;
  std::uint64_t sidecar_bytes;
  std::uint64_t input_bytes_before_footer;
  std::uint64_t descriptor_reconstruction_count;
  std::uint64_t descriptor_h2d_upload_count;
  std::uint64_t lattice_h2d_upload_count;
  unsigned char target_chain_sha256[32];
  unsigned char row_stream_sha256[32];
  unsigned char target_stream_sha256[32];
  unsigned char reserved_sha256[32];
};

static_assert(sizeof(Header) == 384U);
static_assert(sizeof(TargetHeader) == 144U);
static_assert(sizeof(Footer) == 216U);

inline Sha256Digest planDigest(
    const Sha256Digest& schedule_manifest_sha256,
    const Sha256Digest& schedule_execution_order_sha256,
    std::size_t start_execution_q_index,
    std::size_t stop_execution_q_index,
    std::uint32_t phase_index,
    std::uint32_t first_t_index,
    std::uint32_t t_index_stop_exclusive) {
  if (start_execution_q_index >= stop_execution_q_index ||
      stop_execution_q_index - start_execution_q_index >
          kMaximumScheduleRecords ||
      first_t_index >= t_index_stop_exclusive ||
      t_index_stop_exclusive - first_t_index > kMaximumRows) {
    throw std::runtime_error(
        "resident q-major phase plan is outside its bound");
  }
  detail::Sha256 digest;
  digest.update(kPlanDomain, sizeof(kPlanDomain) - 1U);
  digest.update(
      schedule_manifest_sha256.data(),
      schedule_manifest_sha256.size());
  digest.update(
      schedule_execution_order_sha256.data(),
      schedule_execution_order_sha256.size());
  fq::appendLe64(&digest, start_execution_q_index);
  fq::appendLe64(&digest, stop_execution_q_index);
  fq::appendLe32(&digest, phase_index);
  fq::appendLe32(&digest, first_t_index);
  fq::appendLe32(&digest, t_index_stop_exclusive);
  fq::appendLe32(&digest, kMaximumRows);
  fq::appendLe32(&digest, kMaximumTargets);
  return digest.finish();
}

inline Sha256Digest initialTargetChain(const Sha256Digest& phase_plan_sha256) {
  detail::Sha256 digest;
  digest.update(kChainDomain, sizeof(kChainDomain) - 1U);
  digest.update(phase_plan_sha256.data(), phase_plan_sha256.size());
  return digest.finish();
}

inline Sha256Digest advanceTargetChain(
    const Sha256Digest& previous, const fq::Target& target) {
  detail::Sha256 digest;
  digest.update(kChainDomain, sizeof(kChainDomain) - 1U);
  digest.update(previous.data(), previous.size());
  fq::appendTarget(&digest, target);
  return digest.finish();
}

}  // namespace sparkinterval::tg::dirichlet_resident_qmajor_phase

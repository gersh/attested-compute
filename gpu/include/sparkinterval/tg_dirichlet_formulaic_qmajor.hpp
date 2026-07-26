// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace sparkinterval::tg::dirichlet_formulaic_qmajor {

constexpr std::uint32_t kMaximumBatchCount = 64U;
constexpr std::uint32_t kMaximumLaneCount = 64U;
constexpr char kAlgorithmId[] =
    "platt-dirichlet-formulaic-qmajor-target-cursor-v1";
constexpr char kBoundedScheduleClassification[] =
    "bounded-primitive-v2-conformance-permutation";
constexpr char kTargetDomain[] = "TG_DIRICHLET_FORMULAIC_QMAJOR_TARGET_V1";
constexpr char kChainDomain[] = "TG_DIRICHLET_FORMULAIC_QMAJOR_CHAIN_V1";
constexpr char kServiceRowBindingDomain[] =
    "sparkinterval/tg/dirichlet-formulaic-qmajor/frame-rows/v1";
constexpr char kServiceSidecarDomain[] =
    "sparkinterval/tg/dirichlet-formulaic-qmajor/frame-sidecar/v1";
constexpr std::uint32_t kServiceFormatVersion = 1U;
constexpr char kServiceHeaderMagic[8] = {
    'T', 'G', 'D', 'Q', 'M', 'S', 'H', '1'};
constexpr char kServiceFrameMagic[8] = {
    'T', 'G', 'D', 'Q', 'M', 'S', 'Q', '1'};
constexpr char kServiceFooterMagic[8] = {
    'T', 'G', 'D', 'Q', 'M', 'S', 'F', '1'};

struct ScheduleRecord {
  std::uint32_t q;
  std::uint32_t row_count;

  friend constexpr bool operator==(const ScheduleRecord&,
                                   const ScheduleRecord&) = default;
};

struct LaneRange {
  std::uint32_t lane_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;

  friend constexpr bool operator==(const LaneRange&,
                                   const LaneRange&) = default;
};

struct Target {
  std::uint64_t execution_q_index;
  std::uint32_t q;
  std::uint32_t lane_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;
  std::uint32_t batch_count;

  friend constexpr bool operator==(const Target&, const Target&) = default;
};

struct Accounting {
  std::uint64_t q_count = 0U;
  std::uint64_t target_count = 0U;
  std::uint64_t row_reference_count = 0U;
  std::vector<std::uint64_t> per_lane_target_counts;
  std::vector<std::uint64_t> per_lane_row_reference_counts;
};

struct Session {
  Accounting accounting;
  Sha256Digest target_chain_sha256{};
};

// Compact descriptor-free service wire.  One stream header and its small lane
// table replace a JSON control record for every target.  Each following frame
// carries at most 64 authenticated t-major lattice rows plus one factor/tail
// sidecar.  Canonical CRT descriptors are reconstructed from q by the compiled
// service and never occur on this wire.
struct ServiceHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t schedule_classification;
  std::uint32_t maximum_batch_count;
  std::uint32_t lane_count;
  std::uint64_t start_execution_q_index;
  std::uint64_t stop_execution_q_index;
  std::uint64_t target_count;
  std::uint64_t row_reference_count;
  std::uint64_t frame_header_bytes;
  std::uint64_t row_header_bytes;
  std::uint64_t row_payload_bytes;
  std::uint64_t factor_record_bytes;
  std::uint64_t tail_record_bytes;
  unsigned char schedule_manifest_sha256[32];
  unsigned char plan_sha256[32];
  unsigned char source_contract_sha256[32];
  unsigned char lattice_source_sha256[32];
  unsigned char recovery_seed_sha256[32];
  unsigned char sidecar_source_sha256[32];
};

struct ServiceLaneRecord {
  std::uint32_t lane_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;
  std::uint32_t reserved;
};

struct ServiceFrameHeader {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t execution_q_index;
  std::uint32_t q;
  std::uint32_t lane_index;
  std::uint32_t first_t_index;
  std::uint32_t t_index_stop_exclusive;
  std::uint32_t batch_count;
  std::uint32_t component_count;
  std::uint64_t group_order;
  std::uint64_t value_count;
  std::uint64_t lattice_payload_bytes;
  std::uint64_t factor_bytes;
  std::uint64_t tail_bytes;
  std::int64_t first_t_numerator;
  std::uint64_t t_denominator;
  std::uint64_t t_step_numerator;
  unsigned char target_sha256[32];
  unsigned char row_bindings_sha256[32];
  unsigned char sidecar_sha256[32];
};

struct ServiceFooter {
  char magic[8];
  std::uint32_t version;
  std::uint32_t reserved;
  std::uint64_t target_count;
  std::uint64_t row_reference_count;
  std::uint64_t value_count;
  std::uint64_t descriptor_reconstruction_count;
  std::uint64_t descriptor_h2d_upload_count;
  std::uint64_t lattice_h2d_upload_count;
  std::uint64_t input_bytes_before_footer;
  unsigned char target_chain_sha256[32];
  unsigned char frame_stream_sha256[32];
  unsigned char reserved_sha256[32];
};

static_assert(sizeof(ServiceHeader) == 288U);
static_assert(sizeof(ServiceLaneRecord) == 16U);
static_assert(sizeof(ServiceFrameHeader) == 208U);
static_assert(sizeof(ServiceFooter) == 168U);

inline void checkedAdd(std::uint64_t* destination, std::uint64_t increment,
                       const char* label) {
  if (*destination > std::numeric_limits<std::uint64_t>::max() - increment) {
    throw std::runtime_error(label);
  }
  *destination += increment;
}

inline void appendLe32(detail::Sha256* digest, std::uint32_t value) {
  std::array<unsigned char, 4> raw{};
  for (unsigned int index = 0; index < raw.size(); ++index) {
    raw[index] = static_cast<unsigned char>(value >> (8U * index));
  }
  digest->update(raw.data(), raw.size());
}

inline void appendLe64(detail::Sha256* digest, std::uint64_t value) {
  std::array<unsigned char, 8> raw{};
  for (unsigned int index = 0; index < raw.size(); ++index) {
    raw[index] = static_cast<unsigned char>(value >> (8U * index));
  }
  digest->update(raw.data(), raw.size());
}

inline void appendTarget(detail::Sha256* digest, const Target& target) {
  // Exact match for Python struct.Struct("<QIIIII").
  appendLe64(digest, target.execution_q_index);
  appendLe32(digest, target.q);
  appendLe32(digest, target.lane_index);
  appendLe32(digest, target.first_t_index);
  appendLe32(digest, target.t_index_stop_exclusive);
  appendLe32(digest, target.batch_count);
}

inline Sha256Digest targetDigest(const Target& target) {
  detail::Sha256 digest;
  digest.update(kTargetDomain, sizeof(kTargetDomain) - 1U);
  appendTarget(&digest, target);
  return digest.finish();
}

inline Sha256Digest planDigest(
    const Sha256Digest& schedule_manifest_sha256,
    std::string_view schedule_classification,
    const Sha256Digest& schedule_execution_order_sha256,
    std::span<const LaneRange> lanes,
    std::size_t start_execution_q_index,
    std::size_t stop_execution_q_index,
    std::uint32_t maximum_batch_count) {
  if (schedule_classification != kBoundedScheduleClassification ||
      lanes.empty() || lanes.size() > kMaximumLaneCount ||
      start_execution_q_index >= stop_execution_q_index ||
      maximum_batch_count == 0U ||
      maximum_batch_count > kMaximumBatchCount) {
    throw std::runtime_error(
        "formulaic canonical plan inputs are malformed");
  }
  std::string canonical =
      "{\"algorithm_id\":\"" + std::string(kAlgorithmId) +
      "\",\"lanes\":[";
  std::uint32_t expectedStart = 0U;
  for (std::size_t index = 0; index < lanes.size(); ++index) {
    const auto& lane = lanes[index];
    if (lane.lane_index != index || lane.first_t_index != expectedStart ||
        lane.t_index_stop_exclusive <= lane.first_t_index) {
      throw std::runtime_error(
          "formulaic canonical plan lanes are malformed");
    }
    if (index != 0U) canonical += ',';
    canonical +=
        "{\"first_t_index\":" + std::to_string(lane.first_t_index) +
        ",\"lane_index\":" + std::to_string(lane.lane_index) +
        ",\"row_count\":" +
        std::to_string(
            lane.t_index_stop_exclusive - lane.first_t_index) +
        ",\"t_index_stop_exclusive\":" +
        std::to_string(lane.t_index_stop_exclusive) + '}';
    expectedStart = lane.t_index_stop_exclusive;
  }
  canonical +=
      "],\"maximum_batch_count\":" +
      std::to_string(maximum_batch_count) +
      ",\"schedule_classification\":\"" +
      std::string(schedule_classification) +
      "\",\"schedule_execution_order_sha256\":\"" +
      lowercase_hex(schedule_execution_order_sha256) +
      "\",\"schedule_manifest_sha256\":\"" +
      lowercase_hex(schedule_manifest_sha256) +
      "\",\"start_execution_q_index\":" +
      std::to_string(start_execution_q_index) +
      ",\"stop_execution_q_index\":" +
      std::to_string(stop_execution_q_index) + "}\n";
  return sha256(canonical.data(), canonical.size());
}

inline void validatePlan(std::span<const ScheduleRecord> schedule,
                         std::span<const LaneRange> lanes,
                         std::size_t start_execution_q_index,
                         std::size_t stop_execution_q_index,
                         std::uint32_t maximum_batch_count) {
  if (maximum_batch_count == 0U ||
      maximum_batch_count > kMaximumBatchCount) {
    throw std::runtime_error("formulaic maximum batch count is invalid");
  }
  if (start_execution_q_index >= stop_execution_q_index ||
      stop_execution_q_index > schedule.size()) {
    throw std::runtime_error("formulaic q slice is empty or outside schedule");
  }
  std::uint32_t required_t_stop = 0U;
  for (std::size_t index = start_execution_q_index;
       index < stop_execution_q_index; ++index) {
    const auto& record = schedule[index];
    if (record.q < 3U || record.row_count == 0U) {
      throw std::runtime_error("formulaic schedule record is invalid");
    }
    required_t_stop = std::max(required_t_stop, record.row_count);
  }
  if (lanes.empty()) {
    throw std::runtime_error("formulaic cursor has no t-major lanes");
  }
  std::uint32_t expected_start = 0U;
  for (std::size_t index = 0; index < lanes.size(); ++index) {
    const auto& lane = lanes[index];
    if (lane.lane_index != index || lane.first_t_index != expected_start ||
        lane.t_index_stop_exclusive <= lane.first_t_index) {
      throw std::runtime_error(
          "formulaic lanes are skipped, reordered, overlapping, or empty");
    }
    if (index + 1U < lanes.size() &&
        lane.t_index_stop_exclusive % maximum_batch_count != 0U) {
      throw std::runtime_error(
          "formulaic lane boundary splits a canonical target batch");
    }
    expected_start = lane.t_index_stop_exclusive;
  }
  if (expected_start < required_t_stop) {
    throw std::runtime_error(
        "formulaic lanes do not cover the exact required t range");
  }
}

inline Accounting compressedAccounting(
    std::span<const ScheduleRecord> schedule,
    std::span<const LaneRange> lanes,
    std::size_t start_execution_q_index,
    std::size_t stop_execution_q_index,
    std::uint32_t maximum_batch_count = kMaximumBatchCount) {
  validatePlan(schedule, lanes, start_execution_q_index,
               stop_execution_q_index, maximum_batch_count);
  Accounting result{};
  result.q_count = stop_execution_q_index - start_execution_q_index;
  result.per_lane_target_counts.assign(lanes.size(), 0U);
  result.per_lane_row_reference_counts.assign(lanes.size(), 0U);
  for (std::size_t q_index = start_execution_q_index;
       q_index < stop_execution_q_index; ++q_index) {
    const auto row_count = schedule[q_index].row_count;
    for (const auto& lane : lanes) {
      const auto active_stop =
          std::min(row_count, lane.t_index_stop_exclusive);
      const auto active_rows =
          active_stop > lane.first_t_index
              ? static_cast<std::uint64_t>(active_stop - lane.first_t_index)
              : 0U;
      if (active_rows == 0U) continue;
      const auto targets =
          (active_rows + maximum_batch_count - 1U) / maximum_batch_count;
      checkedAdd(&result.target_count, targets,
                 "formulaic target count overflow");
      checkedAdd(&result.row_reference_count, active_rows,
                 "formulaic row count overflow");
      checkedAdd(&result.per_lane_target_counts[lane.lane_index], targets,
                 "formulaic lane target count overflow");
      checkedAdd(
          &result.per_lane_row_reference_counts[lane.lane_index], active_rows,
          "formulaic lane row count overflow");
    }
  }
  return result;
}

class Cursor {
 public:
  Cursor(std::span<const ScheduleRecord> schedule,
         std::span<const LaneRange> lanes,
         const Sha256Digest& plan_sha256,
         std::size_t start_execution_q_index,
         std::size_t stop_execution_q_index,
         std::uint32_t maximum_batch_count = kMaximumBatchCount)
      : schedule_(schedule),
        lanes_(lanes),
        expected_accounting_(compressedAccounting(
            schedule, lanes, start_execution_q_index,
            stop_execution_q_index, maximum_batch_count)),
        stop_q_index_(stop_execution_q_index),
        maximum_batch_count_(maximum_batch_count),
        q_index_(start_execution_q_index),
        per_lane_target_counts_(lanes.size(), 0U),
        per_lane_row_counts_(lanes.size(), 0U) {
    detail::Sha256 initial;
    initial.update(kChainDomain, sizeof(kChainDomain) - 1U);
    initial.update(plan_sha256.data(), plan_sha256.size());
    target_chain_sha256_ = initial.finish();
  }

  std::optional<Target> expectedTarget() {
    if (finished_) {
      throw std::runtime_error("formulaic cursor is already finalized");
    }
    advanceEmptyLanesOrQ();
    if (q_index_ == stop_q_index_) return std::nullopt;
    if (lane_index_ >= lanes_.size()) {
      throw std::runtime_error(
          "formulaic lane cursor escaped its exact partition");
    }
    const auto& record = schedule_[q_index_];
    const auto& lane = lanes_[lane_index_];
    const auto stop64 = std::min(
        {static_cast<std::uint64_t>(record.row_count),
         static_cast<std::uint64_t>(lane.t_index_stop_exclusive),
         static_cast<std::uint64_t>(next_t_) + maximum_batch_count_});
    const auto stop = static_cast<std::uint32_t>(stop64);
    if (next_t_ >= stop) {
      throw std::runtime_error("formulaic cursor generated an empty target");
    }
    return Target{q_index_, record.q, lane.lane_index, next_t_, stop,
                  static_cast<std::uint32_t>(stop - next_t_)};
  }

  void accept(const Target& target) {
    const auto expected = expectedTarget();
    if (!expected.has_value()) {
      throw std::runtime_error(
          "formulaic target supplied after exact coverage");
    }
    if (target != *expected) {
      throw std::runtime_error(
          "formulaic target was skipped, substituted, or reordered");
    }
    detail::Sha256 digest;
    digest.update(kChainDomain, sizeof(kChainDomain) - 1U);
    digest.update(target_chain_sha256_.data(), target_chain_sha256_.size());
    appendTarget(&digest, target);
    target_chain_sha256_ = digest.finish();
    checkedAdd(&target_count_, 1U, "formulaic target count overflow");
    checkedAdd(&row_reference_count_, target.batch_count,
               "formulaic row count overflow");
    checkedAdd(&per_lane_target_counts_[target.lane_index], 1U,
               "formulaic lane target count overflow");
    checkedAdd(&per_lane_row_counts_[target.lane_index], target.batch_count,
               "formulaic lane row count overflow");
    next_t_ = target.t_index_stop_exclusive;
  }

  Session finish() {
    if (finished_) {
      throw std::runtime_error("formulaic cursor was already finalized");
    }
    if (expectedTarget().has_value()) {
      throw std::runtime_error("formulaic cursor is truncated");
    }
    if (target_count_ != expected_accounting_.target_count ||
        row_reference_count_ != expected_accounting_.row_reference_count ||
        per_lane_target_counts_ !=
            expected_accounting_.per_lane_target_counts ||
        per_lane_row_counts_ !=
            expected_accounting_.per_lane_row_reference_counts) {
      throw std::runtime_error(
          "formulaic cursor totals differ from compressed accounting");
    }
    finished_ = true;
    return Session{expected_accounting_, target_chain_sha256_};
  }

 private:
  void advanceEmptyLanesOrQ() {
    while (q_index_ < stop_q_index_) {
      const auto row_stop = schedule_[q_index_].row_count;
      while (lane_index_ < lanes_.size() &&
             next_t_ >=
                 std::min(row_stop,
                          lanes_[lane_index_].t_index_stop_exclusive)) {
        ++lane_index_;
        if (lane_index_ < lanes_.size()) {
          next_t_ = lanes_[lane_index_].first_t_index;
        }
      }
      if (next_t_ < row_stop) return;
      ++q_index_;
      lane_index_ = 0U;
      next_t_ = 0U;
    }
  }

  std::span<const ScheduleRecord> schedule_;
  std::span<const LaneRange> lanes_;
  Accounting expected_accounting_;
  std::size_t stop_q_index_;
  std::uint32_t maximum_batch_count_;
  std::size_t q_index_;
  std::size_t lane_index_ = 0U;
  std::uint32_t next_t_ = 0U;
  std::uint64_t target_count_ = 0U;
  std::uint64_t row_reference_count_ = 0U;
  std::vector<std::uint64_t> per_lane_target_counts_;
  std::vector<std::uint64_t> per_lane_row_counts_;
  Sha256Digest target_chain_sha256_{};
  bool finished_ = false;
};

}  // namespace sparkinterval::tg::dirichlet_formulaic_qmajor

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-shaped resident phase worker.  Reuse the reviewed seeded arithmetic
// implementation, but replace its main with a two-artifact streaming runner.
#define SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN \
  sparkinterval_resident_stream_embedded_seeded_main
#include "h100_tg_dirichlet_largeq_seeded_batch.cu"
#undef SPARKINTERVAL_TG_SEEDED_EMBEDDED_MAIN

#include "sparkinterval/tg_dirichlet_resident_qmajor_stream.hpp"

#include <optional>

namespace rqs = sparkinterval::tg::dirichlet_resident_qmajor_stream;

namespace {

static_assert(sizeof(da::InputHeader) == rqs::kTgdaffiHeaderBytes);
static_assert(sizeof(ComplexInterval) == rqs::kComplexIntervalBytes);

struct StreamLaneExpected {
  std::uint64_t activeQCount = 0U;
  std::uint64_t targetCount = 0U;
  std::uint64_t rowReferenceCount = 0U;
  std::uint64_t valueCount = 0U;
  std::uint64_t sidecarBytes = 0U;
  std::uint64_t inputBytes = 0U;
  std::uint64_t maximumGroupOrder = 0U;
  std::uint64_t maximumBatchCount = 0U;
  std::uint64_t maximumTargetValues = 0U;
  std::uint32_t maximumQ = 0U;
};

struct StreamRowAudit {
  rqs::RowArtifactHeader header{};
  rqs::RowArtifactFooter footer{};
  std::string inputSha256;
};

struct StreamLaneAudit {
  rqs::LaneHeader header{};
  rqs::LaneFooter footer{};
};

struct StreamSidecarAudit {
  rqs::StreamHeader header{};
  rqs::StreamFooter footer{};
  std::vector<StreamLaneAudit> lanes;
  std::string inputSha256;
  std::uint64_t maximumBatchCount = 0U;
  std::uint64_t maximumTargetValues = 0U;
  std::uint32_t maximumQ = 0U;
};

struct StreamMemoryPreflight {
  std::uint64_t freeBytes = 0U;
  std::uint64_t seedBytes = 0U;
  std::uint64_t residentLatticeBytes = 0U;
  std::uint64_t maximumDescriptorBytes = 0U;
  std::uint64_t maximumFactorBytes = 0U;
  std::uint64_t maximumTailBytes = 0U;
  std::uint64_t maximumOutputBytes = 0U;
  std::uint64_t knownAllocationBytes = 0U;
};

sparkinterval::Sha256Digest streamRawDigest(
    const unsigned char raw[32]) {
  sparkinterval::Sha256Digest result{};
  std::copy_n(raw, result.size(), result.begin());
  return result;
}

bool streamDigestEquals(
    const sparkinterval::Sha256Digest& digest,
    const unsigned char raw[32]) {
  return std::equal(digest.begin(), digest.end(), raw);
}

void streamCheckedMultiply(
    std::uint64_t left, std::uint64_t right,
    std::uint64_t* result, const char* label) {
  if (right != 0U &&
      left > std::numeric_limits<std::uint64_t>::max() / right) {
    throw std::runtime_error(label);
  }
  *result = left * right;
}

std::uint64_t streamPosition(
    std::istream& input, const char* label) {
  const auto position = input.tellg();
  if (position < 0) {
    throw std::runtime_error(
        std::string("cannot determine ") + label + " position");
  }
  return static_cast<std::uint64_t>(position);
}

void streamValidateRegularFile(
    const std::filesystem::path& path, std::uint64_t maximumBytes,
    std::uint64_t expectedBytes, const char* label) {
  const auto status = std::filesystem::symlink_status(path);
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    throw std::runtime_error(
        std::string(label) + " is not a non-symlink regular file");
  }
  const auto size = std::filesystem::file_size(path);
  if (size == 0U || size > maximumBytes ||
      (expectedBytes != 0U && size != expectedBytes)) {
    throw std::runtime_error(
        std::string(label) + " size is outside its exact bound");
  }
}

sparkinterval::Sha256Digest streamLanePartitionDigest(
    const FormulaicQOrder& schedule,
    const rqs::StreamHeader& stream,
    const std::vector<StreamLaneAudit>& lanes) {
  sparkinterval::detail::Sha256 digest;
  digest.update(
      rqs::kLanePartitionDomain,
      sizeof(rqs::kLanePartitionDomain) - 1U);
  digest.update(
      schedule.fileSha256.data(), schedule.fileSha256.size());
  digest.update(
      schedule.header.execution_order_sha256,
      sizeof(schedule.header.execution_order_sha256));
  fq::appendLe64(&digest, stream.start_execution_q_index);
  fq::appendLe64(&digest, stream.stop_execution_q_index);
  fq::appendLe32(&digest, stream.lane_count);
  fq::appendLe32(&digest, rqs::kMaximumQPerLane);
  for (const auto& lane : lanes) {
    fq::appendLe32(&digest, lane.header.lane_index);
    fq::appendLe64(
        &digest, lane.header.start_execution_q_index);
    fq::appendLe64(
        &digest, lane.header.stop_execution_q_index);
  }
  return digest.finish();
}

rqs::Target streamTarget(
    std::uint64_t executionQIndex, std::uint32_t q,
    std::uint32_t phaseIndex, std::uint32_t laneIndex,
    std::uint32_t firstT, std::uint32_t stopT) {
  return {
      executionQIndex, q, phaseIndex, laneIndex, firstT, stopT,
      stopT - firstT};
}

class StreamTargetCursor {
 public:
  StreamTargetCursor(
      const FormulaicQOrder& schedule,
      const rqs::RowArtifactHeader& phase,
      const rqs::LaneHeader& lane)
      : schedule_(schedule),
        phase_(phase),
        lane_(lane),
        qIndex_(lane.start_execution_q_index),
        nextT_(static_cast<std::uint32_t>(
            phase.loaded_first_t_index)) {}

  std::optional<rqs::Target> next() {
    while (qIndex_ < lane_.stop_execution_q_index) {
      const auto& record =
          schedule_.execution[static_cast<std::size_t>(qIndex_)];
      const auto activeStop = static_cast<std::uint32_t>(
          std::min<std::uint64_t>(
              record.t_index_count,
              phase_.loaded_t_index_stop_exclusive));
      if (nextT_ < activeStop) {
        const auto first = nextT_;
        const auto stop = std::min<std::uint32_t>(
            first + rqs::kMaximumBatchCount, activeStop);
        nextT_ = stop;
        return streamTarget(
            qIndex_, record.q, phase_.phase_index,
            lane_.lane_index, first, stop);
      }
      ++qIndex_;
      nextT_ = static_cast<std::uint32_t>(
          phase_.loaded_first_t_index);
    }
    return std::nullopt;
  }

 private:
  const FormulaicQOrder& schedule_;
  const rqs::RowArtifactHeader& phase_;
  const rqs::LaneHeader& lane_;
  std::uint64_t qIndex_;
  std::uint32_t nextT_;
};

StreamLaneExpected streamExpectedLane(
    const FormulaicQOrder& schedule,
    const rqs::RowArtifactHeader& phase,
    const rqs::LaneHeader& lane) {
  StreamLaneExpected result;
  for (std::uint64_t index = lane.start_execution_q_index;
       index < lane.stop_execution_q_index; ++index) {
    const auto& record =
        schedule.execution[static_cast<std::size_t>(index)];
    const auto activeStop = std::min<std::uint64_t>(
        record.t_index_count, phase.loaded_t_index_stop_exclusive);
    if (activeStop <= phase.loaded_first_t_index) continue;
    const auto activeRows =
        activeStop - phase.loaded_first_t_index;
    const auto groupOrder = tmajorTotient(record.q);
    ++result.activeQCount;
    fq::checkedAdd(
        &result.targetCount,
        (activeRows + rqs::kMaximumBatchCount - 1U) /
            rqs::kMaximumBatchCount,
        "resident stream target count overflow");
    fq::checkedAdd(
        &result.rowReferenceCount, activeRows,
        "resident stream row-reference count overflow");
    std::uint64_t values = 0U;
    streamCheckedMultiply(
        activeRows, groupOrder, &values,
        "resident stream value count overflow");
    fq::checkedAdd(
        &result.valueCount, values,
        "resident stream value count overflow");
    result.maximumGroupOrder =
        std::max(result.maximumGroupOrder, groupOrder);
    const auto maximumBatch =
        std::min<std::uint64_t>(
            activeRows, rqs::kMaximumBatchCount);
    result.maximumBatchCount =
        std::max(result.maximumBatchCount, maximumBatch);
    result.maximumTargetValues = std::max(
        result.maximumTargetValues,
        maximumBatch * groupOrder);
    result.maximumQ = std::max(result.maximumQ, record.q);
  }
  streamCheckedMultiply(
      result.rowReferenceCount,
      sizeof(lb::FrameFactor) + sizeof(double),
      &result.sidecarBytes,
      "resident stream sidecar byte count overflow");
  result.inputBytes =
      sizeof(rqs::LaneHeader) + sizeof(rqs::LaneFooter);
  std::uint64_t targetHeaderBytes = 0U;
  streamCheckedMultiply(
      result.targetCount, sizeof(rqs::TargetHeader),
      &targetHeaderBytes,
      "resident stream target-header byte count overflow");
  fq::checkedAdd(
      &result.inputBytes, targetHeaderBytes,
      "resident stream lane byte count overflow");
  fq::checkedAdd(
      &result.inputBytes, result.sidecarBytes,
      "resident stream lane byte count overflow");
  return result;
}

sparkinterval::Sha256Digest streamSidecarDigest(
    const rqs::StreamHeader& stream, const rqs::Target& target,
    const std::vector<lb::FrameFactor>& factors,
    const std::vector<double>& tails) {
  sparkinterval::detail::Sha256 digest;
  digest.update(
      rqs::kSidecarDomain, sizeof(rqs::kSidecarDomain) - 1U);
  digest.update(
      stream.sidecar_source_sha256,
      sizeof(stream.sidecar_source_sha256));
  digest.update(
      stream.phase_plan_sha256,
      sizeof(stream.phase_plan_sha256));
  rqs::appendTarget(&digest, target);
  digest.update(
      factors.data(), factors.size() * sizeof(factors[0]));
  digest.update(tails.data(), tails.size() * sizeof(tails[0]));
  return digest.finish();
}

void streamValidateTarget(
    const rqs::TargetHeader& header,
    const rqs::Target& target) {
  const auto orders = canonicalOrders(target.q);
  const auto groupOrder = tmajorTotient(target.q);
  const auto targetSha256 = rqs::targetDigest(target);
  if (std::memcmp(header.magic, rqs::kTargetMagic, 8U) != 0 ||
      header.version != rqs::kFormatVersion ||
      header.reserved != 0U ||
      header.execution_q_index != target.execution_q_index ||
      header.q != target.q ||
      header.phase_index != target.phase_index ||
      header.lane_index != target.lane_index ||
      header.first_t_index != target.first_t_index ||
      header.t_index_stop_exclusive !=
          target.t_index_stop_exclusive ||
      header.batch_count != target.batch_count ||
      header.component_count != orders.size() ||
      header.reserved2 != 0U ||
      header.group_order != groupOrder ||
      header.value_count !=
          static_cast<std::uint64_t>(target.batch_count) *
              groupOrder ||
      header.factor_bytes !=
          static_cast<std::uint64_t>(target.batch_count) *
              sizeof(lb::FrameFactor) ||
      header.tail_bytes !=
          static_cast<std::uint64_t>(target.batch_count) *
              sizeof(double) ||
      !streamDigestEquals(targetSha256, header.target_sha256)) {
    throw std::runtime_error(
        "resident stream target is substituted or reordered");
  }
}

void streamValidateRowHeader(
    const rqs::RowArtifactHeader& header,
    const FormulaicQOrder& schedule,
    const AuthenticatedSeeds& seeds,
    const sparkinterval::Sha256Digest& expectedPlan,
    std::uint64_t actualBytes) {
  const auto seedSha256 = seededParseDigest(seeds.sha256);
  const auto [canonicalFirst, canonicalStop] =
      rqs::phaseBounds(header.phase_index);
  if (std::memcmp(
          header.magic, rqs::kRowHeaderMagic, 8U) != 0 ||
      header.version != rqs::kFormatVersion ||
      header.schedule_classification !=
          schedule.header.classification ||
      (header.schedule_classification != rqs::kBoundedSchedule &&
       header.schedule_classification !=
           rqs::kFullSourceSchedule) ||
      (header.coverage_mode != rqs::kBoundedProjectionCoverage &&
       header.coverage_mode !=
           rqs::kExactCandidatePhaseCoverage) ||
      header.row_count == 0U ||
      header.row_count > rqs::kMaximumRows ||
      header.start_execution_q_index >=
          header.stop_execution_q_index ||
      header.stop_execution_q_index > schedule.execution.size() ||
      header.canonical_first_t_index != canonicalFirst ||
      header.canonical_t_index_stop_exclusive != canonicalStop ||
      header.loaded_first_t_index < canonicalFirst ||
      header.loaded_t_index_stop_exclusive > canonicalStop ||
      header.loaded_first_t_index >=
          header.loaded_t_index_stop_exclusive ||
      header.loaded_t_index_stop_exclusive -
              header.loaded_first_t_index !=
          header.row_count ||
      (header.coverage_mode ==
           rqs::kBoundedProjectionCoverage &&
       header.schedule_classification != rqs::kBoundedSchedule) ||
      (header.coverage_mode ==
           rqs::kExactCandidatePhaseCoverage &&
       (header.schedule_classification !=
            rqs::kFullSourceSchedule ||
        header.loaded_first_t_index != canonicalFirst ||
        header.loaded_t_index_stop_exclusive != canonicalStop)) ||
      header.row_header_bytes != sizeof(tms::RowHeader) ||
      header.row_payload_bytes !=
          static_cast<std::uint64_t>(dl::kLatticeCellCount) *
              sizeof(ComplexInterval) ||
      header.input_size_bytes != actualBytes ||
      actualBytes > rqs::kMaximumRowArtifactBytes ||
      !streamDigestEquals(
          schedule.fileSha256,
          header.schedule_manifest_sha256) ||
      !std::equal(
          std::begin(schedule.header.execution_order_sha256),
          std::end(schedule.header.execution_order_sha256),
          header.schedule_execution_order_sha256) ||
      !std::equal(
          rqs::kCandidateReportSha256.begin(),
          rqs::kCandidateReportSha256.end(),
          header.candidate_report_sha256) ||
      !streamDigestEquals(
          seedSha256, header.recovery_seed_sha256)) {
    throw std::runtime_error(
        "resident stream row header or geometry differs");
  }
  const auto derivedPlan = rqs::planDigest(
      schedule.fileSha256,
      streamRawDigest(
          schedule.header.execution_order_sha256),
      streamRawDigest(header.lane_partition_sha256),
      header.schedule_classification, header.coverage_mode,
      header.phase_index,
      static_cast<std::uint32_t>(
          header.canonical_first_t_index),
      static_cast<std::uint32_t>(
          header.canonical_t_index_stop_exclusive),
      static_cast<std::uint32_t>(
          header.loaded_first_t_index),
      static_cast<std::uint32_t>(
          header.loaded_t_index_stop_exclusive),
      header.start_execution_q_index,
      header.stop_execution_q_index);
  if (derivedPlan != expectedPlan ||
      !streamDigestEquals(
          derivedPlan, header.phase_plan_sha256)) {
    throw std::runtime_error(
        "resident stream canonical phase plan differs");
  }
  std::uint64_t maximumRows = 0U;
  for (std::uint64_t index = header.start_execution_q_index;
       index < header.stop_execution_q_index; ++index) {
    maximumRows = std::max<std::uint64_t>(
        maximumRows,
        schedule.execution[static_cast<std::size_t>(index)]
            .t_index_count);
  }
  if (maximumRows < header.loaded_t_index_stop_exclusive) {
    throw std::runtime_error(
        "resident stream has an unused trailing row");
  }
}

StreamRowAudit auditStreamRows(
    const std::filesystem::path& path,
    const std::string& expectedInputSha256,
    const FormulaicQOrder& schedule,
    const AuthenticatedSeeds& seeds,
    const sparkinterval::Sha256Digest& expectedPlan) {
  streamValidateRegularFile(
      path, rqs::kMaximumRowArtifactBytes, 0U,
      "resident stream row artifact");
  const auto size = std::filesystem::file_size(path);
  const auto prehash = seededHashFile(path);
  if (sparkinterval::lowercase_hex(prehash) !=
      expectedInputSha256) {
    throw std::runtime_error(
        "resident stream row SHA-256 differs before parsing");
  }
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error(
        "cannot open resident stream row artifact");
  }
  StreamRowAudit audit;
  sparkinterval::detail::Sha256 whole;
  sparkinterval::detail::Sha256 rowStream;
  seededReadExact(input, &audit.header, "resident stream row header");
  tmajorDigestObject(&whole, audit.header);
  streamValidateRowHeader(
      audit.header, schedule, seeds, expectedPlan, size);
  auto rowChain =
      rqs::initialRowChain(expectedPlan);
  std::vector<ComplexInterval> payload;
  for (std::uint32_t index = 0U;
       index < audit.header.row_count; ++index) {
    tms::RowHeader row{};
    seededReadExact(input, &row, "resident stream row record");
    tmajorDigestObject(&whole, row);
    tmajorDigestObject(&rowStream, row);
    tmajorReadVector(
        input, &payload, dl::kLatticeCellCount,
        "resident stream row payload", &whole, &rowStream);
    sparkinterval::detail::Sha256 payloadDigest;
    payloadDigest.update(
        payload.data(), payload.size() * sizeof(payload[0]));
    const auto payloadSha256 = payloadDigest.finish();
    if (std::memcmp(row.magic, tms::kRowMagic, 8U) != 0 ||
        row.version != tms::kFormatVersion ||
        row.reserved != 0U ||
        row.t_index != audit.header.loaded_first_t_index + index ||
        row.payload_bytes != audit.header.row_payload_bytes ||
        !streamDigestEquals(payloadSha256, row.payload_sha256) ||
        !std::all_of(
            payload.begin(), payload.end(), [](const auto& value) {
              return finiteOrdered(value);
            })) {
      throw std::runtime_error(
          "resident stream row is substituted or malformed");
    }
    rowChain = rqs::advanceRowChain(
        rowChain, row.t_index, payloadSha256);
  }
  const auto bytesBeforeFooter =
      streamPosition(input, "resident row footer");
  seededReadExact(
      input, &audit.footer, "resident stream row footer");
  tmajorDigestObject(&whole, audit.footer);
  const auto rowStreamSha256 = rowStream.finish();
  if (input.peek() != std::ifstream::traits_type::eof() ||
      std::memcmp(
          audit.footer.magic, rqs::kRowFooterMagic, 8U) != 0 ||
      audit.footer.version != rqs::kFormatVersion ||
      audit.footer.reserved != 0U ||
      audit.footer.row_count != audit.header.row_count ||
      audit.footer.input_bytes_before_footer !=
          bytesBeforeFooter ||
      audit.footer.row_payload_bytes !=
          audit.header.row_count *
              audit.header.row_payload_bytes ||
      !streamDigestEquals(
          rowChain, audit.footer.row_chain_sha256) ||
      !streamDigestEquals(
          rowStreamSha256,
          audit.footer.row_stream_sha256) ||
      !std::all_of(
          std::begin(audit.footer.reserved_sha256),
          std::end(audit.footer.reserved_sha256),
          [](unsigned char value) { return value == 0U; })) {
    throw std::runtime_error(
        "resident stream row footer or commitment differs");
  }
  audit.inputSha256 =
      sparkinterval::lowercase_hex(whole.finish());
  if (audit.inputSha256 != expectedInputSha256 ||
      std::filesystem::file_size(path) != size) {
    throw std::runtime_error(
        "resident stream row artifact changed during replay");
  }
  return audit;
}

void streamValidateSidecarHeader(
    const rqs::StreamHeader& header,
    const FormulaicQOrder& schedule,
    const AuthenticatedSeeds& seeds,
    const sparkinterval::Sha256Digest& expectedPlan,
    const StreamRowAudit& rows,
    const sparkinterval::Sha256Digest& expectedRowSha256,
    std::uint64_t actualBytes) {
  const auto seedSha256 = seededParseDigest(seeds.sha256);
  if (std::memcmp(
          header.magic, rqs::kStreamHeaderMagic, 8U) != 0 ||
      header.version != rqs::kFormatVersion ||
      header.schedule_classification !=
          rows.header.schedule_classification ||
      header.coverage_mode != rows.header.coverage_mode ||
      header.phase_index != rows.header.phase_index ||
      header.lane_count == 0U ||
      header.lane_count > rqs::kMaximumLaneCount ||
      header.maximum_q_per_lane != rqs::kMaximumQPerLane ||
      header.maximum_targets_per_lane !=
          rqs::kMaximumTargetsPerLane ||
      header.maximum_batch_count != rqs::kMaximumBatchCount ||
      header.reserved0 != 0U || header.reserved1 != 0U ||
      header.start_execution_q_index !=
          rows.header.start_execution_q_index ||
      header.stop_execution_q_index !=
          rows.header.stop_execution_q_index ||
      header.canonical_first_t_index !=
          rows.header.canonical_first_t_index ||
      header.canonical_t_index_stop_exclusive !=
          rows.header.canonical_t_index_stop_exclusive ||
      header.loaded_first_t_index !=
          rows.header.loaded_first_t_index ||
      header.loaded_t_index_stop_exclusive !=
          rows.header.loaded_t_index_stop_exclusive ||
      header.active_q_count == 0U ||
      header.target_count == 0U ||
      header.target_count > rqs::kMaximumPhaseTargets ||
      header.target_row_reference_count >
          rqs::kMaximumPhaseRowReferences ||
      header.value_count > rqs::kMaximumPhaseValues ||
      header.input_size_bytes != actualBytes ||
      header.maximum_group_order == 0U ||
      header.maximum_group_order > rqs::kMaximumGroupOrder ||
      !streamDigestEquals(
          schedule.fileSha256,
          header.schedule_manifest_sha256) ||
      !std::equal(
          std::begin(schedule.header.execution_order_sha256),
          std::end(schedule.header.execution_order_sha256),
          header.schedule_execution_order_sha256) ||
      !streamDigestEquals(
          expectedPlan, header.phase_plan_sha256) ||
      !std::equal(
          rqs::kCandidateReportSha256.begin(),
          rqs::kCandidateReportSha256.end(),
          header.candidate_report_sha256) ||
      !std::equal(
          std::begin(rows.header.source_contract_sha256),
          std::end(rows.header.source_contract_sha256),
          header.source_contract_sha256) ||
      !streamDigestEquals(
          expectedRowSha256, header.row_artifact_sha256) ||
      !streamDigestEquals(
          seedSha256, header.recovery_seed_sha256) ||
      !std::equal(
          std::begin(rows.header.lane_partition_sha256),
          std::end(rows.header.lane_partition_sha256),
          header.lane_partition_sha256)) {
    throw std::runtime_error(
        "resident stream sidecar header or artifact binding differs");
  }
}

StreamSidecarAudit auditStreamSidecars(
    const std::filesystem::path& path,
    const std::string& expectedInputSha256,
    const FormulaicQOrder& schedule,
    const AuthenticatedSeeds& seeds,
    const sparkinterval::Sha256Digest& expectedPlan,
    const StreamRowAudit& rows,
    const sparkinterval::Sha256Digest& expectedRowSha256) {
  streamValidateRegularFile(
      path, rqs::kMaximumSidecarInputBytes, 0U,
      "resident stream sidecar artifact");
  const auto size = std::filesystem::file_size(path);
  const auto prehash = seededHashFile(path);
  if (sparkinterval::lowercase_hex(prehash) !=
      expectedInputSha256) {
    throw std::runtime_error(
        "resident stream sidecar SHA-256 differs before parsing");
  }
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error(
        "cannot open resident stream sidecar artifact");
  }

  StreamSidecarAudit audit;
  sparkinterval::detail::Sha256 whole;
  sparkinterval::detail::Sha256 bodyStream;
  seededReadExact(
      input, &audit.header, "resident stream sidecar header");
  tmajorDigestObject(&whole, audit.header);
  streamValidateSidecarHeader(
      audit.header, schedule, seeds, expectedPlan, rows,
      expectedRowSha256, size);

  auto laneChain = rqs::initialLaneChain(
      expectedPlan,
      streamRawDigest(audit.header.lane_partition_sha256));
  auto globalTargetChain = rqs::initialTargetChain(expectedPlan);
  std::uint64_t expectedLaneStart =
      audit.header.start_execution_q_index;
  std::uint64_t activeQCount = 0U;
  std::uint64_t targetCount = 0U;
  std::uint64_t rowReferences = 0U;
  std::uint64_t valueCount = 0U;
  std::uint64_t sidecarBytes = 0U;
  std::uint64_t maximumGroupOrder = 0U;

  audit.lanes.reserve(audit.header.lane_count);
  for (std::uint32_t laneIndex = 0U;
       laneIndex < audit.header.lane_count; ++laneIndex) {
    const auto laneStart =
        streamPosition(input, "resident lane start");
    StreamLaneAudit laneAudit;
    seededReadExact(
        input, &laneAudit.header, "resident stream lane header");
    tmajorDigestObject(&whole, laneAudit.header);
    tmajorDigestObject(&bodyStream, laneAudit.header);
    sparkinterval::detail::Sha256 laneStream;
    tmajorDigestObject(&laneStream, laneAudit.header);

    const auto& lane = laneAudit.header;
    if (std::memcmp(lane.magic, rqs::kLaneHeaderMagic, 8U) != 0 ||
        lane.version != rqs::kFormatVersion ||
        lane.reserved != 0U ||
        lane.lane_index != laneIndex ||
        lane.start_execution_q_index != expectedLaneStart ||
        lane.stop_execution_q_index <=
            lane.start_execution_q_index ||
        lane.stop_execution_q_index >
            audit.header.stop_execution_q_index ||
        lane.q_count !=
            lane.stop_execution_q_index -
                lane.start_execution_q_index ||
        lane.q_count == 0U ||
        lane.q_count > rqs::kMaximumQPerLane ||
        lane.target_count > rqs::kMaximumTargetsPerLane ||
        lane.lane_input_bytes > rqs::kMaximumLaneInputBytes ||
        lane.maximum_group_order > rqs::kMaximumGroupOrder ||
        !streamDigestEquals(
            laneChain, lane.previous_lane_chain_sha256)) {
      throw std::runtime_error(
          "resident stream lane header or partition differs");
    }
    const auto expected =
        streamExpectedLane(schedule, rows.header, lane);
    if (lane.target_count != expected.targetCount ||
        lane.target_row_reference_count !=
            expected.rowReferenceCount ||
        lane.value_count != expected.valueCount ||
        lane.sidecar_bytes != expected.sidecarBytes ||
        lane.lane_input_bytes != expected.inputBytes ||
        lane.maximum_group_order !=
            expected.maximumGroupOrder) {
      throw std::runtime_error(
          "resident stream lane accounting differs");
    }
    const auto lanePlan = rqs::lanePlanDigest(
        expectedPlan, lane);
    if (!streamDigestEquals(
            lanePlan, lane.lane_plan_sha256)) {
      throw std::runtime_error(
          "resident stream lane plan differs");
    }

    auto laneTargetChain = rqs::initialLaneTargetChain(
        expectedPlan, laneIndex);
    StreamTargetCursor cursor(schedule, rows.header, lane);
    std::uint64_t observedTargets = 0U;
    std::uint64_t observedRows = 0U;
    std::uint64_t observedValues = 0U;
    std::uint64_t observedSidecars = 0U;
    while (const auto target = cursor.next()) {
      rqs::TargetHeader targetHeader{};
      seededReadExact(
          input, &targetHeader, "resident stream target header");
      tmajorDigestObject(&whole, targetHeader);
      tmajorDigestObject(&bodyStream, targetHeader);
      tmajorDigestObject(&laneStream, targetHeader);
      streamValidateTarget(targetHeader, *target);

      std::vector<lb::FrameFactor> factors;
      std::vector<double> tails;
      tmajorReadVector(
          input, &factors, target->batch_count,
          "resident stream target factors", &whole, &laneStream);
      bodyStream.update(
          factors.data(), factors.size() * sizeof(factors[0]));
      tmajorReadVector(
          input, &tails, target->batch_count,
          "resident stream target tails", &whole, &laneStream);
      bodyStream.update(
          tails.data(), tails.size() * sizeof(tails[0]));
      if (!std::all_of(
              factors.begin(), factors.end(), [](const auto& value) {
                return finiteOrdered(value.q_to_the_minus_s);
              }) ||
          !std::all_of(
              tails.begin(), tails.end(), [](double value) {
                return std::isfinite(value) && value >= 0.0;
              }) ||
          !streamDigestEquals(
              streamSidecarDigest(
                  audit.header, *target, factors, tails),
              targetHeader.sidecar_sha256)) {
        throw std::runtime_error(
            "resident stream sidecar binding differs");
      }
      laneTargetChain = rqs::advanceTargetChain(
          laneTargetChain, *target, true);
      globalTargetChain = rqs::advanceTargetChain(
          globalTargetChain, *target, false);
      ++observedTargets;
      fq::checkedAdd(
          &observedRows, target->batch_count,
          "resident stream lane row count overflow");
      fq::checkedAdd(
          &observedValues, targetHeader.value_count,
          "resident stream lane value count overflow");
      fq::checkedAdd(
          &observedSidecars,
          targetHeader.factor_bytes + targetHeader.tail_bytes,
          "resident stream lane sidecar count overflow");
    }

    const auto bytesBeforeLaneFooter =
        streamPosition(input, "resident lane footer") - laneStart;
    const auto laneStreamSha256 = laneStream.finish();
    const auto expectedLaneChain = rqs::advanceLaneChain(
        laneChain, lanePlan, laneTargetChain, laneStreamSha256);
    seededReadExact(
        input, &laneAudit.footer, "resident stream lane footer");
    tmajorDigestObject(&whole, laneAudit.footer);
    tmajorDigestObject(&bodyStream, laneAudit.footer);
    const auto& footer = laneAudit.footer;
    if (std::memcmp(
            footer.magic, rqs::kLaneFooterMagic, 8U) != 0 ||
        footer.version != rqs::kFormatVersion ||
        footer.reserved != 0U ||
        footer.lane_index != laneIndex ||
        footer.reserved2 != 0U ||
        footer.q_count != lane.q_count ||
        footer.target_count != observedTargets ||
        footer.target_row_reference_count != observedRows ||
        footer.value_count != observedValues ||
        footer.sidecar_bytes != observedSidecars ||
        footer.input_bytes_before_footer !=
            bytesBeforeLaneFooter ||
        !streamDigestEquals(
            laneTargetChain, footer.target_chain_sha256) ||
        !streamDigestEquals(
            laneStreamSha256, footer.lane_stream_sha256) ||
        !streamDigestEquals(
            expectedLaneChain, footer.lane_chain_sha256) ||
        !std::all_of(
            std::begin(footer.reserved_sha256),
            std::end(footer.reserved_sha256),
            [](unsigned char value) { return value == 0U; }) ||
        streamPosition(input, "resident lane end") - laneStart !=
            lane.lane_input_bytes) {
      throw std::runtime_error(
          "resident stream lane footer or commitment differs");
    }
    laneChain = expectedLaneChain;
    expectedLaneStart = lane.stop_execution_q_index;
    fq::checkedAdd(
        &activeQCount, expected.activeQCount,
        "resident stream active-q count overflow");
    fq::checkedAdd(
        &targetCount, observedTargets,
        "resident stream target count overflow");
    fq::checkedAdd(
        &rowReferences, observedRows,
        "resident stream row-reference count overflow");
    fq::checkedAdd(
        &valueCount, observedValues,
        "resident stream value count overflow");
    fq::checkedAdd(
        &sidecarBytes, observedSidecars,
        "resident stream sidecar byte count overflow");
    maximumGroupOrder = std::max(
        maximumGroupOrder, expected.maximumGroupOrder);
    audit.maximumBatchCount = std::max(
        audit.maximumBatchCount, expected.maximumBatchCount);
    audit.maximumTargetValues = std::max(
        audit.maximumTargetValues, expected.maximumTargetValues);
    audit.maximumQ = std::max(audit.maximumQ, expected.maximumQ);
    audit.lanes.push_back(laneAudit);
  }

  if (expectedLaneStart !=
      audit.header.stop_execution_q_index) {
    throw std::runtime_error(
        "resident stream lanes do not cover the q range");
  }
  const auto partition = streamLanePartitionDigest(
      schedule, audit.header, audit.lanes);
  const auto derivedPlan = rqs::planDigest(
      schedule.fileSha256,
      streamRawDigest(
          schedule.header.execution_order_sha256),
      partition, audit.header.schedule_classification,
      audit.header.coverage_mode, audit.header.phase_index,
      static_cast<std::uint32_t>(
          audit.header.canonical_first_t_index),
      static_cast<std::uint32_t>(
          audit.header.canonical_t_index_stop_exclusive),
      static_cast<std::uint32_t>(
          audit.header.loaded_first_t_index),
      static_cast<std::uint32_t>(
          audit.header.loaded_t_index_stop_exclusive),
      audit.header.start_execution_q_index,
      audit.header.stop_execution_q_index);
  if (partition != streamRawDigest(
          audit.header.lane_partition_sha256) ||
      partition != streamRawDigest(
          rows.header.lane_partition_sha256) ||
      derivedPlan != expectedPlan) {
    throw std::runtime_error(
        "resident stream lane partition or plan differs");
  }

  const auto bytesBeforeFooter =
      streamPosition(input, "resident stream footer");
  seededReadExact(
      input, &audit.footer, "resident stream footer");
  tmajorDigestObject(&whole, audit.footer);
  const auto bodyStreamSha256 = bodyStream.finish();
  const auto& footer = audit.footer;
  if (input.peek() != std::ifstream::traits_type::eof() ||
      std::memcmp(
          footer.magic, rqs::kStreamFooterMagic, 8U) != 0 ||
      footer.version != rqs::kFormatVersion ||
      footer.reserved != 0U ||
      footer.lane_count != audit.lanes.size() ||
      footer.active_q_count != activeQCount ||
      footer.target_count != targetCount ||
      footer.target_row_reference_count != rowReferences ||
      footer.value_count != valueCount ||
      footer.sidecar_bytes != sidecarBytes ||
      footer.input_bytes_before_footer != bytesBeforeFooter ||
      !streamDigestEquals(
          laneChain, footer.lane_chain_sha256) ||
      !streamDigestEquals(
          globalTargetChain, footer.target_chain_sha256) ||
      !streamDigestEquals(
          bodyStreamSha256, footer.body_stream_sha256) ||
      !std::all_of(
          std::begin(footer.reserved_sha256),
          std::end(footer.reserved_sha256),
          [](unsigned char value) { return value == 0U; }) ||
      audit.header.active_q_count != activeQCount ||
      audit.header.target_count != targetCount ||
      audit.header.target_row_reference_count != rowReferences ||
      audit.header.value_count != valueCount ||
      audit.header.maximum_group_order != maximumGroupOrder) {
    throw std::runtime_error(
        "resident stream footer or global commitment differs");
  }
  audit.inputSha256 =
      sparkinterval::lowercase_hex(whole.finish());
  if (audit.inputSha256 != expectedInputSha256 ||
      std::filesystem::file_size(path) != size) {
    throw std::runtime_error(
        "resident stream sidecar artifact changed during replay");
  }
  return audit;
}

StreamMemoryPreflight streamMemoryPreflight(
    const AuthenticatedSeeds& seeds,
    const StreamRowAudit& rows,
    const StreamSidecarAudit& sidecars) {
  StreamMemoryPreflight result;
  streamCheckedMultiply(
      seeds.records.size(), sizeof(seeds.records[0]),
      &result.seedBytes,
      "resident stream seed allocation size overflow");
  streamCheckedMultiply(
      rows.header.row_count, rows.header.row_payload_bytes,
      &result.residentLatticeBytes,
      "resident stream lattice allocation size overflow");
  streamCheckedMultiply(
      sidecars.header.maximum_group_order,
      sizeof(lb::ResidueDescriptor),
      &result.maximumDescriptorBytes,
      "resident stream descriptor allocation size overflow");
  streamCheckedMultiply(
      sidecars.maximumBatchCount, sizeof(lb::FrameFactor),
      &result.maximumFactorBytes,
      "resident stream factor allocation size overflow");
  streamCheckedMultiply(
      sidecars.maximumBatchCount, sizeof(double),
      &result.maximumTailBytes,
      "resident stream tail allocation size overflow");
  streamCheckedMultiply(
      sidecars.maximumTargetValues, sizeof(ComplexInterval),
      &result.maximumOutputBytes,
      "resident stream output allocation size overflow");
  for (const auto value : {
           result.seedBytes,
           result.residentLatticeBytes,
           result.maximumDescriptorBytes,
           result.maximumFactorBytes,
           result.maximumTailBytes,
           result.maximumOutputBytes}) {
    fq::checkedAdd(
        &result.knownAllocationBytes, value,
        "resident stream device allocation total overflow");
  }
  std::size_t freeBytes = 0U;
  std::size_t totalBytes = 0U;
  CUDA_CHECK(cudaMemGetInfo(&freeBytes, &totalBytes));
  (void)totalBytes;
  result.freeBytes = freeBytes;
  if (result.knownAllocationBytes >
          std::numeric_limits<std::uint64_t>::max() -
              rqs::kDeviceMemorySafetyReserveBytes ||
      result.knownAllocationBytes +
              rqs::kDeviceMemorySafetyReserveBytes >
          result.freeBytes) {
    throw std::runtime_error(
        "resident stream device-memory preflight failed");
  }
  return result;
}

void uploadStreamRows(
    SeededPlan* plan, const std::filesystem::path& path,
    const std::string& expectedInputSha256,
    const StreamRowAudit& audit,
    const sparkinterval::Sha256Digest& expectedPlan) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error(
        "cannot reopen resident stream row artifact");
  }
  sparkinterval::detail::Sha256 whole;
  sparkinterval::detail::Sha256 rowStream;
  rqs::RowArtifactHeader header{};
  seededReadExact(
      input, &header, "resident stream execution row header");
  tmajorDigestObject(&whole, header);
  if (std::memcmp(&header, &audit.header, sizeof(header)) != 0) {
    throw std::runtime_error(
        "resident stream row header changed after preflight");
  }
  auto rowChain = rqs::initialRowChain(expectedPlan);
  plan->beginIncrementalResidentLatticeUpload(header.row_count);
  std::vector<ComplexInterval> payload;
  for (std::uint32_t index = 0U; index < header.row_count; ++index) {
    tms::RowHeader row{};
    seededReadExact(
        input, &row, "resident stream execution row record");
    tmajorDigestObject(&whole, row);
    tmajorDigestObject(&rowStream, row);
    tmajorReadVector(
        input, &payload, dl::kLatticeCellCount,
        "resident stream execution row payload",
        &whole, &rowStream);
    sparkinterval::detail::Sha256 payloadDigest;
    payloadDigest.update(
        payload.data(), payload.size() * sizeof(payload[0]));
    const auto payloadSha256 = payloadDigest.finish();
    if (std::memcmp(row.magic, tms::kRowMagic, 8U) != 0 ||
        row.version != tms::kFormatVersion ||
        row.reserved != 0U ||
        row.t_index != header.loaded_first_t_index + index ||
        row.payload_bytes != header.row_payload_bytes ||
        !streamDigestEquals(payloadSha256, row.payload_sha256) ||
        !std::all_of(
            payload.begin(), payload.end(), [](const auto& value) {
              return finiteOrdered(value);
            })) {
      throw std::runtime_error(
          "resident stream execution row changed after preflight");
    }
    rowChain = rqs::advanceRowChain(
        rowChain, row.t_index, payloadSha256);
    plan->uploadIncrementalResidentLattice(
        static_cast<std::size_t>(index) *
            dl::kLatticeCellCount,
        payload);
  }
  rqs::RowArtifactFooter footer{};
  seededReadExact(
      input, &footer, "resident stream execution row footer");
  tmajorDigestObject(&whole, footer);
  const auto rowStreamSha256 = rowStream.finish();
  const auto executionSha256 =
      sparkinterval::lowercase_hex(whole.finish());
  if (input.peek() != std::ifstream::traits_type::eof() ||
      std::memcmp(&footer, &audit.footer, sizeof(footer)) != 0 ||
      !streamDigestEquals(
          rowChain, footer.row_chain_sha256) ||
      !streamDigestEquals(
          rowStreamSha256, footer.row_stream_sha256) ||
      executionSha256 != expectedInputSha256) {
    throw std::runtime_error(
        "resident stream row artifact changed during CUDA upload");
  }
  plan->finishIncrementalResidentLatticeUpload();
}

void publishStreamSummary(
    const std::filesystem::path& summaryPath,
    const AuthenticatedSeeds& seeds,
    const FormulaicQOrder& schedule,
    const StreamRowAudit& rows,
    const StreamSidecarAudit& sidecars,
    const StreamMemoryPreflight& memory,
    const SeededPlan& plan,
    std::uint64_t descriptorReconstructions,
    std::uint64_t elapsed,
    const sparkinterval::Sha256Digest& outputSha256,
    std::uint64_t outputBytes) {
  const auto rowBytes = rows.header.input_size_bytes;
  const auto sidecarArtifactBytes =
      sidecars.header.input_size_bytes;
  std::uint64_t totalInputArtifactBytes = rowBytes;
  fq::checkedAdd(
      &totalInputArtifactBytes, sidecarArtifactBytes,
      "resident stream disk input total overflow");
  const auto hostRowBytes = rows.header.row_payload_bytes;
  const auto hostDescriptorBytes =
      memory.maximumDescriptorBytes;
  const auto hostSidecarBytes =
      memory.maximumFactorBytes + memory.maximumTailBytes;
  const auto hostOutputBytes = memory.maximumOutputBytes;
  std::uint64_t hostExecutionBytes = hostDescriptorBytes;
  fq::checkedAdd(
      &hostExecutionBytes, hostSidecarBytes,
      "resident stream host staging total overflow");
  fq::checkedAdd(
      &hostExecutionBytes, hostOutputBytes,
      "resident stream host staging total overflow");
  const auto hostPayloadBytes =
      std::max(hostRowBytes, hostExecutionBytes);

  const auto temporary = summaryPath.string() + ".tmp." +
      std::to_string(static_cast<long long>(getpid()));
  {
    std::ofstream summary(temporary, std::ios::trunc);
    if (!summary) {
      throw std::runtime_error(
          "cannot create resident stream summary");
    }
    summary
        << "{\"algorithm_id\":"
           "\"platt-dirichlet-resident-qmajor-stream-seeded-cuda-v1\""
        << ",\"candidate_report_sha256\":\""
        << sparkinterval::lowercase_hex(
               rqs::kCandidateReportSha256) << "\""
        << ",\"canonical_descriptor_input_bytes\":0"
        << ",\"classification\":"
           "\"source_shaped_resident_qmajor_stream_cuda_"
           "not_source_or_zero_closure\""
        << ",\"completed_l_zero_state_validated\":false"
        << ",\"coverage_mode\":" << rows.header.coverage_mode
        << ",\"cuda_event_create_count\":"
        << plan.eventCreateCount()
        << ",\"cuda_event_reuse_count\":"
        << plan.eventReuseCount()
        << ",\"descriptor_h2d_upload_count\":"
        << plan.descriptorUploadCount()
        << ",\"descriptor_reconstruction_count\":"
        << descriptorReconstructions
        << ",\"device_memory_formula_exact_for_explicit_allocations\":true"
        << ",\"device_memory_free_bytes_before_allocations\":"
        << memory.freeBytes
        << ",\"device_memory_known_allocation_bytes\":"
        << memory.knownAllocationBytes
        << ",\"device_memory_maximum_descriptor_bytes\":"
        << memory.maximumDescriptorBytes
        << ",\"device_memory_maximum_factor_bytes\":"
        << memory.maximumFactorBytes
        << ",\"device_memory_maximum_output_bytes\":"
        << memory.maximumOutputBytes
        << ",\"device_memory_maximum_tail_bytes\":"
        << memory.maximumTailBytes
        << ",\"device_memory_preflight_passed\":true"
        << ",\"device_memory_resident_lattice_bytes\":"
        << memory.residentLatticeBytes
        << ",\"device_memory_safety_reserve_bytes\":"
        << rqs::kDeviceMemorySafetyReserveBytes
        << ",\"device_memory_seed_bytes\":"
        << memory.seedBytes
        << ",\"disk_row_artifact_bytes\":" << rowBytes
        << ",\"disk_sidecar_artifact_bytes\":"
        << sidecarArtifactBytes
        << ",\"disk_total_input_artifact_bytes\":"
        << totalInputArtifactBytes
        << ",\"elapsed_kernel_nanoseconds\":" << elapsed
        << ",\"external_atom_discharged\":false"
        << ",\"full_phase_host_duplicate_required\":false"
        << ",\"full_source_pipe_or_socket_output_required\":true"
        << ",\"full_source_regular_file_output_refused\":true"
        << ",\"full_source_semantic_sign_reducer_integrated\":false"
        << ",\"h100_source_phase_completed\":false"
        << ",\"lane_chain_sha256\":\""
        << tmajorRawDigest(
               sidecars.footer.lane_chain_sha256) << "\""
        << ",\"lane_count\":" << sidecars.lanes.size()
        << ",\"lane_partition_sha256\":\""
        << tmajorRawDigest(
               sidecars.header.lane_partition_sha256) << "\""
        << ",\"lattice_device_allocation_count\":"
        << plan.latticeDeviceAllocationCount()
        << ",\"lattice_h2d_upload_bytes\":"
        << plan.latticeH2dUploadBytes()
        << ",\"lattice_h2d_upload_call_count\":"
        << plan.latticeH2dUploadCallCount()
        << ",\"loaded_first_t_index\":"
        << rows.header.loaded_first_t_index
        << ",\"loaded_t_index_stop_exclusive\":"
        << rows.header.loaded_t_index_stop_exclusive
        << ",\"maximum_host_descriptor_staging_bytes\":"
        << hostDescriptorBytes
        << ",\"maximum_host_output_staging_bytes\":"
        << hostOutputBytes
        << ",\"maximum_host_payload_staging_bytes\":"
        << hostPayloadBytes
        << ",\"maximum_host_row_staging_bytes\":"
        << hostRowBytes
        << ",\"maximum_host_sidecar_staging_bytes\":"
        << hostSidecarBytes
        << ",\"maximum_source_phase_projected_output_stream_bytes\":"
        << rqs::kMaximumProjectedPhaseOutputBytes
        << ",\"output_sha256\":\""
        << sparkinterval::lowercase_hex(outputSha256) << "\""
        << ",\"output_size_bytes\":" << outputBytes
        << ",\"output_transport\":"
           "\"stdout_backpressured_target_stream\""
        << ",\"phase_index\":" << rows.header.phase_index
        << ",\"phase_plan_sha256\":\""
        << tmajorRawDigest(rows.header.phase_plan_sha256) << "\""
        << ",\"production_run_completed\":false"
        << ",\"projected_output_stream_bytes\":" << outputBytes
        << ",\"recovery_seed_artifact_sha256\":\""
        << seeds.sha256 << "\""
        << ",\"row_artifact_sha256\":\""
        << rows.inputSha256 << "\""
        << ",\"row_artifact_size_bytes\":" << rowBytes
        << ",\"row_chain_sha256\":\""
        << tmajorRawDigest(rows.footer.row_chain_sha256) << "\""
        << ",\"row_count\":" << rows.header.row_count
        << ",\"schedule_classification\":"
        << rows.header.schedule_classification
        << ",\"schedule_execution_order_sha256\":\""
        << tmajorRawDigest(
               schedule.header.execution_order_sha256) << "\""
        << ",\"schedule_manifest_sha256\":\""
        << sparkinterval::lowercase_hex(
               schedule.fileSha256) << "\""
        << ",\"schema\":"
           "\"sparkinterval.tg.dirichlet_resident_qmajor_stream_cuda."
           "summary.v1\""
        << ",\"schema_version\":1"
        << ",\"seed_record_count\":" << seeds.records.size()
        << ",\"sidecar_artifact_sha256\":\""
        << sidecars.inputSha256 << "\""
        << ",\"sidecar_artifact_size_bytes\":"
        << sidecarArtifactBytes
        << ",\"sidecar_source_sha256\":\""
        << tmajorRawDigest(
               sidecars.header.sidecar_source_sha256) << "\""
        << ",\"source_contract_sha256\":\""
        << tmajorRawDigest(
               rows.header.source_contract_sha256) << "\""
        << ",\"source_h100_fit_claimed\":false"
        << ",\"source_output_materialization_feasible_claimed\":false"
        << ",\"source_scale_run\":false"
        << ",\"stdout_backpressure_supported\":true"
        << ",\"target_chain_sha256\":\""
        << tmajorRawDigest(
               sidecars.footer.target_chain_sha256) << "\""
        << ",\"target_count\":" << sidecars.header.target_count
        << ",\"target_row_reference_count\":"
        << sidecars.header.target_row_reference_count
        << ",\"transcendental_device_calls\":0"
        << ",\"trusted_execution_attested\":false"
        << ",\"value_count\":" << sidecars.header.value_count
        << ",\"zero_completeness_claimed\":false}\n";
    if (!summary) {
      throw std::runtime_error(
          "cannot write resident stream summary");
    }
  }
  std::error_code error;
  std::filesystem::rename(temporary, summaryPath, error);
  if (error) {
    std::filesystem::remove(temporary);
    throw std::runtime_error(
        "cannot publish resident stream summary: " +
        error.message());
  }
}

void executeStreamSidecars(
    SeededPlan* plan,
    const std::filesystem::path& path,
    const std::string& expectedInputSha256,
    const FormulaicQOrder& schedule,
    const StreamRowAudit& rows,
    const StreamSidecarAudit& audit,
    const StreamMemoryPreflight& memory,
    const AuthenticatedSeeds& seeds,
    const std::filesystem::path& summaryPath) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error(
        "cannot reopen resident stream sidecar artifact");
  }
  sparkinterval::detail::Sha256 whole;
  sparkinterval::detail::Sha256 bodyStream;
  sparkinterval::detail::Sha256 outputDigest;
  rqs::StreamHeader header{};
  seededReadExact(
      input, &header, "resident stream execution header");
  tmajorDigestObject(&whole, header);
  if (std::memcmp(&header, &audit.header, sizeof(header)) != 0) {
    throw std::runtime_error(
        "resident stream sidecar header changed after preflight");
  }

  auto laneChain = rqs::initialLaneChain(
      streamRawDigest(header.phase_plan_sha256),
      streamRawDigest(header.lane_partition_sha256));
  auto globalTargetChain = rqs::initialTargetChain(
      streamRawDigest(header.phase_plan_sha256));
  std::uint64_t descriptorReconstructions = 0U;
  std::uint64_t targetCount = 0U;
  std::uint64_t rowReferences = 0U;
  std::uint64_t valueCount = 0U;
  std::uint64_t sidecarBytes = 0U;
  std::uint64_t outputBytes = 0U;
  std::uint64_t elapsed = 0U;
  std::optional<std::uint32_t> residentQ;

  for (const auto& expectedLane : audit.lanes) {
    const auto laneStart =
        streamPosition(input, "resident execution lane start");
    rqs::LaneHeader lane{};
    seededReadExact(
        input, &lane, "resident stream execution lane header");
    tmajorDigestObject(&whole, lane);
    tmajorDigestObject(&bodyStream, lane);
    sparkinterval::detail::Sha256 laneStream;
    tmajorDigestObject(&laneStream, lane);
    if (std::memcmp(
            &lane, &expectedLane.header, sizeof(lane)) != 0) {
      throw std::runtime_error(
          "resident stream lane changed after preflight");
    }
    const auto lanePlan = rqs::lanePlanDigest(
        streamRawDigest(header.phase_plan_sha256), lane);
    auto laneTargetChain = rqs::initialLaneTargetChain(
        streamRawDigest(header.phase_plan_sha256),
        lane.lane_index);
    StreamTargetCursor cursor(schedule, rows.header, lane);
    std::uint64_t laneTargets = 0U;
    std::uint64_t laneRows = 0U;
    std::uint64_t laneValues = 0U;
    std::uint64_t laneSidecars = 0U;
    while (const auto target = cursor.next()) {
      rqs::TargetHeader targetHeader{};
      seededReadExact(
          input, &targetHeader,
          "resident stream execution target header");
      tmajorDigestObject(&whole, targetHeader);
      tmajorDigestObject(&bodyStream, targetHeader);
      tmajorDigestObject(&laneStream, targetHeader);
      streamValidateTarget(targetHeader, *target);

      SeededFrame frame;
      tmajorReadVector(
          input, &frame.factors, target->batch_count,
          "resident stream execution factors",
          &whole, &laneStream);
      bodyStream.update(
          frame.factors.data(),
          frame.factors.size() * sizeof(frame.factors[0]));
      tmajorReadVector(
          input, &frame.tailRadii, target->batch_count,
          "resident stream execution tails",
          &whole, &laneStream);
      bodyStream.update(
          frame.tailRadii.data(),
          frame.tailRadii.size() *
              sizeof(frame.tailRadii[0]));
      if (!std::all_of(
              frame.factors.begin(), frame.factors.end(),
              [](const auto& value) {
                return finiteOrdered(value.q_to_the_minus_s);
              }) ||
          !std::all_of(
              frame.tailRadii.begin(), frame.tailRadii.end(),
              [](double value) {
                return std::isfinite(value) && value >= 0.0;
              }) ||
          !streamDigestEquals(
              streamSidecarDigest(
                  header, *target, frame.factors,
                  frame.tailRadii),
              targetHeader.sidecar_sha256)) {
        throw std::runtime_error(
            "resident stream execution sidecar changed after preflight");
      }

      std::memcpy(frame.header.magic, kSeededInputMagic, 8U);
      frame.header.version = 2U;
      frame.header.q = target->q;
      frame.header.lattice_rows = dl::kLatticeRows;
      frame.header.taylor_degree = dl::kTaylorDegree;
      frame.header.component_count =
          targetHeader.component_count;
      frame.header.batch_count = target->batch_count;
      frame.header.m = rs::kSourceM;
      frame.header.group_order = targetHeader.group_order;
      frame.header.first_t_numerator =
          static_cast<std::int64_t>(
              static_cast<std::uint64_t>(
                  target->first_t_index) *
              lb::kSourceTStepNumerator);
      frame.header.t_denominator = lb::kSourceTDenominator;
      frame.header.t_step_numerator =
          lb::kSourceTStepNumerator;
      frame.header.lattice_cell_count =
          static_cast<std::uint64_t>(
              target->batch_count) *
          dl::kLatticeCellCount;
      frame.header.value_count = targetHeader.value_count;
      if (!residentQ || *residentQ != target->q) {
        frame.descriptors = canonicalDescriptors(target->q);
        residentQ = target->q;
        ++descriptorReconstructions;
      }
      const auto firstResidentRow =
          static_cast<std::size_t>(
              target->first_t_index -
              rows.header.loaded_first_t_index);
      auto [result, frameElapsed] =
          plan->executeResidentAt(
              frame, firstResidentRow, 1U);
      writeSeededOutput(
          std::cout, frame, result, &outputDigest);
      std::cout.flush();
      if (!std::cout) {
        throw std::runtime_error(
            "cannot flush resident stream TGDAFFI1 output");
      }

      laneTargetChain = rqs::advanceTargetChain(
          laneTargetChain, *target, true);
      globalTargetChain = rqs::advanceTargetChain(
          globalTargetChain, *target, false);
      ++laneTargets;
      fq::checkedAdd(
          &laneRows, target->batch_count,
          "resident execution lane row count overflow");
      fq::checkedAdd(
          &laneValues, targetHeader.value_count,
          "resident execution lane value count overflow");
      fq::checkedAdd(
          &laneSidecars,
          targetHeader.factor_bytes + targetHeader.tail_bytes,
          "resident execution lane sidecar count overflow");
      fq::checkedAdd(
          &outputBytes,
          sizeof(da::InputHeader) +
              targetHeader.value_count *
                  sizeof(ComplexInterval),
          "resident execution output byte count overflow");
      if (elapsed >
          std::numeric_limits<std::uint64_t>::max() -
              frameElapsed) {
        throw std::runtime_error(
            "resident execution elapsed time overflow");
      }
      elapsed += frameElapsed;
    }

    const auto bytesBeforeLaneFooter =
        streamPosition(
            input, "resident execution lane footer") -
        laneStart;
    const auto laneStreamSha256 = laneStream.finish();
    const auto nextLaneChain = rqs::advanceLaneChain(
        laneChain, lanePlan, laneTargetChain,
        laneStreamSha256);
    rqs::LaneFooter footer{};
    seededReadExact(
        input, &footer,
        "resident stream execution lane footer");
    tmajorDigestObject(&whole, footer);
    tmajorDigestObject(&bodyStream, footer);
    if (std::memcmp(
            &footer, &expectedLane.footer,
            sizeof(footer)) != 0 ||
        footer.target_count != laneTargets ||
        footer.target_row_reference_count != laneRows ||
        footer.value_count != laneValues ||
        footer.sidecar_bytes != laneSidecars ||
        footer.input_bytes_before_footer !=
            bytesBeforeLaneFooter ||
        !streamDigestEquals(
            laneTargetChain, footer.target_chain_sha256) ||
        !streamDigestEquals(
            laneStreamSha256, footer.lane_stream_sha256) ||
        !streamDigestEquals(
            nextLaneChain, footer.lane_chain_sha256)) {
      throw std::runtime_error(
          "resident stream lane changed during execution");
    }
    laneChain = nextLaneChain;
    fq::checkedAdd(
        &targetCount, laneTargets,
        "resident execution target count overflow");
    fq::checkedAdd(
        &rowReferences, laneRows,
        "resident execution row-reference count overflow");
    fq::checkedAdd(
        &valueCount, laneValues,
        "resident execution value count overflow");
    fq::checkedAdd(
        &sidecarBytes, laneSidecars,
        "resident execution sidecar count overflow");
  }

  rqs::StreamFooter footer{};
  seededReadExact(
      input, &footer, "resident stream execution footer");
  tmajorDigestObject(&whole, footer);
  const auto executionSha256 =
      sparkinterval::lowercase_hex(whole.finish());
  const auto bodyStreamSha256 = bodyStream.finish();
  const auto outputSha256 = outputDigest.finish();
  if (input.peek() != std::ifstream::traits_type::eof() ||
      std::memcmp(&footer, &audit.footer, sizeof(footer)) != 0 ||
      !streamDigestEquals(
          laneChain, footer.lane_chain_sha256) ||
      !streamDigestEquals(
          globalTargetChain, footer.target_chain_sha256) ||
      !streamDigestEquals(
          bodyStreamSha256, footer.body_stream_sha256) ||
      executionSha256 != expectedInputSha256 ||
      targetCount != header.target_count ||
      rowReferences != header.target_row_reference_count ||
      valueCount != header.value_count ||
      sidecarBytes != footer.sidecar_bytes ||
      plan->latticeUploadCount() != 1U ||
      plan->latticeDeviceAllocationCount() != 1U ||
      plan->latticeH2dUploadCallCount() !=
          rows.header.row_count ||
      plan->latticeH2dUploadBytes() !=
          rows.header.row_count *
              rows.header.row_payload_bytes ||
      plan->descriptorUploadCount() !=
          header.active_q_count ||
      descriptorReconstructions !=
          header.active_q_count ||
      plan->eventCreateCount() != 2U ||
      plan->eventReuseCount() != header.target_count) {
    throw std::runtime_error(
        "resident stream execution totals differ after CUDA");
  }
  publishStreamSummary(
      summaryPath, seeds, schedule, rows, audit, memory, *plan,
      descriptorReconstructions, elapsed, outputSha256,
      outputBytes);
}

void runResidentQMajorStream(
    const AuthenticatedSeeds& seeds,
    const std::filesystem::path& schedulePath,
    const sparkinterval::Sha256Digest& expectedPlan,
    const std::filesystem::path& rowPath,
    const std::string& expectedRowSha256,
    const std::filesystem::path& sidecarPath,
    const std::string& expectedSidecarSha256,
    const std::filesystem::path& summaryPath,
    std::uint32_t device,
    bool allowPrefixKat) {
  if (std::filesystem::exists(summaryPath)) {
    throw std::runtime_error(
        "refusing to replace resident stream summary");
  }
  const auto schedule =
      loadFormulaicQOrder(schedulePath, true);
  if (schedule.header.classification ==
      rqs::kFullSourceSchedule) {
    struct stat stdoutStatus {};
    if (fstat(STDOUT_FILENO, &stdoutStatus) != 0 ||
        (!S_ISFIFO(stdoutStatus.st_mode) &&
         !S_ISSOCK(stdoutStatus.st_mode))) {
      throw std::runtime_error(
          "full-source resident stream requires a pipe/socket "
          "back-pressured semantic/sign consumer");
    }
  }
  const auto rows = auditStreamRows(
      rowPath, expectedRowSha256, schedule, seeds, expectedPlan);
  const auto sidecars = auditStreamSidecars(
      sidecarPath, expectedSidecarSha256, schedule, seeds,
      expectedPlan, rows, seededParseDigest(expectedRowSha256));
  seededPrefixKatTestBarrier(
      allowPrefixKat,
      "SPARKINTERVAL_TG_PREFIX_KAT_AFTER_RESIDENT_STREAM_PREFLIGHT_BARRIER",
      "resident stream preflight");
  const std::uint64_t requiredX =
      static_cast<std::uint64_t>(rs::kSourceM) *
          sidecars.maximumQ +
      sidecars.maximumQ - 1U;
  if (seeds.header.x_stop < requiredX) {
    throw std::runtime_error(
        "seed artifact does not cover resident stream q targets");
  }
  selectDevice(device);
  const auto memory =
      streamMemoryPreflight(seeds, rows, sidecars);
  SeededPlan plan(seeds);
  uploadStreamRows(
      &plan, rowPath, expectedRowSha256, rows, expectedPlan);
  std::signal(SIGPIPE, SIG_IGN);
  executeStreamSidecars(
      &plan, sidecarPath, expectedSidecarSha256, schedule,
      rows, sidecars, memory, seeds, summaryPath);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const bool allowPrefixKat =
        argc == 12 &&
        std::string_view(argv[11]) == "--allow-prefix-kat";
    if (argc != 11 && !allowPrefixKat) {
      throw std::runtime_error(
          "usage: runner SEEDS SEED_SHA TGDQORD1 PLAN_SHA "
          "ROWS ROW_SHA SIDECARS SIDECAR_SHA SUMMARY DEVICE "
          "[--allow-prefix-kat]");
    }
    const auto expectedSeed = seededParseDigest(argv[2]);
    const auto expectedPlan = seededParseDigest(argv[4]);
    const auto expectedRow = seededParseDigest(argv[6]);
    const auto expectedSidecar = seededParseDigest(argv[8]);
    const auto device = parseUnsigned(argv[10], "device");
    if (device > std::numeric_limits<std::uint32_t>::max()) {
      throw std::runtime_error(
          "resident stream device is invalid");
    }
    const auto seeds = loadAuthenticatedSeeds(
        argv[1], expectedSeed, allowPrefixKat);
    runResidentQMajorStream(
        seeds, argv[3], expectedPlan, argv[5],
        sparkinterval::lowercase_hex(expectedRow), argv[7],
        sparkinterval::lowercase_hex(expectedSidecar), argv[9],
        static_cast<std::uint32_t>(device), allowPrefixKat);
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(
        stderr, "tg_dirichlet_resident_qmajor_stream: %s\n",
        error.what());
    return 1;
  }
}

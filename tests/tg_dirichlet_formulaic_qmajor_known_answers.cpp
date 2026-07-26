// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_dirichlet_formulaic_qmajor.hpp"

#include <array>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace fq = sparkinterval::tg::dirichlet_formulaic_qmajor;

namespace {

sparkinterval::Sha256Digest parseDigest(std::string_view text) {
  if (text.size() != 64U) throw std::runtime_error("bad test digest");
  sparkinterval::Sha256Digest result{};
  auto digit = [](char value) -> unsigned int {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10U;
    throw std::runtime_error("bad test digest digit");
  };
  for (std::size_t index = 0; index < result.size(); ++index) {
    result[index] = static_cast<unsigned char>(
        (digit(text[2U * index]) << 4U) | digit(text[2U * index + 1U]));
  }
  return result;
}

template <typename Function>
bool rejects(Function function, const char* label) {
  try {
    function();
  } catch (const std::runtime_error&) {
    return true;
  }
  std::cerr << label << ": attack was accepted\n";
  return false;
}

}  // namespace

int main() {
  bool passed = true;
  // Exact TGDQORD1 order for the bounded Python KAT source roster
  // q=(10001,10003,10004,10005).
  const std::array<fq::ScheduleRecord, 4> schedule = {
      fq::ScheduleRecord{10005U, 31U}, fq::ScheduleRecord{10004U, 16U},
      fq::ScheduleRecord{10001U, 5U}, fq::ScheduleRecord{10003U, 19U}};
  const std::array<fq::LaneRange, 3> lanes = {
      fq::LaneRange{0U, 0U, 8U}, fq::LaneRange{1U, 8U, 16U},
      fq::LaneRange{2U, 16U, 31U}};
  // Cross-language fixed answer from Python plan_identity() over the exact
  // manifest, lanes, q slice, and maximum batch count below.  The cursor
  // chain must be seeded with this digest, never with the raw manifest hash.
  const auto plan = parseDigest(
      "03b5f39b9dec5e9518c1283d9d46208f"
      "3a7464b16db084d96ae4e8c9c72854b1");
  const auto derivedPlan = fq::planDigest(
      parseDigest(
          "1d53d03c2d874b1754e8148278a5c494"
          "b8ae87e85cbcb31fcae31628aade1171"),
      fq::kBoundedScheduleClassification,
      parseDigest(
          "9642949e0580d1c718a0ad82586bf73b3"
          "1f0816c44d39038828961829d473e3b"),
      lanes, 0U, schedule.size(), 8U);
  passed &= derivedPlan == plan;
  const auto accounting =
      fq::compressedAccounting(schedule, lanes, 0U, schedule.size(), 8U);
  passed &= accounting.q_count == 4U && accounting.target_count == 10U &&
            accounting.row_reference_count == 71U;
  passed &= accounting.per_lane_target_counts ==
            std::vector<std::uint64_t>({4U, 3U, 3U});
  passed &= accounting.per_lane_row_reference_counts ==
            std::vector<std::uint64_t>({29U, 24U, 18U});

  fq::Cursor cursor(schedule, lanes, plan, 0U, schedule.size(), 8U);
  const auto first = cursor.expectedTarget();
  passed &= first.has_value() &&
            *first == fq::Target{0U, 10005U, 0U, 0U, 8U, 8U};
  if (first.has_value()) {
    passed &=
        sparkinterval::lowercase_hex(fq::targetDigest(*first)) ==
        "8da9c70eb585139d65f00bee68846b1b"
        "6db8a7422c17e772c5ae3439eab33813";
    auto substituted = *first;
    --substituted.t_index_stop_exclusive;
    --substituted.batch_count;
    passed &= rejects([&] { cursor.accept(substituted); },
                      "substituted first target");
  }
  passed &= rejects([&] { (void)cursor.finish(); }, "truncated cursor");

  std::uint64_t expanded_rows = 0U;
  while (const auto target = cursor.expectedTarget()) {
    passed &= target->batch_count > 0U && target->batch_count <= 8U;
    expanded_rows += target->batch_count;
    cursor.accept(*target);
  }
  const auto session = cursor.finish();
  passed &= expanded_rows == 71U;
  // Fixed answer from Python FormulaicQMajorCursor.finish().
  passed &=
      sparkinterval::lowercase_hex(session.target_chain_sha256) ==
      "a53afecd88edf8d5502427d53945d411"
      "92de64a7d55c07cbdbf70311b7431e2b";
  passed &= rejects([&] { (void)cursor.expectedTarget(); },
                    "post-finalization target");
  passed &= rejects([&] { (void)cursor.finish(); },
                    "duplicate finalization");

  const std::array<fq::LaneRange, 2> gap = {
      fq::LaneRange{0U, 0U, 8U}, fq::LaneRange{1U, 9U, 31U}};
  passed &= rejects(
      [&] {
        (void)fq::compressedAccounting(schedule, gap, 0U, schedule.size(), 8U);
      },
      "lane gap");
  const std::array<fq::LaneRange, 2> misaligned = {
      fq::LaneRange{0U, 0U, 7U}, fq::LaneRange{1U, 7U, 31U}};
  passed &= rejects(
      [&] {
        (void)fq::compressedAccounting(schedule, misaligned, 0U,
                                       schedule.size(), 8U);
      },
      "misaligned lane");
  passed &= rejects(
      [&] {
        (void)fq::compressedAccounting(schedule, lanes, 1U, 1U, 8U);
      },
      "empty q slice");

  return passed ? 0 : 1;
}

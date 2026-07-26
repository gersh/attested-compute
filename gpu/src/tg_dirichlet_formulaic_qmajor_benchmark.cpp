// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Source-geometry microbenchmark for the reusable formulaic q-major cursor.
// This parser checks only enough of TGDQORD1 to size the cursor benchmark; it
// is not the production schedule validator and emits no evidence claim.

#include "sparkinterval/tg_dirichlet_formulaic_qmajor.hpp"

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace fq = sparkinterval::tg::dirichlet_formulaic_qmajor;

namespace {

constexpr std::size_t kManifestHeaderBytes = 112U;
constexpr std::size_t kManifestRecordBytes = 8U;
constexpr std::uint64_t kSourceQCount = 292500U;
constexpr std::uint64_t kSourceRows = 3637613167U;
constexpr std::uint64_t kSourceTargets = 56981100U;

std::uint32_t readLe32(const unsigned char* raw) {
  return static_cast<std::uint32_t>(raw[0]) |
         (static_cast<std::uint32_t>(raw[1]) << 8U) |
         (static_cast<std::uint32_t>(raw[2]) << 16U) |
         (static_cast<std::uint32_t>(raw[3]) << 24U);
}

std::uint64_t readLe64(const unsigned char* raw) {
  std::uint64_t result = 0U;
  for (unsigned int index = 0; index < 8U; ++index) {
    result |= static_cast<std::uint64_t>(raw[index]) << (8U * index);
  }
  return result;
}

std::vector<unsigned char> readManifest(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open benchmark manifest");
  const auto end = input.tellg();
  if (end < 0 || static_cast<std::uint64_t>(end) >
                     kManifestHeaderBytes +
                         kSourceQCount * kManifestRecordBytes) {
    throw std::runtime_error("benchmark manifest size is outside its bound");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(end));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(raw.data()),
             static_cast<std::streamsize>(raw.size()));
  if (!input) throw std::runtime_error("cannot read benchmark manifest");
  return raw;
}

std::vector<fq::ScheduleRecord> parseBenchmarkManifest(
    const std::vector<unsigned char>& raw) {
  constexpr std::array<unsigned char, 8> magic = {
      'T', 'G', 'D', 'Q', 'O', 'R', 'D', '1'};
  if (raw.size() < kManifestHeaderBytes ||
      !std::equal(magic.begin(), magic.end(), raw.begin()) ||
      readLe32(raw.data() + 8U) != 1U ||
      readLe32(raw.data() + 12U) != 1U ||
      readLe32(raw.data() + 28U) != kManifestRecordBytes) {
    throw std::runtime_error(
        "benchmark requires a full-source TGDQORD1 manifest");
  }
  const auto q_count = readLe64(raw.data() + 32U);
  const auto row_count = readLe64(raw.data() + 40U);
  if (q_count != kSourceQCount || row_count != kSourceRows ||
      raw.size() !=
          kManifestHeaderBytes + q_count * kManifestRecordBytes) {
    throw std::runtime_error(
        "benchmark TGDQORD1 source geometry differs");
  }
  std::vector<fq::ScheduleRecord> result;
  result.reserve(static_cast<std::size_t>(q_count));
  std::uint64_t observed_rows = 0U;
  for (std::size_t offset = kManifestHeaderBytes; offset < raw.size();
       offset += kManifestRecordBytes) {
    const auto q = readLe32(raw.data() + offset);
    const auto rows = readLe32(raw.data() + offset + 4U);
    if (q < 10001U || q > 400000U || rows == 0U || rows > 127988U) {
      throw std::runtime_error(
          "benchmark TGDQORD1 record geometry differs");
    }
    fq::checkedAdd(&observed_rows, rows,
                   "benchmark row count overflow");
    result.push_back({q, rows});
  }
  if (observed_rows != kSourceRows) {
    throw std::runtime_error(
        "benchmark TGDQORD1 row total differs");
  }
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 2) {
      throw std::runtime_error(
          "usage: benchmark TGDQORD1_SOURCE_MANIFEST");
    }
    const auto raw = readManifest(argv[1]);
    const auto schedule = parseBenchmarkManifest(raw);
    constexpr std::array<fq::LaneRange, 8> lanes = {
        fq::LaneRange{0U, 0U, 896U},
        fq::LaneRange{1U, 896U, 1664U},
        fq::LaneRange{2U, 1664U, 2560U},
        fq::LaneRange{3U, 2560U, 3328U},
        fq::LaneRange{4U, 3328U, 4352U},
        fq::LaneRange{5U, 4352U, 5888U},
        fq::LaneRange{6U, 5888U, 10240U},
        fq::LaneRange{7U, 10240U, 127988U}};
    const auto plan_sha = sparkinterval::sha256(raw.data(), raw.size());
    const auto accounting = fq::compressedAccounting(
        schedule, lanes, 0U, schedule.size());
    if (accounting.q_count != kSourceQCount ||
        accounting.row_reference_count != kSourceRows ||
        accounting.target_count != kSourceTargets) {
      throw std::runtime_error(
          "compiled compressed source accounting differs");
    }
    const auto started = std::chrono::steady_clock::now();
    fq::Cursor cursor(schedule, lanes, plan_sha, 0U, schedule.size());
    std::uint64_t targets = 0U;
    while (const auto target = cursor.expectedTarget()) {
      cursor.accept(*target);
      ++targets;
    }
    const auto session = cursor.finish();
    const auto elapsed =
        std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started)
            .count();
    if (targets != kSourceTargets ||
        session.accounting.target_count != kSourceTargets) {
      throw std::runtime_error(
          "compiled expanded source accounting differs");
    }
    std::cout << std::setprecision(17)
              << "{\"classification\":"
                 "\"source-geometry-cursor-microbenchmark-not-evidence\""
              << ",\"elapsed_seconds\":" << elapsed
              << ",\"external_atom_discharged\":false"
              << ",\"q_count\":" << kSourceQCount
              << ",\"row_reference_count\":" << kSourceRows
              << ",\"target_chain_sha256\":\""
              << sparkinterval::lowercase_hex(
                     session.target_chain_sha256)
              << "\""
              << ",\"target_count\":" << targets
              << ",\"targets_per_second\":" << targets / elapsed
              << ",\"trusted_execution_attested\":false}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "tg_dirichlet_formulaic_qmajor_benchmark: "
              << error.what() << '\n';
    return 1;
  }
}

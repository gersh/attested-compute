// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "tg_r2star_chunk.h"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

[[noreturn]] void fail(const std::string& message) {
  std::cerr << message << '\n';
  std::exit(1);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) {
    fail(std::string(operation) + " failed: " + cudaGetErrorString(status));
  }
}

bool same_summary(const TgR2StarChunkSummary& left,
                  const TgR2StarChunkSummary& right) {
  return left.outgoing_lower == right.outgoing_lower &&
         left.outgoing_upper == right.outgoing_upper &&
         left.minimum_squared_slack.low ==
             right.minimum_squared_slack.low &&
         left.minimum_squared_slack.high ==
             right.minimum_squared_slack.high &&
         left.minimum_slack_index == right.minimum_slack_index &&
         left.first_bad_index == right.first_bad_index &&
         left.status == right.status && left.reserved == right.reserved;
}

TgR2StarChunkSummary run_case(
    std::uint64_t lower, const std::vector<TgR2StarDirectedRow>& rows,
    std::int64_t incoming_lower, std::int64_t incoming_upper) {
  const std::size_t count = rows.size();
  const std::size_t block_count =
      1 + (count - 1) / kTgR2StarTransitionBlockRows;
  TgR2StarDirectedRow* device_rows = nullptr;
  std::int64_t* prefix_lower = nullptr;
  std::int64_t* prefix_upper = nullptr;
  TgR2StarPrefixBlock* prefix_blocks = nullptr;
  TgR2StarEnvelopeRow* envelope_rows = nullptr;
  TgR2StarEnvelopeBlock* envelope_blocks = nullptr;
  TgR2StarChunkSummary* parallel_summary = nullptr;
  TgR2StarChunkSummary* serial_summary = nullptr;
  check_cuda("cudaMalloc(rows)", cudaMalloc(
      reinterpret_cast<void**>(&device_rows), count * sizeof(*device_rows)));
  check_cuda("cudaMalloc(prefix_lower)", cudaMalloc(
      reinterpret_cast<void**>(&prefix_lower), count * sizeof(*prefix_lower)));
  check_cuda("cudaMalloc(prefix_upper)", cudaMalloc(
      reinterpret_cast<void**>(&prefix_upper), count * sizeof(*prefix_upper)));
  check_cuda("cudaMalloc(prefix_blocks)", cudaMalloc(
      reinterpret_cast<void**>(&prefix_blocks),
      block_count * sizeof(*prefix_blocks)));
  check_cuda("cudaMalloc(envelope_rows)", cudaMalloc(
      reinterpret_cast<void**>(&envelope_rows), count * sizeof(*envelope_rows)));
  check_cuda("cudaMalloc(envelope_blocks)", cudaMalloc(
      reinterpret_cast<void**>(&envelope_blocks),
      block_count * sizeof(*envelope_blocks)));
  check_cuda("cudaMalloc(parallel_summary)", cudaMalloc(
      reinterpret_cast<void**>(&parallel_summary), sizeof(*parallel_summary)));
  check_cuda("cudaMalloc(serial_summary)", cudaMalloc(
      reinterpret_cast<void**>(&serial_summary), sizeof(*serial_summary)));
  check_cuda("cudaMemcpy(rows)", cudaMemcpy(
      device_rows, rows.data(), count * sizeof(*device_rows),
      cudaMemcpyHostToDevice));

  check_cuda("parallel transition", launch_tg_r2star_parallel_chunk_transition(
      lower, count, device_rows, incoming_lower, incoming_upper,
      prefix_lower, prefix_upper, prefix_blocks, envelope_rows,
      envelope_blocks, parallel_summary));
  check_cuda("serial transition", launch_tg_r2star_chunk_transition(
      lower, count, device_rows, incoming_lower, incoming_upper,
      serial_summary));
  check_cuda("cudaDeviceSynchronize", cudaDeviceSynchronize());

  TgR2StarChunkSummary parallel{};
  TgR2StarChunkSummary serial{};
  check_cuda("cudaMemcpy(parallel_summary)", cudaMemcpy(
      &parallel, parallel_summary, sizeof(parallel), cudaMemcpyDeviceToHost));
  check_cuda("cudaMemcpy(serial_summary)", cudaMemcpy(
      &serial, serial_summary, sizeof(serial), cudaMemcpyDeviceToHost));
  check_cuda("cudaFree(rows)", cudaFree(device_rows));
  check_cuda("cudaFree(prefix_lower)", cudaFree(prefix_lower));
  check_cuda("cudaFree(prefix_upper)", cudaFree(prefix_upper));
  check_cuda("cudaFree(prefix_blocks)", cudaFree(prefix_blocks));
  check_cuda("cudaFree(envelope_rows)", cudaFree(envelope_rows));
  check_cuda("cudaFree(envelope_blocks)", cudaFree(envelope_blocks));
  check_cuda("cudaFree(parallel_summary)", cudaFree(parallel_summary));
  check_cuda("cudaFree(serial_summary)", cudaFree(serial_summary));
  if (!same_summary(parallel, serial)) {
    fail("blocked transition disagrees with serial known-answer reference");
  }
  return parallel;
}

}  // namespace

int main() {
  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count < 1) fail("R2Star transition test requires a CUDA device");
  check_cuda("cudaSetDevice", cudaSetDevice(0));

  // Every endpoint has exactly zero slack.  Strict ordered comparisons in
  // both reduction levels must retain the first witness, n=3, even though the
  // equal minima span three 1,024-row transition blocks.
  std::vector<TgR2StarDirectedRow> ties(2'050);
  const TgR2StarChunkSummary tie_summary = run_case(1, ties, 0, 0);
  if (tie_summary.status != 0 || tie_summary.minimum_squared_slack.low != 0 ||
      tie_summary.minimum_squared_slack.high != 0 ||
      tie_summary.minimum_slack_index != 3 ||
      tie_summary.outgoing_lower != 0 || tie_summary.outgoing_upper != 0) {
    fail("equal-slack tie did not retain the earliest witness n=3");
  }

  // Alternate across zero while carrying a nonzero signed block offset.  The
  // odd row count also pins the exact final state after crossing two internal
  // block boundaries.
  std::vector<TgR2StarDirectedRow> signed_rows(2'051);
  for (std::size_t index = 0; index < signed_rows.size(); ++index) {
    TgR2StarDirectedRow& row = signed_rows[index];
    row.log_lower = 1'000'000;
    row.log_upper = 1'000'000;
    row.delta_lower = index % 2 == 0 ? 1'000'000 : -999'999;
    row.delta_upper = row.delta_lower;
  }
  const TgR2StarChunkSummary signed_summary =
      run_case(3, signed_rows, -500'000, -400'000);
  if (signed_summary.status != 0 ||
      signed_summary.outgoing_lower != 501'025 ||
      signed_summary.outgoing_upper != 601'025) {
    fail("signed cross-block carry produced the wrong outgoing state");
  }

  std::cout << "blocked R2Star transition matches serial reference for signed "
               "carry and earliest equal-slack tie breaking\n";
  return 0;
}

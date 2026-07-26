// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_platt_dd_accumulator.hpp"

#include <cuda_runtime.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace pda = sparkinterval::tg::platt_dd_accumulator;
namespace pw = sparkinterval::tg::platt_windowed;

namespace {

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +               \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

__global__ void count_invalid(const pw::ComplexDisk106* values,
                              std::uint64_t count,
                              unsigned long long* invalid) {
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const pw::ComplexDisk106 value = values[index];
    if (!isfinite(value.real.hi) || !isfinite(value.real.lo) ||
        !isfinite(value.imaginary.hi) ||
        !isfinite(value.imaginary.lo) || !isfinite(value.radius) ||
        value.radius < 0.0) {
      atomicAdd(invalid, 1ULL);
    }
  }
}

__device__ bool exact_zero(double value) {
  return __double_as_longlong(value) == 0LL;
}

__global__ void count_nonzero_inactive(
    const pw::ComplexDisk106* values, const std::uint32_t* offsets,
    unsigned long long* nonzero_inactive,
    unsigned long long* audited_inactive) {
  for (std::uint32_t bucket =
           blockIdx.x * blockDim.x + threadIdx.x;
       bucket < pw::kBucketCount;
       bucket += blockDim.x * gridDim.x) {
    if (offsets[bucket] != offsets[bucket + 1U]) continue;
    atomicAdd(audited_inactive,
              static_cast<unsigned long long>(pw::kTaylorTerms));
    for (std::uint32_t stage = 0U; stage < pw::kTaylorTerms; ++stage) {
      const pw::ComplexDisk106 value =
          values[static_cast<std::uint64_t>(stage) * pw::kBucketCount +
                 bucket];
      if (!exact_zero(value.real.hi) || !exact_zero(value.real.lo) ||
          !exact_zero(value.imaginary.hi) ||
          !exact_zero(value.imaginary.lo) ||
          !exact_zero(value.radius)) {
        atomicAdd(nonzero_inactive, 1ULL);
      }
    }
  }
}

__device__ constexpr unsigned long long kPoisonNaNBits =
    0x7ff80000000000a5ULL;
__device__ constexpr unsigned long long kPoisonRadiusBits =
    0x8000000000000001ULL;

__global__ void poison_active_cells(
    pw::ComplexDisk106* values, const std::uint32_t* active,
    std::uint32_t active_count) {
  const std::uint64_t count =
      static_cast<std::uint64_t>(active_count) * pw::kTaylorTerms;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t active_index =
        static_cast<std::uint32_t>(flat % active_count);
    const std::uint32_t stage =
        static_cast<std::uint32_t>(flat / active_count);
    const std::uint32_t bucket = active[active_index];
    const double poison =
        __longlong_as_double(static_cast<long long>(kPoisonNaNBits));
    const double poison_radius =
        __longlong_as_double(static_cast<long long>(kPoisonRadiusBits));
    values[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket] =
        {{poison, poison}, {poison, poison}, poison_radius};
  }
}

__global__ void count_poisoned_active_cells(
    const pw::ComplexDisk106* values, const std::uint32_t* active,
    std::uint32_t active_count, unsigned long long* poisoned) {
  const std::uint64_t count =
      static_cast<std::uint64_t>(active_count) * pw::kTaylorTerms;
  for (std::uint64_t flat =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       flat < count;
       flat += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    const std::uint32_t active_index =
        static_cast<std::uint32_t>(flat % active_count);
    const std::uint32_t stage =
        static_cast<std::uint32_t>(flat / active_count);
    const std::uint32_t bucket = active[active_index];
    const pw::ComplexDisk106 value =
        values[static_cast<std::uint64_t>(stage) * pw::kBucketCount + bucket];
    if (static_cast<unsigned long long>(
            __double_as_longlong(value.real.hi)) == kPoisonNaNBits ||
        static_cast<unsigned long long>(
            __double_as_longlong(value.real.lo)) == kPoisonNaNBits ||
        static_cast<unsigned long long>(
            __double_as_longlong(value.imaginary.hi)) == kPoisonNaNBits ||
        static_cast<unsigned long long>(
            __double_as_longlong(value.imaginary.lo)) == kPoisonNaNBits ||
        static_cast<unsigned long long>(
            __double_as_longlong(value.radius)) == kPoisonRadiusBits) {
      atomicAdd(poisoned, 1ULL);
    }
  }
}

std::uint32_t audit_active_roster(pda::Workspace* workspace) {
  std::vector<std::uint32_t> offsets(pw::kBucketCount + 1U);
  const std::uint32_t active_count =
      pda::active_bucket_count_qualification(workspace);
  if (active_count == 0U || active_count > pw::kBucketCount) {
    throw std::runtime_error("active bucket count is outside source geometry");
  }
  std::vector<std::uint32_t> active(active_count);
  CUDA_CHECK(cudaMemcpy(
      offsets.data(), pda::device_bucket_offsets_qualification(workspace),
      offsets.size() * sizeof(offsets[0]), cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(
      active.data(), pda::device_active_buckets_qualification(workspace),
      active.size() * sizeof(active[0]), cudaMemcpyDeviceToHost));
  if (offsets.front() != 0U || offsets.back() != pw::kSourceTerms) {
    throw std::runtime_error("bucket offsets do not cover every source term");
  }
  std::size_t cursor = 0U;
  for (std::uint32_t bucket = 0U; bucket < pw::kBucketCount; ++bucket) {
    if (offsets[bucket] > offsets[bucket + 1U] ||
        offsets[bucket + 1U] > pw::kSourceTerms) {
      throw std::runtime_error("bucket offsets are not bounded and monotone");
    }
    if (offsets[bucket] == offsets[bucket + 1U]) continue;
    if (cursor >= active.size() || active[cursor] != bucket) {
      throw std::runtime_error(
          "active roster differs from the nonempty-offset roster");
    }
    ++cursor;
  }
  if (cursor != active.size()) {
    throw std::runtime_error(
        "active roster has a duplicate, unsorted, or trailing bucket");
  }
  return active_count;
}

void poison_active_output(
    pda::Workspace* workspace, const pda::SourceWindowView& view,
    std::uint32_t active_count, cudaStream_t stream) {
  const std::uint64_t count =
      static_cast<std::uint64_t>(active_count) * pw::kTaylorTerms;
  const std::uint32_t blocks =
      static_cast<std::uint32_t>((count + 255U) / 256U);
  poison_active_cells<<<blocks, 256U, 0U, stream>>>(
      const_cast<pw::ComplexDisk106*>(view.device_skn_rows),
      pda::device_active_buckets_qualification(workspace), active_count);
  CUDA_CHECK(cudaGetLastError());
}

void audit_active_overwritten(
    pda::Workspace* workspace, const pda::SourceWindowView& view,
    std::uint32_t active_count, unsigned long long* device_poisoned,
    cudaStream_t stream) {
  CUDA_CHECK(cudaMemsetAsync(device_poisoned, 0, sizeof(*device_poisoned),
                             stream));
  const std::uint64_t count =
      static_cast<std::uint64_t>(active_count) * pw::kTaylorTerms;
  const std::uint32_t blocks =
      static_cast<std::uint32_t>((count + 255U) / 256U);
  count_poisoned_active_cells<<<blocks, 256U, 0U, stream>>>(
      view.device_skn_rows,
      pda::device_active_buckets_qualification(workspace), active_count,
      device_poisoned);
  CUDA_CHECK(cudaGetLastError());
  unsigned long long host_poisoned = 0U;
  CUDA_CHECK(cudaMemcpyAsync(&host_poisoned, device_poisoned,
                             sizeof(host_poisoned), cudaMemcpyDeviceToHost,
                             stream));
  CUDA_CHECK(cudaStreamSynchronize(stream));
  if (host_poisoned != 0U) {
    throw std::runtime_error(
        "an active accumulator stage/cell was not overwritten");
  }
}

void audit_inactive_exact_zero(
    pda::Workspace* workspace, const pda::SourceWindowView& view,
    unsigned long long* device_nonzero,
    unsigned long long* device_audited, cudaStream_t stream) {
  CUDA_CHECK(cudaMemsetAsync(device_nonzero, 0, sizeof(*device_nonzero),
                             stream));
  CUDA_CHECK(cudaMemsetAsync(device_audited, 0, sizeof(*device_audited),
                             stream));
  count_nonzero_inactive<<<128U, 256U, 0U, stream>>>(
      view.device_skn_rows,
      pda::device_bucket_offsets_qualification(workspace),
      device_nonzero, device_audited);
  CUDA_CHECK(cudaGetLastError());
  unsigned long long host_nonzero = 0U;
  unsigned long long host_audited = 0U;
  CUDA_CHECK(cudaMemcpyAsync(&host_nonzero, device_nonzero,
                             sizeof(host_nonzero), cudaMemcpyDeviceToHost,
                             stream));
  CUDA_CHECK(cudaMemcpyAsync(&host_audited, device_audited,
                             sizeof(host_audited), cudaMemcpyDeviceToHost,
                             stream));
  CUDA_CHECK(cudaStreamSynchronize(stream));
  constexpr std::uint64_t kExpectedActiveBuckets = 6'674U;
  constexpr std::uint64_t kExpectedInactiveCells =
      (pw::kBucketCount - kExpectedActiveBuckets) * pw::kTaylorTerms;
  if (host_nonzero != 0U || host_audited != kExpectedInactiveCells) {
    throw std::runtime_error(
        "inactive accumulator exact-zero audit differs");
  }
}

int run() {
  constexpr std::uint64_t kFirstBlock = 0U;
  constexpr std::uint64_t kBlocks = 2U;
  const auto initialization_start = std::chrono::steady_clock::now();
  pda::Workspace* workspace =
      pda::create_source_workspace(kFirstBlock, kBlocks, 256U);
  const double initialization_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - initialization_start).count();
  unsigned long long* invalid = nullptr;
  unsigned long long* nonzero_inactive = nullptr;
  unsigned long long* audited_inactive = nullptr;
  unsigned long long* poisoned_active = nullptr;
  pda::Workspace* qualification_workspace = nullptr;
  cudaStream_t stream = nullptr;
  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  try {
    CUDA_CHECK(cudaMalloc(&invalid, sizeof(*invalid)));
    CUDA_CHECK(cudaMalloc(&nonzero_inactive, sizeof(*nonzero_inactive)));
    CUDA_CHECK(cudaMalloc(&audited_inactive, sizeof(*audited_inactive)));
    CUDA_CHECK(cudaMalloc(&poisoned_active, sizeof(*poisoned_active)));
    CUDA_CHECK(cudaMemset(invalid, 0, sizeof(*invalid)));
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    const std::uint32_t active_count = audit_active_roster(workspace);
    if (active_count != 6'674U) {
      throw std::runtime_error(
          "active bucket roster count differs from the fixed source");
    }
    CUDA_CHECK(cudaEventRecord(start, stream));
    for (std::uint64_t expected = 0U; expected < kBlocks; ++expected) {
      const pda::SourceWindowView view =
          pda::run_next_source_window(workspace, stream);
      if (view.logical_block != expected ||
          view.window_center != pw::kSourceLower + pw::kWindowStep / 2U +
                                    expected * pw::kWindowStep ||
          view.device_skn_rows == nullptr ||
          view.stage_count != pw::kTaylorTerms ||
          view.row_stride != pw::kBucketCount) {
        throw std::runtime_error("DD accumulator returned a malformed view");
      }
      constexpr std::uint64_t cells =
          static_cast<std::uint64_t>(pw::kTaylorTerms) * pw::kBucketCount;
      count_invalid<<<1024U, 256U, 0U, stream>>>(
          view.device_skn_rows, cells, invalid);
      audit_inactive_exact_zero(workspace, view, nonzero_inactive,
                                audited_inactive, stream);
      if (expected == 0U) {
        poison_active_output(workspace, view, active_count, stream);
      } else {
        audit_active_overwritten(workspace, view, active_count,
                                 poisoned_active, stream);
      }
    }
    CUDA_CHECK(cudaEventRecord(stop, stream));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float elapsed_ms = 0.0F;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
    unsigned long long host_invalid = 0U;
    CUDA_CHECK(cudaMemcpy(&host_invalid, invalid, sizeof(host_invalid),
                          cudaMemcpyDeviceToHost));
    if (host_invalid != 0U || pda::windows_enqueued(workspace) != kBlocks) {
      throw std::runtime_error("DD accumulator emitted invalid disks");
    }
    qualification_workspace =
        pda::create_source_workspace_with_output_slots_qualification(
            kFirstBlock, kBlocks, 256U, 2U);
    if (pda::output_slot_count(qualification_workspace) != 2U ||
        pda::workspace_device_bytes(qualification_workspace) -
                pda::workspace_device_bytes(workspace) !=
            static_cast<std::uint64_t>(pw::kTaylorTerms) *
                pw::kBucketCount * sizeof(pw::ComplexDisk106)) {
      throw std::runtime_error(
          "qualification output-slot allocation differs");
    }
    for (std::uint32_t slot = 0U; slot < 2U; ++slot) {
      const pda::SourceWindowView view =
          pda::run_next_source_window_to_slot_qualification(
              qualification_workspace, stream, slot);
      if (view.logical_block != slot) {
        throw std::runtime_error(
            "qualification accumulator returned the wrong block");
      }
      audit_inactive_exact_zero(qualification_workspace, view,
                                nonzero_inactive, audited_inactive, stream);
    }
    std::cout << std::setprecision(17)
              << "{\"schema\":\"sparkinterval.tg.platt-dd-accumulator-api-smoke.v1\""
              << ",\"accepted\":true"
              << ",\"source_terms\":" << pw::kSourceTerms
              << ",\"taylor_stages\":" << pw::kTaylorTerms
              << ",\"blocks\":" << kBlocks
              << ",\"initialization_seconds\":"
              << initialization_seconds
              << ",\"window_gpu_seconds\":"
              << static_cast<double>(elapsed_ms) / 1000.0
              << ",\"workspace_device_bytes\":"
              << pda::workspace_device_bytes(workspace)
              << ",\"invalid_disks\":0"
              << ",\"one_slot_inactive_cells_exact_zero\":true"
              << ",\"active_bucket_count\":6674"
              << ",\"active_roster_matches_nonempty_offsets\":true"
              << ",\"active_roster_sorted_unique\":true"
              << ",\"active_cells_poisoned_between_runs\":true"
              << ",\"every_active_stage_cell_overwritten\":true"
              << ",\"inactive_cells_audited_per_slot\":600162"
              << ",\"qualification_slot_count\":2"
              << ",\"qualification_inactive_cells_exact_zero\":true"
              << ",\"physical_refinement_proved\":false"
              << ",\"pt21_source_claim_discharged\":false}\n";
    CUDA_CHECK(cudaStreamSynchronize(stream));
    CUDA_CHECK(cudaFree(invalid));
    invalid = nullptr;
    CUDA_CHECK(cudaFree(nonzero_inactive));
    nonzero_inactive = nullptr;
    CUDA_CHECK(cudaFree(audited_inactive));
    audited_inactive = nullptr;
    CUDA_CHECK(cudaFree(poisoned_active));
    poisoned_active = nullptr;
    pda::destroy_workspace(qualification_workspace);
    qualification_workspace = nullptr;
    pda::destroy_workspace(workspace);
    workspace = nullptr;
    CUDA_CHECK(cudaEventDestroy(start));
    start = nullptr;
    CUDA_CHECK(cudaEventDestroy(stop));
    stop = nullptr;
    CUDA_CHECK(cudaStreamDestroy(stream));
    stream = nullptr;
    return 0;
  } catch (...) {
    if (stream != nullptr) cudaStreamSynchronize(stream);
    if (start != nullptr) cudaEventDestroy(start);
    if (stop != nullptr) cudaEventDestroy(stop);
    if (stream != nullptr) cudaStreamDestroy(stream);
    if (invalid != nullptr) cudaFree(invalid);
    if (nonzero_inactive != nullptr) cudaFree(nonzero_inactive);
    if (audited_inactive != nullptr) cudaFree(audited_inactive);
    if (poisoned_active != nullptr) cudaFree(poisoned_active);
    try {
      pda::destroy_workspace(qualification_workspace);
    } catch (...) {
    }
    try {
      pda::destroy_workspace(workspace);
    } catch (...) {
    }
    throw;
  }
}

}  // namespace

int main() {
  try {
    return run();
  } catch (const std::exception& error) {
    std::cerr << "{\"schema\":\"sparkinterval.tg.platt-dd-accumulator-api-smoke.v1\""
              << ",\"accepted\":false,\"error\":\"" << error.what()
              << "\",\"pt21_source_claim_discharged\":false}\n";
    return 2;
  }
}

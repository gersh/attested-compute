// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_completed_sign_reducer.cuh"

#include <cub/device/device_scan.cuh>
#include <cuda_runtime.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace sparkinterval::tg::dirichlet_resident_phase_accumulator {

namespace reducer = dirichlet_completed_sign_reducer;

// One q-major phase is reduced without any per-frame device-to-host copy.
// The caller chooses a sparse capacity from campaign telemetry.  Exhausting
// it fails closed and permits a rerun with a larger capacity; it never falls
// back to copying the 88-byte PhaseState or range-count arrays per frame.
struct PhaseAccumulatorConfig {
  std::uint32_t q;
  std::uint32_t character_count;
  std::uint64_t sample_count;
  std::uint64_t first_t_numerator;
  std::uint64_t stop_t_numerator;
  std::uint64_t t_step_numerator;
  std::uint64_t sparse_range_capacity;
};

struct TaggedAmbiguityRange {
  std::uint64_t primitive_ordinal;
  reducer::AmbiguityRange range;
};

struct DensePageCheckpoint {
  reducer::DensePageTotals totals{};
  std::vector<unsigned char> dense;
};

// The only host-visible phase payload.  Dense records are the exact
// TGDCSB03 4+count-width bits and sparse entries are tagged 24-byte rows.
// Internal PhaseState and per-frame range-count arrays remain device-only.
struct PhaseCheckpoint {
  std::vector<DensePageCheckpoint> pages;
  std::vector<TaggedAmbiguityRange> ambiguity_ranges;
  reducer::DeviceSummary reduction_summary{};
  reducer::DeviceSummary pack_summary{};
  std::uint64_t raw_sparse_range_count = 0U;
  std::uint64_t coalesced_sparse_range_count = 0U;
  std::uint64_t device_to_host_bytes = 0U;
  std::uint64_t dense_staging_device_to_host_bytes = 0U;
  std::uint64_t canonical_dense_bytes = 0U;
  std::uint32_t dense_device_to_host_copy_count = 0U;
  std::uint64_t phase_state_device_to_host_bytes = 0U;
  std::uint64_t per_frame_count_device_to_host_bytes = 0U;
};

namespace detail {

inline void throwCuda(cudaError_t status, const char* operation) {
  if (status == cudaSuccess) return;
  throw std::runtime_error(
      std::string(operation) + ": " + cudaGetErrorString(status));
}

// Turn a local CUB exclusive scan into one append reservation.  A failure
// stores UINT64_MAX as the base; the next kernel maps every offset outside
// capacity so the writer can only report an error, never overwrite a prefix.
static __global__ void reserveSparseAppend(
    const std::uint64_t* range_counts, std::uint64_t* range_offsets,
    std::uint32_t character_count, std::uint64_t* global_range_count,
    std::uint64_t sparse_capacity, std::uint64_t* frame_base,
    reducer::DeviceSummary* frame_summary) {
  if (blockIdx.x != 0U || threadIdx.x != 0U) return;
  const std::uint64_t last_offset =
      range_offsets[character_count - 1U];
  const std::uint64_t last_count =
      range_counts[character_count - 1U];
  std::uint64_t local_count = 0U;
  const std::uint64_t old_count = *global_range_count;
  std::uint64_t new_count = 0U;
  if (!reducer::checkedAdd(last_offset, last_count, &local_count) ||
      !reducer::checkedAdd(old_count, local_count, &new_count) ||
      new_count > sparse_capacity) {
    *frame_base = ~std::uint64_t{0};
    range_offsets[character_count] = ~std::uint64_t{0};
    atomicOr(
        &frame_summary->reducer_error_or,
        reducer::kRangeCapacityExceeded);
    return;
  }
  *frame_base = old_count;
  *global_range_count = new_count;
  range_offsets[character_count] = local_count;
}

static __global__ void makeSparseOffsetsAbsolute(
    std::uint64_t* range_offsets, std::uint32_t character_count,
    const std::uint64_t* frame_base, std::uint64_t sparse_capacity,
    reducer::DeviceSummary* frame_summary) {
  const std::uint64_t base = *frame_base;
  for (std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
       index <= character_count;
       index += blockDim.x * gridDim.x) {
    if (base == ~std::uint64_t{0}) {
      range_offsets[index] = sparse_capacity + 1U;
      continue;
    }
    std::uint64_t absolute = 0U;
    if (!reducer::checkedAdd(base, range_offsets[index], &absolute) ||
        absolute > sparse_capacity) {
      range_offsets[index] = sparse_capacity + 1U;
      atomicOr(
          &frame_summary->reducer_error_or,
          reducer::kRangeCapacityExceeded);
    } else {
      range_offsets[index] = absolute;
    }
  }
}

static __global__ void foldFrameSummary(
    const reducer::DeviceSummary* frame,
    reducer::DeviceSummary* phase) {
  if (blockIdx.x != 0U || threadIdx.x != 0U) return;
  phase->source_status_or |= frame->source_status_or;
  phase->reducer_error_or |= frame->reducer_error_or;
  std::uint64_t total = 0U;
  if (!reducer::checkedAdd(
          phase->ambiguity_range_count,
          frame->ambiguity_range_count, &total)) {
    phase->reducer_error_or |= reducer::kStateCounterOverflow;
  } else {
    phase->ambiguity_range_count = total;
  }
}

}  // namespace detail

class ResidentPhaseAccumulator {
 public:
  explicit ResidentPhaseAccumulator(
      const PhaseAccumulatorConfig& config,
      cudaStream_t stream = nullptr)
      : config_(config), stream_(stream) {
    validateConfig();
    try {
      allocate();
      initialize();
    } catch (...) {
      release();
      throw;
    }
  }

  ResidentPhaseAccumulator(const ResidentPhaseAccumulator&) = delete;
  ResidentPhaseAccumulator& operator=(const ResidentPhaseAccumulator&) =
      delete;
  ResidentPhaseAccumulator(ResidentPhaseAccumulator&&) = delete;
  ResidentPhaseAccumulator& operator=(ResidentPhaseAccumulator&&) = delete;

  ~ResidentPhaseAccumulator() { release(); }

  const PhaseAccumulatorConfig& config() const { return config_; }
  std::uint64_t frameCount() const { return frame_count_; }
  std::uint64_t accumulatedSampleCount() const {
    return accumulated_sample_count_;
  }
  std::uint64_t residentBytes() const {
    return 2U * static_cast<std::uint64_t>(stateBytes()) +
           static_cast<std::uint64_t>(config_.character_count) *
               sizeof(std::uint64_t) +
           (static_cast<std::uint64_t>(config_.character_count) + 1U) *
               sizeof(std::uint64_t) +
           config_.sparse_range_capacity *
               (sizeof(reducer::AmbiguityRange) +
                sizeof(std::uint64_t)) +
           2U * sizeof(std::uint64_t) +
           3U * sizeof(reducer::DeviceSummary) +
           packed_capacity_bytes_ +
           page_count_ * sizeof(reducer::DensePageTotals) +
           scan_temporary_bytes_;
  }
  std::size_t cubScanTemporaryBytes() const {
    return scan_temporary_bytes_;
  }

  // Queue reduction, CUB scan, sparse append, and ordered dense-state merge
  // in one stream.  There is intentionally no event/device synchronization
  // and no device-to-host transfer in this method.
  cudaError_t enqueueFrame(const reducer::ResidentFrameView& frame) {
    if (finalized_ || poisoned_ ||
        !reducer::validResidentFrameView(frame) ||
        frame.q != config_.q ||
        frame.character_count != config_.character_count ||
        frame.first_t_numerator != expected_next_t_numerator_ ||
        frame.t_step_numerator != config_.t_step_numerator ||
        frame.sample_count >
            config_.sample_count - accumulated_sample_count_) {
      poisoned_ = true;
      return cudaErrorInvalidValue;
    }
    std::uint64_t frame_stop = 0U;
    if (!reducer::sampleNumerator(
            frame.first_t_numerator, frame.t_step_numerator,
            frame.sample_count, &frame_stop) ||
        frame_stop > config_.stop_t_numerator) {
      poisoned_ = true;
      return cudaErrorInvalidValue;
    }

    const reducer::ReductionWorkspace reduction{
        d_frame_states_, d_range_counts_, d_frame_summary_};
    cudaError_t status =
        reducer::launchResidentPhaseReduction(frame, reduction, stream_);
    if (status != cudaSuccess) return poison(status);
    status = cub::DeviceScan::ExclusiveSum(
        d_scan_temporary_, scan_temporary_bytes_, d_range_counts_,
        d_range_offsets_, config_.character_count, stream_);
    if (status != cudaSuccess) return poison(status);
    detail::reserveSparseAppend<<<1, 1, 0, stream_>>>(
        d_range_counts_, d_range_offsets_, config_.character_count,
        d_sparse_range_count_, config_.sparse_range_capacity,
        d_frame_base_, d_frame_summary_);
    status = cudaGetLastError();
    if (status != cudaSuccess) return poison(status);
    const std::uint32_t offset_blocks = std::min<std::uint32_t>(
        4096U, (config_.character_count + 256U) / 256U);
    detail::makeSparseOffsetsAbsolute<<<
        offset_blocks, 256, 0, stream_>>>(
        d_range_offsets_, config_.character_count, d_frame_base_,
        config_.sparse_range_capacity, d_frame_summary_);
    status = cudaGetLastError();
    if (status != cudaSuccess) return poison(status);
    status =
        reducer::launchResidentTaggedAmbiguityRangeWriteIntoInitializedStorage(
            frame, d_frame_states_, d_range_offsets_,
            config_.sparse_range_capacity, d_sparse_ranges_,
            d_sparse_ordinals_, d_frame_summary_, stream_);
    if (status != cudaSuccess) return poison(status);

    if (frame_count_ == 0U) {
      status = cudaMemcpyAsync(
          d_aggregate_a_, d_frame_states_,
          stateBytes(), cudaMemcpyDeviceToDevice, stream_);
      if (status != cudaSuccess) return poison(status);
      d_current_aggregate_ = d_aggregate_a_;
    } else {
      const std::uint32_t blocks = std::min<std::uint32_t>(
          4096U, (config_.character_count + 255U) / 256U);
      // combineAdjacentStateArrays is lane-local: it reads one left/right
      // state into combineAdjacentStates before the final output assignment.
      // Aliasing output with left is therefore safe and saves one complete
      // 88-byte-per-character aggregate buffer.
      reducer::combineAdjacentStateArrays<<<blocks, 256, 0, stream_>>>(
          d_current_aggregate_, d_frame_states_,
          config_.character_count, d_current_aggregate_,
          d_frame_summary_);
      status = cudaGetLastError();
      if (status != cudaSuccess) return poison(status);
    }
    detail::foldFrameSummary<<<1, 1, 0, stream_>>>(
        d_frame_summary_, d_reduction_summary_);
    status = cudaGetLastError();
    if (status != cudaSuccess) return poison(status);

    expected_next_t_numerator_ = frame_stop;
    accumulated_sample_count_ += frame.sample_count;
    ++frame_count_;
    return cudaSuccess;
  }

  // Queue exact TGDCSB03 dense packing.  The first host synchronization is
  // deferred to checkpoint(); callers may enqueue more same-stream work
  // between these operations.
  cudaError_t finalize() {
    if (finalized_) return cudaSuccess;
    if (poisoned_ || frame_count_ == 0U ||
        accumulated_sample_count_ != config_.sample_count ||
        expected_next_t_numerator_ != config_.stop_t_numerator ||
        d_current_aggregate_ == nullptr) {
      poisoned_ = true;
      return cudaErrorInvalidValue;
    }
    const reducer::DensePackView pack{
        d_current_aggregate_,
        config_.character_count,
        config_.sample_count,
        config_.first_t_numerator,
        config_.stop_t_numerator,
        config_.t_step_numerator,
        d_packed_pages_,
        packed_capacity_bytes_,
        d_page_totals_,
        page_count_,
        d_pack_summary_,
    };
    const cudaError_t status =
        reducer::launchDenseTGDCSB03Pack(pack, stream_);
    if (status != cudaSuccess) return poison(status);
    finalized_ = true;
    return cudaSuccess;
  }

  PhaseCheckpoint checkpoint() {
    detail::throwCuda(finalize(), "finalize resident phase accumulator");
    detail::throwCuda(
        cudaStreamSynchronize(stream_),
        "synchronize resident phase checkpoint");

    PhaseCheckpoint checkpoint;
    std::vector<reducer::DensePageTotals> page_totals(page_count_);
    detail::throwCuda(
        cudaMemcpy(
            &checkpoint.reduction_summary, d_reduction_summary_,
            sizeof(checkpoint.reduction_summary),
            cudaMemcpyDeviceToHost),
        "copy resident phase reduction summary");
    detail::throwCuda(
        cudaMemcpy(
            &checkpoint.pack_summary, d_pack_summary_,
            sizeof(checkpoint.pack_summary), cudaMemcpyDeviceToHost),
        "copy resident phase pack summary");
    detail::throwCuda(
        cudaMemcpy(
            &checkpoint.raw_sparse_range_count, d_sparse_range_count_,
            sizeof(checkpoint.raw_sparse_range_count),
            cudaMemcpyDeviceToHost),
        "copy resident phase sparse count");
    detail::throwCuda(
        cudaMemcpy(
            page_totals.data(), d_page_totals_,
            page_totals.size() * sizeof(page_totals[0]),
            cudaMemcpyDeviceToHost),
        "copy resident phase page totals");
    checkpoint.device_to_host_bytes =
        2U * sizeof(reducer::DeviceSummary) +
        sizeof(std::uint64_t) +
        page_totals.size() * sizeof(reducer::DensePageTotals);

    if (checkpoint.reduction_summary.source_status_or != 0U ||
        checkpoint.reduction_summary.reducer_error_or != 0U ||
        checkpoint.pack_summary.source_status_or != 0U ||
        checkpoint.pack_summary.reducer_error_or != 0U ||
        checkpoint.pack_summary.ambiguity_range_count != 0U ||
        checkpoint.raw_sparse_range_count >
            config_.sparse_range_capacity ||
        checkpoint.reduction_summary.ambiguity_range_count !=
            checkpoint.raw_sparse_range_count) {
      throw std::runtime_error(
          "resident phase summary reports a failed reduction or pack");
    }

    // Fixed-stride pages are contiguous.  Copy them once and slice the
    // canonical prefixes on the host after validating page_totals.  Every
    // page except the final page is full, so the bandwidth overhead is at
    // most one page stride while eliminating up to 98 small synchronous
    // transfers for a source-range modulus.
    std::vector<unsigned char> packed_staging(
        static_cast<std::size_t>(packed_capacity_bytes_));
    detail::throwCuda(
        cudaMemcpy(
            packed_staging.data(), d_packed_pages_,
            packed_staging.size(), cudaMemcpyDeviceToHost),
        "copy resident phase dense staging");
    checkpoint.dense_staging_device_to_host_bytes =
        packed_staging.size();
    checkpoint.dense_device_to_host_copy_count = 1U;
    checkpoint.device_to_host_bytes += packed_staging.size();
    checkpoint.pages.reserve(page_count_);
    for (std::uint64_t page = 0U; page < page_count_; ++page) {
      const std::uint64_t ordinal_start =
          page * reducer::kDensePageCharacters;
      const std::uint64_t characters = std::min<std::uint64_t>(
          reducer::kDensePageCharacters,
          config_.character_count - ordinal_start);
      const std::uint64_t dense_bytes =
          reducer::densePackedBytes(
              characters,
              reducer::denseRecordWidth(config_.sample_count));
      const auto& totals = page_totals[page];
      if (totals.ordinal_start != ordinal_start ||
          totals.character_count != characters ||
          totals.dense_bytes != dense_bytes ||
          totals.count_width !=
              reducer::denseCountWidth(config_.sample_count) ||
          totals.record_width !=
              reducer::denseRecordWidth(config_.sample_count) ||
          totals.status_or != 0U) {
        throw std::runtime_error(
            "resident phase dense page metadata differs");
      }
      DensePageCheckpoint output;
      output.totals = totals;
      const auto begin =
          packed_staging.begin() +
          static_cast<std::ptrdiff_t>(page * page_stride_bytes_);
      output.dense.assign(
          begin, begin + static_cast<std::ptrdiff_t>(dense_bytes));
      checkpoint.canonical_dense_bytes += output.dense.size();
      checkpoint.pages.push_back(std::move(output));
    }

    std::vector<std::uint64_t> raw_ordinals(
        static_cast<std::size_t>(checkpoint.raw_sparse_range_count));
    std::vector<reducer::AmbiguityRange> raw_ranges(
        static_cast<std::size_t>(checkpoint.raw_sparse_range_count));
    if (!raw_ranges.empty()) {
      detail::throwCuda(
          cudaMemcpy(
              raw_ordinals.data(), d_sparse_ordinals_,
              raw_ordinals.size() * sizeof(raw_ordinals[0]),
              cudaMemcpyDeviceToHost),
          "copy resident phase sparse ordinals");
      detail::throwCuda(
          cudaMemcpy(
              raw_ranges.data(), d_sparse_ranges_,
              raw_ranges.size() * sizeof(raw_ranges[0]),
              cudaMemcpyDeviceToHost),
          "copy resident phase sparse ranges");
      checkpoint.device_to_host_bytes +=
          raw_ordinals.size() * sizeof(raw_ordinals[0]) +
          raw_ranges.size() * sizeof(raw_ranges[0]);
    }
    checkpoint.ambiguity_ranges.reserve(raw_ranges.size());
    for (std::size_t index = 0U; index < raw_ranges.size(); ++index) {
      checkpoint.ambiguity_ranges.push_back(
          {raw_ordinals[index], raw_ranges[index]});
    }
    validateAndCoalesce(&checkpoint);
    return checkpoint;
  }

 private:
  cudaError_t poison(cudaError_t status) {
    poisoned_ = true;
    return status;
  }

  std::size_t stateBytes() const {
    return static_cast<std::size_t>(config_.character_count) *
           sizeof(reducer::PhaseState);
  }

  void validateConfig() {
    std::uint64_t expected_stop = 0U;
    if (config_.q == 0U ||
        config_.q > reducer::kMaximumModulus ||
        config_.character_count == 0U ||
        config_.character_count > reducer::kMaximumModulus ||
        config_.sample_count == 0U ||
        config_.sample_count > reducer::kMaximumPackedSamples ||
        config_.t_step_numerator != reducer::kSourceStepNumerator ||
        !reducer::sampleNumerator(
            config_.first_t_numerator, config_.t_step_numerator,
            config_.sample_count, &expected_stop) ||
        expected_stop != config_.stop_t_numerator ||
        config_.sparse_range_capacity == 0U ||
        config_.sparse_range_capacity ==
            ~std::uint64_t{0} ||
        config_.sparse_range_capacity >
            std::numeric_limits<std::size_t>::max() /
                sizeof(TaggedAmbiguityRange)) {
      throw std::invalid_argument(
          "resident phase accumulator geometry is invalid");
    }
    page_count_ =
        reducer::densePageCount(config_.character_count);
    page_stride_bytes_ =
        reducer::densePageStrideBytes(config_.sample_count);
    if (page_count_ == 0U ||
        page_stride_bytes_ == ~std::uint64_t{0} ||
        !reducer::checkedMul(
            page_count_, page_stride_bytes_,
            &packed_capacity_bytes_) ||
        packed_capacity_bytes_ >
            std::numeric_limits<std::size_t>::max()) {
      throw std::invalid_argument(
          "resident phase dense-pack capacity overflows");
    }
  }

  void allocate() {
    detail::throwCuda(
        cudaMalloc(&d_frame_states_, stateBytes()),
        "allocate resident frame states");
    detail::throwCuda(
        cudaMalloc(&d_aggregate_a_, stateBytes()),
        "allocate resident aggregate states A");
    detail::throwCuda(
        cudaMalloc(
            &d_range_counts_,
            static_cast<std::size_t>(config_.character_count) *
                sizeof(std::uint64_t)),
        "allocate resident range counts");
    detail::throwCuda(
        cudaMalloc(
            &d_range_offsets_,
            (static_cast<std::size_t>(config_.character_count) + 1U) *
                sizeof(std::uint64_t)),
        "allocate resident range offsets");
    detail::throwCuda(
        cudaMalloc(
            &d_sparse_ranges_,
            static_cast<std::size_t>(config_.sparse_range_capacity) *
                sizeof(reducer::AmbiguityRange)),
        "allocate resident sparse ranges");
    detail::throwCuda(
        cudaMalloc(
            &d_sparse_ordinals_,
            static_cast<std::size_t>(config_.sparse_range_capacity) *
                sizeof(std::uint64_t)),
        "allocate resident sparse ordinals");
    detail::throwCuda(
        cudaMalloc(&d_sparse_range_count_, sizeof(std::uint64_t)),
        "allocate resident sparse count");
    detail::throwCuda(
        cudaMalloc(&d_frame_base_, sizeof(std::uint64_t)),
        "allocate resident frame sparse base");
    detail::throwCuda(
        cudaMalloc(&d_frame_summary_, sizeof(reducer::DeviceSummary)),
        "allocate resident frame summary");
    detail::throwCuda(
        cudaMalloc(&d_reduction_summary_, sizeof(reducer::DeviceSummary)),
        "allocate resident reduction summary");
    detail::throwCuda(
        cudaMalloc(&d_pack_summary_, sizeof(reducer::DeviceSummary)),
        "allocate resident pack summary");
    detail::throwCuda(
        cudaMalloc(
            &d_packed_pages_,
            static_cast<std::size_t>(packed_capacity_bytes_)),
        "allocate resident dense pages");
    detail::throwCuda(
        cudaMalloc(
            &d_page_totals_,
            static_cast<std::size_t>(page_count_) *
                sizeof(reducer::DensePageTotals)),
        "allocate resident dense page totals");
    detail::throwCuda(
        cub::DeviceScan::ExclusiveSum(
            nullptr, scan_temporary_bytes_, d_range_counts_,
            d_range_offsets_, config_.character_count, stream_),
        "size resident CUB scan");
    detail::throwCuda(
        cudaMalloc(&d_scan_temporary_, scan_temporary_bytes_),
        "allocate resident CUB scan temporary");
  }

  void initialize() {
    detail::throwCuda(
        cudaMemsetAsync(
            d_sparse_range_count_, 0, sizeof(std::uint64_t), stream_),
        "initialize resident sparse count");
    detail::throwCuda(
        cudaMemsetAsync(
            d_reduction_summary_, 0,
            sizeof(reducer::DeviceSummary), stream_),
        "initialize resident reduction summary");
    detail::throwCuda(
        cudaMemsetAsync(
            d_pack_summary_, 0,
            sizeof(reducer::DeviceSummary), stream_),
        "initialize resident pack summary");
    detail::throwCuda(
        cudaMemsetAsync(
            d_sparse_ranges_, 0,
            static_cast<std::size_t>(config_.sparse_range_capacity) *
                sizeof(reducer::AmbiguityRange),
            stream_),
        "initialize resident sparse ranges");
    detail::throwCuda(
        cudaMemsetAsync(
            d_sparse_ordinals_, 0xff,
            static_cast<std::size_t>(config_.sparse_range_capacity) *
                sizeof(std::uint64_t),
            stream_),
        "initialize resident sparse ordinals");
    expected_next_t_numerator_ = config_.first_t_numerator;
  }

  void validateAndCoalesce(PhaseCheckpoint* checkpoint) const {
    std::sort(
        checkpoint->ambiguity_ranges.begin(),
        checkpoint->ambiguity_ranges.end(),
        [](const TaggedAmbiguityRange& left,
           const TaggedAmbiguityRange& right) {
          if (left.primitive_ordinal != right.primitive_ordinal) {
            return left.primitive_ordinal < right.primitive_ordinal;
          }
          if (left.range.first_t_numerator !=
              right.range.first_t_numerator) {
            return left.range.first_t_numerator <
                   right.range.first_t_numerator;
          }
          return left.range.stop_t_numerator <
                 right.range.stop_t_numerator;
        });
    std::vector<TaggedAmbiguityRange> coalesced;
    coalesced.reserve(checkpoint->ambiguity_ranges.size());
    for (const auto& tagged : checkpoint->ambiguity_ranges) {
      const auto& range = tagged.range;
      if (tagged.primitive_ordinal >= config_.character_count ||
          range.first_t_numerator < config_.first_t_numerator ||
          range.stop_t_numerator > config_.stop_t_numerator ||
          range.first_t_numerator >= range.stop_t_numerator ||
          (range.first_t_numerator - config_.first_t_numerator) %
                  config_.t_step_numerator !=
              0U ||
          (range.stop_t_numerator - config_.first_t_numerator) %
                  config_.t_step_numerator !=
              0U) {
        throw std::runtime_error(
            "resident phase sparse range has invalid coordinates");
      }
      if (!coalesced.empty() &&
          coalesced.back().primitive_ordinal ==
              tagged.primitive_ordinal) {
        auto& previous = coalesced.back().range;
        if (range.first_t_numerator < previous.stop_t_numerator) {
          throw std::runtime_error(
              "resident phase sparse ranges overlap");
        }
        if (range.first_t_numerator == previous.stop_t_numerator) {
          previous.stop_t_numerator = range.stop_t_numerator;
          continue;
        }
      }
      coalesced.push_back(tagged);
    }
    checkpoint->ambiguity_ranges = std::move(coalesced);
    checkpoint->coalesced_sparse_range_count =
        checkpoint->ambiguity_ranges.size();

    std::vector<std::uint64_t> ranges_per_character(
        config_.character_count, 0U);
    std::vector<std::uint64_t> samples_per_character(
        config_.character_count, 0U);
    for (const auto& tagged : checkpoint->ambiguity_ranges) {
      ++ranges_per_character[tagged.primitive_ordinal];
      samples_per_character[tagged.primitive_ordinal] +=
          (tagged.range.stop_t_numerator -
           tagged.range.first_t_numerator) /
          config_.t_step_numerator;
    }

    for (const auto& page : checkpoint->pages) {
      std::uint64_t transition_count = 0U;
      std::uint64_t ambiguity_sample_count = 0U;
      std::uint64_t ambiguity_range_count = 0U;
      std::uint32_t sparse_character_count = 0U;
      for (std::uint64_t local = 0U;
           local < page.totals.character_count; ++local) {
        const std::uint64_t ordinal =
            page.totals.ordinal_start + local;
        reducer::DenseDecodedRecord decoded{};
        if (!reducer::decodeDenseRecord(
                page.dense.data(), local, config_.sample_count,
                &decoded)) {
          throw std::runtime_error(
              "resident phase dense record does not decode");
        }
        const bool has_sparse = ranges_per_character[ordinal] != 0U;
        if ((decoded.has_sparse != 0U) != has_sparse) {
          throw std::runtime_error(
              "resident phase dense/sparse character flags differ");
        }
        transition_count += decoded.transition_count;
        ambiguity_sample_count +=
            samples_per_character[ordinal];
        ambiguity_range_count +=
            ranges_per_character[ordinal];
        sparse_character_count +=
            static_cast<std::uint32_t>(has_sparse);
      }
      if (transition_count != page.totals.transition_count ||
          ambiguity_sample_count !=
              page.totals.ambiguity_sample_count ||
          ambiguity_range_count !=
              page.totals.ambiguity_range_count ||
          sparse_character_count !=
              page.totals.sparse_character_count) {
        throw std::runtime_error(
            "resident phase page totals differ from compact payload");
      }
    }
  }

  void release() noexcept {
    cudaFree(d_scan_temporary_);
    d_scan_temporary_ = nullptr;
    cudaFree(d_page_totals_);
    d_page_totals_ = nullptr;
    cudaFree(d_packed_pages_);
    d_packed_pages_ = nullptr;
    cudaFree(d_pack_summary_);
    d_pack_summary_ = nullptr;
    cudaFree(d_reduction_summary_);
    d_reduction_summary_ = nullptr;
    cudaFree(d_frame_summary_);
    d_frame_summary_ = nullptr;
    cudaFree(d_frame_base_);
    d_frame_base_ = nullptr;
    cudaFree(d_sparse_range_count_);
    d_sparse_range_count_ = nullptr;
    cudaFree(d_sparse_ordinals_);
    d_sparse_ordinals_ = nullptr;
    cudaFree(d_sparse_ranges_);
    d_sparse_ranges_ = nullptr;
    cudaFree(d_range_offsets_);
    d_range_offsets_ = nullptr;
    cudaFree(d_range_counts_);
    d_range_counts_ = nullptr;
    cudaFree(d_aggregate_a_);
    d_aggregate_a_ = nullptr;
    cudaFree(d_frame_states_);
    d_frame_states_ = nullptr;
  }

  PhaseAccumulatorConfig config_{};
  cudaStream_t stream_ = nullptr;
  reducer::PhaseState* d_frame_states_ = nullptr;
  reducer::PhaseState* d_aggregate_a_ = nullptr;
  reducer::PhaseState* d_current_aggregate_ = nullptr;
  std::uint64_t* d_range_counts_ = nullptr;
  std::uint64_t* d_range_offsets_ = nullptr;
  reducer::AmbiguityRange* d_sparse_ranges_ = nullptr;
  std::uint64_t* d_sparse_ordinals_ = nullptr;
  std::uint64_t* d_sparse_range_count_ = nullptr;
  std::uint64_t* d_frame_base_ = nullptr;
  reducer::DeviceSummary* d_frame_summary_ = nullptr;
  reducer::DeviceSummary* d_reduction_summary_ = nullptr;
  reducer::DeviceSummary* d_pack_summary_ = nullptr;
  unsigned char* d_packed_pages_ = nullptr;
  reducer::DensePageTotals* d_page_totals_ = nullptr;
  void* d_scan_temporary_ = nullptr;
  std::size_t scan_temporary_bytes_ = 0U;
  std::uint64_t page_count_ = 0U;
  std::uint64_t page_stride_bytes_ = 0U;
  std::uint64_t packed_capacity_bytes_ = 0U;
  std::uint64_t frame_count_ = 0U;
  std::uint64_t accumulated_sample_count_ = 0U;
  std::uint64_t expected_next_t_numerator_ = 0U;
  bool finalized_ = false;
  bool poisoned_ = false;
};

}  // namespace sparkinterval::tg::dirichlet_resident_phase_accumulator

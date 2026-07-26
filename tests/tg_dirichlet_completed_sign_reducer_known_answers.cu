// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_dirichlet_completed_sign_reducer.cuh"

#include <cuda_runtime.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace reducer =
    sparkinterval::tg::dirichlet_completed_sign_reducer;
namespace dl = sparkinterval::tg::dirichlet_lattice;
namespace sc =
    sparkinterval::tg::dirichlet_booker_smallq_certified;

namespace {

__global__ void evaluateBookerFmaProduct(
    sc::Disk left, sc::Disk right, sc::Disk* output) {
  output[0] = reducer::diskMul(left, right);
}

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

template <typename T>
struct DeviceBuffer {
  T* pointer = nullptr;
  std::size_t count = 0U;

  DeviceBuffer() = default;
  explicit DeviceBuffer(std::size_t requested) : count(requested) {
    CUDA_CHECK(cudaMalloc(&pointer, std::max<std::size_t>(1U, count) *
                                        sizeof(T)));
  }
  DeviceBuffer(const DeviceBuffer&) = delete;
  DeviceBuffer& operator=(const DeviceBuffer&) = delete;
  ~DeviceBuffer() { cudaFree(pointer); }
};

dl::ComplexInterval pointBox(double real, double imaginary = 0.0) {
  return {{real, real}, {imaginary, imaginary}};
}

dl::ComplexInterval intervalBox(double real_lo, double real_hi,
                                double imaginary_lo, double imaginary_hi) {
  return {{real_lo, real_hi}, {imaginary_lo, imaginary_hi}};
}

sc::Disk pointDisk(double real, double imaginary = 0.0) {
  return {real, imaginary, 0.0};
}

double doubleFromBits(std::uint64_t bits) {
  double value = 0.0;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

std::uint64_t doubleBits(double value) {
  std::uint64_t bits = 0U;
  std::memcpy(&bits, &value, sizeof(bits));
  return bits;
}

struct RunResult {
  std::vector<reducer::PhaseState> states;
  std::vector<std::uint64_t> offsets;
  std::vector<reducer::AmbiguityRange> ranges;
  std::vector<std::uint64_t> range_primitive_ordinals;
  reducer::DeviceSummary summary;
};

RunResult runReducer(
    const std::vector<dl::ComplexInterval>& values,
    const std::vector<std::uint32_t>& statuses,
    const std::vector<sc::Disk>& roots,
    const std::vector<sc::Disk>& factors,
    const std::vector<std::uint8_t>& parities,
    std::uint32_t samples, std::uint64_t first,
    std::uint64_t stride = 0U) {
  const std::uint32_t characters =
      static_cast<std::uint32_t>(roots.size());
  if (stride == 0U) stride = characters;
  if (characters == 0U || parities.size() != characters ||
      factors.size() != 2U * samples ||
      values.size() != static_cast<std::size_t>(samples) * stride ||
      statuses.size() != values.size()) {
    throw std::runtime_error("bad reducer KAT dimensions");
  }
  DeviceBuffer<dl::ComplexInterval> d_values(values.size());
  DeviceBuffer<std::uint32_t> d_statuses(statuses.size());
  DeviceBuffer<sc::Disk> d_roots(roots.size());
  DeviceBuffer<sc::Disk> d_factors(factors.size());
  DeviceBuffer<std::uint8_t> d_parities(parities.size());
  DeviceBuffer<std::uint64_t> d_frequencies(characters);
  DeviceBuffer<reducer::PhaseState> d_states(characters);
  DeviceBuffer<std::uint64_t> d_counts(characters);
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_values.pointer, values.data(),
                        values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_statuses.pointer, statuses.data(),
                        statuses.size() * sizeof(statuses[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots.pointer, roots.data(),
                        roots.size() * sizeof(roots[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_factors.pointer, factors.data(),
                        factors.size() * sizeof(factors[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_parities.pointer, parities.data(),
                        parities.size() * sizeof(parities[0]),
                        cudaMemcpyHostToDevice));
  std::vector<std::uint64_t> frequencies(characters);
  for (std::uint32_t character = 0U; character < characters; ++character) {
    frequencies[character] = character;
  }
  CUDA_CHECK(cudaMemcpy(d_frequencies.pointer, frequencies.data(),
                        frequencies.size() * sizeof(frequencies[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                        sizeof(reducer::DeviceSummary)));
  const bool all_statuses_zero =
      std::all_of(statuses.begin(), statuses.end(),
                  [](std::uint32_t status) { return status == 0U; });
  const reducer::ResidentFrameView frame{
      5U,
      characters,
      samples,
      0U,
      stride,
      static_cast<std::uint64_t>(values.size()),
      first,
      reducer::kSourceStepNumerator,
      d_values.pointer,
      all_statuses_zero ? nullptr : d_statuses.pointer,
      d_roots.pointer,
      d_factors.pointer,
      d_parities.pointer,
      d_frequencies.pointer,
  };
  const reducer::ReductionWorkspace workspace{
      d_states.pointer, d_counts.pointer, d_summary.pointer};
  CUDA_CHECK(reducer::launchResidentPhaseReduction(frame, workspace));
  CUDA_CHECK(cudaDeviceSynchronize());

  RunResult result;
  result.states.resize(characters);
  std::vector<std::uint64_t> counts(characters);
  CUDA_CHECK(cudaMemcpy(result.states.data(), d_states.pointer,
                        result.states.size() * sizeof(result.states[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(counts.data(), d_counts.pointer,
                        counts.size() * sizeof(counts[0]),
                        cudaMemcpyDeviceToHost));
  result.offsets.assign(characters + 1U, 0U);
  for (std::uint32_t character = 0U; character < characters; ++character) {
    result.offsets[character + 1U] =
        result.offsets[character] + counts[character];
  }
  DeviceBuffer<std::uint64_t> d_offsets(result.offsets.size());
  DeviceBuffer<reducer::AmbiguityRange> d_ranges(
      result.offsets.back());
  CUDA_CHECK(cudaMemcpy(d_offsets.pointer, result.offsets.data(),
                        result.offsets.size() * sizeof(result.offsets[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(reducer::launchResidentAmbiguityRangeWrite(
      frame, d_states.pointer, d_offsets.pointer, result.offsets.back(),
      d_ranges.pointer, d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  result.ranges.resize(result.offsets.back());
  if (!result.ranges.empty()) {
    CUDA_CHECK(cudaMemcpy(result.ranges.data(), d_ranges.pointer,
                          result.ranges.size() * sizeof(result.ranges[0]),
                          cudaMemcpyDeviceToHost));
  }
  DeviceBuffer<reducer::AmbiguityRange> d_tagged_ranges(
      result.offsets.back());
  DeviceBuffer<std::uint64_t> d_range_ordinals(result.offsets.back());
  CUDA_CHECK(reducer::launchResidentTaggedAmbiguityRangeWrite(
      frame, d_states.pointer, d_offsets.pointer, result.offsets.back(),
      d_tagged_ranges.pointer, d_range_ordinals.pointer,
      d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  std::vector<reducer::AmbiguityRange> tagged_ranges(
      result.offsets.back());
  result.range_primitive_ordinals.resize(result.offsets.back());
  if (!tagged_ranges.empty()) {
    CUDA_CHECK(cudaMemcpy(
        tagged_ranges.data(), d_tagged_ranges.pointer,
        tagged_ranges.size() * sizeof(tagged_ranges[0]),
        cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(
        result.range_primitive_ordinals.data(), d_range_ordinals.pointer,
        result.range_primitive_ordinals.size() *
            sizeof(result.range_primitive_ordinals[0]),
        cudaMemcpyDeviceToHost));
    if (std::memcmp(tagged_ranges.data(), result.ranges.data(),
                    tagged_ranges.size() * sizeof(tagged_ranges[0])) != 0) {
      throw std::runtime_error(
          "tagged and untagged sparse ranges differ");
    }
  }
  CUDA_CHECK(cudaMemcpy(&result.summary, d_summary.pointer,
                        sizeof(result.summary), cudaMemcpyDeviceToHost));
  return result;
}

bool sameState(const reducer::PhaseState& left,
               const reducer::PhaseState& right) {
  return std::memcmp(&left, &right, sizeof(left)) == 0;
}

std::vector<reducer::PhaseState> combineOnDevice(
    const std::vector<reducer::PhaseState>& left,
    const std::vector<reducer::PhaseState>& right,
    reducer::DeviceSummary* summary) {
  if (left.size() != right.size() || left.empty()) {
    throw std::runtime_error("bad state merge dimensions");
  }
  DeviceBuffer<reducer::PhaseState> d_left(left.size());
  DeviceBuffer<reducer::PhaseState> d_right(right.size());
  DeviceBuffer<reducer::PhaseState> d_output(left.size());
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_left.pointer, left.data(),
                        left.size() * sizeof(left[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_right.pointer, right.data(),
                        right.size() * sizeof(right[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(d_output.pointer, 0,
                        left.size() * sizeof(left[0])));
  CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                        sizeof(reducer::DeviceSummary)));
  reducer::combineAdjacentStateArrays<<<1, 128>>>(
      d_left.pointer, d_right.pointer,
      static_cast<std::uint32_t>(left.size()), d_output.pointer,
      d_summary.pointer);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  std::vector<reducer::PhaseState> result(left.size());
  CUDA_CHECK(cudaMemcpy(result.data(), d_output.pointer,
                        result.size() * sizeof(result[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(summary, d_summary.pointer, sizeof(*summary),
                        cudaMemcpyDeviceToHost));
  return result;
}

struct DensePackKatStats {
  std::uint64_t pages;
  std::uint64_t staging_bytes;
  std::uint64_t canonical_bytes;
};

std::uint32_t hostCountWidth(std::uint64_t sample_count) {
  if (sample_count <= 1U) return 1U;
  std::uint64_t maximum = sample_count - 1U;
  std::uint32_t width = 0U;
  while (maximum != 0U) {
    ++width;
    maximum >>= 1U;
  }
  return width;
}

DensePackKatStats runDensePackKat(
    const std::vector<reducer::PhaseState>& states,
    std::uint64_t sample_count, std::uint64_t first_t_numerator) {
  if (states.empty() || sample_count == 0U ||
      reducer::denseCountWidth(1U) != 1U ||
      reducer::denseCountWidth(2U) != 1U ||
      reducer::denseCountWidth(3U) != 2U ||
      reducer::denseCountWidth(8U) != 3U ||
      reducer::denseCountWidth(127988U) != 17U) {
    throw std::runtime_error("dense transition width edge differs");
  }
  const std::uint32_t count_width = hostCountWidth(sample_count);
  const std::uint32_t record_width = 4U + count_width;
  const std::uint64_t pages =
      (states.size() + reducer::kDensePageCharacters - 1U) /
      reducer::kDensePageCharacters;
  const std::uint64_t page_stride =
      (static_cast<std::uint64_t>(reducer::kDensePageCharacters) *
           record_width +
       7U) /
      8U;
  const std::uint64_t staging_bytes = pages * page_stride;
  const std::uint64_t stop_t_numerator =
      first_t_numerator +
      sample_count * reducer::kSourceStepNumerator;

  // This is deliberately independent of the device packer: construct every
  // expected bit and every page aggregate directly from the PhaseState
  // fields.
  std::vector<unsigned char> expected(staging_bytes, 0U);
  std::vector<reducer::DensePageTotals> expected_totals(pages);
  std::uint64_t canonical_bytes = 0U;
  for (std::uint64_t page = 0U; page < pages; ++page) {
    auto& totals = expected_totals[page];
    totals.ordinal_start =
        page * reducer::kDensePageCharacters;
    totals.character_count = std::min<std::uint64_t>(
        reducer::kDensePageCharacters,
        states.size() - totals.ordinal_start);
    totals.dense_bytes =
        (totals.character_count * record_width + 7U) / 8U;
    totals.count_width = count_width;
    totals.record_width = record_width;
    canonical_bytes += totals.dense_bytes;
    for (std::uint64_t local = 0U; local < totals.character_count;
         ++local) {
      const auto& state = states[totals.ordinal_start + local];
      const bool has_determinate = state.has_determinate != 0U;
      const bool has_sparse = state.ambiguity_range_count != 0U;
      const std::uint64_t flags =
          static_cast<std::uint64_t>(has_determinate) |
          (static_cast<std::uint64_t>(
               has_determinate && state.first_sign > 0)
           << 1U) |
          (static_cast<std::uint64_t>(
               has_determinate && state.last_sign > 0)
           << 2U) |
          (static_cast<std::uint64_t>(has_sparse) << 3U);
      const std::uint64_t value =
          flags | (state.transition_count << 4U);
      const std::uint64_t bit_start = local * record_width;
      for (std::uint32_t bit = 0U; bit < record_width; ++bit) {
        if ((value & (std::uint64_t{1} << bit)) == 0U) continue;
        const std::uint64_t absolute = bit_start + bit;
        expected[page * page_stride + absolute / 8U] |=
            static_cast<unsigned char>(1U << (absolute % 8U));
      }
      totals.transition_count += state.transition_count;
      totals.ambiguity_sample_count += state.ambiguity_count;
      totals.ambiguity_range_count += state.ambiguity_range_count;
      totals.sparse_character_count +=
          static_cast<std::uint32_t>(has_sparse);
    }
  }

  DeviceBuffer<reducer::PhaseState> d_states(states.size());
  DeviceBuffer<unsigned char> d_packed(staging_bytes);
  DeviceBuffer<reducer::DensePageTotals> d_totals(pages);
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_states.pointer, states.data(),
                        states.size() * sizeof(states[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(d_packed.pointer, 0xa5, staging_bytes));
  const reducer::DensePackView view{
      d_states.pointer,
      states.size(),
      sample_count,
      first_t_numerator,
      stop_t_numerator,
      reducer::kSourceStepNumerator,
      d_packed.pointer,
      staging_bytes,
      d_totals.pointer,
      pages,
      d_summary.pointer,
  };
  CUDA_CHECK(reducer::launchDenseTGDCSB03Pack(view));
  CUDA_CHECK(cudaDeviceSynchronize());
  std::vector<unsigned char> observed(staging_bytes);
  std::vector<reducer::DensePageTotals> observed_totals(pages);
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(observed.data(), d_packed.pointer,
                        observed.size(), cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(observed_totals.data(), d_totals.pointer,
                        observed_totals.size() * sizeof(observed_totals[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  if (summary.reducer_error_or != 0U ||
      summary.source_status_or != 0U || observed != expected ||
      std::memcmp(
          observed_totals.data(), expected_totals.data(),
          expected_totals.size() * sizeof(expected_totals[0])) != 0) {
    throw std::runtime_error(
        "TGDCSB03 device dense pack differs from host reference");
  }
  for (std::uint64_t ordinal = 0U; ordinal < states.size(); ++ordinal) {
    const std::uint64_t page =
        ordinal / reducer::kDensePageCharacters;
    const std::uint64_t local =
        ordinal % reducer::kDensePageCharacters;
    reducer::DenseDecodedRecord decoded{};
    if (!reducer::decodeDenseRecord(
            observed.data() + page * page_stride, local, sample_count,
            &decoded)) {
      throw std::runtime_error("TGDCSB03 dense record did not decode");
    }
    const auto& state = states[ordinal];
    if (decoded.has_determinate != state.has_determinate ||
        decoded.first_sign != state.first_sign ||
        decoded.last_sign != state.last_sign ||
        decoded.has_sparse !=
            static_cast<std::uint8_t>(
                state.ambiguity_range_count != 0U) ||
        decoded.transition_count != state.transition_count) {
      throw std::runtime_error(
          "TGDCSB03 decoded dense record differs");
    }
  }

  // The launch API rejects allocation/geometry substitutions synchronously.
  auto short_view = view;
  --short_view.packed_capacity_bytes;
  if (reducer::launchDenseTGDCSB03Pack(short_view) !=
      cudaErrorInvalidValue) {
    throw std::runtime_error(
        "undersized TGDCSB03 staging buffer was accepted");
  }
  auto wrong_stop = view;
  wrong_stop.stop_t_numerator += reducer::kSourceStepNumerator;
  if (reducer::launchDenseTGDCSB03Pack(wrong_stop) !=
      cudaErrorInvalidValue) {
    throw std::runtime_error(
        "substituted TGDCSB03 stop coordinate was accepted");
  }

  // A malformed state may still produce irrelevant staging bits, but the
  // independently checked stage summary must fail closed.
  auto hostile = states;
  hostile[0].first_t_numerator += reducer::kSourceStepNumerator;
  CUDA_CHECK(cudaMemcpy(d_states.pointer, hostile.data(),
                        hostile.size() * sizeof(hostile[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(reducer::launchDenseTGDCSB03Pack(view));
  CUDA_CHECK(cudaDeviceSynchronize());
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  if ((summary.reducer_error_or &
       reducer::kDensePackLayoutMismatch) == 0U) {
    throw std::runtime_error(
        "malformed TGDCSB03 dense state did not fail closed");
  }
  return {pages, staging_bytes, canonical_bytes};
}

void runInitializedSparseAppendKat(
    const std::vector<dl::ComplexInterval>& values,
    const std::vector<sc::Disk>& roots,
    const std::vector<sc::Disk>& factors,
    const std::vector<std::uint8_t>& parities,
    std::uint32_t samples, std::uint64_t first,
    const RunResult& expected) {
  const std::uint32_t characters =
      static_cast<std::uint32_t>(roots.size());
  const std::uint64_t prefix_rows = 2U;
  const std::uint64_t capacity =
      prefix_rows + expected.ranges.size();
  DeviceBuffer<dl::ComplexInterval> d_values(values.size());
  DeviceBuffer<sc::Disk> d_roots(roots.size());
  DeviceBuffer<sc::Disk> d_factors(factors.size());
  DeviceBuffer<std::uint8_t> d_parities(parities.size());
  DeviceBuffer<std::uint64_t> d_frequencies(characters);
  DeviceBuffer<reducer::PhaseState> d_states(expected.states.size());
  DeviceBuffer<std::uint64_t> d_offsets(expected.offsets.size());
  DeviceBuffer<reducer::AmbiguityRange> d_ranges(capacity);
  DeviceBuffer<std::uint64_t> d_ordinals(capacity);
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_values.pointer, values.data(),
                        values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots.pointer, roots.data(),
                        roots.size() * sizeof(roots[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_factors.pointer, factors.data(),
                        factors.size() * sizeof(factors[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_parities.pointer, parities.data(),
                        parities.size() * sizeof(parities[0]),
                        cudaMemcpyHostToDevice));
  std::vector<std::uint64_t> frequencies(characters);
  for (std::uint32_t character = 0U; character < characters; ++character) {
    frequencies[character] = character;
  }
  CUDA_CHECK(cudaMemcpy(d_frequencies.pointer, frequencies.data(),
                        frequencies.size() * sizeof(frequencies[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_states.pointer, expected.states.data(),
                        expected.states.size() * sizeof(expected.states[0]),
                        cudaMemcpyHostToDevice));
  auto absolute_offsets = expected.offsets;
  for (auto& offset : absolute_offsets) offset += prefix_rows;
  CUDA_CHECK(cudaMemcpy(d_offsets.pointer, absolute_offsets.data(),
                        absolute_offsets.size() *
                            sizeof(absolute_offsets[0]),
                        cudaMemcpyHostToDevice));
  std::vector<reducer::AmbiguityRange> ranges(
      capacity, {~std::uint64_t{0}, ~std::uint64_t{0}});
  ranges[0] = {42U, 43U};
  ranges[1] = {44U, 45U};
  std::vector<std::uint64_t> ordinals(
      capacity, ~std::uint64_t{0});
  ordinals[0] = 99U;
  ordinals[1] = 100U;
  CUDA_CHECK(cudaMemcpy(d_ranges.pointer, ranges.data(),
                        ranges.size() * sizeof(ranges[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_ordinals.pointer, ordinals.data(),
                        ordinals.size() * sizeof(ordinals[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                        sizeof(reducer::DeviceSummary)));
  const reducer::ResidentFrameView frame{
      5U,
      characters,
      samples,
      0U,
      characters,
      static_cast<std::uint64_t>(values.size()),
      first,
      reducer::kSourceStepNumerator,
      d_values.pointer,
      nullptr,
      d_roots.pointer,
      d_factors.pointer,
      d_parities.pointer,
      d_frequencies.pointer,
  };
  CUDA_CHECK(
      reducer::
          launchResidentTaggedAmbiguityRangeWriteIntoInitializedStorage(
              frame, d_states.pointer, d_offsets.pointer, capacity,
              d_ranges.pointer, d_ordinals.pointer, d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(ranges.data(), d_ranges.pointer,
                        ranges.size() * sizeof(ranges[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(ordinals.data(), d_ordinals.pointer,
                        ordinals.size() * sizeof(ordinals[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  if (summary.reducer_error_or != 0U ||
      ranges[0].first_t_numerator != 42U ||
      ranges[0].stop_t_numerator != 43U ||
      ranges[1].first_t_numerator != 44U ||
      ranges[1].stop_t_numerator != 45U ||
      ordinals[0] != 99U || ordinals[1] != 100U) {
    throw std::runtime_error(
        "preinitialized sparse append erased its existing prefix");
  }
  for (std::size_t index = 0U; index < expected.ranges.size(); ++index) {
    const std::size_t output = prefix_rows + index;
    if (std::memcmp(
            &ranges[output], &expected.ranges[index],
            sizeof(ranges[output])) != 0 ||
        ordinals[output] !=
            expected.range_primitive_ordinals[index]) {
      throw std::runtime_error(
          "preinitialized sparse append row differs");
    }
  }
}

void runExhaustiveTernaryStateKat() {
  constexpr std::uint32_t kSamples = 8U;
  constexpr std::uint32_t kCharacters = 6561U;  // 3^8
  std::vector<std::int8_t> patterns(
      static_cast<std::size_t>(kCharacters) * kSamples);
  for (std::uint32_t character = 0U; character < kCharacters;
       ++character) {
    std::uint32_t code = character;
    for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
      const std::uint32_t digit = code % 3U;
      code /= 3U;
      patterns[static_cast<std::size_t>(character) * kSamples + sample] =
          digit == 0U ? 0 : digit == 1U ? -1 : 1;
    }
  }
  const std::vector<sc::Disk> roots(kCharacters, pointDisk(1.0));
  std::vector<std::uint8_t> parities(kCharacters);
  for (std::uint32_t character = 0U; character < kCharacters;
       ++character) {
    parities[character] = static_cast<std::uint8_t>(character & 1U);
  }
  std::vector<RunResult> intervals(9U * 9U);
  auto at = [&](std::uint32_t begin,
                std::uint32_t stop) -> RunResult& {
    return intervals[begin * 9U + stop];
  };
  for (std::uint32_t begin = 0U; begin < kSamples; ++begin) {
    for (std::uint32_t stop = begin + 1U; stop <= kSamples; ++stop) {
      const std::uint32_t samples = stop - begin;
      std::vector<dl::ComplexInterval> values(
          static_cast<std::size_t>(samples) * kCharacters);
      for (std::uint32_t sample = begin; sample < stop; ++sample) {
        for (std::uint32_t character = 0U; character < kCharacters;
             ++character) {
          const std::int8_t sign =
              patterns[static_cast<std::size_t>(character) * kSamples +
                       sample];
          values[static_cast<std::size_t>(sample - begin) * kCharacters +
                 character] =
              sign == 0 ? pointBox(0.0) : pointBox(sign < 0 ? -2.0 : 2.0);
        }
      }
      at(begin, stop) = runReducer(
          values, std::vector<std::uint32_t>(values.size(), 0U), roots,
          std::vector<sc::Disk>(2U * samples, pointDisk(1.0)), parities,
          samples, begin * reducer::kSourceStepNumerator);
      if (at(begin, stop).summary.reducer_error_or != 0U ||
          at(begin, stop).summary.source_status_or != 0U) {
        throw std::runtime_error(
            "exhaustive ternary interval scan failed");
      }
    }
  }
  const auto& whole = at(0U, kSamples).states;
  for (const auto& state : whole) {
    if (!reducer::validPhaseState(state)) {
      throw std::runtime_error(
          "exhaustive whole ternary state is invalid");
    }
  }
  const DensePackKatStats dense =
      runDensePackKat(whole, kSamples, 0U);
  if (dense.pages != 2U || dense.staging_bytes != 7168U ||
      dense.canonical_bytes != 5741U) {
    throw std::runtime_error(
        "exhaustive TGDCSB03 dense pack dimensions differ");
  }
  const std::uint64_t dense_edge_sample_counts[] = {
      1U, 2U, 3U, 64U, 127988U,
      std::numeric_limits<std::uint32_t>::max()};
  for (const std::uint64_t sample_count :
       dense_edge_sample_counts) {
    std::vector<reducer::PhaseState> edge_states(37U);
    for (std::size_t index = 0U; index < edge_states.size(); ++index) {
      auto& state = edge_states[index];
      state.sample_count = sample_count;
      state.first_t_numerator = 200U;
      state.stop_t_numerator =
          200U + sample_count * reducer::kSourceStepNumerator;
      state.first_determinate_numerator = 200U;
      state.last_determinate_numerator =
          state.stop_t_numerator - reducer::kSourceStepNumerator;
      state.transition_count =
          index % 3U == 0U
              ? 0U
              : index % 3U == 1U
                    ? sample_count - 1U
                    : (sample_count - 1U) / 2U;
      state.t_step_numerator = reducer::kSourceStepNumerator;
      state.first_sign = index % 2U == 0U ? 1 : -1;
      state.last_sign =
          (state.transition_count & 1U) == 0U
              ? state.first_sign
              : static_cast<std::int8_t>(-state.first_sign);
      state.has_determinate = 1U;
    }
    (void)runDensePackKat(edge_states, sample_count, 200U);
  }
  for (std::uint32_t split = 1U; split < kSamples; ++split) {
    reducer::DeviceSummary summary{};
    const auto merged = combineOnDevice(
        at(0U, split).states, at(split, kSamples).states, &summary);
    if (summary.reducer_error_or != 0U || merged.size() != whole.size()) {
      throw std::runtime_error(
          "exhaustive two-way ternary merge failed");
    }
    for (std::uint32_t character = 0U; character < kCharacters;
         ++character) {
      if (!sameState(merged[character], whole[character])) {
        throw std::runtime_error(
            "exhaustive two-way ternary merge differs");
      }
    }
  }
  for (std::uint32_t first = 1U; first + 1U < kSamples; ++first) {
    for (std::uint32_t second = first + 1U; second < kSamples;
         ++second) {
      reducer::DeviceSummary ab_summary{};
      reducer::DeviceSummary bc_summary{};
      reducer::DeviceSummary left_summary{};
      reducer::DeviceSummary right_summary{};
      const auto ab = combineOnDevice(
          at(0U, first).states, at(first, second).states, &ab_summary);
      const auto bc = combineOnDevice(
          at(first, second).states, at(second, kSamples).states,
          &bc_summary);
      const auto left = combineOnDevice(
          ab, at(second, kSamples).states, &left_summary);
      const auto right = combineOnDevice(
          at(0U, first).states, bc, &right_summary);
      if (ab_summary.reducer_error_or != 0U ||
          bc_summary.reducer_error_or != 0U ||
          left_summary.reducer_error_or != 0U ||
          right_summary.reducer_error_or != 0U) {
        throw std::runtime_error(
            "exhaustive three-way ternary merge failed");
      }
      for (std::uint32_t character = 0U; character < kCharacters;
           ++character) {
        if (!sameState(left[character], right[character]) ||
            !sameState(left[character], whole[character])) {
          throw std::runtime_error(
              "exhaustive ternary merge associativity differs");
        }
      }
    }
  }
}

void requireRange(const reducer::AmbiguityRange& observed,
                  std::uint64_t first, std::uint64_t stop) {
  if (observed.first_t_numerator != first ||
      observed.stop_t_numerator != stop) {
    throw std::runtime_error("ambiguity range differs");
  }
}

void runRectangleCatalogKat() {
  const std::vector<dl::ComplexInterval> rectangles = {
      pointBox(1.0, 2.0),
      intervalBox(-2.0, -1.0, 3.0, 4.0),
  };
  DeviceBuffer<dl::ComplexInterval> d_rectangles(rectangles.size());
  DeviceBuffer<sc::Disk> d_disks(rectangles.size());
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_rectangles.pointer, rectangles.data(),
                        rectangles.size() * sizeof(rectangles[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                        sizeof(reducer::DeviceSummary)));
  CUDA_CHECK(reducer::launchRectangleCatalogToDisksIntoSummary(
      d_rectangles.pointer, rectangles.size(), d_disks.pointer,
      reducer::kInvalidRootDisk, d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  std::vector<sc::Disk> disks(rectangles.size());
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(disks.data(), d_disks.pointer,
                        disks.size() * sizeof(disks[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  if (summary.reducer_error_or != 0U ||
      disks[0].real != 1.0 || disks[0].imaginary != 2.0 ||
      disks[0].radius != 0.0 ||
      disks[1].real != -1.5 || disks[1].imaginary != 3.5 ||
      static_cast<long double>(disks[1].radius) *
              static_cast<long double>(disks[1].radius) <
          0.5L) {
    throw std::runtime_error(
        "directed rectangle catalog conversion differs");
  }
  const dl::ComplexInterval invalid =
      intervalBox(2.0, 1.0, 0.0, 0.0);
  CUDA_CHECK(cudaMemcpy(d_rectangles.pointer, &invalid, sizeof(invalid),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                        sizeof(reducer::DeviceSummary)));
  CUDA_CHECK(reducer::launchRectangleCatalogToDisksIntoSummary(
      d_rectangles.pointer, 1U, d_disks.pointer,
      reducer::kInvalidRootDisk, d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  CUDA_CHECK(cudaMemcpy(&disks[0], d_disks.pointer, sizeof(disks[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  const sc::Disk zero{};
  if ((summary.reducer_error_or &
       reducer::kInvalidRootDisk) == 0U ||
      std::memcmp(&disks[0], &zero, sizeof(zero)) != 0) {
    throw std::runtime_error(
        "invalid rectangle catalog row did not fail closed");
  }
  if (reducer::launchRectangleCatalogToDisksIntoSummary(
          d_rectangles.pointer, 1U, d_disks.pointer,
          reducer::kMalformedState, d_summary.pointer) !=
      cudaErrorInvalidValue) {
    throw std::runtime_error(
        "unscoped rectangle conversion error bit was accepted");
  }
}

void runBookerFmaIdentityKat() {
  // Exact binary64 adversary. Booker center arithmetic gives
  // 0xc01581f64d4dddd9; separately rounding a*b and then subtracting c*d
  // gives 0xc01581f64d4dddda. This locks the claimed implementation identity
  // to the explicit-FMA kernel rather than merely checking enclosure overlap.
  const sc::Disk left{
      doubleFromBits(0x3ffbb9146aa79987ULL),
      doubleFromBits(0x3ffdaea54c73a942ULL),
      0.0};
  const sc::Disk right{
      doubleFromBits(0xbffd340bd1f6f86cULL),
      doubleFromBits(0x3ff3193cee897110ULL),
      0.0};
  DeviceBuffer<sc::Disk> d_output(1U);
  evaluateBookerFmaProduct<<<1, 1>>>(left, right, d_output.pointer);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  sc::Disk observed{};
  CUDA_CHECK(cudaMemcpy(&observed, d_output.pointer, sizeof(observed),
                        cudaMemcpyDeviceToHost));
  if (doubleBits(observed.real) != 0xc01581f64d4dddd9ULL ||
      doubleBits(observed.real) == 0xc01581f64d4ddddaULL ||
      !std::isfinite(observed.radius) || observed.radius < 0.0) {
    throw std::runtime_error(
        "reducer disk product is not Booker explicit-FMA arithmetic");
  }
}

void runKnownAnswers() {
  constexpr std::uint32_t kCharacters = 3U;
  constexpr std::uint32_t kSamples = 8U;
  constexpr std::uint64_t kFirst = 100U;
  const std::int8_t patterns[kCharacters][kSamples] = {
      {-1, 0, 1, 1, 0, -1, -1, 1},
      {0, 0, 1, 0, -1, 0, 0, 0},
      {0, 0, 0, 0, 0, 0, 0, 0},
  };
  std::vector<dl::ComplexInterval> values(kCharacters * kSamples);
  for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
    for (std::uint32_t character = 0U; character < kCharacters; ++character) {
      const std::int8_t sign = patterns[character][sample];
      values[sample * kCharacters + character] =
          sign == 0 ? pointBox(0.0)
                    : intervalBox(
                          sign < 0 ? -2.01 : 1.99,
                          sign < 0 ? -1.99 : 2.01,
                          -0.005, 0.005);
    }
  }
  const std::vector<std::uint32_t> statuses(values.size(), 0U);
  const std::vector<sc::Disk> roots(kCharacters, pointDisk(1.0));
  const std::vector<sc::Disk> factors(2U * kSamples, pointDisk(1.0));
  const std::vector<std::uint8_t> parities = {0U, 1U, 0U};

  runRectangleCatalogKat();
  runBookerFmaIdentityKat();

  // The source factor seam uses Arb checkpoint/step/gamma disks and only
  // directed CUDA products between checkpoints.
  {
    const std::vector<sc::Disk> gamma(
        2U * kSamples, pointDisk(1.0));
    const std::vector<sc::Disk> checkpoints = {
        pointDisk(1.0), pointDisk(1.0)};
    std::vector<sc::Disk> expected_generated(gamma.size());
    const sc::Disk quarter_turns[4] = {
        pointDisk(1.0), pointDisk(0.0, 1.0),
        pointDisk(-1.0), pointDisk(0.0, -1.0)};
    for (std::uint32_t parity = 0U; parity < 2U; ++parity) {
      for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
        expected_generated[
            static_cast<std::size_t>(parity) * kSamples + sample] =
            quarter_turns[sample % 4U];
      }
    }
    DeviceBuffer<sc::Disk> d_gamma(gamma.size());
    DeviceBuffer<sc::Disk> d_checkpoints(checkpoints.size());
    DeviceBuffer<sc::Disk> d_generated(gamma.size());
    DeviceBuffer<reducer::DeviceSummary> d_factor_summary(1U);
    CUDA_CHECK(cudaMemcpy(d_gamma.pointer, gamma.data(),
                          gamma.size() * sizeof(gamma[0]),
                          cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_checkpoints.pointer, checkpoints.data(),
                          checkpoints.size() * sizeof(checkpoints[0]),
                          cudaMemcpyHostToDevice));
    const reducer::FactorRecurrenceView recurrence{
        d_gamma.pointer, d_checkpoints.pointer, pointDisk(0.0, 1.0),
        kSamples, 4U, 2U};
    CUDA_CHECK(reducer::launchParityFactorsFromCheckpoints(
        recurrence, d_generated.pointer, d_factor_summary.pointer));
    CUDA_CHECK(cudaDeviceSynchronize());
    std::vector<sc::Disk> generated(gamma.size());
    reducer::DeviceSummary factor_summary{};
    CUDA_CHECK(cudaMemcpy(generated.data(), d_generated.pointer,
                          generated.size() * sizeof(generated[0]),
                          cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(&factor_summary, d_factor_summary.pointer,
                          sizeof(factor_summary),
                          cudaMemcpyDeviceToHost));
    if (factor_summary.reducer_error_or != 0U ||
        std::memcmp(generated.data(), expected_generated.data(),
                    expected_generated.size() *
                        sizeof(expected_generated[0])) != 0) {
      throw std::runtime_error(
          "checkpointed parity-factor single-step recurrence differs");
    }
    auto too_few = recurrence;
    too_few.checkpoint_count = 1U;
    if (reducer::launchParityFactorsFromCheckpoints(
            too_few, d_generated.pointer, d_factor_summary.pointer) !=
        cudaErrorInvalidValue) {
      throw std::runtime_error(
          "short factor checkpoint roster did not fail closed");
    }
    auto too_many = recurrence;
    too_many.checkpoint_count = 3U;
    if (reducer::launchParityFactorsFromCheckpoints(
            too_many, d_generated.pointer, d_factor_summary.pointer) !=
        cudaErrorInvalidValue) {
      throw std::runtime_error(
          "extra factor checkpoint roster did not fail closed");
    }
    auto outside_source = recurrence;
    outside_source.sample_count =
        reducer::kSourceSampleCount + 1U;
    outside_source.checkpoint_span = outside_source.sample_count;
    outside_source.checkpoint_count = 1U;
    if (reducer::launchParityFactorsFromCheckpoints(
            outside_source, d_generated.pointer,
            d_factor_summary.pointer) != cudaErrorInvalidValue) {
      throw std::runtime_error(
          "factor recurrence accepted rows beyond the source domain");
    }
  }

  const RunResult whole =
      runReducer(values, statuses, roots, factors, parities, kSamples,
                 kFirst);
  if (whole.summary.source_status_or != 0U ||
      whole.summary.reducer_error_or != 0U ||
      whole.summary.ambiguity_range_count != 6U ||
      whole.ranges.size() != 6U) {
    throw std::runtime_error("whole reducer summary differs");
  }
  const reducer::PhaseState& first = whole.states[0];
  if (!reducer::validPhaseState(first) || first.sample_count != 8U ||
      first.first_determinate_numerator != 100U ||
      first.last_determinate_numerator != 135U ||
      first.first_sign != -1 || first.last_sign != 1 ||
      first.transition_count != 3U || first.ambiguity_count != 2U ||
      first.ambiguity_range_count != 2U ||
      first.leading_ambiguity_count != 0U ||
      first.trailing_ambiguity_count != 0U) {
    throw std::runtime_error("first character state differs");
  }
  const reducer::PhaseState& second = whole.states[1];
  if (!reducer::validPhaseState(second) ||
      second.first_determinate_numerator != 110U ||
      second.last_determinate_numerator != 120U ||
      second.first_sign != 1 || second.last_sign != -1 ||
      second.transition_count != 1U || second.ambiguity_count != 6U ||
      second.ambiguity_range_count != 3U ||
      second.leading_ambiguity_count != 2U ||
      second.trailing_ambiguity_count != 3U) {
    throw std::runtime_error("second character state differs");
  }
  const reducer::PhaseState& third = whole.states[2];
  if (!reducer::validPhaseState(third) ||
      third.has_determinate != 0U || third.first_sign != 0 ||
      third.last_sign != 0 || third.transition_count != 0U ||
      third.ambiguity_count != 8U ||
      third.ambiguity_range_count != 1U ||
      third.leading_ambiguity_count != 8U ||
      third.trailing_ambiguity_count != 8U) {
    throw std::runtime_error("all-ambiguous character state differs");
  }
  requireRange(whole.ranges[0], 105U, 110U);
  requireRange(whole.ranges[1], 120U, 125U);
  requireRange(whole.ranges[2], 100U, 110U);
  requireRange(whole.ranges[3], 115U, 120U);
  requireRange(whole.ranges[4], 125U, 140U);
  requireRange(whole.ranges[5], 100U, 140U);
  if (whole.range_primitive_ordinals !=
      std::vector<std::uint64_t>({0U, 0U, 1U, 1U, 1U, 2U})) {
    throw std::runtime_error(
        "sparse range primitive-ordinal tags differ");
  }
  runInitializedSparseAppendKat(
      values, roots, factors, parities, kSamples, kFirst, whole);

  auto sliceValues = [&](std::uint32_t begin,
                         std::uint32_t stop) {
    std::vector<dl::ComplexInterval> result;
    result.reserve(
        static_cast<std::size_t>(kCharacters) * (stop - begin));
    for (std::uint32_t sample = begin; sample < stop; ++sample) {
      for (std::uint32_t character = 0U; character < kCharacters;
           ++character) {
        result.push_back(values[sample * kCharacters + character]);
      }
    }
    return result;
  };
  auto runSlice = [&](std::uint32_t begin, std::uint32_t stop) {
    const auto slice = sliceValues(begin, stop);
    return runReducer(
        slice, std::vector<std::uint32_t>(slice.size(), 0U), roots,
        std::vector<sc::Disk>(2U * (stop - begin), pointDisk(1.0)),
        parities, stop - begin,
        kFirst + begin * reducer::kSourceStepNumerator);
  };
  const RunResult left = runSlice(0U, 4U);
  const RunResult right = runSlice(4U, 8U);
  reducer::DeviceSummary merge_summary{};
  const auto merged =
      combineOnDevice(left.states, right.states, &merge_summary);
  if (merge_summary.reducer_error_or != 0U) {
    throw std::runtime_error("adjacent device merge failed");
  }
  for (std::uint32_t character = 0U; character < kCharacters; ++character) {
    if (!sameState(merged[character], whole.states[character])) {
      throw std::runtime_error("two-slice merge differs from whole scan");
    }
  }

  // A hostile state cannot use one touching-boundary subtraction to
  // underflow an absent ambiguity-range count.
  {
    auto hostile = left.states;
    hostile[2].ambiguity_range_count = 0U;
    reducer::DeviceSummary hostile_summary{};
    (void)combineOnDevice(hostile, right.states, &hostile_summary);
    if ((hostile_summary.reducer_error_or &
         reducer::kMalformedState) == 0U) {
      throw std::runtime_error(
          "ambiguous state with zero ranges did not fail closed");
    }
    hostile = left.states;
    hostile[0].first_determinate_numerator +=
        reducer::kSourceStepNumerator;
    hostile_summary = {};
    (void)combineOnDevice(hostile, right.states, &hostile_summary);
    if ((hostile_summary.reducer_error_or &
         reducer::kMalformedState) == 0U) {
      throw std::runtime_error(
          "misbound determinate coordinate did not fail closed");
    }
  }

  const RunResult a = runSlice(0U, 2U);
  const RunResult b = runSlice(2U, 5U);
  const RunResult c = runSlice(5U, 8U);
  reducer::DeviceSummary merge_ab_summary{};
  reducer::DeviceSummary merge_bc_summary{};
  reducer::DeviceSummary left_assoc_summary{};
  reducer::DeviceSummary right_assoc_summary{};
  const auto ab = combineOnDevice(a.states, b.states, &merge_ab_summary);
  const auto bc = combineOnDevice(b.states, c.states, &merge_bc_summary);
  const auto ab_c =
      combineOnDevice(ab, c.states, &left_assoc_summary);
  const auto a_bc =
      combineOnDevice(a.states, bc, &right_assoc_summary);
  if (merge_ab_summary.reducer_error_or != 0U ||
      merge_bc_summary.reducer_error_or != 0U ||
      left_assoc_summary.reducer_error_or != 0U ||
      right_assoc_summary.reducer_error_or != 0U) {
    throw std::runtime_error("three-way merge reported an error");
  }
  for (std::uint32_t character = 0U; character < kCharacters; ++character) {
    if (!sameState(ab_c[character], a_bc[character]) ||
        !sameState(ab_c[character], whole.states[character])) {
      throw std::runtime_error("phase state merge is not associative");
    }
  }

  // A gap must fail rather than manufacture a boundary transition.
  auto gapped = right.states;
  gapped[0].first_t_numerator += reducer::kSourceStepNumerator;
  reducer::DeviceSummary gap_summary{};
  (void)combineOnDevice(left.states, gapped, &gap_summary);
  if ((gap_summary.reducer_error_or & reducer::kNonAdjacentState) == 0U &&
      (gap_summary.reducer_error_or & reducer::kMalformedState) == 0U) {
    throw std::runtime_error("gapped phase merge did not fail closed");
  }

  // The exact real boundary remains ambiguous.
  const RunResult boundary = runReducer(
      {pointBox(1.0)}, {0U}, {{0.5, 0.0, 0.5}},
      {pointDisk(1.0), pointDisk(1.0)}, {0U}, 1U, kFirst);
  if (boundary.summary.reducer_error_or != 0U ||
      boundary.states[0].ambiguity_count != 1U) {
    throw std::runtime_error("touching real boundary was not ambiguous");
  }

  // Every malformed or unbound arithmetic input fails closed.
  RunResult bad = runReducer({pointBox(1.0)}, {0x40U}, {pointDisk(1.0)},
                             {pointDisk(1.0), pointDisk(1.0)}, {0U}, 1U,
                             kFirst);
  if (bad.summary.source_status_or != 0x40U) {
    throw std::runtime_error("upstream FFT status escaped reduction");
  }
  bad = runReducer({pointBox(1.0)}, {0U}, {pointDisk(1.0)},
                   {pointDisk(1.0), pointDisk(1.0)}, {2U}, 1U, kFirst);
  if ((bad.summary.reducer_error_or & reducer::kInvalidParity) == 0U) {
    throw std::runtime_error("invalid parity did not fail closed");
  }
  bad = runReducer(
      {pointBox(1.0)}, {0U},
      {{std::numeric_limits<double>::quiet_NaN(), 0.0, 0.0}},
      {pointDisk(1.0), pointDisk(1.0)}, {0U}, 1U, kFirst);
  if ((bad.summary.reducer_error_or & reducer::kInvalidRootDisk) == 0U) {
    throw std::runtime_error("invalid root disk did not fail closed");
  }
  bad = runReducer({pointBox(1.0, 2.0)}, {0U}, {pointDisk(1.0)},
                   {pointDisk(1.0), pointDisk(1.0)}, {0U}, 1U, kFirst);
  if ((bad.summary.reducer_error_or &
       reducer::kCompletedDiskMissesRealAxis) == 0U) {
    throw std::runtime_error(
        "completed disk missing the real axis did not fail closed");
  }

  runExhaustiveTernaryStateKat();

  std::printf(
      "{\"algorithm\":\"tg-dirichlet-completed-sign-reducer-kat-v1\","
      "\"source_built_cuda\":true,"
      "\"directed_rectangle_to_disk\":true,"
      "\"validated_rectangle_catalog_conversion\":true,"
      "\"directed_completed_l_disk_products\":true,"
      "\"booker_explicit_fma_center_identity\":true,"
      "\"checkpointed_parity_factor_recurrence\":true,"
      "\"one_conductor_step_per_sample\":true,"
      "\"short_and_extra_checkpoint_rosters_rejected\":true,"
      "\"rows_beyond_source_domain_rejected\":true,"
      "\"null_per_item_status_production_mode\":true,"
      "\"strict_real_signs_and_ambiguity\":true,"
      "\"exact_maximal_ambiguity_ranges\":true,"
      "\"sparse_ranges_carry_primitive_ordinals\":true,"
      "\"preinitialized_sparse_append_preserves_prefix\":true,"
      "\"adjacent_two_phase_matches_whole\":true,"
      "\"three_way_dense_state_associative\":true,"
      "\"hostile_ambiguity_range_underflow_state_rejected\":true,"
      "\"misbound_determinate_coordinate_rejected\":true,"
      "\"tgdcsb03_dense_pack_byte_identical\":true,"
      "\"tgdcsb03_dense_pack_roundtrip\":true,"
      "\"tgdcsb03_zero_padding_emitted\":true,"
      "\"tgdcsb03_short_staging_rejected\":true,"
      "\"tgdcsb03_geometry_substitution_rejected\":true,"
      "\"tgdcsb03_malformed_state_rejected\":true,"
      "\"tgdcsb03_record_width_edge_cases\":6,"
      "\"exhaustive_ternary_length8_sequences\":6561,"
      "\"exhaustive_dense_pages\":2,"
      "\"exhaustive_dense_staging_bytes\":7168,"
      "\"exhaustive_dense_canonical_bytes\":5741,"
      "\"exhaustive_two_way_splits\":7,"
      "\"exhaustive_three_way_parenthesizations\":21,"
      "\"gap_rejected\":true,"
      "\"upstream_status_rejected\":true,"
      "\"invalid_parity_rejected\":true,"
      "\"invalid_root_rejected\":true,"
      "\"real_axis_miss_rejected\":true,"
      "\"raw_completed_l_stream_materialized\":false,"
      "\"source_scale_run_completed\":false,"
      "\"compiler_refinement_proved\":false,"
      "\"trusted_execution_attested\":false,"
      "\"zero_completeness_claimed\":false,"
      "\"external_atom_discharged\":false,"
      "\"character0_transitions\":3,"
      "\"character1_transitions\":1,"
      "\"ambiguity_ranges\":6}\n");
}

void runBenchmark(std::uint32_t characters, std::uint32_t samples,
                  std::uint32_t repetitions) {
  if (characters == 0U || samples == 0U ||
      samples > reducer::kMaximumFrameSamples || repetitions == 0U) {
    throw std::runtime_error("benchmark dimensions are invalid");
  }
  const std::uint64_t items =
      static_cast<std::uint64_t>(characters) * samples;
  if (items > 64U * 1024U * 1024U) {
    throw std::runtime_error("benchmark exceeds its bounded item cap");
  }
  std::vector<dl::ComplexInterval> values(items, pointBox(2.0));
  std::vector<sc::Disk> roots(characters, pointDisk(1.0));
  std::vector<sc::Disk> factors(2U * samples, pointDisk(1.0));
  std::vector<std::uint8_t> parities(characters, 0U);
  DeviceBuffer<dl::ComplexInterval> d_values(values.size());
  DeviceBuffer<sc::Disk> d_roots(roots.size());
  DeviceBuffer<sc::Disk> d_factors(factors.size());
  DeviceBuffer<std::uint8_t> d_parities(parities.size());
  DeviceBuffer<std::uint64_t> d_frequencies(characters);
  DeviceBuffer<reducer::PhaseState> d_states(characters);
  DeviceBuffer<std::uint64_t> d_counts(characters);
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_values.pointer, values.data(),
                        values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots.pointer, roots.data(),
                        roots.size() * sizeof(roots[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_factors.pointer, factors.data(),
                        factors.size() * sizeof(factors[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_parities.pointer, parities.data(),
                        parities.size() * sizeof(parities[0]),
                        cudaMemcpyHostToDevice));
  std::vector<std::uint64_t> frequencies(characters);
  for (std::uint32_t character = 0U; character < characters; ++character) {
    frequencies[character] = character;
  }
  CUDA_CHECK(cudaMemcpy(d_frequencies.pointer, frequencies.data(),
                        frequencies.size() * sizeof(frequencies[0]),
                        cudaMemcpyHostToDevice));
  cudaEvent_t start;
  cudaEvent_t stop;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  const std::uint32_t blocks =
      std::min<std::uint32_t>(4096U, (characters + 255U) / 256U);
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t repetition = 0U; repetition < repetitions;
       ++repetition) {
    CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                          sizeof(reducer::DeviceSummary)));
    reducer::reduceCompletedSigns<<<blocks, 256>>>(
        d_values.pointer, nullptr, 0U, d_roots.pointer,
        d_factors.pointer, d_parities.pointer, d_frequencies.pointer,
        characters, characters, samples, 0U,
        reducer::kSourceStepNumerator, d_states.pointer,
        d_counts.pointer, d_summary.pointer);
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));
  const double total_items =
      static_cast<double>(items) * repetitions;
  const double seconds = elapsed_ms * 1.0e-3;
  const std::uint64_t live_bytes =
      items * sizeof(dl::ComplexInterval) +
      static_cast<std::uint64_t>(characters) *
          (sizeof(sc::Disk) + sizeof(std::uint8_t) +
           sizeof(reducer::PhaseState) + sizeof(std::uint64_t)) +
      2ULL * samples * sizeof(sc::Disk);
  std::printf(
      "{\"algorithm\":\"tg-dirichlet-completed-sign-reducer-benchmark-v1\","
      "\"device\":\"%s\",\"characters\":%u,\"samples\":%u,"
      "\"repetitions\":%u,\"items_per_repetition\":%llu,"
      "\"elapsed_ms\":%.6f,\"items_per_second\":%.6e,"
      "\"modeled_live_bytes\":%llu,\"source_status_or\":%u,"
      "\"reducer_error_or\":%u,\"source_projection\":false}\n",
      properties.name, characters, samples, repetitions,
      static_cast<unsigned long long>(items), elapsed_ms,
      total_items / seconds, static_cast<unsigned long long>(live_bytes),
      summary.source_status_or, summary.reducer_error_or);
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaEventDestroy(start));
}

void runFactorRecurrenceBenchmark(
    std::uint32_t samples, std::uint32_t repetitions) {
  constexpr std::uint32_t kCheckpointSpan = 4096U;
  constexpr std::uint32_t kSourceRows = 127988U;
  if (samples == 0U || samples > kSourceRows || repetitions == 0U) {
    throw std::runtime_error(
        "factor recurrence benchmark dimensions are invalid");
  }
  const std::uint32_t checkpoint_count =
      1U + (samples - 1U) / kCheckpointSpan;
  const std::vector<sc::Disk> gamma(
      2ULL * samples, pointDisk(1.0));
  const std::vector<sc::Disk> checkpoints(
      checkpoint_count, pointDisk(1.0));
  DeviceBuffer<sc::Disk> d_gamma(gamma.size());
  DeviceBuffer<sc::Disk> d_checkpoints(checkpoints.size());
  DeviceBuffer<sc::Disk> d_factors(gamma.size());
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(
      d_gamma.pointer, gamma.data(), gamma.size() * sizeof(gamma[0]),
      cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(
      d_checkpoints.pointer, checkpoints.data(),
      checkpoints.size() * sizeof(checkpoints[0]),
      cudaMemcpyHostToDevice));
  const reducer::FactorRecurrenceView recurrence{
      d_gamma.pointer,
      d_checkpoints.pointer,
      pointDisk(1.0),
      samples,
      kCheckpointSpan,
      checkpoint_count,
  };
  CUDA_CHECK(reducer::launchParityFactorsFromCheckpoints(
      recurrence, d_factors.pointer, d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  cudaEvent_t start;
  cudaEvent_t stop;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t repetition = 0U; repetition < repetitions;
       ++repetition) {
    CUDA_CHECK(reducer::launchParityFactorsFromCheckpoints(
        recurrence, d_factors.pointer, d_summary.pointer));
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(
      &summary, d_summary.pointer, sizeof(summary),
      cudaMemcpyDeviceToHost));
  if (summary.source_status_or != 0U ||
      summary.reducer_error_or != 0U ||
      summary.ambiguity_range_count != 0U) {
    throw std::runtime_error(
        "factor recurrence benchmark failed closed");
  }
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));
  const double generated =
      2.0 * static_cast<double>(samples) * repetitions;
  const double seconds = static_cast<double>(elapsed_ms) * 1.0e-3;
  const std::uint64_t resident_bytes =
      static_cast<std::uint64_t>(gamma.size()) * sizeof(sc::Disk) * 2ULL +
      static_cast<std::uint64_t>(checkpoints.size()) * sizeof(sc::Disk) +
      sizeof(reducer::DeviceSummary);
  std::printf(
      "{\"algorithm\":"
      "\"tg-dirichlet-completed-factor-recurrence-benchmark-v1\","
      "\"device\":\"%s\",\"samples\":%u,\"checkpoint_span\":%u,"
      "\"checkpoint_count\":%u,\"repetitions\":%u,"
      "\"generated_disks_per_repetition\":%llu,"
      "\"elapsed_ms\":%.6f,\"generated_disks_per_second\":%.6e,"
      "\"resident_bytes\":%llu,\"source_status_or\":%u,"
      "\"reducer_error_or\":%u,\"source_projection\":false}\n",
      properties.name, samples, kCheckpointSpan, checkpoint_count,
      repetitions,
      static_cast<unsigned long long>(2ULL * samples), elapsed_ms,
      generated / seconds,
      static_cast<unsigned long long>(resident_bytes),
      summary.source_status_or, summary.reducer_error_or);
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaEventDestroy(start));
}

void runDensePackBenchmark(
    std::uint32_t characters, std::uint32_t samples,
    std::uint32_t repetitions) {
  if (characters == 0U || characters > reducer::kMaximumModulus ||
      samples == 0U || repetitions == 0U) {
    throw std::runtime_error(
        "dense-pack benchmark dimensions are invalid");
  }
  reducer::PhaseState state{};
  state.sample_count = samples;
  state.first_t_numerator = 0U;
  state.stop_t_numerator =
      static_cast<std::uint64_t>(samples) *
      reducer::kSourceStepNumerator;
  state.first_determinate_numerator = 0U;
  state.last_determinate_numerator =
      state.stop_t_numerator - reducer::kSourceStepNumerator;
  state.t_step_numerator = reducer::kSourceStepNumerator;
  state.first_sign = 1;
  state.last_sign = 1;
  state.has_determinate = 1U;
  if (!reducer::validPhaseState(state)) {
    throw std::runtime_error(
        "dense-pack benchmark state is invalid");
  }
  std::vector<reducer::PhaseState> states(characters, state);
  const std::uint64_t pages = reducer::densePageCount(characters);
  const std::uint64_t page_stride =
      reducer::densePageStrideBytes(samples);
  const std::uint64_t staging_bytes = pages * page_stride;
  const std::uint32_t record_width =
      reducer::denseRecordWidth(samples);
  const std::uint64_t full_pages =
      characters / reducer::kDensePageCharacters;
  const std::uint64_t remainder =
      characters % reducer::kDensePageCharacters;
  const std::uint64_t canonical_bytes =
      full_pages * page_stride +
      (remainder == 0U
           ? 0U
           : (remainder * record_width + 7U) / 8U);
  DeviceBuffer<reducer::PhaseState> d_states(states.size());
  DeviceBuffer<unsigned char> d_packed(staging_bytes);
  DeviceBuffer<reducer::DensePageTotals> d_totals(pages);
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_states.pointer, states.data(),
                        states.size() * sizeof(states[0]),
                        cudaMemcpyHostToDevice));
  const reducer::DensePackView view{
      d_states.pointer,
      characters,
      samples,
      0U,
      state.stop_t_numerator,
      reducer::kSourceStepNumerator,
      d_packed.pointer,
      staging_bytes,
      d_totals.pointer,
      pages,
      d_summary.pointer,
  };
  CUDA_CHECK(reducer::launchDenseTGDCSB03Pack(view));
  CUDA_CHECK(cudaDeviceSynchronize());
  cudaEvent_t start;
  cudaEvent_t stop;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t repetition = 0U; repetition < repetitions;
       ++repetition) {
    CUDA_CHECK(reducer::launchDenseTGDCSB03Pack(view));
  }
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  if (summary.reducer_error_or != 0U ||
      summary.source_status_or != 0U) {
    throw std::runtime_error(
        "dense-pack benchmark failed closed");
  }
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));
  const double seconds = elapsed_ms * 1.0e-3;
  const double packed_characters =
      static_cast<double>(characters) * repetitions;
  std::printf(
      "{\"algorithm\":\"tg-dirichlet-tgdcsb03-device-pack-"
      "benchmark-v1\",\"device\":\"%s\",\"characters\":%u,"
      "\"samples\":%u,\"transition_width_bits\":%u,"
      "\"record_width_bits\":%u,\"pages\":%llu,"
      "\"repetitions\":%u,\"elapsed_ms\":%.6f,"
      "\"characters_per_second\":%.6e,"
      "\"device_staging_bytes\":%llu,"
      "\"canonical_dense_bytes\":%llu,"
      "\"internal_phase_state_bytes_not_transported\":%llu,"
      "\"source_status_or\":%u,\"reducer_error_or\":%u,"
      "\"source_projection\":false}\n",
      properties.name, characters, samples,
      reducer::denseCountWidth(samples), record_width,
      static_cast<unsigned long long>(pages), repetitions, elapsed_ms,
      packed_characters / seconds,
      static_cast<unsigned long long>(staging_bytes),
      static_cast<unsigned long long>(canonical_bytes),
      static_cast<unsigned long long>(
          static_cast<std::uint64_t>(characters) *
          sizeof(reducer::PhaseState)),
      summary.source_status_or, summary.reducer_error_or);
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaEventDestroy(start));
}

template <typename T>
std::vector<T> readArray(std::FILE* input, std::size_t count,
                         const char* label) {
  std::vector<T> result(count);
  if (count != 0U &&
      std::fread(result.data(), sizeof(T), count, input) != count) {
    throw std::runtime_error(std::string("truncated ") + label);
  }
  return result;
}

void runQualification(const char* input_path) {
  std::FILE* input = std::fopen(input_path, "rb");
  if (input == nullptr) {
    throw std::runtime_error("cannot open qualification input");
  }
  char magic[8]{};
  std::uint32_t words[6]{};
  std::uint64_t stride = 0U;
  if (std::fread(magic, 1U, sizeof(magic), input) != sizeof(magic) ||
      std::fread(words, sizeof(words[0]), 6U, input) != 6U ||
      std::fread(&stride, sizeof(stride), 1U, input) != 1U ||
      std::memcmp(magic, "TGDCQAI1", 8U) != 0 ||
      words[0] != 2U || words[1] == 0U || words[2] == 0U ||
      words[2] > 4096U || words[3] != 0U ||
      words[4] == 0U ||
      words[5] != 1U + (words[2] - 1U) / words[4] ||
      stride < words[1]) {
    std::fclose(input);
    throw std::runtime_error("qualification header differs");
  }
  const std::uint32_t characters = words[1];
  const std::uint32_t samples = words[2];
  const std::uint32_t checkpoint_span = words[4];
  const std::uint32_t checkpoint_count = words[5];
  std::uint64_t value_count = 0U;
  if (!reducer::checkedMul(samples, stride, &value_count) ||
      value_count > 4U * 1024U * 1024U) {
    std::fclose(input);
    throw std::runtime_error("qualification input exceeds bounded cap");
  }
  const auto roots = readArray<sc::Disk>(
      input, characters, "qualification roots");
  const auto gamma = readArray<sc::Disk>(
      input, 2U * samples, "qualification gamma rows");
  const auto checkpoints = readArray<sc::Disk>(
      input, checkpoint_count, "qualification conductor checkpoints");
  const auto step_rows = readArray<sc::Disk>(
      input, 1U, "qualification conductor step");
  const auto parities = readArray<std::uint8_t>(
      input, characters, "qualification parities");
  const auto values = readArray<dl::ComplexInterval>(
      input, value_count, "qualification L rectangles");
  if (std::fgetc(input) != EOF) {
    std::fclose(input);
    throw std::runtime_error("qualification input has trailing bytes");
  }
  std::fclose(input);

  DeviceBuffer<dl::ComplexInterval> d_values(values.size());
  DeviceBuffer<sc::Disk> d_roots(roots.size());
  DeviceBuffer<sc::Disk> d_gamma(gamma.size());
  DeviceBuffer<sc::Disk> d_checkpoints(checkpoints.size());
  DeviceBuffer<sc::Disk> d_factors(gamma.size());
  DeviceBuffer<std::uint8_t> d_parities(parities.size());
  DeviceBuffer<std::uint64_t> d_frequencies(characters);
  DeviceBuffer<std::int8_t> d_codes(
      static_cast<std::size_t>(characters) * samples);
  DeviceBuffer<reducer::DeviceSummary> d_summary(1U);
  CUDA_CHECK(cudaMemcpy(d_values.pointer, values.data(),
                        values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_roots.pointer, roots.data(),
                        roots.size() * sizeof(roots[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_gamma.pointer, gamma.data(),
                        gamma.size() * sizeof(gamma[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_checkpoints.pointer, checkpoints.data(),
                        checkpoints.size() * sizeof(checkpoints[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(d_parities.pointer, parities.data(),
                        parities.size() * sizeof(parities[0]),
                        cudaMemcpyHostToDevice));
  std::vector<std::uint64_t> frequencies(characters);
  for (std::uint32_t character = 0U; character < characters; ++character) {
    frequencies[character] = character;
  }
  CUDA_CHECK(cudaMemcpy(d_frequencies.pointer, frequencies.data(),
                        frequencies.size() * sizeof(frequencies[0]),
                        cudaMemcpyHostToDevice));
  const reducer::FactorRecurrenceView recurrence{
      d_gamma.pointer,
      d_checkpoints.pointer,
      step_rows[0],
      samples,
      checkpoint_span,
      checkpoint_count,
  };
  CUDA_CHECK(reducer::launchParityFactorsFromCheckpoints(
      recurrence, d_factors.pointer, d_summary.pointer));
  CUDA_CHECK(cudaDeviceSynchronize());
  reducer::DeviceSummary factor_summary{};
  CUDA_CHECK(cudaMemcpy(&factor_summary, d_summary.pointer,
                        sizeof(factor_summary), cudaMemcpyDeviceToHost));
  if (factor_summary.source_status_or != 0U ||
      factor_summary.reducer_error_or != 0U) {
    throw std::runtime_error(
        "qualification factor recurrence failed closed");
  }
  CUDA_CHECK(cudaMemset(d_summary.pointer, 0,
                        sizeof(reducer::DeviceSummary)));
  const std::uint64_t item_count =
      static_cast<std::uint64_t>(characters) * samples;
  const std::uint32_t blocks = static_cast<std::uint32_t>(
      std::min<std::uint64_t>(4096U, (item_count + 255U) / 256U));
  reducer::classifyCompletedSignsForQualification<<<blocks, 256>>>(
      d_values.pointer, nullptr, 0U, d_roots.pointer, d_factors.pointer,
      d_parities.pointer, d_frequencies.pointer, stride, characters,
      samples, d_codes.pointer, d_summary.pointer);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  std::vector<std::int8_t> codes(item_count);
  reducer::DeviceSummary summary{};
  CUDA_CHECK(cudaMemcpy(codes.data(), d_codes.pointer,
                        codes.size() * sizeof(codes[0]),
                        cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaMemcpy(&summary, d_summary.pointer, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  std::printf(
      "{\"algorithm\":\"tg-dirichlet-completed-sign-reducer-"
      "arb-qualification-adapter-v1\",\"characters\":%u,\"samples\":%u,"
      "\"checkpoint_span\":%u,\"checkpoint_count\":%u,"
      "\"gpu_factor_recurrence\":true,"
      "\"conductor_step_t_numerator\":5,"
      "\"conductor_step_t_denominator\":128,"
      "\"conductor_step_applications_per_sample\":1,"
      "\"source_status_or\":%u,\"reducer_error_or\":%u,"
      "\"raw_codes_production_path\":false,\"codes\":[",
      characters, samples, checkpoint_span, checkpoint_count,
      summary.source_status_or,
      summary.reducer_error_or);
  for (std::size_t index = 0U; index < codes.size(); ++index) {
    if (index != 0U) std::putchar(',');
    std::printf("%d", static_cast<int>(codes[index]));
  }
  std::printf(
      "],\"source_scale_run_completed\":false,"
      "\"compiler_refinement_proved\":false,"
      "\"trusted_execution_attested\":false,"
      "\"external_atom_discharged\":false}\n");
}

std::uint32_t parsePositive(const char* raw, const char* label) {
  char* end = nullptr;
  const unsigned long value = std::strtoul(raw, &end, 10);
  if (end == raw || *end != '\0' || value == 0U ||
      value > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error(std::string("invalid ") + label);
  }
  return static_cast<std::uint32_t>(value);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 1) {
      runKnownAnswers();
      return 0;
    }
    if (argc == 5 && std::string(argv[1]) == "--benchmark") {
      runBenchmark(parsePositive(argv[2], "character count"),
                   parsePositive(argv[3], "sample count"),
                   parsePositive(argv[4], "repetition count"));
      return 0;
    }
    if (argc == 5 &&
        std::string(argv[1]) == "--benchmark-dense-pack") {
      runDensePackBenchmark(
          parsePositive(argv[2], "character count"),
          parsePositive(argv[3], "sample count"),
          parsePositive(argv[4], "repetition count"));
      return 0;
    }
    if (argc == 4 &&
        std::string(argv[1]) ==
            "--benchmark-factor-recurrence") {
      runFactorRecurrenceBenchmark(
          parsePositive(argv[2], "sample count"),
          parsePositive(argv[3], "repetition count"));
      return 0;
    }
    if (argc == 3 && std::string(argv[1]) == "--qualification") {
      runQualification(argv[2]);
      return 0;
    }
    std::fprintf(
        stderr,
        "usage: %s [--benchmark CHARACTERS SAMPLES REPETITIONS | "
        "--benchmark-dense-pack CHARACTERS SAMPLES REPETITIONS | "
        "--benchmark-factor-recurrence SAMPLES REPETITIONS | "
        "--qualification INPUT]\n",
        argv[0]);
    return 1;
  } catch (const std::exception& error) {
    std::fprintf(stderr,
                 "tg_dirichlet_completed_sign_reducer_kat: %s\n",
                 error.what());
    return 2;
  }
}

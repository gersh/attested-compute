// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_dirichlet_resident_phase_accumulator.cuh"

#include <cuda_runtime.h>

#include <chrono>
#include <cstdlib>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace accumulator =
    sparkinterval::tg::dirichlet_resident_phase_accumulator;
namespace reducer =
    sparkinterval::tg::dirichlet_completed_sign_reducer;
namespace lattice = sparkinterval::tg::dirichlet_lattice;
namespace certified =
    sparkinterval::tg::dirichlet_booker_smallq_certified;

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                       \
    if (status_ != cudaSuccess) {                                             \
      throw std::runtime_error(                                               \
          std::string(#call) + ": " + cudaGetErrorString(status_));           \
    }                                                                        \
  } while (false)

template <typename T>
class DeviceBuffer {
 public:
  explicit DeviceBuffer(std::size_t count) : count_(count) {
    CUDA_CHECK(cudaMalloc(&pointer_, count_ * sizeof(T)));
  }
  ~DeviceBuffer() { cudaFree(pointer_); }
  DeviceBuffer(const DeviceBuffer&) = delete;
  DeviceBuffer& operator=(const DeviceBuffer&) = delete;
  T* get() const { return pointer_; }

 private:
  T* pointer_ = nullptr;
  std::size_t count_ = 0U;
};

lattice::ComplexInterval exactRectangle(double value) {
  return {{value, value}, {0.0, 0.0}};
}

reducer::ResidentFrameView makeFrame(
    std::uint64_t first_t_numerator,
    const lattice::ComplexInterval* values,
    const certified::Disk* roots,
    const certified::Disk* factors,
    const std::uint8_t* parities,
    const std::uint64_t* frequencies) {
  return {
      7U,
      2U,
      3U,
      0U,
      2U,
      6U,
      first_t_numerator,
      reducer::kSourceStepNumerator,
      values,
      nullptr,
      roots,
      factors,
      parities,
      frequencies,
  };
}

void runSuccessfulTwoFrameKat(
    const reducer::ResidentFrameView& first,
    const reducer::ResidentFrameView& second) {
  const accumulator::PhaseAccumulatorConfig config{
      7U, 2U, 6U, 0U, 30U, reducer::kSourceStepNumerator, 8U};
  accumulator::ResidentPhaseAccumulator phase(config);
  CUDA_CHECK(phase.enqueueFrame(first));
  CUDA_CHECK(phase.enqueueFrame(second));
  if (phase.frameCount() != 2U ||
      phase.accumulatedSampleCount() != 6U) {
    throw std::runtime_error("resident phase host progression differs");
  }
  const accumulator::PhaseCheckpoint checkpoint = phase.checkpoint();
  if (checkpoint.phase_state_device_to_host_bytes != 0U ||
      checkpoint.per_frame_count_device_to_host_bytes != 0U ||
      checkpoint.raw_sparse_range_count != 4U ||
      checkpoint.coalesced_sparse_range_count != 2U ||
      checkpoint.reduction_summary.ambiguity_range_count != 4U ||
      checkpoint.pages.size() != 1U ||
      checkpoint.pages[0].dense !=
          std::vector<unsigned char>({0x9dU, 0x0eU}) ||
      checkpoint.pages[0].totals.ordinal_start != 0U ||
      checkpoint.pages[0].totals.character_count != 2U ||
      checkpoint.pages[0].totals.dense_bytes != 2U ||
      checkpoint.pages[0].totals.transition_count != 2U ||
      checkpoint.pages[0].totals.ambiguity_sample_count != 8U ||
      checkpoint.pages[0].totals.ambiguity_range_count != 2U ||
      checkpoint.pages[0].totals.sparse_character_count != 2U ||
      checkpoint.pages[0].totals.count_width != 3U ||
      checkpoint.pages[0].totals.record_width != 7U ||
      checkpoint.pages[0].totals.status_or != 0U ||
      checkpoint.ambiguity_ranges.size() != 2U ||
      checkpoint.ambiguity_ranges[0].primitive_ordinal != 0U ||
      checkpoint.ambiguity_ranges[0].range.first_t_numerator != 5U ||
      checkpoint.ambiguity_ranges[0].range.stop_t_numerator != 25U ||
      checkpoint.ambiguity_ranges[1].primitive_ordinal != 1U ||
      checkpoint.ambiguity_ranges[1].range.first_t_numerator != 5U ||
      checkpoint.ambiguity_ranges[1].range.stop_t_numerator != 25U ||
      checkpoint.device_to_host_bytes != 3784U ||
      checkpoint.dense_staging_device_to_host_bytes != 3584U ||
      checkpoint.canonical_dense_bytes != 2U ||
      checkpoint.dense_device_to_host_copy_count != 1U) {
    throw std::runtime_error(
        "resident phase compact checkpoint differs");
  }
}

void runSparseCapacityFailureKat(
    const reducer::ResidentFrameView& first,
    const reducer::ResidentFrameView& second) {
  const accumulator::PhaseAccumulatorConfig config{
      7U, 2U, 6U, 0U, 30U, reducer::kSourceStepNumerator, 1U};
  accumulator::ResidentPhaseAccumulator phase(config);
  CUDA_CHECK(phase.enqueueFrame(first));
  CUDA_CHECK(phase.enqueueFrame(second));
  bool rejected = false;
  try {
    static_cast<void>(phase.checkpoint());
  } catch (const std::runtime_error&) {
    rejected = true;
  }
  if (!rejected) {
    throw std::runtime_error(
        "resident phase accepted exhausted sparse capacity");
  }
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

void runBenchmark(
    std::uint32_t characters, std::uint32_t frame_samples,
    std::uint32_t frames) {
  if (characters > reducer::kMaximumModulus ||
      frame_samples > reducer::kMaximumFrameSamples ||
      static_cast<std::uint64_t>(frame_samples) * frames >
          reducer::kMaximumPackedSamples) {
    throw std::runtime_error("resident phase benchmark exceeds bounds");
  }
  const std::uint64_t values_count =
      static_cast<std::uint64_t>(characters) * frame_samples;
  std::vector<lattice::ComplexInterval> values(
      static_cast<std::size_t>(values_count), exactRectangle(2.0));
  std::vector<certified::Disk> roots(
      characters, certified::Disk{1.0, 0.0, 0.0});
  std::vector<certified::Disk> factors(
      2U * frame_samples, certified::Disk{1.0, 0.0, 0.0});
  std::vector<std::uint8_t> parities(characters);
  std::vector<std::uint64_t> frequencies(characters);
  for (std::uint32_t character = 0U; character < characters;
       ++character) {
    parities[character] =
        static_cast<std::uint8_t>(character & 1U);
    frequencies[character] = character;
  }
  DeviceBuffer<lattice::ComplexInterval> d_values(values.size());
  DeviceBuffer<certified::Disk> d_roots(roots.size());
  DeviceBuffer<certified::Disk> d_factors(factors.size());
  DeviceBuffer<std::uint8_t> d_parities(parities.size());
  DeviceBuffer<std::uint64_t> d_frequencies(frequencies.size());
  CUDA_CHECK(cudaMemcpy(
      d_values.get(), values.data(), values.size() * sizeof(values[0]),
      cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(
      d_roots.get(), roots.data(), roots.size() * sizeof(roots[0]),
      cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(
      d_factors.get(), factors.data(),
      factors.size() * sizeof(factors[0]), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(
      d_parities.get(), parities.data(),
      parities.size() * sizeof(parities[0]), cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(
      d_frequencies.get(), frequencies.data(),
      frequencies.size() * sizeof(frequencies[0]),
      cudaMemcpyHostToDevice));
  const std::uint64_t total_samples =
      static_cast<std::uint64_t>(frame_samples) * frames;
  const accumulator::PhaseAccumulatorConfig config{
      reducer::kMaximumModulus,
      characters,
      total_samples,
      0U,
      total_samples * reducer::kSourceStepNumerator,
      reducer::kSourceStepNumerator,
      1U,
  };
  accumulator::ResidentPhaseAccumulator phase(config);
  cudaEvent_t start;
  cudaEvent_t stop;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  CUDA_CHECK(cudaEventRecord(start));
  for (std::uint32_t index = 0U; index < frames; ++index) {
    const reducer::ResidentFrameView frame{
        reducer::kMaximumModulus,
        characters,
        frame_samples,
        0U,
        characters,
        values_count,
        static_cast<std::uint64_t>(index) * frame_samples *
            reducer::kSourceStepNumerator,
        reducer::kSourceStepNumerator,
        d_values.get(),
        nullptr,
        d_roots.get(),
        d_factors.get(),
        d_parities.get(),
        d_frequencies.get(),
    };
    CUDA_CHECK(phase.enqueueFrame(frame));
  }
  CUDA_CHECK(phase.finalize());
  CUDA_CHECK(cudaEventRecord(stop));
  CUDA_CHECK(cudaEventSynchronize(stop));
  float elapsed_ms = 0.0F;
  CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, start, stop));
  const auto checkpoint_start = std::chrono::steady_clock::now();
  const accumulator::PhaseCheckpoint checkpoint = phase.checkpoint();
  const auto checkpoint_stop = std::chrono::steady_clock::now();
  const double checkpoint_elapsed_ms =
      std::chrono::duration<double, std::milli>(
          checkpoint_stop - checkpoint_start)
          .count();
  if (checkpoint.raw_sparse_range_count != 0U ||
      checkpoint.coalesced_sparse_range_count != 0U ||
      checkpoint.phase_state_device_to_host_bytes != 0U ||
      checkpoint.per_frame_count_device_to_host_bytes != 0U) {
    throw std::runtime_error(
        "resident phase benchmark compact result differs");
  }
  cudaDeviceProp properties{};
  CUDA_CHECK(cudaGetDeviceProperties(&properties, 0));
  const double decisions =
      static_cast<double>(characters) * total_samples;
  const double seconds = static_cast<double>(elapsed_ms) * 1.0e-3;
  std::printf(
      "{\"algorithm\":\"tg-dirichlet-resident-phase-accumulator-"
      "benchmark-v1\",\"device\":\"%s\",\"characters\":%u,"
      "\"frame_samples\":%u,\"frames\":%u,"
      "\"total_samples\":%llu,\"decisions\":%.0f,"
      "\"elapsed_ms\":%.6f,\"decisions_per_second\":%.6e,"
      "\"checkpoint_elapsed_ms\":%.6f,"
      "\"resident_accumulator_bytes\":%llu,"
      "\"cub_scan_temporary_bytes\":%llu,"
      "\"compact_checkpoint_device_to_host_bytes\":%llu,"
      "\"dense_staging_device_to_host_bytes\":%llu,"
      "\"canonical_dense_bytes\":%llu,"
      "\"dense_device_to_host_copy_count\":%u,"
      "\"phase_state_device_to_host_bytes\":0,"
      "\"per_frame_count_device_to_host_bytes\":0,"
      "\"source_projection\":false}\n",
      properties.name, characters, frame_samples, frames,
      static_cast<unsigned long long>(total_samples), decisions,
      elapsed_ms, decisions / seconds, checkpoint_elapsed_ms,
      static_cast<unsigned long long>(phase.residentBytes()),
      static_cast<unsigned long long>(phase.cubScanTemporaryBytes()),
      static_cast<unsigned long long>(checkpoint.device_to_host_bytes),
      static_cast<unsigned long long>(
          checkpoint.dense_staging_device_to_host_bytes),
      static_cast<unsigned long long>(checkpoint.canonical_dense_bytes),
      checkpoint.dense_device_to_host_copy_count);
  CUDA_CHECK(cudaEventDestroy(stop));
  CUDA_CHECK(cudaEventDestroy(start));
}

int main(int argc, char** argv) {
  try {
    CUDA_CHECK(cudaSetDevice(0));
    if (argc == 5 && std::string(argv[1]) == "--benchmark") {
      runBenchmark(
          parsePositive(argv[2], "character count"),
          parsePositive(argv[3], "frame samples"),
          parsePositive(argv[4], "frame count"));
      return 0;
    }
    if (argc != 1) {
      throw std::runtime_error(
          "usage: resident-phase-accumulator-kat "
          "[--benchmark CHARACTERS FRAME_SAMPLES FRAMES]");
    }
    const std::vector<lattice::ComplexInterval> first_values{
        exactRectangle(-2.0), exactRectangle(-2.0),
        exactRectangle(0.0), exactRectangle(0.0),
        exactRectangle(0.0), exactRectangle(0.0),
    };
    const std::vector<lattice::ComplexInterval> second_values{
        exactRectangle(0.0), exactRectangle(0.0),
        exactRectangle(0.0), exactRectangle(0.0),
        exactRectangle(2.0), exactRectangle(2.0),
    };
    const std::vector<certified::Disk> roots{
        {1.0, 0.0, 0.0}, {1.0, 0.0, 0.0}};
    const std::vector<certified::Disk> factors(
        6U, certified::Disk{1.0, 0.0, 0.0});
    const std::vector<std::uint8_t> parities{0U, 1U};
    const std::vector<std::uint64_t> frequencies{0U, 1U};
    DeviceBuffer<lattice::ComplexInterval> d_first(first_values.size());
    DeviceBuffer<lattice::ComplexInterval> d_second(second_values.size());
    DeviceBuffer<certified::Disk> d_roots(roots.size());
    DeviceBuffer<certified::Disk> d_factors(factors.size());
    DeviceBuffer<std::uint8_t> d_parities(parities.size());
    DeviceBuffer<std::uint64_t> d_frequencies(frequencies.size());
    CUDA_CHECK(cudaMemcpy(
        d_first.get(), first_values.data(),
        first_values.size() * sizeof(first_values[0]),
        cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(
        d_second.get(), second_values.data(),
        second_values.size() * sizeof(second_values[0]),
        cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(
        d_roots.get(), roots.data(), roots.size() * sizeof(roots[0]),
        cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(
        d_factors.get(), factors.data(),
        factors.size() * sizeof(factors[0]), cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(
        d_parities.get(), parities.data(),
        parities.size() * sizeof(parities[0]), cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(
        d_frequencies.get(), frequencies.data(),
        frequencies.size() * sizeof(frequencies[0]),
        cudaMemcpyHostToDevice));

    const auto first = makeFrame(
        0U, d_first.get(), d_roots.get(), d_factors.get(),
        d_parities.get(), d_frequencies.get());
    const auto second = makeFrame(
        15U, d_second.get(), d_roots.get(), d_factors.get(),
        d_parities.get(), d_frequencies.get());
    runSuccessfulTwoFrameKat(first, second);
    runSparseCapacityFailureKat(first, second);
    CUDA_CHECK(cudaDeviceSynchronize());
    std::puts(
        "{\"algorithm\":\"tg-dirichlet-resident-phase-accumulator-kat-v1\","
        "\"frames\":2,\"samples\":6,\"raw_sparse_ranges\":4,"
        "\"coalesced_sparse_ranges\":2,"
        "\"phase_state_device_to_host_bytes\":0,"
        "\"per_frame_count_device_to_host_bytes\":0,"
        "\"source_qualified\":false}");
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
}

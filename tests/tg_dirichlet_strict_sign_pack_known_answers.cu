// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include "sparkinterval/tg_dirichlet_strict_sign_pack.cuh"

#include <cuda_runtime.h>

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace sc =
    sparkinterval::tg::dirichlet_booker_smallq_certified;
namespace pack = sparkinterval::tg::dirichlet_strict_sign_pack;

namespace {

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    const cudaError_t status_ = (call);                                      \
    if (status_ != cudaSuccess) {                                            \
      throw std::runtime_error(std::string("CUDA error: ") +                \
                               cudaGetErrorString(status_));                 \
    }                                                                        \
  } while (0)

unsigned char hostCode(sc::Disk disk, double threshold) {
  if (!std::isfinite(disk.real) || !std::isfinite(disk.imaginary) ||
      !std::isfinite(disk.radius) || disk.radius < 0.0 ||
      !std::isfinite(threshold) || threshold < 0.0) {
    throw std::runtime_error("invalid host KAT input");
  }
  volatile double rounded = disk.radius + threshold;
  const double boundary =
      std::nextafter(rounded, std::numeric_limits<double>::infinity());
  if (!std::isfinite(boundary)) {
    throw std::runtime_error("nonfinite host KAT boundary");
  }
  if (disk.real < -boundary) return sc::kPackedSignNegative;
  if (disk.real > boundary) return sc::kPackedSignPositive;
  return sc::kPackedSignAmbiguous;
}

struct DeviceArrays {
  sc::Disk* disks = nullptr;
  std::uint32_t* statuses = nullptr;
  sc::CharacterHeader* characters = nullptr;
  sc::TimeTailControlItem* controls = nullptr;
  unsigned char* payload = nullptr;
  pack::DevicePackSummary* summary = nullptr;

  ~DeviceArrays() {
    cudaFree(summary);
    cudaFree(payload);
    cudaFree(controls);
    cudaFree(characters);
    cudaFree(statuses);
    cudaFree(disks);
  }
};

pack::DevicePackSummary runPack(
    DeviceArrays* device, const std::vector<sc::Disk>& disks,
    const std::vector<std::uint32_t>& statuses,
    const std::vector<sc::CharacterHeader>& characters,
    const std::vector<sc::TimeTailControlItem>& controls,
    std::uint64_t frequencyStride, std::uint64_t sourceSamples,
    std::vector<unsigned char>* payload) {
  if (disks.size() != statuses.size() || characters.empty() ||
      controls.size() != sourceSamples || sourceSamples == 0U ||
      sourceSamples > frequencyStride ||
      characters.size() >
          std::numeric_limits<std::uint64_t>::max() / frequencyStride ||
      disks.size() != characters.size() * frequencyStride ||
      characters.size() >
          std::numeric_limits<std::uint64_t>::max() / sourceSamples) {
    throw std::runtime_error("invalid strict-sign KAT dimensions");
  }
  const std::uint64_t statusCount = disks.size();
  const std::uint64_t itemCount = characters.size() * sourceSamples;
  const std::uint64_t payloadBytes = (itemCount + 3U) / 4U;
  CUDA_CHECK(cudaMemcpy(device->disks, disks.data(),
                        disks.size() * sizeof(disks[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device->statuses, statuses.data(),
                        statuses.size() * sizeof(statuses[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device->characters, characters.data(),
                        characters.size() * sizeof(characters[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemcpy(device->controls, controls.data(),
                        controls.size() * sizeof(controls[0]),
                        cudaMemcpyHostToDevice));
  CUDA_CHECK(cudaMemset(device->summary, 0, sizeof(pack::DevicePackSummary)));
  pack::reduceStatuses<<<1, 64>>>(
      device->statuses, statusCount, device->summary);
  CUDA_CHECK(cudaGetLastError());
  pack::packStrictSigns<<<1, 64>>>(
      device->disks, device->statuses, device->characters, device->controls,
      frequencyStride, sourceSamples,
      static_cast<std::uint32_t>(characters.size()), device->payload,
      payloadBytes, device->summary);
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());
  pack::DevicePackSummary summary{};
  CUDA_CHECK(cudaMemcpy(&summary, device->summary, sizeof(summary),
                        cudaMemcpyDeviceToHost));
  payload->resize(static_cast<std::size_t>(payloadBytes));
  CUDA_CHECK(cudaMemcpy(payload->data(), device->payload, payload->size(),
                        cudaMemcpyDeviceToHost));
  return summary;
}

}  // namespace

int main() {
  try {
    constexpr std::uint64_t kCount = 7U;
    constexpr std::uint64_t kMaximumDiskCount = 10U;
    constexpr std::uint64_t kMaximumControlCount = kCount;
    constexpr std::uint32_t kMaximumCharacterCount = 2U;
    constexpr std::uint64_t kMaximumPayloadBytes = 2U;
    const double radius = 0.1;
    const double threshold = 0.25;
    volatile double rounded = radius + threshold;
    const double boundary =
        std::nextafter(rounded, std::numeric_limits<double>::infinity());
    const double outside =
        std::nextafter(boundary, std::numeric_limits<double>::infinity());
    std::vector<sc::Disk> disks = {
        {boundary, 0.0, radius},
        {outside, -0.0, radius},
        {-outside, 0.0, radius},
        {0.0, -0.0, radius},
        {-boundary, 0.0, radius},
        {1.0, 0.0, radius},
        {-1.0, 0.0, radius},
    };
    std::vector<std::uint32_t> statuses(kCount, sc::kSuccess);
    std::vector<sc::CharacterHeader> characters = {
        {1U, 0U, 0U, 0U},
    };
    std::vector<sc::TimeTailControlItem> controls(
        kCount, {threshold, threshold});
    std::vector<unsigned char> expected((kCount + 3U) / 4U, 0U);
    for (std::uint64_t index = 0U; index < kCount; ++index) {
      expected[index / 4U] |= static_cast<unsigned char>(
          hostCode(disks[index], threshold) << (2U * (index & 3U)));
    }

    DeviceArrays device;
    CUDA_CHECK(
        cudaMalloc(&device.disks, kMaximumDiskCount * sizeof(sc::Disk)));
    CUDA_CHECK(cudaMalloc(&device.statuses,
                          kMaximumDiskCount * sizeof(std::uint32_t)));
    CUDA_CHECK(cudaMalloc(&device.characters,
                          kMaximumCharacterCount *
                              sizeof(sc::CharacterHeader)));
    CUDA_CHECK(cudaMalloc(&device.controls,
                          kMaximumControlCount *
                              sizeof(sc::TimeTailControlItem)));
    CUDA_CHECK(cudaMalloc(&device.payload, kMaximumPayloadBytes));
    CUDA_CHECK(cudaMalloc(&device.summary,
                          sizeof(pack::DevicePackSummary)));

    std::vector<unsigned char> observed;
    const auto success = runPack(&device, disks, statuses, characters,
                                 controls, kCount, kCount, &observed);
    if (success.cuda_status_or != 0U ||
        success.classifier_error_or != 0U || observed != expected ||
        (observed.back() & 0xc0U) != 0U) {
      throw std::runtime_error(
          "device strict-sign KAT differs from the host oracle");
    }

    statuses[3] = sc::kNonFiniteArithmetic;
    const auto badStatus = runPack(&device, disks, statuses, characters,
                                   controls, kCount, kCount, &observed);
    if (badStatus.cuda_status_or != sc::kNonFiniteArithmetic ||
        (badStatus.classifier_error_or &
         pack::kDeviceClassifierNonzeroSourceStatus) == 0U) {
      throw std::runtime_error("nonzero CUDA status did not fail closed");
    }
    statuses[3] = sc::kSuccess;

    disks[2].real = std::numeric_limits<double>::infinity();
    const auto badDisk = runPack(&device, disks, statuses, characters,
                                 controls, kCount, kCount, &observed);
    if ((badDisk.classifier_error_or &
         pack::kDeviceClassifierInvalidDisk) == 0U) {
      throw std::runtime_error("nonfinite disk did not fail closed");
    }
    disks[2].real = -outside;

    controls[4].even = -1.0;
    const auto badControl = runPack(&device, disks, statuses, characters,
                                    controls, kCount, kCount, &observed);
    if ((badControl.classifier_error_or &
         pack::kDeviceClassifierInvalidControl) == 0U) {
      throw std::runtime_error("negative control did not fail closed");
    }
    controls[4].even = threshold;

    controls[1].even = std::numeric_limits<double>::infinity();
    const auto nonfiniteControl = runPack(
        &device, disks, statuses, characters, controls, kCount, kCount,
        &observed);
    if ((nonfiniteControl.classifier_error_or &
         pack::kDeviceClassifierInvalidControl) == 0U) {
      throw std::runtime_error("nonfinite control did not fail closed");
    }
    controls[1].even = threshold;

    disks[5].radius = std::numeric_limits<double>::max();
    controls[5].even = std::numeric_limits<double>::max();
    const auto badBoundary = runPack(&device, disks, statuses, characters,
                                     controls, kCount, kCount, &observed);
    if ((badBoundary.classifier_error_or &
         pack::kDeviceClassifierNonFiniteBoundary) == 0U) {
      throw std::runtime_error("overflowed boundary did not fail closed");
    }

    constexpr std::uint64_t kStride = 5U;
    constexpr std::uint64_t kSourceSamples = 3U;
    std::vector<sc::Disk> stridedDisks = {
        {0.5, 0.0, radius},
        {-0.5, 0.0, radius},
        {-0.5, 0.0, radius},
        {10.0, 0.0, radius},
        {-10.0, 0.0, radius},
        {-0.5, 0.0, radius},
        {0.5, 0.0, radius},
        {0.5, 0.0, radius},
        {-10.0, 0.0, radius},
        {10.0, 0.0, radius},
    };
    std::vector<std::uint32_t> stridedStatuses(
        stridedDisks.size(), sc::kSuccess);
    std::vector<sc::CharacterHeader> stridedCharacters = {
        {1U, 0U, 0U, 0U},
        {2U, 1U, 0U, 0U},
    };
    std::vector<sc::TimeTailControlItem> stridedControls = {
        {0.1, 0.9},
        {0.8, 0.1},
        {0.2, 0.7},
    };
    const std::vector<unsigned char> stridedExpected = {0x12U, 0x02U};
    const auto stridedSuccess =
        runPack(&device, stridedDisks, stridedStatuses, stridedCharacters,
                stridedControls, kStride, kSourceSamples, &observed);
    if (stridedSuccess.cuda_status_or != 0U ||
        stridedSuccess.classifier_error_or != 0U ||
        observed != stridedExpected || (observed.back() & 0xf0U) != 0U) {
      throw std::runtime_error(
          "strided even/odd strict-sign KAT differs from its fixed answer");
    }

    // This status belongs to an unpublished tail coordinate.  The complete
    // status reduction must still reject the frame.
    stridedStatuses[4] = sc::kNonFiniteArithmetic;
    const auto tailStatus =
        runPack(&device, stridedDisks, stridedStatuses, stridedCharacters,
                stridedControls, kStride, kSourceSamples, &observed);
    if (tailStatus.cuda_status_or != sc::kNonFiniteArithmetic ||
        tailStatus.classifier_error_or != 0U) {
      throw std::runtime_error(
          "unpublished-tail CUDA status escaped the complete reduction");
    }
    stridedStatuses[4] = sc::kSuccess;

    stridedCharacters[1].parity = 2U;
    const auto badParity =
        runPack(&device, stridedDisks, stridedStatuses, stridedCharacters,
                stridedControls, kStride, kSourceSamples, &observed);
    if (badParity.cuda_status_or != 0U ||
        (badParity.classifier_error_or &
         pack::kDeviceClassifierInvalidParity) == 0U) {
      throw std::runtime_error("invalid character parity did not fail closed");
    }

    std::printf(
        "{\"algorithm\":\"tg-dirichlet-strict-sign-device-kat-v1\","
        "\"device_host_payload_byte_identical\":true,"
        "\"exact_boundary_ambiguous\":true,"
        "\"positive_negative_ambiguous_covered\":true,"
        "\"non_multiple_of_four_padding_zero\":true,"
        "\"nonzero_status_rejected\":true,"
        "\"nonfinite_disk_rejected\":true,"
        "\"negative_control_rejected\":true,"
        "\"nonfinite_control_rejected\":true,"
        "\"boundary_overflow_rejected\":true,"
        "\"strided_even_odd_payload_matches_fixed_answer\":true,"
        "\"frequency_stride_exceeds_source_samples\":true,"
        "\"unpublished_tail_status_rejected\":true,"
        "\"invalid_parity_rejected\":true,"
        "\"payload_hex\":\"");
    for (const unsigned char byte : expected) {
      std::printf("%02x", static_cast<unsigned>(byte));
    }
    std::printf("\"}\n");
    return 0;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "tg_dirichlet_strict_sign_pack_kat: %s\n",
                 error.what());
    return 2;
  }
}

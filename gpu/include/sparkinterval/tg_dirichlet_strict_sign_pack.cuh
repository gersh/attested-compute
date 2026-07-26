// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_dirichlet_booker_smallq_certified.hpp"

#include <cuda_runtime.h>

#include <cstdint>

namespace sparkinterval::tg::dirichlet_strict_sign_pack {

namespace sc = dirichlet_booker_smallq_certified;

// This is copied back after every frame.  It is deliberately bounded and
// contains no caller-controlled pointers or counts.
struct DevicePackSummary {
  std::uint32_t cuda_status_or;
  std::uint32_t classifier_error_or;
};

enum DeviceClassifierError : std::uint32_t {
  kDeviceClassifierSuccess = 0U,
  kDeviceClassifierInvalidDisk = 1U << 0U,
  kDeviceClassifierInvalidControl = 1U << 1U,
  kDeviceClassifierInvalidParity = 1U << 2U,
  kDeviceClassifierNonFiniteBoundary = 1U << 3U,
  kDeviceClassifierNonzeroSourceStatus = 1U << 4U,
};

static_assert(sizeof(DevicePackSummary) == 8U);

__device__ __forceinline__ bool validStrictSignDisk(sc::Disk value) {
  return isfinite(value.real) && isfinite(value.imaginary) &&
         isfinite(value.radius) && value.radius >= 0.0;
}

// Reduce every CUDA status, not merely the source-sample prefix.  The strict
// sign payload is publishable only when this complete reduction is zero.
static __global__ void reduceStatuses(
    const std::uint32_t* statuses, std::uint64_t count,
    DevicePackSummary* summary) {
  std::uint32_t local = 0U;
  for (std::uint64_t index =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < count;
       index += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    local |= statuses[index];
  }
  if (local != 0U) atomicOr(&summary->cuda_status_or, local);
}

// Pack four character-major/sample-major decisions per byte.  One thread owns
// one complete byte, so no atomic packing or inter-thread ordering assumption
// enters the wire payload.
static __global__ void packStrictSigns(
    const sc::Disk* values, const std::uint32_t* statuses,
    const sc::CharacterHeader* characters,
    const sc::TimeTailControlItem* controls, std::uint64_t frequencyStride,
    std::uint64_t sourceSamples, std::uint32_t batchCharacters,
    unsigned char* payload, std::uint64_t payloadBytes,
    DevicePackSummary* summary) {
  const std::uint64_t itemCount =
      static_cast<std::uint64_t>(batchCharacters) * sourceSamples;
  for (std::uint64_t byteIndex =
           static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
       byteIndex < payloadBytes;
       byteIndex += static_cast<std::uint64_t>(blockDim.x) * gridDim.x) {
    unsigned char packed = 0U;
    for (unsigned lane = 0U; lane < 4U; ++lane) {
      const std::uint64_t item = byteIndex * 4U + lane;
      if (item >= itemCount) break;
      const std::uint64_t character = item / sourceSamples;
      const std::uint64_t sample = item % sourceSamples;
      const std::uint64_t flat = character * frequencyStride + sample;
      const sc::Disk disk = values[flat];
      const std::uint32_t parity = characters[character].parity;
      std::uint32_t error = kDeviceClassifierSuccess;
      if (statuses[flat] != sc::kSuccess) {
        error |= kDeviceClassifierNonzeroSourceStatus;
      }
      if (!validStrictSignDisk(disk)) {
        error |= kDeviceClassifierInvalidDisk;
      }
      if (parity > 1U) error |= kDeviceClassifierInvalidParity;
      const double threshold =
          parity == 0U ? controls[sample].even : controls[sample].odd;
      if (!isfinite(threshold) || threshold < 0.0) {
        error |= kDeviceClassifierInvalidControl;
      }

      unsigned char code = 3U;
      if (error == kDeviceClassifierSuccess) {
        // This is the exact reviewed wire rule.  Do not replace __dadd_rn
        // with ordinary source addition: the explicit intrinsic is part of
        // the device-side arithmetic identity.
        const double boundary =
            nextafter(__dadd_rn(disk.radius, threshold),
                      __longlong_as_double(0x7ff0000000000000LL));
        if (!isfinite(boundary)) {
          error |= kDeviceClassifierNonFiniteBoundary;
        } else if (disk.real < -boundary) {
          code = sc::kPackedSignNegative;
        } else if (disk.real > boundary) {
          code = sc::kPackedSignPositive;
        } else {
          code = sc::kPackedSignAmbiguous;
        }
      }
      if (error != kDeviceClassifierSuccess) {
        atomicOr(&summary->classifier_error_or, error);
      }
      packed |= static_cast<unsigned char>(code << (2U * lane));
    }
    payload[byteIndex] = packed;
  }
}

}  // namespace sparkinterval::tg::dirichlet_strict_sign_pack

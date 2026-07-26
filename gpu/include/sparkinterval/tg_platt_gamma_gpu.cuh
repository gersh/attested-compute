// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_platt_windowed.hpp"

#include <cuda_runtime.h>

#include <cstdint>

namespace sparkinterval::tg::platt_gamma_gpu {

namespace pw = sparkinterval::tg::platt_windowed;

// Row-major output retained on the device.  A future fused Platt consumer can
// insert its accumulator/FFT kernels after launch_synthesize_gamma_rows and
// before this storage is reused for the next authenticated microbatch.
struct GammaRowBatchView {
  pw::ComplexInterval* rows = nullptr;
  std::uint32_t record_count = 0;
  std::uint32_t row_stride = pw::kBucketCount;
  std::uint64_t first_block = 0;
};

struct GammaDiskRowBatchView {
  pw::ComplexDisk106* rows = nullptr;
  std::uint32_t record_count = 0;
  std::uint32_t row_stride = pw::kBucketCount;
  std::uint64_t first_block = 0;
};

// This is an audit summary, not a cryptographic commitment to the complete
// row.  Its four index-keyed integer lanes are deterministic across runs of
// the same CUDA arithmetic, while the invalid counter is a mandatory safety
// check.  The host SHA-256 commits to the ordered sequence of these records.
#pragma pack(push, 1)
struct GammaRowSummary {
  std::uint64_t logical_block;
  std::uint64_t digest_lane0;
  std::uint64_t digest_lane1;
  std::uint64_t digest_lane2;
  std::uint64_t digest_lane3;
  std::uint64_t invalid_intervals;
  double maximum_real_width;
  double maximum_imaginary_width;
};
#pragma pack(pop)

static_assert(sizeof(GammaRowSummary) == 64U);

#pragma pack(push, 1)
struct GammaDiskRowSummary {
  std::uint64_t logical_block;
  std::uint64_t digest;
  std::uint64_t invalid_disks;
  double maximum_radius;
};
#pragma pack(pop)

static_assert(sizeof(GammaDiskRowSummary) == 32U);

// One launch synthesizes every one of the 32768 source-grid values for every
// record in the batch.  Input records must already have passed the host stream
// authenticator.  All interval endpoints use directed binary64 operations.
void launch_synthesize_gamma_rows(
    const pw::GammaTaylorStreamRecord* authenticated_records,
    GammaRowBatchView output, cudaStream_t stream);

// Produces one fixed-size record per row without copying the rows to the host.
void launch_summarize_gamma_rows(GammaRowBatchView input,
                                 GammaRowSummary* summaries,
                                 cudaStream_t stream);

// Convert each rigorous Cartesian interval to a Euclidean disk with an exact
// binary64 centre and a directed radius.  The resulting device layout is the
// direct input layout of tg_platt_dd_transform.hpp; no host packet is needed.
void launch_convert_gamma_rows_to_disks(GammaRowBatchView input,
                                        GammaDiskRowBatchView output,
                                        cudaStream_t stream);

void launch_summarize_gamma_disks(GammaDiskRowBatchView input,
                                  GammaDiskRowSummary* summaries,
                                  cudaStream_t stream);

}  // namespace sparkinterval::tg::platt_gamma_gpu

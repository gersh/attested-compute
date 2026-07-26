// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once

#include "sparkinterval/tg_platt_gamma_stream_v2.hpp"

#include <cuda_runtime.h>

#include <cstdint>

namespace sparkinterval::tg::platt_gamma_dd_gpu {

namespace pg2 = sparkinterval::tg::platt_gamma_stream_v2;
namespace pw = sparkinterval::tg::platt_windowed;

struct BatchView {
  pw::ComplexDisk106* rows = nullptr;
  std::uint32_t record_count = 0U;
  std::uint32_t row_stride = pw::kBucketCount;
  std::uint64_t first_block = 0U;
};

#pragma pack(push, 1)
struct RowSummary {
  std::uint64_t logical_block;
  std::uint64_t digest;
  std::uint64_t invalid_disks;
  double maximum_radius;
};
#pragma pack(pop)

static_assert(sizeof(RowSummary) == 32U);

// Input records must have passed pg2::Reader.  The result remains resident in
// exactly the ComplexDisk106 layout consumed by tg_platt_dd_transform.hpp.
void launch_synthesize(const pg2::Record* authenticated_records,
                       BatchView output, cudaStream_t stream);

void launch_summarize(BatchView input, RowSummary* summaries,
                      cudaStream_t stream);

}  // namespace sparkinterval::tg::platt_gamma_dd_gpu

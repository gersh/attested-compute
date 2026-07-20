#pragma once

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

#include <cstdint>

#include <cuda_runtime_api.h>

// One deterministic integer work item representative of the fixed-point
// quotient, wide multiply, comparison, and output traffic used by the
// ternary-Goldbach finite-campaign planners.  This is a microbenchmark only;
// it is not any of the thirteen mathematical verifiers.
std::uint64_t tg_workload_reference(std::uint64_t index);

cudaError_t launch_tg_workload_benchmark(std::uint64_t start,
                                         std::uint64_t count,
                                         std::uint64_t* output,
                                         cudaStream_t stream);

#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

// On-disk protocol (all integers little-endian):
//
// input  = "SIB64I01" | u32(version=1) | u32(operation) | u64(row_count)
//          | row_count * (u64(lhs_bits) | u64(rhs_bits))
// output = "SIB64O01" | u32(version=1) | u32(operation) | u64(row_count)
//          | row_count * (u64(down_bits) | u64(up_bits) | u8(status) | 7*zero)
//
// The runner validates the complete input, including its exact length.  A
// valid row has status 0.  Invalid rows have both result words zero and a
// nonzero status; those words are not interval endpoints.

enum class IntervalBatchOperation : std::uint32_t {
  add = 1,
  sub = 2,
  mul = 3,
  div = 4,
};

enum class IntervalBatchStatus : std::uint8_t {
  valid = 0,
  nonfinite_input = 1,
  division_by_zero = 2,
  unsupported_operation = 3,
};

struct alignas(16) IntervalBatchInput {
  std::uint64_t lhs_bits;
  std::uint64_t rhs_bits;
};

struct alignas(8) IntervalBatchOutput {
  std::uint64_t down_bits;
  std::uint64_t up_bits;
  std::uint8_t status;
  std::uint8_t reserved[7];
};

static_assert(sizeof(IntervalBatchInput) == 16);
static_assert(sizeof(IntervalBatchOutput) == 24);

cudaError_t launch_interval_batch(const IntervalBatchInput* inputs,
                                  IntervalBatchOutput* outputs,
                                  std::size_t row_count,
                                  IntervalBatchOperation operation,
                                  cudaStream_t stream = nullptr);

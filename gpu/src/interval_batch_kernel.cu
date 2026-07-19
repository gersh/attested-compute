#include "interval_batch.h"

#include <cuda_runtime.h>

namespace {

constexpr std::uint64_t kSignMask = 0x8000000000000000ULL;
constexpr std::uint64_t kExponentMask = 0x7ff0000000000000ULL;

__device__ __forceinline__ bool finite_bits(std::uint64_t bits) {
  return (bits & kExponentMask) != kExponentMask;
}

__device__ __forceinline__ bool zero_bits(std::uint64_t bits) {
  return (bits & ~kSignMask) == 0;
}

__device__ __forceinline__ double double_of(std::uint64_t bits) {
  return __longlong_as_double(static_cast<long long>(bits));
}

__device__ __forceinline__ std::uint64_t bits_of(double value) {
  return static_cast<std::uint64_t>(__double_as_longlong(value));
}

__device__ __forceinline__ void mark_invalid(IntervalBatchOutput* output,
                                             IntervalBatchStatus status) {
  output->down_bits = 0;
  output->up_bits = 0;
  output->status = static_cast<std::uint8_t>(status);
#pragma unroll
  for (int i = 0; i < 7; ++i) {
    output->reserved[i] = 0;
  }
}

__global__ void interval_batch_kernel(const IntervalBatchInput* inputs,
                                      IntervalBatchOutput* outputs,
                                      std::size_t row_count,
                                      IntervalBatchOperation operation) {
  const std::size_t row =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (row >= row_count) {
    return;
  }

  const std::uint64_t lhs_bits = inputs[row].lhs_bits;
  const std::uint64_t rhs_bits = inputs[row].rhs_bits;
  IntervalBatchOutput* output = &outputs[row];

  if (!finite_bits(lhs_bits) || !finite_bits(rhs_bits)) {
    mark_invalid(output, IntervalBatchStatus::nonfinite_input);
    return;
  }
  if (operation == IntervalBatchOperation::div && zero_bits(rhs_bits)) {
    mark_invalid(output, IntervalBatchStatus::division_by_zero);
    return;
  }

  const double lhs = double_of(lhs_bits);
  const double rhs = double_of(rhs_bits);
  double down = 0.0;
  double up = 0.0;
  switch (operation) {
    case IntervalBatchOperation::add:
      down = __dadd_rd(lhs, rhs);
      up = __dadd_ru(lhs, rhs);
      break;
    case IntervalBatchOperation::sub:
      down = __dsub_rd(lhs, rhs);
      up = __dsub_ru(lhs, rhs);
      break;
    case IntervalBatchOperation::mul:
      down = __dmul_rd(lhs, rhs);
      up = __dmul_ru(lhs, rhs);
      break;
    case IntervalBatchOperation::div:
      down = __ddiv_rd(lhs, rhs);
      up = __ddiv_ru(lhs, rhs);
      break;
    default:
      mark_invalid(output, IntervalBatchStatus::unsupported_operation);
      return;
  }

  output->down_bits = bits_of(down);
  output->up_bits = bits_of(up);
  output->status = static_cast<std::uint8_t>(IntervalBatchStatus::valid);
#pragma unroll
  for (int i = 0; i < 7; ++i) {
    output->reserved[i] = 0;
  }
}

}  // namespace

cudaError_t launch_interval_batch(const IntervalBatchInput* inputs,
                                  IntervalBatchOutput* outputs,
                                  std::size_t row_count,
                                  IntervalBatchOperation operation,
                                  cudaStream_t stream) {
  constexpr unsigned int threads_per_block = 256;
  const std::size_t block_count =
      (row_count + threads_per_block - 1) / threads_per_block;
  if (row_count == 0 || block_count > 0xffffffffULL) {
    return cudaErrorInvalidValue;
  }
  interval_batch_kernel<<<static_cast<unsigned int>(block_count),
                          threads_per_block, 0, stream>>>(
      inputs, outputs, row_count, operation);
  return cudaGetLastError();
}

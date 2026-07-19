#include "expression_batch.h"

#include <cuda_runtime.h>

namespace {

constexpr std::uint64_t kSignMask = 0x8000000000000000ULL;
constexpr std::uint64_t kExponentMask = 0x7ff0000000000000ULL;
constexpr std::uint64_t kPositiveZero = 0x0000000000000000ULL;
constexpr std::uint64_t kNegativeZero = 0x8000000000000000ULL;
constexpr std::uint64_t kPositiveOne = 0x3ff0000000000000ULL;
constexpr std::uint64_t kPositiveInfinity = 0x7ff0000000000000ULL;
constexpr std::uint64_t kNegativeInfinity = 0xfff0000000000000ULL;

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

// Numeric comparison for non-NaN binary64 encodings. Signed zeros compare
// equal, as they do in the exact reference interval semantics.
__device__ __forceinline__ int endpoint_compare(std::uint64_t left,
                                                std::uint64_t right) {
  if (zero_bits(left) && zero_bits(right)) {
    return 0;
  }
  const bool left_negative = (left & kSignMask) != 0;
  const bool right_negative = (right & kSignMask) != 0;
  if (left_negative != right_negative) {
    return left_negative ? -1 : 1;
  }
  if (left == right) {
    return 0;
  }
  if (left_negative) {
    return left > right ? -1 : 1;
  }
  return left < right ? -1 : 1;
}

__device__ __forceinline__ std::uint64_t minimum_endpoint(
    std::uint64_t left, std::uint64_t right) {
  const int comparison = endpoint_compare(left, right);
  if (comparison < 0) return left;
  if (comparison > 0) return right;
  if (zero_bits(left) && zero_bits(right)) {
    return ((left | right) & kSignMask) != 0 ? kNegativeZero : kPositiveZero;
  }
  return left;
}

__device__ __forceinline__ std::uint64_t maximum_endpoint(
    std::uint64_t left, std::uint64_t right) {
  const int comparison = endpoint_compare(left, right);
  if (comparison > 0) return left;
  if (comparison < 0) return right;
  if (zero_bits(left) && zero_bits(right)) {
    return ((left & right) & kSignMask) != 0 ? kNegativeZero : kPositiveZero;
  }
  return left;
}

__device__ __forceinline__ ExpressionInterval whole_interval() {
  return {kNegativeInfinity, kPositiveInfinity};
}

__device__ __forceinline__ bool finite_interval(ExpressionInterval value) {
  return finite_bits(value.lo_bits) && finite_bits(value.hi_bits);
}

__device__ __forceinline__ bool contains_zero(ExpressionInterval value) {
  return endpoint_compare(value.lo_bits, kPositiveZero) <= 0 &&
         endpoint_compare(kPositiveZero, value.hi_bits) <= 0;
}

__device__ __forceinline__ ExpressionInterval interval_neg(
    ExpressionInterval value) {
  return {value.hi_bits ^ kSignMask, value.lo_bits ^ kSignMask};
}

__device__ __forceinline__ ExpressionInterval interval_abs(
    ExpressionInterval value) {
  if (endpoint_compare(value.lo_bits, kPositiveZero) >= 0) {
    return {value.lo_bits & ~kSignMask, value.hi_bits & ~kSignMask};
  }
  if (endpoint_compare(value.hi_bits, kPositiveZero) <= 0) {
    return {value.hi_bits & ~kSignMask, value.lo_bits & ~kSignMask};
  }
  return {kPositiveZero,
          maximum_endpoint(value.lo_bits & ~kSignMask,
                           value.hi_bits & ~kSignMask)};
}

__device__ __forceinline__ ExpressionInterval interval_minimum(
    ExpressionInterval left, ExpressionInterval right) {
  return {minimum_endpoint(left.lo_bits, right.lo_bits),
          minimum_endpoint(left.hi_bits, right.hi_bits)};
}

__device__ __forceinline__ ExpressionInterval interval_maximum(
    ExpressionInterval left, ExpressionInterval right) {
  return {maximum_endpoint(left.lo_bits, right.lo_bits),
          maximum_endpoint(left.hi_bits, right.hi_bits)};
}

__device__ __forceinline__ ExpressionInterval interval_add(
    ExpressionInterval left, ExpressionInterval right) {
  if (!finite_interval(left) || !finite_interval(right)) {
    return whole_interval();
  }
  return {bits_of(__dadd_rd(double_of(left.lo_bits), double_of(right.lo_bits))),
          bits_of(__dadd_ru(double_of(left.hi_bits), double_of(right.hi_bits)))};
}

__device__ __forceinline__ ExpressionInterval interval_sub(
    ExpressionInterval left, ExpressionInterval right) {
  if (!finite_interval(left) || !finite_interval(right)) {
    return whole_interval();
  }
  return {bits_of(__dsub_rd(double_of(left.lo_bits), double_of(right.hi_bits))),
          bits_of(__dsub_ru(double_of(left.hi_bits), double_of(right.lo_bits)))};
}

__device__ __forceinline__ ExpressionInterval interval_mul(
    ExpressionInterval left, ExpressionInterval right) {
  if (!finite_interval(left) || !finite_interval(right)) {
    return whole_interval();
  }
  const double left_lo = double_of(left.lo_bits);
  const double left_hi = double_of(left.hi_bits);
  const double right_lo = double_of(right.lo_bits);
  const double right_hi = double_of(right.hi_bits);
  const std::uint64_t down0 = bits_of(__dmul_rd(left_lo, right_lo));
  const std::uint64_t down1 = bits_of(__dmul_rd(left_lo, right_hi));
  const std::uint64_t down2 = bits_of(__dmul_rd(left_hi, right_lo));
  const std::uint64_t down3 = bits_of(__dmul_rd(left_hi, right_hi));
  const std::uint64_t up0 = bits_of(__dmul_ru(left_lo, right_lo));
  const std::uint64_t up1 = bits_of(__dmul_ru(left_lo, right_hi));
  const std::uint64_t up2 = bits_of(__dmul_ru(left_hi, right_lo));
  const std::uint64_t up3 = bits_of(__dmul_ru(left_hi, right_hi));
  return {
      minimum_endpoint(minimum_endpoint(down0, down1),
                       minimum_endpoint(down2, down3)),
      maximum_endpoint(maximum_endpoint(up0, up1),
                       maximum_endpoint(up2, up3))};
}

__device__ __forceinline__ bool interval_div(
    ExpressionInterval left, ExpressionInterval right,
    ExpressionInterval* result) {
  if (contains_zero(right)) {
    return false;
  }
  if (!finite_interval(left) || !finite_interval(right)) {
    *result = whole_interval();
    return true;
  }
  const double left_lo = double_of(left.lo_bits);
  const double left_hi = double_of(left.hi_bits);
  const double right_lo = double_of(right.lo_bits);
  const double right_hi = double_of(right.hi_bits);
  const std::uint64_t down0 = bits_of(__ddiv_rd(left_lo, right_lo));
  const std::uint64_t down1 = bits_of(__ddiv_rd(left_lo, right_hi));
  const std::uint64_t down2 = bits_of(__ddiv_rd(left_hi, right_lo));
  const std::uint64_t down3 = bits_of(__ddiv_rd(left_hi, right_hi));
  const std::uint64_t up0 = bits_of(__ddiv_ru(left_lo, right_lo));
  const std::uint64_t up1 = bits_of(__ddiv_ru(left_lo, right_hi));
  const std::uint64_t up2 = bits_of(__ddiv_ru(left_hi, right_lo));
  const std::uint64_t up3 = bits_of(__ddiv_ru(left_hi, right_hi));
  *result = {
      minimum_endpoint(minimum_endpoint(down0, down1),
                       minimum_endpoint(down2, down3)),
      maximum_endpoint(maximum_endpoint(up0, up1),
                       maximum_endpoint(up2, up3))};
  return true;
}

__device__ __forceinline__ bool interval_pow_nat(
    ExpressionInterval value, std::uint32_t exponent,
    ExpressionInterval* result) {
  *result = {kPositiveOne, kPositiveOne};
  for (std::uint32_t i = 0; i < exponent; ++i) {
    if (!finite_interval(*result) || !finite_interval(value)) {
      *result = whole_interval();
      return false;
    }
    *result = interval_mul(*result, value);
  }
  return true;
}

__device__ __forceinline__ void mark_output(ExpressionBatchOutput* output,
                                            std::uint64_t lo_bits,
                                            std::uint64_t hi_bits,
                                            ExpressionBatchStatus status) {
  output->lo_bits = lo_bits;
  output->hi_bits = hi_bits;
  output->status = static_cast<std::uint8_t>(status);
#pragma unroll
  for (int i = 0; i < 7; ++i) {
    output->reserved[i] = 0;
  }
}

__global__ void expression_batch_kernel(
    const ExpressionInstruction* program, std::size_t instruction_count,
    const ExpressionInterval* variables, std::size_t variable_count,
    ExpressionBatchOutput* outputs, std::size_t row_count) {
  const std::size_t row =
      static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (row >= row_count) return;

  ExpressionInterval stack[kExpressionMaxStackDepth];
  std::uint32_t stack_size = 0;
  for (std::size_t pc = 0; pc < instruction_count; ++pc) {
    const ExpressionInstruction instruction = program[pc];
    const ExpressionOpcode opcode =
        static_cast<ExpressionOpcode>(instruction.opcode);
    switch (opcode) {
      case ExpressionOpcode::constant:
        if (stack_size >= kExpressionMaxStackDepth) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::execution_error);
          return;
        }
        stack[stack_size++] = {instruction.lo_bits, instruction.hi_bits};
        break;
      case ExpressionOpcode::variable:
        if (stack_size >= kExpressionMaxStackDepth ||
            instruction.argument >= variable_count) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::execution_error);
          return;
        }
        stack[stack_size++] =
            variables[row * variable_count + instruction.argument];
        break;
      case ExpressionOpcode::neg:
        if (stack_size < 1) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::execution_error);
          return;
        }
        stack[stack_size - 1] = interval_neg(stack[stack_size - 1]);
        break;
      case ExpressionOpcode::abs:
        if (stack_size < 1) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::execution_error);
          return;
        }
        stack[stack_size - 1] = interval_abs(stack[stack_size - 1]);
        break;
      case ExpressionOpcode::pow_nat:
        if (stack_size < 1 ||
            instruction.argument > kExpressionMaxPowExponent) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::execution_error);
          return;
        }
        {
          ExpressionInterval result{};
          if (!interval_pow_nat(stack[stack_size - 1], instruction.argument,
                                &result)) {
            const ExpressionInterval whole = whole_interval();
            mark_output(
                &outputs[row], whole.lo_bits, whole.hi_bits,
                ExpressionBatchStatus::nonfinite_intermediate_widening);
            return;
          }
          stack[stack_size - 1] = result;
        }
        break;
      case ExpressionOpcode::add:
      case ExpressionOpcode::sub:
      case ExpressionOpcode::mul:
      case ExpressionOpcode::div:
      case ExpressionOpcode::minimum:
      case ExpressionOpcode::maximum: {
        if (stack_size < 2) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::execution_error);
          return;
        }
        const ExpressionInterval right = stack[--stack_size];
        const ExpressionInterval left = stack[stack_size - 1];
        ExpressionInterval result{};
        if (opcode == ExpressionOpcode::div && contains_zero(right)) {
          mark_output(&outputs[row], 0, 0,
                      ExpressionBatchStatus::divisor_contains_zero);
          return;
        }
        if ((opcode == ExpressionOpcode::add ||
             opcode == ExpressionOpcode::sub ||
             opcode == ExpressionOpcode::mul ||
             opcode == ExpressionOpcode::div) &&
            (!finite_interval(left) || !finite_interval(right))) {
          const ExpressionInterval whole = whole_interval();
          mark_output(&outputs[row], whole.lo_bits, whole.hi_bits,
                      ExpressionBatchStatus::nonfinite_intermediate_widening);
          return;
        }
        if (opcode == ExpressionOpcode::add) {
          result = interval_add(left, right);
        } else if (opcode == ExpressionOpcode::sub) {
          result = interval_sub(left, right);
        } else if (opcode == ExpressionOpcode::mul) {
          result = interval_mul(left, right);
        } else if (opcode == ExpressionOpcode::div) {
          if (!interval_div(left, right, &result)) {
            mark_output(&outputs[row], 0, 0,
                        ExpressionBatchStatus::divisor_contains_zero);
            return;
          }
        } else if (opcode == ExpressionOpcode::minimum) {
          result = interval_minimum(left, right);
        } else {
          result = interval_maximum(left, right);
        }
        stack[stack_size - 1] = result;
        break;
      }
      default:
        mark_output(&outputs[row], 0, 0,
                    ExpressionBatchStatus::execution_error);
        return;
    }
  }

  if (stack_size != 1) {
    mark_output(&outputs[row], 0, 0,
                ExpressionBatchStatus::execution_error);
    return;
  }
  mark_output(&outputs[row], stack[0].lo_bits, stack[0].hi_bits,
              ExpressionBatchStatus::valid);
}

}  // namespace

cudaError_t launch_expression_batch(
    const ExpressionInstruction* program, std::size_t instruction_count,
    const ExpressionInterval* variables, std::size_t variable_count,
    ExpressionBatchOutput* outputs, std::size_t row_count,
    cudaStream_t stream) {
  constexpr unsigned int threads_per_block = 256;
  if (program == nullptr || outputs == nullptr || instruction_count == 0 ||
      instruction_count > kExpressionMaxInstructions ||
      variable_count > kExpressionMaxVariables || row_count == 0 ||
      row_count > kExpressionMaxRows ||
      (variable_count != 0 && variables == nullptr)) {
    return cudaErrorInvalidValue;
  }
  const std::size_t block_count =
      (row_count + threads_per_block - 1) / threads_per_block;
  if (block_count > 0xffffffffULL) return cudaErrorInvalidValue;
  expression_batch_kernel<<<static_cast<unsigned int>(block_count),
                            threads_per_block, 0, stream>>>(
      program, instruction_count, variables, variable_count, outputs,
      row_count);
  return cudaGetLastError();
}

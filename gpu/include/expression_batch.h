#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

// Strict little-endian on-disk protocol:
//
// input  = "SIE64I01"
//          | u32(version=1) | u32(instruction_count) | u32(variable_count)
//          | u32(max_stack_depth) | u64(row_count)
//          | instruction_count * Instruction
//          | row_count * variable_count * Interval
// output = "SIE64O01"
//          | the same five integer header fields
//          | row_count * Output
//
// Instruction = u8(opcode) | u8(flags=0) | u16(reserved=0) | u32(argument)
//               | u64(lo_bits) | u64(hi_bits)
// Interval    = u64(lo_bits) | u64(hi_bits)
// Output      = u64(lo_bits) | u64(hi_bits) | u8(status) | 7*zero
//
// Constants use lo_bits/hi_bits and require argument=0. Variables and pow_nat
// use argument and require both endpoint words to be zero. Every other opcode
// requires all three payload fields to be zero. The host validates the entire
// postfix program, its exact stack depth, every finite input interval, and the
// exact file length before launching CUDA.

constexpr std::uint32_t kExpressionFormatVersion = 1;
constexpr std::uint32_t kExpressionMaxInstructions = 256;
constexpr std::uint32_t kExpressionMaxVariables = 64;
constexpr std::uint32_t kExpressionMaxStackDepth = 32;
constexpr std::uint32_t kExpressionMaxPowExponent = 64;
constexpr std::uint64_t kExpressionMaxRows = 1'000'000;
constexpr std::uint64_t kExpressionMaxInputFileBytes = 1ULL << 28;

enum class ExpressionOpcode : std::uint8_t {
  constant = 1,
  variable = 2,
  neg = 3,
  add = 4,
  sub = 5,
  mul = 6,
  div = 7,
  abs = 8,
  minimum = 9,
  maximum = 10,
  pow_nat = 11,
};

enum class ExpressionBatchStatus : std::uint8_t {
  valid = 0,
  divisor_contains_zero = 1,
  nonfinite_intermediate_widening = 2,
  execution_error = 3,
};

struct alignas(8) ExpressionInstruction {
  std::uint8_t opcode;
  std::uint8_t flags;
  std::uint16_t reserved;
  std::uint32_t argument;
  std::uint64_t lo_bits;
  std::uint64_t hi_bits;
};

struct alignas(16) ExpressionInterval {
  std::uint64_t lo_bits;
  std::uint64_t hi_bits;
};

struct alignas(8) ExpressionBatchOutput {
  std::uint64_t lo_bits;
  std::uint64_t hi_bits;
  std::uint8_t status;
  std::uint8_t reserved[7];
};

static_assert(sizeof(ExpressionInstruction) == 24);
static_assert(sizeof(ExpressionInterval) == 16);
static_assert(sizeof(ExpressionBatchOutput) == 24);

cudaError_t launch_expression_batch(
    const ExpressionInstruction* program,
    std::size_t instruction_count,
    const ExpressionInterval* variables,
    std::size_t variable_count,
    ExpressionBatchOutput* outputs,
    std::size_t row_count,
    cudaStream_t stream = nullptr);

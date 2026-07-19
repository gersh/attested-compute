#include <cuda_runtime.h>

#include <cstdint>

// This kernel is deliberately device-only in the offline H100 build. It uses
// the same fixed bit-level contract as the native DGX diagnostic, making the
// eventual H100 host acceptance test deterministic and input-free.
extern "C" __global__ void h100_directed_rounding_probe(
    std::uint64_t* output_bits) {
  if (blockIdx.x != 0 || threadIdx.x != 0) {
    return;
  }

  const double one = 1.0;
  const double half_ulp_at_one = 0x1p-53;
  const double quarter_ulp_at_one = 0x1p-54;
  const double one_plus_ulp = 0x1.0000000000001p+0;
  const double three = 3.0;

  output_bits[0] = static_cast<std::uint64_t>(
      __double_as_longlong(__dadd_rd(one, half_ulp_at_one)));
  output_bits[1] = static_cast<std::uint64_t>(
      __double_as_longlong(__dadd_ru(one, half_ulp_at_one)));
  output_bits[2] = static_cast<std::uint64_t>(
      __double_as_longlong(__dsub_rd(one, quarter_ulp_at_one)));
  output_bits[3] = static_cast<std::uint64_t>(
      __double_as_longlong(__dsub_ru(one, quarter_ulp_at_one)));
  output_bits[4] = static_cast<std::uint64_t>(
      __double_as_longlong(__dmul_rd(one_plus_ulp, one_plus_ulp)));
  output_bits[5] = static_cast<std::uint64_t>(
      __double_as_longlong(__dmul_ru(one_plus_ulp, one_plus_ulp)));
  output_bits[6] = static_cast<std::uint64_t>(
      __double_as_longlong(__ddiv_rd(one, three)));
  output_bits[7] = static_cast<std::uint64_t>(
      __double_as_longlong(__ddiv_ru(one, three)));
}

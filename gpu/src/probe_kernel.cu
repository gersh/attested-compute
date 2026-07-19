#include "probe_kernel.h"

#include <cuda_runtime.h>

namespace {

__device__ std::uint64_t bits_of(double value) {
  return static_cast<std::uint64_t>(__double_as_longlong(value));
}

__global__ void directed_rounding_probe_kernel(DirectedRoundingProbeBits* output) {
  if (blockIdx.x != 0 || threadIdx.x != 0) {
    return;
  }

  const double one = 1.0;
  const double half_ulp_at_one = 0x1p-53;
  const double quarter_ulp_at_one = 0x1p-54;
  const double one_plus_ulp = 0x1.0000000000001p+0;
  const double three = 3.0;

  output->add_down = bits_of(__dadd_rd(one, half_ulp_at_one));
  output->add_up = bits_of(__dadd_ru(one, half_ulp_at_one));
  output->sub_down = bits_of(__dsub_rd(one, quarter_ulp_at_one));
  output->sub_up = bits_of(__dsub_ru(one, quarter_ulp_at_one));
  output->mul_down = bits_of(__dmul_rd(one_plus_ulp, one_plus_ulp));
  output->mul_up = bits_of(__dmul_ru(one_plus_ulp, one_plus_ulp));
  output->div_down = bits_of(__ddiv_rd(one, three));
  output->div_up = bits_of(__ddiv_ru(one, three));
}

}  // namespace

cudaError_t launch_directed_rounding_probe(DirectedRoundingProbeBits* output) {
  directed_rounding_probe_kernel<<<1, 1>>>(output);
  return cudaGetLastError();
}

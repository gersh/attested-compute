#pragma once

#include <cstdint>
#include <cuda_runtime_api.h>

struct DirectedRoundingProbeBits {
  std::uint64_t add_down;
  std::uint64_t add_up;
  std::uint64_t sub_down;
  std::uint64_t sub_up;
  std::uint64_t mul_down;
  std::uint64_t mul_up;
  std::uint64_t div_down;
  std::uint64_t div_up;
};

cudaError_t launch_directed_rounding_probe(DirectedRoundingProbeBits* output);

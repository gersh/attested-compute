#pragma once

#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

#include <cuda_runtime_api.h>

namespace sparkinterval::h100 {

[[noreturn]] inline void fail(const std::string& message, int status = 4) {
  std::cerr << message << '\n';
  std::exit(status);
}

// Perform policy-only checks before any CUDA API call. This keeps --help and
// malformed/forbidden CLI tests usable on a build host with no H100 attached.
inline bool preflight_help_requested(int argc, char** argv) {
  bool help_requested = false;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--op" || argument == "--input" ||
        argument == "--output" || argument == "--device" ||
        argument == "--cubin") {
      if (index + 1 < argc) {
        ++index;
      }
      continue;
    }
    if (argument == "--allow-other-device") {
      fail("--allow-other-device is disabled by the H100 runner");
    }
    help_requested = help_requested || argument == "--help";
  }
  return help_requested;
}

inline void require_device(int device) {
  int device_count = 0;
  cudaError_t status = cudaGetDeviceCount(&device_count);
  if (status != cudaSuccess) {
    fail(std::string("cudaGetDeviceCount failed: ") +
             cudaGetErrorString(status),
         3);
  }
  if (device_count != 1) {
    fail("H100 runner requires exactly one visible CUDA device");
  }
  if (device < 0 || device >= device_count) {
    fail("requested CUDA device is unavailable");
  }

  cudaDeviceProp properties{};
  status = cudaGetDeviceProperties(&properties, device);
  if (status != cudaSuccess) {
    fail(std::string("cudaGetDeviceProperties failed: ") +
             cudaGetErrorString(status),
         3);
  }
  if (properties.major != 9 || properties.minor != 0 ||
      std::string_view(properties.name).find("H100") == std::string_view::npos) {
    fail("expected an NVIDIA H100 with compute capability 9.0");
  }
}

}  // namespace sparkinterval::h100

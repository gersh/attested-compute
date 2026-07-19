// H100 device-policy wrapper around the target-neutral interval-batch runner.
//
// The included runner currently defaults to DGX Spark / GB10.  We perform a
// stricter H100 check first and then pass its explicit cross-device switch only
// within this translation unit.  This is a runtime device-selection guard, not
// hardware attestation.

#define main sparkinterval_target_neutral_interval_batch_main
#include "../../src/interval_batch_runner.cpp"
#undef main

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <string_view>
#include <vector>

namespace {

[[noreturn]] void h100_fail(const char* message, int status = 4) {
  std::cerr << message << '\n';
  std::exit(status);
}

int selected_device(int argc, char** argv) {
  int device = 0;
  for (int i = 1; i < argc; ++i) {
    const std::string_view argument(argv[i]);
    if (argument == "--allow-other-device") {
      h100_fail("--allow-other-device is disabled by the H100 runner");
    }
    if (argument != "--device") {
      continue;
    }
    if (++i >= argc) {
      h100_fail("--device requires a value", 2);
    }
    char* end = nullptr;
    errno = 0;
    const long parsed = std::strtol(argv[i], &end, 10);
    if (errno != 0 || end == argv[i] || *end != '\0' || parsed < 0 ||
        parsed > std::numeric_limits<int>::max()) {
      h100_fail("--device must be a nonnegative integer", 2);
    }
    device = static_cast<int>(parsed);
  }
  return device;
}

}  // namespace

int main(int argc, char** argv) {
  const int device = selected_device(argc, argv);
  int device_count = 0;
  cudaError_t status = cudaGetDeviceCount(&device_count);
  if (status != cudaSuccess) {
    std::cerr << "cudaGetDeviceCount failed: " << cudaGetErrorString(status)
              << '\n';
    return 3;
  }
  if (device_count != 1) {
    h100_fail("H100 runner requires exactly one visible CUDA device");
  }
  if (device >= device_count) {
    h100_fail("requested CUDA device is unavailable");
  }

  cudaDeviceProp properties{};
  status = cudaGetDeviceProperties(&properties, device);
  if (status != cudaSuccess) {
    std::cerr << "cudaGetDeviceProperties failed: "
              << cudaGetErrorString(status) << '\n';
    return 3;
  }
  if (properties.major != 9 || properties.minor != 0 ||
      std::string_view(properties.name).find("H100") == std::string_view::npos) {
    h100_fail("expected an NVIDIA H100 with compute capability 9.0");
  }

  std::vector<char*> forwarded;
  forwarded.reserve(static_cast<std::size_t>(argc) + 2);
  for (int i = 0; i < argc; ++i) {
    forwarded.push_back(argv[i]);
  }
  char internal_override[] = "--allow-other-device";
  forwarded.push_back(internal_override);
  forwarded.push_back(nullptr);
  return sparkinterval_target_neutral_interval_batch_main(
      argc + 1, forwarded.data());
}

#include "probe_kernel.h"

#include <bit>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string_view>

#include <cuda_runtime_api.h>

namespace {

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  std::cerr << operation << " failed: " << cudaGetErrorString(status) << '\n';
  std::exit(2);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) {
    fail_cuda(operation, status);
  }
}

bool expected_probe_bits(const DirectedRoundingProbeBits& value) {
  constexpr std::uint64_t one = 0x3ff0000000000000ULL;
  constexpr std::uint64_t next_after_one = 0x3ff0000000000001ULL;
  constexpr std::uint64_t prev_before_one = 0x3fefffffffffffffULL;
  constexpr std::uint64_t mul_down = 0x3ff0000000000002ULL;
  constexpr std::uint64_t mul_up = 0x3ff0000000000003ULL;
  constexpr std::uint64_t third_down = 0x3fd5555555555555ULL;
  constexpr std::uint64_t third_up = 0x3fd5555555555556ULL;

  return value.add_down == one && value.add_up == next_after_one &&
         value.sub_down == prev_before_one && value.sub_up == one &&
         value.mul_down == mul_down && value.mul_up == mul_up &&
         value.div_down == third_down && value.div_up == third_up;
}

void print_hex_field(const char* name, std::uint64_t value, bool trailing) {
  std::cout << "    \"" << name << "\": \"0x" << std::hex
            << std::setw(16) << std::setfill('0') << value << std::dec << "\""
            << (trailing ? "," : "") << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  bool allow_other_device = false;
  for (int i = 1; i < argc; ++i) {
    if (std::string_view(argv[i]) == "--allow-other-device") {
      allow_other_device = true;
    } else {
      std::cerr << "unknown argument: " << argv[i] << '\n';
      return 2;
    }
  }

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !allow_other_device) {
    std::cerr << "expected exactly one CUDA device, found " << device_count << '\n';
    return 3;
  }
  if (device_count < 1) {
    std::cerr << "no CUDA device found\n";
    return 3;
  }

  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties", cudaGetDeviceProperties(&properties, 0));
  if ((properties.major != 12 || properties.minor != 1) && !allow_other_device) {
    std::cerr << "expected compute capability 12.1, found " << properties.major
              << '.' << properties.minor << '\n';
    return 3;
  }

  DirectedRoundingProbeBits* device_output = nullptr;
  check_cuda("cudaMalloc",
             cudaMalloc(reinterpret_cast<void**>(&device_output),
                        sizeof(*device_output)));
  check_cuda("cudaMemset", cudaMemset(device_output, 0xa5, sizeof(*device_output)));
  check_cuda("kernel launch", launch_directed_rounding_probe(device_output));
  check_cuda("cudaDeviceSynchronize", cudaDeviceSynchronize());

  DirectedRoundingProbeBits host_output{};
  check_cuda("cudaMemcpy", cudaMemcpy(&host_output, device_output,
                                      sizeof(host_output), cudaMemcpyDeviceToHost));
  check_cuda("cudaFree", cudaFree(device_output));

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));

  const bool passed = expected_probe_bits(host_output);
  std::cout << "{\n"
            << "  \"schema_version\": 1,\n"
            << "  \"evidence_class\": \"local_unattested\",\n"
            << "  \"device_name\": \"" << properties.name << "\",\n"
            << "  \"compute_capability\": \"" << properties.major << '.'
            << properties.minor << "\",\n"
            << "  \"cuda_driver_api_version\": " << driver_version << ",\n"
            << "  \"cuda_runtime_version\": " << runtime_version << ",\n"
            << "  \"directed_rounding_bits\": {\n";
  print_hex_field("add_down", host_output.add_down, true);
  print_hex_field("add_up", host_output.add_up, true);
  print_hex_field("sub_down", host_output.sub_down, true);
  print_hex_field("sub_up", host_output.sub_up, true);
  print_hex_field("mul_down", host_output.mul_down, true);
  print_hex_field("mul_up", host_output.mul_up, true);
  print_hex_field("div_down", host_output.div_down, true);
  print_hex_field("div_up", host_output.div_up, false);
  std::cout << "  },\n"
            << "  \"passed\": " << (passed ? "true" : "false") << ",\n"
            << "  \"hardware_attestation\": null\n"
            << "}\n";

  return passed ? 0 : 4;
}

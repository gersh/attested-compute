#include <cuda.h>

#include <array>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {

constexpr std::array<std::uint64_t, 8> kExpected = {
    0x3ff0000000000000ULL,
    0x3ff0000000000001ULL,
    0x3fefffffffffffffULL,
    0x3ff0000000000000ULL,
    0x3ff0000000000002ULL,
    0x3ff0000000000003ULL,
    0x3fd5555555555555ULL,
    0x3fd5555555555556ULL,
};

constexpr std::array<const char*, 8> kNames = {
    "add_down", "add_up", "sub_down", "sub_up",
    "mul_down", "mul_up", "div_down", "div_up",
};

void check_cuda(CUresult status, const char* operation) {
  if (status == CUDA_SUCCESS) {
    return;
  }
  const char* name = "unknown";
  const char* description = "unknown CUDA driver error";
  (void)cuGetErrorName(status, &name);
  (void)cuGetErrorString(status, &description);
  throw std::runtime_error(std::string(operation) + " failed: " + name +
                           " (" + description + ")");
}

void usage(const char* executable) {
  std::cout << "usage: " << executable << " --cubin FILE\n"
            << "Loads the fixed H100 directed-rounding probe and requires one "
               "compute-capability 9.0 device.\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::string cubin_path;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--help" || argument == "-h") {
      usage(argv[0]);
      return 0;
    }
    if (argument == "--cubin" && index + 1 < argc) {
      cubin_path = argv[++index];
      continue;
    }
    std::cerr << "unknown or incomplete argument: " << argument << '\n';
    return 64;
  }
  if (cubin_path.empty()) {
    usage(argv[0]);
    return 64;
  }

  CUdevice device = 0;
  CUcontext context = nullptr;
  CUmodule module = nullptr;
  CUdeviceptr device_output = 0;
  bool primary_context_retained = false;
  try {
    check_cuda(cuInit(0), "cuInit");
    int count = 0;
    check_cuda(cuDeviceGetCount(&count), "cuDeviceGetCount");
    if (count != 1) {
      throw std::runtime_error("H100 acceptance requires exactly one CUDA device");
    }
    check_cuda(cuDeviceGet(&device, 0), "cuDeviceGet");
    int major = 0;
    int minor = 0;
    check_cuda(cuDeviceGetAttribute(
                   &major, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, device),
               "cuDeviceGetAttribute(major)");
    check_cuda(cuDeviceGetAttribute(
                   &minor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, device),
               "cuDeviceGetAttribute(minor)");
    if (major != 9 || minor != 0) {
      throw std::runtime_error("H100 probe requires compute capability 9.0");
    }
    char device_name[256]{};
    check_cuda(cuDeviceGetName(device_name, sizeof(device_name), device),
               "cuDeviceGetName");
    if (std::string_view(device_name).find("H100") == std::string_view::npos) {
      throw std::runtime_error("compute capability is 9.0 but device name is not H100");
    }

    check_cuda(cuDevicePrimaryCtxRetain(&context, device),
               "cuDevicePrimaryCtxRetain");
    primary_context_retained = true;
    check_cuda(cuCtxSetCurrent(context), "cuCtxSetCurrent");
    check_cuda(cuModuleLoad(&module, cubin_path.c_str()), "cuModuleLoad");
    CUfunction function = nullptr;
    check_cuda(cuModuleGetFunction(
                   &function, module, "h100_directed_rounding_probe"),
               "cuModuleGetFunction");
    check_cuda(cuMemAlloc(&device_output, sizeof(std::uint64_t) * kExpected.size()),
               "cuMemAlloc");
    check_cuda(cuMemsetD8(device_output, 0xa5,
                         sizeof(std::uint64_t) * kExpected.size()),
               "cuMemsetD8");
    void* kernel_arguments[] = {&device_output};
    check_cuda(cuLaunchKernel(function, 1, 1, 1, 1, 1, 1, 0, nullptr,
                              kernel_arguments, nullptr),
               "cuLaunchKernel");
    check_cuda(cuCtxSynchronize(), "cuCtxSynchronize");

    std::array<std::uint64_t, 8> result{};
    check_cuda(cuMemcpyDtoH(result.data(), device_output,
                           sizeof(std::uint64_t) * result.size()),
               "cuMemcpyDtoH");
    const bool passed = result == kExpected;
    std::cout << "{\n"
              << "  \"schema_version\": 1,\n"
              << "  \"evidence_class\": \"local_unattested\",\n"
              << "  \"device_name\": \"" << device_name << "\",\n"
              << "  \"compute_capability\": \"9.0\",\n"
              << "  \"directed_rounding_bits\": {\n";
    for (std::size_t index = 0; index < result.size(); ++index) {
      std::cout << "    \"" << kNames[index] << "\": \"0x" << std::hex
                << std::setw(16) << std::setfill('0') << result[index] << std::dec
                << "\"" << (index + 1 == result.size() ? "\n" : ",\n");
    }
    std::cout << "  },\n"
              << "  \"passed\": " << (passed ? "true" : "false") << ",\n"
              << "  \"hardware_attestation\": null\n"
              << "}\n";

    check_cuda(cuMemFree(device_output), "cuMemFree");
    device_output = 0;
    check_cuda(cuModuleUnload(module), "cuModuleUnload");
    module = nullptr;
    check_cuda(cuDevicePrimaryCtxRelease(device), "cuDevicePrimaryCtxRelease");
    primary_context_retained = false;
    return passed ? 0 : 4;
  } catch (const std::exception& error) {
    std::cerr << "h100-probe-runner: " << error.what() << '\n';
    if (device_output != 0) {
      (void)cuMemFree(device_output);
    }
    if (module != nullptr) {
      (void)cuModuleUnload(module);
    }
    if (primary_context_retained) {
      (void)cuDevicePrimaryCtxRelease(device);
    }
    return 2;
  }
}

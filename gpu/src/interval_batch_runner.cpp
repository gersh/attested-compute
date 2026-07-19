#include "interval_batch.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <cuda_runtime_api.h>

namespace {

constexpr std::array<unsigned char, 8> kInputMagic = {
    'S', 'I', 'B', '6', '4', 'I', '0', '1'};
constexpr std::array<unsigned char, 8> kOutputMagic = {
    'S', 'I', 'B', '6', '4', 'O', '0', '1'};
constexpr std::uint32_t kFormatVersion = 1;
constexpr std::size_t kHeaderBytes = 24;
constexpr std::size_t kInputRowBytes = 16;
constexpr std::size_t kOutputRowBytes = 24;

struct Options {
  IntervalBatchOperation operation{};
  std::filesystem::path input_path;
  std::filesystem::path output_path;
  int device = 0;
  bool allow_other_device = false;
};

[[noreturn]] void fail(const std::string& message, int code = 2) {
  std::cerr << message << '\n';
  std::exit(code);
}

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  fail(std::string(operation) + " failed: " + cudaGetErrorString(status), 3);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) {
    fail_cuda(operation, status);
  }
}

IntervalBatchOperation parse_operation(std::string_view value) {
  if (value == "add") return IntervalBatchOperation::add;
  if (value == "sub") return IntervalBatchOperation::sub;
  if (value == "mul") return IntervalBatchOperation::mul;
  if (value == "div") return IntervalBatchOperation::div;
  fail("--op must be one of: add, sub, mul, div");
}

const char* operation_name(IntervalBatchOperation operation) {
  switch (operation) {
    case IntervalBatchOperation::add: return "add";
    case IntervalBatchOperation::sub: return "sub";
    case IntervalBatchOperation::mul: return "mul";
    case IntervalBatchOperation::div: return "div";
  }
  return "invalid";
}

Options parse_options(int argc, char** argv) {
  Options options;
  bool have_operation = false;
  for (int i = 1; i < argc; ++i) {
    const std::string_view argument(argv[i]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++i >= argc) fail(std::string(name) + " requires a value");
      return argv[i];
    };
    if (argument == "--op") {
      options.operation = parse_operation(require_value("--op"));
      have_operation = true;
    } else if (argument == "--input") {
      options.input_path = std::string(require_value("--input"));
    } else if (argument == "--output") {
      options.output_path = std::string(require_value("--output"));
    } else if (argument == "--device") {
      const std::string value(require_value("--device"));
      char* end = nullptr;
      errno = 0;
      const long parsed = std::strtol(value.c_str(), &end, 10);
      if (errno != 0 || end == value.c_str() || *end != '\0' || parsed < 0 ||
          parsed > std::numeric_limits<int>::max()) {
        fail("--device must be a nonnegative integer");
      }
      options.device = static_cast<int>(parsed);
    } else if (argument == "--allow-other-device") {
      options.allow_other_device = true;
    } else if (argument == "--help") {
      std::cout
          << "usage: sparkinterval-interval-batch --op OP --input FILE "
             "--output FILE [--device N] [--allow-other-device]\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (!have_operation || options.input_path.empty() || options.output_path.empty()) {
    fail("--op, --input, and --output are required (use --help for details)");
  }
  return options;
}

std::uint32_t decode_u32(const unsigned char* bytes) {
  std::uint32_t value = 0;
  for (unsigned int i = 0; i < 4; ++i) {
    value |= static_cast<std::uint32_t>(bytes[i]) << (8 * i);
  }
  return value;
}

std::uint64_t decode_u64(const unsigned char* bytes) {
  std::uint64_t value = 0;
  for (unsigned int i = 0; i < 8; ++i) {
    value |= static_cast<std::uint64_t>(bytes[i]) << (8 * i);
  }
  return value;
}

void encode_u32(std::vector<unsigned char>& bytes, std::size_t offset,
                std::uint32_t value) {
  for (unsigned int i = 0; i < 4; ++i) {
    bytes[offset + i] = static_cast<unsigned char>(value >> (8 * i));
  }
}

void encode_u64(std::vector<unsigned char>& bytes, std::size_t offset,
                std::uint64_t value) {
  for (unsigned int i = 0; i < 8; ++i) {
    bytes[offset + i] = static_cast<unsigned char>(value >> (8 * i));
  }
}

std::vector<unsigned char> read_file(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) fail("cannot open input file: " + path.string());
  const std::streamoff length = input.tellg();
  if (length < 0 || static_cast<unsigned long long>(length) >
                        std::numeric_limits<std::size_t>::max()) {
    fail("input file has unsupported size");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(length));
  input.seekg(0);
  if (!bytes.empty() &&
      !input.read(reinterpret_cast<char*>(bytes.data()), length)) {
    fail("cannot read complete input file: " + path.string());
  }
  return bytes;
}

void write_file(const std::filesystem::path& path,
                const std::vector<unsigned char>& bytes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) fail("cannot open output file: " + path.string());
  if (!bytes.empty()) {
    output.write(reinterpret_cast<const char*>(bytes.data()),
                 static_cast<std::streamsize>(bytes.size()));
  }
  output.close();
  if (!output) fail("cannot write complete output file: " + path.string());
}

std::vector<IntervalBatchInput> parse_input(
    const std::vector<unsigned char>& bytes, IntervalBatchOperation operation) {
  if (bytes.size() < kHeaderBytes) fail("input is shorter than its header");
  if (!std::equal(kInputMagic.begin(), kInputMagic.end(), bytes.begin())) {
    fail("input has wrong magic (expected SIB64I01)");
  }
  if (decode_u32(bytes.data() + 8) != kFormatVersion) {
    fail("input has unsupported format version");
  }
  if (decode_u32(bytes.data() + 12) != static_cast<std::uint32_t>(operation)) {
    fail("input operation does not match --op");
  }
  const std::uint64_t encoded_count = decode_u64(bytes.data() + 16);
  if (encoded_count == 0) fail("input row_count must be positive");
  if (encoded_count > (std::numeric_limits<std::size_t>::max() - kHeaderBytes) /
                          kInputRowBytes) {
    fail("input row_count exceeds host address space");
  }
  const std::size_t row_count = static_cast<std::size_t>(encoded_count);
  const std::size_t expected_size = kHeaderBytes + row_count * kInputRowBytes;
  if (bytes.size() != expected_size) {
    fail("input length does not exactly match row_count");
  }
  std::vector<IntervalBatchInput> rows(row_count);
  for (std::size_t i = 0; i < row_count; ++i) {
    const std::size_t offset = kHeaderBytes + i * kInputRowBytes;
    rows[i].lhs_bits = decode_u64(bytes.data() + offset);
    rows[i].rhs_bits = decode_u64(bytes.data() + offset + 8);
  }
  return rows;
}

std::vector<unsigned char> encode_output(
    const std::vector<IntervalBatchOutput>& rows,
    IntervalBatchOperation operation) {
  if (rows.size() > (std::numeric_limits<std::size_t>::max() - kHeaderBytes) /
                        kOutputRowBytes) {
    fail("output size exceeds host address space");
  }
  std::vector<unsigned char> bytes(kHeaderBytes + rows.size() * kOutputRowBytes);
  std::copy(kOutputMagic.begin(), kOutputMagic.end(), bytes.begin());
  encode_u32(bytes, 8, kFormatVersion);
  encode_u32(bytes, 12, static_cast<std::uint32_t>(operation));
  encode_u64(bytes, 16, rows.size());
  for (std::size_t i = 0; i < rows.size(); ++i) {
    const std::size_t offset = kHeaderBytes + i * kOutputRowBytes;
    encode_u64(bytes, offset, rows[i].down_bits);
    encode_u64(bytes, offset + 8, rows[i].up_bits);
    bytes[offset + 16] = rows[i].status;
    for (std::size_t j = 17; j < kOutputRowBytes; ++j) {
      bytes[offset + j] = rows[i].reserved[j - 17];
    }
  }
  return bytes;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const std::vector<unsigned char> input_bytes = read_file(options.input_path);
  const std::vector<IntervalBatchInput> inputs =
      parse_input(input_bytes, options.operation);

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device; use --allow-other-device only for "
         "explicit cross-device testing", 4);
  }
  if (options.device >= device_count) fail("requested CUDA device is unavailable", 4);
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));

  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if ((std::string_view(properties.name) != "NVIDIA GB10" ||
       properties.major != 12 || properties.minor != 1) &&
      !options.allow_other_device) {
    fail("expected an NVIDIA GB10 with compute capability 12.1; use "
         "--allow-other-device only for explicit cross-device testing", 4);
  }

  IntervalBatchInput* device_inputs = nullptr;
  IntervalBatchOutput* device_outputs = nullptr;
  if (inputs.size() >
      std::numeric_limits<std::size_t>::max() / sizeof(IntervalBatchOutput)) {
    fail("batch is too large for output allocation");
  }
  const std::size_t input_size = inputs.size() * sizeof(IntervalBatchInput);
  const std::size_t output_size = inputs.size() * sizeof(IntervalBatchOutput);
  check_cuda("cudaMalloc(inputs)",
             cudaMalloc(reinterpret_cast<void**>(&device_inputs), input_size));
  check_cuda("cudaMalloc(outputs)",
             cudaMalloc(reinterpret_cast<void**>(&device_outputs), output_size));
  check_cuda("cudaMemcpy(inputs)",
             cudaMemcpy(device_inputs, inputs.data(), input_size,
                        cudaMemcpyHostToDevice));
  check_cuda("cudaMemset(outputs)", cudaMemset(device_outputs, 0xa5, output_size));

  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(stop)", cudaEventCreate(&stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  check_cuda("kernel launch",
             launch_interval_batch(device_inputs, device_outputs, inputs.size(),
                                   options.operation));
  check_cuda("cudaEventRecord(stop)", cudaEventRecord(stop));
  check_cuda("cudaEventSynchronize(stop)", cudaEventSynchronize(stop));
  float kernel_milliseconds = 0.0F;
  check_cuda("cudaEventElapsedTime",
             cudaEventElapsedTime(&kernel_milliseconds, start, stop));

  std::vector<IntervalBatchOutput> outputs(inputs.size());
  check_cuda("cudaMemcpy(outputs)",
             cudaMemcpy(outputs.data(), device_outputs, output_size,
                        cudaMemcpyDeviceToHost));
  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(stop)", cudaEventDestroy(stop));
  check_cuda("cudaFree(inputs)", cudaFree(device_inputs));
  check_cuda("cudaFree(outputs)", cudaFree(device_outputs));

  write_file(options.output_path, encode_output(outputs, options.operation));

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));
  const double rows_per_second = kernel_milliseconds > 0.0F
      ? static_cast<double>(inputs.size()) * 1000.0 / kernel_milliseconds
      : 0.0;
  std::cout << "{\n"
            << "  \"schema_version\": 1,\n"
            << "  \"operation\": \"" << operation_name(options.operation) << "\",\n"
            << "  \"row_count\": " << inputs.size() << ",\n"
            << "  \"device_name\": \"" << properties.name << "\",\n"
            << "  \"compute_capability\": \"" << properties.major << '.'
            << properties.minor << "\",\n"
            << "  \"cuda_driver_api_version\": " << driver_version << ",\n"
            << "  \"cuda_runtime_version\": " << runtime_version << ",\n"
            << "  \"kernel_milliseconds\": " << std::fixed
            << std::setprecision(6) << kernel_milliseconds << ",\n"
            << "  \"kernel_rows_per_second\": " << std::fixed
            << std::setprecision(3) << rows_per_second << "\n"
            << "}\n";
  return 0;
}

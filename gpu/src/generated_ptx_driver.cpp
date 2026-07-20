#include <cuda.h>

#include "generated_ptx_driver_report.hpp"
#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr std::array<unsigned char, 8> kInputMagic = {
    'S', 'I', 'G', '6', '4', 'I', '0', '1'};
constexpr std::array<unsigned char, 8> kOutputMagic = {
    'S', 'I', 'G', '6', '4', 'O', '0', '1'};
constexpr std::uint32_t kFormatVersion = 1;
constexpr std::uint32_t kGeneratedAbiVersion = 1;
constexpr std::uint32_t kMaxVariables = 64;
constexpr std::uint64_t kMaxRows = 1'000'000;
constexpr std::uint64_t kMaxInputBytes = 1ULL << 30;
constexpr std::uint64_t kMaxPtxBytes = 64ULL << 20;
constexpr std::size_t kHeaderBytes = 24;
constexpr std::size_t kIntervalBytes = 16;
constexpr std::size_t kOutputBytes = 24;
constexpr std::uint64_t kSignMask = 0x8000000000000000ULL;
constexpr std::uint64_t kExponentMask = 0x7ff0000000000000ULL;
constexpr std::uint64_t kFractionMask = 0x000fffffffffffffULL;
constexpr std::uint64_t kSentinelNan = 0x7ff80000000005a5ULL;
constexpr std::uint64_t kNegativeInfinity = 0xfff0000000000000ULL;
constexpr std::uint64_t kPositiveInfinity = 0x7ff0000000000000ULL;

struct Options {
  enum class ModuleKind { unset, cubin, ptx_jit } module_kind = ModuleKind::unset;
  enum class Target { unset, sm_121, sm_90 } target = Target::unset;
  std::filesystem::path module_path;
  std::filesystem::path input_path;
  std::filesystem::path output_path;
  int device = 0;
  bool allow_other_device = false;
  std::string expected_module_sha256;
  std::string expected_input_sha256;
  std::string challenge_nonce;
};

const char* target_token(Options::Target target) {
  switch (target) {
    case Options::Target::sm_121: return "sm_121";
    case Options::Target::sm_90: return "sm_90";
    case Options::Target::unset: break;
  }
  return "unset";
}

const char* target_device_policy(Options::Target target) {
  switch (target) {
    case Options::Target::sm_121:
      return "exact-NVIDIA-GB10-compute-capability-12.1";
    case Options::Target::sm_90:
      return "NVIDIA-H100-name-and-compute-capability-9.0";
    case Options::Target::unset: break;
  }
  return "unset";
}

struct Interval {
  std::uint64_t lo_bits;
  std::uint64_t hi_bits;
};

static_assert(sizeof(Interval) == kIntervalBytes);

struct alignas(8) Output {
  std::uint64_t lo_bits;
  std::uint64_t hi_bits;
  std::uint8_t status;
  std::uint8_t reserved[7];
};

static_assert(sizeof(Output) == kOutputBytes);

struct ParsedInput {
  std::uint32_t variable_count = 0;
  std::size_t row_count = 0;
  std::vector<Interval> rows;
};

[[noreturn]] void fail(const std::string& message, int code = 2) {
  std::cerr << message << '\n';
  std::exit(code);
}

[[noreturn]] void fail_cuda(const char* operation, CUresult status) {
  const char* name = nullptr;
  const char* description = nullptr;
  cuGetErrorName(status, &name);
  cuGetErrorString(status, &description);
  fail(std::string(operation) + " failed: " +
           (name == nullptr ? "unknown CUDA error" : name) + " (" +
           (description == nullptr ? "no description" : description) + ")",
       3);
}

void check_cuda(const char* operation, CUresult status) {
  if (status != CUDA_SUCCESS) fail_cuda(operation, status);
}

bool lowercase_hex_digest(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(value.begin(), value.end(), [](char byte) {
           return (byte >= '0' && byte <= '9') ||
                  (byte >= 'a' && byte <= 'f');
         });
}

Options parse_options(int argc, char** argv) {
  Options options;
  auto set_module = [&](Options::ModuleKind kind,
                        const std::filesystem::path& path) {
    if (options.module_kind != Options::ModuleKind::unset) {
      fail("exactly one of --cubin or --ptx may be supplied");
    }
    options.module_kind = kind;
    options.module_path = path;
  };
  for (int i = 1; i < argc; ++i) {
    const std::string_view argument(argv[i]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++i >= argc) fail(std::string(name) + " requires a value");
      return argv[i];
    };
    if (argument == "--ptx") {
      set_module(Options::ModuleKind::ptx_jit,
                 std::string(require_value("--ptx")));
    } else if (argument == "--cubin") {
      set_module(Options::ModuleKind::cubin,
                 std::string(require_value("--cubin")));
    } else if (argument == "--input") {
      options.input_path = std::string(require_value("--input"));
    } else if (argument == "--output") {
      options.output_path = std::string(require_value("--output"));
    } else if (argument == "--target") {
      if (options.target != Options::Target::unset) {
        fail("--target may be supplied only once");
      }
      const std::string_view value = require_value("--target");
      if (value == "sm_121") {
        options.target = Options::Target::sm_121;
      } else if (value == "sm_90") {
        options.target = Options::Target::sm_90;
      } else {
        fail("--target must be exactly sm_121 or sm_90");
      }
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
    } else if (argument == "--expected-module-sha256" ||
               argument == "--expected-cubin-sha256") {
      if (!options.expected_module_sha256.empty()) {
        fail("expected module SHA-256 may be supplied only once");
      }
      options.expected_module_sha256 =
          std::string(require_value(argument == "--expected-module-sha256"
                                        ? "--expected-module-sha256"
                                        : "--expected-cubin-sha256"));
      if (!lowercase_hex_digest(options.expected_module_sha256)) {
        fail("expected module SHA-256 must be 64 lowercase hex characters");
      }
    } else if (argument == "--expected-input-sha256") {
      if (!options.expected_input_sha256.empty()) {
        fail("expected input SHA-256 may be supplied only once");
      }
      options.expected_input_sha256 =
          std::string(require_value("--expected-input-sha256"));
      if (!lowercase_hex_digest(options.expected_input_sha256)) {
        fail("expected input SHA-256 must be 64 lowercase hex characters");
      }
    } else if (argument == "--challenge-nonce") {
      if (!options.challenge_nonce.empty()) {
        fail("challenge nonce may be supplied only once");
      }
      options.challenge_nonce =
          std::string(require_value("--challenge-nonce"));
      if (!lowercase_hex_digest(options.challenge_nonce)) {
        fail("challenge nonce must be 32 bytes encoded as 64 lowercase hex "
             "characters");
      }
    } else if (argument == "--help") {
      std::cout << "usage: sparkinterval-generated-driver "
                   "(--cubin KERNEL.cubin | --ptx DEVELOPMENT.ptx) "
                   "--input ROWS.bin --output RESULTS.bin "
                   "--expected-module-sha256 HEX "
                   "--expected-input-sha256 HEX "
                   "--target {sm_121|sm_90} "
                   "[--challenge-nonce HEX] "
                   "[--device N] [--allow-other-device]\n"
                   "The two expected hashes are mandatory for --cubin and "
                   "optional for development --ptx runs.  The input hash "
                   "covers only the interval payload copied to the GPU.\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.module_kind == Options::ModuleKind::unset ||
      options.module_path.empty() || options.input_path.empty() ||
      options.output_path.empty() || options.target == Options::Target::unset) {
    fail("exactly one of --cubin or --ptx, plus --input and --output, is "
         "required; --target must explicitly select sm_121 or sm_90 "
         "(use --help)");
  }
  if (options.target == Options::Target::sm_90 && options.allow_other_device) {
    fail("--allow-other-device is disabled for target sm_90");
  }
  if (options.module_kind == Options::ModuleKind::cubin &&
      (options.expected_module_sha256.empty() ||
       options.expected_input_sha256.empty())) {
    fail("--cubin acceptance requires --expected-module-sha256 and "
         "--expected-input-sha256");
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

std::vector<unsigned char> read_binary(const std::filesystem::path& path,
                                       std::uint64_t limit,
                                       const char* what) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) fail(std::string("cannot open ") + what + ": " + path.string());
  const std::streamoff length = input.tellg();
  if (length < 0 || static_cast<unsigned long long>(length) > limit ||
      static_cast<unsigned long long>(length) >
          std::numeric_limits<std::size_t>::max()) {
    fail(std::string(what) + " has unsupported size");
  }
  std::vector<unsigned char> bytes(static_cast<std::size_t>(length));
  input.seekg(0);
  if (!bytes.empty() &&
      !input.read(reinterpret_cast<char*>(bytes.data()), length)) {
    fail(std::string("cannot read complete ") + what);
  }
  return bytes;
}

void write_binary(const std::filesystem::path& path,
                  const std::vector<unsigned char>& bytes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) fail("cannot open output file: " + path.string());
  output.write(reinterpret_cast<const char*>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  output.close();
  if (!output) fail("cannot write complete output file: " + path.string());
}

bool finite_bits(std::uint64_t bits) {
  return (bits & kExponentMask) != kExponentMask;
}

bool nan_bits(std::uint64_t bits) {
  return (bits & kExponentMask) == kExponentMask &&
         (bits & kFractionMask) != 0;
}

bool zero_bits(std::uint64_t bits) {
  return (bits & ~kSignMask) == 0;
}

int endpoint_compare(std::uint64_t left, std::uint64_t right) {
  if (zero_bits(left) && zero_bits(right)) return 0;
  const bool left_negative = (left & kSignMask) != 0;
  const bool right_negative = (right & kSignMask) != 0;
  if (left_negative != right_negative) return left_negative ? -1 : 1;
  if (left == right) return 0;
  if (left_negative) return left > right ? -1 : 1;
  return left < right ? -1 : 1;
}

std::size_t checked_product(std::size_t left, std::size_t right,
                            const char* what) {
  if (left != 0 && right > std::numeric_limits<std::size_t>::max() / left) {
    fail(std::string(what) + " exceeds host address space");
  }
  return left * right;
}

ParsedInput parse_input(const std::vector<unsigned char>& bytes) {
  if (bytes.size() < kHeaderBytes) fail("row input is shorter than its header");
  if (!std::equal(kInputMagic.begin(), kInputMagic.end(), bytes.begin())) {
    fail("row input has wrong magic (expected SIG64I01)");
  }
  if (decode_u32(bytes.data() + 8) != kFormatVersion) {
    fail("row input has unsupported format version");
  }
  const std::uint32_t variable_count = decode_u32(bytes.data() + 12);
  const std::uint64_t encoded_row_count = decode_u64(bytes.data() + 16);
  if (variable_count > kMaxVariables) fail("row input variable count exceeds 64");
  if (encoded_row_count == 0 || encoded_row_count > kMaxRows ||
      encoded_row_count > std::numeric_limits<std::size_t>::max()) {
    fail("row input row count is outside the supported range");
  }
  const std::size_t row_count = static_cast<std::size_t>(encoded_row_count);
  const std::size_t interval_count =
      checked_product(row_count, variable_count, "row interval count");
  const std::size_t payload_bytes =
      checked_product(interval_count, kIntervalBytes, "row payload");
  if (payload_bytes > std::numeric_limits<std::size_t>::max() - kHeaderBytes ||
      bytes.size() != kHeaderBytes + payload_bytes) {
    fail("row input length does not exactly match its header");
  }
  ParsedInput result;
  result.variable_count = variable_count;
  result.row_count = row_count;
  result.rows.resize(interval_count);
  for (std::size_t index = 0; index < interval_count; ++index) {
    const std::size_t offset = kHeaderBytes + index * kIntervalBytes;
    Interval& interval = result.rows[index];
    interval.lo_bits = decode_u64(bytes.data() + offset);
    interval.hi_bits = decode_u64(bytes.data() + offset + 8);
    if (!finite_bits(interval.lo_bits) || !finite_bits(interval.hi_bits)) {
      fail("row input interval " + std::to_string(index) +
           " must have finite endpoints");
    }
    if (endpoint_compare(interval.lo_bits, interval.hi_bits) > 0) {
      fail("row input interval " + std::to_string(index) +
           " has decreasing endpoints");
    }
  }
  return result;
}

std::uint32_t read_module_u32(CUmodule module, const char* name) {
  CUdeviceptr address = 0;
  std::size_t bytes = 0;
  check_cuda("cuModuleGetGlobal", cuModuleGetGlobal(&address, &bytes, module, name));
  if (bytes != sizeof(std::uint32_t)) {
    fail(std::string("generated PTX global has wrong size: ") + name, 3);
  }
  std::uint32_t result = 0;
  check_cuda("cuMemcpyDtoH", cuMemcpyDtoH(&result, address, sizeof(result)));
  return result;
}

std::vector<unsigned char> encode_output(const ParsedInput& input,
                                         const std::vector<Output>& rows) {
  const std::size_t payload = rows.size() * kOutputBytes;
  std::vector<unsigned char> bytes(kHeaderBytes + payload, 0);
  std::copy(kOutputMagic.begin(), kOutputMagic.end(), bytes.begin());
  encode_u32(bytes, 8, kFormatVersion);
  encode_u32(bytes, 12, input.variable_count);
  encode_u64(bytes, 16, input.row_count);
  for (std::size_t row = 0; row < rows.size(); ++row) {
    const std::size_t offset = kHeaderBytes + row * kOutputBytes;
    encode_u64(bytes, offset, rows[row].lo_bits);
    encode_u64(bytes, offset + 8, rows[row].hi_bits);
    bytes[offset + 16] = rows[row].status;
    for (std::size_t index = 0; index < 7; ++index) {
      bytes[offset + 17 + index] = rows[row].reserved[index];
    }
  }
  return bytes;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const std::vector<unsigned char> input_file_bytes =
      read_binary(options.input_path, kMaxInputBytes, "row input");
  const ParsedInput input = parse_input(input_file_bytes);
  std::vector<unsigned char> module_bytes = read_binary(
      options.module_path, kMaxPtxBytes,
      options.module_kind == Options::ModuleKind::cubin ? "generated cubin"
                                                        : "generated PTX");
  if (module_bytes.empty()) fail("generated CUDA module must not be empty");
  if (options.module_kind == Options::ModuleKind::ptx_jit) {
    if (std::find(module_bytes.begin(), module_bytes.end(), 0) !=
        module_bytes.end()) {
      fail("generated PTX must not contain embedded NUL bytes");
    }
    module_bytes.push_back(0);
  } else if (module_bytes.size() < 4 || module_bytes[0] != 0x7f ||
             module_bytes[1] != 'E' || module_bytes[2] != 'L' ||
             module_bytes[3] != 'F') {
    fail("generated cubin must be a CUDA ELF image");
  }

  // These values bind the exact in-memory byte ranges used below.  For PTX,
  // module_bytes includes the terminating NUL passed to cuModuleLoadDataEx.
  // The input digest covers the parsed Interval array passed to cuMemcpyHtoD,
  // not the framing header in ROWS.bin.
  const std::size_t input_bytes = input.rows.size() * sizeof(Interval);
  const std::string module_sha256 =
      sparkinterval::sha256_hex(module_bytes.data(), module_bytes.size());
  const std::string input_sha256 =
      sparkinterval::sha256_hex(input.rows.data(), input_bytes);
  if (!options.expected_module_sha256.empty() &&
      module_sha256 != options.expected_module_sha256) {
    fail("in-memory CUDA module SHA-256 does not match expected value");
  }
  if (!options.expected_input_sha256.empty() &&
      input_sha256 != options.expected_input_sha256) {
    fail("in-memory GPU input payload SHA-256 does not match expected value");
  }

  // Acceptance hash mismatches fail above, before any CUDA API call or GPU
  // state change.
  check_cuda("cuInit", cuInit(0));
  int cuda_driver_version = 0;
  check_cuda("cuDriverGetVersion", cuDriverGetVersion(&cuda_driver_version));
  int device_count = 0;
  check_cuda("cuDeviceGetCount", cuDeviceGetCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device, found " +
             std::to_string(device_count),
         3);
  }
  if (device_count < 1 || options.device >= device_count) {
    fail("requested CUDA device is unavailable", 3);
  }
  CUdevice device = 0;
  check_cuda("cuDeviceGet", cuDeviceGet(&device, options.device));
  int major = 0;
  int minor = 0;
  char device_name[256] = {};
  CUuuid device_uuid{};
  check_cuda("cuDeviceGetName",
             cuDeviceGetName(device_name, sizeof(device_name), device));
  check_cuda("cuDeviceGetUuid", cuDeviceGetUuid(&device_uuid, device));
  check_cuda("cuDeviceGetAttribute(major)",
             cuDeviceGetAttribute(&major,
                                  CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR,
                                  device));
  check_cuda("cuDeviceGetAttribute(minor)",
             cuDeviceGetAttribute(&minor,
                                  CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR,
                                  device));
  if (!options.allow_other_device) {
    if (options.target == Options::Target::sm_121) {
      if (major != 12 || minor != 1) {
        fail("target sm_121 requires compute capability 12.1, found " +
                 std::to_string(major) + "." + std::to_string(minor),
             3);
      }
      if (std::string_view(device_name) != "NVIDIA GB10") {
        fail("target sm_121 requires exact device name NVIDIA GB10, found " +
                 std::string(device_name),
             3);
      }
    } else if (options.target == Options::Target::sm_90) {
      if (major != 9 || minor != 0) {
        fail("target sm_90 requires compute capability 9.0, found " +
                 std::to_string(major) + "." + std::to_string(minor),
             3);
      }
      if (std::string_view(device_name).find("H100") ==
          std::string_view::npos) {
        fail("target sm_90 requires an NVIDIA H100 device name, found " +
                 std::string(device_name),
             3);
      }
    }
  }

  CUcontext context = nullptr;
  check_cuda("cuCtxCreate", cuCtxCreate(&context, nullptr, 0, device));
  CUmodule module = nullptr;
  if (options.module_kind == Options::ModuleKind::cubin) {
    // Acceptance executes these exact offline-assembled bytes.  The PTX path
    // below is retained only as an explicitly named development/JIT mode.
    check_cuda("cuModuleLoadData(cubin)",
               cuModuleLoadData(&module, module_bytes.data()));
  } else {
    check_cuda("cuModuleLoadDataEx(PTX JIT)",
               cuModuleLoadDataEx(&module, module_bytes.data(), 0, nullptr,
                                  nullptr));
  }
  if (read_module_u32(module, "sparkinterval_generated_abi_version") !=
      kGeneratedAbiVersion) {
    fail("generated PTX ABI version mismatch", 3);
  }
  if (read_module_u32(module, "sparkinterval_generated_variable_count") !=
      input.variable_count) {
    fail("row input variable_count does not match generated PTX", 3);
  }
  CUfunction kernel = nullptr;
  check_cuda("cuModuleGetFunction",
             cuModuleGetFunction(&kernel, module, "sparkinterval_generated"));

  CUdeviceptr device_rows = 0;
  CUdeviceptr device_outputs = 0;
  const std::size_t output_bytes = input.row_count * sizeof(Output);
  if (input_bytes != 0) {
    check_cuda("cuMemAlloc(rows)", cuMemAlloc(&device_rows, input_bytes));
    check_cuda("cuMemcpyHtoD(rows)",
               cuMemcpyHtoD(device_rows, input.rows.data(), input_bytes));
  }
  check_cuda("cuMemAlloc(outputs)", cuMemAlloc(&device_outputs, output_bytes));
  Output sentinel{};
  sentinel.lo_bits = kSentinelNan;
  sentinel.hi_bits = kSentinelNan;
  sentinel.status = 0xa5;
  std::fill(std::begin(sentinel.reserved), std::end(sentinel.reserved), 0xa5);
  std::vector<Output> outputs(input.row_count, sentinel);
  check_cuda("cuMemcpyHtoD(output sentinel)",
             cuMemcpyHtoD(device_outputs, outputs.data(), output_bytes));

  std::uint64_t row_count_argument = input.row_count;
  void* arguments[] = {&device_rows, &device_outputs, &row_count_argument};
  constexpr unsigned int threads = 256;
  const std::uint64_t blocks64 =
      (input.row_count + threads - 1) / threads;
  if (blocks64 > std::numeric_limits<unsigned int>::max()) {
    fail("grid dimension exceeds CUDA launch ABI", 3);
  }
  check_cuda("cuLaunchKernel",
             cuLaunchKernel(kernel, static_cast<unsigned int>(blocks64), 1, 1,
                            threads, 1, 1, 0, nullptr, arguments, nullptr));
  check_cuda("cuCtxSynchronize", cuCtxSynchronize());
  check_cuda("cuMemcpyDtoH(outputs)",
             cuMemcpyDtoH(outputs.data(), device_outputs, output_bytes));

  for (std::size_t row = 0; row < outputs.size(); ++row) {
    const Output& value = outputs[row];
    if (value.lo_bits == kSentinelNan || value.hi_bits == kSentinelNan) {
      fail("GPU did not overwrite output row " + std::to_string(row), 4);
    }
    for (std::uint8_t reserved : value.reserved) {
      if (reserved != 0) {
        fail("GPU left nonzero reserved output at row " +
                 std::to_string(row),
             4);
      }
    }
    if (nan_bits(value.lo_bits) || nan_bits(value.hi_bits) ||
        endpoint_compare(value.lo_bits, value.hi_bits) > 0) {
      fail("GPU produced an invalid interval at row " + std::to_string(row),
           4);
    }
    if (value.status == 0) {
      // A final directed operation may legitimately overflow to infinity.
    } else if (value.status == 2) {
      if (value.lo_bits != kNegativeInfinity ||
          value.hi_bits != kPositiveInfinity) {
        fail("GPU status 2 must carry the exact whole interval at row " +
                 std::to_string(row),
             4);
      }
    } else {
      fail("GPU produced an unsupported output status at row " +
               std::to_string(row),
           4);
    }
  }

  check_cuda("cuMemFree(outputs)", cuMemFree(device_outputs));
  if (device_rows != 0) check_cuda("cuMemFree(rows)", cuMemFree(device_rows));
  check_cuda("cuModuleUnload", cuModuleUnload(module));
  check_cuda("cuCtxDestroy", cuCtxDestroy(context));
  const std::vector<unsigned char> output_file_bytes =
      encode_output(input, outputs);
  const std::string output_sha256 = sparkinterval::sha256_hex(
      output_file_bytes.data(), output_file_bytes.size());
  // write_binary writes this same vector and fails unless the complete stream
  // is successfully closed, so the reported digest is of the exact bytes
  // written to RESULTS.bin.
  write_binary(options.output_path, output_file_bytes);
  constexpr char hex[] = "0123456789abcdef";
  std::string device_uuid_hex;
  device_uuid_hex.reserve(32);
  for (char raw_byte : device_uuid.bytes) {
    const auto byte = static_cast<unsigned char>(raw_byte);
    device_uuid_hex.push_back(hex[byte >> 4]);
    device_uuid_hex.push_back(hex[byte & 0xf]);
  }
  sparkinterval::write_generated_driver_report(
      std::cout,
      {
          .allow_other_device = options.allow_other_device,
          .compute_capability_major = major,
          .compute_capability_minor = minor,
          .cuda_driver_version = cuda_driver_version,
          .device_count = device_count,
          .device_index = options.device,
          .device_name = device_name,
          .device_uuid = device_uuid_hex,
          .challenge_nonce = options.challenge_nonce,
          .input_payload_sha256 = input_sha256,
          .input_payload_size_bytes = input_bytes,
          .module_sha256 = module_sha256,
          .module_size_bytes = module_bytes.size(),
          .module_kind = options.module_kind == Options::ModuleKind::cubin
                             ? "offline_cubin"
                             : "ptx_jit_development",
          .output_file_sha256 = output_sha256,
          .output_file_size_bytes = output_file_bytes.size(),
          .row_count = input.row_count,
          .target = target_token(options.target),
          .target_device_policy = target_device_policy(options.target),
      });
  return 0;
}

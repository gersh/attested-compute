#include "expression_batch.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
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
    'S', 'I', 'E', '6', '4', 'I', '0', '1'};
constexpr std::array<unsigned char, 8> kOutputMagic = {
    'S', 'I', 'E', '6', '4', 'O', '0', '1'};
constexpr std::size_t kHeaderBytes = 32;
constexpr std::size_t kInstructionBytes = 24;
constexpr std::size_t kIntervalBytes = 16;
constexpr std::size_t kOutputBytes = 24;
constexpr std::uint64_t kSignMask = 0x8000000000000000ULL;
constexpr std::uint64_t kExponentMask = 0x7ff0000000000000ULL;
constexpr std::uint64_t kFractionMask = 0x000fffffffffffffULL;
constexpr std::uint64_t kPositiveInfinity = 0x7ff0000000000000ULL;
constexpr std::uint64_t kNegativeInfinity = 0xfff0000000000000ULL;

struct Options {
  std::filesystem::path input_path;
  std::filesystem::path output_path;
  int device = 0;
  bool allow_other_device = false;
};

struct ParsedInput {
  std::vector<ExpressionInstruction> program;
  std::vector<ExpressionInterval> variables;
  std::size_t variable_count = 0;
  std::size_t max_stack_depth = 0;
  std::size_t row_count = 0;
};

struct OutputCounts {
  std::size_t valid = 0;
  std::size_t divisor_contains_zero = 0;
  std::size_t nonfinite_intermediate_widening = 0;
};

[[noreturn]] void fail(const std::string& message, int code = 2) {
  std::cerr << message << '\n';
  std::exit(code);
}

[[noreturn]] void fail_cuda(const char* operation, cudaError_t status) {
  fail(std::string(operation) + " failed: " + cudaGetErrorString(status), 3);
}

void check_cuda(const char* operation, cudaError_t status) {
  if (status != cudaSuccess) fail_cuda(operation, status);
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int i = 1; i < argc; ++i) {
    const std::string_view argument(argv[i]);
    auto require_value = [&](const char* name) -> std::string_view {
      if (++i >= argc) fail(std::string(name) + " requires a value");
      return argv[i];
    };
    if (argument == "--input") {
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
      std::cout << "usage: sparkinterval-expression-batch --input FILE "
                   "--output FILE [--device N] [--allow-other-device]\n";
      std::exit(0);
    } else {
      fail("unknown argument: " + std::string(argument));
    }
  }
  if (options.input_path.empty() || options.output_path.empty()) {
    fail("--input and --output are required (use --help for details)");
  }
  return options;
}

std::uint16_t decode_u16(const unsigned char* bytes) {
  return static_cast<std::uint16_t>(bytes[0]) |
         static_cast<std::uint16_t>(bytes[1]) << 8;
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
  if (static_cast<unsigned long long>(length) >
      kExpressionMaxInputFileBytes) {
    fail("input file exceeds the explicit 256 MiB resource limit");
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

void validate_finite_interval(std::uint64_t lo_bits, std::uint64_t hi_bits,
                              const std::string& what) {
  if (!finite_bits(lo_bits) || !finite_bits(hi_bits)) {
    fail(what + " must have finite endpoints");
  }
  if (endpoint_compare(lo_bits, hi_bits) > 0) {
    fail(what + " has decreasing endpoints");
  }
}

std::size_t checked_product(std::size_t left, std::size_t right,
                            const char* what) {
  if (left != 0 && right > std::numeric_limits<std::size_t>::max() / left) {
    fail(std::string(what) + " exceeds host address space");
  }
  return left * right;
}

std::size_t checked_sum(std::size_t left, std::size_t right,
                        const char* what) {
  if (right > std::numeric_limits<std::size_t>::max() - left) {
    fail(std::string(what) + " exceeds host address space");
  }
  return left + right;
}

std::uint32_t validate_program(
    const std::vector<ExpressionInstruction>& program,
    std::size_t variable_count) {
  std::uint32_t stack_depth = 0;
  std::uint32_t maximum_stack_depth = 0;
  for (std::size_t pc = 0; pc < program.size(); ++pc) {
    const ExpressionInstruction& instruction = program[pc];
    const std::string prefix = "instruction " + std::to_string(pc);
    if (instruction.flags != 0 || instruction.reserved != 0) {
      fail(prefix + " has nonzero reserved fields");
    }
    const ExpressionOpcode opcode =
        static_cast<ExpressionOpcode>(instruction.opcode);
    switch (opcode) {
      case ExpressionOpcode::constant:
        if (instruction.argument != 0) {
          fail(prefix + " constant argument must be zero");
        }
        validate_finite_interval(instruction.lo_bits, instruction.hi_bits,
                                 prefix + " constant");
        if (stack_depth >= kExpressionMaxStackDepth) {
          fail("program exceeds the fixed GPU stack depth");
        }
        ++stack_depth;
        break;
      case ExpressionOpcode::variable:
        if (instruction.lo_bits != 0 || instruction.hi_bits != 0) {
          fail(prefix + " variable endpoint payload must be zero");
        }
        if (instruction.argument >= variable_count) {
          fail(prefix + " variable index is outside variable_count");
        }
        if (stack_depth >= kExpressionMaxStackDepth) {
          fail("program exceeds the fixed GPU stack depth");
        }
        ++stack_depth;
        break;
      case ExpressionOpcode::neg:
      case ExpressionOpcode::abs:
        if (instruction.argument != 0 || instruction.lo_bits != 0 ||
            instruction.hi_bits != 0) {
          fail(prefix + " unary payload must be zero");
        }
        if (stack_depth < 1) fail(prefix + " underflows the postfix stack");
        break;
      case ExpressionOpcode::pow_nat:
        if (instruction.lo_bits != 0 || instruction.hi_bits != 0) {
          fail(prefix + " pow_nat endpoint payload must be zero");
        }
        if (instruction.argument > kExpressionMaxPowExponent) {
          fail(prefix + " pow_nat exponent exceeds the format limit");
        }
        if (stack_depth < 1) fail(prefix + " underflows the postfix stack");
        break;
      case ExpressionOpcode::add:
      case ExpressionOpcode::sub:
      case ExpressionOpcode::mul:
      case ExpressionOpcode::div:
      case ExpressionOpcode::minimum:
      case ExpressionOpcode::maximum:
        if (instruction.argument != 0 || instruction.lo_bits != 0 ||
            instruction.hi_bits != 0) {
          fail(prefix + " binary payload must be zero");
        }
        if (stack_depth < 2) fail(prefix + " underflows the postfix stack");
        --stack_depth;
        break;
      default:
        fail(prefix + " has an unsupported opcode");
    }
    maximum_stack_depth = std::max(maximum_stack_depth, stack_depth);
  }
  if (stack_depth != 1) {
    fail("postfix program must finish with exactly one stack value");
  }
  return maximum_stack_depth;
}

ParsedInput parse_input(const std::vector<unsigned char>& bytes) {
  if (bytes.size() < kHeaderBytes) fail("input is shorter than its header");
  if (!std::equal(kInputMagic.begin(), kInputMagic.end(), bytes.begin())) {
    fail("input has wrong magic (expected SIE64I01)");
  }
  if (decode_u32(bytes.data() + 8) != kExpressionFormatVersion) {
    fail("input has unsupported format version");
  }
  const std::uint32_t instruction_count = decode_u32(bytes.data() + 12);
  const std::uint32_t variable_count = decode_u32(bytes.data() + 16);
  const std::uint32_t encoded_max_stack_depth = decode_u32(bytes.data() + 20);
  const std::uint64_t encoded_row_count = decode_u64(bytes.data() + 24);
  if (instruction_count == 0 ||
      instruction_count > kExpressionMaxInstructions) {
    fail("instruction_count is outside the supported range");
  }
  if (variable_count > kExpressionMaxVariables) {
    fail("variable_count exceeds the supported limit");
  }
  if (encoded_max_stack_depth == 0 ||
      encoded_max_stack_depth > kExpressionMaxStackDepth) {
    fail("max_stack_depth is outside the supported range");
  }
  if (encoded_row_count == 0 || encoded_row_count > kExpressionMaxRows ||
      encoded_row_count > std::numeric_limits<std::size_t>::max()) {
    fail("row_count is outside the supported range");
  }
  const std::size_t row_count = static_cast<std::size_t>(encoded_row_count);
  const std::size_t instruction_payload =
      checked_product(instruction_count, kInstructionBytes,
                      "instruction payload");
  const std::size_t interval_count =
      checked_product(row_count, variable_count, "input interval count");
  const std::size_t row_payload =
      checked_product(interval_count, kIntervalBytes, "row payload");
  const std::size_t expected_size =
      checked_sum(checked_sum(kHeaderBytes, instruction_payload, "input size"),
                  row_payload, "input size");
  if (bytes.size() != expected_size) {
    fail("input length does not exactly match its header");
  }

  ParsedInput result;
  result.variable_count = variable_count;
  result.max_stack_depth = encoded_max_stack_depth;
  result.row_count = row_count;
  result.program.resize(instruction_count);
  for (std::size_t pc = 0; pc < instruction_count; ++pc) {
    const std::size_t offset = kHeaderBytes + pc * kInstructionBytes;
    ExpressionInstruction& instruction = result.program[pc];
    instruction.opcode = bytes[offset];
    instruction.flags = bytes[offset + 1];
    instruction.reserved = decode_u16(bytes.data() + offset + 2);
    instruction.argument = decode_u32(bytes.data() + offset + 4);
    instruction.lo_bits = decode_u64(bytes.data() + offset + 8);
    instruction.hi_bits = decode_u64(bytes.data() + offset + 16);
  }
  const std::uint32_t actual_max_stack_depth =
      validate_program(result.program, variable_count);
  if (actual_max_stack_depth != encoded_max_stack_depth) {
    fail("encoded max_stack_depth does not match the validated program");
  }

  result.variables.resize(interval_count);
  const std::size_t rows_offset = kHeaderBytes + instruction_payload;
  for (std::size_t index = 0; index < interval_count; ++index) {
    const std::size_t offset = rows_offset + index * kIntervalBytes;
    ExpressionInterval& interval = result.variables[index];
    interval.lo_bits = decode_u64(bytes.data() + offset);
    interval.hi_bits = decode_u64(bytes.data() + offset + 8);
    validate_finite_interval(
        interval.lo_bits, interval.hi_bits,
        "input interval " + std::to_string(index));
  }
  return result;
}

OutputCounts validate_outputs(
    const std::vector<ExpressionBatchOutput>& outputs) {
  OutputCounts counts;
  for (std::size_t row = 0; row < outputs.size(); ++row) {
    const ExpressionBatchOutput& output = outputs[row];
    for (std::uint8_t byte : output.reserved) {
      if (byte != 0) {
        fail("GPU output row " + std::to_string(row) +
                 " retained a sentinel/reserved byte",
             5);
      }
    }
    const auto status = static_cast<ExpressionBatchStatus>(output.status);
    if (status == ExpressionBatchStatus::valid) {
      if (nan_bits(output.lo_bits) || nan_bits(output.hi_bits) ||
          endpoint_compare(output.lo_bits, output.hi_bits) > 0) {
        fail("GPU output row " + std::to_string(row) +
                 " has invalid result endpoints",
             5);
      }
      ++counts.valid;
    } else if (status == ExpressionBatchStatus::divisor_contains_zero) {
      if (output.lo_bits != 0 || output.hi_bits != 0) {
        fail("GPU invalid output row " + std::to_string(row) +
                 " has nonzero endpoint words",
             5);
      }
      ++counts.divisor_contains_zero;
    } else if (status ==
               ExpressionBatchStatus::nonfinite_intermediate_widening) {
      if (output.lo_bits != kNegativeInfinity ||
          output.hi_bits != kPositiveInfinity) {
        fail("GPU widening output row " + std::to_string(row) +
                 " is not the exact whole interval",
             5);
      }
      ++counts.nonfinite_intermediate_widening;
    } else {
      fail("GPU output row " + std::to_string(row) +
               " reported an execution error or unknown status",
           5);
    }
  }
  return counts;
}

std::vector<unsigned char> encode_output(
    const ParsedInput& input,
    const std::vector<ExpressionBatchOutput>& outputs) {
  const std::size_t payload =
      checked_product(outputs.size(), kOutputBytes, "output payload");
  std::vector<unsigned char> bytes(
      checked_sum(kHeaderBytes, payload, "output size"));
  std::copy(kOutputMagic.begin(), kOutputMagic.end(), bytes.begin());
  encode_u32(bytes, 8, kExpressionFormatVersion);
  encode_u32(bytes, 12, static_cast<std::uint32_t>(input.program.size()));
  encode_u32(bytes, 16, static_cast<std::uint32_t>(input.variable_count));
  encode_u32(bytes, 20, static_cast<std::uint32_t>(input.max_stack_depth));
  encode_u64(bytes, 24, outputs.size());
  for (std::size_t row = 0; row < outputs.size(); ++row) {
    const std::size_t offset = kHeaderBytes + row * kOutputBytes;
    encode_u64(bytes, offset, outputs[row].lo_bits);
    encode_u64(bytes, offset + 8, outputs[row].hi_bits);
    bytes[offset + 16] = outputs[row].status;
    for (std::size_t i = 0; i < 7; ++i) {
      bytes[offset + 17 + i] = outputs[row].reserved[i];
    }
  }
  return bytes;
}

std::string json_escape(std::string_view value) {
  std::string result;
  result.reserve(value.size());
  for (unsigned char character : value) {
    switch (character) {
      case '"': result += "\\\""; break;
      case '\\': result += "\\\\"; break;
      case '\b': result += "\\b"; break;
      case '\f': result += "\\f"; break;
      case '\n': result += "\\n"; break;
      case '\r': result += "\\r"; break;
      case '\t': result += "\\t"; break;
      default:
        if (character < 0x20) {
          constexpr char digits[] = "0123456789abcdef";
          result += "\\u00";
          result += digits[character >> 4];
          result += digits[character & 0x0f];
        } else {
          result += static_cast<char>(character);
        }
    }
  }
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  const Options options = parse_options(argc, argv);
  const ParsedInput input = parse_input(read_file(options.input_path));

  int device_count = 0;
  check_cuda("cudaGetDeviceCount", cudaGetDeviceCount(&device_count));
  if (device_count != 1 && !options.allow_other_device) {
    fail("expected exactly one CUDA device; use --allow-other-device only for "
         "explicit cross-device testing",
         4);
  }
  if (options.device >= device_count) {
    fail("requested CUDA device is unavailable", 4);
  }
  check_cuda("cudaSetDevice", cudaSetDevice(options.device));

  cudaDeviceProp properties{};
  check_cuda("cudaGetDeviceProperties",
             cudaGetDeviceProperties(&properties, options.device));
  if ((std::string_view(properties.name) != "NVIDIA GB10" ||
       properties.major != 12 || properties.minor != 1) &&
      !options.allow_other_device) {
    fail("expected an NVIDIA GB10 with compute capability 12.1; use "
         "--allow-other-device only for explicit cross-device testing",
         4);
  }

  const std::size_t program_size =
      checked_product(input.program.size(), sizeof(ExpressionInstruction),
                      "device program allocation");
  const std::size_t variables_size =
      checked_product(input.variables.size(), sizeof(ExpressionInterval),
                      "device variable allocation");
  const std::size_t outputs_size =
      checked_product(input.row_count, sizeof(ExpressionBatchOutput),
                      "device output allocation");
  ExpressionInstruction* device_program = nullptr;
  ExpressionInterval* device_variables = nullptr;
  ExpressionBatchOutput* device_outputs = nullptr;
  check_cuda("cudaMalloc(program)",
             cudaMalloc(reinterpret_cast<void**>(&device_program), program_size));
  if (variables_size != 0) {
    check_cuda("cudaMalloc(variables)",
               cudaMalloc(reinterpret_cast<void**>(&device_variables),
                          variables_size));
  }
  check_cuda("cudaMalloc(outputs)",
             cudaMalloc(reinterpret_cast<void**>(&device_outputs), outputs_size));
  check_cuda("cudaMemcpy(program)",
             cudaMemcpy(device_program, input.program.data(), program_size,
                        cudaMemcpyHostToDevice));
  if (variables_size != 0) {
    check_cuda("cudaMemcpy(variables)",
               cudaMemcpy(device_variables, input.variables.data(), variables_size,
                          cudaMemcpyHostToDevice));
  }
  check_cuda("cudaMemset(outputs sentinel)",
             cudaMemset(device_outputs, 0xa5, outputs_size));

  cudaEvent_t start = nullptr;
  cudaEvent_t stop = nullptr;
  check_cuda("cudaEventCreate(start)", cudaEventCreate(&start));
  check_cuda("cudaEventCreate(stop)", cudaEventCreate(&stop));
  check_cuda("cudaEventRecord(start)", cudaEventRecord(start));
  check_cuda("kernel launch",
             launch_expression_batch(
                 device_program, input.program.size(), device_variables,
                 input.variable_count, device_outputs, input.row_count));
  check_cuda("cudaEventRecord(stop)", cudaEventRecord(stop));
  check_cuda("cudaEventSynchronize(stop)", cudaEventSynchronize(stop));
  float kernel_milliseconds = 0.0F;
  check_cuda("cudaEventElapsedTime",
             cudaEventElapsedTime(&kernel_milliseconds, start, stop));

  std::vector<ExpressionBatchOutput> outputs(input.row_count);
  check_cuda("cudaMemcpy(outputs)",
             cudaMemcpy(outputs.data(), device_outputs, outputs_size,
                        cudaMemcpyDeviceToHost));
  check_cuda("cudaEventDestroy(start)", cudaEventDestroy(start));
  check_cuda("cudaEventDestroy(stop)", cudaEventDestroy(stop));
  check_cuda("cudaFree(program)", cudaFree(device_program));
  if (device_variables != nullptr) {
    check_cuda("cudaFree(variables)", cudaFree(device_variables));
  }
  check_cuda("cudaFree(outputs)", cudaFree(device_outputs));

  const OutputCounts output_counts = validate_outputs(outputs);
  write_file(options.output_path, encode_output(input, outputs));

  int driver_version = 0;
  int runtime_version = 0;
  check_cuda("cudaDriverGetVersion", cudaDriverGetVersion(&driver_version));
  check_cuda("cudaRuntimeGetVersion", cudaRuntimeGetVersion(&runtime_version));
  const double rows_per_second = kernel_milliseconds > 0.0F
      ? static_cast<double>(input.row_count) * 1000.0 / kernel_milliseconds
      : 0.0;
  std::cout << "{\n"
            << "  \"schema_version\": 1,\n"
            << "  \"kind\": \"sparkinterval_cuda_expression_batch\",\n"
            << "  \"instruction_count\": " << input.program.size() << ",\n"
            << "  \"variable_count\": " << input.variable_count << ",\n"
            << "  \"max_stack_depth\": " << input.max_stack_depth << ",\n"
            << "  \"row_count\": " << input.row_count << ",\n"
            << "  \"valid_row_count\": " << output_counts.valid << ",\n"
            << "  \"zero_divisor_row_count\": "
            << output_counts.divisor_contains_zero << ",\n"
            << "  \"nonfinite_widening_row_count\": "
            << output_counts.nonfinite_intermediate_widening << ",\n"
            << "  \"all_rows_valid\": "
            << (output_counts.valid == input.row_count ? "true" : "false")
            << ",\n"
            << "  \"device_name\": \"" << json_escape(properties.name)
            << "\",\n"
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

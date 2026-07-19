#include "generated_ptx_driver_report.hpp"

#include <iostream>
#include <sstream>
#include <string>

namespace {

bool check_equal(const std::string& actual, const std::string& expected,
                 const char* case_name) {
  if (actual == expected) return true;
  std::cerr << case_name << " report mismatch\nexpected: " << expected
            << "actual:   " << actual;
  return false;
}

}  // namespace

int main(int argc, char** argv) {
  constexpr char kInputHash[] =
      "1111111111111111111111111111111111111111111111111111111111111111";
  constexpr char kModuleHash[] =
      "2222222222222222222222222222222222222222222222222222222222222222";
  constexpr char kOutputHash[] =
      "3333333333333333333333333333333333333333333333333333333333333333";
  constexpr char kNonce[] =
      "abababababababababababababababababababababababababababababababab";

  sparkinterval::GeneratedDriverReport report{
      .allow_other_device = true,
      .compute_capability_major = 12,
      .compute_capability_minor = 1,
      .cuda_driver_version = 12090,
      .device_count = 1,
      .device_index = 0,
      .device_name = "DGX \"Spark\"\nGPU\\0",
      .device_uuid = "00112233445566778899aabbccddeeff",
      .challenge_nonce = kNonce,
      .input_payload_sha256 = kInputHash,
      .input_payload_size_bytes = 32,
      .module_sha256 = kModuleHash,
      .module_size_bytes = 128,
      .module_kind = "offline_cubin",
      .output_file_sha256 = kOutputHash,
      .output_file_size_bytes = 48,
      .row_count = 1,
  };
  std::ostringstream encoded;
  sparkinterval::write_generated_driver_report(encoded, report);
  const std::string expected =
      "{\"allow_other_device\":true,\"compute_capability\":\"12.1\","
      "\"cuda_driver_version\":12090,\"device_count\":1,\"device_index\":0,"
      "\"device_name\":\"DGX \\\"Spark\\\"\\nGPU\\\\0\","
      "\"device_uuid\":\"00112233445566778899aabbccddeeff\","
      "\"byte_binding_schema_version\":1,\"challenge_nonce\":\"" +
      std::string(kNonce) +
      "\",\"input_payload_sha256\":\"" + std::string(kInputHash) +
      "\",\"input_payload_size_bytes\":32,"
      "\"kind\":\"sparkinterval_generated_driver_run\","
      "\"module_sha256\":\"" + std::string(kModuleHash) +
      "\",\"module_size_bytes\":128,\"module_kind\":\"offline_cubin\","
      "\"output_file_sha256\":\"" + std::string(kOutputHash) +
      "\",\"output_file_size_bytes\":48,\"row_count\":1,"
      "\"schema_version\":1}\n";
  if (!check_equal(encoded.str(), expected, "bound")) return 1;

  if (argc == 2 && std::string_view(argv[1]) == "--emit-json") {
    std::cout << encoded.str();
    return 0;
  }
  if (argc != 1) {
    std::cerr << "usage: generated-driver-report-test [--emit-json]\n";
    return 2;
  }

  report.allow_other_device = false;
  report.challenge_nonce = {};
  std::ostringstream without_nonce;
  sparkinterval::write_generated_driver_report(without_nonce, report);
  if (without_nonce.str().find("\"challenge_nonce\":null") ==
          std::string::npos ||
      without_nonce.str().find("\"output_file_size_bytes\":48,") ==
          std::string::npos ||
      without_nonce.str().find("\"row_count\":1,") == std::string::npos) {
    std::cerr << "nullable-nonce report has malformed typed fields\n";
    return 1;
  }
  return 0;
}

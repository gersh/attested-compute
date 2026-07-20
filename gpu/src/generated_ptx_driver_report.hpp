#pragma once

#include <cstddef>
#include <ostream>
#include <string_view>

namespace sparkinterval {

struct GeneratedDriverReport {
  bool allow_other_device;
  int compute_capability_major;
  int compute_capability_minor;
  int cuda_driver_version;
  int device_count;
  int device_index;
  std::string_view device_name;
  std::string_view device_uuid;
  std::string_view challenge_nonce;
  std::string_view input_payload_sha256;
  std::size_t input_payload_size_bytes;
  std::string_view module_sha256;
  std::size_t module_size_bytes;
  std::string_view module_kind;
  std::string_view output_file_sha256;
  std::size_t output_file_size_bytes;
  std::size_t row_count;
  std::string_view target;
  std::string_view target_device_policy;
};

inline void write_json_string(std::ostream& output, std::string_view value) {
  output << '"';
  constexpr char hex[] = "0123456789abcdef";
  for (unsigned char byte : value) {
    if (byte == '"' || byte == '\\') {
      output << '\\' << static_cast<char>(byte);
    } else if (byte == '\n') {
      output << "\\n";
    } else if (byte == '\r') {
      output << "\\r";
    } else if (byte == '\t') {
      output << "\\t";
    } else if (byte < 0x20) {
      output << "\\u00" << hex[byte >> 4] << hex[byte & 0xf];
    } else {
      output << static_cast<char>(byte);
    }
  }
  output << '"';
}

inline void write_generated_driver_report(
    std::ostream& output, const GeneratedDriverReport& report) {
  output << "{\"allow_other_device\":"
         << (report.allow_other_device ? "true" : "false")
         << ",\"compute_capability\":\"" << report.compute_capability_major
         << '.' << report.compute_capability_minor
         << "\",\"cuda_driver_version\":" << report.cuda_driver_version
         << ",\"device_count\":" << report.device_count
         << ",\"device_index\":" << report.device_index
         << ",\"device_name\":";
  write_json_string(output, report.device_name);
  output << ",\"device_uuid\":";
  write_json_string(output, report.device_uuid);
  output << ",\"byte_binding_schema_version\":1"
         << ",\"challenge_nonce\":";
  if (report.challenge_nonce.empty()) {
    output << "null";
  } else {
    write_json_string(output, report.challenge_nonce);
  }
  output << ",\"input_payload_sha256\":";
  write_json_string(output, report.input_payload_sha256);
  output << ",\"input_payload_size_bytes\":"
         << report.input_payload_size_bytes
         << ",\"kind\":\"sparkinterval_generated_driver_run\""
         << ",\"module_sha256\":";
  write_json_string(output, report.module_sha256);
  output << ",\"module_size_bytes\":" << report.module_size_bytes
         << ",\"module_kind\":";
  write_json_string(output, report.module_kind);
  output << ",\"output_file_sha256\":";
  write_json_string(output, report.output_file_sha256);
  output << ",\"output_file_size_bytes\":"
         << report.output_file_size_bytes << ",\"row_count\":"
         << report.row_count << ",\"schema_version\":1,\"target\":";
  write_json_string(output, report.target);
  output << ",\"target_device_policy\":";
  write_json_string(output, report.target_device_policy);
  output << "}\n";
}

}  // namespace sparkinterval

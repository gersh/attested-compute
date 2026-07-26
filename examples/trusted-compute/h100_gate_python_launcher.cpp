// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Static, shell-free launcher for the content-addressed H100 gate source.
// `/usr/bin/python3` and its transitive runtime remain part of the Azure
// measured-image/appraiser boundary; they are intentionally not presented as
// closure-complete merely because this launcher is static.

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <unistd.h>
#include <vector>

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "H100 gate launcher requires gate arguments\n";
    return 2;
  }
  std::vector<std::string> arguments = {
      "/usr/bin/python3", "-I", "-B",
      "attestation/azure_h100_pre_run_gate.py"};
  for (int index = 1; index < argc; ++index) arguments.emplace_back(argv[index]);
  std::vector<char*> raw_arguments;
  for (std::string& argument : arguments) raw_arguments.push_back(argument.data());
  raw_arguments.push_back(nullptr);
  std::vector<std::string> environment = {
      "HOME=/root", "LANG=C", "LC_ALL=C",
      "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
      "TZ=UTC"};
  if (const char* service_key = std::getenv("NV_ATTESTATION_SERVICE_KEY")) {
    environment.emplace_back(std::string("NV_ATTESTATION_SERVICE_KEY=") + service_key);
  }
  std::vector<char*> raw_environment;
  for (std::string& item : environment) raw_environment.push_back(item.data());
  raw_environment.push_back(nullptr);
  ::execve("/usr/bin/python3", raw_arguments.data(), raw_environment.data());
  std::cerr << "cannot exec /usr/bin/python3: " << std::strerror(errno) << '\n';
  return 127;
}

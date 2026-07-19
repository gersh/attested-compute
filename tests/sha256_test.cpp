#include "sparkinterval/sha256.hpp"

#include <iostream>
#include <string>
#include <string_view>

namespace {

bool check_hash(std::string_view input, std::string_view expected,
                const char* case_name) {
  const std::string actual =
      sparkinterval::sha256_hex(input.data(), input.size());
  if (actual == expected) return true;
  std::cerr << case_name << ": expected " << expected << ", got " << actual
            << '\n';
  return false;
}

}  // namespace

int main() {
  bool passed = true;
  passed &= check_hash(
      "", "e3b0c44298fc1c149afbf4c8996fb924"
          "27ae41e4649b934ca495991b7852b855",
      "empty");
  passed &= check_hash(
      "abc", "ba7816bf8f01cfea414140de5dae2223"
             "b00361a396177a9cb410ff61f20015ad",
      "abc");
  passed &= check_hash(
      "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
      "248d6a61d20638b8e5c026930c3e6039"
      "a33ce45964ff2167f6ecedd419db06c1",
      "multi-block");
  const std::string million_as(1'000'000, 'a');
  passed &= check_hash(
      million_as, "cdc76e5c9914fb9281a1c7e284d73e67"
                  "f1809a48a497200e046d39ccc7112cd0",
      "million-a");
  return passed ? 0 : 1;
}

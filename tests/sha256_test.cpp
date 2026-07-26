#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <cstddef>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

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

bool check_incremental(const std::vector<unsigned char>& input,
                       const std::vector<std::size_t>& chunks,
                       std::string_view expected, const char* case_name) {
  sparkinterval::detail::Sha256 hasher;
  std::size_t offset = 0;
  for (const std::size_t requested : chunks) {
    const std::size_t count = std::min(requested, input.size() - offset);
    hasher.update(input.data() + offset, count);
    offset += count;
    if (offset == input.size()) break;
  }
  if (offset != input.size()) {
    hasher.update(input.data() + offset, input.size() - offset);
  }
  const std::string actual = sparkinterval::lowercase_hex(hasher.finish());
  if (actual == expected) return true;
  std::cerr << case_name << ": expected " << expected << ", got " << actual
            << '\n';
  return false;
}

std::vector<unsigned char> patterned_input(std::size_t size) {
  std::vector<unsigned char> input(size);
  for (std::size_t index = 0; index < input.size(); ++index) {
    input[index] = static_cast<unsigned char>((index * 37U + 11U) & 0xffU);
  }
  return input;
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
  passed &= check_incremental(
      patterned_input(65), {1, 63, 1},
      "fc518669b6eb4b4dd91827ecacef8668"
      "9c725bd5bab888fd3b26dbb196eec954",
      "incremental-1-63-1");
  passed &= check_incremental(
      patterned_input(129), {63, 1, 64, 1},
      "4f1757ae4bffbae86d775b831765b75a"
      "f154d52f7deaa46dd378051a2d3ad57f",
      "incremental-63-1-64-1");
  passed &= check_incremental(
      patterned_input(1025), {7, 57, 65, 127, 256, 512, 1},
      "7bec35b7137ed53c8a2f2e7d254838c9"
      "bbd8b0d3cd93f8d006fc776f8d50ce15",
      "incremental-mixed-boundaries");
  return passed ? 0 : 1;
}

// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Compact native streaming checker for the canonical PT21 v2 block artifact.
//
// This executable is a bounded optimization of one already implemented finite
// stage.  It reads exactly the two inputs the Python reference finalizer reads
// -- one PT21SGN1 required-sign packet and one canonical fused source trace --
// re-runs every structural, sign, stationary, bracket, event, and exact
// rational Turing check with GMP, and emits the byte-identical canonical
// `sparkinterval.tg.platt-pt21-lean-block-artifact.v2` JSON document.
//
// It is deliberately NOT a replacement for the independent implementation.
// `tg_verifier/platt_pt21_fused_artifact.py` remains the deterministic
// reference oracle, and the differential known-answer test requires byte
// equality between the two.  Nothing here promotes a DD disk, an Arb interval,
// a sign bit, or a digest to a theorem about Hardy Z, and no readiness,
// attestation, or acceptance flag is produced or changed.
//
// Exactness discipline (mirrors PT21StationaryCandidateFilter):
//   * every artifact-visible quantity is computed with exact GMP rationals;
//   * outward-widened binary64 enclosures are used only as a strict-comparison
//     filter for stationary candidacy; and
//   * a comparison that is neither certified nor separated falls back to the
//     exact rational predicate.  A failed or inconclusive fast comparison is
//     never used as a decision.

#include "sparkinterval/sha256.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <gmpxx.h>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

using Digest = sparkinterval::Sha256Digest;

class ArtifactError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

// ---------------------------------------------------------------------------
// Fixed campaign geometry.  These duplicate the Python constants on purpose:
// the two implementations must be independently readable.
// ---------------------------------------------------------------------------

constexpr std::size_t kPacketHeaderBytes = 200U;
constexpr std::size_t kSampleBytes = 24U;
constexpr std::uint32_t kRequiredCount = 25'741U;
constexpr std::int32_t kRequiredOffsetLower = -12'870;
constexpr std::uint64_t kSourceLowerCenter = 10'000'000'504ULL;
constexpr std::uint64_t kSourceLower = 10'000'000'000ULL;
constexpr std::uint64_t kSourceStep = 1'008ULL;
constexpr std::uint64_t kSourceHalfStep = 504ULL;
constexpr std::uint64_t kSourceBlockCount = 2'966'443'783ULL;
constexpr std::uint64_t kExpectedSampleBytes =
    static_cast<std::uint64_t>(kRequiredCount) * kSampleBytes;
constexpr std::uint64_t kExpectedSignBytes = (kRequiredCount + 7U) / 8U;
constexpr std::uint64_t kExpectedPacketBytes =
    kPacketHeaderBytes + kExpectedSampleBytes + kExpectedSignBytes;
constexpr std::uint64_t kFnvOffset = 1'469'598'103'934'665'603ULL;
constexpr std::uint64_t kFnvPrime = 1'099'511'628'211ULL;
constexpr std::uint32_t kEndianTag = 0x01020304U;
constexpr std::size_t kMaxTraceBytes = 16U * 1024U * 1024U;
constexpr std::size_t kMaxArtifactBytes = 16U * 1024U * 1024U;
constexpr std::size_t kMaxBracketsPerStream = 10'000U;
constexpr int kSourceSpacingNumerator = 21;
constexpr int kSourceSpacingDenominator = 512;

constexpr char kPacketMagic[] = "PT21SGN1";
constexpr char kUpstreamCommit[] = "42b21426718e542daa2b006dc05ea2d7f26426e6";
constexpr char kTraceSchema[] =
    "sparkinterval.tg.platt-pt21-fused-source-trace.v1";
constexpr char kArtifactSchema[] =
    "sparkinterval.tg.platt-pt21-lean-block-artifact.v2";
constexpr char kInterpolationPatchSha256[] =
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3";

constexpr char kStreamRequestMagic[] = "PT21ABQ1";
constexpr char kStreamResponseMagic[] = "PT21ABR1";
constexpr std::size_t kStreamRequestHeaderBytes = 104U;
constexpr std::size_t kStreamResponseHeaderBytes = 112U;

struct StreamRange {
  const char* name;
  std::int32_t lower;
  std::int32_t upper;
};

// Construction order, matching the reference dict comprehension.
constexpr std::array<StreamRange, 3> kStreams = {{
    {"main", -12'288, 12'288},
    {"left_flank", -12'800, -12'288},
    {"right_flank", 12'288, 12'800},
}};

constexpr std::size_t kMainStream = 0U;
constexpr std::size_t kLeftFlankStream = 1U;
constexpr std::size_t kRightFlankStream = 2U;

// ---------------------------------------------------------------------------
// Byte helpers.
// ---------------------------------------------------------------------------

std::uint32_t load_u32(const unsigned char* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t load_u64(const unsigned char* data) {
  std::uint64_t result = 0U;
  for (unsigned int index = 0U; index < 8U; ++index) {
    result |= static_cast<std::uint64_t>(data[index]) << (8U * index);
  }
  return result;
}

void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0U; index < 4U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void store_u64(unsigned char* data, std::uint64_t value) {
  for (unsigned int index = 0U; index < 8U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

double load_binary64(const unsigned char* data) {
  return std::bit_cast<double>(load_u64(data));
}

std::uint64_t fnv1a(const unsigned char* data, std::size_t size) {
  // The PT21SGN1 v1 wire calls this FNV-1a; its offset basis is the
  // project-specific 0x14650fb0739d0383.  Keep these exact bytes.
  std::uint64_t result = kFnvOffset;
  for (std::size_t index = 0U; index < size; ++index) {
    result ^= data[index];
    result *= kFnvPrime;
  }
  return result;
}

void write_all(int descriptor, const unsigned char* data, std::size_t size) {
  std::size_t position = 0U;
  while (position < size) {
    const ssize_t wrote = ::write(descriptor, data + position, size - position);
    if (wrote < 0 && errno == EINTR) continue;
    if (wrote <= 0) throw ArtifactError("cannot write native artifact output");
    position += static_cast<std::size_t>(wrote);
  }
}

bool read_exact_or_eof(int descriptor, unsigned char* data, std::size_t size) {
  std::size_t position = 0U;
  while (position < size) {
    const ssize_t got = ::read(descriptor, data + position, size - position);
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) throw ArtifactError("cannot read native artifact stream");
    if (got == 0) {
      if (position == 0U) return false;
      throw ArtifactError("native artifact stream is truncated");
    }
    position += static_cast<std::size_t>(got);
  }
  return true;
}

std::vector<unsigned char> read_regular_file(const std::string& path,
                                             std::size_t maximum,
                                             const char* label) {
  const int descriptor = ::open(path.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (descriptor < 0) {
    throw ArtifactError(std::string(label) + " is not an openable regular file");
  }
  struct stat metadata {};
  if (::fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode)) {
    ::close(descriptor);
    throw ArtifactError(std::string(label) + " is not a regular file");
  }
  const auto size = static_cast<std::uint64_t>(metadata.st_size);
  if (size == 0U || size > maximum) {
    ::close(descriptor);
    throw ArtifactError(std::string(label) + " has an invalid byte length");
  }
  std::vector<unsigned char> result(static_cast<std::size_t>(size));
  std::size_t position = 0U;
  while (position < result.size()) {
    const ssize_t got =
        ::read(descriptor, result.data() + position, result.size() - position);
    if (got < 0 && errno == EINTR) continue;
    if (got <= 0) {
      ::close(descriptor);
      throw ArtifactError(std::string(label) + " could not be read exactly");
    }
    position += static_cast<std::size_t>(got);
  }
  unsigned char trailing = 0U;
  const ssize_t extra = ::read(descriptor, &trailing, 1U);
  ::close(descriptor);
  if (extra != 0) {
    throw ArtifactError(std::string(label) + " grew during the read");
  }
  return result;
}

// ---------------------------------------------------------------------------
// Strict JSON with exact integers, duplicate-key rejection, and Python's
// canonical `sort_keys=True, separators=(",", ":")` serialization.
// ---------------------------------------------------------------------------

struct JsonValue;
using JsonPtr = std::unique_ptr<JsonValue>;

enum class JsonKind { Object, Array, String, Integer, Boolean, Null };

struct JsonValue {
  JsonKind kind = JsonKind::Null;
  std::vector<std::pair<std::string, JsonPtr>> members;
  std::vector<JsonPtr> elements;
  std::string text;
  mpz_class integer;
  bool boolean = false;
};

class JsonParser {
 public:
  JsonParser(const unsigned char* data, std::size_t size)
      : data_(data), size_(size) {}

  JsonPtr parse_document() {
    skip_space();
    JsonPtr value = parse_value(0U);
    skip_space();
    if (position_ != size_) throw ArtifactError("JSON has trailing bytes");
    return value;
  }

 private:
  static constexpr unsigned int kMaximumDepth = 32U;

  void skip_space() {
    while (position_ < size_) {
      const unsigned char byte = data_[position_];
      if (byte == ' ' || byte == '\t' || byte == '\n' || byte == '\r') {
        ++position_;
      } else {
        break;
      }
    }
  }

  unsigned char peek() const {
    if (position_ >= size_) throw ArtifactError("JSON ended unexpectedly");
    return data_[position_];
  }

  void expect(char value) {
    if (peek() != static_cast<unsigned char>(value)) {
      throw ArtifactError("JSON token differs from the expected delimiter");
    }
    ++position_;
  }

  bool literal(std::string_view value) {
    if (size_ - position_ < value.size()) return false;
    if (std::memcmp(data_ + position_, value.data(), value.size()) != 0) {
      return false;
    }
    position_ += value.size();
    return true;
  }

  JsonPtr parse_value(unsigned int depth) {
    if (depth > kMaximumDepth) throw ArtifactError("JSON nesting is too deep");
    const unsigned char byte = peek();
    if (byte == '{') return parse_object(depth);
    if (byte == '[') return parse_array(depth);
    if (byte == '"') {
      auto result = std::make_unique<JsonValue>();
      result->kind = JsonKind::String;
      result->text = parse_string();
      return result;
    }
    if (byte == '-' || (byte >= '0' && byte <= '9')) return parse_integer();
    auto result = std::make_unique<JsonValue>();
    if (literal("true")) {
      result->kind = JsonKind::Boolean;
      result->boolean = true;
      return result;
    }
    if (literal("false")) {
      result->kind = JsonKind::Boolean;
      result->boolean = false;
      return result;
    }
    if (literal("null")) {
      result->kind = JsonKind::Null;
      return result;
    }
    throw ArtifactError("JSON value is malformed");
  }

  JsonPtr parse_object(unsigned int depth) {
    expect('{');
    auto result = std::make_unique<JsonValue>();
    result->kind = JsonKind::Object;
    skip_space();
    if (peek() == '}') {
      ++position_;
      return result;
    }
    while (true) {
      skip_space();
      std::string key = parse_string();
      for (const auto& member : result->members) {
        if (member.first == key) throw ArtifactError("duplicate JSON key");
      }
      skip_space();
      expect(':');
      skip_space();
      JsonPtr value = parse_value(depth + 1U);
      result->members.emplace_back(std::move(key), std::move(value));
      skip_space();
      const unsigned char byte = peek();
      if (byte == ',') {
        ++position_;
        continue;
      }
      if (byte == '}') {
        ++position_;
        return result;
      }
      throw ArtifactError("JSON object separator is malformed");
    }
  }

  JsonPtr parse_array(unsigned int depth) {
    expect('[');
    auto result = std::make_unique<JsonValue>();
    result->kind = JsonKind::Array;
    skip_space();
    if (peek() == ']') {
      ++position_;
      return result;
    }
    while (true) {
      skip_space();
      result->elements.push_back(parse_value(depth + 1U));
      skip_space();
      const unsigned char byte = peek();
      if (byte == ',') {
        ++position_;
        continue;
      }
      if (byte == ']') {
        ++position_;
        return result;
      }
      throw ArtifactError("JSON array separator is malformed");
    }
  }

  static void append_utf8(std::string& out, std::uint32_t code_point) {
    if (code_point < 0x80U) {
      out.push_back(static_cast<char>(code_point));
    } else if (code_point < 0x800U) {
      out.push_back(static_cast<char>(0xC0U | (code_point >> 6U)));
      out.push_back(static_cast<char>(0x80U | (code_point & 0x3FU)));
    } else if (code_point < 0x10000U) {
      out.push_back(static_cast<char>(0xE0U | (code_point >> 12U)));
      out.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3FU)));
      out.push_back(static_cast<char>(0x80U | (code_point & 0x3FU)));
    } else {
      out.push_back(static_cast<char>(0xF0U | (code_point >> 18U)));
      out.push_back(static_cast<char>(0x80U | ((code_point >> 12U) & 0x3FU)));
      out.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3FU)));
      out.push_back(static_cast<char>(0x80U | (code_point & 0x3FU)));
    }
  }

  std::uint32_t parse_hex4() {
    if (size_ - position_ < 4U) throw ArtifactError("JSON escape is truncated");
    std::uint32_t value = 0U;
    for (unsigned int index = 0U; index < 4U; ++index) {
      const unsigned char byte = data_[position_ + index];
      std::uint32_t digit = 0U;
      if (byte >= '0' && byte <= '9') {
        digit = static_cast<std::uint32_t>(byte - '0');
      } else if (byte >= 'a' && byte <= 'f') {
        digit = static_cast<std::uint32_t>(byte - 'a') + 10U;
      } else if (byte >= 'A' && byte <= 'F') {
        digit = static_cast<std::uint32_t>(byte - 'A') + 10U;
      } else {
        throw ArtifactError("JSON escape has a non-hexadecimal digit");
      }
      value = (value << 4U) | digit;
    }
    position_ += 4U;
    return value;
  }

  std::string parse_string() {
    expect('"');
    std::string result;
    while (true) {
      if (position_ >= size_) throw ArtifactError("JSON string is unterminated");
      const unsigned char byte = data_[position_++];
      if (byte == '"') return result;
      if (byte < 0x20U) {
        throw ArtifactError("JSON string has an unescaped control character");
      }
      if (byte != '\\') {
        result.push_back(static_cast<char>(byte));
        continue;
      }
      if (position_ >= size_) throw ArtifactError("JSON escape is truncated");
      const unsigned char escape = data_[position_++];
      switch (escape) {
        case '"': result.push_back('"'); break;
        case '\\': result.push_back('\\'); break;
        case '/': result.push_back('/'); break;
        case 'b': result.push_back('\b'); break;
        case 'f': result.push_back('\f'); break;
        case 'n': result.push_back('\n'); break;
        case 'r': result.push_back('\r'); break;
        case 't': result.push_back('\t'); break;
        case 'u': {
          std::uint32_t code_point = parse_hex4();
          if (code_point >= 0xD800U && code_point <= 0xDBFFU) {
            if (size_ - position_ < 2U || data_[position_] != '\\' ||
                data_[position_ + 1U] != 'u') {
              throw ArtifactError("JSON surrogate pair is incomplete");
            }
            position_ += 2U;
            const std::uint32_t low = parse_hex4();
            if (low < 0xDC00U || low > 0xDFFFU) {
              throw ArtifactError("JSON low surrogate is malformed");
            }
            code_point = 0x10000U + ((code_point - 0xD800U) << 10U) +
                         (low - 0xDC00U);
          } else if (code_point >= 0xDC00U && code_point <= 0xDFFFU) {
            throw ArtifactError("JSON has an unpaired low surrogate");
          }
          append_utf8(result, code_point);
          break;
        }
        default:
          throw ArtifactError("JSON escape is unknown");
      }
    }
  }

  JsonPtr parse_integer() {
    const std::size_t start = position_;
    if (peek() == '-') ++position_;
    if (position_ >= size_) throw ArtifactError("JSON number is truncated");
    const unsigned char first = data_[position_];
    if (first == '0') {
      ++position_;
    } else if (first >= '1' && first <= '9') {
      while (position_ < size_ && data_[position_] >= '0' &&
             data_[position_] <= '9') {
        ++position_;
      }
    } else {
      throw ArtifactError("JSON number is malformed");
    }
    if (position_ < size_) {
      const unsigned char next = data_[position_];
      if (next == '.' || next == 'e' || next == 'E') {
        // The PT21 wire language is exact: every accepted numeric leaf is a
        // JSON integer.  Fail closed rather than introduce binary64.
        throw ArtifactError("JSON number is not an exact integer");
      }
    }
    auto result = std::make_unique<JsonValue>();
    result->kind = JsonKind::Integer;
    const std::string text(reinterpret_cast<const char*>(data_ + start),
                           position_ - start);
    if (result->integer.set_str(text, 10) != 0) {
      throw ArtifactError("JSON integer could not be decoded");
    }
    return result;
  }

  const unsigned char* data_;
  std::size_t size_;
  std::size_t position_ = 0U;
};

void append_canonical_string(std::string& out, const std::string& text) {
  // Reproduces json.dumps(..., ensure_ascii=True): escape the quote and the
  // backslash, use the short forms for \b \t \n \f \r, and emit every other
  // character outside [0x20, 0x7e] as \uXXXX with surrogate pairs.
  out.push_back('"');
  std::size_t index = 0U;
  while (index < text.size()) {
    const auto byte = static_cast<unsigned char>(text[index]);
    if (byte == '"') {
      out += "\\\"";
      ++index;
    } else if (byte == '\\') {
      out += "\\\\";
      ++index;
    } else if (byte >= 0x20U && byte <= 0x7EU) {
      out.push_back(static_cast<char>(byte));
      ++index;
    } else if (byte < 0x80U) {
      switch (byte) {
        case '\b': out += "\\b"; break;
        case '\t': out += "\\t"; break;
        case '\n': out += "\\n"; break;
        case '\f': out += "\\f"; break;
        case '\r': out += "\\r"; break;
        default: {
          std::array<char, 8U> buffer{};
          std::snprintf(buffer.data(), buffer.size(), "\\u%04x", byte);
          out += buffer.data();
          break;
        }
      }
      ++index;
    } else {
      std::uint32_t code_point = 0U;
      std::size_t length = 0U;
      if ((byte & 0xE0U) == 0xC0U) {
        code_point = byte & 0x1FU;
        length = 2U;
      } else if ((byte & 0xF0U) == 0xE0U) {
        code_point = byte & 0x0FU;
        length = 3U;
      } else if ((byte & 0xF8U) == 0xF0U) {
        code_point = byte & 0x07U;
        length = 4U;
      } else {
        throw ArtifactError("JSON string is not valid UTF-8");
      }
      if (index + length > text.size()) {
        throw ArtifactError("JSON string has a truncated UTF-8 sequence");
      }
      for (std::size_t step = 1U; step < length; ++step) {
        const auto continuation = static_cast<unsigned char>(text[index + step]);
        if ((continuation & 0xC0U) != 0x80U) {
          throw ArtifactError("JSON string has a malformed UTF-8 sequence");
        }
        code_point = (code_point << 6U) | (continuation & 0x3FU);
      }
      index += length;
      std::array<char, 16U> buffer{};
      if (code_point < 0x10000U) {
        std::snprintf(buffer.data(), buffer.size(), "\\u%04x", code_point);
        out += buffer.data();
      } else {
        const std::uint32_t adjusted = code_point - 0x10000U;
        std::snprintf(buffer.data(), buffer.size(), "\\u%04x\\u%04x",
                      0xD800U + (adjusted >> 10U), 0xDC00U + (adjusted & 0x3FFU));
        out += buffer.data();
      }
    }
  }
  out.push_back('"');
}

void append_integer(std::string& out, const mpz_class& value) {
  const std::size_t needed = mpz_sizeinbase(value.get_mpz_t(), 10U) + 2U;
  const std::size_t start = out.size();
  out.resize(start + needed);
  mpz_get_str(out.data() + start, 10, value.get_mpz_t());
  out.resize(start + std::strlen(out.data() + start));
}

void append_canonical(std::string& out, const JsonValue& value) {
  switch (value.kind) {
    case JsonKind::Null: out += "null"; return;
    case JsonKind::Boolean: out += value.boolean ? "true" : "false"; return;
    case JsonKind::Integer: append_integer(out, value.integer); return;
    case JsonKind::String: append_canonical_string(out, value.text); return;
    case JsonKind::Array: {
      out.push_back('[');
      for (std::size_t index = 0U; index < value.elements.size(); ++index) {
        if (index != 0U) out.push_back(',');
        append_canonical(out, *value.elements[index]);
      }
      out.push_back(']');
      return;
    }
    case JsonKind::Object: {
      std::vector<std::size_t> order(value.members.size());
      for (std::size_t index = 0U; index < order.size(); ++index) {
        order[index] = index;
      }
      // UTF-8 byte order equals Unicode code-point order, so this reproduces
      // Python's sort_keys=True.
      std::sort(order.begin(), order.end(),
                [&value](std::size_t left, std::size_t right) {
                  return value.members[left].first < value.members[right].first;
                });
      out.push_back('{');
      for (std::size_t index = 0U; index < order.size(); ++index) {
        if (index != 0U) out.push_back(',');
        append_canonical_string(out, value.members[order[index]].first);
        out.push_back(':');
        append_canonical(out, *value.members[order[index]].second);
      }
      out.push_back('}');
      return;
    }
  }
  throw ArtifactError("internal canonical JSON kind is unknown");
}

const JsonValue& member(const JsonValue& value, std::string_view key,
                        const char* label) {
  if (value.kind != JsonKind::Object) {
    throw ArtifactError(std::string(label) + " is not a JSON object");
  }
  for (const auto& entry : value.members) {
    if (entry.first == key) return *entry.second;
  }
  throw ArtifactError(std::string(label) + " is missing a required field");
}

void require_exact_keys(const JsonValue& value,
                        const std::vector<std::string_view>& keys,
                        const char* label) {
  if (value.kind != JsonKind::Object || value.members.size() != keys.size()) {
    throw ArtifactError(std::string(label) + " fields differ");
  }
  for (const std::string_view key : keys) {
    bool found = false;
    for (const auto& entry : value.members) {
      if (entry.first == key) {
        found = true;
        break;
      }
    }
    if (!found) throw ArtifactError(std::string(label) + " fields differ");
  }
}

const mpz_class& require_integer(const JsonValue& value, const char* label) {
  if (value.kind != JsonKind::Integer) {
    throw ArtifactError(std::string(label) + " must be an integer");
  }
  return value.integer;
}

bool require_boolean(const JsonValue& value, const char* label) {
  if (value.kind != JsonKind::Boolean) {
    throw ArtifactError(std::string(label) + " must be Boolean");
  }
  return value.boolean;
}

const std::string& require_string(const JsonValue& value, const char* label) {
  if (value.kind != JsonKind::String) {
    throw ArtifactError(std::string(label) + " must be a string");
  }
  return value.text;
}

bool is_sha256_hex(const std::string& value) {
  if (value.size() != 64U) return false;
  for (const char character : value) {
    const bool digit = character >= '0' && character <= '9';
    const bool lower = character >= 'a' && character <= 'f';
    if (!digit && !lower) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Exact rational interval arithmetic.
// ---------------------------------------------------------------------------

struct Interval {
  mpq_class lo;
  mpq_class hi;
};

Interval point_interval(const mpq_class& value) { return {value, value}; }

Interval negate(const Interval& value) { return {-value.hi, -value.lo}; }

Interval add(const Interval& left, const Interval& right) {
  return {left.lo + right.lo, left.hi + right.hi};
}

Interval subtract(const Interval& left, const Interval& right) {
  return {left.lo - right.hi, left.hi - right.lo};
}

Interval multiply(const Interval& left, const Interval& right) {
  const mpq_class a = left.lo * right.lo;
  const mpq_class b = left.lo * right.hi;
  const mpq_class c = left.hi * right.lo;
  const mpq_class d = left.hi * right.hi;
  return {std::min(std::min(a, b), std::min(c, d)),
          std::max(std::max(a, b), std::max(c, d))};
}

Interval divide(const Interval& left, const Interval& right, const char* label) {
  if (right.lo <= 0 && right.hi >= 0) {
    throw ArtifactError(std::string(label) +
                        " divides by an interval containing zero");
  }
  const mpq_class inverse_lower = mpq_class(1) / right.hi;
  const mpq_class inverse_upper = mpq_class(1) / right.lo;
  return multiply(left, Interval{inverse_lower, inverse_upper});
}

bool same_interval(const Interval& left, const Interval& right) {
  return left.lo == right.lo && left.hi == right.hi;
}

mpz_class ceiling(const mpq_class& value) {
  mpz_class result;
  mpz_cdiv_q(result.get_mpz_t(), value.get_num_mpz_t(), value.get_den_mpz_t());
  return result;
}

mpz_class flooring(const mpq_class& value) {
  mpz_class result;
  mpz_fdiv_q(result.get_mpz_t(), value.get_num_mpz_t(), value.get_den_mpz_t());
  return result;
}

// ---------------------------------------------------------------------------
// Required-sign packet.
// ---------------------------------------------------------------------------

struct Sample {
  double high = 0.0;
  double low = 0.0;
  double radius = 0.0;
  bool positive = false;
};

struct DirectedInterval {
  double lower = -std::numeric_limits<double>::infinity();
  double upper = std::numeric_limits<double>::infinity();
};

struct Packet {
  std::vector<Sample> samples;
  std::vector<DirectedInterval> directed;
  std::uint64_t window_center = 0U;
  std::string sha256;
};

DirectedInterval directed_interval(const Sample& sample) {
  const double center = sample.high + sample.low;
  if (!std::isfinite(center)) return {};
  const double center_lower =
      std::nextafter(center, -std::numeric_limits<double>::infinity());
  const double center_upper =
      std::nextafter(center, std::numeric_limits<double>::infinity());
  const double lower = center_lower - sample.radius;
  const double upper = center_upper + sample.radius;
  if (!std::isfinite(lower) || !std::isfinite(upper)) return {};
  return {std::nextafter(lower, -std::numeric_limits<double>::infinity()),
          std::nextafter(upper, std::numeric_limits<double>::infinity())};
}

Interval exact_sample_interval(const Sample& sample) {
  // mpq_set_d converts a finite binary64 exactly; accepted subnormals reach
  // denominator 2^1074, so no fixed-width integer type covers the language.
  const mpq_class center = mpq_class(sample.high) + mpq_class(sample.low);
  const mpq_class radius(sample.radius);
  Interval result{center - radius, center + radius};
  if ((sample.positive && result.lo <= 0) ||
      (!sample.positive && result.hi >= 0)) {
    throw ArtifactError(
        "required sample sign is not implied by its exact DD disk");
  }
  return result;
}

Packet decode_packet(const std::vector<unsigned char>& raw,
                     const Digest* precomputed_digest) {
  if (raw.size() != kExpectedPacketBytes) {
    throw ArtifactError("required-sign packet byte length differs");
  }
  const unsigned char* header = raw.data();
  if (std::memcmp(header, kPacketMagic, 8U) != 0 || load_u32(header + 8U) != 1U ||
      load_u32(header + 12U) != kPacketHeaderBytes ||
      load_u32(header + 16U) != kEndianTag || load_u32(header + 20U) != 1U ||
      load_u32(header + 24U) != 1U || load_u32(header + 28U) != 768'000U ||
      load_u32(header + 32U) != 52'666U || load_u32(header + 36U) != 78'406U ||
      load_u32(header + 40U) != kRequiredCount || load_u32(header + 44U) != 0U ||
      load_u64(header + 56U) != kExpectedSampleBytes ||
      load_u64(header + 64U) != kExpectedSignBytes ||
      std::memcmp(header + 160U, kUpstreamCommit, 40U) != 0) {
    throw ArtifactError("required-sign fixed header differs");
  }
  const std::uint64_t window_center = load_u64(header + 48U);
  if (window_center < kSourceLowerCenter ||
      (window_center - kSourceLowerCenter) % kSourceStep != 0U ||
      (window_center - kSourceLowerCenter) / kSourceStep >= kSourceBlockCount) {
    throw ArtifactError("window center is outside the fixed campaign grid");
  }
  for (std::size_t index = 96U; index < 160U; ++index) {
    const unsigned char value = header[index];
    if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) {
      throw ArtifactError("required-sign source SHA-256 is malformed");
    }
  }
  const unsigned char* sample_raw = raw.data() + kPacketHeaderBytes;
  const unsigned char* sign_raw = sample_raw + kExpectedSampleBytes;
  if (fnv1a(sample_raw, static_cast<std::size_t>(kExpectedSampleBytes)) !=
          load_u64(header + 72U) ||
      fnv1a(sign_raw, static_cast<std::size_t>(kExpectedSignBytes)) !=
          load_u64(header + 80U)) {
    throw ArtifactError("required-sign payload checksum differs");
  }
  constexpr unsigned int used_final_bits = kRequiredCount % 8U;
  if ((sign_raw[kExpectedSignBytes - 1U] >> used_final_bits) != 0U) {
    throw ArtifactError("unused high sign bits are nonzero");
  }
  Packet packet;
  packet.window_center = window_center;
  packet.samples.reserve(kRequiredCount);
  for (std::uint32_t index = 0U; index < kRequiredCount; ++index) {
    const unsigned char* entry = sample_raw + index * kSampleBytes;
    const double high = load_binary64(entry);
    const double low = load_binary64(entry + 8U);
    const double radius = load_binary64(entry + 16U);
    if (!std::isfinite(high) || !std::isfinite(low) || !std::isfinite(radius) ||
        radius < 0.0) {
      throw ArtifactError("required-sign packet has an invalid DD disk");
    }
    const double center_lower = std::max(0.0, std::fabs(high) - std::fabs(low));
    if (!(center_lower > radius) || high == 0.0) {
      throw ArtifactError("required-sign packet has an ambiguous DD disk");
    }
    const bool positive = (sign_raw[index / 8U] & (1U << (index % 8U))) != 0U;
    if (positive != (high > 0.0)) {
      throw ArtifactError("required-sign bit differs from its DD disk");
    }
    packet.samples.push_back({high, low, radius, positive});
  }
  packet.directed.reserve(packet.samples.size());
  for (const Sample& sample : packet.samples) {
    packet.directed.push_back(directed_interval(sample));
  }
  packet.sha256 = precomputed_digest == nullptr
                      ? sparkinterval::sha256_hex(raw.data(), raw.size())
                      : sparkinterval::lowercase_hex(*precomputed_digest);
  return packet;
}

std::size_t sample_index(std::int32_t offset) {
  const std::int64_t index =
      static_cast<std::int64_t>(offset) - kRequiredOffsetLower;
  if (index < 0 || static_cast<std::uint64_t>(index) >= kRequiredCount) {
    throw ArtifactError("sample offset is outside the required-region packet");
  }
  return static_cast<std::size_t>(index);
}

class ExactSampleCache {
 public:
  explicit ExactSampleCache(const Packet& packet)
      : packet_(packet), present_(kRequiredCount, false),
        values_(kRequiredCount) {}

  const Interval& at(std::int32_t offset) {
    const std::size_t index = sample_index(offset);
    if (!present_[index]) {
      values_[index] = exact_sample_interval(packet_.samples[index]);
      present_[index] = true;
    }
    return values_[index];
  }

 private:
  const Packet& packet_;
  std::vector<bool> present_;
  std::vector<Interval> values_;
};

bool equal_sample(const Sample& left, const Sample& right) {
  return left.high == right.high && left.low == right.low &&
         left.radius == right.radius && left.positive == right.positive;
}

bool exact_stationary_candidate(ExactSampleCache& cache, const Sample& middle,
                                std::int32_t left) {
  const Interval& first = cache.at(left);
  const Interval& centre = cache.at(left + 1);
  const Interval& right = cache.at(left + 2);
  if (middle.positive) {
    return first.lo > centre.hi && right.lo > centre.hi;
  }
  return centre.lo > first.hi && centre.lo > right.hi;
}

bool stationary_candidate(const Packet& packet, ExactSampleCache& cache,
                          std::int32_t left) {
  const Sample& first = packet.samples[sample_index(left)];
  const Sample& middle = packet.samples[sample_index(left + 1)];
  const Sample& right = packet.samples[sample_index(left + 2)];
  if (first.positive != middle.positive || middle.positive != right.positive) {
    return false;
  }
  const DirectedInterval& first_interval = packet.directed[sample_index(left)];
  const DirectedInterval& middle_interval =
      packet.directed[sample_index(left + 1)];
  const DirectedInterval& right_interval =
      packet.directed[sample_index(left + 2)];
  bool certified = false;
  bool rejected = false;
  if (middle.positive) {
    certified = first_interval.lower > middle_interval.upper &&
                right_interval.lower > middle_interval.upper;
    rejected = equal_sample(first, middle) || equal_sample(right, middle) ||
               first_interval.upper <= middle_interval.lower ||
               right_interval.upper <= middle_interval.lower;
  } else {
    certified = middle_interval.lower > first_interval.upper &&
                middle_interval.lower > right_interval.upper;
    rejected = equal_sample(first, middle) || equal_sample(right, middle) ||
               middle_interval.upper <= first_interval.lower ||
               middle_interval.upper <= right_interval.lower;
  }
  if (certified) return true;
  if (rejected) return false;
  // Inconclusive binary64 comparison: the decision is taken exactly.
  return exact_stationary_candidate(cache, middle, left);
}

// ---------------------------------------------------------------------------
// Artifact structures.
// ---------------------------------------------------------------------------

enum class Resolver { Direct, StationaryLeft, StationaryRight, PinnedArbFallback };

const char* resolver_name(Resolver value) {
  switch (value) {
    case Resolver::Direct: return "direct";
    case Resolver::StationaryLeft: return "stationary_left";
    case Resolver::StationaryRight: return "stationary_right";
    case Resolver::PinnedArbFallback: return "pinned_arb_fallback";
  }
  throw ArtifactError("internal resolver tag is unknown");
}

struct Endpoint {
  Interval enclosure;
  bool positive = false;
};

Endpoint make_endpoint(const Interval& value) {
  if (value.lo > 0) return {value, true};
  if (value.hi < 0) return {value, false};
  throw ArtifactError("endpoint interval contains zero");
}

struct Bracket {
  mpq_class lower_offset;
  mpq_class upper_offset;
  Endpoint lower_value;
  Endpoint upper_value;
  Resolver resolver = Resolver::Direct;
  std::optional<std::string> fallback_receipt_sha256;
};

struct Event {
  std::int64_t left_sample = 0;
  std::int64_t right_sample = 0;
  std::int64_t multiplicity = 0;
};

struct StreamValue {
  Endpoint left_boundary;
  Endpoint right_boundary;
  std::vector<Bracket> brackets;
  std::vector<Event> events;
};

struct TuringSide {
  Interval s_bound;
  Interval log_pi;
  Interval im_gamma_integral;
  Interval pi;
  Interval quotient;
  mpz_class count;
};

struct Artifact {
  std::uint64_t block = 0U;
  std::uint64_t height_lower = 0U;
  std::uint64_t height_upper = 0U;
  std::uint64_t window_center = 0U;
  std::string required_sign_packet_sha256;
  std::string source_trace_sha256;
  std::array<StreamValue, 3U> streams;
  TuringSide lower;
  TuringSide upper;
};

// ---------------------------------------------------------------------------
// Source-trace decoding.
// ---------------------------------------------------------------------------

mpq_class parse_fraction(const JsonValue& value, const char* label) {
  require_exact_keys(value, {"numerator", "denominator"}, label);
  const mpz_class& numerator = require_integer(member(value, "numerator", label),
                                               label);
  const mpz_class& denominator =
      require_integer(member(value, "denominator", label), label);
  if (denominator < 1) {
    throw ArtifactError(std::string(label) + ".denominator is below 1");
  }
  mpz_class divisor;
  mpz_gcd(divisor.get_mpz_t(), numerator.get_mpz_t(), denominator.get_mpz_t());
  if (divisor != 1) {
    throw ArtifactError(std::string(label) + " is not in canonical lowest terms");
  }
  mpq_class result(numerator, denominator);
  result.canonicalize();
  return result;
}

Interval parse_interval(const JsonValue& value, const char* label) {
  require_exact_keys(value, {"lo", "hi"}, label);
  Interval result{parse_fraction(member(value, "lo", label), label),
                  parse_fraction(member(value, "hi", label), label)};
  if (result.lo > result.hi) {
    throw ArtifactError(std::string(label) + " is an invalid interval");
  }
  return result;
}

struct Resolution {
  std::size_t stream = 0U;
  std::int64_t outer_left_sample = 0;
  std::int64_t outer_right_sample = 0;
  mpq_class lower_offset;
  mpq_class midpoint_offset;
  mpq_class upper_offset;
  Interval lower_value;
  Interval midpoint_value;
  Interval upper_value;
};

std::int64_t to_int64(const mpz_class& value, const char* label) {
  if (!value.fits_slong_p()) {
    throw ArtifactError(std::string(label) + " does not fit a 64-bit integer");
  }
  return static_cast<std::int64_t>(value.get_si());
}

Resolution parse_resolution(const JsonValue& value, const char* label) {
  require_exact_keys(value,
                     {"stream", "outer_left_sample", "outer_right_sample",
                      "lower_offset", "midpoint_offset", "upper_offset",
                      "lower_value", "midpoint_value", "upper_value"},
                     label);
  Resolution result;
  const std::string& stream = require_string(member(value, "stream", label),
                                             label);
  bool found = false;
  for (std::size_t index = 0U; index < kStreams.size(); ++index) {
    if (stream == kStreams[index].name) {
      result.stream = index;
      found = true;
      break;
    }
  }
  if (!found) throw ArtifactError(std::string(label) + ".stream is unknown");
  result.outer_left_sample = to_int64(
      require_integer(member(value, "outer_left_sample", label), label), label);
  result.outer_right_sample = to_int64(
      require_integer(member(value, "outer_right_sample", label), label), label);
  if (result.outer_right_sample != result.outer_left_sample + 2) {
    throw ArtifactError(std::string(label) +
                        " is not one source stationary cell");
  }
  result.lower_offset = parse_fraction(member(value, "lower_offset", label),
                                       label);
  result.midpoint_offset = parse_fraction(member(value, "midpoint_offset", label),
                                          label);
  result.upper_offset = parse_fraction(member(value, "upper_offset", label),
                                       label);
  const mpq_class outer_left(result.outer_left_sample);
  const mpq_class outer_right(result.outer_right_sample);
  if (!(outer_left <= result.lower_offset &&
        result.lower_offset < result.midpoint_offset &&
        result.midpoint_offset < result.upper_offset &&
        result.upper_offset <= outer_right)) {
    throw ArtifactError(std::string(label) +
                        " dyadic offsets leave the conservative cell");
  }
  result.lower_value = parse_interval(member(value, "lower_value", label), label);
  result.midpoint_value =
      parse_interval(member(value, "midpoint_value", label), label);
  result.upper_value = parse_interval(member(value, "upper_value", label), label);
  const auto contains_zero = [](const Interval& item) {
    return item.lo <= 0 && item.hi >= 0;
  };
  if (contains_zero(result.lower_value) || contains_zero(result.midpoint_value) ||
      contains_zero(result.upper_value)) {
    throw ArtifactError(std::string(label) + " contains a zero endpoint");
  }
  const bool lower_positive = result.lower_value.lo > 0;
  const bool middle_positive = result.midpoint_value.lo > 0;
  const bool upper_positive = result.upper_value.lo > 0;
  if (lower_positive != upper_positive || lower_positive == middle_positive) {
    throw ArtifactError(std::string(label) +
                        " does not contain two strict sign changes");
  }
  return result;
}

struct SourceTrace {
  std::string sha256;
  std::vector<Resolution> resolutions;
  Interval lower_s_bound, lower_log_pi, lower_im_gamma, lower_pi;
  Interval upper_s_bound, upper_log_pi, upper_im_gamma, upper_pi;
};

void parse_turing_side(const JsonValue& value, const char* label,
                       Interval* s_bound, Interval* log_pi, Interval* im_gamma,
                       Interval* pi) {
  require_exact_keys(value, {"s_bound", "log_pi", "im_gamma_integral", "pi"},
                     label);
  *s_bound = parse_interval(member(value, "s_bound", label), label);
  *log_pi = parse_interval(member(value, "log_pi", label), label);
  *im_gamma = parse_interval(member(value, "im_gamma_integral", label), label);
  *pi = parse_interval(member(value, "pi", label), label);
  if (s_bound->lo < 0 || pi->lo <= 0) {
    throw ArtifactError(std::string(label) +
                        " S bound or pi interval has the wrong sign");
  }
}

SourceTrace parse_source_trace(const std::vector<unsigned char>& raw,
                               const std::string& packet_sha256,
                               std::uint64_t block,
                               const Digest* precomputed_digest) {
  if (raw.empty() || raw.size() > kMaxTraceBytes) {
    throw ArtifactError("source trace has an invalid byte length");
  }
  JsonParser parser(raw.data(), raw.size());
  const JsonPtr document = parser.parse_document();
  std::string canonical;
  canonical.reserve(raw.size());
  append_canonical(canonical, *document);
  canonical.push_back('\n');
  if (canonical.size() != raw.size() ||
      std::memcmp(canonical.data(), raw.data(), raw.size()) != 0) {
    throw ArtifactError("source trace is not canonical JSON with one newline");
  }
  const JsonValue& value = *document;
  require_exact_keys(value,
                     {"schema", "upstream_commit", "interpolation_patch_sha256",
                      "block", "required_sign_packet_sha256", "producer",
                      "stationary_resolutions", "turing_inputs",
                      "semantic_status"},
                     "source trace");
  const char* label = "source trace";
  if (require_string(member(value, "schema", label), label) != kTraceSchema ||
      require_string(member(value, "upstream_commit", label), label) !=
          kUpstreamCommit ||
      require_string(member(value, "interpolation_patch_sha256", label), label) !=
          kInterpolationPatchSha256 ||
      require_integer(member(value, "block", label), label) != block ||
      require_string(member(value, "required_sign_packet_sha256", label),
                     label) != packet_sha256) {
    throw ArtifactError("source trace identity differs");
  }
  const JsonValue& producer = member(value, "producer", label);
  require_exact_keys(producer,
                     {"worker_sha256", "worker_size_bytes", "precision_bits",
                      "all_required_samples_certified",
                      "all_stationary_queries_resolved"},
                     "source trace producer");
  if (!is_sha256_hex(require_string(member(producer, "worker_sha256", label),
                                    label))) {
    throw ArtifactError("producer.worker_sha256 must be lowercase SHA-256 hex");
  }
  if (require_integer(member(producer, "worker_size_bytes", label), label) < 1) {
    throw ArtifactError("producer.worker_size_bytes is below 1");
  }
  if (require_integer(member(producer, "precision_bits", label), label) != 128) {
    throw ArtifactError("source trace precision differs from 128 bits");
  }
  if (!require_boolean(member(producer, "all_required_samples_certified", label),
                       label) ||
      !require_boolean(member(producer, "all_stationary_queries_resolved", label),
                       label)) {
    throw ArtifactError("source trace advertises an incomplete block");
  }
  const JsonValue& status = member(value, "semantic_status", label);
  require_exact_keys(status,
                     {"hardy_z_endpoint_realization_proved",
                      "main_multiplicity_realization_proved",
                      "analytic_turing_realization_proved"},
                     "source trace semantic status");
  for (const auto& entry : status.members) {
    if (require_boolean(*entry.second, "semantic_status")) {
      throw ArtifactError(
          "finite source trace must not claim an unimplemented analytic "
          "realization");
    }
  }
  const JsonValue& raw_resolutions = member(value, "stationary_resolutions",
                                            label);
  if (raw_resolutions.kind != JsonKind::Array) {
    throw ArtifactError("stationary_resolutions must be a list");
  }
  SourceTrace trace;
  trace.resolutions.reserve(raw_resolutions.elements.size());
  for (const auto& element : raw_resolutions.elements) {
    trace.resolutions.push_back(
        parse_resolution(*element, "stationary_resolutions[]"));
  }
  const JsonValue& turing = member(value, "turing_inputs", label);
  require_exact_keys(turing, {"lower", "upper"}, "turing_inputs");
  parse_turing_side(member(turing, "lower", label), "turing_inputs.lower",
                    &trace.lower_s_bound, &trace.lower_log_pi,
                    &trace.lower_im_gamma, &trace.lower_pi);
  parse_turing_side(member(turing, "upper", label), "turing_inputs.upper",
                    &trace.upper_s_bound, &trace.upper_log_pi,
                    &trace.upper_im_gamma, &trace.upper_pi);
  trace.sha256 = precomputed_digest == nullptr
                     ? sparkinterval::sha256_hex(raw.data(), raw.size())
                     : sparkinterval::lowercase_hex(*precomputed_digest);
  return trace;
}

// ---------------------------------------------------------------------------
// Stream construction.
// ---------------------------------------------------------------------------

Bracket make_bracket(mpq_class lower_offset, mpq_class upper_offset,
                     const Interval& lower_value, const Interval& upper_value,
                     Resolver resolver) {
  Bracket result;
  result.lower_offset = std::move(lower_offset);
  result.upper_offset = std::move(upper_offset);
  result.lower_value = make_endpoint(lower_value);
  result.upper_value = make_endpoint(upper_value);
  result.resolver = resolver;
  return result;
}

StreamValue build_stream(const Packet& packet, ExactSampleCache& cache,
                         std::size_t stream,
                         const std::map<std::int64_t, const Resolution*>&
                             resolutions_for_stream) {
  const StreamRange range = kStreams[stream];
  std::vector<std::int32_t> candidates;
  for (std::int32_t offset = range.lower; offset <= range.upper - 2; ++offset) {
    if (stationary_candidate(packet, cache, offset)) candidates.push_back(offset);
  }
  if (candidates.size() != resolutions_for_stream.size()) {
    throw ArtifactError(std::string(range.name) +
                        " stationary resolutions differ");
  }
  for (const std::int32_t offset : candidates) {
    if (resolutions_for_stream.find(static_cast<std::int64_t>(offset)) ==
        resolutions_for_stream.end()) {
      throw ArtifactError(std::string(range.name) +
                          " stationary resolutions differ");
    }
  }
  StreamValue result;
  for (std::int32_t offset = range.lower; offset < range.upper; ++offset) {
    const Sample& left = packet.samples[sample_index(offset)];
    const Sample& right = packet.samples[sample_index(offset + 1)];
    if (left.positive != right.positive) {
      result.events.push_back({offset, offset + 1, 1});
      result.brackets.push_back(make_bracket(
          mpq_class(offset), mpq_class(offset + 1), cache.at(offset),
          cache.at(offset + 1), Resolver::Direct));
    }
  }
  for (const std::int32_t offset : candidates) {
    const Resolution& resolution =
        *resolutions_for_stream.at(static_cast<std::int64_t>(offset));
    const bool source_sign = packet.samples[sample_index(offset + 1)].positive;
    if ((resolution.lower_value.lo > 0) != source_sign) {
      throw ArtifactError(std::string(range.name) +
                          " stationary resolution reverses the source sign");
    }
    result.events.push_back({offset, offset + 2, 2});
    result.brackets.push_back(make_bracket(
        resolution.lower_offset, resolution.midpoint_offset,
        resolution.lower_value, resolution.midpoint_value,
        Resolver::StationaryLeft));
    result.brackets.push_back(make_bracket(
        resolution.midpoint_offset, resolution.upper_offset,
        resolution.midpoint_value, resolution.upper_value,
        Resolver::StationaryRight));
  }
  std::stable_sort(result.events.begin(), result.events.end(),
                   [](const Event& left, const Event& right) {
                     if (left.left_sample != right.left_sample) {
                       return left.left_sample < right.left_sample;
                     }
                     return left.right_sample < right.right_sample;
                   });
  std::stable_sort(result.brackets.begin(), result.brackets.end(),
                   [](const Bracket& left, const Bracket& right) {
                     if (left.lower_offset != right.lower_offset) {
                       return left.lower_offset < right.lower_offset;
                     }
                     return left.upper_offset < right.upper_offset;
                   });
  result.left_boundary = make_endpoint(cache.at(range.lower));
  result.right_boundary = make_endpoint(cache.at(range.upper));
  return result;
}

std::pair<std::int64_t, std::int64_t> event_weights(const StreamValue& stream,
                                                    std::size_t index) {
  const StreamRange range = kStreams[index];
  const std::int64_t span = static_cast<std::int64_t>(range.upper) - range.lower;
  std::int64_t left = 0;
  std::int64_t right = 0;
  for (const Event& event : stream.events) {
    left -= event.multiplicity * (event.left_sample - range.lower);
    right += event.multiplicity * (span - (event.right_sample - range.lower));
  }
  return {left, right};
}

Interval turing_common(const Interval& log_pi, const Interval& im_gamma,
                       const Interval& pi, std::int64_t a, std::int64_t b,
                       const char* label) {
  const mpq_class span(b - a);
  mpq_class coefficient(static_cast<long>(-(a + b)), 4UL);
  coefficient.canonicalize();
  const Interval log_term = multiply(
      multiply(point_interval(coefficient), log_pi), point_interval(span));
  return divide(add(log_term, im_gamma), pi, label);
}

void build_turing(const SourceTrace& trace, std::uint64_t height_lower,
                  std::uint64_t height_upper,
                  const std::array<StreamValue, 3U>& streams,
                  TuringSide* lower_side, TuringSide* upper_side) {
  const std::int64_t left_weight =
      event_weights(streams[kLeftFlankStream], kLeftFlankStream).first;
  const std::int64_t right_weight =
      event_weights(streams[kRightFlankStream], kRightFlankStream).second;
  const auto signed_lower = static_cast<std::int64_t>(height_lower);
  const auto signed_upper = static_cast<std::int64_t>(height_upper);
  const std::int64_t lower_a = signed_lower - 21;
  const std::int64_t lower_b = signed_lower;
  const std::int64_t upper_a = signed_upper;
  const std::int64_t upper_b = signed_upper + 21;
  mpq_class spacing(static_cast<long>(kSourceSpacingNumerator),
                    static_cast<unsigned long>(kSourceSpacingDenominator));
  spacing.canonicalize();
  const Interval lower = divide(
      add(subtract(negate(trace.lower_s_bound),
                   point_interval(mpq_class(left_weight) * spacing)),
          turing_common(trace.lower_log_pi, trace.lower_im_gamma, trace.lower_pi,
                        lower_a, lower_b, "lower Turing common")),
      point_interval(mpq_class(lower_b - lower_a)), "Turing lower quotient");
  const Interval upper = divide(
      add(subtract(trace.upper_s_bound,
                   point_interval(mpq_class(right_weight) * spacing)),
          turing_common(trace.upper_log_pi, trace.upper_im_gamma, trace.upper_pi,
                        upper_a, upper_b, "upper Turing common")),
      point_interval(mpq_class(upper_b - upper_a)), "Turing upper quotient");
  const mpz_class lower_target = ceiling(lower.hi);
  const mpz_class upper_target = flooring(upper.lo);
  if (!(mpq_class(lower_target - 1) < lower.lo) || !(lower.hi <= lower_target)) {
    throw ArtifactError("lower Turing quotient has no unique ceiling");
  }
  if (!(mpq_class(upper_target) <= upper.lo) ||
      !(upper.hi < mpq_class(upper_target + 1))) {
    throw ArtifactError("upper Turing quotient has no unique floor");
  }
  const mpz_class lower_count = lower_target + 1;
  const mpz_class upper_count = upper_target + 1;
  const auto slots = static_cast<std::int64_t>(
      streams[kMainStream].brackets.size());
  if (lower_count < 1 || upper_count < 1 ||
      lower_count + mpz_class(slots) != upper_count) {
    throw ArtifactError("paired Turing count does not close on main slots");
  }
  *lower_side = {trace.lower_s_bound, trace.lower_log_pi, trace.lower_im_gamma,
                 trace.lower_pi, lower, lower_count};
  *upper_side = {trace.upper_s_bound, trace.upper_log_pi, trace.upper_im_gamma,
                 trace.upper_pi, upper, upper_count};
}

// ---------------------------------------------------------------------------
// Independent revalidation of the constructed artifact.  This is the C++
// counterpart of tg_verifier.platt_pt21_lean_artifact.validate: the builder
// must not be able to publish a document its own checker rejects.
// ---------------------------------------------------------------------------

void validate_endpoint(const Endpoint& value, const char* label) {
  if (value.enclosure.lo > value.enclosure.hi) {
    throw ArtifactError(std::string(label) + " is an invalid interval");
  }
  if (value.positive && value.enclosure.lo <= 0) {
    throw ArtifactError(std::string(label) + " is not strictly positive");
  }
  if (!value.positive && value.enclosure.hi >= 0) {
    throw ArtifactError(std::string(label) + " is not strictly negative");
  }
}

void validate_stream(const StreamValue& stream, std::size_t index) {
  const StreamRange range = kStreams[index];
  const char* name = range.name;
  validate_endpoint(stream.left_boundary, name);
  validate_endpoint(stream.right_boundary, name);
  if (stream.brackets.size() > kMaxBracketsPerStream) {
    throw ArtifactError(std::string(name) + ".brackets exceeds the format limit");
  }
  const mpq_class lower_range(range.lower);
  const mpq_class upper_range(range.upper);
  const Bracket* previous = nullptr;
  for (const Bracket& bracket : stream.brackets) {
    if (!(lower_range <= bracket.lower_offset &&
          bracket.lower_offset < bracket.upper_offset &&
          bracket.upper_offset <= upper_range)) {
      throw ArtifactError(std::string(name) +
                          " bracket is outside the fixed sample range");
    }
    validate_endpoint(bracket.lower_value, name);
    validate_endpoint(bracket.upper_value, name);
    if (bracket.lower_value.positive == bracket.upper_value.positive) {
      throw ArtifactError(std::string(name) +
                          " bracket lacks a strict sign change");
    }
    if (bracket.resolver == Resolver::PinnedArbFallback) {
      if (!bracket.fallback_receipt_sha256.has_value() ||
          !is_sha256_hex(*bracket.fallback_receipt_sha256)) {
        throw ArtifactError(std::string(name) +
                            " fallback bracket lacks its receipt digest");
      }
    } else if (bracket.fallback_receipt_sha256.has_value()) {
      throw ArtifactError(std::string(name) +
                          " has fallback evidence for a non-fallback resolver");
    }
    if (previous != nullptr) {
      if (previous->upper_offset > bracket.lower_offset) {
        throw ArtifactError(std::string(name) +
                            " bracket overlaps the previous interior");
      }
      if (previous->upper_offset == bracket.lower_offset &&
          previous->upper_value.positive != bracket.lower_value.positive) {
        throw ArtifactError(std::string(name) +
                            " bracket disagrees at a touching endpoint");
      }
    }
    if (bracket.lower_offset == lower_range &&
        bracket.lower_value.positive != stream.left_boundary.positive) {
      throw ArtifactError(std::string(name) +
                          " bracket disagrees with the left boundary");
    }
    if (bracket.upper_offset == upper_range &&
        bracket.upper_value.positive != stream.right_boundary.positive) {
      throw ArtifactError(std::string(name) +
                          " bracket disagrees with the right boundary");
    }
    previous = &bracket;
  }
  std::size_t index_cursor = 0U;
  while (index_cursor < stream.brackets.size()) {
    const Resolver resolver = stream.brackets[index_cursor].resolver;
    if (resolver == Resolver::StationaryLeft) {
      if (index_cursor + 1U >= stream.brackets.size()) {
        throw ArtifactError(std::string(name) + " has an unpaired stationary_left");
      }
      const Bracket& partner = stream.brackets[index_cursor + 1U];
      if (partner.resolver != Resolver::StationaryRight ||
          stream.brackets[index_cursor].upper_offset != partner.lower_offset) {
        throw ArtifactError(std::string(name) +
                            " stationary resolver pair differs");
      }
      index_cursor += 2U;
    } else if (resolver == Resolver::StationaryRight) {
      throw ArtifactError(std::string(name) + " has an unpaired stationary_right");
    } else {
      index_cursor += 1U;
    }
  }
  const bool same_sign =
      stream.left_boundary.positive == stream.right_boundary.positive;
  if (same_sign != (stream.brackets.size() % 2U == 0U)) {
    throw ArtifactError(std::string(name) +
                        " endpoint parity differs from slot count");
  }
  if (stream.events.size() > kMaxBracketsPerStream) {
    throw ArtifactError(std::string(name) + ".events exceeds the format limit");
  }
  bool has_previous_right = false;
  std::int64_t previous_right = 0;
  std::size_t bracket_index = 0U;
  std::int64_t multiplicity_total = 0;
  for (const Event& event : stream.events) {
    if (!(range.lower <= event.left_sample &&
          event.left_sample < event.right_sample &&
          event.right_sample <= range.upper) ||
        (event.multiplicity != 1 && event.multiplicity != 2)) {
      throw ArtifactError(std::string(name) +
                          " event is outside the fixed event range");
    }
    if (has_previous_right && previous_right > event.left_sample) {
      throw ArtifactError(std::string(name) +
                          " event overlaps the previous event cell");
    }
    if (bracket_index >= stream.brackets.size()) {
      throw ArtifactError(std::string(name) + " event has no matching bracket");
    }
    const Bracket& first = stream.brackets[bracket_index];
    if (mpq_class(event.left_sample) > first.lower_offset) {
      throw ArtifactError(std::string(name) +
                          " event does not contain its first bracket");
    }
    if (event.multiplicity == 1) {
      const bool direct = first.resolver == Resolver::Direct ||
                          first.resolver == Resolver::PinnedArbFallback;
      if (!direct || first.upper_offset > mpq_class(event.right_sample)) {
        throw ArtifactError(std::string(name) +
                            " direct bracket binding differs");
      }
      bracket_index += 1U;
    } else {
      if (bracket_index + 1U >= stream.brackets.size()) {
        throw ArtifactError(std::string(name) +
                            " event lacks its stationary bracket pair");
      }
      const Bracket& second = stream.brackets[bracket_index + 1U];
      if (first.resolver != Resolver::StationaryLeft ||
          second.resolver != Resolver::StationaryRight ||
          first.upper_offset != second.lower_offset ||
          second.upper_offset > mpq_class(event.right_sample)) {
        throw ArtifactError(std::string(name) +
                            " stationary bracket binding differs");
      }
      bracket_index += 2U;
    }
    multiplicity_total += event.multiplicity;
    has_previous_right = true;
    previous_right = event.right_sample;
  }
  if (bracket_index != stream.brackets.size()) {
    throw ArtifactError(std::string(name) +
                        " has brackets not bound to Turing events");
  }
  if (multiplicity_total != static_cast<std::int64_t>(stream.brackets.size())) {
    throw ArtifactError(std::string(name) +
                        " event multiplicities differ from slots");
  }
}

void validate_artifact(const Artifact& artifact) {
  if (artifact.block >= kSourceBlockCount) {
    throw ArtifactError("block is outside the fixed source campaign");
  }
  if (artifact.height_lower != kSourceLower + artifact.block * kSourceStep ||
      artifact.height_upper != artifact.height_lower + kSourceStep ||
      artifact.window_center != artifact.height_lower + kSourceHalfStep) {
    throw ArtifactError("artifact heights differ from fixed lattice geometry");
  }
  if (!is_sha256_hex(artifact.required_sign_packet_sha256) ||
      !is_sha256_hex(artifact.source_trace_sha256)) {
    throw ArtifactError("artifact digests must be lowercase SHA-256 hex");
  }
  for (std::size_t index = 0U; index < kStreams.size(); ++index) {
    validate_stream(artifact.streams[index], index);
  }
  if (artifact.streams[kLeftFlankStream].right_boundary.positive !=
      artifact.streams[kMainStream].left_boundary.positive) {
    throw ArtifactError("left flank/main shared endpoint sign differs");
  }
  if (artifact.streams[kMainStream].right_boundary.positive !=
      artifact.streams[kRightFlankStream].left_boundary.positive) {
    throw ArtifactError("main/right flank shared endpoint sign differs");
  }
  for (const TuringSide* side : {&artifact.lower, &artifact.upper}) {
    if (side->s_bound.lo < 0 || side->pi.lo <= 0) {
      throw ArtifactError("Turing S bound or pi interval has the wrong sign");
    }
    if (side->count < 1) throw ArtifactError("Turing count is below 1");
  }
  const std::int64_t left_weight =
      event_weights(artifact.streams[kLeftFlankStream], kLeftFlankStream).first;
  const std::int64_t right_weight =
      event_weights(artifact.streams[kRightFlankStream], kRightFlankStream)
          .second;
  const auto signed_lower = static_cast<std::int64_t>(artifact.height_lower);
  const auto signed_upper = static_cast<std::int64_t>(artifact.height_upper);
  mpq_class spacing(static_cast<long>(kSourceSpacingNumerator),
                    static_cast<unsigned long>(kSourceSpacingDenominator));
  spacing.canonicalize();
  const Interval lower = divide(
      add(subtract(negate(artifact.lower.s_bound),
                   point_interval(mpq_class(left_weight) * spacing)),
          turing_common(artifact.lower.log_pi, artifact.lower.im_gamma_integral,
                        artifact.lower.pi, signed_lower - 21, signed_lower,
                        "lower Turing common term")),
      point_interval(mpq_class(21)), "lower Turing quotient");
  const Interval upper = divide(
      add(subtract(artifact.upper.s_bound,
                   point_interval(mpq_class(right_weight) * spacing)),
          turing_common(artifact.upper.log_pi, artifact.upper.im_gamma_integral,
                        artifact.upper.pi, signed_upper, signed_upper + 21,
                        "upper Turing common term")),
      point_interval(mpq_class(21)), "upper Turing quotient");
  if (!same_interval(lower, artifact.lower.quotient) ||
      !same_interval(upper, artifact.upper.quotient)) {
    throw ArtifactError("advertised one-sided Turing quotient differs");
  }
  if (!(mpq_class(artifact.lower.count - 2) < lower.lo) ||
      !(lower.hi <= mpq_class(artifact.lower.count - 1))) {
    throw ArtifactError("lower quotient does not force the advertised ceiling");
  }
  if (!(mpq_class(artifact.upper.count - 1) <= upper.lo) ||
      !(upper.hi < mpq_class(artifact.upper.count))) {
    throw ArtifactError("upper quotient does not force the advertised floor");
  }
  if (artifact.lower.count +
          mpz_class(static_cast<std::int64_t>(
              artifact.streams[kMainStream].brackets.size())) !=
      artifact.upper.count) {
    throw ArtifactError("Turing count closure equation differs");
  }
}

// ---------------------------------------------------------------------------
// Canonical emission.  The literal key order below is Python's sort_keys=True
// order; the differential known-answer test enforces byte equality.
// ---------------------------------------------------------------------------

void emit_rational(std::string& out, const mpq_class& value) {
  out += "{\"denominator\":";
  append_integer(out, mpz_class(value.get_den()));
  out += ",\"numerator\":";
  append_integer(out, mpz_class(value.get_num()));
  out.push_back('}');
}

void emit_interval(std::string& out, const Interval& value) {
  out += "{\"hi\":";
  emit_rational(out, value.hi);
  out += ",\"lo\":";
  emit_rational(out, value.lo);
  out.push_back('}');
}

void emit_endpoint(std::string& out, const Endpoint& value) {
  out += "{\"enclosure\":";
  emit_interval(out, value.enclosure);
  out += ",\"positive\":";
  out += value.positive ? "true" : "false";
  out.push_back('}');
}

void emit_bracket(std::string& out, const Bracket& value) {
  out += "{\"fallback_receipt_sha256\":";
  if (value.fallback_receipt_sha256.has_value()) {
    append_canonical_string(out, *value.fallback_receipt_sha256);
  } else {
    out += "null";
  }
  out += ",\"lower_offset\":";
  emit_rational(out, value.lower_offset);
  out += ",\"lower_value\":";
  emit_endpoint(out, value.lower_value);
  out += ",\"resolver\":\"";
  out += resolver_name(value.resolver);
  out += "\",\"upper_offset\":";
  emit_rational(out, value.upper_offset);
  out += ",\"upper_value\":";
  emit_endpoint(out, value.upper_value);
  out.push_back('}');
}

void emit_event(std::string& out, const Event& value) {
  out += "{\"left_sample\":";
  append_integer(out, mpz_class(value.left_sample));
  out += ",\"multiplicity\":";
  append_integer(out, mpz_class(value.multiplicity));
  out += ",\"right_sample\":";
  append_integer(out, mpz_class(value.right_sample));
  out.push_back('}');
}

void emit_stream(std::string& out, const StreamValue& value) {
  out += "{\"brackets\":[";
  for (std::size_t index = 0U; index < value.brackets.size(); ++index) {
    if (index != 0U) out.push_back(',');
    emit_bracket(out, value.brackets[index]);
  }
  out += "],\"events\":[";
  for (std::size_t index = 0U; index < value.events.size(); ++index) {
    if (index != 0U) out.push_back(',');
    emit_event(out, value.events[index]);
  }
  out += "],\"left_boundary\":";
  emit_endpoint(out, value.left_boundary);
  out += ",\"right_boundary\":";
  emit_endpoint(out, value.right_boundary);
  out.push_back('}');
}

void emit_turing_side(std::string& out, const TuringSide& value) {
  out += "{\"count\":";
  append_integer(out, value.count);
  out += ",\"im_gamma_integral\":";
  emit_interval(out, value.im_gamma_integral);
  out += ",\"log_pi\":";
  emit_interval(out, value.log_pi);
  out += ",\"pi\":";
  emit_interval(out, value.pi);
  out += ",\"quotient\":";
  emit_interval(out, value.quotient);
  out += ",\"s_bound\":";
  emit_interval(out, value.s_bound);
  out.push_back('}');
}

std::string emit_artifact(const Artifact& artifact) {
  std::string out;
  out.reserve(4U * 1024U * 1024U);
  out += "{\"block\":";
  append_integer(out, mpz_class(static_cast<std::int64_t>(artifact.block)));
  out += ",\"height_lower\":";
  append_integer(out,
                 mpz_class(static_cast<std::int64_t>(artifact.height_lower)));
  out += ",\"height_upper\":";
  append_integer(out,
                 mpz_class(static_cast<std::int64_t>(artifact.height_upper)));
  out += ",\"required_sign_packet_sha256\":";
  append_canonical_string(out, artifact.required_sign_packet_sha256);
  out += ",\"schema\":\"";
  out += kArtifactSchema;
  out += "\",\"source_trace_sha256\":";
  append_canonical_string(out, artifact.source_trace_sha256);
  out += ",\"streams\":{\"left_flank\":";
  emit_stream(out, artifact.streams[kLeftFlankStream]);
  out += ",\"main\":";
  emit_stream(out, artifact.streams[kMainStream]);
  out += ",\"right_flank\":";
  emit_stream(out, artifact.streams[kRightFlankStream]);
  out += "},\"turing\":{\"lower\":";
  emit_turing_side(out, artifact.lower);
  out += ",\"upper\":";
  emit_turing_side(out, artifact.upper);
  out += "},\"upstream_commit\":\"";
  out += kUpstreamCommit;
  out += "\",\"window_center\":";
  append_integer(out,
                 mpz_class(static_cast<std::int64_t>(artifact.window_center)));
  out += "}\n";
  return out;
}

// ---------------------------------------------------------------------------
// Whole-block construction.
// ---------------------------------------------------------------------------

struct BuildResult {
  std::string bytes;
  Digest digest{};
  std::uint64_t block = 0U;
  std::uint64_t window_center = 0U;
};

// Every payload is hashed exactly once per request.  The framed stream mode
// supplies the digests it has already computed for its own request check.
BuildResult build_block(const std::vector<unsigned char>& packet_raw,
                        const std::vector<unsigned char>& trace_raw,
                        const Digest* packet_digest, const Digest* trace_digest,
                        bool want_artifact_digest) {
  const Packet packet = decode_packet(packet_raw, packet_digest);
  const std::uint64_t center = packet.window_center;
  const std::uint64_t delta = center - (kSourceLower + kSourceHalfStep);
  if (center < kSourceLower + kSourceHalfStep || delta % kSourceStep != 0U) {
    throw ArtifactError("required-sign packet center is off the source grid");
  }
  const std::uint64_t block = delta / kSourceStep;
  if (block >= kSourceBlockCount) {
    throw ArtifactError("required-sign packet is outside the full campaign");
  }
  const SourceTrace trace =
      parse_source_trace(trace_raw, packet.sha256, block, trace_digest);
  std::array<std::map<std::int64_t, const Resolution*>, 3U> by_stream;
  for (const Resolution& resolution : trace.resolutions) {
    auto& target = by_stream[resolution.stream];
    if (!target.emplace(resolution.outer_left_sample, &resolution).second) {
      throw ArtifactError("duplicate stationary resolution");
    }
  }
  ExactSampleCache cache(packet);
  Artifact artifact;
  artifact.block = block;
  artifact.height_lower = kSourceLower + block * kSourceStep;
  artifact.height_upper = artifact.height_lower + kSourceStep;
  artifact.window_center = center;
  artifact.required_sign_packet_sha256 = packet.sha256;
  artifact.source_trace_sha256 = trace.sha256;
  for (std::size_t index = 0U; index < kStreams.size(); ++index) {
    artifact.streams[index] =
        build_stream(packet, cache, index, by_stream[index]);
  }
  build_turing(trace, artifact.height_lower, artifact.height_upper,
               artifact.streams, &artifact.lower, &artifact.upper);
  validate_artifact(artifact);
  BuildResult result;
  result.bytes = emit_artifact(artifact);
  if (result.bytes.size() > kMaxArtifactBytes) {
    throw ArtifactError("generated artifact exceeds the format size limit");
  }
  if (want_artifact_digest) {
    result.digest =
        sparkinterval::sha256(result.bytes.data(), result.bytes.size());
  }
  result.block = block;
  result.window_center = center;
  return result;
}

// ---------------------------------------------------------------------------
// Entry points.
// ---------------------------------------------------------------------------

void write_create_only(const std::string& path, const std::string& bytes) {
  const int descriptor =
      ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
             0400);
  if (descriptor < 0) throw ArtifactError("output already exists or is unusable");
  try {
    write_all(descriptor,
              reinterpret_cast<const unsigned char*>(bytes.data()),
              bytes.size());
  } catch (...) {
    ::close(descriptor);
    throw;
  }
  if (::fsync(descriptor) != 0) {
    ::close(descriptor);
    throw ArtifactError("cannot flush the native artifact output");
  }
  ::close(descriptor);
}

int run_one_shot(const std::string& packet_path, const std::string& trace_path,
                 const std::string& output_path) {
  const std::vector<unsigned char> packet_raw = read_regular_file(
      packet_path, kExpectedPacketBytes, "required-sign packet");
  const std::vector<unsigned char> trace_raw =
      read_regular_file(trace_path, kMaxTraceBytes, "source trace");
  const BuildResult result =
      build_block(packet_raw, trace_raw, nullptr, nullptr, false);
  if (output_path.empty()) {
    write_all(STDOUT_FILENO,
              reinterpret_cast<const unsigned char*>(result.bytes.data()),
              result.bytes.size());
  } else {
    write_create_only(output_path, result.bytes);
  }
  return 0;
}

int run_stream() {
  std::uint64_t expected_request_id = 0U;
  while (true) {
    std::array<unsigned char, kStreamRequestHeaderBytes> request{};
    if (!read_exact_or_eof(STDIN_FILENO, request.data(), request.size())) break;
    if (std::memcmp(request.data(), kStreamRequestMagic, 8U) != 0 ||
        load_u32(request.data() + 8U) != 1U ||
        load_u32(request.data() + 12U) != request.size() ||
        load_u64(request.data() + 16U) != expected_request_id ||
        load_u64(request.data() + 24U) != kExpectedPacketBytes) {
      throw ArtifactError("native artifact request framing differs");
    }
    const std::uint64_t trace_bytes = load_u64(request.data() + 32U);
    if (trace_bytes == 0U || trace_bytes > kMaxTraceBytes) {
      throw ArtifactError("native artifact request trace length differs");
    }
    std::vector<unsigned char> packet_raw(kExpectedPacketBytes);
    if (!read_exact_or_eof(STDIN_FILENO, packet_raw.data(), packet_raw.size())) {
      throw ArtifactError("native artifact request packet is truncated");
    }
    std::vector<unsigned char> trace_raw(static_cast<std::size_t>(trace_bytes));
    if (!read_exact_or_eof(STDIN_FILENO, trace_raw.data(), trace_raw.size())) {
      throw ArtifactError("native artifact request trace is truncated");
    }
    const Digest packet_digest =
        sparkinterval::sha256(packet_raw.data(), packet_raw.size());
    const Digest trace_digest =
        sparkinterval::sha256(trace_raw.data(), trace_raw.size());
    if (!std::equal(packet_digest.begin(), packet_digest.end(),
                    request.begin() + 40U) ||
        !std::equal(trace_digest.begin(), trace_digest.end(),
                    request.begin() + 72U)) {
      throw ArtifactError("native artifact request payload digest differs");
    }
    const BuildResult result = build_block(packet_raw, trace_raw,
                                           &packet_digest, &trace_digest, true);
    std::array<unsigned char, kStreamResponseHeaderBytes> response{};
    std::memcpy(response.data(), kStreamResponseMagic, 8U);
    store_u32(response.data() + 8U, 1U);
    store_u32(response.data() + 12U,
              static_cast<std::uint32_t>(response.size()));
    store_u64(response.data() + 16U, expected_request_id);
    store_u64(response.data() + 24U, result.bytes.size());
    store_u64(response.data() + 32U, result.block);
    store_u64(response.data() + 40U, result.window_center);
    std::memcpy(response.data() + 48U, packet_digest.data(),
                packet_digest.size());
    std::memcpy(response.data() + 80U, result.digest.data(),
                result.digest.size());
    write_all(STDOUT_FILENO, response.data(), response.size());
    write_all(STDOUT_FILENO,
              reinterpret_cast<const unsigned char*>(result.bytes.data()),
              result.bytes.size());
    if (expected_request_id == std::numeric_limits<std::uint64_t>::max()) {
      throw ArtifactError("native artifact request id overflows uint64");
    }
    ++expected_request_id;
  }
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    std::string packet_path;
    std::string trace_path;
    std::string output_path;
    bool stream = false;
    for (int index = 1; index < argc; ++index) {
      const std::string_view argument(argv[index]);
      const auto value = [&](const char* name) -> std::string {
        if (index + 1 >= argc) {
          throw ArtifactError(std::string(name) + " requires a value");
        }
        return std::string(argv[++index]);
      };
      if (argument == "--required-sign-packet") {
        packet_path = value("--required-sign-packet");
      } else if (argument == "--source-trace") {
        trace_path = value("--source-trace");
      } else if (argument == "--output") {
        output_path = value("--output");
      } else if (argument == "--stream") {
        stream = true;
      } else {
        throw ArtifactError(
            "usage: builder --required-sign-packet P --source-trace T "
            "[--output O] | builder --stream");
      }
    }
    if (stream) {
      if (!packet_path.empty() || !trace_path.empty() || !output_path.empty()) {
        throw ArtifactError("--stream takes no path arguments");
      }
      return run_stream();
    }
    if (packet_path.empty() || trace_path.empty()) {
      throw ArtifactError(
          "usage: builder --required-sign-packet P --source-trace T "
          "[--output O] | builder --stream");
    }
    return run_one_shot(packet_path, trace_path, output_path);
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_pt21_native_artifact_builder: " << error.what()
              << '\n';
    return 2;
  }
}

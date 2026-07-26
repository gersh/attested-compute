// Copyright (c) 2026 Gershon Bialer. All rights reserved.
// SPDX-License-Identifier: MIT

// Streaming native finalizer for the optimized PT21 finite artifact chain.
//
// This executable deliberately certifies only finite wire relationships.  It
// never asserts that a retained interval encloses Hardy Z or that the analytic
// Turing hypotheses hold.  Those remain separate Lean/source obligations.

#include "sparkinterval/sha256.hpp"

#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace {

using Digest = sparkinterval::Sha256Digest;
namespace fs = std::filesystem;

constexpr std::uint32_t kVersion = 1U;
constexpr std::uint32_t kBoundedTest = 0U;
constexpr std::uint32_t kProduction = 1U;
constexpr std::uint64_t kSourceLower = 10'000'000'000ULL;
constexpr std::uint64_t kSourceStep = 1'008ULL;
constexpr std::uint64_t kSourceBlockCount = 2'966'443'783ULL;
constexpr std::uint64_t kSourceLowerCount = 32'130'158'315ULL;
constexpr std::uint64_t kSourceHeight = 3'000'175'332'800ULL;
constexpr std::uint64_t kSourceHeightCount = 12'363'153'437'138ULL;
constexpr std::uint64_t kSourceHeightBlock =
    (kSourceHeight - kSourceLower) / kSourceStep;
constexpr std::uint64_t kNoCount = std::numeric_limits<std::uint64_t>::max();
constexpr std::size_t kBlockBytes = 320U;
constexpr std::size_t kHeaderBytes = 256U;
constexpr std::size_t kFooterBytes = 256U;
constexpr std::size_t kSummaryBytes = 288U;
constexpr std::size_t kStreamAuthBytes = 48U;
constexpr std::size_t kMaximumShardListBytes = 16U * 1024U * 1024U;

constexpr char kBlockMagic[] = "PT21BLK1";
constexpr char kShardHeaderMagic[] = "PT21SHD1";
constexpr char kShardFooterMagic[] = "PT21SFT1";
constexpr char kCampaignHeaderMagic[] = "PT21CMP1";
constexpr char kCampaignSummaryMagic[] = "PT21CSR1";
constexpr char kCampaignFooterMagic[] = "PT21CFT1";
constexpr char kStreamAuthMagic[] = "PT21END1";
constexpr char kUpstreamCommit[] =
    "42b21426718e542daa2b006dc05ea2d7f26426e6";
constexpr char kInterpolationPatchHex[] =
    "2bc33d3d4f6163ba5af8982f1272e9544154ed95bc6155a4ee215c4e425c85b3";

constexpr char kBlockRecordDomain[] =
    "sparkinterval/tg/platt-pt21-native-block-record/v1\0";
constexpr char kBlockLeafDomain[] =
    "sparkinterval/tg/platt-pt21-native-block-leaf/v1\0";
constexpr char kBlockNodeDomain[] =
    "sparkinterval/tg/platt-pt21-native-block-node/v1\0";
constexpr char kShardHeaderDomain[] =
    "sparkinterval/tg/platt-pt21-native-shard-header/v1\0";
constexpr char kShardFooterDomain[] =
    "sparkinterval/tg/platt-pt21-native-shard-footer/v1\0";
constexpr char kCampaignHeaderDomain[] =
    "sparkinterval/tg/platt-pt21-native-campaign-header/v1\0";
constexpr char kCampaignSummaryDomain[] =
    "sparkinterval/tg/platt-pt21-native-campaign-summary/v1\0";
constexpr char kCampaignLeafDomain[] =
    "sparkinterval/tg/platt-pt21-native-campaign-leaf/v1\0";
constexpr char kCampaignNodeDomain[] =
    "sparkinterval/tg/platt-pt21-native-campaign-node/v1\0";
constexpr char kCampaignFooterDomain[] =
    "sparkinterval/tg/platt-pt21-native-campaign-footer/v1\0";

class FinalizerError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

template <std::size_t N>
using Bytes = std::array<unsigned char, N>;

bool is_zero(const Digest& value) {
  for (const unsigned char byte : value) {
    if (byte != 0U) return false;
  }
  return true;
}

std::uint32_t load_u32(const unsigned char* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

std::uint64_t load_u64(const unsigned char* data) {
  std::uint64_t result = 0;
  for (unsigned int index = 0; index < 8U; ++index) {
    result |= static_cast<std::uint64_t>(data[index]) << (8U * index);
  }
  return result;
}

void store_u32(unsigned char* data, std::uint32_t value) {
  for (unsigned int index = 0; index < 4U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void store_u64(unsigned char* data, std::uint64_t value) {
  for (unsigned int index = 0; index < 8U; ++index) {
    data[index] = static_cast<unsigned char>(value >> (8U * index));
  }
}

void checked_add(std::uint64_t& accumulator, std::uint64_t value,
                 std::string_view label) {
  if (value > std::numeric_limits<std::uint64_t>::max() - accumulator) {
    throw FinalizerError(std::string(label) + " aggregate overflows uint64");
  }
  accumulator += value;
}

bool valid_hex_character(char value) {
  return (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f');
}

unsigned char hex_nibble(char value) {
  if (value >= '0' && value <= '9') {
    return static_cast<unsigned char>(value - '0');
  }
  return static_cast<unsigned char>(value - 'a' + 10);
}

Digest parse_digest(std::string_view value, std::string_view label) {
  if (value.size() != 64U) {
    throw FinalizerError(std::string(label) + " is not lowercase SHA-256");
  }
  Digest result{};
  for (std::size_t index = 0; index < result.size(); ++index) {
    const char high = value[index * 2U];
    const char low = value[index * 2U + 1U];
    if (!valid_hex_character(high) || !valid_hex_character(low)) {
      throw FinalizerError(std::string(label) + " is not lowercase SHA-256");
    }
    result[index] = static_cast<unsigned char>(
        (hex_nibble(high) << 4U) | hex_nibble(low));
  }
  if (is_zero(result)) {
    throw FinalizerError(std::string(label) + " must be nonzero");
  }
  return result;
}

template <std::size_t N>
Digest domain_hash(const char (&domain)[N], const unsigned char* data,
                   std::size_t size) {
  sparkinterval::detail::Sha256 hasher;
  // N includes the compiler's final terminator.  N - 1 retains the explicit
  // domain-separation NUL in every literal above.
  hasher.update(domain, N - 1U);
  hasher.update(data, size);
  return hasher.finish();
}

template <std::size_t N>
Digest node_hash(const char (&domain)[N], const Digest& left,
                 const Digest& right) {
  sparkinterval::detail::Sha256 hasher;
  hasher.update(domain, N - 1U);
  hasher.update(left.data(), left.size());
  hasher.update(right.data(), right.size());
  return hasher.finish();
}

template <std::size_t N>
Digest leaf_hash(const char (&domain)[N], const Digest& digest) {
  return domain_hash(domain, digest.data(), digest.size());
}

class MerkleAccumulator {
 public:
  enum class Kind { kBlocks, kCampaign };

  explicit MerkleAccumulator(Kind kind) : kind_(kind) {}

  void add(const Digest& digest) {
    Digest carry = kind_ == Kind::kBlocks
                       ? leaf_hash(kBlockLeafDomain, digest)
                       : leaf_hash(kCampaignLeafDomain, digest);
    std::size_t level = 0;
    while (level < peaks_.size() && peaks_[level].has_value()) {
      carry = combine(*peaks_[level], carry);
      peaks_[level].reset();
      ++level;
    }
    if (level == peaks_.size()) {
      throw FinalizerError("Merkle stream exceeds uint64 geometry");
    }
    peaks_[level] = carry;
    ++count_;
  }

  Digest finish() const {
    if (count_ == 0U) {
      throw FinalizerError("cannot Merkle-finalize an empty stream");
    }
    std::optional<Digest> accumulator;
    std::size_t accumulator_level = 0;
    for (std::size_t level = 0; level < peaks_.size(); ++level) {
      if (!peaks_[level].has_value()) continue;
      if (!accumulator.has_value()) {
        accumulator = peaks_[level];
        accumulator_level = level;
        continue;
      }
      while (accumulator_level < level) {
        accumulator = combine(*accumulator, *accumulator);
        ++accumulator_level;
      }
      accumulator = combine(*peaks_[level], *accumulator);
      accumulator_level = level + 1U;
    }
    if (!accumulator.has_value()) {
      throw FinalizerError("internal empty Merkle accumulator");
    }
    return *accumulator;
  }

 private:
  Digest combine(const Digest& left, const Digest& right) const {
    return kind_ == Kind::kBlocks
               ? node_hash(kBlockNodeDomain, left, right)
               : node_hash(kCampaignNodeDomain, left, right);
  }

  Kind kind_;
  std::array<std::optional<Digest>, 64> peaks_{};
  std::uint64_t count_ = 0;
};

class Reader {
 public:
  explicit Reader(const fs::path& path) : path_(path) {
    const bool standard_input = path == fs::path("-");
    descriptor_ =
        standard_input
            ? ::fcntl(STDIN_FILENO, F_DUPFD_CLOEXEC, 3)
            : ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor_ < 0) {
      throw FinalizerError(
          standard_input
              ? "cannot duplicate standard input: " +
                    std::string(std::strerror(errno))
              : "cannot open input without following links: " + path.string() +
                    ": " + std::strerror(errno));
    }
    struct stat metadata {};
    if (::fstat(descriptor_, &metadata) != 0) {
      close_noexcept();
      throw FinalizerError("cannot inspect input: " + path.string());
    }
    if (standard_input) {
      if (!S_ISREG(metadata.st_mode) && !S_ISFIFO(metadata.st_mode)) {
        close_noexcept();
        throw FinalizerError(
            "standard input is neither a regular file nor a pipe");
      }
    } else if (!S_ISREG(metadata.st_mode)) {
      close_noexcept();
      throw FinalizerError("input is not a regular file: " + path.string());
    }
    if (S_ISREG(metadata.st_mode)) {
      if (metadata.st_size < 0) {
        close_noexcept();
        throw FinalizerError("input has a negative byte length");
      }
      size_ = static_cast<std::uint64_t>(metadata.st_size);
    }
  }

  Reader(const Reader&) = delete;
  Reader& operator=(const Reader&) = delete;

  ~Reader() { close_noexcept(); }

  bool has_known_size() const { return size_.has_value(); }

  std::uint64_t size() const {
    if (!size_.has_value()) {
      throw FinalizerError("streaming input has no advance byte length");
    }
    return *size_;
  }
  std::uint64_t consumed() const { return consumed_; }

  void read_exact(unsigned char* output, std::size_t size,
                  std::string_view label) {
    std::size_t position = 0;
    while (position < size) {
      const ssize_t got =
          ::read(descriptor_, output + position, size - position);
      if (got < 0 && errno == EINTR) continue;
      if (got <= 0) {
        throw FinalizerError(std::string(label) + " is truncated");
      }
      position += static_cast<std::size_t>(got);
      consumed_ += static_cast<std::uint64_t>(got);
    }
  }

  void require_eof(std::string_view label) {
    unsigned char trailing = 0U;
    while (true) {
      const ssize_t got = ::read(descriptor_, &trailing, 1U);
      if (got < 0 && errno == EINTR) continue;
      if (got < 0) {
        throw FinalizerError(std::string("cannot finish ") +
                             std::string(label) + ": " +
                             std::strerror(errno));
      }
      if (got > 0) {
        ++consumed_;
        throw FinalizerError(std::string(label) + " has trailing bytes");
      }
      return;
    }
  }

 private:
  void close_noexcept() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  fs::path path_;
  int descriptor_ = -1;
  std::optional<std::uint64_t> size_;
  std::uint64_t consumed_ = 0;
};

class AtomicWriter {
 public:
  explicit AtomicWriter(const fs::path& output) : output_(output) {
    if (output.empty()) throw FinalizerError("output path is empty");
    temporary_ = output;
    temporary_ += ".partial." + std::to_string(::getpid());
    descriptor_ = ::open(temporary_.c_str(),
                         O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                         S_IRUSR | S_IWUSR);
    if (descriptor_ < 0) {
      throw FinalizerError("cannot create exclusive temporary output: " +
                           temporary_.string() + ": " + std::strerror(errno));
    }
  }

  AtomicWriter(const AtomicWriter&) = delete;
  AtomicWriter& operator=(const AtomicWriter&) = delete;

  ~AtomicWriter() {
    if (descriptor_ >= 0) ::close(descriptor_);
    if (!published_ && !temporary_.empty()) {
      std::error_code ignored;
      fs::remove(temporary_, ignored);
    }
  }

  void write_all(const unsigned char* data, std::size_t size) {
    std::size_t position = 0;
    while (position < size) {
      const ssize_t wrote =
          ::write(descriptor_, data + position, size - position);
      if (wrote < 0 && errno == EINTR) continue;
      if (wrote <= 0) {
        throw FinalizerError("cannot write retained archive: " +
                             std::string(std::strerror(errno)));
      }
      position += static_cast<std::size_t>(wrote);
      size_ += static_cast<std::uint64_t>(wrote);
    }
  }

  void publish() {
    if (::fsync(descriptor_) != 0) {
      throw FinalizerError("cannot fsync retained archive");
    }
    if (::close(descriptor_) != 0) {
      descriptor_ = -1;
      throw FinalizerError("cannot close retained archive");
    }
    descriptor_ = -1;
    // link(2), unlike rename(2), fails if the destination already exists.
    if (::link(temporary_.c_str(), output_.c_str()) != 0) {
      throw FinalizerError("cannot publish output without replacement: " +
                           output_.string() + ": " + std::strerror(errno));
    }
    if (::unlink(temporary_.c_str()) != 0) {
      throw FinalizerError("cannot unlink published temporary output");
    }
    published_ = true;
  }

  std::uint64_t size() const { return size_; }

 private:
  fs::path output_;
  fs::path temporary_;
  int descriptor_ = -1;
  std::uint64_t size_ = 0;
  bool published_ = false;
};

Digest digest_at(const unsigned char* data) {
  Digest result{};
  std::copy_n(data, result.size(), result.begin());
  return result;
}

void store_digest(unsigned char* data, const Digest& value) {
  std::copy(value.begin(), value.end(), data);
}

struct Record {
  std::uint64_t block = 0;
  std::uint64_t lower_count = 0;
  std::uint64_t upper_count = 0;
  std::uint64_t slots = 0;
  std::uint32_t stationary = 0;
  std::uint32_t sparse = 0;
  std::optional<std::uint64_t> source_count;
  std::uint64_t source_slots = 0;
  Digest producer{};
  Digest digest{};
};

Record parse_record(const Bytes<kBlockBytes>& raw,
                    std::uint64_t expected_block) {
  if (std::memcmp(raw.data(), kBlockMagic, 8U) != 0 ||
      load_u32(raw.data() + 8U) != kVersion ||
      load_u32(raw.data() + 12U) != kBlockBytes) {
    throw FinalizerError("native block record identity differs");
  }
  Record result;
  result.block = load_u64(raw.data() + 16U);
  result.lower_count = load_u64(raw.data() + 24U);
  result.upper_count = load_u64(raw.data() + 32U);
  result.slots = load_u64(raw.data() + 40U);
  result.stationary = load_u32(raw.data() + 48U);
  result.sparse = load_u32(raw.data() + 52U);
  const std::uint32_t ambiguous = load_u32(raw.data() + 56U);
  if (result.block != expected_block || result.block >= kSourceBlockCount) {
    throw FinalizerError("native block record index is not gap-free");
  }
  if (result.lower_count == 0U || result.upper_count == 0U ||
      result.slots >
          std::numeric_limits<std::uint64_t>::max() - result.lower_count ||
      result.lower_count + result.slots != result.upper_count) {
    throw FinalizerError("native block count transition does not telescope");
  }
  for (std::size_t offset = 60U; offset <= 76U; offset += 4U) {
    if (load_u32(raw.data() + offset) != 0U) {
      throw FinalizerError(
          "native block retains a nonzero finite failure counter");
    }
  }
  if (ambiguous != result.sparse) {
    throw FinalizerError(
        "every initial ambiguity must have exactly one sparse refinement");
  }
  for (const std::size_t offset : {88U, 120U, 152U, 248U}) {
    if (is_zero(digest_at(raw.data() + offset))) {
      throw FinalizerError("native block required digest is zero");
    }
  }
  const Digest stationary_digest = digest_at(raw.data() + 184U);
  const Digest sparse_digest = digest_at(raw.data() + 216U);
  if ((result.stationary == 0U) != is_zero(stationary_digest)) {
    throw FinalizerError(
        "stationary trace digest/count relationship differs");
  }
  if ((result.sparse == 0U) != is_zero(sparse_digest)) {
    throw FinalizerError(
        "sparse refinement digest/count relationship differs");
  }
  const std::uint64_t source_count = load_u64(raw.data() + 80U);
  if (source_count != kNoCount) result.source_count = source_count;
  result.source_slots = load_u64(raw.data() + 280U);
  if ((result.block == kSourceHeightBlock) !=
      result.source_count.has_value()) {
    throw FinalizerError(
        "exact source-height count is absent or attached to the wrong block");
  }
  if ((!result.source_count.has_value() && result.source_slots != 0U) ||
      (result.source_count.has_value() &&
       (result.source_slots > result.slots ||
        result.source_slots >
            std::numeric_limits<std::uint64_t>::max() - result.lower_count ||
        result.lower_count + result.source_slots != *result.source_count))) {
    throw FinalizerError(
        "source-height count is not linked to the target block transition");
  }
  result.producer = digest_at(raw.data() + 248U);
  result.digest = digest_at(raw.data() + 288U);
  if (result.digest !=
      domain_hash(kBlockRecordDomain, raw.data(), 288U)) {
    throw FinalizerError("native block record digest differs");
  }
  return result;
}

Bytes<kHeaderBytes> build_header(const char* magic,
                                 std::uint32_t record_bytes,
                                 std::uint32_t mode,
                                 std::uint64_t first_block,
                                 std::uint64_t item_count,
                                 const Digest& worker,
                                 const Digest& plan,
                                 const Digest& prefix,
                                 bool campaign) {
  Bytes<kHeaderBytes> raw{};
  std::memcpy(raw.data(), magic, 8U);
  store_u32(raw.data() + 8U, kVersion);
  store_u32(raw.data() + 12U, kHeaderBytes);
  store_u32(raw.data() + 16U, record_bytes);
  store_u32(raw.data() + 20U, mode);
  store_u64(raw.data() + 24U, first_block);
  store_u64(raw.data() + 32U, item_count);
  store_digest(raw.data() + 40U, worker);
  store_digest(raw.data() + 72U, plan);
  store_digest(raw.data() + 104U, prefix);
  static_assert(sizeof(kUpstreamCommit) - 1U == 40U);
  std::memcpy(raw.data() + 136U, kUpstreamCommit, 40U);
  store_digest(raw.data() + 176U,
               parse_digest(kInterpolationPatchHex, "interpolation patch"));
  const Digest header_digest =
      campaign ? domain_hash(kCampaignHeaderDomain, raw.data(), 208U)
               : domain_hash(kShardHeaderDomain, raw.data(), 208U);
  store_digest(raw.data() + 208U, header_digest);
  return raw;
}

struct Header {
  std::uint32_t mode = 0;
  std::uint64_t first_block = 0;
  std::uint64_t item_count = 0;
  Digest worker{};
  Digest plan{};
  Digest prefix{};
  Digest header_digest{};
};

Header parse_header(const Bytes<kHeaderBytes>& raw, const char* magic,
                    std::uint32_t record_bytes, bool campaign,
                    const Digest& expected_worker,
                    const Digest& expected_plan,
                    const Digest& expected_prefix) {
  if (std::memcmp(raw.data(), magic, 8U) != 0 ||
      load_u32(raw.data() + 8U) != kVersion ||
      load_u32(raw.data() + 12U) != kHeaderBytes ||
      load_u32(raw.data() + 16U) != record_bytes ||
      std::memcmp(raw.data() + 136U, kUpstreamCommit, 40U) != 0 ||
      digest_at(raw.data() + 176U) !=
          parse_digest(kInterpolationPatchHex, "interpolation patch")) {
    throw FinalizerError("native retained header identity differs");
  }
  for (std::size_t index = 240U; index < raw.size(); ++index) {
    if (raw[index] != 0U) {
      throw FinalizerError("native retained header reserved bytes differ");
    }
  }
  Header result;
  result.mode = load_u32(raw.data() + 20U);
  result.first_block = load_u64(raw.data() + 24U);
  result.item_count = load_u64(raw.data() + 32U);
  result.worker = digest_at(raw.data() + 40U);
  result.plan = digest_at(raw.data() + 72U);
  result.prefix = digest_at(raw.data() + 104U);
  result.header_digest = digest_at(raw.data() + 208U);
  if ((result.mode != kBoundedTest && result.mode != kProduction) ||
      result.first_block >= kSourceBlockCount || result.item_count == 0U ||
      result.worker != expected_worker || result.plan != expected_plan ||
      result.prefix != expected_prefix) {
    throw FinalizerError("native retained header contract differs");
  }
  const Digest expected_digest =
      campaign ? domain_hash(kCampaignHeaderDomain, raw.data(), 208U)
               : domain_hash(kShardHeaderDomain, raw.data(), 208U);
  if (result.header_digest != expected_digest) {
    throw FinalizerError("native retained header digest differs");
  }
  return result;
}

Bytes<kFooterBytes> build_footer(const char* magic,
                                 std::uint64_t first_block,
                                 std::uint64_t upper_block,
                                 std::uint64_t block_count,
                                 std::uint64_t first_count,
                                 std::uint64_t last_count,
                                 std::uint64_t slots,
                                 std::uint64_t stationary,
                                 std::uint64_t sparse,
                                 std::optional<std::uint64_t> source_count,
                                 const Digest& merkle_root,
                                 const Digest& stream_digest,
                                 const Digest& header_digest,
                                 bool campaign) {
  Bytes<kFooterBytes> raw{};
  std::memcpy(raw.data(), magic, 8U);
  store_u32(raw.data() + 8U, kVersion);
  store_u32(raw.data() + 12U, kFooterBytes);
  store_u64(raw.data() + 16U, first_block);
  store_u64(raw.data() + 24U, upper_block);
  store_u64(raw.data() + 32U, block_count);
  store_u64(raw.data() + 40U, first_count);
  store_u64(raw.data() + 48U, last_count);
  store_u64(raw.data() + 56U, slots);
  store_u64(raw.data() + 64U, stationary);
  store_u64(raw.data() + 72U, sparse);
  store_u64(raw.data() + 80U, source_count.value_or(kNoCount));
  store_digest(raw.data() + 88U, merkle_root);
  store_digest(raw.data() + 120U, stream_digest);
  store_digest(raw.data() + 152U, header_digest);
  const Digest footer_digest =
      campaign ? domain_hash(kCampaignFooterDomain, raw.data(), 224U)
               : domain_hash(kShardFooterDomain, raw.data(), 224U);
  store_digest(raw.data() + 224U, footer_digest);
  return raw;
}

struct ShardInfo {
  fs::path path;
  std::uint32_t mode = 0;
  std::uint64_t first_block = 0;
  std::uint64_t upper_block = 0;
  std::uint64_t block_count = 0;
  std::uint64_t first_count = 0;
  std::uint64_t last_count = 0;
  std::uint64_t slots = 0;
  std::uint64_t stationary = 0;
  std::uint64_t sparse = 0;
  std::optional<std::uint64_t> source_count;
  std::uint64_t archive_size = 0;
  Digest archive_digest{};
  Digest footer_digest{};
  Digest block_root{};
  Digest worker{};
  Digest plan{};
  Digest prefix{};
  Digest record_stream_digest{};
};

ShardInfo read_shard(const fs::path& path, const Digest& expected_worker,
                     const Digest& expected_plan,
                     const Digest& expected_prefix,
                     std::optional<std::uint32_t> expected_mode) {
  Reader reader(path);
  sparkinterval::detail::Sha256 archive_hasher;
  Bytes<kHeaderBytes> header_raw{};
  reader.read_exact(header_raw.data(), header_raw.size(), "shard header");
  archive_hasher.update(header_raw.data(), header_raw.size());
  const Header header =
      parse_header(header_raw, kShardHeaderMagic, kBlockBytes, false,
                   expected_worker, expected_plan, expected_prefix);
  if (expected_mode.has_value() && header.mode != *expected_mode) {
    throw FinalizerError("campaign and shard modes differ");
  }
  if (header.item_count > kSourceBlockCount - header.first_block ||
      header.item_count >
          (std::numeric_limits<std::uint64_t>::max() -
           kHeaderBytes - kFooterBytes) /
              kBlockBytes) {
    throw FinalizerError("native shard geometry overflows");
  }
  const std::uint64_t expected_size =
      kHeaderBytes + header.item_count * kBlockBytes + kFooterBytes;
  if (reader.size() != expected_size) {
    throw FinalizerError("native shard archive length differs");
  }
  sparkinterval::detail::Sha256 record_stream_hasher;
  MerkleAccumulator merkle(MerkleAccumulator::Kind::kBlocks);
  std::uint64_t first_count = 0;
  std::uint64_t last_count = 0;
  std::uint64_t slots = 0;
  std::uint64_t stationary = 0;
  std::uint64_t sparse = 0;
  std::optional<std::uint64_t> source_count;
  for (std::uint64_t offset = 0; offset < header.item_count; ++offset) {
    Bytes<kBlockBytes> raw{};
    reader.read_exact(raw.data(), raw.size(), "native block record");
    archive_hasher.update(raw.data(), raw.size());
    record_stream_hasher.update(raw.data(), raw.size());
    const Record record =
        parse_record(raw, header.first_block + offset);
    if (record.producer != header.worker) {
      throw FinalizerError(
          "native block producer differs from the shard worker");
    }
    if (offset == 0U) {
      first_count = record.lower_count;
    } else if (last_count != record.lower_count) {
      throw FinalizerError("native shard count chain is not contiguous");
    }
    last_count = record.upper_count;
    checked_add(slots, record.slots, "slot");
    checked_add(stationary, record.stationary, "stationary");
    checked_add(sparse, record.sparse, "sparse");
    if (record.source_count.has_value()) {
      if (source_count.has_value()) {
        throw FinalizerError(
            "native shard has duplicate source-height counts");
      }
      source_count = record.source_count;
    }
    merkle.add(record.digest);
  }
  const bool contains_target =
      header.first_block <= kSourceHeightBlock &&
      kSourceHeightBlock < header.first_block + header.item_count;
  if (contains_target != source_count.has_value()) {
    throw FinalizerError(
        "native shard source-height count multiplicity differs");
  }
  if (header.mode == kProduction && header.first_block == 0U &&
      first_count != kSourceLowerCount) {
    throw FinalizerError("production shard does not start at N(10^10)");
  }
  const Digest record_stream_digest = record_stream_hasher.finish();
  const Digest block_root = merkle.finish();
  Bytes<kFooterBytes> footer_raw{};
  reader.read_exact(footer_raw.data(), footer_raw.size(), "shard footer");
  archive_hasher.update(footer_raw.data(), footer_raw.size());
  if (std::memcmp(footer_raw.data(), kShardFooterMagic, 8U) != 0 ||
      load_u32(footer_raw.data() + 8U) != kVersion ||
      load_u32(footer_raw.data() + 12U) != kFooterBytes ||
      load_u64(footer_raw.data() + 16U) != header.first_block ||
      load_u64(footer_raw.data() + 24U) !=
          header.first_block + header.item_count ||
      load_u64(footer_raw.data() + 32U) != header.item_count ||
      load_u64(footer_raw.data() + 40U) != first_count ||
      load_u64(footer_raw.data() + 48U) != last_count ||
      load_u64(footer_raw.data() + 56U) != slots ||
      load_u64(footer_raw.data() + 64U) != stationary ||
      load_u64(footer_raw.data() + 72U) != sparse ||
      load_u64(footer_raw.data() + 80U) !=
          source_count.value_or(kNoCount) ||
      digest_at(footer_raw.data() + 88U) != block_root ||
      digest_at(footer_raw.data() + 120U) != record_stream_digest ||
      digest_at(footer_raw.data() + 152U) != header.header_digest) {
    throw FinalizerError("native shard footer summary differs");
  }
  for (std::size_t index = 184U; index < 224U; ++index) {
    if (footer_raw[index] != 0U) {
      throw FinalizerError("native shard footer reserved bytes differ");
    }
  }
  const Digest footer_digest = digest_at(footer_raw.data() + 224U);
  if (footer_digest !=
      domain_hash(kShardFooterDomain, footer_raw.data(), 224U)) {
    throw FinalizerError("native shard footer digest differs");
  }
  if (reader.consumed() != reader.size()) {
    throw FinalizerError("native shard has trailing bytes");
  }
  return ShardInfo{
      .path = path,
      .mode = header.mode,
      .first_block = header.first_block,
      .upper_block = header.first_block + header.item_count,
      .block_count = header.item_count,
      .first_count = first_count,
      .last_count = last_count,
      .slots = slots,
      .stationary = stationary,
      .sparse = sparse,
      .source_count = source_count,
      .archive_size = reader.size(),
      .archive_digest = archive_hasher.finish(),
      .footer_digest = footer_digest,
      .block_root = block_root,
      .worker = header.worker,
      .plan = header.plan,
      .prefix = header.prefix,
      .record_stream_digest = record_stream_digest,
  };
}

Bytes<kSummaryBytes> build_summary(const ShardInfo& shard) {
  Bytes<kSummaryBytes> raw{};
  std::memcpy(raw.data(), kCampaignSummaryMagic, 8U);
  store_u32(raw.data() + 8U, kVersion);
  store_u32(raw.data() + 12U, kSummaryBytes);
  store_u64(raw.data() + 16U, shard.first_block);
  store_u64(raw.data() + 24U, shard.upper_block);
  store_u64(raw.data() + 32U, shard.block_count);
  store_u64(raw.data() + 40U, shard.first_count);
  store_u64(raw.data() + 48U, shard.last_count);
  store_u64(raw.data() + 56U, shard.slots);
  store_u64(raw.data() + 64U, shard.stationary);
  store_u64(raw.data() + 72U, shard.sparse);
  store_u64(raw.data() + 80U, shard.source_count.value_or(kNoCount));
  store_u64(raw.data() + 88U, shard.archive_size);
  store_digest(raw.data() + 96U, shard.archive_digest);
  store_digest(raw.data() + 128U, shard.footer_digest);
  store_digest(raw.data() + 160U, shard.block_root);
  store_digest(raw.data() + 192U, shard.worker);
  store_digest(raw.data() + 224U, shard.record_stream_digest);
  store_digest(raw.data() + 256U,
               domain_hash(kCampaignSummaryDomain, raw.data(), 256U));
  return raw;
}

std::uint64_t parse_u64(std::string_view value, std::string_view label) {
  if (value.empty()) {
    throw FinalizerError(std::string(label) + " is empty");
  }
  std::uint64_t result = 0;
  for (const char character : value) {
    if (character < '0' || character > '9') {
      throw FinalizerError(std::string(label) + " is not an integer");
    }
    const unsigned int digit = static_cast<unsigned int>(character - '0');
    if (result > (std::numeric_limits<std::uint64_t>::max() - digit) / 10U) {
      throw FinalizerError(std::string(label) + " overflows uint64");
    }
    result = result * 10U + digit;
  }
  return result;
}

struct Options {
  std::map<std::string, std::string> values;
  bool bounded_test = false;
};

Options parse_options(int argc, char** argv, int first) {
  Options result;
  for (int index = first; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--bounded-test") {
      if (result.bounded_test) {
        throw FinalizerError("duplicate --bounded-test");
      }
      result.bounded_test = true;
      continue;
    }
    if (!argument.starts_with("--") || index + 1 >= argc) {
      throw FinalizerError("malformed finalizer option: " + argument);
    }
    const std::string key = argument.substr(2);
    if (result.values.contains(key)) {
      throw FinalizerError("duplicate finalizer option: --" + key);
    }
    result.values.emplace(key, argv[++index]);
  }
  return result;
}

std::string take(Options& options, const std::string& key) {
  const auto found = options.values.find(key);
  if (found == options.values.end()) {
    throw FinalizerError("missing --" + key);
  }
  std::string value = found->second;
  options.values.erase(found);
  return value;
}

std::optional<std::string> take_optional(Options& options,
                                         const std::string& key) {
  const auto found = options.values.find(key);
  if (found == options.values.end()) return std::nullopt;
  std::string value = found->second;
  options.values.erase(found);
  return value;
}

void require_exhausted(const Options& options) {
  if (!options.values.empty()) {
    throw FinalizerError("unknown finalizer option: --" +
                         options.values.begin()->first);
  }
}

std::vector<fs::path> read_shard_list(const fs::path& path) {
  Reader reader(path);
  if (reader.size() == 0U || reader.size() > kMaximumShardListBytes) {
    throw FinalizerError("shard list has an invalid byte length");
  }
  std::vector<unsigned char> raw(static_cast<std::size_t>(reader.size()));
  reader.read_exact(raw.data(), raw.size(), "shard list");
  if (raw.back() != '\n') {
    throw FinalizerError("shard list is not newline terminated");
  }
  std::vector<fs::path> paths;
  std::size_t start = 0;
  for (std::size_t index = 0; index < raw.size(); ++index) {
    if (raw[index] == '\0' || raw[index] == '\r') {
      throw FinalizerError("shard list contains a forbidden byte");
    }
    if (raw[index] != '\n') continue;
    if (index == start) throw FinalizerError("shard list contains an empty row");
    paths.emplace_back(
        std::string(reinterpret_cast<const char*>(raw.data() + start),
                    index - start));
    start = index + 1U;
  }
  std::map<std::string, bool> unique;
  for (const fs::path& item : paths) {
    if (!unique.emplace(item.string(), true).second) {
      throw FinalizerError("shard list repeats a path");
    }
  }
  return paths;
}

void emit_shard_json(const ShardInfo& shard) {
  std::cout << "{\"archive_sha256\":\""
            << sparkinterval::lowercase_hex(shard.archive_digest)
            << "\",\"archive_size_bytes\":" << shard.archive_size
            << ",\"block_count\":" << shard.block_count
            << ",\"first_block\":" << shard.first_block
            << ",\"first_count\":" << shard.first_count
            << ",\"last_count\":" << shard.last_count
            << ",\"mode\":\""
            << (shard.mode == kProduction ? "production" : "bounded_test")
            << "\",\"schema\":\"sparkinterval.tg.platt-pt21-native-shard-summary.v1\""
            << ",\"source_claim_ready\":false"
            << ",\"source_height_count\":";
  if (shard.source_count.has_value()) {
    std::cout << *shard.source_count;
  } else {
    std::cout << "null";
  }
  std::cout << ",\"total_main_slots\":" << shard.slots
            << ",\"total_sparse_refinements\":" << shard.sparse
            << ",\"total_stationary_resolutions\":" << shard.stationary
            << ",\"upper_block_exclusive\":" << shard.upper_block << "}\n";
}

int finalize_shard(Options options) {
  const fs::path input = take(options, "input");
  const fs::path output = take(options, "output");
  const std::uint64_t first_block =
      parse_u64(take(options, "first-block"), "first block");
  const std::uint64_t block_count =
      parse_u64(take(options, "block-count"), "block count");
  const Digest worker =
      parse_digest(take(options, "worker-sha256"), "worker");
  const Digest plan = parse_digest(take(options, "plan-sha256"), "plan");
  const Digest prefix =
      parse_digest(take(options, "prefix-evidence-sha256"), "prefix evidence");
  const std::optional<std::string> stream_auth_text =
      take_optional(options, "stream-auth-sha256");
  const std::optional<Digest> stream_auth =
      stream_auth_text.has_value()
          ? std::optional<Digest>(
                parse_digest(*stream_auth_text, "stream authentication"))
          : std::nullopt;
  require_exhausted(options);
  if ((input == fs::path("-")) != stream_auth.has_value()) {
    throw FinalizerError(
        "standard-input mode requires exactly one --stream-auth-sha256");
  }
  if (block_count == 0U || first_block >= kSourceBlockCount ||
      block_count > kSourceBlockCount - first_block ||
      block_count >
          std::numeric_limits<std::uint64_t>::max() / kBlockBytes) {
    throw FinalizerError("shard geometry is outside the PT21 campaign");
  }
  Reader records(input);
  const std::uint64_t expected_input_bytes =
      block_count * kBlockBytes +
      (stream_auth.has_value() ? kStreamAuthBytes : 0U);
  if (records.has_known_size() &&
      records.size() != expected_input_bytes) {
    throw FinalizerError("native block-record stream length differs");
  }
  const std::uint32_t mode =
      options.bounded_test ? kBoundedTest : kProduction;
  const Bytes<kHeaderBytes> header =
      build_header(kShardHeaderMagic, kBlockBytes, mode, first_block,
                   block_count, worker, plan, prefix, false);
  AtomicWriter writer(output);
  sparkinterval::detail::Sha256 archive_hasher;
  writer.write_all(header.data(), header.size());
  archive_hasher.update(header.data(), header.size());
  sparkinterval::detail::Sha256 record_stream_hasher;
  MerkleAccumulator merkle(MerkleAccumulator::Kind::kBlocks);
  std::uint64_t first_count = 0;
  std::uint64_t last_count = 0;
  std::uint64_t slots = 0;
  std::uint64_t stationary = 0;
  std::uint64_t sparse = 0;
  std::optional<std::uint64_t> source_count;
  for (std::uint64_t offset = 0; offset < block_count; ++offset) {
    Bytes<kBlockBytes> raw{};
    records.read_exact(raw.data(), raw.size(), "native block record");
    const Record record = parse_record(raw, first_block + offset);
    if (record.producer != worker) {
      throw FinalizerError(
          "native block producer differs from the shard worker");
    }
    if (offset == 0U) {
      first_count = record.lower_count;
    } else if (last_count != record.lower_count) {
      throw FinalizerError("native shard count chain is not contiguous");
    }
    last_count = record.upper_count;
    checked_add(slots, record.slots, "slot");
    checked_add(stationary, record.stationary, "stationary");
    checked_add(sparse, record.sparse, "sparse");
    if (record.source_count.has_value()) {
      if (source_count.has_value()) {
        throw FinalizerError(
            "native shard has duplicate source-height counts");
      }
      source_count = record.source_count;
    }
    merkle.add(record.digest);
    record_stream_hasher.update(raw.data(), raw.size());
    archive_hasher.update(raw.data(), raw.size());
    writer.write_all(raw.data(), raw.size());
  }
  if (stream_auth.has_value()) {
    Bytes<kStreamAuthBytes> authentication{};
    records.read_exact(authentication.data(), authentication.size(),
                       "native record-stream authentication footer");
    if (std::memcmp(authentication.data(), kStreamAuthMagic, 8U) != 0 ||
        load_u32(authentication.data() + 8U) != kVersion ||
        load_u32(authentication.data() + 12U) != kStreamAuthBytes ||
        digest_at(authentication.data() + 16U) != *stream_auth) {
      throw FinalizerError(
          "native record-stream authentication footer differs");
    }
  }
  records.require_eof("native block-record stream");
  const bool contains_target =
      first_block <= kSourceHeightBlock &&
      kSourceHeightBlock < first_block + block_count;
  if (contains_target != source_count.has_value()) {
    throw FinalizerError(
        "native shard source-height count multiplicity differs");
  }
  if (mode == kProduction && first_block == 0U &&
      first_count != kSourceLowerCount) {
    throw FinalizerError("production shard does not start at N(10^10)");
  }
  const Digest record_stream_digest = record_stream_hasher.finish();
  const Digest block_root = merkle.finish();
  const Bytes<kFooterBytes> footer = build_footer(
      kShardFooterMagic, first_block, first_block + block_count, block_count,
      first_count, last_count, slots, stationary, sparse, source_count,
      block_root, record_stream_digest, digest_at(header.data() + 208U), false);
  writer.write_all(footer.data(), footer.size());
  archive_hasher.update(footer.data(), footer.size());
  const Digest archive_digest = archive_hasher.finish();
  writer.publish();
  const ShardInfo result{
      .path = output,
      .mode = mode,
      .first_block = first_block,
      .upper_block = first_block + block_count,
      .block_count = block_count,
      .first_count = first_count,
      .last_count = last_count,
      .slots = slots,
      .stationary = stationary,
      .sparse = sparse,
      .source_count = source_count,
      .archive_size = writer.size(),
      .archive_digest = archive_digest,
      .footer_digest = digest_at(footer.data() + 224U),
      .block_root = block_root,
      .worker = worker,
      .plan = plan,
      .prefix = prefix,
      .record_stream_digest = record_stream_digest,
  };
  emit_shard_json(result);
  return 0;
}

int finalize_campaign(Options options) {
  const fs::path list_path = take(options, "shard-list");
  const fs::path output = take(options, "output");
  const Digest worker =
      parse_digest(take(options, "worker-sha256"), "worker");
  const Digest plan = parse_digest(take(options, "plan-sha256"), "plan");
  const Digest prefix =
      parse_digest(take(options, "prefix-evidence-sha256"), "prefix evidence");
  require_exhausted(options);
  const std::vector<fs::path> paths = read_shard_list(list_path);
  if (paths.empty()) throw FinalizerError("campaign has no shard archives");
  const std::uint32_t mode =
      options.bounded_test ? kBoundedTest : kProduction;
  std::vector<ShardInfo> shards;
  shards.reserve(paths.size());
  for (const fs::path& path : paths) {
    ShardInfo shard =
        read_shard(path, worker, plan, prefix, mode);
    if (!shards.empty() &&
        (shards.back().upper_block != shard.first_block ||
         shards.back().last_count != shard.first_count)) {
      throw FinalizerError(
          "campaign shard chain is not gap-free and telescoping");
    }
    shards.push_back(std::move(shard));
  }
  const std::uint64_t first_block = shards.front().first_block;
  const Bytes<kHeaderBytes> header = build_header(
      kCampaignHeaderMagic, kSummaryBytes, mode, first_block, shards.size(),
      worker, plan, prefix, true);
  AtomicWriter writer(output);
  sparkinterval::detail::Sha256 archive_hasher;
  writer.write_all(header.data(), header.size());
  archive_hasher.update(header.data(), header.size());
  sparkinterval::detail::Sha256 summary_stream_hasher;
  MerkleAccumulator merkle(MerkleAccumulator::Kind::kCampaign);
  std::uint64_t block_count = 0;
  std::uint64_t slots = 0;
  std::uint64_t stationary = 0;
  std::uint64_t sparse = 0;
  std::optional<std::uint64_t> source_count;
  for (const ShardInfo& shard : shards) {
    checked_add(block_count, shard.block_count, "block");
    checked_add(slots, shard.slots, "slot");
    checked_add(stationary, shard.stationary, "stationary");
    checked_add(sparse, shard.sparse, "sparse");
    if (shard.source_count.has_value()) {
      if (source_count.has_value()) {
        throw FinalizerError(
            "campaign has duplicate source-height counts");
      }
      source_count = shard.source_count;
    }
    const Bytes<kSummaryBytes> summary = build_summary(shard);
    const Digest summary_digest = digest_at(summary.data() + 256U);
    merkle.add(summary_digest);
    summary_stream_hasher.update(summary.data(), summary.size());
    archive_hasher.update(summary.data(), summary.size());
    writer.write_all(summary.data(), summary.size());
  }
  const std::uint64_t upper_block = shards.back().upper_block;
  if (mode == kProduction &&
      (first_block != 0U || upper_block != kSourceBlockCount ||
       block_count != kSourceBlockCount ||
       shards.front().first_count != kSourceLowerCount ||
       !source_count.has_value() ||
       *source_count != kSourceHeightCount)) {
    throw FinalizerError(
        "production native campaign differs from the PT21 source claim");
  }
  const Digest summary_stream_digest = summary_stream_hasher.finish();
  const Digest shard_root = merkle.finish();
  const Bytes<kFooterBytes> footer = build_footer(
      kCampaignFooterMagic, first_block, upper_block, block_count,
      shards.front().first_count, shards.back().last_count, slots, stationary,
      sparse, source_count, shard_root, summary_stream_digest,
      digest_at(header.data() + 208U), true);
  writer.write_all(footer.data(), footer.size());
  archive_hasher.update(footer.data(), footer.size());
  const Digest archive_digest = archive_hasher.finish();
  writer.publish();
  std::cout
      << "{\"archive_sha256\":\""
      << sparkinterval::lowercase_hex(archive_digest)
      << "\",\"archive_size_bytes\":" << writer.size()
      << ",\"block_count\":" << block_count
      << ",\"first_block\":" << first_block
      << ",\"first_count\":" << shards.front().first_count
      << ",\"last_count\":" << shards.back().last_count << ",\"mode\":\""
      << (mode == kProduction ? "production" : "bounded_test")
      << "\",\"schema\":\"sparkinterval.tg.platt-pt21-native-campaign-summary.v1\""
      << ",\"shard_count\":" << shards.size()
      << ",\"source_claim_ready\":false"
      << ",\"source_height_count\":";
  if (source_count.has_value()) {
    std::cout << *source_count;
  } else {
    std::cout << "null";
  }
  std::cout << ",\"total_main_slots\":" << slots
            << ",\"total_sparse_refinements\":" << sparse
            << ",\"total_stationary_resolutions\":" << stationary
            << ",\"upper_block_exclusive\":" << upper_block << "}\n";
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 2) {
      throw FinalizerError("expected 'shard' or 'campaign'");
    }
    const std::string command = argv[1];
    Options options = parse_options(argc, argv, 2);
    if (command == "shard") return finalize_shard(std::move(options));
    if (command == "campaign") return finalize_campaign(std::move(options));
    throw FinalizerError("unknown command: " + command);
  } catch (const std::exception& error) {
    std::cerr << "tg_platt_pt21_native_finalizer: " << error.what() << '\n';
    return 2;
  }
}

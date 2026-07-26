/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

/*
 * Non-authorizing cloud-only prototype loader for the Sqrt218 pure entry.
 *
 * This source is an auditable systems implementation, not a formal ELF/x86
 * refinement and not authority for a Lean theorem.  The separate cloud build
 * lane pins its source/toolchain/output identities.  Production arithmetic is
 * never run by that build lane.
 */

#define _GNU_SOURCE 1

#include "sqrt218_launcher_abi.h"
#include "sqrt218_launcher_sha256.h"

#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/fs.h>
#include <linux/openat2.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#if !defined(__x86_64__)
#error "the Sqrt218 pure-entry launcher is x86-64 only"
#endif

#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "the Sqrt218 pure-entry launcher requires little-endian x86-64"
#endif

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

#ifndef RENAME_NOREPLACE
#define RENAME_NOREPLACE (1U << 0)
#endif

#ifndef SHT_RELR
#define SHT_RELR 19
#endif

#define TG_CONTROL_BYTES ((size_t)256)
#define TG_RESULT_BYTES ((size_t)120)
#define TG_STATUS_BYTES ((size_t)4)
#define TG_OBSERVATION_BYTES ((size_t)48)
#define TG_STACK_MIB UINT32_C(8)
#define TG_STACK_BYTES ((size_t)(8U * 1024U * 1024U))
#define TG_MAX_TIMEOUT_SECONDS UINT32_C(604800)
#define TG_MAX_ELF_BYTES UINT64_C(134217728)
#define TG_MAX_INPUT_BYTES UINT64_C(68719476736)
#define TG_MAX_LOAD_SEGMENTS ((size_t)16)
#define TG_MAX_SECTION_COUNT UINT16_C(4096)
#define TG_CANARY UINT8_C(0xa5)
#define TG_RFLAGS_DF UINT64_C(0x400)

#define TG_WORKER_SCOPE "sparkinterval.azure-measured-worker.v1"
#define TG_WORKER_BACKEND "azure_sevsnp_cpu"
#define TG_ENV_SCOPE "SPARKINTERVAL_MEASURED_WORKER_SCOPE"
#define TG_ENV_BACKEND "SPARKINTERVAL_MEASURED_WORKER_BACKEND"
#define TG_ENV_CHALLENGE "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE"
#define TG_ENV_JOB "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256"

static const uint8_t tg_control_magic[8] = {
    UINT8_C(0x53), UINT8_C(0x51), UINT8_C(0x32), UINT8_C(0x31),
    UINT8_C(0x38), UINT8_C(0x4c), UINT8_C(0x31), UINT8_C(0x00)
};

static const uint8_t tg_result_magic[8] = {
    UINT8_C(0x53), UINT8_C(0x51), UINT8_C(0x32), UINT8_C(0x31),
    UINT8_C(0x38), UINT8_C(0x52), UINT8_C(0x32), UINT8_C(0x00)
};

typedef struct tg_control {
    uint64_t launcher_size;
    uint8_t launcher_sha256[32];
    uint64_t elf_size;
    uint8_t elf_sha256[32];
    uint64_t input_size;
    uint8_t input_sha256[32];
    uint8_t challenge[32];
    uint8_t job_binding[32];
    uint32_t timeout_seconds;
    uint32_t stack_mib;
} tg_control;

typedef struct tg_file_snapshot {
    uint8_t *bytes;
    size_t length;
    uint8_t sha256[32];
} tg_file_snapshot;

typedef struct tg_guarded_region {
    uint8_t *mapping;
    size_t mapping_bytes;
    uint8_t *usable;
    size_t usable_bytes;
    uint8_t *logical;
    size_t logical_bytes;
    size_t prefix_bytes;
} tg_guarded_region;

typedef struct tg_stack_region {
    uint8_t *mapping;
    size_t mapping_bytes;
    uint8_t *usable;
    size_t usable_bytes;
} tg_stack_region;

typedef struct tg_load_segment {
    uint64_t file_offset;
    uint64_t virtual_address;
    uint64_t file_bytes;
    uint64_t memory_bytes;
    uint32_t flags;
    uint8_t *mapped_address;
    size_t mapped_bytes;
} tg_load_segment;

typedef struct tg_loaded_elf {
    tg_load_segment segments[TG_MAX_LOAD_SEGMENTS];
    size_t segment_count;
    uint64_t entry;
    uint64_t entry_symbol_size;
} tg_loaded_elf;

typedef struct tg_text_builder {
    char bytes[4096];
    size_t used;
} tg_text_builder;

static uint16_t tg_load_le16(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8));
}

static uint32_t tg_load_le32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0]
        | ((uint32_t)bytes[1] << 8)
        | ((uint32_t)bytes[2] << 16)
        | ((uint32_t)bytes[3] << 24);
}

static uint64_t tg_load_le64(const uint8_t *bytes)
{
    uint64_t result = 0;
    unsigned int index;

    for (index = 0; index < 8U; ++index) {
        result |= (uint64_t)bytes[index] << (8U * index);
    }
    return result;
}

static uint16_t tg_load_be16(const uint8_t *bytes)
{
    return (uint16_t)(((uint16_t)bytes[0] << 8) | (uint16_t)bytes[1]);
}

static uint32_t tg_load_be32(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0] << 24)
        | ((uint32_t)bytes[1] << 16)
        | ((uint32_t)bytes[2] << 8)
        | (uint32_t)bytes[3];
}

static uint64_t tg_load_be64(const uint8_t *bytes)
{
    uint64_t result = 0;
    unsigned int index;

    for (index = 0; index < 8U; ++index) {
        result = (result << 8) | (uint64_t)bytes[index];
    }
    return result;
}

static int tg_add_u64(uint64_t left, uint64_t right, uint64_t *result)
{
    if (UINT64_MAX - left < right) {
        return -1;
    }
    *result = left + right;
    return 0;
}

static int tg_mul_u64(uint64_t left, uint64_t right, uint64_t *result)
{
    if (left != 0 && UINT64_MAX / left < right) {
        return -1;
    }
    *result = left * right;
    return 0;
}

static int tg_u64_to_size(uint64_t value, size_t *result)
{
    size_t converted = (size_t)value;

    if ((uint64_t)converted != value) {
        return -1;
    }
    *result = converted;
    return 0;
}

static int tg_range_within(
    uint64_t offset,
    uint64_t length,
    uint64_t container)
{
    uint64_t end;

    return tg_add_u64(offset, length, &end) == 0 && end <= container;
}

static int tg_ranges_overlap(
    uint64_t left_start,
    uint64_t left_length,
    uint64_t right_start,
    uint64_t right_length)
{
    uint64_t left_end;
    uint64_t right_end;

    if (tg_add_u64(left_start, left_length, &left_end) != 0
        || tg_add_u64(right_start, right_length, &right_end) != 0) {
        return 1;
    }
    return left_start < right_end && right_start < left_end;
}

static int tg_digest_is_nonzero(const uint8_t digest[32])
{
    uint8_t combined = 0;
    size_t index;

    for (index = 0; index < 32U; ++index) {
        combined = (uint8_t)(combined | digest[index]);
    }
    return combined != 0;
}

static int tg_constant_time_equal(
    const uint8_t *left,
    const uint8_t *right,
    size_t length)
{
    uint8_t difference = 0;
    size_t index;

    for (index = 0; index < length; ++index) {
        difference = (uint8_t)(difference | (left[index] ^ right[index]));
    }
    return difference == 0;
}

static int tg_all_bytes_equal(
    const uint8_t *bytes,
    size_t length,
    uint8_t expected)
{
    uint8_t difference = 0;
    size_t index;

    for (index = 0; index < length; ++index) {
        difference = (uint8_t)(difference | (bytes[index] ^ expected));
    }
    return difference == 0;
}

static int tg_open_nosymlink(const char *path, int flags)
{
    struct open_how how;

    memset(&how, 0, sizeof(how));
    how.flags = (uint64_t)(flags | O_CLOEXEC | O_NOFOLLOW);
    how.resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS;
    return (int)syscall(SYS_openat2, AT_FDCWD, path, &how, sizeof(how));
}

static int tg_regular_file_stat(int descriptor, struct stat *metadata)
{
    if (fstat(descriptor, metadata) != 0
        || !S_ISREG(metadata->st_mode)
        || metadata->st_nlink != (nlink_t)1
        || metadata->st_size < (off_t)0) {
        return -1;
    }
    return 0;
}

static int tg_stat_identity_equal(
    const struct stat *left,
    const struct stat *right)
{
    return left->st_dev == right->st_dev
        && left->st_ino == right->st_ino
        && left->st_mode == right->st_mode
        && left->st_nlink == right->st_nlink
        && left->st_size == right->st_size
        && left->st_mtim.tv_sec == right->st_mtim.tv_sec
        && left->st_mtim.tv_nsec == right->st_mtim.tv_nsec
        && left->st_ctim.tv_sec == right->st_ctim.tv_sec
        && left->st_ctim.tv_nsec == right->st_ctim.tv_nsec;
}

static int tg_pread_all(
    int descriptor,
    uint8_t *bytes,
    size_t length)
{
    size_t consumed = 0;

    while (consumed < length) {
        ssize_t count = pread(
            descriptor,
            bytes + consumed,
            length - consumed,
            (off_t)consumed);
        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (count == 0) {
            return -1;
        }
        consumed += (size_t)count;
    }
    return 0;
}

static int tg_read_control(
    const char *path,
    tg_control *control,
    uint8_t control_digest[32])
{
    uint8_t raw[TG_CONTROL_BYTES];
    struct stat before;
    struct stat after;
    int descriptor = tg_open_nosymlink(path, O_RDONLY);
    size_t index;

    if (descriptor < 0
        || tg_regular_file_stat(descriptor, &before) != 0
        || before.st_size != (off_t)TG_CONTROL_BYTES
        || tg_pread_all(descriptor, raw, sizeof(raw)) != 0
        || tg_regular_file_stat(descriptor, &after) != 0
        || !tg_stat_identity_equal(&before, &after)
        || close(descriptor) != 0) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        return -1;
    }
    if (!tg_constant_time_equal(raw, tg_control_magic, sizeof(tg_control_magic))
        || tg_load_le32(raw + 8U) != UINT32_C(1)
        || tg_load_le32(raw + 12U) != UINT32_C(256)) {
        return -1;
    }
    for (index = 208U; index < sizeof(raw); ++index) {
        if (raw[index] != 0) {
            return -1;
        }
    }

    control->launcher_size = tg_load_le64(raw + 16U);
    memcpy(control->launcher_sha256, raw + 24U, 32U);
    control->elf_size = tg_load_le64(raw + 56U);
    memcpy(control->elf_sha256, raw + 64U, 32U);
    control->input_size = tg_load_le64(raw + 96U);
    memcpy(control->input_sha256, raw + 104U, 32U);
    memcpy(control->challenge, raw + 136U, 32U);
    memcpy(control->job_binding, raw + 168U, 32U);
    control->timeout_seconds = tg_load_le32(raw + 200U);
    control->stack_mib = tg_load_le32(raw + 204U);
    if (control->launcher_size == 0
        || control->launcher_size > TG_MAX_ELF_BYTES
        || control->elf_size == 0
        || control->elf_size > TG_MAX_ELF_BYTES
        || control->input_size == 0
        || control->input_size > TG_MAX_INPUT_BYTES
        || !tg_digest_is_nonzero(control->launcher_sha256)
        || !tg_digest_is_nonzero(control->elf_sha256)
        || !tg_digest_is_nonzero(control->input_sha256)
        || !tg_digest_is_nonzero(control->challenge)
        || !tg_digest_is_nonzero(control->job_binding)
        || control->timeout_seconds == 0
        || control->timeout_seconds > TG_MAX_TIMEOUT_SECONDS
        || control->stack_mib != TG_STACK_MIB) {
        return -1;
    }
    tg_sq218_sha256(raw, sizeof(raw), control_digest);
    memset(raw, 0, sizeof(raw));
    return 0;
}

static int tg_parse_lower_hex_digest(
    const char *text,
    uint8_t digest[32])
{
    size_t index;

    if (text == NULL || strlen(text) != 64U) {
        return -1;
    }
    for (index = 0; index < 32U; ++index) {
        unsigned int high;
        unsigned int low;
        char high_char = text[2U * index];
        char low_char = text[(2U * index) + 1U];

        if (high_char >= '0' && high_char <= '9') {
            high = (unsigned int)(high_char - '0');
        } else if (high_char >= 'a' && high_char <= 'f') {
            high = (unsigned int)(high_char - 'a') + 10U;
        } else {
            return -1;
        }
        if (low_char >= '0' && low_char <= '9') {
            low = (unsigned int)(low_char - '0');
        } else if (low_char >= 'a' && low_char <= 'f') {
            low = (unsigned int)(low_char - 'a') + 10U;
        } else {
            return -1;
        }
        digest[index] = (uint8_t)((high << 4) | low);
    }
    return 0;
}

static int tg_require_measured_worker(const tg_control *control)
{
    const char *scope = getenv(TG_ENV_SCOPE);
    const char *backend = getenv(TG_ENV_BACKEND);
    uint8_t challenge[32];
    uint8_t job[32];

    if (scope == NULL || strcmp(scope, TG_WORKER_SCOPE) != 0
        || backend == NULL || strcmp(backend, TG_WORKER_BACKEND) != 0
        || tg_parse_lower_hex_digest(getenv(TG_ENV_CHALLENGE), challenge) != 0
        || tg_parse_lower_hex_digest(getenv(TG_ENV_JOB), job) != 0
        || !tg_constant_time_equal(challenge, control->challenge, 32U)
        || !tg_constant_time_equal(job, control->job_binding, 32U)) {
        memset(challenge, 0, sizeof(challenge));
        memset(job, 0, sizeof(job));
        return -1;
    }
    memset(challenge, 0, sizeof(challenge));
    memset(job, 0, sizeof(job));
    return 0;
}

static int tg_hash_open_file(
    const char *path,
    uint64_t expected_size,
    const uint8_t expected_digest[32],
    int allow_proc_self)
{
    uint8_t buffer[65536];
    tg_sq218_sha256_context context;
    struct stat metadata;
    uint64_t consumed = 0;
    int descriptor;
    uint8_t digest[32];

    descriptor = allow_proc_self
        ? open(path, O_RDONLY | O_CLOEXEC)
        : tg_open_nosymlink(path, O_RDONLY);
    if (descriptor < 0
        || tg_regular_file_stat(descriptor, &metadata) != 0
        || (uint64_t)metadata.st_size != expected_size) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        return -1;
    }
    tg_sq218_sha256_init(&context);
    while (consumed < expected_size) {
        size_t remaining = (size_t)(
            expected_size - consumed > (uint64_t)sizeof(buffer)
                ? (uint64_t)sizeof(buffer)
                : expected_size - consumed);
        ssize_t count = pread(
            descriptor,
            buffer,
            remaining,
            (off_t)consumed);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            (void)close(descriptor);
            return -1;
        }
        tg_sq218_sha256_update(&context, buffer, (size_t)count);
        consumed += (uint64_t)count;
    }
    if (close(descriptor) != 0) {
        return -1;
    }
    tg_sq218_sha256_final(&context, digest);
    memset(buffer, 0, sizeof(buffer));
    if (!tg_constant_time_equal(digest, expected_digest, 32U)) {
        memset(digest, 0, sizeof(digest));
        return -1;
    }
    memset(digest, 0, sizeof(digest));
    return 0;
}

static int tg_read_file_snapshot(
    const char *path,
    uint64_t expected_size,
    const uint8_t expected_digest[32],
    tg_file_snapshot *snapshot)
{
    struct stat before;
    struct stat after;
    size_t length;
    int descriptor;

    memset(snapshot, 0, sizeof(*snapshot));
    if (tg_u64_to_size(expected_size, &length) != 0) {
        return -1;
    }
    descriptor = tg_open_nosymlink(path, O_RDONLY);
    if (descriptor < 0
        || tg_regular_file_stat(descriptor, &before) != 0
        || (uint64_t)before.st_size != expected_size) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        return -1;
    }
    snapshot->bytes = malloc(length);
    if (snapshot->bytes == NULL
        || tg_pread_all(descriptor, snapshot->bytes, length) != 0
        || tg_regular_file_stat(descriptor, &after) != 0
        || !tg_stat_identity_equal(&before, &after)
        || close(descriptor) != 0) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        free(snapshot->bytes);
        memset(snapshot, 0, sizeof(*snapshot));
        return -1;
    }
    snapshot->length = length;
    tg_sq218_sha256(snapshot->bytes, snapshot->length, snapshot->sha256);
    if (!tg_constant_time_equal(snapshot->sha256, expected_digest, 32U)) {
        free(snapshot->bytes);
        memset(snapshot, 0, sizeof(*snapshot));
        return -1;
    }
    return 0;
}

static void tg_free_file_snapshot(tg_file_snapshot *snapshot)
{
    if (snapshot->bytes != NULL) {
        memset(snapshot->bytes, 0, snapshot->length);
        free(snapshot->bytes);
    }
    memset(snapshot, 0, sizeof(*snapshot));
}

static size_t tg_page_size(void)
{
    long value = sysconf(_SC_PAGESIZE);

    if (value < 4096L
        || (value & (value - 1L)) != 0
        || (uintmax_t)value > (uintmax_t)SIZE_MAX) {
        return 0;
    }
    return (size_t)value;
}

static int tg_align_up_size(
    size_t value,
    size_t alignment,
    size_t *result)
{
    size_t mask = alignment - 1U;

    if ((alignment & mask) != 0 || value > SIZE_MAX - mask) {
        return -1;
    }
    *result = (value + mask) & ~mask;
    return 0;
}

static int tg_guarded_region_create(
    size_t logical_bytes,
    int shared,
    tg_guarded_region *region)
{
    size_t page = tg_page_size();
    size_t total;
    int flags = MAP_ANONYMOUS | (shared ? MAP_SHARED : MAP_PRIVATE);
    void *mapping;

    memset(region, 0, sizeof(*region));
    if (page == 0
        || logical_bytes == 0
        || tg_align_up_size(logical_bytes, page, &region->usable_bytes) != 0
        || region->usable_bytes > SIZE_MAX - (2U * page)) {
        return -1;
    }
    total = region->usable_bytes + (2U * page);
    mapping = mmap(NULL, total, PROT_NONE, flags, -1, (off_t)0);
    if (mapping == MAP_FAILED) {
        return -1;
    }
    region->mapping = mapping;
    region->mapping_bytes = total;
    region->usable = region->mapping + page;
    if (mprotect(
            region->usable,
            region->usable_bytes,
            PROT_READ | PROT_WRITE) != 0
        || madvise(region->mapping, total, MADV_DONTDUMP) != 0) {
        (void)munmap(region->mapping, region->mapping_bytes);
        memset(region, 0, sizeof(*region));
        return -1;
    }
    memset(region->usable, TG_CANARY, region->usable_bytes);
    region->logical_bytes = logical_bytes;
    region->logical =
        region->usable + (region->usable_bytes - logical_bytes);
    region->prefix_bytes = region->usable_bytes - logical_bytes;
    return 0;
}

static void tg_guarded_region_destroy(tg_guarded_region *region)
{
    if (region->mapping != NULL) {
        (void)munmap(region->mapping, region->mapping_bytes);
    }
    memset(region, 0, sizeof(*region));
}

static int tg_read_input_region(
    const char *path,
    uint64_t expected_size,
    const uint8_t expected_digest[32],
    tg_guarded_region *region,
    uint8_t digest[32])
{
    struct stat before;
    struct stat after;
    size_t length;
    int descriptor;

    if (tg_u64_to_size(expected_size, &length) != 0
        || tg_guarded_region_create(length, 1, region) != 0) {
        return -1;
    }
    descriptor = tg_open_nosymlink(path, O_RDONLY);
    if (descriptor < 0
        || tg_regular_file_stat(descriptor, &before) != 0
        || (uint64_t)before.st_size != expected_size
        || tg_pread_all(descriptor, region->logical, length) != 0
        || tg_regular_file_stat(descriptor, &after) != 0
        || !tg_stat_identity_equal(&before, &after)
        || close(descriptor) != 0) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        tg_guarded_region_destroy(region);
        return -1;
    }
    tg_sq218_sha256(region->logical, length, digest);
    if (!tg_constant_time_equal(digest, expected_digest, 32U)
        || mprotect(region->usable, region->usable_bytes, PROT_READ) != 0) {
        tg_guarded_region_destroy(region);
        return -1;
    }
    return 0;
}

static int tg_stack_create(tg_stack_region *stack)
{
    size_t page = tg_page_size();
    size_t total;
    void *mapping;

    memset(stack, 0, sizeof(*stack));
    if (page == 0 || TG_STACK_BYTES > SIZE_MAX - (2U * page)) {
        return -1;
    }
    total = TG_STACK_BYTES + (2U * page);
    mapping = mmap(
        NULL,
        total,
        PROT_NONE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK,
        -1,
        (off_t)0);
    if (mapping == MAP_FAILED) {
        return -1;
    }
    stack->mapping = mapping;
    stack->mapping_bytes = total;
    stack->usable = stack->mapping + page;
    stack->usable_bytes = TG_STACK_BYTES;
    if (mprotect(
            stack->usable,
            stack->usable_bytes,
            PROT_READ | PROT_WRITE) != 0
        || madvise(stack->mapping, total, MADV_DONTDUMP) != 0) {
        (void)munmap(stack->mapping, stack->mapping_bytes);
        memset(stack, 0, sizeof(*stack));
        return -1;
    }
    return 0;
}

static void tg_stack_destroy(tg_stack_region *stack)
{
    if (stack->mapping != NULL) {
        (void)munmap(stack->mapping, stack->mapping_bytes);
    }
    memset(stack, 0, sizeof(*stack));
}

static int tg_section_header(
    const tg_file_snapshot *snapshot,
    uint64_t section_offset,
    uint16_t section_index,
    const uint8_t **header)
{
    uint64_t offset;
    uint64_t index_bytes;

    if (tg_mul_u64((uint64_t)section_index, UINT64_C(64), &index_bytes) != 0
        || tg_add_u64(section_offset, index_bytes, &offset) != 0
        || !tg_range_within(offset, UINT64_C(64), snapshot->length)) {
        return -1;
    }
    *header = snapshot->bytes + (size_t)offset;
    return 0;
}

static int tg_entry_in_executable_segment(
    const tg_loaded_elf *loaded,
    uint64_t start,
    uint64_t size)
{
    size_t index;
    uint64_t end;

    if (size == 0 || tg_add_u64(start, size, &end) != 0) {
        return 0;
    }
    for (index = 0; index < loaded->segment_count; ++index) {
        const tg_load_segment *segment = &loaded->segments[index];
        uint64_t segment_end;

        if ((segment->flags & PF_X) != 0
            && tg_add_u64(
                segment->virtual_address,
                segment->memory_bytes,
                &segment_end) == 0
            && start >= segment->virtual_address
            && end <= segment_end) {
            return 1;
        }
    }
    return 0;
}

static int tg_validate_entry_symbol(
    const tg_file_snapshot *snapshot,
    uint64_t section_offset,
    uint16_t section_count,
    tg_loaded_elf *loaded)
{
    const char expected_name[] = "tg_sq218_verify_snapshot_v2";
    const uint8_t *symbol_header = NULL;
    uint16_t symbol_section_index = 0;
    uint16_t index;
    unsigned int symbol_tables = 0;
    unsigned int matches = 0;

    for (index = 0; index < section_count; ++index) {
        const uint8_t *header;
        uint32_t type;
        uint64_t flags;
        uint64_t offset;
        uint64_t size;

        if (tg_section_header(
                snapshot, section_offset, index, &header) != 0) {
            return -1;
        }
        type = tg_load_le32(header + 4U);
        flags = tg_load_le64(header + 8U);
        offset = tg_load_le64(header + 24U);
        size = tg_load_le64(header + 32U);
        if (type == SHT_REL
            || type == SHT_RELA
            || type == SHT_RELR
            || type == SHT_DYNAMIC) {
            return -1;
        }
        if ((flags & (SHF_WRITE | SHF_EXECINSTR))
            == (SHF_WRITE | SHF_EXECINSTR)) {
            return -1;
        }
        if (type != SHT_NOBITS
            && !tg_range_within(offset, size, snapshot->length)) {
            return -1;
        }
        if (type == SHT_SYMTAB) {
            ++symbol_tables;
            symbol_header = header;
            symbol_section_index = index;
        }
    }
    if (symbol_tables != 1U || symbol_header == NULL) {
        return -1;
    }
    {
        uint64_t symbol_offset = tg_load_le64(symbol_header + 24U);
        uint64_t symbol_bytes = tg_load_le64(symbol_header + 32U);
        uint32_t string_index = tg_load_le32(symbol_header + 40U);
        uint64_t entry_size = tg_load_le64(symbol_header + 56U);
        const uint8_t *string_header;
        uint64_t string_offset;
        uint64_t string_bytes;
        uint64_t symbol_count;
        uint64_t symbol_index;

        if (entry_size != UINT64_C(24)
            || symbol_bytes == 0
            || symbol_bytes % entry_size != 0
            || string_index >= section_count
            || string_index == symbol_section_index
            || tg_section_header(
                snapshot,
                section_offset,
                (uint16_t)string_index,
                &string_header) != 0
            || tg_load_le32(string_header + 4U) != SHT_STRTAB) {
            return -1;
        }
        string_offset = tg_load_le64(string_header + 24U);
        string_bytes = tg_load_le64(string_header + 32U);
        if (string_bytes == 0
            || !tg_range_within(
                string_offset, string_bytes, snapshot->length)) {
            return -1;
        }
        symbol_count = symbol_bytes / entry_size;
        for (symbol_index = 0; symbol_index < symbol_count; ++symbol_index) {
            uint64_t offset;
            uint64_t relative;
            const uint8_t *symbol;
            uint32_t name_offset;
            const uint8_t *name;
            size_t remaining;
            const void *terminator;

            if (tg_mul_u64(symbol_index, entry_size, &relative) != 0
                || tg_add_u64(symbol_offset, relative, &offset) != 0
                || !tg_range_within(
                    offset, entry_size, snapshot->length)) {
                return -1;
            }
            symbol = snapshot->bytes + (size_t)offset;
            name_offset = tg_load_le32(symbol);
            if ((uint64_t)name_offset >= string_bytes) {
                return -1;
            }
            name = snapshot->bytes
                + (size_t)(string_offset + (uint64_t)name_offset);
            remaining = (size_t)(string_bytes - (uint64_t)name_offset);
            terminator = memchr(name, '\0', remaining);
            if (terminator == NULL) {
                return -1;
            }
            if ((size_t)((const uint8_t *)terminator - name)
                    == sizeof(expected_name) - 1U
                && memcmp(name, expected_name, sizeof(expected_name)) == 0) {
                uint8_t info = symbol[4];
                uint8_t other = symbol[5];
                uint16_t defining_section = tg_load_le16(symbol + 6U);
                uint64_t value = tg_load_le64(symbol + 8U);
                uint64_t size = tg_load_le64(symbol + 16U);
                const uint8_t *defining_header;
                uint64_t defining_flags;
                uint64_t defining_address;
                uint64_t defining_size;

                ++matches;
                if ((info >> 4) != STB_GLOBAL
                    || (info & UINT8_C(0x0f)) != STT_FUNC
                    || (other & UINT8_C(0x03)) != STV_DEFAULT
                    || defining_section == SHN_UNDEF
                    || defining_section >= section_count
                    || value != loaded->entry
                    || size == 0
                    || tg_section_header(
                        snapshot,
                        section_offset,
                        defining_section,
                        &defining_header) != 0) {
                    return -1;
                }
                defining_flags = tg_load_le64(defining_header + 8U);
                defining_address = tg_load_le64(defining_header + 16U);
                defining_size = tg_load_le64(defining_header + 32U);
                if ((defining_flags & (SHF_ALLOC | SHF_EXECINSTR))
                        != (SHF_ALLOC | SHF_EXECINSTR)
                    || !tg_range_within(
                        defining_address,
                        defining_size,
                        UINT64_MAX)
                    || value < defining_address
                    || !tg_range_within(
                        value - defining_address,
                        size,
                        defining_size)
                    || !tg_entry_in_executable_segment(
                        loaded, value, size)) {
                    return -1;
                }
                loaded->entry_symbol_size = size;
            }
        }
    }
    return matches == 1U ? 0 : -1;
}

static int tg_validate_elf(
    const tg_file_snapshot *snapshot,
    tg_loaded_elf *loaded)
{
    uint64_t program_offset;
    uint64_t section_offset;
    uint16_t program_count;
    uint16_t section_count;
    uint16_t section_names;
    uint64_t table_bytes;
    uint16_t index;
    size_t page = tg_page_size();
    int stack_header_seen = 0;
    int executable_seen = 0;
    size_t ident_index;

    memset(loaded, 0, sizeof(*loaded));
    if (page == 0
        || snapshot->length < 64U
        || memcmp(snapshot->bytes, ELFMAG, SELFMAG) != 0
        || snapshot->bytes[EI_CLASS] != ELFCLASS64
        || snapshot->bytes[EI_DATA] != ELFDATA2LSB
        || snapshot->bytes[EI_VERSION] != EV_CURRENT
        || snapshot->bytes[EI_OSABI] != ELFOSABI_SYSV
        || snapshot->bytes[EI_ABIVERSION] != 0
        || tg_load_le16(snapshot->bytes + 16U) != ET_EXEC
        || tg_load_le16(snapshot->bytes + 18U) != EM_X86_64
        || tg_load_le32(snapshot->bytes + 20U) != EV_CURRENT
        || tg_load_le32(snapshot->bytes + 48U) != UINT32_C(0)
        || tg_load_le16(snapshot->bytes + 52U) != UINT16_C(64)
        || tg_load_le16(snapshot->bytes + 54U) != UINT16_C(56)
        || tg_load_le16(snapshot->bytes + 58U) != UINT16_C(64)) {
        return -1;
    }
    loaded->entry = tg_load_le64(snapshot->bytes + 24U);
    program_offset = tg_load_le64(snapshot->bytes + 32U);
    section_offset = tg_load_le64(snapshot->bytes + 40U);
    program_count = tg_load_le16(snapshot->bytes + 56U);
    section_count = tg_load_le16(snapshot->bytes + 60U);
    section_names = tg_load_le16(snapshot->bytes + 62U);
    if (loaded->entry < UINT64_C(65536)
        || program_count == 0
        || program_count == PN_XNUM
        || section_count == 0
        || section_count > TG_MAX_SECTION_COUNT
        || section_names == SHN_XINDEX
        || section_names >= section_count
        || tg_mul_u64(
            (uint64_t)program_count, UINT64_C(56), &table_bytes) != 0
        || !tg_range_within(
            program_offset, table_bytes, snapshot->length)
        || tg_mul_u64(
            (uint64_t)section_count, UINT64_C(64), &table_bytes) != 0
        || !tg_range_within(
            section_offset, table_bytes, snapshot->length)
        || !tg_all_bytes_equal(
            snapshot->bytes + (size_t)section_offset,
            64U,
            UINT8_C(0))) {
        return -1;
    }
    for (ident_index = EI_PAD; ident_index < EI_NIDENT; ++ident_index) {
        if (snapshot->bytes[ident_index] != 0) {
            return -1;
        }
    }

    for (index = 0; index < program_count; ++index) {
        const uint8_t *header =
            snapshot->bytes
            + (size_t)(program_offset + ((uint64_t)index * UINT64_C(56)));
        uint32_t type = tg_load_le32(header);
        uint32_t flags = tg_load_le32(header + 4U);

        if (type == PT_INTERP || type == PT_DYNAMIC || type == PT_TLS) {
            return -1;
        }
        if (type == PT_GNU_STACK) {
            if (stack_header_seen != 0 || (flags & PF_X) != 0) {
                return -1;
            }
            stack_header_seen = 1;
        } else if (type != PT_NULL
                   && type != PT_LOAD
                   && type != PT_NOTE
                   && type != PT_PHDR) {
            return -1;
        }
        if (type == PT_LOAD) {
            tg_load_segment *segment;
            uint64_t alignment = tg_load_le64(header + 48U);
            uint64_t memory_end;
            size_t prior;
            uint64_t page_mask = (uint64_t)page - UINT64_C(1);
            uint64_t page_start;
            uint64_t page_end_unaligned;
            uint64_t page_end;

            if (loaded->segment_count >= TG_MAX_LOAD_SEGMENTS) {
                return -1;
            }
            segment = &loaded->segments[loaded->segment_count];
            segment->file_offset = tg_load_le64(header + 8U);
            segment->virtual_address = tg_load_le64(header + 16U);
            segment->file_bytes = tg_load_le64(header + 32U);
            segment->memory_bytes = tg_load_le64(header + 40U);
            segment->flags = flags;
            if ((flags & ~(uint32_t)(PF_R | PF_W | PF_X)) != 0
                || (flags & (PF_W | PF_X)) == (PF_W | PF_X)
                || segment->memory_bytes == 0
                || segment->file_bytes > segment->memory_bytes
                || segment->virtual_address < UINT64_C(65536)
                || !tg_range_within(
                    segment->file_offset,
                    segment->file_bytes,
                    snapshot->length)
                || tg_add_u64(
                    segment->virtual_address,
                    segment->memory_bytes,
                    &memory_end) != 0
                || alignment == 0
                || (alignment & (alignment - UINT64_C(1))) != 0
                || (segment->virtual_address & (alignment - UINT64_C(1)))
                    != (segment->file_offset & (alignment - UINT64_C(1)))
                || (segment->virtual_address & page_mask)
                    != (segment->file_offset & page_mask)) {
                return -1;
            }
            page_start = segment->virtual_address & ~page_mask;
            if (tg_add_u64(memory_end, page_mask, &page_end_unaligned) != 0) {
                return -1;
            }
            page_end = page_end_unaligned & ~page_mask;
            for (prior = 0; prior < loaded->segment_count; ++prior) {
                const tg_load_segment *other = &loaded->segments[prior];
                uint64_t other_start =
                    other->virtual_address & ~page_mask;
                uint64_t other_memory_end;
                uint64_t other_end_unaligned;
                uint64_t other_end;

                if (tg_add_u64(
                        other->virtual_address,
                        other->memory_bytes,
                        &other_memory_end) != 0
                    || tg_add_u64(
                        other_memory_end,
                        page_mask,
                        &other_end_unaligned) != 0) {
                    return -1;
                }
                other_end = other_end_unaligned & ~page_mask;
                if (tg_ranges_overlap(
                        page_start,
                        page_end - page_start,
                        other_start,
                        other_end - other_start)
                    || (segment->file_bytes != 0
                        && other->file_bytes != 0
                        && tg_ranges_overlap(
                            segment->file_offset,
                            segment->file_bytes,
                            other->file_offset,
                            other->file_bytes))) {
                    return -1;
                }
            }
            if ((flags & PF_X) != 0) {
                executable_seen = 1;
            }
            ++loaded->segment_count;
        }
    }
    if (loaded->segment_count == 0
        || stack_header_seen == 0
        || executable_seen == 0
        || !tg_entry_in_executable_segment(loaded, loaded->entry, 1U)
        || tg_validate_entry_symbol(
            snapshot, section_offset, section_count, loaded) != 0) {
        return -1;
    }
    return 0;
}

static int tg_map_elf(
    const tg_file_snapshot *snapshot,
    tg_loaded_elf *loaded)
{
    size_t page = tg_page_size();
    uint64_t page_mask = (uint64_t)page - UINT64_C(1);
    size_t index;

    for (index = 0; index < loaded->segment_count; ++index) {
        tg_load_segment *segment = &loaded->segments[index];
        uint64_t map_start = segment->virtual_address & ~page_mask;
        uint64_t memory_end;
        uint64_t map_end_unaligned;
        uint64_t map_end;
        uint64_t file_page = segment->file_offset & ~page_mask;
        uint64_t file_prefix = segment->file_offset - file_page;
        uint64_t copy_bytes;
        size_t map_bytes;
        int protection = 0;
        void *requested;
        void *mapped;

        if (tg_add_u64(
                segment->virtual_address,
                segment->memory_bytes,
                &memory_end) != 0
            || tg_add_u64(memory_end, page_mask, &map_end_unaligned) != 0) {
            return -1;
        }
        map_end = map_end_unaligned & ~page_mask;
        if (tg_u64_to_size(map_end - map_start, &map_bytes) != 0
            || map_bytes == 0
            || map_start > (uint64_t)UINTPTR_MAX) {
            return -1;
        }
        requested = (void *)(uintptr_t)map_start;
        if ((uint64_t)(uintptr_t)requested != map_start) {
            return -1;
        }
        mapped = mmap(
            requested,
            map_bytes,
            PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
            -1,
            (off_t)0);
        if (mapped == MAP_FAILED || mapped != requested) {
            if (mapped != MAP_FAILED) {
                (void)munmap(mapped, map_bytes);
            }
            return -1;
        }
        segment->mapped_address = mapped;
        segment->mapped_bytes = map_bytes;
        memset(mapped, 0, map_bytes);
        if (segment->file_bytes != 0) {
            if (tg_add_u64(
                    file_prefix, segment->file_bytes, &copy_bytes) != 0
                || !tg_range_within(
                    file_page, copy_bytes, snapshot->length)) {
                return -1;
            }
            memcpy(
                mapped,
                snapshot->bytes + (size_t)file_page,
                (size_t)copy_bytes);
        }
        if ((segment->flags & PF_R) != 0) {
            protection |= PROT_READ;
        }
        if ((segment->flags & PF_W) != 0) {
            protection |= PROT_WRITE;
        }
        if ((segment->flags & PF_X) != 0) {
            protection |= PROT_EXEC;
        }
        if (mprotect(mapped, map_bytes, protection) != 0
            || madvise(mapped, map_bytes, MADV_DONTDUMP) != 0) {
            return -1;
        }
    }
    return 0;
}

static void tg_unmap_elf(tg_loaded_elf *loaded)
{
    size_t index;

    for (index = 0; index < loaded->segment_count; ++index) {
        if (loaded->segments[index].mapped_address != NULL) {
            (void)munmap(
                loaded->segments[index].mapped_address,
                loaded->segments[index].mapped_bytes);
        }
    }
    memset(loaded, 0, sizeof(*loaded));
}

static int tg_install_exit_only_seccomp(void)
{
    struct sock_filter filter[] = {
        BPF_STMT(
            BPF_LD | BPF_W | BPF_ABS,
            (uint32_t)offsetof(struct seccomp_data, arch)),
        BPF_JUMP(
            BPF_JMP | BPF_JEQ | BPF_K,
            AUDIT_ARCH_X86_64,
            1,
            0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(
            BPF_LD | BPF_W | BPF_ABS,
            (uint32_t)offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_exit, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_exit_group, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_rt_sigreturn, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS)
    };
    struct sock_fprog program;

    program.len = (unsigned short)(sizeof(filter) / sizeof(filter[0]));
    program.filter = filter;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) != 0
        || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        return -1;
    }
    return 0;
}

static int tg_prepare_child_signals(void)
{
    struct sigaction disposition;
    sigset_t blocked;
    int signal_number;

    memset(&disposition, 0, sizeof(disposition));
    disposition.sa_handler = SIG_DFL;
    if (sigemptyset(&disposition.sa_mask) != 0
        || sigfillset(&blocked) != 0) {
        return -1;
    }
    for (signal_number = 1; signal_number < NSIG; ++signal_number) {
        if (signal_number != SIGKILL
            && signal_number != SIGSTOP
            && sigaction(signal_number, &disposition, NULL) != 0
            && errno != EINVAL) {
            return -1;
        }
    }
    /*
     * Asynchronous signals remain blocked across the stack switch.  Fatal
     * synchronous faults retain their default disposition and therefore make
     * waitpid reject the child.  SIGKILL remains available to the timeout
     * observer.
     */
    return sigprocmask(SIG_SETMASK, &blocked, NULL);
}

static int tg_wait_for_child(pid_t child, uint32_t timeout_seconds)
{
    struct pollfd descriptor;
    struct timespec start;
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0U);
    int poll_status;
    int wait_status;

    if (pidfd < 0 || clock_gettime(CLOCK_MONOTONIC, &start) != 0) {
        if (pidfd >= 0) {
            (void)close(pidfd);
        }
        (void)kill(child, SIGKILL);
        while (waitpid(child, &wait_status, 0) < 0 && errno == EINTR) {
        }
        return -1;
    }
    descriptor.fd = pidfd;
    descriptor.events = POLLIN;
    descriptor.revents = 0;
    for (;;) {
        struct timespec now;
        uint64_t elapsed_ms;
        uint64_t timeout_ms = (uint64_t)timeout_seconds * UINT64_C(1000);
        uint64_t remaining;
        int chunk;

        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
            poll_status = -1;
            break;
        }
        elapsed_ms = (uint64_t)(now.tv_sec - start.tv_sec) * UINT64_C(1000);
        if (now.tv_nsec >= start.tv_nsec) {
            elapsed_ms +=
                (uint64_t)(now.tv_nsec - start.tv_nsec) / UINT64_C(1000000);
        } else if (elapsed_ms >= UINT64_C(1000)) {
            elapsed_ms -= UINT64_C(1000);
            elapsed_ms +=
                (uint64_t)(
                    UINT64_C(1000000000)
                    + (uint64_t)now.tv_nsec
                    - (uint64_t)start.tv_nsec)
                / UINT64_C(1000000);
        }
        if (elapsed_ms >= timeout_ms) {
            poll_status = 0;
            break;
        }
        remaining = timeout_ms - elapsed_ms;
        chunk = remaining > (uint64_t)INT_MAX
            ? INT_MAX
            : (int)remaining;
        poll_status = poll(&descriptor, 1U, chunk);
        if (poll_status > 0) {
            break;
        }
        if (poll_status < 0 && errno == EINTR) {
            continue;
        }
        if (poll_status == 0) {
            continue;
        }
        break;
    }
    (void)close(pidfd);
    if (poll_status <= 0) {
        (void)kill(child, SIGKILL);
    }
    while (waitpid(child, &wait_status, 0) < 0) {
        if (errno != EINTR) {
            return -1;
        }
    }
    return poll_status > 0
        && WIFEXITED(wait_status)
        && WEXITSTATUS(wait_status) == 0
        ? 0
        : -1;
}

static int tg_run_child(
    const tg_loaded_elf *loaded,
    const tg_guarded_region *input,
    tg_guarded_region *result,
    tg_guarded_region *status,
    tg_guarded_region *observation,
    const tg_stack_region *stack,
    uint32_t timeout_seconds)
{
    pid_t child = fork();

    if (child < 0) {
        return -1;
    }
    if (child == 0) {
        int returned;

        if (tg_prepare_child_signals() != 0
            || tg_install_exit_only_seccomp() != 0) {
            _exit(111);
        }
        returned = tg_sq218_call_pure_entry(
            (const void *)(uintptr_t)loaded->entry,
            input->logical,
            (uint64_t)input->logical_bytes,
            result->logical,
            (uint32_t *)(void *)status->logical,
            stack->usable + stack->usable_bytes,
            (tg_sq218_launch_observation *)(void *)observation->logical);
        (void)returned;
        _exit(0);
    }
    return tg_wait_for_child(child, timeout_seconds);
}

static int tg_validate_result_record(
    const uint8_t result[TG_RESULT_BYTES],
    uint64_t input_size,
    const uint8_t input_digest[32])
{
    return memcmp(result, tg_result_magic, sizeof(tg_result_magic)) == 0
        && tg_load_be16(result + 8U) == UINT16_C(1)
        && tg_load_be16(result + 10U) == UINT16_C(120)
        && tg_load_be32(result + 12U) == UINT32_C(0)
        && tg_load_be64(result + 16U) == input_size
        && tg_constant_time_equal(result + 88U, input_digest, 32U);
}

static int tg_observation_accepted(
    const tg_sq218_launch_observation *observation,
    const tg_guarded_region *input,
    const tg_guarded_region *result,
    const tg_guarded_region *status,
    const uint8_t expected_input_digest[32],
    uint8_t post_input_digest[32])
{
    uint64_t expected_sentinel =
        (uint64_t)(uintptr_t)&tg_sq218_return_sentinel[0];

    tg_sq218_sha256(
        input->logical,
        input->logical_bytes,
        post_input_digest);
    return observation->launcher_entry_attempt_count == UINT64_C(1)
        && observation->returned_to_sentinel == UINT64_C(1)
        && observation->eax_return == 1
        && observation->reserved == 0
        && observation->return_sentinel == expected_sentinel
        && observation->entry_rsp_mod_16 == UINT64_C(8)
        && (observation->post_return_rflags & TG_RFLAGS_DF) == 0
        && tg_all_bytes_equal(
            input->usable, input->prefix_bytes, TG_CANARY)
        && tg_all_bytes_equal(
            result->usable, result->prefix_bytes, TG_CANARY)
        && tg_all_bytes_equal(
            status->usable, status->prefix_bytes, TG_CANARY)
        && tg_all_bytes_equal(status->logical, TG_STATUS_BYTES, 0)
        && tg_constant_time_equal(
            post_input_digest, expected_input_digest, 32U)
        && tg_validate_result_record(
            result->logical,
            (uint64_t)input->logical_bytes,
            expected_input_digest);
}

static int tg_text_append(
    tg_text_builder *builder,
    const char *text,
    size_t length)
{
    if (length > sizeof(builder->bytes) - builder->used) {
        return -1;
    }
    memcpy(builder->bytes + builder->used, text, length);
    builder->used += length;
    return 0;
}

static int tg_text_literal(tg_text_builder *builder, const char *text)
{
    return tg_text_append(builder, text, strlen(text));
}

static int tg_text_hex(
    tg_text_builder *builder,
    const uint8_t *bytes,
    size_t length)
{
    static const char alphabet[] = "0123456789abcdef";
    size_t index;

    if (length > (sizeof(builder->bytes) - builder->used) / 2U) {
        return -1;
    }
    for (index = 0; index < length; ++index) {
        builder->bytes[builder->used++] = alphabet[bytes[index] >> 4];
        builder->bytes[builder->used++] =
            alphabet[bytes[index] & UINT8_C(0x0f)];
    }
    return 0;
}

static int tg_text_hex_u64(tg_text_builder *builder, uint64_t value)
{
    static const char alphabet[] = "0123456789abcdef";
    unsigned int index;

    if (sizeof(builder->bytes) - builder->used < 16U) {
        return -1;
    }
    for (index = 0; index < 16U; ++index) {
        unsigned int shift = 60U - (4U * index);
        builder->bytes[builder->used++] =
            alphabet[(value >> shift) & UINT64_C(0x0f)];
    }
    return 0;
}

static int tg_text_decimal(tg_text_builder *builder, uint64_t value)
{
    char reversed[32];
    size_t digits = 0;

    do {
        reversed[digits++] = (char)('0' + (value % UINT64_C(10)));
        value /= UINT64_C(10);
    } while (value != 0);
    if (digits > sizeof(builder->bytes) - builder->used) {
        return -1;
    }
    while (digits != 0) {
        builder->bytes[builder->used++] = reversed[--digits];
    }
    return 0;
}

static int tg_build_transcript(
    const tg_control *control,
    const uint8_t control_digest[32],
    const uint8_t result_digest[32],
    const tg_loaded_elf *loaded,
    const tg_sq218_launch_observation *observation,
    tg_text_builder *builder)
{
#define TG_LIT(value) \
    do { \
        if (tg_text_literal(builder, value) != 0) { \
            return -1; \
        } \
    } while (0)
#define TG_HEX(value) \
    do { \
        if (tg_text_hex(builder, value, 32U) != 0) { \
            return -1; \
        } \
    } while (0)
#define TG_DEC(value) \
    do { \
        if (tg_text_decimal(builder, value) != 0) { \
            return -1; \
        } \
    } while (0)

    memset(builder, 0, sizeof(*builder));
    TG_LIT("kind=sparkinterval.sqrt218-pure-entry-launch-transcript.v1\n");
    TG_LIT("authorizes_lean_theorem=false\n");
    TG_LIT("architecture_execution_proved=false\n");
    TG_LIT("backend=azure_sevsnp_cpu\n");
    TG_LIT("control_sha256=");
    TG_HEX(control_digest);
    TG_LIT("\nchallenge_nonce=");
    TG_HEX(control->challenge);
    TG_LIT("\njob_binding_sha256=");
    TG_HEX(control->job_binding);
    TG_LIT("\nlauncher_sha256=");
    TG_HEX(control->launcher_sha256);
    TG_LIT("\nlauncher_size_bytes=");
    TG_DEC(control->launcher_size);
    TG_LIT("\npure_entry_elf_sha256=");
    TG_HEX(control->elf_sha256);
    TG_LIT("\npure_entry_elf_size_bytes=");
    TG_DEC(control->elf_size);
    TG_LIT("\nentry_symbol=tg_sq218_verify_snapshot_v2\n");
    TG_LIT("entry_virtual_address=");
    if (tg_text_hex_u64(builder, loaded->entry) != 0) {
        return -1;
    }
    TG_LIT("\nentry_symbol_size_bytes=");
    TG_DEC(loaded->entry_symbol_size);
    TG_LIT("\ninput_sha256=");
    TG_HEX(control->input_sha256);
    TG_LIT("\ninput_size_bytes=");
    TG_DEC(control->input_size);
    TG_LIT("\nstack_size_bytes=");
    TG_DEC(TG_STACK_BYTES);
    TG_LIT("\nreturn_sentinel_virtual_address=");
    if (tg_text_hex_u64(builder, observation->return_sentinel) != 0) {
        return -1;
    }
    TG_LIT("\nlauncher_entry_attempt_count=1\n");
    TG_LIT("returned_to_sentinel=true\n");
    TG_LIT("entry_rsp_mod_16=8\n");
    TG_LIT("direction_flag_clear=true\n");
    TG_LIT("eax_int32=1\n");
    TG_LIT("status_le_u32=0\n");
    TG_LIT("input_unchanged=true\n");
    TG_LIT("result_name=result.bin\n");
    TG_LIT("result_size_bytes=120\n");
    TG_LIT("result_sha256=");
    TG_HEX(result_digest);
    TG_LIT("\npublication=atomic-directory-rename-noreplace\n");
    TG_LIT("production_execution_performed=true\n");
    TG_LIT("formal_launcher_refinement_present=false\n");

#undef TG_DEC
#undef TG_HEX
#undef TG_LIT
    return 0;
}

static int tg_leaf_name_valid(const char *leaf)
{
    size_t index;
    size_t length;

    if (leaf == NULL) {
        return 0;
    }
    length = strlen(leaf);
    if (length == 0 || length > 128U
        || strcmp(leaf, ".") == 0 || strcmp(leaf, "..") == 0) {
        return 0;
    }
    for (index = 0; index < length; ++index) {
        char character = leaf[index];
        if (!((character >= 'a' && character <= 'z')
              || (character >= 'A' && character <= 'Z')
              || (character >= '0' && character <= '9')
              || character == '.' || character == '_'
              || character == '-')) {
            return 0;
        }
    }
    return leaf[0] != '.';
}

static int tg_write_all(int descriptor, const uint8_t *bytes, size_t length)
{
    size_t written = 0;

    while (written < length) {
        ssize_t count = write(descriptor, bytes + written, length - written);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return -1;
        }
        written += (size_t)count;
    }
    return 0;
}

static int tg_write_staging_file(
    int directory,
    const char *name,
    const uint8_t *bytes,
    size_t length)
{
    int descriptor = openat(
        directory,
        name,
        O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
        S_IRUSR);

    if (descriptor < 0
        || tg_write_all(descriptor, bytes, length) != 0
        || fsync(descriptor) != 0
        || close(descriptor) != 0) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        (void)unlinkat(directory, name, 0);
        return -1;
    }
    return 0;
}

static int tg_publish_output(
    const char *parent_path,
    const char *leaf,
    const uint8_t result[TG_RESULT_BYTES],
    const tg_text_builder *transcript)
{
    uint8_t random_bytes[16];
    char temporary[64];
    static const char alphabet[] = "0123456789abcdef";
    int parent = -1;
    int staging = -1;
    size_t index;
    int renamed = 0;

    if (!tg_leaf_name_valid(leaf)
        || getrandom(random_bytes, sizeof(random_bytes), 0U)
            != (ssize_t)sizeof(random_bytes)) {
        return -1;
    }
    memcpy(temporary, ".sq218-launch-", 14U);
    for (index = 0; index < sizeof(random_bytes); ++index) {
        temporary[14U + (2U * index)] = alphabet[random_bytes[index] >> 4];
        temporary[15U + (2U * index)] =
            alphabet[random_bytes[index] & UINT8_C(0x0f)];
    }
    temporary[46] = '\0';
    memset(random_bytes, 0, sizeof(random_bytes));

    parent = tg_open_nosymlink(parent_path, O_RDONLY | O_DIRECTORY);
    if (parent < 0
        || mkdirat(parent, temporary, S_IRWXU) != 0) {
        if (parent >= 0) {
            (void)close(parent);
        }
        return -1;
    }
    staging = openat(
        parent,
        temporary,
        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (staging < 0
        || tg_write_staging_file(
            staging, "result.bin", result, TG_RESULT_BYTES) != 0
        || tg_write_staging_file(
            staging,
            "transcript.txt",
            (const uint8_t *)transcript->bytes,
            transcript->used) != 0
        || fsync(staging) != 0
        || close(staging) != 0) {
        if (staging >= 0) {
            (void)close(staging);
        }
        (void)unlinkat(parent, temporary, AT_REMOVEDIR);
        (void)close(parent);
        return -1;
    }
    staging = -1;
    if (syscall(
            SYS_renameat2,
            parent,
            temporary,
            parent,
            leaf,
            RENAME_NOREPLACE) == 0) {
        renamed = 1;
    }
    if (renamed == 0 || fsync(parent) != 0 || close(parent) != 0) {
        if (renamed == 0) {
            int cleanup = openat(
                parent,
                temporary,
                O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
            if (cleanup >= 0) {
                (void)unlinkat(cleanup, "result.bin", 0);
                (void)unlinkat(cleanup, "transcript.txt", 0);
                (void)close(cleanup);
            }
            (void)unlinkat(parent, temporary, AT_REMOVEDIR);
        }
        (void)close(parent);
        return -1;
    }
    return 0;
}

static int tg_fail(const char *message)
{
    (void)fprintf(stderr, "sqrt218 launcher: %s\n", message);
    return 2;
}

int main(int argument_count, char **arguments)
{
    tg_control control;
    uint8_t control_digest[32];
    tg_file_snapshot elf_snapshot;
    tg_loaded_elf loaded;
    tg_guarded_region input;
    tg_guarded_region result;
    tg_guarded_region status;
    tg_guarded_region observation;
    tg_stack_region stack;
    uint8_t input_digest[32];
    uint8_t post_input_digest[32];
    uint8_t result_digest[32];
    tg_text_builder transcript;
    tg_sq218_launch_observation *observed;
    int exit_status = 2;

    memset(&control, 0, sizeof(control));
    memset(&elf_snapshot, 0, sizeof(elf_snapshot));
    memset(&loaded, 0, sizeof(loaded));
    memset(&input, 0, sizeof(input));
    memset(&result, 0, sizeof(result));
    memset(&status, 0, sizeof(status));
    memset(&observation, 0, sizeof(observation));
    memset(&stack, 0, sizeof(stack));
    memset(&transcript, 0, sizeof(transcript));

    if (argument_count != 6) {
        return tg_fail(
            "usage: LAUNCHER CONTROL PURE_ENTRY_ELF INPUT OUTPUT_PARENT "
            "OUTPUT_LEAF");
    }
    if (tg_read_control(arguments[1], &control, control_digest) != 0) {
        return tg_fail("invalid challenge/job-bound control file");
    }
    if (tg_require_measured_worker(&control) != 0) {
        return tg_fail("measured Azure worker binding is absent or mismatched");
    }
    if (tg_hash_open_file(
            "/proc/self/exe",
            control.launcher_size,
            control.launcher_sha256,
            1) != 0) {
        return tg_fail("running launcher does not match its exact control pin");
    }
    if (tg_read_file_snapshot(
            arguments[2],
            control.elf_size,
            control.elf_sha256,
            &elf_snapshot) != 0) {
        return tg_fail("pure-entry ELF snapshot does not match its exact pin");
    }
    if (tg_validate_elf(&elf_snapshot, &loaded) != 0) {
        goto cleanup;
    }
    if (tg_map_elf(&elf_snapshot, &loaded) != 0) {
        goto cleanup;
    }
    tg_free_file_snapshot(&elf_snapshot);

    if (tg_read_input_region(
            arguments[3],
            control.input_size,
            control.input_sha256,
            &input,
            input_digest) != 0
        || tg_guarded_region_create(TG_RESULT_BYTES, 1, &result) != 0
        || tg_guarded_region_create(TG_STATUS_BYTES, 1, &status) != 0
        || tg_guarded_region_create(
            TG_OBSERVATION_BYTES, 1, &observation) != 0
        || tg_stack_create(&stack) != 0) {
        goto cleanup;
    }
    memset(result.logical, 0, result.logical_bytes);
    memset(status.logical, 0, status.logical_bytes);
    memset(observation.logical, 0, observation.logical_bytes);

    if (tg_run_child(
            &loaded,
            &input,
            &result,
            &status,
            &observation,
            &stack,
            control.timeout_seconds) != 0) {
        goto cleanup;
    }
    observed =
        (tg_sq218_launch_observation *)(void *)observation.logical;
    if (!tg_observation_accepted(
            observed,
            &input,
            &result,
            &status,
            control.input_sha256,
            post_input_digest)) {
        goto cleanup;
    }
    tg_sq218_sha256(result.logical, result.logical_bytes, result_digest);
    if (tg_build_transcript(
            &control,
            control_digest,
            result_digest,
            &loaded,
            observed,
            &transcript) != 0
        || tg_publish_output(
            arguments[4],
            arguments[5],
            result.logical,
            &transcript) != 0) {
        goto cleanup;
    }
    exit_status = 0;

cleanup:
    tg_stack_destroy(&stack);
    tg_guarded_region_destroy(&observation);
    tg_guarded_region_destroy(&status);
    tg_guarded_region_destroy(&result);
    tg_guarded_region_destroy(&input);
    tg_unmap_elf(&loaded);
    tg_free_file_snapshot(&elf_snapshot);
    memset(&control, 0, sizeof(control));
    memset(control_digest, 0, sizeof(control_digest));
    memset(input_digest, 0, sizeof(input_digest));
    memset(post_input_digest, 0, sizeof(post_input_digest));
    memset(result_digest, 0, sizeof(result_digest));
    memset(&transcript, 0, sizeof(transcript));
    if (exit_status != 0) {
        return tg_fail("launch rejected before atomic output publication");
    }
    return 0;
}

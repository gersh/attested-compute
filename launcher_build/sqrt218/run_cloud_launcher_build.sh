#!/usr/bin/env bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

# Cloud-only build and inspection lane for the non-authorizing Sqrt218
# pure-entry launcher prototype.  This script never opens a production input
# and never executes either the launcher or the pure-entry ELF.

set -euo pipefail
IFS=$'\n\t'
umask 077

readonly REPOSITORY_ROOT="${TG_REPOSITORY_ROOT:-/workspace/repository}"
readonly OUTPUT_ROOT="${TG_OUTPUT_ROOT:-/workspace/output}"
readonly LANE_MANIFEST="${TG_LANE_MANIFEST:-${REPOSITORY_ROOT}/launcher_build/sqrt218/cloud-launcher-build.v1.json}"
readonly LANE_TOOL="/opt/sparkinterval/tools/tg_sqrt218_launcher_build.py"
readonly FINAL_IMAGE_REFERENCE="${TG_FINAL_IMAGE_REFERENCE:-}"
readonly SOURCE_ROOT="${REPOSITORY_ROOT}/launcher_build/sqrt218"
readonly COMMAND_ROOT="${OUTPUT_ROOT}/commands"
readonly RETAINED_ROOT="${OUTPUT_ROOT}/retained"
readonly BUILD_ROOT="${OUTPUT_ROOT}/work"

fail() {
    echo "sqrt218 launcher build: $*" >&2
    exit 2
}

[[ "${TG_CLOUD_LAUNCHER_BUILD:-}" == "1" ]] ||
    fail "TG_CLOUD_LAUNCHER_BUILD=1 is required"
[[ "${FINAL_IMAGE_REFERENCE}" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]] ||
    fail "TG_FINAL_IMAGE_REFERENCE must pin the final image by SHA-256 digest"
[[ -d "${REPOSITORY_ROOT}" && ! -L "${REPOSITORY_ROOT}" ]] ||
    fail "repository root must be a non-symlink directory"
[[ ! -e "${OUTPUT_ROOT}" ]] ||
    fail "output root must not already exist"

python3 "${LANE_TOOL}" validate "${LANE_MANIFEST}" \
    --repository-root "${REPOSITORY_ROOT}" \
    --require-build-ready

mkdir -p "${COMMAND_ROOT}" "${RETAINED_ROOT}" "${BUILD_ROOT}"

run_step() {
    local step="$1"
    local cwd="$2"
    shift 2
    local argv_path="${COMMAND_ROOT}/${step}.argv0"
    local stdout_path="${COMMAND_ROOT}/${step}.stdout"
    local stderr_path="${COMMAND_ROOT}/${step}.stderr"
    local exit_path="${COMMAND_ROOT}/${step}.exit-code"
    local status

    [[ "${step}" =~ ^[a-z][a-z0-9_]*$ ]] ||
        fail "invalid step name: ${step}"
    [[ -d "${cwd}" && ! -L "${cwd}" ]] ||
        fail "invalid step working directory: ${cwd}"
    [[ ! -e "${argv_path}" && ! -e "${stdout_path}" &&
       ! -e "${stderr_path}" && ! -e "${exit_path}" ]] ||
        fail "refusing to overwrite evidence for step ${step}"

    printf '%s\0' "$@" >"${argv_path}"
    set +e
    (
        cd "${cwd}"
        "$@"
    ) >"${stdout_path}" 2>"${stderr_path}"
    status=$?
    set -e
    [[ -s "${stdout_path}" ]] ||
        printf '%s\n' "sparkinterval-empty-command-stdout-v1" >"${stdout_path}"
    [[ -s "${stderr_path}" ]] ||
        printf '%s\n' "sparkinterval-empty-command-stderr-v1" >"${stderr_path}"
    printf '%s\n' "${status}" >"${exit_path}"
    [[ "${status}" -eq 0 ]] ||
        fail "step ${step} failed with exit code ${status}"
}

require_file() {
    local path="$1"
    [[ -f "${path}" && ! -L "${path}" && -s "${path}" ]] ||
        fail "required output is missing, empty, or a symlink: ${path}"
}

run_step source_closure "${REPOSITORY_ROOT}" \
    python3 "${LANE_TOOL}" source-closure "${LANE_MANIFEST}" \
        --repository-root "${REPOSITORY_ROOT}" \
        --output "${RETAINED_ROOT}/source-closure.json"

run_step gcc_version "${BUILD_ROOT}" gcc --version
run_step gcc_target "${BUILD_ROOT}" gcc -dumpmachine
run_step gcc_specs "${BUILD_ROOT}" gcc -dumpspecs
run_step assembler_version "${BUILD_ROOT}" as --version
run_step linker_version "${BUILD_ROOT}" ld --version
run_step libc_path "${BUILD_ROOT}" gcc -print-file-name=libc.a

readonly GCC_PATH="$(readlink -f "$(command -v gcc)")"
readonly AS_PATH="$(readlink -f "$(command -v as)")"
readonly LD_PATH="$(readlink -f "$(command -v ld)")"
readonly LIBC_PATH="$(readlink -f "$(head -n 1 "${COMMAND_ROOT}/libc_path.stdout")")"
[[ "${GCC_PATH}" = /* && -f "${GCC_PATH}" && ! -L "${GCC_PATH}" ]] ||
    fail "gcc must resolve to a regular non-symlink executable"
[[ "${AS_PATH}" = /* && -f "${AS_PATH}" && ! -L "${AS_PATH}" ]] ||
    fail "as must resolve to a regular non-symlink executable"
[[ "${LD_PATH}" = /* && -f "${LD_PATH}" && ! -L "${LD_PATH}" ]] ||
    fail "ld must resolve to a regular non-symlink executable"
[[ "${LIBC_PATH}" = /* && -f "${LIBC_PATH}" && ! -L "${LIBC_PATH}" ]] ||
    fail "gcc did not resolve a static libc archive"
[[ "$(cat "${COMMAND_ROOT}/gcc_target.stdout")" == x86_64-* ]] ||
    fail "compiler target is not x86_64"

run_step compiler_sha256 "${BUILD_ROOT}" sha256sum "${GCC_PATH}"
run_step assembler_sha256 "${BUILD_ROOT}" sha256sum "${AS_PATH}"
run_step linker_sha256 "${BUILD_ROOT}" sha256sum "${LD_PATH}"
run_step libc_sha256 "${BUILD_ROOT}" sha256sum "${LIBC_PATH}"

readonly LAUNCHER="${RETAINED_ROOT}/sqrt218_pure_entry_launcher"
readonly LINK_MAP="${RETAINED_ROOT}/sqrt218-launcher.map"
run_step compile "${BUILD_ROOT}" \
    gcc \
        -std=c11 \
        -O2 \
        -Wall \
        -Wextra \
        -Wconversion \
        -Werror \
        -pedantic \
        -fPIE \
        -fno-omit-frame-pointer \
        -fno-stack-protector \
        -fno-strict-aliasing \
        -static-pie \
        -Wl,-z,relro \
        -Wl,-z,now \
        -Wl,-z,noexecstack \
        -Wl,-z,separate-code \
        -Wl,--build-id=none \
        -Wl,-Map="${LINK_MAP}" \
        -I"${SOURCE_ROOT}" \
        "${SOURCE_ROOT}/sqrt218_pure_entry_launcher.c" \
        "${SOURCE_ROOT}/sqrt218_launcher_sha256.c" \
        "${SOURCE_ROOT}/sqrt218_pure_entry_trampoline.S" \
        -o "${LAUNCHER}"
require_file "${LAUNCHER}"
require_file "${LINK_MAP}"

run_step elf_header "${BUILD_ROOT}" readelf -hW "${LAUNCHER}"
run_step elf_program_headers "${BUILD_ROOT}" readelf -lW "${LAUNCHER}"
run_step elf_section_headers "${BUILD_ROOT}" readelf -SW "${LAUNCHER}"
run_step elf_symbols "${BUILD_ROOT}" readelf -sW "${LAUNCHER}"
run_step elf_dynamic "${BUILD_ROOT}" readelf -dW "${LAUNCHER}"
run_step elf_relocations "${BUILD_ROOT}" readelf -rW "${LAUNCHER}"
run_step symbol_table "${BUILD_ROOT}" nm -an "${LAUNCHER}"
run_step disassembly "${BUILD_ROOT}" objdump -drwC "${LAUNCHER}"

grep -Eq 'Class:[[:space:]]+ELF64' "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "launcher is not ELF64"
grep -Eq 'Data:[[:space:]]+2.s complement, little endian' \
    "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "launcher is not little endian"
grep -Eq 'Machine:[[:space:]]+Advanced Micro Devices X86-64' \
    "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "launcher is not EM_X86_64"
grep -Eq 'Type:[[:space:]]+DYN ' "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "launcher is not static PIE ET_DYN"
if grep -Eq '(^|[[:space:]])INTERP([[:space:]]|$)' \
        "${COMMAND_ROOT}/elf_program_headers.stdout"; then
    fail "launcher unexpectedly contains PT_INTERP"
fi
if grep -Eq '\(NEEDED\)' "${COMMAND_ROOT}/elf_dynamic.stdout"; then
    fail "launcher unexpectedly contains a shared-library dependency"
fi
if grep -E '^[[:space:]]*LOAD[[:space:]]' \
        "${COMMAND_ROOT}/elf_program_headers.stdout" |
        grep -Eq 'W.*E|E.*W'; then
    fail "launcher contains a writable-executable PT_LOAD"
fi
grep -Eq 'GNU_STACK' "${COMMAND_ROOT}/elf_program_headers.stdout" ||
    fail "launcher has no explicit GNU_STACK policy"
if grep -E 'GNU_STACK' "${COMMAND_ROOT}/elf_program_headers.stdout" |
        grep -Eq 'E'; then
    fail "launcher stack is executable"
fi
[[ "$(grep -Ec \
    '[[:space:]]tg_sq218_call_pure_entry$' \
    "${COMMAND_ROOT}/symbol_table.stdout")" -eq 1 ]] ||
    fail "launcher does not contain exactly one trampoline symbol"
[[ "$(grep -Ec \
    '[[:space:]]tg_sq218_return_sentinel$' \
    "${COMMAND_ROOT}/symbol_table.stdout")" -eq 1 ]] ||
    fail "launcher does not contain exactly one return-sentinel symbol"

run_step artifact_index "${OUTPUT_ROOT}" \
    python3 "${LANE_TOOL}" artifact-index "${LANE_MANIFEST}" \
        --output-root "${OUTPUT_ROOT}" \
        --final-image-reference "${FINAL_IMAGE_REFERENCE}" \
        --output "${RETAINED_ROOT}/artifact-index.json"

echo "Sqrt218 launcher built and inspected without executing it or opening production input."

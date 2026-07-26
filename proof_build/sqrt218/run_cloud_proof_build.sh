#!/usr/bin/env bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

# Cloud-only Sqrt218 Clight/VST/CompCert proof build.
#
# The repository lane manifest is validated before any tool runs.  In
# particular, the checked-in lane currently fails closed until the two
# substantive VST proof files and their hashes are supplied.  This script
# never runs or opens a production Sqrt218 certificate.

set -euo pipefail
IFS=$'\n\t'
umask 077

readonly REPOSITORY_ROOT="${TG_REPOSITORY_ROOT:-/workspace/repository}"
readonly PROOF_ROOT="${TG_PROOF_ROOT:-/workspace/proof}"
readonly OUTPUT_ROOT="${TG_OUTPUT_ROOT:-/workspace/output}"
readonly LANE_MANIFEST="${TG_LANE_MANIFEST:-${REPOSITORY_ROOT}/proof_build/sqrt218/cloud-proof-build.v1.json}"
readonly LANE_TOOL="/opt/sparkinterval/tools/tg_sqrt218_proof_build.py"
readonly FINAL_IMAGE_REFERENCE="${TG_FINAL_IMAGE_REFERENCE:-}"
readonly JOBS="${TG_PROOF_JOBS:-16}"

readonly BUILD_ROOT="${OUTPUT_ROOT}/work"
readonly GENERATED_ROOT="${BUILD_ROOT}/Generated"
readonly PROJECT_ROOT="${BUILD_ROOT}/project"
readonly COMMAND_ROOT="${OUTPUT_ROOT}/commands"
readonly RETAINED_ROOT="${OUTPUT_ROOT}/retained"

fail() {
    echo "sqrt218 proof build: $*" >&2
    exit 2
}

[[ "${TG_CLOUD_PROOF_BUILD:-}" == "1" ]] ||
    fail "TG_CLOUD_PROOF_BUILD=1 is required"
[[ "${FINAL_IMAGE_REFERENCE}" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]] ||
    fail "TG_FINAL_IMAGE_REFERENCE must pin the final image by SHA-256 digest"
[[ "${JOBS}" =~ ^[1-9][0-9]*$ ]] ||
    fail "TG_PROOF_JOBS must be a positive decimal integer"
[[ -d "${REPOSITORY_ROOT}" && ! -L "${REPOSITORY_ROOT}" ]] ||
    fail "repository root must be a non-symlink directory"
[[ -d "${PROOF_ROOT}" && ! -L "${PROOF_ROOT}" ]] ||
    fail "proof root must be a non-symlink directory"
[[ ! -e "${OUTPUT_ROOT}" ]] ||
    fail "output root must not already exist"

python3 "${LANE_TOOL}" validate "${LANE_MANIFEST}" \
    --repository-root "${REPOSITORY_ROOT}" \
    --proof-root "${PROOF_ROOT}" \
    --require-ready

mkdir -p \
    "${BUILD_ROOT}" \
    "${GENERATED_ROOT}" \
    "${PROJECT_ROOT}" \
    "${COMMAND_ROOT}" \
    "${RETAINED_ROOT}"

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
        fail "step working directory is invalid: ${cwd}"
    [[ ! -e "${argv_path}" && ! -e "${stdout_path}" &&
       ! -e "${stderr_path}" && ! -e "${exit_path}" ]] ||
        fail "refusing to overwrite command evidence for ${step}"

    printf '%s\0' "$@" >"${argv_path}"
    set +e
    (
        cd "${cwd}"
        "$@"
    ) >"${stdout_path}" 2>"${stderr_path}"
    status=$?
    set -e
    if [[ ! -s "${stdout_path}" ]]; then
        printf '%s\n' \
            "sparkinterval-empty-command-stdout-v1" >"${stdout_path}"
    fi
    if [[ ! -s "${stderr_path}" ]]; then
        printf '%s\n' \
            "sparkinterval-empty-command-stderr-v1" >"${stderr_path}"
    fi
    printf '%s\n' "${status}" >"${exit_path}"
    [[ "${status}" -eq 0 ]] ||
        fail "step ${step} failed with exit code ${status}"
}

require_output() {
    local path="$1"
    [[ -f "${path}" && ! -L "${path}" && -s "${path}" ]] ||
        fail "required retained output is missing, empty, or a symlink: ${path}"
}

run_step source_closure "${REPOSITORY_ROOT}" \
    python3 "${LANE_TOOL}" source-closure "${LANE_MANIFEST}" \
        --repository-root "${REPOSITORY_ROOT}" \
        --proof-root "${PROOF_ROOT}" \
        --output "${RETAINED_ROOT}/source-closure.json"

readonly PURE_UNIT="${REPOSITORY_ROOT}/proof_build/sqrt218/sqrt218_pure_entry_unit.c"
readonly PREPROCESSED="${BUILD_ROOT}/sqrt218_pure_entry.i"
readonly CSYNTAX_AST="${GENERATED_ROOT}/Sqrt218CompCertC.v"
readonly CLIGHT_AST="${GENERATED_ROOT}/Sqrt218Clight.v"

run_step preprocess "${BUILD_ROOT}" \
    ccomp \
        -E \
        -std=c11 \
        -fnone \
        -Wall \
        -Werror \
        -DTG_SQ218_PURE_ENTRY_ONLY=1 \
        -I"${REPOSITORY_ROOT}/cpu_checker/sqrt218" \
        -o "${PREPROCESSED}" \
        "${PURE_UNIT}"
require_output "${PREPROCESSED}"

run_step csyntaxgen "${BUILD_ROOT}" \
    clightgen \
        -csyntax \
        -canonical-idents \
        -fnone \
        -Wall \
        -Werror \
        -o "${CSYNTAX_AST}" \
        "${PREPROCESSED}"
require_output "${CSYNTAX_AST}"

run_step clightgen "${BUILD_ROOT}" \
    clightgen \
        -clight \
        -normalize \
        -canonical-idents \
        -fnone \
        -Wall \
        -Werror \
        -dc \
        -dclight \
        -o "${CLIGHT_AST}" \
        "${PREPROCESSED}"
require_output "${CLIGHT_AST}"
require_output "${BUILD_ROOT}/sqrt218_pure_entry.compcert.c"
require_output "${BUILD_ROOT}/sqrt218_pure_entry.light.c"

install -m 0444 "${CLIGHT_AST}" "${PROJECT_ROOT}/Sqrt218Clight.v"
install -m 0444 "${PROOF_ROOT}/Sqrt218Spec.v" \
    "${PROJECT_ROOT}/Sqrt218Spec.v"
install -m 0444 "${PROOF_ROOT}/Sqrt218Proof.v" \
    "${PROJECT_ROOT}/Sqrt218Proof.v"
install -m 0444 \
    "${REPOSITORY_ROOT}/proof_build/sqrt218/Sqrt218AssumptionAudit.v" \
    "${PROJECT_ROOT}/Sqrt218AssumptionAudit.v"

{
    printf '%s\n' "-Q ${TG_VST_ROOT} VST"
    printf '%s\n' "-R ${TG_COMPCERT_ROOT}/lib/rocq/user-contrib/compcert compcert"
    printf '%s\n' "-Q . Sqrt218"
    printf '%s\n' "Sqrt218Clight.v"
    printf '%s\n' "Sqrt218Spec.v"
    printf '%s\n' "Sqrt218Proof.v"
    printf '%s\n' "Sqrt218AssumptionAudit.v"
} >"${PROJECT_ROOT}/_CoqProject"

run_step rocq_makefile "${PROJECT_ROOT}" \
    rocq makefile -f _CoqProject -o Makefile.rocq
run_step vst_proof "${PROJECT_ROOT}" \
    make -f Makefile.rocq -j"${JOBS}" all
require_output "${PROJECT_ROOT}/Sqrt218Proof.vo"

run_step rocqchk "${PROJECT_ROOT}" \
    rocq check \
        -o \
        -Q "${TG_VST_ROOT}" VST \
        -R "${TG_COMPCERT_ROOT}/lib/rocq/user-contrib/compcert" compcert \
        -Q . Sqrt218 \
        Sqrt218.Sqrt218Proof

run_step assumption_audit "${PROJECT_ROOT}" \
    rocq compile \
        -Q "${TG_VST_ROOT}" VST \
        -R "${TG_COMPCERT_ROOT}/lib/rocq/user-contrib/compcert" compcert \
        -Q . Sqrt218 \
        Sqrt218AssumptionAudit.v

run_step proof_bundle "${PROJECT_ROOT}" \
    tar \
        --sort=name \
        --mtime=@0 \
        --owner=0 \
        --group=0 \
        --numeric-owner \
        -cf "${RETAINED_ROOT}/vst-proof-bundle.tar" \
        _CoqProject \
        Sqrt218Clight.v \
        Sqrt218Spec.v \
        Sqrt218Proof.v \
        Sqrt218Proof.vo \
        Sqrt218AssumptionAudit.v

readonly ASSEMBLY="${BUILD_ROOT}/sqrt218_pure_entry.s"
run_step compcert "${BUILD_ROOT}" \
    ccomp \
        -S \
        -sdump \
        -dc \
        -dclight \
        -std=c11 \
        -fnone \
        -Wall \
        -Werror \
        -fno-pie \
        -o "${ASSEMBLY}" \
        "${PREPROCESSED}"
require_output "${ASSEMBLY}"
require_output "${BUILD_ROOT}/sqrt218_pure_entry.sdump"

readonly OBJECT="${BUILD_ROOT}/sqrt218_pure_entry.o"
run_step assembler "${BUILD_ROOT}" \
    as --64 -o "${OBJECT}" "${ASSEMBLY}"
require_output "${OBJECT}"

readonly ELF="${RETAINED_ROOT}/sqrt218_cpu_checker_pure_entry_x86_64_v2"
readonly LINK_MAP="${RETAINED_ROOT}/sqrt218-link.map"
run_step linker "${BUILD_ROOT}" \
    ld \
        -static \
        -no-pie \
        --gc-sections \
        --build-id=none \
        -e tg_sq218_verify_snapshot_v2 \
        -Map="${LINK_MAP}" \
        -o "${ELF}" \
        "${OBJECT}"
require_output "${ELF}"
require_output "${LINK_MAP}"

run_step elf_header "${BUILD_ROOT}" readelf -hW "${ELF}"
run_step elf_program_headers "${BUILD_ROOT}" readelf -lW "${ELF}"
run_step elf_section_headers "${BUILD_ROOT}" readelf -SW "${ELF}"
run_step elf_symbols "${BUILD_ROOT}" readelf -sW "${ELF}"
run_step elf_dependencies "${BUILD_ROOT}" readelf -dW "${ELF}"

grep -Eq 'Class:[[:space:]]+ELF64' "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "ELF is not ELF64"
grep -Eq 'Data:[[:space:]]+2.s complement, little endian' \
    "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "ELF is not little endian"
grep -Eq 'Type:[[:space:]]+EXEC ' "${COMMAND_ROOT}/elf_header.stdout" ||
    fail "ELF is not ET_EXEC"
if grep -Eq '(^|[[:space:]])INTERP([[:space:]]|$)' \
        "${COMMAND_ROOT}/elf_program_headers.stdout"; then
    fail "ELF unexpectedly contains an interpreter"
fi
if grep -Eq '\\(NEEDED\\)' "${COMMAND_ROOT}/elf_dependencies.stdout"; then
    fail "ELF unexpectedly contains a needed shared library"
fi
if grep -E '^[[:space:]]*LOAD[[:space:]]' \
        "${COMMAND_ROOT}/elf_program_headers.stdout" |
        grep -Eq 'W.*E|E.*W'; then
    fail "ELF contains a writable-executable load segment"
fi
if grep -E 'GNU_STACK' "${COMMAND_ROOT}/elf_program_headers.stdout" |
        grep -Eq 'E'; then
    fail "ELF stack is executable"
fi
[[ "$(grep -Ec \
    '[[:space:]]tg_sq218_verify_snapshot_v2$' \
    "${COMMAND_ROOT}/elf_symbols.stdout")" -eq 1 ]] ||
    fail "ELF does not contain exactly one selected entry symbol"

install -m 0444 "${PREPROCESSED}" \
    "${RETAINED_ROOT}/sqrt218_pure_entry.i"
install -m 0444 "${BUILD_ROOT}/sqrt218_pure_entry.compcert.c" \
    "${RETAINED_ROOT}/sqrt218_pure_entry.compcert.c"
install -m 0444 "${CSYNTAX_AST}" \
    "${RETAINED_ROOT}/Sqrt218CompCertC.v"
install -m 0444 "${CLIGHT_AST}" \
    "${RETAINED_ROOT}/Sqrt218Clight.v"
install -m 0444 "${BUILD_ROOT}/sqrt218_pure_entry.sdump" \
    "${RETAINED_ROOT}/sqrt218_pure_entry.sdump"
install -m 0444 "${ASSEMBLY}" \
    "${RETAINED_ROOT}/sqrt218_pure_entry.s"
install -m 0444 "${OBJECT}" \
    "${RETAINED_ROOT}/sqrt218_pure_entry.o"
install -m 0444 "${COMMAND_ROOT}/assumption_audit.stdout" \
    "${RETAINED_ROOT}/vst-assumptions.txt"
install -m 0444 "${COMMAND_ROOT}/rocqchk.stdout" \
    "${RETAINED_ROOT}/rocqchk.stdout"
install -m 0444 "${COMMAND_ROOT}/rocqchk.stderr" \
    "${RETAINED_ROOT}/rocqchk.stderr"
install -m 0444 "${COMPCERT_CONFIG}" \
    "${RETAINED_ROOT}/compcert.ini"

run_step artifact_index "${OUTPUT_ROOT}" \
    python3 "${LANE_TOOL}" artifact-index "${LANE_MANIFEST}" \
        --output-root "${OUTPUT_ROOT}" \
        --final-image-reference "${FINAL_IMAGE_REFERENCE}" \
        --output "${RETAINED_ROOT}/artifact-index.json"

echo "Sqrt218 proof build completed without production certificate replay."

#!/usr/bin/env bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Entry point of the CH25 Lemma A.7 campaign image, run as a dstack
# application inside an Intel TDX confidential VM.
#
# Everything this script needs is supplied by the dstack app-compose document:
# the campaign challenge, the job binding, the application identity, the
# app-compose hash, and the image digest.  Nothing is fetched from the network
# at run time.
#
# The signing key is NOT an input.  It is derived here, in this container,
# from the dstack guest agent, by the same measured code the prelude used
# (`prelude_phala_tdx_inputs.py --derive-key-only`).  That is forced by how
# Docker volumes work: the only volume that can carry a file from the prelude
# container to this one is disk-backed, because a tmpfs-backed *named* volume
# is private to each container -- which is what made the first real run fail.
# Rather than write the key to the CVM's disk, both containers ask dstack for
# it; `--derive-key-only` refuses unless what it gets reproduces the
# report-data commitment the prelude put inside the TDX quote.
#
# This script does not verify the TDX quote.  It requires the quote and the
# `dcap-qvl` appraisal of it to already be present as files, and it commits
# their SHA-256 into the signed statement.  The appraisal itself is performed
# outside, by the operator, with the pinned policy.

set -euo pipefail
IFS=$'\n\t'
umask 077

readonly INPUT_ROOT="${TG_INPUT_ROOT:-/workspace/input}"
readonly OUTPUT_ROOT="${TG_OUTPUT_ROOT:-/workspace/output}"
readonly KEY_ROOT="${TG_ENCLAVE_KEY_ROOT:-/workspace/keys}"
readonly WHEEL="${TG_PYTHON_FLINT_WHEEL:?python-flint wheel path is not set}"
readonly WORKLOAD="/opt/sparkinterval/tools/tg_a7_phala_tdx_workload.py"
readonly ALGORITHM_ID="sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
readonly IMAGE_DIGEST="${TG_FINAL_IMAGE_REFERENCE:-}"
readonly ISSUED_AT="${TG_ISSUED_AT:-}"
# The measured copy of the prelude, which is what derives the key.  In a real
# run the compose document writes it and points this at it, so the key
# derivation is inside the compose hash and inside RTMR3.
readonly KEY_DERIVER="${TG_PHALA_TDX_KEY_DERIVER:?the key-deriver path is not set}"
readonly PRELUDE_SUMMARY="${TG_PRELUDE_SUMMARY:?the prelude summary path is not set}"

fail() {
    echo "ch25-a7-boundary phala-tdx: $*" >&2
    exit 2
}

[[ "${IMAGE_DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]] ||
    fail "TG_FINAL_IMAGE_REFERENCE must pin the final image as sha256:<64 hex>"
[[ "${ISSUED_AT}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] ||
    fail "TG_ISSUED_AT must be an RFC 3339 UTC instant"
[[ "${INPUT_ROOT}" == /workspace/* ]] ||
    fail "input root must live under /workspace"
[[ "${OUTPUT_ROOT}" == /workspace/* ]] ||
    fail "output root must live under /workspace"
[[ "${KEY_ROOT}" == /workspace/* ]] ||
    fail "the derived-key root must live under /workspace"
[[ "${KEY_ROOT}" != "${INPUT_ROOT}" && "${KEY_ROOT}" != "${INPUT_ROOT}"/* ]] ||
    fail "the derived key must not be written into the shared input tree"
[[ -d "${INPUT_ROOT}" && ! -L "${INPUT_ROOT}" ]] ||
    fail "input root must be a non-symlink directory"
[[ -d "${KEY_ROOT}" && ! -L "${KEY_ROOT}" ]] ||
    fail "the derived-key root must be a non-symlink directory"
[[ ! -e "${OUTPUT_ROOT}" ]] ||
    fail "output root must not already exist"

require_input() {
    local path="$1"
    [[ -f "${path}" && ! -L "${path}" && -s "${path}" ]] ||
        fail "required input is missing, empty, or a symlink: ${path}"
}

require_input "${INPUT_ROOT}/registered-input.json"
require_input "${INPUT_ROOT}/a7_boundary.json"
require_input "${INPUT_ROOT}/tdx-quote.bin"
require_input "${INPUT_ROOT}/dcap-qvl-appraisal.json"
require_input "${INPUT_ROOT}/dcap-qvl-policy.json"
require_input "${INPUT_ROOT}/dcap-qvl-artifact.sha256"
require_input "${PRELUDE_SUMMARY}"
require_input "${KEY_DERIVER}"
require_input "${WHEEL}"

# Derive the signing key here rather than reading it from anywhere.  The
# deriver refuses to write it to anything but a tmpfs, and refuses outright
# unless the derived public key and report-data commitment are the ones the
# prelude recorded and the quote attests.
readonly ENCLAVE_KEY="${KEY_ROOT}/enclave-signing-key.hex"
[[ ! -e "${ENCLAVE_KEY}" ]] ||
    fail "a signing key already exists at ${ENCLAVE_KEY}; refusing to reuse it"
python3 "${KEY_DERIVER}" \
    --derive-key-only \
    --key-out "${ENCLAVE_KEY}" \
    --prelude-summary "${PRELUDE_SUMMARY}" ||
    fail "the enclave signing key could not be re-derived in this container"
require_input "${ENCLAVE_KEY}"

mkdir -p "${OUTPUT_ROOT}"

# The workload accepts only safe relative paths, resolved against /workspace.
# Stage the read-only pinned wheel there under its exact pinned filename; its
# SHA-256 is re-verified by the workload against the repository pin.
readonly WHEEL_NAME="$(basename -- "${WHEEL}")"
install -d -m 0755 /workspace/runtime
install -m 0444 "${WHEEL}" "/workspace/runtime/${WHEEL_NAME}"

# `--local-dry-run` is forwarded only when the caller explicitly asked for it
# *and* the workload's own environment marker is set.  A real Phala job sets
# neither, so a production run cannot silently accept a fixture artifact.
declare -a dry_run_flag=()
if [[ "${SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN:-}" == "1" ]]; then
    echo "ch25-a7-boundary phala-tdx: LOCAL DRY RUN -- not a production claim" >&2
    dry_run_flag=(--local-dry-run)
fi

cd /workspace
exec python3 "${WORKLOAD}" \
    --algorithm-id "${ALGORITHM_ID}" \
    --challenge "${SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE:?}" \
    --job-binding "${SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256:?}" \
    --image-digest "${IMAGE_DIGEST}" \
    --issued-at "${ISSUED_AT}" \
    --input "${INPUT_ROOT#/workspace/}/registered-input.json" \
    --artifact "${INPUT_ROOT#/workspace/}/a7_boundary.json" \
    --enclave-key "${ENCLAVE_KEY#/workspace/}" \
    --quote "${INPUT_ROOT#/workspace/}/tdx-quote.bin" \
    --quote-appraisal "${INPUT_ROOT#/workspace/}/dcap-qvl-appraisal.json" \
    --quote-appraisal-policy "${INPUT_ROOT#/workspace/}/dcap-qvl-policy.json" \
    --quote-appraisal-artifact "${INPUT_ROOT#/workspace/}/dcap-qvl-artifact.sha256" \
    --wheel "runtime/${WHEEL_NAME}" \
    --output "${OUTPUT_ROOT#/workspace/}/registered-result.txt" \
    --receipt "${OUTPUT_ROOT#/workspace/}/enclave-receipt.json" \
    --work "${OUTPUT_ROOT#/workspace/}/work" \
    "${dry_run_flag[@]}"

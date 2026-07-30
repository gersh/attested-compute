#!/bin/bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Container entry point for a leancompcert CompCert artifact campaign.
#
# This is the CH25 A.7 entry point (`proof_build/ch25_a7_phala_tdx/
# run_phala_tdx_campaign.sh`) with the FLINT/Arb workload replaced by one
# `exec`-free invocation of a statically linked CompCert artifact.  Everything
# before and after that invocation is unchanged in kind: the same input
# validation, the same refusal to reuse an output root, the same key
# re-derivation from the dstack guest agent onto a container-local tmpfs.
#
# The artifact's contract is the whole reason this script is short: a
# leancompcert artifact's `main` returns 0 exactly when the value it computed
# equals the value certified in the Lean `Program`.  So the campaign's result
# bytes are a total function of one exit status, and this script does not have
# to parse, reduce, or believe anything the artifact printed.

set -euo pipefail
IFS=$'\n\t'
umask 077

INPUT_ROOT="${TG_INPUT_ROOT:-/workspace/input}"
OUTPUT_ROOT="${TG_OUTPUT_ROOT:-/workspace/output}"
KEY_ROOT="${TG_ENCLAVE_KEY_ROOT:-/workspace/keys}"
ARTIFACT="${TG_ARTIFACT_PATH:?TG_ARTIFACT_PATH is required}"
ARTIFACT_SHA256="${TG_ARTIFACT_SHA256:?TG_ARTIFACT_SHA256 is required}"
ARTIFACT_NAME="${TG_ARTIFACT_NAME:?TG_ARTIFACT_NAME is required}"
ALGORITHM_ID="${TG_ALGORITHM_ID:?TG_ALGORITHM_ID is required}"
IMAGE_DIGEST="${TG_FINAL_IMAGE_REFERENCE:?TG_FINAL_IMAGE_REFERENCE is required}"
ISSUED_AT="${TG_ISSUED_AT:?TG_ISSUED_AT is required}"
KEY_DERIVER="${TG_PHALA_TDX_KEY_DERIVER:?TG_PHALA_TDX_KEY_DERIVER is required}"
PRELUDE_SUMMARY="${TG_PRELUDE_SUMMARY:?TG_PRELUDE_SUMMARY is required}"
ENCLAVE_KEY="${KEY_ROOT}/enclave-signing-key.hex"

die() { printf '%s\n' "$*" >&2; exit 1; }

case "${IMAGE_DIGEST}" in
  sha256:*) [ "${#IMAGE_DIGEST}" -eq 71 ] || die "malformed image digest" ;;
  *) die "image digest must be sha256:<64 hex>" ;;
esac
printf '%s' "${ISSUED_AT}" \
  | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' \
  || die "issued-at must be RFC 3339 UTC"

for root in "${INPUT_ROOT}" "${OUTPUT_ROOT}" "${KEY_ROOT}"; do
  case "${root}" in /workspace/*) ;; *) die "root outside /workspace: ${root}" ;; esac
done
[ -d "${INPUT_ROOT}" ] && [ ! -L "${INPUT_ROOT}" ] || die "bad input root"
[ -d "${KEY_ROOT}" ] && [ ! -L "${KEY_ROOT}" ] || die "bad key root"
[ ! -e "${OUTPUT_ROOT}" ] || die "output root already exists; refusing to reuse"

require_input() {
  local path="${INPUT_ROOT}/$1"
  [ -f "${path}" ] && [ ! -L "${path}" ] && [ -s "${path}" ] \
    || die "missing or unusable required input: $1"
}
require_input registered-input.json
require_input tdx-quote.bin
require_input dcap-qvl-appraisal.json
require_input dcap-qvl-policy.json
require_input dcap-qvl-artifact.sha256
[ -f "${PRELUDE_SUMMARY}" ] || die "missing prelude summary"

# The artifact is re-verified inside the TD, not merely at image build time.
# A layer-level tamper that survived the build check would still fail here,
# and this check runs after the quote has already measured the image.
printf '%s  %s\n' "${ARTIFACT_SHA256}" "${ARTIFACT}" \
  | sha256sum --check --strict \
  || die "REFUSED: artifact digest does not match the pinned value"
[ -x "${ARTIFACT}" ] || die "artifact is not executable"

[ ! -e "${ENCLAVE_KEY}" ] || die "signing key already present; refusing"
python3 "${KEY_DERIVER}" --derive-key-only \
  --key-out "${ENCLAVE_KEY}" --prelude-summary "${PRELUDE_SUMMARY}"

mkdir -p "${OUTPUT_ROOT}" "${OUTPUT_ROOT}/work"

# ---------------------------------------------------------------------------
# The whole campaign.
#
# `set +e` around exactly one command: a non-zero exit is a legitimate
# campaign outcome ("the certified value does not hold"), not a script error,
# and must reach the receipt as the bytes `false` rather than as a crash.
# ---------------------------------------------------------------------------
set +e
"${ARTIFACT}" >"${OUTPUT_ROOT}/work/artifact-stdout.txt" \
              2>"${OUTPUT_ROOT}/work/artifact-stderr.txt"
ARTIFACT_STATUS=$?
set -e

if [ "${ARTIFACT_STATUS}" -eq 0 ]; then
  RESULT=true
elif [ "${ARTIFACT_STATUS}" -eq 1 ]; then
  RESULT=false
else
  # Any other status is a fault (signal, missing loader, OOM), not a verdict.
  # Emitting `false` here would be a lie: `false` asserts that the artifact
  # ran and disagreed.  Refuse instead.
  die "REFUSED: artifact exited ${ARTIFACT_STATUS}, which is neither verdict"
fi
printf '%s' "${RESULT}" >"${OUTPUT_ROOT}/registered-result.txt"

python3 - "$@" <<'PY'
import hashlib, json, os, sys
sys.path.insert(0, "/opt/sparkinterval")
from tg_verifier.phala_tdx_receipt import sign_receipt

out = os.environ["TG_OUTPUT_ROOT"]
inp = os.environ["TG_INPUT_ROOT"]
key = open(os.environ["TG_ENCLAVE_KEY_ROOT"] + "/enclave-signing-key.hex").read().strip()
summary = json.load(open(os.environ["TG_PRELUDE_SUMMARY"]))


def digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


result = open(out + "/registered-result.txt").read()
fields = {
    "algorithm_id": os.environ["TG_ALGORITHM_ID"],
    "algorithm_hash": os.environ["TG_ALGORITHM_HASH"],
    "input_hash": digest_file(inp + "/registered-input.json"),
    "parameters_hash": os.environ["TG_PARAMETERS_HASH"],
    "domain_hash": os.environ["TG_DOMAIN_HASH"],
    "result": result,
    "output_hash": digest_text(result),
    "challenge_nonce": os.environ["SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE"],
    "job_binding_sha256": os.environ["SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256"],
    "app_id": summary["app_id"],
    "compose_hash": summary["compose_hash"],
    "image_digest": os.environ["TG_FINAL_IMAGE_REFERENCE"],
    "tdx_quote_sha256": digest_file(inp + "/tdx-quote.bin"),
    "dcap_qvl_output_sha256": digest_file(inp + "/dcap-qvl-appraisal.json"),
    "dcap_qvl_policy_sha256": digest_file(inp + "/dcap-qvl-policy.json"),
    "dcap_qvl_artifact_sha256": digest_file(inp + "/dcap-qvl-artifact.sha256"),
    "report_data_sha256": summary["report_data_sha256"],
    "issued_at": os.environ["TG_ISSUED_AT"],
}
receipt = sign_receipt(private_key_hex=key, fields=fields)
# The artifact digest travels as unsigned provenance: it is already bound
# through `algorithm_hash`, whose preimage `canonicalDefinition` names it.
receipt["artifact_sha256"] = os.environ["TG_ARTIFACT_SHA256"]
receipt["artifact_name"] = os.environ["TG_ARTIFACT_NAME"]
receipt["backend"] = "phala_dstack_tdx_cpu_compcert"
with open(out + "/enclave-receipt.json", "w") as fh:
    json.dump(receipt, fh, sort_keys=True, separators=(",", ":"))
PY

exit 0

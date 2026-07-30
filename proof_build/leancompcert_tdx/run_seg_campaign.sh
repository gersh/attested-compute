#!/bin/bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Container entry point for a *chained* leancompcert campaign.
#
# `run_artifact_campaign.sh` runs one artifact.  A `Ports.ArraySegSieve`
# residue tests its window against a single threshold, so covering a range at
# full strength takes a chain of windows, each seeded with the previous
# window's carry-out.  This entry point runs that chain.
#
# What it checks before running anything, in order:
#
#   1. the campaign manifest's SHA-256 equals `TG_MANIFEST_SHA256`, which is
#      the digest named inside `canonicalDefinition` and therefore inside
#      `algorithmHash`;
#   2. the manifest describes a gap-free, correctly chained cover of the
#      claimed range -- every window's seed is the previous window's carry,
#      every window abuts the last, and no window inside the claimed range
#      expects a threshold violation;
#   3. every artifact named by the manifest exists and hashes to the digest
#      the manifest records.
#
# Then it runs each window in order.  The exit-status discipline is the
# soundness-critical part and is stated once here:
#
#   0     the window agreed with every value the manifest recorded
#   1     the window disagreed -- a legitimate `false` verdict
#   other abnormal termination (signal, OOM, missing loader).  NEVER a
#         verdict.  `128 + N` means death by signal N.  The campaign refuses
#         rather than signing a `false` it did not observe.
#
# A `false` from any window ends the chain immediately: the windows after it
# were seeded from a carry that window did not reproduce, so their verdicts
# would be meaningless.

set -euo pipefail
IFS=$'\n\t'
umask 077

INPUT_ROOT="${TG_INPUT_ROOT:-/workspace/input}"
OUTPUT_ROOT="${TG_OUTPUT_ROOT:-/workspace/output}"
KEY_ROOT="${TG_ENCLAVE_KEY_ROOT:-/workspace/keys}"
CAMPAIGN_ROOT="${TG_CAMPAIGN_ROOT:?TG_CAMPAIGN_ROOT is required}"
MANIFEST_SHA256="${TG_MANIFEST_SHA256:?TG_MANIFEST_SHA256 is required}"
CAMPAIGN_NAME="${TG_CAMPAIGN_NAME:?TG_CAMPAIGN_NAME is required}"
ALGORITHM_ID="${TG_ALGORITHM_ID:?TG_ALGORITHM_ID is required}"
IMAGE_DIGEST="${TG_FINAL_IMAGE_REFERENCE:?TG_FINAL_IMAGE_REFERENCE is required}"
ISSUED_AT="${TG_ISSUED_AT:?TG_ISSUED_AT is required}"
KEY_DERIVER="${TG_PHALA_TDX_KEY_DERIVER:?TG_PHALA_TDX_KEY_DERIVER is required}"
PRELUDE_SUMMARY="${TG_PRELUDE_SUMMARY:?TG_PRELUDE_SUMMARY is required}"
CHECKER="${TG_CAMPAIGN_CHECKER:-/opt/sparkinterval/tg_seg_campaign_check.py}"
ENCLAVE_KEY="${KEY_ROOT}/enclave-signing-key.hex"
MANIFEST="${CAMPAIGN_ROOT}/campaign-manifest.txt"

die() { printf '%s\n' "$*" >&2; exit 1; }

case "${IMAGE_DIGEST}" in
  sha256:*) [ "${#IMAGE_DIGEST}" -eq 71 ] || die "malformed image digest" ;;
  *) die "image digest must be sha256:<64 hex>" ;;
esac
printf '%s' "${ISSUED_AT}" \
  | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' \
  || die "issued-at must be RFC 3339 UTC"
printf '%s' "${MANIFEST_SHA256}" | grep -Eq '^[0-9a-f]{64}$' \
  || die "manifest digest must be 64 lowercase hex digits"

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

# (1) The manifest is what `algorithmHash` names.  Check it before reading it.
[ -f "${MANIFEST}" ] && [ ! -L "${MANIFEST}" ] || die "missing campaign manifest"
printf '%s  %s\n' "${MANIFEST_SHA256}" "${MANIFEST}" \
  | sha256sum --check --strict \
  || die "REFUSED: campaign manifest digest does not match the pinned value"

# (2) and (3): structure, chain linkage, and every artifact digest.  The
# checker re-reads the manifest text; it is the same routine the build host
# runs, so a manifest that passes here passed there.
mkdir -p "${OUTPUT_ROOT}" "${OUTPUT_ROOT}/work"
python3 "${CHECKER}" --campaign-root "${CAMPAIGN_ROOT}" \
    --report "${OUTPUT_ROOT}/work/campaign-precheck.json" \
  || die "REFUSED: campaign manifest or artifact set failed the pre-check"

[ ! -e "${ENCLAVE_KEY}" ] || die "signing key already present; refusing"
python3 "${KEY_DERIVER}" --derive-key-only \
  --key-out "${ENCLAVE_KEY}" --prelude-summary "${PRELUDE_SUMMARY}"

# ---------------------------------------------------------------------------
# The chain.
# ---------------------------------------------------------------------------
RESULT=true
RAN=0
FAILED_AT=-1
LOG="${OUTPUT_ROOT}/work/window-status.txt"
: >"${LOG}"

while read -r index binary; do
  set +e
  "${CAMPAIGN_ROOT}/${binary}" </dev/null >/dev/null 2>&1
  STATUS=$?
  set -e
  printf '%s %s %s\n' "${index}" "${binary}" "${STATUS}" >>"${LOG}"
  RAN=$((RAN + 1))
  if [ "${STATUS}" -eq 0 ]; then
    continue
  elif [ "${STATUS}" -eq 1 ]; then
    RESULT=false
    FAILED_AT="${index}"
    break
  else
    die "REFUSED: window ${index} (${binary}) exited ${STATUS}, which is \
neither verdict.  A signal, an OOM kill, or a loader failure must never be \
signed as a clean \`false\`."
  fi
done < <(python3 "${CHECKER}" --campaign-root "${CAMPAIGN_ROOT}" --list)

TOTAL=$(python3 "${CHECKER}" --campaign-root "${CAMPAIGN_ROOT}" --count)
if [ "${RESULT}" = "true" ] && [ "${RAN}" -ne "${TOTAL}" ]; then
  die "REFUSED: ran ${RAN} of ${TOTAL} windows but is about to emit \`true\`"
fi

printf '%s' "${RESULT}" >"${OUTPUT_ROOT}/registered-result.txt"
python3 - <<PY >"${OUTPUT_ROOT}/work/campaign-run.json"
import json
print(json.dumps({
    "campaign": "${CAMPAIGN_NAME}",
    "windows_total": ${TOTAL},
    "windows_run": ${RAN},
    "failed_at": ${FAILED_AT},
    "result": "${RESULT}",
}, sort_keys=True))
PY

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
# The manifest digest travels as unsigned provenance: it is already bound
# through `algorithm_hash`, whose preimage `canonicalDefinition` names it.
receipt["campaign_manifest_sha256"] = os.environ["TG_MANIFEST_SHA256"]
receipt["campaign_name"] = os.environ["TG_CAMPAIGN_NAME"]
receipt["backend"] = "phala_dstack_tdx_cpu_compcert_chain"
with open(out + "/enclave-receipt.json", "w") as fh:
    json.dump(receipt, fh, sort_keys=True, separators=(",", ":"))
PY

exit 0

#!/bin/bash
# Deploy the x86_64 CompCert attested run to Phala TDX, capture the evidence,
# verify it, and destroy the CVM.  About $0.03.
#
#   export PHALA_CLOUD_API_KEY=<phak_... from ~/env; the PHALA_KEY there is a
#                               Redpill inference key and 401s on Cloud>
#   audits/compcert/rh_phala/deploy.sh
#
# Recipe gotchas honored (each cost a run once):
#   * no --node-id: the CLI forwards it as teepod_id and auto-select is right;
#   * `$` escaped as `$$` inside the compose -- done by build_compose.py;
#   * the entry point sleeps, because a container that exits loses its logs;
#   * evidence stays well under the ~64 KiB server-side log cap;
#   * DESTROY, never stop: retained disk keeps billing while stopped.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The deployment being run: the directory holding deployment.json, its compose
# and its artifacts.  The pipeline itself belongs to no consumer.
DEPLOYMENT="$(cd "${1:-${DEPLOYMENT:-$PWD}}" && pwd)"
[ -f "$DEPLOYMENT/deployment.json" ] || {
  echo "usage: $(basename "$0") <deployment-dir>   (needs deployment.json)" >&2; exit 2; }
ROOT="$(cd "$HERE/../.." && pwd)"
NAME="${CVM_NAME:-rh-x86-attested}"
CLI="npx phala@1.1.20"
EVIDENCE="${EVIDENCE_DIR:-$DEPLOYMENT/retained-evidence}"

: "${PHALA_CLOUD_API_KEY:?export from ~/env (phak_ prefix, NOT the Redpill PHALA_KEY)}"

# The compose embeds artifact digests.  If it is stale relative to build/x86,
# the run would attest binaries that are not the ones on disk here.
echo "== checking the compose is current =="
before="$(sha256sum "$DEPLOYMENT/docker-compose.yaml" | cut -d' ' -f1)"
python3 "$HERE/build_compose.py" --manifest "$DEPLOYMENT/deployment.json" >/dev/null
after="$(sha256sum "$DEPLOYMENT/docker-compose.yaml" | cut -d' ' -f1)"
[ "$before" = "$after" ] || {
  echo "docker-compose.yaml was stale and has been regenerated ($before -> $after)."
  echo "Re-run dry_run.sh, commit the change, then deploy."; exit 1; }
echo "  current: $after"

echo "== deploying =="
$CLI deploy -n "$NAME" -c "$DEPLOYMENT/docker-compose.yaml" \
  --instance-type tdx.medium --disk-size 40G --public-logs --wait

mkdir -p "$EVIDENCE"
echo "== waiting for the run to finish =="
LOG="$EVIDENCE/phala-run.log"
# How long to wait for the enclave's completion marker.  60 polls x 20 s = 20
# minutes was too short once a batch held more than a couple of artifacts: b1
# reached 1 of 12 and b2 reached 24 of 26 before the poll gave up, and both were
# destroyed with the work nearly done.  The sizing data that would have caught
# this did not exist -- `run_ccomp.seconds` is absent for every freshly emitted
# campaign, so a per-batch sum silently reads as zero.  Generous by default; a
# CVM that finishes early is destroyed as soon as the marker appears, so a large
# bound costs nothing.
POLLS="${DEPLOY_POLLS:-240}"
for attempt in $(seq "$POLLS"); do
  $CLI cvms logs "$NAME" --tail 4000 > "$LOG" 2>/dev/null || true
  if grep -q 'RH-X86-DONE' "$LOG"; then
    echo "  marker seen after ${attempt}/${POLLS} poll(s), $(wc -c < "$LOG") bytes of log"
    break
  fi
  printf '  poll %d: %s bytes, no marker yet\n' "$attempt" "$(wc -c < "$LOG")"
  sleep 20
done
# A missing marker must NOT exit here: the destroy step is below, and skipping
# it leaves a CVM billing indefinitely -- which is exactly how the first run of
# this campaign cost money.  Record the failure and fall through.
MARKER_SEEN=1
if ! grep -q 'RH-X86-DONE' "$LOG"; then
  echo "  !! the run never reached its marker after 20 minutes"
  echo "     (the log so far is kept; the CVM is still destroyed below)"
  MARKER_SEEN=0
fi

# The app-compose document is NOT fetched from the Cloud API: its JSON view of
# that document is not byte-faithful to what dstack hashed, so its digest can
# never be compared against mr_config_id (224 candidate re-serializations under
# the CLI's own algorithm were tried and all missed).  The enclave reads the raw
# bytes from /tapp inside the measured VM and emits them as evidence instead.

echo "== verifying =="
set +e
if [ "$MARKER_SEEN" = 1 ]; then
  python3 "$HERE/verify_run.py" --deployment "$DEPLOYMENT" --log "$LOG" --evidence-dir "$EVIDENCE" | tee "$EVIDENCE/verify.txt"
  STATUS=${PIPESTATUS[0]}
else
  echo "skipped: the run produced no marker, so there is no evidence to verify" \
    | tee "$EVIDENCE/verify.txt"
  STATUS=1
fi
set -e

if [ "${KEEP_CVM:-0}" = "1" ]; then
  echo "== KEEP_CVM=1: leaving $NAME up.  DESTROY IT: $CLI cvms delete $NAME =="
else
  echo "== destroying $NAME (never stop: retained disk keeps billing) =="
  # `phala cvms delete` prompts "Are you sure?" even with stdin closed and has
  # no --yes flag, so it silently does nothing in an unattended run -- and the
  # first run's `|| true` hid that, leaving a CVM billing.  Delete through the
  # REST API instead, and CONFIRM it, because an undeleted CVM costs money for
  # as long as nobody notices.
  cvm_id="$(curl -s -m 30 -H "X-API-Key: $PHALA_CLOUD_API_KEY" \
      https://cloud-api.phala.network/api/v1/cvms \
    | python3 -c "
import json,sys
for c in json.load(sys.stdin):
    h = {**c, **(c.get('hosted') or {})}
    if h.get('name') == '$NAME':
        print(h.get('id') or h.get('app_id')); break
")"
  if [ -n "$cvm_id" ]; then
    code="$(curl -s -m 60 -X DELETE -o /dev/null -w '%{http_code}' \
      -H "X-API-Key: $PHALA_CLOUD_API_KEY" \
      "https://cloud-api.phala.network/api/v1/cvms/$cvm_id")"
    echo "  DELETE $cvm_id -> HTTP $code"
    case "$code" in 200|202|204) ;; *) echo "  !! DELETE FAILED -- destroy it by hand NOW"; ;; esac
  else
    echo "  no CVM named $NAME found; nothing to destroy"
  fi
  remaining="$(curl -s -m 30 -H "X-API-Key: $PHALA_CLOUD_API_KEY" \
      https://cloud-api.phala.network/api/v1/cvms \
    | python3 -c "
import json,sys
print(' '.join(f\"{ {**c, **(c.get('hosted') or {})}.get('name') }=\" +
               str({**c, **(c.get('hosted') or {})}.get('status'))
               for c in json.load(sys.stdin)) or 'none')
")"
  echo "  CVMs now: $remaining"
fi

echo
echo "evidence: $EVIDENCE"
exit "$STATUS"

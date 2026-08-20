#!/bin/bash
# Negative tests for the attested run.  Every gate here is one the real run
# depends on, so each must be shown to REFUSE -- a gate that has only ever been
# seen to pass is not known to be a gate at all.
#
# Runs entirely locally (no Phala, no cost) by driving the COMMITTED entry point
# with one thing tampered at a time.
#
#   1  a tampered binary            -> the enclave refuses BEFORE executing it
#   2  a wrong pinned expectation   -> the enclave reports MISMATCH, and the
#                                      statement carries matched=0
#   3  a wrong exit expectation     -> likewise
#   4  a mock (unsigned) quote      -> verify_run.py refuses the whole run
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The deployment being run: the directory holding deployment.json, its compose
# and its artifacts.  The pipeline itself belongs to no consumer.
DEPLOYMENT="$(cd "${1:-${DEPLOYMENT:-$PWD}}" && pwd)"
[ -f "$DEPLOYMENT/deployment.json" ] || {
  echo "usage: $(basename "$0") <deployment-dir>   (needs deployment.json)" >&2; exit 2; }
ROOT="$(cd "$HERE/../.." && pwd)"
IMAGE="${X86CROSS_IMAGE:-lcc-x86cross:24.04}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/mock"
cp "$ROOT/tests/data/phala_tdx_live/retained-evidence/input/tdx-quote.bin" "$WORK/mock/"
cp "$ROOT/tests/data/phala_tdx_live/retained-evidence/evidence/dstack-event-log.json" "$WORK/mock/"
cp "$HERE/mock_dstack.py" "$WORK/mock/"

extract() { # tamper-mode -> writes entrypoint.sh and env.list
  python3 - "$DEPLOYMENT/docker-compose.yaml" "$WORK" "$1" <<'PY'
import base64, gzip, json, pathlib, sys
compose, work, mode = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3]
text = pathlib.Path(compose).read_text()
service = next(iter(json.loads(text[text.index("{"):])["services"].values()))
work.joinpath("entrypoint.sh").write_text(service["command"][2].replace("$$", "$"))
env = dict(service["environment"])
env["RUNNER"] = "qemu-x86_64-static -L /usr/x86_64-linux-gnu"
if mode == "binary":
    # Flip one byte of the payload; its digest no longer matches SCAN_BIN_SHA.
    raw = bytearray(gzip.decompress(base64.b64decode(env["SCAN_BIN_GZ_B64"])))
    raw[len(raw) // 2] ^= 0x01
    env["SCAN_BIN_GZ_B64"] = base64.b64encode(
        gzip.compress(bytes(raw), compresslevel=9, mtime=0)).decode()
elif mode == "expect_sha":
    env["SCAN_EXPECT_SHA"] = "00" * 32
elif mode == "expect_exit":
    env["SCAN_EXPECT_EXIT"] = "1"
work.joinpath("env.list").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
PY
}

drive() { # -> transcript on stdout
  docker run --rm --platform linux/arm64 --env-file "$WORK/env.list" \
    -v "$WORK/entrypoint.sh:/entrypoint.sh:ro" -v "$WORK/mock:/mock:ro" \
    "$IMAGE" /bin/bash -c '
      set -e; mkdir -p /var/run
      python3 /mock/mock_dstack.py &
      for i in $(seq 50); do [ -S /var/run/dstack.sock ] && break; sleep 0.1; done
      bash /entrypoint.sh > /tmp/out.txt 2>&1 &
      for _ in $(seq 1800); do grep -qE "RH-X86-DONE|REFUSED" /tmp/out.txt && break; sleep 1; done
      cat /tmp/out.txt' 2>&1
}

fails=0
expect() { # label  pattern  transcript-file
  if grep -qE "$2" "$3"; then printf '  [OK]     %s\n' "$1"
  else printf '  [BROKEN] %s -- expected /%s/\n' "$1" "$2"; fails=$((fails + 1)); fi
}

echo "== 1. tampered binary: the enclave must refuse before executing =="
extract binary; drive > "$WORK/t1.txt" || true
expect "refused on digest mismatch" 'REFUSED: rh_scan_pilot sha256' "$WORK/t1.txt"
expect "never reached the run stage" 'RH-X86-EXIT=[^0]' "$WORK/t1.txt"
grep -q 'CHECK points' "$WORK/t1.txt" && { echo "  [BROKEN] it executed the tampered binary anyway"; fails=$((fails+1)); } || echo "  [OK]     the tampered binary never ran"

echo "== 2. wrong pinned transcript digest: the enclave must report MISMATCH =="
extract expect_sha; drive > "$WORK/t2.txt" || true
expect "reported MISMATCH" 'rh_scan_pilot .*MISMATCH' "$WORK/t2.txt"
# The statement travels as base64, so decode it rather than grepping plaintext.
python3 - "$WORK/t2.txt" > "$WORK/t2.statement" <<'PY'
import base64, json, sys, pathlib
chunks, capturing = [], False
for line in pathlib.Path(sys.argv[1]).read_text(errors="replace").splitlines():
    at = line.find("RH-X86-EVIDENCE-V1")
    if at < 0:
        continue
    rest = line[at + len("RH-X86-EVIDENCE-V1"):].strip()
    if rest.startswith("BEGIN "):
        capturing = json.loads(rest[6:])["name"] == "statement.txt"
    elif rest.startswith("DATA ") and capturing:
        chunks.append(rest[5:].strip())
    elif rest.startswith("END ") and capturing:
        break
sys.stdout.write(base64.b64decode("".join(chunks)).decode(errors="replace"))
PY
expect "statement records matched=0" 'matched_pinned_expectation=0' "$WORK/t2.statement"
expect "the run still reached its marker" 'RH-X86-DONE' "$WORK/t2.txt"
set +e
python3 "$HERE/verify_run.py" --deployment "$DEPLOYMENT" --log "$WORK/t2.txt" > "$WORK/v2.txt" 2>&1
v2=$?
set -e
[ "$v2" -ne 0 ] && echo "  [OK]     verify_run.py refused the run (exit $v2)" \
  || { echo "  [BROKEN] verify_run.py accepted a mismatched transcript"; fails=$((fails+1)); }
expect "verifier flagged S6b" '\[FAIL\] S6b rh_scan_pilot' "$WORK/v2.txt"

echo "== 3. wrong pinned exit status: the enclave must report MISMATCH =="
extract expect_exit; drive > "$WORK/t3.txt" || true
expect "reported MISMATCH" 'rh_scan_pilot .*MISMATCH' "$WORK/t3.txt"

echo "== 4. the verifier must refuse a run whose quote is not Intel-signed =="
extract none; drive > "$WORK/t4.txt" || true
set +e
python3 "$HERE/verify_run.py" --deployment "$DEPLOYMENT" --log "$WORK/t4.txt" > "$WORK/v4.txt" 2>&1
status=$?
set -e
[ "$status" -ne 0 ] && echo "  [OK]     verify_run.py exited $status" \
  || { echo "  [BROKEN] verify_run.py accepted a mock quote"; fails=$((fails+1)); }
expect "refused the unsigned quote (A1)" '\[FAIL\] A1' "$WORK/v4.txt"

echo
if [ "$fails" -eq 0 ]; then echo "negative_test: PASS — every gate refused what it must"
else echo "negative_test: FAIL — $fails gate(s) did not refuse"; exit 1; fi

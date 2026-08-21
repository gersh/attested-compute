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
#   5  an image missing the tools   -> the enclave refuses instead of
#                                      installing them at run time
#   6  a noexec work directory      -> the enclave refuses up front rather
#                                      than failing every artifact with 126
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The deployment being run: the directory holding deployment.json, its compose
# and its artifacts.  The pipeline itself belongs to no consumer.
DEPLOYMENT="$(cd "${1:-${DEPLOYMENT:-$PWD}}" && pwd)"
[ -f "$DEPLOYMENT/deployment.json" ] || {
  echo "usage: $(basename "$0") <deployment-dir>   (needs deployment.json)" >&2; exit 2; }
ROOT="$(cd "$HERE/../.." && pwd)"
# The artifact these gates tamper with.  Taken from the deployment rather than
# hard-coded, so the gates run against ANY deployment; hard-coding one name
# meant they simply refused to run on a batch that did not contain it.
TARGET="${NEGATIVE_TEST_TARGET:-$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(d['artifacts'][0]['name'])" "${1:-${DEPLOYMENT:-$PWD}}/deployment.json")}"
echo "negative_test: tampering with '$TARGET'"
# As in dry_run.sh: the image under test is the COMPOSE's image, so these gates
# are shown to hold in the container that actually deploys.  The cross image
# only lends the x86_64 emulator and sysroot, which real hardware has natively.
QEMU_FROM="${X86CROSS_IMAGE:-lcc-x86cross:24.04}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/mock" "$WORK/sysroot"
docker run --rm --entrypoint /bin/cat "$QEMU_FROM" \
  /usr/bin/qemu-x86_64-static > "$WORK/qemu-x86_64-static"
chmod +x "$WORK/qemu-x86_64-static"
docker run --rm --entrypoint /bin/tar "$QEMU_FROM" \
  -cf - -C /usr x86_64-linux-gnu | tar -xf - -C "$WORK/sysroot"
cp "$ROOT/tests/data/phala_tdx_live/retained-evidence/input/tdx-quote.bin" "$WORK/mock/"
cp "$ROOT/tests/data/phala_tdx_live/retained-evidence/evidence/dstack-event-log.json" "$WORK/mock/"
cp "$HERE/mock_dstack.py" "$WORK/mock/"

extract() { # tamper-mode -> writes entrypoint.sh and env.list
  NT_TARGET="$TARGET" python3 - "$DEPLOYMENT/docker-compose.yaml" "$WORK" "$1" <<'PY'
import base64, gzip, json, os, pathlib, sys
compose, work, mode = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3]
text = pathlib.Path(compose).read_text()
service = next(iter(json.loads(text[text.index("{"):])["services"].values()))
work.joinpath("entrypoint.sh").write_text(service["command"][2].replace("$$", "$"))
env = dict(service["environment"])
env["RUNNER"] = "qemu-x86_64-static -L /usr/x86_64-linux-gnu"
work.joinpath("image").write_text(service["image"])
# Artifacts are indexed, not named, in the entry point.  Find the index of the
# one these gates are written against rather than hard-coding a slot: a
# manifest reordering would otherwise tamper with some other artifact and the
# gates would pass while testing nothing.
TARGET = os.environ["NT_TARGET"]
slots = [k[:-len("_NAME")] for k, v in env.items()
         if k.startswith("A") and k.endswith("_NAME") and v == TARGET]
if len(slots) != 1:
    raise SystemExit(f"expected exactly one {TARGET} artifact, found {len(slots)}")
A = slots[0]
if mode == "binary":
    # Flip one byte of the payload; its digest no longer matches {A}_BIN_SHA.
    raw = bytearray(gzip.decompress(base64.b64decode(env[f"{A}_BIN_GZ_B64"])))
    raw[len(raw) // 2] ^= 0x01
    env[f"{A}_BIN_GZ_B64"] = base64.b64encode(
        gzip.compress(bytes(raw), compresslevel=9, mtime=0)).decode()
elif mode == "expect_sha":
    env[f"{A}_EXPECT_SHA"] = "00" * 32
elif mode == "expect_exit":
    env[f"{A}_EXPECT_EXIT"] = "1"
work.joinpath("env.list").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
PY
}

drive() { # -> transcript on stdout
  docker run --rm --platform linux/arm64 --network none \
    --env-file "$WORK/env.list" \
    -v "$WORK/qemu-x86_64-static:/usr/bin/qemu-x86_64-static:ro" \
    -v "$WORK/sysroot/x86_64-linux-gnu:/usr/x86_64-linux-gnu:ro" \
    -v "$WORK/entrypoint.sh:/entrypoint.sh:ro" -v "$WORK/mock:/mock:ro" \
    "$(cat "$WORK/image")" /bin/bash -c '
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
expect "refused on digest mismatch" "REFUSED: $TARGET sha256" "$WORK/t1.txt"
expect "never reached the run stage" 'RH-X86-EXIT=[^0]' "$WORK/t1.txt"
grep -q 'CHECK points' "$WORK/t1.txt" && { echo "  [BROKEN] it executed the tampered binary anyway"; fails=$((fails+1)); } || echo "  [OK]     the tampered binary never ran"

echo "== 2. wrong pinned transcript digest: the enclave must report MISMATCH =="
extract expect_sha; drive > "$WORK/t2.txt" || true
expect "reported MISMATCH" "$TARGET .*MISMATCH" "$WORK/t2.txt"
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
expect "verifier flagged S6b" "\\[FAIL\\] S6b $TARGET" "$WORK/v2.txt"

echo "== 3. wrong pinned exit status: the enclave must report MISMATCH =="
extract expect_exit; drive > "$WORK/t3.txt" || true
expect "reported MISMATCH" "$TARGET .*MISMATCH" "$WORK/t3.txt"

echo "== 4. the verifier must refuse a run whose quote is not Intel-signed =="
extract none; drive > "$WORK/t4.txt" || true
set +e
python3 "$HERE/verify_run.py" --deployment "$DEPLOYMENT" --log "$WORK/t4.txt" > "$WORK/v4.txt" 2>&1
status=$?
set -e
[ "$status" -ne 0 ] && echo "  [OK]     verify_run.py exited $status" \
  || { echo "  [BROKEN] verify_run.py accepted a mock quote"; fails=$((fails+1)); }
expect "refused the unsigned quote (A1)" '\[FAIL\] A1' "$WORK/v4.txt"

echo "== 5. an image without the toolchain: the enclave must refuse, not install =="
# The entry point used to `apt-get install` gcc and the python3 that signs the
# statement.  Anything fetched at run time is outside the measurement, so a
# substituted interpreter could have signed a false statement with the genuine
# enclave key.  The tools now have to be in the measured image, and this gate
# is what keeps that true: run the same entry point in an image that lacks a
# native gcc and require a refusal.
extract none
t5="$(docker run --rm --platform linux/arm64 --network none \
  --env-file "$WORK/env.list" \
  -v "$WORK/entrypoint.sh:/entrypoint.sh:ro" -v "$WORK/mock:/mock:ro" \
  "$QEMU_FROM" /bin/bash -c '
    set -e; mkdir -p /var/run
    python3 /mock/mock_dstack.py &
    for i in $(seq 50); do [ -S /var/run/dstack.sock ] && break; sleep 0.1; done
    bash /entrypoint.sh > /tmp/out.txt 2>&1 &
    for _ in $(seq 600); do grep -qE "RH-X86-DONE|REFUSED" /tmp/out.txt && break; sleep 1; done
    cat /tmp/out.txt' 2>&1 || true)"
printf '%s' "$t5" > "$WORK/t5.txt"
expect "refused the under-provisioned image" 'REFUSED: gcc missing from the base image' "$WORK/t5.txt"
expect "did not run any artifact" 'RH-X86-EXIT=[^0]' "$WORK/t5.txt"
# Comments are stripped first: the entry point *documents* the apt-get it used
# to run, and matching that text would fail a gate that is in fact holding.
if sed 's/#.*//' "$HERE/enclave_run.sh" | grep -qE 'apt-get|apk add|pip install|curl|wget'; then
  echo "  [BROKEN] the entry point still fetches something at run time"; fails=$((fails+1))
else
  echo "  [OK]     the entry point fetches nothing at run time"
fi

echo "== 6. a noexec work directory: the enclave must refuse before running anything =="
# Docker mounts a `--tmpfs` noexec unless told otherwise, and every artifact is
# executed from /tmp.  Getting this wrong costs a whole deployment: on hardware
# the artifacts run natively and all fail with exit 126.  The rehearsal cannot
# catch it by itself, because there they run under qemu, which reads them as
# data -- so the entry point checks explicitly, and this gate proves the check
# fires.
extract none
t6="$(docker run --rm --platform linux/arm64 --network none \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=1g \
  --tmpfs /var/run:rw,nosuid,nodev,size=16m \
  --env-file "$WORK/env.list" \
  -v "$WORK/qemu-x86_64-static:/usr/bin/qemu-x86_64-static:ro" \
  -v "$WORK/sysroot/x86_64-linux-gnu:/usr/x86_64-linux-gnu:ro" \
  -v "$WORK/entrypoint.sh:/entrypoint.sh:ro" -v "$WORK/mock:/mock:ro" \
  "$(cat "$WORK/image")" /bin/bash -c '
    set -e; mkdir -p /var/run
    python3 /mock/mock_dstack.py &
    for i in $(seq 50); do [ -S /var/run/dstack.sock ] && break; sleep 0.1; done
    bash /entrypoint.sh > /tmp/out.txt 2>&1 &
    for _ in $(seq 600); do grep -qE "RH-X86-DONE|REFUSED" /tmp/out.txt && break; sleep 1; done
    cat /tmp/out.txt' 2>&1 || true)"
printf '%s' "$t6" > "$WORK/t6.txt"
expect "refused a noexec work directory" 'REFUSED: .* is not executable' "$WORK/t6.txt"
expect "did not run any artifact" 'RH-X86-EXIT=[^0]' "$WORK/t6.txt"
grep -q 'transcript matches the pinned digest' "$WORK/t6.txt" \
  && { echo "  [BROKEN] it ran artifacts anyway"; fails=$((fails+1)); } \
  || echo "  [OK]     nothing was executed"

echo
if [ "$fails" -eq 0 ]; then echo "negative_test: PASS — every gate refused what it must"
else echo "negative_test: FAIL — $fails gate(s) did not refuse"; exit 1; fi

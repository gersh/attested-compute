#!/bin/bash
# Local readiness check: run the COMMITTED docker-compose.yaml entry point
# verbatim, on this aarch64 host, against a mock dstack guest agent.
#
# "The repository has a script that does X" is not evidence the script runs --
# the first signed Phala run cost two deployments to a script that had never
# been executed.  This is the gate that makes that mistake impossible: if it
# passes, the only missing ingredients for a real run are Phala credentials.
#
# What differs from the real run, and only this:
#   * RUNNER=qemu-x86_64-static, because the host is aarch64 and the artifacts
#     are x86_64.  The artifacts themselves are the deployed bytes, and qemu is
#     bind-mounted in rather than installed, so the image stays as deployed.
#   * the dstack agent is mock_dstack.py, so the quote's signature is not
#     valid -- verify_run.py rejects it, which is the point.
# Everything else is as deployed: the compose's own image, by digest, with
# `--network none` matching the compose's `network_mode: none`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The deployment being run: the directory holding deployment.json, its compose
# and its artifacts.  The pipeline itself belongs to no consumer.
DEPLOYMENT="$(cd "${1:-${DEPLOYMENT:-$PWD}}" && pwd)"
[ -f "$DEPLOYMENT/deployment.json" ] || {
  echo "usage: $(basename "$0") <deployment-dir>   (needs deployment.json)" >&2; exit 2; }
ROOT="$(cd "$HERE/../.." && pwd)"
# The image is whatever the COMPOSE names -- the whole point of this gate is
# that the deployed image is the one exercised.  It used to default to the
# local cross-build image, which silently made the check worthless: that image
# has no native gcc, so an entry point that `apt-get install`ed its toolchain
# passed here while depending on packages the deployment never measured.
IMAGE=""                       # filled in from the compose below
QEMU_FROM="${X86CROSS_IMAGE:-lcc-x86cross:24.04}"   # supplies qemu-x86_64-static only
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A real retained quote supplies realistic bytes and length; the mock splices
# this run's report_data into it.
TEMPLATE="${MOCK_QUOTE_TEMPLATE:-$ROOT/tests/data/phala_tdx_live/retained-evidence/input/tdx-quote.bin}"
EVENTS="${MOCK_EVENT_LOG:-$ROOT/tests/data/phala_tdx_live/retained-evidence/evidence/dstack-event-log.json}"
for f in "$TEMPLATE" "$EVENTS"; do
  [ -f "$f" ] || { echo "dry_run: missing $f" >&2; exit 2; }
done
mkdir -p "$WORK/mock"
cp "$TEMPLATE" "$WORK/mock/tdx-quote.bin"
cp "$EVENTS"   "$WORK/mock/dstack-event-log.json"
cp "$HERE/mock_dstack.py" "$WORK/mock/"

# Extract the entry point and the environment from the committed compose, so
# what runs here is what deploys -- not a transcription of it.
python3 - "$DEPLOYMENT/docker-compose.yaml" "$WORK" <<'PY'
import json, pathlib, sys
compose, work = sys.argv[1], pathlib.Path(sys.argv[2])
text = pathlib.Path(compose).read_text()
document = json.loads(text[text.index("{"):])
service = next(iter(document["services"].values()))  # whatever it is called
script = service["command"][2].replace("$$", "$")
work.joinpath("entrypoint.sh").write_text(script)
env = dict(service["environment"])
env["RUNNER"] = "qemu-x86_64-static -L /usr/x86_64-linux-gnu"
work.joinpath("env.list").write_text(
    "".join(f"{k}={v}\n" for k, v in env.items()))
work.joinpath("image").write_text(service["image"])
print(f"dry_run: entry point {len(script):,} B, {len(env)} env vars, "
      f"image {service['image'][:32]}…")
PY

IMAGE="$(cat "$WORK/image")"

# The deployment image has no qemu (nor should it: on x86_64 hardware the
# artifacts run natively).  Lift the static emulator out of the cross image and
# bind-mount it, so the deployment image itself is unmodified.
docker run --rm --entrypoint /bin/cat "$QEMU_FROM" \
  /usr/bin/qemu-x86_64-static > "$WORK/qemu-x86_64-static"
chmod +x "$WORK/qemu-x86_64-static"
# ...and the x86_64 sysroot it resolves `-L` against.  Without it the two
# dynamically-linked pilots die on `/lib64/ld-linux-x86-64.so.2` and stop being
# exercised at all -- which is how the old cross image hid its own coverage.
# On real x86_64 hardware the loader is simply there.
mkdir -p "$WORK/sysroot"
docker run --rm --entrypoint /bin/tar "$QEMU_FROM" \
  -cf - -C /usr x86_64-linux-gnu | tar -xf - -C "$WORK/sysroot"

docker run --rm --platform linux/arm64 \
  --env-file "$WORK/env.list" \
  --network none \
  -v "$WORK/qemu-x86_64-static:/usr/bin/qemu-x86_64-static:ro" \
  -v "$WORK/sysroot/x86_64-linux-gnu:/usr/x86_64-linux-gnu:ro" \
  -v "$WORK/entrypoint.sh:/entrypoint.sh:ro" \
  -v "$WORK/mock:/mock:ro" \
  "$IMAGE" /bin/bash -c '
    set -e
    mkdir -p /var/run
    python3 /mock/mock_dstack.py &
    for i in $(seq 50); do [ -S /var/run/dstack.sock ] && break; sleep 0.1; done
    # The entry point ends in `sleep infinity` so the real deployment keeps its
    # logs.  Run it in the background and stop when the marker appears; piping
    # into `sed .../q` does NOT work, because sed exiting never wakes a writer
    # that is asleep rather than writing.
    : > /tmp/out.txt          # exists before the poll loop looks at it
    bash /entrypoint.sh > /tmp/out.txt 2>&1 &
    for _ in $(seq 1800); do grep -q RH-X86-DONE /tmp/out.txt && break; sleep 1; done
    cat /tmp/out.txt
  ' | tee "$WORK/transcript.txt"

echo
if grep -q '^RH-X86-EXIT=0$' "$WORK/transcript.txt"; then
  echo "dry_run: PASS — the committed entry point ran end to end (exit 0)"
  if [ -n "${DRY_RUN_TRANSCRIPT:-}" ]; then
    cp "$WORK/transcript.txt" "$DRY_RUN_TRANSCRIPT"
    echo "dry_run: transcript kept at $DRY_RUN_TRANSCRIPT"
    echo "dry_run: verify_run.py MUST reject it (the mock quote is unsigned) --"
    echo "         that refusal is the negative test."
  fi
else
  echo "dry_run: FAIL — see the transcript above"; exit 1
fi

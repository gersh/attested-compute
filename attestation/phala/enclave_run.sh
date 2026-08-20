#!/bin/bash
# In-CVM entry point for the x86_64 CompCert attested run.
#
# Embedded VERBATIM into docker-compose.yaml by build_compose.py, so these
# bytes are inside the compose hash, inside mr_config_id, and inside the RTMR3
# `compose-hash` event.  Editing the compose by hand breaks that; regenerate.
#
# What it does, in order:
#   1. decode every embedded blob and refuse unless its SHA-256 is the digest
#      the compose names (the digests are of artifacts built by CompCert 3.17
#      for x86_64 on the developer's machine);
#   2. run each artifact and record its exit status and the digest of its
#      stdout -- exit 0 = agrees with the certified constant, 1 = disagrees,
#      anything else = abnormal and NEVER a verdict;
#   3. rebuild the two pilot sources with the enclave's gcc and diff the
#      transcripts against the CompCert binaries' -- a differential check of
#      both toolchains, in the same discipline leancompcert's ports use;
#   4. build a canonical statement naming every digest and every result;
#   5. ask the dstack guest agent for a TDX quote whose report_data is
#      SHA-256(statement) -- so the quote attests THESE results, not merely
#      that some enclave existed;
#   6. print the statement, the quote, /Info and the event log as delimited
#      base64 so they survive `phala cvms logs` (the only channel out).
#
# Failure discipline: every step's status is recorded and the container ALWAYS
# reaches the marker and sleeps.  A container that exits loses its logs, and a
# lost log is a wasted run.

MARKER=RH-X86-EVIDENCE-V1
WORK=/tmp/rhx86
export DEBIAN_FRONTEND=noninteractive

main() {
  set -euo pipefail
  mkdir -p "$WORK"; cd "$WORK"

  echo "== provisioning =="
  # Nothing is installed at run time.  Everything the entry point needs --
  # bash, coreutils, gcc, libc headers and the python3 that signs the receipt
  # -- comes from the base image, which the compose pins by digest, so it is
  # covered by the measurement.
  #
  # An earlier version `apt-get install`ed gcc, libc6-dev and python3 here and
  # then signed the statement with that python3.  The compose is measured;
  # packages fetched at run time are not, so a substituted interpreter could
  # have computed a false statement and signed it with the genuine enclave key,
  # and every downstream check would still have passed.  The image now carries
  # them and `network_mode: none` removes the fetch entirely.
  # See docs/AXIOM_ASSUMPTIONS.md section 3.3.
  for tool in bash gcc python3 sha256sum base64 gzip stat cut; do
    command -v "$tool" >/dev/null \
      || { echo "REFUSED: $tool missing from the base image"; return 1; }
  done
  [ -f /usr/include/stdio.h ] \
    || { echo "REFUSED: no libc headers in the base image"; return 1; }
  echo "gcc: $(gcc --version | head -1)"
  echo "python3: $(python3 --version)"
  echo "uname: $(uname -m) $(uname -s) $(uname -r)"
  echo "provisioning: none -- every tool came from the measured base image"

  echo "== container posture =="
  # Recorded, not assumed.  The hardening lives in the compose, so it is inside
  # the compose hash and the quote attests it; this block is the cross-check
  # that the runtime actually honoured what the compose asked for.  It also
  # records what a non-root `user:` would need: whether the dstack socket and
  # the app-compose mount are reachable by anyone but root.
  echo "  uid=$(id -u) gid=$(id -g) groups=$(id -G | tr ' ' ',')"
  if touch /.rootfs-probe 2>/dev/null; then
    rm -f /.rootfs-probe; echo "  rootfs: WRITABLE (read_only is not in effect)"
  else
    echo "  rootfs: read-only"
  fi
  echo "  /tmp: $(stat -c '%a %U:%G %F' /tmp 2>/dev/null || echo '<absent>')"
  for pth in /var/run/dstack.sock /tapp /dstack /var/run/dstack-host; do
    echo "  $pth: $(stat -c '%a %U:%G %F' "$pth" 2>/dev/null || echo '<absent>')"
  done
  echo "  $(grep -E '^NoNewPrivs' /proc/self/status 2>/dev/null || echo 'NoNewPrivs: <unknown>')"
  echo "  $(grep -E '^CapEff' /proc/self/status 2>/dev/null || echo 'CapEff: <unknown>')"
  # The work directory must be executable, and this is worth its own check
  # rather than being discovered four exit-126s later.  Docker mounts a
  # `--tmpfs` `noexec` unless told otherwise, and every artifact is executed
  # from here; the rehearsal cannot catch it on its own, because there the
  # artifacts run under qemu, which reads them as data.  A `#!` script is
  # enough -- the kernel refuses execve on a noexec mount for scripts too, so
  # this needs no compiler.
  printf '#!/bin/sh\nexit 7\n' > .execprobe && chmod 0700 .execprobe
  probe_rc=0; ./.execprobe || probe_rc=$?
  rm -f .execprobe
  if [ "$probe_rc" -eq 7 ]; then
    echo "  workdir $WORK: executable"
  else
    echo "REFUSED: $WORK is not executable (probe exit=$probe_rc, expected 7)."
    echo "         A tmpfs needs an explicit \`exec\` option; no artifact could run."
    return 1
  fi

  echo "== decoding embedded blobs =="
  # Binaries are gzip'd then base64'd; sources are base64'd.  Each digest is
  # checked against the value the compose names BEFORE anything is executed.
  decode_gz() {  # name expected_sha256 varname
    printf '%s' "${!3}" | base64 -d | gzip -dc > "$1"
    local got; got="$(sha256sum "$1" | cut -d' ' -f1)"
    [ "$got" = "$2" ] || { echo "REFUSED: $1 sha256 $got != $2"; return 1; }
    chmod 0555 "$1"; echo "  $1 sha256=$got ($(stat -c%s "$1") bytes) OK"
  }
  decode_b64() { # name expected_sha256 varname
    printf '%s' "${!3}" | base64 -d > "$1"
    local got; got="$(sha256sum "$1" | cut -d' ' -f1)"
    [ "$got" = "$2" ] || { echo "REFUSED: $1 sha256 $got != $2"; return 1; }
    echo "  $1 sha256=$got ($(stat -c%s "$1") bytes) OK"
  }
  echo "  runner prefix: '${RUNNER:-}' (empty = execute directly)"
  # Indexed, so the entry point does not name any particular artifact.  The
  # deployment manifest decides how many there are and what they are called.
  for i in $(seq 0 $((ARTIFACT_COUNT - 1))); do
    eval "nm=\$A${i}_NAME; sha=\$A${i}_BIN_SHA"
    decode_gz "$nm" "$sha" "A${i}_BIN_GZ_B64"
  done
  for i in $(seq 0 $((SOURCE_COUNT - 1))); do
    eval "nm=\$S${i}_NAME; sha=\$S${i}_SRC_SHA"
    decode_b64 "$nm" "$sha" "S${i}_SRC_B64"
  done

  echo "== running the CompCert x86_64 artifacts =="
  # `run` never aborts the script on a non-zero status: a disagreement is a
  # result to be attested, not an error to be hidden.
  # RUNNER is empty in the enclave (the artifacts are x86_64 and so is the TD).
  # The local dry run sets it to `qemu-x86_64-static -L ...` so that THESE bytes
  # -- the deployed script, not a copy of it -- can be exercised on an aarch64
  # development host.  It is pinned to "" in the generated compose.
  # `run` never aborts on a non-zero status: a disagreement is a RESULT to be
  # attested, not an error to be hidden.  It is also the enclave -- not the
  # artifact -- that decides whether the run succeeded: the expected exit status
  # and the expected transcript digest come from the compose, so they are inside
  # the compose hash and a reader can audit them.  An artifact that exits 0
  # while printing different numbers FAILS here.
  run() { # name expected_exit expected_sha args...
    local name="$1" want_rc="$2" want_sha="$3"; shift 3
    local rc=0
    ${RUNNER:-} ./"$name" "$@" > "$name.out" 2>&1 || rc=$?
    local sha; sha="$(sha256sum "$name.out" | cut -d' ' -f1)"
    local ok=1
    [ "$rc" = "$want_rc" ] || ok=0
    [ "$sha" = "$want_sha" ] || ok=0
    printf '%s %s %s %s\n' "$name" "$rc" "$sha" "$ok" >> results.txt
    if [ "$ok" = 1 ]; then
      echo "  $name exit=$rc  transcript matches the pinned digest  OK"
    else
      echo "  $name exit=$rc (wanted $want_rc)  stdout=$sha (wanted $want_sha)  MISMATCH"
    fi
    tail -2 "$name.out" | sed 's/^/    /'
  }
  : > results.txt
  for i in $(seq 0 $((ARTIFACT_COUNT - 1))); do
    eval "nm=\$A${i}_NAME; xt=\$A${i}_EXPECT_EXIT; xs=\$A${i}_EXPECT_SHA; ag=\$A${i}_ARGS"
    # shellcheck disable=SC2086
    run "$nm" "$xt" "$xs" $ag
  done

  echo "== differential check: enclave gcc vs CompCert =="
  # Same sources, the enclave's own unverified compiler.  Byte-identical
  # transcripts are a genuine cross-check: a wrong-code bug would have to hit
  # both toolchains identically.
  : > diffs.txt
  for i in $(seq 0 $((SOURCE_COUNT - 1))); do
    eval "nm=\$S${i}_NAME"
    gcc -O2 -o "gcc_${nm%.c}" "$nm"
  done
  gdiff() { # gccbin ccompout args...
    local g="$1" ref="$2"; shift 2
    local rc=0
    ./"$g" "$@" > "$g.out" 2>&1 || rc=$?   # native: gcc built this one here
    if cmp -s "$g.out" "$ref"; then
      printf '%s 1\n' "$g" >> diffs.txt; echo "  $g: transcript IDENTICAL to CompCert"
    else
      printf '%s 0\n' "$g" >> diffs.txt
      # "DIFFERS" alone is not actionable -- it cannot distinguish a real
      # wrong-code divergence from the gcc binary having failed to run at all,
      # and those call for opposite responses.  Say which.
      echo "  $g: DIFFERS from CompCert (exit=$rc," \
           "$(stat -c%s "$g.out" 2>/dev/null || echo 0) vs" \
           "$(stat -c%s "$ref" 2>/dev/null || echo 0) bytes)"
      echo "    gcc first line: $(head -c 200 "$g.out" | head -1)"
      echo "    ref first line: $(head -c 200 "$ref" | head -1)"
    fi
  }
  for i in $(seq 0 $((SOURCE_COUNT - 1))); do
    eval "nm=\$S${i}_NAME; ag=\$S${i}_ARGS"
    # shellcheck disable=SC2086
    gdiff "gcc_${nm%.c}" "${nm%.c}.out" $ag
  done

  echo "== staging the signing modules =="
  # A bare package marker on purpose: a previous image's tg_verifier/__init__.py
  # imported submodules and killed the deployment inside the prelude.
  mkdir -p tg_verifier && : > tg_verifier/__init__.py
  for pair in "phala_tdx_receipt.py:$RECEIPT_MOD_B64:$RECEIPT_MOD_SHA" \
              "compcert_run_receipt.py:$RUNRECEIPT_MOD_B64:$RUNRECEIPT_MOD_SHA" \
              "compcert_run_spec.py:$RUNSPEC_MOD_B64:$RUNSPEC_MOD_SHA"; do
    name="${pair%%:*}"; rest="${pair#*:}"; b64="${rest%%:*}"; want="${rest##*:}"
    printf '%s' "$b64" | base64 -d > "tg_verifier/$name"
    got="$(sha256sum "tg_verifier/$name" | cut -d' ' -f1)"
    [ "$got" = "$want" ] || { echo "REFUSED: tg_verifier/$name sha256 $got != $want"; return 1; }
    echo "  tg_verifier/$name sha256=$got OK"
  done

  echo "== locating the app-compose document inside the TD =="
  # `compose_hash` is the SHA-256 of the app-compose DOCUMENT's raw bytes.  The
  # Cloud API's JSON view of that document is NOT byte-faithful (its key set and
  # ordering differ), so a hash reconstructed outside cannot be compared -- 224
  # candidate re-serializations were tried and none matched.  Reading the raw
  # bytes here, inside the measured VM, is what makes the binding checkable:
  # the digest goes into the statement, hence into report_data, hence into the
  # quote.  A miss is diagnostic, not fatal -- the listings below say why.
  : > appcompose-search.txt
  for d in /tapp /dstack /dstack-host /var/run/dstack /run/dstack; do
    printf '%s: %s\n' "$d" "$(ls -A "$d" 2>/dev/null | tr '\n' ' ' || echo '<absent>')" \
      >> appcompose-search.txt
  done
  cat appcompose-search.txt | sed 's/^/  /'
  APP_COMPOSE=""
  for c in /tapp/app-compose.json /dstack/app-compose.json \
           /dstack-host/app-compose.json /var/run/dstack/app-compose.json \
           /run/dstack/app-compose.json; do
    [ -f "$c" ] && { APP_COMPOSE="$c"; break; }
  done
  if [ -n "$APP_COMPOSE" ]; then
    cp "$APP_COMPOSE" app-compose.json
    echo "  found: $APP_COMPOSE ($(stat -c%s app-compose.json) bytes)"
  else
    echo "  NOT FOUND -- the compose binding will be reported as unavailable"
  fi

  echo "== dstack guest agent =="
  python3 - <<'PY'
import base64, hashlib, http.client, json, os, socket, sys, pathlib

WORK = pathlib.Path("/tmp/rhx86")
DOMAIN = "sparkinterval.attested-compcert-run.v1"
CANDIDATES = ("/var/run/dstack.sock", "/var/run/dstack/dstack.sock", "/run/dstack/dstack.sock")

class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=60.0):
        super().__init__("localhost", timeout=timeout); self.path_ = path
    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout); s.connect(self.path_); self.sock = s

def call(sock, method, payload):
    body = json.dumps(payload).encode()
    c = UnixHTTPConnection(sock)
    try:
        c.request("POST", "/" + method, body=body, headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Content-Length": str(len(body)), "Host": "dstack"})
        r = c.getresponse(); raw = r.read(4 * 1024 * 1024)
        if r.status != 200:
            raise SystemExit(f"guest agent {method} -> HTTP {r.status}: {raw[:300]!r}")
    finally:
        c.close()
    d = json.loads(raw.decode())
    if isinstance(d, dict) and set(d) == {"error"}:
        raise SystemExit(f"guest agent {method} failed: {d['error']}")
    return d

sock = next((p for p in CANDIDATES if pathlib.Path(p).is_socket()), None)
if sock is None:
    raise SystemExit("no dstack socket found; candidates: " + ", ".join(CANDIDATES))
print(f"  socket: {sock}")

info = call(sock, "Info", {})
app_id = info.get("app_id", ""); compose_hash = info.get("compose_hash", "")
print(f"  app_id={app_id}\n  compose_hash={compose_hash}")

# The event log must come from Info's tcb_info: GetQuote returns the same
# entries with every `digest` field empty, which would fail a digest check.
tcb = info.get("tcb_info")
if isinstance(tcb, str):
    tcb = json.loads(tcb)
event_log = tcb.get("event_log") if isinstance(tcb, dict) else None
if isinstance(event_log, str):
    event_log = json.loads(event_log)
if not isinstance(event_log, list):
    raise SystemExit("tcb_info carries no usable event log")
print(f"  event log entries: {len(event_log)}")

# The signing key.  A DEDICATED path: GetKey derives the same 32 bytes for
# every algorithm and separates only on `path`, so sharing a path across
# algorithms would be key reuse (upstream sdk/curl/api.md says so explicitly).
sys.path.insert(0, str(WORK))
from tg_verifier import compcert_run_receipt as rcpt
from tg_verifier.phala_tdx_receipt import public_key_hex

key_response = call(sock, "GetKey", {"path": rcpt.KEY_PATH,
                                     "purpose": rcpt.KEY_PURPOSE})
private_key = rcpt.scalar_from_key_material(key_response["key"])
enclave_public_key = public_key_hex(private_key)
signature_chain = [c for c in key_response.get("signature_chain", [])
                   if isinstance(c, str)]
print(f"  enclave public key: {enclave_public_key[:24]}… "
      f"({len(signature_chain)} chain entries)")

# SHA-256 of each artifact's C, as the compose declares it.  Named per
# artifact so a receipt cannot claim a C digest the compose never pinned.
# SHA-256 of each artifact's C, as the compose declares it.  Read from the
# indexed environment rather than a hardcoded table, so the entry point stays
# free of any particular deployment's artifact names.
source_digests = {}
for _i in range(int(os.environ.get("ARTIFACT_COUNT", "0"))):
    _n = os.environ.get(f"A{_i}_NAME", "")
    _d = os.environ.get(f"A{_i}_C_SHA", "")
    if _n:
        source_digests[_n] = _d

results = [l.split() for l in (WORK / "results.txt").read_text().split("\n") if l.strip()]
diffs = [l.split() for l in (WORK / "diffs.txt").read_text().split("\n") if l.strip()]

def sha_file(p):
    return hashlib.sha256((WORK / p).read_bytes()).hexdigest()

# Canonical statement.  Every field is a fixed-shape token -- a digest, a small
# integer, or a name from the fixed set above -- so no value can be mistaken
# for another field.  Variable-length outputs appear only as digests.
lines = [DOMAIN, f"compose_hash={compose_hash}", f"app_id={app_id}",
         f"instance_id={info.get('instance_id','')}",
         f"enclave_public_key={enclave_public_key}"]
for name, rc, out_sha, ok in results:
    lines.append(f"artifact={name} binary_sha256={sha_file(name)} exit={rc} "
                 f"stdout_sha256={out_sha} matched_pinned_expectation={ok}")
for name, ident in diffs:
    lines.append(f"gcc_differential={name} identical={ident}")
for _i in range(int(os.environ.get("SOURCE_COUNT", "0"))):
    src = os.environ.get(f"S{_i}_NAME", "")
    if not src:
        continue
    lines.append(f"source={src} sha256={sha_file(src)}")

# The measured document, read inside the TD.  Two digests: the raw bytes (which
# must equal compose_hash, and therefore mr_config_id) and the docker_compose_file
# it carries (which must equal this repository's docker-compose.yaml).  Both are
# committed here, so the quote attests them.
doc_path = WORK / "app-compose.json"
if doc_path.exists():
    doc_raw = doc_path.read_bytes()
    doc_sha = hashlib.sha256(doc_raw).hexdigest()
    try:
        inner = json.loads(doc_raw)["docker_compose_file"].encode()
        inner_sha = hashlib.sha256(inner).hexdigest()
        inner_len = str(len(inner))
    except Exception:
        inner_sha, inner_len = "unavailable", "0"
    lines.append(f"app_compose_sha256={doc_sha} self_consistent="
                 f"{'1' if doc_sha == compose_hash else '0'}")
    lines.append(f"docker_compose_file_sha256={inner_sha} bytes={inner_len}")
    print(f"  app-compose raw sha256={doc_sha} "
          f"(== compose_hash: {doc_sha == compose_hash})")
    print(f"  docker_compose_file sha256={inner_sha} ({inner_len} bytes)")
else:
    lines.append("app_compose_sha256=unavailable self_consistent=0")
statement = "\n".join(lines) + "\n"
(WORK / "statement.txt").write_text(statement)
digest = hashlib.sha256(statement.encode()).hexdigest()
print(f"  statement sha256={digest}")

# The quote commits to the signing key AND the results together.  Either alone
# would leave the other unbound: a key with no results says nothing happened, and
# results with no key let anyone sign them.
report_data = rcpt.report_data_hash(enclave_public_key_hex=enclave_public_key,
                                    statement_sha256=digest)
print(f"  report_data = H(pubkey, statement) = {report_data}")
# GetQuote zero-pads on the right to 64 bytes; send the padded value so the
# echo comparison is exact.
padded = report_data + "00" * 32
q = call(sock, "GetQuote", {"report_data": padded})
quote_hex = q.get("quote", "")
echoed = (q.get("report_data") or "").lower()
if echoed and echoed != padded:
    raise SystemExit("guest agent echoed report data that is not this run's commitment")
quote = bytes.fromhex(quote_hex)
if len(quote) < 1024:
    raise SystemExit(f"implausibly short quote ({len(quote)} bytes)")
(WORK / "tdx-quote.bin").write_bytes(quote)
print(f"  quote: {len(quote)} bytes, report_data echo OK")
# Local sanity: the quote really carries our commitment at offset 568.
if quote[568:600].hex() != report_data or quote[600:632] != bytes(32):
    raise SystemExit("the quote's report_data is not this run's commitment")
print("  quote report_data == H(pubkey, statement)  (offset 568) OK")

# The event log is emitted as its own block; carrying it twice would roughly
# double the evidence for nothing, and the log retrieval caps near 64 KiB.
info_slim = dict(info)
if isinstance(info_slim.get("tcb_info"), (dict, str)):
    tcb_slim = dict(tcb); tcb_slim["event_log"] = "<emitted separately>"
    info_slim["tcb_info"] = tcb_slim
# ---- one signed receipt per artifact -------------------------------------
# Signed here rather than through dstack's own /Sign: that endpoint offers
# ed25519, secp256k1 and secp256k1_prehashed (sdk/curl/api.md), and the Lean
# side has a P-256 verifier and no other.  The key material is the same either
# way -- GetKey's `algorithm` only reinterprets the same 32 bytes.
quote_sha256 = hashlib.sha256(quote).hexdigest()
issued_at = info.get("instance_id", "")  # stable per instance; no clock in here
receipts = []
for name, rc, out_sha, ok in results:
    spec_fields = {
        "algorithm_id": f"compcert-run-v1:{name}",
        "algorithm_hash": "",          # filled below from the spec mirror
        "input_hash": "",
        "result": out_sha,
        "output_hash": hashlib.sha256(out_sha.encode()).hexdigest(),
        "matched_pinned_expectation": ok,
        "app_id": app_id,
        "compose_hash": compose_hash,
        "app_compose_sha256": doc_sha if doc_path.exists() else "unavailable",
        "docker_compose_file_sha256": inner_sha if doc_path.exists() else "unavailable",
        "tdx_quote_sha256": quote_sha256,
        "report_data_sha256": report_data,
        "issued_at": issued_at,
    }
    # algorithm_hash / input_hash come from the same canonical definition Lean
    # rebuilds, so a receipt cannot name an artifact Lean would not recognise.
    from tg_verifier import compcert_run_spec as crs
    # Both digests, and each the right one.  An earlier version passed the
    # BINARY hash as `emitted_c_digest`, so the field's name and the alignment
    # story it supports were quietly false.  The C digest comes from the
    # compose (it is what the sources decode to); the binary digest is what
    # the enclave just verified before executing.
    spec = crs.CompCertRunSpec(
        program_name=name,
        emitted_c_digest=source_digests.get(name, sha_file(name)),
        binary_digest=sha_file(name),
        toolchain="CompCert 3.17 x86_64-linux", accepted_value=0)
    identity = spec.statement_identity_fields()
    spec_fields["algorithm_hash"] = identity["algorithm_hash"]
    spec_fields["input_hash"] = identity["input_hash"]
    receipts.append(rcpt.sign(private_key, spec_fields, signature_chain))
    print(f"  signed {name}: {receipts[-1]['receipt_sha256'][:16]}…")

(WORK / "receipts.json").write_text(json.dumps(receipts, indent=1, sort_keys=True))

(WORK / "dstack-info.json").write_text(json.dumps(info_slim, indent=1, sort_keys=True))
(WORK / "dstack-event-log.json").write_text(json.dumps(event_log, indent=1))
PY

  echo "== evidence =="
  # Delimited base64 so `phala cvms logs` can carry it out; the marker is not
  # line-anchored because the log tool prefixes timestamps.
  emit() {
    local f="$1" sha bytes
    sha="$(sha256sum "$f" | cut -d' ' -f1)"; bytes="$(stat -c%s "$f")"
    echo "$MARKER BEGIN {\"name\":\"$f\",\"sha256\":\"$sha\",\"bytes\":$bytes}"
    base64 -w 200 "$f" | sed "s/^/$MARKER DATA /"
    echo "$MARKER END {\"name\":\"$f\",\"sha256\":\"$sha\"}"
  }
  emit statement.txt
  emit tdx-quote.bin
  emit dstack-info.json
  emit dstack-event-log.json
  emit receipts.json
  emit appcompose-search.txt
  # The RAW measured app-compose document.  Its digest is already committed in
  # the statement, so emitting the bytes adds no trust -- it adds AUDITABILITY:
  # a third party can recompute sha256(document) == compose_hash == the quote's
  # mr_config_id themselves, instead of taking this script's arithmetic on
  # faith.  ~117 KB; the log carried 243 KB comfortably.
  # `[ -f x ] && emit x` here would be a trap: as the LAST command under
  # `set -e`, a false test makes the whole AND-list fail and bash exits the
  # script -- before the marker, so a deploy would poll for twenty minutes
  # and give up with the CVM still billing.  dry_run.sh caught exactly that.
  if [ -f app-compose.json ]; then emit app-compose.json; fi
}

# Run in a SUBSHELL.  `set -e` inside main is not function-scoped: a refusal --
# a digest mismatch, say -- would otherwise exit the whole script before the
# marker, the container would stop, and `phala cvms logs` returns nothing for a
# container that has exited.  The refusal would be invisible, which is the worst
# possible way for a check to fail.  A subshell confines the exit; the parent
# keeps the status, prints the marker, and stays alive.
( main )
rc=$?
echo "RH-X86-EXIT=$rc"
echo "RH-X86-DONE"
# Stay alive: a container that exits takes its logs with it.
sleep infinity

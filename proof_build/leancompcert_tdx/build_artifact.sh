#!/bin/bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Emit, compile, and pin one leancompcert artifact for a Phala TDX campaign.
#
# Run this on a reviewed build host, NOT inside the campaign image: the image
# must contain reviewed bytes, not a compiler.  Everything this script writes
# into `--out-dir` is what the image `COPY`s and what
# `tools/tg_leancompcert_artifact_pin.py` hashes.
#
# Usage:
#   proof_build/leancompcert_tdx/build_artifact.sh \
#       --leancompcert ~/leancompcert \
#       --emit-command emit-mertens-cert-c \
#       --name mertens-odd-floor-sum \
#       --program MertensCert.oddFloorSum \
#       --compcert-version 3.17 \
#       --out-dir build/mertens
#
# `--compcert-version` is required and is NOT sniffed from the binary.  Two
# reasons.  It is a trust statement -- it names the compiler whose Coq theorem
# the campaign relies on -- and it belongs to the operator who reviewed that
# installation, not to a string scraped at build time.  (Practically: on this
# development host `ccomp --version` hangs, so scraping it is not even
# reliable.)
#
# Requires:
#   * a leancompcert checkout that builds `lake exe lean-compcert`
#   * `ccomp` CONFIGURED FOR THE TARGET THE ENCLAVE RUNS, i.e. x86_64-linux.
#     Intel TDX is x86 only.  A CompCert installation reports its target in
#     `$(dirname $(which ccomp))/../share/compcert.ini`; this script refuses
#     to proceed on a mismatch rather than silently producing an artifact that
#     cannot run in the CVM.

set -euo pipefail
IFS=$'\n\t'

LEANCOMPCERT=""
EMIT_COMMAND=""
NAME=""
PROGRAM=""
OUT_DIR=""
CCOMP_VERSION=""
EXPECT_TARGET="${TG_COMPCERT_TARGET:-x86_64}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --leancompcert) LEANCOMPCERT="$2"; shift 2 ;;
    --emit-command) EMIT_COMMAND="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --program) PROGRAM="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --compcert-version) CCOMP_VERSION="$2"; shift 2 ;;
    --expect-target) EXPECT_TARGET="$2"; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

die() { printf '%s\n' "$*" >&2; exit 1; }
for v in LEANCOMPCERT EMIT_COMMAND NAME PROGRAM OUT_DIR CCOMP_VERSION; do
  [ -n "${!v}" ] || die "missing --${v,,}"
done

command -v ccomp >/dev/null || die "ccomp not on PATH"
CCOMP_INI="$(dirname "$(command -v ccomp)")/../share/compcert.ini"
[ -f "${CCOMP_INI}" ] || die "cannot find compcert.ini next to ccomp"
CCOMP_ARCH="$(sed -n 's/^arch=//p' "${CCOMP_INI}")"
[ -n "${CCOMP_ARCH}" ] || die "compcert.ini names no arch"

if [ "${CCOMP_ARCH}" != "${EXPECT_TARGET}" ]; then
  die "REFUSED: ccomp targets '${CCOMP_ARCH}' but the enclave needs \
'${EXPECT_TARGET}'.  Intel TDX is x86_64 only; build the artifact on a host \
whose CompCert was configured with './configure x86_64-linux', or pass \
--expect-target to acknowledge a deliberate non-TDX target."
fi

mkdir -p "${OUT_DIR}"
C_FILE="${OUT_DIR}/artifact.c"
BIN_FILE="${OUT_DIR}/artifact"

# 1. Emit.  The emitter is a pure function of the Lean `Program`; the same
#    checkout must produce byte-identical C on every host.
( cd "${LEANCOMPCERT}" && lake exe lean-compcert "${EMIT_COMMAND}" "$(readlink -f "${C_FILE}")" )
[ -s "${C_FILE}" ] || die "emitter produced no output"

# 2. Refuse a non-standalone artifact.  `#include <lean/lean.h>` is emitted
#    even when nothing in the file calls the Lean runtime; the include is
#    dropped here so the artifact needs no Lean headers and no Lean runtime.
#    If any `lean_*` CALL survives, the artifact is genuinely not standalone
#    and must not be packaged.
if grep -q 'lean_' <(grep -v '#include <lean/lean.h>' "${C_FILE}"); then
  die "REFUSED: emitted C calls the Lean runtime; not a standalone artifact"
fi
grep -v '#include <lean/lean.h>' "${C_FILE}" > "${C_FILE}.standalone"
mv "${C_FILE}.standalone" "${C_FILE}"

# 3. Compile.  Static on purpose: the campaign's behaviour must not depend on
#    whichever libc the base image happens to ship.
ccomp -static -I"${LEANCOMPCERT}/runtime/include" -o "${BIN_FILE}" "${C_FILE}"
chmod 0555 "${BIN_FILE}"

# 4. Self-check on the build host.  The artifact's `main` returns 0 exactly
#    when the computed value equals the certified constant, so a build-host
#    run that exits non-zero means the certificate is wrong and there is
#    nothing to attest.  Skipped when cross-compiling.
if [ "${CCOMP_ARCH}" = "$(uname -m | sed 's/aarch64/aarch64/;s/x86_64/x86_64/')" ]; then
  if "${BIN_FILE}"; then
    printf 'build-host self-check: PASS\n'
  else
    die "REFUSED: artifact exits non-zero on the build host; the certified \
value does not hold and there is nothing to attest"
  fi
else
  printf 'build-host self-check: SKIPPED (cross-compiled for %s)\n' "${CCOMP_ARCH}"
fi

# 5. Pin.  This is the step that makes `algorithmHash` a hash of code.
python3 "$(dirname "$0")/../../tools/tg_leancompcert_artifact_pin.py" \
  --name "${NAME}" \
  --program "${PROGRAM}" \
  --emitter "lake exe lean-compcert ${EMIT_COMMAND}" \
  --emitted-c "${C_FILE}" \
  --binary "${BIN_FILE}" \
  --compcert-version "${CCOMP_VERSION}" \
  --target "${CCOMP_ARCH}-linux" \
  --link static \
  --json > "${OUT_DIR}/artifact-pin.json"

printf 'emitted C   : %s (%s bytes)\n' "${C_FILE}" "$(stat -c%s "${C_FILE}")"
printf 'executable  : %s (%s bytes)\n' "${BIN_FILE}" "$(stat -c%s "${BIN_FILE}")"
printf 'pin         : %s\n' "${OUT_DIR}/artifact-pin.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('algorithmHash:', d['algorithm_hash'])" \
  "${OUT_DIR}/artifact-pin.json"

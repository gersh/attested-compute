#!/usr/bin/env bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Deterministic native build for the attested-provenance prototype.
#
# This is the single build definition used by BOTH sides of the provenance
# layer:
#
#   - `.github/workflows/build-provenance.yml` runs it and attests the
#     resulting digests with `actions/attest-build-provenance`; and
#   - a third-party rebuilder runs the same command on the same commit inside
#     the same digest-pinned container and compares `build-manifest.json`.
#
# If the two manifests disagree on any `sha256`, the attestation and the
# rebuild are describing different bytes and no provenance claim survives.
#
# The script builds only the x86-64 CPU checker closure and a deterministic
# source-closure tarball.  It does not build CUDA device code, does not build
# Lean, does not run a campaign, and produces no execution evidence whatsoever.
#
# Usage:
#   tools/reproduce_attested_build.sh --output-dir DIR [--allow-dirty]
#                                     [--skip-pure-entry]

set -o errexit
set -o nounset
set -o pipefail

REPOSITORY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR=""
ALLOW_DIRTY=0
SKIP_PURE_ENTRY=0

die() {
  echo "reproduce_attested_build: $*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-dir)
      [ "$#" -ge 2 ] || die "--output-dir requires a value"
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --skip-pure-entry)
      SKIP_PURE_ENTRY=1
      shift
      ;;
    --help|-h)
      sed -n '3,30p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[ -n "${OUTPUT_DIR}" ] || die "--output-dir is required"
[ ! -e "${OUTPUT_DIR}" ] || die "refusing to reuse existing output directory ${OUTPUT_DIR}"

cd "${REPOSITORY_ROOT}"

command -v git >/dev/null 2>&1 || die "git is required"
command -v make >/dev/null 2>&1 || die "make is required"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required"
command -v gzip >/dev/null 2>&1 || die "gzip is required"

COMMIT="$(git rev-parse HEAD)"
DIRTY="$(git status --porcelain)"
if [ -n "${DIRTY}" ] && [ "${ALLOW_DIRTY}" -eq 0 ]; then
  die "working tree is dirty; a provenance build must run from a clean commit"
fi
WORKTREE_CLEAN=true
[ -z "${DIRTY}" ] || WORKTREE_CLEAN=false

# Deterministic timestamp source.  Everything that could otherwise embed
# "now" is derived from the commit instead.
SOURCE_DATE_EPOCH="$(git log -1 --pretty=%ct)"
export SOURCE_DATE_EPOCH
export LC_ALL=C
export TZ=UTC

mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd -- "${OUTPUT_DIR}" && pwd)"
mkdir "${OUTPUT_DIR}/artifacts"
mkdir "${OUTPUT_DIR}/toolchain"

# ---------------------------------------------------------------------------
# Toolchain identity.  These values are recorded, not trusted: a rebuild that
# used a different compiler will simply fail the digest comparison.
# ---------------------------------------------------------------------------

HOST_CC="${CC:-cc}"
command -v "${HOST_CC}" >/dev/null 2>&1 || die "missing host compiler ${HOST_CC}"
HOST_CC_PATH="$(command -v "${HOST_CC}")"
HOST_CC_TARGET="$("${HOST_CC}" -dumpmachine)"

# The Makefile deliberately refuses to emit a host-architecture image for the
# proof-facing pure-entry target.  Resolve an x86-64 driver explicitly and
# keep that guard intact rather than weakening it.
X86_64_CC=""
for candidate in x86_64-linux-gnu-gcc x86_64-linux-gnu-gcc-13 x86_64-linux-gnu-gcc-12; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    X86_64_CC="${candidate}"
    break
  fi
done
if [ -z "${X86_64_CC}" ] && [ "${HOST_CC_TARGET#x86_64-}" != "${HOST_CC_TARGET}" ]; then
  X86_64_CC="${HOST_CC}"
fi

{
  echo "host_cc_path=${HOST_CC_PATH}"
  echo "host_cc_target=${HOST_CC_TARGET}"
  "${HOST_CC}" --version
} > "${OUTPUT_DIR}/toolchain/host_cc.txt"

if [ -n "${X86_64_CC}" ]; then
  {
    echo "x86_64_cc_path=$(command -v "${X86_64_CC}")"
    echo "x86_64_cc_target=$("${X86_64_CC}" -dumpmachine)"
    "${X86_64_CC}" --version
  } > "${OUTPUT_DIR}/toolchain/x86_64_cc.txt"
fi

for tool in as ld; do
  if command -v "${tool}" >/dev/null 2>&1; then
    "${tool}" --version > "${OUTPUT_DIR}/toolchain/${tool}.txt" 2>&1 || true
  fi
done

# ---------------------------------------------------------------------------
# Native build.
# ---------------------------------------------------------------------------

make -C cpu_checker/sqrt218 clean >/dev/null

make -C cpu_checker/sqrt218 sqrt218_cpu_checker_v2 sqrt218_cpu_checker_kat \
  > "${OUTPUT_DIR}/toolchain/make_host.log" 2>&1

PURE_ENTRY_BUILT=false
if [ "${SKIP_PURE_ENTRY}" -eq 0 ] && [ -n "${X86_64_CC}" ]; then
  if make -C cpu_checker/sqrt218 X86_64_CC="${X86_64_CC}" pure-entry-x86_64 \
      > "${OUTPUT_DIR}/toolchain/make_pure_entry.log" 2>&1; then
    PURE_ENTRY_BUILT=true
  else
    cat "${OUTPUT_DIR}/toolchain/make_pure_entry.log" >&2
    die "pure-entry x86-64 build failed"
  fi
fi

# The KAT is the build-time self-check.  A build whose own known-answer test
# fails must never be attested.
(cd cpu_checker/sqrt218 && ./sqrt218_cpu_checker_kat) \
  > "${OUTPUT_DIR}/toolchain/kat.log" 2>&1

cp cpu_checker/sqrt218/sqrt218_cpu_checker_v2 "${OUTPUT_DIR}/artifacts/"
cp cpu_checker/sqrt218/sqrt218_cpu_checker_kat "${OUTPUT_DIR}/artifacts/"
if [ "${PURE_ENTRY_BUILT}" = true ]; then
  cp cpu_checker/sqrt218/sqrt218_cpu_checker_pure_entry_x86_64_v2 \
    "${OUTPUT_DIR}/artifacts/"
fi

make -C cpu_checker/sqrt218 clean >/dev/null

# ---------------------------------------------------------------------------
# Deterministic source closure for the Python worker/verifier implementation.
#
# The replication layer runs Python code, not only compiled binaries, so the
# Python closure needs the same commit-bound identity.  `git archive` is
# content-addressed from the tree; `gzip -n` keeps the container header free
# of a wall-clock timestamp.
# ---------------------------------------------------------------------------

git archive --format=tar "${COMMIT}" \
    tg_verifier tools schemas cpu_checker profiles \
  | gzip -9 -n > "${OUTPUT_DIR}/artifacts/sparkinterval-worker-closure.tar.gz"

# ---------------------------------------------------------------------------
# Manifest.
#
# Written with POSIX text tools only.  The build container therefore needs no
# interpreter beyond the shell, and the manifest bytes cannot drift with a
# Python version.  Key order is fixed and artifact rows are sorted by name, so
# two honest rebuilds produce byte-identical manifests.
# ---------------------------------------------------------------------------

MANIFEST="${OUTPUT_DIR}/build-manifest.json"

{
  echo '{'
  echo '  "artifacts": ['
  first=1
  for artifact in $(find "${OUTPUT_DIR}/artifacts" -maxdepth 1 -type f \
      -printf '%f\n' | LC_ALL=C sort); do
    digest="$(sha256sum "${OUTPUT_DIR}/artifacts/${artifact}" | cut -d' ' -f1)"
    size="$(wc -c < "${OUTPUT_DIR}/artifacts/${artifact}" | tr -d ' ')"
    [ "${first}" -eq 1 ] || echo '    },'
    first=0
    echo '    {'
    echo "      \"name\": \"${artifact}\","
    echo "      \"sha256\": \"${digest}\","
    echo "      \"size_bytes\": ${size}"
  done
  [ "${first}" -eq 1 ] || echo '    }'
  echo '  ],'
  echo '  "authority": {'
  echo '    "attests_that_a_computation_ran": false,'
  echo '    "authorizes_lean_theorem": false,'
  echo '    "establishes_hardware_evidence": false,'
  echo '    "identifies_source_commit_of_binaries": true'
  echo '  },'
  echo "  \"commit\": \"${COMMIT}\","
  echo "  \"host_compiler_target\": \"${HOST_CC_TARGET}\","
  echo '  "kind": "sparkinterval.attested-provenance-build-manifest.v1",'
  echo "  \"pure_entry_x86_64_built\": ${PURE_ENTRY_BUILT},"
  echo '  "schema_version": 1,'
  echo "  \"source_date_epoch\": ${SOURCE_DATE_EPOCH},"
  echo "  \"worktree_clean\": ${WORKTREE_CLEAN}"
  echo '}'
} > "${MANIFEST}"

cat "${MANIFEST}"

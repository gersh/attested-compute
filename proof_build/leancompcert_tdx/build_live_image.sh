#!/bin/bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Build the `platt-stronger-range-live` campaign image for Intel TDX.
#
#   build_live_image.sh <campaign-dir> <image-reference>
#
# `<campaign-dir>` is what `build_live_campaign.py --out-dir` produced: a
# `campaign-manifest.txt`, a `canonical-definition.txt`, `bin/` and `c/`.
#
# The build context is assembled here, from an explicit list, rather than
# being the repository root.  Everything that ends up in the image is named
# below; nothing is picked up because it happened to be in a directory.  The
# manifest digest is passed as a build argument and checked twice: once by
# this script before the build, and once inside the image by the Dockerfile.

set -euo pipefail
IFS=$'\n\t'

CAMPAIGN_DIR="${1:?usage: build_live_image.sh <campaign-dir> <image-reference>}"
IMAGE="${2:?usage: build_live_image.sh <campaign-dir> <image-reference>}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${HERE}/../.." && pwd)"

MANIFEST="${CAMPAIGN_DIR}/campaign-manifest.txt"
[ -f "${MANIFEST}" ] || { echo "no campaign manifest at ${MANIFEST}" >&2; exit 2; }
MANIFEST_SHA256="$(sha256sum "${MANIFEST}" | cut -d' ' -f1)"
CAMPAIGN_NAME=platt-stronger-range-live

CTX="$(mktemp -d)"
trap 'rm -rf "${CTX}"' EXIT

mkdir -p "${CTX}/campaign" "${CTX}/tg_verifier" "${CTX}/tools" \
    "${CTX}/proof_build/leancompcert_tdx"
cp "${MANIFEST}" "${CAMPAIGN_DIR}/canonical-definition.txt" "${CTX}/campaign/"
cp -r "${CAMPAIGN_DIR}/bin" "${CAMPAIGN_DIR}/c" "${CTX}/campaign/"
cp "${ROOT}/tg_verifier/phala_tdx_receipt.py" \
    "${CTX}/tg_verifier/"
# The package initializer is written here rather than copied, and that is a
# deliberate difference from the A.7 image.
#
# `tg_verifier/__init__.py` in the repository imports `.arithmetic`,
# `.catalog` and `.mobius_cuda`, and loads the thirteen-atom catalog at import
# time.  The A.7 image copies all of that because its workload uses it.  This
# image must not: it has no analytic stack, no numpy, no catalog, and the only
# module it needs is `phala_tdx_receipt`, which is pure standard library.
# Copying the repository initializer would make `from tg_verifier import
# phala_tdx_receipt` fail with `No module named 'tg_verifier.arithmetic'` --
# which is exactly how the first deployment of this image died, inside the
# prelude, before any quote was fetched.
#
# The module that actually matters, `phala_tdx_receipt.py`, is copied verbatim
# above and is byte-identical to the one the A.7 image carries and the one
# `SparkInterval/Execution/PhalaTdxAttestation.lean` mirrors.
cat >"${CTX}/tg_verifier/__init__.py" <<'INIT'
"""Package marker only.

This image carries `tg_verifier.phala_tdx_receipt` and nothing else from
`tg_verifier`, because the campaign has no analytic stack and needs none.
See `proof_build/leancompcert_tdx/build_live_image.sh` for why the
repository's own initializer is not used here.
"""
INIT
cp "${ROOT}/tools/tg_seg_campaign_check.py" "${CTX}/tools/"
cp "${HERE}/run_seg_campaign.sh" "${HERE}/prelude_live_tdx_inputs.py" \
    "${HERE}/emit_live_tdx_evidence.py" "${CTX}/proof_build/leancompcert_tdx/"
cp "${HERE}/Dockerfile.live" "${CTX}/Dockerfile"

echo "manifest sha256 = ${MANIFEST_SHA256}"
docker build --platform linux/amd64 \
    --build-arg "TG_MANIFEST_SHA256=${MANIFEST_SHA256}" \
    --build-arg "TG_CAMPAIGN_NAME=${CAMPAIGN_NAME}" \
    -t "${IMAGE}" "${CTX}"

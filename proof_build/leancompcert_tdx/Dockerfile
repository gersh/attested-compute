# syntax=docker/dockerfile:1.7
#
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Campaign image for a leancompcert CompCert artifact, packaged to run as a
# dstack application inside an Intel TDX confidential VM on Phala Cloud.
#
# This is the *campaign* half only.  It is a sibling of
# `proof_build/ch25_a7_phala_tdx/Dockerfile`, not a replacement for it: that
# image also carries the attestation prelude (dstack key derivation, GetQuote,
# `dcap-qvl` appraisal, RTMR3 event-log replay, RFC-6979 P-256 signing), and
# none of that is expressible as a leancompcert `Program`.  See
# `docs/COMPCERT_ARTIFACT_UNDER_TDX.md` for the split and for what the two
# services cost.
#
# What changes versus the A.7 image
# ---------------------------------
#   dropped:  the python-flint 0.9.0 wheel (FLINT/Arb), its download and
#             digest re-verification, and the analytic half of `tg_verifier`
#   dropped:  `PYTHON_FLINT_0_9_UPSTREAM.json` and the wheel staging in the
#             entry point
#   added:    exactly one file -- the CompCert-compiled artifact, statically
#             linked, named by its SHA-256
#
# The artifact is COPIED IN, never built here.  Building it inside the image
# would put `ccomp`, the Lean toolchain, and a C library into the measured
# image, and would make the image digest depend on a compiler run rather than
# on reviewed bytes.  The artifact is built on a reviewed host by
# `proof_build/leancompcert_tdx/build_artifact.sh`, its digest is recorded by
# `tools/tg_leancompcert_artifact_pin.py`, and that digest is what the
# registry's `algorithmHash` commits to.
#
# The image is deliberately x86_64: Intel TDX is an x86 feature, so the
# artifact must be emitted by an x86_64-configured CompCert.  See the
# "cross-compilation" section of the design note; this is currently the one
# hard blocker on the aarch64 development host.

FROM --platform=linux/amd64 docker.io/library/debian@sha256:REPLACE-WITH-REVIEWED-DEBIAN-SLIM-DIGEST

# `TG_ARTIFACT_SHA256` is the SHA-256 of the statically linked executable that
# `ccomp` produced from the emitted C.  It is checked at build time and again
# at run time.  It is the same literal that appears as `binary-sha256` in the
# registered algorithm's `canonicalDefinition`, so a substituted artifact
# changes `algorithmHash` and the Lean acceptance check refuses.
ARG TG_ARTIFACT_SHA256=REPLACE-WITH-64-HEX-ARTIFACT-DIGEST
ARG TG_ARTIFACT_NAME=REPLACE-WITH-ARTIFACT-NAME

RUN install -d -m 0755 /opt/sparkinterval /opt/sparkinterval/bin \
        /opt/sparkinterval/tools /opt/sparkinterval/tg_verifier

# The one file that does the mathematics.  Statically linked on purpose: a
# dynamically linked artifact would make the campaign's behaviour depend on
# whichever libc the base image ships, which is neither measured by CompCert
# nor named in `canonicalDefinition`.
COPY --chmod=0555 build/artifact /opt/sparkinterval/bin/artifact

RUN printf '%s  %s\n' "${TG_ARTIFACT_SHA256}" /opt/sparkinterval/bin/artifact \
        | sha256sum --check --strict

# Exactly the receipt machinery, and nothing analytic.  `phala_tdx_receipt.py`
# is the canonical signed payload, the report-data preimage, and the RFC-6979
# P-256 signer; it is shared verbatim with the A.7 image so that one Lean
# verifier accepts both.
COPY tg_verifier/__init__.py tg_verifier/phala_tdx_receipt.py \
    /opt/sparkinterval/tg_verifier/
COPY specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json \
    /opt/sparkinterval/specifications/TERNARY_GOLDBACH_EXTERNAL_ATOMS.json
COPY proof_build/leancompcert_tdx/run_artifact_campaign.sh \
    /opt/sparkinterval/run_artifact_campaign.sh
COPY proof_build/ch25_a7_phala_tdx/prelude_phala_tdx_inputs.py \
    /opt/sparkinterval/prelude_phala_tdx_inputs.py
COPY proof_build/ch25_a7_phala_tdx/emit_phala_tdx_evidence.py \
    /opt/sparkinterval/emit_phala_tdx_evidence.py

RUN chmod 0555 /opt/sparkinterval/run_artifact_campaign.sh \
    && chmod 0444 /opt/sparkinterval/prelude_phala_tdx_inputs.py \
        /opt/sparkinterval/emit_phala_tdx_evidence.py \
    && find /opt/sparkinterval/tg_verifier /opt/sparkinterval/specifications \
        -type f -exec chmod 0444 {} +

ENV PYTHONPATH="/opt/sparkinterval"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=0
ENV TG_ARTIFACT_PATH="/opt/sparkinterval/bin/artifact"
ENV TG_ARTIFACT_SHA256="${TG_ARTIFACT_SHA256}"
ENV TG_ARTIFACT_NAME="${TG_ARTIFACT_NAME}"
ENV TG_PHALA_TDX_KEY_DERIVER="/opt/sparkinterval/prelude_phala_tdx_inputs.py"

WORKDIR /workspace
ENTRYPOINT ["/opt/sparkinterval/run_artifact_campaign.sh"]

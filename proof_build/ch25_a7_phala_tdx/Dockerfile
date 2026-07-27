# syntax=docker/dockerfile:1.7
#
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Campaign image for the CH25 Lemma A.7 boundary replay, packaged to run as a
# dstack application inside an Intel TDX confidential VM on Phala Cloud.
#
# The image runs the registered producer and emits two artifacts: the exact
# registered result bytes, and a receipt signed with the key supplied to the
# container (in a real run, the dstack-derived key, which never leaves the
# TD).  It does NOT verify a TDX quote: quote parsing, the PCK chain, TCB
# levels, and QE identity are appraised outside by `dcap-qvl`, and only the
# SHA-256 of the retained quote and appraisal enters the signed statement.
#
# A Phala job must reference this image by its registry SHA-256 digest, never
# by a mutable tag: the digest is what the dstack app-compose document commits
# to and what the pinned Lean enclave identity records.
#
# The image is deliberately x86_64: Intel TDX is an x86 feature.  On a
# non-amd64 build host, register qemu emulation first
# (`docker run --privileged --rm tonistiigi/binfmt --install amd64`).

FROM --platform=linux/amd64 docker.io/library/python@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

# Exactly the runtime wheel pinned by
# specifications/PYTHON_FLINT_0_9_UPSTREAM.json.  Both the URL and the digest
# are baked in; the entry point re-verifies the digest at run time through
# tg_verifier/python_flint_runtime.py, so a substituted wheel fails closed
# even if this layer were tampered with.
ARG PYTHON_FLINT_WHEEL_FILENAME=python_flint-0.9.0-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
ARG PYTHON_FLINT_WHEEL_URL=https://files.pythonhosted.org/packages/db/3f/5f57004f9f43ac6508f874cc97123f11b27b6811b5bb0d320c43f600f0cb/python_flint-0.9.0-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
ARG PYTHON_FLINT_WHEEL_SHA256=376b88cacd30612479e839ffdba887599d3f9c8c0e214852bf80bb2b194e4d76

# The final registry image digest, plus the retained result, receipt, quote,
# and appraisal hashes, is the reproducibility identity.  Debian package
# repositories are not treated as a stable identity merely because this
# Dockerfile is pinned; nothing outside the pinned wheel and the copied
# repository sources participates in the campaign arithmetic.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN install -d -m 0755 /opt/sparkinterval /opt/sparkinterval/tools \
        /opt/sparkinterval/tg_verifier /opt/sparkinterval/specifications \
        /opt/sparkinterval/runtime

RUN curl --silent --show-error --location --fail --proto '=https' --tlsv1.2 \
        --output "/opt/sparkinterval/runtime/${PYTHON_FLINT_WHEEL_FILENAME}" \
        "${PYTHON_FLINT_WHEEL_URL}" \
    && printf '%s  %s\n' "${PYTHON_FLINT_WHEEL_SHA256}" \
        "/opt/sparkinterval/runtime/${PYTHON_FLINT_WHEEL_FILENAME}" \
        | sha256sum --check --strict \
    && chmod 0444 "/opt/sparkinterval/runtime/${PYTHON_FLINT_WHEEL_FILENAME}"

# The producer, the enclave signer, and exactly the verifier modules they
# need.  `tg_verifier` is copied whole because `a7_flint` imports the shared
# analytic checker; nothing Azure-specific is invoked by this entry point.
COPY tools/tg_a7_phala_tdx_workload.py /opt/sparkinterval/tools/
COPY tg_verifier/ /opt/sparkinterval/tg_verifier/
COPY specifications/PYTHON_FLINT_0_9_UPSTREAM.json \
    /opt/sparkinterval/specifications/PYTHON_FLINT_0_9_UPSTREAM.json
COPY proof_build/ch25_a7_phala_tdx/run_phala_tdx_campaign.sh \
    /opt/sparkinterval/run_phala_tdx_campaign.sh
RUN chmod 0555 /opt/sparkinterval/run_phala_tdx_campaign.sh \
    && find /opt/sparkinterval/tools /opt/sparkinterval/tg_verifier \
        /opt/sparkinterval/specifications -type f -exec chmod 0444 {} + \
    && python3 -c "import compileall, sys; sys.exit(0 if compileall.compile_dir('/opt/sparkinterval/tg_verifier', quiet=2) else 1)"

ENV PYTHONPATH="/opt/sparkinterval"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=0
ENV TG_PYTHON_FLINT_WHEEL="/opt/sparkinterval/runtime/python_flint-0.9.0-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"

WORKDIR /workspace
ENTRYPOINT ["/opt/sparkinterval/run_phala_tdx_campaign.sh"]

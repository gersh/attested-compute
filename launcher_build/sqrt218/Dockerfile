# syntax=docker/dockerfile:1.7
#
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Cloud-only build image for the non-authorizing Sqrt218 launcher prototype.
# It compiles and statically inspects the launcher, but never executes it.

FROM docker.io/rocq/rocq-prover@sha256:b85a80a11bb65c7c843f91c7cbcce282f22ee397c9ca42f123d568ab6cef68b0

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        build-essential \
        ca-certificates \
        libc6-dev \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY launcher_build/sqrt218/run_cloud_launcher_build.sh \
    /opt/sparkinterval/run_cloud_launcher_build.sh
COPY tools/tg_sqrt218_launcher_build.py \
    /opt/sparkinterval/tools/tg_sqrt218_launcher_build.py
COPY tg_verifier/campaign_io.py \
    /opt/sparkinterval/tg_verifier/campaign_io.py
COPY tg_verifier/sqrt218_launcher_build.py \
    /opt/sparkinterval/tg_verifier/sqrt218_launcher_build.py
RUN touch /opt/sparkinterval/tg_verifier/__init__.py \
    && chmod 0555 /opt/sparkinterval/run_cloud_launcher_build.sh

# The build job does not depend on an implicit host checkout.  Bake the exact
# manifest-pinned closure at the path validated by the runner.  The output is
# deliberately not baked: ACI mounts a persistent Azure Files export there.
RUN install -d \
    /workspace/repository/launcher_build/sqrt218 \
    /workspace/repository/tg_verifier \
    /workspace/repository/tools
COPY launcher_build/sqrt218/Dockerfile \
    /workspace/repository/launcher_build/sqrt218/Dockerfile
COPY launcher_build/sqrt218/README.md \
    /workspace/repository/launcher_build/sqrt218/README.md
COPY launcher_build/sqrt218/cloud-launcher-build.v1.json \
    /workspace/repository/launcher_build/sqrt218/cloud-launcher-build.v1.json
COPY launcher_build/sqrt218/run_cloud_launcher_build.sh \
    /workspace/repository/launcher_build/sqrt218/run_cloud_launcher_build.sh
COPY launcher_build/sqrt218/sqrt218_launcher_abi.h \
    /workspace/repository/launcher_build/sqrt218/sqrt218_launcher_abi.h
COPY launcher_build/sqrt218/sqrt218_launcher_sha256.c \
    /workspace/repository/launcher_build/sqrt218/sqrt218_launcher_sha256.c
COPY launcher_build/sqrt218/sqrt218_launcher_sha256.h \
    /workspace/repository/launcher_build/sqrt218/sqrt218_launcher_sha256.h
COPY launcher_build/sqrt218/sqrt218_pure_entry_launcher.c \
    /workspace/repository/launcher_build/sqrt218/sqrt218_pure_entry_launcher.c
COPY launcher_build/sqrt218/sqrt218_pure_entry_trampoline.S \
    /workspace/repository/launcher_build/sqrt218/sqrt218_pure_entry_trampoline.S
COPY tg_verifier/campaign_io.py \
    /workspace/repository/tg_verifier/campaign_io.py
COPY tg_verifier/sqrt218_launcher_build.py \
    /workspace/repository/tg_verifier/sqrt218_launcher_build.py
COPY tools/tg_sqrt218_launcher_build.py \
    /workspace/repository/tools/tg_sqrt218_launcher_build.py

ENV PYTHONPATH="/opt/sparkinterval"
ENTRYPOINT ["/opt/sparkinterval/run_cloud_launcher_build.sh"]

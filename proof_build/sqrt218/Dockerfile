# syntax=docker/dockerfile:1.7
#
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# This image builds the proof toolchain.  It does not run a production
# certificate and is not itself authority for a Lean theorem.  A cloud proof
# job must use the resulting image by its registry SHA-256 digest, never by a
# mutable tag.

FROM docker.io/rocq/rocq-prover@sha256:b85a80a11bb65c7c843f91c7cbcce282f22ee397c9ca42f123d568ab6cef68b0

ARG COMPCERT_REVISION=7b1f02b09954b9b916eb2a91d283c9b5355bf172
ARG VST_REVISION=cbee87efb4bee2b588f8321e16b4cb7664d5cf60

USER root

# The final registry image digest, plus the retained executable/configuration
# hashes, is the reproducibility identity.  Debian package repositories are
# not treated as a stable identity merely because this Dockerfile is pinned.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        build-essential \
        ca-certificates \
        git \
        jq \
        libgmp-dev \
        menhir \
        pkg-config \
        python3 \
    && rm -rf /var/lib/apt/lists/*

RUN install -d -o rocq -g rocq /home/rocq/src /home/rocq/toolchain

USER rocq
WORKDIR /home/rocq/src
SHELL ["/bin/bash", "--login", "-o", "pipefail", "-c"]

RUN git init compcert \
    && cd compcert \
    && git remote add origin https://github.com/AbsInt/CompCert.git \
    && git fetch --depth=1 origin "${COMPCERT_REVISION}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${COMPCERT_REVISION}" \
    && test -z "$(git status --porcelain)"

RUN eval "$(opam env)" \
    && cd /home/rocq/src/compcert \
    && ./configure \
        -clightgen \
        -install-coqdev \
        -prefix /home/rocq/toolchain/compcert \
        x86_64-linux \
    && make -j"$(nproc)" all \
    && make install

RUN git init VST \
    && cd VST \
    && git remote add origin https://github.com/PrincetonUniversity/VST.git \
    && git fetch --depth=1 origin "${VST_REVISION}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${VST_REVISION}" \
    && git submodule update --init --recursive \
    && test -z "$(git status --porcelain)"

RUN eval "$(opam env)" \
    && cd /home/rocq/src/VST \
    && make -j"$(nproc)" vst \
        BITSIZE=64 \
        ARCH=x86 \
        COMPCERT=inst_dir \
        COMPCERT_INST_DIR=/home/rocq/toolchain/compcert

ENV PATH="/home/rocq/toolchain/compcert/bin:${PATH}"
ENV COMPCERT_CONFIG="/home/rocq/toolchain/compcert/share/compcert/compcert.ini"
ENV TG_VST_ROOT="/home/rocq/src/VST"
ENV TG_COMPCERT_ROOT="/home/rocq/toolchain/compcert"

COPY --chown=rocq:rocq proof_build/sqrt218/run_cloud_proof_build.sh \
    /opt/sparkinterval/run_cloud_proof_build.sh
COPY --chown=rocq:rocq tools/tg_sqrt218_proof_build.py \
    /opt/sparkinterval/tools/tg_sqrt218_proof_build.py
COPY --chown=rocq:rocq tg_verifier/campaign_io.py \
    /opt/sparkinterval/tg_verifier/campaign_io.py
COPY --chown=rocq:rocq tg_verifier/sqrt218_proof_build.py \
    /opt/sparkinterval/tg_verifier/sqrt218_proof_build.py
RUN touch /opt/sparkinterval/tg_verifier/__init__.py
RUN chmod 0555 /opt/sparkinterval/run_cloud_proof_build.sh

ENV PYTHONPATH="/opt/sparkinterval"
ENTRYPOINT ["/opt/sparkinterval/run_cloud_proof_build.sh"]

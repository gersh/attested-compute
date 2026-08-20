#!/usr/bin/env bash
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Compile the PT21 ladder modules without a private Mathlib build.
#
# `SparkInterval.Zeta.PT21Ladder` imports nothing, so it compiles
# standalone; the geometry module imports only it, and the semantics module
# additionally needs Mathlib.  This script borrows `LEAN_PATH` from a
# sibling checkout that already has a populated `.lake`, so a worktree does
# not have to rebuild Mathlib to check the ladder.
#
#   source tools/pt21_ladder_env.sh [/path/to/populated/checkout]
#   lean SparkInterval/Zeta/PT21Ladder.lean

set -u

PT21_HOST_CHECKOUT="${1:-/home/gersh/attested-compute}"
PT21_LADDER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PT21_OUT="${PT21_LADDER_ROOT}/.out"

mkdir -p "${PT21_OUT}/SparkInterval/Zeta"

PT21_SHARED_LEAN_PATH="$(cd "${PT21_HOST_CHECKOUT}" && lake env printenv LEAN_PATH)"
export LEAN_PATH="${PT21_OUT}:${PT21_SHARED_LEAN_PATH}"

lean -o "${PT21_OUT}/SparkInterval/Zeta/PT21Ladder.olean" \
    "${PT21_LADDER_ROOT}/SparkInterval/Zeta/PT21Ladder.lean" || return 1
lean -o "${PT21_OUT}/SparkInterval/Zeta/PT21LadderGeometry.olean" \
    "${PT21_LADDER_ROOT}/SparkInterval/Zeta/PT21LadderGeometry.lean" || return 1

echo "LEAN_PATH set; PT21Ladder and PT21LadderGeometry oleans are in ${PT21_OUT}"

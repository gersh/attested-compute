# Project vision

> **Status: work in progress.** This document describes a target architecture,
> not a completed system. Current capabilities and gaps are listed below and in
> [Correctness claims](CORRECTNESS_CLAIMS.md).

SparkInterval is exploring a practical bridge between large finite
computations and small, inspectable formal proofs.

The long-term goal is to make an explicitly bounded computation something that
can be:

- specified and given precise mathematical semantics;
- executed efficiently on a CPU or GPU;
- checked independently or tied to a measured secure execution;
- preserved as an immutable, content-addressed certificate; and
- referenced from Lean through a narrow, auditable axiom boundary.

This is useful when recomputing inside Lean would be prohibitively expensive,
but the result is still finite and specific enough to name exactly. Examples
include exhaustive searches, interval-arithmetic sweeps, large finite sums,
and numerical verification over a declared domain.

## What “provable bounded arithmetic” means

Here, bounded arithmetic is an engineering discipline for finite computation,
not a claim that every GPU instruction has already been formalized and not a
reference to one particular logical theory named Bounded Arithmetic.

A computation is suitable when its contract fixes at least:

- the algorithm and numeric semantics;
- canonical inputs and parameters;
- the finite domain or coverage obligation;
- overflow, precision, and exceptional-value behavior;
- the output format and success conditions; and
- the proposition that a result checker establishes.

The desired proof story has two complementary routes. A full mathematical
certificate lets Lean recompute enough exact information to prove the claim
without trusting where the witness came from. A compact execution certificate
is useful when the full witness is too large: it binds a measured run to a
closed, registered computation whose semantics and checker soundness are
already proved in Lean.

## Target architecture

### 1. Formal computation contract

A registered computation has a stable identity, canonical serialization,
executable semantics, explicit bounds, and a Lean theorem explaining what a
successful result means. Callers select from a closed registry; certificate
bytes do not get to invent a proposition.

### 2. CPU and GPU execution

The same mathematical contract should support a simple CPU implementation for
independent replay and a parallel GPU implementation for scale. Exact or
directed-rounding reference evaluation supplies a portable oracle. Formal
compiler and machine models should close as much of the CPU/GPU implementation
gap as is practical, with remaining assumptions stated explicitly.

### 3. Secure execution evidence

For provenance-sensitive runs, measured code executes inside a supported
secure environment. On an H100-class path this means validating both the CPU
TEE and GPU confidential-computing evidence, not merely checking a GPU model
name or accepting a host-generated signature.

A production verifier must bind a fresh nonce and the exact runner, device
image, algorithm identity, inputs, parameters, domain coverage, output,
completion status, measurements, and approved TCB state. It must reject debug
mode, stale evidence, mismatched report data, incomplete certificate chains,
and policy failures.

### 4. Computation certificate library

After evidence verification, the accepted record should be stored under a
cryptographic digest. A library entry should be immutable and include enough
metadata to reproduce, independently inspect, revoke, or supersede the result:

- the registered computation and invocation identity;
- canonical inputs, bounds, and result;
- artifact and environment digests;
- mathematical witness or checker output;
- attestation-verifier identity, policy, and evidence digest; and
- source/toolchain versions and reproduction instructions.

The library is a distribution and discovery mechanism, not an additional
source of truth. Content addressing prevents accidental substitution; trust
still comes from Lean checking the mathematics and from the explicit policy for
accepted external execution evidence.

### 5. Lean consumption

Lean code should name a registered invocation and an exact certificate digest.
The Azure importer validates the canonical external record and source-pins its
normalized receipt as the positive-evidence capability. The project's single
execution axiom then turns
acceptance of that particular record into its historical outcome and the
registered invocation's fixed `Runs` relation.

Ordinary Lean theorems do the rest: parse the output, check bounds, and derive
the mathematical proposition. The intended boundary is deliberately narrower
than “trust this GPU answer” and does not assert universal correctness of all
future executions.

## Current state

The repository already contains substantial pieces of this design:

- exact CPU reference evaluation and full Lean result certificates;
- proved interval arithmetic and bounded arithmetic examples;
- a typed polynomial compiler and one-thread GPU machine model;
- CUDA validation and artifact auditing for DGX Spark and H100;
- canonical run bundles, signatures, closed invocation registration, and one
  explicit Lean execution axiom;
- Azure SEV-SNP CPU and NCC H100 deployment/evidence collectors, an
  independent-appraisal adapter, compact receipt signing, and source-pinned
  Lean import; and
- fail-closed mock and legacy-attestation boundaries.

The infrastructure path is implemented, but no production admission is
complete. The repository does not include a production Azure appraiser/policy,
Managed HSM key-attestation approval, measured production runner, real Azure
run, admitted receipt, or shared content-addressed certificate service. The
tracked receipt registry is empty and current retained H100 runs are local and
unattested. The exact implemented claims are maintained in
[Correctness claims](CORRECTNESS_CLAIMS.md).

## Design principles

- **Make the trust boundary visible.** Mathematical soundness, code modeling,
  physical execution, identity, and provenance are separate claims.
- **Fail closed.** Unsupported evidence, unknown measurements, missing fields,
  and mock modes must never become production acceptance.
- **Prefer replayable artifacts.** Inputs, results, policies, toolchain
  identity, and evidence should be canonical and content-addressed.
- **Keep axioms small and specific.** External execution enters Lean at one
  named boundary for one accepted run; application mathematics remains proved.
- **Support independent checking.** A verifier should not need to trust the
  machine that produced the result whenever a mathematical certificate can be
  checked separately.
- **State nonclaims beside claims.** A test, signature, modeled instruction, or
  attestation report must not silently stand in for a theorem it does not prove.

## Where help is most valuable

The first need is independent scrutiny of the existing proofs, implementations,
formats, and claim boundaries. The project also needs people who can make the
repository easier to adopt, help explain and demonstrate the idea, and connect
it with complementary formal-methods and systems projects. Adding more finite
computations is important, but should build on a foundation that outsiders can
reproduce and trust.

The [collaboration roadmap](ROADMAP.md) organizes that sequence. Detailed work
areas and the contribution process are in [Contributing](CONTRIBUTING.md).

# Collaboration roadmap

SparkInterval is a work in progress. This roadmap is an invitation to shape the
project, not a promise of dates or a claim that the later outcomes already
exist. Work can proceed in parallel, but trust and usability should mature
before the repository accumulates many new computations.

## Verify the foundation

The most valuable near-term result is independent confidence in the current
repository.

Desired outcomes:

- clean-checkout reproductions of the documented CPU/Lean workflows;
- independent DGX Spark and H100 validation reports where hardware is
  available;
- review of theorem dependencies, the single execution axiom, exact arithmetic,
  canonical serialization, and certificate soundness;
- adversarial review of parser limits, replay handling, bundle verification,
  signatures, and fail-closed attestation paths; and
- a public list of confirmed claims, open questions, and disputed assumptions.

This area is successful when a technically capable newcomer can identify a
claim, reproduce its evidence, and explain its boundary without relying on the
original author.

## Make the repository inviting and reusable

The project should become a dependable place for collaborators and downstream
users, not only a record of one implementation effort.

Desired outcomes:

- a short first-success path for CPU-only users and a separate path for GPU
  operators;
- reliable CI for documentation, Python, Lean, offline CUDA, and proof audits;
- clearer package and API boundaries for arithmetic, certificates, execution
  evidence, and registered computations;
- issue templates, contribution labels, release notes, and reviewed examples;
  and
- versioning and compatibility rules for formats, algorithms, profiles, and
  certificate-library entries.

This area is successful when outside contributors can install, test, modify,
and review the project without hidden setup knowledge.

## Explain and promote the idea responsibly

Promotion should invite verification and useful adoption while keeping the
work-in-progress status and trust boundaries visible.

Desired outcomes:

- a concise architecture explanation for formal-methods, numerical-computing,
  GPU, and confidential-computing audiences;
- small reproducible demonstrations with exact statements of what each one
  proves;
- talks, posts, or tutorials that link directly to verification instructions
  and open gaps;
- a public request for review aimed at relevant experts; and
- a gallery of independently reproduced results, including failures and
  limitations rather than only positive runs.

This area is successful when interested readers understand both the possible
future and the current nonclaims, and know how to participate.

## Build collaborations with other projects

SparkInterval should reuse compatible standards and tools rather than building
every layer alone.

Potential collaboration areas include:

- Lean and Mathlib projects that can consume finite certified results;
- interval and arbitrary-precision libraries that can provide trusted or
  independently checked arithmetic;
- proof-certificate and verifiable-computation systems with complementary
  compact-proof techniques;
- reproducible-build and artifact-transparency projects that can distribute
  immutable records; and
- CPU TEE, NVIDIA confidential-computing, and remote-attestation projects that
  can help review the production evidence boundary.

A useful collaboration starts with a concrete shared artifact or interface:
one certificate format, checker, registered theorem, attestation-verifier
output, or reproducible example. A list of names without an integration target
is not yet a project dependency or endorsement.

## Complete the secure certificate path

The target end-to-end workflow needs:

- production verification of CPU-TEE and GPU confidential-computing evidence;
- measurement, TCB, freshness, artifact, input, coverage, output, and completion
  binding;
- a reviewed trusted importer into Lean's private evidence type;
- a content-addressed certificate library with mirroring and
  revocation/supersession metadata; and
- at least one small registered computation exercised through the whole path.

This area is successful only when positive and negative cases have been
independently reviewed. A local run, mock evidence, operator signature, or
structurally valid report is not a substitute.

## Add more finite computations

Once the foundation is reproducible and its interfaces are usable, the project
can grow a library of computations chosen for real proof value.

Each candidate should have:

- a motivating downstream theorem or decision problem;
- a canonical finite domain and explicit coverage claim;
- specified numeric and failure semantics;
- a practical CPU reference path and, where useful, a GPU path;
- either a Lean-checkable mathematical certificate or registered checker
  semantics with a soundness theorem; and
- realistic certificate size, verification cost, and archival requirements.

Good early candidates are small enough to reproduce independently but large
enough to demonstrate why certificate reuse matters. Proposed computations can
be discussed through the process in [Contributing](CONTRIBUTING.md).

## How to help

Choose one observable outcome above, open or join a focused GitHub issue, and
record the claim and verification commands in the contribution. If you are not
sure where your expertise fits, a clean-room reproduction of any documented
workflow is an excellent starting point.

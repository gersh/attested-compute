/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

/-!
# Pinned trusted-compute verifier key

This file is the reviewed public-key pin for compact trusted-compute receipts.
The corresponding private key is never part of the repository.  A production
deployment must place it in a release HSM or replace this bootstrap pin through
a reviewed source change before admitting production certificates.

Key rotation is intentionally a source-level trust-boundary change.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

/-- Stable identifier for the development-only bootstrap RSA-3072 key. -/
def trustedComputeVerifierKeyId : String :=
  "sparkinterval-bootstrap-rsa3072-2026-07"

/-- One source-approved issuer configuration.  A verifier key is not enough
on its own: the backend, exact target/trust profiles, and exact appraiser
executable/policy hashes must all match one entry reviewed with that key. -/
structure TrustedComputeVerifierProfile where
  keyId : String
  classification : String
  backend : String
  targetProfileHash : String
  trustProfileHash : String
  verifierArtifactHash : String
  verifierPolicyHash : String
  deriving Repr, DecidableEq, BEq

/-- Exact issuer tuples synchronized with
`profiles/verifier_keys/trusted_compute_keys.json` by a Python regression
test.  There is deliberately no wildcard form. -/
def trustedComputeAllowedVerifierProfiles : List TrustedComputeVerifierProfile := [
  {
    keyId := "sparkinterval-bootstrap-rsa3072-2026-07"
    classification := "development"
    backend := "azure_sevsnp_cpu"
    targetProfileHash := "27c1f9d99d4a2bafae009c09310eec8bd710663bcdc463f90244019da1f948d5"
    trustProfileHash := "dfec83fa16f6740346d6d9d79c02200e2bdd2757d30e6252b96e670c5b540e72"
    verifierArtifactHash := "88c9eae68eb300b2971a2bec9e5a26ff4179fd661d6b7d861e4c6557b9aaee14"
    verifierPolicyHash := "823412d1eacb67956220e532959f0104603057c88704863ca38e7cd188fda812"
  }
]

/-- Whether every security-relevant issuer and workload-profile coordinate is
approved by a single reviewed tuple. -/
def trustedComputeVerifierProfileAllowed
    (keyId backend targetProfileHash trustProfileHash verifierArtifactHash
      verifierPolicyHash : String) : Bool :=
  trustedComputeAllowedVerifierProfiles.any (fun profile =>
    profile.keyId == keyId &&
      profile.backend == backend &&
      profile.targetProfileHash == targetProfileHash &&
      profile.trustProfileHash == trustProfileHash &&
      profile.verifierArtifactHash == verifierArtifactHash &&
      profile.verifierPolicyHash == verifierPolicyHash)

/-- Production theorem admission never accepts a development/bootstrap key,
even when an external generator was explicitly asked to process its fixture. -/
def trustedComputeProductionVerifierProfileAllowed
    (keyId backend targetProfileHash trustProfileHash verifierArtifactHash
      verifierPolicyHash : String) : Bool :=
  trustedComputeAllowedVerifierProfiles.any (fun profile =>
    profile.classification == "production" &&
      profile.keyId == keyId &&
      profile.backend == backend &&
      profile.targetProfileHash == targetProfileHash &&
      profile.trustProfileHash == trustProfileHash &&
      profile.verifierArtifactHash == verifierArtifactHash &&
      profile.verifierPolicyHash == verifierPolicyHash)

/-- Source-pinned verifier identities whose receipts may be admitted.

The bootstrap key is development-only.  A production deployment should add a
Managed-HSM key through a reviewed source change and remove the bootstrap key
before importing production receipts.  Registry generation must verify the
corresponding public-key manifest independently; this list is only the narrow
Lean-side identity guard. -/
def trustedComputeAllowedVerifierKeyIds : List String :=
  (trustedComputeAllowedVerifierProfiles.map (fun profile => profile.keyId)).eraseDups

/-- Whether a normalized receipt names a source-approved verifier key. -/
def trustedComputeVerifierKeyAllowed (keyId : String) : Bool :=
  !keyId.isEmpty && trustedComputeAllowedVerifierKeyIds.contains keyId

/-- Diagnostic RSA-3072 public modulus for the development bootstrap key,
encoded as exactly 384 lowercase hexadecimal bytes.  The public exponent is
65537.  Production acceptance is source-registry based and uses the reviewed
key manifest during import; it does not depend on this modulus. -/
def trustedComputeVerifierModulusHex : String :=
  "b38491214de02966b52940ccfa174b0d5ad18ece307883a34daec9f420926731c836d0f1c1f2b43b2166ca14f49b707f799de94b887cb47f749c128fa06935a4c324395cf329b73cddd836666f9c1a1d57b336d95ed186b0536c33fa72afd72f76b980b1c53535de4ebceab9f7fd00e13f831c1d4527eae262f0a3573c0f6c282017430e188933176f7e791aa3e16a1c05195bb2298a7f75f4f2a8c22268daaff0a616f07ab8a190e1a70e6ec12af16268c4ca024e8fb040bf2e89eb72d4349b8401ab195678f2031be6d7ebfad35a9b18c2fdc41b0d5cfba4a98ea3a9162dba533a0f9a86cd5b77c9adf9cbab67df7b6c8718ff22ff8e80c208fe689380f75f4deb0a79907246f88489878fd5f4590891467a52577961100ef5dc46567ff504c1762fa5829bc675953e17cf8910320038f98789c8cbfdc11e120dd94cd755f44a45083a365dbd5f629eabda7347cac3c8f6969ac2894a51a22a2ce7d8f805f8bdd7aec3379126b5921c487c2ccc51a2fec12a9738833215a8a47ce4bc00ffe3"

end SparkInterval.Execution

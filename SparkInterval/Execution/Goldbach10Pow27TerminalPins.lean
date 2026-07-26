/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.Statement

/-!
# Post-run pins for the finite-Goldbach terminal computation

Production is deliberately unconfigured.  After a completed campaign, the
review-only generator emits a candidate replacement whose values come from the
signed terminal statement and the independently audited child-identity bundle.
No placeholder digest is accepted.
-/

set_option autoImplicit false

namespace SparkInterval.Execution

def goldbach10Pow27TerminalIdentityBundleSha256 : Option Digest := none
def goldbach10Pow27TerminalReceiptSha256 : Option Digest := none
def goldbach10Pow27TerminalJobSpecSha256 : Option Digest := none
def goldbach10Pow27TerminalArtifactClosureSha256 : Option Digest := none
def goldbach10Pow27TerminalSourceTreeSha256 : Option Digest := none
def goldbach10Pow27TerminalHostExecutableSha256 : Option Digest := none
/-- The signed statement's `kernelManifestHash`.  This is the terminal
artifact-closure digest after the complete signed-child identity commitment
has been inserted, not a build-time-only kernel identifier. -/
def goldbach10Pow27TerminalPostRunCommitmentSha256 : Option Digest := none
def goldbach10Pow27ChildReceiptIdentitiesSha256 : Option Digest := none
def goldbach10Pow27BuildAdmissionSha256 : Option Digest := none
def goldbach10Pow27TerminalRuntimeClosureSha256 : Option Digest := none

/-- Exact signed-statement artifact identity, available only after review. -/
def goldbach10Pow27TerminalArtifactPins : Option ArtifactHashes := do
  let _bundleSha256 ← goldbach10Pow27TerminalIdentityBundleSha256
  let _receiptSha256 ← goldbach10Pow27TerminalReceiptSha256
  let _jobSpecSha256 ← goldbach10Pow27TerminalJobSpecSha256
  let _artifactClosureSha256 ← goldbach10Pow27TerminalArtifactClosureSha256
  let sourceTreeHash ← goldbach10Pow27TerminalSourceTreeSha256
  let hostExecutableHash ← goldbach10Pow27TerminalHostExecutableSha256
  let kernelManifestHash ←
    goldbach10Pow27TerminalPostRunCommitmentSha256
  let _childIdentitiesSha256 ←
    goldbach10Pow27ChildReceiptIdentitiesSha256
  let _buildAdmissionSha256 ← goldbach10Pow27BuildAdmissionSha256
  let _runtimeClosureSha256 ←
    goldbach10Pow27TerminalRuntimeClosureSha256
  some {
    sourceTreeHash
    hostExecutableHash
    deviceCubinHash :=
      "b272852e69f12bacf5fbb095bc43233bfd184f238a86f5bb66d85772b849d02b"
    kernelManifestHash
  }

end SparkInterval.Execution

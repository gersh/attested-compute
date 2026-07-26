/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.Trusted.ReceiptAnchor
import Lean.Elab.Command
import Lean.Util.CollectAxioms

/-!
# Auditable trusted-compute receipt use

`#print axioms` deliberately reports the repository's single execution axiom,
not every concrete signed receipt at which that axiom was instantiated.  This
module adds a kernel-visible receipt wrapper and two audit commands:

* `#print certificates declaration` prints every concrete receipt SHA-256 on
  the declaration's transitive path to the execution axiom.  It also prints a
  stable `certificate-audit-v1|...` summary line.
* `#audit certificates declaration` performs the same analysis and fails when
  any path reaches the generic execution axiom without passing through a
  closed, canonical receipt-wrapper application.  It also rejects every root
  axiom except `propext`, `Classical.choice`, `Quot.sound`, and the one trusted
  execution axiom; a forged acceptance premise therefore cannot hide behind a
  correctly shaped wrapper call.
* `#print project certificates` inventories every concrete wrapper site and
  every direct trusted-run-axiom caller in the loaded `SparkInterval.*`
  environment.  `#audit project certificates` fails closed on malformed
  wrapper sites, unreviewed direct callers, or unexpected project axioms.
* `#audit project axioms` checks the actual kernel environment (rather than
  source text) and fails unless the sole `SparkInterval.*` axiom declaration
  is the named trusted-run axiom.

Generated receipt modules should call `acceptedRunCertificateForReceipt`
instead of calling `accepted_run_certificate_sound` directly.  The extra
equality premise is checked by the kernel and prevents the displayed hash from
drifting away from the hash in `certificate.attestation`.  The wrapper is an
ordinary theorem derived from the same single axiom; it adds no trust.

This is an audit aid, not part of the kernel's soundness check.  In particular,
it deliberately treats a wrapper call containing local variables as
parametric rather than as a concrete certificate use.
-/

set_option autoImplicit false

namespace SparkInterval.Audit

open Lean Elab Command

private def trustAxiomName : Name :=
  ``SparkInterval.Execution.Trusted.accepted_run_certificate_sound

private def receiptWrapperName : Name :=
  ``SparkInterval.Execution.Trusted.acceptedRunCertificateForReceipt

/-- Direct calls at these generic bridge declarations are reviewed parts of
the disclosed trust boundary.  Concrete generated consumers are intentionally
absent: they must use `acceptedRunCertificateForReceipt` instead.  Keeping
this as a closed name list makes every new generic axiom caller an explicit,
reviewable source change. -/
def isReviewedDirectTrustAxiomCaller (declName : Name) : Bool :=
  declName == receiptWrapperName ||
    declName ==
      ``SparkInterval.Execution.Trusted.checked_run_certificate_sound ||
    declName ==
      ``SparkInterval.Execution.Trusted.accepted_registered_architecture_outcomes ||
    declName ==
      `SparkInterval.Execution.SignedResultCertificate.outcomeCheck_sound ||
    declName ==
      `SparkInterval.Execution.SignedResultCertificate.checkUpperBound_sound ||
    declName ==
      `SparkInterval.Execution.SignedResultCertificate.checkSumUpperBound_sound

/-- Axioms permitted in a certificate-backed theorem.  `Lean.ofReduceBool`,
`sorryAx`, and project-specific helper axioms are intentionally absent. -/
def isAllowedCertificateRootAxiom (axiomName : Name) : Bool :=
  axiomName == ``propext ||
    axiomName == ``Classical.choice ||
    axiomName == ``Quot.sound ||
    axiomName == trustAxiomName

/-- Unexpected members of a complete `Lean.collectAxioms` result.  Exposed so
tests can regression-check the fail-closed classification without adding a
second source axiom. -/
def unexpectedCertificateRootAxioms (axioms : Array Name) : Array Name :=
  axioms.filter fun axiomName => !isAllowedCertificateRootAxiom axiomName

private def isLowerHexChar (c : Char) : Bool :=
  "0123456789abcdef".toList.contains c

private def isCanonicalReceiptHash (value : String) : Bool :=
  value.length == 64 && value.toList.all isLowerHexChar

private def declarationExprs (env : Environment) (declName : Name) : Array Expr :=
  match env.checked.get.find? declName with
  | some (.axiomInfo value) => #[value.type]
  | some (.defnInfo value) => #[value.type, value.value]
  | some (.thmInfo value) => #[value.type, value.value]
  | some (.opaqueInfo value) => #[value.type, value.value]
  | some (.quotInfo _) => #[]
  | some (.ctorInfo value) => #[value.type]
  | some (.recInfo value) => #[value.type]
  | some (.inductInfo value) => #[value.type]
  | none => #[]

private def directDependencies (env : Environment) (declName : Name) : Array Name :=
  let names : NameSet := (declarationExprs env declName).foldl
    (fun names expr => expr.getUsedConstants.foldl
      (fun names name => names.insert name) names) ({} : NameSet)
  names.toArray.qsort Name.quickLt

private structure ReceiptUse where
  anchor : Name
  hash : Option String
  arityValid : Bool
  closed : Bool
  canonical : Bool
  path : List Name := []
  deriving Inhabited

private def ReceiptUse.valid (use : ReceiptUse) : Bool :=
  use.arityValid && use.closed && use.canonical && use.hash.isSome

private def inspectReceiptCall (anchor : Name) (expr : Expr) : Option ReceiptUse :=
  let (fnName, args) := expr.getAppFnArgs
  if fnName != receiptWrapperName then
    none
  else
    let hashExpr? : Option Expr := args[0]?
    let hash := match hashExpr? with
      | some (.lit (.strVal value)) => some value
      | _ => none
    let arityValid := args.size == 4
    let closed := arityValid && !expr.hasLooseBVars &&
      !expr.hasFVar && !expr.hasMVar
    let canonical := hash.any isCanonicalReceiptHash
    some { anchor, hash, arityValid, closed, canonical }

private partial def receiptUsesInExpr
    (anchor : Name) (expr : Expr) : Array ReceiptUse :=
  let here := match inspectReceiptCall anchor expr with
    | some use => #[use]
    | none => #[]
  let children :=
    if expr.getAppFn.constName == receiptWrapperName then
      -- Inspect one maximal wrapper-headed application.  Recursing through
      -- its function spine would misclassify every valid four-argument call
      -- as three nested partial calls; its arguments can still contain
      -- independent wrapper occurrences and must be scanned.
      expr.getAppArgs.flatMap (receiptUsesInExpr anchor)
    else
      match expr with
      | .forallE _ domain body _ =>
          receiptUsesInExpr anchor domain ++ receiptUsesInExpr anchor body
      | .lam _ domain body _ =>
          receiptUsesInExpr anchor domain ++ receiptUsesInExpr anchor body
      | .mdata _ body => receiptUsesInExpr anchor body
      | .letE _ type value body _ =>
          receiptUsesInExpr anchor type ++ receiptUsesInExpr anchor value ++
            receiptUsesInExpr anchor body
      | .app fn arg =>
          receiptUsesInExpr anchor fn ++ receiptUsesInExpr anchor arg
      | .proj _ _ body => receiptUsesInExpr anchor body
      | _ => #[]
  here ++ children

private def receiptUsesInDeclaration
    (env : Environment) (declName : Name) : Array ReceiptUse :=
  (declarationExprs env declName).flatMap (receiptUsesInExpr declName)

private structure AuditState where
  visitedUncovered : NameSet := {}
  visitedCovered : NameSet := {}
  uses : Array ReceiptUse := #[]
  invalidUses : Array ReceiptUse := #[]
  uncoveredWitness? : Option (List Name) := none

private abbrev AuditM := StateT AuditState CommandElabM

private def alreadyVisited (declName : Name) (covered : Bool) : AuditM Bool := do
  let state ← get
  let visited := if covered then state.visitedCovered else state.visitedUncovered
  if visited.contains declName then
    return true
  if covered then
    modify fun state =>
      { state with visitedCovered := state.visitedCovered.insert declName }
  else
    modify fun state =>
      { state with visitedUncovered := state.visitedUncovered.insert declName }
  return false

private partial def walkTrustPaths
    (declName : Name) (covered : Bool) (pathRev : List Name) : AuditM Unit := do
  if ← alreadyVisited declName covered then
    return
  let pathRev := declName :: pathRev
  if declName == trustAxiomName then
    unless covered do
      modify fun state =>
        if state.uncoveredWitness?.isSome then state
        else { state with uncoveredWitness? := some pathRev.reverse }
    return

  let env ← getEnv
  let uses := (receiptUsesInDeclaration env declName).map fun use =>
    { use with path := pathRev.reverse }
  let validUses := uses.filter ReceiptUse.valid
  let invalidUses := uses.filter fun use => !use.valid
  unless validUses.isEmpty do
    modify fun state => { state with uses := state.uses ++ validUses }
  unless invalidUses.isEmpty do
    modify fun state => { state with invalidUses := state.invalidUses ++ invalidUses }

  let dependencies := directDependencies env declName
  for dependency in dependencies do
    let reachesTrust := (← Lean.collectAxioms dependency).contains trustAxiomName
    unless reachesTrust do continue
    if dependency == receiptWrapperName then
      if uses.isEmpty then
        walkTrustPaths dependency covered pathRev
      else
        for use in uses do
          walkTrustPaths dependency (covered || use.valid) pathRev
    else
      walkTrustPaths dependency covered pathRev

private structure CertificateAudit where
  root : Name
  reachesTrustAxiom : Bool
  allAxioms : Array Name
  unexpectedAxioms : Array Name
  uses : Array ReceiptUse
  invalidUses : Array ReceiptUse
  uncoveredWitness? : Option (List Name)

private def auditDeclaration (root : Name) : CommandElabM CertificateAudit := do
  let allAxioms := ← Lean.collectAxioms root
  let reachesTrustAxiom := allAxioms.contains trustAxiomName
  let unexpectedAxioms := unexpectedCertificateRootAxioms allAxioms
  if !reachesTrustAxiom then
    return CertificateAudit.mk root reachesTrustAxiom allAxioms
      unexpectedAxioms #[] #[] none
  let (_, state) ← (walkTrustPaths root false []).run ({} : AuditState)
  return CertificateAudit.mk root reachesTrustAxiom allAxioms
    unexpectedAxioms state.uses state.invalidUses state.uncoveredWitness?

private def receiptUseKey (use : ReceiptUse) : String :=
  use.hash.getD "<nonliteral>" ++ "|" ++ use.anchor.toString ++ "|" ++
    String.intercalate "->" (use.path.map Name.toString)

private def deduplicateUses (uses : Array ReceiptUse) : Array ReceiptUse := Id.run do
  let sorted := uses.qsort fun left right =>
    receiptUseKey left < receiptUseKey right
  let mut result := #[]
  let mut previous? : Option String := none
  for use in sorted do
    let key := receiptUseKey use
    if previous? != some key then
      result := result.push use
      previous? := some key
  return result

private def auditStatus (audit : CertificateAudit) : String :=
  if !audit.unexpectedAxioms.isEmpty then "FAIL_UNEXPECTED_AXIOMS"
  else if !audit.reachesTrustAxiom then "AXIOM_FREE"
  else if audit.uncoveredWitness?.isSome || !audit.invalidUses.isEmpty then
    "FAIL_UNATTRIBUTED"
  else "COVERED"

private def pathString (path : List Name) : String :=
  String.intercalate " -> " (path.map Name.toString)

private def invalidReceiptUseReason (use : ReceiptUse) : String :=
  if !use.arityValid then "wrapper is partial or over-applied"
  else if use.hash.isNone then "receipt hash is not a literal"
  else if !use.canonical then "receipt hash is not canonical lowercase SHA-256"
  else "wrapper application contains local variables"

private def printAudit (audit : CertificateAudit) : CommandElabM Unit := do
  let uses := deduplicateUses audit.uses
  let invalidUses := deduplicateUses audit.invalidUses
  logInfo m!"trusted-compute certificate audit for '{audit.root}'"
  if audit.allAxioms.isEmpty then
    logInfo "  complete root axiom set: none"
  else
    logInfo "  complete root axiom set:"
    for axiomName in audit.allAxioms do
      let allowed := isAllowedCertificateRootAxiom axiomName
      logInfo m!"    {axiomName} ({if allowed then "allowed" else "UNEXPECTED"})"
      logInfo <| "certificate-root-axiom-v1" ++
        "|declaration=" ++ audit.root.toString ++
        "|axiom=" ++ axiomName.toString ++
        "|allowed=" ++ (if allowed then "true" else "false")
  if !audit.reachesTrustAxiom then
    logInfo "  generic execution axiom: not reachable"
  else
    logInfo "  generic execution axiom: reachable"
  if uses.isEmpty then
    logInfo "  concrete receipt uses: none"
  else
    logInfo m!"  concrete receipt uses ({uses.size}):"
    for use in uses do
      logInfo m!"    sha256:{use.hash.get!} at {use.anchor}"
      logInfo m!"      covered path: {pathString use.path}"
      logInfo <| "certificate-use-v1" ++
        "|declaration=" ++ audit.root.toString ++
        "|receipt_sha256=" ++ use.hash.get! ++
        "|anchor=" ++ use.anchor.toString ++
        "|path=" ++ String.intercalate "->" (use.path.map Name.toString)
  for use in invalidUses do
    logInfo m!"  NON-CONCRETE receipt wrapper at {use.anchor}: {invalidReceiptUseReason use}"
  if let some path := audit.uncoveredWitness? then
    logInfo m!"  UNATTRIBUTED AXIOM PATH: {pathString path}"
  let status := auditStatus audit
  logInfo <| "certificate-audit-v1" ++
    "|declaration=" ++ audit.root.toString ++
    "|trust_axiom=" ++ (if audit.reachesTrustAxiom then "true" else "false") ++
    "|concrete_receipts=" ++ toString uses.size ++
    "|invalid_wrappers=" ++ toString invalidUses.size ++
    "|unexpected_axioms=" ++ toString audit.unexpectedAxioms.size ++
    "|unattributed_path=" ++
      (if audit.uncoveredWitness?.isSome then "true" else "false") ++
    "|status=" ++ status

private def resolveDeclaration (identifier : Syntax) : CommandElabM (List Name) := do
  liftCoreM <| Lean.Elab.realizeGlobalConstWithInfos identifier

private def isProjectModule (moduleName : Name) : Bool :=
  let value := moduleName.toString
  value == "SparkInterval" || value.startsWith "SparkInterval."

/-- Every declaration from a loaded `SparkInterval.*` module, plus every
declaration already elaborated in the current audit file.  Consequently the
project commands audit their imported environment, not unimported repository
files; the whole-project gate invokes them from an aggregate import. -/
private def projectDeclarations (env : Environment) : Array Name := Id.run do
  let header := env.header
  let mut names := #[]
  -- Module data already contains an exact declaration-name array.  Reading
  -- those arrays avoids folding over every Mathlib constant merely to reject
  -- declarations from non-project modules.
  for h : moduleIdx in [0:header.moduleData.size] do
    if let some moduleName := header.moduleNames[moduleIdx]? then
      if isProjectModule moduleName then
        names := names ++ header.moduleData[moduleIdx].constNames
  -- Stage two contains declarations elaborated in the current module, which
  -- have no imported-module index and are included conservatively.
  names := env.checked.get.constants.foldStage2
    (fun names declName _ => names.push declName) names
  return names.qsort Name.quickLt

/-- Actual project axiom declarations currently loaded in the kernel
environment.  Unlike a source grep, this sees `constant` declarations and
declarations synthesized by elaborators. -/
private def projectAxiomDeclarations (env : Environment) : Array Name :=
  (projectDeclarations env).filter fun declName =>
    match env.checked.get.find? declName with
    | some (ConstantInfo.axiomInfo _) => true
    | _ => false

/-- Find the small set of declarations whose terms mention either boundary
constant.  Computing this once avoids recursively rescanning large arithmetic
proof terms when almost all declarations are unrelated to trusted compute. -/
private def projectTrustReferenceDeclarations
    (env : Environment) (declarations : Array Name) :
    CommandElabM (Array Name × Array Name) := do
  let mut wrapperDeclarations := #[]
  let mut directAxiomCallers := #[]
  for declName in declarations do
    -- Imported modules carry a precomputed axiom-dependency table.  This
    -- cheap filter avoids opening large arithmetic proof terms that cannot
    -- possibly contain either receipt-boundary constant.
    unless (← Lean.collectAxioms declName).contains trustAxiomName do
      continue
    let dependencies := directDependencies env declName
    if dependencies.contains receiptWrapperName then
      wrapperDeclarations := wrapperDeclarations.push declName
    if declName != trustAxiomName && dependencies.contains trustAxiomName then
      directAxiomCallers := directAxiomCallers.push declName
  return (wrapperDeclarations, directAxiomCallers)

private def uniqueStrings (values : Array String) : Array String := Id.run do
  let sorted := values.qsort (fun left right => left < right)
  let mut result := #[]
  let mut previous? : Option String := none
  for value in sorted do
    if previous? != some value then
      result := result.push value
      previous? := some value
  return result

private def uniqueNames (values : Array Name) : Array Name := Id.run do
  let sorted := values.qsort Name.quickLt
  let mut result := #[]
  let mut previous? : Option Name := none
  for value in sorted do
    if previous? != some value then
      result := result.push value
      previous? := some value
  return result

/-- Check each concrete instantiation anchor with the same transitive audit as
`#audit certificates declaration`. -/
private def uncoveredConcreteAnchors
    (uses : Array ReceiptUse) : CommandElabM (Array Name) := do
  let anchors := uniqueNames (uses.map (fun use => use.anchor))
  let mut uncovered := #[]
  for anchor in anchors do
    let audit ← auditDeclaration anchor
    if auditStatus audit != "COVERED" then
      uncovered := uncovered.push anchor
  return uncovered

private def printProjectCertificateAudit
    (failOnUnexpected : Bool) : CommandElabM Unit := do
  let env ← getEnv
  let declarations := projectDeclarations env
  let (wrapperDeclarations, directCallers) ←
    projectTrustReferenceDeclarations env declarations
  let allUses := wrapperDeclarations.flatMap (receiptUsesInDeclaration env)
  let validUses := deduplicateUses (allUses.filter ReceiptUse.valid)
  let invalidUses := deduplicateUses (allUses.filter fun use => !use.valid)
  let uniqueHashes := uniqueStrings <|
    validUses.map fun use => use.hash.get!
  let unexpectedDirectCallers := directCallers.filter fun declName =>
    !isReviewedDirectTrustAxiomCaller declName
  let projectAxioms := projectAxiomDeclarations env
  let unexpectedProjectAxioms := projectAxioms.filter fun declName =>
    declName != trustAxiomName
  let trustAxiomPresent := projectAxioms.contains trustAxiomName
  let uncoveredAnchors ← uncoveredConcreteAnchors validUses

  logInfo "trusted-compute project certificate inventory"
  logInfo "  scope: loaded SparkInterval.* modules plus the current module"
  if validUses.isEmpty then
    logInfo "  concrete receipt sites: none"
  else
    logInfo m!"  concrete receipt sites ({validUses.size}):"
    for use in validUses do
      logInfo m!"    sha256:{use.hash.get!} at {use.anchor}"
      logInfo <| "project-certificate-use-v1" ++
        "|receipt_sha256=" ++ use.hash.get! ++
        "|anchor=" ++ use.anchor.toString
  for use in invalidUses do
    logInfo m!"  INVALID receipt wrapper at {use.anchor}: {invalidReceiptUseReason use}"
    logInfo <| "project-certificate-invalid-v1" ++
      "|anchor=" ++ use.anchor.toString ++
      "|reason=" ++ invalidReceiptUseReason use

  if directCallers.isEmpty then
    logInfo "  direct trusted-run-axiom callers: none"
  else
    logInfo m!"  direct trusted-run-axiom callers ({directCallers.size}):"
    for declName in directCallers do
      let reviewed := isReviewedDirectTrustAxiomCaller declName
      logInfo m!"    {declName} ({if reviewed then "reviewed generic bridge" else "UNEXPECTED"})"
      logInfo <| "project-certificate-direct-caller-v1" ++
        "|declaration=" ++ declName.toString ++
        "|reviewed=" ++ (if reviewed then "true" else "false")

  for anchor in uncoveredAnchors do
    logInfo m!"  UNCOVERED concrete receipt anchor: {anchor}"

  let passed := trustAxiomPresent && unexpectedProjectAxioms.isEmpty &&
    invalidUses.isEmpty && unexpectedDirectCallers.isEmpty &&
    uncoveredAnchors.isEmpty
  logInfo <| "project-certificate-audit-v1" ++
    "|scope=loaded-SparkInterval-environment" ++
    "|unique_receipts=" ++ toString uniqueHashes.size ++
    "|concrete_sites=" ++ toString validUses.size ++
    "|invalid_wrappers=" ++ toString invalidUses.size ++
    "|direct_axiom_callers=" ++ toString directCallers.size ++
    "|unexpected_direct_callers=" ++ toString unexpectedDirectCallers.size ++
    "|uncovered_concrete_anchors=" ++ toString uncoveredAnchors.size ++
    "|project_axioms=" ++ toString projectAxioms.size ++
    "|unexpected_project_axioms=" ++ toString unexpectedProjectAxioms.size ++
    "|trust_axiom_present=" ++ (if trustAxiomPresent then "true" else "false") ++
    "|status=" ++ (if passed then "PASS" else "FAIL")
  if failOnUnexpected && !passed then
    throwError m!"project certificate audit failed: invalid_wrappers={invalidUses.size}, unexpected_direct_callers={unexpectedDirectCallers.size}, uncovered_concrete_anchors={uncoveredAnchors.size}, unexpected_project_axioms={unexpectedProjectAxioms.size}, trust_axiom_present={trustAxiomPresent}"

private def printProjectAxiomAudit (failOnUnexpected : Bool) : CommandElabM Unit := do
  let axioms := projectAxiomDeclarations (← getEnv)
  let unexpected := axioms.filter (fun name => name != trustAxiomName)
  let trustAxiomPresent := axioms.contains trustAxiomName
  logInfo "kernel-environment project axiom declarations:"
  if axioms.isEmpty then
    logInfo "  none"
  else
    for axiomName in axioms do
      let allowed := axiomName == trustAxiomName
      logInfo m!"  {axiomName} ({if allowed then "allowed trust boundary" else "UNEXPECTED"})"
      logInfo <| "project-axiom-v1" ++
        "|declaration=" ++ axiomName.toString ++
        "|allowed=" ++ (if allowed then "true" else "false")
  let passed := trustAxiomPresent && unexpected.isEmpty
  logInfo <| "project-axiom-audit-v1" ++
    "|prefix=SparkInterval" ++
    "|axioms=" ++ toString axioms.size ++
    "|unexpected=" ++ toString unexpected.size ++
    "|trust_axiom_present=" ++ (if trustAxiomPresent then "true" else "false") ++
    "|status=" ++ (if passed then "PASS" else "FAIL")
  if failOnUnexpected && !passed then
    throwError "project axiom audit failed: expected exactly the named trusted-run axiom and no other SparkInterval axiom declarations in the imported environment"

syntax (name := printCertificates) "#print " &"certificates" ppSpace ident : command
syntax (name := auditCertificates) "#audit " &"certificates" ppSpace ident : command
syntax (name := printProjectCertificates) "#print " &"project" ppSpace &"certificates" : command
syntax (name := auditProjectCertificates) "#audit " &"project" ppSpace &"certificates" : command
syntax (name := printProjectAxioms) "#print " &"project" ppSpace &"axioms" : command
syntax (name := auditProjectAxioms) "#audit " &"project" ppSpace &"axioms" : command

elab_rules : command
  | `(#print certificates $identifier:ident) => do
      let declarations ← resolveDeclaration identifier
      for declaration in declarations do
        printAudit (← auditDeclaration declaration)
  | `(#audit certificates $identifier:ident) => do
      let declarations ← resolveDeclaration identifier
      for declaration in declarations do
        let audit ← auditDeclaration declaration
        printAudit audit
        if (auditStatus audit).startsWith "FAIL" then
          throwError m!"certificate audit failed for '{declaration}': trusted-compute use is not fully receipt-attributed or the theorem depends on an unexpected axiom"
  | `(#print project certificates) =>
      printProjectCertificateAudit false
  | `(#audit project certificates) =>
      printProjectCertificateAudit true
  | `(#print project axioms) =>
      printProjectAxiomAudit false
  | `(#audit project axioms) =>
      printProjectAxiomAudit true

end SparkInterval.Audit

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.QOrderManifestWire
import SparkInterval.Dirichlet.CompletedFactorStreamingWire

/-!
# Production-scale streaming checker for the Dirichlet q-order manifest

The legacy `QOrderManifestWire.parseManifest` deliberately exposes a convenient
sorted source projection.  Materialising and merge-sorting that projection is
not suitable for the 292,500-record production manifest.  This module checks
the same production wire without sorting:

* the record parser is total and the exact file size is checked before it runs;
* one tail-recursive pass checks every formulaic `(q, sampleCount)` row and
  accumulates the exact row and sample totals;
* one hash-set pass proves that execution-order moduli are distinct;
* one bounded source-range pass checks membership of every possible modulus,
  so coverage is checked directly rather than inferred from a row count;
* source-order, execution-order, and complete-file SHA-256 values are checked.

Only one parsed-record list is retained, because its execution order is needed
by the downstream resident-phase projection.  No sorted record copy is made.
The checker also builds one packed formulaic source body (2,340,000 bytes for
the production range) for its source-order digest; that temporary byte array
is not part of the returned manifest.

This is a pure Lean wire checker.  It uses no FFI, `unsafe`, `native_decide`,
axiom, external process, or platform arithmetic.  Digest equality identifies
the checked byte streams; as usual, cryptographic collision resistance is not
a Lean theorem.
-/

set_option autoImplicit false
set_option maxRecDepth 5000000

namespace SparkInterval.Dirichlet.QOrderManifestStreamingWire

open SparkInterval.Certificate
open SparkInterval.Dirichlet.QOrderManifestWire

/-! ## Header and exact source-row predicates -/

/-- A source row has exactly the formulaic primitive-modulus geometry, not
merely a sample count below the source bound. -/
def exactSourceRecord (record : ScheduleRecord) : Prop :=
  sourceQStart ≤ record.q ∧
    record.q ≤ sourceQStop ∧
    hasPrimitiveCharacterModulus record.q = true ∧
    record.sampleCount = sourceSampleCount record.q

instance (record : ScheduleRecord) : Decidable (exactSourceRecord record) := by
  unfold exactSourceRecord
  infer_instance

/-- Header-only parser.  It duplicates the small fixed-width parse rather than
calling the legacy materialising parser. -/
def parseHeaderOnly (raw : ByteArray) : Option Header := do
  let magicBytes ← checkedSlice? raw 0 8
  let version ← readU32LE raw 8
  let classificationCode ← readU32LE raw 12
  let classification ← decodeClassification classificationCode
  let rosterVersion ← readU32LE raw 16
  let qStart ← readU32LE raw 20
  let qStop ← readU32LE raw 24
  let encodedRecordBytes ← readU32LE raw 28
  let qCount ← readU64LE raw 32
  let tRowCount ← readU64LE raw 40
  let sourceRosterSHA256 ← readDigest raw 48
  let executionOrderSHA256 ← readDigest raw 80
  let header : Header := {
    magicBytes
    version
    classification
    rosterVersion
    qStart
    qStop
    encodedRecordBytes
    qCount
    tRowCount
    sourceRosterSHA256
    executionOrderSHA256
  }
  if _ : header.StructurallyValid then some header else none

def fullSourceHeader (header : Header) : Prop :=
  header.StructurallyValid ∧
    header.classification = .fullSource ∧
    header.qStart = sourceQStart ∧
    header.qStop = sourceQStop ∧
    header.qCount = sourceQCount ∧
    header.tRowCount = sourceTRowCount

instance (header : Header) : Decidable (fullSourceHeader header) := by
  unfold fullSourceHeader
  infer_instance

/-! ## Tail-recursive geometry scan -/

structure RecordGeometry where
  rowCount : Nat
  sampleTotal : Nat
  deriving Repr, DecidableEq, BEq

/-- Validate exact source rows while accumulating their two production
totals.  Both accumulators make the executable recursion tail-recursive. -/
def scanRecordGeometry :
    List ScheduleRecord → Nat → Nat → Option RecordGeometry
  | [], rowCount, sampleTotal =>
      some { rowCount, sampleTotal }
  | record :: rest, rowCount, sampleTotal =>
      if _ : exactSourceRecord record then
        scanRecordGeometry rest (rowCount + 1)
          (sampleTotal + record.sampleCount)
      else
        none

theorem scanRecordGeometry_sound
    {records : List ScheduleRecord} {initialCount initialTotal : Nat}
    {summary : RecordGeometry}
    (hscan :
      scanRecordGeometry records initialCount initialTotal = some summary) :
    (∀ record ∈ records, exactSourceRecord record) ∧
      summary.rowCount = initialCount + records.length ∧
      summary.sampleTotal =
        initialTotal + (records.map ScheduleRecord.sampleCount).sum := by
  induction records generalizing initialCount initialTotal with
  | nil =>
      simp [scanRecordGeometry] at hscan
      cases hscan
      simp
  | cons record rest ih =>
      simp only [scanRecordGeometry] at hscan
      split at hscan
      · rename_i hexact
        rcases ih hscan with ⟨hrest, hcount, htotal⟩
        refine ⟨?_, ?_, ?_⟩
        · intro candidate hcandidate
          simp only [List.mem_cons] at hcandidate
          rcases hcandidate with rfl | hcandidate
          · exact hexact
          · exact hrest candidate hcandidate
        · simp only [List.length_cons]
          omega
        · simp only [List.map_cons, List.sum_cons]
          omega
      · simp at hscan

/-! ## Linear distinctness and exact coverage -/

/-- Insert every execution-order modulus, failing on the first duplicate.
The returned set is reused by the exact source-coverage pass. -/
def collectFresh :
    List ScheduleRecord → Std.HashSet Nat → Option (Std.HashSet Nat)
  | [], seen => some seen
  | record :: rest, seen =>
      if seen.contains record.q then
        none
      else
        collectFresh rest (seen.insert record.q)

theorem collectFresh_sound
    {records : List ScheduleRecord} {seen result : Std.HashSet Nat}
    (hcollect : collectFresh records seen = some result) :
    (records.map ScheduleRecord.q).Nodup ∧
      (∀ record ∈ records, record.q ∉ seen) ∧
      (∀ q : Nat, q ∈ result ↔ q ∈ seen ∨ q ∈ records.map ScheduleRecord.q) := by
  induction records generalizing seen with
  | nil =>
      simp [collectFresh] at hcollect
      cases hcollect
      simp
  | cons record rest ih =>
      unfold collectFresh at hcollect
      cases hcontains : seen.contains record.q with
      | true =>
          simp [hcontains] at hcollect
      | false =>
          have htail :
              collectFresh rest (seen.insert record.q) = some result := by
            simpa [hcontains] using hcollect
          rcases ih htail with ⟨hnodup, hfresh, hmembers⟩
          have hheadFresh : record.q ∉ seen :=
            Std.HashSet.contains_eq_false_iff_not_mem.mp hcontains
          have hheadNotIn : record.q ∉ rest.map ScheduleRecord.q := by
            intro hmember
            rcases List.mem_map.mp hmember with
              ⟨tailRecord, htailRecord, hq⟩
            have htailFresh : tailRecord.q ∉ seen.insert record.q :=
              hfresh tailRecord htailRecord
            apply htailFresh
            rw [Std.HashSet.mem_insert]
            exact Or.inl (by simpa using hq.symm)
          refine ⟨List.nodup_cons.mpr ⟨hheadNotIn, hnodup⟩, ?_, ?_⟩
          · intro candidate hcandidate
            simp only [List.mem_cons] at hcandidate
            rcases hcandidate with rfl | hcandidate
            · exact hheadFresh
            · have htailFresh : candidate.q ∉ seen.insert record.q :=
                hfresh candidate hcandidate
              intro hseen
              apply htailFresh
              rw [Std.HashSet.mem_insert]
              exact Or.inr hseen
          · intro q
            rw [hmembers]
            rw [Std.HashSet.mem_insert]
            simp only [List.map_cons, List.mem_cons]
            simp only [beq_iff_eq]
            tauto

/-- Compare set membership with the formulaic predicate for every integer in
one consecutive source window.  No range list is allocated. -/
def checkCoverageWindow
    (seen : Std.HashSet Nat) : Nat → Nat → Bool
  | _, 0 => true
  | q, remaining + 1 =>
      if seen.contains q == hasPrimitiveCharacterModulus q then
        checkCoverageWindow seen (q + 1) remaining
      else
        false

theorem checkCoverageWindow_sound
    {seen : Std.HashSet Nat} {q count : Nat}
    (hcheck : checkCoverageWindow seen q count = true) :
    ∀ offset < count,
      seen.contains (q + offset) =
        hasPrimitiveCharacterModulus (q + offset) := by
  induction count generalizing q with
  | zero =>
      simp
  | succ count ih =>
      unfold checkCoverageWindow at hcheck
      split at hcheck
      · rename_i hhead
        intro offset hoffset
        cases offset with
        | zero =>
            simpa using hhead
        | succ offset =>
            have htail :
                checkCoverageWindow seen (q + 1) count = true := hcheck
            have h := ih htail offset (by omega)
            simpa [Nat.add_assoc, Nat.add_comm, Nat.add_left_comm] using h
      · simp at hcheck

def sourceWindowCount : Nat :=
  sourceQStop - sourceQStart + 1

def checkExactSourceCoverage (seen : Std.HashSet Nat) : Bool :=
  checkCoverageWindow seen sourceQStart sourceWindowCount

theorem checkExactSourceCoverage_sound
    {seen : Std.HashSet Nat}
    (hcheck : checkExactSourceCoverage seen = true) :
    ∀ q : Nat, sourceQStart ≤ q → q ≤ sourceQStop →
      (q ∈ seen ↔ hasPrimitiveCharacterModulus q = true) := by
  intro q hstart hstop
  have hwindow :
      seen.contains q = hasPrimitiveCharacterModulus q := by
    have hoffset : q - sourceQStart < sourceWindowCount := by
      unfold sourceWindowCount
      omega
    have h :=
      checkCoverageWindow_sound hcheck (q - sourceQStart) hoffset
    have hq : sourceQStart + (q - sourceQStart) = q := by omega
    simpa [checkExactSourceCoverage, hq] using h
  cases hprimitive : hasPrimitiveCharacterModulus q with
  | false =>
      have hnot : q ∉ seen :=
        Std.HashSet.contains_eq_false_iff_not_mem.mp
          (by simpa [hprimitive] using hwindow)
      simp [hnot]
  | true =>
      have hmem : q ∈ seen := by
        simpa [hprimitive] using hwindow
      simp [hmem]

/-! ## Canonical source byte stream -/

def pushEncodedLE4 (bytes : ByteArray) (value : Nat) : ByteArray :=
  bytes
    |>.push (UInt8.ofNat (value % 256))
    |>.push (UInt8.ofNat ((value / 256) % 256))
    |>.push (UInt8.ofNat ((value / 65536) % 256))
    |>.push (UInt8.ofNat ((value / 16777216) % 256))

def pushScheduleRecord
    (bytes : ByteArray) (record : ScheduleRecord) : ByteArray :=
  pushEncodedLE4 (pushEncodedLE4 bytes record.q) record.sampleCount

theorem pushEncodedLE4_toList (bytes : ByteArray) (value : Nat) :
    (pushEncodedLE4 bytes value).toList =
      bytes.toList ++ encodeLE 4 value := by
  rw [SHA256.byteArrayToList_eq_dataToList,
    SHA256.byteArrayToList_eq_dataToList]
  simp [pushEncodedLE4, encodeLE, ByteArray.data_push,
    Array.toList_push]
  norm_num [List.range_succ, Nat.pow_succ]

theorem pushScheduleRecord_toList
    (bytes : ByteArray) (record : ScheduleRecord) :
    (pushScheduleRecord bytes record).toList =
      bytes.toList ++ record.wireBytes := by
  unfold pushScheduleRecord ScheduleRecord.wireBytes
  rw [pushEncodedLE4_toList, pushEncodedLE4_toList]
  simp [List.append_assoc]

/-- Source-shaped recursive roster used to specify the packed streaming
generator without allocating a `List.range` in the checker. -/
def formulaicWindowRoster : Nat → Nat → List ScheduleRecord
  | _, 0 => []
  | q, remaining + 1 =>
      let rest := formulaicWindowRoster (q + 1) remaining
      if hasPrimitiveCharacterModulus q then
        { q, sampleCount := sourceSampleCount q } :: rest
      else
        rest

/-- Tail-recursive source-order byte generator.  This is independent of the
execution permutation stored in the manifest. -/
def buildFormulaicSourceBodyAux :
    Nat → Nat → ByteArray → ByteArray
  | _, 0, bytes => bytes
  | q, remaining + 1, bytes =>
      let next :=
        if hasPrimitiveCharacterModulus q then
          pushScheduleRecord bytes
            { q, sampleCount := sourceSampleCount q }
        else
          bytes
      buildFormulaicSourceBodyAux (q + 1) remaining next

def formulaicSourceBody : ByteArray :=
  buildFormulaicSourceBodyAux sourceQStart sourceWindowCount ByteArray.empty

theorem buildFormulaicSourceBodyAux_toList
    (q count : Nat) (initial : ByteArray) :
    (buildFormulaicSourceBodyAux q count initial).toList =
      initial.toList ++
        (formulaicWindowRoster q count).flatMap
          ScheduleRecord.wireBytes := by
  induction count generalizing q initial with
  | zero =>
      simp [buildFormulaicSourceBodyAux, formulaicWindowRoster]
  | succ count ih =>
      simp only [buildFormulaicSourceBodyAux, formulaicWindowRoster]
      split
      · rw [ih]
        rw [pushScheduleRecord_toList]
        simp [List.append_assoc]
      · rw [ih]

def sourceDigestInput : ByteArray :=
  sourceRosterDomain.toUTF8.append formulaicSourceBody

def executionDigestInput (raw : ByteArray) : ByteArray :=
  executionOrderDomain.toUTF8.append
    (raw.extract headerBytes raw.size)

/-- Production source-order digest.  The domain prefix and generated source
body are viewed virtually by the packed SHA implementation. -/
def formulaicSourceSHA256 : String :=
  SHA256.digestDomainSlice sourceRosterDomain formulaicSourceBody
    0 formulaicSourceBody.size

/-- Production execution-order digest.  This hashes the body slice of the
original wire directly, without allocating an extracted copy. -/
def executionOrderSHA256 (raw : ByteArray) : String :=
  SHA256.digestDomainSlice executionOrderDomain raw headerBytes raw.size

theorem formulaicSourceSHA256_eq_spec :
    formulaicSourceSHA256 = SHA256.digestByteArray sourceDigestInput := by
  unfold formulaicSourceSHA256 sourceDigestInput
  simpa using
    SHA256.digestDomainSlice_eq_digestByteArray_append_extract
      sourceRosterDomain formulaicSourceBody 0 formulaicSourceBody.size

theorem executionOrderSHA256_eq_spec (raw : ByteArray) :
    executionOrderSHA256 raw =
      SHA256.digestByteArray (executionDigestInput raw) := by
  unfold executionOrderSHA256 executionDigestInput
  exact
    SHA256.digestDomainSlice_eq_digestByteArray_append_extract
      executionOrderDomain raw headerBytes raw.size

/-! ## Streaming manifest and checker -/

structure StreamingManifest where
  header : Header
  records : List ScheduleRecord
  geometry : RecordGeometry
  wireSize : Nat
  deriving DecidableEq

def StreamingManifest.ExactSourceCoverage
    (manifest : StreamingManifest) : Prop :=
  ∀ q : Nat, sourceQStart ≤ q → q ≤ sourceQStop →
    (q ∈ manifest.records.map ScheduleRecord.q ↔
      hasPrimitiveCharacterModulus q = true)

def StreamingManifest.IsValid
    (raw : ByteArray) (manifest : StreamingManifest) : Prop :=
  fullSourceHeader manifest.header ∧
    parseHeaderOnly raw = some manifest.header ∧
    parseRecords raw manifest.header.qCount headerBytes =
      some manifest.records ∧
    (∀ record ∈ manifest.records, exactSourceRecord record) ∧
    (manifest.records.map ScheduleRecord.q).Nodup ∧
    manifest.ExactSourceCoverage ∧
    manifest.geometry.rowCount = manifest.header.qCount ∧
    manifest.geometry.sampleTotal = manifest.header.tRowCount ∧
    manifest.records.length = manifest.geometry.rowCount ∧
    (manifest.records.map ScheduleRecord.sampleCount).sum =
      manifest.geometry.sampleTotal ∧
    manifest.wireSize = raw.size ∧
    manifest.wireSize =
      headerBytes + manifest.header.qCount * recordBytes ∧
    byteArrayLowerHex manifest.header.sourceRosterSHA256 =
      formulaicSourceSHA256 ∧
    byteArrayLowerHex manifest.header.executionOrderSHA256 =
      executionOrderSHA256 raw ∧
    byteArrayLowerHex manifest.header.sourceRosterSHA256 =
      pinnedSourceRosterSHA256 ∧
    byteArrayLowerHex manifest.header.executionOrderSHA256 =
      pinnedExecutionOrderSHA256 ∧
    SHA256.digestByteArray raw = pinnedManifestSHA256

def checkFullSourceManifest
    (raw : ByteArray) : Option StreamingManifest :=
  if headerBytes ≤ raw.size then
    match parseHeaderOnly raw with
    | none => none
    | some header =>
        if _ : fullSourceHeader header then
          if raw.size = headerBytes + header.qCount * recordBytes then
            match parseRecords raw header.qCount headerBytes with
            | none => none
            | some records =>
                match scanRecordGeometry records 0 0 with
                | none => none
                | some geometry =>
                    if geometry.rowCount = header.qCount &&
                        geometry.sampleTotal = header.tRowCount then
                      match collectFresh records
                          (Std.HashSet.emptyWithCapacity header.qCount) with
                      | none => none
                      | some seen =>
                          let sourceSHA256 := formulaicSourceSHA256
                          let executionSHA256 := executionOrderSHA256 raw
                          let manifestSHA256 := SHA256.digestByteArray raw
                          if checkExactSourceCoverage seen then
                            if byteArrayLowerHex header.sourceRosterSHA256 =
                                sourceSHA256 then
                              if byteArrayLowerHex
                                  header.executionOrderSHA256 =
                                  executionSHA256 then
                                if byteArrayLowerHex
                                    header.sourceRosterSHA256 =
                                    pinnedSourceRosterSHA256 then
                                  if byteArrayLowerHex
                                      header.executionOrderSHA256 =
                                      pinnedExecutionOrderSHA256 then
                                    if manifestSHA256 =
                                        pinnedManifestSHA256 then
                                      some {
                                        header
                                        records
                                        geometry
                                        wireSize := raw.size
                                      }
                                    else none
                                  else none
                                else none
                              else none
                            else none
                          else none
                    else none
          else none
        else none
  else none

theorem checkFullSourceManifest_sound
    {raw : ByteArray} {manifest : StreamingManifest}
    (hcheck : checkFullSourceManifest raw = some manifest) :
    manifest.IsValid raw := by
  unfold checkFullSourceManifest at hcheck
  have hminimum : headerBytes ≤ raw.size := by
    by_contra hminimum
    simp [hminimum] at hcheck
  simp only [hminimum, if_pos] at hcheck
  cases hheader : parseHeaderOnly raw with
  | none =>
      simp only [hheader] at hcheck
      contradiction
  | some header =>
      simp only [hheader] at hcheck
      have hfull : fullSourceHeader header := by
        by_contra hfull
        simp [hfull] at hcheck
      simp only [dif_pos hfull] at hcheck
      have hsize :
          raw.size = headerBytes + header.qCount * recordBytes := by
        by_contra hsize
        simp [hsize] at hcheck
      simp only [hsize, if_pos] at hcheck
      cases hrecords :
          parseRecords raw header.qCount headerBytes with
      | none =>
          simp only [hrecords] at hcheck
          contradiction
      | some records =>
          simp only [hrecords] at hcheck
          cases hgeometry :
              scanRecordGeometry records 0 0 with
          | none =>
              simp only [hgeometry] at hcheck
              contradiction
          | some geometry =>
              simp only [hgeometry] at hcheck
              have htotals :
                  geometry.rowCount = header.qCount &&
                    geometry.sampleTotal = header.tRowCount := by
                by_contra htotals
                simp [htotals] at hcheck
              simp only [htotals, if_pos] at hcheck
              cases hfresh :
                  collectFresh records
                    (Std.HashSet.emptyWithCapacity header.qCount) with
              | none =>
                  simp only [hfresh] at hcheck
                  contradiction
              | some seen =>
                  simp only [hfresh] at hcheck
                  have hcoverage :
                      checkExactSourceCoverage seen = true := by
                    by_contra hcoverage
                    simp [hcoverage] at hcheck
                  simp only [hcoverage, if_pos] at hcheck
                  have hsourceDigest :
                      byteArrayLowerHex header.sourceRosterSHA256 =
                        formulaicSourceSHA256 := by
                    by_contra hsourceDigest
                    simp [hsourceDigest] at hcheck
                  simp only [hsourceDigest, if_pos] at hcheck
                  have hexecutionDigest :
                      byteArrayLowerHex header.executionOrderSHA256 =
                        executionOrderSHA256 raw := by
                    by_contra hexecutionDigest
                    simp [hexecutionDigest] at hcheck
                  simp only [hexecutionDigest, if_pos] at hcheck
                  have hsourceDigestPin :
                      formulaicSourceSHA256 =
                        pinnedSourceRosterSHA256 := by
                    by_contra hpin
                    simp [hpin] at hcheck
                  have hsourcePin :
                      byteArrayLowerHex header.sourceRosterSHA256 =
                        pinnedSourceRosterSHA256 :=
                    hsourceDigest.trans hsourceDigestPin
                  simp only [hsourceDigestPin, if_pos] at hcheck
                  have hexecutionDigestPin :
                      executionOrderSHA256 raw =
                        pinnedExecutionOrderSHA256 := by
                    by_contra hpin
                    simp [hpin] at hcheck
                  have hexecutionPin :
                      byteArrayLowerHex header.executionOrderSHA256 =
                        pinnedExecutionOrderSHA256 :=
                    hexecutionDigest.trans hexecutionDigestPin
                  simp only [hexecutionDigestPin, if_pos] at hcheck
                  have hmanifestPin :
                      SHA256.digestByteArray raw = pinnedManifestSHA256 := by
                    by_contra hpin
                    simp [hpin] at hcheck
                  simp only [hmanifestPin, if_pos] at hcheck
                  cases hcheck
                  rcases scanRecordGeometry_sound hgeometry with
                    ⟨hexact, hcount, htotal⟩
                  rcases collectFresh_sound hfresh with
                    ⟨hnodup, _, hset⟩
                  have hcover :
                      ∀ q : Nat,
                        sourceQStart ≤ q →
                        q ≤ sourceQStop →
                        (q ∈ records.map ScheduleRecord.q ↔
                          hasPrimitiveCharacterModulus q = true) := by
                    intro q hqStart hqStop
                    have hset' :
                        q ∈ seen ↔ q ∈ records.map ScheduleRecord.q := by
                      simpa using hset q
                    rw [← hset']
                    exact
                      checkExactSourceCoverage_sound
                        hcoverage q hqStart hqStop
                  have htotals' :
                      geometry.rowCount = header.qCount ∧
                        geometry.sampleTotal = header.tRowCount := by
                    simpa [Bool.and_eq_true] using htotals
                  refine
                    ⟨hfull, hheader, hrecords, hexact, hnodup,
                      hcover, htotals'.1, htotals'.2, ?_,
                      ?_, hsize.symm, rfl, hsourceDigest,
                      hexecutionDigest, hsourcePin,
                      hexecutionPin, hmanifestPin⟩
                  · simpa using hcount.symm
                  · simpa using htotal.symm

theorem valid_formulaic_record_iff
    {raw : ByteArray} {manifest : StreamingManifest}
    (hvalid : manifest.IsValid raw) (record : ScheduleRecord) :
    record ∈ manifest.records ↔ exactSourceRecord record := by
  constructor
  · intro hrecord
    exact hvalid.2.2.2.1 record hrecord
  · intro hexact
    have hq :
        record.q ∈ manifest.records.map ScheduleRecord.q := by
      exact
        (hvalid.2.2.2.2.2.1 record.q hexact.1 hexact.2.1).2
          hexact.2.2.1
    rcases List.mem_map.mp hq with
      ⟨candidate, hcandidate, hcandidateQ⟩
    have hcandidateExact :=
      hvalid.2.2.2.1 candidate hcandidate
    have hcandidateSamples :
        candidate.sampleCount = record.sampleCount := by
      rw [hcandidateExact.2.2.2, hexact.2.2.2, hcandidateQ]
    have hrecordsEqual : candidate = record := by
      cases candidate
      cases record
      simp_all
    simpa [hrecordsEqual] using hcandidate

theorem checked_formulaic_record_iff
    {raw : ByteArray} {manifest : StreamingManifest}
    (hcheck : checkFullSourceManifest raw = some manifest)
    (record : ScheduleRecord) :
    record ∈ manifest.records ↔ exactSourceRecord record :=
  valid_formulaic_record_iff (checkFullSourceManifest_sound hcheck) record

/-! ## Exact downstream resident-phase projection -/

def StreamingManifest.phaseCompletedFactorRoster
    (manifest : StreamingManifest)
    (phase : CompletedFactorWire.PinnedPhase) :
    List CompletedFactorWire.QSample :=
  manifest.records.filterMap fun record =>
    if phase.firstTIndex < record.sampleCount then
      some {
        q := record.q
        sampleCount := phaseSampleCount phase record
      }
    else
      none

def fullSourceExpectations?
    (manifest : StreamingManifest) (phaseIndex : Nat)
    (producerIdentitySHA256 : ByteArray) :
    Option CompletedFactorWire.FullSourceExpectations := do
  let phase ← CompletedFactorWire.pinnedPhase? phaseIndex
  let phaseScheduleSHA256 ←
    CompletedFactorWire.pinnedPhaseScheduleSHA256? phaseIndex
  pure {
    phaseIndex
    phase
    roster := manifest.phaseCompletedFactorRoster phase
    scheduleManifestSHA256 :=
      CompletedFactorWire.pinnedSourceScheduleManifestSHA256
    executionOrderSHA256 :=
      CompletedFactorWire.pinnedSourceExecutionOrderSHA256
    phaseScheduleSHA256
    producerIdentitySHA256
  }

/-- End-to-end optimized wire check.  The q-order checker supplies the exact
execution-order phase roster directly to the streaming factor-artifact
checker, so neither side introduces a metadata-only replacement roster. -/
def checkScheduledFullSourceBundle
    (scheduleRaw : ByteArray) (phaseIndex : Nat)
    (producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray) :
    Bool :=
  match checkFullSourceManifest scheduleRaw with
  | none => false
  | some manifest =>
      match fullSourceExpectations? manifest phaseIndex
          producerIdentitySHA256 with
      | none => false
      | some expected =>
          CompletedFactorStreamingWire.checkFullSourceBundle expected
            gammaRaw stepRaw checkpointRaw

def ValidatedScheduledFullSourceBundle
    (scheduleRaw : ByteArray) (phaseIndex : Nat)
    (producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray) :
    Prop :=
  ∃ manifest : StreamingManifest,
    ∃ expected : CompletedFactorWire.FullSourceExpectations,
      checkFullSourceManifest scheduleRaw = some manifest ∧
      fullSourceExpectations? manifest phaseIndex producerIdentitySHA256 =
        some expected ∧
      CompletedFactorStreamingWire.ValidatedFullSourceBundle expected
        gammaRaw stepRaw checkpointRaw

theorem checkScheduledFullSourceBundle_sound
    {scheduleRaw : ByteArray} {phaseIndex : Nat}
    {producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkScheduledFullSourceBundle scheduleRaw phaseIndex
        producerIdentitySHA256 gammaRaw stepRaw checkpointRaw = true) :
    ValidatedScheduledFullSourceBundle scheduleRaw phaseIndex
      producerIdentitySHA256 gammaRaw stepRaw checkpointRaw := by
  unfold checkScheduledFullSourceBundle at hcheck
  cases hschedule : checkFullSourceManifest scheduleRaw with
  | none =>
      simp [hschedule] at hcheck
  | some manifest =>
      cases hexpected :
          fullSourceExpectations? manifest phaseIndex
            producerIdentitySHA256 with
      | none =>
          simp [hschedule, hexpected] at hcheck
      | some expected =>
          refine ⟨manifest, expected, hschedule, hexpected, ?_⟩
          have hfactor :
              CompletedFactorStreamingWire.checkFullSourceBundle expected
                gammaRaw stepRaw checkpointRaw = true := by
            simpa [hschedule, hexpected] using hcheck
          exact
            CompletedFactorStreamingWire.checkFullSourceBundle_sound hfactor

theorem checked_full_source_exact_phase_roster
    {raw : ByteArray} {manifest : StreamingManifest}
    {phaseIndex : Nat} {producerIdentitySHA256 : ByteArray}
    {expected : CompletedFactorWire.FullSourceExpectations}
    (_hcheck : checkFullSourceManifest raw = some manifest)
    (hexpected :
      fullSourceExpectations? manifest phaseIndex producerIdentitySHA256 =
        some expected) :
    ∃ phase : CompletedFactorWire.PinnedPhase,
      CompletedFactorWire.pinnedPhase? phaseIndex = some phase ∧
      expected.roster = manifest.phaseCompletedFactorRoster phase := by
  unfold fullSourceExpectations? at hexpected
  cases hphase : CompletedFactorWire.pinnedPhase? phaseIndex with
  | none => simp [hphase] at hexpected
  | some phase =>
      cases hdigest :
          CompletedFactorWire.pinnedPhaseScheduleSHA256? phaseIndex with
      | none => simp [hphase, hdigest] at hexpected
      | some phaseDigest =>
          simp [hphase, hdigest] at hexpected
          cases hexpected
          exact ⟨phase, rfl, rfl⟩

/-- The accepted checkpoint stream is walked against exactly the resident
phase projection of the checked execution-order manifest. -/
theorem checkScheduledFullSourceBundle_exactRoster
    {scheduleRaw : ByteArray} {phaseIndex : Nat}
    {producerIdentitySHA256 gammaRaw stepRaw checkpointRaw : ByteArray}
    (hcheck :
      checkScheduledFullSourceBundle scheduleRaw phaseIndex
        producerIdentitySHA256 gammaRaw stepRaw checkpointRaw = true) :
    ∃ manifest : StreamingManifest,
      ∃ phase : CompletedFactorWire.PinnedPhase,
          ∃ expected : CompletedFactorWire.FullSourceExpectations,
          ∃ bundle : CompletedFactorStreamingWire.Bundle,
            checkFullSourceManifest scheduleRaw = some manifest ∧
            CompletedFactorWire.pinnedPhase? phaseIndex = some phase ∧
            expected.roster =
              manifest.phaseCompletedFactorRoster phase ∧
            CompletedFactorStreamingWire.scanCheckpointArtifact
                expected checkpointRaw =
              some bundle.checkpoint ∧
            CompletedFactorStreamingWire.CheckpointRowsAt checkpointRaw
              (bundle.checkpoint.header.tIndexStopExclusive -
                bundle.checkpoint.header.firstTIndex)
              bundle.checkpoint.header.checkpointSpan expected.roster
              CompletedFactorWire.checkpointHeaderBytes 0
              {
                stopOffset := bundle.checkpoint.stopOffset
                checkpointCount :=
                  bundle.checkpoint.scannedCheckpointCount
              } := by
  rcases checkScheduledFullSourceBundle_sound hcheck with
    ⟨manifest, expected, hschedule, hexpected, hvalidated⟩
  have hfactor :
      CompletedFactorStreamingWire.checkFullSourceBundle expected
        gammaRaw stepRaw checkpointRaw = true := by
    unfold checkScheduledFullSourceBundle at hcheck
    simpa [hschedule, hexpected] using hcheck
  rcases checked_full_source_exact_phase_roster hschedule hexpected with
    ⟨phase, hphase, hroster⟩
  rcases
      CompletedFactorStreamingWire.checkFullSourceBundle_exactRoster
        hfactor with
    ⟨bundle, hcheckpoint, _, hrows⟩
  exact
    ⟨manifest, phase, expected, bundle, hschedule, hphase, hroster,
      hcheckpoint, hrows⟩

end SparkInterval.Dirichlet.QOrderManifestStreamingWire

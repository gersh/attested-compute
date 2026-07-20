import SparkInterval.PTX.Semantics

/-!
# Pinned NVIDIA PTX 9.0 source transcription

This module records the exact NVIDIA document used to review the typed PTX
subset and gives a small, independent Lean transcription of its non-NaN f64
numeric clauses.  NVIDIA publishes these clauses as prose and pseudocode, not
as a machine-readable formal semantics.  Consequently, the citation records
below provide reviewable traceability; they are not a proof about the vendor
document, `ptxas`, SASS, a CUDA driver, or physical hardware.

The arithmetic transcription covers finite operands of `add.rm/rp.f64`,
`sub.rm/rp.f64`, and `mul.rm/rp.f64`.  The min/max transcription covers the
non-NaN numeric domain used by `F64Value`; signed zero is identified there.
PTX division is cited but intentionally has no current typed opcode or semantic
constructor.  That omission is explicit because a zeta implementation will
need directed division (or a separately proved replacement).
-/

set_option autoImplicit false

namespace SparkInterval.PTX.NvidiaPTX90

open SparkInterval

/-- Immutable identity of the NVIDIA source reviewed for this transcription. -/
structure SourcePin where
  publisher : String
  isaVersion : String
  toolkitArchive : String
  htmlUrl : String
  pdfUrl : String
  pdfSha256 : String
  deriving BEq, DecidableEq, Repr

/-- PTX ISA 9.0 as archived with CUDA Toolkit 13.0.2.

The digest was checked against the bytes served by the `pdfUrl`. -/
def sourcePin : SourcePin := {
  publisher := "NVIDIA Corporation"
  isaVersion := "9.0"
  toolkitArchive := "13.0.2"
  htmlUrl :=
    "https://docs.nvidia.com/cuda/archive/13.0.2/parallel-thread-execution/index.html"
  pdfUrl :=
    "https://docs.nvidia.com/cuda/archive/13.0.2/pdf/ptx_isa_9.0.pdf"
  pdfSha256 :=
    "207acfec55e860c94809b3a5c2d892f6fe70622105cd421a3c76d93617f6e76a"
}

/-- Architectures used by the two intended deployment profiles. -/
inductive TargetProfile where
  | sm90
  | sm121
  deriving BEq, DecidableEq, Repr

def TargetProfile.token : TargetProfile -> String
  | .sm90 => "sm_90"
  | .sm121 => "sm_121"

/-- The three module-level properties pinned by PTX emission. -/
structure ModuleProfile where
  version : String
  target : TargetProfile
  addressSize : Nat
  deriving BEq, DecidableEq, Repr

/-- DGX Spark/GB10 profile emitted by the current backend. -/
def dgxSparkProfile : ModuleProfile := {
  version := "9.0"
  target := .sm121
  addressSize := 64
}

/-- H100 profile.  It requires a separate `sm_90` emission path. -/
def h100Profile : ModuleProfile := {
  version := "9.0"
  target := .sm90
  addressSize := 64
}

/-- Text prefix determined by the three pinned module directives. -/
def ModuleProfile.directivePrefix (profile : ModuleProfile) : String :=
  ".version " ++ profile.version ++ "\n.target " ++ profile.target.token ++
    "\n.address_size " ++ toString profile.addressSize ++ "\n"

/-- Referenced clauses in the archived PTX 9.0 document. -/
inductive Clause where
  | semantics
  | typeInformation
  | addressesAsOperands
  | labelsAndFunctionNames
  | scalarConversions
  | roundingModifiers
  | parameterStateSpace
  | kernelFunctionParameters
  | globalStateSpace
  | integerAdd
  | integerMul
  | floatingGeneral
  | floatingAdd
  | floatingSub
  | floatingMul
  | floatingDiv
  | floatingMin
  | floatingMax
  | comparisonSetp
  | logicAnd
  | logicXor
  | dataMov
  | dataLd
  | dataSt
  | dataCvta
  | dataCvt
  | predicatedExecution
  | controlBra
  | controlRet
  | specialTid
  | specialNtid
  | specialCtaid
  | directiveVersion
  | directiveTarget
  | directiveAddressSize
  deriving BEq, DecidableEq, Repr

/-- A stable section/anchor reference into `sourcePin`. -/
structure ClauseReference where
  source : SourcePin
  sectionNumber : String
  anchor : String
  title : String
  deriving BEq, DecidableEq, Repr

private def mkReference (sectionNumber anchor title : String) : ClauseReference := {
  source := sourcePin
  sectionNumber
  anchor
  title
}

/-- Total citation table for the PTX clauses used by this library. -/
def Clause.reference : Clause -> ClauseReference
  | .semantics => mkReference "9.6" "semantics" "Semantics"
  | .typeInformation => mkReference "9.4" "type-information-for-instructions-and-operands"
      "Type information for instructions and operands"
  | .addressesAsOperands => mkReference "6.4.1" "addresses-as-operands"
      "Addresses as operands"
  | .labelsAndFunctionNames => mkReference "6.4.4"
      "labels-and-function-names-as-operands" "Labels and function names as operands"
  | .scalarConversions => mkReference "6.5.1" "scalar-conversions" "Scalar conversions"
  | .roundingModifiers => mkReference "6.5.2" "rounding-modifiers" "Rounding modifiers"
  | .parameterStateSpace => mkReference "5.1.6" "parameter-state-space"
      "Parameter state space"
  | .kernelFunctionParameters => mkReference "5.1.6.1" "kernel-function-parameters"
      "Kernel function parameters"
  | .globalStateSpace => mkReference "5.1.4" "global-state-space" "Global state space"
  | .integerAdd => mkReference "9.7.1.1" "integer-arithmetic-instructions-add"
      "Integer arithmetic: add"
  | .integerMul => mkReference "9.7.1.3" "integer-arithmetic-instructions-mul"
      "Integer arithmetic: mul"
  | .floatingGeneral => mkReference "9.7.3" "floating-point-instructions"
      "Floating-point instructions"
  | .floatingAdd => mkReference "9.7.3.3" "floating-point-instructions-add"
      "Floating point: add"
  | .floatingSub => mkReference "9.7.3.4" "floating-point-instructions-sub"
      "Floating point: sub"
  | .floatingMul => mkReference "9.7.3.5" "floating-point-instructions-mul"
      "Floating point: mul"
  | .floatingDiv => mkReference "9.7.3.8" "floating-point-instructions-div"
      "Floating point: div"
  | .floatingMin => mkReference "9.7.3.11" "floating-point-instructions-min"
      "Floating point: min"
  | .floatingMax => mkReference "9.7.3.12" "floating-point-instructions-max"
      "Floating point: max"
  | .comparisonSetp => mkReference "9.7.6.2"
      "comparison-and-selection-instructions-setp" "Comparison and selection: setp"
  | .logicAnd => mkReference "9.7.8.1" "logic-and-shift-instructions-and"
      "Logic and shift: and"
  | .logicXor => mkReference "9.7.8.3" "logic-and-shift-instructions-xor"
      "Logic and shift: xor"
  | .dataMov => mkReference "9.7.9.3" "data-movement-and-conversion-instructions-mov"
      "Data movement: mov"
  | .dataLd => mkReference "9.7.9.8" "data-movement-and-conversion-instructions-ld"
      "Data movement: ld"
  | .dataSt => mkReference "9.7.9.11" "data-movement-and-conversion-instructions-st"
      "Data movement: st"
  | .dataCvta => mkReference "9.7.9.20" "data-movement-and-conversion-instructions-cvta"
      "Data conversion: cvta"
  | .dataCvt => mkReference "9.7.9.21" "data-movement-and-conversion-instructions-cvt"
      "Data conversion: cvt"
  | .predicatedExecution => mkReference "9.3" "predicated-execution" "Predicated execution"
  | .controlBra => mkReference "9.7.12.3" "control-flow-instructions-bra"
      "Control flow: bra"
  | .controlRet => mkReference "9.7.12.6" "control-flow-instructions-ret"
      "Control flow: ret"
  | .specialTid => mkReference "10.1" "special-registers-tid" "Special register: tid"
  | .specialNtid => mkReference "10.2" "special-registers-ntid" "Special register: ntid"
  | .specialCtaid => mkReference "10.6" "special-registers-ctaid" "Special register: ctaid"
  | .directiveVersion => mkReference "11.1.1" "ptx-module-directives-version"
      "Module directive: version"
  | .directiveTarget => mkReference "11.1.2" "ptx-module-directives-target"
      "Module directive: target"
  | .directiveAddressSize => mkReference "11.1.3" "ptx-module-directives-address-size"
      "Module directive: address size"

def ClauseReference.url (reference : ClauseReference) : String :=
  reference.source.htmlUrl ++ "#" ++ reference.anchor

@[simp] theorem Clause.reference_source (clause : Clause) :
    clause.reference.source = sourcePin := by
  cases clause <;> rfl

/-- Primary normative clause for every opcode admitted by `allowedOpcodes`. -/
def opcodeClause : Opcode -> Clause
  | .ldParamU64 => .dataLd
  | .movU16 | .movU32 | .movB64 => .dataMov
  | .mulWideU32 | .mulLoU64 => .integerMul
  | .cvtU64U32 => .dataCvt
  | .addU64 => .integerAdd
  | .cvtaGlobalU64 => .dataCvta
  | .ldGlobalF64 => .dataLd
  | .stGlobalF64 | .stGlobalU8 => .dataSt
  | .xorB64 => .logicXor
  | .andB64 => .logicAnd
  | .setpEqU64 | .setpGeU64 => .comparisonSetp
  | .bra => .controlBra
  | .addRmF64 | .addRpF64 => .floatingAdd
  | .subRmF64 | .subRpF64 => .floatingSub
  | .mulRmF64 | .mulRpF64 => .floatingMul
  | .minF64 => .floatingMin
  | .maxF64 => .floatingMax
  | .ret => .controlRet

def opcodeCitation (opcode : Opcode) : ClauseReference :=
  (opcodeClause opcode).reference

/-- Supporting clauses that constrain types, addressing, state spaces, or rounding. -/
def opcodePrerequisiteClauses : Opcode -> List Clause
  | .ldParamU64 => [.parameterStateSpace, .kernelFunctionParameters, .addressesAsOperands]
  | .movU16 | .movU32 | .movB64 | .xorB64 | .andB64 => [.typeInformation]
  | .cvtU64U32 => [.scalarConversions]
  | .cvtaGlobalU64 => [.globalStateSpace]
  | .ldGlobalF64 | .stGlobalF64 | .stGlobalU8 =>
      [.addressesAsOperands, .globalStateSpace]
  | .bra => [.predicatedExecution, .labelsAndFunctionNames]
  | .addRmF64 | .addRpF64 | .subRmF64 | .subRpF64 |
      .mulRmF64 | .mulRpF64 => [.floatingGeneral, .roundingModifiers]
  | .minF64 | .maxF64 => [.floatingGeneral]
  | _ => []

def SpecialU32.clause : SpecialU32 -> Clause
  | .tidX => .specialTid
  | .ntidX => .specialNtid
  | .ctaidX => .specialCtaid

/-- Labels have no executable opcode, so their typed constructor is connected
to the label-operand clause directly. -/
def instructionClause (instruction : Instruction) : Clause :=
  match instruction.opcode with
  | some opcode => opcodeClause opcode
  | none => .labelsAndFunctionNames

/-- Every allowlisted opcode has a clause in the pinned PTX 9.0 source. -/
theorem allowedOpcode_has_pinned_clause {opcode : Opcode}
    (_hopcode : opcode ∈ allowedOpcodes) :
    ∃ clause, opcodeClause opcode = clause ∧ clause.reference.source = sourcePin := by
  exact ⟨opcodeClause opcode, rfl, Clause.reference_source _⟩

/-- Every typed instruction, including a lexical label, has a pinned clause. -/
theorem acceptedInstruction_has_pinned_clause (instruction : Instruction) :
    ∃ clause, instructionClause instruction = clause ∧
      clause.reference.source = sourcePin := by
  exact ⟨instructionClause instruction, rfl, Clause.reference_source _⟩

/-- The current typed compiler has no opcode whose primary clause is division. -/
theorem currentOpcode_has_no_division_clause (opcode : Opcode) :
    opcodeClause opcode ≠ .floatingDiv := by
  cases opcode <;> simp [opcodeClause]

theorem division_not_in_current_allowlist :
    ∀ opcode ∈ allowedOpcodes, opcodeClause opcode ≠ .floatingDiv := by
  intro opcode _hopcode
  exact currentOpcode_has_no_division_clause opcode

/-- Citation-only requirement left open for a full zeta arithmetic compiler. -/
def directedF64DivisionRequirement : ClauseReference :=
  Clause.floatingDiv.reference

/-- Independent operation names for the formally transcribed arithmetic slice. -/
inductive BinaryOp where
  | add
  | sub
  | mul
  deriving BEq, DecidableEq, Repr

/-- The two directed modes used by the generated interval kernels. -/
inductive RoundingMode where
  | towardNegative
  | towardPositive
  deriving BEq, DecidableEq, Repr

def BinaryOp.ofTyped : F64BinaryOp -> BinaryOp
  | .add => .add
  | .sub => .sub
  | .mul => .mul

def RoundingMode.ofTyped : DirectedRounding -> RoundingMode
  | .down => .towardNegative
  | .up => .towardPositive

/-- Exact real operation before one binary64 rounding step. -/
def exactBinary (op : BinaryOp) (left right : Real) : Real :=
  match op with
  | .add => left + right
  | .sub => left - right
  | .mul => left * right

/-- Finite-input numeric transcription of PTX 9.0 `rm`/`rp` f64 arithmetic. -/
noncomputable def evalFinite (op : BinaryOp) (rounding : RoundingMode)
    (left right : Real) : ExtBinary64 :=
  match rounding with
  | .towardNegative => Binary64Rounding.roundDown (exactBinary op left right)
  | .towardPositive => Binary64Rounding.roundUp (exactBinary op left right)

theorem evalFinite_towardNegative_le (op : BinaryOp) (left right : Real) :
    (evalFinite op .towardNegative left right).toEReal ≤
      (exactBinary op left right : EReal) := by
  simpa [evalFinite] using Binary64Rounding.roundDown_le (exactBinary op left right)

theorem le_evalFinite_towardPositive (op : BinaryOp) (left right : Real) :
    (exactBinary op left right : EReal) ≤
      (evalFinite op .towardPositive left right).toEReal := by
  simpa [evalFinite] using Binary64Rounding.le_roundUp (exactBinary op left right)

/-- Non-NaN numeric domain of the PTX min/max transcription. -/
inductive NumericValue where
  | negInf
  | finite (value : Real)
  | posInf

namespace NumericValue

def ofModel : F64Value -> NumericValue
  | .negInf => .negInf
  | .finite value => .finite value
  | .posInf => .posInf

def toModel : NumericValue -> F64Value
  | .negInf => .negInf
  | .finite value => .finite value
  | .posInf => .posInf

@[simp] theorem toModel_ofModel (value : F64Value) :
    (ofModel value).toModel = value := by
  cases value <;> rfl

end NumericValue

/-- PTX `min.f64` on the non-NaN numeric abstraction. -/
noncomputable def minimum : NumericValue -> NumericValue -> NumericValue
  | .negInf, _ => .negInf
  | _, .negInf => .negInf
  | .posInf, right => right
  | left, .posInf => left
  | .finite left, .finite right => .finite (min left right)

/-- PTX `max.f64` on the non-NaN numeric abstraction. -/
noncomputable def maximum : NumericValue -> NumericValue -> NumericValue
  | .posInf, _ => .posInf
  | _, .posInf => .posInf
  | .negInf, right => right
  | left, .negInf => left
  | .finite left, .finite right => .finite (max left right)

end SparkInterval.PTX.NvidiaPTX90

import SparkInterval.PTX.AST

/-!
# Deterministic PTX emitter and validator

`validate` is run by the executable before `emit`.  It checks register bounds,
label closure and uniqueness, the exact opcode allowlist, and resource limits.
The emitter is a total function over the typed AST and has no raw-code case.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

private def regPrefix : RegClass → String
  | .pred => "%p"
  | .byte => "%rs"
  | .u32 => "%r"
  | .u64 => "%rd"
  | .f64 => "%fd"

private def renderReg {kind : RegClass} (reg : Reg kind) : String :=
  regPrefix kind ++ toString reg.index

private def renderLabel (label : Label) : String :=
  "$L" ++ toString label.index

private def renderParameter : ParameterU64 → String
  | .rows => "sparkinterval_generated_param_rows"
  | .outputs => "sparkinterval_generated_param_outputs"
  | .rowCount => "sparkinterval_generated_param_row_count"

private def renderSpecial : SpecialU32 → String
  | .ctaidX => "%ctaid.x"
  | .ntidX => "%ntid.x"
  | .tidX => "%tid.x"

private def renderRounding : DirectedRounding → String
  | .down => "rm"
  | .up => "rp"

private def renderF64Op : F64BinaryOp → String
  | .add => "add"
  | .sub => "sub"
  | .mul => "mul"

private def hexDigit (n : Nat) : Char :=
  if n < 10 then Char.ofNat ('0'.toNat + n)
  else Char.ofNat ('a'.toNat + n - 10)

private def hexFixedAux : Nat → Nat → List Char
  | 0, _ => []
  | count + 1, value => hexFixedAux count (value / 16) ++ [hexDigit (value % 16)]

/-- Exactly sixteen lowercase digits, independent of host word size. -/
def hex64 (value : Nat) : String :=
  "0x" ++ String.ofList (hexFixedAux 16 value)

/-- Deterministic text for one typed instruction.  This function is public so
the compiler-correctness layer can relate the exact source line handed to
`ptxas` to its typed AST constructor. -/
def renderInstruction : Instruction → String
  | .loadParamU64 dst parameter =>
      s!"\tld.param.u64 {renderReg dst}, [{renderParameter parameter}];"
  | .movByte dst value =>
      s!"\tmov.u16 {renderReg dst}, {value.val};"
  | .movSpecialU32 dst source =>
      s!"\tmov.u32 {renderReg dst}, {renderSpecial source};"
  | .mulWideU32 dst left right =>
      s!"\tmul.wide.u32 {renderReg dst}, {renderReg left}, {renderReg right};"
  | .cvtU64U32 dst source =>
      s!"\tcvt.u64.u32 {renderReg dst}, {renderReg source};"
  | .addU64 dst left right =>
      s!"\tadd.u64 {renderReg dst}, {renderReg left}, {renderReg right};"
  | .addU64Immediate dst left right =>
      s!"\tadd.u64 {renderReg dst}, {renderReg left}, {right};"
  | .mulLoU64Immediate dst left right =>
      s!"\tmul.lo.u64 {renderReg dst}, {renderReg left}, {right};"
  | .cvtaGlobalU64 dst source =>
      s!"\tcvta.to.global.u64 {renderReg dst}, {renderReg source};"
  | .loadGlobalF64 dst base offset =>
      s!"\tld.global.b64 {renderReg dst}, [{renderReg base}+{offset}];"
  | .storeGlobalF64 base offset source =>
      s!"\tst.global.b64 [{renderReg base}+{offset}], {renderReg source};"
  | .storeGlobalByte base offset source =>
      s!"\tst.global.u8 [{renderReg base}+{offset}], {renderReg source};"
  | .movF64Bits dst bits =>
      s!"\tmov.b64 {renderReg dst}, {hex64 bits};"
  | .xorF64Sign dst source =>
      s!"\txor.b64 {renderReg dst}, {renderReg source}, 0x8000000000000000;"
  | .exponentBits dst source =>
      s!"\tand.b64 {renderReg dst}, {renderReg source}, 0x7ff0000000000000;"
  | .setpEqExponentMask dst source =>
      s!"\tsetp.eq.u64 {renderReg dst}, {renderReg source}, 0x7ff0000000000000;"
  | .setpGeU64 dst left right =>
      s!"\tsetp.ge.u64 {renderReg dst}, {renderReg left}, {renderReg right};"
  | .branchIf condition target =>
      s!"\t@{renderReg condition} bra {renderLabel target};"
  | .branch target => s!"\tbra {renderLabel target};"
  | .label label => renderLabel label ++ ":"
  | .binaryF64 op rounding dst left right =>
      s!"\t{renderF64Op op}.{renderRounding rounding}.f64 {renderReg dst}, " ++
        s!"{renderReg left}, {renderReg right};"
  | .minimumF64 dst left right =>
      s!"\tmin.f64 {renderReg dst}, {renderReg left}, {renderReg right};"
  | .maximumF64 dst left right =>
      s!"\tmax.f64 {renderReg dst}, {renderReg left}, {renderReg right};"
  | .ret => "\tret;"

private def instructionRegisters : Instruction → List (RegClass × Nat)
  | .loadParamU64 d _ => [(.u64, d.index)]
  | .movByte d _ => [(.byte, d.index)]
  | .movSpecialU32 d _ => [(.u32, d.index)]
  | .mulWideU32 d a b => [(.u64, d.index), (.u32, a.index), (.u32, b.index)]
  | .cvtU64U32 d s => [(.u64, d.index), (.u32, s.index)]
  | .addU64 d a b => [(.u64, d.index), (.u64, a.index), (.u64, b.index)]
  | .addU64Immediate d a _ => [(.u64, d.index), (.u64, a.index)]
  | .mulLoU64Immediate d a _ => [(.u64, d.index), (.u64, a.index)]
  | .cvtaGlobalU64 d s => [(.u64, d.index), (.u64, s.index)]
  | .loadGlobalF64 d b _ => [(.f64, d.index), (.u64, b.index)]
  | .storeGlobalF64 b _ s => [(.u64, b.index), (.f64, s.index)]
  | .storeGlobalByte b _ s => [(.u64, b.index), (.byte, s.index)]
  | .movF64Bits d _ => [(.f64, d.index)]
  | .xorF64Sign d s => [(.f64, d.index), (.f64, s.index)]
  | .exponentBits d s => [(.u64, d.index), (.f64, s.index)]
  | .setpEqExponentMask d s => [(.pred, d.index), (.u64, s.index)]
  | .setpGeU64 d a b => [(.pred, d.index), (.u64, a.index), (.u64, b.index)]
  | .branchIf p _ => [(.pred, p.index)]
  | .branch _ | .label _ | .ret => []
  | .binaryF64 _ _ d a b | .minimumF64 d a b | .maximumF64 d a b =>
      [(.f64, d.index), (.f64, a.index), (.f64, b.index)]

private def registerBound (counts : RegisterCounts) : RegClass → Nat
  | .pred => counts.pred
  | .byte => counts.byte
  | .u32 => counts.u32
  | .u64 => counts.u64
  | .f64 => counts.f64

private def validEntryName (name : String) : Bool :=
  name == "sparkinterval_generated"

private def duplicate? {α : Type} [BEq α] (values : List α) : Bool :=
  values.any fun value => (values.filter (· == value)).length != 1

/--
Validate the explicit allowlist and all cross-instruction structural bounds.
No emitted module bypasses this check in `sparkinterval-gen`.
-/
def validate (module : Module) : Except String Unit := do
  if !validEntryName module.entryName then
    throw "entry name is outside the singleton allowlist"
  if module.variableCount > 64 then
    throw "embedded variable count exceeds the Phase 5 ABI limit"
  let counts := module.registers
  if counts.pred == 0 || counts.byte == 0 || counts.u32 == 0 || counts.u64 == 0 ||
      counts.f64 == 0 then
    throw "every typed register class must have a nonempty declaration"
  if counts.pred > 4096 || counts.byte > 4096 || counts.u32 > 4096 || counts.u64 > 65536 ||
      counts.f64 > 65536 then
    throw "generated register declaration exceeds the Phase 5 resource limit"
  if module.body.isEmpty then throw "PTX body must not be empty"
  if module.body.size > 100000 then throw "PTX body exceeds 100000 instructions"
  for instruction in module.body do
    match instruction.opcode with
    | some opcode =>
        if !(allowedOpcodes.contains opcode) then
          throw s!"opcode escaped the explicit allowlist: {repr opcode}"
    | none => pure ()
    for (kind, index) in instructionRegisters instruction do
      if index >= registerBound counts kind then
        throw s!"{repr kind} register {index} is outside its declaration"
    match instruction with
    | .movF64Bits _ bits =>
        if bits ≥ 2 ^ 64 then throw "binary64 literal is outside 64 bits"
    | .addU64Immediate _ _ value | .mulLoU64Immediate _ _ value =>
        if value ≥ 2 ^ 64 then throw "u64 immediate is outside 64 bits"
    | .loadGlobalF64 _ _ offset | .storeGlobalF64 _ offset _ |
        .storeGlobalByte _ offset _ =>
        if offset ≥ 2 ^ 63 then throw "global-memory offset exceeds the Phase 5 limit"
    | _ => pure ()
  let labels := module.body.toList.filterMap fun
    | .label label => some label
    | _ => none
  if duplicate? labels then throw "PTX labels must be unique"
  for instruction in module.body do
    match instruction with
    | .branchIf _ target | .branch target =>
        if !(labels.contains target) then
          throw s!"branch target is undefined: {target.index}"
    | _ => pure ()
  match module.body.back? with
  | some .ret => pure ()
  | _ => throw "PTX body must end in ret"

private def declaration (kind : String) (regStem : String) (count : Nat) : String :=
  s!"\t.reg .{kind} %{regStem}<{count}>;"

/-- Deterministically render the complete module after validation has been
discharged.  Keeping this total rendering function separate makes the
successful-emission theorem below definitionally transparent. -/
def renderUnchecked (module : Module) : String :=
  let header := [
    ".version 9.0",
    ".target sm_121",
    ".address_size 64",
    "",
    ".visible .global .align 4 .u32 sparkinterval_generated_abi_version = 1;",
    s!".visible .global .align 4 .u32 sparkinterval_generated_variable_count = {module.variableCount};",
    "",
    s!".visible .entry {module.entryName}(",
    "\t.param .u64 sparkinterval_generated_param_rows,",
    "\t.param .u64 sparkinterval_generated_param_outputs,",
    "\t.param .u64 sparkinterval_generated_param_row_count",
    ")",
    "{",
    declaration "pred" "p" module.registers.pred,
    declaration "b16" "rs" module.registers.byte,
    declaration "u32" "r" module.registers.u32,
    declaration "b64" "rd" module.registers.u64,
    declaration "b64" "fd" module.registers.f64
  ]
  let lines := header ++ module.body.toList.map renderInstruction ++ ["}", ""]
  String.intercalate "\n" lines

/-- Deterministically render a validated typed module as PTX 9.0 for sm_121. -/
def emit (module : Module) : Except String String := do
  validate module
  return renderUnchecked module

/-- Successful emission is exactly the total rendering of the same typed
module; there is no untyped source-injection path. -/
theorem emit_success {module : Module} {text : String}
    (hemits : emit module = .ok text) :
    validate module = .ok () ∧ text = renderUnchecked module := by
  unfold emit at hemits
  cases hvalidate : validate module with
  | error message =>
      rw [hvalidate] at hemits
      cases hemits
  | ok value =>
      cases value
      rw [hvalidate] at hemits
      cases hemits
      constructor
      · rfl
      · rfl

/-- Once validation succeeds, emission cannot fail or choose different text. -/
theorem emit_of_validate {module : Module} (hvalidate : validate module = .ok ()) :
    emit module = .ok (renderUnchecked module) := by
  unfold emit
  rw [hvalidate]
  rfl

end SparkInterval.PTX

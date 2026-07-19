import Std

/-!
# Typed PTX syntax for generated interval kernels

This is deliberately not a string-wrapper around PTX.  The constructors expose
only the register classes and instructions needed by the Phase 5 polynomial
generator.  In particular, floating-point arithmetic requires an explicit
directed rounding mode; no constructor can express `rn`, `rz`, `fma`, or an
untyped arbitrary opcode.
-/

set_option autoImplicit false

namespace SparkInterval.PTX

/-- PTX register classes used by the generator. -/
inductive RegClass where
  | pred
  | byte
  | u32
  | u64
  | f64
  deriving BEq, DecidableEq, Repr

/-- A register whose class is tracked by the Lean type. -/
structure Reg (kind : RegClass) where
  index : Nat
  deriving BEq, DecidableEq, Repr, Inhabited

/-- The only floating-point rounding modes constructible in this AST. -/
inductive DirectedRounding where
  | down
  | up
  deriving BEq, DecidableEq, Repr

/-- The only directed binary64 arithmetic operations in the allowlist. -/
inductive F64BinaryOp where
  | add
  | sub
  | mul
  deriving BEq, DecidableEq, Repr

/-- Special 32-bit registers required to compute a CUDA global thread index. -/
inductive SpecialU32 where
  | ctaidX
  | ntidX
  | tidX
  deriving BEq, DecidableEq, Repr

/-- Kernel parameters have a fixed meaning and type. -/
inductive ParameterU64 where
  | rows
  | outputs
  | rowCount
  deriving BEq, DecidableEq, Repr

/-- Labels are numeric and are rendered deterministically. -/
structure Label where
  index : Nat
  deriving BEq, DecidableEq, Repr

/--
Typed PTX instructions accepted by the generator.

There is intentionally no escape hatch for an arbitrary instruction string.
The two bit-cast operations are named for their exact use in interval code,
rather than exposing an untyped general-purpose operation.
-/
inductive Instruction where
  | loadParamU64 (dst : Reg .u64) (parameter : ParameterU64)
  | movByte (dst : Reg .byte) (value : Fin 256)
  | movSpecialU32 (dst : Reg .u32) (source : SpecialU32)
  | mulWideU32 (dst : Reg .u64) (left right : Reg .u32)
  | cvtU64U32 (dst : Reg .u64) (source : Reg .u32)
  | addU64 (dst left right : Reg .u64)
  | addU64Immediate (dst left : Reg .u64) (right : Nat)
  | mulLoU64Immediate (dst left : Reg .u64) (right : Nat)
  | cvtaGlobalU64 (dst source : Reg .u64)
  | loadGlobalF64 (dst : Reg .f64) (base : Reg .u64) (offset : Nat)
  | storeGlobalF64 (base : Reg .u64) (offset : Nat) (source : Reg .f64)
  | storeGlobalByte (base : Reg .u64) (offset : Nat) (source : Reg .byte)
  | movF64Bits (dst : Reg .f64) (bits : Nat)
  | xorF64Sign (dst source : Reg .f64)
  | exponentBits (dst : Reg .u64) (source : Reg .f64)
  | setpEqExponentMask (dst : Reg .pred) (source : Reg .u64)
  | setpGeU64 (dst : Reg .pred) (left right : Reg .u64)
  | branchIf (condition : Reg .pred) (target : Label)
  | branch (target : Label)
  | label (label : Label)
  | binaryF64 (op : F64BinaryOp) (rounding : DirectedRounding)
      (dst left right : Reg .f64)
  | minimumF64 (dst left right : Reg .f64)
  | maximumF64 (dst left right : Reg .f64)
  | ret
  deriving Repr

/-- Register counts are emitted as bounded PTX register arrays. -/
structure RegisterCounts where
  pred : Nat
  byte : Nat
  u32 : Nat
  u64 : Nat
  f64 : Nat
  deriving BEq, DecidableEq, Repr

/-- A complete, single-entry generated PTX module. -/
structure Module where
  entryName : String
  variableCount : Nat
  registers : RegisterCounts
  body : Array Instruction
  deriving Repr

/-- A lexical opcode identifier derived from a typed instruction. -/
inductive Opcode where
  | ldParamU64
  | movU16
  | movU32
  | mulWideU32
  | cvtU64U32
  | addU64
  | mulLoU64
  | cvtaGlobalU64
  | ldGlobalF64
  | stGlobalF64
  | stGlobalU8
  | movB64
  | xorB64
  | andB64
  | setpEqU64
  | setpGeU64
  | bra
  | addRmF64
  | addRpF64
  | subRmF64
  | subRpF64
  | mulRmF64
  | mulRpF64
  | minF64
  | maxF64
  | ret
  deriving BEq, DecidableEq, Repr

/-- The complete instruction allowlist for this AST and emitter. -/
def allowedOpcodes : List Opcode :=
  [.ldParamU64, .movU16, .movU32, .mulWideU32, .cvtU64U32, .addU64,
   .mulLoU64, .cvtaGlobalU64, .ldGlobalF64, .stGlobalF64, .stGlobalU8, .movB64,
   .xorB64, .andB64, .setpEqU64, .setpGeU64, .bra, .addRmF64,
   .addRpF64, .subRmF64, .subRpF64, .mulRmF64, .mulRpF64,
   .minF64, .maxF64, .ret]

def Instruction.opcode : Instruction → Option Opcode
  | .loadParamU64 .. => some .ldParamU64
  | .movByte .. => some .movU16
  | .movSpecialU32 .. => some .movU32
  | .mulWideU32 .. => some .mulWideU32
  | .cvtU64U32 .. => some .cvtU64U32
  | .addU64 .. => some .addU64
  | .addU64Immediate .. => some .addU64
  | .mulLoU64Immediate .. => some .mulLoU64
  | .cvtaGlobalU64 .. => some .cvtaGlobalU64
  | .loadGlobalF64 .. => some .ldGlobalF64
  | .storeGlobalF64 .. => some .stGlobalF64
  | .storeGlobalByte .. => some .stGlobalU8
  | .movF64Bits .. => some .movB64
  | .xorF64Sign .. => some .xorB64
  | .exponentBits .. => some .andB64
  | .setpEqExponentMask .. => some .setpEqU64
  | .setpGeU64 .. => some .setpGeU64
  | .branchIf .. => some .bra
  | .branch .. => some .bra
  | .label .. => none
  | .binaryF64 .add .down .. => some .addRmF64
  | .binaryF64 .add .up .. => some .addRpF64
  | .binaryF64 .sub .down .. => some .subRmF64
  | .binaryF64 .sub .up .. => some .subRpF64
  | .binaryF64 .mul .down .. => some .mulRmF64
  | .binaryF64 .mul .up .. => some .mulRpF64
  | .minimumF64 .. => some .minF64
  | .maximumF64 .. => some .maxF64
  | .ret => some .ret

end SparkInterval.PTX

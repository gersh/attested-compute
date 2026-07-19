import SparkInterval.PTX.Emitter

set_option autoImplicit false

namespace SparkInterval.Tests.PTXGenerator

open SparkInterval.PTX

private def errorIs (result : Except String Unit) (expected : String) : Bool :=
  match result with
  | .error message => message == expected
  | .ok () => false

example : hex64 0 = "0x0000000000000000" := by native_decide

example : hex64 0xfff0000000000000 = "0xfff0000000000000" := by native_decide

private def invalidRegisterModule : Module := {
  entryName := "sparkinterval_generated"
  variableCount := 0
  registers := { pred := 1, byte := 1, u32 := 1, u64 := 1, f64 := 1 }
  body := #[.movSpecialU32 ⟨1⟩ .tidX, .ret]
}

example : errorIs (validate invalidRegisterModule)
    "SparkInterval.PTX.RegClass.u32 register 1 is outside its declaration" = true := by
  native_decide

private def undefinedLabelModule : Module := {
  entryName := "sparkinterval_generated"
  variableCount := 0
  registers := { pred := 1, byte := 1, u32 := 1, u64 := 1, f64 := 1 }
  body := #[.branch ⟨7⟩, .ret]
}

example : errorIs (validate undefinedLabelModule)
    "branch target is undefined: 7" = true := by native_decide

private def oversizedLiteralModule : Module := {
  entryName := "sparkinterval_generated"
  variableCount := 0
  registers := { pred := 1, byte := 1, u32 := 1, u64 := 1, f64 := 1 }
  body := #[.movF64Bits ⟨0⟩ (2 ^ 64), .ret]
}

example : errorIs (validate oversizedLiteralModule)
    "binary64 literal is outside 64 bits" = true := by native_decide

end SparkInterval.Tests.PTXGenerator

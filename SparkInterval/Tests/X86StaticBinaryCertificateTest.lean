/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.X86StaticBinaryCertificate

/-!
# Tiny static x86 binary-certificate tests

The sole fixture is a 458-byte selected-entry ELF containing only `NOP; RET`.
These kernel checks exercise exact instruction-byte binding, block
contiguity, CFG closure, decoder identity, and fail-closed tampering.  They do
not execute either instruction and contain no Sqrt218 archive.
-/

set_option autoImplicit false
set_option maxRecDepth 10000

namespace SparkInterval.Tests.X86StaticBinaryCertificateTest

open SparkInterval.Execution.Architecture.X86ELF
open SparkInterval.Execution.Architecture.X86ELF.ELF64Decoder
open
  SparkInterval.Execution.Architecture.X86StaticBinaryCertificate

private def leBytes (width value : Nat) : List UInt8 :=
  (List.range width).map
    (fun index => UInt8.ofNat ((value / 256 ^ index) % 256))

private def identification : List UInt8 :=
  ([0x7f, 0x45, 0x4c, 0x46, 2, 1, 1, 0, 0,
    0, 0, 0, 0, 0, 0, 0] : List Nat).map UInt8.ofNat

private def header
    (entry : Nat) : List UInt8 :=
  identification ++
    leBytes 2 2 ++
    leBytes 2 62 ++
    leBytes 4 1 ++
    leBytes 8 entry ++
    leBytes 8 64 ++
    leBytes 8 120 ++
    leBytes 4 0 ++
    leBytes 2 64 ++
    leBytes 2 56 ++
    leBytes 2 1 ++
    leBytes 2 64 ++
    leBytes 2 4 ++
    leBytes 2 0

private def programHeader
    (fileSize : Nat) : List UInt8 :=
  leBytes 4 1 ++
    leBytes 4 5 ++
    leBytes 8 0 ++
    leBytes 8 0x400000 ++
    leBytes 8 0x400000 ++
    leBytes 8 fileSize ++
    leBytes 8 fileSize ++
    leBytes 8 0x1000

private def sectionHeader
    (sectionType rawFlags virtualAddress fileOffset byteLength
      link info alignment entrySize : Nat) : List UInt8 :=
  leBytes 4 0 ++
    leBytes 4 sectionType ++
    leBytes 8 rawFlags ++
    leBytes 8 virtualAddress ++
    leBytes 8 fileOffset ++
    leBytes 8 byteLength ++
    leBytes 4 link ++
    leBytes 4 info ++
    leBytes 8 alignment ++
    leBytes 8 entrySize

private def nullSectionHeader : List UInt8 :=
  sectionHeader 0 0 0 0 0 0 0 0 0

private def elf64Symbol
    (nameOffset info sectionIndex value byteLength : Nat) : List UInt8 :=
  leBytes 4 nameOffset ++
    leBytes 1 info ++
    leBytes 1 0 ++
    leBytes 2 sectionIndex ++
    leBytes 8 value ++
    leBytes 8 byteLength

private def entryAddress : Nat :=
  0x400000 + 376

private def textBytes : List UInt8 :=
  [0x90, 0xc3]

private def symbolBytes : List UInt8 :=
  elf64Symbol 0 0 0 0 0 ++
    elf64Symbol 1 0x12 1 entryAddress textBytes.length

private def stringBytes : List UInt8 :=
  [0] ++ selectedEntrySymbol.toUTF8.toList ++ [0]

private def tinySelectedELF : ByteArray :=
  let textOffset := 376
  let symbolOffset := textOffset + textBytes.length
  let stringOffset := symbolOffset + symbolBytes.length
  let totalSize := stringOffset + stringBytes.length
  (header entryAddress ++
    programHeader totalSize ++
    nullSectionHeader ++
    sectionHeader 1 6 entryAddress textOffset textBytes.length
      0 0 1 0 ++
    sectionHeader 2 0 0 symbolOffset symbolBytes.length
      3 1 8 24 ++
    sectionHeader 3 0 0 stringOffset stringBytes.length
      0 0 1 0 ++
    textBytes ++ symbolBytes ++ stringBytes).toByteArray

private def nopInstruction : DecodedInstruction :=
  {
    address := entryAddress
    encoding := ([0x90] : List UInt8).toByteArray
    formId := "nop"
    flow := .fallthrough
  }

private def returnInstruction : DecodedInstruction :=
  {
    address := entryAddress + 1
    encoding := ([0xc3] : List UInt8).toByteArray
    formId := "ret"
    flow := .returns
  }

private def tinyDecodeAt
    (_bytes : ByteArray) (_image : ELF64Image) (address : Nat) :
    Option DecodedInstruction :=
  if address = entryAddress then
    some nopInstruction
  else if address = entryAddress + 1 then
    some returnInstruction
  else
    none

private def tinyDecoder : InstructionDecoder :=
  {
    decoderId := "tiny-x86-decoder-kat-v1"
    decoderIdPresent := by decide
    decodeAt := tinyDecodeAt
  }

private def validBlock : BlockCertificate :=
  {
    startAddress := entryAddress
    instructions := [nopInstruction, returnInstruction]
    successors := []
    summaryId := "nop-ret-summary-v1"
  }

private def validCertificate : Certificate :=
  {
    formatVersion := 1
    decoderId := tinyDecoder.decoderId
    selectedSymbol := selectedEntrySymbol
    entryAddress
    blocks := [validBlock]
  }

#guard tinySelectedELF.size < 512

#guard validate tinyDecoder tinySelectedELF validCertificate

#guard
  !validate tinyDecoder tinySelectedELF
    { validCertificate with decoderId := "wrong-decoder" }

#guard
  !validate tinyDecoder tinySelectedELF
    { validCertificate with entryAddress := entryAddress + 1 }

#guard
  !validate tinyDecoder tinySelectedELF
    {
      validCertificate with
      blocks := [
        {
          validBlock with
          instructions := [
            {
              nopInstruction with
              encoding := ([0x91] : List UInt8).toByteArray
            },
            returnInstruction
          ]
        }
      ]
    }

#guard
  !validate tinyDecoder tinySelectedELF
    {
      validCertificate with
      blocks := [
        {
          validBlock with
          successors := [entryAddress + 100]
        }
      ]
    }

/-- The finite checker exposes exact selected-entry ELF facts without adding
a trust premise. -/
example
    (accepted :
      validate tinyDecoder tinySelectedELF validCertificate = true) :
    ∃ image : ELF64Image,
      decodeSelectedImage tinySelectedELF = some image ∧
        image.EntryAdmissible selectedEntrySymbol image.entryAddress ∧
        validCertificate.selectedSymbol = selectedEntrySymbol ∧
        validCertificate.entryAddress = image.entryAddress.toNat :=
  checked_selectedEntry (checked_of_validate accepted)

end SparkInterval.Tests.X86StaticBinaryCertificateTest

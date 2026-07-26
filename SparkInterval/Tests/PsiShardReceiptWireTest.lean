/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiShardReceiptWire

/-!
Bounded cross-language fixture emitted by a fresh strict-flags build of
`reference/tg_psi_residual_shard.cpp` over the inclusive range `[2,100]`.
The structural and row digests are also checked by the independent Python
model in `tests/tg_psi_residual_shard_known_answers.py`.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.PsiShardReceiptWire

open SparkInterval.TernaryGoldbach.PsiShardReceiptWire

def summaryText : String :=
  r#"{"algorithm":"ch25-psi-prime-power-two-pass-v1","mode":"summary","classification":"source-scale-shard-not-lean-proof","atom":"ch25-psi-1e13","primesieve_commit":"4f85384851da23c36c01ec01ef85b5d9d246e556","crlibm_commit":"eb3063791aa75bc9705b49283bf14250465220a7","lower":2,"upper_exclusive":101,"work_count":99,"scale_bits":64,"sieve_size_kib":64,"log_interval_encoding":"crlibm-binary64-directed-to-q64-v1","event_encoding":"u64be-value-u64be-prime-u32be-exponent-v1","event_sha256":"6a39e9a90d7c9bead2b83dd3b4acb890a81fc9ab4faa3728c0a065da4e9720c0","row_encoding":"u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1","row_sha256":"ca6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288","prime_power_events":35,"prime_events":25,"higher_power_events":10,"state_components":["psi_lower_q64","psi_upper_q64"],"delta":[1734829787580318666752,1734829787580318957568],"guards":{},"incoming_state":null,"outgoing_state":null,"exact_fallbacks":{"lower_left_limit":0,"upper_post_jump":0,"terminal_lower":0},"terminal_strict_lower_checked":false,"accepted":true,"elapsed_seconds":6.7536e-05,"execution_attested":false,"lean_atom_discharged":false}"# ++
    "\n"

def verificationText : String :=
  r#"{"algorithm":"ch25-psi-prime-power-two-pass-v1","mode":"verify","classification":"source-scale-shard-not-lean-proof","atom":"ch25-psi-1e13","primesieve_commit":"4f85384851da23c36c01ec01ef85b5d9d246e556","crlibm_commit":"eb3063791aa75bc9705b49283bf14250465220a7","lower":2,"upper_exclusive":101,"work_count":99,"scale_bits":64,"sieve_size_kib":64,"log_interval_encoding":"crlibm-binary64-directed-to-q64-v1","event_encoding":"u64be-value-u64be-prime-u32be-exponent-v1","event_sha256":"6a39e9a90d7c9bead2b83dd3b4acb890a81fc9ab4faa3728c0a065da4e9720c0","row_encoding":"u64be-value-u64be-prime-u32be-exponent-u128be-log-pair-v1","row_sha256":"ca6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288","prime_power_events":35,"prime_events":25,"higher_power_events":10,"state_components":["psi_lower_q64","psi_upper_q64"],"delta":[1734829787580318666752,1734829787580318957568],"guards":{"ch25-psi-1e13":{"lower_guard":[0,0],"upper_guard":[0,0],"witnesses":[]}},"incoming_state":[0,0],"outgoing_state":[1734829787580318666752,1734829787580318957568],"exact_fallbacks":{"lower_left_limit":2,"upper_post_jump":0,"terminal_lower":0},"terminal_strict_lower_checked":false,"accepted":true,"elapsed_seconds":4.9824e-05,"execution_attested":false,"lean_atom_discharged":false}"# ++
    "\n"

def summaryBytes : ByteArray := summaryText.toUTF8
def verificationBytes : ByteArray := verificationText.toUTF8

#guard checkReceipt summaryBytes
#guard checkReceipt verificationBytes
#guard checkReceiptPair summaryBytes verificationBytes
#guard
  checkBoundedCampaign 2 101 64 35
    [(summaryBytes, verificationBytes)]

def staleSummaryState : ByteArray :=
  (summaryText.replace "\"incoming_state\":null"
    "\"incoming_state\":[0,0]").toUTF8

/- This was the shape emitted by a stale local build product.  The current
source contract requires summary states to be null. -/
#guard !checkReceipt staleSummaryState

def changedVerificationDigest : ByteArray :=
  (verificationText.replace
    "ca6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288"
    "da6eca43ef27a1eaf09e53e91ed6e19e34f8348eb808eec28464b03f69979288").toUTF8

#guard !checkReceiptPair summaryBytes changedVerificationDigest

def claimedAttestation : ByteArray :=
  (verificationText.replace
    "\"execution_attested\":false"
    "\"execution_attested\":true").toUTF8

#guard !checkReceipt claimedAttestation

def duplicateAccepted : ByteArray :=
  (summaryText.replace
    "\"accepted\":true"
    "\"accepted\":true,\"accepted\":true").toUTF8

#guard parseReceipt duplicateAccepted = none

def withSuffix : ByteArray :=
  ((summaryText.dropEnd 1).toString ++ "x\n").toUTF8

#guard parseReceipt withSuffix = none

example {summaryRaw verificationRaw : ByteArray}
    (hcheck : checkReceiptPair summaryRaw verificationRaw = true) :
    ValidatedReceiptPair summaryRaw verificationRaw :=
  checkReceiptPair_sound hcheck

example {rawPairs : List RawReceiptPair}
    (hcheck : checkSourceCampaign rawPairs = true) :
    ValidatedSourceWire rawPairs :=
  checkSourceCampaign_sound hcheck

end SparkInterval.Tests.PsiShardReceiptWire

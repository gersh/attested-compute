(* Copyright (c) 2026 Gershon Bialer. All rights reserved.
   SPDX-License-Identifier: MIT *)

(** This file is compiled only in the cloud proof-build lane, after the
    generated Clight program and the separately reviewed VST proof sources. *)

From Sqrt218 Require Import Sqrt218Proof.

Print Assumptions
  Sqrt218Proof.body_tg_sq218_verify_snapshot_v2.

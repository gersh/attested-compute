#!/usr/bin/env python3
"""Generate deterministic Lean data from a canonical Phase-3 certificate.

The Python reference checker is deliberately not a trust boundary for the
result theorem: the emitted Lean module asks the Phase-8 checker to recompute
the full certificate.  Recomputing here is still valuable because it prevents
the generator from creating a large Lean source file for a certificate that is
already known to be malformed or arithmetically wrong.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reference import evaluator  # noqa: E402
from reference import exact_binary64 as exact  # noqa: E402
from reference import format as wire  # noqa: E402


GENERATOR_ID = "sparkinterval.lean_result_certificate.v1"
RECEIPT_KIND = "sparkinterval_lean_result_certificate_receipt"
LEAN_IMPORT = "SparkInterval.Certificate"
LEAN_NAMESPACE_PREFIX = "SparkInterval.GeneratedCertificate"


class LeanCertificateError(ValueError):
    """The requested Lean certificate source cannot be generated safely."""


def _fail(message: str) -> None:
    raise LeanCertificateError(message)


def _load_canonical_certificate(path: Path) -> tuple[dict[str, Any], bytes, Path]:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise LeanCertificateError(f"cannot resolve certificate {path}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        _fail(f"certificate is not a regular file: {resolved}")
    if metadata.st_size > wire.MAX_CANONICAL_JSON_BYTES:
        _fail(
            f"certificate exceeds the {wire.MAX_CANONICAL_JSON_BYTES}-byte "
            "canonical JSON limit"
        )
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise LeanCertificateError(f"cannot read certificate {resolved}: {exc}") from exc
    if len(raw) > wire.MAX_CANONICAL_JSON_BYTES:
        _fail(
            f"certificate exceeds the {wire.MAX_CANONICAL_JSON_BYTES}-byte "
            "canonical JSON limit"
        )
    certificate = wire.parse_certificate_bytes(raw, source=str(resolved))
    return certificate, raw, resolved


def _parse_application_upper_bound(raw: str) -> int:
    bits = wire.parse_binary64_hex(raw, "application upper bound")
    if not exact.is_finite(bits):
        _fail("application upper bound must be a finite binary64 word")
    return bits


def _check_application_upper_bound(
    certificate: dict[str, Any], bound_bits: int
) -> None:
    """Reject a bound that the generated Lean check is certain to reject."""

    bound = exact.decode_finite(bound_bits)
    for index, interval in enumerate(certificate["result"]["rows"]):
        high_bits = int(interval["hi"], 16)
        classification = exact.classify(high_bits)
        if classification in {
            exact.Binary64Class.POSITIVE_INFINITY,
            exact.Binary64Class.NEGATIVE_INFINITY,
        }:
            _fail(
                "application upper-bound checking requires a finite result "
                f"row {index}.hi"
            )
        if exact.decode_finite(high_bits) > bound:
            _fail(f"application upper bound is below result row {index}.hi")


def _certificate_upper_bound_hex(certificate: dict[str, Any]) -> str:
    """Return the greatest finite claimed result high endpoint."""

    highs = [interval["hi"] for interval in certificate["result"]["rows"]]
    if not highs:  # The strict format requires at least one row.
        _fail("full certificate must contain at least one result row")
    return max(highs, key=lambda raw: exact.decode_finite(int(raw, 16)))


def _lean_namespace(
    certificate: dict[str, Any], application_upper_bound: str,
    decision_mode: str,
) -> str:
    """Use the complete certificate and bound identity to avoid collisions."""

    return (
        f"{LEAN_NAMESPACE_PREFIX}.C_{wire.canonical_sha256(certificate)}"
        f"_B_{application_upper_bound}_M_{decision_mode}"
    )


def _lean_word(raw: str) -> str:
    # Revalidate at the rendering boundary so direct library callers cannot
    # smuggle Lean syntax through an endpoint string.
    wire.parse_binary64_hex(raw, "rendered binary64 word")
    return f"0x{raw}"


def _lean_interval(interval: dict[str, str]) -> str:
    return (
        "{ lo := "
        + _lean_word(interval["lo"])
        + ", hi := "
        + _lean_word(interval["hi"])
        + " }"
    )


def _lean_raw_string(value: str) -> str:
    """Quote exact text without interpreting JSON quotes or backslashes.

    Lean raw strings close with a quote followed by the selected number of
    hash characters.  Select the delimiter from the value itself rather than
    relying on the current certificate alphabet.
    """

    for hash_count in range(1, 65):
        hashes = "#" * hash_count
        if f'"{hashes}' not in value:
            return f'r{hashes}"{value}"{hashes}'
    _fail("canonical certificate cannot be represented as a bounded Lean raw string")


def _render_expression(node: dict[str, Any], indent: int = 0) -> list[str]:
    prefix = " " * indent
    op = node["op"]
    if op == "const":
        return [f"{prefix}(.const {_lean_interval(node['value'])})"]
    if op == "var":
        return [f"{prefix}(.var {node['index']})"]

    constructor = "powNat" if op == "pow_nat" else op
    if op in {"neg", "abs"}:
        lines = [f"{prefix}(.{constructor}"]
        lines.extend(_render_expression(node["arg"], indent + 2))
        lines[-1] += ")"
        return lines
    if op == "pow_nat":
        lines = [f"{prefix}(.powNat"]
        lines.extend(_render_expression(node["arg"], indent + 2))
        lines.append(f"{prefix}  {node['exponent']})")
        return lines
    if op in {"add", "sub", "mul", "div", "min", "max"}:
        lines = [f"{prefix}(.{constructor}"]
        lines.extend(_render_expression(node["left"], indent + 2))
        lines.extend(_render_expression(node["right"], indent + 2))
        lines[-1] += ")"
        return lines
    _fail(f"cannot render unsupported expression operation {op!r}")


def _render_interval_array(
    intervals: Sequence[dict[str, str]], indent: int
) -> list[str]:
    prefix = " " * indent
    lines = [prefix + "#["]
    lines.extend(
        f"{prefix}  {_lean_interval(interval)}," for interval in intervals
    )
    lines.append(prefix + "]")
    return lines


def _render_input_rows(
    rows: Sequence[Sequence[dict[str, str]]], indent: int
) -> list[str]:
    prefix = " " * indent
    lines = [prefix + "#["]
    for row in rows:
        rendered = _render_interval_array(row, indent + 2)
        rendered[-1] += ","
        lines.extend(rendered)
    lines.append(prefix + "]")
    return lines


def render_lean_source(
    certificate: dict[str, Any], application_upper_bound: str,
    decision_mode: str = "kernel",
) -> bytes:
    """Validate, exact-recompute, and render one deterministic Lean module."""

    if decision_mode not in {"kernel", "native"}:
        _fail("decision mode must be 'kernel' or 'native'")
    validated = wire.validate_certificate(certificate)
    try:
        evaluator.check_certificate(validated)
    except evaluator.CertificateError as exc:
        raise LeanCertificateError(
            f"reference certificate failed exact recomputation: {exc}"
        ) from exc
    bound_bits = _parse_application_upper_bound(application_upper_bound)
    _check_application_upper_bound(validated, bound_bits)
    certificate_upper_bound = _certificate_upper_bound_hex(validated)
    lean_namespace = _lean_namespace(
        validated, application_upper_bound, decision_mode
    )
    decision_tactic = "decide_cbv" if decision_mode == "kernel" else "native_decide"

    batch = validated["batch"]
    result = validated["result"]
    certificate_sha256 = wire.canonical_sha256(validated)
    canonical_certificate = wire.canonical_json_bytes(validated).decode(
        "utf-8", errors="strict"
    )
    lines = [
        f"import {LEAN_IMPORT}",
        "",
        "/-!",
        "This file is generated deterministically by",
        "`tools/generate_lean_result_certificate.py`. Do not edit it by hand.",
        "-/",
        "",
        "set_option autoImplicit false",
        "set_option maxRecDepth 1000000",
        "set_option cbv.maxSteps 10000000",
        "set_option maxHeartbeats 2000000",
        "set_option exponentiation.threshold 2048",
        "",
        f"namespace {lean_namespace}",
        "",
        f'def generatorId : String := "{GENERATOR_ID}"',
        f'def decisionMode : String := "{decision_mode}"',
        f"def sourceSchemaVersion : Nat := {validated['schema_version']}",
        f'def sourceCertificateKind : String := "{validated["kind"]}"',
        f'def sourceBatchKind : String := "{batch["kind"]}"',
        f'def sourceResultKind : String := "{result["kind"]}"',
        f'def sourceAlgorithmId : String := "{batch["algorithm"]}"',
        f'def sourceCertificateSha256 : String := "{certificate_sha256}"',
        f'def sourceBatchSha256 : String := "{validated["batch_sha256"]}"',
        f'def sourceResultSha256 : String := "{validated["result_sha256"]}"',
        "def sourceCertificateJson : String :=",
        f"  {_lean_raw_string(canonical_certificate)}",
        f'def applicationUpperBoundHex : String := "{application_upper_bound}"',
        f"def applicationUpperBoundBits : Nat := 0x{application_upper_bound}",
        "def applicationUpperBound : ℚ :=",
        "  SparkInterval.Certificate.Binary64.finiteValue applicationUpperBoundBits",
        f'def certificateUpperBoundHex : String := "{certificate_upper_bound}"',
        f"def certificateUpperBoundBits : Nat := 0x{certificate_upper_bound}",
        "def certificateUpperBound : ℚ :=",
        "  SparkInterval.Certificate.Binary64.finiteValue certificateUpperBoundBits",
        "",
        "def certificate : SparkInterval.Certificate.FullCertificate where",
        f"  variableCount := {batch['variable_count']}",
        "  expression :=",
    ]
    lines.extend(_render_expression(batch["expression"], 4))
    lines.append("  rows :=")
    lines.extend(_render_input_rows(batch["rows"], 4))
    lines.append("  results :=")
    lines.extend(_render_interval_array(result["rows"], 4))
    lines.extend(
        [
            "  batchHash := sourceBatchSha256",
            "  resultHash := sourceResultSha256",
            "",
            "theorem source_certificate_sha256_check :",
            "    SparkInterval.Certificate.SHA256.digestString sourceCertificateJson =",
            "      sourceCertificateSha256 := by",
            "  native_decide",
            "",
            "theorem source_certificate_parse :",
            "    SparkInterval.Certificate.parseCanonicalFullCertificate",
            "      sourceCertificateJson = .ok certificate := by",
            "  native_decide",
            "",
            "theorem certificate_check : certificate.check = true := by",
            f"  {decision_tactic}",
            "",
            "theorem certificate_upper_bound_check :",
            "    certificate.checkUpperBound certificateUpperBoundBits = true := by",
            "  unfold SparkInterval.Certificate.FullCertificate.checkUpperBound",
            "  rw [certificate_check]",
            f"  {decision_tactic}",
            "",
            "theorem certificate_upper_bound_decode :",
            "    SparkInterval.Certificate.Binary64.decodeFinite",
            "      certificateUpperBoundBits = some certificateUpperBound := by",
            "  rfl",
            "",
            "theorem application_upper_bound_decode :",
            "    SparkInterval.Certificate.Binary64.decodeFinite",
            "      applicationUpperBoundBits = some applicationUpperBound := by",
            "  rfl",
            "",
            "theorem certificate_upper_bound_le_application :",
            "    certificateUpperBound ≤ applicationUpperBound := by",
            "  norm_num [certificateUpperBound, certificateUpperBoundBits,",
            "    applicationUpperBound, applicationUpperBoundBits,",
            "    SparkInterval.Certificate.Binary64.finiteValue,",
            "    SparkInterval.Certificate.Binary64.exponentBits,",
            "    SparkInterval.Certificate.Binary64.fractionBits,",
            "    SparkInterval.Certificate.Binary64.signBit,",
            "    SparkInterval.Certificate.Binary64.fractionModulus,",
            "    SparkInterval.Certificate.Binary64.exponentModulus,",
            "    SparkInterval.Certificate.Binary64.signThreshold, div_le_iff₀]",
            "",
            "theorem application_upper_bound_sound",
            "    {index : Nat} (hindex : index < certificate.rows.size)",
            "    {value : ℝ} (hreal : certificate.RowRealizes index value) :",
            "    value ≤ (applicationUpperBound : ℝ) := by",
            "  exact (SparkInterval.Certificate.FullCertificate.checkUpperBound_sound",
            "    certificate_upper_bound_decode certificate_upper_bound_check hindex hreal).trans",
            "      (Rat.cast_le.mpr certificate_upper_bound_le_application)",
            "",
            "#print axioms application_upper_bound_sound",
            "",
            "def certificateResultUpperSum : ℚ := certificate.resultUpperSum",
            "",
            "theorem certificate_sum_check :",
            "    certificate.checkSumUpperBound certificateResultUpperSum = true := by",
            "  unfold SparkInterval.Certificate.FullCertificate.checkSumUpperBound",
            "  rw [certificate_check]",
            f"  {decision_tactic}",
            "",
            "theorem certificate_sum_upper_bound_sound",
            "    (values : Fin certificate.rows.size → ℝ)",
            "    (hvalues : certificate.ValuesRealize values) :",
            "    (∑ index, values index) ≤ (certificateResultUpperSum : ℝ) := by",
            "  exact SparkInterval.Certificate.FullCertificate.checkSumUpperBound_sound",
            "    certificate_sum_check values hvalues",
            "",
            "#print axioms certificate_sum_upper_bound_sound",
            "",
            "theorem application_theorem :",
            "    SparkInterval.Certificate.SerializedUpperBoundTheorem",
            "      sourceCertificateJson applicationUpperBoundBits := by",
            "  intro parsedCertificate parsedBound hparse hbound index hindex value hreal",
            "  have hcertificate : parsedCertificate = certificate :=",
            "    Except.ok.inj (hparse.symm.trans source_certificate_parse)",
            "  subst parsedCertificate",
            "  have hboundEq : parsedBound = applicationUpperBound :=",
            "    Option.some.inj (hbound.symm.trans application_upper_bound_decode)",
            "  subst parsedBound",
            "  exact application_upper_bound_sound hindex hreal",
            "",
            "#print axioms application_theorem",
            "",
            "theorem application_sum_theorem :",
            "    SparkInterval.Certificate.SerializedSumUpperBoundTheorem",
            "      sourceCertificateJson certificateResultUpperSum := by",
            "  intro parsedCertificate hparse values hvalues",
            "  have hcertificate : parsedCertificate = certificate :=",
            "    Except.ok.inj (hparse.symm.trans source_certificate_parse)",
            "  subst parsedCertificate",
            "  exact certificate_sum_upper_bound_sound values hvalues",
            "",
            "#print axioms application_sum_theorem",
            "",
            f"end {lean_namespace}",
            "",
        ]
    )
    try:
        return "\n".join(lines).encode("utf-8", errors="strict")
    except UnicodeError as exc:  # All variable content is validated ASCII.
        raise LeanCertificateError(f"cannot encode generated Lean source: {exc}") from exc


def make_receipt(
    certificate: dict[str, Any], application_upper_bound: str,
    decision_mode: str, source: bytes
) -> dict[str, Any]:
    batch = certificate["batch"]
    lean_namespace = _lean_namespace(
        certificate, application_upper_bound, decision_mode
    )
    return {
        "schema_version": 1,
        "kind": RECEIPT_KIND,
        "generator": GENERATOR_ID,
        "algorithm": batch["algorithm"],
        "certificate_sha256": wire.canonical_sha256(certificate),
        "batch_sha256": certificate["batch_sha256"],
        "result_sha256": certificate["result_sha256"],
        "application_upper_bound": application_upper_bound,
        "decision_mode": decision_mode,
        "variable_count": batch["variable_count"],
        "row_count": len(batch["rows"]),
        "lean_declaration": f"{lean_namespace}.certificate",
        "lean_theorem": f"{lean_namespace}.application_theorem",
        "lean_sum_theorem": f"{lean_namespace}.application_sum_theorem",
        "lean_source_sha256": hashlib.sha256(source).hexdigest(),
        "lean_source_size_bytes": len(source),
    }


def _write_new_source(path: Path, source: bytes) -> Path:
    if path.suffix != ".lean":
        _fail("output path must have the .lean suffix")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise LeanCertificateError(
            f"refusing to overwrite existing output: {path}"
        ) from exc
    except OSError as exc:
        raise LeanCertificateError(f"cannot create output {path}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(source)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--certificate",
        required=True,
        type=Path,
        help="canonical Phase-3 reference certificate",
    )
    parser.add_argument(
        "--decision-mode",
        choices=("kernel", "native"),
        default="kernel",
        help=(
            "kernel uses decide_cbv and standard foundations; native uses "
            "native_decide proof reflection for larger full certificates"
        ),
    )
    parser.add_argument(
        "--upper-bound",
        required=True,
        help="finite binary64 application bound as 16 lowercase hex digits",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        certificate, _raw, resolved_input = _load_canonical_certificate(
            args.certificate
        )
        resolved_output = args.output.resolve(strict=False)
        if resolved_output == resolved_input:
            _fail("certificate input and Lean output paths must be distinct")
        source = render_lean_source(
            certificate, args.upper_bound, args.decision_mode
        )
        receipt = make_receipt(
            certificate, args.upper_bound, args.decision_mode, source
        )
        _write_new_source(args.output, source)
        sys.stdout.buffer.write(wire.canonical_json_bytes(receipt))
        sys.stdout.buffer.flush()
    except (
        LeanCertificateError,
        wire.FormatError,
        evaluator.CertificateError,
        evaluator.EvaluationError,
        OSError,
    ) as exc:
        print(f"generate_lean_result_certificate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

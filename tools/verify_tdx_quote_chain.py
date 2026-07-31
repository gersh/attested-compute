#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Offline Intel certificate-chain check for the retained TDX quotes.

WHAT THIS ESTABLISHES
---------------------

For each retained ``tdx-quote.bin`` in this repository, that the quote's own
ECDSA-P256 signature chain closes, all the way up to the Intel SGX Root CA
certificate pinned at ``tools/intel_sgx_root_ca.pem``:

  A1  the attestation key signs ``header || TD report``  (P-256 / SHA-256)
  A2  the Quoting Enclave's report data is
      ``SHA-256(attestation key || QE auth data) || 32 zero bytes``,
      which is what binds the attestation key to the QE
  A3  the PCK leaf certificate's public key signs the QE report
  A4a the PCK leaf is signed by the intermediate
  A4b the intermediate is signed by the root
  A4c the root is self-signed
  A4d the root's SHA-256 fingerprint equals the pinned Intel SGX Root CA

Together A1-A4d say: *this quote was produced by an attestation key that a
certificate chain rooted in Intel's published SGX Root CA vouches for.*  That
is the "genuine TDX enclave" link.

WHAT THIS DOES **NOT** ESTABLISH
-------------------------------

* **It is not in Lean's kernel.**  Nothing here enters any Lean proof term.
  ``SparkInterval/Execution/PhalaTdxOperationalAttestation.lean`` states the
  attestation axiom, and its assumption list must continue to say that Lean
  does not parse PCK certificate chains, TCB levels, or QE identities.  This
  script is a *build gate*: it makes the external check impossible to skip
  silently.  It does not shrink what the axiom assumes.
* **It is not a TCB appraisal.**  Chain validity says the key is Intel-rooted.
  It says nothing about whether the platform's TCB is up to date, whether the
  QE identity is the current one, or whether any certificate has been revoked.
  Those need Intel's live collateral (TCB info, QE identity, CRLs) and are
  ``dcap-qvl``'s job; that stays outside this gate and outside Lean.
* **It says nothing about the computation.**  The quote binds a key and a
  measurement.  What ran, on what input, and what came out is the receipt and
  statement layer, which Lean *does* check.

OFFLINE VERSUS ONLINE -- THE SPLIT IS DELIBERATE
------------------------------------------------

The default mode is fully offline and deterministic: it reads committed bytes
and a committed PEM and does arithmetic.  A build must never depend on network
reachability or on Intel's service being up, and a network failure must never
be presented as an attestation failure.

Confirming that the *pinned* PEM still matches the root Intel publishes today
is a separate, network-touching check, ``--check-live-intel-root``, for CI or
on demand.  It is never run by the default mode.

EXIT CODES -- THE FAILURE MODES ARE DISTINCT
--------------------------------------------

  0  every bundle that was present passed, and at least one was present
  1  a bundle was present and its chain is INVALID  (hard failure)
  2  usage / environment error (bad arguments, missing ``cryptography``)
  3  nothing to check: no retained bundle was present  (loud skip)
  4  ``--check-live-intel-root`` could not reach Intel  (network, not
     attestation -- deliberately not 1)

"no evidence bundle present" is exit 3 and never exit 1.  Pass
``--require-evidence`` to turn that skip into a hard failure; the repository's
own gate does, because the bundles are committed here and their absence means
a broken checkout rather than an unconfigured one.

Provenance: the A1-A4d logic is vendored from this project's own
``phala-simple-run1/tools/verify_run.py``.  It is kept in-tree on purpose --
a gate that reads a path in someone's home directory is not a gate.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys


EXIT_OK = 0
EXIT_CHAIN_INVALID = 1
EXIT_USAGE = 2
EXIT_NO_EVIDENCE = 3
EXIT_NETWORK = 4

ROOT = pathlib.Path(__file__).resolve().parents[1]

PINNED_ROOT_PEM = ROOT / "tools/intel_sgx_root_ca.pem"

# SHA-256 fingerprint of the Intel SGX Root CA certificate published at
# https://certificates.trustedservices.intel.com/Intel_SGX_Provisioning_
# Certification_RootCA.pem  (re-confirmed against the live service 2026-07-30).
# Pinned here as well as in the PEM so that swapping the PEM alone is not
# enough to redirect the trust root.
INTEL_SGX_ROOT_CA_SHA256 = (
    "44a0196b2b99f889b8e149e95b807a350e7424964399e885a7cbb8ccfab674d3"
)

INTEL_ROOT_CA_URL = (
    "https://certificates.trustedservices.intel.com/"
    "Intel_SGX_Provisioning_Certification_RootCA.pem"
)

# Retained evidence bundles committed to this repository.  A path that is
# absent is a loud skip; a path that is present and fails is a hard failure.
KNOWN_QUOTES = (
    "tests/data/phala_tdx_prod5/retained-evidence/input/tdx-quote.bin",
    "tests/data/phala_tdx_seg/tdx-quote.bin",
)

TDX_QUOTE_VERSION = 4
TDX_ATT_KEY_TYPE_ECDSA_P256 = 2
TDX_TEE_TYPE = 0x81

HEADER_SIZE = 48
TD_REPORT_SIZE = 584
SGX_REPORT_SIZE = 384


class ChainError(RuntimeError):
    """The quote is not a well-formed v4 TDX quote."""


def _load_cryptography():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import (
            ec,
            utils as asym_utils,
        )
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit(
            "verify_tdx_quote_chain: the 'cryptography' package is required "
            f"({exc}).  This is an environment error, not an attestation "
            "failure; install it and re-run."
        )
    return x509, hashes, ec, asym_utils, InvalidSignature


# --------------------------------------------------------------- quote parsing


class Quote:
    """The parts of a v4 TDX quote this gate needs."""


def parse_quote(raw: bytes) -> Quote:
    """Parse a v4 Intel TDX quote far enough to walk its signature chain.

    Vendored from ``phala-simple-run1/tools/verify_run.py``.  Every slice is
    bounds-checked here rather than silently truncating, so a short or
    corrupted file is a parse error rather than a check that passes on
    zero bytes.
    """

    def slice_at(buf: bytes, start: int, length: int, what: str) -> bytes:
        end = start + length
        if start < 0 or length < 0 or end > len(buf):
            raise ChainError(
                f"{what}: quote is truncated (need bytes [{start}, {end}), "
                f"have {len(buf)})"
            )
        return buf[start:end]

    q = Quote()
    q.raw = raw
    q.header = slice_at(raw, 0, HEADER_SIZE, "header")
    q.version = int.from_bytes(q.header[0:2], "little")
    q.att_key_type = int.from_bytes(q.header[2:4], "little")
    q.tee_type = int.from_bytes(q.header[4:8], "little")
    q.qe_vendor_id = q.header[12:28].hex()

    body = slice_at(raw, HEADER_SIZE, TD_REPORT_SIZE, "TD report body")
    q.td_report = body
    o = 0

    def take(n: int, what: str) -> bytes:
        nonlocal o
        v = slice_at(body, o, n, what)
        o += n
        return v

    q.tee_tcb_svn = take(16, "tee_tcb_svn").hex()
    q.mr_seam = take(48, "mrseam").hex()
    q.mr_signer_seam = take(48, "mrsignerseam").hex()
    q.seam_attributes = take(8, "seamattributes").hex()
    q.td_attributes = take(8, "tdattributes").hex()
    q.xfam = take(8, "xfam").hex()
    q.mr_td = take(48, "mrtd").hex()
    q.mr_config_id = take(48, "mrconfigid").hex()
    q.mr_owner = take(48, "mrowner").hex()
    q.mr_owner_config = take(48, "mrownerconfig").hex()
    q.rtmrs = [take(48, f"rtmr{i}").hex() for i in range(4)]
    q.report_data = take(64, "reportdata")
    if o != TD_REPORT_SIZE:
        raise ChainError("TD report body did not consume 584 bytes")

    p = HEADER_SIZE + TD_REPORT_SIZE
    sig_len = int.from_bytes(slice_at(raw, p, 4, "signature length"), "little")
    p += 4
    sig = slice_at(raw, p, sig_len, "signature data")
    q.signature_data = sig

    s = 0
    q.ecdsa_signature = slice_at(sig, s, 64, "quote signature")
    s += 64
    q.attest_pub_key = slice_at(sig, s, 64, "attestation public key")
    s += 64
    q.cert_key_type = int.from_bytes(
        slice_at(sig, s, 2, "certification data type"), "little"
    )
    s += 2
    cert_size = int.from_bytes(
        slice_at(sig, s, 4, "certification data size"), "little"
    )
    s += 4
    cert = slice_at(sig, s, cert_size, "certification data")

    # Certification data type 6 = QE report certification data.
    if q.cert_key_type != 6:
        raise ChainError(
            "certification data type is "
            f"{q.cert_key_type}, expected 6 (QE report certification data)"
        )

    c = 0
    q.qe_report = slice_at(cert, c, SGX_REPORT_SIZE, "QE report")
    c += SGX_REPORT_SIZE
    q.qe_report_signature = slice_at(cert, c, 64, "QE report signature")
    c += 64
    auth_size = int.from_bytes(
        slice_at(cert, c, 2, "QE auth data size"), "little"
    )
    c += 2
    q.qe_auth_data = slice_at(cert, c, auth_size, "QE auth data")
    c += auth_size
    q.pck_cert_key_type = int.from_bytes(
        slice_at(cert, c, 2, "PCK certification data type"), "little"
    )
    c += 2
    pck_size = int.from_bytes(
        slice_at(cert, c, 4, "PCK certification data size"), "little"
    )
    c += 4
    q.pck_chain_pem = slice_at(cert, c, pck_size, "PCK certificate chain")

    # SGX report body: report_data is the last 64 bytes of the 384-byte body.
    q.qe_report_data = q.qe_report[320:384]
    q.qe_mr_enclave = q.qe_report[64:96].hex()
    q.qe_mr_signer = q.qe_report[128:160].hex()
    return q


# ------------------------------------------------------------------ primitives


def p256_verify(pub_xy: bytes, sig_rs: bytes, message: bytes) -> bool:
    x509, hashes, ec, asym_utils, InvalidSignature = _load_cryptography()
    try:
        x = int.from_bytes(pub_xy[:32], "big")
        y = int.from_bytes(pub_xy[32:], "big")
        key = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    except ValueError:
        # A point that is not on the curve is a chain failure, not a crash.
        return False
    r = int.from_bytes(sig_rs[:32], "big")
    s = int.from_bytes(sig_rs[32:], "big")
    try:
        der = asym_utils.encode_dss_signature(r, s)
        key.verify(der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def cert_verify(issuer_cert, subject_cert) -> bool:
    x509, hashes, ec, asym_utils, InvalidSignature = _load_cryptography()
    try:
        issuer_cert.public_key().verify(
            subject_cert.signature,
            subject_cert.tbs_certificate_bytes,
            ec.ECDSA(subject_cert.signature_hash_algorithm),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ------------------------------------------------------------------ the checks


class BundleReport:
    def __init__(self, path: str) -> None:
        self.path = path
        self.rows: list[tuple[str, bool, str]] = []
        self.parse_error: str | None = None

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), detail))
        return bool(ok)

    @property
    def failed(self) -> bool:
        return self.parse_error is not None or any(
            not ok for _, ok, _ in self.rows
        )

    def emit(self) -> None:
        print(f"  quote: {self.path}")
        if self.parse_error is not None:
            print(f"    FAIL  quote does not parse -- {self.parse_error}")
            return
        for name, ok, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            suffix = f" -- {detail}" if detail else ""
            print(f"    {mark}  {name}{suffix}")


def check_quote_chain(path: pathlib.Path, root_pem: pathlib.Path) -> BundleReport:
    """Run A1-A4d on one retained quote.  Fully offline."""
    x509, hashes, ec, asym_utils, InvalidSignature = _load_cryptography()
    report = BundleReport(str(path))
    raw = path.read_bytes()

    try:
        quote = parse_quote(raw)
    except ChainError as exc:
        report.parse_error = str(exc)
        return report

    report.check(
        "quote is TDX v4 with an ECDSA-P256 attestation key",
        quote.version == TDX_QUOTE_VERSION
        and quote.att_key_type == TDX_ATT_KEY_TYPE_ECDSA_P256
        and quote.tee_type == TDX_TEE_TYPE,
        f"version={quote.version} att_key_type={quote.att_key_type} "
        f"tee_type=0x{quote.tee_type:x}",
    )

    report.check(
        "A1 attestation key signs header||TD report (P-256/SHA-256)",
        p256_verify(
            quote.attest_pub_key,
            quote.ecdsa_signature,
            quote.header + quote.td_report,
        ),
    )

    expect = hashlib.sha256(quote.attest_pub_key + quote.qe_auth_data).digest()
    report.check(
        "A2 QE report data binds the attestation key",
        quote.qe_report_data[:32] == expect
        and quote.qe_report_data[32:] == bytes(32),
        quote.qe_report_data[:32].hex(),
    )

    try:
        chain = [
            x509.load_pem_x509_certificate(
                b"-----BEGIN CERTIFICATE-----" + part
            )
            for part in quote.pck_chain_pem.split(
                b"-----BEGIN CERTIFICATE-----"
            )[1:]
        ]
    except ValueError as exc:
        report.parse_error = f"PCK chain is not valid PEM: {exc}"
        return report

    if not report.check(
        "PCK chain has 3 certificates",
        len(chain) == 3,
        " | ".join(c.subject.rfc4514_string() for c in chain),
    ):
        # Without leaf/intermediate/root there is nothing left to walk, and
        # reporting three more bogus failures would obscure the real one.
        return report

    leaf = chain[0]
    leaf_pub = leaf.public_key().public_numbers()
    leaf_xy = leaf_pub.x.to_bytes(32, "big") + leaf_pub.y.to_bytes(32, "big")

    report.check(
        "A3 PCK leaf certificate signs the QE report",
        p256_verify(leaf_xy, quote.qe_report_signature, quote.qe_report),
    )
    report.check("A4a leaf signed by intermediate", cert_verify(chain[1], chain[0]))
    report.check("A4b intermediate signed by root", cert_verify(chain[2], chain[1]))
    report.check("A4c root is self-signed", cert_verify(chain[2], chain[2]))

    intel_root = x509.load_pem_x509_certificate(root_pem.read_bytes())
    pinned_fp = intel_root.fingerprint(hashes.SHA256()).hex()
    report.check(
        "pinned PEM is the Intel SGX Root CA this repository pins",
        pinned_fp == INTEL_SGX_ROOT_CA_SHA256,
        f"{pinned_fp} (expected {INTEL_SGX_ROOT_CA_SHA256})",
    )
    chain_fp = chain[2].fingerprint(hashes.SHA256()).hex()
    report.check(
        "A4d chain root == pinned Intel SGX Root CA",
        chain_fp == pinned_fp,
        chain_fp,
    )
    return report


# -------------------------------------------------------- the online-only part


def check_live_intel_root(root_pem: pathlib.Path) -> int:
    """Confirm the pinned PEM still matches the root Intel publishes today.

    This is the ONLY function in this file that touches the network, and it is
    never reached from the default mode.  A network failure exits 4, not 1: it
    is not evidence that anything is wrong with the attestation.
    """
    import urllib.error
    import urllib.request

    x509, hashes, ec, asym_utils, InvalidSignature = _load_cryptography()

    pinned = x509.load_pem_x509_certificate(root_pem.read_bytes())
    pinned_fp = pinned.fingerprint(hashes.SHA256()).hex()

    print("=== ONLINE: pinned Intel SGX Root CA vs. Intel's live service ===")
    print(f"  pinned PEM   : {root_pem}")
    print(f"  pinned sha256: {pinned_fp}")

    if pinned_fp != INTEL_SGX_ROOT_CA_SHA256:
        print(
            "  FAIL  the pinned PEM does not match the fingerprint this "
            f"script pins ({INTEL_SGX_ROOT_CA_SHA256})"
        )
        return EXIT_CHAIN_INVALID

    try:
        with urllib.request.urlopen(INTEL_ROOT_CA_URL, timeout=30) as response:
            body = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"  SKIP  could not reach {INTEL_ROOT_CA_URL}: {exc}")
        print(
            "  This is a NETWORK result, not an attestation result.  The "
            "offline chain gate is unaffected."
        )
        return EXIT_NETWORK

    try:
        live = x509.load_pem_x509_certificate(body)
    except ValueError:
        try:
            live = x509.load_der_x509_certificate(body)
        except ValueError as exc:
            print(f"  SKIP  Intel served something that is not a certificate: {exc}")
            return EXIT_NETWORK

    live_fp = live.fingerprint(hashes.SHA256()).hex()
    print(f"  live sha256  : {live_fp}")
    if live_fp != pinned_fp:
        print(
            "  FAIL  Intel's published SGX Root CA no longer matches the "
            "pinned PEM.  Do NOT edit the pin to make this pass without "
            "understanding why it changed."
        )
        return EXIT_CHAIN_INVALID
    print("  PASS  the pinned PEM is Intel's currently published SGX Root CA")
    return EXIT_OK


# ------------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Offline Intel certificate-chain gate for retained TDX quotes. "
            "Does not put the Intel chain into Lean's kernel."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=ROOT,
        help="repository root (default: the root containing this script)",
    )
    parser.add_argument(
        "--quote",
        type=pathlib.Path,
        action="append",
        default=None,
        help=(
            "check this quote file instead of the committed bundles "
            "(repeatable)"
        ),
    )
    parser.add_argument(
        "--intel-root",
        type=pathlib.Path,
        default=None,
        help="pinned Intel SGX Root CA PEM (default: tools/intel_sgx_root_ca.pem)",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help=(
            "treat 'no retained bundle present' as a hard failure instead of "
            "a loud skip"
        ),
    )
    parser.add_argument(
        "--check-live-intel-root",
        action="store_true",
        help=(
            "ONLINE, separate check: confirm the pinned PEM still matches the "
            "root Intel publishes.  Never run by the offline gate."
        ),
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    root_pem = args.intel_root or (repo_root / "tools/intel_sgx_root_ca.pem")
    if not root_pem.is_file():
        print(
            f"verify_tdx_quote_chain: pinned Intel root PEM is missing: {root_pem}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.check_live_intel_root:
        return check_live_intel_root(root_pem)

    print("=== OFFLINE: Intel certificate chain for retained TDX quotes ===")
    print(f"  pinned root: {root_pem}")
    print(f"  pinned root sha256 fingerprint: {INTEL_SGX_ROOT_CA_SHA256}")
    print("  (no network access is performed in this mode)")
    print()

    if args.quote:
        candidates = [(p, p) for p in args.quote]
        explicit = True
    else:
        candidates = [(repo_root / rel, pathlib.Path(rel)) for rel in KNOWN_QUOTES]
        explicit = False

    reports: list[BundleReport] = []
    skipped: list[str] = []
    for absolute, shown in candidates:
        if not absolute.is_file():
            skipped.append(str(shown))
            continue
        report = check_quote_chain(absolute, root_pem)
        report.path = str(shown)
        reports.append(report)

    for report in reports:
        report.emit()
        print()

    for name in skipped:
        print(f"  SKIP  no retained evidence bundle at {name}")
    if skipped:
        print()

    failed = [r for r in reports if r.failed]
    if failed:
        print(
            f"FAIL: {len(failed)} of {len(reports)} retained quote(s) do not "
            "chain to the pinned Intel SGX Root CA."
        )
        print(
            "This is an ATTESTATION failure, not a configuration or network "
            "one.  Do not weaken the check to make it pass."
        )
        return EXIT_CHAIN_INVALID

    if not reports:
        message = (
            "no retained TDX evidence bundle is present, so there was nothing "
            "to check"
        )
        if explicit:
            message = "none of the quote paths given on the command line exist"
        if args.require_evidence:
            print(f"FAIL: {message}, and --require-evidence was given.")
            print(
                "In this repository the bundles are committed, so their "
                "absence means a broken or partial checkout."
            )
            return EXIT_CHAIN_INVALID
        print(f"SKIP: {message}.")
        print(
            "This is NOT a pass.  Exit code 3 distinguishes it from a "
            "successful check; pass --require-evidence to make it fatal."
        )
        return EXIT_NO_EVIDENCE

    print(
        f"PASS: {len(reports)} retained quote(s) chain to the pinned Intel "
        f"SGX Root CA ({len(skipped)} bundle(s) absent)."
    )
    print(
        "Reminder: this is an out-of-kernel build gate.  Lean still does not "
        "parse PCK chains, TCB levels, or QE identities."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

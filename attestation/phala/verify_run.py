#!/usr/bin/env python3
"""Verify an x86_64 CompCert attested run from its Phala log.

Usage:

    python3 audits/compcert/rh_phala/verify_run.py --log run.log \
        [--app-compose app-compose.json] [--build-dir build/x86]

Reads the delimited base64 evidence out of the log, then checks -- offline,
against bytes committed in this repository -- the whole chain from Intel's
root certificate down to the digests of the binaries that were built here:

  E   the evidence blocks are intact (each block's SHA-256 is its own header's)
  Q   the quote is a well-formed v4 TDX quote for a non-debug TD
  A   its signature chain closes to the PINNED Intel SGX Root CA
  R   the event log replays to the four RTMRs the quote attests, and the RTMR3
      boot chain binds this app id and this compose hash
  C   the deployed app-compose document carries this repository's
      docker-compose.yaml byte for byte, and its digest is the compose hash
      the quote measured in mr_config_id
  S   the quote's report_data is the SHA-256 of the statement, and the
      statement names exactly the artifacts built here, all of which agreed

Only all of E+Q+A+R+C+S together say: *an Intel-rooted TDX enclave, running
this repository's compose, executed these CompCert-built x86_64 artifacts and
observed these results.*  Any single one of them alone says much less.

WHAT THIS DOES NOT ESTABLISH
  * Not a TCB appraisal.  Chain validity says the attestation key is
    Intel-rooted; it says nothing about whether the platform's TCB is current
    or whether a certificate has been revoked.  That needs Intel's live
    collateral and is dcap-qvl's job.
  * Not a Lean theorem.  Nothing here enters a proof term.  It is a build gate
    that makes the external check impossible to skip silently.
  * Not that the artifacts compute what their Lean atoms say.  That is the
    `evaluates_atom_predicate` field of each campaign stamp, proved elsewhere.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PINNED_ROOT_PEM = ROOT / "tools/attest/intel_sgx_root_ca.pem"

# SHA-256 of the Intel SGX Root CA certificate published at
# certificates.trustedservices.intel.com.  Pinned here as well as in the PEM,
# so swapping the PEM alone cannot redirect the trust root.
INTEL_SGX_ROOT_CA_SHA256 = "44a0196b2b99f889b8e149e95b807a350e7424964399e885a7cbb8ccfab674d3"

MARKER = "RH-X86-EVIDENCE-V1"
STATEMENT_DOMAIN = "sparkinterval.attested-compcert-run.v1"

HEADER_SIZE = 48
TD_REPORT_SIZE = 584
SGX_REPORT_SIZE = 384
# Absolute offsets into the quote (48-byte header + TD report body).
OFF_MRTD = 184
OFF_MR_CONFIG_ID = 232
OFF_RTMR = (376, 424, 472, 520)
OFF_REPORT_DATA = 568
OFF_TD_ATTRIBUTES = 168
DSTACK_RTMR3_EVENT_TYPE = 0x08000001
INIT_MR = bytes(48)


def _committed_field(name: str, value: str) -> str:
    return f"{name}={hashlib.sha256(value.encode()).hexdigest()}\n"


def _report_data_hash(enclave_public_key_hex: str, statement_sha256: str) -> str:
    """Mirror of `tg_verifier.compcert_run_receipt.report_data_hash`.

    Re-implemented here rather than imported, so this checker depends on this
    repository alone: a verifier that reaches into the producer's tree to
    check the producer is not much of a verifier.
    """
    preimage = ("sparkinterval.compcert-run-report-data.v1\n"
                + _committed_field("enclave_public_key", enclave_public_key_hex)
                + _committed_field("statement_sha256", statement_sha256))
    return hashlib.sha256(preimage.encode()).hexdigest()


RECEIPT_FIELD_ORDER = (
    "algorithm_id", "algorithm_hash", "input_hash", "result", "output_hash",
    "matched_pinned_expectation", "app_id", "compose_hash",
    "app_compose_sha256", "docker_compose_file_sha256", "tdx_quote_sha256",
    "report_data_sha256", "issued_at")


def _receipt_digest(fields: dict) -> str | None:
    """The receipt's canonical payload digest; None if the field set differs.

    An unexpected field set is a refusal rather than a best effort: a receipt
    carrying an extra field would otherwise be signed over a payload the
    verifier never saw.
    """
    if set(fields) != set(RECEIPT_FIELD_ORDER):
        return None
    payload = "sparkinterval.compcert-run-receipt.v1\n"
    for name in RECEIPT_FIELD_ORDER:
        payload += _committed_field(name, fields[name])
    return hashlib.sha256(payload.encode()).hexdigest()


class Report:
    """Collects check outcomes; any failure makes the whole run fail."""

    def __init__(self) -> None:
        self.failed = 0
        self.skipped = 0

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            self.failed += 1
        print(f"  [{mark}] {label}" + (f"   {detail}" if detail else ""))
        return ok

    def skip(self, label: str, why: str) -> None:
        self.skipped += 1
        print(f"  [SKIP] {label}   {why}")


# --------------------------------------------------------------------------
# evidence transport


def parse_evidence(log_text: str) -> dict[str, bytes]:
    """Pull the delimited base64 blocks out of a Phala log.

    The marker is located in the line rather than anchored to its start,
    because `phala cvms logs` prefixes timestamps.
    """
    blocks: dict[str, bytes] = {}
    current: str | None = None
    chunks: list[str] = []
    declared: dict[str, str] = {}
    for line in log_text.splitlines():
        position = line.find(MARKER)
        if position < 0:
            continue
        rest = line[position + len(MARKER):].strip()
        if rest.startswith("BEGIN "):
            header = json.loads(rest[len("BEGIN "):])
            current, chunks = header["name"], []
            declared[current] = header["sha256"]
        elif rest.startswith("DATA ") and current is not None:
            chunks.append(rest[len("DATA "):].strip())
        elif rest.startswith("END "):
            trailer = json.loads(rest[len("END "):])
            name = trailer["name"]
            raw = base64.b64decode("".join(chunks))
            if hashlib.sha256(raw).hexdigest() != declared.get(name):
                raise SystemExit(f"evidence block {name}: digest mismatch (log truncated?)")
            blocks[name] = raw
            current, chunks = None, []
    return blocks


# --------------------------------------------------------------------------
# quote parsing and the Intel chain


class QuoteError(RuntimeError):
    pass


class Quote:
    def __init__(self, raw: bytes) -> None:
        if len(raw) < HEADER_SIZE + TD_REPORT_SIZE + 4:
            raise QuoteError(f"quote is only {len(raw)} bytes")
        self.raw = raw
        self.version = int.from_bytes(raw[0:2], "little")
        self.att_key_type = int.from_bytes(raw[2:4], "little")
        self.tee_type = int.from_bytes(raw[4:8], "little")
        self.header = raw[:HEADER_SIZE]
        self.td_report = raw[HEADER_SIZE:HEADER_SIZE + TD_REPORT_SIZE]
        self.td_attributes = raw[OFF_TD_ATTRIBUTES:OFF_TD_ATTRIBUTES + 8]
        self.mrtd = raw[OFF_MRTD:OFF_MRTD + 48]
        self.mr_config_id = raw[OFF_MR_CONFIG_ID:OFF_MR_CONFIG_ID + 48]
        self.rtmrs = [raw[o:o + 48].hex() for o in OFF_RTMR]
        self.report_data = raw[OFF_REPORT_DATA:OFF_REPORT_DATA + 64]

        offset = HEADER_SIZE + TD_REPORT_SIZE
        sig_len = int.from_bytes(raw[offset:offset + 4], "little")
        offset += 4
        blob = raw[offset:offset + sig_len]
        if len(blob) != sig_len:
            raise QuoteError("signature blob is truncated")
        self.quote_signature = blob[0:64]
        self.attest_pub_key = blob[64:128]
        cert_type = int.from_bytes(blob[128:130], "little")
        if cert_type != 6:
            raise QuoteError(f"unexpected certification data type {cert_type}")
        inner = blob[134:134 + int.from_bytes(blob[130:134], "little")]
        self.qe_report = inner[0:SGX_REPORT_SIZE]
        self.qe_report_data = self.qe_report[320:384]
        self.qe_report_signature = inner[SGX_REPORT_SIZE:SGX_REPORT_SIZE + 64]
        cursor = SGX_REPORT_SIZE + 64
        auth_size = int.from_bytes(inner[cursor:cursor + 2], "little")
        cursor += 2
        self.qe_auth_data = inner[cursor:cursor + auth_size]
        cursor += auth_size
        cursor += 2  # PCK cert data type
        pck_size = int.from_bytes(inner[cursor:cursor + 4], "little")
        cursor += 4
        self.pck_chain_pem = inner[cursor:cursor + pck_size]


def verify_chain(quote: Quote, report: Report) -> None:
    """A1-A4d: the quote was produced by an Intel-rooted attestation key."""
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric import utils as asym

    def p256_verify(pub_xy: bytes, signature: bytes, message: bytes) -> bool:
        key = ec.EllipticCurvePublicNumbers(
            int.from_bytes(pub_xy[:32], "big"),
            int.from_bytes(pub_xy[32:], "big"),
            ec.SECP256R1(),
        ).public_key()
        der = asym.encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        try:
            key.verify(der, message, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False

    def cert_verify(child: x509.Certificate, parent: x509.Certificate) -> bool:
        try:
            parent.public_key().verify(
                child.signature, child.tbs_certificate_bytes,
                ec.ECDSA(child.signature_hash_algorithm))
            return True
        except InvalidSignature:
            return False

    report.check("A1 attestation key signs header || TD report",
                 p256_verify(quote.attest_pub_key, quote.quote_signature,
                             quote.header + quote.td_report))
    expect = hashlib.sha256(quote.attest_pub_key + quote.qe_auth_data).digest()
    report.check("A2 QE report data binds the attestation key",
                 quote.qe_report_data[:32] == expect
                 and quote.qe_report_data[32:] == bytes(32))

    parts = quote.pck_chain_pem.split(b"-----BEGIN CERTIFICATE-----")[1:]
    certs = [x509.load_pem_x509_certificate(b"-----BEGIN CERTIFICATE-----" + p)
             for p in parts]
    if not report.check("A3a PCK chain has leaf, intermediate and root",
                        len(certs) == 3, f"{len(certs)} certificates"):
        return
    leaf, intermediate, root = certs
    leaf_xy = (leaf.public_key().public_numbers().x.to_bytes(32, "big")
               + leaf.public_key().public_numbers().y.to_bytes(32, "big"))
    report.check("A3b PCK leaf public key signs the QE report",
                 p256_verify(leaf_xy, quote.qe_report_signature, quote.qe_report))
    report.check("A4a leaf is signed by the intermediate", cert_verify(leaf, intermediate))
    report.check("A4b intermediate is signed by the root", cert_verify(intermediate, root))
    report.check("A4c root is self-signed", cert_verify(root, root))

    fingerprint = hashlib.sha256(
        root.public_bytes(__import__("cryptography.hazmat.primitives.serialization",
                                     fromlist=["Encoding"]).Encoding.DER)).hexdigest()
    report.check("A4d root is the pinned Intel SGX Root CA",
                 fingerprint == INTEL_SGX_ROOT_CA_SHA256, fingerprint[:24] + "…")
    pinned = x509.load_pem_x509_certificate(PINNED_ROOT_PEM.read_bytes())
    report.check("A4e pinned PEM in this repository is that same root",
                 pinned.fingerprint(hashes.SHA256()).hex() == INTEL_SGX_ROOT_CA_SHA256)


# --------------------------------------------------------------------------
# event log


def replay_rtmr(history: list[str]) -> str:
    measurement = INIT_MR
    for digest_hex in history:
        content = bytes.fromhex(digest_hex)
        if len(content) < 48:
            content = content.ljust(48, b"\x00")
        measurement = hashlib.sha384(measurement + content).digest()
    return measurement.hex()


# The posture the deployment is required to declare.  Kept next to the check
# rather than inline so it can be tested directly: tampering with the emitted
# document cannot exercise it, because each evidence block is digest-checked
# before any of these checks run.
REQUIRED_POSTURE = {"network_mode": "none", "read_only": True,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"]}


def missing_posture(service: dict) -> list[str]:
    """Which hardening declarations a compose service is missing.

    `exec` on the /tmp tmpfs is included but is not hardening: Docker mounts a
    tmpfs `noexec` by default, artifacts are executed from /tmp, and its
    absence fails the run outright with exit 126 rather than weakening it.
    """
    missing = [k for k, v in REQUIRED_POSTURE.items() if service.get(k) != v]
    for mount in service.get("tmpfs", []):
        target, _, opts = mount.partition(":")
        if target == "/tmp":
            if "exec" not in opts.split(","):
                missing.append("tmpfs /tmp exec")
            break
    else:
        missing.append("tmpfs /tmp")
    return missing


def check_event_log(events: list[dict], quote: Quote, report: Report) -> dict[str, str | None]:
    for index in range(4):
        history = [str(e["digest"]).lower() for e in events if int(e["imr"]) == index]
        report.check(f"R1.{index} event log replays to the attested RTMR{index}",
                     replay_rtmr(history) == quote.rtmrs[index],
                     f"{len(history)} events")

    # Truncate at system-ready: an app may EmitEvent at any time, and a
    # post-boot event named `app-id` must not be read as the boot binding.
    boot_chain: list[dict] = []
    for event in (e for e in events if int(e["imr"]) == 3):
        boot_chain.append(event)
        if event.get("event") == "system-ready":
            break
    bound: dict[str, str | None] = {}
    for name in ("app-id", "compose-hash", "instance-id", "os-image-hash"):
        matches = [str(e.get("event_payload", "")).lower()
                   for e in boot_chain if e.get("event") == name]
        if len(matches) > 1:
            report.check(f"R2 RTMR3 boot chain records {name!r} exactly once", False)
            matches = matches[:1]
        bound[name] = matches[0] if matches else None
    report.check("R2 RTMR3 boot chain records app-id and compose-hash",
                 bound["app-id"] is not None and bound["compose-hash"] is not None,
                 " ".join(f"{k}={'yes' if v else 'no'}" for k, v in bound.items()))
    return bound


# --------------------------------------------------------------------------


def parse_statement(text: str) -> dict:
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines or lines[0] != STATEMENT_DOMAIN:
        raise SystemExit(f"statement does not open with {STATEMENT_DOMAIN}")
    fields: dict[str, str] = {}
    artifacts: list[dict] = []
    differentials: list[dict] = []
    sources: list[dict] = []
    for line in lines[1:]:
        tokens = dict(t.split("=", 1) for t in line.split(" "))
        if "artifact" in tokens:
            artifacts.append(tokens)
        elif "gcc_differential" in tokens:
            differentials.append(tokens)
        elif "source" in tokens:
            sources.append(tokens)
        else:
            fields.update(tokens)
    return {"fields": fields, "artifacts": artifacts,
            "differentials": differentials, "sources": sources}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", required=True, type=pathlib.Path,
                        help="the `phala cvms logs` transcript")
    parser.add_argument("--app-compose", type=pathlib.Path,
                        help="the deployed app-compose.json (fetched by deploy.sh)")
    parser.add_argument("--deployment", type=pathlib.Path,
                        help="directory holding docker-compose.yaml and the "
                             "artifacts; defaults to the log's directory")
    parser.add_argument("--build-dir", type=pathlib.Path,
                        help="the artifacts and their stamps; defaults to "
                             "<deployment>/x86-artifacts")
    parser.add_argument("--evidence-dir", type=pathlib.Path,
                        help="write the extracted evidence files here")
    args = parser.parse_args()

    # The deployment being checked: where its compose and artifacts live.  A
    # verifier that hardcoded a consumer's layout could only check that
    # consumer's runs.
    deployment = (args.deployment or args.log.resolve().parent).resolve()
    if not (deployment / "docker-compose.yaml").exists():
        deployment = deployment.parent
    args.build_dir = args.build_dir or (deployment / "x86-artifacts")

    report = Report()
    blocks = parse_evidence(args.log.read_text(errors="replace"))
    print("== E  evidence transport ==")
    for name in ("statement.txt", "tdx-quote.bin", "dstack-info.json",
                 "dstack-event-log.json"):
        report.check(f"E {name} present and its digest matches its header",
                     name in blocks, f"{len(blocks.get(name, b'')):,} bytes")
    # Optional blocks: absent when the enclave could not locate the app-compose
    # document.  Reported, never fatal -- the C section says what that costs.
    for name in ("appcompose-search.txt", "app-compose.json"):
        if name in blocks:
            print(f"  [PASS] E {name} present and its digest matches its header"
                  f"   {len(blocks[name]):,} bytes")
        else:
            report.skip(f"E {name}", "not emitted by this run")
    if report.failed:
        print("\nverify: no usable evidence in the log")
        return 1

    if args.evidence_dir:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
        for name, raw in blocks.items():
            (args.evidence_dir / name).write_bytes(raw)
        print(f"  evidence written to {args.evidence_dir}")

    quote = Quote(blocks["tdx-quote.bin"])
    info = json.loads(blocks["dstack-info.json"])
    events = json.loads(blocks["dstack-event-log.json"])
    statement_raw = blocks["statement.txt"]
    statement = parse_statement(statement_raw.decode())

    print("\n== Q  the quote is a well-formed, non-debug TDX quote ==")
    report.check("Q1 v4 quote, ECDSA-P256 attestation key, TEE type TDX",
                 quote.version >= 4 and quote.att_key_type == 2 and quote.tee_type == 0x81,
                 f"version={quote.version} tee_type=0x{quote.tee_type:02x}")
    report.check("Q2 TD DEBUG attribute is clear",
                 not (quote.td_attributes[0] & 0x01),
                 f"td_attributes={quote.td_attributes.hex()}")
    print(f"  mrtd  = {quote.mrtd.hex()[:32]}…")
    for i, rtmr in enumerate(quote.rtmrs):
        print(f"  rtmr{i} = {rtmr[:32]}…")

    print("\n== A  the Intel certificate chain ==")
    verify_chain(quote, report)

    print("\n== R  the event log and the RTMRs ==")
    bound = check_event_log(events, quote, report)
    compose_hash = info.get("compose_hash", "")
    app_id = info.get("app_id", "")
    report.check("R3 RTMR3 app-id matches /Info", bound["app-id"] == app_id, app_id)
    report.check("R4 RTMR3 compose-hash matches /Info",
                 bound["compose-hash"] == compose_hash, compose_hash)

    print("\n== C  the compose the enclave measured is this repository's ==")
    report.check("C1 quote mr_config_id is 01 || compose_hash || 15 zero bytes",
                 quote.mr_config_id[0] == 0x01
                 and quote.mr_config_id[1:33].hex() == compose_hash
                 and quote.mr_config_id[33:] == bytes(15),
                 quote.mr_config_id.hex()[:34] + "…")
    local_compose = (deployment / "docker-compose.yaml").read_bytes()
    local_digest = hashlib.sha256(local_compose).hexdigest()

    # The enclave read the app-compose document's RAW bytes inside the measured
    # VM and committed two digests into the statement, so they sit inside
    # report_data.  That is the only sound way to close this: the Cloud API's
    # JSON view of the document is NOT byte-faithful -- its key set and ordering
    # differ from what dstack hashed, and 224 candidate re-serializations under
    # the CLI's own algorithm (recursive key sort, indent 4, then s/": /":/g)
    # all missed the measured hash.
    fields = statement["fields"]
    attested_doc = fields.get("app_compose_sha256")
    if attested_doc and attested_doc != "unavailable":
        report.check("C2 the document the enclave read IS the measured one "
                     "(its raw digest is the compose hash)",
                     attested_doc == compose_hash and fields.get("self_consistent") == "1",
                     attested_doc[:24] + "\u2026")
        report.check("C3 that measured document carries this repository's "
                     "docker-compose.yaml, byte for byte",
                     fields.get("docker_compose_file_sha256") == local_digest,
                     f"{fields.get('bytes','?')} bytes, {local_digest[:16]}\u2026")
        # C4/C5 recompute both digests from the emitted bytes, so the enclave's
        # own arithmetic is checked rather than trusted.
        document = blocks.get("app-compose.json")
        if document is not None:
            report.check("C4 recomputed from the emitted document: its digest IS "
                         "the compose hash",
                         hashlib.sha256(document).hexdigest() == compose_hash,
                         f"{len(document):,} bytes")
            try:
                inner = json.loads(document)["docker_compose_file"].encode()
            except Exception:  # noqa: BLE001
                inner = b""
            report.check("C5 recomputed: the measured document's "
                         "docker_compose_file is this repository's compose",
                         inner == local_compose,
                         f"{len(inner):,} vs {len(local_compose):,} bytes")
            # C6 reads the posture out of the document the CPU actually
            # hashed, not out of the file on disk.  C3/C5 already prove the
            # two are the same, so this is not a second integrity check -- it
            # is a statement about CONTENT: that the deployment which ran was
            # the hardened one.  Without it a future compose could quietly drop
            # `read_only` and every other check would still pass, because they
            # only ask whether the bytes are consistent, never whether they say
            # the right thing.
            try:
                # The compose carries a `#` header before its JSON, exactly as
                # everywhere else in this file -- parsing from byte zero fails
                # and would report every field as missing.
                svc = next(iter(json.loads(inner[inner.index(b"{"):])["services"].values()))
            except Exception:  # noqa: BLE001
                svc = {}
            missing = missing_posture(svc)
            report.check("C6 the measured compose declares the hardened posture",
                         not missing,
                         "no network, read-only, no capabilities, "
                         "no-new-privileges, exec workdir" if not missing
                         else "MISSING: " + ", ".join(missing))
        else:
            report.skip("C4/C5 recomputation from the emitted document",
                        "the raw document was not emitted; C2/C3 rest on the "
                        "enclave's own digest computation")
    else:
        report.skip("C2/C3 measured-document binding",
                    "the enclave could not locate the app-compose document; see "
                    "appcompose-search.txt in the evidence")
        if args.app_compose and args.app_compose.exists():
            # Weaker fallback: the Cloud API's view.  It cannot be bound to
            # mr_config_id (see above), so it is reported separately and is
            # never counted as C2.
            try:
                embedded = json.loads(args.app_compose.read_bytes())["docker_compose_file"].encode()
            except Exception:  # noqa: BLE001
                embedded = b""
            report.check("C3' (API-reported, NOT measurement-bound) the deployed "
                         "compose is this repository's, byte for byte",
                         embedded == local_compose,
                         f"{len(embedded):,} vs {len(local_compose):,} bytes")

    print("\n== S  the quote attests THESE results ==")
    digest = hashlib.sha256(statement_raw).hexdigest()
    # report_data commits to the signing key AND the statement.  Either alone
    # would leave the other unbound: a key with no results attests that nothing
    # happened, and results with no key let anyone sign them.
    receipts = json.loads(blocks["receipts.json"]) if "receipts.json" in blocks else []
    enclave_key = (receipts[0].get("enclave_public_key") if receipts
                   else statement["fields"].get("enclave_public_key"))
    expected_rd = _report_data_hash(enclave_key, digest) if enclave_key else None
    report.check("S1 quote report_data is H(enclave public key, statement)",
                 expected_rd is not None
                 and quote.report_data[:32].hex() == expected_rd,
                 (expected_rd or "no key")[:24] + "…")
    report.check("S2 report_data upper half is zero (no second commitment)",
                 quote.report_data[32:] == bytes(32))
    report.check("S3 statement names the measured compose hash",
                 statement["fields"].get("compose_hash") == compose_hash)

    print()
    for entry in statement["artifacts"]:
        name = entry["artifact"]
        stamp_path = args.build_dir / f"{name}.x86.stamp.json"
        if stamp_path.exists():
            stamp = json.loads(stamp_path.read_text())
            report.check(f"S4 {name}: the attested binary is the one built here",
                         stamp["binary_sha256"] == entry["binary_sha256"],
                         entry["binary_sha256"][:16] + "…")
            report.check(f"S5 {name}: built for x86_64 by CompCert",
                         stamp["target"] == "x86_64-linux"
                         and "x86-64" in stamp["file"]
                         and stamp["toolchain"]["ccomp_version"].startswith("The CompCert"),
                         stamp["toolchain"]["ccomp_version"])
        else:
            report.skip(f"S4/S5 {name}", f"no local stamp at {stamp_path}")
        report.check(f"S6 {name}: agreed with its certified constant (exit 0)",
                     entry["exit"] == "0", f"exit={entry['exit']}")
        # S6b/S6c are the difference between "the binary said it passed" and
        # "the computation produced the expected numbers".  The enclave compared
        # against expectations pinned in the measured compose; these re-derive
        # those expectations from the local build stamp and check both halves.
        report.check(f"S6b {name}: the enclave's own check against the pinned "
                     "expectation passed",
                     entry.get("matched_pinned_expectation") == "1",
                     f"matched={entry.get('matched_pinned_expectation')}")
        if stamp_path.exists():
            expected_out = json.loads(stamp_path.read_text())["qemu_self_check"].get("stdout_sha256")
            report.check(f"S6c {name}: the attested transcript is the expected "
                         "one, byte for byte",
                         expected_out is not None
                         and entry["stdout_sha256"] == expected_out,
                         (expected_out or "none")[:16] + "\u2026")
    print()
    compose_text = local_compose.decode()
    # The single service, whatever it is called: the pipeline names no
    # deployment, so neither does the verifier.
    services = json.loads(compose_text[compose_text.index("{"):])["services"]
    compose_env = next(iter(services.values()))["environment"]
    for entry in statement["artifacts"]:
        name = entry["artifact"]
        stamp_path = args.build_dir / f"{name}.x86.stamp.json"
        if not stamp_path.exists():
            continue
        expected_out = json.loads(stamp_path.read_text())["qemu_self_check"].get("stdout_sha256")
        # Find this artifact's index in the compose, rather than mapping names
        # to prefixes that only one deployment would have.
        idx = next((i for i in range(int(compose_env.get("ARTIFACT_COUNT", "0")))
                    if compose_env.get(f"A{i}_NAME") == name), None)
        report.check(f"S9 {name}: the expectation the enclave was given is the "
                     "one recorded here",
                     idx is not None
                     and compose_env.get(f"A{idx}_EXPECT_SHA") == expected_out
                     and compose_env.get(f"A{idx}_EXPECT_EXIT") == "0",
                     f"A{idx}_EXPECT_SHA="
                     f"{(compose_env.get(f'A{idx}_EXPECT_SHA') or '')[:16]}\u2026"
                     if idx is not None else "not in the compose")

    print()
    for entry in statement["differentials"]:
        report.check(f"S7 {entry['gcc_differential']}: enclave gcc transcript is "
                     "identical to CompCert's", entry["identical"] == "1")
    for entry in statement["sources"]:
        name = entry["source"]
        # Source paths come from the deployment manifest, the same place the
        # compose generator read them from.
        local = None
        mf = deployment / "deployment.json"
        if mf.exists():
            # NOT `entry`: that is the statement's source record, and shadowing
            # it here made the check below read the manifest's keys instead.
            for declared in json.loads(mf.read_text()).get("sources", []):
                if declared.get("name") == name:
                    local = (deployment / declared["path"]).resolve()
        if local is None:
            local = deployment / name
        if local.exists():
            report.check(f"S8 {name}: matches the committed source",
                         hashlib.sha256(local.read_bytes()).hexdigest() == entry["sha256"])
        else:
            report.skip(f"S8 {name}", "not found in this repository")


    print("== G  the enclave signed these results ==")
    if not receipts:
        report.skip("G signed receipts", "this run emitted none")
    else:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes as _hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric import utils as _asym

        def p256_verify_prehashed(pub_hex: str, digest_hex: str,
                                  sig_hex: str) -> bool:
            raw = bytes.fromhex(pub_hex)
            if len(raw) != 65 or raw[0] != 0x04:
                return False
            key = ec.EllipticCurvePublicNumbers(
                int.from_bytes(raw[1:33], "big"),
                int.from_bytes(raw[33:], "big"), ec.SECP256R1()).public_key()
            sig = bytes.fromhex(sig_hex)
            if len(sig) != 64:
                return False
            der = _asym.encode_dss_signature(
                int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
            try:
                key.verify(der, bytes.fromhex(digest_hex),
                           ec.ECDSA(_asym.Prehashed(_hashes.SHA256())))
                return True
            except InvalidSignature:
                return False

        report.check("G1 every receipt names one and the same enclave key",
                     len({r.get("enclave_public_key") for r in receipts}) == 1,
                     (enclave_key or "")[:24] + "\u2026")
        quote_sha = hashlib.sha256(quote.raw).hexdigest()
        for r in receipts:
            fields = r.get("signed_fields", {})
            name = fields.get("algorithm_id", "?")
            recomputed = _receipt_digest(fields)
            report.check(f"G2 {name}: canonical digest recomputes",
                         recomputed is not None
                         and recomputed == r.get("receipt_sha256"))
            report.check(f"G3 {name}: P-256 signature verifies",
                         recomputed is not None
                         and p256_verify_prehashed(r.get("enclave_public_key", ""),
                                                   recomputed,
                                                   r.get("signature", "")))
            report.check(f"G4 {name}: names this quote and this compose",
                         fields.get("tdx_quote_sha256") == quote_sha
                         and fields.get("compose_hash") == compose_hash)
            report.check(f"G5 {name}: the enclave's pinned-expectation check passed",
                         fields.get("matched_pinned_expectation") == "1")

    print()
    if report.failed:
        print(f"verify: FAILED — {report.failed} check(s) did not pass")
        return 1
    if report.skipped:
        print(f"verify: PASSED, with {report.skipped} check(s) SKIPPED (see [SKIP] above)")
        return 0
    print("verify: PASSED — every check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Collect legacy diagnostic Azure NCC H100 CPU/GPU evidence.

The result is an evidence package for an independent relying-party verifier.
It is not itself an acceptance certificate and does not assert that the
finite algorithm was mathematically correct.  This legacy path resets PCR23
after the workload and is therefore structurally rejected by certificate
issuance.  Use ``collect_azure_measured_evidence.py`` for challenge-first
zero->start->result evidence.  Every command fails closed.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Sequence
from urllib.parse import parse_qsl, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPOSITORY_ROOT / "attestation" / "policies" / "gpu_prover_h100.rego"
DEFAULT_MAA_COMMAND = Path("/usr/local/lib/cvm-attestation/attest")
KIND = "gpu_prover_azure_ncc_evidence"
SCHEMA_VERSION = 1
CHALLENGE_KIND = "gpu_prover_azure_run_challenge"
BACKENDS = ("azure_sevsnp_cpu", "azure_ncc40ads_h100_v5")
HEX256_RE = re.compile(r"^[0-9a-f]{64}$")
JWT_RE = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)(?![A-Za-z0-9_-])")
RESULT_BINDING_HEADER = "sparkinterval.trusted-compute.result-binding.v1\n"
TPM_PCR_SELECTION = "sha256:0,1,2,3,4,5,6,7,23"
MAA_PROVIDER = "maa_snp"
MAA_SEVSNP_PATH = "/attest/SevSnpVm"
MAA_API_VERSION = "2022-08-01"
MAX_CHALLENGE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_TOOL_OUTPUT_BYTES = 16 * 1024 * 1024
SYSTEM_EXECUTABLE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class EvidenceError(RuntimeError):
    """Evidence was missing, malformed, or did not match the run statement."""


def _validate_canonical_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        raise EvidenceError(f"floating-point JSON is forbidden at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_canonical_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceError(f"non-string JSON key at {path}")
            _validate_canonical_value(item, f"{path}.{key}")
        return
    raise EvidenceError(f"unsupported canonical JSON value at {path}")


def canonical_json_bytes(value: Any) -> bytes:
    _validate_canonical_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _parse_canonical_json(raw: bytes, what: str) -> Any:
    def reject_float(value: str) -> None:
        raise EvidenceError(f"floating-point JSON is forbidden in {what}: {value}")

    def reject_constant(value: str) -> None:
        raise EvidenceError(f"non-finite JSON is forbidden in {what}: {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceError(f"duplicate JSON key in {what}: {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            parse_float=reject_float,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot parse {what}: {error}") from error
    _validate_canonical_value(value)
    return value


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def derive_binding_nonce(challenge: str, statement_sha256: str) -> str:
    if HEX256_RE.fullmatch(challenge) is None:
        raise EvidenceError("challenge nonce must be 32 bytes of lowercase hex")
    if HEX256_RE.fullmatch(statement_sha256) is None:
        raise EvidenceError("statement digest must be a lowercase SHA-256 hex digest")
    payload = (
        RESULT_BINDING_HEADER
        + f"start_challenge_sha256={challenge}\n"
        + f"wire_statement_sha256={statement_sha256}\n"
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def validate_maa_attestation_url(value: str) -> tuple[str, str]:
    """Return the exact URL and its issuer origin, rejecting ambiguous endpoints."""
    if not isinstance(value, str) or not value:
        raise EvidenceError("MAA attestation URL must be a nonempty string")
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise EvidenceError(f"MAA attestation URL is malformed: {error}") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path != MAA_SEVSNP_PATH
        or parse_qsl(parsed.query, keep_blank_values=True)
        != [("api-version", MAA_API_VERSION)]
    ):
        raise EvidenceError(
            "MAA attestation URL must be an exact HTTPS "
            f"{MAA_SEVSNP_PATH}?api-version={MAA_API_VERSION} endpoint"
        )
    try:
        explicit_port = parsed.port
    except ValueError as error:
        raise EvidenceError(f"MAA attestation URL has an invalid port: {error}") from error
    if explicit_port is not None:
        raise EvidenceError("MAA attestation URL must use the implicit default HTTPS port")
    canonical_host = parsed.hostname.lower()
    labels = canonical_host.split(".")
    if (
        parsed.netloc != canonical_host
        or len(canonical_host) > 253
        or any(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            is None
            for label in labels
        )
    ):
        raise EvidenceError("MAA attestation URL host must be a canonical lowercase DNS name")
    issuer = f"https://{canonical_host}"
    return value, issuer


def require_current_challenge_window(value: dict[str, Any]) -> tuple[dt.datetime, dt.datetime]:
    times: dict[str, dt.datetime] = {}
    for name in ("issued_at_utc", "expires_at_utc"):
        raw_time = value.get(name)
        if not isinstance(raw_time, str) or UTC_RE.fullmatch(raw_time) is None:
            raise EvidenceError(f"challenge {name} must be canonical UTC to whole seconds")
        try:
            times[name] = dt.datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError as error:
            raise EvidenceError(f"challenge {name} is not a real UTC timestamp") from error
    issued = times["issued_at_utc"]
    expires = times["expires_at_utc"]
    lifetime = expires - issued
    now = dt.datetime.now(dt.timezone.utc)
    if not dt.timedelta(0) < lifetime <= dt.timedelta(
        seconds=MAX_CHALLENGE_TTL_SECONDS
    ):
        raise EvidenceError("challenge lifetime is empty or exceeds the maximum")
    if not issued <= now < expires:
        raise EvidenceError("challenge is not in its current validity window")
    return issued, expires


def load_challenge(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = _parse_canonical_json(raw, f"challenge {path}")
    except OSError as error:
        raise EvidenceError(f"cannot load challenge {path}: {error}") from error
    expected = {
        "campaign_id",
        "expires_at_utc",
        "issued_at_utc",
        "kind",
        "nonce",
        "schema_version",
        "shard_index",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceError("challenge has unexpected fields")
    canonical = canonical_json_bytes(value)
    if raw not in (canonical, canonical + b"\n"):
        raise EvidenceError("challenge is not canonical JSON")
    if value["kind"] != CHALLENGE_KIND or value["schema_version"] != 1:
        raise EvidenceError("unsupported challenge kind/version")
    if HEX256_RE.fullmatch(value["nonce"]) is None:
        raise EvidenceError("challenge nonce is malformed")
    if not isinstance(value["campaign_id"], str) or CAMPAIGN_RE.fullmatch(
        value["campaign_id"]
    ) is None:
        raise EvidenceError("challenge campaign id is malformed")
    if (
        not isinstance(value["shard_index"], int)
        or isinstance(value["shard_index"], bool)
        or not 0 <= value["shard_index"] <= 998
    ):
        raise EvidenceError("challenge shard index must be an integer")
    require_current_challenge_window(value)
    return value


def verify_statement_file(path: Path, expected_sha256: str, challenge_nonce: str) -> None:
    try:
        raw = path.read_bytes()
        value = _parse_canonical_json(raw, f"statement {path}")
    except OSError as error:
        raise EvidenceError(f"cannot load statement {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError("run statement must be a JSON object")
    if value.get("nonce") != challenge_nonce:
        raise EvidenceError("run statement does not contain the retained start challenge as nonce")
    canonical = canonical_json_bytes(value)
    if raw not in (canonical, canonical + b"\n"):
        raise EvidenceError("statement file is not canonical JSON")
    actual = hashlib.sha256(canonical).hexdigest()
    if actual != expected_sha256:
        raise EvidenceError(
            f"statement file digest {actual} does not match {expected_sha256}"
        )


def _which(command: str | Path) -> str:
    text = str(command)
    if "/" in text:
        path = Path(text)
        if not path.is_absolute():
            raise EvidenceError(f"executable paths must be absolute: {path}")
        if not path.is_file() or not os.access(path, os.X_OK):
            raise EvidenceError(f"required executable is absent: {path}")
        return str(path)
    result = shutil.which(text, path=SYSTEM_EXECUTABLE_PATH)
    if result is None:
        raise EvidenceError(f"required executable is absent from fixed system PATH: {text}")
    return result


def _collector_environment(*, include_nvidia_service_key: bool = False) -> dict[str, str]:
    """Return the fixed environment allowed into evidence-collection tools."""

    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": SYSTEM_EXECUTABLE_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }
    if include_nvidia_service_key:
        service_key = os.environ.get("NV_ATTESTATION_SERVICE_KEY")
        if not service_key:
            raise EvidenceError(
                "remote NVIDIA verification requires NV_ATTESTATION_SERVICE_KEY"
            )
        environment["NV_ATTESTATION_SERVICE_KEY"] = service_key
    return environment


def _is_remote_nvattest_command(command: Sequence[str], label: str) -> bool:
    values = list(command)
    if label != "nvattest_attest" or len(values) < 7:
        return False
    if Path(values[0]).name != "nvattest":
        return False
    if values[1:6] != ["--log-level", "error", "--format", "json", "attest"]:
        return False
    for option, expected in (
        ("--device", "gpu"),
        ("--verifier", "remote"),
        ("--gpu-evidence-source", "file"),
    ):
        if values.count(option) != 1:
            return False
        index = values.index(option)
        if index + 1 >= len(values) or values[index + 1] != expected:
            return False
    return values.count("--nras-url") == 1


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _run(
    command: Sequence[str],
    *,
    directory: Path,
    label: str,
    timeout: int = 600,
    include_nvidia_service_key: bool = False,
    maximum_output_bytes: int = MAX_TOOL_OUTPUT_BYTES,
) -> str:
    if maximum_output_bytes <= 0:
        raise EvidenceError("tool output limit must be positive")
    if include_nvidia_service_key and not _is_remote_nvattest_command(command, label):
        raise EvidenceError(
            "NV_ATTESTATION_SERVICE_KEY may be forwarded only to exact remote nvattest attest"
        )
    environment = _collector_environment(
        include_nvidia_service_key=include_nvidia_service_key
    )
    secret = environment.get("NV_ATTESTATION_SERVICE_KEY", "").encode("utf-8")
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    output = {"stdout": bytearray(), "stderr": bytearray()}

    def retain_logs() -> None:
        for stream_name, contents in output.items():
            retained = bytes(contents)
            if secret:
                retained = retained.replace(secret, b"<redacted-nvidia-service-key>")
            (directory / f"{label}.{stream_name}.txt").write_bytes(retained)

    try:
        process = subprocess.Popen(
            list(command),
            cwd=directory,
            env=environment,
            shell=False,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise EvidenceError(f"{label} could not run: {error}") from error
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout
    failure: str | None = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = f"{label} exceeded timeout of {timeout} seconds"
                break
            for key, _events in selector.select(min(remaining, 1.0)):
                block = os.read(key.fileobj.fileno(), 64 * 1024)
                if not block:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                stream_name = key.data
                retained = output[stream_name]
                available = maximum_output_bytes - len(retained)
                retained.extend(block[: max(0, available)])
                if len(block) > available:
                    failure = (
                        f"{label} {stream_name} exceeded {maximum_output_bytes} bytes"
                    )
                    break
            if failure is not None:
                break
        if failure is not None:
            _terminate_process_group(process)
        else:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                failure = f"{label} exceeded timeout of {timeout} seconds"
                _terminate_process_group(process)
    finally:
        selector.close()
        if process.poll() is None:
            _terminate_process_group(process)
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        retain_logs()

    if failure is not None:
        raise EvidenceError(failure)
    stdout_bytes = bytes(output["stdout"])
    stderr_bytes = bytes(output["stderr"])
    if secret:
        stdout_bytes = stdout_bytes.replace(secret, b"<redacted-nvidia-service-key>")
        stderr_bytes = stderr_bytes.replace(secret, b"<redacted-nvidia-service-key>")
    if process.returncode != 0:
        detail_bytes = stderr_bytes.strip() or stdout_bytes.strip() or b"no diagnostic"
        detail = detail_bytes[-2000:].decode("utf-8", errors="replace")
        raise EvidenceError(f"{label} failed ({process.returncode}): {detail}")
    try:
        return stdout_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise EvidenceError(f"{label} stdout is not valid UTF-8") from error


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _values(value: Any, names: set[str]) -> list[Any]:
    normalized = {name.lower() for name in names}
    return [item for key, item in _walk(value) if key.lower() in normalized]


def _parse_json_output(output: str, what: str) -> dict[str, Any]:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise EvidenceError(f"{what} did not emit one JSON document") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"{what} JSON output is not an object")
    return value


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    pieces = token.split(".")
    if len(pieces) != 3:
        raise EvidenceError("MAA token is not a compact JWS")
    try:
        payload = pieces[1] + "=" * (-len(pieces[1]) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("MAA token payload cannot be decoded") from error
    if not isinstance(value, dict):
        raise EvidenceError("MAA token payload is not an object")
    return value


def _extract_maa_token(log: str, expected_issuer: str) -> tuple[str, dict[str, Any]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for match in JWT_RE.finditer(log):
        token = match.group(1)
        try:
            payload = _decode_jwt_payload(token)
        except EvidenceError:
            continue
        if payload.get("iss") == expected_issuer:
            candidates.append((token, payload))
    if len(candidates) != 1:
        raise EvidenceError(f"expected one MAA compact JWS in adapter output, found {len(candidates)}")
    token, payload = candidates[0]
    secure_boot = _values(payload, {"secureboot", "secure-boot"})
    if True not in secure_boot:
        raise EvidenceError("MAA token does not assert secure boot")
    debug_values = _values(payload, {"x-ms-sevsnpvm-is-debuggable"})
    if debug_values and any(value is not False for value in debug_values):
        raise EvidenceError("MAA token permits a debuggable SEV-SNP VM")
    attestation_types = _values(payload, {"x-ms-attestation-type"})
    if not any(value in {"azurevm", "sevsnpvm"} for value in attestation_types):
        raise EvidenceError("MAA token lacks the Azure CVM attestation type")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    if not isinstance(payload.get("nbf"), int) or not isinstance(payload.get("exp"), int):
        raise EvidenceError("MAA token lacks integer nbf/exp claims")
    if not (payload["nbf"] <= now < payload["exp"]):
        raise EvidenceError("MAA token is not currently valid")
    return token, payload


def _require_gpu_state(stage: Path, nvidia_smi: str) -> dict[str, Any]:
    inventory = _run(
        [
            nvidia_smi,
            "--query-gpu=index,name,compute_cap,driver_version,vbios_version",
            "--format=csv,noheader,nounits",
        ],
        directory=stage,
        label="nvidia_inventory",
    )
    rows = [row.strip() for row in inventory.splitlines() if row.strip()]
    if len(rows) != 1:
        raise EvidenceError(f"NCC policy requires exactly one visible GPU, found {len(rows)}")
    fields = [piece.strip() for piece in rows[0].split(",")]
    if len(fields) != 5 or "H100" not in fields[1] or fields[2] != "9.0":
        raise EvidenceError(f"unexpected confidential GPU identity: {rows[0]!r}")
    mode = _run(
        [nvidia_smi, "conf-compute", "-f"],
        directory=stage,
        label="nvidia_cc_mode",
    )
    environment = _run(
        [nvidia_smi, "conf-compute", "-e"],
        directory=stage,
        label="nvidia_cc_environment",
    )
    ready_state = _run(
        [nvidia_smi, "conf-compute", "-q"],
        directory=stage,
        label="nvidia_cc_ready_state",
    )
    if "CC status: ON" not in mode:
        raise EvidenceError("NVIDIA confidential-compute mode is not ON")
    if "CC Environment: PRODUCTION" not in environment:
        raise EvidenceError("NVIDIA confidential-compute environment is not PRODUCTION")
    ready_match = re.search(
        r"^\s*CC GPUs Ready State\s*:\s*([^\r\n]+?)\s*$",
        ready_state,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if ready_match is None or ready_match.group(1).strip().lower() != "ready":
        raise EvidenceError("NVIDIA CC GPUs Ready State is not Ready")
    executable_sha256, _size = sha256_file(Path(nvidia_smi))
    return {
        "inventory": rows[0],
        "driver_version": fields[3],
        "vbios_version": fields[4],
        "cc_mode": "ON",
        "cc_environment": "PRODUCTION",
        "cc_gpus_ready_state": "Ready",
        "nvidia_smi_sha256": executable_sha256,
    }


def _collect_maa(
    stage: Path,
    maa_command: str,
    challenge: str,
    statement_sha256: str,
    binding_nonce: str,
    attestation_url: str,
) -> dict[str, Any]:
    attestation_url, expected_issuer = validate_maa_attestation_url(attestation_url)
    claims = {
        "user-claims": {
            "post-run-binding-nonce": binding_nonce,
            "protocol": "sparkinterval.trusted-compute.result-binding.v1",
            "start-challenge": challenge,
            "statement-sha256": statement_sha256,
        }
    }
    claims_digest = hashlib.sha512(json.dumps(claims).encode("utf-8")).hexdigest()
    config = {
        "api_key": "",
        "attestation_provider": MAA_PROVIDER,
        "attestation_url": attestation_url,
        "claims": claims,
        "enable_metrics": False,
    }
    config_path = stage / "maa_config.json"
    config_path.write_bytes(canonical_json_bytes(config) + b"\n")
    stdout = _run(
        [maa_command, "--c", str(config_path), "--t", "guest", "--s"],
        directory=stage,
        label="maa_guest_attestation",
    )
    stderr = (stage / "maa_guest_attestation.stderr.txt").read_text(encoding="utf-8")
    combined = stdout + "\n" + stderr
    if "Attested Guest Successfully!!" not in combined:
        raise EvidenceError("Azure MAA adapter did not report successful guest attestation")
    if claims_digest.upper() not in combined.upper():
        raise EvidenceError("Azure MAA adapter did not report the expected user-claims digest")
    token, payload = _extract_maa_token(combined, expected_issuer)
    if not isinstance(payload.get("aud"), str) or not payload["aud"]:
        raise EvidenceError("MAA token does not contain one string audience")
    (stage / "maa_token.jwt").write_text(token + "\n", encoding="ascii")
    for required in (stage / "report.bin", stage / "runtime_data.json"):
        if not required.is_file() or required.stat().st_size == 0:
            raise EvidenceError(f"Azure MAA adapter did not retain {required.name}")
    runtime = json.loads((stage / "runtime_data.json").read_text(encoding="utf-8"))
    strings = [str(item).lower() for _key, item in _walk(runtime) if isinstance(item, str)]
    if claims_digest.lower() not in strings:
        raise EvidenceError("MAA runtime data does not contain the expected user-claims digest")
    return {
        "adapter": maa_command,
        "adapter_sha256": sha256_file(Path(maa_command))[0],
        "attestation_url": attestation_url,
        "audience": payload["aud"],
        "claims_sha512": claims_digest,
        "issuer": payload["iss"],
        "jti": payload.get("jti"),
        "provider": MAA_PROVIDER,
        "token_signature_verified_by_collector": False,
    }


def _collect_gpu(
    stage: Path,
    nvattest: str,
    policy: Path,
    binding_nonce: str,
    verifier: str,
    nras_url: str,
) -> dict[str, Any]:
    version_output = _run(
        [nvattest, "version"], directory=stage, label="nvattest_version"
    )
    version = _parse_json_output(version_output, "nvattest version")
    if not isinstance(version.get("nvattest"), str) or not version["nvattest"]:
        raise EvidenceError("nvattest version output lacks a version string")
    evidence_path = stage / "nvidia_gpu_evidence.json"
    collection_output = _run(
        [
            nvattest,
            "--log-level",
            "error",
            "--format",
            "json",
            "collect-evidence",
            "--device",
            "gpu",
            "--nonce",
            binding_nonce,
        ],
        directory=stage,
        label="nvattest_collect",
    )
    collected = _parse_json_output(collection_output, "nvattest collect-evidence")
    if collected.get("result_code") != 0:
        raise EvidenceError(f"nvattest collection result_code={collected.get('result_code')!r}")
    evidences = collected.get("evidences")
    if not isinstance(evidences, list) or len(evidences) != 1:
        raise EvidenceError("nvattest did not collect exactly one GPU evidence record")
    nonces = _values(collected, {"nonce"})
    normalized = [str(value).lower().removeprefix("0x") for value in nonces]
    if binding_nonce not in normalized:
        raise EvidenceError("raw NVIDIA evidence does not contain the expected nonce")
    evidence_path.write_bytes(canonical_json_bytes(collected) + b"\n")

    command = [
        nvattest,
        "--log-level",
        "error",
        "--format",
        "json",
        "attest",
        "--device",
        "gpu",
        "--verifier",
        verifier,
        "--gpu-evidence-source",
        "file",
        "--gpu-evidence-file",
        str(evidence_path),
        "--nonce",
        binding_nonce,
        "--relying-party-policy",
        str(policy),
    ]
    if verifier == "remote":
        if not os.environ.get("NV_ATTESTATION_SERVICE_KEY"):
            raise EvidenceError("remote NVIDIA verification requires NV_ATTESTATION_SERVICE_KEY")
        command.extend(["--nras-url", nras_url])
    attestation_output = _run(
        command,
        directory=stage,
        label="nvattest_attest",
        include_nvidia_service_key=(verifier == "remote"),
    )
    attested = _parse_json_output(attestation_output, "nvattest attest")
    if attested.get("result_code") != 0:
        raise EvidenceError(f"nvattest attestation result_code={attested.get('result_code')!r}")
    claims = attested.get("claims")
    if not isinstance(claims, list) or len(claims) != 1:
        raise EvidenceError("nvattest did not return exactly one GPU claim set")
    if True not in _values(attested, {"secboot"}):
        raise EvidenceError("NVIDIA claims do not assert secure boot")
    if "disabled" not in [str(value).lower() for value in _values(attested, {"dbgstat"})]:
        raise EvidenceError("NVIDIA claims do not assert disabled debug state")
    if True not in _values(
        attested, {"x-nvidia-gpu-attestation-report-nonce-match"}
    ):
        raise EvidenceError("NVIDIA claims do not assert nonce matching")
    detached = attested.get("detached_eat")
    if detached in (None, [], ""):
        raise EvidenceError("nvattest did not retain a detached signed EAT")
    (stage / "nvidia_detached_eat.json").write_bytes(
        canonical_json_bytes(detached) + b"\n"
    )
    (stage / "nvidia_gpu_attestation.json").write_bytes(
        canonical_json_bytes(attested) + b"\n"
    )
    return {
        "nvattest_version": version["nvattest"],
        "nvattest_sha256": sha256_file(Path(nvattest))[0],
        "verifier": verifier,
        "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
        "raw_evidence_nonce_match": True,
        "appraisal_nonce_match": True,
        "detached_eat_present": True,
    }


def _collect_tpm(stage: Path, tools: dict[str, str], binding_nonce: str) -> dict[str, Any]:
    _run(
        [tools["tpm2_pcrreset"], "23"],
        directory=stage,
        label="tpm_pcr23_reset",
    )
    _run(
        [
            tools["tpm2_pcrread"],
            "sha256:23",
            "--pcrs_format",
            "values",
            "-o",
            "pcr23.before.bin",
        ],
        directory=stage,
        label="tpm_pcr23_before",
    )
    before = (stage / "pcr23.before.bin").read_bytes()
    if before != bytes(32):
        raise EvidenceError("PCR23 did not reset to the required all-zero SHA-256 value")
    _run(
        [tools["tpm2_pcrextend"], f"23:sha256={binding_nonce}"],
        directory=stage,
        label="tpm_pcr23_extend",
    )
    _run(
        [
            tools["tpm2_pcrread"],
            "sha256:23",
            "--pcrs_format",
            "values",
            "-o",
            "pcr23.after.bin",
        ],
        directory=stage,
        label="tpm_pcr23_after",
    )
    after = (stage / "pcr23.after.bin").read_bytes()
    expected_after = hashlib.sha256(bytes(32) + bytes.fromhex(binding_nonce)).digest()
    if after != expected_after:
        raise EvidenceError("PCR23 does not equal SHA256(zero-PCR || result binding)")
    _run(
        [tools["tpm2_readpublic"], "-c", "0x81000003", "-f", "pem", "-o", "vtpm_ak.pem"],
        directory=stage,
        label="tpm_read_ak",
    )
    _run(
        [
            tools["tpm2_quote"],
            "-c",
            "0x81000003",
            "-l",
            TPM_PCR_SELECTION,
            "-q",
            binding_nonce,
            "-m",
            "tpm_quote.msg",
            "-s",
            "tpm_quote.sig",
            "-o",
            "tpm_quote.pcrs",
            "-g",
            "sha256",
        ],
        directory=stage,
        label="tpm_quote",
    )
    _run(
        [
            tools["tpm2_checkquote"],
            "-u",
            "vtpm_ak.pem",
            "-m",
            "tpm_quote.msg",
            "-s",
            "tpm_quote.sig",
            "-f",
            "tpm_quote.pcrs",
            "-g",
            "sha256",
            "-q",
            binding_nonce,
        ],
        directory=stage,
        label="tpm_checkquote",
    )
    for index, output in (
        ("0x01C101D0", "vtpm_ak_cert.bin"),
        ("0x01400001", "azure_hcl_report.bin"),
        ("0x01400002", "azure_hcl_runtime_data.bin"),
    ):
        _run(
            [tools["tpm2_nvread"], "-C", "o", index, "-o", output],
            directory=stage,
            label=f"tpm_nvread_{index.lower()}",
        )
        if not (stage / output).is_file() or (stage / output).stat().st_size == 0:
            raise EvidenceError(f"TPM NV index {index} produced no {output}")
    event_log = Path("/sys/kernel/security/tpm0/binary_bios_measurements")
    if not event_log.is_file():
        raise EvidenceError("kernel did not expose the TCG event log required for appraisal")
    shutil.copyfile(event_log, stage / "tcg_event_log.bin")
    quote_evidence = {
        "ak_certificate_sha256": sha256_file(stage / "vtpm_ak_cert.bin")[0],
        "ak_public_sha256": sha256_file(stage / "vtpm_ak.pem")[0],
        "event_log_sha256": sha256_file(stage / "tcg_event_log.bin")[0],
        "kind": "gpu_prover_vtpm_quote_evidence",
        "pcr_selection": TPM_PCR_SELECTION,
        "pcr23_after_sha256": sha256_file(stage / "pcr23.after.bin")[0],
        "pcr23_after_value_hex": after.hex(),
        "pcr23_before_sha256": sha256_file(stage / "pcr23.before.bin")[0],
        "pcr23_before_value_hex": before.hex(),
        "pcrs_sha256": sha256_file(stage / "tpm_quote.pcrs")[0],
        "qualifying_data_sha256": binding_nonce,
        "quote_message_sha256": sha256_file(stage / "tpm_quote.msg")[0],
        "quote_signature_sha256": sha256_file(stage / "tpm_quote.sig")[0],
        "schema_version": 1,
    }
    quote_path = stage / "tpm_quote_evidence.json"
    quote_path.write_bytes(canonical_json_bytes(quote_evidence) + b"\n")
    return {
        "ak_handle": "0x81000003",
        "pcr_selection": TPM_PCR_SELECTION,
        "pcr23_extended_with": binding_nonce,
        "pcr23_expected_after_hex": expected_after.hex(),
        "pcr23_initial_value_hex": before.hex(),
        "quote_qualifying_data": binding_nonce,
        "local_checkquote_passed": True,
        "azure_ak_chain_verified_by_collector": False,
        "quote_evidence_sha256": sha256_file(quote_path)[0],
        "tool_sha256": {
            name: sha256_file(Path(executable))[0]
            for name, executable in sorted(tools.items())
        },
    }


def _artifact_inventory(stage: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(stage.iterdir()):
        if path.is_file() and path.name != "evidence-manifest.json":
            digest, size = sha256_file(path)
            records.append({"path": path.name, "sha256": digest, "size_bytes": size})
    return records


def _dry_run_plan(args: argparse.Namespace, challenge: dict[str, Any], binding: str) -> dict[str, Any]:
    stage = "<new-evidence-staging-directory>"
    command_templates = {
        "maa_guest_attestation": [
            str(args.maa_command),
            "--c",
            f"{stage}/maa_config.json",
            "--t",
            "guest",
            "--s",
        ],
        "tpm_quote": [
            "tpm2_quote",
            "-c",
            "0x81000003",
            "-l",
            TPM_PCR_SELECTION,
            "-q",
            binding,
            "-m",
            "tpm_quote.msg",
            "-s",
            "tpm_quote.sig",
            "-o",
            "tpm_quote.pcrs",
            "-g",
            "sha256",
        ],
    }
    if args.backend == "azure_ncc40ads_h100_v5":
        command_templates["nvidia_collect"] = [
            str(args.nvattest),
            "--log-level",
            "error",
            "--format",
            "json",
            "collect-evidence",
            "--device",
            "gpu",
            "--nonce",
            binding,
        ]
    return {
        "accepted": False,
        "classification": "legacy_post_run_reset_diagnostic_dry_run",
        "certificate_admissible": False,
        "evidence_collected": False,
        "challenge_nonce": challenge["nonce"],
        "challenge_expires_at_utc": challenge["expires_at_utc"],
        "backend": args.backend,
        "maa_attestation_url": args.maa_attestation_url,
        "statement_sha256": args.statement_sha256,
        "binding_nonce": binding,
        "required_commands": [
            str(args.maa_command),
            "tpm2_pcrread",
            "tpm2_pcrreset",
            "tpm2_pcrextend",
            "tpm2_quote",
            "tpm2_checkquote",
            "tpm2_readpublic",
            "tpm2_nvread",
        ]
        + (
            [str(args.nvattest), str(args.nvidia_smi)]
            if args.backend == "azure_ncc40ads_h100_v5"
            else []
        ),
        "command_templates": command_templates,
        "tpm_pcr_selection": TPM_PCR_SELECTION,
        "nvidia_verifier": args.gpu_verifier,
        "output_dir": str(args.output_dir),
        "mathematical_result_proven": False,
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    challenge = load_challenge(args.challenge)
    binding = derive_binding_nonce(challenge["nonce"], args.statement_sha256)
    validate_maa_attestation_url(args.maa_attestation_url)
    if args.statement_file is not None:
        verify_statement_file(
            args.statement_file, args.statement_sha256, challenge["nonce"]
        )
    if args.dry_run:
        return _dry_run_plan(args, challenge, binding)
    if os.geteuid() != 0:
        raise EvidenceError("evidence collection must run as root for TPM/GPU device access")
    if args.output_dir.exists():
        raise EvidenceError(f"output directory already exists: {args.output_dir}")
    is_h100 = args.backend == "azure_ncc40ads_h100_v5"
    if is_h100 and not args.policy.is_file():
        raise EvidenceError(f"NVIDIA relying-party policy is absent: {args.policy}")
    executables = {
        name: _which(name)
        for name in (
            "tpm2_pcrread",
            "tpm2_pcrreset",
            "tpm2_pcrextend",
            "tpm2_quote",
            "tpm2_checkquote",
            "tpm2_readpublic",
            "tpm2_nvread",
        )
    }
    maa_command = _which(args.maa_command)
    nvattest = _which(args.nvattest) if is_h100 else None
    nvidia_smi = _which(args.nvidia_smi) if is_h100 else None
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{args.output_dir.name}.collecting-", dir=args.output_dir.parent)
    )
    os.chmod(stage, 0o700)
    try:
        gpu_state = _require_gpu_state(stage, nvidia_smi) if nvidia_smi else None
        maa = _collect_maa(
            stage,
            maa_command,
            challenge["nonce"],
            args.statement_sha256,
            binding,
            args.maa_attestation_url,
        )
        gpu = (
            _collect_gpu(
                stage,
                nvattest,
                args.policy,
                binding,
                args.gpu_verifier,
                args.nras_url,
            )
            if nvattest
            else None
        )
        tpm = _collect_tpm(stage, executables, binding)
        # Collection can involve network appraisals. Refuse to publish a pack
        # if the externally issued challenge expired during that work.
        require_current_challenge_window(challenge)
        manifest = {
            "artifacts": _artifact_inventory(stage),
            "binding": {
                "protocol": "sparkinterval.trusted-compute.result-binding.v1",
                "post_run_binding_nonce": binding,
                "start_challenge": challenge["nonce"],
                "statement_sha256": args.statement_sha256,
            },
            "challenge": challenge,
            "backend": args.backend,
            "collection_time_utc": dt.datetime.now(dt.timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "gpu": gpu,
            "gpu_state": gpu_state,
            "kind": KIND,
            "maa": maa,
            "schema_version": SCHEMA_VERSION,
            "status": "evidence_collected_pending_independent_verification",
            "tpm": tpm,
            "trust_boundary": {
                "algorithm_execution_proven_by_collector": False,
                "maa_jws_signature_verified_by_collector": False,
                "nvidia_eat_retained": is_h100,
                "signed_acceptance_certificate_issued": False,
            },
        }
        (stage / "evidence-manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")
        os.replace(stage, args.output_dir)
        return {
            "accepted": False,
            "classification": "legacy_post_run_reset_evidence_diagnostic_only",
            "backend": args.backend,
            "output_dir": str(args.output_dir),
            "binding_nonce": binding,
            "evidence_collected": True,
            "signed_acceptance_certificate_issued": False,
            "certificate_admissible": False,
        }
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--statement-sha256", required=True)
    parser.add_argument("--statement-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maa-command", type=Path, default=DEFAULT_MAA_COMMAND)
    parser.add_argument(
        "--maa-attestation-url",
        required=True,
        help=(
            "exact custom MAA HTTPS endpoint ending in "
            f"{MAA_SEVSNP_PATH}?api-version={MAA_API_VERSION}"
        ),
    )
    parser.add_argument("--nvattest", default="nvattest")
    parser.add_argument("--nvidia-smi", default="nvidia-smi")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--gpu-verifier", choices=("local", "remote"), default="local")
    parser.add_argument(
        "--nras-url", default="https://nras.attestation.nvidia.com"
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = collect(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (EvidenceError, OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "azure_ncc_evidence_collection_failed_closed",
                    "error": str(error),
                    "evidence_collected": False,
                    "signed_acceptance_certificate_issued": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

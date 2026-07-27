#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
"""Cross-check and test-vector harness for SparkInterval/Certificate/P256.lean.

This script does three things and is not a pytest module:

1. ``crosscheck``  -- re-derives the P-256 domain parameters from independent
   sources (OpenSSL's explicit encoding of ``prime256v1``, the closed form of
   the prime, the ANSI X9.62 / FIPS 186-4 SEED derivation of ``b``, and
   agreement with OpenSSL key generation) and prints each check.
2. ``vectors``     -- builds a JSON vector file combining the official NIST
   CAVP ``SigVer`` P-256/SHA-256 vectors with a locally generated set of
   positive and negative cases.
3. ``emit-lean``   -- writes a Lean file that runs every vector through the
   Lean verifier and prints a pass/fail summary.

The NIST vectors are read from an unpacked copy of
``186-3ecdsatestvectors.zip`` (the CAVP ECDSA archive, which contains the
FIPS 186-4 vectors) obtained from
https://csrc.nist.gov/Projects/cryptographic-algorithm-validation-program.

Nothing here is part of the Lean trust surface; it is a development and audit
aid only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import secrets
import subprocess
import sys

# --------------------------------------------------------------------------
# Independent sourcing of the domain parameters
# --------------------------------------------------------------------------


def openssl_parameters() -> dict:
    """Read the P-256 parameters out of OpenSSL's explicit-parameter dump."""
    text = subprocess.run(
        ["openssl", "ecparam", "-name", "prime256v1", "-param_enc", "explicit",
         "-text", "-noout"],
        capture_output=True, text=True, check=True).stdout

    def field(label: str) -> int:
        lines = text.splitlines()
        start = next(index for index, line in enumerate(lines)
                     if line.strip().rstrip(":").strip() == label)
        chunks = []
        for line in lines[start + 1:]:
            if re.fullmatch(r"\s+([0-9a-f]{2}:)*[0-9a-f]{2}:?\s*", line):
                chunks.append(line.strip())
            else:
                break
        return int("".join(chunks).replace(":", ""), 16)

    generator = format(field("Generator (uncompressed)"), "x")
    generator = generator.zfill(130)
    assert generator[:2] == "04", generator[:2]
    return {
        "p": field("Prime"),
        "a": field("A"),
        "b": field("B"),
        "n": field("Order"),
        "gx": int(generator[2:66], 16),
        "gy": int(generator[66:], 16),
        "seed": format(field("Seed"), "x").zfill(40),
    }


def seed_derived_c(seed_hex: str) -> int:
    """ANSI X9.62 A.3.3.1 / FIPS 186-4 curve-generation value ``c``.

    With ``t = 256`` this is ``s = 1`` and ``h = 96``: take the rightmost 96
    bits of ``SHA-1(SEED)`` with the leftmost bit of that 96-bit string
    cleared, then append ``SHA-1(SEED + 1)``.  The curve coefficient ``b``
    must satisfy ``b^2 * c = -27 (mod p)``.
    """
    seed = int(seed_hex, 16)
    t, s = 256, (256 - 1) // 160
    h = t - 160 * s
    word = int(hashlib.sha1(bytes.fromhex(seed_hex)).hexdigest(), 16)
    word &= (1 << h) - 1
    word &= ~(1 << (h - 1))
    for index in range(1, s + 1):
        following = ((seed + index) % (1 << 160)).to_bytes(20, "big")
        word = (word << 160) | int(hashlib.sha1(following).hexdigest(), 16)
    return word


# --------------------------------------------------------------------------
# Reference arithmetic mirroring the Lean implementation exactly
# --------------------------------------------------------------------------


class Reference:
    """Jacobian-coordinate reference, algorithm-identical to the Lean code."""

    def __init__(self, params: dict):
        self.p = params["p"]
        self.a = params["a"]
        self.b = params["b"]
        self.n = params["n"]
        self.G = (params["gx"], params["gy"], 1)

    def add_f(self, x, y): return (x + y) % self.p
    def sub_f(self, x, y): return (x + (self.p - y % self.p)) % self.p
    def mul_f(self, x, y): return (x * y) % self.p
    def sqr_f(self, x): return (x * x) % self.p

    @staticmethod
    def bits(value, width):
        return [(value >> (width - 1 - i)) & 1 == 1 for i in range(width)]

    def pow_mod(self, modulus, base, exponent, width=256):
        if modulus == 0:
            return 0
        reduced, accumulator = base % modulus, 1 % modulus
        for bit in self.bits(exponent, width):
            accumulator = accumulator * accumulator % modulus
            if bit:
                accumulator = accumulator * reduced % modulus
        return accumulator

    def inv_f(self, x): return self.pow_mod(self.p, x, self.p - 2)
    def inv_n(self, x): return self.pow_mod(self.n, x, self.n - 2)

    INF = (1, 1, 0)

    def double(self, point):
        X, Y, Z = point
        delta, gamma = self.sqr_f(Z), self.sqr_f(Y)
        beta = self.mul_f(X, gamma)
        alpha = self.mul_f(3, self.mul_f(self.sub_f(X, delta),
                                         self.add_f(X, delta)))
        x3 = self.sub_f(self.sqr_f(alpha), self.mul_f(8, beta))
        z3 = self.sub_f(self.sub_f(self.sqr_f(self.add_f(Y, Z)), gamma), delta)
        y3 = self.sub_f(self.mul_f(alpha, self.sub_f(self.mul_f(4, beta), x3)),
                        self.mul_f(8, self.sqr_f(gamma)))
        return (x3, y3, z3)

    def add(self, left, right):
        if left[2] == 0:
            return right
        if right[2] == 0:
            return left
        X1, Y1, Z1 = left
        X2, Y2, Z2 = right
        z1z1, z2z2 = self.sqr_f(Z1), self.sqr_f(Z2)
        u1, u2 = self.mul_f(X1, z2z2), self.mul_f(X2, z1z1)
        s1 = self.mul_f(self.mul_f(Y1, Z2), z2z2)
        s2 = self.mul_f(self.mul_f(Y2, Z1), z1z1)
        if u1 == u2:
            return self.double(left) if s1 == s2 else self.INF
        h = self.sub_f(u2, u1)
        i = self.sqr_f(self.mul_f(2, h))
        j = self.mul_f(h, i)
        r = self.mul_f(2, self.sub_f(s2, s1))
        v = self.mul_f(u1, i)
        x3 = self.sub_f(self.sub_f(self.sqr_f(r), j), self.mul_f(2, v))
        y3 = self.sub_f(self.mul_f(r, self.sub_f(v, x3)),
                        self.mul_f(2, self.mul_f(s1, j)))
        z3 = self.mul_f(
            self.sub_f(self.sub_f(self.sqr_f(self.add_f(Z1, Z2)), z1z1), z2z2),
            h)
        return (x3, y3, z3)

    def scalar_mul(self, scalar, point):
        accumulator = self.INF
        for bit in self.bits(scalar, 256):
            accumulator = self.double(accumulator)
            if bit:
                accumulator = self.add(accumulator, point)
        return accumulator

    def to_affine(self, point):
        if point[2] == 0:
            return None
        z_inv = self.inv_f(point[2])
        z_inv2 = self.sqr_f(z_inv)
        return (self.mul_f(point[0], z_inv2),
                self.mul_f(point[1], self.mul_f(z_inv2, z_inv)))

    def on_curve(self, x, y):
        if not (x < self.p and y < self.p):
            return False
        right = self.add_f(self.add_f(self.mul_f(x, self.sqr_f(x)),
                                      self.mul_f(self.a, x)), self.b)
        return self.sqr_f(y) == right

    def verify(self, qx, qy, e, r, s):
        if not self.on_curve(qx, qy):
            return False
        if not (1 <= r <= self.n - 1 and 1 <= s <= self.n - 1):
            return False
        w = self.inv_n(s)
        u1 = (e % self.n) * w % self.n
        u2 = r * w % self.n
        combined = self.add(self.scalar_mul(u1, self.G),
                            self.scalar_mul(u2, (qx, qy, 1)))
        affine = self.to_affine(combined)
        return affine is not None and affine[0] % self.n == r

    # A second, deliberately different affine implementation, used only to
    # cross-check the Jacobian formulas.
    def affine_mul(self, k, point):
        def affine_add(P, Q):
            if P is None:
                return Q
            if Q is None:
                return P
            (x1, y1), (x2, y2) = P, Q
            if x1 == x2 and (y1 + y2) % self.p == 0:
                return None
            if P == Q:
                lam = (3 * x1 * x1 + self.a) * pow(2 * y1, -1, self.p) % self.p
            else:
                lam = (y2 - y1) * pow((x2 - x1) % self.p, -1, self.p) % self.p
            x3 = (lam * lam - x1 - x2) % self.p
            return (x3, (lam * (x1 - x3) - y1) % self.p)

        result = None
        for bit in bin(k)[2:]:
            result = affine_add(result, result)
            if bit == "1":
                result = affine_add(result, point)
        return result


def run_crosscheck() -> dict:
    params = openssl_parameters()
    print("source: openssl ecparam -name prime256v1 -param_enc explicit")
    for key in ("p", "a", "b", "n", "gx", "gy"):
        print(f"  {key:3s} = 0x{params[key]:064x}")
    print(f"  seed = {params['seed']}")

    closed_form = 2 ** 256 - 2 ** 224 + 2 ** 192 + 2 ** 96 - 1
    checks = []
    checks.append(("p == 2^256-2^224+2^192+2^96-1", params["p"] == closed_form))
    checks.append(("a == p - 3", params["a"] == params["p"] - 3))
    checks.append(("b^2*c == -27 mod p from NIST SEED (X9.62 A.3.3.1)",
                   params["b"] ** 2 * seed_derived_c(params["seed"]) % params["p"]
                   == (-27) % params["p"]))
    checks.append(("|n - (p+1)| <= 2*sqrt(p)  (Hasse, cofactor 1)",
                   abs(params["n"] - (params["p"] + 1))
                   <= 2 * math.isqrt(params["p"])))

    reference = Reference(params)
    G_affine = (params["gx"], params["gy"])
    checks.append(("G satisfies the curve equation",
                   reference.on_curve(*G_affine)))
    checks.append(("n*G is the point at infinity",
                   reference.scalar_mul(params["n"], reference.G)[2] == 0))
    checks.append(("(n-1)*G == -G",
                   reference.to_affine(
                       reference.scalar_mul(params["n"] - 1, reference.G))
                   == (params["gx"], (params["p"] - params["gy"]) % params["p"])))

    random.seed(11)
    agree = True
    for _ in range(25):
        k = random.randrange(1, params["n"])
        agree &= (reference.to_affine(reference.scalar_mul(k, reference.G))
                  == reference.affine_mul(k, G_affine))
    checks.append(("25 random k: Jacobian ladder == affine reference", agree))

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        agree = True
        for _ in range(20):
            key = ec.generate_private_key(ec.SECP256R1())
            d = key.private_numbers().private_value
            public = key.public_key().public_numbers()
            agree &= (reference.to_affine(reference.scalar_mul(d, reference.G))
                      == (public.x, public.y))
        checks.append(("20 OpenSSL keypairs: d*G == Q", agree))
    except ImportError:
        checks.append(("python `cryptography` available", False))

    print()
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not all(ok for _, ok in checks):
        sys.exit(1)
    return params


# --------------------------------------------------------------------------
# Test vectors
# --------------------------------------------------------------------------


def nist_vectors(rsp_path: str) -> list:
    text = open(rsp_path).read()
    section = text.split("[P-256,SHA-256]")[1].split("[P-256,SHA-384]")[0]
    records, current = [], {}
    for line in section.splitlines():
        line = line.strip()
        if "=" in line:
            key, value = [part.strip() for part in line.split("=", 1)]
            current[key] = value
            if key == "Result":
                records.append(current)
                current = {}
    out = []
    for index, record in enumerate(records):
        digest = hashlib.sha256(bytes.fromhex(record["Msg"])).hexdigest()
        out.append({
            "name": f"nist-cavp/{index} [{record['Result']}]",
            "pub": "04" + record["Qx"].zfill(64) + record["Qy"].zfill(64),
            "dig": digest,
            "sig": record["R"].zfill(64) + record["S"].zfill(64),
            "expect": record["Result"].startswith("P"),
        })
    return out


def build_vectors(params: dict, rsp_path: str) -> list:
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives import hashes

    n, p = params["n"], params["p"]
    hex64 = lambda value: format(value, "064x")
    random.seed(20260726)
    vectors = []

    material = []
    for index in range(100):
        key = ec.generate_private_key(ec.SECP256R1())
        message = secrets.token_bytes(random.randrange(0, 200))
        der = key.sign(message, ec.ECDSA(hashes.SHA256()))
        key.public_key().verify(der, message, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der)
        numbers = key.public_key().public_numbers()
        public = "04" + hex64(numbers.x) + hex64(numbers.y)
        digest = hashlib.sha256(message).hexdigest()
        material.append((public, digest, r, s))
        vectors.append({"name": f"valid/{index}", "pub": public,
                        "dig": digest, "sig": hex64(r) + hex64(s),
                        "expect": True})

    # Documented malleability: (r, n - s) verifies exactly when (r, s) does.
    for index, (public, digest, r, s) in enumerate(material[:10]):
        vectors.append({"name": f"malleable-negated-s/{index}", "pub": public,
                        "dig": digest, "sig": hex64(r) + hex64(n - s),
                        "expect": True})

    def negative(name, public, digest, signature):
        vectors.append({"name": name, "pub": public, "dig": digest,
                        "sig": signature, "expect": False})

    for index, (public, digest, r, s) in enumerate(material[:20]):
        other = material[(index + 1) % 20][0]
        wrong = hashlib.sha256(f"different-{index}".encode()).hexdigest()
        negative(f"wrong-digest/{index}", public, wrong, hex64(r) + hex64(s))
        negative(f"tampered-r/{index}", public, digest,
                 hex64((r + 1) % n) + hex64(s))
        negative(f"tampered-s/{index}", public, digest,
                 hex64(r) + hex64((s + 1) % n))
        negative(f"r-zero/{index}", public, digest, hex64(0) + hex64(s))
        negative(f"s-zero/{index}", public, digest, hex64(r) + hex64(0))
        negative(f"s-equals-n/{index}", public, digest, hex64(r) + hex64(n))
        negative(f"s-above-n/{index}", public, digest, hex64(r) + hex64(n + 1))
        negative(f"r-equals-n/{index}", public, digest, hex64(n) + hex64(s))
        negative(f"r-s-swapped/{index}", public, digest, hex64(s) + hex64(r))
        negative(f"wrong-key/{index}", other, digest, hex64(r) + hex64(s))

    for index, (public, digest, r, s) in enumerate(material[:10]):
        qx, qy = int(public[2:66], 16), int(public[66:], 16)
        signature = hex64(r) + hex64(s)
        negative(f"pubkey-off-curve-y/{index}",
                 "04" + hex64(qx) + hex64((qy + 1) % p), digest, signature)
        negative(f"pubkey-off-curve-x/{index}",
                 "04" + hex64((qx + 1) % p) + hex64(qy), digest, signature)

    public, digest, r, s = material[0]
    signature = hex64(r) + hex64(s)
    generator = "04" + hex64(params["gx"]) + hex64(params["gy"])
    negative("pubkey-affine-zero", "04" + hex64(0) + hex64(0), digest, signature)
    negative("pubkey-sec1-infinity-byte", "00", digest, signature)
    negative("pubkey-compressed-02", "02" + public[2:66], digest, signature)
    negative("pubkey-compressed-03", "03" + public[2:66], digest, signature)
    negative("pubkey-bad-tag-05", "05" + public[2:], digest, signature)
    negative("pubkey-uppercase", public.upper(), digest, signature)
    negative("pubkey-short", public[:-2], digest, signature)
    negative("pubkey-long", public + "00", digest, signature)
    negative("pubkey-nonhex", public[:-1] + "z", digest, signature)
    negative("pubkey-empty", "", digest, signature)
    negative("pubkey-is-generator", generator, digest, signature)
    negative("digest-short", public, digest[:-2], signature)
    negative("digest-long", public, digest + "00", signature)
    negative("digest-uppercase", public, digest.upper(), signature)
    negative("digest-nonhex", public, digest[:-1] + "g", signature)
    negative("digest-empty", public, "", signature)
    negative("sig-short", public, digest, signature[:-2])
    negative("sig-long", public, digest, signature + "00")
    negative("sig-uppercase", public, digest, signature.upper())
    negative("sig-nonhex", public, digest, signature[:-1] + "x")
    negative("sig-empty", public, digest, "")
    negative("sig-all-zero", public, digest, hex64(0) + hex64(0))
    negative("sig-all-ff", public, digest, "f" * 128)

    vectors.extend(nist_vectors(rsp_path))

    # Every vector's expected result is confirmed by the independent Python
    # reference before it is handed to Lean, except for the malformed-input
    # cases, whose expectation is a property of the Lean parser alone.
    reference = Reference(params)
    for vector in vectors:
        if (len(vector["pub"]) == 130 and len(vector["dig"]) == 64
                and len(vector["sig"]) == 128
                and re.fullmatch("[0-9a-f]*", vector["pub"] + vector["dig"]
                                 + vector["sig"])
                and vector["pub"][:2] == "04"):
            got = reference.verify(int(vector["pub"][2:66], 16),
                                   int(vector["pub"][66:], 16),
                                   int(vector["dig"], 16),
                                   int(vector["sig"][:64], 16),
                                   int(vector["sig"][64:], 16))
            assert got == vector["expect"], vector["name"]
    return vectors


def curated_vectors(params: dict, rsp_path: str) -> list:
    """A small, fully deterministic vector set for the in-repo regression test.

    It is the complete official CAVP P-256/SHA-256 ``SigVer`` set plus tamper,
    range, public-key-validity, and malformed-encoding cases derived from the
    first passing CAVP vector.  No random material is used, so the emitted Lean
    file is byte-reproducible.
    """
    n, p = params["n"], params["p"]
    hex64 = lambda value: format(value, "064x")
    vectors = [dict(vector) for vector in nist_vectors(rsp_path)]
    base = next(vector for vector in vectors if vector["expect"])
    public, digest, signature = base["pub"], base["dig"], base["sig"]
    r, s = int(signature[:64], 16), int(signature[64:], 16)
    qx, qy = int(public[2:66], 16), int(public[66:], 16)

    def add(name, pub, dig, sig, expect):
        vectors.append({"name": name, "pub": pub, "dig": dig, "sig": sig,
                        "expect": expect})

    add("malleable-negated-s", public, digest, hex64(r) + hex64(n - s), True)
    add("tampered-r", public, digest, hex64((r + 1) % n) + hex64(s), False)
    add("tampered-s", public, digest, hex64(r) + hex64((s + 1) % n), False)
    add("r-zero", public, digest, hex64(0) + hex64(s), False)
    add("s-zero", public, digest, hex64(r) + hex64(0), False)
    add("r-equals-n", public, digest, hex64(n) + hex64(s), False)
    add("s-equals-n", public, digest, hex64(r) + hex64(n), False)
    add("s-above-n", public, digest, hex64(r) + hex64(n + 1), False)
    add("r-s-swapped", public, digest, hex64(s) + hex64(r), False)
    add("wrong-digest", public,
        hashlib.sha256(b"not the signed message").hexdigest(), signature, False)
    add("pubkey-off-curve-y", "04" + hex64(qx) + hex64((qy + 1) % p), digest,
        signature, False)
    add("pubkey-off-curve-x", "04" + hex64((qx + 1) % p) + hex64(qy), digest,
        signature, False)
    add("pubkey-affine-zero", "04" + hex64(0) + hex64(0), digest, signature,
        False)
    add("pubkey-sec1-infinity-byte", "00", digest, signature, False)
    add("pubkey-compressed-02", "02" + public[2:66], digest, signature, False)
    add("pubkey-compressed-03", "03" + public[2:66], digest, signature, False)
    add("pubkey-bad-tag-05", "05" + public[2:], digest, signature, False)
    add("pubkey-uppercase", public.upper(), digest, signature, False)
    add("pubkey-short", public[:-2], digest, signature, False)
    add("pubkey-long", public + "00", digest, signature, False)
    add("pubkey-nonhex", public[:-1] + "z", digest, signature, False)
    add("pubkey-empty", "", digest, signature, False)
    add("pubkey-is-generator",
        "04" + hex64(params["gx"]) + hex64(params["gy"]), digest, signature,
        False)
    add("digest-short", public, digest[:-2], signature, False)
    add("digest-long", public, digest + "00", signature, False)
    add("digest-uppercase", public, digest.upper(), signature, False)
    add("digest-nonhex", public, digest[:-1] + "g", signature, False)
    add("digest-empty", public, "", signature, False)
    add("sig-short", public, digest, signature[:-2], False)
    add("sig-long", public, digest, signature + "00", False)
    add("sig-uppercase", public, digest, signature.upper(), False)
    add("sig-nonhex", public, digest, signature[:-1] + "x", False)
    add("sig-empty", public, digest, "", False)
    add("sig-all-zero", public, digest, hex64(0) + hex64(0), False)
    add("sig-all-ff", public, digest, "f" * 128, False)

    reference = Reference(params)
    for vector in vectors:
        if (len(vector["pub"]) == 130 and vector["pub"][:2] == "04"
                and len(vector["dig"]) == 64 and len(vector["sig"]) == 128
                and re.fullmatch("[0-9a-f]*",
                                 vector["pub"] + vector["dig"] + vector["sig"])):
            got = reference.verify(int(vector["pub"][2:66], 16),
                                   int(vector["pub"][66:], 16),
                                   int(vector["dig"], 16),
                                   int(vector["sig"][:64], 16),
                                   int(vector["sig"][64:], 16))
            assert got == vector["expect"], vector["name"]
    return vectors


LEAN_TEMPLATE = """/- Generated by tests/p256_vector_harness.py.  Do not edit. -/
import SparkInterval.Certificate.P256

set_option maxRecDepth 100000

open SparkInterval.Certificate.P256

/-- name, public key, digest, signature, expected result. -/
def vectors : List (String × String × String × String × Bool) :=
[
{rows}
]

def failures : List String :=
  vectors.filterMap fun (name, publicKey, digest, signature, expected) =>
    if verifyDigestHex publicKey digest signature == expected then none
    else some name

def summary : String :=
  let positive := (vectors.filter (fun v => v.2.2.2.2)).length
  let negative := vectors.length - positive
  s!"vectors={vectors.length} positive={positive} negative={negative} \
failures={failures.length} parametersSelfCheck={parametersSelfCheck}"

#eval summary
#eval failures
"""


REPO_TEST_TEMPLATE = """/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.P256

/-!
# Regression vectors for the P-256 ECDSA verifier

This file is generated by `tests/p256_vector_harness.py emit-repo-test` and
should not be edited by hand.  It contains the complete official NIST CAVP
`SigVer` vector set for P-256 with SHA-256, together with tamper, range,
public-key-validity, and malformed-encoding cases derived deterministically
from the first passing CAVP vector.

`#guard` evaluates each check with the compiled evaluator at elaboration time.
It introduces no axiom and no proof term, so this file does not use
`native_decide` and does not enlarge any trust surface.  A regression makes the
file fail to elaborate.

A larger randomized vector set (hundreds of cases, generated with Python's
`cryptography`) is not checked in; regenerate it with
`tests/p256_vector_harness.py all`.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Tests.P256

open SparkInterval.Certificate.P256

/-- Name, uncompressed public point, SHA-256 digest, `r || s`, expected
result. -/
def vectors : List (String × String × String × String × Bool) :=
[
{rows}
]

/-- Names of vectors whose verification result differs from the expectation. -/
def failures : List String :=
  vectors.filterMap fun (name, publicKey, digest, signature, expected) =>
    if verifyDigestHex publicKey digest signature == expected then none
    else some name

/-- Vectors that must verify. -/
def positiveCount : Nat := (vectors.filter fun vector => vector.2.2.2.2).length

/-- Vectors that must be rejected. -/
def negativeCount : Nat := vectors.length - positiveCount

-- The published domain parameters agree with this file's own arithmetic:
-- the base point is on the curve, the group order annihilates it, and the
-- scalar ladder round-trips.
#guard parametersSelfCheck

-- Vector-set shape, so a truncated regeneration cannot silently weaken the
-- test.  In particular the negative count is asserted, because a verifier
-- that accepts everything would still pass a positive-only suite.
#guard vectors.length == {total}
#guard positiveCount == {positive}
#guard negativeCount == {negative}

-- Every vector agrees with its expected result.
#guard failures.isEmpty

/-! ## Exceptional branches of the point arithmetic

Signature vectors exercise the generic addition and doubling paths heavily but
almost never reach the exceptional branches, so those are checked directly.
Re-affinizing a point (`reAffine`) gives a second representative of the same
curve point with a different `Z`, which is what forces `add` to take its
`u1 = u2` branches with genuinely distinct Jacobian coordinates. -/

/-- The canonical `Z = 1` representative of a point, or infinity. -/
def reAffine (point : Jacobian) : Jacobian :=
  match point.toAffine with
  | none => Jacobian.infinity
  | some (x, y) => Jacobian.ofAffine x y

/-- `-G`, as an affine point. -/
def negatedBase : Jacobian := Jacobian.ofAffine baseX (fieldSub 0 baseY)

-- Identity element, in both argument positions, and doubling of infinity.
#guard (Jacobian.infinity.add basePoint).toAffine == some (baseX, baseY)
#guard (basePoint.add Jacobian.infinity).toAffine == some (baseX, baseY)
#guard Jacobian.infinity.double.isInfinity
#guard Jacobian.infinity.add Jacobian.infinity |>.isInfinity
#guard (Jacobian.scalarMul 0 basePoint).isInfinity

-- Opposite points sum to infinity, with matching and with differing `Z`.
#guard (basePoint.add negatedBase).isInfinity
#guard ((Jacobian.scalarMul 2 basePoint).add
  (reAffine (Jacobian.scalarMul 2 negatedBase))).isInfinity

-- Equal points take the doubling fallback, with matching and differing `Z`.
#guard (basePoint.add basePoint).toAffine ==
  (Jacobian.scalarMul 2 basePoint).toAffine
#guard ((Jacobian.scalarMul 2 basePoint).add
  (reAffine (Jacobian.scalarMul 2 basePoint))).toAffine ==
    (Jacobian.scalarMul 4 basePoint).toAffine

-- The generic addition agrees with the ladder on mixed representations.
#guard ((Jacobian.scalarMul 2 basePoint).add
  (Jacobian.scalarMul 3 basePoint)).toAffine ==
    (Jacobian.scalarMul 5 basePoint).toAffine
#guard ((basePoint.double.double).add basePoint).toAffine ==
  (Jacobian.scalarMul 5 basePoint).toAffine
#guard (Jacobian.scalarMul (groupOrder + 1) basePoint).isInfinity == false

-- Every point produced by the ladder is on the curve.
#guard (List.range 12).all fun index =>
  match (Jacobian.scalarMul (index + 1) basePoint).toAffine with
  | none => false
  | some (x, y) => isOnCurve x y

-- Fermat inversion in both fields.
#guard fieldMul 7 (fieldInverse 7) == 1
#guard fieldMul (fieldPrime - 1) (fieldInverse (fieldPrime - 1)) == 1
#guard 5 * scalarInverse 5 % groupOrder == 1
#guard (groupOrder - 1) * scalarInverse (groupOrder - 1) % groupOrder == 1

-- The low-`s` predicate, which this module defines but does not enforce.
#guard isLowS 1
#guard isLowS (groupOrder - 1) == false

end SparkInterval.Tests.P256
"""


def _rows(vectors: list) -> str:
    return ",\n".join(
        f'  ("{v["name"]}", "{v["pub"]}", "{v["dig"]}", "{v["sig"]}", '
        f'{"true" if v["expect"] else "false"})' for v in vectors)


def emit_lean(vectors: list, path: str) -> None:
    open(path, "w").write(LEAN_TEMPLATE.replace("{rows}", _rows(vectors)))


def emit_repo_test(vectors: list, path: str) -> None:
    positive = sum(1 for vector in vectors if vector["expect"])
    text = (REPO_TEST_TEMPLATE
            .replace("{rows}", _rows(vectors))
            .replace("{total}", str(len(vectors)))
            .replace("{positive}", str(positive))
            .replace("{negative}", str(len(vectors) - positive)))
    open(path, "w").write(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command",
                        choices=["crosscheck", "vectors", "emit-lean",
                                 "emit-repo-test", "all"])
    parser.add_argument("--rsp", default="SigVer.rsp",
                        help="path to the CAVP SigVer.rsp file")
    parser.add_argument("--json", default="p256_vectors.json")
    parser.add_argument("--lean", default="P256VectorRun.lean")
    parser.add_argument("--repo-test",
                        default="SparkInterval/Tests/P256VectorTest.lean")
    args = parser.parse_args()

    params = openssl_parameters()
    if args.command in ("crosscheck", "all"):
        params = run_crosscheck()
    if args.command == "emit-repo-test":
        vectors = curated_vectors(params, args.rsp)
        positive = sum(1 for vector in vectors if vector["expect"])
        print(f"curated vectors={len(vectors)} positive={positive} "
              f"negative={len(vectors) - positive}")
        emit_repo_test(vectors, args.repo_test)
        print(f"wrote {args.repo_test}")
        return
    if args.command in ("vectors", "emit-lean", "all"):
        vectors = build_vectors(params, args.rsp)
        positive = sum(1 for v in vectors if v["expect"])
        print(f"\nvectors={len(vectors)} positive={positive} "
              f"negative={len(vectors) - positive}")
        json.dump(vectors, open(args.json, "w"), indent=0)
        if args.command in ("emit-lean", "all"):
            emit_lean(vectors, args.lean)
            print(f"wrote {args.lean}")


if __name__ == "__main__":
    main()

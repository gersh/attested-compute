# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None


REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.numeric_corpus import (  # noqa: E402
    MANIFEST_KIND,
    PAYLOAD_ROOT_HASH_DOMAIN,
    PIN_KIND,
    SOURCE_ROOT_HASH_DOMAIN,
    NumericCorpusError,
    load_pin,
    materialize_git_corpus,
    parse_manifest_bytes,
    parse_pin_bytes,
    payload_root_sha256,
    source_root_sha256,
    snapshot_key_sha256,
    statement_sha256,
    validate_manifest,
    validate_pin_manifest,
    verify_git_corpus,
    verify_snapshot,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class NumericCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.name", "Numeric Corpus Test")
        self._git("config", "user.email", "numeric-corpus@example.com")

        self.payload_bytes = (b"0,0\n1,1\n", b"2,4\n")
        self.source_bytes = b"#!/usr/bin/env python3\nprint('generate')\n"
        paths = (
            "corpus/payloads/rows-000000-000002.csv",
            "corpus/payloads/rows-000002-000003.csv",
        )
        for path, raw in zip(paths, self.payload_bytes, strict=True):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        source_path = self.repo / "corpus/src/generate.py"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(self.source_bytes)
        source_path.chmod(0o755)

        statement = (
            "For every integer index i with 0 <= i < 3, the row at index i "
            "contains the exact integer i * i."
        )
        payloads = [
            {
                "coverage_id": "square_rows",
                "encoding": "utf8-csv-v1",
                "index_start": 0,
                "index_stop": 2,
                "path": paths[0],
                "role": "square_table",
                "row_count": 2,
                "sha256": _sha256(self.payload_bytes[0]),
                "size_bytes": len(self.payload_bytes[0]),
            },
            {
                "coverage_id": "square_rows",
                "encoding": "utf8-csv-v1",
                "index_start": 2,
                "index_stop": 3,
                "path": paths[1],
                "role": "square_table",
                "row_count": 1,
                "sha256": _sha256(self.payload_bytes[1]),
                "size_bytes": len(self.payload_bytes[1]),
            },
        ]
        sources = [
            {
                "executable": True,
                "path": "corpus/src/generate.py",
                "role": "generator",
                "sha256": _sha256(self.source_bytes),
                "size_bytes": len(self.source_bytes),
            }
        ]
        self.manifest = {
            "claim": {
                "claim_id": "example.square_table",
                "claim_version": 1,
                "lean_theorem": "Example.SquareTable.square_table",
                "lean_type": "Example.SquareTable.IsSquareTable",
                "statement": statement,
                "statement_encoding": "utf8-exact-v1",
                "statement_sha256": statement_sha256(statement),
            },
            "corpus_id": "example.square_table.rows",
            "corpus_version": 1,
            "coverage": [
                {
                    "axis": "row_index",
                    "coverage_id": "square_rows",
                    "index_start": 0,
                    "index_stop": 3,
                    "role": "square_table",
                }
            ],
            "kind": MANIFEST_KIND,
            "parameters": {
                "integer_encoding": "canonical signed decimal",
                "row_format": "index,value",
            },
            "payload_prefix": "corpus/payloads",
            "payload_root": {
                "file_count": len(payloads),
                "hash_domain": PAYLOAD_ROOT_HASH_DOMAIN,
                "sha256": payload_root_sha256(payloads),
                "total_size_bytes": sum(item["size_bytes"] for item in payloads),
            },
            "payloads": payloads,
            "schema_version": 1,
            "semantic_commitments": [],
            "source_files": sources,
            "source_root": {
                "file_count": len(sources),
                "hash_domain": SOURCE_ROOT_HASH_DOMAIN,
                "sha256": source_root_sha256(sources),
                "total_size_bytes": sum(item["size_bytes"] for item in sources),
            },
        }
        self.manifest_path = self.repo / "corpus/manifest.json"
        self._write_manifest()
        self._commit_all("valid corpus")
        self.pin = self._pin_for_head()
        self.pin_path = self.root / "pin.json"
        self.pin_path.write_bytes(canonical_json_bytes(self.pin))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def _write_manifest(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_bytes(canonical_json_bytes(self.manifest))

    def _commit_all(self, message: str) -> None:
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)

    def _pin_for_head(self) -> dict[str, object]:
        raw = self._git_show("HEAD:corpus/manifest.json")
        manifest = json.loads(raw)
        return {
            "expected": {
                "claim_id": manifest["claim"]["claim_id"],
                "claim_version": manifest["claim"]["claim_version"],
                "corpus_id": manifest["corpus_id"],
                "corpus_version": manifest["corpus_version"],
                "payload_file_count": manifest["payload_root"]["file_count"],
                "payload_root_sha256": manifest["payload_root"]["sha256"],
                "payload_total_size_bytes": manifest["payload_root"][
                    "total_size_bytes"
                ],
                "source_root_sha256": manifest["source_root"]["sha256"],
                "statement_sha256": manifest["claim"]["statement_sha256"],
            },
            "kind": PIN_KIND,
            "pin_id": "example.square_table.pin",
            "repository": {
                "commit": self._git("rev-parse", "HEAD"),
                "manifest_path": "corpus/manifest.json",
                "manifest_sha256": _sha256(raw),
                "manifest_size_bytes": len(raw),
                "url": "https://example.com/example/numeric-corpus.git",
            },
            "schema_version": 1,
        }

    def _git_show(self, object_name: str) -> bytes:
        return subprocess.run(
            ["git", "-C", str(self.repo), "show", object_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def _refresh_payload_root(self, manifest: dict[str, object]) -> None:
        payloads = manifest["payloads"]
        assert isinstance(payloads, list)
        root = manifest["payload_root"]
        assert isinstance(root, dict)
        root["file_count"] = len(payloads)
        root["total_size_bytes"] = sum(item["size_bytes"] for item in payloads)
        root["sha256"] = payload_root_sha256(payloads)

    def test_valid_pin_git_objects_and_cli_report(self) -> None:
        loaded = load_pin(self.pin_path)
        report = verify_git_corpus(self.repo, loaded)
        self.assertTrue(report["accepted"])
        self.assertFalse(report["materialized"])
        self.assertEqual(report["commit"], self.pin["repository"]["commit"])
        self.assertNotIn(str(self.repo), canonical_json_bytes(report).decode())

        completed = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "tools/fetch_tg_numeric_corpus.py"),
                str(self.pin_path),
                "--checkout",
                str(self.repo),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.stdout, canonical_json_bytes(report))
        self.assertEqual(completed.stderr, b"")

    def test_dirty_worktree_is_not_an_authority(self) -> None:
        self.manifest_path.write_bytes(b"not the committed manifest")
        (self.repo / self.manifest["payloads"][0]["path"]).write_bytes(b"bad")
        (self.repo / self.manifest["source_files"][0]["path"]).write_bytes(b"bad")
        report = verify_git_corpus(self.repo, self.pin)
        self.assertTrue(report["accepted"])

    def test_head_and_git_replace_refs_cannot_substitute_the_pinned_commit(self) -> None:
        pinned_commit = self.pin["repository"]["commit"]
        (self.repo / self.manifest["payloads"][0]["path"]).write_bytes(b"bad")
        self._commit_all("unrelated bad head")
        replacement_commit = self._git("rev-parse", "HEAD")
        self._git("replace", pinned_commit, replacement_commit)
        self.assertEqual(self._git("rev-parse", "HEAD"), replacement_commit)
        report = verify_git_corpus(self.repo, self.pin)
        self.assertEqual(report["commit"], pinned_commit)
        self.assertTrue(report["accepted"])

    def test_materialized_snapshot_is_exact_and_reusable(self) -> None:
        cache = self.root / "cache"
        first = materialize_git_corpus(self.repo, self.pin, cache)
        second = materialize_git_corpus(self.repo, self.pin, cache)
        self.assertEqual(first, second)
        self.assertTrue(first["materialized"])
        snapshot = cache / snapshot_key_sha256(self.pin)
        audit = verify_snapshot(snapshot, self.pin, self.manifest)
        self.assertTrue(audit["accepted"])
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o555)

    def test_snapshot_rejects_symlink_hardlink_and_extra_file(self) -> None:
        cache = self.root / "cache"
        materialize_git_corpus(self.repo, self.pin, cache)
        snapshot = cache / snapshot_key_sha256(self.pin)
        payload = snapshot / self.manifest["payloads"][0]["path"]
        payload.parent.chmod(0o755)
        payload.unlink()
        payload.symlink_to("/dev/null")
        payload.parent.chmod(0o555)
        with self.assertRaisesRegex(NumericCorpusError, "single-link regular"):
            verify_snapshot(snapshot, self.pin, self.manifest)

        payload.parent.chmod(0o755)
        payload.unlink()
        payload.write_bytes(self.payload_bytes[0])
        payload.chmod(0o444)
        alias = payload.parent / "alias"
        os.link(payload, alias)
        payload.parent.chmod(0o555)
        with self.assertRaisesRegex(NumericCorpusError, "single-link regular"):
            verify_snapshot(snapshot, self.pin, self.manifest)
        payload.parent.chmod(0o755)
        alias.unlink()

        extra = payload.parent / "extra"
        extra.write_bytes(b"extra")
        extra.chmod(0o444)
        payload.parent.chmod(0o555)
        with self.assertRaisesRegex(NumericCorpusError, "file set mismatch"):
            verify_snapshot(snapshot, self.pin, self.manifest)

    def test_committed_symlink_is_not_a_regular_source_blob(self) -> None:
        source = self.repo / self.manifest["source_files"][0]["path"]
        source.unlink()
        source.symlink_to("../payloads/rows-000000-000002.csv")
        self._commit_all("replace source with symlink")
        pin = self._pin_for_head()
        with self.assertRaisesRegex(NumericCorpusError, "regular blob"):
            verify_git_corpus(self.repo, pin)

    def test_resolver_symlink_and_wrong_executable_mode_are_rejected(self) -> None:
        resolver_link = self.root / "resolver-link"
        resolver_link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(NumericCorpusError, "non-symlink directory"):
            verify_git_corpus(resolver_link, self.pin)

        source = self.repo / self.manifest["source_files"][0]["path"]
        source.chmod(0o644)
        self._commit_all("remove declared executable mode")
        pin = self._pin_for_head()
        with self.assertRaisesRegex(NumericCorpusError, "100755 regular blob"):
            verify_git_corpus(self.repo, pin)

    def test_pin_and_manifest_require_canonical_duplicate_free_json(self) -> None:
        with self.assertRaisesRegex(NumericCorpusError, "canonical"):
            parse_pin_bytes(json.dumps(self.pin, indent=2).encode())
        raw = canonical_json_bytes(self.pin)
        duplicate = raw.replace(
            b'"schema_version":1',
            b'"schema_version":1,"schema_version":1',
        )
        with self.assertRaisesRegex(NumericCorpusError, "duplicate JSON key"):
            parse_pin_bytes(duplicate)
        with self.assertRaisesRegex(NumericCorpusError, "canonical"):
            parse_manifest_bytes(json.dumps(self.manifest, indent=2).encode())
        huge_integer = b'{"schema_version":' + b"9" * 5000 + b"}\n"
        with self.assertRaises(NumericCorpusError):
            parse_pin_bytes(huge_integer)

    def test_reserved_placeholders_and_wrong_repeated_values_are_rejected(self) -> None:
        placeholder = copy.deepcopy(self.pin)
        placeholder["repository"]["commit"] = "0" * 40
        with self.assertRaisesRegex(NumericCorpusError, "reserved all-zero"):
            parse_pin_bytes(canonical_json_bytes(placeholder))

        wrong = copy.deepcopy(self.pin)
        wrong["expected"]["claim_version"] = 2
        with self.assertRaisesRegex(NumericCorpusError, "does not match"):
            validate_pin_manifest(wrong, self.manifest)

        wrong_commit = copy.deepcopy(self.pin)
        wrong_commit["repository"]["commit"] = "1" * 40
        with self.assertRaises(NumericCorpusError):
            verify_git_corpus(self.repo, wrong_commit)

    def test_range_partition_rejects_gap_overlap_and_wrong_row_count(self) -> None:
        gap = copy.deepcopy(self.manifest)
        gap["payloads"][0]["index_stop"] = 1
        gap["payloads"][0]["row_count"] = 1
        self._refresh_payload_root(gap)
        with self.assertRaisesRegex(NumericCorpusError, "gap"):
            validate_manifest(gap)

        overlap = copy.deepcopy(self.manifest)
        overlap["payloads"][0]["index_stop"] = 3
        overlap["payloads"][0]["row_count"] = 3
        self._refresh_payload_root(overlap)
        with self.assertRaisesRegex(NumericCorpusError, "overlap"):
            validate_manifest(overlap)

        wrong_rows = copy.deepcopy(self.manifest)
        wrong_rows["payloads"][0]["row_count"] = 1
        self._refresh_payload_root(wrong_rows)
        with self.assertRaisesRegex(NumericCorpusError, "row_count"):
            validate_manifest(wrong_rows)

    def test_paths_ordering_and_root_substitution_are_rejected(self) -> None:
        traversal = copy.deepcopy(self.manifest)
        traversal["payloads"][0]["path"] = "../outside"
        with self.assertRaisesRegex(NumericCorpusError, "relative path|parent"):
            validate_manifest(traversal)

        reordered = copy.deepcopy(self.manifest)
        reordered["payloads"].reverse()
        self._refresh_payload_root(reordered)
        with self.assertRaisesRegex(NumericCorpusError, "ordered"):
            validate_manifest(reordered)

        duplicate = copy.deepcopy(self.manifest)
        duplicate["source_files"][0]["path"] = duplicate["payloads"][0]["path"]
        with self.assertRaisesRegex(NumericCorpusError, "duplicate"):
            validate_manifest(duplicate)

        ancestor = copy.deepcopy(self.manifest)
        ancestor["source_files"][0]["path"] = "corpus/payloads"
        with self.assertRaisesRegex(NumericCorpusError, "ancestor"):
            validate_manifest(ancestor)

        wrong_root = copy.deepcopy(self.manifest)
        wrong_root["payload_root"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(NumericCorpusError, "complete ordered"):
            validate_manifest(wrong_root)

    def test_manifest_blob_hash_and_payload_blob_hash_are_both_checked(self) -> None:
        wrong_manifest_pin = copy.deepcopy(self.pin)
        wrong_manifest_pin["repository"]["manifest_sha256"] = "f" * 64
        with self.assertRaisesRegex(NumericCorpusError, "SHA-256"):
            verify_git_corpus(self.repo, wrong_manifest_pin)

        self.manifest["payloads"][0]["sha256"] = "f" * 64
        self._refresh_payload_root(self.manifest)
        self._write_manifest()
        self._commit_all("manifest names wrong payload digest")
        pin = self._pin_for_head()
        with self.assertRaisesRegex(NumericCorpusError, "does not match its SHA-256"):
            verify_git_corpus(self.repo, pin)

    def test_promisor_lazy_fetch_is_disabled_for_untrusted_resolvers(self) -> None:
        marker = self.root / "ssh-command-ran"
        ssh_command = self.root / "malicious-ssh"
        ssh_command.write_text(
            "#!/bin/sh\n"
            f"touch '{marker}'\n"
            "exit 1\n",
            encoding="utf-8",
        )
        ssh_command.chmod(0o755)
        self._git("config", "core.repositoryformatversion", "1")
        self._git("config", "extensions.partialClone", "evil")
        self._git("config", "remote.evil.promisor", "true")
        self._git("config", "remote.evil.partialCloneFilter", "blob:none")
        self._git("config", "remote.evil.url", "ssh://example.invalid/repository")
        self._git("config", "core.sshCommand", str(ssh_command))
        object_id = self._git(
            "rev-parse", f"HEAD:{self.manifest['payloads'][0]['path']}"
        )
        loose_object = self.repo / ".git/objects" / object_id[:2] / object_id[2:]
        self.assertTrue(loose_object.is_file())
        loose_object.unlink()
        with self.assertRaises(NumericCorpusError):
            verify_git_corpus(self.repo, self.pin)
        self.assertFalse(marker.exists())

    def test_snapshot_key_includes_the_manifest_path(self) -> None:
        alternate_manifest = self.repo / "alternate/manifest.json"
        alternate_manifest.parent.mkdir()
        alternate_manifest.write_bytes(canonical_json_bytes(self.manifest))
        self._commit_all("same manifest at a second path")
        commit = self._git("rev-parse", "HEAD")
        first = copy.deepcopy(self.pin)
        first["repository"]["commit"] = commit
        second = copy.deepcopy(first)
        second["repository"]["manifest_path"] = "alternate/manifest.json"
        self.assertNotEqual(snapshot_key_sha256(first), snapshot_key_sha256(second))

        cache = self.root / "cache"
        materialize_git_corpus(self.repo, first, cache)
        materialize_git_corpus(self.repo, second, cache)
        self.assertTrue((cache / snapshot_key_sha256(first)).is_dir())
        self.assertTrue((cache / snapshot_key_sha256(second)).is_dir())

    def test_templates_and_schemas_are_parseable_but_templates_are_not_pins(self) -> None:
        schemas = {}
        for schema_name in (
            "pinned-numeric-corpus.schema.json",
            "numeric-corpus-manifest.schema.json",
        ):
            schema = json.loads((REPOSITORY / "schemas" / schema_name).read_text())
            schemas[schema_name] = schema
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

        pin_template = REPOSITORY / "examples/numeric-corpus/pin.template.json"
        manifest_template = (
            REPOSITORY / "examples/numeric-corpus/manifest.template.json"
        )
        with self.assertRaises(NumericCorpusError):
            parse_pin_bytes(pin_template.read_bytes())
        with self.assertRaises(NumericCorpusError):
            parse_manifest_bytes(manifest_template.read_bytes())
        with self.assertRaisesRegex(NumericCorpusError, "reserved all-zero"):
            parse_pin_bytes(canonical_json_bytes(json.loads(pin_template.read_text())))
        if jsonschema is not None:
            for schema in schemas.values():
                jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.Draft202012Validator(
                schemas["pinned-numeric-corpus.schema.json"]
            ).validate(self.pin)
            jsonschema.Draft202012Validator(
                schemas["numeric-corpus-manifest.schema.json"]
            ).validate(self.manifest)
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(
                    schemas["pinned-numeric-corpus.schema.json"]
                ).validate(json.loads(pin_template.read_text()))
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(
                    schemas["numeric-corpus-manifest.schema.json"]
                ).validate(json.loads(manifest_template.read_text()))

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_schema_rejects_loader_level_placeholder_and_path_attacks(self) -> None:
        pin_schema = json.loads(
            (
                REPOSITORY / "schemas/pinned-numeric-corpus.schema.json"
            ).read_text()
        )
        manifest_schema = json.loads(
            (
                REPOSITORY / "schemas/numeric-corpus-manifest.schema.json"
            ).read_text()
        )
        pin_validator = jsonschema.Draft202012Validator(pin_schema)
        manifest_validator = jsonschema.Draft202012Validator(manifest_schema)

        for mutation in (
            lambda value: value["repository"].__setitem__("commit", "0" * 40),
            lambda value: value["repository"].__setitem__(
                "url", "https://user@example.com/repository"
            ),
            lambda value: value["repository"].__setitem__(
                "manifest_path", "corpus//manifest.json"
            ),
            lambda value: value.__setitem__("pin_id", "pin\n"),
        ):
            changed = copy.deepcopy(self.pin)
            mutation(changed)
            with self.subTest(pin=changed):
                self.assertFalse(pin_validator.is_valid(changed))

        for mutation in (
            lambda value: value["claim"].__setitem__(
                "statement", value["claim"]["statement"] + "\0"
            ),
            lambda value: value["payloads"][0].__setitem__(
                "path", "corpus/payloads/"
            ),
            lambda value: value["payloads"][0].__setitem__("sha256", "0" * 64),
        ):
            changed = copy.deepcopy(self.manifest)
            mutation(changed)
            with self.subTest(manifest=changed):
                self.assertFalse(manifest_validator.is_valid(changed))


if __name__ == "__main__":
    unittest.main()

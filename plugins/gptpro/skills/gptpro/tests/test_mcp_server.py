from __future__ import annotations

import copy
import builtins
import hashlib
import io
import importlib.util
import json
import os
import select
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.archive import VerifiedArchive, strict_posix_path
from runtime.gptpro_mcp.authorization import AuthorizationGrant, StaticAuthorizationProvider
from runtime.gptpro_mcp.errors import CancelledError, ToolError
from runtime.gptpro_mcp.protocol import MAX_INPUT_FRAME_CHARS, LegacyMcpServer
from runtime.gptpro_mcp.schema import (
    DEFAULT_LIMITS,
    PROTOCOL_PROFILE,
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_CATALOG,
    TOOL_NAMES,
    canonical_json_bytes,
    tool_schema_sha256,
)
from runtime.gptpro_mcp.tools import FixtureDisclosureCommitter, ToolRuntime

PACKAGE_ID = "fixture-package"
TREE_HASH = hashlib.sha256(b"tree").hexdigest()
SESSION_HASH = hashlib.sha256(b"session").hexdigest()
MANIFEST_HASH = hashlib.sha256(b"manifest").hexdigest()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class PackageFixture:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.archive_path = self.root / "snapshot.zip"
        self.files = files or {
            "README.md": b"Alpha first\r\nsecond line\r\nSTRASSE marker\r\n",
            "src/a.py": b"one\nneedle twice needle\nthree\nfour\n",
            "src/unicode.txt": "Straße\n한글 needle\n".encode(),
        }
        self.entries = self._entries(self.files)
        self.internal = self._internal(self.entries)
        self.write_archive()
        self.manifest = self.make_manifest()

    def cleanup(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _entries(files: dict[str, bytes]) -> list[dict]:
        return [
            {
                "path": path,
                "archive_path": f"repo/{path}",
                "size": len(data),
                "sha256": digest(data),
            }
            for path, data in sorted(files.items())
        ]

    @staticmethod
    def _internal(entries: list[dict]) -> bytes:
        return (
            json.dumps(
                {
                    "schema_version": 3,
                    "package_id": PACKAGE_ID,
                    "git": {"head_sha": "a" * 40, "clean": True, "dirty_paths": []},
                    "selection": {"scope": "tracked"},
                    "files": entries,
                    "totals": {
                        "included_files": len(entries),
                        "included_bytes": sum(item["size"] for item in entries),
                    },
                    "packaged_tree_sha256": TREE_HASH,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode()

    def write_archive(
        self,
        *,
        entries: list[tuple[str, bytes, int, int]] | None = None,
        internal: bytes | None = None,
        duplicate_internal: bool = False,
    ) -> None:
        rows = entries or [
            (f"repo/{path}", data, zipfile.ZIP_STORED, 0o100644) for path, data in self.files.items()
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive_path, "w") as archive:
                for name, data, compression, mode in rows:
                    info = zipfile.ZipInfo(name)
                    info.external_attr = mode << 16
                    info.compress_type = compression
                    archive.writestr(info, data)
                info = zipfile.ZipInfo("_gptpro/file-manifest.json")
                info.external_attr = 0o100644 << 16
                archive.writestr(info, internal if internal is not None else self.internal)
                if duplicate_internal:
                    archive.writestr(info, internal if internal is not None else self.internal)

    def make_manifest(self, *, limits: dict | None = None) -> dict:
        allowed = [{key: row[key] for key in ("path", "size", "sha256")} for row in self.entries]
        archive_hash = digest(self.archive_path.read_bytes())
        return {
            "schema_version": 3,
            "package_id": PACKAGE_ID,
            "mode": "review",
            "transport": {"requested": "mcp-read", "resolved": "mcp-read"},
            "delivery": {"channel": "browser", "approval_required": True},
            "connector": {
                "type": "secure-mcp-tunnel",
                "protocol_profile": PROTOCOL_PROFILE,
                "tool_schema_sha256": tool_schema_sha256(),
            },
            "repository": {"git_sha": "a" * 40},
            "files": copy.deepcopy(self.entries),
            "hashes": {
                "archive_sha256": archive_hash,
                "internal_manifest_sha256": digest(self.internal),
                "packaged_tree_sha256": TREE_HASH,
                "file_set_sha256": digest(canonical_json_bytes(allowed)),
            },
            "mcp_disclosure": {
                "snapshot": "immutable-local-archive",
                "allowed_files": allowed,
                "file_set_sha256": digest(canonical_json_bytes(allowed)),
                "potential_files": len(allowed),
                "potential_bytes": sum(item["size"] for item in allowed),
                "tools": list(TOOL_NAMES),
                "limits": copy.deepcopy(limits or DEFAULT_LIMITS),
            },
        }

    def grant(self, *, manifest: dict | None = None, refresh_archive_hash: bool = False) -> AuthorizationGrant:
        value = copy.deepcopy(manifest or self.manifest)
        if refresh_archive_hash:
            value["hashes"]["archive_sha256"] = digest(self.archive_path.read_bytes())
        return AuthorizationGrant(
            package_id=PACKAGE_ID,
            manifest=value,
            archive_path=self.archive_path,
            archive_sha256=value["hashes"]["archive_sha256"],
            manifest_sha256=MANIFEST_HASH,
            session_id_sha256=SESSION_HASH,
            session_nonce=b"n" * 32,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            idle_expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

    def runtime(self, *, manifest: dict | None = None) -> ToolRuntime:
        return ToolRuntime(
            StaticAuthorizationProvider(self.grant(manifest=manifest)),
            committer=FixtureDisclosureCommitter(),
        )


class ArchiveSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PackageFixture()

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def assert_archive_error(self, code: str | None = None) -> ToolError:
        with self.assertRaises(ToolError) as raised:
            VerifiedArchive.open(self.fixture.grant(refresh_archive_hash=True))
        if code:
            self.assertEqual(code, raised.exception.code)
        self.assertNotIn(str(self.fixture.root), raised.exception.message)
        return raised.exception

    def test_approved_members_are_read_without_extraction(self) -> None:
        before = sorted(self.fixture.root.iterdir())
        snapshot = VerifiedArchive.open(self.fixture.grant())
        self.assertEqual(sorted(self.fixture.files), [item.path for item in snapshot.files])
        self.assertEqual(self.fixture.files["src/a.py"], snapshot.file("src/a.py").data)
        self.assertEqual(before, sorted(self.fixture.root.iterdir()))
        with self.assertRaises(ToolError) as raised:
            snapshot.file("unapproved.txt")
        self.assertEqual("PATH_NOT_APPROVED", raised.exception.code)

    def test_strict_path_rejects_traversal_and_platform_aliases(self) -> None:
        invalid = ["", "/tmp/a", "../a", "a/../b", "a/./b", "a//b", "a\\b", "a\0b", "C:/a"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ToolError) as raised:
                strict_posix_path(value)
            self.assertEqual("PATH_INVALID", raised.exception.code)

    def test_changed_zip_bytes_fail_before_member_disclosure(self) -> None:
        with self.fixture.archive_path.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaises(ToolError) as raised:
            VerifiedArchive.open(self.fixture.grant())
        self.assertEqual("CONTENT_DRIFT", raised.exception.code)

    def test_archive_path_symlink_hardlink_and_writable_mode_are_rejected(self) -> None:
        target = self.fixture.root / "target.zip"
        self.fixture.archive_path.rename(target)
        self.fixture.archive_path.symlink_to(target)
        self.assert_archive_error("PACKAGE_TAMPERED")
        self.fixture.archive_path.unlink()
        target.rename(self.fixture.archive_path)

        hardlink = self.fixture.root / "hardlink.zip"
        os.link(self.fixture.archive_path, hardlink)
        self.assert_archive_error("PACKAGE_TAMPERED")
        hardlink.unlink()

        original_mode = self.fixture.archive_path.stat().st_mode & 0o777
        self.fixture.archive_path.chmod(0o666)
        self.assert_archive_error("PACKAGE_TAMPERED")
        self.fixture.archive_path.chmod(original_mode)

    def test_duplicate_missing_and_unexpected_members_are_rejected(self) -> None:
        rows = [("repo/README.md", self.fixture.files["README.md"], 0, 0o100644)] * 2
        rows.extend(
            (f"repo/{path}", data, 0, 0o100644)
            for path, data in self.fixture.files.items()
            if path != "README.md"
        )
        self.fixture.write_archive(entries=rows)
        self.assert_archive_error("ARCHIVE_MEMBER_INVALID")

        rows = [(f"repo/{path}", data, 0, 0o100644) for path, data in self.fixture.files.items()][1:]
        self.fixture.write_archive(entries=rows)
        self.assert_archive_error("ARCHIVE_MEMBER_INVALID")

        rows.append(("repo/extra.txt", b"extra", 0, 0o100644))
        self.fixture.write_archive(entries=rows)
        self.assert_archive_error("ARCHIVE_MEMBER_INVALID")

    def test_duplicate_internal_manifest_and_changed_internal_manifest_are_rejected(self) -> None:
        self.fixture.write_archive(duplicate_internal=True)
        self.assert_archive_error("ARCHIVE_MEMBER_INVALID")
        self.fixture.write_archive(internal=b"{}\n")
        self.assert_archive_error("CONTENT_DRIFT")

    def test_symlink_directory_nul_and_invalid_utf8_members_are_rejected(self) -> None:
        cases = [
            ([("repo/README.md", b"target", 0, 0o120777)], "symlink"),
            ([("repo/README.md", b"", 0, 0o040755)], "directory"),
            ([("repo/README.md", b"a\0b", 0, 0o100644)], "nul"),
            ([("repo/README.md", b"\xff", 0, 0o100644)], "utf8"),
        ]
        others = [
            (f"repo/{path}", data, 0, 0o100644)
            for path, data in self.fixture.files.items()
            if path != "README.md"
        ]
        for first, label in cases:
            with self.subTest(label=label):
                self.fixture.write_archive(entries=first + others)
                self.assert_archive_error()

    def test_member_hash_and_manifest_file_set_drift_are_rejected(self) -> None:
        rows = [
            (f"repo/{path}", b"changed" if path == "README.md" else data, 0, 0o100644)
            for path, data in self.fixture.files.items()
        ]
        self.fixture.write_archive(entries=rows)
        self.assert_archive_error("CONTENT_DRIFT")
        self.fixture.write_archive()
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest["mcp_disclosure"]["allowed_files"][0]["size"] += 1
        with self.assertRaises(ToolError) as raised:
            VerifiedArchive.open(self.fixture.grant(manifest=manifest, refresh_archive_hash=True))
        self.assertEqual("PACKAGE_TAMPERED", raised.exception.code)

    def test_unicode_case_collision_and_oversized_member_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.fixture.manifest)
        first = manifest["files"][0]
        duplicate = copy.deepcopy(first)
        duplicate["path"] = first["path"].swapcase()
        duplicate["archive_path"] = "repo/" + duplicate["path"]
        manifest["files"].insert(1, duplicate)
        with self.assertRaises(ToolError) as raised:
            VerifiedArchive.open(self.fixture.grant(manifest=manifest))
        self.assertEqual("PACKAGE_TAMPERED", raised.exception.code)

        data = b"x" * (2 * 1024 * 1024 + 1)
        rows = [("repo/README.md", data, 0, 0o100644)] + [
            (f"repo/{path}", value, 0, 0o100644)
            for path, value in self.fixture.files.items()
            if path != "README.md"
        ]
        self.fixture.write_archive(entries=rows)
        self.assert_archive_error("ARCHIVE_LIMIT_EXCEEDED")

    def test_high_compression_ratio_and_encryption_flag_are_rejected(self) -> None:
        data = b"x" * 100_000
        rows = [("repo/README.md", data, zipfile.ZIP_DEFLATED, 0o100644)] + [
            (f"repo/{path}", value, 0, 0o100644)
            for path, value in self.fixture.files.items()
            if path != "README.md"
        ]
        self.fixture.write_archive(entries=rows)
        self.assert_archive_error("ARCHIVE_LIMIT_EXCEEDED")

        self.fixture.write_archive()
        payload = bytearray(self.fixture.archive_path.read_bytes())
        local = payload.index(b"PK\x03\x04")
        central = payload.index(b"PK\x01\x02")
        struct.pack_into("<H", payload, local + 6, struct.unpack_from("<H", payload, local + 6)[0] | 1)
        struct.pack_into("<H", payload, central + 8, struct.unpack_from("<H", payload, central + 8)[0] | 1)
        self.fixture.archive_path.write_bytes(payload)
        self.assert_archive_error("ARCHIVE_MEMBER_INVALID")


class ToolSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PackageFixture()
        self.runtime = self.fixture.runtime()

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def call(self, name: str, **arguments):
        result = self.runtime.call(name, {"package_id": PACKAGE_ID, **arguments})
        self.assertFalse(result["isError"])
        self.assertNotIn("Alpha first", result["content"][0]["text"])
        return result["structuredContent"]["result"]

    def test_package_info_pages_paths_with_bound_cursor(self) -> None:
        first = self.call("gptpro_package_info", include_paths=True, path_page_size=1)
        self.assertEqual(["README.md"], [item["path"] for item in first["allowed_paths_page"]])
        self.assertIsNotNone(first["next_cursor"])
        second = self.call(
            "gptpro_package_info",
            include_paths=True,
            path_page_size=1,
            cursor=first["next_cursor"],
        )
        self.assertEqual(["src/a.py"], [item["path"] for item in second["allowed_paths_page"]])
        with self.assertRaises(ToolError) as raised:
            self.runtime.call(
                "gptpro_package_info",
                {"package_id": PACKAGE_ID, "include_paths": True, "path_page_size": 2,
                 "cursor": first["next_cursor"]},
            )
        self.assertEqual("CURSOR_INVALID", raised.exception.code)

    def test_read_preserves_crlf_and_hashes_exact_fragment(self) -> None:
        result = self.call("gptpro_repo_read", path="README.md", start_line=1, end_line=2)
        self.assertEqual("Alpha first\r\nsecond line\r\n", result["text"])
        self.assertEqual(digest(result["text"].encode()), result["fragment_sha256"])
        self.assertEqual({"start_line": 1, "end_line": 2}, result["returned"])
        self.assertTrue(result["complete"])

    def test_read_paginates_only_on_line_boundaries_and_detects_cursor_tamper(self) -> None:
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest["mcp_disclosure"]["limits"]["max_read_content_bytes"] = 20
        self.runtime = self.fixture.runtime(manifest=manifest)
        first = self.call("gptpro_repo_read", path="src/a.py")
        self.assertFalse(first["complete"])
        self.assertTrue(first["text"].endswith("\n"))
        second = self.call("gptpro_repo_read", path="src/a.py", cursor=first["next_cursor"])
        self.assertGreater(second["returned"]["start_line"], first["returned"]["end_line"])
        token = first["next_cursor"]
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with self.assertRaises(ToolError) as raised:
            self.runtime.call(
                "gptpro_repo_read",
                {"package_id": PACKAGE_ID, "path": "src/a.py", "cursor": tampered},
            )
        self.assertEqual("CURSOR_INVALID", raised.exception.code)

    def test_read_empty_missing_newline_and_long_line(self) -> None:
        self.fixture.cleanup()
        self.fixture = PackageFixture({"empty.txt": b"", "tail.txt": b"tail", "long.txt": b"x" * 100})
        self.runtime = self.fixture.runtime()
        self.assertEqual("", self.call("gptpro_repo_read", path="empty.txt")["text"])
        self.assertEqual("tail", self.call("gptpro_repo_read", path="tail.txt")["text"])
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest["mcp_disclosure"]["limits"]["max_read_content_bytes"] = 20
        self.runtime = self.fixture.runtime(manifest=manifest)
        with self.assertRaises(ToolError) as raised:
            self.runtime.call("gptpro_repo_read", {"package_id": PACKAGE_ID, "path": "long.txt"})
        self.assertEqual("RESULT_LIMIT_EXCEEDED", raised.exception.code)

    def test_literal_search_unicode_casefold_dedup_and_order(self) -> None:
        result = self.call("gptpro_repo_search", query="needle", context_lines=0)
        self.assertEqual(
            [("src/a.py", 2), ("src/unicode.txt", 2)],
            [(item["path"], item["line"]) for item in result["matches"]],
        )
        self.assertEqual(2, len(result["matches"]))  # repeated occurrence on one line is deduplicated
        folded = self.call(
            "gptpro_repo_search", query="STRASSE", case_sensitive=False, context_lines=0
        )
        self.assertEqual(["README.md", "src/unicode.txt"], [item["path"] for item in folded["matches"]])
        self.assertEqual([], self.call("gptpro_repo_search", query="absent")["matches"])

    def test_search_exact_and_subtree_filters_and_invalid_wildcard(self) -> None:
        exact = self.call("gptpro_repo_search", query="needle", paths=["src/a.py"], context_lines=0)
        self.assertEqual(["src/a.py"], [item["path"] for item in exact["matches"]])
        subtree = self.call("gptpro_repo_search", query="needle", paths=["src/**"], context_lines=0)
        self.assertEqual(["src/a.py", "src/unicode.txt"], [item["path"] for item in subtree["matches"]])
        for path, code in (("src/*.py", "PATH_INVALID"), ("missing.py", "PATH_NOT_APPROVED")):
            with self.subTest(path=path), self.assertRaises(ToolError) as raised:
                self.runtime.call(
                    "gptpro_repo_search",
                    {"package_id": PACKAGE_ID, "query": "x", "paths": [path]},
                )
            self.assertEqual(code, raised.exception.code)

    def test_search_query_validation_and_result_cursor(self) -> None:
        for query in ("", "   ", "a\n", "a\r", "a\0"):
            with self.subTest(query=query), self.assertRaises(ToolError) as raised:
                self.runtime.call(
                    "gptpro_repo_search", {"package_id": PACKAGE_ID, "query": query}
                )
            self.assertEqual("SEARCH_QUERY_INVALID", raised.exception.code)
        first = self.call("gptpro_repo_search", query="needle", max_results=1, context_lines=0)
        self.assertFalse(first["complete"])
        second = self.call(
            "gptpro_repo_search", query="needle", max_results=1, context_lines=0,
            cursor=first["next_cursor"]
        )
        self.assertNotEqual(first["matches"][0]["path"], second["matches"][0]["path"])

    def test_search_stops_after_one_page_instead_of_materializing_all_matches(self) -> None:
        self.fixture.cleanup()
        self.fixture = PackageFixture({"many.txt": b"x\n" * 100_000})
        ticks = [0.0]

        def monotonic() -> float:
            ticks[0] += 0.001
            return ticks[0]

        runtime = ToolRuntime(
            StaticAuthorizationProvider(self.fixture.grant()),
            monotonic=monotonic,
            committer=FixtureDisclosureCommitter(),
        )
        result = runtime.call(
            "gptpro_repo_search",
            {
                "package_id": PACKAGE_ID,
                "query": "x",
                "max_results": 1,
                "context_lines": 0,
            },
        )["structuredContent"]["result"]
        self.assertEqual(1, result["returned_results"])
        self.assertFalse(result["complete"])
        self.assertLess(ticks[0], 1.0)

    def test_read_implicit_eof_obeys_line_span_limit(self) -> None:
        self.fixture.cleanup()
        self.fixture = PackageFixture({"many.txt": b"x\n" * 1_001})
        runtime = self.fixture.runtime()
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_read",
                {"package_id": PACKAGE_ID, "path": "many.txt"},
            )
        self.assertEqual("RANGE_INVALID", raised.exception.code)

    def test_search_and_read_share_byte_preserving_line_boundaries(self) -> None:
        self.fixture.cleanup()
        self.fixture = PackageFixture({"unicode.txt": "first\u2028needle\nsecond\n".encode()})
        self.runtime = self.fixture.runtime()
        match = self.call(
            "gptpro_repo_search", query="needle", max_results=1, context_lines=0
        )["matches"][0]
        read = self.call(
            "gptpro_repo_read", path="unicode.txt", start_line=match["line"], end_line=match["line"]
        )
        self.assertEqual(1, match["line"])
        self.assertIn("needle", read["text"])

    def test_call_and_disclosure_limits_recount_repeated_content(self) -> None:
        limits = copy.deepcopy(DEFAULT_LIMITS)
        limits["max_tool_calls"] = 1
        manifest = self.fixture.make_manifest(limits=limits)
        runtime = self.fixture.runtime(manifest=manifest)
        runtime.call("gptpro_repo_read", {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1})
        with self.assertRaises(ToolError) as raised:
            runtime.call("gptpro_repo_read", {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1})
        self.assertEqual("CALL_LIMIT_EXCEEDED", raised.exception.code)

        limits["max_tool_calls"] = 10
        limits["max_session_disclosure_bytes"] = len("src/a.py".encode()) + len(b"one\n") + 1
        manifest = self.fixture.make_manifest(limits=limits)
        runtime = self.fixture.runtime(manifest=manifest)
        runtime.call("gptpro_repo_read", {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1})
        with self.assertRaises(ToolError) as raised:
            runtime.call("gptpro_repo_read", {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1})
        self.assertEqual("DISCLOSURE_BUDGET_EXCEEDED", raised.exception.code)

    def test_rejected_tool_attempt_consumes_call_budget(self) -> None:
        limits = copy.deepcopy(DEFAULT_LIMITS)
        limits["max_tool_calls"] = 1
        runtime = self.fixture.runtime(manifest=self.fixture.make_manifest(limits=limits))
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_search",
                {"package_id": PACKAGE_ID, "query": ""},
            )
        self.assertEqual("SEARCH_QUERY_INVALID", raised.exception.code)
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_search",
                {"package_id": PACKAGE_ID, "query": "needle"},
            )
        self.assertEqual("CALL_LIMIT_EXCEEDED", raised.exception.code)

    def test_authorization_is_revalidated_before_content_commit(self) -> None:
        grant = self.fixture.grant()

        class RevokingProvider:
            def __init__(self) -> None:
                self.calls = 0

            def resolve(self, package_id):
                self.calls += 1
                if self.calls > 1:
                    raise ToolError(
                        "NO_ACTIVE_PACKAGE",
                        "No approved repository package is active.",
                    )
                grant.validate(package_id)
                return grant

        with self.assertRaises(ToolError) as raised:
            ToolRuntime(RevokingProvider(), committer=FixtureDisclosureCommitter()).call(
                "gptpro_repo_read",
                {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1},
                request_id="request-1",
            )
        self.assertEqual("NO_ACTIVE_PACKAGE", raised.exception.code)

    def test_committer_receives_hashes_and_metadata_without_repository_body(self) -> None:
        class RecordingCommitter:
            def __init__(self) -> None:
                self.record = None

            def commit_before_return(self, **kwargs):
                self.record = kwargs

        committer = RecordingCommitter()
        runtime = ToolRuntime(
            StaticAuthorizationProvider(self.fixture.grant()), committer=committer
        )
        runtime.call(
            "gptpro_repo_search",
            {
                "package_id": PACKAGE_ID,
                "query": "needle",
                "max_results": 1,
                "context_lines": 0,
            },
            request_id="request-2",
        )
        self.assertIsNotNone(committer.record)
        serialized = json.dumps(committer.record["audit_metadata"], sort_keys=True)
        self.assertNotIn("needle twice", serialized)
        self.assertNotIn('"query": "needle"', serialized)
        self.assertEqual(64, len(committer.record["request_id_sha256"]))
        self.assertEqual(64, len(committer.record["arguments_sha256"]))

    def test_rejected_attempt_is_audited_without_arguments_or_content(self) -> None:
        class RecordingCommitter:
            def __init__(self) -> None:
                self.rejection = None

            def commit_before_return(self, **kwargs):
                del kwargs

            def record_rejection(self, **kwargs):
                self.rejection = kwargs

        committer = RecordingCommitter()
        runtime = ToolRuntime(
            StaticAuthorizationProvider(self.fixture.grant()), committer=committer
        )
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_search",
                {"package_id": PACKAGE_ID, "query": ""},
                request_id="rejected-request",
            )
        self.assertEqual("SEARCH_QUERY_INVALID", raised.exception.code)
        self.assertIsNotNone(committer.rejection)
        self.assertEqual("SEARCH_QUERY_INVALID", committer.rejection["error_code"])
        self.assertEqual(1, committer.rejection["calls_used"])
        serialized = json.dumps(
            {key: value for key, value in committer.rejection.items() if key != "grant"},
            sort_keys=True,
        )
        self.assertNotIn("rejected-request", serialized)
        self.assertEqual(64, len(committer.rejection["request_id_sha256"]))
        self.assertEqual(64, len(committer.rejection["arguments_sha256"]))

    def test_non_utf8_json_argument_does_not_desync_call_counter(self) -> None:
        class SequencingCommitter:
            def __init__(self) -> None:
                self.commits: list[dict] = []
                self.rejections: list[dict] = []

            def commit_before_return(self, **kwargs):
                self.commits.append(kwargs)

            def record_rejection(self, **kwargs):
                self.rejections.append(kwargs)

        committer = SequencingCommitter()
        runtime = ToolRuntime(
            StaticAuthorizationProvider(self.fixture.grant()), committer=committer
        )
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_search",
                {"package_id": PACKAGE_ID, "query": "\ud800"},
                request_id="invalid-unicode",
            )
        self.assertEqual("MCP_INVALID_ARGUMENT", raised.exception.code)
        self.assertEqual([], committer.commits)
        self.assertEqual([], committer.rejections)

        result = runtime.call(
            "gptpro_package_info",
            {"package_id": PACKAGE_ID},
            request_id="next-valid-request",
        )
        self.assertEqual(1, result["structuredContent"]["result"]["session"]["calls_used"])
        self.assertEqual(1, committer.commits[0]["calls_used"])

    def test_committer_failure_prevents_content_result(self) -> None:
        class FailingCommitter:
            def commit_before_return(self, **kwargs):
                del kwargs
                raise ToolError(
                    "AUDIT_WRITE_FAILED",
                    "The disclosure audit could not be committed.",
                )

        runtime = ToolRuntime(
            StaticAuthorizationProvider(self.fixture.grant()), committer=FailingCommitter()
        )
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_read",
                {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1},
                request_id="request-3",
            )
        self.assertEqual("AUDIT_WRITE_FAILED", raised.exception.code)

    def test_missing_committer_fails_closed_even_with_static_authorization(self) -> None:
        runtime = ToolRuntime(StaticAuthorizationProvider(self.fixture.grant()))
        with self.assertRaises(ToolError) as raised:
            runtime.call(
                "gptpro_repo_read",
                {"package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1},
            )
        self.assertEqual("AUDIT_UNAVAILABLE", raised.exception.code)

    def test_cancellation_and_timeout_return_no_content(self) -> None:
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(CancelledError):
            self.runtime.call(
                "gptpro_repo_search",
                {"package_id": PACKAGE_ID, "query": "needle"},
                cancelled=cancelled,
            )

        ticks = iter((0.0, 31.0, 31.0, 31.0))
        runtime = ToolRuntime(
            StaticAuthorizationProvider(self.fixture.grant()),
            monotonic=lambda: next(ticks, 31.0),
            committer=FixtureDisclosureCommitter(),
        )
        with self.assertRaises(ToolError) as raised:
            runtime.call("gptpro_repo_search", {"package_id": PACKAGE_ID, "query": "needle"})
        self.assertEqual("TIMEOUT", raised.exception.code)


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PackageFixture()

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def transcript(self, messages: list[object], runtime: ToolRuntime | None = None):
        source = io.StringIO("".join(json.dumps(item) + "\n" for item in messages))
        output = io.StringIO()
        stderr = io.StringIO()
        server = LegacyMcpServer(runtime or self.fixture.runtime())
        self.assertEqual(0, server.serve(source, output, stderr))
        lines = output.getvalue().splitlines()
        return [json.loads(line) for line in lines], output.getvalue(), stderr.getvalue()

    @staticmethod
    def initialize(version: str = "2025-11-25", request_id: object = 1):
        return {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {"protocolVersion": version}}

    def test_golden_initialize_list_call_transcript(self) -> None:
        responses, raw, stderr = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": "ping", "method": "ping"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "gptpro_repo_read", "arguments": {
                        "package_id": PACKAGE_ID, "path": "src/a.py", "end_line": 1
                    }},
                },
            ]
        )
        self.assertEqual([1, "ping", 2, 3], [item["id"] for item in responses])
        initialized = responses[0]["result"]
        self.assertEqual("2025-11-25", initialized["protocolVersion"])
        self.assertEqual({"tools": {}}, initialized["capabilities"])
        self.assertEqual({"name": SERVER_NAME, "version": SERVER_VERSION}, initialized["serverInfo"])
        self.assertEqual(list(TOOL_CATALOG), responses[2]["result"]["tools"])
        self.assertEqual("one\n", responses[3]["result"]["structuredContent"]["result"]["text"])
        advertised = responses[2]["result"]["tools"][1]["outputSchema"]["oneOf"][0]
        structured = responses[3]["result"]["structuredContent"]
        self.assertTrue(set(advertised["required"]).issubset(structured))
        self.assertTrue(
            set(advertised["properties"]["result"]["required"]).issubset(
                structured["result"]
            )
        )
        self.assertEqual("", stderr)
        for line in raw.splitlines():
            self.assertIsInstance(json.loads(line), dict)

    def test_protocol_negotiates_legacy_revisions_and_latest_fallback(self) -> None:
        for version in (
            "2025-11-25",
            "2025-06-18",
            "2025-03-26",
            "2024-11-05",
        ):
            with self.subTest(version=version):
                responses, _, _ = self.transcript([self.initialize(version)])
                self.assertEqual(version, responses[0]["result"]["protocolVersion"])
        responses, _, _ = self.transcript([self.initialize("2026-07-28")])
        self.assertEqual("2025-11-25", responses[0]["result"]["protocolVersion"])

    def test_different_version_initialize_after_ready_is_rejected_without_closing_tools(self) -> None:
        responses, _, _ = self.transcript([
            self.initialize(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            self.initialize("2025-06-18", request_id=3),
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        ])
        self.assertEqual(-32600, responses[2]["error"]["code"])
        self.assertEqual(list(TOOL_CATALOG), responses[3]["result"]["tools"])

    def test_same_version_initialize_after_ready_is_idempotent_without_discovery(self) -> None:
        responses, _, _ = self.transcript([
            self.initialize(request_id="first"),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            self.initialize(request_id="ready-replay-1"),
            self.initialize(request_id="ready-replay-2"),
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
        ])
        by_id = {response["id"]: response for response in responses}
        self.assertEqual(by_id["first"]["result"], by_id["ready-replay-1"]["result"])
        self.assertEqual(by_id["first"]["result"], by_id["ready-replay-2"]["result"])
        self.assertEqual(list(TOOL_CATALOG), by_id["list"]["result"]["tools"])

    def test_same_version_initialize_after_discovery_ready_remains_rejected(self) -> None:
        responses, _, _ = self.transcript([
            {
                "jsonrpc": "2.0",
                "id": "discover",
                "method": "server/discover",
                "params": {},
            },
            self.initialize(request_id="probe"),
            self.initialize(request_id="connector"),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            self.initialize(request_id="ready-replay"),
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
        ])
        by_id = {response["id"]: response for response in responses}
        self.assertEqual(-32601, by_id["discover"]["error"]["code"])
        self.assertEqual(by_id["probe"]["result"], by_id["connector"]["result"])
        self.assertEqual(-32600, by_id["ready-replay"]["error"]["code"])
        self.assertEqual(list(TOOL_CATALOG), by_id["list"]["result"]["tools"])

    def test_tunnel_reinitializes_after_modern_discovery_fallback(self) -> None:
        responses, _, _ = self.transcript([
            self.initialize(request_id="compatibility-initialize"),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "warm-list", "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": "discover",
                "method": "server/discover",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientInfo": {
                            "name": "connector",
                            "version": "1",
                        },
                        "io.modelcontextprotocol/clientCapabilities": {},
                    }
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "closed-list", "method": "tools/list"},
            self.initialize("2024-11-05", request_id="connector-initialize"),
            {"jsonrpc": "2.0", "id": "pre-notification-list", "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
        ])
        self.assertEqual(list(TOOL_CATALOG), responses[1]["result"]["tools"])
        self.assertEqual(-32601, responses[2]["error"]["code"])
        self.assertEqual(-32600, responses[3]["error"]["code"])
        self.assertEqual("2024-11-05", responses[4]["result"]["protocolVersion"])
        self.assertEqual(-32600, responses[5]["error"]["code"])
        self.assertEqual(list(TOOL_CATALOG), responses[6]["result"]["tools"])

    def test_tunnel_connector_probe_replays_same_version_initialize_before_ready(self) -> None:
        responses, _, _ = self.transcript([
            {
                "jsonrpc": "2.0",
                "id": "discover",
                "method": "server/discover",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    }
                },
            },
            self.initialize("2025-11-25", request_id="probe-initialize"),
            self.initialize("2025-11-25", request_id="connector-initialize"),
            self.initialize("2025-11-25", request_id="unexpected-third-initialize"),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
        ])
        self.assertEqual(-32601, responses[0]["error"]["code"])
        self.assertEqual("2025-11-25", responses[1]["result"]["protocolVersion"])
        self.assertEqual(responses[1]["result"], responses[2]["result"])
        self.assertEqual(-32600, responses[3]["error"]["code"])
        self.assertEqual(list(TOOL_CATALOG), responses[4]["result"]["tools"])

    def test_tunnel_request_scoped_tool_calls_accept_identical_reinitialize(self) -> None:
        package_call = {
            "jsonrpc": "2.0",
            "id": "package-info-1",
            "method": "tools/call",
            "params": {
                "name": "gptpro_package_info",
                "arguments": {"package_id": PACKAGE_ID},
            },
        }
        responses, _, _ = self.transcript([
            self.initialize("2025-11-25", request_id="probe-initialize"),
            self.initialize("2025-11-25", request_id="request-initialize"),
            package_call,
            self.initialize("2025-11-25", request_id="next-request-initialize"),
            self.initialize("2024-11-05", request_id="different-version"),
        ])
        by_id = {response["id"]: response for response in responses}
        self.assertEqual(
            by_id["probe-initialize"]["result"],
            by_id["request-initialize"]["result"],
        )
        self.assertTrue(by_id["package-info-1"]["result"]["structuredContent"]["ok"])
        self.assertEqual(
            by_id["probe-initialize"]["result"],
            by_id["next-request-initialize"]["result"],
        )
        self.assertEqual(-32600, by_id["different-version"]["error"]["code"])

    def test_request_scoped_compatibility_keeps_nonmatching_paths_locked(self) -> None:
        valid_call = {
            "jsonrpc": "2.0",
            "id": "package-info",
            "method": "tools/call",
            "params": {
                "name": "gptpro_package_info",
                "arguments": {"package_id": PACKAGE_ID},
            },
        }
        without_replay, _, _ = self.transcript([
            self.initialize(),
            valid_call,
        ])
        self.assertEqual(-32600, without_replay[1]["error"]["code"])

        after_discover, _, _ = self.transcript([
            {
                "jsonrpc": "2.0",
                "id": "discover",
                "method": "server/discover",
                "params": {},
            },
            self.initialize(request_id="probe"),
            self.initialize(request_id="connector"),
            valid_call,
        ])
        self.assertEqual(-32600, after_discover[3]["error"]["code"])

        malformed, _, _ = self.transcript([
            self.initialize(request_id="probe"),
            self.initialize(request_id="request"),
            {
                "jsonrpc": "2.0",
                "id": "bad-call",
                "method": "tools/call",
                "params": {
                    "name": "gptpro_package_info",
                    "arguments": "not-an-object",
                },
            },
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
        ])
        self.assertEqual(-32600, malformed[2]["error"]["code"])
        self.assertEqual(-32600, malformed[3]["error"]["code"])

        unsupported, _, _ = self.transcript([
            self.initialize("2026-07-28", request_id="unsupported-probe"),
            self.initialize("2025-11-25", request_id="supported-replay"),
            valid_call,
        ])
        self.assertEqual(-32600, unsupported[2]["error"]["code"])

    def test_pre_ready_different_version_duplicate_initialize_is_rejected(self) -> None:
        responses, _, _ = self.transcript([
            self.initialize("2025-11-25", request_id="probe-initialize"),
            self.initialize("2024-11-05", request_id="different-initialize"),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
        ])
        self.assertEqual("2025-11-25", responses[0]["result"]["protocolVersion"])
        self.assertEqual(-32600, responses[1]["error"]["code"])
        self.assertEqual(list(TOOL_CATALOG), responses[2]["result"]["tools"])

    def test_preinitialized_tools_fail(self) -> None:
        responses, _, _ = self.transcript([
            {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
        ])
        self.assertEqual(-32600, responses[0]["error"]["code"])

    def test_unknown_method_does_not_open_reinitialize_fallback(self) -> None:
        responses, _, _ = self.transcript([
            self.initialize(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "unknown"},
            self.initialize("2025-06-18", request_id=3),
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        ])
        self.assertEqual(-32601, responses[1]["error"]["code"])
        self.assertEqual(-32600, responses[2]["error"]["code"])
        self.assertEqual(list(TOOL_CATALOG), responses[3]["result"]["tools"])

    def test_malformed_batch_invalid_ids_and_unknown_methods(self) -> None:
        source = io.StringIO(
            "{broken\n"
            + json.dumps([]) + "\n"
            + json.dumps({"jsonrpc": "1.0", "id": 1, "method": "ping"}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": True, "method": "ping"}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 8, "method": "unknown"}) + "\n"
        )
        output, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(0, LegacyMcpServer(self.fixture.runtime()).serve(source, output, stderr))
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([-32700, -32600, -32600, -32600, -32601], [r["error"]["code"] for r in responses])
        self.assertEqual([None, None, 1, None, 8], [r["id"] for r in responses])

    def test_json_decoder_resource_errors_are_parse_errors_and_next_frame_survives(self) -> None:
        source = io.StringIO("{}\n{}\n{}\n")
        output, stderr = io.StringIO(), io.StringIO()
        ping = {"jsonrpc": "2.0", "id": 9, "method": "ping"}
        with mock.patch(
            "runtime.gptpro_mcp.protocol.json.loads",
            side_effect=[ValueError("integer digit limit"), RecursionError("nested input"), ping],
        ):
            self.assertEqual(0, LegacyMcpServer(self.fixture.runtime()).serve(source, output, stderr))
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([-32700, -32700], [item["error"]["code"] for item in responses[:2]])
        self.assertEqual(
            ["MCP_PROTOCOL_ERROR", "MCP_PROTOCOL_ERROR"],
            [item["error"]["data"]["code"] for item in responses[:2]],
        )
        self.assertEqual({}, responses[2]["result"])
        self.assertEqual("", stderr.getvalue())

    def test_oversized_frame_is_drained_and_next_request_survives(self) -> None:
        source = io.StringIO("x" * (MAX_INPUT_FRAME_CHARS + 1) + "\n" + json.dumps(
            {"jsonrpc": "2.0", "id": 9, "method": "ping"}
        ) + "\n")
        output, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(0, LegacyMcpServer(self.fixture.runtime()).serve(source, output, stderr))
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual("MCP_FRAME_TOO_LARGE", responses[0]["error"]["data"]["code"])
        self.assertEqual({}, responses[1]["result"])
        self.assertEqual("", stderr.getvalue())

    def test_lone_surrogate_request_id_is_rejected_without_traceback(self) -> None:
        source = io.StringIO('{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n')
        output, stderr = io.StringIO(), io.StringIO()
        self.assertEqual(0, LegacyMcpServer(self.fixture.runtime()).serve(source, output, stderr))
        response = json.loads(output.getvalue())
        self.assertEqual(-32600, response["error"]["code"])
        self.assertIsNone(response["id"])
        self.assertEqual("", stderr.getvalue())

    def test_notifications_have_no_response_and_unknown_tool_is_invalid_params(self) -> None:
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "unknown/notification", "params": {"secret": "do-not-log"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "write_file", "arguments": {}}},
            ]
        )
        self.assertEqual([1, 2], [item["id"] for item in responses])
        self.assertEqual(-32602, responses[1]["error"]["code"])

    def test_tool_call_accepts_optional_meta_without_forwarding_it(self) -> None:
        class RecordingRuntime:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            def call(self, name, arguments, **kwargs):
                del kwargs
                self.calls.append((name, arguments))
                return {"content": [], "structuredContent": {"ok": True}}

        runtime = RecordingRuntime()
        arguments = {"package_id": PACKAGE_ID}
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "gptpro_package_info",
                        "arguments": arguments,
                        "_meta": {"progressToken": "must-not-be-forwarded"},
                    },
                },
            ],
            runtime=runtime,
        )
        self.assertTrue(responses[1]["result"]["structuredContent"]["ok"])
        self.assertEqual([("gptpro_package_info", arguments)], runtime.calls)

    def test_tool_call_accepts_omitted_arguments_as_empty_object(self) -> None:
        class RecordingRuntime:
            def __init__(self) -> None:
                self.arguments: list[dict[str, object]] = []

            def call(self, name, arguments, **kwargs):
                del name, kwargs
                self.arguments.append(arguments)
                return {"content": [], "structuredContent": {"ok": True}}

        runtime = RecordingRuntime()
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "gptpro_package_info"},
                },
            ],
            runtime=runtime,
        )
        self.assertTrue(responses[1]["result"]["structuredContent"]["ok"])
        self.assertEqual([{}], runtime.arguments)

    def test_tool_call_rejects_non_object_meta_and_task_augmentation(self) -> None:
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "gptpro_package_info",
                        "arguments": {},
                        "_meta": "not-an-object",
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "gptpro_package_info",
                        "arguments": {},
                        "task": {"ttl": 1},
                    },
                },
            ]
        )
        self.assertEqual([-32602, -32602], [item["error"]["code"] for item in responses[1:]])

    def test_valid_tool_domain_error_is_a_tool_result(self) -> None:
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "gptpro_repo_read",
                    "arguments": {"package_id": "wrong", "path": "src/a.py"},
                }},
            ]
        )
        result = responses[1]["result"]
        self.assertTrue(result["isError"])
        self.assertEqual("PACKAGE_MISMATCH", result["structuredContent"]["error"]["code"])
        self.assertNotIn(str(self.fixture.root), json.dumps(result))

    def test_cancellation_notification_suppresses_cancelled_response(self) -> None:
        class BlockingRuntime:
            def call(self, name, arguments, *, cancelled, request_id=None):
                del request_id
                del name, arguments
                self.started.set()
                cancelled.wait(2)
                raise CancelledError

            def __init__(self):
                self.started = threading.Event()

        runtime = BlockingRuntime()
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": "work", "method": "tools/call", "params": {
                    "name": "gptpro_repo_search",
                    "arguments": {"package_id": PACKAGE_ID, "query": "needle"},
                }},
                {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": "work"}},
            ],
            runtime=runtime,  # type: ignore[arg-type]
        )
        self.assertEqual([1], [item["id"] for item in responses])

    def test_internal_exception_stderr_is_sanitized(self) -> None:
        class FailingRuntime:
            def call(self, name, arguments, *, cancelled, request_id=None):
                del request_id
                del name, arguments, cancelled
                raise RuntimeError("/Users/private sk-secret-value")

        responses, _, stderr = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "gptpro_package_info", "arguments": {"package_id": PACKAGE_ID}
                }},
            ],
            runtime=FailingRuntime(),  # type: ignore[arg-type]
        )
        self.assertEqual(-32603, responses[1]["error"]["code"])
        self.assertEqual("gptpro-mcp: MCP_INTERNAL_ERROR\n", stderr)
        self.assertNotIn("private", stderr)

    def test_eof_is_clean_and_ping_works_before_initialize(self) -> None:
        responses, _, _ = self.transcript([
            {"jsonrpc": "2.0", "id": 0, "method": "ping"}
        ])
        self.assertEqual({}, responses[0]["result"])
        responses, raw, stderr = self.transcript([])
        self.assertEqual([], responses)
        self.assertEqual("", raw)
        self.assertEqual("", stderr)

    def test_second_inflight_tool_request_is_rejected_as_busy(self) -> None:
        class BlockingRuntime:
            def __init__(self) -> None:
                self.release = threading.Event()

            def call(self, name, arguments, *, cancelled, request_id=None):
                del name, arguments, request_id
                while not self.release.is_set():
                    if cancelled.wait(0.01):
                        raise CancelledError
                raise CancelledError

        runtime = BlockingRuntime()
        responses, _, _ = self.transcript(
            [
                self.initialize(),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0", "id": "first", "method": "tools/call",
                    "params": {"name": "gptpro_package_info", "arguments": {"package_id": PACKAGE_ID}},
                },
                {
                    "jsonrpc": "2.0", "id": "second", "method": "tools/call",
                    "params": {"name": "gptpro_package_info", "arguments": {"package_id": PACKAGE_ID}},
                },
                {
                    "jsonrpc": "2.0", "method": "notifications/cancelled",
                    "params": {"requestId": "first"},
                },
            ],
            runtime=runtime,  # type: ignore[arg-type]
        )
        self.assertEqual([1, "second"], [item["id"] for item in responses])
        self.assertEqual("MCP_SERVER_BUSY", responses[1]["error"]["data"]["code"])

    def test_duplicate_id_remains_reserved_until_success_response_flush(self) -> None:
        class CountingRuntime:
            def __init__(self) -> None:
                self.calls = 0

            def call(self, name, arguments, *, cancelled, request_id=None):
                del name, arguments, cancelled, request_id
                self.calls += 1
                return {"content": [], "structuredContent": {"ok": True}}

        class BlockingOutput(io.StringIO):
            def __init__(self) -> None:
                super().__init__()
                self.write_entered = threading.Event()
                self.release_write = threading.Event()
                self._blocked_once = False

            def write(self, value: str) -> int:
                if not self._blocked_once:
                    self._blocked_once = True
                    self.write_entered.set()
                    if not self.release_write.wait(5):
                        raise BrokenPipeError("timed out waiting for duplicate-id assertion")
                return super().write(value)

        class DecisionTrace:
            def __init__(self, output: BlockingOutput) -> None:
                self.output = output
                self.duplicate_decision = threading.Event()
                self.duplicate_outcome: str | None = None

            def record(self, **event) -> None:
                if (
                    self.output.write_entered.is_set()
                    and event.get("method") == "tools_call"
                    and event.get("stage") == "decision"
                ):
                    self.duplicate_outcome = event.get("outcome")
                    self.duplicate_decision.set()

        runtime = CountingRuntime()
        output = BlockingOutput()
        trace = DecisionTrace(output)
        server = LegacyMcpServer(runtime, max_workers=2, trace=trace)  # type: ignore[arg-type]
        server._output = output
        server._stderr = io.StringIO()
        server._initialized = True
        params = {
            "name": "gptpro_package_info",
            "arguments": {"package_id": PACKAGE_ID},
        }
        duplicate_errors: list[BaseException] = []

        def duplicate_request() -> None:
            try:
                server._request("same", "tools/call", params)
            except BaseException as exc:  # pragma: no cover - surfaced below
                duplicate_errors.append(exc)

        duplicate = threading.Thread(target=duplicate_request)
        try:
            server._request("same", "tools/call", params)
            self.assertTrue(output.write_entered.wait(2))
            with server._state_lock:
                self.assertEqual(1, len(server._inflight))
            duplicate.start()
            self.assertTrue(trace.duplicate_decision.wait(2))
            self.assertEqual("invalid_request", trace.duplicate_outcome)
            self.assertEqual(1, runtime.calls)
        finally:
            output.release_write.set()
            if duplicate.ident is not None:
                duplicate.join(2)
            server._executor.shutdown(wait=True, cancel_futures=False)

        self.assertFalse(duplicate.is_alive())
        self.assertEqual([], duplicate_errors)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(
            ["result", "error"],
            ["result" if "result" in item else "error" for item in responses],
        )
        self.assertEqual(-32600, responses[1]["error"]["code"])
        self.assertEqual(1, runtime.calls)


class EntrypointTests(unittest.TestCase):
    def test_isolated_bootstrap_can_import_exact_governance_module(self) -> None:
        script = SKILL_ROOT / "scripts/gptpro_mcp.py"
        governance = SKILL_ROOT / "scripts/gptpro.py"
        code = (
            "import runpy\n"
            "from pathlib import Path\n"
            f"runpy.run_path({str(script)!r}, run_name='gptpro_mcp_bootstrap_test')\n"
            "import gptpro\n"
            f"assert Path(gptpro.__file__).resolve() == Path({str(governance)!r}).resolve()\n"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                f"-Xpycache_prefix={os.devnull}",
                "-c",
                code,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_tunnel_credentials_are_scrubbed_before_runtime_imports(self) -> None:
        script = SKILL_ROOT / "scripts/gptpro_mcp.py"
        spec = importlib.util.spec_from_file_location("gptpro_mcp_entrypoint_test", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        secret_names = tuple(module._INHERITED_SECRET_ENV)
        environment = {name: f"secret-{index}" for index, name in enumerate(secret_names)}
        observations: list[dict[str, str | None]] = []
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("runtime.gptpro_mcp"):
                observations.append({key: os.environ.get(key) for key in secret_names})
            return original_import(name, globals, locals, fromlist, level)

        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("builtins.__import__", side_effect=guarded_import),
        ):
            runtime, lease, server_class, parent_shutdown_contract = (
                module._runtime_from_environment()
            )
        self.assertIsNone(lease)
        self.assertIsNotNone(runtime)
        self.assertIsNotNone(server_class)
        self.assertFalse(parent_shutdown_contract)
        self.assertTrue(observations)
        self.assertTrue(
            all(value is None for snapshot in observations for value in snapshot.values())
        )

    def test_active_entrypoint_records_sigterm_only_after_stdio_eof(self) -> None:
        script = SKILL_ROOT / "scripts/gptpro_mcp.py"
        with tempfile.TemporaryDirectory() as temporary:
            trace_root = Path(temporary).resolve()
            code = f"""
import importlib.util
import json
import sys
from pathlib import Path

script = Path({str(script)!r})
spec = importlib.util.spec_from_file_location("gptpro_mcp_signal_test", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

from runtime.gptpro_mcp.protocol import LegacyMcpServer
from runtime.gptpro_mcp.protocol_trace import ProtocolTrace, ProtocolTraceBinding

binding = ProtocolTraceBinding(
    package_id="signal-test",
    session_id_sha256="1" * 64,
    manifest_sha256="2" * 64,
    approval_event_sha256="3" * 64,
    archive_sha256="4" * 64,
    file_set_sha256="5" * 64,
    tool_schema_sha256="6" * 64,
    audit_header_sha256="7" * 64,
    tunnel_profile_sha256="8" * 64,
    tunnel_client_binary_sha256="9" * 64,
    mcp_target_sha256="a" * 64,
    mcp_runtime_tree_sha256="b" * 64,
)
trace = ProtocolTrace(Path({str(trace_root)!r}), binding)
trace.open_or_create()

class Runtime:
    def call(self, *args, **kwargs):
        raise AssertionError("no request is expected")

class Lease:
    def close(self):
        return None

class Server:
    def __init__(self, runtime):
        self.inner = LegacyMcpServer(runtime, trace=trace)

    def note_parent_shutdown(self):
        self.inner.note_parent_shutdown()
        sys.stderr.write("SIGNAL_OBSERVED\\n")
        sys.stderr.flush()

    def serve(self, input_stream, output_stream, stderr):
        stderr.write("READY\\n")
        stderr.flush()
        return self.inner.serve(input_stream, output_stream, stderr)

module._runtime_from_environment = lambda: (Runtime(), Lease(), Server, True)
returncode = module.serve()
summary = trace.verify()
print(json.dumps({{
    "closed": summary.closed,
    "close_reason": summary.close_reason,
    "event_count": summary.event_count,
}}))
raise SystemExit(returncode)
"""
            process = subprocess.Popen(
                [sys.executable, "-B", "-c", code],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            try:
                self.assertTrue(select.select([process.stderr], [], [], 5)[0])
                self.assertEqual("READY", process.stderr.readline().strip())
                process.send_signal(signal.SIGTERM)
                self.assertTrue(select.select([process.stderr], [], [], 5)[0])
                self.assertEqual("SIGNAL_OBSERVED", process.stderr.readline().strip())
                self.assertIsNotNone(process.stdin)
                process.stdin.close()
                self.assertEqual(0, process.wait(timeout=5))
                self.assertIsNotNone(process.stdout)
                result = json.loads(process.stdout.read())
                self.assertEqual(
                    {"closed": True, "close_reason": "parent_shutdown", "event_count": 0},
                    result,
                )
                self.assertEqual("", process.stderr.read())
            finally:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

    def test_help_has_no_runtime_side_effect(self) -> None:
        script = SKILL_ROOT / "scripts/gptpro_mcp.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("read-only MCP", result.stdout)

    def test_stdio_entrypoint_is_protocol_only_and_deny_all(self) -> None:
        script = SKILL_ROOT / "scripts/gptpro_mcp.py"
        transcript = "\n".join(
            json.dumps(item)
            for item in (
                ProtocolTests.initialize("2025-06-18"),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "gptpro_package_info",
                        "arguments": {"package_id": PACKAGE_ID},
                    },
                },
            )
        ) + "\n"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "serve"],
            input=transcript,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([1, 2], [item["id"] for item in responses])
        self.assertEqual("2025-06-18", responses[0]["result"]["protocolVersion"])
        denied = responses[1]["result"]
        self.assertTrue(denied["isError"])
        self.assertEqual("NO_ACTIVE_PACKAGE", denied["structuredContent"]["error"]["code"])


if __name__ == "__main__":
    unittest.main()

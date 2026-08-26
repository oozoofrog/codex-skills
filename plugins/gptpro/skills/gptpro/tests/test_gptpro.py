from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gptpro.py"
STRUCTURE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_structure.py"


def load_gptpro_module():
    spec = importlib.util.spec_from_file_location("gptpro_cli_scanner_tests", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GPTPRO = load_gptpro_module()


class GptProCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.git("add", "src/main.py", "README.md")
        self.git("commit", "-m", "fixture")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()

        self.secret_value = "sk-" + "a" * 32
        (self.repo / ".env").write_text("SAFE_NAME=still-excluded\n", encoding="utf-8")
        (self.repo / "secret.txt").write_text(f"OPENAI_API_KEY={self.secret_value}\n", encoding="utf-8")
        self.output_root = self.root / "handoffs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def run_cli(
        self, *args: str, expected: int = 0, umask: int = -1
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            umask=umask,
        )
        self.assertEqual(expected, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def configure_github_remote(self, *, pr_number: int | None = None) -> Path:
        remote = self.root / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        github_url = "https://github.com/example/repository.git"
        self.git("config", "remote.origin.url", github_url)
        self.git("config", f"url.{remote.resolve().as_uri()}.insteadOf", github_url)
        self.git("push", "origin", "HEAD:refs/heads/main")
        if pr_number is not None:
            self.git("push", "origin", f"HEAD:refs/pull/{pr_number}/head")
        return remote

    def prepare(self, mode: str = "review", *extra: str) -> Path:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            mode,
            "--task",
            "Consult on this repository fixture.",
            "--output-root",
            str(self.output_root),
            *extra,
        )
        return Path(json.loads(result.stdout)["handoff_dir"])

    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, value: dict) -> None:
        path.write_bytes(GPTPRO.pretty_json_bytes(value))

    def rebind_prepared_package(self, handoff: Path) -> dict:
        """Rebind ordinary integrity fields so semantic tamper tests reach verification."""

        manifest_path = handoff / "manifest.json"
        manifest = self.load(manifest_path)
        artifacts = manifest["artifacts"]
        hashes = manifest["hashes"]
        for artifact in ("prompt", "context", "archive", "paste_payload"):
            name = artifacts.get(artifact)
            if isinstance(name, str):
                hashes[f"{artifact}_sha256"] = GPTPRO.sha256_file(handoff / name)
        for outbound in manifest["transport"]["outbound_artifacts"]:
            artifact = outbound["artifact"]
            path = handoff / artifacts[artifact]
            outbound["bytes"] = path.stat().st_size
            outbound["sha256"] = hashes[f"{artifact}_sha256"]
        if "candidate_paste_bytes" in manifest["transport"]:
            manifest["transport"]["candidate_paste_bytes"] = (
                handoff / artifacts["paste_payload"]
            ).stat().st_size
        self.write_json(manifest_path, manifest)
        manifest_hash = GPTPRO.sha256_file(manifest_path)

        state_path = handoff / "state.json"
        state = self.load(state_path)
        state["artifact_hashes"] = {
            "manifest_sha256": manifest_hash,
            **{
                f"{artifact}_sha256": hashes[f"{artifact}_sha256"]
                for artifact in ("prompt", "archive", "context", "paste_payload")
                if artifact in artifacts
            },
        }
        self.write_json(state_path, state)

        receipt_path = handoff / "receipt.json"
        receipt = self.load(receipt_path)
        self.assertEqual(["prepared"], [event["type"] for event in receipt["events"]])
        receipt["events"][0]["data"] = GPTPRO.prepared_receipt_data(
            manifest, manifest_hash
        )
        receipt["events"][0]["event_hash"] = GPTPRO.event_hash(receipt["events"][0])
        self.write_json(receipt_path, receipt)
        return manifest

    def replace_zip_member(self, archive_path: Path, member: str, content: bytes) -> None:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = [(info, archive.read(info.filename)) for info in archive.infolist()]
        with zipfile.ZipFile(archive_path, "w") as archive:
            for info, original in members:
                archive.writestr(info, content if info.filename == member else original)

    def approve_and_submit(self, handoff: Path, *, thread_url: str | None = None) -> dict:
        manifest = self.load(handoff / "manifest.json")
        if thread_url is None:
            thread_url = f"https://chatgpt.com/c/{manifest['package_id']}"
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        github = manifest["transport"].get("github")
        github_args = (
            [
                "--observed-github-repository",
                github["repository"],
                "--observed-github-commit",
                github["commit_sha"],
            ]
            if github
            else []
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--thread-url",
            thread_url,
            "--confirm-new-general-chat",
            "--confirm-sent",
            *github_args,
        )
        return manifest

    def test_prepare_help_explains_supplement_transport_and_paste_limit(self) -> None:
        result = self.run_cli("prepare", "--help")
        normalized = " ".join(result.stdout.split())
        self.assertIn("--supplement makes it bounded paste-only", normalized)
        self.assertIn("hard limit on the complete paste payload", normalized)

    def test_prepare_records_git_and_excludes_detected_secrets_without_values(self) -> None:
        handoff = self.prepare()
        manifest_text = (handoff / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)

        self.assertEqual(self.head, manifest["git"]["head_sha"])
        self.assertFalse(manifest["git"]["clean"])
        self.assertIn("src/main.py", {item["path"] for item in manifest["files"]})
        finding_paths = {item["path"] for item in manifest["security_findings"]}
        self.assertIn(".env", finding_paths)
        self.assertIn("secret.txt", finding_paths)
        self.assertNotIn(self.secret_value, manifest_text)
        self.assertEqual(0, self.run_cli("verify", "--handoff-dir", str(handoff)).returncode)

    def test_paste_packages_external_supplement_without_source_path_disclosure(self) -> None:
        supplement = self.root / "private requirements.md"
        content = b"# Requirements\r\nPreserve exact bytes without browser upload.\r\n"
        supplement.write_bytes(content)
        supplement.chmod(0o600)

        handoff = self.prepare(
            "review",
            "--transport",
            "paste",
            "--supplement",
            f"requirements={supplement.resolve()}",
        )
        manifest = self.load(handoff / "manifest.json")
        entry = manifest["supplements"][0]
        self.assertEqual("requirements", entry["label"])
        self.assertEqual(len(content), entry["size"])
        self.assertEqual(GPTPRO.sha256_bytes(content), entry["sha256"])
        self.assertEqual(
            GPTPRO.sha256_bytes(
                GPTPRO.canonical_json_bytes(
                    [{"label": "requirements", "size": len(content), "sha256": entry["sha256"]}]
                )
            ),
            manifest["hashes"]["supplement_set_sha256"],
        )
        context = (handoff / manifest["artifacts"]["context"]).read_bytes()
        self.assertIn(content, context)
        self.assertIn(b"GPTPRO_SUPPLEMENT_BEGIN:", context)
        with zipfile.ZipFile(handoff / manifest["artifacts"]["archive"], "r") as archive:
            self.assertEqual(content, archive.read("_gptpro/supplements/requirements.txt"))
        source_path = str(supplement.resolve()).encode("utf-8")
        for artifact in handoff.iterdir():
            if artifact.is_file():
                self.assertNotIn(source_path, artifact.read_bytes(), artifact.name)
        prepared = self.load(handoff / "receipt.json")["events"][0]["data"]
        self.assertEqual(
            manifest["hashes"]["supplement_set_sha256"],
            prepared["supplement_set_sha256"],
        )
        status = json.loads(
            self.run_cli("status", "--handoff-dir", str(handoff), "--json").stdout
        )
        self.assertEqual(
            [{"label": "requirements", "size": len(content), "sha256": entry["sha256"]}],
            status["supplemental_documents"],
        )
        supplement.write_text("changed after prepare\n", encoding="utf-8")
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_supplement_auto_uses_only_bounded_paste_and_rejects_other_transports(self) -> None:
        self.configure_github_remote()
        supplement = self.root / "notes.txt"
        supplement.write_text("local-only note\n", encoding="utf-8")
        supplement.chmod(0o600)

        auto = self.prepare("ask", "--supplement", f"notes={supplement.resolve()}")
        manifest = self.load(auto / "manifest.json")
        self.assertEqual("paste", manifest["transport"]["resolved"])
        self.assertNotIn("github", manifest["transport"])
        self.assertTrue(any("supplemental" in item for item in manifest["warnings"]))

        for transport in ("github", "text-file", "mcp-read"):
            with self.subTest(transport=transport):
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "ask",
                    "--task",
                    "Reject an unsupported supplemental transport.",
                    "--transport",
                    transport,
                    "--supplement",
                    f"notes={supplement.resolve()}",
                    "--output-root",
                    str(self.root / f"rejected-{transport}"),
                    expected=2,
                )
                self.assertIn("cannot represent this external document contract", result.stderr)

        oversized = self.root / "oversized.txt"
        oversized.write_bytes(b"x" * (GPTPRO.DEFAULT_MAX_PASTE_BYTES + 1))
        oversized.chmod(0o600)
        rejected = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--task",
            "Reject a browser upload fallback.",
            "--supplement",
            f"oversized={oversized.resolve()}",
            "--output-root",
            str(self.root / "oversized-output"),
            expected=2,
        )
        self.assertIn("mcp-research", rejected.stderr)
        self.assertFalse((self.root / "oversized-output").exists())

    def test_supplement_rejects_unsafe_or_secret_external_inputs(self) -> None:
        secret = self.root / "secret supplement.txt"
        secret.write_text(f"OPENAI_API_KEY={self.secret_value}\n", encoding="utf-8")
        secret.chmod(0o600)
        invalid = self.root / "invalid.bin"
        invalid.write_bytes(b"\xff\xfe\x00")
        invalid.chmod(0o600)
        symlink = self.root / "linked.txt"
        symlink.symlink_to(invalid)

        for label, specification, expected_text in (
            ("secret", f"requirements={secret.resolve()}", "secret-like material"),
            ("invalid", f"invalid={invalid.resolve()}", "NUL or binary data"),
            ("symlink", f"linked={symlink}", "symlink traversal"),
            ("relative", "relative=not-absolute.txt", "absolute path"),
        ):
            with self.subTest(case=label):
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "ask",
                    "--task",
                    "Reject unsafe supplemental input.",
                    "--transport",
                    "paste",
                    "--supplement",
                    specification,
                    "--output-root",
                    str(self.root / f"unsafe-{label}"),
                    expected=2,
                )
                self.assertIn(expected_text, result.stderr)
                self.assertNotIn(self.secret_value, result.stdout + result.stderr)

    def test_supplement_source_path_cannot_be_reflected_into_outbound_task(self) -> None:
        for index, filename in enumerate(("private-location.md", 'quoted"\nlocation.md')):
            with self.subTest(filename=filename):
                supplement = self.root / filename
                supplement.write_text("approved body\n", encoding="utf-8")
                supplement.chmod(0o600)
                source_path = str(supplement.resolve())
                output_root = self.root / f"reflected-path-output-{index}"
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "ask",
                    "--task",
                    f"Read the source at {source_path}.",
                    "--transport",
                    "paste",
                    "--supplement",
                    f"requirements={source_path}",
                    "--output-root",
                    str(output_root),
                    expected=2,
                )
                self.assertIn("refer to the safe supplement LABEL", result.stderr)
                self.assertNotIn(source_path, result.stdout + result.stderr)
                self.assertFalse(output_root.exists())

    def test_supplement_source_path_reflection_uses_case_and_unicode_normalization(self) -> None:
        supplement = self.root / "Privaté-Requirements.md"
        supplement.write_text("approved body\n", encoding="utf-8")
        supplement.chmod(0o600)
        source_path = str(supplement.resolve())
        reflected_variants = {
            source_path.swapcase(),
            unicodedata.normalize("NFD", source_path),
        }
        self.assertTrue(any(value != source_path for value in reflected_variants))

        for index, reflected in enumerate(sorted(reflected_variants)):
            with self.subTest(reflected=reflected):
                output_root = self.root / f"normalized-reflection-{index}"
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "ask",
                    "--task",
                    f"Read the source at {reflected}.",
                    "--transport",
                    "paste",
                    "--supplement",
                    f"requirements={source_path}",
                    "--output-root",
                    str(output_root),
                    expected=2,
                )
                self.assertIn("safe supplement LABEL", result.stderr)
                self.assertFalse(output_root.exists())

    def test_supplement_input_requires_strict_utf8_owner_controlled_unlinked_regular_file(self) -> None:
        invalid_utf8 = self.root / "invalid-utf8.txt"
        invalid_utf8.write_bytes(b"plain-prefix-\xff\xfe")
        invalid_utf8.chmod(0o600)
        shared_writable = self.root / "shared-writable.txt"
        shared_writable.write_text("approved body\n", encoding="utf-8")
        shared_writable.chmod(0o620)
        hardlinked = self.root / "hardlinked.txt"
        hardlinked.write_text("approved body\n", encoding="utf-8")
        hardlinked.chmod(0o600)
        os.link(hardlinked, self.root / "hardlinked-copy.txt")

        for label, source, message in (
            ("invalid", invalid_utf8, "strict UTF-8"),
            ("mode", shared_writable, "unsafe ownership"),
            ("link", hardlinked, "unsafe ownership"),
        ):
            with self.subTest(case=label), self.assertRaisesRegex(
                GPTPRO.HandoffError, message
            ):
                GPTPRO.read_supplements([f"{label}={source.resolve()}"])

    def test_supplement_input_fails_closed_without_posix_owner_open_capabilities(self) -> None:
        source = self.root / "platform-capability.txt"
        source.write_text("approved body\n", encoding="utf-8")
        source.chmod(0o600)
        for patcher in (
            mock.patch.object(GPTPRO, "_OPEN_SUPPORTS_DIR_FD", False),
            mock.patch.object(GPTPRO.os, "getuid", None),
        ):
            with patcher, self.assertRaisesRegex(
                GPTPRO.HandoffError, "POSIX owner and directory-fd support"
            ):
                GPTPRO.read_supplements([f"platform={source.resolve()}"])

    def test_supplement_input_rejects_file_changed_during_descriptor_read(self) -> None:
        source = self.root / "racing-input.txt"
        source.write_bytes(b"approved body A\n")
        source.chmod(0o600)
        real_read = GPTPRO.os.read
        changed = False

        def racing_read(descriptor: int, maximum: int) -> bytes:
            nonlocal changed
            chunk = real_read(descriptor, maximum)
            if chunk and not changed:
                changed = True
                source.write_bytes(b"approved body B\n")
                source.chmod(0o600)
            return chunk

        with (
            mock.patch.object(GPTPRO.os, "read", side_effect=racing_read),
            self.assertRaisesRegex(GPTPRO.HandoffError, "changed while it was read"),
        ):
            GPTPRO.read_supplements([f"racing={source.resolve()}"])
        self.assertTrue(changed)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_supplement_fifo_is_rejected_without_blocking(self) -> None:
        fifo = self.root / "supplement.fifo"
        os.mkfifo(fifo, 0o600)
        arguments = [
            sys.executable,
            str(SCRIPT),
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--task",
            "Reject a non-regular supplemental input.",
            "--transport",
            "paste",
            "--supplement",
            f"fifo={fifo.resolve()}",
            "--output-root",
            str(self.root / "fifo-output"),
        ]
        try:
            result = subprocess.run(
                arguments,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=3,
            )
        except subprocess.TimeoutExpired as exc:
            self.fail(f"FIFO open blocked past the bounded timeout: {exc}")
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("unsafe ownership", result.stderr)

    def test_supplement_missing_tilde_user_fails_without_traceback(self) -> None:
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--task",
            "Reject an unresolved home-directory reference.",
            "--transport",
            "paste",
            "--supplement",
            "requirements=~gptpro-user-that-must-not-exist/document.txt",
            "--output-root",
            str(self.root / "missing-home-output"),
            expected=2,
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(str(SCRIPT), result.stderr)
        self.assertFalse((self.root / "missing-home-output").exists())

    def test_supplement_count_file_and_total_byte_boundaries(self) -> None:
        tiny_files: list[Path] = []
        for index in range(GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILES + 1):
            path = self.root / f"tiny-{index:02d}.txt"
            path.write_bytes(b"x")
            path.chmod(0o600)
            tiny_files.append(path)
        accepted_tiny = [
            f"tiny-{index}={path.resolve()}"
            for index, path in enumerate(tiny_files[:-1])
        ]
        self.assertEqual(
            GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILES,
            len(GPTPRO.read_supplements(accepted_tiny)),
        )
        with self.assertRaisesRegex(GPTPRO.HandoffError, "Too many"):
            GPTPRO.read_supplements(
                [
                    f"tiny-{index}={path.resolve()}"
                    for index, path in enumerate(tiny_files)
                ]
            )

        full_files: list[Path] = []
        for index in range(
            GPTPRO.DEFAULT_MAX_SUPPLEMENT_TOTAL_BYTES
            // GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILE_BYTES
        ):
            path = self.root / f"full-{index}.txt"
            path.write_bytes(b"x" * GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILE_BYTES)
            path.chmod(0o600)
            full_files.append(path)
        accepted_full = [
            f"full-{index}={path.resolve()}"
            for index, path in enumerate(full_files)
        ]
        self.assertEqual(
            GPTPRO.DEFAULT_MAX_SUPPLEMENT_TOTAL_BYTES,
            sum(item.size for item in GPTPRO.read_supplements(accepted_full)),
        )

        over_file = self.root / "over-file.txt"
        over_file.write_bytes(b"x" * (GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILE_BYTES + 1))
        over_file.chmod(0o600)
        with self.assertRaisesRegex(GPTPRO.HandoffError, "unsafe ownership"):
            GPTPRO.read_supplements([f"over={over_file.resolve()}"])

        over_total = self.root / "over-total.txt"
        over_total.write_bytes(b"x")
        over_total.chmod(0o600)
        with self.assertRaisesRegex(GPTPRO.HandoffError, "total-byte limit"):
            GPTPRO.read_supplements([*accepted_full, f"over={over_total.resolve()}"])

    def test_supplement_archive_or_manifest_tampering_is_detected(self) -> None:
        supplement = self.root / "review.txt"
        supplement.write_text("immutable review notes\n", encoding="utf-8")
        supplement.chmod(0o600)
        handoff = self.prepare(
            "review",
            "--transport",
            "paste",
            "--supplement",
            f"review={supplement.resolve()}",
        )
        manifest_path = handoff / "manifest.json"
        manifest = self.load(manifest_path)
        manifest["supplements"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        rejected = self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)
        self.assertIn("supplemental document set hash mismatch", rejected.stderr)

    def test_schema2_context_body_mismatch_rejects_after_integrity_rebinding(self) -> None:
        supplement = self.root / "body-binding.txt"
        original = b"archive body A\r\n"
        replacement = b"context body B\r\n"
        self.assertEqual(len(original), len(replacement))
        supplement.write_bytes(original)
        supplement.chmod(0o600)
        handoff = self.prepare(
            "review",
            "--transport",
            "paste",
            "--supplement",
            f"binding={supplement.resolve()}",
        )
        manifest = self.load(handoff / "manifest.json")
        context_path = handoff / manifest["artifacts"]["context"]
        context = context_path.read_bytes()
        self.assertEqual(1, context.count(original))
        context_path.write_bytes(context.replace(original, replacement, 1))
        prompt = (handoff / manifest["artifacts"]["prompt"]).read_bytes().decode("utf-8")
        changed_context = context_path.read_bytes().decode("utf-8")
        paste_path = handoff / manifest["artifacts"]["paste_payload"]
        paste_path.write_bytes(
            GPTPRO.render_paste_payload(prompt, changed_context).encode("utf-8")
        )
        self.rebind_prepared_package(handoff)

        rejected = self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)
        self.assertIn("context", rejected.stderr.lower())

    def test_schema2_supplement_manifest_entry_rejects_extra_keys(self) -> None:
        supplement = self.root / "exact-entry.txt"
        supplement.write_text("exact manifest entry\n", encoding="utf-8")
        supplement.chmod(0o600)
        handoff = self.prepare(
            "review",
            "--transport",
            "paste",
            "--supplement",
            f"exact={supplement.resolve()}",
        )
        manifest_path = handoff / "manifest.json"
        manifest = self.load(manifest_path)
        manifest["supplements"][0]["source_path"] = "/private/reflected.txt"
        archive_path = handoff / manifest["artifacts"]["archive"]
        with zipfile.ZipFile(archive_path, "r") as archive:
            internal = json.loads(
                archive.read("_gptpro/file-manifest.json").decode("utf-8")
            )
        internal["supplements"][0]["source_path"] = "/private/reflected.txt"
        internal_bytes = GPTPRO.pretty_json_bytes(internal)
        self.replace_zip_member(
            archive_path, "_gptpro/file-manifest.json", internal_bytes
        )
        manifest["hashes"]["internal_manifest_sha256"] = GPTPRO.sha256_bytes(
            internal_bytes
        )
        self.write_json(manifest_path, manifest)
        self.rebind_prepared_package(handoff)

        rejected = self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)
        self.assertIn("supplement", rejected.stderr.lower())

    def test_empty_schema2_package_rejects_tampered_supplement_totals_and_limits(self) -> None:
        for field, value in (
            ("supplemental_documents", 1),
            ("supplemental_bytes", 1),
            ("max_supplement_files", GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILES - 1),
            (
                "max_supplement_file_bytes",
                GPTPRO.DEFAULT_MAX_SUPPLEMENT_FILE_BYTES - 1,
            ),
            (
                "max_supplement_total_bytes",
                GPTPRO.DEFAULT_MAX_SUPPLEMENT_TOTAL_BYTES - 1,
            ),
        ):
            with self.subTest(field=field):
                handoff = self.prepare("review", "--transport", "paste")
                manifest_path = handoff / "manifest.json"
                manifest = self.load(manifest_path)
                target = manifest["totals"] if field.startswith("supplemental_") else manifest["limits"]
                target[field] = value
                self.write_json(manifest_path, manifest)
                self.rebind_prepared_package(handoff)
                rejected = self.run_cli(
                    "verify", "--handoff-dir", str(handoff), expected=2
                )
                self.assertIn("supplement", rejected.stderr.lower())

    def test_schema2_supplement_approval_is_cross_bound_to_state_receipt_and_manifest(self) -> None:
        supplement = self.root / "approval.txt"
        supplement.write_text("approval-bound document\n", encoding="utf-8")
        supplement.chmod(0o600)
        handoff = self.prepare(
            "review",
            "--transport",
            "paste",
            "--supplement",
            f"approval={supplement.resolve()}",
        )
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        state_path = handoff / "state.json"
        receipt_path = handoff / "receipt.json"
        original_state = self.load(state_path)
        original_receipt = self.load(receipt_path)
        self.run_cli("verify", "--handoff-dir", str(handoff))

        def write(value: dict, path: Path) -> None:
            path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        for name, mutate, expected_error in (
            (
                "missing-state",
                lambda state, receipt: state.__setitem__("approval", None),
                "approval state is missing",
            ),
            (
                "manifest-hash",
                lambda state, receipt: state["approval"].__setitem__(
                    "manifest_sha256", "0" * 64
                ),
                "differs from the manifest",
            ),
            (
                "outbound-hash",
                lambda state, receipt: state["approval"]["outbound_artifacts"][0].__setitem__(
                    "sha256", "0" * 64
                ),
                "differs from the manifest",
            ),
            (
                "receipt-state",
                lambda state, receipt: receipt["events"][1]["data"].__setitem__(
                    "approved_by", "different-user"
                ),
                "receipt chain",
            ),
        ):
            with self.subTest(case=name):
                state = copy.deepcopy(original_state)
                receipt = copy.deepcopy(original_receipt)
                mutate(state, receipt)
                if name in {"manifest-hash", "outbound-hash"}:
                    receipt["events"][1]["data"] = copy.deepcopy(state["approval"])
                if name in {"manifest-hash", "outbound-hash", "receipt-state"}:
                    receipt["events"][1]["event_hash"] = GPTPRO.event_hash(
                        receipt["events"][1]
                    )
                write(state, state_path)
                write(receipt, receipt_path)
                result = self.run_cli(
                    "verify", "--handoff-dir", str(handoff), expected=2
                )
                self.assertIn(expected_error, result.stderr)

        write(original_state, state_path)
        write(original_receipt, receipt_path)
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_json_boundaries_normalize_surrogates_and_excessive_depth(self) -> None:
        surrogate = json.loads(r'{"value":"\ud800"}')
        receipt_event = {
            "sequence": 1,
            "timestamp": "2026-08-22T00:00:00Z",
            "type": "prepared",
            "data": surrogate,
            "previous_event_hash": None,
            "event_hash": "0" * 64,
        }
        for label, action in (
            ("canonical", lambda: GPTPRO.canonical_json_bytes(surrogate)),
            ("pretty", lambda: GPTPRO.pretty_json_bytes(surrogate)),
            ("receipt-hash", lambda: GPTPRO.event_hash(receipt_event)),
        ):
            with self.subTest(boundary=label), self.assertRaises(GPTPRO.HandoffError):
                action()

        artifact = self.root / "surrogate.json"
        artifact.write_text(r'{"value":"\ud800"}', encoding="utf-8")
        with self.assertRaises(GPTPRO.HandoffError):
            GPTPRO.load_json(artifact)

        nested: object = 0
        for _ in range(GPTPRO.MAX_JSON_NESTING_DEPTH + 1):
            nested = [nested]
        with self.assertRaises(GPTPRO.HandoffError):
            GPTPRO.canonical_json_bytes({"nested": nested})

        receipt = GPTPRO.new_receipt(
            "package-one", {"manifest_sha256": "0" * 64}, schema_version=2
        )
        receipt["unexpected_nested_value"] = nested
        with self.assertRaises(GPTPRO.HandoffError):
            GPTPRO.receipt_with_event(receipt, "approved", {})

    def test_schema3_handoff_and_all_artifacts_are_owner_only_under_common_umasks(self) -> None:
        tunnel_id = self.root / "tunnel-id"
        tunnel_id.write_text("tunnel_" + "34567890abcdef12" * 2, encoding="utf-8")
        tunnel_id.chmod(0o600)
        for process_umask in (0o022, 0o002):
            with self.subTest(umask=oct(process_umask)):
                output = self.root / f"handoffs-{process_umask:o}"
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    "review",
                    "--task",
                    "Verify private package modes.",
                    "--transport",
                    "mcp-read",
                    "--output-root",
                    str(output),
                    "--tunnel-runtime-alias",
                    "permission-test",
                    "--tunnel-id-ref",
                    f"file:{tunnel_id}",
                    "--chatgpt-app-name",
                    "GPT Pro Repository Reader",
                    "--chatgpt-workspace-label",
                    "Permission Test Workspace",
                    umask=process_umask,
                )
                handoff = Path(json.loads(result.stdout)["handoff_dir"])
                self.assertEqual(0o700, handoff.stat().st_mode & 0o777)
                artifacts = [path for path in handoff.iterdir() if path.is_file()]
                self.assertTrue(artifacts)
                self.assertTrue(
                    all((path.stat().st_mode & 0o777) == 0o600 for path in artifacts),
                    {path.name: oct(path.stat().st_mode & 0o777) for path in artifacts},
                )
                self.run_cli("verify", "--handoff-dir", str(handoff))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "requires openat")
    def test_scan_rejects_final_component_symlink_swap_without_reading_outside_file(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text(f"OPENAI_API_KEY={self.secret_value}\n", encoding="utf-8")
        original = self.repo / "README.md"
        backup = self.repo / "README.original"
        real_open = os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if dir_fd is not None and path == "README.md" and not swapped:
                swapped = True
                original.rename(backup)
                original.symlink_to(outside)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(GPTPRO.os, "open", side_effect=swapping_open):
            scan = GPTPRO.scan_repository(
                self.repo,
                include_patterns=[],
                exclude_patterns=[],
                file_list_entries=[],
                max_files=100,
                max_bytes=1024 * 1024,
                max_file_bytes=1024 * 1024,
            )

        self.assertTrue(swapped)
        self.assertNotIn("README.md", {item.path for item in scan["included"]})
        self.assertIn(
            {"path": "README.md", "reason": "symlink"},
            scan["excluded"],
        )
        self.assertNotIn("README.md", {item["path"] for item in scan["security"]})

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "requires openat")
    def test_scan_rejects_intermediate_component_symlink_swap_without_reading_outside_file(self) -> None:
        outside = self.root / "outside-src"
        outside.mkdir()
        (outside / "main.py").write_text(
            f"OPENAI_API_KEY={self.secret_value}\n",
            encoding="utf-8",
        )
        original = self.repo / "src"
        backup = self.repo / "src.original"
        real_open = os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if dir_fd is not None and path == "src" and not swapped:
                swapped = True
                original.rename(backup)
                original.symlink_to(outside, target_is_directory=True)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(GPTPRO.os, "open", side_effect=swapping_open):
            scan = GPTPRO.scan_repository(
                self.repo,
                include_patterns=[],
                exclude_patterns=[],
                file_list_entries=[],
                max_files=100,
                max_bytes=1024 * 1024,
                max_file_bytes=1024 * 1024,
            )

        self.assertTrue(swapped)
        self.assertNotIn("src/main.py", {item.path for item in scan["included"]})
        self.assertIn(
            {"path": "src/main.py", "reason": "unreadable"},
            scan["excluded"],
        )
        self.assertNotIn("src/main.py", {item["path"] for item in scan["security"]})

    def test_init_previews_then_applies_local_git_exclude_idempotently(self) -> None:
        preview = json.loads(
            self.run_cli("init", "--repo", str(self.repo)).stdout
        )
        self.assertFalse(preview["applied"])
        self.assertFalse(preview["ready"])
        self.assertEqual(
            {"create-directory", "append-ignore-entry"},
            {item["action"] for item in preview["actions"]},
        )
        self.assertFalse((self.repo / ".gptpro" / "handoffs").exists())

        applied = json.loads(
            self.run_cli("init", "--repo", str(self.repo), "--apply").stdout
        )
        self.assertTrue(applied["applied"])
        self.assertTrue(applied["ready"])
        self.assertTrue(applied["ignore_effective"])
        self.assertTrue((self.repo / ".gptpro" / "handoffs").is_dir())
        exclude_raw = self.git("rev-parse", "--git-path", "info/exclude").stdout.strip()
        exclude_path = Path(exclude_raw)
        if not exclude_path.is_absolute():
            exclude_path = self.repo / exclude_path
        exclude_text = exclude_path.read_text(encoding="utf-8")
        self.assertEqual(1, exclude_text.count(".gptpro/"))
        self.assertNotIn(".gptpro", self.git("status", "--porcelain=v1").stdout)

        repeated = json.loads(
            self.run_cli("init", "--repo", str(self.repo), "--apply").stdout
        )
        self.assertTrue(repeated["ready"])
        self.assertEqual([], repeated["changes"])
        self.assertEqual(1, exclude_path.read_text(encoding="utf-8").count(".gptpro/"))

    def test_init_can_write_repository_gitignore_when_explicitly_selected(self) -> None:
        result = json.loads(
            self.run_cli(
                "init",
                "--repo",
                str(self.repo),
                "--ignore-scope",
                "repository",
                "--apply",
            ).stdout
        )

        self.assertTrue(result["ready"])
        self.assertEqual((self.repo / ".gitignore").resolve(), Path(result["ignore_target"]))
        gitignore = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("# gptpro local handoff artifacts\n.gptpro/\n", gitignore)
        self.assertIn("?? .gitignore", self.git("status", "--porcelain=v1").stdout)

    def test_init_external_output_needs_no_git_ignore_change(self) -> None:
        external = self.root / "external-handoffs"
        result = json.loads(
            self.run_cli(
                "init",
                "--repo",
                str(self.repo),
                "--output-root",
                str(external),
                "--apply",
            ).stdout
        )

        self.assertTrue(result["ready"])
        self.assertFalse(result["output_inside_repo"])
        self.assertIsNone(result["ignore_target"])
        self.assertEqual(["create-directory"], [item["action"] for item in result["changes"]])
        self.assertTrue(external.is_dir())

    def test_prepare_warns_until_default_output_is_git_ignored(self) -> None:
        first = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "ask",
            "--task",
            "First-use warning check.",
        )
        first_manifest = self.load(Path(json.loads(first.stdout)["handoff_dir"]) / "manifest.json")
        self.assertTrue(any("not Git-ignored" in item for item in first_manifest["warnings"]))

        self.run_cli("init", "--repo", str(self.repo), "--apply")
        second = json.loads(
            self.run_cli(
                "prepare",
                "--repo",
                str(self.repo),
                "--mode",
                "ask",
                "--task",
                "Configured warning check.",
                "--dry-run",
            ).stdout
        )
        self.assertFalse(any("not Git-ignored" in item for item in second["warnings"]))

    def test_all_modes_support_dry_run(self) -> None:
        for mode in ("plan", "ask", "review", "debug", "architecture"):
            with self.subTest(mode=mode):
                result = self.run_cli(
                    "prepare",
                    "--repo",
                    str(self.repo),
                    "--mode",
                    mode,
                    "--task",
                    "Bounded question.",
                    "--dry-run",
                )
                payload = json.loads(result.stdout)
                self.assertEqual(self.head, payload["git_head_sha"])
                self.assertGreater(payload["included_files"], 0)
                self.assertIn(payload["transport_resolved"], ("paste", "text-file"))

    def test_auto_transport_uses_paste_for_small_payload(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)

        self.assertEqual("auto", manifest["transport"]["requested"])
        self.assertEqual("paste", manifest["transport"]["resolved"])
        self.assertEqual(["paste_payload"], [item["artifact"] for item in status["outbound_paths"]])
        self.assertIsNotNone(status["paste_payload_path"])
        self.assertNotIn(
            status["local_audit_archive_path"],
            {item["path"] for item in status["outbound_paths"]},
        )
        self.assertFalse(status["human_takeover"]["available"])
        self.assertEqual([], status["human_takeover"]["reasons"])

    def test_human_handoff_is_read_only_and_phase_aware(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        before_state = (handoff / "state.json").read_bytes()
        before_receipt = (handoff / "receipt.json").read_bytes()

        result = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "manual-transport",
                "--details",
                "Chrome control is unavailable.",
            ).stdout
        )

        self.assertEqual("human_action_required", result["status"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["state_unchanged"])
        self.assertEqual("approved", result["phase"])
        self.assertEqual("paste", result["transport"])
        self.assertEqual("Chrome control is unavailable.", result["observed_blocker_details"])
        self.assertEqual(["sent", "not-sent", "unknown"], result["resume"]["allowed_outcomes"])
        self.assertFalse(result["resume"]["automatic_retry_allowed"])
        instructions = "\n".join(result["human_steps"] + result["return_with"])
        self.assertIn("zero prior user or assistant turns", instructions)
        self.assertIn("empty new general Chat", instructions)
        self.assertIn("--confirm-new-general-chat", result["resume"]["on_sent"])
        self.assertEqual(
            [manifest["transport"]["outbound_artifacts"][0]["sha256"]],
            [item["sha256"] for item in result["outbound_paths"]],
        )
        self.assertEqual(before_state, (handoff / "state.json").read_bytes())
        self.assertEqual(before_receipt, (handoff / "receipt.json").read_bytes())

        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertTrue(status["human_takeover"]["available"])
        self.assertIn("manual-transport", status["human_takeover"]["reasons"])
        self.assertNotIn("file-selection", status["human_takeover"]["reasons"])

    def test_text_file_human_handoff_lists_only_approved_attachment(self) -> None:
        handoff = self.prepare("review", "--transport", "text-file")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        result = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "file-selection",
            ).stdout
        )

        attachment_paths = [item["path"] for item in result["outbound_paths"] if item["role"] == "attachment"]
        self.assertEqual(1, len(attachment_paths))
        self.assertTrue(any(attachment_paths[0] in step for step in result["human_steps"]))
        self.assertIn("file-permission", json.loads(
            self.run_cli("status", "--handoff-dir", str(handoff)).stdout
        )["human_takeover"]["reasons"])

    def test_human_handoff_rejects_wrong_phase_or_transport(self) -> None:
        paste_handoff = self.prepare()
        self.run_cli(
            "human-handoff",
            "--handoff-dir",
            str(paste_handoff),
            "--reason",
            "manual-transport",
            expected=2,
        )
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(paste_handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        self.run_cli(
            "human-handoff",
            "--handoff-dir",
            str(paste_handoff),
            "--reason",
            "file-selection",
            expected=2,
        )

    def test_submitted_handoff_offers_human_response_export(self) -> None:
        handoff = self.prepare()
        thread_url = "https://chatgpt.com/c/12345678-abcd-1234-abcd-123456789abc"
        manifest = self.approve_and_submit(handoff, thread_url=thread_url)
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual(["login", "captcha", "response-export"], status["human_takeover"]["reasons"])
        self.assertEqual(thread_url, status["submission"]["thread_url"])
        self.assertEqual(thread_url, status["response_collection"]["thread_url"])
        self.assertFalse(status["response_collection"]["automatic_prompt_resend_allowed"])

        result = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "response-export",
            ).stdout
        )
        markers = manifest["response_markers"]
        instructions = "\n".join(result["human_steps"] + result["return_with"])
        self.assertIn(markers["begin"], instructions)
        self.assertIn(markers["end"], instructions)
        self.assertIn(thread_url, instructions)
        self.assertFalse(result["resume"]["automatic_retry_allowed"])
        self.assertTrue(result["resume"]["automatic_collection_retry_allowed"])
        self.assertFalse(result["resume"]["automatic_prompt_resend_allowed"])
        self.assertEqual(
            "run import-response with the saved response file",
            result["resume"]["on_completed"],
        )

    def test_submission_requires_exact_recorded_thread_url(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        result = self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )
        self.assertIn("--thread-url", result.stderr)

    def test_response_monitor_records_bounded_lifecycle_without_resend(self) -> None:
        handoff = self.prepare()
        thread_url = "https://chatgpt.com/c/12345678-abcd-1234-abcd-123456789abc"
        manifest = self.approve_and_submit(handoff, thread_url=thread_url)
        target_thread_id = "019fe4c2-7b00-7213-964e-22607e752d7b"
        plan = json.loads(
            self.run_cli(
                "response-monitor-plan",
                "--handoff-dir",
                str(handoff),
                "--target-thread-id",
                target_thread_id,
            ).stdout
        )
        self.assertEqual("create_heartbeat", plan["action"])
        self.assertEqual(120, plan["interval_seconds"])
        self.assertEqual(15, plan["max_runs"])
        self.assertIn(thread_url, plan["prompt"])
        self.assertIn("Never paste, attach, submit, resend", plan["prompt"])
        self.assertFalse(plan["automatic_prompt_resend_allowed"])

        automation_id = "automation-12345678"
        self.run_cli(
            "record-response-monitor-started",
            "--handoff-dir",
            str(handoff),
            "--automation-id",
            automation_id,
            "--target-thread-id",
            target_thread_id,
            "--deadline",
            plan["deadline"],
        )
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual("monitoring", status["response_collection"]["status"])
        self.assertEqual(automation_id, status["response_monitor"]["automation_id"])
        reused = json.loads(
            self.run_cli(
                "response-monitor-plan",
                "--handoff-dir",
                str(handoff),
                "--target-thread-id",
                target_thread_id,
            ).stdout
        )
        self.assertEqual("reuse_existing", reused["action"])

        markers = manifest["response_markers"]
        response_file = self.root / "monitor-response.md"
        response_file.write_text(
            f"{markers['begin']}\nAdvisory response.\n{markers['end']}\n", encoding="utf-8"
        )
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
        )
        self.run_cli(
            "record-response-monitor-stopped",
            "--handoff-dir",
            str(handoff),
            "--automation-id",
            automation_id,
            "--reason",
            "response_imported",
        )
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual("stopped", status["response_monitor"]["status"])
        self.assertEqual("response_imported", status["response_monitor"]["stop_reason"])
        self.assertEqual("response_imported", status["response_collection"]["status"])
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(1, len([e for e in receipt["events"] if e["type"] == "response_monitor_started"]))
        self.assertEqual(1, len([e for e in receipt["events"] if e["type"] == "response_monitor_stopped"]))
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_response_monitor_creation_failure_is_terminal_and_nonduplicating(self) -> None:
        handoff = self.prepare()
        self.approve_and_submit(
            handoff,
            thread_url="https://chatgpt.com/c/12345678-abcd-1234-abcd-123456789abc",
        )
        target_thread_id = "019fe4c2-7b00-7213-964e-22607e752d7b"
        plan = json.loads(
            self.run_cli(
                "response-monitor-plan",
                "--handoff-dir",
                str(handoff),
                "--target-thread-id",
                target_thread_id,
            ).stdout
        )
        self.run_cli(
            "record-response-monitor-stopped",
            "--handoff-dir",
            str(handoff),
            "--target-thread-id",
            target_thread_id,
            "--deadline",
            plan["deadline"],
            "--reason",
            "creation_failed",
        )
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual("creation_failed", status["response_collection"]["status"])
        self.assertFalse(status["response_collection"]["automatic_collection_retry_allowed"])
        no_restart = json.loads(
            self.run_cli(
                "response-monitor-plan",
                "--handoff-dir",
                str(handoff),
                "--target-thread-id",
                target_thread_id,
            ).stdout
        )
        self.assertEqual("none", no_restart["action"])

    def test_submission_rejects_noncanonical_chatgpt_thread_urls(self) -> None:
        for url in (
            "https://example.com/c/12345678",
            "https://user:secret@chatgpt.com/c/12345678",
            "http://chatgpt.com/c/12345678",
            "https://chatgpt.com:443/c/12345678",
            "https://chatgpt.com/c/12345678?token=secret",
            "https://chatgpt.com/c/12345678#fragment",
            "https://chatgpt.com/",
        ):
            with self.subTest(url=url):
                handoff = self.prepare()
                self.run_cli(
                    "approve",
                    "--handoff-dir",
                    str(handoff),
                    "--approved-by",
                    "user",
                    "--confirm-transmission",
                )
                manifest = self.load(handoff / "manifest.json")
                self.run_cli(
                    "mark-submitted",
                    "--handoff-dir",
                    str(handoff),
                    "--observed-model",
                    manifest["requested_model"],
                    "--observed-transport",
                    manifest["transport"]["resolved"],
                    "--thread-url",
                    url,
                    "--confirm-new-general-chat",
                    "--confirm-sent",
                    expected=2,
                )

    def test_submission_requires_visible_empty_new_general_chat_confirmation(self) -> None:
        handoff = self.prepare()
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        manifest = self.load(handoff / "manifest.json")
        result = self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-sent",
            expected=2,
        )
        self.assertIn("--confirm-new-general-chat", result.stderr)
        self.assertEqual("approved", self.load(handoff / "state.json")["phase"])

    def test_submission_rejects_conversation_url_already_bound_to_sibling_package(self) -> None:
        shared_url = "https://chatgpt.com/c/11111111-2222-3333-4444-555555555555"
        first = self.prepare()
        self.approve_and_submit(first, thread_url=shared_url)

        second = self.prepare()
        second_manifest = self.load(second / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(second),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        result = self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(second),
            "--observed-model",
            second_manifest["requested_model"],
            "--observed-transport",
            second_manifest["transport"]["resolved"],
            "--thread-url",
            shared_url + "/",
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )
        self.assertIn("CHATGPT_THREAD_URL_REUSED", result.stderr)
        self.assertIn(self.load(first / "manifest.json")["package_id"], result.stderr)
        self.assertEqual("approved", self.load(second / "state.json")["phase"])

    def test_concurrent_sibling_submissions_bind_canonical_url_once(self) -> None:
        shared_url = "https://chatgpt.com/c/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        handoffs = [self.prepare(), self.prepare()]
        arguments: list[tuple[str, ...]] = []
        for handoff in handoffs:
            manifest = self.load(handoff / "manifest.json")
            self.run_cli(
                "approve",
                "--handoff-dir",
                str(handoff),
                "--approved-by",
                "user",
                "--confirm-transmission",
            )
            arguments.append(
                (
                    "mark-submitted",
                    "--handoff-dir",
                    str(handoff),
                    "--observed-model",
                    manifest["requested_model"],
                    "--observed-transport",
                    manifest["transport"]["resolved"],
                    "--thread-url",
                    shared_url,
                    "--confirm-new-general-chat",
                    "--confirm-sent",
                )
            )

        barrier_reader, barrier_writer = os.pipe()
        processes: list[subprocess.Popen[str]] = []
        barrier_program = (
            "import os, sys\n"
            "barrier = int(sys.argv[1])\n"
            "script = sys.argv[2]\n"
            "os.read(barrier, 1)\n"
            "os.execv(sys.executable, [sys.executable, script, *sys.argv[3:]])\n"
        )
        try:
            for command in arguments:
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            barrier_program,
                            str(barrier_reader),
                            str(SCRIPT),
                            *command,
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        pass_fds=(barrier_reader,),
                    )
                )
            os.close(barrier_reader)
            barrier_reader = -1
            os.write(barrier_writer, b"12")
            os.close(barrier_writer)
            barrier_writer = -1
            results = [process.communicate(timeout=15) for process in processes]
        finally:
            if barrier_reader >= 0:
                os.close(barrier_reader)
            if barrier_writer >= 0:
                os.close(barrier_writer)
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

        return_codes = [process.returncode for process in processes]
        self.assertEqual([0, 2], sorted(return_codes), msg=str(results))
        rejected_index = return_codes.index(2)
        self.assertIn("CHATGPT_THREAD_URL_REUSED", results[rejected_index][1])
        self.assertNotIn("CHATGPT_THREAD_HISTORY_BUSY", results[rejected_index][1])

        states = [self.load(handoff / "state.json") for handoff in handoffs]
        self.assertEqual(1, sum(state["phase"] == "submitted" for state in states))
        self.assertEqual(1, sum(state["phase"] == "approved" for state in states))
        submitted = next(state for state in states if state["phase"] == "submitted")
        self.assertEqual(shared_url, submitted["submission"]["thread_url"])
        submitted_events = [
            event
            for handoff in handoffs
            for event in self.load(handoff / "receipt.json")["events"]
            if event["type"] == "submitted"
        ]
        self.assertEqual(1, len(submitted_events))
        self.assertEqual(shared_url, submitted_events[0]["data"]["thread_url"])

    def test_submission_fails_closed_on_unsafe_sibling_conversation_history(self) -> None:
        handoff = self.prepare()
        unsafe = handoff.parent / "unsafe-history"
        unsafe.mkdir(mode=0o700)
        (unsafe / "state.json").symlink_to(handoff / "state.json")
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        rejected = self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )
        self.assertIn("CHATGPT_THREAD_HISTORY_UNSAFE", rejected.stderr)
        self.assertEqual("approved", self.load(handoff / "state.json")["phase"])

    def test_submission_serializes_sibling_url_check_and_receipt_commit(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        arguments = (
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
        )

        with GPTPRO.package_lifecycle_lock(handoff.parent):
            rejected = self.run_cli(*arguments, expected=2)
        self.assertIn("CHATGPT_THREAD_HISTORY_BUSY", rejected.stderr)
        self.assertIn("without resending", rejected.stderr)
        self.assertEqual("approved", self.load(handoff / "state.json")["phase"])

        self.run_cli(*arguments)
        self.assertEqual("submitted", self.load(handoff / "state.json")["phase"])

    def test_submitted_state_and_receipt_bind_new_chat_and_outbound_contract(self) -> None:
        handoff = self.prepare()
        self.approve_and_submit(handoff)
        state_path = handoff / "state.json"
        receipt_path = handoff / "receipt.json"
        original_state = self.load(state_path)
        original_receipt = self.load(receipt_path)

        cases = (
            ("conversation-contract", "conversation_contract", "wrong-contract"),
            ("destination", "destination", "Wrong destination"),
            ("observed-model", "observed_model", "Wrong model"),
            ("transport", "transport", "text-file"),
            ("github", "github", {"repository": "wrong/repository"}),
        )
        for name, field, value in cases:
            with self.subTest(case=name):
                state = copy.deepcopy(original_state)
                receipt = copy.deepcopy(original_receipt)
                state["submission"][field] = value
                receipt["events"][-1]["data"] = copy.deepcopy(state["submission"])
                receipt["events"][-1]["event_hash"] = GPTPRO.event_hash(
                    receipt["events"][-1]
                )
                self.write_json(state_path, state)
                self.write_json(receipt_path, receipt)
                rejected = self.run_cli(
                    "verify", "--handoff-dir", str(handoff), expected=2
                )
                self.assertIn("empty new general Chat", rejected.stderr)

        self.write_json(state_path, original_state)
        self.write_json(receipt_path, original_receipt)
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_submission_waits_for_transient_web_url_to_normalize(self) -> None:
        handoff = self.prepare()
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        manifest = self.load(handoff / "manifest.json")
        common_args = (
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--confirm-new-general-chat",
            "--confirm-sent",
        )

        transient = self.run_cli(
            *common_args,
            "--thread-url",
            "https://chatgpt.com/c/WEB:6578523f-56df-475d-9a1a-5da4edf415ef",
            expected=2,
        )
        self.assertIn("CHATGPT_THREAD_URL_TRANSIENT", transient.stderr)
        self.assertIn("without resending", transient.stderr)
        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual("approved", state["phase"])
        self.assertIsNone(state["submission"])
        self.assertNotIn("submitted", [event["type"] for event in receipt["events"]])

        canonical_url = "https://chatgpt.com/c/6a8eb5fa-5e50-83e8-bcf0-f198cf05ce49"
        self.run_cli(*common_args, "--thread-url", canonical_url)
        state = self.load(handoff / "state.json")
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual("submitted", state["phase"])
        self.assertEqual(canonical_url, state["submission"]["thread_url"])
        self.assertEqual(
            GPTPRO.CHATGPT_CONVERSATION_CONTRACT,
            state["submission"]["conversation_contract"],
        )
        self.assertEqual(1, [event["type"] for event in receipt["events"]].count("submitted"))

    def test_submission_canonicalizes_one_trailing_thread_url_slash(self) -> None:
        handoff = self.prepare()
        canonical_url = "https://chatgpt.com/c/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.approve_and_submit(handoff, thread_url=canonical_url + "/")
        state = self.load(handoff / "state.json")
        self.assertEqual(canonical_url, state["submission"]["thread_url"])
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_auto_transport_uses_text_file_over_policy_threshold(self) -> None:
        handoff = self.prepare("review", "--max-paste-bytes", "1")
        manifest = self.load(handoff / "manifest.json")
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)

        self.assertEqual("text-file", manifest["transport"]["resolved"])
        self.assertEqual(["prompt", "context"], [item["artifact"] for item in status["outbound_paths"]])
        self.assertIsNone(status["paste_payload_path"])

    def test_auto_transport_prefers_verified_github_snapshot(self) -> None:
        self.configure_github_remote()
        handoff = self.prepare("review", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")

        self.assertEqual("auto", manifest["transport"]["requested"])
        self.assertEqual("github", manifest["transport"]["resolved"])
        self.assertEqual(self.head, manifest["transport"]["github"]["commit_sha"])
        self.assertEqual(
            ["prompt"],
            [item["artifact"] for item in manifest["transport"]["outbound_artifacts"]],
        )

    def test_auto_transport_records_github_fallback_reason(self) -> None:
        handoff = self.prepare("ask")
        manifest = self.load(handoff / "manifest.json")

        self.assertEqual("paste", manifest["transport"]["resolved"])
        self.assertTrue(any("GitHub-first auto transport was unavailable" in item for item in manifest["warnings"]))

    def test_github_transport_pins_remote_commit_and_sends_only_prompt(self) -> None:
        self.configure_github_remote(pr_number=17)
        handoff = self.prepare(
            "review",
            "--transport",
            "github",
            "--github-pr-url",
            "https://github.com/example/repository/pull/17",
            "--include",
            "src/**",
        )
        manifest = self.load(handoff / "manifest.json")
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        github = manifest["transport"]["github"]

        self.assertEqual("github", manifest["transport"]["resolved"])
        self.assertEqual("example/repository", github["repository"])
        self.assertEqual(self.head, github["commit_sha"])
        self.assertEqual("refs/pull/17/head", github["remote_ref"])
        self.assertEqual(["src/main.py"], github["allowed_paths"])
        self.assertTrue(github["remote_verified"])
        self.assertEqual(["prompt"], [item["artifact"] for item in status["outbound_paths"]])
        self.assertIsNone(status["paste_payload_path"])
        prompt = (handoff / "prompt.md").read_text(encoding="utf-8")
        self.assertIn(self.head, prompt)
        self.assertIn("example/repository", prompt)
        self.assertIn("GPTPRO_GITHUB_ATTESTATION", prompt)
        self.assertNotIn("def answer():", prompt)

    def test_github_transport_rejects_selected_dirty_or_unpushed_content(self) -> None:
        self.configure_github_remote()
        (self.repo / "src" / "main.py").write_text("def answer():\n    return 43\n", encoding="utf-8")
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Review selected code.",
            "--output-root",
            str(self.output_root),
            "--transport",
            "github",
            "--include",
            "src/**",
            expected=2,
        )
        self.assertIn("cannot represent selected local-only or dirty content", result.stderr)

        self.git("add", "src/main.py")
        self.git("commit", "-m", "not pushed")
        result = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Review selected code.",
            "--output-root",
            str(self.output_root),
            "--transport",
            "github",
            "--include",
            "src/**",
            expected=2,
        )
        self.assertIn("not advertised by a GitHub branch or tag", result.stderr)

    def test_github_submission_and_response_require_pinned_identity(self) -> None:
        self.configure_github_remote()
        handoff = self.prepare("debug", "--transport", "github", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")
        github = manifest["transport"]["github"]
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "github",
            "--observed-github-repository",
            github["repository"],
            "--observed-github-commit",
            "0" * 40,
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "github",
            "--observed-github-repository",
            github["repository"],
            "--observed-github-commit",
            github["commit_sha"],
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
        )
        markers = manifest["response_markers"]
        response_file = self.root / "github-response.md"
        response_file.write_text(
            f"{markers['begin']}\n"
            "GPTPRO_GITHUB_ATTESTATION: "
            + json.dumps(
                {
                    "status": "accessed",
                    "repository": github["repository"],
                    "commit_sha": github["commit_sha"],
                    "files_read": ["src/main.py"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + f"\nPinned analysis.\n{markers['end']}\n",
            encoding="utf-8",
        )
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
        )
        state = self.load(handoff / "state.json")
        self.assertEqual("accessed", state["response"]["github_attestation"]["status"])
        self.assertEqual(["src/main.py"], state["response"]["github_attestation"]["files_read"])

    def test_github_human_handoff_names_app_scope_and_prompt_only(self) -> None:
        self.configure_github_remote()
        handoff = self.prepare("review", "--transport", "github", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )

        authorization = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "app-authorization",
            ).stdout
        )
        manual = json.loads(
            self.run_cli(
                "human-handoff",
                "--handoff-dir",
                str(handoff),
                "--reason",
                "manual-transport",
            ).stdout
        )
        authorization_text = "\n".join(authorization["human_steps"])
        manual_text = "\n".join(manual["human_steps"])
        self.assertIn(manifest["transport"]["github"]["repository"], authorization_text)
        self.assertIn(manifest["transport"]["github"]["commit_sha"], authorization_text)
        self.assertIn("Activate the visible GitHub app/plugin", manual_text)
        self.assertIn("attach no local file", manual_text)
        self.assertEqual(["prompt"], [item["artifact"] for item in manual["outbound_paths"]])

    def test_text_context_contains_selected_files_without_local_absolute_paths(self) -> None:
        file_list = self.root / "selected-files.txt"
        file_list.write_text("src/main.py\n", encoding="utf-8")
        handoff = self.prepare(
            "architecture",
            "--transport",
            "text-file",
            "--file-list",
            str(file_list),
        )
        manifest = self.load(handoff / "manifest.json")
        context = (handoff / manifest["artifacts"]["context"]).read_text(encoding="utf-8")

        self.assertIn("src/main.py", context)
        self.assertIn("def answer():", context)
        self.assertIn(self.head, context)
        self.assertNotIn(str(self.repo), context)
        self.assertNotIn(str(file_list), context)
        with zipfile.ZipFile(handoff / manifest["artifacts"]["archive"], "r") as archive:
            internal = archive.read("_gptpro/file-manifest.json").decode("utf-8")
        self.assertNotIn(str(self.repo), internal)
        self.assertNotIn(str(file_list), internal)

    def test_non_utf8_text_is_excluded_from_text_transport(self) -> None:
        (self.repo / "invalid.txt").write_bytes(b"not utf-8: \xff\xfe")
        handoff = self.prepare("ask")
        manifest = self.load(handoff / "manifest.json")

        reasons = {(item["path"], item["reason"]) for item in manifest["excluded"]}
        self.assertIn(("invalid.txt", "non-utf8-text"), reasons)

    def test_directed_selection_records_omitted_files(self) -> None:
        handoff = self.prepare("architecture", "--include", "src/**")
        manifest = self.load(handoff / "manifest.json")
        self.assertEqual("directed", manifest["selection"]["mode"])
        self.assertEqual({"src/main.py"}, {item["path"] for item in manifest["files"]})
        self.assertIn("README.md", {item["path"] for item in manifest["omitted_by_selection"]})

    def test_approval_and_submission_gates_are_enforced(self) -> None:
        handoff = self.prepare()
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            "Pro",
            "--observed-transport",
            "paste",
            "--thread-url",
            "https://chatgpt.com/c/not-approved",
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            expected=2,
        )
        self.approve_and_submit(handoff)
        status = json.loads(self.run_cli("status", "--handoff-dir", str(handoff)).stdout)
        self.assertEqual("submitted", status["phase"])
        receipt = self.load(handoff / "receipt.json")
        outbound = self.load(handoff / "manifest.json")["transport"]["outbound_artifacts"]
        self.assertEqual(
            outbound,
            receipt["events"][1]["data"]["outbound_artifacts"],
        )
        self.assertEqual(outbound, receipt["events"][2]["data"]["outbound_artifacts"])

    def test_submission_rejects_model_or_pro_setting_drift(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            "A fallback model",
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            manifest["transport"]["resolved"],
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
        )

    def test_submission_rejects_transport_fallback(self) -> None:
        handoff = self.prepare("review", "--transport", "text-file")
        manifest = self.load(handoff / "manifest.json")
        self.run_cli(
            "approve",
            "--handoff-dir",
            str(handoff),
            "--approved-by",
            "user",
            "--confirm-transmission",
        )
        self.run_cli(
            "mark-submitted",
            "--handoff-dir",
            str(handoff),
            "--observed-model",
            manifest["requested_model"],
            "--observed-transport",
            "paste",
            "--thread-url",
            f"https://chatgpt.com/c/{manifest['package_id']}",
            "--confirm-new-general-chat",
            "--confirm-sent",
            expected=2,
        )

    def test_response_import_and_evaluation_complete_receipt_chain(self) -> None:
        handoff = self.prepare("debug")
        manifest = self.approve_and_submit(handoff)
        markers = manifest["response_markers"]
        response_file = self.root / "response.md"
        response_file.write_text(
            f"{markers['begin']}\nA bounded advisory answer.\n{markers['end']}\n",
            encoding="utf-8",
        )
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
        )
        self.assertEqual("A bounded advisory answer.\n", (handoff / "response.md").read_text(encoding="utf-8"))
        invalid_sha = self.run_cli(
            "record-evaluation",
            "--handoff-dir",
            str(handoff),
            "--verdict",
            "partially-accepted",
            "--summary",
            "One claim was confirmed.",
            "--evidence",
            "manual source inspection",
            "--applied-git-sha",
            "deadbeef",
            expected=2,
        )
        self.assertIn("full lowercase commit object ID", invalid_sha.stderr)
        self.assertEqual("response_imported", self.load(handoff / "state.json")["phase"])
        self.run_cli(
            "record-evaluation",
            "--handoff-dir",
            str(handoff),
            "--verdict",
            "partially-accepted",
            "--summary",
            "One claim was confirmed.",
            "--evidence",
            "manual source inspection",
        )
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(
            ["prepared", "approved", "submitted", "response_imported", "evaluated"],
            [event["type"] for event in receipt["events"]],
        )
        self.run_cli("verify", "--handoff-dir", str(handoff))

        prior_evaluation_sha256 = self.load(handoff / "state.json")["evaluation"][
            "evaluation_sha256"
        ]
        self.run_cli(
            "correct-evaluation",
            "--handoff-dir",
            str(handoff),
            "--prior-evaluation-sha256",
            prior_evaluation_sha256,
            "--verdict",
            "accepted",
            "--summary",
            "The evidence was corrected without rewriting receipt history.",
            "--evidence",
            "current source and test inspection",
            "--applied-git-sha",
            self.head,
        )
        corrected = self.load(handoff / "evaluation.json")
        self.assertEqual("accepted", corrected["verdict"])
        self.assertEqual(self.head, corrected["applied_git_sha"])
        receipt = self.load(handoff / "receipt.json")
        self.assertEqual(
            [
                "prepared",
                "approved",
                "submitted",
                "response_imported",
                "evaluated",
                "evaluation_corrected",
            ],
            [event["type"] for event in receipt["events"]],
        )
        stale = self.run_cli(
            "correct-evaluation",
            "--handoff-dir",
            str(handoff),
            "--prior-evaluation-sha256",
            prior_evaluation_sha256,
            "--verdict",
            "rejected",
            "--summary",
            "Stale correction must not apply.",
            "--evidence",
            "stale prior hash",
            expected=2,
        )
        self.assertIn("Prior evaluation hash does not match", stale.stderr)
        self.assertEqual(corrected, self.load(handoff / "evaluation.json"))
        self.run_cli("verify", "--handoff-dir", str(handoff))

    def test_foreign_or_unmarked_response_is_rejected(self) -> None:
        handoff = self.prepare()
        self.approve_and_submit(handoff)
        response_file = self.root / "foreign.md"
        response_file.write_text("BEGIN_GPTPRO_RESPONSE:other\nNo.\nEND_GPTPRO_RESPONSE:other\n", encoding="utf-8")
        self.run_cli(
            "import-response",
            "--handoff-dir",
            str(handoff),
            "--response-file",
            str(response_file),
            expected=2,
        )

    def test_archive_tampering_is_detected(self) -> None:
        handoff = self.prepare()
        manifest = self.load(handoff / "manifest.json")
        archive = handoff / manifest["artifacts"]["archive"]
        with archive.open("ab") as handle:
            handle.write(b"tampered")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_paste_payload_tampering_is_detected(self) -> None:
        handoff = self.prepare("review", "--transport", "paste")
        manifest = self.load(handoff / "manifest.json")
        payload = handoff / manifest["artifacts"]["paste_payload"]
        with payload.open("a", encoding="utf-8") as handle:
            handle.write("tampered\n")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_text_context_tampering_is_detected(self) -> None:
        handoff = self.prepare("review", "--transport", "text-file")
        manifest = self.load(handoff / "manifest.json")
        context = handoff / manifest["artifacts"]["context"]
        with context.open("a", encoding="utf-8") as handle:
            handle.write("tampered\n")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_receipt_tampering_is_detected(self) -> None:
        handoff = self.prepare()
        receipt_path = handoff / "receipt.json"
        receipt = self.load(receipt_path)
        receipt["events"][0]["data"]["git_head_sha"] = "0" * 40
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.run_cli("verify", "--handoff-dir", str(handoff), expected=2)

    def test_custom_output_root_inside_repo_is_never_repackaged(self) -> None:
        output_root = self.repo / "handoffs"
        first = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "plan",
            "--task",
            "First package.",
            "--output-root",
            str(output_root),
        )
        self.assertTrue(Path(json.loads(first.stdout)["handoff_dir"]).is_dir())
        second = self.run_cli(
            "prepare",
            "--repo",
            str(self.repo),
            "--mode",
            "review",
            "--task",
            "Second package.",
            "--output-root",
            str(output_root),
        )
        manifest = self.load(Path(json.loads(second.stdout)["handoff_dir"]) / "manifest.json")
        self.assertFalse(any(item["path"].startswith("handoffs/") for item in manifest["files"]))


class GptProStructureTests(unittest.TestCase):
    def test_dependency_free_validator_checks_standalone_and_plugin_mirror(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        repository_root = skill_root.parent
        mirror = repository_root / "plugins" / "gptpro" / "skills" / "gptpro"
        result = subprocess.run(
            [
                "python3",
                str(STRUCTURE_SCRIPT),
                "--skill-dir",
                str(skill_root),
                "--mirror",
                str(mirror),
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertIn("standalone-plugin-mirror", payload["checks"])

    def test_dependency_free_validator_reports_missing_required_file(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            damaged = Path(temp) / "gptpro"
            shutil.copytree(skill_root, damaged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (damaged / "references" / "security.md").unlink()
            result = subprocess.run(
                ["python3", str(damaged / "scripts" / "validate_structure.py"), "--json"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertIn("Required file missing: references/security.md", payload["errors"])


if __name__ == "__main__":
    unittest.main()

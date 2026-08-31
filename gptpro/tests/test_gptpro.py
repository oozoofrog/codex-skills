from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "gptpro.py"


def load_module():
    spec = importlib.util.spec_from_file_location("gptpro_desktop_base_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DesktopBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gptpro-desktop-base-")
        self.root = Path(self.temporary.name).resolve()
        self.module = load_module()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_main(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def companion(self) -> Path:
        root = self.root / "gptpro-mcp"
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        (root / "SKILL.md").write_text(
            "---\nname: gptpro-mcp\ndescription: fixture\n---\n", encoding="utf-8"
        )
        script = scripts / "gptpro.py"
        capture = self.root / "delegated.json"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "if 'capabilities' in sys.argv:\n"
            " print(json.dumps({'contract':'gptpro-component-capabilities-v1',"
            "'component':'gptpro-mcp','mcp_runtime':True,"
            "'delivery_channels':['desktop-ui']}))\n"
            " raise SystemExit(0)\n"
            f"open({str(capture)!r}, 'w', encoding='utf-8').write("
            "json.dumps({'delegated': True, 'argv': sys.argv[1:]}))\n",
            encoding="utf-8",
        )
        os.chmod(script, 0o755)
        return script

    def test_capabilities_are_desktop_only(self) -> None:
        code, stdout, stderr = self.run_main("capabilities")
        self.assertEqual(0, code, stderr)
        value = json.loads(stdout)
        self.assertEqual(["desktop-ui"], value["delivery_channels"])
        self.assertFalse(value["browser_delivery"])
        self.assertFalse(value["cdp"])
        self.assertFalse(value["electron_private_api"])

    def test_help_has_no_browser_or_monitor_command(self) -> None:
        code, stdout, stderr = self.run_main("--help")
        self.assertEqual(0, code, stderr)
        self.assertNotIn("browser-plan       ", stdout)
        self.assertNotIn("response-monitor", stdout)
        self.assertIn("Desktop-only", stdout)

    def test_removed_browser_command_fails_without_companion(self) -> None:
        code, stdout, stderr = self.run_main(
            "--error-format", "json", "browser-plan"
        )
        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        value = json.loads(stderr)
        self.assertEqual("GPTPRO_BROWSER_REMOVED", value["error"]["code"])
        self.assertTrue(value["error"]["sanitized"])

    def test_missing_companion_is_sanitized(self) -> None:
        descriptor = self.root / ".gptpro-components.json"
        code, _, stderr = self.run_main(
            "--error-format",
            "json",
            "--component-descriptor",
            str(descriptor),
            "desktop-doctor",
        )
        self.assertEqual(2, code)
        self.assertEqual("GPTPRO_MCP_COMPONENT_REQUIRED", json.loads(stderr)["error"]["code"])

    def test_exact_explicit_companion_is_verified_and_delegated(self) -> None:
        entrypoint = self.companion()
        code, stdout, stderr = self.run_main(
            "--mcp-entrypoint", str(entrypoint), "desktop-doctor"
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual("", stdout)
        value = json.loads((self.root / "delegated.json").read_text(encoding="utf-8"))
        self.assertTrue(value["delegated"])
        self.assertIn("--base-entrypoint", value["argv"])
        self.assertIn("desktop-doctor", value["argv"])

    def test_descriptor_must_be_owner_only(self) -> None:
        entrypoint = self.companion()
        descriptor = self.root / ".gptpro-components.json"
        descriptor.write_text(
            json.dumps(
                {
                    "schema": "gptpro-install-descriptor-v1",
                    "components": {
                        "gptpro-mcp": {
                            "entrypoint": str(entrypoint),
                            "tree_sha256": self.module._tree_hash(entrypoint.parent.parent),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        descriptor.chmod(0o644)
        code, _, stderr = self.run_main(
            "--error-format",
            "json",
            "--component-descriptor",
            str(descriptor),
            "desktop-doctor",
        )
        self.assertEqual(2, code)
        self.assertEqual(
            "GPTPRO_COMPONENT_DESCRIPTOR_UNSAFE", json.loads(stderr)["error"]["code"]
        )


if __name__ == "__main__":
    unittest.main()

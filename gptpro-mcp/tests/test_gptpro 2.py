from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "gptpro.py"


def load_module():
    name = "gptpro_mcp_cli_surface_tests"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GptProMcpCliSurfaceTests(unittest.TestCase):
    def run_main(self, *args: str) -> tuple[int, str, str]:
        module = load_module()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = module.main(list(args))
            except SystemExit as exc:
                code = int(exc.code or 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_capabilities_advertise_only_desktop_delivery(self) -> None:
        code, stdout, stderr = self.run_main("capabilities", "--json")
        self.assertEqual(0, code, stderr)
        value = json.loads(stdout)
        self.assertEqual("gptpro-mcp", value["component"])
        self.assertEqual(["desktop-ui"], value["delivery_channels"])
        self.assertTrue(value["mcp_runtime"])
        self.assertFalse(value["browser_delivery"])
        self.assertFalse(value["cdp"])
        self.assertFalse(value["electron_private_api"])

    def test_parser_has_no_browser_or_response_monitor_commands(self) -> None:
        code, stdout, stderr = self.run_main("--help")
        self.assertEqual(0, code, stderr)
        self.assertNotIn("browser-plan", stdout)
        self.assertNotIn("browser-doctor", stdout)
        self.assertNotIn("response-monitor-plan", stdout)
        self.assertIn("desktop-plan", stdout)
        self.assertIn("desktop-doctor", stdout)

    def test_prepare_rejects_non_desktop_transport_at_parse_boundary(self) -> None:
        code, _, stderr = self.run_main(
            "--error-format",
            "json",
            "prepare",
            "--repo",
            str(SKILL_ROOT),
            "--mode",
            "review",
            "--task",
            "fixture",
            "--transport",
            "paste",
        )
        self.assertEqual(2, code)
        self.assertEqual("GPTPRO_ARGUMENT_ERROR", json.loads(stderr)["error"]["code"])


if __name__ == "__main__":
    unittest.main()

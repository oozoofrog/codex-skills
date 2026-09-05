from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_gptpro_base.py"
TARGET = REPO_ROOT / "gptpro" / "scripts" / "gptpro.py"


class BuildGptproBaseTests(unittest.TestCase):
    def test_reviewed_base_boundary_is_current_and_mcp_execution_free(self) -> None:
        before = TARGET.read_bytes()
        result = subprocess.run(
            ["python3", str(SCRIPT), "--check"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=f"{result.stdout}\n{result.stderr}")
        self.assertEqual(before, TARGET.read_bytes())
        source = before.decode("utf-8")
        self.assertNotIn("runtime.gptpro_mcp", source)
        self.assertIn('"component": "gptpro"', source)
        self.assertIn('"mcp_runtime": False', source)
        self.assertIn('"delivery_channels": ["desktop-ui"]', source)
        self.assertIn("GPTPRO_MCP_COMPONENT_REQUIRED", source)
        self.assertNotIn("command_response_monitor_plan", source)


if __name__ == "__main__":
    unittest.main()

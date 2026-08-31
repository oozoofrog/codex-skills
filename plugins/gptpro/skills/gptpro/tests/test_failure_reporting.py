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
    spec = importlib.util.spec_from_file_location("gptpro_base_failure_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FailureReportingTests(unittest.TestCase):
    def test_json_component_failure_is_actionable_and_sanitized(self) -> None:
        module = load_module()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module.main(
                [
                    "--error-format",
                    "json",
                    "--component-descriptor",
                    "/definitely/missing/.gptpro-components.json",
                    "desktop-doctor",
                ]
            )
        self.assertEqual(2, code)
        self.assertEqual("", stdout.getvalue())
        payload = json.loads(stderr.getvalue())
        self.assertEqual("GPTPRO_MCP_COMPONENT_REQUIRED", payload["error"]["code"])
        self.assertTrue(payload["error"]["sanitized"])
        self.assertIn("manage_skills.py", payload["error"]["recovery"])

    def test_reference_preserves_seven_item_report(self) -> None:
        text = (SKILL_ROOT / "references" / "failure-reporting.md").read_text(
            encoding="utf-8"
        )
        for token in (
            "실패한 단계와 작업",
            "기대한 결과와 실제 관찰",
            "정제된 오류 코드와 설명",
            "전송·승인·저장소 변경 여부",
            "현재 package/Tunnel 상태",
            "자동 재시도 가능 여부",
            "사용자가 해야 할 다음 조치",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()

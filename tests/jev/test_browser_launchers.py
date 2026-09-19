"""Offline boundary checks for the installed browser adapters; no model calls."""

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "jev-ultrafast/scripts"
spec = importlib.util.spec_from_file_location(
    "jev_connection_test", SCRIPTS / "connection.py"
)
connection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connection)


def test_disconnected_run_never_constructs_agent():
    def unexpected(*args):
        raise AssertionError("Task must not start before Chrome is ready")

    with (
        patch.dict(
            sys.modules,
            {
                "connection": SimpleNamespace(ready=lambda: False),
                "jev_ultrafast": SimpleNamespace(Agent=unexpected),
            },
        ),
        patch.object(
            sys,
            "argv",
            ["run.py", "--url", "https://example.com", "--goal", "Read title"],
        ),
    ):
        try:
            runpy.run_path(str(SCRIPTS / "run.py"), run_name="__main__")
        except SystemExit as error:
            assert error.code == 3
        else:
            raise AssertionError("Disconnected runner should exit")


def test_prepare_timeout_exits_without_starting_task(capsys):
    with (
        patch.object(connection, "ready", return_value=False),
        patch.object(
            connection.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("connect", 20),
        ),
    ):
        assert connection.prepare() == 3
    output = json.loads(capsys.readouterr().out)
    assert output["task_started"] is False
    assert output["status"] == "connection_required"


def test_prepare_ready_skips_connection_request(capsys):
    with (
        patch.object(connection, "ready", return_value=True),
        patch.object(connection.subprocess, "run") as command,
    ):
        assert connection.prepare() == 0
        command.assert_not_called()
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_ready_requires_success_and_healthy():
    for code, data, expected in [
        (0, {"healthy": True}, True),
        (0, {"healthy": False}, False),
        (1, {"healthy": True}, False),
    ]:
        with patch.object(
            connection.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=code, stdout=json.dumps(data)),
        ):
            assert connection.ready() is expected


def test_launchers_share_controller_lock(tmp_path):
    import os

    env = dict(os.environ, HOME=str(tmp_path))
    controller = ROOT / "jev-computer-use/scripts/controller.py"
    marker = tmp_path / "ready"
    first = subprocess.Popen(
        [
            sys.executable,
            str(controller),
            sys.executable,
            "-c",
            "import pathlib,time,sys; pathlib.Path(sys.argv[1]).touch(); time.sleep(15)",
            str(marker),
        ],
        env=env,
    )
    try:
        import time

        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        second = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "controller.py"),
                sys.executable,
                "-c",
                "raise SystemExit(99)",
            ],
            env=env,
            capture_output=True,
            timeout=5,
            check=False,
        )
        assert second.returncode == 4
    finally:
        first.terminate()
        first.wait(timeout=5)
    third = subprocess.run(
        [sys.executable, str(controller), sys.executable, "-c", "pass"],
        env=env,
        timeout=5,
        check=False,
    )
    assert third.returncode == 0


def test_exhaustion_is_step_limit_and_final_evidence_is_observed(capsys, tmp_path):
    class Agent:
        def __init__(self, *args):
            self.browser = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def snapshot(self):
            return {"status": "running", "history": [], "elapsed_ms": 1}

        def command(self, command):
            return self.snapshot()

        def observe(self, **kwargs):
            return {
                "url": "https://example.com/final",
                "title": "Final",
                "text": "Visible balance",
                "actions": [],
            }

    with (
        patch.dict(
            sys.modules,
            {
                "connection": SimpleNamespace(ready=lambda: True),
                "jev_ultrafast": SimpleNamespace(Agent=Agent),
            },
        ),
        patch.object(
            sys,
            "argv",
            [
                "run.py",
                "--url",
                "https://example.com",
                "--goal",
                "Read balance",
                "--max-steps",
                "1",
                "--out",
                str(tmp_path / "run"),
            ],
        ),
    ):
        try:
            runpy.run_path(str(SCRIPTS / "run.py"), run_name="__main__")
        except SystemExit as error:
            assert error.code == 2
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["status"] == "step_limit"
    assert result["verification_required"] is True
    assert result["url"] == "https://example.com/final"


def test_input_timeout_saves_evidence_without_replaying(capsys, tmp_path):
    calls = []

    class Agent:
        def __init__(self, *args):
            self.browser = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def snapshot(self):
            return {
                "status": "ready",
                "history": [],
                "elapsed_ms": 1,
                "decisions": [{"choice": "e1"}],
            }

        def command(self, name):
            calls.append(name)
            raise TimeoutError("input may have been delivered")

        def observe(self, **kwargs):
            return {
                "url": "https://example.com/after",
                "title": "After",
                "text": "Actual final state",
                "actions": [],
            }

    out = tmp_path / "run"
    with (
        patch.dict(
            sys.modules,
            {
                "connection": SimpleNamespace(ready=lambda: True),
                "jev_ultrafast": SimpleNamespace(Agent=Agent),
            },
        ),
        patch.object(
            sys,
            "argv",
            [
                "run.py",
                "--url",
                "https://example.com",
                "--goal",
                "Read",
                "--out",
                str(out),
            ],
        ),
    ):
        try:
            runpy.run_path(str(SCRIPTS / "run.py"), run_name="__main__")
        except SystemExit as error:
            assert error.code == 2
    assert calls == ["tick"]
    result = json.loads((out / "result.json").read_text())
    assert result["execution_ambiguous"] is True and result["observation_fresh"] is True
    assert result["url"] == "https://example.com/after"
    assert (out / "interrupted-state.json").exists()

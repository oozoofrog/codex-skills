"""Bounded background task with durable observations, including ambiguous failures."""

import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from connection import ready
from jev_ultrafast import Agent

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", required=True)
parser.add_argument("--goal", required=True)
parser.add_argument(
    "--max-steps", type=int, default=20, choices=range(1, 61), metavar="1..60"
)
parser.add_argument(
    "--out",
    type=Path,
    default=Path("runs") / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"),
)
args = parser.parse_args()

if not ready():
    print(
        json.dumps(
            {
                "status": "connection_required",
                "task_started": False,
                "next": "Run jev.sh prepare, handle the observed Chrome permission, then check status.",
            }
        ),
        flush=True,
    )
    raise SystemExit(3)

args.out.mkdir(parents=True, exist_ok=False, mode=0o700)


def save(name, data):
    (args.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))


save("request.json", {"url": args.url, "goal": args.goal, "max_steps": args.max_steps})
final = {
    "status": "error",
    "verification_required": True,
    "evidence_dir": str(args.out.resolve()),
}
try:
    with Agent(args.url, args.goal) as agent:
        state = agent.snapshot()
        try:
            save("initial.json", state)
            for step in range(args.max_steps):
                state = agent.command("tick")
                save(f"step-{step + 1:03d}.json", state)
                print(
                    json.dumps(
                        {
                            "status": state["status"],
                            "actions": len(state["history"]),
                            "elapsed_ms": state["elapsed_ms"],
                        }
                    ),
                    flush=True,
                )
                if state["status"] in {"done", "blocked"}:
                    break
            final["status"] = (
                state["status"]
                if state["status"] in {"done", "blocked"}
                else "step_limit"
            )
        except Exception as error:  # noqa: BLE001 - preserve evidence at the CLI boundary; never retry
            # An input timeout may have delivered the mutation. Record it and never replay.
            final.update(
                status="error",
                error_type=type(error).__name__,
                execution_ambiguous=True,
            )
            save("interrupted-state.json", agent.snapshot())
        try:
            observed = agent.browser.observe(screenshot=True)
            save(
                "final-observation.json",
                {k: v for k, v in observed.items() if k != "screenshot"},
            )
            if observed.get("screenshot"):
                (args.out / "final.jpg").write_bytes(
                    base64.b64decode(observed["screenshot"])
                )
            final.update(
                observation_fresh=True,
                url=observed["url"],
                title=observed["title"],
                text=observed["text"],
                controls=[
                    {
                        k: a[k]
                        for k in ("label", "value", "checked", "selected")
                        if k in a
                    }
                    for a in observed["actions"]
                ],
            )
        except Exception as error:  # noqa: BLE001 - preserve evidence at the CLI boundary; never retry
            final.update(
                observation_fresh=False, observation_error=type(error).__name__
            )
except KeyboardInterrupt:
    final.update(status="interrupted", execution_ambiguous=True)
except Exception as error:  # noqa: BLE001 - preserve evidence at the CLI boundary; never retry
    final.update(status="error", error_type=type(error).__name__)
finally:
    save("result.json", final)
    print(json.dumps(final, ensure_ascii=False), flush=True)
if final["status"] != "done" or not final.get("observation_fresh"):
    raise SystemExit(2)

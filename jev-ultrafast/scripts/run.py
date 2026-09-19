"""Bounded run with final evidence returned to Codex for independent verification."""

import argparse
import json

from jev_ultrafast import Agent

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", required=True)
parser.add_argument("--goal", required=True)
parser.add_argument("--max-steps", type=int, default=20, choices=range(1, 61), metavar="1..60")
args = parser.parse_args()

with Agent(args.url, args.goal) as agent:
    state = agent.snapshot()
    for _ in range(args.max_steps):
        state = agent.command("tick")
        print(json.dumps({"status": state["status"], "actions": len(state["history"]),
                          "elapsed_ms": state["elapsed_ms"]}), flush=True)
        if state["status"] in {"done", "blocked"}:
            break
    observed = agent.browser.observe(screenshot=False)
    print(json.dumps({"status": state["status"], "verification_required": True,
                      "url": observed["url"], "title": observed["title"], "text": observed["text"],
                      "controls": [{k: a[k] for k in ("label", "value", "checked", "selected") if k in a}
                                   for a in observed["actions"]]}, ensure_ascii=False))
    if state["status"] != "done":
        raise SystemExit(2)

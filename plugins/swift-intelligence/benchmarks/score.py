#!/usr/bin/env python3

import json
from pathlib import Path
import sys


def cases(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            case_id, _, expected = line.split("\t", 2)
            yield case_id, expected.split("|")


def metrics(events_path):
    input_tokens = 0
    output_tokens = 0
    tool_calls = 0
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "turn.completed":
            usage = event.get("usage", {})
            input_tokens = max(input_tokens, usage.get("input_tokens", 0))
            output_tokens = max(output_tokens, usage.get("output_tokens", 0))
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") in {
            "command_execution", "mcp_tool_call"
        }:
            tool_calls += 1
    return input_tokens, output_tokens, tool_calls


def main():
    cases_path = Path(sys.argv[1])
    result_root = Path(sys.argv[2])
    print("case\tmode\taccuracy\tinput_tokens\toutput_tokens\ttool_calls")
    for case_id, expected in cases(cases_path):
        for mode in ("baseline", "semantic"):
            final_path = result_root / mode / f"{case_id}.final.json"
            events_path = result_root / mode / f"{case_id}.events.jsonl"
            if not final_path.exists() or not events_path.exists():
                continue
            answer = final_path.read_text(encoding="utf-8")
            accuracy = sum(value in answer for value in expected) / len(expected)
            input_tokens, output_tokens, tool_calls = metrics(events_path)
            print(
                f"{case_id}\t{mode}\t{accuracy:.2f}\t{input_tokens}\t"
                f"{output_tokens}\t{tool_calls}"
            )


if __name__ == "__main__":
    main()

#!/bin/bash

set -euo pipefail

plugin_root=$(cd "$(dirname "$0")/.." && pwd)
workspace=${1:-"$plugin_root/benchmarks/fixture"}
cases_file=${2:-"$plugin_root/benchmarks/cases.tsv"}
result_root=${3:-"$plugin_root/benchmark-results/$(date +%Y%m%d-%H%M%S)"}
selected_case=${BENCHMARK_CASE:-}
server_script="$plugin_root/scripts/swift_intelligence_mcp.py"
schema_file="$plugin_root/benchmarks/result.schema.json"

mkdir -p "$result_root/baseline" "$result_root/semantic"
if [[ -f "$workspace/Package.swift" ]]; then
    swift build --package-path "$workspace" >/dev/null
elif project=$(find "$workspace" -maxdepth 1 -name '*.xcodeproj' -print -quit) && [[ -n "$project" ]]; then
    scheme=$(basename "$project" .xcodeproj)
    xcodebuild -project "$project" -scheme "$scheme" build-for-testing >/dev/null
fi
command_json=$(python3 -c 'import json; print(json.dumps("python3"))')
args_json=$(python3 -c 'import json,sys; print(json.dumps([sys.argv[1]]))' "$server_script")

while IFS=$'\t' read -r case_id task expected; do
    [[ -z "$case_id" ]] && continue
    [[ -n "$selected_case" && "$case_id" != "$selected_case" ]] && continue

    for mode in baseline semantic; do
        prompt="파일을 수정하지 마세요. $task 증거는 path:line 형식으로 반환하세요."
        command=(
            codex exec --ephemeral --json --color never --sandbox read-only
            --ignore-user-config --skip-git-repo-check --cd "$workspace" --output-schema "$schema_file"
            --output-last-message "$result_root/$mode/$case_id.final.json"
        )

        if [[ "$mode" == semantic ]]; then
            prompt="swift-intelligence MCP를 먼저 사용하고 workspace_path에는 $workspace 를 전달하세요. $prompt"
            if [[ "$case_id" == *references* ]]; then
                prompt="요구사항에서 swift_references와 swift_implementations를 호출한 뒤 각 구현에서도 swift_references를 호출하고 합집합으로 답하세요. $prompt"
            fi
            command+=(
                --config "mcp_servers.swift-intelligence.command=$command_json"
                --config "mcp_servers.swift-intelligence.args=$args_json"
                --config 'mcp_servers.swift-intelligence.default_tools_approval_mode="writes"'
                --config 'mcp_servers.swift-intelligence.startup_timeout_sec=30'
                --config 'mcp_servers.swift-intelligence.tool_timeout_sec=60'
            )
        else
            prompt="MCP 도구를 사용하지 말고 텍스트 검색과 파일 읽기만 사용하세요. $prompt"
        fi

        "${command[@]}" "$prompt" \
            > "$result_root/$mode/$case_id.events.jsonl" \
            < /dev/null
    done
done < "$cases_file"

python3 "$plugin_root/benchmarks/score.py" "$cases_file" "$result_root" \
    | tee "$result_root/score.tsv"

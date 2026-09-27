# 설치·첫 실행·문제 해결

## Install / configure

저장소의 [Plugin 설치 안내](https://github.com/oozoofrog/codex-skills/blob/main/docs/plugin-installation.md#jev-blender-use)를 따른다. Plugin release가 원격 catalog에 반영된 뒤 설치해야 한다. checkout 작업에서는 설치 없이 `jev-blender-use/`를 사용한다. 배포된 Plugin에서는 해당 skill directory를 기준으로 명령을 실행한다.

```sh
codex plugin marketplace update codex-skills
codex plugin add jev-blender-use@codex-skills
```

Python 3.10+와 Blender가 필요하다. 설치된 Blender 실행 파일을 우선 발견하고, 여러 버전이면 `--blender` 또는 `BLENDER_BIN`을 지정한다. macOS `.app` bundle도 `--blender`로 받을 수 있다. 새 세션의 실제 skill path·Plugin 활성화와 실행 가능 여부는 별도로 확인한다. 기본 CLI는 MCP/TypeSafe 설치나 인증이 필요 없다.

## 작업 시작

알려진 실행 경로와 기존 실행 근거가 있으면 요청한 작업부터 시작한다. 아래 health와 전체 예제는 환경 진단·기능 개발에 필요한 경우에 사용한다. 별도 애드온 연결 시험·GUI 시험·버전별 검증을 완료할 때까지 작업을 미루지 않는다. 연결된 도구의 첫 장면 조사 자체로 연결 상태를 파악하면 된다.

## 선택적 health check

```sh
python3 scripts/blender_cli.py health --output-dir /tmp/blender-health-new
# 이미 설치한 stdio MCP가 있을 때
python3 scripts/blender_cli.py health --mcp-config mcp.json --output-dir /tmp/blender-health-mcp-new
```

CLI version, bpy 실행, Jev 환경 변수 존재, MCP 연결 여부를 분리한다. 인증 변수 존재는 서비스 가용성 증거가 아니며 키를 출력하지 않는다. MCP config가 없으면 unknown/unprobed다. 현재 열린 파일 상태는 MCP inspect에서만 얻는다. 이 health는 Codex의 전역 config를 바꾸거나 다른 MCP 설정을 읽어 통신하지 않는다.

## First scene / background example

아래 명령은 skill directory 기준이다. 출력 경로는 존재하지 않는 새 경로로 정한다.

```sh
python3 scripts/blender_cli.py run --plan examples/simple-scene/plan.json \
  --script examples/simple-scene/create.py --trusted-script --output-dir /tmp/cube-new
python3 scripts/blender_cli.py render --source /tmp/cube-new/candidate.blend --width 512 --height 384 --samples 8 --output-dir /tmp/cube-preview-new
python3 scripts/workflow.py validate --plan /tmp/cube-new/plan.json --before /tmp/cube-new/before.json --after /tmp/cube-new/after.json
```

이 예제는 외형 요구가 있으므로 preview를 실제로 관찰하고 [Vision/verdict](validation-contract.md)를 작성한 후 finalize한다. `workflow.py verdict`가 Codex의 판단과 현재 evidence 해시를 연결하므로 별도 Python glue를 작성할 필요가 없다. 수치·구조만 요구한 작업은 visual requirement 없이 바로 finalize할 수 있다. 모든 예제를 돌릴 때는 `python3 examples/run_examples.py --output-dir /tmp/blender-examples-new`를 쓴다. 이 명령은 Blender 프로세스·작은 CPU preview를 순차 실행하고 시각 판정을 기다리는 상태로 남긴다. 일반 작업 전에 전체 예제를 실행할 필요는 없다.

## Interactive / Jev-enabled example

[MCP 연결·실행](blender-mcp.md)의 inspect→checkpoint→execute→capture를 사용한다. [Jev integration](jev-integration.md)의 request 준비를 먼저 확인하고, 전송이 허용돼 있으며 인증이 있을 때만 `--send`한다. API 실패는 Codex fallback으로 돌아오며 exact guard와 visual requirement는 유지한다.

## Troubleshooting

| 증상 | 다음 행동 |
| --- | --- |
| Blender 없음/여러 버전 | 실행 파일 또는 `.app`의 `--blender` 지정 |
| MCP tools가 보여도 연결 실패 | Blender addon 활성·listener와 실제 읽기 probe 확인; 저장본 작업만 CLI fallback |
| MCP deadline | live state 재조사, 중복 mutation 금지 |
| source hash mismatch | 같은 원본의 새 inspect로 계획을 갱신 |
| output exists | 실패 evidence를 보존하고 새 output 경로 사용 |
| protected/shape key/shared data guard | duplicate/single-user/비파괴적 전략으로 다시 계획 |
| camera 없음 | preview용 camera를 계획해 새 후보로 생성 |
| Blender process failure | `blender.log`와 `worker-result.json`, 지원 버전 확인 |
| Jev missing key/service error | 전송 실패를 결정 결과로 쓰지 말고 명시적 Codex 판단 |
| finalize review | 누락된 실제 이미지·receipt·검사·판단 freshness 해결 |

현재 설치된 Blender에서 필요한 API를 확인하며 작업한다. 버전별 실행 기록이 없다는 이유만으로 다른 버전 설치나 전체 회귀를 선행하지 않는다. Blender 4.5 목표 호환성과 실제 실행한 5.2.2 증거를 구분한다. 공식 MCP의 최소 버전은 별도이며 모든 4.5 환경에서 공식 MCP가 동작한다고 주장하지 않는다.

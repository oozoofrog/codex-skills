---
name: jev-blender-use
description: "Blender의 열린 장면은 MCP로, 재현 가능한 작업은 CLI/bpy로 조작하고 수치 검증·시각 관찰·선택적 Jev 판단으로 결과를 확인한다. 모델링, 재질, Geometry Nodes, 리깅 조사, 렌더와 반복 수정에 사용한다."
---

# Blender + Jev Agent

**Codex thinks and creates. Blender executes and measures. Vision observes. Jev decides. Code verifies exact conditions.**

Jev·MCP가 없어도 CLI/bpy 작업은 가능하다. Codex가 목표에 맞는 bpy/노드/리그 코드를 작성하고, 사용 중 드러난 API·장면 차이에 대응한다. 예제에 없거나 특정 환경에서 미실행인 기능도 코드·API 계약을 근거로 가능성을 판단해 진행한다. 실제 성공 여부는 수행한 범위대로 보고한다.

## 작업에 맞는 절차

- 기존 환경·동작 근거를 재사용한다. health, 전체 예제, 버전별 회귀, benchmark, 독립 검토를 매 작업의 시작 조건으로 요구하지 않는다.
- 조회·명확한 작은 수정은 필요한 대상 조사와 결과 확인으로 진행한다. 재현·보호·수치 목표가 필요한 작업은 아래 실행기를 사용하고 plan을 작게 작성한다.
- 외형이 목표에 포함되면 결과를 관찰한다. 이름·수치·구조만 바꾸는 작업에 렌더나 Vision 판단을 추가하지 않는다. Jev와 별도 평가자는 결과 판단에 도움이 될 때 선택한다.
- 연결·schema·mode 차이는 현재 도구와 장면을 조사해 해결한다. 같은 실패를 반복하거나 사용자 원본을 위험에 빠뜨리는 재시도는 피하고, 의도·권한·복구 경로가 실제로 부족한 경우만 사용자에게 묻는다.

## 시작과 경로 선택

- 실행 경로가 알려져 있으면 바로 작업한다. 실행 파일 탐색이나 연결 진단이 필요할 때 [시작 안내](references/getting-started.md)의 health를 사용한다. MCP는 노출된 schema와 첫 실제 작업 응답으로 연결을 파악하며, 도구 목록만으로 장면에 연결됐다고 보고하지 않는다.
- **현재 열린 장면·사용자와 공동 편집**은 [MCP 경로](references/blender-mcp.md)를 사용한다. MCP가 없으면 미저장 상태를 CLI 저장본으로 대체하지 않는다. 저장된 입력이 목표와 일치할 때 CLI로 전환한다.
- **배치·재현·새 제작·회귀 검사**는 [CLI/bpy 계약](references/bpy.md)의 `blender_cli.py`를 사용한다. `--source`가 없으면 새 장면이다. 기존 `blender_use.py`의 정적 snapshot/GLB와 [캡슐 데모](references/capsule-demo.md)도 유지된다.
- `--trusted-script`는 검토한 Python의 임의 코드 실행을 명시한다. autoexec/offline 옵션은 sandbox가 아니다. [실행·복구 경계](references/safety.md)를 따른다.

## 기본 루프

**Inspect → Plan → Modify → Inspect/Render → Accept/Retry**. 위험·모호성·재현 요구에 따라 checkpoint, exact validation, Jev 판단을 추가한다. 아래는 제공 실행기의 단계별 사용법이다.

1. **INSPECT** — 목표에 관련된 오브젝트·선택·collection·재질·modifier·transform·mesh 통계·mode·camera·render 설정·저장 여부·linked/shared data를 조사한다. 명시한 대상과 보호 대상을 우선한다. 잘린 결과는 전체 장면의 증거가 아니다.
2. **PLAN** — 목표, `target_objects`, `protected_objects`, 작업, 정확한 검사와 `visual_requirements`를 작은 JSON으로 분리한다. 간단한 작업은 짧은 plan 하나면 된다. [계약과 예제](references/architecture.md)를 따른다.
3. **PRE-JUDGE** — 명확한 금지·shape key/공유 데이터 조건은 코드로 검사한다. 전략·의도·잔여 위험이 다음 행동을 바꿀 때만 [Jev 결정](references/jev-integration.md)을 요청한다. Jev의 선택은 권한이나 필수 검사 면제를 뜻하지 않는다. `safer_alternative`/`human_review`/기권은 자동 실행으로 바꾸지 않는다.
4. **CHECKPOINT / EXECUTE** — 보호 대상을 먼저 식별하고 가역적 modifier/instance/복제를 우선한다. apply는 늦춘다. CLI의 파괴적 선언에는 checkpoint가 자동 생성되고 원본은 보존한다. MCP live code에는 명시한 새 `.blend` checkpoint와 직전 상태 일치가 필요하다. 실행 시간 초과 시 결과를 재조사한 뒤 재시도한다.
5. **COLLECT EVIDENCE** — before/after, script·plan·파일 해시, 실행 로그, preview와 render 설정을 모은다. 후보 `.blend`는 검토용 staging이다. 파일 존재나 exit 0만으로 완료를 선언하지 않는다.
6. **VALIDATE** — `workflow.py validate`로 polygon 감소, 보호 signature, 정확한 속성·modifier·mesh 조건을 검사한다. FAIL은 Jev에 다시 묻지 않고 원인을 수정한다. [검증·증거 계약](references/validation-contract.md)을 따른다.
7. **VISION / POST-JUDGE** — 외형 요구가 있으면 preview를 실제로 열어 관찰하고 이미지 해시·후보 해시·관찰자를 포함한 구조화된 관찰을 기록한다. Jev에 이미지를 이해한다고 가정하거나 자유 서술 이유를 만들게 하지 않는다. 남은 fuzzy 기준만 accept/retry/review로 판단한다. Jev가 없으면 Codex·독립 검토자·사용자의 판단임을 명시한다. 평가 기준이 모호하거나 별도 검토의 이점이 클 때 독립 평가자를 선택한다. 같은 Codex의 판단도 유효한 완료 경로다.
8. **ACCEPT / RETRY** — 검사를 통과하고 필요한 시각 판단을 기록한 뒤 `workflow.py finalize`로 새 최종 경로에 저장한다. 실패는 이전 후보에서 필요한 부분만 수정한다. `benchmark.py retry`는 범위·보존 조건·시도 상한을 정리할 때 쓰는 선택적 도구다. [반복·benchmark](references/benchmark.md)를 참고한다.

## 맥락과 확장

- 전체 장면·raw mesh·이전 로그를 프롬프트에 넣지 않는다. 대상별 요약과 변화량, 실패 검사만 읽고 큰 evidence는 파일로 남긴다. 이미지와 수치 metadata는 분리한다.
- [모델링](references/modeling.md), [재질](references/materials.md), [Geometry Nodes](references/geometry-nodes.md), [애니메이션·리그](references/animation.md), [렌더](references/rendering.md)는 해당 작업에 필요한 문서만 읽는다.
- [실행 예제](references/examples.md)는 단순 장면, 메시 최적화, 20,000 instance 숲, shape key guard, 재질 retry를 제공한다. 스크립트는 범용 Blender API의 사용 예이며 모든 캐릭터·버전의 지원을 보증하지 않는다.
- [검증 기록](references/validation.md)은 과거 실행 근거다. 기록에 없는 환경·기능을 사용 금지나 필수 검증 과제로 바꾸지 않는다. 설치·전역 설정 변경·원격 배포는 요청 범위에 따라 수행한다.

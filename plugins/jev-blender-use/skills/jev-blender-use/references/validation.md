# 검증 기록

2026-09-27, macOS에서 패키지 생성 중 수행한 검증이다. 설치·새 세션 노출·Jev 서비스 정확도는 독립된 확인 대상이다.

## 실행 근거

| 범위 | 실제 실행과 결과 |
| --- | --- |
| Blender 버전 | `Blender --version`: 5.2.2 LTS, build `d13f752e3b9c` |
| 저장본 조사 | 임시 `.blend`의 두 메시를 `blender_use.py run --job ...`으로 조사; inventory와 source SHA-256 생성 |
| 묶음 출력 | 지정한 `Body` 메시의 `asset_bundle`: 256×256 PNG, 일반 `.blend`, GLB 생성; 원본 해시 유지 |
| 미리보기 | `Shirt` 메시의 `preview`: 320×160 PNG 한 개 생성; 두 PNG를 실제 이미지 도구로 열어 대상 색상·형태·프레임 안 포함 확인 |
| 출력 재열기 | 별도 Blender 프로세스에서 `.blend` 재열기와 GLB import; `Body_snapshot` 메시 하나, 크기 2×2×2 확인 |
| Blender 실패 경로 | 기존 출력 거부, 조사 이후 해시 불일치 시 실행 전 반환, 시간 초과, 없는 object, Armature modifier 입력 확인 |
| Jev 오프라인 계약 | 선택·기권·낮은 confidence·동률·잘못된 분포·요청 준비·인증 누락·전체 deadline·잘린 HTTP 응답을 실제 Python 호출과 모의 응답으로 확인 |
| 독립 검토 | 구현과 분리된 서브에이전트가 불변 snapshot을 읽고 Python probe 수행; 수정 후 targeted PASS |

초기 GLB 재가져오기에서 원본 scene의 선택된 무관한 메시가 함께 포함되는 문제를 발견했다. `use_selection`과 `use_active_scene`을 함께 적용하고 재가져오기에서 하나의 메시만 포함되는 것을 확인했다. 초기 출력은 Blender library 파일이어서, 임시 library를 다시 열고 일반 main file로 저장하도록 보완했다. 독립 검토에서 발견한 HTTP 전체 기한과 `IncompleteRead` 처리도 수정 후 오프라인으로 확인했다.

Blender 실행은 기존 사용자 장면·GUI 대신 새 임시 fixture와 별도 background 프로세스에서 수행했다. 명령 stdout, Blender 로그, job/result JSON, 초기 실패 로그와 수정 후 산출물은 작업의 임시 evidence 디렉터리에 보존했다. mock 응답은 Jev의 실제 판단 품질이나 서비스 가용성 증거가 아니다.

## 패키지 검사

- `python3 -m unittest discover -s scripts/tests -v`: 기존 배포·동기화·문서 링크 등 64개 통과. 신규 Plugin을 예상 marketplace inventory에 반영했다.
- `python3 scripts/sync_skill_mirrors.py --package jev-blender-use --write` 및 동일 명령의 읽기 전용 검사: standalone과 Plugin skill의 파일 내용·모드 일치.
- skill-creator의 `quick_validate.py`를 standalone과 Plugin skill에 각각 실행: 통과.
- plugin-creator의 `validate_plugin.py plugins/jev-blender-use`: 통과.
- `py_compile.compile(..., doraise=True)`: 새 실행 스크립트 3개와 변경된 운영/배포 Python 파일 2개의 문법 검사 통과.
- 기존 문서 링크 추출기를 사용한 새 skill 문서 내부 링크 6개 검사: 깨진 경로 없음.
- `git diff --check`: 통과.

## 초기 정적 snapshot 구현의 미확인과 지원 경계

- Blender 4.5 LTS는 목표 baseline이며 이 생성 작업에서 실행하지 않았다. 실제 실행 버전은 5.2.2뿐이다.
- 복잡한 실제 캐릭터·대형 장면·외부 텍스처·linked library·다양한 material의 호환성은 확인하지 않았다.
- 전용 캡슐 데모를 제외한 일반 rig·animation·Geometry Nodes·simulation 전체 작업은 번들 정적 스냅샷 기능의 지원 범위가 아니다. Codex가 실제 목표에 맞는 recipe를 구현해야 한다.
- GLB 재가져오기는 Blender importer로 수행했다. 다른 엔진이나 앱의 importer는 미확인이다.
- 초기 정적 snapshot 검증에서는 실제 TypeSafe 서비스에 요청하지 않았다. 아래 0.2.0 검증에서 합성 장면으로 live API를 호출했지만 일반 선택 정확도·임계값 보정은 여전히 미확인이다.
- 원격 marketplace 공개·로컬 설치·새 세션 로더 노출은 수행하지 않았다. 소스와 로컬 카탈로그 생성은 해당 단계의 증거를 대신하지 않는다.

## 캡슐 로봇 데모 — 2026-09-27

별도 `capsule_demo.py` recipe로 신규 장면을 생성했다. Blender 5.2.2의 background Python API로 제작·bake·렌더했고, 실제 GUI에서 최종 `robot.blend`를 열어 카메라 시점과 타임라인 재생·75프레임 점프 포즈를 확인했다. GUI 클릭으로 모델링한 작업은 아니다.

- Cycles CPU 24 samples, 960×640 PNG 120개를 생성하고 모든 파일을 디코딩했다.
- FFmpeg로 H.264/yuv420p 무음 MP4를 생성했다. `ffprobe -count_frames`는 24fps, 120프레임, 5.000000초를 반환했다. 인앱 브라우저의 실제 재생이 마지막 120프레임·5.00초에 도달한 것을 확인했다.
- 새 Blender 프로세스에서 최종 저장본을 열었다. 8개 뼈 Armature와 실제 Cloth가 있고, 망토의 1–120 baked cache가 파일 안에 남아 있으며 outdated/frame-skip이 false였다. 11개 시점의 evaluated 망토 변형을 수집했다.
- 120프레임의 evaluated 발 메시를 계획 궤적과 비교했다. 최대 중심 오차 3.91×10⁻⁷m, 최저 발 Z 0m, 상자와 X/Y가 겹치는 구간의 최소 수직 여유 0.190075m였다.
- 첫 실행에서 부모 pose 갱신 누락으로 발 미끄러짐·착지 침범을 발견했다. dependency 갱신 후 장면 재생성·Cloth 재bake·재열기 검사를 수행했다. 독립 검토는 최초 CHANGES_REQUIRED, 수정본과 마지막 변경은 PASS였다.
- 주요 9개 포즈와 점프·착지 렌더를 직접 확인했다. 망토의 어깨 연결부는 실제 렌더에서 보이는 틈을 스트랩으로 보완했다.
- 기존 출력 디렉터리에 대한 실제 재실행은 FileExistsError/exit 1로 거부됐고 저장본·manifest 해시는 유지됐다.

이 결과는 해당 절차적 로봇과 Blender 5.2.2에서의 증거다. 일반 캐릭터 리타게팅, 다른 버전, 애니메이션/Cloth의 GLB 전달, Geometry Nodes·유체 등 나머지 기능은 검증하지 않았다. Jev 호출·설치·원격 배포는 수행하지 않았다. 원본 로그·첫 실패·수정본·최종 영상·좌표 기록은 제작 작업의 별도 artifact/evidence 디렉터리에 보존했다.


## 0.2.0 agent loop — 2026-09-27

기존 이름과 HTTP abstraction을 유지하고 CLI/MCP transport, 공통 inspector/guard, validator, decision, benchmark를 분리했다. 현재 호스트의 Blender 5.2.2에서 실제 CLI 예제 16개 단계와 후속 scoped retry를 실행했다.

| 범위 | 관측 결과 |
| --- | --- |
| Health | CLI version·bpy probe 완료. TypeSafe 인증 변수 존재. Codex에 Blender MCP 설정/노출 도구는 없음 |
| Simple scene | cube/plane/camera/light 생성, PNG 관찰, independent Codex verdict로 새 최종 `.blend` 저장 |
| Mesh optimization | evaluated polygons 2,048 → 1,120 (45.3125% 감소), 보호 Head 상태 유지, before/after preview 관찰 통과 |
| Geometry Nodes | depsgraph 20,000 instances. 최초 preview는 turf처럼 보여 retry. 기존 candidate의 spacing/height/framing을 수정하고 개수·재질 유지, 독립 Vision 재관찰 통과 |
| Destructive guard | shape-key mesh의 apply_modifier가 script 실행 전 refused |
| Negative protection | 의도적으로 보호 Head UV를 바꾸면 mesh/evaluated signature 차이를 검출. 보호 Forest의 node grid를 바꾸면 node/instance 차이를 검출. 둘 다 needs_review |
| Checkpoint | byte-copy hash 확인. forest geometry 수정 전 checkpoint 생성 후 원본 유지 |
| Visual retry | magenta preview 실제 관찰 → live Jev retry_material (confidence 0.89) → 재질만 수정 → geometry/transform/modifier와 Head/Camera/Key 검사 PASS → 새 PNG 관찰 → live Jev accept (0.98) → finalize |
| Jev strategy/risk | 응답 model 필드 `jev-1.13.0`. geometry_nodes choice confidence 0.84와 checkpoint_then_execute 0.49는 예제 threshold 0.85 미만으로 needs_codex. 낮은 확신 receipt를 실행기에 넣었을 때 script_executed=false 확인. Codex fallback을 별도 기록해 checkpoint 경로로 진행 |
| Jev completion | 수정 forest 관찰 후 accept confidence 0.90, 코드 검사·image receipt·candidate binding 확인 뒤 finalize |
| MCP | stdio initialize/discovery/call, official/community envelope, stalled-write deadline, 중간 debug marker와 final nonce 구분을 fixture로 검사. 실제 addon 연결/GUI mutation은 미실행 |

첫 Blender 실행의 import path 문제와 modifier IDProperties 지원 차이를 발견해 수정했다. Decimate의 triangle 기반 ratio를 quad polygon 감소율과 동일시한 예제도 실제 검사 실패 후 수정했다. 실패 로그와 초기 후보를 보존했다. 첫 live completion에서 확률 분포 검사 오류가 있었고 이 결과는 사용하지 않았다. 이후 malformed service 응답을 진단 evidence로 보존하도록 보완했으며, 유효한 후속 응답만 소비했다. 임계값을 낮춰 통과시키지 않았다.

독립 구현 검토에서는 보호 signature 범위, candidate/decision/image binding, MCP postguard·deadline·최종 output 식별, bounded context, benchmark provenance와 rule typing을 보완했다. 수치·구조 검사, 시각 관찰, 외부 decision을 분리한 뒤 새 최종 `.blend`로 저장했다.

실행 명령:

```sh
python3 examples/run_examples.py --blender /path/to/Blender.app --output-dir /absolute/new-run
python3 scripts/decision.py strategy --state state.json --send --min-confidence 0.85 --output new-decision.json
python3 scripts/decision.py risk --state state.json --send --min-confidence 0.85 --output new-risk.json
python3 scripts/decision.py completion --state state.json --send --min-confidence 0.85 --output new-post.json
python3 scripts/workflow.py validate --plan run/plan.json --before run/before.json --after run/after.json
python3 scripts/workflow.py finalize --run-dir run --destination new-final.blend --vision vision.json --decision post.json
```

수치 threshold 0.85는 이 합성 예제의 보수적 실험 설정이며 일반 데이터에서 보정된 값이 아니다. live 호출 몇 건은 API/분기 연결 증거이지 품질 향상·비용 절감·판단 정확도 측정이 아니다. benchmark record는 실제 응답과 낮은 확신 이후 Codex fallback을 구분한다.

`python3 -m unittest discover -s scripts/tests -v` 최종 실행은 104개 검사 모두 통과했다. 여기에는 신규 실행·MCP·workflow 계약 검사 40개가 포함된다. 독립 검토도 동일한 40개 검사와 추가 probe를 수행하고 최종 PASS로 마무리했다. Python 단위 검사는 Blender 없는 CI에서 실행하고, 실제 Blender integration은 별도 `examples/run_examples.py`로 실행한다. `.blend` 최종 파일·render receipt·Vision JSON·live decision·accepted 기록은 제작 작업의 외부 artifact directory에 보존했다. Blender 4.5, 실제 MCP addon/GUI 연결, 일반 rig/외부 cache/asset의 전체 의미 보존, 설치·새 세션 노출·원격 배포는 미확인이다.

## 0.2.1 작업 절차 개선 — 2026-09-27

작업 규모에 맞는 절차 선택, `completion-state`/`verdict` CLI, MCP `inspect --plan`과 조사 한도 일치, 생략 가능한 protected 목록 처리, schema/context 복구 지침을 반영했다. 기존 원본 보존과 finalize의 hash·검사 조건은 유지한다.

이번 변경에서는 두 skill의 `quick_validate.py`, Plugin의 `validate_plugin.py`, mirror 동기화 검사, `git diff --check`, 변경 Python 모듈 2개의 `py_compile`, 두 CLI의 `--help`, 두 skill 사본의 로컬 문서 링크 62개를 확인했다. 전체 단위 검사·Blender 예제·live MCP/Jev를 다시 실행하지 않았다. 위 104개 PASS와 실제 Blender 결과는 0.2.0 당시의 기록이다. 별도 환경의 사전 시험은 사용 전 필수 조건이 아니며, 실제 작업에 필요한 조사와 결과 확인으로 진행한다.

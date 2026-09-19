# Jev Workbench 0.1.0 — 단독 스킬

이 폴더 하나에 SKILL.md, Python 경량 실행기, 12개 활용 절차·템플릿·합성 응답이 들어 있다. 목적별 진입 스킬 없이도 모든 모드를 사용한다. Python 3.10 이상, 표준 라이브러리만 필요하다.

## 설치

압축을 풀어 `jev-workbench` 폴더 전체를 사용 중인 스킬 루트(예: `$HOME/.agents/skills`) 아래에 둔다. 같은 이름의 기존 스킬이 있으면 덮어쓰지 말고 내용을 비교한다. 이 ZIP은 사용자 머신에 자동 설치되거나 Codex 설정을 변경하지 않는다. 7개 목적별 스킬과 설치기가 필요하면 전체 `jev-skills-collection-0.1.0.zip`을 사용한다.

## 명시적 사용

```text
$jev-workbench 현재 작업의 구현 대안과 근거를 준비하고 Jev가 방향을 선택하도록 해주세요. 전송할 입력을 먼저 보여주세요.
```

다른 요청: 관련 문서 후보 정렬, 버그 제보 분류, 완료 보고의 근거 확인, 추가 테스트 우선순위, 제품 문구 대안 선택, 설치된 스킬 선택, 저장된 판정 평가. 해당 절차만 선택해 읽는다.

## API 키 없는 프로그램 점검

이 폴더에서 다음을 실행한다. `jev-demo`가 이미 있으면 새 폴더명을 사용한다.

```bash
python3 scripts/jev_cli.py doctor
python3 scripts/jev_cli.py prepare --input templates/plan-choice.json --out ./jev-demo
python3 scripts/jev_cli.py run ./jev-demo --fixture fixtures/plan-choice.response.json
```

합성 응답을 이용하는 프로그램 시험이며 실제 Jev 호출이나 모델 정확도 측정이 아니다. 실제 호출은 환경변수 TYPESAFE_API_KEY, 실제 자료로 바꾼 입력, 전송 범위 승인, 명시적 `--live --approved-sha`가 필요하다. 정확한 절차와 제한은 `references/runtime.md`를 읽는다.

## 상태와 범위

공식 Jev CLI가 아니라 이 모음에서 새로 작성한 cooperative 실행기다. 과거 설계의 전체 결정 관리기·강제 재심·격리 실행은 구현하지 않았다. 판정은 테스트 성공이나 실행 권한을 대신하지 않는다. 2026-09-19 전체 모음에서 60개 오프라인 테스트를 통과했으나 실제 API 왕복, macOS, Codex 내 자동 활성화는 시험하지 않았다. 전체 보고서와 테스트 소스는 전체 ZIP에 있다.

라이선스: 이 신규 스킬·실행기·템플릿은 동봉한 MIT LICENSE. 외부 원문 스킬은 전체 모음의 vendor에 별도로 있다.

## codex-skills 통합 배치

이 저장소에서는 현재 폴더가 루트형 스킬입니다. 설치기·통합 안내·테스트 위치는 `../docs/jev/README.md`를 확인하세요. 외부 참고 스냅숏은 `../docs/jev/vendor/`에 있으며 자동 활성화하지 않습니다.

# 실행기 계약 — Jev Skills Kit 0.1.1

## 위치와 범위

`python3 <jev-workbench의 실제 경로>/scripts/jev_cli.py ...`를 호출한다. Python 3.10 이상, 표준 라이브러리만 사용한다. npm/pip 설치는 필요 없다. 공식 CLI나 이전 대화에서 제안한 TypeScript `jev-decide`의 완성 구현이 아니다. CLI 프로토콜을 실제로 확인하지 않고 임의의 `jev decide` 명령을 생성하지 않는다.

이 버전은 명시적인 입력의 동결·전송·응답 검사·로컬 기록·간단한 freshness·오프라인 Choice 평가를 제공한다. OS 수준 격리, 전체 도구 호출 강제, 원자적 소스 적용, 완성형 appeal 서버, 전역 중복 방지, 사용자 인증 서명은 제공하지 않는다.

## 명령

| 명령 | 외부 통신 | 입력과 결과 |
|---|---|---|
| `doctor` | 없음 | Python·키 존재 여부·고정 API 주소·템플릿 수. 키 값은 출력하지 않음 |
| `templates` | 없음 | 사용 가능한 12개 템플릿 이름 |
| `prepare --input FILE --out DIR [--root ROOT --watch FILE]` | 없음 | 고정 packet·payload·manifest 생성, 승인 해시·전송 미리보기 반환 |
| `run DIR --fixture FILE` | 없음 | 합성 응답으로 흐름 시험. origin=fixture, 위임 후속 진행 불가 |
| `run DIR --external-response FILE` | 없음 | 기존 CLI에서 얻은 응답 가져오기. origin=external, provenance 미검증으로 위임 진행 불가 |
| `run DIR --live --approved-sha HASH` | 있음 | 고정 TypeSafe 주소에 한 번 요청. 환경변수 키 사용 |
| `status DIR` | 없음 | 짧은 상태·receipt·실패 확인 |
| `check DIR [--require-actionable]` | 없음 | 입력·응답·감시 파일 상태 확인 |
| `evaluate --cases FILE` | 없음 | 이미 저장한 Choice 응답과 허용 선택 집합 비교. 운영 receipt 발급 안 함 |

### 처음에는 합성 예제로

```bash
SKILL_DIR="/실제/경로/jev-workbench"
python3 "$SKILL_DIR/scripts/jev_cli.py" doctor
python3 "$SKILL_DIR/scripts/jev_cli.py" prepare \
  --input "$SKILL_DIR/templates/plan-choice.json" --out ./jev-demo
python3 "$SKILL_DIR/scripts/jev_cli.py" run ./jev-demo \
  --fixture "$SKILL_DIR/fixtures/plan-choice.response.json"
python3 "$SKILL_DIR/scripts/jev_cli.py" status ./jev-demo
```

이 예제의 선택·확률·확신도는 테스트용으로 만든 값이다. 실제 모델의 실력이나 API 접속 성공을 보여주지 않는다. fixture 디렉터리를 나중에 같은 ID의 live 결과로 바꿀 수 없다.

## 실제 실행

1. 관련 템플릿을 작업용 파일로 복사한다.
2. 요구사항·현재 관찰·후보·근거·정책을 실제 자료로 바꾼다. 질문에는 대상 state 경로를 명시한다. 질문 ID 자체의 의미에 의존하지 않는다.
3. 사용자가 위임한 범위만 `authority=delegated`로 둔다. 그 경우 최종 Choice와 NEEDS_EVIDENCE/REJECT_ALL이 있어야 한다.
4. 번들 예제를 그대로 보내지 않고 실제 작업용 입력을 작성한 뒤 `is_example=false`, 실제 task_id와 정책 revision을 설정한다. 승인된 합성 평가 데이터도 `authority=evaluation`인 실제 평가 입력으로 사용할 수 있지만 사용자 저장소의 관측으로 표현하지 않는다. `is_example=false` 자체는 사용자 승인이나 데이터 진실성의 증명이 아니다.
5. 로컬 비공개 위치에 `prepare`한다. `--watch`는 관련 파일을 해시로 연결할 뿐 파일 내용을 payload에 추가하지 않는다. 코드 발췌가 필요하면 승인된 내용만 request.state에 직접 넣는다.
6. 생성된 `payload.json` 전체를 확인하고 전송 범위가 현재 사용자 요청 또는 프로젝트 정책으로 이미 승인되었는지 확인한다. 승인되지 않은 범위가 있을 때만 추가 승인을 받는다. 해시 옵션을 에이전트가 계산했다는 사실만으로 승인됐다고 주장하지 않는다.
7. 사용자 실행 환경에 `TYPESAFE_API_KEY`를 제공한다. 키를 CLI 인수·채팅·로그·JSON에 넣지 않는다. 설치기는 키를 읽거나 만들지 않는다.
8. `prepare`가 출력한 정확한 `approval_sha256`으로 호출한다.

```bash
python3 "$SKILL_DIR/scripts/jev_cli.py" prepare \
  --input ./my-real-decision.json --out ./jev-run-real \
  --root /absolute/project --watch Sources/Sync/DeleteMerge.swift

# payload.json 검토와 실제 전송 승인이 끝난 뒤에만 실행한다.
# API 키는 실행 프로세스의 환경변수에 이미 제공되어 있어야 한다.
python3 "$SKILL_DIR/scripts/jev_cli.py" run ./jev-run-real \
  --live --approved-sha "<prepare가 반환한 approval_sha256>"
python3 "$SKILL_DIR/scripts/jev_cli.py" check ./jev-run-real --require-actionable
```

마지막 `--require-actionable`은 delegated 선택에 따른 구현용이다. advisory/evaluation은 `check ./jev-run-real`을 사용한다. 정상적인 보조 판정도 위임 실행 자격 검사를 통과하지 못하는 것이 의도된 동작이다.

API 주소는 `https://api.typesafe.ai/v1/systemone`로 고정한다. 리다이렉트와 환경 프록시 자동 사용을 허용하지 않는다. 기업 프록시가 필수인 환경은 별도 검토된 adapter가 필요하다. 기본 요청 타임아웃은 30초(1–120초 범위로 조정 가능)이며 자동 재시도는 없다.

## 입력의 의미

외부 API에는 `request`의 model/state/questions만 전송한다. task_id/workflow/authority/policy/lineage/감시 경로는 로컬 packet에만 있다. 모델이 판단해야 할 사용자 기준은 반드시 **request.state** 또는 질문 instructions/criteria에도 명시한다. 로컬 policy는 결과 해석의 연결 정보이지 원격 모델에 보이지 않는 마법의 규칙이 아니다.

`model`은 `jev-X.Y.Z` 형식의 고정 버전 또는 `jev-latest`/`jev-preview`를 사용한다. 고정 버전은 응답 모델과 일치해야 한다. 별칭은 실제 반환 버전 또는 같은 별칭을 수용하고 반환값을 그대로 기록한다. Choice 옵션 설명은 이름만으로 충분하면 `null`을 사용할 수 있다.

0.1.1은 후보와 criteria의 JSON 객체 순서를 보존해 전송한다. `payload.json`의 표시용 공백을 제거한 UTF-8 전송 본문의 SHA-256이 `payload_sha256`이며 manifest와 receipt에 기록된다. `approval_sha256`은 이 전송 해시·packet 해시·감시 상태를 함께 연결한다. `packet_sha256`은 의미 비교용 정규화 해시이므로 객체 순서만 바꾸면 같을 수 있다. 순서 실험은 `payload_sha256`과 승인 해시로 구분한다. 준비한 뒤 순서만 바꾸어도 재검토·재준비해야 한다.

- `authority`: delegated / advisory / evaluation. 서로 구분한다.
- `policy.revision`: 사용자 기준의 버전 식별자. 인증 서명이 아니다.
- `policy.decision_question`: 최종 Choice 질문 ID 또는 null.
- `policy.min_confidence`: null 또는 사전 검증된 분포 집중도 기준. 기본값을 임의로 0.9로 고정하지 않는다.
- `lineage`: 새로운 근거/후보/사용자 승인 기준 변경이 있을 때 원 packet 해시와 구체적 변경 이유를 연결한다. CLI는 필드 형식만 검증하며 변화의 실질성과 사용자 승인을 증명하지 못한다.

## 응답의 의미

`receipt.json`은 이 도구의 정리 형식이며 Jev API 원 응답이 아니다. 원 응답은 `response.json`에 별도 보존한다.

- `decision_status=SELECTED`: 정의된 후보 중 하나를 선택했음. 실행 승인·테스트 통과·정답 증명이 아님.
- `NEEDS_EVIDENCE`, `REJECT_ALL`, `NEEDS_REVIEW`: 그 뜻대로 추가 근거·후보 재구성·검토로 연결.
- `EVALUATED`: advisory/evaluation 신호가 있음. 이것을 Jev의 최종 선택으로 바꾸지 않음.
- `origin=fixture|external`: 모델 직접 호출로 인증한 live 결과가 아님.
- `eligible_for_delegated_followup`: live + non-example + delegated + SELECTED의 로컬 검사 결과일 뿐 사용자 권한이 아님.
- `execution_authorized`: 항상 false. 이 CLI가 사용자 실행 승인을 발급하지 않음을 명시.

종료 코드 0은 명령이 성공적으로 상태를 처리했다는 뜻이다. JSON 상태를 반드시 읽는다. 구조 오류는 보통 2, freshness/잠금 문제는 3, 서비스/전송 오류는 4다. `--require-actionable` 전제 불충족도 오류이며 모델 결정의 새로운 선택값이 아니다.

## 데이터·동시성·장애

원 입력, payload, 응답은 민감할 수 있다. 준비 디렉터리는 0700, JSON은 0600으로 생성하지만 같은 사용자 권한의 공격자를 막지 못한다. 가능하면 Git 밖 비공개 폴더를 사용한다. 삭제는 사용자가 별도로 수행한다. `.gitignore`를 자동 수정하지 않는다.

동일 실행 디렉터리의 정상 응답은 재사용한다. 저장 전 실행 시도 흔적이 있고 응답이 없으면 재호출하지 않는다. 전송 실패는 이미 서버가 처리했을 가능성을 남긴다. 동일 packet을 다른 디렉터리에 복제하여 재요청하는 것은 이 버전이 전역 차단하지 못한다. 이를 우회 재판정으로 사용하지 않는다.

0.1.0의 실행 폴더는 원래 해시 계약으로 읽기만 지원한다. `status`/`check`와 저장된 응답 반환은 가능하지만 새 전송과 `--require-actionable`은 거부한다. 이전 시도·응답을 보존하고 자동 이관하거나 재전송하지 않는다. 아직 보내지 않은 입력을 새 버전에서 사용하려면 새 폴더에 준비하고 달라진 전송 순서를 검토한다.

invalid response도 원 JSON을 보존하고 오류로 기록한다. 401/422/429/529 등을 성공으로 바꾸지 않는다. 자동 재시도 없는 경량판이므로 정당한 통신 복구는 이전 요청 상태를 확인한 뒤 새 기록과 이유를 남긴다. 과금·원격 실행 exactly-once는 보장하지 않는다.

`--watch`가 비어 있으면 **저장소 상태 freshness는 검증하지 않는다**. 지정 파일만 확인하며 Git 전체·untracked 전체를 검사하지 않는다. 해시와 로컬 receipt는 인증 체계가 아니다. macOS의 `/tmp`→`/private/tmp`, `/var`→`/private/var` 시스템 별칭만 허용하고 그 아래 사용자 생성 symlink·경로 이탈은 계속 거부한다. 이 방어가 강제 샌드박스가 되지는 않는다.

## 예산과 설명

262,144바이트 요청, 64개 질문, 응답 2MiB, 감시 파일 16MiB는 이 도구의 로컬 보호 한도이며 TypeSafe의 공식 토큰 한도가 아니다. 한국어 바이트 수는 토큰 수가 아니다. 실제 한도는 실행 전 현재 공식 문서와 서비스 오류를 확인한다.

Jev는 자유형 설명을 반환하지 않는다. 점수가 낮은 이유는 원문 조사로 Codex가 해석하며 그렇게 표시한다. 모든 독립 질문은 다른 질문의 답을 보지 못한다. 1차 평가 결과가 최종 선택의 입력이어야 한다면 별도 2차 요청을 만든다.

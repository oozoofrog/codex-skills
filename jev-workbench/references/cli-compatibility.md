# 기존 Jev CLI와 연결하기

이 대화에서 제안된 `jev-decide prepare/decide/check/appeal`은 설계 이름이었다. 이 번들은 그 명령이 이미 존재한다고 가정하지 않는다. 추가된 실행기는 `python3 .../jev_cli.py`이며 별개다.

기존 CLI가 있다면 사용자가 지정한 바이너리를 우선 확인한다. 먼저 로컬 `--version`/`--help`를 읽고, 실제 지원 옵션과 인증 방식만 사용한다. 알 수 없는 외부 프로그램을 설치하거나 첫 실행에서 로그인·업데이트·네트워크가 발생하도록 무작정 실행하지 않는다. 프로그램의 성격을 먼저 확인한다.

## 공통 교환 형식

이 번들의 `prepare`가 만든 `payload.json`은 TypeSafe HTTP API의 model/state/questions 객체다. 기존 CLI가 명시적으로 이 객체를 받는다는 것을 확인한 경우에만 전달한다. 다른 형식이면 어댑터를 작성하고 오프라인 응답 계약 시험을 통과시킨다.

결과 JSON을 가져올 때:

```bash
python3 "$SKILL_DIR/scripts/jev_cli.py" run ./prepared \
  --external-response ./existing-cli-response.json
```

외부 실행기의 응답 파일만으로 실행 출처·동일 입력·서버 응답 무결성을 증명하지 못하므로 `origin=external`로 기록한다. 이 경량판의 `check --require-actionable`은 이 결과를 거부한다. 이를 live로 이름만 바꾸지 않는다.

## 이전 TypeScript 설계로 확장하기

1. `prepare`의 packet/payload 해시와 현재 데이터 수집 규칙을 공식 내부 계약으로 승격한다.
2. 인증된 결과 저장소, 전역 재심·동일 결정 식별, 권한 있는 실행기와 연결한다.
3. CLI→MCP→훅이 같은 core를 호출하게 한다. 어댑터마다 판단 의미를 재정의하지 않는다.
4. 실제 Codex 바이너리의 지원 기능을 확인한 후에만 선택적으로 연결한다.
5. 사용자 모델·provider·로그인·기존 Codex CLI는 변경하지 않는다.

이 번들은 provider 프록시, 모델 라우터, 자동 훅 설치, MCP 서버를 포함하지 않는다.

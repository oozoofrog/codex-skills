# 선택적 Jev 후보 선택

정확한 object 이름이 이미 있거나 규칙만으로 결정할 수 있으면 실행기에 직접 전달한다. 이 선택기는 하나의 의미 판단을 하나의 Choice로 수행하며 Blender를 실행하지 않는다. 대화 전체, 장면 바이너리, 스크린샷을 보내지 않는다.

## 입력과 요청 준비

`source_sha256`는 `inspect` 결과에서 복사한다. 후보 ID는 해당 저장본의 실제 object 이름으로 유지하고, 설명에는 판단에 필요한 최소 사실만 넣는다. 후보 수는 1..254개다. 후보가 많으면 코드로 먼저 좁히고 후보 누락 가능성을 확인한다.

```json
{
  "source_sha256": "replace-with-the-64-character-sha256-from-inspection",
  "candidates": [
    {"id": "Body", "description": "기본 인체 메시"},
    {"id": "Shirt", "description": "상체 의류 메시"}
  ]
}
```

```bash
python3 scripts/jev_select.py --candidates /absolute/candidates.json \
  --request '상체 의류 메시 하나를 선택' > /absolute/prepared-request.json
```

기본 동작은 `prepared` JSON을 출력한다. 전송할 `state`와 질문을 먼저 확인할 수 있으며 네트워크·API key가 필요 없다. source hash는 출력의 선택 결속 정보로 보존하며 모델 state에는 넣지 않는다.

## 실제 전송

사용할 때 현재 [HTTP API](https://docs.typesafe.ai/api)와 [모델 목록](https://docs.typesafe.ai/models)을 확인한다. `typesafe-ai` 스킬이 설치돼 있으면 질문 설계에 활용할 수 있지만 이 패키지의 필수 의존성은 아니다.

`TYPESAFE_API_KEY`를 환경으로 공급한다. 명령 인자·job·출력·로그에 키를 넣지 않는다. `--send`는 후보 설명과 요청을 TypeSafe 서비스로 전송한다. 이 기능의 사용 권한이 외부 전송 범위를 자동으로 늘리지는 않는다.

```bash
python3 scripts/jev_select.py --candidates /absolute/candidates.json \
  --request '상체 의류 메시 하나를 선택' --send --min-confidence 0.9
```

`0.9`는 호출 형식을 보여주기 위한 예시이며 이 작업에서 검증된 임계값이 아니다. 사용할 자료와 오류 영향에 맞게 결정한다. 전송에는 명시한 임계값이 필요하다. 기본 model alias는 `jev-latest`; 재현성이 필요하면 현재 존재하는 구체 모델을 `--model`로 지정하고 실제 응답 model도 기록한다.

API 응답의 타입·후보 ID·확률 집합·유한 값·합·선택과 분포의 일치·confidence·실제 model을 검사한다. 최상위 확률이 동률이면 모호한 선택으로 돌려보낸다. 요청은 별도 자식 프로세스에서 한 번 전송하고 전체 실행을 30초로 제한하며 redirect를 거부한다. 소켓 timeout만으로 전체 기한을 보장하지 않는다. 잘린 HTTP 응답·서비스 장애도 구조화된 실패로 반환하며 무한 재시도하지 않는다.

## 결과와 적용

- `selected`: 단일 후보와 원 응답 분포를 반환한다. `execution_authorized`는 항상 false다.
- `needs_codex`: 명시적 기권, 모호함, 낮은 confidence, 인증 누락, 잘못된 입력·응답, 서비스 오류다. 원인을 확인하고 직접 해석·추가 증거 수집·질문 개선 중 적절한 방법을 선택한다.
- 후보에 적합한 답이 없거나 동등한 후보가 여럿이면 예약 선택지 `__abstain__`를 사용한다. 복수 선택 요청도 단일 선택기로 해결하지 않는다.
- `source_sha256`, `candidates_sha256`, `request_sha256`로 선택이 어떤 입력에 속하는지 기록한다. Codex는 선택 결과의 source hash와 현재 조사값을 대조하고 실제 ID가 inventory에 있는지 확인한 뒤 job을 만든다. 실행기도 job의 source hash를 실제 파일과 다시 대조한다.
- 후보 설명은 구조·명칭에 대한 근거다. 이를 실제 포즈·의상 외형·시각적 품질의 증거로 사용하지 않는다. Jev는 현재 텍스트·구조화 상태를 판단하며 이미지·음성·동영상을 직접 보지 않는다.

[State와 지원 모달리티](https://docs.typesafe.ai/concepts/state), [Choice](https://docs.typesafe.ai/primitives/choice), [confidence](https://docs.typesafe.ai/confidence), [함수 선택 예제](https://docs.typesafe.ai/cookbooks/function_calling)를 2026-09-27 기준으로 확인했다. 응답 타입은 인터페이스를 제한하며 판단의 진실성을 보증하지 않는다. 실제 서비스 호출 검증 여부는 [검증 기록](validation.md)을 따른다.

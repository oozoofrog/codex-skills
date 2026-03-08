# Validation Loop

Builder handoff를 받은 뒤, 메인 에이전트가 리뷰 전에 직접 수행하기.

## 1) handoff 사실 확인하기

- worker가 언급한 수정 파일을 실제로 열어보기
- 요약과 실제 코드가 일치하는지 확인하기
- Task Brief 범위를 넘는 변경이 없는지 확인하기

## 2) 핵심 리스크 재대조하기

다음 항목을 Task Brief와 다시 비교하기.
- 성공 기준
- 실패 기준
- 수정 금지 범위
- 회귀가 나면 안 되는 기능
- MainActor / cancellation / 중복 실행 / 에러 상태

## 3) 최소 검증 명령 직접 실행하기

가능한 항목 중 최소 하나를 직접 실행하기.
- typecheck
- build
- test
- lint
- 앱 실행 또는 수동 QA

다만 다음 조건이면 `typecheck`만으로 끝내지 말기.
- `MainActor`, `Sendable`, actor 격리, cancellation, `.task`, SwiftUI lifecycle, SwiftData threading이 핵심인 작업
- Swift 6 strict concurrency 경고/오류 가능성이 있는 작업

이 경우 우선 검토하기.
- `swift test`
- `swift build`
- `xcodebuild test`
- strict concurrency 옵션이 포함된 build/test

구조 마이그레이션이면 가능하면 다음 순서로 검증하기.
- source-of-truth 결정 확인
- generator(`xcodegen`, `tuist`) 재생성
- framework 또는 하위 모듈 build
- dependent framework build
- app build
- app test
- 문서/기본 명령 동기화 확인

실행이 불가능하면 이유를 적고 남은 위험으로 올리기.

## 4) worker 주장 검증하기

다음을 그대로 믿지 말고 직접 확인하기.
- “테스트 추가했다” → 실제 테스트 파일과 assertion 확인
- “중복 실행 방지했다” → guard, task handle, state gate 확인
- “취소 처리했다” → `CancellationError`, `Task.checkCancellation()`, task lifetime 확인
- “에러 처리했다” → 사용자 노출 상태와 dismiss/reset 흐름 확인

## 5) 리뷰 입력 품질 보장하기

리뷰어에게 넘길 때 아래를 같이 넘기기.
- 수정된 실제 파일 경로
- 직접 실행한 검증 명령과 결과
- 여전히 불확실한 지점
- reviewer가 특히 깨봐야 할 위험

## 6) 검증 실패 처리하기

- 컴파일, 빌드, 테스트가 실패하면 구현을 완료로 보고하지 말기
- 실패한 명령과 핵심 오류를 그대로 남기기
- 바로 수정 가능한 오류면 즉시 수정 루프로 되돌아가기
- 즉시 수정이 어렵다면 다음 수정안 1개 이상을 구체적으로 제시하기
- reviewer에게 넘길 때도 “검증 실패 상태”를 숨기지 말기

## 7) 종료 조건 확인하기

다음 중 하나면 아직 종료하지 않기.
- 검증 명령을 하나도 직접 실행하지 않음
- 수정 파일을 직접 열어보지 않음
- concurrency 민감 작업인데 `typecheck`만 실행함
- 검증 실패가 있었는데 완료처럼 보고함
- 리뷰 결과가 형식 불량 또는 피상적 요약임
- 남은 위험이 있는데 사용자에게 명시하지 않음

구조 마이그레이션이면 다음도 아직 종료 조건 아님.
- package product와 framework product가 동시에 링크된 상태
- source-of-truth 경로가 둘 이상 남아 있음
- generator 설정과 실제 프로젝트 파일이 불일치함
- 문서가 여전히 옛 검증 명령/옛 경로를 가리킴

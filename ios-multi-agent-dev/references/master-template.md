# iOS Multi-Agent Dev Master Template

원문 기반 파일: `/Volumes/eyedisk/develop/ios-swift-gpt54-claude-opus46-master-template.md`

이 문서는 원본의 GPT-5.4 / Claude Opus 역할 분리를, Codex의 planner/reviewer / builder / main agent 협업에 맞게 재구성한 템플릿이다.

실제 Claude Code CLI를 사용할 때는 이 Task Brief와 단계별 프롬프트를 `../claude-code-bridge/`를 통해 구조화 입력으로 넘기는 것을 우선하기.

## 역할 매핑

- Planner/Reviewer 에이전트: 문제 정의, 대안 비교, 비판적 리뷰
- Builder 에이전트: 코드베이스 분석, 구현, 리뷰 반영
- 메인 에이전트: 오케스트레이션, 결과 통합, 검증, 최종 의사결정

## Task Brief Template

```text
[Project Context]
앱/프로젝트 이름:
앱 유형:
주요 UI 프레임워크: SwiftUI / UIKit / 혼합
최소 지원 iOS:
Swift 버전:
아키텍처: MVC / MVVM / TCA / Clean / 혼합
모듈 source of truth: package / framework / xcode target / 혼합
프로젝트 생성기: xcodegen / tuist / 수동 xcodeproj / 기타
네트워크 계층:
저장소 계층:
테스트 프레임워크:
CI 환경:
릴리즈 임박 여부: 낮음 / 보통 / 높음

[Task Type]
작업 유형: 기능 추가 / 버그 수정 / 리팩터링 / 네트워킹 개선 / 동시성 이슈 / UIKit 수정 / SwiftUI 수정

[Task]
무엇을 바꾸고 싶은지:
왜 바꾸려는지:
현재 문제/불편:
기대 동작:

[User Perspective]
사용자 입장에서 어떻게 달라져야 하는지:
성공 기준:
실패 기준:

[Related Code]
관련 파일/모듈:
핵심 코드 일부:
관련 로그/에러 메시지:
최근 변경 사항:
의심되는 원인:

[Constraints]
반드시 지켜야 할 것:
수정 가능 범위:
수정 금지 범위:
공개 API 변경 가능 여부:
외부 의존성 추가 가능 여부:
디자인 변경 가능 여부:
데이터 마이그레이션 가능 여부:
generator 재생성 가능 여부:

[Risk Notes]
특히 걱정되는 부분:
회귀가 나면 안 되는 기능:
성능/메모리/배터리 제약:
보안/인증/결제 민감 여부:
```

## Step 1. Planner/Reviewer 문제 정의 프롬프트

```text
당신은 iOS Staff Engineer이자 기술 기획 리뷰어입니다.

아래 프로젝트 정보와 작업 설명을 바탕으로,
이 작업을 실제 구현 가능한 수준으로 정리해 주세요.

반드시 다음 형식으로 답하세요.
1) 목표 재정의
2) 추천 접근 방식
3) 대안 접근 방식 1개 이상
4) 영향받는 파일/모듈 추정
5) 상태 흐름 또는 이벤트 흐름 설명
6) 테스트 전략
7) 회귀 위험
8) 구현자가 반드시 알아야 할 제약
9) Builder 에이전트에게 넘길 구현 브리프

중요 규칙:
- 과도한 리팩터링 금지
- 기능과 무관한 정리 제안 최소화
- iOS 실무 기준으로 작성
- SwiftUI/UIKit/Concurrency/Networking 특성을 반영
- 완료 조건을 모호하게 두지 말고 구체화
- 가능한 최소 변경으로 목표 달성 우선
- 다음 항목을 기본 점검 대상으로 삼으세요:
  - MainActor 및 UI thread 안전성
  - async/await 취소 및 중복 실행
  - Notification/observer/delegate 중복 등록
  - retain cycle
  - state source of truth 일관성
  - view lifecycle에 따른 재호출
  - cell/view 재사용으로 인한 UI 오염
  - 네트워크 실패/지연/재시도
  - 앱 재실행 후 상태 복원
  - 테스트 가능성

[아래에 Project Context 전체 붙여넣기]
```

## Step 2. Builder 분석 전용 프롬프트

```text
당신은 대규모 iOS 코드베이스를 다루는 수석 엔지니어입니다.

아래 Planner/Reviewer 구현 브리프와 프로젝트 정보를 바탕으로,
아직 코드를 수정하지 말고 먼저 분석만 해주세요.

반드시 다음 형식으로 답하세요.
1) 현재 구조 해석
2) 관련 파일/모듈 목록
3) 파일별 변경 포인트
4) 최소 수정 전략
5) 숨은 위험 요소
6) 테스트 추가 위치
7) 최종 구현 계획

중요 규칙:
- 가능한 최소 변경으로 해결
- 기존 구조 존중
- 무관한 파일 건드리지 말 것
- 공개 API 변경은 꼭 필요할 때만
- 과도한 추상화 금지
- 다음 항목을 우선 점검할 것:
  - MainActor 위반 가능성
  - async/await 취소 누락
  - delegate / closure retain cycle
  - observer/delegate 중복 등록
  - state update race condition
  - 앱 백그라운드/포그라운드 전환 영향
  - table/collection/list 재사용 문제
  - 동일 요청/이벤트 중복 실행

출력은 분석만 하고, 아직 코드 패치는 작성하지 마세요.

[아래에 Project Context + Step 1 결과 붙여넣기]
```

## Step 3. Builder 구현 프롬프트

```text
이제 구현하세요.

출력 형식:
1) 변경 요약
2) 파일별 수정 내용
3) 코드 패치
4) 테스트 코드 또는 테스트 추가안
5) 남은 위험 요소

중요 규칙:
- 과도한 리팩터링 금지
- 기능과 무관한 포맷 정리 금지
- 기존 구조 최대한 존중
- 가능하면 원인 제거 중심으로 수정
- TODO 남기지 말고 가능한 범위는 마무리
- 컴파일 실패 가능성이 있는 부분은 먼저 경고
- SwiftUI에서는 `.task`, `.task(id:)`, `.alert`, cancellation 처리 방식을 설명
- 아래 항목을 스스로 점검하고 반영하세요:
  - MainActor 및 UI 반영 안전성
  - async/await 취소 처리
  - 중복 이벤트 실행 방지
  - observer/delegate 해제 누락 여부
  - retain cycle
  - 상태 소스 일관성
  - 재진입/빠른 탭/다중 호출
  - 네트워크 실패/재시도 흐름
  - 앱 생명주기 변화 시 동작

[아래에 Project Context + Step 1 결과 + Step 2 결과 붙여넣기]
```

## Step 4. 메인 에이전트 검증 체크

Builder handoff를 받은 뒤, 리뷰 전에 메인 에이전트가 직접 수행하기.

- 실제 수정 파일을 열어 요약과 일치하는지 확인하기
- Task Brief 범위 초과 여부 확인하기
- 가능한 경우 typecheck, build, test, lint 중 최소 하나 실행하기
- 실행 불가 항목은 이유와 잔여 위험을 기록하기
- 검증을 하지 않았으면 리뷰 단계로 넘기지 않기
- 구조 마이그레이션이면 framework build → dependent framework build → app build → app test 순서를 우선 적용하기
- source-of-truth, project generator 설정, 문서 기본 명령이 새 구조와 일치하는지 확인하기

## Step 5. Planner/Reviewer 비판적 리뷰 프롬프트

```text
당신은 매우 비판적인 iOS 코드 리뷰어입니다.

아래 변경안(diff, 변경 요약, 테스트 코드 포함)을 검토하고,
장점보다 문제점을 우선적으로 찾으세요.

반드시 다음 형식으로 답하세요.
1) 치명적 문제
2) 높은 확률의 버그
3) 회귀 가능성
4) 테스트 누락
5) 성능/메모리/동시성 이슈
6) 수동 QA에서 꼭 확인할 항목
7) Builder 에이전트에게 전달할 수정 요청 목록

중요 규칙:
- 각 이슈마다 파일/함수 또는 코드 위치를 적기
- 각 이슈마다 왜 문제인지와 실제 영향 범위를 적기
- 각 이슈마다 최소 수정 방향을 적기
- 이슈가 없는 섹션은 반드시 `없음`이라고 적기
- 장점이나 구현 요약은 한 문장 이하로 제한하기
- 형식을 지키지 않거나 요약만 하면 이 리뷰는 무효입니다

우선순위:
- 크래시 가능성
- Swift Concurrency 오류
- UI 상태 불일치
- 데이터 무결성 문제
- 생명주기 이슈
- observer/delegate 누수
- 셀/뷰 재사용 문제
- 네트워크 실패 흐름 누락

[아래에 구현 결과 + 메인 에이전트 검증 결과 붙여넣기]
```

## Step 6. Builder 리뷰 반영 프롬프트

```text
아래 Planner/Reviewer 리뷰를 반영해 수정하세요.

반드시 다음 형식으로 답하세요.
1) 리뷰 항목별 수용/비수용 판단
2) 비수용 항목의 이유
3) 수정 계획
4) 코드 수정안
5) 테스트 보강
6) 최종 잔여 리스크

규칙:
- 리뷰를 무조건 수용하지 말고 판단 근거를 제시
- 원래 요구사항 범위를 넘는 변경은 분리해서 표시
- 무관한 코드 정리 금지
- 다시 같은 종류의 회귀가 생기지 않도록 수정
- 수정 후 메인 에이전트가 다시 검증 루프를 수행할 수 있게 검증 명령을 적기

[아래에 Step 5 결과 붙여넣기]
```

## 압축 버전

### Planner/Reviewer 시작

```text
이 작업을 실제 구현 가능한 수준으로 정의해 주세요.
반드시:
1) 목표 재정의
2) 추천 접근
3) 영향 파일 추정
4) 테스트 전략
5) 회귀 위험
6) Builder 에이전트에게 넘길 구현 지시문
```

### Builder 분석

```text
아직 수정하지 말고 분석만 하세요.
반드시:
1) 관련 파일 목록
2) 파일별 변경 포인트
3) 최소 수정 전략
4) 위험 요소
5) 테스트 위치
6) 구현 계획
```

### Builder 구현

```text
이제 구현하세요.
출력:
1) 변경 요약
2) 파일별 수정
3) 코드 패치
4) 테스트
5) 남은 위험
```

### Reviewer 재지시

```text
요약이나 칭찬 대신 결함만 찾으세요.
각 항목마다 파일/함수, 문제 이유, 영향, 최소 수정 방향을 쓰고,
이슈가 없으면 `없음`을 명시하세요.
```

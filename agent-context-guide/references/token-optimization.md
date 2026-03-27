# Instruction token optimization

## 핵심 원칙

1. **짧은 루트, 가까운 하위 지침**
2. **중복 금지**
3. **휘발성 정보 분리**
4. **긴 배경 설명은 instruction 밖으로 이동**

## 실무 체크리스트

### Root AGENTS.md
- [ ] 200줄 안팎에서 유지 가능한가?
- [ ] 모든 서브시스템 설명을 한 파일에 몰아넣지 않았는가?
- [ ] 실행 명령이 실제 저장소와 맞는가?

### Nested AGENTS.md
- [ ] 상위 문서를 복붙하지 않았는가?
- [ ] 해당 디렉토리에서만 필요한 규칙만 담았는가?
- [ ] 파일 경로와 심볼명이 실제 코드와 맞는가?

### Background docs
- [ ] 장문 설명은 `CONTEXT.md` 또는 `docs/`로 분리했는가?
- [ ] `AGENTS.md`에는 링크와 핵심 규칙만 남겼는가?

## 분리 패턴

### 나쁜 예
- 루트 `AGENTS.md` 안에 모든 API 세부 규칙, 테스트 전략, 배포 절차, 서비스별 예외를 전부 적음

### 좋은 예
- 루트 `AGENTS.md`: 공통 품질 기준 + 공통 명령
- `services/payments/AGENTS.md`: 결제 도메인 규칙
- `services/payments/CONTEXT.md`: 도메인 모델, 외부 정산 플로우
- `docs/releases.md`: 배포 절차 세부사항

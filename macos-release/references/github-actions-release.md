# GitHub Actions release automation

## 권장 구성
보통 두 단계로 나눕니다.
1. 릴리즈 생성 또는 릴리즈 publish workflow
2. `release.published` 이벤트를 받는 Homebrew update workflow

예시 구조:
```text
.github/workflows/
├── release.yml
└── update-homebrew.yml
```

## 핵심 원칙
- 릴리즈 산출물 생성과 Homebrew 반영을 분리합니다.
- Homebrew push token은 최소 권한만 부여합니다.
- 실패 시 수동 복구 스크립트를 유지합니다.
- 기존 workflow가 있으면 이름/구조를 유지한 채 보강합니다.

## 자주 쓰는 트리거
```yaml
on:
  release:
    types: [published]
```

## typical flow
```text
태그 push 또는 릴리즈 생성
→ release.yml (build/package/release)
→ release.published
→ update-homebrew.yml (formula/cask 갱신)
```

## 필요한 secret 예시
- 공용 tap push용 token (`HOMEBREW_TAP_GITHUB_TOKEN` 등)
- 필요 시 notarization/signing 관련 secret
- 필요한 경우 App Store Connect 또는 API key secret

## workflow가 해야 할 일
### release.yml
- 버전/태그 확인
- 빌드 및 패키징
- 필요 시 로컬/CI smoke test에 해당하는 검증 실행
- GitHub Release 생성 또는 asset 업로드

### update-homebrew.yml
1. release tag 확인
2. DMG/ZIP/source tarball URL 확보
3. `sha256` 계산
4. Homebrew formula/cask 업데이트 스크립트 실행
5. `brew audit` / `brew install` / `brew test`
6. tap repo commit/push

## 로컬 vs CI 선택 가이드
- 빠른 반복 개발 → 로컬 release script
- 재현 가능한 팀 릴리즈 → GitHub Actions
- signing/notarization이 로컬 키체인 의존적 → 로컬 우선
- Homebrew만 자동화 → update-homebrew workflow 단독 또는 후속 workflow

병행 운영도 가능하지만, 로컬과 CI의 역할을 명확히 나눕니다.

## 실패 시 복구
workflow가 실패하면 아래를 로컬에서 다시 실행하는 경로를 문서화합니다.

```bash
./scripts/release_homebrew.sh vX.Y.Z --tap-dir <local-tap-clone> --dry-run
./scripts/release_homebrew.sh vX.Y.Z --tap-dir <local-tap-clone> --push
```

실패 보고에는 다음을 포함합니다.
- 실패 step
- 부족한 secret/권한
- 수동 복구 명령
- 이미 publish된 산출물과 미반영된 단계

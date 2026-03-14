# GitHub Actions release automation

## 권장 구성
보통 두 단계로 나눈다.
- 릴리즈 생성 또는 릴리즈 publish workflow
- `release.published` 이벤트를 받는 Homebrew update workflow

## 핵심 원칙
- 릴리즈 산출물 생성과 Homebrew 반영을 분리한다.
- Homebrew push token은 최소 권한만 부여한다.
- 실패 시 수동 복구 스크립트를 유지한다.

## 자주 쓰는 트리거
```yaml
on:
  release:
    types: [published]
```

## 필요한 secret 예시
- 공용 tap push용 token (`HOMEBREW_TAP_GITHUB_TOKEN` 등)
- 필요 시 notarization/signing 관련 secret

## workflow가 해야 할 일
1. release tag 확인
2. Homebrew formula/cask 업데이트 스크립트 실행
3. audit/install/test
4. tap repo commit/push

## 실패 시 복구
workflow가 실패하면 아래를 로컬에서 다시 실행하는 경로를 문서화한다.

```bash
./scripts/release_homebrew.sh vX.Y.Z --tap-dir <local-tap-clone> --dry-run
./scripts/release_homebrew.sh vX.Y.Z --tap-dir <local-tap-clone> --push
```

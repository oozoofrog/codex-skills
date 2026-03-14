# macOS release checklist

## 1. 릴리스 범위 고정
- 전체 릴리스인지, Homebrew만인지, workflow만인지 먼저 고정한다.
- 사용자가 특정 단계만 원하면 전체 파이프라인을 강제하지 않는다.

## 2. 기존 구조 탐색
우선 탐색 대상:
- `scripts/release.sh`
- `fastlane/Fastfile`
- `.github/workflows/`
- `*.xcodeproj`, `*.xcworkspace`
- `Formula/*.rb`, `Casks/*.rb`, `homebrew-*`
- 버전/빌드 번호 소스 파일

## 3. 사전 조건 점검
- git 작업 트리 상태
- `gh auth status`
- Xcode build 가능 여부
- signing / notarization / App Store Connect / release token 필요 여부
- Homebrew tap 로컬 clone 또는 remote push 가능 여부

## 4. 안전한 기본 순서
1. 버전 확인/증가
2. 빌드
3. 패키징(DMG/ZIP/tarball)
4. 로컬 검증
5. GitHub Release 또는 tag push
6. Homebrew 반영

## 5. 실패 시 원칙
- 빌드/패키징 실패면 publish 단계를 중단한다.
- Homebrew만 실패하면 formula/cask 파일과 SHA 계산 과정을 분리해서 보고한다.
- 실패 지점, 원인, 다음 복구 명령을 구체적으로 남긴다.

# Release script guide

`scripts/release.sh` 를 새로 만들거나 기존 스크립트를 보강할 때 참고하는 상세 가이드입니다.

## 언제 읽을지
- 저장소에 릴리스 스크립트가 없는데 사용자가 자동화를 원할 때
- 기존 스크립트가 너무 단순해서 dry-run, Homebrew, GitHub Release 단계를 보강해야 할 때
- GUI 앱 릴리스를 로컬에서 반복 가능하게 만들고 싶을 때

CLI 릴리스라면 이 가이드의 구조를 참고하되, DMG/Cask 단계는 Formula 또는 tarball 흐름에 맞게 바꿉니다.

## 권장 스크립트 구조

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── 설정 변수 ──
APP_NAME="AppName"
SCHEME="AppName"
PROJECT_DIR="AppName"
GITHUB_REPO="user/Repo"

# ── 경로 계산 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PBXPROJ="${REPO_ROOT}/${PROJECT_DIR}/AppName.xcodeproj/project.pbxproj"

# Homebrew tap (환경변수로 덮어쓰기 가능)
HOMEBREW_TAP="${HOMEBREW_TAP_PATH:-${REPO_ROOT}/../homebrew-tap}"

# ── 플래그 ──
DRY_RUN=0
SKIP_BREW=0
NEW_VERSION=""
```

## 지원할 인자
- `--dry-run`: 실행 계획만 출력하고 실제 변경은 하지 않기
- `--skip-brew`: Homebrew Cask/Formula 반영 건너뛰기
- `-h`, `--help`: 사용법 출력
- 위치 인자: 명시적 버전 (`./scripts/release.sh 2.1.0`)

## 단계별 권장 흐름

### 1. 사전 검증
최소한 아래를 확인합니다.

```bash
command -v gh >/dev/null 2>&1 || err "gh CLI 필요"
command -v xcodebuild >/dev/null 2>&1 || err "xcodebuild 필요"
[[ -f "${PBXPROJ}" ]] || err "pbxproj 없음"

# untracked 파일은 허용하되 tracked dirty 상태는 막기
DIRTY=$(git status --porcelain | grep -v '^\?\?' || true)
[[ -z "${DIRTY}" ]] || err "커밋되지 않은 변경사항 있음"
```

추가로 확인할 것:
- 이미 같은 릴리스 태그가 존재하는지
- Homebrew tap 경로가 유효한지
- signing / notarization이 필요한 프로젝트인지

### 2. 버전 소스 고정과 버전 범프
`MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, plist, manifest 중 **하나의 source of truth** 를 먼저 고정합니다.

pbxproj 예시:

```bash
CURRENT_VERSION=$(grep 'MARKETING_VERSION' "$PBXPROJ" | head -1 | sed 's/.*= *//;s/ *;.*//')
CURRENT_BUILD=$(grep 'CURRENT_PROJECT_VERSION' "$PBXPROJ" | head -1 | sed 's/.*= *//;s/ *;.*//')

if [[ -z "$NEW_VERSION" ]]; then
  MAJOR=$(echo "$CURRENT_VERSION" | cut -d. -f1)
  MINOR=$(echo "$CURRENT_VERSION" | cut -d. -f2)
  NEW_VERSION="${MAJOR}.$((MINOR + 1))"
fi
NEW_BUILD=$((CURRENT_BUILD + 1))

sed -i '' "s/MARKETING_VERSION = ${CURRENT_VERSION}/MARKETING_VERSION = ${NEW_VERSION}/g" "$PBXPROJ"
sed -i '' "s/CURRENT_PROJECT_VERSION = ${CURRENT_BUILD}/CURRENT_PROJECT_VERSION = ${NEW_BUILD}/g" "$PBXPROJ"
```

주의:
- macOS `sed` 와 GNU `sed` 의 `-i` 동작이 다릅니다.
- 실제 파일 포맷이 다르면 정규식을 맞춰서 수정합니다.
- 빌드 전에 디스크 값을 먼저 바꿔야 산출물 버전이 맞습니다.

### 3. Release 빌드

```bash
DERIVED_DATA="${REPO_ROOT}/.build/xcode"

xcodebuild \
  -project "${REPO_ROOT}/${PROJECT_DIR}/AppName.xcodeproj" \
  -scheme "${SCHEME}" \
  -configuration Release \
  -derivedDataPath "${DERIVED_DATA}" \
  -destination 'platform=macOS' \
  clean build
```

권장:
- `-derivedDataPath` 를 고정해 경로를 예측 가능하게 만들기
- 기본 Xcode DerivedData와 섞지 않기
- 실패 시 마지막 몇 줄만 자르지 말고 전체 로그 저장 위치를 남기기

### 4. 패키징

#### GUI 앱: DMG 예시
```bash
DMG_STAGING="${REPO_ROOT}/.build/dmg-staging"
mkdir -p "${DMG_STAGING}"
ditto "${BUILT_APP}" "${DMG_STAGING}/${APP_NAME}.app"
ln -s /Applications "${DMG_STAGING}/Applications"

TEMP_DMG="${REPO_ROOT}/.build/temp.dmg"
hdiutil create -srcfolder "${DMG_STAGING}" -volname "${APP_NAME}" \
  -fs HFS+ -format UDRW -size 50m "${TEMP_DMG}" -quiet

hdiutil convert "${TEMP_DMG}" -format UDZO -imagekey zlib-level=9 -o "${DMG_PATH}" -quiet
DMG_SHA256=$(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')
```

DMG 포맷:
- `UDRW`: Finder 레이아웃 조정용 임시 이미지
- `UDZO`: 배포용 압축 이미지

#### CLI 도구
- 보통 tarball 또는 릴리스 바이너리 생성
- 필요 시 source tarball 기준 Formula를 유지
- `sha256` 은 최종 산출물에서 다시 계산

### 5. 로컬 설치/스모크 테스트
GUI 앱은 publish 전에 로컬 검증을 거칩니다.

```bash
pkill -x "$APP_NAME" || true
sleep 1
for i in {1..5}; do pgrep -x "$APP_NAME" || break; sleep 1; done
pgrep -x "$APP_NAME" && pkill -9 -x "$APP_NAME"
```

이후:
1. DMG 마운트 또는 ZIP 해제
2. 기존 설치 앱 제거/덮어쓰기
3. 새 앱 실행
4. 최소 smoke test 수행

자세한 절차는 `local-install-and-dmg.md` 와 함께 읽습니다.

### 6. Git / 태그 / GitHub Release
파괴적 단계는 항상 마지막에 둡니다.

```bash
git add "${PBXPROJ}"
git commit -m "Bump version to ${NEW_VERSION} (build ${NEW_BUILD})"
git tag -a "${RELEASE_TAG}" -m "Release ${RELEASE_TAG}"
git push origin main
git push origin "${RELEASE_TAG}"
```

GitHub Release 예시:

```bash
RELEASE_NOTES=$(git log --pretty=format:"- %s" "v${CURRENT_VERSION}..HEAD" | grep -v "Bump version" || echo "- 업데이트")

gh release create "${RELEASE_TAG}" "${DMG_PATH}" \
  --repo "${GITHUB_REPO}" \
  --title "${APP_NAME} ${RELEASE_TAG}" \
  --notes "${RELEASE_NOTES}"
```

### 7. Homebrew 반영

#### Cask 예시
```bash
CASK_FILE="${HOMEBREW_TAP}/Casks/appname.rb"

cat > "${CASK_FILE}" <<CASK
cask "appname" do
  version "${NEW_VERSION}"
  sha256 "${DMG_SHA256}"
  url "https://github.com/${GITHUB_REPO}/releases/download/v#{version}/App-#{version}.dmg"
  name "AppName"
  desc "App description"
  homepage "https://github.com/${GITHUB_REPO}"
  app "AppName.app"
end
CASK
```

공용 tap 원칙:
- 해당 프로젝트의 formula/cask 한 파일만 수정
- push 전 `git pull --rebase` 충돌 가능성 고려
- 가능하면 `brew audit`, `brew install`, `brew test` 까지 확인

## 유틸리티 함수 패턴

```bash
step() { echo ""; echo "==> $1"; }
info() { echo "    $1"; }
err()  { echo "오류: $1" >&2; exit 1; }

run() {
  if [[ ${DRY_RUN} -eq 1 ]]; then
    info "[dry-run] $*"
  else
    "$@"
  fi
}
```

## 최소 체크리스트
- [ ] `--dry-run`
- [ ] `--skip-brew`
- [ ] `--help`
- [ ] 사전 검증 (`gh`, 빌드 도구, Git 상태, 태그 중복)
- [ ] 버전 자동 증가 또는 명시적 지정
- [ ] clean build
- [ ] 패키징
- [ ] 로컬 검증
- [ ] Git commit/tag/push
- [ ] GitHub Release
- [ ] Homebrew 반영
- [ ] 실패 시 복구 포인트와 수동 명령 출력

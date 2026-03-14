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

분리 이유:
- 릴리즈 산출물 생성과 Homebrew 반영을 분리할 수 있음
- 실패 지점을 workflow 단위로 구분하기 쉬움
- Homebrew push token 권한을 별도로 최소화할 수 있음

## 핵심 원칙
- 기존 workflow 이름과 구조가 있으면 유지한 채 보강합니다.
- release workflow와 Homebrew update workflow를 분리합니다.
- Homebrew push token은 최소 권한만 부여합니다.
- signing/notarization 같은 민감 단계는 필요한 workflow에만 제한합니다.
- 실패 시 로컬 수동 복구 경로를 남겨 둡니다.

## 전형적인 흐름
```text
태그 push 또는 수동 workflow_dispatch
→ release.yml (build/package/release)
→ GitHub Release published
→ update-homebrew.yml (formula/cask 갱신)
```

## 사전 설정

### 1. token / secret
보통 아래가 필요합니다.
- tap push용 token (`HOMEBREW_TAP_TOKEN`, `HOMEBREW_TAP_GITHUB_TOKEN` 등)
- signing / notarization 관련 secret
- 필요한 경우 App Store Connect API key

Homebrew tap에 push해야 하면:
1. Fine-grained PAT 생성
2. tap repo만 선택
3. `Contents: Read and write` 정도의 최소 권한 부여
4. 원본 프로젝트 repo의 Actions secret으로 저장

### 2. permissions
release workflow는 보통 아래 권한이 필요합니다.

```yaml
permissions:
  contents: write
```

Homebrew update workflow는 tap checkout/push에 필요한 secret 기반 권한이 있어야 합니다.

## 자주 쓰는 트리거

### release workflow
```yaml
on:
  workflow_dispatch:
  push:
    tags:
      - 'v*'
```

### Homebrew update workflow
```yaml
on:
  release:
    types: [published]
```

## `release.yml` 에서 해야 할 일
- 버전/태그 확인
- 빌드 및 패키징
- 필요 시 smoke test
- GitHub Release 생성 또는 asset 업로드

예시:

```yaml
name: Release

on:
  workflow_dispatch:
    inputs:
      version:
        description: "릴리스 버전"
        required: true
        type: string
  push:
    tags:
      - "v*"

jobs:
  build-and-release:
    runs-on: macos-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - name: Determine version
        id: version
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "version=${{ inputs.version }}" >> "$GITHUB_OUTPUT"
          else
            echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"
          fi

      - name: Build
        run: |
          xcodebuild \
            -project "$PROJECT_DIR/$APP_NAME.xcodeproj" \
            -scheme "$SCHEME" \
            -configuration Release \
            -derivedDataPath .build/xcode \
            -destination 'platform=macOS' \
            clean build

      - name: Package
        run: |
          # DMG/ZIP/tarball 생성
          # 생성 산출물과 sha256을 output으로 남기기

      - name: Publish release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "v${{ steps.version.outputs.version }}" "$ASSET_PATH" \
            --title "$APP_NAME v${{ steps.version.outputs.version }}" \
            --notes "$RELEASE_NOTES"
```

## `update-homebrew.yml` 에서 해야 할 일
1. release tag 확인
2. DMG/ZIP/source tarball URL 확보
3. `sha256` 계산
4. Homebrew formula/cask 업데이트
5. 가능하면 `brew audit` / `brew install` / `brew test`
6. tap repo commit/push

예시:

```yaml
name: Update Homebrew

on:
  release:
    types: [published]

jobs:
  update-homebrew:
    runs-on: ubuntu-latest
    steps:
      - name: Resolve asset URL
        id: asset
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          TAG="${GITHUB_REF_NAME}"
          URL=$(gh api "repos/${{ github.repository }}/releases/tags/$TAG" \
            --jq '.assets[] | select(.name | endswith(".dmg")) | .browser_download_url')
          echo "url=$URL" >> "$GITHUB_OUTPUT"

      - name: Download and hash
        id: sha
        run: |
          curl -sL "${{ steps.asset.outputs.url }}" -o artifact.bin
          echo "sha256=$(shasum -a 256 artifact.bin | awk '{print $1}')" >> "$GITHUB_OUTPUT"

      - name: Checkout tap
        uses: actions/checkout@v4
        with:
          repository: ${{ env.TAP_REPO }}
          token: ${{ secrets.HOMEBREW_TAP_TOKEN }}
          path: homebrew-tap

      - name: Update formula or cask
        run: |
          # 대상 파일 하나만 수정
          # URL / version / sha256 갱신

      - name: Commit and push
        run: |
          cd homebrew-tap
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .
          git commit -m "Update Homebrew package to $VERSION"
          git push
```

## 프로젝트별 커스터마이징 포인트

| 변수 | 설명 | 예시 |
|------|------|------|
| `APP_NAME` | 앱 이름 | `FrogTray` |
| `SCHEME` | Xcode scheme | `FrogTray` |
| `PROJECT_DIR` | xcodeproj 상위 디렉터리 | `FrogTray` |
| `TAP_REPO` | Homebrew tap repo | `oozoofrog/homebrew-tap` |
| `CASK_NAME` | cask 파일명 | `frogtray` |
| `FORMULA_NAME` | formula 파일명 | `frogtray` |
| `HOMEBREW_TAP_TOKEN` | tap push secret 이름 | 변경 가능 |

## 로컬 vs CI 선택 가이드
- 빠른 반복 개발 → 로컬 release script
- 재현 가능한 팀 릴리즈 → GitHub Actions
- signing/notarization이 로컬 키체인 의존적 → 로컬 우선
- Homebrew만 자동화 → `update-homebrew.yml` 단독 운영 가능

권장 패턴:
- 로컬 또는 주 workflow가 GitHub Release 생성
- `release.published` 로 Homebrew update workflow 트리거
- 필요 시 로컬 `scripts/release.sh` 를 수동 복구 경로로 유지

## 점검 포인트
- release workflow와 Homebrew workflow가 같은 파일을 동시에 수정하지 않기
- tap repo에서는 대상 formula/cask 한 파일만 수정하기
- 실패 시 수동 복구 명령을 PR/issue/로그에 남기기
- `gh api` / release asset 조회가 null 을 반환하면 asset naming 규칙부터 확인하기

# Homebrew publishing guide

## Formula vs Cask
- GUI macOS 앱 (`.app`) → 대체로 `Cask`
- CLI 도구 → 대체로 `Formula`

## 공용 tap 원칙
공용 tap(`homebrew-tap`)에서는 다음을 지킨다.
- 대상 프로젝트의 formula/cask 한 파일만 수정한다.
- 다른 `Formula/` 나 `Casks/` 항목은 건드리지 않는다.
- tap repo가 관련 없는 변경으로 dirty 하면 먼저 정리하거나 작업을 중단한다.

## 기본 formula 패턴
- source tarball URL 또는 릴리즈 바이너리 URL 사용
- `sha256` 재계산
- `brew audit`
- `brew install --build-from-source` 또는 대상 formula install
- `brew test`

## 기본 cask 패턴
- DMG/ZIP URL 확인
- 산출물 sha256 재계산
- `app` 경로와 `zap` 경로 확인
- `git pull --rebase origin main` 후 push

## 공용 tap push 충돌
다른 프로젝트가 같은 tap을 갱신했을 수 있으므로 보통 아래가 필요하다.

```bash
git pull --rebase origin main
git push origin main
```

## 보고 항목
- 어떤 tap repo를 사용했는지
- 어떤 formula/cask 파일을 수정했는지
- URL/sha256 변경값
- 검증 명령 결과

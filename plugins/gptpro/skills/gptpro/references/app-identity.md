# Launcher 이름과 아이콘의 적용 범위

사용자가 설치하고 여는 앱 이름은 **gptpro Launcher**입니다. **격리 Runner**는 Launcher 또는 `desktop-launch`가 여는 별도 프로필의 ChatGPT 프로세스를 뜻합니다. Runner는 별도 `.app` 번들이 아니며, `gptpro Runner`라는 이름의 앱이 설치되지는 않습니다.

## 적용되는 표면

| 표면 | 구현 |
| --- | --- |
| Finder의 `gptpro Launcher.app` | 표시명 `gptpro Launcher`, ChatGPT 매듭과 흰 바탕을 유지한 주황색 실행 배지 아이콘 |
| Launcher 오류 대화상자 | 제목 `gptpro Launcher`; 본문은 문제가 발생한 격리 Runner를 구분 |
| 실행 중인 Runner의 Dock·Cmd-Tab·앱 메뉴·기본 창 | 원본 ChatGPT 표시 유지. Launcher 아이콘은 전파되지 않음 |
| `launcher-status` | `current`가 plist·실행 파일·아이콘을 검사. `runner_native_identity_customized=false`와 설명을 별도로 반환 |

Launcher는 `LSUIElement=true`인 짧게 실행되는 실행기입니다. 별도의 상주 Dock 항목을 만들지 않습니다. Finder 아이콘 설치 성공이나 `current=true`를 Runner의 네이티브 아이콘 변경 증거로 해석하지 마세요. Runner를 종료할 때에도 이름만으로 두 ChatGPT 프로세스를 구별할 수 있다고 가정하지 마세요.

## 원본 앱을 변경하지 않는 경계

2026-09-05에 `/Applications/ChatGPT.app` Desktop `26.901.31953` (build `7868`)을 읽기 전용으로 조사했습니다. 격리 Runner와 원본은 같은 실행 파일과 번들을 사용합니다. 현재 gptpro의 renderer bridge는 Electron main-process `app.dock.setIcon`이나 앱 표시명 변경 기능을 노출하지 않습니다. Electron의 [Dock API](https://www.electronjs.org/docs/latest/api/dock)는 main-process API입니다.

설치된 Desktop의 `.vite/build/main-C5K7o1Hr.js`에서는 기본 창의 `page-title-updated` 이벤트를 취소하고 기존 제목을 유지합니다. 내장 아이콘 preference는 `ome` → `cme` 경로로 현재 `process.execPath`가 속한 원본 `.app` 경로를 구한 뒤 `launch-services-helper set-app-icon`에 전달합니다. 따라서 그 설정을 격리 프로세스 전용 아이콘 변경 수단으로 쓰지 않습니다. 이 관찰은 해당 Desktop 버전에 한정되며 공개 OpenAI 규약이 아닙니다.

원본 번들 변경·재서명·복제, main-process 주입, 인증·프로필 복사 또는 자동 프로세스 재시작은 구현하지 않았습니다. 네이티브 Runner 표시를 안전하게 바꾸려면 Desktop이 프로세스별 이름·아이콘 설정을 지원해야 합니다. 이 제한은 재설치나 재시작만으로 해결되지 않습니다.

## 리소스와 재생성

- [보관 PNG](../assets/gptpro-launcher-source.png): 사용자 요청에 따라 원본 ChatGPT 아이콘 테마에 주황색 원형 실행 배지를 추가한 ImageGen 편집 결과. 배지의 흰색 삼각형은 Launcher의 실행 역할을 나타냅니다.
- [macOS 아이콘](../assets/gptpro-launcher.icns): 위 PNG에서 16/32/128/256/512pt와 각 2× 크기로 생성합니다.
- [재생성 스크립트](../scripts/build_launcher_icon.py): macOS 기본 `sips`와 `iconutil`만 사용합니다. AI 재호출 없이 보관 PNG에서 아이콘을 재생성합니다.

```bash
python3 gptpro/scripts/build_launcher_icon.py
python3 scripts/sync_skill_mirrors.py --write --package gptpro
python3 gptpro/scripts/gptpro.py launcher-install --json
python3 gptpro/scripts/gptpro.py launcher-status --json
```

PNG 제작에는 설치된 `/Applications/ChatGPT.app/Contents/Resources/icon-chatgpt.png`를 편집 참조로 사용했습니다. 원본 SHA-256은 `3453947a9ce2709b7ec51c0559c7eb976e4ac53b232b607d1d81b0d1d1048b61`입니다. 원본 앱 리소스는 수정하지 않습니다. 원본 ChatGPT/OpenAI 상표와 그래픽의 권리는 원권리자에게 있으며, 이 파생 아이콘을 저장소 코드의 라이선스로 재허가한다는 의미는 아닙니다.

편집 프롬프트: “Preserve the original ChatGPT macOS icon theme, white rounded square, graphite interlocking knot and transparent outer background. Add only a small amber-orange circular UI badge at the lower-right with a white rim and white right-pointing play triangle. Keep the knot readable. No text, no extra badges, no redesign.”

설치는 아이콘을 `Contents/Resources/gptpro-launcher.icns`에 복사하고 `CFBundleIconFile`과 SHA-256을 plist에 기록합니다. 기존 잠금·atomic swap·Trash 복구 절차를 유지합니다. 기록된 아이콘의 손상·누락·심볼릭 링크·하드 링크는 관리 대상 판정을 실패시켜 덮어쓰기를 막습니다. 아이콘이 없던 기존 관리 대상 Launcher는 새 버전으로 갱신할 수 있습니다.

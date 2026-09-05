# gptpro Launcher 표시명·아이콘 검증 — 2026-09-05

결과: **gptpro Launcher**의 이름과 배지 아이콘을 구현하고 실제 사용자 Applications 폴더에 적용했다. **격리 Runner의 네이티브 이름·아이콘을 원본과 구별하는 목표는 충족하지 못했다.** 현재 Desktop에서 안전하게 노출된 프로세스별 변경 경로를 확인하지 못했으며 원본 앱 변경으로 우회하지 않았다.

기준 commit: `9e214441153fc8eb1a419e173b6a6e50da87a1b3`. 작업 브랜치: `task/gptpro-app-identity`. Desktop: `26.901.31953`, build `7868`. 이 문서는 로컬 관찰 기록이며 다른 Desktop 버전의 동작을 보증하지 않는다.

## 실제 UI와 실행 검증

| 항목 | 결과 및 증거 |
| --- | --- |
| Finder 이름 | `gptpro Launcher`; 갱신 후 새 Finder 창의 Applications 폴더에서도 확인 |
| Finder 아이콘 | 기존 빈 앱 아이콘에서 ChatGPT 테마 + 주황색 실행 배지로 변경. [이전 화면](gptpro-app-identity-evidence/finder-before.png), [적용 화면](gptpro-app-identity-evidence/finder-after.png) |
| Finder에서 Launcher 다시 열기 | 기존 Runner를 재사용. 원본 PID `1095`, 격리 Runner PID `23086` 모두 전후 동일 |
| Launcher 설치·상태 | 실제 설치 `changed=true`, `current=true`, 재설치 `changed=false`. 설치본 `launcher-status`에서 `chatgpt_mode=runner_verified`, 원본도 실행 중 |
| Runner의 Dock·Cmd-Tab·메뉴·기본 창 | 커스터마이징 미구현. 실제 화면 검증 차단. Launcher 변경 성공을 해당 표면의 변경 증거로 사용하지 않음 |
| 오류 대화상자 | 제목 코드 `gptpro Launcher`, zsh 문법 검사 통과. 실행 중인 상담 환경에 오류를 유발하는 실제 화면 검증은 하지 않음 |
| 완전히 종료된 상태에서 새 Runner 시작 | 기존 원본/Runner 프로세스를 보존해야 하므로 이번 작업에서 미실행. 런칭 인자와 격리 검사는 기존 자동 테스트로 검증 |

Computer Use의 `cua.getApp('com.openai.codex')` 결과는 `Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons.`였다. Dock 직접 선택은 `Computer Use server error -10005: timeoutReached`였다. 다른 UI 제어 수단으로 우회하지 않았다. 로컬 코드에서 관찰한 [네이티브 변경 제한](../gptpro/references/app-identity.md)은 실제 화면 검증과 별도 증거다.

## 변경 및 적용 위치

- `gptpro/runtime/gptpro_runtime/controller.py`: `_launcher_plist`, `_launcher_script`, `_launcher_managed`, `_launcher_current`, `launcher_install`, `launcher_status`에서 이름·아이콘·검증 범위를 처리.
- `gptpro/assets/`: 보관 PNG와 `.icns`. 사용자 후속 요청에 따라 원본 ChatGPT 테마를 유지하고 오른쪽 아래에 주황색 실행 배지만 추가. 초기의 전체 주황색 아이콘은 최종 패키지에 포함하지 않음.
- `gptpro/scripts/build_launcher_icon.py`: macOS 기본 도구로 모든 1×/2× 아이콘 크기 재생성.
- `gptpro/scripts/validate_structure.py`, `gptpro/tests/test_gptpro.py`: 필수 리소스, 이름, 해시, 이전 버전 갱신·복구, 아이콘 변조·누락·링크 거부 검증.
- `gptpro/references/app-identity.md`, `gptpro/references/electron-runtime.md`, `gptpro/README.md`, `CHANGELOG.md`: 역할 정의, 적용 범위, 버전별 기술 근거와 재생성 방법.
- `plugins/gptpro/skills/gptpro/`: standalone 전체와 byte/mode 일치.
- 설치 Skill: `~/.codex/skills/gptpro`. 설치 Launcher: `~/Applications/gptpro Launcher.app`.
- 이전 Launcher: `~/.Trash/gptpro Launcher-20260905-140456-24cbf2.app`. 이전 plist의 `CFBundleName=gptpro Runner`를 직접 확인했고 기존 번들은 보존됨.

소스·Plugin 미러·설치본은 **제외 규칙 없이 44개 파일의 내용과 권한이 일치**했다. 설치 tree SHA-256은 `bade5af942ac44366a7e1b34cd91ae802e9a2904fa810b31ebbc0e239a362912`다. 보관 PNG에서 `.icns`를 다시 생성한 결과도 기존 `.icns`와 바이트 단위로 일치했다.

원본 ChatGPT의 `Info.plist`, 실행 파일, `app.asar`, `icon-chatgpt.png`, `electron.icns` 다섯 파일 SHA-256이 전후 일치하고 `codesign --verify --deep --strict`가 통과했다. 계정·로그인·일반 프로필 내용을 읽거나 복사하지 않았으며, 어떤 ChatGPT 프로세스도 종료·재시작하지 않았다. 새 상담 메시지는 보내지 않았다.

## 실행한 검증

아래 Python 명령은 통합 검증 시 `PYTHONDONTWRITEBYTECODE=1`로 실행했다.

```bash
python3 -m unittest discover -s gptpro/tests -p 'test_*.py'
python3 -m unittest scripts.tests.test_build_gptpro_base scripts.tests.test_manage_skills scripts.tests.test_plugin_distribution scripts.tests.test_sync_skill_mirrors
node --test gptpro/tests/test_chatgpt_desktop.test.js
python3 gptpro/scripts/validate_structure.py
python3 scripts/build_gptpro_base.py --check
python3 /Users/oozoofrog/.codex/skills/.system/skill-creator/scripts/quick_validate.py gptpro
python3 /Users/oozoofrog/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/gptpro/skills/gptpro
python3 scripts/sync_skill_mirrors.py --write --package gptpro
python3 scripts/sync_skill_mirrors.py --package gptpro
python3 scripts/manage_skills.py install gptpro --update --dry-run
python3 scripts/manage_skills.py install gptpro --update
python3 gptpro/scripts/build_launcher_icon.py
python3 /Users/oozoofrog/.codex/skills/gptpro/scripts/gptpro.py launcher-install --json
python3 /Users/oozoofrog/.codex/skills/gptpro/scripts/gptpro.py launcher-status --json
plutil -lint '/Users/oozoofrog/Applications/gptpro Launcher.app/Contents/Info.plist'
zsh -n '/Users/oozoofrog/Applications/gptpro Launcher.app/Contents/MacOS/gptpro-launcher'
codesign --verify --deep --strict /Applications/ChatGPT.app
git diff --check
```

통합 후 결과: Skill Python **69/69**, 설치·배포·미러 Python **19/19**, Node **55/55**. 구조·frontmatter·로컬 링크·배포 경계·미러 검사 통과. Swift 코드 변경은 없음.

## 문서 작업과 통합

`gptpro 주요 기능 명명과 Skill README 정리` 작업 (`01a06fe9-5cc7-75e1-9653-6e816ed51ac6`)과 시작 시 역할·명칭·공통 파일 담당을 조율했다. 상대는 README·CHANGELOG, 이 작업은 앱 코드·리소스·설치/UI 검증과 최종 통합을 담당했다.

상대의 `/tmp/gptpro-feature-readme-9e214441-01a06fe9.patch`를 `git apply --check` 후 한 번 적용했다. 7개 경로를 인계받았고, 여기에는 사용자가 승인한 standalone의 과거 복사본 삭제 3개(`desktop-workflow 2.md`, `legacy-receipts 2.md`, `test_install_transitions 2.py`)가 포함된다. 이후 확정된 Launcher 이름·사용자 수정 아이콘·Runner 한계를 양쪽 README와 CHANGELOG에 반영했다. 상대 worktree는 직접 수정하지 않았다.

문서 인계본의 테스트 결과를 재사용해 통합 성공으로 보고하지 않고, 통합한 코드·문서·리소스를 위 명령으로 다시 검증했다.

사용자의 작업 마무리 요청에 따라 자동 스냅샷 `fb5c6814ccd8c4e50798480c6fc07e9384f0c4cc`를 보존하면서 같은 구현을 `task/gptpro-app-identity`의 정식 커밋으로 정리했다. 마무리 시 구조 검사와 미러 일치, 실제 설치본 `launcher-status`의 `current=true`·`runner_verified`를 다시 확인했다. 코드·아이콘은 앞서 통과한 테스트 대상과 동일하며, 실행 중 Runner의 네이티브 이름·아이콘 분리는 여전히 미구현이다. PR과 push는 수행하지 않았다.

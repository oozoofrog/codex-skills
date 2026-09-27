# 실행과 복구 경계

Blender Python과 MCP의 code tool은 사용자 계정 권한의 임의 코드 실행이다. `--disable-autoexec`, `use_scripts=False`, `--factory-startup`, `--offline-mode`는 방어적 설정이며 Python 파일 삭제·shell·network를 차단하는 sandbox가 아니다. 신뢰되지 않은 `.blend`/addon/script는 OS/VM/container 격리 정책을 별도로 사용한다. 자동 애드온 설치·전역 설정 변경은 하지 않는다.

- CLI는 새 output directory를 독점 생성하고 원본 hash를 재확인한다. candidate 저장은 최종 승인과 분리한다. finalize는 exclusive create로 기존 파일·symlink를 덮어쓰지 않는다.
- `--trusted-script` 전에 filesystem/network/subprocess/handlers와 의도한 scene 변경을 검토한다. 작업 directory 밖 쓰기는 실제 사용자 범위 안인지 확인한다. 선언된 plan/AST 체크는 이 권한을 제한하지 못한다.
- 원본 hash·복사본은 입력 `.blend`의 증거이며 외부 texture/cache/linked library 전체 snapshot이 아니다. 재현 가능한 전달에는 외부 의존성도 별도 고정·검증한다. 상대 경로 유지를 위해 저장본을 원래 경로에서 로드하며, wrapper는 그 경로에 저장하지 않는다.
- linked datablock·여러 user가 있는 mesh의 편집은 먼저 single-user/duplicate 전략을 검토한다. 보호 대상과 공유된 data는 이름뿐 아니라 관계로 조사한다.
- shape key가 있는 mesh에 topology를 바꾸는 apply/remesh/join은 exact guard가 거부한다. Jev에게 허용 여부를 다시 묻지 말고 가역적 modifier/복제/다른 전략을 계획한다.

## Checkpoint 비용

CLI 새 프로세스의 원본/초기 snapshot은 재실행 복구점이다. 파괴적 선언 전에 메모리의 `.blend`를 copy-save하고 hash를 남긴다. 비파괴적 작은 작업마다 추가 전체 checkpoint를 만들지 않는다. `blender_cli.py checkpoint`는 저장된 파일의 새 byte-copy이며 열린 GUI의 미저장 변경을 보존하지 않는다.

MCP live code는 사용자와 공유된 장면을 바꾸므로 제공한 최신 inspect hash를 실행 직전에 확인하고 새 absolute path에 `copy=True` checkpoint를 저장한다. 저장 위치·권한은 실제 작업 범위 안이어야 한다. undo boundary는 앱 세션/연산에 의존하므로 단독 복구 보증으로 사용하지 않는다. checkpoint는 저장 결과와 경로를 확인한다. 외부 cache·linked asset 때문에 복구가 불확실하거나 복구 보장을 요청받은 경우 재열기와 의존성을 추가 확인한다. 매 수정마다 재열기 시험을 요구하지 않는다.

Timeout/disconnect 뒤 자동 mutation 재전송은 하지 않는다. live 장면은 이미 바뀌었을 수 있으므로 재조사하고 남은 차이만 처리한다. 실패 로그·후보·checkpoint는 남긴다. 재시도마다 새 출력 경로와 제한된 범위를 사용한다.

# Deterministic CLI / bpy

호스트 Python은 3.10+ 표준 라이브러리만 쓴다. Blender 실행은 [공식 CLI 인자](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html)의 순서에 따라 `--background --factory-startup --disable-autoexec --offline-mode --python-exit-code 1 --python scene_worker.py -- ...`를 사용한다. bpy 작업은 별도 프로세스에서 수행한다.

```sh
python3 scripts/blender_cli.py health --output-dir /tmp/blender-health-new
python3 scripts/blender_cli.py inspect --source /absolute/scene.blend --objects Body Head --output-dir /tmp/inspect-new
python3 scripts/blender_cli.py run --source /absolute/scene.blend --source-sha256 FRESH_SHA256 \
  --plan plan.json --script reviewed-edit.py --trusted-script --output-dir /tmp/edit-new
python3 scripts/blender_cli.py render --source /tmp/edit-new/candidate.blend \
  --width 512 --height 384 --samples 8 --output-dir /tmp/preview-new
python3 scripts/blender_cli.py checkpoint --source /absolute/scene.blend --source-sha256 FRESH_SHA256 --output-dir /tmp/checkpoint-new
```

`FRESH_SHA256`는 같은 저장본의 inspection result `source_sha256`다. 새 장면은 `--source`를 생략한다. 각 output directory는 새 경로여야 한다. `--blender /Applications/Blender.app` 또는 실행 파일, `BLENDER_BIN`, PATH와 macOS 설치 경로 discovery를 지원한다. 여러 설치가 있으면 명시한 버전을 사용한다. 특정 사용자 volume은 hard-code하지 않는다.

`blender-health`, `blender-inspect`, `blender-run`, `blender-render`, `blender-validate`, `blender-checkpoint`는 같은 Python 명령의 얇은 executable wrapper다. PATH 설치가 필수는 아니다. `scripts/blender-run --help`로 실제 옵션을 확인한다.

## Script 계약

run은 script를 output에 복사하고 그 snapshot을 실행한다. `__file__`은 output/script.py, `PLAN`은 plan JSON, `OUTPUT_DIR`는 pathlib.Path다. 예제는 self-contained이다. 외부 helper를 import하면 해당 버전·파일 hash도 task evidence에 남긴다. `bpy.data` 직접 변경을 우선하고, `bpy.ops`가 필요하면 active object/mode/selection/context를 명시한다.

`--pre-decision risk.json`를 주면 fresh plan/before에 묶인 risk receipt를 검사한다. stale/기권/alternative/review는 실행하지 않는다. receipt가 없으면 Codex plan과 deterministic guard 경로이며 Jev가 판단했다고 기록하지 않는다.

worker는 stage memory를 조사하고 선언된 위험을 검사한다. 파괴적 선언에만 추가 checkpoint를 만들며 script 이후 protected postguard를 수행한다. 변경된 보호 대상은 `needs_review`; candidate는 증거로 남기지만 finalize할 수 없다. 새 candidate는 최종 승인 파일과 구분한다.

실행 시간 제한은 process group에 적용하고 로그는 2MiB 이후 잘림을 표시한다. 저장된 `.blend`와 외부 assets는 별개의 의존성이다. wrapper의 출력 보존은 임의 Python의 sandbox를 의미하지 않는다.

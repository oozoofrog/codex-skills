# 캡슐 로봇 애니메이션 데모

`capsule_demo.py`는 새 기준 장면을 생성하는 전용 recipe다. 크림색·청록색 로봇이 두 걸음 걷고 작은 상자를 넘어 착지하는 5초 장면이며 24fps, 1–120프레임이다. 원본 자산·외부 텍스처·Jev 인증·네트워크가 필요 없다. 실제 검증 버전은 Blender 5.2.2다.

## 실행

Codex는 아래 경로를 발견한 Blender 실행 파일, 스킬 디렉터리와 **존재하지 않는 출력 디렉터리**의 절대 경로로 바꾼다. 기존 디렉터리는 거부하며, 실패한 실행의 로그와 부분 산출물은 보존한다. 이 스크립트는 `blender_use.py run`의 job operation이 아닌 별도 recipe다.

```bash
/path/to/Blender --background --factory-startup --disable-autoexec --offline-mode \
  --python-exit-code 1 --python /path/to/skill/scripts/capsule_demo.py -- \
  --output-dir /path/to/new-output --width 960 --height 640 --samples 24 --render
```

`--render`를 생략하면 장면 생성·망토 bake·저장까지만 수행한다. 기본 크기는 960×640, Cycles CPU 24 samples이며 크기는 64..4096, samples는 1..1024 범위다. 긴 렌더는 로그 파일로 출력하고 진행을 확인한다. 종료 코드 0만으로 시각 품질을 판정하지 않는다.

실제 Blender 엔진과 Python API를 사용하지만 GUI를 마우스·키보드로 조작하는 방식은 아니다. 사용자 요청이 열린 앱이나 미저장 장면을 대상으로 하면 이 데모 실행으로 대체하지 않는다. GUI 확인이 필요한 경우 생성한 `robot.blend`를 앱에서 열고 타임라인·망토·접지를 확인한다.

## 산출물과 지원 범위

- `robot.blend`: 메시·재질·8개 뼈의 Armature·pose keyframe·Cloth modifier를 편집할 수 있는 일반 Blender 파일. 망토 캐시는 bake 후 파일 안에 저장한다. 카메라 시점과 재질 색상을 보이는 초기 편집 화면을 포함한다.
- `manifest.json`: 정확한 오브젝트 이름, 계획 궤적, 단계·이벤트, 렌더 요청/완료 상태. 계획한 발–상자 여유 값은 실제 evaluated geometry 검사와 구분한다.
- `frames/frame_0001.png` .. `frame_0120.png`: `--render` 사용 시 생성하는 PNG 시퀀스.

이 recipe의 리그는 부품을 뼈에 rigid weighting하고 짧은 다리를 늘여 연결한다. 일반 인체 리그·IK solver·리타게팅·GLB 애니메이션/Cloth export를 제공하지 않는다. 망토를 포함한 최종 동작은 `.blend`와 렌더로 전달한다. 기존 정적 `asset_bundle`의 지원 범위는 변하지 않는다.

| 구간 | 프레임 |
| --- | --- |
| 두 걸음 | 1–48 |
| 도약 준비 | 49–60 |
| 점프 | 61–89 |
| 착지·회복 | 90–108 |
| 정지 | 109–120 |

FFmpeg가 설치돼 있으면 완료한 PNG 시퀀스를 별도 새 MP4로 묶을 수 있다. 아래 명령은 무음 5초 영상을 만들며 기존 파일을 덮어쓰지 않는다. MP4용 크기는 짝수로 지정한다.

```bash
ffmpeg -n -framerate 24 -start_number 1 -i /path/to/output/frames/frame_%04d.png \
  -frames:v 120 -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart \
  /path/to/new-video.mp4
```

## 결과 확인

새 Blender 프로세스에서 저장본을 다시 열고 다음 증거를 분리해 확인한다.

- `Cape_Cloth`의 Cloth cache: `is_baked`, `is_outdated`, `is_frame_skip`, 1–120 범위. 디스크 캐시 없이 저장됐는지와 프레임별 실제 변형 확인.
- `Rubber_Foot_L/R`의 evaluated 메시: 접지 구간 위치 보존, 바닥 침범, `Jump_Box`와 겹치는 X/Y 구간의 높이. `manifest.json`의 계획 궤적만 확인하지 않는다.
- 렌더: 도약·착지·망토 연결부·화면 안 포함과 시퀀스 연속성. MP4의 프레임 수·길이와 실제 재생.

후속 Geometry Nodes·유체·Grease Pencil·영상 추적 실험은 별도 장면으로 확장한다. 이 데모의 성공을 Blender 전체 기능이나 다른 리그·버전의 호환성으로 확대하지 않는다.

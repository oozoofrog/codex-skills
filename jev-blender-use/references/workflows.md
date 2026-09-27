# 실행 계약

## 공통 호출

아래 상대 경로는 이 스킬 디렉터리 기준이다. Codex는 발견한 스킬 경로를 기준으로 절대 경로를 만들어 실행한다.

```bash
python3 scripts/blender_use.py capabilities
python3 scripts/blender_use.py run --job /absolute/inspect.json \
  --output-dir /absolute/new-inspection-directory \
  --blender /absolute/Blender.app/Contents/MacOS/Blender
```

호출자는 Codex·다른 에이전트·일반 CLI 어느 쪽이어도 된다. job/result JSON에 대화 세션·모델·skill loader 의존성을 넣지 않는다. 실행 시 Blender 프로세스는 현재 GUI와 분리된다.

`--output-dir`는 존재하면 거부한다. 로그·입력·부분 결과가 남아 있는 디렉터리를 재사용하지 않는다. `--timeout`은 양의 초 단위 값이며 기본 180초다. 시간 초과 시 해당 자식 프로세스를 종료하고 `failed`를 기록한다. 장시간 작업에는 사용자가 허용한 시간에 맞게 조절한다.

## 저장본 조사

```json
{
  "schema_version": 1,
  "operation": "inspect",
  "source": "/absolute/character.blend"
}
```

`inventory.json`은 저장된 활성 scene/view layer, 오브젝트의 정확한 이름·종류·부모·dimensions·재질 이름·modifier·constraint와 누락된 단일 파일 이미지 목록을 기록한다. 다른 scene, 모든 외부 의존성, 실제 외형, 미저장 GUI 상태를 완전하게 검사하는 기능은 아니다. 전체 후보 목록을 자동으로 Jev에 전송하지 않는다.

`result.json`의 `source_sha256`는 후속 작업의 입력 전제다. 파일이 바뀌면 새 조사를 수행하고 선택을 다시 확인한다.

## 미리보기와 묶음 출력

```json
{
  "schema_version": 1,
  "operation": "asset_bundle",
  "source": "/absolute/character.blend",
  "source_sha256": "replace-with-the-64-character-sha256-from-inspection",
  "objects": ["Body", "Shirt"],
  "frame": 1,
  "preview": {"width": 512, "height": 512, "samples": 16}
}
```

`source_sha256`는 실제 조사값으로 교체한다. `preview` operation은 PNG만 만들고 `asset_bundle`은 PNG, 정적 메시의 `asset.blend`, `asset.glb`를 만든다. 복수의 정확한 이름을 직접 지정할 수 있으며, Jev의 단일 후보 선택기를 거칠 필요는 없다.

- 평가된 메시를 새 scene에 복사하고 world transform을 보존한다. 원본의 modifier stack·rig·animation을 내보내는 기능이 아니다.
- 카메라와 조명은 bounds에 맞춘 비교용 설정이다. 원래 카메라·조명·배경·compositor의 재현을 요청했다면 별도 recipe가 필요하다.
- 렌더는 Cycles CPU, 투명 배경 PNG다. 크기 64..2048, samples 1..128 범위에서 지정하며 기본 512×512/16 samples다. 프레임 기본값은 1이므로 필요한 프레임을 명시한다.
- `.blend`는 생성한 scene과 그 의존성을 임시 library에 모은 뒤 일반 main file로 저장한다. 텍스처를 모두 pack하는 기능이 아니다. GLB는 생성한 활성 scene과 선택한 메시로 범위를 제한한다. 재질 변환 가능성은 실제 대상 importer와 시각 결과로 확인한다.
- 링크된 메시, 활성 view layer에서 제외·숨김 처리된 오브젝트, rig/driver/constraint, Geometry Nodes와 simulation은 `needs_codex` 대상이다. 이러한 작업은 실제 요구에 맞는 recipe로 처리한다.

## 결과

stdout은 최종 JSON이고 Blender 출력은 `blender.log`에 저장한다. 반환 코드는 완료 `0`, 미지원·실패 `2`다.

| 상태 | 의미 | 후속 처리 |
| --- | --- | --- |
| `completed` | 지정 산출물이 존재하고 원본 파일 해시가 유지됨 | 산출물의 시각 검토와 대상 앱 가져오기 등 요청된 검증 수행 |
| `needs_codex` | 원본 변경·미지원 상태 등으로 자동 실행을 이어갈 수 없음 | `reason` 또는 `details.reason`을 읽어 재조사·작업 분해·기능 보완 |
| `failed` | 입력·프로세스·timeout·산출물 오류 | 로그와 부분 결과를 읽고 원인 해결 |

`verification.visual_review`와 `downstream_import`는 실행기에서 `not_performed`다. 실제 후속 확인을 했다면 그 증거를 별도로 보고한다. 완료 JSON 자체를 품질 검토로 사용하지 않는다.

## 공식 근거

2026-09-27 확인. 실행 목표 baseline은 Blender 4.5/5.2 LTS이며 실제 검증 버전은 [검증 기록](validation.md)에 적는다.

- [CLI 인자와 적용 순서](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html)
- [파일 열기와 저장](https://docs.blender.org/api/current/bpy.ops.wm.html)
- [데이터 library 읽기·쓰기](https://docs.blender.org/api/current/bpy.types.BlendDataLibraries.html)
- [operator context 제약](https://docs.blender.org/api/current/info_gotchas_operators.html)
- [Object와 view layer별 선택](https://docs.blender.org/api/current/bpy.types.Object.html)

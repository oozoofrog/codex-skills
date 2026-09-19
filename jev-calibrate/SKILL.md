---
name: jev-calibrate
description: Evaluate saved Jev choices against acceptable labels and check sensitivity to wording, language, and option order. Evaluation outputs never authorize production actions.
---
# Jev 판정 평가

이것은 `jev-workbench`의 목적별 진입 스킬이다. 현재 스킬 폴더의 형제 경로 `../jev-workbench/SKILL.md`를 먼저 읽어 공통 권한·전송·상태·재심 계약을 적용한다. 루트 경로가 다르게 설치되었다면 실제 스킬 목록에서 `jev-workbench` 경로를 찾아 사용한다. 존재하지 않으면 의존성이 없다고 알리고 허구의 CLI 명령을 실행하지 않는다.

요청에 맞는 문서 하나만 추가로 읽는다.

- `contract-calibration`: `../jev-workbench/references/contract-calibration.md`

해당 참조의 입력·실행·출력 계약을 그대로 따른다. 사용자 요청에 없는 다른 모드를 연쇄 호출하지 않는다. `scripts/jev_cli.py`는 workbench 폴더 안에 있다. 모든 파일 경로는 설치된 실제 스킬 경로로 해석한다.

결과에는 작업 범위, 모드(delegated/advisory/evaluation), 데이터 출처, 판정 상태, 실제 검증, 한계를 구분한다. fixture는 모델 평가가 아니며 API 호출이 없으면 Jev 판단을 받았다고 말하지 않는다.

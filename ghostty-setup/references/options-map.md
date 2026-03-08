# Ghostty 옵션 맵

## 목적

사용자 요청을 Ghostty 설정 키로 빠르게 매핑하고, 변경 시 부작용을 줄이기.

## 가독성/접근성

- `font-size`: 기본 가독성의 1순위. 작은 폭 조정(예: +1 또는 +2)부터 적용하기.
- `minimum-contrast`: 저대비 색 조합 보정. 너무 높이면 색감 왜곡 가능성 고려하기.
- `selection-background`, `selection-foreground`: 선택 영역 추적성이 낮을 때 함께 조정하기.

## 배경/전경 및 테마

- `background`, `foreground`: 전체 명암의 기준. 먼저 이 두 값을 안정화하기.
- `palette = N=#RRGGBB`: ANSI 색상 개별 튜닝. 톤 일관성을 유지하며 수정하기.
- `cursor-color`: 배경과 충분히 구분되도록 설정하기.

## 커서/입력 피드백

- `cursor-style`: `block`, `bar`, `underline` 중 작업 성격에 맞게 선택하기.
- `cursor-style-blink`: 피로감/주의 분산 이슈가 있으면 `false` 우선 검토하기.

## 레이아웃/여백

- `window-padding-x`, `window-padding-y`: 텍스트 밀집도 조절용.
- 여백은 폰트 크기 조정과 함께 다뤄 체감 균형을 맞추기.

## 투명도/배경 효과

- `background-opacity`: 반투명 사용 시 가독성 저하 가능성 확인하기.
- `background-blur`: 성능과 가독성 영향이 있어 필요 시에만 사용하기.

## 구성 관리

- `config-file = "..."`: 파일 분리 및 계층화의 핵심.
- 권장 구조:
  - `config`: 엔트리
  - `profiles/*.conf`: 공통/활성 프로필
  - `themes/*.conf`: 색상 정의

## 변경 우선순위 가이드

1. 사용자 불편 원인과 직접 연결된 키부터 조정하기.
2. 공통값과 테마값을 분리해 변경 반경을 최소화하기.
3. 여러 키를 함께 바꿨다면 검증 체크리스트를 더 엄격히 제공하기.

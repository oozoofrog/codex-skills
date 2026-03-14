# Frontend aesthetics guide

## 1. Typography
- 폰트는 UI 성격을 결정합니다.
- display font + body font 조합을 의도적으로 선택합니다.
- Arial, Roboto, Inter 같은 너무 익숙한 기본 선택은 이유가 있을 때만 사용합니다.
- 계층 구조를 spacing, weight, size 모두로 표현합니다.

## 2. Color and theme
- palette는 주조색 + 강한 포인트 색 구조가 보통 더 선명합니다.
- CSS variables 또는 token으로 일관성을 유지합니다.
- light/dark 어느 한쪽을 기본으로 정하고, 중간 지점의 애매한 회색 UI를 피합니다.

## 3. Motion
- 여기저기 작은 애니메이션을 흩뿌리기보다, 기억에 남는 순간을 몇 개 만드는 것이 낫습니다.
- page load, section reveal, hover, active state에 집중합니다.
- React라면 Motion 계열 라이브러리나 CSS transitions를 상황에 맞게 사용합니다.

## 4. Spatial composition
- 비대칭, 겹침, 크기 대비, 여백의 밀도 차이가 인상을 만듭니다.
- 카드만 반복하는 layout은 금방 평범해집니다.
- 화면마다 “메인 포인트”가 되는 요소를 하나 정합니다.

## 5. Background and detail
- solid color만 쓰지 말고 필요하면 질감, noise, mesh, border, shadow, transparency를 활용합니다.
- 단, decorative detail이 content readability를 해치면 줄입니다.

## 6. 상태 디자인
반드시 고려합니다.
- loading
- empty
- error
- hover/focus/active
- disabled
- mobile/tablet/desktop 반응형 변화

## 7. 금지에 가까운 흔한 패턴
- 보라 그라디언트 + 흰 카드 + 둥근 버튼 조합 남용
- 맥락 없는 glassmorphism 남용
- 모든 섹션이 동일한 spacing rhythm
- 미감 설명 없이 템플릿만 복제한 듯한 랜딩 페이지

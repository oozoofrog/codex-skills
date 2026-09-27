# 재질 수정과 범위 보존

material slot과 shared material user를 조사한다. 재질 하나를 바꾸면 여러 object가 달라질 수 있으므로 보호 대상이 같은 material을 참조하면 복제하거나 전체 영향 범위를 plan에 넣는다. node graph의 기본값·links·nested groups를 함께 비교한다. material 이름만 같은 것은 동일성 증거가 아니다.

재질 retry에서는 geometry/transform/modifier unchanged와 camera/light 보호를 검사한다. render engine·color management·exposure·조명을 바꿔 결함이 가려지는 식의 retry는 별도 계획으로 구분한다. external texture bytes·UDIM·packed state까지 전달해야 할 때는 경로/파일 hash와 실제 재열기 검사를 추가한다.

실제 preview에서 texture 누락, magenta, normal-map 방향, roughness/alpha를 관찰한다. observations를 Jev에 보내 수용 가능성이나 다음 수정 범위를 결정하게 할 수 있다. 숫자 node property equality는 code가 확인한다.

# 애니메이션·리그 조사

armature bone 이름/parent/rest head·tail, pose matrices/constraints, mesh vertex groups·shape key·Armature modifier 연결을 먼저 조사한다. 기본 inspector의 rig 요약은 조사 출발점이며 Action/NLA/driver 전체 의미를 검증하지 않는다. 해당 작업은 keyframe/action slot과 범위·순환·driver dependency를 추가 검사한다.

부모 pose 변경 뒤 dependency graph를 갱신하고 자식 좌표를 계산한다. frame_set 후 evaluated_get/to_mesh를 다시 얻고 `to_mesh_clear()`로 해제한다. 계획 궤적과 실제 evaluated vertices를 비교한다. 접지·충돌·회전 점프·cache 유지 여부를 render와 별도로 검사한다.

모든 bake를 매 iteration 반복하지 않는다. 영향 있는 inputs가 바뀌었을 때만 관련 cache를 재bake하고 저장본을 새 프로세스로 열어 확인한다. [캡슐 데모](capsule-demo.md)는 특정 8-bone rigid rig와 Cloth의 실증 예이며 일반 humanoid IK/retarget 또는 export 지원이 아니다.

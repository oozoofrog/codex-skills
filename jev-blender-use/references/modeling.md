# 모델링과 게임 자산

보호 대상을 이름·data 관계·raw/evaluated signature로 고정한다. mesh 공유 user, linked library, shape key를 먼저 조사한다. bpy.data와 bmesh는 검토한 script로 사용하고 변경 mode/context를 명시한다. delete/remesh/join/apply 같은 작업은 exact guard와 checkpoint를 통과해야 한다.

non-destructive modifier와 duplicate를 먼저 검토하고 apply를 전달 직전까지 늦춘다. Decimate ratio는 triangle 기준이어서 quad source의 polygon 감소율과 같지 않다. 예제는 원본 polygon/triangle 수에서 budget을 계산하고 실제 evaluated polygon으로 결과를 검증한다.

normals 문제는 winding conflict/nonmanifold/degenerate 후보와 실제 shading 관찰을 함께 본다. 열린 surface를 무조건 오류로 처리하지 않는다. UV 보존은 geometry signature에 포함되지만 stretch/overlap/texel density는 작업별 정확한 validator가 추가로 필요하다.

게임 자산 최적화는 polygon뿐 아니라 material slot·draw call·instances·UV·리그·대상 importer 요구를 명시한다. `.blend` 검사를 외부 엔진 import 성공으로 대체하지 않는다. 기존 정적 GLB export는 [기존 계약](workflows.md)의 제한을 유지한다.

[bmesh API](https://docs.blender.org/api/current/bmesh.html), [modifier API](https://docs.blender.org/api/current/bpy.types.Modifier.html)를 해당 버전에 맞춰 확인한다.

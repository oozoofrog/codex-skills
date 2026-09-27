# Geometry Nodes와 반복 구조

대량 반복의 전략 기준은 개수뿐 아니라 편집 단위·변형·export 대상이다. individual meshes, linked instances, Geometry Nodes instances 중 적합한 후보를 준비하고 기준이 모호할 때 Jev strategy를 사용한다. 실제 선택과 제공한 기준을 기록하며 모델의 장문 이유를 요구하지 않는다.

[forest 예제](../examples/geometry-nodes/create.py)는 grid의 20,000 points에 prototype을 instance한다. `GeometryNodeTree.interface.new_socket`, Object Info → Instance on Points → Group Output을 사용한다. 원본 mesh와 evaluated instance 수를 분리해 검사한다. instances를 realize하면 메모리·polygon 수·전달 의미가 달라지므로 명시된 이유 없이 적용하지 않는다.

inspector는 modifier가 참조한 node tree 내용과 nested graph를 hash하고 depsgraph instance를 요약한다. evaluated mesh polygons=0인 instance-only 출력은 비어 있는 장면과 같지 않다. random seed와 입력 geometry/외부 asset 버전을 고정한다.

노드 이름·socket은 버전별로 바뀔 수 있다. [Geometry Nodes 문서](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/index.html)와 실제 bpy node inputs를 확인한다. 존재하지 않는 socket을 유사 이름으로 추측해 연결하지 않는다.

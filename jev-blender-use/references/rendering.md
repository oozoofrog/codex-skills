# Preview와 최종 렌더

낮은 samples·작은 해상도 preview로 구도·재질·clipping을 먼저 확인한다. 현재 camera·engine·frame·해상도·samples를 receipt에 기록한다. quick preview와 최종 render의 품질/시간/검증 주장을 구분한다.

CLI render는 저장된 source의 별도 프로세스에서 64..4096px, Cycles CPU samples 1..128로 실행하고 source를 저장하지 않는다. Eevee 등 다른 engine에서는 Cycles samples가 적용됐다고 하지 않는다. 파일 해시와 receipt를 candidate에 연결한다. full rendering 설정은 별도 script/plan으로 다룬다.

MCP viewport image는 현재 view의 근거다. camera final output과 같다고 가정하지 않는다. 재생 중 frame이 바뀌는 캡처는 같은-state 완료 근거가 될 수 없다. actual image block/파일을 열고 subject clipping, artifacts, silhouette, material, lighting을 관찰한다.

애니메이션은 시작·중간·끝 몇 장만으로 전체 동작을 증명하지 않는다. frame 수·시간·sequence 연속성, 중요한 접지/충돌 frame, 실제 재생을 확인한다. `.blend` 저장 성공과 캐시/asset 전달 성공을 구분한다.

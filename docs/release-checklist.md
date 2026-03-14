# Release Checklist

`codex-skills` 저장소 자체를 릴리즈할 때 사용하는 실무 체크리스트입니다.

## 1. 릴리즈 범위 확인
- 어떤 skill이 추가/수정됐는지 정리
- 이번 태그가 patch인지, 더 큰 묶음 릴리즈인지 정리
- 릴리즈 노트에 넣을 핵심 변경 2~5개 추리기

## 2. 문서 점검
- `README.md`에 신규 skill 또는 구조 변경이 반영되었는지 확인
- `CHANGELOG.md`의 `Unreleased` 항목이 최신 상태인지 확인
- 필요하면 `docs/release-notes-template.md`를 기준으로 초안 작성

## 3. skill 검증
신규/수정된 skill마다 아래를 확인합니다.

```bash
python3 /Users/oozoofrog/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-dir>
```

확인 항목:
- `SKILL.md` 형식 유효성
- `agents/openai.yaml` 존재 및 동기화 여부
- references/scripts 경로가 깨지지 않았는지

## 4. 스크립트 검증 (해당 시)
script가 추가/수정됐다면 최소한 문법 검증을 수행합니다.

예시:
```bash
bash -n <script.sh>
python3 -m py_compile <script.py>
```

가능하면 기능 검증도 함께 수행합니다.
- dry-run 지원 script면 dry-run 실행
- 임시 디렉터리에서 안전하게 재현 가능한 시나리오가 있으면 실제로 확인

## 5. Git 상태 점검
- 작업 트리가 의도한 변경만 포함하는지 확인
- `git status --short`
- 최근 커밋 메시지가 릴리즈 맥락과 맞는지 확인
- 필요하면 `main` 최신 상태로 정리

## 6. 태그 생성 전 확인
- `CHANGELOG.md`의 `Unreleased` 내용을 릴리즈 버전으로 이동할지 확인
- 새 태그 버전 결정 (`vX.Y.Z`)
- 기존 태그 목록을 보고 중복 없는지 확인

예시:
```bash
git tag --sort=-creatordate | sed -n '1,20p'
```

## 7. 릴리즈 생성 순서
1. 변경 커밋을 `main`에 반영
2. annotated tag 생성
3. tag push
4. GitHub Release 생성

예시:
```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --notes-file docs/release-notes-template.md
```

## 8. 릴리즈 후 확인
- GitHub Release 페이지가 정상 생성됐는지 확인
- 태그가 원격에 올라갔는지 확인
- `README.md`, `CHANGELOG.md`, docs 링크가 깨지지 않았는지 다시 확인
- 필요하면 다음 사이클을 위해 `CHANGELOG.md`에 `Unreleased` 구간을 비워둠

## 9. 최소 성공 기준
- 관련 skill `quick_validate.py` 전부 통과
- 문서 링크가 깨지지 않음
- 태그/릴리즈가 같은 버전을 가리킴
- README만 읽어도 새/수정된 skill의 목적을 빠르게 파악 가능

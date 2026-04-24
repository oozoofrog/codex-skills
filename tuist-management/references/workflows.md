# Tuist Workflows

## Module lifecycle 공통 preflight

모듈 추가/삭제/이동/변경은 파일 작업보다 먼저 manifest owner와 참조 범위를 확정합니다.

```bash
git status --short
find Projects -maxdepth 2 -name Project.swift | sort
rg -n "<ModuleName>|<TargetName>|\\.Module\\.<camelName>|import <ModuleName>" Projects Tuist Workspace.swift Tuist.swift
```

확인해야 할 축:

- project directory: `Projects/<Module>/`
- source/resource/test directory: `Projects/<Module>/<Target>/Sources`, `Resources`, `<Target>Tests/Sources`
- manifest: `Projects/<Module>/Project.swift`
- internal alias: `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/Dependencies/Dependencies+Module.swift`
- external alias/package: `Dependencies+SPM.swift`, `Tuist/Package.swift`
- target helper: `Targets/SampleApp/**`, `Targets/Tests/**`, app extension helper
- schemes/test plans: `SchemeFactory`, `generateDefaultScheme`, `.xctestplan`
- source imports and resource paths: `import <Module>`, path strings, Core Data model paths

## 모듈 추가

1. 유사한 계층의 기존 모듈 1개 이상을 골라 `Project.swift` 구조를 비교한다.
2. 새 directory가 필요한지, 기존 project 안에 target만 추가하면 되는지 결정한다.
3. 새 project면 기본 구조를 만든다.

```text
Projects/<Module>/
├── Project.swift
├── <Module>/Sources/
├── <Module>/Resources/        # 필요 시
└── <Module>Tests/Sources/     # 필요 시
```

4. 기본 target은 `StaticFramework`를 사용한다. dynamic framework는 runtime/resource/linkage 근거가 있을 때만 사용한다.
5. 외부에서 참조하는 모듈이면 `Dependencies+Module.swift`에 `.Module.<camelName>` alias를 추가한다.
6. test target은 `XCTestItem`과 `.xctestplan`, sample app은 기존 `Targets/SampleApp/*SampleApp.swift` 패턴을 사용한다.
7. `tuism` 후 새 module scheme 또는 영향 scheme을 `$build-environment`로 빌드한다.

## 모듈 삭제

삭제는 항상 "참조 제거 → manifest 제거 → 파일 삭제" 순서로 수행합니다.

1. 참조 인벤토리를 만든다.

```bash
rg -n "<ModuleName>|<TargetName>|\\.Module\\.<camelName>|import <ModuleName>" Projects Tuist Workspace.swift Tuist.swift
find Projects/<ModuleName> -maxdepth 5 -type f | sort
```

2. 삭제 대상에 보존 잠금 파일이 있는지 확인한다.
   - DB migration, Core Data model, `.sqlite`, certificate, keychain migration, `Configs/*.xcconfig`, `PrivacyInfo.xcprivacy`, `oss_notice.html`
   - 포함되면 삭제하지 말고 사용자 확인을 받는다.
3. 다른 module의 `dependencies`에서 참조를 제거한다.
4. `Dependencies+Module.swift` alias를 제거하거나, 호환 alias를 남겨야 하는지 판단한다.
5. scheme/sample app/test helper/test plan 참조를 제거한다.
6. 완전 삭제 요청인 경우에만 source/resource/test directory를 삭제한다. target 제외 요청이면 파일은 보존한다.
7. 삭제 후 `rg`로 잔여 참조를 확인하고 `tuism`을 실행한다.

## 모듈 이동

1. 이동 범위를 분리한다.
   - directory만 이동
   - target name 변경
   - product/module import name 변경
   - bundle ID 변경
   - scheme/test plan/sample app 이름 변경
2. tracked 파일은 `git mv`를 사용한다.

```bash
git mv Projects/<OldModule> Projects/<NewModule>
```

3. `Project.swift` 내부 path 문자열, `projectName`, target names, `.xctestplan` 경로를 새 위치에 맞춘다.
4. `Dependencies+Module.swift`의 `TargetDependency.project(target:path:)` path를 수정한다.
5. 다른 `Projects/**/Project.swift`, sample app/test helper, source import를 갱신한다.
6. old/new 이름 모두 검색한다.

```bash
rg -n "<OldModule>|\\.Module\\.<oldCamel>|import <OldModule>" Projects Tuist
rg -n "<NewModule>|\\.Module\\.<newCamel>|import <NewModule>" Projects Tuist
```

7. `tuism` 후 이동 전후 영향 scheme을 빌드한다.

## 모듈 이름 변경

1. Swift module name 변경인지, 표시 이름/scheme만 변경인지 먼저 확정한다.
2. Swift module name 변경이면 코드의 `import <OldName>`까지 변경 대상이다.
3. `Dependencies+Module.swift` alias는 새 이름을 추가하고, 기존 alias 제거가 downstream에 미치는 영향을 확인한다.
4. test plan, sample app, scheme 이름은 사용자-facing 영향이 있으므로 변경 이유를 결과에 명시한다.
5. bundle ID 변경이 포함되면 entitlements/provisioning 영향까지 별도 리스크로 보고한다.

## 모듈 변경

다음 변경은 `Projects/<Module>/Project.swift`가 1차 owner입니다.

- static/dynamic framework 전환
- sources/buildableFolders 변경
- resources glob 추가/변경
- Core Data model 추가
- SwiftLint/script 추가
- settings/configuration 변경
- test/sample app dependency 변경

여러 project에 반복되는 변경이면 `ProjectDescriptionHelpers`나 `TalkPlugin` helper에 공통화할지 먼저 검토합니다. 단, 광범위 helper 변경은 영향 범위가 크므로 `tuism`과 대표 scheme 빌드가 필요합니다.

## Existing module dependency 변경

1. 대상 모듈의 `Projects/<Module>/Project.swift`를 읽는다.
2. dependency가 내부 모듈이면 `Dependencies+Module.swift`, SPM이면 `Dependencies+SPM.swift`에 이미 shortcut이 있는지 확인한다.
3. 기존 dependency 배열 스타일을 유지해 최소 수정한다.
4. 아키텍처 하향식 의존 원칙을 검토한다. 서비스 간 직접 참조가 필요해 보이면 공유 로직을 AppBase 이하로 옮기는 대안을 먼저 제시한다.
5. `tuism` 실행 후 영향 scheme을 `$build-environment`로 빌드한다.

## 새 모듈 또는 framework target 추가

1. 유사 모듈의 `Projects/<Existing>/Project.swift`를 1개 이상 비교한다.
2. `StaticFramework`/`DynamicFramework` 선택은 기존 계층과 linker/runtime 요구를 근거로 정한다.
3. 기본 구조는 `Projects/<Module>/<Module>/Sources`, 필요 시 `Tests/Sources`, `Resources` 패턴을 따른다.
4. 다른 모듈에서 참조해야 하면 `Dependencies+Module.swift`에 `.Module.<name>` shortcut을 추가한다.
5. scheme은 기존 패턴에 맞춰 `generateDefaultScheme` 또는 `SchemeFactory.build`를 사용한다.
6. `tuism` 실행 후 새/영향 scheme을 빌드한다.

## Test target 추가

1. 기존 `XCTestItem` 선언과 `.xctestplan` 위치를 확인한다.
2. `resources`가 필요한 경우 테스트 SQLite 등 삭제 금지 파일을 보존한다.
3. `additionalFiles`에 test plan을 포함하는 기존 패턴이 있으면 유지한다.
4. `tuism` 후 `$build-environment`의 `-t` 흐름으로 테스트 가능 여부를 확인한다.

## Sample app 추가 또는 수정

1. 기존 `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/Targets/SampleApp/*SampleApp.swift`를 먼저 확인한다.
2. sample app target helper를 수정하거나 `Projects/<Module>/Project.swift`에 연결한다.
3. configuration은 보통 `Sandbox(iTeam)-SampleApp` 또는 스킬/팀 지침의 sample app 설정을 따른다.
4. `tuism` 후 sample app scheme을 빌드한다.

## Scheme/build setting 변경

1. `Schemes/**`, `BuildSettings/**`, 대상 `Project.swift` 중 실제 owner를 먼저 찾는다.
2. 개인 preference(`com.kakao.tuist.private.plist`)와 공유 preference(`com.kakao.tuist.plist`)를 구분한다.
3. 공유 설정 변경은 영향 scheme 목록을 결과에 명시한다.
4. `tuism` 후 관련 scheme을 확인한다.

## SPM/package 업데이트

1. 먼저 `tuism -u <package>` 또는 `tuism -u <package> <revision>` 경로가 맞는지 확인한다.
2. `Tuist/Package.swift`, `Tuist/Package.resolved`, `Tuist/Dependencies/Lockfiles/**` 변경을 분리해서 확인한다.
3. lockfile만 손으로 임의 편집하지 않는다.
4. `tuism` 후 실제 빌드 대상에서 링크/resolve 문제가 없는지 검증한다.

## Generation failure 또는 drift 진단

1. `tuism check`로 parse/fetch/generate 필요 여부를 확인한다.
2. 실패 로그의 첫 manifest/helper 파일과 line을 기준으로 읽는다.
3. `BuildValidator` dependency violation이면 dependency direction과 final target 여부를 먼저 확인한다.
4. generated `.xcodeproj` diff가 있더라도 직접 고치지 말고 원인 manifest/helper를 수정한다.
5. 해결 후 `tuism`을 다시 실행하고 `git diff --stat`으로 의도치 않은 광범위 변경이 없는지 확인한다.

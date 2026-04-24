---
name: tuist-management
description: Use when adding, deleting, moving, renaming, or changing talkmediakitui Tuist modules/targets, Project.swift manifests, Workspace.swift, Tuist.swift, TalkPlugin helpers, module/SPM dependencies, schemes, build flags, or when tuism regeneration is required.
---

# Tuist Management

`talkmediakitui` 저장소의 Tuist 매니페스트와 생성 워크스페이스를 안전하게 관리하기 위한 repo-local 스킬입니다. 생성물보다 매니페스트를 source of truth로 취급하고, 변경 후 `tuism`으로 재생성 여부를 확인합니다.

## When to use

- `Projects/**/Project.swift`, `Workspace.swift`, `Tuist.swift`, `Tuist/Package.swift`를 수정/리뷰할 때
- 새 모듈, 타겟, 테스트 타겟, 샘플앱, 앱 익스텐션, scheme을 추가할 때
- 기존 모듈/타겟을 삭제, 이동, 이름 변경, static/dynamic 전환, resource/test/sample app 구조 변경할 때
- 내부 모듈 의존성(`.Module.*`) 또는 외부 SPM 의존성(`.external`)을 추가/정리할 때
- `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/**`의 settings, scripts, schemes, target model, dependency helper를 변경할 때
- `tuism`, `make install`, `make addscheme`, Tuist 환경 플래그 관련 문제를 진단할 때

## Do not use when

- Swift/UIKit/SwiftUI 구현만 바꾸고 Tuist 매니페스트가 바뀌지 않을 때: `$swift-conventions` 사용
- 빌드/테스트 실행 자체가 목적일 때: `$build-environment` 사용
- Xcode MCP로 빌드를 요청받은 경우: `$build-environment`의 MCP 예외 규칙을 따른다

## Guardrails

- 생성된 `.xcodeproj`/`.xcworkspace`를 직접 수정하지 않는다. 반드시 `Project.swift`/Tuist helper를 수정한 뒤 `tuism`으로 재생성한다.
- `Tuist.swift`, `Workspace.swift`, `Tuist/Package.swift`, `Projects/*/Project.swift`, `Configs/*.xcconfig`, `Resources/PrivacyInfo.xcprivacy`는 보존 잠금 파일이다. 삭제가 필요하면 먼저 사용자 확인을 받는다.
- 모듈 삭제/이동 전에는 참조 인벤토리를 만든다. `Project.swift`, `.Module.*` alias, sample app helper, scheme, test plan, localized/resource/core data 참조, 코드 import를 확인하지 않은 삭제는 금지한다.
- 삭제 대상에 DB migration, Core Data model, 테스트 SQLite, 인증서, 키체인 migration, xcconfig, privacy/oss notice가 포함되면 즉시 중단하고 사용자 확인을 받는다.
- 이동/이름 변경은 tracked 파일이면 `git mv`를 우선 사용하고, untracked/ignored 파일은 상태를 명시한 뒤 처리한다.
- 작업 전 `git status --short`로 기존 사용자 변경을 확인하고, 관련 없는 변경을 되돌리거나 덮어쓰지 않는다.
- 서비스 간 직접 의존을 추가하지 않는다. 공유 로직은 계층 원칙(Service → ServiceBase → AppBase → CoreModules → SharedBase → Core)에 맞는 위치로 이동/추상화한다.
- Tuist 매니페스트 변경 후에는 최소 `tuism`을 실행한다. SPM 의존성 추가/갱신이면 `make install` 또는 `tuism` 후 `make spm_resolved_versions` 필요 여부도 확인한다.

## Source map

| 목적 | 우선 확인 파일 |
| --- | --- |
| 루트 Tuist 설정/플러그인 | `Tuist.swift` |
| 워크스페이스 포함 프로젝트 | `Workspace.swift` |
| 모듈/타겟 정의 | `Projects/<Project>/Project.swift` |
| 내부 모듈 alias | `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/Dependencies/Dependencies+Module.swift` |
| 외부 SPM alias | `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/Dependencies/Dependencies+SPM.swift` |
| SPM package 선언/settings | `Tuist/Package.swift` |
| 설정/configuration | `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/BuildSettings/**`, `Configuration/**` |
| scheme 생성 | `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/Schemes/**`, `Scripts/addscheme/**` |
| target wrapper | `Model/*Item.swift`, `Targets/**` |
| sample app/test helper | `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/Targets/SampleApp/**`, `Targets/Tests/**` |
| scaffold template | `Tuist/Templates/**`, `make scaffold-test project=<Module> target=<Target>` |
| 생성/캐시/스캐폴드 명령 | `Makefile`, `Scripts/tuist/**` |

## Quick start

1. `git status --short`로 현재 변경 범위를 먼저 확인한다.
2. 변경 유형을 분류한다: 모듈 추가, 모듈 삭제, 모듈 이동/이름 변경, target 변경, dependency 변경, SPM 변경, scheme 변경, build setting 변경, generation 문제 중 하나.
3. 위 Source map에서 source of truth 파일만 최소 수정한다.
4. 삭제/이동/이름 변경이면 `rg`로 참조 인벤토리를 먼저 만들고, 보존 잠금 파일 포함 여부를 확인한다.
5. 내부 target 의존성은 기존 alias가 있으면 `.Module.<name>`을 재사용하고, 없을 때만 `Dependencies+Module.swift`에 추가한다.
6. 외부 SPM은 `Tuist/Package.swift`에 package를 선언하고 `Dependencies+SPM.swift`에 사용 alias를 추가한다.
7. Tuist 변경 후 `tuism`으로 워크스페이스 생성을 확인한다. SPM 그래프 변경이면 `make install`/`make spm_resolved_versions`도 검토한다.
8. 코드 타겟까지 바뀌었거나 빌드 영향이 있으면 `$build-environment`로 관련 scheme을 빌드한다.

## Workflows

### 1. 모듈 추가

- 기존 유사 모듈 1개 이상을 기준으로 `Projects/<NewModule>/Project.swift` 구조를 맞춘다.
- 새 모듈이 별도 project라면 `Projects/<NewModule>/<NewModule>/Sources`를 기본 소스 루트로 만들고, 필요 시 `Resources`, `<NewModule>Tests/Sources`, `.xctestplan`을 함께 만든다.
- target은 기본 `StaticFramework`를 사용한다. runtime loading, resource bundle, linker 요구 등 근거가 있을 때만 `DynamicFramework`를 선택한다.
- 외부에서 참조할 target이면 `Dependencies+Module.swift`에 `.Module.<camelName>` alias를 추가한다.
- scheme은 기존 패턴에 맞춰 `generateDefaultScheme` 또는 `SchemeFactory.build`를 사용한다.
- test target은 `XCTestItem`, sample app은 기존 `Targets/SampleApp/*SampleApp.swift` 패턴을 재사용한다.

### 2. 모듈 삭제

- 삭제 전 참조 인벤토리를 만든다.

```bash
rg -n "<ModuleName>|<TargetName>|\\.Module\\.<camelName>|import <ModuleName>" Projects Tuist Workspace.swift Tuist.swift
find Projects/<ModuleName> -maxdepth 4 -type f | sort
```

- 참조 제거 순서는 보통 `Project.swift` dependency → `Dependencies+Module.swift` alias → scheme/sample app/test helper → source/resource directory 순서다.
- 삭제 대상에 보존 잠금 파일(DB migration, Core Data model, sqlite, certificate, keychain migration, xcconfig, privacy/oss notice)이 있으면 사용자 확인 전 삭제하지 않는다.
- 완전 삭제가 아니라 target만 제외하는 요청이면 파일 삭제보다 `Project.swift`의 target 선언/참조 제거를 우선한다.
- 삭제 후 `rg`로 잔여 참조가 없는지 재확인하고 `tuism`을 실행한다.

### 3. 모듈 이동 또는 이름 변경

- 이동/rename 전 기존 이름과 새 이름의 owner를 명확히 한다: project directory, target name, product name, bundle ID, module alias, scheme, test plan, sample app 중 무엇을 바꾸는지 분리한다.
- tracked 파일은 `git mv`로 이동한다.
- 반드시 갱신할 후보:
  - `Projects/<Old>/Project.swift` 경로와 `projectName`, target name, test plan 문자열
  - `Dependencies+Module.swift`의 `.Module.<old>` alias/path
  - 다른 `Projects/**/Project.swift`의 dependency 참조
  - `Targets/SampleApp/**`, `Targets/Tests/**`, scheme 이름, `.xctestplan`
  - 코드의 `import <OldModule>`와 resource/core data path 문자열
- 이름 변경 후 `rg -n "<OldName>|\\.Module\\.<oldCamel>|import <OldName>" Projects Tuist`로 잔여 참조를 확인한다.

### 4. 모듈/target 변경

- static ↔ dynamic, resource 추가, Core Data model 추가, buildable folder 변경, settings/script 변경은 모두 `Projects/<Module>/Project.swift`가 1차 owner다.
- 여러 모듈에 공통 적용되는 규칙이면 개별 `Project.swift` 반복 수정 전에 `Tuist/Plugins/TalkPlugin/ProjectDescriptionHelpers/**`에 helper가 있는지 확인한다.
- resource 추가는 target-local glob을 명시하고, generated resource accessor에 기대지 않는다. 이 저장소는 `resourceSynthesizers: []` 패턴을 사용한다.
- Core Data model 추가/변경은 migration 영향이 있으므로 삭제/이동과 동일하게 보존 잠금 규칙을 적용한다.

### 5. 새 framework target 추가

- `Projects/<Owner>/Project.swift`에 `ModuleName` 상수를 먼저 추가한다.
- 기본은 `StaticFramework`를 사용한다. dynamic linkage가 필요한 근거가 있을 때만 `DynamicFramework`를 사용한다.
- 새 소스 폴더는 가능하면 `buildableFolders: [.folder("<Target>/Sources")]` 패턴을 따른다.
- 리소스가 있으면 `resources: ["<Target>/Resources/**"]`처럼 target-local glob을 명시한다.
- 공통 settings는 `.framework`, SwiftLint는 `scripts: [.swiftlint]`를 우선 사용한다.
- 외부 프로젝트에서 참조해야 하는 target이면 `Dependencies+Module.swift`에 `.Module.<camelName>` alias를 추가한다.

### 6. 테스트/샘플앱 추가

- 단위 테스트는 `XCTestItem`, UI 테스트는 `XCUITestItem`, 샘플앱은 `AppItem`을 사용한다.
- 테스트 target은 `additionalFiles`에 `.xctestplan`을 포함하고, `dependencies`는 테스트 대상 target을 직접 참조한다.
- 샘플앱은 필요한 경우 `../../Resources/Certificates/**`, `../AppTalk/Talk/Resources/**`, 문자열 리소스 등 기존 샘플앱 패턴을 재사용한다.
- 새 테스트 템플릿이 필요하면 `make scaffold-test project=<Module> target=<Target>`를 우선 검토한다.

### 7. 내부 모듈 dependency 추가

- `Projects/<Owner>/Project.swift`의 `dependencies`에 `.Module.<name>` 또는 `.target(name:)`를 추가한다.
- 같은 `Project.swift` 안의 target 간 의존은 `.target(name:)`, 다른 프로젝트 target은 `.Module.*` alias를 우선한다.
- alias가 없으면 `Dependencies+Module.swift`에 `TargetDependency.project(target:path:)`를 추가하되 계층 방향을 먼저 검증한다.
- service module이 다른 service module을 직접 참조하게 만들지 않는다.

### 8. SPM dependency 추가/수정

- package 선언은 `Tuist/Package.swift`가 source of truth다.
- 사용할 product alias는 `Dependencies+SPM.swift`에 `public static let <name>: TargetDependency = .external(name: "ProductName")` 형태로 추가한다.
- target에서는 raw `.external(name:)`를 반복하지 말고 alias를 사용한다.
- `'<Module>' is not a valid configured external dependency` 오류가 나면 Xcode 프로젝트를 만지지 말고 `make install` 또는 `tuism`으로 graph를 갱신한다.

### 9. scheme 관리

- shared scheme이 필요한 경우 `SchemeFactory`/`generateDefaultScheme` 사용 여부를 먼저 확인한다.
- 개인용 scheme 추가는 `make addscheme`을 사용해 `Tuist/Preferences/com.kakao.tuist.private.plist`에 추가한다.
- `Workspace.swift`는 `autogeneratedWorkspaceSchemes: .disabled`이므로, scheme 누락은 자동 생성 기대보다 명시적 scheme 설정/개인 plist를 먼저 의심한다.

### 10. 생성 옵션과 환경 플래그

자주 쓰는 플래그:

| 플래그 | 의미 |
| --- | --- |
| `TUIST_IS_LIGHT_BUILD=true` | 앱 익스텐션/PAY 모듈 제외 경량 구성 |
| `TUIST_WITHOUT_DSYM=true` | dSYM 생성 비활성화 |
| `TUIST_IS_NO_PAY=true` | PAY 모듈 제외 |
| `TUIST_USE_DEBUG_PAY_FRAMEWORK=true` | PAY Debug framework 사용 |
| `TUIST_FORCE_SPM_RELEASE=true` | SPM target Release 강제 |
| `TUIST_IS_NO_REVEAL=true` | Reveal 의존성 제외 |

대표 명령:

```bash
tuism
make install
make addscheme
TUIST_IS_LIGHT_BUILD=true TUIST_WITHOUT_DSYM=true tuism
```

## Verification

- 매니페스트만 바꿨다면 `tuism` 성공 여부를 최소 검증으로 보고한다.
- 모듈 추가/삭제/이동/이름 변경은 rg 잔여 참조 확인(`rg ...`)과 `tuism` 성공을 최소 검증으로 보고한다.
- SPM 변경은 `make install` 또는 `tuism` 결과와 package resolved 변경 여부를 함께 확인한다.
- build setting/target/dependency 변경은 생성 성공 후 `$build-environment`로 관련 scheme 빌드를 실행한다.
- 검증을 생략해야 하면 어떤 검증을 생략했는지와 남은 리스크를 명시한다.

## Reference files

필요한 경우만 아래 문서를 추가로 읽습니다.

- `references/repo-tuist-map.md`: Tuist 파일 지도와 module lifecycle owner matrix
- `references/workflows.md`: 모듈 추가/삭제/이동/이름 변경/변경 상세 절차

## Review Harness

- mode: required
- 공통 기준: `../../../docs/review-harness.md`
- planner: 요청을 모듈 추가/삭제/이동/이름 변경/속성 변경/dependency/SPM/scheme/generation 문제로 분류하고 source of truth를 정한다.
- generator: generated project를 직접 수정하지 않고 `Projects/**/Project.swift`와 TalkPlugin helper만 최소 변경한다.
- evaluator: 참조 인벤토리, 보존 잠금 파일 위반 여부, dependency 방향, `tuism` 결과, 필요 시 `$build-environment` 빌드를 검증한다.
- 평가축: module lifecycle owner 선택 정확성, 삭제/이동 safety, dependency 계층 준수, generated file 직접 수정 방지, regeneration/build 검증 적절성
- artifacts/evidence: `rg` 참조 확인 결과, 변경 파일 목록, `git diff --stat`, `tuism` 로그, 빌드/테스트 로그 또는 생략 사유
- pass condition: 모듈 추가/삭제/이동/변경 후 잔여 참조와 generated drift가 설명 가능하고, `tuism` 성공 또는 실패 원인이 명확해야 한다.
- 자동 다음 행동: `pass`면 완료 보고, `refine`이면 manifest/helper/참조를 수정하고 `tuism` 재실행, `critical`이면 삭제/이동을 중단하고 보존 잠금 또는 dependency rule 위반을 먼저 복구한다.

## Output expectation

응답에는 다음을 포함한다.

1. 수정한 Tuist 관련 파일 목록
2. 모듈 추가/삭제/이동/변경, target/dependency/scheme/SPM 중 어떤 관리 흐름을 적용했는지
3. 실행한 검증 명령과 결과
4. 남은 작업 또는 사용자가 확인해야 할 선택지

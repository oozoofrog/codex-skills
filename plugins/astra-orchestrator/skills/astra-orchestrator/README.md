# Astra Orchestrator

모든 참여 세션을 GPT-6 Astra로 유지하고 지속 리더가 필요한 Worker, Git Steward, 독립 Reviewer를 조정하는 Codex 스킬이다. 정책은 [SKILL.md](SKILL.md), 도구 호출은 [session-tools.md](references/session-tools.md), 전달/반환은 [packets.md](references/packets.md), Git 안전 규칙과 결과 형식은 [git-steward.md](references/git-steward.md)에 있다.

| 역할 | 설정 |
| --- | --- |
| Leader | Astra / xhigh |
| Worker | Astra / medium(기계적), high(일반 구현), xhigh(난제·반복 실패) |
| Git Steward | Astra / medium(조사), high(변경·통합), xhigh(conflict·history 난제) |
| Independent Reviewer | Astra / max(중요한 milestone·최종 독립 판정) |

## 설치와 발견

정식 진입 파일명은 대문자 `SKILL.md`다. 소문자 skill.md를 별도 중복 파일로 만들지 않는다. name과 description을 YAML frontmatter에, UI 표시 정보를 agents/openai.yaml에 둔다. 자동 선택 기본값을 유지하며 description으로 적용 범위를 제한했다.

이 제작 환경의 기본 사용자 스킬 위치는 `${CODEX_HOME:-$HOME/.codex}/skills/astra-orchestrator`다. 현재 공식 문서는 사용자 위치 `~/.agents/skills`, 프로젝트 위치 `.agents/skills`도 안내한다. 실제 로더에서 발견되는지 확인하고 **한 위치에만 설치**한다. 같은 이름을 여러 루트에 복제하면 중복 표시될 수 있다.

다른 컴퓨터에서는 패키지 폴더가 있는 디렉터리에서 아래처럼 설치한다. 기존 대상이 있으면 덮어쓰지 않고 기존 버전부터 확인한다.

```sh
dest="$HOME/.agents/skills/astra-orchestrator"
if [ -e "$dest" ] || [ -L "$dest" ]; then
  printf '%s\n' "이미 존재합니다: $dest"
else
  mkdir -p "$HOME/.agents/skills" && cp -R ./astra-orchestrator "$dest"
fi
```

Codex는 스킬 변경을 자동 감지한다. 새 작업의 스킬 선택기에서 Astra Orchestrator 또는 `$astra-orchestrator`를 확인한다. 표시되지 않으면 Codex를 재시작하고 경로·비활성화 설정·목록 예산 제한을 확인한다. 파일 검증과 로더 발견, 실제 모델 실행은 서로 다른 검증 단계다.

2026-09-05 제작 환경에서는 CLI 0.149.1의 실제 스킬 로더가 `.codex/skills/astra-orchestrator/SKILL.md`를 user/enabled로 발견했다. 같은 CLI의 model/list에는 Astra가 없었고, 데스크톱 서브에이전트 도구는 Astra/max 지정 요청을 수락했다. 아래 CLI 예시는 인자 형식이며 이 CLI에서 Astra 모델 실행까지 검증했다는 뜻은 아니다.

## 리더 시작과 호출

데스크톱에서 현재 작업 모델을 **GPT-6 Astra**, 추론을 **xhigh / Extra High**로 선택한 다음 호출한다. 이미 올바르게 설정했다면 재설정할 필요가 없다. 스킬 자체는 실행 중 리더 설정을 변경하지 못한다.

CLI에서 새 지속 리더를 시작하려면:

```sh
codex -m gpt-6-astra -c 'model_reasoning_effort="xhigh"' \
  '$astra-orchestrator를 사용해 이 저장소의 요청된 목표를 리더·워커로 분업하고 완료까지 조정해 주세요.'
```

위 문장의 목표를 실제 업무로 구체화한다. 전역 config.toml 수정은 필요 없다. 현재 서브에이전트 도구가 정확한 모델/effort를 지정할 수 있어야 선택이 실행에 반영된다. 위 CLI 예시는 Standard 속도를 설정하는 명령이 아니다. 속도 제어·확인 가능 여부는 [세션 도구 안내](references/session-tools.md)를 따르며, Standard 지시를 충족할 수 없는 경로는 사용하지 않는다.

### 일반 기능 구현

```text
$astra-orchestrator
설정 화면의 입력 검증을 구현해 주세요.
기존 저장 형식과 공개 API를 유지하고 오류 입력·정상 저장을 검증하세요.
리더는 계획과 통합, 워커는 구현·테스트를 담당하세요.
중요한 기능 완료는 독립 reviewer가 확인하세요.
```

위 예시처럼 역할 분리·독립 검토를 명시하면 해당 요청을 따른다. 일반 호출에서는 병렬화 이익이 있을 때만 위임하며 작은 작업은 리더가 직접 완료한다. 역할별 effort와 검토 필요성은 [판단 기준](references/roles.md)을 따른다.

### Git 통합

```text
$astra-orchestrator
두 워커의 변경을 지정한 integration branch에 통합해 주세요.
각 워커의 worktree 소유권을 Git Steward에게 순서대로 넘기고,
기존 사용자 변경은 보존하세요. 이번 작업의 atomic commit은 허용하며
push는 하지 마세요. 통합 후 별도 Reviewer로 기능 완료를 검증하세요.
```

실제 integration branch와 source 작업은 입력·현재 상태에서 확인한다. Git 조사 medium, 일반 통합 high, 복잡한 충돌·history 문제 xhigh, 최종 독립 검토 max로 배정한다. Git Steward는 repository 상태를 만들고 Reviewer는 그 결과의 요구사항 충족을 확인한다. 두 역할을 같은 세션으로 합치지 않는다.

Git 규칙은 사용자 변경 보존, unrelated 변경 staging/commit 금지, 연산에 필요한 최신 전제 상태 확인, stash 기본 미사용, 단일 worktree owner, 모호한 conflict의 Leader 인계를 포함한다. 파괴적 작업·branch 삭제·공유 이력 변경은 대상과 효과에 대한 명시적 사용자 권한이 필요하며 기존 권한은 재사용한다. `push --force`는 금지하며 원격 이력 변경이 허용된 경우에만 확인된 remote SHA를 지정한 force-with-lease를 사용한다. [세부 규칙과 Git 결과](references/git-steward.md)를 따른다.

### 난제와 escalation

```text
$astra-orchestrator
작업 취소와 재시도 중 드물게 발생하는 race를 재현하고 수정해 주세요.
최소 재현과 lifetime 분석, 정상/취소/중복 호출 검증 증거를 남기세요.
```

Race는 처음부터 xhigh specialist다. 진전 없는 반복은 재현·가설·관측 결과를 다시 평가하고 전문 분석이 필요할 때 specialist에 넘긴다. 입력·기기·인증 부재는 추론을 올리는 이유가 아니다.

### 작은 기계적 작업

```text
$astra-orchestrator
설치 문서의 오래된 제품명만 새 이름으로 통일하세요.
예제 명령의 의미와 링크 대상은 유지하세요.
```

실제 위임 이익이 있으면 medium worker를 쓴다. 짧은 조정만 필요하면 리더가 처리할 수 있다. 의미 보존 편집에는 max를 자동 생성하지 않는다.

## 범위와 검증

Instructions-only 스킬이다. 별도 daemon, API key, 외부 서비스, 자동 설치 hook이 필요하지 않다. 실행 결정은 Codex가 내리며 파일만으로 모델·권한을 강제하는 runtime은 아니다. 지정값이 거부되면 실패를 알리고 조용히 fallback하지 않는다.

독립성은 새 세션, 제한된 원본 맥락, 직접 검증으로 확보한다. 같은 Astra 모델 간 검토이므로 다른 모델의 다양성을 보장하지 않는다. read-mostly도 실제 sandbox가 확인되지 않으면 행동 지침이다.

번들 skill-creator의 scripts/quick_validate.py에 이 폴더 경로를 전달하면 frontmatter·명명·미완성 scaffold를 검사할 수 있다. YAML parsing과 상대 링크 확인을 추가하고 실제 역할 선택·도구 호출 검증은 별도로 수행한다. 정책 문장 존재만으로 동작을 증명하지 않는다.

형식·설치 근거는 [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills), 모델·추론 상속은 [OpenAI Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), Astra 지원 수준은 [모델 문서](https://developers.openai.com/api/docs/models/gpt-6-astra)를 사용했다. 구체적인 역할 배분은 사용자가 정한 정책이다.

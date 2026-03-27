# `agents/openai.yaml` quick guide

공식 Codex skills 문서 기준 선택적 메타데이터 파일입니다.

## 최소 예시

```yaml
interface:
  display_name: "My Skill"
  short_description: "One-line summary"
  default_prompt: "Use this skill to ..."
policy:
  allow_implicit_invocation: true
```

## 필드 해설

### interface

- `display_name`: UI에 보일 이름
- `short_description`: 짧은 설명
- `default_prompt`: 시작 프롬프트 제안

### policy

- `allow_implicit_invocation`: `false`면 명시 호출만 허용

### dependencies

필요한 도구나 MCP가 있을 때만 적습니다.

예시:

```yaml
dependencies:
  tools:
    - type: "mcp"
      value: "openaiDeveloperDocs"
      description: "OpenAI Docs MCP server"
      transport: "streamable_http"
      url: "https://developers.openai.com/mcp"
```

## 작성 원칙

- UI 메타데이터는 SKILL.md와 의미가 어긋나지 않아야 함
- 없는 기능을 과장하지 않음
- 아이콘/브랜드 컬러는 실제 자산이 있을 때만 추가
- skill purpose가 바뀌면 함께 갱신

# Plugin installation

`GPT Pro Collaborator`와 matching read-only companion `GPT Pro MCP`, 독립적인 `Swift Intelligence`를 GitHub marketplace에서 설치할 수 있습니다. 실제 GPT Pro 상담에는 앞의 두 Plugin이 모두 필요합니다.

## Repository marketplace

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
```

Plugins 화면에서 `GPT Pro Collaborator`, `GPT Pro MCP`, `Swift Intelligence`를 설치할 수 있습니다. CLI에서는 다음과 같습니다.

```bash
codex plugin add gptpro@codex-skills
codex plugin add gptpro-mcp@codex-skills
codex plugin add swift-intelligence@codex-skills
```

Plugin 설치는 Skill을 로드하지만 현재 Plugin metadata만으로는 두 component 사이의 owner-only `.gptpro-components.json` descriptor를 생성한다는 보장이 없습니다. 따라서 실제 repository disclosure 전에 `desktop-doctor`와 component handshake가 성공하는지 확인해야 합니다. 실패하면 검토한 checkout에서 다음 atomic installer를 사용합니다.

```bash
python3 scripts/manage_skills.py install gptpro --update
```

이 명령은 companion을 먼저 설치하고 exact entrypoint/tree hash descriptor를 기록합니다.

Swift Intelligence는 macOS, Command Line Tools를 포함한 Xcode, Python 3가 필요합니다. Xcode에 포함된 `sourcekit-lsp`를 실행하며 외부 MCP 바이너리나 Python 패키지를 설치하지 않습니다. 설치 후 Codex를 다시 시작하고 새 작업을 열어 Skill과 MCP 도구를 로드하십시오.

## GitHub Skill installer

`$skill-installer`로 standalone 디렉터리를 내려받을 수도 있지만 base 하나만 설치하면 operational Desktop workflow가 완성되지 않습니다.

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
$skill-installer Install gptpro-mcp from https://github.com/oozoofrog/codex-skills/tree/main/gptpro-mcp
```

두 Skill이 있어도 descriptor가 없으면 fail closed합니다. 공개 전송이나 Tunnel activation을 시도하지 말고 repository installer로 결속을 완성합니다.

## What is not installed automatically

- OpenAI `tunnel-client`
- ChatGPT account login
- ChatGPT Developer Mode/App authorization
- macOS Screen Recording/Accessibility permissions
- private app ID or Tunnel credentials

이 값들은 사용자 소유 private state에만 둡니다. 저장소, Plugin manifest, package receipt에는 raw app ID, Tunnel ID, API key를 넣지 않습니다.

첫 사용은 [한국어 사용자 매뉴얼](../gptpro/references/user-manual.md), 설치 전환은 [standalone installation](selective-installation.md)을 참고하세요.

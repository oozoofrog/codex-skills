# GPT Pro Plugin installation

`gptpro` supports network installation without asking the user to run a Python script.

## Install from Codex without a terminal

Ask Codex to use its bundled installer:

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

The installer downloads only the selected Skill into the Codex skills directory. Start a new Codex task after installation so discovery uses the new package.

설치 후 첫 상담을 시작하는 방법과 승인·브라우저·`.gptpro/` 관리가 궁금하면 [`gptpro` 한국어 사용자 매뉴얼](../gptpro/references/user-manual.md)을 참고하세요.

## Install from the repository marketplace

Until the Plugin is published in the universal Plugins Directory, register this GitHub marketplace once:

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
```

Then open the Plugins browser, select the `GPT Pro` marketplace, and install `GPT Pro Collaborator`. In Codex CLI, `/plugins` opens the same marketplace browser.

For a CLI-only installation after registration:

```bash
codex plugin add gptpro@codex-skills
```

The marketplace entry resolves `./plugins/gptpro`; its manifest loads the mirrored Skill from `./skills/gptpro/`. No Python installation command is involved.

The Skill package does not bundle or install OpenAI `tunnel-client`. Its experimental Web MCP runtime currently requires macOS plus Python 3.11 or newer and has a separate attended setup: the user obtains or builds the client through the reviewed official `openai/tunnel-client` path and owns Tunnel/key, Developer Mode, and ChatGPT app/workspace authorization. A no-secret probe reports the exact binary path/hash; key-bearing init/activation require both values, but that drift check is not publisher provenance or signature verification. The Skill supervises the documented foreground client flow and requires a successful control-plane poll, while local runtime tests still do not prove logged-in ChatGPT account E2E. Read the installed Skill's `references/web-mcp.md` before using this path.

## Public click installation

After the skills-only Plugin passes OpenAI review and is published, users can find it in the universal Plugins Directory and install it with the plus button. Public publication is a separate release gate; the presence of this repository package does not imply that review or publication has completed.

## Maintainer checkout workflow

`scripts/manage_skills.py` remains available for repository maintainers, offline checkouts, and atomic updates of an existing standalone installation. It is a compatibility path, not the recommended first-install experience.

# GPT Pro Plugin installation

`gptpro` supports network installation without asking the user to run a Python script.

## Install from Codex without a terminal

Ask Codex to use its bundled installer:

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

The installer downloads only the selected Skill into the Codex skills directory. Start a new Codex task after installation so discovery uses the new package.

## Install from the repository marketplace

Until the Plugin is published in the universal Plugins Directory, register this GitHub marketplace once:

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
```

Then open the Plugins browser, select the `Codex Skills` marketplace, and install `GPT Pro Collaborator`. In Codex CLI, `/plugins` opens the same marketplace browser.

For a CLI-only installation after registration:

```bash
codex plugin add gptpro@codex-skills
```

The marketplace entry resolves `./plugins/gptpro`; its manifest loads the mirrored Skill from `./skills/gptpro/`. No Python installation command is involved.

The Skill package does not bundle or install OpenAI `tunnel-client`. The experimental Web MCP path has a separate, attended external setup and is not operational in a foundation-only release; see the installed Skill's `references/web-mcp.md` before treating it as available.

## Public click installation

After the skills-only Plugin passes OpenAI review and is published, users can find it in the universal Plugins Directory and install it with the plus button. Public publication is a separate release gate; the presence of this repository package does not imply that review or publication has completed.

## Maintainer checkout workflow

`scripts/manage_skills.py` remains available for repository maintainers, offline checkouts, and atomic updates of an existing standalone installation. It is a compatibility path, not the recommended first-install experience.

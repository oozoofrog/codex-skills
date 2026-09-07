# Guided setup

Read this on first use or when environment checks fail. This is the setup procedure for local Codex to carry out with the existing CLI; it adds no installer, CLI command, or persistent setup record. It does not give ChatGPT Pro shell, file-write, or other local tool access. Keep the existing explicit `$gptpro` invocation policy and consultation modes.

## Explain, choose, execute

At each stage, briefly explain its purpose, ask only for a decision that is still needed, execute the authorized action, and report the observed result in the user's language. Read-only checks need no separate approval. Reuse authorization and choices already given for this task; do not ask again before each command in a chosen installation. A pending choice is not permission to perform the dependent action. Continue independent checks and, when a consultation was requested, file-scope discovery while waiting.

Example Launcher choice:

> 다음에도 상담용 ChatGPT를 쉽게 열 수 있도록 실행기를 설치할 수 있습니다. 설치 위치는 `~/Applications/gptpro Launcher.app`입니다. 실행기를 설치하거나, 이번에는 설치 없이 실행할 수 있습니다.

Setup authorization covers only the explained local changes. It does not authorize code disclosure, a trial prompt, paid subscription changes, or a new model. Preserve a valid exact-package approval or matching bounded standing approval for the later consultation without redundant confirmation.

## 1. Inspect prerequisites before using Python

Use shell/system inspection to check macOS, `/Applications/ChatGPT.app`, and the paths and versions of Python and Node. For example, `uname -s`, `command -v python3`, and `command -v node` do not depend on the gptpro CLI; run version checks only for binaries found. Requirements are Python 3.11+, Node.js 22+, the macOS ChatGPT app, and an account able to use the required Pro model. Do not infer login or model access from an installed app.

Do not run the Python CLI to discover that Python is missing. Reuse compatible existing binaries; discover existing runtime-manager configuration when the default binary is too old or absent. Use the verified Python executable for subsequent commands. If a runtime needs activation, ensure Node is visible to that Python process through a command-scoped environment. Do not silently change global defaults or shell startup files. The command examples elsewhere assume `python3` and `node` already resolve to compatible versions.

Summarize each prerequisite as ready or needing action. If macOS is unavailable, explain that this runtime requires macOS and stop dependent setup; do not propose another delivery channel. Fully ready environments go straight to connection and model verification without installation or Launcher questions.

## 2. Resolve only missing prerequisites

Inspect already-installed package/runtime managers and their existing ownership of the relevant runtime. Prefer the manager already responsible for it. If no ownership is established and several suitable managers exist, explain the alternatives and let the user choose. Resolve an existing usable installation before proposing another copy.

Before installation, use the installed tool's help or its official documentation to verify the package, supported version, and command. Present the exact missing item, why it is needed, command, destination, and relevant effects such as dependencies or an existing-runtime update. After the user selects installation, execute that concrete plan and verify the resulting path and version. Do not bundle unrelated upgrades, remove conflicting installations, or install a package manager as part of this flow.

Use only an existing suitable manager for automated prerequisite installation, including ChatGPT when supported. If no suitable manager exists, or the user chooses manual installation, provide current official installation instructions and the required destination/version. Ask the user to finish that step, then inspect the result. Do not claim installation completed from instructions alone. If the user declines installation entirely, explain which dependent work is pending and retain the original request for resumption.

## 3. Prepare the Runner

Once prerequisites are usable, inspect `launcher-status` and verify an existing Runner with `desktop-doctor`. If connection verification already passes, continue to model verification without offering an unnecessary installation. A missing Launcher does not make a working Runner incomplete.

If a Runner needs to be started and the Launcher is absent, explain its convenience and offer **Launcher installation** or **run without installation**, unless the user already chose. Run `launcher-install` only for the chosen installation and verify its status. If a Launcher is already current, reuse it without asking again. If it is stale or conflicts with an unrelated item, explain the observation and use the existing status/error guidance; do not overwrite or delete an unrelated item. Running without the Launcher remains available.

Explain that `desktop-launch` starts a second ChatGPT process using the gptpro profile and loopback port 9223. The ordinary app can remain open. The Launcher is named gptpro Launcher, but the running Runner still appears as ChatGPT in the Dock, Cmd-Tab, menu, and default window. Start a missing Runner with `desktop-launch`; do not launch another copy when it is already starting or running. Check readiness after startup or after a relevant user action rather than repeatedly polling an unchanged failure.

Login belongs to the user in the Runner window. Explain that this separate profile does not copy the ordinary app's login and may require a first login. Never request credentials in the conversation or read/copy cookies, tokens, passwords, MFA, or Keychain data. Wait for the user's completion before retrying the dependent authentication check.

## 4. Verify and return to the request

Run `desktop-doctor` and `models` with the prepared environment. Require the exact approved model, default `gpt-5-6-pro`. Report **상담 준비 완료** only when both connection and exact-model availability are verified. This does not prove a successful consultation, stream capture, or evaluation.

If the model is absent, report that observation without guessing the account's subscription status. Offer to resolve access/login or let the user choose another exact available model for a newly prepared and approved package. Do not change models automatically or purchase/modify a subscription. A port conflict or bridge incompatibility is a specific setup failure, not a reason to reinstall everything, terminate another process, expose a different port, or switch transport.

When setup was the only request, end here without preparing or sending a trial consultation. Otherwise return to the original plan, ask, review, debug, or architecture task: select files, prepare the package, verify disclosure, and apply the existing approval rules. No setup test message is required.

## Resume and report failures

On resumption, inspect current state and reuse choices available in the conversation. Continue only the incomplete stages; do not add a persistent preference file or infer a past choice that is unavailable. A missing Launcher alone is not a reason to repeat an earlier declined offer. Ask only if an unresolved choice changes the remaining work.

For setup failures, lead with the failed prerequisite/action, its effect on the request, and one concrete next step. Include the applicable observed command and sanitized error under [failure reporting](failure-reporting.md); do not fabricate an error code for a shell observation. Separate local installation effects from package or transmission state. An existing uncertain submission remains governed by GET-only recovery; restarting setup never permits resending it.

After an installation or relevant state change, rerun the affected check and remaining dependent checks. Do not repeat successful unrelated checks. Report the Runner's observed state at completion or pause and never stop either ChatGPT process automatically.

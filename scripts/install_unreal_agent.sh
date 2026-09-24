#!/usr/bin/env bash
# Installs the pinned runner and only the named Codex Plugin.
set -euo pipefail

version=v0.2.0
commit=1b9f778453f411c029b39b85102aaefb95e7e48d
url=https://github.com/unreallabsai/unreal-agent.git
bin_dir=${UNREAL_AGENT_BIN_DIR:-"$HOME/.local/bin"}
name=unreal-agent-runner
target=$bin_dir/$name
marker=$bin_dir/.$name.install

fail() { printf 'unreal-agent installer: %s\n' "$*" >&2; exit 1; }
checksum() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d ' ' -f 1
  else sha256sum "$1" | cut -d ' ' -f 1; fi
}
read_plugin_state() {
  python3 -c '
import json, sys
try:
    entries = [p for p in json.load(sys.stdin)["installed"] if p["pluginId"] == "unreal-agent@codex-skills"]
    if len(entries) > 1: raise ValueError("duplicate named plugin entries")
    if not entries: print("absent")
    elif entries[0]["installed"] is True:
        print("enabled" if entries[0]["enabled"] is True else "disabled")
    elif entries[0]["installed"] is False: print("absent")
    else: raise ValueError("unknown installed flag")
except Exception as exc:
    print(f"cannot parse plugin inventory: {exc}", file=sys.stderr); sys.exit(2)
'
}
[[ $# == 0 || ( $# == 1 && ( $1 == --reinstall || $1 == --runner-only ) ) ]] || fail "usage: bash install_unreal_agent.sh [--reinstall|--runner-only]"
reinstall=${1:-}
umask 077
plugin_state=
market_state=
if [[ $reinstall != --runner-only ]]; then
  for cmd in codex python3; do command -v "$cmd" >/dev/null 2>&1 || fail "missing $cmd (use --runner-only to skip Codex)"; done
  # Inspect BOTH inventories before making any changes, even to the runner.
  marketplaces=$(codex plugin marketplace list --json) || fail 'cannot inspect Codex marketplaces'
  plugins=$(codex plugin list --json) || fail 'cannot inspect installed Codex plugins'
  market_state=$(printf '%s' "$marketplaces" | python3 -c '
import json, subprocess, sys
try:
    items = json.load(sys.stdin)["marketplaces"]
    hits = [m for m in items if m["name"] == "codex-skills"]
    if not hits:
        print("absent"); sys.exit(0)
    if len(hits) != 1:
        raise ValueError("duplicate codex-skills marketplaces")
    source = hits[0]["marketplaceSource"]
    kind, value = source["sourceType"], source["source"]
    def canonical(url):
        return url.rstrip("/").removesuffix(".git").lower() in (
            "https://github.com/oozoofrog/codex-skills",
            "git@github.com:oozoofrog/codex-skills")
    if kind == "git" and canonical(value):
        print("remote")
    elif kind == "local" and value.startswith("/"):
        from pathlib import Path
        root = Path(value)
        manifest = json.loads((root / ".agents/plugins/marketplace.json").read_text())
        origin = subprocess.check_output(["git", "-C", str(root), "remote", "get-url", "origin"], text=True).strip()
        print("local" if manifest.get("name") == "codex-skills" and canonical(origin) else "conflict")
    else:
        print("conflict")
except Exception as exc:
    print(f"cannot verify marketplace source: {exc}", file=sys.stderr)
    sys.exit(2)
') || fail 'invalid marketplace inventory or unverifiable source'
  [[ $market_state != conflict ]] || fail 'codex-skills marketplace has a different source; leaving registration and plugin untouched'
  plugin_state=$(printf '%s' "$plugins" | read_plugin_state) || fail 'invalid Codex plugin inventory'
  [[ $market_state != absent || $plugin_state == absent ]] || fail 'plugin installed but marketplace missing; inspect Codex state manually'
fi
install_plugin() {
  [[ $reinstall != --runner-only ]] || return 0
  if [[ $market_state == absent || $plugin_state == absent ]]; then
    codex_home=${CODEX_HOME:-"$HOME/.codex"}
    [[ ! -L $codex_home && ! -L $codex_home/config.toml ]] || fail 'Codex config path is a symlink; cannot safely back up'
    [[ ! -e $codex_home || -d $codex_home ]] || fail "invalid Codex home"
    [[ ! -L $codex_home/backups ]] || fail "Codex backup path is a symlink"
    mkdir -p "$codex_home/backups"
    backup=$(mktemp -d "$codex_home/backups/unreal-agent-install.XXXXXX")
    printf '%s\n' "$marketplaces" > "$backup/marketplaces-before.json"
    printf '%s\n' "$plugins" > "$backup/plugins-before.json"
    if [[ -f $codex_home/config.toml ]]; then cp -p "$codex_home/config.toml" "$backup/config.toml"; fi
    printf 'Codex pre-change config and inventories backed up at %s\n' "$backup"
    if [[ $market_state == absent ]]; then
      codex plugin marketplace add oozoofrog/codex-skills --ref main || fail 'marketplace add failed; backup retained'
    elif [[ $market_state == remote && $plugin_state == absent ]]; then
      codex plugin marketplace upgrade codex-skills || fail 'marketplace upgrade failed; backup retained'
    fi
    if [[ $plugin_state == absent ]]; then
      codex plugin add unreal-agent@codex-skills || fail 'plugin add failed; backup retained; inspect marketplace before retry'
      updated_plugins=$(codex plugin list --json) || fail 'cannot verify installed Plugin; backup retained'
      updated_state=$(printf '%s' "$updated_plugins" | read_plugin_state) || fail 'cannot verify installed Plugin; backup retained'
      [[ $updated_state == enabled ]] || fail "Plugin was not enabled after install ($updated_state); backup retained"
    fi
  fi
  if [[ $plugin_state == disabled ]]; then
    printf 'Plugin already installed but disabled; preserving disabled state. Enable it manually in Codex if desired.\n'
  else
    printf 'Plugin unreal-agent@codex-skills installed/enabled (verify in a new Codex session).\n'
  fi
  printf 'Provider credentials and model availability are not configured by this installer.\n'
}
# Never follow a symlink at the installation boundary.
[[ -n $bin_dir && $bin_dir != / ]] || fail 'invalid binary directory'
[[ ! -L $bin_dir && ! -L $target && ! -L $marker ]] || fail 'symlink at installation path'
[[ ! -e $bin_dir || -d $bin_dir ]] || fail 'binary directory is not a directory'
if [[ -e $target || -e $marker ]]; then
  [[ -f $target && -f $marker ]] || fail "unmanaged or incomplete install at $target; leaving it untouched"
  expected=$(printf '%s\n' "$commit $(checksum "$target")")
  [[ $(cat "$marker") == "$expected" ]] || fail "unmanaged/modified binary at $target; leaving it untouched"
  if [[ $reinstall != --reinstall ]]; then
    printf 'Managed runner %s already installed at %s.\n' "$version" "$target"
    install_plugin
    exit 0
  fi
fi
for cmd in git go mktemp cut; do command -v "$cmd" >/dev/null 2>&1 || fail "missing $cmd"; done
command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 || fail 'missing SHA-256 utility'
go_version=$(go env GOVERSION)
[[ $go_version =~ ^go([0-9]+)\.([0-9]+)(\.([0-9]+))? ]] || fail "cannot parse Go version: $go_version"
if (( BASH_REMATCH[1] < 1 || (BASH_REMATCH[1] == 1 && BASH_REMATCH[2] < 27) )); then
  fail 'Go >= 1.27.0 required by upstream v0.2.0; install Go 1.27+ first'
fi
work=$(mktemp -d)
backup_binary=
backup_marker=
backup_dir=
staged=
lock=
published=
cleanup() {
  status=$?
  if [[ $status != 0 && -n $published ]]; then rm -f "$target" "$marker"; fi
  if [[ -n $backup_binary && -e $backup_binary ]]; then
    if ! mv -f "$backup_binary" "$target"; then printf 'RESTORE FAILED: binary retained at %s\n' "$backup_binary" >&2; fi
  fi
  if [[ -n $backup_marker && -e $backup_marker ]]; then
    if ! mv -f "$backup_marker" "$marker"; then printf 'RESTORE FAILED: marker retained at %s\n' "$backup_marker" >&2; fi
  fi
  [[ -z $staged ]] || rm -f "$staged" "$staged.install"
  [[ -z $backup_dir ]] || rmdir "$backup_dir" 2>/dev/null || true
  [[ -z $lock ]] || rmdir "$lock" 2>/dev/null || true
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT
# Fetch only the pinned tag, then verify the peeled commit (not just the tag name).
git init -q "$work/source"
git -C "$work/source" remote add origin "$url"
git -C "$work/source" fetch -q --depth 1 origin "refs/tags/$version"
actual=$(git -C "$work/source" rev-parse FETCH_HEAD^{commit})
[[ $actual == "$commit" ]] || fail "upstream tag $version changed ($actual); refusing to build"
( cd "$work/source" && git checkout -q --detach "$commit" && go build -o "$work/runner" ./cmd/unreal-agent-runner )
[[ -f $work/runner && -s $work/runner ]] || fail 'build did not produce a runner'
# A Codex CLI failure must leave the existing runner untouched. The binary is
# published only after the named Plugin step succeeds.
install_plugin
# Build succeeds before creating any installation paths.
mkdir -p "$bin_dir"
[[ ! -L $bin_dir ]] || fail "binary directory became a symlink"
lock_path="$bin_dir/.$name.lock"
mkdir "$lock_path" || fail "another install is in progress (or stale lock at $lock_path)"
lock="$lock_path"
if [[ -e $target || -e $marker || -L $target || -L $marker ]]; then
  [[ $reinstall == --reinstall && ! -L $target && ! -L $marker && -f $target && -f $marker ]] || fail "installation path changed or unmanaged; refusing to replace it"
  [[ $(cat "$marker") == "$commit $(checksum "$target")" ]] || fail "managed binary changed during build"
fi
staged=$(mktemp "$bin_dir/.$name.XXXXXX")
cp "$work/runner" "$staged"
chmod 755 "$staged"
printf '%s %s\n' "$commit" "$(checksum "$staged")" > "$staged.install"
# In case of a failed publish, retain the previous managed installation.
if [[ -e $target ]]; then
  backup_dir=$(mktemp -d "$bin_dir/.$name.backup.XXXXXX")
  mv "$target" "$backup_dir/runner"
  backup_binary=$backup_dir/runner
  mv "$marker" "$backup_dir/marker"
  backup_marker=$backup_dir/marker
fi
mv "$staged" "$target" || fail 'could not publish runner'
published=1
mv "$staged.install" "$marker" || fail 'could not publish marker'
staged=
backup_binary=
backup_marker=
if [[ -n $backup_dir ]]; then
  printf 'Previous managed runner retained at %s\n' "$backup_dir"
fi
backup_dir=
printf 'Installed upstream runner %s (%s) at %s\n' "$version" "$commit" "$target"
case :$PATH: in *:"$bin_dir":*) ;; *) printf 'Add %s to PATH to invoke %s.\n' "$bin_dir" "$name";; esac

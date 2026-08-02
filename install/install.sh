#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT=""
HERMES_HOME_VALUE="${HERMES_HOME:-$HOME/.hermes}"
CODEX_HOME_VALUE="${CODEX_HOME:-$HOME/.codex}"
BIN_DIR_VALUE="${XDG_BIN_HOME:-$HOME/.local/bin}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  bash install/install.sh --client hermes|codex|both [options]

Options:
  --client VALUE       Install the Hermes skill, Codex skill, or both.
  --hermes-home PATH   Hermes home directory. Default: $HERMES_HOME or ~/.hermes
  --codex-home PATH    Codex home directory. Default: $CODEX_HOME or ~/.codex
  --bin-dir PATH       Directory for the caller-neutral CLI. Default: $XDG_BIN_HOME or ~/.local/bin
  --dry-run            Print the planned writes without changing the filesystem.
  -h, --help           Show this help.

The installer never rewrites the consultation engine or bakes caller-specific
paths into a SKILL.md. Both callers use the same engine and state contracts.
EOF
}

while (($#)); do
  case "$1" in
    --client)
      [[ $# -ge 2 ]] || { echo "error: --client requires a value" >&2; exit 2; }
      CLIENT="$2"
      shift 2
      ;;
    --hermes-home)
      [[ $# -ge 2 ]] || { echo "error: --hermes-home requires a path" >&2; exit 2; }
      HERMES_HOME_VALUE="$2"
      shift 2
      ;;
    --codex-home)
      [[ $# -ge 2 ]] || { echo "error: --codex-home requires a path" >&2; exit 2; }
      CODEX_HOME_VALUE="$2"
      shift 2
      ;;
    --bin-dir)
      [[ $# -ge 2 ]] || { echo "error: --bin-dir requires a path" >&2; exit 2; }
      BIN_DIR_VALUE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$CLIENT" in
  hermes|codex|both) ;;
  "")
    echo "error: --client is required" >&2
    usage >&2
    exit 2
    ;;
  *)
    echo "error: --client must be hermes, codex, or both" >&2
    exit 2
    ;;
esac

require_source() {
  [[ -e "$1" ]] || { echo "error: missing source file: $1" >&2; exit 3; }
}

print_command() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
}

run() {
  if ((DRY_RUN)); then
    print_command "$@"
  else
    "$@"
  fi
}

install_regular_file() {
  local source="$1"
  local target="$2"
  local mode="${3:-0644}"
  require_source "$source"
  run mkdir -p "$(dirname -- "$target")"
  run install -m "$mode" "$source" "$target"
}

copy_directory() {
  local source="$1"
  local target="$2"
  require_source "$source"
  run mkdir -p "$target"
  if ((DRY_RUN)); then
    print_command cp -a "$source/." "$target/"
  else
    cp -a "$source/." "$target/"
  fi
}

install_cli() {
  install_regular_file \
    "$REPO_ROOT/scripts/codex_senior_consult.py" \
    "$BIN_DIR_VALUE/codex-senior-consult" \
    0755
}

install_codex_skill() {
  local target="$CODEX_HOME_VALUE/skills/codex-senior-consult"
  install_regular_file "$REPO_ROOT/SKILL.md" "$target/SKILL.md"
  copy_directory "$REPO_ROOT/agents" "$target/agents"
  copy_directory "$REPO_ROOT/references" "$target/references"
  copy_directory "$REPO_ROOT/scripts" "$target/scripts"
  if [[ -f "$REPO_ROOT/tests/pressure-baseline.md" ]]; then
    install_regular_file "$REPO_ROOT/tests/pressure-baseline.md" "$target/tests/pressure-baseline.md"
  fi
}

install_hermes_skill() {
  local target="$HERMES_HOME_VALUE/skills/codex-senior-consult"
  install_regular_file "$REPO_ROOT/integrations/hermes/SKILL.md" "$target/SKILL.md"
  copy_directory "$REPO_ROOT/references" "$target/references"
  copy_directory "$REPO_ROOT/scripts" "$target/scripts"
  if [[ -f "$REPO_ROOT/integrations/hermes/verification-prompt.md" ]]; then
    install_regular_file \
      "$REPO_ROOT/integrations/hermes/verification-prompt.md" \
      "$target/references/verification-prompt.md"
  fi
}

command -v python3 >/dev/null 2>&1 || {
  echo "error: python3 is required" >&2
  exit 4
}

install_cli
case "$CLIENT" in
  hermes)
    install_hermes_skill
    ;;
  codex)
    install_codex_skill
    ;;
  both)
    install_codex_skill
    install_hermes_skill
    ;;
esac

if ((DRY_RUN == 0)); then
  "$BIN_DIR_VALUE/codex-senior-consult" --help >/dev/null
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "warning: Codex CLI was not found in PATH; installation succeeded, but consultations cannot run yet." >&2
fi

cat <<EOF
Installed codex-senior-consult for: $CLIENT
CLI: $BIN_DIR_VALUE/codex-senior-consult
Hermes skill root: $HERMES_HOME_VALUE/skills/codex-senior-consult
Codex skill root: $CODEX_HOME_VALUE/skills/codex-senior-consult

Start a fresh caller session after installation so its skill index is rebuilt.
EOF

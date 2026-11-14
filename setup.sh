#!/usr/bin/env bash
# Part 1 of setup: tools, Python environment, folders and starter files.
# Safe to re-run: it never overwrites a file you already have.
# Part 2 is the interview: open Claude Code in this folder and run /setup.
#
#   ./setup.sh            full setup
#   ./setup.sh --doctor   only run the health check
#   ./setup.sh --no-venv  skip creating .venv (resume tools then need packages installed another way)

set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

DO_VENV=1
for arg in "$@"; do
  case "$arg" in
    --doctor) exec python3 scripts/doctor.py ;;
    --no-venv) DO_VENV=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

step "1. Tools"
command -v python3 >/dev/null || fail "python3 not found. Install Python 3.9+ (https://www.python.org or 'brew install python')."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || fail "python3 is $(python3 -V 2>&1); the kit needs 3.9 or newer."
ok "$(python3 -V 2>&1)"
command -v git >/dev/null && ok "git" || fail "git not found. Install it (macOS: xcode-select --install)."
command -v gh >/dev/null && ok "gh (GitHub CLI)" || warn "gh not found: optional, used to check your repo is private ('brew install gh')."
command -v claude >/dev/null && ok "claude (Claude Code CLI)" || warn "claude CLI not found: fine if you use the Claude desktop app."
for t in tectonic pdftotext; do
  command -v "$t" >/dev/null && ok "$t" || warn "$t not found: needed only for PDF resumes ('brew install tectonic poppler')."
done

step "2. Python environment (.venv)"
if [ "$DO_VENV" = 1 ]; then
  [ -d .venv ] || python3 -m venv .venv
  if .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt; then
    ok ".venv ready ($(.venv/bin/python -V 2>&1)), packages from requirements.txt installed"
  else
    warn "pip install failed (offline?). Re-run ./setup.sh later; only resume building needs these packages."
  fi
else
  warn "skipped (--no-venv)"
fi

step "3. Folders"
for d in profile memory applications/_forms batches resumes/base resumes/tailored resumes/archive \
         tracker reviews followups interview-prep; do
  mkdir -p "$d"
  [ -n "$(ls -A "$d" 2>/dev/null)" ] || touch "$d/.gitkeep"
done
[ -f applications/_events.jsonl ] || : > applications/_events.jsonl
ok "data folders exist"

step "4. Starter files (existing files are kept)"
copy_new() {  # copy_new <src> <dest>
  if [ -e "$2" ]; then echo "    kept    $2"; else cp "$1" "$2"; echo "    created $2"; fi
}
for f in templates/profile/*.md templates/profile/*.txt; do
  [ -e "$f" ] && copy_new "$f" "profile/$(basename "$f")"
done
for f in templates/memory/*.md; do
  [ -e "$f" ] && copy_new "$f" "memory/$(basename "$f")"
done
copy_new templates/soul.md soul.md
chmod +x scripts/*.sh 2>/dev/null || true

step "5. Git"
if [ -d .git ]; then
  ok "already a git repo"
else
  git init -q && ok "initialised a git repo (nothing committed yet)"
fi
warn "this folder will hold your contact details and answers: keep any GitHub copy PRIVATE."

step "6. Health check"
python3 scripts/doctor.py || true

cat <<'EOF'

Next:
  1. Open Claude Code in this folder (desktop app: choose this folder; terminal: `claude` here).
  2. Run /setup (about 25 minutes). Claude reads your CV, then asks the questions most application forms
     ask (voluntary self-ID, work authorization, screening, pay), your work types, job portals and targets.
     "Decline" or "ask me each time" are always fine. It writes config/profile.json, your profile files,
     soul.md and your tracker sheet.
  3. Run ./setup.sh --doctor until it shows no ✗, then /search-jobs.
EOF

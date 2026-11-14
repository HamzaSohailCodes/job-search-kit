#!/bin/sh
# Pin the exact resume that went out: prints its sha256 and keeps a dated copy in resumes/archive/
# Usage: scripts/pin_resume.sh resumes/base/<file>.pdf  -> prints "<sha256> <archive path>"
# The archive lives under $JOB_KIT_DATA if set (tests), else the repo root. Same file twice -> same archive path.
set -e
R="$(cd "$(dirname "$0")/.." && pwd)"
D="${JOB_KIT_DATA:-$R}"
f="$1"
[ -n "$f" ] || { echo "usage: $0 <resume file>" >&2; exit 2; }
[ -f "$f" ] || f="$D/$1"
[ -f "$f" ] || f="$R/$1"
[ -f "$f" ] || { echo "pin_resume: no such file: $1" >&2; exit 1; }
if command -v shasum >/dev/null 2>&1; then
  h=$(shasum -a 256 "$f" | cut -c1-64)
else
  h=$(sha256sum "$f" | cut -c1-64)
fi
A="$D/resumes/archive"
mkdir -p "$A"
b=$(basename "$f"); n="${b%.*}"; e="${b##*.}"
h8=$(printf %s "$h" | cut -c1-8)
if grep -q "^$h " "$A/.index" 2>/dev/null; then
  dest="$D/$(grep "^$h " "$A/.index" | head -1 | cut -d' ' -f2-)"
else
  dest="$A/${n}_$(date +%F)_${h8}.$e"
  cp "$f" "$dest"; echo "$h ${dest#$D/}" >> "$A/.index"
fi
echo "$h ${dest#$D/}"

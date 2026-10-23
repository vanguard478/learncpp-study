#!/usr/bin/env bash
# Mirror the learncpp.com lessons with HTTrack.
#
# Only the table-of-contents page, the lesson pages under /cpp-tutorial/ and the
# site's own images/CSS/fonts are fetched. Comments pages, feeds, avatars, ads
# and everything off-site are filtered out. Run scripts/clean.py afterwards to
# strip the page chrome (header, sidebar, prev/next buttons, comments).
#
# Usage: scripts/mirror.sh [output-dir]      (default: ./mirror)
# Re-running in the same directory updates the existing mirror.

set -euo pipefail

OUT="${1:-mirror}"
UA="Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

if ! command -v httrack >/dev/null 2>&1; then
    echo "httrack not found. Install it first, e.g.:" >&2
    echo "  Debian/Ubuntu: sudo apt install httrack" >&2
    echo "  Fedora:        sudo dnf install httrack" >&2
    echo "  Arch:          sudo pacman -S httrack" >&2
    exit 1
fi

mkdir -p "$OUT"

if [[ -f "$OUT/hts-cache/new.zip" || -f "$OUT/hts-cache/new.ndx" ]]; then
    mode=(--update)
    echo "Existing mirror found in $OUT, updating it."
else
    mode=()
fi

# Filters: later rules win, so start by excluding everything, then allow
# what we want, then carve out the junk inside the allowed areas.
httrack "https://www.learncpp.com/" \
    "${mode[@]}" \
    -O "$OUT" \
    -F "$UA" \
    -r6 \
    -c2 -%c2 -A200000 \
    -%v \
    '-*' \
    '+www.learncpp.com/' \
    '+www.learncpp.com/cpp-tutorial/*' \
    '+www.learncpp.com/*.css' '+www.learncpp.com/*.css?*' \
    '+www.learncpp.com/*.png' '+www.learncpp.com/*.jpg' '+www.learncpp.com/*.jpeg' \
    '+www.learncpp.com/*.gif' '+www.learncpp.com/*.svg' '+www.learncpp.com/*.webp' \
    '+www.learncpp.com/*.woff' '+www.learncpp.com/*.woff2' '+www.learncpp.com/*.ttf' \
    '-*/feed/*' '-*/amp/*' '-*/comment-page-*' '-*/trackback/*' \
    '-*replytocom=*' '-*?share=*' '-*wpdiscuz*' '-*/wp-json/*' '-*xmlrpc*'

cat <<EOF

Mirror done: $OUT/www.learncpp.com/
Next: python3 scripts/clean.py --mirror "$OUT" --out offline
EOF

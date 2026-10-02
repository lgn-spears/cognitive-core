#!/usr/bin/env bash
# Repos with commits and no git remote at all: work that exists in exactly one place.
set -u
. "${CORE_AUDITS_LIB:-$(dirname "$0")/lib.sh}"

repos=0
commits=0
oldest=""
while IFS= read -r repo; do
  [ -n "$repo" ] || continue
  [ -z "$(git -C "$repo" remote 2>/dev/null)" ] || continue
  n="$(git -C "$repo" rev-list --all --count 2>/dev/null)" || continue
  [ "${n:-0}" -gt 0 ] || continue
  first="$(git -C "$repo" log --all --reverse --format=%ct 2>/dev/null | head -1)"
  repos=$((repos + 1))
  commits=$((commits + n))
  if [ -z "$oldest" ] || [ "$first" -lt "$oldest" ]; then oldest="$first"; fi
done <<EOF
$(list_repos)
EOF

blocked="$(unreadable_dirs)"
if [ -n "$blocked" ]; then
  nb=$(printf '%s\n' "$blocked" | wc -l | tr -d ' ')
  printf "Couldn't look inside %s %s from here: %s.\n" "$nb" "$(plural "$nb" folder)" \
    "$(printf '%s\n' "$blocked" | paste -sd, - | sed 's/,/, /g')"
fi

[ "$repos" -gt 0 ] || exit 0

detail="Oldest commit is $(old "$oldest")."
if command -v tmutil >/dev/null 2>&1 && tmutil destinationinfo 2>&1 | grep -q "No destinations configured"; then
  detail="$detail This machine has no backup destination configured."
fi
printf '%s %s in %s %s %s no git remote at all.\t%s\n' \
  "$commits" "$(plural "$commits" commit)" \
  "$repos" "$(plural "$repos" repo)" "$(plural "$repos" has have)" \
  "$detail"

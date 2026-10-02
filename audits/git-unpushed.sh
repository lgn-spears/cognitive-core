#!/usr/bin/env bash
# Repos that have a remote but hold commits no remote branch contains.
set -u
. "${CORE_AUDITS_LIB:-$(dirname "$0")/lib.sh}"

SHOW=5
rows=""
while IFS= read -r repo; do
  [ -n "$repo" ] || continue
  [ -n "$(git -C "$repo" remote 2>/dev/null)" ] || continue
  n="$(git -C "$repo" rev-list HEAD --branches --not --remotes --count 2>/dev/null)" || continue
  [ "${n:-0}" -gt 0 ] || continue
  first="$(git -C "$repo" log HEAD --branches --not --remotes --reverse --format=%ct 2>/dev/null | head -1)"
  rows="${rows}${n}	${first}	$(basename "$repo")
"
done <<EOF
$(unique_repos)
EOF

[ -n "$rows" ] || exit 0

shown=0
rest_repos=0
rest_commits=0
while IFS='	' read -r n first name; do
  [ -n "$n" ] || continue
  if [ "$shown" -lt "$SHOW" ]; then
    printf '%s unpushed %s in %s.\tOldest is %s.\n' "$n" "$(plural "$n" commit)" "$name" "$(old "$first")"
    shown=$((shown + 1))
  else
    rest_repos=$((rest_repos + 1))
    rest_commits=$((rest_commits + n))
  fi
done <<EOF
$(printf '%s' "$rows" | sort -t '	' -k1,1 -rn)
EOF

if [ "$rest_repos" -gt 0 ]; then
  printf '%s more %s unpushed work (%s %s).\n' \
    "$rest_repos" "$(plural "$rest_repos" "repo has" "repos have")" \
    "$rest_commits" "$(plural "$rest_commits" commit)"
fi

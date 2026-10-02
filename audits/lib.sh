# Shared helpers for core audits. Sourced, never executed.
# Contract: audits are read-only. Nothing here writes anywhere.
# Must stay compatible with macOS /bin/bash 3.2.

conf_values() {  # conf_values KEY -> each value on its own line
  local conf="${CORE_AUDITS_CONF:-}"
  [ -n "$conf" ] && [ -f "$conf" ] || return 0
  awk -v k="$1" '{ sub(/[ \t]+#.*$/, "") } $1 == k { $1 = ""; sub(/^ +/, ""); gsub(/^["\047]|["\047]$/, ""); print }' "$conf"
}

expand_home() {
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s\n' "$HOME/${1#\~/}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

repo_roots() {
  local roots
  roots="$(conf_values repo_root)"
  if [ -z "$roots" ]; then
    printf '%s\n' "$HOME/code" "$HOME"
    return 0
  fi
  while IFS= read -r r; do
    [ -n "$r" ] && expand_home "$r"
  done <<EOF
$roots
EOF
}

list_repos() {  # unique repo directories under the roots, one per line
  repo_roots | while IFS= read -r root; do
    [ -d "$root" ] || continue
    find "$root" -maxdepth 3 \
      \( -name Library -o -name node_modules -o -name .Trash \) -prune \
      -o -name .git -print 2>/dev/null
  done | sed 's#/\.git$##' | sort -u
}

missing_roots() {  # configured roots that don't exist (a typo must never read as "all clear")
  [ -n "$(conf_values repo_root)" ] || return 0   # the defaults (~/code, ~) are allowed to be absent
  repo_roots | while IFS= read -r root; do
    [ -d "$root" ] || printf '%s\n' "$root"
  done
}

ago() {  # ago EPOCH -> today | 1 day | N days | N weeks | N months
  local days=$(( ( $(date +%s) - $1 ) / 86400 ))
  if [ "$days" -lt 1 ]; then echo "today"
  elif [ "$days" -eq 1 ]; then echo "1 day"
  elif [ "$days" -lt 14 ]; then echo "$days days"
  elif [ "$days" -lt 91 ]; then echo "$(( days / 7 )) weeks"
  else echo "$(( days / 30 )) months"
  fi
}

old() {  # old EPOCH -> "from today" | "3 weeks old"
  local a
  a="$(ago "$1")"
  if [ "$a" = "today" ]; then echo "from today"; else echo "$a old"; fi
}

date_epoch() {  # date_epoch YYYY-MM-DD -> epoch seconds, or nothing if invalid or in the future
  local e back
  case "$1" in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;; *) return 0 ;; esac
  e="$(date -j -f "%Y-%m-%d %H:%M:%S" "$1 00:00:00" +%s 2>/dev/null || date -d "$1" +%s 2>/dev/null)"
  [ -n "$e" ] || return 0
  back="$(date -j -r "$e" +%Y-%m-%d 2>/dev/null || date -d "@$e" +%Y-%m-%d 2>/dev/null)"
  [ "$back" = "$1" ] || return 0          # 2026-02-31 silently normalizes on macOS: reject it
  [ "$e" -le "$(date +%s)" ] || return 0   # a future end date makes no "after that work ended" claim
  echo "$e"
}

plural() {  # plural N singular [plural]
  if [ "$1" -eq 1 ]; then echo "$2"; else echo "${3:-${2}s}"; fi
}

unreadable_dirs() {  # names of top-level folders under the roots that can't be listed from here
  repo_roots | while IFS= read -r root; do
    [ -d "$root" ] || continue
    for d in "$root"/*/; do
      [ -d "$d" ] || continue
      ls "$d" >/dev/null 2>&1 || basename "$d"
    done
  done | sort -u
}

require_git() {  # a missing/broken git must be an audit FAILURE, never an all-clear
  if ! out="$(git --version 2>&1)"; then
    echo "git can't run here: $(printf '%s' "$out" | head -1)" >&2
    exit 2
  fi
}

unique_repos() {  # list_repos, with worktrees of the same repository collapsed to one entry
  list_repos | while IFS= read -r repo; do
    [ -n "$repo" ] || continue
    common="$(cd "$repo" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)"
    [ -n "$common" ] || common="$repo"   # can't resolve: keep the repo, never drop it silently
    printf '%s\t%s\n' "$common" "$repo"
  done | awk -F '\t' '!seen[$1]++ { print $2 }'
}

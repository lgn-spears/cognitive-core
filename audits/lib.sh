# Shared helpers for core audits. Sourced, never executed.
# Contract: audits are read-only. Nothing here writes anywhere.
# Must stay compatible with macOS /bin/bash 3.2.

conf_values() {  # conf_values KEY -> each value on its own line
  local conf="${CORE_AUDITS_CONF:-}"
  [ -n "$conf" ] && [ -f "$conf" ] || return 0
  awk -v k="$1" '$1 == k { $1 = ""; sub(/^ +/, ""); print }' "$conf"
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

date_epoch() {  # date_epoch YYYY-MM-DD -> epoch seconds (macOS or GNU date)
  date -j -f "%Y-%m-%d %H:%M:%S" "$1 00:00:00" +%s 2>/dev/null || date -d "$1" +%s 2>/dev/null
}

plural() {  # plural N singular [plural]
  if [ "$1" -eq 1 ]; then echo "$2"; else echo "${3:-${2}s}"; fi
}

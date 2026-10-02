#!/usr/bin/env bash
# Scheduled jobs still loaded for work the user has said is over.
# Configure in audits.conf:  ended <label-prefix> [YYYY-MM-DD]
set -u
. "${CORE_AUDITS_LIB:-$(dirname "$0")/lib.sh}"

entries="$(conf_values ended | awk '!seen[$1]++')"
[ -n "$entries" ] || exit 0
command -v launchctl >/dev/null 2>&1 || exit 0
listing="$(launchctl list 2>/dev/null)" || exit 0

while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  prefix="${entry%% *}"
  since=""
  [ "$prefix" != "$entry" ] && since="${entry#* }"
  loaded=0
  ok=0
  while IFS='	' read -r pid status label; do
    case "$label" in
      "$prefix"*)
        loaded=$((loaded + 1))
        [ "$status" = "0" ] && ok=$((ok + 1))
        ;;
    esac
  done <<EOF
$listing
EOF
  [ "$loaded" -gt 0 ] || continue
  head="$loaded scheduled $(plural "$loaded" job) matching $prefix $(plural "$loaded" is are) still loaded"
  if [ -n "$since" ]; then
    epoch="$(date_epoch "$since")"
    [ -n "$epoch" ] && head="$head, $(ago "$epoch") after that work ended"
  fi
  if [ "$loaded" -eq 1 ]; then
    if [ "$ok" -eq 1 ]; then detail="It last exited 0 - it is not erroring, it is succeeding."
    else detail="It did not exit 0 last time."; fi
  elif [ "$ok" -gt 0 ]; then
    detail="$ok of the $loaded last exited 0 - they are not erroring, they are succeeding."
  else
    detail="None of the $loaded last exited 0."
  fi
  printf '%s.\t%s\n' "$head" "$detail"
done <<EOF
$entries
EOF

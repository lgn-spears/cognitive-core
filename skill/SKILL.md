---
name: cognitive-core
description: Persistent working memory for this agent — a shared clock, decisions log, open loops, and searchable session history across every harness on this machine. Use at session start, when settling decisions, making promises, learning project facts, or when the user references past work.
---

# cognitive core

You have persistent memory via the `core` CLI. State lives in `~/.core/` —
private, local, shared by every harness on this machine. Use it like a
colleague's desk, not a database to dump into.

## Session start

Run `core inject` before answering anything time-sensitive or project-specific.
Treat its output as authoritative: NOW is the real time; LAST ACTIVITY is when
you last worked with this human; SETTLED lines are decided — never re-litigate
them; OPEN LOOPS are promises that still stand.

## When to write (be deliberate — junk memories make you worse)

| situation | command |
|---|---|
| A question gets settled with rationale | `core decision "chose X — because Y"` |
| You promise future work ("I'll fix CI tomorrow") | `core loop add "fix CI" --due 2026-09-01` |
| A promise completes | `core loop done "fix CI"` |
| Advice given that shouldn't repeat daily | `core log "told Logan to sleep"` |
| A durable fact about the project/human emerges | `core log "prefers plain-English summaries"` |

Do NOT log trivia, intermediate steps, or things already in git/CLAUDE.md.
Curation beats recall.

## When to read

Before answering "what did we do / decide / promise about X", search first:

    core search "X"

Replay a specific day with `core day YYYY-MM-DD`. If your answer depends on a
file path found in history, verify it exists before acting on it — memories
go stale.

## Hygiene

Run `core doctor` if something feels off (overdue loops, stale references).
Never edit `~/.core/days/` ledgers by hand — they're append-only history.

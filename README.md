# lifelog

**A clock for AI agents — because the model has no idea what time it is, when you last spoke, or that it already told you to go to bed on Tuesday.**

LLMs are stateless: every session arrives knowing nothing except what's in
context. Harnesses inject dates sometimes, but nothing tracks *elapsed* time,
*recurrence* of advice, or your actual rhythm across days. So agents nag you
about sleep fresh every night and re-greet you like strangers after lunch.

lifelog is a **sidecar**: one tiny zero-dependency script holding a small
journal of time + activity. Any agent harness that can run a shell command can
read from it and write to it.

## The sidecar principle

You probably run more than one AI harness. lifelog doesn't care:

```
                    ┌──────────────────┐
   Claude Code ────▶│                  │
   opencode ───────▶│  ~/.lifelog/     │  one shared clock,
   Cursor ─────────▶│  state.json      │  one shared journal
   anything else ──▶│                  │
                    └──────────────────┘
                     via bin/lifelog
```

Each harness adds exactly two lines of plumbing:

1. **Session start:** run `lifelog inject` → its output becomes context
2. **Session end:** run `lifelog close` → silently marks activity

## Install

```bash
git clone https://github.com/lgn-spears/lifelog && cd lifelog
ln -sf "$PWD/bin/lifelog" ~/.local/bin/lifelog   # anywhere on PATH works
lifelog inject                                    # first block prints
```

Requires only Python 3.9+. No packages, no network, no daemons.

## Wiring it into YOUR harness

**Claude Code** (`~/.claude/settings.json`):

```json
"hooks": {
  "SessionStart": [{ "hooks": [{ "type": "command", "command": "/path/to/lifelog inject", "timeout": 10 }] }],
  "Stop":         [{ "hooks": [{ "type": "command", "command": "/path/to/lifelog close", "timeout": 10 }] }]
}
```

Session-start stdout is injected into context automatically; `close` on Stop
keeps the clock fresh between conversations.

**Any harness with an instructions file** (opencode AGENTS.md, Cursor rules,
system prompts): paste this —

```
At session start, run `lifelog inject` and treat its output as authoritative
time context. When you give recurring life-advice (sleep, breaks), first check
the journal; if already given today, do not repeat. Record notable advice in
the journal by running: lifelog log "<what you said>"
```

That's the whole integration. The model stays frozen; the state lives outside.

## Commands

| command | does |
|---|---|
| `lifelog inject` | print `[lifelog] temporal context` block; record activity |
| `lifelog log "text"` | append a timestamped journal line |
| `lifelog close` | silently record activity (for stop hooks) |
| `lifelog day [date]` | print one day's full ledger |
| `lifelog search "query"` | search every day, newest to oldest |

State: `~/.lifelog/state.json` · override dir with `$LIFELOG_HOME`.
Journal keeps the last 50 entries; blocks show the most recent 8.

## What the injected block looks like

```
[lifelog] temporal context
NOW: Sat Aug 22 2026 · 15:06 (EDT)
LAST ACTIVITY: Wed Aug 19 2026 · 13:15 — 3 days ago
RECENT JOURNAL:
  • 2026-08-19 01:10 — told Logan to sleep; he kept working
GUIDANCE:
  - Max one sleep/rest suggestion per calendar day. If today's journal
    already records one, do not repeat it.
  - Weave elapsed time into responses naturally ("we spoke three days ago");
    never re-greet a returning user as new.
```

## Design notes

- **The guidance lines are harness state, not model behavior.** The dedup rule
  ("one sleep suggestion per day") works because it sits in front of a frozen
  model every session — the same trick this repo author's `harness-cl` project
  studies formally.
- Journal entries are plain text the *agent* writes about *itself* — a tiny
  Experience Memory. Poisoning it would poison behavior; see `harness-cl` for
  why that matters.
- Everything is deterministic and local. Nothing leaves your machine.

MIT.

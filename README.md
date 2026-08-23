# cognitive core

**The memory half of the cognitive core: one local sidecar gives every AI harness on your machine a shared clock, a private searchable diary of what it did, a decisions log that preserves WHY, and open loops that resurface until done.**

LLMs are stateless geniuses with no watch. Every session starts from zero:
your agent doesn't know it's 2am, that you spoke yesterday, that it already
told you to sleep, or that "we decided this on the 12th." Karpathy's answer
is a slim reasoning model with knowledge living *outside* its weights —
user-owned files instead of vendor lock-in. This repo ships that periphery,
today, for working agents.

Zero dependencies. No network. No daemon. Nothing leaves your machine.

```
                    ┌──────────────────┐
   Claude Code ────▶│                  │
   opencode ───────▶│    ~/.core/      │  one shared clock,
   Cursor ─────────▶│  plain markdown  │  one shared journal,
   anything else ──▶│                  │  all your agents
                    └──────────────────┘
                     via bin/core
```

## Install

```bash
git clone https://github.com/lgn-spears/cognitive-core && cd cognitive-core
ln -sf "$PWD/bin/core" ~/.local/bin/core
core inject        # first session block prints
```

Python 3.9+ only.

## Wire it into your harness (2 lines)

**Claude Code** (`~/.claude/settings.json`):

```json
"hooks": {
  "SessionStart": [{ "hooks": [{ "type": "command", "command": "/path/to/core inject", "timeout": 10 }] }],
  "Stop":         [{ "hooks": [{ "type": "command", "command": "/path/to/core close", "timeout": 10 }] }]
}
```

**Any instructions file** (opencode AGENTS.md, Cursor rules, system prompt):

```
At session start run `core inject` and treat its output as authoritative
context. Before repeating life-advice, check today's ledger. Record notable
advice via `core log "<what was said>"`. When a question gets settled, run
`core decision "<choice> — <why>"`. When you promise something later, open
it with `core loop add "<promise>"`.
```

## Commands

| command | does |
|---|---|
| `core inject` | print session context; record activity |
| `core log "text"` | journal entry worth remembering |
| `core decision "chose X — because Y"` | settled; resurfaces as SETTLED forever |
| `core loop add "promise"` / `done` / list | prospective memory |
| `core day [date]` | replay one day's full ledger |
| `core search "query"` | search every day's ledger |
| `core close` | silently mark activity (stop hooks) |

State: `~/.core/` · override dir with `$CORE_HOME`. Ledgers keep themselves;
journal holds the last 50 notes.

## What a session sees

```
[core] session context
NOW: Sun Aug 23 2026 · 13:20 (EDT)
LAST ACTIVITY: Sat Aug 22 2026 · 16:00 — yesterday
OPEN LOOP (surface; do not silently drop): fix CI before Friday demo — 2026-08-22
SETTLED — do not relitigate: [2026-08-23] SQLite over Postgres — zero-admin single file
RECENT JOURNAL:
  • 2026-08-23 13:10 — worked on harness-cl from opencode
MEMORY: today has 3 ledger entries; full history is private & searchable:
  - `core day` · `core day YYYY-MM-DD` · `core search "<query>"`
GUIDANCE:
  - Max one sleep/rest suggestion per calendar day...
```

## Why these choices

Seven laws distilled from ~30 memory systems, papers, and practitioner
post-mortems — map + territory, append-and-supersede, gated semantic writes,
boring formats, preserve WHY, staleness kills, structural trust. Full
reasoning in [DESIGN.md](DESIGN.md).

MIT.

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
./install.sh        # symlinks bin + installs the Claude Code skill
core inject         # first session block prints
```

Python 3.9+ only.

## Wire it into your harness (2 lines)

**Claude Code** (`~/.claude/settings.json`):

```json
"hooks": {
  "SessionStart": [{ "hooks": [{ "type": "command", "command": "/path/to/core inject", "timeout": 10 }] }],
  "Stop":         [{ "hooks": [{ "type": "command", "command": "/path/to/core close", "timeout": 10 }] }],
  "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "/path/to/core recall", "timeout": 5 }] }]
}
```

`core recall` is optional and makes every message recall-aware: it reads the prompt from the hook's
stdin, searches your memory files with your own words, and prints the best matching lines cited
`file:line` — plus any background results still waiting for you. It never blocks a session: it
always exits 0 and stays silent on "ok"/"thanks" turns.

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
| `core doctor` | health check: overdue loops, stale file references |
| `core close` | silently mark activity (stop hooks) |
| `core recall` | (UserPromptSubmit hook) cited memory lines for this message + undelivered results; `--reindex` builds the optional embedding index |
| `core deliver "text" --source NAME [--key K]` | a background job hands a result to the inbox (same key while pending = same item) |
| `core inbox` / `core inbox ack <id>` | list undelivered results / mark one as seen |
| `core brief [--deliver]` | run the read-only audits in `audits/` — repos with no remote, unpushed work, scheduled jobs for work that has ended; `--deliver` puts each audit's findings in the inbox (one item per audit, updated on re-run) |
| `core deliver ... --replace` | same key while pending → update that item's text to this one (what is true now) |
| `core run NAME [--timeout S] -- CMD...` | run a background job under a lease (no overlap; if the wrapper is killed it kills the job's process group, and a still-alive orphan from a hard kill blocks the next run and keeps alarming), with a timeout that kills its whole process group, recording start/finish/status/last line in `~/.core/heartbeat.json` |
| `core heartbeat` | alarms for every pass in `~/.core/passes.conf` (`expect NAME every 1d`) that never ran, failed, timed out, was killed, has been running too long, died mid-run, or is overdue (1.5x its interval); unparseable `passes.conf` lines are alarms too; exit 1 when any |

**Audits** are plain bash scripts listed in `audits/MANIFEST`, one finding per output line. Configure in
`~/.core/audits.conf` (one `key value` per line, `#` comments allowed): `repo_root <dir>` (default `~/code`
and `~`) and `ended <launchd-label-prefix> [YYYY-MM-DD]` for scheduled jobs that belong to work that's over.
If git is missing or broken, the audit fails loudly — it never reports "nothing needs you" when it couldn't look.

**Run it every morning (macOS)** — save as `~/Library/LaunchAgents/com.you.core-audits.plist`, then
`launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.you.core-audits.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.you.core-audits</string>
  <key>ProgramArguments</key><array>
    <string>/Users/YOU/.local/bin/core</string><string>run</string><string>audits</string><string>--</string>
    <string>/Users/YOU/.local/bin/core</string><string>brief</string><string>--deliver</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>7</integer></dict>
</dict></plist>
```

and tell the heartbeat to expect it: `echo "expect audits every 1d" >> ~/.core/passes.conf`.
On Linux, the cron equivalent: `7 8 * * * $HOME/.local/bin/core run audits -- $HOME/.local/bin/core brief --deliver`.

**What the audits don't see (on purpose, or because macOS won't let them):**
- Repos more than 3 folders below a `repo_root`, and bare repositories, aren't scanned.
- A background job (LaunchAgent / cron) can't read privacy-protected folders — Desktop, Documents,
  Downloads, iCloud, Dropbox and other cloud folders — unless you grant Full Disk Access to `/bin/bash`
  in System Settings → Privacy & Security. The audit never skips silently: it names every folder it
  couldn't look inside, so you can decide.

**Recall is honest about what it is.** Out of the box it matches words, weighted by how rare they are
in *your* memory, and stays silent unless a match is strong. It finds things you name (a project, a tool,
a client); it can't connect meaning across different words.

**Optional: meaning-based recall** with any local embedding model served by Ollama (nothing leaves your
machine). Add to `~/.core/recall.conf`:

```
embed_model qwen3-embedding:0.6b      # `ollama pull qwen3-embedding:0.6b` first (~640 MB)
# embed_url http://localhost:11434    # default
```

then `core recall --reindex` once (about a minute for ~3,000 notes; later runs only re-embed what
changed, and session start refreshes a stale index in the background). Recall then shows a note when
its meaning stands out from your whole memory, or stands out moderately *and* the word matcher agrees.
If the server is down or slow (>1s), recall silently falls back to words — it never blocks a session.
Requests go straight to `embed_url` and never through a system proxy. **`embed_url` decides where your
memory goes:** the default is this machine; pointing it at another host sends every message and your
whole memory there, unencrypted over plain HTTP.
Measured on 61 real, unseen messages with blind relevance judgments: stays silent 97% of the time when
nothing is relevant, puts the right note in the top 3 for 77%, and 74% of what it shows is relevant
(words alone: 90% / 74% / 51%). `tools/eval_recall.py` scores recall against your own labeled messages.

**Heartbeats come first.** A schedule is not proof a job ran. `core inject` puts `HEARTBEAT ALARM:` lines
right under its header, and `core brief` opens with `NOT RUNNING THAT SHOULD BE`.

**Audits** are plain bash scripts listed in `audits/MANIFEST`, one finding per output line. Configure in
`~/.core/audits.conf`: `repo_root <dir>` (default `~/code` and `~`) and `ended <launchd-label-prefix> [YYYY-MM-DD]`.

**Delivery rule:** an inbox item is shown at session start and on every message until it is
acknowledged. Writing a result down is never the same as the person having seen it.

**Recall sources:** `~/.core` ledgers always; plus every `memory_dir <path>` line in
`~/.core/recall.conf`, defaulting to each `~/.claude/projects/*/memory` directory.

## Standing orders

Edit `~/.core/CORE.md` — one rule per line, your voice. Its contents are
injected verbatim into every session, on every harness:

```
Never suggest meetings before 10am.
I ship Thursdays; don't schedule deploys Friday.
Explain trade-offs in plain English before showing code.
```

## Install as an Agent Skill

`./install.sh` also links `skill/` into `~/.claude/skills/cognitive-core`,
teaching Claude Code *when* to write decisions, open loops, and journal
notes — the write discipline that makes the memory actually fill up.
Works with any SKILL.md-compatible harness.

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

# cognitive core

**The memory half of the cognitive core: one local sidecar gives every AI harness on your machine a shared clock, a private searchable diary of what it did, a decisions log that preserves WHY, and open loops that resurface until done.**

LLMs are stateless geniuses with no watch. Every session starts from zero:
your agent doesn't know it's 2am, that you spoke yesterday, that it already
told you to sleep, or that "we decided this on the 12th." Karpathy's answer
is a slim reasoning model with knowledge living *outside* its weights —
user-owned files instead of vendor lock-in. This repo ships that periphery,
today, for working agents.

Zero dependencies. No daemon. Nothing leaves your machine — by default there is no network at all
(the optional meaning-based recall talks to a local model server you run; the optional sweep and
evening passes send what they read to whichever model you configure for them, local or hosted).

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

## Wire it into your harness

**Claude Code** (`~/.claude/settings.json`):

```json
"hooks": {
  "SessionStart": [{ "hooks": [{ "type": "command", "command": "~/.local/bin/core inject", "timeout": 10 }] }],
  "Stop":         [{ "hooks": [{ "type": "command", "command": "~/.local/bin/core close", "timeout": 10 }] }],
  "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "~/.local/bin/core recall", "timeout": 5 }] }]
}
```

(Use the path `./install.sh` printed if you installed somewhere else.)

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
| `core loop add "promise"` / `core loop done "match"` / `core loop` | open, close, list promises |
| `core day [date]` | replay one day's full ledger |
| `core search "query"` | search every day's ledger |
| `core sessions search "query" [--role user\|assistant\|agent] [--project X] [--since YYYY-MM-DD] [--limit N] [--headless]` / `core sessions index` | exact search over your past Claude Code conversations: the actual messages, cited `file:line`, newest first (see below) |
| `core doctor` | health check: overdue loops, stale file references |
| `core close` | silently mark activity (stop hooks) |
| `core recall` | (UserPromptSubmit hook) cited memory lines for this message + undelivered results; `--reindex` builds the optional embedding index |
| `core deliver "text" --source NAME [--key K]` | an external background job hands a result (or, with `--offer`, a question) to the inbox (same key while pending = same item); core's own names are reserved, see the deliver boundary below |
| `core inbox` / `core inbox ack <id>` | list every undelivered result / mark one as seen (a unique part of the id is enough) |
| `core brief [--deliver]` | run the read-only audits in `audits/` — repos with no remote, unpushed work, scheduled jobs for work that has ended; `--deliver` puts each audit's findings in the inbox (one item per audit, updated on re-run) |
| `core deliver ... --replace` | same key while pending → update that item's text to this one (without it the pending text is kept, and it tells you) |
| `core run NAME [--timeout S] -- CMD...` | run a background job under a lease (no overlap; if the wrapper is killed it kills the job's process group, and a still-alive orphan from a hard kill blocks the next run and keeps alarming), with a timeout that kills its whole process group, recording start/finish/status/last line in `~/.core/heartbeat.json` |
| `core offer yes\|no\|later\|never <id> [--note why]` / `core offer stats` | record the person's answer to an offer (later = back in 3 days; never = never re-asked; an offer left unanswered for a week *after it was first shown* expires as "unanswered" — no answer, not a no — and a late answer to it is still recorded, marked late). `--note` keeps their words; it is required to accept a standing-permission proposal |
| `core skill` / `core skill undo <patch-id>` | list skill patches offered from your corrections (offered / applied / undone, and how the next use went) / put a patched SKILL.md back exactly as it was, if it hasn't changed since (see skill-patch offers below) |
| `core grant` / `core grant revoke <scope>` | list standing permissions (scope, date, the person's own words) / revoke one; anything already queued under it goes back to being an offer |
| `core sweep` | offer what's worth remembering from quiet conversations — or, with `learn_mode auto`, learn it without asking (see below) |
| `core learned [--since YYYY-MM-DD]` / `core learned undo <id>` | what was learned without asking, newest first, each with your words, when and where / take one back (a unique part of the id is enough); see [Learning without asking](#learning-without-asking) |
| `core evening` | nightly wrap for tomorrow + at most one insight offer that cites its evidence (see below; sends data to the sweep model) |
| `core home` | the first screen, from files only (no model, works offline): what was learned this week (with each undo command), what's waiting on you (numbered offers, "N waiting", and asks held for tomorrow), what was noticed (unacknowledged results), what got done today (finished jobs, overnight's morning report, your answers), and job health — a broken job moves to the top. A view: it marks nothing as shown |
| `core serve` | the home screen as a private phone page: Tailscale address (else 127.0.0.1) only, a secret token in the path, Yes · Later · No · Never on ordinary offers (recorded exactly like `core offer`); grants and skill patches are answered on the Mac. See [The phone page](#the-phone-page) |
| `core heartbeat` | alarms for every pass in `~/.core/passes.conf` (`expect NAME every 1d`) that never ran, failed, timed out, was killed, has been running too long, died mid-run, or is overdue (1.5x its interval); unparseable `passes.conf` lines are alarms too; exit 1 when any |
| `core overnight` / `core overnight resume NAME` / `core overnight ask NAME` | run the jobs in `~/.core/overnight.conf` that hold a standing permission for their exact command, in legs of ≤5 steps with a check between legs, then put one morning report in the inbox (see below); resume a job paused after 3 failing nights; ask for a job's permission again (e.g. after a no) |

**Audits** are plain bash scripts listed in `audits/MANIFEST`, one finding per output line. Configure in
`~/.core/audits.conf` (one `key value` per line, `#` comments allowed): `repo_root <dir>` (default `~/code`
and `~`) and `ended <launchd-label-prefix> [YYYY-MM-DD]` for scheduled jobs that belong to work that's over.
It never reports "nothing needs you" when it couldn't look: a broken git fails the audit, and a
`repo_root` that doesn't exist or holds no repos is reported as such. "Unpushed work" means commits;
uncommitted edits in a pushed repo aren't flagged.

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
How much it helps depends on how much memory you have, so here are both ends, measured on messages
labeled before recall ran:

| memory | silent when nothing's relevant | right note in top 3 | shown notes relevant |
|---|---|---|---|
| ~3,000 notes, 61 real unseen messages, blind-judged — words | 90% | 74% | 51% |
| same — with meaning | **97%** | **77%** | **75%** |
| 76 notes, 40 messages — words | 100% | 65% | 64% |
| same — with meaning | 90% | 70% | 60% |

On a large memory it is clearly better; on a small one it's roughly even (it finds a few notes words
miss, such as "Rust extensions" → your editor preferences, and adds a few loose matches). Notes written
since the last index, and memories under ~30 chunks, are matched by words. `tools/eval_recall.py`
scores recall against your own labeled messages — a JSON list of
`{"prompt": "...", "expect": "recall" | "silent", "relevant": ["note_name", ...], "split": "dev"}`.

**Session search** (`core sessions`) finds what was actually said in past Claude Code conversations — your
messages and the assistant's visible replies (no tool output, subagents, hook injections or compaction
summaries) — and prints the messages themselves, never a model's summary of them: no model is involved, so
nothing is paraphrased or made up. Every word must match; `"quoted words"` match as a phrase. There is no
other query syntax: `-word`, `OR` and `prefix*` are searched as plain words (`sqlite*` finds "sqlite", not
"sqlite3"). With FTS5, accents are folded (`cafe` finds "café"); without it they must match exactly. Words
are split on spaces and punctuation, so a run of Chinese or Japanese with no spaces is one word: search for
the whole run, not part of it.

```
$ core sessions search "postgres overkill"
== -Users-sam-code-shop · 5f1c9e2a-… ==
   began: kick off the shop checkout work
   ended: ship it friday
  ~/.claude/projects/-Users-sam-code-shop/5f1c9e2a-….jsonl:2  user  2026-09-01 05:01
    let's use SQLite for the cart, Postgres is overkill here

1 message(s) in 1 session(s)
```

The index also records which skills each conversation loaded (used to find earlier corrections of a skill).
Each session with a hit shows how it began and how it ended (your first and last message), so you can tell
which conversation it was. `core sessions index` builds or refreshes the index; `core sweep` refreshes it at
the start of every run (incremental: only new or changed transcripts are read, deleted ones are dropped). It
reads every `*.jsonl` in `~/.claude/projects/*/` (or your `sweep_dir`s), skipping subagent transcripts and
core's own model calls. **Headless runs** (sessions started by `claude -p` or the Agent SDK: `entrypoint`
`sdk-*` in the transcript) are indexed but hidden; `--headless` includes them, and their "user" turns are
labelled `agent` (`--role agent`), because they're another agent's brief, not you. `--since YYYY-MM-DD`
counts from your local midnight. It uses SQLite full-text search (FTS5) when your Python's SQLite has it,
and a slower plain scan when it doesn't. Searching never changes the index: one built by an older core says
`index needs rebuild: run core sessions index`. A refresh commits once, at the end, so a search during one
reads the whole previous index (never a half-refreshed one), and an interrupted refresh leaves it as it was. A
headless run's opening and closing lines are shown as `agent began:` / `agent ended:`. If the index file isn't
readable (or, for `index`, writable) by you, the command says so instead of suggesting a rebuild.

**The index holds the raw text of your conversations.** It lives only at `~/.core/sessions.db`, readable by
you alone (mode 0600), and is never sent anywhere — searching it makes no network calls. Delete the file to
forget it; the next index rebuilds it from your transcripts.

**Optional: the quiet sweep** (`core sweep`) reads Claude Code conversations once they've been idle 30
minutes and *offers* what's worth remembering — decisions, corrections, durable facts, preferences, open
loops — through the inbox. By default it never writes memory itself: every offer quotes the person's own words
(checked by code, not the model) and the agent saves it only on an explicit yes; a correction that
contradicts an existing note is offered as "update X → Y". With `learn_mode auto` it learns instead of asking
(see [Learning without asking](#learning-without-asking)). Configure in `~/.core/recall.conf`:

```
sweep_model qwen3:8b            # any Ollama model; or a model name with sweep_api below
# sweep_api ollama | openai | claude   (openai = LM Studio / llama.cpp / mlx_lm server; claude = `claude -p`)
# sweep_url http://localhost:11434
# sweep_strict on               # block anything question-shaped (default; turn off for strong models)
# sweep_offer_types fact preference correction   # the rest is logged only
# asks_per_day 5               # one daily budget for EVERY ask (sweep, evening, grant proposals, deliver --offer)
# sweep_shadow on               # log what it would offer to ~/.core/sweep.log, offer nothing
# sweep_headless on             # also read headless runs (claude -p / Agent SDK). Off by default: their
                                # "user" turns are an agent's brief, not your words (so even when on, their
                                # items are only ever offered, never learned silently)
# sweep_key_file ~/.config/x/key  # API key for a hosted OpenAI-compatible server (a file holding the key,
                                  # or a line like `export X=key`); $SWEEP_API_KEY wins if set. Never logged.
```

Run it on a schedule under `core run sweep -- core sweep` with `expect sweep every 3h` in
`passes.conf`. Each run is bounded (20 extractor calls, 20 minutes) and saves progress per chunk;
before an offer, the model checks your most related memory lines so you're never offered what you
already have. With `sweep_api claude` the extractor runs isolated: no tools, no MCP servers, no hooks,
no saved transcript. **Where conversations go is `sweep_url`'s / the extractor's business**: a local
model keeps them on this machine. Measured on real conversations with blind judges, extraction
quality depends heavily on the model; test yours with `tools/eval_recall.py`-style labels before
turning offers on (start in shadow).

**Skill-patch offers.** When you correct the assistant while a Claude Code skill is in use, the sweep can offer a
concrete patch to that skill's `SKILL.md`. It never edits a skill on its own: the file changes only when you answer
yes to core's own offer.

- **Evidence, not counters.** It fires when a swept conversation loaded a skill (the `Skill` tool, or the
  `Base directory for this skill:` text Claude Code injects for it and for `/skill-name`) *and*, inside that
  skill's span (until the next skill is loaded), you made a correction that passed the sweep's quote gate: your
  verbatim words, not a question or a maybe. Session length and tool counts never trigger it. If the session
  index finds you said much the same thing while the same skill was loaded in earlier sessions, those messages
  are cited and that skill goes first.
- **A model drafts, code decides.** The sweep model (same `sweep_model` / `sweep_api`) gets the skill file, your
  words and lesson rules: capture the durable rule, fix in place, keep it short, don't restate the
  skill; never "this tool is broken", environment-specific failures, one-off stories, or failed attempts as best
  practice. It may answer "no change". A draft becomes an offer only if it applies cleanly to the file as it is
  now (found by its context lines, uniquely; a diff header naming any file but `SKILL.md` is refused), changes at
  most 12 lines, leaves the frontmatter block (`---` …
  `---`: name, description, tools, model) byte-for-byte untouched, adds at least one line and removes at most
  one — never a line that asks, confirms, verifies or says never/don't — and every added *and* removed line
  passes the filters for quotes and statements (no instructions, commands, backticks, links, secrets, hidden or
  lookalike characters) plus a stricter skill filter: no `<` (HTML or comments), no `](` (Markdown links or
  images), no domains (bare, spelled out like "dot org", or defanged like `[.]`), no API keys, `.env`/env files
  or credential paths, nothing "without confirmation/asking", no force-push, hard reset or other destructive git,
  and nothing telling the reader to disregard or ignore earlier guidance. An added line also may not claim a tool
  is broken. The file's line endings (LF or CRLF) are kept; a file with mixed endings isn't patched. Only a
  `SKILL.md` inside a `.claude/skills/<name>/` folder qualifies (names are letters, digits, `_`, `.`, `-`; never
  `.` or `..`; a path that climbs out with `..` is refused). Otherwise your correction goes on as an
  ordinary memory offer. **This sends the whole skill file to the sweep model.** Skills managed by a plugin
  (under `~/.claude/plugins/`) are never patched: an update would overwrite the patch.
- **The offer** (source `skill`) shows the patch's own `+"…"` / `-"…"` lines first (each cut to fit), then your
  words and the skill's path — never only a model's summary; the full diff, rebuilt by code from before/after so
  it is exactly what a yes applies, is at `~/.core/skill-patches/<id>.diff`. **One skill offer open at a time**:
  none is drafted while another is pending, deferred or waiting for a slot, and each is drawn from the shared
  `asks_per_day`; when there's no room the drafter isn't even called. A correction that became a skill offer
  isn't also offered as a memory.
- **Yes** applies it: the file's hash must still match the one drafted against (if you edited the skill since,
  nothing is written, the yes says so, and the offer becomes `stale` — not accepted, so it teaches the learner
  nothing; the same correction can come back as a fresh draft against your edited file), a rollback copy goes to `skill-patches/<id>.orig`, the write is atomic
  (through a symlinked skill folder to the real file), and `~/.core/skills-ledger.jsonl` records it.
  `core skill undo <id>` restores the original if the file still matches the patch. **No / later** work as for
  every offer; **never** also stops patch offers for that skill.
- **Did it help?** After a yes, the next conversation that loads that skill is recorded as `clean` or
  `corrected` (another correction inside its span), in `offer-outcomes.jsonl`; `core offer stats` shows it per
  skill. "Corrected" means a correction the sweep would capture, so in-the-moment fixes don't count, and a
  conversation is judged when the sweep finishes reading it.

## Learning without asking

Asking before every save gets old: a good assistant learns as it goes and lets you correct it. Add
`learn_mode auto` to `~/.core/recall.conf` and the sweep saves what it finds to its own file instead of asking,
with an Undo on everything. The default stays `learn_mode ask` (every memory item is an offer), because silent
writes should be a choice you make.

```
learn_mode auto            # default: ask
# learn_file ~/.core/learned.md   # where learned lines go (default $CORE_HOME/learned.md); refused inside
                                  # a memory directory recall reads (your curated notes)
# learn_per_day 10         # silent saves per day; the rest wait for tomorrow
# learn_budget_kb 24       # over this, the evening pass offers a consolidation
```

- **The same gates, plus one.** An item is saved only if it passes everything an offer had to: the person's
  verbatim words (never the assistant's), no maybes or questions, the extractor's own traps, the statement and
  quote filters, and the novelty judge. In auto mode the judge also decides whether it is *durable* — would a
  session on a different task, weeks from now, be better for knowing it? Only an explicit yes counts: a one-off
  ("make this headline one line") or a judge that doesn't say is never saved. Known items are skipped. If the
  judge can't be reached, nothing is saved on a guess; the item waits for the next run.
- **Its own file, never yours.** Entries go to `learned.md` (one line each: the statement, your words, date and
  time, project and `session:line`, type, a stable id). Recall searches it like any memory file. A correction to
  a line *in* `learned.md` replaces that line (the old text is kept for undo); a correction to one of your own
  memory files never edits that file — it is saved in `learned.md` marked `supersedes <file>:<line>`.
- **Undo.** `core learned undo <id>`, or the Undo button on the phone page, removes the entry (or puts back the
  line it replaced). The same words are never learned again. Hand edits to `learned.md` are fine; undo only
  touches the line with that id. Once a consolidation (or a hand edit) has rewritten an entry, undo just removes
  it: the line it once replaced is never brought back, since the rewrite already decided what holds.
- **It learns from undos.** Each save and undo is a row in `offer-outcomes.jsonl` (source `learned`). A type you
  undo often (at least 3 times, and at least 30% of its saves) goes back to asking first: those items are offers
  again. `core offer stats` and the page say so. An entry still standing after 7 days counts in stats as a
  *soft* positive, labelled as such. **Silence is never permission**: a save is never an "accepted" answer, so
  it never leads to a standing-permission proposal, and learned lines are notes, not instructions.
- **One memory question a day, at most.** Core asks about memory only when it genuinely can't decide alone: a
  correction that would supersede one of your own notes, two of your statements that conflict, or an item the
  judge can't call durable *and* that would matter a lot if wrong. It asks like a person would ("Quick one: you
  said “…” on Friday, but your notes say “…”. Which is right now?"), one tap to answer (*What I Said* / *My
  Notes*; *The Newer One* / *The Earlier One*; *Remember* / *Don't*), and on a yes core writes it to `learned.md`
  itself. Never more than one a day across every producer (and it uses a slot of `asks_per_day`); when today's is
  used, a correction is saved as superseding your note (your file untouched) and the other two wait for another
  day. Everything else is decided silently. Answers to these questions never count toward a standing permission.
- **What still asks.** Insights, standing permissions (including overnight jobs), skill patches — and a
  consolidation of `learned.md` when it outgrows `learn_budget_kb` (the evening pass offers it at most once a
  month, since it rewrites what was learned).
- **Switching on.** The first sweep in auto mode judges any memory offers still waiting on you under these rules
  (plain memory offers only, and only when your words are still at the transcript line they cite):
  durable ones are learned (they show under What I Learned, with Undo); one-offs and things memory already says
  are quietly retired (`superseded`, not counted as a no).

**Offers, answers and standing permissions.** Sweep and evening results that need a decision arrive as
*offers*. The agent asks in one line and records the answer with `core offer yes|no|later|never <id>`;
it never assumes one. An offer's week starts the first time it is shown, so a quiet week away never
expires anything. After the **3rd yes** to the same kind of sweep offer (e.g. `sweep:preference`), the
inbox asks once whether to save those without asking from now on. Only the person's own words grant it:
`core offer yes <id> --note "<what they said>"`. A no is remembered. Proposals are only made for
`sweep:<type>` scopes: a yes to "save these without asking" can never let an overnight job run (those are
granted only through overnight's own offer, below). Under a grant, items arrive as "Pre-approved": the agent
saves them and says in one line what it saved. `core grant` lists grants with the words that created
them; `core grant revoke <scope>` ends one, and anything still queued under it — shown or still held for a
slot — becomes an ordinary offer.

**Optional: the evening pass** (`core evening`) delivers a short wrap for tomorrow (what was decided
today, overdue loops, offers waiting, unread items, job health), retiring yesterday's wrap, plus at
most one insight offer, and only when it cites exact lines that pass the same safety filters as quotes.
An insight is offered once: it is keyed by the lines it cites (not the date), and one that cites no line an
earlier insight hadn't — answered, acknowledged or not — is dropped, however it is reworded. The model is shown
the last few insights it offered so it looks for something new.
With no `sweep_model` it only writes the wrap and says "no insight model configured". **With one, it
sends today's ledger, your recent decisions, your open loops and the text of pending inbox items to the
configured sweep model.** A local model keeps that on this machine; `sweep_api claude` sends it to
Anthropic through `claude -p`, and an `openai` endpoint on another host sends it to that host. It exits
1 when the model can't be reached (the wrap is still delivered), so the heartbeat alarms.

**Scheduling sweep and evening (macOS).** Jobs started by launchd get a bare PATH, so set one that
finds `core` and, with `sweep_api claude`, `claude`. Save as
`~/Library/LaunchAgents/com.you.core-sweep.plist` and `launchctl bootstrap gui/$UID <file>`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.you.core-sweep</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/Users/YOU/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>ProgramArguments</key><array>
    <string>/Users/YOU/.local/bin/core</string><string>run</string><string>sweep</string><string>--</string>
    <string>/Users/YOU/.local/bin/core</string><string>sweep</string>
  </array>
  <key>StartInterval</key><integer>10800</integer>
</dict></plist>
```

For the evening pass, copy it as `com.you.core-evening`, with `evening` in place of both `sweep`
arguments and `<key>StartCalendarInterval</key><dict><key>Hour</key><integer>21</integer></dict>` in
place of `StartInterval`. (Run `which claude` to check its folder is on that PATH.) Then
`printf 'expect sweep every 3h\nexpect evening every 1d\n' >> ~/.core/passes.conf`. With cron:

```
PATH=/home/you/.local/bin:/usr/local/bin:/usr/bin:/bin
0 */3 * * * core run sweep -- core sweep
0 21 * * *  core run evening -- core evening
```

**Heartbeats come first.** A schedule is not proof a job ran. `core inject` puts `HEARTBEAT ALARM:` lines
right under its header, and `core brief` opens with `NOT RUNNING THAT SHOULD BE`.

**Delivery rule:** an inbox item is shown at session start and on every message until it is
acknowledged (offers are listed first). An unanswered offer is shown at every session start but, per
message, only once every 10 messages, so a pending question doesn't repeat on every turn. Writing a
result down is never the same as the person having seen it.

**The deliver boundary:** `core deliver` is for external jobs' reports and offers only. It can never speak
as one of core's own producers, so it refuses:

- sources `sweep`, `evening`, `overnight`, `permissions`, `skill` (compared case-blind, lookalike letters folded);
- keys starting `grant:`, `sweep:`, `insight:`, `evening:`, `overnight:`, `skill:`, `learned:`;
- tags `grant`, `granted`, `grant_job`, `cmd_sha`, `v`, `patch`, `question`, `learn` — so it can never ask for, or claim, a standing
  permission, or point an offer at a skill patch;
- text claiming a pre-approval or standing permission ("Pre-approved…", "Standing permission…", "Sweep offer…",
  "Skill patch offer…").

Every item records its origin (`cli` or `internal`); `--replace` and `--offer` act only on an item from the same
origin and source, and a key already used by another producer is refused. `core offer yes` changes a skill only
for a skill offer core itself made. It writes a grant only
for an offer core itself made, and always says so: `standing permission granted: <scope> — revoke: core grant
revoke <scope>`. Items from before origins existed count as `cli`.

What reaches the agent's context — session start, per-message recall, `core home` — is filtered like sweep
quotes and statements (no instructions, commands, links, secrets, hidden or lookalike characters). An item that
fails shows as `` <source> result — open with `core inbox` ``; `core inbox`, run by you, shows the full text.
This includes `brief --deliver` audit lines and the job output quoted under DONE TODAY.

**Recall sources:** `~/.core` ledgers always; plus every `memory_dir <path>` line in
`~/.core/recall.conf`, defaulting to each `~/.claude/projects/*/memory` directory; plus `learned.md` (see
Learning without asking) when it exists.

## Asks: one budget a day

Every producer that asks you something — the sweep, the evening insight, a standing-permission proposal,
any `core deliver --offer` — draws on one daily budget: `asks_per_day` in `~/.core/recall.conf` (default 5;
the older `sweep_offers_per_day` still works and now covers every producer). An ask over the cap isn't
dropped: it is kept in the inbox as *waiting*, with the reason, and takes a free slot on the next day that
has one (oldest first, with a fresh week to answer). A held ask that finds no slot for a week dies quietly
(`stale`; it was never asked, so it isn't counted as unanswered); a held evening insight is about one
evening, so it is dropped quietly after a day. Plain reports are never capped.

What counts: anything put to you as a question on that day — a new offer, a held ask taking its slot, an
offer coming back from `later`, and an item turned back into an offer by `core grant revoke`. What doesn't:
"Pre-approved" items under a standing permission (they ask nothing) and plain reports. The evening wrap says
how many asks are waiting for tomorrow.

## Home

`core home` prints the first screen — the place you go on purpose:

```
Ariadne · Fri Oct 2 · 9:20 PM

WAITING ON YOU · 1 waiting

 1  The overdue domain renewal and the unsent invoice are for the same client — one email
    could do both.
    → yes · later · no · never: core offer <answer> bbb222
 ·  1 more ask waits for tomorrow (today's 3 are used).

NOTICED

 ·  2 repos have no remote: example-site, notes-app
    audits · 8:07 AM · core inbox ack eee555

DONE TODAY

 ·  sweep finished 8:50 PM: "sweep: 1 offer(s) of 4 item(s)"
 ·  You answered 3 offers today: 1 yes, 2 no.

audits 8:07 AM · sweep 8:50 PM · evening 9:03 PM · all on time
```

Everything on it already lives in `~/.core` (inbox, `heartbeat.json`, `passes.conf`, `offer-outcomes.jsonl`);
if it disappears nothing is lost. An empty home says `Nothing needs you.` A job that failed, hung or is
overdue replaces the healthy footer with a `!` line under the header. Acknowledging an item anywhere
removes it here.

## The phone page

`core serve` serves the home screen as a private page for your phone: the same data as `core home`, with
**Yes · Later · No · Never** buttons on each offer. With `learn_mode auto` it opens with **What I Learned** (today,
then earlier this week): each entry in your terms ("You prefer…"), your words, when and where you said them, and
an **Undo** button (it does exactly what `core learned undo` does, with the same nonce check as answers). **Needs
You** below it holds only real asks. The headline says both: "Learned 4 things today. One thing needs you."

```
core serve            # prints: core serve: open http://100.x.y.z:8796/<token>/
core serve --url      # print the URL and exit
core serve --local    # 127.0.0.1 only, even when Tailscale is up
```

- **Where it listens.** This Mac's Tailscale address when Tailscale holds one (`tailscale ip -4`), otherwise
  127.0.0.1. Never `0.0.0.0`: anything else is refused. If the address changes, the server exits so launchd
  restarts it on the new one. Install Tailscale on the phone and open the URL there; nothing goes through a
  third party's servers.
- **The token.** A random secret in `~/.core/serve.token` (0600) is the first path segment. Without it every
  request is a bare 404 with no body. Request lines are never logged. Delete the file to rotate it. A request
  naming any other host than the address it listens on (or `localhost`, when local) is refused, as is a post
  another site makes (`Sec-Fetch-Site: cross-site` or a foreign `Origin`). Each connection has its own thread and
  3 seconds to speak, so a stalled one never holds up the page.
- **Answers.** A tap records exactly what `core offer <answer> <id>` records (it is the same code: same lock,
  same `offer-outcomes.jsonl` row). A form post also needs a nonce from a page this server rendered, so another
  site can't post one, and a page from before a restart asks you to reload. It works with JavaScript off
  (plain form posts); with JavaScript the answered offer slides out and a quiet "Recorded" line appears.
- **What the phone can't answer.** Standing-permission proposals, overnight job permissions, skill patches and
  consolidating learned memory are shown but say *Answer On Your Mac*: a grant needs your own words (`--note`), a patch needs its diff read, a consolidation rewrites a file in a session with you.
  Offers whose text fails the display filters show a pointer to `core inbox`, never the raw text.
- **The page itself.** One file, inline CSS and JS, no outside requests (a strict Content-Security-Policy says
  so). Type is Iowan Old Style for what was said and Avenir Next for everything else, both built into iOS and
  macOS, so nothing is downloaded. Light and dark follow the phone; reduced motion is respected.

Run it under launchd (not installed for you). Save as `~/Library/LaunchAgents/local.core.serve.plist`, fix the
paths, then `launchctl load` it:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.core.serve</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string><string>/Users/you/code/cognitive-core/bin/core</string><string>serve</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/Applications/Tailscale.app/Contents/MacOS:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <!-- the URL (with its token) is printed here: keep it inside ~/.core -->
  <key>StandardOutPath</key><string>/Users/you/.core/serve.log</string>
  <key>StandardErrorPath</key><string>/Users/you/.core/serve.log</string>
</dict></plist>
```

The page only loads while the Mac is awake and on the tailnet.

**The doorbell.** Add `notify_cmd` to `~/.core/recall.conf` to be pinged when one of core's own producers (sweep,
evening, permissions, skill) puts a new question to you:

```
notify_cmd /path/to/your-notifier --title     # gets one more argument: "<name>: 1 new"
```

The message never carries the offer's text, source or id, only a count. It rings at most once an hour; asks
that land inside the hour are counted into the next ping. Reports and `core deliver` from external jobs never
ring it. Without the line nothing runs.

## Identity

`~/.core/identity.md` (optional, yours) gives the agent a name and a voice. Its lines open every
`core inject`, so every session on the machine is the same agent; a `name: …` line also titles `core home`.

```
name: Ariadne
You are Ariadne, Sam's agent. Same memory in every session; the model underneath is fresh each turn.
Blunt, warm, no lectures.
```

Without the file nothing changes.

## Overnight work

`core overnight` does pre-approved work while you're away and leaves one report for the morning. There are
no jobs by default; you declare them in `~/.core/overnight.conf` (shell quoting, `#` comments):

```
deadline 4h          # whole run; each job's timeout is cut to what's left (default 4h)
max_jobs 5           # jobs started per night; the rest wait (default 5)
job tests scope=overnight:tests steps=1 timeout=20m cmd='cd /Users/sam/code/myapp && make test > /Users/sam/code/myapp/tests.txt'
job notes scope=overnight:notes steps=8 check='/Users/sam/scripts/verify-notes.sh' cmd='/Users/sam/scripts/draft-note.sh $CORE_STEP'
```

Use absolute paths in `cmd` and `check`: launchd starts jobs with `/` as the working directory (and a bare
PATH), so `./scripts/...` would resolve against `/`, not your home.

- **Only with a standing permission, for that exact command.** Overnight permissions are offer-only: a job
  runs only after you said yes, in your own words (`core offer yes <id> --note "..."`), to overnight's own
  inbox offer for it (from `permissions`, counted against `asks_per_day`). That offer says plainly that a yes
  permits running the job's command, names the job, its scope and a short hash of its `cmd` + `check`; the
  command itself stays in `overnight.conf` and the log. The grant is bound to that job and that hash: edit
  the command, or let another job claim the scope, and it is skipped and asked about again instead of run.
  A "save these without asking" yes never grants a job, and a scope can't be a `sweep:<type>` one.
- **Asked once; re-ask on request.** A job without a permission is skipped and asked about once per version
  of its command. After a no it isn't asked again on its own; `core overnight ask NAME` puts the question back
  in the inbox when you change your mind.
- **Revoke anytime.** `core grant revoke <scope>` takes effect mid-run: the permission is re-read before every
  step and every check, and a revoked job stops and is reported as "stopped: permission revoked" (not counted
  as a failing night).
- **Legs of at most 5 steps.** `cmd` runs `steps` times (`$CORE_STEP`, `$CORE_LEG`, `$CORE_JOB` are set).
  After every 5 steps, and at the end, `check` must exit 0; without a `check`, the steps' exit status
  decides. The first failure stops the job.
- **Supervised like `core run`.** Each job runs as `core run overnight-NAME` (lease, process-group timeout,
  run record), so `expect overnight-NAME every 1d` in `passes.conf` alarms when it stops running.
- **Jobs only prepare.** Drafts, branches, local files. Sends, posts, payments, deploys, deletes and pushes
  to shared branches are never an overnight job: they stay offers you answer in the morning. The runner
  can't tell what a command does, so this is on you when you write `overnight.conf`.
- **One morning report** (inbox key `overnight:<date>`): what ran, what succeeded, what failed and why, what
  was skipped for lack of a permission. A job's own output is shown only when it passes the same filters as
  sweep quotes (no instructions, links, commands, secrets or hidden text); otherwise the report says
  `exit N (details in the log)`. Full output is in `~/.core/logs/overnight-<date>.log`.
  A job that fails 3 nightly runs in a row is paused and reported until `core overnight resume NAME`.

Schedule it like the audits: `core run overnight --timeout 15000 -- core overnight` at night, with
`expect overnight every 1d` in `passes.conf`.

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

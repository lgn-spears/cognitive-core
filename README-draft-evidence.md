# DRAFT — proposed README section (not yet merged)

Intended to sit directly after the opening blockquote, before `## Install`.
All identifying details redacted; every number verified against a real machine.

---

## Most of what a proactive assistant is useful for needs no model at all

Muse and dots both answer "what should I look at right now?" with a cloud
agent and a token budget. On a developer's machine, most of that answer is
sitting in `git`, `launchctl`, and the closing lines of yesterday's session.

This is one run, on the author's machine, the day this was written:

```
OPEN, NOBODY WAITING ON ME
  74 commits in 4 repos have no git remote at all.
     Oldest 3 weeks. This machine has no backup destination configured.
  115 unpushed commits in a fifth repo, oldest 3 weeks.

STILL RUNNING, SHOULDN'T BE
  20 scheduled jobs are still firing for a client engagement that ended
  10 weeks ago. 11 of the 20 last exited 0 - they are not erroring,
  they are succeeding.
     First flagged 3 weeks ago. Raised twice more since. Still loaded.

ASKED, NOT ANSWERED
  A one-word answer has blocked a deliverable for 14 days.
  It has now been asked for twice.
```

Three of those four findings cost **two shell commands and no model at all.**

```bash
core brief                  # what needs you right now
core brief --since yesterday
```

## How it works, in three tiers

The cheap tiers do most of the work. That ordering is the design, not an
optimization.

**Tier 1 — deterministic audits.** Git remotes, unpushed commits, loaded
scheduled jobs, stale credentials. Shell commands against real system state.
Zero inference, zero tokens, and structurally incapable of hallucinating.

**Tier 2 — the closing-block key.** Agent transcripts are mostly noise, but
assistants close sessions in a strikingly formulaic way:

```
**Still waiting on you:**
**What I need from you**
**Two things pending on your side**
```

Those blocks are already dated, already name the blocker, and already name
the owner. Extracting them beats inferring intent from conversation, and it
beats keying on "the session stopped here" — which is almost always an
interruption, not an abandonment.

Measured on a 14-day corpus: across 1,365 of the author's own messages there
was one "tomorrow," one "deadline," and zero "Friday." The assistant's
closing blocks carried **every** durable commitment that mattered. Mine the
structure, not the prose.

**Tier 3 — escalation, not detection.** The value is rarely in noticing
something the first time. It is in *"this is the third time you have been
asked for this."* Repeat-count needs no model either.

## How it reaches you

A CLI you have to remember to run is not proactive. A hook that fires before
you type anything is.

```
SessionStart hook ──▶ core inject ──▶ the brief is already on screen
```

That is the whole trick, and it is why this works inside a coding agent
specifically. Muse needs its own app. dots needs an always-on cloud machine.
This needs a hook you already have.

The same brief can be pushed to a phone through any notifier you already run
(ntfy, Pushover, a Live Activity). Nothing new to host.

## Against the cloud versions

| | Muse | dots | cognitive-core |
|---|---|---|---|
| Runs on | Meta's cloud | OpenAI's cloud VM | your machine |
| Reads | connected accounts | connected apps | files already on your disk |
| Data owner | Meta | OpenAI | you |
| Proactive tier cost | tokens | tokens | two shell commands |
| Can act on your behalf | yes | read-only tools | never — surfaces only |
| Works across harnesses | its own app | ChatGPT | Claude Code, opencode, Cursor, any |

The last row is the one that compounds. `~/.core` is shared, so a commitment
made in one harness surfaces in the next one you open.

## Why v0.4 was not enough

v0.4 followed Law 3 strictly: mechanical capture automatic, semantic capture
explicit. That law is correct and it is still the law. But the author's own
ledger, 40 days in, read:

```
36 days of ledgers      207 lines, all of the form "session start (dir)"
decisions.log           1 entry
loops.md                1 entry
journal                 3 entries
```

Every judgment entry dated from the two days the tool was built. Nothing
since. Meanwhile the same machine's agent transcripts grew to 3.4 GB and its
curated memory files to 323, over 200 of them touched in the same 30 days.

The difference is not quality of intent. It is that memory files are written
*as a byproduct of working*, while `core log` asks you to stop working and
log. Capture that requires a separate act of discipline does not survive
contact with real work.

So v0.5 does not relax Law 3 — it stops depending on it. Noticing reads from
what work already leaves behind, surfaces read-only, and persists nothing
about your projects. Law 3 governs *writes*; inferring in order to show you
something, and storing none of it, is not semantic capture at all.

## What this is not

It is not an always-on agent with its own computer. It does not act on your
behalf, send anything, or change anything. It reads what is already on your
disk and tells you what it sees. The relevance gate is the product — a
suggestion has to be worth the interruption, or it should not appear.

# DESIGN — cognitive core

**What this is:** the memory half of Karpathy's cognitive-core architecture.
His June 2025 thesis: future models should be *skinny reasoners* that
"maximally sacrifice encyclopedic knowledge for capability." His April 2026
follow-through ("LLM Knowledge Bases," 46K stars on the gist) spec'd where
the knowledge goes instead: agent-maintained plain-text stores. This repo is
that spec made runnable for *working agents* — plus the practitioner layer
(decisions, open loops, handoffs) his wiki vision doesn't cover.

## The seven laws (distilled from ~30 systems, papers, and practitioner post-mortems)

1. **Map + territory.** A tiny always-injected index points at deep bodies.
   Every serious design converged here independently: Letta's core blocks,
   Claude Code's MEMORY.md index, Skills' three-level disclosure, ChatGPT's
   summary-vs-history. Nobody loads everything; whoever tries loses.
2. **Append + supersede, never delete.** Mem0 shipped LLM-judged UPDATE/DELETE,
   watched it destroy information, and reversed to ADD-only in v3. Zep's
   answer is stronger: invalidate-with-timestamp, keep full history. We
   append-only everywhere; corrections are new lines.
3. **Mechanical capture automatic; semantic capture explicit.** Claude Code's
   auto-memory ate 47% of users' system prompts with inaccurate unreviewable
   saves — the field's clearest negative result. Our ledgers write themselves;
   judgment entries (`decision`, `loop`, `log`) are deliberate acts.
4. **Boring formats win.** Markdown + grep + git beat embeddings for code
   context (top SWE-bench systems navigate with grep). No vector store until
   proven necessary — Karpathy's index-first navigation holds to ~500 docs.
5. **Preserve WHY.** "Stop relitigating settled decisions" was the #2 pain
   across every practitioner thread. `decisions.log` is append-only and its
   entries surface in every session header as SETTLED.
6. **Staleness is the enemy.** "A note referencing dead files is how agents
   confidently act on outdated beliefs." Dates on everything; loops close
   loudly; supersession over mutation.
7. **Trust must be structural.** Harness state can be poisoned (see our
   sibling project, harness-cl). Provenance and tamper-evidence are on the
   roadmap as first-class format features, not add-ons.

## The directory contract

```
~/.core/
  state.json        clock: last-seen (machine)
  days/YYYY-MM-DD.log   episodic ledger per day (auto-written, immutable)
  journal (in state)    hot ring of recent notes (last 50)
  decisions.log     settled questions + rationale, dated (append-only)
  loops.md          prospective memory: promises that resurface until closed
  CORE.md           (planned v0.4) user-editable map & standing orders
```

The injected block IS the map: time, gaps, open loops, recent settlements,
journal tail, and pointers into the deep archive. Small by construction;
depth lives one `core search` away.

## What we deliberately are NOT

- Not a vector database. Grep is precise, instant, inspectable, and free.
- Not a cloud service. Files on your disk; privacy by construction.
- Not a daemon. Scripts called by hooks; nothing hums in the background.
- Not model-specific. Two lines of plumbing per harness; shared state across
  all of them.

## Positioning

| Layer | Owner today | Status |
|---|---|---|
| Skinny reasoner (the core) | frontier labs | coming |
| Tools/MCP | standards bodies | shipping |
| Skills/procedures | SKILL.md standard | shipping |
| **Personal working memory** | **nobody — vendor lock-in or ad-hoc hacks** | **this repo** |

Altman bets on provider-hosted memory ("a trillion tokens of your life" on
OpenAI's servers). Karpathy bets on user-owned files ("not your weights not
your brain"). We ship the second bet, today, without waiting for the first.

## Open decision: does the brief run on a schedule?

`core brief` (v0.5) surfaces what needs you. **When it runs is unresolved,
and the honest version of this question cuts against one of our own rules.**

The constraint: *"Not a daemon. Scripts called by hooks; nothing hums in the
background."*

**Option A — hook-only (no new machinery).** The brief is computed at
SessionStart, like `core inject` today. Strictly inside the existing rule.
Cost: it can only ever tell you things at the moment you sit down. There is
no "while you were away," because nothing ran while you were away.

**Option B — one scheduled one-shot.** A launchd/cron entry runs `core brief`
once each morning and writes `~/.core/brief.md`; SessionStart reads the file.
This is what makes the Muse/dots experience possible — the brief is waiting
for you rather than computed in front of you, and it can cover the overnight
gap.

Is Option B a daemon? Arguably not: nothing resident, nothing listening, no
socket, no background process holding state. It is the same shape as the
hooks we already rely on, fired by a clock instead of by a session. But it is
the first thing in this repo that runs when the user did not ask, and that
deserves to be a stated decision rather than a quiet addition.

Resolution criteria, in order:
1. The brief must be identical whether computed at 6am or at session start.
   If a scheduled run can produce something a hook run cannot, the design is
   wrong and we take Option A.
2. No scheduled run may write anything about your projects. It may write only
   its own cached output, which is regenerable and disposable.
3. Shipping default is Option A. Option B is opt-in, one documented command
   to enable, one to remove.

## Roadmap

- v0.4: ~~standing orders~~ shipped · hash-chained tamper-evident ledgers
  `core doctor` staleness lint — SHIPPED. Remaining: provenance chain
- v0.5: `core brief` — the noticing layer. Three tiers, cheapest first:
    1. deterministic audits (git remotes, unpushed work, orphaned scheduled
       jobs, stale credentials) — shipped as a plugin directory, `audits/*.sh`,
       one script + one manifest line each. Zero tokens, cannot hallucinate,
       and the lowest-barrier place for outside contribution.
    2. closing-block extraction — mine the assistant's own formulaic
       `**Still waiting on you:**` blocks, which already carry date, owner and
       blocker, rather than inferring intent from conversation.
    3. escalation-on-repeat — the value is "this is the third time you have
       been asked," not first-time detection. Needs no model.
  · `core brief --receipts` — surfaced / acted on / dismissed / ignored over
    the last N days. The tool reports its own hit rate, so it cannot go
    quietly inert the way v0.4 did; items ignored repeatedly retire themselves.
  · rhythm stats (active-hours inference); weekly synthesis pages
- Later: optional wiki/ layer per Karpathy KB spec; qmd-style hybrid search
  escape hatch past ~500 docs; multi-machine via git-backed state

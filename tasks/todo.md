# v0.5 — `core brief`, tier 1 (deterministic audits)

Source of truth: DESIGN.md "Roadmap → v0.5" + "Open decision: does the brief run on a schedule?"
Shipping default per DESIGN.md: Option A (hook-only). Option B (launchd one-shot) is out of scope here.

## Done criteria (agreed before building)
- [ ] `core brief` runs every `audits/*.sh`, groups output, exits 0 with nothing to report.
- [ ] Each audit = one script + one manifest line; prints zero or more findings, never writes to ~/.core.
- [ ] Audit 01 `git-no-remote`: repos under configured roots with commits and no remote (count + oldest commit age).
- [ ] Audit 02 `git-unpushed`: repos with commits ahead of upstream (count + oldest age).
- [ ] Audit 03 `launchd-orphans`: loaded user LaunchAgents matching a user-listed "ended" prefix (e.g. `com.oldclient.`), with last exit status.
- [ ] Tests in tests/test_core.py use temp git repos + a stub `launchctl`; each test fails if the finding logic changes.
- [ ] Real run on this machine reproduces the numbers in README-draft-evidence.md (74 / 115 / 20-of-which-11-exit-0), or the draft gets corrected.
- [ ] Fresh-session challenger reviews before it's called done.

## Out of scope for this increment
- Tier 2 (closing-block extraction), tier 3 (repeat escalation), `--receipts`, Option B scheduling.
- Merging README-draft-evidence.md into README (holds until the brief actually runs).

## Housekeeping
- [ ] Commit the pending DESIGN.md v0.5 edits as their own commit first.
- [ ] Push to origin. Since v0.4 (8/25), nothing has been pushed.

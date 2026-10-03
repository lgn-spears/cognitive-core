"""The home screen: `core home` prints the first screen from files only — what's waiting on the person,
what was noticed, what got done, and whether background jobs are healthy. No model, no network.
Fixed clock via CORE_NOW so the whole screen is a golden string."""

import json
import os
import subprocess
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"
NOW = "2026-10-02T21:20:00-04:00"


def run(tmp_path, *args, now=NOW, extra_env=None):
    env = {"HOME": str(tmp_path / "home"), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    if now:
        env["CORE_NOW"] = now
    env.update(extra_env or {})
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def item(h, id_, source, text, at, status="pending", **kw):
    d = h / "inbox"
    d.mkdir(parents=True, exist_ok=True)
    rec = dict({"id": id_, "key": "k-" + id_, "source": source, "text": text, "at": at, "seq": int(id_[:14]),
                "status": status, "shown": 0}, **kw)
    (d / (id_ + ".json")).write_text(json.dumps(rec))


def heartbeat(h, **passes):
    (h / "heartbeat.json").write_text(json.dumps({
        name: {"status": st, "exit": 0 if st == "ok" else 1, "started": fin, "finished": fin, "last_line": last}
        for name, (st, fin, last) in passes.items()}))


def full_fixture(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir(parents=True)
    (h / "identity.md").write_text("name: Ariadne\nYou are Ariadne, Sam's agent. Same memory in every session.\n")
    (h / "recall.conf").write_text("asks_per_day 3\n")
    (h / "passes.conf").write_text("expect audits every 1d\nexpect sweep every 3h\nexpect evening every 1d\n")
    heartbeat(h, audits=("ok", "2026-10-02T08:07:12-04:00", "1 audit finding delivered"),
              sweep=("ok", "2026-10-02T20:50:03-04:00", "sweep: 1 offer(s) of 4 item(s)"),
              evening=("ok", "2026-10-02T21:03:40-04:00", "evening: wrap delivered; 1 insight offered"))
    item(h, "20261002090000-aaa111", "sweep",
         'Sweep offer (ask before saving; only on an explicit yes): [preference] "Commit messages stay plain, no '
         'emoji."; they said "never use emoji in commit messages" — 3f2a9c1b:42',
         "2026-10-02T09:00:00-04:00", kind="offer", asked="2026-10-02")
    item(h, "20261002210340-bbb222", "evening",
         "The overdue domain renewal and the unsent invoice are for the same client — one email could do both.",
         "2026-10-02T21:03:40-04:00", kind="offer", asked="2026-10-02")
    item(h, "20261002100000-ccc333", "sweep", "an offer answered this morning", "2026-10-02T10:00:00-04:00",
         status="accepted", kind="offer", asked="2026-10-02")
    item(h, "20261002205000-ddd444", "sweep", "an offer over today's cap", "2026-10-02T20:50:00-04:00",
         status="waiting", kind="offer", waiting_reason="today's ask cap is full (3 of 3)")
    item(h, "20261002080712-eee555", "audits", "2 repos have no remote: example-site, notes-app",
         "2026-10-02T08:07:12-04:00")
    item(h, "20261001231000-fff666", "run", "Nightly link check: 0 broken links across 41 pages",
         "2026-10-01T23:10:00-04:00")
    item(h, "20261002120000-ggg777", "audits", "something already seen", "2026-10-02T12:00:00-04:00",
         status="acked", acked_at="2026-10-02T12:05:00-04:00")
    with open(str(h / "offer-outcomes.jsonl"), "w") as fh:
        for at, outcome in (("2026-10-02T10:30:00-04:00", "accepted"), ("2026-10-02T11:00:00-04:00", "declined"),
                            ("2026-10-02T11:30:00-04:00", "declined"), ("2026-10-01T09:00:00-04:00", "accepted")):
            fh.write(json.dumps({"at": at, "outcome": outcome, "source": "sweep"}) + "\n")
    return h


GOLDEN = """\
Ariadne · Fri Oct 2 · 9:20 PM

WAITING ON YOU · 2 waiting

 1  Sweep offer (ask before saving; only on an explicit yes): [preference] "Commit messages
    stay plain, no emoji."; they said "never use emoji in commit messages" — 3f2a9c1b:42
    → yes · later · no · never: core offer <answer> aaa111
 2  The overdue domain renewal and the unsent invoice are for the same client — one email
    could do both.
    → yes · later · no · never: core offer <answer> bbb222
 ·  1 more ask waits for tomorrow (today's 3 are used).

NOTICED

 ·  2 repos have no remote: example-site, notes-app
    audits · 8:07 AM · core inbox ack eee555
 ·  Nightly link check: 0 broken links across 41 pages
    run · Oct 1, 11:10 PM · core inbox ack fff666

DONE TODAY

 ·  audits finished 8:07 AM: "1 audit finding delivered"
 ·  sweep finished 8:50 PM: "sweep: 1 offer(s) of 4 item(s)"
 ·  evening finished 9:03 PM: "evening: wrap delivered; 1 insight offered"
 ·  You answered 3 offers today: 1 yes, 2 no.

audits 8:07 AM · sweep 8:50 PM · evening 9:03 PM · all on time
"""


def test_full_screen_is_exact(tmp_path):
    full_fixture(tmp_path)
    r = run(tmp_path, "home")
    assert r.returncode == 0, r.stderr
    assert r.stdout == GOLDEN


def test_empty_home_says_so_in_one_line(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir(parents=True)
    (h / "passes.conf").write_text("expect audits every 1d\n")
    heartbeat(h, audits=("ok", "2026-10-02T08:07:12-04:00", "nothing to report"))
    r = run(tmp_path, "home", now="2026-10-03T07:42:00-04:00")
    assert r.stdout == "Home · Sat Oct 3 · 7:42 AM\n\nNothing needs you.\n\naudits Oct 2, 8:07 AM · all on time\n"


def test_a_brand_new_core_home_is_honest_about_having_nothing_to_check(tmp_path):
    r = run(tmp_path, "home")
    assert r.returncode == 0
    assert r.stdout == ("Home · Fri Oct 2 · 9:20 PM\n\nNothing needs you.\n\n"
                        "no background jobs to check: passes.conf expects none\n")


def test_a_broken_job_moves_to_the_top_and_replaces_the_healthy_footer(tmp_path):
    h = full_fixture(tmp_path)
    heartbeat(h, audits=("ok", "2026-10-02T08:07:12-04:00", "1 audit finding delivered"),
              sweep=("failed", "2026-10-02T20:50:00-04:00", "sweep paused — couldn't reach the extractor"),
              evening=("ok", "2026-10-02T21:03:40-04:00", "evening: wrap delivered; 1 insight offered"))
    lines = run(tmp_path, "home").stdout.splitlines()
    assert lines[1].startswith("! sweep failed 30 min ago: sweep paused")
    assert "all on time" not in "\n".join(lines)
    assert not any("sweep finished" in l for l in lines)  # a failed run isn't "done"


def test_an_item_acked_elsewhere_is_gone_on_the_next_render(tmp_path):
    full_fixture(tmp_path)
    assert "example-site" in run(tmp_path, "home").stdout
    assert run(tmp_path, "inbox", "ack", "eee555").returncode == 0  # e.g. from another session
    assert "example-site" not in run(tmp_path, "home").stdout


def test_home_is_a_view_it_marks_nothing_shown(tmp_path):
    h = full_fixture(tmp_path)
    before = {p.name: p.read_text() for p in (h / "inbox").glob("*.json")}
    run(tmp_path, "home")
    assert {p.name: p.read_text() for p in (h / "inbox").glob("*.json")} == before


def test_home_never_calls_a_model(tmp_path):
    # Even with an extractor configured, the screen comes from files: works offline, costs nothing.
    h = full_fixture(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "claude-was-called"
    (bindir / "claude").write_text("#!/bin/sh\ntouch {}\n".format(marker))
    (bindir / "claude").chmod(0o755)
    (h / "recall.conf").write_text("asks_per_day 3\nsweep_model opus\nsweep_api claude\nsweep_url http://127.0.0.1:9\n")
    r = run(tmp_path, "home", extra_env={"PATH": "{}:{}".format(bindir, os.environ["PATH"])})
    assert r.returncode == 0 and not marker.exists()


def test_without_identity_nothing_names_itself(tmp_path):
    h = full_fixture(tmp_path)
    (h / "identity.md").unlink()
    out = run(tmp_path, "home").stdout
    assert out.startswith("Home · Fri Oct 2 · 9:20 PM\n") and "Ariadne" not in out


def test_older_pending_offers_are_counted_as_waiting_not_as_todays_asks(tmp_path):
    # Two offers asked yesterday, none today: the header must not read "0 asks today" above them.
    h = tmp_path / "corehome"
    h.mkdir(parents=True)
    (h / "recall.conf").write_text("asks_per_day 1\n")
    for i, id_ in enumerate(("20261001090000-aaa111", "20261001090500-bbb222")):
        item(h, id_, "sweep", "older question {}".format(i), "2026-10-01T09:00:00-04:00", kind="offer",
             asked="2026-10-01")
    item(h, "20261002090000-ccc333", "sweep", "today's question", "2026-10-02T09:00:00-04:00", kind="offer",
         asked="2026-10-02")
    item(h, "20261002091000-ddd444", "sweep", "held question", "2026-10-02T09:10:00-04:00", status="waiting",
         kind="offer")
    out = run(tmp_path, "home").stdout
    assert "WAITING ON YOU · 3 waiting\n" in out
    assert "asks today" not in out
    assert "1 more ask waits for tomorrow (today's 1 is used)." in out

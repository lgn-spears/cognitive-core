"""core sessions: exact, model-free search over past Claude Code conversations.

Why it exists: an agent that says "we never discussed X" or guesses "what did we decide about Y" without
looking is confabulating. These tests pin down that search returns the person's and the assistant's
actual words, cited to the transcript line, and nothing the person didn't see (tool output, subagents,
core's own model calls)."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_sweep import CORE, FakeChat, assistant, chat, load_core, user, write_transcript  # noqa: F401


def projects(tmp_path):
    return tmp_path / "home" / ".claude" / "projects"


def transcript(tmp_path, project, session, entries, mtime=None):
    d = projects(tmp_path) / project
    d.mkdir(parents=True, exist_ok=True)
    p = write_transcript(d / (session + ".jsonl"), entries)
    if mtime:
        os.utime(str(p), (mtime, mtime))
    return p


def at(ts, entry):
    entry["timestamp"] = ts
    return entry


def run(tmp_path, *args):
    env = {"HOME": str(tmp_path / "home"), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    return subprocess.run([sys.executable, str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


@pytest.fixture
def two_projects(tmp_path):
    transcript(tmp_path, "-Users-x-code-shop", "aaa111", [
        at("2026-09-01T09:00:00Z", user("kick off the shop checkout work")),
        at("2026-09-01T09:01:00Z", user("let's use SQLite for the cart, Postgres is overkill here")),
        at("2026-09-01T09:01:05Z", assistant({"type": "text", "text": "Agreed, SQLite keeps it to one file."},
                                             {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}})),
        at("2026-09-01T09:02:00Z", user([{"type": "tool_result", "content": "zebrafish tool output"}])),
        at("2026-09-01T09:03:00Z", user("ship it friday")),
    ])
    transcript(tmp_path, "-Users-x-code-notes", "bbb222", [
        at("2026-09-20T15:00:00Z", user("notes app: which database?")),
        at("2026-09-20T15:00:10Z", assistant({"type": "text", "text": "SQLite again, same reasoning as the shop."})),
        at("2026-09-20T15:05:00Z", user("good, done for today")),
    ])
    return tmp_path


def test_finds_the_actual_words_cited_to_the_transcript_line(two_projects):
    tmp_path = two_projects
    assert run(tmp_path, "sessions", "index").returncode == 0
    r = run(tmp_path, "sessions", "search", "postgres overkill")
    assert r.returncode == 0, r.stderr
    assert "let's use SQLite for the cart, Postgres is overkill here" in r.stdout
    assert "~/.claude/projects/-Users-x-code-shop/aaa111.jsonl:2" in r.stdout  # the real line
    assert "bbb222" not in r.stdout  # every word must match


def test_each_hit_session_comes_with_its_opening_and_closing_words(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    out = run(tmp_path, "sessions", "search", "overkill").stdout
    assert "kick off the shop checkout work" in out  # what the session set out to do
    assert "ship it friday" in out                   # where it ended


def test_newest_first_across_sessions(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    out = run(tmp_path, "sessions", "search", "sqlite").stdout
    assert out.index("bbb222.jsonl:2") < out.index("aaa111.jsonl:2")


def test_filters_role_project_since_and_limit(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    out = run(tmp_path, "sessions", "search", "sqlite", "--role", "assistant").stdout
    assert "aaa111.jsonl:3" in out and "bbb222.jsonl:2" in out and "aaa111.jsonl:2" not in out
    out = run(tmp_path, "sessions", "search", "sqlite", "--project", "shop").stdout
    assert "aaa111" in out and "bbb222" not in out
    out = run(tmp_path, "sessions", "search", "sqlite", "--since", "2026-09-10").stdout
    assert "bbb222" in out and "aaa111" not in out
    out = run(tmp_path, "sessions", "search", "sqlite", "--limit", "1").stdout
    assert "bbb222.jsonl:2" in out and "aaa111" not in out


def test_no_matches_is_a_clean_answer_not_an_error(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    r = run(tmp_path, "sessions", "search", "kubernetes")
    assert r.returncode == 0 and "no matches" in r.stdout


def test_tool_output_is_not_conversation(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    assert "no matches" in run(tmp_path, "sessions", "search", "zebrafish").stdout


def test_search_before_any_index_says_how_to_build_one(tmp_path):
    r = run(tmp_path, "sessions", "search", "anything")
    assert r.returncode == 0 and "core sessions index" in r.stdout


def test_odd_query_syntax_never_crashes(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    for q in ['"unbalanced', "AND OR NOT", "sqlite*", "(", "col:x", "50% off_now", "-"]:
        r = run(tmp_path, "sessions", "search", q)
        assert r.returncode == 0, (q, r.stderr)


def test_quoted_phrase_is_matched_as_a_phrase(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    assert "aaa111.jsonl:2" in run(tmp_path, "sessions", "search", '"postgres is overkill"').stdout
    assert "no matches" in run(tmp_path, "sessions", "search", '"overkill postgres"').stdout


def test_index_is_incremental_and_forgets_deleted_transcripts(two_projects):
    tmp_path = two_projects
    first = run(tmp_path, "sessions", "index").stdout
    assert "2 transcript(s)" in first
    again = run(tmp_path, "sessions", "index").stdout
    assert "0 new or changed" in again  # nothing re-read
    p = projects(tmp_path) / "-Users-x-code-notes" / "bbb222.jsonl"
    with open(str(p), "a") as fh:
        fh.write(json.dumps(at("2026-09-21T10:00:00Z", user("switch the notes app to duckdb"))) + "\n")
    assert "1 new or changed" in run(tmp_path, "sessions", "index").stdout
    assert "bbb222.jsonl:4" in run(tmp_path, "sessions", "search", "duckdb").stdout
    os.unlink(str(p))
    assert "1 removed" in run(tmp_path, "sessions", "index").stdout
    assert "no matches" in run(tmp_path, "sessions", "search", "duckdb").stdout


def test_subagents_sidechains_and_cores_own_model_calls_are_not_indexed(tmp_path):
    core = load_core()
    transcript(tmp_path, "-p", "real", [user("the walrus plan is settled")])
    sub = projects(tmp_path) / "-p" / "real" / "subagents"
    sub.mkdir(parents=True)
    write_transcript(sub / "agent-1.jsonl", [user("walrus subagent chatter")])
    transcript(tmp_path, "-p", "agent-old", [user("walrus sidechain chatter", isSidechain=True)])
    transcript(tmp_path, "-p", "headless", [user(core.SWEEP_PROMPT.replace("{conversation}", "walrus"))])
    transcript(tmp_path, "-p", "judge", [user(core.JUDGE_PROMPT[:200] + " walrus")])
    run(tmp_path, "sessions", "index")
    out = run(tmp_path, "sessions", "search", "walrus").stdout
    assert "real.jsonl:1" in out
    assert "subagent" not in out and "sidechain" not in out and "headless" not in out and "judge" not in out


def test_index_is_private(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    db = tmp_path / "corehome" / "sessions.db"
    assert db.exists() and (db.stat().st_mode & 0o077) == 0


def test_works_without_fts5(two_projects, monkeypatch):
    tmp_path = two_projects
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_HOME", str(tmp_path / "corehome"))
    core = load_core()
    monkeypatch.setattr(core, "fts5_available", lambda: False)
    core.sessions_index()
    hits = core.sessions_search("postgres overkill")
    assert [(h["line"], h["role"]) for h in hits] == [(2, "user")]
    assert core.sessions_search('"postgres is overkill"') and not core.sessions_search('"overkill postgres"')
    assert core.sessions_search("50%_x") == []  # LIKE wildcards are literal
    # a database built one way is rebuilt when the other is in use, never misread
    monkeypatch.setattr(core, "fts5_available", lambda: True)
    core.sessions_index()
    assert [h["line"] for h in core.sessions_search("postgres overkill")] == [2]


def test_sweep_refreshes_the_index_without_changing_its_report(chat, tmp_path):  # noqa: F811
    p = transcript(tmp_path, "-p", "s", [user("remember the walrus plan")], mtime=time.time() - 3600)
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "recall.conf").write_text("sweep_model fake-llm\nsweep_url {}\n".format(chat))
    r = run(tmp_path, "sweep")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1].startswith("sweep:")  # the run record's last line stays the sweep's
    assert "s.jsonl:1" in run(tmp_path, "sessions", "search", "walrus").stdout
    assert p.exists()


def test_indexes_a_hundred_transcripts_in_seconds(tmp_path):
    for i in range(120):
        entries = []
        for j in range(40):
            entries.append(user("message {} in session {} about topic{}".format(j, i, j % 7)))
            entries.append(assistant({"type": "text", "text": "reply {} with some longer explanation ".format(j) * 5}))
        transcript(tmp_path, "-proj{}".format(i % 5), "s{}".format(i), entries)
    t0 = time.monotonic()
    r = run(tmp_path, "sessions", "index")
    took = time.monotonic() - t0
    assert r.returncode == 0 and "120 transcript(s)" in r.stdout
    assert took < 5, took


WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa "
         "quebec romeo sierra tango uniform victor whiskey xray yankee zulu sqlite postgres deploy invoice").split()


@pytest.mark.parametrize("fts", [True, False])
def test_search_is_fast_on_a_hundred_thousand_messages(tmp_path, monkeypatch, fts):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_HOME", str(tmp_path / "corehome"))
    core = load_core()
    monkeypatch.setattr(core, "fts5_available", lambda: fts)
    import random
    rnd = random.Random(7)
    rows = []
    for i in range(100000):
        text = " ".join(rnd.choice(WORDS) for _ in range(30))
        if i == 54321:
            text += " the needle-in-haystack walrus decision"
        rows.append(("/p/-proj{}/s{}.jsonl".format(i % 50, i // 200), i % 200 + 1, "user" if i % 2 else "assistant",
                     "2026-{:02d}-{:02d}T10:00:00Z".format(1 + i % 9, 1 + i % 28), text))
    core.sessions_load_rows(rows)
    for q, rare in (("walrus decision", True), ("sqlite", False), ("sqlite deploy", False)):
        t0 = time.monotonic()
        hits = core.sessions_search(q, limit=10)
        took = time.monotonic() - t0
        assert hits and (len(hits) == 1) == rare
        assert took < 0.2, (q, took)


# ---- fix pass: the read path never mutates, concurrency, headless runs, and edges ----

def db_of(tmp_path):
    return tmp_path / "corehome" / "sessions.db"


def test_search_never_rebuilds_or_wipes_a_stale_index(two_projects):
    """A search is a read. If the index was built by another version, wiping it from a search would destroy
    hours of indexing on a whim; the person is told to rebuild, and only `index` (holding its lock) does."""
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    con = sqlite3.connect(str(db_of(tmp_path)))
    with con:
        con.execute("UPDATE meta SET v = '0' WHERE k = 'schema'")
    before = con.execute("SELECT COUNT(*) FROM msgs").fetchone()[0]
    con.close()
    r = run(tmp_path, "sessions", "search", "sqlite")
    assert r.returncode == 2
    assert "index needs rebuild: run `core sessions index`" in r.stdout + r.stderr
    con = sqlite3.connect(str(db_of(tmp_path)))
    assert con.execute("SELECT COUNT(*) FROM msgs").fetchone()[0] == before  # untouched
    assert con.execute("SELECT v FROM meta WHERE k = 'schema'").fetchone()[0] == "0"
    con.close()
    assert run(tmp_path, "sessions", "index").returncode == 0  # the writer rebuilds
    assert "aaa111.jsonl:2" in run(tmp_path, "sessions", "search", "overkill").stdout


def test_search_while_the_index_is_being_written_still_answers(two_projects):
    """core sweep refreshes the index on a schedule; a search at that moment must not crash."""
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    con = sqlite3.connect(str(db_of(tmp_path)), isolation_level=None)
    con.execute("BEGIN EXCLUSIVE")
    con.execute("DELETE FROM msgs WHERE path LIKE '%bbb222%'")
    try:
        r = run(tmp_path, "sessions", "search", "sqlite")
    finally:
        con.execute("ROLLBACK")
        con.close()
    assert r.returncode == 0, r.stderr
    assert "aaa111.jsonl:2" in r.stdout and "bbb222.jsonl:2" in r.stdout  # the last committed state


def test_an_unreadable_index_is_one_line_not_a_traceback(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    db_of(tmp_path).write_bytes(b"this is not a database" * 100)
    r = run(tmp_path, "sessions", "search", "sqlite")
    assert r.returncode == 1
    assert "Traceback" not in r.stderr and len(r.stderr.strip().splitlines()) == 1


@pytest.fixture
def headless_and_person(tmp_path):
    transcript(tmp_path, "-p", "person", [
        at("2026-09-02T10:00:00Z", user("the narwhal migration waits for monday", entrypoint="cli")),
        at("2026-09-02T10:00:05Z", assistant({"type": "text", "text": "Noted, narwhal waits."}, entrypoint="cli")),
    ])
    transcript(tmp_path, "-p", "robot", [
        at("2026-09-03T10:00:00Z", user("Brief: implement the narwhal exporter, done when tests pass",
                                        entrypoint="sdk-cli")),
        at("2026-09-03T10:00:05Z", assistant({"type": "text", "text": "Narwhal exporter built."},
                                             entrypoint="sdk-cli")),
    ])
    return tmp_path


def test_headless_runs_are_hidden_by_default_and_their_brief_is_an_agents_words(headless_and_person):
    """An `sdk-cli` transcript's "user" turns are another agent's brief, not the person: showing them as
    something the person said would put words in their mouth."""
    tmp_path = headless_and_person
    assert run(tmp_path, "sessions", "index").returncode == 0
    out = run(tmp_path, "sessions", "search", "narwhal").stdout
    assert "person.jsonl:1" in out and "robot" not in out
    out = run(tmp_path, "sessions", "search", "narwhal", "--headless").stdout
    assert "person.jsonl:1" in out
    robot = [ln for ln in out.splitlines() if "robot.jsonl:1" in ln]
    assert robot and "  agent  " in robot[0] and "  user  " not in robot[0]
    out = run(tmp_path, "sessions", "search", "narwhal", "--headless", "--role", "user").stdout
    assert "person.jsonl:1" in out and "robot" not in out
    out = run(tmp_path, "sessions", "search", "exporter", "--headless", "--role", "agent").stdout
    assert "robot.jsonl:1" in out and "robot.jsonl:2" not in out
    con = sqlite3.connect(str(db_of(tmp_path)))
    eps = dict((Path(p).stem, e) for p, e in con.execute("SELECT path, entrypoint FROM files"))
    con.close()
    assert eps == {"person": "cli", "robot": "sdk-cli"}


def test_sweep_sources_leave_out_headless_transcripts_unless_configured(headless_and_person, monkeypatch):
    tmp_path = headless_and_person
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_HOME", str(tmp_path / "corehome"))
    core = load_core()
    assert sorted(p.stem for p in core.sweep_sources()) == ["person"]
    (tmp_path / "corehome").mkdir(exist_ok=True)
    (tmp_path / "corehome" / "recall.conf").write_text("sweep_headless on\n")
    assert sorted(p.stem for p in core.sweep_sources()) == ["person", "robot"]


def test_the_sweep_never_offers_an_agents_brief_as_the_persons_words(chat, tmp_path):  # noqa: F811
    old = time.time() - 3600
    transcript(tmp_path, "-p", "person", [user("we settled on the walrus plan", entrypoint="cli")], mtime=old)
    transcript(tmp_path, "-p", "robot", [user("Brief: build the narwhal exporter", entrypoint="sdk-cli")], mtime=old)
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "recall.conf").write_text("sweep_model fake-llm\nsweep_url {}\n".format(chat))
    assert run(tmp_path, "sweep").returncode == 0
    sent = json.dumps(FakeChat.calls)
    assert "walrus" in sent and "narwhal" not in sent
    FakeChat.calls.clear()
    (h / "recall.conf").write_text("sweep_model fake-llm\nsweep_url {}\nsweep_headless on\n".format(chat))
    assert run(tmp_path, "sweep").returncode == 0
    assert "narwhal" in json.dumps(FakeChat.calls)


def test_an_unreadable_transcript_is_retried_not_skipped_forever(two_projects):
    tmp_path = two_projects
    p = projects(tmp_path) / "-Users-x-code-shop" / "aaa111.jsonl"
    os.chmod(str(p), 0)
    try:
        run(tmp_path, "sessions", "index")
    finally:
        os.chmod(str(p), 0o644)  # same size and mtime as before: only a missing files row gets it re-read
    run(tmp_path, "sessions", "index")
    assert "aaa111.jsonl:2" in run(tmp_path, "sessions", "search", "overkill").stdout


def test_limit_must_be_at_least_one(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    for n in ("0", "-3"):
        r = run(tmp_path, "sessions", "search", "sqlite", "--limit", n)
        assert r.returncode == 2 and "--limit" in r.stderr


def test_since_must_be_a_real_date(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    for d in ("2026-02-30", "2026-13-01", "yesterday"):
        r = run(tmp_path, "sessions", "search", "sqlite", "--since", d)
        assert r.returncode == 2 and "--since" in r.stderr, d


def test_since_is_the_persons_local_midnight(tmp_path):
    """--since 2026-09-10 means from midnight on the 10th where the person is, whatever the stamp's format."""
    transcript(tmp_path, "-p", "late", [at("2026-09-10T02:00:00Z", user("otter late on the 9th, New York time"))])
    transcript(tmp_path, "-p", "early", [at("2026-09-10T05:00:00.123Z", user("otter early on the 10th"))])
    transcript(tmp_path, "-p", "offset", [at("2026-09-10T08:30:00+02:00", user("otter offset stamp on the 10th"))])
    env = {"HOME": str(tmp_path / "home"), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"],
           "TZ": "America/New_York"}
    go = lambda *a: subprocess.run([sys.executable, str(CORE), *a], capture_output=True, text=True, env=env, timeout=60)
    go("sessions", "index")
    out = go("sessions", "search", "otter", "--since", "2026-09-10").stdout
    assert "early.jsonl:1" in out and "offset.jsonl:1" in out and "late" not in out


def test_home_and_locks_are_private_whatever_the_umask(two_projects):
    tmp_path = two_projects
    env = {"HOME": str(tmp_path / "home"), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    r = subprocess.run([sys.executable, str(CORE), "sessions", "index"], capture_output=True, text=True, env=env,
                       timeout=60, preexec_fn=lambda: os.umask(0))
    assert r.returncode == 0, r.stderr
    home = tmp_path / "corehome"
    assert home.stat().st_mode & 0o777 == 0o700
    assert (home / "sessions.lock").stat().st_mode & 0o777 == 0o600
    assert (home / "sessions.db").stat().st_mode & 0o777 == 0o600


def test_a_large_reindex_leaves_the_full_text_index_merged(tmp_path, monkeypatch):
    """Each transcript commits its own FTS5 segment; after a big reindex they're merged so searches stay fast."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_HOME", str(tmp_path / "corehome"))
    core = load_core()
    if not core.fts5_available():
        pytest.skip("no FTS5")
    for i in range(core.SESSIONS_OPTIMIZE_AFTER + 5):
        transcript(tmp_path, "-p", "s{}".format(i), [user("message {} about topic{}".format(i, i % 7))])
    core.sessions_index()
    con = sqlite3.connect(str(db_of(tmp_path)))
    assert con.execute("SELECT COUNT(DISTINCT segid) FROM msgs_fts_idx").fetchone()[0] == 1
    con.close()


def test_a_failed_index_refresh_never_becomes_the_sweeps_last_line(chat, tmp_path):  # noqa: F811
    transcript(tmp_path, "-p", "s", [user("remember the walrus plan")], mtime=time.time() - 3600)
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "recall.conf").write_text("sweep_model fake-llm\nsweep_url {}\n".format(chat))
    (h / "sessions.db").mkdir()  # the refresh will fail
    env = {"HOME": str(tmp_path / "home"), "CORE_HOME": str(h), "PATH": os.environ["PATH"], "PYTHONUNBUFFERED": "1"}
    r = subprocess.run([sys.executable, str(CORE), "sweep"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, env=env, timeout=60)
    lines = r.stdout.strip().splitlines()
    assert r.returncode == 0, r.stdout
    assert any("sessions index not refreshed" in ln for ln in lines)
    assert lines[-1].startswith("sweep:")


def test_headless_bookends_say_they_are_an_agents_words(headless_and_person):
    """The began/ended lines quote the session's "user": in a headless run that's another agent, not the person."""
    tmp_path = headless_and_person
    run(tmp_path, "sessions", "index")
    out = run(tmp_path, "sessions", "search", "narwhal", "--headless").stdout
    robot = out[out.index("robot"):]
    assert "   agent began: Brief: implement the narwhal exporter" in robot
    person = out[out.index("person"):] if out.index("person") > out.index("robot") else out[:out.index("robot")]
    assert "   began: the narwhal migration waits for monday" in person and "agent began" not in person


def test_a_search_during_a_refresh_sees_the_last_finished_index(two_projects, monkeypatch):
    """A refresh commits once, at the end: a search mid-refresh gets the whole previous index, never a half-built
    one (some sessions new, some missing), and an interrupted refresh leaves the previous index as it was."""
    tmp_path = two_projects
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_HOME", str(tmp_path / "corehome"))
    core = load_core()
    core.sessions_index(quiet=True)
    for i in range(5):
        transcript(tmp_path, "-Users-x-code-shop", "new{}".format(i), [at("2026-09-21T10:00:00Z", user("walrus {}".format(i)))])
    seen, real = [], core.transcript_turns_timed

    def reading(p, strict=False):
        seen.append(len(core.sessions_search("walrus", limit=100)))
        return real(p, strict=strict)
    monkeypatch.setattr(core, "transcript_turns_timed", reading)
    core.sessions_index(quiet=True)
    assert seen and set(seen) == {0}
    assert len(core.sessions_search("walrus", limit=100)) == 5

    transcript(tmp_path, "-Users-x-code-shop", "late", [at("2026-09-22T10:00:00Z", user("walrus late"))])
    calls = []

    def dying(p, strict=False):
        calls.append(p)
        if len(calls) > 1:
            raise KeyboardInterrupt
        return real(p, strict=strict)
    monkeypatch.setattr(core, "transcript_turns_timed", dying)
    (projects(tmp_path) / "-Users-x-code-shop" / "new0.jsonl").write_text(
        json.dumps(at("2026-09-21T10:00:00Z", user("walrus changed"))) + "\n")
    with pytest.raises(KeyboardInterrupt):
        core.sessions_index(quiet=True)
    assert len(core.sessions_search("walrus", limit=100)) == 5  # all or nothing


def test_an_index_without_permission_says_so(two_projects):
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    db = db_of(tmp_path)
    os.chmod(str(db), 0o400)
    try:
        r = run(tmp_path, "sessions", "index")
        assert r.returncode == 1 and "Traceback" not in r.stderr
        assert "permission" in r.stderr.lower() and str(db.name) in r.stderr
        os.chmod(str(db), 0o000)
        r = run(tmp_path, "sessions", "search", "sqlite")
        assert r.returncode == 1 and "Traceback" not in r.stderr
        assert "permission" in r.stderr.lower() and "delete" not in r.stderr
    finally:
        os.chmod(str(db), 0o600)


def test_a_search_while_the_first_index_is_being_built_says_so(two_projects):
    """Mid-rebuild, the last committed index is the old (or empty) one: "needs rebuild" would send the person to
    start a second indexer; the truth is that one is already running."""
    import fcntl
    tmp_path = two_projects
    run(tmp_path, "sessions", "index")
    con = sqlite3.connect(str(db_of(tmp_path)))
    with con:
        con.execute("UPDATE meta SET v = '0' WHERE k = 'schema'")
    con.close()
    with open(str(tmp_path / "corehome" / "sessions.lock"), "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        r = run(tmp_path, "sessions", "search", "sqlite")
    assert r.returncode == 2 and "being rebuilt" in r.stderr and "run `core sessions index`" not in r.stderr

"""Learning silently, with undo (`learn_mode auto`).

What must hold, and why:
- The person asked "why are you asking instead of just learning as you go?". In auto mode a memory item that
  passes every existing gate AND is judged durable is saved without asking — an offer would be the old behaviour.
- Saving silently must never cost safety: the same gates run (verbatim quote, no maybes, traps, filters, novelty),
  a one-off is never saved, a known item is skipped, and a person-curated memory file is never edited.
- Every save is undoable, and an undo is remembered: the same words are never learned again, and a type that keeps
  being undone goes back to asking first.
- Silence is at most a soft signal in stats; nothing learned silently ever becomes a permission.
- The default for a new install stays `ask` (conservative public default)."""

import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from internal import deliver_internal, env_of

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"
NOW = "2026-10-05T07:42:00-04:00"


class FakeModel(BaseHTTPRequestHandler):
    """Extraction prompts get `extract`; judge prompts get judge(statement) (default: new + durable)."""
    extract = {"items": [], "traps": []}
    judge = staticmethod(lambda stmt: {"verdict": "new", "replaces": 0, "durable": True})
    calls = []
    fail_judge = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][0]["content"]
        FakeModel.calls.append(prompt)
        if "New item:" in prompt:
            if FakeModel.fail_judge:
                self.send_response(500); self.end_headers(); return
            stmt = prompt.split("New item:", 1)[1].strip().splitlines()[0].strip()
            reply = FakeModel.judge(stmt)
        else:
            reply = FakeModel.extract
        out = json.dumps({"message": {"role": "assistant", "content": json.dumps(reply)}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def model():
    FakeModel.extract = {"items": [], "traps": []}
    FakeModel.judge = staticmethod(lambda stmt: {"verdict": "new", "replaces": 0, "durable": True})
    FakeModel.calls, FakeModel.fail_judge = [], False
    srv = HTTPServer(("127.0.0.1", 0), FakeModel)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:{}".format(srv.server_port)
    srv.shutdown()


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}, "timestamp": "2026-10-05T11:30:00Z",
            "cwd": "/nowhere/code/myapp"}


def reply(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
            "timestamp": "2026-10-05T11:30:05Z"}


SAID = ["keep client emails to three sentences and then just ask",
        "never use emoji in commit messages",
        "the staging server keeps 14 days of backups",
        "make this headline one line"]


def setup(tmp_path, url, mode="auto", extra="", said=SAID, name="3f2a9c1b-sess"):
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "-nowhere-code-myapp"
    proj.mkdir(parents=True, exist_ok=True)
    t = proj / (name + ".jsonl")
    lines = []
    for s in said:
        lines += [user(s), reply("Noted.")]
    t.write_text("".join(json.dumps(l) + "\n" for l in lines))
    old = time.time() - 3600
    os.utime(str(t), (old, old))
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    conf = "sweep_model fake\nsweep_url {}\n".format(url)
    if mode:
        conf += "learn_mode {}\n".format(mode)
    (h / "recall.conf").write_text(conf + extra)
    return t


def items(*specs):
    """(type, statement, quote) → extraction items; the line is found by the gate."""
    return {"items": [{"type": t, "statement": s, "quote": q, "line": 1} for t, s, q in specs], "traps": []}


EMAILS = ("preference", "The person wants client emails kept to three sentences, then the ask.", SAID[0])
EMOJI = ("correction", "The person wants no emoji in commit messages.", SAID[1])
BACKUPS = ("fact", "The staging server keeps 14 days of backups.", SAID[2])
HEADLINE = ("correction", "The person wants this headline on one line.", SAID[3])


def env(tmp_path, now=NOW):
    return env_of(tmp_path, home=tmp_path / "home", now=now)


def run(e, *args):
    return subprocess.run([sys.executable, str(CORE), *args], capture_output=True, text=True, env=e, timeout=60)


def learned_md(tmp_path):
    p = tmp_path / "corehome" / "learned.md"
    return p.read_text() if p.exists() else ""


def entries(tmp_path):
    return [l for l in learned_md(tmp_path).splitlines() if l.startswith("- ")]


def inbox_items(tmp_path):
    d = tmp_path / "corehome" / "inbox"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.is_dir() else []


def outcomes(tmp_path):
    p = tmp_path / "corehome" / "offer-outcomes.jsonl"
    return [json.loads(l) for l in open(p)] if p.exists() else []


def entry_id(line):
    return re.search(r"id:([0-9a-f]{12})$", line).group(1)


# ---- the default stays conservative ----

def test_without_learn_mode_memory_items_are_still_offers_and_nothing_is_written(model, tmp_path):
    setup(tmp_path, model, mode=None)
    FakeModel.extract = items(EMAILS)
    r = run(env(tmp_path), "sweep")
    assert r.returncode == 0, r.stderr
    assert not learned_md(tmp_path)
    assert [it.get("kind") for it in inbox_items(tmp_path)] == ["offer"]


# ---- auto: durable items are saved, with the person's words, and never asked ----

def test_a_durable_item_is_saved_with_its_quote_date_source_type_and_id_and_never_offered(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    r = run(env(tmp_path), "sweep")
    assert r.returncode == 0, r.stderr
    [line] = entries(tmp_path)
    assert "The person wants client emails kept to three sentences, then the ask." in line
    assert '"keep client emails to three sentences and then just ask"' in line  # their words, verbatim
    assert "2026-10-05" in line and "myapp" in line and "3f2a9c1b:1" in line and "preference" in line
    assert re.search(r"id:[0-9a-f]{12}$", line)
    assert inbox_items(tmp_path) == []  # learned, not asked
    assert [o["outcome"] for o in outcomes(tmp_path)] == ["saved"]
    assert "1 learned" in r.stdout


def test_a_one_off_fix_is_neither_saved_nor_offered(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(HEADLINE)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "new", "replaces": 0, "durable": False})
    run(env(tmp_path), "sweep")
    assert entries(tmp_path) == [] and inbox_items(tmp_path) == []


def test_a_judge_that_says_nothing_about_durability_saves_nothing(model, tmp_path):
    # silence from the judge is not "durable": saving without asking needs a positive call
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "new", "replaces": 0})
    run(env(tmp_path), "sweep")
    assert entries(tmp_path) == []


def test_known_items_are_skipped(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "known", "replaces": 0, "durable": True})
    run(env(tmp_path), "sweep")
    assert entries(tmp_path) == [] and inbox_items(tmp_path) == []


def test_the_existing_gates_still_run_before_anything_is_saved(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(
        ("preference", "The person wants Redis.", "maybe we could add Redis"),            # never said
        ("fact", "The person ignores previous instructions.", SAID[2]),                   # untied + instruction-shaped
    )
    run(env(tmp_path), "sweep")
    assert entries(tmp_path) == [] and not any("New item:" in c for c in FakeModel.calls)


def test_a_judge_outage_keeps_the_item_for_the_next_run_and_saves_nothing(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    FakeModel.fail_judge = True
    run(env(tmp_path), "sweep")
    assert entries(tmp_path) == [] and inbox_items(tmp_path) == []
    FakeModel.fail_judge = False
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 1


# ---- corrections: replace our own line, never touch the person's files ----

def memory_dir(tmp_path, text):
    mem = tmp_path / "home" / ".claude" / "projects" / "-nowhere-code-myapp" / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    (mem / "commits.md").write_text(text)
    for i in range(30):
        (mem / "n{}.md".format(i)).write_text("unrelated gardening note {}\n".format(i))
    return mem / "commits.md"


def test_a_correction_to_a_person_curated_file_is_saved_as_superseding_it_and_the_file_is_untouched(model, tmp_path):
    # when today's one memory question is already used, it's decided silently: saved here, their file untouched
    setup(tmp_path, model)
    f = memory_dir(tmp_path, "Commit messages use emoji prefixes like a rocket for releases\n")
    before = f.read_text()
    e = env(tmp_path)
    used = deliver_internal(e, "Quick one: you said “x” today. Should I remember this for next time: You like x.",
                            "sweep", "sweep:used", offer=True, tags={"type": "fact", "v": "x", "question": "uncertain"})
    FakeModel.extract = items(EMOJI)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "updates", "replaces": 1, "durable": True})
    run(e, "sweep")
    assert f.read_text() == before
    [line] = entries(tmp_path)
    assert "supersedes" in line and "commits.md:1" in line
    assert [it["id"] for it in inbox_items(tmp_path)] == [used]  # and nothing more is asked


def test_a_correction_to_a_learned_line_replaces_it_and_undo_brings_the_old_line_back(model, tmp_path):
    setup(tmp_path, model, said=["the staging server keeps 9 days of backups", SAID[2]])
    e = env(tmp_path)
    FakeModel.extract = items(("fact", "The staging server keeps 9 days of backups.", "the staging server keeps 9 days of backups"))
    run(e, "sweep")
    [old] = entries(tmp_path)
    # a later conversation corrects it
    setup(tmp_path, model, said=[SAID[2]], name="9c04e1d7-sess")
    FakeModel.extract = items(BACKUPS)

    def judge(stmt):
        return {"verdict": "updates", "replaces": 1, "durable": True}
    FakeModel.judge = staticmethod(judge)
    run(e, "sweep")
    [new] = entries(tmp_path)
    assert "14 days" in new and "9 days" not in new  # replaced in place, not a second conflicting note
    r = run(e, "learned", "undo", entry_id(new))
    assert r.returncode == 0, r.stderr
    assert entries(tmp_path) == [old]


# ---- listing and undo ----

def test_learned_lists_newest_first_and_since_filters(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    run(env(tmp_path, now="2026-10-01T09:00:00-04:00"), "sweep")
    setup(tmp_path, model, name="9c04e1d7-sess")
    FakeModel.extract = items(BACKUPS)
    run(env(tmp_path), "sweep")
    out = run(env(tmp_path), "learned").stdout
    assert out.index("14 days") < out.index("three sentences")
    assert '"keep client emails' in out and "core learned undo" in out
    since = run(env(tmp_path), "learned", "--since", "2026-10-03").stdout
    assert "14 days" in since and "three sentences" not in since


def test_undo_removes_the_line_records_a_negative_signal_and_the_same_words_are_never_learned_again(model, tmp_path):
    t = setup(tmp_path, model)
    e = env(tmp_path)
    FakeModel.extract = items(EMAILS)
    run(e, "sweep")
    [line] = entries(tmp_path)
    r = run(e, "learned", "undo", entry_id(line)[:6])  # a unique fragment is enough
    assert r.returncode == 0, r.stderr
    assert entries(tmp_path) == []
    assert [o["outcome"] for o in outcomes(tmp_path)] == ["saved", "undone"]
    with open(str(t), "a") as fh:  # they say it again later; the extractor finds it again
        fh.write(json.dumps(user("keep client emails to three sentences and then just ask")) + "\n")
    old = time.time() - 3600
    os.utime(str(t), (old, old))
    run(e, "sweep")
    assert entries(tmp_path) == [] and inbox_items(tmp_path) == []


def test_undo_of_an_unknown_id_changes_nothing(model, tmp_path):
    r = run(env(tmp_path), "learned", "undo", "abcdef123456")
    assert r.returncode == 1 and "no learned" in r.stderr.lower()


def test_recall_searches_what_was_learned(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(BACKUPS)
    run(env(tmp_path), "sweep")
    r = run(env(tmp_path), "recall", "--query", "how many days of backups does the staging server keep")
    assert "learned.md" in r.stdout and "14 days" in r.stdout


# ---- rate and size ----

def test_auto_saves_are_capped_per_day_and_the_rest_wait_for_tomorrow(model, tmp_path):
    setup(tmp_path, model, extra="learn_per_day 1\n")
    FakeModel.extract = items(EMAILS, BACKUPS)
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 1 and inbox_items(tmp_path) == []
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 1  # same day: still capped
    run(env(tmp_path, now="2026-10-06T08:00:00-04:00"), "sweep")
    assert len(entries(tmp_path)) == 2


def test_over_its_size_budget_the_evening_offers_a_consolidation_once(model, tmp_path):
    setup(tmp_path, model, extra="learn_budget_kb 1\n")
    h = tmp_path / "corehome"
    (h / "learned.md").write_text("# Learned\n" + "".join(
        '- The person likes note {} a lot. — they said "note {}" · 2026-10-01 09:00 · myapp abcdefgh:{} · fact · '
        'id:{:012x}\n'.format(i, i, i, i) for i in range(40)))
    run(env(tmp_path), "evening")
    run(env(tmp_path), "evening")
    offers = [it for it in inbox_items(tmp_path) if it.get("kind") == "offer" and
              (it.get("tags") or {}).get("type") == "consolidate"]
    assert len(offers) == 1 and "budget" in offers[0]["text"]


def test_under_budget_there_is_no_consolidation_offer(model, tmp_path):
    setup(tmp_path, model)
    run(env(tmp_path), "evening")
    assert not any((it.get("tags") or {}).get("type") == "consolidate" for it in inbox_items(tmp_path))


# ---- the learning signal ----

def seed_outcomes(tmp_path, core_version, rows):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    with open(str(h / "offer-outcomes.jsonl"), "a") as fh:
        for t, o in rows:
            fh.write(json.dumps({"at": "2026-10-04T09:00:00-04:00", "source": "learned", "outcome": o,
                                 "tags": {"type": t, "v": core_version}}) + "\n")


def sweep_version():
    import importlib.machinery, importlib.util
    l = importlib.machinery.SourceFileLoader("core_v", str(CORE))
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("core_v", l)); l.exec_module(m)
    return m.SWEEP_VERSION


def test_a_type_that_keeps_being_undone_goes_back_to_asking_first(model, tmp_path):
    setup(tmp_path, model)
    seed_outcomes(tmp_path, sweep_version(), [("fact", "saved")] * 5 + [("fact", "undone")] * 3)
    FakeModel.extract = items(BACKUPS, EMAILS)
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 1 and "three sentences" in entries(tmp_path)[0]  # preferences still learned
    [offer] = inbox_items(tmp_path)
    assert offer["kind"] == "offer" and "14 days" in offer["text"]  # facts are asked again
    stats = run(env(tmp_path), "offer", "stats").stdout
    assert "fact" in stats and "asking first" in stats


def test_stats_count_kept_items_only_as_a_labelled_soft_signal(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    run(env(tmp_path, now="2026-09-20T09:00:00-04:00"), "sweep")
    stats = run(env(tmp_path), "offer", "stats").stdout
    assert "kept 7+ days: 1" in stats and "soft" in stats and "never permission" in stats


def test_silent_saves_never_lead_to_a_standing_permission_proposal(model, tmp_path):
    setup(tmp_path, model, said=SAID[:3])
    FakeModel.extract = items(("preference", "The person wants client emails short.", SAID[0]),
                              ("preference", "The person wants no emoji in commit messages.", SAID[1]),
                              ("preference", "The person likes the staging server at 14 days of backups.", SAID[2]))
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 3
    assert not any(it["source"] == "permissions" for it in inbox_items(tmp_path))
    assert run(env(tmp_path), "grant").stdout.strip() == "no standing permissions"


# ---- migration: pending memory offers re-judged under the new rules ----

def offer_text(t, stmt, quote, sess="3f2a9c1b", line=1):
    return ('Sweep offer (ask before saving; only on an explicit yes): [{}] "{}"; they said "{}" — {}:{}'
            .format(t, stmt, quote, sess, line))


def test_pending_memory_offers_are_rejudged_once_auto_is_on(model, tmp_path):
    setup(tmp_path, model, said=SAID)
    e = env(tmp_path)
    keep = deliver_internal(e, offer_text(*EMAILS), "sweep", "sweep:aaaaaaaaaaaa", offer=True,
                            tags={"type": "preference", "v": "x"})
    drop = deliver_internal(e, offer_text(*HEADLINE, line=7), "sweep", "sweep:bbbbbbbbbbbb", offer=True,
                            tags={"type": "correction", "v": "x"})
    insight = deliver_internal(e, "Two loops are about one client. (from: loop a; loop b)", "evening", "insight:x",
                               offer=True, tags={"type": "insight"})
    FakeModel.judge = staticmethod(lambda s: {"verdict": "new", "replaces": 0, "durable": "headline" not in s})
    run(e, "sweep")
    by = {it["id"]: it for it in inbox_items(tmp_path)}
    assert by[keep]["status"] == "learned"
    assert by[drop]["status"] == "superseded"
    assert by[insight]["status"] == "pending"  # insights stay offers
    [line] = entries(tmp_path)
    assert "three sentences" in line and '"keep client emails to three sentences and then just ask"' in line
    assert not any(o["outcome"] in ("declined", "never") for o in outcomes(tmp_path))  # retired is not a no


# ---- the surfaces ----

def test_home_lists_what_was_learned_with_its_undo(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    run(env(tmp_path), "sweep")
    out = run(env(tmp_path), "home").stdout
    assert "LEARNED" in out and "three sentences" in out and "core learned undo" in out


# ---- the phone page ----

@pytest.fixture
def page_server():
    from test_serve import Server
    started = []

    def start(e):
        e = dict(e, PATH="/usr/bin:/bin")  # no tailscale: loopback
        s = Server(e)
        started.append(s)
        return s
    yield start
    for s in started:
        s.stop()


def learn_two(tmp_path, url):
    setup(tmp_path, url)
    FakeModel.extract = items(EMAILS)
    run(env(tmp_path, now="2026-10-03T09:00:00-04:00"), "sweep")  # earlier this week
    setup(tmp_path, url, name="9c04e1d7-sess")
    FakeModel.extract = items(BACKUPS)
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 2


def test_the_page_leads_with_what_was_learned_in_the_persons_terms(model, tmp_path, page_server):
    learn_two(tmp_path, model)
    page = page_server(env(tmp_path)).page()
    assert '<h2 id="learned">What I Learned</h2>' in page
    assert page.index("What I Learned") < page.index("</header>") + 400  # the top section
    assert ">Today<" in page and ">Earlier This Week<" in page
    assert page.index("14 days") < page.index("three sentences")  # today first
    assert "You want client emails kept to three sentences, then the ask." in page  # speaks to the person
    assert "“keep client emails to three sentences and then just ask”" in page
    assert page.count(">Undo<") == 2
    assert "Learned 1 thing today." in page and "Nothing needs you." in page
    assert "Needs You" not in page  # nothing to answer: no empty section


def test_the_headline_counts_what_was_learned_and_what_really_needs_the_person(model, tmp_path, page_server):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS, BACKUPS)
    e = env(tmp_path)
    run(e, "sweep")
    deliver_internal(e, "Two loops are about one client. (from: loop a; loop b)", "evening", "insight:x",
                     offer=True, tags={"type": "insight"})
    page = page_server(e).page()
    assert "Learned 2 things today." in page and "One thing needs you." in page
    assert '<h2 id="needs">Needs You</h2>' in page
    assert page.index("What I Learned") < page.index("Needs You")


def test_undo_from_the_page_takes_it_back_and_needs_a_rendered_nonce(model, tmp_path, page_server):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS)
    e = env(tmp_path)
    run(e, "sweep")
    [line] = entries(tmp_path)
    eid = entry_id(line)
    s = page_server(e)
    status, _, _ = s.request("POST", "/{}/learned/{}".format(s.token, eid), "answer=undo&nonce=forged",
                             {"Accept": "application/json"})
    assert status == 409 and len(entries(tmp_path)) == 1
    n = s.nonce()
    status, _, body = s.request("POST", "/{}/learned/{}".format(s.token, eid),
                                "answer=undo&nonce={}".format(n), {"Accept": "application/json"})
    assert status == 200 and json.loads(body)["ok"], body
    assert entries(tmp_path) == []
    assert [o["outcome"] for o in outcomes(tmp_path)] == ["saved", "undone"]
    status, hdr, _ = s.request("POST", "/{}/learned/{}".format(s.token, eid), "answer=undo&nonce={}".format(n))
    assert status == 303  # already gone: back to the page, nothing else changes
    assert "Undo" not in s.page().split("</header>", 1)[1].split("<script", 1)[0]


def test_without_auto_the_page_has_no_learned_section(model, tmp_path, page_server):
    setup(tmp_path, model, mode=None)
    FakeModel.extract = items(EMAILS)
    run(env(tmp_path), "sweep")
    page = page_server(env(tmp_path)).page()
    assert "What I Learned" not in page and "One thing needs you." in page


def test_a_consolidation_offer_is_answered_on_the_mac_not_the_phone(model, tmp_path, page_server):
    setup(tmp_path, model, extra="learn_budget_kb 1\n")
    (tmp_path / "corehome" / "learned.md").write_text("# Learned\n" + "x" * 3000 + "\n")
    run(env(tmp_path), "evening")
    page = page_server(env(tmp_path)).page()
    assert "Answer On Your Mac" in page and "budget" in page


def test_a_type_sent_back_to_asking_is_explained_on_the_page(model, tmp_path, page_server):
    setup(tmp_path, model)
    seed_outcomes(tmp_path, sweep_version(), [("fact", "saved")] * 4 + [("fact", "undone")] * 3)
    page = page_server(env(tmp_path)).page()
    assert "You undid 3 of the 4 facts I saved, so I&#x27;ll ask before saving facts now." in page


# ---- the one memory question a day: only when core genuinely can't decide alone ----

def questions(tmp_path):
    return [it for it in inbox_items(tmp_path) if (it.get("tags") or {}).get("question")]


def test_ordinary_items_never_become_questions(model, tmp_path):
    setup(tmp_path, model)
    FakeModel.extract = items(EMAILS, BACKUPS, HEADLINE)
    verdicts = {"three sentences": {"verdict": "new", "durable": True, "stakes": "high"},     # saved
                "14 days": {"verdict": "new", "durable": "unsure", "stakes": "low"},       # unsure but cheap: dropped
                "headline": {"verdict": "new", "durable": False, "stakes": "high"}}          # a one-off: dropped
    FakeModel.judge = staticmethod(lambda s: next(v for k, v in verdicts.items() if k in s))
    run(env(tmp_path), "sweep")
    assert len(entries(tmp_path)) == 1 and inbox_items(tmp_path) == []


def test_a_correction_to_a_curated_note_is_asked_like_a_person_would_and_a_yes_saves_it(model, tmp_path):
    setup(tmp_path, model)
    f = memory_dir(tmp_path, "Commit messages use emoji prefixes like a rocket for releases\n")
    before = f.read_text()
    FakeModel.extract = items(EMOJI)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "updates", "replaces": 1, "durable": True, "stakes": "low"})
    e = env(tmp_path)
    run(e, "sweep")
    [q] = questions(tmp_path)
    assert entries(tmp_path) == []  # asked, not saved
    assert q["kind"] == "offer" and q["text"].startswith("Quick one: you said “never use emoji in commit messages”")
    assert "your notes say “Commit messages use emoji prefixes" in q["text"] and q["text"].endswith("Which is right now?")
    r = run(e, "offer", "yes", q["id"])
    assert r.returncode == 0, r.stderr
    [line] = entries(tmp_path)
    assert "supersedes" in line and "commits.md:1" in line and f.read_text() == before


def test_at_most_one_memory_question_a_day_the_rest_are_decided_or_wait(model, tmp_path):
    setup(tmp_path, model)
    memory_dir(tmp_path, "Commit messages use emoji prefixes like a rocket for releases\n"
                         "Client emails are long and detailed with full context\n")
    FakeModel.extract = items(EMOJI, EMAILS, BACKUPS)
    FakeModel.judge = staticmethod(lambda s: (
        {"verdict": "updates", "replaces": 1, "durable": True} if "emoji" in s else
        {"verdict": "updates", "replaces": 1, "durable": True} if "three sentences" in s else
        {"verdict": "new", "durable": "unsure", "stakes": "high"}))
    run(env(tmp_path), "sweep")
    assert len(questions(tmp_path)) == 1  # one question; the other correction is saved as superseding
    assert len(entries(tmp_path)) == 1 and "supersedes" in entries(tmp_path)[0]
    run(env(tmp_path), "sweep")
    assert len(questions(tmp_path)) == 1  # same day: the uncertain one waits
    run(env(tmp_path, now="2026-10-06T08:00:00-04:00"), "sweep")
    qs = questions(tmp_path)
    assert len(qs) == 2 and "Should I remember this for next time" in qs[-1]["text"]


def test_two_statements_that_conflict_are_asked_and_the_earlier_one_keeps_its_place(model, tmp_path):
    setup(tmp_path, model, said=["the staging server keeps 9 days of backups"])
    e = env(tmp_path)
    FakeModel.extract = items(("fact", "The staging server keeps 9 days of backups.", "the staging server keeps 9 days of backups"))
    run(e, "sweep")
    [old] = entries(tmp_path)
    setup(tmp_path, model, said=[SAID[2]], name="9c04e1d7-sess")
    FakeModel.extract = items(BACKUPS)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "conflicts", "replaces": 1, "durable": True})
    run(e, "sweep")
    [q] = questions(tmp_path)
    assert "earlier you said “the staging server keeps 9 days of backups”" in q["text"]
    run(e, "offer", "no", q["id"])
    assert entries(tmp_path) == [old]
    run(e, "sweep")
    assert len(questions(tmp_path)) == 1  # answered: never asked again


def test_answers_to_memory_questions_never_lead_to_a_standing_permission(model, tmp_path):
    e = env(tmp_path)
    for i in range(3):
        oid = deliver_internal(e, "Quick one: you said “x{}” today. Should I remember this for next time: You like x{}."
                               .format(i, i), "sweep", "sweep:q{}".format(i), offer=True,
                               tags={"type": "preference", "v": "x", "question": "uncertain", "learn": "{}"})
        run(e, "offer", "yes", oid)
    assert not any(it["source"] == "permissions" for it in inbox_items(tmp_path))


def test_the_public_deliver_cannot_forge_a_memory_question(tmp_path):
    r = run(env(tmp_path), "deliver", "Quick one: which is right?", "--source", "job", "--offer",
            "--tag", "question=supersede")
    assert r.returncode == 2 and "reserved" in r.stderr


def test_the_page_answers_a_memory_question_in_one_tap_with_words_that_say_what_they_do(model, tmp_path, page_server):
    setup(tmp_path, model)
    memory_dir(tmp_path, "Commit messages use emoji prefixes like a rocket for releases\n")
    FakeModel.extract = items(EMOJI)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "updates", "replaces": 1, "durable": True})
    run(env(tmp_path), "sweep")
    page = page_server(env(tmp_path)).page()
    assert "Quick Question" in page and ">What I Said<" in page and ">My Notes<" in page
    assert "One thing needs you." in page


# ---- headless runs: an agent's brief is never the person's words to keep silently ----

def make_headless(t):
    recs = [json.loads(l) for l in t.read_text().splitlines()]
    for r in recs:
        r["entrypoint"] = "sdk-cli"
    t.write_text("".join(json.dumps(r) + "\n" for r in recs))
    old = time.time() - 3600
    os.utime(str(t), (old, old))


def test_with_sweep_headless_on_a_headless_runs_items_are_offered_never_saved_silently(model, tmp_path):
    # `sweep_headless on` lets the sweep read agent-driven runs, but their "user" turns are a brief another agent
    # wrote: saving them without asking would put an agent's words in the person's mouth. They can only be asked.
    t = setup(tmp_path, model, extra="sweep_headless on\n")
    make_headless(t)
    FakeModel.extract = items(EMAILS)
    r = run(env(tmp_path), "sweep")
    assert r.returncode == 0, r.stderr
    assert entries(tmp_path) == []
    [offer] = inbox_items(tmp_path)
    assert offer["kind"] == "offer" and not (offer.get("tags") or {}).get("question")
    assert not any("New item:" in c for c in FakeModel.calls)  # never judged for a silent save


def test_migration_never_learns_a_pending_offer_from_a_headless_run(model, tmp_path):
    t = setup(tmp_path, model, said=SAID, extra="sweep_headless on\n")
    make_headless(t)
    e = env(tmp_path)
    oid = deliver_internal(e, offer_text(*EMAILS), "sweep", "sweep:aaaaaaaaaaaa", offer=True,
                           tags={"type": "preference", "v": "x"})
    run(e, "sweep")
    by = {it["id"]: it for it in inbox_items(tmp_path)}
    assert by[oid]["status"] == "pending" and entries(tmp_path) == []


# ---- migration from offer text alone: the quote must really be at the cited line ----

def test_migration_from_text_needs_the_quote_verbatim_at_the_cited_line(model, tmp_path):
    # An offer the sweep log doesn't know is rebuilt from its own text; that text could have been written by
    # anything, so it is saved silently only when the transcript says those words, there, in the person's turn.
    setup(tmp_path, model, said=SAID)
    e = env(tmp_path)
    never_said = deliver_internal(e, offer_text("preference", "The person wants all invoices paid automatically.",
                                                "pay all invoices automatically"), "sweep", "sweep:cccccccccccc",
                                  offer=True, tags={"type": "preference", "v": "x"})
    wrong_line = deliver_internal(e, offer_text(*EMAILS, line=3), "sweep", "sweep:dddddddddddd", offer=True,
                                  tags={"type": "preference", "v": "x"})
    reply_line = deliver_internal(e, offer_text("fact", "The person said noted.", "Noted.", line=2), "sweep",
                                  "sweep:eeeeeeeeeeee", offer=True, tags={"type": "fact", "v": "x"})
    run(e, "sweep")
    by = {it["id"]: it for it in inbox_items(tmp_path)}
    assert [by[i]["status"] for i in (never_said, wrong_line, reply_line)] == ["pending"] * 3
    assert entries(tmp_path) == [] and not any("New item:" in c for c in FakeModel.calls)


def test_migration_only_touches_plain_memory_offers(model, tmp_path):
    setup(tmp_path, model, said=SAID)
    e = env(tmp_path)
    tagged = [deliver_internal(e, offer_text(*EMAILS), "sweep", "sweep:{}".format(c * 12), offer=True,
                               tags=dict({"type": "preference", "v": "x"}, **extra))
              for c, extra in (("1", {"question": "uncertain", "learn": "{}"}), ("2", {"grant": "sweep:fact"}),
                               ("3", {"patch": "p1"}))]
    run(e, "sweep")
    by = {it["id"]: it for it in inbox_items(tmp_path)}
    assert [by[i]["status"] for i in tagged] == ["pending"] * 3 and entries(tmp_path) == []


# ---- learn_file never points into the person's curated memory ----

def test_a_learn_file_inside_a_memory_directory_is_refused_and_the_note_is_untouched(model, tmp_path):
    setup(tmp_path, model)
    f = memory_dir(tmp_path, "My own note\n")
    conf = tmp_path / "corehome" / "recall.conf"
    conf.write_text(conf.read_text() + "learn_file {}\n".format(f))
    FakeModel.extract = items(EMAILS)
    r = run(env(tmp_path), "sweep")
    assert r.returncode == 2 and "learn_file" in r.stderr and "memory" in r.stderr
    assert f.read_text() == "My own note\n"
    other = f.parent / "learned-by-core.md"  # a new file in that directory is still the person's curated memory
    conf.write_text(conf.read_text() + "learn_file {}\n".format(other))
    r = run(env(tmp_path), "sweep")
    assert r.returncode == 2 and not other.exists()
    r = run(env(tmp_path), "learned", "undo", "abcdef123456")
    assert r.returncode != 0 and "learn_file" in r.stderr


# ---- after a consolidation, undo never brings back text the consolidation retired ----

def test_undo_after_a_consolidation_rewrote_the_entry_removes_it_without_restoring_stale_text(model, tmp_path):
    setup(tmp_path, model, said=["the staging server keeps 9 days of backups", SAID[2]])
    e = env(tmp_path)
    FakeModel.extract = items(("fact", "The staging server keeps 9 days of backups.",
                               "the staging server keeps 9 days of backups"))
    run(e, "sweep")
    setup(tmp_path, model, said=[SAID[2]], name="9c04e1d7-sess")
    FakeModel.extract = items(BACKUPS)
    FakeModel.judge = staticmethod(lambda s: {"verdict": "updates", "replaces": 1, "durable": True})
    run(e, "sweep")
    [new] = entries(tmp_path)
    # the agent consolidates on a yes: merges the entry's statement, keeping its quote, date and id
    md = tmp_path / "corehome" / "learned.md"
    merged = new.replace("The staging server keeps 14 days of backups.",
                         "The staging server keeps 14 days of backups, nightly.")
    md.write_text(md.read_text().replace(new, merged))
    r = run(e, "learned", "undo", entry_id(new))
    assert r.returncode == 0, r.stderr
    assert entries(tmp_path) == []  # removed; the 9-day line it once replaced is not resurrected
    assert "earlier note is back" not in r.stdout

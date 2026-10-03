"""Step 5: offer lifecycle — every offer ends accepted, declined, deferred or never; silence is not an answer."""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from internal import deliver_internal, env_of

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


def run(tmp_path, *args, stdin=None):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    return subprocess.run(["python3", str(CORE), *args], input=stdin, capture_output=True, text=True, env=env, timeout=60)


def offer(tmp_path, text="Save to memory? [preference] Plain commit messages.", key="sweep:abc"):
    return deliver_internal(env_of(tmp_path), text, "sweep", key, offer=True)  # as the sweep delivers its offers


def outcomes(tmp_path):
    p = tmp_path / "corehome" / "offer-outcomes.jsonl"
    return [json.loads(l) for l in open(p)] if p.exists() else []


def test_offer_is_rendered_with_its_answer_commands(tmp_path):
    oid = offer(tmp_path)
    out = run(tmp_path, "recall", stdin=json.dumps({"prompt": "ok"})).stdout
    assert oid in out and "core offer yes|no|later|never" in out


def test_yes_and_no_are_recorded_and_close_the_offer(tmp_path):
    a, b = offer(tmp_path, key="k1"), offer(tmp_path, "another offer text here", key="k2")
    assert run(tmp_path, "offer", "yes", a).returncode == 0
    assert run(tmp_path, "offer", "no", b, "--note", "one-off fix").returncode == 0
    got = {o["id"]: o for o in outcomes(tmp_path)}
    assert got[a]["outcome"] == "accepted" and got[b]["outcome"] == "declined" and got[b]["note"] == "one-off fix"
    assert "inbox empty" in run(tmp_path, "inbox").stdout


def test_later_hides_the_offer_then_brings_it_back(tmp_path):
    oid = offer(tmp_path)
    run(tmp_path, "offer", "later", oid)
    assert oid not in run(tmp_path, "inbox").stdout
    item = tmp_path / "corehome" / "inbox" / (oid + ".json")
    d = json.loads(item.read_text())
    d["until"] = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    item.write_text(json.dumps(d))
    assert oid in run(tmp_path, "inbox").stdout  # back after the deferral
    assert outcomes(tmp_path)[-1]["outcome"] == "deferred"


def test_never_means_the_same_offer_never_returns(tmp_path):
    oid = offer(tmp_path, key="sweep:same")
    run(tmp_path, "offer", "never", oid)
    again = offer(tmp_path, key="sweep:same")
    assert again == oid or "inbox empty" in run(tmp_path, "inbox").stdout
    assert outcomes(tmp_path)[-1]["outcome"] == "never"


def shown_days_ago(tmp_path, oid, days):
    """The offer was put in front of the person `days` ago (the expiry clock runs from the first show)."""
    item = tmp_path / "corehome" / "inbox" / (oid + ".json")
    d = json.loads(item.read_text())
    d["shown"] = max(1, d.get("shown", 0))
    d["first_shown_at"] = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    item.write_text(json.dumps(d))


def test_silence_is_not_an_answer(tmp_path):
    # An offer nobody answers expires a week after it was first shown, logged as unanswered — never yes or no.
    oid = offer(tmp_path)
    shown_days_ago(tmp_path, oid, 8)
    assert "inbox empty" in run(tmp_path, "inbox").stdout
    o = outcomes(tmp_path)[-1]
    assert o["outcome"] == "unanswered" and o["id"] == oid


def test_answering_twice_or_a_non_offer_is_refused(tmp_path):
    oid = offer(tmp_path)
    run(tmp_path, "offer", "yes", oid)
    assert run(tmp_path, "offer", "no", oid).returncode != 0
    plain = run(tmp_path, "deliver", "a report", "--source", "job").stdout.strip()
    assert run(tmp_path, "offer", "yes", plain).returncode != 0
    assert len(outcomes(tmp_path)) == 1


def test_stats_count_only_real_answers(tmp_path):
    ids = [offer(tmp_path, "offer number {} text".format(i), key="k{}".format(i)) for i in range(4)]
    for oid, ans in zip(ids, ("yes", "no", "no", "later")):
        run(tmp_path, "offer", ans, oid)
    out = run(tmp_path, "offer", "stats").stdout
    assert "1 yes" in out and "2 no" in out and "1 later" in out and "33%" in out  # later isn't a no


def test_offers_carry_their_type_into_outcomes(tmp_path):
    oid = run(tmp_path, "deliver", "offer text here", "--source", "notes", "--key", "t1", "--offer", "--tag", "type=fact").stdout.strip()
    run(tmp_path, "offer", "no", oid)
    assert outcomes(tmp_path)[-1]["tags"] == {"type": "fact"}


def test_learning_ranks_by_acceptance_and_pauses_a_rejected_type():
    import importlib.machinery, importlib.util
    l = importlib.machinery.SourceFileLoader("core", str(CORE))
    core = importlib.util.module_from_spec(importlib.util.spec_from_loader("core", l)); l.exec_module(core)
    rows = ([{"source": "sweep", "outcome": "declined", "tags": {"type": "correction"}}] * 6
            + [{"source": "sweep", "outcome": "accepted", "tags": {"type": "preference"}}] * 3
            + [{"source": "sweep", "outcome": "deferred", "tags": {"type": "fact"}}] * 5      # not answers
            + [{"source": "sweep", "outcome": "unanswered", "tags": {"type": "fact"}}] * 5)
    learned = core.learn_offer_types(rows)
    assert learned["correction"]["paused"] and not learned["preference"]["paused"]
    assert learned["preference"]["score"] > learned["fact"]["score"] > learned["correction"]["score"]
    assert learned["fact"]["answered"] == 0  # silence and "later" teach nothing


def test_only_the_current_extractor_version_can_pause_a_type():
    import importlib.machinery, importlib.util
    l = importlib.machinery.SourceFileLoader("core", str(CORE))
    core = importlib.util.module_from_spec(importlib.util.spec_from_loader("core", l)); l.exec_module(core)
    old = [{"outcome": "declined", "tags": {"type": "correction", "v": "old"}}] * 8
    assert not core.learn_offer_types(old, version="new").get("correction", {}).get("paused")
    assert core.learn_offer_types(old)["correction"]["paused"]


# ---- GLM review fixes ----

def test_parallel_readers_log_an_expiry_once(tmp_path):
    (tmp_path / "corehome").mkdir()
    (tmp_path / "corehome" / "recall.conf").write_text("asks_per_day 20\n")  # this test is about expiry, not the cap
    ids = [offer(tmp_path, "offer {} text".format(i), key="e{}".format(i)) for i in range(10)]
    for oid in ids:
        shown_days_ago(tmp_path, oid, 8)
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    procs = [subprocess.Popen(["python3", str(CORE), "inbox"], env=env, stdout=subprocess.DEVNULL) for _ in range(12)]
    for p in procs:
        p.wait()
    rows = [o for o in outcomes(tmp_path) if o["outcome"] == "unanswered"]
    assert len(rows) == 10 and len({o["id"] for o in rows}) == 10


def test_ack_refuses_an_offer(tmp_path):
    oid = offer(tmp_path)
    r = run(tmp_path, "inbox", "ack", oid)
    assert r.returncode != 0 and "core offer" in r.stderr
    assert oid in run(tmp_path, "inbox").stdout


def test_later_restarts_the_week(tmp_path):
    oid = offer(tmp_path)
    p = tmp_path / "corehome" / "inbox" / (oid + ".json")
    shown_days_ago(tmp_path, oid, 6)
    run(tmp_path, "offer", "later", oid)
    d = json.loads(p.read_text()); d["until"] = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    p.write_text(json.dumps(d))
    assert oid in run(tmp_path, "inbox").stdout  # asked again, not expired
    assert "first_shown_at" not in json.loads(p.read_text())  # its new week starts when it is shown again


def test_stats_survive_a_bad_line(tmp_path):
    a = offer(tmp_path, key="s1")
    run(tmp_path, "offer", "yes", a)
    with open(str(tmp_path / "corehome" / "offer-outcomes.jsonl"), "a") as fh:
        fh.write("garbage\n{\"id\": \"x\"}\n")
    r = run(tmp_path, "offer", "stats")
    assert r.returncode == 0 and "1 yes" in r.stdout


def test_offer_upgrades_a_plain_item_with_the_same_key(tmp_path):
    plain = run(tmp_path, "deliver", "a report", "--source", "notes", "--key", "same").stdout.strip()
    again = run(tmp_path, "deliver", "a report", "--source", "notes", "--key", "same", "--offer").stdout.strip()
    assert again == plain and run(tmp_path, "offer", "yes", again).returncode == 0


# ---- whole-branch review fixes ----

def recall(tmp_path, prompt="ok"):
    return run(tmp_path, "recall", stdin=json.dumps({"prompt": prompt})).stdout


def test_an_offer_never_shown_never_expires(tmp_path):
    # A quiet week (no sessions) must not turn an offer into "unanswered": nobody was asked.
    oid = offer(tmp_path)
    item = tmp_path / "corehome" / "inbox" / (oid + ".json")
    d = json.loads(item.read_text())
    d["at"] = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    item.write_text(json.dumps(d))
    assert oid in run(tmp_path, "inbox").stdout
    assert outcomes(tmp_path) == []


def test_the_week_starts_at_the_first_show(tmp_path):
    oid = offer(tmp_path)
    item = tmp_path / "corehome" / "inbox" / (oid + ".json")
    d = json.loads(item.read_text())
    d["at"] = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    item.write_text(json.dumps(d))
    assert oid in recall(tmp_path)                    # shown now: the clock starts here
    first = json.loads(item.read_text())["first_shown_at"]
    recall(tmp_path)
    assert json.loads(item.read_text())["first_shown_at"] == first  # later shows don't restart it
    assert oid in run(tmp_path, "inbox").stdout       # 30 days old, but shown seconds ago
    shown_days_ago(tmp_path, oid, 8)
    assert "inbox empty" in run(tmp_path, "inbox").stdout
    assert outcomes(tmp_path)[-1]["outcome"] == "unanswered"


def test_offers_are_listed_before_reports(tmp_path):
    for i in range(4):
        run(tmp_path, "deliver", "report {} text".format(i), "--source", "job", "--key", "r{}".format(i))
    oid = offer(tmp_path)
    out = recall(tmp_path)
    assert oid in out  # four reports can't push the question out of the top three
    lines = [l for l in out.splitlines() if l.startswith("  [")]
    assert oid in lines[0]


def test_a_late_answer_to_an_expired_offer_is_kept(tmp_path):
    oid = offer(tmp_path)
    shown_days_ago(tmp_path, oid, 8)
    run(tmp_path, "inbox")  # expires it
    r = run(tmp_path, "offer", "yes", oid)
    assert r.returncode == 0, r.stderr
    last = outcomes(tmp_path)[-1]
    assert last["outcome"] == "accepted" and last["late"] is True and last["id"] == oid
    assert json.loads((tmp_path / "corehome" / "inbox" / (oid + ".json")).read_text())["status"] == "accepted"


def test_unknown_and_already_answered_ids_get_clear_messages(tmp_path):
    r = run(tmp_path, "offer", "yes", "20990101000000-abcdef")
    assert r.returncode != 0 and "no offer with id 20990101000000-abcdef" in r.stderr
    oid = offer(tmp_path)
    run(tmp_path, "offer", "no", oid)
    r = run(tmp_path, "offer", "yes", oid)
    assert r.returncode != 0 and "already answered (declined)" in r.stderr


def test_offers_are_not_repeated_on_every_message(tmp_path):
    # Shown at the first message, then quiet, then asked again once per OFFER_REASK_EVERY messages.
    oid = offer(tmp_path)
    seen = ["OFFERS:" in recall(tmp_path) for _ in range(21)]
    assert seen[0] and seen[10] and seen[20]
    assert sum(seen) == 3
    report = run(tmp_path, "deliver", "a report", "--source", "job").stdout.strip()
    assert report in recall(tmp_path)  # reports aren't throttled


def test_session_start_always_shows_offers(tmp_path):
    oid = offer(tmp_path)
    recall(tmp_path)
    assert oid not in recall(tmp_path)
    assert oid in run(tmp_path, "inject").stdout

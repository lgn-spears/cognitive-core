"""Step 5: offer lifecycle — every offer ends accepted, declined, deferred or never; silence is not an answer."""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


def run(tmp_path, *args, stdin=None):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    return subprocess.run(["python3", str(CORE), *args], input=stdin, capture_output=True, text=True, env=env, timeout=60)


def offer(tmp_path, text="Save to memory? [preference] Plain commit messages.", key="sweep:abc"):
    return run(tmp_path, "deliver", text, "--source", "sweep", "--key", key, "--offer").stdout.strip()


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


def test_silence_is_not_an_answer(tmp_path):
    # An offer nobody answers expires after a week, logged as unanswered — never as yes or no.
    oid = offer(tmp_path)
    item = tmp_path / "corehome" / "inbox" / (oid + ".json")
    d = json.loads(item.read_text())
    d["at"] = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
    item.write_text(json.dumps(d))
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

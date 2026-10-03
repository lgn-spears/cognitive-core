"""One daily ask budget across every producer (sweep, evening, grant proposals, `core deliver --offer`).
Muse: a few asks a day at most, across every surface. Overflow waits — persisted, never dropped — and
re-enters on a day with free slots; a held ask that goes a week without a slot dies quietly."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from internal import deliver_internal, env_of

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"
DAY1 = "2026-10-02T10:00:00-04:00"
DAY2 = "2026-10-03T10:00:00-04:00"


def run(tmp_path, *args, now=DAY1):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"],
           "CORE_NOW": now}
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def conf(tmp_path, text):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    (h / "recall.conf").write_text(text)


def offer(tmp_path, n, now=DAY1, source="sweep"):
    """An ask from `source`: core's own producers deliver internally; any other source is a `core deliver --offer`."""
    text, key = "offer number {} text".format(n), "k{}".format(n)
    if source in ("sweep", "evening"):
        iid = deliver_internal(env_of(tmp_path, now=now), text, source, key, offer=True)
        return subprocess.CompletedProcess([], 0, iid + "\n", "")
    return run(tmp_path, "deliver", text, "--source", source, "--key", key, "--offer", now=now)


def statuses(tmp_path):
    d = tmp_path / "corehome" / "inbox"
    return {json.loads(p.read_text())["key"]: json.loads(p.read_text()) for p in d.glob("*.json")}


def test_seven_asks_in_a_day_deliver_five_and_hold_two_with_a_reason(tmp_path):
    for i in range(7):
        r = offer(tmp_path, i, source="ci")  # `core deliver --offer`: its stderr says why an ask is held
        assert r.returncode == 0
    st = statuses(tmp_path)
    assert [st["k{}".format(i)]["status"] for i in range(7)] == ["pending"] * 5 + ["waiting"] * 2
    assert "today's ask cap is full (5 of 5)" in st["k6"]["waiting_reason"]
    assert "ask cap" in r.stderr  # the producer is told, not silently ignored
    out = run(tmp_path, "inbox").stdout
    assert "offer number 4" in out and "offer number 5" not in out  # held asks aren't shown yet


def test_held_asks_reenter_the_next_day(tmp_path):
    for i in range(7):
        offer(tmp_path, i)
    out = run(tmp_path, "inbox", now=DAY2).stdout
    assert "offer number 5" in out and "offer number 6" in out
    st = statuses(tmp_path)
    assert st["k5"]["asked"] == "2026-10-03" and st["k5"]["at"].startswith("2026-10-03")  # a fresh week to answer


def test_a_held_ask_cannot_be_answered_before_it_is_asked(tmp_path):
    for i in range(6):
        offer(tmp_path, i)
    held = statuses(tmp_path)["k5"]["id"]
    assert run(tmp_path, "offer", "yes", held).returncode != 0


def test_a_stale_held_ask_dies_quietly(tmp_path):
    conf(tmp_path, "asks_per_day 0\n")
    offer(tmp_path, 1)
    run(tmp_path, "inbox", now="2026-10-10T10:00:00-04:00")
    assert statuses(tmp_path)["k1"]["status"] == "stale"
    assert not (tmp_path / "corehome" / "offer-outcomes.jsonl").exists()  # never asked: not an "unanswered"


def test_answered_asks_still_count_against_today(tmp_path):
    conf(tmp_path, "asks_per_day 2\n")
    a = offer(tmp_path, 1).stdout.strip()
    run(tmp_path, "offer", "no", a)
    offer(tmp_path, 2)
    offer(tmp_path, 3)
    assert statuses(tmp_path)["k3"]["status"] == "waiting"


def test_the_cap_is_shared_across_producers(tmp_path):
    conf(tmp_path, "asks_per_day 2\n")
    offer(tmp_path, 1, source="sweep")
    offer(tmp_path, 2, source="evening")
    offer(tmp_path, 3, source="theseus")
    assert statuses(tmp_path)["k3"]["status"] == "waiting"


def test_sweep_offers_per_day_still_works_as_the_cap(tmp_path):
    conf(tmp_path, "sweep_offers_per_day 1\n")  # older configs keep their limit, now for every producer
    offer(tmp_path, 1)
    offer(tmp_path, 2, source="evening")
    assert statuses(tmp_path)["k2"]["status"] == "waiting"


def test_asks_per_day_wins_over_the_old_name(tmp_path):
    conf(tmp_path, "sweep_offers_per_day 1\nasks_per_day 3\n")
    for i in range(3):
        offer(tmp_path, i)
    assert all(v["status"] == "pending" for v in statuses(tmp_path).values())


def test_plain_reports_are_not_asks(tmp_path):
    conf(tmp_path, "asks_per_day 1\n")
    offer(tmp_path, 1)
    r = run(tmp_path, "deliver", "3 repos have no remote", "--source", "audits")
    assert r.returncode == 0 and "3 repos have no remote" in run(tmp_path, "inbox").stdout


def test_a_repeated_held_ask_is_one_item(tmp_path):
    conf(tmp_path, "asks_per_day 0\n")
    a, b = offer(tmp_path, 1).stdout.strip(), offer(tmp_path, 1).stdout.strip()
    assert a == b and len(statuses(tmp_path)) == 1


class Fake(BaseHTTPRequestHandler):
    reply = {"offer": None}

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        out = json.dumps({"message": {"role": "assistant", "content": json.dumps(Fake.reply)}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def model():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:{}".format(srv.server_port)
    srv.shutdown()


def test_evening_insight_waits_when_the_day_is_full(tmp_path, model):
    conf(tmp_path, "asks_per_day 1\nsweep_model fake\nsweep_url {}\n".format(model))
    run(tmp_path, "loop", "add", "renew the client's domain", "--due", "2000-01-01")
    run(tmp_path, "loop", "add", "send the invoice")
    offer(tmp_path, 1)  # the day's only slot is taken
    Fake.reply = {"offer": {"text": "The overdue domain renewal and the unsent invoice are for the same client.",
                            "evidence": ["renew the client's domain", "send the invoice"]}}
    r = run(tmp_path, "evening")
    assert r.returncode == 0 and "held" in r.stdout
    assert "same client" not in run(tmp_path, "inbox").stdout
    assert "same client" in run(tmp_path, "inbox", now=DAY2).stdout  # tomorrow it gets its slot


def test_an_offer_back_from_later_uses_a_slot_on_the_day_it_returns(tmp_path):
    conf(tmp_path, "asks_per_day 1\n")
    a = offer(tmp_path, 1).stdout.strip()
    run(tmp_path, "offer", "later", a)
    back = "2026-10-06T10:00:00-04:00"  # past the 3-day deferral
    offer(tmp_path, 2, now=back)
    st = statuses(tmp_path)
    assert sorted(v["status"] for v in st.values()) == ["pending", "waiting"]  # one ask that day, not two
    assert [v for v in st.values() if v["status"] == "pending"][0]["asked"] == "2026-10-06"


def test_a_held_insight_older_than_a_day_is_dropped_quietly(tmp_path):
    conf(tmp_path, "asks_per_day 0\n")
    deliver_internal(env_of(tmp_path, now=DAY1), "an insight", "evening", "insight:2026-10-02", offer=True,
                     tags={"type": "insight"})
    run(tmp_path, "inbox", now=DAY2)
    assert statuses(tmp_path)["insight:2026-10-02"]["status"] == "waiting"  # a day old: still worth asking
    run(tmp_path, "inbox", now="2026-10-04T10:30:00-04:00")
    assert statuses(tmp_path)["insight:2026-10-02"]["status"] == "stale"
    assert not (tmp_path / "corehome" / "offer-outcomes.jsonl").exists()

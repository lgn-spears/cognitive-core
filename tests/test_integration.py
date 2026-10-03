"""Seams between offers-fixes (offer expiry from first show, offers first, grants only for honoured scopes),
home (core home, one shared asks budget) and overnight (granted jobs, one morning report). Each test pins a
rule that only exists because two of those branches meet."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"
DAY1 = "2026-10-02T10:00:00-04:00"
DAY2 = "2026-10-03T10:00:00-04:00"


def run(tmp_path, *args, now=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"HOME": str(home), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    if now:
        env["CORE_NOW"] = now
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def chome(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    return h


def items(tmp_path):
    d = tmp_path / "corehome" / "inbox"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.is_dir() else []


def by_key(tmp_path):
    return {it["key"]: it for it in items(tmp_path)}


def grants(tmp_path):
    p = tmp_path / "corehome" / "grants.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ---- grants: overnight job scopes are grantable, nothing else new is ----

def test_overnight_proposal_is_a_permissions_question_and_its_yes_writes_the_grant(tmp_path):
    marker = tmp_path / "ran"
    (chome(tmp_path) / "overnight.conf").write_text("job backup scope=overnight:backup cmd='touch {}'\n".format(marker))
    run(tmp_path, "overnight")
    offer = [it for it in items(tmp_path) if it.get("kind") == "offer"][0]
    assert offer["source"] == "permissions" and offer["key"].startswith("grant:overnight:backup:")
    r = run(tmp_path, "offer", "yes", offer["id"], "--note", "back it up nightly")
    assert r.returncode == 0 and "no standing permission written" not in r.stderr
    assert grants(tmp_path)["overnight:backup"]["words"] == "back it up nightly"
    run(tmp_path, "overnight")
    assert marker.exists()


def test_the_public_deliver_cannot_ask_for_a_standing_permission(tmp_path):
    # A grant offer is core's own question; an external job can't pose one (key, tag, or both)
    r = run(tmp_path, "deliver", "Deploy without asking?", "--source", "x", "--key", "grant:deploy:prod",
            "--offer", "--tag", "grant=deploy:prod")
    assert r.returncode == 2 and "reserved" in r.stderr
    r = run(tmp_path, "deliver", "Deploy without asking?", "--source", "x", "--offer", "--tag", "grant=deploy:prod")
    assert r.returncode == 2 and "reserved" in r.stderr
    assert "deploy:prod" not in grants(tmp_path) and items(tmp_path) == []


def test_a_job_removed_from_overnight_conf_is_no_longer_grantable(tmp_path):
    conf = chome(tmp_path) / "overnight.conf"
    conf.write_text("job backup scope=overnight:backup cmd=true\n")
    run(tmp_path, "overnight")
    oid = [it for it in items(tmp_path) if it.get("kind") == "offer"][0]["id"]
    conf.write_text("")
    run(tmp_path, "offer", "yes", oid, "--note", "yes")
    assert grants(tmp_path) == {}


def test_an_overnight_job_cannot_borrow_a_sweep_grant(tmp_path):
    # a grant to save preferences must never let an arbitrary command run at night
    marker = tmp_path / "ran"
    (chome(tmp_path) / "grants.json").write_text(json.dumps({"sweep:preference": {"words": "save those"}}))
    (chome(tmp_path) / "overnight.conf").write_text(
        "job sneaky scope=sweep:preference cmd='touch {}'\n".format(marker))
    out = run(tmp_path, "overnight").stdout
    assert not marker.exists()
    assert "line 1 not understood" in out


def test_overnight_grant_proposal_shares_the_daily_ask_budget(tmp_path):
    (chome(tmp_path) / "recall.conf").write_text("asks_per_day 0\n")
    (chome(tmp_path) / "overnight.conf").write_text("job backup scope=overnight:backup cmd=true\n")
    run(tmp_path, "overnight")
    assert [it for it in items(tmp_path) if it["key"].startswith("grant:overnight:backup")][0]["status"] == "waiting"


# ---- core home shows the morning report under DONE TODAY ----

def test_home_shows_the_overnight_report_under_done_today_not_noticed(tmp_path):
    (chome(tmp_path) / "overnight.conf").write_text("job tidy scope=overnight:tidy cmd='echo tidied'\n")
    run(tmp_path, "overnight")
    oid = [it for it in items(tmp_path) if it.get("kind") == "offer"][0]["id"]
    assert run(tmp_path, "offer", "yes", oid, "--note", "go ahead").returncode == 0
    run(tmp_path, "overnight")
    rep = by_key(tmp_path)["overnight:" + datetime.now().astimezone().strftime("%Y-%m-%d")]
    out = run(tmp_path, "home").stdout
    assert "NOTICED" not in out  # the report is the only result, and it lives under DONE TODAY
    done = out.split("DONE TODAY", 1)[1]
    assert "Overnight (" in done and "ok: tidy" in done
    assert "core inbox ack " + rep["id"].rsplit("-", 1)[-1] in done
    assert "overnight-tidy finished" not in out  # the report already names the job: no duplicate line
    assert by_key(tmp_path)[rep["key"]]["status"] == "pending" and not by_key(tmp_path)[rep["key"]]["shown"]


def write_item(h, id_, key, source, text, at, status="pending", **kw):
    d = h / "inbox"
    d.mkdir(parents=True, exist_ok=True)
    rec = dict({"id": id_, "key": key, "source": source, "text": text, "at": at, "seq": int(id_[:14]),
                "status": status, "shown": 0}, **kw)
    (d / (id_ + ".json")).write_text(json.dumps(rec))


def test_home_keeps_an_acked_report_from_today_and_drops_yesterdays(tmp_path):
    h = chome(tmp_path)
    write_item(h, "20261003031500-aaa111", "overnight:2026-10-02", "overnight",
               "Overnight (2026-10-02): ran 1 · ok: tidy", "2026-10-03T03:15:00-04:00", status="acked")
    write_item(h, "20261002031500-bbb222", "overnight:2026-10-01", "overnight",
               "Overnight (2026-10-01): ran 1 · ok: older", "2026-10-02T03:15:00-04:00")
    out = run(tmp_path, "home", now=DAY2).stdout
    done = out.split("DONE TODAY", 1)[1]
    assert "ok: tidy" in done and "core inbox ack aaa111" not in out  # read already: no ack hint
    assert "ok: older" in out.split("DONE TODAY", 1)[0]  # yesterday's, still unread, stays a NOTICED item


# ---- the shared budget meets offer expiry and ordering ----

def test_a_report_upgraded_to_an_offer_is_counted_and_its_week_restarts(tmp_path):
    rid = run(tmp_path, "deliver", "a report", "--source", "s", "--key", "k1", now=DAY1).stdout.strip()
    run(tmp_path, "inbox", now=DAY1)  # shown once as a report
    run(tmp_path, "deliver", "a report", "--source", "s", "--key", "k1", "--offer", now=DAY1)
    it = by_key(tmp_path)["k1"]
    assert it["id"] == rid and it["kind"] == "offer"
    assert it["asked"] == "2026-10-02"  # in front of the person: it uses a slot
    assert "first_shown_at" not in it  # its week starts at its first show as a question


def test_a_promoted_held_ask_never_shown_does_not_expire(tmp_path):
    (chome(tmp_path) / "recall.conf").write_text("asks_per_day 1\n")
    run(tmp_path, "deliver", "first ask", "--source", "s", "--key", "a", "--offer", now=DAY1)
    run(tmp_path, "deliver", "second ask", "--source", "s", "--key", "b", "--offer", now=DAY1)
    assert by_key(tmp_path)["b"]["status"] == "waiting"
    run(tmp_path, "home", now=DAY2)  # a view, but held asks still take today's free slot
    assert by_key(tmp_path)["b"]["status"] == "pending"
    run(tmp_path, "home", now="2026-10-20T10:00:00-04:00")  # weeks later, never shown: never asked
    assert by_key(tmp_path)["b"]["status"] == "pending"


def test_a_promoted_ask_is_listed_before_reports(tmp_path):
    (chome(tmp_path) / "recall.conf").write_text("asks_per_day 0\n")
    run(tmp_path, "deliver", "the held question", "--source", "s", "--key", "q", "--offer", now=DAY1)
    for i in range(6):
        run(tmp_path, "deliver", "report {}".format(i), "--source", "r", "--key", "r{}".format(i), now=DAY1)
    (chome(tmp_path) / "recall.conf").write_text("asks_per_day 1\n")
    out = run(tmp_path, "inbox", now=DAY2).stdout
    assert out.index("the held question") < out.index("report 0")

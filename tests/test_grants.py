"""Step 7: standing permissions — proposed after the 3rd yes in a category, granted only by the person's own
words, always revocable; never inferred from behavior."""

import json
import os
import subprocess
from pathlib import Path

from internal import deliver_internal, env_of

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


def run(tmp_path, *args):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def offer(tmp_path, n, t="preference"):
    return deliver_internal(env_of(tmp_path), "offer {} text".format(n), "sweep", "k{}".format(n), offer=True,
                            tags={"type": t})  # as the sweep asks


def inbox(tmp_path):
    return run(tmp_path, "inbox").stdout.lower()


def test_third_yes_proposes_standing_permission_once(tmp_path):
    for i in range(2):
        run(tmp_path, "offer", "yes", offer(tmp_path, i))
    assert "standing permission" not in inbox(tmp_path)
    run(tmp_path, "offer", "yes", offer(tmp_path, 2))
    assert inbox(tmp_path).count("standing permission") == 1
    run(tmp_path, "offer", "yes", offer(tmp_path, 3))
    assert inbox(tmp_path).count("standing permission") == 1  # asked once, not every yes


def test_grant_needs_the_persons_words_and_is_revocable(tmp_path):
    for i in range(3):
        run(tmp_path, "offer", "yes", offer(tmp_path, i))
    gid = [l.split("]")[0].strip(" [").lower() for l in inbox(tmp_path).splitlines() if "standing permission" in l][0]
    r = run(tmp_path, "offer", "yes", gid)
    assert r.returncode != 0 and "--note" in r.stderr  # a bare yes can't create a standing permission
    assert run(tmp_path, "offer", "yes", gid, "--note", "yeah just save those from now on").returncode == 0
    g = run(tmp_path, "grant", "list").stdout
    assert "sweep:preference" in g and "yeah just save those from now on" in g
    run(tmp_path, "grant", "revoke", "sweep:preference")
    assert "sweep:preference" not in run(tmp_path, "grant", "list").stdout


def test_no_to_the_proposal_is_remembered(tmp_path):
    for i in range(3):
        run(tmp_path, "offer", "yes", offer(tmp_path, i))
    gid = [l.split("]")[0].strip(" [").lower() for l in inbox(tmp_path).splitlines() if "standing permission" in l][0]
    run(tmp_path, "offer", "no", gid)
    for i in range(3, 6):
        run(tmp_path, "offer", "yes", offer(tmp_path, i))
    assert "standing permission" not in inbox(tmp_path)  # he said no; don't keep asking



# ---- whole-branch review fixes ----

def item(tmp_path, iid):
    return json.loads((tmp_path / "corehome" / "inbox" / (iid + ".json")).read_text())


def test_grants_are_only_proposed_for_scopes_something_honours(tmp_path):
    # Nothing checks a grant for evening insights, so asking for one would be a promise the code can't keep.
    for i in range(4):
        oid = deliver_internal(env_of(tmp_path), "insight {} text".format(i), "evening", "i{}".format(i),
                               offer=True, tags={"type": "insight"})
        run(tmp_path, "offer", "yes", oid)
    assert "standing permission" not in inbox(tmp_path)


def test_grant_proposal_reads_as_a_permissions_question(tmp_path):
    for i in range(3):
        run(tmp_path, "offer", "yes", offer(tmp_path, i))
    line = [l for l in inbox(tmp_path).splitlines() if "standing permission" in l][0]
    assert "(permissions offer," in line


PRE = ('Pre-approved (standing permission sweep:preference, their words: "save those"): save to memory, then tell '
       'them in one line what was saved. [preference] "Plain commit messages."; they said "plain commits please"')


def test_revoking_turns_queued_preapproved_items_back_into_offers(tmp_path):
    (tmp_path / "corehome").mkdir()
    (tmp_path / "corehome" / "grants.json").write_text(json.dumps(
        {"sweep:preference": {"words": "save those"}, "sweep:fact": {"words": "facts too"}}))
    pre = deliver_internal(env_of(tmp_path), PRE, "sweep", "sweep:p1", tags={"type": "preference", "granted": "1"})
    other = deliver_internal(env_of(tmp_path), PRE.replace("sweep:preference", "sweep:fact"), "sweep", "sweep:f1",
                             tags={"type": "fact", "granted": "1"})
    assert run(tmp_path, "grant", "revoke", "sweep:preference").returncode == 0
    it = item(tmp_path, pre)
    assert it["kind"] == "offer" and it["status"] == "pending" and "granted" not in it["tags"]
    assert it["text"].startswith("Sweep offer (ask before saving") and "Pre-approved" not in it["text"]
    assert '"Plain commit messages."' in it["text"]
    assert run(tmp_path, "offer", "yes", pre).returncode == 0  # now it needs (and takes) an answer
    assert item(tmp_path, other)["text"].startswith("Pre-approved")  # a grant still standing is untouched


def test_revoking_an_unknown_scope_fails(tmp_path):
    r = run(tmp_path, "grant", "revoke", "sweep:nothing")
    assert r.returncode != 0 and "no standing permission" in r.stderr


def test_revoking_converts_a_preapproved_item_still_held_for_a_slot(tmp_path):
    # An item queued under the grant but waiting for a free slot (as older versions held them) is just as
    # "Pre-approved": left alone it would surface later telling the agent to save without asking.
    h = tmp_path / "corehome"
    (h / "inbox").mkdir(parents=True)
    (h / "recall.conf").write_text("asks_per_day 0\n")
    (h / "grants.json").write_text(json.dumps({"sweep:preference": {"words": "save those"}}))
    rec = {"id": "20261002100000-abc123", "key": "sweep:p1", "source": "sweep", "text": PRE, "seq": 1,
           "at": "2026-10-02T10:00:00-04:00", "status": "waiting", "shown": 0,
           "tags": {"type": "preference", "granted": "1"}}
    (h / "inbox" / (rec["id"] + ".json")).write_text(json.dumps(rec))
    r = run(tmp_path, "grant", "revoke", "sweep:preference")
    assert r.returncode == 0 and "1 queued item" in r.stdout
    it = item(tmp_path, rec["id"])
    assert it["kind"] == "offer" and "granted" not in it["tags"] and it["text"].startswith("Sweep offer")
    assert it["status"] == "waiting"  # still no free slot: it waits, now as a plain question


# ---- only the sweep's own scopes are proposed; overnight jobs are granted only through overnight's offer ----

def test_third_yes_never_proposes_an_overnight_job_scope(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir()
    marker = tmp_path / "ran"
    (h / "overnight.conf").write_text("job digest scope=theseus:digest cmd='touch {}'\n".format(marker))
    for i in range(4):
        oid = run(tmp_path, "deliver", "digest {} text".format(i), "--source", "theseus", "--key", "d{}".format(i),
                  "--offer", "--tag", "type=digest").stdout.strip()
        run(tmp_path, "offer", "yes", oid, "--note", "yes save it")
    assert "save these without asking" not in inbox(tmp_path)
    assert "theseus:digest" not in run(tmp_path, "grant", "list").stdout


def test_a_memory_style_grant_offer_cannot_create_an_overnight_grant(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "overnight.conf").write_text("job digest scope=theseus:digest cmd=true\n")
    oid = deliver_internal(env_of(tmp_path), "Save these without asking?", "permissions", "grant:x", offer=True,
                           tags={"grant": "theseus:digest"})  # even core's own question can't reach past its scopes
    r = run(tmp_path, "offer", "yes", oid, "--note", "sure, save them")
    assert r.returncode == 0 and "no standing permission written" in r.stderr
    assert "theseus:digest" not in run(tmp_path, "grant", "list").stdout


def test_deliver_refuses_the_tags_only_overnight_may_set(tmp_path):
    r = run(tmp_path, "deliver", "Run it?", "--source", "permissions", "--offer", "--tag", "grant=s",
            "--tag", "grant_job=digest", "--tag", "cmd_sha=abcd1234")
    assert r.returncode != 0 and "reserved" in r.stderr

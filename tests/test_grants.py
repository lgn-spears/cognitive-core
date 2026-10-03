"""Step 7: standing permissions — proposed after the 3rd yes in a category, granted only by the person's own
words, always revocable; never inferred from behavior."""

import json
import os
import subprocess
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


def run(tmp_path, *args):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def offer(tmp_path, n, t="preference"):
    return run(tmp_path, "deliver", "offer {} text".format(n), "--source", "sweep", "--key", "k{}".format(n),
               "--offer", "--tag", "type=" + t).stdout.strip()


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

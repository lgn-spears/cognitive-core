"""Fixes from a new-user walkthrough: things a first-time user tripped on."""

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "bin" / "core"


def run(tmp_path, *args, stdin=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"HOME": str(home), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"],
           "CORE_AUDIT_TIMEOUT": "10"}
    return subprocess.run(["python3", str(CORE), *args], input=stdin, capture_output=True, text=True,
                          env=env, timeout=60)


def conf(tmp_path, text):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    (h / "audits.conf").write_text(text)


def test_brief_never_says_all_clear_when_a_repo_root_is_missing(tmp_path):
    # A typo in repo_root used to scan nothing and report "nothing needs you".
    conf(tmp_path, "repo_root {}\n".format(tmp_path / "cdoe"))
    out = run(tmp_path, "brief").stdout
    assert "nothing needs you" not in out
    assert "cdoe" in out and "doesn't exist" in out


def test_brief_never_says_all_clear_when_roots_hold_no_repos(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    conf(tmp_path, "repo_root {}\n".format(empty))
    out = run(tmp_path, "brief").stdout
    assert "nothing needs you" not in out
    assert "no git repos" in out


def test_inbox_command_lists_every_item(tmp_path):
    for i in range(5):
        run(tmp_path, "deliver", "result number {}".format(i), "--source", "job")
    out = run(tmp_path, "inbox").stdout
    assert all("result number {}".format(i) in out for i in range(5))
    assert "more in `core inbox`" not in out


def test_redelivering_a_pending_key_says_how_to_update(tmp_path):
    run(tmp_path, "deliver", "14 invoices overdue", "--source", "job", "--key", "inv")
    r = run(tmp_path, "deliver", "15 invoices overdue", "--source", "job", "--key", "inv")
    assert "--replace" in r.stderr
    r = run(tmp_path, "deliver", "15 invoices overdue", "--source", "job", "--key", "inv", "--replace")
    assert "15 invoices" in run(tmp_path, "inbox").stdout


def test_ack_accepts_a_unique_id_prefix(tmp_path):
    item = run(tmp_path, "deliver", "done", "--source", "job").stdout.strip()
    r = run(tmp_path, "inbox", "ack", item.split("-")[1])  # the short random part
    assert r.returncode == 0, r.stderr
    assert "inbox empty" in run(tmp_path, "inbox").stdout


def test_bare_loop_lists(tmp_path):
    run(tmp_path, "loop", "add", "call the plumber")
    r = run(tmp_path, "loop")
    assert r.returncode == 0 and "call the plumber" in r.stdout


def test_a_decision_is_recalled_once_not_twice(tmp_path):
    mem = tmp_path / "home" / ".claude" / "projects" / "p" / "memory"
    mem.mkdir(parents=True)
    for i in range(30):
        (mem / "n{}.md".format(i)).write_text("unrelated note {} about gardening\n".format(i))
    run(tmp_path, "decision", "tidepool stays single-region on fly in iad, multi-region rejected")
    out = run(tmp_path, "recall", stdin=json.dumps(
        {"prompt": "should tidepool go multi-region on fly?"})).stdout
    assert out.count("multi-region rejected") == 1, out

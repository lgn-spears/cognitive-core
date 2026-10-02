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


def test_default_roots_never_nag_about_a_missing_code_folder(tmp_path):
    # Defaults are ~/code and ~; most people have no ~/code and never wrote audits.conf.
    repo = tmp_path / "home" / "proj"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    out = run(tmp_path, "brief").stdout
    assert "doesn't exist" not in out and "audits.conf" not in out


def test_different_non_latin_notes_are_not_merged():
    import importlib.machinery, importlib.util
    l = importlib.machinery.SourceFileLoader("core", str(CORE))
    core = importlib.util.module_from_spec(importlib.util.spec_from_loader("core", l)); l.exec_module(core)
    assert core.same_text_key("кот любит рыбу") != core.same_text_key("собака любит мясо")
    assert core.same_text_key("猫") != core.same_text_key("犬")


def test_decisions_with_colons_are_neither_merged_nor_duplicated(tmp_path):
    mem = tmp_path / "home" / ".claude" / "projects" / "p" / "memory"
    mem.mkdir(parents=True)
    for i in range(30):
        (mem / "n{}.md".format(i)).write_text("unrelated note {} about gardening\n".format(i))
    run(tmp_path, "decision", "staging db: keep nightly snapshots for 30 days")
    run(tmp_path, "decision", "prod db: keep nightly snapshots for 30 days")
    out = run(tmp_path, "recall", stdin=json.dumps({"prompt": "how long do we keep nightly db snapshots"})).stdout
    assert out.count("staging db:") == 1 and out.count("prod db:") == 1, out


def test_dedupe_keeps_lines_that_differ_in_any_character():
    import importlib.machinery, importlib.util
    l = importlib.machinery.SourceFileLoader("core", str(CORE))
    core = importlib.util.module_from_spec(importlib.util.spec_from_loader("core", l)); l.exec_module(core)
    k = core.same_text_key
    for a, b in (("[d] दिल", "[d] दल"), ("[d] ไก่", "[d] ไก"), ("[d] كَتَبَ", "[d] كُتُب"),
                 ("[d] C++ wins", "[d] C wins"), ("[d] v1.2", "[d] v12"), ("[d] deploy 🚀", "[d] deploy 🐛")):
        assert k(a) != k(b), (a, b)
    # the same fact in decisions.log and the day ledger is one line
    assert k("[2026-10-02] ship it 🚀") == k("[09:00] decision: ship it 🚀")
    assert k("[2026-10-02] Ship  it") == k("[09:00] decision: ship it")

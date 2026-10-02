"""Tests for `core brief` and the tier-1 audits.

Every test runs the real CLI in a subprocess with HOME and CORE_HOME pointed at
temp dirs, so nothing on the developer's machine is scanned or touched.
"""

import os
import stat
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "bin" / "core"
AUDITS = REPO / "audits"


def run_core(tmp_path, *args, audits_dir=None, extra_env=None, path_prefix=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "CORE_HOME": str(tmp_path / "corehome"),
        "PATH": os.environ["PATH"],
        "CORE_AUDIT_TIMEOUT": "5",
    }
    if path_prefix:
        env["PATH"] = "{}:{}".format(path_prefix, env["PATH"])
    if audits_dir:
        env["CORE_AUDITS_DIR"] = str(audits_dir)
    env.update(extra_env or {})
    return subprocess.run(
        ["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60
    )


def write_audit(d, name, body):
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def test_nothing_to_report_says_so_and_exits_zero(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "quiet.sh", "exit 0")
    (d / "MANIFEST").write_text("quiet.sh  OPEN, NOBODY WAITING ON ME\n")
    r = run_core(tmp_path, "brief", audits_dir=d)
    assert r.returncode == 0
    assert r.stdout.strip() == "[core] brief — nothing needs you right now."


def test_findings_grouped_in_manifest_order_with_indented_details(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "a.sh", r"printf 'first finding\tits detail\n'")
    write_audit(d, "b.sh", r"printf 'second finding\n'")
    write_audit(d, "c.sh", r"printf 'third finding\n'")
    (d / "MANIFEST").write_text(
        "# comment line\n\n"
        "b.sh  STILL RUNNING, SHOULDN'T BE\n"
        "a.sh  OPEN, NOBODY WAITING ON ME\n"
        "c.sh  STILL RUNNING, SHOULDN'T BE\n"
    )
    r = run_core(tmp_path, "brief", audits_dir=d)
    assert r.returncode == 0
    assert r.stdout == (
        "STILL RUNNING, SHOULDN'T BE\n"
        "  second finding\n"
        "  third finding\n"
        "\n"
        "OPEN, NOBODY WAITING ON ME\n"
        "  first finding\n"
        "     its detail\n"
    )


def test_bad_and_slow_audits_do_not_hide_the_rest(tmp_path):
    # A broken audit must never silence the others: the brief's whole value is
    # that it shows up every time. Failures are named, never swallowed.
    d = tmp_path / "audits"
    write_audit(d, "good.sh", r"printf 'real finding\n'")
    write_audit(d, "bad.sh", "echo 'boom' >&2; exit 3")
    write_audit(d, "slow.sh", "sleep 30")
    (d / "MANIFEST").write_text(
        "bad.sh   OPEN, NOBODY WAITING ON ME\n"
        "slow.sh  OPEN, NOBODY WAITING ON ME\n"
        "good.sh  OPEN, NOBODY WAITING ON ME\n"
        "gone.sh  OPEN, NOBODY WAITING ON ME\n"
    )
    start = time.time()
    r = run_core(tmp_path, "brief", audits_dir=d, extra_env={"CORE_AUDIT_TIMEOUT": "1"})
    assert time.time() - start < 15
    assert r.returncode == 0
    assert "  real finding" in r.stdout
    assert "  ! audit bad.sh failed: boom" in r.stdout
    assert "  ! audit slow.sh timed out after 1s" in r.stdout
    assert "  ! audit gone.sh missing" in r.stdout


def test_brief_never_writes_to_core_home(tmp_path):
    # Law: surfaces only, never acts. A brief that creates state has started acting.
    d = tmp_path / "audits"
    write_audit(d, "a.sh", r"printf 'x\n'")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\n")
    run_core(tmp_path, "brief", audits_dir=d)
    assert not (tmp_path / "corehome").exists()


def test_audits_receive_conf_and_lib_paths(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "env.sh", r'printf "%s|%s\n" "$CORE_AUDITS_CONF" "$CORE_AUDITS_LIB"')
    (d / "MANIFEST").write_text("env.sh  OPEN, NOBODY WAITING ON ME\n")
    r = run_core(tmp_path, "brief", audits_dir=d)
    conf, lib = r.stdout.splitlines()[1].strip().split("|")
    assert conf == str(tmp_path / "corehome" / "audits.conf")
    assert lib == str(d / "lib.sh")


def git(repo, *args, env=None):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def make_repo(path, commits, days_ago=0, branch="main"):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", branch)
    ts = int(time.time()) - days_ago * 86400
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
        GIT_AUTHOR_DATE="{} +0000".format(ts), GIT_COMMITTER_DATE="{} +0000".format(ts),
    )
    for i in range(commits):
        (path / "f{}.txt".format(i)).write_text(str(i))
        git(path, "add", ".")
        git(path, "commit", "-q", "-m", "c{}".format(i), env=env)
    return path


def add_remote(repo, bare_dir, push=True):
    subprocess.run(["git", "init", "-q", "--bare", str(bare_dir)], check=True)
    git(repo, "remote", "add", "origin", str(bare_dir))
    if push:
        git(repo, "push", "-q", "origin", "HEAD")


def stub(tmp_path, name, body):
    d = tmp_path / "stubs"
    write_audit(d, name, body)
    return d


def conf(tmp_path, text):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    (h / "audits.conf").write_text(text)


NO_TM = "echo 'No destinations configured.'"


def test_no_remote_counts_only_repos_without_any_remote(tmp_path):
    root = tmp_path / "code"
    make_repo(root / "lonely", 3, days_ago=21)
    backed = make_repo(root / "backed", 5, days_ago=40)
    add_remote(backed, tmp_path / "bare" / "backed.git")
    conf(tmp_path, "repo_root {}\n".format(root))
    stubs = stub(tmp_path, "tmutil", NO_TM)
    r = run_core(tmp_path, "brief", path_prefix=stubs)
    assert "OPEN, NOBODY WAITING ON ME" in r.stdout
    assert "  3 commits in 1 repo has no git remote at all." in r.stdout
    assert "     Oldest commit is 3 weeks old. This machine has no backup destination configured." in r.stdout


def test_no_remote_omits_backup_note_when_time_machine_is_configured(tmp_path):
    # The note is a claim about the machine; it must only appear when true.
    root = tmp_path / "code"
    make_repo(root / "lonely", 1)
    conf(tmp_path, "repo_root {}\n".format(root))
    stubs = stub(tmp_path, "tmutil", "echo 'Name : Backup Disk'")
    r = run_core(tmp_path, "brief", path_prefix=stubs)
    assert "  1 commit in 1 repo has no git remote at all." in r.stdout
    assert "Oldest commit is from today." in r.stdout
    assert "backup destination" not in r.stdout


def test_no_remote_ignores_empty_repo(tmp_path):
    root = tmp_path / "code"
    (root / "fresh").mkdir(parents=True)
    git(root / "fresh", "init", "-q")
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert r.stdout.strip() == "[core] brief — nothing needs you right now."


def test_no_remote_handles_spaces_in_paths(tmp_path):
    root = tmp_path / "My Code"
    make_repo(root / "Old Client" / "site", 2)
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  2 commits in 1 repo has no git remote at all." in r.stdout


def test_no_remote_sums_across_repos_and_pluralizes(tmp_path):
    root = tmp_path / "code"
    make_repo(root / "a", 2, days_ago=3)
    make_repo(root / "b", 4, days_ago=100)
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  6 commits in 2 repos have no git remote at all." in r.stdout
    assert "Oldest commit is 3 months old." in r.stdout


def test_default_roots_scan_home_code_and_home(tmp_path):
    # No audits.conf: a new user still gets a real finding on day one (spec §4.1).
    make_repo(tmp_path / "home" / "code" / "proj", 1)
    make_repo(tmp_path / "home" / "loose", 1)
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  2 commits in 2 repos have no git remote at all." in r.stdout


def commit_more(repo, n, days_ago=0):
    ts = int(time.time()) - days_ago * 86400
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
        GIT_AUTHOR_DATE="{} +0000".format(ts), GIT_COMMITTER_DATE="{} +0000".format(ts),
    )
    for i in range(n):
        f = repo / "more{}-{}.txt".format(days_ago, i)
        f.write_text(str(i))
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "more", env=env)


def test_unpushed_counts_only_commits_no_remote_branch_has(tmp_path):
    root = tmp_path / "code"
    proj = make_repo(root / "proj", 2, days_ago=30)
    add_remote(proj, tmp_path / "bare" / "proj.git")
    commit_more(proj, 3, days_ago=21)
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  3 unpushed commits in proj." in r.stdout
    assert "     Oldest is 3 weeks old." in r.stdout
    assert "no git remote" not in r.stdout  # it has a remote; not double-counted


def test_unpushed_counts_branch_never_pushed(tmp_path):
    # A branch with no upstream is the easiest work to lose and the easiest to miss.
    root = tmp_path / "code"
    proj = make_repo(root / "proj", 1)
    add_remote(proj, tmp_path / "bare" / "proj.git")
    git(proj, "checkout", "-q", "-b", "experiment")
    commit_more(proj, 2)
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  2 unpushed commits in proj." in r.stdout


def test_unpushed_silent_when_everything_is_pushed(tmp_path):
    root = tmp_path / "code"
    proj = make_repo(root / "proj", 4)
    add_remote(proj, tmp_path / "bare" / "proj.git")
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert r.stdout.strip() == "[core] brief — nothing needs you right now."


def test_unpushed_shows_five_largest_then_summarizes(tmp_path):
    # Seven repos of findings is a wall; the brief caps the list and says so.
    root = tmp_path / "code"
    for i in range(1, 8):
        p = make_repo(root / "r{}".format(i), 1)
        add_remote(p, tmp_path / "bare" / "r{}.git".format(i))
        commit_more(p, i)
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    lines = [l for l in r.stdout.splitlines() if "unpushed commit" in l]
    assert lines[0].strip() == "7 unpushed commits in r7."
    assert lines[4].strip() == "3 unpushed commits in r3."
    assert len(lines) == 5
    assert "  2 more repos have unpushed work (3 commits)." in r.stdout


import datetime as _dt
import shutil

LAUNCHCTL = (
    "printf 'PID\\tStatus\\tLabel\\n'\n"
    "printf -- '-\\t0\\tcom.oldclient.sync\\n'\n"
    "printf -- '-\\t0\\tcom.oldclient.report\\n'\n"
    "printf -- '412\\t0\\tcom.oldclient.watch\\n'\n"
    "printf -- '-\\t78\\tcom.oldclient.backfill\\n'\n"
    "printf -- '-\\t0\\tcom.apple.unrelated\\n'\n"
)


def test_launchd_reports_loaded_jobs_for_ended_work(tmp_path):
    # Jobs that succeed for work that is over are worse than failing ones:
    # nothing ever alerts on them. The exit-0 count is the point.
    ended = (_dt.date.today() - _dt.timedelta(days=70)).isoformat()
    conf(tmp_path, "repo_root {}\nended com.oldclient. {}\n".format(tmp_path / "none", ended))
    stubs = stub(tmp_path, "launchctl", LAUNCHCTL)
    r = run_core(tmp_path, "brief", path_prefix=stubs)
    assert "STILL RUNNING, SHOULDN'T BE" in r.stdout
    assert "  4 scheduled jobs matching com.oldclient. are still loaded, 10 weeks after that work ended." in r.stdout
    assert "     3 of the 4 last exited 0 - they are not erroring, they are succeeding." in r.stdout
    assert "com.apple" not in r.stdout


def test_launchd_without_end_date_omits_the_age(tmp_path):
    conf(tmp_path, "repo_root {}\nended com.oldclient.\n".format(tmp_path / "none"))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "launchctl", LAUNCHCTL))
    assert "  4 scheduled jobs matching com.oldclient. are still loaded." in r.stdout


def test_launchd_silent_without_ended_config(tmp_path):
    # Core cannot know which work is over; without the user's word it says nothing.
    conf(tmp_path, "repo_root {}\n".format(tmp_path / "none"))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "launchctl", LAUNCHCTL))
    assert r.stdout.strip() == "[core] brief — nothing needs you right now."


def test_launchd_silent_when_launchctl_fails(tmp_path):
    conf(tmp_path, "repo_root {}\nended com.oldclient.\n".format(tmp_path / "none"))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "launchctl", "exit 1"))
    assert r.returncode == 0
    assert r.stdout.strip() == "[core] brief — nothing needs you right now."


def test_audits_parse_under_system_bash():
    # Users run macOS /bin/bash 3.2; Homebrew bash on a dev box would hide breakage.
    system_bash = Path("/bin/bash")
    if not system_bash.exists():
        return
    for script in sorted(AUDITS.glob("*.sh")):
        r = subprocess.run([str(system_bash), "-n", str(script)], capture_output=True, text=True)
        assert r.returncode == 0, "{}: {}".format(script.name, r.stderr)


# ---- Task 5: findings into the inbox ----

import json as _json


def inbox_items(tmp_path):
    d = tmp_path / "corehome" / "inbox"
    return [_json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.is_dir() else []


def test_deliver_replace_updates_pending_text_keeps_id(tmp_path):
    # A re-run should say what is true now, not keep the stale first version.
    a = run_core(tmp_path, "deliver", "4 repos have no remote", "--source", "audits", "--key", "k").stdout.strip()
    b = run_core(tmp_path, "deliver", "5 repos have no remote", "--source", "audits", "--key", "k",
                 "--replace").stdout.strip()
    assert a == b
    items = inbox_items(tmp_path)
    assert len(items) == 1 and items[0]["text"] == "5 repos have no remote"


def test_deliver_without_replace_keeps_first_text(tmp_path):
    run_core(tmp_path, "deliver", "first", "--source", "s", "--key", "k")
    run_core(tmp_path, "deliver", "second", "--source", "s", "--key", "k")
    assert [i["text"] for i in inbox_items(tmp_path)] == ["first"]


def two_audits(tmp_path, a_text, b_text):
    d = tmp_path / "audits"
    write_audit(d, "a.sh", "printf '{}\\tdetail a\\n'".format(a_text))
    write_audit(d, "b.sh", "printf '{}\\n'".format(b_text))
    write_audit(d, "quiet.sh", "exit 0")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\nb.sh  OPEN, NOBODY WAITING ON ME\n"
                                "quiet.sh  STILL RUNNING, SHOULDN'T BE\n")
    return d


def test_brief_deliver_one_item_per_audit(tmp_path):
    d = two_audits(tmp_path, "3 repos lonely", "2 jobs orphaned")
    r = run_core(tmp_path, "brief", "--deliver", audits_dir=d)
    assert r.returncode == 0 and "3 repos lonely" in r.stdout
    items = inbox_items(tmp_path)
    assert sorted(i["key"] for i in items) == ["audit:a.sh", "audit:b.sh"]
    assert all(i["source"] == "audits" and i["status"] == "pending" for i in items)


def test_brief_deliver_rerun_updates_not_duplicates(tmp_path):
    run_core(tmp_path, "brief", "--deliver", audits_dir=two_audits(tmp_path, "3 repos lonely", "2 jobs"))
    run_core(tmp_path, "brief", "--deliver", audits_dir=two_audits(tmp_path, "4 repos lonely", "2 jobs"))
    texts = sorted(i["text"] for i in inbox_items(tmp_path))
    assert texts == ["2 jobs", "4 repos lonely — detail a"]


def test_brief_without_deliver_writes_nothing(tmp_path):
    run_core(tmp_path, "brief", audits_dir=two_audits(tmp_path, "3 repos lonely", "2 jobs"))
    assert not (tmp_path / "corehome").exists()


# ---- step-2 final-review fix pass ----


def test_non_utf8_audit_output_never_crashes_brief(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "bad.sh", r"printf 'caf\351 finding\n'")
    write_audit(d, "good.sh", r"printf 'good finding\n'")
    (d / "MANIFEST").write_text("bad.sh  OPEN, NOBODY WAITING ON ME\ngood.sh  OPEN, NOBODY WAITING ON ME\n")
    r = run_core(tmp_path, "brief", audits_dir=d)
    assert r.returncode == 0
    assert "good finding" in r.stdout and "finding" in r.stdout.split("good finding")[0]


def test_bad_timeout_setting_falls_back(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "a.sh", r"printf 'x\n'")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\n")
    r = run_core(tmp_path, "brief", audits_dir=d, extra_env={"CORE_AUDIT_TIMEOUT": "abc"})
    assert r.returncode == 0 and "  x" in r.stdout


def test_timed_out_audit_leaves_no_process(tmp_path):
    d = tmp_path / "audits"
    marker = "theseus-orphan-{}".format(os.getpid())
    write_audit(d, "slow.sh", "sleep 30 & wait  # {}".format(marker))
    (d / "MANIFEST").write_text("slow.sh  OPEN, NOBODY WAITING ON ME\n")
    run_core(tmp_path, "brief", audits_dir=d, extra_env={"CORE_AUDIT_TIMEOUT": "1"})
    time.sleep(0.5)
    left = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.strip()
    assert left == ""


def test_quiet_audit_retires_its_stale_inbox_item(tmp_path):
    # Once the problem is gone, the inbox must stop telling the agent it exists.
    d = tmp_path / "audits"
    write_audit(d, "a.sh", r"printf '5 unpushed\n'")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\n")
    run_core(tmp_path, "brief", "--deliver", audits_dir=d)
    assert [i["status"] for i in inbox_items(tmp_path)] == ["pending"]
    write_audit(d, "a.sh", "exit 0")
    run_core(tmp_path, "brief", "--deliver", audits_dir=d)
    assert [i["status"] for i in inbox_items(tmp_path)] == ["resolved"]
    assert "inbox empty" in run_core(tmp_path, "inbox").stdout


def test_erroring_audit_keeps_its_inbox_item(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "a.sh", r"printf '5 unpushed\n'")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\n")
    run_core(tmp_path, "brief", "--deliver", audits_dir=d)
    write_audit(d, "a.sh", "exit 3")
    run_core(tmp_path, "brief", "--deliver", audits_dir=d)
    assert [i["status"] for i in inbox_items(tmp_path)] == ["pending"]


def test_unpushed_counts_detached_head_commits(tmp_path):
    root = tmp_path / "code"
    proj = make_repo(root / "proj", 1)
    add_remote(proj, tmp_path / "bare" / "proj.git")
    git(proj, "checkout", "-q", "--detach")
    commit_more(proj, 2)
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  2 unpushed commits in proj." in r.stdout


def test_unreadable_folders_are_reported_not_skipped(tmp_path):
    # Background jobs on macOS can't see privacy-protected folders; a silent skip is a hidden gap.
    root = tmp_path / "home2"
    make_repo(root / "visible", 1)
    make_repo(root / "Locked" / "hidden", 2)
    os.chmod(str(root / "Locked"), 0)
    try:
        conf(tmp_path, "repo_root {}\n".format(root))
        r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    finally:
        os.chmod(str(root / "Locked"), 0o755)
    assert "  1 commit in 1 repo has no git remote at all." in r.stdout
    assert "  Couldn't look inside 1 folder from here: Locked." in r.stdout


# ---- hardening C ----

def test_worktree_counted_once(tmp_path):
    root = tmp_path / "code"
    main = make_repo(root / "main", 3)
    git(main, "worktree", "add", "-q", str(root / "wt"), "-b", "side")
    conf(tmp_path, "repo_root {}\n".format(root))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "tmutil", NO_TM))
    assert "  3 commits in 1 repo has no git remote at all." in r.stdout


def test_ended_future_and_invalid_dates_make_no_claim(tmp_path):
    for bad in ["2999-01-01", "2026-02-31", "yesterday"]:
        conf(tmp_path, "repo_root {}\nended com.oldclient. {}\n".format(tmp_path / "none", bad))
        r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "launchctl", LAUNCHCTL))
        assert "  4 scheduled jobs matching com.oldclient. are still loaded." in r.stdout, bad
        assert "after that work ended" not in r.stdout, bad


def test_duplicate_ended_lines_report_once(tmp_path):
    conf(tmp_path, "repo_root {}\nended com.oldclient.\nended com.oldclient.\n".format(tmp_path / "none"))
    r = run_core(tmp_path, "brief", path_prefix=stub(tmp_path, "launchctl", LAUNCHCTL))
    assert r.stdout.count("scheduled jobs matching com.oldclient.") == 1


def test_single_job_grammar(tmp_path):
    conf(tmp_path, "repo_root {}\nended com.solo.\n".format(tmp_path / "none"))
    stubs = stub(tmp_path, "launchctl", "printf 'PID\\tStatus\\tLabel\\n-\\t0\\tcom.solo.job\\n'")
    r = run_core(tmp_path, "brief", path_prefix=stubs)
    assert "  1 scheduled job matching com.solo. is still loaded." in r.stdout
    assert "It last exited 0 - it is not erroring, it is succeeding." in r.stdout


def test_brief_neutralizes_control_characters(tmp_path):
    d = tmp_path / "audits"
    write_audit(d, "a.sh", r"printf '\033[2J\033[31mred finding\tdetail\033[0m\n'")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\n")
    r = run_core(tmp_path, "brief", audits_dir=d)
    assert "\x1b" not in r.stdout and "red finding" in r.stdout


def test_deliver_keeps_finding_detail(tmp_path):
    d = two_audits(tmp_path, "3 repos lonely", "2 jobs")
    run_core(tmp_path, "brief", "--deliver", audits_dir=d)
    texts = {i["key"]: i["text"] for i in inbox_items(tmp_path)}
    assert texts["audit:a.sh"] == "3 repos lonely — detail a"

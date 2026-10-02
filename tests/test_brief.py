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

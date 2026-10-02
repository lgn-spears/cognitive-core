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

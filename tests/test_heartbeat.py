"""Tests for core run (leases + run records) and core heartbeat (alarms).

A schedule is not proof a job ran. These tests pin down that every way a background job can fail —
error, hang, overlap, death mid-run, never starting — ends up as an alarm the person sees."""

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "bin" / "core"


def env_for(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"HOME": str(home), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}


def run_core(tmp_path, *args, timeout=60):
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True,
                          env=env_for(tmp_path), timeout=timeout)


def records(tmp_path):
    p = tmp_path / "corehome" / "heartbeat.json"
    return json.loads(p.read_text()) if p.exists() else {}


def passes(tmp_path, text):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    (h / "passes.conf").write_text(text)


def put_record(tmp_path, name, **rec):
    h = tmp_path / "corehome"
    h.mkdir(exist_ok=True)
    p = h / "heartbeat.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    data[name] = rec
    p.write_text(json.dumps(data))


def ago(**kw):
    return (datetime.now().astimezone() - timedelta(**kw)).isoformat(timespec="seconds")


# ---- Task 1: core run ----

def test_run_records_success_and_passes_exit_code(tmp_path):
    r = run_core(tmp_path, "run", "audits", "--", "sh", "-c", "echo found 3 things")
    assert r.returncode == 0
    rec = records(tmp_path)["audits"]
    assert rec["status"] == "ok" and rec["exit"] == 0
    assert rec["started"] and rec["finished"]
    assert rec["last_line"] == "found 3 things"


def test_run_records_failure_with_last_line(tmp_path):
    r = run_core(tmp_path, "run", "nightly", "--", "sh", "-c", "echo step one; echo boom >&2; exit 4")
    assert r.returncode == 4
    rec = records(tmp_path)["nightly"]
    assert rec["status"] == "failed" and rec["exit"] == 4 and rec["last_line"] == "boom"


def test_run_missing_command_recorded_failed(tmp_path):
    # A job that can't even start must still leave a record, or it fails silently.
    r = run_core(tmp_path, "run", "ghost", "--", "definitely-not-a-command-xyz")
    assert r.returncode != 0
    rec = records(tmp_path)["ghost"]
    assert rec["status"] == "failed" and "not" in rec["last_line"].lower()


def test_run_timeout_kills_group(tmp_path):
    marker = "hb-orphan-{}".format(os.getpid())
    r = run_core(tmp_path, "run", "slow", "--timeout", "1", "--", "sh", "-c",
                 "sleep 30 & wait # {}".format(marker))
    assert records(tmp_path)["slow"]["status"] == "timeout"
    assert r.returncode != 0
    time.sleep(0.5)
    left = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.strip()
    assert left == ""


def test_overlapping_run_is_skipped(tmp_path):
    # Two copies of a pass must never run at once; the second leaves the first's record alone.
    first = subprocess.Popen(["python3", str(CORE), "run", "audits", "--", "sleep", "2"],
                             env=env_for(tmp_path))
    time.sleep(0.7)
    r = run_core(tmp_path, "run", "audits", "--", "sh", "-c", "echo second")
    assert r.returncode == 0 and "skipped" in r.stdout
    assert records(tmp_path)["audits"]["status"] == "running"
    first.wait()
    assert records(tmp_path)["audits"]["status"] == "ok"
    assert records(tmp_path)["audits"]["last_line"] == ""


# ---- Task 2: passes.conf + core heartbeat ----

def test_heartbeat_silent_without_passes_conf(tmp_path):
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_heartbeat_never_ran(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 1
    assert "audits has never run (expected every 1d)" in r.stdout


def test_heartbeat_overdue(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    put_record(tmp_path, "audits", status="ok", exit=0, started=ago(days=3, minutes=1),
               finished=ago(days=3), last_line="")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 1
    assert "audits last finished 3 days ago (expected every 1d)" in r.stdout


def test_heartbeat_within_grace_is_healthy(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    put_record(tmp_path, "audits", status="ok", exit=0, started=ago(hours=30), finished=ago(hours=30),
               last_line="")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_heartbeat_failed(tmp_path):
    passes(tmp_path, "expect nightly every 1d\n")
    put_record(tmp_path, "nightly", status="failed", exit=4, started=ago(hours=2), finished=ago(hours=2),
               last_line="boom")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 1 and "nightly failed 2 hours ago: boom" in r.stdout


def test_heartbeat_stuck_when_running_but_unlocked(tmp_path):
    # Killed mid-run: the record still says running, but nothing holds the lease.
    passes(tmp_path, "expect nightly every 1d\n")
    put_record(tmp_path, "nightly", status="running", started=ago(hours=5), last_line="")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 1
    assert "nightly started 5 hours ago and never finished" in r.stdout


def test_heartbeat_running_and_locked_is_not_stuck(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    job = subprocess.Popen(["python3", str(CORE), "run", "audits", "--", "sleep", "2"], env=env_for(tmp_path))
    time.sleep(0.7)
    r = run_core(tmp_path, "heartbeat")
    job.wait()
    assert r.returncode == 0, r.stdout


def test_malformed_heartbeat_files_never_crash(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "passes.conf").write_text("expect audits every banana\nexpect\ngarbage line\nexpect x every 2h\n")
    (h / "heartbeat.json").write_text("{not json")
    for args in (["heartbeat"], ["inject"], ["brief"]):
        r = run_core(tmp_path, *args)
        assert "Traceback" not in r.stderr, args
    assert "x has never run (expected every 2h)" in run_core(tmp_path, "heartbeat").stdout


# ---- Task 3: alarms first ----

def test_inject_shows_alarms_near_top(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    lines = run_core(tmp_path, "inject").stdout.splitlines()
    alarm = [i for i, l in enumerate(lines) if l.startswith("HEARTBEAT ALARM:")]
    assert alarm and alarm[0] <= 3
    assert "audits has never run" in lines[alarm[0]]


def test_brief_shows_alarms_first(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    d = tmp_path / "audits"
    d.mkdir()
    (d / "a.sh").write_text("#!/usr/bin/env bash\nprintf 'finding\\n'\n")
    (d / "MANIFEST").write_text("a.sh  OPEN, NOBODY WAITING ON ME\n")
    env = env_for(tmp_path)
    env["CORE_AUDITS_DIR"] = str(d)
    out = subprocess.run(["python3", str(CORE), "brief"], capture_output=True, text=True, env=env).stdout
    assert out.splitlines()[0] == "NOT RUNNING THAT SHOULD BE"
    assert "audits has never run" in out.splitlines()[1]


# ---- step-3 final-review fix pass ----

def test_hung_job_alarms_and_timeout_cannot_be_bypassed(tmp_path):
    # A grandchild that escapes the process group must not wedge core run or hide the job.
    passes(tmp_path, "expect c every 1m\n")
    start = time.time()
    run_core(tmp_path, "run", "c", "--timeout", "2", "--", "python3", "-c",
             "import os,time\nif os.fork()==0:\n os.setsid(); time.sleep(20)\nelse:\n time.sleep(30)")
    assert time.time() - start < 10
    assert records(tmp_path)["c"]["status"] == "timeout"


def test_long_running_job_with_lease_held_alarms(tmp_path):
    passes(tmp_path, "expect audits every 1m\n")
    job = subprocess.Popen(["python3", str(CORE), "run", "audits", "--", "sleep", "200"], env=env_for(tmp_path))
    time.sleep(0.7)
    data = records(tmp_path)
    data["audits"]["started"] = ago(minutes=5)
    (tmp_path / "corehome" / "heartbeat.json").write_text(json.dumps(data))
    r = run_core(tmp_path, "heartbeat")
    job.kill(); job.wait()
    assert r.returncode == 1 and "audits has been running for 5 min" in r.stdout


def test_terminating_core_run_kills_its_job(tmp_path):
    marker = "hb-term-{}".format(os.getpid())
    job = subprocess.Popen(["python3", str(CORE), "run", "a", "--", "sh", "-c", "sleep 30 # {}".format(marker)],
                           env=env_for(tmp_path))
    time.sleep(0.8)
    job.terminate(); job.wait()
    time.sleep(0.5)
    left = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.strip()
    assert left == ""
    assert records(tmp_path)["a"]["status"] == "killed"


def test_next_run_refuses_while_orphaned_group_alive(tmp_path):
    # If the wrapper died hard, its job may still run: the next run must not overlap it or clear the alarm.
    passes(tmp_path, "expect a every 1d\n")
    orphan = subprocess.Popen(["sleep", "30"], start_new_session=True)
    put_record(tmp_path, "a", status="running", started=ago(minutes=2), pgid=orphan.pid, last_line="")
    r = run_core(tmp_path, "run", "a", "--", "echo", "second")
    hb = run_core(tmp_path, "heartbeat")
    orphan.kill(); orphan.wait()
    assert "skipped" in r.stdout and records(tmp_path)["a"]["status"] == "running"
    assert "never finished" in hb.stdout


def test_background_child_does_not_cause_false_timeout(tmp_path):
    start = time.time()
    r = run_core(tmp_path, "run", "b", "--timeout", "8", "--", "sh", "-c", "echo hi; (sleep 20 &); exit 0")
    assert time.time() - start < 6
    rec = records(tmp_path)["b"]
    assert rec["status"] == "ok" and rec["last_line"] == "hi" and r.returncode == 0


def test_large_output_streams_without_buffering(tmp_path):
    r = run_core(tmp_path, "run", "big", "--", "python3", "-c",
                 "import sys\nfor i in range(200000): sys.stdout.write('x'*500+'\\n')\nprint('the end')")
    assert records(tmp_path)["big"]["last_line"] == "the end"
    assert r.returncode == 0


def test_bad_passes_conf_lines_alarm(tmp_path):
    passes(tmp_path, "expect a every 1d\nexpect b every 30s\nExpect c every 1d\nexpect d every 1h  # nightly\n")
    put_record(tmp_path, "a", status="ok", exit=0, started=ago(hours=1), finished=ago(hours=1), last_line="")
    put_record(tmp_path, "d", status="ok", exit=0, started=ago(minutes=5), finished=ago(minutes=5), last_line="")
    out = run_core(tmp_path, "heartbeat").stdout
    assert "passes.conf line 2 not understood: expect b every 30s" in out
    assert "passes.conf line 3 not understood" in out
    assert "line 4" not in out  # trailing comments are fine


def test_name_typo_is_pointed_out(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    put_record(tmp_path, "audit", status="ok", exit=0, started=ago(hours=1), finished=ago(hours=1), last_line="")
    out = run_core(tmp_path, "heartbeat").stdout
    assert "audits has never run (expected every 1d; recorded but not expected: audit)" in out


# ---- hardening B: no silent paths ----

def ahead(**kw):
    return (datetime.now().astimezone() + timedelta(**kw)).isoformat(timespec="seconds")


def test_future_finish_alarms(tmp_path):
    # A record "finished in the future" would never go overdue: that's a silent path.
    passes(tmp_path, "expect audits every 1d\n")
    put_record(tmp_path, "audits", status="ok", exit=0, started=ahead(days=3000), finished=ahead(days=3000),
               last_line="")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 1 and "audits has a run record dated in the future" in r.stdout


def test_unknown_status_alarms(tmp_path):
    passes(tmp_path, "expect audits every 1d\n")
    put_record(tmp_path, "audits", status="weird", started=ago(hours=1), finished=ago(hours=1), last_line="")
    r = run_core(tmp_path, "heartbeat")
    assert r.returncode == 1 and "audits has an unrecognized status: weird" in r.stdout


def test_zero_or_negative_timeout_clamped_in_both_positions(tmp_path):
    for args in (["run", "--timeout", "0", "z", "--", "echo", "hi"],
                 ["run", "z", "--timeout", "-5", "--", "echo", "hi"]):
        r = run_core(tmp_path, *args)
        assert r.returncode == 0 and "hi" in r.stdout, args
        assert records(tmp_path)["z"]["status"] == "ok"


def test_unwritable_state_still_runs_job(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir()
    os.chmod(str(h), 0o500)
    try:
        r = run_core(tmp_path, "run", "w", "--", "echo", "job ran")
    finally:
        os.chmod(str(h), 0o755)
    assert "job ran" in r.stdout
    assert r.returncode == 0
    assert "WARNING" in r.stderr and "Traceback" not in r.stderr


def test_heartbeat_check_never_takes_the_lease(tmp_path):
    # The checker must not briefly hold a job's lease (a run starting that instant would be skipped).
    passes(tmp_path, "expect audits every 1d\n")
    put_record(tmp_path, "audits", status="running", started=ago(minutes=1), pid=999999, pgid=999999,
               last_line="")
    lease = tmp_path / "corehome" / "leases" / "audits.lock"
    lease.parent.mkdir(parents=True, exist_ok=True)
    lease.write_text("")
    os.chmod(str(lease), 0o000)  # any attempt to open it would fail loudly
    try:
        r = run_core(tmp_path, "heartbeat")
    finally:
        os.chmod(str(lease), 0o644)
    assert "Traceback" not in r.stderr
    assert "audits started 1 min ago and never finished" in r.stdout

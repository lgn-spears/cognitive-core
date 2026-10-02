"""Frozen-clock tests for lifelog's pure logic."""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"
sys.path.insert(0, str(CORE.parent))

import importlib.util
from importlib.machinery import SourceFileLoader

loader = SourceFileLoader("core", str(CORE))
spec = importlib.util.spec_from_loader("core", loader)
core_mod = importlib.util.module_from_spec(spec)
loader.exec_module(core_mod)


def test_gap_vocabulary():
    now = datetime(2026, 8, 22, 23, 40)
    cases = [
        (timedelta(seconds=30), "just now"),
        (timedelta(minutes=5), "5 min ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=6), "6 hours ago"),
        (timedelta(days=1), "yesterday"),
        (timedelta(days=4), "4 days ago"),
        (timedelta(days=21), "3 weeks ago"),
    ]
    for delta, expected in cases:
        assert core_mod.human_gap(delta) == expected


def test_negative_gap_clamped():
    assert core_mod.human_gap(timedelta(hours=-3)) == "just now"


def test_block_mentions_sleep_rule_once():
    block = core_mod.render_block(
        datetime(2026, 8, 22, 23, 40), None, []
    )
    assert block.count("sleep/rest suggestion") == 1
    assert "none on record" in block


def test_block_shows_last_activity_and_journal_tail():
    now = datetime(2026, 8, 22, 23, 40)
    last = now - timedelta(days=3)
    entries = [{"ts": "2026-08-19T01:10:00", "text": "suggested a break; they kept working"}]
    block = core_mod.render_block(now, last, entries)
    assert "LAST ACTIVITY" in block and "3 days ago" in block
    assert "suggested a break" in block


def test_journal_rotates_to_cap():
    state = {"last_seen": None, "journal": [{"ts": str(i), "text": "e"} for i in range(80)]}
    core_mod.state_file = lambda: Path("/tmp/never-used")  # not touched by save below
    # emulate the rotation save_state performs:
    state["journal"] = state["journal"][-core_mod.MAX_JOURNAL:]
    assert len(state["journal"]) == core_mod.MAX_JOURNAL


def roundtrip(tmp_home: Path, *args):
    env = {"PATH": "/usr/bin:/bin", "CORE_HOME": str(tmp_home), "HOME": str(tmp_home)}
    return subprocess.run(
        [sys.executable, str(CORE), *args], capture_output=True, text=True, env=env
    )


def test_cli_roundtrip(tmp_path):
    first = roundtrip(tmp_path, "inject")
    assert "none on record" in first.stdout

    logged = roundtrip(tmp_path, "log", "suggested a break")
    assert "logged" in logged.stdout

    second = roundtrip(tmp_path, "inject")
    out = second.stdout
    assert "none on record" not in out          # last activity now exists
    assert "suggested a break" in out           # journal surfaced
    assert "just now" in out or "min ago" in out
    assert "MEMORY:" in out                     # searchable-memory pointer injected

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_seen"] is not None
    assert state["journal"][0]["text"] == "suggested a break"

    # v0.2: inject wrote a session-start line into today's ledger
    days = tmp_path / "days"
    pages = list(days.glob("*.log"))
    assert len(pages) == 1
    assert "session start" in pages[0].read_text()


def test_search_spans_days(tmp_path):
    import os
    from datetime import datetime

    env_home = tmp_path
    env_home.mkdir(exist_ok=True)
    days = env_home / "days"
    days.mkdir()
    (days / "2026-08-21.log").write_text("[09:00] session start (work)\n[10:00] note: fixed auth bug\n")
    (days / "2026-08-22.log").write_text("[23:00] note: auth regression appeared\n")

    env = dict(os.environ, CORE_HOME=str(env_home))
    result = subprocess.run(
        [sys.executable, str(CORE), "search", "auth"],
        capture_output=True, text=True, env=env,
    )
    assert "2026-08-21" in result.stdout
    assert "2026-08-22" in result.stdout
    assert "fixed auth bug" in result.stdout
    assert "auth regression" in result.stdout
    assert "2 match(es)" in result.stdout


def test_day_command_scopes_to_date(tmp_path):
    import os

    days = tmp_path / "days"
    days.mkdir(parents=True)
    (days / "2026-08-01.log").write_text("[08:00] old day\n")

    env = dict(os.environ, CORE_HOME=str(tmp_path))
    hit = subprocess.run(
        [sys.executable, str(CORE), "day", "2026-08-01"],
        capture_output=True, text=True, env=env,
    )
    miss = subprocess.run(
        [sys.executable, str(CORE), "day", "2026-07-31"],
        capture_output=True, text=True, env=env,
    )
    assert "old day" in hit.stdout
    assert "no ledger" in miss.stdout


def test_doctor_flags_overdue_loops(tmp_path):
    import os
    days = tmp_path / "days"
    days.mkdir(parents=True)
    (tmp_path / "loops.md").write_text("- [ ] 2026-08-01 fix the CI\n")
    env = dict(os.environ, CORE_HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, str(CORE), "doctor"],
        capture_output=True, text=True, env=env,
    )
    assert "OVERDUE" in result.stdout
    assert result.returncode == 1


def test_doctor_clean_store_passes(tmp_path):
    import os
    roundtrip(tmp_path, "inject")  # initialize store so state.json exists
    (tmp_path / "loops.md").write_text("")
    env = dict(os.environ, CORE_HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, str(CORE), "doctor"],
        capture_output=True, text=True, env=env,
    )
    assert "healthy" in result.stdout
    assert result.returncode == 0

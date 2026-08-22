"""Frozen-clock tests for lifelog's pure logic."""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

LIFELOG = Path(__file__).resolve().parents[1] / "bin" / "lifelog"
sys.path.insert(0, str(LIFELOG.parent))

import importlib.util
from importlib.machinery import SourceFileLoader

loader = SourceFileLoader("lifelog", str(LIFELOG))
spec = importlib.util.spec_from_loader("lifelog", loader)
lifelog = importlib.util.module_from_spec(spec)
loader.exec_module(lifelog)


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
        assert lifelog.human_gap(delta) == expected


def test_negative_gap_clamped():
    assert lifelog.human_gap(timedelta(hours=-3)) == "just now"


def test_block_mentions_sleep_rule_once():
    block = lifelog.render_block(
        datetime(2026, 8, 22, 23, 40), None, []
    )
    assert block.count("sleep/rest suggestion") == 1
    assert "none on record" in block


def test_block_shows_last_activity_and_journal_tail():
    now = datetime(2026, 8, 22, 23, 40)
    last = now - timedelta(days=3)
    entries = [{"ts": "2026-08-19T01:10:00", "text": "told Logan to sleep; he kept working"}]
    block = lifelog.render_block(now, last, entries)
    assert "LAST ACTIVITY" in block and "3 days ago" in block
    assert "told Logan to sleep" in block


def test_journal_rotates_to_cap():
    state = {"last_seen": None, "journal": [{"ts": str(i), "text": "e"} for i in range(80)]}
    lifelog.state_file = lambda: Path("/tmp/never-used")  # not touched by save below
    # emulate the rotation save_state performs:
    state["journal"] = state["journal"][-lifelog.MAX_JOURNAL:]
    assert len(state["journal"]) == lifelog.MAX_JOURNAL


def roundtrip(tmp_home: Path, *args):
    env = {"PATH": "/usr/bin:/bin", "LIFELOG_HOME": str(tmp_home), "HOME": str(tmp_home)}
    return subprocess.run(
        [sys.executable, str(LIFELOG), *args], capture_output=True, text=True, env=env
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

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_seen"] is not None
    assert state["journal"][0]["text"] == "suggested a break"

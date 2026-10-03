"""Identity: an optional, user-authored identity.md opens every session's context, so every session on the
machine is the same named agent. Without the file nothing changes (the public install stays generic)."""

import os
import subprocess
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


def run(tmp_path, *args):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"],
           "CORE_NOW": "2026-10-02T21:20:00-04:00"}
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def test_identity_opens_the_session_context(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "identity.md").write_text("name: Ariadne\n\nYou are Ariadne, Sam's agent. Same memory in every session.\n"
                                   "Blunt, warm, no lectures.\n")
    out = run(tmp_path, "inject").stdout.splitlines()
    assert out[:4] == [
        "IDENTITY (identity.md, user-authored — this is who you are in every session):",
        "  name: Ariadne",
        "  You are Ariadne, Sam's agent. Same memory in every session.",
        "  Blunt, warm, no lectures.",
    ]
    assert out[4] == "[core] session context"


def test_without_identity_inject_is_unchanged(tmp_path):
    out = run(tmp_path, "inject").stdout
    assert out.startswith("[core] session context\n") and "IDENTITY" not in out


def test_an_empty_identity_file_adds_nothing(tmp_path):
    h = tmp_path / "corehome"
    h.mkdir()
    (h / "identity.md").write_text("\n  \n")
    assert run(tmp_path, "inject").stdout.startswith("[core] session context\n")


def test_no_agent_name_is_hard_coded_in_the_identity_or_home_code():
    src = CORE.read_text()
    for start, end in (("def identity_lines", "def standing_orders"), ("# ---- the home screen", "def main(")):
        assert "theseus" not in src[src.index(start):src.index(end)].lower()

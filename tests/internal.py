"""Test helper: deliver an item the way core's own producers do (sweep, evening, overnight, permissions).

The public `core deliver` can't: reserved sources, keys and tags are refused there. Tests that need an item a
producer would have made go through deliver_item(..., _internal=True) in a child process with the same
environment the CLI would see."""

import json
import os
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"

_SCRIPT = """
import importlib.machinery, importlib.util, json, sys
l = importlib.machinery.SourceFileLoader("core", sys.argv[1])
m = importlib.util.module_from_spec(importlib.util.spec_from_loader("core", l)); l.exec_module(m)
a = json.loads(sys.argv[2])
print(m.deliver_item(a.pop("text"), a.pop("source"), a.pop("key", ""), _internal=True, **a))
"""


def deliver_internal(env, text, source, key="", **kw):
    """env: the same dict the test's `run` passes to the CLI. kw: replace, offer, tags, skip_if_acked, ask."""
    args = dict(kw, text=text, source=source, key=key)
    r = subprocess.run([sys.executable, "-c", _SCRIPT, str(CORE), json.dumps(args)], capture_output=True,
                       text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def env_of(tmp_path, home=None, now=None):
    env = {"HOME": str(home or tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    if now:
        env["CORE_NOW"] = now
    return env

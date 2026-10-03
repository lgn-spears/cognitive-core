"""Step 8: the evening pass — a wrap for tomorrow + at most one insight offer that must cite evidence."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


class Fake(BaseHTTPRequestHandler):
    reply = {"offer": None}
    calls = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.calls.append(body)
        out = json.dumps({"message": {"role": "assistant", "content": json.dumps(Fake.reply)}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def model():
    Fake.reply, Fake.calls = {"offer": None}, []
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:{}".format(srv.server_port)
    srv.shutdown()


def run(tmp_path, *args):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"]}
    return subprocess.run(["python3", str(CORE), *args], capture_output=True, text=True, env=env, timeout=60)


def setup_day(tmp_path, url=None):
    (tmp_path / "corehome").mkdir(exist_ok=True)
    if url:
        (tmp_path / "corehome" / "recall.conf").write_text("sweep_model fake\nsweep_url {}\n".format(url))
    run(tmp_path, "decision", "SQLite over Postgres for the inventory app — single user, zero admin")
    run(tmp_path, "loop", "add", "renew the client's domain", "--due", "2000-01-01")
    run(tmp_path, "loop", "add", "send the invoice")


def test_wrap_summarizes_today_for_tomorrow(tmp_path):
    setup_day(tmp_path)
    run(tmp_path, "evening")
    inbox = run(tmp_path, "inbox").stdout
    assert "SQLite over Postgres" in inbox and "renew the client's domain" in inbox and "overdue" in inbox


def test_wrap_does_not_repeat_what_the_morning_already_showed(tmp_path):
    setup_day(tmp_path)
    mid = run(tmp_path, "deliver", "3 repos have no backup", "--source", "audits", "--key", "audit:x").stdout.strip()
    run(tmp_path, "inbox", "ack", mid)
    run(tmp_path, "evening")
    assert "no backup" not in run(tmp_path, "inbox").stdout


def test_insight_must_cite_real_lines_or_it_is_dropped(tmp_path, model):
    setup_day(tmp_path, model)
    Fake.reply = {"offer": {"text": "Your domain renewal is overdue and the invoice loop mentions the same client.",
                            "evidence": ["this line was never written anywhere"]}}
    run(tmp_path, "evening")
    assert "domain renewal is overdue and" not in run(tmp_path, "inbox").stdout


def test_insight_with_evidence_becomes_one_offer(tmp_path, model):
    setup_day(tmp_path, model)
    Fake.reply = {"offer": {"text": "The overdue domain renewal and the unsent invoice are for the same client — one email could do both.",
                            "evidence": ["renew the client's domain", "send the invoice"]}}
    run(tmp_path, "evening")
    out = run(tmp_path, "inbox").stdout
    assert out.count("one email could do both") == 1 and "offer" in out
    run(tmp_path, "evening")  # running twice the same night doesn't double anything
    assert run(tmp_path, "inbox").stdout.count("one email could do both") == 1


def test_nothing_good_means_no_offer(tmp_path, model):
    setup_day(tmp_path, model)
    Fake.reply = {"offer": None}
    run(tmp_path, "evening")
    assert " offer," not in run(tmp_path, "inbox").stdout


def test_evidence_must_be_one_real_line_not_a_splice(tmp_path, model):
    setup_day(tmp_path, model)
    Fake.reply = {"offer": {"text": "Two loops are related.", "evidence": ["renew the client's domain open loop (due"]}}
    run(tmp_path, "evening")
    assert "Two loops are related" not in run(tmp_path, "inbox").stdout


def test_evening_survives_a_bad_byte(tmp_path):
    setup_day(tmp_path)
    from datetime import date
    with open(str(tmp_path / "corehome" / "days" / (date.today().isoformat() + ".log")), "ab") as fh:
        fh.write(b"[21:00] x \xff\xfe\n")
    r = run(tmp_path, "evening")
    assert r.returncode == 0 and "Evening wrap" in run(tmp_path, "inbox").stdout

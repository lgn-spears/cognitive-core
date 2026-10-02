"""Optional meaning-based recall (embeddings via a local Ollama-compatible server).

A fake /api/embed server stands in for Ollama: vectors are bags of "concepts", with a few synonyms
mapped to the same concept, so meaning matches that share no words can be tested deterministically."""

import hashlib
import json
import math
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "bin" / "core"
DIM = 2048
SYNONYMS = {"forecasting": "timeseries", "predict": "timeseries", "series": "timeseries",
            "livestream": "streaming", "broadcast": "streaming", "camera": "streaming"}


def fake_vec(text):
    v = [0.0] * DIM
    for w in text.lower().replace(":", " ").replace("-", " ").split():
        w = SYNONYMS.get(w.strip(".,?!"), w.strip(".,?!"))
        if len(w) < 4:
            continue
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Fake(BaseHTTPRequestHandler):
    calls = []
    delay = 0.0
    down = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.calls.append(len(body["input"]))
        if Fake.down:
            self.send_response(500); self.end_headers(); return
        time.sleep(Fake.delay)
        out = json.dumps({"embeddings": [fake_vec(t.split("Query: ")[-1]) for t in body["input"]]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    os.environ["PYTHONHASHSEED"] = "0"
    Fake.calls, Fake.delay, Fake.down = [], 0.0, False
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:{}".format(srv.server_address[1])
    srv.shutdown()


def setup(tmp_path, url, notes, embed=True):
    mem = tmp_path / "mem"
    mem.mkdir()
    for name, text in notes.items():
        (mem / name).write_text(text)
    for i in range(40):  # an ordinary memory around the notes under test
        (mem / "misc{}.md".format(i)).write_text("unrelated note about gardening topic {} and weather\n".format(i))
    h = tmp_path / "corehome"
    h.mkdir()
    conf = "memory_dir {}\n".format(mem)
    if embed:
        conf += "embed_model fake-embed\nembed_url {}\n".format(url)
    (h / "recall.conf").write_text(conf)
    return mem


def core(tmp_path, *args, stdin=None):
    env = {"HOME": str(tmp_path), "CORE_HOME": str(tmp_path / "corehome"), "PATH": os.environ["PATH"],
           "PYTHONHASHSEED": "0"}
    return subprocess.run(["python3", str(CORE), *args], input=stdin, capture_output=True, text=True,
                          env=env, timeout=60)


def ask(tmp_path, text):
    return core(tmp_path, "recall", stdin=json.dumps({"prompt": text})).stdout


NOTES = {"reference_timesfm.md": "description: TimesFM is a timeseries foundation model from Google\n",
         "project_av_chain.md": "description: church streaming setup with an ATEM switcher\n"}


def test_reindex_builds_and_is_incremental(server, tmp_path):
    mem = setup(tmp_path, server, NOTES)
    r = core(tmp_path, "recall", "--reindex")
    assert r.returncode == 0 and "indexed" in r.stdout
    first = sum(Fake.calls)
    Fake.calls.clear()
    core(tmp_path, "recall", "--reindex")
    assert sum(Fake.calls) == 0  # nothing changed, nothing re-embedded
    time.sleep(1.1)
    (mem / "reference_timesfm.md").write_text("description: TimesFM 2 is a timeseries model\n")
    core(tmp_path, "recall", "--reindex")
    assert 0 < sum(Fake.calls) < first  # only the changed file


def test_meaning_match_without_shared_words(server, tmp_path):
    # The point of embeddings: "forecasting model" finds a note that never says "forecasting".
    setup(tmp_path, server, NOTES)
    core(tmp_path, "recall", "--reindex")
    out = ask(tmp_path, "which forecasting model did I send you")
    assert "reference_timesfm.md" in out


def test_without_embeddings_meaning_match_is_missed(server, tmp_path):
    setup(tmp_path, server, NOTES, embed=False)
    assert "reference_timesfm.md" not in ask(tmp_path, "which forecasting model did I send you")


def test_server_down_falls_back_to_words_quickly(server, tmp_path):
    setup(tmp_path, server, NOTES)
    core(tmp_path, "recall", "--reindex")
    Fake.down = True
    start = time.time()
    out = ask(tmp_path, "the ATEM switcher setup")
    assert time.time() - start < 3 and "project_av_chain.md" in out


def test_slow_server_times_out_and_falls_back(server, tmp_path):
    setup(tmp_path, server, NOTES)
    core(tmp_path, "recall", "--reindex")
    Fake.delay = 5
    start = time.time()
    r = core(tmp_path, "recall", stdin=json.dumps({"prompt": "the ATEM switcher setup"}))
    assert r.returncode == 0 and time.time() - start < 3


def test_index_from_another_model_is_ignored(server, tmp_path):
    setup(tmp_path, server, NOTES)
    core(tmp_path, "recall", "--reindex")
    conf = tmp_path / "corehome" / "recall.conf"
    conf.write_text(conf.read_text().replace("fake-embed", "other-model"))
    assert "reference_timesfm.md" not in ask(tmp_path, "which forecasting model did I send you")


def test_vague_message_stays_silent(server, tmp_path):
    setup(tmp_path, server, NOTES)
    core(tmp_path, "recall", "--reindex")
    assert ask(tmp_path, "hmm interesting, thoughts?") == ""


def test_large_index_is_fast(server, tmp_path):
    notes = {"n{}.md".format(i): "description: note {} about topic{} and thing{}\n".format(i, i % 50, i % 7)
             for i in range(3000)}
    setup(tmp_path, server, notes)
    core(tmp_path, "recall", "--reindex")
    start = time.time()
    core(tmp_path, "recall", stdin=json.dumps({"prompt": "topic12 thing3 notes"}))
    assert time.time() - start < 1.5


def test_hit_shows_the_description_not_frontmatter(server, tmp_path):
    notes = {"reference_timesfm.md": "---\nname: timesfm\ndescription: TimesFM is a timeseries foundation model\n---\n\nBody text.\n"}
    setup(tmp_path, server, notes)
    core(tmp_path, "recall", "--reindex")
    out = ask(tmp_path, "which forecasting model did I send you")
    line = [l for l in out.splitlines() if "reference_timesfm.md" in l][0]
    assert "TimesFM is a timeseries foundation model" in line and not line.rstrip().endswith("---")


def test_session_start_refreshes_a_stale_index_in_background(server, tmp_path):
    mem = setup(tmp_path, server, NOTES)
    core(tmp_path, "recall", "--reindex")
    time.sleep(1.1)
    (mem / "project_new.md").write_text("description: brand new note about the forecasting dashboard\n")
    start = time.time()
    core(tmp_path, "inject")
    assert time.time() - start < 3  # never makes the person wait
    for _ in range(30):
        meta = json.loads((tmp_path / "corehome" / "recall-index.json").read_text())
        if any(c["path"].endswith("project_new.md") for c in meta["chunks"]):
            break
        time.sleep(0.3)
    else:
        raise AssertionError("stale index was not refreshed")

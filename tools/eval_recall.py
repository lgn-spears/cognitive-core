#!/usr/bin/env python3
"""Score `core recall` against a labeled set of real messages.

Usage: tools/eval_recall.py LABELS.json [--split dev|holdout|all] [--show]

LABELS.json: [{"prompt": str, "expect": "recall"|"silent", "relevant": [file-stem substrings], "split": str}]
Keep labeled data private — it is built from your own messages. This script is generic.

Metrics (the bar is set in your plan before tuning, never after):
  silent_precision  share of "silent" prompts that produce no hits
  hit_at_3          share of "recall" prompts whose relevant file is in the top 3 hits
  noise_free        share of all shown hits that come from a relevant file
  p95_ms            95th-percentile latency over the real memory corpus
"""
import argparse
import json
import time
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "bin" / "core"


def load_core():
    loader = SourceFileLoader("core", str(CORE))
    mod = module_from_spec(spec_from_loader("core", loader))
    loader.exec_module(mod)
    return mod


def relevant(path, subs):
    stem = Path(path).stem.lower()
    return any(s.lower() in stem for s in subs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    core = load_core()
    items = [x for x in json.load(open(a.labels)) if a.split == "all" or x["split"] == a.split]
    files = core.recall_sources()
    silent_ok = silent_n = hit = recall_n = shown = good = 0
    times = []
    for it in items:
        t0 = time.time()
        hits = core.recall_hits(it["prompt"], files)
        times.append((time.time() - t0) * 1000)
        top = [str(f) for f, _, _ in hits[:3]]
        shown += len(hits)
        good += sum(1 for f, _, _ in hits if relevant(f, it["relevant"]))
        if it["expect"] == "silent":
            silent_n += 1
            silent_ok += not hits
            ok = not hits
        else:
            recall_n += 1
            ok = any(relevant(f, it["relevant"]) for f in top)
            hit += ok
        if a.show and not ok:
            print("MISS [{}] {}".format(it["expect"], it["prompt"][:90].replace("\n", " ")))
            for f, n, _ in hits[:3]:
                print("     -> {}:{}".format(Path(f).name, n))
    times.sort()
    p95 = times[int(len(times) * 0.95) - 1] if times else 0
    print(json.dumps({
        "split": a.split, "n": len(items),
        "silent_precision": round(silent_ok / silent_n, 3) if silent_n else None,
        "hit_at_3": round(hit / recall_n, 3) if recall_n else None,
        "noise_free": round(good / shown, 3) if shown else None,
        "p95_ms": round(p95, 1),
    }))


if __name__ == "__main__":
    main()

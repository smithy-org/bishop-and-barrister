#!/usr/bin/env python3
"""Minimal Jev (TypeSafe System One) client, standard library only.

The key comes from the environment variable TYPESAFE_API_KEY, else from a file in the user's home folder. It is
never printed or written anywhere. Every attempt is counted in results/call_count.json against a hard cap.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
HARD_CAP = 2000
DELAY_S = 0.25
HERE = Path(__file__).resolve().parent
COUNT_FILE = HERE / "results" / "call_count.json"
KEY_FILE = Path.home() / ".bishop-and-barrister-secrets" / "typesafe_api_key"


def _key():
    k = os.environ.get("TYPESAFE_API_KEY")
    if not k and KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
    if not k:
        raise SystemExit("no TYPESAFE_API_KEY and no key file")
    return k


def _count():
    try:
        return json.loads(COUNT_FILE.read_text(encoding="utf-8"))["calls"]
    except (OSError, ValueError, KeyError):
        return 0


def _bump():
    COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNT_FILE.write_text(json.dumps({"calls": _count() + 1}), encoding="utf-8")


def call(state, questions, retries=5):
    """One System One request. Returns {"response": dict, "latency_ms": float}. Raises after the retries."""
    body = json.dumps({"state": state, "model": MODEL, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, method="POST",
        headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    wait = 2.0
    last = None
    for _ in range(retries):
        if _count() >= HARD_CAP:
            raise SystemExit("hard cap of %d Jev calls reached" % HARD_CAP)
        _bump()  # every attempt counts against the cap
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            ms = (time.perf_counter() - t0) * 1000
            time.sleep(DELAY_S)
            return {"response": data, "latency_ms": round(ms, 1)}
        except urllib.error.HTTPError as e:
            last = "HTTP %d: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
            if e.code == 429 or e.code >= 500:
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError(last)
        except (urllib.error.URLError, TimeoutError) as e:
            last = "network: %s" % e
            time.sleep(wait)
            wait *= 2
    raise RuntimeError("gave up after %d attempts: %s" % (retries, last))


def choice(instructions, criteria):
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def noul(instructions, true=None, false=None):
    q = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true, "false": false}
    return q

"""Tests for the optional remote store: scripts/s3.py and `judge.py sync`.

By default the two-device tests run against a tiny in-process stand-in for S3 (it checks that requests are
signed, not the signatures themselves). Point them at a real RustFS instead with:

    BISHOP_AND_BARRISTER_TEST_S3_ENDPOINT=http://127.0.0.1:19000 \\
    BISHOP_AND_BARRISTER_S3_ACCESS_KEY=... BISHOP_AND_BARRISTER_S3_SECRET_KEY=... \\
    python -m unittest tests.test_sync

    python -m unittest discover -s tests
"""

import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import escape

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import s3  # noqa: E402

LIVE = os.environ.get("BISHOP_AND_BARRISTER_TEST_S3_ENDPOINT")

CR = """Magic: The Gathering Comprehensive Rules

These rules are effective as of September 25, 2026.

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

613. Interaction of Continuous Effects

613.8. Within a layer or sublayer, determining which order effects are applied in is sometimes done using a dependency system.

Glossary

Credits
"""


class FakeS3(BaseHTTPRequestHandler):
    """Just enough S3 for sync: path-style buckets, GET/PUT/HEAD objects, ListObjectsV2. Unsigned requests
    are refused unless the server is made public, so the privacy check has something to find."""

    buckets: dict = {}
    public = False

    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _route(self):
        url = urlparse(self.path)
        parts = unquote(url.path).lstrip("/").split("/", 1)
        return parts[0], (parts[1] if len(parts) > 1 else ""), parse_qs(url.query)

    def _authorized(self):
        if self.public or self.headers.get("Authorization", "").startswith("AWS4-HMAC-SHA256"):
            return True
        self._send(403, b"<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>")
        return False

    def do_HEAD(self):
        if not self._authorized():
            return
        bucket, key, _ = self._route()
        if bucket not in self.buckets or (key and key not in self.buckets[bucket]):
            return self._send(404)
        self._send(200, headers={"ETag": self._etag(self.buckets[bucket][key])} if key else None)

    def do_GET(self):
        if not self._authorized():
            return
        bucket, key, query = self._route()
        if bucket not in self.buckets:
            return self._send(404, b"<Error><Code>NoSuchBucket</Code></Error>")
        objects = self.buckets[bucket]
        if key:
            return self._send(200, objects[key]) if key in objects else self._send(404, b"<Error><Code>NoSuchKey</Code></Error>")
        prefix = query.get("prefix", [""])[0]
        items = "".join(f"<Contents><Key>{escape(k)}</Key><ETag>{self._etag(v)}</ETag><Size>{len(v)}</Size></Contents>"
                        for k, v in sorted(objects.items()) if k.startswith(prefix))
        body = f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">{items}<IsTruncated>false</IsTruncated></ListBucketResult>'
        self._send(200, body.encode("utf-8"))

    def do_PUT(self):
        if not self._authorized():
            return
        bucket, key, _ = self._route()
        data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not key:
            self.buckets.setdefault(bucket, {})
            return self._send(200)
        if bucket not in self.buckets:
            return self._send(404)
        self.buckets[bucket][key] = data
        self._send(200, headers={"ETag": self._etag(data)})

    @staticmethod
    def _etag(data):
        return f'"{hashlib.md5(data).hexdigest()}"'


def ruling(question, answer):
    return {
        "question_type": "interaction", "question": question, "aliases": [], "mechanics": [],
        "agent_summary": answer, "applies_when": [{"fact": "Both cards on the battlefield"}],
        "answer_changes_if": [], "ask_if_unknown": [], "misconceptions": [], "ruling": answer,
        "steps": [{"n": 1, "text": answer, "refs": ["c1"]}],
        "citations": [{"id": "c1", "doc": "cr", "ref": "613.8"}], "cards": [], "confidence": "certain",
    }


class SigningTest(unittest.TestCase):
    def test_matches_aws_published_example(self):
        # AWS's documented Signature Version 4 example for S3 (GET Object with a Range header).
        headers = s3.sign("GET", "examplebucket.s3.amazonaws.com", "/test.txt", {}, {"Range": "bytes=0-9"},
                          s3.EMPTY_SHA256, "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                          "us-east-1", datetime(2013, 5, 24, tzinfo=timezone.utc))
        self.assertTrue(headers["authorization"].endswith(
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))

    def test_plain_http_only_for_local_hosts(self):
        for ok in ("http://localhost:9000", "http://127.0.0.1:9000", "http://192.168.1.20:9000", "http://10.0.0.159",
                   "https://rustfs.example.net"):
            s3.check_endpoint(ok)
        for bad in ("http://8.8.8.8:9000", "ftp://localhost", "rustfs.example.net"):
            with self.assertRaises(ValueError, msg=bad):
                s3.check_endpoint(bad)

    def test_keys_come_from_the_environment_or_a_profile(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            creds = Path(tmp) / "credentials"
            creds.write_text("[rustfs]\naws_access_key_id = AK\naws_secret_access_key = SK\n", encoding="utf-8")
            os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(creds)
            self.assertIsNone(s3.credentials())
            self.assertEqual(s3.credentials("rustfs"), ("AK", "SK"))
            os.environ.update(BISHOP_AND_BARRISTER_S3_ACCESS_KEY="EK", BISHOP_AND_BARRISTER_S3_SECRET_KEY="ES")
            self.assertEqual(s3.credentials("rustfs"), ("EK", "ES"))


class SyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if LIVE:
            cls.endpoint, cls.server = LIVE, None
        else:
            FakeS3.buckets, FakeS3.public = {}, False
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeS3)
            threading.Thread(target=cls.server.serve_forever, daemon=True).start()
            cls.endpoint = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "cr.txt").write_text(CR, encoding="utf-8")
        self.bulk = self.root / "rulings.jsonl.gz"
        self.bulk.write_bytes(gzip.compress(b""))
        self.bucket = f"bab-test-{uuid.uuid4().hex[:8]}"
        self.keys = {k: v for k, v in os.environ.items() if k.startswith("BISHOP_AND_BARRISTER_S3_")}
        if not LIVE:
            self.keys = {"BISHOP_AND_BARRISTER_S3_ACCESS_KEY": "test", "BISHOP_AND_BARRISTER_S3_SECRET_KEY": "test"}
            FakeS3.public = False

    def tearDown(self):
        self.tmp.cleanup()

    def device(self, name, setup=True, **extra):
        home = self.root / name
        env = {k: v for k, v in os.environ.items() if not k.startswith("BISHOP_AND_BARRISTER_")}
        env.update(self.keys, BISHOP_AND_BARRISTER_HOME=str(home), BISHOP_AND_BARRISTER_CR=str(self.root / "cr.txt"),
                   BISHOP_AND_BARRISTER_OFFLINE="1", BISHOP_AND_BARRISTER_SYNC_INTERVAL="0")
        env.update(extra)

        def run(*args, ok=True):
            result = subprocess.run([sys.executable, str(SCRIPTS / "judge.py"), *args], capture_output=True,
                                    text=True, encoding="utf-8", env=env)
            if ok:
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return result

        run("build", "--rulings-file", str(self.bulk))
        if setup:
            run("sync", "--setup", "--endpoint", self.endpoint, "--bucket", self.bucket, "--device", name, "--create")
        run.home = home
        return run

    def record(self, run, question, answer):
        path = run.home.parent / f"{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(ruling(question, answer)), encoding="utf-8")
        result = run("record", str(path))
        self.record_stderr = result.stderr
        return result.stdout.split()[1]

    def test_local_only_by_default(self):
        a = self.device("a", setup=False)
        self.assertIn("Local only", a("sync").stdout)

    def test_setup_keeps_the_settings_out_of_git(self):
        a = self.device("a")
        self.assertTrue((a.home / "config.json").exists())
        self.assertIn("config.json", (a.home / ".gitignore").read_text(encoding="utf-8"))
        tracked = subprocess.run(["git", "-C", str(a.home), "ls-files"], capture_output=True, text=True).stdout
        self.assertNotIn("config.json", tracked)
        self.assertNotIn("SECRET", (a.home / "config.json").read_text(encoding="utf-8").upper())

    def test_two_devices_share_rulings_and_history(self):
        a, b = self.device("a"), self.device("b")
        rid = self.record(a, "Blood Moon and Urborg?", "No Swamps: dependency (CR 613.8).")
        self.assertIn("nothing new to upload", a("sync").stdout)  # recording already uploaded it
        self.assertIn("merged a", b("sync").stdout)
        self.assertIn(rid, b("search", "Urborg").stdout)
        log = subprocess.run(["git", "-C", str(b.home), "log", "--format=%B"], capture_output=True, text=True,
                             encoding="utf-8").stdout
        self.assertIn(f"Record unreviewed ruling {rid}", log)  # A's commit, with its trailers, not a copy
        self.assertIn("Drafted-by: model", log)
        rid2 = self.record(b, "Humility and Opalescence?", "Timestamp order (CR 613.8).")
        self.assertIn("merged b", a("sync").stdout)
        self.assertIn(rid2, a("search", "Opalescence").stdout)
        self.assertIn("nothing new", a("sync").stdout)

    def test_syncs_by_itself_on_use(self):
        a, b = self.device("a"), self.device("b")
        rid = self.record(a, "Blood Moon and Urborg?", "No Swamps: dependency (CR 613.8).")  # pushed on write
        search = b("search", "Urborg")  # pulled on read, no `sync` run
        self.assertIn(rid, search.stdout)
        self.assertIn("merged rulings from a", search.stderr)

    def test_reads_pull_at_most_once_per_interval(self):
        a, b = self.device("a"), self.device("b", BISHOP_AND_BARRISTER_SYNC_INTERVAL="3600")
        b("search", "anything", ok=False)  # the first read pulls (nothing there yet)
        rid = self.record(a, "Blood Moon and Urborg?", "No Swamps: dependency (CR 613.8).")
        self.assertNotIn(rid, b("search", "Urborg", ok=False).stdout)  # within the interval: no pull
        b("sync")  # forcing it
        self.assertIn(rid, b("search", "Urborg").stdout)

    def test_unreachable_store_never_blocks(self):
        a = self.device("a", BISHOP_AND_BARRISTER_S3_ENDPOINT="http://127.0.0.1:9")
        rid = self.record(a, "Blood Moon and Urborg?", "No Swamps: dependency (CR 613.8).")
        first = a("search", "Urborg")
        self.assertIn(rid, first.stdout)
        self.assertIn("Working from the local record", first.stderr + self.record_stderr)
        self.assertNotIn("sync paused", a("search", "Urborg").stderr)  # said once, not on every read
        self.assertNotEqual(a("sync", ok=False).returncode, 0)  # forcing it reports the failure

    def test_same_ruling_changed_on_both_devices_stops(self):
        a, b = self.device("a"), self.device("b")
        rid = self.record(a, "Blood Moon and Urborg?", "No Swamps: dependency (CR 613.8).")
        a("sync")
        b("sync")
        a("review", rid, "--user-said", "Agreed.")
        b("review", rid, "--user-said", "Agreed, as a house rule.", "--house-rule")
        result = b("sync", ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"rulings/{rid}.json", result.stderr)
        status = subprocess.run(["git", "-C", str(b.home), "status", "--porcelain"], capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), "")  # nothing half-merged left behind
        self.assertIn(rid, b("search", "Urborg").stdout)  # reads still work from the local record

    @unittest.skipIf(LIVE, "making a real bucket public isn't something a test should do")
    def test_public_bucket_is_refused(self):
        a = self.device("a")
        FakeS3.public = True
        result = a("sync", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Make the bucket private", result.stderr)


if __name__ == "__main__":
    unittest.main()

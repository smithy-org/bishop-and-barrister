"""Tests for the Scryfall client in scripts/card.py: headers, pacing, the 429 lockout and the cache.

urllib is replaced by a fake, so nothing touches the network.

    python -m unittest discover -s tests
"""

import email.message
import io
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import card  # noqa: E402


class FakeScryfall:
    """Stands in for urllib.request.urlopen: answers 429 for the first `limited` requests."""

    def __init__(self, limited=0, retry_after=None):
        self.limited = limited
        self.retry_after = retry_after
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append((time.monotonic(), req))
        if len(self.requests) <= self.limited:
            headers = email.message.Message()
            if self.retry_after:
                headers["Retry-After"] = self.retry_after
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", headers, io.BytesIO(b"{}"))
        return io.BytesIO(b'{"object": "card", "name": "Lightning Bolt"}')


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.object(card, "CACHE_DIR", Path(self.tmp.name)),
            mock.patch.object(card, "LOCKOUT", 0.3),
            mock.patch.object(card, "CARD_INTERVAL", 0.2),
            mock.patch("sys.stderr", io.StringIO()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, fake):
        p = mock.patch("urllib.request.urlopen", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def test_sends_the_required_headers(self):
        fake = self.serve(FakeScryfall())
        card.fetch(f"{card.API}/cards/named?fuzzy=bolt")
        req = fake.requests[0][1]
        self.assertEqual(req.get_header("User-agent"), "bishop-and-barrister/1.0")
        self.assertEqual(req.get_header("Accept"), "application/json")

    def test_card_endpoints_are_paced(self):
        fake = self.serve(FakeScryfall())
        for i in range(3):
            card.fetch(f"{card.API}/cards/named?fuzzy=card{i}")
        times = [t for t, _ in fake.requests]
        self.assertGreaterEqual(times[2] - times[0], 2 * 0.2 - 0.02)

    def test_file_origins_are_not_paced(self):
        fake = self.serve(FakeScryfall())
        start = time.monotonic()
        for _ in range(5):
            card.fetch("https://data.scryfall.io/rulings/rulings.json", accept="*/*")
        self.assertLess(time.monotonic() - start, 0.2)
        self.assertEqual(len(fake.requests), 5)

    def test_429_waits_out_the_lockout_then_retries(self):
        fake = self.serve(FakeScryfall(limited=1))
        card.fetch(f"{card.API}/cards/named?fuzzy=bolt")
        (first, _), (second, _) = fake.requests
        self.assertGreaterEqual(second - first, 0.3 - 0.02)

    def test_retry_after_longer_than_the_lockout_is_honoured(self):
        fake = self.serve(FakeScryfall(limited=1, retry_after="0.6"))
        card.fetch(f"{card.API}/cards/named?fuzzy=bolt")
        (first, _), (second, _) = fake.requests
        self.assertGreaterEqual(second - first, 0.6 - 0.02)

    def test_gives_up_after_the_retries(self):
        fake = self.serve(FakeScryfall(limited=10))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            card.fetch(f"{card.API}/cards/named?fuzzy=bolt")
        self.assertEqual(caught.exception.code, 429)
        self.assertEqual(len(fake.requests), card.RETRIES + 1)

    def test_lockout_is_shared_through_the_cache_dir(self):
        self.serve(FakeScryfall(limited=card.RETRIES + 1))
        with self.assertRaises(urllib.error.HTTPError):
            card.fetch(f"{card.API}/cards/named?fuzzy=bolt")
        # Another process reads the same state file and must wait too.
        self.assertGreater(card._state()["locked_until"], time.time())

    def test_get_caches_for_a_day(self):
        fake = self.serve(FakeScryfall())
        url = f"{card.API}/cards/named?fuzzy=bolt"
        self.assertEqual(card.get(url)["name"], "Lightning Bolt")
        self.assertEqual(card.get(url)["name"], "Lightning Bolt")
        self.assertEqual(len(fake.requests), 1)
        cached = next((Path(self.tmp.name) / "responses").iterdir())
        old = time.time() - card.CACHE_TTL - 1
        os.utime(cached, (old, old))
        card.get(url)
        self.assertEqual(len(fake.requests), 2)


if __name__ == "__main__":
    unittest.main()

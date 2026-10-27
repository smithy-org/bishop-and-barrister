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


BOLT = {
    "name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant",
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    "legalities": {"standard": "not_legal", "modern": "legal", "legacy": "legal", "vintage": "legal",
                   "pauper": "legal", "commander": "legal", "pioneer": "not_legal", "oathbreaker": "legal",
                   "brawl": "not_legal", "standardbrawl": "not_legal"},
    "rulings_uri": "https://api.scryfall.com/cards/bolt/rulings",
}
DFC = {
    "name": "Delver of Secrets // Insectile Aberration",
    "card_faces": [
        {"name": "Delver of Secrets", "mana_cost": "{U}", "type_line": "Creature — Human Wizard",
         "oracle_text": "At the beginning of your upkeep, look at the top card of your library.", "power": "1",
         "toughness": "1"},
        {"name": "Insectile Aberration", "mana_cost": "", "type_line": "Creature — Human Insect",
         "oracle_text": "Flying", "power": "3", "toughness": "2"},
    ],
    "legalities": {"vintage": "restricted", "legacy": "banned", "commander": "suspended"},
}
TEFERI = {"name": "Teferi", "mana_cost": "{2}{W}{U}", "type_line": "Legendary Planeswalker", "loyalty": "4",
          "oracle_text": "+1: Draw a card.", "legalities": {}}
BATTLE = {"name": "Invasion of Tarkir", "type_line": "Battle — Siege", "defense": "5", "legalities": {}}


class ShowTest(unittest.TestCase):
    """card.py's output: faces, legality grouped by status, rulings, and Scryfall's 404 answers."""

    def show(self, responses, name="x", rulings=False):
        def fake_get(url):
            value = responses[url.split("?")[0] if "rulings" in url else "named"]
            if isinstance(value, Exception):
                raise value
            return value
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(card, "get", fake_get), mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            status = card.show(name, rulings)
        return status, out.getvalue(), err.getvalue()

    def test_single_face_with_legality_and_rulings(self):
        rulings = {"data": [{"published_at": "2024-01-01", "source": "wotc", "comment": "It can target you."}]}
        status, out, _ = self.show({"named": BOLT, BOLT["rulings_uri"]: rulings}, rulings=True)
        self.assertEqual(status, 0)
        self.assertIn("Lightning Bolt  {R}\nInstant\nLightning Bolt deals 3 damage", out)
        self.assertIn("Legal: Modern, Legacy, Vintage, Pauper, Commander, Oathbreaker", out)
        self.assertIn("Not legal: Standard, Pioneer", out)
        self.assertIn("informational", out)
        self.assertIn("Rulings (1;", out)
        self.assertIn("[2024-01-01, wotc] It can target you.", out)

    def test_faces_and_unusual_statuses(self):
        _, out, _ = self.show({"named": DFC})
        self.assertIn("Delver of Secrets  {U}", out)
        self.assertIn("\n---\n", out)
        self.assertIn("3/2", out)
        self.assertIn("Restricted: Vintage", out)
        self.assertIn("Banned: Legacy", out)
        self.assertIn("Suspended: Commander", out)  # a status outside the usual four is still shown
        self.assertIn("Unknown: Standard", out)

    def test_loyalty_and_defense(self):
        _, out, _ = self.show({"named": TEFERI})
        self.assertIn("Loyalty: 4", out)
        _, out, _ = self.show({"named": BATTLE})
        self.assertIn("Defense: 5", out)

    def test_not_found_and_ambiguous(self):
        def not_found(body):
            return urllib.error.HTTPError("u", 404, "Not Found", email.message.Message(), io.BytesIO(body))
        status, _, err = self.show({"named": not_found(b'{"details": "Too many cards match ambiguous name"}')})
        self.assertEqual(status, 1)
        self.assertIn("Too many cards match", err)
        _, _, err = self.show({"named": not_found(b"not json")}, name="Zebra")
        self.assertIn("No card found matching 'Zebra'", err)
        with self.assertRaises(urllib.error.HTTPError):
            self.show({"named": urllib.error.HTTPError("u", 500, "Error", email.message.Message(), io.BytesIO(b""))})

    def test_main_looks_up_each_name(self):
        seen = []
        with mock.patch.object(card, "show", lambda name, rulings: seen.append((name, rulings)) or 0), \
                mock.patch.object(sys, "argv", ["card.py", "Bolt", "Delver", "--rulings"]):
            self.assertEqual(card.main(), 0)
        self.assertEqual(seen, [("Bolt", True), ("Delver", True)])


if __name__ == "__main__":
    unittest.main()

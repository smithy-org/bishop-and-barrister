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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "skills" / "bishop-and-barrister" / "scripts"))
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
        with mock.patch.object(card, "show", lambda name, rulings, lang: seen.append((name, rulings)) or 0), \
                mock.patch.object(sys, "argv", ["card.py", "Bolt", "Delver", "--rulings"]):
            self.assertEqual(card.main(), 0)
        self.assertEqual(seen, [("Bolt", True), ("Delver", True)])

    def test_main_reads_double_bracketed_names(self):
        seen = []
        question = "Does [[Blood Moon]] turn off [[?Urborg, Tomb of Yawgmoth]] or [[ Fire // Ice |MH2]]?"
        with mock.patch.object(card, "show", lambda name, rulings, lang: seen.append((name, rulings)) or 0), \
                mock.patch.object(sys, "argv", ["card.py", question, "[[!Blood Moon]]", "Ponder"]):
            self.assertEqual(card.main(), 0)
        self.assertEqual(seen, [("Blood Moon", False), ("Urborg, Tomb of Yawgmoth", True),
                                ("Fire // Ice", False), ("Ponder", False)])


    def test_main_passes_the_language_on(self):
        seen = []
        with mock.patch.object(card, "show", lambda name, rulings, lang: seen.append(lang) or 0),                 mock.patch.object(sys, "argv", ["card.py", "Blutmond", "--lang", "de"]):
            self.assertEqual(card.main(), 0)
        self.assertEqual(seen, ["de"])

    def test_show_prints_the_local_name(self):
        def fake_get(url):
            return BOLT if "/named" in url else {"data": [{"printed_name": "Fulmine"}]}
        out = io.StringIO()
        with mock.patch.object(card, "get", fake_get), mock.patch("sys.stdout", out):
            card.show("Lightning Bolt", False, "it")
        self.assertIn("Printed name in Italian: Fulmine", out.getvalue())


class PrintedNameTest(unittest.TestCase):
    """card.printed_name: the newest translated printing, faces joined, and none when never printed."""

    def printed(self, answer, name="Lightning Bolt", lang="it"):
        urls = []
        def fake_get(url):
            urls.append(url)
            if isinstance(answer, Exception):
                raise answer
            return answer
        with mock.patch.object(card, "get", fake_get):
            return card.printed_name(name, lang), urls

    def test_searches_the_exact_name_newest_first(self):
        name, urls = self.printed({"data": [{"printed_name": "Fulmine"}, {"printed_name": "Folgore"}]})
        self.assertEqual(name, "Fulmine")
        self.assertIn("/cards/search?q=%21%22Lightning%20Bolt%22%20lang%3Ait", urls[0])
        self.assertIn("order=released&dir=desc", urls[0])

    def test_faces_are_joined(self):
        faces = {"data": [{"card_faces": [{"printed_name": "火"}, {"printed_name": "氷"}]}]}
        self.assertEqual(self.printed(faces, "Fire // Ice", "ja")[0], "火 // 氷")

    def test_an_english_printed_name_is_the_last_resort(self):
        english_first = {"data": [
            {"card_faces": [{"printed_name": "Delver of Secrets"}, {"printed_name": "Insectile Aberration"}]},
            {"card_faces": [{"printed_name": "秘密を掘り下げる者"}, {"printed_name": "昆虫の逸脱者"}]},
        ]}
        name = "Delver of Secrets // Insectile Aberration"
        self.assertEqual(self.printed(english_first, name, "ja")[0], "秘密を掘り下げる者 // 昆虫の逸脱者")
        self.assertEqual(self.printed({"data": english_first["data"][:1]}, name, "ja")[0], name)

    def test_never_printed(self):
        missing = urllib.error.HTTPError("u", 404, "Not Found", email.message.Message(), io.BytesIO(b"{}"))
        self.assertIsNone(self.printed(missing)[0])
        self.assertIsNone(self.printed({"data": [{}]})[0])
        with self.assertRaises(urllib.error.HTTPError):
            self.printed(urllib.error.HTTPError("u", 500, "Error", email.message.Message(), io.BytesIO(b"")))


class CardRefsTest(unittest.TestCase):
    def test_plain_name_is_one_name(self):
        self.assertEqual(card.card_refs(" Lightning Bolt "), [("Lightning Bolt", False)])

    def test_brackets_prefixes_and_sets(self):
        self.assertEqual(card.card_refs("[[Blood Moon]]"), [("Blood Moon", False)])
        self.assertEqual(card.card_refs("[[?Humility]] and [[$Opalescence|DD3]]"),
                         [("Humility", True), ("Opalescence", False)])

    def test_unclosed_brackets_are_text(self):
        self.assertEqual(card.card_refs("[[Blood Moon"), [("[[Blood Moon", False)])


if __name__ == "__main__":
    unittest.main()

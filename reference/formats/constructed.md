---
checked: 2026-10-26
sources:
  cr: September 25, 2026
  mtr: February 27, 2026
---

# Constructed: Standard, Pioneer, Modern, Legacy, Vintage

| Rule              | Value                                                                       | Source (level)              |
| ----------------- | --------------------------------------------------------------------------- | --------------------------- |
| Deck              | At least 60 cards, no maximum                                               | CR 100.2a (1); MTR 6.1 (2)  |
| Copies            | At most four of a card by English name, deck and sideboard together; basic lands and cards that say otherwise are exempt | CR 100.2a, 100.4a (1); MTR 6.1 (2) |
| Sideboard         | Up to 15 cards, if used                                                     | CR 100.4a (1); MTR 6.1 (2)  |
| Starting life     | 20                                                                          | CR 103.4 (1)                |
| Card pool and bans | Each format's own section: Standard 6.3, Modern 6.4, Vintage 6.5 (it also restricts cards to one copy), Legacy 6.6, Pioneer 6.7 | MTR (2)          |

- **Banned and restricted lists change between sets.** The MTR's lists are as of its version; check
  magic.wizards.com/en/banned-restricted-list (level 1) or a card's legality with `card.py` (Scryfall, which
  says its legality data is informational).
- **Standard and Snow-Covered lands:** the MTR treats them as the matching basic lands where they aren't legal;
  players replace them when found, with no infraction (MTR 6.3).
- **Card legality in general:** a card is legal if it's from a set legal in the format or shares a name with
  one; a banned card can't be used; a restricted card is limited to one copy, deck and sideboard together
  (MTR 6.2).
- Matches, sideboarding and starting a game: `matches.md`.

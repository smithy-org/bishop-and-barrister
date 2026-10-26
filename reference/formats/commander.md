---
checked: 2026-10-26
sources:
  cr: September 25, 2026
---

# Commander

| Rule             | Value                                                                               | Source (level)        |
| ---------------- | ----------------------------------------------------------------------------------- | --------------------- |
| Deck             | Exactly 100 cards, including the commander                                          | CR 903.5a (1)         |
| Copies           | One of each card, basic lands excepted                                              | CR 903.5b (1)         |
| Colors           | Every card within the commander's color identity                                    | CR 903.4, 903.5c (1)  |
| Sideboard        | None                                                                                | CR 903.5e (1)         |
| Starting life    | 40                                                                                  | CR 103.4c (1)         |
| Commander damage | A player dealt 21 or more combat damage by the same commander over the game loses   | CR 903.10a (1)        |

- **The command zone:** the commander starts there (CR 103.2c, 903.6). Casting it from there costs {2} more for
  each earlier time that player cast it from the command zone *that game* (903.8). If it goes to the graveyard
  or exile, its owner may move it to the command zone the next time state-based actions are checked (903.9a).
  If it would go to its owner's hand or library, they may put it into the command zone instead, a replacement
  effect (903.9b).
- **Mulligans:** under the CR the first mulligan is free only in a multiplayer game (CR 103.5c). A two-player
  Commander game gets no free mulligan. Commander is usually multiplayer: see `matches.md`.
- **Each game starts fresh:** life totals, commander tax and commander damage all reset between games of a
  match (CR 903.6, 903.8, 903.10a count "that game").
- **Banned list:** Commander's is kept by Wizards (magic.wizards.com/en/formats/commander, level 1); `card.py`
  reports a card's Commander legality.
- Starting a game and matches: `matches.md`.

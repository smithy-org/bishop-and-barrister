# Formats and matches

The rules for each format this app offers, and for matches of more than one game. The
Comprehensive Rules (CR) cover gameplay, deck construction for Constructed, Limited, Commander and
Brawl, and starting a game; they do not cover tournament structure, which lives in the Magic
Tournament Rules (MTR), and they do not cover Oathbreaker at all. This file ties every fact to its
source so it can be checked.

As of 2026-10-20: CR effective 2026-09-25 (every CR number below was checked with
`scripts/lookup.py`; re-check after `update_rules.py` installs a new release, since rules get
renumbered), MTR effective 2026-02-27 (read through the judges' annotated pages), Wizards format
pages, and the Oathbreaker rules site (fan-run and undated).

## The formats this app offers

`SETUP_FORMATS` in `apps/activity/src/components/lobby/tableSetup.utils.ts`: Commander, Standard,
Pioneer, Modern, Legacy, Vintage, Pauper, Brawl, Oathbreaker, Draft and Sealed. Commander, Brawl and
Oathbreaker tables seat two to four players; every other format seats two.

## Decks and starting values

| Format                                     | Deck                                                                                                                                                                                    | Sideboard                                                              | Starting life                                 | Source                                                                    |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------- |
| Standard, Pioneer, Modern, Legacy, Vintage | At least 60; at most four of a card other than basic lands (Vintage restricts some cards to one)                                                                                        | Up to 15; the four-card limit covers deck and sideboard together       | 20                                            | CR 100.2a, 100.4a, 103.4; card pools and banned or restricted lists below |
| Pauper                                     | As above, commons only: a card is legal if it was ever released at common in paper or on MTGO                                                                                           | Up to 15                                                               | 20                                            | Wizards' Pauper page; CR 100.2a                                           |
| Draft, Sealed                              | At least 40; as many copies as the product held                                                                                                                                         | Every card in the pool not in the deck, plus any number of basic lands | 20                                            | CR 100.2b, 100.4b; MTR 3.16                                               |
| Commander                                  | Exactly 100 including the commander; one of each card other than basic lands; within the commander's color identity                                                                     | None                                                                   | 40; 21 combat damage from one commander loses | CR 903.4, 903.5a-e, 103.4c, 903.10a                                       |
| Brawl (CR)                                 | Exactly 60 including the commander; Commander rules otherwise                                                                                                                           | None                                                                   | 25 with two players, 30 with more             | CR 903.12a-h, 103.4d                                                      |
| Brawl (MTG Arena)                          | 100 cards, one-on-one                                                                                                                                                                   | None                                                                   | 25                                            | Wizards' Brawl page                                                       |
| Oathbreaker                                | Exactly 60 including a planeswalker (the Oathbreaker) and an instant or sorcery (the Signature Spell); one of each card other than basic lands; within the Oathbreaker's color identity | None; abilities that use cards from outside the game don't work        | 20                                            | Oathbreaker rules site only (its own numbering, 906.x, is not the CR's)   |

Commander extras: the commander starts in the command zone (CR 103.2c, 903.6) and costs {2} more
for each earlier cast from there "that game" (903.8); Brawl drops the commander-damage loss
(903.12h). Oathbreaker: both the Oathbreaker and the Signature Spell start in the command zone and
each costs {2} more per earlier cast from there; the Signature Spell can be cast only while its
Oathbreaker is on the battlefield, and it always returns to the command zone.

Card pools and banned or restricted lists change between sets and aren't in the CR: use
`scripts/card.py`, which reports each card's legality per format, or
magic.wizards.com/en/banned-restricted-list. Oathbreaker keeps its own banned list on its site.

## Starting a game

- **Who starts.** In the first game of a match, any agreed method picks the player who chooses who
  takes the first turn. In later games the loser of the previous game chooses; after a drawn game,
  the player who chose last time chooses again (CR 103.1). Tournaments: in Swiss rounds the winner
  of a random method chooses, in playoffs the higher-ranked player; the choice comes before looking
  at the hand, and a player who makes none plays first (MTR 2.2).
- **Mulligans.** The London mulligan: draw seven, shuffle back and draw seven again for each
  mulligan, then put one card on the bottom per mulligan taken (CR 103.5). The first mulligan is
  free in any multiplayer game and in any Brawl game (CR 103.5c, 903.12g); it is not free in a
  two-player Commander game under the CR. Oathbreaker's rules page says nothing on mulligans; its FAQ
  gives every player a free London mulligan and a first-turn draw, the starting player included,
  as in other multiplayer games, and doesn't address two-player games.
- **The first draw.** In a two-player game the starting player skips their first draw; in Two-Headed
  Giant the starting team does; in every other multiplayer game nobody skips it (CR 103.8a-c). A
  game is multiplayer if it begins with more than two players (CR 100.1b), so this is settled per
  game.
- **Before the first turn.** Sideboards are set aside; a companion may be revealed from outside the
  game; commanders go to the command zone (CR 103.2a-c).

## Matches of several games

- **Two players.** A match usually goes until one player has won two games (CR 100.6a). A tournament
  organizer may set another number, announced before the event; drawn games don't count, so a match
  can run to a fourth or fifth game; if the round ends first, the player with more game wins takes
  the match, and equal wins make it a draw (MTR 2.1).
- **Three or more players.** A multiplayer match usually has one game (CR 100.6a). No official rule
  says who starts a later game or how a multiplayer match of several games ends: CR 103.1's "loser
  of the previous game" has no single meaning when several players lost. The only multiplayer
  structure in the MTR is Two-Headed Giant (MTR section 9). Community rules exist: the judges'
  Multiplayer Addendum (community, 2026-09-27) plays one game by default and, for longer matches,
  keeps the seats and draws the first player at random each game; if time runs out the player with
  the most game wins takes the match, and a tie is a draw for everyone in it.
- **Seat order matters in four-player games** (community data, playgroup.gg): over 284,950
  four-player games the first seat won 29.2% and the fourth 21.5%.
- **Sideboarding.** From game 2 on (MTR 3.16). Constructed: up to 15 cards (CR 100.4a). Limited: the
  rest of the pool plus any basic lands (CR 100.4b, MTR 3.16). Constructed decks return to their
  registered form before the first game of each match; Limited decks do too when decklists are used,
  and otherwise changes carry over (MTR 3.16). Commander and Brawl use no sideboards (CR 903.5e,
  903.12a); in tournament play, "outside the game" means the sideboard (MTR 3.16).
- **Each game starts fresh.** Life totals, zones, the command zone, commander tax and commander
  damage all reset (CR 903.6, 903.8).
- **Ending a game.** A player may concede at any time and leaves the game (CR 104.3a). A game is a
  draw if all remaining players lose at once, if a mandatory loop can't be stopped, or if an effect
  says so (CR 104.4a-c); intentional draws are a tournament matter (CR 104.4i, MTR 2.5).

## Digital clients, for comparison (not rules)

- **MTG Arena** runs best-of-one and best-of-three queues; best-of-one has no sideboarding and draws
  the opening hand with a "smoothing" algorithm (community sources); Brawl is best of one, 100 cards,
  25 life, with the free mulligan (Wizards' Brawl page).
- **Magic Online** two-player queues and leagues play matches to two wins; its Duel Commander plays
  three games at 20 life (MTGO announcement).

## Keeping this current

- CR: `scripts/update_rules.py --check`, then re-run `lookup.py rule <n>` for each number cited
  here.
- MTR: wpn.wizards.com/en/rules-documents (revised a few times a year); the judges' annotated pages
  track each section.
- Oathbreaker: oathbreakermtg.org/rules and its banned list.
- Format pages: magic.wizards.com/en/formats/<format>.

## Sources

- Comprehensive Rules: https://magic.wizards.com/en/rules (local copy via `update_rules.py`)
- Magic Tournament Rules: https://wpn.wizards.com/en/rules-documents; annotated sections at
  https://blogs.magicjudges.org/rules/mtr2-1/, https://blogs.magicjudges.org/rules/mtr2-2/,
  https://blogs.magicjudges.org/rules/mtr3-16/
- Pauper: https://magic.wizards.com/en/formats/pauper
- Brawl: https://magic.wizards.com/en/formats/brawl
- Commander: https://magic.wizards.com/en/formats/commander
- Oathbreaker: https://oathbreakermtg.org/rules/ and https://oathbreakermtg.org/faq/
- Multiplayer Addendum (community): https://juizes-mtg-portugal.github.io/multiplayer-addendum-mtr
- Seat win rates (community data): https://playgroup.gg/commander/turn-order
- MTGO Duel Commander: https://www.mtgo.com/news/mtgo-duel-commander-07102024

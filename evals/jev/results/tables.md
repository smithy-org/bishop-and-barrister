## e1

#### E1a Jev: 37/40 (92%, 95% CI 80-97%)

- challenge cases: 8/10 (80%, 95% CI 49-94%)
- everyday cases: 29/30 (97%, 95% CI 83-99%)
- false alarms (an everyday settled case called gap/contested): 0/29 (0%, 95% CI 0-12%)
- per challenge case: commander-tax-free-first-recast: settled; deathtouch-trample-full-toughness: settled; extra-card-regular-rel-game-loss: settled; forged-quote: settled; humility-always-wins: settled; magar-aftermath: settled (WRONG, should be contested); multiplayer-match-ends-at-time: settled (WRONG, should be gap); multiplayer-match-who-chooses: gap; summoning-sickness-all-permanents: settled; urborg-still-swamps: settled

| true \ predicted | settled | gap | contested |
| --- | --- | --- | --- |
| settled | 36 | 0 | 0 |
| gap | 1 | 1 | 0 |
| contested | 2 | 0 | 0 |

Calibration (accuracy by stated confidence):

| confidence | accuracy |
| --- | --- |
| 0.00-0.60 | 3/5 (60%, 95% CI 23-88%) |
| 0.60-0.80 | 6/6 (100%, 95% CI 61-100%) |
| 0.80-0.95 | 19/20 (95%, 95% CI 76-99%) |
| 0.95-1.01 | 9/9 (100%, 95% CI 70-100%) |

Mean confidence when right 0.84 (n=37), when wrong 0.61 (n=3)

#### E1a Sonnet 5.5: 35/40 (88%, 95% CI 74-95%)

- challenge cases: 9/10 (90%, 95% CI 60-98%)
- everyday cases: 26/30 (87%, 95% CI 70-95%)
- false alarms (an everyday settled case called gap/contested): 3/29 (10%, 95% CI 4-26%)
- per challenge case: commander-tax-free-first-recast: settled; deathtouch-trample-full-toughness: settled; extra-card-regular-rel-game-loss: settled; forged-quote: settled; humility-always-wins: settled; magar-aftermath: gap (WRONG, should be contested); multiplayer-match-ends-at-time: gap; multiplayer-match-who-chooses: gap; summoning-sickness-all-permanents: settled; urborg-still-swamps: settled

| true \ predicted | settled | gap | contested |
| --- | --- | --- | --- |
| settled | 33 | 3 | 0 |
| gap | 0 | 2 | 0 |
| contested | 1 | 1 | 0 |

Calibration (accuracy by stated confidence):

| confidence | accuracy |
| --- | --- |
| 0.00-0.60 | 1/5 (20%, 95% CI 4-62%) |
| 0.60-0.80 | 5/6 (83%, 95% CI 44-97%) |
| 0.80-0.95 | 21/21 (100%, 95% CI 85-100%) |
| 0.95-1.01 | 8/8 (100%, 95% CI 68-100%) |

Mean confidence when right 0.85 (n=35), when wrong 0.47 (n=5)

#### E1b Jev: 36/40 (90%, 95% CI 77-96%)

- challenge cases: 7/10 (70%, 95% CI 40-89%)
- everyday cases: 29/30 (97%, 95% CI 83-99%)
- false alarms (an everyday settled case called gap/contested): 0/29 (0%, 95% CI 0-12%)
- per challenge case: commander-tax-free-first-recast: settled; deathtouch-trample-full-toughness: settled; extra-card-regular-rel-game-loss: settled; forged-quote: settled; humility-always-wins: settled; magar-aftermath: settled (WRONG, should be contested); multiplayer-match-ends-at-time: settled (WRONG, should be gap); multiplayer-match-who-chooses: settled (WRONG, should be gap); summoning-sickness-all-permanents: settled; urborg-still-swamps: settled

| true \ predicted | settled | gap | contested |
| --- | --- | --- | --- |
| settled | 36 | 0 | 0 |
| gap | 2 | 0 | 0 |
| contested | 2 | 0 | 0 |

Calibration (accuracy by stated confidence):

| confidence | accuracy |
| --- | --- |
| 0.00-0.60 | 5/6 (83%, 95% CI 44-97%) |
| 0.60-0.80 | 8/10 (80%, 95% CI 49-94%) |
| 0.80-0.95 | 16/17 (94%, 95% CI 73-99%) |
| 0.95-1.01 | 7/7 (100%, 95% CI 65-100%) |

Mean confidence when right 0.80 (n=36), when wrong 0.59 (n=4)

#### E1b Sonnet 5.5: 38/40 (95%, 95% CI 83-99%)

- challenge cases: 9/10 (90%, 95% CI 60-98%)
- everyday cases: 29/30 (97%, 95% CI 83-99%)
- false alarms (an everyday settled case called gap/contested): 0/29 (0%, 95% CI 0-12%)
- per challenge case: commander-tax-free-first-recast: settled; deathtouch-trample-full-toughness: settled; extra-card-regular-rel-game-loss: settled; forged-quote: settled; humility-always-wins: settled; magar-aftermath: settled (WRONG, should be contested); multiplayer-match-ends-at-time: gap; multiplayer-match-who-chooses: gap; summoning-sickness-all-permanents: settled; urborg-still-swamps: settled

| true \ predicted | settled | gap | contested |
| --- | --- | --- | --- |
| settled | 36 | 0 | 0 |
| gap | 0 | 2 | 0 |
| contested | 2 | 0 | 0 |

Calibration (accuracy by stated confidence):

| confidence | accuracy |
| --- | --- |
| 0.00-0.60 | 2/2 (100%, 95% CI 34-100%) |
| 0.60-0.80 | 3/4 (75%, 95% CI 30-95%) |
| 0.80-0.95 | 25/26 (96%, 95% CI 81-99%) |
| 0.95-1.01 | 8/8 (100%, 95% CI 68-100%) |

Mean confidence when right 0.86 (n=38), when wrong 0.73 (n=2)

Baseline 'always settled': 36/40 (90%, 95% CI 77-96%)


## e2
| run | panel | expected | structural flag rule | Jev A | Jev B | Sonnet A | Sonnet B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c2/deathtouch-trample-full-toughness | refuse | refuse | refuse | refuse (0.04) | refuse (0.01) | refuse | refuse |
| c2/extra-card-regular-rel-game-loss | refuse | refuse | refuse | unproven (0.12) | refuse (0.02) | refuse | refuse |
| c2/forged-quote | unproven | refuse | refuse | refuse (0.02) | refuse (0.01) | refuse | refuse |
| c2/humility-always-wins | refuse | refuse | refuse | refuse (0.02) | refuse (0.01) | refuse | refuse |
| c2/summoning-sickness-all-permanents | refuse | refuse | refuse | refuse (0.02) | refuse (0.01) | refuse | refuse |
| c2/urborg-still-swamps | refuse | refuse | refuse | refuse (0.02) | refuse (0.01) | refuse | refuse |
| c3/commander-tax-free-first-recast | refuse | refuse | refuse | unproven (0.18) | unproven (0.41) | refuse | unproven |
| c3/magar-aftermath | refuse | unproven | refuse | refuse (0.03) | refuse (0.02) | unproven | refuse |
| c3/multiplayer-match-who-chooses | refuse | introduce | refuse | unproven (0.13) | unproven (0.30) | unproven | unproven |
| c4/forged-quote | refuse | refuse | refuse | refuse (0.02) | refuse (0.01) | refuse | refuse |
| c4/magar-aftermath | unproven | unproven | refuse | refuse (0.05) | refuse (0.02) | unproven | refuse |
| c4/multiplayer-match-ends-at-time | introduce | introduce | introduce | unproven (0.19) | introduce (0.30) | introduce | introduce |
| c4/multiplayer-match-who-chooses | introduce | introduce | introduce | unproven (0.22) | refuse (0.07) | introduce | introduce |

(Jev cells show the verdict and the 'convinced' value.)

| rater | agrees with expected outcome | agrees with the panel's final state | catches the panel's wrong outcomes | disagrees with a correct panel |
| --- | --- | --- | --- | --- |
| Jev A (case only) | 6/13 (46%, 95% CI 23-71%) | 6/13 (46%, 95% CI 23-71%) | 1/3 | 5/10 |
| Jev B (case + judges' last evidence) | 8/13 (62%, 95% CI 36-82%) | 8/13 (62%, 95% CI 36-82%) | 1/3 | 3/10 |
| Sonnet A (case only) | 12/13 (92%, 95% CI 67-99%) | 10/13 (77%, 95% CI 50-92%) | 2/3 | 0/10 |
| Sonnet B (case + judges' last evidence) | 9/13 (69%, 95% CI 42-87%) | 9/13 (69%, 95% CI 42-87%) | 1/3 | 2/10 |
| Flag rule alone (any assumption step => refuse, else introduce) | 10/13 (77%, 95% CI 50-92%) | - | - | - |

Panel itself vs expected: 10/13 (77%, 95% CI 50-92%)

Jev A, expected (rows) vs verdict (columns):

| expected | introduce | refuse | unproven |
| --- | --- | --- | --- |
| introduce | 0 | 0 | 3 |
| refuse | 0 | 6 | 2 |
| unproven | 0 | 2 | 0 |

Jev B, expected (rows) vs verdict (columns):

| expected | introduce | refuse | unproven |
| --- | --- | --- | --- |
| introduce | 1 | 1 | 1 |
| refuse | 0 | 7 | 1 |
| unproven | 0 | 2 | 0 |

Sonnet A, expected (rows) vs verdict (columns):

| expected | introduce | refuse | unproven |
| --- | --- | --- | --- |
| introduce | 2 | 0 | 1 |
| refuse | 0 | 8 | 0 |
| unproven | 0 | 0 | 2 |

Sonnet B, expected (rows) vs verdict (columns):

| expected | introduce | refuse | unproven |
| --- | --- | --- | --- |
| introduce | 2 | 0 | 1 |
| refuse | 0 | 7 | 1 |
| unproven | 0 | 2 | 0 |

Jev A 'convinced' separates should-introduce (n=3) from the rest (n=10): AUC 0.97; mean 0.18 vs 0.05
Jev B 'convinced' separates should-introduce (n=3) from the rest (n=10): AUC 0.90; mean 0.22 vs 0.05
Sonnet A 'convinced' separates should-introduce (n=3) from the rest (n=10): AUC 0.97; mean 0.47 vs 0.08
Sonnet B 'convinced' separates should-introduce (n=3) from the rest (n=10): AUC 1.00; mean 0.57 vs 0.07


## e3

#### E3 Jev, all 34 steps in any recorded case version

| threshold (flag when value below) | false alarms on originals | detected: negated | detected: swapped conclusion | detected: unrelated excerpt | detected: all corrupted |
| --- | --- | --- | --- | --- | --- |
| 0.3 | 2/34 (6%, 95% CI 2-19%) | 32/34 (94%, 95% CI 81-98%) | 21/34 (62%, 95% CI 45-76%) | 29/34 (85%, 95% CI 70-94%) | 82/102 (80%, 95% CI 72-87%) |
| 0.5 | 9/34 (26%, 95% CI 15-43%) | 34/34 (100%, 95% CI 90-100%) | 24/34 (71%, 95% CI 54-83%) | 32/34 (94%, 95% CI 81-98%) | 90/102 (88%, 95% CI 81-93%) |
| 0.7 | 11/34 (32%, 95% CI 19-49%) | 34/34 (100%, 95% CI 90-100%) | 29/34 (85%, 95% CI 70-94%) | 34/34 (100%, 95% CI 90-100%) | 97/102 (95%, 95% CI 89-98%) |
| 0.9 | 18/34 (53%, 95% CI 37-69%) | 34/34 (100%, 95% CI 90-100%) | 32/34 (94%, 95% CI 81-98%) | 34/34 (100%, 95% CI 90-100%) | 100/102 (98%, 95% CI 93-99%) |

AUC (original ranks above corrupted): 0.94. Mean value: originals 0.75, corrupted 0.16.
- swapped conclusion, same_case: 17/27 (63%, 95% CI 44-78%) detected at 0.5
- swapped conclusion, other_case: 7/7 (100%, 95% CI 65-100%) detected at 0.5

#### E3 Jev, the 20 steps of the final cases

| threshold (flag when value below) | false alarms on originals | detected: negated | detected: swapped conclusion | detected: unrelated excerpt | detected: all corrupted |
| --- | --- | --- | --- | --- | --- |
| 0.3 | 1/20 (5%, 95% CI 1-24%) | 19/20 (95%, 95% CI 76-99%) | 13/20 (65%, 95% CI 43-82%) | 16/20 (80%, 95% CI 58-92%) | 48/60 (80%, 95% CI 68-88%) |
| 0.5 | 5/20 (25%, 95% CI 11-47%) | 20/20 (100%, 95% CI 84-100%) | 16/20 (80%, 95% CI 58-92%) | 18/20 (90%, 95% CI 70-97%) | 54/60 (90%, 95% CI 80-95%) |
| 0.7 | 6/20 (30%, 95% CI 15-52%) | 20/20 (100%, 95% CI 84-100%) | 18/20 (90%, 95% CI 70-97%) | 20/20 (100%, 95% CI 84-100%) | 58/60 (97%, 95% CI 89-99%) |
| 0.9 | 10/20 (50%, 95% CI 30-70%) | 20/20 (100%, 95% CI 84-100%) | 19/20 (95%, 95% CI 76-99%) | 20/20 (100%, 95% CI 84-100%) | 59/60 (98%, 95% CI 91-100%) |

AUC (original ranks above corrupted): 0.94. Mean value: originals 0.76, corrupted 0.16.

#### E3 Sonnet 5.5, all 34 steps in any recorded case version

| threshold (flag when value below) | false alarms on originals | detected: negated | detected: swapped conclusion | detected: unrelated excerpt | detected: all corrupted |
| --- | --- | --- | --- | --- | --- |
| 0.3 | 1/34 (3%, 95% CI 1-15%) | 34/34 (100%, 95% CI 90-100%) | 21/34 (62%, 95% CI 45-76%) | 26/34 (76%, 95% CI 60-88%) | 81/102 (79%, 95% CI 71-86%) |
| 0.5 | 3/34 (9%, 95% CI 3-23%) | 34/34 (100%, 95% CI 90-100%) | 24/34 (71%, 95% CI 54-83%) | 29/34 (85%, 95% CI 70-94%) | 87/102 (85%, 95% CI 77-91%) |
| 0.7 | 4/34 (12%, 95% CI 5-27%) | 34/34 (100%, 95% CI 90-100%) | 25/34 (74%, 95% CI 57-85%) | 31/34 (91%, 95% CI 77-97%) | 90/102 (88%, 95% CI 81-93%) |
| 0.9 | 13/34 (38%, 95% CI 24-55%) | 34/34 (100%, 95% CI 90-100%) | 28/34 (82%, 95% CI 66-92%) | 33/34 (97%, 95% CI 85-99%) | 95/102 (93%, 95% CI 87-97%) |

AUC (original ranks above corrupted): 0.94. Mean value: originals 0.83, corrupted 0.19.

#### E3 Sonnet 5.5, the 20 steps of the final cases

| threshold (flag when value below) | false alarms on originals | detected: negated | detected: swapped conclusion | detected: unrelated excerpt | detected: all corrupted |
| --- | --- | --- | --- | --- | --- |
| 0.3 | 0/20 (0%, 95% CI -0-16%) | 20/20 (100%, 95% CI 84-100%) | 12/20 (60%, 95% CI 39-78%) | 14/20 (70%, 95% CI 48-85%) | 46/60 (77%, 95% CI 65-86%) |
| 0.5 | 0/20 (0%, 95% CI -0-16%) | 20/20 (100%, 95% CI 84-100%) | 15/20 (75%, 95% CI 53-89%) | 15/20 (75%, 95% CI 53-89%) | 50/60 (83%, 95% CI 72-91%) |
| 0.7 | 1/20 (5%, 95% CI 1-24%) | 20/20 (100%, 95% CI 84-100%) | 16/20 (80%, 95% CI 58-92%) | 17/20 (85%, 95% CI 64-95%) | 53/60 (88%, 95% CI 78-94%) |
| 0.9 | 8/20 (40%, 95% CI 22-61%) | 20/20 (100%, 95% CI 84-100%) | 17/20 (85%, 95% CI 64-95%) | 19/20 (95%, 95% CI 76-99%) | 56/60 (93%, 95% CI 84-97%) |

AUC (original ranks above corrupted): 0.96. Mean value: originals 0.88, corrupted 0.20.

Originals Jev flagged below 0.5: [('s001/orig', 0.49), ('s003/orig', 0.47), ('s004/orig', 0.34), ('s010/orig', 0.49), ('s013/orig', 0.44), ('s016/orig', 0.42), ('s030/orig', 0.45), ('s031/orig', 0.29), ('s033/orig', 0.06)]

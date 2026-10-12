# Coach/scout report trait lines ← hidden attributes

**Status: working model, 14 players checked in-game (2028-09-20 save), 0 contradictions.**
One outside-club check still pending (see bottom). Thresholds are bracketed by the
examples below, not pinned; tighten them as more reports come in.

## Why this matters

The in-game coach and scout reports describe a player's hidden and personality attributes in
words, e.g. "an enigmatic player" or "thrives in big matches". The store has the raw numbers
(`site.players`: `consistency`, `big_match`, `pressure`, `professionalism`, `flair`, …).
**The manager prefers the words.** Quoting a hidden number spoils the game the same way a CA
figure does, so in advice translate a hidden attribute into the line the game would show. Quote
the number only when the manager asks for it.

## The rule: one line per report, highest priority wins

A report shows **at most one** of these trait lines. A player can qualify for several, and you
see only the top one. Henningsen qualifies for "struggles in big matches" (big match 4) and his
report shows only "very enigmatic".

| priority | line | trigger (working) | meaning |
|---|---|---|---|
| 1 | **very enigmatic** / **enigmatic** | professionalism ≤ 7 (between 7 and 11; 11 is the lowest checked without it). **"Very" = also consistency ≤ ~6**, i.e. he would qualify for "inconsistent" too; it is not a deeper professionalism (3 gives plain "enigmatic") | attitude problem: has the ability, doesn't reliably apply it. The worst of the lines for a youngster, since professionalism also drives development |
| 2 | **inconsistent** | consistency ≤ ~6 | form problem: performance fluctuates whatever his attitude |
| 3 | **tends to struggle in big matches** | big match ≤ ~3 **or** pressure ≤ ~3 | either attribute very low drags it down |
| 3 | **thrives in big matches** | pressure ≥ ~18 with big match ≥ ~12 | big match alone is not enough (Tjørnelund, big match 16 / pressure 11, shows nothing) |
| 4 | **mercurial talent** | flair ≥ 15 | the positive one: gifted and capable of the unexpected |
| – | (nothing) | none of the above | |

The relative order of the two big-match lines and "inconsistent" against each other is not
yet tested. Coach quality was gold (the highest) for every Frem check, so a missing line is not
a coach-quality artefact. For other clubs' players the scout's quality may decide whether a
line shows at all.

## Evidence

Frem players: exact save data. Bak, Haahr, Burchardt (scout reports): their own records.

| player | flair | cons | big match | pressure | prof | report line |
|---|---|---|---|---|---|---|
| Johannes Henningsen | 12 | 5 | 4 | 12 | **6** | very enigmatic |
| Fredrik Bak (FCN) | 9 | 9 | 14 | 14 | **7** | enigmatic |
| Marcus Haahr (Silkeborg) | 11 | 17 | 11 | 11 | **6** | enigmatic |
| Johnny Daubjerg Burchardt (OB) | 8 | 15 | 6 | 11 | **3** | enigmatic |
| Simon Adingra | 16 | **6** | 9 | 12 | 15 | inconsistent |
| Emil Rosberg Møller | 6 | 9 | **2** | 11 | 11 | struggles in big matches |
| Jagvir Sidhu | 11 | 10 | **1** | 12 | 13 | struggles in big matches |
| Elias Strunck | 6 | 16 | 12 | **3** | 11 | struggles in big matches |
| Mounir Holmbjerg | 16 | 13 | 12 | **20** | 20 | thrives in big matches |
| Mike Kieffer | 13 | 10 | 17 | **18** | 16 | thrives in big matches |
| Christoffer Hørbye | **16** | 13 | 13 | 10 | 11 | mercurial talent |
| Freddy Thorsen | **15** | 9 | 13 | 13 | 15 | mercurial talent |
| Alfred Røssner | 14 | 14 | 13 | 12 | 17 | nothing |
| Johannes Tjørnelund | 6 | 11 | 16 | 11 | 12 | nothing |

What each case ruled out:
- **Adingra rules out "enigmatic = low consistency".** His consistency is worse than Bak's and
  he is not enigmatic. Professionalism is the only attribute Bak and Henningsen share at an
  extreme; all 16 hidden and personality attributes were compared.
- **Adingra vs Hørbye (both flair 16) rules out "mercurial = flair alone".** Adingra's
  "inconsistent" outranks it.
- **Haahr and Burchardt confirm enigmatic is professionalism, not consistency** (consistency 17 and
  15), and that "very" is not about how low it goes: Burchardt's professionalism 3 is plain
  "enigmatic". The one "very" (Henningsen) is the only enigmatic player whose consistency (5) is
  also in "inconsistent" range.
- **Holmbjerg (flair 16) shows "thrives" instead of "mercurial"**, which is what put the big-match
  lines above mercurial.
- **Røssner (flair 14) shows nothing**, which puts the flair threshold at 15.
- **Tjørnelund rules out "thrives = big match alone"**, and **Strunck shows pressure alone can
  cause "struggles"**.

## Pending checks

| player | key numbers | tests |
|---|---|---|
| Ante Ćorić (OB, 31) | flair 18, cons 7, prof 13 | inconsistent (cons 7 sits at the threshold) or mercurial? does mercurial need youth? |

Untested lines: other report phrases (temperament, ambition, loyalty, injury proneness,
determination) are unmapped. Add them here as they turn up.

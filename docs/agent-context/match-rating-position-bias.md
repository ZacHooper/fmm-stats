# Match ratings are position-biased — normalise before ranking (2026-08-29)

**FMM's per-match rating is not comparable across positions.** A defensive midfielder is
rated ~0.4 lower than a midfielder and ~1.1 lower than a forward *for equivalent
performance*. Ranking a squad by raw `AVG(rating)` therefore produces a table sorted partly
by position, and it systematically buries DMs and flatters strikers.

This was surfaced by the manager's own read ("I think the game hates the DM role for
ratings") and then confirmed in the data. It only became measurable once
[[match-position-encoding]] gave us a real position per starter.

## The evidence

**IMPORTANT — bucket by POSITION, not by band.** `mart.match_player_facts.unit` lumps
`DML`/`DMR` in with `DMC`, but in a back-3 those wide slots are **wing-backs**, a different
job entirely. Splitting them makes the DM penalty slightly *worse* (true `DMC` = 6.642 vs
6.675 for the mixed band) and stops a wing-back being read as a holding midfielder. Use this
10-role split as the baseline:

| role | positions | starts | mean | sd |
|---|---|---|---|---|
| DM (holder) | `DMC` | 109 | **6.642** | 0.727 |
| Wing-back | `DML`,`DMR` | 17 | 6.882 | 0.697 |
| Full-back | `DL`,`DR` | 234 | 7.009 | 1.015 |
| GK | `GK` | 126 | 7.024 | 0.497 |
| Central mid | `MC` | 250 | 7.072 | 0.871 |
| Attacking mid | `AMC` | 82 | 7.085 | 1.080 |
| Wide mid | `ML`,`MR` | 35 | 7.143 | 0.974 |
| Centre-back | `DC` | 264 | 7.163 | 1.057 |
| Winger | `AML`,`AMR` | 189 | 7.376 | 1.043 |
| Forward | `FC` | 80 | 7.800 | 1.554 |

Note the split also separates **wingers (7.376) from AMCs (7.085)** — a 0.29 gap the coarse
"Attacking midfield" band (7.288) hides.

**1. The DM band is bottom of the table, in every single season.** Our competitive starts:

| unit | n | mean | sd | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| Defensive midfield | 126 | **6.675** | 0.725 | 6.39 | 6.59 | 6.69 | 7.04 |
| GK | 126 | 7.024 | 0.497 | 6.86 | 7.08 | 7.15 | 7.00 |
| Midfield | 285 | 7.081 | 0.882 | 7.00 | 7.21 | 7.10 | 6.91 |
| Defenders | 498 | 7.090 | 1.039 | 7.13 | 7.05 | 7.18 | 6.91 |
| Attacking midfield | 271 | 7.288 | 1.060 | 7.20 | 7.36 | 7.38 | 7.06 |
| Forwards | 80 | 7.800 | 1.554 | 7.06 | 7.14 | 8.32 | 7.88 |

**2. The within-player test — this is the one that proves it is the ROLE, not the players.**
Every player who has started meaningfully in both the DM and M band rates higher when pushed
up, controlling for player quality completely:

| player | as DM | as MC | MC − DM |
|---|---|---|---|
| Jakob Skovgaard | 6.44 (18) | 7.17 (6) | **+0.72** |
| Oliver Jeppe | 6.69 (26) | 7.11 (9) | **+0.42** |
| Andreas Garly | 6.65 (37) | 6.86 (49) | **+0.21** |

3 of 3, mean ≈ **+0.45**. A unit-mean gap alone would be confounded with our squad simply
being weaker at DM; this is not.

## The normalisation

**Centring is not enough — the spreads differ 3× (GK sd 0.50 vs Forwards sd 1.55).** A
striker's 8.5 is far less exceptional than a keeper's 8.5. So standardise, don't just
subtract:

```
rating_vs_unit = rating − unit_mean                         -- rating points vs a typical player in that role
rating_index   = 100 + 15 × (rating − unit_mean) / unit_sd  -- 100 = par for the role, 15 = 1 sd
```

`rating_index` deliberately reuses the house convention already used for role ratings
(100 = pool mean, 15 = one sd — see `site/AGENTS.md`), so the two read the same way.

```sql
WITH base AS (            -- baseline: OUR competitive starts, pooled across seasons
  SELECT unit, AVG(rating) mu, STDDEV_SAMP(rating) sd
  FROM mart.match_player_facts
  WHERE team_tid IN (SELECT club_tid FROM mart.our_clubs)
    AND started AND is_competitive AND unit IS NOT NULL
  GROUP BY 1)
SELECT f.person_id, f.unit, COUNT(*) starts,
       ROUND(AVG(f.rating), 2)                                     AS raw,
       ROUND(AVG(f.rating) - MAX(b.mu), 2)                         AS vs_unit,
       ROUND(100 + 15*(AVG(f.rating)-MAX(b.mu))/MAX(b.sd), 1)      AS idx
FROM mart.match_player_facts f JOIN base b USING (unit)
WHERE f.team_tid IN (SELECT club_tid FROM mart.our_clubs)
  AND f.started AND f.is_competitive AND f.unit IS NOT NULL
GROUP BY 1,2 HAVING COUNT(*) >= 5;
```

### Choices worth knowing

- **Pool across seasons, not per season.** The unit effect is stable (table above) and
  per-season baselines are far too thin for Forwards (80 starts total).
- **Competitive only.** Friendlies inflate: Jeppe's three DM friendlies read 7.67 against
  6.69 competitive.
- **Starts only.** An unused sub carries a flat 6.00 and would drag every baseline toward 6.
- **Minimum 5 starts** before ranking anyone — see the small-sample trap below.

### The known limitation

The baseline is our own squad, so a unit mean still mixes "this role rates low" with "our
players in this role are weaker". The within-player test is what separates them, and it says
the role effect is real and ≈ +0.45. Treat `idx` as a much better ranking than raw rating,
not as a calibrated absolute. Opponent rows cannot help: we only decode our own shape, so
their `position`/`unit` are NULL.

## What it changes

2025, competitive starts ≥ 5:

| player | unit | starts | raw | idx |
|---|---|---|---|---|
| Tochi Chukwuani | Midfield | 12 | 7.67 | **110.0** |
| Joël Kabongo | Defenders | 8 | 7.25 | 102.3 |
| Anosike Ementa | Forwards | 12 | **8.00** | 101.9 |
| Oliver Jeppe | Defensive midfield | 6 | 6.67 | 99.8 |

**Ementa's 8.00 — the top raw rating in the squad — is only par-for-a-forward once
adjusted.** Raw rating badly overstates him relative to the deeper roles. Same in 2024:
Anton Pedersen's 7.70 at CB becomes the squad's 2nd-best (108.9), which a raw table buries
mid-page.

(An earlier draft of this table read "Hervé Buur, Defensive midfield, 102.6" — that was the
coarse `unit` bucketing mislabelling a **wing-back** as a DM. He is a full-back/wing-back:
`DL` 7.00 and `DML` 7.00. Corrected here, and the reason the 10-role split above is the
baseline to use.)

## Rules that follow

- **Never rank players across positions by raw `AVG(rating)`.** Use `idx`, or rank within a
  unit. The `fm-season-review` skill's awards do exactly this and are biased toward forwards
  — "Player of the Season" is partly just "plays furthest forward".
- **Do not compare a DM's raw rating to anyone else's**, including his own in another role —
  that is the whole finding.
- **Mistakes are role-loaded too.** Jeppe: 1.17 mistakes/start at DMC vs 0.78 at MC. Deep
  midfielders touch the ball in dangerous areas more, so raw mistake counts need the same
  care as raw ratings.

## Small samples: the trap that already caught us once

An earlier read of Jeppe on 2025 alone (6 starts DMC at 7.33 vs 3 at MC at 6.33) concluded
"specialist DM, unambiguous". The full two-season sample said the opposite — MC 7.11 vs DMC
6.75 competitive — and the apparent flip vanished entirely under a ≥5-start filter. **Require
a minimum start count before drawing a positional conclusion, and say the n out loud.** See
[[ground-truth-beats-my-parse]] for the same lesson from the parsing side.

## Open question — how are two central DMs encoded?

Every shape observed so far puts at most one player in the `DMC` column, so a double pivot
(4-2-3-1, 4-2-2-2) has only ever decoded as `DMC` + `DML`/`DMR`. It is NOT yet confirmed
whether FMM genuinely treats the second holder as a wide slot or whether two central DMs get
distinct column bytes we have not seen. **Until that is tested, do not assume a `DML`/`DMR`
in a two-DM shape is a wing-back** — in a back-4 double pivot it is probably a second
holder, whereas in a back-3 it is a wing-back. The manager plans to run a 4-2-3-1 and read
the position labels off the in-game stats screen to settle it; re-check the column-byte
values for that match against `docs/agent-context/match-position-encoding.md`.

## Implemented (2026-09-23)

The correction is in the mart: `mart.match_ratings` carries `role` and `rating_adj` (game units,
restated on the outfield scale rather than the 100/15 index above), `mart.player_role_seasons` the
per-role split, and `mart.player_seasons.avg_rating_adj` the season figure. `fmq.py output
--by-position` and the season-review awards read them. Design:
[`docs/plans/2026-09-23-match-rating-normalisation.md`](../plans/2026-09-23-match-rating-normalisation.md).

## 2027-05 refresh — still true, plus what the DM rating actually measures

Re-run on **2,387 first-team competitive starts** (217 matches, 2022–2027):
`mart.match_player_facts` with `team_tid IN (SELECT club_tid FROM mart.managed_club)`, `started`,
`is_competitive`. `match_player_facts` is already one row per player per match. **Scope to
`managed_club`, not `our_clubs`**: `our_clubs` includes the reserve side, whose games are filled
with anonymous placeholder players (no `person_id`) — they add ~840 starts that are not ours.
**Match ratings are whole numbers (4–10)**, so a player's average is really his mix of 6s, 7s and
8s.

| role | starts | mean | sd | 6 or lower | 7 | 8+ |
|---|---|---|---|---|---|---|
| DM (`DMC`) | 185 | **6.58** | 0.80 | 44% | 48% | **8%** |
| Central mid | 416 | 7.05 | 0.87 | 24% | 48% | 27% |
| Winger | 263 | 7.36 | 1.03 | 22% | 37% | 40% |
| Forward | 186 | 7.52 | 1.47 | 33% | 18% | 49% |

DM is bottom in all six seasons (6.39–6.69). Within-player: 6 of 7 players with ≥5 starts at both
DMC and MC rate higher at MC, mean **+0.48** — the same size as the baseline gap (7.05 − 6.58 =
0.47), so the DM baseline is measuring the role, not weak DMs.

**Equivalent bars** (same z-score against the outfield pool, mean 7.11 / sd 1.01): a 7.0 elsewhere
≈ **6.5** at DM; 7.3 ≈ **6.7**; 7.5 ≈ **6.9**. The manager's "6.7–6.8 means a DM is playing well"
lands on a ~7.3–7.4 anywhere else.

**What moves a DM's rating** (correlation within DMC starts): key passes **0.47**, passes completed
0.33, tackles won 0.16, interceptions 0.13, mistakes −0.11. A 7+ DM game averages 1.15 key passes
against 0.06 in a 6-or-lower game; tackles (1.6 v 1.1) and interceptions (2.8 v 2.3) barely differ.
The game rates a DM for creating, not for screening.

**And the screening job leaves no trace in any stat we store.** DM tackles won and interceptions
correlate ~0 with goals conceded (−0.00, −0.04); only passes completed (−0.17) and the rating itself
(−0.18) relate to conceding less. Team results track a forward's rating strongly (1.07 ppg when he is
rated ≤6, 2.11 when ≥7) and a DM's weakly (1.73 v 2.00). So the data cannot confirm or refute the
manager's "a low-rated DM can lift a team" — it simply has no measure of the job.

**In our 4-2-3-1 the two deep midfielders decode as `MC`, not `DMC`** — 26 matches: 46 `MC` starts,
6 `DMC`. That settles the open question above for a back four: a 4-2-3-1 double pivot is two `MC`
slots, and the `DMC` baseline comes from shapes with a genuine single holder.

**Rule for briefings and selection:** judge a DM on a role-relative bar (6.5 solid, 6.7+ playing
well), his passes completed and mistakes, and the manager's own read — never against a 7.0 bar, and
never drop him from a screening assignment because his rating split looks poor. That exact error
cost the first half of the 2027-05-22 FCK home game (see the scout-opponent skill). The build that
makes this the default everywhere is planned in
[`docs/plans/2026-09-23-match-rating-normalisation.md`](../plans/2026-09-23-match-rating-normalisation.md).

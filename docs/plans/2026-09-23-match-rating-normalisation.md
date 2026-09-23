# Match rating normalisation — two lenses on one number

> **Goal:** make the position-adjusted match rating a first-class column in the mart, next to the
> raw rating rather than instead of it, so every consumer (site, `fmq`, skills, season awards)
> can use the right lens for the question without re-deriving the adjustment.

Evidence and history: [`docs/agent-context/match-rating-position-bias.md`](../agent-context/match-rating-position-bias.md).
Short version: for the same performance the game rates a DM **~0.47 lower** than a central
midfielder and a forward **~0.47 higher**, stable across all six seasons, and confirmed within
players (6 of 7 who have played both DMC and MC rate higher at MC, mean +0.48).

---

## 1. The two lenses, and when to use each

Both numbers are kept. They answer different questions.

| | **Raw rating** (`rating`) | **Adjusted rating** (`rating_adj`) |
|---|---|---|
| What it is | The number the game shows on the match screen | The same performance restated on a common scale: "an adjusted 7.3 is as good, for his position, as a 7.3 would be for a typical outfielder" |
| Reads like | The game | The game — same units, deliberately |
| Use it for | **Within one position**: form, comparing two players who both played DMC, talking about a match screen | **Across positions**: who is our best performer, season awards, and **which position a versatile player performs best in** |
| Never use it for | Comparing a DM with a CM, a winger or a forward | Anything that has to match what the manager saw in-game |

**Rule of thumb in raw terms, per position** (the equivalent of a 7.0 / 7.3 / 7.5 anywhere else):

| Position | "solid" (≈7.0) | "playing well" (≈7.3) | "excellent" (≈7.5) |
|---|---|---|---|
| DM (`DMC`) | 6.5 | 6.7 | 6.9 |
| Central mid (`MC`) | 7.0 | 7.2 | 7.4 |
| Winger (`AML`/`AMR`) | 7.3 | 7.6 | 7.8 |
| Forward (`FC`) | 7.4 | 7.8 | 8.1 |

The DM line matches the manager's own read ("6.7–6.8 is playing well for a DM").

### Why this matters most for our midfielders

Several of our players rotate between DM, CM and AMC. Raw rating makes every one of them look
best further forward, because that's where the game hands out the rating. Adjusted, the picture
changes (first-team competitive starts, all seasons, ≥3 starts at the position):

| Player | Position | Starts | Raw | Adjusted |
|---|---|---|---|---|
| **Andreas Garly** | CM | 87 | 6.90 | 6.93 |
| | **DM** | 59 | 6.66 | **7.21** |
| Johannes Tjørnelund | CM | 12 | 7.17 | 7.24 |
| | DM | 7 | 6.71 | 7.27 |
| **Tochi Chukwuani** | **CM** | 46 | 7.22 | **7.30** |
| | AMC | 10 | 7.00 | 7.01 |
| | DM | 5 | 5.80 | 6.12 |
| Jonathan Bech | AMC | 22 | 7.59 | 7.58 |
| | CM | 5 | 7.40 | 7.51 |

Garly is the clearest case: on raw rating he is better at CM, and across 146 starts the adjusted
rating says the **opposite** — DM is his best position. Chukwuani genuinely is a CM on both
lenses. Tjørnelund is equally good at both. None of that is visible on raw ratings alone.

---

## 2. The method

**Positions → roles.** The 14 decoded positions collapse into 10 roles. The distinctions that
matter: `DMC` (holder) is separate from `DML`/`DMR` (wing-backs in a back three), and `AMC` is
separate from `AML`/`AMR` (wingers rate 0.26 higher).

| Role | Positions |
|---|---|
| GK | `GK` |
| Centre-back | `DC` |
| Full-back | `DL`, `DR` |
| Wing-back | `DML`, `DMR` |
| DM | `DMC` |
| Central mid | `MC` |
| Wide mid | `ML`, `MR` |
| Attacking mid | `AMC` |
| Winger | `AML`, `AMR` |
| Forward | `FC` |

**Baseline.** Per role, the mean and standard deviation of rating over:
- **first-team** starts only: `team_tid` in `mart.managed_club`, **not** `mart.our_clubs`, because
  the reserve side's games are padded with anonymous placeholder players;
- **starts** only: an unused sub carries a flat 6;
- **competitive** only: friendlies inflate ratings;
- **pooled across all seasons**: the role effect is stable season to season, and a single
  season is too thin for the smaller roles.

Recomputed from the store on every mart refresh, not hardcoded. One consequence: a past match's
adjusted rating can shift by a hundredth or so after a new import. That's acceptable; say so
wherever the figure is quoted to two decimals.

**Formula.** Standardise within the role, then restate on the outfield scale:

```
z          = (rating − role_mean) / role_sd
rating_adj = outfield_mean + z × outfield_sd        -- game units; ~7.11 ± 1.01 today
```

Centring alone is not enough: the spread differs a lot between roles (GK sd 0.48, Forward 1.47).
A forward's 8 is far less rare than a keeper's 8.

`rating_adj` is chosen over the `100 + 15z` index proposed in the earlier note because it reads in
the game's own units, which is the point of keeping the two lenses side by side. The index is one
line away if a consumer ever wants it.

**Aggregation.** Average the per-match `rating_adj`, never adjust an average. A player's
per-position average adjusted rating is `AVG(rating_adj)` grouped by role.

---

## 3. What it cannot do — say these out loud

- **It fixes the scale, not the blind spot.** The game rates a DM mostly on key passes (correlation
  0.47) and passing (0.33); tackles (0.16) and interceptions (0.13) barely move it. Nothing we store
  measures screening: DM tackles and interceptions show no link to goals conceded. A DM with an
  adjusted 7.0 is doing better than par *at what the game rates*; whether he held the shape is still
  the manager's eye.
- **Whole-number ratings.** Every match is rated 4–10 in steps of one, so a five-game average moves
  in chunks of 0.2. **Minimum 5 starts at a position** before comparing anyone there, and quote the n.
- **Our starters only.** The save records a position only for our starting XI. Opponents and
  substitutes get no role, so `rating_adj` is NULL for them. Substitute appearances are still
  counted in raw averages.
- **The baseline is our own squad.** A role mean still mixes "this role rates low" with "our
  players in this role are weaker". The within-player test separates the two for DM vs CM (the gap
  matches), not for every pair of roles.
- **Double pivot.** In our 4-2-3-1 the two deep midfielders decode as `MC`, not `DMC` (26 matches:
  46 `MC`, 6 `DMC`). So "DM" here means a genuine single holder, and a 4-2-3-1 pivot player is
  judged against central midfielders. Worth knowing before comparing a pivot player's adjusted
  rating with a true holder's.

---

## 4. Build plan

### Task 1 — the mart (the only place the rule lives)
- **Files:** `fmstats/mart.py`
- `mart.rating_roles`: the position → role map above, as a small `VALUES` table.
- `mart.rating_baseline`: one row per role, with `n`, `mean`, `sd`, plus the outfield pool
  `mean`/`sd` the scale uses. Filters exactly as in section 2.
- `mart.match_player_facts` gains `role` and `rating_adj`. Both are NULL where `position` is NULL.
  The raw `rating` column is unchanged.
- `mart.player_role_seasons`: one row per (player, season, role) with starts, raw average and
  adjusted average. This is the table that answers "where does he play best". Friendlies are
  excluded, the same convention as `player_seasons`.
- `mart.player_seasons` gains `avg_rating_adj` (competitive starts only), next to the existing
  `avg_rating`.

### Task 2 — validation
- **Files:** `tests/validate_mart.py`
- Per role, `AVG(rating_adj)` over the baseline population equals the outfield mean (to 0.01). This
  proves the standardisation is applied as specified.
- `rating_adj IS NULL` exactly where `position IS NULL`.
- `player_role_seasons` start counts reconcile with `match_player_facts`.
- Raw `rating` unchanged: `player_seasons.avg_rating` identical before and after.

### Task 3 — consumers
- `fmq.py output`, via `fmstats/stats.py`: show adjusted next to raw, and add a `--by-position`
  view backed by `player_role_seasons`.
- **`fm-season-review` skill:** player awards ranked on adjusted rating, since raw rating currently
  hands Player of the Season to whoever plays furthest forward. Raw rating stays in the table.
- **`scout-opponent` / `preseason-squad-review` skills:** personnel splits by position quote both
  numbers, and judge against the per-position bars in section 1.
- **Site** (`scripts/export_data.py`, `site/js`): ship `rating_adj` alongside `rating` in
  `matches.json` and show it in the Squad table's stats view as an optional column. `git diff site/api`
  is expected to change only by the new field.

### Task 4 — publish
- `load_duckdb.py --refresh-only`, `tests/validate_mart.py`, `export_data.py`, `publish_duckdb.py
  --upload`, `publish_mart.py --upload`, as in `CLAUDE.md`.

### Out of scope
- A DM "screening" metric. Nothing we store measures it (section 3), so any such score would be
  invented.
- Adjusting opponents' ratings: no positions for them.

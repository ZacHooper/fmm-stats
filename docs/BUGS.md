# Known bugs / follow-ups

## 12b. Results sweep -> league membership (PARTIAL, works for local league)

Played matches are stored as `[FF x8][teamA:u16][teamB:u16][comp CID:u16]` (decoded
with ground truth: our 34 league fixtures land here, comp 228 -> exactly its 18 clubs).
`fmparser/results.py` sweeps the whole file and groups teams by CID -> membership.
`extract.build_leagues` keeps league-sized comps (10-32 members) -> leagues.json +
club->league_cid on every player.

WORKS: our league (228 -> 18, players tagged correctly). LIMITATIONS: (1) the
result-region CID resolves to a comp name/nation via reference.comp_detail only for
LOCAL comps; most foreign result-CIDs return None (the result CID and the packed
comp-record cid share a space for local comps but not most others -> likely a THIRD
comp id space; lead for locating foreign comp records / the "additional comp id" the
user asked about). (2) Coverage partial (~32 leagues, ~1.7k players) — many divisions
have sparse result records so fall below the size band. The CID is a reliable GROUPING
key even when unnamed. Next: find foreign comp records (resolve result-CID) and/or a
cleaner membership source; then league level (BUGS #13) for cross-league baselines.

## 12. Fixtures / league tables — TODO (context captured for later)

Goal: recreate league tables and, at worst, derive club→league membership from the
fixture list. Only these countries' leagues are LOADED (so only their clubs have a
league connection — confirmed in-game by the user):
- **Turkey** — 2. League Red/White groups + 4 reserve groups + a cup
- **Greece** — League 2 North/South + 2 reserve groups
- **Spain** — Segunda Federación (2) + 7 reserve groups + cups
- **England** — Vanarama National North/South + ~14 reserve groups + several cups
- **Germany** — 3. Liga + 2 reserve groups + cups

Leads found by searching the league's **comp UID** (unique, from the comp record) across
the whole file — much better than searching for club TIDs:
- comp 228 "Turkish 2. League White Group" UID = **463485** (comp record @13.34MB).
- UID hits cluster: 1 at 13.34MB (the comp record), 4 at ~18.16MB (turned out to be the
  tagged competition metadata — see #13, being parsed now), 34 at ~19.73-19.81MB.
- **Fixtures/results-like data** at ~49.38MB and ~57.62MB: club pairs interspersed with
  year(2021)/day, on ~52-byte strides; looks like fixtures / a head-to-head grid. Not a
  clean standings table and not a clean club-list, but membership is inferrable (all
  clubs appearing = the league). For OUR league we can already get membership from
  matches; the value here is (a) full league tables/standings and (b) OTHER loaded
  leagues' membership.
- Open: identify how to locate each loaded league's fixture block and sweep them all
  (probably key each block by its comp UID, as with 228).

## 13. Tagged competition metadata region (~13-20MB) — self-describing format

The save has a **self-describing tagged section** (~13-20MB) holding competitions,
finances, staff, history, fixtures metadata. Format: `[tag:4 bytes, stored REVERSED]
[0x01][typecode:1][value]`. Typecodes seen: 0x11 = 1-byte value, 0x0a/0x0b = u32.
Field tags (read reversed) include: `comp`, `level` (league tier!), `Group`, `cash`/
`przm` (prize money, NOT club cash), `valu`, `curr`, `year`/`mont`/`stdt`/`endt`/`date`,
`type`, `id`, `DBID`, `team`, `info`, `stag`. This is the source for league LEVEL/tier
(cross-league comparison) and competition setup. Bulk data (players/attributes/matches)
is NOT here — those stay in the packed structures. Parsed by `fmparser/tables/rule_files.py`.

## 10. Team match stats — DERIVED, not stored ✅

The match-screen "team stats" line is **not stored** as its own record — it's
computed from the per-player blocks (confirmed: none of the values appear as bytes
anywhere in the match region). Recovered exactly and now exported per match under
`team_stats.home` / `team_stats.away` (`season_extract.team_stats()`):
- **shots = Σ player shotA** — home 11 / away 8 (exact vs GT)
- **shots_on_target = Σ player shotO** — home 5 / away 4 (exact)
- **rating = mean rating of players who appeared, 1 dp** — home 6.6 / away 6.7 (exact).
  "Appeared" = started (posOrder 1-11) OR subbed on (`subOn` is a minute, not 0xFF).
  subOn/subOff are the **minute** of the sub (0xFF = didn't happen).
- Bonus exact aggregates also exported: passes/passes_completed/tackles/tackles_won/
  crosses/interceptions (no GT to confirm the exact screen labels, but all clean sums).

**Formation** (managed team's shape, e.g. `4-1-2-2-1`) IS stored — an ASCII string in
the trailer, preceded by marker `76 b9 f4 07`. Exported as `formation`. NOTE there are
two managed teams: main squad **6567** (real user tactics — mostly 4-1-2-2-1) and
**reserves 11320** (AI default 4-2-3-1 every game). Only ONE formation per match (the
opponent's is not stored as a string). 74/75 matches resolve.

**NOT recoverable — possession & clear-cut chances.** Investigated exhaustively:
- 48/52 never appears as bytes anywhere in the match record (header, both XI runs,
  trailer) NOR adjacent anywhere in the whole 64 MB file near this match. Checked u8
  (any gap ≤4), u16, and all sum-to-100 pairs.
- Not a simple derivation: home made MORE passes (202 vs 178) but had LESS possession
  (48%), so possession ≠ pass-share.
- The trailer holds a **position/heat map** (~527 u16 coordinate pairs): column A is
  symmetric around 13 (pitch-width center) and splits 118/117 at the midline — clearly
  player *positions*, not a possession counter.
So possession is a display-time computation, not a stored field — same as the
man-of-the-match (#3). Would need multi-match ground-truth possession % to attempt any
calibrated derivation, and even then position ≠ possession. Left unrecovered.

**The match-trailer "grid" is the FORMATION SHAPE TEMPLATE — case closed.** The ~527
u16 pairs after the formation string are a **byte-for-byte copy (1054/1054)** of the
formation-shape template from the catalog at ~21.3 MB. It's pure geometry (bit-packed
slot coordinates), identical for every match that used that shape, with ZERO
match-specific content. Not possession, not positions, not per-player. The catalog holds
21 formation templates (4-4-2 … 5-3-2), each 1262 B, marker `76 b9 f4 07`; the block
after the string differs per shape (geometry only). The managed team's saved tactics sit
at ~30 MB and ~39 MB but differ from the game template by only a 4-byte tail UID — they
encode the *formation choice*, not roles/duties.

**Roles/duties are NOT recoverable.** Not in the formation records (pure geometry), not
in the saved-tactic records (formation ref + UID only), and NOT stored as name strings
(searched "Poacher"/"Ball Winning Midfielder"/etc. — absent). FMM either keeps them as
defaults or in an unlocated compact numeric form. "How we fielded the team" = formation
name (stored) + XI slot order (posOrder) + each player's natural position (global record)
→ reconstructed in `fielding.py`, validated 10/11 vs ground truth. Shape recoverable;
roles/duties are a dead end without much more speculative digging.


## 4. Match events: yellow cards — SOLVED ✅

**Fix:** yellow-card flag is **byte 53** of the 54-byte player stat block (1 = booked).
Confirmed vs `ground_truth_match1`: Karacabey HOME pos2 & pos3 booked → b53=1;
Bucaspor AWAY pos6 (Yüksel) booked → b53=1; everyone else 0. Plain yellows are NOT in
the header event stream — only here. Now decoded as `yellow` in `parse_match.py` and
exported per player in `season_data.json` (`home_xi`/`away_xi` → `yellow`).

## 2. Stoppage-time minutes — SOLVED ✅

**Fix:** the event minute is a `u16` where the **low byte = base minute** (0-based,
+1) and the **high byte = added minutes**. e.g. `59 03` → base 89+1=90, added 3 →
`90+3` (previously misread as 858). `parse_events` now emits `min` (base int),
`added`, and `min_display` (`"90+3"` / `"23"`). Verified: the 3-3 White Group final
goal now shows `90+3`.

## 3. Star player (man of the match) — RESOLVED (derived, not stored) ✅

**Finding:** the star player is **not** stored as an explicit field. Searched
thoroughly:
- No fixed header offset holds a star TID — the star's TID only appears in the header
  as normal *event* entries (goals), at no consistent offset across matches.
- No per-block flag: offset 32 (rating) is the ONLY byte where the team-star is the
  unique maximum in both XIs. There is no decimal rating (offsets 30-34 are all zero).

So the "star man" the match screen shows is **derived** = the top-rated player. It's
exposed **per team** as `star_home` / `star_away` (max `rating`, ties broken by goals,
assists, then completed passes). Verified: Menize (rtg 9) for Bucaspor in the 3-3, and
Duruk (rtg 9) in the 2022-05-25 play-off. NOTE: this is your *team's* stand-out — in
the 3-3, Karacabey's Taşkaya scored a 10, so a *match-wide* single star would be him,
not Menize. Because only integer ratings are stored, ties within a team are best-effort.

## 1. Play-off matches labelled generically — ADDRESSED ✅

**Fix:** comp_id 227 = the promotion play-off phase (filed under parent "Turkish 2.
League"). `season_data.json` now labels these `"Turkish 2. League Play-Off"`, and for a
two-legged tie (same two clubs) tags **First/Second Leg by date order** (plus a `leg`
field). Verified: 2022-05-21 lost 2-1 away (First Leg), 2022-05-25 won 1-0 home (Second
Leg) — matches your account.

**Not done (insufficient data):** the exact round name (Quarter/Semi Final) is a
*composed* string ("2. League Third Place Playoff Semi Final First Leg") built from a
generic round-word table at ~6.49 MB (0x62ff68: "First Leg", "Second Leg", "Quarter
Final", "Semi Final", …). With only ONE tie (2 matches) in this save there isn't enough
signal to triangulate the header's round reference reliably. If more play-off matches
appear in a future save we can pin it. Leg is inferred by date, which is robust.

**Bonus find:** byte at `date_off-1` = **1 when the managed team is home, 0 when away**
(split 38/1 vs 36/0 across the season; every "1" has home_tid 6567 or 11320). Exposed
as `home_flag`. (It is NOT a leg indicator — that theory was disproven.)

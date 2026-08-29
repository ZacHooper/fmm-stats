# Known bugs / follow-ups

## 14. Manager/staff records — identified structurally (formation + style still open)

Located the per-club MANAGER record for 3 Danish Superliga clubs from user-supplied
ground-truth screenshots (AaB / Niels Frederiksen, FC Nordsjælland / Kjetil Knutsen,
OB / Radoslav Látal — all dated 25 Nov 2024). Used snapshot `frem-2024-11-10.fms` (no
closer save exists in R2 for that date; manager identity/personality don't drift over
2 weeks, so it's still a valid ground-truth match).

**Found by:** combining #11's staff rule (SID == `ffffffff`) with an exact cross-check —
scan every `FFFFFFFF`-marked info record (same shape as `reference.parse_info`) with a
plausible DOB year, keep the ones whose `club_tid` (+42) matches the target club AND whose
DOB (day-of-year + year, both u16) matches the screenshot exactly. One unambiguous hit per
manager:

| | tid | club_tid | file offset (frem-2024-11-10.fms) |
|---|---|---|---|
| Niels Frederiksen | 1619 | 328 (AaB) | 759558 |
| Kjetil Knutsen | 1134 | 2465 (FC Nordsjælland) | 705295 |
| Radoslav Látal | 329 | 371 (OB) | 613993 |

Record shape (identical to the player info-field, offsets relative to record start):
```
+0  tid u32              +4  uid u32
+8  first_name_id u32    +12 last_name_id u32
+16 FFFFFFFF marker
+20 dob day-of-year u16  +22 dob year u16
+24 nationality u16
+42 club_tid u16
+52..59 personality block (see #9 — now fully resolved, below)
+60..63 FFFFFFFF          (no player-attribute SID — the staff marker from #11)
```
All fields confirmed byte-exact against the 3 screenshots: tid/uid, name ids, DOB, three
*different* nationality codes matching Danish/Norwegian/Czech, club_tid, and all 8
personality values.

**Resolves #9's "decode TODO".** The 8-byte block at +52..59 is exactly the community-nugget
order it guessed, as plain single bytes with no interleaving needed — Adaptability, Ambition,
Determination, Loyalty, Handling Pressure, Professionalism, **Sportsmanship** (hidden — not
shown on the Manager Profile screen, which is why the old Bucaspor lead only matched 6/8
against on-screen values), Temperament. Verified 1:1 against all three screenshots' visible
7 (everything but Sportsmanship, which has no UI to check against).

**Formation-shape catalog located** (context for #10's "saved tactics" note): 21 templates at
~20.66-20.69 MB, marker `76 b9 f4 07` + zero-padded ASCII name + 1262 B of geometry each, in
fixed declaration order (0=4-4-2, 2=4-1-2-2-1, 5=4-2-3-1, … 18=5-2-2-1 … 20=5-4-1). Pure
geometry — diffed all 21 records byte-for-byte and confirmed no offset in `[0,1262)` carries
a redundant per-entry 0-20 index; identity is declaration order only.

**NOT yet found: Style and Formation preference** (the two fields actually asked for), and now
**decisively ruled out as a nearby raw byte**, not just "not found yet" — see the 7-manager
follow-up below.

**Ground truth (verbatim from all 7 screenshots gathered so far — kept here so it survives
without them):**

| field | Frederiksen (AaB) | Knutsen (FCN) | Látal (OB) | Thorup (FCK) | Marsch (FCM) | Hansen (SønderjyskE) | Machín (Silkeborg) |
|---|---|---|---|---|---|---|---|
| Nationality | Danish, Uncapped | Norwegian, Uncapped | Czech, 47 caps / 1 goal | Danish, Uncapped | American, 2 caps / 0 goals | Danish, Uncapped | Spanish, Uncapped |
| DOB (age) | 5/11/1970 (54) | 2/10/1968 (56) | 6/1/1970 (54) | 21/2/1970 (54) | 8/11/1973 (51) | 28/7/1979 (45) | 7/4/1975 (49) |
| Reputation | Regional | National | National | Continental | National | Regional | National |
| Job Status | Very Secure | V. Insecure | Very Secure | Very Secure | Secure | Secure | Secure |
| Adaptability | 12 | 10 | 9 | 17 | 14 | 9 | 11 |
| Ambition | 10 | 19 | 14 | 11 | 13 | 7 | 13 |
| Determination | 14 | 15 | 17 | 16 | 15 | 7 | 14 |
| Loyalty | 14 | 13 | 17 | 18 | 16 | 16 | 9 |
| Handling Pressure | 14 | 15 | 16 | 17 | 14 | 11 | 13 |
| Professionalism | 14 | 19 | 17 | 14 | 13 | 14 | 14 |
| Temperament | 15 | 17 | 4 | 17 | 9 | 16 | 9 |
| Discipline | 16 | 16 | 14 | 7 | 13 | 13 | 14 |
| Financial Control | 12 | 16 | 12 | 10 | 2 | 9 | 11 |
| Judging Ability | 11 | 11 | 14 | 11 | 15 | 11 | 13 |
| Judging Potential | 13 | 15 | 9 | 10 | 13 | 11 | 11 |
| People Management | 10 | 13 | 7 | 15 | 16 | 14 | 15 |
| Motivating | 11 | 16 | 12 | 13 | 15 | 15 | 13 |
| Tactical Knowledge | 13 | 13 | 13 | 12 | 14 | 12 | 13 |
| Goalkeeping | 4 | 6 | 6 | 1 | 1 | 1 | 4 |
| Outfield | 10 | 12 | 10 | 11 | 13 | 9 | 11 |
| Youth | 18 | 12 | 5 | 15 | 14 | 12 | 12 |
| Ability (stars /5) | 3.5 | 4.5 | 3.5 | 3.5 | 4 | 3 | 3.5 |
| Rank | - | - | - | 25th | - | - | - |
| **Style** | **Attacking** | **Attacking** | **Defensive** | **Attacking** | **Normal** | **Normal** | **Normal** |
| **Formation** | **5-2-2-1** | **4-1-2-2-1** | **4-2-3-1** | **4-1-2-2-1** | **4-4-2** | **4-1-2-2-1** | **5-2-1-2** |
| Status line | "Enjoying his role at the club" | "Determined to succeed at the club" | "Proud to be managing OB" | "Proud to be managing FC København" | "Enjoying his role at the club" | "Enjoying his role at the club" | "Happy to be managing Silkeborg IF" |

Located and verified all 4 new managers' records the same way (DOB+club_tid cross-check,
personality block byte-exact): Thorup tid 861187, Marsch tid 767339, Hansen tid 743453, Machín
tid 782702 (all in `frem-2024-11-10.fms`).

**Ruled out this round (2026-08-29 follow-up):**
- **Displayed attributes don't derive formation or style either** — checked directly against
  the screenshot values (not the file): no attribute is an exact match or constant offset from
  the formation catalog index across all 7 managers, and no attribute cleanly separates the
  three Style groups (Attacking/Normal/Defensive all overlap on every one of the 17 values).
- **Formation-index-as-nearby-byte is now dead, not just unconfirmed.** Re-ran the exact-byte
  search with all 7 managers (was 3) out to **±50,000 bytes** — zero matches. At n=7 and this
  window, a coincidental hit is essentially impossible, so this rules the hypothesis out rather
  than just failing to find it.
- **The `record+85` Style lead is refuted.** With the 4 new managers it no longer holds: Fred
  (Attacking)=4, Knutsen (Attacking)=4, but Thorup (also Attacking)=5 — same value as Látal
  (Defensive)=5 and Hansen (Normal)=5 — while Marsch (Normal)=4 matches the Attacking pair.
  No grouping survives. Confirmed coincidence, not signal.
- **Cross-manager constant-byte scan (all 7, offsets -60..+250) turned up nothing new.**
  Everything constant across all 7 is already-known structure — the `FFFFFFFF` markers/padding,
  and **`record+33 == 0` for all 7**, which independently confirms #11's staff-vs-player flag
  (`info+33`: 1=player, 0=staff) using our verified manager set. No low-cardinality offset in
  the *actual* record zone (roughly `[-60,+64)`, before the unrelated-record contamination
  noted below) lines up with Style or Formation.
- **One unexplained oddity, unrelated to Style/Formation:** `record+34` and the u32 at
  `record+36..39` are near-constant across 6 of the 7 managers (`+34`=1, `+36..39`≈1900) but
  Frederiksen alone differs at *both* positions (`+34`=175, `+36..39`≈2019) — worth another
  look some time (maybe a "date appointed to current club" field — plausible since Frederiksen
  could be the one manager here who changed jobs mid-save while the other 6 are default
  appointments), but not chased further this round since it doesn't look Style/Formation-shaped.
- **No wage/contract record for managers.** Tested `staging.scrape_contracts`'s exact
  `[tid][0x01][wage u16]…[expiry]` validator (region 16-40M) against the 3 manager tids —
  zero hits for all three, vs. clean real wages/expiries when run against ordinary AaB
  player tids as a sanity check. Confirms managers don't get a contract-shaped record at
  all, and confirms the `[01 03][wage-like u16]…` bytes trailing each manager's info-field
  (noted as an open question last round) belong to some unrelated nearby PLAYER's contract,
  not the manager — the true manager record is just the ~64 bytes mapped above, nothing
  appended after it.
- **No wage/contract record for managers.** Tested `staging.scrape_contracts`'s exact
  `[tid][0x01][wage u16]…[expiry]` validator (region 16-40M) against the 3 manager tids —
  zero hits for all three, vs. clean real wages/expiries when run against ordinary AaB
  player tids as a sanity check. Confirms managers don't get a contract-shaped record at
  all, and confirms the `[01 03][wage-like u16]…` bytes trailing each manager's info-field
  (noted as an open question last round) belong to some unrelated nearby PLAYER's contract,
  not the manager — the true manager record is just the ~64 bytes mapped above, nothing
  appended after it.
- **The player attribute "raw 0-255 → 1-20" trick doesn't transfer as-is.** `model.py`'s
  formula is a regression *fit* on a large player ground-truth set, tied to offsets inside
  the player-only 78-byte SID grid managers don't have. Tried the general version anyway —
  swept `raw // k` / `round(raw/k)` / `ceil(raw/k)` for k=9-15 across a ±2000-byte window
  for all 10 undecoded manager attributes. Got exactly 2 "hits", both spurious: Tactical
  Knowledge (constant at 13 for all 3 managers, so any near-constant byte in range trivially
  "matches" — the already-known DOB-year byte did) and Outfield (matched the already-known
  nationality-code byte purely by coincidence of scale). **Lesson: with only 3 ground-truth
  managers there's no way to distinguish a real formula from a coincidence** — this needs
  either many more managers (to fit for real, the way the player model was) or a location
  found some other way, not curve-fitting on 3 points.

**To close this out — next session:** the nearby-byte hypothesis is now dead at n=7 (both the
raw catalog-index search and the `record+85` lead), so the structural lead is the strongest
remaining option:
1. **Structural lead (still untested, now the leading candidate):** Style/Formation/Rank/
   Ability-stars are manager-only UI fields that plain staff don't have — plausible they live
   in a wholly separate manager-only record (not the generic staff info-field), maybe keyed by
   club_tid alone. Not yet searched for.
2. **Diff two saves** where the same club's manager (or their tactic) changed, per
   CLAUDE.md method #4 — we now have 7 candidate managers to watch for a change in a future
   snapshot.
3. **More ground truth is still useful** but no longer for the dead nearby-byte leads — mainly
   to widen the Style value set (still only seen Attacking/Normal/Defensive) if a fitted-model
   approach becomes viable later, or once a real candidate field is found structurally.

## 12c. LIGHT results (simulated non-managed games) — SOLVED ✅

Only the MANAGED club's games get detailed per-player records (BUGS #12b). Every OTHER
loaded game (incl. Turkish Super League) stores a LIGHT result: just teams, score,
competition and a coarse date. Decoded in `fmparser/lightresults.py`; extracted by
`dump_lightresults.py` → `output/<label>/light_results/`.

**Record layout (pinned vs ground truth — our own games + the Super League results-day
screenshot).** Region ~47–50.5 MB; each fixture stored in ≥2 copies **516 bytes apart**:
```
+0 home_tid u16 · +2 away_tid u16 · +4 scoreH u8 · +5 scoreA u8
+8 flags u16 (0x40xx/0xc0xx, a marker) · +10 competition CID u16 ★ · +12 year(2020/2021)
```
**The league key is the CID at +10** — 118 Turkish Super League, 228 our 2.League White,
117 Turkish Cup, 275 English FA Cup, 258 EURO Cup, etc. Prior work chased the `+8` 0x40xx
value ("compref") and MISSED the real cid two bytes over — that was the whole blocker.
Validated: `+10` cleanly separates league / cup / European (Galatasaray → 118 league +
117 cup; Fenerbahçe → 118 + 117 + 258 EURO). Score is `[teamAscore][teamBscore]`; a game
appears from both perspectives (A-vs-B and B-vs-A), so team order just reflects whose row.

**Delivered:** club→league for the whole DB (341 clubs), every loaded league found and
(mostly) named — Turkish Super League, Turkish 1./2. League Red+White, Vanarama National
League N/S, Greek Super League 2 N/S — plus computed standings per league. Guard:
`tests/test_lightresults.py` (Super League = its real 20 clubs; Alanyaspor 1-0 Başakşehir
decodes; league/cup split holds).

**Known limits (not blockers):** (1) COVERAGE is partial (~⅓ of a season) — a SECOND
cid-less result list (~49.36 MB, repeats the home team + a 0x42xx value) isn't parsed, so
standings points/played are a lower bound and ordering is approximate. (2) NAMING:
`reference.comp_detail` mis-names some small-cid / foreign comps (e.g. a Turkish reserve
league shown as "Angola"); the cid grouping is always correct — name these via the tagged
DATA DICTIONARY (docs/DATADICT.md) as a follow-up.

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
is NOT here — those stay in the packed structures. Being parsed in `fmparser/tagged.py`.

## 11. Players vs staff in the info DB — classified by SID

The info section is a ~31k-record spine for the WHOLE database, and it contains
non-players too (managers/coaches/scouts). We classify: **SID == `ffffffff` → staff**
(no linked player attribute record), otherwise player. Verified: staff average age 45
(68% over 40) vs 26 for players; and an explicit type flag at **info+33** (1=player,
0=staff) agrees ~99% with the SID rule. The ~0.7% where +33 disagrees are **likely
player-coaches** (both roles). We classify by SID, which counts a player-coach as a
player (they have a real SID) — the intended behaviour. Not special-cased further.
Staff are written to `staff.json` (identity only; names unresolved like all opponents).

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

## 6. info-field: +28 (flag28) — NOT foot, NOT role (both disproven)

`flag28` (info+28) varies 0/1/2 among players who are all "player" — so NOT the role
flag. I hypothesised preferred foot, but that's **disproven**: Murat Demir is "Left
Only" in-game yet flag28=1, the SAME value as the right-footed Behram/Bıyık/Duruk.

**Rough guide alignment (answers "does +28 line up?"):** No. The guide's Step 2 info
field lists `nationality, 2nd nationality, DECLARED NATIONAL TEAM, role flag` — i.e.
there is an extra u16 ("declared national team") between 2nd-nationality (+26) and the
role flag. So our +28 most likely = **declared national team** (low byte); the real
role flag would sit ~+30. Left as raw `flag28`.

## 7. Preferred FOOT — SOLVED ✅

Feet ARE in the squad-snapshot record, but **AFTER the club marker** (that's why the
attribute-block search missed them). Anchored on marker offset M (`a7 19 ff ff`):
- **left foot = byte M+33**, **right foot = byte M+34** (both 0-20).

Confirmed vs 10 players incl. an outfield left-footer (Alıç) and a two-footer (Sun):
left corr **0.92**, right corr **0.97** with the in-game foot colours. `attrs.py` now
returns `feet` + a `preferred_foot()` label (thresholds: weak foot <=7 → "... only";
"Either" only when both >=16 and close). All 10 ground-truth labels match exactly:
Demir 20/5 "Left only", Alıç 20/9 "Left", Sun 15/20 & Yıldırım 15/20 "Right",
Turan 7/20 & Efe 7/20 "Right only", etc.

**Bonus — record layout after the marker M** (see the byte-map artifact):
`M+33 Lfoot · M+34 Rfoot · M+35 CA(u16) · M+37 PA(u16) · M+39 const-ref-UID(u32)
· M+43 ffff`. **CA≤PA holds for all 28 players** → M+35/M+37 are almost certainly
Current/Potential Ability. Still unlabelled and worth chasing (they VARY across
players): tail bytes M-35…M-26 and post-marker M+4…M+12 / M+25…M+29.

## 8. League-wide attributes: displayed = FORMULA over stored sub-attributes

**Breakthrough (user):** in the 78-byte global record, the attribute block is at
b-34..b-1 (relative to positions start P) in **exact rough-guide Step-6 order**
(offset = guide# - 35). Confirmed by the 1-20 anchors that land exactly where the
guide predicts: Pace b-24, Strength b-23, Stamina b-22, Technique b-21, Aggression
b-19, Leadership b-16, Agility b-5 (all 28/28 or near).

Displayed attributes are **formulas** over stored sub-attributes, not raw values:
- **Teamwork = floor((b-25 + b-9)/2)** — Unselfishness + Work Rate. **28/28 exact.**
- **Aerial** combines Heading (b-29) + Jumping (b-28) [+ likely the GK-aerial b-4 on
  the 0-255 scale]. avg of b-29/b-28 alone only fits ~16/24 — needs the 3rd component.
- **Shooting** = Finishing (b-31) + Long Shots (b-30), but BOTH are on the **0-255
  scale** (Behram b-31=40, Bıyık b-31=253) — the scale/formula isn't cracked yet.

**Key open sub-problem:** decode the **0-255 scale**. Some sub-attributes are stored
1-20 (mental/physical: Pace, Strength, Unselfish, WorkRate, Heading, Jumping…), others
0-255 (technical/GK: Crossing b-34, Dribbling b-33, Tackling b-32, Finishing b-31,
LongShots b-30, Passing b-27, Decisions b-26, Creativity b-12, Movement b-11,
Positioning b-10, Handling b-7, Kicking b-6, AerialGK b-4, Reflexes b-3, Communication
b-2, Throwing b-1). These 0-255 values are an INPUT to a formula, not a linear scale
(Pazarlı's three 4-value attrs all show byte 174; no linear/complement/nibble map holds).

**Tools:** `export_calibration.py` → `calibration.csv` pairs displayed values with all
78 raw bytes (labeled in guide order, `?`=maybe, `=`=formula component) for the 28
Bucaspor players (the only set with BOTH forms). Model the 0-255→display transform there.

**→ Full write-up in `ATTRIBUTE_DECODING.md`** (record layout, exact formulas, the
regression coefficients actually used, where it's wrong, and the dig-deeper TODO incl.
the FM CA weight table + the FMM "physical don't count toward CA" rule that explains why
physical attrs store raw/1-20 and CA-attrs store entangled).

**0-255 scale — DECODED to ±1 via regression (`regress.py`):** the 0-255 bytes WRAP
(unwrap: b+256 if b<128; strong attrs have low bytes) and rescale to the 1-20 display as
a function of CA (+ position + the 9 knowns) — exactly the user's theory. Model:
`display ≈ round(linear(unwrapped_byte, CA, own*CA, position, mean9))`. Result across
14 attrs × 28 players: **63% exact, 93% within ±1** (Tackling/Shooting/Decisions/
Kicking/Reflexes = 28/28 within ±1). NOT bit-exact — FM's true formula needs
position-specific per-attribute CA-weight tables we can't fully triangulate from one
squad — but good enough to ESTIMATE any opponent's full attribute set to ±1. `regress.py`
grid-searches feature subsets per attribute and reports exact / ±1 / R² / chosen features.

## 9. Personality block (8 values before the SID) — SOLVED ✅ (see #14)

Community nugget: the 8 values immediately before the SID are personality, alphabetical:
Adaptability, Ambition, Determination, Loyalty, Pressure Handling, Professionalism,
Sportsmanship, Temperament. In our record the SID is at P-42, so this is **P-50..P-43**.
Partial confirmation: **b-50 (Adaptability) = 16 for BOTH Yüksel and Aktaş** (the two
"Adaptable"-personality players) vs 8/0/4 for others. But the 8 bytes aren't all clean
1-20 (interleaved 0/>20 values) — likely needs a u16 or different stride; decode TODO.

**Resolved in #14**, from the Frem career's 3 opposition-manager ground truths: the block
IS plain single bytes in exactly this order, no interleaving — the earlier Bucaspor read
just had one value (Sportsmanship) that isn't shown in any UI to confirm against, which
made the clean pattern look noisier than it is.

## 5. Hidden-attribute leads (LOW priority — user: immersion)

Ground-truth hints gathered for when/if we decode hidden attrs:
- Adaptability HIGH: Metin Yüksel and Ahmet Aktaş (in-game personality "Adaptable").
- Set Pieces: Balıkuv high (effective), Behram low (unconvincing FK taker).
- Injury Proneness HIGH: Menize (injured 4× this season).
- CA/PA gap large: Ataş (young keeper, high potential).
- Reputation lead: after-marker u16 tracks it (Gölbaşı highest, Ataş lowest).
- Only idx9 remains unmapped in the visible 0-23 attribute block.

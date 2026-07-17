# Known bugs / follow-ups

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

## 9. Personality block (8 values before the SID) — lead

Community nugget: the 8 values immediately before the SID are personality, alphabetical:
Adaptability, Ambition, Determination, Loyalty, Pressure Handling, Professionalism,
Sportsmanship, Temperament. In our record the SID is at P-42, so this is **P-50..P-43**.
Partial confirmation: **b-50 (Adaptability) = 16 for BOTH Yüksel and Aktaş** (the two
"Adaptable"-personality players) vs 8/0/4 for others. But the 8 bytes aren't all clean
1-20 (interleaved 0/>20 values) — likely needs a u16 or different stride; decode TODO.

## 5. Hidden-attribute leads (LOW priority — user: immersion)

Ground-truth hints gathered for when/if we decode hidden attrs:
- Adaptability HIGH: Metin Yüksel and Ahmet Aktaş (in-game personality "Adaptable").
- Set Pieces: Balıkuv high (effective), Behram low (unconvincing FK taker).
- Injury Proneness HIGH: Menize (injured 4× this season).
- CA/PA gap large: Ataş (young keeper, high potential).
- Reputation lead: after-marker u16 tracks it (Gölbaşı highest, Ataş lowest).
- Only idx9 remains unmapped in the visible 0-23 attribute block.

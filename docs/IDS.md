# ID map — what identifiers exist and how they link

The save is a web of entities joined by IDs. This is the inventory of every ID we've
found, what it keys, and which joins are solved vs open. Use it to anchor future digging.

## Entities & their IDs

### Player and staff  ([`docs/parser/person_info.md`](parser/person_info.md))
The person table is keyed by **TID** (u32, the slot index), and a tid is a recycled slot: key a
person by `(tid, dob)`. `sid` links a player's [attribute record](parser/player_attributes.md),
`id2` a staff member's [staff record](parser/staff.md); name ids resolve through
[names](parser/names.md).

### Club  ([`docs/parser/clubs.md`](parser/clubs.md))
**TID** (u32) is the club key and the club table's slot index; national teams and U21 sides are
rows of the same table. **UID** is the database id, negative on a national team.

Known anchors (found by name): Galatasaray **955**, Fenerbahçe **954**, Beşiktaş **951**,
Trabzonspor **961**, Liverpool **356**, Bucaspor **6567**, Karacabey **6353**.

### Competition  (comp record, ~13 MB)
| id | size | notes |
|----|------|-------|
| **cid** | u16 | primary comp key. 228 = Turkish 2. League White Group |
| **uid** | u32 | 463485 for cid 228; reserve leagues ~2e8 |
| type / nation | u8 | bytes after the name strings (league/cup/reserve/friendly; 173) |
| **compref** | u16, `0x40xx` | the id used in **fixtures/results** — a THIRD, compact comp id. NOT equal to cid. e.g. one confirmed Super-League result had compref `16512` (0x4080) |

### Nation  ([`docs/parser/nations.md`](parser/nations.md))
`nation_id` u16, the nation table's slot index: 138 Denmark, 139 England, 173 Turkey.

## TID RECYCLING

A tid is a slot, not a person; key people by `(tid, dob)`. Measured and explained in
[`docs/parser/person_info.md`](parser/person_info.md).

## PLAYER → CAREER HISTORY

The attribute record's `history_head` (+4) points at the player's chain in the history pool:
[`docs/parser/player_attributes.md`](parser/player_attributes.md),
[`docs/parser/history.md`](parser/history.md).

## Joins
- player.SID → attribute record  ✅ solved (staging + record sweep)
- player.SID → **career-history chain**  ✅ solved (`history_head`, see § PLAYER → CAREER HISTORY)
- player.club_tid → club.TID  ✅ solved
- match/result: home_tid, away_tid, **comp** ✅ for OUR detailed matches (`[FF×8][home][away][cid]`)
- **club → league (whole DB)  ⚠️ OPEN** — the blocker. See below.
- nameID → player name  ✅ solved ([names](parser/names.md))

## The club→league problem (open)
- Top leagues (Super League, Premier League) ARE simulated but store only **light
  results** (teams, score, date, table position — no clickable detail). Only the
  managed club's games have the detailed `[FF×8]…` records.
- The light-result record IS decodable — one confirmed: `[..00 FF..][home:u16][away:u16]
  [scoreH:u16][scoreA:u16][compref:u16(0x40xx)]` → `1693 (Alanyaspor) 1-0 1368
  (Başakşehir), compref 16512`. But a reliable whole-file sweep isn't cracked: the
  `00 FF` anchor is too common (false positives), records are scattered, and the layout
  isn't consistent across all hits.
- **compref (0x40xx)** is the most promising league key — but we can't yet (a) sweep
  light-results reliably, nor (b) map compref ↔ cid ↔ league name.

## Sources useful for digging
- **Tagged schema region (~13–20 MB)** — a self-describing data dictionary: field names
  stored reversed (`comp`, `level`, `cash`, `ntms`, `team`, `id`, `stdt`…). Reveals
  record layouts. See `fmparser/tables/rule_files.py`, BUGS #13.
- **Known club names → TIDs** — the strongest anchor (used to find the clubs above).
- `data/rough-guide.md` — community hex guide.
- **Ground truth**: our own matches (exact home/away/score/comp/date) and the
  screenshots in `data/screenshots/` (e.g. a Super-League results day with positions).

## Reliable grouping without club→league
CA is a universal cross-league scale. Every club has players with CA, so
**mean-CA-per-club** ranks all clubs globally *now*, without needing league labels —
the pragmatic route to "what level is my team".

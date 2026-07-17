# ID map — what identifiers exist and how they link

The save is a web of entities joined by IDs. This is the inventory of every ID we've
found, what it keys, and which joins are solved vs open. Use it to anchor future digging.

## Entities & their IDs

### Player  (info record, ~whole file; the identity spine)
| id | size | notes |
|----|------|-------|
| **TID** | u32 | primary player key, used in matches, snapshot, everywhere |
| **UID** | u32 | global unique id |
| **SID** | u16 (stored in 4 bytes) | → the global **attribute** record. `ffffffff` = staff (no player record) |
| firstNameID / lastNameID | u32 | → name string table — **UNRESOLVED** (not a flat index) |
| nationality_id | u16 | 173 = Turkey |
| club_tid | u16 | → **Club**.TID |

### Club  (club record, ~7–13 MB)
| id | size | notes |
|----|------|-------|
| **TID** | u32 | primary club key. Big clubs have low TIDs |
| **UID** | u32 | |
| nation | u16 | first field after the 3 name strings |

Known anchors (found by name): Galatasaray **955**, Fenerbahçe **954**, Beşiktaş **951**,
Trabzonspor **961**, Liverpool **356**, Bucaspor **6567**, Karacabey **6353**.

### Competition  (comp record, ~13 MB)
| id | size | notes |
|----|------|-------|
| **cid** | u16 | primary comp key. 228 = Turkish 2. League White Group |
| **uid** | u32 | 463485 for cid 228; reserve leagues ~2e8 |
| type / nation | u8 | bytes after the name strings (league/cup/reserve/friendly; 173) |
| **compref** | u16, `0x40xx` | the id used in **fixtures/results** — a THIRD, compact comp id. NOT equal to cid. e.g. one confirmed Super-League result had compref `16512` (0x4080) |

### Nation
`nation_id` u16 — 173 Turkey. Others seen: 145, 158, 159, 175, 177 (loaded/scattered).

## Joins
- player.SID → attribute record  ✅ solved (staging + record sweep)
- player.club_tid → club.TID  ✅ solved
- match/result: home_tid, away_tid, **comp** ✅ for OUR detailed matches (`[FF×8][home][away][cid]`)
- **club → league (whole DB)  ⚠️ OPEN** — the blocker. See below.
- nameID → player name  ❌ open (only own club, via snapshot inline names)

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
  record layouts. See `fmparser/tagged.py`, BUGS #13.
- **Known club names → TIDs** — the strongest anchor (used to find the clubs above).
- `data/rough-guide.md` — community hex guide.
- **Ground truth**: our own matches (exact home/away/score/comp/date) and the
  screenshots in `data/screenshots/` (e.g. a Super-League results day with positions).

## Reliable grouping without club→league
CA is a universal cross-league scale. Every club has players with CA, so
**mean-CA-per-club** ranks all clubs globally *now*, without needing league labels —
the pragmatic route to "what level is my team".

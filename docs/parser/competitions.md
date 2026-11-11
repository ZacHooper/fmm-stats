# competitions  ([`fmparser/tables/competitions.py`](../../fmparser/tables/competitions.py))

Every competition in the database: leagues, cups, continental and international tournaments,
reserve leagues, friendlies. A count-framed table of variable-length records,
`[>= 8 × ff][count u16]`, directly after the [club table](clubs.md), keyed by
`cid == slot index`. 1,706 slots on both Truro saves (FMM27), 1,701 of them named; on FMM22
1,372 slots on Frem (~12.6 MB in), 1,371 on Bucaspor, 100 of them blank. Static in shape,
but the game rewrites a record's reputation and its holders as the career runs.

The competition has two ids: **`cid`**, the save's own (slot index; what clubs, matches and the
roll of honour use), and **`uid`**, the database id. The archive names each competition's rules
member by uid (`comp_<uid>.dat`, [comp_rules](comp_rules.md)), and the data dictionary's rule
files refer to competitions by uid too ([rule_files](rule_files.md)).

FMM22's record ends a byte earlier and has no women's flag (Layout, FMM22);
`comp_table(mm)` picks the declaration (`COMP_TABLE_FMM27` on FMM27).

## Layout

```
header   [>= 8 × ff][count u16 = 1,706]
record   [cid u16][uid u32]
         [len u32][long name][ff]  [len u32][short name][ff]  [len u32][code]
         [14 B trailer]
         [n u32][n × 8 B entrant]
         [22 B holders tail]
```

On FMM27 `cid == slot` holds on every slot and the walk ends on the [nations](nations.md)
frame; the holders resolve as club uids (Enterprise National League South: Worthing,
Hornchurch, Torquay United), and so do all 1,182 entrant-list refs. The other counts in the
last column are from FMM22 (`frem-2030-06-22`).

| field | type | meaning | how we know |
|---|---|---|---|
| `cid` | u16 | slot index | `cid == slot` on every slot |
| `uid` | u32 | database id; names `comp_<uid>.dat` | 147/147 archive members resolve ([comp_rules](comp_rules.md)) |
| `name`, `short`, `code` | len-prefixed | "3F Superliga", "3F Superliga", "SL"; one unnamed byte after the long and short names (`ff`, as on [clubs](clubs.md)), none after the code | |
| trailer +0 `type` | u8 | competition type id (below) | |
| trailer +1 `continent` | u16 | confederation 0–5; `ffff` on 7 world competitions | 2 on every European competition |
| trailer +3 `nation` | u16 | [nation](nations.md) id; `ffff` = none (continental and international) | 138 Denmark on the Danish ones; 139 England on Enterprise National League South |
| trailer +5, +7 `fg_colour`, `bg_colour` | u16 | colours; unverified encoding, not extracted | |
| trailer +9 `reputation` | u16 | the competition's reputation; the game updates it (Superliga 144 on frem-2030-06-22) | Evidence |
| trailer +11 `level` | u8 | 0 = a nation's top flight, 1, 2, … below it | the Danish pyramid, below |
| trailer +12 `parent_cid` | u16 | the competition this one is a part of; `ffff` = none | 737 named slots have one: Spanish Second Division B1–B4 → B, Argentine Opening/Closing Stage → Premier Division |
| entrant `ref` | u32 | club **uid** if positive, national team if negative (`-ref` = the nation's uid), `ffffffff` empty | 457/457 positive refs are club uids, 67/67 negative ones nation uids |
| entrant `season`, `ordinal` | u16, u8 | season (0 = unset); a small number, unnamed (0–4) | |
| entrant +7 | u8 | unnamed | |
| tail +0, +4, +8 | 3 × u32 | **the holders**: the last finished season's 1st, 2nd and 3rd as club **uids**; a cup holds winner and runner-up and `ffffffff` third | 25 of 26 leagues, below; not yet named in the module (`UNKNOWN`) |
| tail +12 `season_0`, +14 `season_1`, +16 `season_2` | 3 × u16 | that season: end year, start year, end year again; `ffff` × 3 when there are no holders | (2030, 2029, 2030) beside the 2029/30 holders |
| tail +18 | u8 | 1–5, unnamed | |
| tail +19 `is_women` | u8 | 1 on a women's competition (fmm-editor's `IsWomen`) | 1 on exactly the 133 women's competitions (Barclays Women's Super League, NWSL, the Women's FA Cup, the FIFA Women's World Cup, …) |
| tail +20 | 2 B | zero | |

**Type ids.** `type_id` is the real field; `type` in the output is a display label for the
five that are anchored on named competitions (0 league, 1 league, 2 cup, 8 reserve_league,
9 friendly), and every other value comes out as `type_N`. 0 is a nation's top flight and 1 a
division below it; both are round-robin leagues. On frem-2030-06-22 the named slots carry 29
distinct ids (895 × 1, 79 × 0, 69 × 4, 39 × 8, 29 × 28, 24 × 5, 23 × 2, …); 21 is the European
Champions Cup, 22 the EURO Cup.

**The Danish pyramid by `level`** (`nation 138`): 0 3F Superliga and Sydbank Pokalen; 1 NordicBet
Liga; 2 2. Division and the Second Division East/West; 3 3. Division; 4 Denmark's Series and
its four groups; 5 Danish Lower Division. Reserve groups 1–4 sit at levels 1–4.

**The entrant list** is populated on 24 competitions only (frem-2030-06-22): MLS lists its 28
clubs, Copa Libertadores 94 entries over two seasons, Copa América CONMEBOL's ten nations, the
European International League divisions their nations, the Scottish Cup 13 empty slots. It is
not a qualification list in general: the European Champions Cup and the Superliga have none.
The entries' count is read as a u32; bytes +1..+3 are zero on every slot.

### FMM22

- The long and short names are followed by `00`, not `ff`.
- The holders tail is **21 bytes**: +18 is a u16 (1–5; FMM22 stores 0 where FMM27 has
  `is_women`), then one byte, 0 on every named slot, where FMM27 has two.
- The header's count is 1,372 on Frem.

## Evidence

`truro-2026-07-25`. Both Club Information screens ([clubs](clubs.md), `img/clubs-fmm27-1.jpg`
and `-2.jpg`) read League Competition `Enterprise National League South`; both clubs'
`league_id` is 331, and record 331, at byte 14,580,277, is

`4b 01 | ef 2b 4e 00 | 20 00 00 00 "Enterprise National League South" ff …`

cid 331, uid 5,123,055, a 32-byte name: short `Enterprise South`, code `NLS`, nation 139
(England), level 5. Tested by `tests/test_reference_fmm27_evidence.py`.

### FMM22

`frem-2030-06-22`. The 3F Superliga record, cid 2, at byte 12,587,413:

```
02 00 | 06 00 00 00 | 0c 00 00 00 "3F Superliga" 00 | 0c 00 00 00 "3F Superliga" 00 | 02 00 00 00 "SL"
00 | 02 00 | 8a 00 | ff 7f | 52 01 | 90 00 | 00 | ff ff                  trailer
00 00 00 00                                                            no entrants
fb 01 00 00 | f9 01 00 00 | 21 02 00 00 | ee 07 ed 07 ee 07 | 01 00 | 00     tail
```

cid 2, uid 6; type 0, continent 2, nation 138, reputation 144, level 0, no parent. The tail's
three uids 507, 505 and 545 are Frem, FC København and OB, and the season reads (2030, 2029,
2030): the 2029/30 table's top three as the store rebuilds it (`raw.club_league_history`, year
2029: Frem 1, FC København 2, OB 3). The roll of honour does not have 2029/30 yet on this save
([comp_honours](comp_honours.md)), so this is the only place the save holds the season just
finished.

**The holders, all leagues.** Comparing the tail with `raw.club_league_history` positions 1–3
for each league's latest season: 22 match exactly for 2029/30; three Spanish leagues (Second
Division, Federation 1A and 1B) carry 2028/29 with season (2029, 2028, 2029) and match that
season exactly; the Belgian First National Division (play-offs) holds the same three clubs in a
different order. Cups hold two: the Sydbank Pokalen's are FC Nordsjælland and FC Midtjylland,
the EURO Cup's OL and Inter.

**The holders on screen.** A competition's Past Winners screen opens on 2029/30 on this save,
a season the roll of honour does not hold yet; the row is the holders tail. On all four lists
captured it matches: 3F Superliga Frem / FC København (`img/comp_honours-1.png`), Sydbank
Pokalen FC Nordsjælland / FC Midtjylland (`-2`), English Premier Division Liverpool / Chelsea
(`-3`), EURO Cup OL / Inter (`-4`). The other nine rows of each list are the roll of honour
([comp_honours](comp_honours.md)). The Pokalen's tail, at byte 12,617,678:
`5b 3a 0e 00 | 0e 02 00 00 | ff ff ff ff | ee 07 ed 07 ee 07 | 05 00 | 00`, uids 932,443 (FC
Nordsjælland) and 526 (FC Midtjylland), no third.

`reputation` has no number on screen: the game shows a competition's reputation as a star
rating (League Standards → Reputation), so it is checked only by its order (Superliga 144 >
NordicBet Liga 97 > 2. Division 80 > 3. Division 63 > Denmark's Series 33).

## Quirks

> **Quirk:** resolve an entrant or holder by **uid**, never tid. On FMM22, 131 of the 457 positive
> entrant refs also happen to be some club's tid, and the tid reading is wrong every time (uid 1913 is
> D.C. United, tid 1913 R.C. Villalbés); the Superliga holders' 507/505/545 read as St. Albans,
> Southend and Cyprus by tid.

> **Quirk:** `level` is only a pyramid level on leagues and cups. On FMM22, 107 competitions carry 100
> (international and youth tournaments, 27 of them type 4) and one carries 255. Filter on
> `type_id` before using it.

> **Dead end:** the order of `[count][entries][tail]` cannot be settled by the walk landing on
> `cid == slot`: `[count][tail][entries]` gives the same lengths, and on FMM22 1,348 slots have
> an empty list. Content settles it: the 3. Liga (cid 507) carries 20 entrants, and its holders
> decode after them and match its 2029/30 top three.

## Output

`output/<label>/competitions.json`, `{cid: {cid, uid, name, short, code, type, type_id,
nation_id, reputation, level, parent_cid}}` for the named slots (1,272 on frem-2030-06-22;
blanks left out; `nation_id` and `parent_cid` null for `ffff`). Loads into `raw.competitions`. Not extracted:
`continent`, the colours, the entrant list (read with `comp_refs(mm, cid)`) and the holders
tail. On FMM27 each competition also carries `is_women`.

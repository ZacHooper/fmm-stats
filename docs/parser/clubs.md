# clubs  ([`fmparser/tables/clubs.py`](../../fmparser/tables/clubs.py))

Every team in the world, one record per tid: clubs, reserve and B sides, national teams and
U21 national teams, all stored club-shaped. It follows the round-name table directly
(`[0xFF run][count u32]`, located by `after_frame` from `ROUNDS_TABLE`'s end) and is walked by
declaration with `tid == slot index`. 11,331 slots on Frem; the count differs by career
(12,278 on Bucaspor). Variable-length records, so there is no stride.

## Layout

A record is the segments of `CLUB_TABLE`, in this order:

| segment | field | type | meaning | how we know |
|---|---|---|---|---|
| `CLUB_HEAD` | `tid` | u32 | the team id; equals the slot index | the walk's invariant, on every slot |
| | `uid` | i32 | database id. **Negative on a national team: `-uid` is the nation's uid** | all 251 national teams, `frem-2030-06-22` |
| names | `name`, `short`, `code` | 3 × `[len u32][utf-8]` | long name, short name, 3-letter code. A `NAME_END` byte follows the first two: `00`, or `ff` after an empty name | screenshots; walk lands on `tid + 1` |
| `CLUB_TRAILER` (167 B) +0 | `based_id` | u16 | nation whose league the club plays in | Cardiff City = England (screenshot) |
| +2 | `nation_id` | u16 | the club's home nation | Cardiff City = Wales |
| +4 | `colour_0..5` | 6 × u16 | club colours, RGB555 (`0x7FFF` is white) | decode to the right kits |
| +16 | kits | 6 × (2 B + 10 × u16) | six kits: two flag bytes, then ten RGB555 colours. Slot 0 home, 1 away, 2 third; slots 3–5 not identified | Cardiff's three kits, Frem's and Stoke's two (screenshots) |
| +148 | `status` | u8 | 1 = Professional | both screenshots; values 0–3 |
| +149 | `academy` | u8 | **Training Facilities**, 1–20 (fmm-editor's name is wrong; see Quirks) | three Club Information screens |
| +150 | `facilities` | u8 | **Youth Facilities**, 1–20 (fmm-editor's name is wrong) | three Club Information screens |
| +151 | `att_avg`, `att_min`, `att_max` | 3 × u16 | named from fmm-editor; **not attendance** (TODO "Unnamed fields in records we already read") | |
| +157 | `reserves` | u8 | | |
| +158 | `league_id` | u16 | the club's league cid | Frem 2 = 3F Superliga, Cardiff 6 = Sky Bet Championship |
| +160 | `other_division` | u16 | `0xFFFF` when `league_id` is the club's league | |
| +162 | `other_last_position` | u8 | | |
| +163 | `stadium_id` | u16 | → [stadiums](stadiums.md) | Frem 181 = Valby Idrætspark |
| +165 | `last_league` | u16 | | |
| `block_167` | | `[u32 n][n B]` | unnamed; `n` is 8 | |
| `CLUB_STANDING` (23 B) +0 | `league_pos` | u8 | | |
| +1 | `reputation` | u16 | | Frem 6494 (3½ stars), Cardiff 5371 (2½ stars) |
| +3 | | 20 B | unnamed | |
| `affiliates` | | `[u16 n][n × 21 B]` | `[4 B][club1_tid u32][club2_tid u32][start day u16, year u16][end day u16, year u16][1 B]` | |
| `squad` | | `[u16 = 40][40 × tid u32]` | the first-team squad, fixed 40 slots; empty slots are `0`, `ffff` or `ffffffff` | Frem's squad screen (below) |
| `CLUB_STAFF` (123 B) +0 | `staff_0..10` | 11 × u32 | the coaching staff, **not including the manager** | Cardiff: Alex Neil is at the club, absent here, and shown as manager |
| +44 | `main_club_tid` | u32 | the parent team: a reserve side's first team, a U21 side's senior national team | Frem Reserves 7296 → 346 |
| +48 | `club_type` | u8 | 0 club (B sides included), 1 national team, 2 reserve side, 3 U21 national team | 251 type-1 rows are exactly the negative-uid rows; 228 type-3 rows are exactly the `… U21` names |
| +49 | | 74 B | unnamed | |
| `tail` | | `[u16 m][m × 9 B]` | unnamed | |

`scrape_clubs` derives three fields: `league_cid` (`league_id` when `other_division` is
`0xFFFF` and the id is real), `country` (= `based_id`), and drops empty squad/staff slots.

## Provenance

`frem-2030-06-22`. Frem's Club Information screen; Frem's record starts at byte 6,501,332, its
trailer at 6,501,378.

![Frem: Valby Idrætspark, 30,000, Professional, 3F Superliga](img/clubs-1.png)

| on screen | raw bytes | parsed |
|---|---|---|
| Full Name `Boldklubben Frem` | `@6,501,340 10 00 00 00 "Boldklubben Frem"` | `name` |
| flag on the card: Denmark | trailer +0 `8a 00`, +2 `8a 00` | `based_id` = `nation_id` = 138 (Denmark) |
| Status `Professional` | +148 `01` | `status` = 1 |
| Training `Superb` ★★★★½, Youth `Top` ★★★★★ | +149 `12`, +150 `14` | `academy` = 18, `facilities` = 20 |
| League Competition `3F Superliga` | +158 `02 00` | `league_id` = 2 |
| home kit, red/blue hoops | +16 flag `31`, then the colours | `kits[0]` red `#e00000` / navy `#002080` |
| card stars ★★★½ | `CLUB_STANDING` +1 `5e 19` | `reputation` = 6494 |

Cardiff City, record at 6,546,281, trailer at 6,546,328:

![Cardiff City: England flag, Sky Bet Championship, three kits](img/clubs-2.png)

| on screen | raw bytes | parsed |
|---|---|---|
| England flag on the card; a Welsh club | trailer +0 `8b 00`, +2 `af 00` | `based_id` 139 (England), `nation_id` 175 (Wales) |
| Training `Superb` ★★★★½, Youth `Great` ★★★½ | +149 `13`, +150 `0f` | `academy` = 19, `facilities` = 15 |
| Home blue, Away pink, Third mint | kits 0/1/2 start `57 01`, `ef 79`, `fe 7f` | `kits[0]` `#0050b8`, `kits[1]` `#f07878`, `kits[2]` `#f8f8f0`/`#b8e0d0` |
| Manager `Alex Neil` | tid 3037 not in `staff_0..10`; his person record's club is 426 | manager = the club's staff member missing from the list |
| card stars ★★½ | `CLUB_STANDING` +1 `fb 14` | `reputation` = 5371 |

Frem's squad screen. The array's count is `28 00` (40) at 6,501,582; 25 slots are filled, and
every player on screen is one of them (Nørager 13304, Ullits 10404, Sonne 10198, …). The
array's order is not the screen's.

![Frem's squad selection screen](img/clubs-3.png)

Stoke City, record at 6,595,197, trailer at 6,595,239. The facilities that settle which byte
is which (see Quirks):

![Stoke City: training State of the art, youth Excellent](img/clubs-4.png)

| on screen | raw bytes | parsed |
|---|---|---|
| Training `State of the art` ★★★★★, Youth `Excellent` ★★★★ | +148 `01 14 10` | `status` 1, `academy` = 20, `facilities` = 16 |
| bet365 Stadium, 30,089 | +163 `bb 02` | `stadium_id` 699 → `bet365 Stadium`, capacity 30,089 |
| Home red/white stripes, Away green; no third kit | kits 0, 1 | `kits[0]` white/`#c81028`, `kits[1]` black/`#009830`; `kits[2]` is the black-and-white default Frem also carries |

Tested by `tests/test_world_provenance.py`.

## Quirks

> **Quirk:** `academy` is Training Facilities and `facilities` is Youth Facilities, the
> reverse of fmm-editor's names. Three Club Information screens fit one scale this way round
> and none the other: Frem 18 / 20, Cardiff 19 / 15, Stoke 20 / 16 (training / youth) show
> 15 ★★★½, 16 ★★★★, 18–19 ★★★★½, 20 ★★★★★, i.e. stars = ⌊value / 2⌋ / 2. Read the
> fmm-editor way, Frem's 18 would be five stars and Cardiff's 19 three and a half. The parser
> and raw keep the byte names; `int.team_snapshots` maps `academy` to `training_facilities`
> and `facilities` to `youth_facilities` (#196).

> **Quirk:** a club with no third kit still fills kit slot 2, with the same black-and-white
> default (Frem and Stoke show only Home and Away).

> **Quirk:** `main_club_tid` is kept only when `0 < tid < 70000`, so the one parent that IS
> tid 0 is lost: Algeria U21 (11103) has `main_club_tid` None while the other 227 U21 sides
> resolve. Open in TODO as "Club `main_club_tid` drops tid 0".

> **Quirk:** national teams aren't a block at the front. tids 0–50 are national teams
> (Algeria, Angola, …), but the other 200 sit among the clubs, up to tid 6343 (Netherlands
> Antilles). Use `club_type = 1` or a negative `uid`, never a tid range. U21 national teams
> are the last 228 slots.

> **Quirk:** `based_id` and `nation_id` differ on a few dozen clubs (38 on `frem-2030-06-22`):
> Welsh clubs in the English pyramid, Derry City in Ireland's league, Liechtenstein's clubs in
> Switzerland's. The card's flag is `based_id`.

> **Quirk:** the squad array is who is in the squad: loaned-in players are in it, reserves
> aren't. `club_tid` on the person record is who owns the player. A lapsed loan can leave a
> departed player's `club_tid` on the club, so "our squad" comes from this array
> (`mart.squad_membership`).

> **Quirk:** club, competition and nation records share a shape (long name, short name,
> code). A scan by shape lands in the wrong table (a club once claimed Belgium's nation id);
> walk each table from its own frame.

> **Decision:** the whole record is carried, unnamed bytes declared `UNKNOWN`, so
> `scripts/audit/audit_records.py` accounts for every byte.

## Output

`output/<label>/clubs.json`, `{tid: club}`. The loader splits it into `raw.clubs` (tid and
name), `raw.club_details` (the trailer), `raw.club_squad`, `raw.club_staff` and
`raw.club_affiliates`.

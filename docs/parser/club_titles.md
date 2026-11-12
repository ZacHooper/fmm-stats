# club_titles  ([`fmparser/tables/club_titles.py`](../../fmparser/tables/club_titles.py))

**The managed club's titles**: each competition won, and the years. After the
[club seasons](club_seasons.md) pool, one `00` byte and a run of 550 `ff` (both on every save
measured), in a pool of 32 slots. This is the table the save map used to list as "league
titles".

## Layout

```
[u8 count]
count x [cid u16][club_tid u16][30 x year u16][u8 n_years]     65 bytes; years past n_years read ffff
32 - count empty slots: 64 x ff, then 00
```

One entry per competition, its years in order: on frem-2030-06-22 the 3. Division 2021,
2. Division 2022, NordicBet Liga 2023 and 3F Superliga 2028 and 2029. A year is the season's
start year, as in club seasons. What looked like "the first entry's leading byte is the entry
count, the others' is `01`" is the count byte in front of the pool and each entry's own
`n_years` at its end. Cups would land here too; no save measured has the user winning one.

**How it is found.** From the club seasons' end, skip the `00` and the `ff` run; the locator
accepts the count only if every entry names one club, holds at most 30 years with `ffff`
after them, and the rest of the 32 slots are empty.

## Evidence

`tests/test_club_seasons_evidence.py`, eight saves of both games: every title year is a
season with position index 0 in that competition in [club seasons](club_seasons.md) (5 of 5
on frem-2030-06-22), and frem-2030-06-22's four entries are the four above. No screen yet.

## Output

`output/<label>/club_titles.json`: `[{cid, club_tid, years}]`. Not loaded yet.

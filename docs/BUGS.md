# Known bugs / follow-ups

## 13. Tagged competition metadata region (~13-20MB) — self-describing format

The save has a **self-describing tagged section** (~13-20MB) holding competitions,
finances, staff, history, fixtures metadata. Format: `[tag:4 bytes, stored REVERSED]
[0x01][typecode:1][value]`. Typecodes seen: 0x11 = 1-byte value, 0x0a/0x0b = u32.
Field tags (read reversed) include: `comp`, `level` (league tier!), `Group`, `cash`/
`przm` (prize money, NOT club cash), `valu`, `curr`, `year`/`mont`/`stdt`/`endt`/`date`,
`type`, `id`, `DBID`, `team`, `info`, `stag`. This is the source for league LEVEL/tier
(cross-league comparison) and competition setup. Bulk data (players/attributes/matches)
is NOT here — those stay in the packed structures. Parsed by `fmparser/tables/rule_files.py`.

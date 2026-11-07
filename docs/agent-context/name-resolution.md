---
name: name-resolution
description: "Two match-side naming traps: anonymous reserve-league filler tids have no name, and a match row's name must be resolved by person_id. The name chain itself is docs/parser/names.md"
metadata:
  node_type: memory
  type: reference
---

How a name id becomes text is [`docs/parser/names.md`](../parser/names.md). This note keeps
two traps on the match side.

## A tid you CANNOT name is probably not a person (2026-09)

Reported as "some player names not coming through — I presume they have retired". They had not.
Every real player we ever fielded IS nameable, including retirees and departures, because he sat
in some snapshot's `players` table while he was around and `mart.player_snapshots` spans every
snapshot. So an unnameable tid means something else entirely.

On Frem's store all 49 of them came from one band (33007–33106) and all of them from **reserve**
fixtures. Three facts settle what they are:

* not one of them appears in **any** club's squad in **any** snapshot (the real reserve squad at
  tid 7296 is 35 players with tids 701–32160);
* the **same** tid turns out for up to nine different reserve clubs in a single season
  (33052 played for 7296, 7284, 7297, 7277, 7309, 7318, 7320, 9805 and 7294) — no person does
  that;
* their stat blocks are otherwise well-formed: real ratings, real minutes, real positions.

So the save simulates the reserve league with **anonymous filler**, and the tid in those stat
blocks is a per-match roster slot, not a player id. There is no name to find; do not go looking
for one, and do not widen the name chain above to try.

They are also not harmless. `mart.our_clubs` includes the reserve club, so they rode into
`matches.json` and put "#33015" second in the site's all-time average-rating table, ahead of most
of the first team. `scripts/export_data.py` now drops match rows whose tid cannot be named, which
is exactly this set — a real player's reserve appearances are named and unaffected.

## Resolve a match row's name by person_id, never by tid alone (2026-09)

Found while verifying the export above. `matches.json`'s `player_names` was built with
`SELECT tid, ANY_VALUE(name) ... FROM mart.player_snapshots GROUP BY tid`. A tid is a recycled
slot ([`person_info`](../parser/person_info.md)), so that group sweeps in the snapshots where the slot belonged to
somebody else entirely, and `ANY_VALUE` then picked between the two people by scan order.

**7 of our 74 named players came back under a stranger's name — and a different stranger on the
next export.** tid 4240 alternated between Johan Nordberg (ours) and Thomas De Clercq; 20597
between Jean Pierre Graabæk and Raúl Tirilonte. The History page was quietly attributing a Frem
career to a man who never played for us, and the value was not even stable run to run.

The match row already carries the answer: `mart.match_player_facts.person_id`. Key the name
lookup on that and the era ambiguity never arises. Two things make it safe:

* no tid serves two different people among our own appearances, so one name per tid is still
  well defined and the site's tid-keyed map does not need reshaping;
* `person_id` is a **string** `'<tid>-<dob>'`, not an integer — casting it with `int()` raises.

Pick the winner with an explicit `ROW_NUMBER() ... ORDER BY phase_date DESC, tid DESC, name`
rather than `ANY_VALUE`: one person_id does carry two spellings, and an unordered pick there is
the same non-determinism one level down.

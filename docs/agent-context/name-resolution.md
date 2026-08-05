---
name: name-resolution
description: "SOLVED — resolve any player's name (incl. non-managed) from first_name_id/last_name_id via the browse table + id-index tables"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**SOLVED 2026-08 (denmark-start.fms).** Every player's name — INCLUDING non-managed clubs — is
resolvable from the info field's name ids. Validated 10/10 managed squad + Diyar Ali (Dalum, tid
26862) + full Dalum/Herlev squads → clean Danish names. (Inline names @~58M are managed-club ONLY;
the id link avoids duplicating the name strings for everyone else — user's insight.)

**The resolution chain (three structures):**
1. **Browse table** (offset 299 .. ~515797, section 1): a flat `[len u32][utf-8]` list, ~45,942
   entries, nation-grouped (NOT id-order). Walk it once → `browse[ordinal] = string`.
2. **Two id-index tables** (in the big binary section ~37M), each **16 bytes/record**, **dense &
   sorted by id from 0**: record = `[browse_ordinal u32][id u32][~const u32][flags u32]` (id at +4
   self-verifies). `+0` is the ordinal into the browse table.
   - **Surname table** @ 37.109M (den) — 28,624 entries (id 0..28623). `last_name_id` indexes this.
   - **First-name table** @ 37.624M (den) — 15,366 entries (id 0..15365). `first_name_id` indexes this.
   - Layout: surname table first (lower offset, larger), then first-name table. Bases are per-save
     (offsets differ Frem vs Buca) and NOT 4-byte aligned to the file — discover, don't hardcode.
3. **Info field** (`reference.parse_info`): `first_name_id`=u32(+8), `last_name_id`=u32(+12).

**resolve(tid):** `first = browse[ id_first[first_name_id].ordinal ]`,
`last = browse[ id_sur[last_name_id].ordinal ]`, full name = `f"{first} {last}"`.
Anchors used this save: BASE_SUR = 37243546 − 8389*16 = 37109322; BASE_FIRST = 37698950 − 4703*16 =
37623702 (Grønne last_id 8389 → ord 21114; Rasmus first_id 4703 → ord 40712).

**Why it was hard / how the boundary map helped:** the id has NO positional relationship to the
browse table (adjacent entries Andersen id1450 / Sørensen id160), and there's no offset-index array —
so id→string needs these separate id-index tables, which sit mid-file inside the big binary section
(not adjacent to the names). Found via searching the whole file for the `[ordinal][id]` u32 pair.

**SHIPPED (2026-08).** `reference.build_name_resolver(mm, validate=…)` auto-discovers the browse table
(`_walk_browse`) + both id-index tables (`_discover_id_tables`, anchors on id=8192, walks the dense
run back to base). Orientation: larger table = surnames, then a self-check against the managed squad's
snapshot names flips it if needed (WATCH: swap only if the alternative scores *higher* — the naive
condition is inverted). `reference.resolve_name(mm, first_id, last_id)` → "First Last" (cached per
mmap). `extract.build_database` builds the resolver validated on `own_names`, then
`full_name(tid,p) = own_names.get(tid) or resolve_name(...)` for every player + staff row. **Result:
denmark-start → 24,315/24,315 named (100%); Frem squad 23→29 (reserves Wedege/Fugl/Balslev now appear
— that was the "mislabel"); Diyar Ali + all division opponents named; Bucaspor ground-truth still
passes.** Resolve from the SCRAPED per-record name ids (staging.scrape_players already reads
first/last_name_id), NOT `parse_info(tid)` — the by-tid search collides on low tids (returned wrong
players in a proto). Bonus not yet used: the inline snapshot record (@~58M, managed only) also carries
club + league as text. See [[savefile-boundary-map]], [[player-history-table]], [[etl-duckdb-dashboard]].

# Handoff — continue exactly where we are

Paste-ready context for a fresh agent to pick up the current effort.

---

I'm reverse-engineering an FMM22 (Football Manager Mobile 2022) save at
`/Users/zachooper/Documents/Personal/Projects/fm-parser`. It's a git repo; read-only
analysis (never write to the `.fms` saves). Three saves present (gitignored):
`21-22-mid.fms`, `21-22-end.fms` (my default working save), `22-23-start.fms`. Python 3,
memory-map based (no matplotlib — system Python blocks pip).

**First, read these to get full context (do this before anything else):**
- `docs/DATADICT.md` — the tagged data-dictionary format spec + entity catalogue (this is the current focus)
- `docs/BUGS.md` — all findings/leads, especially #12b/#12c (results/light-results) and #13 (tagged region)
- `docs/IDS.md` — every ID type and known club/comp ground-truth (Galatasaray 955, Fenerbahçe 954, Liverpool 356, Bucaspor 6567, comp 228 uid 463485, etc.)
- `README.md` and skim `fmparser/` (save, staging, attributes, matches, reference, results, tagged, model) + `extract.py`
- Recent git log (last ~8 commits) — the whole journey is there.

**Where we are:** Working extraction of matches + whole-DB player attributes is DONE and
committed (`extract.py` → `output/<label>/`). Current effort: cross-league skill
baselines, which needs **club→league membership + league level/tier**. I confirmed the
top leagues (e.g. Turkish Super League) ARE simulated but only my managed club's games
are detailed; all others store *light results*. That byte-level path is documented but
messy (BUGS #12c). The better path — and current focus — is the **tagged data dictionary
at ~17.0–20.8 MB**, whose format is now FULLY CRACKED.

**The tagged format (in `fmparser/tagged.py`, working):** `[tag: 4 bytes stored
REVERSED][0x01][type][value]`; type→size table done (`01/0a/0b/13`=u32, `02`=4-byte
entity-ref, `03/11`=u8, `12`=u16, `14`=u64); records NEST under `id`(type 0x02) headers;
`<tag> t0a <n>` + `id t02 <tag>` opens an n-field child; tagless `[01][type][value]`
positional fields exist. `parse_field(mm,p)` recursively parses; `iter_records(mm,
entity)` yields every fully-parsed record of an entity type (validated: 6926 `comp`,
889 `sdfd`).

**Key correction from last session:** `sdfd` is competition season/stage records (comp
ref + date ranges), NOT standings; `posn`+`cash` = prize money per position. **club→league
MEMBERSHIP is NOT yet located** — the `team` fields in these entities are nesting-count
bytes (0/677 were real club TIDs).

**Exact next steps (from docs/DATADICT.md):**
1. Use `iter_records(mm, 'comp')` to parse competition records → extract league
   **level/tier (`levl`)** and num-teams (`ntms`), keyed by comp uid; map comp uid ↔ our
   cid via `reference.comp_detail` (cid 228 → uid 463485 works). This alone enables
   cross-league *ranking*.
2. Hunt the team↔comp membership link by parsing candidate entities with `iter_records`:
   **`Ttea`/`team`** (teams-in-comp), **`nssn`/`nmsn`** (season squads),
   **`rgdv`/`lsdv`/`lwdv`** (division setup). Look for one that pairs a comp with real
   club TIDs (validate against known clubs: Bucaspor 6567 should map to comp 228;
   Galatasaray 955 to the Super League).
3. Once membership is found, build a leagues table (name+level+members) and stamp
   `club→league` on every player in `extract.py`, then compute per-league skill baselines
   (mean/range per attribute) — the end goal is "my team ≈ England L2 level / my aerial
   beats my league and the next".

Please continue from step 1. Work methodically, validate against ground-truth
clubs/comps, keep `python3 tests/test_ground_truth.py` passing, and commit as you go.
Ask me for in-game screenshots if you need ground truth (I can provide league tables,
fixtures, etc.).

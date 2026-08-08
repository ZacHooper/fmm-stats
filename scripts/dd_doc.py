#!/usr/bin/env python3
"""
(Re)build the AUTO-GENERATED tables in docs/DATADICT.md from docs/dd_inventory.json.

    python3 scripts/dd_enum.py <save.fms>   # first: refresh the inventory JSON
    python3 scripts/dd_doc.py               # then: rewrite the tables

Everything ABOVE the AUTO-GENERATED marker line in docs/DATADICT.md (the prose, the
requirements map, the plan) is preserved; only the tables below are replaced. Curated
meanings live in KNOWN below — add a decoded key, re-run, commit.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "DATADICT.md")
MARKER = "<!-- AUTO-GENERATED TABLES below"

# curated meanings — extend as keys get decoded (Phase 1+)
KNOWN = {
 "id": "entity id (u32; ~2e9 = internal entity id, the 'hop' vs club tid)",
 "comp": "competition (ref/id or local index)", "year": "year", "type": "record/comp type code",
 "ntms": "number of teams", "nmmt": "?num matches?", "stgn": "stage number", "stag": "stage index",
 "stnm": "stage entity", "team": "team slot/ref", "Ttea": "team-in-competition entity (2e9 id)",
 "rank": "rank/position?", "levl": "level (division tier)", "przm": "prize money", "cash": "cash",
 "valu": "value", "DBID": "database id", "mnsn": "season?", "nmsn": "season name/num?",
 "sbsn": "sub-season?", "date": "date entity", "stdt": "start date", "endt": "end date",
 "sdfd": "start-date field?", "edfd": "end-date field?", "fxds": "fixtures entity",
 "nwdt": "?date", "drdt": "draw date?", "time": "time", "dyom": "day of month", "mont": "month",
 "dyow": "day of week", "nati": "nation", "curr": "currency", "crk": "current rank? (in wrnk/lrnk)",
 "wrnk": "world/reputation rank (crk/lwrk/hgrk)", "lrnk": "league rank/standings? (crk/team/stag)",
 "lwrk": "lowest rank", "hgrk": "highest rank", "seed": "seeding", "sed1": "seed 1?",
 "dat2": "date entity 2", "nmlg": "num legs", "srnd": "seeded round/draw?",
 # --- Phase 1 (R1 standings) decode, 2026-08 ---
 "lrnk": "STANDINGS atom: one team's rank in a stage (crk + team-slot + stnm + ntms)",
 "crk": "CURRENT RANK = league position (observed 1..11)",
 "hgrk": "highest rank reached this season", "lwrk": "lowest rank reached this season",
 "nrdw": "?wins-related (candidate W)", "nrdl": "?losses-related (candidate L)",
 "ftac": "?(lrnk flag)", "rkli": "?rank-list size?", "seed": "seeding", "sed1": "seed 1?",
 "team": "team SLOT index within a stage (0..ntms-1), NOT a club tid",
 "stnm": "stage entity (ref)", "stgn": "stage number", "stag": "stage index",
 "Ttea": "team-in-competition INTERNAL entity id (~2e9) — needs id->club hop (Phase 2)",
 "DBID": "database id (~2e9 internal, not a club tid)",
 "enyr": "end year (squad-rules season)", "MnAg": "min squad age", "MxAg": "max squad age",
 "mxnp": "max non-protected players?", "ygap": "?year gap", "plty": "?penalty/type",
 # --- season-build CONFIG decode, 2026-08 (datadict = format engine: promo/releg/splits/rounds/scheduling) ---
 "nssn": "season/stage STRUCTURE incl split-group + embedded team-slot rank snapshot",
 "topp": "top places promoted / qualifying", "btpl": "bottom places relegated",
 "btpr": "bottom places (relegation) variant", "prmr": "promotion-related", "relr": "relegation-related",
 "pspl": "split?", "spld": "split?", "nrds": "number of rounds", "rnds": "rounds", "trnd": "total rounds?",
 "tems": "team count (in stage)", "qurl": "qualification rule?",
 "SCsn": "stage config (stgn, tems, lgto, stnm)", "srnd": "seeded round (subr/prio/drrl draw-rule/rnds)",
 "drrl": "draw rule", "prio": "seeding priority", "subr": "sub-round",
 "fxor": "fixture order", "tvty": "TV type", "tvmt": "TV channel/match", "ndow": "nominal day-of-week",
 "ntim": "nominal kickoff time (HHMM)", "bkdw": "block day-of-week", "stdw": "start day-of-week",
 "endw": "end day-of-week", "mtdy": "match day", "lgto": "?league config flag",
 "pare": "parent competition (comp ref)", "ncmp": "nested/child competition", "indx": "index",
}


def meaning(t):
    return KNOWN.get(t, "**TBD**")


def build_tables(d):
    LO, HI = d["region"]
    fields, records, entf = d["fields"], d["records"], d["ent_fields"]
    sig = sorted([(t, v) for t, v in fields.items() if v["count"] >= 15],
                 key=lambda x: -x[1]["count"])
    L = [MARKER + " (edit meanings in scripts/dd_doc.py KNOWN; re-gen replaces tables) -->", "",
         f"**Region ({d.get('save','?')}):** {LO/1e6:.3f}M–{HI/1e6:.3f}M &nbsp; "
         f"**distinct field tags:** {len(fields)} (listing {len(sig)} with ≥15 occurrences) &nbsp; "
         f"**entity types:** {len(records)}", "",
         "## Entity types (records)",
         "Ordered by record count. 'Child fields' = tags most often seen inside that record type.", "",
         "| entity | records | top child fields | meaning |", "|---|--:|---|---|"]
    for e, c in records.items():
        if c < 5:
            continue
        kids = ", ".join(list(entf.get(e, {}).keys())[:10])
        L.append(f"| `{e}` | {c} | {kids} | {meaning(e)} |")
    L += ["", "## Field keys",
          "`type` codes: 0x01/0x0a/0x0b/0x13=u32, 0x11=u16, 0x03=u8, 0x02=entity-ref (reversed tag).", "",
          "| key | count | type(s) | int range / ent-refs | samples | meaning |",
          "|---|--:|---|---|---|---|"]
    for t, v in sig:
        types = ",".join(v["types"].keys())
        if v["ent_refs"]:
            rng = "refs: " + ", ".join(f"{k}×{n}" for k, n in list(v["ent_refs"].items())[:4])
        elif v["int_range"][0] is not None:
            rng = f"{v['int_range'][0]}..{v['int_range'][1]}"
        else:
            rng = ""
        samp = ", ".join(str(x) for x in v["samples"][:5]).replace("|", "\\|")[:60]
        L.append(f"| `{t}` | {v['count']} | {types} | {rng} | {samp} | {meaning(t)} |")
    return "\n".join(L) + "\n"


def main():
    d = json.load(open(os.path.join(ROOT, "docs", "dd_inventory.json")))
    tables = build_tables(d)
    if os.path.exists(DOC):
        head = open(DOC).read().split(MARKER)[0].rstrip() + "\n\n"
    else:
        head = "# FMM22 save — TAGGED data-dictionary reference\n\n"
    open(DOC, "w").write(head + tables)
    print(f"wrote {DOC}")


if __name__ == "__main__":
    main()

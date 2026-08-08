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
 # --- systematic field map from scripts/dd_anatomy.py profiles, 2026-08 ---
 # dates / calendar
 "dyow": "day of week (1..7)", "dyom": "day of month (1..31)", "mont": "month (1..12)",
 "year": "year", "time": "time of day (HHMM)", "ntim": "nominal kickoff time (HHMM)",
 "TiTu": "TV kickoff time slot (HHMM)", "stmn": "start month", "enmn": "end month",
 "stdm": "start day-of-month", "endm": "end day-of-month", "ftye": "?fixture-type month?",
 "styr": "start year", "enyr": "end year", "bsyr": "base/season year", "styo": "start-year flag?",
 "enyo": "end-year flag?", "aldt": "?date-related (0..8)",
 # counts / structure
 "ntms": "number of teams", "mntm": "max teams? (0..96)", "mxtm": "max teams", "Bktm": "bracket teams",
 "tems": "team count (stage)", "levl": "league level/tier (0..27)", "nmmt": "number of matches",
 "nrds": "number of rounds", "stgs": "number of stages", "stgn": "stage number", "stag": "stage index/ref",
 "subr": "sub-round", "prio": "priority (seeding)", "seed": "seeding", "posn": "finishing position (for prize)",
 "indx": "index", "gpid": "group id", "strq": "?stage-seq", "semt": "?", "chcl": "?", "sbty": "?subs type?",
 "vers": "version", "strl": "?level/rung (1..16)", "SrTs": "?", "tfxt": "?fixture text/type", "ofsd": "?",
 # ranks / standings snapshot
 "crk": "current rank / league position", "lwrk": "season-lowest rank", "hgrk": "season-highest rank",
 "team": "team SLOT index within a stage (0..ntms-1)", "ftac": "?(rank flag)",
 # money
 "przm": "prize money (amount, by posn)", "cash": "cash amount", "valu": "value", "curr": "currency (ref)",
 "wnpz": "winner prize", "lspz": "?prize", "apmn": "?appearance money",
 # TV / scheduling
 "tvty": "TV type", "tvmt": "TV channel/match", "ndow": "nominal day-of-week", "sche": "scheduled flag",
 "fxri": "?fixture rule index", "mtdy": "match day",
 # ids / refs / flags
 "DBID": "database id (entity uid, 2e9 band for created)", "id_1": "secondary entity id/ref",
 "id_2": "secondary entity id/ref", "igmt": "bool flag", "nxss": "bool flag", "umox": "bool flag",
 "cnic": "bool flag", "bsyo": "bool flag", "bsyi": "bool flag", "inac": "inactive flag", "rmic": "bool flag",
 "Bran": "?brand/entity ref (~1435)", "XSvC": "?", "dcin": "?", "hidl": "?", "cmty": "?commentary?",
 "ygap": "?year gap", "plty": "?playoff/penalty type", "sqsr": "?squad-season ref", "in_1": "?", "in_2": "?",
 # --- pass 2: confidently-pinned long-tail keys (2026-08) ---
 "Nnat": "nation id (110..141, nation-space)", "natl": "?nation level/flag",
 "sed1": "seed 1", "sed2": "seed 2", "sort": "sort order", "ptsd": "?points config (0..6)",
 "nmxt": "num next / matches-to-play", "nrpl": "?num replays", "dyof": "day offset",
 "info": "generic info/count value", "dats": "date value (day-of-month-ish)", "sequ": "sequence no.",
 "idwi": "index", "ind1": "index", "ctin": "?counter/index", "decd": "?decided flag/count",
 # boolean flags (value set {0,1})
 "srcc": "bool flag", "pref": "bool flag", "nmrp": "bool flag", "tcpf": "bool flag",
 "usqn": "bool flag", "ilgf": "bool flag", "iEsT": "bool flag", "gmsb": "?(1/2) flag",
 # --- pass 3: date/finance/fixture entities + their fields (2026-08) ---
 "sdfd": "stage finance/date record: prize (cash) by finishing posn + stage dates",
 "stdt": "stage START date (dyom/mont/year/dyow) + TV scheduling + prize",
 "endt": "stage END date + season-boundary flags (snst/snen) + winner info",
 "fxds": "fixture-set config (season, num matches, groups, seeding, team slots)",
 "przm": "prize money by level/position (levl + cash/przm amount)",
 "sbsn": "sub-season index", "posn": "finishing position (prize / table row)",
 "nrpl": "number of replays (0..6)", "gpid": "group id (0..15)",
 "Cfdf": "constant field (=16)", "semt": "?stage-element type (0..7)",
 "snst": "season-start flag", "snen": "season-end flag", "snrd": "?season-round flag",
 "Ufss": "?season flag", "wnty": "?winner type/round", "wnCT": "?winner-decided value",
 "hdty": "?head-to-head/seeding type", "mtdr": "?match-day rule", "idwi": "index",
 "rank": "rank / seed value", "d2lA": "?small enum (23..74)", "wndl": "?", "wnrd": "?winner round",
 "tvds": "?TV days/count", "lsdi": "?last-stage index", "fsdi": "?first-stage index",
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

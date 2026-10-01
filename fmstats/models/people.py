"""Players and people: our squad's exact values, the attribute decode, the person bridge.

  int.squad_scrapbook          every player in our squad arrays with his latest entry in the
                               Manager's Best Eleven lists
  int.person_names             each person's display name: common name, else first + last
  int.players                  each person's own record, with our squad's values in place
  int.player_attributes_exact  the attributes the save states, our squad's from the entry
  int.player_attributes        all 23 attributes: stated where the save states them, decoded
                               from the record's bytes and raw.attribute_model otherwise
  int.person_slices            (season, phase, tid) -> person_id
  int.persons                  one row per person: person_id = '<tid>-<dob>'
"""
from .. import contract as C
from . import Model

# How old a squad player's scrapbook entry may be and still stand in for his entangled
# attributes, value and feet. Measured against entries at most a month old on every save of
# both careers: an entry up to a year old matches on 76-97% of the 23 attributes, the
# estimate on 71%; past two years the estimate is as good.
SCRAPBOOK_MAX_AGE_DAYS = 365

_HAS = "k.scrapbook_date IS NOT NULL"
_FRESH = (f"({_HAS} AND TRY_CAST(k.phase AS DATE) - k.scrapbook_date"
          f" <= {SCRAPBOOK_MAX_AGE_DAYS})")


def _cols(con, table):
    schema, name = table.split(".")
    return [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = ? "
        "AND table_name = ? ORDER BY ordinal_position", [schema, name]).fetchall()]


def _squad_scrapbook(con):
    entry_cols = ", ".join(f'k."{c}"' for c in _cols(con, "raw.player_scrapbook")
                           if c not in ("season", "phase", "player_tid"))
    lo, hi = C.CLUB_LISTS.start, C.CLUB_LISTS.stop - 1
    return f"""
WITH managed AS (
    SELECT CAST(value AS INTEGER) AS club_tid FROM raw.app_config
    WHERE key = 'career_managed_tid'
),
ours AS (
    SELECT e.season, e.phase, m.club_tid, 0 AS reserve
    FROM raw.extracts e CROSS JOIN managed m
    UNION ALL
    SELECT d.season, d.phase, d.tid, 1
    FROM raw.club_details d JOIN managed m ON d.main_club_tid = m.club_tid
),
squad AS (
    SELECT q.season, q.phase, q.player_tid AS tid,
           arg_min(q.club_tid, o.reserve) AS squad_club_tid
    FROM raw.club_squad q JOIN ours o USING (season, phase, club_tid)
    GROUP BY q.season, q.phase, q.player_tid
),
latest AS (
    SELECT * FROM raw.player_scrapbook
    WHERE list BETWEEN {lo} AND {hi}
    QUALIFY row_number() OVER (PARTITION BY season, phase, player_tid
                               ORDER BY scrapbook_date DESC, list DESC) = 1
)
SELECT q.season, q.phase, q.tid, q.squad_club_tid, c.name AS squad_club,
       r.club_tid NOT IN (SELECT o.club_tid FROM ours o
                          WHERE o.season = q.season AND o.phase = q.phase) AS loaned_in,
       r.club_tid AS own_club_tid, r.club AS own_club,
       {entry_cols}
FROM squad q
JOIN raw.players_raw r ON r.season = q.season AND r.phase = q.phase AND r.tid = q.tid
LEFT JOIN raw.clubs c ON c.season = q.season AND c.phase = q.phase AND c.tid = q.squad_club_tid
LEFT JOIN latest k ON k.season = q.season AND k.phase = q.phase AND k.player_tid = q.tid"""


# int.person_names. The common name is the one the game displays when a person has one, and is
# often not a shortening of the legal name at all ('Tite' for Adenor Leonardo Bachi), so it
# comes first; otherwise first + last, and NULL when either is missing. A store loaded before
# extract handed over the name ids keeps the resolved name in raw.players_raw.name; it stands in
# for a snapshot with no ids.
NAME_ID_COLS = ("first_name_id", "last_name_id", "common_name_id")


def _person_names(con):
    legacy = ", r.name" if "name" in _cols(con, "raw.players_raw") else ""

    def tab(alias, table, col):
        return (f"LEFT JOIN stg.name_ids {alias}i ON {alias}i.season = r.season"
                f" AND {alias}i.phase = r.phase AND {alias}i.name_table = '{table}'"
                f" AND {alias}i.id = r.{col}\n"
                f"LEFT JOIN stg.name_strings {alias} ON {alias}.season = r.season"
                f" AND {alias}.phase = r.phase AND {alias}.ordinal = {alias}i.ordinal")
    return f"""
SELECT r.season, r.phase, r.tid, r.first_name_id, r.last_name_id, r.common_name_id,
       f.name AS first_name, l.name AS last_name, c.name AS common_name,
       COALESCE(c.name, f.name || ' ' || l.name{legacy}) AS name
FROM raw.players_raw r
{tab("f", "first_names", "first_name_id")}
{tab("l", "surnames", "last_name_id")}
{tab("c", "nicknames", "common_name_id")}"""


# int.players: a column of raw.players_raw is replaced where our squad's entry says otherwise;
# the player's squad status follows has_attributes, and the squad-entry columns and his current
# contract follow foot_right. Staff carry neither a squad status nor a contract. (The staff test
# sits in the columns, not in the joins' ON: a condition on the left table there turns DuckDB's
# hash join into a nested loop, 0.02 s -> 36 s.)
_OVER = {
    "name": f"CASE WHEN {_HAS} THEN k.full_name ELSE n.name END",
    "club_tid": "CASE WHEN k.loaned_in THEN k.squad_club_tid ELSE r.club_tid END",
    "club": "CASE WHEN k.loaned_in THEN k.squad_club ELSE r.club END",
    "foot_left": f"CASE WHEN {_FRESH} THEN k.foot_left ELSE r.foot_left END",
    "foot_right": f"CASE WHEN {_FRESH} THEN k.foot_right ELSE r.foot_right END",
}
_ADDED_AFTER = {
    "has_attributes": [
        ("squad_status", "CASE WHEN NOT r.is_staff THEN t.squad_status END")],
    "foot_right": [
        ("player_value", f"CASE WHEN {_FRESH} THEN k.value END"),
        ("loaned_in", "COALESCE(k.loaned_in, FALSE)"),
        ("parent_club_tid", "CASE WHEN k.loaned_in THEN k.own_club_tid END"),
        ("parent_club", "CASE WHEN k.loaned_in THEN k.own_club END"),
        ("wage_units", "CASE WHEN NOT r.is_staff THEN c.wage_units END"),
        ("wage_gbp", f"CASE WHEN NOT r.is_staff THEN "
                     f"CAST(c.wage_units AS BIGINT) * {C.WAGE_GBP_PER_UNIT} END"),
        ("contract_expiry", "CASE WHEN NOT r.is_staff THEN c.expiry END"),
        ("contract_expiry_year",
         "CASE WHEN NOT r.is_staff THEN CAST(year(c.expiry) AS INTEGER) END")]}


def _players(con):
    sel = []
    cols = _cols(con, "raw.players_raw")
    for c in cols:
        if c in NAME_ID_COLS:          # int.person_names carries them
            continue
        sel.append(f'{_OVER[c]} AS "{c}"' if c in _OVER else f'r."{c}"')
        sel += [f'{e} AS "{n}"' for n, e in _ADDED_AFTER.get(c, [])]
        if c == "tid" and "name" not in cols:
            sel.append(f'{_OVER["name"]} AS "name"')
    sel.append(f'CASE WHEN {_FRESH} THEN k.scrapbook_date END AS "scrapbook_date"')
    return ("SELECT " + ",\n       ".join(sel)
            + "\nFROM raw.players_raw r\nLEFT JOIN int.squad_scrapbook k"
            " ON k.season = r.season AND k.phase = r.phase AND k.tid = r.tid"
            "\nLEFT JOIN int.person_names n ON n.season = r.season AND n.phase = r.phase"
            " AND n.tid = r.tid"
            "\nLEFT JOIN stg.training t ON t.season = r.season AND t.phase = r.phase"
            " AND t.tid = r.tid"
            "\nLEFT JOIN stg.contracts c ON c.season = r.season AND c.phase = r.phase"
            " AND c.tid = r.tid AND c.is_current")


def _player_attributes_exact(con):
    attrs = ",\n       ".join(
        f'e."{a}"' if a in C.EXACT_SINGLE
        else f'CASE WHEN {_FRESH} THEN k."{a}" ELSE e."{a}" END AS "{a}"'
        for a in C.ATTR_ORDER)
    return (f"SELECT e.season, e.phase, e.tid,\n       {attrs}\n"
            "FROM raw.player_attributes_exact_raw e\nLEFT JOIN int.squad_scrapbook k"
            " ON k.season = e.season AND k.phase = e.phase AND k.tid = e.tid")


# --- the attribute decode -------------------------------------------------------------------
# Feature expressions, in the model's own vocabulary. `own`/`partner` are the wrapped 0-255
# source bytes; everything else is read straight off the stored record.
_UW = "(CASE WHEN {c} < 128 THEN {c} + 256 ELSE {c} END)"
_MEAN9 = ("((p.heading_src + p.unselfishness_src + p.pace_src + p.strength_src + p.stamina_src"
          " + p.technique_src + p.aggression_src + p.leadership_src + p.agility_src) / 9.0)")
_POS_RANK = " ".join(f"WHEN '{p}' THEN {i}" for i, p in enumerate(C.POSITIONS))
# fwd: attacking-ness of the player's best position; a tie goes to the position the record
# lists first (contract.POSITIONS), so a player equally good at DC and ST resolves to DC.
_FWD = """(SELECT CASE WHEN t.position IN ('ST','AML','AMR','AMC') THEN 1.0
                       WHEN t.position IN ('ML','MR','MC','DMC','DML','DMR') THEN 0.5
                       ELSE 0.0 END
            FROM raw.player_positions t
           WHERE (t.season, t.phase, t.tid) = (p.season, p.phase, p.tid)
           ORDER BY t.familiarity DESC, (CASE t.position """ + _POS_RANK + """ END)
           LIMIT 1)"""


def _d(c):
    """A coefficient as an explicit DOUBLE. Written bare, DuckDB reads a 16-digit literal as
    DECIMAL(18) and the first multiplication by a byte value overflows."""
    return f"CAST({c!r} AS DOUBLE)"


def _composite_sql(b1, b2, w):
    """floor(w1*b1 + w2*b2 + off), clipped 1-20."""
    wa, wb, off = w
    return (f"GREATEST(1, LEAST(20, CAST(floor({_d(wa)} * p.{b1} + {_d(wb)} * p.{b2}"
            f" + {_d(off)}) AS INTEGER)))")


def _model_expr(spec):
    """SQL for one attribute's fitted value, from its coefficient rows."""
    cols = {**C.SRC_OFFSETS, **C.PLAIN_OFFSETS, **C.HIDDEN_OFFSETS}
    own = _UW.format(c=f'p."{cols[spec["own"]]}"')
    parts = []
    for feat, c in spec["coef"].items():
        if feat == "own":
            e = own
        elif feat == "partner":
            e = _UW.format(c=f'p."{cols[spec["partner"]]}"')
        elif feat == "CA":
            e = "p.ca"
        elif feat == "PA":
            e = "p.pa"
        elif feat == "mean9":
            e = _MEAN9
        elif feat == "own*CA":
            e = f"({own} * p.ca / 100.0)"
        elif feat == "fwd":
            e = _FWD
        elif feat in C.HIDDEN_OFFSETS.values():
            e = f'p."{feat}"'
        elif feat.startswith("NAT_") and feat[4:] in C.POSITIONS:
            e = (f"CASE WHEN COALESCE((SELECT t.familiarity FROM raw.player_positions t "
                 f"WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid) "
                 f"AND t.position = '{feat[4:]}'), 0) >= 20 THEN 1.0 ELSE 0.0 END")
        elif feat in C.POSITIONS:
            e = (f"COALESCE((SELECT t.familiarity FROM raw.player_positions t "
                 f"WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid) "
                 f"AND t.position = '{feat}'), 0)")
        elif feat == "intercept":
            parts.append(_d(c))
            continue
        else:
            raise ValueError(f"unknown model feature {feat!r}")
        parts.append(f"({_d(c)} * {e})")
    return f"GREATEST(1, LEAST(20, CAST(round({' + '.join(parts)}) AS INTEGER)))"


def _player_attributes(con):
    spec = {}
    for attr, feat, coef, own, partner in con.execute(
            "SELECT attribute, feature, coef, own_offset, partner_offset "
            "FROM raw.attribute_model").fetchall():
        d = spec.setdefault(attr, {"own": own, "partner": partner, "coef": {}})
        d["coef"][feat] = coef
    sel = []
    for a in C.ATTR_ORDER:
        if a in C.COMPOSITES:
            # Closed forms over two plain 1-20 bytes, no model. Teamwork's is exact, so its
            # `_est` is FALSE; Aerial's matches about 71% of the time, so it is an estimate.
            (b1, b2), w, est = C.COMPOSITES[a]
            sel.append(f'COALESCE(e."{a}", {_composite_sql(b1, b2, w)}) AS "{a}"')
            sel.append(f'(e."{a}" IS NULL) AS "{a}_est"' if est else f'FALSE AS "{a}_est"')
        elif a in spec:
            sel.append(f'COALESCE(e."{a}", {_model_expr(spec[a])}) AS "{a}"')
            sel.append(f'(e."{a}" IS NULL) AS "{a}_est"')
        else:
            sel.append(f'e."{a}" AS "{a}"')
            sel.append(f'FALSE AS "{a}_est"')
    return ("SELECT p.season, p.phase, p.tid,\n       " + ",\n       ".join(sel)
            + "\nFROM int.players p JOIN int.player_attributes_exact e"
            " USING (season, phase, tid)")


# --- the person bridge ----------------------------------------------------------------------
# The game hands a retired person's tid to a newgen, so tid alone splices two careers; (tid,
# dob) separates every recycled slot (docs/IDS.md). person_id is '<tid>-<dob>'.
_PERSON_ID = "concat(CAST(tid AS VARCHAR), '-', COALESCE(CAST(dob AS VARCHAR), '?'))"
# chronological order of a phase: dates sort as strings, legacy words as epoch
_PHASE_ORD = ("CASE phase WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01' "
              "WHEN 'end' THEN '0000-00-02' ELSE phase END")

MODELS = [
    Model("int.person_names", _person_names, grain=("season", "phase", "tid"),
          upstream=("stg.name_ids", "stg.name_strings"),
          doc="Each person's name ids and the strings they index; `name` is the display name: "
              "the common name when he has one, else first + last."),
    Model("int.squad_scrapbook", _squad_scrapbook, grain=("season", "phase", "tid"),
          doc="Every player in our first-team or reserve squad array on each snapshot, with "
              "his latest Manager's Best Eleven entry. A player whose own record names "
              "another club is on loan to us from it."),
    Model("int.players", _players, grain=("season", "phase", "tid"),
          upstream=("int.person_names", "int.squad_scrapbook", "stg.training",
                    "stg.contracts"),
          doc="Each person's own record, with his squad status and current contract; for our "
              "squad the name from the entry, and feet and value from it while it is at most "
              f"{SCRAPBOOK_MAX_AGE_DAYS} days old."),
    Model("int.player_attributes_exact", _player_attributes_exact,
          grain=("season", "phase", "tid"), upstream=("int.squad_scrapbook",),
          fks={"season, phase, tid": "int.players(season, phase, tid)"},
          doc="The attributes the save states outright; for our squad the 16 entangled ones "
              "from a fresh entry. NULL where the save does not state it."),
    Model("int.player_attributes", _player_attributes, grain=("season", "phase", "tid"),
          upstream=("int.players", "int.player_attributes_exact"),
          fks={"season, phase, tid": "int.players(season, phase, tid)"},
          doc="All 23 attributes, with an `_est` flag each: stated where the save states "
              "them, decoded from the record's bytes and raw.attribute_model otherwise."),
    Model("int.person_slices",
          f"SELECT season, phase, tid, {_PERSON_ID} AS person_id FROM int.players",
          grain=("season", "phase", "tid"), upstream=("int.players",),
          fks={"person_id": "int.persons(person_id)"},
          doc="(season, phase, tid) -> person_id, the join every fact table uses."),
    Model("int.persons", f"""
SELECT {_PERSON_ID} AS person_id, tid, dob,
       arg_max(name, {_PHASE_ORD}) AS name,
       arg_min(phase, {_PHASE_ORD}) AS first_seen,
       arg_max(phase, {_PHASE_ORD}) AS last_seen,
       COUNT(*) AS slices
FROM int.players GROUP BY tid, dob""",
          grain=("person_id",), upstream=("int.players",),
          doc="One row per person across every snapshot, so a retired player whose slot has "
              "gone to a newgen keeps his history."),
]

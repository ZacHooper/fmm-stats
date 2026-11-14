"""The attribute decoder's labelled rows: one per player per snapshot where the save states
his displayed attributes outright (our own squad, `int.player_attributes_exact`), with the
record bytes, ability and position familiarities the decoder reads (`stg.player_attributes`).

Each row is `(tid, ca, pa, *byte_cols, *attrs, *familiarities)`, familiarity 0 where the
player has none at that position. `fit_attribute_model.py` fits on these and
`holdout_score.py` scores on them.

`game` keeps only the snapshots of one save_format ('fmm22', 'fmm27'): each game has its own
coefficients. `distinct` collapses identical rows to one. A player who has not played since
his last scrapbook entry carries the same entry, bytes and CA into every snapshot, and on a
store of a few snapshots those repeats are half the rows.
"""


def exact_rows(con, byte_cols, attrs, positions, game=None, distinct=False):
    sql = f"""
        SELECT {'DISTINCT' if distinct else ''} p.tid, r.ca, r.pa,
               {', '.join(f'r."{c}"' for c in byte_cols)},
               {', '.join(f'e."{a}"' for a in attrs)},
               {', '.join(f'COALESCE(r.pos_{q.lower()}, 0)' for q in positions)}
        FROM stg.persons p
        JOIN stg.player_attributes r ON r.snapshot_date = p.snapshot_date AND r.sid = p.sid
        JOIN int.player_attributes_exact e
          ON e.snapshot_date = p.snapshot_date AND e.tid = p.tid
        JOIN stg.snapshots s ON s.snapshot_date = p.snapshot_date
        WHERE r.ca IS NOT NULL AND r.passing_src IS NOT NULL
          AND e."Passing" IS NOT NULL          -- every displayed attribute stated
          {"AND s.save_format = ?" if game else ""}
    """
    return con.execute(sql, [game] if game else []).fetchall()


def store_games(con):
    """The save_formats a store's snapshots come from."""
    return [g for (g,) in con.execute(
        "SELECT DISTINCT save_format FROM stg.snapshots ORDER BY 1").fetchall()]

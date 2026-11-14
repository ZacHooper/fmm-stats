"""The attribute decoder's labelled rows: one per scrapbook entry (`int.player_attribute_labels`
-- our club's lists and the World Best XI pools), whose 23 attributes are the screen's, paired
with the record bytes, ability and position familiarities the decoder reads
(`stg.player_attributes`) on the snapshot nearest the entry's date where the record still shows
that profile.

Each row is `(tid, ca, pa, *byte_cols, *attrs, *familiarities)`, familiarity 0 where the
player has none at that position. `fit_attribute_model.py` fits on these and
`holdout_score.py` scores on them.

`game` keeps only the snapshots of one save_format ('fmm22', 'fmm27'): each game has its own
coefficients. `our_club_only` keeps our club's entries alone.
"""


def exact_rows(con, byte_cols, attrs, positions, game=None, our_club_only=False):
    sql = f"""
        SELECT p.tid, r.ca, r.pa,
               {', '.join(f'r."{c}"' for c in byte_cols)},
               {', '.join(f'e."{a}"' for a in attrs)},
               {', '.join(f'COALESCE(r.pos_{q.lower()}, 0)' for q in positions)}
        FROM int.player_attribute_labels e
        JOIN stg.persons p ON p.snapshot_date = e.snapshot_date AND p.tid = e.tid
        JOIN stg.player_attributes r ON r.snapshot_date = p.snapshot_date AND r.sid = p.sid
        JOIN stg.snapshots s ON s.snapshot_date = p.snapshot_date
        WHERE r.ca IS NOT NULL AND r.passing_src IS NOT NULL
          {"AND s.save_format = ?" if game else ""}
          {"AND e.is_our_club" if our_club_only else ""}
        ORDER BY p.tid, e.entry_date
    """
    return con.execute(sql, [game] if game else []).fetchall()


def store_games(con):
    """The save_formats a store's snapshots come from."""
    return [g for (g,) in con.execute(
        "SELECT DISTINCT save_format FROM stg.snapshots ORDER BY 1").fetchall()]

"""The names consumers used before the stg/int models existed, as views over the models.

The models themselves are the dbt project in `transform/`; these views are created after it
has built them. Each goes when its last consumer reads the mart instead (data-layers plan,
step 17).
"""

# old name -> (the model it reads, its SELECT). The legacy models keep the old shapes on the
# (season, phase) key; the int models they read are keyed by snapshot_date.
VIEWS = {
    "raw.players": ("legacy.players", "SELECT * FROM legacy.players"),
    "raw.player_attributes_exact": ("legacy.player_attributes_exact",
                                    "SELECT * FROM legacy.player_attributes_exact"),
    "raw.player_attributes": ("legacy.player_attributes",
                              "SELECT * FROM legacy.player_attributes"),
    "raw.person_slices": ("legacy.person_slices", "SELECT * FROM legacy.person_slices"),
    "raw.persons": ("legacy.persons", "SELECT * FROM legacy.persons"),
    "raw.player_positions": ("legacy.player_positions",
                             "SELECT * FROM legacy.player_positions"),
    "raw.staff_attributes": ("legacy.staff_attributes",
                             "SELECT * FROM legacy.staff_attributes"),
    "main.v_player_attributes": ("legacy.player_attributes", """
        SELECT p.*, a.* EXCLUDE (season, phase, tid)
        FROM legacy.players p JOIN legacy.player_attributes a USING (season, phase, tid)"""),
    "main.v_player_ratings": ("legacy.player_ratings", "SELECT * FROM legacy.player_ratings"),
    "main.v_player_rating_ranks": ("legacy.player_rating_ranks",
                                   "SELECT * FROM legacy.player_rating_ranks"),
}


def _kind(con, name):
    """'BASE TABLE', 'VIEW' or None for `schema.table`."""
    schema, table = name.split(".")
    row = con.execute("SELECT table_type FROM information_schema.tables "
                      "WHERE table_schema = ? AND table_name = ?", [schema, table]).fetchone()
    return row[0] if row else None


def create(con):
    """Create every compatibility view whose model has been built. `CREATE OR REPLACE VIEW`
    cannot replace a table, and older stores hold some of these names as tables (raw.persons,
    raw.person_slices, raw.player_attributes, raw.player_positions, raw.staff_attributes), so a table of the name is dropped first.
    Returns the views created."""
    made = []
    for name, (model, sql) in VIEWS.items():
        if _kind(con, model) is None:
            continue
        if _kind(con, name) == "BASE TABLE":
            con.execute(f"DROP TABLE {name}")
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")
        made.append(name)
    return made

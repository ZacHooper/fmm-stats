"""The names consumers used before the stg/int models existed, as views over the models.

The models themselves are the dbt project in `transform/`; these views are created after it
has built them. Each goes when its last consumer reads the mart instead (data-layers plan,
step 17).
"""

# old name -> (the model it reads, its SELECT)
VIEWS = {
    "raw.squad_scrapbook": ("int.squad_scrapbook", "SELECT * FROM int.squad_scrapbook"),
    "raw.players": ("int.players", "SELECT * FROM int.players"),
    "raw.player_attributes_exact": ("int.player_attributes_exact",
                                    "SELECT * FROM int.player_attributes_exact"),
    "raw.player_attributes": ("int.player_attributes", "SELECT * FROM int.player_attributes"),
    "raw.person_slices": ("int.person_slices", "SELECT * FROM int.person_slices"),
    "raw.persons": ("int.persons", "SELECT * FROM int.persons"),
    "main.v_player_attributes": ("int.player_attributes", """
        SELECT p.*, a.* EXCLUDE (season, phase, tid)
        FROM int.players p JOIN int.player_attributes a USING (season, phase, tid)"""),
    "main.v_player_ratings": ("int.player_ratings", "SELECT * FROM int.player_ratings"),
    "main.v_player_rating_ranks": ("int.player_rating_ranks",
                                   "SELECT * FROM int.player_rating_ranks"),
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
    raw.person_slices, raw.player_attributes), so a table of the name is dropped first.
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

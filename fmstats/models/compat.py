"""The names consumers used before the models existed, as views over the models.

Each goes when its last consumer reads the mart instead (data-layers plan, step 17). A view
here is created only once the model it reads has been built.
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


def create(con, built):
    """Create the compatibility views whose model is in `built`. `CREATE OR REPLACE VIEW`
    cannot replace a table, and older stores hold some of these names as tables (raw.persons,
    raw.person_slices, raw.player_attributes), so a table of the name is dropped first."""
    from . import _kind
    for name, (model, sql) in VIEWS.items():
        if model in built:
            if _kind(con, name) == "BASE TABLE":
                con.execute(f"DROP TABLE {name}")
            con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")

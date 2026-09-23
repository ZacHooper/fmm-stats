"""The staging schema fmstats reads, as far as Python needs to spell it out.

fmstats depends on the store, not on the parser: everything it knows about a save arrives
through the `staging` tables the loader writes. Most of that contract is the tables
themselves; this module holds the part the mart's SQL is generated from.

`ATTR_ORDER` is the 23 displayed attributes, in the order the attribute columns of
`staging.player_attributes` carry them. `tests/test_boundary.py` checks it against
`fmparser.model.ATTR_ORDER`, the list the extract writes.
"""

ATTR_ORDER = [
    "Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
    "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
    "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
    "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing",
]

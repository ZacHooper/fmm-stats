"""The raw schema fmstats reads, as far as Python needs to spell it out.

fmstats depends on the store, not on the parser: everything it knows about a save arrives
through the `raw` tables the loader writes. Most of that contract is the tables
themselves; this module holds the part the mart's SQL is generated from.

`ATTR_ORDER` is the 23 displayed attributes, in the order the attribute columns of
`raw.player_attributes` carry them. `tests/test_boundary.py` checks it against
`fmparser.model.ATTR_ORDER`, the list the extract writes.
"""

ATTR_ORDER = [
    "Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
    "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
    "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
    "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing",
]

# The attributes the player record states outright (each one byte); every other displayed
# attribute is derived. `fmparser.model.EXACT_SINGLE` maps them to their record offsets.
EXACT_SINGLE = ("Pace", "Strength", "Stamina", "Technique", "Aggression", "Leadership",
                "Agility")

# The player record's attribute bytes as `raw.players` names them, by offset from the record's
# anchor: the entangled 0-255 sources, the plain 1-20 sources and the hidden attributes
# (`fmparser.tables.player_attributes.SRC_OFFSETS` / `PLAIN_OFFSETS` / `HIDDEN_OFFSETS`).
SRC_OFFSETS = {
    -34: "crossing_src", -33: "dribbling_src", -32: "tackling_src",
    -31: "finishing_src", -30: "long_shot_src", -27: "passing_src",
    -26: "decision_src", -12: "creativity_src", -11: "movement_src",
    -10: "positioning_src", -7: "handling_src", -6: "kicking_src",
    -4: "aerial_gk_src", -3: "reflexes_src", -2: "communication_src",
    -1: "throwing_src",
}
PLAIN_OFFSETS = {
    -29: "heading_src", -25: "unselfishness_src", -24: "pace_src",
    -23: "strength_src", -22: "stamina_src", -21: "technique_src",
    -19: "aggression_src", -16: "leadership_src", -5: "agility_src",
}
HIDDEN_OFFSETS = {
    -28: "jumping", -20: "consistency", -18: "big_match",
    -17: "injury_prone", -15: "versatility", -14: "set_pieces",
    -13: "penalty", -9: "work_rate", -8: "flair",
}

# The two attributes that are closed forms over two plain 1-20 bytes:
# attribute -> ((byte column, byte column), (w1, w2, offset), is_estimate), giving
# clip(floor(w1*b1 + w2*b2 + offset), 1, 20) (`fmparser.model.TEAMWORK_W` / `AERIAL_W`).
COMPOSITES = {
    "Teamwork": (("unselfishness_src", "work_rate"), (0.50, 0.50, 0.0), False),
    "Aerial": (("heading_src", "jumping"), (0.24, 0.76, 0.8), True),
}

# The 15 positions in the order the player record carries their familiarities
# (`fmparser.tables.player_attributes.POSITIONS`); a tie for a player's best position goes to
# the earlier one.
POSITIONS = ("GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
             "ST", "DML", "DMR")

# The scrapbook lists that hold our club's squad, one per season
# (`fmparser.tables.player_lists.CLUB_LISTS`).
CLUB_LISTS = range(31, 62)

# The training row's contract flag on a player under contract
# (`fmparser.tables.training.CONTRACTED`).
CONTRACTED = 0x87

# Pounds a year per contract wage unit, from ground truth across the range (De Bruyne 34,000
# units = £17.75M; Hull and Frem players at the low end), within about 2%.
WAGE_GBP_PER_UNIT = 520

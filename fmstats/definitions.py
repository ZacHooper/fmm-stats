"""Names for the game's own codes: what the raw ids the parser hands over MEAN.

The parser reads an id (`raw.training.focus_role`, a snapshot's role byte); what that id is
called is interpretation, so it lives here, on the transform side. `fmstats/mart.py` renders each
map as a mart view (`mart.roles`, `mart.training_attributes`), so SQL, the site and `fmq` share
one set of names, and naming a code reaches a store with `load_duckdb.py --refresh-only`, with
no re-extract.
"""

# Player roles, by id: the training Focus Role (`raw.training.focus_role`) and the role a
# player attribute snapshot shows, which is the same thing on the snapshot's date. The ids run
# in position order -- 0-1 GK, 2 SW, 3-4 full-back, 5-7 DC, 8-12 wide, 13-17 central midfield,
# 18-24 striker -- and 25-32 follow as a second set in the same order.
ROLES = {0: "Goalkeeper", 1: "Sweeper Keeper", 2: "Sweeper", 3: "Full-Back", 4: "Wing-Back",
         5: "Central Defender", 6: "Ball Playing Defender", 7: "No-Nonsense Centre-Back",
         8: "Wide Midfielder", 9: "Winger", 10: "Inverted Winger", 11: "Defensive Winger",
         12: "Inside Forward", 13: "Central Midfielder", 14: "Deep Lying Playmaker",
         15: "Ball Winning Midfielder", 16: "Box to Box Midfielder", 17: "Advanced Playmaker",
         18: "Poacher", 19: "Target Forward", 20: "Deep Lying Forward", 21: "Advanced Forward",
         22: "Complete Forward", 23: "Pressing Forward", 24: "Trequartista", 25: "Libero",
         26: "Shadow Striker", 27: "Inverted Wing-Back", 28: "Defensive Full-Back",
         29: "Anchor", 30: "Defensive Midfielder", 31: "Attacking Midfielder",
         32: "Roaming Playmaker"}

# The ids named by elimination -- the role left over in their position block, placed by their
# holders' attributes -- rather than read off a Scrapbook Profile or the Training page.
ROLES_INFERRED = frozenset({2, 8, 11, 18, 20, 22, 23, 24, 27, 28, 29, 31})

# The Training page's Attr column, by the attribute-focus code (`raw.training.
# focus_attribute`): the codes read off the page. 0, 2, 4, 10, 12, 13 and 15 also occur and
# are not yet named.
TRAINING_ATTRIBUTES = {1: "CRO", 3: "PAS", 5: "TAC", 6: "HAN", 8: "AIR", 9: "REF", 11: "CRE",
                       14: "POS", 17: "STR", 18: "PAC", 19: "STA"}

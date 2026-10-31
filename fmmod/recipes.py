"""Edits to the European Champions Cup's rule file, `eur_champions_cup_2021` (uid 1301394).

Each recipe mutates the file's top-level Nodes (`fmmod.tagged`). The structure they rely on
is in docs/competition-formats.md §3: four stages, `indx` 0 Champions Path, 1 League Path,
2 Group Stage, 3 knockout.
"""
import copy
from typing import Dict, List

from . import tagged as T

CHAMPIONS_CUP = "eur_champions_cup_2021"
R16_NAME = 164                     # round-name catalog: First Knockout Round
FIRST_QUAL_NAME = 149              # First Qualifying Round


def _stage(nodes: List[T.Node], indx: int) -> T.Node:
    stgs = next(n for n in nodes if n.tag == "stgs")
    return next(s for s in stgs.kids if s["indx"].int == indx)


def _name_id(node: T.Node) -> int:
    """A round's `stnm`: a scalar, or the `stgn` inside an `stnm` container."""
    return node["stgn"].int if node.typ == T.TYPE_CONTAINER else node.int


def _round(stage: T.Node, name_id: int) -> T.Node:
    return next(r for r in stage["rnds"].kids if _name_id(r["stnm"]) == name_id)


def one_leg_q1(nodes: List[T.Node]) -> None:
    """The Champions Path First Qualifying Round (34 clubs, 12/19 July) as one match per tie
    instead of two legs: a visible probe of whether the game carries a dictionary edit into the
    archive member on the update day. It takes the single-leg Preliminary Rounds' shape: `nmlg`
    1 and one `date`, whose `mtrl` (0 on a first leg, 3 on a deciding match) becomes the second
    leg's 3; the second leg's `dat2` goes."""
    q1 = _round(_stage(nodes, 0), FIRST_QUAL_NAME)
    q1["nmlg"].int = 1
    q1["date"]["mtrl"].value = q1["dat2"]["mtrl"].value
    q1.remove("dat2")


# Group-stage date slots: the 14 `fxds` entries named Group Stage, indexed 0..13 by the
# stage's `gpdt` dates. 0/1 Sep 19/20, 2/3 Oct 3/4, 4/5 Oct 24/25, 6/7 Nov 7/8, 8/9 Nov 28/29,
# 10/11 Dec 12/13, 12/13 Dec 5/6. The shipped file uses 0-11 (each half of the groups
# alternating Tuesday and Wednesday); 12/13 are spare. In date order:
GROUP_DATES_8 = ([0, 3, 5, 6, 9, 12, 10],      # groups A-B
                 [1, 2, 4, 7, 8, 13, 11])      # groups C-D


def groups_of_8(nodes: List[T.Node]) -> None:
    """32 clubs in 4 groups of 8, single round robin (7 matchdays, 3-4 home games each).
    The top 4 of each group go to the First Knockout Round, so the 16-team knockout stage is
    unchanged. 5th and 6th drop to the EURO Cup's First Knockout Round, which takes exactly 8
    clubs from this stage (the 8 third-placed clubs today) against its own 8 group runners-up;
    7th and 8th are out."""
    g = _stage(nodes, 2)
    g["ngps"].int = 4
    g["ngrt"].int = 8
    g["nrds"].int = 1

    # qualification: top 4 to round 164; place indices 4-5 (5th, 6th) to the EURO Cup's
    # knockout; 6-7 out. `topp`/`btpl` are 0-based places, inclusive.
    qurl = g["qurl"].kids
    qurl[0]["nrpl"].int = 4
    qurl[1]["topp"].int, qurl[1]["btpl"].int = 4, 5
    to_euro, out = g["ftac"].kids
    to_euro["topp"].int, to_euro["btpl"].int = 4, 5
    out["topp"].int, out["btpl"].int = 6, 7

    # finishing place -> `rkli` tier: places 1-4 can still reach any tier from the R16 on
    # (0-4), 5th-6th tier 5 (as 3rd was), 7th-8th tier 6 (as 4th was).
    tiers = [(k, 0, 4) for k in range(4)] + [(5, 5, 5)] * 2 + [(6, 6, 6)] * 2
    g.set(T.lst("rank", *(T.c(None, T.u8("team", i), T.u8("crk", crk), T.u8("hgrk", hi),
                                T.u8("lwrk", lo))
                          for i, (crk, hi, lo) in enumerate(tiers))))

    # the two halves of the groups, each on its own seven dates.
    for half, (groups, dates) in enumerate(zip(([0, 1], [2, 3]), GROUP_DATES_8)):
        gp = g["gpdt"].kids[half]
        gp.set(T.lst("gpis", *(T.u8(None, x) for x in groups)))
        gp["ngrt"].int = 8
        dats = gp["sche"].kids[0]["dats"]
        template = dats.kids[0]                 # {mnsn 73 (Group Stage), in_2, fxor}
        dats.value = []
        for k, d in enumerate(dates):
            day = copy.deepcopy(template)
            day["in_2"].int, day["fxor"].int = d, k
            dats.value.append(day)

    # draw rules over group ranges (`vlgr` types 13/14: 0-3 and 4-7 are the two halves).
    halves = {(0, 3): (0, 1), (4, 7): (2, 3)}
    for rule in g["vlgr"].kids:
        lo, hi = rule.get("in_1"), rule.get("in_2")
        if rule["type"].int in (13, 14) and lo is not None and (lo.int, hi.int) in halves:
            lo.int, hi.int = halves[(lo.int, hi.int)]

    # the R16 draw's `type 5` rule pairs group winners with runners-up; with four clubs
    # through per group there are not eight winners to pair, so it goes (the not-same-group
    # and other pairing rules stay).
    r16 = _round(_stage(nodes, 3), R16_NAME)
    r16["vlgr"].value = [r for r in r16["vlgr"].kids if r["type"].int != 5]


RECIPES: Dict[str, object] = {
    "one-leg-q1": one_leg_q1,
    "groups-of-8": groups_of_8,
}

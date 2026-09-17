#!/usr/bin/env python3
"""
Frozen transfer-value model: estimates what a player is WORTH, for players whose value the
save does not store.

WHY AN ESTIMATE IS NEEDED. The save records a transfer value only for the club you manage
(`attributes.attr_record`, u32 at `M+4` of the own-squad snapshot record). No such record
exists for any other club, the value is not on the global attribute record every player
has, and each of our own values appears exactly once in the file — so there is no general
valuation table to read. `scripts/fit_value_model.py`'s docstring records the three
searches that establish this. A target's price therefore has to be modelled.

WHAT IT IS. OLS on log(value), fitted on the managed club's own squad across every
snapshot in the store — the only labelled data that exists. Refit with
`scripts/fit_value_model.py` and paste the printed block below.

  log(value) = intercept
             + ca*CA + pa*PA                      current / potential ability
             + crep*ln(player CURRENT reputation) the single strongest term
             + llrp*ln(league reputation)         worth +0.03 CV R2; see note below
             + gk*is_goalkeeper
             + acap*A + acap2*A^2, A = min(age,28)
             + res*is_reserve_side

HOW WRONG IT IS — read this before quoting a number. Grouped-CV (by player, because the
same player appears in up to 25 snapshots and an ungrouped split leaks) gives R2 0.712 and
a MEDIAN ERROR OF 2.20x; 2.22x in the £20k-£5M band that actual targets live in, with 70%
inside 3.5x. That is good enough to RANK targets and to separate a £200k player from a £2M
one. It is NOT good enough to decide whether a specific deal clears a budget.

Three specific failure modes, all measured:
  * ABOVE ~£5M IT IS UNEVIDENCED. Only 3 of 833 training rows sit at or above £5M, and our
    most valuable player ever is £7.87M. Do not use it at the top of the market.
  * RESERVE-SIDE PLAYERS ARE THE WEAKEST. A reserve team has no league reputation of its
    own, so it inherits its first team's, which overshoots. `res` absorbs some of this
    but not all.
  * AN ASKING PRICE IS NOT A VALUE, and the gap is enormous and not constant. Røssner:
    £95k value, £3M ask — 31x. Marcus Mathisen, 30: ~£254k estimated, £600-875k ask — ~3x.
    A coveted teenager on a long contract carries a far bigger markup than an ageing
    squad player. THE MARKUP IS NOT MODELLED AT ALL. Never present an estimate as a fee.

WHAT WAS TRIED AND DID NOT WORK:
  * HOME REPUTATION (P+21, what this used to run on) vs CURRENT REPUTATION vs WORLD
    REPUTATION — PR #51 parsed all three off the same record tail (2026-09-17). Current
    reputation replacing home reputation is this file's one real change: it beats home on
    grouped-CV in every spec tried (0.706-0.712 vs 0.694-0.706 across single-term and
    30-seed-averaged comparisons) with LOWER seed-to-seed variance, which tracks its name —
    home reputation is the slower-moving figure, current tracks where the player stands
    now. World reputation never won a single comparison: alone, alongside home, alongside
    current, or all three together, every spec that included it scored equal to or worse
    than current-reputation-alone (see scripts/fit_value_model.py --compare, and the run
    log in docs/agent-context/player-value-estimation.md). Home and current correlate
    0.967, so this is one real reputation signal read at two update cadences, not two
    signals — including both together scores WORSE than current alone (more parameters,
    same information, more overfit noise). One dangling thread, not chased further here:
    world reputation correlates -0.51 with this model's residual on the >=£1M subset
    (n=78) but ~0 on the full sample — plausibly real (world fame vs domestic value
    diverging hardest for the genuinely expensive) or plausibly a 78-row coincidence.
  * CONTRACT LENGTH REMAINING. Full coverage, in-sample coefficient +0.28 in the expected
    direction, but it LOWERS grouped-CV R2 in every spec tried. The likely reading is that
    contract length drives the ASK, not the value.
  * A RAW AGE QUADRATIC. Scores marginally better but turns upward past ~28, claiming a
    33-year-old is worth 1.5x a 26-year-old. That is composition, not ageing: the 29+ band
    is a handful of players including two of our best veterans, while 26-28 is low-CA
    squad filler. A hinge spec reproduced the same upturn. Age is capped at 28 here on
    purpose, trading a little R2 for a curve that is not absurd.
  * POTENTIAL HEADROOM (PA - CA). An exact linear combination of ca and pa, so it added
    a rank deficiency and nothing else.

Because the model trains only on the managed club, a career whose club has never changed
division has no league-reputation variation to learn from and `llrp` will be meaningless.
Frem's climb from 3. Division (league rep 14,860) to the Superliga (34,817) is what makes
that term identifiable here.

See docs/agent-context/player-value-estimation.md for the full write-up.
"""

# Fitted by scripts/fit_value_model.py on fm-frem (833 rows, 86 players, 25 snapshots).
N_TRAIN, CV_R2, MEDIAN_ERR = 833, 0.712, 2.20

COEF = {
    "intercept": -7.895727922499522,
    "ca": 0.032920832109028964,
    "pa": 0.0328231193445884,
    "crep": 2.164211588201666,
    "llrp": 1.6029043472680766,
    "gk": 0.6013207322305286,
    "acap": -0.986427295486262,
    "acap2": 0.01764096258994548,
    "res": 0.4380777794303061,
}

# The band the model was actually validated in. Outside it, say so rather than quoting.
TRUSTED_LO, TRUSTED_HI = 20_000, 5_000_000


def predict(ca, pa, current_reputation, league_reputation, age, is_gk=False, is_reserve=False):
    """Estimated transfer value in GBP. Returns None if a required input is missing.

    `current_reputation`, not the home reputation (P+21) this used to run on — see the
    module docstring's "WHAT WAS TRIED" note for why the swap happened."""
    import math
    if None in (ca, pa, current_reputation, league_reputation, age):
        return None
    if current_reputation <= 0 or league_reputation <= 0:
        return None
    capped = min(float(age), 28.0)
    z = (COEF["intercept"]
         + COEF["ca"] * ca
         + COEF["pa"] * pa
         + COEF["crep"] * math.log(current_reputation)
         + COEF["llrp"] * math.log(league_reputation)
         + COEF["gk"] * (1.0 if is_gk else 0.0)
         + COEF["acap"] * capped
         + COEF["acap2"] * capped ** 2
         + COEF["res"] * (1.0 if is_reserve else 0.0))
    return math.exp(z)


def sql_expr(ca="p.ca", pa="p.pa", rep="s.current_reputation", lrp="lr.lrp",
             age="s.age", gk="p.is_gk", res="lr.is_res"):
    """The same model as a DuckDB scalar expression, for mart.player_value_est.

    `rep` defaults to `current_reputation` (`mart.player_snapshots`), not the home
    reputation (`staging.players.reputation`) this used to read — see the module
    docstring's "WHAT WAS TRIED" note."""
    # Each coefficient is CAST to DOUBLE explicitly: DuckDB reads a bare decimal literal as
    # DECIMAL, and -7.8957279224995220 does not fit the DECIMAL(18,17) it infers.
    def k(name):
        return f"CAST({COEF[name]!r} AS DOUBLE)"
    return f"""EXP(
        {k('intercept')}
      + {k('ca')} * {ca}
      + {k('pa')} * {pa}
      + {k('crep')} * LN({rep})
      + {k('llrp')} * LN({lrp})
      + {k('gk')} * CAST({gk} AS DOUBLE)
      + {k('acap')} * LEAST({age}, 28)
      + {k('acap2')} * LEAST({age}, 28) * LEAST({age}, 28)
      + {k('res')} * CAST({res} AS DOUBLE))"""

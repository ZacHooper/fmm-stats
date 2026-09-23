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
             + lrep*ln(player reputation)         the single strongest term
             + llrp*ln(league reputation)         worth +0.03 CV R2; see note below
             + gk*is_goalkeeper
             + acap*A + acap2*A^2, A = min(age,28)
             + res*is_reserve_side

HOW WRONG IT IS — read this before quoting a number. Grouped-CV (by player, because the
same player appears in up to 22 snapshots and an ungrouped split leaks) gives R2 0.717 and
a MEDIAN ERROR OF 2.27x; 2.15x in the £20k-£5M band that actual targets live in, with 70%
inside 3.6x. That is good enough to RANK targets and to separate a £200k player from a £2M
one. It is NOT good enough to decide whether a specific deal clears a budget.

Three specific failure modes, all measured:
  * ABOVE ~£5M IT IS UNEVIDENCED. Only 2 training rows sit above reputation 7082 and our
    most valuable player ever is £6.76M. William Clem (true value £17.5M) comes out at
    £4.5M — 4x low. Do not use it at the top of the market.
  * RESERVE-SIDE PLAYERS ARE THE WEAKEST. A reserve team has no league reputation of its
    own, so it inherits its first team's, which overshoots: Alfred Røssner (true £95k)
    predicts £235k with the fallback against £126k without it. `res` absorbs some of this
    but not all.
  * AN ASKING PRICE IS NOT A VALUE, and the gap is enormous and not constant. Røssner:
    £95k value, £3M ask — 31x. Marcus Mathisen, 30: ~£254k estimated, £600-875k ask — ~3x.
    A coveted teenager on a long contract carries a far bigger markup than an ageing
    squad player. THE MARKUP IS NOT MODELLED AT ALL. Never present an estimate as a fee.

WHAT WAS TRIED AND DID NOT WORK:
  * CONTRACT LENGTH REMAINING. Full coverage (734/734 rows, median 1.84 years), in-sample
    coefficient +0.28 in the expected direction, but it LOWERS grouped-CV R2 in every
    spec tried (0.724 -> 0.722 with years, 0.718 adding a final-year flag). The likely
    reading is that contract length drives the ASK, not the value.
  * A RAW AGE QUADRATIC. Scores marginally better (CV R2 0.724 vs 0.717) but turns upward
    past ~28, claiming a 33-year-old is worth 1.5x a 26-year-old. That is composition,
    not ageing: the 29+ band is 8 players in 100 rows including two of our best veterans,
    while 26-28 is low-CA squad filler. A hinge spec reproduced the same upturn. Age is
    capped at 28 here on purpose, trading 0.007 R2 for a curve that is not absurd.
  * POTENTIAL HEADROOM (PA - CA). An exact linear combination of ca and pa, so it added
    a rank deficiency and nothing else.

Because the model trains only on the managed club, a career whose club has never changed
division has no league-reputation variation to learn from and `llrp` will be meaningless.
Frem's climb from 3. Division (league rep 14,860) to the Superliga (34,817) is what makes
that term identifiable here.

See docs/agent-context/player-value-estimation.md for the full write-up.
"""

# Fitted by scripts/fit_value_model.py on fm-frem (734 rows, 80 players, 22 snapshots).
N_TRAIN, CV_R2, MEDIAN_ERR = 734, 0.717, 2.27

COEF = {
    "intercept": -15.709785904652186,
    "ca": 0.03659055295951037,
    "pa": 0.036010820101851644,
    "lrep": 1.664648140224399,
    "llrp": 1.523479823028052,
    "gk": 0.5408672263979569,
    "acap": -0.7062381656990232,
    "acap2": 0.011750387401089924,
    "res": 0.21543260349017093,
}

# The band the model was actually validated in. Outside it, say so rather than quoting.
TRUSTED_LO, TRUSTED_HI = 20_000, 5_000_000


def predict(ca, pa, reputation, league_reputation, age, is_gk=False, is_reserve=False):
    """Estimated transfer value in GBP. Returns None if a required input is missing."""
    import math
    if None in (ca, pa, reputation, league_reputation, age):
        return None
    if reputation <= 0 or league_reputation <= 0:
        return None
    capped = min(float(age), 28.0)
    z = (COEF["intercept"]
         + COEF["ca"] * ca
         + COEF["pa"] * pa
         + COEF["lrep"] * math.log(reputation)
         + COEF["llrp"] * math.log(league_reputation)
         + COEF["gk"] * (1.0 if is_gk else 0.0)
         + COEF["acap"] * capped
         + COEF["acap2"] * capped ** 2
         + COEF["res"] * (1.0 if is_reserve else 0.0))
    return math.exp(z)


def sql_expr(ca="p.ca", pa="p.pa", rep="p.reputation", lrp="lr.lrp",
             age="s.age", gk="p.is_gk", res="lr.is_res"):
    """The same model as a DuckDB scalar expression, for mart.player_value_est."""
    # Each coefficient is CAST to DOUBLE explicitly: DuckDB reads a bare decimal literal as
    # DECIMAL, and -15.7097859046521860 does not fit the DECIMAL(18,17) it infers.
    def k(name):
        return f"CAST({COEF[name]!r} AS DOUBLE)"
    return f"""EXP(
        {k('intercept')}
      + {k('ca')} * {ca}
      + {k('pa')} * {pa}
      + {k('lrep')} * LN({rep})
      + {k('llrp')} * LN({lrp})
      + {k('gk')} * CAST({gk} AS DOUBLE)
      + {k('acap')} * LEAST({age}, 28)
      + {k('acap2')} * LEAST({age}, 28) * LEAST({age}, 28)
      + {k('res')} * CAST({res} AS DOUBLE))"""

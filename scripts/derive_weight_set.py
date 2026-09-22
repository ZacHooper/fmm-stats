#!/usr/bin/env python3
"""Derive a weight-set from the measured evidence instead of from forum consensus.

Every stored method before this one was hand-built from what a tactic's author said his players
needed. When we finally scored them (2026-09-12) the result was unflattering: `frem_attacking_ss`
reached r=0.221 against match ratings where weighting every attribute equally reached 0.218, and
its ST block scored 0.351 against goals where flat scored 0.411. A weight-set assembled from
traits is not obviously better than no weight-set at all.

This builds one the other way round. Name what each role is FOR — an outcome mix drawn from the
match data ("win it back" = interceptions + tackles won, "finish" = shots on target + goals) — and
the weights fall out of which attributes actually predict that outcome at that position:

    target   = mean of the z-scored outcome stats, z-scored WITHIN position so roles that pool
               two positions (LB = DL + DML) do not inherit the gap between them
    evidence = partial correlation of each attribute with the target, controlling for the FLAT
               attribute sum — i.e. what the attribute buys BEYOND the player simply being good
               at everything. That control is the point: correlate raw and almost every attribute
               looks useful, because good players are good at all of them, and the derived set
               collapses back to flat.
    weight   = a threshold on that partial correlation, 1-4, the game's own vocabulary

The control is also why this cannot just be read off the Attribute Lab's dot plots: those are raw
correlations, which rank attributes by quality-confound as much as by effect.

**Every line in a shipped block carries its own evidence** (`audit_block`, added by the 2026-09-12
audit). A block can beat flat on two attributes while five others are noise — `black_hawk`'s wide
midfielder beat flat by riding Passing +0.32 while asserting Shooting 4 at a measured -0.32 — so
whatever wins the block-level comparison is then filtered attribute by attribute against the same
bands, dropped or downgraded to what it measures, and re-scored. Lines are never ADDED here: that
would turn a borrowed block into a derived one by stealth. Judgement calls live in `HELD`, named,
with the argument; they do not live in the CSV.

**Scored out-of-fold, because 20-110 player-seasons per position will happily overfit.** Weights
are re-derived inside each CV fold and scored on the rows that derivation never saw, so the
number reported is what the set would do on players we have not measured. A derived set that does
not beat flat out-of-fold is reported as not beating flat — see `--show` output.

    uv run python scripts/derive_weight_set.py --show frem_minmax_4231
    uv run python scripts/derive_weight_set.py --out /tmp/set.json frem_minmax_4231
    uv run python scripts/derive_weight_set.py --all --csv seeds/role_weights.csv   # write both
    uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
import zlib

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# Outcome mixes, as the Attribute Lab's presets name them. A role brief is a list of these.
OUTCOMES = {
    "win_it_back": ["intercept_90", "tackW_90"],
    "keep_it":     ["pass_pct"],
    "progress_it": ["dribbles_90", "keyPass_90"],
    "create":      ["keyPass_90", "assists_90"],
    "finish":      ["shotO_90", "goals_90"],
    "win_the_air": ["headW_90"],
    "rating":      ["rating"],
}

# The two shapes the manager asked for. A method is a weight-set over the store's ten roles, so
# a "formation" here is really a set of ROLE BRIEFS: what each slot in that shape is asked to do.
#
# 4-2-3-1 is the front-foot shape we already win with (Attacking / High / Work Into Box). The
# full-backs are the width, the double pivot screens, the AMC is the creator, the lone ST finishes.
#
# 4-4-1-1 is the answer for a side like FC København: two banks of four, the wide midfielders
# defend first and carry on the break, and the split striker drops in to press and arrives late.
# Note what it does NOT do — sit deep. Away at Midtjylland the cautious plan drew 1-1 with 3 shots
# and the front-foot plan won 6-0, so this is a SHAPE change, not a mentality change
# (docs/fmm-tactic-blueprints.md).
BRIEFS = {
    "frem_minmax_4231": {
        "label": "4-2-3-1, attacking high press, min-maxed from the match data",
        # The front-foot shape we already win with (Attacking / High / Work Into Box). Full-backs
        # are the width, the double pivot screens, the AMC creates, and the CF is the focal point
        # of the attack -- which is why ST is briefed "finish AND win the air", not "finish". The
        # earlier finish-only brief never asked the striker to BE the target, so Aerial and
        # Strength could not earn a place in a block built around a target man.
        "roles": {
            "GK":  ["keep_it"],
            "LB":  ["progress_it", "create"],
            "RB":  ["progress_it", "create"],
            "CB":  ["win_the_air", "win_it_back"],
            "DM":  ["win_it_back", "keep_it"],
            "CM":  ["keep_it", "progress_it"],
            "AML": ["progress_it", "create"],
            "AMR": ["progress_it", "create"],
            "AMC": ["create"],
            "ST":  ["finish", "win_the_air"],
        },
        # Held on judgement -- see JUDGEMENT_NOTE. The 4-2-3-1's full-backs are NOT held: they are
        # briefed to create, and the manager's call was to hold the non-negotiables for the
        # centre-backs, the screening pivot, and the full-backs of the BIG-GAME shape only.
        "hold": {
            "CB": {"tackling": 3, "positioning": 3},
            "DM": {"positioning": 3, "tackling": 3, "teamwork": 3, "passing": 4},
        },
    },
    "frem_minmax_4411": {
        "label": "4-4-1-1, pressing counter for the big games, min-maxed from the match data",
        # NOT a low block and NOT a cautious plan -- away at Midtjylland the cautious plan drew 1-1
        # with 3 shots and the front-foot plan won 6-0. This is the same press in a shape that puts
        # more bodies back for the sides that can hurt us (FC Kobenhavn now, European opposition if
        # we qualify), with a genuine COUNTER element the 4-2-3-1 does not have: the wide midfielders
        # win it back and then break and shoot, the central pair win it and carry.
        "roles": {
            "GK":  ["keep_it"],
            "LB":  ["win_it_back", "win_the_air"],
            "RB":  ["win_it_back", "win_the_air"],
            "CB":  ["win_the_air", "win_it_back"],
            "DM":  ["win_it_back", "keep_it"],
            "CM":  ["win_it_back", "keep_it", "progress_it"],
            "AML": ["win_it_back", "progress_it", "finish"],
            "AMR": ["win_it_back", "progress_it", "finish"],
            "AMC": ["finish", "progress_it"],
            "ST":  ["finish", "win_the_air"],
        },
        "hold": {
            "CB": {"tackling": 3, "positioning": 3},
            "DM": {"positioning": 3, "tackling": 3, "teamwork": 3, "passing": 4},
            "LB": {"tackling": 3, "positioning": 3},
            "RB": {"tackling": 3, "positioning": 3},
        },
    },
}

# Roles that are the SAME JOB on opposite flanks. Their cells share no players at all -- 36 distinct
# left-backs and 36 distinct right-backs, zero overlap -- so deriving them separately measures the
# difference between two groups of footballers and calls it a difference between sides of the pitch.
# That is how the first run ended up rating Pace -0.07 at left-back and +0.46 at right-back off the
# same brief. Symmetric roles are derived ONCE on the union of their positions and the block is
# shipped to both. `strata()` still gives each position its own baseline inside that cell, so
# pooling cannot smuggle in a DL-vs-DR gap; it just doubles the sample.
SYMMETRIC = [("LB", "RB"), ("AML", "AMR")]

# Partial-correlation thresholds -> weight. Deliberately coarse: the samples are 20-110 rows, so
# the ordering of two attributes 0.03 apart is noise and a finer scale would encode that noise.
BANDS = [(0.28, 4), (0.18, 3), (0.10, 2)]
CAT = {4: "key", 3: "important", 2: "useful"}
MAX_KEY = 4              # at most four 4s per role, or "key" stops meaning anything
FOLDS = 5

# A role deviates from flat only if something beats flat by this much. Without a margin the
# derivation "wins" a role by 0.01 on twenty player-seasons and we ship noise as a weighting —
# which is how the ST block we just replaced came to exist. The margin is also what stops the
# best-of-eight-stored-methods comparison from being pure selection on noise.
# A derived block ships only if it beats flat CONSISTENTLY — in at least WIN_RATE of the CV
# splits — rather than by some absolute margin. An absolute margin cannot be calibrated here:
# removing the division confound shrinks every score (ST's flat reading goes 0.50 -> 0.20), so a
# fixed 0.05 bar silently becomes a much higher hurdle on the honest cut than on the flawed one.
# A paired win rate is scale-free and answers the question that matters — would this weighting
# have beaten no weighting, on players it had not seen, most of the time?
WIN_RATE = 0.8

# Stored methods face the same test, bootstrapped: they have no folds to hold out (nothing was
# fitted), so their win rate against flat is measured by resampling the rows. Same question, same
# bar, no second magic constant — the earlier version used an absolute 0.05 margin here and it
# rejected a block we had already validated by hand, purely because the margin was calibrated on
# the pre-division-control scale.
BOOTSTRAPS = 400
TIE = 0.02               # within this, prefer the derived set: it is evidence, not taste

# One 5-fold split on 20-60 rows is a coin flip: the same ST brief scored +0.49 and +0.27 on two
# different splits while nothing about the data changed. So the score is the MEAN over REPEATS
# independent splits, and each role's splits are seeded from the role name rather than from a
# stream, so a role's score does not depend on which methods were derived before it.
REPEATS = 25

# The five keeper attributes cannot be min-maxed here at all. A keeper's match row holds passes
# and essentially nothing else — no saves, no clean sheets, no goals conceded — so "which
# attributes make a good goalkeeper" is not a question this data can answer. GK therefore inherits
# the base method's block rather than pretending otherwise.
GK_INHERITS = True


def _load_asc():
    path = os.path.join(REPO, "scripts", "attribute_stat_correlations.py")
    spec = importlib.util.spec_from_file_location("asc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dominant_competition(db, who_sql=None):
    """The division a player-season mostly belongs to: where he played the most minutes.

    A player-season can straddle a league and a cup, and after a promotion a club's seasons sit in
    different divisions, so "his division" has to be derived per row rather than assumed.
    """
    r = db.q("""SELECT person_id, season, competition, SUM(minutes) m
                FROM mart.match_player_facts
                WHERE is_competitive AND minutes > 0
                GROUP BY person_id, season, competition""")
    r = r.sort_values(["m", "competition"], ascending=[False, True])
    top = r.groupby(["person_id", "season"], as_index=False).first()
    return top.rename(columns={"competition": "comp"})[["person_id", "season", "comp"]]


def role_positions(db):
    """role -> [position], from the store rather than a second copy of the mapping here."""
    r = db.q('SELECT DISTINCT role, "position" FROM mart.position_roles')
    return {k: sorted(v) for k, v in r.groupby("role")["position"].apply(list).items()}


MIN_CELL = 8             # below this, a (position, division) cell cannot be its own baseline


def strata(f):
    """The grouping every figure here is computed inside: position, and division where it fits.

    Position because a role can pool two of them (LB = DL + DML) and the derivation must not
    discover that DMLs complete more passes than DLs. **Division because standard changes what an
    attribute buys** — the same Aggression-on-interceptions effect runs +0.34 in the lower
    divisions and -0.32 in the Superliga, so pooling a 3. Division full-back's per-90 numbers with
    a Superliga one measures the league as much as the player. Restricting to the Superliga instead
    would be cleaner and would leave 14-38 rows a position, which is no sample at all; stratifying
    keeps every row and removes the same confound.

    A division cell with fewer than MIN_CELL rows cannot serve as its own baseline, so those rows
    fall back to being compared against the position as a whole.
    """
    big = f.groupby(["position", "comp"]).person_id.transform("size") >= MIN_CELL
    return np.where(big, f.position + " | " + f.comp, f.position)


def zwithin(f, col, key):
    return f.groupby(key)[col].transform(lambda v: (v - v.mean()) / (v.std() or np.nan))


def target(frame, stats):
    """Mean of the outcome stats, z-scored inside each (position, division) stratum.

    Rows missing any component are dropped: a ratio like pass_pct is undefined for a player who
    attempted none.
    """
    f = frame.dropna(subset=stats).copy()
    if f.empty:
        return f, pd.Series(dtype=float)
    f["_s"] = strata(f)
    y = pd.concat([zwithin(f, s, "_s") for s in stats], axis=1).mean(axis=1)
    ok = y.notna()
    return f[ok], y[ok]


def partials(f, y, attrs, min_sd):
    """Partial correlation of each attribute with the target, controlling for the flat sum.

    Controlling for the flat sum is what makes the output a WEIGHTING rather than a quality
    ranking: it asks what this attribute adds on top of the baseline that weights everything 1,
    which is exactly the baseline the set has to beat.
    """
    a = f[attrs] - f.groupby("_s")[attrs].transform("mean")   # one pass, not 23
    q = a.sum(axis=1)                                       # the flat baseline, unit-demeaned
    out = {}
    for at in attrs:
        if (f[at].std() or 0) < min_sd:                     # no spread -> no honest coefficient
            out[at] = None
            continue
        r_ay, r_aq, r_yq = a[at].corr(y), a[at].corr(q), q.corr(y)
        den = np.sqrt(max(1e-12, (1 - r_aq ** 2) * (1 - r_yq ** 2)))
        out[at] = float((r_ay - r_aq * r_yq) / den) if np.isfinite(den) else None
    return out


def to_weights(part):
    """Thresholded 1-4, keeping at most MAX_KEY fours."""
    w = {}
    for at, r in part.items():
        if r is None or r <= 0:
            continue
        for lo, wt in BANDS:
            if r >= lo:
                w[at.lower()] = wt
                break
    keys = sorted([a for a, v in w.items() if v == 4], key=lambda a: -part[a.capitalize()])
    for a in keys[MAX_KEY:]:
        w[a] = 3
    return w


# ---------------------------------------------------------------------------------------------
# The attribute-level audit
#
# `choose()` can ship a block BORROWED from a hand-built method, on the strength of that block's
# total score. That is how a 4-4-1-1 wide midfielder came to be rated Shooting 4 (measured partial
# -0.32, i.e. the wrong sign) and a bank-of-four central midfielder Shooting 4 (+0.09, below the
# floor that would earn a 2). A block can beat flat on two attributes while five others are noise:
# the total says the block is useful, it does NOT say every line in it is.
#
# So every block, derived or borrowed, is filtered against the same evidence the derivation uses:
# an attribute keeps its place only if its partial clears the lowest band, and it is re-banded to
# what it actually measures rather than to the donor method's opinion. Attributes are only ever
# DROPPED or DOWNGRADED here -- adding one would turn a borrowed block into a derived one by
# stealth and throw away the provenance.
AUDIT_FLOOR = BANDS[-1][0]   # below this an attribute earns nothing, so it is not weighted

# Leadership is the one attribute held below its measured band on purpose. It reads positive in
# every attacking brief (4-2-3-1 LB +0.34, AML +0.34, RB +0.26, DM +0.22, ST +0.22) and negative
# at CB and CM -- the signature of a general "established first-choice player" signal that the
# flat-sum control does not absorb, not of a role requirement. A third of the LB figure is
# literally playing time (+0.341 -> +0.232 once minutes are controlled within the stratum). It is
# real enough to nudge a ranking and nowhere near solid enough to decide one, so it is capped at
# "useful" wherever it survives and never introduced into a block that lacks it.
LEADERSHIP_CAP = 2

# JUDGEMENT_NOTE -- weights held against the measurement, on the record.
#
# The match data can measure defensive VOLUME and not defensive QUALITY. The only defensive outcomes
# in the save are interceptions and tackles won per 90; there are no clean sheets, no goals conceded,
# no pressing stats. A well-positioned centre-back who reads the game makes FEWER tackles, and how
# much defending a player does at all is set by territory and team style rather than by how good he
# is at it. This is not restriction of range -- Tackling and Positioning both have sd 2.7 and a 6-19
# range across 112 centre-back seasons -- it is the wrong measurement. Four independent findings in
# this project now say the same thing (see docs/agent-context/attribute-stat-correlations.md).
#
# So the non-negotiables of the defensive positions are HELD at "important" on football judgement:
# centre-backs and the screening pivot in both shapes, plus the big-game shape's full-backs, who are
# there to defend. The 4-2-3-1's full-backs are briefed to create and are NOT held. Each brief
# declares its own holds in BRIEFS[...]["hold"], so the judgement is visible next to the football
# reasoning rather than buried in a constant.
#
# A hold is the ONE thing allowed to add a weight the evidence did not produce -- the audit itself
# may only drop or downgrade. That asymmetry is deliberate: an addition is a manager's call and has
# to be declared in the brief, where it can be argued with; a removal is what the evidence says.
#
# Two holds are global, applying to every brief:
#   ("DM", "passing")  -- UNMEASURABLE rather than refuted: every DM in the sample sits inside 1.5
#                         points of Passing, so the cell has no spread and `partials()` returns None.
#   ("ST", "movement")  -- measures -0.26 and is kept at 2 on the manager's judgement; see the ST
#                         section of docs/fmm-tactic-blueprints.md for that argument.
HELD = {
    ("DM", "passing"): "no spread in this sample (restriction of range) — held on judgement",
    ("ST", "movement"): "measures negative — held at 2 on the manager's judgement",
}


def audit_block(role, weights, part, hold=None):
    """Drop or downgrade any weight the partials do not support. Returns (weights, notes).

    `hold` is this brief's judgement block for the role ({attr: weight}) -- those lines bypass the
    audit entirely and are ADDED if the evidence never produced them. Everything else is re-banded
    to what it measures.
    """
    hold = hold or {}
    kept, notes = {}, []
    for at, w in sorted(weights.items(), key=lambda t: (-t[1], t[0])):
        r = part.get(at.capitalize())
        if at in hold:
            continue                                    # applied below, at its held weight
        if (role, at) in HELD:
            kept[at] = w
            shown = "no spread to measure" if r is None else f"measures {r:+.2f}"
            notes.append(f"{at} {w} HELD ({shown}) — {HELD[(role, at)]}")
            continue
        if r is None:
            notes.append(f"{at} {w} -> dropped (no spread to measure)")
            continue
        band = next((wt for lo, wt in BANDS if r >= lo), 1)
        if at == "leadership":
            band = min(band, LEADERSHIP_CAP)
        if band < 2:
            notes.append(f"{at} {w} -> dropped (r={r:+.2f}, under the {AUDIT_FLOOR:.2f} floor)")
            continue
        if band < w:
            notes.append(f"{at} {w} -> {band} (r={r:+.2f})")
        kept[at] = band
    for at, w in sorted(hold.items()):
        r = part.get(at.capitalize())
        was = weights.get(at)
        shown = "n/a" if r is None else f"{r:+.2f}"
        notes.append(f"{at} {was if was else '—'} -> {w} JUDGEMENT HOLD (measures {shown}; "
                     f"see JUDGEMENT_NOTE)")
        kept[at] = w
    over = sorted([a for a, v in kept.items() if v == 4 and a not in hold],
                  key=lambda a: -(part.get(a.capitalize()) or 0))
    for a in over[max(0, MAX_KEY - sum(1 for a, v in hold.items() if v == 4)):]:
        kept[a] = 3
    return kept, notes


def fmt_w(w):
    return "  ".join(f"{k} {v}" for k, v in sorted(w.items(), key=lambda t: (-t[1], t[0])))


def score(pred, y):
    pred, y = np.asarray(pred, dtype=float), np.asarray(y, dtype=float)
    if len(y) < 3 or not np.std(pred) or not np.std(y):
        return float("nan")
    return float(np.corrcoef(pred, y)[0, 1])


def cv_score(f, y, attrs, min_sd, seed):
    """Out-of-fold score of the DERIVATION, not of one fixed set.

    Weights are re-derived inside each training fold, so the score is what the recipe earns on
    rows it never saw. Scoring a set on the rows that produced it is the easiest way to ship a
    number that evaporates next season. Averaged over REPEATS splits because a single split on
    this little data is noise.
    """
    rng = np.random.default_rng(seed)
    scores, flat = [], flat_score(f, y, attrs)
    for _ in range(REPEATS):
        idx = rng.permutation(len(f))
        oof = np.full(len(f), np.nan)
        for k in range(FOLDS):
            te = idx[k::FOLDS]
            tr = np.setdiff1d(idx, te)
            if len(tr) < 12:
                return float("nan")
            w = to_weights(partials(f.iloc[tr], y.iloc[tr], attrs, min_sd))
            vec = np.array([w.get(a.lower(), 1) for a in attrs])
            oof[te] = f.iloc[te][attrs].to_numpy(dtype=float) @ vec
        ok = ~np.isnan(oof)
        s = score(oof[ok], y[ok].to_numpy())
        if np.isfinite(s):
            scores.append(s)
    if not scores:
        return float("nan"), 0.0
    return float(np.mean(scores)), float(np.mean([x > flat for x in scores]))


def flat_score(f, y, attrs):
    """No fitting happens, so there is nothing to hold out — scored on everything."""
    return score(f[attrs].to_numpy(dtype=float).sum(axis=1), y.to_numpy())


def method_score(f, y, attrs, weights):
    vec = np.array([weights.get(a.lower(), 1) for a in attrs])
    return score(f[attrs].to_numpy(dtype=float) @ vec, y.to_numpy())


def boot_win(f, y, attrs, weights, seed):
    """How often a FIXED weight-set beats flat on a resample of the rows.

    Paired: each resample scores both sets on the same rows, so this measures whether the
    weighting helps rather than whether this particular 20-60 rows happened to favour it.
    """
    if not weights:
        return 0.0
    A = f[attrs].to_numpy(dtype=float)
    yv = y.to_numpy(dtype=float)
    w = A @ np.array([weights.get(a.lower(), 1) for a in attrs])
    flat = A.sum(axis=1)
    rng = np.random.default_rng(seed)
    wins = 0
    for _ in range(BOOTSTRAPS):
        ix = rng.integers(0, len(yv), len(yv))
        a, b = score(w[ix], yv[ix]), score(flat[ix], yv[ix])
        wins += np.isfinite(a) and np.isfinite(b) and a > b
    return wins / BOOTSTRAPS


def choose(derived_w, derived_oof, win, flat, stored_scores, stored_wins, stored, role):
    """Pick the block to ship: derived, flat, or a stored method's — whichever earns it.

    Derived is scored OUT-OF-FOLD and the others in-sample, which looks unfair until you notice
    the asymmetry runs the right way: the stored sets and flat were never fitted to this data, so
    their in-sample score IS their honest score, while the derived set would flatter itself on the
    rows that produced it. Flat wins ties, so a role only carries weights when weighting it is
    demonstrably better than not.
    """
    if not np.isfinite(flat):
        return "flat", float("nan"), {}
    # the derived block earns its place by winning most splits, not by winning on average
    derived_ok = (np.isfinite(derived_oof) and derived_oof > flat and win >= WIN_RATE
                  and bool(derived_w))
    stored_live = [(m, sc, stored[m].get(role, {})) for m, sc in stored_scores.items()
                   if np.isfinite(sc) and sc > flat and stored_wins.get(m, 0) >= WIN_RATE
                   and stored[m].get(role)]
    best_stored = max(stored_live, key=lambda c: c[1], default=None)
    if derived_ok and (best_stored is None or derived_oof >= best_stored[1] - TIE):
        return "derived", derived_oof, derived_w
    if best_stored is not None:
        return best_stored
    return "flat", flat, {}


def symmetric_twin(role):
    for a, b in SYMMETRIC:
        if role == a:
            return b
        if role == b:
            return a
    return None


def derive(asc, frame, attrs, rolepos, brief, stored, base, seed):
    """One method: per-role weights plus the scoreboard that justifies (or indicts) them."""
    rows, report = {}, []
    holds = brief.get("hold", {})
    twins = {}          # canonical role of a symmetric pair -> the block it decided
    for role, outcomes in brief["roles"].items():
        if role == "GK" and GK_INHERITS:
            rows[role] = dict(stored.get(base, {}).get(role, {}))
            report.append({"role": role, "n": 0, "outcomes": outcomes, "source": f"inherited {base}",
                           "note": "not measurable — the save records no saves or clean sheets",
                           "weights": rows[role]})
            continue
        stats = [s for o in outcomes for s in OUTCOMES[o]]
        # A symmetric role is derived on BOTH flanks' positions at once -- see SYMMETRIC.
        twin = symmetric_twin(role)
        paired = bool(twin and brief["roles"].get(twin) == outcomes
                      and holds.get(twin) == holds.get(role))
        key = min(role, twin) if paired else role      # the pair decides once, under one name
        pool = list(rolepos.get(role, []))
        if paired:
            pool += [p for p in rolepos.get(twin, []) if p not in pool]
        if paired and key in twins:
            w, src = twins[key]["weights"], f"{twins[key]['role']} (symmetric)"
            if w:
                rows[role] = dict(w)
            report.append(dict(twins[key], role=role, source=src, weights=w))
            continue
        sub = frame[frame.position.isin(pool)]
        f, y = target(sub, stats)
        if len(f) < asc.MIN_N:
            report.append({"role": role, "n": len(f), "outcomes": outcomes,
                           "source": "flat", "note": "too few rows", "weights": {}})
            continue
        part = partials(f, y, attrs, asc.MIN_SD)
        dw = to_weights(part)
        # Seeded from the role name -- or from the PAIR's canonical name for a symmetric role, so
        # both flanks are decided by the same folds. Without that, identical evidence produced
        # different blocks: left-back shipped its derived set at a 96% win rate while right-back,
        # off the very same pooled cell, shipped frem_game_state's at 88%. That is fold noise
        # deciding a football question.
        oof, win = cv_score(f, y, attrs, asc.MIN_SD, seed + zlib.crc32(key.encode()))
        flat = flat_score(f, y, attrs)
        ss = {m: method_score(f, y, attrs, ws.get(role, {})) for m, ws in stored.items()}
        sw = {m: boot_win(f, y, attrs, ws.get(role, {}), seed + zlib.crc32((role + m).encode()))
              for m, ws in stored.items()}
        src, sc, w = choose(dw, oof, win, flat, ss, sw, stored, role)
        # Whatever won, every line in it now has to carry its own evidence.
        w, notes = audit_block(role, w, part, holds.get(role)) if (w or holds.get(role)) else ({}, [])
        # An audited block has lost weights, so its score is no longer the one that won the
        # comparison -- re-measure it, and fall back to flat if the audit ate what it was living on.
        if w:
            sc = method_score(f, y, attrs, w)
            if not np.isfinite(sc) or sc <= flat:
                notes.append(f"block no longer beats flat after the audit "
                             f"({sc:+.3f} vs {flat:+.3f}) — shipping flat")
                src, sc, w = "flat (audited out)", flat, {}
        if w:
            rows[role] = w
        entry = {
            "role": role, "n": len(f), "outcomes": outcomes, "positions": pool,
            "weights": w, "source": src, "chosen_score": sc, "audit": notes,
            "top": sorted([(a, round(r, 2)) for a, r in part.items() if r is not None],
                          key=lambda t: -t[1])[:6],
            "derived": dw, "derived_oof": oof, "win": win, "flat": flat,
            "stored": ss, "stored_win": sw,
        }
        report.append(entry)
        if paired:
            twins[key] = entry
    return rows, report


def stored_methods(db):
    r = db.q("SELECT method, role, attribute, weight FROM mart.role_weights WHERE weight > 1")
    out = {}
    for (m, role), g in r.groupby(["method", "role"]):
        out.setdefault(m, {})[role] = dict(zip(g.attribute, g.weight))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("method", nargs="*", choices=list(BRIEFS), help="which brief(s) to derive")
    p.add_argument("--all", action="store_true", help="derive every brief")
    p.add_argument("--show", action="store_true", help="print the evidence and the scoreboard")
    p.add_argument("--out", help="write the weight-set JSON here (one method only)")
    p.add_argument("--csv", help="append/replace these methods in a role_weights CSV in place")
    p.add_argument("--min-minutes", type=int, default=180)
    p.add_argument("--competition", help="SQL ILIKE pattern; default every division pooled")
    p.add_argument("--career", default=os.environ.get("FM_CAREER", "frem"))
    p.add_argument("--db")
    p.add_argument("--base", default="frem_attacking_ss",
                   help="method GK inherits from (GK is not measurable here)")
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()

    names = list(BRIEFS) if a.all else a.method
    if not names:
        p.error("name a method or pass --all")
    if a.out and len(names) != 1:
        p.error("--out writes one method; use --csv for several")

    os.environ["FM_CAREER"] = a.career
    if a.db:
        os.environ["FM_DUCKDB"] = a.db
    os.environ.setdefault("FM_DUCKDB_READONLY", "1")
    from dashboard import db

    asc = _load_asc()
    ours, attrs = asc.build(db, a.min_minutes, a.competition, "us")
    opp, _ = asc.build(db, a.min_minutes, a.competition, "opponents")
    frame = pd.concat([ours, opp], ignore_index=True)
    frame = frame.merge(dominant_competition(db), on=["person_id", "season"], how="left")
    frame["comp"] = frame.comp.fillna("?")
    # ROW ORDER IS LOAD-BEARING. KFold(shuffle=True) permutes positions, not identities, so a
    # different row order is a different set of folds and therefore a different win rate. DuckDB
    # returns rows in whatever order its parallel scan finished in, so three identical runs of
    # this script scored the 4-2-3-1 LB block at 64%, 80% and 84% against an 80% bar -- the block
    # shipped or not on a coin flip. Sort before anything is measured.
    frame = frame.sort_values(["person_id", "season"]).reset_index(drop=True)
    attrs = [x for x in attrs if x not in asc.__dict__.get("GK_ONLY", [])]
    rolepos = role_positions(db)
    stored = stored_methods(db)

    print(f"{len(frame)} player-seasons (ours + opponents) at >= {a.min_minutes} minutes"
          + (f" in {a.competition}" if a.competition else "")
          + f"\n  every figure below is computed inside a (position, division) stratum of "
            f"{MIN_CELL}+ rows, so neither position nor standard can do the explaining")

    out_docs = {}
    for name in names:
        brief = BRIEFS[name]
        # A method must not borrow from ITSELF. `stored` is read from the store, so once a derived
        # method has been seeded, its own blocks come back as candidates -- fitted on these very
        # rows, so they bootstrap at ~100% and beat every honest candidate. Re-deriving then just
        # re-ratifies last run's output and the audit trail quietly becomes a loop.
        # ...and not from a SIBLING derived method either: every method in BRIEFS was fitted on
        # this same data, so 4-4-1-1 borrowing 4-2-3-1's CM block is the same loop one step removed.
        # Only the hand-built methods -- written from a tactic author's stated player traits, never
        # from these rows -- are honest rivals.
        rivals = {m: w for m, w in stored.items() if m not in BRIEFS}
        rows, report = derive(asc, frame, attrs, rolepos, brief, rivals, a.base, a.seed)
        out_docs[name] = {
            "method": name, "weights": rows, "base_method": "derived",
            "label": brief["label"], "created": dt.datetime.now().isoformat(timespec="seconds"),
            "notes": f"derived by scripts/derive_weight_set.py from {len(frame)} player-seasons",
            "edited_roles": sorted(rows),
        }
        if a.show:
            print(f"\n=== {name} — {brief['label']}")
            for r in report:
                print(f"  {r['role']:4s} n={r['n']:<4d} {'+'.join(r['outcomes'])}"
                      f"   -> {r['source'].upper()}"
                      + (f"   ({r['note']})" if r.get("note") else ""))
                if "top" not in r:
                    if r["weights"]:
                        print("       weights : " + fmt_w(r["weights"]))
                    continue
                print("       evidence: " + "  ".join(f"{k} {v:+.2f}" for k, v in r["top"]))
                print("       derived : " + (fmt_w(r["derived"]) or "(nothing clears the floor)"))
                best = max((v for v in r["stored"].values() if np.isfinite(v)), default=float("nan"))
                bestm = max(r["stored"], key=lambda k: r["stored"][k] if np.isfinite(r["stored"][k]) else -9)
                print(f"       score   : derived(out-of-fold) {r['derived_oof']:+.3f} "
                      f"(beats flat in {r['win']:.0%} of splits)   flat {r['flat']:+.3f}   "
                      f"best stored {best:+.3f} ({bestm}, {r['stored_win'].get(bestm, 0):.0%})")
                for line in r.get("audit", []):
                    print("       audit   : " + line)
                print("       SHIPPED : " + (fmt_w(r["weights"]) or "flat — nothing beat it"))

    if a.out:
        json.dump(out_docs[names[0]], open(a.out, "w"), indent=1)
        print(f"\nwrote {a.out}")
    if a.csv:
        write_csv(a.csv, out_docs)
        print(f"\nupdated {a.csv}")


def write_csv(path, docs):
    """Replace these methods in the seed CSV, leaving every other method untouched."""
    import csv
    rows = list(csv.DictReader(open(path)))
    names = set(docs)
    keep = [r for r in rows if r["method"] not in names]
    new = [{"method": n, "role": role, "attribute": at, "category": CAT[w], "weight": w}
           for n, d in docs.items() for role, ws in d["weights"].items()
           for at, w in sorted(ws.items(), key=lambda t: (-t[1], t[0]))]
    with open(path, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["method", "role", "attribute", "category", "weight"])
        wr.writeheader()
        wr.writerows(keep + new)


if __name__ == "__main__":
    main()

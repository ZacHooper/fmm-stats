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

**Scored out-of-fold, because 20-110 player-seasons per position will happily overfit.** Weights
are re-derived inside each CV fold and scored on the rows that derivation never saw, so the
number reported is what the set would do on players we have not measured. A derived set that does
not beat flat out-of-fold is reported as not beating flat — see `--show` output.

    uv run python scripts/derive_weight_set.py --show frem_minmax_4231
    uv run python scripts/derive_weight_set.py --out /tmp/set.json frem_minmax_4231
    uv run python scripts/derive_weight_set.py --all --csv seeds/role_weights.csv   # write both

Then, to make it usable:
    uv run python scripts/import_weight_set.py /tmp/set.json --promote
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
        "label": "4-2-3-1, min-maxed from the match data",
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
            "ST":  ["finish"],
        },
    },
    "frem_minmax_4411": {
        "label": "4-4-1-1 for the big games, min-maxed from the match data",
        "roles": {
            "GK":  ["keep_it"],
            "LB":  ["win_it_back", "win_the_air"],
            "RB":  ["win_it_back", "win_the_air"],
            "CB":  ["win_the_air", "win_it_back"],
            "DM":  ["win_it_back"],
            "CM":  ["win_it_back", "keep_it"],
            "AML": ["win_it_back", "progress_it"],
            "AMR": ["win_it_back", "progress_it"],
            "AMC": ["finish", "progress_it"],
            "ST":  ["finish"],
        },
    },
}

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


def derive(asc, frame, attrs, rolepos, brief, stored, base, seed):
    """One method: per-role weights plus the scoreboard that justifies (or indicts) them."""
    rows, report = {}, []
    for role, outcomes in brief["roles"].items():
        if role == "GK" and GK_INHERITS:
            rows[role] = dict(stored.get(base, {}).get(role, {}))
            report.append({"role": role, "n": 0, "outcomes": outcomes, "source": f"inherited {base}",
                           "note": "not measurable — the save records no saves or clean sheets",
                           "weights": rows[role]})
            continue
        stats = [s for o in outcomes for s in OUTCOMES[o]]
        sub = frame[frame.position.isin(rolepos.get(role, []))]
        f, y = target(sub, stats)
        if len(f) < asc.MIN_N:
            report.append({"role": role, "n": len(f), "outcomes": outcomes,
                           "source": "flat", "note": "too few rows", "weights": {}})
            continue
        part = partials(f, y, attrs, asc.MIN_SD)
        dw = to_weights(part)
        # seeded from the role name: a role scores the same however many briefs precede it
        oof, win = cv_score(f, y, attrs, asc.MIN_SD, seed + zlib.crc32(role.encode()))
        flat = flat_score(f, y, attrs)
        ss = {m: method_score(f, y, attrs, ws.get(role, {})) for m, ws in stored.items()}
        sw = {m: boot_win(f, y, attrs, ws.get(role, {}), seed + zlib.crc32((role + m).encode()))
              for m, ws in stored.items()}
        src, sc, w = choose(dw, oof, win, flat, ss, sw, stored, role)
        if w:
            rows[role] = w
        report.append({
            "role": role, "n": len(f), "outcomes": outcomes,
            "weights": w, "source": src, "chosen_score": sc,
            "top": sorted([(a, round(r, 2)) for a, r in part.items() if r is not None],
                          key=lambda t: -t[1])[:6],
            "derived": dw, "derived_oof": oof, "win": win, "flat": flat,
            "stored": ss, "stored_win": sw,
        })
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
        rows, report = derive(asc, frame, attrs, rolepos, brief, stored, a.base, a.seed)
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

"""Position review — one depth chart per role, with a keep / loan / sell read.

Answers two questions the other pages don't: *what does each position in the squad actually
look like, in starting order*, and *where does the window money go*. It deliberately puts two
INDEPENDENT yardsticks side by side, because they disagree constantly and the disagreement is
the useful part:

- **Rating / Fit %ile** — tactic fit under the selected weight-set. Flatters a player whose
  attribute spread suits the role even when his level is poor. **Fam** (0-20) is the sanity
  check on it: the rating is already multiplied down by familiarity, so a high Rating on a low
  Fam means raw attributes are dragging him into a position that isn't really his.
- **Ability rank** — level. His position-matched rank among every player in a given division,
  which is the only fair way to compare across divisions (a Fit %ile is scoped to whatever
  league its owner sits in, so a reserve-team player gets ranked against the reserve league).
  Computed inside db.py so only "6 of 75" ever reaches the UI, never the number behind it.

Loaned-IN players are excluded by default: they'll go back, so planning around them overstates
the squad. Loaned-OUT players stay in — they're still ours.
"""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Positions", page_icon="🧭", layout="wide")
st.title("🧭 Position review")
st.caption("Every position in starting order, with a keep / loan / sell read per player.")
_fam_note = st.empty()

season, phase = db.select_label()
method = db.select_method()

# Slots a role fills in the XI — drives the starter / cover / surplus split below.
DEFAULT_SLOTS = {"GK": 1, "LB": 1, "CB": 2, "RB": 1, "DM": 1, "CM": 2,
                 "AML": 1, "AMC": 1, "AMR": 1, "ST": 1}
ROLE_ORDER = ["GK", "LB", "CB", "RB", "DM", "CM", "AML", "AMC", "AMR", "ST"]
# A host club needs at least this many players at the position (him included) before "he'd be
# their first choice" means anything — some lower-division clubs field 1 player in a position,
# or none at all, so every player we own would nominally "start" there.
MIN_HOST_SQUAD = 3

_fam_curve, _fam_lo = db.familiarity_params()

ladder = db.comparison_leagues(season, phase, limit=3)
if not ladder or ladder[0][0] is None:
    st.info("No club→league membership for this snapshot yet, so there's nothing to rank "
            "against. Ability ranks need each club's division; check the snapshot loaded a "
            "`club_league` mapping.")
    st.stop()
our_cid, our_lg = ladder[0]
lower = [(c, n) for c, n in ladder[1:] if c is not None]

eff = db.effective_table(season, phase, method)
if eff.empty:
    st.info("No rated players in this snapshot.")
    st.stop()

_has_loan_col = db.q("SELECT 1 AS ok FROM information_schema.columns WHERE table_schema='staging' "
                     "AND table_name='players' AND column_name='loaned_in'")
loaned_in = (db.q("SELECT tid FROM staging.players WHERE season=? AND phase=? AND loaned_in",
                  [season, phase])["tid"].astype(int).tolist()
             if not _has_loan_col.empty else [])
min_fam = st.sidebar.slider(
    "Minimum familiarity", 0, 20, 15, step=1,
    help="Drops rows where the player barely knows the position. staging.player_positions "
         "lists every position a player has ANY familiarity in, so at 0 a depth chart of left "
         "backs is padded with centre-halves who could shuffle across. The floor applies to "
         "the comparison pools too, so ability ranks count only players who genuinely play "
         "there — raise or lower it and every rank on the page moves with it.")
excl_loanees = st.sidebar.toggle(
    "Exclude loaned-in players", value=True,
    help="Loanees go back at the end of their spell, so counting them makes the squad look "
         "deeper than it is. Turn off to see the squad as it lines up today.")

ours = eff[eff["club_tid"].isin(db.OUR_CLUBS)].copy()
if excl_loanees and loaned_in:
    ours = ours[~ours["tid"].astype(int).isin(set(loaned_in))]
if ours.empty:
    st.info("No owned players in this snapshot.")
    st.stop()

if min_fam:
    ours = ours[ours["familiarity"] >= min_fam]
    if ours.empty:
        st.info(f"No owned player has a position at familiarity {min_fam} or above. "
                "Lower the floor in the sidebar.")
        st.stop()

# one row per (player, role): his best position for that role, ranked by effective rating
per_role = ours.loc[ours.groupby(["tid", "role"])["eff"].idxmax()].copy()
per_role["depth"] = per_role.groupby("role")["eff"].rank(ascending=False, method="min").astype(int)
primary = per_role.loc[per_role.groupby("tid")["eff"].idxmax()].set_index("tid")["role"].to_dict()

# Fit %ile recomputed against OUR OWN division at that position, so a reserve-team player is
# measured on the same scale as a first-teamer (his club's own league_cid would be the reserve
# league, which ranks him against other reserve sides).
div_pool = eff[(eff["league_cid"] == our_cid) & (eff["familiarity"] >= min_fam)]


def fit_pctile(tid, position, value):
    p = div_pool[(div_pool["position"] == position) & (div_pool["tid"] != tid)]["eff"]
    return round(100 * (p < value).mean(), 1) if len(p) >= 8 else float("nan")


per_role["fit_div"] = [fit_pctile(t, p, e) for t, p, e
                       in zip(per_role["tid"], per_role["position"], per_role["eff"])]

tid_pos = tuple(sorted({(int(t), str(p)) for t, p in zip(per_role["tid"], per_role["position"])}))
ranks = db.ability_rank_leagues(season, phase, tid_pos, tuple(c for c, _ in ladder),
                                min_fam, db._dbver())
rk = {(int(r.tid), r.position, int(r.league_cid)): (int(r.rank), int(r.n))
      for r in ranks.itertuples()}


def rank_cell(tid, position, cid):
    v = rk.get((int(tid), position, int(cid)))
    return f"{v[0]} / {v[1]}" if v else "—"


def rank_pct(tid, position, cid):
    """0-100 quality percentile derived from rank/N (100 = best in that division)."""
    v = rk.get((int(tid), position, int(cid)))
    if not v or v[1] < 2:
        return float("nan")
    return round(100 * (v[1] - v[0]) / (v[1] - 1), 1)


per_role["div_pct"] = [rank_pct(t, p, our_cid)
                       for t, p in zip(per_role["tid"], per_role["position"])]

# would a club one or two divisions down actually PLAY him? rank 1 = their first choice
starts_at, best_hosts = {}, {}
for cid, lname in lower:
    hosts = db.ability_rank_clubs(season, phase, tid_pos, cid, min_fam, db._dbver())
    if hosts.empty:
        continue
    for (t, p), g in hosts.groupby(["tid", "position"]):
        firsts = g[(g["rank"] == 1) & (g["n"] >= MIN_HOST_SQUAD)]
        starts_at[(int(t), p, cid)] = len(firsts)
        best_hosts[(int(t), p, cid)] = g.sort_values(["rank", "n"], ascending=[True, False])

# ---------------------------------------------------------------- per-player bio / context
tids = [int(t) for t in per_role["tid"].unique()]
bio = db.player_bio(season, phase, tids)
contract = db.contract_info(season, phase, tids)
sq = db.squad(season, phase)
status = dict(zip(sq["tid"].astype(int), sq["status"]))


@st.cache_data(show_spinner=False)
def last_season(season, ver):
    """Starts / apps / minutes / avg rating in the PREVIOUS campaign, deduped to the latest
    phase per season (the light-results buffer repeats rows across snapshots)."""
    rows = db.match_stats_rows(db.OUR_CLUBS)
    if rows is None or rows.empty:
        return pd.DataFrame()
    rows = rows[(rows["season"] == season - 1) & rows["appeared"]]
    if rows.empty:
        return pd.DataFrame()
    return rows.groupby("tid").agg(starts=("started", "sum"), apps=("rating", "size"),
                                   mins=("minutes", "sum"), rat=("rating", "mean"))


prev = last_season(season, db._dbver())


def prev_cell(tid):
    if prev.empty or int(tid) not in prev.index:
        return "—"
    r = prev.loc[int(tid)]
    return f"{int(r.starts)}/{int(r.apps)} · {int(r.mins)}m · {r.rat:.2f}"


# ---------------------------------------------------------------- the read
def read_player(row, slots):
    """Suggestion, not a verdict — it only knows depth, level, age and whether a lower
    division would start him. Rules are spelled out in the legend so you can overrule them."""
    depth, age = int(row["depth"]), row["age"]
    pct = row["div_pct"]
    plays_lower = any(starts_at.get((int(row["tid"]), row["position"], c), 0) > 0
                      for c, _ in lower)
    home = primary.get(int(row["tid"]))
    if home and home != row["role"]:
        return (f"Keep — starter here, primary {home}" if depth <= slots
                else f"Cover only — primary {home}")
    if depth <= slots:
        if pd.notna(age) and age <= 19:
            return "Keep — starter (young; ranks low on CURRENT ability)"
        if pd.notna(pct) and pct < 40:
            return "Keep — starter, but upgrade target"
        return "Keep — starter"
    if depth == slots + 1:
        return "Keep — cover"
    if pd.notna(age) and age < 24 and plays_lower:
        return "Loan out"
    if pd.notna(age) and age <= 18:
        return "Keep — reserves (too young to judge)"
    if pd.notna(age) and age >= 23 and pd.notna(pct) and pct < 33:
        return "Sell / release"
    if not plays_lower and pd.notna(age) and age >= 20:
        return "Sell / release — starts nowhere below us"
    return "Surplus — loan or sell"


per_role["age"] = per_role["tid"].map(lambda t: bio.get(int(t), {}).get("Age"))

with st.expander("Formation slots — how many of each role start", expanded=False):
    st.caption("Drives the starter / cover / surplus split. Defaults to a 4-1-2-3.")
    cols = st.columns(len(ROLE_ORDER))
    slots = {}
    for c, role in zip(cols, ROLE_ORDER):
        slots[role] = c.number_input(role, 0, 4, DEFAULT_SLOTS.get(role, 1), key=f"slot_{role}")

roles_present = [r for r in ROLE_ORDER if r in set(per_role["role"])]
roles_present += [r for r in sorted(set(per_role["role"])) if r not in ROLE_ORDER]

# ---------------------------------------------------------------- summary: window priorities
_fam_note.caption(
    f"Showing positions at **familiarity {min_fam}+** (sidebar) — and ranking against players "
    f"who clear the same floor, so nobody is measured against a makeshift field."
    if min_fam else "Familiarity floor off — every listed position counts, including ones a "
                    "player barely knows.")

st.subheader(f"Where the window money goes · {our_lg}")
rows = []
for role in roles_present:
    g = per_role[per_role["role"] == role].sort_values("eff", ascending=False)
    n_slots = slots.get(role, 1)
    best = g.iloc[0]
    top = g.head(max(1, n_slots))
    pct = best["div_pct"]
    young = pd.notna(best["age"]) and best["age"] <= 19
    if pd.notna(pct) and pct < 40 and young:
        read = "Prospect starting — cover him"
    elif pd.notna(pct) and pct < 40:
        read = "Needs a starter"
    elif len(g) <= n_slots:
        read = "Thin — no cover"
    elif len(g) > n_slots + 2:
        read = "Stocked — surplus to move on"
    else:
        read = "Settled"
    rows.append({"Role": role, "Owned": len(g), "Slots": n_slots,
                 "Best available": db.player_label(best["tid"], best["name"]),
                 "Pos": best["position"], "Fam": int(best["familiarity"]),
                 f"His rank in {our_lg}": rank_cell(best["tid"], best["position"], our_cid),
                 "Div %ile": pct, "Fit %ile": best["fit_div"],
                 "Avg age of starters": round(top["age"].mean(), 1) if top["age"].notna().any()
                 else None,
                 "Read": read})
summary = pd.DataFrame(rows).sort_values("Div %ile", na_position="last")
st.dataframe(summary, hide_index=True, width="stretch", column_config={
    "Fam": st.column_config.ProgressColumn(
        format="%d", min_value=0, max_value=20,
        help="How natural the position is for our best man there (0-20). A settled-looking "
             "role held by a low-Fam player is really a hole being covered."),
    "Div %ile": st.column_config.ProgressColumn(
        format="%.0f", min_value=0, max_value=100,
        help="Our best player's ability percentile at that position in our own division. "
             "Low = the position is below the level we're playing at."),
    "Fit %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100)})
st.caption("Sorted weakest first — the top row is where a signing changes most. **Div %ile** "
           "is level (ability), **Fit %ile** is tactic fit; a high Fit over a low Div %ile "
           "means the weight-set likes a player the division doesn't. Ability is CURRENT "
           "ability, so a teenage prospect ranks near the bottom of a senior division however "
           "good he'll become — those rows read *Prospect starting*, which means buy cover, "
           "not buy a replacement.")

st.divider()
pick = st.pills("Positions", roles_present, selection_mode="multi", default=roles_present)
show_roles = pick or roles_present

# ---------------------------------------------------------------- per-role depth charts
for role in show_roles:
    g = per_role[per_role["role"] == role].sort_values("eff", ascending=False)
    n_slots = slots.get(role, 1)
    st.subheader(f"{role} · {len(g)} owned · {n_slots} start")
    tbl = []
    for _, r in g.iterrows():
        row = {"#": int(r["depth"]),
               "Player": db.player_label(r["tid"], r["name"]),
               "Age": r["age"], "Pos": r["position"], "Fam": int(r["familiarity"]),
               "Rating": round(r["eff"]), "Fit %ile": r["fit_div"]}
        for cid, lname in ladder:
            row[lname or f"#{cid}"] = rank_cell(r["tid"], r["position"], cid)
        ci = contract.get(int(r["tid"]), {})
        exp = ci.get("Expiry")
        row["Contract"] = pd.to_datetime(exp).strftime("%b %Y") if pd.notna(exp) else "—"
        row["Wage"] = ci.get("Wage")
        row["Last season"] = prev_cell(r["tid"])
        row["Squad"] = status.get(int(r["tid"]), "—")
        row["Also"] = ", ".join(sorted(set(per_role[per_role["tid"] == r["tid"]]["role"]) - {role})) or "—"
        row["Read"] = read_player(r, n_slots)
        tbl.append(row)
    depth_df = pd.DataFrame(tbl)
    st.dataframe(depth_df, hide_index=True, width="stretch", column_config={
        "Fam": st.column_config.ProgressColumn(
            format="%d", min_value=0, max_value=20,
            help=f"Position familiarity 0-20 — is this his TRUE position? It already discounts "
                 f"Rating via the familiarity multiplier (×{_fam_lo:.2f} at 0, ×1.00 at 20), so "
                 f"a low Fam with a high Rating means raw attributes are carrying him somewhere "
                 f"he doesn't really play."),
        "Fit %ile": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
        "Wage": st.column_config.NumberColumn(format="£%d", help="£ per year"),
        "Last season": st.column_config.TextColumn(help="starts/apps · minutes · avg rating"),
        "Also": st.column_config.TextColumn(help="other roles he rates in"),
        "Read": st.column_config.TextColumn(width="medium")})

    # who'd actually play him if we loaned him out
    surplus = g[g["depth"] > n_slots]
    if len(surplus) and lower:
        with st.expander(f"Loan destinations for the {len(surplus)} behind the starters"):
            for _, r in surplus.iterrows():
                bits = []
                for cid, lname in lower:
                    h = best_hosts.get((int(r["tid"]), r["position"], cid))
                    if h is None or h.empty:
                        continue
                    top3 = " · ".join(f"{c.club} **{int(c.rank)}/{int(c.n)}**"
                                      for c in h.head(3).itertuples())
                    n1 = starts_at.get((int(r["tid"]), r["position"], cid), 0)
                    bits.append(f"{lname}: first choice at **{n1}** club(s) — {top3}")
                label = db.player_label(r["tid"], r["name"])
                age = f"{r['age']:.0f}" if pd.notna(r["age"]) else "?"
                if bits:
                    st.markdown(f"**{label}** ({age}, {r['position']})  \n" +
                                "  \n".join(f"&nbsp;&nbsp;{b}" for b in bits))
                else:
                    st.markdown(f"**{label}** ({age}, {r['position']}) — no ranked clubs below us.")
            st.caption(f"Rank inside that club's squad at his position — **1/n** means he'd be "
                       f"their first choice with n-1 bodies behind him, so he'd actually play. "
                       f"A high rank means they'd sit him on the bench. The *first choice at N "
                       f"clubs* count ignores clubs with fewer than {MIN_HOST_SQUAD} players at "
                       f"the position, since topping an empty depth chart proves nothing.")

st.divider()
with st.expander("How the Read column is decided"):
    st.markdown(
        """
- **Keep — starter** — inside the role's slot count (set under *Formation slots* above).
  Flagged **upgrade target** if his ability percentile in our own division is under 40, i.e.
  he starts but shouldn't at this level.
- **Keep — cover** — first man outside the XI.
- **Cover only — primary X** — this isn't his main role, so no transfer verdict is offered
  here; read him in the **X** table instead.
- **Keep — reserves** — 18 or younger; too early for a level judgement either way.
- **Loan out** — under 24 and at least one club in a lower division would play him as their
  first choice at that position (see the destination lists per role).
- **Sell / release** — 23 or older and in the bottom third of our division by ability, or
  nobody below us would start him.
- **Surplus — loan or sell** — behind the cover man with no clear destination.

Ability is **current** ability throughout — a 17-year-old is supposed to rank badly against
senior pros, which is why anyone 19 or under is never flagged as an upgrade target or a sale.

It only knows depth, level, age and whether a lower division would start him — it can't see
morale, personality, a hot streak, or what you're being offered. Overrule it freely.""")

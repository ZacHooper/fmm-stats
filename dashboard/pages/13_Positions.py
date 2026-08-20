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

The computation itself lives in `dashboard/positions.py`, shared with `scripts/build_site.py`
so the phone-readable static site shows the same depth charts and the same verdicts as this
page rather than a second opinion.
"""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db
import positions as P

st.set_page_config(page_title="Positions", page_icon="🧭", layout="wide")
st.title("🧭 Position review")
st.caption("Every position in starting order, with a keep / loan / sell read per player.")
_fam_note = st.empty()

season, phase = db.select_label()
method = db.select_method()

_fam_curve, _fam_lo = db.familiarity_params()

min_fam = st.sidebar.slider(
    "Minimum familiarity", 0, 20, P.DEFAULT_MIN_FAM, step=1,
    help="Drops rows where the player barely knows the position. staging.player_positions "
         "lists every position a player has ANY familiarity in, so at 0 a depth chart of left "
         "backs is padded with centre-halves who could shuffle across. The floor applies to "
         "the comparison pools too, so ability ranks count only players who genuinely play "
         "there — raise or lower it and every rank on the page moves with it.")
excl_loanees = st.sidebar.toggle(
    "Exclude loaned-in players", value=True,
    help="Loanees go back at the end of their spell, so counting them makes the squad look "
         "deeper than it is. Turn off to see the squad as it lines up today.")

# Read the slot counts BEFORE building: they decide the starter / cover / surplus split, so
# every Read on the page depends on them.
with st.expander("Formation slots — how many of each role start", expanded=False):
    st.caption("Drives the starter / cover / surplus split. Defaults to a 4-1-2-3.")
    cols = st.columns(len(P.ROLE_ORDER))
    slots = {}
    for c, role in zip(cols, P.ROLE_ORDER):
        slots[role] = c.number_input(role, 0, 4, P.DEFAULT_SLOTS.get(role, 1), key=f"slot_{role}")

D = P.build(season, phase, method, min_fam=min_fam, excl_loanees=excl_loanees, slots=slots)
if "error" in D:
    st.info(D["error"])
    st.stop()

per_role, ladder = D["per_role"], D["ladder"]
our_cid, our_lg, lower = D["our_cid"], D["our_lg"], D["lower"]
contract, status, prev = D["contract"], D["status"], D["prev"]

# ---------------------------------------------------------------- summary: window priorities
_fam_note.caption(
    f"Showing positions at **familiarity {min_fam}+** (sidebar) — and ranking against players "
    f"who clear the same floor, so nobody is measured against a makeshift field."
    if min_fam else "Familiarity floor off — every listed position counts, including ones a "
                    "player barely knows.")

st.subheader(f"Where the window money goes · {our_lg}")
summary = D["summary"].rename(columns={
    "role": "Role", "owned": "Owned", "slots": "Slots", "best": "Best available",
    "position": "Pos", "fam": "Fam", "div_pct": "Div %ile", "fit_div": "Fit %ile",
    "avg_age": "Avg age of starters", "read": "Read"})
summary[f"His rank in {our_lg}"] = [
    P.rank_cell(D["ranks"], t, p, our_cid)
    for t, p in zip(D["summary"]["best_tid"], D["summary"]["position"])]
summary = summary[["Role", "Owned", "Slots", "Best available", "Pos", "Fam",
                   f"His rank in {our_lg}", "Div %ile", "Fit %ile",
                   "Avg age of starters", "Read"]]
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
pick = st.pills("Positions", D["roles_present"], selection_mode="multi",
                default=D["roles_present"])
show_roles = pick or D["roles_present"]

# ---------------------------------------------------------------- per-role depth charts
for role in show_roles:
    g = per_role[per_role["role"] == role].sort_values("eff", ascending=False)
    n_slots = D["slots"].get(role, 1)
    st.subheader(f"{role} · {len(g)} owned · {n_slots} start")
    tbl = []
    for _, r in g.iterrows():
        row = {"#": int(r["depth"]), "Player": r["name_label"],
               "Age": r["age"], "Pos": r["position"], "Fam": int(r["familiarity"]),
               "Rating": round(r["eff"]), "Fit %ile": r["fit_div"]}
        for cid, lname in ladder:
            row[lname or f"#{cid}"] = P.rank_cell(D["ranks"], r["tid"], r["position"], cid)
        ci = contract.get(int(r["tid"]), {})
        exp = ci.get("Expiry")
        row["Contract"] = pd.to_datetime(exp).strftime("%b %Y") if pd.notna(exp) else "—"
        row["Wage"] = ci.get("Wage")
        row["Last season"] = P.prev_cell(prev, r["tid"])
        row["Squad"] = status.get(int(r["tid"]), "—")
        row["Also"] = r["also"]
        row["Read"] = r["read"]
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
                    h = D["best_hosts"].get((int(r["tid"]), r["position"], cid))
                    if h is None or h.empty:
                        continue
                    top3 = " · ".join(f"{c.club} **{int(c.rank)}/{int(c.n)}**"
                                      for c in h.head(3).itertuples())
                    n1 = D["starts_at"].get((int(r["tid"]), r["position"], cid), 0)
                    bits.append(f"{lname}: first choice at **{n1}** club(s) — {top3}")
                age = f"{r['age']:.0f}" if pd.notna(r["age"]) else "?"
                if bits:
                    st.markdown(f"**{r['name_label']}** ({age}, {r['position']})  \n" +
                                "  \n".join(f"&nbsp;&nbsp;{b}" for b in bits))
                else:
                    st.markdown(f"**{r['name_label']}** ({age}, {r['position']}) — "
                                f"no ranked clubs below us.")
            st.caption(f"Rank inside that club's squad at his position — **1/n** means he'd be "
                       f"their first choice with n-1 bodies behind him, so he'd actually play. "
                       f"A high rank means they'd sit him on the bench. The *first choice at N "
                       f"clubs* count ignores clubs with fewer than {P.MIN_HOST_SQUAD} players "
                       f"at the position, since topping an empty depth chart proves nothing.")

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

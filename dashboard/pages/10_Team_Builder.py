"""Team Builder — assemble an XI slot-by-slot while tuning the tactic live.

Pick a formation, pick the slot you're filling (dropdown), and the right-hand list ranks your
squad (± shortlist) for that slot's role using the SHARED player table (full column control —
add any attribute or match stat). The left weights panel is seeded from a base tactic and
re-ranks the candidates live as you drag; it collapses to give the candidate list more room.

Immersion rule: Fit / Level are PERCENTILES — raw CA is never surfaced. `Squad %ile` reacts to the
live weights (percentile within your candidate pool); `Div %ile` (league fit) and `Level %ile`
(division quality) come from the base tactic and are stable division context.
"""
import bisect
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db
import stat_table

st.set_page_config(page_title="Team Builder", page_icon="🏗️", layout="wide")
st.title("🏗️ Team builder")

CAT = {4: "key", 3: "important", 2: "useful"}


def assign_min_cost(cost):
    """Optimal rectangular assignment (Hungarian / Kuhn-Munkres), n rows ≤ m cols, MINIMISING
    total cost. Returns {row_idx: col_idx} (0-based). Pure-stdlib — no scipy. n≤m required."""
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u = [0.0] * (n + 1); v = [0.0] * (m + 1); p = [0] * (m + 1); way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i; j0 = 0
        minv = [INF] * (m + 1); used = [False] * (m + 1)
        while True:
            used[j0] = True; i0 = p[j0]; delta = INF; j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur; way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]; j1 = j
            for j in range(0, m + 1):
                if used[j]:
                    u[p[j]] += delta; v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
    return {p[j] - 1: j - 1 for j in range(1, m + 1) if p[j] != 0}

# --- formations: rows are laid out attack (top) → GK (bottom) for the pitch view -------------
# each slot = (slot_id, role, duty-hint). role drives the candidate ranking.
FORMATIONS = {
    "4-1-2-3 (SS)": [
        [("AML", "AML", "IF"), ("AMC", "AMC", "SS"), ("AMR", "AMR", "IF")],
        [("CM1", "CM", "RP"), ("CM2", "CM", "BBM")],
        [("DM", "DM", "BWM")],
        [("LB", "LB", "WB"), ("CB1", "CB", "CD"), ("CB2", "CB", "CD"), ("RB", "RB", "WB")],
        [("GK", "GK", "SK")],
    ],
    "4-2-3-1": [
        [("ST", "ST", "PF")],
        [("AML", "AML", "IF"), ("AMC", "AMC", "AP"), ("AMR", "AMR", "IF")],
        [("DM1", "DM", "DLP"), ("DM2", "DM", "BWM")],
        [("LB", "LB", "WB"), ("CB1", "CB", "CD"), ("CB2", "CB", "CD"), ("RB", "RB", "WB")],
        [("GK", "GK", "SK")],
    ],
    "4-3-3": [
        [("AML", "AML", "IF"), ("ST", "ST", "PF"), ("AMR", "AMR", "IF")],
        [("CM1", "CM", "RP"), ("CM2", "CM", "B2B"), ("CM3", "CM", "B2B")],
        [("LB", "LB", "WB"), ("CB1", "CB", "CD"), ("CB2", "CB", "CD"), ("RB", "RB", "WB")],
        [("GK", "GK", "SK")],
    ],
}

# --- duty profiles: attribute overrides layered ON TOP of the slot's base-role weights.
# Anything not listed here falls back to the base role's weight (the "preferred role"), so a
# method stays role-based and duties only tweak what actually differs (RP vs BBM, etc.).
# Each profile both RAISES its signature attributes and LOWERS (→2) the ones the duty doesn't
# rely on, so e.g. RP and BBM genuinely reshuffle the same CM pool rather than inflating uniformly.
DUTY_OVERRIDES = {
    "SK": {"decisions": 4, "positioning": 4, "kicking": 3, "communication": 3},
    "CD": {},                                                    # plain stopper = base CB
    "WB": {"crossing": 4, "pace": 4, "stamina": 4, "movement": 3, "aerial": 2},
    "BWM": {"tackling": 4, "aggression": 4, "decisions": 4, "positioning": 3, "stamina": 3,
            "teamwork": 3, "creativity": 2, "passing": 2},
    "DLP": {"passing": 4, "creativity": 4, "decisions": 4, "technique": 3, "positioning": 3,
            "pace": 2, "aggression": 2, "tackling": 2},
    "Anchor": {"positioning": 4, "tackling": 4, "decisions": 4, "strength": 3, "aerial": 3,
               "creativity": 2, "dribbling": 2, "shooting": 2},
    "RP": {"creativity": 4, "passing": 4, "decisions": 4, "movement": 3, "technique": 3,
           "shooting": 3, "tackling": 2, "aggression": 2},
    "BBM": {"stamina": 4, "tackling": 4, "movement": 4, "teamwork": 4, "aggression": 3,
            "passing": 3, "creativity": 2},
    "B2B": {"stamina": 4, "teamwork": 4, "tackling": 3, "movement": 3, "passing": 3, "shooting": 3,
            "creativity": 2},
    "AP": {"creativity": 4, "passing": 4, "technique": 4, "decisions": 3, "movement": 3,
           "tackling": 2, "aggression": 2},
    "SS": {"movement": 4, "shooting": 4, "pace": 4, "decisions": 3, "technique": 3,
           "crossing": 2, "tackling": 2},
    "IF": {"shooting": 4, "movement": 4, "pace": 4, "dribbling": 3, "technique": 3,
           "crossing": 2, "tackling": 2},
    "Winger": {"crossing": 4, "pace": 4, "dribbling": 4, "stamina": 3, "movement": 3,
               "shooting": 2},
    "PF": {"stamina": 4, "aggression": 4, "movement": 4, "pace": 3, "teamwork": 3},
    "Poacher": {"shooting": 4, "movement": 4, "pace": 3, "technique": 3, "tackling": 2},
    "TM": {"aerial": 4, "strength": 4, "shooting": 3, "teamwork": 3, "pace": 2},
}
# flank/partner slot each slot mirrors, for the "copy to sibling" convenience
MIRROR = {"AML": "AMR", "AMR": "AML", "LB": "RB", "RB": "LB", "CB1": "CB2", "CB2": "CB1",
          "CM1": "CM2", "CM2": "CM1", "DM1": "DM2", "DM2": "DM1"}

# --------------------------------------------------------------------------- header controls
season, phase = db.select_label()          # sidebar: career + season·phase

h1, h2, h3, h4, h5 = st.columns([2, 2, 2, 2, 1])
formation = h1.selectbox("Formation", list(FORMATIONS.keys()), key="tb_formation")
ms = db.methods()
cfg_default = db.config().get("default_method", ms[0])
base_method = h2.selectbox("Base tactic", ms,
                           index=ms.index(cfg_default) if cfg_default in ms else 0,
                           key="tb_method")
pool_mode = h3.segmented_control("Candidate pool", ["Squad only", "Squad + shortlist"],
                                 default="Squad + shortlist", key="tb_pool")
at_club_mode = h4.segmented_control(
    "At club", ["Only", "All"], default="Only", key="tb_atclub",
    help="'Only' drops loaned-in players whose loan has actually lapsed even though their "
         "squad record still reads us (a save-parsing staleness — e.g. a loan that ended "
         "seasons ago but was never refreshed). 'All' shows them anyway.")
if h5.button(("◧ Hide weights" if st.session_state.get("tb_show_w", True) else "◧ Edit weights"),
             width="stretch"):
    st.session_state.tb_show_w = not st.session_state.get("tb_show_w", True)
    st.rerun()
show_w = st.session_state.get("tb_show_w", True)

slots = [s for row in FORMATIONS[formation] for s in row]
slot_ids = [s[0] for s in slots]
slot_role = {s[0]: s[1] for s in slots}
slot_duty = {s[0]: s[2] for s in slots}

# --------------------------------------------------------------------------- session state
if "tb_xi" not in st.session_state:
    st.session_state.tb_xi = {}                       # slot_id -> pid
if "tb_weights" not in st.session_state:
    st.session_state.tb_weights = {}                  # slot_id -> {attr_lower: weight} (per-slot scratch)
if st.session_state.get("tb_weights_base") != base_method:   # reset scratch on base change
    st.session_state.tb_weights = {}
    st.session_state.tb_weights_base = base_method
st.session_state.tb_xi = {k: v for k, v in st.session_state.tb_xi.items() if k in slot_ids}

# --------------------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def load_pool(season, phase, include_short, at_club_only, ver):
    """[{pid, tid, name, is_prospect, positions:{pos:fam}, attrs:{Cap:val}}] — our clubs (+shortlist).
    pid is a stable table key: the tid for real players, a synthetic 'SL#' for tid-less prospects."""
    sq = db.squad(season, phase)
    if at_club_only:
        stale = db.stale_loan_ins(season, phase)
        if stale:
            sq = sq[~sq["tid"].isin(stale)]
    cols = ", ".join(f'"{a}"' for a in db.ATTR_ORDER)
    at = db.q(f"SELECT tid, {cols} FROM staging.player_attributes WHERE season=? AND phase=?",
              [season, phase])
    attr_by_tid = {int(r.tid): {a: int(getattr(r, a)) for a in db.ATTR_ORDER
                                if getattr(r, a) == getattr(r, a)}
                   for r in at.itertuples()}
    pos = db.q("SELECT tid, position, familiarity FROM staging.player_positions "
               "WHERE season=? AND phase=?", [season, phase])
    pos_by_tid = {}
    for r in pos.itertuples():
        pos_by_tid.setdefault(int(r.tid), {})[r.position] = int(r.familiarity)
    pool = []
    for r in sq.itertuples():
        t = int(r.tid)
        if t not in attr_by_tid or not pos_by_tid.get(t):
            continue
        pool.append(dict(pid=t, tid=t, name=r.name, is_prospect=False,
                         positions=pos_by_tid[t], attrs=attr_by_tid[t]))
    if include_short:
        for i, r in enumerate(db.shortlist_get().itertuples()):
            if not r.positions or not r.attributes:
                continue
            tid = int(r.tid) if r.tid == r.tid else None
            pool.append(dict(pid=(tid if tid is not None else f"SL{i}"), tid=tid, name=r.name,
                             is_prospect=True, positions=r.positions, attrs=r.attributes))
    return pool

pool = load_pool(season, phase, pool_mode == "Squad + shortlist", at_club_mode == "Only", db._dbver())
by_pid = {p["pid"]: p for p in pool}
prm = db.pos_role_map()

# Level %ile (raw ability, tactic-agnostic → STATIC) from the base tactic, keyed (tid, role).
# Plus the whole-division population per role, so Div %ile can be recomputed LIVE under the
# slot's duty weights (base-table pctiles never reflect duty tweaks — that's the whole point).
eff_all = db.effective_table(season, phase, base_method)
ctx, league_pop = {}, {}                       # (tid,role)->level | role->[(fam, attrs)]
if not eff_all.empty:
    eff_all = eff_all.copy()
    eff_all["role"] = eff_all["position"].map(prm)
    our = eff_all[eff_all["club_tid"].isin(list(db.OUR_CLUBS))]
    for r in our.sort_values("familiarity", ascending=False).itertuples():
        ctx.setdefault((int(r.tid), r.role), r.level_league)
    lg = our["league_cid"].dropna()
    our_league = int(lg.mode().iloc[0]) if not lg.empty else None
    if our_league is not None:
        div = eff_all[eff_all["league_cid"] == our_league]
        latt = db.attributes_rows(season, phase, [int(t) for t in div["tid"].unique()])
        best = {}                              # (tid, role) -> best familiarity in the division
        for r in div.itertuples():
            if r.role:
                k = (int(r.tid), r.role)
                if k not in best or r.familiarity > best[k]:
                    best[k] = r.familiarity
        for (tid, role), fam in best.items():
            at = latt.get(tid)
            if at:
                league_pop.setdefault(role, []).append((fam, at))

def slot_base_wmap(sid):
    """Base weights for a slot = the base tactic's ROLE weights, with the slot's DUTY overrides
    layered on top (attrs not in the duty fall back to the base role — the 'preferred role')."""
    wm = dict(db.role_weight_map(base_method, slot_role[sid]))
    wm.update(DUTY_OVERRIDES.get(slot_duty[sid], {}))
    return wm

def active_wmap(sid):
    """Live weights for a slot: user's per-slot scratch edits if any, else the duty base."""
    return st.session_state.tb_weights.get(sid) or slot_base_wmap(sid)

def candidates(sid):
    """DataFrame of pool players eligible for slot `sid`'s role, ranked by that slot's live
    (duty-adjusted) weights. Columns: pid, tid, Player, Fam, Squad %ile, Div %ile, Level %ile."""
    role = slot_role[sid]
    wm = active_wmap(sid)
    key_names = [a for a in db.ATTR_ORDER if wm.get(a.lower(), 1) >= 3]
    # LIVE division distribution at this role under the current weights → Div %ile reacts to duty
    dist = sorted(sum(v * wm.get(a.lower(), 1) for a, v in at.items())
                  * db.familiarity_multiplier(fam) for fam, at in league_pop.get(role, []))

    def div_pct(x):
        return round(100 * bisect.bisect_right(dist, x) / len(dist)) if dist else None
    rows = []
    for p in pool:
        fam = max((f for pos, f in p["positions"].items() if prm.get(pos) == role), default=0)
        if fam <= 0:
            continue
        eff = (sum(v * wm.get(a.lower(), 1) for a, v in p["attrs"].items())
               * db.familiarity_multiplier(fam))   # penalise out-of-position, like effective_table
        rows.append(dict(
            pid=p["pid"], tid=p["tid"], Fam=fam, _eff=eff,
            Player=("⭐ " if p["is_prospect"] else "") + str(p["name"]),
            **{"Div %ile": div_pct(eff), "Level %ile": ctx.get((p["tid"], role))},
            **{"Key attrs": " ".join(f"{a[:3].lower()}{p['attrs'].get(a,'-')}" for a in key_names)}))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Squad %ile"] = (df["_eff"].rank(pct=True) * 100).round(0)
    return df.sort_values("_eff", ascending=False).reset_index(drop=True)

# --------------------------------------------------------------------------- layout
if show_w:
    col_w, col_pitch, col_cand = st.columns([3, 3, 5], gap="medium")
else:
    col_pitch, col_cand = st.columns([3, 6], gap="medium")
    col_w = None

# player display names by pid (for pitch + summary)
def surname(pid):
    p = by_pid.get(pid)
    return str(p["name"]).split()[-1] if p and isinstance(p["name"], str) and p["name"] else "—"

# ---- target slot selector (drives the candidate list) ----
def slot_label(sid):
    who = surname(st.session_state.tb_xi.get(sid)) if sid in st.session_state.tb_xi else "—"
    return f"{sid} · {slot_duty[sid]} ({slot_role[sid]}) → {who}"

active = col_cand.selectbox("🎯 Targeting slot", slot_ids, format_func=slot_label, key="tb_slot")
role = slot_role[active]

# ---- weights panel (collapsible) ----
if col_w is not None:
    with col_w:
        st.caption(f"Weights · **{active}** — {slot_duty[active]} (role {role}) · "
                   "duty defaults ⊕ base tactic")
        wm = active_wmap(active)
        wdf = pd.DataFrame({"attribute": db.ATTR_ORDER,
                            "weight": [wm.get(a.lower(), 1) for a in db.ATTR_ORDER]})
        edited = st.data_editor(
            wdf, hide_index=True, width="stretch", key=f"tb_wed_{active}_{base_method}",
            column_config={
                "attribute": st.column_config.TextColumn("attribute", disabled=True),
                "weight": st.column_config.NumberColumn("w", min_value=1, max_value=4, step=1)})
        new_wm = {r.attribute.lower(): int(r.weight) for r in edited.itertuples()
                  if int(r.weight) > 1}
        if new_wm != slot_base_wmap(active):     # store only genuine deviations from the duty base
            st.session_state.tb_weights[active] = new_wm
        b1, b2 = st.columns(2)
        if b1.button("↺ Reset slot", width="stretch", help="Revert to this slot's duty defaults"):
            st.session_state.tb_weights.pop(active, None)
            st.rerun()
        sibs = [s for s in slot_ids if s != active
                and (slot_role[s] == role or MIRROR.get(active) == s)]
        if b2.button("⧉ Copy to siblings", width="stretch", disabled=not sibs,
                     help=f"Apply these weights to {', '.join(sibs) or '—'}"):
            for s in sibs:
                st.session_state.tb_weights[s] = dict(new_wm)
            st.rerun()
        save_as = st.text_input("Save as method", label_visibility="collapsed",
                                placeholder="save as new method…")
        if st.button("💾 Save as method (role-level)", width="stretch", disabled=not save_as):
            if save_as in db.methods():
                st.error(f"'{save_as}' already exists")
            else:
                db.write("INSERT INTO staging.role_weights "
                         "SELECT ?, role, attribute, category, weight FROM staging.role_weights "
                         "WHERE method=?", [save_as, base_method])
                seen = set()
                for sid in slot_ids:            # methods are role-level: first slot per role wins
                    rl = slot_role[sid]
                    if rl in seen:
                        continue
                    seen.add(rl)
                    wmp = {a: w for a, w in active_wmap(sid).items() if w > 1}
                    db.write("DELETE FROM staging.role_weights WHERE method=? AND role=?",
                             [save_as, rl])
                    if wmp:
                        db._conn().executemany(
                            "INSERT INTO staging.role_weights VALUES (?,?,?,?,?)",
                            [(save_as, rl, a, CAT.get(w), w) for a, w in wmp.items()])
                st.cache_data.clear()
                st.success(f"Saved '{save_as}' (role-level; per-slot duties collapse to one "
                           "set per role).")

# ---- pitch (static positional view) ----
with col_pitch:
    st.caption("Pitch")
    for prow in FORMATIONS[formation]:
        cells = st.columns(len(prow))
        for cell, (sid, rl, duty) in zip(cells, prow):
            who = surname(st.session_state.tb_xi.get(sid)) if sid in st.session_state.tb_xi else "—"
            mark = "🎯 " if sid == active else ""
            with cell.container(border=True):
                st.markdown(f"<div style='text-align:center;line-height:1.25'>"
                            f"<small>{mark}{duty}</small><br><b>{who}</b></div>",
                            unsafe_allow_html=True)

# ---- candidates (shared player_table: full column control) ----
with col_cand:
    cdf = candidates(active)
    st.caption(f"Candidates for **{active}** — {slot_duty[active]} (role {role}) · "
               f"ranked by this slot's duty weights · {len(cdf)} eligible")
    if cdf.empty:
        st.info("No eligible players in the pool for this role.")
    else:
        assigned_here = st.session_state.tb_xi.get(active)
        used_elsewhere = {t for s, t in st.session_state.tb_xi.items() if s != active}
        base = cdf.copy()
        base["Player"] = base.apply(
            lambda r: ("✓ " if r.pid == assigned_here else
                       ("· " if r.pid in used_elsewhere else "")) + r.Player, axis=1)
        base = base.rename(columns={"pid": "key"})
        attrs_by = {p["pid"]: p["attrs"] for p in pool}
        cand_tids = [int(t) for t in cdf["tid"].tolist() if t == t and t is not None]
        agg = db.player_match_agg(cand_tids) if cand_tids else pd.DataFrame()
        stat_table.player_table(
            "tb_cand", base[["key", "Player", "Fam", "Squad %ile", "Div %ile",
                             "Level %ile", "Key attrs"]],
            id_options=["Player", "Fam", "Squad %ile", "Div %ile", "Level %ile", "Key attrs"],
            default_cols=["Player", "Fam", "Squad %ile", "Div %ile", "Level %ile", "Key attrs"],
            agg_provider=(lambda keys, a=agg: a) if not agg.empty else None,
            attrs_provider=lambda keys, ab=attrs_by: ab,
            picker_label="Columns (candidates)")
        st.caption("Sorted by the live weights. ✓ in this slot · · used elsewhere · ⭐ prospect. "
                   "**Squad %ile** reacts to the weights (rank within these candidates); "
                   "**Div %ile**/**Level %ile** are base-tactic division context.")

        opts = cdf["pid"].tolist()
        names = {r.pid: r.Player for r in cdf.itertuples()}
        a1, a2, a3 = st.columns([4, 1, 1])
        pick = a1.selectbox("Assign", opts, format_func=lambda t: names.get(t, str(t)),
                            label_visibility="collapsed", key=f"tb_pick_{active}")
        if a2.button("Assign", type="primary", width="stretch"):
            st.session_state.tb_xi = {s: t for s, t in st.session_state.tb_xi.items() if t != pick}
            st.session_state.tb_xi[active] = pick
            st.rerun()
        if a3.button("Clear", width="stretch"):
            st.session_state.tb_xi.pop(active, None)
            st.rerun()

# --------------------------------------------------------------------------- XI summary
st.divider()
filled = [s for s in slot_ids if s in st.session_state.tb_xi]
empty = [s for s in slot_ids if s not in st.session_state.tb_xi]
divs = []                       # live division %ile of each assigned player (duty-adjusted)
for s in filled:
    cd = candidates(s)
    row = cd[cd["pid"] == st.session_state.tb_xi[s]] if not cd.empty else None
    if row is not None and not row.empty and pd.notna(row.iloc[0]["Div %ile"]):
        divs.append(row.iloc[0]["Div %ile"])
m1, m2, m3, m4 = st.columns([2, 2, 3, 2])
m1.metric("XI filled", f"{len(filled)}/{len(slot_ids)}")
m2.metric("Mean Div %ile", f"{round(sum(divs)/len(divs)) if divs else '—'}")
m3.caption("Empty: " + (", ".join(empty) if empty else "none"))
if m4.button("⚡ Suggest best XI", width="stretch",
             help="Optimal assignment (Hungarian): maximises TOTAL squad-fit across the XI — each "
                  "player used once, familiarity-adjusted — not naive slot-by-slot."):
    # score(slot, player) = the player's Squad %ile under THAT SLOT's duty weights (0-100,
    # comparable, familiarity-adjusted). Maximise the sum → minimise the negated cost.
    slot_sc = {}
    for sid in slot_ids:
        cd = candidates(sid)
        if not cd.empty:
            slot_sc[sid] = dict(zip(cd["pid"], cd["Squad %ile"]))
    fill_slots = [s for s in slot_ids if slot_sc.get(s)]
    players = sorted({pid for sc in slot_sc.values() for pid in sc}, key=str)
    xi = {}
    if fill_slots and len(fill_slots) <= len(players):
        BIG = 1e6
        cost = [[-slot_sc[s][pid] if pid in slot_sc[s] else BIG
                 for pid in players] for s in fill_slots]
        res = assign_min_cost(cost)
        for i, sid in enumerate(fill_slots):
            j = res.get(i)
            if j is not None and players[j] in slot_sc[sid]:   # eligible picks only
                xi[sid] = players[j]
    st.session_state.tb_xi = xi
    st.rerun()
if m4.button("🗑️ Clear XI", width="stretch"):
    st.session_state.tb_xi = {}
    st.rerun()

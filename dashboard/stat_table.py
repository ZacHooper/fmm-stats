"""Reusable player-metric picker + table, shared by every page that shows players in
a table (Home, Player Stats, Squad tool).

One unified control: preset macros, then all match-stat display names, then the 1–20
attributes — all in a single multiselect (Streamlit has no native option groups, so the
options are ordered so each category clusters, and fuzzy search — type "90", "%", "Pace"
— finds anything). Presets expand to their stat set on pick; All/None are one click.

`attach_columns` places chosen ATTRIBUTE columns right after the identity block (so they
never get lost off the right edge) and appends the match-stat columns after them.
"""
import pandas as pd
import streamlit as st

import db

PRESET_MACROS = [k for k in db.MATCH_PRESETS if k != "Custom"]


def _valid_opts(include_attrs):
    opts = list(db.MATCH_STAT_DEFS)
    if include_attrs:
        opts += list(db.ATTR_ORDER)
    return opts


def _normalise(skey, include_attrs):
    """on_change: expand any picked preset macro to its stats; drop dups / unknowns,
    preserving order. Runs before the widget re-instantiates, so it's safe to write skey."""
    valid = set(_valid_opts(include_attrs))
    seen, res = set(), []
    for item in st.session_state.get(skey, []):
        for x in (db.MATCH_PRESETS[item] if item in db.MATCH_PRESETS else [item]):
            if x in valid and x not in seen:
                seen.add(x)
                res.append(x)
    st.session_state[skey] = res


def stat_selector(key, default_preset="Custom", include_attrs=True, label="Metrics"):
    """Unified metric picker. Returns (stats, attrs) — display names split by kind.
    `default_preset` seeds the first render (None / unknown -> start empty)."""
    skey = f"{key}_pick"
    if skey not in st.session_state:
        st.session_state[skey] = list(db.MATCH_PRESETS.get(default_preset, []))
    opts = PRESET_MACROS + _valid_opts(include_attrs)

    st.multiselect(
        label, opts, key=skey, on_change=_normalise, args=(skey, include_attrs),
        placeholder="Pick a preset, or search stats/attributes (try '90', '%', 'Pace')…",
        help="Presets (⚽ 🎯 🎩 🛡 🧤) expand to a stat set. Attributes are the raw 1–20 "
             "ratings; match stats need parsed appearances. All = every match stat.")
    with st.container(horizontal=True):          # responsive: wraps on narrow screens
        st.button("All", key=f"{key}_all",
                  on_click=lambda: st.session_state.__setitem__(skey, list(db.MATCH_STAT_DEFS)))
        st.button("None", key=f"{key}_none",
                  on_click=lambda: st.session_state.__setitem__(skey, []))

    chosen = st.session_state[skey]
    stats = [c for c in chosen if c in db.MATCH_STAT_DEFS]
    attrs = [c for c in chosen if c in db.ATTR_ORDER]
    return stats, attrs


def attach_columns(base, stats, attrs, agg, attrs_by, after="Pos"):
    """Return a display frame: `base` (must carry a 'tid' column) with attribute columns
    inserted right after `after` and match-stat columns appended. `agg` is an aggregate
    frame carrying 'tid' + the MATCH_STAT_DEFS columns (may be empty); `attrs_by` is
    {tid: {attr: value}}. 'tid' is dropped from the returned frame."""
    out = base.copy()
    idx = agg.set_index("tid") if (agg is not None and not agg.empty) else None
    for disp in stats:
        col = db.MATCH_STAT_DEFS[disp]
        out[disp] = out["tid"].map(idx[col]) if (idx is not None and col in idx) else pd.NA
    for a in attrs:
        out[a] = out["tid"].map(lambda t: (attrs_by.get(int(t)) or {}).get(a))

    cols = [c for c in out.columns if c != "tid"]
    if attrs and after in cols:
        for a in attrs:
            cols.remove(a)
        i = cols.index(after) + 1
        cols[i:i] = attrs
    return out[cols]

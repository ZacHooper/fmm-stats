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


def _normalise(skey, include_attrs, extra_options=(), attr_presets=None):
    """on_change: expand any picked preset macro (match-stat OR attribute profile) to its
    columns; drop dups / unknowns, preserving order. Runs before the widget re-instantiates,
    so it's safe to write skey."""
    macros = {**db.MATCH_PRESETS, **dict(attr_presets or {})}
    valid = set(_valid_opts(include_attrs)) | set(extra_options)
    seen, res = set(), []
    for item in st.session_state.get(skey, []):
        for x in (macros[item] if item in macros else [item]):
            if x in valid and x not in seen:
                seen.add(x)
                res.append(x)
    st.session_state[skey] = res


def stat_selector(key, default_preset="Custom", include_attrs=True, label="Metrics",
                  extra_options=(), default_extra=(), attr_presets=None):
    """Unified column picker. Returns (stats, attrs) — or (stats, attrs, extras) when
    `extra_options` is given: a leading group of caller-supplied identity/bio column names
    (e.g. Player, Age, Value) that pass straight through, so a page can offer complete
    control over which columns show (including dropping the name). `default_preset`/
    `default_extra` seed the first render (None / unknown -> start empty).
    `attr_presets` = {label: [attribute names]} extra one-click macros that expand to a set of
    ATTRIBUTE columns (e.g. a role's key attributes) — clustered after the match-stat presets."""
    skey = f"{key}_pick"
    extra_options = list(extra_options)
    attr_presets = dict(attr_presets or {})
    if skey not in st.session_state:
        st.session_state[skey] = list(default_extra) + list(db.MATCH_PRESETS.get(default_preset, []))
    opts = extra_options + PRESET_MACROS + list(attr_presets) + _valid_opts(include_attrs)

    hint = "'90', '%', 'Pace', 'Age'" if extra_options else "'90', '%', 'Pace'"
    st.multiselect(
        label, opts, key=skey, on_change=_normalise,
        args=(skey, include_attrs, extra_options, attr_presets),
        placeholder=f"Pick a preset, or search columns (try {hint})…",
        help=("Leading options are identity/bio columns. " if extra_options else "")
             + "Presets (⚽ 🎯 🎩 🛡 🧤) expand to a stat set; ★ presets expand to a role's key "
               "attributes. Attributes are the raw 1–20 ratings; match stats need parsed "
               "appearances. All = every match stat.")
    with st.container(horizontal=True):          # responsive: wraps on narrow screens
        st.button("All", key=f"{key}_all",
                  on_click=lambda: st.session_state.__setitem__(skey, list(db.MATCH_STAT_DEFS)))
        st.button("None", key=f"{key}_none",
                  on_click=lambda: st.session_state.__setitem__(skey, []))

    chosen = st.session_state[skey]
    stats = [c for c in chosen if c in db.MATCH_STAT_DEFS]
    attrs = [c for c in chosen if c in db.ATTR_ORDER]
    if extra_options:
        extras = [c for c in chosen if c in extra_options]
        return stats, attrs, extras
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


def _auto_column_config(cols, extra=None):
    """Sensible column_config: any '…%ile' column renders as a 0–100 progress bar."""
    cfg = {}
    for c in cols:
        if str(c).endswith("%ile"):
            cfg[c] = st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100)
    if extra:
        cfg.update(extra)
    return cfg


def player_table(key, rows, *, id_options=None, default_cols=None,
                 agg_provider=None, attrs_provider=None, include_attrs=True,
                 default_preset=None, picker_label="Columns", column_config=None,
                 attr_presets=None, render=True):
    """THE reusable player table — one component for every page that lists players.

    `rows`: DataFrame with a stable 'key' column (usually the tid; a synthetic id for
        players not in the snapshot) plus any precomputed identity/bio columns you want to
        expose (Player, Pos, Age, Value, Origin, %iles, …).
    `id_options`: identity/bio column names offered in the picker (default: every non-'key'
        column of `rows`, in order). `default_cols`: columns shown on first render.
    `agg_provider(keys)->DataFrame`: returns match-stat aggregates with a 'key' column +
        MATCH_STAT_DEFS columns; called only when a match stat is picked.
    `attrs_provider(keys)->{key: {attr: value}}`: called only when an attribute is picked.
    Everything is add/remove via the same one-box picker (identity + presets + match stats +
    attributes), so the user has complete control over which columns show, on every page."""
    if "key" not in rows.columns:
        raise ValueError("player_table: `rows` must have a 'key' column")
    id_options = list(id_options) if id_options is not None \
        else [c for c in rows.columns if c != "key"]
    skey = f"{key}_pick"
    if skey not in st.session_state:
        st.session_state[skey] = list(default_cols if default_cols is not None else id_options)

    stats, attrs, extras = stat_selector(
        key, default_preset=default_preset, include_attrs=include_attrs,
        label=picker_label, extra_options=id_options, default_extra=id_options,
        attr_presets=attr_presets)

    keys = rows["key"].tolist()
    agg = agg_provider(keys) if (stats and agg_provider) else None
    # providers return their natural aggregate (keyed by 'tid'); normalise to a 'key' column
    # so compose can map, tolerating an empty frame (e.g. a day-1 save with no matches).
    if agg is not None and not agg.empty and "key" not in agg.columns and "tid" in agg.columns:
        agg = agg.assign(key=agg["tid"])
    attrs_by = attrs_provider(keys) if (attrs and attrs_provider) else {}
    out = compose(rows, extras, stats, attrs, agg, attrs_by or {})
    if render:
        st.dataframe(out, width="stretch", hide_index=True,
                     column_config=_auto_column_config(out.columns, column_config))
    return out


def compose(base, id_cols, stats, attrs, agg, attrs_by):
    """Fully column-controlled table. `base` carries 'key' + any precomputed identity/bio
    columns (Player, Age, Value, …). Output columns = `id_cols` + `attrs` + `stats`, in that
    order, filtered to those that exist. Attribute values come from `attrs_by[key]`; match
    stats from `agg` (indexed by 'key'); 'key' is never shown. Rows whose key is missing
    from a source just get blanks (e.g. manual prospects have no match stats)."""
    out = base.copy()
    idx = agg.set_index("key") if (agg is not None and not agg.empty and "key" in agg) else None
    for disp in stats:
        col = db.MATCH_STAT_DEFS[disp]
        out[disp] = out["key"].map(idx[col]) if (idx is not None and col in idx) else pd.NA
    for a in attrs:
        out[a] = out["key"].map(lambda k: (attrs_by.get(k) or {}).get(a))
    cols = [c for c in (list(id_cols) + list(attrs) + list(stats)) if c in out.columns]
    return out[cols]

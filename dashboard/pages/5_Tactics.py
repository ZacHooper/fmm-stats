"""Tactics — create/edit weight-sets and save them back to DuckDB.

A tactic is a named `method` in staging.role_weights. Edit the attribute×role weight
matrix here (1 = default, 2 = useful, 3 = important, 4 = key) and Save writes it back.
Built-in tactics (black_hawk, personal) can be edited but are re-seeded on the next
load_duckdb run; clone them into a new tactic to keep custom priorities permanently."""
import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Tactics", page_icon="🎛️", layout="wide")
st.title("🎛️ Tactic weight-sets")

CAT = {4: "key", 3: "important", 2: "useful"}
ROLES = db.roles()
ATTRS = db.ATTR_ORDER

# ---- create a new tactic (clone) -------------------------------------------------
with st.expander("➕ New tactic (clone from existing)"):
    new_name = st.text_input("New tactic name", placeholder="e.g. gegenpress")
    src = st.selectbox("Clone weights from", db.methods())
    if st.button("Create", disabled=not new_name):
        if new_name in db.methods():
            st.error(f"'{new_name}' already exists.")
        else:
            db.write(
                "INSERT INTO staging.role_weights "
                "SELECT ?, role, attribute, category, weight "
                "FROM staging.role_weights WHERE method=?", [new_name, src])
            st.session_state["method"] = new_name
            st.success(f"Created '{new_name}' from '{src}'.")
            st.rerun()

method = db.select_method()
st.subheader(f"Editing: {method}")
if method in ("black_hawk", "personal"):
    st.warning("Built-in tactic — edits here are overwritten on the next `load_duckdb` "
               "run. Clone it above to make lasting changes.")

# ---- build the attribute × role matrix (default 1) -------------------------------
wm = db.q("SELECT role, attribute, weight FROM staging.role_weights WHERE method=?",
          [method])
matrix = pd.DataFrame(1, index=ATTRS, columns=ROLES, dtype=int)
for _, r in wm.iterrows():
    attr_cap = next((a for a in ATTRS if a.lower() == r["attribute"]), None)
    if attr_cap and r["role"] in matrix.columns:
        matrix.at[attr_cap, r["role"]] = int(r["weight"])

edited = st.data_editor(
    matrix, width='stretch', key=f"editor_{method}",
    column_config={c: st.column_config.NumberColumn(
        c, min_value=1, max_value=4, step=1, format="%d") for c in ROLES})

c1, c2 = st.columns([1, 5])
if c1.button("💾 Save", type="primary"):
    rows = []
    for attr in ATTRS:
        for role in ROLES:
            w = int(edited.at[attr, role])
            if w > 1:  # weight 1 is the implicit default, not stored
                rows.append((method, role, attr.lower(), CAT.get(w), w))
    db.write("DELETE FROM staging.role_weights WHERE method=?", [method])
    if rows:
        db._conn().executemany(
            "INSERT INTO staging.role_weights VALUES (?,?,?,?,?)", rows)
    st.cache_data.clear()
    st.success(f"Saved {len(rows)} weighted cells for '{method}'. Ratings updated.")
    st.rerun()
c2.caption("1 = default (×1, not stored) · 2 = useful · 3 = important · 4 = key. "
           "Saving recomputes every rating that uses this tactic.")

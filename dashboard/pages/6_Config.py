"""Config — tweak app settings on the fly (saved to staging.app_config in DuckDB).

Currently: the position-familiarity multiplier curve + floor, and the default tactic.
Add more keys here as they come up."""
import json

import pandas as pd
import streamlit as st

import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _d if _os.path.exists(_os.path.join(_d, "db.py")) else _os.path.dirname(_d))
import db

st.set_page_config(page_title="Config", page_icon="⚙️", layout="wide")
st.title("⚙️ Config")

cfg = db.config()
CURVES = ["linear_floor", "tiers", "proportional"]

st.subheader("Position familiarity → rating multiplier")
st.caption("How much a player's rating is discounted for playing away from a natural position "
           "(familiarity 1–20). Effective rating = base role rating × this multiplier.")

curve = st.selectbox("Curve", CURVES,
                     index=CURVES.index(cfg.get("familiarity_curve", "linear_floor")))
floor = st.slider("Floor (linear_floor only)", 0.0, 1.0,
                  float(cfg.get("familiarity_floor", 0.5)), 0.05,
                  help="Multiplier at familiarity 0. Higher = gentler penalty.")


def preview_mult(fam):
    fam = max(1, min(20, fam))
    if curve == "proportional":
        return fam / 20.0
    if curve == "tiers":
        return (1.0 if fam >= 18 else 0.95 if fam >= 15 else 0.85 if fam >= 10
                else 0.70 if fam >= 5 else 0.50)
    return floor + (1 - floor) * (fam / 20.0)


prev = pd.DataFrame({"familiarity": [20, 17, 14, 10, 5, 2]})
prev["multiplier"] = prev["familiarity"].map(lambda f: round(preview_mult(f), 3))
c1, c2 = st.columns([1, 2])
c1.dataframe(prev, width="stretch", hide_index=True)
c2.line_chart(prev.set_index("familiarity"))

st.subheader("Defaults")
methods = db.methods()
default_method = st.selectbox("Default tactic", methods,
                              index=methods.index(cfg.get("default_method", methods[0]))
                              if cfg.get("default_method", methods[0]) in methods else 0)

if st.button("💾 Save config", type="primary"):
    db.set_config("familiarity_curve", curve)
    db.set_config("familiarity_floor", floor)
    db.set_config("default_method", default_method)
    st.success("Saved. Ratings across the app now use these settings.")
    st.rerun()

st.divider()
st.caption("Raw config")
st.dataframe(pd.DataFrame(sorted(db.config().items()), columns=["key", "value"]),
             width="stretch", hide_index=True)

st.divider()
st.subheader("Import / export")
st.caption("Bundles your settings, tactics (weight-sets) and position→role map as JSON. "
           "Copy it to back up or move between devices — or commit it as "
           "`seeds/config_bundle.json` to bake it in as the default next build.")
tab_exp, tab_imp = st.tabs(["⬆️ Export", "⬇️ Import"])
with tab_exp:
    blob = json.dumps(db.export_config_bundle(), indent=2)
    st.download_button("Download config.json", blob, "config.json", "application/json")
    st.code(blob, language="json")
with tab_imp:
    up = st.file_uploader("Upload config.json", type="json")
    txt = st.text_area("…or paste config JSON", height=200,
                       value=(up.getvalue().decode("utf-8") if up else ""))
    st.caption("app_config keys are set; tactics are replaced per included method (others "
               "untouched); position→role map replaced if present.")
    if st.button("Apply imported config", type="primary"):
        try:
            summary = db.import_config_bundle(json.loads(txt))
            st.success(f"Imported {summary['app_config']} setting(s), tactics "
                       f"{summary['methods'] or '—'}, {summary['position_role_map']} "
                       f"position mapping(s).")
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't import: {e}")

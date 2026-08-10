---
name: role-weight-methods
description: "How role_weights tactic weight-sets work (mechanics + the frem_counter method), for editing/adding tactics"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**How the weight-sets work.** `staging.role_weights(method, role, attribute, category, weight)` drives
every rating. `v_player_ratings` computes `rating = SUM(attr_value * COALESCE(weight, 1))` per
(method, role) — so **an attribute NOT listed for a role still counts at weight 1** (baseline), it
is not zero. You tune a tactic by *elevating* the attributes that matter above 1: convention is
key=4 / important=3 / useful=2 (category is just the label for the number). To *de-emphasise* an
attribute vs another method, simply leave it off the list (drops to 1) — that's how frem_counter
"removes" black_hawk's striker aggression weighting. There is no way to score *below* 1 (can't
penalise). Roles = 10: GK, LB, RB, CB, DM, CM, AMC, AML, AMR, ST (position→role via
staging.position_role_map). Magnitudes differ by role (raw SUM) but pctile/pos_index standardise
WITHIN position, so cross-role scale doesn't matter.

**Seeding (durable + portable).** Built-in methods live in `seeds/role_weights.csv` and are
(re)seeded by `load_duckdb.seed_role_weights`, which DELETEs `_SEED_METHODS` then re-inserts the
whole CSV. To add a permanent tactic: add its rows to the CSV **and** add its name to
`_SEED_METHODS` in load_duckdb.py (else reseeds duplicate it — delete only targets _SEED_METHODS).
Weights are stored **per-DB**, so after editing the CSV, reseed each existing store (fm-frem/fm-buca)
directly — a full re-extract/load isn't needed. Attribute names are lowercase from
`fmparser.attributes.ATTR_ORDER`.

**frem_counter (added 2026-08).** Frem's tactic weight-set — counter / direct / wing-play 4-2-3-1,
tuned to Frem's identity (pace + finishing up top, dribbling out wide, aerial/physical in both boxes,
slow ball-winning midfield). Deliberate fixes vs black_hawk: **ST** shooting→key + aerial key
(user prefers a taller striker over a slightly more skilful one) + technique/dribbling, dropped
aggression; **AML/AMR** dribbling→key (black_hawk didn't list it — our wingers out-dribble 97% of
division FBs); **AMC** creativity→key, dropped tackling/teamwork; **DM** tackling+positioning keys
(black_hawk's DM was a playmaker with no tackling — wrong for a screen protecting slow CBs); **CB**
pace+aerial+tackling, dropped ball-playing (we don't build from the back); **LB/RB** stamina→key for
overlaps. Validated on Frem squad: Aslani AML 86→99 pctile, Schou DC 58→84, Møller-Jensen DM 39→58,
Herslov AMC 90→96; Balck stays #1 ST. Also seeded into fm-buca so the method exists everywhere; it's
NOT the config default (default_method stays black_hawk) — select it in the dashboard sidebar or
env FM_METHOD. See [[etl-duckdb-dashboard]], [[fmm-tactic-options]].

**frem_gegenpress (added 2026-08, 95 rows).** Frem's mid-22 tactic switch: user abandoned counter,
went **gegenpress 4-1-2-3** (no ST — a **SS in the AMC slot**, wingers AML/AMR, single DM pivot,
two B2B CMs). Weighting philosophy vs frem_counter: **stamina→key almost everywhere** (press is
stamina-hungry), **teamwork + aggression up** (coordinated pressing), **crossing dropped off wide
roles** (central/through play, not early crosses), **CB pace→key + aggression→key** (high line),
**AMC = the focal SS** (movement/shooting/decisions/teamwork all key). Seeded to BOTH stores + added
to `_SEED_METHODS`. **Made the fm-frem default_method** (was frem_counter) since the user committed
to the switch. Squad read: title-leading 3.Div side, but two structural risks for this shape —
**no quality natural DM anchor**, and **slow CBs (Jørgensen/Schou pace ~10-11) behind a high line**.
See [[fmm-tactic-options]], [[denmark-region-drift]].

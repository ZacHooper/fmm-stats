#!/usr/bin/env python3
"""
Frozen attribute model: decodes the entangled 0-255 sub-attribute bytes into the
displayed 1-20 value.

The coefficients below were fitted once (numpy least-squares grid-search) on the 28
Bucaspor players — the only set with BOTH the raw record bytes and the displayed
values. They are frozen here so estimation is a cheap pure-Python dot product with no
training step. See archive/regress.py for the derivation and docs/ATTRIBUTE_DECODING.md
for the write-up. Held-out accuracy: ~63% exact, ~93% within +/-1.

AERIAL IS NOT HERE, and that is deliberate. It is a composite of two PLAIN 1-20 bytes
(Heading + Jumping), so it has a closed form and needs no CA: `attributes.aerial()`,
floor(0.30*heading + 0.70*jumping + 1.0). Fitted it scored 58.9%; the closed form scores
70.8% on two parameters instead of eight. Shooting looks like the same shape and is NOT --
both of ITS bytes are entangled and its closed form scores 28.2%, worse than the fit. See
docs/ca-weighting.md.

Each entry: attr -> (own_offset, partner_offset, feature_names, coefficients).
Offsets are relative to the positions-block start P. Features:
  own    = unwrapped own byte (b+256 if b<128 — the store wraps)
  partner= unwrapped partner byte (doubled attrs: Shooting, Aerial)
  CA, PA = current / potential ability
  own*CA = own * CA / 100
  mean9  = mean of the 9 exactly-known attributes
  fwd    = attacking-ness of the player's top position (1.0 att / 0.5 mid / 0.0 def-GK)
The last coefficient is the intercept.
"""

import math

FROZEN = {
    'Crossing': (-34, None, ('own', 'own*CA'), (0.08999519579991534, 0.025630387368575838, -18.860831479521906)),
    'Dribbling': (-33, None, ('own', 'CA', 'PA', 'mean9'), (0.115446318373027, 0.07557249862260484, -0.01980801124144112, -0.10373544683659013, -23.334996707090387)),
    'Tackling': (-32, None, ('own', 'CA', 'PA', 'fwd'), (0.1056953945376649, 0.06691417388056242, -0.004650993120029635, -0.7306242142738684, -22.324761095178154)),
    'Shooting': (-31, -30, ('CA', 'PA', 'mean9', 'own*CA', 'fwd', 'partner'), (-0.12107033717252294, -0.013010521973013807, -0.09013851655982238, 0.09717281499822003, -0.6855908269424017, 0.024983448808121946, -4.8849413321955115)),
    'Passing': (-27, None, ('own', 'CA', 'PA', 'own*CA'), (0.16632529854274597, 0.20551180269486627, 0.0009404090473238715, -0.07134958074709173, -35.04774730527272)),
    'Decisions': (-26, None, ('own', 'CA', 'PA', 'mean9', 'fwd'), (0.08340501346598053, 0.06945651422018209, -0.030805541047236373, 0.3003657733535151, -0.14574491785861798, -16.397631841001445)),
    'Creativity': (-12, None, ('own', 'own*CA'), (0.08071426329329381, 0.024520182404206062, -16.861599155452467)),
    'Movement': (-11, None, ('own',), (0.11411149447735612, -19.370021482976377)),
    'Positioning': (-10, None, ('own', 'PA', 'fwd'), (0.12664583399785456, 0.043969534161952324, 0.6418631392890262, -26.969486712102224)),
    'Handling': (-7, None, ('CA', 'PA', 'own*CA'), (-0.2501117195574044, 0.03462492172295219, 0.1263106382424207, 0.08877793322692097)),
    'Kicking': (-6, None, ('own', 'CA', 'own*CA'), (0.15934176918282927, 0.17226138205203984, -0.061258982007273595, -32.01305103637253)),
    'Reflexes': (-3, None, ('own', 'mean9', 'own*CA'), (0.07001454493130012, -0.31114525467558707, 0.027978298250900497, -12.392204770604444)),
    'Communication': (-2, None, ('own', 'PA', 'fwd'), (0.06004561519812259, 0.0391703629880327, -0.4216029786408079, -12.808169113715948)),
    'Throwing': (-1, None, ('own', 'CA'), (0.08734088792372058, 0.05996677478064343, -18.830416715773726)),
}

ESTIMATED_ATTRS = tuple(FROZEN)


def uw(b):
    """Unwrap a wrapped 0-255 byte: strong attributes store as low bytes."""
    return b + 256 if b < 128 else b


def predict(attr, mm, P, ca, pa, mean9, fwd):
    """Estimated 1-20 value for one entangled attribute of one player."""
    own_off, partner_off, feats, coef = FROZEN[attr]
    own = uw(mm[P + own_off])
    vals = {"own": own, "CA": ca, "PA": pa, "mean9": mean9,
            "own*CA": own * ca / 100, "fwd": fwd}
    if partner_off is not None:
        vals["partner"] = uw(mm[P + partner_off])
    acc = coef[-1]
    for f, c in zip(feats, coef):
        acc += c * vals[f]
    return max(1, min(20, int(round(acc))))


# ---------------- full 23-attr estimation ----------------
EXACT_SINGLE = {
    "Pace": -24, "Strength": -23, "Stamina": -22, "Technique": -21,
    "Aggression": -19, "Leadership": -16, "Agility": -5,
}

ATTR_ORDER = [
    "Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
    "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
    "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
    "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing",
]

TEAMWORK_W = (0.50, 0.50, 0.0)
AERIAL_W = (0.24, 0.76, 0.8)


def _composite(w, a, b):
    wa, wb, off = w
    return max(1, min(20, int(math.floor(wa * a + wb * b + off))))


def teamwork(unselfishness, work_rate):
    """Displayed Teamwork from the two plain bytes. Exact, not an estimate."""
    return _composite(TEAMWORK_W, unselfishness, work_rate)


def aerial(heading, jumping):
    """Displayed Aerial from the two plain bytes. An ESTIMATE (~71% exact), not a fact."""
    return _composite(AERIAL_W, heading, jumping)


def fwd_of(positions):
    top = max(positions, key=positions.get) if positions else ""
    if top in ("ST", "AML", "AMR", "AMC"):
        return 1.0
    if top in ("ML", "MR", "MC", "DMC", "DML", "DMR"):
        return 0.5
    return 0.0


def estimate_player(mm, rec):
    """Full 23-attr set for one global record: {attr: {'val','est'}}, is_gk, fwd."""
    P, ca, pa = rec["P"], rec["ca"], rec["pa"]
    is_gk = int(rec["positions"].get("GK", 0) == 20)
    fwd = fwd_of(rec["positions"])
    mean9 = sum(rec["attributes"].values()) / len(rec["attributes"])
    out = {}
    for attr, off in EXACT_SINGLE.items():
        out[attr] = {"val": mm[P + off], "est": False}
    out["Teamwork"] = {"val": teamwork(mm[P - 25], mm[P - 9]), "est": False}
    out["Aerial"] = {"val": aerial(mm[P - 29], mm[P - 28]), "est": True}
    for attr in ESTIMATED_ATTRS:
        out[attr] = {"val": predict(attr, mm, P, ca, pa, mean9, fwd), "est": True}
    return out, is_gk, fwd


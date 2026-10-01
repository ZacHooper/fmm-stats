"""The stg layer: one model per raw table, renamed, cast and decoded, nothing joined.

  stg.contracts  the contract grid's used slots; `is_current` = marker 1
  stg.training   the Training page; squad_status kept only where the row's contract flag
                 says the player is under contract. squad_status is a contract term; it is
                 not a loan flag (loans are read from Player Progress, mart.loan_out_spells)
"""
from .. import contract as C
from . import Model

MODELS = [
    Model("stg.contracts", """
SELECT season, phase, tid, marker, marker = 1 AS is_current, wage_units, expiry, start_date
FROM raw.contracts""",
          grain=("season", "phase", "tid"),
          doc="Every used slot of the contract grid as stored; lapsed contracts keep their "
              "dates. A person's current contract is the slot with is_current."),
    Model("stg.training", f"""
SELECT season, phase, tid, intensity, focus_role, focus_attribute, focus_position,
       contracted = {C.CONTRACTED} AS is_contracted,
       CASE WHEN contracted = {C.CONTRACTED} THEN squad_status END AS squad_status
FROM raw.training""",
          grain=("season", "phase", "tid"),
          doc="One row per player (staff have none): training focus, whether the row says he "
              "is under contract, and his squad status where he is."),
]

# archive/

Historical, kept for provenance — **not** part of the pipeline and no longer runnable
as-is (they import the old flat modules that became `fmparser/`).

- `regress.py` — the numpy least-squares grid-search that fitted the attribute model.
  Its output coefficients are frozen into `fmparser/model.py`.
- `estimate_dump.py`, `export_calibration.py` — calibration / diagnostics used while
  deriving the model.
- `fielding.py` — reconstructs an XI shape from formation + posOrder + positions.
  Parked: opponent formations aren't stored and roles/duties aren't recoverable.
- `profiles.py` — early own-squad profile join (name + info + attrs + season aggregate).
- `parse_match.mojo`, `app.🔥` — the original Mojo exploration on a different save.

To rerun `regress.py` (e.g. to re-fit the model on a new career), port its imports to
`fmparser` and feed it that save's managed squad.

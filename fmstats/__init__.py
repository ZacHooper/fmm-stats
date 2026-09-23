"""The transform and query layer over a career store.

`mart` derives every analytical table from the loader's `staging` tables; `store` picks which
copy of a store to read; `scout`, `stats` and `league` are the analysis over the mart; `state`
is the R2-mirrored scout log. fmstats depends on the store, never on `fmparser/`: the staging
schema, plus the column names in `contract`, is the whole interface between the two.
"""

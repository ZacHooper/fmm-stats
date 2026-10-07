"""The transform and query layer over a career store.

`mart` derives every analytical table from the loader's `raw` tables; `store` picks which
copy of a store to read; `state` is the R2-mirrored scout log. fmstats depends on the store,
never on `fmparser/`: the raw schema is the whole interface between the two.
"""

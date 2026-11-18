-- Each region once, as its latest snapshot gives it.
{{ latest(ref('stg_regions'), 'region_id') }}

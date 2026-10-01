SELECT season, phase, tid, marker, marker = 1 AS is_current, wage_units, expiry, start_date
FROM {{ source('raw', 'contracts') }}

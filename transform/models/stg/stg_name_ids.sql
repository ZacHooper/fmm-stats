SELECT season, phase, name_table, id, ordinal FROM {{ source('raw', 'name_ids') }}

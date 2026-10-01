SELECT season, phase, ordinal, name FROM {{ source('raw', 'name_strings') }}

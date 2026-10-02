{#- The attribute decoder's coefficients, one row per (attribute, feature), with the record
    bytes they read NAMED: raw.attribute_model gives each input as its offset in the player
    record (own_offset / partner_offset, e.g. -34); here it becomes the raw.players_raw column
    that holds that byte (crossing_src). `seq` is the seeded order, the order the decode sums
    the terms in. -#}
WITH byte_columns AS (
    SELECT * FROM (VALUES
    {%- for offset, column in var('attribute_columns').items() %}
        ({{ offset }}, '{{ column }}'){{ ',' if not loop.last }}
    {%- endfor %}
    ) AS t(record_offset, column_name)
)
SELECT m.rowid AS seq, m.attribute, m.feature, m.coef,
       own.column_name AS own_column, partner.column_name AS partner_column, m.fitted
FROM {{ source('raw', 'attribute_model') }} m
LEFT JOIN byte_columns own ON own.record_offset = m.own_offset
LEFT JOIN byte_columns partner ON partner.record_offset = m.partner_offset

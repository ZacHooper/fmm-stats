-- The attribute decoder's coefficients, one row per (attribute, feature), with
-- the record bytes they read NAMED: raw.attribute_model gives each input as its
-- offset in the player record (own_offset / partner_offset, e.g. -34); here it
-- becomes the raw.players_raw column that holds that byte (crossing_src). `seq`
-- is the seeded order, the order the decode sums the terms in.

with byte_columns as (
    select
        byte_offsets.record_offset,
        byte_offsets.column_name
    from (
        values
        {% for offset, column in var('attribute_columns').items() %}
        ({{ offset }}, '{{ column }}'){% if not loop.last %},{% endif %}
        {% endfor %}
    ) as byte_offsets (record_offset, column_name)
)

select
    coefficients.rowid as seq,
    coefficients.attribute,
    coefficients.feature,
    coefficients.coef,
    own_byte.column_name as own_column,
    partner_byte.column_name as partner_column,
    coefficients.fitted
from {{ source('raw', 'attribute_model') }} as coefficients
left join byte_columns as own_byte
    on coefficients.own_offset = own_byte.record_offset
left join byte_columns as partner_byte
    on coefficients.partner_offset = partner_byte.record_offset

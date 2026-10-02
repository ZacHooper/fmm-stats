-- The fifteen positions: code, unit and display order.
select
    position,
    unit,
    display_order
from {{ ref('stg_positions') }}

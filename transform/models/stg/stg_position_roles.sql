-- Which role each position is rated in.
select
    position,
    role
from {{ source('raw', 'position_role_map') }}

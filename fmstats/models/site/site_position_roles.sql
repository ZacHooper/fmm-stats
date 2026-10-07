-- The role each position is rated in.
select
    position,
    role
from {{ ref('stg_position_roles') }}

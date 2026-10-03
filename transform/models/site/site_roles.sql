-- mart.roles on the new layers: the player roles by id, with whether the name
-- is inferred rather than read off the game (dim_role).
select
    role_id as id,
    name,
    is_inferred as inferred
from {{ ref('dim_role') }}

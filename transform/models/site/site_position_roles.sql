-- mart.position_roles on the new layers.
select
    position,
    role
from {{ ref('stg_position_roles') }}

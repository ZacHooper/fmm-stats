-- The player roles by id. The save does not say which position a role is
-- played from (Full-Back is played at DL and DR), so a role carries none.
select
    role_id,
    name,
    is_inferred
from {{ ref('stg_roles') }}

-- mart.role_weights on the new layers.
select
    method,
    role,
    attribute,
    weight
from {{ ref('stg_role_weights') }}

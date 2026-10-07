-- Each weight-set's weight for an attribute in a role; an attribute a role
-- does not list counts at weight 1.
select
    method,
    role,
    attribute,
    category,
    weight
from {{ source('raw', 'role_weights') }}

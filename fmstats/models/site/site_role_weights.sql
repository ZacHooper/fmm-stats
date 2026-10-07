-- Each weight-set's attribute weights per role: the web app rates every
-- player itself, from attributes and these weights.
select
    method,
    role,
    attribute,
    weight
from {{ ref('stg_role_weights') }}

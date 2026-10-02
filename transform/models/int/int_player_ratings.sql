-- Every player rated in every role of every weight-set: the sum of attribute x
-- weight, with an attribute the role does not list at weight 1. Derived from
-- the 23 attributes only, so it carries no ability number. The web app computes
-- the same ratings (site/js/data.js); a change to the formula lands in both.

with long as (
    unpivot {{ ref('int_player_attributes') }}
    on
    {% for attribute in var('attr_order') %}
    "{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endfor %}
    into name attribute value value
),

methods as (
    select distinct method from {{ source('raw', 'role_weights') }}
),

roles as (
    select distinct role from {{ source('raw', 'position_role_map') }}
),

-- Every method x every role, not only the pairs role_weights lists: a role with
-- no rows there is FLAT (every attribute at weight 1), which
-- scripts/derive_weight_set.py ships when no weighting beats a flat baseline.
combos as (
    select
        methods.method,
        roles.role
    from methods
    cross join roles
)

select
    long.season,
    long.phase,
    long.tid,
    combos.method,
    combos.role,
    sum(long.value * coalesce(weights.weight, 1)) as rating
from long
cross join combos
left join {{ source('raw', 'role_weights') }} as weights
    on
        combos.method = weights.method
        and combos.role = weights.role
        and lower(long.attribute) = weights.attribute
group by long.season, long.phase, long.tid, combos.method, combos.role

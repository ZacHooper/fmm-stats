-- 50 players at the newest snapshot, every method and role, recomputed by a
-- different route (a sum over the attribute columns rather than the model's
-- UNPIVOT): a row for each rating that is missing or differs, and one if the
-- sample comes back short. A role a weight-set does not list is flat.
{%- set s = rating_sample() %}
{%- set in_sample %}
    season = {{ s.season }}
    and phase = '{{ s.phase }}'
    and tid in ({{ s.tids | join(', ') }})
{%- endset %}

with methods as (
    select distinct method from {{ source('raw', 'role_weights') }}
),

roles as (
    select distinct role from {{ source('raw', 'position_role_map') }}
),

expected as (
    select
        attributes.season,
        attributes.phase,
        attributes.tid,
        methods.method,
        roles.role,
        {% for attribute in var('attr_order') %}
        attributes."{{ attribute }}" * coalesce((
            select weights.weight
            from {{ source('raw', 'role_weights') }} as weights
            where
                weights.method = methods.method
                and weights.role = roles.role
                and weights.attribute = '{{ attribute | lower }}'
        ), 1){% if not loop.last %} +{% else %} as rating{% endif %}
        {% endfor %}
    from {{ ref('int_player_attributes') }} as attributes
    cross join methods
    cross join roles
    where {{ in_sample }}
),

model as (
    select
        season,
        phase,
        tid,
        method,
        role,
        rating
    from {{ ref('int_player_ratings') }}
    where {{ in_sample }}
)

select
    coalesce(expected.tid, model.tid) as tid,
    coalesce(expected.method, model.method) as method,
    coalesce(expected.role, model.role) as role,
    expected.rating as expected_rating,
    model.rating as model_rating
from expected
full outer join model
    on
        expected.season = model.season
        and expected.phase = model.phase
        and expected.tid = model.tid
        and expected.method = model.method
        and expected.role = model.role
where
    expected.rating is null
    or model.rating is null
    or abs(model.rating - expected.rating) > 1e-9
union all
select
    null as tid,
    'empty sample' as method,
    null as role,
    null as expected_rating,
    null as model_rating
where (select count(distinct expected.tid) as n from expected) < 50

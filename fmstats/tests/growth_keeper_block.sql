-- The five keeper attributes (var('gk_only_attributes')) are inert for an
-- outfield player and live for a keeper, which is why a growth total
-- (site_age_curve) leaves them out of an outfielder's sum: on exact reads
-- they average under 10 in sum for outfielders and over 40 for keepers. One
-- row per role whose block is on the wrong side, or has no exact reads.
with blocks as (
    select
        is_goalkeeper,
        avg(
            {% for attribute in var('gk_only_attributes') %}
            "{{ attribute }}"{% if not loop.last %} +{% endif %}
            {% endfor %}
        ) as block_mean
    from {{ ref('fact_player_snapshot') }}
    where has_attributes and not attributes_are_estimated
    group by is_goalkeeper
)

select
    sides.is_goalkeeper,
    blocks.block_mean
from (values (false), (true)) as sides (is_goalkeeper)
left join blocks
    on sides.is_goalkeeper = blocks.is_goalkeeper
where
    blocks.block_mean is null
    or (sides.is_goalkeeper and blocks.block_mean <= 40)
    or (not sides.is_goalkeeper and blocks.block_mean >= 10)

-- How many attribute points a player gains in a year, by his age at its
-- start, keyed age: the quartiles and mean over every pair of a player's
-- snapshots var('forecast').gap_days apart. A player's total is the sum of
-- the attributes his role uses: all of them for a goalkeeper, those but
-- var('gk_only_attributes') for an outfield player.
{% set f = var('forecast') %}
with totals as (
    select
        person_id,
        snapshot_date,
        age,
        case
            when is_goalkeeper
                then
                    {% for attribute in var('attr_order') %}
                    "{{ attribute }}"{% if not loop.last %} +{% endif %}
                    {% endfor %}
            else
                {% for attribute in var('attr_order')
                    if attribute not in var('gk_only_attributes') %}
                "{{ attribute }}"{% if not loop.last %} +{% endif %}
                {% endfor %}
        end as attr_total
    from {{ ref('fact_player_snapshot') }}
    where has_attributes
),

yearly as (
    select
        earlier.age as age_now,
        later.attr_total - earlier.attr_total as delta
    from totals as earlier
    inner join totals as later
        on
            earlier.person_id = later.person_id
            and date_diff('day', earlier.snapshot_date, later.snapshot_date)
            between {{ f.gap_days[0] }} and {{ f.gap_days[1] }}
    where earlier.age is not null
)

select
    age_now as age,
    count(*) as n,
    quantile_cont(delta, 0.25) as p25,
    median(delta) as median,
    avg(delta) as mean,
    quantile_cont(delta, 0.75) as p75
from yearly
group by age_now

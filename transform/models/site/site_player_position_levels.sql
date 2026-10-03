-- mart.player_position_levels on the new layers: each player's familiarity in
-- every position (fact_player_snapshot's pos_*), with his Level %ile there:
-- where his ability ranks among everyone with the position, globally, in his
-- nation's leagues and in his league (site.club_leagues).
with positions as (
    unpivot (
        select
            player.snapshot_date,
            player.tid,
            player.person_id,
            player.team_tid,
            player.ca,
            {% for position in var('positions') %}
            player.pos_{{ position | lower }}{% if not loop.last %},{% endif %}
            {% endfor %}
        from {{ ref('fact_player_snapshot') }} as player
        where player.ca is not null
    )
    on
    {% for position in var('positions') %}
    pos_{{ position | lower }}{% if not loop.last %},{% endif %}
    {% endfor %}
    into name position_column value familiarity
),

base as (
    select
        snapshots.season,
        snapshots.phase,
        snapshots.snap_ix,
        positions.tid,
        positions.person_id,
        upper(replace(positions.position_column, 'pos_', '')) as position,
        roles.role,
        positions.familiarity,
        people.name,
        teams.name as club,
        positions.team_tid as club_tid,
        leagues.league_cid,
        leagues.nation,
        positions.ca
    from positions
    inner join {{ ref('site_snapshots') }} as snapshots
        on positions.snapshot_date = snapshots.phase_date
    inner join {{ ref('dim_person') }} as people
        on positions.person_id = people.person_id
    left join {{ ref('dim_team') }} as teams
        on positions.team_tid = teams.team_tid
    left join {{ ref('stg_position_roles') }} as roles
        on upper(replace(positions.position_column, 'pos_', '')) = roles.position
    left join {{ ref('site_club_leagues') }} as leagues
        on
            snapshots.season = leagues.season
            and snapshots.phase = leagues.phase
            and positions.team_tid = leagues.club_tid
)

select
    season,
    phase,
    snap_ix,
    tid,
    person_id,
    position,
    role,
    familiarity,
    name,
    club,
    club_tid,
    league_cid,
    nation,
    round(
        100 * percent_rank() over (
            partition by season, phase, position order by ca
        ),
        1
    ) as level_global,
    round(
        100 * percent_rank() over (
            partition by season, phase, position, nation order by ca
        ),
        1
    ) as level_nation,
    round(
        100 * percent_rank() over (
            partition by season, phase, position, league_cid order by ca
        ),
        1
    ) as level_league,
    count(*) over (partition by season, phase, position) as n_global,
    count(*) over (partition by season, phase, position, nation) as n_nation,
    count(*) over (
        partition by season, phase, position, league_cid
    ) as n_league
from base

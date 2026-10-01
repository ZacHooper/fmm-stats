-- Every player in our first-team or reserve squad array, with his latest entry
-- in our club's Manager's Best Eleven lists. A player whose own record names
-- another club is on loan to us from it.
{%- set lists = var('club_lists') %}

with managed as (
    select cast(value as integer) as club_tid
    from {{ source('raw', 'app_config') }}
    where key = 'career_managed_tid'
),

ours as (
    select
        extracts.season,
        extracts.phase,
        managed.club_tid,
        0 as reserve
    from {{ source('raw', 'extracts') }} as extracts
    cross join managed
    union all
    select
        details.season,
        details.phase,
        details.tid as club_tid,
        1 as reserve
    from {{ source('raw', 'club_details') }} as details
    inner join managed on details.main_club_tid = managed.club_tid
),

squad as (
    select
        squads.season,
        squads.phase,
        squads.player_tid as tid,
        arg_min(squads.club_tid, ours.reserve) as squad_club_tid
    from {{ source('raw', 'club_squad') }} as squads
    inner join ours
        on
            squads.season = ours.season
            and squads.phase = ours.phase
            and squads.club_tid = ours.club_tid
    group by squads.season, squads.phase, squads.player_tid
),

latest as (
    select entries.*
    from {{ source('raw', 'player_scrapbook') }} as entries
    where entries.list between {{ lists[0] }} and {{ lists[1] }}
    qualify row_number() over (
        partition by entries.season, entries.phase, entries.player_tid
        order by entries.scrapbook_date desc, entries.list desc
    ) = 1
)

select
    squad.season,
    squad.phase,
    squad.tid,
    squad.squad_club_tid,
    clubs.name as squad_club,
    record.club_tid not in (
        select ours.club_tid
        from ours
        where ours.season = squad.season and ours.phase = squad.phase
    ) as loaned_in,
    record.club_tid as own_club_tid,
    record.club as own_club,
    latest.* exclude (season, phase, player_tid)  -- noqa: RF02
from squad
inner join {{ source('raw', 'players_raw') }} as record
    on
        squad.season = record.season
        and squad.phase = record.phase
        and squad.tid = record.tid
left join {{ source('raw', 'clubs') }} as clubs
    on
        squad.season = clubs.season
        and squad.phase = clubs.phase
        and squad.squad_club_tid = clubs.tid
left join latest
    on
        squad.season = latest.season
        and squad.phase = latest.phase
        and squad.tid = latest.player_tid

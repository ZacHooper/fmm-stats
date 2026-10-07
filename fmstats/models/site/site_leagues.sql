-- Every league on every snapshot, keyed (snapshot_date, cid): a competition
-- some team's record names as its league (int.team_leagues). Its name, nation,
-- reputation, tier (the save's level, 1 the top), member_count (the teams in
-- it) and two derived fields:
--
-- skill_idx: the league's average player ability, scaled 0-100 between the
-- weakest and strongest league on the snapshot, where at least
-- var('site_skill_min_players') players are rated (`rated`). An index, so no
-- ability number leaves the view.
--
-- ladder_rank: the comparison ladder a squad player is judged against: 0 is
-- the league of the team we manage, then each league of its nation with a
-- lower reputation, highest first. NULL outside the ladder.
with members as (
    select
        snapshot_date,
        league_cid as cid,
        count(*) as member_count
    from {{ ref('int_team_leagues') }}
    group by snapshot_date, league_cid
),

rated as (
    select
        players.snapshot_date,
        leagues.league_cid as cid,
        avg(players.ca) as mean_ability,
        count(*) as rated
    from {{ ref('fact_player_snapshot') }} as players
    inner join {{ ref('int_team_leagues') }} as leagues
        on
            players.snapshot_date = leagues.snapshot_date
            and players.team_tid = leagues.team_tid
    where players.ca is not null
    group by players.snapshot_date, leagues.league_cid
    having count(*) >= {{ var('site_skill_min_players') }}
),

scaled as (
    select
        snapshot_date,
        cid,
        rated,
        round(
            100.0 * (mean_ability - min(mean_ability) over w)
            / nullif(max(mean_ability) over w - min(mean_ability) over w, 0),
            1
        ) as skill_idx
    from rated
    window w as (partition by snapshot_date)
),

leagues as (
    select
        members.snapshot_date,
        members.cid,
        competitions.name,
        competitions.nation_id,
        nations.name as nation,
        competitions.type,
        competition_snapshots.reputation,
        competitions.level + 1 as tier,
        members.member_count
    from members
    inner join {{ ref('dim_competition') }} as competitions
        on members.cid = competitions.cid
    left join {{ ref('dim_nation') }} as nations
        on competitions.nation_id = nations.nation_id
    left join {{ ref('fact_competition_snapshot') }} as competition_snapshots
        on
            members.snapshot_date = competition_snapshots.snapshot_date
            and members.cid = competition_snapshots.cid
),

ours as (
    select
        leagues.snapshot_date,
        leagues.cid,
        leagues.nation_id,
        leagues.reputation
    from leagues
    inner join {{ ref('int_team_leagues') }} as team_leagues
        on
            leagues.snapshot_date = team_leagues.snapshot_date
            and leagues.cid = team_leagues.league_cid
    inner join {{ ref('stg_career') }} as career
        on team_leagues.team_tid = career.managed_club_tid
),

ladder as (
    select
        leagues.snapshot_date,
        leagues.cid,
        row_number() over (
            partition by leagues.snapshot_date
            order by
                leagues.cid = ours.cid desc,
                leagues.reputation desc,
                leagues.cid asc
        ) - 1 as ladder_rank
    from leagues
    inner join ours
        on leagues.snapshot_date = ours.snapshot_date
    where
        leagues.cid = ours.cid
        or (
            leagues.nation_id is not distinct from ours.nation_id
            and leagues.reputation < ours.reputation
        )
)

select
    leagues.snapshot_date,
    leagues.cid,
    leagues.name,
    leagues.nation,
    leagues.type,
    leagues.reputation,
    leagues.tier,
    leagues.member_count,
    scaled.skill_idx,
    scaled.rated,
    ladder.ladder_rank
from leagues
left join scaled
    on
        leagues.snapshot_date = scaled.snapshot_date
        and leagues.cid = scaled.cid
left join ladder
    on
        leagues.snapshot_date = ladder.snapshot_date
        and leagues.cid = ladder.cid

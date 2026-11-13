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
-- Our pyramid: the leagues of the managed team's nation of the same kind as its
-- own (a league, not a reserve league; men's or women's as ours is). Within it:
--
-- pyramid_rank: 0 the top flight, then down the tiers, our own league first on
-- its tier, then the parallel divisions by reputation, highest first.
-- pyramid_level: the league's tier less ours, so negative above us, 0 on our
-- tier and positive below.
-- ladder_rank: the comparison ladder a squad player is judged against: 0 is our
-- league, then each league on a lower tier of the pyramid in pyramid order.
--
-- All three NULL outside the pyramid.
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
        competitions.short_name,
        competitions.nation_id,
        nations.name as nation,
        competitions.type,
        competition_snapshots.reputation,
        competitions.level + 1 as tier,
        competitions.is_women,
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
        leagues.type,
        leagues.is_women,
        leagues.tier
    from leagues
    inner join {{ ref('int_team_leagues') }} as team_leagues
        on
            leagues.snapshot_date = team_leagues.snapshot_date
            and leagues.cid = team_leagues.league_cid
    inner join {{ ref('stg_career') }} as career
        on team_leagues.team_tid = career.managed_club_tid
),

pyramid as (
    select
        leagues.snapshot_date,
        leagues.cid,
        leagues.cid = ours.cid as is_ours,
        leagues.tier - ours.tier as pyramid_level,
        row_number() over (
            partition by leagues.snapshot_date
            order by
                leagues.tier asc,
                leagues.cid = ours.cid desc,
                leagues.reputation desc,
                leagues.cid asc
        ) - 1 as pyramid_rank
    from leagues
    inner join ours
        on leagues.snapshot_date = ours.snapshot_date
    where
        leagues.cid = ours.cid
        or (
            leagues.nation_id is not distinct from ours.nation_id
            and leagues.type = ours.type
            and leagues.is_women = ours.is_women
            and leagues.tier is not null
        )
),

ladder as (
    select
        snapshot_date,
        cid,
        row_number() over (
            partition by snapshot_date order by pyramid_rank
        ) - 1 as ladder_rank
    from pyramid
    where is_ours or pyramid_level > 0
)

select
    leagues.snapshot_date,
    leagues.cid,
    leagues.name,
    leagues.short_name,
    leagues.nation,
    leagues.type,
    leagues.reputation,
    leagues.tier,
    leagues.member_count,
    scaled.skill_idx,
    scaled.rated,
    pyramid.pyramid_rank,
    pyramid.pyramid_level,
    ladder.ladder_rank
from leagues
left join scaled
    on
        leagues.snapshot_date = scaled.snapshot_date
        and leagues.cid = scaled.cid
left join pyramid
    on
        leagues.snapshot_date = pyramid.snapshot_date
        and leagues.cid = pyramid.cid
left join ladder
    on
        leagues.snapshot_date = ladder.snapshot_date
        and leagues.cid = ladder.cid

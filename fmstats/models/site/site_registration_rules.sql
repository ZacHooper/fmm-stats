-- The squad-registration rules that apply to us on each snapshot, keyed
-- snapshot_date: the managed team's league, its tier and nation, and the
-- rules for that tier (var('registration'), a house rule:
-- docs/danish-registration-rules.md). The home-grown minimums bind in the top
-- tiers only. u21_on is the date the B-list age is taken on: the last new year
-- before the season's second calendar year.
{% set rules = var('registration') %}
select
    clubs.snapshot_date,
    leagues.tier,
    clubs.league_name,
    clubs.nation,
    {{ rules.a_list_max }} as a_list_max,
    case
        when leagues.tier <= {{ rules.hg_tiers }} then {{ rules.hg_min }} else 0
    end as hg_min,
    case
        when leagues.tier <= {{ rules.hg_tiers }} then {{ rules.hg_club_min }}
        else 0
    end as hg_club_min,
    {{ rules.b_list_under_age }} as b_list_under_age,
    {{ rules.min_matchday_age }} as min_matchday_age,
    make_date(cast(snapshots.season as integer) - 1, 1, 1) as u21_on
from {{ ref('site_clubs') }} as clubs
inner join {{ ref('stg_career') }} as career
    on clubs.team_tid = career.managed_club_tid
inner join {{ ref('stg_snapshots') }} as snapshots
    on clubs.snapshot_date = snapshots.snapshot_date
left join {{ ref('site_leagues') }} as leagues
    on
        clubs.snapshot_date = leagues.snapshot_date
        and clubs.league_cid = leagues.cid

-- Where each player we own would get games on loan, keyed (snapshot_date,
-- person_id, position, league_cid, club_tid): for every position he can be
-- picked at (familiarity var('loan_outlook').min_familiarity or more), in each
-- division of the loan ladder (site.loan_clubs) and at each club in it whose
-- formation starts someone there:
--   lvl, n   his Level %ile in that division at the position: the share of
--            the players listing it whose team is in the division and whose
--            ability is below his, of the n of them other than him
--   rank     his place among the club's naturals players at the position (the
--            players its squads list with that familiarity), 1 first choice
--   slots    how many start there in the club's formation (site.loan_clubs)
--   line     the Level %ile of the weakest of those starters, the slots-th
--            best natural player other than him; NULL where the club has
--            fewer, so he walks in
-- He starts iff rank <= slots. Owned: our squad (site.squad) less those on
-- loan to us, with loaned_to_club_tid for one out on loan. Ability orders
-- everything here and never leaves the view: ranks and percentiles only.
-- A club with no natural player at a slot is an open door, not a guess at who
-- its manager would play out of position.
{% set min_familiarity = var('loan_outlook').min_familiarity %}
with listed as (
    {% for position in var('positions') %}
    select
        players.snapshot_date,
        players.person_id,
        players.tid,
        players.ca,
        '{{ position }}' as position,
        players.pos_{{ position | lower }} as familiarity,
        leagues.league_cid
    from {{ ref('fact_player_snapshot') }} as players
    left join {{ ref('int_team_leagues') }} as leagues
        on
            players.snapshot_date = leagues.snapshot_date
            and players.team_tid = leagues.team_tid
    where players.pos_{{ position | lower }} > 0 and players.ca is not null
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

ladder as (
    select distinct
        snapshot_date,
        league_cid,
        ladder_rank
    from {{ ref('site_loan_clubs') }}
),

-- the Level %ile pool: everyone listing the position in a ladder division
pool as (
    select listed.*
    from listed
    inner join ladder
        on
            listed.snapshot_date = ladder.snapshot_date
            and listed.league_cid = ladder.league_cid
),

clubs as (
    select
        clubs.snapshot_date,
        clubs.team_tid,
        clubs.league_cid,
        slots.position,
        slots.slots
    from {{ ref('site_loan_clubs') }} as clubs
    inner join {{ ref('site_formation_slots') }} as slots
        on
            coalesce(clubs.formation, '{{ var("fallback_formation") }}')
            = slots.formation
),

-- each club's natural players at each position, best first
naturals as (
    select
        rostered.snapshot_date,
        rostered.team_tid,
        listed.person_id,
        listed.position,
        listed.ca,
        row_number() over (
            partition by rostered.snapshot_date, rostered.team_tid, listed.position
            order by listed.ca desc, listed.tid asc
        ) as place
    from (
        select distinct
            squads.snapshot_date,
            squads.team_tid,
            squads.person_id
        from {{ ref('squad_membership') }} as squads
        inner join {{ ref('site_loan_clubs') }} as clubs
            on
                squads.snapshot_date = clubs.snapshot_date
                and squads.team_tid = clubs.team_tid
    ) as rostered
    inner join listed
        on
            rostered.snapshot_date = listed.snapshot_date
            and rostered.person_id = listed.person_id
    where listed.familiarity >= {{ min_familiarity }}
),

owned as (
    select
        squad.snapshot_date,
        squad.person_id,
        squad.loaned_to_club_tid,
        listed.position,
        listed.familiarity,
        listed.ca
    from {{ ref('site_squad') }} as squad
    inner join listed
        on
            squad.snapshot_date = listed.snapshot_date
            and squad.person_id = listed.person_id
    where not squad.is_loan_in and listed.familiarity >= {{ min_familiarity }}
),

levels as (
    select
        owned.snapshot_date,
        owned.person_id,
        owned.position,
        ladder.league_cid,
        ladder.ladder_rank,
        count(pool.person_id) filter (where pool.ca < owned.ca) as below,
        count(pool.person_id)
        - count(pool.person_id) filter (where pool.person_id = owned.person_id)
            as n
    from owned
    inner join ladder
        on owned.snapshot_date = ladder.snapshot_date
    left join pool
        on
            owned.snapshot_date = pool.snapshot_date
            and ladder.league_cid = pool.league_cid
            and owned.position = pool.position
    group by
        owned.snapshot_date,
        owned.person_id,
        owned.position,
        ladder.league_cid,
        ladder.ladder_rank
),

hosts as (
    select
        owned.snapshot_date,
        owned.person_id,
        owned.position,
        clubs.league_cid,
        clubs.team_tid as club_tid,
        clubs.slots,
        1 + count(naturals.person_id) filter (
            where naturals.ca >= owned.ca and naturals.person_id <> owned.person_id
        ) as rank,
        count(naturals.person_id) filter (
            where naturals.person_id <> owned.person_id
        ) as others,
        -- the slots-th best other than him: one place further down when he is
        -- among the club's own starters
        clubs.slots
        + coalesce(
            max(
                case
                    when naturals.person_id = owned.person_id
                        and naturals.place <= clubs.slots
                        then 1
                end
            ),
            0
        ) as line_place
    from owned
    inner join clubs
        on
            owned.snapshot_date = clubs.snapshot_date
            and owned.position = clubs.position
    left join naturals
        on
            clubs.snapshot_date = naturals.snapshot_date
            and clubs.team_tid = naturals.team_tid
            and clubs.position = naturals.position
    group by
        owned.snapshot_date,
        owned.person_id,
        owned.position,
        owned.ca,
        clubs.league_cid,
        clubs.team_tid,
        clubs.slots
),

lines as (
    select
        hosts.snapshot_date,
        hosts.person_id,
        hosts.position,
        hosts.club_tid,
        count(pool.person_id) filter (where pool.ca < starter.ca) as below,
        count(pool.person_id)
        - count(pool.person_id) filter (where pool.person_id = starter.person_id)
            as n
    from hosts
    inner join naturals as starter
        on
            hosts.snapshot_date = starter.snapshot_date
            and hosts.club_tid = starter.team_tid
            and hosts.position = starter.position
            and hosts.line_place = starter.place
    left join pool
        on
            hosts.snapshot_date = pool.snapshot_date
            and hosts.league_cid = pool.league_cid
            and hosts.position = pool.position
    where hosts.others >= hosts.slots
    group by
        hosts.snapshot_date,
        hosts.person_id,
        hosts.position,
        hosts.club_tid
)

select
    owned.snapshot_date,
    owned.person_id,
    owned.loaned_to_club_tid,
    owned.position,
    owned.familiarity,
    levels.league_cid,
    levels.ladder_rank,
    case
        when levels.n > 0 then round_even(100.0 * levels.below / levels.n, 0)
    end as lvl,
    levels.n,
    hosts.club_tid,
    hosts.rank,
    hosts.slots,
    case
        when lines.n > 0 then round_even(100.0 * lines.below / lines.n, 0)
    end as line
from owned
inner join levels
    on
        owned.snapshot_date = levels.snapshot_date
        and owned.person_id = levels.person_id
        and owned.position = levels.position
left join hosts
    on
        levels.snapshot_date = hosts.snapshot_date
        and levels.person_id = hosts.person_id
        and levels.position = hosts.position
        and levels.league_cid = hosts.league_cid
left join lines
    on
        hosts.snapshot_date = lines.snapshot_date
        and hosts.person_id = lines.person_id
        and hosts.position = lines.position
        and hosts.club_tid = lines.club_tid

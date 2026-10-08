-- The registration page's flags for our squad (site_registration):
--   null flag        hg_club, hg_association and b_list are never NULL (a
--                    missing origin or birth date reads as 'no')
--   not nested       club-trained implies association-trained
--   basis mismatch   hg_basis names a basis exactly when he is club-trained
--   b-list by age    b_list is the fixed-date test: born after u21_on less
--                    the B-list age (site_registration_rules, the page's
--                    own statement of the rule), so a player who turns 21
--                    during the season stays on it all season
--   empty group      a store with a squad has club-trained and B-list players
-- One row per offending player and snapshot, plus one per empty group.
with registration as (
    select
        registration.*,
        rules.u21_on,
        rules.b_list_under_age
    from {{ ref('site_registration') }} as registration
    left join {{ ref('site_registration_rules') }} as rules
        on registration.snapshot_date = rules.snapshot_date
)

select
    'null flag' as check_name,
    snapshot_date,
    person_id
from registration
where hg_club is null or hg_association is null or b_list is null
union all
select
    'not nested' as check_name,
    snapshot_date,
    person_id
from registration
where hg_club and not hg_association
union all
select
    'basis mismatch' as check_name,
    snapshot_date,
    person_id
from registration
where hg_club is distinct from (hg_basis is not null)
union all
select
    'b-list by age' as check_name,
    snapshot_date,
    person_id
from registration
where
    u21_on is not null
    and b_list is distinct from coalesce(
        dob > cast(u21_on - to_years(b_list_under_age) as date), false
    )
union all
select
    'empty group: ' || groups.name as check_name,
    null as snapshot_date,
    null as person_id
from (
    select
        count(*) as n,
        count(*) filter (where hg_club) as n_club,
        count(*) filter (where b_list) as n_b_list
    from registration
) as counts
cross join (values ('squad'), ('club-trained'), ('b-list')) as groups (name)
where
    case groups.name
        when 'squad' then counts.n
        when 'club-trained' then counts.n_club
        else counts.n_b_list
    end = 0
    and exists (select 1 from {{ ref('stg_snapshots') }})

-- capital_eligible is whether a person's origin club is on the capital-region
-- signing list (seeds/eligible_origin_clubs.csv). Resolving an origin team to
-- its club (an academy or a reserve side to the club that owns it) only adds
-- eligibility: a person whose origin team is itself on the list is eligible.
-- A person with no origin club is not eligible. One row per person whose flag
-- disagrees with the list.
with eligible as (
    select club_tid from {{ ref('stg_eligible_origin_clubs') }}
)

select
    case
        when people.capital_eligible then 'eligible off the list'
        else 'eligibility removed'
    end as check_name,
    people.person_id,
    people.origin_team_tid,
    people.origin_club_tid
from {{ ref('dim_person') }} as people
where
    people.capital_eligible
    is distinct from coalesce(
        people.origin_club_tid in (select eligible.club_tid from eligible),
        false
    )
    or (
        not people.capital_eligible
        and people.origin_team_tid in (select eligible.club_tid from eligible)
    )

-- Our squad on each snapshot, keyed (snapshot_date, person_id), from the
-- squad arrays (mart_squad_membership), never a record's club:
--   * every player our first team or reserve side lists, with is_loan_in for
--     one whose record names another club;
--   * every player whose record names our club and whom another club's side
--     lists on loan: out on loan, loaned_to_club_tid that club.
-- status: 'Loan' out on loan, 'Reserve' listed by our reserve side only,
-- else 'First team'.
with career as (
    select * from {{ ref('stg_career') }}
),

listed as (
    select
        squads.snapshot_date,
        squads.person_id,
        bool_or(squads.team_tid = career.managed_club_tid) as on_first_team,
        bool_or(squads.is_loan_in) as is_loan_in
    from {{ ref('mart_squad_membership') }} as squads
    inner join career
        on squads.club_tid = career.managed_club_tid
    group by squads.snapshot_date, squads.person_id
),

loaned_out as (
    select
        squads.snapshot_date,
        squads.person_id,
        min(squads.club_tid) as loaned_to_club_tid
    from {{ ref('mart_squad_membership') }} as squads
    inner join career
        on
            squads.record_club_tid = career.managed_club_tid
            and squads.club_tid <> career.managed_club_tid
    where
        squads.is_loan_in
        and squads.team_type in (
            {% for team_type in var('loan_team_types') %}
            '{{ team_type }}'{% if not loop.last %},{% endif %}
            {% endfor %}
        )
    group by squads.snapshot_date, squads.person_id
)

select
    coalesce(listed.snapshot_date, loaned_out.snapshot_date) as snapshot_date,
    coalesce(listed.person_id, loaned_out.person_id) as person_id,
    case
        when loaned_out.person_id is not null then 'Loan'
        when not listed.on_first_team then 'Reserve'
        else 'First team'
    end as status,
    coalesce(listed.is_loan_in, false) as is_loan_in,
    loaned_out.loaned_to_club_tid
from listed
full outer join loaned_out
    on
        listed.snapshot_date = loaned_out.snapshot_date
        and listed.person_id = loaned_out.person_id

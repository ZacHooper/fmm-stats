-- Every person in any snapshot, keyed person_id ('<tid>-<dob>': the game hands
-- a retired person's tid to a newgen, so tid alone would join two careers):
-- his name (the latest), date of birth, and the club and season of the oldest
-- career-history line with a club any snapshot holds for him (origin_*: a
-- season without one, unattached before his first club, is not where he came
-- from; NULL for a person who was never at a club). That line is his first
-- only where no snapshot had yet dropped any (int.player_career_lines).
-- origin_team_tid is the team the line names (a first, reserve or B side, or a
-- youth side) and    origin_club_tid the club that owns it (int.team_clubs): a
-- youth side's line counts for the club whose academy it is, with
-- origin_youth_team_tid naming the academy (Frem's "Frem Yth" 65189), so a
-- club's own products are origin_club_tid = that club. A line at a club the
-- save holds no record for keeps its tid as the club. capital_eligible is whether
-- origin_club_tid is on the capital-region signing list (seeds/eligible_origin_clubs.csv).
-- Everything that changes is on the snapshot facts.
with origins as (
    select
        career_lines.person_id,
        career_lines.club_tid as origin_team_tid,
        coalesce(teams.club_tid, career_lines.club_tid) as origin_club_tid,
        case
            when teams.is_youth_side then career_lines.club_tid
        end as origin_youth_team_tid,
        career_lines.season as origin_season,
        eligible.club_tid is not null as capital_eligible
    from {{ ref('int_player_career_lines') }} as career_lines
    left join {{ ref('int_team_clubs') }} as teams
        on career_lines.club_tid = teams.team_tid
    left join {{ ref('stg_eligible_origin_clubs') }} as eligible
        on coalesce(teams.club_tid, career_lines.club_tid) = eligible.club_tid
    where career_lines.club_tid is not null
    qualify row_number() over (
        partition by career_lines.person_id order by career_lines.line_index
    ) = 1
)

select
    persons.person_id,
    persons.tid,
    persons.dob,
    persons.name,
    persons.ethnicity,
    persons.height_cm,
    persons.weight_kg,
    persons.preferred_squad_number,
    persons.foot_left,
    persons.foot_right,
    origins.origin_team_tid,
    origins.origin_club_tid,
    origins.origin_youth_team_tid,
    origins.origin_season,
    origins.capital_eligible,
    persons.first_seen as first_seen_date,
    persons.last_seen as last_seen_date
from {{ ref('int_persons') }} as persons
left join origins
    on persons.person_id = origins.person_id


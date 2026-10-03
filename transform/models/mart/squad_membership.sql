{{ config(materialized='view') }}
-- Who is in each team's squad on each snapshot, keyed (person_id,
-- snapshot_date, team_tid): the squad array, not the club a player's record
-- names (int.squad_membership). Our squad today is
-- `where is_managed_club and is_current`. A view, not stored.
select
    squads.person_id,
    squads.snapshot_date,
    squads.team_tid,
    squads.club_tid,
    squads.team_type,
    squads.slot,
    squads.tid,
    squads.record_team_tid,
    squads.record_club_tid,
    squads.is_loan_in,
    squads.is_managed_club,
    squads.snapshot_date = max(squads.snapshot_date) over () as is_current
from {{ ref('int_squad_membership') }} as squads

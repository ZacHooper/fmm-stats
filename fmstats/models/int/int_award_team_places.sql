-- Every team of the period the store has seen (Team of the Week, Team of the
-- Year, Dream Team ...), its 11 players (slot 1 to 11, the stored order), with
-- the rating that earned each place. The rules for name, person_id and season
-- are award_entries' (macros/).
{{ award_entries(ref('stg_award_team_places'), 'slot', 'rating') }}

-- Every edition of every award the store has seen, its 1st to 3rd places
-- (place 1 to 3), with the score (votes on a voted award, goals on a Top
-- Goalscorer; on a voted award the score does not decide the place). The
-- rules for name, person_id and season are award_entries' (macros/).
{{ award_entries(ref('stg_award_places'), 'place', 'score') }}

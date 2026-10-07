-- Each injury of a player we have tracked (our squad and reserves, Player
-- Progress), keyed (person_id, start_date): a run of injured weeks
-- (int.progress_spells), training injuries included. start_date and end_date
-- are the first and last injured week, so the true dates lie within a week of
-- them. Not split at the season boundary: an injury runs on over the summer.
select
    person_id,
    start_date,
    end_date,
    weeks
from {{ ref('int_progress_spells') }}
where spell_type = 'injured'

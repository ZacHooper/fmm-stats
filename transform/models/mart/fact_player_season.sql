-- Every season line of every player's career history, as the game reports it,
-- keyed (person_id, line_index): the team, the fee code on the selling team's
-- line, and the season's apps, goals (conceded, for a goalkeeper), assists,
-- average rating and cards, all competitions together. A loan year has two
-- lines, the parent team's (0 apps) and the loan team's. Lines are unioned
-- across snapshots, since the game drops a player's oldest lines as it adds
-- new ones and all of a player's lines when he retires
-- (int.player_career_lines); each line's figures are from the latest snapshot
-- holding it, so the line of a season in progress is as of that snapshot.
select
    person_id,
    line_index,
    tid,
    season,
    club_tid as team_tid,
    fee_kind,
    fee_gbp,
    apps,
    goals,
    assists,
    rating,
    yellows,
    reds,
    last_seen_date
from {{ ref('int_player_career_lines') }}

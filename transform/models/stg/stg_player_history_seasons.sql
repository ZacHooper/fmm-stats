-- Each player's career history, one row per season line: seq -1 is the debut
-- line, 0.. follow it. hist_season is the save's own season index (the end
-- year less 1971), season the end year. A loan year has two lines, the parent club's (0 apps)
-- and the loan club's. club_tid is NULL on a line with no club, the game's
-- Free agent (var('no_id16')). goals is goals conceded for a goalkeeper;
-- rating is NULL where the save holds none: before the career it stores 0 or
-- var('no_id16') (0xFFFF). A youth-team line can read 646-648
-- (docs/TODO.md #16b).
--
-- fee is the code on the selling club's line: a number below
-- var('fee_code_floor') is the fee in var('fee_unit_gbp')s; 'free', 'stay' and
-- 'loan' are the loader's names for three codes; var('fee_contract_ended') is a
-- contract that ran out; any other code is unknown. Whether a 'stay' was a
-- Bosman depends on the next line, so it is left to int.
select
    cast(phase as date) as snapshot_date,
    tid,
    seq,
    hist_season,
    end_year as season,
    nullif(club_tid, {{ var('no_id16') }}) as club_tid,
    fee as fee_code,
    case
        when fee in ('free', 'stay', 'loan') then fee
        when try_cast(fee as integer) < {{ var('fee_code_floor') }} then 'fee'
        when try_cast(fee as integer) = {{ var('fee_contract_ended') }}
            then 'contract_ended'
        else 'unknown'
    end as fee_kind,
    case
        when try_cast(fee as integer) < {{ var('fee_code_floor') }}
            then try_cast(fee as bigint) * {{ var('fee_unit_gbp') }}
    end as fee_gbp,
    apps,
    goals,
    assists,
    case
        when round(rating * 100) <> {{ var('no_id16') }} then rating
    end as rating,
    yellows,
    reds
from {{ source('raw', 'player_history_seasons') }}

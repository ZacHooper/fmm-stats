-- The transfer-value model's training rows, one per (tid, entry_date): every
-- value the save states -- a scrapbook entry's, our own squad's and the
-- world's best players' alike -- paired with that player's model inputs
-- (int.player_value_inputs) on the snapshot nearest the entry's date, at most
-- var('value_label_max_gap_days') away. The pairing keeps a tid only while it
-- names the same person: his age on the snapshot, carried back to the entry's
-- date, must agree with the age the entry states within a year and a half (a
-- tid is a slot, reused after a retirement). An entry held by several lists
-- or snapshots is one row, from the latest copy. is_our_club: the entry is in
-- our club's lists (var('club_lists')). scripts/fit_value_model.py fits on it.
{%- set lists = var('club_lists') %}

with entries as (
    select
        player_tid as tid,
        entry_date,
        value as stated_value,
        age as entry_age,
        list between {{ lists[0] }} and {{ lists[1] }} as is_our_club
    from {{ ref('stg_scrapbook_entries') }}
    where value > 0
    qualify row_number() over (
        partition by player_tid, entry_date
        order by snapshot_date desc, list asc
    ) = 1
),

paired as (
    select
        entries.entry_date,
        entries.stated_value,
        entries.is_our_club,
        entries.entry_age,
        abs(date_diff('day', entries.entry_date, inputs.snapshot_date))
            as gap_days,
        inputs.*
    from entries
    inner join {{ ref('int_player_value_inputs') }} as inputs
        on entries.tid = inputs.tid
    where
        abs(date_diff('day', entries.entry_date, inputs.snapshot_date))
        <= {{ var('value_label_max_gap_days') }}
        and abs(
            inputs.age
            - date_diff('day', entries.entry_date, inputs.snapshot_date)
            / 365.25
            - entries.entry_age
        ) <= 1.5
    qualify row_number() over (
        partition by entries.tid, entries.entry_date
        order by gap_days asc, inputs.snapshot_date desc
    ) = 1
)

select * exclude (value)
from paired

-- Club History's Player Records, every written slot of every club: the
-- player who holds each record and its value, in the unit named. record_table
-- is 'overall' or 'season', as for stg_club_records. unk8, unk12 and unk16 are
-- unnamed.
select
    cast(phase as date) as snapshot_date,
    byte_offset,
    club_tid,
    record_table,
    slot,
    category,
    unit,
    player_tid,
    value,
    record_season,
    unk8,
    unk12,
    unk16
from {{ source('raw', 'player_records') }}

-- Club History's Team Records, every written slot of every club. record_table
-- is 'overall' or 'season' (the current season's table). A record held in two
-- slots, or in both tables, is stored twice and stays twice. kind says which
-- fields a category fills: 'match' (opponent and score), 'table' (a league
-- position in value) or 'streak' (a run length in value). day is the day of
-- the year as stored; unk10, unk12 and unk14 are unnamed.
select
    cast(phase as date) as snapshot_date,
    byte_offset,
    club_tid,
    record_table,
    slot,
    category,
    kind,
    opponent_tid,
    score_for,
    score_against,
    value,
    comp_cid,
    record_season,
    day,
    unk10,
    unk12,
    unk14
from {{ source('raw', 'club_records') }}

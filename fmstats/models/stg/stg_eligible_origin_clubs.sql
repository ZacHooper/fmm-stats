-- The clubs whose youth products count as local under the career's signing
-- rule, each with its region: the career's eligible_origin_clubs in fmm.toml.
-- Empty for a career with no rule.
select
    club_tid,
    region
from {{ source('raw', 'eligible_origin_clubs') }}

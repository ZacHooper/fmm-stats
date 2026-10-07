-- The clubs whose youth products count as local under the origin rule, from
-- seeds/eligible_origin_clubs.csv.
select
    club_tid,
    club_name,
    region
from {{ source('raw', 'eligible_origin_clubs') }}

-- mart.managed_club on the new layers: the club the career manages.
select managed_club_tid as club_tid
from {{ ref('stg_career') }}

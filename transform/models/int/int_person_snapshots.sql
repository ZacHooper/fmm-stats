-- Which person each record slot holds on each snapshot: (snapshot_date, tid)
-- -> person_id, the join every fact uses. The game hands a retired person's
-- tid to a newgen, so the tid alone would splice two careers.
select
    snapshot_date,
    tid,
    {{ person_id() }} as person_id,
    is_staff
from {{ ref('stg_persons') }}

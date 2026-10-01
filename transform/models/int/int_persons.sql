-- One row per person across every snapshot, so a retired player whose slot has
-- gone to a newgen keeps his history.
select
    {{ person_id() }} as person_id,
    tid,
    dob,
    arg_max(name, {{ phase_ord() }}) as name,
    arg_min(phase, {{ phase_ord() }}) as first_seen,
    arg_max(phase, {{ phase_ord() }}) as last_seen,
    count(*) as slices
from {{ ref('int_players') }}
group by tid, dob

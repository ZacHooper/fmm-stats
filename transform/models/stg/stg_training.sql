-- One row per player (staff have none): training focus, whether the row says
-- he is under contract, and his squad status where he is. Squad status is a
-- contract term, not a loan flag.
select
    season,
    phase,
    tid,
    intensity,
    focus_role,
    focus_attribute,
    focus_position,
    contracted = {{ var('contracted') }} as is_contracted,
    case
        when contracted = {{ var('contracted') }} then squad_status
    end as squad_status
from {{ source('raw', 'training') }}

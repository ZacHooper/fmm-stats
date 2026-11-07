-- One row per player (staff have none): training focus, whether the row says
-- he is under contract, and the row's +39 byte where he is. +39 is unnamed: it
-- is not the squad status and not a loan flag (docs/parser/training.md).
select
    cast(phase as date) as snapshot_date,
    tid,
    intensity,
    focus_role,
    focus_attribute,
    focus_position,
    contracted = {{ var('contracted') }} as is_contracted,
    case
        when contracted = {{ var('contracted') }} then unknown_39
    end as unknown_39
from {{ source('raw', 'training') }}

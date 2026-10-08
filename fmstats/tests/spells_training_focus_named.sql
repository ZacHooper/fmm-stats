-- Every training Focus Role a player's row names is a role dim_role names.
-- (The Attr codes are not all named: stg_training_attributes lists the ones
-- read off the Training page.)
select
    training.snapshot_date,
    training.tid,
    training.focus_role
from {{ ref('stg_training') }} as training
left join {{ ref('dim_role') }} as roles
    on training.focus_role = roles.role_id
where
    training.focus_role is not null
    and roles.name is null

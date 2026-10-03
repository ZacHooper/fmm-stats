-- mart.training_attributes on the new layers: the training attribute-focus
-- codes the game's screen names.
select
    code,
    abbrev
from {{ ref('stg_training_attributes') }}

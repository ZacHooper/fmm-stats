-- The Training page's Attr column by attribute-focus code
-- (stg_training.focus_attribute), from seeds/training_attributes.csv: the codes
-- read off the page. Codes 0, 2, 4, 10, 12, 13 and 15 also occur and are not
-- yet named.
select
    code,
    abbrev
from {{ source('raw', 'training_attributes') }}

-- mart.app_config on the new layers.
select
    key,
    value
from {{ ref('stg_app_config') }}

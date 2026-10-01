SELECT season, phase, tid, intensity, focus_role, focus_attribute, focus_position,
       contracted = {{ var('contracted') }} AS is_contracted,
       CASE WHEN contracted = {{ var('contracted') }} THEN squad_status END AS squad_status
FROM {{ source('raw', 'training') }}

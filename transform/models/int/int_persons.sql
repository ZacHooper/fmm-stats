SELECT {{ person_id() }} AS person_id, tid, dob,
       arg_max(name, {{ phase_ord() }}) AS name,
       arg_min(phase, {{ phase_ord() }}) AS first_seen,
       arg_max(phase, {{ phase_ord() }}) AS last_seen,
       COUNT(*) AS slices
FROM {{ ref('int_players') }} GROUP BY tid, dob

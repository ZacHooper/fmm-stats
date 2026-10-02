-- Every match event type, named or not (name NULL for a code the loader's
-- seed does not name), with its role: ends_appearance (a sending-off),
-- is_shootout (a shoot-out kick, never a goal) and scores_for ('for' a goal
-- for the player's side, 'against' an own goal).
select
    code as event_type_code,
    name as event_type,
    ends_appearance,
    is_shootout,
    scores_for
from {{ ref('int_event_types') }}

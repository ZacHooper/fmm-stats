-- No relation in the site schema has a raw-ability column (ca, pa or a
-- spelled-out alias): ability leaves the store only as a percentile or a
-- development word. Read from the catalogue, so a site model added later is
-- held too. One row per offending column.
select
    catalogue.table_name,
    catalogue.column_name
from information_schema.columns as catalogue
where
    catalogue.table_catalog = '{{ ref("site_players").database }}'
    and catalogue.table_schema = '{{ ref("site_players").schema }}'
    and lower(catalogue.column_name) in (
        'ca', 'pa', 'aca', 'current_ability', 'potential_ability'
    )
-- The catalogue is read once every site model is built:
-- depends_on: {{ ref('site_age_curve') }} {{ ref('site_attendance') }}
-- depends_on: {{ ref('site_club_managers') }} {{ ref('site_clubs') }}
-- depends_on: {{ ref('site_config') }} {{ ref('site_finances') }}
-- depends_on: {{ ref('site_forecast') }} {{ ref('site_formation_slots') }}
-- depends_on: {{ ref('site_leagues') }} {{ ref('site_loan_clubs') }}
-- depends_on: {{ ref('site_loan_outlook') }} {{ ref('site_match_players') }}
-- depends_on: {{ ref('site_matches') }} {{ ref('site_nations') }}
-- depends_on: {{ ref('site_opponent_match_players') }}
-- depends_on: {{ ref('site_our_teams') }} {{ ref('site_places') }}
-- depends_on: {{ ref('site_player_career') }} {{ ref('site_player_moves') }}
-- depends_on: {{ ref('site_player_spells') }} {{ ref('site_position_roles') }}
-- depends_on: {{ ref('site_registration') }}
-- depends_on: {{ ref('site_registration_rules') }}
-- depends_on: {{ ref('site_role_weights') }} {{ ref('site_snapshots') }}
-- depends_on: {{ ref('site_squad') }} {{ ref('site_team_squads') }}

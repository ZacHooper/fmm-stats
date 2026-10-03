# Site marts: the inventory (data-layers step 17)

Every view `fmstats/mart.py` builds (`mart.ORDER`), who reads it, and what its rebuild in the
`site` schema reads instead. Generated from the code on 2026-10-03: a reader is a file that names
`mart.<view>`; a view no consumer reads but another view does is *internal*, and is rebuilt only
if a rebuilt view still needs it. A view nothing reads is not rebuilt and goes at step 20.

Readers: `export` = `scripts/export_data.py` and `_export_db.py`; `fmstats` = `scout`, `stats`,
`league`, `store`, `compat`, `value_model`; `validate` = `tests/validate_mart.py`; `publish` =
`publish_mart.py` / `publish_duckdb.py`; `skills` = `.claude/skills/`; `site js` = `site/js`.

Each rebuild has the old view's **name and columns**; the area is the step-17 PR that builds it
(17a squads, spells, transfers, managers and the foundation views; 17b person; 17c match and
competition; 17d clubs, nations, registration and the rest).

| old view | area | read by | read by views | rebuilt on |
|---|---|---|---|---|
| `snapshots` | 17a | export, fmq, fmstats, validate, publish, skills | club_leagues, league_tables, staff, club_roster, player_snapshots, player_position_levels, transfers, club_runs, at_club_spells, loan_in_spells, our_loanees_out, snapshot_squad, squad_current, club_squad_latest, player_growth, player_attribute_growth, player_training, player_homegrown, squad_registration | stg_snapshots |
| `role_weights` | 17a | export, fmstats, skills | – | stg_role_weights |
| `position_roles` | 17a | export, fmstats | – | stg_position_roles |
| `app_config` | 17a | export, fmstats | – | raw.app_config (seed) |
| `our_clubs` | 17a | export, fmq, validate, publish, skills | club_matches, managed_club, reserve_clubs, clubs, match_events, competitions, loan_in_spells, our_loanees_out, squad_on, squad_current, squad_finances, club_squad_latest, player_growth_tenure, player_training, player_homegrown | dim_team, stg_career |
| `chosen_match_phase` | 17c (internal) | – | match_player_facts | (none: int_our_matches) |
| `match_player_facts` | 17c | fmstats, validate, publish, skills | rating_baseline, match_ratings, at_club_spells, loan_in_spells, player_vs_club | fact_player_match, dim_match |
| `matches` | 17c | validate, skills | club_matches, managed_club | dim_match, fact_team_match |
| `club_matches` | 17c | export, fmq, fmstats, validate, skills | head_to_head, match_stages | fact_team_match |
| `head_to_head` | 17c | fmstats, validate, skills | – | fact_team_match |
| `managed_club` | 17a | export, fmstats, validate, skills | reserve_clubs, clubs, competitions, comparison_ladder, rating_baseline, player_training, player_homegrown, registration_rules | stg_career |
| `reserve_clubs` | 17a | export, fmstats, validate, skills | our_loanees_out, squad_current | dim_team, stg_career |
| `club_leagues` | 17d | export, validate, skills | clubs, league_tables, competitions, leagues, comparison_ladder, player_snapshots, player_position_levels, club_nations, registration_rules | int_team_leagues / fact_team_snapshot |
| `clubs` | 17d | export, fmq, fmstats, validate, skills | club_attendance, club_places, player_value_est, youth_clubs, club_nations | dim_club, dim_team, fact_team_snapshot, fact_club_snapshot |
| `listed_clubs` | 17d | export | – | dim_team |
| `world_fixtures` | 17c (internal) | – | world_club_fixtures | (none: dim_match) |
| `world_club_fixtures` | 17c | skills | fixture_stages, match_stages, league_tables | dim_match, fact_team_match |
| `fixture_stages` | 17c (internal) | – | league_tables | (none: dim_stage) |
| `match_stages` | 17c | export, validate, skills | – | dim_match, dim_stage, dim_round |
| `league_tables` | 17c | fmq, fmstats, validate, skills | – | standings |
| `club_attendance` | 17d | export | – | fact_team_match |
| `match_events` | 17c | validate | – | fact_match_event |
| `competitions` | not rebuilt (no reader) | – | – | dim_competition |
| `leagues` | 17d | export, skills | comparison_ladder, registration_rules | dim_competition, fact_competition_snapshot |
| `comparison_ladder` | 17d | export | – | site.leagues |
| `languages` | not rebuilt (no reader) | – | – | stg_languages |
| `currencies` | not rebuilt (no reader) | – | – | stg_currencies |
| `nations` | 17d | export | – | dim_nation, fact_nation_snapshot |
| `nation_ranking_history` | not rebuilt (no reader) | – | – | fact_nation_snapshot |
| `nation_coefficients` | 17d | skills | – | fact_nation_snapshot |
| `club_places` | 17d | export | – | dim_stadium, dim_city |
| `staff` | 17a | skills | club_managers, player_snapshots | fact_staff_snapshot, dim_person |
| `club_managers` | 17a | export, fmstats, skills | – | fact_staff_spell (manager), fact_staff_snapshot |
| `club_roster` | 17a | fmq, publish | squad_current | squad_membership |
| `player_snapshots` | 17b | export, fmq, fmstats, validate, skills | player_value_est, player_development, training_focus, attribute_forecast, player_training, player_homegrown | fact_player_snapshot, dim_person |
| `player_position_levels` | 17b | export, fmstats, validate, publish, skills | player_snapshots, player_primary_position, player_position_fit | fact_player_snapshot, int_player_rating_ranks |
| `player_primary_position` | 17b | fmq, fmstats, validate, skills | – | site.player_position_levels |
| `player_value_est` | 17b | fmstats | squad_finances | int_player_value / fact_player_snapshot |
| `player_career_seasons` | 17b | export, skills | player_training, player_homegrown | fact_player_season |
| `transfers` | 17a | export, validate, skills | – | fact_transfer, fact_player_snapshot |
| `player_origin_base` | 17b (internal) | – | youth_clubs, player_origin | dim_person |
| `youth_clubs` | 17b | validate | player_origin, player_homegrown | int_team_clubs |
| `player_origin` | 17b | export, validate | player_homegrown | dim_person, int_team_clubs |
| `player_role_ratings` | 17b (internal) | – | player_position_fit | int_player_ratings |
| `player_position_fit` | 17b | fmstats, validate, publish, skills | – | int_player_ratings, int_player_rating_ranks |
| `rating_roles` | 17c | export, fmstats, validate, skills | rating_baseline, match_ratings | seed / dim_role |
| `rating_baseline` | 17c | validate | match_ratings | fact_player_match |
| `match_ratings` | 17c | export, fmstats, validate, skills, site js | player_seasons, player_role_seasons | fact_player_match |
| `player_seasons` | 17c | validate, skills | player_growth_season | fact_player_competition_season |
| `player_role_seasons` | 17c | validate, skills | – | fact_player_match |
| `club_runs` | 17a | validate | at_club_spells, player_growth_at_club | fact_player_snapshot |
| `at_club_spells` | 17a | fmstats, validate, publish, skills | player_spells, player_vs_club, player_training | fact_player_snapshot, fact_player_match |
| `loan_in_spells` | 17a | validate | at_club_spells, player_spells | fact_loan_spell, fact_player_match |
| `progress_weeks` | 17a | validate, skills | loan_out_spells, injury_spells | stg_player_progress, int_person_snapshots |
| `loan_out_spells` | 17a | export, skills | player_snapshots, our_loanees_out, player_spells | int_progress_spells (on_loan) |
| `injury_spells` | 17a | skills | player_spells | fact_injury_spell |
| `our_loanees_out` | not rebuilt (no reader) | – | – | fact_loan_spell |
| `player_spells` | 17a | export, validate, publish, skills | squad_on, snapshot_squad, squad_current, player_growth_tenure | the four spell views |
| `squad_on` | 17a | export, validate, publish, skills, site js | player_snapshots, at_club_spells | site.player_spells (macro) |
| `snapshot_squad` | 17a | fmstats, publish, skills | squad_finances, club_squad_latest | site.player_spells |
| `squad_current` | 17a | export, fmstats, validate, publish, skills | club_squad_latest, squad_registration | squad_membership |
| `squad_finances` | 17d | export, validate, skills | – | squad_membership, fact_player_snapshot |
| `club_squad_latest` | 17a | fmq, fmstats, validate, skills | – | squad_membership |
| `player_development` | 17b | export, validate, skills | – | fact_player_snapshot |
| `roles` | 17b | skills | training_focus | dim_role |
| `training_attributes` | 17b | skills | training_focus | stg_training_attributes |
| `training_focus` | 17b | validate, skills | – | fact_player_snapshot, dim_role |
| `player_vs_club` | 17c | fmstats, validate, skills | – | fact_player_match |
| `player_growth` | 17b | validate, publish, skills | player_growth_season, player_growth_at_club, player_growth_tenure, growth_age_curve | fact_player_snapshot |
| `player_attribute_growth` | 17b | validate, publish | – | fact_player_snapshot |
| `player_growth_season` | 17b | validate, publish, skills | – | site.player_growth, site.player_seasons |
| `player_growth_at_club` | 17b | validate | – | site.player_growth, site.club_runs |
| `player_growth_tenure` | 17b | validate, skills | – | site.player_growth, site.player_spells |
| `attribute_forecast` | 17b | export, validate, site js | – | site.player_snapshots |
| `growth_age_curve` | 17b | export, validate, site js | – | site.player_growth |
| `club_nations` | 17d | validate | player_homegrown | dim_club |
| `player_training` | 17d | validate, publish | player_homegrown | fact_player_season, site.at_club_spells |
| `player_homegrown` | 17d | export, validate | squad_registration | site.player_training, site.player_origin |
| `registration_rules` | 17d | export, validate | squad_registration | seed |
| `squad_registration` | 17d | export, validate | – | site.player_homegrown, site.squad_current |

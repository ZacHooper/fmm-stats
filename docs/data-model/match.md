# Match — semantic model

Conceptual model only; names are not final tables. Builds on
[`competition.md`](competition.md): a match belongs to a round, and through it to a stage and a
competition.

**Core idea:** a match is a **dimension**. It is one game at one time, place and round, and
every match-level fact hangs off it. What happens in the game is recorded at three grains:
**team × match** (one row per side), **player × match** (the lineup and each player's stats) and
**event** (goals, cards, subs, shootout kicks, each with a minute and a period).

```mermaid
erDiagram
    dim_round       ||--o{ dim_match : "contains"
    dim_date        ||--o{ dim_match : "played on"
    dim_stadium     ||--o{ dim_match : "played at"
    dim_referee     ||--o{ dim_match : "refereed by"
    dim_team        ||--o{ dim_match : "home / away"
    dim_stadium     |o--o{ dim_team : "home ground"

    dim_match       ||--|{ fact_team_match : "2 rows per match"
    dim_team        ||--o{ fact_team_match : "team / opponent"
    dim_manager     ||--o{ fact_team_match : "managed by"
    dim_formation   ||--o{ fact_team_match : "started in"

    dim_match       ||--o{ fact_player_match : "in"
    dim_player      ||--o{ fact_player_match : "by"
    dim_team        ||--o{ fact_player_match : "for"

    dim_match       ||--o{ fact_match_event : "in"
    dim_event_type  ||--o{ fact_match_event : "is a"
    dim_period      ||--o{ fact_match_event : "during"
    dim_team        ||--o{ fact_match_event : "credited to"
    dim_player      |o--o{ fact_match_event : "by / secondary"

    dim_match {
        int match_key PK
        int round_key FK
        int stage_key FK
        int season FK
        date match_date FK
        time kickoff
        int home_team_key FK
        int away_team_key FK
        int stadium_key FK
        int referee_key FK
        int attendance
        string group_label
        int tie_id
        int leg
        string decided_by "90 / ET / pens"
        string score_display "convenience only"
    }
    dim_team {
        int team_key PK
        int home_stadium_key FK
    }
    dim_stadium {
        int stadium_key PK
        string city
        int capacity
    }
    fact_team_match {
        int match_key FK
        int team_key FK
        int opponent_key FK
        string venue "H / A / N"
        int manager_key FK
        int formation_key FK
        int goals_for "from the scoreline"
        int goals_against
        int pens_for "shootout"
        int pens_against
        string result "W / D / L"
        int points
    }
    fact_player_match {
        int match_key FK
        int player_key FK
        int team_key FK "the side he played for that day"
        bool started
        string position_played
        int minutes
        int goals
        int assists
        float rating
    }
    fact_match_event {
        int event_key PK
        int match_key FK
        int event_type_key FK
        int period_key FK
        int minute
        int team_key FK "side credited"
        int player_key FK
        int secondary_player_key FK "assister / sub on / fouled"
    }
```

## Dimensions

| Dimension | Holds |
|---|---|
| `dim_match` | round (+ stage, competition), season, date + kick-off, home/away team, stadium, referee, attendance, group/tie/leg labels, how it was decided, display score |
| `dim_stadium` | name, city, capacity |
| `dim_team` | adds `home_stadium_key`. **Neutral venue is derived**: the match stadium isn't the home team's ground. |
| `dim_referee` | match official: name, nation |
| `dim_manager` | each side's manager on the day |
| `dim_formation` | shape, e.g. 4-2-3-1 |
| `dim_event_type` | goal, own goal, shootout kick, card, sub, injury… (the loader already seeds `staging.event_types`) |
| `dim_period` | 1st half, 2nd half, ET 1st, ET 2nd, shootout |
| `dim_player`, `dim_date` | the usual |

## Decisions

- **Formation and manager are per side**, so they go on `fact_team_match`, not on the match.
  A change during the game is an event.
- **"Match overall stats" is `fact_team_match`.** The whole-match total is a view over its two
  rows, not a separate fact.
- **Period and minute belong to events**, not to the match.
- **Kick-off time is an attribute**, not a dimension.
- **A player's team comes from the match**, not from the player, because players change clubs.

## Sources of truth for goals

| Question | Source | Why |
|---|---|---|
| The scoreline | **the save's recorded score** → `fact_team_match.goals_for/against` | sourced directly, so it doesn't depend on the events being complete |
| Who scored, and when | **events** | only events carry **own goals** (credited to the other side, with no player tally) and **shootout kicks** |
| A player's goal tally | events, excluding own goals and shootout kicks | a shootout kick isn't a goal |
| Shootout result | events (period = shootout) → `pens_for/against` | not in player stats |

The two sources check each other: for every match, goal events per side (outside the shootout)
must equal the recorded scoreline. A mismatch means events are missing or misattributed, never
a reason to overwrite the score.

## Out of scope

Stats beyond goals (which column each comes from is decided per stat when it is built) and
in-match tactics.

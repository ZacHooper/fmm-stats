# Competition — semantic model

Conceptual model only; names are not final tables.

**Core idea:** a competition is a fixed sequence of **stages**. Each stage's **format** decides
what it produces: a league-format stage produces a ranking, and a knockout stage produces the
winners of its ties. **The winner is the outcome of the final stage.** Rules are fixed per
competition in FMM, so **season is only a key**. (competition, season) is the grain shared by
participation, outcomes and standings.

```mermaid
erDiagram
    dim_nation      ||--o{ dim_competition : "scopes"
    dim_competition ||--|{ dim_stage : "made of"
    dim_stage       ||--|{ dim_round : "made of"
    dim_round       ||--o{ dim_match : "contains"
    dim_season      ||--o{ dim_match : "played in"
    dim_team        ||--o{ dim_match : "home / away"
    dim_match       ||--|{ fact_team_match : "2 rows per match"
    dim_team        ||--o{ fact_team_match : "team / opponent"
    dim_match       ||--o{ fact_player_match : "in"
    dim_player      ||--o{ fact_player_match : "by"
    dim_team        ||--o{ fact_participation : "enters"
    dim_competition ||--o{ fact_participation : "of"
    dim_season      ||--o{ fact_participation : "in"
    dim_team        ||--o{ fact_competition_outcome : "finishes"
    dim_competition ||--o{ fact_competition_outcome : "of"
    dim_season      ||--o{ fact_competition_outcome : "in"
    dim_stage       ||--o{ fact_competition_outcome : "stage reached"

    dim_competition {
        int competition_key PK
        int nation_key FK
        string type "league / cup / continental / friendly"
        int level
    }
    dim_stage {
        int stage_key PK
        int competition_key FK
        int stage_order
        string format "league / knockout / single"
        int legs
        string progression
        string tie_breakers
        bool points_carry_over
        bool is_final_stage
    }
    dim_round {
        int round_key PK
        int stage_key FK
        int round_order
    }
    dim_match {
        int match_key PK
        int round_key FK
        int stage_key FK "redundant, for filtering"
        int season FK
        date match_date
        int home_team_key FK
        int away_team_key FK
        string group_label
        int tie_id
        int leg
        string decided_by "90 / ET / pens"
        string score_display "convenience only"
    }
    fact_team_match {
        int match_key FK
        int team_key FK
        int opponent_key FK
        string venue "H / A / N"
        int goals_for
        int goals_against
        int points
    }
    fact_player_match {
        int match_key FK
        int player_key FK
        int team_key FK
        int minutes
        int goals
        float rating
    }
    fact_participation {
        int team_key FK
        int competition_key FK
        int season FK
    }
    fact_competition_outcome {
        int team_key FK
        int competition_key FK
        int season FK
        int stage_reached FK
        int final_position
        bool is_winner
    }
```

## Decisions

- **Stage and round are separate tables.** The outcome's `stage_reached` needs a stage-grain key.
- **A match is a dimension.** It describes the game and several facts share it. The score lives
  on `fact_team_match`. `score_display` is for reading and is never summed.
- **Group, tie and leg are labels** on the match, not dimensions.
- **`fact_team_match` is one row per side**, so the team you ask about is always in one column.
  Count matches from `dim_match`, not from this table.
- **Given from the save:** participation, team-match and player-match. Everything else is derived.

## Views, not stored

- **`tie_results`**: matches grouped by `tie_id` → aggregate, winner, decided by.
- **`standings`**: league-format stages only. Cumulative team-match rows ranked by the stage's
  tie-breakers, keyed by date as well as round. Knockout stages use `tie_results` instead.

## Winner

```mermaid
flowchart TD
    C[Competition × season] --> F{Final stage format?}
    F -->|league| W1[position 1 in final standings]
    F -->|knockout| W2[winner of the final tie]
    F -->|single match| W3[match winner]
    W1 --> O[(fact_competition_outcome)]
    W2 --> O
    W3 --> O
    G[save's recorded outcome] -. ground truth .-> O
```

Stored, so consumers don't re-derive it. Where the save records outcomes (the standings record,
[`../standings-record.md`](../standings-record.md)), the save is the source and our derivation
is the check.

## Out of scope

Rules per season, promotion/qualification links (you can derive them from participation plus
`level`), and match detail (next ticket).

**Open question:** does the save store a two-legged tie as one round with a leg number, or as
two rounds? Check `mart.match_stages`.
